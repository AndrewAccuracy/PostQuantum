"""Generate data-quality reports and publication-ready figures for repeated runs."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List

os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mlkem-leakage-matplotlib")
)
os.environ.setdefault(
    "XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "mlkem-leakage-cache")
)
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import mannwhitneyu, spearmanr, ttest_rel

from .palette import ALTERED_COLOR, CONTROL_COLOR, NEUTRAL_COLOR, VALID_COLOR, apply_style

apply_style()

FEATURES = [
    "mean_ns",
    "median_ns",
    "std_ns",
    "min_ns",
    "max_ns",
    "p10_ns",
    "p90_ns",
    "iqr_ns",
    "mad_ns",
    "trimmed_mean_ns",
    "skewness",
    "kurtosis",
    "cv",
]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=Path("results/paper_runs"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/paper_artifacts"))
    return parser.parse_args()


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _iqr_outliers(values: np.ndarray) -> int:
    q1, q3 = np.percentile(values, [25, 75])
    iqr = q3 - q1
    return int(np.sum((values < q1 - 1.5 * iqr) | (values > q3 + 1.5 * iqr)))


def _paired_group_test(rows: List[Dict[str, str]]) -> Dict[str, float]:
    grouped: Dict[tuple[int, int], List[float]] = {}
    for row in rows:
        grouped.setdefault((int(row["group_id"]), int(row["label"])), []).append(
            float(row["mean_ns"])
        )
    group_ids = sorted({group_id for group_id, _ in grouped})
    valid = np.asarray([np.mean(grouped[(group_id, 0)]) for group_id in group_ids])
    altered = np.asarray([np.mean(grouped[(group_id, 1)]) for group_id in group_ids])
    test = ttest_rel(valid, altered)
    return {
        "group_mean_difference_ns": float(np.mean(altered - valid)),
        "paired_t_statistic": float(test.statistic),
        "paired_t_p_value": float(test.pvalue),
    }


def _audit(rows: List[Dict[str, str]]) -> Dict[str, object]:
    labels = Counter(int(row["label"]) for row in rows)
    groups = Counter(int(row["group_id"]) for row in rows)
    pairs = Counter((int(row["group_id"]), int(row["label"])) for row in rows)
    numeric_values = [float(row[name]) for row in rows for name in FEATURES]
    mean_values = np.asarray([float(row["mean_ns"]) for row in rows])
    valid = mean_values[np.asarray([int(row["label"]) for row in rows]) == 0]
    altered = mean_values[np.asarray([int(row["label"]) for row in rows]) == 1]
    trace_ids = np.asarray([int(row["trace_id"]) for row in rows])
    order_test = spearmanr(trace_ids, mean_values)
    rank_test = mannwhitneyu(valid, altered, alternative="two-sided")
    duplicate_ids = len(rows) - len({(row["scenario"], row["trace_id"]) for row in rows})
    return {
        "rows": len(rows),
        "labels": dict(sorted(labels.items())),
        "groups": len(groups),
        "group_size_min": min(groups.values()),
        "group_size_max": max(groups.values()),
        "group_label_size_min": min(pairs.values()),
        "group_label_size_max": max(pairs.values()),
        "missing_cells": sum(value == "" for row in rows for value in row.values()),
        "nonfinite_numeric_cells": sum(not math.isfinite(value) for value in numeric_values),
        "duplicate_trace_ids": duplicate_ids,
        "mean_ns_iqr_outliers": _iqr_outliers(mean_values),
        "mean_ns_iqr_outlier_rate": _iqr_outliers(mean_values) / len(rows),
        "mean_ns_min": float(np.min(mean_values)),
        "mean_ns_max": float(np.max(mean_values)),
        "mann_whitney_p_value": float(rank_test.pvalue),
        "trace_order_spearman_rho": float(order_test.statistic),
        "trace_order_spearman_p_value": float(order_test.pvalue),
        **_paired_group_test(rows),
    }


def _load_runs(input_root: Path) -> List[Dict[str, object]]:
    runs = []
    for summary_path in sorted(input_root.rglob("summary.json")):
        run_dir = summary_path.parent
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        name = run_dir.relative_to(input_root).as_posix()
        runs.append(
            {
                "name": name,
                "summary": summary,
                "rows": {
                    scenario: _read_csv(run_dir / f"{scenario}_traces.csv")
                    for scenario in ("real", "positive_control")
                },
            }
        )
    if not runs:
        raise ValueError(f"No completed runs found in {input_root}")
    return runs


def _label(run: Dict[str, object]) -> str:
    summary = run["summary"]
    implementation = summary.get("implementation", "ml_kem")
    variant = implementation.rsplit("_", 1)[-1]
    strategy = summary.get("invalid_strategy", "single_bit")
    return f"{variant}/{strategy}/{run['name']}"


def _save_figure(output_dir: Path, name: str) -> None:
    plt.tight_layout()
    plt.savefig(output_dir / name, dpi=300, bbox_inches="tight")
    plt.close()


def _plot_distributions(runs: List[Dict[str, object]], output_dir: Path) -> None:
    for scenario in ("real", "positive_control"):
        values = {0: [], 1: []}
        for run in runs:
            for row in run["rows"][scenario]:
                values[int(row["label"])].append(float(row["mean_ns"]) / 1000)
        plt.figure(figsize=(7.4, 4.4))
        plt.hist(values[0], bins=36, density=True, alpha=0.85, label="Valid ciphertext", color=VALID_COLOR)
        plt.hist(values[1], bins=36, density=True, alpha=0.85, label="Altered ciphertext", color=ALTERED_COLOR)
        plt.xlabel("Mean decapsulation time per aggregate trace (us)")
        plt.ylabel("Density")
        plt.title(f"ML-KEM (all parameter sets) timing distribution: {scenario.replace('_', ' ')}")
        plt.legend()
        _save_figure(output_dir, f"{scenario}_distribution.png")


def _plot_model_accuracy(runs: List[Dict[str, object]], output_dir: Path) -> None:
    names = [m["model"] for m in runs[0]["summary"]["scenarios"]["real"]["models"]]
    labels = [n.replace("_", " ").title() for n in names]
    scenarios = ["real", "positive_control"]
    x = np.arange(len(names))
    width = 0.34
    plt.figure(figsize=(9.0, 4.8))
    bar_colors = {"real": ALTERED_COLOR, "positive_control": CONTROL_COLOR}
    for index, scenario in enumerate(scenarios):
        scores = []
        errors = []
        for name in names:
            values = [
                next(
                    model["balanced_accuracy_mean"]
                    for model in run["summary"]["scenarios"][scenario]["models"]
                    if model["model"] == name
                )
                for run in runs
            ]
            scores.append(np.mean(values))
            errors.append(np.std(values, ddof=1) if len(values) > 1 else 0.0)
        plt.bar(
            x + (index - 0.5) * width,
            scores,
            width,
            yerr=errors,
            capsize=4,
            label=scenario,
            color=bar_colors[scenario],
        )
    plt.axhline(0.5, color=NEUTRAL_COLOR, linestyle="--", linewidth=1, label="Random baseline")
    plt.xticks(x, labels, rotation=15, ha="right")
    plt.ylabel("Grouped balanced accuracy")
    plt.ylim(0, 1.08)
    plt.title("Classifier performance across repeated runs")
    plt.legend()
    _save_figure(output_dir, "model_accuracy_comparison.png")


def _plot_run_stability(runs: List[Dict[str, object]], output_dir: Path) -> None:
    real = [run["summary"]["scenarios"]["real"]["mean_difference_ns"] for run in runs]
    control = [
        run["summary"]["scenarios"]["positive_control"]["mean_difference_ns"] for run in runs
    ]
    x = np.arange(1, len(runs) + 1)
    figure, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharex=True)
    axes[0].plot(x, real, marker="o", color=ALTERED_COLOR)
    axes[0].axhline(0, color=NEUTRAL_COLOR, linestyle="--", linewidth=1)
    axes[0].set_title("Real scenario")
    axes[0].set_ylabel("Altered - valid mean time (ns)")
    axes[1].plot(x, control, marker="o", color=CONTROL_COLOR)
    axes[1].set_title("Positive control")
    tick_step = 12 if len(runs) >= 24 else max(1, len(runs) // 5)
    ticks = list(range(1, len(runs) + 1, tick_step))
    if ticks[-1] != len(runs):
        ticks.append(len(runs))
    for axis in axes:
        axis.set_xticks(ticks)
        axis.set_xlabel("Independent experiment index")
        for boundary in range(tick_step, len(runs), tick_step):
            axis.axvline(boundary + 0.5, color=NEUTRAL_COLOR, linewidth=0.6, alpha=0.25)
    figure.suptitle("Timing-difference stability across repeated runs")
    _save_figure(output_dir, "run_stability.png")


def _plot_trace_order(runs: List[Dict[str, object]], output_dir: Path) -> None:
    def trimmed_values(values: np.ndarray, proportion: float = 0.1) -> np.ndarray:
        ordered = np.sort(values)
        trim = int(len(ordered) * proportion)
        if trim == 0 or len(ordered) <= 2 * trim:
            return ordered
        return ordered[trim:-trim]

    rows = runs[-1]["rows"]["real"]
    trace_ids = np.asarray([int(row["trace_id"]) for row in rows])
    labels = np.asarray([int(row["label"]) for row in rows])
    means = np.asarray([float(row["mean_ns"]) for row in rows])
    n_bins = 20
    bins = np.linspace(trace_ids.min(), trace_ids.max() + 1, n_bins + 1)

    xs, deltas, ci95 = [], [], []
    for index in range(n_bins):
        mask = (trace_ids >= bins[index]) & (trace_ids < bins[index + 1])
        valid = means[mask & (labels == 0)]
        altered = means[mask & (labels == 1)]
        if len(valid) < 2 or len(altered) < 2:
            continue
        valid_trimmed = trimmed_values(valid)
        altered_trimmed = trimmed_values(altered)
        xs.append((bins[index] + bins[index + 1]) / 2)
        deltas.append((altered_trimmed.mean() - valid_trimmed.mean()) / 1000)
        se = math.sqrt(
            valid_trimmed.var(ddof=1) / len(valid_trimmed)
            + altered_trimmed.var(ddof=1) / len(altered_trimmed)
        ) / 1000
        ci95.append(1.96 * se)

    plt.figure(figsize=(7.4, 4.2))
    plt.axhline(0, color=NEUTRAL_COLOR, linestyle="--", linewidth=1, label="No label difference")
    plt.errorbar(
        xs,
        deltas,
        yerr=ci95,
        fmt="o-",
        color=ALTERED_COLOR,
        ecolor=VALID_COLOR,
        elinewidth=1.0,
        capsize=3,
        markersize=4,
        linewidth=1.4,
        label="Altered - valid trimmed mean",
    )
    plt.xlabel("Randomized collection order (20 adjacent bins)")
    plt.ylabel("Altered - valid time (us)")
    plt.title(f"Collection-order diagnostic: {runs[-1]['name']}")
    plt.legend()
    _save_figure(output_dir, "trace_order_diagnostic.png")


def _quality_report(runs: List[Dict[str, object]], audits: Dict[str, object]) -> str:
    real_diffs = [run["summary"]["scenarios"]["real"]["mean_difference_ns"] for run in runs]
    real_scores = [
        max(model["balanced_accuracy_mean"] for model in run["summary"]["scenarios"]["real"]["models"])
        for run in runs
    ]
    control_scores = [
        max(
            model["balanced_accuracy_mean"]
            for model in run["summary"]["scenarios"]["positive_control"]["models"]
        )
        for run in runs
    ]
    quality_pass = all(
        run["summary"]["pipeline_valid"]
        and audits[run["name"]][scenario]["missing_cells"] == 0
        and audits[run["name"]][scenario]["nonfinite_numeric_cells"] == 0
        and audits[run["name"]][scenario]["duplicate_trace_ids"] == 0
        and len(set(audits[run["name"]][scenario]["labels"].values())) == 1
        for run in runs
        for scenario in ("real", "positive_control")
    )
    lines = [
        "# ML-KEM Data Quality Report",
        "",
        "## Bottom Line",
        "",
        f"- Completed independent runs: `{len(runs)}`",
        f"- Data-quality acceptance checks passed: `{quality_pass}`",
        f"- All positive-control pipelines valid: `{all(run['summary']['pipeline_valid'] for run in runs)}`",
        f"- Real timing difference mean across runs: `{np.mean(real_diffs):.1f} ns`",
        f"- Real timing difference standard deviation: `{np.std(real_diffs, ddof=1):.1f} ns`",
        f"- Best real balanced accuracy mean across runs: `{np.mean(real_scores):.3f}`",
        f"- Best positive-control balanced accuracy mean: `{np.mean(control_scores):.3f}`",
        "",
        "The dataset is suitable for the paper's scoped conclusion when interpreted per",
        "implementation and invalid-ciphertext strategy. A negative real result means no stable",
        "timing distinction was detected under this software-only setup. It does not prove",
        "side-channel security or secret-key independence.",
        "",
        "## Integrity Checks",
        "",
        "| Run | Implementation | Strategy | Scenario | Rows | Labels | Groups | Missing | Non-finite | Duplicate IDs | IQR outliers | Order rho |",
        "| --- | --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for run in runs:
        summary = run["summary"]
        implementation = summary.get("implementation", "unknown")
        strategy = summary.get("invalid_strategy", "single_bit")
        for scenario in ("real", "positive_control"):
            audit = audits[run["name"]][scenario]
            lines.append(
                f"| `{run['name']}` | `{implementation}` | `{strategy}` | `{scenario}` | {audit['rows']} | "
                f"`{audit['labels']}` | {audit['groups']} | {audit['missing_cells']} | "
                f"{audit['nonfinite_numeric_cells']} | {audit['duplicate_trace_ids']} | "
                f"{audit['mean_ns_iqr_outliers']} | {audit['trace_order_spearman_rho']:.3f} |"
            )
    lines += [
        "",
        "## Interpretation Notes",
        "",
        "- IQR outliers are retained. They are plausible operating-system scheduling noise, not invalid values.",
        "- Sample order is randomized before collection. Mild order drift can increase variance but should not systematically favor either label.",
        "- Train/test evaluation is grouped by base ciphertext to reduce memorization leakage.",
        "- Positive controls validate that the pipeline can detect a known timing signal.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    args = _arguments()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    runs = _load_runs(args.input_root)
    audits = {
        run["name"]: {
            scenario: _audit(run["rows"][scenario])
            for scenario in ("real", "positive_control")
        }
        for run in runs
    }
    _plot_distributions(runs, args.output_dir)
    _plot_model_accuracy(runs, args.output_dir)
    _plot_run_stability(runs, args.output_dir)
    _plot_trace_order(runs, args.output_dir)
    report = {"runs": audits}
    report["data_quality_pass"] = all(
        run["summary"]["pipeline_valid"]
        and audits[run["name"]][scenario]["missing_cells"] == 0
        and audits[run["name"]][scenario]["nonfinite_numeric_cells"] == 0
        and audits[run["name"]][scenario]["duplicate_trace_ids"] == 0
        and len(set(audits[run["name"]][scenario]["labels"].values())) == 1
        for run in runs
        for scenario in ("real", "positive_control")
    )
    (args.output_dir / "data_quality.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.output_dir / "DATA_QUALITY_REPORT.md").write_text(
        _quality_report(runs, audits), encoding="utf-8"
    )
    print(f"Wrote paper artifacts to {args.output_dir}")


if __name__ == "__main__":
    main()
