# -*- coding: utf-8 -*-
# Single-script reproduction of the 5 figures:
#   figures/sus_distribution.png
#   figures/tlx_distribution.png
#   figures/tlx_subscales.png
#   figures/sus_vs_tlx.png
#   figures/sus_item_contributions.png
#
# Works standalone (uses RAW_CSV below). If you already have a CSV file,
# set CSV_PATH to its path and set USE_FILE=True.

import os
import re
from io import StringIO
import math

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Optional: for Pearson r p-value + t critical value for CI
try:
    from scipy import stats
except Exception:
    stats = None


USE_FILE = False
CSV_PATH = "user_study.csv"  # used only if USE_FILE=True

RAW_CSV = r"""
"Informazioni cronologiche","User ID (anonimo)","Età","Genere","Livello di istruzione","Competenze informatiche (1 = basse, 5 = alte)","Conoscenza della piattaforma IFTTT (1 = nulla, 5 = avanzata)","1. Penso che vorrei usare questo sistema frequentemente.","2. Ho trovato il sistema inutilmente complesso.","3. Ho ritenuto il sistema facile da usare.","4. Credo che avrei bisogno del supporto di un tecnico per poter utilizzare questo sistema.","5. Ho trovato che le varie funzioni del sistema sono ben integrate.","6. Penso che ci sia stata troppa incoerenza nel sistema.","7. Immagino che la maggior parte delle persone imparerebbe a usare questo sistema molto rapidamente.","8. Ho trovato il sistema molto macchinoso da usare.","9. Mi sono sentito molto sicuro nell’utilizzare il sistema.","10. Ho dovuto imparare molte cose prima di riuscire a utilizzare il sistema.","Domanda Mentale","Domanda Fisica","Domanda Temporale","Prestazione","Sforzo","Frustrazione"
"2025/12/11 2:21:36 PM CET","1","20","Uomo","Laurea triennale","2","1","4","1","4","1","3","1","3","1","5","1","1","0","2","10","1","0"
"2025/12/11 3:56:52 PM CET","2","20","Uomo","Laurea triennale","3","2","4","3","4","2","4","3","4","3","4","2","7","2","0","10","4","0"
"2025/12/11 5:22:17 PM CET","3","20","Uomo","Scuola superiore","4","1","3","3","2","2","4","1","2","3","2","2","10","0","7","8","5","2"
"2025/12/11 6:50:33 PM CET","4","19","Uomo","Scuola superiore","3","1","3","3","3","4","4","2","3","2","1","1","7","6","8","10","7","5"
"2025/12/11 8:03:46 PM CET","5","20","Uomo","Scuola superiore","4","1","2","2","4","2","4","2","4","3","5","3","7","1","0","7","6","2"
"2025/12/12 9:13:56 AM CET","6","18","Uomo","Scuola superiore","2","3","3","1","5","1","5","1","5","1","5","1","1","0","0","8","1","0"
"2025/12/12 10:01:14 AM CET","7","18","Uomo","Scuola superiore","2","1","5","2","4","1","5","1","4","1","5","1","2","0","0","4","0","0"
"2025/12/12 12:55:12 PM CET","8","18","Uomo","Scuola superiore","2","1","4","3","5","1","5","1","5","1","5","1","2","0","0","8","2","0"
"2025/12/15 12:22:19 PM CET","11","26","Donna","Laurea magistrale","5","3","4","1","5","2","5","1","5","1","5","2","3","0","0","1","2","0"
"2025/12/15 8:25:08 PM CET","12","28","Donna","Laurea magistrale","4","3","3","2","3","4","4","2","4","2","3","3","6","2","1","5","5","3"
"2025/12/16 12:27:09 AM CET","9","23","Uomo","Scuola superiore","2","1","4","3","2","3","3","4","2","3","4","2","7","2","6","7","8","8"
"2025/12/16 12:30:27 AM CET","13","36","Uomo","Laurea triennale","3","2","4","2","4","2","4","3","4","2","3","1","5","0","5","6","4","4"
"2025/12/16 12:10:47 PM CET","14","25","Uomo","Master/Specializzazione","4","2","4","2","4","1","4","1","4","2","4","2","6","0","1","6","6","2"
"2025/12/16 3:27:58 PM CET","16","24","Uomo","Laurea magistrale","5","1","2","2","4","1","3","3","4","2","4","1","8","0","0","9","3","0"
"2025/12/16 5:12:48 PM CET","17","29","Uomo","Master/Specializzazione","5","1","4","2","5","3","4","2","4","2","4","2","8","0","5","8","1","1"
"2025/12/16 8:19:00 PM CET","18","29","Donna","Laurea magistrale","5","2","4","1","5","1","4","1","5","1","4","2","7","0","0","6","7","0"
"2025/12/17 12:05:50 AM CET","15","35","Donna","Dottorato","4","4","3","2","4","3","3","2","3","3","3","3","4","0","0","5","3","1"
"2025/12/17 12:05:50 AM CET","10","35","Donna","Dottorato","4","4","3","2","4","3","3","2","3","3","3","3","4","0","0","5","3","1"
"2025/12/17 12:05:50 AM CET","19","31","Uomo","Dottorato","4","4","3","2","4","3","3","2","3","3","3","3","4","0","0","5","3","1"
"2025/12/17 12:05:50 AM CET","20","29","Uomo","Dottorato","4","4","3","2","4","3","3","2","3","3","3","3","4","0","0","5","3","1"
""".strip()


def read_data() -> pd.DataFrame:
    if USE_FILE:
        return pd.read_csv(CSV_PATH)
    return pd.read_csv(StringIO(RAW_CSV))


def cronbach_alpha(items: pd.DataFrame) -> float:
    items = items.dropna()
    k = items.shape[1]
    if k < 2:
        return float("nan")
    item_vars = items.var(axis=0, ddof=1)
    total_var = items.sum(axis=1).var(ddof=1)
    if total_var <= 0 or np.isnan(total_var):
        return float("nan")
    return (k / (k - 1)) * (1 - item_vars.sum() / total_var)


def mean_sd_ci(x: pd.Series, alpha: float = 0.05):
    x = pd.to_numeric(x, errors="coerce").dropna()
    n = len(x)
    m = float(x.mean())
    sd = float(x.std(ddof=1)) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n > 0 else float("nan")
    if stats is not None and n > 1:
        tcrit = float(stats.t.ppf(1 - alpha / 2, df=n - 1))
    else:
        tcrit = 1.96  # fallback
    ci = (m - tcrit * se, m + tcrit * se)
    return n, m, sd, ci


def pearson_r_p(x: pd.Series, y: pd.Series):
    xy = pd.concat([x, y], axis=1).dropna()
    if len(xy) < 3:
        return float("nan"), float("nan")
    if stats is not None:
        r, p = stats.pearsonr(xy.iloc[:, 0], xy.iloc[:, 1])
        return float(r), float(p)
    r = float(np.corrcoef(xy.iloc[:, 0], xy.iloc[:, 1])[0, 1])
    return r, float("nan")


# --------------------------
# Main
# --------------------------
df = read_data()

# Detect SUS item columns robustly: columns starting with "1." ... "10."
sus_cols = [c for c in df.columns if re.match(r"^\s*\d+\.", str(c))]
sus_cols = sorted(
    sus_cols,
    key=lambda c: int(re.match(r"^\s*(\d+)\.", str(c)).group(1))
)

if len(sus_cols) != 10:
    raise ValueError(f"Expected 10 SUS items, found {len(sus_cols)}: {sus_cols}")

# TLX columns (exact names from your dataset)
tlx_cols = ["Domanda Mentale", "Domanda Fisica", "Domanda Temporale", "Prestazione", "Sforzo", "Frustrazione"]
for c in tlx_cols:
    if c not in df.columns:
        raise ValueError(f"Missing TLX column: {c}")

# Numeric conversion
for c in sus_cols + tlx_cols:
    df[c] = pd.to_numeric(df[c], errors="coerce")

# Keep rows with complete SUS+TLX (so N is well-defined)
df = df.dropna(subset=sus_cols + tlx_cols).copy()
N = len(df)

# SUS computation: odd items => (x-1); even items => (5-x); total * 2.5
adj = pd.DataFrame(index=df.index)
for i, c in enumerate(sus_cols, start=1):
    if i % 2 == 1:
        adj[c] = df[c] - 1
    else:
        adj[c] = 5 - df[c]

df["SUS"] = adj.sum(axis=1) * 2.5

# Raw NASA-TLX (0–10): mean of 6 subscales
df["TLX_Raw"] = df[tlx_cols].mean(axis=1)

# Stats
n_sus, sus_mean, sus_sd, sus_ci = mean_sd_ci(df["SUS"])
n_tlx, tlx_mean, tlx_sd, tlx_ci = mean_sd_ci(df["TLX_Raw"])
r, p = pearson_r_p(df["SUS"], df["TLX_Raw"])
alpha = cronbach_alpha(df[sus_cols])

# Output dirs
out_dir = "figures"
os.makedirs(out_dir, exist_ok=True)

# --------------------------
# Figure 1: SUS distribution
# --------------------------
plt.figure(figsize=(7, 4.2))
plt.hist(df["SUS"], bins=8, edgecolor="black")
plt.axvline(68, linestyle="--", linewidth=1)
plt.axvline(80, linestyle="--", linewidth=1)
plt.axvline(sus_mean, linestyle="-", linewidth=1)
plt.xlabel("SUS (0–100)")
plt.ylabel("Count")
plt.title(f"SUS Distribution (N={N})")
plt.tight_layout()
plt.savefig(os.path.join(out_dir, "sus_distribution.png"), dpi=300)
plt.close()

# --------------------------
# Figure 2: TLX distribution
# --------------------------
plt.figure(figsize=(7, 4.2))
plt.hist(df["TLX_Raw"], bins=8, edgecolor="black")
plt.axvline(tlx_mean, linestyle="-", linewidth=1)
plt.xlabel("Raw NASA-TLX (0–10)")
plt.ylabel("Count")
plt.title(f"Raw NASA-TLX Distribution (N={N})")
plt.tight_layout()
plt.savefig(os.path.join(out_dir, "tlx_distribution.png"), dpi=300)
plt.close()

# --------------------------
# Figure 3: TLX subscales (means)
# --------------------------
sub_means = df[tlx_cols].mean().reindex(tlx_cols)
plt.figure(figsize=(7.5, 4.6))
plt.bar(range(len(tlx_cols)), sub_means.values, edgecolor="black")
plt.xticks(range(len(tlx_cols)), tlx_cols, rotation=35, ha="right")
plt.ylim(0, 10)
plt.ylabel("Mean (0–10)")
plt.title("NASA-TLX Subscale Means")
plt.tight_layout()
plt.savefig(os.path.join(out_dir, "tlx_subscales.png"), dpi=300)
plt.close()

# --------------------------
# Figure 4: SUS vs TLX scatter (+ regression line)
# --------------------------
plt.figure(figsize=(7, 4.6))
plt.scatter(df["TLX_Raw"], df["SUS"])
# regression line
m, b = np.polyfit(df["TLX_Raw"], df["SUS"], 1)
xs = np.linspace(df["TLX_Raw"].min(), df["TLX_Raw"].max(), 200)
plt.plot(xs, m * xs + b, linewidth=1)
plt.xlabel("Raw NASA-TLX (0–10)")
plt.ylabel("SUS (0–100)")
p_text = f"{p:.4f}" if not np.isnan(p) else "NA"
plt.title(f"SUS vs Raw NASA-TLX (r={r:.3f}, p={p_text})")
plt.tight_layout()
plt.savefig(os.path.join(out_dir, "sus_vs_tlx.png"), dpi=300)
plt.close()

# --------------------------
# Figure 5: SUS item contributions (mean adjusted 0–4)
# --------------------------
item_means = adj.mean(axis=0).values  # already adjusted
plt.figure(figsize=(7.5, 4.6))
plt.bar(range(1, 11), item_means, edgecolor="black")
plt.xticks(range(1, 11), [str(i) for i in range(1, 11)])
plt.ylim(0, 4)
plt.xlabel("SUS item (1–10)")
plt.ylabel("Mean adjusted score (0–4)")
plt.title("SUS Item Contributions")
plt.tight_layout()
plt.savefig(os.path.join(out_dir, "sus_item_contributions.png"), dpi=300)
plt.close()

# --------------------------
# Save a small metrics file (handy for LaTeX)
# --------------------------
metrics = pd.DataFrame([{
    "N": N,
    "SUS_mean": sus_mean,
    "SUS_sd": sus_sd,
    "SUS_ci_low": sus_ci[0],
    "SUS_ci_high": sus_ci[1],
    "SUS_cronbach_alpha": alpha,
    "TLX_mean": tlx_mean,
    "TLX_sd": tlx_sd,
    "TLX_ci_low": tlx_ci[0],
    "TLX_ci_high": tlx_ci[1],
    "SUS_TLX_pearson_r": r,
    "SUS_TLX_pearson_p": p,
}])
metrics.to_csv("user_study_metrics_N20.csv", index=False)

print("Done.")
print(f"N={N}")
print(f"SUS: mean={sus_mean:.2f}, sd={sus_sd:.2f}, 95% CI=[{sus_ci[0]:.2f}, {sus_ci[1]:.2f}], alpha={alpha:.3f}")
print(f"TLX: mean={tlx_mean:.2f}, sd={tlx_sd:.2f}, 95% CI=[{tlx_ci[0]:.2f}, {tlx_ci[1]:.2f}]")
print(f"SUS vs TLX: r={r:.3f}, p={p if not np.isnan(p) else 'NA'}")
print(f"Figures saved to: {os.path.abspath(out_dir)}")
print("Metrics saved to: user_study_metrics_N20.csv")
