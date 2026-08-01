from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_reference_policy_gives_explicit_user_style_precedence() -> None:
    policy = _read("skill/editaplot/references/reference-figures.md")

    assert "user's explicit, confirmed style request" in policy
    assert "precedence over a conflicting token inferred from the reference" in policy
    for field in (
        "exact series colors",
        "physical line widths",
        "fill transparency",
        "page/aspect ratio",
        "legend show/hide",
        "borderless",
        "position",
    ):
        assert field in policy
    for disposition in ("`applied`", "`retained_template_default`", "`rejected`"):
        assert disposition in policy


def test_xps_style_docs_separate_cosmetics_from_immutable_science() -> None:
    policy = "\n".join(
        (
            _read("skill/editaplot/references/reference-figures.md"),
            _read("skill/editaplot/references/origin-safety.md"),
            _read("runtime/templates/xps_adaptive/visual_contract.md"),
            _read("runtime/templates/xps_c1s_fit/visual_contract.md"),
        )
    )

    for boundary in (
        "source data",
        "column roles",
        "binding-energy direction",
        "component identity",
        "set_fill_area(..., type=9)",
        "-pfm 3",
    ):
        assert boundary in policy
    assert "A reference image is never sufficient authorization" in policy
    assert "Origin object readback" in policy


def test_beginner_docs_explain_capability_gated_style_choices() -> None:
    chinese = "\n".join(
        (
            _read("README.md"),
            _read("docs/installation.md"),
            _read("docs/quickstart.zh-CN.md"),
        )
    )
    english = "\n".join(
        (
            _read("README.en.md"),
            _read("docs/quickstart.en.md"),
        )
    )

    for phrase in ("明确选择优先", "线宽", "填充透明度", "画幅比例", "图例显示/无框/位置"):
        assert phrase in chinese
    for phrase in ("applied", "template default retained", "reference"):
        assert phrase in english
