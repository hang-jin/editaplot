from __future__ import annotations

import hashlib
import json

import pytest
from origin_sciplot.reference_style import (
    ReferenceStyleError,
    apply_reference_style,
)
from origin_sciplot.scientific_visual import resolve_adaptive_style
from origin_sciplot.scientific_workflow import (
    ScientificAxisPlan,
    ScientificDisplayPlan,
    ScientificPlotSpec,
    ScientificPreparation,
    ScientificSeries,
)


def _preparation(
    *,
    template_id: str = "xrd",
    plot_kind: str = "line_error",
) -> ScientificPreparation:
    series = (
        ScientificSeries("A", "A"),
        ScientificSeries("B", "B"),
    )
    style = resolve_adaptive_style(
        template_id=template_id,
        plot_kind=plot_kind,
        row_count=12,
        series_count=2,
    )
    spec = ScientificPlotSpec(
        plot_kind=plot_kind,
        plot_mode="default",
        x_column="X",
        category_column="Category" if "bar" in plot_kind else None,
        series=series,
        x_title="X",
        y_title="Y",
        y2_title=None,
        x_scale="linear",
        y_scale="linear",
        display_transform="identity",
        display_plan=ScientificDisplayPlan(
            marker_size_pt=6.0,
            bar_group_span=0.8,
            bar_inner_width=0.72,
            figure_style=style,
        ),
        axis_plan=ScientificAxisPlan(
            x_from=0.0,
            x_to=10.0,
            x_step=2.0,
            y_from=0.0,
            y_to=10.0,
            y_step=2.0,
        ),
    )
    return ScientificPreparation(
        template_id=template_id,
        source_path="source.csv",
        source_sha256="a" * 64,
        source_size_bytes=10,
        source_format="csv",
        source_sheet=None,
        source_columns=("X", "A", "B"),
        row_count=12,
        ignored_empty_rows=0,
        assignments=(("X", "x"), ("A", "series"), ("B", "series")),
        plot_spec=spec,
        confidence=1.0,
        requires_confirmation=False,
        confirmation_reasons=(),
        warnings=(),
        mapping_confirmed=True,
        plan_digest="b" * 64,
    )


def _adaptation(
    *,
    template_id: str = "xrd",
    route: str = "template_adaptation",
    panel_count: int = 1,
    **style_overrides: object,
) -> dict[str, object]:
    style = {
        "palette_family": None,
        "palette_id": "blue_coral",
        "line_weight": "heavy",
        "marker_density": "sparse",
        "fill_transparency": "light",
        "legend_position": "inside",
        "legend_frame": False,
        "grid": "none",
        "background": "white",
        "typography_hierarchy": "publication_informed",
    }
    style.update(style_overrides)
    payload: dict[str, object] = {
        "plan_version": "1.0",
        "route": route,
        "template_id": template_id if route == "template_adaptation" else None,
        "layout": {
            "archetype": "single_chart" if panel_count == 1 else "quantitative_grid",
            "aspect_ratio_class": "wide",
            "panels": [{"id": f"panel_{index}"} for index in range(panel_count)],
        },
        "style_tokens": style,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    payload["plan_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def _entries(report: dict[str, object], section: str) -> dict[str, dict[str, object]]:
    return {
        str(item["token"]): item
        for item in report[section]  # type: ignore[index]
    }


def test_reference_style_applies_shared_tokens_without_changing_series() -> None:
    preparation = _preparation()
    application = apply_reference_style(preparation, _adaptation())
    style = application.preparation.plot_spec.display_plan.figure_style

    assert style is not None
    assert style.palette_name == "blue_coral"
    assert style.plot_line_width_pt > 2.6
    assert application.preparation.plot_spec.display_plan.marker_size_pt < 6.0
    assert application.preparation.plot_spec.series == preparation.plot_spec.series
    assert application.preparation.source_columns == preparation.source_columns
    applied = _entries(application.report, "applied")
    assert {
        "palette_id",
        "line_weight",
        "marker_density",
        "legend_frame",
    }.issubset(applied)
    assert applied["marker_density"]["implementation"] == "no_sampling_no_point_deletion"
    assert application.report["safety"]["marker_points_sampled_or_removed"] == 0
    assert application.report["execution_allowed"] is True
    assert len(application.report["report_hash"]) == 64


def test_marker_none_is_rejected_and_never_hides_required_points() -> None:
    preparation = _preparation()
    application = apply_reference_style(
        preparation,
        _adaptation(marker_density="none", palette_id=None),
    )

    assert application.preparation.plot_spec.display_plan.marker_size_pt == 6.0
    rejected = _entries(application.report, "rejected")
    assert rejected["marker_density"]["reason"] == "marker_hiding_forbidden"
    assert rejected["marker_density"]["implementation"] == "all_source_points_retained"
    assert application.report["safety"]["series_visibility_changed"] is False


def test_fill_transparency_is_shared_for_verified_fill_templates() -> None:
    preparation = _preparation(template_id="bar", plot_kind="bar_error")
    application = apply_reference_style(
        preparation,
        _adaptation(
            template_id="bar",
            palette_id=None,
            marker_density="adaptive",
            fill_transparency="heavy",
        ),
    )
    style = application.preparation.plot_spec.display_plan.figure_style

    assert style is not None
    assert style.fill_transparency_percent == 55.0
    assert (
        _entries(application.report, "applied")["fill_transparency"]["implementation"]
        == "shared_preview_origin_percent_transparency"
    )


def test_unverified_cosmetics_are_rejected_and_template_defaults_survive() -> None:
    preparation = _preparation()
    original_style = preparation.plot_spec.display_plan.figure_style
    application = apply_reference_style(
        preparation,
        _adaptation(
            palette_id=None,
            line_weight="adaptive",
            marker_density="adaptive",
            legend_position="outside_right",
            legend_frame=True,
            grid="major_only",
            background="black",
            typography_hierarchy="dense",
        ),
    )
    rejected = _entries(application.report, "rejected")

    assert {
        "legend_position",
        "legend_frame",
        "grid",
        "background",
        "typography_hierarchy",
    }.issubset(rejected)
    assert application.preparation.plot_spec.display_plan.figure_style == original_style
    assert application.report["execution_allowed"] is True


def test_multi_panel_and_controlled_composition_remain_blocked() -> None:
    preparation = _preparation()
    multi = apply_reference_style(preparation, _adaptation(panel_count=2))
    controlled = apply_reference_style(
        preparation,
        _adaptation(route="controlled_composition"),
    )

    assert multi.report["execution_allowed"] is False
    assert "reference_layout_renderer_not_verified" in multi.report["blocking_reasons"]
    assert controlled.report["execution_allowed"] is False
    assert "reference_controlled_composition_renderer_not_verified" in controlled.report["blocking_reasons"]


def test_locked_user_palette_has_precedence_over_reference_palette() -> None:
    preparation = _preparation()
    application = apply_reference_style(
        preparation,
        _adaptation(),
        locked_palette_id="navy_ember",
    )

    rejected = _entries(application.report, "rejected")
    assert rejected["palette_id"]["reason"] == "explicit_user_palette_has_precedence"
    assert rejected["palette_id"]["resolved"] == "navy_ember"


def test_tampered_reference_style_plan_is_rejected() -> None:
    adaptation = _adaptation()
    adaptation["style_tokens"] = {
        **adaptation["style_tokens"],  # type: ignore[dict-item]
        "line_weight": "light",
    }

    with pytest.raises(ReferenceStyleError) as caught:
        apply_reference_style(_preparation(), adaptation)

    assert caught.value.code == "reference_style_plan_hash_mismatch"


def test_xps_rejects_reference_style_even_with_a_scientific_shape() -> None:
    preparation = _preparation(template_id="xps")

    with pytest.raises(ReferenceStyleError) as caught:
        apply_reference_style(
            preparation,
            _adaptation(template_id="xps"),
        )

    assert caught.value.code == "reference_style_xps_unsupported"


def test_output_digest_is_stable_for_the_same_reference_style() -> None:
    preparation = _preparation()
    first = apply_reference_style(preparation, _adaptation())
    second = apply_reference_style(preparation, _adaptation())

    assert first.preparation.plan_digest == second.preparation.plan_digest
    assert first.report == second.report


def test_template_mismatch_is_rejected() -> None:
    with pytest.raises(ReferenceStyleError) as caught:
        apply_reference_style(
            _preparation(),
            _adaptation(template_id="bar"),
        )

    assert caught.value.code == "reference_style_template_mismatch"
