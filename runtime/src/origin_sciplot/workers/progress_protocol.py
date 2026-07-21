"""JSON-lines progress protocol for GUI/worker communication."""

from __future__ import annotations

import json
import sys
from typing import Any


def message(kind: str, **payload: Any) -> dict[str, Any]:
    return {"type": kind, **payload}


def emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def progress(step: str, status: str, text: str) -> None:
    emit(message("progress", step=step, status=status, message=text))


def warning(code: str, text: str, **extra: Any) -> None:
    emit(message("warning", code=code, message=text, **extra))


def error(code: str, text: str, **extra: Any) -> None:
    emit(message("error", code=code, message=text, **extra))


def done(**payload: Any) -> None:
    emit(message("done", **payload))
