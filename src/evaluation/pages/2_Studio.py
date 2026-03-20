# pages/2_Studio.py — Pagina unica: sidebar (contesto + selezione) + main (workflow)

# --- Minimal imports: streamlit FIRST, then page config + loading banner ---
import os, sys
import streamlit as st

st.set_page_config(
    page_title="NL2TAP Studio",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# CSS + loading banner — rendered BEFORE heavy imports
st.markdown("""
<style>
/* Force light theme */
:root, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
[data-testid="stHeader"], .main, .block-container, stApp {
    color-scheme: light !important;
}
[data-testid="stAppViewContainer"] { background: #ffffff !important; color: #111827 !important; }
[data-testid="stSidebar"] > div { background: #f9fafb !important; }
[data-testid="stHeader"] { background: #ffffff !important; }
[data-testid="stSidebar"] { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
.stDeployButton { display: none !important; }
/* More breathing room on the main content area */
.block-container { padding: 4rem 4rem !important; max-width: 1100px !important; }
/* Prevent column rows from wrapping */
[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
/* Fixed-width nav next button */
.st-key-nav_next_btn {
    flex: 0 0 auto !important; min-width: 110px !important; max-width: 140px !important;
}
.st-key-nav_next_btn button {
    white-space: nowrap !important; font-size: 0.82rem !important;
    padding: 6px 12px !important;
}
[data-testid="stSidebarNav"] { display: none; }
[data-testid="stSidebarCollapseButton"] { display: none; }
[data-testid="stSidebarCollapsedControl"] { display: none; }
/* G2 field-selection styling */
.g2-badge {
    display: inline-block; font-size: 0.72rem; text-transform: uppercase;
    letter-spacing: 0.04em; padding: 2px 8px; border-radius: 4px;
    font-weight: 600; margin-right: 6px; vertical-align: middle;
}
.g2-badge-trigger { background: #eff6ff; color: #2563eb; }
.g2-badge-action  { background: #fffbeb; color: #d97706; }
.g2-svc-name {
    font-size: 0.82rem; color: #6b7280; vertical-align: middle;
}
.g2-hint {
    font-size: 0.82rem; color: #9ca3af; font-style: italic;
    margin: -4px 0 4px 0; line-height: 1.3;
}
/* Compact vertical gap inside field-selection containers */
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] {
    gap: 0.25rem;
}
.g2-skip-badge {
    display: inline-block; font-size: 0.7rem; padding: 1px 7px;
    border-radius: 4px; background: #fef2f2; color: #dc2626;
    font-weight: 600; margin-left: 6px; vertical-align: middle;
}
/* G1 chip selector: ensure iframe has no extra border */
iframe[title="chip_selector"] {
    border: none !important;
}
/* Field drawer: collapse entire wrapper — rendering happens in parent document */
iframe[title*="field_drawer"] {
    position: absolute !important; width: 0 !important; height: 0 !important;
    overflow: hidden !important; border: none !important;
}
[data-testid="stElementContainer"]:has(iframe[title*="field_drawer"]) {
    display: none !important;
}
/* Smooth scrolling */
html { scroll-behavior: smooth; }
/* Questionnaire compact layout — confine radios/sliders to a comfortable width */
.q-page { max-width: 620px; margin: 0 auto; }
.q-page .stRadio > div { max-width: 440px; }
.q-page .stSlider { max-width: 480px; }
/* Larger question labels in questionnaires */
.q-page .stRadio > label > div > p,
.q-page .stSlider > label > div > p {
    font-size: 1.05rem !important;
    font-weight: 500 !important;
    line-height: 1.5 !important;
    color: #1e293b !important;
}
/* Section step indicator */
.q-step {
    display: flex; align-items: center; gap: 10px;
    margin: 32px 0 8px; padding-bottom: 6px;
    border-bottom: 2px solid #e2e8f0;
}
.q-step-num {
    width: 30px; height: 30px; border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.9rem; color: #fff; flex-shrink: 0;
}
.q-step-label { font-size: 1.1rem; font-weight: 700; }
/* Tutorial overlay: collapse iframe — rendering happens in parent document */
iframe[title*="tutorial_overlay"] {
    position: absolute !important; width: 0 !important; height: 0 !important;
    overflow: hidden !important; border: none !important;
}
[data-testid="stElementContainer"]:has(iframe[title*="tutorial_overlay"]) {
    display: none !important;
}
/* Scenario navigation bar */
.sc-nav {
    display: flex; align-items: center; gap: 10px;
    background: linear-gradient(135deg, #eff6ff 0%, #f0f9ff 100%);
    border: 1px solid #bfdbfe; border-radius: 12px;
    padding: 10px 16px; margin-bottom: 10px;
}
.sc-nav-left { display: flex; align-items: center; gap: 10px; }
.sc-nav-dots { display: flex; gap: 5px; align-items: center; }
.sc-dot {
    width: 28px; height: 28px; border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 0.72rem; font-weight: 700; cursor: default;
    border: 2px solid #cbd5e1; background: #fff; color: #94a3b8;
    transition: all .15s;
}
.sc-dot.active {
    border-color: #3b82f6; background: #3b82f6; color: #fff;
    box-shadow: 0 0 0 3px rgba(59,130,246,.18);
}
.sc-dot.done {
    border-color: #22c55e; background: #f0fdf4; color: #16a34a;
}
.sc-dot.done.active {
    background: #22c55e; color: #fff; border-color: #16a34a;
    box-shadow: 0 0 0 3px rgba(34,197,94,.18);
}
.sc-nav-sep { width: 1px; height: 28px; background: #cbd5e1; margin: 0 2px; }
.sc-nav-center { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.sc-nav-title {
    font-size: 0.92rem; font-weight: 600; color: #1e3a5f;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.sc-nav-meta {
    display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
}
.sc-nav-tag {
    display: inline-block; font-size: 0.65rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.04em;
    padding: 1px 7px; border-radius: 4px; line-height: 1.5;
}
.sc-tag-block { background: #e0e7ff; color: #4338ca; }
.sc-tag-c1 { background: #dcfce7; color: #15803d; }
.sc-tag-c2 { background: #fef9c3; color: #a16207; }
.sc-tag-c3 { background: #fee2e2; color: #b91c1c; }
.sc-nav-right { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
.sc-nav-progress {
    font-size: 0.78rem; color: #64748b; white-space: nowrap; font-weight: 500;
}
.sc-nav-bar-track {
    width: 90px; height: 5px; background: #e2e8f0; border-radius: 3px; overflow: hidden;
}
.sc-nav-bar-fill {
    height: 100%; background: linear-gradient(90deg, #3b82f6, #22c55e);
    border-radius: 3px; transition: width .3s ease;
}
/* Context card */
.ctx-card {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 16px 20px; margin-bottom: 8px; line-height: 1.6;
}
.ctx-card .ctx-label {
    font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;
    color: #94a3b8; font-weight: 600; margin-bottom: 6px;
}
.ctx-card .ctx-text { font-size: 0.92rem; color: #334155; }
.ctx-ifthen {
    background: #eff6ff; border-left: 3px solid #3b82f6;
    padding: 10px 16px; border-radius: 0 8px 8px 0;
    margin: 8px 0; font-size: 0.9rem; color: #1e40af;
}
.ctx-examples {
    display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px;
}
.ctx-ex-chip {
    background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 16px;
    padding: 4px 12px; font-size: 0.82rem; color: #475569;
    font-style: italic;
}
/* Sticky user badge (top-left) */
.user-badge-sticky {
    position: fixed; top: 12px; left: 16px; z-index: 999999;
    display: flex; align-items: center; gap: 8px;
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 20px;
    padding: 5px 14px 5px 10px; box-shadow: 0 1px 4px rgba(0,0,0,.08);
    font-family: inherit; font-size: 0.78rem; color: #475569;
    cursor: default; user-select: none;
}
.user-badge-sticky .uid { font-weight: 600; color: #334155; }
.user-badge-sticky .sep { color: #cbd5e1; margin: 0 2px; }
.user-badge-sticky .logout-link {
    color: #94a3b8; cursor: pointer; display: flex; align-items: center;
    transition: color .15s;
}
.user-badge-sticky .logout-link:hover { color: #ef4444; }
.user-badge-sticky .logout-link svg { width: 14px; height: 14px; }
/* Hide the real Streamlit logout button — keep in DOM so JS .click() works */
.st-key-studio_logout_btn { position: fixed; bottom: -100px; left: -100px; opacity: 0; }
/* Streaming reveal animations */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0); }
}
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
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# code_editor import removed — editing now happens inline in chat
from utils.study_utils import STUDY, NON_EXP, EXP
from code_parsing.feedback import run_l1_validation, L1Report
from code_parsing.flowchart import render_behavior_flow_html, render_api_warning_html
from code_parsing.catalog_validator import build_display_labels
from code_parsing.agent_support import (
    suggest_api_fixes, render_intent_diff_html,
    run_orchestrator_turn, build_api_surface_text,
    build_api_surface_behavioral,
)
from utils.interaction_logger import InteractionLogger
from utils.chip_component import chip_selector as _chip_selector
from utils.chip_component import field_drawer as _field_drawer
from utils.chip_component import tutorial_overlay as _tutorial_overlay
from utils.session_manager import (
    start_scenario_session, complete_scenario_session,
    log_interaction as db_log_interaction, get_participant_progress,
    get_scenario_attempt_count, get_last_generated_code,
    save_chat_snapshot, load_chat_snapshot,
    compute_discrepancy, save_toast_response, get_toast_responses,
    save_tlx_response, get_tlx_responses,
    save_sus_response, get_sus_response, get_sus_responses,
    validate_session_token, invalidate_session_token,
)

# --- Model serving endpoints ---
# LM Studio: generator (sequential, low frequency)
# vLLM: orchestrator (concurrent batching, tool calling)
GEN_ENDPOINT = "http://localhost:1234/v1/chat/completions"
ORC_ENDPOINT = "http://localhost:8001/v1/chat/completions"
GENERATION_MODEL = "ft_2_qwen_merged"
ORCHESTRATOR_MODEL = "qwen3-4b-2507"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS_PATH = _PROJECT_ROOT / "results" / "user_study_results.jsonl"
RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)


# ============================================================
# STREAMING / ANIMATION HELPERS
# ============================================================

def _simulated_stream(text, chunk_size=5, delay=0.025):
    """Yield word chunks with delay for st.write_stream(), preserving newlines."""
    lines = text.split('\n')
    for li, line in enumerate(lines):
        if li > 0:
            yield '\n'
        words = line.split()
        for i in range(0, max(len(words), 1), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            if i + chunk_size < len(words):
                chunk += " "
            if chunk:
                yield chunk
                time.sleep(delay)


def _anim_wrap(html: str, delay: float, is_fresh: bool) -> str:
    """Wrap HTML in a fadeInUp animation div (only for fresh messages)."""
    if not is_fresh:
        return html
    return (
        f'<div style="animation:fadeInUp 0.45s ease-out {delay}s backwards;">'
        f'{html}</div>'
    )


_DRAWER_CLEANUP_HTML = (
    '<script>'
    '(function(){'
    '["sfd-stack","sfd-tooltip","tutorial-spotlight","tutorial-callout"]'
    '.forEach(function(id){'
    'var e=window.parent.document.getElementById(id);'
    'if(e)e.parentNode.removeChild(e);'
    '});'
    '})();'
    '</script>'
)

def _emit_dom_cleanup():
    """Inject JS via st.components.v1.html to remove drawer/tutorial DOM from parent."""
    import streamlit.components.v1 as _cv1
    _cv1.html(_DRAWER_CLEANUP_HTML, height=0)

def _cleanup_scenario_state(ss, scenario_code: str):
    """Clear scenario-specific session state + remove field-drawer DOM elements."""
    for k in ("forced_scenario", "resume_from_eval", "prefill_prompt",
              "studio_chat", "orchestrator_messages",
              "latest_code", "latest_l1", "latest_l2",
              "attempt_count", "attempt_log",
              "_scenario_attempt_num", "_last_gen_fingerprint"):
        ss.pop(k, None)
    # Clear field-drawer selection keys for the completed scenario
    ss.pop(f"chip_sel_ing_{scenario_code}", None)
    ss.pop(f"chip_sel_set_{scenario_code}", None)
    # Clear field selections for the completed scenario
    if "selected_ingredients" in ss and scenario_code in ss["selected_ingredients"]:
        del ss["selected_ingredients"][scenario_code]
    if "selected_setters" in ss and scenario_code in ss["selected_setters"]:
        del ss["selected_setters"][scenario_code]
    # Bump drawer close nonce to force drawer DOM cleanup
    ss["_drawer_close_nonce"] = ss.get("_drawer_close_nonce", 0) + 1
    # Remove drawer DOM elements from parent page
    _emit_dom_cleanup()


# ============================================================
# SESSION CHECK (with token restore)
# ============================================================

def _try_restore_session():
    """Attempt to restore session from URL token if session_state is empty."""
    token = st.query_params.get("token", "")
    if not token:
        return False
    session_data = validate_session_token(token)
    if not session_data:
        st.query_params.pop("token", None)
        return False
    st.session_state["authenticated"] = True
    st.session_state["_session_token"] = token
    st.session_state["user_id"] = session_data["participant_id"]
    st.session_state["user_type"] = session_data["user_type"]
    st.session_state["lang"] = session_data["lang"]
    if session_data.get("is_admin"):
        st.session_state["admin_authenticated"] = True
    if session_data.get("scenario_assignment"):
        st.session_state["scenario_assignment"] = session_data["scenario_assignment"]
        st.session_state["condition_order"] = session_data["condition_order"]
        st.session_state["counterbalance_group"] = session_data["counterbalance_group"]
        st.session_state["study_registration"] = {
            "participant_id": session_data["participant_id"],
            "scenario_assignment": session_data["scenario_assignment"],
            "condition_order": session_data["condition_order"],
            "counterbalance_group": session_data["counterbalance_group"],
            "already_registered": True,
        }
    return True

user_id = st.session_state.get("user_id", "").strip()
if not user_id:
    if not _try_restore_session():
        st.switch_page("Home.py")
    user_id = st.session_state.get("user_id", "")

# Ensure token is always in URL so page reload can restore the session
_token = st.session_state.get("_session_token", "")
if _token and st.query_params.get("token", "") != _token:
    st.query_params["token"] = _token

user_type = st.session_state.get("user_type", "non_expert")
lang = st.session_state.get("lang", "it")

# Within-subjects design: condition determined per scenario from assignment
_scenario_assignment = st.session_state.get("scenario_assignment", [])
_condition_order = st.session_state.get("condition_order", ["A", "B"])

def _get_condition_for_scenario(scenario_code: str) -> str:
    """Look up the condition (A or B) for a given scenario from assignment."""
    for entry in _scenario_assignment:
        if entry.get("scenario_code") == scenario_code:
            return entry.get("condition", "B")
    # Fallback: determine by index — first half = condition_order[0], second = condition_order[1]
    return _condition_order[0]

def _get_block_for_scenario(scenario_code: str) -> int:
    """Look up the block (1 or 2) for a given scenario from assignment."""
    for entry in _scenario_assignment:
        if entry.get("scenario_code") == scenario_code:
            return entry.get("block", 1)
    return 1

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
        "trigger_ing": "Evento — Dati",
        "action_setter": "Azione — Configurazione",
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
        "edit_code_btn": "Modifica codice",
        "validate_edit_btn": "Valida modifiche",
        "cancel_edit_btn": "Annulla",
        "code_edited_label": "Codice modificato dall'utente",
        "code_validating": "Validazione del codice modificato...",
        "correct_q": "Il Filter Code finale è corretto?",
        "eval_notes": "Note sulla valutazione (opzionale)",
        "eval_notes_placeholder": "Spiega brevemente perch\u00e9 hai dato questa valutazione, eventuali dubbi o osservazioni\u2026",
        "save_eval": "Salva valutazione",
        "analysis": "Analisi",
        "agent_panel": "Assistente",
        "agent_fixes": "Suggerimenti API",
        "agent_analyze": "Analisi approfondita",
        "agent_analyzing": "Analisi in corso...",
        "agent_try": "Prova a riformulare",
        "agent_use_suggestion": "Usa questo intent",
        "agent_suggested_fields_label": "Campi suggeriti",
        "agent_use_fields": "Seleziona questi campi",
        "agent_code_or_suggestions": "Puoi modificare il codice direttamente oppure seguire i suggerimenti qui sotto.",
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
        # Non-expert evaluation
        "eval_behavioral_q": "Questa automazione corrisponde a ciò che volevi?",
        "eval_match_full": "Corrisponde completamente",
        "eval_match_partial": "Corrisponde parzialmente",
        "eval_match_no": "Non corrisponde",
        "eval_match_unsure": "Non sono sicuro/a",
        "eval_mismatch_q": "Se non corrisponde, cosa c'è di sbagliato?",
        "eval_confidence_q": "Quanto sei sicuro/a della tua valutazione?",
        "eval_confidence_low": "per nulla",
        "eval_confidence_high": "molto sicuro/a",
        # Expert evaluation
        "eval_behavioral_header": "Valutazione comportamentale",
        "eval_code_header": "Valutazione codice",
        "eval_code_correct_q": "Il codice JavaScript è corretto?",
        # Attempt counter
        "attempt_counter": "Tentativo {n}/{max}",
        "attempt_max_reached": "Hai raggiunto il numero massimo di tentativi per questo scenario.",
        "next_scenario": "Prossimo scenario",
        # G2 field selection
        "field_badge_trigger": "Dati evento",
        "field_badge_action": "Configurazione azione",
        "field_trigger_hint": "Dati noti dell'evento \u2014 seleziona quelli rilevanti per la tua regola",
        "field_action_hint": "Configurazione dell'azione \u2014 seleziona i campi che vuoi personalizzare",
        "field_select_all": "Tutti",
        "field_deselect": "Nessuno",
        "field_blockable": "bloccabile",
        # Navigation
        "nav_progress": "{done}/{total} completati",
        "nav_next": "Successivo",
        # Tutorial overlay — button labels
        "tutorial_btn_next": "Avanti",
        "tutorial_btn_back": "Indietro",
        "tutorial_btn_skip": "Salta tutorial",
        "tutorial_btn_done": "Ho capito!",
        # Tutorial overlay — step 1: scenario card
        "tutorial_scenario_title": "Leggi lo scenario",
        "tutorial_scenario_body": "Qui trovi la descrizione dell'automazione da personalizzare.",
        # Tutorial overlay — step 2: field drawer
        "tutorial_fields_title": "Seleziona i campi",
        "tutorial_fields_body": "Apri i pannelli per scegliere i dati dell'evento e i campi dell'azione.",
        # Tutorial overlay — step 3: chat input
        "tutorial_chat_title": "Descrivi il comportamento",
        "tutorial_chat_body": "Scrivi in linguaggio naturale cosa deve fare l'automazione e premi Invia.",
        # Tutorial overlay — step 4: results
        "tutorial_results_title": "Esamina il risultato",
        "tutorial_results_body_expert": (
            "Il sistema genera il codice e lo valida. Vedrai: validazione API, "
            "diagramma comportamentale, commento dell'assistente e il codice generato. "
            "Puoi MODIFICARE IL CODICE cliccando il pulsante sotto di esso: "
            "le modifiche verranno validate automaticamente."
        ),
        "tutorial_results_body_nonexpert": (
            "Il sistema genera l'automazione e mostra: il comportamento previsto, "
            "eventuali avvisi e un commento dell'assistente. "
            "Non vedrai codice: tutto descritto in linguaggio naturale."
        ),
        # Tutorial overlay — step 5: evaluation
        "tutorial_eval_title": "Valuta",
        "tutorial_eval_body_expert": (
            "Indica se il comportamento corrisponde al tuo intento, "
            "se il codice è corretto e se hai apportato correzioni. "
            "Hai massimo 3 tentativi per scenario."
        ),
        "tutorial_eval_body_nonexpert": (
            "Indica se il comportamento corrisponde a quanto desiderato "
            "e quanto sei sicuro della tua valutazione. "
            "Hai massimo 3 tentativi per scenario."
        ),
        # Tutorial mock messages (step 4 demo)
        "tutorial_mock_user": "Salva l'allegato solo se l'email proviene da un collega",
        "tutorial_mock_assistant": "Ho generato un'automazione che controlla il mittente dell'email e salva l'allegato solo se corrisponde a un indirizzo aziendale. Verifica se il comportamento corrisponde a quanto desiderato.",
        # TOAST questionnaire
        "toast_title": "Questionario sulla fiducia nel sistema",
        "toast_subtitle": "Indica quanto sei d'accordo con ciascuna affermazione (1 = per niente, 7 = completamente)",
        "toast_block_done": "Hai completato il blocco {n}. Prima di continuare, rispondi a queste domande.",
        "toast_item_1": "Capisco cosa dovrebbe fare il sistema",
        "toast_item_2": "Capisco i limiti del sistema",
        "toast_item_3": "Capisco le capacit\u00e0 del sistema",
        "toast_item_4": "Capisco come il sistema esegue i compiti",
        "toast_item_5": "Il sistema mi aiuta a raggiungere i miei obiettivi",
        "toast_item_6": "Il sistema funziona in modo coerente",
        "toast_item_7": "Il sistema funziona come dovrebbe",
        "toast_item_8": "Raramente sono sorpreso/a da come risponde il sistema",
        "toast_item_9": "Mi sento a mio agio nel fare affidamento sulle informazioni fornite dal sistema",
        "toast_submit": "Invia e continua",
        "toast_thanks": "Grazie! Prosegui con il prossimo blocco di scenari.",
        "toast_study_complete": "Hai completato tutti gli scenari. Grazie per la partecipazione!",
        # NASA-TLX questionnaire
        "tlx_title": "Carico di lavoro percepito",
        "tlx_subtitle": "Indica il livello per ciascuna dimensione (0 = molto basso, 100 = molto alto)",
        "tlx_mental": "Carico mentale",
        "tlx_mental_desc": "Quanto e' stato mentalmente impegnativo?",
        "tlx_physical": "Carico fisico",
        "tlx_physical_desc": "Quanto e' stato fisicamente impegnativo?",
        "tlx_temporal": "Pressione temporale",
        "tlx_temporal_desc": "Quanto ti sei sentito/a sotto pressione per il tempo?",
        "tlx_performance": "Prestazione percepita",
        "tlx_performance_desc": "Quanto sei soddisfatto/a di come e' andata?",
        "tlx_performance_low": "perfetta",
        "tlx_performance_high": "scarsa",
        "tlx_effort": "Impegno",
        "tlx_effort_desc": "Quanto ti e' costato in termini di fatica/impegno?",
        "tlx_frustration": "Frustrazione",
        "tlx_frustration_desc": "Quanto ti sei sentito/a frustrato/a o stressato/a?",
        "tlx_low": "molto basso",
        "tlx_high": "molto alto",
        # SUS questionnaire
        "sus_title": "Usabilita' del sistema",
        "sus_subtitle": "Indica quanto sei d'accordo con ciascuna affermazione (1 = per niente d'accordo, 5 = completamente d'accordo)",
        "sus_item_1": "Penso che mi piacerebbe usare questo sistema frequentemente",
        "sus_item_2": "Ho trovato il sistema inutilmente complesso",
        "sus_item_3": "Ho trovato il sistema facile da usare",
        "sus_item_4": "Penso che avrei bisogno del supporto di una persona tecnica per usare questo sistema",
        "sus_item_5": "Ho trovato le varie funzioni del sistema ben integrate",
        "sus_item_6": "Ho trovato troppa incoerenza in questo sistema",
        "sus_item_7": "Immagino che la maggior parte delle persone imparerebbe a usare questo sistema molto rapidamente",
        "sus_item_8": "Ho trovato il sistema molto macchinoso da usare",
        "sus_item_9": "Mi sono sentito/a molto sicuro/a nell'usare il sistema",
        "sus_item_10": "Ho dovuto imparare molte cose prima di poter iniziare a usare questo sistema",
        "sus_submit": "Invia questionario finale",
        "sus_thanks": "Grazie per aver completato lo studio!",
        "sus_disagree": "per niente d'accordo",
        "sus_agree": "completamente d'accordo",
        "questionnaire_submit": "Invia e continua",
        "toast_block_label": "Blocco",
    },
    "en": {
        "services": "Services",
        "trigger_ing": "Event — Data",
        "action_setter": "Action — Configuration",
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
        "edit_code_btn": "Edit code",
        "validate_edit_btn": "Validate changes",
        "cancel_edit_btn": "Cancel",
        "code_edited_label": "User-edited code",
        "code_validating": "Validating edited code...",
        "correct_q": "Is the final Filter Code correct?",
        "eval_notes": "Evaluation notes (optional)",
        "eval_notes_placeholder": "Briefly explain your evaluation, any doubts or observations\u2026",
        "save_eval": "Save evaluation",
        "analysis": "Analysis",
        "agent_panel": "Assistant",
        "agent_fixes": "API suggestions",
        "agent_analyze": "Deep analysis",
        "agent_analyzing": "Analyzing...",
        "agent_try": "Try rephrasing",
        "agent_use_suggestion": "Use this intent",
        "agent_suggested_fields_label": "Suggested fields",
        "agent_use_fields": "Select these fields",
        "agent_code_or_suggestions": "You can edit the code directly or follow the suggestions below.",
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
        # Non-expert evaluation
        "eval_behavioral_q": "Does this automation match what you wanted?",
        "eval_match_full": "Matches completely",
        "eval_match_partial": "Matches partially",
        "eval_match_no": "Does not match",
        "eval_match_unsure": "I'm not sure",
        "eval_mismatch_q": "If it doesn't match, what's wrong?",
        "eval_confidence_q": "How confident are you in your evaluation?",
        "eval_confidence_low": "not at all",
        "eval_confidence_high": "very confident",
        # Expert evaluation
        "eval_behavioral_header": "Behavioral evaluation",
        "eval_code_header": "Code evaluation",
        "eval_code_correct_q": "Is the JavaScript code correct?",
        # Attempt counter
        "attempt_counter": "Attempt {n}/{max}",
        "attempt_max_reached": "You have reached the maximum number of attempts for this scenario.",
        "next_scenario": "Next scenario",
        # G2 field selection
        "field_badge_trigger": "Event data",
        "field_badge_action": "Action config",
        "field_trigger_hint": "Known event data \u2014 select those relevant to your rule",
        "field_action_hint": "Action configuration \u2014 select the fields you want to customize",
        "field_select_all": "All",
        "field_deselect": "None",
        "field_blockable": "blockable",
        # Navigation
        "nav_progress": "{done}/{total} completed",
        "nav_next": "Next",
        # Tutorial overlay — button labels
        "tutorial_btn_next": "Next",
        "tutorial_btn_back": "Back",
        "tutorial_btn_skip": "Skip tutorial",
        "tutorial_btn_done": "Got it!",
        # Tutorial overlay — step 1: scenario card
        "tutorial_scenario_title": "Read the scenario",
        "tutorial_scenario_body": "Here you will find the description of the automation to customize.",
        # Tutorial overlay — step 2: field drawer
        "tutorial_fields_title": "Select the fields",
        "tutorial_fields_body": "Open the panels to choose event data and action fields.",
        # Tutorial overlay — step 3: chat input
        "tutorial_chat_title": "Describe the behavior",
        "tutorial_chat_body": "Write in natural language what the automation should do and press Send.",
        # Tutorial overlay — step 4: results
        "tutorial_results_title": "Examine the result",
        "tutorial_results_body_expert": (
            "The system generates code and validates it. You'll see: API validation, "
            "behavior diagram, assistant commentary, and the generated code. "
            "You can EDIT THE CODE by clicking the button below it: "
            "your changes will be validated automatically."
        ),
        "tutorial_results_body_nonexpert": (
            "The system generates the automation and shows: expected behavior, "
            "any warnings, and assistant commentary. "
            "You won't see code: everything is described in plain language."
        ),
        # Tutorial overlay — step 5: evaluation
        "tutorial_eval_title": "Evaluate",
        "tutorial_eval_body_expert": (
            "Indicate whether the behavior matches your intent, "
            "whether the code is correct, and if you made corrections. "
            "You have up to 3 attempts per scenario."
        ),
        "tutorial_eval_body_nonexpert": (
            "Indicate whether the behavior matches what you wanted "
            "and how confident you are in your evaluation. "
            "You have up to 3 attempts per scenario."
        ),
        # Tutorial mock messages (step 4 demo)
        "tutorial_mock_user": "Save the attachment only if the email is from a colleague",
        "tutorial_mock_assistant": "I generated an automation that checks the email sender and saves the attachment only if it matches a company address. Check whether the behavior matches your intent.",
        # TOAST questionnaire
        "toast_title": "Trust in the system questionnaire",
        "toast_subtitle": "Indicate how much you agree with each statement (1 = not at all, 7 = completely)",
        "toast_block_done": "You completed block {n}. Before continuing, please answer these questions.",
        "toast_item_1": "I understand what the system should do",
        "toast_item_2": "I understand the limitations of the system",
        "toast_item_3": "I understand the capabilities of the system",
        "toast_item_4": "I understand how the system executes tasks",
        "toast_item_5": "The system helps me achieve my goals",
        "toast_item_6": "The system performs consistently",
        "toast_item_7": "The system performs the way it should",
        "toast_item_8": "I am rarely surprised by how the system responds",
        "toast_item_9": "I feel comfortable relying on the information provided by the system",
        "toast_submit": "Submit and continue",
        "toast_thanks": "Thank you! Continue with the next block of scenarios.",
        "toast_study_complete": "You have completed all scenarios. Thank you for participating!",
        # NASA-TLX questionnaire
        "tlx_title": "Perceived workload",
        "tlx_subtitle": "Indicate the level for each dimension (0 = very low, 100 = very high)",
        "tlx_mental": "Mental demand",
        "tlx_mental_desc": "How mentally demanding was the task?",
        "tlx_physical": "Physical demand",
        "tlx_physical_desc": "How physically demanding was the task?",
        "tlx_temporal": "Temporal demand",
        "tlx_temporal_desc": "How much time pressure did you feel?",
        "tlx_performance": "Perceived performance",
        "tlx_performance_desc": "How satisfied are you with how it went?",
        "tlx_performance_low": "perfect",
        "tlx_performance_high": "poor",
        "tlx_effort": "Effort",
        "tlx_effort_desc": "How much effort did you have to put in?",
        "tlx_frustration": "Frustration",
        "tlx_frustration_desc": "How frustrated or stressed did you feel?",
        "tlx_low": "very low",
        "tlx_high": "very high",
        # SUS questionnaire
        "sus_title": "System usability",
        "sus_subtitle": "Indicate how much you agree with each statement (1 = strongly disagree, 5 = strongly agree)",
        "sus_item_1": "I think that I would like to use this system frequently",
        "sus_item_2": "I found the system unnecessarily complex",
        "sus_item_3": "I thought the system was easy to use",
        "sus_item_4": "I think that I would need the support of a technical person to be able to use this system",
        "sus_item_5": "I found the various functions in this system were well integrated",
        "sus_item_6": "I thought there was too much inconsistency in this system",
        "sus_item_7": "I would imagine that most people would learn to use this system very quickly",
        "sus_item_8": "I found the system very cumbersome to use",
        "sus_item_9": "I felt very confident using the system",
        "sus_item_10": "I needed to learn a lot of things before I could get going with this system",
        "sus_submit": "Submit final questionnaire",
        "sus_thanks": "Thank you for completing the study!",
        "sus_disagree": "strongly disagree",
        "sus_agree": "strongly agree",
        "questionnaire_submit": "Submit and continue",
        "toast_block_label": "Block",
    },
}

def U(key: str) -> str:
    """UI label translation."""
    return _UI.get(lang, _UI["en"]).get(key, key)

# ============================================================
# SCENARIO LIST — ordered by assignment (block 1 first, then block 2)
# ============================================================

_raw_scenarios = NON_EXP if user_type == "non_expert" else EXP

# Reorder scenarios to match the participant's assignment order (block 1 → block 2)
_assignment = st.session_state.get("scenario_assignment", [])
if _assignment:
    _assignment_order = [a["scenario_code"] for a in sorted(_assignment, key=lambda a: a.get("index", 0))]
    _sc_by_code = {sc["code"]: sc for sc in _raw_scenarios}
    SCENARIOS = [_sc_by_code[code] for code in _assignment_order if code in _sc_by_code]
    # Fallback: add any scenarios not in assignment (shouldn't happen)
    _assigned_codes = set(_assignment_order)
    for sc in _raw_scenarios:
        if sc["code"] not in _assigned_codes:
            SCENARIOS.append(sc)
else:
    # Sort by block (1 first, then 2), then by intra-block order (simple→medium→complex)
    SCENARIOS = sorted(_raw_scenarios, key=lambda s: (s.get("assigned_block", 1), s.get("block_order", 0)))

num_scenarios = len(SCENARIOS)

if "scenario_index" not in st.session_state:
    # Auto-resume: find the first incomplete scenario
    _init_progress = get_participant_progress(user_id)
    _init_done = {r["scenario_code"] for r in _init_progress.get("completed_scenarios", [])}
    _resume_idx = 0
    for _ri, _rs in enumerate(SCENARIOS):
        if _rs["code"] not in _init_done:
            _resume_idx = _ri
            break
    else:
        _resume_idx = num_scenarios - 1  # all done, show last
    st.session_state["scenario_index"] = _resume_idx

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
# SCENARIO + CATALOG + FIELD DATA
# ============================================================

raw_idx = st.session_state.get("scenario_index", 0)
safe_idx = max(0, min(raw_idx, num_scenarios - 1))
idx = safe_idx

# --- Completed scenarios set (from DB) ---
_progress = get_participant_progress(user_id)
_completed_codes = {r["scenario_code"] for r in _progress.get("completed_scenarios", [])}
_n_done = len(_completed_codes & {sc["code"] for sc in SCENARIOS})

# --- If study fully done (all scenarios + SUS for both blocks submitted), go to summary ---
if _n_done >= num_scenarios and not st.session_state.get("_show_toast_for_block") and not st.session_state.get("_show_sus"):
    _existing_sus_all = get_sus_responses(user_id)
    _sus_blocks_done = {r["block"] for r in _existing_sus_all}
    if {1, 2}.issubset(_sus_blocks_done):
        st.switch_page("Home.py")

# --- Enriched navigation bar ---
_cur_sc = SCENARIOS[idx]
_cur_block = _cur_sc.get("assigned_block", 1)
_cur_tag = _cur_sc.get("complexity_class", _cur_sc.get("complexity_tag", "C1"))
_tag_css = {"C1": "sc-tag-c1", "C2": "sc-tag-c2", "C3": "sc-tag-c3"}.get(_cur_tag, "sc-tag-c1")
_tag_labels = {"C1": ("Semplice", "Simple"), "C2": ("Medio", "Medium"), "C3": ("Complesso", "Complex")}
_tag_lbl = _tag_labels.get(_cur_tag, ("?", "?"))[0 if lang == "it" else 1]
_block_lbl = f"Blocco {_cur_block}" if lang == "it" else f"Block {_cur_block}"
_pct = int((_n_done / num_scenarios) * 100) if num_scenarios else 0

_nav_html = '<div class="sc-nav"><div class="sc-nav-left"><div class="sc-nav-dots">'
for _si, _sc in enumerate(SCENARIOS):
    _cls = "sc-dot"
    if _si == idx:
        _cls += " active"
    if _sc["code"] in _completed_codes:
        _cls += " done"
    _check = "\u2713" if _sc["code"] in _completed_codes else str(_si + 1)
    _nav_html += f'<span class="{_cls}">{_check}</span>'
_nav_html += '</div></div>'
_nav_html += '<div class="sc-nav-sep"></div>'
_nav_html += (
    f'<div class="sc-nav-center">'
    f'<span class="sc-nav-title">{T(_cur_sc, "title")}</span>'
    f'</div>'
)
_nav_html += (
    f'<div class="sc-nav-right">'
    f'<span class="sc-nav-progress">'
    f'{U("nav_progress").format(done=_n_done, total=num_scenarios)}'
    f'</span>'
    f'<div class="sc-nav-bar-track"><div class="sc-nav-bar-fill" style="width:{_pct}%"></div></div>'
    f'</div>'
)
_nav_html += '</div>'
st.markdown(_nav_html, unsafe_allow_html=True)

st.session_state["scenario_index"] = idx
SC = SCENARIOS[idx]

# Determine condition for current scenario (within-subjects: varies per block)
_current_condition = _get_condition_for_scenario(SC["code"])
_current_block = _get_block_for_scenario(SC["code"])

# ============================================================
# BLOCK-END INTERSTITIAL — NASA-TLX + TOAST (between blocks)
# ============================================================

_toast_block = st.session_state.get("_show_toast_for_block")
# Fallback: if TOAST+TLX saved for a block but SUS missing, re-show full questionnaire
if _toast_block is None:
    _existing_sus_list = get_sus_responses(user_id)
    _sus_blocks_done = {r["block"] for r in _existing_sus_list}
    _existing_toast = get_toast_responses(user_id)
    _toast_blocks_done = {r["block"] for r in _existing_toast}
    for _b in [1, 2]:
        if _b in _toast_blocks_done and _b not in _sus_blocks_done:
            _toast_block = _b
            st.session_state["_show_toast_for_block"] = _b
            st.session_state["_toast_condition"] = next(
                (r["condition"] for r in _existing_toast if r["block"] == _b), "A"
            )
            break

if _toast_block is not None:
    _toast_cond = st.session_state.get("_toast_condition", "A")
    _is_last_block = (_toast_block == 2)

    # Open centered wrapper
    st.markdown('<div class="q-page">', unsafe_allow_html=True)

    # ---- Header card ----
    _q_header_msg = (
        U("toast_thanks").replace("!", ".") if _toast_block == 1
        else U("toast_study_complete").split(".")[0] + "."
    )
    st.markdown(
        '<div style="border:2px solid #3b82f6;border-radius:14px;'
        'padding:28px 32px;background:#f0f7ff;margin:40px 0 24px;">'
        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">'
        '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" '
        'fill="none" stroke="#3b82f6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/>'
        '<path d="M12 8v4"/><path d="M12 16h.01"/></svg>'
        '<span style="font-size:1.25rem;font-weight:700;color:#1e40af;">'
        f'{U("toast_block_done").format(n=_toast_block)}</span>'
        '</div>'
        f'<p style="font-size:0.95rem;color:#475569;margin:0;">{_q_header_msg}</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ================================================================
    # SECTION 1/3: TOAST — 9 items, Likert 1-7
    # ================================================================
    st.markdown(
        '<div class="q-step">'
        '<span class="q-step-num" style="background:#3b82f6;">1</span>'
        f'<span class="q-step-label" style="color:#1e40af;">{U("toast_title")}</span>'
        '</div>'
        f'<p style="font-size:0.9rem;color:#6b7280;font-style:italic;margin:0 0 12px;">'
        f'{U("toast_subtitle")}</p>',
        unsafe_allow_html=True,
    )

    _toast_values = []
    _likert_options = ["1", "2", "3", "4", "5", "6", "7"]

    # Understanding items (1-4)
    st.markdown(
        '<p style="font-size:0.88rem;font-weight:600;color:#1e40af;'
        'text-transform:uppercase;letter-spacing:0.04em;margin:16px 0 4px;">'
        'System Understanding</p>',
        unsafe_allow_html=True,
    )
    for i in range(1, 5):
        val = st.radio(
            U(f"toast_item_{i}"),
            _likert_options, index=3, horizontal=True,
            key=f"toast_q{i}_block{_toast_block}",
        )
        _toast_values.append(int(val))

    # Performance items (5-9)
    st.markdown(
        '<p style="font-size:0.88rem;font-weight:600;color:#1e40af;'
        'text-transform:uppercase;letter-spacing:0.04em;margin:16px 0 4px;">'
        'System Performance</p>',
        unsafe_allow_html=True,
    )
    for i in range(5, 10):
        val = st.radio(
            U(f"toast_item_{i}"),
            _likert_options, index=3, horizontal=True,
            key=f"toast_q{i}_block{_toast_block}",
        )
        _toast_values.append(int(val))

    # ================================================================
    # SECTION 2/3: NASA-TLX — 6 subscales, 0-100
    # ================================================================
    st.markdown(
        '<div class="q-step">'
        '<span class="q-step-num" style="background:#6366f1;">2</span>'
        f'<span class="q-step-label" style="color:#312e81;">{U("tlx_title")}</span>'
        '</div>'
        f'<p style="font-size:0.9rem;color:#6b7280;font-style:italic;margin:0 0 12px;">'
        f'{U("tlx_subtitle")}</p>',
        unsafe_allow_html=True,
    )

    _tlx_subscales = [
        ("mental",    "tlx_mental",    "tlx_mental_desc"),
        ("physical",  "tlx_physical",  "tlx_physical_desc"),
        ("temporal",  "tlx_temporal",  "tlx_temporal_desc"),
        ("performance", "tlx_performance", "tlx_performance_desc"),
        ("effort",    "tlx_effort",    "tlx_effort_desc"),
        ("frustration", "tlx_frustration", "tlx_frustration_desc"),
    ]
    _tlx_values = []
    for _tlx_key, _tlx_label_key, _tlx_desc_key in _tlx_subscales:
        if _tlx_key == "performance":
            _lo = U("tlx_performance_low")
            _hi = U("tlx_performance_high")
        else:
            _lo = U("tlx_low")
            _hi = U("tlx_high")
        _label = f"{U(_tlx_label_key)} — {U(_tlx_desc_key)}"
        _val = st.slider(
            _label,
            min_value=0, max_value=100, value=50, step=5,
            key=f"tlx_{_tlx_key}_block{_toast_block}",
            help=f"{_lo} (0) ← → {_hi} (100)",
        )
        _tlx_values.append(_val)

    # ================================================================
    # SECTION 3/3: SUS — 10 items, 1-5
    # ================================================================
    st.markdown(
        '<div class="q-step">'
        '<span class="q-step-num" style="background:#10b981;">3</span>'
        f'<span class="q-step-label" style="color:#065f46;">{U("sus_title")}</span>'
        '</div>'
        f'<p style="font-size:0.9rem;color:#6b7280;font-style:italic;margin:0 0 12px;">'
        f'{U("sus_subtitle")}</p>',
        unsafe_allow_html=True,
    )

    _sus_values = []
    for i in range(1, 11):
        _val = st.slider(
            U(f"sus_item_{i}"),
            min_value=1, max_value=5, value=3,
            key=f"sus_q{i}_block{_toast_block}",
            help=f"{U('sus_disagree')} (1) — {U('sus_agree')} (5)",
        )
        _sus_values.append(_val)

    # Close wrapper
    st.markdown('</div>', unsafe_allow_html=True)

    # ---- Single submit for all three ----
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    _q_btn_label = U("sus_submit") if _is_last_block else U("questionnaire_submit")
    if st.button(_q_btn_label, type="primary", width="stretch",
                 key=f"questionnaire_submit_{_toast_block}"):
        # Save TOAST
        save_toast_response(
            participant_id=user_id,
            block=_toast_block,
            condition=_toast_cond,
            items=_toast_values,
        )
        # Save TLX
        save_tlx_response(
            participant_id=user_id,
            block=_toast_block,
            condition=_toast_cond,
            subscales=_tlx_values,
        )
        # Save SUS
        save_sus_response(
            participant_id=user_id,
            items=_sus_values,
            block=_toast_block,
            condition=_toast_cond,
        )
        st.session_state.pop("_show_toast_for_block", None)
        st.session_state.pop("_toast_condition", None)

        if _is_last_block:
            st.switch_page("Home.py")
        else:
            # Advance to first scenario of block 2
            _block2_scenarios = [e for e in _scenario_assignment if e.get("block") == 2]
            if _block2_scenarios:
                _b2_code = _block2_scenarios[0]["scenario_code"]
                for _si, _sc in enumerate(SCENARIOS):
                    if _sc["code"] == _b2_code:
                        st.session_state["scenario_index"] = _si
                        break
            st.rerun()

    st.stop()  # Don't render scenarios while questionnaire is showing

# ---- Catalog (pre-enriched, no runtime translation needed) ----
CAT = SC.get("catalog", {}).get(lang) or SC.get("catalog", {}).get("en", {})

SERVICE_INDEX = {s["service_slug"]: s for s in CAT.get("services", [])}
TRIGGER_INDEX = {t["api_endpoint_slug"]: t for t in CAT.get("triggers", [])}
ACTION_INDEX  = {a["api_endpoint_slug"]: a for a in CAT.get("actions", [])}

# ---- Collect field data ----
st.session_state.setdefault("selected_ingredients", {})
sel_ing = st.session_state["selected_ingredients"].setdefault(SC["code"], set())

_all_ing_keys = []
_ing_items = []
_trig_services = []
_seen_trig_svc = set()
for trig_api in SC["trigger_apis"]:
    trig = TRIGGER_INDEX.get(trig_api)
    if trig:
        _tsvc = SERVICE_INDEX.get(trig.get("service_slug", ""), {})
        _tslug = trig.get("service_slug", "")
        if _tslug and _tslug not in _seen_trig_svc:
            _seen_trig_svc.add(_tslug)
            _trig_services.append({
                "name": _tsvc.get("name", _tslug),
                "image_url": _tsvc.get("image_url", ""),
                "brand_color": _tsvc.get("brand_color", "#333"),
            })
        for ing in trig.get("ingredients", []):
            fck = ing.get("filter_code_key", "")
            if fck:
                _all_ing_keys.append(fck)
                _ing_desc = ing.get("description", "") or ""
                if _ing_desc.lower() == "none":
                    _ing_desc = ""
                # Fallback: use trigger context if no description
                if not _ing_desc:
                    _ing_desc = f"Ingredient from {trig.get('name', 'trigger')}"
                _ing_items.append({
                    "key": fck,
                    "name": ing.get("name", fck),
                    "desc": _ing_desc,
                    "trigger_name": trig.get("name", ""),
                    "svc_name": _tsvc.get("name", ""),
                })
st.session_state["_all_ing_keys"] = _all_ing_keys

st.session_state.setdefault("selected_setters", {})
sel_set = st.session_state["selected_setters"].setdefault(SC["code"], set())

_all_set_methods = []
_set_items = []
_skip_targets = []
_act_services = []
_seen_act_svc = set()
for act_api in SC["action_apis"]:
    act = ACTION_INDEX.get(act_api)
    if not act:
        continue
    ns = act.get("namespace", "")
    _asvc = SERVICE_INDEX.get(act.get("service_slug", ""), {})
    _aslug = act.get("service_slug", "")
    if _aslug and _aslug not in _seen_act_svc:
        _seen_act_svc.add(_aslug)
        _act_services.append({
            "name": _asvc.get("name", _aslug),
            "image_url": _asvc.get("image_url", ""),
            "brand_color": _asvc.get("brand_color", "#333"),
        })
    for fld in act.get("fields", []):
        method = fld.get("filter_code_method")
        if method:
            clean_method = re.sub(r'\(.*\)', '()', method)
        elif fld.get("slug") and ns:
            s = fld["slug"]
            clean_method = f"{ns}.set{s[0].upper()}{s[1:]}()"
        else:
            continue
        _all_set_methods.append(clean_method)
        _set_desc = fld.get("helper_text", "") or ""
        if _set_desc.lower() == "none":
            _set_desc = ""
        # Fallback: use action context if no description
        if not _set_desc:
            _set_desc = f"Field in {act.get('name', 'action')}"
        _set_items.append({
            "key": clean_method,
            "name": fld.get("label", fld.get("slug", clean_method)),
            "desc": _set_desc,
            "action_name": act.get("name", ""),
            "svc_name": _asvc.get("name", ""),
        })
    name = act.get("name", ns)
    skip_method = act.get("skip_method", "")
    skip_call = re.sub(r'\(.*\)', '()', skip_method) if skip_method else f"{ns}.skip()"
    if ns:
        _skip_targets.append((ns, name, skip_call))
st.session_state["_all_set_methods"] = _all_set_methods


# ============================================================
# MAIN — Header
# ============================================================

_loading_banner.empty()
st.session_state["_studio_initialized"] = True

# ============================================================
# TUTORIAL OVERLAY — first-time guided walkthrough
# ============================================================

def _inject_tutorial_mocks(include_eval=False):
    """Add mock chat messages so tutorial steps 4-5 have content to show."""
    _chat = st.session_state.setdefault("studio_chat", [])
    if any(m.get("_tutorial_mock") for m in _chat):
        # If eval mocks needed but not yet set, add them
        if include_eval and not st.session_state.get("_tutorial_mock_code"):
            st.session_state["latest_code"] = "// Tutorial example\nFilter.apply();"
            st.session_state["_tutorial_mock_code"] = True
        return
    _chat.append({
        "role": "user", "type": "intent",
        "text": U("tutorial_mock_user"), "_tutorial_mock": True,
    })
    _chat.append({
        "role": "assistant", "type": "followup",
        "text": U("tutorial_mock_assistant"),
        "suggested_intent": "", "_tutorial_mock": True,
    })
    if include_eval:
        st.session_state["latest_code"] = "// Tutorial example\nFilter.apply();"
        st.session_state["_tutorial_mock_code"] = True


def _remove_tutorial_mocks():
    """Remove mock chat messages and mock code injected for the tutorial."""
    _chat = st.session_state.get("studio_chat", [])
    st.session_state["studio_chat"] = [m for m in _chat if not m.get("_tutorial_mock")]
    if st.session_state.get("_tutorial_mock_code"):
        st.session_state.pop("latest_code", None)
        st.session_state.pop("_tutorial_mock_code", None)


if st.session_state.get("tutorial_active", False):
    _tut_step = st.session_state.get("tutorial_step", 0)

    # Inject/remove mock messages depending on which step we're at
    if _tut_step >= 3:
        _inject_tutorial_mocks(include_eval=(_tut_step >= 4))
    else:
        _remove_tutorial_mocks()

    _tut_type_key = user_type.replace("_", "")  # "non_expert" -> "nonexpert"
    _tut_results_body = U(f"tutorial_results_body_{_tut_type_key}")
    _tut_eval_body = U(f"tutorial_eval_body_{_tut_type_key}")
    _tut_steps = [
        {"selector": ".ctx-card", "placement": "bottom",
         "title": U("tutorial_scenario_title"), "body": U("tutorial_scenario_body")},
        {"selector": "#sfd-stack", "placement": "right",
         "title": U("tutorial_fields_title"), "body": U("tutorial_fields_body")},
        {"selector": ".st-key-chat_section", "placement": "top",
         "title": U("tutorial_chat_title"), "body": U("tutorial_chat_body")},
        {"selector": ".st-key-chat_section", "placement": "top",
         "title": U("tutorial_results_title"), "body": _tut_results_body},
        {"selector": ".st-key-eval_section", "placement": "top",
         "title": U("tutorial_eval_title"), "body": _tut_eval_body},
    ]
    # Use generation-based key so each activation gets a fresh component (no stale values)
    _tut_key = f"tutorial_overlay_{st.session_state.get('_tutorial_key_gen', 0)}"
    _tut_result = _tutorial_overlay(
        steps=_tut_steps,
        current_step=_tut_step,
        active=True,
        lbl_next=U("tutorial_btn_next"),
        lbl_back=U("tutorial_btn_back"),
        lbl_skip=U("tutorial_btn_skip"),
        lbl_done=U("tutorial_btn_done"),
        key=_tut_key,
        default=None,
    )
    if _tut_result is not None:
        _tut_action = _tut_result.get("action", "")
        _tut_from = _tut_result.get("step", -1)
        # Guard: only process if the action's origin step matches current step
        # (prevents infinite rerun when the component's stored value persists)
        if _tut_from == _tut_step:
            if _tut_action in ("done", "skip"):
                _remove_tutorial_mocks()
                st.session_state["tutorial_active"] = False
                st.session_state["_tutorial_completed"] = True
                st.session_state["_tutorial_needs_cleanup"] = True
                st.session_state.pop("tutorial_step", None)
                st.rerun()
            elif _tut_action == "next":
                st.session_state["tutorial_step"] = min(_tut_step + 1, len(_tut_steps) - 1)
                st.rerun()
            elif _tut_action == "back":
                st.session_state["tutorial_step"] = max(_tut_step - 1, 0)
                st.rerun()
elif st.session_state.get("_tutorial_needs_cleanup", False):
    # One-shot cleanup render: send active=False so the JS removes DOM elements
    _cleanup_key = f"tutorial_overlay_{st.session_state.get('_tutorial_key_gen', 0)}"
    _tutorial_overlay(
        active=False, steps=[], current_step=0,
        key=_cleanup_key, default=None,
    )
    st.session_state["_tutorial_needs_cleanup"] = False

# Start scenario session in DB (safe — won't overwrite completed scenarios)
if SC["code"] not in _completed_codes:
    start_scenario_session(
        participant_id=user_id,
        scenario_code=SC["code"],
        condition=_current_condition,
        complexity_class=SC.get("complexity_tag", ""),
        scenario_index=st.session_state.get("scenario_index", 0),
    )

# --- Sticky user badge (top-left, minimal) ---
_logout_tip = "Esci" if lang == "it" else "Log out"
_logout_svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>'
# Badge via st.markdown (visual only, no onclick — Streamlit strips JS handlers)
st.markdown(
    f'<div class="user-badge-sticky">'
    f'<span class="uid">{user_id}</span>'
    f'<span class="sep">|</span>'
    f'<span class="logout-link" id="badge-logout" title="{_logout_tip}">'
    f'{_logout_svg}</span>'
    f'</div>',
    unsafe_allow_html=True,
)
# Inject click handler via st.components.v1.html (runs in iframe, accesses parent DOM)
import streamlit.components.v1 as _cmp
_cmp.html('''<script>
(function(){
    var doc = window.parent.document;
    var link = doc.getElementById("badge-logout");
    if (link) {
        link.style.cursor = "pointer";
        link.onclick = function(){
            var btn = doc.querySelector('.st-key-studio_logout_btn button');
            if (btn) btn.click();
        };
    }
})();
</script>''', height=0)
# Hidden real button for Streamlit callback
if st.button("logout", key="studio_logout_btn"):
    _emit_dom_cleanup()
    _token = st.session_state.get("_session_token", "")
    if _token:
        invalidate_session_token(_token)
    st.query_params.clear()
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.switch_page("Home.py")

st.title(T(SC, "title"))

# ============================================================
# MAIN — Context & Intent Examples
# ============================================================

ss = st.session_state

_bg_text = T(SC, "background")
_ifthen_text = T(SC, "if_then")
_examples = SC.get("intent_examples_it" if lang == "it" else "intent_examples_en", [])
if not _examples:
    _examples = SC.get("intent_examples_it", [])

# Context card
_ctx_html = '<div class="ctx-card">'
_ctx_html += f'<div class="ctx-label">{U("context")}</div>'
_ctx_html += f'<div class="ctx-text">{_bg_text}</div>'
if _ifthen_text:
    _ctx_html += f'<div class="ctx-ifthen">{_ifthen_text}</div>'
if _examples:
    _ex_label = U("intent_examples")
    _ctx_html += f'<div class="ctx-label" style="margin-top:10px;">{_ex_label}</div>'
    _ctx_html += '<div class="ctx-examples">'
    for _ex in _examples:
        _ctx_html += f'<span class="ctx-ex-chip">&ldquo;{_ex}&rdquo;</span>'
    _ctx_html += '</div>'
_ctx_html += '</div>'
st.markdown(_ctx_html, unsafe_allow_html=True)

# ============================================================
# MAIN — Field Selection (G1 mini-card layout)
# ============================================================

def _svc_icons_html(services):
    """Build inline HTML for service icons."""
    html = ""
    for s in services:
        html += (
            f'<div style="display:inline-flex;align-items:center;gap:5px;margin-right:6px;">'
            f'<div style="background:{s["brand_color"]};border-radius:8px;padding:4px;'
            f'width:28px;height:28px;display:inline-flex;align-items:center;'
            f'justify-content:center;flex-shrink:0;">'
            f'<img src="{s["image_url"]}" width="20" height="20" '
            f'style="object-fit:contain;"></div>'
            f'<span class="g2-svc-name">{s["name"]}</span></div>'
        )
    return html

# -- Trigger ingredients (state + chip data) --
if _ing_items:
    _sel_key_ing = f"chip_sel_ing_{SC['code']}"
    if _sel_key_ing not in ss:
        ss[_sel_key_ing] = list(sel_ing)
    _chip_items_ing = [
        {"key": it["key"], "name": it["name"], "desc": it.get("desc", "")}
        for it in _ing_items
    ]
else:
    _sel_key_ing = None
    _chip_items_ing = []

# -- Action setters (state + chip data) --
if _set_items:
    _sel_key_set = f"chip_sel_set_{SC['code']}"
    if _sel_key_set not in ss:
        ss[_sel_key_set] = list(sel_set)
    _chip_items_set = [
        {"key": it["key"], "name": it["name"], "desc": it.get("desc", "")}
        for it in _set_items
    ]
else:
    _sel_key_set = None
    _chip_items_set = []

# --- Sticky field drawers (lateral, stacked on the left side) ---
# Rendered early so sel_ing / sel_set are updated before chip summary + prompt building.
# The iframes are hidden via CSS (display:none); the drawer UI lives in the parent DOM.
_drawer_close_nonce = ss.get("_drawer_close_nonce", 0)

# SVG icons for drawer tabs
_ICON_TRIGGER = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" '
    'fill="none" stroke="#1e40af" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>'
)
_ICON_ACTION = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" '
    'fill="none" stroke="#92400e" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/>'
    '<path d="m9 12 2 2 4-4"/></svg>'
)

_drawer_auto_open = (
    ss.get("tutorial_active", False) and ss.get("tutorial_step", 0) == 1
)

if _chip_items_ing and _sel_key_ing is not None:
    _new_sel_ing = _field_drawer(
        items=_chip_items_ing,
        selected=ss[_sel_key_ing],
        group_type="trigger",
        label=U("field_badge_trigger"),
        icon_svg=_ICON_TRIGGER,
        bottom_offset=42,
        all_btn_label=U("field_select_all"),
        none_btn_label=U("field_deselect"),
        close_nonce=_drawer_close_nonce,
        auto_open=_drawer_auto_open,
        key=f"drawer_ing_{SC['code']}",
        default=ss[_sel_key_ing],
    )
    if _new_sel_ing is not None:
        ss[_sel_key_ing] = list(_new_sel_ing)
    sel_ing.clear()
    sel_ing.update(ss[_sel_key_ing])

if _chip_items_set and _sel_key_set is not None:
    _new_sel_set = _field_drawer(
        items=_chip_items_set,
        selected=ss[_sel_key_set],
        group_type="action",
        label=U("field_badge_action"),
        icon_svg=_ICON_ACTION,
        bottom_offset=0,
        all_btn_label=U("field_select_all"),
        none_btn_label=U("field_deselect"),
        close_nonce=_drawer_close_nonce,
        auto_open=_drawer_auto_open,
        key=f"drawer_set_{SC['code']}",
        default=ss[_sel_key_set],
    )
    if _new_sel_set is not None:
        ss[_sel_key_set] = list(_new_sel_set)
    sel_set.clear()
    sel_set.update(ss[_sel_key_set])

# ============================================================
# HELPERS — chat rendering & prompt building
# ============================================================
ss.setdefault("studio_chat", [])
ss.setdefault("orchestrator_messages", [])

# --- Restore state from DB on page reload ---
ss.setdefault("_scenario_attempt_num", {})
ss.setdefault("attempt_count", {})
_sc_already_completed = SC["code"] in {
    r["scenario_code"] for r in get_participant_progress(user_id).get("completed_scenarios", [])
}
if not ss["studio_chat"] and SC["code"] not in ss.get("_scenario_restored", set()):
    _db_attempts = get_scenario_attempt_count(user_id, SC["code"])
    if _db_attempts > 0:
        ss["_scenario_attempt_num"][SC["code"]] = _db_attempts
        ss["attempt_count"][SC["code"]] = _db_attempts
        # Restore chat from DB snapshot
        if not _sc_already_completed:
            _saved_chat = load_chat_snapshot(user_id, SC["code"])
            if _saved_chat:
                ss["studio_chat"] = _saved_chat
                # Restore latest_code from last generation in chat
                for _rm in reversed(_saved_chat):
                    if _rm.get("type") == "generation" and _rm.get("data", {}).get("code"):
                        ss["latest_code"] = _rm["data"]["code"]
                        break
            elif not ss.get("latest_code"):
                _db_code = get_last_generated_code(user_id, SC["code"])
                if _db_code:
                    ss["latest_code"] = _db_code
    ss.setdefault("_scenario_restored", set()).add(SC["code"])


def _serialize_chat_for_db(chat: list) -> list:
    """Convert studio_chat to a JSON-serializable list (strip non-serializable objects)."""
    out = []
    for msg in chat:
        if msg.get("_tutorial_mock"):
            continue
        m = dict(msg)
        if m.get("type") == "generation" and "data" in m:
            d = dict(m["data"])
            # L1Report is not serializable — keep only l1_html (string)
            d.pop("l1_report", None)
            # conditions may have non-serializable items
            if "conditions" in d:
                try:
                    json.dumps(d["conditions"])
                except (TypeError, ValueError):
                    d["conditions"] = {}
            m["data"] = d
        out.append(m)
    return out


def _save_chat_to_db():
    """Serialize and save current chat to DB for crash recovery."""
    chat = ss.get("studio_chat", [])
    if not chat:
        return
    serializable = _serialize_chat_for_db(chat)
    save_chat_snapshot(user_id, SC["code"], serializable)


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


def _build_conditions_data(code: str, l1: L1Report, api_fixes=None) -> dict:
    """Pre-build behavior flow + semantic blocks data for embedding in chat."""
    result = {"behavior_flow_html": None, "api_warning_html": "", "l1_warnings_html": ""}
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

    # Inject api_fixes as extra getter/setter labels so invalid names get
    # replaced by their corrected human-readable label in the behavior flow
    if api_fixes:
        gl = display_labels.setdefault("getter_labels", {})
        sl = display_labels.setdefault("setter_labels", {})
        for fix in api_fixes:
            inv = fix.get("invalid", "")
            label = fix.get("label") or fix.get("suggestion", "")
            if inv and label:
                if fix.get("type") == "getter":
                    gl.setdefault(inv, label)
                elif fix.get("type") == "setter":
                    sl.setdefault(inv, label)

    # Behavior flow (hybrid F-style visual) — used by both expert and non-expert
    if l1.outcomes_raw:
        result["behavior_flow_html"] = render_behavior_flow_html(
            l1.outcomes_raw, lang=lang, user_type=user_type,
            display_labels=display_labels,
        )

    # API warning block (invalid getters/setters)
    result["api_warning_html"] = render_api_warning_html(
        api_fixes or [], lang=lang, user_type=user_type,
    )

    # L1 warnings block (uncovered actions, missing setters, etc.)
    if l1.warnings:
        result["l1_warnings_html"] = _build_l1_warnings_html(l1.warnings, display_labels)

    return result


def _build_l1_warnings_html(warnings: list, display_labels: dict = None) -> str:
    """Render L1 warnings (e.g., uncovered actions) as a visual block.

    Translates technical API names to human-readable labels using display_labels.
    Works for both expert and non-expert views.
    """
    if not warnings:
        return ""

    _warn_title = {
        "it": "Avvisi",
        "en": "Warnings",
    }

    getter_labels = (display_labels or {}).get("getter_labels", {})
    setter_labels = (display_labels or {}).get("setter_labels", {})
    all_labels = {**getter_labels, **setter_labels}

    items = []
    for w in warnings:
        if not isinstance(w, str):
            continue
        text = w
        # Replace technical API names with human-readable labels
        for api_name, label in all_labels.items():
            if api_name in text:
                if user_type == "non_expert":
                    text = text.replace(api_name, f"<b>{label}</b>")
                else:
                    text = text.replace(api_name, f"<b>{label}</b> (<code>{api_name}</code>)")
        # Also clean up list formatting: ['A', 'B'] → A, B
        text = re.sub(r"\['([^']*?)'\]", r"\1", text)
        text = re.sub(r"'([^']*?)'", r"<b>\1</b>", text)
        items.append(text)

    if not items:
        return ""

    title = _warn_title.get(lang, _warn_title["en"])
    rows = "".join(
        f'<div style="padding:3px 0;font-size:0.88em;color:#92400e;line-height:1.5;">'
        f'&#9888;&#65039; {item}</div>'
        for item in items
    )

    return (
        f'<div style="border:1px solid #fbbf24;border-radius:10px;overflow:hidden;'
        f'margin:8px 0;">'
        f'<div style="background:#fffbeb;padding:8px 14px;font-weight:700;'
        f'font-size:0.92em;color:#b45309;">{title}</div>'
        f'<div style="padding:8px 14px;">{rows}</div></div>'
    )


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
        return "", None, {"behavior_flow_html": None}, []

    # 2. Log attempt — only count as new attempt if intent or fields changed
    _avail_ing = ss.get("_all_ing_keys", [])
    _avail_set = ss.get("_all_set_methods", [])
    if not sel_ing and not sel_set:
        _sel_strategy = "none"
    elif set(sel_ing) >= set(_avail_ing) and set(sel_set) >= set(_avail_set):
        _sel_strategy = "all"
    else:
        _sel_strategy = "selective"

    _cur_fingerprint = (intent.strip(), tuple(sorted(sel_ing)), tuple(sorted(sel_set)))
    _prev_fingerprint = ss.get("_last_gen_fingerprint", {}).get(SC["code"])

    ss.setdefault("attempt_count", {})
    if _cur_fingerprint != _prev_fingerprint:
        # New attempt: prompt or fields changed
        count = ss["attempt_count"].get(SC["code"], 0) + 1
        ss["attempt_count"][SC["code"]] = count
        # Update the scenario attempt counter immediately
        ss.setdefault("_scenario_attempt_num", {})
        ss["_scenario_attempt_num"][SC["code"]] = count
    else:
        # Same prompt + fields → regeneration, keep current count
        count = ss["attempt_count"].get(SC["code"], 1)

    # Store fingerprint for next comparison
    ss.setdefault("_last_gen_fingerprint", {})[SC["code"]] = _cur_fingerprint

    ss.setdefault("attempt_log", []).append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "scenario_code": SC["code"],
        "row_index": SC["row_index"],
        "attempt": count,
        "is_new_attempt": _cur_fingerprint != _prev_fingerprint,
        "user_intent": intent,
        "llm_output": code,
        "selected_ingredients": sorted(sel_ing),
        "selected_setters": sorted(sel_set),
        "available_ingredients": sorted(_avail_ing),
        "available_setters": sorted(_avail_set),
        "selection_strategy": _sel_strategy,
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
            endpoint=ORC_ENDPOINT,
            model=ORCHESTRATOR_MODEL,
        )

    # 5. Build conditions data (flowchart + blocks + API warnings)
    conditions = _build_conditions_data(code, l1, api_fixes)

    return code, l1, conditions, api_fixes


def _run_orchestrator(user_text: str):
    """Send user message to the orchestrator and update chat + session state."""
    studio_chat = ss["studio_chat"]
    logger = _get_logger()

    # Log user message
    has_gen = any(m.get("type") == "generation" for m in studio_chat)
    logger.log_user_message(user_text, "followup" if has_gen else "intent")

    # If there's already been a generation, inject a hint to force a new tool
    # call while preserving orchestrator context (so it can learn from prior
    # attempts and build improved intents).
    if has_gen:
        user_text = (
            "[SYSTEM: The user is requesting a new generation. You MUST call "
            "generate_and_validate with an improved intent that fixes the issues "
            "found in the previous attempt. Do NOT respond conversationally.]\n\n"
            + user_text
        )

    # Build API surface text for the orchestrator's system prompt
    if user_type == "non_expert":
        api_surface = build_api_surface_behavioral(
            SC["trigger_apis"], SC["action_apis"],
            TRIGGER_INDEX, ACTION_INDEX,
        )
        # Technical surface needed for non-expert B's SUGGESTED_FIELDS
        _api_surface_tech = build_api_surface_text(
            SC["trigger_apis"], SC["action_apis"],
            TRIGGER_INDEX, ACTION_INDEX,
        )
    else:
        api_surface = build_api_surface_text(
            SC["trigger_apis"], SC["action_apis"],
            TRIGGER_INDEX, ACTION_INDEX,
        )
        _api_surface_tech = ""

    # Run orchestrator turn (uses dedicated orchestrator model)
    result = run_orchestrator_turn(
        history=ss.get("orchestrator_messages", []),
        user_message=user_text,
        tool_executor=_execute_tool,
        endpoint=ORC_ENDPOINT,
        model=ORCHESTRATOR_MODEL,
        lang=lang,
        api_surface_text=api_surface,
        api_surface_technical=_api_surface_tech,
        user_type=user_type,
        condition=_current_condition,
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
                "suggested_fields": result.suggested_fields,
            },
        })
        ss["_fresh_msg_idx"] = len(studio_chat) - 1

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
            "suggested_fields": result.suggested_fields,
        })
        ss["_fresh_msg_idx"] = len(studio_chat) - 1

    # Log agent response
    logger.log_agent_response(
        text=result.assistant_text,
        tool_called=result.tool_called,
        suggested_intent=result.suggested_intent,
    )

    # Also log to DB for crash safety (include code so reload can restore eval block)
    db_log_interaction(
        participant_id=user_id,
        scenario_code=SC["code"],
        turn=logger._turn,
        elapsed_s=round(time.monotonic() - logger.session_start, 2),
        event="orchestrator_turn",
        data={
            "tool_called": result.tool_called,
            "has_suggestion": bool(result.suggested_intent),
            "suggested_fields": result.suggested_fields,
            "code": data["code"] if result.tool_called and data else None,
        },
    )

    # Save chat snapshot for reload recovery
    _save_chat_to_db()


def _render_field_suggestions(sug_fields_raw, msg_index, anim_delay, is_fresh):
    """Render suggested fields as individual selectable buttons + select-all.

    Returns True if any field was clicked (caller should st.rerun()).
    """
    if not sug_fields_raw:
        return False
    _all_keys_ing = {it["key"] for it in _chip_items_ing}
    _all_keys_set = {it["key"] for it in _chip_items_set}
    _matched_ing = [k for k in sug_fields_raw if k in _all_keys_ing]
    _matched_set = [k for k in sug_fields_raw if k in _all_keys_set]
    _matched_all = _matched_ing + _matched_set
    if not _matched_all:
        return False

    # Build field info list: (key, display_name, is_ingredient, already_selected)
    _fields_info = []
    for fk in _matched_ing:
        fn = next((it["name"] for it in _chip_items_ing if it["key"] == fk), fk)
        _fields_info.append((fk, fn, True, fk in sel_ing))
    for fk in _matched_set:
        fn = next((it["name"] for it in _chip_items_set if it["key"] == fk), fk)
        _fields_info.append((fk, fn, False, fk in sel_set))

    # Header card with chips preview
    _chips_html = ""
    for fk, fn, is_ing, already in _fields_info:
        bg = "#dbeafe" if is_ing else "#fef3c7"
        fg = "#1e40af" if is_ing else "#92400e"
        strike = "text-decoration:line-through;opacity:0.5;" if already else ""
        _chips_html += (
            f'<span style="display:inline-block;background:{bg};color:{fg};'
            f'padding:3px 10px;border-radius:12px;font-size:0.85em;font-weight:600;'
            f'margin:2px 3px;{strike}">{fn}</span>'
        )
    _card_html = (
        f'<div style="border:1px solid #e0e0e0;border-radius:8px;'
        f'padding:12px 16px;margin:8px 0;">'
        f'<strong>{U("agent_suggested_fields_label")}:</strong><br>'
        f'<div style="margin-top:6px;">{_chips_html}</div></div>'
    )
    st.markdown(
        _anim_wrap(_card_html, anim_delay, is_fresh),
        unsafe_allow_html=True,
    )

    # Individual buttons — one per field
    _not_yet = [(fk, fn, is_ing) for fk, fn, is_ing, already in _fields_info if not already]
    if _not_yet:
        _ncols = min(len(_not_yet) + 1, 4)  # +1 for "select all"
        _cols = st.columns(_ncols)
        for idx, (fk, fn, is_ing) in enumerate(_not_yet):
            with _cols[idx % _ncols]:
                if st.button(
                    f"+ {fn}",
                    key=f"sug_f_{msg_index}_{fk}",
                    width="stretch",
                ):
                    if is_ing and _sel_key_ing is not None:
                        ss[_sel_key_ing] = list(set(ss.get(_sel_key_ing, [])) | {fk})
                        sel_ing.add(fk)
                    elif _sel_key_set is not None:
                        ss[_sel_key_set] = list(set(ss.get(_sel_key_set, [])) | {fk})
                        sel_set.add(fk)
                    db_log_interaction(
                        participant_id=user_id,
                        scenario_code=SC["code"],
                        turn=len(ss.get("studio_chat", [])),
                        elapsed_s=0,
                        event="field_suggestion_accepted",
                        data=json.dumps({"field": fk}),
                    )
                    st.rerun()
        # "Select all" button (if more than one field remaining)
        if len(_not_yet) > 1:
            with _cols[len(_not_yet) % _ncols] if len(_not_yet) < _ncols else st:
                if st.button(
                    U("agent_use_fields"),
                    key=f"use_fields_{msg_index}",
                    width="stretch",
                ):
                    if _sel_key_ing is not None:
                        ss[_sel_key_ing] = list(set(ss.get(_sel_key_ing, [])) | set(_matched_ing))
                        sel_ing.clear()
                        sel_ing.update(ss[_sel_key_ing])
                    if _sel_key_set is not None:
                        ss[_sel_key_set] = list(set(ss.get(_sel_key_set, [])) | set(_matched_set))
                        sel_set.clear()
                        sel_set.update(ss[_sel_key_set])
                    db_log_interaction(
                        participant_id=user_id,
                        scenario_code=SC["code"],
                        turn=len(ss.get("studio_chat", [])),
                        elapsed_s=0,
                        event="fields_suggestion_accepted",
                        data=json.dumps({"suggested_fields": _matched_all}),
                    )
                    st.rerun()
    return False


# ============================================================
# MAIN — Chat (unified conversation with orchestrator)
# ============================================================

studio_chat = ss["studio_chat"]

# --- Chat container (bordered box with messages + input bar) ---
_chat_box = st.container(border=True, key="chat_section")

MAX_ATTEMPTS = 3
ss.setdefault("_scenario_attempt_num", {})
_attempt_num = ss["_scenario_attempt_num"].get(SC["code"], 1)
_has_gen = any(m.get("type") == "generation" for m in studio_chat)
# Also check DB: if we restored attempt_count from DB, the chat may be empty
# but attempts were already made.
_db_has_gen = ss.get("attempt_count", {}).get(SC["code"], 0) > 0
_input_disabled = (_attempt_num >= MAX_ATTEMPTS and (_has_gen or _db_has_gen))

with _chat_box:
    # --- Render all chat messages ---
    for msg_index, msg in enumerate(studio_chat):
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.markdown(msg["text"])

        elif msg["type"] == "generation":
            with st.chat_message("assistant"):
                data = msg["data"]
                _is_fresh = (msg_index == ss.get("_fresh_msg_idx", -1))

                if data.get("user_edited"):
                    st.markdown(
                        f'<div style="display:inline-block;background:#e0e7ff;color:#3730a3;'
                        f'padding:3px 10px;border-radius:12px;font-size:0.82em;'
                        f'font-weight:600;margin-bottom:8px;">'
                        f'{U("code_edited_label")}</div>',
                        unsafe_allow_html=True,
                    )

                if user_type == "non_expert":
                    # ---- NON-EXPERT: behavioral view only ----

                    # 1. Behavior flow (hybrid visual)
                    cond = data.get("conditions", {})
                    if cond.get("behavior_flow_html"):
                        st.markdown(
                            _anim_wrap(cond["behavior_flow_html"], 0.0, _is_fresh),
                            unsafe_allow_html=True,
                        )

                    # 2. API warning block (invalid getters/setters)
                    if cond.get("api_warning_html"):
                        st.markdown(
                            _anim_wrap(cond["api_warning_html"], 0.15, _is_fresh),
                            unsafe_allow_html=True,
                        )

                    # 3. Orchestrator commentary (behavioral language)
                    commentary = data.get("commentary", "")
                    if commentary:
                        st.markdown("---")
                        if _is_fresh:
                            st.write_stream(_simulated_stream(commentary))
                        else:
                            st.markdown(commentary)

                else:
                    # ---- EXPERT: full technical view ----
                    # Order: L1 card → behavior flow → API warnings → commentary → code → suggestions

                    _has_suggestions = bool(
                        data.get("suggested_intent") or data.get("suggested_fields")
                    ) and _current_condition == "B"

                    # L1 card
                    if data.get("l1_html"):
                        st.markdown(
                            _anim_wrap(data["l1_html"], 0.0, _is_fresh),
                            unsafe_allow_html=True,
                        )

                    # Embedded conditions (behavior flow)
                    cond = data.get("conditions", {})
                    if cond.get("behavior_flow_html"):
                        st.markdown(
                            _anim_wrap(cond["behavior_flow_html"], 0.15, _is_fresh),
                            unsafe_allow_html=True,
                        )

                    # API warning block (invalid getters/setters)
                    if cond.get("api_warning_html"):
                        st.markdown(
                            _anim_wrap(cond["api_warning_html"], 0.3, _is_fresh),
                            unsafe_allow_html=True,
                        )

                    # Orchestrator commentary
                    commentary = data.get("commentary", "")
                    if commentary:
                        st.markdown("---")
                        if _is_fresh:
                            st.write_stream(_simulated_stream(commentary))
                        else:
                            st.markdown(commentary)

                    # Code block (after commentary, before suggestions)
                    # — inline editable for expert
                    st.markdown("---")
                    _code_val = data.get("code", "") or ""
                    _edit_key = f"_editing_code_{msg_index}"
                    _edited_code_key = f"_edited_code_{SC['code']}"

                    # Check if user already edited this code
                    _user_edited = ss.get(_edited_code_key)
                    _display_code = _user_edited if _user_edited else _code_val

                    if ss.get(_edit_key):
                        # --- EDIT MODE ---
                        st.markdown(f"**{U('chat_code_header')}**")
                        if _has_suggestions:
                            st.caption(U("agent_code_or_suggestions"))
                        _buf_key = f"_edit_buf_{msg_index}"
                        _edited = st.text_area(
                            U("edit_code_btn"),
                            value=ss.get(_buf_key, _display_code),
                            height=250,
                            key=f"code_area_{msg_index}",
                            label_visibility="collapsed",
                        )
                        _ec1, _ec2, _ = st.columns([1, 1, 3])
                        with _ec1:
                            if st.button(
                                U("validate_edit_btn"),
                                key=f"validate_code_{msg_index}",
                                type="primary",
                            ):
                                ss[_edited_code_key] = _edited
                                ss.pop(_edit_key, None)
                                ss["_pending_code_validation"] = _edited
                                st.rerun()
                        with _ec2:
                            if st.button(
                                U("cancel_edit_btn"),
                                key=f"cancel_edit_{msg_index}",
                            ):
                                ss.pop(_edit_key, None)
                                st.rerun()
                    else:
                        # --- VIEW MODE ---
                        st.markdown(f"**{U('chat_code_header')}**")
                        if _has_suggestions:
                            st.caption(U("agent_code_or_suggestions"))
                        if _user_edited:
                            st.caption(f"_{U('code_edited_label')}_")
                        st.code(_display_code or U("no_code"), language="javascript")
                        # Edit button (only on the LATEST generation message)
                        _is_latest_gen = all(
                            m.get("type") != "generation"
                            for m in studio_chat[msg_index + 1:]
                        )
                        if _is_latest_gen and not _input_disabled:
                            if st.button(
                                U("edit_code_btn"),
                                key=f"edit_code_{msg_index}",
                            ):
                                ss[_edit_key] = True
                                ss[f"_edit_buf_{msg_index}"] = _display_code
                                st.rerun()

                # --- Suggested intent (condition B only, not at max attempts) ---
                if _current_condition == "B" and not _input_disabled:
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
                        _suggestion_html = (
                            f'<div style="border:1px solid #e0e0e0;border-radius:8px;'
                            f'padding:12px 16px;margin:8px 0;line-height:1.8;'
                            f'font-size:0.95em;">'
                            f'<strong>{U("agent_try")}:</strong><br>{diff_html}</div>'
                        )
                        st.markdown(
                            _anim_wrap(_suggestion_html, 0.6, _is_fresh),
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            U("agent_use_suggestion"),
                            key=f"use_suggestion_{msg_index}",
                        ):
                            _get_logger().log_suggestion_accepted(suggested)
                            db_log_interaction(
                                participant_id=user_id,
                                scenario_code=SC["code"],
                                turn=len(studio_chat),
                                elapsed_s=0,
                                event="suggestion_accepted",
                                data=json.dumps({"suggested_intent": suggested}),
                            )
                            # Prefill the chat input with the suggested intent
                            ss["prefill_prompt"] = suggested
                            st.rerun()

                    # --- Suggested fields (condition B only) ---
                    _render_field_suggestions(
                        data.get("suggested_fields", []),
                        msg_index, 0.75, _is_fresh,
                    )

                # Clear fresh flag after rendering this message
                if _is_fresh:
                    ss.pop("_fresh_msg_idx", None)

        elif msg["type"] == "followup" and msg["role"] == "assistant":
            with st.chat_message("assistant"):
                _is_fresh = (msg_index == ss.get("_fresh_msg_idx", -1))
                text = msg.get("text", "")
                if _is_fresh:
                    st.write_stream(_simulated_stream(text))
                else:
                    st.markdown(text)

                # Suggested intent in follow-up messages too (condition B only, not at max attempts)
                if _current_condition == "B" and not _input_disabled:
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
                        _suggestion_html = (
                            f'<div style="border:1px solid #e0e0e0;border-radius:8px;'
                            f'padding:12px 16px;margin:8px 0;line-height:1.8;'
                            f'font-size:0.95em;">'
                            f'<strong>{U("agent_try")}:</strong><br>{diff_html}</div>'
                        )
                        st.markdown(
                            _anim_wrap(_suggestion_html, 0.3, _is_fresh),
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            U("agent_use_suggestion"),
                            key=f"use_suggestion_{msg_index}",
                        ):
                            _get_logger().log_suggestion_accepted(suggested)
                            db_log_interaction(
                                participant_id=user_id,
                                scenario_code=SC["code"],
                                turn=len(studio_chat),
                                elapsed_s=0,
                                event="suggestion_accepted",
                                data=json.dumps({"suggested_intent": suggested}),
                            )
                            # Prefill the chat input with the suggested intent
                            ss["prefill_prompt"] = suggested
                            st.rerun()

                    # --- Suggested fields in follow-up (condition B only) ---
                    _render_field_suggestions(
                        msg.get("suggested_fields", []),
                        msg_index, 0.45, _is_fresh,
                    )

                # Clear fresh flag after rendering this message
                if _is_fresh:
                    ss.pop("_fresh_msg_idx", None)

    # --- Deferred orchestrator call (runs AFTER messages are rendered) ---
    if ss.get("_pending_orchestrator"):
        _pending_text = ss.pop("_pending_orchestrator")
        ss["_generating"] = True
        with st.spinner(U("chat_generating")):
            _run_orchestrator(_pending_text)
        ss["_generating"] = False
        st.rerun()

    # --- Input bar (inside the chat box, with separator) ---

    # -- Selected fields chip summary (above input bar) --
    _sel_chips_parts = []
    for _ik in sorted(sel_ing):
        _iname = next((it["name"] for it in _ing_items if it["key"] == _ik), _ik.split(".")[-1])
        _sel_chips_parts.append(
            f'<span style="display:inline-block;background:#dbeafe;color:#1e40af;'
            f'padding:3px 10px;border-radius:12px;font-size:0.78rem;font-weight:500;'
            f'margin:2px 3px;">{_iname}</span>'
        )
    for _sk in sorted(sel_set):
        _sname = next((it["name"] for it in _set_items if it["key"] == _sk), _sk.split(".")[-1])
        _sel_chips_parts.append(
            f'<span style="display:inline-block;background:#fef3c7;color:#92400e;'
            f'padding:3px 10px;border-radius:12px;font-size:0.78rem;font-weight:500;'
            f'margin:2px 3px;">{_sname}</span>'
        )
    if _sel_chips_parts:
        st.markdown(
            '<div style="display:flex;flex-wrap:wrap;gap:2px;padding:6px 2px;">'
            + "".join(_sel_chips_parts) + '</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        "<hr style='margin:4px 0 8px 0;border:none;border-top:1px solid #d0d0d0;'>",
        unsafe_allow_html=True,
    )

    _chat_text = ""
    _btn_send = False

    if _input_disabled:
        # Max attempts reached — show clear info message instead of disabled form
        st.markdown(
            f'<div style="background:#fff3e0;border:1px solid #ffcc80;border-radius:10px;'
            f'padding:12px 18px;text-align:center;color:#e65100;font-weight:600;'
            f'font-size:0.92rem;margin:4px 0;">'
            f'{U("attempt_max_reached")}</div>',
            unsafe_allow_html=True,
        )
    else:
        # Clear input: bump the widget key so Streamlit creates a fresh instance
        _input_gen = ss.get("_input_gen", 0)
        if ss.pop("_clear_input", False):
            _input_gen += 1
            ss["_input_gen"] = _input_gen
        _prefill_value = ss.pop("_prefill_input", "") or ""

        # Use a form to ensure text_area value and submit button fire together
        # (fixes double-press bug where first click only commits text_area focus)
        with st.form(key=f"chat_form_{_input_gen}", clear_on_submit=True, border=False):
            _col_icon, _col_input, _col_send = st.columns(
                [0.6, 15, 1], vertical_alignment="bottom",
            )

            with _col_icon:
                st.markdown(
                    '<div style="display:flex;align-items:center;justify-content:center;'
                    'padding-bottom:14px;">'
                    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
                    'viewBox="0 0 24 24" fill="none" stroke="#6b7280" stroke-width="1.5" '
                    'stroke-linecap="round" stroke-linejoin="round">'
                    '<path d="M12 8V4H8"/>'
                    '<rect width="16" height="12" x="4" y="8" rx="2"/>'
                    '<path d="M2 14h2"/><path d="M20 14h2"/>'
                    '<path d="M15 13v2"/><path d="M9 13v2"/>'
                    '</svg>'
                    '</div>',
                    unsafe_allow_html=True,
                )

            with _col_input:
                _chat_text = st.text_area(
                    U("chat_input_placeholder"),
                    value=_prefill_value,
                    key=f"chat_input_text_{_input_gen}",
                    label_visibility="collapsed",
                    placeholder=U("chat_input_placeholder"),
                    height=68,
                )
            with _col_send:
                _btn_send = st.form_submit_button(
                    "\u27a4",
                    type="primary",
                )

# --- Handle send (deferred: append message + rerun, orchestrator runs on next pass) ---
if _btn_send and _chat_text and _chat_text.strip():
    text = _chat_text.strip()
    has_generation = any(m.get("type") == "generation" for m in ss["studio_chat"])
    msg_type = "intent" if not has_generation else "followup"
    ss["studio_chat"].append({"role": "user", "type": msg_type, "text": text})
    _save_chat_to_db()
    # Auto-close field drawers
    ss["_drawer_close_nonce"] = ss.get("_drawer_close_nonce", 0) + 1
    ss["_pending_orchestrator"] = text
    ss["_clear_input"] = True
    st.rerun()

# --- Handle user code edit validation ---
if ss.get("_pending_code_validation"):
    _edited_code_str = ss.pop("_pending_code_validation")
    # Count as new attempt
    ss.setdefault("attempt_count", {})
    _edit_count = ss["attempt_count"].get(SC["code"], 0) + 1
    ss["attempt_count"][SC["code"]] = _edit_count
    ss.setdefault("_scenario_attempt_num", {})
    ss["_scenario_attempt_num"][SC["code"]] = _edit_count

    with st.spinner(U("code_validating")):
        # L1 validation
        _edit_l1 = run_l1_validation(
            code=_edited_code_str,
            trigger_slugs=SC["trigger_apis"],
            action_slugs=SC["action_apis"],
            lang=lang,
        )
        # API fixes
        _edit_api_fixes = []
        if _edit_l1 and _edit_l1.syntax_ok:
            _edit_api_fixes = suggest_api_fixes(
                _edit_l1, SC["trigger_apis"], SC["action_apis"],
                lang=lang,
                catalog_triggers=CAT.get("triggers", []),
                catalog_actions=CAT.get("actions", []),
                endpoint=ORC_ENDPOINT,
                model=ORCHESTRATOR_MODEL,
            )
        # Build conditions
        _edit_conditions = _build_conditions_data(_edited_code_str, _edit_l1, _edit_api_fixes)
        # Build L1 HTML
        _edit_l1_html = _build_l1_card_html(_edit_l1) if _edit_l1 else ""

    # Add as new generation message in chat
    ss["studio_chat"].append({
        "role": "assistant",
        "type": "generation",
        "data": {
            "code": _edited_code_str,
            "l1_report": _edit_l1,
            "api_fixes": _edit_api_fixes,
            "l1_html": _edit_l1_html,
            "conditions": _edit_conditions,
            "commentary": "",
            "suggested_intent": "",
            "suggested_fields": [],
            "user_edited": True,
        },
    })
    ss["_fresh_msg_idx"] = len(ss["studio_chat"]) - 1
    ss["latest_code"] = _edited_code_str
    ss["latest_l1"] = _edit_l1

    # Log to DB
    db_log_interaction(
        participant_id=user_id,
        scenario_code=SC["code"],
        turn=len(ss["studio_chat"]),
        elapsed_s=0,
        event="code_edit_validated",
        data=json.dumps({
            "edited_code": _edited_code_str,
            "attempt": _edit_count,
            "l1_syntax_ok": _edit_l1.syntax_ok if _edit_l1 else False,
        }),
    )
    _save_chat_to_db()
    st.rerun()

# --- Handle prefill: put suggested intent into the chat input ---
if ss.get("prefill_prompt"):
    _prefill = ss.pop("prefill_prompt")
    # Bump input gen to force new widget with the prefill value
    ss["_input_gen"] = ss.get("_input_gen", 0) + 1
    ss["_prefill_input"] = _prefill
    st.rerun()

# ============================================================
# MAIN — Valutazione + Salvataggio
# ============================================================

if ss.get("latest_code") and not ss.get("_generating"):
    generated_code = ss["latest_code"]

    st.markdown("---")

    # Evaluation card header with attempt counter (key for tutorial targeting)
    with st.container(key="eval_section"):
        st.markdown(
            f'<div style="display:flex;align-items:center;justify-content:space-between;'
            f'margin-bottom:8px;">'
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" '
            f'fill="none" stroke="#3b82f6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5'
            f'a2 2 0 0 1 2-2h11"/></svg>'
            f'<span style="font-size:1.15rem;font-weight:700;color:#1e293b;">{U("evaluation")}</span>'
            f'</div>'
            f'<span style="background:#fff3e0;padding:4px 12px;border-radius:16px;'
            f'font-size:0.82rem;font-weight:600;color:#e65100;">'
            f'{U("attempt_counter").format(n=_attempt_num, max=MAX_ATTEMPTS)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    state_key = f"{SC['code']}__{ss.get('selected_attempt', 1)}"

    edited_code = None
    expert_claim_fixed = "not_required"
    expert_gave_up = None
    eval_behavioral_match = ""
    eval_mismatch_reason = ""
    eval_confidence = 3
    eval_code_correct = None
    notes = ""

    _sandbox_pass_rate = None
    _sandbox_all_pass = None

    # Find latest generation for orchestrator metadata in record
    _last_gen = None
    for _m in reversed(ss.get("studio_chat", [])):
        if _m.get("type") == "generation":
            _last_gen = _m["data"]
            break

    if user_type == "non_expert":
        # ============================================
        # NON-EXPERT EVALUATION FORM
        # ============================================
        with st.container(border=True):
            # Behavioral match question
            st.markdown(
                f'<div style="font-weight:600;font-size:0.95rem;color:#334155;'
                f'margin-bottom:6px;">{U("eval_behavioral_q")}</div>',
                unsafe_allow_html=True,
            )
            _match_options = {
                U("eval_match_full"): "matches_completely",
                U("eval_match_partial"): "partially",
                U("eval_match_no"): "does_not_match",
                U("eval_match_unsure"): "unsure",
            }
            _match_choice = st.radio(
                U("eval_behavioral_q"),
                list(_match_options.keys()),
                key=f"eval_match_{state_key}",
                horizontal=True,
                label_visibility="collapsed",
            )
            eval_behavioral_match = _match_options.get(_match_choice, "unsure")

            # Mismatch reason (conditional)
            if eval_behavioral_match in ("partially", "does_not_match", "unsure"):
                eval_mismatch_reason = st.text_area(
                    U("eval_mismatch_q"),
                    height=80,
                    key=f"eval_mismatch_{state_key}",
                )

        with st.container(border=True):
            # Confidence scale (1-5) — radio
            _conf_options = ["1", "2", "3", "4", "5"]
            _conf_val = st.radio(
                U("eval_confidence_q"),
                _conf_options, index=2, horizontal=True,
                key=f"eval_conf_{state_key}",
            )
            eval_confidence = int(_conf_val)
            _conf_labels = {
                1: U("eval_confidence_low"),
                5: U("eval_confidence_high"),
            }
            if eval_confidence in _conf_labels:
                st.caption(_conf_labels[eval_confidence])

        final_code_used = generated_code  # non-expert can't edit code

    else:
        # ============================================
        # EXPERT EVALUATION FORM
        # ============================================

        # --- Behavioral evaluation ---
        with st.container(border=True):
            st.markdown(
                f'<div style="font-weight:600;font-size:0.95rem;color:#1e40af;'
                f'margin-bottom:4px;">{U("eval_behavioral_header")}</div>',
                unsafe_allow_html=True,
            )
            _match_options = {
                U("eval_match_full"): "matches_completely",
                U("eval_match_partial"): "partially",
                U("eval_match_no"): "does_not_match",
            }
            _match_choice = st.radio(
                U("eval_behavioral_q"),
                list(_match_options.keys()),
                key=f"eval_match_{state_key}",
                horizontal=True,
            )
            eval_behavioral_match = _match_options.get(_match_choice, "partially")

        # --- Code evaluation ---
        with st.container(border=True):
            st.markdown(
                f'<div style="font-weight:600;font-size:0.95rem;color:#1e40af;'
                f'margin-bottom:4px;">{U("eval_code_header")}</div>',
                unsafe_allow_html=True,
            )
            _code_opts = {"yes": "yes", "no": "no"}
            _code_choice = st.radio(
                U("eval_code_correct_q"),
                list(_code_opts.keys()),
                horizontal=True,
                key=f"eval_code_correct_{state_key}",
            )
            eval_code_correct = _code_opts.get(_code_choice, "no")

        # --- Code edit status (from inline chat editor) ---
        _edited_code_key = f"_edited_code_{SC['code']}"
        edited_code = ss.get(_edited_code_key)
        has_real_fix = (
            isinstance(edited_code, str)
            and edited_code.strip() != ""
            and edited_code.strip() != generated_code.strip()
        )

        with st.container(border=True):
            st.markdown(
                f'<div style="font-weight:600;font-size:0.92rem;color:#334155;'
                f'margin:8px 0 4px 0;">{U("correction_result")}</div>',
                unsafe_allow_html=True,
            )
            if has_real_fix:
                st.info(U("applied"))
            else:
                st.caption(U("not_applied"))

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

        # Confidence
        with st.container(border=True):
            _conf_options = ["1", "2", "3", "4", "5"]
            _conf_val = st.radio(
                U("eval_confidence_q"),
                _conf_options, index=2, horizontal=True,
                key=f"eval_conf_expert_{state_key}",
            )
            eval_confidence = int(_conf_val)

        # Final code — use edited code from chat if available
        final_code_used = edited_code if has_real_fix else generated_code

    # ---- Notes (both user types) ----
    notes = st.text_area(
        U("eval_notes"), height=80, key=f"eval_notes_{state_key}",
        placeholder=U("eval_notes_placeholder"),
    )

    # ---- Save (prominent button) ----
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    if st.button(U("save_eval"), key=f"save_eval_{state_key}",
                 type="primary", width="stretch"):
        attempt_log = ss.get("attempt_log", [])
        current = attempt_log[-1] if attempt_log else {}

        l1 = ss.get("latest_l1")

        discrepancy = compute_discrepancy(eval_behavioral_match, _sandbox_all_pass) if _sandbox_all_pass is not None else ""

        # Build intent evolution
        intent_evolution = []
        _ie_attempt = 0
        for _m in ss.get("studio_chat", []):
            if _m.get("role") == "user" and _m.get("type") == "intent":
                _ie_attempt += 1
                intent_evolution.append({
                    "attempt": _ie_attempt,
                    "intent": _m.get("text", ""),
                    "source": "user_typed",
                })

        record = dict(current)
        record.update({
            # Identification
            "user_id": user_id,
            "user_type": user_type,
            "scenario_code": SC["code"],
            "complexity_tag": SC.get("complexity_tag", ""),
            "condition": _current_condition,
            "lang": lang,
            # Attempt metadata
            "attempt_number": _attempt_num,
            "final_timestamp": datetime.now(timezone.utc).isoformat(),
            # Intent
            "intent_evolution": intent_evolution,
            # Output
            "generated_code": generated_code,
            "final_code": final_code_used if user_type == "expert" else generated_code,
            # L1 Validation
            "l1_syntax_ok": l1.syntax_ok if l1 else None,
            "l1_api_valid": (l1.api_report.is_valid if l1 and l1.api_report else None),
            "l1_invalid_getters": (l1.api_report.invalid_getters if l1 and l1.api_report else []),
            "l1_invalid_setters": (l1.api_report.invalid_setters if l1 and l1.api_report else []),
            "l1_outcomes_summary": (l1.outcomes_summary if l1 else []),
            "l1_getter_coverage": (l1.getter_coverage if l1 else None),
            "l1_setter_coverage": (l1.setter_coverage if l1 else None),
            "l1_warnings": (l1.warnings if l1 else []),
            # Subjective evaluation
            "eval_behavioral_match": eval_behavioral_match,
            "eval_mismatch_reason": eval_mismatch_reason,
            "eval_confidence": eval_confidence,
            "eval_code_correct": eval_code_correct,
            "eval_notes": notes,
            # Expert-specific
            "expert_edited_code": edited_code,
            "expert_claim_fixed": expert_claim_fixed,
            "expert_gave_up": expert_gave_up,
            # Orchestrator
            "agent_fixes_shown": (_last_gen.get("api_fixes", []) if _last_gen else []),
            "agent_commentary": (_last_gen.get("commentary", "") if _last_gen else ""),
            "agent_suggested_intent": (_last_gen.get("suggested_intent", "") if _last_gen else ""),
            "agent_suggestion_accepted": any(
                m.get("type") == "intent" and m is not ss["studio_chat"][0]
                for m in ss.get("studio_chat", [])
                if m.get("role") == "user"
            ) if ss.get("studio_chat") else False,
            # Derived metric
            "discrepancy_user_vs_sandbox": discrepancy,
            # Sidebar selections
            "selected_ingredients": sorted(sel_ing),
            "selected_setters": sorted(sel_set),
        })

        with open(RESULTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

        # Log evaluation to interaction log
        _logger = _get_logger()
        _logger.log_evaluation(
            correct=eval_behavioral_match,
            notes=notes,
            final_code=final_code_used if user_type == "expert" else generated_code,
            expert_edited=bool(edited_code),
        )

        # Complete scenario session in DB
        complete_scenario_session(
            participant_id=user_id,
            scenario_code=SC["code"],
            final_correct=eval_behavioral_match,
            eval_notes=notes,
            total_turns=_logger._turn,
            total_elapsed_s=round(
                time.monotonic() - _logger.session_start, 2
            ),
            final_code=final_code_used if user_type == "expert" else generated_code,
            l1_syntax_ok=l1.syntax_ok if l1 else None,
            l1_api_valid=l1.api_report.is_valid if l1 and l1.api_report else None,
            exec_pass_rate=_sandbox_pass_rate,
            eval_behavioral_match=eval_behavioral_match,
            eval_confidence=eval_confidence,
            eval_mismatch_reason=eval_mismatch_reason,
            eval_code_correct=eval_code_correct,
            sandbox_all_pass=_sandbox_all_pass,
            attempt_number=_attempt_num,
            discrepancy_user_vs_sandbox=discrepancy,
            intent_evolution=json.dumps(intent_evolution, ensure_ascii=False),
        )

        # --- Post-save: check if block questionnaires (TLX+TOAST) are needed ---
        _next_idx = ss.get("scenario_index", 0) + 1

        # Use TLX as the authoritative check (TLX and TOAST are saved together)
        _existing_tlx = get_tlx_responses(user_id)
        _tlx_blocks_done = {r["block"] for r in _existing_tlx}

        if _current_block == 1 and 1 not in _tlx_blocks_done:
            _block1_codes = {e["scenario_code"] for e in _scenario_assignment if e.get("block", 1) == 1}
            _block1_all_done = bool(_block1_codes) and _block1_codes.issubset(_completed_codes | {SC["code"]})
            if _block1_all_done:
                ss["_show_toast_for_block"] = 1
                ss["_toast_condition"] = _current_condition
                _cleanup_scenario_state(ss, SC["code"])
                st.rerun()

        elif _current_block == 2 and 2 not in _tlx_blocks_done:
            _block2_codes = {e["scenario_code"] for e in _scenario_assignment if e.get("block", 1) == 2}
            _block2_all_done = bool(_block2_codes) and _block2_codes.issubset(_completed_codes | {SC["code"]})
            if _block2_all_done:
                ss["_show_toast_for_block"] = 2
                ss["_toast_condition"] = _current_condition
                _cleanup_scenario_state(ss, SC["code"])
                st.rerun()

        # Normal advance — find next incomplete scenario
        _just_completed = _completed_codes | {SC["code"]}
        _next_incomplete = None
        for _ni, _ns in enumerate(SCENARIOS):
            if _ns["code"] not in _just_completed:
                _next_incomplete = _ni
                break
        if _next_incomplete is not None:
            ss["scenario_index"] = _next_incomplete
        else:
            # All done — stay on last or advance
            if _next_idx < len(SCENARIOS):
                ss["scenario_index"] = _next_idx
        _cleanup_scenario_state(ss, SC["code"])
        st.rerun()
