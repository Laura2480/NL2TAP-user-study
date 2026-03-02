# Home.py — Entry point dello studio (LEAN & CORRETTO)

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st

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
# TITLE & INTRO
# ============================================================

st.title("Filter Code User Study")

st.markdown("""
Benvenuta/o nello studio sperimentale.

Questo studio analizza **come utenti esperti e non esperti collaborano con modelli di linguaggio (LLM)**
per generare **Filter Code JavaScript** per automazioni *IFTTT-style*.

Osserviamo:
- come viene espresso un intento in linguaggio naturale,
- come un LLM genera il codice,
- come il codice viene valutato o corretto,
- l’esperienza d’uso e il carico cognitivo.
""")

st.markdown("---")

# ============================================================
# LANGUAGE
# ============================================================

st.subheader("Lingua / Language")

lang = st.radio(
    "Scegli la lingua",
    ["it", "en"],
    format_func=lambda x: "\U0001f1ee\U0001f1f9 Italiano" if x == "it" else "\U0001f1ec\U0001f1e7 English",
    horizontal=True,
)

st.session_state.lang = lang

st.caption(
    "Nota: il **codice generato è sempre in JavaScript**. "
    "La lingua influenza solo testi e descrizioni."
)

st.markdown("---")

# ============================================================
# USER TYPE
# ============================================================

st.subheader("Profilo utente")

user_type = st.radio(
    "Seleziona il tuo profilo",
    ["non_expert", "expert"],
    format_func=lambda x:
        "Non-expert (solo descrizioni)" if x == "non_expert"
        else "Expert (con metodi JavaScript)",
    horizontal=True
)

st.session_state.user_type = user_type

if user_type == "non_expert":
    st.info(
        "Modalità **Non-expert**:\n"
        "- vedrai solo descrizioni testuali\n"
        "- nessun metodo JavaScript esplicito\n"
        "- focus su comprensione e usabilità"
    )
else:
    st.info(
        "Modalità **Expert**:\n"
        "- vedrai accessor e setter JavaScript reali\n"
        "- potrai correggere manualmente il codice\n"
        "- focus su controllo e precisione"
    )

st.markdown("---")

# ============================================================
# USER ID
# ============================================================

st.subheader("ID partecipante")

if "user_id" not in st.session_state:
    st.session_state.user_id = ""

user_id_input = st.text_input(
    "Inserisci un ID anonimo",
    value=st.session_state.user_id,
    placeholder="es. user_01, exp_A12, test_003"
)

if st.button("Conferma ID"):
    uid = user_id_input.strip()
    if uid:
        st.session_state.user_id = uid
        st.success(f"ID impostato correttamente: `{uid}`")
    else:
        st.error("Inserisci un ID valido.")

if not st.session_state.user_id:
    st.warning("⚠ Devi impostare un ID prima di continuare.")
    st.stop()

st.markdown("---")

# ============================================================
# START STUDY
# ============================================================

st.subheader("Avvio dello studio")

st.markdown("""
Quando sei pronta/o:
- passerai alla **selezione dello scenario**,
- leggerai una descrizione IF–THEN,
- interagirai con un LLM,
- valuterai o correggerai il codice prodotto.
""")

if st.button("Inizia lo studio"):
    st.switch_page("pages/2_Studio.py")
