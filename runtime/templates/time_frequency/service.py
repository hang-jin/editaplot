"""Shared read-only table service for upstream time-frequency values."""

from origin_sciplot.template_service import ScientificTemplateService


def create_service(manifest):
    return ScientificTemplateService(manifest)
