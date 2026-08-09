"""Editable Origin renderer for circular directed weighted networks.

The renderer deliberately keeps every visible relationship editable:

* sampled cubic Bézier paths are normal Origin XY line plots;
* terminal arrowheads are scale-attached Origin line objects;
* nodes are grouped Origin scatter plots;
* panel, node, edge, and legend text are editable Origin labels.

The user's table is copied unchanged to a source worksheet.  Geometry columns
are generated only in a separate helper worksheet inside the OPJU project.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from origin_sciplot.circular_network_layout import (
    MAX_NODE_GROUP_COUNT,
    NETWORK_EDGE_TRANSPARENCY_PERCENT,
    NETWORK_NODE_GROUP_COLORS,
    CircularNetworkEdgeGeometry,
    CircularNetworkLayoutPlan,
)
from origin_sciplot.logging_utils import RunLogger
from origin_sciplot.output_manager import RunOutput, write_json
from origin_sciplot.scientific_visual import palette_colors
from origin_sciplot.scientific_workflow import ScientificPreparation, prepare_scientific
from origin_sciplot.template_registry import TemplateManifest

from .base_style_contract import page_size_inches, pt_to_origin_width_units
from .export_utils import export_graph
from .safe_errors import OriginDrawError
from .scientific_renderer import _figure_style, _origin_font_code, _style_label
from .session import OriginSession
from .verify_utils import (
    PAGE_SIZE_TOLERANCE_CM,
    read_layer_geometry_percent,
    require_nonempty,
    verify_plot_color,
    verify_plot_line_widths,
    verify_symbol_style,
    verify_text_fonts,
    verify_text_sizes,
)

SIGN_COLORS: dict[str, str] = {
    "positive": "#2F6B6F",
    "negative": "#B65C67",
    "neutral": "#7B8794",
}

NODE_GROUP_COLORS = NETWORK_NODE_GROUP_COLORS

NETWORK_NODE_MARKER_SIZE_PT = 15.0
NETWORK_NODE_EDGE_PERCENT = 28.0


@dataclass(frozen=True)
class NetworkEdgeColumnPlan:
    """Helper-column binding for one editable edge path."""

    panel: str
    order_index: int
    x_column: str
    y_column: str
    edge: CircularNetworkEdgeGeometry


@dataclass(frozen=True)
class NetworkNodeColumnPlan:
    """Helper-column binding for one node group."""

    group: str
    order_index: int
    x_column: str
    y_column: str
    nodes: tuple[str, ...]


@dataclass(frozen=True)
class OriginNetworkTablePlan:
    """Origin-only helper table and its semantic bindings."""

    helper_frame: pd.DataFrame
    edge_columns: tuple[NetworkEdgeColumnPlan, ...]
    node_columns: tuple[NetworkNodeColumnPlan, ...]
    node_groups: tuple[tuple[str, str], ...]
    source_frame_unchanged: bool = True


@dataclass(frozen=True)
class NetworkLayerGeometry:
    """One graph-layer rectangle in percent-of-page units."""

    left: float
    top: float
    width: float
    height: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def _safe_fragment(value: str, *, fallback: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return text[:28] or fallback


def _resolve_preparation(
    manifest: TemplateManifest,
    frame: pd.DataFrame,
    output: RunOutput,
    preparation: ScientificPreparation | None,
) -> ScientificPreparation:
    resolved = preparation or prepare_scientific(output.input_copy, manifest.id)
    if resolved.template_id != manifest.id:
        raise OriginDrawError(
            f"Network preparation {resolved.template_id!r} does not match {manifest.id!r}."
        )
    if tuple(map(str, frame.columns)) != resolved.source_columns:
        raise OriginDrawError("Network preparation columns do not match the validated source copy.")
    if resolved.requires_confirmation:
        raise OriginDrawError("Column mapping confirmation is required before Origin can run.")
    if resolved.plot_spec.plot_kind != "circular_network":
        raise OriginDrawError(
            f"Unsupported network plot kind: {resolved.plot_spec.plot_kind!r}."
        )
    if resolved.plot_spec.network_layout is None:
        raise OriginDrawError("Circular-network geometry is missing from the frozen render plan.")
    return resolved


def _node_group_map(preparation: ScientificPreparation) -> dict[str, str]:
    layout = preparation.plot_spec.network_layout
    if layout is None:
        raise OriginDrawError("Circular-network geometry is missing.")
    groups = dict(preparation.plot_spec.node_groups)
    if not groups:
        return {node: "Nodes" for node in layout.node_order}
    missing = [node for node in layout.node_order if node not in groups]
    extra = [node for node in groups if node not in layout.node_order]
    if missing or extra:
        raise OriginDrawError(
            "Circular-network node-group mapping does not match the frozen node order."
        )
    return groups


def _node_group_colors(
    preparation: ScientificPreparation,
    groups: tuple[str, ...],
) -> dict[str, str]:
    if len(groups) > MAX_NODE_GROUP_COUNT:
        raise OriginDrawError(
            f"Circular networks support at most {MAX_NODE_GROUP_COUNT} node groups."
        )
    style = _figure_style(preparation)
    colors = palette_colors(style.palette_name)
    if len(colors) < len(groups):
        raise OriginDrawError(
            "The selected circular-network palette does not provide one colour per node group."
        )
    return {
        group: colors[index]
        for index, group in enumerate(groups)
    }


def _network_layout_summary(
    layout: CircularNetworkLayoutPlan,
) -> dict[str, Any]:
    return {
        "panel_order": list(layout.panel_order),
        "node_order": list(layout.node_order),
        "edge_counts": {
            panel.panel: len(panel.edges)
            for panel in layout.panels
        },
        "edge_labels_visible": {
            panel.panel: panel.edge_labels_visible
            for panel in layout.panels
        },
        "weight_scale": layout.weight_scale.to_dict(),
        "sample_count": layout.sample_count,
        "node_radius": layout.node_radius,
        "geometry_source": "circular_network_analysis_report.json",
    }


def _compact_plot_spec(preparation: ScientificPreparation) -> dict[str, Any]:
    payload = asdict(preparation.plot_spec)
    layout = preparation.plot_spec.network_layout
    payload["network_layout"] = (
        _network_layout_summary(layout)
        if layout is not None
        else None
    )
    return payload


def _network_helper_table(
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> OriginNetworkTablePlan:
    """Build Origin helper columns without mutating the validated source frame."""

    source_snapshot = frame.copy(deep=True)
    layout = preparation.plot_spec.network_layout
    if layout is None:
        raise OriginDrawError("Circular-network geometry is missing.")
    node_groups = _node_group_map(preparation)
    group_order = tuple(dict.fromkeys(node_groups[node] for node in layout.node_order))
    node_by_name = {item.node: item for item in layout.nodes}
    row_count = max(
        layout.sample_count,
        max(sum(node_groups[node] == group for node in layout.node_order) for group in group_order),
        2,
    )
    helper: dict[str, np.ndarray] = {}
    edge_columns: list[NetworkEdgeColumnPlan] = []
    for panel_index, panel in enumerate(layout.panels, start=1):
        for edge_index, edge in enumerate(panel.edges, start=1):
            x_column = f"__P{panel_index:02d}_E{edge_index:03d}_X"
            y_column = f"__P{panel_index:02d}_E{edge_index:03d}_Y"
            x_values = np.full(row_count, np.nan, dtype=float)
            y_values = np.full(row_count, np.nan, dtype=float)
            x_values[: len(edge.sampled_points)] = [point.x for point in edge.sampled_points]
            y_values[: len(edge.sampled_points)] = [point.y for point in edge.sampled_points]
            helper[x_column] = x_values
            helper[y_column] = y_values
            edge_columns.append(
                NetworkEdgeColumnPlan(
                    panel=panel.panel,
                    order_index=edge_index - 1,
                    x_column=x_column,
                    y_column=y_column,
                    edge=edge,
                )
            )
    node_columns: list[NetworkNodeColumnPlan] = []
    for group_index, group in enumerate(group_order, start=1):
        nodes = tuple(node for node in layout.node_order if node_groups[node] == group)
        x_column = f"__G{group_index:02d}_NodeX"
        y_column = f"__G{group_index:02d}_NodeY"
        x_values = np.full(row_count, np.nan, dtype=float)
        y_values = np.full(row_count, np.nan, dtype=float)
        x_values[: len(nodes)] = [node_by_name[node].point.x for node in nodes]
        y_values[: len(nodes)] = [node_by_name[node].point.y for node in nodes]
        helper[x_column] = x_values
        helper[y_column] = y_values
        node_columns.append(
            NetworkNodeColumnPlan(
                group=group,
                order_index=group_index - 1,
                x_column=x_column,
                y_column=y_column,
                nodes=nodes,
            )
        )
    try:
        pd.testing.assert_frame_equal(
            frame,
            source_snapshot,
            check_exact=True,
            check_dtype=True,
            check_names=True,
        )
    except AssertionError as exc:
        raise OriginDrawError("Network table preparation modified the validated source frame.") from exc
    return OriginNetworkTablePlan(
        helper_frame=pd.DataFrame(helper),
        edge_columns=tuple(edge_columns),
        node_columns=tuple(node_columns),
        node_groups=tuple((node, node_groups[node]) for node in layout.node_order),
        source_frame_unchanged=True,
    )


def _network_layer_geometries(
    panel_count: int,
) -> tuple[tuple[NetworkLayerGeometry, ...], NetworkLayerGeometry]:
    """Return non-overlapping panel and bottom-legend rectangles."""

    if panel_count == 1:
        panels = (NetworkLayerGeometry(14.0, 5.0, 72.0, 73.0),)
        legend = NetworkLayerGeometry(6.0, 82.0, 88.0, 14.0)
    elif panel_count == 2:
        panels = (
            NetworkLayerGeometry(3.0, 5.0, 45.0, 73.0),
            NetworkLayerGeometry(52.0, 5.0, 45.0, 73.0),
        )
        legend = NetworkLayerGeometry(3.0, 82.0, 94.0, 14.0)
    elif panel_count == 3:
        panels = (
            NetworkLayerGeometry(1.5, 5.0, 31.0, 73.0),
            NetworkLayerGeometry(34.5, 5.0, 31.0, 73.0),
            NetworkLayerGeometry(67.5, 5.0, 31.0, 73.0),
        )
        legend = NetworkLayerGeometry(2.0, 82.0, 96.0, 14.0)
    elif panel_count == 4:
        panels = (
            NetworkLayerGeometry(4.0, 3.0, 43.0, 37.0),
            NetworkLayerGeometry(53.0, 3.0, 43.0, 37.0),
            NetworkLayerGeometry(4.0, 45.0, 43.0, 37.0),
            NetworkLayerGeometry(53.0, 45.0, 43.0, 37.0),
        )
        legend = NetworkLayerGeometry(4.0, 86.0, 92.0, 11.0)
    else:
        raise OriginDrawError("Circular networks support one to four panels.")
    return panels, legend


def _set_page_size(graph: Any, preparation: ScientificPreparation) -> dict[str, float]:
    style = _figure_style(preparation)
    width_in, height_in = page_size_inches(style)
    graph.activate()
    if not graph.obj.LT_execute("page.updatetoprinter=0;page.kar=0;"):
        raise OriginDrawError("Origin could not unlock the network page size.")
    state: dict[str, float] = {}
    for _attempt in range(3):
        if not graph.obj.LT_execute(
            f"page.width=({width_in:g})*page.resx;"
            f"page.height=({height_in:g})*page.resy;doc -uw;"
        ):
            raise OriginDrawError("Origin could not set the adaptive network page size.")
        state = {
            "width_cm": float(graph.obj.GetWidth()) * 2.54,
            "height_cm": float(graph.obj.GetHeight()) * 2.54,
        }
        if (
            abs(state["width_cm"] - style.page_width_cm) <= PAGE_SIZE_TOLERANCE_CM
            and abs(state["height_cm"] - style.page_height_cm) <= PAGE_SIZE_TOLERANCE_CM
        ):
            return state
    raise OriginDrawError(
        "Origin network page size failed readback: "
        f"{state.get('width_cm', math.nan):.3f} x "
        f"{state.get('height_cm', math.nan):.3f} cm."
    )


def _apply_layer_geometry(
    op: Any,
    layer: Any,
    geometry: NetworkLayerGeometry,
) -> dict[str, Any]:
    layer.set_int("unit", 1)
    layer.set_float("left", geometry.left)
    layer.set_float("top", geometry.top)
    layer.set_float("width", geometry.width)
    layer.set_float("height", geometry.height)
    layer.set_int("fixed", 1)
    layer.set_float("factor", 1.0)
    layer.obj.LT_execute("doc -uw;")
    readback = read_layer_geometry_percent(op, layer)
    state: dict[str, Any] = {
        "left": float(readback["left_percent"]),
        "top": float(readback["top_percent"]),
        "width": float(readback["width_percent"]),
        "height": float(readback["height_percent"]),
        "factor": float(readback["factor"]),
        "geometry_readback_source": readback["geometry_readback_source"],
        "bridge_geometry_consistent": readback["bridge_geometry_consistent"],
        "bridge_left_percent": readback["bridge_left_percent"],
    }
    expected = {**geometry.to_dict(), "factor": 1.0}
    if any(abs(state[key] - expected[key]) > 0.03 for key in expected):
        raise OriginDrawError("Origin network layer geometry failed readback.")
    return state


def _hide_axes(layer: Any) -> dict[str, float | int]:
    """Hide only the bottom/left axis pair; do not touch x2/y2 flags."""

    state: dict[str, float | int] = {}
    for axis_name in ("x", "y"):
        layer.set_int(f"{axis_name}.showAxes", 0)
        layer.set_int(f"{axis_name}.ticks", 0)
        layer.set_int(f"{axis_name}.minorTicks", 0)
        layer.set_int(f"{axis_name}.showLabels", 0)
        layer.set_int(f"{axis_name}.showlabel", 0)
        layer.set_int(f"{axis_name}.label.show", 0)
        layer.set_int(f"{axis_name}.showGrids", 0)
        for prop in ("showAxes", "ticks", "minorTicks", "showLabels"):
            state[f"{axis_name}.{prop}"] = int(layer.get_int(f"{axis_name}.{prop}"))
    if any(int(value) != 0 for value in state.values()):
        raise OriginDrawError("Origin did not keep circular-network axes hidden.")
    return state


def _scale_limits(
    preparation: ScientificPreparation,
    geometry: NetworkLayerGeometry,
) -> tuple[float, float, float, float]:
    style = _figure_style(preparation)
    physical_width = style.page_width_cm * geometry.width / 100.0
    physical_height = style.page_height_cm * geometry.height / 100.0
    ratio = physical_width / physical_height if physical_height > 0 else 1.0
    x_half = 1.34 * max(1.0, ratio)
    y_half = 1.34 * max(1.0, 1.0 / ratio)
    return -x_half, x_half, -y_half, y_half


def _set_layer_limits(
    layer: Any,
    limits: tuple[float, float, float, float],
) -> dict[str, float]:
    x_from, x_to, y_from, y_to = limits
    layer.axis("x").set_limits(x_from, x_to)
    layer.axis("y").set_limits(y_from, y_to)
    state = {
        "x.from": float(layer.get_float("x.from")),
        "x.to": float(layer.get_float("x.to")),
        "y.from": float(layer.get_float("y.from")),
        "y.to": float(layer.get_float("y.to")),
    }
    expected = {
        "x.from": x_from,
        "x.to": x_to,
        "y.from": y_from,
        "y.to": y_to,
    }
    if any(abs(state[key] - expected[key]) > 1e-6 for key in expected):
        raise OriginDrawError("Origin network axis ranges differ from the frozen geometry.")
    return state


def _remove_template_labels(layer: Any) -> None:
    for name in ("Legend", "legend", "xb", "yl"):
        label = layer.label(name)
        if label is not None:
            label.remove()


def _add_scale_label(
    op: Any,
    layer: Any,
    *,
    name: str,
    text: str,
    x: float,
    y: float,
    size_pt: float,
    font_code: int,
    color: str = "#20262B",
    bold: bool = False,
) -> Any:
    label = layer.add_label(text)
    if label is None:
        raise OriginDrawError(f"Origin could not add network text {text!r}.")
    label.name = name
    label.set_int("attach", 2)
    label.set_float("x1", float(x))
    label.set_float("y1", float(y))
    _style_label(label, size_pt, bold=bold)
    label.set_int("font", font_code)
    label.color = op.ocolor(color)
    actual_text = str(label.text)
    actual_attach = int(label.get_int("attach"))
    actual_size = float(label.get_float("fsize"))
    actual_font = int(round(float(label.get_float("font"))))
    if (
        actual_text != text
        or actual_attach != 2
        or abs(actual_size - size_pt) > 0.05
        or actual_font != font_code
    ):
        raise OriginDrawError(
            "Origin network text readback failed for "
            f"{text!r}: text={actual_text!r}, attach={actual_attach}, "
            f"size={actual_size:g}, font={actual_font}."
        )
    return label


def _node_label_position(node: Any) -> tuple[float, float]:
    x = float(node.point.x) * 1.13
    y = float(node.point.y) * 1.13
    text_width = min(0.58, max(0.10, len(node.node) * 0.035))
    if x < -0.25:
        x -= text_width
    elif abs(x) <= 0.25:
        x -= text_width * 0.50
    if y < -0.85:
        y -= 0.08
    return x, y


def _edge_line_state(
    op: Any,
    plot: Any,
    edge: CircularNetworkEdgeGeometry,
    *,
    variable_stem: str,
) -> dict[str, Any]:
    try:
        width = verify_plot_line_widths(
            op,
            {variable_stem: plot},
            edge.line_width_pt,
        )[variable_stem]
        color = verify_plot_color(
            op,
            plot,
            SIGN_COLORS[edge.sign],
            variable_name=f"__osc_{variable_stem}_color",
        )
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc
    transparency = float(plot.transparency)
    if abs(transparency - NETWORK_EDGE_TRANSPARENCY_PERCENT) > 0.05:
        raise OriginDrawError("Origin network edge transparency failed readback.")
    return {
        "source": edge.source,
        "target": edge.target,
        "weight": edge.weight,
        "sign": edge.sign,
        "label": edge.label,
        "plot_range": plot.lt_range(),
        "width": width,
        "color": color,
        "transparency_percent": transparency,
    }


def _arrow_state(
    op: Any,
    arrow: Any,
    edge: CircularNetworkEdgeGeometry,
) -> dict[str, Any]:
    expected = {
        "x1": edge.arrow_segment.start.x,
        "y1": edge.arrow_segment.start.y,
        "x2": edge.arrow_segment.end.x,
        "y2": edge.arrow_segment.end.y,
    }
    state: dict[str, Any] = {
        "name": arrow.name,
        "attach": int(arrow.get_int("attach")),
        "arrow_end_shape": int(arrow.get_int("arrowendshape")),
        "line_width_pt": float(arrow.width),
        "origin_color_code": float(arrow.get_float("color")),
    }
    state.update({key: float(arrow.get_float(key)) for key in expected})
    if state["attach"] != 2 or state["arrow_end_shape"] != 2:
        raise OriginDrawError("Origin network arrow attachment/shape failed readback.")
    if abs(state["line_width_pt"] - edge.line_width_pt) > 0.05:
        raise OriginDrawError("Origin network arrow width failed readback.")
    if int(state["origin_color_code"]) != int(op.ocolor(SIGN_COLORS[edge.sign])):
        raise OriginDrawError("Origin network arrow color failed readback.")
    if any(abs(float(state[key]) - value) > 1e-6 for key, value in expected.items()):
        raise OriginDrawError("Origin network arrow geometry failed readback.")
    return state


def _draw_panel(
    op: Any,
    layer: Any,
    helper_sheet: Any,
    preparation: ScientificPreparation,
    table: OriginNetworkTablePlan,
    *,
    panel_index: int,
    geometry: NetworkLayerGeometry,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    layout = preparation.plot_spec.network_layout
    if layout is None:
        raise OriginDrawError("Circular-network geometry is missing.")
    style = _figure_style(preparation)
    font_code = _origin_font_code(op, style.font_family)
    panel = layout.panels[panel_index]
    geometry_state = _apply_layer_geometry(op, layer, geometry)
    axis_state = _set_layer_limits(layer, _scale_limits(preparation, geometry))
    axis_state.update(_hide_axes(layer))
    _remove_template_labels(layer)
    edge_plots: list[dict[str, Any]] = []
    arrows: list[dict[str, Any]] = []
    labels: dict[str, Any] = {}
    expected_sizes: dict[str, float] = {}

    panel_edges = [item for item in table.edge_columns if item.panel == panel.panel]
    for edge_index, item in enumerate(panel_edges, start=1):
        edge = item.edge
        plot = layer.add_plot(helper_sheet, item.y_column, item.x_column, type="l")
        if plot is None:
            raise OriginDrawError("Origin could not create every circular-network edge path.")
        color = SIGN_COLORS[edge.sign]
        plot.color = color
        plot.set_cmd(
            f"-c color({color})",
            f"-w {pt_to_origin_width_units(edge.line_width_pt)}",
            "-d 0",
        )
        plot.transparency = NETWORK_EDGE_TRANSPARENCY_PERCENT
        variable_stem = f"net_p{panel_index + 1}_e{edge_index}"
        edge_plots.append(_edge_line_state(op, plot, edge, variable_stem=variable_stem))

        arrow = layer.add_line(
            edge.arrow_segment.start.x,
            edge.arrow_segment.start.y,
            edge.arrow_segment.end.x,
            edge.arrow_segment.end.y,
        )
        if arrow is None:
            raise OriginDrawError("Origin could not create every circular-network arrow.")
        arrow.name = f"NetArrow_P{panel_index + 1:02d}_E{edge_index:03d}"
        arrow.color = color
        arrow.width = edge.line_width_pt
        arrow.set_int("arrowendshape", 2)
        arrows.append(_arrow_state(op, arrow, edge))

        if edge.label and panel.edge_labels_visible:
            edge_label_size = float(round(max(10.0, style.legend_size_pt * 0.72)))
            label_name = f"edge_label_p{panel_index + 1}_{edge_index}"
            labels[label_name] = _add_scale_label(
                op,
                layer,
                name=f"NetEdgeLabel_P{panel_index + 1:02d}_E{edge_index:03d}",
                text=edge.label,
                x=edge.label_anchor.x + 0.025,
                y=edge.label_anchor.y + 0.025,
                size_pt=edge_label_size,
                font_code=font_code,
                color="#4D5963",
                bold=False,
            )
            expected_sizes[label_name] = edge_label_size

    node_plots: list[dict[str, Any]] = []
    group_colors = _node_group_colors(
        preparation,
        tuple(item.group for item in table.node_columns),
    )
    for item in table.node_columns:
        plot = layer.add_plot(helper_sheet, item.y_column, item.x_column, type="s")
        if plot is None:
            raise OriginDrawError("Origin could not create circular-network node markers.")
        color = group_colors[item.group]
        plot.color = color
        plot.symbol_kind = 2
        plot.symbol_interior = 0
        plot.symbol_size = NETWORK_NODE_MARKER_SIZE_PT
        plot.set_cmd(
            f"-c color({color})",
            "-k 2",
            "-kf 0",
            f"-z {NETWORK_NODE_MARKER_SIZE_PT:g}",
            f"-kh {NETWORK_NODE_EDGE_PERCENT:g}",
        )
        try:
            symbol_state = verify_symbol_style(
                op,
                plot,
                expected_size_pt=NETWORK_NODE_MARKER_SIZE_PT,
                expected_edge_percent=NETWORK_NODE_EDGE_PERCENT,
            )
            color_state = verify_plot_color(
                op,
                plot,
                color,
                variable_name=f"__osc_node_p{panel_index + 1}_{item.order_index + 1}_color",
            )
        except RuntimeError as exc:
            raise OriginDrawError(str(exc)) from exc
        node_plots.append(
            {
                "group": item.group,
                "nodes": list(item.nodes),
                "plot_range": plot.lt_range(),
                "symbol": symbol_state,
                "color": color_state,
            }
        )

    title_size = style.axis_title_size_pt
    title_x = -min(0.72, max(0.18, len(panel.panel) * 0.035))
    label_name = f"panel_title_{panel_index + 1}"
    labels[label_name] = _add_scale_label(
        op,
        layer,
        name=f"NetPanelTitle_{panel_index + 1:02d}",
        text=panel.panel,
        x=title_x,
        y=float(axis_state["y.to"]) * 1.03,
        size_pt=title_size,
        font_code=font_code,
        color="#20262B",
        bold=True,
    )
    expected_sizes[label_name] = title_size
    for node_index, node in enumerate(layout.nodes, start=1):
        x, y = _node_label_position(node)
        key = f"node_label_p{panel_index + 1}_{node_index}"
        labels[key] = _add_scale_label(
            op,
            layer,
            name=f"NetNode_P{panel_index + 1:02d}_N{node_index:02d}",
            text=node.node,
            x=x,
            y=y,
            size_pt=style.tick_label_size_pt,
            font_code=font_code,
            color="#20262B",
            bold=True,
        )
        expected_sizes[key] = style.tick_label_size_pt

    try:
        text_state: dict[str, Any] = {
            **verify_text_sizes(labels, expected_sizes),
            **verify_text_fonts(op, labels, style.font_family),
        }
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc
    return (
        {
            **geometry_state,
            "panel": panel.panel,
            "axis_limits": {
                key: axis_state[key]
                for key in ("x.from", "x.to", "y.from", "y.to")
            },
        },
        {
            "panel": panel.panel,
            "edges": edge_plots,
            "arrows": arrows,
            "nodes": node_plots,
            "group_colors": group_colors,
            "edge_labels_visible": panel.edge_labels_visible,
        },
        text_state,
    )


def _legend_entries(
    table: OriginNetworkTablePlan,
    layout: CircularNetworkLayoutPlan,
    preparation: ScientificPreparation,
) -> tuple[tuple[str, str, str], ...]:
    entries: list[tuple[str, str, str]] = []
    group_order = tuple(dict.fromkeys(group for _, group in table.node_groups))
    group_colors = _node_group_colors(preparation, group_order)
    entries.extend(("group", group, group_colors[group]) for group in group_order)
    signs = tuple(
        sign
        for sign in ("positive", "negative", "neutral")
        if any(edge.sign == sign for panel in layout.panels for edge in panel.edges)
    )
    entries.extend(("sign", sign.title(), SIGN_COLORS[sign]) for sign in signs)
    entries.append(("note", "Line width = Weight", "#4D5963"))
    return tuple(entries)


def _draw_legend(
    op: Any,
    layer: Any,
    preparation: ScientificPreparation,
    table: OriginNetworkTablePlan,
    geometry: NetworkLayerGeometry,
) -> tuple[dict[str, Any], dict[str, Any]]:
    layout = preparation.plot_spec.network_layout
    if layout is None:
        raise OriginDrawError("Circular-network geometry is missing.")
    style = _figure_style(preparation)
    font_code = _origin_font_code(op, style.font_family)
    geometry_state = _apply_layer_geometry(op, layer, geometry)
    layer.axis("x").set_limits(0.0, 1.0)
    layer.axis("y").set_limits(0.0, 1.0)
    axis_state = {
        "x.from": float(layer.get_float("x.from")),
        "x.to": float(layer.get_float("x.to")),
        "y.from": float(layer.get_float("y.from")),
        "y.to": float(layer.get_float("y.to")),
    }
    axis_state.update(_hide_axes(layer))
    _remove_template_labels(layer)
    entries = _legend_entries(table, layout, preparation)
    columns = min(6, max(1, len(entries)))
    rows = math.ceil(len(entries) / columns)
    labels: dict[str, Any] = {}
    expected_sizes: dict[str, float] = {}
    line_state: list[dict[str, Any]] = []
    for index, (kind, text, color) in enumerate(entries):
        row = index // columns
        column = index % columns
        x = 0.02 + column / columns
        y = 0.78 - row * (0.68 / max(1, rows))
        key = f"legend_{index + 1}"
        if kind == "group":
            swatch_key = f"{key}_swatch"
            text_key = f"{key}_text"
            labels[swatch_key] = _add_scale_label(
                op,
                layer,
                name=f"NetLegendSwatch_{index + 1:02d}",
                text="■",
                x=x,
                y=y,
                size_pt=style.legend_size_pt,
                font_code=font_code,
                color=color,
                bold=False,
            )
            labels[text_key] = _add_scale_label(
                op,
                layer,
                name=f"NetLegend_{index + 1:02d}",
                text=text,
                x=x + 0.015,
                y=y,
                size_pt=style.legend_size_pt,
                font_code=font_code,
                color="#20262B",
                bold=False,
            )
            expected_sizes[swatch_key] = style.legend_size_pt
            expected_sizes[text_key] = style.legend_size_pt
        elif kind == "sign":
            line = layer.add_line(x, y + 0.03, x + 0.035, y + 0.03)
            if line is None:
                raise OriginDrawError("Origin could not create the network legend swatch.")
            line.name = f"NetLegendLine_{index + 1:02d}"
            line.color = color
            line.width = 2.4
            line.set_int("arrowendshape", 2)
            line_state.append(
                {
                    "name": line.name,
                    "attach": int(line.get_int("attach")),
                    "arrow_end_shape": int(line.get_int("arrowendshape")),
                    "line_width_pt": float(line.width),
                    "origin_color_code": float(line.get_float("color")),
                }
            )
            labels[key] = _add_scale_label(
                op,
                layer,
                name=f"NetLegend_{index + 1:02d}",
                text=text,
                x=x + 0.045,
                y=y,
                size_pt=style.legend_size_pt,
                font_code=font_code,
                color="#20262B",
                bold=False,
            )
        else:
            labels[key] = _add_scale_label(
                op,
                layer,
                name=f"NetLegend_{index + 1:02d}",
                text=text,
                x=x,
                y=y,
                size_pt=style.legend_size_pt,
                font_code=font_code,
                color=color,
                bold=False,
            )
        if kind != "group":
            expected_sizes[key] = style.legend_size_pt
    if any(
        item["attach"] != 2
        or item["arrow_end_shape"] != 2
        or abs(item["line_width_pt"] - 2.4) > 0.05
        for item in line_state
    ):
        raise OriginDrawError("Origin network legend line-object readback failed.")
    try:
        text_state: dict[str, Any] = {
            **verify_text_sizes(labels, expected_sizes),
            **verify_text_fonts(op, labels, style.font_family),
        }
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc
    return (
        {
            **geometry_state,
            "axis_state": axis_state,
            "showframe": 0,
            "entries": [
                {"kind": kind, "label": text, "color": color}
                for kind, text, color in entries
            ],
            "line_objects": line_state,
        },
        text_state,
    )


def _build_origin_graph(
    op: Any,
    frame: pd.DataFrame,
    output: RunOutput,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    layout = preparation.plot_spec.network_layout
    if layout is None:
        raise OriginDrawError("Circular-network geometry is missing.")
    table = _network_helper_table(frame, preparation)
    source_sheet = op.new_sheet("w", "CIRCULAR NETWORK Source")
    if source_sheet is None:
        raise OriginDrawError("Origin could not create the network source worksheet.")
    source_sheet.from_df(frame.copy(deep=True))
    source_sheet.cols_axis()
    helper_sheet = op.new_sheet("w", "CIRCULAR NETWORK Helpers")
    if helper_sheet is None:
        raise OriginDrawError("Origin could not create the network helper worksheet.")
    helper_sheet.from_df(table.helper_frame)
    helper_sheet.cols_axis("xy")

    graph = op.new_graph("CIRCULAR NETWORK Figure", template="Line")
    if graph is None:
        raise OriginDrawError("Origin could not create the circular-network graph.")
    graph.set_int("background", op.ocolor("#FFFFFF"))
    page_state = _set_page_size(graph, preparation)
    panel_geometries, legend_geometry = _network_layer_geometries(len(layout.panels))
    layers = [graph[0]]
    for _index in range(len(layout.panels)):
        layer = graph.add_layer(0)
        if layer is None:
            raise OriginDrawError("Origin could not add every circular-network layer.")
        layers.append(layer)
    panel_layers = layers[: len(layout.panels)]
    legend_layer = layers[-1]
    if len(graph) != len(layout.panels) + 1:
        raise OriginDrawError("Origin circular-network layer count failed readback.")

    panel_states: list[dict[str, Any]] = []
    plot_states: list[dict[str, Any]] = []
    text_states: list[dict[str, Any]] = []
    for panel_index, (layer, geometry) in enumerate(
        zip(panel_layers, panel_geometries, strict=True)
    ):
        panel_state, plot_state, text_state = _draw_panel(
            op,
            layer,
            helper_sheet,
            preparation,
            table,
            panel_index=panel_index,
            geometry=geometry,
        )
        panel_states.append(panel_state)
        plot_states.append(plot_state)
        text_states.append(text_state)
    legend_state, legend_text_state = _draw_legend(
        op,
        legend_layer,
        preparation,
        table,
        legend_geometry,
    )
    graph.activate()
    op.lt_exec("doc -uw;")

    if not table.source_frame_unchanged:
        raise OriginDrawError("Circular-network source data were modified.")
    if output.result_opju.exists():
        raise OriginDrawError("Circular-network output path was unexpectedly pre-existing.")
    if not op.save(str(output.result_opju)):
        raise OriginDrawError("Origin did not save result.opju")
    require_nonempty(output.result_opju)

    style = _figure_style(preparation)
    report = {
        **page_state,
        "template_id": preparation.template_id,
        "plan_digest": preparation.plan_digest,
        "plot_spec": _compact_plot_spec(preparation),
        "source_sha256": preparation.source_sha256,
        "source_columns": list(preparation.source_columns),
        "origin_helper_columns": list(table.helper_frame.columns),
        "origin_axis_state": {
            "plot_kind": "circular_network",
            "layer_count": len(graph),
            "panel_count": len(layout.panels),
            "panels": panel_states,
            "legend_layer": legend_state,
        },
        "origin_plot_state": {
            "panels": plot_states,
            "sign_colors": SIGN_COLORS,
            "node_group_colors": _node_group_colors(
                preparation,
                tuple(dict.fromkeys(group for _, group in table.node_groups)),
            ),
            "layout": _network_layout_summary(layout),
        },
        "origin_text_state": {
            "panels": text_states,
            "legend": legend_text_state,
            "font_family_expected": style.font_family,
            "axis_title_size_pt": style.axis_title_size_pt,
            "tick_label_size_pt": style.tick_label_size_pt,
            "legend_size_pt": style.legend_size_pt,
            "adaptive_profile": style.to_dict(),
        },
        "source_data_modified": False,
    }
    return graph, report


def run_network_template(
    manifest: TemplateManifest,
    frame: pd.DataFrame,
    output: RunOutput,
    logger: RunLogger,
    *,
    keep_origin_open: bool = True,
    preparation: ScientificPreparation | None = None,
) -> dict[str, Any]:
    """Render and verify one circular directed weighted network in Origin."""

    resolved = _resolve_preparation(manifest, frame, output, preparation)
    with OriginSession(keep_open=keep_origin_open) as session:
        op = session.op
        if op is None or session.environment is None:
            raise OriginDrawError("Origin session was not initialized.")
        logger.write(f"Origin connected: version {session.environment.origin_version}")
        graph, verify_report = _build_origin_graph(op, frame, output, resolved)
        exports = export_graph(
            op,
            graph,
            output.result_png,
            output.result_pdf,
            output.result_tif,
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
        logger.write("Circular-network Origin graph verified and exported")
    return {
        "opju": str(output.result_opju),
        "png": str(output.result_png),
        "pdf": str(output.result_pdf),
        "tif": str(output.result_tif),
        "verify": verify_report,
    }


__all__ = [
    "NETWORK_EDGE_TRANSPARENCY_PERCENT",
    "NETWORK_NODE_MARKER_SIZE_PT",
    "NODE_GROUP_COLORS",
    "SIGN_COLORS",
    "NetworkEdgeColumnPlan",
    "NetworkLayerGeometry",
    "NetworkNodeColumnPlan",
    "OriginNetworkTablePlan",
    "_network_helper_table",
    "_network_layer_geometries",
    "run_network_template",
]
