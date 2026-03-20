# pages/3_Admin.py — Admin dashboard for monitoring user study logs

import os, sys, json, time
import streamlit as st
import pandas as pd
import altair as alt

st.set_page_config(page_title="NL2TAP Admin", layout="wide", initial_sidebar_state="collapsed")

# Force light theme + hide sidebar
st.markdown("""
<style>
:root, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
[data-testid="stHeader"], .main, .block-container, stApp {
    color-scheme: light !important;
}
[data-testid="stAppViewContainer"] { background: #ffffff !important; color: #111827 !important; }
[data-testid="stSidebar"] > div { background: #f9fafb !important; }
[data-testid="stHeader"] { background: #ffffff !important; }
[data-testid="stSidebar"] { display: none; }
[data-testid="stSidebarCollapsedControl"] { display: none; }
[data-testid="stSidebarNav"] { display: none; }
.block-container { padding: 1.5rem 3rem !important; max-width: 1400px !important; }
.admin-kpi {
    background: linear-gradient(135deg, #f0f9ff, #e0f2fe);
    border: 1px solid #bae6fd; border-radius: 12px;
    padding: 16px 20px; text-align: center;
}
.admin-kpi .value { font-size: 2rem; font-weight: 700; color: #0369a1; }
.admin-kpi .label { font-size: 0.82rem; color: #64748b; margin-top: 2px; }
.section-header {
    font-size: 1.05rem; font-weight: 700; color: #1e293b;
    border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; margin: 18px 0 12px 0;
}
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
.stDeployButton { display: none !important; }
.block-container { padding-bottom: 80px !important; }
</style>
""", unsafe_allow_html=True)

# --- path setup ---
_src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from pathlib import Path
from datetime import datetime
from utils.session_manager import (
    _get_conn, export_participants_csv, export_sessions_csv, export_interactions_csv,
    export_toast_csv, export_tlx_csv, export_sus_csv,
    validate_session_token,
)

_RESULTS_DIR = Path("results")
_INTERACTION_LOG = _RESULTS_DIR / "interaction_log.jsonl"
_STUDY_RESULTS = _RESULTS_DIR / "user_study_results.jsonl"

# ============================================================
# ADMIN LOGIN GATE
# ============================================================

if not st.session_state.get("admin_authenticated"):
    _token = st.query_params.get("token", "")
    if _token:
        _sess = validate_session_token(_token)
        if _sess and _sess.get("is_admin"):
            st.session_state["admin_authenticated"] = True
            st.session_state["authenticated"] = True
            st.session_state["user_id"] = "admin"
            st.session_state["user_type"] = "admin"
            st.session_state["_session_token"] = _token

# Ensure token stays in URL for reload persistence
_admin_token = st.session_state.get("_session_token", "")
if _admin_token and st.query_params.get("token", "") != _admin_token:
    st.query_params["token"] = _admin_token

if not st.session_state.get("admin_authenticated"):
    st.markdown("<div style='height:15vh'></div>", unsafe_allow_html=True)
    _, center, _ = st.columns([1.5, 1, 1.5])
    with center:
        with st.container(border=True):
            st.markdown("### Admin Dashboard")
            st.markdown(
                "Per accedere, effettua il login dalla **Home** con le credenziali admin.\n\n"
                "To access, log in from **Home** with admin credentials."
            )
            if st.button("Vai alla Home / Go to Home", type="primary", width="stretch"):
                st.switch_page("Home.py")
    st.stop()

# ============================================================
# DISPLAY CODE MAPPING — Expert E→S/M/C based on complexity
# ============================================================
_DISPLAY_CODE = {
    # Non-expert: keep as-is
    "S1": "S1", "S2": "S2", "M1": "M1", "M2": "M2", "C1": "C1", "C2": "C2",
    # Expert: remap E→S/M/C with distinct numbers
    "E2": "S3", "E5": "S4",   # C1 (simple)
    "E1": "M3", "E4": "M4",   # C2 (medium)
    "E3": "C3", "E6": "C4",   # C3 (complex)
}

def _dc(code: str) -> str:
    """Return display code for admin UI."""
    return _DISPLAY_CODE.get(code, code)

# ============================================================
# DATA LOADING (cached, 15s TTL)
# ============================================================

@st.cache_data(ttl=15)
def load_participants():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM participants ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@st.cache_data(ttl=15)
def load_sessions():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM scenario_sessions ORDER BY started_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@st.cache_data(ttl=15)
def load_interactions(limit=500):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM interactions ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@st.cache_data(ttl=15)
def load_toast():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM toast_responses ORDER BY participant_id, block").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@st.cache_data(ttl=15)
def load_tlx():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM tlx_responses ORDER BY participant_id, block").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@st.cache_data(ttl=15)
def load_sus():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM sus_responses ORDER BY participant_id").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@st.cache_data(ttl=15)
def load_jsonl(path: str):
    p = Path(path)
    if not p.exists():
        return []
    records = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records

def _parse_json_safe(s):
    if not s:
        return s
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return s

def _kpi_card(value, label):
    return (
        f'<div class="admin-kpi">'
        f'<div class="value">{value}</div>'
        f'<div class="label">{label}</div>'
        f'</div>'
    )

# ============================================================
# BUILD ANALYSIS DATAFRAMES
# ============================================================

def build_sessions_df(sessions, participants):
    """Build enriched sessions DataFrame with user_type from participants."""
    if not sessions:
        return pd.DataFrame()
    df = pd.DataFrame(sessions)
    # Join with participants to get user_type
    p_map = {p["participant_id"]: p.get("user_type", "") for p in participants}
    df["user_type"] = df["participant_id"].map(p_map)
    # Only completed
    df_c = df[df["completed_at"].notna() & (df["completed_at"] != "")].copy()
    # Ensure numeric columns
    for col in ["attempt_number", "total_turns", "total_elapsed_s", "eval_confidence"]:
        if col in df_c.columns:
            df_c[col] = pd.to_numeric(df_c[col], errors="coerce")
    return df_c

# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">'
    '<span style="font-size:1.3rem;font-weight:700;color:#111827;">NL2TAP Admin Dashboard</span>'
    '</div>',
    unsafe_allow_html=True,
)

# ============================================================
# TABS
# ============================================================

tab_overview, tab_aggregate, tab_detail, tab_log = st.tabs([
    "Overview", "Aggregate Analysis", "Participant Detail", "Interaction Log"
])

# ============================================================
# TAB 1 — OVERVIEW
# ============================================================

with tab_overview:
    participants = load_participants()
    sessions = load_sessions()

    if not participants:
        st.info("No participants registered yet.")
    else:
        # KPI cards
        n_participants = len(participants)
        n_expert = sum(1 for p in participants if p.get("user_type") == "expert")
        n_nonexpert = n_participants - n_expert

        completed_sessions = [s for s in sessions if s.get("completed_at")]
        n_completed = len(completed_sessions)
        total_expected = sum(
            len(_parse_json_safe(p.get("scenario_assignment", "[]")) or [])
            for p in participants
        )

        fully_done = 0
        for p in participants:
            pid = p["participant_id"]
            assignment = _parse_json_safe(p.get("scenario_assignment", "[]"))
            total_sc = len(assignment) if isinstance(assignment, list) else 0
            done = sum(1 for s in sessions if s["participant_id"] == pid and s.get("completed_at"))
            if done == total_sc and total_sc > 0:
                fully_done += 1

        k1, k2, k3, k4, k5 = st.columns(5)
        with k1:
            st.markdown(_kpi_card(n_participants, "Participants"), unsafe_allow_html=True)
        with k2:
            st.markdown(_kpi_card(f"{n_nonexpert} / {n_expert}", "Non-expert / Expert"), unsafe_allow_html=True)
        with k3:
            st.markdown(_kpi_card(f"{n_completed}/{total_expected}", "Scenarios completed"), unsafe_allow_html=True)
        with k4:
            st.markdown(_kpi_card(fully_done, "Fully completed"), unsafe_allow_html=True)
        with k5:
            pct = round(100 * n_completed / total_expected, 1) if total_expected > 0 else 0
            st.markdown(_kpi_card(f"{pct}%", "Completion rate"), unsafe_allow_html=True)

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

        # Participant progress table
        table_rows = []
        for p in participants:
            pid = p["participant_id"]
            assignment = _parse_json_safe(p.get("scenario_assignment", "[]"))
            total_scenarios = len(assignment) if isinstance(assignment, list) else 0
            condition_order = _parse_json_safe(p.get("condition_order", "[]"))
            cb = p.get("counterbalance_group", "")

            p_sessions = [s for s in sessions if s["participant_id"] == pid]
            completed = sum(1 for s in p_sessions if s.get("completed_at"))
            has_active = any(s.get("started_at") and not s.get("completed_at") for s in p_sessions)

            if completed == total_scenarios and total_scenarios > 0:
                status = "completed"
            elif has_active or completed > 0:
                status = "active"
            else:
                status = "registered"

            # Avg time for completed
            times = [s.get("total_elapsed_s") for s in p_sessions
                     if s.get("completed_at") and s.get("total_elapsed_s")]
            avg_time = f"{sum(times)/len(times):.0f}s" if times else "-"

            table_rows.append({
                "ID": pid,
                "Type": p.get("user_type", ""),
                "CB": cb,
                "Registered": p.get("created_at", "")[:16].replace("T", " "),
                "Progress": f"{completed}/{total_scenarios}",
                "Avg time": avg_time,
                "Status": status,
            })

        df = pd.DataFrame(table_rows)
        st.dataframe(df, width="stretch", hide_index=True)

        # Export
        st.markdown("---")
        st.markdown("**Export CSV**")
        ec1, ec2, ec3, ec4, ec5, ec6, _ = st.columns([1, 1, 1, 1, 1, 1, 2])
        with ec1:
            if st.button("Participants"):
                export_participants_csv()
                st.success("Saved")
        with ec2:
            if st.button("Sessions"):
                export_sessions_csv()
                st.success("Saved")
        with ec3:
            if st.button("Interactions"):
                export_interactions_csv()
                st.success("Saved")
        with ec4:
            if st.button("TOAST"):
                export_toast_csv()
                st.success("Saved")
        with ec5:
            if st.button("NASA-TLX"):
                export_tlx_csv()
                st.success("Saved")
        with ec6:
            if st.button("SUS"):
                export_sus_csv()
                st.success("Saved")


# ============================================================
# TAB 2 — AGGREGATE ANALYSIS
# ============================================================

with tab_aggregate:
    participants = load_participants()
    sessions = load_sessions()
    df_s = build_sessions_df(sessions, participants)
    if not df_s.empty and "scenario_code" in df_s.columns:
        df_s["scenario_code"] = df_s["scenario_code"].map(lambda c: _dc(c))
    toast_data = load_toast()
    tlx_data = load_tlx()
    sus_data = load_sus()

    if df_s.empty:
        st.info("No completed scenario sessions yet. Data will appear here once participants complete scenarios.")
    else:
        n_completed = len(df_s)
        st.caption(f"Analysis based on **{n_completed}** completed scenario sessions.")

        # ---- Filters ----
        _fc1, _fc2, _fc3 = st.columns(3)
        with _fc1:
            _f_condition = st.multiselect(
                "Filter condition", ["A", "B"],
                default=["A", "B"], key="agg_f_cond",
            )
        with _fc2:
            _all_types = sorted(df_s["user_type"].dropna().unique().tolist())
            _f_type = st.multiselect(
                "Filter user type", _all_types,
                default=_all_types, key="agg_f_type",
            )
        with _fc3:
            _all_cx = sorted(df_s["complexity_class"].dropna().unique().tolist())
            _f_cx = st.multiselect(
                "Filter complexity", _all_cx,
                default=_all_cx, key="agg_f_cx",
            )

        dff = df_s.copy()
        if _f_condition:
            dff = dff[dff["condition"].isin(_f_condition)]
        if _f_type:
            dff = dff[dff["user_type"].isin(_f_type)]
        if _f_cx:
            dff = dff[dff["complexity_class"].isin(_f_cx)]

        if dff.empty:
            st.warning("No data matches the selected filters.")
        else:

            # ============ PERFORMANCE ============
            st.markdown('<div class="section-header">Performance — Behavioral Match</div>', unsafe_allow_html=True)

            _match_vals = dff["eval_behavioral_match"].dropna()
            if not _match_vals.empty:
                pc1, pc2 = st.columns(2)

                with pc1:
                    # By condition
                    _perf_cond = (
                        dff.groupby(["condition", "eval_behavioral_match"])
                        .size().reset_index(name="count")
                    )
                    if not _perf_cond.empty:
                        chart = alt.Chart(_perf_cond).mark_bar().encode(
                            x=alt.X("condition:N", title="Condition", axis=alt.Axis(labelAngle=0)),
                            y=alt.Y("count:Q", title="Count"),
                            color=alt.Color("eval_behavioral_match:N", title="Match",
                                            scale=alt.Scale(
                                                domain=["matches_completely", "partially", "does_not_match", "unsure"],
                                                range=["#16a34a", "#f59e0b", "#dc2626", "#9ca3af"],
                                            )),
                            xOffset="eval_behavioral_match:N",
                        ).properties(title="Behavioral match by Condition", height=280)
                        st.altair_chart(chart, width="stretch")

                with pc2:
                    # By complexity
                    _perf_cx = (
                        dff.groupby(["complexity_class", "eval_behavioral_match"])
                        .size().reset_index(name="count")
                    )
                    if not _perf_cx.empty:
                        chart = alt.Chart(_perf_cx).mark_bar().encode(
                            x=alt.X("complexity_class:N", title="Complexity",
                                    sort=["C1", "C2", "C3"],
                                    axis=alt.Axis(labelAngle=0)),
                            y=alt.Y("count:Q", title="Count"),
                            color=alt.Color("eval_behavioral_match:N", title="Match",
                                            scale=alt.Scale(
                                                domain=["matches_completely", "partially", "does_not_match", "unsure"],
                                                range=["#16a34a", "#f59e0b", "#dc2626", "#9ca3af"],
                                            )),
                            xOffset="eval_behavioral_match:N",
                        ).properties(title="Behavioral match by Complexity", height=280)
                        st.altair_chart(chart, width="stretch")

                # By condition x user_type
                _perf_cxtype = (
                    dff.groupby(["condition", "user_type", "eval_behavioral_match"])
                    .size().reset_index(name="count")
                )
                if not _perf_cxtype.empty:
                    chart = alt.Chart(_perf_cxtype).mark_bar().encode(
                        x=alt.X("eval_behavioral_match:N", title="Match",
                                axis=alt.Axis(labelAngle=-30)),
                        y=alt.Y("count:Q", title="Count"),
                        color="condition:N",
                        column=alt.Column("user_type:N", title="User type"),
                    ).properties(title="Match by Condition x User Type", height=240, width=250)
                    st.altair_chart(chart)
            else:
                st.caption("No behavioral match evaluations recorded yet.")

            # ============ CONFIDENCE ============
            st.markdown('<div class="section-header">Confidence (self-reported 1-5)</div>', unsafe_allow_html=True)
            _conf_data = dff[dff["eval_confidence"].notna()].copy()
            if not _conf_data.empty:
                cc1, cc2 = st.columns(2)
                with cc1:
                    _conf_means = _conf_data.groupby("condition")["eval_confidence"].mean().reset_index()
                    _conf_means.columns = ["Condition", "Mean confidence"]
                    chart = alt.Chart(_conf_means).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                        x=alt.X("Condition:N", axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("Mean confidence:Q", scale=alt.Scale(domain=[0, 5])),
                        color=alt.Color("Condition:N", scale=alt.Scale(domain=["A","B"], range=["#94a3b8","#3b82f6"])),
                    ).properties(title="Mean confidence by Condition", height=250)
                    st.altair_chart(chart, width="stretch")
                with cc2:
                    _conf_cx = _conf_data.groupby("complexity_class")["eval_confidence"].mean().reset_index()
                    _conf_cx.columns = ["Complexity", "Mean confidence"]
                    chart = alt.Chart(_conf_cx).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                        x=alt.X("Complexity:N", sort=["C1","C2","C3"], axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("Mean confidence:Q", scale=alt.Scale(domain=[0, 5])),
                        color=alt.Color("Complexity:N"),
                    ).properties(title="Mean confidence by Complexity", height=250)
                    st.altair_chart(chart, width="stretch")
            else:
                st.caption("No confidence data yet.")

            # ============ EFFICIENCY ============
            st.markdown('<div class="section-header">Efficiency — Attempts & Time</div>', unsafe_allow_html=True)

            ef1, ef2 = st.columns(2)
            with ef1:
                # Attempts by condition
                _att_data = dff[dff["attempt_number"].notna()]
                if not _att_data.empty:
                    _att_means = _att_data.groupby("condition")["attempt_number"].mean().reset_index()
                    _att_means.columns = ["Condition", "Mean attempts"]
                    chart = alt.Chart(_att_means).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                        x=alt.X("Condition:N", axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("Mean attempts:Q", scale=alt.Scale(domain=[0, 3])),
                        color=alt.Color("Condition:N", scale=alt.Scale(domain=["A","B"], range=["#94a3b8","#3b82f6"])),
                    ).properties(title="Mean attempts by Condition", height=250)
                    st.altair_chart(chart, width="stretch")

            with ef2:
                # Time by condition
                _time_data = dff[dff["total_elapsed_s"].notna() & (dff["total_elapsed_s"] > 0)]
                if not _time_data.empty:
                    _time_means = _time_data.groupby("condition")["total_elapsed_s"].mean().reset_index()
                    _time_means.columns = ["Condition", "Mean time (s)"]
                    chart = alt.Chart(_time_means).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                        x=alt.X("Condition:N", axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("Mean time (s):Q"),
                        color=alt.Color("Condition:N", scale=alt.Scale(domain=["A","B"], range=["#94a3b8","#3b82f6"])),
                    ).properties(title="Mean time-on-task by Condition", height=250)
                    st.altair_chart(chart, width="stretch")

            # Efficiency by complexity
            ef3, ef4 = st.columns(2)
            with ef3:
                _att_cx = dff[dff["attempt_number"].notna()].groupby("complexity_class")["attempt_number"].mean().reset_index()
                _att_cx.columns = ["Complexity", "Mean attempts"]
                if not _att_cx.empty:
                    chart = alt.Chart(_att_cx).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                        x=alt.X("Complexity:N", sort=["C1","C2","C3"], axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("Mean attempts:Q", scale=alt.Scale(domain=[0, 3])),
                        color="Complexity:N",
                    ).properties(title="Mean attempts by Complexity", height=250)
                    st.altair_chart(chart, width="stretch")
            with ef4:
                _time_cx = dff[dff["total_elapsed_s"].notna() & (dff["total_elapsed_s"] > 0)].groupby("complexity_class")["total_elapsed_s"].mean().reset_index()
                _time_cx.columns = ["Complexity", "Mean time (s)"]
                if not _time_cx.empty:
                    chart = alt.Chart(_time_cx).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                        x=alt.X("Complexity:N", sort=["C1","C2","C3"], axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("Mean time (s):Q"),
                        color="Complexity:N",
                    ).properties(title="Mean time-on-task by Complexity", height=250)
                    st.altair_chart(chart, width="stretch")

            # ============ CALIBRATION ============
            st.markdown('<div class="section-header">Calibration — User eval vs Sandbox</div>', unsafe_allow_html=True)
            _disc_data = dff[dff["discrepancy_user_vs_sandbox"].notna() & (dff["discrepancy_user_vs_sandbox"] != "")]
            if not _disc_data.empty:
                dc1, dc2 = st.columns(2)
                with dc1:
                    _disc_counts = _disc_data.groupby(["condition", "discrepancy_user_vs_sandbox"]).size().reset_index(name="count")
                    _disc_order = ["agree_correct", "agree_incorrect", "false_positive", "false_negative"]
                    _disc_colors = ["#16a34a", "#dc2626", "#f59e0b", "#7c3aed"]
                    chart = alt.Chart(_disc_counts).mark_bar().encode(
                        x=alt.X("condition:N", title="Condition", axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("count:Q", title="Count"),
                        color=alt.Color("discrepancy_user_vs_sandbox:N", title="Discrepancy",
                                        scale=alt.Scale(domain=_disc_order, range=_disc_colors)),
                        xOffset="discrepancy_user_vs_sandbox:N",
                    ).properties(title="Discrepancy by Condition", height=280)
                    st.altair_chart(chart, width="stretch")

                with dc2:
                    # Summary table
                    _disc_pivot = _disc_data.groupby("discrepancy_user_vs_sandbox").size().reset_index(name="Count")
                    _disc_pivot.columns = ["Discrepancy", "Count"]
                    total = _disc_pivot["Count"].sum()
                    _disc_pivot["Pct"] = (_disc_pivot["Count"] / total * 100).round(1).astype(str) + "%"
                    st.dataframe(_disc_pivot, width="stretch", hide_index=True)
            else:
                st.caption("No calibration data yet (requires sandbox results).")

            # ============ TOAST ============
            st.markdown('<div class="section-header">Trust — TOAST (Likert 1-7)</div>', unsafe_allow_html=True)
            if toast_data:
                df_toast = pd.DataFrame(toast_data)
                # Join with participant data for user_type
                p_map = {p["participant_id"]: p.get("user_type", "") for p in participants}
                df_toast["user_type"] = df_toast["participant_id"].map(p_map)

                tc1, tc2 = st.columns(2)
                with tc1:
                    # Mean subscales by condition
                    _toast_cond = df_toast.groupby("condition").agg(
                        Understanding=("understanding_mean", "mean"),
                        Performance=("performance_mean", "mean"),
                        Overall=("overall_mean", "mean"),
                    ).reset_index()
                    _toast_melted = _toast_cond.melt(id_vars="condition", var_name="Subscale", value_name="Mean")
                    chart = alt.Chart(_toast_melted).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                        x=alt.X("Subscale:N", axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("Mean:Q", scale=alt.Scale(domain=[0, 7]), title="Mean score (1-7)"),
                        color=alt.Color("condition:N", title="Condition",
                                        scale=alt.Scale(domain=["A","B"], range=["#94a3b8","#3b82f6"])),
                        xOffset="condition:N",
                    ).properties(title="TOAST subscales by Condition", height=280)
                    st.altair_chart(chart, width="stretch")

                with tc2:
                    # By user_type
                    _toast_type = df_toast.groupby("user_type").agg(
                        Understanding=("understanding_mean", "mean"),
                        Performance=("performance_mean", "mean"),
                        Overall=("overall_mean", "mean"),
                    ).reset_index()
                    _toast_type_m = _toast_type.melt(id_vars="user_type", var_name="Subscale", value_name="Mean")
                    chart = alt.Chart(_toast_type_m).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                        x=alt.X("Subscale:N", axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("Mean:Q", scale=alt.Scale(domain=[0, 7]), title="Mean score (1-7)"),
                        color=alt.Color("user_type:N", title="User type"),
                        xOffset="user_type:N",
                    ).properties(title="TOAST subscales by User type", height=280)
                    st.altair_chart(chart, width="stretch")

                # Item-level table
                with st.expander("TOAST item-level means by Condition"):
                    _toast_items_cond = df_toast.groupby("condition")[[f"item_{i}" for i in range(1, 10)]].mean().T
                    _toast_items_cond.index = [
                        "1. Logical", "2. Understand process", "3. Predict behavior",
                        "4. Understand considerations", "5. Uses relevant info",
                        "6. Good as expert", "7. Can depend", "8. Reliable", "9. Meets needs",
                    ]
                    st.dataframe(_toast_items_cond.round(2), width="stretch")
            else:
                st.caption("No TOAST responses yet.")

            # ============ NASA-TLX ============
            st.markdown('<div class="section-header">Workload — NASA-TLX (0-100)</div>', unsafe_allow_html=True)
            if tlx_data:
                df_tlx = pd.DataFrame(tlx_data)
                p_map = {p["participant_id"]: p.get("user_type", "") for p in participants}
                df_tlx["user_type"] = df_tlx["participant_id"].map(p_map)

                _tlx_subscales = ["mental_demand", "physical_demand", "temporal_demand",
                                  "performance", "effort", "frustration"]
                _tlx_labels = ["Mental", "Physical", "Temporal", "Performance", "Effort", "Frustration"]

                tl1, tl2 = st.columns(2)
                with tl1:
                    _tlx_cond = df_tlx.groupby("condition")[_tlx_subscales].mean().reset_index()
                    _tlx_melted = _tlx_cond.melt(id_vars="condition", var_name="Subscale", value_name="Mean")
                    _tlx_melted["Subscale"] = _tlx_melted["Subscale"].map(dict(zip(_tlx_subscales, _tlx_labels)))
                    chart = alt.Chart(_tlx_melted).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                        x=alt.X("Subscale:N", sort=_tlx_labels, axis=alt.Axis(labelAngle=-30)),
                        y=alt.Y("Mean:Q", scale=alt.Scale(domain=[0, 100]), title="Mean (0-100)"),
                        color=alt.Color("condition:N", title="Condition",
                                        scale=alt.Scale(domain=["A","B"], range=["#94a3b8","#3b82f6"])),
                        xOffset="condition:N",
                    ).properties(title="NASA-TLX by Condition", height=300)
                    st.altair_chart(chart, width="stretch")

                with tl2:
                    # Raw TLX mean by condition
                    _tlx_raw = df_tlx.groupby("condition")["raw_tlx_mean"].mean().reset_index()
                    _tlx_raw.columns = ["Condition", "Raw TLX Mean"]
                    chart = alt.Chart(_tlx_raw).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=50).encode(
                        x=alt.X("Condition:N", axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("Raw TLX Mean:Q", scale=alt.Scale(domain=[0, 100])),
                        color=alt.Color("Condition:N", scale=alt.Scale(domain=["A","B"], range=["#94a3b8","#3b82f6"])),
                    ).properties(title="Raw TLX mean by Condition", height=300)
                    st.altair_chart(chart, width="stretch")
            else:
                st.caption("No NASA-TLX responses yet.")

            # ============ SUS ============
            st.markdown('<div class="section-header">Usability — SUS (0-100)</div>', unsafe_allow_html=True)
            if sus_data:
                df_sus = pd.DataFrame(sus_data)
                p_map = {p["participant_id"]: p.get("user_type", "") for p in participants}
                df_sus["user_type"] = df_sus["participant_id"].map(p_map)

                su1, su2, su3 = st.columns(3)
                mean_sus = df_sus["sus_score"].mean()
                with su1:
                    st.markdown(_kpi_card(f"{mean_sus:.1f}", "Mean SUS score"), unsafe_allow_html=True)
                with su2:
                    # By user type
                    _sus_type = df_sus.groupby("user_type")["sus_score"].mean()
                    for ut, sc in _sus_type.items():
                        st.metric(f"SUS ({ut})", f"{sc:.1f}")
                with su3:
                    # Distribution
                    chart = alt.Chart(df_sus).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                        x=alt.X("sus_score:Q", bin=alt.Bin(step=10), title="SUS Score"),
                        y=alt.Y("count():Q", title="Participants"),
                    ).properties(title="SUS score distribution", height=200)
                    st.altair_chart(chart, width="stretch")
            else:
                st.caption("No SUS responses yet.")

            # ============ RAW DATA TABLE ============
            st.markdown('<div class="section-header">Raw Session Data</div>', unsafe_allow_html=True)
            _show_cols = [
                "participant_id", "scenario_code", "condition", "complexity_class", "user_type",
                "attempt_number", "total_turns", "total_elapsed_s",
                "eval_behavioral_match", "eval_confidence", "eval_code_correct",
                "sandbox_all_pass", "discrepancy_user_vs_sandbox",
            ]
            _avail = [c for c in _show_cols if c in dff.columns]
            _raw_df = dff[_avail].sort_values(["participant_id", "scenario_code"]).copy()
            if "scenario_code" in _raw_df.columns:
                _raw_df["scenario_code"] = _raw_df["scenario_code"].map(lambda c: _dc(c))
            st.dataframe(_raw_df, width="stretch", hide_index=True)


# ============================================================
# TAB 3 — PARTICIPANT DETAIL
# ============================================================

with tab_detail:
    participants = load_participants()
    if not participants:
        st.info("No participants registered yet.")
    else:
        pids = [p["participant_id"] for p in participants]
        sel_pid = st.selectbox("Select participant", pids, key="detail_pid")

        p_data = next((p for p in participants if p["participant_id"] == sel_pid), None)
        if not p_data:
            st.warning("Participant not found.")
            st.stop()

        # --- Participant info card ---
        condition_order = _parse_json_safe(p_data.get("condition_order", "[]"))
        condition_str = ", ".join(condition_order) if isinstance(condition_order, list) else str(condition_order)
        assignment = _parse_json_safe(p_data.get("scenario_assignment", "[]"))
        cb_group = p_data.get("counterbalance_group", "")

        ic1, ic2, ic3, ic4, ic5 = st.columns(5)
        ic1.metric("Type", p_data.get("user_type", ""))
        ic2.metric("Language", p_data.get("lang", ""))
        ic3.metric("CB Group", cb_group)
        ic4.metric("Condition order", condition_str)
        ic5.metric("Registered", p_data.get("created_at", "")[:10])

        st.markdown("---")

        # --- Sessions detail ---
        sessions = load_sessions()
        p_sessions = [s for s in sessions if s["participant_id"] == sel_pid]

        jsonl_records = load_jsonl(str(_INTERACTION_LOG))
        user_jsonl = [r for r in jsonl_records if r.get("user_id") == sel_pid]

        results_records = load_jsonl(str(_STUDY_RESULTS))
        user_results = [r for r in results_records if r.get("user_id") == sel_pid]

        if not assignment or not isinstance(assignment, list):
            st.info("No scenario assignment found.")
            st.stop()

        # Scenario summary table
        st.markdown("**Scenario progress**")
        _sc_rows = []
        for sc_info in assignment:
            sc_code = sc_info.get("scenario_code", "")
            sc_condition = sc_info.get("condition", "")
            sc_complexity = sc_info.get("complexity_class", "")
            sc_block = sc_info.get("block", "")
            sc_session = next((s for s in p_sessions if s["scenario_code"] == sc_code), None)

            if sc_session and sc_session.get("completed_at"):
                status = "Completed"
            elif sc_session and sc_session.get("started_at"):
                status = "In progress"
            else:
                status = "Not started"

            _sc_rows.append({
                "Scenario": _dc(sc_code),
                "Block": sc_block,
                "Condition": sc_condition,
                "Complexity": sc_complexity,
                "Status": status,
                "Attempts": str(sc_session.get("attempt_number", "-")) if sc_session else "-",
                "Time (s)": f"{sc_session['total_elapsed_s']:.0f}" if sc_session and sc_session.get("total_elapsed_s") else "-",
                "Beh. match": str(sc_session.get("eval_behavioral_match", "-")) if sc_session else "-",
                "Confidence": str(sc_session.get("eval_confidence", "-")) if sc_session else "-",
                "Discrepancy": str(sc_session.get("discrepancy_user_vs_sandbox", "-")) if sc_session else "-",
            })
        st.dataframe(pd.DataFrame(_sc_rows), width="stretch", hide_index=True)

        # --- Detailed scenario expanders ---
        for sc_info in assignment:
            sc_code = sc_info.get("scenario_code", "")
            sc_condition = sc_info.get("condition", "")
            sc_complexity = sc_info.get("complexity_class", "")
            sc_session = next((s for s in p_sessions if s["scenario_code"] == sc_code), None)

            if sc_session and sc_session.get("completed_at"):
                status_label = "Completed"
                status_color = "#16a34a"
            elif sc_session and sc_session.get("started_at"):
                status_label = "In progress"
                status_color = "#2563eb"
            else:
                status_label = "Not started"
                status_color = "#9ca3af"

            with st.expander(
                f"{_dc(sc_code)}  —  {status_label}  ·  {sc_complexity}  ·  condition {sc_condition}",
                expanded=False,
            ):
                if sc_session:
                    mc1, mc2, mc3, mc4 = st.columns(4)
                    mc1.metric("Attempts", sc_session.get("attempt_number", "-"))
                    mc2.metric("Turns", sc_session.get("total_turns", "-"))
                    elapsed_s = sc_session.get("total_elapsed_s")
                    mc3.metric("Time", f"{elapsed_s:.0f}s" if elapsed_s else "-")

                    bm = sc_session.get("eval_behavioral_match", "")
                    conf = sc_session.get("eval_confidence", "")
                    eval_str = bm or "-"
                    if conf:
                        eval_str += f" (conf: {conf})"
                    mc4.metric("Evaluation", eval_str)

                    disc = sc_session.get("discrepancy_user_vs_sandbox", "")
                    if disc:
                        st.caption(f"Discrepancy: **{disc}**")

                    mismatch = sc_session.get("eval_mismatch_reason", "")
                    if mismatch:
                        st.caption(f"Mismatch reason: {mismatch}")

                    notes = sc_session.get("eval_notes", "")
                    if notes:
                        st.caption(f"Notes: {notes}")

                    # Intent evolution
                    ie_raw = sc_session.get("intent_evolution", "")
                    if ie_raw:
                        ie = _parse_json_safe(ie_raw)
                        if isinstance(ie, list) and ie:
                            st.markdown("**Intent evolution**")
                            for step in ie:
                                att = step.get("attempt", "?")
                                intent = step.get("intent", "")
                                st.markdown(f"  {att}. {intent[:300]}")

                # Attempts with code
                sc_tool_calls = [
                    r for r in user_jsonl
                    if r.get("scenario_code") == sc_code and r.get("event") == "tool_call"
                ]
                sc_results = [r for r in user_results if r.get("scenario_code") == sc_code]
                attempt_log = []
                for res in sc_results:
                    al = res.get("attempt_log", [])
                    if isinstance(al, list):
                        attempt_log.extend(al)

                attempts = []
                prev_fingerprint = None
                for tc in sc_tool_calls:
                    intent = tc.get("intent_used", "")
                    selected_getters = tc.get("selected_getters", tc.get("getter_coverage", ""))
                    selected_setters = tc.get("selected_setters", tc.get("setter_coverage", ""))
                    fingerprint = f"{intent}|{selected_getters}|{selected_setters}"
                    if fingerprint != prev_fingerprint:
                        attempts.append(tc)
                        prev_fingerprint = fingerprint

                if not attempts and attempt_log:
                    attempts = list(attempt_log)

                if attempts:
                    st.markdown(f"**Attempts ({len(attempts)})**")
                    for idx, att in enumerate(attempts, 1):
                        intent = att.get("intent_used", att.get("intent", ""))
                        code = att.get("code", att.get("generated_code", ""))
                        l1_syn = att.get("l1_syntax_ok")
                        l1_api = att.get("l1_api_valid")

                        syn_badge = ""
                        if l1_syn is not None:
                            syn_ok = l1_syn if isinstance(l1_syn, bool) else bool(l1_syn)
                            syn_badge = "syntax OK" if syn_ok else "syntax ERR"
                        api_badge = ""
                        if l1_api is not None:
                            api_ok = l1_api if isinstance(l1_api, bool) else bool(l1_api)
                            api_badge = "API valid" if api_ok else "API invalid"

                        st.markdown(
                            f"**#{idx}** &nbsp; "
                            + (f"`{syn_badge}` " if syn_badge else "")
                            + (f"`{api_badge}`" if api_badge else "")
                        )
                        if intent:
                            st.caption(f"Intent: {intent[:200]}{'...' if len(intent) > 200 else ''}")
                        if code:
                            st.code(code, language="javascript")

                elif status_label == "Not started":
                    st.caption("No attempts yet.")

        # --- Questionnaires ---
        st.markdown("---")
        st.markdown("**Questionnaire responses**")

        toast_data_user = [t for t in load_toast() if t["participant_id"] == sel_pid]
        tlx_data_user = [t for t in load_tlx() if t["participant_id"] == sel_pid]
        sus_data_user = [s for s in load_sus() if s["participant_id"] == sel_pid]

        if toast_data_user:
            st.markdown("**TOAST**")
            for tr in toast_data_user:
                st.markdown(f"Block {tr['block']} (condition {tr['condition']})")
                _items = [tr.get(f"item_{i}", "-") for i in range(1, 10)]
                _toast_labels = [
                    "Logical", "Understand process", "Predict behavior", "Understand considerations",
                    "Uses relevant info", "Good as expert", "Can depend", "Reliable", "Meets needs",
                ]
                _toast_df = pd.DataFrame({
                    "Item": _toast_labels,
                    "Score": _items,
                })
                st.dataframe(_toast_df, width="stretch", hide_index=True)
                st.caption(
                    f"Understanding: {tr.get('understanding_mean', '-'):.2f} | "
                    f"Performance: {tr.get('performance_mean', '-'):.2f} | "
                    f"Overall: {tr.get('overall_mean', '-'):.2f}"
                )
        else:
            st.caption("No TOAST responses.")

        if tlx_data_user:
            st.markdown("**NASA-TLX**")
            for tr in tlx_data_user:
                st.markdown(f"Block {tr['block']} (condition {tr['condition']})")
                _tlx_items = {
                    "Mental demand": tr.get("mental_demand", "-"),
                    "Physical demand": tr.get("physical_demand", "-"),
                    "Temporal demand": tr.get("temporal_demand", "-"),
                    "Performance": tr.get("performance", "-"),
                    "Effort": tr.get("effort", "-"),
                    "Frustration": tr.get("frustration", "-"),
                }
                st.dataframe(
                    pd.DataFrame({"Subscale": list(_tlx_items.keys()), "Score": list(_tlx_items.values())}),
                    width="stretch", hide_index=True,
                )
                st.caption(f"Raw TLX mean: {tr.get('raw_tlx_mean', '-'):.1f}")
        else:
            st.caption("No NASA-TLX responses.")

        if sus_data_user:
            st.markdown("**SUS**")
            sr = sus_data_user[0]
            st.metric("SUS Score", f"{sr.get('sus_score', 0):.1f}")
        else:
            st.caption("No SUS response.")


# ============================================================
# TAB 4 — INTERACTION LOG (LIVE)
# ============================================================

with tab_log:
    f1, f2, f3, f4 = st.columns([1, 1, 1, 2])
    with f4:
        auto_refresh = st.checkbox("Auto-refresh (15s)", value=False, key="admin_auto_refresh")

    interactions = load_interactions(limit=500)

    if not interactions:
        jsonl_records = load_jsonl(str(_INTERACTION_LOG))
        if jsonl_records:
            interactions = jsonl_records[-500:]
            interactions.reverse()

    if not interactions:
        st.info("No interactions recorded yet.")
    else:
        all_users = sorted(set(r.get("participant_id", r.get("user_id", "")) for r in interactions))
        all_scenarios = sorted(set(_dc(r.get("scenario_code", "")) for r in interactions))
        all_events = sorted(set(r.get("event", "") for r in interactions))

        with f1:
            sel_user = st.selectbox("User", ["All"] + all_users, key="log_user_filter")
        with f2:
            sel_scenario = st.selectbox("Scenario", ["All"] + all_scenarios, key="log_scenario_filter")
        with f3:
            sel_event = st.selectbox("Event", ["All"] + all_events, key="log_event_filter")

        filtered = interactions
        if sel_user != "All":
            filtered = [r for r in filtered if r.get("participant_id", r.get("user_id", "")) == sel_user]
        if sel_scenario != "All":
            filtered = [r for r in filtered if _dc(r.get("scenario_code", "")) == sel_scenario]
        if sel_event != "All":
            filtered = [r for r in filtered if r.get("event", "") == sel_event]

        st.caption(f"Showing {len(filtered)} of {len(interactions)} interactions")

        for i, rec in enumerate(filtered[:200]):
            ts = rec.get("timestamp", "")[:19].replace("T", " ")
            uid = rec.get("participant_id", rec.get("user_id", ""))
            sc = _dc(rec.get("scenario_code", ""))
            turn = rec.get("turn", "")
            event = rec.get("event", "")
            elapsed = rec.get("elapsed_s", "")

            ev_colors = {
                "user_message": "#2563eb",
                "tool_call": "#d97706",
                "agent_response": "#16a34a",
                "suggestion_accepted": "#7c3aed",
                "field_suggestion_accepted": "#7c3aed",
                "evaluation": "#dc2626",
                "scenario_start": "#0891b2",
                "scenario_complete": "#16a34a",
            }
            ev_color = ev_colors.get(event, "#6b7280")

            header = (
                f"`{ts}` &nbsp; **{uid}** &nbsp; `{sc}` &nbsp; "
                f"T{turn} &nbsp; "
                f'<span style="color:{ev_color};font-weight:600;">{event}</span>'
                f" &nbsp; ({elapsed}s)"
            )

            data = {k: v for k, v in rec.items()
                    if k not in ("timestamp", "participant_id", "user_id", "scenario_code",
                                 "turn", "event", "elapsed_s", "condition", "user_type", "id")}

            with st.expander(header, expanded=False):
                st.json(data)

    if auto_refresh:
        time.sleep(15)
        st.rerun()
