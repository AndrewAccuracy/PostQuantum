"""Aggregate statistics across results/paper_runs for the paper draft update.

Prints per-variant/strategy aggregates over the 5 independent runs, plus
overall headline numbers used in the abstract / conclusion.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path("results/paper_runs")
VARIANTS = ["512", "768", "1024"]
STRATEGIES = ["single_bit", "byte_flip", "random_bytes", "zero"]


def main() -> None:
    rows = []
    all_real_diffs = []
    all_real_best_acc = []
    all_ctrl_best_acc = []
    leakage_flags = []

    for variant in VARIANTS:
        for strategy in STRATEGIES:
            diffs, welch_p, mw_p, ks_p, cohend = [], [], [], [], []
            real_acc, ctrl_acc, leak = [], [], []
            for run_dir in sorted(ROOT.glob(f"run_*/ml_kem_{variant}/{strategy}")):
                summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
                real = summary["scenarios"]["real"]
                ctrl = summary["scenarios"]["positive_control"]
                diffs.append(real["mean_difference_ns"])
                welch_p.append(real["welch_p_value"])
                mw_p.append(real["mann_whitney_p_value"])
                ks_p.append(real["ks_pvalue"])
                cohend.append(real["cohens_d"])
                ra = max(m["balanced_accuracy_mean"] for m in real["models"])
                ca = max(m["balanced_accuracy_mean"] for m in ctrl["models"])
                real_acc.append(ra)
                ctrl_acc.append(ca)
                leak.append(real["leakage_detected"])
                all_real_diffs.append(real["mean_difference_ns"])
                all_real_best_acc.append(ra)
                all_ctrl_best_acc.append(ca)
                leakage_flags.append(real["leakage_detected"])
            rows.append(
                {
                    "variant": variant,
                    "strategy": strategy,
                    "diff_mean": float(np.mean(diffs)),
                    "diff_sd": float(np.std(diffs, ddof=1)),
                    "welch_p_mean": float(np.mean(welch_p)),
                    "welch_p_min": float(np.min(welch_p)),
                    "mw_p_mean": float(np.mean(mw_p)),
                    "ks_p_mean": float(np.mean(ks_p)),
                    "ks_p_min": float(np.min(ks_p)),
                    "cohend_mean": float(np.mean(cohend)),
                    "cohend_absmax": float(np.max(np.abs(cohend))),
                    "real_acc_mean": float(np.mean(real_acc)),
                    "real_acc_sd": float(np.std(real_acc, ddof=1)),
                    "ctrl_acc_mean": float(np.mean(ctrl_acc)),
                    "ctrl_acc_sd": float(np.std(ctrl_acc, ddof=1)),
                    "leak_count": int(sum(leak)),
                }
            )

    print("=== Headline (all 60 combos, real scenario) ===")
    print(f"mean diff ns: {np.mean(all_real_diffs):.1f}")
    print(f"sd diff ns:   {np.std(all_real_diffs, ddof=1):.1f}")
    print(f"min/max diff ns: {np.min(all_real_diffs):.1f} / {np.max(all_real_diffs):.1f}")
    print(f"real best-acc mean: {np.mean(all_real_best_acc):.4f}")
    print(f"real best-acc min/max: {np.min(all_real_best_acc):.4f} / {np.max(all_real_best_acc):.4f}")
    print(f"ctrl best-acc mean: {np.mean(all_ctrl_best_acc):.4f}")
    print(f"ctrl best-acc min/max: {np.min(all_ctrl_best_acc):.4f} / {np.max(all_ctrl_best_acc):.4f}")
    print(f"any leakage detected: {any(leakage_flags)} (count={sum(leakage_flags)} / {len(leakage_flags)})")
    print(f"max |cohen d|: {max(abs(r['cohend_mean']) for r in rows):.4f}")
    print(f"max welch p over combos (mean of 5): min={min(r['welch_p_mean'] for r in rows):.4f}")

    print("\n=== Per variant/strategy (mean over 5 runs) ===")
    for r in rows:
        print(
            f"{r['variant']}/{r['strategy']:>12}: "
            f"diff={r['diff_mean']:+8.1f}+/-{r['diff_sd']:7.1f} ns  "
            f"welch_p={r['welch_p_mean']:.3f}  mw_p={r['mw_p_mean']:.3f}  ks_p={r['ks_p_mean']:.3f}  "
            f"d={r['cohend_mean']:+.4f}  "
            f"real_acc={r['real_acc_mean']:.3f}+/-{r['real_acc_sd']:.3f}  "
            f"ctrl_acc={r['ctrl_acc_mean']:.3f}+/-{r['ctrl_acc_sd']:.3f}  "
            f"leak={r['leak_count']}/5"
        )

    # Mean decapsulation time per variant (single_bit, valid ciphertexts, all 5 runs)
    print("\n=== Mean decapsulation time per variant (single_bit, valid, 5 runs) ===")
    for variant in VARIANTS:
        vals = []
        for run_dir in sorted(ROOT.glob(f"run_*/ml_kem_{variant}/single_bit")):
            with (run_dir / "real_traces.csv").open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    if int(row["label"]) == 0:
                        vals.append(float(row["mean_ns"]))
        print(f"ML-KEM-{variant}: mean={np.mean(vals)/1000:.2f} us, sd={np.std(vals, ddof=1)/1000:.2f} us")

    # Feature importance top-3 per variant (single_bit, mean over 5 runs)
    print("\n=== Top-3 feature importances per variant (single_bit, mean over 5 runs) ===")
    feature_names = None
    for variant in VARIANTS:
        per_run = []
        for run_dir in sorted(ROOT.glob(f"run_*/ml_kem_{variant}/single_bit")):
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            importances = summary["scenarios"]["real"]["feature_importances"]
            if feature_names is None:
                feature_names = [d["feature"] for d in importances]
            order = {d["feature"]: d["importance"] for d in importances}
            per_run.append([order[name] for name in feature_names])
        means = np.mean(per_run, axis=0)
        ranked = sorted(zip(feature_names, means), key=lambda t: -t[1])[:3]
        print(f"ML-KEM-{variant}: " + ", ".join(f"{name}({val:.3f})" for name, val in ranked))


if __name__ == "__main__":
    main()
