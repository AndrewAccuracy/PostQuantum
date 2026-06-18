"""Build cross-variant / cross-strategy comparison figures from results/paper_runs.

Reads the 5-run x 3-variant x 4-strategy paper matrix and writes:

- variant_timing_distributions.png: real-scenario timing histograms per variant
  (single_bit strategy, all 5 runs combined)
- variant_strategy_accuracy.png: real vs positive-control balanced accuracy per
  variant and invalid-ciphertext strategy, averaged across runs
- variant_feature_importance.csv: random-forest feature importance table per
  variant (single_bit strategy, averaged across runs)
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mlkem-leakage-matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "mlkem-leakage-cache"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from mlkem_leakage.palette import ALTERED_COLOR, CONTROL_COLOR, NEUTRAL_COLOR, VALID_COLOR, apply_style

apply_style()

INPUT_ROOT = Path("results/paper_runs")
OUTPUT_DIR = Path("results/paper_artifacts")
VARIANTS = ["512", "768", "1024"]
STRATEGIES = ["single_bit", "byte_flip", "random_bytes", "zero"]
FEATURE_LABELS = {
    "mean_ns": "mean",
    "median_ns": "median",
    "std_ns": "std",
    "min_ns": "min",
    "max_ns": "max",
    "p10_ns": "p10",
    "p90_ns": "p90",
    "iqr_ns": "IQR",
    "mad_ns": "MAD",
    "trimmed_mean_ns": "trimmed mean",
    "skewness": "skewness",
    "kurtosis": "kurtosis",
    "cv": "CV",
}


def _save(name: str) -> None:
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / name, dpi=300, bbox_inches="tight")
    plt.close()


def plot_timing_distributions() -> None:
    figure, axes = plt.subplots(1, 3, figsize=(13.5, 4.0), sharey=False)
    for axis, variant in zip(axes, VARIANTS):
        valid_vals: list[float] = []
        altered_vals: list[float] = []
        for run_dir in sorted(INPUT_ROOT.glob(f"run_*/ml_kem_{variant}/single_bit")):
            with (run_dir / "real_traces.csv").open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    value = float(row["mean_ns"]) / 1000
                    if int(row["label"]) == 0:
                        valid_vals.append(value)
                    else:
                        altered_vals.append(value)
        combined = np.asarray(valid_vals + altered_vals)
        lo, hi = np.percentile(combined, [0.5, 99.5])
        bins = np.linspace(lo, hi, 31)
        axis.hist(valid_vals, bins=bins, density=True, alpha=0.85, label="Valid ciphertext", color=VALID_COLOR)
        axis.hist(altered_vals, bins=bins, density=True, alpha=0.85, label="Altered ciphertext", color=ALTERED_COLOR)
        axis.set_xlim(lo, hi)
        axis.set_title(f"ML-KEM-{variant}")
        axis.set_xlabel("Mean decapsulation time (us)")
    axes[0].set_ylabel("Density")
    axes[0].legend()
    figure.suptitle("Real-scenario timing distribution by parameter set (single_bit, 5 runs)")
    _save("variant_timing_distributions.png")


def plot_strategy_accuracy() -> None:
    figure, axes = plt.subplots(1, 3, figsize=(14.5, 4.4), sharey=True)
    x = np.arange(len(STRATEGIES))
    width = 0.34
    for axis, variant in zip(axes, VARIANTS):
        real_means, real_stds, ctrl_means, ctrl_stds = [], [], [], []
        for strategy in STRATEGIES:
            real_scores, ctrl_scores = [], []
            for run_dir in sorted(INPUT_ROOT.glob(f"run_*/ml_kem_{variant}/{strategy}")):
                summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
                real_scores.append(
                    max(m["balanced_accuracy_mean"] for m in summary["scenarios"]["real"]["models"])
                )
                ctrl_scores.append(
                    max(
                        m["balanced_accuracy_mean"]
                        for m in summary["scenarios"]["positive_control"]["models"]
                    )
                )
            real_means.append(np.mean(real_scores))
            real_stds.append(np.std(real_scores, ddof=1))
            ctrl_means.append(np.mean(ctrl_scores))
            ctrl_stds.append(np.std(ctrl_scores, ddof=1))
        axis.bar(x - width / 2, real_means, width, yerr=real_stds, capsize=4, label="real", color=ALTERED_COLOR)
        axis.bar(x + width / 2, ctrl_means, width, yerr=ctrl_stds, capsize=4, label="positive_control", color=CONTROL_COLOR)
        axis.axhline(0.5, color=NEUTRAL_COLOR, linestyle="--", linewidth=1)
        axis.set_xticks(x, [s.replace("_", "\n") for s in STRATEGIES])
        axis.set_title(f"ML-KEM-{variant}")
        axis.set_ylim(0, 1.08)
    axes[0].set_ylabel("Best-model balanced accuracy\n(mean +/- sd over 5 runs)")
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(handles, labels, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.02))
    figure.suptitle("Real vs. positive-control accuracy by parameter set and invalid-ciphertext strategy")
    figure.subplots_adjust(bottom=0.18)
    _save("variant_strategy_accuracy.png")


def write_feature_importance_table() -> None:
    feature_names: list[str] | None = None
    per_variant: dict[str, list[list[float]]] = defaultdict(list)
    for variant in VARIANTS:
        for run_dir in sorted(INPUT_ROOT.glob(f"run_*/ml_kem_{variant}/single_bit")):
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            importances = summary["scenarios"]["real"]["feature_importances"]
            if feature_names is None:
                feature_names = [d["feature"] for d in importances]
            order = {d["feature"]: d["importance"] for d in importances}
            per_variant[variant].append([order[name] for name in feature_names])

    assert feature_names is not None
    means = {variant: np.mean(per_variant[variant], axis=0) for variant in VARIANTS}
    overall = np.mean([means[v] for v in VARIANTS], axis=0)
    order_idx = np.argsort(overall)[::-1]
    with (OUTPUT_DIR / "variant_feature_importance.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["feature", "ml_kem_512", "ml_kem_768", "ml_kem_1024", "mean"])
        for i in order_idx:
            writer.writerow(
                [
                    FEATURE_LABELS.get(feature_names[i], feature_names[i]),
                    *(f"{means[variant][i]:.6f}" for variant in VARIANTS),
                    f"{overall[i]:.6f}",
                ]
            )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    plot_timing_distributions()
    plot_strategy_accuracy()
    write_feature_importance_table()
    print(f"Wrote variant comparison artifacts to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
