"""v1.3 runtime policy and local-countdown regression coverage."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kakaomap_bus import async_migrate_entry
from custom_components.kakaomap_bus.api import RateLimited, build_bus_dict
from custom_components.kakaomap_bus.const import DOMAIN, POLLING_FIXED
from custom_components.kakaomap_bus.coordinator import KakaoBusCoordinator
from tests.test_runtime import FETCH, setup


async def test_local_countdown_expires_without_changing_last_success_or_promoting_second_bus(
    hass, stop_payload, freezer
):
    freezer.move_to("2026-09-05T03:00:00Z")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"stop_id": "BS12345", "stop_name": "예시역"},
        options={"buses": ["10"], "quiet_enabled": False},
        minor_version=2,
    )
    entry.add_to_hass(hass)
    coordinator = KakaoBusCoordinator(hass, entry)
    coordinator.data = build_bus_dict(stop_payload)
    last_success = coordinator.last_success = freezer()
    coordinator._receipt = 1_000

    try:
        with patch("custom_components.kakaomap_bus.coordinator.monotonic", return_value=1_120):
            coordinator._local_tick()
            assert coordinator.last_success == last_success
            assert coordinator.route_status("10") == "expired"
    finally:
        await coordinator.async_shutdown()


async def test_local_countdown_uses_monotonic_time_across_wall_clock_changes(
    hass, stop_payload, freezer
):
    freezer.move_to("2026-09-05T03:00:00Z")
    entry, coordinator, arrival, _ = await setup(hass, stop_payload)
    coordinator._receipt = 1_000

    with patch("custom_components.kakaomap_bus.coordinator.monotonic", return_value=1_060):
        freezer.move_to("2036-09-05T03:00:00Z")
        coordinator._local_tick()
        await hass.async_block_till_done()

    assert hass.states.get(arrival).state == "1"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_adaptive_interval_changes_at_three_minute_threshold(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T03:00:00Z")
    stop_payload["lines"][0]["arrival"]["arrivalTime"] = 181
    entry, coordinator, _, _ = await setup(hass, stop_payload)
    coordinator._receipt = 1_000

    with patch("custom_components.kakaomap_bus.coordinator.monotonic", return_value=1_000):
        assert coordinator._poll_interval() == 120
    with patch("custom_components.kakaomap_bus.coordinator.monotonic", return_value=1_001):
        assert coordinator._poll_interval() == 30
    await hass.config_entries.async_unload(entry.entry_id)


async def test_fixed_mode_keeps_saved_interval(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"stop_id": "BS12345", "stop_name": "예시역"},
        options={"buses": ["10"], "polling_mode": POLLING_FIXED, "scan_interval": 300},
        minor_version=2,
    )
    entry.add_to_hass(hass)
    coordinator = KakaoBusCoordinator(hass, entry)
    assert coordinator._poll_interval() == 300
    await coordinator.async_shutdown()


async def test_disabled_polling_keeps_local_expiry_without_request(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T03:00:00Z")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"stop_id": "BS12345", "stop_name": "예시역"},
        options={"buses": ["10"], "quiet_enabled": False},
        pref_disable_polling=True,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    coordinator = KakaoBusCoordinator(hass, entry)
    coordinator.data = build_bus_dict(stop_payload)
    coordinator._receipt = 1_000
    try:
        with (
            patch(FETCH, new=AsyncMock()) as fetch,
            patch("custom_components.kakaomap_bus.coordinator.monotonic", return_value=1_120),
        ):
            coordinator._local_tick()
        fetch.assert_not_awaited()
        assert coordinator.route_status("10") == "expired"
    finally:
        await coordinator.async_shutdown()


async def test_rate_limit_blocks_direct_refresh_until_its_deadline(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T03:00:00Z")
    entry, coordinator, _, status = await setup(hass, stop_payload)
    with patch(FETCH, new=AsyncMock(side_effect=RateLimited(120))):
        await coordinator.async_refresh()
    with patch(FETCH, new=AsyncMock()) as fetch:
        await coordinator.async_refresh()
    fetch.assert_not_awaited()
    assert hass.states.get(status).state == "rate_limited"
    assert coordinator.retry_at is not None
    await hass.config_entries.async_unload(entry.entry_id)


async def test_quiet_hours_block_direct_refresh_without_network(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T17:00:00Z")
    entry, coordinator, _, status = await setup(hass, stop_payload)
    with patch(FETCH, new=AsyncMock()) as fetch:
        await coordinator.async_refresh()
    fetch.assert_not_awaited()
    assert hass.states.get(status).state == "paused"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_non_rate_failures_back_off_from_two_to_fifteen_minutes(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T03:00:00Z")
    entry, coordinator, _, _ = await setup(hass, stop_payload)
    with patch(FETCH, new=AsyncMock(side_effect=asyncio.TimeoutError)):
        for expected in (120, 240, 480, 900):
            with pytest.raises(UpdateFailed) as err:
                await coordinator._async_update_data()
            assert err.value.retry_after == expected
    await hass.config_entries.async_unload(entry.entry_id)


async def test_wrong_stop_identity_is_not_published_as_live_data(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T03:00:00Z")
    entry, coordinator, arrival, status = await setup(hass, stop_payload)
    wrong_stop = deepcopy(stop_payload)
    wrong_stop["id"] = "BS99999"
    last_success = coordinator.last_success
    with patch(FETCH, new=AsyncMock(return_value=wrong_stop)):
        await coordinator.async_refresh()
    assert coordinator.last_success == last_success
    assert hass.states.get(arrival).state == "unavailable"
    assert hass.states.get(status).state == "connection_lost"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_duplicate_selected_route_reports_ambiguity_and_never_exposes_estimates(
    hass, stop_payload, freezer
):
    freezer.move_to("2026-09-05T03:00:00Z")
    conflicting = deepcopy(stop_payload["lines"][0])
    conflicting["id"] = "B10-alt"
    conflicting["arrival"]["arrivalTime"] = 10
    stop_payload["lines"].append(conflicting)
    entry, _, arrival, status = await setup(hass, stop_payload)
    assert hass.states.get(arrival).state == "unknown"
    assert hass.states.get(arrival).attributes["next_bus_min"] is None
    assert hass.states.get(status).state == "ambiguous_route"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_direction_change_updates_arrival_and_status_labels(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T03:00:00Z")
    entry, coordinator, arrival, status = await setup(hass, stop_payload)
    updated = deepcopy(stop_payload)
    updated["lines"][0]["arrival"]["direction"] = "신항 방향"
    with patch(FETCH, new=AsyncMock(return_value=updated)):
        await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert "신항 방향" in hass.states.get(arrival).name
    assert "신항 방향" in hass.states.get(status).name
    await hass.config_entries.async_unload(entry.entry_id)


async def test_deselect_and_reselect_preserves_custom_entity_id(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T03:00:00Z")
    entry, _, arrival, _ = await setup(hass, stop_payload, registry_id="my_commute_bus")
    registry = er.async_get(hass)

    hass.config_entries.async_update_entry(entry, options={**entry.options, "buses": []})
    await hass.async_block_till_done()
    assert registry.async_get(arrival) is not None

    with patch(FETCH, new=AsyncMock(return_value=stop_payload)):
        hass.config_entries.async_update_entry(entry, options={**entry.options, "buses": ["10"]})
        await hass.async_block_till_done()
    assert registry.async_get_entity_id("sensor", DOMAIN, "kakaobus_BS12345_10") == arrival
    await hass.config_entries.async_unload(entry.entry_id)


async def test_metadata_refresh_preserves_user_assigned_device_name(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T03:00:00Z")
    entry, coordinator, _, _ = await setup(hass, stop_payload)
    registry = dr.async_get(hass)
    device = next(
        (
            device
            for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
            if (DOMAIN, "BS12345") in device.identifiers
        ),
        None,
    )
    assert device is not None
    registry.async_update_device(device.id, name_by_user="내 정류장")
    refreshed = deepcopy(stop_payload)
    refreshed["name"] = "새 정류장 이름"
    with patch(FETCH, new=AsyncMock(return_value=refreshed)):
        await coordinator.async_refresh()
    assert registry.async_get(device.id).name_by_user == "내 정류장"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_entry_unload_cancels_local_countdown_timer(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T03:00:00Z")
    entry, coordinator, _, _ = await setup(hass, stop_payload)
    assert coordinator._unsub_local is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert coordinator._shutdown_requested
    assert coordinator._unsub_local is None


async def test_entry_migration_preserves_fixed_interval_and_does_not_override_later_fixed_choice(
    hass,
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"stop_id": "BS12345", "scan_interval": 90},
        options={"scan_interval": 300},
        version=1,
        minor_version=1,
    )
    entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, entry)
    assert entry.options["scan_interval"] == 300
    assert entry.options["polling_mode"] == "adaptive"
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "polling_mode": "fixed"}
    )
    assert await async_migrate_entry(hass, entry)
    assert entry.options["polling_mode"] == "fixed"
