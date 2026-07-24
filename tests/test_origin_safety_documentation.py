from __future__ import annotations

from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
ORIGIN_SAFETY = (
    PRODUCT_ROOT
    / "skill"
    / "editaplot"
    / "references"
    / "origin-safety.md"
)


def _content() -> str:
    return ORIGIN_SAFETY.read_text(encoding="utf-8")


def test_origin_safety_declares_target_range_without_overclaiming_verification() -> None:
    content = _content()
    compact = " ".join(content.split())

    for product in (
        "2021",
        "2021b",
        "2022",
        "2022b",
        "2023",
        "2023b",
        "2024",
        "2024b",
        "2025",
        "2025b",
        "2026",
        "2026b",
    ):
        assert product in content

    assert "Origin 2024b / 10.15 is the current complete end-to-end" in compact
    assert "Do not describe every other target version as verified." in compact
    assert "Automation handshake" in compact
    assert "capabilities required by the selected template" in compact
    assert "real output evidence from that machine" in compact


def test_origin_safety_requires_editable_exports_readback_and_visual_evidence() -> None:
    content = _content()
    compact = " ".join(content.split())

    for evidence in (
        "editable OPJU",
        "PNG/PDF/TIF",
        "axis/text",
        "human visual inspection",
    ):
        assert evidence in content
    assert "version string, or PNG alone is insufficient" in compact


def test_origin_safety_defaults_to_a_skill_owned_isolated_instance() -> None:
    content = _content()
    compact = " ".join(content.split())

    assert "`launch_isolated` / `new_isolated` by default" in compact
    assert "The Skill starts and owns a dedicated Origin instance" in compact
    assert "does not need to open an Origin window in advance" in compact
    assert "official `Application` behavior, which creates a new instance" in compact
    assert "`attach_existing` only when explicitly requested" in compact


def test_origin_safety_limits_diagnostics_to_technical_callability() -> None:
    content = _content()
    folded = content.casefold()

    assert "readiness means technical callability only" in folded
    assert "do not ask the user to confirm any non-technical product or account state" in folded
    forbidden = (
        "license_confirmed",
        "licensed origin",
        "legally licensed",
        "origin license",
        "originlab eula",
        "proof of license",
        "manual origin",
        "manual launch",
    )
    assert all(token not in folded for token in forbidden)


def test_origin_version_risks_are_advisory_and_unknown_versions_probe_fully() -> None:
    content = _content()
    compact = " ".join(content.split())

    assert "`known_version_risks`" in content
    assert "`probe_priority`" in content
    assert "never block a render by version number alone" in compact
    assert "`version_status=unknown`" in content
    assert "use high probe priority" in compact
    assert "run the complete capability probe" in compact
    assert "Never silently label that environment supported or verified." in compact


def test_origin_safety_links_only_to_relevant_official_technical_sources() -> None:
    content = _content()
    expected_urls = (
        "https://docs.originlab.com/externalpython/",
        (
            "https://docs.originlab.com/com/"
            "difference-of-application-applicationsi-and-applicationcomsi/"
        ),
        "https://www.originlab.com/index.aspx?pid=3325",
        "https://docs.originlab.com/quick-help/why-graph-looks-different-in-2025b/",
    )

    assert "## Official technical references" in content
    assert all(url in content for url in expected_urls)
