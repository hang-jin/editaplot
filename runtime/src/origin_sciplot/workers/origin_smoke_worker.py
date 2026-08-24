"""Run the isolated Origin compatibility smoke test in a subprocess."""

from __future__ import annotations

import argparse
from pathlib import Path

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


def _report_queue_wait(elapsed_seconds: float) -> None:
    proto.progress(
        "origin_job_queue",
        "waiting",
        f"正在等待另一项 Origin 任务结束；已等待 {int(elapsed_seconds)} 秒。",
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        require_interactive_origin_context()
        proto.progress(
            "origin_smoke",
            "running",
            "正在启动专用 Origin 实例并检查最小绘图闭环。",
        )
        with origin_job_slot(
            job_kind="smoke",
            wait_report_interval=30.0,
            on_wait=_report_queue_wait,
        ) as lease:
            if lease.waited:
                proto.progress(
                    "origin_job_queue",
                    "success",
                    "已获得 Origin 使用权，开始当前任务。",
                )
            result = run_origin_smoke(
                args.output_dir,
                keep_open=args.keep_origin_open,
            )
    except OriginEnvironmentError as exc:
        recovery = origin_activation_recovery(exc.code)
        diagnostics = structured_error_diagnostics(exc)
        proto.error(
            exc.code,
            safe_error_message(exc),
            stage=exc.stage,
            compatibility_report=_report_path(args.output_dir),
            **({"diagnostics": diagnostics} if diagnostics else {}),
            **({"recovery": recovery} if recovery is not None else {}),
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
