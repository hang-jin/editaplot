"""Pure display plans for paired channels and a supplied upstream ratio.

Each source row explicitly pairs numerator, denominator and ratio at its own
X coordinate and condition. No ratio is computed or checked against division;
the ratio definition and all units are upstream declarations. No calibration,
physiological interpretation, statistics, normalization, fitting, interpolation,
or sample/subject pairing is inferred. This is an internal, unregistered model,
not a verified Origin plotting route.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RatiometricResponsePlan:
    x_column: str
    condition_column: str
    numerator_column: str
    denominator_column: str
    ratio_column: str
    x_unit: str
    numerator_unit: str
    denominator_unit: str
    ratio_unit: str
    ratio_definition: str
    condition_order: tuple[str, ...]
    condition_rows: tuple[tuple[str, tuple[int, ...]], ...]
    x_range: tuple[float, float]
    numerator_range: tuple[float, float]
    denominator_range: tuple[float, float]
    ratio_range: tuple[float, float]
    retained_columns: tuple[str, ...]
    row_pairing: str = "same_source_row_at_supplied_x_and_condition"
    ratio_validation: str = "upstream_declaration_only"


def _finite_values(frame: pd.DataFrame, column: str) -> np.ndarray:
    source = frame[column]
    forbidden = (bool, np.bool_, dt.date, dt.timedelta, np.datetime64, np.timedelta64)
    if (
        any(isinstance(value, forbidden) for value in source)
        or pd.api.types.is_datetime64_any_dtype(source)
        or pd.api.types.is_timedelta64_dtype(source)
    ):
        raise ValueError(f"{column}: finite real numeric values are required, not booleans or dates.")
    try:
        numeric = pd.to_numeric(source, errors="raise")
        if np.iscomplexobj(numeric):
            raise ValueError("Complex channel/ratio coordinates are unsupported.")
        values = numeric.to_numpy(dtype=float, copy=True)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{column}: finite real numeric values are required.") from error
    if not np.isfinite(values).all():
        raise ValueError(f"{column}: missing or nonfinite values are not removed or replaced.")
    return values


def _display_range(values: np.ndarray) -> tuple[float, float]:
    lower, upper = float(values.min()), float(values.max())
    padding = upper * 0.05 - lower * 0.05 if upper > lower else max(abs(lower), 1.0) * 0.05
    bounds = lower - padding, upper + padding
    if (
        not all(math.isfinite(value) for value in bounds)
        or bounds[0] >= bounds[1]
        or not math.isfinite(bounds[1] - bounds[0])
    ):
        raise ValueError("The supplied values cannot produce finite 5% padded display bounds.")
    return bounds


def build_ratiometric_response_plan(
    frame: pd.DataFrame,
    *,
    x_column: str,
    condition_column: str,
    numerator_column: str,
    denominator_column: str,
    ratio_column: str,
    x_unit: str,
    numerator_unit: str,
    denominator_unit: str,
    ratio_unit: str,
    ratio_definition: str,
) -> RatiometricResponsePlan:
    """Reference supplied observations without copying or rewriting source data.

    ``condition_rows`` freezes zero-based iloc references, in source order.
    Each condition needs at least two unique, strictly increasing X values;
    interleaved conditions and unequal/irregular sampling are retained. Units
    need not match and are never converted. Declare a unitless supplied ratio
    explicitly, for example with ``ratio_unit="dimensionless"``.

    Separate 5% padded linear display ranges never couple channel or ratio
    units and never force a zero baseline. Sample IDs and all other unused
    source columns remain metadata; their values do not establish pairing.
    The caller retains the unchanged source table referenced by this plan.
    """
    columns = (x_column, condition_column, numerator_column, denominator_column, ratio_column)
    if any(not isinstance(column, str) or not column.strip() for column in columns):
        raise ValueError("Provide five explicit nonempty source column names.")
    if len(set(columns)) != len(columns):
        raise ValueError("X, Condition, Numerator, Denominator and Ratio need distinct source columns.")
    for column in columns:
        matches = sum(name == column for name in frame.columns)
        if matches == 0:
            raise ValueError(f"Missing source column: {column}.")
        if matches != 1:
            raise ValueError(f"Source column {column} is ambiguous because its name is duplicated.")
    for name, declaration in (
        ("x_unit", x_unit), ("numerator_unit", numerator_unit),
        ("denominator_unit", denominator_unit), ("ratio_unit", ratio_unit),
        ("ratio_definition", ratio_definition),
    ):
        if not isinstance(declaration, str) or not declaration.strip():
            raise ValueError(f"{name} must be an explicit nonempty string.")
    if frame.empty:
        raise ValueError("A ratiometric-response table requires at least two observations per condition.")

    x = _finite_values(frame, x_column)
    numerator = _finite_values(frame, numerator_column)
    denominator = _finite_values(frame, denominator_column)
    ratio = _finite_values(frame, ratio_column)
    if bool((denominator == 0).any()):
        raise ValueError("Every supplied denominator must be nonzero; rows and ratios are never repaired.")

    rows: dict[str, list[int]] = {}
    originals: dict[str, object] = {}
    for position, value in enumerate(frame[condition_column]):
        if not pd.api.types.is_scalar(value) or pd.isna(value) or not str(value).strip():
            raise ValueError(f"{condition_column}: Condition labels must be nonempty scalar values.")
        label = str(value)
        if label in originals and originals[label] != value:
            raise ValueError(f"{condition_column}: ambiguous Condition values share display label {label!r}.")
        originals[label] = value
        rows.setdefault(label, []).append(position)
    if not 1 <= len(rows) <= 8:
        raise ValueError("A ratiometric-response plan supports 1-8 explicit conditions.")
    for label, positions in rows.items():
        if len(positions) < 2:
            raise ValueError(f"Condition {label!r} requires at least two observations.")
        if any(x[right] <= x[left] for left, right in zip(positions, positions[1:], strict=False)):
            raise ValueError(f"X must be unique and strictly increasing within Condition {label!r}.")

    return RatiometricResponsePlan(
        x_column=x_column,
        condition_column=condition_column,
        numerator_column=numerator_column,
        denominator_column=denominator_column,
        ratio_column=ratio_column,
        x_unit=x_unit,
        numerator_unit=numerator_unit,
        denominator_unit=denominator_unit,
        ratio_unit=ratio_unit,
        ratio_definition=ratio_definition,
        condition_order=tuple(rows),
        condition_rows=tuple((label, tuple(positions)) for label, positions in rows.items()),
        x_range=_display_range(x),
        numerator_range=_display_range(numerator),
        denominator_range=_display_range(denominator),
        ratio_range=_display_range(ratio),
        retained_columns=tuple(str(column) for column in frame.columns if column not in columns),
    )
