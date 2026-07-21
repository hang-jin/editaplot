"""Verified editable Origin runner for 3D multi-condition trajectories."""

from origin_sciplot.origin_backend.trajectory3d_renderer import run_trajectory3d_template


def run(manifest, frame, output, logger, *, keep_origin_open=True, preparation=None):
    return run_trajectory3d_template(
        manifest,
        frame,
        output,
        logger,
        keep_origin_open=keep_origin_open,
        preparation=preparation,
    )
