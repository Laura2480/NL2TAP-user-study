# pages/2_Selezione_scenario.py — Selezione scenario (UX + i18n corretta)

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st

from utils.study_utils import STUDY, SERVICES, TRIGGERS_LIST, ACTIONS_LIST
from utils.i18n_scenario import translate_scenario_bundle

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(page_title="Selezione scenario", layout="wide")
st.title("2 — Selezione scenario")

# ============================================================
# SESSION CHECK
# ============================================================

user_id = st.session_state.get("user_id", "").strip()
if not user_id:
    st.error("⚠ Devi prima inserire un ID utente nella Home.")
    st.stop()

user_type = st.session_state.get("user_type", "non_expert")
lang = st.session_state.get("lang", "it")

st.info(f"User ID: `{user_id}` — Modalità: **{user_type}**")

# ============================================================
# SCENARIO LIST (study_set, già bilingue)
# ============================================================

SCENARIOS = STUDY["non_expert"] if user_type == "non_expert" else STUDY["expert"]

def T(obj: dict, key: str) -> str:
    if not obj:
        return ""
    if lang == "en":
        return obj.get(f"{key}_en") or obj.get(f"{key}_it", "")
    return obj.get(f"{key}_it") or obj.get(f"{key}_en", "")

labels = [f"{sc['code']} — {T(sc,'title')}" for sc in SCENARIOS]

if "scenario_index" not in st.session_state:
    st.session_state["scenario_index"] = 0

num_scenarios = len(SCENARIOS)

# recupera indice, default 0
raw_idx = st.session_state.get("scenario_index", 0)

# clamp difensivo
safe_idx = max(0, min(raw_idx, num_scenarios - 1))

idx = st.selectbox(
    "Scegli uno scenario",
    options=list(range(num_scenarios)),
    format_func=lambda i: labels[i],
    index=safe_idx
)

# riallinea SEMPRE lo stato
st.session_state["scenario_index"] = idx
SC = SCENARIOS[idx]


# ============================================================
# SCENARIO PREVIEW
# ============================================================

st.markdown("---")
st.markdown("## 📘 Scenario selezionato")

st.write(f"**Codice scenario:** `{SC['code']}`")
st.subheader(T(SC, "title"))
st.write(T(SC, "background"))

# ============================================================
# BUILD SCENARIO-SPECIFIC CATALOG
# ============================================================

# Filtra SOLO ciò che serve per questo scenario
services = [s for s in SERVICES if s["service_slug"] in SC["services"]]
triggers = [t for t in TRIGGERS_LIST if t["api_endpoint_slug"] in SC["trigger_apis"]]
actions  = [a for a in ACTIONS_LIST  if a["api_endpoint_slug"] in SC["action_apis"]]

with st.spinner("🌍 Preparazione contenuti dello scenario…"):
    CAT = translate_scenario_bundle(
        scenario_code=SC["code"],
        services=services,
        triggers=triggers,
        actions=actions,
        lang=lang,
    )

SERVICE_INDEX = {s["service_slug"]: s for s in CAT["services"]}
TRIGGER_INDEX = {t["api_endpoint_slug"]: t for t in CAT["triggers"]}
ACTION_INDEX  = {a["api_endpoint_slug"]: a for a in CAT["actions"]}

# ============================================================
# SERVICES (CONTESTO VISIVO)
# ============================================================

st.markdown("### 🔧 Servizi coinvolti")

cols = st.columns(len(SC["services"]))

for col, slug in zip(cols, SC["services"]):
    svc = SERVICE_INDEX.get(slug)
    with col:
        if not svc:
            st.warning(f"Servizio '{slug}' non trovato")
            continue

        st.image(svc["image_url"], width=80)
        st.markdown(f"**{svc['name']}**")  # nome NON tradotto
        if svc.get("description"):
            st.caption(svc["description"])  # tradotto

# ============================================================
# LOGICAL STRUCTURE (HIGH LEVEL)
# ============================================================

st.markdown("---")
st.markdown("## ⚡ Struttura logica della regola")

col_left, col_right = st.columns(2)

with col_left:
    st.markdown("### 🎯 Trigger")
    for trig_api in SC["trigger_apis"]:
        trig = TRIGGER_INDEX.get(trig_api)
        if not trig:
            st.warning(f"Trigger '{trig_api}' non trovato")
            continue

        st.markdown(f"**{trig['name']}**")
        if trig.get("description"):
            st.caption(trig["description"])

with col_right:
    st.markdown("### ⚙️ Action(s)")
    for act_api in SC["action_apis"]:
        act = ACTION_INDEX.get(act_api)
        if not act:
            st.warning(f"Action '{act_api}' non trovata")
            continue

        st.markdown(f"**{act['name']}**")
        if act.get("description"):
            st.caption(act["description"])

# ============================================================
# NAVIGATION
# ============================================================

st.markdown("---")
st.markdown("""
Nella prossima pagina potrai:

- selezionare **quali parametri** (trigger e action) sono ammessi,
- descrivere la regola in linguaggio naturale,
- lasciare che il modello LLM generi il **Filter Code**.
""")

if st.button("➡ Continua: definisci i parametri della regola"):
    st.switch_page("pages/3_Generatore_Filter_Code.py")
