"""XPS C 1s Origin runner.

This module is loaded by the generic worker. It intentionally keeps the XPS
logic inside the template package instead of the GUI.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from origin_sciplot.logging_utils import RunLogger
from origin_sciplot.origin_backend.base_style_contract import (
    FIXED_ORIGIN_STYLE,
    page_size_inches,
    pt_to_origin_width_units,
)
from origin_sciplot.origin_backend.export_utils import export_graph
from origin_sciplot.origin_backend.safe_errors import OriginDrawError
from origin_sciplot.origin_backend.session import OriginSession
from origin_sciplot.origin_backend.verify_utils import (
    require_nonempty,
    verify_page_and_layer,
    verify_plot_line_widths,
    verify_symbol_style,
    verify_text_fonts,
    verify_text_sizes,
)
from origin_sciplot.output_manager import RunOutput, write_json
from origin_sciplot.template_registry import TemplateManifest
from origin_sciplot.xps_workflow import XpsPreparation, prepare_xps


PEAKS = (
    ("Peak_CC", "C-C / C=C", "#4C78A8"),
    ("Peak_CO", "C-O", "#59A14F"),
    ("Peak_CeqO", "C=O", "#E7A1AE"),
    ("Peak_OCeqO", "O-C=O", "#E39C37"),
)
RAW_COLOR = "#808080"
BACKGROUND_COLOR = "#6F6887"
ENVELOPE_COLOR = "#D62728"
X_AXIS_MIN_EV = 280.5
X_FIRST_MAJOR_TICK_EV = 292.0
X_LAST_VISIBLE_MAJOR_LABEL_EV = 282.0
X_VISIBLE_MAJOR_LABELS_EV = (292.0, 290.0, 288.0, 286.0, 284.0, 282.0)
X_LABEL_ALIGN_ON_TICK = 1
RAW_SYMBOL_SIZE_PT = 7.0
RAW_SYMBOL_EDGE_PERCENT = 50.0
FILL_TOP_SUFFIX = "_FillTop"
FILL_BASE_SUFFIX = "_FillBase"

_ORIGIN_AXIS_FORMAT_SOURCE = r'''#include <Origin.h>
#pragma labtalk(2)
void CleanXAxisLabels()
{
    GraphLayer gl = Project.ActiveLayer();
    if (!gl) return;
    Axis axis_x = gl.XAxis;
    Tree format_tree;
    format_tree.Root.Labels.BottomLabels.ShowMinor.nVal = 0;
    format_tree.Root.Labels.BottomLabels.Table.nVal = 0;
    format_tree.Root.Specials.BottomSpecials.SpecialCount.nVal = 0;
    format_tree.Root.Specials.TopSpecials.SpecialCount.nVal = 0;
    if (axis_x.UpdateThemeIDs(format_tree.Root) == 0)
        axis_x.ApplyFormat(format_tree, true, true, true);
    Page page = gl.GetPage();
    page.Refresh();
}
'''


def _resolve_preparation(
    frame: pd.DataFrame,
    output: RunOutput,
    preparation: XpsPreparation | None,
) -> XpsPreparation:
    try:
        resolved = preparation if preparation is not None else prepare_xps(output.input_copy)
        source_digest = hashlib.sha256(Path(output.input_copy).read_bytes()).hexdigest()
    except (OSError, ValueError) as exc:
        raise OriginDrawError(f"XPS preparation failed before Origin startup: {exc}") from exc
    if resolved.plot_spec.visual_profile != "fixed_c1s_publication":
        raise OriginDrawError(
            "XPS preparation visual profile must be 'fixed_c1s_publication' for the fixed C1s runner."
        )
    if source_digest != resolved.source_sha256:
        raise OriginDrawError("XPS preparation no longer matches the immutable input copy.")
    if tuple(str(column) for column in frame.columns) != resolved.source_columns:
        raise OriginDrawError("Validated XPS columns no longer match the preparation plan.")
    if len(frame.index) != resolved.row_count:
        raise OriginDrawError("Validated XPS row count no longer matches the preparation plan.")
    return resolved


def _prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.sort_values("BindingEnergy").reset_index(drop=True).copy()
    prepared.insert(1, "PlotX", -prepared["BindingEnergy"])
    for peak_column, _label, _color in PEAKS:
        if peak_column in prepared.columns and "Background" in prepared.columns:
            prepared[f"{peak_column}{FILL_TOP_SUFFIX}"] = prepared["Background"] + prepared[peak_column]
            prepared[f"{peak_column}{FILL_BASE_SUFFIX}"] = prepared["Background"]
    return prepared


def _apply_page_layer(op: Any, graph: Any, layer: Any) -> dict[str, float]:
    style = FIXED_ORIGIN_STYLE
    width_in, height_in = page_size_inches(style)
    graph.activate()
    graph.obj.LT_execute("page.updatetoprinter=0;page.kar=0;")
    graph.obj.PutWidth(width_in)
    graph.obj.PutHeight(height_in)
    layer.set_int("unit", 1)
    layer.set_float("left", style.layer_left_percent)
    layer.set_float("top", style.layer_top_percent)
    layer.set_float("width", style.layer_width_percent)
    layer.set_float("height", style.layer_height_percent)
    layer.set_int("fixed", style.layer_fixed)
    layer.set_float("factor", style.layer_factor)
    op.set_show(True)
    return verify_page_and_layer(graph, layer)


def _style_axis(layer: Any, axis_name: str, show_ticks: bool) -> None:
    style = FIXED_ORIGIN_STYLE
    show_labels = 1 if show_ticks else 0
    layer.set_int(f"{axis_name}.showGrids", 0)
    layer.set_int(f"{axis_name}.ticks", 5 if show_ticks else 0)
    if axis_name not in {"x2", "y2"}:
        layer.set_int(f"{axis_name}.showLabels", show_labels)
    layer.set_int(f"{axis_name}.showlabel", show_labels)
    layer.set_int(f"{axis_name}.label.show", show_labels)
    if show_ticks:
        layer.set_int(f"{axis_name}.label.type", 1)
        layer.set_int(f"{axis_name}.label.numFormat", 1)
        layer.set_int(f"{axis_name}.label.align", X_LABEL_ALIGN_ON_TICK)
    layer.set_float(f"{axis_name}.thickness", style.frame_line_width_pt)
    layer.set_float(f"{axis_name}.tickthickness", style.frame_line_width_pt)
    layer.set_float(f"{axis_name}.mtickthickness", 1.2)
    layer.set_float(f"{axis_name}.ticklength", style.major_tick_length_pt)
    layer.set_float(f"{axis_name}.mticklength", style.minor_tick_length_pt)
    layer.set_float(f"{axis_name}.label.pt", style.tick_label_size_pt)
    layer.obj.LT_execute(
        f"layer.{axis_name}.label.font=font({style.font_family});"
        "layer.{axis_name}.label.color=color(black);".replace("{axis_name}", axis_name)
        + f"layer.{axis_name}.label.pt={style.tick_label_size_pt};"
    )


def _style_label(label: Any, font_size: float, *, bold: bool) -> None:
    if label is None:
        return
    label.set_int("show", 1)
    label.set_float("fsize", font_size)
    label.set_int("bold", int(bold))
    label.set_int("color", 1)


def _add_plot(layer: Any, worksheet: Any, name: str, color: str, width_pt: float, plot_type: str = "l"):
    plot = layer.add_plot(worksheet, name, "PlotX", type=plot_type)
    if plot is None:
        raise OriginDrawError(f"Origin could not add plot: {name}")
    plot.color = color
    plot.set_cmd(f"-w {pt_to_origin_width_units(width_pt)}")
    return plot


def _apply_clean_x_axis_format(op: Any, graph: Any) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".c", encoding="ascii", delete=False) as handle:
        handle.write(_ORIGIN_AXIS_FORMAT_SOURCE)
        source_path = Path(handle.name)
    try:
        graph.activate()
        op.lt_exec(f'__axis_oc_error=run.LoadOC("{source_path}", 16);')
        if op.lt_int("__axis_oc_error") != 0:
            raise OriginDrawError("Origin C axis formatter did not compile")
        if not op.lt_exec("run -oc CleanXAxisLabels;"):
            raise OriginDrawError("Origin C axis formatter did not execute")
    finally:
        source_path.unlink(missing_ok=True)


def _apply_x_axis_contract(layer: Any, first_tick_plot_value: float) -> None:
    style = FIXED_ORIGIN_STYLE
    layer.set_int("x.showAxes", 3)
    layer.set_int("x.label.show", 1)
    layer.set_int("x.label.type", 1)
    layer.set_int("x.label.numFormat", 1)
    layer.set_int("x.label.align", X_LABEL_ALIGN_ON_TICK)
    layer.set_float("x.label.divideBy", -1.0)
    layer.set_float("x.firstTick", first_tick_plot_value)
    layer.set_float("x.inc", style.x_major_step)
    layer.set_int("x.minorTicks", style.x_minor_ticks_between_majors)
    layer.set_int("x.reverse", 0)
    layer.set_int("x2.ticks", 0)
    layer.set_int("x2.showlabel", 0)
    layer.set_int("x2.label.show", 0)
    layer.set_int("x.label.table", 0)
    layer.set_int("x2.label.table", 0)
    layer.set_int("x.showLabels", 1)
    layer.set_int("x.showlabel", 1)


def _apply_y_axis_contract(layer: Any) -> None:
    layer.set_int("y.showAxes", 3)
    layer.set_int("y.ticks", 0)
    layer.set_int("y.minorTicks", 0)
    layer.set_int("y.showLabels", 0)
    layer.set_int("y.showlabel", 0)
    layer.set_int("y.label.show", 0)
    layer.set_int("y2.ticks", 0)
    layer.set_int("y2.showlabel", 0)
    layer.set_int("y2.label.show", 0)


def _read_axis_state(layer: Any) -> dict[str, float | int]:
    int_props = (
        "x.majorTicksBy",
        "x.ticks",
        "x.minorTicks",
        "x.label.type",
        "x.label.numFormat",
        "x.label.align",
        "x.label.show",
        "x.showLabels",
        "x.showlabel",
        "x.label.table",
        "x.reverse",
        "x2.ticks",
        "x2.label.show",
        "x2.showlabel",
        "y.majorTicksBy",
        "y.ticks",
        "y.minorTicks",
        "y.label.type",
        "y.label.numFormat",
        "y.label.show",
        "y.showLabels",
        "y.showlabel",
        "y2.ticks",
        "y2.label.show",
        "y2.showlabel",
    )
    float_props = (
        "x.from",
        "x.to",
        "x.inc",
        "x.firstTick",
        "x.label.divideBy",
        "x.label.pt",
        "x.label.font",
        "y.label.pt",
        "y.label.font",
        "x.thickness",
        "x2.thickness",
        "y.thickness",
        "y2.thickness",
        "x.tickthickness",
        "y.tickthickness",
        "y.from",
        "y.to",
        "y.inc",
        "y.firstTick",
        "y.label.divideBy",
    )
    state: dict[str, float | int] = {}
    for prop in int_props:
        state[prop] = layer.get_int(prop)
    for prop in float_props:
        state[prop] = layer.get_float(prop)
    return state


def _verify_axis_contract(
    layer: Any,
    first_tick_plot_value: float,
    *,
    op: Any | None = None,
) -> dict[str, float | int]:
    state = _read_axis_state(layer)
    expected_ints = {
        "x.ticks": 5,
        "x.minorTicks": FIXED_ORIGIN_STYLE.x_minor_ticks_between_majors,
        "x.label.type": 1,
        "x.label.numFormat": 1,
        "x.label.align": X_LABEL_ALIGN_ON_TICK,
        "x.showLabels": 1,
        "x.showlabel": 1,
        "x.label.table": 0,
        "x.reverse": 0,
        "y.ticks": 0,
        "y.minorTicks": 0,
        "y.showLabels": 0,
        "y.showlabel": 0,
        "y.label.show": 0,
        "y2.ticks": 0,
        "y2.showlabel": 0,
    }
    for prop, expected in expected_ints.items():
        if state[prop] != expected:
            raise OriginDrawError(f"Origin axis verification failed: {prop}={state[prop]}")
    expected_floats = {
        "x.firstTick": first_tick_plot_value,
        "x.inc": FIXED_ORIGIN_STYLE.x_major_step,
        "x.label.divideBy": -1.0,
        "x.label.pt": FIXED_ORIGIN_STYLE.tick_label_size_pt,
        "y.label.pt": FIXED_ORIGIN_STYLE.tick_label_size_pt,
        "x.thickness": FIXED_ORIGIN_STYLE.frame_line_width_pt,
        "x2.thickness": FIXED_ORIGIN_STYLE.frame_line_width_pt,
        "y.thickness": FIXED_ORIGIN_STYLE.frame_line_width_pt,
        "y2.thickness": FIXED_ORIGIN_STYLE.frame_line_width_pt,
        "x.tickthickness": FIXED_ORIGIN_STYLE.frame_line_width_pt,
        "y.tickthickness": FIXED_ORIGIN_STYLE.frame_line_width_pt,
    }
    for prop, expected in expected_floats.items():
        if abs(float(state[prop]) - expected) > 1e-6:
            raise OriginDrawError(f"Origin axis verification failed: {prop}={state[prop]}")
    if op is not None:
        expected_font = int(
            round(float(op.lt_float(f"font({FIXED_ORIGIN_STYLE.font_family})")))
        )
        state["font_code_expected"] = expected_font
        for prop in ("x.label.font", "y.label.font"):
            if int(round(float(state[prop]))) != expected_font:
                raise OriginDrawError(f"Origin axis font verification failed: {prop}")
    return state


def _build_origin_graph(
    op: Any,
    frame: pd.DataFrame,
    output: RunOutput,
    preparation: XpsPreparation,
) -> tuple[Any, dict[str, Any]]:
    style = FIXED_ORIGIN_STYLE
    worksheet = op.new_sheet("w", "XPS C1s Input")
    if worksheet is None:
        raise OriginDrawError("Origin could not create workbook")
    origin_frame = _prepare_frame(frame)
    worksheet.from_df(origin_frame)
    worksheet.cols_axis("nx" + "y" * (len(origin_frame.columns) - 2), repeat=False)

    graph = op.new_graph("XPS C1s Fit", template="Line")
    if graph is None:
        raise OriginDrawError("Origin could not create graph")
    layer = graph[0]
    geometry_report = _apply_page_layer(op, graph, layer)
    visible_line_plots: dict[str, Any] = {}

    for peak_column, label, color in PEAKS:
        fill_top_column = f"{peak_column}{FILL_TOP_SUFFIX}"
        fill_base_column = f"{peak_column}{FILL_BASE_SUFFIX}"
        peak = _add_plot(layer, worksheet, fill_top_column, color, style.plot_line_width_pt)
        visible_line_plots[label] = peak
        baseline = _add_plot(layer, worksheet, fill_base_column, "#FFFFFF", 0.1)
        baseline.transparency = 100
        peak.set_fill_area(above=op.ocolor(color), type=9, below=op.ocolor(color))
        white = op.ocolor("#FFFFFF")
        peak.set_cmd("-pfm 3")
        peak.set_cmd(f"-pff {white}")
        peak.set_cmd("-p2fm 3")
        peak.set_cmd(f"-p2ff {white}")
        peak.set_cmd("-paaf 0")

    visible_line_plots["Background"] = _add_plot(
        layer, worksheet, "Background", BACKGROUND_COLOR, style.plot_line_width_pt
    )
    raw = _add_plot(layer, worksheet, "Raw", RAW_COLOR, 0.1, plot_type="s")
    raw.symbol_kind = 2
    raw.symbol_interior = 2
    raw.symbol_size = RAW_SYMBOL_SIZE_PT
    raw.set_cmd(f"-kh {RAW_SYMBOL_EDGE_PERCENT:g}")
    raw.set_cmd("-skip 6")
    visible_line_plots["Envelope"] = _add_plot(
        layer, worksheet, "Envelope", ENVELOPE_COLOR, style.plot_line_width_pt
    )

    layer.rescale()
    x_max = float(frame["BindingEnergy"].max())
    x_min = float(frame["BindingEnergy"].min())
    if x_min > X_AXIS_MIN_EV or x_max < X_FIRST_MAJOR_TICK_EV:
        raise OriginDrawError("BindingEnergy range does not cover the required XPS display window")
    layer.axis("x").set_limits(-X_FIRST_MAJOR_TICK_EV, -X_AXIS_MIN_EV, style.x_major_step)
    layer.set_int("x.reverse", 0)
    _, y_top, _ = layer.axis("y").limits
    layer.axis("y").set_limits(0.0, float(y_top) * 1.06)

    layer.axis("x").title = "Binding Energy (eV)"
    layer.axis("y").title = "Intensity (a.u.)"
    layer.axis("x2").title = ""
    layer.axis("y2").title = ""
    _style_axis(layer, "x", True)
    _style_axis(layer, "x2", False)
    _style_axis(layer, "y", False)
    _style_axis(layer, "y2", False)
    layer.set_float("x2.label.divideBy", -1.0)
    _apply_x_axis_contract(layer, -X_FIRST_MAJOR_TICK_EV)
    _apply_y_axis_contract(layer)

    x_title = layer.label("xb")
    y_title = layer.label("yl")
    _style_label(x_title, style.axis_title_size_pt, bold=True)
    _style_label(y_title, style.axis_title_size_pt, bold=True)
    x_title.text = r"\b(Binding Energy (eV))"
    y_title.text = r"\b(Intensity (a.u.))"
    layer.obj.LT_execute(
        f"xb.font=font({style.font_family});xb.color=color(black);xb.bold=1;"
        f"yl.font=font({style.font_family});yl.color=color(black);yl.bold=1;"
    )

    legend = layer.label("legend")
    if legend is not None:
        legend.set_int("link", 1)
        legend.text = "\n".join(
            [
                rf"\L(O Shape:Circle,Interior:Open,Style:sss,EdgeColor:#808080,"
                rf"Size:{RAW_SYMBOL_SIZE_PT:g},EdgeWidth:{RAW_SYMBOL_SIZE_PT * RAW_SYMBOL_EDGE_PERCENT / 200:g},Gap:5) \b(Raw)",
                r"\L(O Style:L,LineColor:#D62728,LineWidth:5,Length:22,Gap:8) \b(Envelope)",
                r"\L(O Style:L,LineColor:#6F6887,LineWidth:5,Length:22,Gap:8) \b(Background)",
                r"\L(O Style:L,LineColor:#4C78A8,LineWidth:5,Length:22,Gap:8) \b(C-C / C=C)",
                r"\L(O Style:L,LineColor:#59A14F,LineWidth:5,Length:22,Gap:8) \b(C-O)",
                r"\L(O Style:L,LineColor:#E7A1AE,LineWidth:5,Length:22,Gap:8) \b(C=O)",
                r"\L(O Style:L,LineColor:#E39C37,LineWidth:5,Length:22,Gap:8) \b(O-C=O)",
            ]
        )
        _style_label(legend, style.legend_size_pt, bold=True)
        layer.obj.LT_execute(
            f"legend.font=font({style.font_family});legend.color=color(black);legend.bold=1;"
        )

    graph.activate()
    graph.set_int("background", op.ocolor("#FFFFFF"))
    _apply_clean_x_axis_format(op, graph)
    _apply_x_axis_contract(layer, -X_FIRST_MAJOR_TICK_EV)
    _apply_y_axis_contract(layer)
    x_title.set_int("show", 1)
    y_title.set_int("show", 1)
    op.lt_exec("doc -uw;")
    page_height = op.lt_float("page.height")
    x_title.set_float("top", x_title.get_float("top") - page_height * style.x_title_upshift_page_percent / 100.0)
    op.lt_exec("doc -uw;")
    axis_state = _verify_axis_contract(layer, -X_FIRST_MAJOR_TICK_EV, op=op)
    try:
        text_state = verify_text_sizes(
            {"x_title": x_title, "y_title": y_title, "legend": legend},
            {
                "x_title": style.axis_title_size_pt,
                "y_title": style.axis_title_size_pt,
                "legend": style.legend_size_pt,
            },
        )
        text_state.update(
            verify_text_fonts(
                op,
                {"x_title": x_title, "y_title": y_title, "legend": legend},
                style.font_family,
            )
        )
        line_width_state = verify_plot_line_widths(
            op, visible_line_plots, style.plot_line_width_pt
        )
        raw_symbol_state = verify_symbol_style(
            op,
            raw,
            expected_size_pt=RAW_SYMBOL_SIZE_PT,
            expected_edge_percent=RAW_SYMBOL_EDGE_PERCENT,
        )
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc

    output.result_opju.unlink(missing_ok=True)
    if not op.save(str(output.result_opju)):
        raise OriginDrawError("Origin did not save result.opju")
    require_nonempty(output.result_opju)

    x_limits = layer.axis("x").limits
    if layer.get_int("x.reverse") != 0 or layer.get_float("x.label.divideBy") != -1.0:
        raise OriginDrawError("Origin numeric reversed X-axis workaround was not applied")
    geometry_report.update(
        {
            "x_display_left_ev": X_FIRST_MAJOR_TICK_EV,
            "x_display_right_ev": X_AXIS_MIN_EV,
            "x_first_major_tick_ev": X_FIRST_MAJOR_TICK_EV,
            "x_last_visible_major_label_ev": X_LAST_VISIBLE_MAJOR_LABEL_EV,
            "x_visible_major_labels_ev": list(X_VISIBLE_MAJOR_LABELS_EV),
            "x_actual_step": abs(float(x_limits[2])),
            "origin_axis_state": axis_state,
            "origin_text_state": {
                **text_state,
                "font_family_expected": style.font_family,
                "plot_line_width_pt": style.plot_line_width_pt,
                "plot_set_w_units": pt_to_origin_width_units(style.plot_line_width_pt),
                "frame_line_width_pt": style.frame_line_width_pt,
            },
            "origin_plot_state": {
                "visible_line_plots": line_width_state,
                "raw_symbol": raw_symbol_state,
            },
            "source_data_modified": False,
            "xps_plan_digest": preparation.plan_digest,
            "xps_plot_spec": preparation.plot_spec.to_dict(),
        }
    )
    return graph, geometry_report


def run(
    manifest: TemplateManifest,
    frame: pd.DataFrame,
    output: RunOutput,
    logger: RunLogger,
    keep_origin_open: bool = True,
    preparation: XpsPreparation | None = None,
) -> dict[str, Any]:
    """Create the editable Origin project and exported images."""
    preparation = _resolve_preparation(frame, output, preparation)
    with OriginSession(keep_open=keep_origin_open) as session:
        op = session.op
        if op is None or session.environment is None:
            raise OriginDrawError("Origin session was not initialized")
        logger.write(f"Origin connected: version {session.environment.origin_version}")
        graph, verify_report = _build_origin_graph(op, frame, output, preparation)
        exports = export_graph(
            op,
            graph,
            output.result_png,
            output.result_pdf,
            output.result_tif,
        )
        verify_report["exports"] = exports
        write_json(
            output.environment_report,
            {
                "template_id": manifest.id,
                "template_version": manifest.version,
                "python_version": __import__("sys").version.split()[0],
                "originpro_version": session.environment.originpro_version,
                "origin_version": session.environment.origin_version,
            },
        )
        write_json(output.origin_verify_report, verify_report)
        return {
            "opju": str(output.result_opju),
            "png": str(output.result_png),
            "pdf": str(output.result_pdf),
            "tif": str(output.result_tif),
            "origin_version": session.environment.origin_version,
            "verify": verify_report,
        }
