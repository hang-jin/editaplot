"""Safe, declarative contracts for adapting a user-provided reference figure.

This module deliberately performs no OCR, model inference, network access, or
rendering.  A vision-capable Codex session may describe a reference image with
the strict JSON contract below; the local runtime only validates, hashes, and
freezes that description before a renderer is allowed to consume it.
"""

from __future__ import annotations

import hashlib
import json
import re
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from PIL import Image, UnidentifiedImageError

REFERENCE_FIGURE_SCHEMA_VERSION = "1.0"
DEFAULT_MAX_REFERENCE_BYTES = 20 * 1024 * 1024
DEFAULT_MAX_REFERENCE_PIXELS = 40_000_000

_MEDIA_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "TIFF": "image/tiff",
}
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_IDENTIFIER_PATTERN = r"^[a-z][a-z0-9_.-]{0,95}$"


class ReferenceFigureError(ValueError):
    """Stable, path-free validation failure for a reference-figure workflow."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ReferenceImageMetadata:
    """Non-identifying facts derived from one validated image snapshot."""

    sha256: str
    media_type: str
    pixel_width: int
    pixel_height: int
    size_bytes: int
    frame_count: int = 1

    @property
    def pixel_count(self) -> int:
        return self.pixel_width * self.pixel_height

    def to_dict(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "media_type": self.media_type,
            "pixel_width": self.pixel_width,
            "pixel_height": self.pixel_height,
            "size_bytes": self.size_bytes,
            "frame_count": self.frame_count,
        }


def inspect_reference_image(
    path: str | Path,
    *,
    max_bytes: int = DEFAULT_MAX_REFERENCE_BYTES,
    max_pixels: int = DEFAULT_MAX_REFERENCE_PIXELS,
) -> ReferenceImageMetadata:
    """Validate a local PNG/JPEG/single-frame TIFF without exposing its path.

    The file is read once into a bounded snapshot.  Pillow then verifies and
    decodes that snapshot so a changed source file cannot make the reported
    hash disagree with the inspected pixels.
    """

    if isinstance(max_bytes, bool) or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")
    if isinstance(max_pixels, bool) or max_pixels <= 0:
        raise ValueError("max_pixels must be a positive integer")

    source = Path(path).expanduser()
    try:
        size_bytes = source.stat().st_size
    except (FileNotFoundError, IsADirectoryError, OSError) as exc:
        raise ReferenceFigureError(
            "reference_image_unavailable",
            "The reference image is not available as a readable local file.",
        ) from exc
    if size_bytes <= 0:
        raise ReferenceFigureError(
            "reference_image_empty",
            "The reference image is empty.",
        )
    if size_bytes > max_bytes:
        raise ReferenceFigureError(
            "reference_image_too_large",
            f"The reference image exceeds the {max_bytes}-byte safety limit.",
        )

    try:
        snapshot = source.read_bytes()
    except OSError as exc:
        raise ReferenceFigureError(
            "reference_image_unavailable",
            "The reference image could not be read.",
        ) from exc
    if len(snapshot) != size_bytes:
        raise ReferenceFigureError(
            "reference_image_changed",
            "The reference image changed while it was being inspected.",
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(snapshot)) as image:
                detected_format = str(image.format or "").upper()
                width, height = image.size
                frame_count = int(getattr(image, "n_frames", 1))
                image.verify()
            with Image.open(BytesIO(snapshot)) as image:
                image.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ReferenceFigureError(
            "reference_image_invalid",
            "The reference image is invalid or unsafe to decode.",
        ) from exc
    except (OSError, ValueError, SyntaxError) as exc:
        raise ReferenceFigureError(
            "reference_image_invalid",
            "The reference image is damaged or uses an unsupported encoding.",
        ) from exc

    media_type = _MEDIA_TYPES.get(detected_format)
    if media_type is None:
        raise ReferenceFigureError(
            "reference_media_unsupported",
            "Only PNG, JPEG, and TIFF reference images are supported.",
        )
    if width <= 0 or height <= 0:
        raise ReferenceFigureError(
            "reference_dimensions_invalid",
            "The reference image has invalid pixel dimensions.",
        )
    if width * height > max_pixels:
        raise ReferenceFigureError(
            "reference_pixel_limit_exceeded",
            f"The reference image exceeds the {max_pixels}-pixel safety limit.",
        )
    if frame_count != 1:
        raise ReferenceFigureError(
            "reference_multiframe_unsupported",
            "Animated or multi-page reference images are not supported.",
        )

    return ReferenceImageMetadata(
        sha256=hashlib.sha256(snapshot).hexdigest(),
        media_type=media_type,
        pixel_width=width,
        pixel_height=height,
        size_bytes=size_bytes,
        frame_count=frame_count,
    )


def _identifier_schema() -> dict[str, object]:
    return {"type": "string", "pattern": _IDENTIFIER_PATTERN}


def _confidence_schema() -> dict[str, object]:
    return {"type": "number", "minimum": 0, "maximum": 1}


REFERENCE_FIGURE_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "reference",
        "layout",
        "marks",
        "encodings",
        "style",
        "text_roles",
        "essential_features",
        "confirmation",
    ],
    "properties": {
        "schema_version": {"const": REFERENCE_FIGURE_SCHEMA_VERSION},
        "reference": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "sha256",
                "media_type",
                "pixel_width",
                "pixel_height",
                "size_bytes",
                "frame_count",
            ],
            "properties": {
                "sha256": {"type": "string", "pattern": _SHA256_PATTERN},
                "media_type": {"enum": sorted(_MEDIA_TYPES.values())},
                "pixel_width": {"type": "integer", "minimum": 1},
                "pixel_height": {"type": "integer", "minimum": 1},
                "size_bytes": {"type": "integer", "minimum": 1},
                "frame_count": {"const": 1},
            },
        },
        "layout": {
            "type": "object",
            "additionalProperties": False,
            "required": ["archetype", "aspect_ratio_class", "panels"],
            "properties": {
                "archetype": {
                    "enum": [
                        "single_chart",
                        "quantitative_grid",
                        "schematic_led",
                        "image_plus_quant",
                        "asymmetric_mixed",
                    ]
                },
                "aspect_ratio_class": {"enum": ["wide", "square", "tall", "adaptive"]},
                "panels": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 12,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "id",
                            "evidence_role",
                            "coordinate_system",
                            "relative_bbox",
                        ],
                        "properties": {
                            "id": _identifier_schema(),
                            "evidence_role": {
                                "enum": ["hero", "support", "control", "context"]
                            },
                            "coordinate_system": {
                                "enum": [
                                    "cartesian_2d",
                                    "polar",
                                    "matrix",
                                    "network",
                                    "cartesian_3d",
                                ]
                            },
                            "relative_bbox": {
                                "type": "array",
                                "minItems": 4,
                                "maxItems": 4,
                                "items": {"type": "number", "minimum": 0, "maximum": 1},
                            },
                            "shared_axis_group": {
                                "oneOf": [_identifier_schema(), {"type": "null"}]
                            },
                        },
                    },
                },
            },
        },
        "marks": {
            "type": "array",
            "minItems": 1,
            "maxItems": 128,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "panel_id",
                    "kind",
                    "evidence_role",
                    "essential",
                    "confidence",
                ],
                "properties": {
                    "id": _identifier_schema(),
                    "panel_id": _identifier_schema(),
                    "kind": {
                        "enum": [
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
                            "residual_curve",
                            "phase_tick",
                            "reference_line",
                            "text_annotation",
                            "legend",
                            "colorbar",
                            "inset",
                        ]
                    },
                    "evidence_role": {
                        "enum": ["primary", "validation", "context", "control", "decorative"]
                    },
                    "essential": {"type": "boolean"},
                    "confidence": _confidence_schema(),
                },
            },
        },
        "encodings": {
            "type": "array",
            "maxItems": 256,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "mark_id",
                    "channel",
                    "semantic_role",
                    "data_binding",
                    "confidence",
                ],
                "properties": {
                    "id": _identifier_schema(),
                    "mark_id": _identifier_schema(),
                    "channel": {
                        "enum": [
                            "x",
                            "y",
                            "y2",
                            "z",
                            "color",
                            "shape",
                            "line_style",
                            "size",
                            "fill",
                            "opacity",
                            "order",
                            "label",
                        ]
                    },
                    "semantic_role": _identifier_schema(),
                    "data_binding": {
                        "oneOf": [_identifier_schema(), {"type": "null"}]
                    },
                    "confidence": _confidence_schema(),
                },
            },
        },
        "style": {
            "type": "object",
            "additionalProperties": False,
            "required": [
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
            ],
            "properties": {
                "palette_family": {
                    "oneOf": [_identifier_schema(), {"type": "null"}]
                },
                "palette_id": {"oneOf": [_identifier_schema(), {"type": "null"}]},
                "line_weight": {"enum": ["light", "medium", "heavy", "adaptive"]},
                "marker_density": {"enum": ["none", "sparse", "medium", "dense", "adaptive"]},
                "fill_transparency": {"enum": ["none", "light", "medium", "heavy"]},
                "legend_position": {
                    "enum": [
                        "inside",
                        "outside_right",
                        "top",
                        "bottom",
                        "direct_labels",
                        "none",
                    ]
                },
                "legend_frame": {"type": "boolean"},
                "grid": {"enum": ["none", "major_only"]},
                "background": {"enum": ["white", "black", "transparent"]},
                "typography_hierarchy": {
                    "enum": ["publication_informed", "adaptive", "dense", "sparse"]
                },
            },
        },
        "text_roles": {
            "type": "array",
            "maxItems": 128,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "panel_id",
                    "role",
                    "observed_present",
                    "copy_policy",
                    "binding_id",
                    "confidence",
                ],
                "properties": {
                    "id": _identifier_schema(),
                    "panel_id": _identifier_schema(),
                    "role": {
                        "enum": [
                            "x_title",
                            "y_title",
                            "y2_title",
                            "z_title",
                            "legend",
                            "annotation",
                            "panel_label",
                            "colorbar_title",
                        ]
                    },
                    "observed_present": {"type": "boolean"},
                    "copy_policy": {"const": "user_data_or_confirmation_only"},
                    "binding_id": {
                        "oneOf": [_identifier_schema(), {"type": "null"}]
                    },
                    "confidence": _confidence_schema(),
                },
            },
        },
        "essential_features": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "feature_role", "mark_ids", "required_encoding_ids"],
                "properties": {
                    "id": _identifier_schema(),
                    "feature_role": _identifier_schema(),
                    "mark_ids": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": _identifier_schema(),
                    },
                    "required_encoding_ids": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": _identifier_schema(),
                    },
                },
            },
        },
        "confirmation": {
            "type": "object",
            "additionalProperties": False,
            "required": ["required", "confirmed", "confirmed_contract_sha256"],
            "properties": {
                "required": {"const": True},
                "confirmed": {"type": "boolean"},
                "confirmed_contract_sha256": {
                    "oneOf": [
                        {"type": "string", "pattern": _SHA256_PATTERN},
                        {"type": "null"},
                    ]
                },
            },
        },
    },
}

_SCHEMA_VALIDATOR = Draft202012Validator(REFERENCE_FIGURE_JSON_SCHEMA)
_FORBIDDEN_KEYS = {
    "code",
    "sourcecode",
    "script",
    "python",
    "labtalk",
    "ocrtext",
    "rawocr",
    "privatepath",
    "absolutepath",
    "sourcepath",
    "filepath",
    "imagepath",
    "command",
    "commands",
    "cmd",
    "cmdline",
    "shell",
    "powershell",
    "exec",
    "executable",
    "argv",
    "subprocess",
}


def _normalized_key(key: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).casefold())


def _find_forbidden_key(value: object, location: str = "$") -> tuple[str, str] | None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            normalized = _normalized_key(raw_key)
            forbidden = (
                normalized in _FORBIDDEN_KEYS
                or "command" in normalized
                or "labtalk" in normalized
                or "python" in normalized
                or normalized.startswith("ocr")
                or normalized.endswith("path")
                or normalized.startswith("script")
            )
            if forbidden:
                return location, str(raw_key)
            found = _find_forbidden_key(child, f"{location}.{raw_key}")
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found = _find_forbidden_key(child, f"{location}[{index}]")
            if found is not None:
                return found
    return None


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _contract_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = json.loads(_canonical_json(payload))
    result.pop("confirmation", None)
    return result


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _unique_index(items: list[dict[str, Any]], kind: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        item_id = item["id"]
        if item_id in result:
            raise ReferenceFigureError(
                "reference_spec_duplicate_id",
                f"The reference-figure contract contains a duplicate {kind} identifier.",
            )
        result[item_id] = item
    return result


def _validate_relations(payload: dict[str, Any]) -> None:
    panels = _unique_index(payload["layout"]["panels"], "panel")
    marks = _unique_index(payload["marks"], "mark")
    encodings = _unique_index(payload["encodings"], "encoding")
    _unique_index(payload["text_roles"], "text-role")
    features = _unique_index(payload["essential_features"], "essential-feature")

    for panel in panels.values():
        x, y, width, height = panel["relative_bbox"]
        if width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
            raise ReferenceFigureError(
                "reference_layout_invalid",
                "Every relative panel box must have positive size and remain inside the page.",
            )
    for mark in marks.values():
        if mark["panel_id"] not in panels:
            raise ReferenceFigureError(
                "reference_mark_panel_missing",
                "Every mark must refer to a declared panel.",
            )
    for encoding in encodings.values():
        if encoding["mark_id"] not in marks:
            raise ReferenceFigureError(
                "reference_encoding_mark_missing",
                "Every encoding must refer to a declared mark.",
            )
    for text_role in payload["text_roles"]:
        if text_role["panel_id"] not in panels:
            raise ReferenceFigureError(
                "reference_text_panel_missing",
                "Every text role must refer to a declared panel.",
            )

    covered_essential_marks: set[str] = set()
    for feature in features.values():
        feature_marks = set(feature["mark_ids"])
        feature_encodings = set(feature["required_encoding_ids"])
        if not feature_marks.issubset(marks):
            raise ReferenceFigureError(
                "reference_feature_mark_missing",
                "Every essential feature must refer to declared marks.",
            )
        if not feature_encodings.issubset(encodings):
            raise ReferenceFigureError(
                "reference_feature_encoding_missing",
                "Every essential feature must refer to declared encodings.",
            )
        if any(encodings[item]["mark_id"] not in feature_marks for item in feature_encodings):
            raise ReferenceFigureError(
                "reference_feature_encoding_mismatch",
                "An essential feature may require only encodings owned by its marks.",
            )
        covered_essential_marks.update(feature_marks)

    declared_essential_marks = {
        mark_id for mark_id, mark in marks.items() if mark["essential"]
    }
    if declared_essential_marks != covered_essential_marks:
        raise ReferenceFigureError(
            "reference_essential_mark_uncovered",
            "Every essential mark must belong to an essential feature, and vice versa.",
        )


def _unbound_essential_encodings(payload: dict[str, Any]) -> tuple[str, ...]:
    encodings = {item["id"]: item for item in payload["encodings"]}
    missing = {
        encoding_id
        for feature in payload["essential_features"]
        for encoding_id in feature["required_encoding_ids"]
        if encodings[encoding_id]["data_binding"] is None
    }
    return tuple(sorted(missing))


@dataclass(frozen=True)
class ReferenceFigureSpec:
    """Immutable canonical JSON contract produced before Origin rendering."""

    _canonical_payload: str
    contract_sha256: str
    spec_sha256: str

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        image_metadata: ReferenceImageMetadata | None = None,
    ) -> ReferenceFigureSpec:
        if not isinstance(payload, Mapping):
            raise ReferenceFigureError(
                "reference_spec_invalid",
                "The reference-figure contract must be a JSON object.",
            )
        forbidden = _find_forbidden_key(payload)
        if forbidden is not None:
            _location, key = forbidden
            raise ReferenceFigureError(
                "reference_spec_forbidden_field",
                f"The reference-figure contract contains a forbidden field: {key}.",
            )

        normalized = json.loads(_canonical_json(payload))
        errors = sorted(
            _SCHEMA_VALIDATOR.iter_errors(normalized),
            key=lambda error: tuple(str(item) for item in error.absolute_path),
        )
        if errors:
            raise ReferenceFigureError(
                "reference_spec_schema_invalid",
                "The reference-figure contract does not match the strict public schema.",
            )
        _validate_relations(normalized)

        if image_metadata is not None and normalized["reference"] != image_metadata.to_dict():
            raise ReferenceFigureError(
                "reference_metadata_mismatch",
                "The reference-figure contract does not match the inspected image snapshot.",
            )

        contract_sha256 = _digest(_contract_payload(normalized))
        confirmation = normalized["confirmation"]
        if confirmation["confirmed"]:
            if confirmation["confirmed_contract_sha256"] != contract_sha256:
                raise ReferenceFigureError(
                    "reference_confirmation_hash_mismatch",
                    "The confirmation does not match the current reference-figure contract.",
                )
            missing = _unbound_essential_encodings(normalized)
            if missing:
                raise ReferenceFigureError(
                    "reference_essential_feature_unbound",
                    "Confirmed reference-figure contracts must bind every essential feature.",
                )
        elif confirmation["confirmed_contract_sha256"] is not None:
            raise ReferenceFigureError(
                "reference_confirmation_state_invalid",
                "An unconfirmed contract cannot carry a confirmation digest.",
            )

        canonical_payload = _canonical_json(normalized)
        return cls(
            _canonical_payload=canonical_payload,
            contract_sha256=contract_sha256,
            spec_sha256=hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest(),
        )

    @property
    def confirmed(self) -> bool:
        return bool(self.to_dict()["confirmation"]["confirmed"])

    def to_dict(self) -> dict[str, Any]:
        """Return a detached copy containing no source path or raw OCR text."""

        return json.loads(self._canonical_payload)

    def confirm(self) -> ReferenceFigureSpec:
        """Bind explicit user confirmation to the current contract digest."""

        payload = self.to_dict()
        missing = _unbound_essential_encodings(payload)
        if missing:
            raise ReferenceFigureError(
                "reference_essential_feature_unbound",
                "Bind every required encoding before confirming the reference-figure contract.",
            )
        payload["confirmation"] = {
            "required": True,
            "confirmed": True,
            "confirmed_contract_sha256": self.contract_sha256,
        }
        return ReferenceFigureSpec.from_dict(payload)

    def require_renderable(self) -> None:
        """Fail closed until confirmation and essential bindings are complete."""

        payload = self.to_dict()
        if not payload["confirmation"]["confirmed"]:
            raise ReferenceFigureError(
                "reference_confirmation_required",
                "Confirm the reference-figure understanding before rendering.",
            )
        if payload["confirmation"]["confirmed_contract_sha256"] != self.contract_sha256:
            raise ReferenceFigureError(
                "reference_confirmation_hash_mismatch",
                "The confirmed reference-figure contract changed after confirmation.",
            )
        if _unbound_essential_encodings(payload):
            raise ReferenceFigureError(
                "reference_essential_feature_unbound",
                "Every essential reference feature needs a confirmed data binding.",
            )


def parse_reference_figure_spec(
    payload: Mapping[str, Any],
    *,
    image_metadata: ReferenceImageMetadata | None = None,
) -> ReferenceFigureSpec:
    """Public functional wrapper around :meth:`ReferenceFigureSpec.from_dict`."""

    return ReferenceFigureSpec.from_dict(payload, image_metadata=image_metadata)


__all__ = [
    "DEFAULT_MAX_REFERENCE_BYTES",
    "DEFAULT_MAX_REFERENCE_PIXELS",
    "REFERENCE_FIGURE_JSON_SCHEMA",
    "REFERENCE_FIGURE_SCHEMA_VERSION",
    "ReferenceFigureError",
    "ReferenceFigureSpec",
    "ReferenceImageMetadata",
    "inspect_reference_image",
    "parse_reference_figure_spec",
]
