"""Config flow for Kakaobus integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
import aiohttp
import async_timeout
import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import json

from .const import DOMAIN, CONF_STOP_ID, CONF_BUSES, CONF_QUIET_START, CONF_QUIET_END, DEFAULT_QUIET_START, DEFAULT_QUIET_END
from .coordinator import API_URL

_LOGGER = logging.getLogger(__name__)

async def get_buses_at_stop(stop_id: str) -> dict[str, str] | None:
    """Get list of buses at stop. Returns dict {bus_name: label}."""
    url = API_URL.format(stop_id)
    try:
        async with async_timeout.timeout(10):
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as response:
                    if response.status != 200:
                         return None
                    text = await response.text()
                    data = json.loads(text)
                    
                    if "lines" not in data:
                        return None
                        
                    # Build dict of {bus_name: Label}
                    # Example Label: "126 (To Sujeong)"
                    bus_dict = {}
                    for line in data["lines"]:
                        name = line.get("name")
                        direction = line.get("arrival", {}).get("direction", "")
                        if name:
                            label = f"{name}"
                            if direction:
                                label += f" ({direction})"
                            bus_dict[name] = label
                    return bus_dict
    except Exception:
        return None


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kakaobus."""

    VERSION = 1

    def __init__(self):
        """Initialize."""
        self.stop_id: str | None = None
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
            buses = await get_buses_at_stop(self.stop_id)
            if buses:
                self.available_buses = buses
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
            # Create Entry
            return self.async_create_entry(
                title=f"Bus Stop {self.stop_id}",
                data={
                    CONF_STOP_ID: self.stop_id,
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
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        errors = {}
        
        # We need to re-fetch buses in case new routes were added to the stop
        stop_id = self.config_entry.data[CONF_STOP_ID]
        available_buses = await get_buses_at_stop(stop_id)
        
        if not available_buses:
             # Fallback to existing selected buses if API fails
             current_buses = self.config_entry.options.get(CONF_BUSES, [])
             available_buses = {b: b for b in current_buses}
             errors["base"] = "cannot_connect"

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Defaults
        current_buses = self.config_entry.options.get(CONF_BUSES, [])
        # Filter current buses to only those that exist in available (or keep them?)
        # Better to keep them in case temporary API glitch
        
        # Merge dicts to ensure we show labels for old buses if still valid
        
        start_def = self.config_entry.options.get(CONF_QUIET_START, DEFAULT_QUIET_START)
        end_def = self.config_entry.options.get(CONF_QUIET_END, DEFAULT_QUIET_END)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_QUIET_START, default=start_def): str,
                vol.Optional(CONF_QUIET_END, default=end_def): str,
                vol.Required(CONF_BUSES, default=current_buses): cv.multi_select(available_buses),
            }),
            errors=errors
        )
