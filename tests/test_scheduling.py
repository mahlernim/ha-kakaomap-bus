"""Exercise actual HA scheduled callbacks, not just interval calculations."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.kakaomap_bus.api import RateLimited
from tests.test_runtime import FETCH, setup


async def advance(hass, freezer, moment):
    freezer.move_to(moment)
    async_fire_time_changed(hass, datetime.fromisoformat(moment))
    await hass.async_block_till_done()


async def test_threshold_timer_then_poll_and_local_ticks_do_not_postpone_requests(
    hass, stop_payload, freezer
):
    freezer.move_to("2026-09-05T03:00:00+00:00")
    stop_payload["lines"][0]["arrival"]["arrivalTime"] = 181
    entry, coordinator, arrival, _ = await setup(hass, stop_payload)
    last_success = coordinator.last_success
    with patch(FETCH, new=AsyncMock(return_value=stop_payload)) as fetch:
        await advance(hass, freezer, "2026-09-05T03:00:01+00:00")
        assert coordinator.update_interval.total_seconds() == 30
        assert coordinator.last_success == last_success
        fetch.assert_not_awaited()
        await advance(hass, freezer, "2026-09-05T03:00:30+00:00")
        fetch.assert_not_awaited()
        await advance(hass, freezer, "2026-09-05T03:00:32+00:00")
        fetch.assert_awaited_once()
    await hass.config_entries.async_unload(entry.entry_id)
    assert coordinator._unsub_local is None
    assert coordinator._unsub_pause is None


async def test_fixed_poll_disabled_actual_timer_expires_and_cleans_up(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T03:00:00+00:00")
    entry, coordinator, arrival, status = await setup(hass, stop_payload)
    # Updating HA's system option removes the scheduled poll on the next scheduling pass.
    hass.config_entries.async_update_entry(entry, pref_disable_polling=True)
    with patch(FETCH, new=AsyncMock(return_value=stop_payload)) as fetch:
        await coordinator.async_refresh()  # explicitly allowed manual fetch
        fetch.reset_mock()
        await advance(hass, freezer, "2026-09-05T03:01:00+00:00")
        assert hass.states.get(arrival).state == "1"
        await advance(hass, freezer, "2026-09-05T03:02:00+00:00")
        assert hass.states.get(status).state == "expired"
        assert hass.states.get(arrival).attributes["next_bus_min"] is None
        fetch.assert_not_awaited()
    await hass.config_entries.async_unload(entry.entry_id)
    assert coordinator._unsub_local is None


async def test_rate_limit_survives_quiet_start_end_and_reload(hass, stop_payload, freezer):
    freezer.move_to("2026-09-05T14:59:00+00:00")
    entry, coordinator, _, status = await setup(hass, stop_payload)
    with patch(FETCH, new=AsyncMock(side_effect=RateLimited(6 * 3600))):
        await coordinator.async_refresh()
    deadline = coordinator.retry_at
    with patch(FETCH, new=AsyncMock(return_value=stop_payload)) as fetch:
        await advance(hass, freezer, "2026-09-05T15:00:00+00:00")
        assert hass.states.get(status).state == "paused"
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        await advance(hass, freezer, "2026-09-05T20:00:00+00:00")
        assert hass.states.get(status).state == "rate_limited"
        assert hass.states.get(status).attributes["retry_at"] == deadline.isoformat()
        fetch.assert_not_awaited()
        await advance(hass, freezer, "2026-09-05T21:00:00+00:00")
        fetch.assert_awaited_once()
        assert hass.states.get(status).state == "live"
    await hass.config_entries.async_unload(entry.entry_id)
