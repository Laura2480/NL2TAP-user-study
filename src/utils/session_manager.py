"""
Session manager for user study — handles participant registration,
session persistence, condition assignment, and scenario counterbalancing.

Data is stored in a SQLite database for durability (survives crashes,
ngrok restarts, Streamlit reruns). Each participant gets a unique session
with assigned condition order and scenario allocation.

Schema:
- participants: anonymous ID, profile, condition order, timestamps
- sessions: per-scenario session data (start/end, condition, scenario)
- interactions: raw interaction log (mirrors interaction_logger but in DB)
"""
import hashlib
import json
import random
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = Path("results/study.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")  # safe for concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS participants (
            participant_id TEXT PRIMARY KEY,
            anon_hash TEXT NOT NULL,
            user_type TEXT NOT NULL,
            lang TEXT NOT NULL DEFAULT 'it',
            condition_order TEXT NOT NULL,
            scenario_assignment TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            sus_data TEXT,
            tlx_data TEXT
        );

        CREATE TABLE IF NOT EXISTS scenario_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id TEXT NOT NULL REFERENCES participants(participant_id),
            scenario_code TEXT NOT NULL,
            condition TEXT NOT NULL,
            complexity_class TEXT,
            scenario_index INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            final_correct TEXT,
            eval_notes TEXT,
            total_turns INTEGER DEFAULT 0,
            total_elapsed_s REAL DEFAULT 0,
            final_code TEXT,
            l1_syntax_ok INTEGER,
            l1_api_valid INTEGER,
            exec_pass_rate REAL,
            UNIQUE(participant_id, scenario_code)
        );

        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id TEXT NOT NULL REFERENCES participants(participant_id),
            scenario_code TEXT NOT NULL,
            turn INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            elapsed_s REAL NOT NULL,
            event TEXT NOT NULL,
            data TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


# Initialize on import
init_db()


# ============================================================
# PARTICIPANT MANAGEMENT
# ============================================================

def _hash_id(raw_id: str) -> str:
    """Create anonymized hash of participant ID for publication."""
    return hashlib.sha256(raw_id.encode()).hexdigest()[:12]


def register_participant(
    participant_id: str,
    user_type: str,
    lang: str,
    scenario_pool: List[dict],
) -> Dict[str, Any]:
    """Register a new participant or return existing registration.

    Assigns condition order (A-first or B-first) and scenario allocation
    using Latin Square counterbalancing.

    Returns dict with:
        participant_id, anon_hash, condition_order, scenario_assignment
    """
    conn = _get_conn()

    # Check if already registered
    row = conn.execute(
        "SELECT * FROM participants WHERE participant_id = ?",
        (participant_id,),
    ).fetchone()

    if row:
        conn.close()
        return {
            "participant_id": row["participant_id"],
            "anon_hash": row["anon_hash"],
            "condition_order": json.loads(row["condition_order"]),
            "scenario_assignment": json.loads(row["scenario_assignment"]),
            "already_registered": True,
        }

    # Count existing participants for counterbalancing
    count = conn.execute("SELECT COUNT(*) FROM participants").fetchone()[0]

    # Condition order: alternate A-first / B-first
    condition_order = ["single_shot", "orchestrator"] if count % 2 == 0 else ["orchestrator", "single_shot"]

    # Assign scenarios: split pool by complexity, assign to conditions
    assignment = _assign_scenarios(scenario_pool, condition_order)

    anon_hash = _hash_id(participant_id)

    conn.execute(
        """INSERT INTO participants
           (participant_id, anon_hash, user_type, lang, condition_order,
            scenario_assignment, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            participant_id,
            anon_hash,
            user_type,
            lang,
            json.dumps(condition_order),
            json.dumps(assignment),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    return {
        "participant_id": participant_id,
        "anon_hash": anon_hash,
        "condition_order": condition_order,
        "scenario_assignment": assignment,
        "already_registered": False,
    }


def _assign_scenarios(
    scenario_pool: List[dict],
    condition_order: List[str],
) -> List[dict]:
    """Assign scenarios to conditions with complexity balancing.

    Each condition gets an equal number of scenarios from each complexity class.
    Returns list of {scenario_code, condition, complexity_class, index}.
    """
    # Group by complexity
    by_complexity: Dict[str, List[dict]] = {}
    for sc in scenario_pool:
        cc = sc.get("complexity_class", "C1")
        by_complexity.setdefault(cc, []).append(sc)

    assignment = []
    idx = 0

    for cc, scenarios in sorted(by_complexity.items()):
        shuffled = list(scenarios)
        random.shuffle(shuffled)

        # Split evenly between conditions
        per_condition = len(shuffled) // len(condition_order)
        if per_condition < 1:
            per_condition = 1

        for ci, cond in enumerate(condition_order):
            start = ci * per_condition
            end = start + per_condition
            for sc in shuffled[start:end]:
                assignment.append({
                    "scenario_code": sc["code"],
                    "condition": cond,
                    "complexity_class": cc,
                    "index": idx,
                })
                idx += 1

    return assignment


# ============================================================
# SCENARIO SESSION MANAGEMENT
# ============================================================

def start_scenario_session(
    participant_id: str,
    scenario_code: str,
    condition: str,
    complexity_class: str = "",
    scenario_index: int = 0,
):
    """Record the start of a scenario session."""
    conn = _get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO scenario_sessions
           (participant_id, scenario_code, condition, complexity_class,
            scenario_index, started_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            participant_id,
            scenario_code,
            condition,
            complexity_class,
            scenario_index,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def complete_scenario_session(
    participant_id: str,
    scenario_code: str,
    final_correct: str,
    eval_notes: str = "",
    total_turns: int = 0,
    total_elapsed_s: float = 0,
    final_code: str = "",
    l1_syntax_ok: bool = None,
    l1_api_valid: bool = None,
    exec_pass_rate: float = None,
):
    """Record completion of a scenario session."""
    conn = _get_conn()
    conn.execute(
        """UPDATE scenario_sessions SET
           completed_at = ?,
           final_correct = ?,
           eval_notes = ?,
           total_turns = ?,
           total_elapsed_s = ?,
           final_code = ?,
           l1_syntax_ok = ?,
           l1_api_valid = ?,
           exec_pass_rate = ?
           WHERE participant_id = ? AND scenario_code = ?""",
        (
            datetime.now(timezone.utc).isoformat(),
            final_correct,
            eval_notes,
            total_turns,
            total_elapsed_s,
            final_code,
            1 if l1_syntax_ok else 0 if l1_syntax_ok is not None else None,
            1 if l1_api_valid else 0 if l1_api_valid is not None else None,
            exec_pass_rate,
            participant_id,
            scenario_code,
        ),
    )
    conn.commit()
    conn.close()


# ============================================================
# INTERACTION LOGGING (DB-backed, crash-safe)
# ============================================================

def log_interaction(
    participant_id: str,
    scenario_code: str,
    turn: int,
    elapsed_s: float,
    event: str,
    data: dict,
):
    """Log a single interaction event to the database."""
    conn = _get_conn()
    conn.execute(
        """INSERT INTO interactions
           (participant_id, scenario_code, turn, timestamp, elapsed_s, event, data)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            participant_id,
            scenario_code,
            turn,
            datetime.now(timezone.utc).isoformat(),
            elapsed_s,
            event,
            json.dumps(data, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()


# ============================================================
# QUESTIONNAIRE DATA
# ============================================================

def save_questionnaire(
    participant_id: str,
    sus_data: dict = None,
    tlx_data: dict = None,
):
    """Save SUS and/or NASA-TLX responses for a participant."""
    conn = _get_conn()
    updates = []
    params = []
    if sus_data is not None:
        updates.append("sus_data = ?")
        params.append(json.dumps(sus_data, ensure_ascii=False))
    if tlx_data is not None:
        updates.append("tlx_data = ?")
        params.append(json.dumps(tlx_data, ensure_ascii=False))
    if updates:
        params.append(participant_id)
        conn.execute(
            f"UPDATE participants SET {', '.join(updates)} WHERE participant_id = ?",
            params,
        )
        conn.commit()
    conn.close()


# ============================================================
# DATA EXPORT (for analysis)
# ============================================================

def export_participants_csv(output_path: str = "results/participants.csv"):
    """Export participants table to CSV."""
    import csv
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM participants").fetchall()
    if not rows:
        conn.close()
        return
    keys = rows[0].keys()
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
    conn.close()


def export_sessions_csv(output_path: str = "results/scenario_sessions.csv"):
    """Export scenario sessions to CSV."""
    import csv
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM scenario_sessions").fetchall()
    if not rows:
        conn.close()
        return
    keys = rows[0].keys()
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
    conn.close()


def export_interactions_csv(output_path: str = "results/interactions.csv"):
    """Export all interactions to CSV."""
    import csv
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM interactions").fetchall()
    if not rows:
        conn.close()
        return
    keys = rows[0].keys()
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
    conn.close()


def get_participant_progress(participant_id: str) -> Dict[str, Any]:
    """Get a participant's progress — which scenarios are completed."""
    conn = _get_conn()
    completed = conn.execute(
        """SELECT scenario_code, condition, final_correct
           FROM scenario_sessions
           WHERE participant_id = ? AND completed_at IS NOT NULL""",
        (participant_id,),
    ).fetchall()
    conn.close()
    return {
        "completed_scenarios": [dict(r) for r in completed],
        "n_completed": len(completed),
    }
