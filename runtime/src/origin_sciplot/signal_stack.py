"""Freeze a display-only, common-amplitude plan for processed signal channels.

This module does not parse acquisition files, filter, align, resample, center,
normalize, or derive any signal. Source observations stay in the caller's table;
the plan contains zero-based positional row references and explicit offsets.
Native rendering, registration and host validation are handled by the template layer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

DISPLAY_TRANSFORM = "channel_offset_only"
AMPLITUDE_SCALE_KIND = "display_unit_length_not_statistical_estimate"


@dataclass(frozen=True)
class SignalStackPlan:
    time_column: str
    value_column: str
    channel_column: str
    time_unit: str
    value_unit: str
    channel_order: tuple[str, ...]
    channel_rows: tuple[tuple[str, tuple[int, ...]], ...]
    offsets: tuple[tuple[str, float], ...]
    offset_step: float
    source_value_range: tuple[float, float]
    time_range: tuple[float, float]
    display_y_range: tuple[float, float]
    display_transform: str
    amplitude_scale_length: float
    amplitude_scale_kind: str


def _real_values(frame: pd.DataFrame, column: str) -> np.ndarray:
    series = frame[column]
    if any(isinstance(value, (bool, np.bool_)) for value in series):
        raise ValueError(f"{column}: values must be finite real numbers, not booleans.")
    if pd.api.types.is_datetime64_any_dtype(series) or pd.api.types.is_timedelta64_dtype(series):
        raise ValueError(f"{column}: values must be finite real numbers, not datetime objects.")
    try:
        numeric = pd.to_numeric(series, errors="raise")
        if np.iscomplexobj(numeric):
            raise ValueError("Complex values are not real signal samples.")
        values = numeric.to_numpy(dtype=float, copy=True)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{column}: values must be finite real numbers.") from error
    if not np.isfinite(values).all():
        raise ValueError(f"{column}: values must be finite real numbers.")
    return values


def _nice_amplitude_length(target: float) -> float:
    """Round a positive reference length upward to a 1/2/5 power of ten."""
    if not math.isfinite(target) or target <= 0.0:
        raise ValueError("Signal range cannot produce a finite positive amplitude reference.")
    power = 10.0 ** math.floor(math.log10(target))
    if power == 0.0:
        raise ValueError("Signal range is too small for a finite positive amplitude reference.")
    fraction = target / power
    multiplier = next(value for value in (1.0, 2.0, 5.0, 10.0) if fraction <= value)
    length = multiplier * power
    if not math.isfinite(length) or length <= 0.0:
        raise ValueError("Signal range cannot produce a finite positive amplitude reference.")
    return length


def build_signal_stack_plan(
    frame: pd.DataFrame,
    *,
    time_column: str,
    value_column: str,
    channel_column: str,
    time_unit: str,
    value_unit: str,
) -> SignalStackPlan:
    """Validate explicit long-form channels and freeze additive display offsets.

    Channel identities retain source spelling and first appearance. Each
    ``channel_rows`` entry indexes ``frame.iloc``, not DataFrame index labels.
    Times must already be strictly increasing within each channel; different
    channels may have different time samples. Units are display text only.

    All channels use the same unchanged amplitude units. With global source
    span S, offset spacing is 1.25*S. For a constant signal it is
    0.25*max(abs(value), 1). The first channel is displayed highest, so channel
    i adds (N-1-i)*spacing; no channel is centered or rescaled. Display bounds
    conservatively include the entire global source range at every offset.
    A single constant channel receives +/- half a spacing of display padding.

    The amplitude reference is the upward 1/2/5 nice value of S/4. For constant
    input its target uses max(abs(value), 1)/4. This is merely a length in the
    supplied amplitude units, not an error bar or an estimated statistic.
    Any future semantic layer must explicitly disclose this display transform.
    """
    columns = (time_column, value_column, channel_column)
    if any(not isinstance(column, str) or not column.strip() for column in columns):
        raise ValueError("Provide explicit nonempty Time, Value, and Channel column names.")
    if len(set(columns)) != 3:
        raise ValueError("Time, Value, and Channel must use three distinct source columns.")
    for column in columns:
        matches = sum(name == column for name in frame.columns)
        if matches == 0:
            raise ValueError(f"Missing source column: {column}.")
        if matches != 1:
            raise ValueError(f"Source column {column} is ambiguous because its name is duplicated.")
    for name, unit in (("time_unit", time_unit), ("value_unit", value_unit)):
        if not isinstance(unit, str) or not unit.strip():
            raise ValueError(f"{name}: provide an explicit nonempty display unit.")
    if frame.empty:
        raise ValueError("A signal table requires observations in at least one channel.")

    times = _real_values(frame, time_column)
    values = _real_values(frame, value_column)
    rows: dict[str, list[int]] = {}
    original_labels: dict[str, object] = {}
    for position, value in enumerate(frame[channel_column]):
        if not pd.api.types.is_scalar(value) or pd.isna(value) or not str(value).strip():
            raise ValueError(f"{channel_column}: Channel labels must be nonempty scalar values.")
        label = str(value)
        if label in original_labels and original_labels[label] != value:
            raise ValueError(f"{channel_column}: ambiguous Channel values share display label {label!r}.")
        original_labels[label] = value
        rows.setdefault(label, []).append(position)
    if not 1 <= len(rows) <= 16:
        raise ValueError("A signal stack supports 1–16 explicit channels.")
    for label, positions in rows.items():
        if len(positions) < 2:
            raise ValueError(f"{channel_column}: channel {label!r} requires at least two time points.")
        channel_times = times[positions]
        # Direct comparison avoids overflow from subtracting extreme timestamps.
        if not np.all(channel_times[1:] > channel_times[:-1]):
            raise ValueError(f"{time_column}: channel {label!r} times must be strictly increasing.")

    lower = float(values.min())
    upper = float(values.max())
    span = upper - lower
    if not math.isfinite(span):
        raise ValueError("Source amplitudes cannot produce a finite common display span.")
    reference_span = span if span > 0.0 else max(abs(lower), 1.0)
    spacing = span * 1.25 if span > 0.0 else reference_span * 0.25
    offsets = tuple((label, float((len(rows) - 1 - index) * spacing))
                    for index, label in enumerate(rows))
    if not math.isfinite(spacing) or spacing <= 0.0 or any(not math.isfinite(v) for _, v in offsets):
        raise ValueError("Source amplitudes cannot produce finite channel display offsets.")
    display_lower = lower
    display_upper = upper + offsets[0][1]
    if display_lower == display_upper:
        display_lower -= spacing / 2.0
        display_upper += spacing / 2.0
    if (not math.isfinite(display_lower) or not math.isfinite(display_upper)
            or display_lower >= display_upper):
        raise ValueError("Source amplitudes cannot produce finite nondegenerate display bounds.")

    return SignalStackPlan(
        time_column=time_column,
        value_column=value_column,
        channel_column=channel_column,
        time_unit=time_unit,
        value_unit=value_unit,
        channel_order=tuple(rows),
        channel_rows=tuple((label, tuple(positions)) for label, positions in rows.items()),
        offsets=offsets,
        offset_step=spacing,
        source_value_range=(lower, upper),
        time_range=(float(times.min()), float(times.max())),
        display_y_range=(display_lower, display_upper),
        display_transform=DISPLAY_TRANSFORM,
        amplitude_scale_length=_nice_amplitude_length(reference_span / 4.0),
        amplitude_scale_kind=AMPLITUDE_SCALE_KIND,
    )
