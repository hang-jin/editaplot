"""Run the isolated Origin compatibility smoke test in a subprocess."""

from __future__ import annotations

import argparse
from pathlib import Path

from origin_sciplot.origin_backend.safe_errors import (
    OriginDrawError,
    OriginEnvironmentError,
    OriginExportError,
    WorkerExitCode,
    safe_error_message,
)
from origin_sciplot.origin_backend.smoke_test import run_origin_smoke

from . import progress_protocol as proto


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the EditaPlot Origin smoke test")
    parser.add_argument("--output-dir", required=True)
    parser.set_defaults(keep_origin_open=False)
    parser.add_argument("--keep-origin-open", dest="keep_origin_open", action="store_true")
    parser.add_argument("--close-origin", dest="keep_origin_open", action="store_false")
    return parser


def _report_path(output_dir: str | Path) -> str | None:
    candidate = Path(output_dir).expanduser().resolve() / "compatibility-report.json"
    return str(candidate) if candidate.is_file() else None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    proto.progress(
        "origin_smoke",
        "running",
        "正在启动专用 Origin 实例并检查最小绘图闭环。",
    )
    try:
        result = run_origin_smoke(
            args.output_dir,
            keep_open=args.keep_origin_open,
        )
    except OriginEnvironmentError as exc:
        proto.error(
            exc.code,
            safe_error_message(exc),
            stage=exc.stage,
            compatibility_report=_report_path(args.output_dir),
        )
        return WorkerExitCode.ORIGIN_ENVIRONMENT
    except OriginDrawError as exc:
        proto.error(
            exc.code,
            safe_error_message(exc),
            stage=exc.stage,
            compatibility_report=_report_path(args.output_dir),
        )
        return WorkerExitCode.ORIGIN_DRAW
    except OriginExportError as exc:
        proto.error(
            exc.code,
            safe_error_message(exc),
            stage=exc.stage,
            compatibility_report=_report_path(args.output_dir),
        )
        return WorkerExitCode.EXPORT_FAILED
    except Exception:  # noqa: BLE001 - never expose unexpected local exception details
        proto.error(
            "origin_smoke_unexpected",
            "Origin smoke test failed",
            stage="unknown",
            compatibility_report=_report_path(args.output_dir),
        )
        return WorkerExitCode.UNKNOWN

    proto.done(
        status="passed",
        message="Origin 最小绘图闭环已通过。",
        **{
            key: value
            for key, value in result.items()
            if key not in {"status", "verify"}
        },
    )
    return WorkerExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
