"""Generate the delay-sweep figure annotated with the analytical MDE band.

Reads the existing delay-sweep results and the per-variant pooled standard
deviations of ``mean_ns`` from the paper's 60 real-scenario runs, computes the
minimum detectable effect (MDE) for ML-KEM-768 at the |d|>=0.2 threshold and
at 80% power, and overlays this band on the balanced-accuracy-vs-delay curve.

Usage: python scripts/plot_mde_sweep.py
Output: docs/figures/delay_sweep_mde.png and .pdf
"""

from __future__ import annotations

import glob
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mlkem-leakage-matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "mlkem-leakage-cache"))

import numpy as np
import pandas as pd
from scipy.stats import norm
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mlkem_leakage.palette import ACCENT_COLOR, NEUTRAL_COLOR, LAVENDER, apply_style  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def pooled_std_ns(variant: str) -> float:
    files = glob.glob(str(ROOT / f"results/paper_runs/run_*/ml_kem_{variant}/*/real_traces.csv"))
    pooled = []
    for f in files:
        df = pd.read_csv(f)
        g0 = df[df.label == 0]["mean_ns"]
        g1 = df[df.label == 1]["mean_ns"]
        s = np.sqrt((g0.std(ddof=1) ** 2 + g1.std(ddof=1) ** 2) / 2)
        pooled.append(s)
    return float(np.mean(pooled))


def main() -> None:
    apply_style()

    sweep = json.load(open(ROOT / "results/delay_sweep_run/delay_sweep/sweep_results.json"))
    delays = [r["delay_ns"] for r in sweep]
    accuracies = [r["best_balanced_accuracy"] for r in sweep]

    n = 400
    alpha = 0.01
    z_alpha = norm.ppf(1 - alpha / 2)
    z_beta80 = norm.ppf(0.80)
    d_min80 = (z_alpha + z_beta80) * np.sqrt(2 / n)

    pooled_768 = pooled_std_ns("768")
    mde_d02 = 0.2 * pooled_768
    mde_80 = d_min80 * pooled_768

    plt.figure(figsize=(7, 4.2))
    plt.axvspan(mde_d02, mde_80, color=LAVENDER, alpha=0.45,
                label=f"ML-KEM-768 MDE band ($|d|$=0.2--0.242,\n{mde_d02/1000:.1f}--{mde_80/1000:.1f}~$\\mu$s)")
    plt.plot(delays, accuracies, marker="o", color=ACCENT_COLOR, linewidth=2,
             label="Positive-control balanced accuracy")
    plt.axhline(0.9, color=ACCENT_COLOR, linestyle="--", linewidth=1, alpha=0.6,
                 label="Detection threshold (0.90)")
    plt.axhline(0.5, color=NEUTRAL_COLOR, linestyle="--", linewidth=1, alpha=0.6,
                 label="Random baseline (0.50)")
    plt.xscale("log")
    plt.xlabel("Artificial delay (ns, log scale)")
    plt.ylabel("Best balanced accuracy")
    plt.title("Delay sweep with analytical minimum-detectable-effect band")
    plt.legend(fontsize=8, loc="upper left")
    plt.tight_layout()

    out_dir = ROOT / "docs" / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_dir / "delay_sweep_mde.png", dpi=300)
    plt.savefig(out_dir / "delay_sweep_mde.pdf")
    plt.close()

    print(f"pooled_std(768) = {pooled_768:.1f} ns")
    print(f"MDE @ |d|=0.2  = {mde_d02:.1f} ns")
    print(f"MDE @ 80% pwr  = {mde_80:.1f} ns")
    print(f"Wrote {out_dir / 'delay_sweep_mde.png'}")


if __name__ == "__main__":
    main()
