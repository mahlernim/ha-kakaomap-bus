"""Coordinate current arrivals and scheduled update pauses."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from time import monotonic

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    InvalidStopID,
    RateLimited,
    arrival_seconds,
    async_fetch_stop_data,
    build_bus_dict,
    describe_api_error,
    validate_stop_identity,
)
from .const import (
    ADAPTIVE_INTERVAL,
    CONF_BUSES,
    CONF_POLLING_MODE,
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
    NEAR_INTERVAL,
    NEAR_SECONDS,
    POLLING_ADAPTIVE,
    POLLING_FIXED,
)

_LOGGER = logging.getLogger(__name__)


def async_get_stop_fetch_lock(hass: HomeAssistant, stop_id: str) -> asyncio.Lock:
    """Return the shared request lock for one physical KakaoMap stop."""
    locks = hass.data.setdefault(f"{DOMAIN}_fetch_locks", {})
    return locks.setdefault(stop_id, asyncio.Lock())


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
        self.loaded_options = dict(entry.options)
        self._fixed_interval = interval
        self._mode = entry.options.get(CONF_POLLING_MODE, POLLING_ADAPTIVE)
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
        self._receipt: float | None = None
        self._unsub_local = None
        self._fetch_lock = async_get_stop_fetch_lock(hass, self.stop_id)
        # Keep retry state across entry reloads and setup retries, without storing arrivals.
        self._recovery = hass.data.setdefault(f"{DOMAIN}_recovery", {}).setdefault(
            entry.entry_id, {"failures": 0, "deadline": 0.0, "reason": None, "retry_at": None}
        )

    @property
    def error_reason(self) -> str | None:
        return self._recovery["reason"]

    @property
    def retry_at(self) -> datetime | None:
        return self._recovery["retry_at"] if self.error_reason == "rate_limited" else None

    def remaining(self, bus_name: str, key: str = "arrivalTime") -> float | None:
        """Use elapsed monotonic time, so wall-clock corrections cannot revive estimates."""
        line = (self.data or {}).get(bus_name, {})
        if line.get("ambiguous") or line.get("realtimeState") == "NOVEHICLE":
            return None
        seconds = arrival_seconds(line.get("arrival", {}).get(key))
        if not seconds or self._receipt is None:
            return None
        return max(0.0, seconds - max(0.0, monotonic() - self._receipt))

    def route_status(self, bus_name: str) -> str:
        if self.paused:
            return "paused"
        if self.error_reason or not self.last_update_success:
            return self.error_reason or "connection_lost"
        if (self.data or {}).get(bus_name, {}).get("ambiguous"):
            return "ambiguous_route"
        seconds = self.remaining(bus_name)
        if seconds == 0:
            return "expired"
        return "live" if seconds is not None else "no_arrival"

    def _poll_interval(self) -> int:
        if self._mode == POLLING_FIXED:
            return self._fixed_interval
        selected = self.entry.options.get(CONF_BUSES, self.entry.data.get(CONF_BUSES, []))
        for name in set(self.async_contexts()).intersection(selected):
            seconds = self.remaining(name)
            if (
                self.route_status(name) == "live"
                and seconds is not None
                and 0 < seconds <= NEAR_SECONDS
            ):
                return NEAR_INTERVAL
        return ADAPTIVE_INTERVAL

    @callback
    def _schedule_refresh(self) -> None:
        """Use one HA poll timer, honoring retry deadlines even after local transitions."""
        self.update_interval = timedelta(seconds=self._poll_interval())
        if self.paused or self._shutdown_requested:
            self._async_unsub_refresh()
            return
        delay = self._recovery["deadline"] - monotonic()
        if delay > 0:
            self._retry_after = delay
        super()._schedule_refresh()

    @callback
    def async_add_listener(self, update_callback, context=None):
        remove = super().async_add_listener(update_callback, context)
        self._schedule_local()
        self._schedule_pause_boundary()

        @callback
        def unsubscribe():
            remove()
            self._schedule_local()
            if not self._listeners and self._unsub_pause:
                self._unsub_pause()
                self._unsub_pause = None

        return unsubscribe

    @callback
    def _schedule_local(self) -> None:
        if self._unsub_local:
            self._unsub_local()
            self._unsub_local = None
        if self._shutdown_requested or not self._listeners or self.paused or self.error_reason:
            return
        delays = []
        for name in set(self.async_contexts()):
            if self.route_status(name) != "live":
                continue
            for key in ("arrivalTime", "arrivalTime2"):
                seconds = self.remaining(name, key)
                if seconds is not None and seconds > 0:
                    # Run just after a half-minute tie to retain Python round semantics.
                    delays.extend([seconds, ((seconds - 30) % 60) + 0.001])
            seconds = self.remaining(name)
            if self._mode == POLLING_ADAPTIVE and seconds > NEAR_SECONDS:
                delays.append(seconds - NEAR_SECONDS)
        if delays:
            self._unsub_local = self.hass.loop.call_later(
                max(0.001, min(delays)), self._local_tick
            ).cancel

    @callback
    def _local_tick(self) -> None:
        self._unsub_local = None
        if self._shutdown_requested:
            return
        previous = self.update_interval
        current = timedelta(seconds=self._poll_interval())
        # Minute-display updates do not reset polling. Only a policy transition does.
        if previous != current and not self.entry.pref_disable_polling:
            self._schedule_refresh()
        self.async_update_listeners()
        self._schedule_local()

    @callback
    def _async_refresh_finished(self) -> None:
        self._schedule_local()
        # HA normally suppresses consecutive failure notifications. Reasons can change.
        if not self.last_update_success:
            self.async_update_listeners()

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
        if self._shutdown_requested:
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
        self.paused = self._quiet_hours_active
        self.paused_until = self._next_pause_boundary(dt_util.now()) if self.paused else None
        self._schedule_pause_boundary()
        self._schedule_local()
        self.async_update_listeners()
        if self.paused:
            self._async_unsub_refresh()
        elif not self.entry.pref_disable_polling:
            self.entry.async_create_background_task(
                self.hass, self.async_refresh(), "KakaoMap pause boundary"
            )

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        if self._unsub_pause:
            self._unsub_pause()
            self._unsub_pause = None
        if self._unsub_local:
            self._unsub_local()
            self._unsub_local = None

    def route_label(self, bus_name: str) -> str:
        return self._route_labels.get(bus_name, bus_name)

    async def _async_update_data(self) -> dict:
        self._schedule_pause_boundary()
        self.paused = self._quiet_hours_active
        self.paused_until = self._next_pause_boundary(dt_util.now()) if self.paused else None
        if self.paused:
            return {}
        async with self._fetch_lock:
            remaining = self._recovery["deadline"] - monotonic()
            if remaining > 0 and (self.error_reason == "rate_limited" or self.last_success is None):
                raise UpdateFailed(
                    "Waiting before retrying KakaoMap " + (self.error_reason or "connection_lost"),
                    retry_after=remaining,
                )
            try:
                payload = await async_fetch_stop_data(self._session, self.stop_id)
                validate_stop_identity(payload, self.stop_id)
                data = build_bus_dict(payload)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, RateLimited) as err:
                if isinstance(err, RateLimited):
                    delay = err.retry_after
                    reason = "rate_limited"
                    try:
                        retry_at = dt_util.utcnow() + timedelta(seconds=delay)
                    except (OverflowError, ValueError):
                        delay = 60
                        retry_at = dt_util.utcnow() + timedelta(seconds=delay)
                    self._recovery["retry_at"] = retry_at
                else:
                    self._recovery["failures"] = min(4, self._recovery["failures"] + 1)
                    delay = min(900, 120 * 2 ** (self._recovery["failures"] - 1))
                    reason = "invalid_stop" if isinstance(err, InvalidStopID) else "connection_lost"
                    self._recovery["retry_at"] = None
                self._recovery.update(deadline=monotonic() + delay, reason=reason)
                raise UpdateFailed(describe_api_error(err), retry_after=delay) from err
            self.last_success = dt_util.utcnow()
            self._receipt = monotonic()
            self._recovery.update(failures=0, deadline=0.0, reason=None, retry_at=None)
            self._persist_metadata(payload, data)
            return data

    @callback
    def _persist_metadata(self, payload: dict, data: dict) -> None:
        for name, line in data.items():
            if not line.get("ambiguous") and (direction := line["arrival"]["direction"]):
                self._route_labels[name] = f"{name} · {direction}"
        updated = {**self.entry.data, CONF_ROUTE_LABELS: dict(self._route_labels)}
        name = payload.get("name")
        if isinstance(name, str) and name.strip():
            updated[CONF_STOP_NAME] = name.strip()
        direction = payload.get("direction")
        if isinstance(direction, str):
            updated["stop_direction"] = direction
        self.stop_name = self.entry.options.get(CONF_STOP_NICKNAME) or updated.get(
            CONF_STOP_NAME, self.stop_id
        )
        if updated != dict(self.entry.data):
            self.hass.config_entries.async_update_entry(
                self.entry, data=updated, title=f"{self.stop_name} ({self.stop_id})"
            )
        registry = dr.async_get(self.hass)
        device = next(
            (
                device
                for device in dr.async_entries_for_config_entry(registry, self.entry.entry_id)
                if (DOMAIN, self.stop_id) in device.identifiers
            ),
            None,
        )
        if device:
            if device.name != self.stop_name:
                registry.async_update_device(device.id, name=self.stop_name)
