from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
TOOLS = PRODUCT_ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import build_star_trend as trend  # noqa: E402


class _FakeResponse:
    def __init__(self, url: str, payload: dict[str, Any]) -> None:
        self._url = url
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int = -1) -> bytes:
        return self._payload

    def geturl(self) -> str:
        return self._url


def test_fetch_uses_only_repository_metadata_endpoint() -> None:
    calls: list[tuple[str, str, float]] = []

    def open_request(request: Any, *, timeout: float) -> _FakeResponse:
        calls.append((request.full_url, request.get_method(), timeout))
        return _FakeResponse(request.full_url, {"stargazers_count": 31, "ignored": "discarded"})

    assert trend.fetch_star_count("hang-jin/editaplot", opener=open_request) == 31
    assert calls == [("https://api.github.com/repos/hang-jin/editaplot", "GET", 20.0)]


def test_fetch_rejects_redirects_and_invalid_counts() -> None:
    def redirect_request(request: Any, *, timeout: float) -> _FakeResponse:
        del request, timeout
        return _FakeResponse("https://example.invalid/elsewhere", {"stargazers_count": 31})

    with pytest.raises(trend.StarTrendError, match="redirect"):
        trend.fetch_star_count("hang-jin/editaplot", opener=redirect_request)

    def invalid_request(request: Any, *, timeout: float) -> _FakeResponse:
        del timeout
        return _FakeResponse(request.full_url, {"stargazers_count": True})

    with pytest.raises(trend.StarTrendError, match="non-negative integer"):
        trend.fetch_star_count("hang-jin/editaplot", opener=invalid_request)


@pytest.mark.parametrize("repository", ("../..", "owner/..", "-owner/repo", "owner/repo/name"))
def test_repository_name_cannot_change_the_fixed_api_path(repository: str) -> None:
    with pytest.raises(trend.StarTrendError, match="owner/name"):
        trend.fetch_star_count(repository, opener=lambda *_args, **_kwargs: None)


def test_daily_snapshot_is_unique_and_same_day_is_replaced() -> None:
    snapshots = [
        {"date": "2026-07-22", "stars": 31},
        {"date": "2026-07-23", "stars": 32},
    ]

    updated = trend.upsert_daily_snapshot(snapshots, date(2026, 7, 23), 33)

    assert updated == [
        {"date": "2026-07-22", "stars": 31},
        {"date": "2026-07-23", "stars": 33},
    ]
    assert snapshots[1]["stars"] == 32


def test_single_snapshot_svg_is_a_real_point_without_a_fake_line() -> None:
    svg = trend.render_svg(
        "hang-jin/editaplot",
        [{"date": "2026-07-22", "stars": 31}],
    )

    assert 'data-role="series-point"' in svg
    assert 'data-date="2026-07-22"' in svg
    assert 'data-stars="31"' in svg
    assert 'cx="86.0"' in svg
    assert 'data-role="trend-line"' not in svg
    assert ">31<" in svg


def test_future_snapshots_form_one_line_through_all_daily_points() -> None:
    svg = trend.render_svg(
        "hang-jin/editaplot",
        [
            {"date": "2026-07-22", "stars": 31},
            {"date": "2026-07-23", "stars": 33},
            {"date": "2026-07-24", "stars": 32},
        ],
    )

    assert svg.count('data-role="series-point"') == 3
    assert svg.count('data-role="trend-line"') == 1
    assert svg.count('data-role="trend-area"') == 1


def test_x_positions_preserve_real_gaps_between_daily_snapshots() -> None:
    svg = trend.render_svg(
        "hang-jin/editaplot",
        [
            {"date": "2026-07-22", "stars": 31},
            {"date": "2026-07-23", "stars": 32},
            {"date": "2026-07-25", "stars": 34},
        ],
    )

    assert 'data-date="2026-07-22" data-stars="31" cx="86.0"' in svg
    assert 'data-date="2026-07-23" data-stars="32" cx="299.3"' in svg
    assert 'data-date="2026-07-25" data-stars="34" cx="726.0"' in svg


def test_initial_public_assets_are_deterministic_and_aggregate_only() -> None:
    data_path = PRODUCT_ROOT / "assets" / "star-trend" / "stars.json"
    svg_path = PRODUCT_ROOT / "assets" / "star-trend" / "stars.svg"
    payload = json.loads(data_path.read_text(encoding="utf-8"))

    assert set(payload) == {"schema_version", "repository", "snapshots"}
    assert payload["schema_version"] == 1
    assert payload["repository"] == "hang-jin/editaplot"
    assert payload["snapshots"][0] == {"date": "2026-07-22", "stars": 31}
    assert len(payload["snapshots"]) >= 1
    assert all(set(item) == {"date", "stars"} for item in payload["snapshots"])
    assert trend.load_payload(data_path, "hang-jin/editaplot") == payload
    assert svg_path.read_text(encoding="utf-8") == trend.render_svg(
        payload["repository"], payload["snapshots"]
    )


def test_source_and_workflow_have_no_identity_collection_route() -> None:
    source = (TOOLS / "build_star_trend.py").read_text(encoding="utf-8").casefold()
    workflow = (
        PRODUCT_ROOT / ".github" / "workflows" / "star-trend.yml"
    ).read_text(encoding="utf-8").casefold()
    forbidden = (
        "/stargazers",
        "starred_at",
        "stargazer list",
        "account id",
        "user id",
        "node_id",
        '"login"',
        '"id"',
        "avatar_url",
        "users/",
    )

    assert "stargazers_count" in source
    assert all(token not in source for token in forbidden)
    assert all(token not in workflow for token in forbidden)
    assert 'cron: "17 1 * * *"' in workflow
    assert "contents: write" in workflow
    assert "tools/build_star_trend.py" in workflow
    assert "--render-only" in workflow
    assert "git switch --orphan metrics-publish" in workflow
    assert "git push --force-with-lease origin head:metrics" in workflow
    assert "github_ref_name" not in workflow
