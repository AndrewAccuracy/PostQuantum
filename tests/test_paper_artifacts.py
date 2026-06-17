import csv
import json

from mlkem_leakage import paper_artifacts


def _row(scenario: str, trace_id: int, group_id: int, label: int, mean_ns: float) -> dict:
    row = {
        "scenario": scenario,
        "invalid_strategy": "single_bit",
        "trace_id": str(trace_id),
        "group_id": str(group_id),
        "label": str(label),
    }
    for feature in paper_artifacts.FEATURES:
        row[feature] = str(mean_ns if feature == "mean_ns" else 1.0)
    return row


def _rows(scenario: str) -> list[dict]:
    return [
        _row(scenario, 0, 0, 0, 1000.0),
        _row(scenario, 1, 0, 1, 1100.0),
        _row(scenario, 2, 1, 0, 1010.0),
        _row(scenario, 3, 1, 1, 1120.0),
    ]


def _write_rows(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_audit_accepts_balanced_finite_trace_rows():
    audit = paper_artifacts._audit(_rows("real"))

    assert audit["rows"] == 4
    assert audit["labels"] == {0: 2, 1: 2}
    assert audit["groups"] == 2
    assert audit["missing_cells"] == 0
    assert audit["nonfinite_numeric_cells"] == 0
    assert audit["duplicate_trace_ids"] == 0
    assert audit["group_label_size_min"] == 1
    assert audit["group_label_size_max"] == 1


def _write_run(root, run_name: str, real_difference_ns: float):
    run_dir = root / run_name / "ml_kem_768" / "single_bit"
    run_dir.mkdir(parents=True)
    model = {"model": "stub", "balanced_accuracy_mean": 0.5}
    summary = {
        "implementation": "pqcrypto.kem.ml_kem_768",
        "invalid_strategy": "single_bit",
        "pipeline_valid": True,
        "scenarios": {
            "real": {"mean_difference_ns": real_difference_ns, "models": [model]},
            "positive_control": {"mean_difference_ns": 20_000.0, "models": [model]},
        },
    }
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    _write_rows(run_dir / "real_traces.csv", _rows("real"))
    _write_rows(run_dir / "positive_control_traces.csv", _rows("positive_control"))


def test_load_runs_and_quality_report_for_completed_runs(tmp_path):
    _write_run(tmp_path, "run_1", 10.0)
    _write_run(tmp_path, "run_2", 12.0)

    runs = paper_artifacts._load_runs(tmp_path)
    audits = {
        run["name"]: {
            scenario: paper_artifacts._audit(run["rows"][scenario])
            for scenario in ("real", "positive_control")
        }
        for run in runs
    }
    report = paper_artifacts._quality_report(runs, audits)

    assert len(runs) == 2
    assert runs[0]["name"] == "run_1/ml_kem_768/single_bit"
    assert "Completed independent runs: `2`" in report
    assert "Data-quality acceptance checks passed: `True`" in report
