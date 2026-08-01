from __future__ import annotations

import csv
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.scientific_workflow import (  # noqa: E402
    ScientificColumnMapping,
    ScientificWorkflowError,
    prepare_scientific,
    role_options,
)
from origin_sciplot.semantic_analysis import propose_prepared_semantics  # noqa: E402

EXAMPLE = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "gallery"
    / "circular_network.csv"
)


def _write_rows(path: Path, rows: list[dict[str, object]]) -> Path:
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _basic_rows() -> list[dict[str, object]]:
    return [
        {
            "Panel": "Period A",
            "Source": "Acquisition",
            "Target": "Evidence",
            "Weight": 0.8,
            "Sign": "positive",
            "SourceGroup": "Input",
            "TargetGroup": "Evidence",
            "EdgeLabel": "reported +0.80",
        },
        {
            "Panel": "Period A",
            "Source": "Evidence",
            "Target": "Decision",
            "Weight": 0.5,
            "Sign": "negative",
            "SourceGroup": "Evidence",
            "TargetGroup": "Decision",
            "EdgeLabel": "reported −0.50",
        },
    ]


def _assert_error(code: str, operation) -> ScientificWorkflowError:
    with pytest.raises(ScientificWorkflowError) as caught:
        operation()
    assert caught.value.code == code
    return caught.value


def test_public_example_freezes_network_roles_geometry_and_adaptive_style() -> None:
    before = EXAMPLE.read_bytes()

    preparation = prepare_scientific(EXAMPLE, "circular_network")

    assert EXAMPLE.read_bytes() == before
    assert preparation.confidence == pytest.approx(0.98)
    assert preparation.requires_confirmation is False
    assert dict(preparation.assignments) == {
        "Panel": "panel",
        "Source": "source",
        "Target": "target",
        "Weight": "value",
        "Sign": "sign",
        "SourceGroup": "source_group",
        "TargetGroup": "target_group",
        "EdgeLabel": "edge_label",
    }
    spec = preparation.plot_spec
    assert spec.plot_kind == "circular_network"
    assert spec.plot_mode == "temporal_directed_weighted"
    assert spec.panel_column == "Panel"
    assert spec.source_column == "Source"
    assert spec.target_column == "Target"
    assert spec.weight_column == "Weight"
    assert spec.sign_column == "Sign"
    assert spec.edge_label_column == "EdgeLabel"
    assert spec.network_layout is not None
    assert spec.network_layout.panel_order == (
        "Period 1 (2000-2010)",
        "Period 2 (2010-2020)",
    )
    assert spec.network_layout.node_order[:4] == (
        "Acquisition",
        "Signal",
        "Quality",
        "Context",
    )
    assert spec.node_groups[:3] == (
        ("Acquisition", "Inputs"),
        ("Signal", "Evidence"),
        ("Quality", "Evidence"),
    )
    first_edge = spec.network_layout.panels[0].edges[0]
    assert first_edge.label == "+0.82"
    assert first_edge.sign == "positive"
    assert all(panel.edge_labels_visible for panel in spec.network_layout.panels)
    style = spec.display_plan.figure_style
    assert style is not None
    assert style.profile_name == "adaptive-circular_network-circular_network"
    assert style.page_width_cm > 35.0
    assert style.axis_title_size_pt == 20.0
    assert style.tick_label_size_pt == 17.0
    assert style.legend_size_pt == 17.0
    assert style.palette_name == "network_nodes"


def test_role_options_expose_required_and_optional_network_columns() -> None:
    options = {key: unique for key, _label, unique in role_options("circular_network")}

    assert set(options) == {
        "panel",
        "source",
        "target",
        "value",
        "sign",
        "source_group",
        "target_group",
        "edge_label",
        "ignored",
    }
    assert all(options[role] for role in set(options) - {"ignored"})


def test_chinese_headers_and_sign_tokens_are_recognized(tmp_path: Path) -> None:
    source = _write_rows(
        tmp_path / "network_zh.csv",
        [
            {
                "时段": "早期",
                "源节点": "采集",
                "目标节点": "证据",
                "权重": 1.2,
                "方向": "正相关",
                "来源组": "输入",
                "目标组": "证据",
                "边标签": "原文甲",
            },
            {
                "时段": "早期",
                "源节点": "证据",
                "目标节点": "决策",
                "权重": 0.7,
                "方向": "p<0",
                "来源组": "证据",
                "目标组": "决策",
                "边标签": "原文乙",
            },
            {
                "时段": "晚期",
                "源节点": "采集",
                "目标节点": "决策",
                "权重": 0.4,
                "方向": "中性",
                "来源组": "输入",
                "目标组": "决策",
                "边标签": "原文丙",
            },
        ],
    )

    preparation = prepare_scientific(source, "circular_network")

    assert preparation.requires_confirmation is False
    layout = preparation.plot_spec.network_layout
    assert layout is not None
    assert [edge.sign for panel in layout.panels for edge in panel.edges] == [
        "positive",
        "negative",
        "neutral",
    ]
    assert [edge.label for panel in layout.panels for edge in panel.edges] == [
        "原文甲",
        "原文乙",
        "原文丙",
    ]


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (
            lambda rows: rows.__setitem__(
                1,
                {**rows[1], "Source": "Evidence", "Target": "Evidence"},
            ),
            "circular_network_self_link",
        ),
        (
            lambda rows: rows.__setitem__(
                1,
                {
                    **rows[1],
                    "Source": "Acquisition",
                    "Target": "Evidence",
                    "SourceGroup": "Input",
                    "TargetGroup": "Evidence",
                },
            ),
            "circular_network_duplicate_edge",
        ),
        (
            lambda rows: rows.__setitem__(0, {**rows[0], "Weight": 0}),
            "circular_network_weight_invalid",
        ),
        (
            lambda rows: rows.__setitem__(0, {**rows[0], "Sign": "maybe"}),
            "circular_network_sign_unknown",
        ),
        (
            lambda rows: rows.__setitem__(
                1,
                {**rows[1], "SourceGroup": "Other evidence"},
            ),
            "circular_network_node_group_conflict",
        ),
    ],
)
def test_invalid_network_rows_are_hard_failures(
    tmp_path: Path,
    mutator,
    code: str,
) -> None:
    rows = _basic_rows()
    mutator(rows)
    source = _write_rows(tmp_path / f"{code}.csv", rows)

    _assert_error(code, lambda: prepare_scientific(source, "circular_network"))


def test_group_columns_must_be_mapped_as_a_pair(tmp_path: Path) -> None:
    rows = [
        {
            "Panel": "A",
            "Source": "N1",
            "Target": "N2",
            "Weight": 1.0,
            "SourceGroup": "Input",
        }
    ]
    source = _write_rows(tmp_path / "group_pair.csv", rows)

    _assert_error(
        "circular_network_group_pair_incomplete",
        lambda: prepare_scientific(source, "circular_network"),
    )


def test_network_limits_are_enforced(tmp_path: Path) -> None:
    five_panels = [
        {"Panel": f"P{index}", "Source": "A", "Target": "B", "Weight": 1.0}
        for index in range(5)
    ]
    source = _write_rows(tmp_path / "five_panels.csv", five_panels)
    _assert_error(
        "circular_network_panel_count",
        lambda: prepare_scientific(source, "circular_network"),
    )

    nodes = [
        {"Panel": "P", "Source": f"N{index}", "Target": f"N{index + 1}", "Weight": 1.0}
        for index in range(24)
    ]
    source = _write_rows(tmp_path / "many_nodes.csv", nodes)
    _assert_error(
        "circular_network_node_count",
        lambda: prepare_scientific(source, "circular_network"),
    )

    five_groups = [
        {
            "Panel": "P",
            "Source": f"N{index}",
            "Target": f"N{index + 1}",
            "Weight": 1.0,
            "SourceGroup": f"G{index}",
            "TargetGroup": f"G{index + 1}",
        }
        for index in range(4)
    ]
    source = _write_rows(tmp_path / "five_groups.csv", five_groups)
    _assert_error(
        "circular_network_node_group_count",
        lambda: prepare_scientific(source, "circular_network"),
    )

    edges: list[dict[str, object]] = []
    for source_index in range(9):
        for target_index in range(9):
            if source_index == target_index:
                continue
            edges.append(
                {
                    "Panel": "P",
                    "Source": f"N{source_index}",
                    "Target": f"N{target_index}",
                    "Weight": 1.0,
                }
            )
            if len(edges) == 61:
                break
        if len(edges) == 61:
            break
    source = _write_rows(tmp_path / "many_edges.csv", edges)
    _assert_error(
        "circular_network_edge_count",
        lambda: prepare_scientific(source, "circular_network"),
    )


def test_dense_panel_hides_edge_labels_without_dropping_source_values(
    tmp_path: Path,
) -> None:
    nodes = tuple(f"N{index}" for index in range(5))
    pairs = [(source, target) for source in nodes for target in nodes if source != target]
    rows = [
        {
            "Panel": "Dense",
            "Source": source,
            "Target": target,
            "Weight": float(index + 1),
            "EdgeLabel": f"original-label-{index + 1}",
        }
        for index, (source, target) in enumerate(pairs[:13])
    ]
    source = _write_rows(tmp_path / "dense_labels.csv", rows)
    before = source.read_bytes()

    preparation = prepare_scientific(source, "circular_network")

    assert source.read_bytes() == before
    layout = preparation.plot_spec.network_layout
    assert layout is not None
    assert layout.panels[0].edge_labels_visible is False
    assert [edge.label for edge in layout.panels[0].edges] == [
        str(row["EdgeLabel"]) for row in rows
    ]
    assert "circular_network_edge_labels_hidden_dense" in preparation.warnings


def test_manual_mapping_can_confirm_synonymous_headers(tmp_path: Path) -> None:
    source = _write_rows(
        tmp_path / "synonyms.csv",
        [
            {
                "Window name": "A",
                "From node": "N1",
                "To node": "N2",
                "Magnitude": 1.0,
                "Comment": "keep but do not render",
            }
        ],
    )
    mapping = ScientificColumnMapping(
        assignments=(
            ("Window name", "panel"),
            ("From node", "source"),
            ("To node", "target"),
            ("Magnitude", "value"),
            ("Comment", "ignored"),
        )
    )

    preparation = prepare_scientific(
        source,
        "circular_network",
        column_mapping=mapping,
    )

    assert preparation.mapping_confirmed is True
    assert preparation.confidence == 1.0
    assert preparation.plot_spec.network_layout is not None
    assert preparation.plot_spec.network_layout.panel_order == ("A",)


def test_semantic_bridge_emits_one_complete_network_element() -> None:
    preparation = prepare_scientific(EXAMPLE, "circular_network")
    wrapped = SimpleNamespace(
        template_id="circular_network",
        source_columns=preparation.source_columns,
        confidence=preparation.confidence,
        requires_confirmation=preparation.requires_confirmation,
        confirmation_reasons=preparation.confirmation_reasons,
        payload=preparation,
    )

    proposal = propose_prepared_semantics(wrapped)

    dispositions = {
        item.source_column: item.disposition.value
        for item in proposal.data_items
    }
    for column in ("Panel", "Source", "Target", "Weight"):
        assert dispositions[column] == "render_primary"
    for column in ("Sign", "SourceGroup", "TargetGroup", "EdgeLabel"):
        assert dispositions[column] == "render_secondary"
    assert len(proposal.figure_elements) == 1
    element = proposal.figure_elements[0]
    assert element.element_kind == "directed_weighted_network"
    assert element.axis == "network"
    assert len(element.data_item_ids) == 8
    proposal.confirm(user_confirmed=True)
