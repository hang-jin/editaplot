"""Categorical publication styling, with no Origin session or source-data edits."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import to_hex

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/src"))

from origin_sciplot.scientific_preview import _build_scientific_preview_figure  # noqa: E402
from origin_sciplot.scientific_visual import palette_colors, resolve_adaptive_style  # noqa: E402
from origin_sciplot.scientific_workflow import prepare_scientific  # noqa: E402


def _physical_regions(style):
    left = style.page_width_cm * style.layer_left_percent / 100
    data = style.page_width_cm * style.layer_width_percent / 100
    return left, data, style.page_width_cm - left - data


def _white_contrast(color):
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return 1.05 / (
        sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True)) + 0.05
    )


@pytest.mark.parametrize("kind", ["bar_error", "radar"])
def test_comparisons_use_eight_visible_colors_with_coral_third_series(kind):
    style = resolve_adaptive_style(template_id="test", plot_kind=kind, row_count=5, series_count=8)
    assert style.palette_name == "publication_comparison"
    colors = palette_colors(style.palette_name)
    assert len(colors) == len(set(colors)) == 8
    assert colors[:3] == ("#59666F", "#247B8B", "#C66454")
    assert min(map(_white_contrast, colors)) >= 3.0


@pytest.mark.parametrize("kind", ["bar_error", "horizontal_bar", "radar"])
@pytest.mark.parametrize("series_count", [1, 3, 8])
def test_categorical_legend_has_a_real_external_column(kind, series_count):
    style = resolve_adaptive_style(
        template_id="test",
        plot_kind=kind,
        row_count=5,
        series_count=series_count,
        max_label_length=26,
    )
    assert style.profile_name.endswith("-external-legend")
    assert _physical_regions(style)[2] >= 8.0
    assert style.legend_size_pt >= 17


@pytest.mark.parametrize("rows", [2, 5, 8])
@pytest.mark.parametrize("label_length", [8, 26, 45])
def test_horizontal_label_gutter_is_physical_and_does_not_squeeze_data(rows, label_length):
    style = resolve_adaptive_style(
        template_id="horizontal_bar",
        plot_kind="horizontal_bar",
        row_count=rows,
        series_count=1,
        max_label_length=label_length,
    )
    left, data, right = _physical_regions(style)
    estimated_text_width = label_length * style.tick_label_size_pt * 2.54 / 72 * 0.52
    assert estimated_text_width + 0.6 <= left <= estimated_text_width + 1.3
    assert data >= 16.0
    assert right >= 8.0
    assert style.tick_label_size_pt == 17
    assert style.axis_title_size_pt == 20


def test_long_horizontal_labels_expand_the_page_not_the_font_or_data_field():
    styles = [
        resolve_adaptive_style(
            template_id="horizontal_bar",
            plot_kind="horizontal_bar",
            row_count=5,
            series_count=1,
            max_label_length=length,
        )
        for length in (8, 26, 45)
    ]
    assert styles[0].page_width_cm < styles[1].page_width_cm < styles[2].page_width_cm
    assert (
        max(_physical_regions(style)[1] for style in styles)
        - min(_physical_regions(style)[1] for style in styles)
        < 0.02
    )


def test_percent_title_keeps_its_full_bottom_gutter():
    style = resolve_adaptive_style(
        template_id="percent_stacked_bar", plot_kind="percent_stacked_bar", row_count=5, series_count=4
    )
    assert style.x_title_upshift_page_percent == 0


def test_radar_reserves_a_physical_top_gutter_for_metric_titles():
    style = resolve_adaptive_style(template_id="radar", plot_kind="radar", row_count=5, series_count=3)
    assert style.page_height_cm * style.layer_top_percent / 100 >= 2.2


def test_long_series_legend_does_not_inflate_the_category_label_gutter():
    short = resolve_adaptive_style(
        template_id="horizontal_bar",
        plot_kind="horizontal_bar",
        row_count=5,
        series_count=3,
        max_label_length=8,
        max_legend_label_length=8,
    )
    long = resolve_adaptive_style(
        template_id="horizontal_bar",
        plot_kind="horizontal_bar",
        row_count=5,
        series_count=3,
        max_label_length=8,
        max_legend_label_length=40,
    )
    sleft, sdata, sright = _physical_regions(short)
    lleft, ldata, lright = _physical_regions(long)
    assert lleft == pytest.approx(sleft, abs=0.02)
    assert ldata == pytest.approx(sdata, abs=0.02)
    assert lright > sright + 4


def test_chinese_category_labels_reserve_full_width_glyph_space(tmp_path):
    source = tmp_path / "chinese.csv"
    labels = ["完整模型", "去除动态校准策略"]
    pd.DataFrame({"Category": labels, "Score": [0.9, 0.8]}).to_csv(source, index=False)
    preparation = prepare_scientific(source, "horizontal_bar")
    style = preparation.plot_spec.display_plan.figure_style
    left_cm = style.page_width_cm * style.layer_left_percent / 100
    assert left_cm > 5.0
    assert preparation.plot_spec.display_plan.category_label_rotation_deg == 0


@pytest.mark.parametrize("rows", [2, 5, 8])
def test_horizontal_error_preview_keeps_all_labels_and_legend_outside_bars(tmp_path, rows):
    source = tmp_path / "horizontal.csv"
    labels = [f"Without feature alignment module {index + 1}" for index in range(rows)]
    pd.DataFrame(
        {"Category": labels, "Performance": np.linspace(0.91, 0.70, rows), "Performance_SEM": [0.02] * rows}
    ).to_csv(source, index=False)
    preparation = prepare_scientific(source, "horizontal_bar")
    figure = _build_scientific_preview_figure(preparation)
    canvas = FigureCanvasAgg(figure)
    canvas.draw()
    renderer = canvas.get_renderer()
    axis = figure.axes[0]
    legend = axis.get_legend()
    assert legend is not None
    assert legend.get_window_extent(renderer).x0 > axis.get_window_extent(renderer).x1
    assert legend.get_window_extent(renderer).x1 < figure.bbox.x1
    assert [label.get_text() for label in axis.get_yticklabels()] == labels
    assert min(label.get_window_extent(renderer).x0 for label in axis.get_yticklabels()) > 0
    assert len(axis.patches) == rows
    assert axis.yaxis.label.get_text() == ""


def test_radar_preview_preserves_five_metrics_and_values():
    source = ROOT / "examples/gallery/radar_multimetric.csv"
    preparation = prepare_scientific(source, "radar")
    figure = _build_scientific_preview_figure(preparation)
    canvas = FigureCanvasAgg(figure)
    canvas.draw()
    axis = figure.axes[0]
    frame = pd.read_csv(source)
    assert [label.get_text() for label in axis.get_xticklabels()] == frame["Metric"].tolist()
    assert len(axis.lines) == 3
    for line, column in zip(axis.lines, frame.columns[1:], strict=True):
        np.testing.assert_allclose(line.get_ydata()[:-1], frame[column])
    assert axis.lines[2].get_color() == "#C66454"
    legend_box = axis.get_legend().get_window_extent(canvas.get_renderer())
    assert legend_box.x0 > axis.get_window_extent(canvas.get_renderer()).x1
    assert legend_box.x1 < figure.bbox.x1


def test_horizontal_preview_preserves_the_native_category_color_ramp():
    source = ROOT / "examples/gallery/horizontal_long_labels.csv"
    preparation = prepare_scientific(source, "horizontal_bar")
    figure = _build_scientific_preview_figure(preparation)
    bars = figure.axes[0].patches
    palette = palette_colors(preparation.plot_spec.display_plan.figure_style.palette_name)
    assert to_hex(bars[0].get_facecolor()).upper() == palette[0]
    assert to_hex(bars[-1].get_facecolor()).upper() == palette[-1]
    assert len({to_hex(bar.get_facecolor()) for bar in bars}) == len(bars)


def test_radar_native_legend_returns_final_geometry_without_hiding_metrics(monkeypatch):
    # Reuse the native radar test double; only its text-bounds surface is new.
    from test_radar_publication_contract import _Label, _render

    def get_float(label, name):
        return float(label.properties.get(name, {"width": 10.0, "height": 10.0}.get(name, 0)))

    monkeypatch.setattr(_Label, "get_float", get_float, raising=False)
    layer, state = _render(monkeypatch)
    bounds = state["origin_text_state"]["external_legend"]
    assert bounds["legend.outside_data_field"] is True
    assert bounds["legend.attach"] == 1
    assert bounds["legend.showframe"] == 0
    assert bounds["legend.width"] == 10.0
    assert layer.labels["yl"].get_int("show") == 1
    assert state["origin_axis_state"]["radial_label_offset_percent"] == 70.0


def test_composition_palettes_and_profiles_are_unchanged():
    expected = {
        "stacked_bar": ("stacked_blue", ("#DCE8F2", "#BCD2E5", "#91B6D4", "#6395BE", "#3B74A5", "#214F7D")),
        "percent_stacked_bar": (
            "composition_lilac",
            ("#ECEBF5", "#D2D0E8", "#B4B0D8", "#928BC2", "#6E65A8", "#494277"),
        ),
    }
    for kind, (palette_name, colors) in expected.items():
        style = resolve_adaptive_style(template_id=kind, plot_kind=kind, row_count=5, series_count=3)
        assert style.palette_name == palette_name
        assert palette_colors(palette_name) == colors
        assert not style.profile_name.endswith("-external-legend")
    assert palette_colors("comparison_family") == (
        "#484878",
        "#7884B4",
        "#B4C0E4",
        "#E4E4F0",
        "#E4CCD8",
        "#F0C0CC",
    )
