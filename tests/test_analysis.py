from mlkem_leakage import analysis
from mlkem_leakage.analysis import ModelResult
from mlkem_leakage.collector import Trace


def _trace(label: int, group_id: int, mean_ns: float) -> Trace:
    return Trace(
        scenario="test",
        invalid_strategy="single_bit",
        trace_id=label * 100 + group_id,
        group_id=group_id,
        label=label,
        mean_ns=mean_ns,
        median_ns=mean_ns,
        std_ns=10.0,
        min_ns=mean_ns - 10.0,
        max_ns=mean_ns + 10.0,
        p10_ns=mean_ns - 5.0,
        p90_ns=mean_ns + 5.0,
        iqr_ns=10.0,
        mad_ns=5.0,
        trimmed_mean_ns=mean_ns,
        skewness=0.0,
        kurtosis=0.0,
        cv=0.01,
    )


def _separated_traces() -> list[Trace]:
    traces = []
    for group_id in range(12):
        traces.append(_trace(0, group_id, 1000.0 + group_id * 10.0))
        traces.append(_trace(1, group_id, 1500.0 + group_id * 10.0))
    return traces


def test_analyze_requires_statistics_effect_size_and_model_signal(monkeypatch):
    monkeypatch.setattr(
        analysis,
        "_feature_importances",
        lambda x, y, groups, seed: [{"feature": "mean_ns", "importance": 1.0}],
    )
    monkeypatch.setattr(
        analysis,
        "_evaluate_models",
        lambda x, y, groups, seed: [
            ModelResult(
                model="stub",
                balanced_accuracy_mean=0.7,
                balanced_accuracy_std=0.0,
                roc_auc_mean=0.7,
                roc_auc_std=0.0,
                permutation_pvalue=0.01,
            )
        ],
    )

    report = analysis.analyze(_separated_traces(), seed=7)

    assert report["leakage_detected"] is True
    assert report["mean_difference_ns"] == 500.0
    assert report["welch_p_value"] < 0.01
    assert abs(report["cohens_d"]) >= 0.2


def test_analyze_does_not_report_leakage_on_model_score_alone(monkeypatch):
    monkeypatch.setattr(
        analysis,
        "_feature_importances",
        lambda x, y, groups, seed: [{"feature": "mean_ns", "importance": 1.0}],
    )
    monkeypatch.setattr(
        analysis,
        "_evaluate_models",
        lambda x, y, groups, seed: [
            ModelResult(
                model="stub",
                balanced_accuracy_mean=0.95,
                balanced_accuracy_std=0.0,
                roc_auc_mean=0.95,
                roc_auc_std=0.0,
                permutation_pvalue=0.01,
            )
        ],
    )
    traces = []
    for group_id in range(12):
        traces.append(_trace(0, group_id, 1000.0 + group_id))
        traces.append(_trace(1, group_id, 1000.2 + group_id))

    report = analysis.analyze(traces, seed=7)

    assert report["leakage_detected"] is False
    assert abs(report["cohens_d"]) < 0.2
