"""Editable Origin runner for histogram plots."""

from origin_sciplot.origin_backend.evidence_renderer import run_evidence_template


def run(manifest, frame, output, logger, *, keep_origin_open=True, preparation=None):
    return run_evidence_template(
        manifest,
        frame,
        output,
        logger,
        keep_origin_open=keep_origin_open,
        preparation=preparation,
    )
