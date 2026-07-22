"""Record one anonymous daily GitHub Star total and render a static SVG trend.

The network boundary is intentionally tiny: one GET request to the repository
metadata endpoint, from which only ``stargazers_count`` is retained. No account
records or event-level data are requested or written.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
API_ROOT = "https://api.github.com/repos"
MAX_RESPONSE_BYTES = 1_000_000
OWNER_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
NAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,100}")


class StarTrendError(RuntimeError):
    """Stable error for aggregate Star collection or rendering."""


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Any,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        del request, file_pointer, code, message, headers, new_url
        return None


def _open_without_redirects(request: urllib.request.Request, *, timeout: float) -> Any:
    opener = urllib.request.build_opener(_RejectRedirects())
    return opener.open(  # noqa: S310 - request is built from the fixed HTTPS API root
        request,
        timeout=timeout,
    )


def _repository_parts(repository: str) -> tuple[str, str]:
    value = repository.strip()
    if value.count("/") != 1:
        raise StarTrendError("Repository must use the owner/name form.")
    owner, name = value.split("/", 1)
    if (
        OWNER_PATTERN.fullmatch(owner) is None
        or NAME_PATTERN.fullmatch(name) is None
        or name in {".", ".."}
    ):
        raise StarTrendError("Repository must use the owner/name form.")
    return owner, name


def fetch_star_count(
    repository: str,
    *,
    token: str | None = None,
    opener: Callable[..., Any] | None = None,
) -> int:
    """Return only the aggregate repository Star count."""

    owner, name = _repository_parts(repository)
    endpoint = f"{API_ROOT}/{owner}/{name}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "EditaPlot-anonymous-star-trend",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(  # noqa: S310 - fixed HTTPS API root and validated path
        endpoint,
        headers=headers,
        method="GET",
    )
    open_request = opener or _open_without_redirects
    try:
        with open_request(request, timeout=20.0) as response:
            if response.geturl() != endpoint:
                raise StarTrendError("The repository request followed an unexpected redirect.")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except StarTrendError:
        raise
    except (OSError, urllib.error.URLError) as exc:
        raise StarTrendError("Could not read the aggregate repository metadata.") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise StarTrendError("The repository metadata response is unexpectedly large.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StarTrendError("The repository metadata response is not valid JSON.") from exc
    count = payload.get("stargazers_count") if isinstance(payload, dict) else None
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise StarTrendError("stargazers_count must be a non-negative integer.")
    return count


def _normalize_snapshots(snapshots: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    previous_day: date | None = None
    for item in snapshots:
        if not isinstance(item, dict) or set(item) != {"date", "stars"}:
            raise StarTrendError("Each snapshot must contain only date and stars.")
        day_text = item.get("date")
        count = item.get("stars")
        if not isinstance(day_text, str):
            raise StarTrendError("Snapshot date must be an ISO date string.")
        try:
            day = date.fromisoformat(day_text)
        except ValueError as exc:
            raise StarTrendError("Snapshot date must be an ISO date string.") from exc
        if day.isoformat() != day_text:
            raise StarTrendError("Snapshot date must use canonical YYYY-MM-DD form.")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise StarTrendError("Snapshot stars must be a non-negative integer.")
        if previous_day is not None and day <= previous_day:
            raise StarTrendError("Snapshots must have unique, increasing daily dates.")
        normalized.append({"date": day_text, "stars": count})
        previous_day = day
    if not normalized:
        raise StarTrendError("At least one aggregate snapshot is required.")
    return normalized


def load_payload(path: Path, repository: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StarTrendError("Could not read the aggregate Star data file.") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "repository",
        "snapshots",
    }:
        raise StarTrendError("The aggregate Star data file has an invalid shape.")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise StarTrendError("The aggregate Star data schema is unsupported.")
    if payload.get("repository") != repository:
        raise StarTrendError("The aggregate Star data belongs to a different repository.")
    snapshots = payload.get("snapshots")
    if not isinstance(snapshots, list):
        raise StarTrendError("The aggregate Star snapshots must be a list.")
    return {
        "schema_version": SCHEMA_VERSION,
        "repository": repository,
        "snapshots": _normalize_snapshots(snapshots),
    }


def upsert_daily_snapshot(
    snapshots: Sequence[dict[str, Any]],
    day: date,
    stars: int,
) -> list[dict[str, Any]]:
    """Return one aggregate snapshot per UTC day without mutating the input."""

    if isinstance(stars, bool) or not isinstance(stars, int) or stars < 0:
        raise StarTrendError("Daily stars must be a non-negative integer.")
    by_day = {item["date"]: item["stars"] for item in _normalize_snapshots(snapshots)}
    by_day[day.isoformat()] = stars
    ordered = [{"date": key, "stars": by_day[key]} for key in sorted(by_day)]
    return _normalize_snapshots(ordered)


def _y_scale(values: Sequence[int]) -> tuple[int, int, list[int]]:
    low = min(values)
    high = max(values)
    if low == high:
        padding = max(2, math.ceil(max(low, 1) * 0.06))
    else:
        padding = max(1, math.ceil((high - low) * 0.18))
    lower = max(0, low - padding)
    upper = max(lower + 2, high + padding)
    middle = int(round((lower + upper) / 2))
    ticks = sorted({lower, middle, upper})
    return lower, upper, ticks


def render_svg(repository: str, snapshots: Sequence[dict[str, Any]]) -> str:
    """Render a deterministic, script-free SVG from aggregate daily totals."""

    _repository_parts(repository)
    points = _normalize_snapshots(snapshots)
    values = [int(item["stars"]) for item in points]
    lower, upper, ticks = _y_scale(values)
    plot_left, plot_right = 86.0, 726.0
    plot_top, plot_bottom = 82.0, 220.0
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top
    point_dates = [date.fromisoformat(str(item["date"])) for item in points]
    date_span = (point_dates[-1] - point_dates[0]).days

    def x_at(index: int) -> float:
        if date_span == 0:
            return plot_left
        elapsed_days = (point_dates[index] - point_dates[0]).days
        return plot_left + plot_width * elapsed_days / date_span

    def y_at(value: int) -> float:
        return plot_bottom - (value - lower) * plot_height / (upper - lower)

    coordinates = [(x_at(index), y_at(int(item["stars"]))) for index, item in enumerate(points)]
    escaped_repository = html.escape(repository, quote=True)
    latest = points[-1]
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="280" viewBox="0 0 760 280" role="img">',
        "  <title>EditaPlot GitHub Star trend</title>",
        (
            "  <desc>Anonymous daily aggregate Star totals for "
            f"{escaped_repository}; no account-level data.</desc>"
        ),
        "  <defs>",
        '    <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">',
        '      <stop offset="0%" stop-color="#2563eb" stop-opacity="0.24"/>',
        '      <stop offset="100%" stop-color="#14b8a6" stop-opacity="0.02"/>',
        "    </linearGradient>",
        "  </defs>",
        '  <rect width="760" height="280" rx="18" fill="#ffffff"/>',
        '  <rect x="18" y="20" width="724" height="244" rx="15" fill="#cbd5e1" opacity="0.18"/>',
        '  <rect x="16" y="16" width="728" height="248" rx="15" fill="#f8fafc" stroke="#e2e8f0"/>',
        '  <text x="42" y="48" fill="#0f172a" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="19" font-weight="700">GitHub Star Trend</text>',
        '  <text x="42" y="68" fill="#64748b" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="11.5">Daily aggregate only · no account data</text>',
        '  <rect x="622" y="34" width="94" height="38" rx="11" fill="#eff6ff" stroke="#bfdbfe"/>',
        f'  <text x="669" y="59" text-anchor="middle" fill="#1d4ed8" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="21" font-weight="750">{latest["stars"]}</text>',
    ]
    for tick in ticks:
        y = y_at(tick)
        lines.extend(
            [
                f'  <line x1="{plot_left:.1f}" y1="{y:.1f}" x2="{plot_right:.1f}" y2="{y:.1f}" stroke="#dbe4ee" stroke-width="1" stroke-dasharray="3 5"/>',
                f'  <text x="72" y="{y + 4:.1f}" text-anchor="end" fill="#64748b" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="11">{tick}</text>',
            ]
        )
    lines.extend(
        [
            f'  <line x1="{plot_left:.1f}" y1="{plot_bottom:.1f}" x2="{plot_right:.1f}" y2="{plot_bottom:.1f}" stroke="#94a3b8" stroke-width="1.2"/>',
            f'  <text x="{coordinates[0][0]:.1f}" y="246" text-anchor="middle" fill="#64748b" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="11">{points[0]["date"]}</text>',
        ]
    )
    if len(points) > 1:
        coordinate_text = " ".join(f"{x:.1f},{y:.1f}" for x, y in coordinates)
        area_path = (
            f"M {coordinates[0][0]:.1f},{plot_bottom:.1f} L {coordinate_text.replace(' ', ' L ')} "
            f"L {coordinates[-1][0]:.1f},{plot_bottom:.1f} Z"
        )
        lines.extend(
            [
                f'  <path data-role="trend-area" d="{area_path}" fill="url(#trendFill)"/>',
                f'  <polyline data-role="trend-line" points="{coordinate_text}" fill="none" stroke="#2563eb" stroke-width="3.2" stroke-linejoin="round" stroke-linecap="round"/>',
                f'  <text x="{plot_right:.1f}" y="246" text-anchor="end" fill="#64748b" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="11">{latest["date"]}</text>',
            ]
        )
    for index, (item, (x, y)) in enumerate(zip(points, coordinates, strict=True)):
        radius = 6.4 if index == len(points) - 1 else 4.7
        lines.append(
            f'  <circle data-role="series-point" data-date="{item["date"]}" data-stars="{item["stars"]}" cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="#ffffff" stroke="#2563eb" stroke-width="3"/>'
        )
    latest_x, latest_y = coordinates[-1]
    label_x = min(plot_right - 2, latest_x + 14)
    label_anchor = "end" if label_x >= plot_right - 2 else "start"
    lines.extend(
        [
            f'  <text x="{label_x:.1f}" y="{latest_y - 12:.1f}" text-anchor="{label_anchor}" fill="#0f172a" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="13" font-weight="700">{latest["stars"]}</text>',
            f'  <text x="718" y="258" text-anchor="end" fill="#94a3b8" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="9.5">{escaped_repository}</text>',
            "</svg>",
            "",
        ]
    )
    return "\n".join(lines)


def _serialize_payload(repository: str, snapshots: Sequence[dict[str, Any]]) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "repository": repository,
        "snapshots": _normalize_snapshots(snapshots),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _write_if_changed(path: Path, content: str) -> bool:
    encoded = content.encode("utf-8")
    if path.is_file() and path.read_bytes() == encoded:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(encoded)
    temporary.replace(path)
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="hang-jin/editaplot")
    parser.add_argument("--data", type=Path, default=Path("assets/star-trend/stars.json"))
    parser.add_argument("--svg", type=Path, default=Path("assets/star-trend/stars.svg"))
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="Render the checked-in aggregate data without making a network request.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = args.repository.strip()
    _repository_parts(repository)
    payload = load_payload(args.data, repository)
    snapshots = payload["snapshots"]
    if not args.render_only:
        count = fetch_star_count(repository, token=os.environ.get("GITHUB_TOKEN"))
        utc_day = datetime.now(timezone.utc).date()
        snapshots = upsert_daily_snapshot(snapshots, utc_day, count)
    data_text = _serialize_payload(repository, snapshots)
    svg_text = render_svg(repository, snapshots)
    data_changed = False if args.render_only else _write_if_changed(args.data, data_text)
    svg_changed = _write_if_changed(args.svg, svg_text)
    print(
        json.dumps(
            {
                "repository": repository,
                "latest": snapshots[-1],
                "data_changed": data_changed,
                "svg_changed": svg_changed,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
