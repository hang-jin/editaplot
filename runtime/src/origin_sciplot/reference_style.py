"""Safe, deterministic style-only adaptation for confirmed reference figures.

This module deliberately cannot add, remove, reorder, or transform scientific
series.  It consumes the path-free :mod:`reference_adaptation` payload and
changes only style fields already shared by the Matplotlib preview and the
editable Origin renderers.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from .scientific_workflow import (
    ScientificPreparation,
    ScientificWorkflowError,
    _scientific_plan_digest,
    apply_scientific_palette_override,
)

REFERENCE_STYLE_REPORT_VERSION = "1.0"

_STYLE_TOKEN_KEYS = (
    "palette_family",
    "palette_id",
    "line_weight",
    "marker_density",
    "fill_transparency",
    "legend_position",
    "legend_frame",
    "grid",
    "background",
    "typography_hierarchy",
)
_LINE_WEIGHT_FACTORS = {
    "light": 0.74,
    "medium": 1.0,
    "heavy": 1.28,
}
_MARKER_SIZE_FACTORS = {
    "sparse": 0.76,
    "medium": 1.0,
    "dense": 1.22,
}
_FILL_TRANSPARENCY_PERCENT = {
    "none": 0.0,
    "light": 12.0,
    "medium": 30.0,
    "heavy": 55.0,
}

_LINE_WEIGHT_PLOT_KINDS = frozenset(
    {
        "bar_error",
        "bland_altman",
        "bubble",
        "calibration_curve",
        "decision_curve",
        "diagnostic_curve",
        "forest",
        "grouped_box",
        "histogram",
        "horizontal_bar",
        "line",
        "line_error",
        "nyquist",
        "paired_trajectory",
        "pl_decay",
        "pl_spectrum",
        "radar",
        "raincloud",
        "raw_summary",
        "rietveld_refinement",
        "scatter",
        "stacked_bar",
        "stacked_line",
        "trajectory3d",
        "trend",
        "uv_vis",
        "violin",
    }
)
_MARKER_SIZE_PLOT_KINDS = frozenset(
    {
        "bland_altman",
        "bubble",
        "calibration_curve",
        "forest",
        "grouped_box",
        "line_error",
        "nyquist",
        "paired_trajectory",
        "pl_decay",
        "pl_spectrum",
        "raincloud",
        "raw_summary",
        "rietveld_refinement",
        "scatter",
        "shap_summary",
        "trajectory3d",
        "uv_vis",
        "violin",
    }
)
_FILL_PLOT_KINDS = frozenset(
    {
        "bar_error",
        "bubble",
        "calibration_curve",
        "grouped_box",
        "histogram",
        "horizontal_bar",
        "percent_stacked_bar",
        "raincloud",
        "raw_summary",
        "stacked_bar",
        "violin",
    }
)


class ReferenceStyleError(ValueError):
    """Stable fail-closed error raised before any renderer is started."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ReferenceStyleApplication:
    """A frozen preparation plus its auditable reference-style decision."""

    preparation: ScientificPreparation
    report: dict[str, Any]


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _payload_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _validated_adaptation(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    expected_hash = normalized.pop("plan_hash", None)
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ReferenceStyleError(
            "reference_style_plan_hash_missing",
            "Reference style adaptation needs its confirmed plan hash.",
        )
    if _payload_hash(normalized) != expected_hash:
        raise ReferenceStyleError(
            "reference_style_plan_hash_mismatch",
            "The reference adaptation changed after confirmation.",
        )
    style_tokens = normalized.get("style_tokens")
    if not isinstance(style_tokens, Mapping):
        raise ReferenceStyleError(
            "reference_style_tokens_missing",
            "The reference adaptation has no style token contract.",
        )
    unknown = set(style_tokens) - set(_STYLE_TOKEN_KEYS)
    missing = set(_STYLE_TOKEN_KEYS) - set(style_tokens)
    if unknown or missing:
        raise ReferenceStyleError(
            "reference_style_tokens_invalid",
            "Reference style tokens do not match the strict public contract.",
        )
    normalized["style_tokens"] = dict(style_tokens)
    normalized["plan_hash"] = expected_hash
    return normalized


def _item(
    token: str,
    requested: object,
    *,
    resolved: object | None = None,
    reason: str,
    implementation: str | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "token": token,
        "requested": requested,
        "reason": reason,
    }
    if resolved is not None:
        item["resolved"] = resolved
    if implementation is not None:
        item["implementation"] = implementation
    return item


def _verified_legend_position(preparation: ScientificPreparation) -> str:
    spec = preparation.plot_spec
    if spec.plot_kind in {"percent_stacked_bar", "pie"}:
        return "outside_right"
    if spec.plot_kind == "grouped_box":
        return "top"
    if spec.plot_kind in {
        "bland_altman",
        "bubble",
        "forest",
        "paired_trajectory",
        "raincloud",
        "raw_summary",
        "shap_summary",
        "violin",
    }:
        return "none"
    visible = [series for series in spec.series if series.series_role != "fit"]
    return "inside" if len(visible) > 1 else "none"


def _verified_grid(preparation: ScientificPreparation) -> str:
    return "major_only" if preparation.plot_spec.plot_kind in {"radar", "trajectory3d"} else "none"


def _finish_report(
    preparation: ScientificPreparation,
    *,
    adaptation: dict[str, Any],
    input_digest: str,
    applied: list[dict[str, object]],
    rejected: list[dict[str, object]],
    retained: list[dict[str, object]],
    execution_allowed: bool,
    blocking_reasons: list[str],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "report_version": REFERENCE_STYLE_REPORT_VERSION,
        "route": adaptation["route"],
        "template_id": adaptation.get("template_id"),
        "reference_plan_hash": adaptation["plan_hash"],
        "input_plan_digest": input_digest,
        "output_plan_digest": preparation.plan_digest,
        "execution_allowed": execution_allowed,
        "blocking_reasons": sorted(set(blocking_reasons)),
        "applied": applied,
        "rejected": rejected,
        "retained_template_default": retained,
        "safety": {
            "style_only": True,
            "source_values_changed": False,
            "scientific_elements_changed": False,
            "series_visibility_changed": False,
            "marker_points_sampled_or_removed": 0,
            "layout_changed": False,
            "reference_pixels_used_by_renderer": False,
            "origin_commands_embedded": False,
        },
    }
    payload["report_hash"] = _payload_hash(payload)
    return payload


def apply_reference_style(
    preparation: ScientificPreparation,
    adaptation_payload: Mapping[str, Any],
    *,
    locked_palette_id: str | None = None,
) -> ReferenceStyleApplication:
    """Apply only renderer-shared style tokens and report every decision.

    Unsupported cosmetic requests are rejected while the verified template
    default is retained.  Structural mismatches, XPS, and controlled
    composition remain blocking.
    """

    if not isinstance(preparation, ScientificPreparation):
        raise ReferenceStyleError(
            "reference_style_preparation_invalid",
            "Reference style adaptation requires a scientific preparation.",
        )
    adaptation = _validated_adaptation(adaptation_payload)
    input_digest = preparation.plan_digest
    applied: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    retained: list[dict[str, object]] = []
    blocking_reasons: list[str] = []
    execution_allowed = True

    route = adaptation.get("route")
    if route == "controlled_composition":
        execution_allowed = False
        blocking_reasons.append("reference_controlled_composition_renderer_not_verified")
        return ReferenceStyleApplication(
            preparation,
            _finish_report(
                preparation,
                adaptation=adaptation,
                input_digest=input_digest,
                applied=applied,
                rejected=rejected,
                retained=retained,
                execution_allowed=execution_allowed,
                blocking_reasons=blocking_reasons,
            ),
        )
    if route != "template_adaptation":
        raise ReferenceStyleError(
            "reference_style_route_invalid",
            "Only template_adaptation can reach the style adapter.",
        )
    if adaptation.get("template_id") != preparation.template_id:
        raise ReferenceStyleError(
            "reference_style_template_mismatch",
            "The reference style belongs to a different registered template.",
        )
    if preparation.template_id == "xps":
        raise ReferenceStyleError(
            "reference_style_xps_unsupported",
            "XPS keeps its verified component and fill style contract.",
        )

    layout = adaptation.get("layout")
    if not isinstance(layout, Mapping):
        raise ReferenceStyleError(
            "reference_style_layout_missing",
            "The reference adaptation has no layout contract.",
        )
    panels = layout.get("panels")
    if layout.get("archetype") != "single_chart" or not isinstance(panels, list) or len(panels) != 1:
        execution_allowed = False
        blocking_reasons.append("reference_layout_renderer_not_verified")
        rejected.append(
            _item(
                "layout",
                {
                    "archetype": layout.get("archetype"),
                    "panel_count": len(panels) if isinstance(panels, list) else None,
                },
                reason="reference_layout_renderer_not_verified",
            )
        )
    else:
        retained.append(
            _item(
                "layout",
                {
                    "archetype": layout.get("archetype"),
                    "aspect_ratio_class": layout.get("aspect_ratio_class"),
                },
                resolved="registered_template_layout",
                reason="template_geometry_remains_frozen",
            )
        )

    tokens = adaptation["style_tokens"]
    spec = preparation.plot_spec
    style = spec.display_plan.figure_style
    if style is None:
        raise ReferenceStyleError(
            "reference_style_profile_missing",
            "The selected template has no adaptive style profile.",
        )

    palette_family = tokens["palette_family"]
    if palette_family is None:
        retained.append(
            _item(
                "palette_family",
                None,
                resolved=style.palette_name,
                reason="registered_palette_retained",
            )
        )
    else:
        rejected.append(
            _item(
                "palette_family",
                palette_family,
                resolved=style.palette_name,
                reason="palette_family_is_descriptive_only_use_palette_id",
            )
        )

    requested_palette = tokens["palette_id"]
    if requested_palette is None:
        retained.append(
            _item(
                "palette_id",
                None,
                resolved=style.palette_name,
                reason="registered_palette_retained",
            )
        )
    elif locked_palette_id is not None and requested_palette != locked_palette_id:
        rejected.append(
            _item(
                "palette_id",
                requested_palette,
                resolved=locked_palette_id,
                reason="explicit_user_palette_has_precedence",
            )
        )
    else:
        try:
            preparation = apply_scientific_palette_override(
                preparation,
                palette_id=str(requested_palette),
            )
        except (ScientificWorkflowError, KeyError, ValueError) as exc:
            rejected.append(
                _item(
                    "palette_id",
                    requested_palette,
                    resolved=style.palette_name,
                    reason=getattr(exc, "code", "palette_id_not_compatible"),
                )
            )
        else:
            applied.append(
                _item(
                    "palette_id",
                    requested_palette,
                    resolved=requested_palette,
                    reason="compatible_registered_palette",
                    implementation="shared_preview_origin_palette_name",
                )
            )

    spec = preparation.plot_spec
    style = spec.display_plan.figure_style
    if style is None:
        raise ReferenceStyleError(
            "reference_style_profile_missing",
            "The selected template lost its adaptive style profile.",
        )

    requested_weight = str(tokens["line_weight"])
    if requested_weight == "adaptive":
        retained.append(
            _item(
                "line_weight",
                requested_weight,
                resolved=style.plot_line_width_pt,
                reason="adaptive_template_weight_retained",
            )
        )
    elif requested_weight in _LINE_WEIGHT_FACTORS and spec.plot_kind in _LINE_WEIGHT_PLOT_KINDS:
        factor = _LINE_WEIGHT_FACTORS[requested_weight]
        style = replace(
            style,
            plot_line_width_pt=round(
                min(4.5, max(0.9, style.plot_line_width_pt * factor)),
                3,
            ),
            bar_border_width_pt=round(
                min(3.6, max(0.8, style.bar_border_width_pt * factor)),
                3,
            ),
            error_bar_width_pt=round(
                min(3.6, max(0.8, style.error_bar_width_pt * factor)),
                3,
            ),
        )
        applied.append(
            _item(
                "line_weight",
                requested_weight,
                resolved={
                    "plot_line_width_pt": style.plot_line_width_pt,
                    "bar_border_width_pt": style.bar_border_width_pt,
                    "error_bar_width_pt": style.error_bar_width_pt,
                },
                reason="verified_data_stroke_mapping",
                implementation="preview_and_origin_physical_point_widths",
            )
        )
    else:
        rejected.append(
            _item(
                "line_weight",
                requested_weight,
                resolved=style.plot_line_width_pt,
                reason="line_weight_not_applicable_or_invalid",
            )
        )

    requested_density = str(tokens["marker_density"])
    marker_size = spec.display_plan.marker_size_pt
    if requested_density == "adaptive":
        retained.append(
            _item(
                "marker_density",
                requested_density,
                resolved=marker_size,
                reason="adaptive_marker_size_retained",
                implementation="all_source_points_retained",
            )
        )
    elif requested_density == "none":
        rejected.append(
            _item(
                "marker_density",
                requested_density,
                resolved=marker_size,
                reason="marker_hiding_forbidden",
                implementation="all_source_points_retained",
            )
        )
    elif requested_density in _MARKER_SIZE_FACTORS and spec.plot_kind in _MARKER_SIZE_PLOT_KINDS:
        marker_size = round(
            min(14.0, max(2.2, marker_size * _MARKER_SIZE_FACTORS[requested_density])),
            3,
        )
        applied.append(
            _item(
                "marker_density",
                requested_density,
                resolved={"marker_size_pt": marker_size},
                reason="density_token_mapped_to_size_only",
                implementation="no_sampling_no_point_deletion",
            )
        )
    else:
        rejected.append(
            _item(
                "marker_density",
                requested_density,
                resolved=marker_size,
                reason="marker_size_not_applicable_or_invalid",
                implementation="all_source_points_retained",
            )
        )

    requested_fill = str(tokens["fill_transparency"])
    if spec.plot_kind not in _FILL_PLOT_KINDS:
        retained.append(
            _item(
                "fill_transparency",
                requested_fill,
                resolved=style.fill_transparency_percent,
                reason="no_verified_fill_mark_in_selected_template",
            )
        )
    elif requested_fill in _FILL_TRANSPARENCY_PERCENT:
        style = replace(
            style,
            fill_transparency_percent=_FILL_TRANSPARENCY_PERCENT[requested_fill],
        )
        applied.append(
            _item(
                "fill_transparency",
                requested_fill,
                resolved=style.fill_transparency_percent,
                reason="verified_fill_transparency_mapping",
                implementation="shared_preview_origin_percent_transparency",
            )
        )
    else:
        rejected.append(
            _item(
                "fill_transparency",
                requested_fill,
                resolved=style.fill_transparency_percent,
                reason="fill_transparency_invalid",
            )
        )

    requested_legend_position = str(tokens["legend_position"])
    verified_legend_position = _verified_legend_position(preparation)
    if requested_legend_position == verified_legend_position:
        retained.append(
            _item(
                "legend_position",
                requested_legend_position,
                resolved=verified_legend_position,
                reason="verified_template_legend_position_retained",
            )
        )
    else:
        rejected.append(
            _item(
                "legend_position",
                requested_legend_position,
                resolved=verified_legend_position,
                reason="reference_legend_position_not_verified_for_renderer",
            )
        )

    requested_legend_frame = tokens["legend_frame"]
    if requested_legend_frame is False:
        applied.append(
            _item(
                "legend_frame",
                False,
                resolved=False,
                reason="verified_borderless_legend_contract",
                implementation="origin_legend_showframe_readback_and_preview_frameoff",
            )
        )
    else:
        rejected.append(
            _item(
                "legend_frame",
                requested_legend_frame,
                resolved=False,
                reason="framed_legend_not_allowed",
            )
        )

    requested_grid = str(tokens["grid"])
    verified_grid = _verified_grid(preparation)
    if requested_grid == verified_grid:
        retained.append(
            _item(
                "grid",
                requested_grid,
                resolved=verified_grid,
                reason="verified_template_grid_retained",
            )
        )
    else:
        rejected.append(
            _item(
                "grid",
                requested_grid,
                resolved=verified_grid,
                reason="reference_grid_not_verified_for_renderer",
            )
        )

    requested_background = str(tokens["background"])
    if requested_background == "white":
        retained.append(
            _item(
                "background",
                requested_background,
                resolved="white",
                reason="verified_white_background_retained",
            )
        )
    else:
        rejected.append(
            _item(
                "background",
                requested_background,
                resolved="white",
                reason="reference_background_not_verified_for_renderer",
            )
        )

    requested_typography = str(tokens["typography_hierarchy"])
    if requested_typography in {"publication_informed", "adaptive"}:
        retained.append(
            _item(
                "typography_hierarchy",
                requested_typography,
                resolved=style.profile_name,
                reason="verified_adaptive_typography_retained",
            )
        )
    else:
        rejected.append(
            _item(
                "typography_hierarchy",
                requested_typography,
                resolved=style.profile_name,
                reason="reference_typography_not_verified_for_renderer",
            )
        )

    updated_display = replace(
        spec.display_plan,
        marker_size_pt=marker_size,
        figure_style=style,
    )
    updated_spec = replace(spec, display_plan=updated_display)
    if updated_spec != preparation.plot_spec:
        preparation = replace(
            preparation,
            plot_spec=updated_spec,
            plan_digest=_scientific_plan_digest(preparation, updated_spec),
        )

    report = _finish_report(
        preparation,
        adaptation=adaptation,
        input_digest=input_digest,
        applied=applied,
        rejected=rejected,
        retained=retained,
        execution_allowed=execution_allowed,
        blocking_reasons=blocking_reasons,
    )
    return ReferenceStyleApplication(preparation, report)


__all__ = [
    "REFERENCE_STYLE_REPORT_VERSION",
    "ReferenceStyleApplication",
    "ReferenceStyleError",
    "apply_reference_style",
]
