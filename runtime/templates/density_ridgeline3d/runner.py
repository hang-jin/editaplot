"""Verified editable Origin runner for dual-profile 3D density ridgelines."""

from origin_sciplot.origin_backend.density_ridgeline3d_renderer import (
    run_density_ridgeline3d_template,
)


def run(manifest, frame, output, logger, *, keep_origin_open=True, preparation=None):
    return run_density_ridgeline3d_template(
        manifest,
        frame,
        output,
        logger,
        keep_origin_open=keep_origin_open,
        preparation=preparation,
    )
