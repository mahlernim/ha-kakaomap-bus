"""Exercise actual HA flow management, validation, and error recovery."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.selector import SelectSelector, SelectSelectorMode, TimeSelector
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kakaomap_bus.api import InvalidResponse, InvalidStopID, RateLimited
from custom_components.kakaomap_bus.config_flow import OptionsFlowHandler
from custom_components.kakaomap_bus.const import (
    CONF_POLLING_MODE,
    DOMAIN,
    POLLING_ADAPTIVE,
    POLLING_FIXED,
)

FETCH = "custom_components.kakaomap_bus.config_flow.async_fetch_stop_data"


def make_entry(data=None, options=None):
    return MockConfigEntry(
        domain=DOMAIN,
        title="예시역 (BS12345)",
        unique_id="BS12345",
        data={"stop_id": "BS12345", "stop_name": "예시역", **(data or {})},
        options={"buses": ["10"], "quiet_start": "00:00", "quiet_end": "05:00", **(options or {})},
    )


@pytest.mark.parametrize("value", [" bs12345 ", "https://map.kakao.com/?busStopId=BS12345"])
async def test_complete_setup_and_confirmation(hass, stop_payload, value):
    with (
        patch(FETCH, new=AsyncMock(return_value=stop_payload)) as fetch,
        patch("custom_components.kakaomap_bus.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"stop_id": value}
        )
        assert result["step_id"] == "select_bus"
        assert result["description_placeholders"]["stop_name"] == "예시역"
        assert result["description_placeholders"]["direction"] == "시청 방향"
        assert isinstance(result["data_schema"].schema["buses"], SelectSelector)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "buses": [],
                "polling": {"polling_mode": POLLING_ADAPTIVE, "scan_interval": 90},
                "pause": {"quiet_enabled": True, "quiet_start": "00:00", "quiet_end": "05:00"},
            },
        )
        assert result["errors"] == {"buses": "select_bus"}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "buses": ["10"],
                "stop_nickname": " 출근길 ",
                "polling": {"polling_mode": POLLING_ADAPTIVE, "scan_interval": 90},
                "pause": {"quiet_enabled": True, "quiet_start": "00:00", "quiet_end": "05:00"},
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["stop_id"] == "BS12345"
    assert result["options"]["stop_nickname"] == "출근길"
    assert result["options"]["quiet_enabled"] is True
    assert result["options"]["scan_interval"] == 90
    assert result["options"][CONF_POLLING_MODE] == POLLING_ADAPTIVE
    assert fetch.await_count == 1


async def test_duplicate_stop_is_detected_after_normalization(hass):
    make_entry().add_to_hass(hass)
    with patch(FETCH, new=AsyncMock()) as fetch:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"stop_id": " bs12345 "}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    fetch.assert_not_awaited()


@pytest.mark.parametrize(
    "error,key",
    [
        (asyncio.TimeoutError(), "cannot_connect"),
        (InvalidStopID(), "invalid_stop_id"),
        (InvalidResponse(), "invalid_response"),
        (RateLimited(120), "rate_limited"),
    ],
)
async def test_lookup_error_keeps_input_and_recovers(hass, stop_payload, error, key):
    with patch(FETCH, new=AsyncMock(side_effect=[error, stop_payload])):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"stop_id": "BS12345"}
        )
        assert result["errors"] == {"base": key}
        assert result["data_schema"]({})["stop_id"] == "BS12345"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"stop_id": "BS12345"}
        )
    assert result["step_id"] == "select_bus"


async def test_no_routes_is_not_a_successful_empty_setup(hass, stop_payload):
    stop_payload["lines"] = []
    with patch(FETCH, new=AsyncMock(return_value=stop_payload)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"stop_id": "BS12345"}
        )
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "no_buses_found"}


async def test_setup_validation_redisplays_nested_polling_and_pause_values(hass, stop_payload):
    with patch(FETCH, new=AsyncMock(return_value=stop_payload)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"stop_id": "BS12345"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "buses": ["10"],
                "polling": {"polling_mode": POLLING_FIXED, "scan_interval": 120},
                "pause": {"quiet_enabled": True, "quiet_start": "22:00", "quiet_end": "22:00"},
            },
        )
    assert result["errors"] == {"base": "equal_pause_times"}
    values = result["data_schema"]({"buses": ["10"], "polling": {}, "pause": {}})
    assert values["polling"] == {"polling_mode": POLLING_FIXED, "scan_interval": 120}
    assert values["pause"] == {
        "quiet_enabled": True,
        "quiet_start": "22:00",
        "quiet_end": "22:00",
    }


def form_input(**kwargs):
    return {
        "buses": ["10"],
        "stop_nickname": "출근길",
        "pause": {
            "quiet_enabled": True,
            "quiet_start": "23:00",
            "quiet_end": "05:30",
        },
        "polling": {"polling_mode": POLLING_FIXED, "scan_interval": 120},
        **kwargs,
    }


async def test_options_sections_save_without_second_fetch(hass, stop_payload):
    entry = make_entry(options={"future_option": "preserve"})
    entry.add_to_hass(hass)
    with patch(FETCH, new=AsyncMock(return_value=stop_payload)) as fetch:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        keys = [str(key) for key in result["data_schema"].schema]
        assert keys == ["buses", "stop_nickname", "polling", "pause"]
        pause = result["data_schema"].schema["pause"]
        assert isinstance(pause.schema.schema["quiet_start"], TimeSelector)
        assert isinstance(result["data_schema"].schema["buses"], SelectSelector)
        result = await hass.config_entries.options.async_configure(result["flow_id"], form_input())
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert fetch.await_count == 1
    assert entry.options["quiet_start"] == "23:00:00"
    assert entry.options["quiet_end"] == "05:30:00"
    assert entry.options["future_option"] == "preserve"
    assert "pause" not in entry.options
    assert entry.data["stop_id"] == "BS12345"
    assert entry.data["stop_name"] == "예시역"
    assert entry.data["stop_direction"] == "시청 방향"
    assert entry.data["route_labels"] == {"2": "2 · 공원 방향", "10": "10 · 시청 방향"}


async def test_options_work_offline_and_keep_choices(hass):
    entry = make_entry()
    entry.add_to_hass(hass)
    with patch(FETCH, new=AsyncMock(side_effect=asyncio.TimeoutError)) as fetch:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["errors"] == {"base": "route_list_unavailable"}
        result = await hass.config_entries.options.async_configure(result["flow_id"], form_input())
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["buses"] == ["10"]
    assert fetch.await_count == 1


async def test_equal_pause_times_show_error_and_preserve_routes(hass, stop_payload):
    entry = make_entry()
    entry.add_to_hass(hass)
    with patch(FETCH, new=AsyncMock(return_value=stop_payload)):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        values = form_input(
            buses=["2"], pause={"quiet_enabled": True, "quiet_start": "00:00", "quiet_end": "00:00"}
        )
        result = await hass.config_entries.options.async_configure(result["flow_id"], values)
        assert result["errors"] == {"base": "equal_pause_times"}
        assert result["data_schema"]({"pause": {}, "polling": {}})["buses"] == ["2"]
        values["pause"]["quiet_enabled"] = False
        result = await hass.config_entries.options.async_configure(result["flow_id"], values)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["quiet_enabled"] is False


@pytest.mark.parametrize(
    "options",
    [
        {"quiet_start": "invalid"},
        {"quiet_start": "00:00", "quiet_end": "00:00"},
    ],
)
async def test_invalid_legacy_pause_defaults_to_disabled(hass, options):
    entry = make_entry(options=options)
    entry.add_to_hass(hass)
    flow = OptionsFlowHandler()
    flow.hass, flow.handler = hass, entry.entry_id
    assert flow._defaults()["pause"]["quiet_enabled"] is False


async def test_reconfigure_refreshes_same_stop_metadata(hass, stop_payload):
    entry = make_entry(data={"route_labels": {"10": "10 · 이전 방향"}})
    entry.add_to_hass(hass)
    with patch(FETCH, new=AsyncMock(return_value=stop_payload)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
        )
        assert result["step_id"] == "reconfigure"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["stop_id"] == "BS12345"
    assert entry.data["route_labels"] == {"2": "2 · 공원 방향", "10": "10 · 시청 방향"}


async def test_options_keep_existing_ambiguous_route_but_exclude_new_choice(hass, stop_payload):
    entry = make_entry(options={"buses": ["중복", "10"]})
    entry.add_to_hass(hass)
    stop_payload["lines"].extend(
        [
            {"id": "A", "name": "중복", "arrival": {}},
            {"id": "B", "name": "중복", "arrival": {}},
        ]
    )
    with patch(FETCH, new=AsyncMock(return_value=stop_payload)):
        result = await hass.config_entries.options.async_init(entry.entry_id)
    selector = result["data_schema"].schema["buses"]
    values = {item["value"] for item in selector.config["options"]}
    assert values == {"2", "10", "중복"}
    assert selector.config["custom_value"] is False
    assert selector.config["mode"] == SelectSelectorMode.DROPDOWN.value


async def test_setup_explains_when_all_routes_are_ambiguous(hass, stop_payload):
    stop_payload["lines"] = [
        {"id": "A", "name": "중복", "arrival": {}},
        {"id": "B", "name": "중복", "arrival": {}},
    ]
    with patch(FETCH, new=AsyncMock(return_value=stop_payload)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"stop_id": "BS12345"}
        )
    assert result["errors"] == {"base": "ambiguous_routes_only"}


async def test_options_do_not_fetch_before_an_active_rate_limit_deadline(hass):
    entry = make_entry()
    entry.add_to_hass(hass)
    hass.data[f"{DOMAIN}_recovery"] = {
        entry.entry_id: {
            "failures": 0,
            "deadline": 1000.0,
            "reason": "rate_limited",
            "retry_at": dt_util.utcnow() + timedelta(seconds=900),
        }
    }
    with (
        patch("custom_components.kakaomap_bus.config_flow.monotonic", return_value=100.0),
        patch(FETCH, new=AsyncMock()) as fetch,
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["errors"] == {"base": "rate_limited"}
    fetch.assert_not_awaited()


async def test_reconfigure_does_not_fetch_before_an_active_rate_limit_deadline(hass):
    entry = make_entry()
    entry.add_to_hass(hass)
    hass.data[f"{DOMAIN}_recovery"] = {
        entry.entry_id: {
            "failures": 0,
            "deadline": 1000.0,
            "reason": "rate_limited",
            "retry_at": dt_util.utcnow() + timedelta(seconds=900),
        }
    }
    with (
        patch("custom_components.kakaomap_bus.config_flow.monotonic", return_value=100.0),
        patch(FETCH, new=AsyncMock()) as fetch,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "rate_limited"}
    fetch.assert_not_awaited()


async def test_reconfigure_429_sets_the_shared_rate_limit_deadline(hass):
    entry = make_entry()
    entry.add_to_hass(hass)
    with (
        patch("custom_components.kakaomap_bus.config_flow.monotonic", return_value=100.0),
        patch(FETCH, new=AsyncMock(side_effect=RateLimited(120))),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    recovery = hass.data[f"{DOMAIN}_recovery"][entry.entry_id]
    assert result["errors"] == {"base": "rate_limited"}
    assert recovery["reason"] == "rate_limited"
    assert recovery["deadline"] == 220.0
    assert recovery["retry_at"] is not None
