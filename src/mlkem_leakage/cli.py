"""Command-line entry point for the ML-KEM leakage experiment."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from .analysis import (
    analyze,
    write_analysis,
    write_delay_sweep_plot,
    write_feature_importance_plot,
    write_plot,
)
from .collector import collect_traces, write_csv, write_raw_csv
from .collector import INVALID_STRATEGIES


def _load_kem(variant: str):
    if variant == "512":
        from pqcrypto.kem import ml_kem_512
        return ml_kem_512
    elif variant == "1024":
        from pqcrypto.kem import ml_kem_1024
        return ml_kem_1024
    else:
        from pqcrypto.kem import ml_kem_768
        return ml_kem_768


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("results/latest"))
    parser.add_argument("--samples-per-class", type=int, default=400)
    parser.add_argument("--repetitions", type=int, default=50)
    parser.add_argument("--groups", type=int, default=40)
    parser.add_argument("--warmup", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260602)
    parser.add_argument("--control-delay-ns", type=int, default=20_000)
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=["512", "768", "1024"],
        default=["768"],
        metavar="N",
        help="ML-KEM security levels to test (default: 768)",
    )
    parser.add_argument(
        "--invalid-strategies",
        nargs="+",
        choices=INVALID_STRATEGIES,
        default=["single_bit"],
        metavar="NAME",
        help="Invalid ciphertext construction strategies to test (default: single_bit)",
    )
    parser.add_argument(
        "--delay-sweep",
        nargs="+",
        type=int,
        default=None,
        metavar="NS",
        help="Run positive-control sweep at these artificial delays (ns). "
             "Example: --delay-sweep 500 1000 2000 5000 10000 20000",
    )
    return parser.parse_args()


def _markdown(summary: dict) -> str:
    real = summary["scenarios"]["real"]
    control = summary["scenarios"]["positive_control"]
    best_real_model = max(real["models"], key=lambda m: m["balanced_accuracy_mean"])
    best_ctrl_model = max(control["models"], key=lambda m: m["balanced_accuracy_mean"])
    impl = summary["implementation"]
    strategy = summary["invalid_strategy"]
    return f"""# {impl} Timing Leakage Experiment

Invalid ciphertext strategy: **{strategy}**

## Result

- Real implementation leakage detected: **{real["leakage_detected"]}**
- Positive-control pipeline valid: **{summary["pipeline_valid"]}**
- Real timing difference: **{real["mean_difference_ns"]:.1f} ns**
- Real Welch p-value: **{real["welch_p_value"]:.4g}**
- Real Mann-Whitney p-value: **{real["mann_whitney_p_value"]:.4g}**
- Real KS p-value: **{real["ks_pvalue"]:.4g}**
- Real Cohen's d: **{real["cohens_d"]:.4f}**
- Best real model: **{best_real_model["model"]}** — balanced accuracy {best_real_model["balanced_accuracy_mean"]:.3f} ± {best_real_model["balanced_accuracy_std"]:.3f}, permutation p={best_real_model["permutation_pvalue"]:.3f}
- Best positive-control model: **{best_ctrl_model["model"]}** — balanced accuracy {best_ctrl_model["balanced_accuracy_mean"]:.3f}

## Interpretation

The positive control checks whether the measurement and detection pipeline can identify a
known timing signal. The real scenario reports detectable leakage only when the Welch
t-test, effect size, and grouped machine-learning evaluation all pass conservative
thresholds. A negative real result means no leakage was detected under this experiment;
it is not a proof that the implementation is side-channel secure.
"""


def _run_variant(args, variant: str, invalid_strategy: str, output_dir: Path) -> dict:
    kem = _load_kem(variant)
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = {}
    for scenario, delay in (("real", 0), ("positive_control", args.control_delay_ns)):
        traces, raw_timings = collect_traces(
            scenario=scenario,
            samples_per_class=args.samples_per_class,
            repetitions=args.repetitions,
            groups=args.groups,
            warmup=args.warmup,
            seed=args.seed,
            control_delay_ns=delay,
            invalid_strategy=invalid_strategy,
            kem=kem,
        )
        write_csv(traces, output_dir / f"{scenario}_traces.csv")
        write_raw_csv(raw_timings, output_dir / f"{scenario}_raw_timings.csv")
        report = analyze(traces, args.seed)
        write_analysis(report, output_dir, scenario)
        write_plot(traces, output_dir, scenario)
        write_feature_importance_plot(report, output_dir, scenario)
        scenarios[scenario] = report

    best_control = max(
        m["balanced_accuracy_mean"] for m in scenarios["positive_control"]["models"]
    )
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "implementation": f"pqcrypto.kem.ml_kem_{variant}",
        "invalid_strategy": invalid_strategy,
        "pqcrypto_version": importlib.metadata.version("pqcrypto"),
        "parameters": vars(args)
        | {"output_dir": str(output_dir), "variant": variant, "invalid_strategy": invalid_strategy},
        "pipeline_valid": bool(
            best_control >= 0.9
            and scenarios["positive_control"]["welch_p_value"] < 0.001
        ),
        "scenarios": scenarios,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "REPORT.md").write_text(_markdown(summary), encoding="utf-8")
    return summary


def _run_delay_sweep(args, output_dir: Path) -> None:
    sweep_dir = output_dir / "delay_sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)
    kem = _load_kem(args.variants[0])
    invalid_strategy = args.invalid_strategies[0]
    sweep_results = []
    for delay in sorted(args.delay_sweep):
        print(f"  delay sweep: {delay:,} ns")
        traces, _ = collect_traces(
            scenario="positive_control",
            samples_per_class=args.samples_per_class,
            repetitions=args.repetitions,
            groups=args.groups,
            warmup=args.warmup,
            seed=args.seed,
            control_delay_ns=delay,
            invalid_strategy=invalid_strategy,
            kem=kem,
        )
        report = analyze(traces, args.seed)
        best = max(m["balanced_accuracy_mean"] for m in report["models"])
        sweep_results.append(
            {
                "delay_ns": delay,
                "best_balanced_accuracy": best,
                "welch_p_value": report["welch_p_value"],
                "ks_pvalue": report["ks_pvalue"],
                "cohens_d": report["cohens_d"],
            }
        )
    write_delay_sweep_plot(sweep_results, sweep_dir)
    (sweep_dir / "sweep_results.json").write_text(
        json.dumps(sweep_results, indent=2), encoding="utf-8"
    )
    print(f"\nDelay sweep results written to {sweep_dir}")
    print(f"{'Delay (ns)':>12}  {'Best accuracy':>14}  {'Welch p':>10}  {'KS p':>10}")
    for r in sweep_results:
        print(
            f"{r['delay_ns']:>12,}  {r['best_balanced_accuracy']:>14.4f}"
            f"  {r['welch_p_value']:>10.4g}  {r['ks_pvalue']:>10.4g}"
        )


def main() -> None:
    args = _arguments()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    multi_variant = len(args.variants) > 1
    multi_strategy = len(args.invalid_strategies) > 1

    for variant in args.variants:
        for invalid_strategy in args.invalid_strategies:
            if multi_variant and multi_strategy:
                run_dir = args.output_dir / f"ml_kem_{variant}" / invalid_strategy
            elif multi_variant:
                run_dir = args.output_dir / f"ml_kem_{variant}"
            elif multi_strategy:
                run_dir = args.output_dir / invalid_strategy
            else:
                run_dir = args.output_dir
            if multi_variant or multi_strategy:
                print(f"\n=== ML-KEM-{variant} / {invalid_strategy} ===")
            summary = _run_variant(args, variant, invalid_strategy, run_dir)
            print(_markdown(summary))

    if multi_variant or multi_strategy:
        print("\n=== Cross-variant comparison ===")
        print(
            f"{'Variant':<12}  {'Strategy':<14}  {'Leakage':>8}"
            f"  {'Best acc (real)':>16}  {'Best acc (ctrl)':>16}"
        )
        for variant in args.variants:
            for invalid_strategy in args.invalid_strategies:
                if multi_variant and multi_strategy:
                    run_dir = args.output_dir / f"ml_kem_{variant}" / invalid_strategy
                elif multi_variant:
                    run_dir = args.output_dir / f"ml_kem_{variant}"
                else:
                    run_dir = args.output_dir / invalid_strategy
                s = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
                real_best = max(
                    m["balanced_accuracy_mean"] for m in s["scenarios"]["real"]["models"]
                )
                ctrl_best = max(
                    m["balanced_accuracy_mean"]
                    for m in s["scenarios"]["positive_control"]["models"]
                )
                print(
                    f"ML-KEM-{variant:<5}  {invalid_strategy:<14}"
                    f"  {str(s['scenarios']['real']['leakage_detected']):>8}"
                    f"  {real_best:>16.4f}  {ctrl_best:>16.4f}"
                )

    if args.delay_sweep:
        print("\n=== Delay sweep ===")
        _run_delay_sweep(args, args.output_dir)


if __name__ == "__main__":
    main()
