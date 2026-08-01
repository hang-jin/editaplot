"""Experimental runner entry point for circular directed networks."""


def run(manifest, frame, output, logger, *, keep_origin_open=True, preparation=None):
    # Import lazily so manifest discovery remains safe until the Origin renderer
    # has passed its isolated acceptance gate and is added to the runtime.
    from origin_sciplot.origin_backend.network_renderer import run_network_template

    return run_network_template(
        manifest,
        frame,
        output,
        logger,
        keep_origin_open=keep_origin_open,
        preparation=preparation,
    )
