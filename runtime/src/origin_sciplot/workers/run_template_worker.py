"""Run a template in a subprocess and emit JSON-lines progress."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import traceback
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from origin_sciplot.logging_utils import RunLogger
from origin_sciplot.origin_backend.execution_context import (
    require_interactive_origin_context,
)
from origin_sciplot.origin_backend.job_queue import origin_job_slot
from origin_sciplot.origin_backend.safe_errors import (
    OriginDrawError,
    OriginEnvironmentError,
    OriginExportError,
    WorkerExitCode,
    origin_activation_recovery,
    safe_error_message,
    structured_error_diagnostics,
)
from origin_sciplot.origin_backend.template_capabilities import (
    OriginCapability,
    evaluate_template_compatibility,
    get_template_capability_profile,
    resolve_activated_optional_capabilities,
)
from origin_sciplot.origin_backend.verify_utils import require_nonempty
from origin_sciplot.output_manager import (
    OutputDirectoryError,
    RunOutput,
    create_run_output,
    output_preparation_error,
    write_json,
)
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

MAX_SUMMARY_TEXT_CHARS = 160
MAX_SUMMARY_ITEMS = 16


def _load_runner(runner_path: Path):
    spec = importlib.util.spec_from_file_location("origin_sciplot_template_runner", runner_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load runner: {runner_path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "run"):
        raise RuntimeError(f"Runner {runner_path.name} does not define run()")
    return module


def _load_template_manifest(template_id: str) -> TemplateManifest:
    """Load only the manifest while the manifest progress stage is active."""

    proto.progress("load_template", "running", "正在读取模板 manifest")
    manifest = TemplateRegistry().get(template_id)
    proto.progress("load_template", "success", f"已读取模板：{manifest.name}")
    return manifest


def _run_data_analysis(
    analyzer: Callable[[], Any],
    *,
    success_text: str,
) -> Any:
    """Wrap the data-analysis call without inventing unobservable sub-stages."""

    proto.progress("analyze_data", "running", "正在分析数据与绘图语义")
    result = analyzer()
    proto.progress("analyze_data", "success", success_text)
    return result


def _report_origin_queue_wait(elapsed_seconds: float) -> None:
    proto.progress(
        "origin_job_queue",
        "waiting",
        f"正在等待另一项 Origin 任务结束；已等待 {int(elapsed_seconds)} 秒。",
    )


def _run_origin_draw_export_verify(
    runner_call: Callable[[], Any],
    verifier: Callable[[Any], Mapping[str, Any]],
) -> tuple[Any, Mapping[str, Any]]:
    """Report the renderer as one observable call, then verify its evidence."""

    require_interactive_origin_context()
    proto.progress(
        "launch_origin_draw_export_verify",
        "running",
        "正在启动 Origin、绘图、导出并执行 Origin 反读",
    )
    with origin_job_slot(
        job_kind="render",
        wait_report_interval=30.0,
        on_wait=_report_origin_queue_wait,
    ) as lease:
        if lease.waited:
            proto.progress(
                "origin_job_queue",
                "success",
                "已获得 Origin 使用权，开始当前任务。",
            )
        result = runner_call()
        proto.progress(
            "launch_origin_draw_export_verify",
            "success",
            "Origin 绘图、导出与反读调用已返回",
        )
        proto.progress(
            "verify_outputs",
            "running",
            "正在核对导出文件与 Origin 反读报告",
        )
        compatibility = verifier(result)
        proto.progress(
            "verify_outputs",
            "success",
            "导出文件与 Origin 反读报告校验通过",
        )
    return result, compatibility


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
    parser.add_argument("--visual-style-json")
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
    allowed_keys = {
        frozenset({"adaptation", "expected_report_hash", "locked_palette_id"}),
        frozenset(
            {
                "adaptation",
                "expected_report_hash",
                "locked_palette_id",
                "locked_style_tokens",
            }
        ),
    }
    if not isinstance(payload, dict) or frozenset(payload) not in allowed_keys:
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
    locked_tokens = payload.get("locked_style_tokens", {})
    if not isinstance(locked_tokens, dict):
        raise ScientificWorkflowError(
            "reference_style_json_invalid",
            "The locked visual style is invalid.",
        )
    payload["locked_style_tokens"] = locked_tokens
    return payload


def _parse_visual_style_request(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ScientificWorkflowError(
            "xps_visual_style_json_invalid",
            "The frozen XPS visual-style request is not valid JSON.",
        ) from exc
    if not isinstance(payload, dict) or set(payload) != {"tokens", "expected_report_hash"}:
        raise ScientificWorkflowError(
            "xps_visual_style_json_invalid",
            "The frozen XPS visual-style request has an invalid structure.",
        )
    if not isinstance(payload["tokens"], dict) or not isinstance(
        payload["expected_report_hash"], str
    ):
        raise ScientificWorkflowError(
            "xps_visual_style_json_invalid",
            "The frozen XPS visual-style request is incomplete.",
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
            locked_style_tokens=request.get("locked_style_tokens", {}),
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


def _apply_xps_visual_style_request(
    preparation: Any,
    request: dict[str, Any] | None,
) -> tuple[Any, dict[str, Any] | None]:
    if request is None:
        return preparation, None
    from origin_sciplot.xps_visual_style import (
        XpsVisualStyleError,
        apply_xps_visual_style,
    )

    try:
        application = apply_xps_visual_style(
            preparation,
            request["tokens"],
            source="explicit_user",
        )
    except XpsVisualStyleError as exc:
        raise ScientificWorkflowError(exc.code, str(exc)) from exc
    if application.report["report_hash"] != request["expected_report_hash"]:
        raise ScientificWorkflowError(
            "xps_visual_style_report_mismatch",
            "The worker XPS visual-style decision differs from the approved plan.",
        )
    return application.preparation, application.report


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
    plot_spec = None if scientific_analysis is None else scientific_analysis.plot_spec
    return resolve_activated_optional_capabilities(template_id, plot_spec)


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
    origin_version = environment.get("origin_version", "")
    if str(origin_version).strip().lower() == "unknown":
        origin_version = environment.get("origin_version_raw", "")
    decision = evaluate_template_compatibility(
        manifest.id,
        origin_version,
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


def _record_xps_visual_style(
    output: RunOutput,
    result: Any,
    report: dict[str, Any] | None,
) -> None:
    """Bind the frozen explicit XPS style decision into render evidence."""

    if report is None:
        return
    report_path = output.output_dir / "xps_visual_style_report.json"
    write_json(report_path, report)
    try:
        verify_report = json.loads(
            output.origin_verify_report.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise OriginDrawError(
            "Origin XPS visual-style evidence could not be read",
            code="xps_visual_style_report_invalid",
            stage="xps_visual_style_report",
        ) from exc
    if not isinstance(verify_report, dict):
        raise OriginDrawError(
            "Origin XPS visual-style evidence is invalid",
            code="xps_visual_style_report_invalid",
            stage="xps_visual_style_report",
        )
    verify_report["xps_visual_style"] = report
    write_json(output.origin_verify_report, verify_report)
    if isinstance(result, dict) and isinstance(result.get("verify"), dict):
        result["verify"]["xps_visual_style"] = report


def _summary_text(value: Any) -> str:
    text = "" if value is None else str(value)
    if len(text) <= MAX_SUMMARY_TEXT_CHARS:
        return text
    suffix = "[truncated]"
    return text[: MAX_SUMMARY_TEXT_CHARS - len(suffix)] + suffix


def _summary_items(values: Any) -> tuple[list[str], int, bool]:
    items = tuple(values or ())
    return (
        [_summary_text(value) for value in items[:MAX_SUMMARY_ITEMS]],
        len(items),
        len(items) > MAX_SUMMARY_ITEMS,
    )


def _compact_plot_spec_payload(
    scientific_analysis: Any,
    analysis_report: Path,
) -> dict[str, Any]:
    """Return a bounded plot-spec summary; the full spec stays in its report."""

    spec = scientific_analysis.plot_spec
    series = tuple(getattr(spec, "series", ()) or ())
    labels, series_count, series_truncated = _summary_items(
        getattr(item, "label", "") for item in series
    )
    roles = sorted(
        {
            _summary_text(getattr(item, "series_role", "data"))
            for item in series
        }
    )
    payload: dict[str, Any] = {
        "plot_kind": _summary_text(getattr(spec, "plot_kind", "")),
        "plot_mode": _summary_text(getattr(spec, "plot_mode", "")),
        "x_title": _summary_text(getattr(spec, "x_title", "")),
        "y_title": _summary_text(getattr(spec, "y_title", "")),
        "y2_title": (
            _summary_text(spec.y2_title)
            if getattr(spec, "y2_title", None) is not None
            else None
        ),
        "x_scale": _summary_text(getattr(spec, "x_scale", "")),
        "y_scale": _summary_text(getattr(spec, "y_scale", "")),
        "series": {
            "count": series_count,
            "labels": labels,
            "roles": roles[:MAX_SUMMARY_ITEMS],
            "truncated": series_truncated or len(roles) > MAX_SUMMARY_ITEMS,
        },
        "full_plot_spec": str(analysis_report),
    }
    if getattr(spec, "plot_kind", None) != "circular_network":
        return payload

    layout = getattr(spec, "network_layout", None)
    if layout is None:
        payload["network_layout"] = None
        return payload
    panel_order, panel_count, panel_order_truncated = _summary_items(layout.panel_order)
    node_order, node_count, node_order_truncated = _summary_items(layout.node_order)
    panels = tuple(layout.panels)
    edge_counts = {
        _summary_text(panel.panel): len(panel.edges)
        for panel in panels[:MAX_SUMMARY_ITEMS]
    }
    payload["network_layout"] = {
        "panel_order": panel_order,
        "panel_count": panel_count,
        "panel_order_truncated": panel_order_truncated,
        "node_order": node_order,
        "node_count": node_count,
        "node_order_truncated": node_order_truncated,
        "edge_counts": edge_counts,
        "edge_counts_truncated": len(panels) > MAX_SUMMARY_ITEMS,
        "total_edge_count": sum(len(panel.edges) for panel in panels),
        "weight_scale": layout.weight_scale.to_dict(),
        "sample_count": layout.sample_count,
        "node_radius": layout.node_radius,
        "full_geometry_report": str(analysis_report),
    }
    return payload


def _compact_reference_style_payload(
    report: Mapping[str, Any] | None,
    report_path: Path,
) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "route": _summary_text(report.get("route")),
        "template_id": _summary_text(report.get("template_id")),
        "report_hash": _summary_text(report.get("report_hash")),
        "execution_allowed": report.get("execution_allowed"),
        "applied_count": len(report.get("applied", ())),
        "rejected_count": len(report.get("rejected", ())),
        "retained_template_default_count": len(
            report.get("retained_template_default", ())
        ),
        "full_report": str(report_path),
    }


def _compact_xps_visual_style_payload(
    report: Mapping[str, Any] | None,
    report_path: Path,
) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "source": _summary_text(report.get("source")),
        "report_hash": _summary_text(report.get("report_hash")),
        "execution_allowed": report.get("execution_allowed"),
        "applied_count": len(report.get("applied", ())),
        "rejected_count": len(report.get("rejected", ())),
        "retained_template_default_count": len(
            report.get("retained_template_default", ())
        ),
        "full_report": str(report_path),
    }


def _compact_runner_result(
    result: Mapping[str, Any],
    output: RunOutput,
    compatibility: Mapping[str, Any],
) -> dict[str, Any]:
    """Emit a small success event while keeping full readback on disk.

    Renderer ``verify`` payloads contain every Origin object and can grow to
    tens of thousands of characters.  They are required for audit, but sending
    them through the terminal makes the beginner workflow look stalled or
    noisy.  The authoritative report remains ``origin_verify_report.json``.
    """

    payload = {
        key: result[key]
        for key in ("opju", "png", "pdf", "tif")
        if isinstance(result.get(key), str)
    }
    payload["origin_verify_report"] = str(output.origin_verify_report)
    origin_version = result.get("origin_version")
    if origin_version is None:
        version_payload = compatibility.get("origin_version")
        if isinstance(version_payload, Mapping):
            origin_version = (
                version_payload.get("product_label")
                or version_payload.get("numeric")
                or version_payload.get("raw_numeric")
            )
    if origin_version is not None:
        payload["origin_version"] = origin_version

    verify = result.get("verify")
    if isinstance(verify, Mapping):
        exports = verify.get("exports")
        export_summary = {}
        if isinstance(exports, Mapping):
            export_summary = {
                key: exports[key]
                for key in ("opju", "png", "pdf", "tif")
                if key in exports
                and (
                    exports[key] is None
                    or isinstance(exports[key], (bool, int, float, str))
                )
            }
        payload["verification_summary"] = {
            "template_id": _summary_text(verify.get("template_id")),
            "page_width_cm": verify.get("width_cm"),
            "page_height_cm": verify.get("height_cm"),
            "source_data_modified": verify.get("source_data_modified"),
            "exports": export_summary,
            "full_readback": str(output.origin_verify_report),
        }
    return payload


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = None
    logger = None
    xps_analysis = None
    scientific_analysis = None
    reference_style_report: dict[str, Any] | None = None
    xps_visual_style_report: dict[str, Any] | None = None
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
        visual_style_request = _parse_visual_style_request(args.visual_style_json)
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
            if scientific_text_overrides:
                raise ScientificWorkflowError(
                    "text_overrides_unsupported",
                    "Axis-title overrides are currently available for scientific-table templates only.",
                )
            if args.palette_id and visual_style_request is not None:
                requested_palette = visual_style_request["tokens"].get("palette_id")
                if requested_palette not in {None, args.palette_id}:
                    raise ScientificWorkflowError(
                        "visual_style_conflict",
                        "The frozen XPS palette requests conflict.",
                    )
            elif args.palette_id:
                raise ScientificWorkflowError(
                    "xps_visual_style_report_missing",
                    "An XPS palette must come from a frozen visual-style plan.",
                )

            def analyze_xps() -> tuple[Any, str, str, Any, Any]:
                analysis = prepare_xps(
                    args.input_csv,
                    column_mapping=column_mapping,
                )
                visual_report = None
                if visual_style_request is not None:
                    analysis, visual_report = _apply_xps_visual_style_request(
                        analysis,
                        visual_style_request,
                    )
                analysis, reference_report = _apply_reference_style_request(
                    analysis,
                    reference_style_request,
                )
                return (
                    analysis,
                    select_xps_template_id(analysis),
                    select_xps_renderer_template_id(analysis),
                    visual_report,
                    reference_report,
                )

            (
                xps_analysis,
                selected_template_id,
                selected_renderer_template_id,
                xps_visual_style_report,
                reference_style_report,
            ) = _run_data_analysis(
                analyze_xps,
                success_text="XPS 数据与绘图语义分析完成",
            )
            if xps_analysis.requires_confirmation:
                proto.error(
                    "mapping_confirmation_required",
                    "Column roles are ambiguous. Confirm the XPS column mapping before running Origin.",
                    reasons=list(xps_analysis.confirmation_reasons),
                )
                return WorkerExitCode.VALIDATION_FAILED

        manifest = _load_template_manifest(selected_template_id)
        if manifest.workflow == "scientific_table":
            if visual_style_request is not None:
                raise ScientificWorkflowError(
                    "visual_style_template_unsupported",
                    "Exact visual-style JSON is currently implemented for XPS only.",
                )
            def analyze_scientific() -> tuple[Any, dict[str, Any] | None]:
                analysis = prepare_scientific(
                    args.input_csv,
                    manifest.id,
                    column_mapping=scientific_mapping,
                )
                if scientific_text_overrides:
                    analysis = apply_scientific_text_overrides(
                        analysis,
                        x_title=scientific_text_overrides.get("x_title"),
                        y_title=scientific_text_overrides.get("y_title"),
                    )
                if args.palette_id:
                    analysis = apply_scientific_palette_override(
                        analysis,
                        palette_id=args.palette_id,
                    )
                return _apply_reference_style_request(
                    analysis,
                    reference_style_request,
                )

            scientific_analysis, reference_style_report = (
                _run_data_analysis(
                    analyze_scientific,
                    success_text="数据角色与绘图语义分析完成",
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

        # Keep all read-only plan and data checks in the sandbox. Request the
        # host's formal current-user approval only after those checks pass and
        # before creating a delivery folder; the Origin seam checks again as
        # defense in depth.
        require_interactive_origin_context()
        proto.progress("create_output_dir", "running", "正在创建输出文件夹")
        try:
            output = create_run_output(args.input_csv, manifest, args.output_dir)
            if render_plan_source is not None:
                shutil.copy2(render_plan_source, output.render_plan_copy)
            logger = RunLogger(output.run_log, output.output_dir)
            logger.write(f"template={manifest.id} version={manifest.version}")
            if xps_analysis is not None:
                write_json(
                    output.output_dir / "xps_analysis_report.json",
                    xps_analysis.to_dict(),
                )
                copied_source_sha256 = hashlib.sha256(output.input_copy.read_bytes()).hexdigest()
                if copied_source_sha256 != xps_analysis.source_sha256:
                    logger.write("XPS source changed while creating the provenance copy")
                    proto.error(
                        "analysis_changed",
                        "The XPS analysis changed after preview. Refresh the preview and run again.",
                    )
                    return WorkerExitCode.VALIDATION_FAILED
                if xps_visual_style_report is not None:
                    write_json(
                        output.output_dir / "xps_visual_style_report.json",
                        xps_visual_style_report,
                    )
                if reference_style_report is not None:
                    write_json(
                        output.output_dir / "reference_style_report.json",
                        reference_style_report,
                    )
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
        except OutputDirectoryError:
            raise
        except OSError as exc:
            raise output_preparation_error(exc) from exc
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

        runner = _load_runner(manifest.runner_path)
        runner_options = {"keep_origin_open": args.keep_origin_open}
        if xps_analysis is not None:
            runner_options["preparation"] = xps_analysis
        elif scientific_analysis is not None:
            runner_options["preparation"] = scientific_analysis

        def verify_runner_result(result_payload: Any) -> Mapping[str, Any]:
            _record_xps_visual_style(
                output,
                result_payload,
                xps_visual_style_report,
            )
            _record_reference_style(
                output,
                result_payload,
                reference_style_report,
            )
            compatibility_payload = _record_template_compatibility(
                output,
                manifest,
                scientific_analysis,
            )
            _validate_runner_result(
                manifest,
                output,
                result_payload,
            )
            return compatibility_payload

        result, compatibility = _run_origin_draw_export_verify(
            lambda: runner.run(
                manifest,
                validation_frame,
                output,
                logger,
                **runner_options,
            ),
            verify_runner_result,
        )
        done_payload = _compact_runner_result(result, output, compatibility)
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
                    "xps_visual_style_summary": _compact_xps_visual_style_payload(
                        xps_visual_style_report,
                        output.output_dir / "xps_visual_style_report.json",
                    ),
                    "reference_style_summary": _compact_reference_style_payload(
                        reference_style_report,
                        output.output_dir / "reference_style_report.json",
                    ),
                }
            )
        elif scientific_analysis is not None:
            analysis_report = (
                output.output_dir / f"{manifest.id}_analysis_report.json"
            )
            done_payload.update(
                {
                    "plan_digest": scientific_analysis.plan_digest,
                    "plot_spec_summary": _compact_plot_spec_payload(
                        scientific_analysis,
                        analysis_report,
                    ),
                    "selected_renderer_template_id": selected_renderer_template_id,
                    "reference_style_summary": _compact_reference_style_payload(
                        reference_style_report,
                        output.output_dir / "reference_style_report.json",
                    ),
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
    except OutputDirectoryError as exc:
        proto.error(exc.code, str(exc), stage="create_output_dir")
        return WorkerExitCode.VALIDATION_FAILED
    except OriginEnvironmentError as exc:
        if logger:
            logger.write(
                "Origin environment error "
                f"[{exc.code}/{exc.stage}]: {safe_error_message(exc)}"
            )
        recovery = origin_activation_recovery(exc.code)
        diagnostics = structured_error_diagnostics(exc)
        proto.error(
            exc.code,
            safe_error_message(exc),
            stage=exc.stage,
            **({"diagnostics": diagnostics} if diagnostics else {}),
            **({"recovery": recovery} if recovery is not None else {}),
        )
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
