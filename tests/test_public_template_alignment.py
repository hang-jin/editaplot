from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SRC = ROOT / "runtime" / "src"
SKILL_SCRIPTS = ROOT / "skill" / "editaplot" / "scripts"
for path in (RUNTIME_SRC, SKILL_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from editaplot_core import VERIFIED_TEMPLATE_IDS  # noqa: E402
from origin_sciplot.scientific_workflow import (  # noqa: E402
    SUPPORTED_SCIENTIFIC_TEMPLATE_IDS,
)
from origin_sciplot.template_registry import TemplateRegistry  # noqa: E402


def test_public_template_registry_matches_verified_skill_routes() -> None:
    registry = TemplateRegistry(ROOT / "runtime" / "templates")
    public_implemented = {manifest.id for manifest in registry.implemented()}

    assert len(public_implemented) == 45
    assert public_implemented == VERIFIED_TEMPLATE_IDS
    assert {manifest.id for manifest in registry.internal_implemented()} == {
        "xps_adaptive",
        "xps_c1s_fit",
    }


def test_scientific_table_routes_match_public_routes_except_xps_router() -> None:
    registry = TemplateRegistry(ROOT / "runtime" / "templates")
    implemented_scientific = {
        manifest.id for manifest in registry.implemented() if manifest.workflow == "scientific_table"
    }
    assert implemented_scientific == VERIFIED_TEMPLATE_IDS - {"xps"}
    assert SUPPORTED_SCIENTIFIC_TEMPLATE_IDS >= implemented_scientific
    for template_id in SUPPORTED_SCIENTIFIC_TEMPLATE_IDS - implemented_scientific:
        manifest = registry.get(template_id)
        assert manifest.status == "planned"
        assert manifest.visibility == "public"
        assert manifest.workflow == "scientific_table"
