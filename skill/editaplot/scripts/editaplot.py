#!/usr/bin/env python
"""Command-line entry point used by the EditaPlot Codex Skill."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from editaplot_core import (
    EditaPlotError,
    build_medical_panel_plan,
    build_origin_smoke_command,
    build_plan,
    build_worker_command,
    catalog,
    doctor,
    inspect_data,
    inspect_reference,
    load_json,
    palette_catalog,
    recommend_charts,
    repair_environment,
    review_reference_figure,
    start_session,
    understand_data,
    verify_output,
    write_json,
)


def _engine_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--engine-home",
        help="Source engine root; defaults to EDITAPLOT_ENGINE_HOME or local discovery.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EditaPlot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="Check local analysis/render prerequisites")
    doctor_parser.add_argument(
        "--repair",
        action="store_true",
        help="Create a project-local environment and install audited Python dependencies only.",
    )
    _engine_option(doctor_parser)

    repair_parser = subparsers.add_parser(
        "repair-environment",
        help=argparse.SUPPRESS,
    )
    _engine_option(repair_parser)

    catalog_parser = subparsers.add_parser("catalog", help="List verified public Origin routes")
    _engine_option(catalog_parser)

    palettes_parser = subparsers.add_parser("palettes", help="List Chinese-first scientific palettes")
    palettes_parser.add_argument("--all", action="store_true", help="Include advanced palettes")
    _engine_option(palettes_parser)

    inspect_parser = subparsers.add_parser("inspect", help="Profile a table without modifying it")
    inspect_parser.add_argument("input_file")
    inspect_parser.add_argument("--output")
    _engine_option(inspect_parser)

    start_parser = subparsers.add_parser(
        "start",
        help="Open a read-only beginner session and ask for scientific confirmation",
    )
    start_parser.add_argument("input_file")
    start_parser.add_argument("--intent", default="")
    start_parser.add_argument("--limit", type=int, default=3)
    start_parser.add_argument("--output")
    _engine_option(start_parser)

    recommend_parser = subparsers.add_parser("recommend", help="Rank suitable verified templates")
    recommend_parser.add_argument("input_file")
    recommend_parser.add_argument("--intent", default="")
    recommend_parser.add_argument("--limit", type=int, default=3)
    recommend_parser.add_argument("--output")
    _engine_option(recommend_parser)

    reference_inspect_parser = subparsers.add_parser(
        "reference-inspect",
        help="Validate a local reference image without OCR or rendering",
    )
    reference_inspect_parser.add_argument("reference_image")
    reference_inspect_parser.add_argument("--output")
    _engine_option(reference_inspect_parser)

    reference_review_parser = subparsers.add_parser(
        "reference-review",
        help="Validate a declarative reference-figure grammar and request confirmation",
    )
    reference_review_parser.add_argument("reference_image")
    reference_review_parser.add_argument("reference_spec_json")
    reference_review_parser.add_argument("--output")
    _engine_option(reference_review_parser)

    understand_parser = subparsers.add_parser(
        "understand",
        help="Explain every source column and proposed figure element before planning",
    )
    understand_parser.add_argument("input_file")
    understand_parser.add_argument("--template-id", required=True)
    understand_parser.add_argument("--mapping-json", help="Confirmed assignments/context JSON")
    understand_parser.add_argument("--output")
    _engine_option(understand_parser)

    plan_parser = subparsers.add_parser("plan", help="Freeze a selected template and figure contract")
    plan_parser.add_argument("input_file")
    plan_parser.add_argument("--template-id", required=True)
    plan_parser.add_argument("--claim", required=True)
    plan_parser.add_argument("--evidence-role", default="comparison")
    plan_parser.add_argument("--intent", default="")
    plan_parser.add_argument("--x-title")
    plan_parser.add_argument("--y-title")
    plan_parser.add_argument("--palette-id", help="Freeze a compatible palette from `palettes`")
    plan_parser.add_argument(
        "--target-output",
        default="editable Origin figure and publication exports",
    )
    plan_parser.add_argument("--mapping-json", help="Confirmed assignments/context JSON")
    plan_parser.add_argument(
        "--semantic-confirmation-json",
        required=True,
        help="Explicit confirmation bound to the latest `understand` proposal hash",
    )
    plan_parser.add_argument("--reference-image")
    plan_parser.add_argument("--reference-spec-json")
    plan_parser.add_argument("--reference-confirmation-json")
    plan_parser.add_argument(
        "--reference-route",
        choices=("template_adaptation", "controlled_composition"),
        default="template_adaptation",
    )
    plan_parser.add_argument("--reference-bindings-json")
    plan_parser.add_argument("--output", required=True)
    _engine_option(plan_parser)

    render_parser = subparsers.add_parser(
        "render",
        help="Execute an approved render plan through the local Origin application",
    )
    render_parser.add_argument("plan_file")
    render_parser.add_argument("--python", dest="python_executable")
    render_parser.add_argument("--output-dir")
    render_parser.add_argument("--close-origin", action="store_true")
    _engine_option(render_parser)

    smoke_parser = subparsers.add_parser(
        "origin-smoke",
        help="Test an EditaPlot-owned Origin instance and the full minimal export loop",
    )
    smoke_parser.add_argument("--output-dir", required=True)
    smoke_parser.add_argument("--python", dest="python_executable")
    smoke_parser.add_argument("--keep-origin-open", action="store_true")
    _engine_option(smoke_parser)

    verify_parser = subparsers.add_parser("verify", help="Check required Origin run artifacts")
    verify_parser.add_argument("output_directory")
    verify_parser.add_argument("--output")

    panel_parser = subparsers.add_parser(
        "panel-plan",
        help="Freeze a deidentification-aware medical multi-panel layout plan",
    )
    panel_parser.add_argument("config_file")
    panel_parser.add_argument("--claim", required=True)
    panel_parser.add_argument("--title", default="Medical imaging & AI evidence")
    panel_parser.add_argument("--output", required=True)
    return parser


def _emit(payload: dict[str, Any], output: str | None = None) -> None:
    if output:
        write_json(output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)


def _paths_refer_to_same_file(left: str | Path, right: str | Path) -> bool:
    left_path = Path(left).expanduser()
    right_path = Path(right).expanduser()
    try:
        if left_path.resolve() == right_path.resolve():
            return True
        if left_path.exists() and right_path.exists():
            return os.path.samefile(left_path, right_path)
    except OSError:
        return False
    return False


def _ensure_output_does_not_replace_paths(
    output: str | None,
    protected_paths: list[str | Path],
    *,
    code: str,
    message: str,
) -> None:
    if not output:
        return
    conflict = next(
        (path for path in protected_paths if _paths_refer_to_same_file(path, output)),
        None,
    )
    if conflict is not None:
        raise EditaPlotError(
            code,
            message,
            protected_path=str(Path(conflict).expanduser().resolve()),
        )


def _ensure_output_does_not_replace_input(
    input_path: str | None,
    output: str | None,
) -> None:
    if not input_path:
        return
    _ensure_output_does_not_replace_paths(
        output,
        [input_path],
        code="source_output_conflict",
        message="A JSON output cannot replace the command's input file.",
    )


def _ensure_verify_output_does_not_replace_artifact(
    output_directory: str,
    output: str | None,
) -> None:
    directory = Path(output_directory).expanduser()
    required = [
        directory / name
        for name in (
            "result.png",
            "result.pdf",
            "result.tif",
            "result.opju",
            "origin_verify_report.json",
            "validation_report.json",
        )
    ]
    _ensure_output_does_not_replace_paths(
        output,
        required,
        code="verification_artifact_output_conflict",
        message="A verification JSON output cannot replace a required Origin artifact.",
    )


def _run_render(args: argparse.Namespace) -> int:
    plan = load_json(args.plan_file)
    command, env, engine_root = build_worker_command(
        plan,
        plan_file=args.plan_file,
        engine_home=args.engine_home,
        python_executable=args.python_executable,
        output_dir=args.output_dir,
        close_origin=args.close_origin,
    )
    start_event = {
        "type": "editaplot_render_start",
        "engine_home": str(engine_root),
        "template_id": plan["template"]["id"],
        "source_sha256": plan["source"]["sha256"],
        "origin_callability_check": "worker_connection",
    }
    print(json.dumps(start_event, ensure_ascii=False), flush=True)
    process = subprocess.Popen(  # noqa: S603 - fixed module invocation, never shell=True
        command,
        cwd=str(engine_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout = process.stdout
    if stdout is None:
        process.kill()
        raise EditaPlotError("worker_pipe_missing", "Could not read the Origin worker output stream.")
    for line in stdout:
        print(line.rstrip("\r\n"), flush=True)
    return int(process.wait())


def _run_origin_smoke(args: argparse.Namespace) -> int:
    command, env, engine_root = build_origin_smoke_command(
        output_dir=args.output_dir,
        engine_home=args.engine_home,
        python_executable=args.python_executable,
        keep_origin_open=args.keep_origin_open,
    )
    print(
        json.dumps(
            {
                "type": "editaplot_origin_smoke_start",
                "engine_home": str(engine_root),
                "connection_mode": "new_isolated",
                "output_dir": str(Path(args.output_dir).expanduser().resolve()),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    process = subprocess.Popen(  # noqa: S603 - fixed module invocation, never shell=True
        command,
        cwd=str(engine_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout = process.stdout
    if stdout is None:
        process.kill()
        raise EditaPlotError(
            "worker_pipe_missing",
            "Could not read the Origin smoke worker output stream.",
        )
    for line in stdout:
        print(line.rstrip("\r\n"), flush=True)
    return int(process.wait())


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            before = doctor(engine_home=args.engine_home)
            if args.repair and not before["ready_for_render"]:
                if before["automatic_repair"]["available"]:
                    _emit(
                        {
                            "schema_version": "1.0",
                            "ok": True,
                            "before": before,
                            "repair": repair_environment(engine_home=args.engine_home),
                        }
                    )
                elif before["missing_python_dependencies"]:
                    raise EditaPlotError(
                        "automatic_repair_unavailable",
                        "Project-local dependency repair is unavailable for the reported blockers.",
                        manual_blockers=before["manual_blockers"],
                        supported_python=before["automatic_repair"]["supported_python"],
                    )
                else:
                    _emit(before)
            else:
                _emit(before)
        elif args.command == "repair-environment":
            _emit(repair_environment(engine_home=args.engine_home))
        elif args.command == "catalog":
            _emit(catalog(engine_home=args.engine_home))
        elif args.command == "palettes":
            _emit(
                palette_catalog(
                    engine_home=args.engine_home,
                    public_only=not args.all,
                )
            )
        elif args.command == "inspect":
            _ensure_output_does_not_replace_input(args.input_file, args.output)
            _emit(
                inspect_data(args.input_file, engine_home=args.engine_home),
                args.output,
            )
        elif args.command == "start":
            _ensure_output_does_not_replace_input(args.input_file, args.output)
            _emit(
                start_session(
                    args.input_file,
                    intent=args.intent,
                    engine_home=args.engine_home,
                    limit=args.limit,
                ),
                args.output,
            )
        elif args.command == "recommend":
            _ensure_output_does_not_replace_input(args.input_file, args.output)
            _emit(
                recommend_charts(
                    args.input_file,
                    intent=args.intent,
                    engine_home=args.engine_home,
                    limit=args.limit,
                ),
                args.output,
            )
        elif args.command == "reference-inspect":
            _ensure_output_does_not_replace_input(args.reference_image, args.output)
            _emit(
                inspect_reference(
                    args.reference_image,
                    engine_home=args.engine_home,
                ),
                args.output,
            )
        elif args.command == "reference-review":
            _ensure_output_does_not_replace_input(args.reference_image, args.output)
            _ensure_output_does_not_replace_input(args.reference_spec_json, args.output)
            _emit(
                review_reference_figure(
                    args.reference_image,
                    load_json(args.reference_spec_json),
                    engine_home=args.engine_home,
                ),
                args.output,
            )
        elif args.command == "understand":
            _ensure_output_does_not_replace_input(args.input_file, args.output)
            _ensure_output_does_not_replace_input(args.mapping_json, args.output)
            mapping = load_json(args.mapping_json) if args.mapping_json else None
            _emit(
                understand_data(
                    args.input_file,
                    template_id=args.template_id,
                    mapping=mapping,
                    engine_home=args.engine_home,
                ),
                args.output,
            )
        elif args.command == "plan":
            _ensure_output_does_not_replace_input(args.input_file, args.output)
            _ensure_output_does_not_replace_input(args.mapping_json, args.output)
            _ensure_output_does_not_replace_input(
                args.semantic_confirmation_json,
                args.output,
            )
            for reference_input in (
                args.reference_image,
                args.reference_spec_json,
                args.reference_confirmation_json,
                args.reference_bindings_json,
            ):
                _ensure_output_does_not_replace_input(reference_input, args.output)
            mapping = load_json(args.mapping_json) if args.mapping_json else None
            semantic_confirmation = load_json(args.semantic_confirmation_json)
            reference_spec = (
                load_json(args.reference_spec_json)
                if args.reference_spec_json
                else None
            )
            reference_confirmation = (
                load_json(args.reference_confirmation_json)
                if args.reference_confirmation_json
                else None
            )
            reference_bindings = (
                load_json(args.reference_bindings_json)
                if args.reference_bindings_json
                else None
            )
            payload = build_plan(
                args.input_file,
                template_id=args.template_id,
                claim=args.claim,
                evidence_role=args.evidence_role,
                target_output=args.target_output,
                intent=args.intent,
                x_title=args.x_title,
                y_title=args.y_title,
                palette_id=args.palette_id,
                mapping=mapping,
                semantic_confirmation=semantic_confirmation,
                reference_image=args.reference_image,
                reference_spec=reference_spec,
                reference_confirmation=reference_confirmation,
                reference_route=args.reference_route,
                reference_bindings=reference_bindings,
                engine_home=args.engine_home,
            )
            _emit(payload, args.output)
        elif args.command == "render":
            return _run_render(args)
        elif args.command == "origin-smoke":
            return _run_origin_smoke(args)
        elif args.command == "verify":
            _ensure_verify_output_does_not_replace_artifact(args.output_directory, args.output)
            _emit(verify_output(args.output_directory), args.output)
        elif args.command == "panel-plan":
            _ensure_output_does_not_replace_input(args.config_file, args.output)
            _emit(
                build_medical_panel_plan(
                    args.config_file,
                    claim=args.claim,
                    title=args.title,
                ),
                args.output,
            )
        else:  # pragma: no cover - argparse enforces a command
            raise EditaPlotError("command_unknown", f"Unknown command: {args.command}")
        return 0
    except EditaPlotError as exc:
        print(json.dumps(exc.to_dict(), ensure_ascii=False, indent=2), file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": {"code": "cancelled"}}), file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
