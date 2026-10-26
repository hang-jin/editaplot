"""Display-only planning for upstream event-aligned means and intervals.

This module does not estimate a mean, uncertainty, baseline, peak, or treatment
effect. Interval labels and physical units are declarations from the caller.
The immutable plan references source rows by iloc position and never stores or
rewrites the observations. Irregular sampling is retained without interpolation
or an inferred gap-detection rule.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EventResponsePlan:
    time_column: str
    mean_column: str
    lower_column: str
    upper_column: str
    condition_column: str
    time_unit: str
    response_unit: str
    interval_label: str
    condition_order: tuple[str, ...]
    condition_rows: tuple[tuple[str, tuple[int, ...]], ...]
    x_range: tuple[float, float]
    y_range: tuple[float, float]
    zero_time: float
    reference_kind: str
    zero_time_visible: bool
    axis_include_zero: bool


def validate_event_response_titles(plan: EventResponsePlan, x_title: str, y_title: str) -> None:
    """Cosmetic wording cannot relabel a supplied physical unit without conversion."""
    for title, unit in ((x_title, plan.time_unit), (y_title, plan.response_unit)):
        if not isinstance(title, str) or not any(
            title.endswith(f"{opening}{unit}{closing}")
            for opening, closing in (("(", ")"), ("[", "]"), ("（", "）"), ("［", "］"))
        ):
            raise ValueError("Event-response axis titles must retain their exact declared unit suffix.")


def _finite_values(frame: pd.DataFrame, column: str) -> np.ndarray:
    series = frame[column]
    if any(isinstance(value, (bool, np.bool_)) for value in series):
        raise ValueError(f"{column}: values must be real numeric values, not booleans.")
    if pd.api.types.is_datetime64_any_dtype(series) or pd.api.types.is_timedelta64_dtype(series):
        raise ValueError(f"{column}: values must be finite real numbers in the declared units.")
    try:
        numeric = pd.to_numeric(series, errors="raise")
        if np.iscomplexobj(numeric):
            raise ValueError("Complex values cannot define event-response coordinates.")
        values = numeric.to_numpy(dtype=float, copy=True)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{column}: values must be finite real numeric values.") from error
    if not np.isfinite(values).all():
        raise ValueError(f"{column}: values must be finite real numeric values.")
    return values


def _padded_range(lower: float, upper: float) -> tuple[float, float]:
    # Multiply before subtraction to avoid overflow in a finite input span.
    padding = upper * 0.05 - lower * 0.05
    if lower == upper:
        padding = max(abs(lower) * 0.05, 1.0)
    bounds = (lower - padding, upper + padding)
    if not all(math.isfinite(value) for value in bounds) or bounds[0] >= bounds[1]:
        raise ValueError("Values are too large for finite 5% padded display bounds.")
    return bounds


def build_event_response_plan(
    frame: pd.DataFrame,
    *,
    time_column: str,
    mean_column: str,
    lower_column: str,
    upper_column: str,
    condition_column: str,
    time_unit: str,
    response_unit: str,
    interval_label: str,
) -> EventResponsePlan:
    """Freeze already calculated responses without sorting or statistical inference.

    Each condition has at least two strictly increasing time coordinates; the
    conditions may be interleaved and sampled differently. Every supplied
    interval must enclose its mean and is allowed to be asymmetric. Units and
    ``interval_label`` are preserved verbatim; SD, SEM and CI are not converted.

    Y includes all supplied intervals and zero as an explicit display choice.
    X pads the observed time domain by 5% without extending it to the event
    origin. ``zero_time_visible`` is based on the unpadded source domain: an
    incidental crossing of zero by axis padding does not imply time coverage.
    A zero-time reference is not an observed response or an interpolated row.
    """
    columns = (time_column, mean_column, lower_column, upper_column, condition_column)
    if any(not isinstance(column, str) or not column.strip() for column in columns):
        raise ValueError("Provide five explicit nonempty source column names.")
    if len(set(columns)) != 5:
        raise ValueError("Time, Mean, Lower, Upper and Condition require five distinct source columns.")
    for column in columns:
        matches = sum(name == column for name in frame.columns)
        if matches == 0:
            raise ValueError(f"Missing source column: {column}.")
        if matches != 1:
            raise ValueError(f"Source column {column} is ambiguous because its name is duplicated.")
    for name, declaration in (
        ("time_unit", time_unit), ("response_unit", response_unit), ("interval_label", interval_label)
    ):
        if not isinstance(declaration, str) or not declaration.strip():
            raise ValueError(f"{name} must be an explicit nonempty string.")
    if frame.empty:
        raise ValueError("An event-response table needs at least two observations per condition.")

    time = _finite_values(frame, time_column)
    mean = _finite_values(frame, mean_column)
    lower = _finite_values(frame, lower_column)
    upper = _finite_values(frame, upper_column)
    if np.any(lower > mean) or np.any(mean > upper):
        raise ValueError("Every row must satisfy Lower <= Mean <= Upper; intervals are never repaired.")

    rows: dict[str, list[int]] = {}
    original_labels: dict[str, object] = {}
    for position, value in enumerate(frame[condition_column]):
        if not pd.api.types.is_scalar(value) or pd.isna(value) or not str(value).strip():
            raise ValueError(f"{condition_column}: Condition labels must be nonempty scalar values.")
        label = str(value)
        if label in original_labels and original_labels[label] != value:
            raise ValueError(f"{condition_column}: ambiguous Condition values share display label {label!r}.")
        original_labels[label] = value
        rows.setdefault(label, []).append(position)
    if not 1 <= len(rows) <= 8:
        raise ValueError("An event-response plan supports 1–8 explicit conditions.")
    for label, positions in rows.items():
        if len(positions) < 2:
            raise ValueError(f"Condition {label!r} requires at least two observations.")
        if any(time[right] <= time[left] for left, right in zip(positions, positions[1:], strict=False)):
            raise ValueError(f"Time must be unique and strictly increasing within Condition {label!r}.")

    time_lower, time_upper = float(time.min()), float(time.max())
    return EventResponsePlan(
        time_column=time_column,
        mean_column=mean_column,
        lower_column=lower_column,
        upper_column=upper_column,
        condition_column=condition_column,
        time_unit=time_unit,
        response_unit=response_unit,
        interval_label=interval_label,
        condition_order=tuple(rows),
        condition_rows=tuple((label, tuple(positions)) for label, positions in rows.items()),
        x_range=_padded_range(time_lower, time_upper),
        y_range=_padded_range(min(float(lower.min()), 0.0), max(float(upper.max()), 0.0)),
        zero_time=0.0,
        reference_kind="declared_event_time_origin",
        zero_time_visible=time_lower <= 0.0 <= time_upper,
        axis_include_zero=True,
    )
