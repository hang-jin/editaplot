"""Build privacy-preserving GitHub star-history metrics and a branded SVG.

The collector uses GitHub's timestamped stargazers REST representation.  User
identifiers are used only in memory to remove pagination overlaps; neither user
ids nor logins are written to disk.  Retained aggregate-count observations form
the primary trend and may rise or fall.  Current-stargazer join dates provide
only dashed historical context because GitHub exposes neither unstar timestamps
nor historical peak counts.  No missing timestamp is ever invented.

This module intentionally depends only on the Python standard library so it can
run on a stock GitHub-hosted runner.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone, tzinfo
from html import escape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

API_VERSION = "2022-11-28"
STAR_MEDIA_TYPE = "application/vnd.github.star+json"
DEFAULT_API_BASE = "https://api.github.com"
DEFAULT_TIMEZONE = "Asia/Shanghai"
UTC = timezone.utc
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
NEXT_LINK_PATTERN = re.compile(r'<([^>]+)>;\s*rel="next"')


class StarHistoryError(RuntimeError):
    """Raised when GitHub metrics cannot be collected or validated."""


def _parse_utc_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise StarHistoryError("GitHub returned a stargazer without a valid starred_at timestamp.")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise StarHistoryError(f"GitHub returned an invalid starred_at timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise StarHistoryError("GitHub returned a timezone-naive starred_at timestamp.")
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_timezone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        if name == DEFAULT_TIMEZONE:
            # Modern GitHub timestamps are safely represented by UTC+08:00 when
            # Windows has no IANA timezone database available.
            return timezone(timedelta(hours=8), name=DEFAULT_TIMEZONE)
        raise StarHistoryError(f"Timezone data is unavailable for {name!r}.") from None


def _validate_repository(repository: str) -> str:
    normalized = repository.strip()
    if not REPOSITORY_PATTERN.fullmatch(normalized):
        raise StarHistoryError("Repository must use the owner/name form.")
    return normalized


class GitHubClient:
    """Small authenticated REST client with same-origin pagination checks."""

    def __init__(
        self,
        *,
        token: str | None = None,
        api_base: str = DEFAULT_API_BASE,
        timeout_seconds: float = 30.0,
        opener: Any = urllib.request.urlopen,
    ) -> None:
        self.token = token.strip() if token else None
        self.api_base = api_base.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.opener = opener

    def get_json(
        self, path_or_url: str, *, params: Mapping[str, str | int] | None = None
    ) -> tuple[object, Mapping[str, str]]:
        if path_or_url.startswith("/"):
            url = f"{self.api_base}{path_or_url}"
        else:
            url = path_or_url
        if not (url == self.api_base or url.startswith(f"{self.api_base}/")):
            raise StarHistoryError("GitHub pagination attempted to leave the configured API origin.")
        if params:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urllib.parse.urlencode(params)}"
        headers = {
            "Accept": STAR_MEDIA_TYPE,
            "User-Agent": "EditaPlot-star-history",
            "X-GitHub-Api-Version": API_VERSION,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(  # noqa: S310 - URL is constrained to the configured HTTPS API.
            url, headers=headers
        )
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                raw = response.read()
                response_headers = {str(key): str(value) for key, value in response.headers.items()}
        except urllib.error.HTTPError as exc:
            rate_remaining = exc.headers.get("X-RateLimit-Remaining", "unknown")
            if exc.code == 401:
                raise StarHistoryError(
                    "GitHub requires authentication for timestamped stargazers; "
                    "set GITHUB_TOKEN to a repository-scoped token."
                ) from exc
            raise StarHistoryError(
                f"GitHub API returned HTTP {exc.code}; rate-limit remaining={rate_remaining}."
            ) from exc
        except urllib.error.URLError as exc:
            raise StarHistoryError(f"Could not reach the GitHub API: {exc.reason}") from exc
        try:
            return json.loads(raw.decode("utf-8")), response_headers
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StarHistoryError("GitHub returned a non-JSON response.") from exc


def _next_link(headers: Mapping[str, str]) -> str | None:
    link = next((value for key, value in headers.items() if key.casefold() == "link"), "")
    match = NEXT_LINK_PATTERN.search(link)
    return match.group(1) if match else None


def fetch_current_stargazer_timestamps(
    client: GitHubClient, repository: str, *, max_pages: int = 1_000
) -> tuple[list[datetime], int]:
    """Return join times for current stargazers plus duplicate API rows.

    GitHub does not return people who have subsequently unstarred the
    repository, nor does it expose unstar timestamps through this endpoint.
    These timestamps therefore cannot represent a durable cumulative history.
    """

    repository = _validate_repository(repository)
    encoded_repository = "/".join(urllib.parse.quote(part, safe="") for part in repository.split("/"))
    next_url: str | None = f"/repos/{encoded_repository}/stargazers"
    params: Mapping[str, str | int] | None = {"per_page": 100, "page": 1}
    seen_users: set[int] = set()
    timestamps: list[datetime] = []
    duplicate_rows = 0
    page_count = 0

    while next_url is not None:
        page_count += 1
        if page_count > max_pages:
            raise StarHistoryError(f"Stargazer pagination exceeded the safety limit of {max_pages} pages.")
        payload, headers = client.get_json(next_url, params=params)
        params = None
        if not isinstance(payload, list):
            raise StarHistoryError("GitHub returned a non-list stargazer response.")
        for item in payload:
            if not isinstance(item, dict):
                raise StarHistoryError("GitHub returned a malformed stargazer event.")
            user = item.get("user")
            user_id = user.get("id") if isinstance(user, dict) else None
            if isinstance(user_id, bool) or not isinstance(user_id, int):
                raise StarHistoryError("GitHub returned a stargazer event without a numeric user id.")
            if user_id in seen_users:
                duplicate_rows += 1
                continue
            seen_users.add(user_id)
            timestamps.append(_parse_utc_timestamp(item.get("starred_at")))
        next_url = _next_link(headers)

    timestamps.sort()
    return timestamps, duplicate_rows


def fetch_current_star_count(client: GitHubClient, repository: str) -> int:
    repository = _validate_repository(repository)
    encoded_repository = "/".join(urllib.parse.quote(part, safe="") for part in repository.split("/"))
    payload, _headers = client.get_json(f"/repos/{encoded_repository}")
    count = payload.get("stargazers_count") if isinstance(payload, dict) else None
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise StarHistoryError("GitHub returned an invalid stargazers_count value.")
    return count


def _sync_status(current_stars: int, timestamped_current_stars: int) -> str:
    if current_stars == timestamped_current_stars:
        return "synced"
    if current_stars > timestamped_current_stars:
        return "pending_current_stargazer_list_sync"
    return "pending_aggregate_sync"


def _previous_observations(previous: Mapping[str, object] | None, repository: str) -> list[dict[str, object]]:
    if previous is None:
        return []
    if previous.get("schema_version") not in {1, 2} or previous.get("repository") != repository:
        raise StarHistoryError("The previous metrics file has an incompatible schema or repository.")
    raw_observations = previous.get("observations", [])
    if not isinstance(raw_observations, list):
        raise StarHistoryError("The previous metrics file has invalid observations.")
    observations: list[dict[str, object]] = []
    previous_time: datetime | None = None
    for item in raw_observations:
        if not isinstance(item, dict):
            raise StarHistoryError("The previous metrics file has a malformed observation.")
        observed = _parse_utc_timestamp(item.get("observed_at_utc"))
        stars = item.get("stars")
        if isinstance(stars, bool) or not isinstance(stars, int) or stars < 0:
            raise StarHistoryError("The previous metrics file has an invalid observed star count.")
        if previous_time is not None and observed < previous_time:
            raise StarHistoryError("The previous metrics observations are not chronological.")
        previous_time = observed
        observations.append({"observed_at_utc": _format_utc(observed), "stars": stars})
    return observations


def _aggregate_current_join_history(
    timestamps: Sequence[datetime], *, observed_at: datetime, display_timezone: str
) -> list[dict[str, object]]:
    """Aggregate recent events hourly and older events daily for privacy."""

    chart_timezone = _load_timezone(display_timezone)
    recent_cutoff = observed_at.astimezone(chart_timezone) - timedelta(days=7)
    buckets: dict[datetime, int] = {}
    for timestamp in timestamps:
        if timestamp.tzinfo is None:
            raise StarHistoryError("A stargazer timestamp is timezone-naive.")
        local = timestamp.astimezone(chart_timezone)
        if local >= recent_cutoff:
            bucket_local = local.replace(minute=0, second=0, microsecond=0)
        else:
            bucket_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
        bucket_utc = bucket_local.astimezone(UTC)
        buckets[bucket_utc] = buckets.get(bucket_utc, 0) + 1

    cumulative = 0
    history: list[dict[str, object]] = []
    for bucket_start, count in sorted(buckets.items()):
        cumulative += count
        history.append(
            {"bucket_start_utc": _format_utc(bucket_start), "cumulative_stars": cumulative}
        )
    return history


def build_payload(
    *,
    repository: str,
    current_stars: int,
    timestamps: Sequence[datetime],
    duplicate_rows: int = 0,
    observed_at: datetime | None = None,
    display_timezone: str = DEFAULT_TIMEZONE,
    previous: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Create the sanitized metrics document without any GitHub user data."""

    repository = _validate_repository(repository)
    if (
        isinstance(current_stars, bool)
        or not isinstance(current_stars, int)
        or current_stars < 0
        or isinstance(duplicate_rows, bool)
        or not isinstance(duplicate_rows, int)
        or duplicate_rows < 0
    ):
        raise StarHistoryError("Star counts cannot be negative.")
    _load_timezone(display_timezone)
    raw_observed_at = observed_at or datetime.now(UTC)
    if raw_observed_at.tzinfo is None:
        raise StarHistoryError("The metrics observation time must include a timezone.")
    observed_at = raw_observed_at.astimezone(UTC).replace(microsecond=0)
    normalized_timestamps: list[datetime] = []
    for value in timestamps:
        if value.tzinfo is None:
            raise StarHistoryError("A stargazer timestamp is timezone-naive.")
        normalized_timestamps.append(value.astimezone(UTC).replace(microsecond=0))
    normalized_timestamps.sort()
    current_star_join_history = _aggregate_current_join_history(
        normalized_timestamps,
        observed_at=observed_at,
        display_timezone=display_timezone,
    )
    observations = _previous_observations(previous, repository)
    if not observations or observations[-1]["stars"] != current_stars:
        if observations and observed_at < _parse_utc_timestamp(observations[-1]["observed_at_utc"]):
            raise StarHistoryError("The new observation predates the previous metrics observation.")
        observations.append({"observed_at_utc": _format_utc(observed_at), "stars": current_stars})

    payload: dict[str, object] = {
        "schema_version": 2,
        "repository": repository,
        "generated_at_utc": _format_utc(observed_at),
        "display_timezone": display_timezone,
        "current_stars": current_stars,
        "timestamped_current_star_count": len(normalized_timestamps),
        "duplicate_api_rows_ignored": duplicate_rows,
        "sync_status": _sync_status(current_stars, len(normalized_timestamps)),
        "current_star_join_history_resolution": {
            "recent_window_days": 7,
            "recent_buckets": "hourly",
            "older_buckets": "daily",
        },
        "current_star_join_history": current_star_join_history,
        "observations": observations,
        "semantics": {
            "primary_series": "observations",
            "primary_series_meaning": (
                "Point-in-time stargazers_count readings retained whenever the observed total changes; "
                "this series may rise or fall and begins when metrics collection starts."
            ),
            "context_series": "current_star_join_history",
            "context_series_meaning": (
                "Join-date reconstruction for users who are currently starring the repository only; "
                "it can change retroactively after an unstar and is not a true cumulative history."
            ),
            "github_limitation": (
                "GitHub does not provide unstar timestamps or historical peak counts through the "
                "stargazers endpoint."
            ),
        },
        "privacy": "No GitHub usernames, logins, profile URLs, or user ids are stored.",
    }

    if previous is not None:
        previous_without_generated = dict(previous)
        previous_generated = previous_without_generated.pop("generated_at_utc", None)
        candidate_without_generated = dict(payload)
        candidate_without_generated.pop("generated_at_utc", None)
        if previous_without_generated == candidate_without_generated and isinstance(previous_generated, str):
            payload["generated_at_utc"] = previous_generated
    return payload


def _chart_timezone(payload: Mapping[str, object]) -> tzinfo:
    name = payload.get("display_timezone")
    if not isinstance(name, str):
        raise StarHistoryError("Metrics payload lacks a display timezone.")
    return _load_timezone(name)


def _svg_text(value: object) -> str:
    return escape(str(value), quote=True)


def _nice_y_max(value: int) -> int:
    if value <= 5:
        return 5
    magnitude = 10 ** (len(str(value)) - 1)
    for multiplier in (1, 2, 5, 10):
        candidate = multiplier * magnitude
        if candidate >= value:
            return candidate
    return value


def render_svg(payload: Mapping[str, object]) -> str:
    """Render observed totals as the primary series and join dates as context."""

    join_history = payload.get("current_star_join_history")
    observations = payload.get("observations")
    if not isinstance(join_history, list):
        raise StarHistoryError("Metrics payload lacks current_star_join_history.")
    if not isinstance(observations, list):
        raise StarHistoryError("Metrics payload lacks observations.")
    current_stars = payload.get("current_stars")
    timestamped_count = payload.get("timestamped_current_star_count")
    if isinstance(current_stars, bool) or not isinstance(current_stars, int):
        raise StarHistoryError("Metrics payload has an invalid current star count.")
    if isinstance(timestamped_count, bool) or not isinstance(timestamped_count, int):
        raise StarHistoryError("Metrics payload has an invalid timestamped current-star count.")

    join_points: list[tuple[datetime, int]] = []
    for item in join_history:
        if not isinstance(item, dict):
            raise StarHistoryError("Metrics payload has a malformed join-history point.")
        count = item.get("cumulative_stars")
        if isinstance(count, bool) or not isinstance(count, int):
            raise StarHistoryError("Metrics payload has an invalid join-history count.")
        join_points.append((_parse_utc_timestamp(item.get("bucket_start_utc")), count))

    observed_points: list[tuple[datetime, int]] = []
    for item in observations:
        if not isinstance(item, dict):
            raise StarHistoryError("Metrics payload has a malformed total-count observation.")
        count = item.get("stars")
        if isinstance(count, bool) or not isinstance(count, int):
            raise StarHistoryError("Metrics payload has an invalid observed star count.")
        observed_points.append((_parse_utc_timestamp(item.get("observed_at_utc")), count))

    width, height = 1120, 580
    left, right, top, bottom = 92.0, 1050.0, 150.0, 420.0
    plot_width, plot_height = right - left, bottom - top
    all_counts = [current_stars, timestamped_count, 1]
    all_counts.extend(count for _timestamp, count in join_points)
    all_counts.extend(count for _timestamp, count in observed_points)
    y_max = _nice_y_max(max(all_counts))
    chart_tz = _chart_timezone(payload)

    all_times = [timestamp for timestamp, _count in join_points + observed_points]
    if all_times:
        start = min(all_times)
        end = max(all_times)
        if start == end:
            start -= timedelta(hours=12)
            end += timedelta(hours=12)
    else:
        generated = _parse_utc_timestamp(payload.get("generated_at_utc"))
        start, end = generated - timedelta(days=1), generated
    span_seconds = max((end - start).total_seconds(), 1.0)

    def x_position(value: datetime) -> float:
        return left + ((value - start).total_seconds() / span_seconds) * plot_width

    def y_position(value: int) -> float:
        return bottom - (value / y_max) * plot_height

    grid: list[str] = []
    for tick in range(6):
        value = round(y_max * tick / 5)
        y = y_position(value)
        grid.append(
            f'<line x1="{left:.1f}" y1="{y:.1f}" x2="{right:.1f}" y2="{y:.1f}" '
            'stroke="#DCE5EC" stroke-width="1"/>'
        )
        grid.append(
            f'<text x="{left - 18:.1f}" y="{y + 5:.1f}" text-anchor="end" '
            f'class="tick">{value}</text>'
        )

    x_ticks: list[str] = []
    for ratio in (0.0, 0.5, 1.0):
        value = start + (end - start) * ratio
        x = left + plot_width * ratio
        label = value.astimezone(chart_tz).strftime("%Y-%m-%d")
        x_ticks.append(
            f'<text x="{x:.1f}" y="{bottom + 34:.1f}" text-anchor="middle" '
            f'class="tick">{_svg_text(label)}</text>'
        )

    join_line_path = ""
    if join_points:
        first_x = x_position(join_points[0][0])
        first_y = y_position(join_points[0][1])
        commands = [f"M {first_x:.1f} {first_y:.1f}"]
        for timestamp, count in join_points[1:]:
            x, y = x_position(timestamp), y_position(count)
            commands.extend((f"H {x:.1f}", f"V {y:.1f}"))
        join_line_path = " ".join(commands)

    observed_line_path = ""
    observed_markers: list[str] = []
    if observed_points:
        commands = [
            f"M {x_position(observed_points[0][0]):.1f} {y_position(observed_points[0][1]):.1f}"
        ]
        for timestamp, count in observed_points[1:]:
            commands.append(f"L {x_position(timestamp):.1f} {y_position(count):.1f}")
        observed_line_path = " ".join(commands)
        for index, (timestamp, count) in enumerate(observed_points):
            is_latest = index == len(observed_points) - 1
            fill = "#E9C46A" if is_latest else "#FFFFFF"
            radius = 6 if is_latest else 4.5
            observed_markers.append(
                f'<circle cx="{x_position(timestamp):.1f}" cy="{y_position(count):.1f}" '
                f'r="{radius}" fill="{fill}" stroke="#14213D" stroke-width="2.5"/>'
            )

    join_markup = (
        f'<path id="currentStarJoinReconstruction" d="{join_line_path}" fill="none" '
        'stroke="#7CBFB5" stroke-opacity="0.72" stroke-width="3" stroke-dasharray="8 7" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        if join_points
        else ""
    )
    observed_markup = (
        f'<path id="observedTotalSeries" d="{observed_line_path}" fill="none" '
        'stroke="#14213D" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>'
        f"{''.join(observed_markers)}"
        if observed_points
        else (
            f'<text x="{(left + right) / 2:.1f}" y="{(top + bottom) / 2:.1f}" '
            'text-anchor="middle" class="empty">No total-count observations yet</text>'
        )
    )

    sync_status = payload.get("sync_status")
    if sync_status == "synced":
        sync_copy = f"{timestamped_count} current-star timestamps - synced"
        sync_color = "#2A9D8F"
    else:
        sync_copy = f"Current-list sync: {timestamped_count} timestamped / {current_stars} aggregate"
        sync_color = "#A65F00"
    timezone_name = payload.get("display_timezone", DEFAULT_TIMEZONE)
    repository = payload.get("repository", "EditaPlot")
    aria_copy = (
        "Solid line shows retained point-in-time aggregate star-count observations and may rise or fall. "
        "The dashed line reconstructs join dates for current stargazers only. GitHub provides no unstar "
        f"timestamps or historical peak counts, so the dashed context can change retroactively. {sync_copy}"
    )

    return f'''<svg xmlns="http://www.w3.org/2000/svg"
  width="{width}" height="{height}" viewBox="0 0 {width} {height}"
  role="img" aria-labelledby="title description">
  <title id="title">EditaPlot observed GitHub star total over time</title>
  <desc id="description">{_svg_text(aria_copy)} Repository: {_svg_text(repository)}.</desc>
  <defs>
    <linearGradient id="backgroundGradient" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#F8FBFD"/>
      <stop offset="1" stop-color="#EEF5F5"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="5" stdDeviation="8" flood-color="#14213D" flood-opacity="0.12"/>
    </filter>
    <style>
      text {{ font-family: Inter, "Segoe UI", Arial, sans-serif; fill: #14213D; }}
      .title {{ font-size: 30px; font-weight: 750; letter-spacing: -0.4px; }}
      .subtitle {{ font-size: 15px; fill: #526777; }}
      .badge-count {{ font-size: 34px; font-weight: 800; }}
      .badge-label {{ font-size: 13px; fill: #526777; text-transform: uppercase; letter-spacing: 1px; }}
      .tick {{ font-size: 13px; fill: #607482; }}
      .axis-label {{ font-size: 14px; font-weight: 650; fill: #415866; }}
      .legend {{ font-size: 13px; font-weight: 650; fill: #415866; }}
      .footnote {{ font-size: 12.5px; fill: #607482; }}
      .status {{ font-size: 13px; font-weight: 600; }}
      .empty {{ font-size: 18px; fill: #607482; }}
    </style>
  </defs>
  <rect x="8" y="8" width="1104" height="564" rx="24"
    fill="url(#backgroundGradient)" stroke="#D8E3E9" filter="url(#shadow)"/>
  <circle cx="47" cy="49" r="17" fill="#14213D"/>
  <path d="M47 34.5l4.2 8.5 9.4 1.4-6.8 6.6 1.6 9.3-8.4-4.4-8.4 4.4 1.6-9.3-6.8-6.6 9.4-1.4z" fill="#E9C46A"/>
  <text x="76" y="53" class="title">EditaPlot Stars - observed total over time</text>
  <text x="77" y="79" class="subtitle">Solid observations are authoritative from collection start;
    dashed history is context only</text>
  <g transform="translate(914 31)">
    <rect width="154" height="76" rx="16" fill="#FFFFFF" stroke="#D8E3E9"/>
    <text x="18" y="39" class="badge-count">{current_stars}</text>
    <text x="19" y="60" class="badge-label">CURRENT TOTAL</text>
    <path d="M123 18l4.2 8.5 9.4 1.4-6.8 6.6 1.6 9.3-8.4-4.4-8.4 4.4
      1.6-9.3-6.8-6.6 9.4-1.4z" fill="#E9C46A"/>
  </g>
  <line x1="77" y1="117" x2="111" y2="117" stroke="#14213D" stroke-width="4"/>
  <circle cx="94" cy="117" r="4" fill="#FFFFFF" stroke="#14213D" stroke-width="2"/>
  <text x="121" y="122" class="legend">Observed totals (scheduled snapshots)</text>
  <line x1="453" y1="117" x2="487" y2="117" stroke="#7CBFB5" stroke-opacity="0.72"
    stroke-width="3" stroke-dasharray="8 7"/>
  <text x="497" y="122" class="legend">Current-star join-date reconstruction*</text>
  {''.join(grid)}
  <line x1="{left:.1f}" y1="{bottom:.1f}" x2="{right:.1f}" y2="{bottom:.1f}"
    stroke="#14213D" stroke-width="1.6"/>
  <line x1="{left:.1f}" y1="{top:.1f}" x2="{left:.1f}" y2="{bottom:.1f}"
    stroke="#14213D" stroke-width="1.6"/>
  {''.join(x_ticks)}
  <text x="29" y="{(top + bottom) / 2:.1f}" text-anchor="middle" class="axis-label"
    transform="rotate(-90 29 {(top + bottom) / 2:.1f})">Stars</text>
  {join_markup}
  {observed_markup}
  <text x="92" y="493" class="footnote">* GitHub does not provide unstar timestamps
    or historical peak counts;</text>
  <text x="92" y="515" class="footnote">  dashed context can change retroactively.
    Solid observations begin when collection starts.</text>
  <circle cx="92" cy="548" r="5" fill="{sync_color}"/>
  <text x="105" y="553" class="status" fill="{sync_color}">{_svg_text(sync_copy)}</text>
  <text x="1048" y="553" text-anchor="end" class="tick">Display timezone: {_svg_text(timezone_name)}</text>
</svg>
'''


def _load_previous(path: Path | None) -> Mapping[str, object] | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StarHistoryError(f"Could not read previous metrics from {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise StarHistoryError("The previous metrics document must be a JSON object.")
    return payload


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY"),
        help="GitHub repository in owner/name form (default: GITHUB_REPOSITORY)",
    )
    parser.add_argument("--json-output", type=Path, required=True, help="Path for sanitized JSON")
    parser.add_argument("--svg-output", type=Path, required=True, help="Path for branded SVG")
    parser.add_argument("--previous", type=Path, default=None, help="Existing metrics JSON to merge")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE, help="IANA display timezone")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if not args.repository:
        parser.error("--repository is required when GITHUB_REPOSITORY is unset")
    try:
        repository = _validate_repository(args.repository)
        _load_timezone(args.timezone)
        previous = _load_previous(args.previous)
        client = GitHubClient(token=os.environ.get("GITHUB_TOKEN"), api_base=args.api_base)
        timestamps, duplicate_rows = fetch_current_stargazer_timestamps(client, repository)
        current_stars = fetch_current_star_count(client, repository)
        payload = build_payload(
            repository=repository,
            current_stars=current_stars,
            timestamps=timestamps,
            duplicate_rows=duplicate_rows,
            display_timezone=args.timezone,
            previous=previous,
        )
        _write_text(args.json_output, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        _write_text(args.svg_output, render_svg(payload))
    except StarHistoryError as exc:
        print(f"Star history build failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"Wrote {args.json_output} and {args.svg_output}: "
        f"current={payload['current_stars']}, "
        f"timestamped-current={payload['timestamped_current_star_count']}, "
        f"status={payload['sync_status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
