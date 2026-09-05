"""Stop links, response validation, and request policy."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest

from custom_components.kakaomap_bus import api


@pytest.mark.parametrize(
    "value",
    [
        "BS12345",
        " bs12345 ",
        "https://map.kakao.com/?target=bus&busStopId=BS12345",
        "https://m.map.kakao.com/?busstopid=BS12345",
    ],
)
def test_stop_id_and_map_link(value):
    assert api.parse_stop_id(value) == "BS12345"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "12345",
        "BS12345&x=1",
        "https://example.com/?busStopId=BS12345",
        "https://map.kakao.com.evil.test/?busStopId=BS12345",
        "https://map.kakao.com@127.0.0.1/?busStopId=BS12345",
        "https://user@map.kakao.com/?busStopId=BS12345",
        "https://map.kakao.com:8123/?busStopId=BS12345",
        "https://map.kakao.com/?busStopId=BS12345&busStopId=BS999",
        "https://map.kakao.com/?busStopId=BS12345%26x%3D1",
    ],
)
def test_invalid_stop_links(value):
    with pytest.raises(api.InvalidStopID):
        api.parse_stop_id(value)


class Response:
    def __init__(self, status=200, body='{"lines": []}', headers=None, error=None):
        self.status, self.body = status, body
        self.headers = headers or {}
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        if self.error:
            raise self.error
        if self.status >= 400:
            raise aiohttp.ClientResponseError(Mock(), (), status=self.status)

    async def text(self):
        return self.body


async def test_short_share_link_uses_validated_redirects():
    session = Mock()
    session.get.return_value = Response(
        302,
        headers={
            "Location": "https://map.kakao.com/?busStopId=BS12345",
        },
    )
    assert await api.async_resolve_stop_id(session, "http://kko.to/example") == "BS12345"
    assert session.get.call_args.args[0] == "https://kko.to/example"
    assert session.get.call_args.kwargs["allow_redirects"] is False


@pytest.mark.parametrize(
    "location",
    [
        "http://127.0.0.1/private",
        "http://192.168.0.1/",
        "https://evil.test/",
        "https://map.kakao.com:8123/",
        "https://user@map.kakao.com/?busStopId=BS12345",
    ],
)
async def test_short_link_rejects_unsafe_redirect_before_request(location):
    session = Mock()
    session.get.return_value = Response(302, headers={"Location": location})
    with pytest.raises(api.InvalidStopID):
        await api.async_resolve_stop_id(session, "https://kko.to/example")
    assert session.get.call_count == 1


async def test_short_link_redirect_loop_is_bounded():
    session = Mock()
    session.get.return_value = Response(302, headers={"Location": "/example"})
    with pytest.raises(api.InvalidStopID):
        await api.async_resolve_stop_id(session, "https://kko.to/example")
    assert session.get.call_count == 5


async def test_short_link_landing_page_needs_an_id():
    session = Mock()
    session.get.return_value = Response(200)
    with pytest.raises(api.InvalidStopID):
        await api.async_resolve_stop_id(session, "https://kko.to/example")


async def test_api_retry_recovers():
    session = Mock()
    session.get.side_effect = [Response(error=asyncio.TimeoutError()), Response()]
    with patch.object(api.asyncio, "sleep", new=AsyncMock()):
        assert await api.async_fetch_stop_data(session, "BS12345") == {"lines": []}
    assert session.get.call_count == 2
    assert session.get.call_args.kwargs["params"] == {"busstopid": "BS12345"}


async def test_server_error_retry_is_bounded():
    session = Mock()
    session.get.return_value = Response(503)
    with patch.object(api.asyncio, "sleep", new=AsyncMock()):
        with pytest.raises(aiohttp.ClientResponseError):
            await api.async_fetch_stop_data(session, "BS12345")
    assert session.get.call_count == 3


async def test_rate_limit_does_not_retry_immediately():
    session = Mock()
    session.get.return_value = Response(429, headers={"Retry-After": "120"})
    with pytest.raises(api.RateLimited) as err:
        await api.async_fetch_stop_data(session, "BS12345")
    assert err.value.retry_after == 120
    assert session.get.call_count == 1


async def test_not_found_has_distinct_error():
    session = Mock()
    session.get.return_value = Response(404)
    with pytest.raises(api.InvalidStopID):
        await api.async_fetch_stop_data(session, "BS12345")
    assert session.get.call_count == 1


@pytest.mark.parametrize("body", ["null", "[]", "42"])
async def test_invalid_json_root(body):
    session = Mock()
    session.get.return_value = Response(body=body)
    with pytest.raises(api.InvalidResponse):
        await api.async_fetch_stop_data(session, "BS12345")


@pytest.mark.parametrize("value", [None, "120", -60, True, False, float("nan"), float("inf")])
def test_unsafe_arrival_values_are_cleared(stop_payload, value):
    data = deepcopy(stop_payload)
    data["lines"][0]["arrival"].update(arrivalTime=value, arrivalTime2=value)
    arrival = api.build_bus_dict(data)["10"]["arrival"]
    assert arrival["arrivalTime"] is None and arrival["arrivalTime2"] is None


def test_null_arrival_and_malformed_route_do_not_break_other_routes(stop_payload):
    stop_payload["lines"][1]["arrival"] = None
    stop_payload["lines"].append(None)
    buses = api.build_bus_dict(stop_payload)
    assert buses["10"]["arrival"]["arrivalTime"] == 120
    assert buses["2"]["arrival"]["arrivalTime"] is None
    assert list(api.build_bus_labels(stop_payload)) == ["2", "10"]


def test_route_labels_show_direction_and_natural_order(stop_payload):
    assert api.build_bus_labels(stop_payload) == {
        "2": "2 · 공원 방향",
        "10": "10 · 시청 방향",
    }


@pytest.mark.parametrize("payload", [{}, {"lines": None}, {"lines": [None]}, []])
def test_unusable_route_list_is_rejected(payload):
    with pytest.raises(api.InvalidResponse):
        api.build_bus_dict(payload)
