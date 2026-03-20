# Home.py — Entry point dello studio NL2TAP

import os
import re
import sys
_src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import streamlit as st
from utils.session_manager import (
    register_participant, get_participant_registration,
    get_participant_progress, get_full_study_summary, get_sus_responses,
    create_session_token, validate_session_token, invalidate_session_token,
)
from utils.study_utils import STUDY, NON_EXP, EXP

_ACCESS_CODE = "STUDY2026"
_ADMIN_USER = "admin"
_ADMIN_CODE = "NL2TAP-ADMIN-2026"

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="NL2TAP",
    layout="wide",
    initial_sidebar_state="collapsed",
)

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
[data-testid="stSidebar"] { display: none; }
[data-testid="stSidebarCollapsedControl"] { display: none; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
.stDeployButton { display: none !important; }
/* Hide field drawers that may persist from Studio page */
#sfd-stack, #sfd-tooltip { display: none !important; }
/* Fixed-width language buttons */
.st-key-lang_it_col, .st-key-lang_en_col {
    flex: 0 0 50px !important; max-width: 50px !important; min-width: 50px !important;
}
</style>
<img src="" onerror="
(function(){
  ['sfd-stack','sfd-tooltip','tutorial-spotlight','tutorial-callout'].forEach(function(id){
    var e=document.getElementById(id);if(e)e.parentNode.removeChild(e);
  });
})();
" style="display:none">
""", unsafe_allow_html=True)

# ============================================================
# LANGUAGE (default)
# ============================================================

if "lang" not in st.session_state:
    st.session_state.lang = "it"

lang = st.session_state.lang

# ============================================================
# I18N
# ============================================================

_T = {
    "it": {
        "title": "NL2TAP",
        "username_label": "Nome utente",
        "username_placeholder": "es. user_01",
        "username_err": "Formato richiesto: user_XX (es. user_01, user_21)",
        "login_label": "Codice di accesso",
        "login_placeholder": "Codice fornito dal ricercatore",
        "login_btn": "Accedi",
        "login_err": "Codice non valido.",
        "login_ok": "Accesso effettuato.",
        "start_btn": "\u25b6 Inizia lo studio",
        "resume_btn": "\u25b6 Riprendi lo studio",
        "registration_ok": "Registrazione completata.",
        "registration_existing": "Bentornato! La sessione precedente \u00e8 stata ripristinata.",
        "progress_label": "Scenari completati: {n}",
        "guide_header": "Come funziona lo studio",
        "start_desc": (
            "Quando sei pronta/o:\n"
            "- selezionerai uno **scenario** di automazione,\n"
            "- descriverai in linguaggio naturale il comportamento desiderato,\n"
            "- il sistema generer\u00e0 l'automazione,\n"
            "- valuterai se il risultato corrisponde al tuo intento."
        ),
        "intro_title": "Come funziona l'esperimento",
        "intro_what": (
            "In questo studio valuterai delle <b>automazioni</b> generate da un sistema AI."
        ),
        "intro_automation": (
            "Un'automazione collega un <b>evento</b> (es. ricevi un'email) "
            "a un'<b>azione</b> (es. salva un allegato). "
            "I servizi mettono a disposizione dei <b>campi dati</b> che descrivono l'evento "
            "e permettono di configurare l'azione."
        ),
        "intro_your_task": (
            "Il tuo compito \u00e8 <b>personalizzare il comportamento</b> di ciascuna automazione "
            "descrivendo in linguaggio naturale cosa deve fare. Il sistema generer\u00e0 il codice "
            "corrispondente e ti mostrer\u00e0 il risultato, che potrai valutare."
        ),
        "intro_steps_header": "Lo studio prevede <b>{n} scenari</b>. Per ciascuno:",
        "intro_step_1": "Leggi la descrizione dello scenario",
        "intro_step_2": "Seleziona i campi dati rilevanti tra quelli disponibili",
        "intro_step_3": "Descrivi in linguaggio naturale cosa vuoi che faccia l'automazione",
        "intro_step_4": "Esamina il risultato generato dal sistema",
        "intro_step_5": "Valuta se il comportamento corrisponde al tuo intento",
        "intro_tips_header": "Suggerimenti",
        "intro_tip_1": "Puoi fare fino a <b>3 tentativi</b> per scenario",
        "intro_tip_2": "L'assistente analizzer\u00e0 i risultati e ti fornir\u00e0 un commento",
        "intro_tip_3": "Non c'\u00e8 una risposta giusta o sbagliata: valuta in base al tuo giudizio",
        "logout_btn": "Esci",
        "logout_confirm": "Sei sicuro di voler uscire?",
        "summary_title": "Riepilogo dello studio",
        "summary_thankyou": "Hai completato tutti gli scenari. Grazie per aver partecipato!",
        "summary_scenarios_header": "Risultati per scenario",
        "summary_scenario": "Scenario",
        "summary_condition": "Condizione",
        "summary_complexity": "Complessita",
        "summary_eval": "Valutazione",
        "summary_confidence": "Confidenza",
        "summary_attempts": "Tentativi",
        "summary_questionnaires": "Questionari",
        "summary_block": "Blocco",
        "summary_tlx_header": "NASA-TLX (Carico di lavoro)",
        "summary_toast_header": "TOAST (Fiducia nel sistema)",
        "summary_sus_header": "SUS (Usabilita del sistema)",
        "summary_sus_score": "Punteggio SUS",
        "summary_mean": "Media",
        "summary_understanding": "Comprensione",
        "summary_performance": "Prestazione",
        "summary_mental": "Carico mentale",
        "summary_physical": "Carico fisico",
        "summary_temporal": "Pressione temporale",
        "summary_perf_tlx": "Prestazione percepita",
        "summary_effort": "Impegno",
        "summary_frustration": "Frustrazione",
        "summary_raw_mean": "Media grezza",
        "summary_not_submitted": "Non compilato",
        "eval_matches_completely": "Corrisponde completamente",
        "eval_matches_partially": "Corrisponde parzialmente",
        "eval_does_not_match": "Non corrisponde",
        "eval_cannot_tell": "Non so valutare",
        "eval_not_evaluated": "Non valutato",
    },
    "en": {
        "title": "NL2TAP",
        "username_label": "Username",
        "username_placeholder": "e.g. user_01",
        "username_err": "Required format: user_XX (e.g. user_01, user_21)",
        "login_label": "Access code",
        "login_placeholder": "Code provided by the researcher",
        "login_btn": "Log in",
        "login_err": "Invalid code.",
        "login_ok": "Access granted.",
        "start_btn": "\u25b6 Start the study",
        "resume_btn": "\u25b6 Resume the study",
        "registration_ok": "Registration complete.",
        "registration_existing": "Welcome back! Previous session restored.",
        "progress_label": "Scenarios completed: {n}",
        "guide_header": "How the study works",
        "start_desc": (
            "When you are ready:\n"
            "- you will select an **automation scenario**,\n"
            "- describe the desired behavior in natural language,\n"
            "- the system will generate the automation,\n"
            "- you will evaluate whether the result matches your intent."
        ),
        "intro_title": "How the experiment works",
        "intro_what": (
            "In this study you will evaluate <b>automations</b> generated by an AI system."
        ),
        "intro_automation": (
            "An automation connects an <b>event</b> (e.g. you receive an email) "
            "to an <b>action</b> (e.g. save an attachment). "
            "Services provide <b>data fields</b> that describe the event "
            "and allow configuring the action."
        ),
        "intro_your_task": (
            "Your task is to <b>customize the behavior</b> of each automation "
            "by describing in natural language what it should do. The system will generate "
            "the corresponding code and show you the result, which you can then evaluate."
        ),
        "intro_steps_header": "The study includes <b>{n} scenarios</b>. For each one:",
        "intro_step_1": "Read the scenario description",
        "intro_step_2": "Select the relevant data fields from those available",
        "intro_step_3": "Describe in natural language what you want the automation to do",
        "intro_step_4": "Examine the result generated by the system",
        "intro_step_5": "Evaluate whether the behavior matches your intent",
        "intro_tips_header": "Tips",
        "intro_tip_1": "You can make up to <b>3 attempts</b> per scenario",
        "intro_tip_2": "The assistant will analyze the results and provide commentary",
        "intro_tip_3": "There is no right or wrong answer: evaluate based on your own judgment",
        "logout_btn": "Log out",
        "logout_confirm": "Are you sure you want to log out?",
        "summary_title": "Study Summary",
        "summary_thankyou": "You have completed all scenarios. Thank you for participating!",
        "summary_scenarios_header": "Scenario Results",
        "summary_scenario": "Scenario",
        "summary_condition": "Condition",
        "summary_complexity": "Complexity",
        "summary_eval": "Evaluation",
        "summary_confidence": "Confidence",
        "summary_attempts": "Attempts",
        "summary_questionnaires": "Questionnaires",
        "summary_block": "Block",
        "summary_tlx_header": "NASA-TLX (Workload)",
        "summary_toast_header": "TOAST (System Trust)",
        "summary_sus_header": "SUS (System Usability)",
        "summary_sus_score": "SUS Score",
        "summary_mean": "Mean",
        "summary_understanding": "Understanding",
        "summary_performance": "Performance",
        "summary_mental": "Mental demand",
        "summary_physical": "Physical demand",
        "summary_temporal": "Temporal demand",
        "summary_perf_tlx": "Perceived performance",
        "summary_effort": "Effort",
        "summary_frustration": "Frustration",
        "summary_raw_mean": "Raw mean",
        "summary_not_submitted": "Not submitted",
        "eval_matches_completely": "Matches completely",
        "eval_matches_partially": "Matches partially",
        "eval_does_not_match": "Does not match",
        "eval_cannot_tell": "Cannot tell",
        "eval_not_evaluated": "Not evaluated",
    },
}

def T(key: str):
    return _T.get(lang, _T["en"]).get(key, key)


# ============================================================
# STUDY COMPLETION SUMMARY
# ============================================================

_EVAL_COLORS = {
    "matches_completely": ("#166534", "#dcfce7"),
    "matches_partially": ("#92400e", "#fef3c7"),
    "does_not_match": ("#991b1b", "#fee2e2"),
    "cannot_tell": ("#6b7280", "#f3f4f6"),
}

def _eval_label(val: str) -> str:
    """Translate eval_behavioral_match value."""
    if not val:
        return T("eval_not_evaluated")
    return T(f"eval_{val}")

def _render_study_summary(user_id: str, is_it: bool):
    """Render the full study completion summary page."""
    summary = get_full_study_summary(user_id)
    scenarios = summary["scenarios"]
    toast_list = summary["toast"]
    tlx_list = summary["tlx"]
    sus_list = summary["sus"]

    # --- Logout button (top-right) ---
    _hdr_l, _hdr_r = st.columns([8, 1])
    with _hdr_r:
        if st.button(T("logout_btn"), key="summary_logout_btn"):
            _token = st.session_state.get("_session_token", "")
            if _token:
                invalidate_session_token(_token)
            st.query_params.clear()
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

    # --- Header with checkmark ---
    st.markdown("<div style='height:2vh'></div>", unsafe_allow_html=True)
    _cl, _cc, _cr = st.columns([0.8, 2.4, 0.8])
    with _cc:
        st.markdown(
            f'<div style="text-align:center;border:2px solid #86efac;border-radius:16px;'
            f'padding:30px 24px 20px;background:#f0fdf4;margin-bottom:24px;">'
            f'<div style="font-size:2.5rem;margin-bottom:8px;">&#10003;</div>'
            f'<h2 style="color:#166534;margin:0 0 8px 0;">{T("summary_title")}</h2>'
            f'<p style="font-size:1rem;color:#334155;margin:0;">{T("summary_thankyou")}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # --- Scenario results table ---
        st.markdown(
            f'<h3 style="color:#1e40af;margin:20px 0 12px;">{T("summary_scenarios_header")}</h3>',
            unsafe_allow_html=True,
        )

        # Build table rows
        _rows_html = ""
        for sc in scenarios:
            code = sc.get("scenario_code", "?")
            cond = sc.get("condition", "?")
            cplx = sc.get("complexity_class", "?")
            ev = sc.get("eval_behavioral_match") or ""
            conf = sc.get("eval_confidence")
            att = sc.get("attempt_number") or "?"
            completed = sc.get("completed_at")

            # Eval badge
            ev_color, ev_bg = _EVAL_COLORS.get(ev, ("#6b7280", "#f3f4f6"))
            ev_text = _eval_label(ev) if completed else T("eval_not_evaluated")
            ev_badge = (
                f'<span style="background:{ev_bg};color:{ev_color};padding:2px 8px;'
                f'border-radius:8px;font-size:0.82rem;font-weight:600;">{ev_text}</span>'
            )

            # Confidence
            if conf is not None:
                conf_bar = "".join(
                    f'<span style="color:{"#3b82f6" if i < conf else "#d1d5db"};">&#9679;</span>'
                    for i in range(5)
                )
            else:
                conf_bar = '<span style="color:#9ca3af;">-</span>'

            # Condition badge
            cond_badge_color = "#7c3aed" if cond == "B" else "#2563eb"
            cond_badge = (
                f'<span style="background:{cond_badge_color};color:#fff;padding:1px 7px;'
                f'border-radius:6px;font-size:0.78rem;font-weight:600;">{cond}</span>'
            )

            _rows_html += (
                f'<tr style="border-bottom:1px solid #e5e7eb;">'
                f'<td style="padding:8px 10px;font-weight:600;font-size:0.9rem;">{code}</td>'
                f'<td style="padding:8px 10px;text-align:center;">{cond_badge}</td>'
                f'<td style="padding:8px 10px;text-align:center;font-size:0.85rem;">{cplx}</td>'
                f'<td style="padding:8px 10px;">{ev_badge}</td>'
                f'<td style="padding:8px 10px;text-align:center;">{conf_bar}</td>'
                f'<td style="padding:8px 10px;text-align:center;font-size:0.9rem;">{att}</td>'
                f'</tr>'
            )

        st.markdown(
            f'<div style="border:1px solid #dbeafe;border-radius:12px;overflow:hidden;margin-bottom:24px;">'
            f'<table style="width:100%;border-collapse:collapse;">'
            f'<thead><tr style="background:#eff6ff;">'
            f'<th style="padding:10px;text-align:left;font-size:0.85rem;color:#1e40af;">{T("summary_scenario")}</th>'
            f'<th style="padding:10px;text-align:center;font-size:0.85rem;color:#1e40af;">{T("summary_condition")}</th>'
            f'<th style="padding:10px;text-align:center;font-size:0.85rem;color:#1e40af;">{T("summary_complexity")}</th>'
            f'<th style="padding:10px;text-align:left;font-size:0.85rem;color:#1e40af;">{T("summary_eval")}</th>'
            f'<th style="padding:10px;text-align:center;font-size:0.85rem;color:#1e40af;">{T("summary_confidence")}</th>'
            f'<th style="padding:10px;text-align:center;font-size:0.85rem;color:#1e40af;">{T("summary_attempts")}</th>'
            f'</tr></thead>'
            f'<tbody>{_rows_html}</tbody>'
            f'</table></div>',
            unsafe_allow_html=True,
        )

        # --- Questionnaires section ---
        st.markdown(
            f'<h3 style="color:#1e40af;margin:20px 0 12px;">{T("summary_questionnaires")}</h3>',
            unsafe_allow_html=True,
        )

        # TLX + TOAST side by side per block
        _tlx_by_block = {t["block"]: t for t in tlx_list}
        _toast_by_block = {t["block"]: t for t in toast_list}

        for block_num in [1, 2]:
            st.markdown(
                f'<h4 style="color:#374151;margin:14px 0 8px;">'
                f'{T("summary_block")} {block_num}</h4>',
                unsafe_allow_html=True,
            )

            _c_tlx, _c_toast = st.columns(2)

            # TLX card
            with _c_tlx:
                tlx = _tlx_by_block.get(block_num)
                if tlx:
                    _tlx_items = [
                        ("summary_mental", tlx.get("mental_demand", 0)),
                        ("summary_physical", tlx.get("physical_demand", 0)),
                        ("summary_temporal", tlx.get("temporal_demand", 0)),
                        ("summary_perf_tlx", tlx.get("performance", 0)),
                        ("summary_effort", tlx.get("effort", 0)),
                        ("summary_frustration", tlx.get("frustration", 0)),
                    ]
                    _bars = ""
                    for label_key, val in _tlx_items:
                        pct = min(val, 100)
                        _bars += (
                            f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0;">'
                            f'<span style="width:120px;font-size:0.82rem;color:#374151;">{T(label_key)}</span>'
                            f'<div style="flex:1;background:#e5e7eb;border-radius:4px;height:14px;">'
                            f'<div style="width:{pct}%;background:#3b82f6;border-radius:4px;height:14px;"></div>'
                            f'</div>'
                            f'<span style="width:30px;font-size:0.8rem;color:#6b7280;text-align:right;">{val}</span>'
                            f'</div>'
                        )
                    _raw_mean = tlx.get("raw_tlx_mean", 0)
                    st.markdown(
                        f'<div style="border:1px solid #dbeafe;border-radius:10px;padding:14px 16px;background:#fafbff;">'
                        f'<div style="font-weight:600;font-size:0.9rem;color:#1e40af;margin-bottom:10px;">'
                        f'{T("summary_tlx_header")}</div>'
                        f'{_bars}'
                        f'<div style="margin-top:8px;padding-top:8px;border-top:1px solid #e5e7eb;'
                        f'font-size:0.85rem;color:#374151;">'
                        f'<b>{T("summary_raw_mean")}:</b> {_raw_mean:.1f}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div style="border:1px dashed #d1d5db;border-radius:10px;padding:14px 16px;'
                        f'background:#f9fafb;color:#9ca3af;font-size:0.9rem;">'
                        f'{T("summary_tlx_header")} — {T("summary_not_submitted")}</div>',
                        unsafe_allow_html=True,
                    )

            # TOAST card
            with _c_toast:
                toast = _toast_by_block.get(block_num)
                if toast:
                    _und = toast.get("understanding_mean", 0)
                    _perf = toast.get("performance_mean", 0)
                    _overall = toast.get("overall_mean", 0)
                    _items = [toast.get(f"item_{i}", 0) for i in range(1, 10)]
                    _dots = ""
                    for idx, v in enumerate(_items):
                        _cat = T("summary_understanding") if idx < 4 else T("summary_performance")
                        _dots += (
                            f'<div style="display:flex;align-items:center;gap:6px;margin:3px 0;">'
                            f'<span style="width:20px;font-size:0.78rem;color:#6b7280;text-align:right;">Q{idx+1}</span>'
                            f'<div style="flex:1;display:flex;gap:3px;">'
                        )
                        for dot in range(1, 8):
                            _c = "#7c3aed" if dot <= v else "#e5e7eb"
                            _dots += f'<span style="width:10px;height:10px;border-radius:50%;background:{_c};display:inline-block;"></span>'
                        _dots += f'</div><span style="width:14px;font-size:0.78rem;color:#6b7280;">{v}</span></div>'

                    st.markdown(
                        f'<div style="border:1px solid #ede9fe;border-radius:10px;padding:14px 16px;background:#faf5ff;">'
                        f'<div style="font-weight:600;font-size:0.9rem;color:#5b21b6;margin-bottom:10px;">'
                        f'{T("summary_toast_header")}</div>'
                        f'{_dots}'
                        f'<div style="margin-top:8px;padding-top:8px;border-top:1px solid #e5e7eb;'
                        f'font-size:0.83rem;color:#374151;display:flex;gap:16px;">'
                        f'<span><b>{T("summary_understanding")}:</b> {_und:.1f}</span>'
                        f'<span><b>{T("summary_performance")}:</b> {_perf:.1f}</span>'
                        f'<span><b>{T("summary_mean")}:</b> {_overall:.1f}</span>'
                        f'</div></div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div style="border:1px dashed #d1d5db;border-radius:10px;padding:14px 16px;'
                        f'background:#f9fafb;color:#9ca3af;font-size:0.9rem;">'
                        f'{T("summary_toast_header")} — {T("summary_not_submitted")}</div>',
                        unsafe_allow_html=True,
                    )

        # --- SUS cards (one per block) ---
        _sus_by_block = {s["block"]: s for s in sus_list}
        if sus_list:
            _sus_cols = st.columns(len(sus_list))
            for _si, sus in enumerate(sus_list):
                with _sus_cols[_si]:
                    _sus_score = sus.get("sus_score", 0)
                    _sus_blk = sus.get("block", 0)
                    if _sus_score >= 80:
                        _sus_color, _sus_bg = "#166534", "#dcfce7"
                    elif _sus_score >= 68:
                        _sus_color, _sus_bg = "#1e40af", "#dbeafe"
                    elif _sus_score >= 50:
                        _sus_color, _sus_bg = "#92400e", "#fef3c7"
                    else:
                        _sus_color, _sus_bg = "#991b1b", "#fee2e2"

                    _sus_items_html = ""
                    for i in range(1, 11):
                        v = sus.get(f"item_{i}", 0)
                        _sus_items_html += (
                            f'<span style="background:#f3f4f6;padding:2px 6px;border-radius:4px;'
                            f'font-size:0.8rem;color:#374151;">Q{i}={v}</span> '
                        )

                    _blk_label = f"{T('summary_block')} {_sus_blk}" if _sus_blk else ""
                    st.markdown(
                        f'<div style="border:1px solid #dbeafe;border-radius:10px;padding:16px 18px;'
                        f'background:#fafbff;margin-top:16px;">'
                        f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">'
                        f'<span style="font-weight:600;font-size:0.9rem;color:#1e40af;">'
                        f'{T("summary_sus_header")} — {_blk_label}</span>'
                        f'<span style="background:{_sus_bg};color:{_sus_color};padding:4px 12px;border-radius:10px;'
                        f'font-size:1.1rem;font-weight:700;">{_sus_score:.0f}/100</span>'
                        f'</div>'
                        f'<div style="display:flex;flex-wrap:wrap;gap:6px;">{_sus_items_html}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        # Spacer at bottom
        st.markdown("<div style='height:4vh'></div>", unsafe_allow_html=True)


# ============================================================
# SESSION RESTORE FROM URL TOKEN
# ============================================================

def _restore_session_from_token():
    """Check URL query params for a session token and restore session state."""
    token = st.query_params.get("token", "")
    if not token:
        return False
    session_data = validate_session_token(token)
    if not session_data:
        # Invalid/expired token — clear it from URL
        st.query_params.pop("token", None)
        return False
    # Restore session state from token data
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

# Try to restore session if not already authenticated
if not st.session_state.get("authenticated"):
    _restore_session_from_token()
    # Re-read lang after potential restore
    if st.session_state.get("lang"):
        lang = st.session_state.lang

# ============================================================
# LOGIN GATE — centered card
# ============================================================

_FLAG_IT = "https://flagcdn.com/w80/it.png"
_FLAG_GB = "https://flagcdn.com/w80/gb.png"

if not st.session_state.get("authenticated"):
    # Vertical spacer + centered column
    st.markdown("<div style='height:8vh'></div>", unsafe_allow_html=True)
    _left, _center, _right = st.columns([1.2, 1.6, 1.2])

    with _center:
        with st.container(border=True):
            # Icon + title header — centered
            st.markdown(
                '<div style="display:flex;align-items:center;justify-content:center;'
                'gap:10px;margin-bottom:16px;margin-top:4px;">'
                '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" '
                'viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="1.5" '
                'stroke-linecap="round" stroke-linejoin="round">'
                '<path d="M12 2a7 7 0 0 1 7 7c0 2.38-1.19 4.47-3 5.74V17a2 2 0 0 1-2 2h-4'
                'a2 2 0 0 1-2-2v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 0 1 7-7z"/>'
                '<path d="M10 21v1a2 2 0 0 0 4 0v-1"/>'
                '<line x1="9" y1="17" x2="15" y2="17"/>'
                '</svg>'
                '<span style="font-size:1.5rem;font-weight:700;color:#111827;">NL2TAP</span>'
                '</div>',
                unsafe_allow_html=True,
            )

            # Username
            username_input = st.text_input(
                T("username_label"),
                placeholder=T("username_placeholder"),
            )

            # Access code
            access_input = st.text_input(
                T("login_label"),
                type="password",
                placeholder=T("login_placeholder"),
            )

            # Language selector — flag above button, centered
            _lp, _it_col, _sp, _en_col, _rp = st.columns(
                [3, 1, 0.3, 1, 3], vertical_alignment="center",
            )
            with _it_col:
                with st.container(key="lang_it_col"):
                    st.markdown(
                        f'<div style="text-align:center;margin-bottom:4px;">'
                        f'<img src="{_FLAG_IT}" style="height:20px;border-radius:3px;">'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("IT", key="lang_it", width="stretch",
                                 type="primary" if lang == "it" else "secondary"):
                        st.session_state.lang = "it"
                        st.rerun()
            with _en_col:
                with st.container(key="lang_en_col"):
                    st.markdown(
                        f'<div style="text-align:center;margin-bottom:4px;">'
                        f'<img src="{_FLAG_GB}" style="height:20px;border-radius:3px;">'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("EN", key="lang_en", width="stretch",
                                 type="primary" if lang == "en" else "secondary"):
                        st.session_state.lang = "en"
                        st.rerun()

            # Login button — centered
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            _btn_pad, _btn_col, _btn_pad2 = st.columns([1, 2, 1])
            with _btn_col:
                if st.button(T("login_btn"), type="primary", width="stretch"):
                    username = username_input.strip().lower()
                    code = access_input.strip()

                    # --- Admin login ---
                    if username == _ADMIN_USER and code == _ADMIN_CODE:
                        token = create_session_token("admin", "admin", lang, is_admin=True)
                        st.session_state["authenticated"] = True
                        st.session_state["admin_authenticated"] = True
                        st.session_state["user_id"] = "admin"
                        st.session_state["user_type"] = "admin"
                        st.session_state["lang"] = lang
                        st.session_state["_session_token"] = token
                        st.query_params["token"] = token
                        st.success(T("login_ok"))
                        st.rerun()

                    # --- User login ---
                    elif code != _ACCESS_CODE:
                        st.error(T("login_err"))
                        st.stop()

                    else:
                        m = re.match(r'^user_(\d+)$', username)
                        if not m:
                            st.error(T("username_err"))
                            st.stop()

                        id_num = int(m.group(1))
                        user_type = "non_expert" if (id_num - 1) % 40 < 20 else "expert"

                        token = create_session_token(username, user_type, lang)
                        st.session_state["authenticated"] = True
                        st.session_state["user_id"] = username
                        st.session_state["user_type"] = user_type
                        st.session_state["lang"] = lang
                        st.session_state["_session_token"] = token
                        st.query_params["token"] = token

                        st.success(T("login_ok"))
                        st.rerun()

    st.stop()

# ============================================================
# POST-LOGIN
# ============================================================

lang = st.session_state.get("lang", "it")
_is_it = lang == "it"

# --- Admin redirect: go straight to admin dashboard ---
if st.session_state.get("user_type") == "admin":
    st.switch_page("pages/3_Admin.py")

# --- Auto-redirect: if study already started, skip Home ---
_uid = st.session_state.get("user_id", "")
_existing_reg = st.session_state.get("study_registration")
if not _existing_reg and _uid:
    # Read-only recovery from DB (does NOT create new participants)
    _reg = get_participant_registration(_uid)
    if _reg:
        st.session_state["study_registration"] = _reg
        st.session_state["scenario_assignment"] = _reg["scenario_assignment"]
        st.session_state["counterbalance_group"] = _reg["counterbalance_group"]
        st.session_state["condition_order"] = _reg["condition_order"]
        _existing_reg = _reg

if _existing_reg and _existing_reg.get("already_registered"):
    _progress = get_participant_progress(_uid)
    _total = len(_existing_reg.get("scenario_assignment", []))
    _n_done = _progress["n_completed"]
    _sus_all = get_sus_responses(_uid)
    _sus_blocks_done = {r["block"] for r in _sus_all}
    if _total > 0 and _n_done >= _total and {1, 2}.issubset(_sus_blocks_done):
        # --- Study completed: full summary screen ---
        _render_study_summary(_uid, _is_it)
        st.stop()
    elif _total > 0 and (_n_done > 0 or _sus_blocks_done):
        # Study in progress — go straight to Studio
        st.switch_page("pages/2_Studio.py")

# ============================================================
# POST-LOGIN — General intro (users only, first time)
# ============================================================

# Title bar + logout
_title_col, _logout_col = st.columns([8, 1])
with _title_col:
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">'
        '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" '
        'viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="1.5" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 2a7 7 0 0 1 7 7c0 2.38-1.19 4.47-3 5.74V17a2 2 0 0 1-2 2h-4'
        'a2 2 0 0 1-2-2v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 0 1 7-7z"/>'
        '<path d="M10 21v1a2 2 0 0 0 4 0v-1"/>'
        '<line x1="9" y1="17" x2="15" y2="17"/>'
        '</svg>'
        '<span style="font-size:1.3rem;font-weight:700;color:#111827;">NL2TAP</span>'
        '</div>',
        unsafe_allow_html=True,
    )
with _logout_col:
    if st.button(T("logout_btn"), key="home_logout_btn"):
        # Clean up any lingering field-drawer / tutorial DOM elements
        import streamlit.components.v1 as _cv1
        _cv1.html(
            '<script>'
            '(function(){'
            '["sfd-stack","sfd-tooltip","tutorial-spotlight","tutorial-callout"]'
            '.forEach(function(id){'
            'var e=window.parent.document.getElementById(id);'
            'if(e)e.parentNode.removeChild(e);'
            '});'
            '})();'
            '</script>',
            height=0,
        )
        _token = st.session_state.get("_session_token", "")
        if _token:
            invalidate_session_token(_token)
        st.query_params.clear()
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# General study explanation — expanded structured card
_user_type_early = st.session_state.get("user_type", "non_expert")
_n_scenarios = len(NON_EXP) if _user_type_early == "non_expert" else len(EXP)
st.markdown(
    # --- What is this study? ---
    '<div style="border:1px solid #bfdbfe; border-radius:12px; padding:22px 26px; '
    'margin-bottom:16px; background:#f0f7ff;">'
    '<div style="display:flex; align-items:center; gap:10px; margin-bottom:14px;">'
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
    'fill="none" stroke="#3b82f6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>'
    f'<span style="font-size:1.15rem; font-weight:700; color:#1e40af;">{T("intro_title")}</span>'
    '</div>'
    f'<p style="font-size:0.95rem; color:#334155; margin:0 0 10px 0;">{T("intro_what")}</p>'
    f'<p style="font-size:0.95rem; color:#334155; margin:0 0 10px 0;">{T("intro_automation")}</p>'
    f'<p style="font-size:0.95rem; color:#334155; margin:0 0 16px 0;">{T("intro_your_task")}</p>'
    # --- Steps ---
    '<div style="background:#fff; border:1px solid #dbeafe; border-radius:10px; '
    'padding:16px 20px; margin-bottom:14px;">'
    f'<p style="font-size:0.95rem; color:#334155; margin:0 0 8px 0; font-weight:600;">'
    f'{T("intro_steps_header").format(n=_n_scenarios)}</p>'
    '<ol style="margin:0 0 0 20px; padding:0; font-size:0.93rem; color:#334155; line-height:1.9;">'
    f'<li>{T("intro_step_1")}</li>'
    f'<li>{T("intro_step_2")}</li>'
    f'<li>{T("intro_step_3")}</li>'
    f'<li>{T("intro_step_4")}</li>'
    f'<li>{T("intro_step_5")}</li>'
    '</ol>'
    '</div>'
    # --- Tips ---
    '<div style="background:#fffbeb; border:1px solid #fde68a; border-radius:10px; '
    'padding:14px 20px;">'
    f'<p style="font-size:0.92rem; font-weight:600; color:#92400e; margin:0 0 6px 0;">'
    f'\U0001f4a1 {T("intro_tips_header")}</p>'
    '<ul style="margin:0 0 0 18px; padding:0; font-size:0.9rem; color:#78350f; line-height:1.8;">'
    f'<li>{T("intro_tip_1")}</li>'
    f'<li>{T("intro_tip_2")}</li>'
    f'<li>{T("intro_tip_3")}</li>'
    '</ul>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown("---")

user_id = st.session_state.get("user_id", "")
user_type = st.session_state.get("user_type", "non_expert")

# --- User ID badge ---
st.markdown(
    f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">'
    f'<span style="background:#e0e7ff;color:#3730a3;padding:3px 10px;border-radius:12px;'
    f'font-size:0.85rem;font-weight:600;">{user_id}</span>'
    f'</div>',
    unsafe_allow_html=True,
)

if st.session_state.get("study_registration"):
    reg = st.session_state["study_registration"]
    progress = get_participant_progress(user_id)
    n_done = progress["n_completed"]
    total = len(reg["scenario_assignment"])
    st.info(T("progress_label").format(n=f"{n_done}/{total}"))
    if reg.get("already_registered"):
        st.caption(T("registration_existing"))

_is_returning = st.session_state.get("study_registration", {}).get("already_registered", False)
_btn_label = T("resume_btn") if _is_returning else T("start_btn")
if st.button(_btn_label, type="primary"):
    scenario_pool = NON_EXP if user_type == "non_expert" else EXP

    reg = register_participant(
        participant_id=user_id,
        user_type=user_type,
        lang=lang,
        scenario_pool=scenario_pool,
    )
    st.session_state["study_registration"] = reg
    st.session_state["scenario_assignment"] = reg["scenario_assignment"]
    st.session_state["counterbalance_group"] = reg["counterbalance_group"]
    st.session_state["condition_order"] = reg["condition_order"]

    if not reg.get("already_registered"):
        st.success(T("registration_ok"))
        # First-time registration: activate tutorial
        st.session_state["tutorial_active"] = True
        st.session_state["tutorial_step"] = 0
        st.session_state["_tutorial_key_gen"] = st.session_state.get("_tutorial_key_gen", 0) + 1
    # Returning user: skip tutorial (they've already seen it)
    st.switch_page("pages/2_Studio.py")
