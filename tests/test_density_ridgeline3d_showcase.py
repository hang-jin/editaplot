from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from tools import build_showcase
from tools import generate_showcase_data as generator

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "gallery" / "density_ridgeline3d.csv"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_density_ridgeline3d_showcase_fixture_is_deterministic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(generator, "OUTPUT", tmp_path)

    generator.generate_density_ridgeline3d()
    generated = tmp_path / "density_ridgeline3d.csv"
    first = generated.read_bytes()
    generator.generate_density_ridgeline3d()

    assert generated.read_bytes() == first
    assert FIXTURE.read_bytes() == first


def test_density_ridgeline3d_showcase_fixture_obeys_frozen_contract() -> None:
    rows = _rows(FIXTURE)
    assert rows
    assert list(rows[0]) == [
        "Condition ID",
        "Follow-up Time (week)",
        "Response Score (a.u.)",
        "Solid Density (a.u.)",
        "Dashed Density (a.u.)",
        "Focal X (a.u.)",
    ]

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["Condition ID"]].append(row)
    assert len(grouped) == 4

    positions: set[float] = set()
    for group in grouped.values():
        assert len(group) == 31
        group_positions = {float(row["Follow-up Time (week)"]) for row in group}
        assert len(group_positions) == 1
        positions.update(group_positions)
        x_values = [float(row["Response Score (a.u.)"]) for row in group]
        assert all(right > left for left, right in zip(x_values, x_values[1:], strict=False))
        assert all(float(row["Solid Density (a.u.)"]) >= 0 for row in group)
        assert all(float(row["Dashed Density (a.u.)"]) >= 0 for row in group)
        focal_values = [float(row["Focal X (a.u.)"]) for row in group if row["Focal X (a.u.)"]]
        assert len(focal_values) == 1
        assert min(x_values) <= focal_values[0] <= max(x_values)
    assert len(positions) == len(grouped)


def test_verified_showcase_case_is_publicly_displayed() -> None:
    case = next(case for case in build_showcase.CASES if case.id == "density-ridgeline3d")
    assert case.template_id == "density_ridgeline3d"
    assert case.data_file == FIXTURE.name
    assert case.display_in_gallery is True
    assert "precomputed density" in case.claim
    assert "Z=0 baseline locator" in case.claim


def test_author_voice_documents_describe_the_verified_route() -> None:
    documents = {
        "chart": ROOT / "skill" / "editaplot" / "references" / "chart-selection.md",
        "data": ROOT / "skill" / "editaplot" / "references" / "data-contracts.md",
        "showcase": ROOT / "skill" / "editaplot" / "references" / "showcase.md",
        "skill": ROOT / "skill" / "editaplot" / "SKILL.md",
    }
    text = {name: path.read_text(encoding="utf-8") for name, path in documents.items()}

    for content in text.values():
        assert "density_ridgeline3d" in content
        assert "我" in content
        assert "Focal X" in content
        assert "KDE" in content
    assert "已验证" in text["chart"]
    assert "2–6" in text["data"]
    assert "CASES" in text["showcase"]
    assert "OPEN_GL_3D" in text["skill"]
