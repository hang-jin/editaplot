"""Local service factory for the public XPS template."""

from origin_sciplot.template_service import XpsTemplateService


def create_service(manifest):
    return XpsTemplateService(manifest)
