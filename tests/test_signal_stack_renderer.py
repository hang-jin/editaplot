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

from origin_sciplot.origin_backend.safe_errors import OriginDrawError  # noqa: E402
from origin_sciplot.origin_backend.signal_stack_renderer import (  # noqa: E402
    _prepare_signal_channel_data,
    _resolve_signal_stack_layout,
    _verify_signal_helper_arrays,
)
from origin_sciplot.signal_stack import build_signal_stack_plan  # noqa: E402


def _source():
    frame = pd.DataFrame(
        {
            "Time": [0, 0.1, 1, 0.7, 2],
            "Value": [-2, 1, 2, -1, 0],
            "Channel": ["Cz", "Pz", "Cz", "Pz", "Cz"],
            "Note": ["a", "b", "c", "d", "e"],
        },
        index=[9, 2, 9, -1, 3],
    )
    plan = build_signal_stack_plan(
        frame,
        time_column="Time",
        value_column="Value",
        channel_column="Channel",
        time_unit="s",
        value_unit="µV",
    )
    return frame, plan


def _preparation():
    return SimpleNamespace(
        plot_spec=SimpleNamespace(
            x_scale="linear",
            y_scale="linear",
            x_title="Time (s)",
            y_title="Amplitude (µV)",
            axis_plan=SimpleNamespace(x_from=-0.5, x_to=2.6, x_step=0.5, y_from=-3.0, y_to=8.0, y_step=1.0),
        )
    )


def test_channel_helpers_preserve_original_rows_time_and_amplitude_with_only_additive_offset():
    frame, plan = _source()
    before = frame.copy(deep=True)

    channels = _prepare_signal_channel_data(frame, plan)

    assert [label for label, _data in channels] == ["Cz", "Pz"]
    np.testing.assert_array_equal(channels[0][1].to_numpy(), [[0, -2, 3], [1, 2, 7], [2, 0, 5]])
    np.testing.assert_array_equal(channels[1][1].to_numpy(), [[0.1, 1, 1], [0.7, -1, -1]])
    assert sum(len(data) for _, data in channels) == len(frame)
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize(
    "field,value",
    [
        ("channel_rows", (("Cz", (0, 2)), ("Pz", (1, 3)))),
        ("offsets", (("Cz", 4.0), ("Pz", 0.0))),
        ("offset_step", 0.5),
    ],
)
def test_renderer_rejects_unfrozen_row_selection_or_channelwise_scaling(field, value):
    frame, plan = _source()
    with pytest.raises(OriginDrawError, match="source table"):
        _prepare_signal_channel_data(frame, replace(plan, **{field: value}))


def test_helper_readback_checks_source_time_exactly_and_subtracted_offset_to_tolerance():
    frame, plan = _source()
    _, expected = _prepare_signal_channel_data(frame, plan)[0]
    report = _verify_signal_helper_arrays(expected.copy(), expected, "Cz", 5.0)
    assert report["count"] == 3
    assert report["source_time_exact"] is True
    assert report["source_amplitude_exact"] is True
    assert report["offset_subtraction_preserves_amplitude"] is True
    for column in expected.columns:
        changed = expected.copy()
        changed.loc[0, column] += 1e-6
        with pytest.raises(OriginDrawError, match="Cz"):
            _verify_signal_helper_arrays(changed, expected, "Cz", 5.0)
    with pytest.raises(OriginDrawError, match="Cz"):
        _verify_signal_helper_arrays(expected.iloc[:-1], expected, "Cz", 5.0)


def test_layout_reserves_frozen_space_and_ruler_has_exact_unit_length():
    _, plan = _source()
    prep = _preparation()
    layout = _resolve_signal_stack_layout(prep, plan)

    assert layout["x_range"] == (-0.5, 2.6)
    assert layout["y_range"] == (-3.0, 8.0)
    assert -0.5 < layout["channel_label_x"] < plan.time_range[0]
    assert plan.time_range[1] < layout["reference_x"] < layout["reference_label_x"] < 2.6
    assert layout["reference_y_to"] - layout["reference_y_from"] == plan.amplitude_scale_length
    assert layout["channel_label_y"] == (("Cz", 5.0), ("Pz", 0.0))
    assert prep.plot_spec.axis_plan.x_from == -0.5
    assert prep.plot_spec.axis_plan.x_to == 2.6


@pytest.mark.parametrize(
    "property_name,value",
    [
        ("x_from", 0.0),
        ("x_from", -0.01),
        ("x_to", 2.0),
        ("x_to", 2.01),
        ("y_from", -1.0),
        ("y_to", 6.0),
        ("x_step", 0.0),
        ("y_step", np.nan),
    ],
)
def test_insufficient_frozen_limits_or_invalid_steps_reject_before_origin(property_name, value):
    _, plan = _source()
    prep = _preparation()
    setattr(prep.plot_spec.axis_plan, property_name, value)
    with pytest.raises(OriginDrawError, match="frozen"):
        _resolve_signal_stack_layout(prep, plan)


def test_constant_single_channel_requires_frozen_space_for_its_reference_ruler():
    frame = pd.DataFrame({"Time": [0, 1], "Value": [0, 0], "Channel": ["A", "A"]})
    plan = build_signal_stack_plan(
        frame,
        time_column="Time",
        value_column="Value",
        channel_column="Channel",
        time_unit="s",
        value_unit="µV",
    )
    prep = _preparation()
    prep.plot_spec.axis_plan.y_from, prep.plot_spec.axis_plan.y_to = plan.display_y_range
    with pytest.raises(OriginDrawError, match="ruler"):
        _resolve_signal_stack_layout(prep, plan)


@pytest.mark.parametrize(
    "property_name,value",
    [("x_scale", "log10"), ("y_scale", "log10"), ("x_title", "Time"), ("y_title", "Amplitude")],
)
def test_requires_linear_axes_and_explicit_source_units_in_frozen_titles(property_name, value):
    _, plan = _source()
    prep = _preparation()
    setattr(prep.plot_spec, property_name, value)
    with pytest.raises(OriginDrawError):
        _resolve_signal_stack_layout(prep, plan)


class _EditableText:
    def __init__(self, text, *, size=18.0):
        self.text = text
        self.properties = {"font": 72, "fsize": size, "show": 1}

    def set_int(self, key, value):
        self.properties[key] = value

    def set_float(self, key, value):
        self.properties[key] = value

    def get_int(self, key):
        return int(self.properties[key])

    def get_float(self, key):
        return float(self.properties[key])


def test_native_builder_preserves_source_restores_frozen_axes_and_draws_common_unit_ruler(monkeypatch):
    from origin_sciplot.origin_backend import evidence_renderer, scientific_renderer, verify_utils
    from origin_sciplot.origin_backend.signal_stack_renderer import build_signal_stack_graph

    frame, plan = _source()
    original = frame.copy(deep=True)
    prep = _preparation()
    prep.template_id = "signal_stack"
    style = SimpleNamespace(
        plot_line_width_pt=1.8,
        tick_label_size_pt=15.0,
        frame_line_width_pt=1.3,
        font_family="Arial",
        legend_size_pt=15.0,
        axis_title_size_pt=18.0,
    )
    written, state, text_objects, native_plots = {}, {}, [], []
    op, graph, layer = (MagicMock() for _ in range(3))
    op.new_graph.return_value = graph
    graph.__getitem__.return_value = layer
    op.lt_float.return_value = 72.0
    op.ocolor.return_value = 1

    def new_sheet(_kind, name):
        sheet = MagicMock()
        sheet.from_df.side_effect = lambda data: written.__setitem__(name, data.copy(deep=True))
        sheet.to_df.side_effect = lambda: written[name].copy(deep=True)
        return sheet

    def add_plot(*args, **kwargs):
        assert kwargs["type"] == "l"
        plot = MagicMock()
        native_plots.append(plot)
        return plot

    def axis(name):
        handle = MagicMock()
        handle.set_limits.side_effect = lambda start, stop, step: state.update(
            {f"{name}.from": start, f"{name}.to": stop, f"{name}.inc": step}
        )
        return handle

    def style_axes(*_args, **_kwargs):
        for name in ("x", "y"):
            for key, value in {
                "from": 0,
                "to": 1,
                "inc": 1,
                "type": 1,
                "showAxes": 3,
                "ticks": 1,
                "minorTicks": 1,
                "showLabels": 1,
                "label.table": 0,
                "label.type": 0,
                "label.pt": 15,
                "label.font": 72,
                "label.rotate": 0,
                "thickness": 1.3,
                "tickthickness": 1.3,
                "atZero": 0,
            }.items():
                state[f"{name}.{key}"] = value

    def style_titles(*_args):
        state.update({"x.from": 0, "x.to": 1, "y.from": 0, "y.to": 1})
        return {"x_title": _EditableText("Time (s)"), "y_title": _EditableText("Amplitude (µV)")}, {}, {}

    def add_label(text):
        label = _EditableText(text)
        text_objects.append(label)
        return label

    op.new_sheet.side_effect = new_sheet
    layer.add_plot.side_effect = add_plot
    layer.add_label.side_effect = add_label
    layer.label.return_value = None
    layer.axis.side_effect = axis
    layer.set_int.side_effect = state.__setitem__
    layer.get_int.side_effect = lambda key: 200 if key.endswith(".pid") else int(state[key])
    layer.get_float.side_effect = lambda key: float(state[key])
    monkeypatch.setattr(scientific_renderer, "_figure_style", lambda _prep: style)
    monkeypatch.setattr(scientific_renderer, "_apply_page_layer", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(scientific_renderer, "_clean_numeric_x_axis", lambda *_args: None)
    monkeypatch.setattr(scientific_renderer, "_title_geometry", lambda *_args: {})
    monkeypatch.setattr(evidence_renderer, "_style_evidence_axes", style_axes)
    monkeypatch.setattr(evidence_renderer, "_style_titles", style_titles)
    monkeypatch.setattr(verify_utils, "verify_page_and_layer", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(verify_utils, "verify_plot_color", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(verify_utils, "verify_plot_line_widths", lambda *_args, **_kwargs: {})

    result, report = build_signal_stack_graph(op, frame, prep, plan)

    assert result is graph
    pd.testing.assert_frame_equal(frame, original)
    pd.testing.assert_frame_equal(written["SIGNAL_STACK Source"], original)
    assert (state["x.from"], state["x.to"]) == (-0.5, 2.6)
    assert (state["y.from"], state["y.to"]) == (-3.0, 8.0)
    assert state["x.showLabels"] == 1
    assert state["y.showLabels"] == state["y.ticks"] == state["y.minorTicks"] == 0
    assert state["x.label.font"] == state["y.label.font"] == 72
    assert len(native_plots) == 3
    assert [label.text for label in text_objects[:2]] == list(plan.channel_order)
    assert "Shared scale" in text_objects[-1].text and "1 µV" in text_objects[-1].text
    readback = report["origin_signal_stack_readback"]
    assert readback["source_observation_count"] == 5
    assert readback["channel_offsets"] == plan.offsets
    assert readback["amplitude_reference_value"] == 1.0
    assert readback["native_plot_types"] == [200, 200, 200]
    assert all(label.get_int("attach") == 2 for label in text_objects)
    assert all(label.get_float("font") == 72 for label in text_objects)


def test_native_windows_line_endings_preserve_exact_multiline_label_content():
    from origin_sciplot.origin_backend.signal_stack_renderer import _verify_signal_text

    values = {"attach": 2, "show": 1, "x1": 4.4, "y1": 5.0}
    label = SimpleNamespace(
        text="Shared scale\r\n10 uV", get_int=values.__getitem__, get_float=values.__getitem__
    )
    report = _verify_signal_text(label, "Shared scale\n10 uV", 4.4, 5.0)
    assert report["text"] == "Shared scale\n10 uV"
    label.text = "Shared scale\r\n20 uV"
    with pytest.raises(OriginDrawError, match="source text"):
        _verify_signal_text(label, "Shared scale\n10 uV", 4.4, 5.0)
