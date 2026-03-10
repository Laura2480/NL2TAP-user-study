# Home.py — Entry point dello studio

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st
from utils.session_manager import register_participant, get_participant_progress
from utils.study_utils import STUDY

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Filter Code User Study",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Hide entire sidebar on Home
st.markdown("""
<style>
[data-testid="stSidebar"] { display: none; }
[data-testid="stSidebarCollapsedControl"] { display: none; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# LANGUAGE — prima di tutto
# ============================================================

if "lang" not in st.session_state:
    st.session_state.lang = "it"

_FLAG_IT = "https://flagcdn.com/w40/it.png"
_FLAG_GB = "https://flagcdn.com/w40/gb.png"

st.caption("Scegli la lingua / Choose your language")

col_it, col_en, _ = st.columns([1, 1, 6])
with col_it:
    st.markdown(
        f'<img src="{_FLAG_IT}" style="height:24px;margin-bottom:8px;">',
        unsafe_allow_html=True,
    )
    if st.button("IT", type="primary" if st.session_state.lang == "it" else "secondary"):
        st.session_state.lang = "it"
        st.rerun()
with col_en:
    st.markdown(
        f'<img src="{_FLAG_GB}" style="height:24px;margin-bottom:8px;">',
        unsafe_allow_html=True,
    )
    if st.button("EN", type="primary" if st.session_state.lang == "en" else "secondary"):
        st.session_state.lang = "en"
        st.rerun()

lang = st.session_state.lang

# ============================================================
# I18N — testi bilingui
# ============================================================

_T = {
    "it": {
        "title": "Filter Code User Study",
        "intro": (
            "Benvenuta/o nello studio sperimentale.\n\n"
            "Questo studio analizza **come utenti esperti e non esperti collaborano "
            "con modelli di linguaggio (LLM)** per generare **Filter Code JavaScript** "
            "per automazioni *IFTTT-style*.\n\n"
            "Osserviamo:\n"
            "- come viene espresso un intento in linguaggio naturale,\n"
            "- come un LLM genera il codice,\n"
            "- come il codice viene valutato o corretto,\n"
            "- l'esperienza d'uso e il carico cognitivo."
        ),
        "lang_note": (
            "Nota: il **codice generato è sempre in JavaScript**. "
            "La lingua influenza solo testi e descrizioni."
        ),
        "profile_header": "\U0001f464 Profilo utente",
        "profile_label": "Seleziona il tuo profilo",
        "non_expert_label": "Non-expert (solo descrizioni)",
        "expert_label": "Expert (con metodi JavaScript)",
        "non_expert_info": (
            "Modalità **Non-expert**:\n"
            "- vedrai solo descrizioni testuali\n"
            "- nessun metodo JavaScript esplicito\n"
            "- focus su comprensione e usabilità"
        ),
        "expert_info": (
            "Modalità **Expert**:\n"
            "- vedrai accessor e setter JavaScript reali\n"
            "- potrai correggere manualmente il codice\n"
            "- focus su controllo e precisione"
        ),
        "id_header": "\U0001f511 ID partecipante",
        "id_label": "Inserisci un ID anonimo",
        "id_placeholder": "es. user_01, exp_A12, test_003",
        "id_confirm": "Conferma ID",
        "id_ok": "ID impostato correttamente",
        "id_err": "Inserisci un ID valido.",
        "id_warn": "Devi impostare un ID prima di continuare.",
        "start_header": "\U0001f680 Avvio dello studio",
        "start_desc": (
            "Quando sei pronta/o:\n"
            "- passerai alla **selezione dello scenario**,\n"
            "- leggerai una descrizione IF–THEN,\n"
            "- interagirai con un LLM,\n"
            "- valuterai o correggerai il codice prodotto."
        ),
        "start_btn": "\u25b6 Inizia lo studio",
        "registration_ok": "Registrazione completata. Ordine condizioni: **{order}**",
        "registration_existing": "Bentornato! La sessione precedente \u00e8 stata ripristinata.",
        "progress_label": "Scenari completati: {n}",
        "condition_a": "Singola generazione (A)",
        "condition_b": "Assistente iterativo (B)",
    },
    "en": {
        "title": "Filter Code User Study",
        "intro": (
            "Welcome to the experimental study.\n\n"
            "This study analyzes **how expert and non-expert users collaborate "
            "with language models (LLMs)** to generate **JavaScript Filter Code** "
            "for *IFTTT-style* automations.\n\n"
            "We observe:\n"
            "- how an intent is expressed in natural language,\n"
            "- how an LLM generates the code,\n"
            "- how the code is evaluated or corrected,\n"
            "- the user experience and cognitive load."
        ),
        "lang_note": (
            "Note: the **generated code is always in JavaScript**. "
            "Language only affects text and descriptions."
        ),
        "profile_header": "\U0001f464 User profile",
        "profile_label": "Select your profile",
        "non_expert_label": "Non-expert (descriptions only)",
        "expert_label": "Expert (with JavaScript methods)",
        "non_expert_info": (
            "**Non-expert** mode:\n"
            "- you will see text descriptions only\n"
            "- no explicit JavaScript methods\n"
            "- focus on comprehension and usability"
        ),
        "expert_info": (
            "**Expert** mode:\n"
            "- you will see real JavaScript accessors and setters\n"
            "- you can manually correct the code\n"
            "- focus on control and precision"
        ),
        "id_header": "\U0001f511 Participant ID",
        "id_label": "Enter an anonymous ID",
        "id_placeholder": "e.g. user_01, exp_A12, test_003",
        "id_confirm": "Confirm ID",
        "id_ok": "ID set successfully",
        "id_err": "Please enter a valid ID.",
        "id_warn": "You must set an ID before continuing.",
        "start_header": "\U0001f680 Start the study",
        "start_desc": (
            "When you are ready:\n"
            "- you will move to **scenario selection**,\n"
            "- read an IF–THEN description,\n"
            "- interact with an LLM,\n"
            "- evaluate or correct the generated code."
        ),
        "start_btn": "\u25b6 Start the study",
        "registration_ok": "Registration complete. Condition order: **{order}**",
        "registration_existing": "Welcome back! Previous session restored.",
        "progress_label": "Scenarios completed: {n}",
        "condition_a": "Single generation (A)",
        "condition_b": "Iterative assistant (B)",
    },
}

def T(key: str) -> str:
    return _T.get(lang, _T["en"]).get(key, key)

# ============================================================
# TITLE & INTRO
# ============================================================

st.title(T("title"))
st.markdown(T("intro"))
st.caption(T("lang_note"))

st.markdown("---")

# ============================================================
# USER TYPE
# ============================================================

st.subheader(T("profile_header"))

user_type = st.radio(
    T("profile_label"),
    ["non_expert", "expert"],
    format_func=lambda x:
        T("non_expert_label") if x == "non_expert"
        else T("expert_label"),
    horizontal=True,
)

st.session_state.user_type = user_type

if user_type == "non_expert":
    st.info(T("non_expert_info"))
else:
    st.info(T("expert_info"))

st.markdown("---")

# ============================================================
# USER ID
# ============================================================

st.subheader(T("id_header"))

if "user_id" not in st.session_state:
    st.session_state.user_id = ""

user_id_input = st.text_input(
    T("id_label"),
    value=st.session_state.user_id,
    placeholder=T("id_placeholder"),
)

if st.button(T("id_confirm")):
    uid = user_id_input.strip()
    if uid:
        st.session_state.user_id = uid
        st.success(f'{T("id_ok")}: `{uid}`')
    else:
        st.error(T("id_err"))

if not st.session_state.user_id:
    st.warning(T("id_warn"))
    st.stop()

st.markdown("---")

# ============================================================
# START STUDY
# ============================================================

st.subheader(T("start_header"))
st.markdown(T("start_desc"))

# Show progress if already registered
if st.session_state.get("study_registration"):
    reg = st.session_state["study_registration"]
    progress = get_participant_progress(st.session_state.user_id)
    n_done = progress["n_completed"]
    total = len(reg["scenario_assignment"])
    st.info(T("progress_label").format(n=f"{n_done}/{total}"))
    if reg.get("already_registered"):
        st.caption(T("registration_existing"))

if st.button(T("start_btn")):
    # Build scenario pool from study set (both pools, since assignment balances across all)
    scenario_pool = STUDY.get("non_expert", []) + STUDY.get("expert", [])

    reg = register_participant(
        participant_id=st.session_state.user_id,
        user_type=user_type,
        lang=lang,
        scenario_pool=scenario_pool,
    )
    st.session_state["study_registration"] = reg
    st.session_state["scenario_assignment"] = reg["scenario_assignment"]
    st.session_state["condition_order"] = reg["condition_order"]

    order_display = " \u2192 ".join(
        T("condition_a") if c == "single_shot" else T("condition_b")
        for c in reg["condition_order"]
    )
    if not reg.get("already_registered"):
        st.success(T("registration_ok").format(order=order_display))
    st.switch_page("pages/2_Studio.py")
