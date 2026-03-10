"""
Feedback module — 2-level validation for IFTTT filter code.

L1: deterministic (syntax, API validation, semantic outcomes, coverage)
L2: LLM-based (intent matching via local endpoint)

Depends on: expr, js_validator, path_analyzer, catalog_validator, requests
"""
import functools
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from .expr import Const, _expr_to_str
from .js_validator import safe_parse_with_tail_drop
from .path_analyzer import extract_used_filter_codes_semantic
from .catalog_validator import (
    ValidationReport,
    load_catalog,
    validate_against_catalog,
    get_allowed_api_surface,
)

# ============================================================
# CATALOG PATHS
# ============================================================

import os

_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_TRIGGERS_PATH = os.path.join(_BASE, "data", "ifttt_catalog", "triggers.json")
_ACTIONS_PATH = os.path.join(_BASE, "data", "ifttt_catalog", "actions.json")


# ============================================================
# CACHED CATALOG LOADER
# ============================================================

@functools.lru_cache(maxsize=4)
def _cached_load_catalog(triggers_path: str, actions_path: str):
    return load_catalog(triggers_path, actions_path)


# ============================================================
# DATACLASSES
# ============================================================

@dataclass
class L1Report:
    syntax_ok: bool
    parse_error: Optional[str] = None
    api_report: Optional[ValidationReport] = None
    outcomes_summary: List[str] = field(default_factory=list)
    outcomes_raw: List[Dict[str, Any]] = field(default_factory=list)
    getter_coverage: float = 0.0
    setter_coverage: float = 0.0
    used_getters: List[str] = field(default_factory=list)
    used_setters: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class L2Report:
    intent_match: bool = False
    explanation: str = ""
    suggestions: List[str] = field(default_factory=list)
    raw_response: str = ""
    error: Optional[str] = None


# ============================================================
# I18N KEYWORDS
# ============================================================

_I18N = {
    "it": {
        "IF": "SE",
        "THEN": "ALLORA",
        "OTHERWISE": "ALTRIMENTI",
        "ALWAYS": "SEMPRE",
        "skip": "salta",
    },
    "en": {
        "IF": "IF",
        "THEN": "THEN",
        "OTHERWISE": "OTHERWISE",
        "ALWAYS": "ALWAYS",
        "skip": "skip",
    },
}


def _kw(lang: str, key: str) -> str:
    return _I18N.get(lang, _I18N["en"]).get(key, key)


# ============================================================
# OUTCOME -> HUMAN-READABLE TEXT
# ============================================================

def _outcome_to_text(outcome: Dict[str, Any], lang: str = "en") -> str:
    """Convert a single semantic outcome to a human-readable line."""
    cond = outcome["condition"]
    is_skip = outcome["skip"]

    # Determine condition prefix
    if isinstance(cond, Const) and cond.value is True:
        prefix = _kw(lang, "ALWAYS")
    else:
        prefix = f"{_kw(lang, 'IF')} {_expr_to_str(cond)}"

    # Build action part
    if is_skip:
        targets = outcome.get("skip_targets", [])
        target_str = ", ".join(targets) if targets else "?"
        action = f"{_kw(lang, 'skip')} {target_str}"
    else:
        setter_parts = []
        for s in outcome.get("setters", []):
            method = s["method"]
            val = s.get("value")
            if val is not None and not (isinstance(val, Const) and val.value is None):
                val_str = _expr_to_str(val)
                setter_parts.append(f"{method}({val_str})")
            else:
                setter_parts.append(method)
        action = ", ".join(setter_parts) if setter_parts else "?"

    # Combine
    if isinstance(cond, Const) and cond.value is True:
        return f"{prefix} → {action}"
    else:
        return f"{prefix} → {action}"


def _outcomes_to_summary(outcomes: List[Dict[str, Any]], lang: str = "en") -> List[str]:
    """Convert all outcomes to human-readable summary lines."""
    return [_outcome_to_text(o, lang) for o in outcomes]


def _outcome_to_dict(outcome: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize an outcome to a JSON-safe dict."""
    cond = outcome["condition"]
    return {
        "condition": _expr_to_str(cond),
        "condition_is_always": isinstance(cond, Const) and cond.value is True,
        "skip": outcome["skip"],
        "skip_targets": outcome.get("skip_targets", []),
        "setters": [
            {
                "method": s["method"],
                "value": _expr_to_str(s["value"]) if s.get("value") is not None else None,
            }
            for s in outcome.get("setters", [])
        ],
    }


# ============================================================
# L1 VALIDATION
# ============================================================

def run_l1_validation(
    code: str,
    trigger_slugs: List[str],
    action_slugs: List[str],
    lang: str = "en",
    triggers_path: str = None,
    actions_path: str = None,
) -> L1Report:
    """
    Level-1 deterministic validation: syntax, API correctness, semantic outcomes, coverage.
    """
    if triggers_path is None:
        triggers_path = _TRIGGERS_PATH
    if actions_path is None:
        actions_path = _ACTIONS_PATH

    # 1. Parse
    result = safe_parse_with_tail_drop(code)
    parsed, cleaned_code, error = result

    if parsed is None or error is not None:
        return L1Report(
            syntax_ok=False,
            parse_error=error or "parse_error",
        )

    # 2. Extract semantics
    try:
        true_getters, used_namespaces, used_setters, outcomes = (
            extract_used_filter_codes_semantic(parsed)
        )
    except Exception as e:
        return L1Report(
            syntax_ok=False,
            parse_error=f"semantic_extraction_error: {e}",
        )

    # 3. Catalog validation
    trigger_index, action_index = _cached_load_catalog(triggers_path, actions_path)

    used_skips = [
        t for o in outcomes
        if o["skip"]
        for t in o.get("skip_targets", [])
    ]

    api_report = validate_against_catalog(
        used_getters=true_getters,
        used_setters=used_setters,
        used_skips=used_skips,
        trigger_slugs=trigger_slugs,
        action_slugs=action_slugs,
        trigger_index=trigger_index,
        action_index=action_index,
    )

    # 4. Outcomes summary
    outcomes_summary = _outcomes_to_summary(outcomes, lang)
    outcomes_raw = [_outcome_to_dict(o) for o in outcomes]

    # 5. Coverage (precision: % of used methods that are valid in catalog)
    total_used_getters = len(api_report.valid_getters) + len(api_report.invalid_getters)
    total_used_setters = len(api_report.valid_setters) + len(api_report.invalid_setters)

    getter_cov = len(api_report.valid_getters) / total_used_getters if total_used_getters else 1.0
    setter_cov = len(api_report.valid_setters) / total_used_setters if total_used_setters else 1.0

    # 6. Warnings (translate catalog warnings if needed)
    if lang == "it":
        warnings = []
        for w in api_report.warnings:
            w = w.replace("Unused available getters:", "Getter disponibili non utilizzati:")
            w = w.replace("Unused available setters:", "Setter disponibili non utilizzati:")
            warnings.append(w)
    else:
        warnings = list(api_report.warnings)

    has_skip = any(o["skip"] for o in outcomes)
    has_setter = any(not o["skip"] and o["setters"] for o in outcomes)
    if has_setter and not has_skip and api_report.skip_available:
        if lang == "it":
            warnings.append("Nessun ramo skip rilevato, ma skip disponibile per: "
                            + ", ".join(api_report.skip_available))
        else:
            warnings.append("No skip branch detected, but skip available for: "
                            + ", ".join(api_report.skip_available))

    return L1Report(
        syntax_ok=True,
        api_report=api_report,
        outcomes_summary=outcomes_summary,
        outcomes_raw=outcomes_raw,
        getter_coverage=round(getter_cov, 3),
        setter_coverage=round(setter_cov, 3),
        used_getters=true_getters,
        used_setters=used_setters,
        warnings=warnings,
    )


# ============================================================
# L2 VALIDATION
# ============================================================

_L2_PROMPT_TEMPLATE = """\
You are an IFTTT automation rule judge.

IMPORTANT: Write ALL text (explanation, suggestions) in {response_lang}. \
Only code identifiers and API names stay in English.

## IFTTT Platform Rules
1. **Skip is STICKY**: if skip() is called on an action at ANY point during a single \
execution flow, that action will NOT execute, even if setters are also called on it \
in the same flow. skip() always wins over setters, regardless of call order. \
So code like: Action.skip(); Action.setX("val"); is CORRECT if the intent is to skip.
2. Actions that are neither set nor skipped will execute with default/empty values.

## User Intent
{user_intent}

## Generated Filter Code
```javascript
{code}
```

## Available API Surface
  Getters: {getters}
  Setters: {setters}
  Available skip targets: {skips}

## Task
Read the actual code above and determine if it correctly implements the user intent. \
Consider the IFTTT platform rules (especially sticky skip). \
Check that conditions, getter usage, setter calls, and skip logic are all correct.

Respond in JSON: {{"intent_match": true/false, "explanation": "...", "suggestions": [...]}}
"""


def _parse_l2_response(raw: str) -> dict:
    """Parse LLM response, trying JSON first, then regex fallback."""
    # Try direct JSON parse
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try extracting JSON from markdown code block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, TypeError):
            pass

    # Try finding any JSON object in the text
    m = re.search(r"\{[^{}]*\"intent_match\"[^{}]*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback
    return {"intent_match": False, "explanation": raw, "suggestions": []}


def run_l2_validation(
    user_intent: str,
    l1_report: L1Report,
    code: str = "",
    endpoint: str = "http://localhost:1234/api/v0/chat/completions",
    model: str = "ft_2_deepseek_merged",
    lang: str = "en",
    timeout: int = 120,
) -> L2Report:
    """
    Level-2 LLM-based validation: checks if code behavior matches user intent.
    The LLM receives the actual generated code and IFTTT platform rules.
    """
    if not l1_report.syntax_ok:
        return L2Report(
            intent_match=False,
            explanation="Cannot verify: code has syntax errors.",
            error="l1_syntax_error",
        )

    getters_str = str(l1_report.used_getters) if l1_report.used_getters else "[]"
    setters_str = str(l1_report.used_setters) if l1_report.used_setters else "[]"

    skips_str = str(l1_report.api_report.skip_available) if l1_report.api_report and l1_report.api_report.skip_available else "[]"

    response_lang = "Italian" if lang == "it" else "English"
    prompt = _L2_PROMPT_TEMPLATE.format(
        user_intent=user_intent,
        getters=getters_str,
        setters=setters_str,
        skips=skips_str,
        response_lang=response_lang,
        code=code,
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 512,
        "stream": False,
    }

    try:
        r = requests.post(endpoint, json=payload, timeout=timeout)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return L2Report(error=str(e), raw_response="")

    parsed = _parse_l2_response(raw)

    intent_match = bool(parsed.get("intent_match", False))

    return L2Report(
        intent_match=intent_match,
        explanation=str(parsed.get("explanation", "")),
        suggestions=list(parsed.get("suggestions", [])),
        raw_response=raw,
    )


# ============================================================
# CONVENIENCE FUNCTION
# ============================================================

def validate_filter_code(
    code: str,
    intent: str,
    trigger_slugs: List[str],
    action_slugs: List[str],
    run_l2: bool = True,
    lang: str = "en",
    endpoint: str = "http://localhost:1234/api/v0/chat/completions",
    model: str = "ft_2_deepseek_merged",
    triggers_path: str = None,
    actions_path: str = None,
) -> Tuple[L1Report, Optional[L2Report]]:
    """
    Convenience: run L1, then optionally L2 if syntax_ok and run_l2=True.
    """
    l1 = run_l1_validation(
        code, trigger_slugs, action_slugs,
        lang=lang,
        triggers_path=triggers_path,
        actions_path=actions_path,
    )

    l2 = None
    if l1.syntax_ok and run_l2:
        l2 = run_l2_validation(
            user_intent=intent,
            l1_report=l1,
            code=code,
            endpoint=endpoint,
            model=model,
            lang=lang,
        )

    return l1, l2
