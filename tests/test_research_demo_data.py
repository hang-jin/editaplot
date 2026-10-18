from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "runtime/src")]

from generate_research_data import (  # noqa: E402
    event_raster_data,
    event_response_data,
    flim_phasor_data,
    signal_stack_data,
    time_frequency_data,
)
from origin_sciplot.event_raster import build_event_raster_plan  # noqa: E402
from origin_sciplot.event_response import build_event_response_plan  # noqa: E402
from origin_sciplot.flim_phasor import build_phasor_plan  # noqa: E402
from origin_sciplot.signal_stack import build_signal_stack_plan  # noqa: E402

GENERATORS = (
    flim_phasor_data, signal_stack_data, event_response_data, event_raster_data, time_frequency_data,
)


@pytest.mark.parametrize("generate", GENERATORS)
def test_generators_are_deterministic_synthetic_and_do_not_change_global_rng(generate) -> None:
    before = np.random.get_state()
    first, second = generate(), generate()
    after = np.random.get_state()

    pd.testing.assert_frame_equal(first, second, check_exact=True)
    assert first.attrs["data_origin"] == "synthetic_teaching_data"
    assert first.attrs["scientific_claim"] == "none"
    assert before[0] == after[0]
    np.testing.assert_array_equal(before[1], after[1])
    assert before[2:] == after[2:]


def test_phasor_example_has_three_explicit_source_bound_clouds() -> None:
    frame = flim_phasor_data()
    original = frame.copy(deep=True)
    assert list(frame.columns) == ["G", "S", "Group"]
    assert frame.shape == (540, 3)
    assert frame.groupby("Group", sort=False).size().tolist() == [180, 180, 180]
    plan = build_phasor_plan(frame, g_column="G", s_column="S", group_column="Group")
    assert plan.group_order == tuple(frame["Group"].drop_duplicates())
    assert sum(len(rows) for _, rows in plan.group_rows) == len(frame)
    pd.testing.assert_frame_equal(frame, original)


def test_signal_example_has_eight_increasing_time_grids_and_a_common_short_event() -> None:
    frame = signal_stack_data()
    assert list(frame.columns) == ["Time (s)", "Channel", "Amplitude (uV)"]
    assert frame.shape == (8008, 3)
    for _, rows in frame.groupby("Channel", sort=False):
        assert len(rows) == 1001
        assert rows["Time (s)"].iloc[0] == 0 and rows["Time (s)"].iloc[-1] == 4
        assert np.all(np.diff(rows["Time (s)"]) > 0)
        event = rows.loc[rows["Time (s)"].between(1.42, 1.65), "Amplitude (uV)"]
        baseline = rows.loc[rows["Time (s)"].between(0.2, 1.0), "Amplitude (uV)"]
        assert event.abs().max() > baseline.abs().max()
    plan = build_signal_stack_plan(
        frame, time_column="Time (s)", value_column="Amplitude (uV)", channel_column="Channel",
        time_unit="s", value_unit="uV",
    )
    assert len(plan.channel_order) == 8
    assert sum(len(rows) for _, rows in plan.channel_rows) == len(frame)


def test_event_responses_have_declared_asymmetric_illustrative_intervals_not_ci() -> None:
    frame = event_response_data()
    assert list(frame.columns) == ["Time (s)", "Condition", "Mean (uV)", "Lower (uV)", "Upper (uV)"]
    assert frame.shape == (802, 5)
    assert frame.attrs["interval_label"] == "Illustrative interval (not CI)"
    assert (frame["Lower (uV)"] < frame["Mean (uV)"]).all()
    assert (frame["Mean (uV)"] < frame["Upper (uV)"]).all()
    assert not np.allclose(frame["Mean (uV)"] - frame["Lower (uV)"],
                           frame["Upper (uV)"] - frame["Mean (uV)"])
    for _, rows in frame.groupby("Condition", sort=False):
        assert len(rows) == 401
        assert rows["Time (s)"].iloc[0] == pytest.approx(-0.2)
        assert rows["Time (s)"].iloc[-1] == pytest.approx(0.8)
        assert np.all(np.diff(rows["Time (s)"]) > 0)
    plan = build_event_response_plan(
        frame, time_column="Time (s)", mean_column="Mean (uV)", lower_column="Lower (uV)",
        upper_column="Upper (uV)", condition_column="Condition", time_unit="s", response_unit="uV",
        interval_label=frame.attrs["interval_label"],
    )
    assert plan.zero_time_visible
    assert sum(len(rows) for _, rows in plan.condition_rows) == len(frame)


def test_raster_contains_40_explicit_trials_with_empty_inventory_not_zero_events() -> None:
    frame = event_raster_data()
    assert list(frame.columns) == ["Time (s)", "Trial", "Condition"]
    assert frame["Trial"].nunique() == 40 and frame["Condition"].nunique() == 2
    plan = build_event_raster_plan(
        frame, event_time_column="Time (s)", trial_column="Trial", condition_column="Condition",
        time_unit="s",
    )
    assert len(plan.empty_trial_ids) == len(plan.inventory_rows) == 4
    assert len(plan.event_rows) == frame["Time (s)"].notna().sum()
    assert len(plan.event_rows) + len(plan.inventory_rows) == len(frame)
    assert (frame.loc[frame["Time (s)"].notna(), "Time (s)"] != 0).all()
    assert frame.loc[frame["Time (s)"].notna(), "Time (s)"].between(-0.2, 0.8).all()
    for trial, rows in frame.groupby("Trial", sort=False):
        if trial in plan.empty_trial_ids:
            assert len(rows) == 1 and rows["Time (s)"].isna().all()
        else:
            assert rows["Time (s)"].notna().all()
            assert np.all(np.diff(rows["Time (s)"]) > 0)


@pytest.mark.parametrize("generate", GENERATORS)
def test_examples_round_trip_only_through_explicit_test_output(tmp_path: Path, generate) -> None:
    source = generate()
    path = tmp_path / f"{generate.__name__}.csv"
    source.to_csv(path, index=False, float_format="%.12g")
    restored = pd.read_csv(path)
    pd.testing.assert_frame_equal(restored, source, check_exact=False, rtol=1e-10, atol=1e-10)


def test_import_and_pure_generation_do_not_create_files_or_import_origin(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    before_modules = set(sys.modules)
    spec = importlib.util.spec_from_file_location(
        "research_data_pure_import", ROOT / "tools/generate_research_data.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in (
        "flim_phasor_data", "signal_stack_data", "event_response_data", "event_raster_data",
        "time_frequency_data",
    ):
        getattr(module, name)()
    assert list(tmp_path.iterdir()) == []
    assert not {"originpro", "OriginExt"} & (set(sys.modules) - before_modules)
