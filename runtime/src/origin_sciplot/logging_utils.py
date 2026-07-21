"""Small redacting run logger."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .project_paths import redact_windows_paths, relative_or_redacted


class RunLogger:
    """Append timestamped, redacted log lines to a run log file."""

    def __init__(self, log_path: Path, base_dir: Path | None = None) -> None:
        self.log_path = log_path
        self.base_dir = base_dir
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = redact_windows_paths(message)
        self.log_path.open("a", encoding="utf-8").write(f"[{timestamp}] {line}\n")

    def path(self, path: str | Path) -> str:
        return relative_or_redacted(path, self.base_dir)
