"""Output directory creation and provenance copies."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .project_paths import safe_filename
from .template_registry import TemplateManifest


@dataclass
class RunOutput:
    output_dir: Path
    input_copy: Path
    render_plan_copy: Path
    result_opju: Path
    result_png: Path
    result_pdf: Path
    result_tif: Path
    run_log: Path
    validation_report: Path
    manifest_copy: Path
    schema_copy: Path
    environment_report: Path
    origin_verify_report: Path
    readme_output: Path


def _unique_dir(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.name}_{index:02d}")
        if not candidate.exists():
            return candidate
    raise RuntimeError("Could not allocate a unique output directory")


def default_output_dir(input_csv: str | Path, template_id: str, now: datetime | None = None) -> Path:
    del template_id  # The source file, not the selected chart, owns the output folder.
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    source = Path(input_csv).resolve()
    label = safe_filename(source.stem, fallback="data")
    return source.parent / f"{label}_EditaPlot_{timestamp}"


def create_run_output(
    input_csv: str | Path,
    manifest: TemplateManifest,
    output_dir: str | Path | None = None,
    now: datetime | None = None,
) -> RunOutput:
    source = Path(input_csv).resolve()
    target_dir = _unique_dir(
        Path(output_dir).resolve()
        if output_dir
        else default_output_dir(source, manifest.id, now)
    )
    target_dir.mkdir(parents=True, exist_ok=False)

    input_copy = target_dir / f"input_copy{source.suffix.lower()}"
    shutil.copy2(source, input_copy)
    manifest_copy = target_dir / "template_manifest_copy.yaml"
    schema_copy = target_dir / "schema_copy.json"
    shutil.copy2(manifest.directory / "manifest.yaml", manifest_copy)
    shutil.copy2(manifest.schema_path, schema_copy)

    readme_output = target_dir / "README_output.txt"
    readme_output.write_text(
        "EditaPlot output folder\n"
        "Files here are a reproducible copy of the input, approved render plan (when invoked "
        "through the Skill), template manifest, schema, validation report, environment report, "
        "editable OPJU, and exported images.\n",
        encoding="utf-8",
    )

    return RunOutput(
        output_dir=target_dir,
        input_copy=input_copy,
        render_plan_copy=target_dir / "render-plan.json",
        result_opju=target_dir / "result.opju",
        result_png=target_dir / "result.png",
        result_pdf=target_dir / "result.pdf",
        result_tif=target_dir / "result.tif",
        run_log=target_dir / "run_log.txt",
        validation_report=target_dir / "validation_report.json",
        manifest_copy=manifest_copy,
        schema_copy=schema_copy,
        environment_report=target_dir / "environment_report.json",
        origin_verify_report=target_dir / "origin_verify_report.json",
        readme_output=readme_output,
    )


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
