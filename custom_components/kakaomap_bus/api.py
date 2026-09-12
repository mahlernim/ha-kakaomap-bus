"""KakaoMap requests and defensive response normalization."""

from __future__ import annotations

import asyncio
import json
import math
import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

import aiohttp

from .const import DEFAULT_REQUEST_RETRIES

API_URL = "https://map.kakao.com/bus/stop.json"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0"}
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)
MAP_HOSTS = {"map.kakao.com", "m.map.kakao.com"}
STOP_ID = re.compile(r"BS[0-9]+", re.IGNORECASE)


class InvalidStopID(ValueError):
    """The supplied value does not identify a KakaoMap bus stop."""


class InvalidResponse(ValueError):
    """KakaoMap returned an unusable response."""


class RateLimited(Exception):
    """KakaoMap requested a pause before the next request."""

    def __init__(self, retry_after: float) -> None:
        super().__init__("KakaoMap is temporarily limiting requests")
        self.retry_after = retry_after


def map_url(stop_id: str) -> str:
    """Return a map view, not the underlying JSON response."""
    return f"https://map.kakao.com/?target=bus&busStopId={stop_id}"


def _safe_link(value: str):
    """Accept only known map/share hosts, without credentials or custom ports."""
    try:
        parts = urlsplit(value.strip())
        if (
            parts.scheme not in {"http", "https"}
            or parts.hostname not in MAP_HOSTS | {"kko.to"}
            or parts.username is not None
            or parts.password is not None
            or parts.port not in {None, 80, 443}
        ):
            raise InvalidStopID
    except ValueError as err:
        raise InvalidStopID from err
    return parts


def parse_stop_id(value: str) -> str:
    """Accept a stop ID or an expanded KakaoMap URL."""
    value = value.strip()
    if STOP_ID.fullmatch(value):
        return value.upper()
    parts = _safe_link(value)
    if parts.hostname in MAP_HOSTS:
        for key, values in parse_qs(parts.query).items():
            if key.lower() == "busstopid" and len(values) == 1:
                if STOP_ID.fullmatch(values[0]):
                    return values[0].upper()
    raise InvalidStopID


async def async_resolve_stop_id(session: aiohttp.ClientSession, value: str) -> str:
    """Resolve supported share redirects without following arbitrary URLs."""
    try:
        return parse_stop_id(value)
    except InvalidStopID:
        parts = _safe_link(value)
        if parts.hostname != "kko.to" or not re.fullmatch(r"/[\w-]+/?", parts.path):
            raise

    url = urlunsplit(("https", "kko.to", parts.path, parts.query, ""))
    async with asyncio.timeout(10):
        for _ in range(5):
            parts = _safe_link(url)
            url = urlunsplit(("https", parts.hostname, parts.path, parts.query, ""))
            async with session.get(
                url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=False
            ) as response:
                if response.status not in {301, 302, 303, 307, 308}:
                    response.raise_for_status()
                    raise InvalidStopID
                location = response.headers.get("Location")
                if not location:
                    raise InvalidStopID
                url = urljoin(url, location)
            _safe_link(url)
            try:
                return parse_stop_id(url)
            except InvalidStopID:
                if urlsplit(url).hostname != "kko.to":
                    raise
    raise InvalidStopID


def _retry_after(value: str | None) -> float:
    """Parse the two Retry-After forms without accepting float-like values."""
    if not value:
        return 60

    candidate = value.strip()
    if re.fullmatch(r"[0-9]+", candidate):
        try:
            seconds = int(candidate)
            # The coordinator exposes this as an absolute datetime.  Reject a
            # syntactically valid delay if it cannot be represented there.
            datetime.now(UTC) + timedelta(seconds=seconds)
        except (OverflowError, ValueError):
            return 60
        return max(1, seconds)

    try:
        date = parsedate_to_datetime(candidate)
        if date.tzinfo is None:
            return 60
        seconds = (date.astimezone(UTC) - datetime.now(UTC)).total_seconds()
    except (TypeError, ValueError, OverflowError):
        return 60
    # An HTTP date has second precision. Rounding down avoids crossing
    # datetime.max after converting the duration back into a deadline.
    return max(1, math.floor(seconds)) if math.isfinite(seconds) else 60


def is_transient_api_error(err: Exception) -> bool:
    """Return whether a short retry can help."""
    return isinstance(err, (aiohttp.ClientConnectionError, asyncio.TimeoutError)) or (
        isinstance(err, aiohttp.ClientResponseError) and err.status >= 500
    )


async def async_fetch_stop_data(
    session: aiohttp.ClientSession, stop_id: str, retries: int = DEFAULT_REQUEST_RETRIES
) -> dict[str, Any]:
    """Fetch a stop, honoring rate limits and validating the response root."""
    attempts = max(1, retries)
    for attempt in range(1, attempts + 1):
        try:
            async with session.get(
                API_URL,
                params={"busstopid": parse_stop_id(stop_id)},
                headers=REQUEST_HEADERS,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status == 429:
                    raise RateLimited(_retry_after(response.headers.get("Retry-After")))
                if response.status in {400, 404}:
                    raise InvalidStopID
                response.raise_for_status()
                data = json.loads(await response.text())
                if not isinstance(data, dict):
                    raise InvalidResponse("Expected a stop object")
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            if attempt == attempts or not is_transient_api_error(err):
                raise
            await asyncio.sleep(min(attempt, 3))
    raise AssertionError("Unreachable retry state")


def arrival_seconds(value: Any) -> int | float | None:
    """Reject nulls, strings, booleans, negative values, and nonfinite numbers."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) and value >= 0 else None
    except OverflowError:
        return None


def validate_stop_identity(data: dict[str, Any], stop_id: str) -> str:
    """Ensure a payload belongs to the requested KakaoMap bus stop.

    A bad payload can be temporary upstream corruption, so callers receive
    ``InvalidResponse`` rather than the non-retryable user-input error.
    """
    if not isinstance(data, dict):
        raise InvalidResponse("Expected a stop object")
    response_stop_id = data.get("id")
    if not isinstance(response_stop_id, str) or not STOP_ID.fullmatch(response_stop_id):
        raise InvalidResponse("Missing or invalid stop ID")
    try:
        expected_stop_id = parse_stop_id(stop_id)
    except (AttributeError, InvalidStopID) as err:
        raise InvalidResponse("Invalid requested stop ID") from err
    normalized_response_id = response_stop_id.upper()
    if normalized_response_id != expected_stop_id:
        raise InvalidResponse("Response stop ID did not match request")
    return normalized_response_id


def build_bus_dict(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize routes so bad arrival fields cannot break entity properties."""
    if not isinstance(data, dict) or not isinstance(data.get("lines"), list):
        raise InvalidResponse("Missing route list")
    route_rows: dict[str, list[dict[str, Any]]] = {}
    for line in data["lines"]:
        if not isinstance(line, dict) or not isinstance(line.get("name"), str):
            continue
        name = line["name"]
        if not name.strip():
            continue
        route_rows.setdefault(name, []).append(line)

    buses = {}
    for name, rows in route_rows.items():
        line = rows[0]
        line_id = line.get("id") if isinstance(line.get("id"), str) else None
        # The API occasionally repeats one exact row.  Any other duplicate
        # route name is unsafe to select because route names are not IDs.
        duplicate_is_exact = (
            len(rows) > 1
            and line_id is not None
            and all(
                isinstance(row.get("id"), str) and row["id"] == line_id and row == line
                for row in rows[1:]
            )
        )
        ambiguous = len(rows) > 1 and not duplicate_is_exact
        source = line.get("arrival")
        source = source if isinstance(source, dict) else {}
        arrival = {key: arrival_seconds(source.get(key)) for key in ("arrivalTime", "arrivalTime2")}
        for key in ("direction", "vehicleType"):
            value = source.get(key)
            arrival[key] = value if isinstance(value, str) else None
        if ambiguous:
            arrival.update(arrivalTime=None, arrivalTime2=None, direction=None, vehicleType=None)
        buses[name] = {
            "id": None if ambiguous else line_id,
            "name": name,
            "arrival": arrival,
            "realtimeState": None if ambiguous else line.get("realtimeState"),
            "ambiguous": ambiguous,
        }
    if data["lines"] and not route_rows:
        raise InvalidResponse("No usable routes in response")
    return buses


def route_sort_key(name: str) -> tuple:
    """Sort 2, 10, 100 and mixed route names naturally."""
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", name)
    )


def build_bus_labels(data: dict[str, Any]) -> dict[str, str]:
    """Build route labels including the direction when available."""
    buses = build_bus_dict(data)
    return {
        name: f"{name} · {direction}"
        if (direction := buses[name]["arrival"]["direction"])
        else name
        for name in sorted(buses, key=route_sort_key)
        if not buses[name]["ambiguous"]
    }


def describe_api_error(err: Exception) -> str:
    """Provide useful messages without including response bodies."""
    if isinstance(err, aiohttp.ClientConnectorDNSError):
        return "Could not resolve KakaoMap; check DNS and network connectivity"
    if isinstance(err, asyncio.TimeoutError):
        return "Timed out contacting KakaoMap"
    if isinstance(err, (InvalidResponse, json.JSONDecodeError)):
        return "KakaoMap returned an invalid response"
    if isinstance(err, InvalidStopID):
        return "KakaoMap did not recognize the stop"
    if isinstance(err, RateLimited):
        return str(err)
    return "Could not retrieve KakaoMap arrival information"
