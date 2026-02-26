# pages/3_Generatore_Filter_Code.py — Generatore Filter Code (UX FINALE, COERENTE)

import os, sys, re
from datetime import datetime
import requests
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from utils.study_utils import STUDY, SERVICES, TRIGGERS_LIST, ACTIONS_LIST
from utils.i18n_scenario import translate_scenario_bundle

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(page_title="Generatore Filter Code", layout="wide")
st.title("3 — Generazione del Filter Code")

LLM_ENDPOINT = "http://localhost:1234/api/v0/chat/completions"
AVAILABLE_MODELS = {
    "DeepSeek FT 6.7B": "ft_2_deepseek_merged",
    "Qwen FT 7.6B":     "ft_2_qwen_merged",
}

# ============================================================
# SESSION CHECK
# ============================================================

user_id = st.session_state.get("user_id", "").strip()
if not user_id:
    st.error("⚠ Devi prima inserire un ID utente.")
    st.stop()

user_type = st.session_state.get("user_type", "non_expert")
lang = st.session_state.get("lang", "it")

st.info(f"User ID: `{user_id}` — Modalità: **{user_type}**")

# ============================================================
# SCENARIO SELECTION (CON RIENTRO DA PAGINA 4)
# ============================================================

SCENARIOS = STUDY["non_expert"] if user_type == "non_expert" else STUDY["expert"]

if st.session_state.get("resume_from_eval"):
    forced = st.session_state.get("forced_scenario")
    if forced:
        for i, s in enumerate(SCENARIOS):
            if s["code"] == forced:
                st.session_state["scenario_index"] = i
                break
    st.session_state["resume_from_eval"] = False

SC = SCENARIOS[st.session_state.get("scenario_index", 0)]

# ============================================================
# I18N
# ============================================================

def T(obj: dict, key: str) -> str:
    if not obj:
        return ""
    if lang == "en":
        return obj.get(f"{key}_en") or obj.get(f"{key}_it", "")
    return obj.get(f"{key}_it") or obj.get(f"{key}_en", "")

# ============================================================
# SCENARIO HEADER + GUIDANCE
# ============================================================

st.subheader(f"{SC['code']} — {T(SC,'title')}")

st.markdown("### 📘 Contesto")
st.write(T(SC, "background"))

if T(SC, "if_then"):
    st.markdown("### 🔀 Regola IF–THEN")
    st.info(T(SC, "if_then"))

examples = SC.get("intent_examples_it", [])
if examples:
    st.markdown("### 🧠 Esempi di intent")
    for ex in examples:
        st.markdown(f"- {ex}")

# ============================================================
# BUILD SCENARIO-SPECIFIC CATALOG
# ============================================================

services = [s for s in SERVICES if s["service_slug"] in SC["services"]]
triggers = [t for t in TRIGGERS_LIST if t["api_endpoint_slug"] in SC["trigger_apis"]]
actions  = [a for a in ACTIONS_LIST  if a["api_endpoint_slug"] in SC["action_apis"]]

with st.spinner("🌍 Preparazione parametri dello scenario…"):
    CAT = translate_scenario_bundle(
        scenario_code=SC["code"],
        services=services,
        triggers=triggers,
        actions=actions,
        lang=lang,
    )

TRIGGER_INDEX = {t["api_endpoint_slug"]: t for t in CAT["triggers"]}
ACTION_INDEX  = {a["api_endpoint_slug"]: a for a in CAT["actions"]}

# ============================================================
# SESSION STORAGE
# ============================================================

st.session_state.setdefault("selected_ingredients", {})
st.session_state.setdefault("selected_setters", {})

sel_ing = st.session_state["selected_ingredients"].setdefault(SC["code"], set())
sel_set = st.session_state["selected_setters"].setdefault(SC["code"], set())

# ============================================================
# UTILS
# ============================================================

def normalize_setter(method: str) -> str:
    if not method:
        return ""
    method = re.sub(r"\(.*?\)", "", method)
    method = re.sub(r"\s+.*$", "", method)
    return method.split(":", 1)[0].strip()

def strip_llm_markdown(code: str) -> str:
    if not code:
        return ""
    code = code.strip()
    if code.startswith("```"):
        code = re.sub(r"^```[a-zA-Z]*\n?", "", code)
        code = re.sub(r"\n?```$", "", code)
    return code.strip()

# ============================================================
# GETTER SELECTION
# ============================================================

st.markdown("---")
st.markdown("## 🎯 Parametri del Trigger")

for trig_api in SC["trigger_apis"]:
    trig = TRIGGER_INDEX.get(trig_api)
    if not trig:
        continue

    st.markdown(f"### {trig['name']}")
    if trig.get("description"):
        st.caption(trig["description"])

    cols = st.columns(2)
    for i, ing in enumerate(trig.get("ingredients", [])):
        key = ing.get("filter_code_key")
        if not key:
            continue

        with cols[i % 2]:
            label = ing.get("name", "")
            desc  = ing.get("description", "")

            display = f"**{label}**\n\n{desc}"
            if user_type == "expert":
                display += f"\n\n`{key}`"

            checked = key in sel_ing
            if st.checkbox(display, value=checked, key=f"{SC['code']}_ing_{key}"):
                sel_ing.add(key)
            else:
                sel_ing.discard(key)

# ============================================================
# SETTER SELECTION
# ============================================================

st.markdown("---")
st.markdown("## ⚙️ Parametri dell’Action")

for act_api in SC["action_apis"]:
    act = ACTION_INDEX.get(act_api)
    if not act:
        continue

    st.markdown(f"### {act['name']}")
    if act.get("description"):
        st.caption(act["description"])

    cols = st.columns(2)
    for i, field in enumerate(act.get("fields", [])):
        method = field.get("filter_code_method")
        if not method:
            continue

        norm = normalize_setter(method)

        with cols[i % 2]:
            label = field.get("label", "")
            helper = field.get("helper_text", "")

            display = f"**{label}**\n\n{helper}"
            if user_type == "expert":
                display += f"\n\n`{method}`"

            checked = norm in sel_set
            if st.checkbox(display, value=checked, key=f"{SC['code']}_set_{norm}"):
                sel_set.add(norm)
            else:
                sel_set.discard(norm)

# ============================================================
# USER INTENT (CON RIPRISTINO)
# ============================================================

st.markdown("---")
st.markdown("## ✍️ Descrivi la regola")

st.markdown("### 🔁 Riepilogo della regola")
st.write(T(SC, "background"))
if T(SC, "if_then"):
    st.info(T(SC, "if_then"))

examples = SC.get("intent_examples_it", [])
if examples:
    for ex in examples:
        st.markdown(f"- {ex}")

# inizializza una volta sola
if "user_intent_text" not in st.session_state:
    st.session_state["user_intent_text"] = ""

# se torni da pagina 4, prefill UNA SOLA VOLTA
if st.session_state.get("prefill_prompt"):
    st.session_state["user_intent_text"] = st.session_state["prefill_prompt"]
    st.session_state["prefill_prompt"] = None  # segnale consumato

user_intent = st.text_area(
    "",
    key="user_intent_text",
    height=180,
    placeholder=T(SC, "background")
)

# ============================================================
# MODEL + PROMPT
# ============================================================

st.markdown("### 🤖 Modello LLM")
model_choice = st.selectbox("Modello", list(AVAILABLE_MODELS.keys()))
model_identifier = AVAILABLE_MODELS[model_choice]

def build_prompt() -> str:
    p = []
    p.append("You are an expert JavaScript developer with knowledge of IFTTT Filter Code.")
    p.append("Generate JavaScript Filter Code for the following intent:\n")
    p.append(user_intent.strip() + "\n")

    if sel_ing:
        p.append("Use ONLY these accessors:")
        for g in sorted(sel_ing):
            p.append(f"- `{g}`")

    if sel_set:
        p.append("\nUse ONLY these setter methods:")
        for s in sorted(sel_set):
            p.append(f"- `{s}`")

    p.append("\nWrite ONLY the JavaScript Filter Code. No explanations.")
    return "\n".join(p)

# ============================================================
# GENERATION
# ============================================================

if st.button("🚀 Genera Filter Code"):
    if not user_intent.strip():
        st.warning("Inserisci una descrizione della regola.")
        st.stop()

    payload = {
        "model": model_identifier,
        "messages": [{"role": "user", "content": build_prompt()}],
        "temperature": 0.0,
        "max_tokens": 512,
        "stream": False
    }

    with st.spinner("🤖 Generazione in corso…"):
        try:
            r = requests.post(LLM_ENDPOINT, json=payload, timeout=120)
            r.raise_for_status()
            llm_out = strip_llm_markdown(
                r.json()["choices"][0]["message"]["content"]
            )
        except Exception as e:
            st.error(f"Errore LLM: {e}")
            llm_out = ""

    st.markdown("### 🧾 Filter Code generato")
    st.code(llm_out or "// Nessun output", language="javascript")

    # ========================================================
    # LOG ATTEMPT (FOR PAGE 4)
    # ========================================================

    st.session_state.setdefault("attempt_count", {})
    count = st.session_state["attempt_count"].get(SC["code"], 0) + 1
    st.session_state["attempt_count"][SC["code"]] = count

    st.session_state.setdefault("attempt_log", []).append({
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": user_id,
        "scenario_code": SC["code"],
        "row_index": SC["row_index"],
        "attempt": count,
        "user_intent": user_intent.strip(),
        "llm_output": llm_out,
        "selected_ingredients": sorted(sel_ing),
        "selected_setters": sorted(sel_set),
    })

    st.session_state["selected_attempt"] = count
    st.success("Codice generato. Vai alla valutazione.")
