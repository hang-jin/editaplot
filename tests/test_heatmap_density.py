from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.heatmap_layout import (  # noqa: E402
    heatmap_cell_labels_enabled,
    resolve_heatmap_colorbar_geometry,
    resolve_heatmap_layout,
)
from origin_sciplot.scientific_preview import (  # noqa: E402
    _build_scientific_preview_figure,
)
from origin_sciplot.scientific_visual import resolve_adaptive_style  # noqa: E402
from origin_sciplot.scientific_workflow import prepare_scientific  # noqa: E402


def _heatmap_source(path: Path, size: int, *, signed: bool = False) -> tuple[Path, pd.DataFrame]:
    row_axis = np.linspace(-1.0, 1.0, size)
    column_axis = np.linspace(-1.0, 1.0, size)
    values = np.outer(np.sin(row_axis * 2.4), np.cos(column_axis * 2.1))
    if not signed:
        values = (values - values.min()) / (values.max() - values.min())
    frame = pd.DataFrame(
        values,
        columns=[f"Feature {index + 1:02d}" for index in range(size)],
    )
    frame.insert(0, "Material", [f"Sample {index + 1:02d}" for index in range(size)])
    frame.to_csv(path, index=False)
    return path, frame


def test_small_and_dense_cell_label_thresholds_are_explicit() -> None:
    assert heatmap_cell_labels_enabled(12, 10)
    assert not heatmap_cell_labels_enabled(13, 10)
    assert not heatmap_cell_labels_enabled(12, 11)
    assert not heatmap_cell_labels_enabled(30, 30)


def test_public_dense_heatmap_fixture_is_exactly_30_by_30() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "gallery"
        / "heatmap_dense_30x30.csv"
    )
    frame = pd.read_csv(source)
    values = frame.iloc[:, 1:].to_numpy(dtype=float)

    assert frame.shape == (30, 31)
    assert values.shape == (30, 30)
    assert values.size == 900
    assert frame.columns[0] == "Dataset"
    assert frame.columns[1] == "Series 01"
    assert frame.columns[-1] == "Series 30"
    assert frame.iloc[0, 0] == "Dataset 01"
    assert frame.iloc[-1, 0] == "Dataset 30"
    assert np.isfinite(values).all()
    assert float(values.min()) >= 0.0
    assert float(values.max()) <= 1.0


@pytest.mark.parametrize(
    ("size", "expected_x_stride", "expected_y_stride"),
    [(30, 4, 2), (40, 5, 3)],
)
def test_dense_layout_thins_labels_and_preserves_endpoints(
    size: int,
    expected_x_stride: int,
    expected_y_stride: int,
) -> None:
    labels = [f"F{index + 1:02d}" for index in range(size)]
    layout = resolve_heatmap_layout(
        x_labels=labels,
        y_labels=labels,
        tick_label_size_pt=17.0,
        major_tick_length_pt=5.5,
    )

    assert not layout.show_cell_labels
    assert layout.x_label_stride == expected_x_stride
    assert layout.y_label_stride == expected_y_stride
    assert len(layout.x_visible_indices) <= 9
    assert len(layout.y_visible_indices) <= 16
    assert layout.x_visible_indices[0] == layout.y_visible_indices[0] == 0
    assert layout.x_visible_indices[-1] == layout.y_visible_indices[-1] == size - 1
    assert (
        layout.x_visible_indices[-1] - layout.x_visible_indices[-2]
        >= layout.x_label_stride
    )
    assert (
        layout.y_visible_indices[-1] - layout.y_visible_indices[-2]
        >= layout.y_label_stride
    )
    assert layout.x_display_labels[0] == "F01"
    assert layout.x_display_labels[-1] == f"F{size:02d}"
    assert layout.x_tick_length_pt == 0.0
    assert layout.y_tick_length_pt == 0.0
    assert layout.x_rotation_deg == 45.0
    assert layout.colorbar_label_size_pt >= 15.0


def test_long_x_labels_use_a_smaller_budget_and_rotation() -> None:
    layout = resolve_heatmap_layout(
        x_labels=[f"Long material feature {index:02d}" for index in range(30)],
        y_labels=[f"S{index:02d}" for index in range(30)],
        tick_label_size_pt=17.0,
        major_tick_length_pt=5.5,
    )

    assert len(layout.x_visible_indices) <= 8
    assert layout.x_rotation_deg == 55.0


@pytest.mark.parametrize("size", [30, 40, 80])
def test_dense_heatmap_style_caps_page_without_shrinking_type(size: int) -> None:
    style = resolve_adaptive_style(
        template_id="heatmap",
        plot_kind="heatmap",
        row_count=size,
        series_count=size,
        max_label_length=9,
    )

    assert style.page_width_cm <= 36.0
    assert style.page_height_cm <= 30.0
    assert style.tick_label_size_pt == 17.0
    assert style.legend_size_pt == 17.0
    assert style.layer_left_percent + style.layer_width_percent == pytest.approx(84.0)


def test_colorbar_geometry_is_detached_and_rejects_insufficient_margin() -> None:
    geometry = resolve_heatmap_colorbar_geometry(18.0, 66.0)
    assert geometry.layer_right_fraction == pytest.approx(0.84)
    assert geometry.left_fraction - geometry.layer_right_fraction == pytest.approx(0.025)
    assert geometry.left_fraction + geometry.object_width_fraction == pytest.approx(0.995)
    assert geometry.bar_axis_width_fraction <= geometry.object_width_fraction

    with pytest.raises(ValueError, match="insufficient right margin"):
        resolve_heatmap_colorbar_geometry(20.0, 75.0)


def test_dense_workflow_uses_heatmap_warnings_and_correct_axis_semantics(tmp_path: Path) -> None:
    source, _frame = _heatmap_source(tmp_path / "dense.csv", 30)
    preparation = prepare_scientific(source, "heatmap")

    assert "series_count_excessive" not in preparation.warnings
    assert "series_count_high" not in preparation.warnings
    assert "heatmap_cell_labels_hidden" in preparation.warnings
    assert "heatmap_dense_matrix" in preparation.warnings
    assert preparation.plot_spec.x_title == "Series"
    assert preparation.plot_spec.y_title == "Material"


@pytest.mark.parametrize(("size", "signed"), [(30, False), (40, True)])
def test_dense_preview_preserves_matrix_and_detaches_colorbar(
    tmp_path: Path,
    size: int,
    signed: bool,
) -> None:
    source, frame = _heatmap_source(tmp_path / f"dense-{size}.csv", size, signed=signed)
    preparation = prepare_scientific(source, "heatmap")
    figure = _build_scientific_preview_figure(preparation)
    image_axis = next(axis for axis in figure.axes if axis.images)
    colorbar_axis = next(axis for axis in figure.axes if axis is not image_axis)
    plotted = np.asarray(image_axis.images[0].get_array(), dtype=float)

    np.testing.assert_allclose(plotted, frame.iloc[:, 1:].to_numpy(dtype=float))
    assert plotted.shape == (size, size)
    assert not image_axis.texts
    assert sum(bool(label.get_text()) for label in image_axis.get_xticklabels()) <= 9
    assert sum(bool(label.get_text()) for label in image_axis.get_yticklabels()) <= 16
    assert all(
        label.get_rotation() == pytest.approx(45.0)
        for label in image_axis.get_xticklabels()
        if label.get_text()
    )
    assert colorbar_axis.get_position().x0 - image_axis.get_position().x1 >= 0.019
    if signed:
        normalization = image_axis.images[0].norm
        assert normalization.vmin == pytest.approx(-normalization.vmax)
    else:
        assert math.isfinite(float(image_axis.images[0].norm.vmin))
