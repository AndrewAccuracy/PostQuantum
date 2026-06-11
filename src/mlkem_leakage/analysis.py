"""Statistical and machine-learning analysis for collected timing traces."""

from __future__ import annotations

import json
import os
import tempfile
import warnings
from dataclasses import asdict, dataclass
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

from .palette import (
    ACCENT_COLOR,
    ALTERED_COLOR,
    LAVENDER,
    NEUTRAL_COLOR,
    VALID_COLOR,
    apply_style,
)

apply_style()
from scipy.stats import ks_2samp, mannwhitneyu, ttest_ind
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit, permutation_test_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, RobustScaler
from sklearn.svm import SVC

from .collector import Trace

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

N_JOBS = int(os.environ.get("MLKEM_N_JOBS", "1"))
PERMUTATIONS = int(os.environ.get("MLKEM_PERMUTATIONS", "200"))


@dataclass(frozen=True)
class ModelResult:
    model: str
    balanced_accuracy_mean: float
    balanced_accuracy_std: float
    roc_auc_mean: float
    roc_auc_std: float
    permutation_pvalue: float


def _clip_features(values: np.ndarray) -> np.ndarray:
    return np.clip(values, -50, 50)


def _effect_size(a: np.ndarray, b: np.ndarray) -> float:
    pooled = np.sqrt((np.var(a, ddof=1) + np.var(b, ddof=1)) / 2)
    return float((np.mean(b) - np.mean(a)) / pooled) if pooled else 0.0


def _make_models(seed: int) -> Dict[str, object]:
    scaled_pipeline = lambda clf: make_pipeline(  # noqa: E731
        RobustScaler(),
        FunctionTransformer(_clip_features),
        clf,
    )
    return {
        "logistic_regression": scaled_pipeline(
            LogisticRegression(solver="liblinear", max_iter=1000, random_state=seed, C=1.0)
        ),
        "linear_svm": scaled_pipeline(
            SVC(kernel="linear", probability=True, random_state=seed, C=0.1)
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300, min_samples_leaf=3, random_state=seed, n_jobs=N_JOBS
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            max_iter=200, random_state=seed
        ),
    }


def _feature_importances(
    x: np.ndarray, y: np.ndarray, groups: np.ndarray, seed: int
) -> list:
    rf = RandomForestClassifier(
        n_estimators=300, min_samples_leaf=3, random_state=seed, n_jobs=N_JOBS
    )
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed)
    train, _ = next(splitter.split(x, y, groups))
    rf.fit(x[train], y[train])
    return [
        {"feature": f, "importance": float(imp)}
        for f, imp in sorted(
            zip(FEATURES, rf.feature_importances_), key=lambda t: -t[1]
        )
    ]


def _evaluate_models(
    x: np.ndarray, y: np.ndarray, groups: np.ndarray, seed: int
) -> List[ModelResult]:
    cv = GroupShuffleSplit(n_splits=8, test_size=0.3, random_state=seed)
    perm_cv = GroupShuffleSplit(n_splits=5, test_size=0.3, random_state=seed)
    splits = list(cv.split(x, y, groups))
    results = []
    for name, model in _make_models(seed).items():
        accuracies, aucs = [], []
        for train, test in splits:
            model.fit(x[train], y[train])
            predictions = model.predict(x[test])
            probabilities = model.predict_proba(x[test])[:, 1]
            accuracies.append(balanced_accuracy_score(y[test], predictions))
            aucs.append(roc_auc_score(y[test], probabilities))
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            _, _, perm_pvalue = permutation_test_score(
                model,
                x,
                y,
                groups=groups,
                cv=perm_cv,
                n_permutations=PERMUTATIONS,
                scoring="balanced_accuracy",
                n_jobs=N_JOBS,
                random_state=seed,
            )
        results.append(
            ModelResult(
                model=name,
                balanced_accuracy_mean=float(np.mean(accuracies)),
                balanced_accuracy_std=float(np.std(accuracies)),
                roc_auc_mean=float(np.mean(aucs)),
                roc_auc_std=float(np.std(aucs)),
                permutation_pvalue=float(perm_pvalue),
            )
        )
    return results


def analyze(traces: Iterable[Trace], seed: int) -> Dict[str, object]:
    trace_list = list(traces)
    x = np.asarray([[getattr(trace, name) for name in FEATURES] for trace in trace_list])
    y = np.asarray([trace.label for trace in trace_list])
    groups = np.asarray([trace.group_id for trace in trace_list])
    valid = x[y == 0, 0]
    altered = x[y == 1, 0]
    welch = ttest_ind(valid, altered, equal_var=False)
    mw = mannwhitneyu(valid, altered, alternative="two-sided")
    ks = ks_2samp(valid, altered)
    models = _evaluate_models(x, y, groups, seed)
    best_accuracy = max(result.balanced_accuracy_mean for result in models)
    effect_size = _effect_size(valid, altered)
    detected = bool(best_accuracy >= 0.65 and welch.pvalue < 0.01 and abs(effect_size) >= 0.2)
    return {
        "samples": len(trace_list),
        "features": FEATURES,
        "valid_mean_ns": float(np.mean(valid)),
        "altered_mean_ns": float(np.mean(altered)),
        "mean_difference_ns": float(np.mean(altered) - np.mean(valid)),
        "welch_t_statistic": float(welch.statistic),
        "welch_p_value": float(welch.pvalue),
        "mann_whitney_u_statistic": float(mw.statistic),
        "mann_whitney_p_value": float(mw.pvalue),
        "ks_statistic": float(ks.statistic),
        "ks_pvalue": float(ks.pvalue),
        "cohens_d": effect_size,
        "feature_importances": _feature_importances(x, y, groups, seed),
        "models": [asdict(result) for result in models],
        "leakage_detected": detected,
    }


def write_analysis(report: Dict[str, object], output_dir: Path, scenario: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{scenario}_analysis.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )


def write_plot(traces: Iterable[Trace], output_dir: Path, scenario: str) -> None:
    trace_list = list(traces)
    valid = [trace.mean_ns / 1000 for trace in trace_list if trace.label == 0]
    altered = [trace.mean_ns / 1000 for trace in trace_list if trace.label == 1]
    plt.figure(figsize=(8, 4.5))
    plt.hist(valid, bins=30, alpha=0.85, label="valid ciphertext", color=VALID_COLOR)
    plt.hist(altered, bins=30, alpha=0.85, label="altered ciphertext", color=ALTERED_COLOR)
    plt.xlabel("Mean decapsulation time per trace (microseconds)")
    plt.ylabel("Count")
    plt.title(f"ML-KEM timing distribution: {scenario}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / f"{scenario}_timing_histogram.png", dpi=160)
    plt.close()


def write_feature_importance_plot(
    report: Dict[str, object], output_dir: Path, scenario: str
) -> None:
    importances = report.get("feature_importances", [])
    if not importances:
        return
    features = [d["feature"] for d in importances]
    values = [d["importance"] for d in importances]
    plt.figure(figsize=(7, 5))
    plt.barh(features[::-1], values[::-1], color=LAVENDER)
    plt.xlabel("Mean decrease in impurity (Random Forest)")
    plt.title(f"Feature importance: {scenario}")
    plt.tight_layout()
    plt.savefig(output_dir / f"{scenario}_feature_importance.png", dpi=160)
    plt.close()


def write_delay_sweep_plot(sweep_results: list, output_dir: Path) -> None:
    delays = [r["delay_ns"] for r in sweep_results]
    accuracies = [r["best_balanced_accuracy"] for r in sweep_results]
    plt.figure(figsize=(7, 4.2))
    plt.plot(delays, accuracies, marker="o", color=ACCENT_COLOR, linewidth=2)
    plt.xscale("log")
    plt.axhline(0.9, color=ACCENT_COLOR, linestyle="--", linewidth=1, alpha=0.6, label="Detection threshold (0.90)")
    plt.axhline(0.5, color=NEUTRAL_COLOR, linestyle="--", linewidth=1, alpha=0.6, label="Random baseline (0.50)")
    plt.xlabel("Artificial delay (ns, log scale)")
    plt.ylabel("Best balanced accuracy")
    plt.title("Positive-control detection sensitivity: delay sweep")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "delay_sweep_plot.png", dpi=160)
    plt.close()
