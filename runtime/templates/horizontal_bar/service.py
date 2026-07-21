"""Local service factory for horizontal grouped bars."""

from origin_sciplot.template_service import ScientificTemplateService


def create_service(manifest):
    return ScientificTemplateService(manifest)
