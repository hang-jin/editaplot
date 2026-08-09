"""XPS C 1s Origin runner.

This module is loaded by the generic worker. It intentionally keeps the XPS
logic inside the template package instead of the GUI.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
from contextlib import suppress
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
    verify_plot_color,
    verify_plot_line_widths,
    verify_symbol_style,
    verify_text_fonts,
    verify_text_sizes,
)
from origin_sciplot.output_manager import RunOutput, write_json
from origin_sciplot.template_registry import TemplateManifest
from origin_sciplot.xps_workflow import (
    XpsPreparation,
    prepare_xps,
    validate_xps_render_frame,
)

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
    try:
        validate_xps_render_frame(frame, resolved)
    except ValueError as exc:
        raise OriginDrawError(str(exc)) from exc
    return resolved


def _prepare_frame(
    frame: pd.DataFrame,
    preparation: XpsPreparation | None = None,
) -> pd.DataFrame:
    prepared = frame.sort_values("BindingEnergy").reset_index(drop=True).copy()
    prepared.insert(1, "PlotX", -prepared["BindingEnergy"])
    component_columns = (
        preparation.roles.components
        if preparation is not None
        else tuple(item[0] for item in PEAKS)
    )
    for peak_column in component_columns:
        if peak_column in prepared.columns and "Background" in prepared.columns:
            prepared[f"{peak_column}{FILL_TOP_SUFFIX}"] = prepared["Background"] + prepared[peak_column]
            prepared[f"{peak_column}{FILL_BASE_SUFFIX}"] = prepared["Background"]
    return prepared


def _apply_page_layer(
    op: Any,
    graph: Any,
    layer: Any,
    style: Any = FIXED_ORIGIN_STYLE,
) -> dict[str, float]:
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
    return verify_page_and_layer(graph, layer, origin=op, style=style)


def _style_axis(
    layer: Any,
    axis_name: str,
    show_ticks: bool,
    style: Any = FIXED_ORIGIN_STYLE,
) -> None:
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
    layer.set_float(f"{axis_name}.label.rotate", 0.0)
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


def _position_axis_titles(
    op: Any,
    x_title: Any,
    y_title: Any,
    style: Any = FIXED_ORIGIN_STYLE,
) -> dict[str, float]:
    """Place fixed-XPS titles using the verified Origin auto-layout route.

    Origin first lays out the 24 pt tick labels and the 26 pt XB/YL titles.
    The contracted 3% upward correction then prevents XB clipping while
    retaining the separation Origin calculated between ticks and title.
    """

    page_height = float(op.lt_float("page.height"))
    x_title.set_float(
        "top",
        x_title.get_float("top")
        - page_height * style.x_title_upshift_page_percent / 100.0,
    )
    op.lt_exec("doc -uw;")
    state: dict[str, float] = {
        "page.width": float(op.lt_float("page.width")),
        "page.height": page_height,
    }
    for name, label in (("x_title", x_title), ("y_title", y_title)):
        state[f"{name}.attach"] = float(label.get_int("attach"))
        for prop in ("left", "top", "width", "height"):
            state[f"{name}.{prop}"] = float(label.get_float(prop))
        if int(state[f"{name}.attach"]) not in {0, 1, 2}:
            raise OriginDrawError(
                f"Origin fixed XPS {name.replace('_', ' ')} uses an unknown "
                "attachment mode."
            )
        right = state[f"{name}.left"] + state[f"{name}.width"]
        bottom = state[f"{name}.top"] + state[f"{name}.height"]
        if (
            state[f"{name}.left"] < 0
            or state[f"{name}.top"] < 0
            or right > state["page.width"]
            or bottom > page_height
        ):
            raise OriginDrawError(
                f"Origin fixed XPS {name.replace('_', ' ')} is clipped."
            )
    if state["x_title.top"] < page_height * 0.90:
        raise OriginDrawError(
            "Origin fixed XPS X title is too close to the plot frame and may "
            f"overlap the {style.tick_label_size_pt:g} pt tick labels."
        )
    return state


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


def _apply_x_axis_contract(
    layer: Any,
    first_tick_plot_value: float,
    style: Any = FIXED_ORIGIN_STYLE,
) -> None:
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
        "x.label.rotate",
        "y.label.pt",
        "y.label.font",
        "y.label.rotate",
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
    style: Any = FIXED_ORIGIN_STYLE,
) -> dict[str, float | int]:
    state = _read_axis_state(layer)
    expected_ints = {
        "x.ticks": 5,
        "x.minorTicks": style.x_minor_ticks_between_majors,
        "x.label.type": 1,
        "x.label.numFormat": 1,
        "x.label.align": X_LABEL_ALIGN_ON_TICK,
        "x.showLabels": 1,
        "x.showlabel": 1,
        "x.label.table": 0,
        "x.reverse": 0,
        "x2.ticks": 0,
        "x2.label.show": 0,
        "x2.showlabel": 0,
        "y.ticks": 0,
        "y.minorTicks": 0,
        "y.showLabels": 0,
        "y.showlabel": 0,
        "y.label.show": 0,
        "y2.ticks": 0,
        "y2.label.show": 0,
        "y2.showlabel": 0,
    }
    for prop, expected in expected_ints.items():
        if state[prop] != expected:
            raise OriginDrawError(f"Origin axis verification failed: {prop}={state[prop]}")
    expected_floats = {
        "x.firstTick": first_tick_plot_value,
        "x.inc": style.x_major_step,
        "x.label.divideBy": -1.0,
        "x.label.pt": style.tick_label_size_pt,
        "x.label.rotate": 0.0,
        "y.label.pt": style.tick_label_size_pt,
        "y.label.rotate": 0.0,
        "x.thickness": style.frame_line_width_pt,
        "x2.thickness": style.frame_line_width_pt,
        "y.thickness": style.frame_line_width_pt,
        "y2.thickness": style.frame_line_width_pt,
        "x.tickthickness": style.frame_line_width_pt,
        "y.tickthickness": style.frame_line_width_pt,
    }
    for prop, expected in expected_floats.items():
        if abs(float(state[prop]) - expected) > 1e-6:
            raise OriginDrawError(f"Origin axis verification failed: {prop}={state[prop]}")
    if op is not None:
        expected_font = int(
            round(float(op.lt_float(f"font({style.font_family})")))
        )
        state["font_code_expected"] = expected_font
        for prop in ("x.label.font", "y.label.font"):
            if int(round(float(state[prop]))) != expected_font:
                raise OriginDrawError(f"Origin axis font verification failed: {prop}")
    return state


def _series_color(
    preparation: XpsPreparation,
    column: str,
    role: str,
    component_index: int = 0,
) -> str:
    """Resolve an exact user colour before the registered role default."""

    visual = preparation.visual_contract
    overrides = dict(visual.series_color_overrides)
    for key in (column, role, "components" if role == "component" else ""):
        if key and key in overrides:
            return overrides[key]
    if role == "raw":
        return visual.raw_color
    if role == "background":
        return visual.background_color
    if role == "envelope":
        return visual.envelope_color
    if role == "residual":
        return visual.residual_color
    return visual.component_colors[component_index % len(visual.component_colors)]


def _component_fill_color(
    preparation: XpsPreparation,
    column: str,
    component_index: int,
) -> str:
    visual = preparation.visual_contract
    overrides = dict(visual.series_color_overrides)
    for key in (column, "component", "components"):
        if key in overrides:
            return overrides[key]
    return visual.component_fill_colors[
        component_index % len(visual.component_fill_colors)
    ]


def _legend_label(label: str) -> str:
    return re.sub(r"\s+", " ", str(label).replace("×", "x")).strip() or "Series"


def _remove_legend(layer: Any) -> None:
    for name in ("legend", "Legend"):
        with suppress(Exception):
            legend = layer.label(name)
            if legend is not None:
                legend.remove()


def _style_legend(
    op: Any,
    layer: Any,
    entries: list[tuple[str, str, str]],
    preparation: XpsPreparation,
) -> tuple[Any | None, dict[str, Any]]:
    """Apply and read back only the verified editable legend properties."""

    visual = preparation.visual_contract
    style = visual.figure_style
    if not visual.legend_visible or visual.legend_position == "none":
        _remove_legend(layer)
        remaining_visible = False
        for name in ("legend", "Legend"):
            with suppress(Exception):
                candidate = layer.label(name)
                if candidate is not None and int(candidate.get_int("show")) != 0:
                    remaining_visible = True
        if remaining_visible:
            raise OriginDrawError("Origin did not remove the hidden fixed XPS legend.")
        return None, {
            "visible": False,
            "visible_readback": False,
            "position": "none",
            "showframe": None,
        }

    legend = layer.label("legend")
    if legend is None:
        raise OriginDrawError("Origin did not create the requested fixed XPS legend.")
    lines: list[str] = []
    raw_edge_width = RAW_SYMBOL_SIZE_PT * RAW_SYMBOL_EDGE_PERCENT / 200
    for role, color, label in entries:
        text = _legend_label(label)
        if role == "raw":
            lines.append(
                rf"\L(O Shape:Circle,Interior:Open,Style:sss,EdgeColor:{color},"
                rf"Size:{RAW_SYMBOL_SIZE_PT:g},EdgeWidth:{raw_edge_width:g},Gap:5) "
                rf"\b({text})"
            )
        else:
            lines.append(
                rf"\L(O Style:L,LineColor:{color},LineWidth:{style.plot_line_width_pt:g},"
                rf"Length:22,Gap:8) \b({text})"
            )
    legend.set_int("link", 1)
    legend.text = "\n".join(lines)
    _style_label(legend, style.legend_size_pt, bold=True)
    legend.set_int("showframe", int(visual.legend_frame))
    layer.obj.LT_execute(
        f"legend.font=font({style.font_family});legend.color=color(black);legend.bold=1;"
    )
    if visual.legend_position == "outside_right":
        op.lt_exec("doc -uw;")
        page_width = float(op.lt_float("page.width"))
        page_height = float(op.lt_float("page.height"))
        layer_right = page_width * (
            style.layer_left_percent + style.layer_width_percent
        ) / 100.0
        legend.set_int("attach", 1)
        legend.set_float("left", layer_right + page_width * 0.02)
        legend.set_float("top", page_height * 0.08)
        op.lt_exec("doc -uw;")

    visible_readback = int(legend.get_int("show")) != 0
    showframe = int(legend.get_int("showframe"))
    if not visible_readback or showframe != int(visual.legend_frame):
        raise OriginDrawError("Origin fixed XPS legend state failed readback.")
    left = float(legend.get_float("left"))
    top = float(legend.get_float("top"))
    width = float(legend.get_float("width"))
    height = float(legend.get_float("height"))
    page_width = float(op.lt_float("page.width"))
    page_height = float(op.lt_float("page.height"))
    inside_page = (
        left >= 0.0
        and top >= 0.0
        and left + width <= page_width
        and top + height <= page_height
    )
    if not inside_page:
        raise OriginDrawError(
            "Origin fixed XPS legend is clipped outside the graph page: "
            f"left={left:g}, top={top:g}, width={width:g}, height={height:g}, "
            f"page_width={page_width:g}, page_height={page_height:g}."
        )
    if visual.legend_position == "outside_right":
        layer_right = page_width * (
            style.layer_left_percent + style.layer_width_percent
        ) / 100.0
        if left < layer_right:
            raise OriginDrawError("Origin fixed XPS legend did not remain outside the plot layer.")
    return legend, {
        "visible": True,
        "visible_readback": visible_readback,
        "position": visual.legend_position,
        "showframe": showframe,
        "left": left,
        "top": top,
        "width": width,
        "height": height,
        "inside_page": inside_page,
        "attach": int(legend.get_int("attach")),
    }


def _verify_series_color_state(
    op: Any,
    plots: dict[str, tuple[Any, str]],
    *,
    prefix: str,
) -> dict[str, dict[str, float | str]]:
    state: dict[str, dict[str, float | str]] = {}
    for index, (label, (plot, color)) in enumerate(plots.items(), start=1):
        try:
            state[label] = verify_plot_color(
                op,
                plot,
                color,
                variable_name=f"__xps_fixed_{prefix}_color_{index}",
            )
        except RuntimeError as exc:
            raise OriginDrawError(str(exc)) from exc
    return state


def _verify_fill_state(
    op: Any,
    fills: dict[str, tuple[Any, str]],
    expected_transparency: float,
) -> dict[str, dict[str, Any]]:
    color_state = _verify_series_color_state(op, fills, prefix="fill")
    state: dict[str, dict[str, Any]] = {}
    for label, (plot, _color) in fills.items():
        actual = float(plot.transparency)
        if abs(actual - expected_transparency) > 0.05:
            raise OriginDrawError(
                f"Origin fixed XPS fill transparency failed readback: {label}={actual:g}%, "
                f"expected {expected_transparency:g}%."
            )
        state[label] = {
            **color_state[label],
            "transparency_percent": actual,
            "fill_mode": "type9_pfm3_two_colors",
        }
    return state


def _build_origin_graph(
    op: Any,
    frame: pd.DataFrame,
    output: RunOutput,
    preparation: XpsPreparation,
) -> tuple[Any, dict[str, Any]]:
    visual = preparation.visual_contract
    style = visual.figure_style
    worksheet = op.new_sheet("w", "XPS C1s Input")
    if worksheet is None:
        raise OriginDrawError("Origin could not create workbook")
    origin_frame = _prepare_frame(frame, preparation)
    worksheet.from_df(origin_frame)
    worksheet.cols_axis("nx" + "y" * (len(origin_frame.columns) - 2), repeat=False)

    graph = op.new_graph("XPS C1s Fit", template="Line")
    if graph is None:
        raise OriginDrawError("Origin could not create graph")
    layer = graph[0]
    geometry_report = _apply_page_layer(op, graph, layer, style)
    visible_line_plots: dict[str, Any] = {}
    visible_color_plots: dict[str, tuple[Any, str]] = {}
    fill_plots: dict[str, tuple[Any, str]] = {}
    series_by_column = {
        series.column: series for series in preparation.plot_spec.series
    }
    component_specs = [
        series
        for series in preparation.plot_spec.series
        if series.role == "component"
    ]

    # Fills are independent DataPlots so their transparency can be edited
    # without fading the component outlines.  The verified Origin route stays
    # one fill region + type=9 + Two Colors (-pfm 3); the unverified
    # four-colour mode is deliberately excluded.
    for index, series in enumerate(component_specs):
        peak_column = series.column
        label = series.label
        fill_top_column = f"{peak_column}{FILL_TOP_SUFFIX}"
        fill_base_column = f"{peak_column}{FILL_BASE_SUFFIX}"
        fill_color = _component_fill_color(preparation, peak_column, index)
        fill_plot = _add_plot(layer, worksheet, fill_top_column, fill_color, 0.01)
        fill_plot.transparency = style.fill_transparency_percent
        baseline = _add_plot(layer, worksheet, fill_base_column, "#FFFFFF", 0.1)
        baseline.transparency = 100
        origin_fill_color = op.ocolor(fill_color)
        fill_plot.set_fill_area(
            above=origin_fill_color,
            type=9,
            below=origin_fill_color,
        )
        white = op.ocolor("#FFFFFF")
        fill_plot.set_cmd(f"-pfb {origin_fill_color}")
        fill_plot.set_cmd("-pfm 3")
        fill_plot.set_cmd(f"-pff {white}")
        fill_plot.set_cmd(f"-p2fb {origin_fill_color}")
        fill_plot.set_cmd("-p2fm 3")
        fill_plot.set_cmd(f"-p2ff {white}")
        fill_plot.set_cmd("-paaf 0")
        fill_plots[f"{label} fill"] = (fill_plot, fill_color)

    for index, series in enumerate(component_specs):
        color = _series_color(
            preparation,
            series.column,
            series.role,
            index,
        )
        plot = _add_plot(
            layer,
            worksheet,
            f"{series.column}{FILL_TOP_SUFFIX}",
            color,
            style.plot_line_width_pt,
        )
        visible_line_plots[series.label] = plot
        visible_color_plots[series.label] = (plot, color)

    background_spec = series_by_column.get(preparation.roles.background or "")
    background_color = _series_color(
        preparation,
        preparation.roles.background or "Background",
        "background",
    )
    background_label = background_spec.label if background_spec is not None else "Background"
    visible_line_plots["Background"] = _add_plot(
        layer,
        worksheet,
        "Background",
        background_color,
        style.plot_line_width_pt,
    )
    if background_label != "Background":
        visible_line_plots[background_label] = visible_line_plots.pop("Background")
    visible_color_plots[background_label] = (
        visible_line_plots[background_label],
        background_color,
    )

    raw_spec = series_by_column.get(preparation.roles.raw)
    raw_color = _series_color(preparation, preparation.roles.raw, "raw")
    raw_label = raw_spec.label if raw_spec is not None else "Raw"
    raw = _add_plot(
        layer,
        worksheet,
        "Raw",
        raw_color,
        style.plot_line_width_pt,
        plot_type="s",
    )
    raw.symbol_kind = 2
    raw.symbol_interior = 2
    raw.symbol_size = RAW_SYMBOL_SIZE_PT
    raw.set_cmd(f"-kh {RAW_SYMBOL_EDGE_PERCENT:g}")
    raw.set_cmd("-skip 6")
    visible_color_plots[raw_label] = (raw, raw_color)

    envelope_spec = series_by_column.get(preparation.roles.envelope or "")
    envelope_color = _series_color(
        preparation,
        preparation.roles.envelope or "Envelope",
        "envelope",
    )
    envelope_label = envelope_spec.label if envelope_spec is not None else "Envelope"
    visible_line_plots[envelope_label] = _add_plot(
        layer,
        worksheet,
        "Envelope",
        envelope_color,
        style.plot_line_width_pt,
    )
    visible_color_plots[envelope_label] = (
        visible_line_plots[envelope_label],
        envelope_color,
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
    _style_axis(layer, "x", True, style)
    _style_axis(layer, "x2", False, style)
    _style_axis(layer, "y", False, style)
    _style_axis(layer, "y2", False, style)
    layer.set_float("x2.label.divideBy", -1.0)
    _apply_x_axis_contract(layer, -X_FIRST_MAJOR_TICK_EV, style)
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

    component_legend_entries = [
        (
            "component",
            _series_color(preparation, series.column, series.role, index),
            series.label,
        )
        for index, series in enumerate(component_specs)
    ]
    legend, legend_state = _style_legend(
        op,
        layer,
        [
            ("raw", raw_color, raw_label),
            ("envelope", envelope_color, envelope_label),
            ("background", background_color, background_label),
            *component_legend_entries,
        ],
        preparation,
    )

    graph.activate()
    graph.set_int("background", op.ocolor("#FFFFFF"))
    _apply_clean_x_axis_format(op, graph)
    _apply_x_axis_contract(layer, -X_FIRST_MAJOR_TICK_EV, style)
    _apply_y_axis_contract(layer)
    x_title.set_int("show", 1)
    y_title.set_int("show", 1)
    op.lt_exec("doc -uw;")
    title_position = _position_axis_titles(op, x_title, y_title, style)
    axis_state = _verify_axis_contract(
        layer,
        -X_FIRST_MAJOR_TICK_EV,
        op=op,
        style=style,
    )
    labels = {"x_title": x_title, "y_title": y_title}
    expected_sizes = {
        "x_title": style.axis_title_size_pt,
        "y_title": style.axis_title_size_pt,
    }
    if legend is not None:
        labels["legend"] = legend
        expected_sizes["legend"] = style.legend_size_pt
    try:
        text_state = verify_text_sizes(
            labels,
            expected_sizes,
        )
        text_state.update(
            verify_text_fonts(
                op,
                labels,
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
        line_color_state = _verify_series_color_state(
            op,
            visible_color_plots,
            prefix="line",
        )
        fill_state = _verify_fill_state(
            op,
            fill_plots,
            style.fill_transparency_percent,
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
            "origin_output_style": style.to_dict(),
            "origin_axis_state": axis_state,
            "origin_text_state": {
                **text_state,
                "font_family_expected": style.font_family,
                "plot_line_width_pt": style.plot_line_width_pt,
                "plot_set_w_units": pt_to_origin_width_units(style.plot_line_width_pt),
                "frame_line_width_pt": style.frame_line_width_pt,
                **title_position,
            },
            "origin_plot_state": {
                "visible_line_plots": line_width_state,
                "visible_series_colors": line_color_state,
                "fill_plots": fill_state,
                "fill_transparency_percent_expected": style.fill_transparency_percent,
                "fill_mode": "type9_pfm3_two_colors",
                "legend": legend_state,
                "raw_symbol": raw_symbol_state,
            },
            "xps_visual_contract": visual.to_dict(),
            "origin_helper_columns": [
                column
                for column in origin_frame.columns
                if column == "PlotX"
                or column.endswith(FILL_TOP_SUFFIX)
                or column.endswith(FILL_BASE_SUFFIX)
            ],
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
                **session.environment.to_dict(),
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
