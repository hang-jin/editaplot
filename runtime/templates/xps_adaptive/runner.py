"""Adaptive XPS Origin runner for variable-column spectra."""

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
    verify_text_fonts,
    verify_text_sizes,
)
from origin_sciplot.output_manager import RunOutput, write_json
from origin_sciplot.template_registry import TemplateManifest
from origin_sciplot.xps_adaptive import XpsAxisPlan, XpsProfile, XpsSeries, build_axis_plan
from origin_sciplot.xps_workflow import (
    XpsPreparation,
    load_xps_source_snapshot,
    prepare_xps,
    validate_xps_render_frame,
    xps_y_axis_title,
)

RAW_COLOR = "#0F4D92"
RAW_FILL_COLOR = "#7884B4"
BACKGROUND_COLOR = "#606060"
ENVELOPE_COLOR = "#B64342"
RESIDUAL_COLOR = "#5B6770"
COMPONENT_FILL_BASE_SUFFIX = "_FillBase"
COMPONENT_FILL_TOP_SUFFIX = "_FillTop"
ADAPTIVE_LAYER_LEFT_PERCENT = 23.0
ADAPTIVE_LAYER_WIDTH_PERCENT = 76.01
ADAPTIVE_RAW_LINE_WIDTH_PT = 5.0
ADAPTIVE_ENVELOPE_LINE_WIDTH_PT = 5.0
COMPONENT_COLORS = (
    "#3E9E96",
    "#7C6CCF",
    "#C7766A",
    "#C49A2C",
    "#5B8FD6",
    "#8A5CA8",
    "#6F8E5E",
    "#767676",
)
COMPONENT_FILL_COLORS = (
    "#7BCDC4",
    "#A59ADE",
    "#D69A8D",
    "#D5B24A",
    "#8DB7E8",
    "#CAA3D5",
    "#BBD6B2",
    "#B0B0B0",
)
X_LABEL_ALIGN_ON_TICK = 1

_ORIGIN_AXIS_FORMAT_SOURCE = r'''#include <Origin.h>
#pragma labtalk(2)
void CleanAdaptiveXAxisLabels()
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


def _apply_page_layer(op: Any, graph: Any, layer: Any, style: Any) -> dict[str, float]:
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
    return verify_page_and_layer(
        graph,
        layer,
        origin=op,
        style=style,
        expected_layer={
            "left_percent": style.layer_left_percent,
            "width_percent": style.layer_width_percent,
        },
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
    style: Any,
) -> dict[str, float]:
    """Keep locked large titles inside the page without shrinking their fonts.

    The 2024b-verified XPS route lets Origin place its special XB/YL objects,
    then moves XB upward by the contracted page percentage.  Rebuilding both
    positions from layer geometry makes the 26 pt X title collide with 24 pt
    tick labels, so do not replace this with generic centering.
    """
    page_height = float(op.lt_float("page.height"))
    x_title.set_float(
        "top",
        x_title.get_float("top")
        - page_height * style.x_title_upshift_page_percent / 100.0,
    )
    op.lt_exec("doc -uw;")
    state = _axis_title_geometry(op, x_title, y_title)

    # Origin's automatic XB/YL placement is stable for the verified default
    # landscape page, but the same special axis-title objects can extend a few
    # physical units beyond a user-confirmed square/tall page.  Preserve the
    # automatic placement whenever it is already valid; otherwise move only
    # the clipped title into page coordinates and clamp it to a 0.5% inset.
    # This is a geometry repair, not a font-size fallback.
    page_width = state["page.width"]
    page_height = state["page.height"]
    padding_x = page_width * 0.005
    padding_y = page_height * 0.005
    repaired = False
    for name, label in (("x_title", x_title), ("y_title", y_title)):
        left = state[f"{name}.left"]
        top = state[f"{name}.top"]
        width = state[f"{name}.width"]
        height = state[f"{name}.height"]
        if (
            left < 0.0
            or top < 0.0
            or left + width > page_width
            or top + height > page_height
        ):
            label.set_int("attach", 1)
            label.set_float(
                "left",
                min(max(left, padding_x), page_width - width - padding_x),
            )
            label.set_float(
                "top",
                min(max(top, padding_y), page_height - height - padding_y),
            )
            repaired = True
    if repaired:
        op.lt_exec("doc -uw;")
        state = _axis_title_geometry(op, x_title, y_title)
    return state


def _axis_title_geometry(op: Any, x_title: Any, y_title: Any) -> dict[str, float]:
    return {
        "page.width": float(op.lt_float("page.width")),
        "page.height": float(op.lt_float("page.height")),
        "x_title.attach": float(x_title.get_int("attach")),
        "y_title.attach": float(y_title.get_int("attach")),
        **{
            f"{name}.{prop}": float(label.get_float(prop))
            for name, label in (("x_title", x_title), ("y_title", y_title))
            for prop in ("left", "top", "width", "height")
        },
    }


def _require_axis_titles_inside_page(state: dict[str, float]) -> None:
    page_width = state["page.width"]
    page_height = state["page.height"]
    for name in ("x_title", "y_title"):
        if int(state[f"{name}.attach"]) not in {0, 1, 2}:
            raise OriginDrawError(
                f"Origin adaptive {name.replace('_', ' ')} uses an unknown "
                "attachment mode."
            )
        left = state[f"{name}.left"]
        top = state[f"{name}.top"]
        right = left + state[f"{name}.width"]
        bottom = top + state[f"{name}.height"]
        if left < 0 or top < 0 or right > page_width or bottom > page_height:
            raise OriginDrawError(
                f"Origin adaptive {name.replace('_', ' ')} is clipped: "
                f"left={left:g}, top={top:g}, right={right:g}, bottom={bottom:g}"
            )
    if state["x_title.top"] < page_height * 0.90:
        raise OriginDrawError(
            "Origin adaptive X title is too close to the plot frame and may "
            "overlap the 24 pt tick labels."
        )


def _style_axis(layer: Any, axis_name: str, show_ticks: bool, style: Any) -> None:
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
        f"layer.{axis_name}.label.color=color(black);"
        f"layer.{axis_name}.label.pt={style.tick_label_size_pt};"
    )


def _safe_origin_column_name(label: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "_", label).strip("_") or "Series"
    if base[0].isdigit():
        base = f"C_{base}"
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}_{index}"
        index += 1
    used.add(candidate)
    return candidate


def _profile_from_preparation(preparation: XpsPreparation) -> XpsProfile:
    """Adapt the shared classification without inferring roles a second time."""
    roles = preparation.roles
    return XpsProfile(
        x_column=roles.x,
        raw_column=roles.raw,
        background_column=roles.background,
        envelope_column=roles.envelope,
        residuals_column=roles.residual,
        component_columns=roles.components,
        series=tuple(XpsSeries(item.column, item.label, item.role) for item in preparation.plot_spec.series),
    )


def _axis_plan_from_preparation(frame: pd.DataFrame, preparation: XpsPreparation) -> XpsAxisPlan:
    return build_axis_plan(frame, _profile_from_preparation(preparation), preparation)


def _main_plot_series(profile: XpsProfile) -> tuple[XpsSeries, ...]:
    """Series drawn on the counts axis; residuals remain worksheet-only."""
    return tuple(series for series in profile.series if series.role != "residual")


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
    if resolved.plot_spec.visual_profile != "adaptive_counts":
        raise OriginDrawError(
            "XPS preparation visual profile must be 'adaptive_counts' for the adaptive runner."
        )
    if source_digest != resolved.source_sha256:
        raise OriginDrawError("XPS preparation no longer matches the immutable input copy.")
    try:
        validate_xps_render_frame(frame, resolved)
    except ValueError as exc:
        raise OriginDrawError(str(exc)) from exc
    return resolved


def _retain_ignored_source_snapshot(
    op: Any,
    output: RunOutput,
    preparation: XpsPreparation,
) -> dict[str, Any]:
    """Keep source-only columns editable without exposing them to plots."""

    ignored = list(preparation.roles.ignored)
    if not ignored:
        return {
            "created": False,
            "retained_not_rendered_columns": [],
            "plotted": False,
        }
    snapshot = load_xps_source_snapshot(output.input_copy, preparation)
    worksheet = op.new_sheet("w", "XPS Source Snapshot")
    if worksheet is None:
        raise OriginDrawError("Origin could not retain the XPS source snapshot")
    worksheet.from_df(snapshot)
    return {
        "created": True,
        "worksheet": "XPS Source Snapshot",
        "columns": [str(column) for column in snapshot.columns],
        "row_count": len(snapshot.index),
        "retained_not_rendered_columns": ignored,
        "plotted": False,
        "source_values_modified": False,
    }


def _prepare_origin_frame(
    frame: pd.DataFrame,
    profile: XpsProfile | XpsPreparation,
    axis_plan: XpsAxisPlan | None = None,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, str]]:
    preparation = profile if isinstance(profile, XpsPreparation) else None
    if preparation is not None:
        profile = _profile_from_preparation(preparation)
        axis_plan = axis_plan or build_axis_plan(frame, profile, preparation)
    sorted_frame = frame.sort_values(profile.x_column).reset_index(drop=True).copy()
    used = {"BindingEnergy_Source", "PlotX"}
    mapping: dict[str, str] = {}
    fill_base_mapping: dict[str, str] = {}
    transform = (
        preparation.plot_spec.axis.transform
        if preparation is not None
        else getattr(axis_plan, "x_transform", "negate")
    )
    plot_x = -sorted_frame[profile.x_column] if transform == "negate" else sorted_frame[profile.x_column]
    output = pd.DataFrame(
        {
            "BindingEnergy_Source": sorted_frame[profile.x_column],
            "PlotX": plot_x,
        }
    )
    for series in profile.series:
        origin_column = _safe_origin_column_name(series.column, used)
        mapping[series.column] = origin_column
        output[origin_column] = sorted_frame[series.column]

    if (
        preparation is not None
        and preparation.component_basis == "relative_to_background"
        and profile.background_column is not None
    ):
        background = sorted_frame[profile.background_column]
        for component in profile.component_columns:
            top_column = _safe_origin_column_name(f"{component}{COMPONENT_FILL_TOP_SUFFIX}", used)
            output[top_column] = background + sorted_frame[component]
            mapping[component] = top_column

    if profile.background_column:
        baseline_values: pd.Series | float | None = sorted_frame[profile.background_column]
    elif axis_plan is not None:
        baseline_values = axis_plan.y_from
    else:
        baseline_values = None

    if baseline_values is not None:
        for series in profile.series:
            if series.role not in {"raw", "component"}:
                continue
            if (
                preparation is not None
                and series.role == "component"
                and preparation.component_basis == "unresolved"
            ):
                continue
            base_column = _safe_origin_column_name(f"{series.column}{COMPONENT_FILL_BASE_SUFFIX}", used)
            fill_base_mapping[series.column] = base_column
            output[base_column] = baseline_values
    return output, mapping, fill_base_mapping


def _series_color(preparation: XpsPreparation, series: Any, component_index: int) -> str:
    visual = preparation.visual_contract
    overrides = dict(visual.series_color_overrides)
    for key in (series.column, series.role, "components" if series.role == "component" else ""):
        if key and key in overrides:
            return overrides[key]
    role = series.role
    if role == "raw":
        return visual.raw_color
    if role == "background":
        return visual.background_color
    if role == "envelope":
        return visual.envelope_color
    if role == "residual":
        return visual.residual_color
    return visual.component_colors[component_index % len(visual.component_colors)]


def _add_plot(
    layer: Any,
    worksheet: Any,
    y_column: str,
    color: str,
    width_pt: float,
    *,
    plot_type: str = "l",
):
    plot = layer.add_plot(worksheet, y_column, "PlotX", type=plot_type)
    if plot is None:
        raise OriginDrawError(f"Origin could not add plot: {y_column}")
    plot.color = color
    plot.set_cmd(f"-w {pt_to_origin_width_units(width_pt)}")
    return plot


def _add_gradient_fill(
    op: Any,
    layer: Any,
    worksheet: Any,
    y_column: str,
    color: str,
    *,
    fill_base_column: str | None,
    transparency_percent: float,
) -> tuple[Any, Any] | None:
    if not fill_base_column:
        return None
    fill_plot = _add_plot(layer, worksheet, y_column, color, 0.01)
    fill_plot.transparency = transparency_percent
    baseline = _add_plot(layer, worksheet, fill_base_column, "#FFFFFF", 0.1)
    baseline.transparency = 100
    fill_color = op.ocolor(color)
    fill_plot.set_fill_area(above=fill_color, type=9, below=fill_color)
    white = op.ocolor("#FFFFFF")
    fill_plot.set_cmd(f"-pfb {fill_color}")
    fill_plot.set_cmd("-pfm 3")
    fill_plot.set_cmd(f"-pff {white}")
    fill_plot.set_cmd(f"-p2fb {fill_color}")
    fill_plot.set_cmd("-p2fm 3")
    fill_plot.set_cmd(f"-p2ff {white}")
    fill_plot.set_cmd("-paaf 0")
    return fill_plot, baseline


def _apply_clean_x_axis_format(op: Any, graph: Any) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".c", encoding="ascii", delete=False) as handle:
        handle.write(_ORIGIN_AXIS_FORMAT_SOURCE)
        source_path = Path(handle.name)
    try:
        graph.activate()
        op.lt_exec(f'__axis_oc_error=run.LoadOC("{source_path}", 16);')
        if op.lt_int("__axis_oc_error") != 0:
            raise OriginDrawError("Origin C axis formatter did not compile")
        if not op.lt_exec("run -oc CleanAdaptiveXAxisLabels;"):
            raise OriginDrawError("Origin C axis formatter did not execute")
    finally:
        source_path.unlink(missing_ok=True)


def _apply_x_axis_contract(layer: Any, axis_plan: XpsAxisPlan, style: Any) -> None:
    label_divide_by = float(getattr(axis_plan, "x_label_divide_by", -1.0))
    layer.set_int("x.showAxes", 3)
    layer.set_float("x.from", axis_plan.x_from_plot)
    layer.set_float("x.to", axis_plan.x_to_plot)
    layer.set_float("x.inc", axis_plan.x_step_ev)
    layer.set_float("x.firstTick", axis_plan.x_first_tick_plot)
    layer.set_int("x.label.show", 1)
    layer.set_int("x.label.type", 1)
    layer.set_int("x.label.numFormat", 1)
    layer.set_int("x.label.align", X_LABEL_ALIGN_ON_TICK)
    layer.set_float("x.label.divideBy", label_divide_by)
    layer.set_int("x.minorTicks", style.x_minor_ticks_between_majors)
    layer.set_int("x.reverse", 0)
    layer.set_int("x2.ticks", 0)
    layer.set_int("x2.showlabel", 0)
    layer.set_int("x2.label.show", 0)
    layer.set_int("x.label.table", 0)
    layer.set_int("x2.label.table", 0)
    layer.set_int("x.showLabels", 1)
    layer.set_int("x.showlabel", 1)


def _apply_y_axis_contract(layer: Any, axis_plan: XpsAxisPlan) -> None:
    layer.set_int("y.showAxes", 3)
    layer.set_float("y.from", axis_plan.y_from)
    layer.set_float("y.to", axis_plan.y_to)
    layer.set_float("y.inc", axis_plan.y_step)
    layer.set_int("y.ticks", 5)
    layer.set_int("y.minorTicks", 0)
    layer.set_int("y.showLabels", 1)
    layer.set_int("y.showlabel", 1)
    layer.set_int("y.label.show", 1)
    layer.set_int("y.label.type", 1)
    layer.set_int("y.label.numFormat", 2)
    layer.set_int("y.label.decPlaces", 2)
    layer.set_int("y.label.align", X_LABEL_ALIGN_ON_TICK)
    layer.set_int("y2.ticks", 0)
    layer.set_int("y2.showlabel", 0)
    layer.set_int("y2.label.show", 0)


def _read_axis_state(layer: Any) -> dict[str, float | int]:
    int_props = (
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
        "y.ticks",
        "y.minorTicks",
        "y.label.type",
        "y.label.numFormat",
        "y.label.decPlaces",
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
    )
    state: dict[str, float | int] = {}
    for prop in int_props:
        state[prop] = layer.get_int(prop)
    for prop in float_props:
        state[prop] = layer.get_float(prop)
    return state


def _verify_axis_contract(
    layer: Any,
    axis_plan: XpsAxisPlan,
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
        "y.ticks": 5,
        "y.minorTicks": 0,
        "y.label.type": 1,
        "y.label.numFormat": 2,
        "y.label.decPlaces": 2,
        "y.showLabels": 1,
        "y.showlabel": 1,
        "y2.ticks": 0,
        "y2.showlabel": 0,
    }
    for prop, expected in expected_ints.items():
        if state[prop] != expected:
            raise OriginDrawError(f"Origin adaptive axis verification failed: {prop}={state[prop]}")
    expected_floats = {
        "x.firstTick": axis_plan.x_first_tick_plot,
        "x.inc": axis_plan.x_step_ev,
        "x.label.divideBy": float(getattr(axis_plan, "x_label_divide_by", -1.0)),
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
            raise OriginDrawError(f"Origin adaptive axis verification failed: {prop}={state[prop]}")
    if op is not None:
        expected_font = int(
            round(float(op.lt_float(f"font({style.font_family})")))
        )
        state["font_code_expected"] = expected_font
        for prop in ("x.label.font", "y.label.font"):
            if int(round(float(state[prop]))) != expected_font:
                raise OriginDrawError(f"Origin adaptive axis font verification failed: {prop}")
    return state


def _legend_label(label: str) -> str:
    return str(label).replace("\r", " ").replace("\n", " ").strip() or "Series"


def _clean_label_text(label: str) -> str:
    return re.sub(r"\s+", " ", str(label).replace("×", "x")).strip() or "Series"


def _style_legend(
    op: Any,
    layer: Any,
    entries: list[tuple[str, str, str]],
    preparation: XpsPreparation,
) -> dict[str, Any]:
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
            raise OriginDrawError("Origin did not remove the hidden XPS legend.")
        return {
            "visible": False,
            "visible_readback": False,
            "position": "none",
            "showframe": None,
        }
    legend = layer.label("legend")
    if legend is None:
        raise OriginDrawError("Origin did not create the requested XPS legend.")
    lines = []
    for _role, color, label in entries:
        text = _legend_label(label)
        lines.append(
            rf"\L(O Style:L,LineColor:{color},LineWidth:{style.plot_line_width_pt:g},"
            rf"Length:22,Gap:8) {text}"
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
        raise OriginDrawError("Origin XPS legend state failed readback.")
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
            "Origin XPS legend is clipped outside the graph page: "
            f"left={left:g}, top={top:g}, width={width:g}, height={height:g}, "
            f"page_width={page_width:g}, page_height={page_height:g}."
        )
    if visual.legend_position == "outside_right":
        layer_right = page_width * (
            style.layer_left_percent + style.layer_width_percent
        ) / 100.0
        if left < layer_right:
            raise OriginDrawError("Origin XPS legend did not remain outside the plot layer.")
    return {
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


def _remove_legend(layer: Any) -> None:
    for name in ("legend", "Legend"):
        with suppress(Exception):
            legend = layer.label(name)
            if legend is not None:
                legend.remove()


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
                variable_name=f"__xps_{prefix}_color_{index}",
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
                f"Origin XPS fill transparency failed readback: {label}={actual:g}%, "
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
    try:
        profile = _profile_from_preparation(preparation)
        axis_plan = build_axis_plan(frame, profile, preparation)
    except ValueError as exc:
        raise OriginDrawError(str(exc)) from exc

    origin_frame, column_mapping, fill_base_mapping = _prepare_origin_frame(
        frame, preparation, axis_plan
    )
    source_snapshot_state = _retain_ignored_source_snapshot(op, output, preparation)
    worksheet = op.new_sheet("w", "XPS Adaptive Input")
    if worksheet is None:
        raise OriginDrawError("Origin could not create workbook")
    worksheet.from_df(origin_frame)
    worksheet.cols_axis("nx" + "y" * (len(origin_frame.columns) - 2), repeat=False)

    graph = op.new_graph("XPS Adaptive Spectrum", template="Line")
    if graph is None:
        raise OriginDrawError("Origin could not create graph")
    layer = graph[0]
    geometry_report = _apply_page_layer(op, graph, layer, style)

    component_color_by_column = {
        column: _series_color(preparation, series, index)
        for index, series in enumerate(
            item for item in profile.series if item.role == "component"
        )
        for column in (series.column,)
    }
    component_fill_color_by_column = {
        series.column: dict(visual.series_color_overrides).get(
            series.column,
            dict(visual.series_color_overrides).get(
                "component",
                dict(visual.series_color_overrides).get(
                    "components",
                    visual.component_fill_colors[index % len(visual.component_fill_colors)],
                ),
            ),
        )
        for index, series in enumerate(
            item for item in profile.series if item.role == "component"
        )
    }
    main_series = _main_plot_series(profile)
    visible_line_plots: dict[str, Any] = {}
    visible_line_color_plots: dict[str, tuple[Any, str]] = {}
    fill_plots: dict[str, tuple[Any, str]] = {}

    for series in main_series:
        if series.role != "raw":
            continue
        origin_column = column_mapping[series.column]
        fill_color = dict(visual.series_color_overrides).get(
            series.column,
            dict(visual.series_color_overrides).get("raw", visual.raw_fill_color),
        )
        added_fill = _add_gradient_fill(
            op,
            layer,
            worksheet,
            origin_column,
            fill_color,
            fill_base_column=fill_base_mapping.get(series.column),
            transparency_percent=style.fill_transparency_percent,
        )
        if added_fill is not None:
            fill_plots[f"{series.label} fill"] = (added_fill[0], fill_color)

    for series in main_series:
        if series.role != "component":
            continue
        origin_column = column_mapping[series.column]
        fill_color = component_fill_color_by_column[series.column]
        added_fill = _add_gradient_fill(
            op,
            layer,
            worksheet,
            origin_column,
            fill_color,
            fill_base_column=fill_base_mapping.get(series.column),
            transparency_percent=style.fill_transparency_percent,
        )
        if added_fill is not None:
            fill_plots[f"{series.label} fill"] = (added_fill[0], fill_color)

    for series in main_series:
        if series.role != "component":
            continue
        origin_column = column_mapping[series.column]
        plot = _add_plot(
            layer,
            worksheet,
            origin_column,
            component_color_by_column[series.column],
            style.plot_line_width_pt,
        )
        visible_line_plots[series.label] = plot
        visible_line_color_plots[series.label] = (
            plot,
            component_color_by_column[series.column],
        )

    for series in main_series:
        if series.role == "component":
            continue
        color = _series_color(preparation, series, 0)
        origin_column = column_mapping[series.column]
        if series.role == "raw":
            width = style.plot_line_width_pt
        elif series.role == "envelope":
            width = style.plot_line_width_pt
        else:
            width = style.plot_line_width_pt
        plot = _add_plot(
            layer, worksheet, origin_column, color, width
        )
        visible_line_plots[series.label] = plot
        visible_line_color_plots[series.label] = (plot, color)

    legend_entries: list[tuple[str, str, str]] = []
    for series in main_series:
        color = component_color_by_column.get(
            series.column,
            _series_color(preparation, series, 0),
        )
        legend_entries.append((series.role, color, series.label))

    layer.set_float("x.from", axis_plan.x_from_plot)
    layer.set_float("x.to", axis_plan.x_to_plot)
    layer.set_float("x.inc", axis_plan.x_step_ev)
    layer.set_float("y.from", axis_plan.y_from)
    layer.set_float("y.to", axis_plan.y_to)
    layer.set_float("y.inc", axis_plan.y_step)

    layer.axis("x").title = axis_plan.x_title
    y_axis_title = _clean_label_text(xps_y_axis_title(preparation))
    layer.axis("y").title = y_axis_title
    layer.axis("x2").title = ""
    layer.axis("y2").title = ""
    _style_axis(layer, "x", True, style)
    _style_axis(layer, "x2", False, style)
    _style_axis(layer, "y", True, style)
    _style_axis(layer, "y2", False, style)
    layer.set_float("y.label.pt", style.tick_label_size_pt)
    layer.obj.LT_execute(f"layer.y.label.pt={style.tick_label_size_pt};")
    _apply_x_axis_contract(layer, axis_plan, style)
    _apply_y_axis_contract(layer, axis_plan)

    x_title = layer.label("xb")
    y_title = layer.label("yl")
    _style_label(x_title, style.axis_title_size_pt, bold=True)
    _style_label(y_title, style.axis_title_size_pt, bold=True)
    x_title.text = rf"\b({axis_plan.x_title})"
    y_title.text = rf"\b({y_axis_title})"
    layer.obj.LT_execute(
        f"xb.font=font({style.font_family});xb.color=color(black);xb.bold=1;"
        f"xb.fsize={style.axis_title_size_pt};xb.pt={style.axis_title_size_pt};"
        f"yl.font=font({style.font_family});yl.color=color(black);yl.bold=1;"
        f"yl.fsize={style.axis_title_size_pt};yl.pt={style.axis_title_size_pt};"
    )
    legend_state = _style_legend(op, layer, legend_entries, preparation)
    direct_labels: list[dict[str, float | str]] = []

    graph.activate()
    graph.set_int("background", op.ocolor("#FFFFFF"))
    _apply_clean_x_axis_format(op, graph)
    _apply_x_axis_contract(layer, axis_plan, style)
    _apply_y_axis_contract(layer, axis_plan)
    x_title.set_int("show", 1)
    y_title.set_int("show", 1)
    op.lt_exec("doc -uw;")
    _position_axis_titles(op, x_title, y_title, style)
    op.lt_exec("doc -uw;")
    title_position = _axis_title_geometry(op, x_title, y_title)
    _require_axis_titles_inside_page(title_position)
    axis_state = _verify_axis_contract(layer, axis_plan, op=op, style=style)
    legend = (
        layer.label("legend")
        if visual.legend_visible and visual.legend_position != "none"
        else None
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
        text_state = verify_text_sizes(labels, expected_sizes)
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
        line_color_state = _verify_series_color_state(
            op, visible_line_color_plots, prefix="line"
        )
        fill_state = _verify_fill_state(
            op, fill_plots, style.fill_transparency_percent
        )
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc

    output.result_opju.unlink(missing_ok=True)
    if not op.save(str(output.result_opju)):
        raise OriginDrawError("Origin did not save result.opju")
    require_nonempty(output.result_opju)

    geometry_report.update(
        {
            "xps_profile": profile.to_dict(),
            "xps_axis_plan": axis_plan.to_dict(),
            "xps_plan_digest": preparation.plan_digest,
            "xps_plot_spec": preparation.plot_spec.to_dict(),
            "origin_output_style": {
                **style.to_dict(),
                "layer_left_percent": style.layer_left_percent,
                "layer_width_percent": style.layer_width_percent,
            },
            "origin_column_mapping": column_mapping,
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
            },
            "xps_visual_contract": visual.to_dict(),
            "source_data_modified": False,
            "origin_source_snapshot": source_snapshot_state,
            "direct_labels": direct_labels,
            "residuals_column_plotted": False,
            "series_fill_base_columns": fill_base_mapping,
            "component_fill_base_columns": {
                column: fill_base_mapping[column]
                for column in profile.component_columns
                if column in fill_base_mapping
            },
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
