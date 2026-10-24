from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/src"))

from origin_sciplot.event_response import EventResponsePlan, build_event_response_plan  # noqa: E402


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Time": [-2.0, -1.0, 0.0, 1.0],
            "Mean": [0.0, 0.3, 0.8, 1.2],
            "Lower": [-0.2, -0.1, 0.5, 1.0],
            "Upper": [0.4, 0.8, 1.0, 1.7],
            "Condition": ["B", "A", "B", "A"],
            "Unused": [9, 8, 7, 6],
        },
        index=[20, 4, 20, 9],
    )


def _plan(frame: pd.DataFrame, **overrides) -> EventResponsePlan:
    arguments = {
        "time_column": "Time",
        "mean_column": "Mean",
        "lower_column": "Lower",
        "upper_column": "Upper",
        "condition_column": "Condition",
        "time_unit": "ms",
        "response_unit": "µV",
        "interval_label": "95% CI supplied upstream",
    }
    arguments.update(overrides)
    return build_event_response_plan(frame, **arguments)


def test_asymmetric_intervals_source_order_and_positional_rows_are_preserved():
    frame = _frame()
    before = frame.copy(deep=True)

    plan = _plan(frame)

    pd.testing.assert_frame_equal(frame, before)
    assert plan.condition_order == ("B", "A")
    assert plan.condition_rows == (("B", (0, 2)), ("A", (1, 3)))
    assert (
        plan.time_column, plan.mean_column, plan.lower_column,
        plan.upper_column, plan.condition_column,
    ) == ("Time", "Mean", "Lower", "Upper", "Condition")
    assert plan.x_range == pytest.approx((-2.15, 1.15))
    assert plan.y_range == pytest.approx((-0.295, 1.795))
    assert plan.zero_time == 0.0
    assert plan.zero_time_visible is True
    assert plan.reference_kind == "declared_event_time_origin"
    assert plan.axis_include_zero is True
    assert not {"times", "means", "values", "points", "lower_values", "upper_values"} & {
        field.name for field in fields(plan)
    }
    with pytest.raises(FrozenInstanceError):
        plan.interval_label = "SEM"  # type: ignore[misc]


@pytest.mark.parametrize("interval_label", ["SD", "SEM", "95% CI", "  上游提供的不对称区间  "])
def test_units_and_interval_definition_are_preserved_verbatim(interval_label):
    plan = _plan(_frame(), interval_label=interval_label, time_unit=" ms ", response_unit="ΔF/F (%)")

    assert plan.interval_label == interval_label
    assert plan.time_unit == " ms "
    assert plan.response_unit == "ΔF/F (%)"


@pytest.mark.parametrize("argument", ["interval_label", "time_unit", "response_unit"])
@pytest.mark.parametrize("bad", [None, "", " \t ", 123])
def test_interval_definition_and_units_must_be_nonempty_strings(argument, bad):
    with pytest.raises(ValueError, match=argument):
        _plan(_frame(), **{argument: bad})


@pytest.mark.parametrize("column", ["Time", "Mean", "Lower", "Upper"])
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf, True, np.bool_(False), 2 + 0j, "invalid"])
def test_rejects_missing_nonfinite_boolean_or_complex_values(column, bad):
    frame = _frame()
    frame[column] = frame[column].astype(object)
    frame.iloc[0, frame.columns.get_loc(column)] = bad
    with pytest.raises(ValueError, match=column):
        _plan(frame)


@pytest.mark.parametrize("column,new_value", [("Lower", 0.1), ("Upper", -0.1)])
def test_mean_must_lie_within_each_supplied_interval(column, new_value):
    frame = _frame()
    frame.iloc[0, frame.columns.get_loc(column)] = new_value
    with pytest.raises(ValueError, match="Lower.*Mean.*Upper"):
        _plan(frame)


@pytest.mark.parametrize("times", [[0.0, -1.0, 0.0, 1.0], [1.0, -1.0, 0.0, 1.0]])
def test_rejects_duplicate_or_decreasing_times_within_condition(times):
    frame = _frame()
    frame["Time"] = times
    with pytest.raises(ValueError, match="strictly increasing"):
        _plan(frame)


@pytest.mark.parametrize("bad", [None, np.nan, "", " \n ", ["A"]])
def test_condition_labels_must_be_nonempty_scalars(bad):
    frame = _frame()
    frame["Condition"] = pd.Series([bad, "A", "B", "A"], index=frame.index, dtype=object)
    with pytest.raises(ValueError, match="Condition"):
        _plan(frame)


def test_numeric_and_text_condition_labels_are_not_silently_merged():
    frame = _frame()
    frame["Condition"] = [1, "1", 1, "1"]
    with pytest.raises(ValueError, match="ambiguous Condition"):
        _plan(frame)


def test_each_condition_requires_two_observations():
    frame = _frame().iloc[:3]
    with pytest.raises(ValueError, match="at least two"):
        _plan(frame)


def test_conditions_can_have_different_irregular_sampling_without_interpolation():
    frame = pd.DataFrame(
        {
            "Time": [-5.0, -2.0, -1.0, 0.7, 9.0],
            "Mean": [0.2] * 5,
            "Lower": [-0.1] * 5,
            "Upper": [0.7] * 5,
            "Condition": [" B ", "A", " B ", "A", " B "],
        },
        index=[8, 3, 8, 1, 100],
    )
    before = frame.copy(deep=True)
    plan = _plan(frame)

    assert plan.condition_order == (" B ", "A")
    assert plan.condition_rows == ((" B ", (0, 2, 4)), ("A", (1, 3)))
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize("condition_count", [1, 8, 9])
def test_condition_count_limits(condition_count):
    frame = pd.DataFrame(
        {
            "Time": [-1.0, 1.0] * condition_count,
            "Mean": [0.0, 0.5] * condition_count,
            "Lower": [-0.2, 0.1] * condition_count,
            "Upper": [0.1, 0.9] * condition_count,
            "Condition": [f"C{n}" for n in range(condition_count) for _ in range(2)],
        }
    )
    if condition_count > 8:
        with pytest.raises(ValueError, match="1.?8"):
            _plan(frame)
    else:
        assert len(_plan(frame).condition_order) == condition_count


@pytest.mark.parametrize("times,bounds", [([10, 11, 12, 15], (9.75, 15.25)),
                                       ([-15, -12, -11, -10], (-15.25, -9.75))])
def test_time_domain_does_not_expand_to_unobserved_event_origin(times, bounds):
    frame = _frame()
    frame["Time"] = times
    plan = _plan(frame)

    assert plan.x_range == pytest.approx(bounds)
    assert plan.zero_time_visible is False
    assert plan.zero_time == 0.0


def test_padding_crossing_zero_does_not_claim_observed_event_coverage():
    frame = _frame()
    frame["Time"] = [0.01, 0.02, 3.0, 4.0]
    plan = _plan(frame)
    assert plan.x_range[0] < 0
    assert plan.zero_time_visible is False


def test_zero_response_constant_guard_and_positive_axis_zero_choice():
    frame = _frame()
    frame[["Mean", "Lower", "Upper"]] = 0.0
    assert _plan(frame).y_range == (-1.0, 1.0)
    frame[["Mean", "Lower", "Upper"]] = 2.0
    assert _plan(frame).y_range == pytest.approx((-0.1, 2.1))


def test_explicit_columns_must_be_distinct_present_and_unambiguous():
    frame = _frame()
    with pytest.raises(ValueError, match="distinct"):
        _plan(frame, lower_column="Mean")
    with pytest.raises(ValueError, match="Missing"):
        _plan(frame.drop(columns="Lower"))
    with pytest.raises(ValueError, match="ambiguous"):
        _plan(pd.concat([frame, frame[["Mean"]]], axis=1))
    with pytest.raises(ValueError, match="column"):
        _plan(frame, mean_column=" ")
    with pytest.raises(ValueError, match="at least"):
        _plan(frame.iloc[:0])


def test_unrepresentable_padded_bounds_fail_instead_of_becoming_infinite():
    frame = _frame()
    frame["Lower"] = -1.75e308
    frame["Mean"] = 0.0
    frame["Upper"] = 1.75e308
    with pytest.raises(ValueError, match="display bounds"):
        _plan(frame)
