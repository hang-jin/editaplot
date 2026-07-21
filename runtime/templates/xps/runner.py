"""Public XPS runner that delegates an immutable plan to an internal renderer."""

from __future__ import annotations

import importlib.util
from types import ModuleType

from origin_sciplot.logging_utils import RunLogger
from origin_sciplot.output_manager import RunOutput
from origin_sciplot.template_registry import TemplateManifest, TemplateRegistry
from origin_sciplot.xps_workflow import XpsPreparation, prepare_xps


def _load_adapter(manifest: TemplateManifest) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"origin_sciplot_xps_adapter_{manifest.id}", manifest.runner_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load XPS renderer adapter: {manifest.id}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(
    manifest: TemplateManifest,
    frame,
    output: RunOutput,
    logger: RunLogger,
    *,
    keep_origin_open: bool = True,
    preparation: XpsPreparation | None = None,
) -> dict:
    resolved = preparation if preparation is not None else prepare_xps(output.input_copy)
    profile = resolved.plot_spec.visual_profile
    adapter_id = (
        "xps_c1s_fit" if profile == "fixed_c1s_publication" else "xps_adaptive"
    )
    adapter_manifest = TemplateRegistry().get(adapter_id)
    adapter = _load_adapter(adapter_manifest)
    return adapter.run(
        manifest,
        frame,
        output,
        logger,
        keep_origin_open=keep_origin_open,
        preparation=resolved,
    )
