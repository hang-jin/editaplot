from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "runtime/src"), str(ROOT / "skill/editaplot/scripts")]

from editaplot_core import build_plan, understand_data  # noqa: E402
from origin_sciplot.scientific_workflow import (  # noqa: E402
    ScientificColumnMapping,
    ScientificWorkflowError,
    prepare_scientific,
)
from origin_sciplot.shap_dashboard import (  # noqa: E402
    DASHBOARD_PALETTES,
    build_dashboard_plan,
    dashboard_regions,
)

SOURCE = ROOT / "examples/gallery/shap_dashboard.csv"


def test_dashboard_preserves_all_source_values_and_links_ring_denominators():
    before = SOURCE.read_bytes()
    p = prepare_scientific(SOURCE, "shap_dashboard")
    base, dashboard = p.plot_spec.shap_plan, p.plot_spec.shap_dashboard
    assert p.row_count == 1440
    assert len(base.feature_order) == 12
    assert dashboard.ring_feature_order != base.feature_order
    assert set(dashboard.ring_feature_order) == set(base.feature_order)
    assert sum(v for _, v in dashboard.feature_percentages) == pytest.approx(100)
    assert sum(v for _, v in dashboard.ring_group_percentages) == pytest.approx(100)
    groups = dict(base.feature_groups)
    for group, share in dashboard.ring_group_percentages:
        assert share == pytest.approx(sum(v for f, v in dashboard.feature_percentages if groups[f] == group))
    assert SOURCE.read_bytes() == before


@pytest.mark.parametrize("palette", list(DASHBOARD_PALETTES))
def test_palette_is_source_bound_and_has_exact_endpoints(palette):
    p = prepare_scientific(SOURCE, "shap_dashboard")
    mapping = ScientificColumnMapping(p.assignments, f"dashboard_{palette}")
    changed = prepare_scientific(SOURCE, "shap_dashboard", column_mapping=mapping)
    colors = changed.plot_spec.shap_dashboard.palette_colors
    assert len(colors) == 101
    assert colors[0] == DASHBOARD_PALETTES[palette][0]
    assert colors[-1] == DASHBOARD_PALETTES[palette][-1]
    if palette != "blue_red":
        assert changed.plan_digest != p.plan_digest


def test_missing_group_is_not_invented(tmp_path):
    import pandas as pd

    frame = pd.read_csv(SOURCE).drop(columns="Feature Group")
    source = tmp_path / "missing_group.csv"
    frame.to_csv(source, index=False)
    with pytest.raises(ScientificWorkflowError, match="Feature Group"):
        prepare_scientific(source, "shap_dashboard")


def test_dashboard_percentages_require_explicit_semantic_approval():
    understanding = understand_data(SOURCE, template_id="shap_dashboard", engine_home=ROOT / "runtime")
    confirmation = understanding["confirmation_gate"]["confirmation_payload_template"]
    assert "derived_shap_dashboard_feature_fractions" in confirmation["approved_derived_item_ids"]
    plan = build_plan(
        SOURCE,
        template_id="shap_dashboard",
        claim="Synthetic features differ in contribution.",
        evidence_role="interpretability",
        semantic_confirmation=confirmation,
        engine_home=ROOT / "runtime",
    )
    assert plan["can_render"] is True
    without_fraction = {
        **confirmation,
        "approved_derived_item_ids": [
            x
            for x in confirmation["approved_derived_item_ids"]
            if x != "derived_shap_dashboard_feature_fractions"
        ],
    }
    with pytest.raises(Exception, match="approv"):
        build_plan(
            SOURCE,
            template_id="shap_dashboard",
            claim="Synthetic features differ in contribution.",
            evidence_role="interpretability",
            semantic_confirmation=without_fraction,
            engine_home=ROOT / "runtime",
        )


def test_existing_shap_plan_digest_remains_compatible():
    current = prepare_scientific(ROOT / "examples/gallery/medical_shap_summary.csv", "shap_summary")
    assert current.plot_spec.shap_dashboard is None
    # Published pre-dashboard plan for this immutable public teaching fixture.
    assert current.plan_digest == "514b394faa9b89b807144df8eb3252457577ddf974c1dddeed8098e5346d2d1d"


def test_layout_aligns_feature_rows_and_separates_colorbar():
    r = dashboard_regions()
    assert r["importance"].top_percent == r["beeswarm"].top_percent
    assert r["importance"].height_percent == r["beeswarm"].height_percent
    assert r["importance"].left_percent + r["importance"].width_percent < r["beeswarm"].left_percent
    assert r["beeswarm"].left_percent + r["beeswarm"].width_percent < r["colorbar"].left_percent


def test_inset_requires_a_real_empty_rectangle_beside_short_bars():
    p = prepare_scientific(SOURCE, "shap_dashboard").plot_spec
    assert p.shap_dashboard.contribution_layout == "inset"
    r = dashboard_regions(p.shap_dashboard)
    assert r["rings"].top_percent < r["importance"].top_percent + r["importance"].height_percent
    equal = replace(p.shap_plan, mean_abs_values=tuple((f, 1.0) for f in p.category_order))
    reserved = build_dashboard_plan(equal, "blue_red")
    assert reserved.contribution_layout == "reserved"
    r = dashboard_regions(reserved)
    assert r["rings"].top_percent > r["importance"].top_percent + r["importance"].height_percent


def test_summary_rejects_zero_total():
    p = prepare_scientific(SOURCE, "shap_dashboard").plot_spec.shap_plan
    zero = replace(p, mean_abs_values=tuple((f, 0.0) for f in p.feature_order))
    with pytest.raises(ValueError, match="positive"):
        build_dashboard_plan(zero, "blue_red")


def test_preview_retains_every_observation_and_both_rings():
    from origin_sciplot.scientific_preview import _build_scientific_preview_figure

    p = prepare_scientific(SOURCE, "shap_dashboard")
    figure = _build_scientific_preview_figure(p)
    axes = {a.get_label(): a for a in figure.axes}
    points = np.concatenate([c.get_offsets()[:, 0] for c in axes["dashboard_beeswarm"].collections])
    import pandas as pd

    original = pd.read_csv(SOURCE)["SHAP value"].to_numpy()
    assert np.array_equal(points, original)
    assert len(axes["dashboard_rings"].patches) == 17
