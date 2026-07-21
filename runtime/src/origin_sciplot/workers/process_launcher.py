"""Build the subprocess command used by the GUI to run the worker."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from collections.abc import Callable
from pathlib import Path
from typing import TextIO


WORKER_MODULE = "origin_sciplot.workers.run_template_worker"
INTERNAL_WORKER_FLAG = "--run-worker"
STD_OUTPUT_HANDLE = -11
STD_ERROR_HANDLE = -12


def _open_windows_standard_stream(handle_id: int) -> TextIO | None:
    """Recreate a text stream for a PyInstaller windowed child process pipe."""
    if os.name != "nt":
        return None
    import ctypes
    import msvcrt

    kernel32 = ctypes.windll.kernel32
    kernel32.GetStdHandle.restype = ctypes.c_void_p
    handle = kernel32.GetStdHandle(handle_id)
    invalid_handle = ctypes.c_void_p(-1).value
    if handle in (None, 0, invalid_handle):
        return None
    try:
        descriptor = msvcrt.open_osfhandle(int(handle), os.O_WRONLY)
        return os.fdopen(
            descriptor,
            "w",
            buffering=1,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return None


def prepare_frozen_worker_stdio(
    stream_factory: Callable[[int], TextIO | None] | None = None,
) -> None:
    """Make the JSON-lines worker protocol usable from a windowed frozen EXE."""
    factory = stream_factory or _open_windows_standard_stream
    if sys.stdout is None:
        sys.stdout = factory(STD_OUTPUT_HANDLE) or open(  # noqa: SIM115 - process lifetime
            os.devnull, "w", encoding="utf-8"
        )
    if sys.stderr is None:
        sys.stderr = factory(STD_ERROR_HANDLE) or open(  # noqa: SIM115 - process lifetime
            os.devnull, "w", encoding="utf-8"
        )


def build_worker_command(
    executable: str,
    template_id: str = "auto",
    input_csv: str | Path | None = None,
    *,
    keep_origin_open: bool,
    frozen: bool,
    expected_plan_digest: str | None = None,
    column_mapping: Mapping[str, object] | None = None,
) -> tuple[str, list[str]]:
    """Return a source-mode or PyInstaller-safe worker command."""
    if input_csv is None:
        raise ValueError("input_csv is required")
    worker_args = [
        "--template-id",
        template_id,
        "--input-csv",
        str(input_csv),
    ]
    if expected_plan_digest is not None:
        worker_args.extend(["--expected-plan-digest", expected_plan_digest])
    if column_mapping is not None:
        worker_args.extend(
            [
                "--column-mapping-json",
                json.dumps(column_mapping, ensure_ascii=True, separators=(",", ":")),
            ]
        )
    worker_args.append("--keep-origin-open" if keep_origin_open else "--close-origin")
    if frozen:
        return executable, [INTERNAL_WORKER_FLAG, *worker_args]
    return executable, ["-m", WORKER_MODULE, *worker_args]
