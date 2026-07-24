"""Serializable semantic intermediate representation for scientific figures.

The objects in this module intentionally contain no source path, timestamp, or
Origin state.  They describe only source-bound scientific meaning and figure
elements, so their hashes are reproducible across machines and sessions.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None

SEMANTIC_PROPOSAL_VERSION = "1.0"
SEMANTIC_CONTRACT_VERSION = "1.0"

ALLOWED_DERIVED_OPERATIONS = frozenset(
    {
        "identity_copy",
        "sum",
        "difference",
        "negate",
        "scale_by_constant",
        "offset_by_constant",
        "mask_by_column",
        "fraction_of_row_total",
    }
)


class SemanticContractError(ValueError):
    """Stable validation failure raised before a render plan can be frozen."""

    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


class DataDisposition(str, Enum):
    """How a source or derived data item participates in the figure."""

    RENDER_PRIMARY = "render_primary"
    RENDER_SECONDARY = "render_secondary"
    SUPPORT_ONLY = "support_only"
    RETAIN_NOT_RENDER = "retain_not_render"
    UNCERTAIN = "uncertain"


def _canonical_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SemanticContractError(
            "semantic_text_required",
            f"{field} must be a non-empty string.",
            field=field,
        )


def _require_unique(values: tuple[str, ...], field: str) -> None:
    if len(values) != len(set(values)):
        raise SemanticContractError(
            "semantic_values_not_unique",
            f"{field} contains duplicate values.",
            field=field,
        )


def _require_confidence(value: float, field: str) -> None:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise SemanticContractError(
            "semantic_confidence_invalid",
            f"{field} must be a finite number.",
            field=field,
        )
    if not 0.0 <= float(value) <= 1.0:
        raise SemanticContractError(
            "semantic_confidence_invalid",
            f"{field} must be between 0 and 1.",
            field=field,
        )


def _require_sha256(value: str) -> None:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise SemanticContractError(
            "semantic_source_hash_invalid",
            "source_sha256 must contain exactly 64 hexadecimal characters.",
        )


def _looks_like_absolute_path(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith(("\\\\", "//", "/")))


def _require_stable_text(value: str, field: str) -> None:
    _require_text(value, field)
    if _looks_like_absolute_path(value):
        raise SemanticContractError(
            "semantic_unstable_path",
            f"{field} must not contain an absolute path.",
            field=field,
        )


def _normalise_strings(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(str(value) for value in values)


def _normalise_parameters(
    values: Mapping[str, JsonScalar] | Iterable[tuple[str, JsonScalar]],
) -> tuple[tuple[str, JsonScalar], ...]:
    items = values.items() if isinstance(values, Mapping) else values
    return tuple(sorted(((str(key), value) for key, value in items), key=lambda item: item[0]))


def _normalise_resolutions(
    values: Mapping[str, str] | Iterable[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    items = values.items() if isinstance(values, Mapping) else values
    return tuple(sorted(((str(key), str(value)) for key, value in items), key=lambda item: item[0]))


def _payload_error(
    message: str,
    *,
    field: str,
    code: str = "semantic_payload_schema_invalid",
    **details: object,
) -> SemanticContractError:
    return SemanticContractError(code, message, field=field, **details)


def _strict_object(
    value: object,
    *,
    field: str,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _payload_error(
            f"{field} must be a JSON object.",
            field=field,
        )
    if any(not isinstance(key, str) for key in value):
        raise _payload_error(
            f"{field} must use string field names.",
            field=field,
        )
    keys = set(value)
    unknown = sorted(keys - required - optional)
    missing = sorted(required - keys)
    if unknown:
        raise _payload_error(
            f"{field} contains unknown fields.",
            field=field,
            code="semantic_payload_unknown_fields",
            unknown_fields=unknown,
        )
    if missing:
        raise _payload_error(
            f"{field} is missing required fields.",
            field=field,
            missing_fields=missing,
        )
    return value


def _strict_string_key_object(
    value: object,
    *,
    field: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _payload_error(
            f"{field} must be a JSON object.",
            field=field,
        )
    if any(not isinstance(key, str) for key in value):
        raise _payload_error(
            f"{field} must use string field names.",
            field=field,
        )
    return value


def _strict_list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise _payload_error(
            f"{field} must be a JSON array.",
            field=field,
        )
    return value


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise _payload_error(
            f"{field} must be a string.",
            field=field,
        )
    return value


def _strict_optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _strict_text(value, field)


def _strict_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise _payload_error(
            f"{field} must be a boolean.",
            field=field,
        )
    return value


def _strict_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _payload_error(
            f"{field} must be a finite JSON number.",
            field=field,
        )
    number = float(value)
    if not math.isfinite(number):
        raise _payload_error(
            f"{field} must be a finite JSON number.",
            field=field,
        )
    return number


def _strict_string_list(value: object, field: str) -> tuple[str, ...]:
    items = _strict_list(value, field)
    return tuple(
        _strict_text(item, f"{field}[{index}]")
        for index, item in enumerate(items)
    )


def _strict_json_scalar(value: object, field: str) -> JsonScalar:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise _payload_error(
        f"{field} must be a finite JSON scalar.",
        field=field,
    )


def _strict_disposition(value: object, field: str) -> DataDisposition:
    text = _strict_text(value, field)
    try:
        return DataDisposition(text)
    except ValueError as exc:
        raise _payload_error(
            f"{field} contains an unknown disposition.",
            field=field,
            code="semantic_payload_value_invalid",
            value=text,
        ) from exc


def _reject_absolute_paths(value: object, location: str = "$") -> None:
    if isinstance(value, str):
        if _looks_like_absolute_path(value):
            raise SemanticContractError(
                "semantic_unstable_path",
                "Semantic payloads must not contain absolute paths.",
                field=location,
            )
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str) and _looks_like_absolute_path(key):
                raise SemanticContractError(
                    "semantic_unstable_path",
                    "Semantic payloads must not contain absolute paths.",
                    field=f"{location}.<key>",
                )
            _reject_absolute_paths(child, f"{location}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _reject_absolute_paths(child, f"{location}[{index}]")


@dataclass(frozen=True)
class SemanticDataItem:
    """One and only one semantic classification for a source column."""

    item_id: str
    source_column: str
    semantic_role: str
    disposition: DataDisposition
    confidence: float
    evidence_codes: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "disposition", DataDisposition(self.disposition))
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "evidence_codes", _normalise_strings(self.evidence_codes))
        object.__setattr__(self, "alternatives", _normalise_strings(self.alternatives))

    def validate(self) -> None:
        _require_text(self.item_id, "item_id")
        _require_text(self.source_column, "source_column")
        _require_text(self.semantic_role, "semantic_role")
        _require_confidence(self.confidence, "confidence")
        _require_unique(self.evidence_codes, "evidence_codes")
        _require_unique(self.alternatives, "alternatives")
        for value in (*self.evidence_codes, *self.alternatives):
            _require_stable_text(value, "semantic item evidence")

    def to_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "item_type": "source_column",
            "source_column": self.source_column,
            "semantic_role": self.semantic_role,
            "disposition": self.disposition.value,
            "confidence": self.confidence,
            "evidence_codes": list(self.evidence_codes),
            "alternatives": list(self.alternatives),
        }


@dataclass(frozen=True)
class DerivedDataItem:
    """A proposed helper with explicit lineage and an allow-listed operation."""

    item_id: str
    semantic_role: str
    disposition: DataDisposition
    operation_id: str
    input_item_ids: tuple[str, ...]
    confidence: float
    parameters: tuple[tuple[str, JsonScalar], ...] = ()
    evidence_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "disposition", DataDisposition(self.disposition))
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "input_item_ids", _normalise_strings(self.input_item_ids))
        object.__setattr__(self, "parameters", _normalise_parameters(self.parameters))
        object.__setattr__(self, "evidence_codes", _normalise_strings(self.evidence_codes))

    def validate(self) -> None:
        _require_text(self.item_id, "derived item_id")
        _require_text(self.semantic_role, "derived semantic_role")
        _require_text(self.operation_id, "derived operation_id")
        _require_confidence(self.confidence, "derived confidence")
        if self.operation_id not in ALLOWED_DERIVED_OPERATIONS:
            raise SemanticContractError(
                "semantic_derived_operation_not_allowed",
                f"Derived operation {self.operation_id!r} is not allow-listed.",
                operation_id=self.operation_id,
            )
        if not self.input_item_ids:
            raise SemanticContractError(
                "semantic_derived_lineage_missing",
                f"Derived item {self.item_id!r} has no lineage inputs.",
                item_id=self.item_id,
            )
        _require_unique(self.input_item_ids, "derived input_item_ids")
        if self.item_id in self.input_item_ids:
            raise SemanticContractError(
                "semantic_derived_cycle",
                f"Derived item {self.item_id!r} depends on itself.",
                item_id=self.item_id,
            )
        if self.disposition is DataDisposition.RETAIN_NOT_RENDER:
            raise SemanticContractError(
                "semantic_derived_disposition_invalid",
                "A generated helper cannot be classified as retained source-only data.",
                item_id=self.item_id,
            )
        _require_unique(tuple(key for key, _value in self.parameters), "derived parameter keys")
        _require_unique(self.evidence_codes, "derived evidence_codes")
        for key, value in self.parameters:
            _require_stable_text(key, "derived parameter key")
            if isinstance(value, float) and not math.isfinite(value):
                raise SemanticContractError(
                    "semantic_derived_parameter_invalid",
                    f"Derived parameter {key!r} must be finite.",
                    item_id=self.item_id,
                    parameter=key,
                )
            if isinstance(value, str) and _looks_like_absolute_path(value):
                raise SemanticContractError(
                    "semantic_unstable_path",
                    "Derived parameters must not contain absolute paths.",
                    item_id=self.item_id,
                    parameter=key,
                )
        for value in self.evidence_codes:
            _require_stable_text(value, "derived evidence code")

    def to_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "item_type": "derived",
            "semantic_role": self.semantic_role,
            "disposition": self.disposition.value,
            "operation_id": self.operation_id,
            "input_item_ids": list(self.input_item_ids),
            "confidence": self.confidence,
            "parameters": dict(self.parameters),
            "evidence_codes": list(self.evidence_codes),
            "explicit_approval_required": True,
        }


@dataclass(frozen=True)
class FigureElement:
    """A proposed visible figure element and its data bindings."""

    element_id: str
    element_kind: str
    data_item_ids: tuple[str, ...]
    required: bool
    visible_by_default: bool = True
    axis: str | None = None
    legend_label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_item_ids", _normalise_strings(self.data_item_ids))

    def validate(self) -> None:
        _require_text(self.element_id, "element_id")
        _require_text(self.element_kind, "element_kind")
        _require_unique(self.data_item_ids, "figure element data_item_ids")
        if self.required and not self.data_item_ids:
            raise SemanticContractError(
                "semantic_required_element_unbound",
                f"Required figure element {self.element_id!r} has no data binding.",
                element_id=self.element_id,
            )
        if self.axis is not None:
            _require_stable_text(self.axis, "figure element axis")
        if self.legend_label is not None:
            _require_text(self.legend_label, "figure element legend_label")

    def to_dict(self) -> dict[str, object]:
        return {
            "element_id": self.element_id,
            "element_kind": self.element_kind,
            "data_item_ids": list(self.data_item_ids),
            "required": self.required,
            "visible_by_default": self.visible_by_default,
            "axis": self.axis,
            "legend_label": self.legend_label,
        }


@dataclass(frozen=True)
class SemanticAmbiguity:
    """A focused scientific question that may block confirmation."""

    ambiguity_id: str
    code: str
    question_zh: str
    item_ids: tuple[str, ...] = ()
    options: tuple[str, ...] = ()
    blocking: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_ids", _normalise_strings(self.item_ids))
        object.__setattr__(self, "options", _normalise_strings(self.options))

    def validate(self) -> None:
        _require_text(self.ambiguity_id, "ambiguity_id")
        _require_text(self.code, "ambiguity code")
        _require_text(self.question_zh, "ambiguity question_zh")
        _require_unique(self.item_ids, "ambiguity item_ids")
        _require_unique(self.options, "ambiguity options")
        for value in self.options:
            _require_stable_text(value, "ambiguity option")

    def to_dict(self) -> dict[str, object]:
        return {
            "ambiguity_id": self.ambiguity_id,
            "code": self.code,
            "question_zh": self.question_zh,
            "item_ids": list(self.item_ids),
            "options": list(self.options),
            "blocking": self.blocking,
        }


def _parse_source_data_item(value: object, field: str) -> SemanticDataItem:
    payload = _strict_object(
        value,
        field=field,
        required=frozenset(
            {
                "item_id",
                "item_type",
                "source_column",
                "semantic_role",
                "disposition",
                "confidence",
                "evidence_codes",
                "alternatives",
            }
        ),
    )
    item_type = _strict_text(payload["item_type"], f"{field}.item_type")
    if item_type != "source_column":
        raise _payload_error(
            f"{field}.item_type must be 'source_column'.",
            field=f"{field}.item_type",
            code="semantic_payload_value_invalid",
        )
    return SemanticDataItem(
        item_id=_strict_text(payload["item_id"], f"{field}.item_id"),
        source_column=_strict_text(
            payload["source_column"],
            f"{field}.source_column",
        ),
        semantic_role=_strict_text(
            payload["semantic_role"],
            f"{field}.semantic_role",
        ),
        disposition=_strict_disposition(
            payload["disposition"],
            f"{field}.disposition",
        ),
        confidence=_strict_number(
            payload["confidence"],
            f"{field}.confidence",
        ),
        evidence_codes=_strict_string_list(
            payload["evidence_codes"],
            f"{field}.evidence_codes",
        ),
        alternatives=_strict_string_list(
            payload["alternatives"],
            f"{field}.alternatives",
        ),
    )


def _parse_derived_data_item(value: object, field: str) -> DerivedDataItem:
    payload = _strict_object(
        value,
        field=field,
        required=frozenset(
            {
                "item_id",
                "item_type",
                "semantic_role",
                "disposition",
                "operation_id",
                "input_item_ids",
                "confidence",
                "parameters",
                "evidence_codes",
                "explicit_approval_required",
            }
        ),
    )
    item_type = _strict_text(payload["item_type"], f"{field}.item_type")
    if item_type != "derived":
        raise _payload_error(
            f"{field}.item_type must be 'derived'.",
            field=f"{field}.item_type",
            code="semantic_payload_value_invalid",
        )
    approval_required = _strict_bool(
        payload["explicit_approval_required"],
        f"{field}.explicit_approval_required",
    )
    if not approval_required:
        raise _payload_error(
            f"{field}.explicit_approval_required must be true.",
            field=f"{field}.explicit_approval_required",
            code="semantic_payload_value_invalid",
        )
    parameters = _strict_string_key_object(
        payload["parameters"],
        field=f"{field}.parameters",
    )
    parsed_parameters = tuple(
        (
            key,
            _strict_json_scalar(
                parameter,
                f"{field}.parameters.{key}",
            ),
        )
        for key, parameter in parameters.items()
    )
    return DerivedDataItem(
        item_id=_strict_text(payload["item_id"], f"{field}.item_id"),
        semantic_role=_strict_text(
            payload["semantic_role"],
            f"{field}.semantic_role",
        ),
        disposition=_strict_disposition(
            payload["disposition"],
            f"{field}.disposition",
        ),
        operation_id=_strict_text(
            payload["operation_id"],
            f"{field}.operation_id",
        ),
        input_item_ids=_strict_string_list(
            payload["input_item_ids"],
            f"{field}.input_item_ids",
        ),
        confidence=_strict_number(
            payload["confidence"],
            f"{field}.confidence",
        ),
        parameters=parsed_parameters,
        evidence_codes=_strict_string_list(
            payload["evidence_codes"],
            f"{field}.evidence_codes",
        ),
    )


def _parse_figure_element(value: object, field: str) -> FigureElement:
    payload = _strict_object(
        value,
        field=field,
        required=frozenset(
            {
                "element_id",
                "element_kind",
                "data_item_ids",
                "required",
                "visible_by_default",
                "axis",
                "legend_label",
            }
        ),
    )
    return FigureElement(
        element_id=_strict_text(
            payload["element_id"],
            f"{field}.element_id",
        ),
        element_kind=_strict_text(
            payload["element_kind"],
            f"{field}.element_kind",
        ),
        data_item_ids=_strict_string_list(
            payload["data_item_ids"],
            f"{field}.data_item_ids",
        ),
        required=_strict_bool(payload["required"], f"{field}.required"),
        visible_by_default=_strict_bool(
            payload["visible_by_default"],
            f"{field}.visible_by_default",
        ),
        axis=_strict_optional_text(payload["axis"], f"{field}.axis"),
        legend_label=_strict_optional_text(
            payload["legend_label"],
            f"{field}.legend_label",
        ),
    )


def _parse_ambiguity(value: object, field: str) -> SemanticAmbiguity:
    payload = _strict_object(
        value,
        field=field,
        required=frozenset(
            {
                "ambiguity_id",
                "code",
                "question_zh",
                "item_ids",
                "options",
                "blocking",
            }
        ),
    )
    return SemanticAmbiguity(
        ambiguity_id=_strict_text(
            payload["ambiguity_id"],
            f"{field}.ambiguity_id",
        ),
        code=_strict_text(payload["code"], f"{field}.code"),
        question_zh=_strict_text(
            payload["question_zh"],
            f"{field}.question_zh",
        ),
        item_ids=_strict_string_list(
            payload["item_ids"],
            f"{field}.item_ids",
        ),
        options=_strict_string_list(
            payload["options"],
            f"{field}.options",
        ),
        blocking=_strict_bool(payload["blocking"], f"{field}.blocking"),
    )


def _validate_derived_graph(
    source_item_ids: set[str],
    derived_items: tuple[DerivedDataItem, ...],
) -> None:
    derived_by_id = {item.item_id: item for item in derived_items}
    known_ids = source_item_ids | set(derived_by_id)
    for item in derived_items:
        unknown = sorted(set(item.input_item_ids) - known_ids)
        if unknown:
            raise SemanticContractError(
                "semantic_derived_lineage_unknown",
                f"Derived item {item.item_id!r} references unknown inputs.",
                item_id=item.item_id,
                unknown_item_ids=unknown,
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(item_id: str) -> None:
        if item_id in visited:
            return
        if item_id in visiting:
            raise SemanticContractError(
                "semantic_derived_cycle",
                "Derived data lineage contains a cycle.",
                item_id=item_id,
            )
        visiting.add(item_id)
        for dependency in derived_by_id[item_id].input_item_ids:
            if dependency in derived_by_id:
                visit(dependency)
        visiting.remove(item_id)
        visited.add(item_id)

    for item_id in derived_by_id:
        visit(item_id)


@dataclass(frozen=True)
class SemanticProposal:
    """A source-bound interpretation that still requires human confirmation."""

    source_sha256: str
    source_columns: tuple[str, ...]
    domain_family: str
    domain_mode: str
    domain_confidence: float
    data_items: tuple[SemanticDataItem, ...]
    derived_items: tuple[DerivedDataItem, ...] = ()
    figure_elements: tuple[FigureElement, ...] = ()
    ambiguities: tuple[SemanticAmbiguity, ...] = ()
    source_adapter_hint: str | None = None
    proposal_version: str = SEMANTIC_PROPOSAL_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_columns", _normalise_strings(self.source_columns))
        object.__setattr__(self, "data_items", tuple(self.data_items))
        object.__setattr__(self, "derived_items", tuple(self.derived_items))
        object.__setattr__(self, "figure_elements", tuple(self.figure_elements))
        object.__setattr__(self, "ambiguities", tuple(self.ambiguities))
        object.__setattr__(self, "domain_confidence", float(self.domain_confidence))

    def validate(self) -> None:
        if self.proposal_version != SEMANTIC_PROPOSAL_VERSION:
            raise SemanticContractError(
                "semantic_proposal_version_unsupported",
                f"Unsupported semantic proposal version: {self.proposal_version!r}.",
            )
        _require_sha256(self.source_sha256)
        if not self.source_columns:
            raise SemanticContractError(
                "semantic_source_columns_missing",
                "A semantic proposal needs at least one source column.",
            )
        _require_unique(self.source_columns, "source_columns")
        for column in self.source_columns:
            _require_text(column, "source column")
        _require_text(self.domain_family, "domain_family")
        _require_text(self.domain_mode, "domain_mode")
        _require_confidence(self.domain_confidence, "domain_confidence")
        if self.source_adapter_hint is not None:
            _require_stable_text(self.source_adapter_hint, "source_adapter_hint")

        for item in self.data_items:
            item.validate()
        item_ids = tuple(item.item_id for item in self.data_items)
        _require_unique(item_ids, "source data item ids")
        classified_columns = tuple(item.source_column for item in self.data_items)
        duplicates = sorted(
            column for column in set(classified_columns) if classified_columns.count(column) > 1
        )
        missing = sorted(set(self.source_columns) - set(classified_columns))
        unknown = sorted(set(classified_columns) - set(self.source_columns))
        if duplicates or missing or unknown:
            raise SemanticContractError(
                "semantic_source_classification_incomplete",
                "Every source column must be classified exactly once.",
                duplicate_columns=duplicates,
                missing_columns=missing,
                unknown_columns=unknown,
            )

        for item in self.derived_items:
            item.validate()
        derived_ids = tuple(item.item_id for item in self.derived_items)
        _require_unique(derived_ids, "derived item ids")
        overlap = sorted(set(item_ids) & set(derived_ids))
        if overlap:
            raise SemanticContractError(
                "semantic_item_id_conflict",
                "Source and derived items must have different item IDs.",
                item_ids=overlap,
            )
        source_item_ids = set(item_ids)
        _validate_derived_graph(source_item_ids, self.derived_items)
        known_item_ids = source_item_ids | set(derived_ids)

        for element in self.figure_elements:
            element.validate()
            unknown_bindings = sorted(set(element.data_item_ids) - known_item_ids)
            if unknown_bindings:
                raise SemanticContractError(
                    "semantic_figure_binding_unknown",
                    f"Figure element {element.element_id!r} references unknown data items.",
                    element_id=element.element_id,
                    unknown_item_ids=unknown_bindings,
                )
        _require_unique(
            tuple(element.element_id for element in self.figure_elements),
            "figure element ids",
        )

        for ambiguity in self.ambiguities:
            ambiguity.validate()
            unknown_items = sorted(set(ambiguity.item_ids) - known_item_ids)
            if unknown_items:
                raise SemanticContractError(
                    "semantic_ambiguity_item_unknown",
                    f"Ambiguity {ambiguity.ambiguity_id!r} references unknown data items.",
                    ambiguity_id=ambiguity.ambiguity_id,
                    unknown_item_ids=unknown_items,
                )
        _require_unique(
            tuple(ambiguity.ambiguity_id for ambiguity in self.ambiguities),
            "ambiguity ids",
        )

    def _payload(self) -> dict[str, object]:
        return {
            "proposal_version": self.proposal_version,
            "source_sha256": self.source_sha256.lower(),
            "source_columns": list(self.source_columns),
            "domain": {
                "family": self.domain_family,
                "mode": self.domain_mode,
                "confidence": self.domain_confidence,
                "source_adapter_hint": self.source_adapter_hint,
            },
            "data_items": [item.to_dict() for item in self.data_items],
            "derived_items": [item.to_dict() for item in self.derived_items],
            "figure_elements": [element.to_dict() for element in self.figure_elements],
            "ambiguities": [ambiguity.to_dict() for ambiguity in self.ambiguities],
        }

    @property
    def proposal_hash(self) -> str:
        return _canonical_hash(self._payload())

    def stable_hash(self) -> str:
        return self.proposal_hash

    def to_dict(self) -> dict[str, object]:
        payload = self._payload()
        payload["proposal_hash"] = self.proposal_hash
        return payload

    def confirm(
        self,
        *,
        user_confirmed: bool,
        approved_derived_item_ids: Iterable[str] = (),
        resolved_ambiguities: Mapping[str, str] | Iterable[tuple[str, str]] = (),
    ) -> ConfirmedSemanticContract:
        """Freeze a confirmed contract after applying every hard gate."""

        self.validate()
        if not user_confirmed:
            raise SemanticContractError(
                "semantic_user_confirmation_required",
                "The semantic interpretation needs explicit user confirmation.",
            )
        approval_ids = _normalise_strings(approved_derived_item_ids)
        resolutions = _normalise_resolutions(resolved_ambiguities)
        contract = ConfirmedSemanticContract(
            proposal=self,
            approved_derived_item_ids=approval_ids,
            resolved_ambiguities=resolutions,
        )
        contract.validate()
        return contract


def _validate_confirmation(
    proposal: SemanticProposal,
    approved_derived_item_ids: tuple[str, ...],
    resolved_ambiguities: tuple[tuple[str, str], ...],
) -> None:
    uncertain = [
        item.item_id
        for item in (*proposal.data_items, *proposal.derived_items)
        if item.disposition is DataDisposition.UNCERTAIN
    ]
    if uncertain:
        raise SemanticContractError(
            "semantic_uncertain_items",
            "Uncertain data items must be resolved before confirmation.",
            item_ids=uncertain,
        )

    _require_unique(approved_derived_item_ids, "approved derived item ids")
    known_derived = {item.item_id for item in proposal.derived_items}
    approved = set(approved_derived_item_ids)
    unknown_approvals = sorted(approved - known_derived)
    missing_approvals = sorted(known_derived - approved)
    if unknown_approvals:
        raise SemanticContractError(
            "semantic_derived_approval_unknown",
            "Approval references unknown derived data items.",
            item_ids=unknown_approvals,
        )
    if missing_approvals:
        raise SemanticContractError(
            "semantic_derived_approval_required",
            "Every derived data item needs explicit approval.",
            item_ids=missing_approvals,
        )

    resolution_map = dict(resolved_ambiguities)
    if len(resolution_map) != len(resolved_ambiguities):
        raise SemanticContractError(
            "semantic_ambiguity_resolution_duplicate",
            "Each ambiguity may be resolved only once.",
        )
    known_ambiguities = {item.ambiguity_id: item for item in proposal.ambiguities}
    unknown_resolutions = sorted(set(resolution_map) - set(known_ambiguities))
    if unknown_resolutions:
        raise SemanticContractError(
            "semantic_ambiguity_resolution_unknown",
            "A resolution references an unknown ambiguity.",
            ambiguity_ids=unknown_resolutions,
        )
    missing_resolutions = sorted(
        item.ambiguity_id
        for item in proposal.ambiguities
        if item.blocking and not resolution_map.get(item.ambiguity_id, "").strip()
    )
    if missing_resolutions:
        raise SemanticContractError(
            "semantic_ambiguity_resolution_required",
            "Every blocking ambiguity must be resolved.",
            ambiguity_ids=missing_resolutions,
        )
    for ambiguity_id, resolution in resolution_map.items():
        _require_stable_text(resolution, "ambiguity resolution")
        ambiguity = known_ambiguities[ambiguity_id]
        if ambiguity.options and resolution not in ambiguity.options:
            raise SemanticContractError(
                "semantic_ambiguity_resolution_invalid",
                f"Resolution for {ambiguity_id!r} is not one of the declared options.",
                ambiguity_id=ambiguity_id,
                resolution=resolution,
            )

    source_by_id = {item.item_id: item for item in proposal.data_items}
    derived_by_id = {item.item_id: item for item in proposal.derived_items}
    renderable_dispositions = {
        DataDisposition.RENDER_PRIMARY,
        DataDisposition.RENDER_SECONDARY,
    }
    for element in proposal.figure_elements:
        if not element.required:
            continue
        if not element.data_item_ids:
            raise SemanticContractError(
                "semantic_required_element_unbound",
                f"Required figure element {element.element_id!r} has no data binding.",
                element_id=element.element_id,
            )
        for item_id in element.data_item_ids:
            if item_id in source_by_id:
                disposition = source_by_id[item_id].disposition
            else:
                if item_id not in approved or item_id not in derived_by_id:
                    raise SemanticContractError(
                        "semantic_required_element_derived_unapproved",
                        f"Required element {element.element_id!r} uses an unapproved helper.",
                        element_id=element.element_id,
                        item_id=item_id,
                    )
                disposition = derived_by_id[item_id].disposition
            if disposition not in renderable_dispositions:
                raise SemanticContractError(
                    "semantic_required_element_not_renderable",
                    f"Required element {element.element_id!r} binds non-renderable data.",
                    element_id=element.element_id,
                    item_id=item_id,
                    disposition=disposition.value,
                )


@dataclass(frozen=True)
class ConfirmedSemanticContract:
    """An immutable, source-bound contract approved by the user."""

    proposal: SemanticProposal
    approved_derived_item_ids: tuple[str, ...] = ()
    resolved_ambiguities: tuple[tuple[str, str], ...] = ()
    contract_version: str = SEMANTIC_CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "approved_derived_item_ids",
            _normalise_strings(self.approved_derived_item_ids),
        )
        object.__setattr__(
            self,
            "resolved_ambiguities",
            _normalise_resolutions(self.resolved_ambiguities),
        )

    def validate(self) -> None:
        if self.contract_version != SEMANTIC_CONTRACT_VERSION:
            raise SemanticContractError(
                "semantic_contract_version_unsupported",
                f"Unsupported semantic contract version: {self.contract_version!r}.",
            )
        self.proposal.validate()
        _validate_confirmation(
            self.proposal,
            self.approved_derived_item_ids,
            self.resolved_ambiguities,
        )

    def _payload(self) -> dict[str, object]:
        payload = self.proposal._payload()
        payload.update(
            {
                "contract_version": self.contract_version,
                "proposal_hash": self.proposal.proposal_hash,
                "status": "confirmed",
                "confirmation": {
                    "approved_derived_item_ids": list(self.approved_derived_item_ids),
                    "resolved_ambiguities": dict(self.resolved_ambiguities),
                },
            }
        )
        return payload

    @property
    def contract_hash(self) -> str:
        return _canonical_hash(self._payload())

    def stable_hash(self) -> str:
        return self.contract_hash

    def to_dict(self) -> dict[str, object]:
        payload = self._payload()
        payload["contract_hash"] = self.contract_hash
        return payload


_PROPOSAL_REQUIRED_FIELDS = frozenset(
    {
        "proposal_version",
        "source_sha256",
        "source_columns",
        "domain",
        "data_items",
        "derived_items",
        "figure_elements",
        "ambiguities",
    }
)
_PROPOSAL_OPTIONAL_FIELDS = frozenset({"proposal_hash"})
_DOMAIN_FIELDS = frozenset(
    {
        "family",
        "mode",
        "confidence",
        "source_adapter_hint",
    }
)
_CONTRACT_REQUIRED_FIELDS = _PROPOSAL_REQUIRED_FIELDS | frozenset(
    {
        "contract_version",
        "status",
        "confirmation",
    }
)
_CONTRACT_OPTIONAL_FIELDS = frozenset({"proposal_hash", "contract_hash"})
_CONFIRMATION_FIELDS = frozenset(
    {
        "approved_derived_item_ids",
        "resolved_ambiguities",
    }
)


def _strict_hash(value: object, field: str) -> str:
    text = _strict_text(value, field)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", text):
        raise _payload_error(
            f"{field} must contain exactly 64 hexadecimal characters.",
            field=field,
        )
    return text.lower()


def _parse_semantic_proposal_fields(
    payload: Mapping[str, object],
) -> SemanticProposal:
    domain = _strict_object(
        payload["domain"],
        field="$.domain",
        required=_DOMAIN_FIELDS,
    )
    source_columns = _strict_string_list(
        payload["source_columns"],
        "$.source_columns",
    )
    data_items = tuple(
        _parse_source_data_item(item, f"$.data_items[{index}]")
        for index, item in enumerate(
            _strict_list(payload["data_items"], "$.data_items")
        )
    )
    derived_items = tuple(
        _parse_derived_data_item(item, f"$.derived_items[{index}]")
        for index, item in enumerate(
            _strict_list(payload["derived_items"], "$.derived_items")
        )
    )
    figure_elements = tuple(
        _parse_figure_element(item, f"$.figure_elements[{index}]")
        for index, item in enumerate(
            _strict_list(payload["figure_elements"], "$.figure_elements")
        )
    )
    ambiguities = tuple(
        _parse_ambiguity(item, f"$.ambiguities[{index}]")
        for index, item in enumerate(
            _strict_list(payload["ambiguities"], "$.ambiguities")
        )
    )
    _reject_absolute_paths(payload)
    proposal = SemanticProposal(
        source_sha256=_strict_hash(payload["source_sha256"], "$.source_sha256"),
        source_columns=source_columns,
        domain_family=_strict_text(domain["family"], "$.domain.family"),
        domain_mode=_strict_text(domain["mode"], "$.domain.mode"),
        domain_confidence=_strict_number(
            domain["confidence"],
            "$.domain.confidence",
        ),
        data_items=data_items,
        derived_items=derived_items,
        figure_elements=figure_elements,
        ambiguities=ambiguities,
        source_adapter_hint=_strict_optional_text(
            domain["source_adapter_hint"],
            "$.domain.source_adapter_hint",
        ),
        proposal_version=_strict_text(
            payload["proposal_version"],
            "$.proposal_version",
        ),
    )
    proposal.validate()
    if "proposal_hash" in payload:
        supplied_hash = _strict_hash(payload["proposal_hash"], "$.proposal_hash")
        if supplied_hash != proposal.proposal_hash:
            raise SemanticContractError(
                "semantic_proposal_hash_mismatch",
                "The semantic proposal hash does not match its current content.",
            )
    return proposal


def parse_semantic_proposal(payload: Mapping[str, object]) -> SemanticProposal:
    """Strictly reconstruct and validate a proposal from its public JSON form."""

    normalized = _strict_object(
        payload,
        field="$",
        required=_PROPOSAL_REQUIRED_FIELDS,
        optional=_PROPOSAL_OPTIONAL_FIELDS,
    )
    return _parse_semantic_proposal_fields(normalized)


def parse_confirmed_semantic_contract(
    payload: Mapping[str, object],
) -> ConfirmedSemanticContract:
    """Strictly reconstruct a confirmed, source-bound semantic contract."""

    normalized = _strict_object(
        payload,
        field="$",
        required=_CONTRACT_REQUIRED_FIELDS,
        optional=_CONTRACT_OPTIONAL_FIELDS,
    )
    _reject_absolute_paths(normalized)
    status = _strict_text(normalized["status"], "$.status")
    if status != "confirmed":
        raise SemanticContractError(
            "semantic_contract_not_confirmed",
            "Only an explicitly confirmed semantic contract can be parsed.",
        )

    proposal_payload = {
        key: normalized[key]
        for key in _PROPOSAL_REQUIRED_FIELDS | _PROPOSAL_OPTIONAL_FIELDS
        if key in normalized
    }
    proposal = _parse_semantic_proposal_fields(proposal_payload)
    confirmation = _strict_object(
        normalized["confirmation"],
        field="$.confirmation",
        required=_CONFIRMATION_FIELDS,
    )
    approved_ids = _strict_string_list(
        confirmation["approved_derived_item_ids"],
        "$.confirmation.approved_derived_item_ids",
    )
    resolutions = _strict_string_key_object(
        confirmation["resolved_ambiguities"],
        field="$.confirmation.resolved_ambiguities",
    )
    resolved_ambiguities = tuple(
        (
            ambiguity_id,
            _strict_text(
                resolution,
                f"$.confirmation.resolved_ambiguities.{ambiguity_id}",
            ),
        )
        for ambiguity_id, resolution in resolutions.items()
    )
    _reject_absolute_paths(confirmation)
    contract = ConfirmedSemanticContract(
        proposal=proposal,
        approved_derived_item_ids=approved_ids,
        resolved_ambiguities=resolved_ambiguities,
        contract_version=_strict_text(
            normalized["contract_version"],
            "$.contract_version",
        ),
    )
    contract.validate()
    if "contract_hash" in normalized:
        supplied_hash = _strict_hash(
            normalized["contract_hash"],
            "$.contract_hash",
        )
        if supplied_hash != contract.contract_hash:
            raise SemanticContractError(
                "semantic_contract_hash_mismatch",
                "The semantic contract hash does not match its current content.",
            )
    return contract


__all__ = [
    "ALLOWED_DERIVED_OPERATIONS",
    "SEMANTIC_CONTRACT_VERSION",
    "SEMANTIC_PROPOSAL_VERSION",
    "ConfirmedSemanticContract",
    "DataDisposition",
    "DerivedDataItem",
    "FigureElement",
    "SemanticAmbiguity",
    "SemanticContractError",
    "SemanticDataItem",
    "SemanticProposal",
    "parse_confirmed_semantic_contract",
    "parse_semantic_proposal",
]
