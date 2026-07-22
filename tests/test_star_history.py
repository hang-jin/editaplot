from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT_ROOT / "tools"))

import build_star_history as star_history  # noqa: E402
from build_star_history import (  # noqa: E402
    DEFAULT_MEDIA_TYPE,
    STAR_MEDIA_TYPE,
    build_payload,
    fetch_current_star_count,
    fetch_current_stargazer_timestamps,
    render_svg,
)

UTC = timezone.utc


class StubClient:
    def __init__(self, responses: list[tuple[object, dict[str, str]]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, object, str]] = []

    def get_json(
        self,
        path_or_url: str,
        *,
        params: object = None,
        accept: str = DEFAULT_MEDIA_TYPE,
    ) -> tuple[object, dict[str, str]]:
        self.calls.append((path_or_url, params, accept))
        return self.responses.pop(0)


def test_workflow_allows_an_empty_first_metrics_branch() -> None:
    workflow = (PRODUCT_ROOT / ".github" / "workflows" / "star-history.yml").read_text(
        encoding="utf-8"
    )

    assert 'git -C "$metrics_dir" rm -rf --ignore-unmatch -- .' in workflow


def _event(user_id: int, timestamp: str, login: str = "private-user") -> dict[str, Any]:
    return {"starred_at": timestamp, "user": {"id": user_id, "login": login}}


def test_timestamped_stargazer_pagination_and_deduplication() -> None:
    client = StubClient(
        [
            (
                [
                    _event(1, "2026-07-21T08:00:00Z", "alpha"),
                    _event(2, "2026-07-21T08:01:00Z", "beta"),
                ],
                {
                    "Link": (
                        "<https://api.github.com/repos/hang-jin/editaplot/stargazers"
                        '?per_page=100&page=2>; rel="next", '
                        "<https://api.github.com/repos/hang-jin/editaplot/stargazers"
                        '?per_page=100&page=2>; rel="last"'
                    )
                },
            ),
            (
                [
                    _event(2, "2026-07-21T08:01:00Z", "beta"),
                    _event(3, "2026-07-21T08:01:00Z", "gamma"),
                ],
                {},
            ),
        ]
    )

    timestamps, duplicate_rows = fetch_current_stargazer_timestamps(client, "hang-jin/editaplot")

    assert [value.isoformat() for value in timestamps] == [
        "2026-07-21T08:00:00+00:00",
        "2026-07-21T08:01:00+00:00",
        "2026-07-21T08:01:00+00:00",
    ]
    assert duplicate_rows == 1
    assert len(client.calls) == 2
    assert client.calls[0][1] == {"per_page": 100, "page": 1}
    assert client.calls[0][2] == STAR_MEDIA_TYPE
    assert client.calls[1][1] is None
    assert client.calls[1][2] == STAR_MEDIA_TYPE


def test_aggregate_count_uses_standard_repository_media_type() -> None:
    client = StubClient([({"stargazers_count": 4}, {})])

    assert fetch_current_star_count(client, "hang-jin/editaplot") == 4
    assert client.calls == [("/repos/hang-jin/editaplot", None, DEFAULT_MEDIA_TYPE)]


def test_payload_is_anonymous_and_does_not_invent_mismatched_event() -> None:
    payload = build_payload(
        repository="hang-jin/editaplot",
        current_stars=3,
        timestamps=[
            datetime(2026, 7, 21, 8, 0, tzinfo=UTC),
            datetime(2026, 7, 21, 8, 1, tzinfo=UTC),
        ],
        observed_at=datetime(2026, 7, 21, 8, 5, tzinfo=UTC),
    )

    assert payload["sync_status"] == "pending_current_stargazer_list_sync"
    assert payload["current_stars"] == 3
    assert payload["timestamped_current_star_count"] == 2
    assert payload["current_star_join_history"][-1]["cumulative_stars"] == 2
    assert all(point["cumulative_stars"] != 3 for point in payload["current_star_join_history"])
    serialized = json.dumps(payload)
    assert "2026-07-21T08:01:00Z" not in serialized
    assert "private-user" not in serialized
    assert '"login"' not in serialized
    assert '"user"' not in serialized


def test_aggregate_lag_is_reported_without_dropping_verified_events() -> None:
    payload = build_payload(
        repository="hang-jin/editaplot",
        current_stars=1,
        timestamps=[
            datetime(2026, 7, 21, 8, 0, tzinfo=UTC),
            datetime(2026, 7, 21, 8, 1, tzinfo=UTC),
        ],
        observed_at=datetime(2026, 7, 21, 8, 5, tzinfo=UTC),
    )

    assert payload["sync_status"] == "pending_aggregate_sync"
    assert payload["timestamped_current_star_count"] == 2
    assert payload["current_star_join_history"][-1]["cumulative_stars"] == 2


def test_aggregate_only_payload_does_not_claim_stargazer_context() -> None:
    payload = build_payload(
        repository="hang-jin/editaplot",
        current_stars=4,
        timestamps=[],
        current_star_listing_status="not_collected",
        observed_at=datetime(2026, 7, 22, 8, 5, tzinfo=UTC),
    )

    assert payload["sync_status"] == "aggregate_only"
    assert payload["current_star_listing_status"] == "not_collected"
    assert payload["current_star_join_history"] == []
    assert "aggregate observations only" in payload["semantics"]["context_series_meaning"]

    svg = render_svg(payload)
    assert 'id="currentStarJoinReconstruction"' not in svg
    assert "no stargazer list requested" in svg
    assert "no stargazer identities or join timestamps are requested" in svg


def test_cli_defaults_to_aggregate_only_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object, str]] = []

    class AggregateClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def get_json(
            self,
            path_or_url: str,
            *,
            params: object = None,
            accept: str = DEFAULT_MEDIA_TYPE,
        ) -> tuple[object, dict[str, str]]:
            calls.append((path_or_url, params, accept))
            if path_or_url.endswith("/stargazers"):
                raise AssertionError("The default workflow must not request the stargazer listing.")
            return {"stargazers_count": 4}, {}

    monkeypatch.setattr(star_history, "GitHubClient", AggregateClient)
    json_output = tmp_path / "stars.json"
    svg_output = tmp_path / "stars.svg"

    returncode = star_history.main(
        [
            "--repository",
            "hang-jin/editaplot",
            "--json-output",
            str(json_output),
            "--svg-output",
            str(svg_output),
        ]
    )

    assert returncode == 0
    assert calls == [("/repos/hang-jin/editaplot", None, DEFAULT_MEDIA_TYPE)]
    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert payload["sync_status"] == "aggregate_only"
    assert payload["observations"][-1]["stars"] == 4
    assert "currentStarJoinReconstruction" not in svg_output.read_text(encoding="utf-8")


def test_svg_uses_asia_shanghai_calendar_dates_across_utc_boundary() -> None:
    payload = build_payload(
        repository="hang-jin/editaplot",
        current_stars=2,
        timestamps=[
            datetime(2026, 7, 22, 15, 30, tzinfo=UTC),
            datetime(2026, 7, 22, 16, 30, tzinfo=UTC),
        ],
        observed_at=datetime(2026, 7, 22, 16, 31, tzinfo=UTC),
        display_timezone="Asia/Shanghai",
    )

    svg = render_svg(payload)

    assert [point["bucket_start_utc"] for point in payload["current_star_join_history"]] == [
        "2026-07-22T15:00:00Z",
        "2026-07-22T16:00:00Z",
    ]
    assert "2026-07-22" in svg
    assert "2026-07-23" in svg
    assert "Display timezone: Asia/Shanghai" in svg


def test_svg_exposes_mismatch_but_keeps_current_count_outside_curve() -> None:
    payload = build_payload(
        repository="hang-jin/editaplot",
        current_stars=3,
        timestamps=[
            datetime(2026, 7, 21, 8, 0, tzinfo=UTC),
            datetime(2026, 7, 21, 8, 1, tzinfo=UTC),
        ],
        observed_at=datetime(2026, 7, 21, 8, 5, tzinfo=UTC),
    )

    svg = render_svg(payload)

    assert "Current-list sync: 2 timestamped / 3 aggregate" in svg
    assert ">3</text>" in svg
    assert re.search(r'id="observedTotalSeries" d="M [0-9.]+ [0-9.]+"', svg)
    assert 'r="6" fill="#E9C46A" stroke="#14213D" stroke-width="2.5"' in svg
    assert payload["current_star_join_history"][-1] == {
        "bucket_start_utc": "2026-07-21T08:00:00Z",
        "cumulative_stars": 2,
    }


def test_unchanged_metrics_preserve_generation_time_and_observation_count() -> None:
    first = build_payload(
        repository="hang-jin/editaplot",
        current_stars=2,
        timestamps=[
            datetime(2026, 7, 21, 8, 0, tzinfo=UTC),
            datetime(2026, 7, 21, 8, 1, tzinfo=UTC),
        ],
        observed_at=datetime(2026, 7, 21, 8, 5, tzinfo=UTC),
    )
    second = build_payload(
        repository="hang-jin/editaplot",
        current_stars=2,
        timestamps=[
            datetime(2026, 7, 21, 8, 0, tzinfo=UTC),
            datetime(2026, 7, 21, 8, 1, tzinfo=UTC),
        ],
        observed_at=datetime(2026, 7, 22, 8, 5, tzinfo=UTC),
        previous=first,
    )

    assert second["generated_at_utc"] == first["generated_at_utc"]
    assert second["observations"] == first["observations"]


def test_changed_count_appends_an_observation() -> None:
    first = build_payload(
        repository="hang-jin/editaplot",
        current_stars=2,
        timestamps=[datetime(2026, 7, 21, 8, 0, tzinfo=UTC)],
        observed_at=datetime(2026, 7, 21, 8, 5, tzinfo=UTC),
    )
    second = build_payload(
        repository="hang-jin/editaplot",
        current_stars=3,
        timestamps=[
            datetime(2026, 7, 21, 8, 0, tzinfo=UTC),
            datetime(2026, 7, 22, 8, 0, tzinfo=UTC),
        ],
        observed_at=datetime(2026, 7, 22, 8, 5, tzinfo=UTC),
        previous=first,
    )

    assert second["generated_at_utc"] == "2026-07-22T08:05:00Z"
    assert second["observations"] == [
        {"observed_at_utc": "2026-07-21T08:05:00Z", "stars": 2},
        {"observed_at_utc": "2026-07-22T08:05:00Z", "stars": 3},
    ]


def test_unstar_preserves_observed_peak_and_draws_primary_series_downward() -> None:
    first = build_payload(
        repository="hang-jin/editaplot",
        current_stars=3,
        timestamps=[
            datetime(2026, 7, 21, 7, 0, tzinfo=UTC),
            datetime(2026, 7, 21, 7, 10, tzinfo=UTC),
            datetime(2026, 7, 21, 7, 20, tzinfo=UTC),
        ],
        observed_at=datetime(2026, 7, 21, 8, 0, tzinfo=UTC),
    )
    after_unstar = build_payload(
        repository="hang-jin/editaplot",
        current_stars=2,
        timestamps=[
            datetime(2026, 7, 21, 7, 0, tzinfo=UTC),
            datetime(2026, 7, 21, 7, 10, tzinfo=UTC),
        ],
        observed_at=datetime(2026, 7, 22, 8, 0, tzinfo=UTC),
        previous=first,
    )

    assert after_unstar["observations"] == [
        {"observed_at_utc": "2026-07-21T08:00:00Z", "stars": 3},
        {"observed_at_utc": "2026-07-22T08:00:00Z", "stars": 2},
    ]
    assert after_unstar["current_star_join_history"][-1]["cumulative_stars"] == 2
    assert "not a true cumulative history" in after_unstar["semantics"]["context_series_meaning"]

    svg = render_svg(after_unstar)
    observed_path = re.search(
        r'id="observedTotalSeries" d="M ([0-9.]+) ([0-9.]+) L ([0-9.]+) ([0-9.]+)"',
        svg,
    )

    assert observed_path is not None
    assert float(observed_path.group(4)) > float(observed_path.group(2))
    assert 'id="currentStarJoinReconstruction"' in svg
    assert 'stroke-dasharray="8 7"' in svg
    assert "does not provide unstar timestamps" in svg
    assert "or historical peak counts" in svg
    assert "observed GitHub star total over time" in svg
