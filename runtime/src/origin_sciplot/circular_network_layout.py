"""Deterministic geometry for small-multiple circular directed networks.

The module deliberately contains no Origin, Matplotlib, or NetworkX calls.
Renderers receive one frozen plan with shared node coordinates and a shared
weight-to-line-width scale, so preview and editable output can use identical
geometry.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
from typing import Any

MIN_PANEL_COUNT = 1
MAX_PANEL_COUNT = 4
MIN_NODE_COUNT = 2
MAX_NODE_GROUP_COUNT = 4
DEFAULT_SAMPLE_COUNT = 33
MIN_SAMPLE_COUNT = 5
DEFAULT_NODE_RADIUS = 0.08
MIN_LINE_WIDTH_PT = 1.2
MAX_LINE_WIDTH_PT = 4.2
MAX_VISIBLE_EDGE_LABELS_PER_PANEL = 12
NETWORK_EDGE_TRANSPARENCY_PERCENT = 8.0
NETWORK_NODE_GROUP_COLORS: tuple[str, ...] = (
    "#D8E7F0",
    "#E8DED0",
    "#DFE8D8",
    "#E6DCEB",
)
DEFAULT_CURVATURE = 0.22
RECIPROCAL_CURVATURE = 0.28
VALID_SIGNS = frozenset({"positive", "negative", "neutral"})


def _clean_zero(value: float) -> float:
    """Avoid serializing visually surprising ``-0.0`` coordinates."""

    return 0.0 if abs(value) < 1e-15 else float(value)


@dataclass(frozen=True, slots=True)
class Point2D:
    """One Cartesian point in the shared unit-circle coordinate system."""

    x: float
    y: float

    def to_dict(self) -> dict[str, float]:
        return {"x": _clean_zero(self.x), "y": _clean_zero(self.y)}


@dataclass(frozen=True, slots=True)
class LineSegment2D:
    """Short terminal segment whose direction is the arrow tangent."""

    start: Point2D
    end: Point2D

    def to_dict(self) -> dict[str, object]:
        return {"start": self.start.to_dict(), "end": self.end.to_dict()}


@dataclass(frozen=True, slots=True)
class CircularNetworkEdgeRecord:
    """Validated semantic input for one directed edge."""

    panel: str
    source: str
    target: str
    weight: float
    sign: str = "neutral"
    label: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "panel": self.panel,
            "source": self.source,
            "target": self.target,
            "weight": float(self.weight),
            "sign": self.sign,
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class CircularNetworkNodeGeometry:
    """Shared position for one node; panels do not duplicate coordinates."""

    node: str
    order_index: int
    angle_deg: float
    point: Point2D

    def to_dict(self) -> dict[str, object]:
        return {
            "node": self.node,
            "order_index": self.order_index,
            "angle_deg": _clean_zero(self.angle_deg),
            "point": self.point.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class CircularNetworkWeightScale:
    """Global linear mapping from positive weights to stroke widths."""

    weight_min: float
    weight_max: float
    line_width_min_pt: float = MIN_LINE_WIDTH_PT
    line_width_max_pt: float = MAX_LINE_WIDTH_PT

    def map_weight(self, weight: float) -> float:
        numeric = _positive_finite_number(weight, field="weight")
        if numeric < self.weight_min or numeric > self.weight_max:
            raise ValueError(
                f"weight {numeric!r} is outside the frozen scale "
                f"[{self.weight_min!r}, {self.weight_max!r}]"
            )
        if math.isclose(self.weight_min, self.weight_max, rel_tol=0.0, abs_tol=1e-15):
            return (self.line_width_min_pt + self.line_width_max_pt) / 2.0
        fraction = (numeric - self.weight_min) / (self.weight_max - self.weight_min)
        return self.line_width_min_pt + fraction * (
            self.line_width_max_pt - self.line_width_min_pt
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "weight_min": float(self.weight_min),
            "weight_max": float(self.weight_max),
            "line_width_min_pt": float(self.line_width_min_pt),
            "line_width_max_pt": float(self.line_width_max_pt),
        }


@dataclass(frozen=True, slots=True)
class CircularNetworkEdgeGeometry:
    """Cubic Bézier path and renderer-ready annotations for one edge."""

    panel: str
    source: str
    target: str
    weight: float
    sign: str
    label: str
    line_width_pt: float
    curvature: float
    control_points: tuple[Point2D, Point2D, Point2D, Point2D]
    sampled_points: tuple[Point2D, ...]
    arrow_segment: LineSegment2D
    label_anchor: Point2D

    def to_dict(self) -> dict[str, object]:
        return {
            "panel": self.panel,
            "source": self.source,
            "target": self.target,
            "weight": float(self.weight),
            "sign": self.sign,
            "label": self.label,
            "line_width_pt": float(self.line_width_pt),
            "curvature": float(self.curvature),
            "control_points": [point.to_dict() for point in self.control_points],
            "sampled_points": [point.to_dict() for point in self.sampled_points],
            "arrow_segment": self.arrow_segment.to_dict(),
            "label_anchor": self.label_anchor.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class CircularNetworkPanelGeometry:
    """Ordered edge geometry for one requested panel."""

    panel: str
    order_index: int
    edges: tuple[CircularNetworkEdgeGeometry, ...]
    edge_labels_visible: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "panel": self.panel,
            "order_index": self.order_index,
            "edges": [edge.to_dict() for edge in self.edges],
            "edge_labels_visible": self.edge_labels_visible,
        }


@dataclass(frozen=True, slots=True)
class CircularNetworkLayoutPlan:
    """Complete renderer-neutral plan for one to four panels."""

    panel_order: tuple[str, ...]
    node_order: tuple[str, ...]
    nodes: tuple[CircularNetworkNodeGeometry, ...]
    panels: tuple[CircularNetworkPanelGeometry, ...]
    weight_scale: CircularNetworkWeightScale
    sample_count: int
    node_radius: float

    def to_dict(self) -> dict[str, object]:
        return {
            "panel_order": list(self.panel_order),
            "node_order": list(self.node_order),
            "nodes": [node.to_dict() for node in self.nodes],
            "panels": [panel.to_dict() for panel in self.panels],
            "weight_scale": self.weight_scale.to_dict(),
            "sample_count": self.sample_count,
            "node_radius": float(self.node_radius),
        }


def _ordered_unique_strings(
    values: Sequence[str],
    *,
    field: str,
    minimum: int,
    maximum: int | None = None,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field} must be an ordered sequence of strings")
    result = tuple(values)
    if len(result) < minimum:
        raise ValueError(f"{field} must contain at least {minimum} item(s)")
    if maximum is not None and len(result) > maximum:
        raise ValueError(f"{field} may contain at most {maximum} items")
    seen: set[str] = set()
    for index, value in enumerate(result):
        if not isinstance(value, str):
            raise TypeError(f"{field}[{index}] must be a string")
        if not value.strip():
            raise ValueError(f"{field}[{index}] must be non-empty")
        if value != value.strip():
            raise ValueError(f"{field}[{index}] must not contain leading or trailing whitespace")
        if value in seen:
            raise ValueError(f"{field} contains duplicate item {value!r}")
        seen.add(value)
    return result


def _positive_finite_number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field} must be a real number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field} must be finite")
    if numeric <= 0.0:
        raise ValueError(f"{field} must be greater than zero")
    return numeric


def _coerce_edge_record(
    value: CircularNetworkEdgeRecord | Mapping[str, Any],
    *,
    index: int,
) -> CircularNetworkEdgeRecord:
    if isinstance(value, CircularNetworkEdgeRecord):
        candidate = value
    elif isinstance(value, Mapping):
        missing = [key for key in ("panel", "source", "target", "weight") if key not in value]
        if missing:
            raise ValueError(f"edges[{index}] is missing required field(s): {', '.join(missing)}")
        candidate = CircularNetworkEdgeRecord(
            panel=value["panel"],
            source=value["source"],
            target=value["target"],
            weight=value["weight"],
            sign=value.get("sign", "neutral"),
            label=value.get("label", ""),
        )
    else:
        raise TypeError(f"edges[{index}] must be CircularNetworkEdgeRecord or a mapping")

    for field_name in ("panel", "source", "target"):
        text = getattr(candidate, field_name)
        if not isinstance(text, str):
            raise TypeError(f"edges[{index}].{field_name} must be a string")
        if not text.strip():
            raise ValueError(f"edges[{index}].{field_name} must be non-empty")
        if text != text.strip():
            raise ValueError(
                f"edges[{index}].{field_name} must not contain leading or trailing whitespace"
            )
    if not isinstance(candidate.sign, str):
        raise TypeError(f"edges[{index}].sign must be a string")
    if candidate.sign not in VALID_SIGNS:
        allowed = ", ".join(sorted(VALID_SIGNS))
        raise ValueError(f"edges[{index}].sign must be one of: {allowed}")
    if not isinstance(candidate.label, str):
        raise TypeError(f"edges[{index}].label must be a string")
    return CircularNetworkEdgeRecord(
        panel=candidate.panel,
        source=candidate.source,
        target=candidate.target,
        weight=_positive_finite_number(candidate.weight, field=f"edges[{index}].weight"),
        sign=candidate.sign,
        label=candidate.label,
    )


def _unit_circle_nodes(node_order: tuple[str, ...]) -> tuple[CircularNetworkNodeGeometry, ...]:
    count = len(node_order)
    result: list[CircularNetworkNodeGeometry] = []
    for index, node in enumerate(node_order):
        angle = math.pi / 2.0 - (2.0 * math.pi * index / count)
        result.append(
            CircularNetworkNodeGeometry(
                node=node,
                order_index=index,
                angle_deg=math.degrees(angle),
                point=Point2D(math.cos(angle), math.sin(angle)),
            )
        )
    return tuple(result)


def _bezier_point(
    control_points: tuple[Point2D, Point2D, Point2D, Point2D],
    t: float,
) -> Point2D:
    p0, p1, p2, p3 = control_points
    one_minus_t = 1.0 - t
    b0 = one_minus_t**3
    b1 = 3.0 * one_minus_t**2 * t
    b2 = 3.0 * one_minus_t * t**2
    b3 = t**3
    return Point2D(
        b0 * p0.x + b1 * p1.x + b2 * p2.x + b3 * p3.x,
        b0 * p0.y + b1 * p1.y + b2 * p2.y + b3 * p3.y,
    )


def _canonical_normal(
    source_index: int,
    target_index: int,
    nodes: tuple[CircularNetworkNodeGeometry, ...],
) -> tuple[float, float, float, int]:
    low_index, high_index = sorted((source_index, target_index))
    low = nodes[low_index].point
    high = nodes[high_index].point
    dx = high.x - low.x
    dy = high.y - low.y
    length = math.hypot(dx, dy)
    if length <= 1e-15:
        raise ValueError("distinct circular-network nodes must not share coordinates")
    normal_x = -dy / length
    normal_y = dx / length
    midpoint_x = (low.x + high.x) / 2.0
    midpoint_y = (low.y + high.y) / 2.0
    inward_dot = (-midpoint_x * normal_x) + (-midpoint_y * normal_y)
    inward_sign = 1 if inward_dot >= 0.0 else -1
    return normal_x, normal_y, length, inward_sign


def _control_points(
    *,
    source_index: int,
    target_index: int,
    nodes: tuple[CircularNetworkNodeGeometry, ...],
    reciprocal: bool,
    node_radius: float,
) -> tuple[float, tuple[Point2D, Point2D, Point2D, Point2D]]:
    source_center = nodes[source_index].point
    target_center = nodes[target_index].point
    center_dx = target_center.x - source_center.x
    center_dy = target_center.y - source_center.y
    center_distance = math.hypot(center_dx, center_dy)
    if center_distance <= 1e-15:
        raise ValueError("distinct circular-network nodes must not share coordinates")
    unit_x = center_dx / center_distance
    unit_y = center_dy / center_distance
    p0 = Point2D(
        source_center.x + unit_x * node_radius,
        source_center.y + unit_y * node_radius,
    )
    p3 = Point2D(
        target_center.x - unit_x * node_radius,
        target_center.y - unit_y * node_radius,
    )
    normal_x, normal_y, _, inward_sign = _canonical_normal(
        source_index,
        target_index,
        nodes,
    )
    chord_length = math.hypot(p3.x - p0.x, p3.y - p0.y)
    magnitude = RECIPROCAL_CURVATURE if reciprocal else DEFAULT_CURVATURE
    if reciprocal and source_index > target_index:
        curvature = -inward_sign * magnitude
    else:
        curvature = inward_sign * magnitude
    offset_x = normal_x * curvature * chord_length
    offset_y = normal_y * curvature * chord_length
    p1 = Point2D(
        p0.x + (p3.x - p0.x) * 0.30 + offset_x,
        p0.y + (p3.y - p0.y) * 0.30 + offset_y,
    )
    p2 = Point2D(
        p0.x + (p3.x - p0.x) * 0.70 + offset_x,
        p0.y + (p3.y - p0.y) * 0.70 + offset_y,
    )
    return curvature, (p0, p1, p2, p3)


def _arrow_segment(
    control_points: tuple[Point2D, Point2D, Point2D, Point2D],
) -> LineSegment2D:
    p0, _, p2, p3 = control_points
    tangent_x = p3.x - p2.x
    tangent_y = p3.y - p2.y
    tangent_length = math.hypot(tangent_x, tangent_y)
    if tangent_length <= 1e-15:
        raise ValueError("edge terminal tangent must be non-zero")
    chord_length = math.hypot(p3.x - p0.x, p3.y - p0.y)
    segment_length = min(0.14, max(0.06, chord_length * 0.10))
    unit_x = tangent_x / tangent_length
    unit_y = tangent_y / tangent_length
    return LineSegment2D(
        start=Point2D(p3.x - unit_x * segment_length, p3.y - unit_y * segment_length),
        end=p3,
    )


def resolve_circular_network_layout(
    *,
    panel_order: Sequence[str],
    node_order: Sequence[str],
    edges: Sequence[CircularNetworkEdgeRecord | Mapping[str, Any]],
    sample_count: int = DEFAULT_SAMPLE_COUNT,
    node_radius: float = DEFAULT_NODE_RADIUS,
) -> CircularNetworkLayoutPlan:
    """Resolve shared circular-network geometry without inferring any order.

    ``panel_order`` and ``node_order`` are authoritative. Edge input order is
    intentionally ignored: each panel is sorted by source and target node
    order, making the result stable across CSV row permutations.
    """

    panels = _ordered_unique_strings(
        panel_order,
        field="panel_order",
        minimum=MIN_PANEL_COUNT,
        maximum=MAX_PANEL_COUNT,
    )
    nodes_ordered = _ordered_unique_strings(
        node_order,
        field="node_order",
        minimum=MIN_NODE_COUNT,
    )
    if isinstance(sample_count, bool) or not isinstance(sample_count, int):
        raise TypeError("sample_count must be an integer")
    if sample_count < MIN_SAMPLE_COUNT:
        raise ValueError(f"sample_count must be at least {MIN_SAMPLE_COUNT}")
    radius = _positive_finite_number(node_radius, field="node_radius")
    if radius >= 0.5:
        raise ValueError("node_radius must be less than 0.5 unit-circle units")
    if isinstance(edges, (str, bytes)) or not isinstance(edges, Sequence):
        raise TypeError("edges must be an ordered sequence")
    if not edges:
        raise ValueError("edges must contain at least one record")

    panel_index = {panel: index for index, panel in enumerate(panels)}
    node_index = {node: index for index, node in enumerate(nodes_ordered)}
    normalized_edges: list[CircularNetworkEdgeRecord] = []
    seen_pairs: set[tuple[str, str, str]] = set()
    for index, value in enumerate(edges):
        edge = _coerce_edge_record(value, index=index)
        if edge.panel not in panel_index:
            raise ValueError(f"edges[{index}].panel {edge.panel!r} is absent from panel_order")
        if edge.source not in node_index:
            raise ValueError(f"edges[{index}].source {edge.source!r} is absent from node_order")
        if edge.target not in node_index:
            raise ValueError(f"edges[{index}].target {edge.target!r} is absent from node_order")
        if edge.source == edge.target:
            raise ValueError(
                f"edges[{index}] is a self-loop ({edge.source!r}); self-loops must be rejected upstream"
            )
        pair = (edge.panel, edge.source, edge.target)
        if pair in seen_pairs:
            raise ValueError(
                f"duplicate directed edge in panel {edge.panel!r}: "
                f"{edge.source!r} -> {edge.target!r}"
            )
        seen_pairs.add(pair)
        normalized_edges.append(edge)

    normalized_edges.sort(
        key=lambda edge: (
            panel_index[edge.panel],
            node_index[edge.source],
            node_index[edge.target],
            edge.sign,
            edge.label,
        )
    )
    weights = tuple(edge.weight for edge in normalized_edges)
    scale = CircularNetworkWeightScale(weight_min=min(weights), weight_max=max(weights))
    node_geometry = _unit_circle_nodes(nodes_ordered)
    directed_pairs = {
        (edge.panel, edge.source, edge.target)
        for edge in normalized_edges
    }
    edges_by_panel: dict[str, list[CircularNetworkEdgeGeometry]] = {
        panel: [] for panel in panels
    }
    for edge in normalized_edges:
        reciprocal = (edge.panel, edge.target, edge.source) in directed_pairs
        curvature, controls = _control_points(
            source_index=node_index[edge.source],
            target_index=node_index[edge.target],
            nodes=node_geometry,
            reciprocal=reciprocal,
            node_radius=radius,
        )
        sampled = tuple(
            _bezier_point(controls, sample_index / (sample_count - 1))
            for sample_index in range(sample_count)
        )
        edges_by_panel[edge.panel].append(
            CircularNetworkEdgeGeometry(
                panel=edge.panel,
                source=edge.source,
                target=edge.target,
                weight=edge.weight,
                sign=edge.sign,
                label=edge.label,
                line_width_pt=scale.map_weight(edge.weight),
                curvature=curvature,
                control_points=controls,
                sampled_points=sampled,
                arrow_segment=_arrow_segment(controls),
                label_anchor=_bezier_point(controls, 0.5),
            )
        )

    panel_geometry = tuple(
        CircularNetworkPanelGeometry(
            panel=panel,
            order_index=index,
            edges=tuple(edges_by_panel[panel]),
            edge_labels_visible=(
                len(edges_by_panel[panel]) <= MAX_VISIBLE_EDGE_LABELS_PER_PANEL
            ),
        )
        for index, panel in enumerate(panels)
    )
    return CircularNetworkLayoutPlan(
        panel_order=panels,
        node_order=nodes_ordered,
        nodes=node_geometry,
        panels=panel_geometry,
        weight_scale=scale,
        sample_count=sample_count,
        node_radius=radius,
    )


__all__ = [
    "DEFAULT_CURVATURE",
    "DEFAULT_NODE_RADIUS",
    "DEFAULT_SAMPLE_COUNT",
    "MAX_LINE_WIDTH_PT",
    "MAX_NODE_GROUP_COUNT",
    "MAX_PANEL_COUNT",
    "MAX_VISIBLE_EDGE_LABELS_PER_PANEL",
    "MIN_LINE_WIDTH_PT",
    "NETWORK_EDGE_TRANSPARENCY_PERCENT",
    "NETWORK_NODE_GROUP_COLORS",
    "RECIPROCAL_CURVATURE",
    "VALID_SIGNS",
    "CircularNetworkEdgeGeometry",
    "CircularNetworkEdgeRecord",
    "CircularNetworkLayoutPlan",
    "CircularNetworkNodeGeometry",
    "CircularNetworkPanelGeometry",
    "CircularNetworkWeightScale",
    "LineSegment2D",
    "Point2D",
    "resolve_circular_network_layout",
]
