"""
Automated code-generation metrics (RQ1): aggregates the precomputed per-sample
similarity scores over the 351-rule real test set and prints mean +/- SD per
(model, variant).

Usage:
    python scripts/compute_codegen_metrics.py [path/to/benchmark.jsonl]
"""

import json
import os
import sys
import statistics as st
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(BASE_DIR, "data", "test", "benchmark_real_4b.jsonl")

METRICS = ["codebert_f1", "codebleu", "bleu", "meteor", "rouge1", "rouge2", "rougeL"]

VARIANT_LABEL = {
    "base_zs": "ZS (zero-shot)",
    "base_intent_only": "ZS (intent only)",
    "base_only_intent": "ZS (intent only)",
    "fine_tuned_ni": "FT-NI",
    "fine_tuned_ni_and_catalog": "FT-NI+Cat",
    "peft": "FT-NI",
}
VARIANT_ORDER = ["base_zs", "base_intent_only", "base_only_intent",
                 "fine_tuned_ni", "peft", "fine_tuned_ni_and_catalog"]
MODEL_ORDER = ["qwen", "deepseek", "codellama", "codestral"]


def _model(m):
    m = str(m).lower()
    for x in ["codestral", "codellama", "deepseek", "qwen", "gemma", "llama2"]:
        if x in m:
            return x
    return m


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    data = defaultdict(lambda: defaultdict(list))
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "codebert_f1" not in r:
                continue
            key = (_model(r.get("model")), str(r.get("variant", "?")))
            for m in METRICS:
                try:
                    data[key][m].append(float(r[m]))
                except (KeyError, ValueError, TypeError):
                    pass

    hdr = f"{'Model':11s} {'Variant':17s} {'n':>4s}  " + "  ".join(f"{m:>11s}" for m in METRICS)
    print(hdr)
    print("-" * len(hdr))
    ordered = sorted(
        data.keys(),
        key=lambda k: (MODEL_ORDER.index(k[0]) if k[0] in MODEL_ORDER else 9,
                       VARIANT_ORDER.index(k[1]) if k[1] in VARIANT_ORDER else 9),
    )
    for (mdl, var) in ordered:
        vals = data[(mdl, var)]
        n = len(next(iter(vals.values()))) if vals else 0
        cells = []
        for m in METRICS:
            xs = vals.get(m, [])
            cells.append(f"{st.mean(xs):.3f}±{st.pstdev(xs):.3f}" if xs else "   n/a   ")
        label = VARIANT_LABEL.get(var, var)
        print(f"{mdl:11s} {label:17s} {n:>4d}  " + "  ".join(f"{c:>11s}" for c in cells))


if __name__ == "__main__":
    main()
