"""Regenerate the hash manifest for the already-curated public runtime tree."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True)
    args = parser.parse_args()
    runtime = Path(args.runtime).resolve()
    manifest_path = runtime / "runtime-manifest.json"
    if not (runtime / "src" / "origin_sciplot" / "__init__.py").is_file():
        raise RuntimeError("The curated runtime marker is missing.")

    records: list[dict[str, object]] = []
    for path in sorted(runtime.rglob("*")):
        relative = path.relative_to(runtime)
        if (
            not path.is_file()
            or path == manifest_path
            or any(part in EXCLUDED_PARTS for part in relative.parts)
            or path.suffix.lower() in EXCLUDED_SUFFIXES
        ):
            continue
        records.append(
            {
                "path": relative.as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )

    manifest = {
        "schema_version": "1.0",
        "source_policy": (
            "curated EditaPlot runtime; caches, tests, builds, outputs, binaries, and local paths excluded"
        ),
        "file_count": len(records),
        "files": records,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {manifest_path} with {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
