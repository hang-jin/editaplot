"""Use the common read-only scientific table service."""

from origin_sciplot.template_service import ScientificTemplateService


def create_service(manifest):
    return ScientificTemplateService(manifest)
