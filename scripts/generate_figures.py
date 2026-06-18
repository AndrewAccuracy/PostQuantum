#!/usr/bin/env python3
"""Generate publication-ready figures for the ML-KEM-768 leakage detection paper."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mlkem-leakage-matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "mlkem-leakage-cache"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from scipy.stats import gaussian_kde
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.model_selection import GroupShuffleSplit, permutation_test_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mlkem_leakage.palette import (  # noqa: E402
    ALTERED_COLOR,
    CONTROL_COLOR,
    NEUTRAL_COLOR,
    VALID_COLOR,
    apply_style,
)

RESULTS_DIR = Path("results/latest")
OUTPUT_DIR = Path("docs/figures")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

apply_style()
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.5,
    "figure.constrained_layout.use": True,
})

C_VALID = VALID_COLOR
C_ALTERED = ALTERED_COLOR
C_REAL = VALID_COLOR
C_CTRL = CONTROL_COLOR
C_NEUTRAL = NEUTRAL_COLOR

FEATURES = [
    "mean_ns", "median_ns", "std_ns", "min_ns", "max_ns",
    "p10_ns", "p90_ns", "iqr_ns", "mad_ns",
    "trimmed_mean_ns", "skewness", "kurtosis", "cv",
]
FEATURE_LABELS = [
    "Mean", "Median", "Std Dev", "Min", "Max",
    "P10", "P90", "IQR", "MAD",
    "Trimmed Mean", "Skewness", "Kurtosis", "CV",
]

MODEL_ORDER = ["logistic_regression", "linear_svm", "random_forest", "hist_gradient_boosting"]
MODEL_LABELS = ["Logistic\nRegression", "Linear SVM", "Random\nForest", "Hist Gradient\nBoosting"]
N_JOBS = int(os.environ.get("MLKEM_N_JOBS", "1"))
N_PERMUTATIONS = int(os.environ.get("MLKEM_PERMUTATIONS", "300"))
SKIP_PERMUTATION = os.environ.get("MLKEM_SKIP_PERMUTATION") == "1"


def load_data():
    real_df = pd.read_csv(RESULTS_DIR / "real_traces.csv")
    ctrl_df = pd.read_csv(RESULTS_DIR / "positive_control_traces.csv")
    summary = json.loads((RESULTS_DIR / "summary.json").read_text())
    return real_df, ctrl_df, summary


def fig_distributions(real_df: pd.DataFrame, ctrl_df: pd.DataFrame):
    """Figure 1: Timing distribution comparison (real + positive control)."""
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.9))

    for ax, df, title in [
        (axes[0], real_df,  "Real scenario"),
        (axes[1], ctrl_df, "Positive control"),
    ]:
        for label, color, name in [(0, C_VALID, "Valid"), (1, C_ALTERED, "Altered")]:
            vals = df.loc[df["label"] == label, "mean_ns"].values / 1e3
            kde = gaussian_kde(vals, bw_method=0.3)
            xs = np.linspace(vals.min() - 1, vals.max() + 1, 300)
            ax.fill_between(xs, kde(xs), alpha=0.25, color=color)
            ax.plot(xs, kde(xs), color=color, linewidth=1.4, label=name)
        ax.set_xlabel("Mean decapsulation time (µs)")
        ax.set_ylabel("Density")
        ax.set_title(title)

    axes[0].legend(framealpha=0.8)
    plt.savefig(OUTPUT_DIR / "fig_distribution.pdf", bbox_inches="tight")
    plt.savefig(OUTPUT_DIR / "fig_distribution.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("fig_distribution done")


def fig_model_accuracy(summary: dict):
    """Figure 2: Grouped bar chart of balanced accuracy for all 4 models."""
    scenarios = {
        "real": ("Real scenario", C_REAL),
        "positive_control": ("Positive control", C_CTRL),
    }
    x = np.arange(len(MODEL_ORDER))
    width = 0.36
    fig, ax = plt.subplots(figsize=(6.5, 3.2))

    for i, (key, (label, color)) in enumerate(scenarios.items()):
        model_results = {m["model"]: m for m in summary["scenarios"][key]["models"]}
        means = [model_results[m]["balanced_accuracy_mean"] for m in MODEL_ORDER]
        stds  = [model_results[m]["balanced_accuracy_std"]  for m in MODEL_ORDER]
        bars = ax.bar(x + (i - 0.5) * width, means, width,
                      yerr=stds, capsize=3, color=color, alpha=0.8,
                      label=label, error_kw={"linewidth": 0.8})

    ax.axhline(0.5, color=C_NEUTRAL, linestyle="--", linewidth=1.0, label="Random baseline (0.5)")
    ax.set_xticks(x)
    ax.set_xticklabels(MODEL_LABELS, ha="center")
    ax.set_ylabel("Balanced accuracy")
    ax.set_ylim(0, 1.09)
    ax.legend(framealpha=0.85, loc="upper left")
    ax.set_title("Classifier balanced accuracy: real scenario vs. positive control")

    # Annotate permutation p-values on real scenario bars
    model_results = {m["model"]: m for m in summary["scenarios"]["real"]["models"]}
    for i, name in enumerate(MODEL_ORDER):
        pval = model_results[name]["permutation_pvalue"]
        mean = model_results[name]["balanced_accuracy_mean"]
        std  = model_results[name]["balanced_accuracy_std"]
        ax.text(x[i] - 0.5 * width, mean + std + 0.03,
                f"p={pval:.2f}", ha="center", va="bottom", fontsize=7, color=C_REAL)

    plt.savefig(OUTPUT_DIR / "fig_models.pdf", bbox_inches="tight")
    plt.savefig(OUTPUT_DIR / "fig_models.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("fig_models done")


def fig_permutation_test(real_df: pd.DataFrame):
    """Figure 3: Permutation test null distributions for 4 models (real scenario)."""
    X = real_df[FEATURES].values
    y = real_df["label"].values
    groups = real_df["group_id"].values

    cv = GroupShuffleSplit(n_splits=5, test_size=0.3, random_state=42)

    models = {
        "Logistic\nRegression": __import__("sklearn.linear_model", fromlist=["LogisticRegression"]).LogisticRegression(
            solver="liblinear", max_iter=1000, C=1.0, random_state=42),
        "Linear SVM": __import__("sklearn.svm", fromlist=["SVC"]).SVC(
            kernel="linear", probability=True, C=0.1, random_state=42),
        "Random\nForest": RandomForestClassifier(
            n_estimators=200, min_samples_leaf=3, random_state=42, n_jobs=N_JOBS),
        "Hist Gradient\nBoosting": HistGradientBoostingClassifier(
            max_iter=200, random_state=42),
    }

    # Preprocessing pipeline for LR and SVM
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import RobustScaler
    from sklearn.preprocessing import FunctionTransformer

    def clip50(v): return np.clip(v, -50, 50)

    models["Logistic\nRegression"] = make_pipeline(
        RobustScaler(), FunctionTransformer(clip50),
        __import__("sklearn.linear_model", fromlist=["LogisticRegression"]).LogisticRegression(
            solver="liblinear", max_iter=1000, C=1.0, random_state=42))
    models["Linear SVM"] = make_pipeline(
        RobustScaler(), FunctionTransformer(clip50),
        __import__("sklearn.svm", fromlist=["SVC"]).SVC(
            kernel="linear", probability=True, C=0.1, random_state=42))

    fig, axes = plt.subplots(2, 2, figsize=(7.0, 4.8))
    axes = axes.flatten()

    for ax, (name, model) in zip(axes, models.items()):
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            obs_score, perm_scores, pvalue = permutation_test_score(
                model, X, y, groups=groups, cv=cv,
                n_permutations=N_PERMUTATIONS, scoring="balanced_accuracy",
                n_jobs=N_JOBS, random_state=42,
            )
        ax.hist(perm_scores, bins=25, color=C_VALID, alpha=0.7, edgecolor="white",
                linewidth=0.4, label="Null distribution")
        ax.axvline(obs_score, color=C_ALTERED, linewidth=1.8, label=f"Observed = {obs_score:.3f}")
        ax.axvline(0.5, color=C_NEUTRAL, linewidth=1.0, linestyle="--", label="Random (0.5)")
        ax.set_title(f"{name}  (p = {pvalue:.3f})", fontsize=9)
        ax.set_xlabel("Balanced accuracy")
        ax.set_ylabel("Count")
        ax.legend(framealpha=0.8, fontsize=7)

    fig.suptitle("Permutation test null distributions — real scenario", fontsize=10)
    plt.savefig(OUTPUT_DIR / "fig_permutation.pdf", bbox_inches="tight")
    plt.savefig(OUTPUT_DIR / "fig_permutation.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("fig_permutation done")


def fig_feature_importance(real_df: pd.DataFrame):
    """Figure 4: Random Forest feature importance with error bars across CV folds."""
    X = real_df[FEATURES].values
    y = real_df["label"].values
    groups = real_df["group_id"].values

    cv = GroupShuffleSplit(n_splits=8, test_size=0.3, random_state=42)
    importances_per_fold = []
    for train, _ in cv.split(X, y, groups):
        rf = RandomForestClassifier(n_estimators=300, min_samples_leaf=3,
                                    random_state=42, n_jobs=N_JOBS)
        rf.fit(X[train], y[train])
        importances_per_fold.append(rf.feature_importances_)

    imp = np.array(importances_per_fold)
    mean_imp = imp.mean(axis=0)
    std_imp  = imp.std(axis=0)

    order = np.argsort(mean_imp)[::-1]
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    colors = [C_REAL if i < 5 else C_NEUTRAL for i in range(len(FEATURES))]
    bars = ax.barh(
        [FEATURE_LABELS[i] for i in order[::-1]],
        mean_imp[order[::-1]],
        xerr=std_imp[order[::-1]],
        color=[colors[i] for i in order[::-1]],
        alpha=0.8, capsize=3, error_kw={"linewidth": 0.8},
    )
    ax.set_xlabel("Mean decrease in impurity (importance)")
    ax.set_title("Random Forest feature importance — real scenario\n(mean ± std over 8 CV folds)")
    plt.savefig(OUTPUT_DIR / "fig_features.pdf", bbox_inches="tight")
    plt.savefig(OUTPUT_DIR / "fig_features.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("fig_features done")


def fig_trace_order(real_df: pd.DataFrame):
    """Figure 5: Collection-order diagnostic using binned label differences."""
    def trimmed_mean(values: np.ndarray, proportion: float = 0.1) -> float:
        ordered = np.sort(values)
        trim = int(len(ordered) * proportion)
        if trim == 0 or len(ordered) <= 2 * trim:
            return float(np.mean(ordered))
        return float(np.mean(ordered[trim:-trim]))

    fig, ax = plt.subplots(figsize=(6.5, 2.9))
    df = real_df.copy()
    n_bins = 20
    bins = np.linspace(df["trace_id"].min(), df["trace_id"].max() + 1, n_bins + 1)
    df["order_bin"] = pd.cut(df["trace_id"], bins=bins, include_lowest=True, labels=False)

    xs, deltas, ci95 = [], [], []
    for bin_index in range(n_bins):
        part = df[df["order_bin"] == bin_index]
        valid = part.loc[part["label"] == 0, "mean_ns"].to_numpy()
        altered = part.loc[part["label"] == 1, "mean_ns"].to_numpy()
        if len(valid) < 2 or len(altered) < 2:
            continue
        valid_trimmed = np.sort(valid)[max(1, int(len(valid) * 0.1)) : -max(1, int(len(valid) * 0.1))]
        altered_trimmed = np.sort(altered)[max(1, int(len(altered) * 0.1)) : -max(1, int(len(altered) * 0.1))]
        xs.append((bins[bin_index] + bins[bin_index + 1]) / 2)
        deltas.append((trimmed_mean(altered) - trimmed_mean(valid)) / 1e3)
        se = np.sqrt(
            valid_trimmed.var(ddof=1) / len(valid_trimmed)
            + altered_trimmed.var(ddof=1) / len(altered_trimmed)
        ) / 1e3
        ci95.append(1.96 * se)

    ax.axhline(0, color=C_NEUTRAL, linewidth=1.1, linestyle="--", label="No label difference")
    ax.errorbar(
        xs,
        deltas,
        yerr=ci95,
        fmt="o-",
        color=C_ALTERED,
        ecolor=C_VALID,
        elinewidth=1.0,
        capsize=2.8,
        markersize=3.8,
        linewidth=1.4,
        label="Altered - valid trimmed mean",
    )
    ax.set_xlabel("Randomized collection order (20 adjacent bins)")
    ax.set_ylabel("Altered - valid time (µs)")
    ax.set_title("Collection-order diagnostic — binned trimmed-mean difference")
    ax.legend(framealpha=0.85, loc="upper right")
    plt.savefig(OUTPUT_DIR / "fig_trace_order.pdf", bbox_inches="tight")
    plt.savefig(OUTPUT_DIR / "fig_trace_order.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("fig_trace_order done")


if __name__ == "__main__":
    real_df, ctrl_df, summary = load_data()
    print("Loaded data:", len(real_df), "real traces,", len(ctrl_df), "control traces")

    fig_distributions(real_df, ctrl_df)
    fig_model_accuracy(summary)
    fig_trace_order(real_df)
    fig_feature_importance(real_df)
    if SKIP_PERMUTATION:
        print("Skipping permutation test figure (MLKEM_SKIP_PERMUTATION=1)")
    else:
        print("Running permutation test figure (set MLKEM_SKIP_PERMUTATION=1 to skip)...")
        fig_permutation_test(real_df)
    print("\nAll figures saved to", OUTPUT_DIR)
