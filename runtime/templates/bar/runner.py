"""Editable Origin runner for grouped bars with optional errors."""

from origin_sciplot.origin_backend.scientific_renderer import run_scientific_template


def run(manifest, frame, output, logger, *, keep_origin_open=True, preparation=None):
    return run_scientific_template(
        manifest,
        frame,
        output,
        logger,
        keep_origin_open=keep_origin_open,
        preparation=preparation,
    )

