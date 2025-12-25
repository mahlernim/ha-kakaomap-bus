"""DataUpdateCoordinator for HA KakaoMap Bus."""
from __future__ import annotations

import asyncio
from datetime import timedelta, datetime
import logging
import json
import async_timeout
import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN, CONF_STOP_ID, CONF_STOP_NAME, CONF_QUIET_START, CONF_QUIET_END, 
    CONF_SCAN_INTERVAL, DEFAULT_QUIET_START, DEFAULT_QUIET_END, DEFAULT_SCAN_INTERVAL
)

_LOGGER = logging.getLogger(__name__)

API_URL = "https://map.kakao.com/bus/stop.json?busstopid={}"

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

        url = API_URL.format(self.stop_id)

        try:
            async with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as response:
                        response.raise_for_status()
                        text = await response.text()
                        
                        # API returns valid JSON
                        data = json.loads(text)
                        
                        if "lines" not in data:
                            _LOGGER.warning("Missing 'lines' key in API response for stop %s", self.stop_id)
                            return {}
                        
                        # Convert list to dict keyed by bus ID or Name for O(1) lookup
                        # We use Bus Name (route number) as key because IDs can change/be opaque
                        # But wait, same bus number might have duplicates? Usually not per stop.
                        # Using Bus Name (e.g., "126") is safer for the sensor to find its data.
                        
                        bus_dict = {}
                        for line in data["lines"]:
                            name = line.get("name")
                            if name:
                                bus_dict[name] = line
                        
                        return bus_dict

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except json.JSONDecodeError as err:
             raise UpdateFailed(f"Error parsing JSON: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err
