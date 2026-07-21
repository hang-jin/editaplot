"""Read-only loading of tabular scientific data from supported local formats."""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd


SourceFormat = Literal["csv", "txt", "xls", "xlsx"]
SUPPORTED_TABLE_SUFFIXES = frozenset({".csv", ".txt", ".xls", ".xlsx"})


class DataLoadError(ValueError):
    """Stable, user-presentable failure raised while auditing a source table."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        column: str | None = None,
        row: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.column = column
        self.row = row


@dataclass(frozen=True)
class LoadedTable:
    """An audited local table plus source identity and reader metadata."""

    source_path: str
    source_sha256: str
    source_size_bytes: int
    source_format: SourceFormat
    delimiter: str | None
    sheet_name: str | None
    columns: tuple[str, ...]
    frame: pd.DataFrame
    ignored_empty_rows: int

    def copy_frame(self) -> pd.DataFrame:
        return self.frame.copy(deep=True)


def _validated_headers(values: list[object]) -> list[str]:
    headers = ["" if pd.isna(value) else str(value).strip() for value in values]
    if not headers or all(not value for value in headers):
        raise DataLoadError("empty_header", "The table header is empty.")
    # Some valid evidence plots (for example a single-variable histogram)
    # intentionally use one column.  Template-specific role validation decides
    # whether additional columns are required after this read-only load step.
    empty = next((value for value in headers if not value), None)
    if empty is not None:
        raise DataLoadError("empty_column_name", "Every table column must have a name.")
    duplicates = [value for index, value in enumerate(headers) if value in headers[:index]]
    if duplicates:
        raise DataLoadError(
            "duplicate_column",
            f"Duplicate table column: {duplicates[0]!r}.",
            column=duplicates[0],
        )
    return headers


def _detect_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:30])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        return dialect.delimiter
    except csv.Error:
        header = next((line for line in text.splitlines() if line.strip()), "")
        counts = {delimiter: header.count(delimiter) for delimiter in ",;\t"}
        detected = max(counts, key=counts.get)  # type: ignore[arg-type]
        # A delimiter-free header is intentionally parsed as one CSV field so the
        # caller can return the more useful stable ``too_few_columns`` error.
        return detected if counts[detected] else ","


def _read_text_table(source: bytes) -> tuple[pd.DataFrame, str, int]:
    if not source:
        raise DataLoadError("empty_file", "The data file is empty.")
    try:
        text = source.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataLoadError("encoding_error", "Text data must use UTF-8 encoding.") from exc
    if not text.strip():
        raise DataLoadError("empty_file", "The data file is empty.")
    delimiter = _detect_delimiter(text)
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True))
    except csv.Error as exc:
        raise DataLoadError("table_parse_error", f"The delimited table is invalid: {exc}") from exc
    if not rows:
        raise DataLoadError("empty_file", "The data file is empty.")
    headers = _validated_headers(list(rows[0]))
    data: list[list[str]] = []
    ignored_empty_rows = 0
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or all(not cell.strip() for cell in row):
            ignored_empty_rows += 1
            continue
        if len(row) != len(headers):
            raise DataLoadError(
                "malformed_row",
                f"Row {row_number} has {len(row)} fields; expected {len(headers)}.",
                row=row_number,
            )
        data.append(row)
    if not data:
        raise DataLoadError("no_data_rows", "The table has no data rows.")
    return pd.DataFrame(data, columns=headers), delimiter, ignored_empty_rows


def _frame_from_excel_matrix(matrix: pd.DataFrame) -> tuple[pd.DataFrame, int] | None:
    if matrix.empty:
        return None
    nonempty_mask = ~matrix.isna().all(axis=1)
    if not bool(nonempty_mask.any()):
        return None
    header_index = nonempty_mask[nonempty_mask].index[0]
    header_values = list(matrix.loc[header_index])
    while header_values and pd.isna(header_values[-1]):
        header_values.pop()
    headers = _validated_headers(header_values)
    raw_data = matrix.loc[matrix.index > header_index, matrix.columns[: len(headers)]].copy()
    empty_mask = raw_data.isna().all(axis=1)
    ignored_empty_rows = int(empty_mask.sum())
    data = raw_data.loc[~empty_mask].reset_index(drop=True)
    if data.empty:
        return None
    data.columns = headers
    return data, ignored_empty_rows


def _read_excel_table(path: Path, *, engine: str) -> tuple[pd.DataFrame, str, int]:
    try:
        with pd.ExcelFile(path, engine=engine) as book:
            for sheet_name in book.sheet_names:
                matrix = pd.read_excel(book, sheet_name=sheet_name, header=None, dtype=object)
                resolved = _frame_from_excel_matrix(matrix)
                if resolved is not None:
                    frame, ignored_empty_rows = resolved
                    return frame, str(sheet_name), ignored_empty_rows
    except ImportError as exc:
        raise DataLoadError(
            "excel_dependency_missing",
            f"Reading this workbook requires the {engine} package.",
        ) from exc
    except DataLoadError:
        raise
    except Exception as exc:  # noqa: BLE001 - converted to a stable UI error
        raise DataLoadError(
            "excel_read_error", f"Could not read the workbook ({type(exc).__name__})."
        ) from exc
    raise DataLoadError("no_data_rows", "No non-empty worksheet contains tabular data.")


def load_table(path: str | Path) -> LoadedTable:
    """Load a supported local table without modifying the source file."""
    source_path = Path(path)
    if not source_path.exists():
        raise DataLoadError("file_not_found", f"Data file does not exist: {source_path}")
    if not source_path.is_file():
        raise DataLoadError("not_a_file", f"Data path is not a file: {source_path}")
    suffix = source_path.suffix.lower()
    if suffix not in SUPPORTED_TABLE_SUFFIXES:
        raise DataLoadError("unsupported_format", f"Unsupported data format: {suffix or '(none)'}")
    try:
        source = source_path.read_bytes()
    except OSError as exc:
        raise DataLoadError("file_read_error", f"Could not read data file: {source_path}") from exc
    if not source:
        raise DataLoadError("empty_file", "The data file is empty.")

    delimiter: str | None = None
    sheet_name: str | None = None
    if suffix in {".csv", ".txt"}:
        frame, delimiter, ignored_empty_rows = _read_text_table(source)
    else:
        engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
        frame, sheet_name, ignored_empty_rows = _read_excel_table(source_path, engine=engine)

    return LoadedTable(
        source_path=str(source_path.resolve()),
        source_sha256=hashlib.sha256(source).hexdigest(),
        source_size_bytes=len(source),
        source_format=suffix.removeprefix("."),  # type: ignore[arg-type]
        delimiter=delimiter,
        sheet_name=sheet_name,
        columns=tuple(str(column) for column in frame.columns),
        frame=frame,
        ignored_empty_rows=ignored_empty_rows,
    )


__all__ = [
    "DataLoadError",
    "LoadedTable",
    "SUPPORTED_TABLE_SUFFIXES",
    "SourceFormat",
    "load_table",
]
