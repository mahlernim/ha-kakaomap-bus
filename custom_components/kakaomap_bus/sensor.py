"""Numeric arrivals and localized status sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .api import map_url
from .const import ARRIVAL_STATUSES, CONF_BUSES, DOMAIN
from .coordinator import KakaoBusCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    buses = entry.options.get(CONF_BUSES, entry.data.get(CONF_BUSES, []))
    async_add_entities(
        [
            entity(coordinator, name)
            for name in buses
            for entity in (KakaoBusSensor, KakaoBusStatusSensor)
        ]
    )


class KakaoBusEntity(CoordinatorEntity[KakaoBusCoordinator], SensorEntity):
    """Shared stop identity and freshness metadata."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: KakaoBusCoordinator, bus_name: str) -> None:
        super().__init__(coordinator, context=bus_name)
        self.bus_name = bus_name
        self.stop_id = coordinator.stop_id

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.stop_id)},
            name=self.coordinator.stop_name,
            manufacturer="KakaoMap",
            model="Bus Stop",
            configuration_url=map_url(self.stop_id),
        )

    @property
    def _line(self) -> dict:
        return (self.coordinator.data or {}).get(self.bus_name, {})

    @property
    def _arrival(self) -> dict:
        arrival = self._line.get("arrival")
        return arrival if isinstance(arrival, dict) else {}

    @property
    def _seconds(self) -> int | float | None:
        if self.arrival_status != "live":
            return None
        return self.coordinator.remaining(self.bus_name)

    @property
    def arrival_status(self) -> str:
        return self.coordinator.route_status(self.bus_name)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        coordinator = self.coordinator
        return {
            "arrival_status": self.arrival_status,
            "last_success": coordinator.last_success.isoformat()
            if coordinator.last_success
            else None,
            "paused_until": coordinator.paused_until.isoformat()
            if coordinator.paused_until
            else None,
            "direction": self._arrival.get("direction"),
            "stop_name": coordinator.stop_name,
            "retry_at": coordinator.retry_at.isoformat() if coordinator.retry_at else None,
        }


class KakaoBusSensor(KakaoBusEntity):
    """Minutes until arrival; keep all existing unique IDs."""

    _attr_native_unit_of_measurement = "min"
    _attr_icon = "mdi:bus-clock"

    def __init__(self, coordinator: KakaoBusCoordinator, bus_name: str) -> None:
        super().__init__(coordinator, bus_name)
        self._attr_unique_id = f"kakaobus_{self.stop_id}_{bus_name}"

    @property
    def name(self) -> str:
        return self.coordinator.route_label(self.bus_name)

    @property
    def suggested_object_id(self) -> str:
        return slugify(f"kakaobus_{self.stop_id}_{self.bus_name}")

    @property
    def native_value(self) -> int | None:
        return round(self._seconds / 60) if self._seconds is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = super().extra_state_attributes
        seconds = self.coordinator.remaining(self.bus_name, "arrivalTime2")
        attrs["next_bus_min"] = (
            round(seconds / 60) if seconds and self.arrival_status == "live" else None
        )
        attrs["vehicle_type"] = self._arrival.get("vehicleType")
        return attrs


class KakaoBusStatusSensor(KakaoBusEntity):
    """Explain missing arrivals, including when the API is unreachable."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ARRIVAL_STATUSES
    _attr_translation_key = "arrival_status"
    _attr_icon = "mdi:bus-alert"

    def __init__(self, coordinator: KakaoBusCoordinator, bus_name: str) -> None:
        super().__init__(coordinator, bus_name)
        self._attr_unique_id = f"kakaobus_status_{self.stop_id}_{bus_name}"
        self._attr_translation_placeholders = {"route": coordinator.route_label(bus_name)}

    @callback
    def _handle_coordinator_update(self) -> None:
        placeholders = {"route": self.coordinator.route_label(self.bus_name)}
        if self._attr_translation_placeholders != placeholders:
            self._attr_translation_placeholders = placeholders
            self.__dict__.pop("name", None)
        super()._handle_coordinator_update()

    @property
    def suggested_object_id(self) -> str:
        return slugify(f"kakaobus_status_{self.stop_id}_{self.bus_name}")

    @property
    def available(self) -> bool:
        # This entity reports connectivity, so an API outage is a valid state.
        return True

    @property
    def native_value(self) -> str:
        return self.arrival_status
