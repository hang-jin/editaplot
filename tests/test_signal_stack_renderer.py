from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

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
from origin_sciplot.scientific_visual import resolve_signal_stack_style  # noqa: E402
from origin_sciplot.signal_stack import build_signal_stack_plan  # noqa: E402
from origin_sciplot.signal_stack_layout import build_signal_stack_layout  # noqa: E402


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
    _, plan = _source()
    style = resolve_signal_stack_style(plan.channel_order, "Time (s)", "Amplitude (µV)", "1 µV")
    return SimpleNamespace(
        plot_spec=SimpleNamespace(
            x_scale="linear",
            y_scale="linear",
            x_title="Time (s)",
            y_title="Amplitude (µV)",
            axis_plan=SimpleNamespace(x_from=0.0, x_to=2.0, x_step=0.5, y_from=-3.0, y_to=8.0, y_step=1.0),
            display_plan=SimpleNamespace(figure_style=style),
            signal_stack_layout=build_signal_stack_layout(plan, style, y_range=(-3.0, 8.0)),
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

    assert layout["x_range"] == (0.0, 2.0)
    assert layout["y_range"] == (-3.0, 8.0)
    assert all(
        right < prep.plot_spec.display_plan.figure_style.layer_left_percent
        for _, right, _ in layout["channel_labels"]
    )
    assert layout["reference_x"] > plan.time_range[1]
    assert layout["reference_y_to"] - layout["reference_y_from"] == plan.amplitude_scale_length
    assert [label for label, _, _ in layout["channel_labels"]] == ["Cz", "Pz"]
    assert prep.plot_spec.axis_plan.x_from == 0.0
    assert prep.plot_spec.axis_plan.x_to == 2.0


@pytest.mark.parametrize(
    "property_name,value",
    [
        ("x_from", -0.5),
        ("x_from", -0.01),
        ("x_to", 2.6),
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
    prep.plot_spec.axis_plan.x_to = 1.0
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


def test_new_layer_cleanup_rejects_populated_layers_and_removes_only_visible_objects():
    from origin_sciplot.origin_backend.signal_stack_renderer import _clear_fresh_layer_objects

    names = ["XB", "YL", "Old annotation", "__FRAMESRCDATAINFOS"]

    class Objects:
        def __iter__(self):
            return iter([SimpleNamespace(GetName=lambda name=name: name) for name in names])

    layer = SimpleNamespace(
        obj=SimpleNamespace(GraphObjects=Objects()),
        plot_list=lambda: [],
        remove_label=lambda name: names.remove(name),
    )
    result = _clear_fresh_layer_objects(layer)
    assert result["remaining_visible_objects"] == []
    assert names == ["__FRAMESRCDATAINFOS"]
    layer.plot_list = lambda: [object()]
    with pytest.raises(OriginDrawError, match="fresh empty"):
        _clear_fresh_layer_objects(layer)


def test_amplitude_ruler_rejects_changed_coordinates_or_nonzero_arrowhead():
    from origin_sciplot.origin_backend.signal_stack_renderer import _verify_signal_ruler

    layout = dict(reference_x=2.1, reference_y_from=-1.0, reference_y_to=0.0, reference_height_cm=1.2)
    values = dict(
        x1=2.1,
        x2=2.1,
        y1=-1.0,
        y2=0.0,
        attach=2,
        color=7,
        arrowbeginwidth=0.0,
        arrowbeginlength=0.0,
        arrowendwidth=0.0,
        arrowendlength=0.0,
    )
    line = SimpleNamespace(width=1.4, get_float=values.__getitem__, get_int=values.__getitem__)
    op = SimpleNamespace(ocolor=lambda _color: 7)
    result = _verify_signal_ruler(op, line, layout, 1.4)
    assert result["amplitude_length"] == 1.0
    values["y2"] = 0.5
    with pytest.raises(OriginDrawError, match="readback"):
        _verify_signal_ruler(op, line, layout, 1.4)
    values["y2"] = 0.0
    values["arrowendwidth"] = 4
    with pytest.raises(OriginDrawError, match="arrowhead"):
        _verify_signal_ruler(op, line, layout, 1.4)


def test_origin_import_copy_preserves_numeric_looking_channel_labels_as_text():
    from origin_sciplot.origin_backend.signal_stack_renderer import _signal_import_copy

    source = pd.DataFrame(
        {"Time": [0.0, 1.0, 0.0, 1.0], "Channel": ["01", "01", "02", "02"], "Value": [1.0, 2.0, 3.0, 4.0]}
    )
    before = source.copy(deep=True)
    plan = build_signal_stack_plan(
        source,
        time_column="Time",
        value_column="Value",
        channel_column="Channel",
        time_unit="s",
        value_unit="uV",
    )
    imported = _signal_import_copy(source, plan)
    assert str(imported.Channel.dtype) == "category"
    assert imported.Channel.tolist() == ["01", "01", "02", "02"]
    assert list(imported.Channel.cat.categories) == ["01", "02"]
    np.testing.assert_array_equal(imported[["Time", "Value"]], source[["Time", "Value"]])
    pd.testing.assert_frame_equal(source, before)
