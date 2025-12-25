"""Config flow for Kakaobus integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
import aiohttp
import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import json

from .const import (
    DOMAIN, CONF_STOP_ID, CONF_STOP_NAME, CONF_BUSES, CONF_QUIET_START, CONF_QUIET_END, 
    CONF_SCAN_INTERVAL, DEFAULT_QUIET_START, DEFAULT_QUIET_END, DEFAULT_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL
)
from .coordinator import API_URL

_LOGGER = logging.getLogger(__name__)

async def get_stop_info(stop_id: str) -> tuple[str, dict[str, str]] | None:
    """Get stop name and list of buses. Returns (stop_name, {bus_name: label})."""
    url = API_URL.format(stop_id)
    timeout = aiohttp.ClientTimeout(total=10)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as response:
                if response.status != 200:
                    _LOGGER.error("API returned status %s for stop %s", response.status, stop_id)
                    return None
                text = await response.text()
                data = json.loads(text)
                
                if "lines" not in data:
                    _LOGGER.error("No 'lines' key in API response for stop %s", stop_id)
                    return None
                    
                stop_name = data.get("name", stop_id)
                    
                bus_dict = {}
                for line in data["lines"]:
                    name = line.get("name")
                    direction = line.get("arrival", {}).get("direction", "")
                    if name:
                        label = f"{name}"
                        if direction:
                            label += f" ({direction})"
                        bus_dict[name] = label
                return stop_name, bus_dict
    except aiohttp.ClientError as err:
        _LOGGER.error("Client error fetching stop %s: %s", stop_id, err)
        return None
    except Exception as err:
        _LOGGER.exception("Unexpected error fetching stop %s: %s", stop_id, err)
        return None


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kakaobus."""

    VERSION = 1

    def __init__(self):
        """Initialize."""
        self.stop_id: str | None = None
        self.stop_name: str | None = None
        self.available_buses: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            self.stop_id = user_input[CONF_STOP_ID]
            
            # unique_id check
            await self.async_set_unique_id(self.stop_id)
            self._abort_if_unique_id_configured()

            # validate and fetch buses
            info = await get_stop_info(self.stop_id)
            if info:
                self.stop_name, self.available_buses = info
                return await self.async_step_select_bus()
            else:
                errors["base"] = "invalid_stop_id"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_STOP_ID): str,
            }),
            errors=errors,
        )

    async def async_step_select_bus(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle bus selection step."""
        errors = {}
        
        if user_input is not None:
            # Title: "Stop Name (Stop ID)"
            title = f"{self.stop_name} ({self.stop_id})"
            
            return self.async_create_entry(
                title=title,
                data={
                    CONF_STOP_ID: self.stop_id,
                    CONF_STOP_NAME: self.stop_name,
                    CONF_QUIET_START: DEFAULT_QUIET_START,
                    CONF_QUIET_END: DEFAULT_QUIET_END
                },
                options={
                    CONF_BUSES: user_input[CONF_BUSES],
                    CONF_QUIET_START: DEFAULT_QUIET_START,
                    CONF_QUIET_END: DEFAULT_QUIET_END
                }
            )

        return self.async_show_form(
            step_id="select_bus",
            data_schema=vol.Schema({
                vol.Required(CONF_BUSES, default=list(self.available_buses.keys())): cv.multi_select(self.available_buses),
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    # Note: In newer HA versions, config_entry is a read-only property
    # that is automatically set by the parent class. No __init__ needed.

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        errors = {}
        
        try:
            stop_id = self.config_entry.data.get(CONF_STOP_ID)
            if not stop_id:
                _LOGGER.error("Config entry missing stop_id: %s", self.config_entry.data)
                errors["base"] = "cannot_connect"
                available_buses = {}
            else:
                # 1. Fetch latest "Available" buses
                info = await get_stop_info(stop_id)
                if info:
                    _, available_buses = info
                else:
                    available_buses = {}
                    errors["base"] = "cannot_connect"

            # 2. Get "Currently Selected" buses from Options (fallback to Data if migration happened)
            current_buses = self.config_entry.options.get(CONF_BUSES, self.config_entry.data.get(CONF_BUSES, []))

            # 3. Ensure all 'current' buses are in the 'available' map.
            for bus in current_buses:
                if bus not in available_buses:
                    available_buses[bus] = f"{bus} (Not found/Old)"

            if user_input is not None:
                return self.async_create_entry(title="", data=user_input)

            start_def = self.config_entry.options.get(CONF_QUIET_START, self.config_entry.data.get(CONF_QUIET_START, DEFAULT_QUIET_START))
            end_def = self.config_entry.options.get(CONF_QUIET_END, self.config_entry.data.get(CONF_QUIET_END, DEFAULT_QUIET_END))
            interval_def = self.config_entry.options.get(CONF_SCAN_INTERVAL, self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({
                    vol.Optional(CONF_SCAN_INTERVAL, default=interval_def): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                    ),
                    vol.Optional(CONF_QUIET_START, default=start_def): str,
                    vol.Optional(CONF_QUIET_END, default=end_def): str,
                    vol.Required(CONF_BUSES, default=current_buses): cv.multi_select(available_buses),
                }),
                errors=errors
            )
        except Exception as err:
            _LOGGER.exception("Error in options flow: %s", err)
            raise
