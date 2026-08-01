from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SRC = ROOT / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.palette_catalog import get_palette  # noqa: E402
from origin_sciplot.reference_style import apply_reference_style  # noqa: E402
from origin_sciplot.xps_visual_style import (  # noqa: E402
    XpsVisualStyleError,
    apply_xps_visual_style,
    normalize_xps_visual_tokens,
)
from origin_sciplot.xps_workflow import (  # noqa: E402
    XpsColumnMapping,
    XpsPreparation,
    prepare_xps,
    replace_xps_visual_contract,
)

FIXED_SOURCE = ROOT / "runtime" / "templates" / "xps_c1s_fit" / "example_standard.csv"
ADAPTIVE_SOURCE = ROOT / "runtime" / "templates" / "xps_adaptive" / "example_standard.csv"
XPS_RUNNERS = (
    ROOT / "runtime" / "templates" / "xps_c1s_fit" / "runner.py",
    ROOT / "runtime" / "templates" / "xps_adaptive" / "runner.py",
)


def _scientific_snapshot(preparation: XpsPreparation) -> tuple[object, ...]:
    """Fields a visual request is never allowed to change."""

    return (
        preparation.source_path,
        preparation.source_sha256,
        preparation.source_size_bytes,
        preparation.source_format,
        preparation.source_sheet,
        preparation.source_delimiter,
        preparation.source_columns,
        preparation.row_count,
        preparation.ignored_empty_rows,
        preparation.detection,
        preparation.roles,
        preparation.component_basis,
        preparation.plot_spec,
        preparation.warnings,
        preparation.confidence,
        preparation.column_mapping,
        preparation.mapping_confirmed,
        preparation.requires_confirmation,
        preparation.confirmation_reasons,
    )


def _reference_adaptation(**style_overrides: object) -> dict[str, object]:
    style: dict[str, object] = {
        "palette_family": None,
        "palette_id": "deep_sea_gold",
        "line_weight": "heavy",
        "marker_density": "adaptive",
        "fill_transparency": "heavy",
        "legend_position": "none",
        "legend_frame": True,
        "grid": "none",
        "background": "white",
        "typography_hierarchy": "publication_informed",
    }
    style.update(style_overrides)
    payload: dict[str, object] = {
        "plan_version": "1.0",
        "route": "template_adaptation",
        "template_id": "xps",
        "layout": {
            "archetype": "single_chart",
            "aspect_ratio_class": "square",
            "panels": [{"id": "main"}],
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


def test_exact_style_changes_only_visual_contract_and_has_stable_digest() -> None:
    preparation = prepare_xps(ADAPTIVE_SOURCE)
    before = _scientific_snapshot(preparation)
    request = {
        "series_colors": {
            "raw": "#123456",
            preparation.roles.envelope: "#A23B72",
            preparation.roles.components[0]: "#2A9D8F",
        },
        "line_width_pt": 2.35,
        "fill_transparency_percent": 37.5,
        "page_size_cm": {"width": 18.0, "height": 18.0},
        "legend_visible": False,
        "legend_frame": False,
    }

    first = apply_xps_visual_style(preparation, request, source="explicit_user")
    repeated_from_base = apply_xps_visual_style(
        preparation,
        request,
        source="explicit_user",
    )
    repeated_from_styled = apply_xps_visual_style(
        first.preparation,
        request,
        source="explicit_user",
    )

    assert _scientific_snapshot(first.preparation) == before
    assert first.preparation.plan_digest != preparation.plan_digest
    assert first.preparation.plan_digest == repeated_from_base.preparation.plan_digest
    assert first.report == repeated_from_base.report
    assert repeated_from_styled.preparation.plan_digest == first.preparation.plan_digest
    assert first.report["safety"] == {
        "style_only": True,
        "source_values_changed": False,
        "scientific_elements_changed": False,
        "series_visibility_changed": False,
        "source_columns_changed": False,
        "unverified_origin_parameter_added": False,
        "xps_fill_mode": "pfm3_two_colors",
    }


def test_empty_style_and_identity_replacement_keep_the_original_digest() -> None:
    preparation = prepare_xps(ADAPTIVE_SOURCE)

    empty = apply_xps_visual_style(preparation, {}, source="explicit_user")
    identity = replace_xps_visual_contract(preparation, preparation.visual_contract)

    assert empty.preparation == preparation
    assert empty.preparation.plan_digest == preparation.plan_digest
    assert empty.report["input_plan_digest"] == preparation.plan_digest
    assert empty.report["output_plan_digest"] == preparation.plan_digest
    assert identity.plan_digest == preparation.plan_digest


def test_exact_user_values_lock_equivalent_coarse_reference_tokens() -> None:
    preparation = prepare_xps(ADAPTIVE_SOURCE)
    explicit = {
        "series_colors": {"raw": "#123456"},
        "line_width_pt": 2.2,
        "fill_transparency_percent": 36.0,
        "page_size_cm": {"width": 18.0, "height": 18.0},
        "legend_visible": True,
        "legend_frame": False,
    }
    explicitly_styled = apply_xps_visual_style(
        preparation,
        explicit,
        source="explicit_user",
    ).preparation

    application = apply_reference_style(
        explicitly_styled,
        _reference_adaptation(),
        locked_style_tokens=explicit,
    )
    style = application.preparation.visual_contract
    rejected = _entries(application.report, "rejected")

    assert style.figure_style.plot_line_width_pt == 2.2
    assert style.figure_style.fill_transparency_percent == 36.0
    assert style.figure_style.page_width_cm == 18.0
    assert style.figure_style.page_height_cm == 18.0
    base_style = preparation.visual_contract.figure_style
    assert (
        style.figure_style.page_width_cm
        * style.figure_style.layer_left_percent
        / 100.0
    ) == pytest.approx(
        base_style.page_width_cm * base_style.layer_left_percent / 100.0
    )
    assert (
        style.figure_style.page_width_cm
        * (
            100.0
            - style.figure_style.layer_left_percent
            - style.figure_style.layer_width_percent
        )
        / 100.0
    ) == pytest.approx(
        base_style.page_width_cm
        * (100.0 - base_style.layer_left_percent - base_style.layer_width_percent)
        / 100.0
    )
    assert style.legend_visible is True
    assert style.legend_position == "inside"
    assert style.legend_frame is False
    assert dict(style.series_color_overrides)["raw"] == "#123456"
    for coarse in (
        "line_weight",
        "fill_transparency",
        "aspect_ratio_class",
        "legend_position",
        "legend_frame",
    ):
        assert rejected[coarse]["reason"] == "explicit_user_visual_setting_has_precedence"


@pytest.mark.parametrize(
    "style_request",
    [
        {"line_width_pt": True},
        {"line_width_pt": float("nan")},
        {"line_width_pt": 0.89},
        {"fill_transparency_percent": float("inf")},
        {"fill_transparency_percent": 85.01},
        {"page_size_cm": {"width": 11.9, "height": 18.0}},
        {"series_colors": {"raw": "#123"}},
        {"legend_visible": "false"},
        {"unknown_style_key": "value"},
    ],
)
def test_malformed_explicit_style_fails_fast(style_request: dict[str, object]) -> None:
    with pytest.raises(XpsVisualStyleError) as caught:
        normalize_xps_visual_tokens(style_request)

    assert caught.value.code == "xps_visual_style_invalid"


def test_unknown_explicit_palette_fails_instead_of_silently_using_default() -> None:
    preparation = prepare_xps(ADAPTIVE_SOURCE)

    with pytest.raises(XpsVisualStyleError) as caught:
        apply_xps_visual_style(
            preparation,
            {"palette_id": "palette_does_not_exist"},
            source="explicit_user",
        )

    assert caught.value.code == "xps_palette_invalid"


def test_fixed_c1s_palette_counts_components_only_and_keeps_semantic_roles() -> None:
    preparation = prepare_xps(FIXED_SOURCE)
    palette = get_palette("navy_cyan_gold")
    assert len(preparation.roles.components) == 4
    assert palette.max_qualitative_categories == 5

    application = apply_xps_visual_style(
        preparation,
        {"palette_id": palette.palette_id},
        source="explicit_user",
    )
    visual = application.preparation.visual_contract

    assert not application.report["rejected"]
    assert visual.palette_id == palette.palette_id
    assert visual.raw_color == preparation.visual_contract.raw_color
    assert visual.background_color == preparation.visual_contract.background_color
    assert visual.envelope_color == preparation.visual_contract.envelope_color
    assert visual.component_colors == palette.colors[:4]


def test_outside_legend_preserves_a_readable_physical_right_column() -> None:
    preparation = prepare_xps(FIXED_SOURCE)

    application = apply_xps_visual_style(
        preparation,
        {
            "legend_position": "outside_right",
            "page_size_cm": {"width": 28.0, "height": 19.0},
        },
        source="explicit_user",
    )
    style = application.preparation.visual_contract.figure_style
    right_margin_cm = style.page_width_cm * (
        100.0 - style.layer_left_percent - style.layer_width_percent
    ) / 100.0

    assert right_margin_cm == pytest.approx(8.0)
    assert style.page_width_cm * style.layer_width_percent / 100.0 > 0.0


def test_explicit_palette_over_safe_category_limit_fails_fast(tmp_path: Path) -> None:
    frame = pd.read_csv(ADAPTIVE_SOURCE)
    frame["Peak C"] = frame["Peak A"] * 0.8
    frame["Peak D"] = frame["Peak A"] * 0.6
    frame["Peak E"] = frame["Peak A"] * 0.4
    source = tmp_path / "xps_five_components.csv"
    frame.to_csv(source, index=False)
    preparation = prepare_xps(
        source,
        column_mapping=XpsColumnMapping(
            x="Binding Energy (E)",
            raw="Counts / s",
            background="Backgnd.",
            envelope="Envelope",
            residual="Residuals",
            components=("Peak A", "Peak B", "Peak C", "Peak D", "Peak E"),
            ignored=(),
            energy_kind="binding",
        ),
    )
    assert len(preparation.roles.components) == 5
    assert get_palette("deep_sea_gold").max_qualitative_categories == 4

    with pytest.raises(XpsVisualStyleError) as caught:
        apply_xps_visual_style(
            preparation,
            {"palette_id": "deep_sea_gold"},
            source="explicit_user",
        )

    assert caught.value.code == "xps_palette_category_limit_exceeded"


def _preparation_with_ignored_column(tmp_path: Path) -> XpsPreparation:
    frame = pd.read_csv(ADAPTIVE_SOURCE)
    frame["QC_only"] = range(len(frame.index))
    source = tmp_path / "xps_with_qc.csv"
    frame.to_csv(source, index=False)
    return prepare_xps(
        source,
        column_mapping=XpsColumnMapping(
            x="Binding Energy (E)",
            raw="Counts / s",
            background="Backgnd.",
            envelope="Envelope",
            residual="Residuals",
            components=("Peak A", "Peak B"),
            ignored=("QC_only",),
            energy_kind="binding",
        ),
    )


@pytest.mark.parametrize("target_kind", ["x", "residual", "ignored"])
def test_explicit_series_colors_reject_non_rendered_columns(
    tmp_path: Path,
    target_kind: str,
) -> None:
    preparation = _preparation_with_ignored_column(tmp_path)
    targets = {
        "x": preparation.roles.x,
        "residual": preparation.roles.residual,
        "ignored": preparation.roles.ignored[0],
    }
    target = targets[target_kind]
    assert target is not None

    with pytest.raises(XpsVisualStyleError) as caught:
        apply_xps_visual_style(
            preparation,
            {"series_colors": {target: "#123456"}},
            source="explicit_user",
        )

    assert caught.value.code == "xps_series_colors_unknown_key"


def test_xps_runners_keep_verified_pfm3_and_never_use_pfm4() -> None:
    for runner in XPS_RUNNERS:
        text = runner.read_text(encoding="utf-8")
        assert "-pfm 3" in text, runner
        assert "-pfm 4" not in text, runner
