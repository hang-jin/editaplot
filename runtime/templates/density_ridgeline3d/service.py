"""Local service factory for the verified 3D density-ridgeline route."""

from origin_sciplot.template_service import ScientificTemplateService


def create_service(manifest):
    return ScientificTemplateService(manifest)
