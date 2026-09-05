"""Stop lookup, route selection, and native Home Assistant options."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TimeSelector,
)
from homeassistant.util import dt as dt_util

from .api import (
    InvalidResponse,
    InvalidStopID,
    RateLimited,
    async_fetch_stop_data,
    async_resolve_stop_id,
    build_bus_labels,
    map_url,
    route_sort_key,
)
from .const import (
    CONF_BUSES,
    CONF_QUIET_ENABLED,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_ROUTE_LABELS,
    CONF_SCAN_INTERVAL,
    CONF_STOP_DIRECTION,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    CONF_STOP_NICKNAME,
    DEFAULT_QUIET_END,
    DEFAULT_QUIET_START,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

FETCH_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError, ValueError, RateLimited)


def _error_key(err: Exception) -> str:
    if isinstance(err, InvalidStopID):
        return "invalid_stop_id"
    if isinstance(err, (InvalidResponse, json.JSONDecodeError)):
        return "invalid_response"
    if isinstance(err, RateLimited):
        return "rate_limited"
    return "cannot_connect"


async def get_stop_info(hass: HomeAssistant, stop_id: str) -> dict[str, Any]:
    """Fetch once during a form step, preserving typed errors for useful messages."""
    data = await async_fetch_stop_data(async_get_clientsession(hass), stop_id, retries=1)
    labels = build_bus_labels(data)
    if data.get("id") != stop_id:
        raise InvalidStopID
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise InvalidResponse("Missing stop name")
    direction = data.get("direction")
    return {
        CONF_STOP_ID: stop_id,
        CONF_STOP_NAME: name.strip(),
        CONF_STOP_DIRECTION: direction if isinstance(direction, str) else "",
        CONF_ROUTE_LABELS: labels,
    }


def _nickname(value: str) -> str:
    return value.strip()[:80]


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Add a stop using a share link or ID, then confirm the routes."""

    VERSION = 1

    def __init__(self) -> None:
        self._input = ""
        self._stop: dict[str, Any] = {}
        self._selection: dict[str, Any] = {}

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            self._input = user_input[CONF_STOP_ID]
            try:
                stop_id = await async_resolve_stop_id(
                    async_get_clientsession(self.hass), self._input
                )
                await self.async_set_unique_id(stop_id)
                self._abort_if_unique_id_configured()
                self._stop = await get_stop_info(self.hass, stop_id)
                if not self._stop[CONF_ROUTE_LABELS]:
                    errors["base"] = "no_buses_found"
                else:
                    return await self.async_step_select_bus()
            except FETCH_ERRORS as err:
                errors["base"] = _error_key(err)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STOP_ID, default=self._input): TextSelector(),
                }
            ),
            errors=errors,
        )

    def _stop_placeholders(self) -> dict[str, str]:
        return {
            "stop_name": self._stop[CONF_STOP_NAME],
            "direction": self._stop[CONF_STOP_DIRECTION] or "—",
            "map_url": map_url(self._stop[CONF_STOP_ID]),
        }

    async def async_step_select_bus(self, user_input=None):
        labels = self._stop[CONF_ROUTE_LABELS]
        errors = {}
        if user_input is not None:
            self._selection = dict(user_input)
            buses = user_input.get(CONF_BUSES, [])
            if not buses:
                errors[CONF_BUSES] = "select_bus"
            elif any(bus not in labels for bus in buses):
                errors[CONF_BUSES] = "invalid_bus"
            else:
                self._selection[CONF_STOP_NICKNAME] = _nickname(
                    user_input.get(CONF_STOP_NICKNAME, "")
                )
                return await self.async_step_confirm()
        return self.async_show_form(
            step_id="select_bus",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BUSES, default=self._selection.get(CONF_BUSES, [])
                    ): cv.multi_select(labels),
                    vol.Optional(
                        CONF_STOP_NICKNAME, default=self._selection.get(CONF_STOP_NICKNAME, "")
                    ): TextSelector(),
                }
            ),
            errors=errors,
            description_placeholders=self._stop_placeholders(),
        )

    async def async_step_confirm(self, user_input=None):
        if user_input is not None:
            nickname = self._selection[CONF_STOP_NICKNAME]
            return self.async_create_entry(
                title=f"{nickname or self._stop[CONF_STOP_NAME]} ({self._stop[CONF_STOP_ID]})",
                data=self._stop,
                options={
                    **self._selection,
                    CONF_QUIET_ENABLED: True,
                    CONF_QUIET_START: DEFAULT_QUIET_START,
                    CONF_QUIET_END: DEFAULT_QUIET_END,
                    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                },
            )
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                **self._stop_placeholders(),
                "display_name": self._selection[CONF_STOP_NICKNAME] or self._stop[CONF_STOP_NAME],
                "routes": ", ".join(
                    self._stop[CONF_ROUTE_LABELS][bus] for bus in self._selection[CONF_BUSES]
                ),
                "interval": str(DEFAULT_SCAN_INTERVAL),
                "pause_start": DEFAULT_QUIET_START[:5],
                "pause_end": DEFAULT_QUIET_END[:5],
                "timezone": str(self.hass.config.time_zone),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Edit routes and pauses without refetching on every submission."""

    def __init__(self) -> None:
        self._labels: dict[str, str] | None = None
        self._lookup_error: str | None = None
        self._input: dict[str, Any] | None = None

    def _defaults(self) -> dict[str, Any]:
        entry = self.config_entry
        values = {**entry.data, **entry.options}
        start = dt_util.parse_time(values.get(CONF_QUIET_START, DEFAULT_QUIET_START))
        end = dt_util.parse_time(values.get(CONF_QUIET_END, DEFAULT_QUIET_END))
        return {
            CONF_BUSES: list(values.get(CONF_BUSES, [])),
            CONF_STOP_NICKNAME: values.get(CONF_STOP_NICKNAME, ""),
            "pause": {
                CONF_QUIET_ENABLED: values.get(
                    CONF_QUIET_ENABLED, bool(start and end and start != end)
                ),
                CONF_QUIET_START: start.isoformat() if start else DEFAULT_QUIET_START,
                CONF_QUIET_END: end.isoformat() if end else DEFAULT_QUIET_END,
            },
            "advanced": {CONF_SCAN_INTERVAL: values.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)},
        }

    async def _load_labels(self) -> None:
        entry = self.config_entry
        current = entry.options.get(CONF_BUSES, entry.data.get(CONF_BUSES, []))
        cached = entry.data.get(CONF_ROUTE_LABELS, {})
        self._labels = {bus: cached.get(bus, bus) for bus in current}
        try:
            stop = await get_stop_info(self.hass, entry.data[CONF_STOP_ID])
        except FETCH_ERRORS as err:
            self._lookup_error = _error_key(err)
        else:
            self._labels = {**self._labels, **stop[CONF_ROUTE_LABELS]}
        self._labels = dict(sorted(self._labels.items(), key=lambda item: route_sort_key(item[0])))

    async def async_step_init(self, user_input=None):
        if self._labels is None:
            await self._load_labels()
        defaults = self._defaults()
        errors = {}
        if user_input is not None:
            self._input = user_input
            buses = user_input.get(CONF_BUSES, [])
            pause = user_input.get("pause", defaults["pause"])
            advanced = user_input.get("advanced", defaults["advanced"])
            if any(bus not in self._labels for bus in buses):
                errors[CONF_BUSES] = "invalid_bus"
            try:
                start = cv.time(pause.get(CONF_QUIET_START, DEFAULT_QUIET_START)).isoformat()
                end = cv.time(pause.get(CONF_QUIET_END, DEFAULT_QUIET_END)).isoformat()
            except vol.Invalid:
                errors["base"] = "invalid_time"
            else:
                if pause.get(CONF_QUIET_ENABLED, False) and start == end:
                    errors["base"] = "equal_pause_times"
            interval = advanced.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            if (
                isinstance(interval, bool)
                or not isinstance(interval, (int, float))
                or not MIN_SCAN_INTERVAL <= interval <= MAX_SCAN_INTERVAL
                or int(interval) != interval
            ):
                errors["base"] = "invalid_interval"
            if not errors:
                return self.async_create_entry(
                    title="",
                    data={
                        **self.config_entry.options,
                        CONF_BUSES: buses,
                        CONF_STOP_NICKNAME: _nickname(user_input.get(CONF_STOP_NICKNAME, "")),
                        CONF_QUIET_ENABLED: pause.get(CONF_QUIET_ENABLED, False),
                        CONF_QUIET_START: start,
                        CONF_QUIET_END: end,
                        CONF_SCAN_INTERVAL: int(interval),
                    },
                )
        values = self._input or defaults
        pause = values.get("pause", defaults["pause"])
        advanced = values.get("advanced", defaults["advanced"])
        if not errors and self._lookup_error:
            errors["base"] = "route_list_unavailable"
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BUSES, default=values.get(CONF_BUSES, [])): cv.multi_select(
                        self._labels
                    ),
                    vol.Optional(
                        CONF_STOP_NICKNAME, default=values.get(CONF_STOP_NICKNAME, "")
                    ): TextSelector(),
                    vol.Required("pause"): section(
                        vol.Schema(
                            {
                                vol.Required(
                                    CONF_QUIET_ENABLED, default=pause.get(CONF_QUIET_ENABLED, False)
                                ): BooleanSelector(),
                                vol.Required(
                                    CONF_QUIET_START,
                                    default=pause.get(CONF_QUIET_START, DEFAULT_QUIET_START),
                                ): TimeSelector(),
                                vol.Required(
                                    CONF_QUIET_END,
                                    default=pause.get(CONF_QUIET_END, DEFAULT_QUIET_END),
                                ): TimeSelector(),
                            }
                        ),
                        {"collapsed": False},
                    ),
                    vol.Required("advanced"): section(
                        vol.Schema(
                            {
                                vol.Required(
                                    CONF_SCAN_INTERVAL,
                                    default=advanced.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                                ): NumberSelector(
                                    NumberSelectorConfig(
                                        min=MIN_SCAN_INTERVAL,
                                        max=MAX_SCAN_INTERVAL,
                                        step=1,
                                        mode=NumberSelectorMode.BOX,
                                        unit_of_measurement="s",
                                    )
                                ),
                            }
                        ),
                        {"collapsed": True},
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "stop_name": self.config_entry.data.get(CONF_STOP_NAME, self.config_entry.title),
                "map_url": map_url(self.config_entry.data[CONF_STOP_ID]),
                "timezone": str(self.hass.config.time_zone),
            },
        )
