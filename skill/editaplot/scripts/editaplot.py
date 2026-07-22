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
    build_plan,
    build_worker_command,
    catalog,
    doctor,
    inspect_data,
    load_json,
    palette_catalog,
    recommend_charts,
    repair_environment,
    start_session,
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
        elif args.command == "plan":
            _ensure_output_does_not_replace_input(args.input_file, args.output)
            _ensure_output_does_not_replace_input(args.mapping_json, args.output)
            mapping = load_json(args.mapping_json) if args.mapping_json else None
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
                engine_home=args.engine_home,
            )
            _emit(payload, args.output)
        elif args.command == "render":
            return _run_render(args)
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
