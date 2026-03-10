# pages/2_Studio.py — Pagina unica: sidebar (contesto + selezione) + main (workflow)

# --- Minimal imports: streamlit FIRST, then page config + loading banner ---
import os, sys
import streamlit as st

st.set_page_config(
    page_title="Studio",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS + loading banner — rendered BEFORE heavy imports
st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none; }
[data-testid="stSidebarCollapseButton"] { display: none; }
[data-testid="stSidebarCollapsedControl"] { display: none; }
[data-testid="stSidebar"] { min-width: 420px; max-width: 520px; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.4rem; }
</style>
""", unsafe_allow_html=True)

_needs_loading = not st.session_state.get("_studio_initialized", False)
_loading_banner = st.empty()
if _needs_loading:
    _loading_msg = (
        "Caricamento in corso"
        if st.session_state.get("lang", "it") == "it"
        else "Loading"
    )
    _loading_banner.markdown(
        f"<div style='text-align:center; padding:6rem 0;'>"
        f"<h2 style='color:#555;'>{_loading_msg}</h2>"
        "<div style='margin:2rem auto; width:40px; height:40px; "
        "border:4px solid #eee; border-top:4px solid #555; "
        "border-radius:50%; animation:spin 1s linear infinite;'></div>"
        "<style>@keyframes spin{to{transform:rotate(360deg)}}</style>"
        "</div>",
        unsafe_allow_html=True,
    )

# --- Heavy imports AFTER banner is visible ---
import re, json, time
from datetime import datetime
from pathlib import Path

import requests
import streamlit.components.v1 as components

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from code_editor import code_editor
from utils.study_utils import STUDY
from code_parsing.feedback import run_l1_validation, L1Report
from code_parsing.flowchart import render_flowchart_html, render_code_flowchart_html
from code_parsing.catalog_validator import build_display_labels
from code_parsing.agent_support import (
    suggest_api_fixes, render_intent_diff_html,
    run_orchestrator_turn, build_api_surface_text,
)
from code_parsing.execution_sandbox import (
    execute_filter_code, build_default_fixtures, run_test_suite,
)
from utils.interaction_logger import InteractionLogger
from utils.session_manager import (
    start_scenario_session, complete_scenario_session,
    log_interaction as db_log_interaction, get_participant_progress,
)

# --- Model serving endpoints (vLLM, one model per GPU) ---
GEN_ENDPOINT = "http://localhost:8001/v1/chat/completions"
ORC_ENDPOINT = "http://localhost:8002/v1/chat/completions"
GENERATION_MODEL = "ft_2_qwen_merged"
ORCHESTRATOR_MODEL = "qwen3-4b-2507"

RESULTS_PATH = Path("results/user_study_results.jsonl")
RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

# ============================================================
# SESSION CHECK
# ============================================================

user_id = st.session_state.get("user_id", "").strip()
if not user_id:
    st.switch_page("Home.py")

user_type = st.session_state.get("user_type", "non_expert")
lang = st.session_state.get("lang", "it")

# Study assignment (from session_manager via Home.py)
_scenario_assignment = st.session_state.get("scenario_assignment", [])
_condition_order = st.session_state.get("condition_order", ["orchestrator"])

# ============================================================
# I18N HELPER
# ============================================================

def T(obj: dict, key: str) -> str:
    if not obj:
        return ""
    if lang == "en":
        return obj.get(f"{key}_en") or obj.get(f"{key}_it", "")
    return obj.get(f"{key}_it") or obj.get(f"{key}_en", "")

_UI = {
    "it": {
        "services": "Servizi",
        "trigger_ing": "Trigger — Ingredient",
        "action_setter": "Action — Setter",
        "select_all": "Seleziona tutto",
        "deselect": "Deseleziona",
        "blockable_actions": "Azioni bloccabili",
        "blockable": "bloccabile",
        "context": "Contesto",
        "intent_examples": "Esempi di intent",
        "agent_model": "Modello assistente",
        "describe_rule": "Descrivi la regola",
        "generate": "Genera Filter Code",
        "insert_desc": "Inserisci una descrizione della regola.",
        "prompt_sent": "Prompt inviato all'LLM",
        "generating": "Generazione in corso...",
        "llm_error": "Errore LLM",
        "results": "Risultati",
        "gen_code": "Codice generato",
        "conditions": "Condizioni",
        "no_code": "// Nessun output",
        "flowchart_na": "Flowchart non disponibile.",
        "na": "Non disponibile.",
        "auto_analysis": "Analisi automatica",
        "empty_gen": "Generazione vuota — analisi non disponibile.",
        "syntax_err": "Errore di sintassi",
        "valid_s": "valido", "valid_p": "validi",
        "invalid_s": "invalido", "invalid_p": "invalidi",
        "api_ok": "Sintassi e API valide",
        "api_err": "Problemi API rilevati",
        "of_available": "su {n} disponibili",
        "error_details": "Dettagli errori",
        "invalid_getters": "Getter invalidi",
        "invalid_setters": "Setter invalidi",
        "invalid_skips": "Skip invalidi",
        "semantic_verify": "Verifica semantica con LLM",
        "verify_btn": "Verifica corrispondenza con l'intento",
        "verifying": "Verifica semantica in corso...",
        "l2_error": "Errore L2",
        "l2_ok": "Il codice implementa correttamente l'intento",
        "l2_warn": "Il codice potrebbe non corrispondere all'intento",
        "l2_suggestions": "Suggerimenti",
        "l2_na": "Verifica semantica non disponibile (richiede sintassi valida).",
        "evaluation": "Valutazione",
        "expert_correction": "Correzione (Expert)",
        "applied": "Codice modificato applicato.",
        "not_applied": "Nessuna modifica: verrà valutato il codice generato.",
        "correction_result": "Esito della correzione",
        "claim_fixed_q": "Ritieni di aver corretto correttamente il codice?",
        "not_required": "non richiesto",
        "claim_fixed_locked": (
            "Non risulta una correzione diversa dal codice generato: "
            'esito impostato su "non richiesto".'
        ),
        "gave_up": "Non riesco a correggere",
        "correct_q": "Il Filter Code finale è corretto?",
        "eval_notes": "Note valutatore",
        "save_eval": "Salva valutazione",
        "analysis": "Analisi",
        "agent_panel": "Assistente",
        "agent_fixes": "Suggerimenti API",
        "agent_analyze": "Analisi approfondita",
        "agent_analyzing": "Analisi in corso...",
        "agent_try": "Prova a riformulare",
        "agent_use_suggestion": "Usa questo intent",
        "agent_no_issues": "Nessun problema rilevato",
        "agent_reasoning": "Ragionamento",
        "agent_result": "Risultato",
        "agent_suggestions": "Suggerimenti",
        "agent_chat": "Chiedi all'assistente",
        "agent_chat_placeholder": "Scrivi una domanda o considerazione...",
        "agent_chat_send": "Invia",
        "agent_chat_thinking": "L'assistente sta rispondendo...",
        "chat_input_placeholder": "Scrivi l'intent o una domanda...",
        "btn_regenerate": "Rigenera codice",
        "btn_regen_tooltip": "Attiva per rigenerare il codice al prossimo invio",
        "regen_rewrite_prompt": "Riscrivi questo intent incorporando le seguenti correzioni/indicazioni dell'utente. Restituisci SOLO il nuovo intent riformulato, senza spiegazioni.",
        "regen_proposal": "Intent riformulato",
        "regen_confirm": "Genera con questo intent",
        "regen_edit": "Modifica",
        "chat_code_header": "Codice generato",
        "chat_generating": "Generazione e analisi in corso...",
        "chat_empty": "Customizza la tua automazione",
        "condition_label": "Condizione",
        "condition_a": "A — Singola generazione",
        "condition_b": "B — Assistente iterativo",
        "single_shot_hint": "In questa condizione puoi generare il codice una sola volta. Scrivi il tuo intent e premi Invia.",
    },
    "en": {
        "services": "Services",
        "trigger_ing": "Trigger — Ingredient",
        "action_setter": "Action — Setter",
        "select_all": "Select all",
        "deselect": "Deselect",
        "blockable_actions": "Blockable actions",
        "blockable": "blockable",
        "context": "Context",
        "intent_examples": "Intent examples",
        "agent_model": "Assistant model",
        "describe_rule": "Describe the rule",
        "generate": "Generate Filter Code",
        "insert_desc": "Please enter a rule description.",
        "prompt_sent": "Prompt sent to LLM",
        "generating": "Generating...",
        "llm_error": "LLM Error",
        "results": "Results",
        "gen_code": "Generated code",
        "conditions": "Conditions",
        "no_code": "// No output",
        "flowchart_na": "Flowchart not available.",
        "na": "Not available.",
        "auto_analysis": "Automatic analysis",
        "empty_gen": "Empty generation — analysis not available.",
        "syntax_err": "Syntax error",
        "valid_s": "valid", "valid_p": "valid",
        "invalid_s": "invalid", "invalid_p": "invalid",
        "api_ok": "Syntax and API valid",
        "api_err": "API issues detected",
        "of_available": "of {n} available",
        "error_details": "Error details",
        "invalid_getters": "Invalid getters",
        "invalid_setters": "Invalid setters",
        "invalid_skips": "Invalid skips",
        "semantic_verify": "Semantic verification with LLM",
        "verify_btn": "Verify intent match",
        "verifying": "Semantic verification in progress...",
        "l2_error": "L2 Error",
        "l2_ok": "The code correctly implements the intent",
        "l2_warn": "The code may not match the intent",
        "l2_suggestions": "Suggestions",
        "l2_na": "Semantic verification not available (requires valid syntax).",
        "evaluation": "Evaluation",
        "expert_correction": "Correction (Expert)",
        "applied": "Modified code applied.",
        "not_applied": "No changes: the generated code will be evaluated.",
        "correction_result": "Correction result",
        "claim_fixed_q": "Do you think you correctly fixed the code?",
        "not_required": "not required",
        "claim_fixed_locked": (
            "No correction differs from the generated code: "
            'result set to "not required".'
        ),
        "gave_up": "I cannot fix it",
        "correct_q": "Is the final Filter Code correct?",
        "eval_notes": "Evaluator notes",
        "save_eval": "Save evaluation",
        "analysis": "Analysis",
        "agent_panel": "Assistant",
        "agent_fixes": "API suggestions",
        "agent_analyze": "Deep analysis",
        "agent_analyzing": "Analyzing...",
        "agent_try": "Try rephrasing",
        "agent_use_suggestion": "Use this intent",
        "agent_no_issues": "No issues detected",
        "agent_reasoning": "Reasoning",
        "agent_result": "Result",
        "agent_suggestions": "Suggestions",
        "agent_chat": "Ask the assistant",
        "agent_chat_placeholder": "Write a question or comment...",
        "agent_chat_send": "Send",
        "agent_chat_thinking": "The assistant is responding...",
        "chat_input_placeholder": "Write the intent or a question...",
        "btn_regenerate": "Regenerate code",
        "btn_regen_tooltip": "Enable to regenerate code on next send",
        "regen_rewrite_prompt": "Rewrite this intent incorporating the following user corrections/directions. Return ONLY the reformulated intent, no explanations.",
        "regen_proposal": "Reformulated intent",
        "regen_confirm": "Generate with this intent",
        "regen_edit": "Edit",
        "chat_code_header": "Generated code",
        "chat_generating": "Generating and analyzing...",
        "chat_empty": "Customize your automation",
        "condition_label": "Condition",
        "condition_a": "A — Single generation",
        "condition_b": "B — Iterative assistant",
        "single_shot_hint": "In this condition you can generate the code only once. Write your intent and press Send.",
    },
}

def U(key: str) -> str:
    """UI label translation."""
    return _UI.get(lang, _UI["en"]).get(key, key)

# ============================================================
# SCENARIO LIST
# ============================================================

SCENARIOS = STUDY["non_expert"] if user_type == "non_expert" else STUDY["expert"]
num_scenarios = len(SCENARIOS)

if "scenario_index" not in st.session_state:
    st.session_state["scenario_index"] = 0

# Handle resume from failed evaluation
if st.session_state.get("resume_from_eval"):
    forced = st.session_state.get("forced_scenario")
    if forced:
        for i, s in enumerate(SCENARIOS):
            if s["code"] == forced:
                st.session_state["scenario_index"] = i
                break
    st.session_state["resume_from_eval"] = False

# ============================================================
# UTILS
# ============================================================

def strip_llm_markdown(code: str) -> str:
    if not code:
        return ""
    code = code.strip()
    if code.startswith("```"):
        code = re.sub(r"^```[a-zA-Z]*\n?", "", code)
        code = re.sub(r"\n?```$", "", code)
    return code.strip()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown(f"**User:** `{user_id}` | **{user_type}**")

    # ---- a) Scenario selector ----
    raw_idx = st.session_state.get("scenario_index", 0)
    safe_idx = max(0, min(raw_idx, num_scenarios - 1))

    labels = [f"{sc['code']} — {T(sc, 'title')}" for sc in SCENARIOS]

    idx = st.selectbox(
        "Scenario",
        options=list(range(num_scenarios)),
        format_func=lambda i: labels[i],
        index=safe_idx,
    )

    # Reset generation state on scenario change
    if idx != st.session_state.get("scenario_index"):
        st.session_state["scenario_index"] = idx
        for k in ("studio_chat", "orchestrator_messages",
                   "latest_code", "latest_l1", "latest_l2",
                   "attempt_count", "attempt_log"):
            st.session_state.pop(k, None)
        st.rerun()

    st.session_state["scenario_index"] = idx
    SC = SCENARIOS[idx]

    # ---- Determine study condition for this scenario ----
    _current_condition = "orchestrator"  # default fallback
    for _asn in _scenario_assignment:
        if _asn.get("scenario_code") == SC["code"]:
            _current_condition = _asn.get("condition", "orchestrator")
            break
    ss_cond_key = "study_condition"
    st.session_state[ss_cond_key] = _current_condition

    # Show condition badge in sidebar
    _cond_label = U("condition_a") if _current_condition == "single_shot" else U("condition_b")
    st.markdown(
        f'<div style="background:{"#e3f2fd" if _current_condition == "single_shot" else "#f3e5f5"};'
        f'padding:6px 12px;border-radius:8px;text-align:center;font-weight:600;'
        f'margin:4px 0;">'
        f'{U("condition_label")}: {_cond_label}</div>',
        unsafe_allow_html=True,
    )

    # ---- b) Catalog (pre-enriched, no runtime translation needed) ----
    CAT = SC.get("catalog", {}).get(lang) or SC.get("catalog", {}).get("en", {})

    SERVICE_INDEX = {s["service_slug"]: s for s in CAT.get("services", [])}
    TRIGGER_INDEX = {t["api_endpoint_slug"]: t for t in CAT.get("triggers", [])}
    ACTION_INDEX  = {a["api_endpoint_slug"]: a for a in CAT.get("actions", [])}

    # ---- c) Servizi coinvolti ----
    st.markdown("---")
    st.markdown(f"#### {U('services')}")
    svc_cols = st.columns(min(len(SC["services"]), 4))
    for col, slug in zip(svc_cols, SC["services"]):
        svc = SERVICE_INDEX.get(slug)
        with col:
            if not svc:
                st.warning(f"'{slug}' ?")
                continue
            st.image(svc["image_url"], width=56)
            st.caption(svc["name"])

    # ---- Context + IF-THEN ----
    st.markdown("---")
    st.markdown(f"#### {U('context')}")
    st.write(T(SC, "background"))

    if_then = T(SC, "if_then")
    if if_then:
        st.info(if_then)

    # ---- Intent examples ----
    examples = SC.get("intent_examples_it" if lang == "it" else "intent_examples_en", [])
    if not examples:
        examples = SC.get("intent_examples_it", [])
    if examples:
        st.markdown(f"#### {U('intent_examples')}")
        for ex in examples:
            st.markdown(f"- {ex}")

    # ---- d) Trigger + Ingredient selection ----
    st.markdown("---")
    st.markdown(f"#### {U('trigger_ing')}")

    st.session_state.setdefault("selected_ingredients", {})
    sel_ing = st.session_state["selected_ingredients"].setdefault(SC["code"], set())

    # Collect all available ingredient keys for "Select All"
    _all_ing_keys = []
    for trig_api in SC["trigger_apis"]:
        trig = TRIGGER_INDEX.get(trig_api)
        if trig:
            for ing in trig.get("ingredients", []):
                fck = ing.get("filter_code_key", "")
                if fck:
                    _all_ing_keys.append(fck)

    col_sa, col_da = st.columns(2)
    if col_sa.button(U("select_all"), key=f"sel_all_ing_{SC['code']}"):
        for fck in _all_ing_keys:
            st.session_state[f"ing_{SC['code']}_{fck}"] = True
        sel_ing.update(_all_ing_keys)
        st.rerun()
    if col_da.button(U("deselect"), key=f"desel_ing_{SC['code']}"):
        for fck in _all_ing_keys:
            st.session_state[f"ing_{SC['code']}_{fck}"] = False
        sel_ing.clear()
        st.rerun()

    for trig_api in SC["trigger_apis"]:
        trig = TRIGGER_INDEX.get(trig_api)
        if not trig:
            continue
        st.markdown(f"**{trig['name']}**")
        if trig.get("description"):
            st.caption(trig["description"])

        ingredients = trig.get("ingredients", [])
        if ingredients:
            for ing in ingredients:
                fck = ing.get("filter_code_key", "")
                if not fck:
                    continue
                ing_name = ing.get("name", fck)
                ing_desc = ing.get("description", "")
                if user_type == "expert":
                    lbl = ing_name
                    tip = ing_desc or None
                else:
                    lbl = ing_name
                    tip = ing_desc or None
                ss_key = f"ing_{SC['code']}_{fck}"
                if ss_key not in st.session_state:
                    st.session_state[ss_key] = fck in sel_ing
                checked = st.checkbox(
                    lbl,
                    key=ss_key,
                    help=tip,
                )
                if user_type == "expert":
                    st.caption(f"`{fck}`")
                if checked:
                    sel_ing.add(fck)
                else:
                    sel_ing.discard(fck)

    # ---- e) Action + Setter/Field selection ----
    st.markdown("---")
    st.markdown(f"#### {U('action_setter')}")

    st.session_state.setdefault("selected_setters", {})
    sel_set = st.session_state["selected_setters"].setdefault(SC["code"], set())

    # Collect all available setter methods for "Select All"
    _all_set_methods = []
    for act_api in SC["action_apis"]:
        act = ACTION_INDEX.get(act_api)
        if act:
            ns = act.get("namespace", "")
            for fld in act.get("fields", []):
                method = fld.get("filter_code_method")
                if method:
                    _all_set_methods.append(re.sub(r'\(.*\)', '()', method))
                elif fld.get("slug") and ns:
                    s = fld["slug"]
                    _all_set_methods.append(f"{ns}.set{s[0].upper()}{s[1:]}()")

    col_sa2, col_da2 = st.columns(2)
    if col_sa2.button(U("select_all"), key=f"sel_all_set_{SC['code']}"):
        for m in _all_set_methods:
            st.session_state[f"set_{SC['code']}_{m}"] = True
        sel_set.update(_all_set_methods)
        st.rerun()
    if col_da2.button(U("deselect"), key=f"desel_set_{SC['code']}"):
        for m in _all_set_methods:
            st.session_state[f"set_{SC['code']}_{m}"] = False
        sel_set.clear()
        st.rerun()

    for act_api in SC["action_apis"]:
        act = ACTION_INDEX.get(act_api)
        if not act:
            continue
        st.markdown(f"**{act['name']}**")
        if act.get("description"):
            st.caption(act["description"])

        ns = act.get("namespace", "")
        fields = act.get("fields", [])
        for fld in fields:
            method = fld.get("filter_code_method")
            if method:
                clean_method = re.sub(r'\(.*\)', '()', method)
            elif fld.get("slug") and ns:
                # Derived setter: Namespace.setSlug()
                s = fld["slug"]
                clean_method = f"{ns}.set{s[0].upper()}{s[1:]}()"
            else:
                continue
            fld_label = fld.get("label", fld.get("slug", clean_method))
            fld_help = fld.get("helper_text", "")
            if user_type == "expert":
                lbl = fld_label
                tip = fld_help or None
            else:
                lbl = fld_label
                tip = fld_help or None
            ss_key = f"set_{SC['code']}_{clean_method}"
            if ss_key not in st.session_state:
                st.session_state[ss_key] = clean_method in sel_set
            checked = st.checkbox(
                lbl,
                key=ss_key,
                help=tip,
            )
            if user_type == "expert":
                st.caption(f"`{clean_method}`")
            if checked:
                sel_set.add(clean_method)
            else:
                sel_set.discard(clean_method)

    # ---- f) Skip targets ----
    _skip_targets = []
    for act_api in SC["action_apis"]:
        act = ACTION_INDEX.get(act_api)
        if not act:
            continue
        ns = act.get("namespace", "")
        name = act.get("name", ns)
        skip_method = act.get("skip_method", "")
        skip_call = re.sub(r'\(.*\)', '()', skip_method) if skip_method else f"{ns}.skip()"
        if ns:
            _skip_targets.append((ns, name, skip_call))

    if _skip_targets:
        st.markdown("---")
        st.markdown(f"#### {U('blockable_actions')}")
        for ns, name, skip_call in _skip_targets:
            if user_type == "expert":
                st.markdown(f"- **{name}** — `{skip_call}`")
            else:
                st.markdown(f"- **{name}** — {U('blockable')}")

    # (model selection removed — endpoints are fixed per vLLM server)


# ============================================================
# MAIN — Header
# ============================================================

_loading_banner.empty()
st.session_state["_studio_initialized"] = True

# Start scenario session in DB (idempotent — INSERT OR REPLACE)
_current_condition = st.session_state.get("study_condition", "orchestrator")
start_scenario_session(
    participant_id=user_id,
    scenario_code=SC["code"],
    condition=_current_condition,
    complexity_class=SC.get("complexity_tag", ""),
    scenario_index=st.session_state.get("scenario_index", 0),
)

st.title(f"{SC['code']} — {T(SC, 'title')}")

# Show single-shot hint if condition A
if _current_condition == "single_shot":
    st.info(U("single_shot_hint"))

# ============================================================
# HELPERS — chat rendering & prompt building
# ============================================================

ss = st.session_state
ss.setdefault("studio_chat", [])
ss.setdefault("orchestrator_messages", [])


def _get_logger() -> InteractionLogger:
    """Get or create the interaction logger for the current scenario."""
    key = f"_logger_{ss.get('scenario_index', 0)}"
    if key not in ss:
        ss[key] = InteractionLogger(
            user_id=user_id,
            scenario_code=SC.get("code", "unknown"),
            condition=ss.get("study_condition", "orchestrator"),
            user_type=user_type,
        )
    return ss[key]


def _build_prompt(intent_text: str) -> str:
    """Build generation prompt from intent + sidebar selections."""
    p = [
        "You are an expert JavaScript developer with knowledge of IFTTT Filter Code.",
        "Generate JavaScript Filter Code for the following intent:\n",
        intent_text + "\n",
    ]

    trigger_lines = []
    for trig_api in SC["trigger_apis"]:
        trig = TRIGGER_INDEX.get(trig_api)
        if not trig:
            continue
        trig_ns = trig.get("namespace", "")
        trig_name = trig.get("name", trig_api)
        if trig_ns:
            trigger_lines.append(f"- `{trig_ns}` — {trig_name}")

    if trigger_lines:
        p.append("Available trigger:")
        p.extend(trigger_lines)

    if sel_ing:
        p.append("\nUse ONLY these accessors:")
        for g in sorted(sel_ing):
            p.append(f"- `{g}`")

    action_lines = []
    all_setters = []
    for act_api in SC["action_apis"]:
        act = ACTION_INDEX.get(act_api)
        if not act:
            continue
        ns = act.get("namespace", "")
        if not ns:
            continue
        skip_method = act.get("skip_method", "")
        skip_call = re.sub(r'\(.*\)', '()', skip_method) if skip_method else f"{ns}.skip()"
        action_lines.append(f"- `{ns}` (skip: `{skip_call}`)")
        for fld in act.get("fields", []):
            m = fld.get("filter_code_method")
            if m:
                all_setters.append(re.sub(r'\(.*\)', '()', m))
            elif fld.get("slug") and ns:
                s = fld["slug"]
                all_setters.append(f"{ns}.set{s[0].upper()}{s[1:]}()")

    if action_lines:
        p.append("\nAvailable actions:")
        p.extend(action_lines)

    if sel_set:
        p.append("\nUse ONLY these setter methods:")
        for s in sorted(sel_set):
            p.append(f"- `{s}`")
    elif all_setters:
        p.append("\nAvailable setter methods:")
        for s in all_setters:
            p.append(f"- `{s}`")

    p.append("\nGlobal time API (always available regardless of trigger):")
    p.append("- `Meta.currentUserTime` — returns the user's current local time as a Date object")
    p.append("- Use `.hour()`, `.minute()`, `.format('HH:mm')` etc. to extract time components")
    p.append("- Example: `var hour = Meta.currentUserTime.hour();`")
    p.append("- NOTE: Do NOT confuse this with trigger-specific time data (e.g. `DateAndTime.everyHourAt.CheckTime`). "
             "Trigger accessors provide the trigger's own time/data fields. "
             "`Meta.currentUserTime` is a global API for the user's real-time clock, "
             "useful for time-range conditions like 'between 9am and 6pm'.")

    p.append("\nWrite ONLY the JavaScript Filter Code. No explanations.")
    return "\n".join(p)


def _build_l1_card_html(l1: L1Report) -> str:
    """Pre-render L1 validation card as HTML string."""
    if l1 is None:
        return ""
    if not l1.syntax_ok:
        return (
            f'<div style="background:#ffebee;color:#c62828;padding:8px 16px;'
            f'border-radius:8px;font-weight:600;margin:8px 0;">'
            f'&#10007;&ensp;{U("syntax_err")}: {l1.parse_error}</div>'
        )

    api = l1.api_report
    n_valid_g = len(api.valid_getters) if api else 0
    n_invalid_g = len(api.invalid_getters) if api else 0
    n_valid_s = len(api.valid_setters) if api else 0
    n_invalid_s = len(api.invalid_setters) if api else 0

    skip_used_set = set(api.skip_used) if api and api.skip_used else set()
    skip_avail_set = set(api.skip_available) if api and api.skip_available else set()
    valid_skips = sorted(skip_used_set & skip_avail_set)
    invalid_skips = sorted(skip_used_set - skip_avail_set)
    n_valid_skip = len(valid_skips)
    n_invalid_skip = len(invalid_skips)
    n_skip_avail = len(skip_avail_set)

    has_errors = n_invalid_g > 0 or n_invalid_s > 0 or n_invalid_skip > 0

    def _pill(n, label_s, label_p, ok):
        c = "#2e7d32" if ok else "#c62828"
        bg = "#e8f5e9" if ok else "#ffebee"
        ico = "&#10003;" if ok else "&#10007;"
        lbl = label_s if n == 1 else label_p
        return (
            f'<span style="display:inline-block;background:{bg};color:{c};'
            f'padding:2px 10px;border-radius:12px;font-size:0.85em;'
            f'font-weight:600;margin:2px 4px;">'
            f'{ico}&nbsp;{n} {lbl}</span>'
        )

    def _row(cat, n_ok, n_ko, note=""):
        cells = _pill(n_ok, U("valid_s"), U("valid_p"), True)
        if n_ko > 0:
            cells += _pill(n_ko, U("invalid_s"), U("invalid_p"), False)
        if note:
            cells += (
                f'<span style="color:#9e9e9e;font-size:0.8em;'
                f'margin-left:6px;">{note}</span>'
            )
        return (
            f'<tr>'
            f'<td style="padding:6px 14px;font-weight:600;'
            f'white-space:nowrap;">{cat}</td>'
            f'<td style="padding:6px 8px;">{cells}</td>'
            f'</tr>'
        )

    if has_errors:
        b_bg, b_color, b_ico = "#ffebee", "#c62828", "&#10007;"
        b_text = U("api_err")
    else:
        b_bg, b_color, b_ico = "#e8f5e9", "#2e7d32", "&#10003;"
        b_text = U("api_ok")

    skip_note = U("of_available").format(n=n_skip_avail) if n_skip_avail else ""
    rows_html = (
        _row("Getter", n_valid_g, n_invalid_g)
        + _row("Setter", n_valid_s, n_invalid_s)
        + _row("Skip", n_valid_skip, n_invalid_skip, skip_note)
    )

    html = (
        f'<div style="border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;'
        f'margin:8px 0;">'
        f'<div style="background:{b_bg};color:{b_color};padding:8px 16px;'
        f'font-weight:700;font-size:0.95em;">'
        f'{b_ico}&ensp;{b_text}</div>'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'{rows_html}</table></div>'
    )

    # Error details
    if has_errors:
        details = []
        if api and api.invalid_getters:
            details.append(f'**{U("invalid_getters")}:** `{", ".join(api.invalid_getters)}`')
        if api and api.invalid_setters:
            details.append(f'**{U("invalid_setters")}:** `{", ".join(api.invalid_setters)}`')
        if invalid_skips:
            details.append(f'**{U("invalid_skips")}:** `{", ".join(invalid_skips)}`')
        if details:
            html += "\n\n" + "\n\n".join(details)

    return html


def _build_conditions_data(code: str, l1: L1Report) -> dict:
    """Pre-build flowchart + semantic blocks data for embedding in chat."""
    result = {"flow_html": None, "flow_height": 0, "blocks_html": None}
    if not code or not l1 or not l1.syntax_ok:
        return result

    display_labels = build_display_labels(
        triggers=CAT.get("triggers", []),
        actions=CAT.get("actions", []),
        trigger_slugs=SC["trigger_apis"],
        action_slugs=SC["action_apis"],
        lang=lang,
        services=CAT.get("services", []),
    )

    inv_set = None
    if l1.api_report and l1.api_report.invalid_setters:
        inv_set = set(l1.api_report.invalid_setters)

    flow_html, flow_height = render_code_flowchart_html(
        code, lang=lang, user_type=user_type,
        display_labels=display_labels, invalid_setters=inv_set,
    )
    result["flow_html"] = flow_html
    result["flow_height"] = flow_height

    if l1.outcomes_raw:
        result["blocks_html"] = render_flowchart_html(
            l1.outcomes_raw, lang=lang, user_type=user_type,
            display_labels=display_labels,
        )

    return result


def _execute_tool(intent: str):
    """Execute code generation + L1 validation (tool for the orchestrator).

    Returns (code, l1_report, conditions_dict, api_fixes_list).
    """
    # 1. Generate code
    final_prompt = _build_prompt(intent)
    payload = {
        "model": GENERATION_MODEL,
        "messages": [{"role": "user", "content": final_prompt}],
        "temperature": 0.0,
        "max_tokens": 512,
        "stream": False,
    }
    try:
        r = requests.post(GEN_ENDPOINT, json=payload, timeout=120)
        r.raise_for_status()
        code = strip_llm_markdown(r.json()["choices"][0]["message"]["content"])
    except Exception as e:
        return "", None, {"flow_html": None, "flow_height": 0, "blocks_html": None}, []

    # 2. Log attempt
    ss.setdefault("attempt_count", {})
    count = ss["attempt_count"].get(SC["code"], 0) + 1
    ss["attempt_count"][SC["code"]] = count
    ss.setdefault("attempt_log", []).append({
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": user_id,
        "scenario_code": SC["code"],
        "row_index": SC["row_index"],
        "attempt": count,
        "user_intent": intent,
        "llm_output": code,
        "selected_ingredients": sorted(sel_ing),
        "selected_setters": sorted(sel_set),
    })
    ss["selected_attempt"] = count

    # 3. L1 validation
    l1 = None
    if code:
        l1 = run_l1_validation(
            code=code,
            trigger_slugs=SC["trigger_apis"],
            action_slugs=SC["action_apis"],
            lang=lang,
        )

    # 4. API fixes (deterministic)
    api_fixes = []
    if l1 and l1.syntax_ok:
        api_fixes = suggest_api_fixes(
            l1, SC["trigger_apis"], SC["action_apis"],
            lang=lang,
            catalog_triggers=CAT.get("triggers", []),
            catalog_actions=CAT.get("actions", []),
        )

    # 5. Build conditions data (flowchart + blocks)
    conditions = _build_conditions_data(code, l1)

    return code, l1, conditions, api_fixes


def _run_orchestrator(user_text: str):
    """Send user message to the orchestrator and update chat + session state."""
    studio_chat = ss["studio_chat"]
    logger = _get_logger()

    # Log user message
    has_gen = any(m.get("type") == "generation" for m in studio_chat)
    logger.log_user_message(user_text, "followup" if has_gen else "intent")

    # Build API surface text for the orchestrator's system prompt
    api_surface = build_api_surface_text(
        SC["trigger_apis"], SC["action_apis"],
        TRIGGER_INDEX, ACTION_INDEX,
    )

    # Run orchestrator turn (uses dedicated orchestrator model)
    result = run_orchestrator_turn(
        history=ss.get("orchestrator_messages", []),
        user_message=user_text,
        tool_executor=_execute_tool,
        endpoint=ORC_ENDPOINT,
        model=ORCHESTRATOR_MODEL,
        lang=lang,
        api_surface_text=api_surface,
    )

    # Save orchestrator context for multi-turn
    ss["orchestrator_messages"] = result.updated_messages

    if result.tool_called:
        # Generation happened — add generation message to chat
        data = result.generation_data
        l1 = data["l1_report"]
        l1_html = _build_l1_card_html(l1)

        # Log tool call
        logger.log_tool_call(
            intent_used=result.intent_used,
            code=data["code"],
            l1_syntax_ok=l1.syntax_ok if l1 else None,
            l1_api_valid=l1.api_report.is_valid if l1 and l1.api_report else None,
            getter_coverage=l1.getter_coverage if l1 else None,
            setter_coverage=l1.setter_coverage if l1 else None,
            invalid_getters=l1.api_report.invalid_getters if l1 and l1.api_report else [],
            invalid_setters=l1.api_report.invalid_setters if l1 and l1.api_report else [],
            warnings=l1.warnings if l1 else [],
            outcomes_summary=l1.outcomes_summary if l1 else [],
        )

        # Run execution sandbox
        exec_results = []
        if data["code"] and l1 and l1.syntax_ok:
            fixtures = build_default_fixtures(
                SC["trigger_apis"], SC["action_apis"],
                TRIGGER_INDEX, ACTION_INDEX,
            )
            exec_results = run_test_suite(
                data["code"], fixtures,
                SC["trigger_apis"], SC["action_apis"],
                TRIGGER_INDEX, ACTION_INDEX,
            )

        studio_chat.append({
            "role": "assistant",
            "type": "generation",
            "data": {
                "code": data["code"],
                "l1_report": l1,
                "api_fixes": data["api_fixes"],
                "l1_html": l1_html,
                "conditions": data["conditions"],
                "commentary": result.assistant_text,
                "suggested_intent": result.suggested_intent,
                "exec_results": exec_results,
            },
        })

        # Update latest_* for evaluation
        ss["latest_code"] = data["code"]
        ss["latest_l1"] = l1
        ss["latest_l2"] = None
    else:
        # Pure conversation — add follow-up message
        studio_chat.append({
            "role": "assistant",
            "type": "followup",
            "text": result.assistant_text,
            "suggested_intent": result.suggested_intent,
        })

    # Log agent response
    logger.log_agent_response(
        text=result.assistant_text,
        tool_called=result.tool_called,
        suggested_intent=result.suggested_intent,
    )

    # Also log to DB for crash safety
    db_log_interaction(
        participant_id=user_id,
        scenario_code=SC["code"],
        turn=logger._turn,
        elapsed_s=round(time.monotonic() - logger.session_start, 2),
        event="orchestrator_turn",
        data={
            "tool_called": result.tool_called,
            "has_suggestion": bool(result.suggested_intent),
        },
    )


# ============================================================
# MAIN — Chat (unified conversation with orchestrator)
# ============================================================

studio_chat = ss["studio_chat"]

# --- Chat container (bordered box with messages + input bar) ---
_chat_box = st.container(border=True)

with _chat_box:
    # Empty space placeholder when chat is empty
    if not studio_chat:
        st.markdown(
            "<div style='min-height:180px;display:flex;"
            "align-items:center;justify-content:center;color:#bbb;gap:10px;'>"
            f"<span style='font-size:1.1em;font-style:italic;'>"
            f"{U('chat_empty')}</span>"
            "<svg xmlns='http://www.w3.org/2000/svg' width='28' height='28' "
            "viewBox='-1.5 -2.5 30.5 29.5' fill='#ccc'>"
            "<path fill-rule='evenodd' "
            "d='M11 14.143L0 0h28L17 14.143V23l-6 3V14.143z'/>"
            "</svg>"
            "</div>",
            unsafe_allow_html=True,
        )

    # --- Render all chat messages ---
    for msg_index, msg in enumerate(studio_chat):
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.markdown(msg["text"])

        elif msg["type"] == "generation":
            with st.chat_message("assistant"):
                data = msg["data"]

                # Code
                st.markdown(f"**{U('chat_code_header')}**")
                st.code(data["code"] or U("no_code"), language="javascript")

                # L1 card
                if data.get("l1_html"):
                    st.markdown(data["l1_html"], unsafe_allow_html=True)

                # Embedded conditions (flowchart + semantic blocks)
                cond = data.get("conditions", {})
                if cond.get("flow_html"):
                    col_chart, col_blocks = st.columns([1, 1])
                    with col_chart:
                        components.html(cond["flow_html"], height=cond["flow_height"], scrolling=False)
                    with col_blocks:
                        if cond.get("blocks_html"):
                            st.html(cond["blocks_html"])

                # Execution sandbox results
                exec_results = data.get("exec_results", [])
                if exec_results:
                    all_pass = all(tr.passed for tr in exec_results)
                    _exec_cols = st.columns(len(exec_results))
                    for _ec, tr in zip(_exec_cols, exec_results):
                        with _ec:
                            icon = "\u2705" if tr.passed else "\u274c"
                            st.markdown(
                                f"{icon} **{tr.fixture_name}**"
                                + ("" if tr.passed else f"\n\n{'  '.join(tr.failures)}")
                            )

                # Orchestrator commentary (replaces L2 + diagnosis)
                commentary = data.get("commentary", "")
                if commentary:
                    st.markdown("---")
                    st.markdown(commentary)

                # Suggested intent with diff + "Use this" button
                suggested = data.get("suggested_intent", "")
                if suggested:
                    original_intent = ""
                    for prev in reversed(studio_chat[:msg_index]):
                        if prev.get("type") in ("intent", "followup") and prev["role"] == "user":
                            original_intent = prev["text"]
                            break

                    diff_html = render_intent_diff_html(
                        original_intent, suggested,
                    )
                    st.markdown(
                        f'<div style="border:1px solid #e0e0e0;border-radius:8px;'
                        f'padding:12px 16px;margin:8px 0;line-height:1.8;'
                        f'font-size:0.95em;">'
                        f'<strong>{U("agent_try")}:</strong><br>{diff_html}</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        U("agent_use_suggestion"),
                        key=f"use_suggestion_{msg_index}",
                    ):
                        _get_logger().log_suggestion_accepted(suggested)
                        ss["studio_chat"].append({
                            "role": "user",
                            "type": "intent",
                            "text": suggested,
                        })
                        ss["_clear_input"] = True
                        with st.spinner(U("chat_generating")):
                            _run_orchestrator(suggested)
                        st.rerun()

        elif msg["type"] == "followup" and msg["role"] == "assistant":
            with st.chat_message("assistant"):
                text = msg.get("text", "")
                st.markdown(text)

                # Suggested intent in follow-up messages too
                suggested = msg.get("suggested_intent", "")
                if suggested:
                    original_intent = ""
                    for prev in reversed(studio_chat[:msg_index]):
                        if prev["role"] == "user":
                            original_intent = prev["text"]
                            break
                    diff_html = render_intent_diff_html(
                        original_intent, suggested,
                    )
                    st.markdown(
                        f'<div style="border:1px solid #e0e0e0;border-radius:8px;'
                        f'padding:12px 16px;margin:8px 0;line-height:1.8;'
                        f'font-size:0.95em;">'
                        f'<strong>{U("agent_try")}:</strong><br>{diff_html}</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        U("agent_use_suggestion"),
                        key=f"use_suggestion_{msg_index}",
                    ):
                        _get_logger().log_suggestion_accepted(suggested)
                        ss["studio_chat"].append({
                            "role": "user",
                            "type": "intent",
                            "text": suggested,
                        })
                        ss["_clear_input"] = True
                        with st.spinner(U("chat_generating")):
                            _run_orchestrator(suggested)
                        st.rerun()

    # --- Input bar (inside the chat box, with separator) ---
    # In single-shot mode, disable input after generation
    _has_gen = any(m.get("type") == "generation" for m in studio_chat)
    _input_disabled = (_current_condition == "single_shot" and _has_gen)

    st.markdown(
        "<hr style='margin:4px 0 8px 0;border:none;border-top:1px solid #d0d0d0;'>",
        unsafe_allow_html=True,
    )

    _chat_text = ""
    _btn_send = False

    _col_input, _col_send = st.columns(
        [15, 1], vertical_alignment="bottom",
    )

    with _col_input:
        # Clear input: bump the widget key so Streamlit creates a fresh instance
        _input_gen = ss.get("_input_gen", 0)
        if ss.pop("_clear_input", False):
            _input_gen += 1
            ss["_input_gen"] = _input_gen
        _chat_text = st.text_area(
            U("chat_input_placeholder"),
            key=f"chat_input_text_{_input_gen}",
            label_visibility="collapsed",
            placeholder=U("chat_input_placeholder"),
            height=68,
            disabled=_input_disabled,
        )
    with _col_send:
        _btn_send = st.button(
            "\u27a4",
            key="btn_chat_send",
            type="primary",
            disabled=_input_disabled,
        )

# --- Handle send (condition-aware) ---
if _btn_send and _chat_text and _chat_text.strip():
    text = _chat_text.strip()
    has_generation = any(m.get("type") == "generation" for m in ss["studio_chat"])

    if _current_condition == "single_shot":
        # Condition A: only one generation, no follow-up
        if has_generation:
            pass  # ignore — single-shot allows only one generation
        else:
            ss["studio_chat"].append({"role": "user", "type": "intent", "text": text})
            logger = _get_logger()
            logger.log_user_message(text, "intent")

            # Direct generation (no orchestrator)
            with st.spinner(U("chat_generating")):
                code, l1, conditions, api_fixes = _execute_tool(text)

            l1_html = _build_l1_card_html(l1)

            # Run execution sandbox
            exec_results = []
            if code and l1 and l1.syntax_ok:
                fixtures = build_default_fixtures(
                    SC["trigger_apis"], SC["action_apis"],
                    TRIGGER_INDEX, ACTION_INDEX,
                )
                exec_results = run_test_suite(
                    code, fixtures,
                    SC["trigger_apis"], SC["action_apis"],
                    TRIGGER_INDEX, ACTION_INDEX,
                )

            ss["studio_chat"].append({
                "role": "assistant",
                "type": "generation",
                "data": {
                    "code": code,
                    "l1_report": l1,
                    "api_fixes": api_fixes,
                    "l1_html": l1_html,
                    "conditions": conditions,
                    "commentary": "",
                    "suggested_intent": "",
                    "exec_results": exec_results,
                },
            })
            ss["latest_code"] = code
            ss["latest_l1"] = l1

            # Log tool call
            logger.log_tool_call(
                intent_used=text,
                code=code,
                l1_syntax_ok=l1.syntax_ok if l1 else None,
                l1_api_valid=l1.api_report.is_valid if l1 and l1.api_report else None,
                getter_coverage=l1.getter_coverage if l1 else None,
                setter_coverage=l1.setter_coverage if l1 else None,
                invalid_getters=l1.api_report.invalid_getters if l1 and l1.api_report else [],
                invalid_setters=l1.api_report.invalid_setters if l1 and l1.api_report else [],
                warnings=l1.warnings if l1 else [],
                outcomes_summary=l1.outcomes_summary if l1 else [],
            )

            # Also log to DB
            db_log_interaction(
                participant_id=user_id,
                scenario_code=SC["code"],
                turn=1,
                elapsed_s=0,
                event="single_shot_generation",
                data={"intent": text, "code": code,
                      "l1_ok": l1.syntax_ok if l1 else None},
            )

            ss["_clear_input"] = True
            st.rerun()
    else:
        # Condition B: orchestrator decides tool vs conversation
        msg_type = "intent" if not has_generation else "followup"
        ss["studio_chat"].append({"role": "user", "type": msg_type, "text": text})
        with st.spinner(U("chat_generating")):
            _run_orchestrator(text)
        ss["_clear_input"] = True
        st.rerun()

# --- Handle prefill on return from failed evaluation ---
if ss.get("prefill_prompt"):
    _prefill = ss.pop("prefill_prompt")
    ss["studio_chat"].append({"role": "user", "type": "intent", "text": _prefill})
    ss["_clear_input"] = True
    with st.spinner(U("chat_generating")):
        _run_orchestrator(_prefill)
    st.rerun()

# ============================================================
# MAIN — Valutazione + Salvataggio
# ============================================================

if ss.get("latest_code"):
    generated_code = ss["latest_code"]

    st.markdown("---")
    st.markdown(f"## {U('evaluation')}")

    # ---- Expert editor ----
    state_key = f"{SC['code']}__{ss.get('selected_attempt', 1)}"

    if "editor_last_submit" not in ss:
        ss["editor_last_submit"] = {}
    if "applied_code" not in ss:
        ss["applied_code"] = {}

    edited_code = None
    expert_claim_fixed = "not_required"
    expert_gave_up = None

    if user_type == "expert":
        st.markdown(f"### {U('expert_correction')}")

        if state_key not in ss["editor_last_submit"]:
            ss["editor_last_submit"][state_key] = generated_code

        editor_value = (
            ss["applied_code"].get(state_key)
            or ss["editor_last_submit"][state_key]
        )

        editor_buttons = [
            {
                "name": "APPLICA MODIFICHE",
                "feather": "Check",
                "primary": True,
                "hasText": True,
                "showWithIcon": True,
                "commands": ["submit"],
                "style": {"bottom": "0.5rem", "right": "0.5rem"},
            }
        ]

        resp = code_editor(
            editor_value,
            lang="javascript",
            key=f"editor_{state_key}",
            buttons=editor_buttons,
            options={"wrap": True},
        )

        if isinstance(resp, dict) and resp.get("type") == "submit":
            if isinstance(resp.get("text"), str):
                ss["editor_last_submit"][state_key] = resp["text"]
                ss["applied_code"][state_key] = resp["text"]
                st.success(U("applied"))

        edited_code = ss["editor_last_submit"][state_key]

        # Status
        if state_key in ss["applied_code"]:
            st.info(U("applied"))
        else:
            st.warning(U("not_applied"))

        # Claim fixed
        applied = ss["applied_code"].get(state_key)
        has_real_fix = (
            isinstance(applied, str)
            and applied.strip() != ""
            and applied.strip() != generated_code.strip()
        )

        st.markdown(f"### {U('correction_result')}")

        UI_TO_CANON = {
            U("not_required"): "not_required",
            "si": "yes",
            "yes": "yes",
            "no": "no",
        }
        _yes = "si" if lang == "it" else "yes"

        if not has_real_fix:
            _ = st.radio(
                U("claim_fixed_q"),
                [U("not_required"), _yes, "no"],
                index=0,
                horizontal=True,
                key=f"expert_claim_fixed_{state_key}_locked",
            )
            expert_claim_fixed = "not_required"
            st.caption(U("claim_fixed_locked"))
        else:
            ui_choice = st.radio(
                U("claim_fixed_q"),
                [_yes, "no"],
                horizontal=True,
                key=f"expert_claim_fixed_{state_key}",
            )
            expert_claim_fixed = UI_TO_CANON.get(ui_choice, "no")

        expert_gave_up = st.checkbox(U("gave_up"))

    # ---- Final code ----
    final_code_used = ss.get("applied_code", {}).get(
        state_key,
        generated_code,
    )

    # ---- Evaluation ----
    correct = st.radio(
        U("correct_q"),
        ["yes", "no"],
        horizontal=True,
    )

    notes = st.text_area(U("eval_notes"), height=100)

    # ---- Save ----
    if st.button(U("save_eval")):
        attempt_log = ss.get("attempt_log", [])
        current = attempt_log[-1] if attempt_log else {}

        l1 = ss.get("latest_l1")

        # Extract agent info from latest generation message
        _last_gen = None
        for _m in reversed(ss.get("studio_chat", [])):
            if _m.get("type") == "generation":
                _last_gen = _m["data"]
                break

        record = dict(current)
        record.update({
            "user_id": user_id,
            "user_type": user_type,
            "eval_correct": correct,
            "eval_notes": notes,
            "final_code_used": final_code_used,
            "expert_edited_code": edited_code,
            "expert_claim_fixed": expert_claim_fixed,
            "expert_gave_up": expert_gave_up,
            "final_timestamp": datetime.utcnow().isoformat(),
            # L1 fields
            "l1_syntax_ok": l1.syntax_ok if l1 else None,
            "l1_api_valid": (l1.api_report.is_valid if l1 and l1.api_report else None),
            "l1_invalid_getters": (l1.api_report.invalid_getters if l1 and l1.api_report else []),
            "l1_invalid_setters": (l1.api_report.invalid_setters if l1 and l1.api_report else []),
            "l1_outcomes_summary": (l1.outcomes_summary if l1 else []),
            "l1_getter_coverage": (l1.getter_coverage if l1 else None),
            "l1_setter_coverage": (l1.setter_coverage if l1 else None),
            "l1_warnings": (l1.warnings if l1 else []),
            # Orchestrator fields
            "agent_fixes_shown": (_last_gen.get("api_fixes", []) if _last_gen else []),
            "agent_commentary": (_last_gen.get("commentary", "") if _last_gen else ""),
            "agent_suggested_intent": (_last_gen.get("suggested_intent", "") if _last_gen else ""),
            "agent_suggestion_accepted": any(
                m.get("type") == "intent" and m is not ss["studio_chat"][0]
                for m in ss.get("studio_chat", [])
                if m.get("role") == "user"
            ) if ss.get("studio_chat") else False,
        })

        with open(RESULTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # Log evaluation to interaction log
        _logger = _get_logger()
        _logger.log_evaluation(
            correct=correct,
            notes=notes,
            final_code=final_code_used,
            expert_edited=bool(edited_code),
        )

        # Complete scenario session in DB
        complete_scenario_session(
            participant_id=user_id,
            scenario_code=SC["code"],
            final_correct=correct,
            eval_notes=notes,
            total_turns=_logger._turn,
            total_elapsed_s=round(
                time.monotonic() - _logger.session_start, 2
            ),
            final_code=final_code_used,
            l1_syntax_ok=l1.syntax_ok if l1 else None,
            l1_api_valid=l1.api_report.is_valid if l1 and l1.api_report else None,
        )

        if correct == "yes":
            # Next scenario
            ss["scenario_index"] = ss.get("scenario_index", 0) + 1
            for k in ("forced_scenario", "resume_from_eval", "prefill_prompt",
                       "studio_chat", "orchestrator_messages",
                       "latest_code", "latest_l1", "latest_l2",
                       "attempt_count", "attempt_log"):
                ss.pop(k, None)
            st.rerun()
        else:
            # Stay, prefill for retry
            ss["prefill_prompt"] = current.get("user_intent", "")
            for k in ("studio_chat", "orchestrator_messages",
                       "latest_code", "latest_l1", "latest_l2"):
                ss.pop(k, None)
            st.rerun()
