"""Deterministic visual-only overrides for an immutable XPS preparation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from .palette_catalog import get_palette
from .xps_workflow import (
    XpsPreparation,
    XpsVisualContract,
    replace_xps_visual_contract,
)

XPS_VISUAL_STYLE_REPORT_VERSION = "1.0"
XPS_VISUAL_STYLE_KEYS = frozenset(
    {
        "palette_id",
        "line_weight",
        "fill_transparency",
        "aspect_ratio_class",
        "legend_position",
        "legend_frame",
        "series_colors",
        "line_width_pt",
        "fill_transparency_percent",
        "page_size_cm",
        "legend_visible",
    }
)

_LINE_WEIGHT_FACTORS = {"light": 0.74, "medium": 1.0, "heavy": 1.28}
_FILL_TRANSPARENCY_PERCENT = {
    "none": 0.0,
    "light": 12.0,
    "medium": 30.0,
    "heavy": 55.0,
}
_PAGE_SIZE_CM = {
    "wide": (24.0, 15.5),
    "square": (19.0, 19.0),
    "tall": (16.5, 22.0),
}
_OUTSIDE_LEGEND_RESERVE_CM = 8.0
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class XpsVisualStyleError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class XpsVisualStyleApplication:
    preparation: XpsPreparation
    report: dict[str, Any]


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def normalize_xps_visual_tokens(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise XpsVisualStyleError(
            "xps_visual_style_invalid",
            "XPS visual style must be a JSON object.",
        )
    unknown = set(payload) - XPS_VISUAL_STYLE_KEYS
    if unknown:
        raise XpsVisualStyleError(
            "xps_visual_style_invalid",
            f"Unsupported XPS visual style keys: {sorted(unknown)}.",
        )
    result = dict(payload)
    palette_id = result.get("palette_id")
    if palette_id is not None and (not isinstance(palette_id, str) or not palette_id.strip()):
        raise XpsVisualStyleError("xps_visual_style_invalid", "palette_id must be a stable string.")
    for key, allowed in (
        ("line_weight", {"adaptive", *_LINE_WEIGHT_FACTORS}),
        ("fill_transparency", {"adaptive", *_FILL_TRANSPARENCY_PERCENT}),
        ("aspect_ratio_class", {"adaptive", *_PAGE_SIZE_CM}),
        ("legend_position", {"adaptive", "inside", "outside_right", "none"}),
    ):
        value = result.get(key)
        if value is not None and value not in allowed:
            raise XpsVisualStyleError(
                "xps_visual_style_invalid",
                f"{key} has an unsupported value.",
            )
    if "legend_frame" in result and not isinstance(result["legend_frame"], bool):
        raise XpsVisualStyleError(
            "xps_visual_style_invalid",
            "legend_frame must be true or false.",
        )
    if "legend_visible" in result and not isinstance(result["legend_visible"], bool):
        raise XpsVisualStyleError(
            "xps_visual_style_invalid",
            "legend_visible must be true or false.",
        )
    if "series_colors" in result:
        colors = result["series_colors"]
        if not isinstance(colors, Mapping) or not all(
            isinstance(key, str)
            and key.strip()
            and isinstance(value, str)
            and _HEX_COLOR.fullmatch(value)
            for key, value in colors.items()
        ):
            raise XpsVisualStyleError(
                "xps_visual_style_invalid",
                "series_colors must map XPS roles or source columns to #RRGGBB values.",
            )
        result["series_colors"] = {
            str(key).strip(): str(value).upper() for key, value in colors.items()
        }
    if "line_width_pt" in result:
        value = result["line_width_pt"]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0.9 <= float(value) <= 6.4
        ):
            raise XpsVisualStyleError(
                "xps_visual_style_invalid",
                "line_width_pt must be a finite physical width from 0.9 to 6.4 pt.",
            )
        result["line_width_pt"] = round(float(value), 3)
    if "fill_transparency_percent" in result:
        value = result["fill_transparency_percent"]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0.0 <= float(value) <= 85.0
        ):
            raise XpsVisualStyleError(
                "xps_visual_style_invalid",
                "fill_transparency_percent must be from 0 to 85.",
            )
        result["fill_transparency_percent"] = round(float(value), 3)
    if "page_size_cm" in result:
        value = result["page_size_cm"]
        if isinstance(value, Mapping):
            width = value.get("width")
            height = value.get("height")
        elif isinstance(value, (list, tuple)) and len(value) == 2:
            width, height = value
        else:
            width = height = None
        if any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            or not 12.0 <= float(item) <= 40.0
            for item in (width, height)
        ):
            raise XpsVisualStyleError(
                "xps_visual_style_invalid",
                "page_size_cm needs width/height values from 12 to 40 cm.",
            )
        result["page_size_cm"] = {
            "width": round(float(width), 3),
            "height": round(float(height), 3),
        }
    return result


def _item(
    token: str,
    requested: object,
    *,
    resolved: object,
    reason: str,
    implementation: str | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "token": token,
        "requested": requested,
        "resolved": resolved,
        "reason": reason,
    }
    if implementation is not None:
        item["implementation"] = implementation
    return item


def _mix_with_white(color: str, fraction: float) -> str:
    text = color.lstrip("#")
    channels = [int(text[index : index + 2], 16) for index in (0, 2, 4)]
    mixed = [round(channel + (255 - channel) * fraction) for channel in channels]
    return "#" + "".join(f"{channel:02X}" for channel in mixed)


def _resize_page_preserving_horizontal_margins(
    style: Any,
    *,
    width_cm: float,
    height_cm: float,
) -> Any:
    """Resize an XPS page without shrinking its verified title/tick margins.

    Origin positions the special YL axis-title object from the plot layer's
    physical left margin.  Keeping only the old percentage on a narrower
    square/tall page can therefore clip a correctly sized 26 pt title.  Keep
    the verified left and right margins in centimetres while allowing the
    plot height to follow the requested page shape.
    """

    left_cm = style.page_width_cm * style.layer_left_percent / 100.0
    right_cm = style.page_width_cm * (
        100.0 - style.layer_left_percent - style.layer_width_percent
    ) / 100.0
    available_cm = width_cm - left_cm - right_cm
    if available_cm <= 0.0:
        raise XpsVisualStyleError(
            "xps_page_width_too_small_for_verified_margins",
            "The requested XPS page is too narrow for the verified axis-title margins.",
        )
    return replace(
        style,
        page_width_cm=width_cm,
        page_height_cm=height_cm,
        layer_left_percent=left_cm / width_cm * 100.0,
        layer_width_percent=available_cm / width_cm * 100.0,
    )


def _palette_contract(
    preparation: XpsPreparation,
    visual: XpsVisualContract,
    palette_id: str,
) -> XpsVisualContract:
    palette = get_palette(palette_id)
    if "qualitative" not in palette.allowed_modes:
        raise XpsVisualStyleError(
            "xps_palette_mode_incompatible",
            "The selected palette is not registered for qualitative XPS roles.",
        )
    component_count = len(preparation.roles.components)
    if component_count < 1:
        raise XpsVisualStyleError(
            "xps_palette_not_applicable",
            "This XPS plan has no component colours to replace.",
        )
    if component_count > palette.max_qualitative_categories:
        raise XpsVisualStyleError(
            "xps_palette_category_limit_exceeded",
            (
                f"The selected palette safely supports {palette.max_qualitative_categories} "
                f"component colours, but this plan needs {component_count}."
            ),
        )
    components = tuple(palette.colors[:component_count])
    return replace(
        visual,
        palette_id=palette_id,
        figure_style=replace(visual.figure_style, palette_name=palette_id),
        component_colors=components,
        component_fill_colors=tuple(_mix_with_white(color, 0.34) for color in components),
    )


def apply_xps_visual_style(
    preparation: XpsPreparation,
    tokens: Mapping[str, Any] | None,
    *,
    source: str,
    locked_tokens: Mapping[str, Any] | None = None,
) -> XpsVisualStyleApplication:
    """Apply style tokens without changing source roles, series, axes, or helpers."""

    if not isinstance(preparation, XpsPreparation):
        raise XpsVisualStyleError(
            "xps_visual_style_preparation_invalid",
            "XPS visual style requires an XpsPreparation.",
        )
    requested = normalize_xps_visual_tokens(tokens)
    locked = dict(locked_tokens or {})
    if set(locked) - XPS_VISUAL_STYLE_KEYS:
        raise XpsVisualStyleError(
            "xps_visual_style_invalid",
            "Locked XPS visual tokens contain unsupported fields.",
        )
    input_digest = preparation.plan_digest
    semantic_snapshot = (
        preparation.source_sha256,
        preparation.source_columns,
        preparation.roles,
        preparation.detection,
        preparation.plot_spec,
    )
    visual = preparation.visual_contract
    applied: list[dict[str, object]] = []
    retained: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []

    def is_locked(token: str, value: object) -> bool:
        if token not in locked:
            return False
        rejected.append(
            _item(
                token,
                value,
                resolved=locked[token],
                reason="explicit_user_visual_setting_has_precedence",
            )
        )
        return True

    if "palette_id" in requested and not is_locked("palette_id", requested["palette_id"]):
        palette_id = requested["palette_id"]
        if palette_id is None:
            retained.append(
                _item(
                    "palette_id",
                    None,
                    resolved=visual.palette_id,
                    reason="template_semantic_palette_retained",
                )
            )
        else:
            try:
                visual = _palette_contract(preparation, visual, str(palette_id))
            except (KeyError, ValueError, XpsVisualStyleError) as exc:
                if source == "explicit_user":
                    raise XpsVisualStyleError(
                        getattr(exc, "code", "xps_palette_invalid"),
                        str(exc),
                    ) from exc
                rejected.append(
                    _item(
                        "palette_id",
                        palette_id,
                        resolved=visual.palette_id,
                        reason=getattr(exc, "code", "xps_palette_invalid"),
                    )
                )
            else:
                applied.append(
                    _item(
                        "palette_id",
                        palette_id,
                        resolved=visual.palette_id,
                        reason="registered_xps_role_palette",
                        implementation="shared_preview_origin_role_hex_colors",
                    )
                )

    if "line_weight" in requested and not is_locked("line_weight", requested["line_weight"]):
        value = str(requested["line_weight"])
        if value == "adaptive":
            retained.append(
                _item(
                    "line_weight",
                    value,
                    resolved=visual.figure_style.plot_line_width_pt,
                    reason="template_physical_line_width_retained",
                )
            )
        else:
            factor = _LINE_WEIGHT_FACTORS[value]
            width = round(min(6.4, max(0.9, 5.0 * factor)), 3)
            visual = replace(
                visual,
                figure_style=replace(visual.figure_style, plot_line_width_pt=width),
            )
            applied.append(
                _item(
                    "line_weight",
                    value,
                    resolved=width,
                    reason="verified_xps_data_stroke_mapping",
                    implementation="set_w_500_units_and_preview_points",
                )
            )

    if "fill_transparency" in requested and not is_locked(
        "fill_transparency", requested["fill_transparency"]
    ):
        value = str(requested["fill_transparency"])
        if value == "adaptive":
            retained.append(
                _item(
                    "fill_transparency",
                    value,
                    resolved=visual.figure_style.fill_transparency_percent,
                    reason="template_fill_transparency_retained",
                )
            )
        else:
            percent = _FILL_TRANSPARENCY_PERCENT[value]
            visual = replace(
                visual,
                figure_style=replace(
                    visual.figure_style,
                    fill_transparency_percent=percent,
                ),
            )
            applied.append(
                _item(
                    "fill_transparency",
                    value,
                    resolved=percent,
                    reason="verified_xps_plot_transparency_mapping",
                    implementation="plot_transparency_property_with_pfm3_fill",
                )
            )

    if "aspect_ratio_class" in requested and not is_locked(
        "aspect_ratio_class", requested["aspect_ratio_class"]
    ):
        value = str(requested["aspect_ratio_class"])
        if value == "adaptive":
            retained.append(
                _item(
                    "aspect_ratio_class",
                    value,
                    resolved={
                        "page_width_cm": visual.figure_style.page_width_cm,
                        "page_height_cm": visual.figure_style.page_height_cm,
                    },
                    reason="template_physical_page_retained",
                )
            )
        else:
            width, height = _PAGE_SIZE_CM[value]
            visual = replace(
                visual,
                figure_style=_resize_page_preserving_horizontal_margins(
                    visual.figure_style,
                    width_cm=width,
                    height_cm=height,
                ),
            )
            applied.append(
                _item(
                    "aspect_ratio_class",
                    value,
                    resolved={"page_width_cm": width, "page_height_cm": height},
                    reason="verified_physical_page_api_mapping",
                    implementation="graph_putwidth_putheight_and_readback",
                )
            )

    if "legend_position" in requested and not is_locked(
        "legend_position", requested["legend_position"]
    ):
        value = str(requested["legend_position"])
        if value == "adaptive":
            retained.append(
                _item(
                    "legend_position",
                    value,
                    resolved=visual.legend_position,
                    reason="template_editable_legend_position_retained",
                )
            )
        else:
            visual = replace(
                visual,
                legend_position=value,
                legend_visible=value != "none",
            )
            if value == "outside_right":
                figure_style = visual.figure_style
                left_cm = (
                    figure_style.page_width_cm
                    * figure_style.layer_left_percent
                    / 100.0
                )
                available_cm = (
                    figure_style.page_width_cm
                    - left_cm
                    - _OUTSIDE_LEGEND_RESERVE_CM
                )
                if available_cm <= 0.0:
                    raise XpsVisualStyleError(
                        "xps_page_width_too_small_for_outside_legend",
                        "The requested XPS page is too narrow for a readable outside legend.",
                    )
                visual = replace(
                    visual,
                    figure_style=replace(
                        figure_style,
                        layer_width_percent=min(
                            figure_style.layer_width_percent,
                            available_cm / figure_style.page_width_cm * 100.0,
                        ),
                    ),
                )
            applied.append(
                _item(
                    "legend_position",
                    value,
                    resolved=value,
                    reason="verified_editable_legend_state_mapping",
                    implementation="legend_show_left_top_properties",
                )
            )

    if "legend_frame" in requested and not is_locked("legend_frame", requested["legend_frame"]):
        value = bool(requested["legend_frame"])
        visual = replace(visual, legend_frame=value)
        applied.append(
            _item(
                "legend_frame",
                value,
                resolved=value,
                reason="explicit_editable_legend_frame_state",
                implementation="legend_showframe_property_and_readback",
            )
        )

    # Exact user-confirmed values are applied after coarse tokens and therefore
    # have deterministic precedence over both reference suggestions and coarse
    # presets from the same request.
    if "series_colors" in requested and not is_locked("series_colors", requested["series_colors"]):
        provided = dict(requested["series_colors"])
        visible_specs = tuple(
            spec for spec in preparation.plot_spec.series if spec.role != "residual"
        )
        allowed_roles = {spec.role for spec in visible_specs}
        if "component" in allowed_roles:
            allowed_roles.add("components")
        source_columns = {spec.column for spec in visible_specs}
        accepted = {
            key: value
            for key, value in provided.items()
            if key in allowed_roles or key in source_columns
        }
        refused = sorted(set(provided) - set(accepted))
        if refused:
            if source == "explicit_user":
                raise XpsVisualStyleError(
                    "xps_series_colors_unknown_key",
                    f"Unknown XPS role or source column: {refused[0]!r}.",
                )
            rejected.append(
                _item(
                    "series_colors",
                    {key: provided[key] for key in refused},
                    resolved=dict(visual.series_color_overrides),
                    reason="unknown_xps_role_or_source_column",
                )
            )
        if accepted:
            visual = replace(
                visual,
                series_color_overrides=tuple(sorted(accepted.items())),
            )
            applied.append(
                _item(
                    "series_colors",
                    accepted,
                    resolved=accepted,
                    reason="exact_user_confirmed_series_colors",
                    implementation="shared_preview_origin_column_or_role_hex_map",
                )
            )

    if "line_width_pt" in requested and not is_locked("line_width_pt", requested["line_width_pt"]):
        width = float(requested["line_width_pt"])
        visual = replace(
            visual,
            figure_style=replace(visual.figure_style, plot_line_width_pt=width),
        )
        applied.append(
            _item(
                "line_width_pt",
                width,
                resolved=width,
                reason="exact_user_confirmed_physical_width",
                implementation="set_w_500_units_and_preview_points",
            )
        )

    if "fill_transparency_percent" in requested and not is_locked(
        "fill_transparency_percent", requested["fill_transparency_percent"]
    ):
        percent = float(requested["fill_transparency_percent"])
        visual = replace(
            visual,
            figure_style=replace(
                visual.figure_style,
                fill_transparency_percent=percent,
            ),
        )
        applied.append(
            _item(
                "fill_transparency_percent",
                percent,
                resolved=percent,
                reason="exact_user_confirmed_fill_transparency",
                implementation="independent_fill_plot_transparency_with_pfm3",
            )
        )

    if "page_size_cm" in requested and not is_locked("page_size_cm", requested["page_size_cm"]):
        page = dict(requested["page_size_cm"])
        visual = replace(
            visual,
            figure_style=_resize_page_preserving_horizontal_margins(
                visual.figure_style,
                width_cm=float(page["width"]),
                height_cm=float(page["height"]),
            ),
        )
        applied.append(
            _item(
                "page_size_cm",
                page,
                resolved=page,
                reason="exact_user_confirmed_physical_page",
                implementation="graph_putwidth_putheight_and_readback",
            )
        )

    if "legend_visible" in requested and not is_locked("legend_visible", requested["legend_visible"]):
        visible = bool(requested["legend_visible"])
        position = visual.legend_position if visible else "none"
        if visible and position == "none":
            position = "inside"
        visual = replace(
            visual,
            legend_visible=visible,
            legend_position=position,
        )
        applied.append(
            _item(
                "legend_visible",
                visible,
                resolved=visible,
                reason="exact_user_confirmed_editable_legend_visibility",
                implementation="legend_show_or_remove_with_readback",
            )
        )

    updated = replace_xps_visual_contract(preparation, visual)
    if semantic_snapshot != (
        updated.source_sha256,
        updated.source_columns,
        updated.roles,
        updated.detection,
        updated.plot_spec,
    ):
        raise XpsVisualStyleError(
            "xps_visual_style_semantics_changed",
            "A visual override attempted to change the frozen XPS semantics.",
        )
    report: dict[str, Any] = {
        "report_version": XPS_VISUAL_STYLE_REPORT_VERSION,
        "source": source,
        "input_plan_digest": input_digest,
        "output_plan_digest": updated.plan_digest,
        "requested_tokens": requested,
        "locked_tokens": locked,
        "applied": applied,
        "retained_template_default": retained,
        "rejected": rejected,
        "execution_allowed": True,
        "safety": {
            "style_only": True,
            "source_values_changed": False,
            "scientific_elements_changed": False,
            "series_visibility_changed": False,
            "source_columns_changed": False,
            "unverified_origin_parameter_added": False,
            "xps_fill_mode": "pfm3_two_colors",
        },
    }
    report["report_hash"] = _canonical_hash(report)
    return XpsVisualStyleApplication(updated, report)


__all__ = [
    "XPS_VISUAL_STYLE_KEYS",
    "XPS_VISUAL_STYLE_REPORT_VERSION",
    "XpsVisualStyleApplication",
    "XpsVisualStyleError",
    "apply_xps_visual_style",
    "normalize_xps_visual_tokens",
]
