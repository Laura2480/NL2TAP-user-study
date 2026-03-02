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
    _loading_banner.markdown(
        "<div style='text-align:center; padding:6rem 0;'>"
        "<h2 style='color:#555;'>Caricamento in corso</h2>" 
        "<div style='margin:2rem auto; width:40px; height:40px; "
        "border:4px solid #eee; border-top:4px solid #555; "
        "border-radius:50%; animation:spin 1s linear infinite;'></div>"
        "<style>@keyframes spin{to{transform:rotate(360deg)}}</style>"
        "</div>",
        unsafe_allow_html=True,
    )

# --- Heavy imports AFTER banner is visible ---
import re, json
from datetime import datetime
from pathlib import Path

import requests
import streamlit.components.v1 as components

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from code_editor import code_editor
from utils.study_utils import STUDY
from code_parsing.feedback import run_l1_validation, run_l2_validation, L1Report, L2Report
from code_parsing.flowchart import render_flowchart_html, render_code_flowchart_html
from code_parsing.catalog_validator import build_display_labels

LLM_ENDPOINT = "http://localhost:1234/api/v0/chat/completions"
AVAILABLE_MODELS = {
    "Qwen": "ft_2_qwen_merged",
}

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

# ============================================================
# I18N HELPER
# ============================================================

def T(obj: dict, key: str) -> str:
    if not obj:
        return ""
    if lang == "en":
        return obj.get(f"{key}_en") or obj.get(f"{key}_it", "")
    return obj.get(f"{key}_it") or obj.get(f"{key}_en", "")

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
        st.session_state["_studio_initialized"] = False
        for k in ("generation_done", "generated_code", "l1_report", "l2_report"):
            st.session_state.pop(k, None)
        st.rerun()

    st.session_state["scenario_index"] = idx
    SC = SCENARIOS[idx]

    # ---- b) Catalog (pre-enriched, no runtime translation needed) ----
    CAT = SC.get("catalog", {}).get(lang) or SC.get("catalog", {}).get("en", {})

    SERVICE_INDEX = {s["service_slug"]: s for s in CAT.get("services", [])}
    TRIGGER_INDEX = {t["api_endpoint_slug"]: t for t in CAT.get("triggers", [])}
    ACTION_INDEX  = {a["api_endpoint_slug"]: a for a in CAT.get("actions", [])}

    # ---- c) Servizi coinvolti ----
    st.markdown("---")
    st.markdown("#### Servizi")
    svc_cols = st.columns(min(len(SC["services"]), 4))
    for col, slug in zip(svc_cols, SC["services"]):
        svc = SERVICE_INDEX.get(slug)
        with col:
            if not svc:
                st.warning(f"'{slug}' ?")
                continue
            st.image(svc["image_url"], width=56)
            st.caption(svc["name"])

    # ---- d) Trigger + Ingredient selection ----
    st.markdown("---")
    st.markdown("#### Trigger — Ingredient")

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
    if col_sa.button("Seleziona tutto", key=f"sel_all_ing_{SC['code']}"):
        for fck in _all_ing_keys:
            st.session_state[f"ing_{SC['code']}_{fck}"] = True
        sel_ing.update(_all_ing_keys)
        st.rerun()
    if col_da.button("Deseleziona", key=f"desel_ing_{SC['code']}"):
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
    st.markdown("#### Action — Setter")

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
    if col_sa2.button("Seleziona tutto", key=f"sel_all_set_{SC['code']}"):
        for m in _all_set_methods:
            st.session_state[f"set_{SC['code']}_{m}"] = True
        sel_set.update(_all_set_methods)
        st.rerun()
    if col_da2.button("Deseleziona", key=f"desel_set_{SC['code']}"):
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
        st.markdown("#### Azioni bloccabili")
        for ns, name, skip_call in _skip_targets:
            if user_type == "expert":
                st.markdown(f"- **{name}** — `{skip_call}`")
            else:
                st.markdown(f"- **{name}** — bloccabile")

    # ---- g) Background + IF-THEN ----
    st.markdown("---")
    st.markdown("#### Contesto")
    st.write(T(SC, "background"))

    if_then = T(SC, "if_then")
    if if_then:
        st.info(if_then)

    # ---- h) Esempi intent ----
    examples = SC.get("intent_examples_it" if lang == "it" else "intent_examples_en", [])
    if not examples:
        examples = SC.get("intent_examples_it", [])
    if examples:
        st.markdown("#### Esempi di intent")
        for ex in examples:
            st.markdown(f"- {ex}")

    # ---- i) Modello LLM ----
    st.markdown("---")
    st.markdown("#### Modello LLM")
    model_choice = st.selectbox(
        "Modello LLM",
        list(AVAILABLE_MODELS.keys()),
        label_visibility="collapsed",
    )
    model_identifier = AVAILABLE_MODELS[model_choice]


# ============================================================
# MAIN — Header
# ============================================================

_loading_banner.empty()
st.session_state["_studio_initialized"] = True

st.title(f"{SC['code']} — {T(SC, 'title')}")

# ============================================================
# MAIN — Intent + Generazione
# ============================================================

st.markdown("## Descrivi la regola")

# Prefill on return from failed evaluation
if "user_intent_text" not in st.session_state:
    st.session_state["user_intent_text"] = ""

if st.session_state.get("prefill_prompt"):
    st.session_state["user_intent_text"] = st.session_state["prefill_prompt"]
    st.session_state["prefill_prompt"] = None

user_intent = st.text_area(
    "",
    key="user_intent_text",
    height=150,
    placeholder=T(SC, "background"),
)


def build_prompt() -> str:
    p = [
        "You are an expert JavaScript developer with knowledge of IFTTT Filter Code.",
        "Generate JavaScript Filter Code for the following intent:\n",
        user_intent.strip() + "\n",
    ]

    # Always include trigger info (namespace + all available ingredients)
    trigger_lines = []
    all_ingredients = []
    for trig_api in SC["trigger_apis"]:
        trig = TRIGGER_INDEX.get(trig_api)
        if not trig:
            continue
        trig_ns = trig.get("namespace", "")
        trig_name = trig.get("name", trig_api)
        if trig_ns:
            trigger_lines.append(f"- `{trig_ns}` — {trig_name}")
        for ing in trig.get("ingredients", []):
            fck = ing.get("filter_code_key", "")
            if fck:
                ing_name = ing.get("name", fck)
                all_ingredients.append((fck, ing_name))

    if trigger_lines:
        p.append("Available trigger:")
        p.extend(trigger_lines)

    if sel_ing:
        p.append("\nUse ONLY these accessors:")
        for g in sorted(sel_ing):
            p.append(f"- `{g}`")

    # Always include action namespaces + skip methods
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

    # Global time API (always available, independent of trigger)
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


# ---- Generate button ----
if st.button("Genera Filter Code"):
    if not user_intent.strip():
        st.warning("Inserisci una descrizione della regola.")
        st.stop()

    final_prompt = build_prompt()

    with st.expander("Prompt inviato all'LLM", expanded=False):
        st.code(final_prompt, language="markdown")

    payload = {
        "model": model_identifier,
        "messages": [{"role": "user", "content": final_prompt}],
        "temperature": 0.0,
        "max_tokens": 512,
        "stream": False,
    }

    with st.spinner("Generazione in corso..."):
        try:
            r = requests.post(LLM_ENDPOINT, json=payload, timeout=120)
            r.raise_for_status()
            llm_out = strip_llm_markdown(
                r.json()["choices"][0]["message"]["content"]
            )
        except Exception as e:
            st.error(f"Errore LLM: {e}")
            llm_out = ""

    st.session_state["generated_code"] = llm_out
    st.session_state["generation_done"] = True

    # Log attempt
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

    # Run L1 automatically
    if llm_out:
        l1 = run_l1_validation(
            code=llm_out,
            trigger_slugs=SC["trigger_apis"],
            action_slugs=SC["action_apis"],
            lang=lang,
        )
        st.session_state["l1_report"] = l1
    else:
        st.session_state["l1_report"] = None

    # Clear previous L2
    st.session_state.pop("l2_report", None)

    st.rerun()


# ============================================================
# MAIN — Risultati (post-generazione)
# ============================================================

if st.session_state.get("generation_done"):
    generated_code = st.session_state.get("generated_code", "")
    l1_report: L1Report = st.session_state.get("l1_report")

    st.markdown("---")
    st.markdown("## Risultati")

    # ---- a) Codice + Flowchart side-by-side ----


    st.markdown("### Codice generato")
    st.code(generated_code or "// Nessun output", language="javascript")

    st.markdown("### Condizioni")

    # Build display labels (needed for both charts)
    display_labels = None
    if l1_report and l1_report.syntax_ok:
        display_labels = build_display_labels(
            triggers=CAT.get("triggers", []),
            actions=CAT.get("actions", []),
            trigger_slugs=SC["trigger_apis"],
            action_slugs=SC["action_apis"],
            lang=lang,
            services=CAT.get("services", []),
        )

    col_chart, col_blocks = st.columns([1, 1])

    # Left column: Mermaid flowchart
    with col_chart:
        if generated_code:
            # Collect invalid setters from L1 report for red highlighting
            inv_set = None
            if l1_report and l1_report.api_report and l1_report.api_report.invalid_setters:
                inv_set = set(l1_report.api_report.invalid_setters)

            flow_html, flow_height = render_code_flowchart_html(
                generated_code, lang=lang,
                user_type=user_type, display_labels=display_labels,
                invalid_setters=inv_set,
            )
            if flow_html:
                components.html(flow_html, height=flow_height, scrolling=False)
            else:
                st.info("Flowchart non disponibile.")
        else:
            st.info("Flowchart non disponibile.")

    # Right column: semantic blocks (stacked vertically via CSS)
    with col_blocks:
        if l1_report and l1_report.syntax_ok and l1_report.outcomes_raw:
            l2_for_chart = st.session_state.get("l2_report")
            chart_html = render_flowchart_html(
                l1_report.outcomes_raw,
                l2_report=l2_for_chart,
                lang=lang,
                user_type=user_type,
                display_labels=display_labels,
            )
            st.html(chart_html)
        else:
            st.info("Non disponibile.")

    # ---- b) L1 Feedback ----
    st.markdown("### Analisi automatica")

    if l1_report is None:
        st.warning("Generazione vuota — analisi non disponibile.")
    elif not l1_report.syntax_ok:
        st.error(f"**Errore di sintassi:** {l1_report.parse_error}")
    else:
        api = l1_report.api_report

        n_valid_g = len(api.valid_getters) if api else 0
        n_invalid_g = len(api.invalid_getters) if api else 0
        n_valid_s = len(api.valid_setters) if api else 0
        n_invalid_s = len(api.invalid_setters) if api else 0

        # Skip validity: check which used skips are actually allowed
        skip_used_set = set(api.skip_used) if api and api.skip_used else set()
        skip_avail_set = set(api.skip_available) if api and api.skip_available else set()
        valid_skips = sorted(skip_used_set & skip_avail_set)
        invalid_skips = sorted(skip_used_set - skip_avail_set)
        n_valid_skip = len(valid_skips)
        n_invalid_skip = len(invalid_skips)
        n_skip_avail = len(skip_avail_set)

        has_errors = n_invalid_g > 0 or n_invalid_s > 0 or n_invalid_skip > 0

        # --- Colored badge helper ---
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
            cells = _pill(n_ok, "valido", "validi", True)
            if n_ko > 0:
                cells += _pill(n_ko, "invalido", "invalidi", False)
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

        # Banner
        if has_errors:
            b_bg, b_color, b_ico = "#ffebee", "#c62828", "&#10007;"
            b_text = "Problemi API rilevati"
        else:
            b_bg, b_color, b_ico = "#e8f5e9", "#2e7d32", "&#10003;"
            b_text = "Sintassi e API valide"

        skip_note = f"su {n_skip_avail} disponibili" if n_skip_avail else ""
        rows_html = (
            _row("Getter", n_valid_g, n_invalid_g)
            + _row("Setter", n_valid_s, n_invalid_s)
            + _row("Skip", n_valid_skip, n_invalid_skip, skip_note)
        )

        card_html = f'''
        <div style="border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;
                    margin:8px 0;">
          <div style="background:{b_bg};color:{b_color};padding:8px 16px;
                      font-weight:700;font-size:0.95em;">
            {b_ico}&ensp;{b_text}
          </div>
          <table style="width:100%;border-collapse:collapse;">
            {rows_html}
          </table>
        </div>
        '''
        st.markdown(card_html, unsafe_allow_html=True)

        # Invalid details (only when errors exist)
        if has_errors:
            with st.expander("Dettagli errori", expanded=True):
                if api and api.invalid_getters:
                    st.markdown(
                        f"**Getter invalidi:** `{', '.join(api.invalid_getters)}`"
                    )
                if api and api.invalid_setters:
                    st.markdown(
                        f"**Setter invalidi:** `{', '.join(api.invalid_setters)}`"
                    )
                if invalid_skips:
                    st.markdown(
                        f"**Skip invalidi:** `{', '.join(invalid_skips)}`"
                    )

    # ============================================================
    # MAIN — L2 + Valutazione
    # ============================================================

    st.markdown("---")
    st.markdown("## Verifica semantica con LLM")

    if l1_report and l1_report.syntax_ok:
        if st.button("Verifica corrispondenza con l'intento"):
            attempt_log = st.session_state.get("attempt_log", [])
            last_intent = attempt_log[-1].get("user_intent", "") if attempt_log else ""

            with st.spinner("Verifica semantica in corso..."):
                l2 = run_l2_validation(
                    user_intent=last_intent,
                    l1_report=l1_report,
                    endpoint=LLM_ENDPOINT,
                    model=model_identifier,
                    lang=lang,
                )
                st.session_state["l2_report"] = l2

        l2_report: L2Report = st.session_state.get("l2_report")
        if l2_report:
            if l2_report.error:
                st.error(f"Errore L2: {l2_report.error}")
            elif l2_report.intent_match:
                st.success("Il codice implementa correttamente l'intento")
                st.write(l2_report.explanation)
            else:
                st.warning("Il codice potrebbe non corrispondere all'intento")
                st.write(l2_report.explanation)
                if l2_report.suggestions:
                    st.markdown("**Suggerimenti:**")
                    for sug in l2_report.suggestions:
                        st.markdown(f"- {sug}")
    else:
        st.info("Verifica semantica non disponibile (richiede sintassi valida).")

    # ============================================================
    # MAIN — Valutazione + Salvataggio
    # ============================================================

    st.markdown("---")
    st.markdown("## Valutazione")

    # ---- Expert editor ----
    state_key = f"{SC['code']}__{st.session_state.get('selected_attempt', 1)}"

    if "editor_last_submit" not in st.session_state:
        st.session_state["editor_last_submit"] = {}
    if "applied_code" not in st.session_state:
        st.session_state["applied_code"] = {}

    edited_code = None
    expert_claim_fixed = "not_required"
    expert_gave_up = None

    if user_type == "expert":
        st.markdown("### Correzione (Expert)")

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
            options={"wrap": True},
        )

        if isinstance(resp, dict) and resp.get("type") == "submit":
            if isinstance(resp.get("text"), str):
                st.session_state["editor_last_submit"][state_key] = resp["text"]
                st.session_state["applied_code"][state_key] = resp["text"]
                st.success("Modifiche applicate.")

        edited_code = st.session_state["editor_last_submit"][state_key]

        # Status
        if state_key in st.session_state["applied_code"]:
            st.info("Codice modificato applicato.")
        else:
            st.warning("Nessuna modifica: verrà valutato il codice generato.")

        # Claim fixed
        applied = st.session_state["applied_code"].get(state_key)
        has_real_fix = (
            isinstance(applied, str)
            and applied.strip() != ""
            and applied.strip() != generated_code.strip()
        )

        st.markdown("### Esito della correzione")

        UI_TO_CANON = {
            "non richiesto": "not_required",
            "si": "yes",
            "no": "no",
        }

        if not has_real_fix:
            _ = st.radio(
                "Ritieni di aver corretto correttamente il codice?",
                ["non richiesto", "si", "no"],
                index=0,
                horizontal=True,
                key=f"expert_claim_fixed_{state_key}_locked",
            )
            expert_claim_fixed = "not_required"
            st.caption(
                "Non risulta una correzione diversa dal codice generato: "
                "esito impostato su \"non richiesto\"."
            )
        else:
            ui_choice = st.radio(
                "Ritieni di aver corretto correttamente il codice?",
                ["si", "no"],
                horizontal=True,
                key=f"expert_claim_fixed_{state_key}",
            )
            expert_claim_fixed = UI_TO_CANON[ui_choice]

        expert_gave_up = st.checkbox("Non riesco a correggere")

    # ---- Final code ----
    final_code_used = st.session_state.get("applied_code", {}).get(
        state_key,
        generated_code,
    )

    # ---- Evaluation ----
    correct = st.radio(
        "Il Filter Code finale è corretto?",
        ["yes", "no"],
        horizontal=True,
    )

    notes = st.text_area("Note valutatore", height=100)

    # ---- Save ----
    if st.button("Salva valutazione"):
        attempt_log = st.session_state.get("attempt_log", [])
        current = attempt_log[-1] if attempt_log else {}

        l1 = st.session_state.get("l1_report")
        l2 = st.session_state.get("l2_report")

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
            # L2 fields
            "l2_intent_match": (l2.intent_match if l2 else None),
            "l2_explanation": (l2.explanation if l2 else None),
            "l2_suggestions": (l2.suggestions if l2 else []),
        })

        with open(RESULTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        if correct == "yes":
            # Next scenario
            st.session_state["scenario_index"] = (
                st.session_state.get("scenario_index", 0) + 1
            )
            for k in ("forced_scenario", "resume_from_eval", "prefill_prompt",
                       "generation_done", "generated_code", "l1_report", "l2_report"):
                st.session_state.pop(k, None)
            st.rerun()
        else:
            # Stay, prefill for retry
            st.session_state["prefill_prompt"] = current.get("user_intent", "")
            st.session_state["generation_done"] = False
            for k in ("generated_code", "l1_report", "l2_report"):
                st.session_state.pop(k, None)
            st.rerun()
