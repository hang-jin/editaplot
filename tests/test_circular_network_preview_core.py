from __future__ import annotations

import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest
from matplotlib.colors import to_hex
from matplotlib.patches import FancyArrowPatch, PathPatch

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME = PRODUCT_ROOT / "runtime"
SCRIPTS = PRODUCT_ROOT / "skill" / "editaplot" / "scripts"
SOURCE = RUNTIME / "templates" / "circular_network" / "example_standard.csv"

sys.path.insert(0, str(RUNTIME / "src"))
sys.path.insert(0, str(SCRIPTS))

import editaplot_core as core  # noqa: E402
from origin_sciplot.circular_network_layout import (  # noqa: E402
    NETWORK_EDGE_TRANSPARENCY_PERCENT,
    NETWORK_NODE_GROUP_COLORS,
)
from origin_sciplot.scientific_preview import (  # noqa: E402
    _build_scientific_preview_figure,
    render_scientific_preview_png,
)
from origin_sciplot.scientific_workflow import prepare_scientific  # noqa: E402


def test_inspection_distinguishes_temporal_network_from_plain_sankey() -> None:
    result = core.inspect_data(SOURCE, engine_home=RUNTIME)

    assert "edge_list" in result["table"]["layouts"]
    assert "temporal_edge_list" in result["table"]["layouts"]
    assert result["domain_signals"]["circular_network"] == 4
    tags = {
        tag
        for profile in result["columns"]
        for tag in profile["semantic_tags"]
    }
    assert {
        "panel",
        "source",
        "target",
        "value",
        "sign",
        "source_group",
        "target_group",
        "edge_label",
    }.issubset(tags)
    profiles = {profile["name"]: profile["semantic_tags"] for profile in result["columns"]}
    assert "source" not in profiles["SourceGroup"]
    assert "target" not in profiles["TargetGroup"]
    assert "category" not in profiles["EdgeLabel"]


def test_temporal_network_scoring_prefers_circular_route_over_sankey() -> None:
    inspection = core.inspect_data(SOURCE, engine_home=RUNTIME)
    prepared = types.SimpleNamespace(
        confidence=0.98,
        requires_confirmation=False,
    )

    network_score, network_codes, _ = core._score_candidate(
        "circular_network",
        prepared,
        inspection,
        "",
    )
    sankey_score, sankey_codes, _ = core._score_candidate(
        "sankey",
        prepared,
        inspection,
        "",
    )

    assert network_score > sankey_score
    assert "temporal_directed_edge_list_match" in network_codes
    assert "temporal_network_route_preferred" in sankey_codes


def test_preview_uses_shared_layout_and_keeps_legend_outside_panels() -> None:
    preparation = prepare_scientific(SOURCE, "circular_network")
    figure = _build_scientific_preview_figure(preparation)
    layout = preparation.plot_spec.network_layout

    assert layout is not None
    assert len(figure.axes) == len(layout.panels) == 2
    assert [axis.get_title() for axis in figure.axes] == list(layout.panel_order)
    assert all(not axis.axison for axis in figure.axes)
    assert all(
        any(isinstance(patch, FancyArrowPatch) for patch in axis.patches)
        for axis in figure.axes
    )
    assert all(
        any(isinstance(patch, PathPatch) for patch in axis.patches)
        for axis in figure.axes
    )
    first_node_offsets = [
        tuple(axis.collections[0].get_offsets()[0])
        for axis in figure.axes
    ]
    assert len(set(first_node_offsets)) == 1
    expected_group_colors = {color.casefold() for color in NETWORK_NODE_GROUP_COLORS}
    for axis in figure.axes:
        actual_group_colors = {
            to_hex(collection.get_facecolors()[0]).casefold()
            for collection in axis.collections
        }
        assert actual_group_colors == expected_group_colors
        edge_alphas = {
            patch.get_alpha()
            for patch in axis.patches
            if isinstance(patch, (FancyArrowPatch, PathPatch))
        }
        assert len(edge_alphas) == 1
        assert next(iter(edge_alphas)) == pytest.approx(
            1.0 - NETWORK_EDGE_TRANSPARENCY_PERCENT / 100.0
        )
    assert any(text.get_text() == "+0.82" for text in figure.axes[0].texts)
    assert len(figure.legends) == 1
    assert figure.legends[0].get_frame_on() is False
    assert figure.legends[0].get_bbox_to_anchor().y0 < (
        figure.axes[0].get_position().y0 * figure.bbox.height
    )


def test_preview_respects_the_frozen_edge_label_visibility_decision() -> None:
    preparation = prepare_scientific(SOURCE, "circular_network")
    layout = preparation.plot_spec.network_layout
    assert layout is not None
    hidden_first_panel = replace(layout.panels[0], edge_labels_visible=False)
    hidden_layout = replace(
        layout,
        panels=(hidden_first_panel, *layout.panels[1:]),
    )
    hidden_spec = replace(preparation.plot_spec, network_layout=hidden_layout)
    hidden_preparation = replace(preparation, plot_spec=hidden_spec)

    figure = _build_scientific_preview_figure(hidden_preparation)

    assert not any(text.get_text() == "+0.82" for text in figure.axes[0].texts)
    assert any(text.get_text() == "+0.69" for text in figure.axes[1].texts)


def test_circular_network_preview_png_is_nonempty() -> None:
    preparation = prepare_scientific(SOURCE, "circular_network")
    png = render_scientific_preview_png(preparation)

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 50_000
