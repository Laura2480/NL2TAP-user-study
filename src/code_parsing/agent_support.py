"""
Agent Support — orchestrator agent with tool-calling for iterative code refinement.

Provides:
1. Deterministic API fix suggestions (fuzzy matching)
2. LLM diagnosis prompt builder (legacy, still used by orchestrator internally)
3. Orchestrator agent — tool-calling LLM that decides when to generate code,
   analyzes results, suggests intent improvements, and converses with the user.
"""
import difflib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from .catalog_validator import (
    load_catalog,
    get_allowed_api_surface,
    build_display_labels,
)
from .feedback import L1Report, _cached_load_catalog, _TRIGGERS_PATH, _ACTIONS_PATH


# ============================================================
# 1. DETERMINISTIC API FIX SUGGESTIONS
# ============================================================

def suggest_api_fixes(
    l1_report: L1Report,
    trigger_slugs: List[str],
    action_slugs: List[str],
    lang: str = "en",
    triggers_path: str = None,
    actions_path: str = None,
    catalog_triggers: List[dict] = None,
    catalog_actions: List[dict] = None,
) -> List[Dict[str, str]]:
    """
    Deterministic suggestions for invalid getters/setters using fuzzy matching.

    Returns list of dicts:
      {"type": "getter"|"setter"|"skip", "invalid": str, "suggestion": str, "label": str}
    """
    if not l1_report or not l1_report.api_report:
        return []

    api = l1_report.api_report
    if not api.invalid_getters and not api.invalid_setters:
        return []

    # Load catalog
    t_path = triggers_path or _TRIGGERS_PATH
    a_path = actions_path or _ACTIONS_PATH
    trigger_index, action_index = _cached_load_catalog(t_path, a_path)

    allowed_getters, allowed_setters, allowed_skips = get_allowed_api_surface(
        trigger_slugs, action_slugs, trigger_index, action_index,
    )

    # Build human-readable labels if catalog data provided
    labels = {}
    if catalog_triggers and catalog_actions:
        dl = build_display_labels(
            triggers=catalog_triggers,
            actions=catalog_actions,
            trigger_slugs=trigger_slugs,
            action_slugs=action_slugs,
            lang=lang,
        )
        labels.update(dl.get("getter_labels", {}))
        labels.update(dl.get("setter_labels", {}))

    fixes: List[Dict[str, str]] = []

    # --- Getter fixes ---
    getter_pool = sorted(allowed_getters)
    for inv in api.invalid_getters:
        matches = difflib.get_close_matches(inv, getter_pool, n=1, cutoff=0.4)
        if matches:
            best = matches[0]
            fixes.append({
                "type": "getter",
                "invalid": inv,
                "suggestion": best,
                "label": labels.get(best, best),
            })
        else:
            fixes.append({
                "type": "getter",
                "invalid": inv,
                "suggestion": "",
                "label": "",
            })

    # --- Setter fixes ---
    setter_pool = sorted(allowed_setters)
    for inv in api.invalid_setters:
        matches = difflib.get_close_matches(inv, setter_pool, n=1, cutoff=0.4)
        if matches:
            best = matches[0]
            fixes.append({
                "type": "setter",
                "invalid": inv,
                "suggestion": best,
                "label": labels.get(best, best),
            })
        else:
            fixes.append({
                "type": "setter",
                "invalid": inv,
                "suggestion": "",
                "label": "",
            })

    return fixes


# ============================================================
# 2. DIAGNOSIS PROMPT BUILDER
# ============================================================

_DIAGNOSIS_SYSTEM = """\
You are an expert IFTTT Filter Code debugger.
You receive a user intent, the actual generated code, the available API surface, \
and any factual errors detected by static analysis (invalid API calls, syntax errors).
Your job: first reason step-by-step, then state your conclusion, then provide suggestions.

KEY RULES — IFTTT Platform Semantics:
1. Skip is STICKY: if skip() is called on an action at ANY point during a single execution \
flow, that action will NOT execute, even if setters are also called on it in the same flow. \
skip() always wins over setters, regardless of call order. \
So code like: Action.skip(); Action.setX("val"); is CORRECT if the intent is to skip that action. \
And: Action.setX("val"); Action.skip(); will also result in the action being skipped.
2. Actions that are neither set nor skipped in any execution path will fire with \
default/empty values — this is almost always a bug.

IMPORTANT: All text values in the JSON (reasoning, result, suggestions) \
MUST be written in {response_lang}. Only code snippets and API identifiers stay in English.

Always respond with a single JSON object (no markdown fences) with EXACTLY this schema \
and field order — reasoning FIRST, then result, then suggestions:
{{
  "reasoning": ["step 1...", "step 2...", ...],
  "result": "overall conclusion: does the code correctly implement the intent? explain clearly",
  "suggestions": [
    {{"problem": "short description", "fix": "what to change", "corrected_api": "Correct.api.call"}},
    ...
  ],
  "intent_suggestion": "rephrased intent that would produce better code (or empty string)",
  "code_tip": "corrected JS snippet (or empty string)"
}}
"""

_DIAGNOSIS_USER = """\
## User intent
{user_intent}

## Generated Filter Code
```javascript
{code}
```

## Factual errors detected by static analysis
{problems_section}

## Available API surface for this scenario
Trigger getters: {trigger_getters}
Action setters: {action_setters}
Skip targets: {skip_targets}

Read the actual code above. For each invalid API call, explain why it's wrong and what \
the correct call should be. Consider the IFTTT platform rules (especially sticky skip) \
when reasoning about the code logic. Then suggest a rephrased intent and, if possible, \
the corrected code snippet."""


def build_diagnosis_prompt(
    user_intent: str,
    l1_report: L1Report,
    api_fixes: List[Dict[str, str]],
    scenario: Dict[str, Any],
    lang: str = "en",
    code: str = "",
) -> List[Dict[str, str]]:
    """
    Build chat messages (system + user) for LLM diagnosis.

    The agent receives the actual generated code and only factual errors
    (invalid API calls, syntax errors). It reasons about platform semantics
    (e.g. sticky skip) by reading the code itself.

    Returns list of {"role": ..., "content": ...} dicts ready for the chat API.
    """
    # Problems section — only factual API errors (no L1 path interpretations)
    problems = []
    if api_fixes:
        for fix in api_fixes:
            line = f"- Invalid {fix['type']}: `{fix['invalid']}`"
            if fix["suggestion"]:
                line += f"  (fuzzy match: `{fix['suggestion']}` — {fix['label']})"
            problems.append(line)
    if l1_report and not l1_report.syntax_ok and l1_report.parse_error:
        problems.append(f"- Syntax error: {l1_report.parse_error}")
    problems_section = "\n".join(problems) if problems else "No factual errors detected."

    # API surface
    api = l1_report.api_report if l1_report else None
    if api:
        all_getters = sorted(set(api.valid_getters) | set(api.missing_getters))
        all_setters = sorted(set(api.valid_setters) | set(api.missing_setters))
        all_skips = sorted(api.skip_available) if api.skip_available else []
    else:
        all_getters, all_setters, all_skips = [], [], []

    trigger_getters = ", ".join(f"`{g}`" for g in all_getters) or "N/A"
    action_setters = ", ".join(f"`{s}`" for s in all_setters) or "N/A"
    skip_targets = ", ".join(f"`{s}`" for s in all_skips) or "N/A"

    user_content = _DIAGNOSIS_USER.format(
        user_intent=user_intent,
        code=code,
        problems_section=problems_section,
        trigger_getters=trigger_getters,
        action_setters=action_setters,
        skip_targets=skip_targets,
    )

    response_lang = "Italian" if lang == "it" else "English"
    system_content = _DIAGNOSIS_SYSTEM.format(response_lang=response_lang)

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


# ============================================================
# 3. LLM DIAGNOSIS RUNNER
# ============================================================

@dataclass
class AgentDiagnosis:
    """Structured output from the agent diagnosis LLM call."""
    reasoning: List[str] = field(default_factory=list)
    result: str = ""
    suggestions: List[Dict[str, str]] = field(default_factory=list)
    intent_suggestion: str = ""
    code_tip: str = ""
    raw_response: str = ""
    error: Optional[str] = None

    def has_content(self) -> bool:
        return bool(self.reasoning or self.result or self.suggestions or self.intent_suggestion)


def run_agent_diagnosis(
    messages: List[Dict[str, str]],
    endpoint: str,
    model: str,
    timeout: int = 120,
) -> AgentDiagnosis:
    """
    Call local LLM for step-by-step diagnosis.

    Args:
        messages: chat messages from build_diagnosis_prompt()
        endpoint: OpenAI-compatible chat completions URL
        model: model identifier
    """
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 1024,
        "stream": False,
    }

    try:
        r = requests.post(endpoint, json=payload, timeout=timeout)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return AgentDiagnosis(error=str(e))

    return _parse_diagnosis_response(raw)


def _parse_diagnosis_response(raw: str) -> AgentDiagnosis:
    """Parse LLM diagnosis response into AgentDiagnosis."""
    data = _try_extract_json(raw)

    if data is None:
        # Fallback: treat entire response as a single reasoning step
        return AgentDiagnosis(
            reasoning=[raw.strip()],
            raw_response=raw,
        )

    reasoning = data.get("reasoning", [])
    if isinstance(reasoning, str):
        reasoning = [reasoning]

    suggestions = data.get("suggestions", [])
    if not isinstance(suggestions, list):
        suggestions = []
    # Normalize each suggestion to have at least "problem" and "fix"
    clean_suggestions = []
    for s in suggestions:
        if isinstance(s, dict):
            clean_suggestions.append({
                "problem": str(s.get("problem", "")),
                "fix": str(s.get("fix", "")),
                "corrected_api": str(s.get("corrected_api", "")),
            })
        elif isinstance(s, str):
            clean_suggestions.append({"problem": s, "fix": "", "corrected_api": ""})

    return AgentDiagnosis(
        reasoning=[str(r) for r in reasoning],
        result=str(data.get("result", "")),
        suggestions=clean_suggestions,
        intent_suggestion=str(data.get("intent_suggestion", "")),
        code_tip=str(data.get("code_tip", "")),
        raw_response=raw,
    )


def _try_extract_json(raw: str) -> Optional[dict]:
    """Try multiple strategies to extract a JSON object from LLM output."""
    # 1. Direct parse (pure JSON response)
    stripped = raw.strip()
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. Markdown code block
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass

    # 3. Scan each '{' position → try parsing to the last '}'
    last_brace = raw.rfind("}")
    if last_brace < 0:
        return None
    start = 0
    while True:
        i = raw.find("{", start)
        if i < 0 or i >= last_brace:
            break
        try:
            data = json.loads(raw[i:last_brace + 1])
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            start = i + 1

    return None


# ============================================================
# 4. AGENT FOLLOW-UP (conversational)
# ============================================================

def run_agent_followup(
    chat_history: List[Dict[str, str]],
    user_message: str,
    endpoint: str,
    model: str,
    lang: str = "en",
    timeout: int = 120,
) -> str:
    """
    Send a follow-up message to the agent, keeping the full conversation history.

    Args:
        chat_history: existing messages (system + user + assistant + ...)
        user_message: the new user message
        endpoint: OpenAI-compatible chat completions URL
        model: model identifier
        lang: response language

    Returns:
        The assistant's text reply.
    """
    messages = list(chat_history)
    response_lang = "Italian" if lang == "it" else "English"
    messages.append({
        "role": "user",
        "content": f"[Respond in {response_lang}]\n\n{user_message}",
    })

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 1024,
        "stream": False,
    }

    try:
        r = requests.post(endpoint, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Error: {e}"


# ============================================================
# 5. INTENT DIFF RENDERING
# ============================================================

def render_intent_diff_html(original: str, suggested: str) -> str:
    """
    Produce HTML highlighting word-level differences between original
    and suggested intent.

    - Removed words: red background + strikethrough
    - Added words: green background
    - Unchanged words: plain text
    """
    orig_words = original.split()
    sugg_words = suggested.split()

    sm = difflib.SequenceMatcher(None, orig_words, sugg_words)
    parts = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            parts.append(" ".join(orig_words[i1:i2]))
        elif tag == "replace":
            parts.append(
                '<span style="background:#ffcdd2;text-decoration:line-through;'
                'padding:1px 3px;border-radius:3px;">'
                + " ".join(orig_words[i1:i2]) + "</span> "
            )
            parts.append(
                '<span style="background:#c8e6c9;padding:1px 3px;'
                'border-radius:3px;font-weight:600;">'
                + " ".join(sugg_words[j1:j2]) + "</span>"
            )
        elif tag == "delete":
            parts.append(
                '<span style="background:#ffcdd2;text-decoration:line-through;'
                'padding:1px 3px;border-radius:3px;">'
                + " ".join(orig_words[i1:i2]) + "</span>"
            )
        elif tag == "insert":
            parts.append(
                '<span style="background:#c8e6c9;padding:1px 3px;'
                'border-radius:3px;font-weight:600;">'
                + " ".join(sugg_words[j1:j2]) + "</span>"
            )

    return " ".join(parts)


# ============================================================
# 6. ORCHESTRATOR — Tool-calling agent for iterative refinement
# ============================================================

ORCHESTRATOR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_and_validate",
            "description": (
                "Generate IFTTT filter code from a natural language intent "
                "and validate it against the API catalog. Returns the generated "
                "code, validation results, and behavioral analysis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": (
                            "Natural language description of the desired "
                            "IFTTT filter behavior"
                        ),
                    },
                },
                "required": ["intent"],
            },
        },
    }
]

_ORCHESTRATOR_SYSTEM = """\
You are an expert IFTTT Filter Code assistant. You help users create and refine \
JavaScript filter code for IFTTT applets through conversation.

You have ONE tool: `generate_and_validate` — it generates JavaScript filter code \
from a natural language intent and validates it against the IFTTT API catalog.

## Your behavior:

1. **When the user describes what they want the filter to do** → call \
`generate_and_validate` with their intent (pass the full intent, not a summary).
2. **After receiving results** → analyze the validation output:
   - Comment on what works and what doesn't
   - If there are API errors (invalid getters/setters), explain what went wrong
   - If the behavioral outcomes don't match the intent, explain the mismatch
   - **If you see issues, suggest an improved intent**, explaining:
     - WHAT you would change and WHY it would help
     - Write the improved intent clearly so the user can evaluate it
     - End your message with the improved intent on its own line, \
preceded by the marker `[SUGGESTED_INTENT]` and followed by `[/SUGGESTED_INTENT]`
   - If the code looks correct, say so clearly
3. **When the user asks questions, wants clarification, or discusses the code** \
→ just respond conversationally. Do NOT call the tool.
4. **When the user asks to regenerate or try a different approach** → call the tool \
with the new or refined intent.
5. **NEVER call the tool multiple times in one turn**. Always present results and \
wait for the user's decision.
6. **NEVER invent API calls**. Only reference getters/setters that appear in the \
validation results.

## IFTTT Platform Rules:
- skip() is STICKY: if called on an action, that action will NOT execute even if \
setters are also called on it in the same flow. skip() always wins.
- Actions neither set nor skipped will fire with default/empty values (usually a bug).
- Meta.currentUserTime.* is always available as a global getter.

## Available API for this scenario:
{api_surface}

## Response language:
Write ALL text in {response_lang}. Only code identifiers and API names stay in English.\
"""


@dataclass
class OrchestratorResult:
    """Result from one orchestrator turn."""
    assistant_text: str = ""
    generation_data: Optional[Dict[str, Any]] = None
    tool_called: bool = False
    intent_used: str = ""
    suggested_intent: str = ""
    updated_messages: List[Dict[str, Any]] = field(default_factory=list)


def _serialize_l1_for_orchestrator(code: str, l1) -> str:
    """Serialize code + L1 report as a readable JSON string for the orchestrator."""
    result: Dict[str, Any] = {"generated_code": code}

    if l1 is None:
        result["error"] = "Code generation failed"
        return json.dumps(result, indent=2, ensure_ascii=False)

    result["syntax_ok"] = l1.syntax_ok
    if l1.parse_error:
        result["parse_error"] = l1.parse_error

    if l1.api_report:
        api = l1.api_report
        result["api_validation"] = {
            "valid_getters": sorted(api.valid_getters),
            "invalid_getters": sorted(api.invalid_getters),
            "valid_setters": sorted(api.valid_setters),
            "invalid_setters": sorted(api.invalid_setters),
            "skip_available": sorted(api.skip_available) if api.skip_available else [],
        }

    if l1.outcomes_summary:
        result["behavior_summary"] = l1.outcomes_summary

    result["getter_coverage"] = l1.getter_coverage
    result["setter_coverage"] = l1.setter_coverage

    if l1.warnings:
        result["warnings"] = l1.warnings

    return json.dumps(result, indent=2, ensure_ascii=False)


def _extract_suggested_intent(text: str) -> Tuple[str, str]:
    """Extract [SUGGESTED_INTENT]...[/SUGGESTED_INTENT] from orchestrator response.

    Returns (clean_text, suggested_intent). If no suggestion found,
    suggested_intent is empty string.
    """
    m = re.search(
        r"\[SUGGESTED_INTENT\]\s*(.*?)\s*\[/SUGGESTED_INTENT\]",
        text, re.DOTALL,
    )
    if not m:
        return text, ""
    suggested = m.group(1).strip()
    clean = text[:m.start()].rstrip()
    return clean, suggested


def build_api_surface_text(
    trigger_slugs: List[str],
    action_slugs: List[str],
    trigger_index: dict,
    action_index: dict,
) -> str:
    """Build a human-readable API surface description for the orchestrator prompt."""
    lines = []

    # Trigger getters
    for slug in trigger_slugs:
        trig = trigger_index.get(slug)
        if not trig:
            continue
        ns = trig.get("namespace", "")
        name = trig.get("name", slug)
        lines.append(f"Trigger: {ns} ({name})")
        for ing in trig.get("ingredients", []):
            fck = ing.get("filter_code_key", "")
            if fck:
                lines.append(f"  getter: {fck}")

    # Action setters
    for slug in action_slugs:
        act = action_index.get(slug)
        if not act:
            continue
        ns = act.get("namespace", "")
        name = act.get("name", slug)
        skip_m = act.get("skip_method", f"{ns}.skip()")
        lines.append(f"Action: {ns} ({name}) — skip: {skip_m}")
        for fld in act.get("fields", []):
            m = fld.get("filter_code_method")
            if m:
                lines.append(f"  setter: {m}")

    return "\n".join(lines) if lines else "N/A"


def run_orchestrator_turn(
    history: List[Dict[str, Any]],
    user_message: str,
    tool_executor: Callable[[str], Tuple[str, Any, dict, list]],
    endpoint: str,
    model: str,
    lang: str = "en",
    api_surface_text: str = "",
    timeout: int = 180,
) -> OrchestratorResult:
    """
    Run one turn of the orchestrator agent.

    Args:
        history: previous orchestrator messages (including tool calls/results)
        user_message: new user message
        tool_executor: fn(intent) -> (code, l1_report, conditions_dict, api_fixes)
        endpoint: OpenAI-compatible chat completions URL
        model: model identifier
        lang: response language
        api_surface_text: pre-built API surface description
        timeout: request timeout in seconds

    Returns:
        OrchestratorResult with assistant text, optional generation data,
        and updated message list for context continuity.
    """
    response_lang = "Italian" if lang == "it" else "English"

    messages = list(history)
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {
            "role": "system",
            "content": _ORCHESTRATOR_SYSTEM.format(
                response_lang=response_lang,
                api_surface=api_surface_text or "N/A",
            ),
        })

    messages.append({"role": "user", "content": user_message})

    # --- First LLM call: may return text or tool_call ---
    payload = {
        "model": model,
        "messages": messages,
        "tools": ORCHESTRATOR_TOOLS,
        "temperature": 0.2,
        "max_tokens": 1500,
        "stream": False,
    }

    try:
        r = requests.post(endpoint, json=payload, timeout=timeout)
        r.raise_for_status()
        choice = r.json()["choices"][0]
    except Exception as e:
        return OrchestratorResult(
            assistant_text=f"Error: {e}",
            updated_messages=messages,
        )

    assistant_msg = choice["message"]
    messages.append(assistant_msg)

    # --- No tool call → pure conversation ---
    tool_calls = assistant_msg.get("tool_calls", [])
    if not tool_calls:
        text = assistant_msg.get("content", "")
        clean_text, suggested = _extract_suggested_intent(text)
        return OrchestratorResult(
            assistant_text=clean_text,
            tool_called=False,
            suggested_intent=suggested,
            updated_messages=messages,
        )

    # --- Tool call: execute generate_and_validate ---
    tc = tool_calls[0]
    try:
        fn_args = json.loads(tc["function"]["arguments"])
    except (json.JSONDecodeError, KeyError):
        fn_args = {}
    intent = fn_args.get("intent", user_message)

    code, l1, conditions, api_fixes = tool_executor(intent)

    # Serialize result for orchestrator
    tool_result_str = _serialize_l1_for_orchestrator(code, l1)

    messages.append({
        "role": "tool",
        "tool_call_id": tc["id"],
        "content": tool_result_str,
    })

    # --- Second LLM call: orchestrator analyzes results ---
    payload2 = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1500,
        "stream": False,
    }

    try:
        r2 = requests.post(endpoint, json=payload2, timeout=timeout)
        r2.raise_for_status()
        commentary = r2.json()["choices"][0]["message"]["content"]
    except Exception as e:
        commentary = f"Error analyzing results: {e}"

    messages.append({"role": "assistant", "content": commentary})

    clean_text, suggested = _extract_suggested_intent(commentary)

    # Build L1 HTML summary (lightweight — for the card)
    from .feedback import L1Report  # avoid circular at module level

    generation_data = {
        "code": code,
        "l1_report": l1,
        "api_fixes": api_fixes,
        "conditions": conditions,
        "intent_used": intent,
    }

    return OrchestratorResult(
        assistant_text=clean_text,
        generation_data=generation_data,
        tool_called=True,
        intent_used=intent,
        suggested_intent=suggested,
        updated_messages=messages,
    )
