"""Pure, deterministic preparation of tabular XPS inputs for plotting adapters.

This module deliberately has no OriginPro dependency.  ``prepare_xps`` reads a
source table without modifying it and returns an immutable description that UI,
preview, and Origin adapters can share.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from .data_loader import DataLoadError, LoadedTable, load_table


EnergyKind = Literal["binding", "kinetic", "unknown"]
SpectrumRegion = str
XpsMode = Literal["scan", "fit", "fit_with_residual"]
VisualProfile = Literal["fixed_c1s_publication", "adaptive_counts"]
XpsTemplateId = Literal["xps"]
XpsRendererTemplateId = Literal["xps_c1s_fit", "xps_adaptive"]
ComponentBasis = Literal["relative_to_background", "baseline_inclusive", "unresolved"]
SeriesRole = Literal["raw", "background", "envelope", "component", "residual"]

FIXED_C1S_COLUMNS = (
    "BindingEnergy",
    "Raw",
    "Background",
    "Envelope",
    "Peak_CC",
    "Peak_CO",
    "Peak_CeqO",
    "Peak_OCeqO",
)
FIXED_C1S_DISPLAY_LEFT_EV = 292.0
FIXED_C1S_DISPLAY_RIGHT_EV = 280.5
FIXED_C1S_MAJOR_STEP_EV = 2.0
FIXED_C1S_LABELS = {
    "Raw": "Raw",
    "Background": "Background",
    "Envelope": "Envelope",
    "Peak_CC": "C-C / C=C",
    "Peak_CO": "C-O",
    "Peak_CeqO": "C=O",
    "Peak_OCeqO": "O-C=O",
}


class XpsWorkflowError(ValueError):
    """Stable, user-presentable failure raised by :func:`prepare_xps`."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        column: str | None = None,
        row: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.column = column
        self.row = row

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": str(self), "column": self.column, "row": self.row}


XpsPreparationError = XpsWorkflowError


@dataclass(frozen=True)
class XpsDetection:
    energy_kind: EnergyKind
    spectrum_region: SpectrumRegion
    mode: XpsMode

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class XpsColumnRoles:
    x: str
    raw: str | None
    background: str | None
    envelope: str | None
    residual: str | None
    components: tuple[str, ...]
    ignored: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["components"] = list(self.components)
        value["ignored"] = list(self.ignored)
        return value


@dataclass(frozen=True)
class XpsColumnMapping:
    """User-confirmed interpretation of source columns."""

    x: str
    raw: str
    background: str | None
    envelope: str | None
    residual: str | None
    components: tuple[str, ...]
    ignored: tuple[str, ...]
    energy_kind: Literal["binding", "kinetic"]

    def __post_init__(self) -> None:
        if self.energy_kind not in {"binding", "kinetic"}:
            raise ValueError("energy_kind must be 'binding' or 'kinetic'")

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["components"] = list(self.components)
        value["ignored"] = list(self.ignored)
        return value


@dataclass(frozen=True)
class XpsAxisPlan:
    energy_kind: EnergyKind
    transform: Literal["negate", "identity"]
    source_min_ev: float
    source_max_ev: float
    plot_from: float
    plot_to: float
    display_from_ev: float
    display_to_ev: float
    major_step_ev: float
    first_tick_ev: float
    first_tick_plot: float
    label_divide_by: float
    x_title: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class XpsHelperExpression:
    name: str
    expression: str
    purpose: Literal["x_transform", "component_fill_top", "component_fill_base"]

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class XpsSeriesSpec:
    column: str
    label: str
    role: SeriesRole

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class XpsPlotSpec:
    visual_profile: VisualProfile
    axis: XpsAxisPlan
    series: tuple[XpsSeriesSpec, ...]
    fill_baseline: str
    component_basis: ComponentBasis
    residual_policy: Literal["preserve_not_plotted"]
    helpers: tuple[XpsHelperExpression, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "visual_profile": self.visual_profile,
            "axis": self.axis.to_dict(),
            "series": [series.to_dict() for series in self.series],
            "fill_baseline": self.fill_baseline,
            "component_basis": self.component_basis,
            "residual_policy": self.residual_policy,
            "helpers": [helper.to_dict() for helper in self.helpers],
        }


@dataclass(frozen=True)
class XpsPreparation:
    source_path: str
    source_sha256: str
    source_size_bytes: int
    source_format: str
    source_sheet: str | None
    source_delimiter: str | None
    source_columns: tuple[str, ...]
    row_count: int
    ignored_empty_rows: int
    detection: XpsDetection
    roles: XpsColumnRoles
    component_basis: ComponentBasis
    plot_spec: XpsPlotSpec
    warnings: tuple[str, ...]
    confidence: float
    column_mapping: XpsColumnMapping | None
    mapping_confirmed: bool
    requires_confirmation: bool
    confirmation_reasons: tuple[str, ...]
    plan_digest: str

    @property
    def axis_plan(self) -> XpsAxisPlan:
        return self.plot_spec.axis

    def to_dict(self) -> dict[str, object]:
        return {
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "source_size_bytes": self.source_size_bytes,
            "source_format": self.source_format,
            "source_sheet": self.source_sheet,
            "source_delimiter": self.source_delimiter,
            "source_columns": list(self.source_columns),
            "row_count": self.row_count,
            "ignored_empty_rows": self.ignored_empty_rows,
            "detection": self.detection.to_dict(),
            "roles": self.roles.to_dict(),
            "component_basis": self.component_basis,
            "plot_spec": self.plot_spec.to_dict(),
            "warnings": list(self.warnings),
            "confidence": self.confidence,
            "column_mapping": self.column_mapping.to_dict() if self.column_mapping else None,
            "mapping_confirmed": self.mapping_confirmed,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_reasons": list(self.confirmation_reasons),
            "plan_digest": self.plan_digest,
        }


def select_xps_template_id(preparation: XpsPreparation) -> XpsTemplateId:
    """Return the single user-visible registry route for every XPS plan."""
    del preparation
    return "xps"


def select_xps_renderer_template_id(preparation: XpsPreparation) -> XpsRendererTemplateId:
    """Return the internal renderer adapter selected by the XPS visual profile."""
    return (
        "xps_c1s_fit"
        if preparation.plot_spec.visual_profile == "fixed_c1s_publication"
        else "xps_adaptive"
    )


def _strip_residual_annotation(value: str) -> str:
    cleaned = re.sub(
        r"\s*\(\s*residuals?\s*[×x*]\s*\d+(?:\.\d+)?\s*\)\s*",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    return " ".join(cleaned.split())


def xps_y_axis_title(preparation: XpsPreparation) -> str:
    """Return an English publication label for standard intensity aliases."""
    raw = preparation.roles.raw
    if raw is None:
        return "Intensity (a.u.)"
    raw = _strip_residual_annotation(raw)
    normalized = _normalize(raw)
    if normalized in {"强度", "原始强度", "原始数据", "实验数据", "测量值"}:
        return "Intensity (a.u.)"
    if normalized in {"计数", "计数率"}:
        return "Counts (a.u.)"
    return raw


def _normalize(value: object) -> str:
    return "".join(character for character in str(value).strip().lower() if character.isalnum())


def _read_csv(source: bytes) -> tuple[list[str], list[list[float]], int]:
    if not source:
        raise XpsWorkflowError("empty_file", "The CSV file is empty.")
    try:
        text = source.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise XpsWorkflowError("encoding_error", "The CSV file is not valid UTF-8 text.") from exc
    if not text.strip():
        raise XpsWorkflowError("empty_file", "The CSV file is empty.")
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as exc:
        raise XpsWorkflowError("csv_parse_error", f"The CSV structure is invalid: {exc}") from exc
    if not rows:
        raise XpsWorkflowError("empty_file", "The CSV file is empty.")
    header = rows[0]
    if not header or all(not column.strip() for column in header):
        raise XpsWorkflowError("empty_header", "The CSV header is empty.")
    if len(header) < 2:
        raise XpsWorkflowError("too_few_columns", "XPS data needs an energy column and at least one series.")
    for column in header:
        if not column.strip():
            raise XpsWorkflowError("empty_column_name", "Every CSV column must have a name.")
    normalized_headers = [column.strip() for column in header]
    if len(set(normalized_headers)) != len(normalized_headers):
        duplicate = next(column for column in normalized_headers if normalized_headers.count(column) > 1)
        raise XpsWorkflowError(
            "duplicate_column", f"Duplicate CSV column: {duplicate!r}.", column=duplicate
        )
    numeric: list[list[float]] = []
    ignored_empty_rows = 0
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or all(not cell.strip() for cell in row):
            ignored_empty_rows += 1
            continue
        if len(row) != len(header):
            raise XpsWorkflowError(
                "malformed_row",
                f"CSV row {row_number} has {len(row)} fields; expected {len(header)}.",
                row=row_number,
            )
        numeric_row: list[float] = []
        for column_index, cell in enumerate(row):
            column = header[column_index]
            if not cell.strip():
                raise XpsWorkflowError(
                    "missing_value",
                    f"Row {row_number}, column {column!r} is empty.",
                    column=column,
                    row=row_number,
                )
            try:
                value = float(cell)
            except ValueError as exc:
                raise XpsWorkflowError(
                    "non_numeric",
                    f"Row {row_number}, column {column!r} is not numeric.",
                    column=column,
                    row=row_number,
                ) from exc
            if not math.isfinite(value):
                raise XpsWorkflowError(
                    "non_finite",
                    f"Row {row_number}, column {column!r} is not finite.",
                    column=column,
                    row=row_number,
                )
            numeric_row.append(value)
        numeric.append(numeric_row)
    if not numeric:
        raise XpsWorkflowError("no_data_rows", "The CSV file has no numeric data rows.")
    return header, numeric, ignored_empty_rows


def _validate_energy_values(values: list[float], column: str) -> None:
    if min(values) == max(values):
        raise XpsWorkflowError(
            "energy_zero_range", f"Energy column {column!r} must contain a non-zero range.", column=column
        )
    increasing = all(left <= right for left, right in zip(values, values[1:]))
    decreasing = all(left >= right for left, right in zip(values, values[1:]))
    if not (increasing or decreasing):
        raise XpsWorkflowError(
            "energy_not_monotonic", f"Energy column {column!r} must be monotonic.", column=column
        )


def _first(columns: list[str], aliases: set[str]) -> str | None:
    return next((column for column in columns if _normalize(column) in aliases), None)


def _first_where(columns: list[str], predicate) -> str | None:
    return next((column for column in columns if predicate(_normalize(column))), None)


def _is_background_name(value: str) -> bool:
    return value in {"background", "backgnd", "bg", "baseline", "背景", "基线"} or any(
        token in value for token in ("background", "backgnd", "baseline", "shirley", "tougaard")
    )


def _is_envelope_name(value: str) -> bool:
    if value in {
        "envelope",
        "fit",
        "fitted",
        "totalfit",
        "fittotal",
        "fitsum",
        "sumfit",
        "拟合包络",
        "包络",
        "总拟合",
        "拟合总和",
    }:
        return True
    return "fit" in value and any(token in value for token in ("total", "sum", "envelope"))


def _is_residual_name(value: str) -> bool:
    return value.startswith("resid") or value in {"残差", "残差值", "差值"}


def _is_raw_name(value: str) -> bool:
    return value.startswith(
        ("counts", "raw", "intensity", "experimental", "experiment", "measured")
    ) or value in {"强度", "计数", "计数率", "原始强度", "原始数据", "实验数据", "测量值"}


def _generic_core_region(text: str) -> SpectrumRegion:
    match = re.search(r"(?<![A-Za-z])([A-Za-z]{1,2})\s*([1-9])\s*([spdf])", text, re.IGNORECASE)
    if match is None:
        return "unknown"
    element = match.group(1)[0].upper() + match.group(1)[1:].lower()
    return f"{element}{match.group(2)}{match.group(3).lower()}"


def _region_from_name(path: Path) -> SpectrumRegion:
    normalized = _normalize(path.stem)
    aliases: tuple[tuple[str, SpectrumRegion], ...] = (
        ("survey", "Survey"),
        ("culm2", "CuLM2"),
        ("cu2p", "Cu2p"),
        ("ca2p", "Ca2p"),
        ("c1s", "C1s"),
        ("o1s", "O1s"),
        ("y3d", "Y3d"),
        ("zr3d", "Zr3d"),
    )
    known = next((region for token, region in aliases if token in normalized), "unknown")
    return known if known != "unknown" else _generic_core_region(path.stem)


def _detect_region(
    path: Path, columns: list[str], energy_kind: EnergyKind, energy_values: list[float]
) -> SpectrumRegion:
    named_region = _region_from_name(path)
    if named_region != "unknown":
        return named_region
    joined_headers = " ".join(_normalize(column) for column in columns)
    header_aliases: tuple[tuple[str, SpectrumRegion], ...] = (
        ("culm2", "CuLM2"),
        ("cu2p", "Cu2p"),
        ("ca2p", "Ca2p"),
        ("c1s", "C1s"),
        ("o1s", "O1s"),
        ("y3d", "Y3d"),
        ("zr3d", "Zr3d"),
    )
    header_region = next((region for token, region in header_aliases if token in joined_headers), "unknown")
    if header_region == "unknown":
        header_region = _generic_core_region(" ".join(columns))
    if header_region != "unknown":
        return header_region
    source_min = min(energy_values)
    source_max = max(energy_values)
    if energy_kind == "binding" and source_max - source_min >= 200.0:
        return "Survey"
    if energy_kind != "binding":
        return "unknown"
    midpoint = (source_min + source_max) / 2.0
    ranges: tuple[tuple[float, float, SpectrumRegion], ...] = (
        (275.0, 305.0, "C1s"),
        (335.0, 370.0, "Ca2p"),
        (515.0, 550.0, "O1s"),
        (560.0, 610.0, "CuLM2"),
        (915.0, 980.0, "Cu2p"),
        (145.0, 178.0, "Y3d"),
        (178.0, 205.0, "Zr3d"),
    )
    return next((region for low, high, region in ranges if low <= midpoint <= high), "unknown")


def _nice_step(value: float) -> float:
    if value <= 0 or not math.isfinite(value):
        return 1.0
    exponent = math.floor(math.log10(value))
    fraction = value / (10**exponent)
    nice = 1.0 if fraction <= 1 else (2.0 if fraction <= 2 else (5.0 if fraction <= 5 else 10.0))
    return nice * (10**exponent)


def _axis_plan(energy_kind: EnergyKind, values: list[float]) -> XpsAxisPlan:
    source_min = min(values)
    source_max = max(values)
    source_span = source_max - source_min
    step = _nice_step(source_span / 5.0)
    endpoint_padding = min(step * 0.25, source_span * 0.03)
    padded_min = source_min - endpoint_padding
    if source_min >= 0:
        padded_min = max(0.0, padded_min)
    padded_max = source_max + endpoint_padding
    if energy_kind == "binding":
        first_tick = math.floor(source_max / step) * step
        return XpsAxisPlan(
            energy_kind=energy_kind,
            transform="negate",
            source_min_ev=source_min,
            source_max_ev=source_max,
            plot_from=-padded_max,
            plot_to=-padded_min,
            display_from_ev=padded_max,
            display_to_ev=padded_min,
            major_step_ev=step,
            first_tick_ev=first_tick,
            first_tick_plot=-first_tick,
            label_divide_by=-1.0,
            x_title="Binding Energy (eV)",
        )
    first_tick = math.ceil(source_min / step) * step
    return XpsAxisPlan(
        energy_kind=energy_kind,
        transform="identity",
        source_min_ev=source_min,
        source_max_ev=source_max,
        plot_from=padded_min,
        plot_to=padded_max,
        display_from_ev=padded_min,
        display_to_ev=padded_max,
        major_step_ev=step,
        first_tick_ev=first_tick,
        first_tick_plot=first_tick,
        label_divide_by=1.0,
        x_title="Kinetic Energy (eV)" if energy_kind == "kinetic" else "Energy (eV)",
    )


def _fixed_c1s_axis_plan(values: list[float]) -> XpsAxisPlan:
    """Return the locked fixed-C1s window rather than inheriting source endpoints."""
    return XpsAxisPlan(
        energy_kind="binding",
        transform="negate",
        source_min_ev=min(values),
        source_max_ev=max(values),
        plot_from=-FIXED_C1S_DISPLAY_LEFT_EV,
        plot_to=-FIXED_C1S_DISPLAY_RIGHT_EV,
        display_from_ev=FIXED_C1S_DISPLAY_LEFT_EV,
        display_to_ev=FIXED_C1S_DISPLAY_RIGHT_EV,
        major_step_ev=FIXED_C1S_MAJOR_STEP_EV,
        first_tick_ev=FIXED_C1S_DISPLAY_LEFT_EV,
        first_tick_plot=-FIXED_C1S_DISPLAY_LEFT_EV,
        label_divide_by=-1.0,
        x_title="Binding Energy (eV)",
    )


def _fixed_helpers(roles: XpsColumnRoles) -> tuple[XpsHelperExpression, ...]:
    helpers = [XpsHelperExpression("PlotX", f"-[{roles.x}]", "x_transform")]
    assert roles.background is not None
    for component in roles.components:
        helpers.extend(
            (
                XpsHelperExpression(
                    f"{component}__FillTop",
                    f"[{roles.background}] + [{component}]",
                    "component_fill_top",
                ),
                XpsHelperExpression(
                    f"{component}__FillBase",
                    f"[{roles.background}]",
                    "component_fill_base",
                ),
            )
        )
    return tuple(helpers)


def _infer_component_basis(
    columns: list[str], rows: list[list[float]], roles: XpsColumnRoles
) -> ComponentBasis:
    if roles.background is None or roles.envelope is None or not roles.components:
        return "unresolved"
    background_index = columns.index(roles.background)
    envelope_index = columns.index(roles.envelope)
    component_indexes = [columns.index(column) for column in roles.components]
    relative_errors: list[float] = []
    inclusive_errors: list[float] = []
    envelope_scale: list[float] = []
    for row in rows:
        background = row[background_index]
        envelope = row[envelope_index]
        component_sum = sum(row[index] for index in component_indexes)
        relative_errors.append(abs(envelope - (background + component_sum)))
        inclusive_errors.append(abs(envelope - (component_sum - (len(component_indexes) - 1) * background)))
        envelope_scale.append(abs(envelope))
    relative_error = statistics.median(relative_errors)
    inclusive_error = statistics.median(inclusive_errors)
    scale = max(statistics.median(envelope_scale), 1.0)
    tolerance = scale * 0.02
    separation = scale * 0.05
    if relative_error <= tolerance and inclusive_error >= max(relative_error * 4.0, separation):
        return "relative_to_background"
    if inclusive_error <= tolerance and relative_error >= max(inclusive_error * 4.0, separation):
        return "baseline_inclusive"
    return "unresolved"


def _adaptive_helpers(
    roles: XpsColumnRoles, energy_kind: EnergyKind, component_basis: ComponentBasis
) -> tuple[XpsHelperExpression, ...]:
    x_expression = f"-[{roles.x}]" if energy_kind == "binding" else f"[{roles.x}]"
    helpers: list[XpsHelperExpression] = [XpsHelperExpression("PlotX", x_expression, "x_transform")]
    if roles.background is None or component_basis == "unresolved":
        return tuple(helpers)
    for component in roles.components:
        top_expression = (
            f"[{roles.background}] + [{component}]"
            if component_basis == "relative_to_background"
            else f"[{component}]"
        )
        helpers.extend(
            (
                XpsHelperExpression(f"{component}__FillTop", top_expression, "component_fill_top"),
                XpsHelperExpression(
                    f"{component}__FillBase", f"[{roles.background}]", "component_fill_base"
                ),
            )
        )
    return tuple(helpers)


def _series_specs(roles: XpsColumnRoles, *, fixed_c1s: bool = False) -> tuple[XpsSeriesSpec, ...]:
    def label(column: str, role: SeriesRole) -> str:
        if fixed_c1s:
            return FIXED_C1S_LABELS.get(column, column)
        if role == "raw":
            column = _strip_residual_annotation(column)
        normalized = _normalize(column)
        canonical = {
            "raw": "Raw",
            "background": "Background",
            "envelope": "Envelope",
            "residual": "Residual",
        }
        chinese_role_names = {
            "强度",
            "计数",
            "计数率",
            "原始强度",
            "原始数据",
            "背景",
            "基线",
            "拟合包络",
            "包络",
            "总拟合",
            "拟合总和",
            "残差",
            "残差值",
            "差值",
        }
        if role in canonical and normalized in chinese_role_names:
            return canonical[role]
        peak_match = re.fullmatch(r"(?:峰|分峰|组分峰)(\d+)", normalized)
        if role == "component" and peak_match:
            return f"Peak {peak_match.group(1)}"
        return column

    series: list[XpsSeriesSpec] = []
    if roles.raw is not None:
        series.append(XpsSeriesSpec(roles.raw, label(roles.raw, "raw"), "raw"))
    if roles.background is not None:
        series.append(
            XpsSeriesSpec(roles.background, label(roles.background, "background"), "background")
        )
    series.extend(
        XpsSeriesSpec(component, label(component, "component"), "component")
        for component in roles.components
    )
    if roles.envelope is not None:
        series.append(XpsSeriesSpec(roles.envelope, label(roles.envelope, "envelope"), "envelope"))
    if roles.residual is not None:
        series.append(XpsSeriesSpec(roles.residual, label(roles.residual, "residual"), "residual"))
    return tuple(series)


def _warnings_and_confidence(
    detection: XpsDetection,
    roles: XpsColumnRoles,
    component_basis: ComponentBasis,
    ignored_empty_rows: int,
    raw_role_inferred: bool,
) -> tuple[tuple[str, ...], float]:
    warnings: list[str] = []
    confidence = 1.0
    if ignored_empty_rows:
        warnings.append("empty_rows_ignored")
    if detection.energy_kind == "unknown":
        warnings.append("energy_kind_unknown")
        confidence -= 0.2
    if detection.spectrum_region == "unknown":
        warnings.append("spectrum_region_unknown")
        confidence -= 0.15
    if roles.raw is None:
        warnings.append("raw_series_missing")
        confidence -= 0.1
    elif raw_role_inferred:
        warnings.append("raw_role_inferred")
        confidence -= 0.15
    if roles.components and component_basis == "unresolved":
        warnings.append("component_basis_unresolved")
        confidence -= 0.2
    return tuple(warnings), round(max(confidence, 0.0), 2)


def _energy_kind_from_name(column: str) -> EnergyKind:
    name = _normalize(column)
    if name.startswith("binding") or name in {"be", "beev", "结合能", "束缚能", "结合能ev"}:
        return "binding"
    if name.startswith("kinetic") or name in {"ke", "keev", "动能", "动力学能", "动能ev"}:
        return "kinetic"
    return "unknown"


def _numeric_rows(
    loaded: LoadedTable, *, ignored_columns: tuple[str, ...] = ()
) -> tuple[list[str], list[list[float]]]:
    columns = list(loaded.columns)
    ignored = set(ignored_columns)
    rows: list[list[float]] = []
    for row_number, values in enumerate(loaded.frame.itertuples(index=False, name=None), start=2):
        numeric_row: list[float] = []
        for column, cell in zip(columns, values):
            if column in ignored:
                numeric_row.append(math.nan)
                continue
            if pd.isna(cell) or (isinstance(cell, str) and not cell.strip()):
                raise XpsWorkflowError(
                    "missing_value",
                    f"Row {row_number}, column {column!r} is empty.",
                    column=column,
                    row=row_number,
                )
            try:
                value = float(str(cell).strip()) if isinstance(cell, str) else float(cell)
            except (TypeError, ValueError) as exc:
                raise XpsWorkflowError(
                    "non_numeric",
                    f"Row {row_number}, column {column!r} is not numeric.",
                    column=column,
                    row=row_number,
                ) from exc
            if not math.isfinite(value):
                raise XpsWorkflowError(
                    "non_finite",
                    f"Row {row_number}, column {column!r} is not finite.",
                    column=column,
                    row=row_number,
                )
            numeric_row.append(value)
        rows.append(numeric_row)
    return columns, rows


def _roles_from_confirmed_mapping(
    columns: list[str], mapping: XpsColumnMapping
) -> XpsColumnRoles:
    assigned = [
        mapping.x,
        mapping.raw,
        *(item for item in (mapping.background, mapping.envelope, mapping.residual) if item),
        *mapping.components,
        *mapping.ignored,
    ]
    unknown = [column for column in assigned if column not in columns]
    if unknown:
        raise XpsWorkflowError(
            "mapping_unknown_column",
            f"Mapped column does not exist: {unknown[0]!r}.",
            column=unknown[0],
        )
    duplicate = next(
        (column for index, column in enumerate(assigned) if column in assigned[:index]), None
    )
    if duplicate is not None:
        raise XpsWorkflowError(
            "mapping_role_conflict",
            f"Column {duplicate!r} is assigned to more than one role.",
            column=duplicate,
        )
    unassigned = [column for column in columns if column not in assigned]
    if unassigned:
        raise XpsWorkflowError(
            "mapping_incomplete",
            f"Column {unassigned[0]!r} must be assigned or ignored.",
            column=unassigned[0],
        )
    return XpsColumnRoles(
        mapping.x,
        mapping.raw,
        mapping.background,
        mapping.envelope,
        mapping.residual,
        mapping.components,
        mapping.ignored,
    )


def prepare_xps(
    path: str | Path,
    *,
    column_mapping: XpsColumnMapping | None = None,
) -> XpsPreparation:
    """Read and classify an XPS table without writing to the source file."""
    try:
        loaded = load_table(path)
    except DataLoadError as exc:
        raise XpsWorkflowError(
            exc.code,
            str(exc),
            column=exc.column,
            row=exc.row,
        ) from exc
    if len(loaded.columns) < 2:
        raise XpsWorkflowError(
            "too_few_columns",
            "XPS data needs an energy column and at least one series.",
        )
    source_path = Path(loaded.source_path)
    ignored = column_mapping.ignored if column_mapping is not None else ()
    columns, rows = _numeric_rows(loaded, ignored_columns=ignored)

    if column_mapping is not None:
        roles = _roles_from_confirmed_mapping(columns, column_mapping)
        energy_column = roles.x
        energy_kind: EnergyKind = column_mapping.energy_kind
        raw_role_inferred = False
        ambiguous_reasons: tuple[str, ...] = ()
    else:
        energy_column = _first(
            columns,
            {
                "bindingenergy",
                "bindingenergye",
                "bindingenergyev",
                "kineticenergy",
                "kineticenergye",
                "kineticenergyev",
                "be",
                "beev",
                "ke",
                "keev",
                "结合能",
                "结合能ev",
                "束缚能",
                "动能",
                "动能ev",
                "动力学能",
            },
        ) or columns[0]
        energy_kind = _energy_kind_from_name(energy_column)
        y_columns = [column for column in columns if column != energy_column]
        background_matches = [column for column in y_columns if _is_background_name(_normalize(column))]
        envelope_matches = [column for column in y_columns if _is_envelope_name(_normalize(column))]
        residual_matches = [column for column in y_columns if _is_residual_name(_normalize(column))]
        background = background_matches[0] if background_matches else None
        envelope = envelope_matches[0] if envelope_matches else None
        residual = residual_matches[0] if residual_matches else None
        reserved = {item for item in (background, envelope, residual) if item is not None}
        raw_matches = [
            column
            for column in y_columns
            if column not in reserved and _is_raw_name(_normalize(column))
        ]
        raw = raw_matches[0] if raw_matches else None
        raw_role_inferred = raw is None
        if raw is None:
            raw = next((column for column in y_columns if column not in reserved), None)
        components = tuple(column for column in y_columns if column not in reserved and column != raw)
        roles = XpsColumnRoles(energy_column, raw, background, envelope, residual, components)
        ambiguous_reasons = tuple(
            reason
            for reason, matches in (
                ("background_role_ambiguous", background_matches),
                ("envelope_role_ambiguous", envelope_matches),
                ("residual_role_ambiguous", residual_matches),
                ("raw_role_ambiguous", raw_matches),
            )
            if len(matches) > 1
        )

    background = roles.background
    envelope = roles.envelope
    residual = roles.residual
    components = roles.components
    mode: XpsMode = "fit_with_residual" if residual else ("fit" if envelope or components else "scan")
    energy_index = columns.index(energy_column)
    energy_values = [row[energy_index] for row in rows]
    _validate_energy_values(energy_values, energy_column)
    region = _detect_region(source_path, columns, energy_kind, energy_values)
    is_fixed_c1s = (
        tuple(columns) == FIXED_C1S_COLUMNS
        and region == "C1s"
        and energy_kind == "binding"
        and min(energy_values) <= FIXED_C1S_DISPLAY_RIGHT_EV
        and max(energy_values) >= FIXED_C1S_DISPLAY_LEFT_EV
    )
    profile: VisualProfile = "fixed_c1s_publication" if is_fixed_c1s else "adaptive_counts"
    component_basis: ComponentBasis = (
        "relative_to_background" if is_fixed_c1s else _infer_component_basis(columns, rows, roles)
    )
    detection = XpsDetection(energy_kind, region, mode)
    axis = _fixed_c1s_axis_plan(energy_values) if is_fixed_c1s else _axis_plan(energy_kind, energy_values)
    helpers = _fixed_helpers(roles) if is_fixed_c1s else _adaptive_helpers(roles, energy_kind, component_basis)
    plot_spec = XpsPlotSpec(
        visual_profile=profile,
        axis=axis,
        series=_series_specs(roles, fixed_c1s=is_fixed_c1s),
        fill_baseline=background if background is not None else "axis_floor",
        component_basis=component_basis,
        residual_policy="preserve_not_plotted",
        helpers=helpers,
    )
    warnings, confidence = _warnings_and_confidence(
        detection, roles, component_basis, loaded.ignored_empty_rows, raw_role_inferred
    )
    confirmation_reasons = ()
    if column_mapping is None:
        confirmation_reasons = tuple(
            dict.fromkeys(
                [
                    *ambiguous_reasons,
                    *(
                        reason
                        for reason in (
                            "energy_kind_unknown",
                            "raw_role_inferred",
                            "component_basis_unresolved",
                        )
                        if reason in warnings
                    ),
                    *(("low_confidence",) if confidence < 0.8 else ()),
                ]
            )
        )
    requires_confirmation = bool(confirmation_reasons)
    digest_payload = {
        "source_sha256": loaded.source_sha256,
        "source_format": loaded.source_format,
        "source_sheet": loaded.sheet_name,
        "source_delimiter": loaded.delimiter,
        "source_columns": columns,
        "row_count": len(rows),
        "ignored_empty_rows": loaded.ignored_empty_rows,
        "detection": detection.to_dict(),
        "roles": roles.to_dict(),
        "component_basis": component_basis,
        "plot_spec": plot_spec.to_dict(),
        "warnings": list(warnings),
        "confidence": confidence,
        "mapping_confirmed": column_mapping is not None,
        "requires_confirmation": requires_confirmation,
        "confirmation_reasons": list(confirmation_reasons),
    }
    plan_digest = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return XpsPreparation(
        source_path=str(source_path),
        source_sha256=loaded.source_sha256,
        source_size_bytes=loaded.source_size_bytes,
        source_format=loaded.source_format,
        source_sheet=loaded.sheet_name,
        source_delimiter=loaded.delimiter,
        source_columns=tuple(columns),
        row_count=len(rows),
        ignored_empty_rows=loaded.ignored_empty_rows,
        detection=detection,
        roles=roles,
        component_basis=component_basis,
        plot_spec=plot_spec,
        warnings=warnings,
        confidence=confidence,
        column_mapping=column_mapping,
        mapping_confirmed=column_mapping is not None,
        requires_confirmation=requires_confirmation,
        confirmation_reasons=confirmation_reasons,
        plan_digest=plan_digest,
    )


def load_xps_frame(path: str | Path, preparation: XpsPreparation) -> pd.DataFrame:
    """Materialize the numeric runner frame for an already confirmed plan."""
    try:
        loaded = load_table(path)
    except DataLoadError as exc:
        raise XpsWorkflowError(
            exc.code, str(exc), column=exc.column, row=exc.row
        ) from exc
    if loaded.source_sha256 != preparation.source_sha256:
        raise XpsWorkflowError(
            "analysis_changed",
            "The source table changed after analysis. Refresh and confirm the preview again.",
        )
    if loaded.columns != preparation.source_columns:
        raise XpsWorkflowError(
            "analysis_changed",
            "The source columns changed after analysis. Refresh and confirm the preview again.",
        )
    columns, rows = _numeric_rows(loaded, ignored_columns=preparation.roles.ignored)
    included = [column for column in columns if column not in preparation.roles.ignored]
    indexes = [columns.index(column) for column in included]
    return pd.DataFrame(
        [[row[index] for index in indexes] for row in rows],
        columns=included,
    )
