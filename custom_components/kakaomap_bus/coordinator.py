"""DataUpdateCoordinator for HA KakaoMap Bus."""
from __future__ import annotations

import asyncio
from datetime import timedelta, datetime
import logging
import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN, CONF_STOP_ID, CONF_STOP_NAME, CONF_QUIET_START, CONF_QUIET_END, 
    CONF_SCAN_INTERVAL, DEFAULT_QUIET_START, DEFAULT_QUIET_END, DEFAULT_SCAN_INTERVAL
)
from .api import async_fetch_stop_data, build_bus_dict, describe_api_error

_LOGGER = logging.getLogger(__name__)

class KakaoBusCoordinator(DataUpdateCoordinator):
    """Class to manage fetching KakaoMap Bus data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        # Get scan interval from options, fallback to data, fallback to default
        scan_interval = entry.options.get(
            CONF_SCAN_INTERVAL, 
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.entry = entry
        self.stop_id = entry.data[CONF_STOP_ID]
        self.stop_name = entry.data.get(CONF_STOP_NAME, self.stop_id)
        self._session = async_get_clientsession(hass)

    @property
    def _quiet_hours_active(self) -> bool:
        """Check if we are currently in quiet hours."""
        
        # Get config or defaults
        start_str = self.entry.options.get(CONF_QUIET_START, self.entry.data.get(CONF_QUIET_START, DEFAULT_QUIET_START))
        end_str = self.entry.options.get(CONF_QUIET_END, self.entry.data.get(CONF_QUIET_END, DEFAULT_QUIET_END))

        now = dt_util.now()
        
        try:
            # Parse times (format HH:MM:SS or HH:MM)
            start_time = datetime.strptime(start_str, "%H:%M:%S").time()
        except ValueError:
            try:
                start_time = datetime.strptime(start_str, "%H:%M").time()
            except ValueError:
                return False # Fail safe

        try:
            end_time = datetime.strptime(end_str, "%H:%M:%S").time()
        except ValueError:
            try:
                end_time = datetime.strptime(end_str, "%H:%M").time()
            except ValueError:
                return False

        current_time = now.time()

        if start_time < end_time:
            return start_time <= current_time <= end_time
        else: # Crosses midnight
            return current_time >= start_time or current_time <= end_time

    async def _async_update_data(self):
        """Fetch data from API."""
        if self._quiet_hours_active:
            _LOGGER.debug("Quiet hours active, skipping update for %s", self.stop_id)
            # Return existing data if available, or empty dict to avoid errors
            return self.data if self.data else {}

        try:
            data = await async_fetch_stop_data(self._session, self.stop_id)
            return build_bus_dict(data)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise UpdateFailed(describe_api_error(err)) from err
        except Exception as err:
            raise UpdateFailed(describe_api_error(err)) from err
