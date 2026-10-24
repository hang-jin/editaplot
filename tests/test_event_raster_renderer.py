from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime/src"))

from origin_sciplot.origin_backend import event_raster_renderer as renderer  # noqa: E402
from origin_sciplot.origin_backend.safe_errors import OriginDrawError  # noqa: E402
from origin_sciplot.scientific_workflow import load_scientific_frame, prepare_scientific  # noqa: E402


@pytest.fixture
def prepared(tmp_path):
    source = tmp_path / "events.csv"
    pd.DataFrame(
        {
            "Time (s)": [-0.1, None, 0.2, 0.0, 0.4],
            "Trial": ["01", "02", "01", "03", "03"],
            "Condition": ["A", "B", "A", "A", "A"],
        }
    ).to_csv(source, index=False)
    return prepare_scientific(source, "event_raster")


def test_helpers_bind_every_event_to_its_exact_source_row_and_never_fill_inventory(prepared):
    frame = load_scientific_frame(prepared.source_path, prepared)
    snapshot = frame.copy(deep=True)
    groups = renderer._prepare_event_raster_data(frame, prepared)
    assert [condition for condition, _data in groups] == ["A", "B"]
    np.testing.assert_array_equal(
        groups[0][1].to_numpy(), [[-0.1, 1, 1], [0.2, 1, 3], [0, 3, 4], [0.4, 3, 5]]
    )
    assert groups[1][1].empty and list(groups[1][1]) == ["SourceTime", "TrialOrdinal", "SourceRow"]
    pd.testing.assert_frame_equal(frame, snapshot)


def test_condition_row_groups_keep_source_event_order_and_empty_conditions(prepared):
    from origin_sciplot.event_raster import event_rows_by_condition

    assert event_rows_by_condition(prepared.plot_spec.event_raster_plan) == (("A", (0, 2, 3, 4)), ("B", ()))


def test_render_rejects_interior_event_value_change_even_when_extents_and_trial_order_match(prepared):
    frame = load_scientific_frame(prepared.source_path, prepared)
    frame.loc[2, "Time (s)"] = 0.25
    with pytest.raises(OriginDrawError, match="source"):
        renderer.build_event_raster_graph(None, frame, prepared)


def test_render_rejects_modified_source_file_before_origin_is_called(prepared):
    frame = load_scientific_frame(prepared.source_path, prepared)
    changed = frame.copy()
    changed.loc[2, "Time (s)"] = 0.25
    changed.to_csv(prepared.source_path, index=False)
    with pytest.raises(OriginDrawError, match="source"):
        renderer.build_event_raster_graph(None, frame, prepared)


def test_render_rejects_unfrozen_trial_direction_before_origin_is_called(prepared):
    frame = load_scientific_frame(prepared.source_path, prepared)
    changed_layout = replace(prepared.plot_spec.event_raster_layout, y_range=(0.5, 3.5))
    changed = replace(prepared, plot_spec=replace(prepared.plot_spec, event_raster_layout=changed_layout))
    with pytest.raises(OriginDrawError, match="layout"):
        renderer.build_event_raster_graph(None, frame, changed)


def test_native_gate_rejects_unit_mislabel_even_with_innocent_source_unit_letters(prepared):
    from origin_sciplot.event_raster_layout import build_event_raster_layout

    title = "Trial's event time (ms)"
    layout = build_event_raster_layout(
        prepared.plot_spec.event_raster_plan, title, prepared.plot_spec.y_title
    )
    spec = replace(
        prepared.plot_spec,
        x_title=title,
        event_raster_layout=layout,
        display_plan=replace(prepared.plot_spec.display_plan, figure_style=layout.style),
    )
    with pytest.raises(OriginDrawError, match="unit"):
        renderer._validate_event_layout(replace(prepared, plot_spec=spec))


@pytest.mark.parametrize("column", ["SourceTime", "TrialOrdinal", "SourceRow"])
def test_native_helper_readback_rejects_changed_event_time_lane_or_lineage(prepared, column):
    frame = load_scientific_frame(prepared.source_path, prepared)
    expected = renderer._prepare_event_raster_data(frame, prepared)[0][1]
    assert renderer._verify_event_helper(expected.copy(), expected)["event_count"] == 4
    actual = expected.copy()
    actual.loc[0, column] += 1e-4
    with pytest.raises(OriginDrawError, match="helper"):
        renderer._verify_event_helper(actual, expected)


def test_source_import_preserves_numeric_looking_trial_ids_and_blank_times(prepared):
    frame = load_scientific_frame(prepared.source_path, prepared)
    imported = renderer._event_source_copy(frame, prepared.plot_spec.event_raster_plan)
    assert list(imported.Trial) == ["01", "02", "01", "03", "03"]
    assert isinstance(imported.Trial.dtype, pd.CategoricalDtype)
    assert imported["Time (s)"].isna().sum() == 1


def test_y_title_readback_rejects_in_page_drift_into_trial_label_column():
    layout = SimpleNamespace(y_title_x_percent=4.0, y_title_y_percent=50.0)
    state = {"left": 30.0, "top": 300.0, "width": 20.0, "height": 200.0, "attach": 1}
    label = SimpleNamespace(get_float=state.__getitem__, get_int=state.__getitem__)
    assert renderer._verify_event_y_title(label, layout, 1000, 800)["center_x_percent"] == 4
    state["left"] = 150.0  # Still inside the page: clipping-only checks miss this overlap.
    with pytest.raises(OriginDrawError, match="Y title"):
        renderer._verify_event_y_title(label, layout, 1000, 800)
    state["left"], state["attach"] = 30.0, 2
    with pytest.raises(OriginDrawError, match="Y title"):
        renderer._verify_event_y_title(label, layout, 1000, 800)


def test_page_y_title_checks_actual_rich_text_not_only_position():
    layout = SimpleNamespace(y_title_x_percent=4.0, y_title_y_percent=50.0)
    state = {"left": 30.0, "top": 300.0, "width": 20.0, "height": 200.0, "attach": 1}
    label = SimpleNamespace(get_float=state.__getitem__, get_int=state.__getitem__, text=r"\b(Trial order)")
    renderer._verify_event_y_title(label, layout, 1000, 800, expected_text="Trial order")
    label.text = r"\b(Unrelated text)"
    with pytest.raises(OriginDrawError):
        renderer._verify_event_y_title(label, layout, 1000, 800, expected_text="Trial order")


@pytest.mark.parametrize(
    "property_name, bad_value",
    [
        ("x.inc", 0.3),
        ("y.from", 0.5),
        ("y.showLabels", 1),
        ("y.ticks", 3),
        ("x.label.font", 99),
        ("y.label.pt", 8),
    ],
)
def test_native_axis_gate_checks_step_direction_hidden_ticks_and_both_fonts(
    prepared, property_name, bad_value
):
    axis, style = prepared.plot_spec.axis_plan, prepared.plot_spec.display_plan.figure_style
    state = {}
    for name, limits in (
        ("x", (axis.x_from, axis.x_to, axis.x_step)),
        ("y", (axis.y_from, axis.y_to, -axis.y_step)),
    ):
        state.update(
            {f"{name}.{key}": value for key, value in zip(("from", "to", "inc"), limits, strict=True)}
        )
        state.update(
            {
                f"{name}.{key}": value
                for key, value in {
                    "showAxes": 3,
                    "atZero": 0,
                    "label.table": 0,
                    "type": 1,
                    "showLabels": 1 if name == "x" else 0,
                    "label.font": 7,
                    "label.pt": 17,
                    "thickness": style.frame_line_width_pt,
                    "label.rotate": 0,
                    "ticks": 3 if name == "x" else 0,
                    "minorTicks": 1 if name == "x" else 0,
                }.items()
            }
        )
    layer = SimpleNamespace(get_float=lambda key: state.get(key, 0), get_int=lambda key: state.get(key, 0))
    op = SimpleNamespace(lt_float=lambda _key: 7)
    assert renderer._verify_event_axes(op, layer, prepared)["y.from"] == 3.5
    state[property_name] = bad_value
    with pytest.raises(OriginDrawError):
        renderer._verify_event_axes(op, layer, prepared)
