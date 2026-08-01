"""JSON-lines progress protocol for GUI/worker communication."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Mapping
from typing import Any

_WORKER_STARTED_MONOTONIC = time.monotonic()

MAX_JSONL_BYTES = 32 * 1024
MAX_FIELD_CHARS = 2_048
MAX_COLLECTION_ITEMS = 64
MAX_NESTING_DEPTH = 8
_MAX_KEY_CHARS = 128
_FALLBACK_FIELD_CHARS = 256
_TRUNCATION_SUFFIX = "[truncated]"
_FALLBACK_PRIORITY_FIELDS = (
    "type",
    "elapsed_seconds",
    "step",
    "status",
    "code",
    "message",
    "output_dir",
    "selected_template_id",
    "selected_renderer_template_id",
    "origin_version",
    "opju",
    "png",
    "pdf",
    "tif",
    "origin_verify_report",
    "plan_digest",
)


def message(kind: str, **payload: Any) -> dict[str, Any]:
    elapsed_seconds = round(time.monotonic() - _WORKER_STARTED_MONOTONIC, 3)
    return {"type": kind, "elapsed_seconds": elapsed_seconds, **payload}


def _truncate_text(value: str, limit: int = MAX_FIELD_CHARS) -> str:
    if len(value) <= limit:
        return value
    retained = max(0, limit - len(_TRUNCATION_SUFFIX))
    return value[:retained] + _TRUNCATION_SUFFIX


def _collection_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        item_count = len(value)
        value_type = "mapping"
    elif isinstance(value, (list, tuple)):
        item_count = len(value)
        value_type = "sequence"
    else:
        item_count = None
        value_type = type(value).__name__
    summary: dict[str, Any] = {
        "_protocol_truncated": True,
        "value_type": value_type,
    }
    if item_count is not None:
        summary["item_count"] = item_count
    return summary


def _bounded_value(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, str):
        return _truncate_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if depth >= MAX_NESTING_DEPTH:
        return _collection_summary(value)
    if isinstance(value, Mapping):
        items = list(value.items())
        bounded: dict[str, Any] = {}
        for raw_key, item in items[:MAX_COLLECTION_ITEMS]:
            key = _truncate_text(str(raw_key), _MAX_KEY_CHARS)
            bounded[key] = _bounded_value(item, depth=depth + 1)
        omitted = len(items) - MAX_COLLECTION_ITEMS
        if omitted > 0:
            bounded["_protocol_truncated_items"] = omitted
        return bounded
    if isinstance(value, (list, tuple)):
        items = list(value)
        bounded_items = [
            _bounded_value(item, depth=depth + 1)
            for item in items[:MAX_COLLECTION_ITEMS]
        ]
        omitted = len(items) - MAX_COLLECTION_ITEMS
        if omitted > 0:
            bounded_items.append({"_protocol_truncated_items": omitted})
        return bounded_items
    return _truncate_text(str(value))


def _json_line(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n"


def _line_limit_fallback(
    payload: Mapping[str, Any],
    *,
    original_json_bytes: int,
) -> dict[str, Any]:
    reduced: dict[str, Any] = {}
    for key in _FALLBACK_PRIORITY_FIELDS:
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, str):
            reduced[key] = _truncate_text(value, _FALLBACK_FIELD_CHARS)
        elif value is None or isinstance(value, (bool, int, float)):
            reduced[key] = value
        else:
            reduced[key] = _collection_summary(value)
    omitted = [str(key) for key in payload if key not in reduced]
    reduced["payload_truncated"] = True
    reduced["original_json_bytes"] = original_json_bytes
    if omitted:
        reduced["omitted_top_level_fields"] = [
            _truncate_text(key, _MAX_KEY_CHARS)
            for key in omitted[:MAX_COLLECTION_ITEMS]
        ]
    return reduced


def _encode_bounded_jsonl(payload: Mapping[str, Any]) -> str:
    bounded = _bounded_value(payload)
    if not isinstance(bounded, dict):
        bounded = {"type": "protocol_error", "payload": bounded}
    line = _json_line(bounded)
    encoded_bytes = len(line.encode("utf-8"))
    if encoded_bytes <= MAX_JSONL_BYTES:
        return line

    fallback = _line_limit_fallback(
        bounded,
        original_json_bytes=encoded_bytes,
    )
    line = _json_line(fallback)
    if len(line.encode("utf-8")) <= MAX_JSONL_BYTES:
        return line

    minimal = {
        "type": _truncate_text(str(bounded.get("type", "protocol_message")), 64),
        "elapsed_seconds": bounded.get("elapsed_seconds"),
        "payload_truncated": True,
        "original_json_bytes": encoded_bytes,
    }
    return _json_line(minimal)


def emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(_encode_bounded_jsonl(payload))
    sys.stdout.flush()


def progress(step: str, status: str, text: str) -> None:
    emit(message("progress", step=step, status=status, message=text))


def warning(code: str, text: str, **extra: Any) -> None:
    emit(message("warning", code=code, message=text, **extra))


def error(code: str, text: str, **extra: Any) -> None:
    emit(message("error", code=code, message=text, **extra))


def done(**payload: Any) -> None:
    emit(message("done", **payload))
