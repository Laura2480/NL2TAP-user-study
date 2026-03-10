"""
Structured interaction logger for user study.

Captures every interaction with timestamps, enabling:
- Time-on-task analysis
- Iteration count per scenario
- Convergence tracking (how many turns to valid code)
- Condition A/B comparison
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


INTERACTION_LOG_PATH = Path("results/interaction_log.jsonl")
INTERACTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


class InteractionLogger:
    """Logs every user/agent interaction for a study session."""

    def __init__(
        self,
        user_id: str,
        scenario_code: str,
        condition: str = "orchestrator",  # "single_shot" or "orchestrator"
        user_type: str = "non_expert",
        log_path: Path = INTERACTION_LOG_PATH,
    ):
        self.user_id = user_id
        self.scenario_code = scenario_code
        self.condition = condition
        self.user_type = user_type
        self.log_path = log_path
        self.session_start = time.monotonic()
        self.session_start_utc = datetime.now(timezone.utc).isoformat()
        self._turn = 0

    def _base_record(self, event: str) -> Dict[str, Any]:
        elapsed = round(time.monotonic() - self.session_start, 2)
        self._turn += 1
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": elapsed,
            "turn": self._turn,
            "user_id": self.user_id,
            "scenario_code": self.scenario_code,
            "condition": self.condition,
            "user_type": self.user_type,
            "event": event,
        }

    def log_user_message(self, text: str, msg_type: str = "intent"):
        """Log a user message (intent or followup)."""
        rec = self._base_record("user_message")
        rec["msg_type"] = msg_type
        rec["text"] = text
        self._write(rec)

    def log_tool_call(
        self,
        intent_used: str,
        code: str,
        l1_syntax_ok: Optional[bool],
        l1_api_valid: Optional[bool],
        getter_coverage: Optional[float],
        setter_coverage: Optional[float],
        invalid_getters: List[str] = None,
        invalid_setters: List[str] = None,
        warnings: List[str] = None,
        outcomes_summary: List[str] = None,
    ):
        """Log a generate_and_validate tool execution."""
        rec = self._base_record("tool_call")
        rec.update({
            "intent_used": intent_used,
            "code": code,
            "l1_syntax_ok": l1_syntax_ok,
            "l1_api_valid": l1_api_valid,
            "getter_coverage": getter_coverage,
            "setter_coverage": setter_coverage,
            "invalid_getters": invalid_getters or [],
            "invalid_setters": invalid_setters or [],
            "warnings": warnings or [],
            "outcomes_summary": outcomes_summary or [],
        })
        self._write(rec)

    def log_agent_response(
        self,
        text: str,
        tool_called: bool,
        suggested_intent: str = "",
    ):
        """Log the orchestrator's response."""
        rec = self._base_record("agent_response")
        rec["text"] = text
        rec["tool_called"] = tool_called
        rec["suggested_intent"] = suggested_intent
        self._write(rec)

    def log_suggestion_accepted(self, suggested_intent: str):
        """Log when user clicks 'Use this intent'."""
        rec = self._base_record("suggestion_accepted")
        rec["suggested_intent"] = suggested_intent
        self._write(rec)

    def log_evaluation(
        self,
        correct: str,
        notes: str = "",
        final_code: str = "",
        expert_edited: bool = False,
    ):
        """Log the final evaluation for this scenario."""
        rec = self._base_record("evaluation")
        rec.update({
            "eval_correct": correct,
            "eval_notes": notes,
            "final_code": final_code,
            "expert_edited": expert_edited,
            "total_elapsed_s": round(time.monotonic() - self.session_start, 2),
            "total_turns": self._turn,
            "session_start_utc": self.session_start_utc,
        })
        self._write(rec)

    def _write(self, record: Dict[str, Any]):
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
