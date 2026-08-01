from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.circular_network_layout import (  # noqa: E402
    MAX_LINE_WIDTH_PT,
    MAX_VISIBLE_EDGE_LABELS_PER_PANEL,
    MIN_LINE_WIDTH_PT,
    CircularNetworkEdgeRecord,
    resolve_circular_network_layout,
)


def _two_panel_edges() -> list[CircularNetworkEdgeRecord]:
    return [
        CircularNetworkEdgeRecord(
            panel="2000–2010",
            source="Exposure",
            target="Risk",
            weight=0.90,
            sign="positive",
            label="L1.0 | W0.90",
        ),
        CircularNetworkEdgeRecord(
            panel="2000–2010",
            source="Risk",
            target="Exposure",
            weight=0.30,
            sign="negative",
            label="L1.5 | W0.30",
        ),
        CircularNetworkEdgeRecord(
            panel="2010–2020",
            source="Hazard",
            target="Risk",
            weight=0.60,
            sign="positive",
        ),
    ]


def test_nodes_follow_frozen_clockwise_unit_circle_order() -> None:
    plan = resolve_circular_network_layout(
        panel_order=("P1",),
        node_order=("North", "East", "South", "West"),
        edges=(
            CircularNetworkEdgeRecord(
                panel="P1",
                source="North",
                target="South",
                weight=1.0,
            ),
        ),
    )

    assert plan.node_order == ("North", "East", "South", "West")
    assert [(node.node, node.order_index) for node in plan.nodes] == [
        ("North", 0),
        ("East", 1),
        ("South", 2),
        ("West", 3),
    ]
    expected = ((0.0, 1.0), (1.0, 0.0), (0.0, -1.0), (-1.0, 0.0))
    for node, (expected_x, expected_y) in zip(plan.nodes, expected, strict=True):
        assert node.point.x == pytest.approx(expected_x, abs=1e-12)
        assert node.point.y == pytest.approx(expected_y, abs=1e-12)
    assert all(
        math.hypot(node.point.x, node.point.y) == pytest.approx(1.0)
        for node in plan.nodes
    )


def test_multi_panel_layout_shares_coordinates_and_global_weight_scale() -> None:
    plan = resolve_circular_network_layout(
        panel_order=("2000–2010", "2010–2020"),
        node_order=("Hazard", "Exposure", "Risk"),
        edges=_two_panel_edges(),
    )

    assert len(plan.nodes) == 3
    assert [panel.panel for panel in plan.panels] == ["2000–2010", "2010–2020"]
    assert plan.weight_scale.weight_min == pytest.approx(0.30)
    assert plan.weight_scale.weight_max == pytest.approx(0.90)
    widths = {
        (edge.panel, edge.source, edge.target): edge.line_width_pt
        for panel in plan.panels
        for edge in panel.edges
    }
    assert widths[("2000–2010", "Risk", "Exposure")] == pytest.approx(MIN_LINE_WIDTH_PT)
    assert widths[("2000–2010", "Exposure", "Risk")] == pytest.approx(MAX_LINE_WIDTH_PT)
    assert widths[("2010–2020", "Hazard", "Risk")] == pytest.approx(2.7)


def test_reciprocal_edges_use_opposite_curvature_and_separate_paths() -> None:
    plan = resolve_circular_network_layout(
        panel_order=("P1",),
        node_order=("A", "B", "C", "D"),
        edges=(
            CircularNetworkEdgeRecord(
                panel="P1",
                source="A",
                target="C",
                weight=0.5,
                sign="positive",
            ),
            CircularNetworkEdgeRecord(
                panel="P1",
                source="C",
                target="A",
                weight=0.7,
                sign="negative",
            ),
        ),
    )
    forward, reverse = plan.panels[0].edges

    assert (forward.source, forward.target) == ("A", "C")
    assert (reverse.source, reverse.target) == ("C", "A")
    assert forward.curvature == pytest.approx(-reverse.curvature)
    assert forward.label_anchor.x == pytest.approx(-reverse.label_anchor.x)
    assert forward.label_anchor.y == pytest.approx(-reverse.label_anchor.y)
    assert forward.label_anchor.to_dict() != reverse.label_anchor.to_dict()


def test_bezier_sampling_arrow_tangent_and_midpoint_label_are_renderer_ready() -> None:
    plan = resolve_circular_network_layout(
        panel_order=("P1",),
        node_order=("A", "B", "C"),
        edges=(
            {
                "panel": "P1",
                "source": "A",
                "target": "B",
                "weight": 2.0,
                "sign": "negative",
                "label": "A→B",
            },
        ),
        sample_count=17,
    )
    edge = plan.panels[0].edges[0]
    p0, _, p2, p3 = edge.control_points
    source_center = plan.nodes[0].point
    target_center = plan.nodes[1].point

    assert len(edge.sampled_points) == 17
    assert edge.sampled_points[0] == p0
    assert edge.sampled_points[-1] == p3
    assert math.hypot(p0.x - source_center.x, p0.y - source_center.y) == pytest.approx(
        plan.node_radius
    )
    assert math.hypot(p3.x - target_center.x, p3.y - target_center.y) == pytest.approx(
        plan.node_radius
    )
    assert edge.arrow_segment.end == p3
    assert edge.sampled_points[8] == edge.label_anchor
    arrow_dx = edge.arrow_segment.end.x - edge.arrow_segment.start.x
    arrow_dy = edge.arrow_segment.end.y - edge.arrow_segment.start.y
    tangent_dx = p3.x - p2.x
    tangent_dy = p3.y - p2.y
    cross_product = arrow_dx * tangent_dy - arrow_dy * tangent_dx
    dot_product = arrow_dx * tangent_dx + arrow_dy * tangent_dy
    assert cross_product == pytest.approx(0.0, abs=1e-12)
    assert dot_product > 0.0

    payload = edge.to_dict()
    assert payload["sign"] == "negative"
    assert payload["label"] == "A→B"
    assert json.loads(json.dumps(plan.to_dict(), ensure_ascii=False))["panel_order"] == ["P1"]


def test_equal_weights_use_midpoint_stroke_width() -> None:
    plan = resolve_circular_network_layout(
        panel_order=("P1",),
        node_order=("A", "B", "C"),
        edges=(
            CircularNetworkEdgeRecord(panel="P1", source="A", target="B", weight=2.0),
            CircularNetworkEdgeRecord(panel="P1", source="B", target="C", weight=2.0),
        ),
    )

    assert [edge.line_width_pt for edge in plan.panels[0].edges] == pytest.approx([2.7, 2.7])


def test_edge_label_visibility_is_frozen_at_the_per_panel_density_limit() -> None:
    nodes = tuple(f"N{index}" for index in range(5))
    candidates = [
        CircularNetworkEdgeRecord(
            panel="P1",
            source=source,
            target=target,
            weight=float(index + 1),
            label=f"E{index + 1}",
        )
        for index, (source, target) in enumerate(
            (source, target)
            for source in nodes
            for target in nodes
            if source != target
        )
    ]

    sparse = resolve_circular_network_layout(
        panel_order=("P1",),
        node_order=nodes,
        edges=candidates[:MAX_VISIBLE_EDGE_LABELS_PER_PANEL],
    )
    dense = resolve_circular_network_layout(
        panel_order=("P1",),
        node_order=nodes,
        edges=candidates[: MAX_VISIBLE_EDGE_LABELS_PER_PANEL + 1],
    )

    assert sparse.panels[0].edge_labels_visible is True
    assert dense.panels[0].edge_labels_visible is False
    assert dense.panels[0].edges[-1].label
    assert dense.to_dict()["panels"][0]["edge_labels_visible"] is False


def test_edge_row_permutation_does_not_change_the_plan() -> None:
    edges = _two_panel_edges()
    first = resolve_circular_network_layout(
        panel_order=("2000–2010", "2010–2020"),
        node_order=("Hazard", "Exposure", "Risk"),
        edges=edges,
    )
    second = resolve_circular_network_layout(
        panel_order=("2000–2010", "2010–2020"),
        node_order=("Hazard", "Exposure", "Risk"),
        edges=tuple(reversed(edges)),
    )

    assert first.to_dict() == second.to_dict()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "panel_order": (),
                "node_order": ("A", "B"),
                "edges": ({"panel": "P", "source": "A", "target": "B", "weight": 1.0},),
            },
            "panel_order must contain at least",
        ),
        (
            {
                "panel_order": ("P1", "P2", "P3", "P4", "P5"),
                "node_order": ("A", "B"),
                "edges": ({"panel": "P1", "source": "A", "target": "B", "weight": 1.0},),
            },
            "panel_order may contain at most 4",
        ),
        (
            {
                "panel_order": ("P",),
                "node_order": ("A", "A"),
                "edges": ({"panel": "P", "source": "A", "target": "A", "weight": 1.0},),
            },
            "node_order contains duplicate",
        ),
        (
            {
                "panel_order": ("P",),
                "node_order": ("A", "B"),
                "edges": ({"panel": "P", "source": "A", "target": "A", "weight": 1.0},),
            },
            "self-loop",
        ),
        (
            {
                "panel_order": ("P",),
                "node_order": ("A", "B"),
                "edges": ({"panel": "P", "source": "A", "target": "B", "weight": 0.0},),
            },
            "must be greater than zero",
        ),
        (
            {
                "panel_order": ("P",),
                "node_order": ("A", "B"),
                "edges": (
                    {
                        "panel": "P",
                        "source": "A",
                        "target": "B",
                        "weight": 1.0,
                        "sign": "up",
                    },
                ),
            },
            "sign must be one of",
        ),
    ],
)
def test_invalid_orders_and_edge_values_are_rejected(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        resolve_circular_network_layout(**kwargs)


def test_unknown_panel_node_duplicate_edge_and_short_sampling_are_rejected() -> None:
    base = {
        "panel_order": ("P",),
        "node_order": ("A", "B", "C"),
    }
    with pytest.raises(ValueError, match="absent from panel_order"):
        resolve_circular_network_layout(
            **base,
            edges=({"panel": "Other", "source": "A", "target": "B", "weight": 1.0},),
        )
    with pytest.raises(ValueError, match="absent from node_order"):
        resolve_circular_network_layout(
            **base,
            edges=({"panel": "P", "source": "A", "target": "Other", "weight": 1.0},),
        )
    with pytest.raises(ValueError, match="duplicate directed edge"):
        resolve_circular_network_layout(
            **base,
            edges=(
                {"panel": "P", "source": "A", "target": "B", "weight": 1.0},
                {"panel": "P", "source": "A", "target": "B", "weight": 2.0},
            ),
        )
    with pytest.raises(ValueError, match="sample_count must be at least"):
        resolve_circular_network_layout(
            **base,
            edges=({"panel": "P", "source": "A", "target": "B", "weight": 1.0},),
            sample_count=4,
        )
