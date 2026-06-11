"""Shared macaron-style pastel color palette and matplotlib styling."""

from __future__ import annotations

import matplotlib

# Soft pastel "macaron" palette.
PINK = "#F8B4C4"
MINT = "#A8D8C9"
LAVENDER = "#C9B6E2"
PEACH = "#FFD9A0"
SKY = "#AEDDE6"
BUTTER = "#F6E2B3"
ROSE = "#E8889A"
SAGE = "#B8C9A1"

# Semantic roles used across plots.
VALID_COLOR = MINT
ALTERED_COLOR = PINK
CONTROL_COLOR = LAVENDER
ACCENT_COLOR = ROSE
NEUTRAL_COLOR = "#9C8AA5"

CYCLE = [PINK, MINT, LAVENDER, PEACH, SKY, BUTTER, ROSE, SAGE]


def apply_style() -> None:
    """Apply the macaron pastel theme to matplotlib's rcParams."""
    matplotlib.rcParams.update(
        {
            "axes.prop_cycle": matplotlib.cycler(color=CYCLE),
            "axes.facecolor": "#FFFDF9",
            "figure.facecolor": "#FFFDF9",
            "axes.edgecolor": "#C9B6BE",
            "axes.grid": True,
            "grid.color": "#EFE2E6",
            "grid.linewidth": 0.8,
            "axes.titlecolor": "#6B5B6E",
            "axes.labelcolor": "#6B5B6E",
            "xtick.color": "#8A7A8C",
            "ytick.color": "#8A7A8C",
            "text.color": "#6B5B6E",
            "patch.edgecolor": "white",
            "patch.linewidth": 0.6,
            "legend.frameon": False,
        }
    )
