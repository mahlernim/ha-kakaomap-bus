"""Stop lookup, route selection, and native Home Assistant options."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from time import monotonic
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
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
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
    build_bus_dict,
    build_bus_labels,
    map_url,
    route_sort_key,
    validate_stop_identity,
)
from .const import (
    CONF_BUSES,
    CONF_POLLING_MODE,
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
    POLLING_ADAPTIVE,
    POLLING_FIXED,
)
from .coordinator import async_get_stop_fetch_lock

FETCH_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError, ValueError, RateLimited)
_AMBIGUOUS_ROUTES = "_ambiguous_routes"


def _error_key(err: Exception) -> str:
    if isinstance(err, InvalidStopID):
        return "invalid_stop_id"
    if isinstance(err, (InvalidResponse, json.JSONDecodeError)):
        return "invalid_response"
    if isinstance(err, RateLimited):
        return "rate_limited"
    return "cannot_connect"


def _recovery_for_entry(hass: HomeAssistant, entry_id: str | None) -> dict[str, Any] | None:
    """Return the per-entry recovery state when a flow edits an existing stop."""
    if entry_id is None:
        return None
    return hass.data.get(f"{DOMAIN}_recovery", {}).get(entry_id)


def _enforce_rate_limit(hass: HomeAssistant, entry_id: str | None) -> None:
    recovery = _recovery_for_entry(hass, entry_id)
    if recovery and recovery.get("reason") == "rate_limited":
        remaining = recovery.get("deadline", 0.0) - monotonic()
        if remaining > 0:
            raise RateLimited(remaining)


def _record_rate_limit(hass: HomeAssistant, entry_id: str | None, delay: float) -> None:
    """Share an options or reconfigure 429 deadline with the coordinator."""
    if entry_id is None:
        return
    try:
        retry_at = dt_util.utcnow() + timedelta(seconds=delay)
    except (OverflowError, ValueError):
        delay = 60
        retry_at = dt_util.utcnow() + timedelta(seconds=delay)
    recovery = hass.data.setdefault(f"{DOMAIN}_recovery", {}).setdefault(
        entry_id, {"failures": 0, "deadline": 0.0, "reason": None, "retry_at": None}
    )
    recovery.update(deadline=monotonic() + delay, reason="rate_limited", retry_at=retry_at)
    coordinator = hass.data.get(DOMAIN, {}).get(entry_id)
    if coordinator is not None:
        coordinator._schedule_refresh()
        coordinator.async_update_listeners()


async def get_stop_info(
    hass: HomeAssistant, stop_id: str, *, entry_id: str | None = None
) -> dict[str, Any]:
    """Fetch once during a form step, preserving typed errors for useful messages."""
    async with async_get_stop_fetch_lock(hass, stop_id):
        _enforce_rate_limit(hass, entry_id)
        try:
            data = await async_fetch_stop_data(async_get_clientsession(hass), stop_id, retries=1)
        except RateLimited as err:
            _record_rate_limit(hass, entry_id, err.retry_after)
            raise
        validate_stop_identity(data, stop_id)
        labels = build_bus_labels(data)
    ambiguous_routes = [
        name for name, line in build_bus_dict(data).items() if line.get("ambiguous")
    ]
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise InvalidResponse("Missing stop name")
    direction = data.get("direction")
    return {
        CONF_STOP_ID: stop_id,
        CONF_STOP_NAME: name.strip(),
        CONF_STOP_DIRECTION: direction if isinstance(direction, str) else "",
        CONF_ROUTE_LABELS: labels,
        _AMBIGUOUS_ROUTES: ambiguous_routes,
    }


def _nickname(value: str) -> str:
    return value.strip()[:80]


def _route_selector(labels: dict[str, str]) -> SelectSelector:
    """Build a searchable, closed list of route choices."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[{"value": name, "label": label} for name, label in labels.items()],
            multiple=True,
            custom_value=False,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _polling_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[POLLING_ADAPTIVE, POLLING_FIXED],
            custom_value=False,
            mode=SelectSelectorMode.LIST,
            translation_key=CONF_POLLING_MODE,
        )
    )


def _interval_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=MIN_SCAN_INTERVAL,
            max=MAX_SCAN_INTERVAL,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="s",
        )
    )


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Add a stop using a share link or ID, then select its routes."""

    VERSION = 1
    MINOR_VERSION = 2

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
                    errors["base"] = (
                        "ambiguous_routes_only"
                        if self._stop[_AMBIGUOUS_ROUTES]
                        else "no_buses_found"
                    )
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
            "direction": self._stop[CONF_STOP_DIRECTION] or "-",
            "map_url": map_url(self._stop[CONF_STOP_ID]),
            "ambiguous_routes": ", ".join(self._stop[_AMBIGUOUS_ROUTES]) or "-",
        }

    async def async_step_select_bus(self, user_input=None):
        labels = self._stop[CONF_ROUTE_LABELS]
        errors = {}
        if user_input is not None:
            self._selection = dict(user_input)
            buses = user_input.get(CONF_BUSES, [])
            polling = user_input.get("polling", {})
            pause = user_input.get("pause", {})
            if not buses:
                errors[CONF_BUSES] = "select_bus"
            elif any(bus not in labels for bus in buses):
                errors[CONF_BUSES] = "invalid_bus"
            polling_mode = polling.get(CONF_POLLING_MODE, POLLING_ADAPTIVE)
            interval = polling.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            if polling_mode not in {POLLING_ADAPTIVE, POLLING_FIXED}:
                errors["base"] = "invalid_polling_mode"
            if (
                isinstance(interval, bool)
                or not isinstance(interval, (int, float))
                or not MIN_SCAN_INTERVAL <= interval <= MAX_SCAN_INTERVAL
                or int(interval) != interval
            ):
                errors["base"] = "invalid_interval"
            try:
                start = cv.time(pause.get(CONF_QUIET_START, DEFAULT_QUIET_START)).isoformat()
                end = cv.time(pause.get(CONF_QUIET_END, DEFAULT_QUIET_END)).isoformat()
            except vol.Invalid:
                errors["base"] = "invalid_time"
            else:
                if pause.get(CONF_QUIET_ENABLED, True) and start == end:
                    errors["base"] = "equal_pause_times"
            if not errors:
                nickname = _nickname(user_input.get(CONF_STOP_NICKNAME, ""))
                return self.async_create_entry(
                    title=f"{nickname or self._stop[CONF_STOP_NAME]} ({self._stop[CONF_STOP_ID]})",
                    data={
                        key: value for key, value in self._stop.items() if key != _AMBIGUOUS_ROUTES
                    },
                    options={
                        CONF_BUSES: buses,
                        CONF_STOP_NICKNAME: nickname,
                        CONF_POLLING_MODE: polling_mode,
                        CONF_SCAN_INTERVAL: int(interval),
                        CONF_QUIET_ENABLED: pause.get(CONF_QUIET_ENABLED, True),
                        CONF_QUIET_START: start,
                        CONF_QUIET_END: end,
                    },
                )
        selected_polling = self._selection.get("polling", {})
        selected_pause = self._selection.get("pause", {})
        return self.async_show_form(
            step_id="select_bus",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BUSES, default=self._selection.get(CONF_BUSES, [])
                    ): _route_selector(labels),
                    vol.Optional(
                        CONF_STOP_NICKNAME, default=self._selection.get(CONF_STOP_NICKNAME, "")
                    ): TextSelector(),
                    vol.Required("polling"): section(
                        vol.Schema(
                            {
                                vol.Required(
                                    CONF_POLLING_MODE,
                                    default=selected_polling.get(
                                        CONF_POLLING_MODE, POLLING_ADAPTIVE
                                    ),
                                ): _polling_selector(),
                                vol.Required(
                                    CONF_SCAN_INTERVAL,
                                    default=selected_polling.get(
                                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                                    ),
                                ): _interval_selector(),
                            }
                        ),
                        {"collapsed": False},
                    ),
                    vol.Required("pause"): section(
                        vol.Schema(
                            {
                                vol.Required(
                                    CONF_QUIET_ENABLED,
                                    default=selected_pause.get(CONF_QUIET_ENABLED, True),
                                ): BooleanSelector(),
                                vol.Required(
                                    CONF_QUIET_START,
                                    default=selected_pause.get(
                                        CONF_QUIET_START, DEFAULT_QUIET_START
                                    ),
                                ): TimeSelector(),
                                vol.Required(
                                    CONF_QUIET_END,
                                    default=selected_pause.get(CONF_QUIET_END, DEFAULT_QUIET_END),
                                ): TimeSelector(),
                            }
                        ),
                        {"collapsed": True},
                    ),
                }
            ),
            errors=errors,
            description_placeholders=self._stop_placeholders(),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler()

    async def async_step_reconfigure(self, user_input=None):
        """Refresh metadata only after the user explicitly submits this form."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            try:
                refreshed = await get_stop_info(
                    self.hass, entry.data[CONF_STOP_ID], entry_id=entry.entry_id
                )
            except FETCH_ERRORS as err:
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=vol.Schema({}),
                    errors={"base": _error_key(err)},
                )
            data_updates = {
                **entry.data,
                CONF_STOP_NAME: refreshed[CONF_STOP_NAME],
                CONF_STOP_DIRECTION: refreshed[CONF_STOP_DIRECTION],
                CONF_ROUTE_LABELS: {
                    **entry.data.get(CONF_ROUTE_LABELS, {}),
                    **refreshed[CONF_ROUTE_LABELS],
                },
            }
            if data_updates == dict(entry.data):
                return self.async_abort(reason="reconfigure_successful")
            return self.async_update_reload_and_abort(
                entry, data_updates=data_updates, reason="reconfigure_successful"
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({}),
            description_placeholders={
                "stop_name": entry.data.get(CONF_STOP_NAME, entry.title),
                "map_url": map_url(entry.data[CONF_STOP_ID]),
            },
        )


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Edit routes and pauses without refetching on every submission."""

    def __init__(self) -> None:
        self._labels: dict[str, str] | None = None
        self._lookup_error: str | None = None
        self._input: dict[str, Any] | None = None
        self._refreshed_stop: dict[str, Any] | None = None

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
            "polling": {
                CONF_POLLING_MODE: values.get(CONF_POLLING_MODE, POLLING_ADAPTIVE),
                CONF_SCAN_INTERVAL: values.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            },
        }

    async def _load_labels(self) -> None:
        entry = self.config_entry
        current = entry.options.get(CONF_BUSES, entry.data.get(CONF_BUSES, []))
        cached = entry.data.get(CONF_ROUTE_LABELS, {})
        self._labels = {bus: cached.get(bus, bus) for bus in current}
        try:
            stop = await get_stop_info(self.hass, entry.data[CONF_STOP_ID], entry_id=entry.entry_id)
        except FETCH_ERRORS as err:
            self._lookup_error = _error_key(err)
        else:
            self._refreshed_stop = stop
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
            polling = user_input.get("polling", defaults["polling"])
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
            polling_mode = polling.get(CONF_POLLING_MODE, POLLING_ADAPTIVE)
            if polling_mode not in {POLLING_ADAPTIVE, POLLING_FIXED}:
                errors["base"] = "invalid_polling_mode"
            interval = polling.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            if (
                isinstance(interval, bool)
                or not isinstance(interval, (int, float))
                or not MIN_SCAN_INTERVAL <= interval <= MAX_SCAN_INTERVAL
                or int(interval) != interval
            ):
                errors["base"] = "invalid_interval"
            if not errors:
                if self._refreshed_stop:
                    data_updates = {
                        **self.config_entry.data,
                        CONF_STOP_NAME: self._refreshed_stop[CONF_STOP_NAME],
                        CONF_STOP_DIRECTION: self._refreshed_stop[CONF_STOP_DIRECTION],
                        CONF_ROUTE_LABELS: {
                            **self.config_entry.data.get(CONF_ROUTE_LABELS, {}),
                            **self._refreshed_stop[CONF_ROUTE_LABELS],
                        },
                    }
                    if data_updates != dict(self.config_entry.data):
                        self.hass.config_entries.async_update_entry(
                            self.config_entry, data=data_updates
                        )
                return self.async_create_entry(
                    title="",
                    data={
                        **self.config_entry.options,
                        CONF_BUSES: buses,
                        CONF_STOP_NICKNAME: _nickname(user_input.get(CONF_STOP_NICKNAME, "")),
                        CONF_QUIET_ENABLED: pause.get(CONF_QUIET_ENABLED, False),
                        CONF_QUIET_START: start,
                        CONF_QUIET_END: end,
                        CONF_POLLING_MODE: polling_mode,
                        CONF_SCAN_INTERVAL: int(interval),
                    },
                )
        values = self._input or defaults
        pause = values.get("pause", defaults["pause"])
        polling = values.get("polling", defaults["polling"])
        if not errors and self._lookup_error:
            errors["base"] = (
                "rate_limited" if self._lookup_error == "rate_limited" else "route_list_unavailable"
            )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BUSES, default=values.get(CONF_BUSES, [])): _route_selector(
                        self._labels
                    ),
                    vol.Optional(
                        CONF_STOP_NICKNAME, default=values.get(CONF_STOP_NICKNAME, "")
                    ): TextSelector(),
                    vol.Required("polling"): section(
                        vol.Schema(
                            {
                                vol.Required(
                                    CONF_POLLING_MODE,
                                    default=polling.get(CONF_POLLING_MODE, POLLING_ADAPTIVE),
                                ): _polling_selector(),
                                vol.Required(
                                    CONF_SCAN_INTERVAL,
                                    default=polling.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                                ): _interval_selector(),
                            }
                        ),
                        {"collapsed": False},
                    ),
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
