"""Display-only event raster plans with explicit, source-bound trial inventory.

Blank event times declare trial inventory; no trial is inferred from an absent
row. Events must already have been detected upstream. This module does not
detect spikes, calculate PSTHs or rates, or change the source DataFrame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EventRasterPlan:
    event_time_column: str
    trial_column: str
    condition_column: str
    time_unit: str
    event_rows: tuple[int, ...]
    inventory_rows: tuple[int, ...]
    empty_trial_ids: tuple[str, ...]
    trial_order: tuple[str, ...]
    condition_order: tuple[str, ...]
    trial_conditions: tuple[tuple[str, str], ...]
    row_trial_positions: tuple[tuple[int, int], ...]
    x_range: tuple[float, float]
    y_range: tuple[float, float]


def _label(value: object, column: str, originals: dict[str, object]) -> str:
    if not pd.api.types.is_scalar(value) or pd.isna(value) or not str(value).strip():
        raise ValueError(f"{column}: labels must be nonempty scalar values.")
    label = str(value)
    if label in originals and originals[label] != value:
        raise ValueError(f"{column}: ambiguous values share display label {label!r}.")
    originals[label] = value
    return label


def _event_time(value: object, column: str) -> float | None:
    if not pd.api.types.is_scalar(value) or isinstance(value, (bool, np.bool_, complex, np.complexfloating)):
        raise ValueError(f"{column}: event times must be real numeric values or blank inventory entries.")
    if pd.isna(value) or (isinstance(value, str) and not value.strip()):
        return None
    try:
        time = float(pd.to_numeric(value, errors="raise"))
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{column}: nonempty event times must be finite real numeric values.") from error
    if not math.isfinite(time):
        raise ValueError(f"{column}: nonempty event times must be finite real numeric values.")
    return time


def _time_bounds(lower: float, upper: float) -> tuple[float, float]:
    # A constant-time table has no observed span; use a documented one-unit or
    # magnitude-based guard instead of collapsing the X axis to one value.
    padding = max(abs(lower), 1.0) * 0.05 if lower == upper else upper * 0.05 - lower * 0.05
    bounds = (lower - padding, upper + padding)
    if not all(math.isfinite(value) for value in bounds) or bounds[0] >= bounds[1]:
        raise ValueError("Event times are too large for finite 5% padded display bounds.")
    return bounds


def build_event_raster_plan(
    frame: pd.DataFrame,
    *,
    event_time_column: str,
    trial_column: str,
    condition_column: str,
    time_unit: str,
) -> EventRasterPlan:
    """Freeze source positions without copying event values into the plan.

    All row references are zero-based ``frame.iloc`` positions. Trial positions
    are 1-based Y coordinates in first-appearance order. One blank-time row per
    trial may declare inventory, including for trials with recorded events.
    ``empty_trial_ids`` contains only explicitly inventoried trials with no
    events. Inventory rows are retained but never drawn as events at time zero.
    """
    if not isinstance(time_unit, str) or not time_unit.strip():
        raise ValueError("time_unit must be explicitly supplied and nonempty.")
    columns = (event_time_column, trial_column, condition_column)
    if any(not isinstance(column, str) or not column.strip() for column in columns):
        raise ValueError("Provide explicit nonempty Time, Trial, and Condition column names.")
    if len(set(columns)) != 3:
        raise ValueError("Time, Trial, and Condition require three distinct source columns.")
    for column in columns:
        matches = sum(name == column for name in frame.columns)
        if matches == 0:
            raise ValueError(f"Missing source column: {column}.")
        if matches != 1:
            raise ValueError(f"Source column {column} is ambiguous because its name is duplicated.")

    event_rows: list[int] = []
    inventory_rows: list[int] = []
    row_positions: list[tuple[int, int]] = []
    trials: dict[str, str] = {}
    trial_positions: dict[str, int] = {}
    original_trials: dict[str, object] = {}
    original_conditions: dict[str, object] = {}
    inventory_trials: set[str] = set()
    event_trials: set[str] = set()
    seen_events: set[tuple[str, float]] = set()
    lower, upper = math.inf, -math.inf

    for row, (raw_time, raw_trial, raw_condition) in enumerate(
        frame.loc[:, list(columns)].itertuples(index=False, name=None)
    ):
        trial = _label(raw_trial, trial_column, original_trials)
        condition = _label(raw_condition, condition_column, original_conditions)
        if trial in trials and trials[trial] != condition:
            raise ValueError(f"{trial_column}: trial {trial!r} must belong to one condition only.")
        if trial not in trials:
            trials[trial] = condition
            trial_positions[trial] = len(trials)
        row_positions.append((row, trial_positions[trial]))

        time = _event_time(raw_time, event_time_column)
        if time is None:
            if trial in inventory_trials:
                raise ValueError(f"{trial_column}: ambiguous duplicate inventory row for trial {trial!r}.")
            inventory_trials.add(trial)
            inventory_rows.append(row)
            continue
        event = (trial, time)
        if event in seen_events:
            raise ValueError(f"{event_time_column}: ambiguous duplicate event for trial {trial!r} at {time}.")
        seen_events.add(event)
        event_trials.add(trial)
        event_rows.append(row)
        lower, upper = min(lower, time), max(upper, time)

    if not event_rows:
        raise ValueError("An event raster requires at least one finite event.")
    if not 1 <= len(original_conditions) <= 8:
        raise ValueError("An event raster supports 1–8 explicit conditions.")
    if len(trials) > 200:
        raise ValueError("An event raster supports at most 200 explicit trials.")

    return EventRasterPlan(
        event_time_column=event_time_column,
        trial_column=trial_column,
        condition_column=condition_column,
        time_unit=time_unit.strip(),
        event_rows=tuple(event_rows),
        inventory_rows=tuple(inventory_rows),
        empty_trial_ids=tuple(
            trial for trial in trials if trial in inventory_trials and trial not in event_trials
        ),
        trial_order=tuple(trials),
        condition_order=tuple(original_conditions),
        trial_conditions=tuple(trials.items()),
        row_trial_positions=tuple(row_positions),
        x_range=_time_bounds(lower, upper),
        y_range=(0.5, len(trials) + 0.5),
    )
