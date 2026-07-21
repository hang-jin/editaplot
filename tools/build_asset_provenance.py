"""Build a deterministic provenance inventory for every public CSV and PNG."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _png_text(path: Path) -> dict[str, str]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise RuntimeError(f"Invalid PNG signature: {path}")
    cursor = len(PNG_SIGNATURE)
    text: dict[str, str] = {}
    saw_iend = False
    while cursor < len(data):
        if cursor + 12 > len(data):
            raise RuntimeError(f"Truncated PNG chunk: {path}")
        length = struct.unpack(">I", data[cursor : cursor + 4])[0]
        if cursor + 12 + length > len(data):
            raise RuntimeError(f"Truncated PNG chunk: {path}")
        chunk_type = data[cursor + 4 : cursor + 8]
        payload = data[cursor + 8 : cursor + 8 + length]
        expected_crc = struct.unpack(">I", data[cursor + 8 + length : cursor + 12 + length])[0]
        if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != expected_crc:
            raise RuntimeError(f"Invalid PNG chunk checksum: {path}")
        cursor += 12 + length
        if chunk_type == b"tEXt":
            key, value = payload.split(b"\x00", 1)
            text[key.decode("latin-1")] = value.decode("latin-1")
        elif chunk_type == b"zTXt":
            key, encoded = payload.split(b"\x00", 1)
            text[key.decode("latin-1")] = zlib.decompress(encoded[1:]).decode("latin-1")
        elif chunk_type == b"iTXt":
            key, rest = payload.split(b"\x00", 1)
            compressed, _method, rest = rest[0], rest[1], rest[2:]
            _language, rest = rest.split(b"\x00", 1)
            _translated, value = rest.split(b"\x00", 1)
            if compressed:
                value = zlib.decompress(value)
            text[key.decode("latin-1")] = value.decode("utf-8")
        elif chunk_type == b"eXIf":
            text["__exif__"] = f"{len(payload)} bytes"
        if chunk_type == b"IEND":
            if payload or cursor != len(data):
                raise RuntimeError(f"PNG has trailing data or an invalid IEND: {path}")
            saw_iend = True
            break
    if not saw_iend:
        raise RuntimeError(f"PNG is missing IEND: {path}")
    return text


def _classification(relative: str) -> str:
    if relative.startswith("assets/gallery/"):
        return "verified_origin_export_from_synthetic_fixture"
    if "/assets/palettes/" in f"/{relative}" or relative.startswith("assets/palettes/"):
        return "generated_original_palette_asset"
    if relative.endswith("resources/app_icon.png"):
        return "original_application_icon"
    if relative.endswith("templates/xps_c1s_fit/preview.png"):
        return "generated_synthetic_ui_preview"
    if relative.startswith("examples/"):
        return "synthetic_public_example"
    if relative.startswith("runtime/templates/"):
        return "synthetic_runtime_fixture"
    raise RuntimeError(f"Unclassified public asset: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = Path(args.root).resolve()
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git is required to inventory the reviewed public file set.")
    completed = subprocess.run(  # noqa: S603 - resolved executable and fixed read-only arguments
        [git, "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    tracked = completed.stdout.decode("utf-8").split("\x00")
    relative_assets = sorted(item for item in tracked if Path(item).suffix.lower() in {".csv", ".png"})
    records = []
    for relative in relative_assets:
        path = root / relative
        record: dict[str, object] = {
            "path": relative,
            "kind": _classification(relative),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "synthetic_or_generated": True,
            "contains_phi": False,
        }
        if path.suffix.lower() == ".png":
            record["png_text"] = _png_text(path)
        records.append(record)

    payload = {
        "schema_version": "1.0",
        "release_policy": "synthetic teaching data and original/generated assets only",
        "inventory_generator": {
            "path": "tools/build_asset_provenance.py",
            "sha256": _sha256(Path(__file__).resolve()),
        },
        "gallery_fixture_generator": {
            "path": "tools/generate_showcase_data.py",
            "sha256": _sha256(root / "tools" / "generate_showcase_data.py"),
        },
        "human_review": {
            "decision": "approved_for_public_source_release",
            "reviewed_on": "2026-07-21",
            "scope": (
                "all listed CSV and PNG assets; synthetic/generated status, PHI, labels, "
                "metadata, and redistribution boundary"
            ),
        },
        "asset_count": len(records),
        "assets": records,
    }
    output = root / "assets" / "provenance-manifest.json"
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {output} with {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
