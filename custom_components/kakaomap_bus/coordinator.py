"""Coordinate current arrivals and scheduled update pauses."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import RateLimited, async_fetch_stop_data, build_bus_dict, describe_api_error
from .const import (
    CONF_QUIET_ENABLED,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_ROUTE_LABELS,
    CONF_SCAN_INTERVAL,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    CONF_STOP_NICKNAME,
    DEFAULT_QUIET_END,
    DEFAULT_QUIET_START,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class KakaoBusCoordinator(DataUpdateCoordinator[dict]):
    """Never publish cached arrival times as a successful fetch."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        interval = entry.options.get(
            CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=interval),
        )
        self.entry = entry
        self.stop_id = entry.data[CONF_STOP_ID]
        self.stop_name = entry.options.get(CONF_STOP_NICKNAME) or entry.data.get(
            CONF_STOP_NAME, self.stop_id
        )
        self.last_success: datetime | None = None
        self.paused = False
        self.paused_until: datetime | None = None
        self._session = async_get_clientsession(hass)
        self._unsub_pause = None
        self._route_labels = dict(entry.data.get(CONF_ROUTE_LABELS, {}))

    def _pause_times(self):
        if not self.entry.options.get(CONF_QUIET_ENABLED, True):
            return None
        start = dt_util.parse_time(
            self.entry.options.get(
                CONF_QUIET_START, self.entry.data.get(CONF_QUIET_START, DEFAULT_QUIET_START)
            )
        )
        end = dt_util.parse_time(
            self.entry.options.get(
                CONF_QUIET_END, self.entry.data.get(CONF_QUIET_END, DEFAULT_QUIET_END)
            )
        )
        return (start, end) if start is not None and end is not None and start != end else None

    @property
    def _quiet_hours_active(self) -> bool:
        times = self._pause_times()
        if times is None:
            return False
        start, end = times
        now = dt_util.now().time()
        return start <= now < end if start < end else now >= start or now < end

    def _next_pause_boundary(self, now: datetime) -> datetime | None:
        times = self._pause_times()
        if times is None:
            return None
        candidates = []
        for time in times:
            boundary = now.replace(
                hour=time.hour, minute=time.minute, second=time.second, microsecond=0
            )
            if boundary <= now:
                boundary += timedelta(days=1)
            candidates.append(boundary)
        return min(candidates)

    def _schedule_pause_boundary(self) -> None:
        if self._unsub_pause:
            self._unsub_pause()
            self._unsub_pause = None
        if self._shutdown_requested or self.entry.pref_disable_polling:
            return
        if boundary := self._next_pause_boundary(dt_util.now()):
            self._unsub_pause = async_track_point_in_time(
                self.hass, self._pause_boundary_reached, boundary
            )

    @callback
    def _pause_boundary_reached(self, _now: datetime) -> None:
        self._unsub_pause = None
        if self._shutdown_requested or not any(True for _ in self.async_contexts()):
            return
        self.entry.async_create_background_task(
            self.hass, self.async_refresh(), "KakaoMap pause boundary"
        )

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        if self._unsub_pause:
            self._unsub_pause()
            self._unsub_pause = None

    def route_label(self, bus_name: str) -> str:
        return self._route_labels.get(bus_name, bus_name)

    async def _async_update_data(self) -> dict:
        self._schedule_pause_boundary()
        self.paused = self._quiet_hours_active
        self.paused_until = self._next_pause_boundary(dt_util.now()) if self.paused else None
        if self.paused:
            return {}
        try:
            payload = await async_fetch_stop_data(self._session, self.stop_id)
            data = build_bus_dict(payload)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, RateLimited) as err:
            raise UpdateFailed(
                describe_api_error(err),
                retry_after=err.retry_after if isinstance(err, RateLimited) else None,
            ) from err
        self.last_success = dt_util.utcnow()
        for name, line in data.items():
            if direction := line["arrival"]["direction"]:
                self._route_labels[name] = f"{name} · {direction}"
        return data
