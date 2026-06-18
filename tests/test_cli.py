from pathlib import Path
from types import SimpleNamespace

from mlkem_leakage import cli
from mlkem_leakage.collector import RawTiming, Trace


def _trace(scenario: str) -> Trace:
    return Trace(
        scenario=scenario,
        invalid_strategy="single_bit",
        trace_id=0,
        group_id=0,
        label=0,
        mean_ns=1000.0,
        median_ns=1000.0,
        std_ns=10.0,
        min_ns=990.0,
        max_ns=1010.0,
        p10_ns=995.0,
        p90_ns=1005.0,
        iqr_ns=10.0,
        mad_ns=5.0,
        trimmed_mean_ns=1000.0,
        skewness=0.0,
        kurtosis=0.0,
        cv=0.01,
    )


def _raw(scenario: str) -> RawTiming:
    return RawTiming(
        scenario=scenario,
        invalid_strategy="single_bit",
        trace_id=0,
        group_id=0,
        label=0,
        rep=0,
        time_ns=1000,
    )


def _report(scenario: str) -> dict:
    control = scenario == "positive_control"
    return {
        "samples": 1,
        "features": ["mean_ns"],
        "valid_mean_ns": 1000.0,
        "altered_mean_ns": 21000.0 if control else 1002.0,
        "mean_difference_ns": 20000.0 if control else 2.0,
        "welch_t_statistic": 10.0 if control else 0.1,
        "welch_p_value": 0.0001 if control else 0.5,
        "mann_whitney_u_statistic": 1.0,
        "mann_whitney_p_value": 0.5,
        "ks_statistic": 0.0,
        "ks_pvalue": 0.5,
        "cohens_d": 5.0 if control else 0.01,
        "feature_importances": [{"feature": "mean_ns", "importance": 1.0}],
        "models": [
            {
                "model": "stub",
                "balanced_accuracy_mean": 0.95 if control else 0.5,
                "balanced_accuracy_std": 0.0,
                "roc_auc_mean": 0.95 if control else 0.5,
                "roc_auc_std": 0.0,
                "permutation_pvalue": 0.01,
            }
        ],
        "leakage_detected": False,
    }


def test_run_variant_writes_summary_report_and_pipeline_status(tmp_path, monkeypatch):
    calls = []
    fake_kem = SimpleNamespace(name="pqcrypto.kem.ml_kem_768", version="test")

    def fake_collect_traces(**kwargs):
        calls.append(kwargs)
        scenario = kwargs["scenario"]
        return [_trace(scenario)], [_raw(scenario)]

    monkeypatch.setattr(cli, "make_kem", lambda variant, backend: fake_kem)
    monkeypatch.setattr(cli, "collect_traces", fake_collect_traces)
    monkeypatch.setattr(cli, "analyze", lambda traces, seed: _report(traces[0].scenario))
    monkeypatch.setattr(cli, "write_plot", lambda traces, output_dir, scenario: None)
    monkeypatch.setattr(
        cli,
        "write_feature_importance_plot",
        lambda report, output_dir, scenario: None,
    )

    args = SimpleNamespace(
        output_dir=Path("unused"),
        samples_per_class=4,
        repetitions=2,
        groups=2,
        warmup=1,
        seed=7,
        control_delay_ns=20_000,
        backend="pqcrypto",
        variants=["768"],
        invalid_strategies=["single_bit"],
        delay_sweep=None,
    )

    summary = cli._run_variant(args, "768", "single_bit", tmp_path)

    assert summary["pipeline_valid"] is True
    assert summary["implementation"] == "pqcrypto.kem.ml_kem_768"
    assert summary["parameters"]["output_dir"] == str(tmp_path)
    assert [call["control_delay_ns"] for call in calls] == [0, 20_000]
    assert all(call["kem"] is fake_kem for call in calls)
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "REPORT.md").exists()
    assert (tmp_path / "real_traces.csv").exists()
    assert (tmp_path / "positive_control_raw_timings.csv").exists()
