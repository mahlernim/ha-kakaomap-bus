"""Sensor for KakaoMap Bus."""
from __future__ import annotations

import logging

from typing import Any
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN, CONF_BUSES, CONF_STOP_ID, CONF_STOP_NAME
from .coordinator import KakaoBusCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator: KakaoBusCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Get selected buses from options (or data during first setup)
    selected_buses = entry.options.get(CONF_BUSES, entry.data.get(CONF_BUSES, []))
    
    entities = []
    for bus_name in selected_buses:
        entities.append(KakaoBusSensor(coordinator, bus_name))

    async_add_entities(entities)


class KakaoBusSensor(CoordinatorEntity, SensorEntity):
    """KakaoBus Sensor class."""

    def __init__(self, coordinator: KakaoBusCoordinator, bus_name: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.bus_name = bus_name
        self.stop_id = coordinator.stop_id
        self.stop_name = coordinator.stop_name
        
        # Entity naming:
        # - unique_id: Used internally for tracking (not visible)
        # - entity_id: Will be generated from device name + entity name
        # - name: Display name in UI
        
        self._attr_has_entity_name = True
        self._attr_name = f"{bus_name}"
        self._attr_unique_id = f"{self.stop_id}_{bus_name}"
        self._attr_native_unit_of_measurement = "min"
        self._attr_icon = "mdi:bus-clock"
        
        # Set a suggested entity_id that is more readable
        # This helps HA generate something like sensor.lotte_castle_126
        self._attr_translation_key = "bus_arrival"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.stop_id)},
            name=self.stop_name,
            manufacturer="KakaoMap",
            model="Bus Stop",
            configuration_url=f"https://map.kakao.com/bus/stop.json?busstopid={self.stop_id}",
            # No suggested_area - prevents the forced area selection dialog
        )

    @property
    def native_value(self) -> int | None:
        """Return the minutes until arrival."""
        if not self.coordinator.data:
            return None
            
        line_data = self.coordinator.data.get(self.bus_name)
        if not line_data:
            return None
        
        # Check "NOVEHICLE" or arrivalTime == 0
        realtime_state = line_data.get("realtimeState", "")
        # The arriving object
        arrival = line_data.get("arrival", {})
        arrival_time = arrival.get("arrivalTime", 0)

        if realtime_state == "NOVEHICLE" or arrival_time == 0:
            # We strictly prevent returning 0 if there is no vehicle
            return None
            
        return round(arrival_time / 60)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # The sensor is "available" in HA terms even if bus is not there, 
        # but the state will be "unavailable" (None) if native_value returns None.
        # However, if API failed completely, super().available is False.
        if not super().available:
            return False
            
        # If logic dictates that "No Bus" = Unavailable entity, we can return False here.
        # But usually "Unknown" state is better for "No Bus".
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes."""
        attrs = {}
        if not self.coordinator.data:
             return attrs

        line_data = self.coordinator.data.get(self.bus_name, {})
        if not line_data:
            return attrs

        arrival = line_data.get("arrival", {})
        
        # Next bus (2nd bus)
        arrival_time_2 = arrival.get("arrivalTime2", 0)
        if arrival_time_2 > 0:
            attrs["next_bus_min"] = round(arrival_time_2 / 60)
        else:
            attrs["next_bus_min"] = None

        attrs["direction"] = arrival.get("direction")
        attrs["stop_name"] = self.coordinator.entry.title # Reuse title which handles Stop Name
        attrs["vehicle_type"] = arrival.get("vehicleType")
        
        return attrs
