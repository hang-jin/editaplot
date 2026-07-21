"""Validation report data structures."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ValidationMessage:
    level: str
    code: str
    message: str
    column: str | None = None
    row: int | None = None


@dataclass
class ValidationReport:
    ok: bool = True
    row_count: int = 0
    cleaned_empty_rows: int = 0
    errors: list[ValidationMessage] = field(default_factory=list)
    warnings: list[ValidationMessage] = field(default_factory=list)

    def add_error(
        self, code: str, message: str, column: str | None = None, row: int | None = None
    ) -> None:
        self.ok = False
        self.errors.append(ValidationMessage("error", code, message, column, row))

    def add_warning(
        self, code: str, message: str, column: str | None = None, row: int | None = None
    ) -> None:
        self.warnings.append(ValidationMessage("warning", code, message, column, row))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
