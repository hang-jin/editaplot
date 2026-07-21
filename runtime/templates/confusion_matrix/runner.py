"""Editable Origin runner for confusion matrices."""

from origin_sciplot.origin_backend.categorical_renderer import run_categorical_template


def run(manifest, frame, output, logger, *, keep_origin_open=True, preparation=None):
    return run_categorical_template(
        manifest,
        frame,
        output,
        logger,
        keep_origin_open=keep_origin_open,
        preparation=preparation,
    )
