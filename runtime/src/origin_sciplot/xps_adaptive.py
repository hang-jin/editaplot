"""Column profiling and axis planning for adaptive tabular XPS inputs."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal

import pandas as pd

if TYPE_CHECKING:
    from origin_sciplot.xps_workflow import XpsPreparation


SeriesRole = Literal["raw", "background", "envelope", "component", "residual"]


class XpsProfileError(ValueError):
    """Raised when a table cannot be interpreted as an XPS spectrum."""


@dataclass(frozen=True)
class XpsSeries:
    column: str
    label: str
    role: SeriesRole

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class XpsProfile:
    x_column: str
    raw_column: str | None
    background_column: str | None
    envelope_column: str | None
    residuals_column: str | None
    component_columns: tuple[str, ...]
    series: tuple[XpsSeries, ...]

    @property
    def primary_y_columns(self) -> tuple[str, ...]:
        return tuple(item.column for item in self.series if item.role != "residual")

    @property
    def scale_y_columns(self) -> tuple[str, ...]:
        preferred = tuple(
            column
            for column in (self.raw_column, self.background_column, self.envelope_column)
            if column is not None
        )
        return preferred or self.primary_y_columns

    def to_dict(self) -> dict[str, object]:
        return {
            "x_column": self.x_column,
            "raw_column": self.raw_column,
            "background_column": self.background_column,
            "envelope_column": self.envelope_column,
            "residuals_column": self.residuals_column,
            "component_columns": list(self.component_columns),
            "series": [item.to_dict() for item in self.series],
        }


@dataclass(frozen=True)
class XpsAxisPlan:
    x_min_ev: float
    x_max_ev: float
    x_from_plot: float
    x_to_plot: float
    x_step_ev: float
    x_first_tick_plot: float
    x_first_tick_ev: float
    y_min: float
    y_max: float
    y_from: float
    y_to: float
    y_step: float
    energy_kind: str = "binding"
    x_transform: str = "negate"
    x_label_divide_by: float = -1.0
    x_title: str = "Binding Energy (eV)"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


ENERGY_ALIASES = {
    "bindingenergy",
    "bindingenergye",
    "bindingenergyev",
    "energy",
    "energye",
    "energyev",
}
BACKGROUND_ALIASES = {"background", "backgnd", "backgnd.", "bg", "baseline"}
ENVELOPE_ALIASES = {"envelope", "fit", "fitted", "totalfit", "fittotal", "total"}
RESIDUAL_ALIASES = {"residual", "residuals"}
RAW_ALIASES = {"raw", "intensity", "intensityau", "experimental", "experiment", "counts", "countss"}


def normalize_column_name(name: object) -> str:
    """Normalize spreadsheet headers for alias matching."""
    return re.sub(r"[^a-z0-9]+", "", str(name).strip().lower())


def _is_counts_column(normalized: str) -> bool:
    return normalized.startswith("counts") or normalized in RAW_ALIASES


def _first_matching(columns: list[str], aliases: set[str]) -> str | None:
    for column in columns:
        if normalize_column_name(column) in aliases:
            return column
    return None


def _first_energy_column(frame: pd.DataFrame) -> str:
    columns = [str(column) for column in frame.columns]
    direct = _first_matching(columns, ENERGY_ALIASES)
    if direct:
        return direct
    for column in columns:
        series = pd.to_numeric(frame[column], errors="coerce")
        if series.notna().sum() >= 2 and (series.is_monotonic_increasing or series.is_monotonic_decreasing):
            if float(series.max()) != float(series.min()):
                return column
    raise XpsProfileError("Could not identify the Binding Energy column.")


def profile_xps_frame(frame: pd.DataFrame) -> XpsProfile:
    """Infer XPS roles from a numeric table without requiring fixed peak columns."""
    if frame.shape[1] < 2:
        raise XpsProfileError("XPS data needs at least two numeric columns.")

    x_column = _first_energy_column(frame)
    y_candidates = [str(column) for column in frame.columns if str(column) != x_column]
    background = _first_matching(y_candidates, BACKGROUND_ALIASES)
    envelope = _first_matching(y_candidates, ENVELOPE_ALIASES)
    residuals = _first_matching(y_candidates, RESIDUAL_ALIASES)

    reserved = {column for column in (background, envelope, residuals) if column}
    raw = None
    for column in y_candidates:
        normalized = normalize_column_name(column)
        if column not in reserved and (_is_counts_column(normalized) or normalized in RAW_ALIASES):
            raw = column
            break
    if raw is None:
        for column in y_candidates:
            if column not in reserved:
                raw = column
                break

    component_columns = tuple(
        column for column in y_candidates if column not in {raw, background, envelope, residuals}
    )
    if raw is None and not component_columns:
        raise XpsProfileError("Could not identify any plottable XPS intensity columns.")

    series: list[XpsSeries] = []
    if raw:
        series.append(XpsSeries(raw, raw, "raw"))
    if background:
        series.append(XpsSeries(background, background, "background"))
    for column in component_columns:
        series.append(XpsSeries(column, column, "component"))
    if envelope:
        series.append(XpsSeries(envelope, envelope, "envelope"))
    if residuals:
        series.append(XpsSeries(residuals, residuals, "residual"))

    return XpsProfile(
        x_column=x_column,
        raw_column=raw,
        background_column=background,
        envelope_column=envelope,
        residuals_column=residuals,
        component_columns=component_columns,
        series=tuple(series),
    )


def _nice_step(value: float) -> float:
    if value <= 0 or not math.isfinite(value):
        return 1.0
    exponent = math.floor(math.log10(value))
    fraction = value / (10**exponent)
    if fraction <= 1:
        nice = 1.0
    elif fraction <= 2:
        nice = 2.0
    elif fraction <= 5:
        nice = 5.0
    else:
        nice = 10.0
    return nice * (10**exponent)


def build_axis_plan(
    frame: pd.DataFrame,
    profile: XpsProfile,
    preparation: XpsPreparation | None = None,
) -> XpsAxisPlan:
    """Build dynamic XPS axis limits from the actual input data."""
    x_values = pd.to_numeric(frame[profile.x_column], errors="coerce").dropna()
    if x_values.empty or float(x_values.max()) == float(x_values.min()):
        raise XpsProfileError("Binding Energy column must contain a non-zero numeric range.")

    x_min = float(x_values.min())
    x_max = float(x_values.max())
    if preparation is None:
        x_range = x_max - x_min
        x_step = _nice_step(x_range / 5.0)
        first_tick_ev = math.floor(x_max / x_step) * x_step
        x_from_plot = -x_max
        x_to_plot = -x_min
        first_tick_plot = -first_tick_ev
        energy_kind = "binding"
        x_transform = "negate"
        x_label_divide_by = -1.0
        x_title = "Binding Energy (eV)"
    else:
        shared_axis = preparation.plot_spec.axis
        x_min = float(shared_axis.source_min_ev)
        x_max = float(shared_axis.source_max_ev)
        x_step = float(shared_axis.major_step_ev)
        first_tick_ev = float(shared_axis.first_tick_ev)
        x_from_plot = float(shared_axis.plot_from)
        x_to_plot = float(shared_axis.plot_to)
        first_tick_plot = float(shared_axis.first_tick_plot)
        energy_kind = shared_axis.energy_kind
        x_transform = shared_axis.transform
        x_label_divide_by = float(shared_axis.label_divide_by)
        x_title = shared_axis.x_title

    y_columns = list(profile.scale_y_columns)
    y_values = pd.concat([pd.to_numeric(frame[column], errors="coerce") for column in y_columns]).dropna()
    if y_values.empty:
        raise XpsProfileError("No numeric intensity values were found.")
    positive_values = y_values[y_values > 0]
    if not positive_values.empty and float(y_values.max()) > 0:
        y_values = positive_values
    y_min = float(y_values.min())
    y_max = float(y_values.max())
    if y_min == y_max:
        padding = max(abs(y_min) * 0.05, 1.0)
    else:
        padding = (y_max - y_min) * 0.06
    y_from = y_min - padding
    if y_min >= 0:
        y_from = max(0.0, y_from)
    y_to = y_max + padding
    y_step = _nice_step((y_to - y_from) / 5.0)

    return XpsAxisPlan(
        x_min_ev=x_min,
        x_max_ev=x_max,
        x_from_plot=x_from_plot,
        x_to_plot=x_to_plot,
        x_step_ev=x_step,
        x_first_tick_plot=first_tick_plot,
        x_first_tick_ev=first_tick_ev,
        y_min=y_min,
        y_max=y_max,
        y_from=y_from,
        y_to=y_to,
        y_step=y_step,
        energy_kind=energy_kind,
        x_transform=x_transform,
        x_label_divide_by=x_label_divide_by,
        x_title=x_title,
    )
