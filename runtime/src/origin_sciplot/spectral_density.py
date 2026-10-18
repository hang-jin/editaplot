"""Display-only plans for supplied PSD curves, intervals and reference bands.

The source must already contain the spectral density. No FFT/Welch estimate,
smoothing, 1/f fit, band integration, normalization, or uncertainty calculation
is performed. This model is not a registered or verified Origin route.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Real

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FrequencyBand:
    name: str
    lower: float
    upper: float


@dataclass(frozen=True)
class SpectralDensityPlan:
    frequency_column: str
    value_column: str
    condition_column: str | None
    lower_column: str | None
    upper_column: str | None
    frequency_unit: str
    value_unit: str
    value_representation: str
    frequency_domain: str
    interval_label: str | None
    series_order: tuple[str, ...]
    series_rows: tuple[tuple[str, tuple[int, ...]], ...]
    frequency_range: tuple[float, float]
    value_range: tuple[float, float]
    x_scale: str
    y_scale: str
    bands: tuple[FrequencyBand, ...]
    retained_columns: tuple[str, ...]
    warnings: tuple[str, ...]
    band_role: str = "reference_only_no_integral"
    display_transform: str = "identity"
    processing_boundary: str = "upstream_spectral_density_only"


def _numbers(frame: pd.DataFrame, column: str) -> np.ndarray:
    source = frame[column]
    if (
        any(isinstance(value, (bool, np.bool_)) for value in source)
        or pd.api.types.is_datetime64_any_dtype(source)
        or pd.api.types.is_timedelta64_dtype(source)
    ):
        raise ValueError(f"{column}: provide real values in the declared units, not flags or dates.")
    try:
        numeric = pd.to_numeric(source, errors="raise")
        if np.iscomplexobj(numeric):
            raise ValueError("Complex spectra need explicit upstream processing.")
        values = numeric.to_numpy(dtype=float, copy=True)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{column}: finite real numeric values are required.") from error
    if not np.isfinite(values).all():
        raise ValueError(f"{column}: missing/nonfinite samples are not deleted or interpolated.")
    return values


def _display_range(lower: float, upper: float, scale: str, zero_floor: bool) -> tuple[float, float]:
    if scale == "log10":
        if lower <= 0:
            raise ValueError("A logarithmic value axis requires positive values and interval bounds.")
        lo, hi = math.log10(lower), math.log10(upper)
        padding = (hi - lo) * 0.08 if hi > lo else 0.08
        try:
            result = 10 ** (lo - padding), 10 ** (hi + padding)
        except OverflowError as error:
            raise ValueError("The logarithmic display range exceeds finite bounds.") from error
    else:
        padding = upper * 0.08 - lower * 0.08 if upper > lower else max(abs(lower), 1) * 0.08
        result = (max(0.0, lower - padding) if zero_floor else lower - padding), upper + padding
    if (
        not all(math.isfinite(value) for value in result)
        or result[0] >= result[1]
        or (scale == "log10" and result[0] <= 0)
        or not math.isfinite(result[1] - result[0])
    ):
        raise ValueError("The supplied values cannot produce finite display bounds.")
    return result


def _bands(bands: Sequence[FrequencyBand], domain: tuple[float, float]) -> tuple[FrequencyBand, ...]:
    try:
        supplied = tuple(bands)
    except TypeError as error:
        raise ValueError("Supply explicit named FrequencyBand declarations.") from error
    result: list[FrequencyBand] = []
    for band in supplied:
        if not isinstance(band, FrequencyBand) or not isinstance(band.name, str) or not band.name.strip():
            raise ValueError("Each frequency band needs its explicit nonempty name and endpoints.")
        if any(not isinstance(v, Real) or isinstance(v, (bool, np.bool_)) for v in (band.lower, band.upper)):
            raise ValueError("Band endpoints must be finite real values in the frequency units.")
        try:
            lower, upper = float(band.lower), float(band.upper)
        except (ValueError, OverflowError) as error:
            raise ValueError("Band endpoints must be finite real values.") from error
        if not all(map(math.isfinite, (lower, upper))) or not domain[0] <= lower < upper <= domain[1]:
            raise ValueError("Band endpoints must increase and lie within the supplied frequency domain.")
        for previous in result:
            if previous.name == band.name or max(lower, previous.lower) < min(upper, previous.upper):
                raise ValueError("Band names must be unique and reference intervals must not overlap.")
        result.append(FrequencyBand(band.name, lower, upper))
    return tuple(result)


def build_spectral_density_plan(
    frame: pd.DataFrame,
    *,
    frequency_column: str,
    value_column: str,
    frequency_unit: str,
    value_unit: str,
    value_representation: str,
    condition_column: str | None = None,
    lower_column: str | None = None,
    upper_column: str | None = None,
    interval_label: str | None = None,
    frequency_domain: str = "nonnegative",
    x_scale: str = "linear",
    y_scale: str = "linear",
    bands: Sequence[FrequencyBand] = (),
) -> SpectralDensityPlan:
    """Preserve nonuniform curves and optional supplied bounds in first-appearance order.

    Rows are iloc positions, not DataFrame index labels. Single-curve two-column
    tables need no fabricated condition. Explicit signed/two-sided frequencies
    are supported; log axes cannot discard zero or negative samples. Already
    logarithmic densities cannot silently receive a second logarithm.
    """
    if any(not isinstance(unit, str) or not unit.strip() for unit in (frequency_unit, value_unit)):
        raise ValueError("Frequency and density units must be explicitly declared.")
    if value_representation not in ("linear_density", "already_logarithmic"):
        raise ValueError("Declare linear density or an already logarithmic density representation.")
    if frequency_domain not in ("nonnegative", "signed"):
        raise ValueError("Declare nonnegative or signed/two-sided frequency coordinates.")
    if x_scale not in ("linear", "log10") or y_scale not in ("linear", "log10"):
        raise ValueError("Only explicitly selected linear and log10 display axes are supported.")
    if value_representation == "already_logarithmic" and y_scale != "linear":
        raise ValueError("The supplied density is already logarithmic; do not apply a second logarithm.")
    if (lower_column is None) != (upper_column is None):
        raise ValueError("Provide both lower and upper interval columns, or neither.")
    has_interval = lower_column is not None
    if has_interval and (not isinstance(interval_label, str) or not interval_label.strip()):
        raise ValueError("A supplied interval requires its explicit definition, not an inferred SD/SEM/CI.")
    if not has_interval and interval_label is not None:
        raise ValueError("An interval label requires actual lower/upper source columns.")
    columns = [frequency_column, value_column]
    columns += [column for column in (condition_column, lower_column, upper_column) if column is not None]
    if any(not isinstance(column, str) or not column.strip() for column in columns) or len(
        set(columns)
    ) != len(columns):
        raise ValueError("Provide distinct explicit source columns for the spectral roles.")
    if any(sum(name == column for name in frame.columns) != 1 for column in columns) or frame.empty:
        raise ValueError("Every selected source column must occur once in a nonempty table.")
    frequency, values = _numbers(frame, frequency_column), _numbers(frame, value_column)
    if frequency_domain == "nonnegative" and bool((frequency < 0).any()):
        raise ValueError("Negative frequency coordinates require an explicit signed frequency declaration.")
    if x_scale == "log10" and bool((frequency <= 0).any()):
        raise ValueError("A logarithmic frequency axis requires positive samples; none are dropped.")
    if value_representation == "linear_density" and bool((values < 0).any()):
        raise ValueError("Linear densities must be nonnegative; declare logarithmic data explicitly.")
    lower = _numbers(frame, lower_column) if lower_column is not None else values
    upper = _numbers(frame, upper_column) if upper_column is not None else values
    if bool((lower > values).any()) or bool((values > upper).any()):
        raise ValueError("Every supplied lower/upper interval must enclose its source density value.")
    rows: dict[str, list[int]] = {}
    originals: dict[str, object] = {}
    labels = frame[condition_column] if condition_column is not None else [value_column] * len(frame)
    for position, value in enumerate(labels):
        if not pd.api.types.is_scalar(value) or pd.isna(value) or not str(value).strip():
            raise ValueError("Condition labels must be nonempty scalar source values.")
        label = str(value)
        if label in originals and originals[label] != value:
            raise ValueError("Distinct conditions share an ambiguous display name.")
        originals[label] = value
        rows.setdefault(label, []).append(position)
    if not 1 <= len(rows) <= 8:
        raise ValueError("One spectral comparison supports 1-8 explicitly named curves.")
    for label, positions in rows.items():
        series_frequency = frequency[positions]
        if len(positions) < 2 or not bool(np.all(series_frequency[1:] > series_frequency[:-1])):
            raise ValueError(f"{label}: retain at least two strictly increasing supplied frequency points.")
    domain = float(frequency.min()), float(frequency.max())
    if not math.isfinite(domain[1] - domain[0]):
        raise ValueError("The supplied frequency domain exceeds finite plotting bounds.")
    low, high = float(lower.min()), float(upper.max())
    warnings = (
        ("provided_interval_below_zero",) if value_representation == "linear_density" and low < 0 else ()
    )
    return SpectralDensityPlan(
        frequency_column=frequency_column,
        value_column=value_column,
        condition_column=condition_column,
        lower_column=lower_column,
        upper_column=upper_column,
        frequency_unit=frequency_unit,
        value_unit=value_unit,
        value_representation=value_representation,
        frequency_domain=frequency_domain,
        interval_label=interval_label,
        series_order=tuple(rows),
        series_rows=tuple((label, tuple(positions)) for label, positions in rows.items()),
        frequency_range=domain,
        value_range=_display_range(low, high, y_scale, value_representation == "linear_density" and low >= 0),
        x_scale=x_scale,
        y_scale=y_scale,
        bands=_bands(bands, domain),
        retained_columns=tuple(str(c) for c in frame.columns if c not in columns),
        warnings=warnings,
    )
