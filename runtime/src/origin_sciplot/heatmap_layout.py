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
    y_label_gap_cm: float = 0.20


@dataclass(frozen=True)
class HeatmapRowLabelAnchor:
    """A source row's right-aligned label position in page percentages."""

    source_index: int
    text: str
    right_percent: float
    center_y_percent: float


def _finite_geometry_value(value: float, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Heatmap row label {name} must be finite.") from exc
    if not math.isfinite(number):
        raise ValueError(f"Heatmap row label {name} must be finite.")
    return number


def resolve_heatmap_row_label_anchors(
    layout: HeatmapLayoutPlan,
    *,
    page_width_cm: float,
    layer_left_percent: float,
    layer_top_percent: float,
    layer_height_percent: float,
) -> tuple[HeatmapRowLabelAnchor, ...]:
    """Place visible labels beside their original rows, top to bottom."""

    page_width = _finite_geometry_value(page_width_cm, "page width")
    layer_left = _finite_geometry_value(layer_left_percent, "layer left")
    layer_top = _finite_geometry_value(layer_top_percent, "layer top")
    layer_height = _finite_geometry_value(layer_height_percent, "layer height")
    gap_cm = _finite_geometry_value(layout.y_label_gap_cm, "planned gap")
    if page_width <= 0 or layer_height <= 0 or gap_cm <= 0:
        raise ValueError("Heatmap row label page width, layer height, and planned gap must be positive.")
    if not 0 < layer_left < 100 or layer_top < 0 or layer_top + layer_height > 100:
        raise ValueError("Heatmap row label layer geometry must be within the page.")
    right = layer_left - gap_cm / page_width * 100.0
    if right <= 0:
        raise ValueError("Heatmap row labels have insufficient left page margin for their planned gap.")

    if not isinstance(layout.rows, int) or isinstance(layout.rows, bool) or layout.rows <= 0:
        raise ValueError("Heatmap row label source row count must be a positive integer.")
    if len(layout.y_display_labels) != layout.rows or not layout.y_visible_indices:
        raise ValueError("Heatmap row label indices and display text must match the source rows.")
    previous_index = -1
    for index in layout.y_visible_indices:
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or not previous_index < index < layout.rows
        ):
            raise ValueError("Heatmap row label source indices must be unique, ordered, and in range.")
        previous_index = index
    visible = set(layout.y_visible_indices)
    for index, text in enumerate(layout.y_display_labels):
        if not isinstance(text, str) or (not text.strip() if index in visible else text != ""):
            raise ValueError("Heatmap row label visible indices and display text are inconsistent.")

    return tuple(
        HeatmapRowLabelAnchor(
            source_index=index,
            text=layout.y_display_labels[index],
            right_percent=right,
            center_y_percent=layer_top + (index + 0.5) / layout.rows * layer_height,
        )
        for index in layout.y_visible_indices
    )


def verify_heatmap_row_label_geometry(
    anchor: HeatmapRowLabelAnchor,
    *,
    left_percent: float,
    top_percent: float,
    width_percent: float,
    height_percent: float,
    page_width_cm: float,
    layer_left_percent: float,
    y_label_gap_cm: float,
) -> dict[str, float]:
    """Verify a measured label bounding box against its page-space contract."""

    left = _finite_geometry_value(left_percent, "left")
    top = _finite_geometry_value(top_percent, "top")
    width = _finite_geometry_value(width_percent, "width")
    height = _finite_geometry_value(height_percent, "height")
    page_width = _finite_geometry_value(page_width_cm, "page width")
    layer_left = _finite_geometry_value(layer_left_percent, "layer left")
    gap_cm = _finite_geometry_value(y_label_gap_cm, "planned gap")
    planned_right = _finite_geometry_value(anchor.right_percent, "planned right")
    planned_center = _finite_geometry_value(anchor.center_y_percent, "planned center")
    if width <= 0 or height <= 0 or page_width <= 0 or gap_cm <= 0:
        raise ValueError("Heatmap row label bounding box, page width, and planned gap must be positive.")
    right = left + width
    center = top + height / 2.0
    if left < 0 or top < 0 or right > 100 or top + height > 100:
        raise ValueError("Heatmap row label bounding box must be within the page.")
    if not 0 < layer_left < 100 or not 0 < planned_right < 100 or not 0 <= planned_center <= 100:
        raise ValueError("Heatmap row label planned geometry must be within the page.")
    if right > layer_left:
        raise ValueError("Heatmap row label bounding box intrudes into the heatmap frame.")
    if abs(right - planned_right) > 0.03 + 1e-9:
        raise ValueError("Heatmap row label right edge drift exceeds 0.03 percentage points.")
    if abs(center - planned_center) > 0.03 + 1e-9:
        raise ValueError("Heatmap row label center drift exceeds 0.03 percentage points.")
    actual_gap_cm = (layer_left - right) / 100.0 * page_width
    if actual_gap_cm < gap_cm - 0.01 - 1e-9:
        raise ValueError("Heatmap row label physical gap is smaller than its planned minimum.")
    return {"gap_cm": actual_gap_cm, "right_percent": right, "center_y_percent": center}


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
    "HeatmapRowLabelAnchor",
    "heatmap_cell_labels_enabled",
    "resolve_heatmap_colorbar_geometry",
    "resolve_heatmap_layout",
    "resolve_heatmap_row_label_anchors",
    "verify_heatmap_row_label_geometry",
]
