"""Local service factory for verified 3D multi-condition trajectories."""

from origin_sciplot.template_service import ScientificTemplateService


def create_service(manifest):
    return ScientificTemplateService(manifest)
