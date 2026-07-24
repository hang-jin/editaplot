"""Run a template in a subprocess and emit JSON-lines progress."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import traceback
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from origin_sciplot.logging_utils import RunLogger
from origin_sciplot.origin_backend.safe_errors import (
    OriginDrawError,
    OriginEnvironmentError,
    OriginExportError,
    WorkerExitCode,
    safe_error_message,
)
from origin_sciplot.origin_backend.template_capabilities import (
    OriginCapability,
    evaluate_template_compatibility,
    get_template_capability_profile,
)
from origin_sciplot.origin_backend.verify_utils import require_nonempty
from origin_sciplot.output_manager import RunOutput, create_run_output, write_json
from origin_sciplot.reference_style import (
    ReferenceStyleError,
    apply_reference_style,
)
from origin_sciplot.scientific_workflow import (
    ScientificColumnMapping,
    ScientificWorkflowError,
    apply_scientific_palette_override,
    apply_scientific_text_overrides,
    load_scientific_frame,
    prepare_scientific,
)
from origin_sciplot.template_registry import TemplateManifest, TemplateRegistry
from origin_sciplot.validation.csv_validator import load_schema, validate_csv_file
from origin_sciplot.validation.schema_models import ValidationReport
from origin_sciplot.xps_workflow import (
    XpsColumnMapping,
    XpsWorkflowError,
    load_xps_frame,
    prepare_xps,
    select_xps_renderer_template_id,
    select_xps_template_id,
)

from . import progress_protocol as proto


def _load_runner(runner_path: Path):
    spec = importlib.util.spec_from_file_location("origin_sciplot_template_runner", runner_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load runner: {runner_path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "run"):
        raise RuntimeError(f"Runner {runner_path.name} does not define run()")
    return module


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an EditaPlot template")
    parser.add_argument("--template-id", default="auto")
    parser.add_argument("--input-csv", "--input-file", dest="input_csv", required=True)
    parser.add_argument("--output-dir")
    parser.add_argument("--render-plan-file")
    parser.add_argument("--expected-plan-digest")
    parser.add_argument("--column-mapping-json")
    parser.add_argument("--text-overrides-json")
    parser.add_argument("--palette-id")
    parser.add_argument("--reference-style-json")
    parser.set_defaults(keep_origin_open=True)
    parser.add_argument("--keep-origin-open", dest="keep_origin_open", action="store_true")
    parser.add_argument("--close-origin", dest="keep_origin_open", action="store_false")
    return parser


def _parse_reference_style_request(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ScientificWorkflowError(
            "reference_style_json_invalid",
            "The frozen reference-style request is not valid JSON.",
        ) from exc
    if not isinstance(payload, dict) or set(payload) != {
        "adaptation",
        "expected_report_hash",
        "locked_palette_id",
    }:
        raise ScientificWorkflowError(
            "reference_style_json_invalid",
            "The frozen reference-style request has an invalid structure.",
        )
    if not isinstance(payload["adaptation"], dict) or not isinstance(
        payload["expected_report_hash"],
        str,
    ):
        raise ScientificWorkflowError(
            "reference_style_json_invalid",
            "The frozen reference-style request is incomplete.",
        )
    locked_palette_id = payload["locked_palette_id"]
    if locked_palette_id is not None and not isinstance(locked_palette_id, str):
        raise ScientificWorkflowError(
            "reference_style_json_invalid",
            "The locked palette identifier is invalid.",
        )
    return payload


def _apply_reference_style_request(
    preparation: Any,
    request: dict[str, Any] | None,
) -> tuple[Any, dict[str, Any] | None]:
    if request is None:
        return preparation, None
    try:
        application = apply_reference_style(
            preparation,
            request["adaptation"],
            locked_palette_id=request["locked_palette_id"],
        )
    except ReferenceStyleError as exc:
        raise ScientificWorkflowError(exc.code, str(exc)) from exc
    report = application.report
    if not report["execution_allowed"]:
        raise ScientificWorkflowError(
            "reference_style_blocked",
            "The frozen reference-style route is not executable.",
        )
    if report["report_hash"] != request["expected_report_hash"]:
        raise ScientificWorkflowError(
            "reference_style_report_mismatch",
            "The worker reference-style decision differs from the approved plan.",
        )
    return application.preparation, report


def _validate_runner_result(
    manifest: TemplateManifest,
    output: RunOutput,
    result: Any,
) -> None:
    """Refuse a success event unless every artifact and axis readback exists."""
    if not isinstance(result, dict):
        raise OriginDrawError("Template runner returned an invalid result payload.")
    expected_paths = {
        "opju": output.result_opju,
        "png": output.result_png,
        "pdf": output.result_pdf,
        "tif": output.result_tif,
    }
    for key in manifest.outputs:
        expected = expected_paths.get(key)
        if expected is None:
            raise OriginExportError(f"Unsupported required output in manifest: {key}")
        reported = result.get(key)
        if not isinstance(reported, str) or not reported.strip():
            raise OriginExportError(f"Template runner omitted required output: {expected.name}")
        if Path(reported).resolve() != expected.resolve():
            raise OriginExportError(f"Template runner reported an unexpected path for {expected.name}")
        try:
            require_nonempty(expected)
        except RuntimeError as exc:
            raise OriginExportError(str(exc)) from exc

    verify = result.get("verify")
    if not isinstance(verify, Mapping) or not isinstance(verify.get("origin_axis_state"), Mapping):
        raise OriginDrawError("Template runner did not return the required Origin axis readback.")
    try:
        require_nonempty(output.origin_verify_report)
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc


def _activated_optional_capabilities(
    template_id: str,
    scientific_analysis: Any,
) -> frozenset[OriginCapability]:
    if scientific_analysis is None:
        return frozenset()
    profile = get_template_capability_profile(template_id)
    spec = scientific_analysis.plot_spec
    route_capabilities: set[OriginCapability] = set()
    if getattr(spec, "aggregate_error_column", None) or any(
        getattr(series, "error_column", None) for series in spec.series
    ):
        route_capabilities.add(OriginCapability.ERROR_BARS)
    if getattr(spec, "inset_series", ()):
        route_capabilities.add(OriginCapability.INSET_LAYER)
    if any(getattr(spec, name, None) == "log10" for name in ("x_scale", "y_scale")):
        route_capabilities.add(OriginCapability.LOG_AXIS)
    return frozenset(route_capabilities & profile.optional)


def _record_template_compatibility(
    output: RunOutput,
    manifest: TemplateManifest,
    scientific_analysis: Any,
) -> dict[str, Any]:
    """Attach a post-render capability decision to the auditable reports."""

    try:
        environment = json.loads(output.environment_report.read_text(encoding="utf-8"))
        verify_report = json.loads(output.origin_verify_report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OriginDrawError(
            "Origin compatibility evidence could not be read",
            code="origin_compatibility_report_invalid",
            stage="compatibility_report",
        ) from exc
    if not isinstance(environment, dict) or not isinstance(verify_report, dict):
        raise OriginDrawError(
            "Origin compatibility evidence is invalid",
            code="origin_compatibility_report_invalid",
            stage="compatibility_report",
        )

    profile = get_template_capability_profile(manifest.id)
    activated = _activated_optional_capabilities(manifest.id, scientific_analysis)
    decision = evaluate_template_compatibility(
        manifest.id,
        str(environment.get("origin_version", "")),
        profile.required | activated,
        activated_optional=activated,
    )
    decision_payload = decision.to_dict()
    decision_payload["evidence_source"] = "successful_template_render"
    decision_payload["global_capability_probe"] = False
    environment["template_capability_profile"] = profile.to_dict()
    environment["template_compatibility"] = decision_payload
    verify_report["template_capability_profile"] = profile.to_dict()
    verify_report["template_compatibility"] = decision_payload
    write_json(output.environment_report, environment)
    write_json(output.origin_verify_report, verify_report)
    return decision_payload


def _record_reference_style(
    output: RunOutput,
    result: Any,
    report: dict[str, Any] | None,
) -> None:
    if report is None:
        return
    write_json(output.output_dir / "reference_style_report.json", report)
    try:
        verify_report = json.loads(
            output.origin_verify_report.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise OriginDrawError(
            "Origin reference-style evidence could not be read",
            code="reference_style_report_invalid",
            stage="reference_style_report",
        ) from exc
    if not isinstance(verify_report, dict):
        raise OriginDrawError(
            "Origin reference-style evidence is invalid",
            code="reference_style_report_invalid",
            stage="reference_style_report",
        )
    verify_report["reference_style"] = report
    write_json(output.origin_verify_report, verify_report)
    if isinstance(result, dict) and isinstance(result.get("verify"), dict):
        result["verify"]["reference_style"] = report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = None
    logger = None
    xps_analysis = None
    scientific_analysis = None
    reference_style_report: dict[str, Any] | None = None
    try:
        render_plan_source = None
        if args.render_plan_file:
            render_plan_source = Path(args.render_plan_file).resolve()
            if not render_plan_source.is_file():
                raise ScientificWorkflowError(
                    "render_plan_missing",
                    "The approved render plan file is unavailable.",
                )
        selected_template_id = args.template_id
        selected_renderer_template_id = None
        reference_style_request = _parse_reference_style_request(
            args.reference_style_json
        )
        column_mapping = None
        scientific_mapping = None
        scientific_text_overrides: dict[str, str] | None = None
        if args.text_overrides_json:
            try:
                payload = json.loads(args.text_overrides_json)
                if not isinstance(payload, dict):
                    raise TypeError("text overrides must be an object")
                unknown = set(payload) - {"x_title", "y_title"}
                if unknown:
                    raise ValueError(f"unsupported text override keys: {sorted(unknown)}")
                scientific_text_overrides = {
                    str(key): str(value) for key, value in payload.items()
                }
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ScientificWorkflowError(
                    "text_overrides_invalid",
                    "The confirmed axis-title overrides are invalid.",
                ) from exc
        if args.column_mapping_json and args.template_id in {"auto", "xps"}:
            try:
                mapping_payload = json.loads(args.column_mapping_json)
                column_mapping = XpsColumnMapping(
                    x=str(mapping_payload["x"]),
                    raw=str(mapping_payload["raw"]),
                    background=(
                        str(mapping_payload["background"])
                        if mapping_payload.get("background")
                        else None
                    ),
                    envelope=(
                        str(mapping_payload["envelope"])
                        if mapping_payload.get("envelope")
                        else None
                    ),
                    residual=(
                        str(mapping_payload["residual"])
                        if mapping_payload.get("residual")
                        else None
                    ),
                    components=tuple(str(item) for item in mapping_payload.get("components", [])),
                    ignored=tuple(str(item) for item in mapping_payload.get("ignored", [])),
                    energy_kind=str(mapping_payload["energy_kind"]),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise XpsWorkflowError(
                    "mapping_json_invalid", "The confirmed column mapping is invalid."
                ) from exc
        elif args.column_mapping_json:
            try:
                mapping_payload = json.loads(args.column_mapping_json)
                raw_assignments = mapping_payload["assignments"]
                if not isinstance(raw_assignments, dict):
                    raise TypeError("assignments must be an object")
                scientific_mapping = ScientificColumnMapping(
                    assignments=tuple(
                        (str(column), str(role))
                        for column, role in raw_assignments.items()
                    ),
                    plot_mode=(
                        str(mapping_payload["plot_mode"])
                        if mapping_payload.get("plot_mode")
                        else None
                    ),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ScientificWorkflowError(
                    "mapping_json_invalid", "The confirmed column mapping is invalid."
                ) from exc
        if args.template_id in {"auto", "xps"}:
            if reference_style_request is not None:
                raise ScientificWorkflowError(
                    "reference_style_xps_unsupported",
                    "XPS keeps its verified component and fill style contract.",
                )
            if scientific_text_overrides:
                raise ScientificWorkflowError(
                    "text_overrides_unsupported",
                    "Axis-title overrides are currently available for scientific-table templates only.",
                )
            if args.palette_id:
                raise ScientificWorkflowError(
                    "palette_override_unsupported",
                    "XPS keeps its verified component-colour contract.",
                )
            xps_analysis = prepare_xps(args.input_csv, column_mapping=column_mapping)
            selected_template_id = select_xps_template_id(xps_analysis)
            selected_renderer_template_id = select_xps_renderer_template_id(xps_analysis)
            if xps_analysis.requires_confirmation:
                proto.error(
                    "mapping_confirmation_required",
                    "Column roles are ambiguous. Confirm the XPS column mapping before running Origin.",
                    reasons=list(xps_analysis.confirmation_reasons),
                )
                return WorkerExitCode.VALIDATION_FAILED

        proto.progress("load_template", "running", "正在读取模板 manifest")
        registry = TemplateRegistry()
        manifest = registry.get(selected_template_id)
        if manifest.workflow == "scientific_table":
            scientific_analysis = prepare_scientific(
                args.input_csv,
                manifest.id,
                column_mapping=scientific_mapping,
            )
            if scientific_text_overrides:
                scientific_analysis = apply_scientific_text_overrides(
                    scientific_analysis,
                    x_title=scientific_text_overrides.get("x_title"),
                    y_title=scientific_text_overrides.get("y_title"),
                )
            if args.palette_id:
                scientific_analysis = apply_scientific_palette_override(
                    scientific_analysis,
                    palette_id=args.palette_id,
                )
            scientific_analysis, reference_style_report = (
                _apply_reference_style_request(
                    scientific_analysis,
                    reference_style_request,
                )
            )
            selected_renderer_template_id = manifest.id
            if scientific_analysis.requires_confirmation:
                proto.error(
                    "mapping_confirmation_required",
                    "Column roles are ambiguous. Confirm the column mapping before running Origin.",
                    reasons=list(scientific_analysis.confirmation_reasons),
                )
                return WorkerExitCode.VALIDATION_FAILED
        schema = load_schema(manifest.schema_path)
        proto.progress("load_template", "success", f"已读取模板：{manifest.name}")

        proto.progress("create_output_dir", "running", "正在创建输出文件夹")
        output = create_run_output(args.input_csv, manifest, args.output_dir)
        if render_plan_source is not None:
            shutil.copy2(render_plan_source, output.render_plan_copy)
        logger = RunLogger(output.run_log, output.output_dir)
        logger.write(f"template={manifest.id} version={manifest.version}")
        if xps_analysis is not None:
            write_json(output.output_dir / "xps_analysis_report.json", xps_analysis.to_dict())
            copied_source_sha256 = hashlib.sha256(output.input_copy.read_bytes()).hexdigest()
            if copied_source_sha256 != xps_analysis.source_sha256:
                logger.write("XPS source changed while creating the provenance copy")
                proto.error(
                    "analysis_changed",
                    "The XPS analysis changed after preview. Refresh the preview and run again.",
                )
                return WorkerExitCode.VALIDATION_FAILED
        elif scientific_analysis is not None:
            write_json(
                output.output_dir / f"{manifest.id}_analysis_report.json",
                scientific_analysis.to_dict(),
            )
            copied_source_sha256 = hashlib.sha256(output.input_copy.read_bytes()).hexdigest()
            if copied_source_sha256 != scientific_analysis.source_sha256:
                logger.write("Scientific source changed while creating the provenance copy")
                proto.error(
                    "analysis_changed",
                    "The scientific analysis changed after preview. Refresh the preview and run again.",
                )
                return WorkerExitCode.VALIDATION_FAILED
            if reference_style_report is not None:
                write_json(
                    output.output_dir / "reference_style_report.json",
                    reference_style_report,
                )
        proto.progress("create_output_dir", "success", "输出文件夹已创建")

        if (
            (xps_analysis is not None or scientific_analysis is not None)
            and args.expected_plan_digest is not None
            and args.expected_plan_digest
            != (
                xps_analysis.plan_digest
                if xps_analysis is not None
                else scientific_analysis.plan_digest
            )
        ):
            logger.write("Scientific analysis changed after preview; refusing to start Origin")
            proto.error(
                "analysis_changed",
                "The scientific analysis changed after preview. Refresh the preview and run again.",
            )
            return WorkerExitCode.VALIDATION_FAILED

        proto.progress("validate_csv", "running", "正在校验绘图数据")
        if xps_analysis is not None:
            validation_frame = load_xps_frame(output.input_copy, xps_analysis)
            validation_report = ValidationReport(row_count=len(validation_frame))
            validation_report.cleaned_empty_rows = xps_analysis.ignored_empty_rows
            for warning_code in xps_analysis.warnings:
                validation_report.add_warning(warning_code, warning_code)
        elif scientific_analysis is not None:
            validation_frame = load_scientific_frame(output.input_copy, scientific_analysis)
            validation_report = ValidationReport(row_count=len(validation_frame))
            validation_report.cleaned_empty_rows = scientific_analysis.ignored_empty_rows
            for warning_code in scientific_analysis.warnings:
                validation_report.add_warning(warning_code, warning_code)
        else:
            validation = validate_csv_file(output.input_copy, schema)
            validation_frame = validation.frame
            validation_report = validation.report
        write_json(output.validation_report, validation_report.to_dict())
        for warning in validation_report.warnings:
            proto.warning(warning.code, warning.message, column=warning.column, row=warning.row)
        if not validation_report.ok or validation_frame is None:
            for item in validation_report.errors:
                proto.error(item.code, item.message, column=item.column, row=item.row)
            return WorkerExitCode.VALIDATION_FAILED
        proto.progress("validate_csv", "success", "绘图数据校验通过")

        proto.progress("launch_origin", "running", "正在启动 Origin 并写入工作簿")
        runner = _load_runner(manifest.runner_path)
        runner_options = {"keep_origin_open": args.keep_origin_open}
        if xps_analysis is not None:
            runner_options["preparation"] = xps_analysis
        elif scientific_analysis is not None:
            runner_options["preparation"] = scientific_analysis
        result = runner.run(manifest, validation_frame, output, logger, **runner_options)
        _record_reference_style(output, result, reference_style_report)
        compatibility = _record_template_compatibility(
            output,
            manifest,
            scientific_analysis,
        )
        _validate_runner_result(manifest, output, result)
        proto.progress("export", "success", "OPJU/PNG/PDF/TIFF 导出流程完成")
        done_payload = dict(result)
        done_payload.update(
            {
                "output_dir": str(output.output_dir),
                "selected_template_id": selected_template_id,
                "origin_compatibility": compatibility,
            }
        )
        if xps_analysis is not None:
            done_payload.update(
                {
                    "plan_digest": xps_analysis.plan_digest,
                    "detection": xps_analysis.detection.to_dict(),
                    "selected_renderer_template_id": selected_renderer_template_id,
                }
            )
        elif scientific_analysis is not None:
            done_payload.update(
                {
                    "plan_digest": scientific_analysis.plan_digest,
                    "plot_spec": asdict(scientific_analysis.plot_spec),
                    "selected_renderer_template_id": selected_renderer_template_id,
                    "reference_style": reference_style_report,
                }
            )
        proto.done(**done_payload)
        return WorkerExitCode.SUCCESS
    except XpsWorkflowError as exc:
        safe = safe_error_message(exc)
        if logger:
            logger.write("XPS workflow error: " + safe)
        proto.error(exc.code, safe, column=exc.column, row=exc.row)
        return WorkerExitCode.VALIDATION_FAILED
    except ScientificWorkflowError as exc:
        safe = safe_error_message(exc)
        if logger:
            logger.write("Scientific workflow error: " + safe)
        proto.error(exc.code, safe, column=exc.column, row=exc.row)
        return WorkerExitCode.VALIDATION_FAILED
    except OriginEnvironmentError as exc:
        if logger:
            logger.write(
                "Origin environment error "
                f"[{exc.code}/{exc.stage}]: {safe_error_message(exc)}"
            )
        proto.error(exc.code, safe_error_message(exc), stage=exc.stage)
        return WorkerExitCode.ORIGIN_ENVIRONMENT
    except OriginDrawError as exc:
        if logger:
            logger.write(
                f"Origin draw error [{exc.code}/{exc.stage}]: "
                + safe_error_message(exc)
            )
        proto.error(exc.code, safe_error_message(exc), stage=exc.stage)
        return WorkerExitCode.ORIGIN_DRAW
    except OriginExportError as exc:
        if logger:
            logger.write(
                f"Origin export error [{exc.code}/{exc.stage}]: "
                + safe_error_message(exc)
            )
        proto.error(exc.code, safe_error_message(exc), stage=exc.stage)
        return WorkerExitCode.EXPORT_FAILED
    except Exception as exc:  # noqa: BLE001
        safe = safe_error_message(exc)
        if logger:
            logger.write("Unexpected error: " + safe)
            logger.write(traceback.format_exc())
        proto.error("unknown_error", safe)
        return WorkerExitCode.UNKNOWN


if __name__ == "__main__":
    raise SystemExit(main())
