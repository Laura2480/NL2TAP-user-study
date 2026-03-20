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
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = _PROJECT_ROOT / "results" / "study.db"
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
            counterbalance_group TEXT NOT NULL DEFAULT 'AB',
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
            eval_behavioral_match TEXT,
            eval_confidence INTEGER,
            eval_mismatch_reason TEXT,
            eval_code_correct TEXT,
            sandbox_all_pass INTEGER,
            attempt_number INTEGER DEFAULT 1,
            discrepancy_user_vs_sandbox TEXT,
            intent_evolution TEXT,
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

        CREATE TABLE IF NOT EXISTS toast_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id TEXT NOT NULL REFERENCES participants(participant_id),
            block INTEGER NOT NULL,
            condition TEXT NOT NULL,
            item_1 INTEGER NOT NULL,
            item_2 INTEGER NOT NULL,
            item_3 INTEGER NOT NULL,
            item_4 INTEGER NOT NULL,
            item_5 INTEGER NOT NULL,
            item_6 INTEGER NOT NULL,
            item_7 INTEGER NOT NULL,
            item_8 INTEGER NOT NULL,
            item_9 INTEGER NOT NULL,
            understanding_mean REAL,
            performance_mean REAL,
            overall_mean REAL,
            submitted_at TEXT NOT NULL,
            UNIQUE(participant_id, block)
        );

        CREATE TABLE IF NOT EXISTS tlx_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id TEXT NOT NULL REFERENCES participants(participant_id),
            block INTEGER NOT NULL,
            condition TEXT NOT NULL,
            mental_demand INTEGER NOT NULL,
            physical_demand INTEGER NOT NULL,
            temporal_demand INTEGER NOT NULL,
            performance INTEGER NOT NULL,
            effort INTEGER NOT NULL,
            frustration INTEGER NOT NULL,
            raw_tlx_mean REAL,
            submitted_at TEXT NOT NULL,
            UNIQUE(participant_id, block)
        );

        CREATE TABLE IF NOT EXISTS sus_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id TEXT NOT NULL,
            block INTEGER NOT NULL DEFAULT 0,
            condition TEXT NOT NULL DEFAULT '',
            item_1 INTEGER NOT NULL,
            item_2 INTEGER NOT NULL,
            item_3 INTEGER NOT NULL,
            item_4 INTEGER NOT NULL,
            item_5 INTEGER NOT NULL,
            item_6 INTEGER NOT NULL,
            item_7 INTEGER NOT NULL,
            item_8 INTEGER NOT NULL,
            item_9 INTEGER NOT NULL,
            item_10 INTEGER NOT NULL,
            sus_score REAL,
            submitted_at TEXT NOT NULL,
            UNIQUE(participant_id, block)
        );

        CREATE TABLE IF NOT EXISTS auth_sessions (
            token TEXT PRIMARY KEY,
            participant_id TEXT NOT NULL,
            user_type TEXT NOT NULL,
            lang TEXT NOT NULL DEFAULT 'it',
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            invalidated INTEGER NOT NULL DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()


def _migrate_db():
    """Add columns that may be missing in older databases."""
    conn = _get_conn()
    # Get existing columns for scenario_sessions
    cursor = conn.execute("PRAGMA table_info(scenario_sessions)")
    existing = {row[1] for row in cursor.fetchall()}

    new_cols = [
        ("eval_behavioral_match", "TEXT"),
        ("eval_confidence", "INTEGER"),
        ("eval_mismatch_reason", "TEXT"),
        ("eval_code_correct", "TEXT"),
        ("sandbox_all_pass", "INTEGER"),
        ("attempt_number", "INTEGER DEFAULT 1"),
        ("discrepancy_user_vs_sandbox", "TEXT"),
        ("intent_evolution", "TEXT"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE scenario_sessions ADD COLUMN {col_name} {col_type}")

    # Migrate participants table
    cursor = conn.execute("PRAGMA table_info(participants)")
    p_existing = {row[1] for row in cursor.fetchall()}
    if "counterbalance_group" not in p_existing:
        conn.execute("ALTER TABLE participants ADD COLUMN counterbalance_group TEXT DEFAULT 'AB'")

    # Ensure toast_responses table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS toast_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id TEXT NOT NULL REFERENCES participants(participant_id),
            block INTEGER NOT NULL,
            condition TEXT NOT NULL,
            item_1 INTEGER NOT NULL,
            item_2 INTEGER NOT NULL,
            item_3 INTEGER NOT NULL,
            item_4 INTEGER NOT NULL,
            item_5 INTEGER NOT NULL,
            item_6 INTEGER NOT NULL,
            item_7 INTEGER NOT NULL,
            item_8 INTEGER NOT NULL,
            item_9 INTEGER NOT NULL,
            understanding_mean REAL,
            performance_mean REAL,
            overall_mean REAL,
            submitted_at TEXT NOT NULL,
            UNIQUE(participant_id, block)
        )
    """)

    # Ensure tlx_responses table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tlx_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id TEXT NOT NULL REFERENCES participants(participant_id),
            block INTEGER NOT NULL,
            condition TEXT NOT NULL,
            mental_demand INTEGER NOT NULL,
            physical_demand INTEGER NOT NULL,
            temporal_demand INTEGER NOT NULL,
            performance INTEGER NOT NULL,
            effort INTEGER NOT NULL,
            frustration INTEGER NOT NULL,
            raw_tlx_mean REAL,
            submitted_at TEXT NOT NULL,
            UNIQUE(participant_id, block)
        )
    """)

    # Ensure sus_responses table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sus_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id TEXT NOT NULL,
            item_1 INTEGER NOT NULL,
            item_2 INTEGER NOT NULL,
            item_3 INTEGER NOT NULL,
            item_4 INTEGER NOT NULL,
            item_5 INTEGER NOT NULL,
            item_6 INTEGER NOT NULL,
            item_7 INTEGER NOT NULL,
            item_8 INTEGER NOT NULL,
            item_9 INTEGER NOT NULL,
            item_10 INTEGER NOT NULL,
            sus_score REAL,
            submitted_at TEXT NOT NULL,
            UNIQUE(participant_id)
        )
    """)

    # Ensure auth_sessions table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS auth_sessions (
            token TEXT PRIMARY KEY,
            participant_id TEXT NOT NULL,
            user_type TEXT NOT NULL,
            lang TEXT NOT NULL DEFAULT 'it',
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            invalidated INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Migrate sus_responses: add block + condition columns if missing
    cursor = conn.execute("PRAGMA table_info(sus_responses)")
    sus_cols = {row[1] for row in cursor.fetchall()}
    if "block" not in sus_cols:
        # Recreate table with new schema (old had UNIQUE(participant_id))
        conn.executescript("""
            ALTER TABLE sus_responses RENAME TO _sus_old;
            CREATE TABLE sus_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_id TEXT NOT NULL,
                block INTEGER NOT NULL DEFAULT 0,
                condition TEXT NOT NULL DEFAULT '',
                item_1 INTEGER NOT NULL,
                item_2 INTEGER NOT NULL,
                item_3 INTEGER NOT NULL,
                item_4 INTEGER NOT NULL,
                item_5 INTEGER NOT NULL,
                item_6 INTEGER NOT NULL,
                item_7 INTEGER NOT NULL,
                item_8 INTEGER NOT NULL,
                item_9 INTEGER NOT NULL,
                item_10 INTEGER NOT NULL,
                sus_score REAL,
                submitted_at TEXT NOT NULL,
                UNIQUE(participant_id, block)
            );
            INSERT INTO sus_responses (participant_id, block, condition,
                item_1, item_2, item_3, item_4, item_5,
                item_6, item_7, item_8, item_9, item_10,
                sus_score, submitted_at)
            SELECT participant_id, 0, '',
                item_1, item_2, item_3, item_4, item_5,
                item_6, item_7, item_8, item_9, item_10,
                sus_score, submitted_at
            FROM _sus_old;
            DROP TABLE _sus_old;
        """)

    conn.commit()
    conn.close()


# Initialize on import
init_db()
_migrate_db()


# ============================================================
# PARTICIPANT MANAGEMENT
# ============================================================

def _hash_id(raw_id: str) -> str:
    """Create anonymized hash of participant ID for publication."""
    return hashlib.sha256(raw_id.encode()).hexdigest()[:12]


def get_participant_registration(participant_id: str) -> Optional[Dict[str, Any]]:
    """Read-only: return existing registration or None (does NOT create)."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM participants WHERE participant_id = ?",
        (participant_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "participant_id": row["participant_id"],
        "anon_hash": row["anon_hash"],
        "counterbalance_group": row["counterbalance_group"],
        "condition_order": json.loads(row["condition_order"]),
        "scenario_assignment": json.loads(row["scenario_assignment"]),
        "already_registered": True,
    }


def register_participant(
    participant_id: str,
    user_type: str,
    lang: str,
    scenario_pool: List[dict],
) -> Dict[str, Any]:
    """Register a new participant or return existing registration.

    Within-subjects design: every participant does both conditions A and B.
    Counterbalancing group (AB or BA) is assigned randomly.
    6 scenarios split into two blocks of 3 (one C1 + one C2 + one C3 per block).

    Returns dict with:
        participant_id, anon_hash, counterbalance_group, condition_order,
        scenario_assignment
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
            "counterbalance_group": row["counterbalance_group"],
            "condition_order": json.loads(row["condition_order"]),
            "scenario_assignment": json.loads(row["scenario_assignment"]),
            "already_registered": True,
        }

    # Random counterbalancing: half AB, half BA
    cb_group = random.choice(["AB", "BA"])
    condition_order = ["A", "B"] if cb_group == "AB" else ["B", "A"]

    # Assign scenarios split into two blocks with alternating conditions
    assignment = _assign_scenarios_within(scenario_pool, condition_order)

    anon_hash = _hash_id(participant_id)

    conn.execute(
        """INSERT INTO participants
           (participant_id, anon_hash, user_type, lang, condition_order,
            counterbalance_group, scenario_assignment, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            participant_id,
            anon_hash,
            user_type,
            lang,
            json.dumps(condition_order),
            cb_group,
            json.dumps(assignment),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    return {
        "participant_id": participant_id,
        "anon_hash": anon_hash,
        "counterbalance_group": cb_group,
        "condition_order": condition_order,
        "scenario_assignment": assignment,
        "already_registered": False,
    }


def _assign_scenarios_within(
    scenario_pool: List[dict],
    condition_order: List[str],
) -> List[dict]:
    """Assign scenarios into two blocks for within-subjects design.

    If scenarios have an 'assigned_block' field (pre-assigned in study_utils),
    use that. Otherwise fall back to splitting by complexity class.

    Block 1 → condition_order[0], Block 2 → condition_order[1].
    Scenarios within each block are shuffled.

    Returns list of {scenario_code, condition, complexity_class, block, index}.
    """
    block1: List[dict] = []
    block2: List[dict] = []

    # Check if scenarios have pre-assigned blocks
    has_preassigned = any(sc.get("assigned_block") for sc in scenario_pool)

    if has_preassigned:
        for sc in scenario_pool:
            cc = sc.get("complexity_class") or sc.get("complexity_tag") or "C1"
            entry = {
                "scenario_code": sc["code"],
                "complexity_class": cc,
                "block_order": sc.get("block_order", 0),
            }
            if sc.get("assigned_block", 1) == 1:
                block1.append(entry)
            else:
                block2.append(entry)
    else:
        # Fallback: split by complexity class
        by_complexity: Dict[str, List[dict]] = {}
        for sc in scenario_pool:
            cc = sc.get("complexity_class") or sc.get("complexity_tag") or "default"
            by_complexity.setdefault(cc, []).append(sc)

        for cc, scenarios in sorted(by_complexity.items()):
            shuffled = list(scenarios)
            random.shuffle(shuffled)
            mid = len(shuffled) // 2
            block1.extend(
                {"scenario_code": sc["code"], "complexity_class": cc, "block_order": 0}
                for sc in shuffled[:mid]
            )
            block2.extend(
                {"scenario_code": sc["code"], "complexity_class": cc, "block_order": 0}
                for sc in shuffled[mid:]
            )

    # Sort within each block: simple before complex (by block_order)
    block1.sort(key=lambda x: x.get("block_order", 0))
    block2.sort(key=lambda x: x.get("block_order", 0))

    # Build final assignment with conditions and indices
    assignment = []
    for idx, sc in enumerate(block1):
        sc["condition"] = condition_order[0]
        sc["block"] = 1
        sc["index"] = idx
        sc.pop("block_order", None)
        assignment.append(sc)
    for idx, sc in enumerate(block2):
        sc["condition"] = condition_order[1]
        sc["block"] = 2
        sc["index"] = len(block1) + idx
        sc.pop("block_order", None)
        assignment.append(sc)

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
    """Record the start of a scenario session.

    Safe: will NOT overwrite a row that already has completed_at set.
    """
    conn = _get_conn()
    conn.execute(
        """INSERT INTO scenario_sessions
           (participant_id, scenario_code, condition, complexity_class,
            scenario_index, started_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(participant_id, scenario_code) DO UPDATE SET
             started_at = CASE WHEN completed_at IS NULL THEN excluded.started_at ELSE started_at END,
             condition = CASE WHEN completed_at IS NULL THEN excluded.condition ELSE condition END""",
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
    final_correct: str = "",
    eval_notes: str = "",
    total_turns: int = 0,
    total_elapsed_s: float = 0,
    final_code: str = "",
    l1_syntax_ok: bool = None,
    l1_api_valid: bool = None,
    exec_pass_rate: float = None,
    eval_behavioral_match: str = "",
    eval_confidence: int = None,
    eval_mismatch_reason: str = "",
    eval_code_correct: str = None,
    sandbox_all_pass: bool = None,
    attempt_number: int = 1,
    discrepancy_user_vs_sandbox: str = "",
    intent_evolution: str = "",
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
           exec_pass_rate = ?,
           eval_behavioral_match = ?,
           eval_confidence = ?,
           eval_mismatch_reason = ?,
           eval_code_correct = ?,
           sandbox_all_pass = ?,
           attempt_number = ?,
           discrepancy_user_vs_sandbox = ?,
           intent_evolution = ?
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
            eval_behavioral_match,
            eval_confidence,
            eval_mismatch_reason,
            eval_code_correct,
            1 if sandbox_all_pass else 0 if sandbox_all_pass is not None else None,
            attempt_number,
            discrepancy_user_vs_sandbox,
            intent_evolution,
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


def save_toast_response(
    participant_id: str,
    block: int,
    condition: str,
    items: List[int],
):
    """Save TOAST questionnaire responses for a block.

    items: list of 9 integers (1-7 Likert scale).
    Items 1-4 = System Understanding, Items 5-9 = System Performance.
    """
    if len(items) != 9:
        raise ValueError(f"TOAST requires exactly 9 items, got {len(items)}")

    understanding_mean = sum(items[:4]) / 4.0
    performance_mean = sum(items[4:]) / 5.0
    overall_mean = sum(items) / 9.0

    conn = _get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO toast_responses
           (participant_id, block, condition,
            item_1, item_2, item_3, item_4,
            item_5, item_6, item_7, item_8, item_9,
            understanding_mean, performance_mean, overall_mean,
            submitted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            participant_id, block, condition,
            *items,
            understanding_mean, performance_mean, overall_mean,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_toast_responses(participant_id: str) -> List[Dict[str, Any]]:
    """Get all TOAST responses for a participant."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM toast_responses WHERE participant_id = ? ORDER BY block",
        (participant_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_tlx_response(
    participant_id: str,
    block: int,
    condition: str,
    subscales: List[int],
):
    """Save Raw NASA-TLX responses for a block.

    subscales: list of 6 integers (0-100, step 5).
    Order: Mental Demand, Physical Demand, Temporal Demand,
           Performance, Effort, Frustration.
    Raw TLX mean = average of all 6 subscales.
    """
    if len(subscales) != 6:
        raise ValueError(f"NASA-TLX requires exactly 6 subscales, got {len(subscales)}")

    raw_tlx_mean = sum(subscales) / 6.0

    conn = _get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO tlx_responses
           (participant_id, block, condition,
            mental_demand, physical_demand, temporal_demand,
            performance, effort, frustration,
            raw_tlx_mean, submitted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            participant_id, block, condition,
            *subscales,
            raw_tlx_mean,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_tlx_responses(participant_id: str) -> List[Dict[str, Any]]:
    """Get all NASA-TLX responses for a participant."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM tlx_responses WHERE participant_id = ? ORDER BY block",
        (participant_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_sus_response(
    participant_id: str,
    items: List[int],
    block: int = 0,
    condition: str = "",
):
    """Save SUS (System Usability Scale) responses.

    items: list of 10 integers (1-5 Likert scale).
    block: 1 or 2 (administered after each block).
    SUS scoring:
      - Odd items (1,3,5,7,9): contribution = response - 1
      - Even items (2,4,6,8,10): contribution = 5 - response
      - SUS score = sum of contributions * 2.5 (range 0-100)
    """
    if len(items) != 10:
        raise ValueError(f"SUS requires exactly 10 items, got {len(items)}")

    contributions = []
    for i, val in enumerate(items):
        if (i + 1) % 2 == 1:  # odd items (1,3,5,7,9)
            contributions.append(val - 1)
        else:  # even items (2,4,6,8,10)
            contributions.append(5 - val)

    sus_score = sum(contributions) * 2.5

    conn = _get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO sus_responses
           (participant_id, block, condition,
            item_1, item_2, item_3, item_4, item_5,
            item_6, item_7, item_8, item_9, item_10,
            sus_score, submitted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            participant_id,
            block,
            condition,
            *items,
            sus_score,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return sus_score


def get_sus_response(participant_id: str) -> Optional[Dict[str, Any]]:
    """Get first SUS response for a participant (backward compat)."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM sus_responses WHERE participant_id = ? ORDER BY block LIMIT 1",
        (participant_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_sus_responses(participant_id: str) -> List[Dict[str, Any]]:
    """Get all SUS responses for a participant (one per block)."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM sus_responses WHERE participant_id = ? ORDER BY block",
        (participant_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def compute_discrepancy(eval_behavioral_match: str, sandbox_all_pass: bool) -> str:
    """Compute discrepancy between user evaluation and sandbox results.

    Returns one of: agree_correct, agree_incorrect, false_positive, false_negative.
    """
    user_says_correct = eval_behavioral_match == "matches_completely"
    sandbox_correct = bool(sandbox_all_pass)

    if user_says_correct and sandbox_correct:
        return "agree_correct"
    elif user_says_correct and not sandbox_correct:
        return "false_positive"
    elif not user_says_correct and sandbox_correct:
        return "false_negative"
    else:
        return "agree_incorrect"


# ============================================================
# AUTH SESSION TOKENS (persistence across refresh, multi-tab)
# ============================================================

def create_session_token(
    participant_id: str,
    user_type: str,
    lang: str = "it",
    is_admin: bool = False,
) -> str:
    """Create a new auth session token and store it in DB.

    Each call creates a NEW token, allowing multiple tabs with
    different users in the same browser (each tab has its own URL token).
    """
    token = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    conn.execute(
        """INSERT INTO auth_sessions
           (token, participant_id, user_type, lang, is_admin, created_at, last_seen_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (token, participant_id, user_type, lang, 1 if is_admin else 0, now, now),
    )
    conn.commit()
    conn.close()
    return token


def validate_session_token(token: str) -> Optional[Dict[str, Any]]:
    """Validate a session token and return session data if valid.

    Also updates last_seen_at for activity tracking.
    Returns None if token is invalid or invalidated.
    """
    if not token:
        return None
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM auth_sessions WHERE token = ? AND invalidated = 0",
        (token,),
    ).fetchone()
    if not row:
        conn.close()
        return None
    # Update last_seen_at
    conn.execute(
        "UPDATE auth_sessions SET last_seen_at = ? WHERE token = ?",
        (datetime.now(timezone.utc).isoformat(), token),
    )
    conn.commit()

    # Also fetch participant data for full session restore
    participant_id = row["participant_id"]
    p_row = conn.execute(
        "SELECT * FROM participants WHERE participant_id = ?",
        (participant_id,),
    ).fetchone()
    conn.close()

    session_data = {
        "token": row["token"],
        "participant_id": row["participant_id"],
        "user_type": row["user_type"],
        "lang": row["lang"],
        "is_admin": bool(row["is_admin"]),
    }
    if p_row:
        session_data["condition_order"] = json.loads(p_row["condition_order"])
        session_data["counterbalance_group"] = p_row["counterbalance_group"]
        session_data["scenario_assignment"] = json.loads(p_row["scenario_assignment"])
    return session_data


def invalidate_session_token(token: str):
    """Invalidate a session token (logout)."""
    if not token:
        return
    conn = _get_conn()
    conn.execute(
        "UPDATE auth_sessions SET invalidated = 1 WHERE token = ?",
        (token,),
    )
    conn.commit()
    conn.close()


def invalidate_all_tokens(participant_id: str):
    """Invalidate all tokens for a participant (force logout everywhere)."""
    conn = _get_conn()
    conn.execute(
        "UPDATE auth_sessions SET invalidated = 1 WHERE participant_id = ?",
        (participant_id,),
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


def export_toast_csv(output_path: str = "results/toast_responses.csv"):
    """Export TOAST responses to CSV."""
    import csv
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM toast_responses").fetchall()
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


def export_tlx_csv(output_path: str = "results/tlx_responses.csv"):
    """Export NASA-TLX responses to CSV."""
    import csv
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM tlx_responses").fetchall()
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


def export_sus_csv(output_path: str = "results/sus_responses.csv"):
    """Export SUS responses to CSV."""
    import csv
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM sus_responses").fetchall()
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


def get_scenario_attempt_count(participant_id: str, scenario_code: str) -> int:
    """Return how many generation attempts were made for a scenario.

    Counts 'orchestrator_turn' events where tool_called=True (i.e. actual
    code generations, not pure conversation turns).
    """
    conn = _get_conn()
    row = conn.execute(
        """SELECT COUNT(*) FROM interactions
           WHERE participant_id = ? AND scenario_code = ? AND event = 'orchestrator_turn'
           AND json_extract(data, '$.tool_called') = 1""",
        (participant_id, scenario_code),
    ).fetchone()
    conn.close()
    return row[0] if row else 0


def get_last_generated_code(participant_id: str, scenario_code: str) -> Optional[str]:
    """Return the last generated code for a scenario, or None if not found.

    Used to restore the evaluation block after page reload.
    """
    conn = _get_conn()
    row = conn.execute(
        """SELECT data FROM interactions
           WHERE participant_id = ? AND scenario_code = ? AND event = 'orchestrator_turn'
           AND json_extract(data, '$.tool_called') = 1
           ORDER BY turn DESC LIMIT 1""",
        (participant_id, scenario_code),
    ).fetchone()
    conn.close()
    if not row:
        return None
    try:
        d = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        return d.get("code")
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None


def save_chat_snapshot(participant_id: str, scenario_code: str, chat_messages: list):
    """Save a serializable snapshot of the studio_chat to the DB.

    Stored as a single 'chat_snapshot' event (replaces previous snapshot).
    """
    conn = _get_conn()
    # Delete previous snapshot for this scenario
    conn.execute(
        "DELETE FROM interactions WHERE participant_id = ? AND scenario_code = ? AND event = 'chat_snapshot'",
        (participant_id, scenario_code),
    )
    conn.execute(
        """INSERT INTO interactions
           (participant_id, scenario_code, turn, timestamp, elapsed_s, event, data)
           VALUES (?, ?, 0, ?, 0, 'chat_snapshot', ?)""",
        (
            participant_id,
            scenario_code,
            datetime.now(timezone.utc).isoformat(),
            json.dumps(chat_messages, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()


def load_chat_snapshot(participant_id: str, scenario_code: str) -> Optional[list]:
    """Load the last chat snapshot for a scenario, or None if not found."""
    conn = _get_conn()
    row = conn.execute(
        """SELECT data FROM interactions
           WHERE participant_id = ? AND scenario_code = ? AND event = 'chat_snapshot'
           ORDER BY rowid DESC LIMIT 1""",
        (participant_id, scenario_code),
    ).fetchone()
    conn.close()
    if not row:
        return None
    try:
        return json.loads(row[0]) if isinstance(row[0], str) else row[0]
    except (json.JSONDecodeError, TypeError):
        return None


def get_full_study_summary(participant_id: str) -> Dict[str, Any]:
    """Get a complete summary of a participant's study data.

    Returns:
        dict with keys: scenarios, toast, tlx, sus, participant
    """
    conn = _get_conn()

    # Participant info
    p_row = conn.execute(
        "SELECT * FROM participants WHERE participant_id = ?",
        (participant_id,),
    ).fetchone()

    # All scenario sessions (completed or not)
    sessions = conn.execute(
        """SELECT scenario_code, condition, complexity_class, scenario_index,
                  started_at, completed_at, eval_behavioral_match, eval_confidence,
                  eval_mismatch_reason, eval_code_correct, attempt_number,
                  discrepancy_user_vs_sandbox, sandbox_all_pass
           FROM scenario_sessions
           WHERE participant_id = ?
           ORDER BY scenario_index""",
        (participant_id,),
    ).fetchall()

    # TOAST responses
    toast_rows = conn.execute(
        "SELECT * FROM toast_responses WHERE participant_id = ? ORDER BY block",
        (participant_id,),
    ).fetchall()

    # TLX responses
    tlx_rows = conn.execute(
        "SELECT * FROM tlx_responses WHERE participant_id = ? ORDER BY block",
        (participant_id,),
    ).fetchall()

    # SUS responses (one per block)
    sus_rows = conn.execute(
        "SELECT * FROM sus_responses WHERE participant_id = ? ORDER BY block",
        (participant_id,),
    ).fetchall()

    conn.close()

    return {
        "participant": dict(p_row) if p_row else {},
        "scenarios": [dict(r) for r in sessions],
        "toast": [dict(r) for r in toast_rows],
        "tlx": [dict(r) for r in tlx_rows],
        "sus": [dict(r) for r in sus_rows],
    }
