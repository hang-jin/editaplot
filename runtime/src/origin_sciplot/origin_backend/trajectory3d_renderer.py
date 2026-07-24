"""Verified Origin 2024b renderer for real XYZ/Series long-table trajectories."""

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
from origin_sciplot.scientific_workflow import (
    ScientificPreparation,
    prepare_scientific,
)
from origin_sciplot.template_registry import TemplateManifest

from .base_style_contract import pt_to_origin_width_units
from .export_utils import export_graph
from .safe_errors import OriginDrawError
from .session import OriginSession
from .verify_utils import require_nonempty


PLOTXYZ_TYPE = 240
GLTRAJECT_TEMPLATE = "glTraject"
OFFICIAL_PLOTXYZ_REFERENCE = "https://docs.originlab.com/x-function/ref/plotxyz/"
OFFICIAL_TRAJECTORY_REFERENCE = "https://docs.originlab.com/origin-help/trajectory-graph/"


@dataclass(frozen=True)
class Trajectory3DSeriesMapping:
    label: str
    row_count: int
    source_x: str
    source_y: str
    source_z: str
    source_series: str
    helper_x: str
    helper_y: str
    helper_z: str


@dataclass(frozen=True)
class Trajectory3DHelperPlan:
    frame: pd.DataFrame
    mappings: tuple[Trajectory3DSeriesMapping, ...]
    helper_columns: tuple[str, ...]


def _safe_helper_name(prefix: str, label: str, index: int) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "_", label).strip("_") or f"Series_{index}"
    return f"__{prefix}_{index}_{base}"[:72]


def build_trajectory3d_helper_plan(
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> Trajectory3DHelperPlan:
    """Split a source-preserving long table into Origin-only XYZ triplets."""
    spec = preparation.plot_spec
    if (
        spec.plot_kind != "trajectory3d"
        or spec.x_column is None
        or spec.y_column is None
        or spec.category_column is None
        or not spec.series
    ):
        raise OriginDrawError("The trajectory3d preparation is incomplete.")
    source_z = spec.series[0].source_column
    labels = frame[spec.category_column].astype(str).str.strip()
    subsets: list[pd.DataFrame] = []
    for group in spec.group_order:
        subset = frame.loc[
            labels == group,
            [spec.x_column, spec.y_column, source_z],
        ].reset_index(drop=True)
        subsets.append(subset)
    maximum = max((len(subset) for subset in subsets), default=0)
    helper = pd.DataFrame(index=np.arange(maximum, dtype=int))
    mappings: list[Trajectory3DSeriesMapping] = []
    helper_columns: list[str] = []
    for index, (group, subset) in enumerate(zip(spec.group_order, subsets, strict=True), start=1):
        names = (
            _safe_helper_name("X", group, index),
            _safe_helper_name("Y", group, index),
            _safe_helper_name("Z", group, index),
        )
        for helper_name, source_name in zip(
            names,
            (spec.x_column, spec.y_column, source_z),
            strict=True,
        ):
            helper[helper_name] = pd.Series(
                subset[source_name].to_numpy(dtype=float, copy=True),
                index=np.arange(len(subset), dtype=int),
            )
            helper_columns.append(helper_name)
        mappings.append(
            Trajectory3DSeriesMapping(
                label=group,
                row_count=len(subset),
                source_x=spec.x_column,
                source_y=spec.y_column,
                source_z=source_z,
                source_series=spec.category_column,
                helper_x=names[0],
                helper_y=names[1],
                helper_z=names[2],
            )
        )
    return Trajectory3DHelperPlan(
        frame=helper,
        mappings=tuple(mappings),
        helper_columns=tuple(helper_columns),
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


def _read_plot_option(op: Any, plot: Any, option: str, variable: str) -> float:
    _require_lt(
        plot.layer.LT_execute(
            f"{{range __trajectory3d_plot={plot.lt_range()};"
            f"get __trajectory3d_plot {option} {variable};}}"
        ),
        f"get {option}",
    )
    return _finite(op.lt_float(variable), f"plot option {option}")


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


def _labtalk_string(value: str) -> str:
    """Escape one user-derived title for a LabTalk double-quoted string."""
    if any(character in value for character in "\r\n\x00"):
        raise OriginDrawError("trajectory3d axis titles must be one printable line.")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _resolve_preparation(
    manifest: TemplateManifest,
    frame: pd.DataFrame,
    output: RunOutput,
    preparation: ScientificPreparation | None,
) -> ScientificPreparation:
    resolved = preparation or prepare_scientific(output.input_copy, manifest.id)
    if resolved.template_id != "trajectory3d" or manifest.id != "trajectory3d":
        raise OriginDrawError("The trajectory3d runner received a different template plan.")
    if tuple(map(str, frame.columns)) != resolved.source_columns:
        raise OriginDrawError("trajectory3d columns do not match the validated source copy.")
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
        raise OriginDrawError("trajectory3d adaptive style or axis plan is missing.")
    helper_plan = build_trajectory3d_helper_plan(frame, preparation)

    source_sheet = op.new_sheet("w", "Trajectory3D Source")
    helper_sheet = op.new_sheet("w", "Trajectory3D Plot Helpers")
    if source_sheet is None or helper_sheet is None:
        raise OriginDrawError("Origin could not create the trajectory3d worksheets.")
    source_sheet.from_df(frame)
    helper_sheet.from_df(helper_plan.frame)
    helper_sheet.cols_axis("xyz" * len(helper_plan.mappings))
    for index, mapping in enumerate(helper_plan.mappings):
        for offset, title in enumerate((spec.x_title, spec.y_title, spec.z_title)):
            meaning, unit = _header_parts(title)
            column = index * 3 + offset
            helper_sheet.set_label(column, meaning or title, "L")
            if unit:
                helper_sheet.set_label(column, unit, "U")
            helper_sheet.set_label(column, mapping.label, "C")

    commands: list[str] = []
    helper_sheet.activate()
    first = f"plotxyz iz:=(1,2,3) plot:={PLOTXYZ_TYPE} ogl:=<new template:={GLTRAJECT_TEMPLATE}>;"
    _require_lt(op.lt_exec(first), "plotxyz glTraject")
    commands.append(first)
    graph = op.find_graph()
    if graph is None or len(graph) != 1:
        raise OriginDrawError("Origin did not create one glTraject graph layer.")
    layer = graph[0]
    target_layer = f"{layer.lt_range()}!"
    for series_index in range(1, len(helper_plan.mappings)):
        start = series_index * 3 + 1
        helper_sheet.activate()
        command = (
            f"plotxyz iz:=({start},{start + 1},{start + 2}) "
            f"plot:={PLOTXYZ_TYPE} ogl:={target_layer};"
        )
        _require_lt(op.lt_exec(command), f"add trajectory3d series {series_index + 1}")
        commands.append(command)

    graph.activate()
    plots = list(layer.plot_list())
    if len(plots) != len(helper_plan.mappings):
        raise OriginDrawError(
            f"Origin created {len(plots)} trajectories; expected {len(helper_plan.mappings)}."
        )

    _require_lt(
        graph.obj.LT_execute("page.updatetoprinter=0;page.kar=0;"),
        "disable printer page coupling",
    )
    graph.obj.PutWidth(style.page_width_cm / 2.54)
    graph.obj.PutHeight(style.page_height_cm / 2.54)
    layer.set_int("unit", 1)
    layer.set_float("left", style.layer_left_percent)
    layer.set_float("top", style.layer_top_percent)
    layer.set_float("width", style.layer_width_percent)
    layer.set_float("height", style.layer_height_percent)
    layer.set_int("fixed", 1)
    layer.set_float("factor", 1.0)

    axis_contracts = {
        "x": (spec.axis_plan.x_from, spec.axis_plan.x_to, spec.axis_plan.x_step),
        "y": (spec.axis_plan.y_from, spec.axis_plan.y_to, spec.axis_plan.y_step),
        "z": (spec.axis_plan.z_from, spec.axis_plan.z_to, spec.axis_plan.z_step),
    }
    for axis, values in axis_contracts.items():
        if any(value is None for value in values):
            raise OriginDrawError(f"trajectory3d {axis.upper()} axis contract is incomplete.")
        layer.set_float(f"{axis}.from", float(values[0]))
        layer.set_float(f"{axis}.to", float(values[1]))
        layer.set_float(f"{axis}.inc", float(values[2]))

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
    _require_lt(layer.lt_exec(title_command), "set trajectory3d axis titles and fonts")

    colors = palette_colors(style.palette_name)
    width_units = pt_to_origin_width_units(style.plot_line_width_pt)
    plot_state: list[dict[str, Any]] = []
    for index, (plot, mapping) in enumerate(
        zip(plots, helper_plan.mappings, strict=True), start=1
    ):
        color = colors[(index - 1) % len(colors)]
        plot.set_cmd(f"-c color({color})", f"-w {width_units}")
        color_code = _read_plot_option(op, plot, "-c", f"__trajectory3d_color_{index}")
        line_width = _read_plot_option(op, plot, "-w", f"__trajectory3d_width_{index}")
        _close(color_code, float(op.ocolor(color)), f"plot {index} color", 0.5)
        _close(line_width, float(width_units), f"plot {index} line width", 1.0)
        plot_state.append(
            {
                "index": index,
                "label": mapping.label,
                "origin_object_name": plot.name,
                "plot_range": plot.lt_range(),
                "source_mapping": asdict(mapping),
                "expected_color_html": color,
                "expected_color_code": int(op.ocolor(color)),
                "color_code": color_code,
                "line_width_units": line_width,
            }
        )

    legend = layer.label("Legend")
    legend_present_before = legend is not None
    if legend is not None:
        legend.remove()
    if layer.label("Legend") is not None:
        raise OriginDrawError("Origin did not remove the redundant trajectory3d legend.")
    _require_lt(layer.lt_exec("doc -uw;"), "refresh trajectory3d graph")

    three_d = {
        "is3D": int(layer.get_int("is3D")),
        "is3DGL": int(layer.get_int("is3DGL")),
        "coortype": int(layer.get_int("coortype")),
        "camera": {
            key: _finite(layer.get_float(f"camera.{key}"), f"camera.{key}")
            for key in ("azimuth", "inclination", "roll")
        },
    }
    if three_d["is3D"] != 1 or three_d["is3DGL"] != 1 or three_d["coortype"] != 16:
        raise OriginDrawError(f"Origin did not confirm the verified OpenGL 3D route: {three_d}")
    axes = {axis: _read_axis(layer, axis) for axis in ("x", "y", "z")}
    for axis, expected in axis_contracts.items():
        for key, value in zip(("from", "to", "inc"), expected, strict=True):
            _close(float(axes[axis][key]), float(value), f"{axis}.{key}")
        _close(float(axes[axis]["label_pt"]), style.tick_label_size_pt, f"{axis}.label.pt")
        if int(axes[axis]["label_font"]) != font_code:
            raise OriginDrawError(f"Origin {axis.upper()} tick-label font readback failed.")

    graph.activate()
    title_state: dict[str, dict[str, Any]] = {}
    for name in ("xb", "yl", "zf"):
        state = {
            "text": op.get_lt_str(f"{name}.text$"),
            "show": int(round(op.lt_float(f"{name}.show"))),
            "font": int(round(op.lt_float(f"{name}.font"))),
            "pt": _finite(op.lt_float(f"{name}.fsize"), f"{name}.fsize"),
        }
        expected_text = {"xb": spec.x_title, "yl": spec.y_title, "zf": spec.z_title}[name]
        if state["text"] != expected_text or state["font"] != font_code:
            raise OriginDrawError(f"Origin title readback failed for {name}.")
        _close(state["pt"], style.axis_title_size_pt, f"{name}.fsize")
        title_state[name] = state

    geometry = {
        "page_width_cm": graph.obj.GetWidth() * 2.54,
        "page_height_cm": graph.obj.GetHeight() * 2.54,
        "layer_unit": int(layer.get_int("unit")),
        "left_percent": _finite(layer.get_float("left"), "layer.left"),
        "top_percent": _finite(layer.get_float("top"), "layer.top"),
        "width_percent": _finite(layer.get_float("width"), "layer.width"),
        "height_percent": _finite(layer.get_float("height"), "layer.height"),
    }
    for actual, expected, name in (
        (geometry["page_width_cm"], style.page_width_cm, "page width"),
        (geometry["page_height_cm"], style.page_height_cm, "page height"),
        (geometry["left_percent"], style.layer_left_percent, "layer left"),
        (geometry["top_percent"], style.layer_top_percent, "layer top"),
        (geometry["width_percent"], style.layer_width_percent, "layer width"),
        (geometry["height_percent"], style.layer_height_percent, "layer height"),
    ):
        _close(float(actual), float(expected), name, 0.06)

    output.result_opju.unlink(missing_ok=True)
    if not op.save(str(output.result_opju)):
        raise OriginDrawError("Origin did not save the editable trajectory3d OPJU.")
    require_nonempty(output.result_opju)
    input_copy_hash = _sha256(output.input_copy)
    if input_copy_hash != preparation.source_sha256:
        raise OriginDrawError("The trajectory3d provenance copy changed during rendering.")

    return graph, {
        "route_status": "verified",
        "template_id": "trajectory3d",
        "plan_digest": preparation.plan_digest,
        "official_references": {
            "plotxyz": OFFICIAL_PLOTXYZ_REFERENCE,
            "trajectory": OFFICIAL_TRAJECTORY_REFERENCE,
        },
        "commands": commands,
        "plot_spec": asdict(spec),
        "source_sha256": preparation.source_sha256,
        "input_copy_sha256_after_render": input_copy_hash,
        "source_columns": list(preparation.source_columns),
        "source_data_modified": False,
        "origin_helper_columns": list(helper_plan.helper_columns),
        "helper_column_purpose": "Series-grouped XYZ triplets inside the editable Origin workbook only",
        "origin_axis_state": {"three_d": three_d, "x": axes["x"], "y": axes["y"], "z": axes["z"]},
        "origin_page_and_layer": geometry,
        "origin_text_state": {
            "titles": title_state,
            "font_family_expected": style.font_family,
            "axis_title_size_pt": style.axis_title_size_pt,
            "tick_label_size_pt": style.tick_label_size_pt,
        },
        "origin_plot_state": plot_state,
        "legend": {"present_before": legend_present_before, "present_after": False},
        "scientific_guardrails": {
            "fit_performed": False,
            "equivalent_circuit_added": False,
            "resistance_annotation_added": False,
            "third_axis_from_user_source": True,
        },
        "origin_acceptance": "templates/trajectory3d/origin_acceptance.md",
        "human_visual_qa": "pending_for_this_run",
    }


def run_trajectory3d_template(
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
        logger.write("trajectory3d Origin graph verified and exported")
    return {
        "opju": str(output.result_opju),
        "png": str(output.result_png),
        "pdf": str(output.result_pdf),
        "tif": str(output.result_tif),
        "verify": verify_report,
    }


__all__ = [
    "GLTRAJECT_TEMPLATE",
    "PLOTXYZ_TYPE",
    "Trajectory3DHelperPlan",
    "Trajectory3DSeriesMapping",
    "build_trajectory3d_helper_plan",
    "run_trajectory3d_template",
]
