"""Deterministic density and colorbar layout for editable heatmaps.

The same plan is consumed by the Matplotlib preview and the Origin renderer.
It deliberately thins only display labels; the source table and editable
Origin matrix retain every row, column, and value in their original order.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

ANNOTATED_MAX_ROWS = 12
ANNOTATED_MAX_COLUMNS = 10
ANNOTATED_MAX_CELLS = 120
DEFAULT_X_LABEL_BUDGET = 12
DEFAULT_Y_LABEL_BUDGET = 16
LONG_X_LABEL_BUDGET = 8
LONG_Y_LABEL_BUDGET = 12
DENSE_X_LABEL_BUDGET = 9


@dataclass(frozen=True)
class HeatmapColorbarGeometry:
    """Detached colorbar geometry expressed as page-width fractions."""

    layer_right_fraction: float
    left_fraction: float
    object_width_fraction: float
    bar_axis_width_fraction: float
    gap_fraction: float
    page_right_fraction: float


@dataclass(frozen=True)
class HeatmapLayoutPlan:
    """Frozen-by-input display decisions for one heatmap matrix."""

    rows: int
    columns: int
    show_cell_labels: bool
    x_label_stride: int
    y_label_stride: int
    x_visible_indices: tuple[int, ...]
    y_visible_indices: tuple[int, ...]
    x_display_labels: tuple[str, ...]
    y_display_labels: tuple[str, ...]
    x_rotation_deg: float
    x_tick_length_pt: float
    y_tick_length_pt: float
    cell_label_size_pt: float
    colorbar_label_size_pt: float


def heatmap_cell_labels_enabled(rows: int, columns: int) -> bool:
    """Return whether a matrix is small enough for per-cell numeric text."""

    row_count = max(0, int(rows))
    column_count = max(0, int(columns))
    return (
        row_count <= ANNOTATED_MAX_ROWS
        and column_count <= ANNOTATED_MAX_COLUMNS
        and row_count * column_count <= ANNOTATED_MAX_CELLS
    )


def _visible_indices(count: int, budget: int) -> tuple[tuple[int, ...], int]:
    if count < 1:
        return (), 1
    if budget < 2 or count <= budget:
        return tuple(range(count)), 1
    stride = max(1, math.ceil((count - 1) / (budget - 1)))
    indices = list(range(0, count, stride))
    if indices[-1] != count - 1:
        if len(indices) > 1 and (count - 1) - indices[-1] < stride:
            indices.pop()
        indices.append(count - 1)
    return tuple(indices), stride


def _display_labels(labels: Sequence[str], indices: tuple[int, ...]) -> tuple[str, ...]:
    visible = set(indices)
    return tuple(str(value) if index in visible else "" for index, value in enumerate(labels))


def resolve_heatmap_layout(
    *,
    x_labels: Sequence[str],
    y_labels: Sequence[str],
    tick_label_size_pt: float,
    major_tick_length_pt: float,
) -> HeatmapLayoutPlan:
    """Resolve label density without changing matrix values or source order."""

    x_text = tuple(str(value) for value in x_labels)
    y_text = tuple(str(value) for value in y_labels)
    max_x_length = max((len(value) for value in x_text), default=0)
    max_y_length = max((len(value) for value in y_text), default=0)
    x_budget = (
        min(LONG_X_LABEL_BUDGET, DENSE_X_LABEL_BUDGET)
        if max_x_length > 10
        else DENSE_X_LABEL_BUDGET
        if len(x_text) >= 24
        else DEFAULT_X_LABEL_BUDGET
    )
    y_budget = LONG_Y_LABEL_BUDGET if max_y_length > 16 else DEFAULT_Y_LABEL_BUDGET
    x_indices, x_stride = _visible_indices(len(x_text), x_budget)
    y_indices, y_stride = _visible_indices(len(y_text), y_budget)
    show_cell_labels = heatmap_cell_labels_enabled(len(y_text), len(x_text))
    return HeatmapLayoutPlan(
        rows=len(y_text),
        columns=len(x_text),
        show_cell_labels=show_cell_labels,
        x_label_stride=x_stride,
        y_label_stride=y_stride,
        x_visible_indices=x_indices,
        y_visible_indices=y_indices,
        x_display_labels=_display_labels(x_text, x_indices),
        y_display_labels=_display_labels(y_text, y_indices),
        x_rotation_deg=(
            55.0 if max_x_length > 18 else 45.0 if max_x_length > 10 or len(x_text) >= 24 else 0.0
        ),
        x_tick_length_pt=float(major_tick_length_pt if x_stride == 1 else 0.0),
        y_tick_length_pt=float(major_tick_length_pt if y_stride == 1 else 0.0),
        cell_label_size_pt=float(round(float(tick_label_size_pt) * 0.76)),
        colorbar_label_size_pt=float(max(15, round(float(tick_label_size_pt) * 0.88))),
    )


def resolve_heatmap_colorbar_geometry(
    layer_left_percent: float,
    layer_width_percent: float,
    *,
    gap_fraction: float = 0.025,
    page_right_fraction: float = 0.995,
    minimum_object_width_fraction: float = 0.07,
    maximum_bar_axis_width_fraction: float = 0.025,
) -> HeatmapColorbarGeometry:
    """Return a detached colorbar region shared by preview and Origin."""

    layer_right_fraction = (float(layer_left_percent) + float(layer_width_percent)) / 100.0
    left_fraction = layer_right_fraction + float(gap_fraction)
    object_width_fraction = float(page_right_fraction) - left_fraction
    if object_width_fraction < float(minimum_object_width_fraction):
        raise ValueError("Heatmap color scale has insufficient right margin; reduce the layer width.")
    bar_axis_width_fraction = min(
        float(maximum_bar_axis_width_fraction),
        object_width_fraction * 0.30,
    )
    return HeatmapColorbarGeometry(
        layer_right_fraction=layer_right_fraction,
        left_fraction=left_fraction,
        object_width_fraction=object_width_fraction,
        bar_axis_width_fraction=bar_axis_width_fraction,
        gap_fraction=float(gap_fraction),
        page_right_fraction=float(page_right_fraction),
    )


__all__ = [
    "ANNOTATED_MAX_CELLS",
    "ANNOTATED_MAX_COLUMNS",
    "ANNOTATED_MAX_ROWS",
    "DEFAULT_X_LABEL_BUDGET",
    "DEFAULT_Y_LABEL_BUDGET",
    "DENSE_X_LABEL_BUDGET",
    "HeatmapColorbarGeometry",
    "HeatmapLayoutPlan",
    "heatmap_cell_labels_enabled",
    "resolve_heatmap_colorbar_geometry",
    "resolve_heatmap_layout",
]
