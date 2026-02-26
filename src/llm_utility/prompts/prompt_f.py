
from __future__ import annotations

import json
import re
from typing import Dict, Any, List, Optional

from llm_utility.prompts.utility import get_prompt_config, get_trigger_def_for_row, get_action_def_for_row

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------

DEFAULT_MODEL_F = "gpt-4.1-mini"      # or "gpt-4o-mini"
DEFAULT_MAX_OUTPUT_TOKENS_F = 900   # raise if outputs get truncated
SUPPORTED_JSON_SCHEMA_PREFIX = ("gpt-5", "gpt-4o", "gpt-4.1")

# ---------------------------------------------------------------------
# Structured output schema for F
# ---------------------------------------------------------------------

SCHEMA_F: Dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "code_required",
            "filter_code",
        ],
        "properties": {
            "code_required": {"type": "boolean", "description": "True if code is strictly required"},
            "filter_code": {"type": "string", "description": "JavaScript Filter Code (IFTTT)"}
        }
}

# ---------------------------------------------------------------------
# Helpers to extract allow-lists from trigger/action definitions
# ---------------------------------------------------------------------

_SIG_RE = re.compile(r"\(.*\)$")

def _format_ingredients_block(ingredients: List[Dict[str, Any]]) -> str:
    if not ingredients:
        return ""

    lines: List[str] = []
    lines.append("")
    lines.append("You must rely exclusively on the following accessors to define the trigger conditions:")
    for ing in ingredients:
        js = ing.get("js_accessor")
        desc = ing.get("description") or ""
        dtype = ing.get("type") or ""
        line = f"- JS accessor: `{js}`"
        if dtype:
            line += f" | type: {dtype}"
        if desc:
            line += f" | description: {desc}"
        lines.append(line)
    return "\n".join(lines)

def _format_time_helpers_block() -> str:
    lines: List[str] = []
    lines.append("Built-in time helpers based on `Meta.currentUserTime` (read-only):")
    lines.append(
        "- Use `Meta.currentUserTime` as the source of the current date and time "
        "in the user's timezone (it behaves like a Moment.js object)."
    )
    lines.append(
        "- Access specific components with helpers such as `hour()`, `minute()`, "
        "`date()`, `month()`, `year()`, `day()` / `isoWeekday()`, etc."
    )
    lines.append(
        "- Use `Meta.currentUserTime.format(...)` to produce formatted date/time strings."
    )
    return "\n".join(lines)

def _format_setters_block(setters: List[Dict[str, Any]]) -> str:
    if not setters:
        return ""
    lines: List[str] = []
    lines.append("")
    lines.append("The action behavior must use only the following methods:")
    for setter in setters:
        js = setter.get("js_method")
        tf = setter.get("type_family") or ""
        helper = setter.get("helper") or ""
        line = f"- JS method: `{js}`"
        if tf:
            line += f" | type family: {tf}"
        if helper:
            line += f" | helper: {helper}"
        lines.append(line)
    return "\n".join(lines)

def _format_skip_block(skip_methods: List[str]) -> str:
    lines: List[str] = []
    lines.append("")
    lines.append("If the user intent requires skipping actions, you may use:")
    for s in skip_methods:
        line = f"-`{s}`"
        lines.append(line)
    return "\n".join(lines)

def _strip_signature(m: Optional[str]) -> Optional[str]:
    if not m:
        return m
    return _SIG_RE.sub("", m)

def extract_allowed_ingredients(trigger_def: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Estrae gli ingredient del trigger in forma strutturata per il prompt.

    Ritorna una lista di dict con chiavi:
    - js_accessor: stringa JS utilizzabile nel Filter Code (ingredient.filter_code_key)
    - description: descrizione testuale (se presente)
    - type: tipo dato (se presente, da dtype)
    """
    out: List[Dict[str, Any]] = []

    for ing in (trigger_def.get("ingredients") or []):
        key = ing.get("filter_code_key")
        if not key:
            continue

        item: Dict[str, Any] = {"js_accessor": key}

        desc = ing.get("description")
        if desc:
            item["description"] = desc

        dtype = ing.get("dtype")
        if dtype:
            item["type"] = dtype

        out.append(item)

    return out

def extract_allowed_setters(action_def: Dict[str, Any]) -> List[Dict[str, Any]]:

    out: List[Dict[str, Any]] = []

    for fld in (action_def.get("fields") or []):
        method = fld.get("filter_code_method")
        if not method:
            continue

        item: Dict[str, Any] = {"js_method": method}

        helper = fld.get("helper_text") or fld.get("label")
        if helper:
            item["helper"] = helper

        out.append(item)

    # de-duplicate by js_method while preserving order
    seen = set()
    dedup: List[Dict[str, Any]] = []
    for item in out:
        m = item["js_method"]
        if m in seen:
            continue
        seen.add(m)
        dedup.append(item)

    return dedup

def extract_skip_method(action_def: Dict[str, Any]) -> str:
    """Return skip method name suitable for invocation (signature stripped)."""
    sk = action_def.get("skip_method") or "Action.skip"
    return _strip_signature(sk) or "Action.skip"


def extract_namespaces(trigger_def: Dict[str, Any], action_def: Dict[str, Any]) -> Dict[str, str]:
    trig_ns = trigger_def.get("api_endpoint_slug") or f"{trigger_def.get('service_slug','')}.{trigger_def.get('module_name','')}"
    act_ns  = action_def.get("api_endpoint_slug")  or f"{action_def.get('service_slug','')}.{action_def.get('module_name','')}"
    return {"trigger_namespace_js": trig_ns, "action_namespace_js": act_ns}

def supports_json_schema(model: str) -> bool:
    return any(model.startswith(p) for p in SUPPORTED_JSON_SCHEMA_PREFIX)

# ---------------------------------------------------------------------
# System & User builders
# ---------------------------------------------------------------------
from typing import Dict, Any

def build_system_F() -> str:
    return (
        "You are an expert JavaScript developer with specialized knowledge of filter code for trigger-action rules.\n"
        "A trigger-action rule defines an automation where a specific condition (trigger) leads to an action being executed.\n"
        "These rules can be represented in filter codes, specifying the conditions under which different actions should be performed or skipped.\n"
        "Given a user intent example in natural language, generate the corresponding JavaScript Filter Code if the user intent:\n"
        "- indicates that the action of the rule must not be executed under specific trigger conditions, implement this behavior using the skip method.\n"
        "- indicates that the action of the rule must be executed with specific parameters values.\n"
        "You receive:\n"
        "- a user intent example describing how the rule should behave in natural language;\n"
        "- a rule description explaining the purpose of the automation;\n"
        "- a list of allowed JS trigger ingredients (read only), each with a full JS accessor, description, and type;\n"
        "- a list of allowed JS action setters, each with a full JS method signature, type family, and helper text;\n"
        "- a JS method that must be called to skip the action.\n"
        "\n"
        "Your tasks are:\n"
        "1) Decide if the rule REQUIRES custom filter code to respect the user intent and the rule description.\n"
        "2) If it does, produce VALID and SAFE JavaScript filter code that enforces the constraints.\n"
        "3) If it does not, return minimal or empty filter code.\n"
        "\n"
       "Usage constraints:\n"
        "- Read trigger data ONLY using the provided ingredients via its provided JS accessor..\n"
        "- Call each action setter ONLY using its provided JS method.\n"
        "- Skip the action ONLY by calling the provided skip method.\n"
        "- For any time-based condition, you MUST use `Meta.currentUserTime` to access the current date and time. "
        "Do NOT use `Date`, `new Date()`, or any other time source.\n"
        "- Treat `Meta.currentUserTime` as a Moment.js instance and use only its documented helper methods "
        "(for example `hour()`, `minute()`, `week()`, `isoWeekday()`, `dayOfYear()`, `format(...)`).\n"
        "- Do NOT invent identifiers, methods, fields, namespaces, or modules.\n"
        "- Do NOT access global objects other than the ones explicitly given (no window, no document, no console, no network).\n"
        "\n"
        "OUTPUT FORMAT (STRICT):\n"
        "- You MUST answer with a single JSON object, and NOTHING ELSE.\n"
        "- The JSON MUST have exactly the following fields:\n"
        "  - 'code_required': boolean, true if the filter code is strictly required.\n"
        "  - 'filter_code': string, containing the JavaScript filter code;\n"
        "- If no custom filter is needed, set 'code_required' to false and still provide a string in 'filter_code' "
        "(for example a minimal no-op JS comment).\n"
    )

def build_user_F(
    row: Dict[str, Any],
    ti: list[Dict[str, Any]],
    ai: list[Dict[str, Any]]
) -> str:
    trigger_def = ti[row["trigger_apis"][0]]
    action_defs = []
    for action_api in row["action_apis"]:
        action_def = ai[action_api]
        action_defs.append(action_def)
    app_name = row.get("name") or row.get("applet_name") or ""
    rule_desc = (
        row.get("rule_description")
        or ""
    )
    user_intent = (
        row.get("user_intent_example")
        or ""
    )

    lines: list[str] = []

    lines.append("Given the following natural language description of a trigger-action rule:")
    lines.append(rule_desc)
    lines.append("")

    lines.extend(["Your task is to produce JavaScript filter code that modifies the rule so that it conforms to the following user intent:",
        f"{user_intent}",
        "- Decide whether custom JavaScript Filter Code is necessary for this rule and, if needed, generate it.",
        "- The filter code MUST complete the automation to fully implement the user intent.",
        "- If no additional constraints are needed (the plain trigger and action are already enough mark that no code is required and return minimal or empty filter code.\n"])

    # Info catalogo trigger/action
    ingredients: List[Dict[str, Any]] = []
    setters: List[Dict[str, Any]] = []
    skippers: List[Dict[str, Any]] = []

    if trigger_def:
        ingredients = extract_allowed_ingredients(trigger_def)
        lines.append(_format_ingredients_block(ingredients))
        lines.append("")

        # Built-in time helpers (Meta.currentUserTime)
    lines.extend(["Built-in time helpers (read-only, based on Meta.currentUserTime):",
                    "- JS accessor: `Meta.currentUserTime` | type: Moment | description: Current time in the user's timezone as a Moment.js instance",
                    "- JS accessor: `Meta.currentUserTime.hour()` | type: number | description: Hour of day (0–23) in the user's timezone",
                    "- JS accessor: `Meta.currentUserTime.minute()` | type: number | description: Minute of hour (0–59) in the user's timezone",
                    "- JS accessor: `Meta.currentUserTime.second()` | type: number | description: Second of minute (0–59) in the user's timezone",
                    "- JS accessor: `Meta.currentUserTime.day()` | type: number | description: Day of week (0 = Sunday, 6 = Saturday)",
                    "- JS accessor: `Meta.currentUserTime.date()` | type: number | description: Day of month (1–31)",
                    "- JS accessor: `Meta.currentUserTime.month()` | type: number | description: Month of year (0 = January, 11 = December)",
                    "- JS accessor: `Meta.currentUserTime.year()` | type: number | description: Full year (e.g., 2025)",
                    "- JS accessor: `Meta.currentUserTime.week()` | type: number | description: Week number of the year in the current locale",
                    "- JS accessor: `Meta.currentUserTime.isoWeekday()` | type: number | description: ISO day of week (1 = Monday, 7 = Sunday)",
                    "- JS accessor: `Meta.currentUserTime.dayOfYear()` | type: number | description: Day of year (1–366)",
                    "- JS accessor: `Meta.currentUserTime.format('YYYY-MM-DD HH:mm')` | type: string | description: Formatted current date and time"])

    if len(action_defs) > 0 :
        for action_def in action_defs:
            setters.extend(extract_allowed_setters(action_def))
        lines.append(_format_setters_block(setters))

    if len(action_defs) > 0:
        for action_def in action_defs:
            skippers.append(extract_skip_method(action_def))
        lines.append(_format_skip_block(skippers))
    lines.append("")


    lines.append("Important:")
    lines.extend([
        "- For any time-based condition, you MUST use `Meta.currentUserTime` to access the current date and time.",
        "  Do NOT use `Date`, `new Date()`, or any other time source.",
        "- If the user intent mentions time windows, locations, or other constraintsimplement them explicitly in the filter code, using the provided ingredients."
        "- The final answer MUST be ONLY the JSON object, with  'code_required' and 'filter_code'."
    ])

    lines.extend([
        "Output format:"
        "- You MUST return a single JSON object with exactly two fields:"
        "  - 'code_required': boolean, true if filter code is strictly required."
        "  - 'filter_code': string containing the JavaScript filter code;"
        "- The JSON MUST be valid and MUST NOT contain any extra fields or comments."
    ])
    lines.append("")

    return "\n".join(lines)

# ---------------------------------------------------------------------
# Body builder
# ---------------------------------------------------------------------

def make_body_F_single(
    row: Dict[str, Any],
    ti: Dict[str, Any], ai: Dict[str, Any],
    model: str = DEFAULT_MODEL_F,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS_F,
) -> Dict[str, Any]:

    sys_text  = build_system_F()
    user_text = build_user_F(row, ti, ai)

    body: Dict[str, Any] = {
        "model": model,
        "input": [
            {"role": "system", "content": sys_text},
            {"role": "user",   "content": user_text},
        ],
        "max_output_tokens": max_output_tokens,
        "temperature": 0,
    }
    if supports_json_schema(model):
        # Use structured outputs only if the model supports it
        body["text"] = {
            "format": {
                "name": "filter_code",
                "strict": True,
                "type": "json_schema",
                "schema": SCHEMA_F
            }
        }

    return body
