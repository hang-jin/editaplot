"""Display contracts for supplied physical time-frequency cells, not signal analysis."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/src"))
sys.path.insert(0, str(ROOT / "tools"))


def source():
    return pd.DataFrame({
        "Time (s)": [-0.2, 0, 0.2] * 2,
        "Frequency (Hz)": [20.0] * 3 + [10.0] * 3,
        "Power (dB)": [-2.0, 1.0, 6.0, -0.5, 2.0, 3.0],
        "QC note": ["retained, not drawn"] * 6,
    }, index=[9, 9, 3, 2, -1, 5])


def build(frame=None, **overrides):
    assert importlib.util.find_spec("origin_sciplot.time_frequency") is not None
    function = importlib.import_module("origin_sciplot.time_frequency").build_time_frequency_plan
    options = dict(
        time_column="Time (s)", frequency_column="Frequency (Hz)", value_column="Power (dB)",
        time_unit="s", frequency_unit="Hz", value_unit="dB", color_semantics="sequential",
    )
    options.update(overrides)
    return function(source() if frame is None else frame, **options)


def test_negative_db_values_do_not_imply_baseline_change_or_normalization():
    frame = source()
    original = frame.copy(deep=True)
    plan = build(frame)
    assert plan.grid.values == ((-2.0, 1.0, 6.0), (-0.5, 2.0, 3.0))
    assert plan.grid.source_rows == ((0, 1, 2), (3, 4, 5))
    assert plan.color_limits == (-2.0, 6.0)
    assert plan.color_semantics == "sequential" and plan.color_reference is None
    assert plan.display_transform == "identity"
    assert plan.processing_boundary == "supplied_time_frequency_values_only"
    assert plan.retained_columns == ("QC note",)
    pd.testing.assert_frame_equal(frame, original, check_exact=True)


def test_physical_coordinates_preserve_source_direction_and_full_cell_edges():
    plan = build()
    assert plan.grid.x == (-0.2, 0.0, 0.2)
    assert plan.grid.y == (20.0, 10.0)
    assert plan.x_range == pytest.approx((-0.3, 0.3))
    assert plan.y_range == (25.0, 5.0)


def test_explicit_units_and_chinese_roles_are_preserved_without_conversion():
    frame = source().rename(columns={"Time (s)": "时间", "Frequency (Hz)": "频率", "Power (dB)": "功率"})
    plan = build(
        frame, time_column="时间", frequency_column="频率", value_column="功率",
        time_unit="ms", frequency_unit="kHz", value_unit="a.u.",
    )
    assert (plan.time_unit, plan.frequency_unit, plan.value_unit) == ("ms", "kHz", "a.u.")
    assert plan.grid.x == (-0.2, 0, 0.2)
    assert plan.grid.y == (20, 10)


@pytest.mark.parametrize("reference,want", [(0.0, (-6.0, 6.0)), (1.0, (-4.0, 6.0))])
def test_diverging_color_needs_a_declared_reference_and_symmetric_display_range(reference, want):
    plan = build(color_semantics="diverging", color_reference=reference)
    assert plan.color_reference == reference
    assert plan.color_limits == want
    assert plan.grid.values[0] == (-2, 1, 6)


def test_an_explicit_sequential_range_does_not_change_or_clip_cells():
    plan = build(color_limits=(-3, 7))
    assert plan.color_limits == (-3, 7)
    assert plan.grid.values[1] == (-0.5, 2, 3)


@pytest.mark.parametrize("constant", [0.0, 5.0, -5.0])
def test_constant_values_get_a_finite_display_range_not_new_measurements(constant):
    frame = source()
    frame["Power (dB)"] = constant
    plan = build(frame)
    assert plan.color_limits[0] < constant < plan.color_limits[1]
    assert np.isfinite(plan.color_limits).all()
    assert np.asarray(plan.grid.values).size == 6
    assert (np.asarray(plan.grid.values) == constant).all()


@pytest.mark.parametrize("options", [
    {"time_unit": ""}, {"frequency_unit": None}, {"value_unit": "  "},
    {"color_semantics": "qualitative"}, {"color_semantics": "diverging"},
    {"color_reference": 0.0}, {"color_semantics": "diverging", "color_reference": True},
    {"color_limits": (-1, 6)}, {"color_limits": (-2, 5)}, {"color_limits": (6, -2)},
    {"color_limits": (np.nan, 7)}, {"color_limits": (-3, np.inf)},
    {"color_semantics": "diverging", "color_reference": 0.0, "color_limits": (-3, 7)},
    {"time_column": "missing"}, {"frequency_column": "Time (s)"},
])
def test_ambiguous_declarations_or_clipping_display_ranges_are_rejected(options):
    with pytest.raises(ValueError):
        build(**options)


@pytest.mark.parametrize(
    "fault", ["negative_frequency", "duplicate", "missing_cell", "nonuniform", "nan", "bool"]
)
def test_invalid_physical_grids_are_rejected_without_repair(fault):
    frame = source()
    if fault == "negative_frequency":
        frame["Frequency (Hz)"] -= 30
    elif fault == "duplicate":
        frame = pd.concat([frame, frame.iloc[[0]]])
    elif fault == "missing_cell":
        frame = frame.iloc[:-1].copy()
    elif fault == "nonuniform":
        frame["Time (s)"] = [-0.2, 0, 0.3] * 2
    elif fault == "nan":
        frame.iloc[0, 2] = np.nan
    else:
        frame["Power (dB)"] = frame["Power (dB)"].astype(object)
        frame.iloc[0, 2] = True
    before = frame.copy(deep=True)
    with pytest.raises(ValueError):
        build(frame)
    pd.testing.assert_frame_equal(frame, before, check_exact=True)


def test_unrepresentable_color_reference_gets_a_regular_validation_error():
    with pytest.raises(ValueError, match="finite"):
        build(color_semantics="diverging", color_reference=10**1000)


def test_time_frequency_fixture_is_deterministic_complete_and_explicitly_synthetic():
    import generate_research_data as demos

    generate = getattr(demos, "time_frequency_data", None)
    assert callable(generate), "The new route needs a reproducible source teaching fixture"
    before_rng = np.random.get_state()
    frame, repeated = generate(), generate()
    after_rng = np.random.get_state()
    pd.testing.assert_frame_equal(frame, repeated, check_exact=True)
    np.testing.assert_array_equal(before_rng[1], after_rng[1])
    assert before_rng[0] == after_rng[0] and before_rng[2:] == after_rng[2:]
    assert frame.shape == (9801, 3)
    assert frame.attrs["data_origin"] == "synthetic_teaching_data"
    assert frame.attrs["scientific_claim"] == "none"
    assert frame.attrs["processing"] == "authored_grid_not_a_transform_of_recorded_signals"
    plan = build(frame)
    assert len(plan.grid.x) == 121 and len(plan.grid.y) == 81
    assert plan.x_range[0] < -0.4 and plan.x_range[1] > 1.2
    maximum = frame.loc[frame["Power (dB)"].idxmax()]
    assert abs(maximum["Time (s)"] - 0.3) < 0.025
    assert abs(maximum["Frequency (Hz)"] - 23) < 1
