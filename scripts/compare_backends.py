"""Compare timing leakage experiment results across two KEM backends.

Usage:
    python scripts/compare_backends.py \\
        --roots results/pqcrypto_runs results/liboqs_runs \\
        --labels pqcrypto liboqs

Prints a side-by-side table of real-scenario statistics (mean over all runs)
for every variant × strategy combination, followed by a brief delta analysis.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

VARIANTS = ["512", "768", "1024"]
STRATEGIES = ["single_bit", "byte_flip", "random_bytes", "zero"]


def _load_runs(root: Path, variant: str, strategy: str) -> list[dict]:
    """Return list of summary dicts matching variant/strategy under root."""
    results = []
    for run_dir in sorted(root.glob(f"run_*/ml_kem_{variant}/{strategy}")):
        path = run_dir / "summary.json"
        if path.exists():
            results.append(json.loads(path.read_text(encoding="utf-8")))
    return results


def _summarize(summaries: list[dict]) -> dict | None:
    """Aggregate real-scenario stats across multiple runs."""
    if not summaries:
        return None
    diffs, welch_p, ks_p, cohend, real_acc, ctrl_acc, leak = [], [], [], [], [], [], []
    for s in summaries:
        real = s["scenarios"]["real"]
        ctrl = s["scenarios"]["positive_control"]
        diffs.append(real["mean_difference_ns"])
        welch_p.append(real["welch_p_value"])
        ks_p.append(real["ks_pvalue"])
        cohend.append(real["cohens_d"])
        real_acc.append(max(m["balanced_accuracy_mean"] for m in real["models"]))
        ctrl_acc.append(max(m["balanced_accuracy_mean"] for m in ctrl["models"]))
        leak.append(real["leakage_detected"])
    return {
        "n": len(summaries),
        "impl": summaries[0].get("implementation", "?"),
        "diff_mean": float(np.mean(diffs)),
        "diff_sd": float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0.0,
        "welch_p": float(np.mean(welch_p)),
        "ks_p": float(np.mean(ks_p)),
        "cohend": float(np.mean(cohend)),
        "real_acc": float(np.mean(real_acc)),
        "ctrl_acc": float(np.mean(ctrl_acc)),
        "leak_count": int(sum(leak)),
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roots",
        nargs="+",
        type=Path,
        default=[Path("results/pqcrypto_runs"), Path("results/liboqs_runs")],
        metavar="DIR",
        help="Result root directories to compare (default: results/pqcrypto_runs results/liboqs_runs)",
    )
    parser.add_argument(
        "--labels",
        nargs="+",
        default=None,
        metavar="LABEL",
        help="Short labels for each root (default: derived from directory name)",
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        default=VARIANTS,
        metavar="N",
    )
    parser.add_argument(
        "--strategies",
        nargs="+",
        default=STRATEGIES,
        metavar="NAME",
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    roots = args.roots
    labels = args.labels or [r.name for r in roots]
    if len(labels) != len(roots):
        raise ValueError("--labels count must match --roots count")

    # Load all data
    data: dict[str, dict] = {label: {} for label in labels}
    for root, label in zip(roots, labels):
        for variant in args.variants:
            for strategy in args.strategies:
                key = f"{variant}/{strategy}"
                summaries = _load_runs(root, variant, strategy)
                data[label][key] = _summarize(summaries)

    # Header
    col = 22
    lbl_w = max(len(l) for l in labels)
    print("\n=== Backend comparison: real-scenario statistics (mean over runs) ===\n")
    hdr = f"{'Variant/Strategy':<20}"
    for label in labels:
        hdr += f"  {label.center(col)}"
    print(hdr)
    print("-" * (20 + (col + 2) * len(labels)))

    all_real_acc: dict[str, list] = {l: [] for l in labels}
    all_leak: dict[str, list] = {l: [] for l in labels}

    for variant in args.variants:
        for strategy in args.strategies:
            key = f"{variant}/{strategy}"
            row = f"  {variant}/{strategy:<14}"
            for label in labels:
                s = data[label].get(key)
                if s is None:
                    row += f"  {'(no data)':>{col}}"
                    continue
                cell = (
                    f"acc={s['real_acc']:.3f} "
                    f"wp={s['welch_p']:.3f} "
                    f"d={s['cohend']:+.3f} "
                    f"leak={s['leak_count']}/{s['n']}"
                )
                row += f"  {cell:>{col}}"
                all_real_acc[label].append(s["real_acc"])
                all_leak[label].append(s["leak_count"])
            print(row)

    print("\n=== Summary ===")
    for label in labels:
        accs = all_real_acc[label]
        leaks = sum(all_leak[label])
        total = sum(len(_load_runs(roots[labels.index(label)], v, st))
                    for v in args.variants for st in args.strategies)
        if accs:
            print(
                f"{label:<{lbl_w}}: mean real acc={np.mean(accs):.4f}  "
                f"min/max={np.min(accs):.4f}/{np.max(accs):.4f}  "
                f"leakage={leaks}/{total}"
            )
        else:
            print(f"{label:<{lbl_w}}: (no data)")

    # Delta section (only meaningful for exactly two backends)
    if len(labels) == 2:
        print(f"\n=== Delta ({labels[1]} − {labels[0]}) ===")
        print("Positive delta_acc means the second backend is slightly more classifiable.")
        for variant in args.variants:
            for strategy in args.strategies:
                key = f"{variant}/{strategy}"
                s0 = data[labels[0]].get(key)
                s1 = data[labels[1]].get(key)
                if s0 is None or s1 is None:
                    continue
                delta_acc = s1["real_acc"] - s0["real_acc"]
                delta_d = s1["cohend"] - s0["cohend"]
                print(
                    f"  {variant}/{strategy:<14}: "
                    f"Δacc={delta_acc:+.4f}  Δd={delta_d:+.4f}  "
                    f"welch_p {labels[0]}={s0['welch_p']:.3f} {labels[1]}={s1['welch_p']:.3f}"
                )


if __name__ == "__main__":
    main()
