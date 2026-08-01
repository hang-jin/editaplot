from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SRC = ROOT / "runtime" / "src"
ADAPTIVE_RUNNER = ROOT / "runtime" / "templates" / "xps_adaptive" / "runner.py"
SOURCE = ROOT / "runtime" / "templates" / "xps_adaptive" / "example_standard.csv"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.xps_workflow import (  # noqa: E402
    XpsColumnMapping,
    load_xps_frame,
    load_xps_source_snapshot,
    prepare_xps,
    validate_xps_render_frame,
)


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("xps_ignored_runner", ADAPTIVE_RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _confirmed_input(tmp_path: Path) -> tuple[Path, object]:
    frame = pd.read_csv(SOURCE)
    frame["QC note"] = [f"keep-{index}" for index in range(len(frame.index))]
    path = tmp_path / "xps_with_source_only_note.csv"
    frame.to_csv(path, index=False)
    preparation = prepare_xps(
        path,
        column_mapping=XpsColumnMapping(
            x="Binding Energy (E)",
            raw="Counts / s",
            background="Backgnd.",
            envelope="Envelope",
            residual="Residuals",
            components=("Peak A", "Peak B"),
            ignored=("QC note",),
            energy_kind="binding",
        ),
    )
    return path, preparation


def test_confirmed_ignored_column_crosses_runner_boundary_without_rendering(
    tmp_path: Path,
) -> None:
    path, preparation = _confirmed_input(tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    render_frame = load_xps_frame(path, preparation)
    validate_xps_render_frame(render_frame, preparation)
    resolved = _load_runner()._resolve_preparation(  # noqa: SLF001
        render_frame,
        SimpleNamespace(input_copy=path),
        preparation,
    )

    assert resolved is preparation
    assert "QC note" not in render_frame.columns
    assert "QC note" not in {series.column for series in preparation.plot_spec.series}
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_ignored_column_is_retained_verbatim_in_editable_source_snapshot(
    tmp_path: Path,
) -> None:
    path, preparation = _confirmed_input(tmp_path)

    snapshot = load_xps_source_snapshot(path, preparation)

    assert tuple(snapshot.columns) == preparation.source_columns
    assert snapshot["QC note"].tolist() == [
        f"keep-{index}" for index in range(preparation.row_count)
    ]
