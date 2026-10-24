from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "runtime/src"), str(ROOT / "skill/editaplot/scripts")]

from editaplot_core import _prepare_with_mapping, build_plan, understand_data  # noqa: E402
from origin_sciplot.template_registry import TemplateRegistry  # noqa: E402
from origin_sciplot.template_service import ScientificTemplateService  # noqa: E402


def test_explicit_agreement_mapping_bypasses_strict_automatic_header_detection(tmp_path):
    source = tmp_path / "agreement.csv"
    pd.DataFrame(
        {"c0": [1, 2, 3], "c1": [0.2, -0.1, 0.4], "c2": [0.2] * 3, "c3": [-0.5] * 3, "c4": [0.9] * 3}
    ).to_csv(source, index=False)
    mapping = {
        "assignments": {"c0": "mean", "c1": "difference", "c2": "bias", "c3": "loa_lower", "c4": "loa_upper"}
    }
    understood = understand_data(
        source, template_id="bland_altman", mapping=mapping, engine_home=ROOT / "runtime"
    )
    confirmation = understood["confirmation_gate"]["confirmation_payload_template"]
    result = build_plan(
        source,
        template_id="bland_altman",
        mapping=mapping,
        engine_home=ROOT / "runtime",
        claim="Supplied agreement values retain their declared roles.",
        evidence_role="agreement",
        semantic_confirmation=confirmation,
    )
    assert result["can_render"] is True


def test_mapping_object_key_order_preserves_source_series_order_and_legacy_digest(tmp_path):
    source = tmp_path / "scatter.csv"
    pd.DataFrame({"X": [0, 1, 2], "A": [2, 3, 4], "B": [1, 4, 5]}).to_csv(source, index=False)
    service = ScientificTemplateService(TemplateRegistry(ROOT / "runtime/templates").get("scatter"))
    mapping = {"assignments": {"B": "series", "X": "x", "A": "series"}}
    legacy = service.confirm_mapping(
        service.prepare(source), assignments=mapping["assignments"], energy_kind=""
    )
    current = _prepare_with_mapping(service, source, mapping)
    assert [series.source_column for series in current.payload.plot_spec.series] == ["A", "B"]
    assert current.plan_digest == legacy.plan_digest
