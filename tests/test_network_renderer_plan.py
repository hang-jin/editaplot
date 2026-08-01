from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SRC = ROOT / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.circular_network_layout import NETWORK_NODE_GROUP_COLORS  # noqa: E402
from origin_sciplot.origin_backend.network_renderer import (  # noqa: E402
    _compact_plot_spec,
    _network_helper_table,
    _network_layer_geometries,
    _node_group_colors,
)
from origin_sciplot.scientific_workflow import (  # noqa: E402
    load_scientific_frame,
    prepare_scientific,
)


def test_network_helper_columns_preserve_source_and_frozen_geometry() -> None:
    source = ROOT / "examples" / "gallery" / "circular_network.csv"
    preparation = prepare_scientific(source, "circular_network")
    frame = load_scientific_frame(source, preparation)
    snapshot = frame.copy(deep=True)

    table = _network_helper_table(frame, preparation)

    pd.testing.assert_frame_equal(frame, snapshot, check_exact=True)
    assert table.source_frame_unchanged is True
    assert len(table.edge_columns) == 22
    assert len(table.node_columns) == 4
    assert table.helper_frame.shape == (33, 52)
    assert all(column.startswith("__") for column in table.helper_frame)
    first = table.edge_columns[0]
    assert table.helper_frame[first.x_column].iloc[0] == pytest.approx(
        first.edge.sampled_points[0].x
    )
    assert table.helper_frame[first.y_column].iloc[-1] == pytest.approx(
        first.edge.sampled_points[-1].y
    )
    compact = _compact_plot_spec(preparation)
    assert compact["network_layout"]["edge_counts"] == {
        "Period 1 (2000-2010)": 11,
        "Period 2 (2010-2020)": 11,
    }
    assert compact["network_layout"]["edge_labels_visible"] == {
        "Period 1 (2000-2010)": True,
        "Period 2 (2010-2020)": True,
    }
    assert "sampled_points" not in str(compact["network_layout"])
    assert _node_group_colors(
        preparation,
        preparation.plot_spec.group_order,
    ) == dict(zip(preparation.plot_spec.group_order, NETWORK_NODE_GROUP_COLORS, strict=True))


@pytest.mark.parametrize("panel_count", [1, 2, 3, 4])
def test_network_panel_and_legend_layers_are_bounded_and_non_overlapping(
    panel_count: int,
) -> None:
    panels, legend = _network_layer_geometries(panel_count)

    assert len(panels) == panel_count
    assert legend.top >= max(panel.top + panel.height for panel in panels)
    for layer in (*panels, legend):
        assert 0.0 <= layer.left < 100.0
        assert 0.0 <= layer.top < 100.0
        assert layer.width > 0.0
        assert layer.height > 0.0
        assert layer.left + layer.width <= 100.0
        assert layer.top + layer.height <= 100.0
