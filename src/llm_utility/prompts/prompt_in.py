from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from llm_utility.prompts.utility import InstructPromptConfig, get_trigger_def_for_row, get_action_def_for_row, \
    PROMPT_CONFIGS, get_prompt_config

# ---------------------------------------------------------------------
# Helpers to extract allow-lists from trigger/action definitions
# (riuso del tuo codice originale)
# ---------------------------------------------------------------------

_SIG_RE = re.compile(r"\(.*\)$")

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
    sk = action_def.get("skip_method")
    return _strip_signature(sk) or "skip"

# ---------------------------------------------------------------------
#Prompt per modelli INSTRUCT
# ---------------------------------------------------------------------

def _build_header_text(cfg: InstructPromptConfig) -> str:
    base = [
        "You are an expert JavaScript developer with specialized knowledge of filter code for trigger-action rules.",
        "A trigger-action rule specifies an automation in which a defined condition (the trigger) causes one or more actions to be executed."
        " Filter code is used to refine these rules by specifying the conditions under which different actions should be performed or skipped."
    ]

    usage_lines: list[str] = []

    if cfg.include_ingredients:
        usage_lines.append(
            "- Read trigger data ONLY using the available trigger states."
        )

    if cfg.include_setters:
        usage_lines.append(
            "- Change each action parameter ONLY using its provided setter method."
        )

    if cfg.include_skip_method:
        usage_lines.append(
            "- Skip the action ONLY by calling the provided skip method."
        )

    if cfg.include_time_helpers:
        usage_lines.extend(
        [
            "- For any time-based condition, you MUST use `Meta.currentUserTime` to access the current date and time.",
            "  Do NOT use `Date`, `new Date()`, or any other time source.",
            "- Treat `Meta.currentUserTime` as a Moment.js instance and use only its helper methods",
            "  (e.g. `hour()`, `minute()`, `week()`, `isoWeekday()`, `dayOfYear()`, `format(...)`).",
        ]
        )

    if usage_lines:
        base.append("Usage constraints:")
        base.extend(usage_lines)


    return "\n".join(base)

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

def build_instruct_prompt(
    row: Dict[str, Any],
    separator: str = "",
    *,
    cfg: InstructPromptConfig,
    trigger_def: Optional[Dict[str, Any]] = None,
    action_defs: Optional[List[Dict[str, Any]]] = None,
selected_ingredients=None, selected_setters=None,selected_skippers=None, selected_time_helpers=None
) -> str:

    parts: List[str] = []
    user_intent = row.get("user_intent_example") or ""
    rule_desc = row.get("rule_description") or ""

    parts.append("You are an expert JavaScript developer with specialized knowledge of filter code for trigger-action rules.")
    parts.append("A trigger-action rule specifies an automation in which a defined condition (the trigger) causes one or more actions to be executed.")
    parts.append(" Filter code is used to refine these rules by specifying the conditions under which different actions should be performed or skipped.\n")

    parts.append("Your task is to produce JavaScript filter code that modifies the rule so that it conforms to the following user intent:")
    parts.append(user_intent)
    parts.append("")

    if cfg.include_rule_description and rule_desc:
        parts.append("Given the following natural language description of a trigger-action rule:")
        parts.append(rule_desc)
        parts.append("")


    # Info catalogo trigger/action
    ingredients: List[Dict[str, Any]] = []
    setters: List[Dict[str, Any]] = []
    skippers: List[Dict[str, Any]] = []

    if trigger_def and cfg.include_ingredients:
        ingredients = extract_allowed_ingredients(trigger_def)
        if selected_ingredients is not None:
            ingredients = selected_ingredients
        parts.append(_format_ingredients_block(ingredients))

    # --- SETTERS ---
    if cfg.include_setters:
        setters_all = []
        for action_def in action_defs:
            setters_all.extend(extract_allowed_setters(action_def))

        if selected_setters is not None:
            # Usa solo quelli scelti dall’utente
            setters = selected_setters
        else:
            # Comportamento classico: tutti
            setters = setters_all

        parts.append(_format_setters_block(setters))

    # --- SKIP METHODS ---
    if cfg.include_skip_method:
        sk_all = [extract_skip_method(ad) for ad in action_defs]

        if selected_skippers is not None:
            skippers = selected_skippers
        else:
            skippers = sk_all

        parts.append(_format_skip_block(skippers))

    if selected_time_helpers:
        parts.append("You may use the following time helpers:")
        for h in selected_time_helpers:
            parts.append(f"- `Meta.currentUserTime.{h}`")

    usage_lines: list[str] = []

    if cfg.include_time_helpers:
        usage_lines.extend(
            [
                "- For any time-based condition, you MUST use `Meta.currentUserTime` to access the current date and time.",
                "  Do NOT use `Date`, `new Date()`, or any other time source.",
                "- Treat `Meta.currentUserTime` as a Moment.js instance and use only its helper methods",
                "  (e.g. `hour()`, `minute()`, `week()`, `isoWeekday()`, `dayOfYear()`, `format(...)`).",
            ]
        )

    if usage_lines:
        parts.append("\nUsage constraints:")
        parts.extend(usage_lines)
    parts.append("")
    parts.append(
        "\n"
        "Write ONLY the JavaScript Filter Code that implements the required constraints.\n"
        "Do not include any explanation, natural language, comments, JSON or other non-code elements.\n"
    )

    # Prompt finale + separatore per attaccare il codice target
    prompt_text = "\n".join(parts).strip() + separator
    return prompt_text


def build_instruct_prompt_with_profile(
    row: Dict[str, Any],
    separator: str = "",
    *,
    profile_name: str,
    trigger_def: Optional[Dict[str, Any]] = None,
    action_def: Optional[Dict[str, Any]] = None,
) -> str:

    cfg = get_prompt_config(profile_name)
    return build_instruct_prompt(
        row,
        separator=separator,
        cfg=cfg,
        trigger_def=trigger_def,
        action_def=action_def,
    )

def build_prompt_row(row,trigger_index:Any,action_index:Any,SEPARATOR='<SEP>',PROMPT_PROFILE_NAME='minimal') -> str:
    trigger_def = get_trigger_def_for_row(row, trigger_index)
    action_def = get_action_def_for_row(row, action_index)
    return build_instruct_prompt_with_profile(
        row.to_dict(),
        separator=SEPARATOR,
        profile_name=PROMPT_PROFILE_NAME,
        trigger_def=trigger_def,
        action_def=action_def,
    )


def make_prompt(row,trigger_index:Any,action_index:Any,PROMPT_CFG:Any,SEPARATOR=''):
    row_dict = row
    trigger_def = trigger_index[row["trigger_apis"][0]]
    action_defs=[]
    for action_api in row["action_apis"]:
        action_def = action_index[action_api]
        action_defs.append(action_def)
    return build_instruct_prompt(
        row_dict,
        separator=SEPARATOR,
        cfg=PROMPT_CFG,
        trigger_def=trigger_def,
        action_defs=action_defs,
    )




