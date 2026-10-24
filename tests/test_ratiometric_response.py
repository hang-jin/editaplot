from __future__ import annotations

import datetime as dt
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/src"))


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Coordinate": [10.0, 11.0, 12.5, 19.0, 28.0],
            "Condition": [" B ", "A", " B ", "A", " B "],
            "Channel A": [20.0, 30.0, -40.0, 50.0, 60.0],
            "Channel B": [1000.0, 2000.0, 3000.0, -4000.0, 5000.0],
            "Ratio": [0.9, -0.4, 0.7, 0.1, 0.3],
            "Sample ID": ["same", "different", "unpaired", "same", None],
            "Notes": [1, 2, 3, 4, 5],
        },
        index=[40, 3, 40, 9, 1],
    )


def _plan(frame: pd.DataFrame, **overrides):
    from origin_sciplot.ratiometric_response import build_ratiometric_response_plan

    arguments = {
        "x_column": "Coordinate",
        "condition_column": "Condition",
        "numerator_column": "Channel A",
        "denominator_column": "Channel B",
        "ratio_column": "Ratio",
        "x_unit": "nm",
        "numerator_unit": "mV",
        "denominator_unit": "counts",
        "ratio_unit": "dimensionless",
        "ratio_definition": "  externally supplied calibrated Channel A/Channel B response  ",
    }
    arguments.update(overrides)
    return build_ratiometric_response_plan(frame, **arguments)


def test_row_pairs_and_independent_ranges_preserve_irregular_data_and_metadata():
    frame = _frame()
    before = frame.copy(deep=True)

    plan = _plan(frame)

    assert plan.condition_order == (" B ", "A")
    assert plan.condition_rows == ((" B ", (0, 2, 4)), ("A", (1, 3)))
    assert plan.x_range == pytest.approx((9.1, 28.9))
    assert plan.numerator_range == pytest.approx((-45.0, 65.0))
    assert plan.denominator_range == pytest.approx((-4450.0, 5450.0))
    assert plan.ratio_range == pytest.approx((-0.465, 0.965))
    assert (plan.x_column, plan.condition_column, plan.numerator_column,
            plan.denominator_column, plan.ratio_column) == (
        "Coordinate", "Condition", "Channel A", "Channel B", "Ratio"
    )
    assert plan.retained_columns == ("Sample ID", "Notes")
    assert plan.row_pairing == "same_source_row_at_supplied_x_and_condition"
    assert plan.ratio_validation == "upstream_declaration_only"
    pd.testing.assert_frame_equal(frame, before)
    # The supplied ratios are deliberately not A/B. No reconciliation is allowed.
    assert frame["Ratio"].tolist() == [0.9, -0.4, 0.7, 0.1, 0.3]
    with pytest.raises(FrozenInstanceError):
        plan.ratio_definition = "recomputed"


def test_units_and_definition_are_explicit_verbatim_upstream_declarations():
    plan = _plan(
        _frame(), x_unit=" concentration (µM) ", numerator_unit="mV",
        denominator_unit="V", ratio_unit=" mV/V ", ratio_definition="  upstream correction  ",
    )
    assert (plan.x_unit, plan.numerator_unit, plan.denominator_unit, plan.ratio_unit) == (
        " concentration (µM) ", "mV", "V", " mV/V "
    )
    assert plan.ratio_definition == "  upstream correction  "
    assert plan.numerator_range == pytest.approx((-45, 65))
    assert plan.denominator_range == pytest.approx((-4450, 5450))


@pytest.mark.parametrize("argument", [
    "x_unit", "numerator_unit", "denominator_unit", "ratio_unit", "ratio_definition",
])
@pytest.mark.parametrize("bad", [None, "", " \t ", 123, True])
def test_missing_unit_or_ratio_definition_is_not_inferred(argument, bad):
    with pytest.raises(ValueError, match=argument):
        _plan(_frame(), **{argument: bad})


@pytest.mark.parametrize("column", ["Coordinate", "Channel A", "Channel B", "Ratio"])
@pytest.mark.parametrize("bad", [
    np.nan, np.inf, -np.inf, True, np.bool_(False), 2 + 0j,
    "invalid", None, dt.date(2020, 1, 1), dt.datetime(2020, 1, 1),
    dt.timedelta(seconds=2), np.datetime64("2020-01-01"), np.timedelta64(2, "s"),
])
def test_rejects_nonfinite_flags_dates_complex_and_missing_values(column, bad):
    frame = _frame()
    frame[column] = frame[column].astype(object)
    frame.iloc[0, frame.columns.get_loc(column)] = bad
    before = frame.copy(deep=True)
    with pytest.raises(ValueError, match=column):
        _plan(frame)
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize("column", ["Coordinate", "Channel A", "Channel B", "Ratio"])
@pytest.mark.parametrize("values", [pd.date_range("2020-01-01", periods=5),
                                     pd.to_timedelta([1, 2, 3, 4, 5], unit="s")])
def test_rejects_entire_datetime_or_timedelta_columns(column, values):
    frame = _frame()
    frame[column] = values
    with pytest.raises(ValueError, match=column):
        _plan(frame)


@pytest.mark.parametrize("zero", [0, -0.0, "0"])
def test_zero_denominator_is_rejected_without_replacing_supplied_ratio(zero):
    frame = _frame()
    frame["Channel B"] = frame["Channel B"].astype(object)
    frame.iloc[0, frame.columns.get_loc("Channel B")] = zero
    with pytest.raises(ValueError, match="denominator|Denominator"):
        _plan(frame)


def test_finite_channels_need_not_have_a_finite_quotient():
    frame = _frame()
    frame["Channel A"] = 1e200
    frame["Channel B"] = 1e-200
    frame["Ratio"] = 2.0
    plan = _plan(frame)
    assert plan.ratio_range == pytest.approx((1.9, 2.1))
    assert plan.numerator_range == pytest.approx((0.95e200, 1.05e200))


@pytest.mark.parametrize("coordinates", [
    [10, 11, 10, 19, 28], [10, 11, 9, 19, 28], [10, 19, 12.5, 11, 28],
])
def test_duplicate_or_descending_x_is_rejected_within_each_condition(coordinates):
    frame = _frame()
    frame["Coordinate"] = coordinates
    with pytest.raises(ValueError, match="strictly increasing"):
        _plan(frame)


@pytest.mark.parametrize("bad", [None, np.nan, "", " \n ", ["A"]])
def test_condition_requires_explicit_nonempty_scalar_labels(bad):
    frame = _frame()
    frame["Condition"] = pd.Series([bad, "A", " B ", "A", " B "], index=frame.index, dtype=object)
    with pytest.raises(ValueError, match="Condition"):
        _plan(frame)


def test_distinct_numeric_and_text_conditions_are_not_merged_by_display_label():
    frame = _frame()
    frame["Condition"] = [1, "1", 1, "1", 1]
    with pytest.raises(ValueError, match="ambiguous"):
        _plan(frame)


def test_each_condition_needs_two_observations():
    with pytest.raises(ValueError, match="at least two"):
        _plan(_frame().iloc[:3])


@pytest.mark.parametrize("count", [1, 8, 9])
def test_condition_count_bounds(count):
    frame = pd.concat([_frame().iloc[:2]] * count, ignore_index=True)
    frame["Condition"] = [f"C{n}" for n in range(count) for _ in range(2)]
    if count > 8:
        with pytest.raises(ValueError, match="1.?8"):
            _plan(frame)
    else:
        assert len(_plan(frame).condition_order) == count


@pytest.mark.parametrize("role", [
    "x_column", "condition_column", "numerator_column", "denominator_column", "ratio_column",
])
@pytest.mark.parametrize("bad", [None, "", " ", 1])
def test_each_source_role_needs_a_named_column(role, bad):
    with pytest.raises(ValueError, match="column"):
        _plan(_frame(), **{role: bad})


def test_source_columns_are_distinct_present_unambiguous_and_nonempty():
    with pytest.raises(ValueError, match="distinct"):
        _plan(_frame(), ratio_column="Channel A")
    with pytest.raises(ValueError, match="Missing"):
        _plan(_frame().drop(columns="Ratio"))
    frame = _frame()
    with pytest.raises(ValueError, match="ambiguous"):
        _plan(pd.concat([frame, frame[["Ratio"]]], axis=1))
    with pytest.raises(ValueError, match="at least two"):
        _plan(frame.iloc[:0])


def test_zero_and_negative_ratios_and_numerator_are_not_a_physiology_filter():
    frame = _frame()
    frame["Channel A"] = [0, -1, -2, -3, -4]
    frame["Ratio"] = [0, -2, 0, -4, -5]
    before = frame.copy(deep=True)
    plan = _plan(frame)
    assert plan.numerator_range == pytest.approx((-4.2, 0.2))
    assert plan.ratio_range == pytest.approx((-5.25, 0.25))
    pd.testing.assert_frame_equal(frame, before)


def test_all_constant_channels_and_ratio_get_independent_nonzero_display_spans():
    frame = _frame()
    frame["Channel A"] = 0.0
    frame["Channel B"] = 100.0
    frame["Ratio"] = 20.0
    plan = _plan(frame)
    assert plan.numerator_range == (-0.05, 0.05)
    assert plan.denominator_range == (95.0, 105.0)
    assert plan.ratio_range == (19.0, 21.0)


@pytest.mark.parametrize("column", ["Coordinate", "Channel A", "Channel B", "Ratio"])
def test_unrepresentable_display_ranges_fail_explicitly(column):
    frame = _frame()
    frame[column] = [-1.75e308, -1.7e308, 0, 1.7e308, 1.75e308]
    if column == "Channel B":
        frame.iloc[2, frame.columns.get_loc(column)] = 1.0
    with pytest.raises(ValueError, match="display bounds"):
        _plan(frame)
