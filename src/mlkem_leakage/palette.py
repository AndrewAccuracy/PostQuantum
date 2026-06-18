"""Shared publication color palette and matplotlib styling."""

from __future__ import annotations

import matplotlib

# Blue/red/gray palette matching the permutation-test figures.
STEEL_BLUE = "#7FA7C7"
DEEP_BLUE = "#2166AC"
CRIMSON = "#DC143C"
MUTED_RED = "#D6604D"
SLATE = "#7F7F7F"
LIGHT_GRAY = "#E6E6E6"
DARK_TEXT = "#222222"
SOFT_BLUE = "#D7E6F2"
SOFT_RED = "#F4D6D0"

# Backwards-compatible names used by plotting scripts.
PINK = MUTED_RED
MINT = STEEL_BLUE
LAVENDER = SOFT_BLUE
PEACH = SOFT_RED
SKY = "#A6CEE3"
BUTTER = "#BDBDBD"
ROSE = CRIMSON
SAGE = "#8C96C6"

# Semantic roles used across plots.
VALID_COLOR = STEEL_BLUE
ALTERED_COLOR = CRIMSON
CONTROL_COLOR = DEEP_BLUE
ACCENT_COLOR = CRIMSON
NEUTRAL_COLOR = SLATE

CYCLE = [STEEL_BLUE, CRIMSON, SLATE, DEEP_BLUE, MUTED_RED, "#A6CEE3", "#BDBDBD", "#8C96C6"]


def apply_style() -> None:
    """Apply the shared publication theme to matplotlib's rcParams."""
    matplotlib.rcParams.update(
        {
            "axes.prop_cycle": matplotlib.cycler(color=CYCLE),
            "axes.facecolor": "white",
            "figure.facecolor": "white",
            "axes.edgecolor": "#222222",
            "axes.grid": True,
            "grid.color": LIGHT_GRAY,
            "grid.linewidth": 0.8,
            "axes.titlecolor": DARK_TEXT,
            "axes.labelcolor": DARK_TEXT,
            "xtick.color": DARK_TEXT,
            "ytick.color": DARK_TEXT,
            "text.color": DARK_TEXT,
            "patch.edgecolor": "white",
            "patch.linewidth": 0.6,
            "legend.frameon": False,
        }
    )
