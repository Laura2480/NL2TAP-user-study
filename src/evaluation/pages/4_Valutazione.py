# pages/4_Valutazione.py — Valutazione finale Filter Code

from code_editor import code_editor
import os, sys, json, re
from pathlib import Path
from datetime import datetime

import streamlit as st
from utils.study_utils import STUDY
import src.code_parsing.parser as parser_mod

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# ============================================================
# CONFIG
# ============================================================

RESULTS_PATH = Path("results/user_study_results.jsonl")
RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="Valutazione", layout="wide")
st.title("4 — Valutazione del Filter Code")

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

attempt_log = st.session_state.get("attempt_log", [])
if not attempt_log:
    st.warning("⚠ Nessun tentativo registrato.")
    st.stop()

# ============================================================
# STATE
# ============================================================

if "editor_last_submit" not in st.session_state:
    st.session_state["editor_last_submit"] = {}

if "applied_code" not in st.session_state:
    st.session_state["applied_code"] = {}

# ============================================================
# SCENARIO / ATTEMPT  (FIX: attempt per scenario)
# ============================================================

# inizializza stato per-attempt-per-scenario
if "selected_attempt_by_scenario" not in st.session_state:
    st.session_state["selected_attempt_by_scenario"] = {}

scenario_codes = sorted({a["scenario_code"] for a in attempt_log})
scenario_code = st.selectbox("Scenario", scenario_codes)

scenario_attempts = [a for a in attempt_log if a["scenario_code"] == scenario_code]
attempt_nums = sorted(a["attempt"] for a in scenario_attempts)

# recupera l'attempt SOLO per questo scenario
default_attempt = st.session_state["selected_attempt_by_scenario"].get(scenario_code)

# fallback sicuro se non esiste o non è valido
if default_attempt not in attempt_nums:
    default_attempt = attempt_nums[-1]

attempt_num = st.selectbox(
    "Tentativo",
    attempt_nums,
    index=attempt_nums.index(default_attempt)
)

# salva lo stato SOLO per questo scenario
st.session_state["selected_attempt_by_scenario"][scenario_code] = attempt_num

current = next(a for a in scenario_attempts if a["attempt"] == attempt_num)
state_key = f"{scenario_code}__{attempt_num}"


# ============================================================
# SCENARIO INFO
# ============================================================

SC = None
for group in ("non_expert", "expert"):
    for s in STUDY[group]:
        if s["code"] == scenario_code:
            SC = s
            break
    if SC:
        break

if not SC:
    st.error("Scenario non trovato.")
    st.stop()

def T(obj, key):
    if lang == "en":
        return obj.get(f"{key}_en") or obj.get(f"{key}_it", "")
    return obj.get(f"{key}_it") or obj.get(f"{key}_en", "")

st.subheader(f"{SC['code']} — {T(SC,'title')}")
st.write(T(SC, "background"))

# ============================================================
# INTENT + GENERATED CODE
# ============================================================

st.markdown("### 🧾 Intent dell’utente")
st.code(current["user_intent"], language="markdown")

generated_code = current["llm_output"] or ""

st.markdown("### 🤖 Codice generato dal modello")
st.code(generated_code or "// Nessun output", language="javascript")

# ============================================================
# NORMALIZATION
# ============================================================

def normalize_setter(m: str) -> str:
    if not m:
        return ""
    m = re.sub(r"\(.*?\)", "", m)
    m = re.sub(r"\s+.*$", "", m)
    return m.split(":", 1)[0].strip()

def normalize_getter(g: str) -> str:
    if g.startswith("Meta.currentUserTime"):
        return "Meta.currentUserTime"
    return g

## ============================================================
# EXPERT — EDITOR
# ============================================================
edited_code = None
expert_claim_fixed = "not_required"  # default assoluto
expert_gave_up = None

if user_type == "expert":
    st.markdown("---")
    st.markdown("## ✍️ Correzione (Expert)")

    # default assoluto: llm_output
    if state_key not in st.session_state["editor_last_submit"]:
        st.session_state["editor_last_submit"][state_key] = generated_code

    editor_value = (
        st.session_state["applied_code"].get(state_key)
        or st.session_state["editor_last_submit"][state_key]
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
        options={"wrap": True}
    )

    # submit = unica fonte di verità per l'applicazione
    if isinstance(resp, dict) and resp.get("type") == "submit":
        if isinstance(resp.get("text"), str):
            st.session_state["editor_last_submit"][state_key] = resp["text"]
            st.session_state["applied_code"][state_key] = resp["text"]
            st.success("✅ Modifiche applicate. Questo codice verrà valutato.")

    edited_code = st.session_state["editor_last_submit"][state_key]

    # stato visibile sempre
    st.markdown("### Stato del codice")
    if state_key in st.session_state["applied_code"]:
        st.info("✔ Codice applicato")
    else:
        st.warning("ℹ Nessuna modifica applicata: verrà valutato il codice generato.")

    applied = st.session_state["applied_code"].get(state_key)

    # VERA CORREZIONE solo se esiste applied e differisce dal codice generato
    has_real_fix = (
        isinstance(applied, str)
        and applied.strip() != ""
        and applied.strip() != generated_code.strip()
    )

    st.markdown("### Esito della correzione")

    # etichette UI (italiane) -> valori canonici (inglesi)
    UI_TO_CANON = {
        "non richiesto": "not_required",
        "sì": "yes",
        "no": "no",
    }
    CANON_TO_UI = {v: k for k, v in UI_TO_CANON.items()}

    if not has_real_fix:
        # radio sempre visibile (in italiano), ma valore SALVATO forzato
        _ = st.radio(
            "Ritieni di aver corretto correttamente il codice?",
            ["non richiesto", "sì", "no"],
            index=0,
            horizontal=True,
            key=f"expert_claim_fixed_{state_key}_locked"
        )
        expert_claim_fixed = "not_required"  # valore canonico
        st.caption(
            "Non risulta una correzione applicata diversa dal codice generato: "
            "esito impostato automaticamente su «non richiesto»."
        )
    else:
        # qui ha senso chiedere davvero l'esito (UI in italiano, salvataggio canonico)
        ui_choice = st.radio(
            "Ritieni di aver corretto correttamente il codice?",
            ["sì", "no"],
            horizontal=True,
            key=f"expert_claim_fixed_{state_key}"
        )
        expert_claim_fixed = UI_TO_CANON[ui_choice]  # "yes" / "no"

    expert_gave_up = st.checkbox("Non riesco a correggere")

# ============================================================
# FINAL CODE
# ============================================================

final_code_used = st.session_state["applied_code"].get(
    state_key,
    generated_code
)

# ============================================================
# EVALUATION
# ============================================================

st.markdown("---")
st.markdown("## 🧑‍⚖️ Valutazione")

correct = st.radio(
    "Il Filter Code finale è corretto?",
    ["yes", "no"],
    horizontal=True
)

notes = st.text_area("Note valutatore", height=140)

# ============================================================
# SAVE + NAVIGATION
# ============================================================

if st.button("💾 Salva valutazione"):
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
    })

    with open(RESULTS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    if correct == "yes":
        # 👉 PASSA AL PROSSIMO SCENARIO
        st.session_state["scenario_index"] = (
            st.session_state.get("scenario_index", 0) + 1
        )

        # pulizia stato transitorio
        st.session_state.pop("forced_scenario", None)
        st.session_state.pop("resume_from_eval", None)
        st.session_state.pop("prefill_prompt", None)

        st.switch_page("pages/2_Selezione_scenario.py")

    else:
        # 👉 TORNA A PAGINA 3, STESSO SCENARIO
        st.session_state["prefill_prompt"] = current["user_intent"]
        st.session_state["forced_scenario"] = scenario_code
        st.session_state["resume_from_eval"] = True
        st.switch_page("pages/3_Generatore_Filter_Code.py")
