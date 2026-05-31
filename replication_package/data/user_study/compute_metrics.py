from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent


def cronbach_alpha(items: pd.DataFrame) -> float:
    items = items.dropna()
    k = items.shape[1]
    return (k / (k - 1)) * (
        1 - items.var(axis=0, ddof=1).sum() / items.sum(axis=1).var(ddof=1)
    )


def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    n1, n2 = len(a), len(b)
    s1, s2 = a.std(ddof=1), b.std(ddof=1)
    sp = math.sqrt(((n1 - 1) * s1**2 + (n2 - 1) * s2**2) / (n1 + n2 - 2))
    return (a.mean() - b.mean()) / sp if sp else float("nan")


def ci95(x: np.ndarray) -> tuple[float, float]:
    x = np.asarray(x, dtype=float)
    n = len(x)
    se = x.std(ddof=1) / math.sqrt(n)
    h = stats.t.ppf(0.975, n - 1) * se
    m = x.mean()
    return m - h, m + h


def cohens_kappa(a: pd.Series, b: pd.Series) -> dict:
    mask = a.notna() & b.notna()
    a, b = a[mask], b[mask]
    labels = sorted(set(a) | set(b))
    n = len(a)
    table = pd.crosstab(a, b).reindex(index=labels, columns=labels, fill_value=0)
    po = np.trace(table.values) / n
    row_marg = table.sum(axis=1).values / n
    col_marg = table.sum(axis=0).values / n
    pe = float((row_marg * col_marg).sum())
    return {"n": int(n), "po": float(po), "pe": pe,
            "kappa": (po - pe) / (1 - pe)}


def main() -> None:
    parts = pd.read_csv(HERE / "participants.csv")
    sus = pd.read_csv(HERE / "sus_responses.csv")
    tlx = pd.read_csv(HERE / "tlx_responses.csv")
    toast = pd.read_csv(HERE / "toast_responses.csv")
    sessions = pd.read_csv(HERE / "scenario_sessions.csv")

    user_type = parts.set_index("participant_id")["user_type"]

    odd = [1, 3, 5, 7, 9]; even = [2, 4, 6, 8, 10]
    t = pd.DataFrame(index=sus.index)
    for i in odd:  t[f"t_{i}"] = sus[f"item_{i}"] - 1
    for i in even: t[f"t_{i}"] = 5 - sus[f"item_{i}"]
    sus = sus.assign(sus_score=t.sum(axis=1) * 2.5)

    sus_items_adj = sus[[f"item_{i}" for i in range(1, 11)]].copy()
    for i in even:
        sus_items_adj[f"item_{i}"] = 6 - sus_items_adj[f"item_{i}"]

    all_sub = ["mental_demand", "physical_demand", "temporal_demand",
               "performance", "effort", "frustration"]
    substantive = [s for s in all_sub if s != "physical_demand"]
    tlx = tlx.assign(raw_tlx=tlx[all_sub].mean(axis=1))

    all_items = [f"item_{i}" for i in range(1, 10)]
    und_items = [f"item_{i}" for i in (1, 3, 4, 8)]
    perf_items = [f"item_{i}" for i in (2, 5, 6, 7, 9)]
    toast = toast.assign(
        toast_und=toast[und_items].mean(axis=1),
        toast_perf=toast[perf_items].mean(axis=1),
        toast_overall=toast[all_items].mean(axis=1),
    )

    sus_pp   = sus.groupby("participant_id")["sus_score"].mean()
    tlx_pp   = tlx.groupby("participant_id")[["raw_tlx"] + substantive].mean()
    toast_pp = toast.groupby("participant_id")[
        ["toast_und", "toast_perf", "toast_overall"]
    ].mean()

    a_sus   = cronbach_alpha(sus_items_adj)
    a_tlx   = cronbach_alpha(tlx[substantive])
    a_toast = cronbach_alpha(toast[all_items])
    a_und   = cronbach_alpha(toast[[f"item_{i}" for i in (1, 2, 3, 4)]])
    a_perf  = cronbach_alpha(toast[perf_items])

    def by_type(series):
        df = series.to_frame("v").join(user_type, how="inner")
        return (df[df["user_type"] == "expert"]["v"].dropna().values,
                df[df["user_type"] == "non_expert"]["v"].dropna().values)

    def row_for(label, series, decimals=1):
        e, ne = by_type(series)
        u, p = stats.mannwhitneyu(e, ne, alternative="two-sided")
        d = cohens_d(e, ne)
        return (label, len(e), e.mean(), e.std(ddof=1), *ci95(e),
                len(ne), ne.mean(), ne.std(ddof=1), *ci95(ne),
                d, float(u), float(p), decimals)

    rows = []
    rows.append(row_for("SUS Score (0-100)",    sus_pp))
    rows.append(row_for("Raw TLX Overall",      tlx_pp["raw_tlx"]))
    for s in substantive:
        rows.append(row_for(f"  {s}",            tlx_pp[s]))
    rows.append(row_for("TOAST Understanding",  toast_pp["toast_und"], 2))
    rows.append(row_for("TOAST Performance",    toast_pp["toast_perf"], 2))
    rows.append(row_for("TOAST Overall",        toast_pp["toast_overall"], 2))

    print("=" * 60)
    print("INTERNAL CONSISTENCY (Cronbach's alpha)")
    print("=" * 60)
    print(f"  SUS                       alpha = {a_sus:.4f}  (N={len(sus_items_adj)})")
    print(f"  NASA-TLX (5 subscales)    alpha = {a_tlx:.4f}  (N={len(tlx)})")
    print(f"  TOAST overall (9 items)   alpha = {a_toast:.4f}  (N={len(toast)})")
    print(f"    Understanding (1-4)     alpha = {a_und:.4f}")
    print(f"    Performance (2,5,6,7,9) alpha = {a_perf:.4f}")

    print()
    print("=" * 60)
    print("QUESTIONNAIRE RESULTS (Table 4)")
    print("=" * 60)
    for (lbl, nE, mE, sdE, lE, hE,
         nNE, mNE, sdNE, lNE, hNE, d, u, p, dec) in rows:
        fmt = f"{{:.{dec}f}}"
        print(f"  {lbl:24s}  "
              f"E: M={fmt.format(mE)} SD={fmt.format(sdE)} "
              f"[{fmt.format(lE)},{fmt.format(hE)}]  "
              f"NE: M={fmt.format(mNE)} SD={fmt.format(sdNE)} "
              f"[{fmt.format(lNE)},{fmt.format(hNE)}]  "
              f"d={d:+.2f}  U={u:.0f}  p={p:.3f}")

    print()
    print("=" * 60)
    print("BEHAVIOURAL OUTCOMES (Table 5)")
    print("=" * 60)
    sess = sessions.merge(parts[["participant_id", "user_type"]], on="participant_id")
    sess["is_correct"] = (sess["success"] == "correct").astype(int)
    for ut, label in [("non_expert", "Non-expert"), ("expert", "Expert")]:
        df = sess[sess["user_type"] == ut]
        for cls in sorted(df["complexity_class"].dropna().unique()):
            sub = df[df["complexity_class"] == cls]
            print(f"  {label:12s} {cls:4s}  n={len(sub):>3d}  "
                  f"success={sub['is_correct'].mean()*100:.1f}%  "
                  f"attempts={sub['attempt_number'].mean():.2f}  "
                  f"time={sub['total_elapsed_s'].mean():.0f}s")
        print(f"  {label:12s} All   n={len(df):>3d}  "
              f"success={df['is_correct'].mean()*100:.1f}%  "
              f"attempts={df['attempt_number'].mean():.2f}  "
              f"time={df['total_elapsed_s'].mean():.0f}s")

    print()
    print("=" * 60)
    print("CROSS-INSTRUMENT CORRELATIONS (Spearman rho, per-participant)")
    print("=" * 60)
    time_pp = sess.groupby("participant_id")["total_elapsed_s"].mean().rename("time")
    correl_df = pd.concat([sus_pp.rename("sus"),
                           tlx_pp["raw_tlx"].rename("tlx"),
                           toast_pp["toast_overall"].rename("toast"),
                           time_pp], axis=1).dropna()
    for a, b in [("sus", "tlx"), ("sus", "toast"), ("tlx", "toast"), ("time", "sus")]:
        r, p = stats.spearmanr(correl_df[a], correl_df[b])
        print(f"  {a.upper():5s} vs {b.upper():5s}  rho = {r:+.3f}  p = {p:.3f}")

    print()
    print("=" * 60)
    print("INTER-RATER RELIABILITY (Cohen's kappa)")
    print("=" * 60)
    ir = cohens_kappa(sessions["evaluator_1"], sessions["evaluator_2"])
    print(f"  N = {ir['n']}, p_o = {ir['po']:.3f}, p_e = {ir['pe']:.3f}, "
          f"kappa = {ir['kappa']:.3f}")

    print()
    print(f"Sample: N = {len(parts)} valid participants, "
          f"sessions = {len(sessions)}")


if __name__ == "__main__":
    main()
