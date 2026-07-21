"""Local service factory for forest plots."""

from origin_sciplot.template_service import ScientificTemplateService


def create_service(manifest):
    return ScientificTemplateService(manifest)
