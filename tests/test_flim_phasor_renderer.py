from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/src"))

from origin_sciplot.flim_phasor import build_phasor_plan  # noqa: E402
from origin_sciplot.origin_backend.flim_phasor_renderer import (  # noqa: E402
    _prepare_phasor_group_data,
    _verify_phasor_helper_arrays,
    _verify_phasor_metric_geometry,
)
from origin_sciplot.origin_backend.safe_errors import OriginDrawError  # noqa: E402


def _source():
    frame = pd.DataFrame(
        {"G": [0.2, -0.1, 0.7, 1.2], "S": [0.1, -0.2, 0.3, 0.1],
         "Group": ["B", "A", "B", "A"], "Note": ["one", "two", "three", "four"]},
        index=[12, 2, 12, 8],
    )
    return frame, build_phasor_plan(frame, g_column="G", s_column="S", group_column="Group")


def test_group_plot_data_uses_source_iloc_rows_without_dropping_outside_points():
    frame, plan = _source()
    before = frame.copy(deep=True)
    groups = _prepare_phasor_group_data(frame, plan)

    assert [label for label, _data in groups] == ["B", "A"]
    np.testing.assert_array_equal(groups[0][1].to_numpy(), [[0.2, 0.1], [0.7, 0.3]])
    np.testing.assert_array_equal(groups[1][1].to_numpy(), [[-0.1, -0.2], [1.2, 0.1]])
    assert sum(len(data) for _, data in groups) == len(frame)
    pd.testing.assert_frame_equal(frame, before)


def test_rejects_plan_rows_that_repeat_omit_or_mislabel_source_observations():
    frame, plan = _source()
    corruptions = (
        (("B", (0, 2)), ("A", (1,))),
        (("B", (0, 2)), ("A", (1, 1))),
        (("B", (0, 1)), ("A", (2, 3))),
    )
    for rows in corruptions:
        with pytest.raises(OriginDrawError, match="source"):
            _prepare_phasor_group_data(frame, replace(plan, group_rows=rows))


def test_equal_physical_units_do_not_require_equal_numeric_ranges():
    geometry = {"width_cm": 20, "height_cm": 10, "width_percent": 80, "height_percent": 80}
    report = _verify_phasor_metric_geometry(geometry, (-0.05, 1.05), (-0.025, 0.525))
    assert report["cm_per_g"] == pytest.approx(report["cm_per_s"])
    assert report["unit_ratio"] == pytest.approx(1.0)
    assert report["relative_tolerance"] == 0.003


@pytest.mark.parametrize("height_cm", [8.0, 10.1, np.nan, 0])
def test_rejects_distorted_semicircle_geometry(height_cm):
    geometry = {"width_cm": 20, "height_cm": height_cm, "width_percent": 80, "height_percent": 80}
    with pytest.raises(OriginDrawError, match="physical"):
        _verify_phasor_metric_geometry(geometry, (-0.05, 1.05), (-0.025, 0.525))


def test_helper_readback_must_preserve_every_coordinate_exactly():
    expected = pd.DataFrame({"PlotG": [-0.1, 0.2, 1.2], "PlotS": [0.3, -0.2, 0.1]})
    assert _verify_phasor_helper_arrays(expected.copy(), expected, "Group A") == 3
    changed = expected.copy()
    changed.loc[0, "PlotG"] += 1e-6
    with pytest.raises(OriginDrawError, match="Group A"):
        _verify_phasor_helper_arrays(changed, expected, "Group A")
    with pytest.raises(OriginDrawError, match="Group A"):
        _verify_phasor_helper_arrays(expected.iloc[:-1], expected, "Group A")


def test_builder_keeps_source_tables_and_restores_axes_after_text_refresh(monkeypatch):
    from origin_sciplot.origin_backend import evidence_renderer, scientific_renderer, verify_utils
    from origin_sciplot.origin_backend.flim_phasor_renderer import build_flim_phasor_graph

    frame, plan = _source()
    original = frame.copy(deep=True)
    style = SimpleNamespace(
        profile_name="phasor-external-legend", palette_name="comparison_family",
        plot_line_width_pt=2.0, font_family="Arial", axis_title_size_pt=18.0, legend_size_pt=15.0,
    )
    preparation = SimpleNamespace(
        template_id="flim_phasor",
        plot_spec=SimpleNamespace(
            display_plan=SimpleNamespace(marker_size_pt=4.0),
            axis_plan=SimpleNamespace(x_step=0.2, y_step=0.1),
        ),
    )
    written = {}
    native_plots = []
    state = {}
    op, graph, layer, legend = (MagicMock() for _ in range(4))
    graph.__getitem__.return_value = layer
    op.new_graph.return_value = graph

    def new_sheet(_kind, name):
        sheet = MagicMock()
        sheet.from_df.side_effect = lambda data: written.__setitem__(name, data.copy(deep=True))
        sheet.to_df.side_effect = lambda: written[name].copy(deep=True)
        return sheet

    def add_plot(*_args, **_kwargs):
        plot = MagicMock()
        native_plots.append(plot)
        return plot

    def axis(name):
        handle = MagicMock()
        handle.set_limits.side_effect = lambda lower, upper, step: state.update(
            {f"{name}.from": lower, f"{name}.to": upper, f"{name}.inc": step}
        )
        return handle

    def refreshed_titles(*_args):
        state.update({"x.from": 0.0, "x.to": 1.0, "y.from": 0.0, "y.to": 1.0})
        return {"x_title": MagicMock(), "y_title": MagicMock()}, {}, {}

    op.new_sheet.side_effect = new_sheet
    layer.add_plot.side_effect = add_plot
    layer.axis.side_effect = axis
    layer.get_int.side_effect = lambda key: 200 if key == "plot1.pid" else 201
    geometry = {
        "width_cm": (plan.x_range[1] - plan.x_range[0]) * 12.5,
        "height_cm": (plan.y_range[1] - plan.y_range[0]) * 12.5,
        "width_percent": 80.0, "height_percent": 80.0,
    }
    monkeypatch.setattr(scientific_renderer, "_figure_style", lambda _preparation: style)
    monkeypatch.setattr(scientific_renderer, "_apply_page_layer", lambda *_args, **_kw: geometry)
    monkeypatch.setattr(scientific_renderer, "_clean_numeric_x_axis", lambda *_args: None)
    monkeypatch.setattr(scientific_renderer, "_style_legend", lambda *_args: legend)
    monkeypatch.setattr(scientific_renderer, "_position_publication_legend", lambda *_args: {})
    monkeypatch.setattr(evidence_renderer, "_style_evidence_axes", lambda *_args, **_kw: None)
    monkeypatch.setattr(evidence_renderer, "_style_titles", refreshed_titles)
    monkeypatch.setattr(evidence_renderer, "_validate_axes", lambda *_args: dict(state))
    monkeypatch.setattr(verify_utils, "verify_page_and_layer", lambda *_args, **_kw: geometry)
    for name in ("verify_plot_color", "verify_plot_line_widths", "verify_symbol_style",
                 "verify_text_fonts", "verify_text_sizes"):
        monkeypatch.setattr(verify_utils, name, lambda *_args, **_kw: {})

    returned_graph, report = build_flim_phasor_graph(op, frame, preparation, plan)

    assert returned_graph is graph
    assert (state["x.from"], state["x.to"]) == plan.x_range
    assert (state["y.from"], state["y.to"]) == plan.y_range
    pd.testing.assert_frame_equal(frame, original)
    pd.testing.assert_frame_equal(written["FLIM_PHASOR Source"], original)
    readback = report["origin_phasor_readback"]
    assert readback["source_observation_count"] == 4
    assert readback["group_counts"] == {"B": 2, "A": 2}
    assert readback["reference_kind"] == "mathematical_reference_not_experimental_data"
    assert readback["reference_point_count"] == 181
    assert readback["outside_reference_count"] == plan.outside_reference_count
    assert readback["native_plot_types"] == [200, 201, 201]
    assert all(plot.symbol_size == 4.0 for plot in native_plots[1:])
