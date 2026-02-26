# prompt_d.py
# =============================================================================
# Costruzione prompt & body per task D (descrizione/parafrasi IF-THEN)
# Usato con OpenAI Responses API (non Batch).
# =============================================================================

from __future__ import annotations
import json
from typing import Dict, Any, List

import pandas as pd
# JSON Schema per structured outputs (D)
# JSON Schema per structured outputs (D)
SCHEMA_D: Dict[str, Any] = {

        "type": "object",
        "additionalProperties": False,
        "required": [
            "rule_description",
            "user_intent_example",
        ],
        "properties": {
            "rule_description": {
                "type": "string",
                "description": "Clear, precise natural-language description of what the rule does, including both IF condition and THEN action.",
            },
            "user_intent_example": {
                "type": "string",
                "description": "Realistic example of a user request or intent that would motivate this automation.",
            },
        },
}


DEFAULT_MODEL_D = "gpt-4o-mini"
DEFAULT_MAX_OUTPUT_TOKENS_D = 600


# prompt_d.py (solo la parte da cambiare)
def _nl_list_from_items(items: Any) -> List[str]:
    out: List[str] = []
    if not items:
        return out
    if isinstance(items, dict):
        items = [items]
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict):
                desc = it.get("description") or it.get("name") or it.get("slug") or repr(it)
                out.append(str(desc))
            else:
                out.append(str(it))
    else:
        out.append(str(items))
    return out


def build_system_D(tc: str, ac: str) -> str:

    return "\n".join([
    "You are an expert in refining and enhancing descriptions for trigger-action rules."
    "A trigger-action rule defines an automation where a specific condition (trigger) leads to an action being executed."
    "These rules can also specifying the conditions boundary (a kind of filter) under which different actions should be performed or skipped.",
    "You receive:"
    "- a noisy descriptions of the automation."
    f"- a natural-language trigger definition and a list of his variables (what the condition depends on).Trigger conditions may reference:, specific time intervals or schedules, numeric or temperature ranges, updates to a channel, account, or device, or other {tc} scenarios.\n"
    f"- a list of natural-language actions definition and a list of their properties (what the action modifies or produces).Action properties describe qualitative aspects of the action such as the message or notification that is sent, the reminder date or event creation details, what device is activated or modified, or other {ac} scenarios.\n"
    "Your tasks are:\n"
    "1) Produce a  natural-language description of what this automation does explaining both the trigger and the resulting action.\n"
    "2) Provide a user request example that express his intent in the rule usage possibly adding user specific prefenrence on when and how the rule shuld be executed that depend on the trigger variables values.\n"
    ])


def build_user_D(row: Dict[str, Any], ti: Dict[str, Any], ai: Dict[str, Any]) -> str:

    name = row.get("name") or row.get("applet_name") or ""
    desc = row.get("description")  or ""
    filter_code = row.get("filter_code") or ""

    triggers: List[str] = []
    for t_key in row.get("trigger_apis", []):
        t=ti.get(t_key)
        trigger: List[str] = []
        if t:
            trig_name= t.get("name") or ""
            trig_descr = t.get("description") or ""
            trigger.append("trigger name: "+trig_name)
            trigger.append("trigger description: "+trig_descr)
            trigger.append("trigger ingredients: ")
            trigger_ingredients = t.get("ingredients") or []
            ing_descs=[]
            for ing in trigger_ingredients:
                fck=ing.get("filter_code_key")
                if fck:
                    ing_descs.append(f"- {ing.get('name')}: {ing.get('description')}")
            ing_desc="\n".join(ing_descs)
            trigger.append(ing_desc)
        triggers.append("\n".join(trigger))

    actions: List[str] = []
    for t_key in row.get("action_apis", []):
        t = ai.get(t_key)
        action: List[str] = []
        if t:
            act_name = t.get("name") or ""
            act_descr = t.get("description") or ""
            action.append("action name: " + act_name)
            action.append("action description: " + act_descr)
            action.append("action fields: ")
            action_fields = t.get("fields") or []
            ing_descs = []
            for ing in action_fields:
                fck = ing.get("filter_code_method")
                if fck:
                    ing_descs.append(f"{ing.get('label')}")
            ing_desc = "\n".join(ing_descs)
            action.append(ing_desc)
        actions.append("\n".join(action))

    lines: List[str] = []

    if name:
        lines.append(f"applet_name={name}")
    lines.append("")

    # descrizione originale dell'applet
    if desc:
        lines.append("Noisy description of the rule:")
        lines.append(desc)
        lines.append("")

    # info strutturale
    lines.append("Trigger section:")
    lines.append("\n".join(triggers))
    lines.append("")

    lines.append("Actions section:")
    lines.append("\n".join(actions))
    lines.append("")

    # # filter code se presente
    if filter_code:
        lines.append("Filter code (JavaScript-like; describes additional IF conditions):")
        lines.append(filter_code)
        lines.append("")

    lines.append("Task:")
    lines.append("- Produce a refined description and spoken user request for this rule.")

    return "\n".join(lines)


def make_body_D_single(
    row: Dict[str, Any],
    ti:Dict[str, Any],ai:Dict[str, Any],
    model: str = DEFAULT_MODEL_D,
    feedback: str = "",
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS_D,
) -> Dict[str, Any]:

    user_text = build_user_D(row,ti,ai)
    sys_text = build_system_D(row.get('triggers_category') or "",row.get('actions_category') or "")
    if feedback:
        user_text += "\n\nValidator feedback:\n" + feedback

    body: Dict[str, Any] = {
        "model": model,
        "input": [
            {"role": "system", "content": sys_text},
            {"role": "user",   "content": user_text},
        ],
        "text": {
            "format": {
                "name": "desc",
                "strict": True,
                "type": "json_schema",
                "schema": SCHEMA_D,
            }
        },
        "max_output_tokens": max_output_tokens,
    }
    return body
