from __future__ import annotations

import base64
import json
import re
import struct
import sys
import zlib
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT_ROOT / "tools"))

from verify_public_release import _expected_asset_kind, _git_blob_id, _png_text  # noqa: E402

ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))


def test_png_audit_rejects_trailing_payload(tmp_path: Path) -> None:
    path = tmp_path / "trailing.png"
    path.write_bytes(ONE_PIXEL_PNG + b"private trailing payload")

    assert "__invalid_png__" in dict(_png_text(path))


def test_png_audit_surfaces_exif_chunk(tmp_path: Path) -> None:
    path = tmp_path / "exif.png"
    path.write_bytes(ONE_PIXEL_PNG[:-12] + _png_chunk(b"eXIf", b"camera metadata") + ONE_PIXEL_PNG[-12:])

    assert "not allowed" in dict(_png_text(path))["__invalid_png__"]


def test_png_audit_rejects_malformed_text_without_separator(tmp_path: Path) -> None:
    path = tmp_path / "malformed-text.png"
    payload = b"PASS" + b"WORD=abcdefgh"
    path.write_bytes(ONE_PIXEL_PNG[:-12] + _png_chunk(b"tEXt", payload) + ONE_PIXEL_PNG[-12:])

    assert "malformed tEXt" in dict(_png_text(path))["__invalid_png__"]


def test_png_audit_rejects_opaque_icc_profile(tmp_path: Path) -> None:
    path = tmp_path / "profile.png"
    payload = b"Profile\0\0" + zlib.compress(b"PASS" + b"WORD=abcdefgh")
    path.write_bytes(ONE_PIXEL_PNG[:-12] + _png_chunk(b"iCCP", payload) + ONE_PIXEL_PNG[-12:])

    assert "not allowed" in dict(_png_text(path))["__invalid_png__"]


def test_png_audit_rejects_duplicate_text_keywords(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-text.png"
    chunks = _png_chunk(b"tEXt", b"Comment\0PASS" + b"WORD=abcdefgh") + _png_chunk(
        b"tEXt", b"Comment\0benign"
    )
    path.write_bytes(ONE_PIXEL_PNG[:-12] + chunks + ONE_PIXEL_PNG[-12:])

    assert "duplicate text keyword" in dict(_png_text(path))["__invalid_png__"]


def test_secret_rules_cover_common_assignment_forms() -> None:
    policy = json.loads((PRODUCT_ROOT / "release" / "public-release-policy.json").read_text(encoding="utf-8"))
    patterns = [re.compile(item["pattern"], flags=re.IGNORECASE) for item in policy["secret_patterns"]]
    samples = (
        '{"pass' + 'word":"abcdefgh"}',
        "PASS" + "WORD=abcdefgh",
        "AWS_SECRET_" + "ACCESS_KEY=abcdefgh12345678",
        "Authoriz" + "ation: Bearer abcdefghijklmnop",
    )

    assert all(any(pattern.search(sample) for pattern in patterns) for sample in samples)


def test_asset_kind_mapping_is_independent_and_fail_closed() -> None:
    assert _expected_asset_kind("assets/gallery/xps-fit.png") == (
        "verified_origin_export_from_synthetic_fixture"
    )
    assert _expected_asset_kind("patient-data/scan.png") is None


def test_git_blob_audit_distinguishes_lf_from_crlf() -> None:
    assert _git_blob_id(b"header,value\nA,1\n") != _git_blob_id(b"header,value\r\nA,1\r\n")


def test_public_readmes_use_aggregate_star_badge_and_anonymous_trend() -> None:
    badge = "https://img.shields.io/github/stars/hang-jin/editaplot?style=social"
    trend = (
        "https://raw.githubusercontent.com/hang-jin/editaplot/"
        "metrics/assets/star-trend/stars.svg"
    )
    repository_link = '<a href="https://github.com/hang-jin/editaplot">'
    forbidden = ("/stargazers", "api.star-history.com")

    for name in ("README.md", "README.en.md"):
        content = (PRODUCT_ROOT / name).read_text(encoding="utf-8")
        assert badge in content
        assert trend in content
        assert repository_link in content
        assert all(token not in content for token in forbidden)


def test_public_source_has_no_stargazer_identity_collection_path() -> None:
    assert not (PRODUCT_ROOT / ".github" / "workflows" / "star-history.yml").exists()
    assert not (PRODUCT_ROOT / "tools" / "build_star_history.py").exists()
    assert not (PRODUCT_ROOT / "tests" / "test_star_history.py").exists()

    forbidden = ("/stargazers", "application/vnd.github.star+json", "include-current-star")
    audited_files = list((PRODUCT_ROOT / ".github").rglob("*.yml")) + list(
        (PRODUCT_ROOT / "tools").glob("*.py")
    )
    for path in audited_files:
        content = path.read_text(encoding="utf-8")
        assert all(token not in content for token in forbidden), path


def test_public_guidance_has_no_legacy_origin_status_gate() -> None:
    fixed_paths = [
        PRODUCT_ROOT / name
        for name in (
            "README.md",
            "README.en.md",
            "CHANGELOG.md",
            "SUPPORT.md",
            "NOTICE",
            "THIRD_PARTY_NOTICES.md",
            "docs/installation.md",
            "docs/quickstart.zh-CN.md",
            "docs/quickstart.en.md",
            "docs/release-boundaries.md",
            "docs/gallery.md",
            "skill/editaplot/SKILL.md",
            "skill/editaplot/agents/openai.yaml",
            "skill/editaplot/references/runtime.md",
            "skill/editaplot/references/origin-safety.md",
            "tools/build_showcase.py",
            "tools/sync_public_gallery.py",
        )
    ]
    fixed_paths.extend((PRODUCT_ROOT / "skill" / "editaplot" / "scripts").glob("*.py"))
    forbidden = (
        "--confirm-origin-started",
        "requires_manual_origin_start_confirmation",
        "manual_origin_launch_confirmation",
        "manual_startup_confirmation",
        "license_confirmed",
        "licensed origin",
        "legally licensed",
        "origin license",
        "originlab eula",
        "manual origin",
        "manual startup",
        "manual launch",
        "origin starts manually",
        "官方合法",
        "合法安装 origin",
        "手动启动 origin",
        "origin 已手动启动",
        "已获许可",
        "已激活",
    )

    for path in fixed_paths:
        content = path.read_text(encoding="utf-8").casefold()
        assert all(token.casefold() not in content for token in forbidden), path
