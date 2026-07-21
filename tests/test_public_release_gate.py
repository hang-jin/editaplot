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
