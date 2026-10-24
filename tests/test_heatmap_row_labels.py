from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot import heatmap_layout  # noqa: E402


def _layout(rows: int = 4, *, long_chinese: bool = False):
    prefix = "不同处理条件下的中文材料样本名称" if long_chinese else "Sample "
    return heatmap_layout.resolve_heatmap_layout(
        x_labels=["Feature A", "Feature B"],
        y_labels=[f"{prefix}{index + 1:02d}" for index in range(rows)],
        tick_label_size_pt=17.0,
        major_tick_length_pt=5.5,
    )


@pytest.mark.parametrize(
    ("rows", "long_chinese", "expected_indices", "first_y", "last_y"),
    [
        (30, False, (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 29), 11.3333333333, 88.6666666667),
        (40, False, (0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39), 11.0, 89.0),
        (40, True, (0, 4, 8, 12, 16, 20, 24, 28, 32, 39), 11.0, 89.0),
    ],
)
def test_row_anchors_preserve_visible_source_rows_and_endpoint_centers(
    rows, long_chinese, expected_indices, first_y, last_y
):
    layout = _layout(rows, long_chinese=long_chinese)

    anchors = heatmap_layout.resolve_heatmap_row_label_anchors(
        layout,
        page_width_cm=20.0,
        layer_left_percent=20.0,
        layer_top_percent=10.0,
        layer_height_percent=80.0,
    )

    assert tuple(anchor.source_index for anchor in anchors) == expected_indices
    assert anchors[0].text == ("不同处理条件下的中文材料样本名称01" if long_chinese else "Sample 01")
    assert anchors[-1].text == ("不同处理条件下的中文材料样本名称40" if long_chinese else f"Sample {rows}")
    assert anchors[0].center_y_percent == pytest.approx(first_y)
    assert anchors[-1].center_y_percent == pytest.approx(last_y)
    assert all(anchor.right_percent == pytest.approx(19.0) for anchor in anchors)


def test_sparse_row_center_uses_source_index_not_visible_label_ordinal():
    anchors = heatmap_layout.resolve_heatmap_row_label_anchors(
        _layout(40),
        page_width_cm=20.0,
        layer_left_percent=20.0,
        layer_top_percent=10.0,
        layer_height_percent=80.0,
    )

    assert anchors[1].source_index == 3
    assert anchors[1].text == "Sample 04"
    assert anchors[1].center_y_percent == pytest.approx(17.0)


def test_row_anchor_converts_requested_gap_from_centimeters_to_page_percent():
    anchors = heatmap_layout.resolve_heatmap_row_label_anchors(
        replace(_layout(), y_label_gap_cm=0.4),
        page_width_cm=20.0,
        layer_left_percent=20.0,
        layer_top_percent=10.0,
        layer_height_percent=80.0,
    )

    assert anchors[0].right_percent == pytest.approx(18.0)


@pytest.mark.parametrize(
    "changes",
    [
        {"rows": 0},
        {"rows": 4.5},
        {"rows": True},
        {"y_display_labels": ("Sample 01",)},
        {"y_visible_indices": (0, 1, 1, 3)},
        {"y_visible_indices": (0, 2, 1, 3)},
        {"y_visible_indices": (0, 1, 2, 4)},
        {"y_visible_indices": (-1, 1, 2, 3)},
        {"y_visible_indices": (0, 1.0, 2, 3)},
        {"y_visible_indices": (0, True, 2, 3)},
        {"y_visible_indices": ()},
        {"y_display_labels": ("Sample 01", "", "Sample 03", "Sample 04")},
        {"y_display_labels": ("Sample 01", None, "Sample 03", "Sample 04")},
        {"y_visible_indices": (0, 3)},
    ],
)
def test_row_anchor_rejects_inconsistent_source_indices_or_display_text(changes):
    with pytest.raises(ValueError):
        heatmap_layout.resolve_heatmap_row_label_anchors(
            replace(_layout(), **changes),
            page_width_cm=20.0,
            layer_left_percent=20.0,
            layer_top_percent=10.0,
            layer_height_percent=80.0,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"page_width_cm": 0.0},
        {"page_width_cm": float("nan")},
        {"page_width_cm": float("inf")},
        {"layer_left_percent": float("nan")},
        {"layer_left_percent": 101.0},
        {"layer_left_percent": 0.5},
        {"layer_top_percent": -1.0},
        {"layer_top_percent": float("nan")},
        {"layer_height_percent": 0.0},
        {"layer_height_percent": -1.0},
        {"layer_height_percent": float("inf")},
        {"layer_top_percent": 21.0, "layer_height_percent": 80.0},
    ],
)
def test_row_anchor_rejects_invalid_or_off_page_layer_geometry(changes):
    geometry = dict(
        page_width_cm=20.0,
        layer_left_percent=20.0,
        layer_top_percent=10.0,
        layer_height_percent=80.0,
    )
    geometry.update(changes)

    with pytest.raises(ValueError):
        heatmap_layout.resolve_heatmap_row_label_anchors(_layout(), **geometry)


@pytest.mark.parametrize("gap", [0.0, -0.2, float("nan"), float("inf")])
def test_row_anchor_rejects_nonpositive_or_nonfinite_planned_gap(gap):
    with pytest.raises(ValueError):
        heatmap_layout.resolve_heatmap_row_label_anchors(
            replace(_layout(), y_label_gap_cm=gap),
            page_width_cm=20.0,
            layer_left_percent=20.0,
            layer_top_percent=10.0,
            layer_height_percent=80.0,
        )


@pytest.mark.parametrize(("left", "width"), [(16.0, 3.0), (8.0, 11.0), (1.0, 18.0)])
def test_row_label_width_changes_preserve_right_alignment_and_physical_gap(left, width):
    anchor = heatmap_layout.HeatmapRowLabelAnchor(0, "Material 样品", 19.0, 25.0)

    geometry = heatmap_layout.verify_heatmap_row_label_geometry(
        anchor,
        left_percent=left,
        top_percent=24.0,
        width_percent=width,
        height_percent=2.0,
        page_width_cm=20.0,
        layer_left_percent=20.0,
        y_label_gap_cm=0.2,
    )

    assert geometry["gap_cm"] == pytest.approx(0.2)
    assert geometry["right_percent"] == pytest.approx(19.0)
    assert geometry["center_y_percent"] == pytest.approx(25.0)


@pytest.mark.parametrize(
    "changes",
    [
        {"left_percent": float("nan")},
        {"top_percent": float("nan")},
        {"width_percent": float("nan")},
        {"height_percent": float("inf")},
        {"page_width_cm": float("nan")},
        {"page_width_cm": 0.0},
        {"layer_left_percent": float("nan")},
        {"layer_left_percent": 101.0},
        {"y_label_gap_cm": float("nan")},
        {"y_label_gap_cm": 0.0},
        {"width_percent": 0.0},
        {"height_percent": 0.0},
        {"left_percent": -1.0},
        {"top_percent": -1.0},
        {"left_percent": 96.0},
        {"top_percent": 99.0},
        {"left_percent": 9.04},
        {"top_percent": 24.04},
        {"left_percent": 19.5, "width_percent": 1.0},
    ],
)
def test_row_label_geometry_rejects_invalid_bbox_drift_or_frame_intrusion(changes):
    geometry = dict(
        left_percent=9.0,
        top_percent=24.0,
        width_percent=10.0,
        height_percent=2.0,
        page_width_cm=20.0,
        layer_left_percent=20.0,
        y_label_gap_cm=0.2,
    )
    geometry.update(changes)
    anchor = heatmap_layout.HeatmapRowLabelAnchor(0, "Sample 01", 19.0, 25.0)

    with pytest.raises(ValueError):
        heatmap_layout.verify_heatmap_row_label_geometry(anchor, **geometry)


def test_row_label_geometry_rejects_insufficient_physical_gap_within_anchor_tolerance():
    anchor = heatmap_layout.HeatmapRowLabelAnchor(0, "Sample 01", 19.8, 25.0)

    with pytest.raises(ValueError, match="gap"):
        heatmap_layout.verify_heatmap_row_label_geometry(
            anchor,
            left_percent=9.82,
            top_percent=24.0,
            width_percent=10.0,
            height_percent=2.0,
            page_width_cm=100.0,
            layer_left_percent=20.0,
            y_label_gap_cm=0.2,
        )


def test_row_label_geometry_never_uses_gap_tolerance_to_allow_frame_intrusion():
    anchor = heatmap_layout.HeatmapRowLabelAnchor(0, "Sample 01", 20.01, 25.0)

    with pytest.raises(ValueError, match="frame"):
        heatmap_layout.verify_heatmap_row_label_geometry(
            anchor,
            left_percent=10.01,
            top_percent=24.0,
            width_percent=10.0,
            height_percent=2.0,
            page_width_cm=20.0,
            layer_left_percent=20.0,
            y_label_gap_cm=0.005,
        )


@pytest.mark.parametrize(
    ("right", "center"),
    [(float("nan"), 25.0), (19.0, float("inf")), (-1.0, 25.0), (19.0, 101.0)],
)
def test_row_label_geometry_rejects_invalid_planned_anchor(right, center):
    anchor = heatmap_layout.HeatmapRowLabelAnchor(0, "Sample 01", right, center)

    with pytest.raises(ValueError):
        heatmap_layout.verify_heatmap_row_label_geometry(
            anchor,
            left_percent=9.0,
            top_percent=24.0,
            width_percent=10.0,
            height_percent=2.0,
            page_width_cm=20.0,
            layer_left_percent=20.0,
            y_label_gap_cm=0.2,
        )
