"""Stop-scoped request locking between runtime and metadata lookups."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kakaomap_bus.api import RateLimited
from custom_components.kakaomap_bus.config_flow import get_stop_info
from custom_components.kakaomap_bus.const import DOMAIN
from custom_components.kakaomap_bus.coordinator import KakaoBusCoordinator
from tests.test_runtime import setup

COORDINATOR_FETCH = "custom_components.kakaomap_bus.coordinator.async_fetch_stop_data"
FLOW_FETCH = "custom_components.kakaomap_bus.config_flow.async_fetch_stop_data"


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={"stop_id": "BS12345", "stop_name": "예시역"},
        options={"buses": ["10"], "quiet_enabled": False},
        minor_version=2,
    )


async def test_metadata_lookup_and_runtime_refresh_share_one_stop_request(hass, stop_payload):
    entry = _entry()
    entry.add_to_hass(hass)
    coordinator = KakaoBusCoordinator(hass, entry)
    entered = asyncio.Event()
    release = asyncio.Event()
    active = 0
    peak = 0

    async def fetch(*_args, **_kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        entered.set()
        await release.wait()
        active -= 1
        return stop_payload

    with (
        patch(COORDINATOR_FETCH, new=AsyncMock(side_effect=fetch)) as runtime_fetch,
        patch(FLOW_FETCH, new=AsyncMock(side_effect=fetch)) as metadata_fetch,
    ):
        runtime = asyncio.create_task(coordinator._async_update_data())
        await entered.wait()
        metadata = asyncio.create_task(get_stop_info(hass, "BS12345", entry_id=entry.entry_id))
        await asyncio.sleep(0)
        assert runtime_fetch.await_count == 1
        metadata_fetch.assert_not_awaited()
        release.set()
        await asyncio.gather(runtime, metadata)

    assert peak == 1
    await coordinator.async_shutdown()


async def test_rate_limit_deadline_is_checked_after_waiting_for_shared_lock(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    coordinator = KakaoBusCoordinator(hass, entry)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def rate_limited(*_args, **_kwargs):
        entered.set()
        await release.wait()
        raise RateLimited(120)

    with patch(COORDINATOR_FETCH, new=AsyncMock(side_effect=rate_limited)) as fetch:
        first = asyncio.create_task(coordinator._async_update_data())
        await entered.wait()
        second = asyncio.create_task(coordinator._async_update_data())
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(UpdateFailed):
            await first
        with pytest.raises(UpdateFailed) as error:
            await second

    assert error.value.retry_after > 0
    assert fetch.await_count == 1
    await coordinator.async_shutdown()


async def test_metadata_rate_limit_immediately_notifies_live_coordinator(hass, stop_payload):
    entry, coordinator, _, status = await setup(hass, stop_payload)
    with (
        patch(FLOW_FETCH, new=AsyncMock(side_effect=RateLimited(120))),
        patch.object(coordinator, "_schedule_refresh") as schedule_refresh,
    ):
        with pytest.raises(RateLimited):
            await get_stop_info(hass, "BS12345", entry_id=entry.entry_id)
    await hass.async_block_till_done()
    schedule_refresh.assert_called_once()
    assert hass.states.get(status).state == "rate_limited"
    await hass.config_entries.async_unload(entry.entry_id)
