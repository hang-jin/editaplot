"""Path helpers for source and frozen execution."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def app_root() -> Path:
    """Return the project root in source mode or PyInstaller extraction root."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)).resolve()
    return Path(__file__).resolve().parents[2]


def templates_dir() -> Path:
    return app_root() / "templates"


def resources_dir() -> Path:
    return app_root() / "src" / "origin_sciplot" / "resources"


def safe_filename(value: str, fallback: str = "file") -> str:
    """Return a portable filename component."""
    cleaned = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "_", value).strip(" ._")
    return cleaned or fallback


def is_ascii_path(path: str | Path) -> bool:
    try:
        str(path).encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def relative_or_redacted(path: str | Path, base: str | Path | None = None) -> str:
    """Return a non-private path for logs."""
    candidate = Path(path).resolve()
    if base is not None:
        root = Path(base).resolve()
        try:
            return candidate.relative_to(root).as_posix()
        except ValueError:
            pass
    return f"<external-path:{candidate.name}>"


def redact_windows_paths(message: str) -> str:
    """Redact absolute Windows paths from user-visible messages."""
    return re.sub(r"[A-Za-z]:\\[^\s,;\"']+", "<path-redacted>", message)
