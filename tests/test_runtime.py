"""Test actual HA entity state, registry compatibility, and coordinator lifecycle."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.kakaomap_bus.api import RateLimited
from custom_components.kakaomap_bus.const import DOMAIN
from tests.test_config_flow import make_entry

FETCH = "custom_components.kakaomap_bus.coordinator.async_fetch_stop_data"


async def setup(hass, stop_payload, *, options=None, registry_id=None):
    await hass.config.async_set_time_zone("Asia/Seoul")
    hass.config.language = "ko"
    entry = make_entry(options=options)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    if registry_id:
        registry.async_get_or_create(
            "sensor",
            DOMAIN,
            "kakaobus_BS12345_10",
            suggested_object_id=registry_id,
            config_entry=entry,
        )
    with patch(FETCH, new=AsyncMock(return_value=stop_payload)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    arrival = registry.async_get_entity_id("sensor", DOMAIN, "kakaobus_BS12345_10")
    status = registry.async_get_entity_id("sensor", DOMAIN, "kakaobus_status_BS12345_10")
    return entry, coordinator, arrival, status


async def test_live_entities_preserve_registered_id(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T03:00:00Z")
    entry, coordinator, arrival, status = await setup(
        hass, stop_payload, registry_id="existing_bus"
    )
    assert arrival == "sensor.existing_bus"
    state = hass.states.get(arrival)
    assert state.state == "2"
    assert state.attributes["next_bus_min"] == 10
    assert state.attributes["direction"] == "시청 방향"
    assert "10 · 시청 방향" in state.name
    status_state = hass.states.get(status)
    assert status_state.state == "live"
    assert "도착 정보 상태" in status_state.name
    assert status_state.attributes["last_success"] is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert coordinator._shutdown_requested
    assert coordinator._unsub_pause is None


async def test_failed_refresh_clears_both_estimates_and_status_explains(
    hass, stop_payload, freezer
):
    freezer.move_to("2026-09-05T03:00:00Z")
    entry, coordinator, arrival, status = await setup(hass, stop_payload)
    last_success = coordinator.last_success
    with patch(FETCH, new=AsyncMock(side_effect=asyncio.TimeoutError)):
        await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(arrival).state == "unavailable"
    # HA drops custom attributes on unavailable entities; consumers must see no estimate.
    assert hass.states.get(arrival).attributes.get("next_bus_min") is None
    assert hass.states.get(status).state == "connection_lost"
    assert coordinator.last_success == last_success
    with patch(FETCH, new=AsyncMock(return_value={"error": "bad payload"})):
        await coordinator.async_refresh()
    with patch(FETCH, new=AsyncMock(side_effect=asyncio.TimeoutError)):
        await coordinator.async_refresh()
    assert hass.states.get(status).state == "connection_lost"
    with patch(FETCH, new=AsyncMock(return_value=stop_payload)):
        await coordinator.async_refresh()
    assert hass.states.get(arrival).state == "2"
    assert hass.states.get(status).state == "live"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_pause_clears_old_arrivals_and_resumes_at_boundary(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T14:59:00Z")  # 23:59 KST
    entry, coordinator, arrival, status = await setup(
        hass, stop_payload, options={"scan_interval": 600}
    )
    with patch(FETCH, new=AsyncMock(return_value=stop_payload)) as fetch:
        freezer.move_to("2026-09-05T15:00:00Z")
        async_fire_time_changed(hass, datetime(2026, 9, 5, 15, tzinfo=UTC))
        await hass.async_block_till_done()
        fetch.assert_not_awaited()
        assert hass.states.get(arrival).state == "unknown"
        assert hass.states.get(arrival).attributes["next_bus_min"] is None
        assert hass.states.get(status).state == "paused"
        assert coordinator.paused_until.hour == 5
        freezer.move_to("2026-09-05T20:00:00Z")
        async_fire_time_changed(hass, datetime(2026, 9, 5, 20, tzinfo=UTC))
        await hass.async_block_till_done()
        fetch.assert_awaited()
        assert hass.states.get(arrival).state == "2"
        assert hass.states.get(status).state == "live"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_startup_while_paused_needs_no_request(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T17:00:00Z")
    entry, coordinator, arrival, status = await setup(hass, stop_payload)
    assert coordinator.last_success is None
    assert hass.states.get(arrival).state == "unknown"
    assert hass.states.get(status).state == "paused"
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "arrival,expected,next_bus",
    [
        (None, "unknown", None),
        ({"arrivalTime": None}, "unknown", None),
        ({"arrivalTime": "120"}, "unknown", None),
        ({"arrivalTime": -60}, "unknown", None),
        ({"arrivalTime": True}, "unknown", None),
        ({"arrivalTime": 120, "arrivalTime2": None}, "2", None),
        ({"arrivalTime": 120, "arrivalTime2": "600"}, "2", None),
    ],
)
async def test_bad_arrival_values_never_break_entity_updates(
    hass, stop_payload, freezer, arrival, expected, next_bus
):
    freezer.move_to("2026-09-05T03:00:00Z")
    stop_payload["lines"][0]["arrival"] = arrival
    entry, _, entity_id, status = await setup(hass, stop_payload)
    assert hass.states.get(entity_id).state == expected
    assert hass.states.get(entity_id).attributes["next_bus_min"] == next_bus
    assert hass.states.get(status).state == ("no_arrival" if expected == "unknown" else "live")
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "options",
    [
        {"quiet_start": "00:00", "quiet_end": "00:00"},
        {"quiet_enabled": False},
        {"quiet_start": "25:99"},
    ],
)
async def test_disabled_equal_or_invalid_legacy_pause_continues_polling(
    hass, stop_payload, freezer, options
):
    freezer.move_to("2026-09-05T17:00:00Z")
    entry, _, arrival, status = await setup(hass, stop_payload, options=options)
    assert hass.states.get(arrival).state == "2"
    assert hass.states.get(status).state == "live"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_missing_selected_route_reports_no_arrival(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T03:00:00Z")
    entry, coordinator, arrival, status = await setup(hass, stop_payload)
    stop_payload["lines"] = []
    with patch(FETCH, new=AsyncMock(return_value=stop_payload)):
        await coordinator.async_refresh()
    assert hass.states.get(arrival).state == "unknown"
    assert hass.states.get(status).state == "no_arrival"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_rate_limit_delay_reaches_ha_scheduler(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T03:00:00Z")
    entry, coordinator, arrival, status = await setup(hass, stop_payload)
    with patch(FETCH, new=AsyncMock(side_effect=RateLimited(120))):
        await coordinator.async_refresh()
    assert coordinator.last_exception.retry_after == 120
    assert hass.states.get(arrival).state == "unavailable"
    assert hass.states.get(status).state == "rate_limited"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_options_reload_keeps_identity_and_cancels_old_coordinator(
    hass, stop_payload, freezer
):
    freezer.move_to("2026-09-05T03:00:00Z")
    entry, previous, arrival, _ = await setup(hass, stop_payload, registry_id="existing_bus")
    with patch(FETCH, new=AsyncMock(return_value=stop_payload)):
        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                "stop_nickname": "퇴근길",
                "scan_interval": 120,
                "polling_mode": "fixed",
            },
        )
        await hass.async_block_till_done()
    assert previous._shutdown_requested
    assert previous._unsub_pause is None
    assert hass.states.get(arrival).state == "2"
    assert "퇴근길" in hass.states.get(arrival).name
    assert hass.data[DOMAIN][entry.entry_id].update_interval.total_seconds() == 120
    await hass.config_entries.async_unload(entry.entry_id)
