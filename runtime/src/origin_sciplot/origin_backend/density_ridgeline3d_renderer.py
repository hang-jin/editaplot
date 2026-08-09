"""Verified Origin renderer for ordered dual-density ridgelines in 3D.

The route uses the documented ``plotxyz`` type 240 / ``glTraject`` path.  It
draws two source-supplied density profiles and one source-supplied focal X
position per condition.  The only derived coordinate is the approved focal
baseline Z value of zero.  No KDE, normalization, smoothing, interpolation,
Waterfall plot, fill-area command, or More Colors parameter is used here.

The focal marker shape is deliberately left at the ``glTraject`` template
default.  The isolated Origin 2024b experiment proved its visibility, size,
colour, Z=0 binding, label, and disabled drop lines, but did not establish a
portable shape-write/readback contract.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from origin_sciplot.logging_utils import RunLogger
from origin_sciplot.output_manager import RunOutput, write_json
from origin_sciplot.scientific_visual import palette_colors
from origin_sciplot.scientific_workflow import ScientificPreparation, prepare_scientific
from origin_sciplot.template_registry import TemplateManifest

from .base_style_contract import pt_to_origin_width_units
from .export_utils import export_graph
from .safe_errors import OriginDrawError
from .session import OriginSession
from .verify_utils import read_layer_geometry_percent, require_nonempty

PLOTXYZ_TYPE = 240
GLTRAJECT_TEMPLATE = "glTraject"
OFFICIAL_PLOTXYZ_REFERENCE = "https://docs.originlab.com/x-function/ref/plotxyz/"
OFFICIAL_TRAJECTORY_REFERENCE = "https://docs.originlab.com/origin-help/trajectory-graph/"
OFFICIAL_RANGE_REFERENCE = "https://docs.originlab.com/labtalk/guide/range-notation/"
OFFICIAL_PLOTDATA_REFERENCE = "https://docs.originlab.com/labtalk/ref/plotdata-func/"
OFFICIAL_NAMEOF_REFERENCE = "https://docs.originlab.com/labtalk/ref/nameof-func/"
OFFICIAL_LAYER_REFERENCE = "https://docs.originlab.com/labtalk/ref/layer-obj/"

CURVE_CONNECTION = 1
SOLID_LINE_STYLE = 0
DASHED_LINE_STYLE = 1
FOCAL_CONNECTION = 0
FOCAL_LINE_STYLE = 0
FOCAL_LINE_WIDTH_UNITS = 900
FOCAL_MARKER_SIZE_PT = 9
FOCAL_LABEL_SIZE_PT = 15
FOCAL_COLOR = "#A66224"

AXIS_EXPECTED_STATE = {
    "show_axes": 3,
    "show_labels": 3,
    "show_label": 1,
    "ticks": 10,
    "minor_ticks": 1,
}
AXIS_STATE_PROPERTIES = {
    "show_axes": "showAxes",
    "show_labels": "showLabels",
    "show_label": "showlabel",
    "ticks": "ticks",
    "minor_ticks": "minorTicks",
}
CAMERA_EXPECTED_STATE = {
    "azimuth": 310.0,
    "inclination": 15.8,
    "roll": 0.2,
}
CAMERA_ALLOWED_RANGES = {
    "azimuth": (0.0, 360.0),
    "inclination": (-90.0, 90.0),
    "roll": (-180.0, 180.0),
}
CAMERA_TOLERANCE = 0.3


@dataclass(frozen=True)
class DensityRidgeline3DPlotMapping:
    condition: str
    condition_position: float
    role: str
    row_count: int
    source_category: str
    source_x: str
    source_y: str
    source_z: str | None
    helper_x: str
    helper_y: str
    helper_z: str
    z_derivation: str | None = None


@dataclass(frozen=True)
class DensityRidgeline3DHelperPlan:
    frame: pd.DataFrame
    mappings: tuple[DensityRidgeline3DPlotMapping, ...]
    helper_columns: tuple[str, ...]
    source_frame_unchanged: bool = True


def _safe_helper_name(prefix: str, condition: str, index: int) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "_", condition).strip("_") or f"Condition_{index}"
    return f"__D3_{index}_{prefix}_{base}"[:72]


def _series_columns(preparation: ScientificPreparation) -> dict[str, str]:
    result = {
        str(series.series_role): str(series.source_column)
        for series in preparation.plot_spec.series
    }
    required = {"density_solid", "density_dashed"}
    if set(result) != required:
        raise OriginDrawError(
            "density_ridgeline3d needs exactly one solid-density and one dashed-density series."
        )
    return result


def build_density_ridgeline3d_helper_plan(
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> DensityRidgeline3DHelperPlan:
    """Build Origin-only XYZ triplets without modifying the validated source."""

    spec = preparation.plot_spec
    if (
        preparation.template_id != "density_ridgeline3d"
        or spec.plot_kind != "density_ridgeline3d"
        or spec.x_column is None
        or spec.y_column is None
        or spec.category_column is None
        or spec.focal_x_column is None
        or not spec.group_order
    ):
        raise OriginDrawError("The density_ridgeline3d preparation is incomplete.")
    series_columns = _series_columns(preparation)
    positions = dict(spec.condition_positions)
    if tuple(positions) != spec.group_order or len(positions) != len(spec.group_order):
        raise OriginDrawError("density_ridgeline3d condition positions are incomplete or out of order.")

    source_snapshot = frame.copy(deep=True)
    labels = frame[spec.category_column].astype(str).str.strip()
    subsets = {
        condition: frame.loc[labels == condition].reset_index(drop=True)
        for condition in spec.group_order
    }
    if any(subset.empty for subset in subsets.values()):
        raise OriginDrawError("density_ridgeline3d contains an empty condition group.")
    maximum = max(len(subset) for subset in subsets.values())
    helper = pd.DataFrame(index=np.arange(maximum, dtype=int))
    mappings: list[DensityRidgeline3DPlotMapping] = []
    helper_columns: list[str] = []

    def add_triplet(
        *,
        condition_index: int,
        condition: str,
        role: str,
        x_values: np.ndarray,
        y_values: np.ndarray,
        z_values: np.ndarray,
        source_x: str,
        source_z: str | None,
        z_derivation: str | None = None,
    ) -> None:
        plot_index = len(mappings) + 1
        names = (
            _safe_helper_name(f"{role}_X", condition, plot_index),
            _safe_helper_name(f"{role}_Y", condition, plot_index),
            _safe_helper_name(f"{role}_Z", condition, plot_index),
        )
        for name, values in zip(names, (x_values, y_values, z_values), strict=True):
            helper[name] = pd.Series(values, index=np.arange(len(values), dtype=int))
            helper_columns.append(name)
        mappings.append(
            DensityRidgeline3DPlotMapping(
                condition=condition,
                condition_position=float(positions[condition]),
                role=role,
                row_count=len(x_values),
                source_category=spec.category_column,
                source_x=source_x,
                source_y=spec.y_column,
                source_z=source_z,
                helper_x=names[0],
                helper_y=names[1],
                helper_z=names[2],
                z_derivation=z_derivation,
            )
        )
        del condition_index  # retained in the call site to make ordering explicit

    for condition_index, condition in enumerate(spec.group_order, start=1):
        subset = subsets[condition]
        x_values = subset[spec.x_column].to_numpy(dtype=float, copy=True)
        y_values = subset[spec.y_column].to_numpy(dtype=float, copy=True)
        for role in ("density_solid", "density_dashed"):
            source_z = series_columns[role]
            add_triplet(
                condition_index=condition_index,
                condition=condition,
                role=role,
                x_values=x_values,
                y_values=y_values,
                z_values=subset[source_z].to_numpy(dtype=float, copy=True),
                source_x=spec.x_column,
                source_z=source_z,
            )

        focal_values = pd.to_numeric(subset[spec.focal_x_column], errors="coerce").dropna()
        if len(focal_values) != 1:
            raise OriginDrawError(
                f"density_ridgeline3d condition {condition!r} must contain one focal X value."
            )
        focal_x = np.asarray([float(focal_values.iloc[0])], dtype=float)
        focal_y = np.asarray([float(positions[condition])], dtype=float)
        focal_z = np.zeros(1, dtype=float)
        add_triplet(
            condition_index=condition_index,
            condition=condition,
            role="focal",
            x_values=focal_x,
            y_values=focal_y,
            z_values=focal_z,
            source_x=spec.focal_x_column,
            source_z=None,
            z_derivation="scale_by_constant(factor=0)",
        )

    try:
        pd.testing.assert_frame_equal(frame, source_snapshot, check_dtype=True)
    except AssertionError as exc:
        raise OriginDrawError("density_ridgeline3d helper preparation modified the source frame.") from exc
    return DensityRidgeline3DHelperPlan(
        frame=helper,
        mappings=tuple(mappings),
        helper_columns=tuple(helper_columns),
        source_frame_unchanged=True,
    )


def density_ridgeline3d_style_commands(
    role: str,
    *,
    color: str,
    font_code: int,
    curve_width_units: int,
) -> tuple[str, ...]:
    """Return only commands proved by the isolated Origin 2024b experiment."""

    if role in {"density_solid", "density_dashed"}:
        line_style = SOLID_LINE_STYLE if role == "density_solid" else DASHED_LINE_STYLE
        return (
            f"-so -l {CURVE_CONNECTION}",
            f"-so -d {line_style}",
            f"-so -w {curve_width_units}",
            f"-so -c color({color})",
            "-so -k 0",
            "-so -z 0",
            "-so -lh 0",
            "-so -lv 0",
            "-so -lo 0",
            "-so -q 0",
        )
    if role == "focal":
        # Do not add -k/-kf here.  Focal shape is not a verified contract.
        return (
            f"-so -l {FOCAL_CONNECTION}",
            f"-so -d {FOCAL_LINE_STYLE}",
            f"-so -w {FOCAL_LINE_WIDTH_UNITS}",
            f"-so -c color({color})",
            f"-so -z {FOCAL_MARKER_SIZE_PT}",
            "-so -lh 0",
            "-so -lv 0",
            "-so -lo 0",
            "-so -q 1",
            "-so -qm 1",
            f"-so -qf {font_code}",
            f"-so -qs {FOCAL_LABEL_SIZE_PT}",
            "-so -qp 4",
            "-so -qw 0",
        )
    raise OriginDrawError(f"Unknown density_ridgeline3d plot role: {role!r}")


def _origin_plain_legend_label(value: str) -> str:
    """Return literal legend text without user-controlled Origin escape syntax."""

    text = str(value).strip()
    if not text or any(character in text for character in "\r\n\x00"):
        raise OriginDrawError(
            "density_ridgeline3d legend labels must be non-empty printable single lines."
        )
    return text.translate(str.maketrans({"\\": "＼", "%": "％", "$": "＄"}))


def density_ridgeline3d_legend_text(solid_label: str, dashed_label: str) -> str:
    """Build a semantic legend while keeping user labels literal."""

    solid = _origin_plain_legend_label(solid_label)
    dashed = _origin_plain_legend_label(dashed_label)
    return (
        rf"\l(1) {solid}    \l(2) {dashed}    "
        r"\l(3) Baseline focal locator"
    )


def _require_lt(result: Any, operation: str) -> None:
    if result is False:
        raise OriginDrawError(f"Origin rejected documented operation: {operation}")


def _finite(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or abs(number) > 1e100:
        raise OriginDrawError(f"Origin returned an invalid value for {name}: {number!r}")
    return number


def _close(actual: float, expected: float, name: str, tolerance: float = 0.05) -> None:
    if abs(actual - expected) > tolerance:
        raise OriginDrawError(
            f"Origin readback mismatch for {name}: {actual:g}, expected {expected:g}"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_original_plot_option(
    op: Any,
    plot: Any,
    option: str,
    *,
    plot_index: int,
    option_index: int,
) -> float:
    variable = f"__dr{plot_index}_{option_index}"
    _require_lt(
        plot.layer.LT_execute(
            f"{{range __drp={plot.lt_range()};get __drp -so {option} {variable};}}"
        ),
        f"get -so {option}",
    )
    return _finite(op.lt_float(variable), f"plot option -so {option}")


def _read_plot_state(op: Any, plot: Any, role: str, plot_index: int) -> dict[str, float]:
    options: list[tuple[str, str]] = [
        ("-l", "connection"),
        ("-d", "line_style"),
        ("-w", "line_width"),
        ("-c", "color"),
    ]
    if role in {"density_solid", "density_dashed"}:
        options.extend(
            (
                ("-k", "symbol_kind"),
                ("-z", "symbol_size"),
                ("-lh", "drop_horizontal"),
                ("-lv", "drop_vertical"),
                ("-lo", "drop_other"),
                ("-q", "label_enabled"),
            )
        )
    else:
        options.extend(
            (
                ("-z", "symbol_size"),
                ("-lh", "drop_horizontal"),
                ("-lv", "drop_vertical"),
                ("-lo", "drop_other"),
                ("-q", "label_enabled"),
                ("-qm", "label_form"),
                ("-qf", "label_font"),
                ("-qs", "label_size"),
                ("-qp", "label_position"),
                ("-qw", "label_whiteout"),
            )
        )
    return {
        name: _read_original_plot_option(
            op,
            plot,
            option,
            plot_index=plot_index,
            option_index=option_index,
        )
        for option_index, (option, name) in enumerate(options)
    }


def _verify_plot_state(
    state: dict[str, float],
    role: str,
    *,
    expected_color: float,
    expected_curve_width: float,
    font_code: int,
) -> None:
    expected: dict[str, float]
    if role in {"density_solid", "density_dashed"}:
        expected = {
            "connection": float(CURVE_CONNECTION),
            "line_style": float(
                SOLID_LINE_STYLE if role == "density_solid" else DASHED_LINE_STYLE
            ),
            "line_width": expected_curve_width,
            "color": expected_color,
            "symbol_kind": 0.0,
            "symbol_size": 0.0,
            "drop_horizontal": 0.0,
            "drop_vertical": 0.0,
            "drop_other": 0.0,
            "label_enabled": 0.0,
        }
    else:
        expected = {
            "connection": float(FOCAL_CONNECTION),
            "line_style": float(FOCAL_LINE_STYLE),
            "line_width": float(FOCAL_LINE_WIDTH_UNITS),
            "color": expected_color,
            "symbol_size": float(FOCAL_MARKER_SIZE_PT),
            "drop_horizontal": 0.0,
            "drop_vertical": 0.0,
            "drop_other": 0.0,
            "label_enabled": 1.0,
            "label_form": 1.0,
            "label_font": float(font_code),
            "label_size": float(FOCAL_LABEL_SIZE_PT),
            "label_position": 4.0,
            "label_whiteout": 0.0,
        }
    for name, value in expected.items():
        tolerance = 1.0 if name == "line_width" else 0.5 if name == "color" else 0.05
        _close(float(state[name]), float(value), f"{role} {name}", tolerance)


def _verify_plot_binding_state(
    state: dict[str, Any],
    mapping: DensityRidgeline3DPlotMapping,
) -> None:
    """Fail unless all three plotted datasets are the mapped helper columns."""

    expected_helpers = {
        "x": mapping.helper_x,
        "y": mapping.helper_y,
        "z": mapping.helper_z,
    }
    for designation, helper_column in expected_helpers.items():
        component = state.get(designation)
        if not isinstance(component, dict):
            raise OriginDrawError(
                f"Origin {mapping.role} {designation.upper()} binding readback is missing."
            )
        if component.get("helper_column") != helper_column:
            raise OriginDrawError(
                f"Origin {mapping.role} {designation.upper()} helper mapping changed."
            )
        actual_dataset = str(component.get("actual_dataset", ""))
        expected_dataset = str(component.get("expected_dataset", ""))
        if not actual_dataset or actual_dataset != expected_dataset:
            raise OriginDrawError(
                f"Origin {mapping.role} {designation.upper()} dataset binding mismatch: "
                f"{actual_dataset!r}, expected {expected_dataset!r}."
            )
        for key in ("actual_range", "expected_range"):
            if not str(component.get(key, "")):
                raise OriginDrawError(
                    f"Origin {mapping.role} {designation.upper()} {key} is empty."
                )
        for key in ("numeric_count", "expected_numeric_count", "plotdata_numeric_count"):
            if int(component.get(key, -1)) != mapping.row_count:
                raise OriginDrawError(
                    f"Origin {mapping.role} {designation.upper()} {key} is "
                    f"{component.get(key)!r}, expected {mapping.row_count}."
                )


def _read_plot_binding(
    op: Any,
    layer: Any,
    plot: Any,
    helper_sheet: Any,
    helper_column_order: tuple[str, ...],
    mapping: DensityRidgeline3DPlotMapping,
    plot_index: int,
) -> dict[str, Any]:
    """Read plotted X/Y/Z worksheet columns through official graph ranges."""

    state: dict[str, Any] = {
        "plot_index": plot_index,
        "plot_range": plot.lt_range(),
        "expected_row_count": mapping.row_count,
    }
    mapped_helpers = {
        "x": mapping.helper_x,
        "y": mapping.helper_y,
        "z": mapping.helper_z,
    }
    range_switches = {"x": "-wx", "y": "-wy", "z": "-wz"}
    for designation_offset, designation in enumerate(("x", "y", "z")):
        helper_column = mapped_helpers[designation]
        try:
            column_index = helper_column_order.index(helper_column) + 1
        except ValueError as exc:
            raise OriginDrawError(
                f"Origin helper column {helper_column!r} cannot be resolved for binding readback."
            ) from exc
        expected_column_index = (plot_index - 1) * 3 + designation_offset + 1
        if column_index != expected_column_index:
            raise OriginDrawError(
                f"Origin helper mapping order changed for plot {plot_index} "
                f"{designation.upper()}: column {column_index}, expected {expected_column_index}."
            )
        actual_range = f"__d3a{plot_index}{designation}"
        expected_range = f"__d3e{plot_index}{designation}"
        actual_string = f"__d3as{plot_index}{designation}"
        expected_string = f"__d3es{plot_index}{designation}"
        actual_dataset = f"__d3ad{plot_index}{designation}"
        expected_dataset = f"__d3ed{plot_index}{designation}"
        actual_count = f"__d3ac{plot_index}{designation}"
        expected_count = f"__d3ec{plot_index}{designation}"
        plotted_count = f"__d3pc{plot_index}{designation}"
        declare_ranges = (
            f"range {range_switches[designation]} {actual_range}={plot.lt_range()};"
            f"range {expected_range}={helper_sheet.lt_range(False)}!col({column_index});"
        )
        _require_lt(
            layer.lt_exec(declare_ranges),
            f"read plot {plot_index} {designation.upper()} worksheet range",
        )
        read_values = (
            f"string {actual_string}$=%({actual_range});"
            f"string {expected_string}$=%({expected_range});"
            f"string {actual_dataset}$=nameof({actual_range})$;"
            f"string {expected_dataset}$=nameof({expected_range})$;"
            f"{actual_count}=count({actual_range},1);"
            f"{expected_count}=count({expected_range},1);"
            f"{plotted_count}=count(plotdata({plot_index},{designation.upper()}),1);"
        )
        _require_lt(
            layer.lt_exec(read_values),
            f"read plot {plot_index} {designation.upper()} binding identity and count",
        )
        state[designation] = {
            "helper_column": helper_column,
            "helper_column_index": column_index,
            "origin_long_name": str(helper_sheet.get_label(column_index - 1, "L")),
            "origin_unit": str(helper_sheet.get_label(column_index - 1, "U")),
            "origin_comment": str(helper_sheet.get_label(column_index - 1, "C")),
            "actual_range": str(op.get_lt_str(actual_string)),
            "expected_range": str(op.get_lt_str(expected_string)),
            "actual_dataset": str(op.get_lt_str(actual_dataset)),
            "expected_dataset": str(op.get_lt_str(expected_dataset)),
            "numeric_count": int(round(_finite(op.lt_float(actual_count), actual_count))),
            "expected_numeric_count": int(
                round(_finite(op.lt_float(expected_count), expected_count))
            ),
            "plotdata_numeric_count": int(
                round(_finite(op.lt_float(plotted_count), plotted_count))
            ),
        }
    _verify_plot_binding_state(state, mapping)
    state["verified"] = True
    return state


def _verify_axis_state(axis: str, state: dict[str, float | int]) -> None:
    for key, expected in AXIS_EXPECTED_STATE.items():
        actual = int(state.get(key, -1))
        if actual != expected:
            raise OriginDrawError(
                f"Origin {axis.upper()} {key} readback is {actual}, expected {expected}."
            )


def _verify_camera_state(state: dict[str, float]) -> None:
    for key, expected in CAMERA_EXPECTED_STATE.items():
        actual = _finite(state.get(key), f"camera.{key}")
        lower, upper = CAMERA_ALLOWED_RANGES[key]
        if not lower <= actual <= upper:
            raise OriginDrawError(
                f"Origin camera.{key} is outside the allowed range [{lower:g}, {upper:g}]."
            )
        _close(actual, expected, f"camera.{key}", CAMERA_TOLERANCE)


def _read_axis(layer: Any, axis: str) -> dict[str, float | int]:
    return {
        "from": _finite(layer.get_float(f"{axis}.from"), f"{axis}.from"),
        "to": _finite(layer.get_float(f"{axis}.to"), f"{axis}.to"),
        "inc": _finite(layer.get_float(f"{axis}.inc"), f"{axis}.inc"),
        "show_axes": int(layer.get_int(f"{axis}.showAxes")),
        "show_labels": int(layer.get_int(f"{axis}.showLabels")),
        "show_label": int(layer.get_int(f"{axis}.showlabel")),
        "ticks": int(layer.get_int(f"{axis}.ticks")),
        "minor_ticks": int(layer.get_int(f"{axis}.minorTicks")),
        "label_font": int(round(layer.get_float(f"{axis}.label.font"))),
        "label_pt": _finite(layer.get_float(f"{axis}.label.pt"), f"{axis}.label.pt"),
    }


def _header_parts(header: str) -> tuple[str, str]:
    match = re.search(r"[\(\[]\s*([^\)\]]+)\s*[\)\]]\s*$", header)
    if match is None:
        return header, ""
    return header[: match.start()].strip(), match.group(1).strip()


def density_ridgeline3d_helper_column_metadata(
    mapping: DensityRidgeline3DPlotMapping,
    *,
    x_title: str,
    y_title: str,
    z_title: str,
) -> tuple[tuple[str, str, str], ...]:
    """Return editable Long Name, Unit, and Comments for one XYZ triplet."""

    x_meaning, x_unit = _header_parts(x_title)
    y_meaning, y_unit = _header_parts(y_title)
    z_meaning, z_unit = _header_parts(z_title)
    comment = f"{mapping.condition}: {mapping.role}"
    if mapping.role == "focal":
        comment = f"{comment}; {mapping.z_derivation}"
        z_meaning = "Baseline locator Z"
    return (
        (x_meaning or x_title, x_unit, comment),
        (y_meaning or y_title, y_unit, comment),
        (z_meaning or z_title, z_unit, comment),
    )


def _labtalk_string(value: str) -> str:
    if any(character in value for character in "\r\n\x00"):
        raise OriginDrawError("density_ridgeline3d axis titles must be one printable line.")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _resolve_preparation(
    manifest: TemplateManifest,
    frame: pd.DataFrame,
    output: RunOutput,
    preparation: ScientificPreparation | None,
) -> ScientificPreparation:
    resolved = preparation or prepare_scientific(output.input_copy, manifest.id)
    if resolved.template_id != "density_ridgeline3d" or manifest.id != "density_ridgeline3d":
        raise OriginDrawError("The density_ridgeline3d runner received a different template plan.")
    if tuple(map(str, frame.columns)) != resolved.source_columns:
        raise OriginDrawError(
            "density_ridgeline3d columns do not match the validated source copy."
        )
    if resolved.requires_confirmation:
        raise OriginDrawError("Column mapping confirmation is required before Origin can run.")
    return resolved


def _build_graph(
    op: Any,
    frame: pd.DataFrame,
    output: RunOutput,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    spec = preparation.plot_spec
    style = spec.display_plan.figure_style
    if style is None or spec.y_column is None or spec.z_title is None:
        raise OriginDrawError("density_ridgeline3d adaptive style or axis plan is missing.")
    helper_plan = build_density_ridgeline3d_helper_plan(frame, preparation)

    source_sheet = op.new_sheet("w", "Density3D Source")
    helper_sheet = op.new_sheet("w", "Density3D Plot Helpers")
    if source_sheet is None or helper_sheet is None:
        raise OriginDrawError("Origin could not create the density_ridgeline3d worksheets.")
    source_sheet.from_df(frame.copy(deep=True))
    helper_sheet.from_df(helper_plan.frame)
    helper_sheet.cols_axis("xyz" * len(helper_plan.mappings))
    for index, mapping in enumerate(helper_plan.mappings):
        metadata = density_ridgeline3d_helper_column_metadata(
            mapping,
            x_title=spec.x_title,
            y_title=spec.y_title,
            z_title=spec.z_title,
        )
        for offset, (meaning, unit, comment) in enumerate(metadata):
            column = index * 3 + offset
            helper_sheet.set_label(column, meaning, "L")
            if unit:
                helper_sheet.set_label(column, unit, "U")
            helper_sheet.set_label(column, comment, "C")

    commands: list[str] = []
    helper_sheet.activate()
    first = (
        f"plotxyz iz:=(1,2,3) plot:={PLOTXYZ_TYPE} "
        f"ogl:=<new template:={GLTRAJECT_TEMPLATE}>;"
    )
    _require_lt(op.lt_exec(first), "plotxyz glTraject")
    commands.append(first)
    graph = op.find_graph()
    if graph is None or len(graph) != 1:
        raise OriginDrawError("Origin did not create one glTraject graph layer.")
    layer = graph[0]
    target_layer = f"{layer.lt_range()}!"
    for plot_index in range(1, len(helper_plan.mappings)):
        start = plot_index * 3 + 1
        helper_sheet.activate()
        command = (
            f"plotxyz iz:=({start},{start + 1},{start + 2}) plot:={PLOTXYZ_TYPE} "
            f"ogl:={target_layer};"
        )
        _require_lt(op.lt_exec(command), f"add density_ridgeline3d plot {plot_index + 1}")
        commands.append(command)

    graph.activate()
    plots = list(layer.plot_list())
    if len(plots) != len(helper_plan.mappings):
        raise OriginDrawError(
            f"Origin created {len(plots)} plots; expected {len(helper_plan.mappings)}."
        )

    _require_lt(
        graph.obj.LT_execute("page.updatetoprinter=0;page.kar=0;"),
        "disable printer page coupling",
    )
    graph.obj.PutWidth(style.page_width_cm / 2.54)
    graph.obj.PutHeight(style.page_height_cm / 2.54)
    layer_top = max(float(style.layer_top_percent), 14.0)
    layer_height = min(float(style.layer_height_percent), 88.0 - layer_top)
    layer.set_int("unit", 1)
    layer.set_float("left", style.layer_left_percent)
    layer.set_float("top", layer_top)
    layer.set_float("width", style.layer_width_percent)
    layer.set_float("height", layer_height)
    layer.set_int("fixed", 1)
    layer.set_float("factor", 1.0)

    axis_contracts = {
        "x": (spec.axis_plan.x_from, spec.axis_plan.x_to, spec.axis_plan.x_step),
        "y": (spec.axis_plan.y_from, spec.axis_plan.y_to, spec.axis_plan.y_step),
        "z": (spec.axis_plan.z_from, spec.axis_plan.z_to, spec.axis_plan.z_step),
    }
    for axis, values in axis_contracts.items():
        if any(value is None for value in values):
            raise OriginDrawError(f"density_ridgeline3d {axis.upper()} axis contract is incomplete.")
        layer.set_float(f"{axis}.from", float(values[0]))
        layer.set_float(f"{axis}.to", float(values[1]))
        layer.set_float(f"{axis}.inc", float(values[2]))
        for state_name, property_name in AXIS_STATE_PROPERTIES.items():
            layer.set_int(f"{axis}.{property_name}", AXIS_EXPECTED_STATE[state_name])

    font_code = int(round(float(op.lt_float(f"font({style.font_family})"))))
    for axis in ("x", "y", "z"):
        layer.set_int(f"{axis}.label.font", font_code)
        layer.set_float(f"{axis}.label.pt", style.tick_label_size_pt)
    title_command = (
        f'xb.text$="{_labtalk_string(spec.x_title)}";'
        f'yl.text$="{_labtalk_string(spec.y_title)}";'
        f'zf.text$="{_labtalk_string(spec.z_title)}";'
        f"xb.font={font_code};yl.font={font_code};zf.font={font_code};"
        f"xb.fsize={style.axis_title_size_pt};"
        f"yl.fsize={style.axis_title_size_pt};"
        f"zf.fsize={style.axis_title_size_pt};"
        "xb.show=1;yl.show=1;zf.show=1;doc -uw;"
    )
    _require_lt(layer.lt_exec(title_command), "set density_ridgeline3d axis titles and fonts")

    colors = palette_colors(style.palette_name)
    if len(colors) < len(spec.group_order):
        raise OriginDrawError("density_ridgeline3d palette does not cover every condition.")
    condition_colors = dict(zip(spec.group_order, colors, strict=False))
    curve_width_units = pt_to_origin_width_units(style.plot_line_width_pt)
    plot_state: list[dict[str, Any]] = []
    for plot_index, (plot, mapping) in enumerate(
        zip(plots, helper_plan.mappings, strict=True),
        start=1,
    ):
        color = FOCAL_COLOR if mapping.role == "focal" else condition_colors[mapping.condition]
        style_commands = density_ridgeline3d_style_commands(
            mapping.role,
            color=color,
            font_code=font_code,
            curve_width_units=curve_width_units,
        )
        plot.set_cmd(*style_commands)
        state = _read_plot_state(op, plot, mapping.role, plot_index)
        expected_color = float(op.ocolor(color))
        _verify_plot_state(
            state,
            mapping.role,
            expected_color=expected_color,
            expected_curve_width=float(curve_width_units),
            font_code=font_code,
        )
        graph.activate()
        binding_state = _read_plot_binding(
            op,
            layer,
            plot,
            helper_sheet,
            helper_plan.helper_columns,
            mapping,
            plot_index,
        )
        plot_state.append(
            {
                "index": plot_index,
                "origin_object_name": plot.name,
                "plot_range": plot.lt_range(),
                "source_mapping": asdict(mapping),
                "style_commands": list(style_commands),
                "expected_color_html": color,
                "expected_color_code": int(op.ocolor(color)),
                "data_binding": binding_state,
                **state,
                "focal_shape_written": False if mapping.role == "focal" else None,
                "focal_shape_contract": "not_set_not_asserted" if mapping.role == "focal" else None,
            }
        )

    for label_name in ("Legend", "legend"):
        native_legend = layer.label(label_name)
        if native_legend is not None:
            native_legend.remove()
    series_labels = {
        str(series.series_role): str(series.label)
        for series in spec.series
    }
    legend_text = density_ridgeline3d_legend_text(
        series_labels["density_solid"],
        series_labels["density_dashed"],
    )
    semantic_legend = layer.add_label(legend_text)
    if semantic_legend is None:
        raise OriginDrawError("Origin could not create the density semantic legend.")
    semantic_legend.name = "DensityLegend"
    semantic_legend.set_int("attach", 1)
    semantic_legend.set_int("font", font_code)
    semantic_legend.set_float("fsize", style.legend_size_pt)
    semantic_legend.set_int("frame", 0)
    semantic_legend.set_int("showframe", 0)
    _require_lt(layer.lt_exec("doc -uw;"), "refresh density semantic legend")
    page_width = _finite(op.lt_float("page.width"), "page.width")
    page_height = _finite(op.lt_float("page.height"), "page.height")
    semantic_legend.set_float("left", page_width * 0.06)
    semantic_legend.set_float("top", page_height * 0.02)
    _require_lt(layer.lt_exec("doc -uw;"), "position density semantic legend")
    legend_state = {
        "text": semantic_legend.text,
        "font": int(semantic_legend.get_int("font")),
        "size": _finite(semantic_legend.get_float("fsize"), "legend.fsize"),
        "frame": int(semantic_legend.get_int("frame")),
        "showframe": int(semantic_legend.get_int("showframe")),
        "attach": int(semantic_legend.get_int("attach")),
        "left": _finite(semantic_legend.get_float("left"), "legend.left"),
        "top": _finite(semantic_legend.get_float("top"), "legend.top"),
        "width": _finite(semantic_legend.get_float("width"), "legend.width"),
        "height": _finite(semantic_legend.get_float("height"), "legend.height"),
    }
    if (
        legend_state["text"] != legend_text
        or legend_state["font"] != font_code
        or legend_state["frame"] != 0
        or legend_state["showframe"] != 0
        or legend_state["attach"] != 1
    ):
        raise OriginDrawError(f"Origin density semantic legend readback failed: {legend_state}")
    _close(float(legend_state["size"]), style.legend_size_pt, "legend size")
    if (
        float(legend_state["left"]) < 0
        or float(legend_state["top"]) < 0
        or float(legend_state["left"]) + float(legend_state["width"]) > page_width
        or float(legend_state["top"]) + float(legend_state["height"]) > page_height
    ):
        raise OriginDrawError("Origin density semantic legend is outside the graph page.")

    layer.set_int("maxpts", 0)
    for key, expected in CAMERA_EXPECTED_STATE.items():
        layer.set_float(f"camera.{key}", expected)
    _require_lt(layer.lt_exec("doc -uw;"), "apply density 3D camera and speed settings")
    three_d = {
        "is3D": int(layer.get_int("is3D")),
        "is3DGL": int(layer.get_int("is3DGL")),
        "coortype": int(layer.get_int("coortype")),
        "maxpts": int(layer.get_int("maxpts")),
        "camera": {
            key: _finite(layer.get_float(f"camera.{key}"), f"camera.{key}")
            for key in ("azimuth", "inclination", "roll")
        },
    }
    if three_d["is3D"] != 1 or three_d["is3DGL"] != 1 or three_d["coortype"] != 16:
        raise OriginDrawError(f"Origin did not confirm the OpenGL 3D route: {three_d}")
    if three_d["maxpts"] != 0:
        raise OriginDrawError("Origin did not disable 3D speed-mode point reduction.")
    _verify_camera_state(three_d["camera"])

    axes = {axis: _read_axis(layer, axis) for axis in ("x", "y", "z")}
    for axis, expected in axis_contracts.items():
        for key, value in zip(("from", "to", "inc"), expected, strict=True):
            _close(float(axes[axis][key]), float(value), f"{axis}.{key}")
        _close(float(axes[axis]["label_pt"]), style.tick_label_size_pt, f"{axis}.label.pt")
        if int(axes[axis]["label_font"]) != font_code:
            raise OriginDrawError(f"Origin {axis.upper()} tick-label font readback failed.")
        _verify_axis_state(axis, axes[axis])

    graph.activate()
    title_state: dict[str, dict[str, Any]] = {}
    expected_titles = {"xb": spec.x_title, "yl": spec.y_title, "zf": spec.z_title}
    for name, expected_text in expected_titles.items():
        state = {
            "text": op.get_lt_str(f"{name}.text$"),
            "show": int(round(op.lt_float(f"{name}.show"))),
            "font": int(round(op.lt_float(f"{name}.font"))),
            "pt": _finite(op.lt_float(f"{name}.fsize"), f"{name}.fsize"),
        }
        if state["text"] != expected_text or state["font"] != font_code or state["show"] != 1:
            raise OriginDrawError(f"Origin title readback failed for {name}: {state}")
        _close(state["pt"], style.axis_title_size_pt, f"{name}.fsize")
        title_state[name] = state

    layer_geometry = read_layer_geometry_percent(op, layer)
    geometry = {
        "page_width_cm": graph.obj.GetWidth() * 2.54,
        "page_height_cm": graph.obj.GetHeight() * 2.54,
        **layer_geometry,
    }
    for actual, expected, name in (
        (geometry["page_width_cm"], style.page_width_cm, "page width"),
        (geometry["page_height_cm"], style.page_height_cm, "page height"),
        (geometry["left_percent"], style.layer_left_percent, "layer left"),
        (geometry["top_percent"], layer_top, "layer top"),
        (geometry["width_percent"], style.layer_width_percent, "layer width"),
        (geometry["height_percent"], layer_height, "layer height"),
    ):
        _close(float(actual), float(expected), name, 0.06)

    if output.result_opju.exists():
        raise OriginDrawError(
            "density_ridgeline3d refuses to overwrite an existing editable OPJU."
        )
    if not op.save(str(output.result_opju)):
        raise OriginDrawError("Origin did not save the editable density_ridgeline3d OPJU.")
    require_nonempty(output.result_opju)
    input_copy_hash = _sha256(output.input_copy)
    if input_copy_hash != preparation.source_sha256:
        raise OriginDrawError("The density_ridgeline3d provenance copy changed during rendering.")

    return graph, {
        "route_status": "verified",
        "template_id": "density_ridgeline3d",
        "plan_digest": preparation.plan_digest,
        "official_references": {
            "plotxyz": OFFICIAL_PLOTXYZ_REFERENCE,
            "trajectory": OFFICIAL_TRAJECTORY_REFERENCE,
            "graph_data_ranges": OFFICIAL_RANGE_REFERENCE,
            "plotdata": OFFICIAL_PLOTDATA_REFERENCE,
            "nameof": OFFICIAL_NAMEOF_REFERENCE,
            "layer_camera": OFFICIAL_LAYER_REFERENCE,
        },
        "commands": commands,
        "plot_spec": asdict(spec),
        "source_sha256": preparation.source_sha256,
        "input_copy_sha256_after_render": input_copy_hash,
        "source_columns": list(preparation.source_columns),
        "source_data_modified": not helper_plan.source_frame_unchanged,
        "origin_helper_columns": list(helper_plan.helper_columns),
        "helper_column_purpose": (
            "Condition-grouped solid/dashed XYZ triplets plus one approved focal Z=0 triplet "
            "inside the editable Origin workbook only"
        ),
        "origin_axis_state": {
            "three_d": three_d,
            "x": axes["x"],
            "y": axes["y"],
            "z": axes["z"],
            "axis_expected_state": dict(AXIS_EXPECTED_STATE),
            "camera_expected_state": dict(CAMERA_EXPECTED_STATE),
            "camera_allowed_ranges": {
                key: list(value) for key, value in CAMERA_ALLOWED_RANGES.items()
            },
        },
        "origin_page_and_layer": geometry,
        "origin_text_state": {
            "titles": title_state,
            "semantic_legend": legend_state,
            "font_family_expected": style.font_family,
            "font_code_expected": font_code,
            "axis_title_size_pt": style.axis_title_size_pt,
            "tick_label_size_pt": style.tick_label_size_pt,
            "legend_size_pt": style.legend_size_pt,
        },
        "origin_plot_state": plot_state,
        "origin_data_binding_state": [
            state["data_binding"] for state in plot_state
        ],
        "legend": {
            "native_present_after": any(layer.label(name) is not None for name in ("Legend", "legend")),
            "semantic": legend_state,
        },
        "focal_contract": {
            "shape_written": False,
            "shape_asserted": False,
            "visible_marker_contract": (
                "connection=0, size=9 pt, fixed colour, one source focal X at derived Z=0, "
                "X-value label, and all drop lines disabled"
            ),
        },
        "scientific_guardrails": {
            "kde_performed": False,
            "normalization_performed": False,
            "smoothing_performed": False,
            "interpolation_performed": False,
            "focus_inferred": False,
            "focus_x_from_user_source": True,
            "focus_z_derived_zero_only": True,
            "third_axis_from_user_source": True,
            "waterfall_used": False,
            "fill_used": False,
        },
        "origin_acceptance": "templates/density_ridgeline3d/origin_acceptance.md",
        "human_visual_qa": "pending_for_this_run",
    }


def run_density_ridgeline3d_template(
    manifest: TemplateManifest,
    frame: pd.DataFrame,
    output: RunOutput,
    logger: RunLogger,
    *,
    keep_origin_open: bool = True,
    preparation: ScientificPreparation | None = None,
) -> dict[str, Any]:
    resolved = _resolve_preparation(manifest, frame, output, preparation)
    with OriginSession(keep_open=keep_origin_open) as session:
        op = session.op
        if op is None or session.environment is None:
            raise OriginDrawError("Origin session was not initialized.")
        logger.write(f"Origin connected: version {session.environment.origin_version}")
        graph, verify_report = _build_graph(op, frame, output, resolved)
        exports = export_graph(
            op,
            graph,
            output.result_png,
            output.result_pdf,
            output.result_tif,
            raster_width=2400,
        )
        verify_report["exports"] = exports
        write_json(output.origin_verify_report, verify_report)
        write_json(
            output.environment_report,
            {
                "backend": "Origin",
                **session.environment.to_dict(),
            },
        )
        if keep_origin_open:
            session.show()
        logger.write("density_ridgeline3d Origin graph exported under the verified contract")
    return {
        "opju": str(output.result_opju),
        "png": str(output.result_png),
        "pdf": str(output.result_pdf),
        "tif": str(output.result_tif),
        "verify": verify_report,
    }


__all__ = [
    "DensityRidgeline3DHelperPlan",
    "DensityRidgeline3DPlotMapping",
    "FOCAL_MARKER_SIZE_PT",
    "GLTRAJECT_TEMPLATE",
    "PLOTXYZ_TYPE",
    "build_density_ridgeline3d_helper_plan",
    "density_ridgeline3d_helper_column_metadata",
    "density_ridgeline3d_legend_text",
    "density_ridgeline3d_style_commands",
    "run_density_ridgeline3d_template",
]
