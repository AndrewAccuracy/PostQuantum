"""Generate cross-backend comparison figures for the paper.

Outputs:
  docs/figures/fig_backend_acc.pdf   – grouped bar chart of balanced accuracy
  docs/figures/fig_backend_cohend.pdf – Cohen's d scatter comparison
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── Macaron palette ───────────────────────────────────────────────────────────
C = {
    "pqcrypto":  "#F9B8C6",   # strawberry pink
    "liboqs":    "#A8D8B5",   # pistachio mint
    "pq_edge":   "#D97A96",   # darker pink for edge
    "lq_edge":   "#5FAD82",   # darker green for edge
    "ref":       "#C8A0B0",   # muted rose – reference / chance line
    "text":      "#4A4A4A",
    "grid":      "#F0EEF0",
    "ctrl_pq":   "#FAD4E0",   # lighter pink for control
    "ctrl_lq":   "#C8EDD8",   # lighter green for control
}

plt.rcParams.update({
    "font.family":      "serif",
    "font.size":        9,
    "axes.titlesize":   9,
    "axes.labelsize":   9,
    "xtick.labelsize":  7.5,
    "ytick.labelsize":  8,
    "legend.fontsize":  8,
    "figure.dpi":       150,
    "text.color":       C["text"],
    "axes.labelcolor":  C["text"],
    "xtick.color":      C["text"],
    "ytick.color":      C["text"],
    "axes.edgecolor":   "#CCCCCC",
})

VARIANTS   = ["512", "768", "1024"]
STRATEGIES = ["single_bit", "byte_flip", "random_bytes", "zero"]
LABELS_CN  = {
    "single_bit":   "single\_bit",
    "byte_flip":    "byte\_flip",
    "random_bytes": "random\_bytes",
    "zero":         "zero",
}

RESULTS_ROOT = Path("/Users/andrew/PostQuantum/results")
OUT_DIR = Path("/Users/andrew/PostQuantum/.claude/worktrees/dazzling-roentgen-cc919e/docs/figures")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_runs(root: Path, variant: str, strategy: str) -> list[dict]:
    summaries = []
    for run_dir in sorted(root.glob(f"run_*/ml_kem_{variant}/{strategy}")):
        p = run_dir / "summary.json"
        if p.exists():
            summaries.append(json.loads(p.read_text()))
    return summaries


def extract(summaries: list[dict]) -> dict:
    real_acc, ctrl_acc, cohend, welch_p = [], [], [], []
    for s in summaries:
        real = s["scenarios"]["real"]
        ctrl = s["scenarios"]["positive_control"]
        real_acc.append(max(m["balanced_accuracy_mean"] for m in real["models"]))
        ctrl_acc.append(max(m["balanced_accuracy_mean"] for m in ctrl["models"]))
        cohend.append(real["cohens_d"])
        welch_p.append(real["welch_p_value"])
    return {
        "real_acc_mean": float(np.mean(real_acc)),
        "real_acc_sd":   float(np.std(real_acc, ddof=1)) if len(real_acc) > 1 else 0.0,
        "ctrl_acc_mean": float(np.mean(ctrl_acc)),
        "cohend_mean":   float(np.mean(cohend)),
        "welch_p_mean":  float(np.mean(welch_p)),
        "n": len(summaries),
    }


# ── Load data ─────────────────────────────────────────────────────────────────
roots = {
    "pqcrypto": RESULTS_ROOT / "compare5_pqcrypto",
    "liboqs":   RESULTS_ROOT / "compare5_liboqs",
}

keys = [f"{v}/{s}" for v in VARIANTS for s in STRATEGIES]
data = {label: {} for label in roots}
for label, root in roots.items():
    for v in VARIANTS:
        for s in STRATEGIES:
            summaries = load_runs(root, v, s)
            if summaries:
                data[label][f"{v}/{s}"] = extract(summaries)

# ── Figure 1: Grouped bar chart – balanced accuracy ───────────────────────────
fig, ax = plt.subplots(figsize=(7.2, 3.4))
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

n_keys = len(keys)
x = np.arange(n_keys)
bw = 0.32

backends = ["pqcrypto", "liboqs"]
colors   = [C["pqcrypto"],  C["liboqs"]]
edges    = [C["pq_edge"],   C["lq_edge"]]

for i, (label, color, edge) in enumerate(zip(backends, colors, edges)):
    means = [data[label].get(k, {}).get("real_acc_mean", np.nan) for k in keys]
    sds   = [data[label].get(k, {}).get("real_acc_sd",   0.0)    for k in keys]
    offset = (i - 0.5) * bw
    ax.bar(x + offset, means, bw,
           color=color, edgecolor=edge, linewidth=0.8,
           yerr=sds, capsize=2.5, error_kw={"elinewidth": 0.8, "ecolor": edge},
           label=label, zorder=3)

# chance line
ax.axhline(0.5, color=C["ref"], linewidth=1.2, linestyle="--", zorder=2, label="Chance (0.50)")

# variant group separators and labels
for sep in [3.5, 7.5]:
    ax.axvline(sep, color="#DDDDDD", linewidth=0.8, zorder=1)
for vi, (vname, xc) in enumerate(zip(VARIANTS, [1.5, 5.5, 9.5])):
    ax.text(xc, ax.get_ylim()[0] if False else 0.483,
            f"ML-KEM-{vname}", ha="center", va="top",
            fontsize=7.5, color="#888888", style="italic")

ax.set_xticks(x)
strat_labels = [s.split("/")[1].replace("_", r"\_") for s in keys]
ax.set_xticklabels(strat_labels, rotation=35, ha="right", fontsize=7)
ax.set_ylabel("Balanced Accuracy (mean $\\pm$ SD over 3 runs)")
ax.set_ylim(0.485, 0.610)
ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.2f"))
ax.grid(axis="y", color=C["grid"], linewidth=0.6, zorder=0)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

handles, lbls = ax.get_legend_handles_labels()
lbls = [l.replace("随机水平 (0.50)", "Chance (0.50)") for l in lbls]
ax.legend(handles, lbls, loc="upper right", framealpha=0.85,
          edgecolor="#DDDDDD", facecolor="white")
ax.set_title("Real-scenario Best-model Accuracy: pqcrypto vs.\\ liboqs", pad=6)

fig.tight_layout(pad=0.8)
out1 = OUT_DIR / "fig_backend_acc.pdf"
fig.savefig(out1, bbox_inches="tight", dpi=200)
plt.close(fig)
print(f"Saved: {out1}")


# ── Figure 2: Cohen's d scatter – pqcrypto vs liboqs ─────────────────────────
fig, ax = plt.subplots(figsize=(3.5, 3.5))
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

pq_d  = [data["pqcrypto"].get(k, {}).get("cohend_mean", np.nan) for k in keys]
lq_d  = [data["liboqs"].get(k, {}).get("cohend_mean",   np.nan) for k in keys]

variant_colors = {
    "512":  "#F9B8C6",
    "768":  "#B8D4F9",
    "1024": "#B8F9CC",
}
marker_map = {"single_bit": "o", "byte_flip": "s", "random_bytes": "^", "zero": "D"}

for k, px, ly in zip(keys, pq_d, lq_d):
    v, s = k.split("/")
    ax.scatter(px, ly,
               color=variant_colors[v], edgecolors=C["pq_edge"],
               marker=marker_map[s], s=55, linewidths=0.8, zorder=3)

lim = 0.22
ax.set_xlim(-lim, lim)
ax.set_ylim(-lim, lim)
ax.axhline(0, color="#DDDDDD", linewidth=0.7)
ax.axvline(0, color="#DDDDDD", linewidth=0.7)
ax.plot([-lim, lim], [-lim, lim], "--", color=C["ref"], linewidth=1.0, label="y = x")

ax.set_xlabel("Cohen's $d$ — pqcrypto")
ax.set_ylabel("Cohen's $d$ — liboqs")
ax.set_title("Effect Size Consistency across Implementations", pad=5)
ax.grid(color=C["grid"], linewidth=0.6, zorder=0)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

# legend for variants
variant_patches = [
    mpatches.Patch(color=c, label=f"ML-KEM-{v}", linewidth=0)
    for v, c in variant_colors.items()
]
strategy_handles = [
    plt.Line2D([0], [0], marker=m, color="w", markerfacecolor="#AAAAAA",
               markeredgecolor="#888888", markersize=5, label=s.replace("_", r"\_"))
    for s, m in marker_map.items()
]
ax.legend(handles=variant_patches + strategy_handles,
          loc="lower right", fontsize=6.5, framealpha=0.85,
          edgecolor="#DDDDDD", ncol=1)

fig.tight_layout(pad=0.8)
out2 = OUT_DIR / "fig_backend_cohend.pdf"
fig.savefig(out2, bbox_inches="tight", dpi=200)
plt.close(fig)
print(f"Saved: {out2}")
print("Done.")
