from __future__ import annotations

import ast
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
MAIN_WINDOW = PRODUCT_ROOT / "runtime" / "src" / "origin_sciplot" / "main_window.py"


def _source_segment(name: str, *, class_name: str | None = None) -> str:
    source = MAIN_WINDOW.read_text(encoding="utf-8")
    tree = ast.parse(source)
    nodes: list[ast.AST] = list(tree.body)
    if class_name is not None:
        owner = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        nodes = list(owner.body)
    function = next(
        node
        for node in nodes
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )
    segment = ast.get_source_segment(source, function)
    assert segment is not None
    return segment


def test_gui_worker_inherits_windows_environment_and_forces_utf8() -> None:
    helper = _source_segment("_worker_process_environment")

    assert "QProcessEnvironment.systemEnvironment()" in helper
    assert 'environment.value("PYTHONPATH", "")' in helper
    assert '"PYTHONPATH"' in helper
    assert 'environment.insert("PYTHONIOENCODING", "utf-8")' in helper


def test_gui_worker_handles_failed_start_and_restores_controls() -> None:
    start = _source_segment("_start_worker", class_name="MainWindow")
    handler = _source_segment("_worker_error", class_name="MainWindow")

    assert "setProcessEnvironment(_worker_process_environment())" in start
    assert "errorOccurred.connect(self._worker_error)" in start
    assert "QProcess.FailedToStart" in handler
    assert "self.stop_btn.setEnabled(False)" in handler
    assert "self.run_btn_set_enabled(" in handler
    assert "worker_start_failed" in handler
    assert "Windows 安全软件" in handler
