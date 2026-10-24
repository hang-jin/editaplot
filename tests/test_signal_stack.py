from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/src"))

from origin_sciplot.signal_stack import SignalStackPlan, build_signal_stack_plan  # noqa: E402


def _plan(frame: pd.DataFrame, **options: str) -> SignalStackPlan:
    return build_signal_stack_plan(
        frame,
        **{"time_column": "Time", "value_column": "Value", "channel_column": "Channel",
           "time_unit": "s", "value_unit": "µV", **options},
    )


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"Time": [0.0, 0.0, 0.5, 0.4, 1.0, 0.8],
                         "Value": [-2.0, -1.0, 2.0, 1.0, 0.0, 0.5],
                         "Channel": [" Cz ", "Fp1", " Cz ", "Fp1", " Cz ", "Fp1"],
                         "Unused": [9, 8, 7, 6, 5, 4]}, index=[90, 1, 90, -1, 2, 2])


def test_source_identity_channel_spelling_order_and_positional_rows_are_preserved() -> None:
    frame = _frame()
    original = frame.copy(deep=True)

    plan = _plan(frame)

    pd.testing.assert_frame_equal(frame, original)
    assert plan.channel_order == (" Cz ", "Fp1")
    assert plan.channel_rows == ((" Cz ", (0, 2, 4)), ("Fp1", (1, 3, 5)))
    assert (plan.time_column, plan.value_column, plan.channel_column) == ("Time", "Value", "Channel")
    assert (plan.time_unit, plan.value_unit) == ("s", "µV")
    assert not {"time_values", "values", "points", "display_values"} & {f.name for f in fields(plan)}
    with pytest.raises(FrozenInstanceError):
        plan.value_column = "other"  # type: ignore[misc]


def test_channels_share_one_amplitude_scale_and_only_add_offsets() -> None:
    frame = _frame()
    plan = _plan(frame)

    assert plan.source_value_range == (-2.0, 2.0)
    assert plan.offset_step == 5.0
    assert plan.offsets == ((" Cz ", 5.0), ("Fp1", 0.0))
    assert plan.display_transform == "channel_offset_only"
    assert plan.display_y_range == (-2.0, 7.0)
    for channel, positions in plan.channel_rows:
        source = frame.iloc[list(positions)]["Value"].to_numpy()
        display = source + dict(plan.offsets)[channel]
        assert np.diff(display) == pytest.approx(np.diff(source))
        assert all(plan.display_y_range[0] <= v <= plan.display_y_range[1] for v in display)


def test_different_sampling_times_are_allowed_without_alignment_or_interpolation() -> None:
    frame = pd.DataFrame({"Time": [0, 2, 3, 1, 5], "Value": [2, -1, 9, 0, 3],
                          "Channel": ["A", "A", "A", "B", "B"]})
    plan = _plan(frame)
    assert plan.time_range == (0.0, 5.0)
    assert plan.channel_rows == (("A", (0, 1, 2)), ("B", (3, 4)))
    assert sum(len(rows) for _, rows in plan.channel_rows) == len(frame)


@pytest.mark.parametrize("times", [[0, 0], [1, 0], [0, -1]])
def test_rejects_duplicate_or_decreasing_times_instead_of_sorting(times: list[int]) -> None:
    frame = pd.DataFrame({"Time": times, "Value": [1, 2], "Channel": ["A", "A"]})
    with pytest.raises(ValueError, match="strictly increasing"):
        _plan(frame)


@pytest.mark.parametrize("value,step,scale", [(0.0, 0.25, 0.5), (8.0, 2.0, 2.0), (-8.0, 2.0, 2.0)])
def test_constant_channels_use_explicit_finite_fallback(value: float, step: float, scale: float) -> None:
    frame = pd.DataFrame({"Time": [0, 1, 0, 1], "Value": [value] * 4,
                          "Channel": ["A", "A", "B", "B"]})
    plan = _plan(frame)
    assert plan.source_value_range == (value, value)
    assert plan.offset_step == step
    assert plan.offsets == (("A", step), ("B", 0.0))
    assert plan.amplitude_scale_length == scale
    assert plan.amplitude_scale_kind == "display_unit_length_not_statistical_estimate"
    assert all(np.isfinite(v) for v in (*plan.display_y_range, plan.offset_step))


def test_constant_single_channel_has_nondegenerate_display_bounds() -> None:
    plan = _plan(pd.DataFrame({"Time": [0, 1], "Value": [0, 0], "Channel": ["A", "A"]}))
    assert plan.offsets == (("A", 0.0),)
    assert plan.display_y_range[0] < 0 < plan.display_y_range[1]


@pytest.mark.parametrize("span,scale", [(4.0, 1.0), (6.0, 2.0), (11.0, 5.0), (0.11, 0.05)])
def test_amplitude_reference_uses_nice_125_unit_length(span: float, scale: float) -> None:
    plan = _plan(pd.DataFrame({"Time": [0, 1], "Value": [0, span], "Channel": ["A", "A"]}))
    assert plan.amplitude_scale_length == pytest.approx(scale)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf, True, False, 1 + 2j, "not numeric", None])
@pytest.mark.parametrize("column", ["Time", "Value"])
def test_rejects_nonfinite_nonreal_or_boolean_values(column: str, bad: object) -> None:
    frame = pd.DataFrame({"Time": [0, 1], "Value": [1, 2], "Channel": ["A", "A"]})
    frame[column] = [bad, 2]
    with pytest.raises(ValueError, match=column):
        _plan(frame)


@pytest.mark.parametrize("bad", [None, np.nan, "", " \t ", ["A"]])
def test_rejects_missing_or_nonscalar_channel_labels(bad: object) -> None:
    frame = pd.DataFrame({"Time": [0, 1], "Value": [1, 2], "Channel": [bad, bad]})
    with pytest.raises(ValueError, match="Channel"):
        _plan(frame)


def test_rejects_distinct_source_labels_that_share_one_display_name() -> None:
    frame = pd.DataFrame({"Time": [0, 1, 0, 1], "Value": [0, 1, 2, 3],
                          "Channel": [1, 1, "1", "1"]})
    with pytest.raises(ValueError, match="ambiguous"):
        _plan(frame)


def test_numeric_channel_labels_become_unambiguous_display_strings() -> None:
    frame = pd.DataFrame({"Time": [0, 1, 0, 1], "Value": [0, 1, 2, 3],
                          "Channel": [2, 2, 1, 1]})
    assert _plan(frame).channel_order == ("2", "1")


@pytest.mark.parametrize("count", [1, 16])
def test_supports_one_through_sixteen_channels(count: int) -> None:
    frame = pd.DataFrame({"Time": [0, 1] * count, "Value": [-1, 1] * count,
                          "Channel": [f"Ch{i}" for i in range(count) for _ in range(2)]})
    plan = _plan(frame)
    assert len(plan.channel_order) == count
    assert len(plan.offsets) == count


def test_rejects_empty_table_too_many_channels_or_singleton_channel() -> None:
    with pytest.raises(ValueError, match="observation"):
        _plan(pd.DataFrame(columns=["Time", "Value", "Channel"]))
    frame = pd.DataFrame({"Time": [0, 1] * 17, "Value": [0, 1] * 17,
                          "Channel": [f"Ch{i}" for i in range(17) for _ in range(2)]})
    with pytest.raises(ValueError, match="1.?16"):
        _plan(frame)
    with pytest.raises(ValueError, match="at least two"):
        _plan(pd.DataFrame({"Time": [0, 1, 0], "Value": [0, 1, 3], "Channel": ["A", "A", "B"]}))


@pytest.mark.parametrize("unit", ["", " \t ", None, 1])
@pytest.mark.parametrize("name", ["time_unit", "value_unit"])
def test_requires_explicit_unit_strings_without_guessing(name: str, unit: object) -> None:
    with pytest.raises(ValueError, match="unit"):
        _plan(_frame(), **{name: unit})  # type: ignore[arg-type]


def test_does_not_convert_units_or_trim_source_unit_text() -> None:
    plan = _plan(_frame(), time_unit=" milliseconds ", value_unit="mV")
    assert plan.time_unit == " milliseconds "
    assert plan.value_unit == "mV"
    assert plan.time_range == (0.0, 1.0)
    assert plan.source_value_range == (-2.0, 2.0)


def test_requires_three_distinct_existing_unambiguous_column_names() -> None:
    frame = _frame()
    with pytest.raises(ValueError, match="distinct"):
        _plan(frame, time_column="Value")
    with pytest.raises(ValueError, match="Missing"):
        _plan(frame, time_column="Absent")
    with pytest.raises(ValueError, match="explicit"):
        _plan(frame, value_column="")
    duplicated = pd.concat([frame, frame[["Value"]]], axis=1)
    with pytest.raises(ValueError, match="duplicated"):
        _plan(duplicated)


def test_extreme_observations_remain_in_source_rows_and_display_bounds() -> None:
    frame = pd.DataFrame({"Time": [0, 1, 2, 0, 1], "Value": [-1e100, 0, 1e100, -1, 1],
                          "Channel": ["A", "A", "A", "B", "B"]})
    original = frame.copy(deep=True)
    plan = _plan(frame)
    assert plan.source_value_range == (-1e100, 1e100)
    assert plan.channel_rows[0] == ("A", (0, 1, 2))
    assert plan.offset_step == pytest.approx(2.5e100)
    pd.testing.assert_frame_equal(frame, original)


def test_overflowing_display_range_is_rejected_not_clipped() -> None:
    frame = pd.DataFrame({"Time": [0, 1], "Value": [-1e308, 1e308], "Channel": ["A", "A"]})
    with pytest.raises(ValueError, match="finite"):
        _plan(frame)
