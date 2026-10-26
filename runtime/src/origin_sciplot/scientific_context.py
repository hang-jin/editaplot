"""Pure, immutable scientific context normalization for explicit route facts."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Mapping

_ALLOWED_KEYS = {
    "event_response": frozenset({"interval_label", "time_unit", "response_unit"}),
    "spatial_profile": frozenset({"profile_x", "profile_y", "x_unit", "y_unit", "value_unit"}),
    "ratiometric_response": frozenset(
        {"ratio_definition", "x_unit", "numerator_unit", "denominator_unit", "ratio_unit"}
    ),
}
_REQUIRED_KEYS = {
    "event_response": frozenset({"interval_label"}),
    "spatial_profile": frozenset({"profile_x", "profile_y"}),
    "ratiometric_response": frozenset({"ratio_definition"}),
}
_COORDINATE_KEYS = frozenset({"profile_x", "profile_y"})


class ScientificContextError(ValueError):
    """A scientific context validation failure with machine-readable details."""

    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


def _context_pairs(value: object) -> tuple[tuple[str, object], ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        pairs = tuple(value.items())
    elif isinstance(value, tuple):
        pairs = value
    else:
        raise ScientificContextError(
            "invalid_scientific_context",
            "Scientific context must be an object or frozen tuple of key/value pairs.",
        )
    keys: set[str] = set()
    duplicate_keys: set[str] = set()
    for pair in pairs:
        if not isinstance(pair, tuple) or len(pair) != 2 or not isinstance(pair[0], str):
            raise ScientificContextError(
                "invalid_scientific_context",
                "Scientific context entries must be pairs with string keys.",
            )
        if pair[0] in keys:
            duplicate_keys.add(pair[0])
        keys.add(pair[0])
    if duplicate_keys:
        raise ScientificContextError(
            "invalid_scientific_context",
            "Scientific context must not contain duplicate keys.",
            duplicate_keys=sorted(duplicate_keys),
        )
    return pairs


def _validate_context_value(key: str, value: object) -> str | int | float:
    if key in _COORDINATE_KEYS:
        finite = False
        if type(value) in (int, float):
            try:
                finite = math.isfinite(value)
            except OverflowError:
                pass
        if not finite:
            raise ScientificContextError(
                "invalid_scientific_context",
                "Scientific context coordinates must be finite native numbers.",
                field=key,
            )
        return value
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 256
        or any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} or char in "\u2028\u2029" for char in value)
    ):
        raise ScientificContextError(
            "invalid_scientific_context",
            "Scientific context text must be nonblank, single-line, "
            "and at most 256 characters without controls.",
            field=key,
        )
    return value


def freeze_scientific_context(value: object = None) -> tuple[tuple[str, str | int | float], ...]:
    """Freeze supported scalar declarations before the route discriminator is available."""
    pairs = _context_pairs(value)
    known_keys = frozenset().union(*_ALLOWED_KEYS.values())
    unknown = {key for key, _ in pairs} - known_keys
    if unknown:
        raise ScientificContextError(
            "unknown_scientific_context_keys", "Scientific context contains unsupported keys.",
            unknown_keys=sorted(unknown),
        )
    return tuple(sorted((key, _validate_context_value(key, item)) for key, item in pairs))


def normalize_scientific_context(
    template_id: str,
    value: object = None,
    *,
    require_complete: bool = False,
) -> tuple[tuple[str, str | int | float], ...]:
    """Validate explicit facts and freeze them without coercion or inference.

    Empty context preserves existing routes. Completeness requires only route
    facts, not units: source-header unit resolution belongs to a later stage.
    Frozen tuple pairs are accepted for internal replay, with duplicate detection.
    Text is preserved exactly; neither expressions nor labels are interpreted.
    """
    pairs = _context_pairs(value)
    allowed = _ALLOWED_KEYS.get(template_id)
    if allowed is None:
        if pairs:
            raise ScientificContextError(
                "unsupported_scientific_context",
                "This template does not support scientific context.",
            )
        return ()
    provided = {key for key, _ in pairs}
    unknown = provided - allowed
    if unknown:
        raise ScientificContextError(
            "unknown_scientific_context_keys",
            "Scientific context contains unsupported keys for this template.",
            unknown_keys=sorted(unknown),
        )
    normalized = tuple(sorted((key, _validate_context_value(key, item)) for key, item in pairs))
    if require_complete:
        missing = _REQUIRED_KEYS[template_id] - provided
        if missing:
            raise ScientificContextError(
                "missing_scientific_context_keys",
                "Scientific context is missing required route facts.",
                missing_keys=sorted(missing),
            )
    return normalized
