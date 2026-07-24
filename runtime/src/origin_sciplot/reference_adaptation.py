"""Pure planning bridge from confirmed semantics and reference-figure grammar.

The adaptation plan is intentionally renderer-free.  It contains no source
path, source values, OCR text, executable code, or Origin commands.  A later
capability-gated renderer may consume only the allow-listed primitives frozen
here.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .reference_figure import ReferenceFigureError, ReferenceFigureSpec
from .semantic_contract import (
    ConfirmedSemanticContract,
    DataDisposition,
    SemanticContractError,
)

REFERENCE_ADAPTATION_PLAN_VERSION = "1.0"

ALLOWED_REFERENCE_PRIMITIVES = frozenset(
    {
        "line",
        "symbol",
        "line_symbol",
        "bar",
        "stacked_bar",
        "area",
        "error_bar",
        "box",
        "violin",
        "heatmap_cell",
        "reference_line",
        "residual_curve",
        "phase_tick",
        "text_annotation",
        "legend",
        "colorbar",
        "inset",
    }
)

_STRUCTURAL_PRIMITIVES = frozenset({"legend", "colorbar", "inset"})
_PRIMITIVE_CAPABILITIES: dict[str, frozenset[str]] = {
    # Keep every identifier aligned with OriginCapability.  Native plot
    # families remain owned by the selected template; this map adds only
    # independently testable capabilities activated by the reference grammar.
    "bar": frozenset({"categorical_axis"}),
    "stacked_bar": frozenset({"categorical_axis"}),
    "error_bar": frozenset({"error_bars"}),
    "box": frozenset({"statistical_plot"}),
    "violin": frozenset({"statistical_plot"}),
    "heatmap_cell": frozenset({"matrix_heatmap"}),
    "colorbar": frozenset({"matrix_heatmap"}),
    "inset": frozenset({"inset_layer"}),
}
_RENDERABLE_DISPOSITIONS = frozenset(
    {
        DataDisposition.RENDER_PRIMARY,
        DataDisposition.RENDER_SECONDARY,
    }
)
_SAFE_TEMPLATE_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FORBIDDEN_REFERENCE_CONTENT = frozenset(
    {
        "author",
        "brand",
        "copyright",
        "logo",
        "signature",
        "trademark",
        "watermark",
    }
)
_FORBIDDEN_EXECUTION_CONTENT = frozenset(
    {
        "argv",
        "cmd",
        "command",
        "exec",
        "labtalk",
        "powershell",
        "python",
        "script",
        "shell",
        "subprocess",
    }
)

_COMMON_CONTEXT_PRIMITIVES = frozenset({"text_annotation", "legend"})
_LINE_PRIMITIVES = frozenset(
    {
        "line",
        "symbol",
        "line_symbol",
        "reference_line",
    }
)

# A template route may consume only primitives it can express without changing
# the scientific chart family.  Routes whose native evidence mark is not yet in
# ReferenceFigureSpec (for example pie sectors and Sankey flows) intentionally
# expose context primitives only and therefore fail closed for essential data
# marks.
TEMPLATE_PRIMITIVE_COMPATIBILITY: dict[str, frozenset[str]] = {
    "xps": _COMMON_CONTEXT_PRIMITIVES | _LINE_PRIMITIVES | frozenset({"area"}),
    "xrd": _COMMON_CONTEXT_PRIMITIVES | _LINE_PRIMITIVES,
    "xas": _COMMON_CONTEXT_PRIMITIVES | _LINE_PRIMITIVES,
    "eis": _COMMON_CONTEXT_PRIMITIVES | _LINE_PRIMITIVES,
    "cv": _COMMON_CONTEXT_PRIMITIVES | _LINE_PRIMITIVES,
    "lsv": _COMMON_CONTEXT_PRIMITIVES | _LINE_PRIMITIVES,
    "scatter": _COMMON_CONTEXT_PRIMITIVES | frozenset({"symbol", "line", "reference_line"}),
    "line_error": _COMMON_CONTEXT_PRIMITIVES | _LINE_PRIMITIVES | frozenset({"error_bar"}),
    "trend": _COMMON_CONTEXT_PRIMITIVES | _LINE_PRIMITIVES,
    "bar": _COMMON_CONTEXT_PRIMITIVES | frozenset({"bar", "error_bar", "symbol", "reference_line"}),
    "horizontal_bar": _COMMON_CONTEXT_PRIMITIVES
    | frozenset({"bar", "error_bar", "symbol", "reference_line"}),
    "stacked_bar": _COMMON_CONTEXT_PRIMITIVES | frozenset({"stacked_bar"}),
    "percent_stacked_bar": _COMMON_CONTEXT_PRIMITIVES | frozenset({"stacked_bar"}),
    "pie": _COMMON_CONTEXT_PRIMITIVES,
    "sankey": _COMMON_CONTEXT_PRIMITIVES,
    "radar": _COMMON_CONTEXT_PRIMITIVES
    | frozenset({"line", "line_symbol", "symbol", "area", "reference_line"}),
    "heatmap": _COMMON_CONTEXT_PRIMITIVES | frozenset({"heatmap_cell", "colorbar"}),
    "raw_summary": _COMMON_CONTEXT_PRIMITIVES | frozenset({"symbol", "line", "error_bar", "reference_line"}),
    "violin": _COMMON_CONTEXT_PRIMITIVES
    | frozenset(
        {
            "violin",
            "box",
            "symbol",
            "line",
            "error_bar",
            "reference_line",
        }
    ),
    "histogram": _COMMON_CONTEXT_PRIMITIVES | frozenset({"bar", "reference_line"}),
    "forest": _COMMON_CONTEXT_PRIMITIVES | frozenset({"symbol", "line", "error_bar", "reference_line"}),
    "bubble": _COMMON_CONTEXT_PRIMITIVES | frozenset({"symbol", "reference_line"}),
    "diagnostic_curve": _COMMON_CONTEXT_PRIMITIVES | _LINE_PRIMITIVES,
    "confusion_matrix": _COMMON_CONTEXT_PRIMITIVES | frozenset({"heatmap_cell", "colorbar"}),
    "bland_altman": _COMMON_CONTEXT_PRIMITIVES | frozenset({"symbol", "line", "reference_line"}),
    "paired_trajectory": _COMMON_CONTEXT_PRIMITIVES
    | frozenset({"line", "symbol", "line_symbol", "reference_line"}),
    "calibration_curve": _COMMON_CONTEXT_PRIMITIVES | _LINE_PRIMITIVES,
    "decision_curve": _COMMON_CONTEXT_PRIMITIVES | _LINE_PRIMITIVES,
    "raincloud": _COMMON_CONTEXT_PRIMITIVES
    | frozenset(
        {
            "violin",
            "box",
            "symbol",
            "line",
            "error_bar",
            "reference_line",
        }
    ),
    "shap_summary": _COMMON_CONTEXT_PRIMITIVES | frozenset({"symbol", "reference_line", "colorbar"}),
    "grouped_box": _COMMON_CONTEXT_PRIMITIVES | frozenset({"box", "symbol", "error_bar", "reference_line"}),
    "pl": _COMMON_CONTEXT_PRIMITIVES | _LINE_PRIMITIVES,
    "uv_vis": _COMMON_CONTEXT_PRIMITIVES | _LINE_PRIMITIVES,
    "trajectory3d": _COMMON_CONTEXT_PRIMITIVES | frozenset({"line", "symbol", "line_symbol"}),
}

TEMPLATE_MODE_PRIMITIVE_EXTENSIONS: dict[tuple[str, str], frozenset[str]] = {
    ("xps", "fit_with_residual"): frozenset({"residual_curve"}),
    ("xrd", "rietveld_refinement"): frozenset(
        {
            "residual_curve",
            "phase_tick",
        }
    ),
    ("uv_vis", "uv_vis_with_tauc"): frozenset({"inset"}),
}


class ReferenceAdaptationError(ValueError):
    """Stable failure raised before an adaptation plan can reach a renderer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ReferenceAdaptationRoute(str, Enum):
    """The only two supported reference-figure planning routes."""

    TEMPLATE_ADAPTATION = "template_adaptation"
    CONTROLLED_COMPOSITION = "controlled_composition"


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _canonical_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalised_identifier(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _looks_like_absolute_path(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith(("\\\\", "//", "/")))


def _validate_reference_content(reference_payload: dict[str, Any]) -> None:
    """Reject identifiers that try to preserve non-graph or executable content."""

    inspected_values: list[object] = []
    inspected_values.extend(mark["id"] for mark in reference_payload["marks"])
    inspected_values.extend(mark["kind"] for mark in reference_payload["marks"])
    inspected_values.extend(encoding["semantic_role"] for encoding in reference_payload["encodings"])
    inspected_values.extend(item["id"] for item in reference_payload["text_roles"])
    inspected_values.extend(item["feature_role"] for item in reference_payload["essential_features"])
    inspected_values.extend(
        value
        for value in (
            reference_payload["style"]["palette_family"],
            reference_payload["style"]["palette_id"],
        )
        if value is not None
    )
    for raw_value in inspected_values:
        normalized = _normalised_identifier(raw_value)
        if any(token in normalized for token in _FORBIDDEN_REFERENCE_CONTENT):
            raise ReferenceAdaptationError(
                "reference_content_not_adaptable",
                "Logos, watermarks, author marks, and branded content cannot enter an adaptation plan.",
            )
        if any(token in normalized for token in _FORBIDDEN_EXECUTION_CONTENT):
            raise ReferenceAdaptationError(
                "reference_execution_content_forbidden",
                "Scripts, commands, and executable content cannot enter an adaptation plan.",
            )


def _semantic_item_index(
    contract: ConfirmedSemanticContract,
) -> dict[str, tuple[str, DataDisposition]]:
    result: dict[str, tuple[str, DataDisposition]] = {}
    for item in contract.proposal.data_items:
        result[item.item_id] = (item.semantic_role, item.disposition)
    for item in contract.proposal.derived_items:
        result[item.item_id] = (item.semantic_role, item.disposition)
    return result


def _resolve_bindings(
    reference_payload: dict[str, Any],
    semantic_items: dict[str, tuple[str, DataDisposition]],
    semantic_bindings: Mapping[str, str] | None,
) -> tuple[dict[str, str], set[str]]:
    binding_tokens = {
        str(encoding["data_binding"])
        for encoding in reference_payload["encodings"]
        if encoding["data_binding"] is not None
    }
    binding_tokens.update(
        str(text_role["binding_id"])
        for text_role in reference_payload["text_roles"]
        if text_role["binding_id"] is not None
    )
    if semantic_bindings is None:
        resolved = {token: token for token in binding_tokens}
    else:
        resolved = {str(key): str(value) for key, value in semantic_bindings.items()}
        extra = sorted(set(resolved) - binding_tokens)
        if extra:
            raise ReferenceAdaptationError(
                "reference_binding_unused",
                "Semantic bindings may contain only tokens used by the confirmed reference contract.",
            )
    missing = sorted(binding_tokens - set(resolved))
    if missing:
        raise ReferenceAdaptationError(
            "reference_binding_missing",
            "Every declared reference binding needs a confirmed semantic item.",
        )

    for semantic_item_id in resolved.values():
        if _looks_like_absolute_path(semantic_item_id):
            raise ReferenceAdaptationError(
                "reference_binding_path_forbidden",
                "An adaptation binding must not contain an absolute path.",
            )
        item = semantic_items.get(semantic_item_id)
        if item is None:
            raise ReferenceAdaptationError(
                "reference_binding_unknown",
                "A reference binding points to an item outside the confirmed semantic contract.",
            )
        _semantic_role, disposition = item
        if disposition not in _RENDERABLE_DISPOSITIONS:
            raise ReferenceAdaptationError(
                "reference_binding_not_renderable",
                "Support-only and retained data cannot become visible through a reference figure.",
            )
    return resolved, binding_tokens


def _required_encoding_ids(reference_payload: dict[str, Any]) -> set[str]:
    return {
        str(encoding_id)
        for feature in reference_payload["essential_features"]
        for encoding_id in feature["required_encoding_ids"]
    }


def _adapt_encodings(
    reference_payload: dict[str, Any],
    semantic_items: dict[str, tuple[str, DataDisposition]],
    resolved_bindings: dict[str, str],
) -> tuple[list[dict[str, object]], list[str]]:
    required = _required_encoding_ids(reference_payload)
    adapted: list[dict[str, object]] = []
    omitted: list[str] = []
    for encoding in reference_payload["encodings"]:
        encoding_id = str(encoding["id"])
        token = encoding["data_binding"]
        if token is None:
            if encoding_id in required:
                raise ReferenceAdaptationError(
                    "reference_essential_encoding_unbound",
                    "Every essential reference encoding must bind confirmed renderable data.",
                )
            omitted.append(encoding_id)
            continue
        semantic_item_id = resolved_bindings[str(token)]
        semantic_role, _disposition = semantic_items[semantic_item_id]
        adapted.append(
            {
                "encoding_id": encoding_id,
                "primitive_id": str(encoding["mark_id"]),
                "channel": str(encoding["channel"]),
                "reference_semantic_role": str(encoding["semantic_role"]),
                "semantic_item_id": semantic_item_id,
                "confirmed_semantic_role": semantic_role,
                "reference_confidence": float(encoding["confidence"]),
            }
        )
    return adapted, sorted(omitted)


def _adapt_text_roles(
    reference_payload: dict[str, Any],
    semantic_items: dict[str, tuple[str, DataDisposition]],
    resolved_bindings: dict[str, str],
) -> tuple[list[dict[str, object]], list[str]]:
    adapted: list[dict[str, object]] = []
    omitted: list[str] = []
    for text_role in reference_payload["text_roles"]:
        binding_token = text_role["binding_id"]
        if binding_token is None:
            omitted.append(str(text_role["id"]))
            continue
        semantic_item_id = resolved_bindings[str(binding_token)]
        semantic_role, _disposition = semantic_items[semantic_item_id]
        adapted.append(
            {
                "text_role_id": str(text_role["id"]),
                "panel_id": str(text_role["panel_id"]),
                "role": str(text_role["role"]),
                "semantic_item_id": semantic_item_id,
                "confirmed_semantic_role": semantic_role,
                "text_source": "confirmed_semantic_binding",
                "copy_policy": "user_data_or_confirmation_only",
            }
        )
    return adapted, sorted(omitted)


def _adapt_primitives(
    reference_payload: dict[str, Any],
    adapted_encodings: list[dict[str, object]],
    adapted_text_roles: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[str]]:
    encoding_ids_by_mark: dict[str, list[str]] = {}
    for encoding in adapted_encodings:
        encoding_ids_by_mark.setdefault(str(encoding["primitive_id"]), []).append(
            str(encoding["encoding_id"])
        )
    text_panels = {str(item["panel_id"]) for item in adapted_text_roles}
    primitives: list[dict[str, object]] = []
    omitted: list[str] = []
    for mark in reference_payload["marks"]:
        primitive = str(mark["kind"])
        if primitive not in ALLOWED_REFERENCE_PRIMITIVES:
            raise ReferenceAdaptationError(
                "reference_primitive_not_allowed",
                f"The reference mark {primitive!r} is not an allow-listed Origin primitive.",
            )
        mark_id = str(mark["id"])
        encoding_ids = sorted(encoding_ids_by_mark.get(mark_id, ()))
        structural = primitive in _STRUCTURAL_PRIMITIVES
        text_bound = primitive == "text_annotation" and str(mark["panel_id"]) in text_panels
        if not encoding_ids and not structural and not text_bound:
            if bool(mark["essential"]):
                raise ReferenceAdaptationError(
                    "reference_essential_primitive_unbound",
                    "Every essential reference primitive must bind confirmed data or text.",
                )
            omitted.append(mark_id)
            continue
        primitives.append(
            {
                "primitive_id": mark_id,
                "panel_id": str(mark["panel_id"]),
                "primitive": primitive,
                "evidence_role": str(mark["evidence_role"]),
                "essential": bool(mark["essential"]),
                "encoding_ids": encoding_ids,
                "reference_confidence": float(mark["confidence"]),
            }
        )
    return primitives, sorted(omitted)


def _template_primitive_gate(
    *,
    template_id: str,
    semantic_domain_family: str,
    semantic_domain_mode: str,
    declared_marks: list[dict[str, object]],
) -> tuple[set[str], list[dict[str, str]], dict[str, object]]:
    """Reject chart-family changes disguised as reference-style adaptation."""

    base = TEMPLATE_PRIMITIVE_COMPATIBILITY.get(template_id)
    if base is None:
        raise ReferenceAdaptationError(
            "reference_template_unsupported",
            "The selected identifier is not a public template with a declared reference-primitive contract.",
        )
    if semantic_domain_family != template_id:
        raise ReferenceAdaptationError(
            "reference_template_semantic_domain_mismatch",
            "The selected template must match the confirmed semantic domain.",
        )
    compatible = base | TEMPLATE_MODE_PRIMITIVE_EXTENSIONS.get(
        (template_id, semantic_domain_mode),
        frozenset(),
    )

    rejected: list[dict[str, str]] = []
    rejected_ids: set[str] = set()
    for mark in declared_marks:
        primitive_kind = str(mark["kind"])
        if primitive_kind in compatible:
            continue
        primitive_id = str(mark["id"])
        if bool(mark["essential"]):
            raise ReferenceAdaptationError(
                "reference_essential_primitive_incompatible",
                (
                    f"Essential primitive {primitive_kind!r} is incompatible with "
                    f"template {template_id!r} in semantic mode "
                    f"{semantic_domain_mode!r}."
                ),
            )
        rejected_ids.add(primitive_id)
        rejected.append(
            {
                "primitive_id": primitive_id,
                "primitive": primitive_kind,
                "reason_code": "template_primitive_incompatible",
            }
        )

    compatibility = {
        "enforced": True,
        "semantic_domain_family": semantic_domain_family,
        "semantic_domain_mode": semantic_domain_mode,
        "compatible_primitives": sorted(compatible),
    }
    return (
        rejected_ids,
        sorted(rejected, key=lambda item: item["primitive_id"]),
        compatibility,
    )


def _capability_gate(
    route: ReferenceAdaptationRoute,
    template_id: str | None,
    primitives: list[dict[str, object]],
) -> dict[str, object]:
    required: set[str] = set()
    for primitive in primitives:
        required.update(_PRIMITIVE_CAPABILITIES.get(str(primitive["primitive"]), ()))
    return {
        "template_profile_id": (
            template_id if route is ReferenceAdaptationRoute.TEMPLATE_ADAPTATION else None
        ),
        "template_profile_required": route is ReferenceAdaptationRoute.TEMPLATE_ADAPTATION,
        "additional_required_capabilities": sorted(required),
        "support_status": (
            "capability_gated" if route is ReferenceAdaptationRoute.TEMPLATE_ADAPTATION else "experimental"
        ),
    }


@dataclass(frozen=True)
class ReferenceAdaptationPlan:
    """Canonical, path-free plan ready for a future capability-gated renderer."""

    _canonical_payload: str
    plan_hash: str

    @property
    def route(self) -> ReferenceAdaptationRoute:
        return ReferenceAdaptationRoute(self.to_dict()["route"])

    @property
    def template_id(self) -> str | None:
        value = self.to_dict()["template_id"]
        return str(value) if value is not None else None

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self._canonical_payload)
        payload["plan_hash"] = self.plan_hash
        return payload


def build_reference_adaptation_plan(
    semantic_contract: ConfirmedSemanticContract,
    reference_spec: ReferenceFigureSpec,
    *,
    route: ReferenceAdaptationRoute | str,
    template_id: str | None = None,
    semantic_bindings: Mapping[str, str] | None = None,
) -> ReferenceAdaptationPlan:
    """Build a deterministic adaptation plan without drawing or code generation."""

    if not isinstance(semantic_contract, ConfirmedSemanticContract):
        raise ReferenceAdaptationError(
            "semantic_confirmation_required",
            "Reference adaptation requires a ConfirmedSemanticContract.",
        )
    try:
        semantic_contract.validate()
    except SemanticContractError as exc:
        raise ReferenceAdaptationError(
            "semantic_contract_invalid",
            "The confirmed semantic contract is not valid.",
        ) from exc
    if not isinstance(reference_spec, ReferenceFigureSpec):
        raise ReferenceAdaptationError(
            "reference_confirmation_required",
            "Reference adaptation requires a confirmed ReferenceFigureSpec.",
        )
    try:
        reference_spec.require_renderable()
    except ReferenceFigureError as exc:
        raise ReferenceAdaptationError(exc.code, str(exc)) from exc

    try:
        selected_route = ReferenceAdaptationRoute(route)
    except ValueError as exc:
        raise ReferenceAdaptationError(
            "reference_route_invalid",
            "Select template_adaptation or controlled_composition.",
        ) from exc
    if selected_route is ReferenceAdaptationRoute.TEMPLATE_ADAPTATION:
        if not isinstance(template_id, str) or not _SAFE_TEMPLATE_ID.fullmatch(template_id):
            raise ReferenceAdaptationError(
                "reference_template_required",
                "Template adaptation requires one stable public template identifier.",
            )
    elif template_id is not None:
        raise ReferenceAdaptationError(
            "reference_template_forbidden",
            "Controlled composition must not masquerade as a registered template.",
        )

    reference_payload = reference_spec.to_dict()
    _validate_reference_content(reference_payload)
    semantic_items = _semantic_item_index(semantic_contract)
    resolved_bindings, _binding_tokens = _resolve_bindings(
        reference_payload,
        semantic_items,
        semantic_bindings,
    )
    encodings, omitted_encodings = _adapt_encodings(
        reference_payload,
        semantic_items,
        resolved_bindings,
    )
    text_roles, omitted_text_roles = _adapt_text_roles(
        reference_payload,
        semantic_items,
        resolved_bindings,
    )
    semantic_domain_family = semantic_contract.proposal.domain_family
    semantic_domain_mode = semantic_contract.proposal.domain_mode
    rejected_primitive_ids: set[str] = set()
    rejected_primitives: list[dict[str, str]] = []
    if selected_route is ReferenceAdaptationRoute.TEMPLATE_ADAPTATION:
        if template_id is None:
            raise ReferenceAdaptationError(
                "reference_template_required",
                "Template adaptation requires one stable public template identifier.",
            )
        (
            rejected_primitive_ids,
            rejected_primitives,
            template_compatibility,
        ) = _template_primitive_gate(
            template_id=template_id,
            semantic_domain_family=semantic_domain_family,
            semantic_domain_mode=semantic_domain_mode,
            declared_marks=reference_payload["marks"],
        )
    else:
        template_compatibility = {
            "enforced": False,
            "semantic_domain_family": semantic_domain_family,
            "semantic_domain_mode": semantic_domain_mode,
            "compatible_primitives": sorted(ALLOWED_REFERENCE_PRIMITIVES),
        }
    primitives, omitted_primitives = _adapt_primitives(
        reference_payload,
        encodings,
        text_roles,
    )
    rejected_encoding_ids = sorted(
        str(encoding["encoding_id"])
        for encoding in encodings
        if str(encoding["primitive_id"]) in rejected_primitive_ids
    )
    primitives = [
        primitive for primitive in primitives if str(primitive["primitive_id"]) not in rejected_primitive_ids
    ]
    encodings = [
        encoding for encoding in encodings if str(encoding["primitive_id"]) not in rejected_primitive_ids
    ]

    included_primitive_ids = {str(item["primitive_id"]) for item in primitives}
    included_encoding_ids = {str(item["encoding_id"]) for item in encodings}
    essential_features: list[dict[str, object]] = []
    for feature in reference_payload["essential_features"]:
        mark_ids = [str(item) for item in feature["mark_ids"]]
        encoding_ids = [str(item) for item in feature["required_encoding_ids"]]
        if not set(mark_ids).issubset(included_primitive_ids) or not set(encoding_ids).issubset(
            included_encoding_ids
        ):
            raise ReferenceAdaptationError(
                "reference_essential_feature_unbound",
                "Every essential reference feature must survive semantic adaptation.",
            )
        essential_features.append(
            {
                "feature_id": str(feature["id"]),
                "feature_role": str(feature["feature_role"]),
                "primitive_ids": mark_ids,
                "encoding_ids": encoding_ids,
            }
        )

    payload: dict[str, Any] = {
        "plan_version": REFERENCE_ADAPTATION_PLAN_VERSION,
        "route": selected_route.value,
        "template_id": template_id,
        "semantic_contract_hash": semantic_contract.contract_hash,
        "reference_contract_hash": reference_spec.contract_sha256,
        "layout": reference_payload["layout"],
        "primitives": primitives,
        "encodings": encodings,
        "text_roles": text_roles,
        "essential_features": essential_features,
        "style_tokens": reference_payload["style"],
        "template_compatibility": template_compatibility,
        "omitted_reference_elements": {
            "primitive_ids": sorted(
                {
                    *omitted_primitives,
                    *(item["primitive_id"] for item in rejected_primitives),
                }
            ),
            "encoding_ids": sorted(
                {
                    *omitted_encodings,
                    *rejected_encoding_ids,
                }
            ),
            "text_role_ids": omitted_text_roles,
            "rejected_primitives": rejected_primitives,
        },
        "origin_capability_gate": _capability_gate(
            selected_route,
            template_id,
            primitives,
        ),
        "safety_contract": {
            "reference_grammar_only": True,
            "source_values_embedded": False,
            "reference_pixels_embedded": False,
            "untrusted_reference_content_embedded": False,
            "executable_content_allowed": False,
            "visible_items_require_renderable_semantics": True,
        },
    }
    serialized = _canonical_json(payload)
    if any(_looks_like_absolute_path(value) for value in _walk_strings(json.loads(serialized))):
        raise ReferenceAdaptationError(
            "reference_plan_path_forbidden",
            "A reference adaptation plan must not contain absolute paths.",
        )
    return ReferenceAdaptationPlan(
        _canonical_payload=serialized,
        plan_hash=_canonical_hash(payload),
    )


def _walk_strings(value: object) -> list[str]:
    strings: list[str] = []
    if isinstance(value, Mapping):
        for child in value.values():
            strings.extend(_walk_strings(child))
    elif isinstance(value, list):
        for child in value:
            strings.extend(_walk_strings(child))
    elif isinstance(value, str):
        strings.append(value)
    return strings


__all__ = [
    "ALLOWED_REFERENCE_PRIMITIVES",
    "REFERENCE_ADAPTATION_PLAN_VERSION",
    "TEMPLATE_MODE_PRIMITIVE_EXTENSIONS",
    "TEMPLATE_PRIMITIVE_COMPATIBILITY",
    "ReferenceAdaptationError",
    "ReferenceAdaptationPlan",
    "ReferenceAdaptationRoute",
    "build_reference_adaptation_plan",
]
