"""
Test-set representativeness analysis (Section 5.2.3, R2 round).

Compares the held-out test set (N=351, rules whose GPT-4-judged descriptions
were already self-descriptive) against the RESIDUAL train+validation pool
(N=2,386 = 2,737 - 351). The residual pool excludes the test rules so that the
selected subset is not compared against a reference distribution that contains
it, which would attenuate the very selection effect under study.

Regenerates:
  data/representativeness_test_vs_pool.csv   (per-feature KS comparison)
  data/representativeness_channel_mix.csv    (per-category channel distribution)

Usage:
    python scripts/representativeness.py
"""

import ast
import csv
import json
import os
import re
import statistics as st

from scipy.stats import ks_2samp

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")


def _load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        d = json.load(f)
    return d if isinstance(d, list) else d.get("data") or list(d.values())[0]


def _categories(value):
    """triggers_category is a plain string; actions_category is a stringified
    Python list (e.g. "['Appliances', 'Lighting']"). Normalise both to a list."""
    if isinstance(value, list):
        return [str(c) for c in value]
    s = str(value).strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            return [str(c) for c in ast.literal_eval(s)]
        except (ValueError, SyntaxError):
            pass
    return [s] if s else []


def _features(rec):
    fc = rec.get("filter_code") or ""
    # nl_words: length of the ORIGINAL user description -- the variable on which
    # selection operates (GPT-4 judges this text and decides whether to refine).
    # Compared like-for-like across partitions to isolate the selection effect.
    return {
        "nl_words": len((rec.get("description") or "").split()),
        "chars": len(fc),
        "lines": fc.count("\n") + 1,
        "n_ifs": len(re.findall(r"if\s*\(", fc)),
        "n_logops": fc.count("&&") + fc.count("||"),
        "n_action_apis": len(rec.get("action_apis") or []),
    }


FEATURES = ["nl_words", "chars", "lines", "n_ifs", "n_logops", "n_action_apis"]


def main():
    train = _load("dataset_train.json")
    val = _load("dataset_val.json")
    test = _load("dataset_test.json")
    pool = train + val  # residual: 2,737 - 351 test = 2,386

    # ---- per-feature KS comparison -------------------------------------
    pool_f = {k: [_features(r)[k] for r in pool] for k in FEATURES}
    test_f = {k: [_features(r)[k] for r in test] for k in FEATURES}

    rows = []
    for k in FEATURES:
        ks = ks_2samp(test_f[k], pool_f[k])
        rows.append({
            "feature": k,
            "pool_M": round(st.mean(pool_f[k]), 2),
            "pool_SD": round(st.stdev(pool_f[k]), 2),
            "pool_median": st.median(pool_f[k]),
            "test_M": round(st.mean(test_f[k]), 2),
            "test_SD": round(st.stdev(test_f[k]), 2),
            "test_median": st.median(test_f[k]),
            "KS_stat": round(ks.statistic, 3),
            "KS_pvalue": ks.pvalue,
        })
    with open(os.path.join(DATA_DIR, "representativeness_test_vs_pool.csv"), "w",
              newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---- per-category channel distribution -----------------------------
    def tally(rows_, field):
        counts = {}
        for r in rows_:
            for cat in set(_categories(r.get(field))):
                counts[cat] = counts.get(cat, 0) + 1
        return counts

    chan_rows = []
    for kind, field in (("trigger", "triggers_category"),
                        ("action", "actions_category")):
        pool_c = tally(pool, field)
        test_c = tally(test, field)
        n_pool, n_test = len(pool), len(test)
        for cat in sorted(set(pool_c) | set(test_c)):
            chan_rows.append({
                "kind": kind,
                "category": cat,
                "pool_count": pool_c.get(cat, 0),
                "pool_pct": round(100 * pool_c.get(cat, 0) / n_pool, 2),
                "test_count": test_c.get(cat, 0),
                "test_pct": round(100 * test_c.get(cat, 0) / n_test, 2),
            })
    with open(os.path.join(DATA_DIR, "representativeness_channel_mix.csv"), "w",
              newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(chan_rows[0].keys()))
        w.writeheader()
        w.writerows(chan_rows)

    # ---- console summary (for the paper table) -------------------------
    print(f"Residual pool N={len(pool)}  |  Test N={len(test)}\n")
    print(f"{'feature':14s} {'pool M±SD':>16s} {'test M±SD':>16s} {'KS D':>7s} {'p':>10s}")
    for r in rows:
        print(f"{r['feature']:14s} "
              f"{r['pool_M']:7.2f}±{r['pool_SD']:<7.2f} "
              f"{r['test_M']:7.2f}±{r['test_SD']:<7.2f} "
              f"{r['KS_stat']:7.3f} {r['KS_pvalue']:10.1e}")
    for kind in ("trigger", "action"):
        ks = [r for r in chan_rows if r["kind"] == kind]
        pool_u = sum(1 for r in ks if r["pool_count"] > 0)
        test_u = sum(1 for r in ks if r["test_count"] > 0)
        oob = sum(1 for r in ks if r["test_count"] > 0 and r["pool_count"] == 0)
        print(f"{kind:8s} categories: pool_unique={pool_u}  test_unique={test_u}  "
              f"out-of-pool={oob}")


if __name__ == "__main__":
    main()
