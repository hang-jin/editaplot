from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import sync_public_gallery as gallery_sync  # noqa: E402


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _prepare_verified_case(
    root: Path,
    case_id: str,
    *,
    output_name: str = "origin-output",
    programmatic_pass: bool = True,
    embedded_manual_review: bool = False,
) -> Path:
    output = root / "showcase" / "gallery" / case_id / output_name
    output.mkdir(parents=True, exist_ok=True)
    png = output / "result.png"
    png.write_bytes(f"verified-{case_id}-{output_name}".encode())
    review = {
        "status": "pending",
        "required_checks": ["axis", "font", "color"],
    }
    if embedded_manual_review:
        review = {
            "status": "pass",
            "reviewer": "Manual reviewer",
            "reviewed_on": "2026-07-27",
            "visual_note": "Axes, labels, fonts, colors, and clipping were checked.",
            "png_sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
        }
    _write_json(
        output.parent / "verification.json",
        {
            "schema_version": "1.0",
            "programmatic_pass": programmatic_pass,
            "output_directory": str(output),
            "artifacts": {
                "png": {
                    "path": str(png),
                    "exists": True,
                    "size_bytes": png.stat().st_size,
                    "ok": True,
                }
            },
            "human_visual_qa": review,
        },
    )
    return png


def _write_public_manifest(root: Path, cases: list[dict[str, object]]) -> None:
    _write_json(
        root / "assets" / "gallery" / "gallery-manifest.json",
        {
            "schema_version": "1.0",
            "case_count": len(cases),
            "display_case_count": sum(bool(case.get("display_in_gallery", True)) for case in cases),
            "cases": cases,
        },
    )


def test_new_case_is_not_blocked_by_the_old_manifest_and_uses_verified_output_02(
    tmp_path: Path,
) -> None:
    public = tmp_path / "assets" / "gallery"
    public.mkdir(parents=True)
    (public / "old-case.png").write_bytes(b"existing-public-png")
    _write_public_manifest(
        tmp_path,
        [
            {
                "id": "old-case",
                "title_zh": "旧案例",
                "sha256": "stale-until-sync",
                "size_bytes": 1,
            }
        ],
    )
    source_png = _prepare_verified_case(
        tmp_path,
        "new-case",
        output_name="origin-output_02",
        embedded_manual_review=True,
    )

    records = gallery_sync.sync_gallery(
        root=tmp_path,
        selected_ids=("new-case",),
        registered_titles={"old-case": "旧案例", "new-case": "新案例"},
    )

    assert (public / "new-case.png").read_bytes() == source_png.read_bytes()
    assert {record["id"] for record in records} == {"old-case", "new-case"}
    manifest = json.loads((public / "gallery-manifest.json").read_text(encoding="utf-8"))
    assert manifest["case_count"] == 2
    assert manifest["display_case_count"] == 2
    assert {item["id"] for item in manifest["cases"]} == {"old-case", "new-case"}
    assert "新案例" in (tmp_path / "docs" / "gallery.md").read_text(encoding="utf-8")
    english = (tmp_path / "docs" / "gallery.en.md").read_text(encoding="utf-8")
    assert "A quick first-choice guide" in english
    assert english.count("<img ") == 2


def test_hidden_verified_cases_remain_in_inventory_but_not_in_gallery_page(
    tmp_path: Path,
) -> None:
    visible_id = "dense-30"
    hidden_id = "annotated-small"
    _prepare_verified_case(tmp_path, visible_id, embedded_manual_review=True)
    _prepare_verified_case(tmp_path, hidden_id, embedded_manual_review=True)

    records = gallery_sync.sync_gallery(
        root=tmp_path,
        selected_ids=(visible_id, hidden_id),
        registered_titles={
            visible_id: "30×30 高密度热力图",
            hidden_id: "小矩阵热力图",
        },
        registered_visibility={
            visible_id: True,
            hidden_id: False,
        },
    )

    manifest = json.loads(
        (tmp_path / "assets" / "gallery" / "gallery-manifest.json").read_text(encoding="utf-8")
    )
    document = (tmp_path / "docs" / "gallery.md").read_text(encoding="utf-8")
    english = (tmp_path / "docs" / "gallery.en.md").read_text(encoding="utf-8")
    assert manifest["case_count"] == len(records) == 2
    assert manifest["display_case_count"] == 1
    assert {record["id"]: record["display_in_gallery"] for record in records} == {
        hidden_id: False,
        visible_id: True,
    }
    assert "30×30 高密度热力图" in document
    assert "小矩阵热力图" not in document
    assert english.count("<img ") == 1
    assert hidden_id not in english
    assert (tmp_path / "assets" / "gallery" / f"{hidden_id}.png").is_file()


def test_existing_case_accepts_the_path_bound_legacy_manual_review(
    tmp_path: Path,
) -> None:
    case_id = "legacy-case"
    png = _prepare_verified_case(tmp_path, case_id)
    _write_public_manifest(
        tmp_path,
        [{"id": case_id, "title_zh": "旧版复核案例"}],
    )
    _write_json(
        tmp_path / "showcase" / "visual-qa.json",
        {
            "cases": [
                {
                    "id": case_id,
                    "programmatic_status": "pass",
                    "manual_visual_review": "pass",
                    "reviewer": "Legacy manual reviewer",
                    "visual_note": "The exact PNG path was visually checked.",
                    "artifacts": {
                        "png": str(png.relative_to(tmp_path)),
                    },
                }
            ]
        },
    )

    records = gallery_sync.sync_gallery(
        root=tmp_path,
        registered_titles={case_id: "旧版复核案例"},
    )

    assert records[0]["id"] == case_id
    assert (tmp_path / "assets" / "gallery" / f"{case_id}.png").read_bytes() == png.read_bytes()


def test_sync_rejects_programmatic_failure_even_with_manual_review(
    tmp_path: Path,
) -> None:
    case_id = "failed-case"
    _prepare_verified_case(
        tmp_path,
        case_id,
        programmatic_pass=False,
        embedded_manual_review=True,
    )

    with pytest.raises(RuntimeError, match="Programmatic verification did not pass"):
        gallery_sync.sync_gallery(
            root=tmp_path,
            selected_ids=(case_id,),
            registered_titles={case_id: "失败案例"},
        )


def test_sync_rejects_missing_or_stale_manual_review(tmp_path: Path) -> None:
    case_id = "stale-review"
    _prepare_verified_case(
        tmp_path,
        case_id,
        output_name="origin-output_02",
    )
    old_png = tmp_path / "showcase" / "gallery" / case_id / "origin-output" / "result.png"
    old_png.parent.mkdir(parents=True)
    old_png.write_bytes(b"previously-reviewed-revision")
    _write_json(
        tmp_path / "showcase" / "visual-qa.json",
        {
            "cases": [
                {
                    "id": case_id,
                    "programmatic_status": "pass",
                    "manual_visual_review": "pass",
                    "reviewer": "Legacy manual reviewer",
                    "visual_note": "Only the old revision was reviewed.",
                    "artifacts": {
                        "png": str(old_png.relative_to(tmp_path)),
                    },
                }
            ]
        },
    )

    with pytest.raises(RuntimeError, match="not bound to the verified PNG"):
        gallery_sync.sync_gallery(
            root=tmp_path,
            selected_ids=(case_id,),
            registered_titles={case_id: "新修订案例"},
        )


def test_sync_rejects_verified_png_outside_the_case_directory(
    tmp_path: Path,
) -> None:
    case_id = "escaped-case"
    case_directory = tmp_path / "showcase" / "gallery" / case_id
    case_directory.mkdir(parents=True)
    outside = tmp_path / "showcase" / "gallery" / "other" / "origin-output"
    outside.mkdir(parents=True)
    png = outside / "result.png"
    png.write_bytes(b"outside")
    _write_json(
        case_directory / "verification.json",
        {
            "programmatic_pass": True,
            "artifacts": {
                "png": {
                    "path": str(png),
                    "size_bytes": png.stat().st_size,
                    "ok": True,
                }
            },
        },
    )

    with pytest.raises(RuntimeError, match="escapes its showcase case directory"):
        gallery_sync.sync_gallery(
            root=tmp_path,
            selected_ids=(case_id,),
            registered_titles={case_id: "越界案例"},
        )
