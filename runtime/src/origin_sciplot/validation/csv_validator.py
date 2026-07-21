"""CSV validation against a fixed template schema."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .schema_models import ValidationReport


@dataclass
class CsvValidationResult:
    frame: pd.DataFrame | None
    report: ValidationReport


def load_schema(schema_path: str | Path) -> dict[str, Any]:
    return json.loads(Path(schema_path).read_text(encoding="utf-8"))


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def _duplicate_columns(header: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for name in header:
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    return duplicates


def validate_csv_file(csv_path: str | Path, schema: dict[str, Any]) -> CsvValidationResult:
    path = Path(csv_path)
    report = ValidationReport()
    if not path.is_file():
        report.add_error("file_missing", "CSV file does not exist")
        return CsvValidationResult(None, report)

    header = _read_header(path)
    duplicates = _duplicate_columns(header)
    if duplicates:
        report.add_error(
            "duplicate_columns",
            "Duplicate CSV columns are not allowed: " + ", ".join(duplicates),
        )
        return CsvValidationResult(None, report)

    try:
        raw = pd.read_csv(path, encoding="utf-8-sig")
    except Exception as exc:  # noqa: BLE001 - converted to friendly report
        report.add_error("read_csv_failed", f"Could not read CSV: {type(exc).__name__}")
        return CsvValidationResult(None, report)

    empty_mask = raw.isna().all(axis=1)
    cleaned_empty_rows = int(empty_mask.sum())
    if cleaned_empty_rows:
        report.add_warning(
            "empty_rows_removed",
            f"Removed {cleaned_empty_rows} fully empty row(s) before validation.",
        )
        raw = raw.loc[~empty_mask].copy()
    report.cleaned_empty_rows = cleaned_empty_rows
    report.row_count = int(len(raw))

    min_columns = int(schema.get("min_columns", 0) or 0)
    if min_columns and len(raw.columns) < min_columns:
        report.add_error(
            "too_few_columns",
            f"CSV needs at least {min_columns} columns for this template.",
        )
        return CsvValidationResult(None, report)

    required = list(schema.get("required", []))
    missing = [name for name in required if name not in raw.columns]
    for name in missing:
        report.add_error("missing_column", f"Missing required column: {name}", column=name)
    if missing:
        return CsvValidationResult(None, report)

    numeric_spec = schema.get("numeric_columns", required)
    if numeric_spec in ("*", "__all__"):
        numeric_columns = [str(column) for column in raw.columns]
    else:
        numeric_columns = list(numeric_spec)
    converted = raw.copy()
    for column in numeric_columns:
        if column not in converted.columns:
            continue
        numeric = pd.to_numeric(converted[column], errors="coerce")
        bad = numeric.isna() & converted[column].notna()
        if bool(bad.any()):
            first_index = int(bad[bad].index[0])
            report.add_error(
                "non_numeric",
                f"Column {column} contains non-numeric data at row {first_index + 2}.",
                column=column,
                row=first_index + 2,
            )
        converted[column] = numeric

    if report.errors:
        return CsvValidationResult(None, report)

    min_rows = int(schema.get("min_rows", 10))
    if len(converted) < min_rows:
        report.add_error("too_few_rows", f"CSV needs at least {min_rows} valid rows.")
        return CsvValidationResult(None, report)

    energy_rule = schema.get("binding_energy", {})
    if "BindingEnergy" in converted.columns and energy_rule:
        low = float(converted["BindingEnergy"].min())
        high = float(converted["BindingEnergy"].max())
        warn_min = float(energy_rule.get("warn_min", 275.0))
        warn_max = float(energy_rule.get("warn_max", 300.0))
        if low < warn_min or high > warn_max:
            report.add_warning(
                "binding_energy_range",
                f"BindingEnergy range {low:g}-{high:g} eV is outside the expected C 1s window.",
                column="BindingEnergy",
            )
        if not converted["BindingEnergy"].is_monotonic_increasing:
            report.add_warning(
                "binding_energy_order",
                "BindingEnergy is not ascending; the Origin runner will sort it.",
                column="BindingEnergy",
            )
            converted = converted.sort_values("BindingEnergy").reset_index(drop=True)

    return CsvValidationResult(converted.reset_index(drop=True), report)
