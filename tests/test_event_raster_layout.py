from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime/src"))

from origin_sciplot.event_raster import build_event_raster_plan  # noqa: E402
from origin_sciplot.event_raster_layout import build_event_raster_layout  # noqa: E402


def _plan(count=40, *, suffix="", conditions=2):
    frame = pd.DataFrame([
        {"Time": t, "Trial": f"Trial {i:03d}{suffix}", "Condition": f"Condition {i % conditions}"}
        for i in range(count) for t in (-0.1, 0.2)
    ])
    return build_event_raster_plan(frame, event_time_column="Time", trial_column="Trial",
                                   condition_column="Condition", time_unit="s")


def test_layout_preserves_every_trial_with_first_supplied_trial_at_top():
    plan = _plan()
    layout = build_event_raster_layout(plan, "Event time (s)", "Trial (source order)")
    assert layout.x_range == pytest.approx((-0.115, 0.215))
    assert layout.y_range == (40.5, 0.5)
    assert layout.trial_labels[0][:2] == ("Trial 000", 1)
    assert layout.trial_labels[-1][:2] == ("Trial 039", 40)
    assert len(plan.event_rows) == 80 and len(plan.trial_order) == 40
    assert layout.trial_labels[0][3] < layout.trial_labels[-1][3]
    style = layout.style
    row_height_pt = style.page_height_cm * style.layer_height_percent / 100 / 40 * 72 / 2.54
    assert 0 < layout.marker_size_pt < row_height_pt


def test_dense_raster_sparsifies_labels_but_retains_all_two_hundred_lanes():
    plan = _plan(200)
    layout = build_event_raster_layout(plan, "Event time (s)", "Trial")
    assert layout.y_range == (200.5, 0.5)
    assert len(layout.trial_labels) <= 13  # At most twelve regular labels plus final source ID.
    assert layout.trial_labels[-1][1] == 200
    assert len(plan.row_trial_positions) == 400
    assert layout.style.tick_label_size_pt == layout.style.legend_size_pt == 17
    assert layout.marker_size_pt < build_event_raster_layout(_plan(40), "Time (s)", "Trial").marker_size_pt


@pytest.mark.parametrize("count, expected_step", [(1, 1), (16, 2), (40, 5), (200, 25)])
def test_hidden_ordinal_axis_freezes_a_bounded_tick_count(count, expected_step):
    layout = build_event_raster_layout(_plan(count), "Time (s)", "Trial")
    assert layout.y_step == expected_step
    assert count / layout.y_step <= 8


def test_long_source_labels_expand_gutter_without_smaller_type():
    short = build_event_raster_layout(_plan(), "Time (s)", "Trial")
    long = build_event_raster_layout(
        _plan(suffix=" - supplied recording unit identifier"), "Time (s)", "Trial"
    )
    assert long.style.page_width_cm > short.style.page_width_cm
    assert long.style.legend_size_pt == short.style.legend_size_pt == 17
    for _label, _ordinal, right, _y in long.trial_labels:
        assert right < long.style.layer_left_percent


def test_multiline_trial_names_do_not_overlap_after_sparse_label_selection():
    layout = build_event_raster_layout(_plan(200, suffix="\nRegion A\nSession B\nLeft"), "Time (s)", "Trial")
    ys = [item[3] / 100 * layout.style.page_height_cm for item in layout.trial_labels]
    minimum_height_cm = 4 * 17 * 2.54 / 72 * 1.4
    assert all(b - a >= minimum_height_cm for a, b in zip(ys, ys[1:], strict=False))


@pytest.mark.parametrize("line_count", [8, 24])
def test_first_and_last_tall_trial_labels_stay_inside_page(line_count):
    layout = build_event_raster_layout(
        _plan(200, suffix="\nRegion" * (line_count - 1)), "Time (s)", "Trial"
    )
    half_label_cm = line_count * 17 * 2.54 / 72 * 1.4 / 2
    for _text, _ordinal, _right, y_percent in layout.trial_labels:
        center_cm = y_percent / 100 * layout.style.page_height_cm
        assert center_cm - half_label_cm >= 0.4
        assert center_cm + half_label_cm <= layout.style.page_height_cm - 0.4


def test_conditions_receive_outside_borderless_legend_space_in_source_order():
    plan = _plan(40, conditions=8)
    layout = build_event_raster_layout(plan, "Time (s)", "Trial")
    assert tuple(item[0] for item in layout.condition_labels) == plan.condition_order
    assert len(layout.condition_labels) == 8
    assert all(0 < y < layout.style.layer_top_percent for _, _left, y in layout.condition_labels)
    assert layout.style.axis_title_size_pt == 20


def test_explicit_long_titles_expand_physical_plot_not_font_scaling():
    short = build_event_raster_layout(_plan(), "Time (s)", "Trial")
    long = build_event_raster_layout(_plan(), "W" * 100 + " (s)", "W" * 100)
    assert long.style.page_width_cm > short.style.page_width_cm
    assert long.style.page_height_cm > short.style.page_height_cm
    assert long.style.axis_title_size_pt == short.style.axis_title_size_pt
    assert long.x_range == short.x_range and long.y_range == short.y_range


def test_one_trial_and_inventory_only_conditions_keep_their_semantics():
    single = build_event_raster_layout(_plan(1, conditions=1), "Time (s)", "Trial")
    assert single.y_range == (1.5, 0.5)
    assert len(single.trial_labels) == 1
    frame = pd.DataFrame({"Time": [0.1, None], "Trial": ["A", "B"], "Condition": ["Events", "No events"]})
    plan = build_event_raster_plan(frame, event_time_column="Time", trial_column="Trial",
                                   condition_column="Condition", time_unit="s")
    layout = build_event_raster_layout(plan, "Time (s)", "Trial")
    assert tuple(item[0] for item in layout.condition_labels) == ("Events", "No events")
    assert plan.empty_trial_ids == ("B",)
    assert layout.y_range == (2.5, 0.5)
