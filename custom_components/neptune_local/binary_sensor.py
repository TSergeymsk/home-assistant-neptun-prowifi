"""Binary sensor platform for Neptun Local."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import NeptunCoordinator
from .entity import NeptunEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neptun binary sensors from a config entry."""
    coordinator: NeptunCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        NeptunAlarmSensor(coordinator),
        NeptunLeakSensor(coordinator, "line0"),
        NeptunLeakSensor(coordinator, "line1"),
        NeptunLeakSensor(coordinator, "line2"),
        NeptunLeakSensor(coordinator, "line3"),
    ]

    # Add leak sensors for wireless lines
    if coordinator.data:
        for line_id in coordinator.data.get("lines", {}):
            if line_id.startswith("line") and line_id not in {"line0", "line1", "line2", "line3"}:
                entities.append(NeptunLeakSensor(coordinator, line_id))

    async_add_entities(entities)


class NeptunAlarmSensor(NeptunEntity, BinarySensorEntity):
    """Overall alarm sensor."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_name = "Alarm"

    def __init__(self, coordinator: NeptunCoordinator) -> None:
        super().__init__(coordinator, "alarm")

    @property
    def is_on(self) -> bool:
        """Return true if there is an alarm."""
        if self.coordinator.data is None:
            return False
        status = self.coordinator.data.get("status", 0)
        return bool(status & 0x01)  # ALARM bit[reference:14]


class NeptunLeakSensor(NeptunEntity, BinarySensorEntity):
    """Leak sensor for a specific line."""

    _attr_device_class = BinarySensorDeviceClass.MOISTURE

    def __init__(self, coordinator: NeptunCoordinator, line_id: str) -> None:
        super().__init__(coordinator, f"{line_id}_leak")
        self._line_id = line_id
        line_name = coordinator.data.get("lines", {}).get(line_id, {}).get("name", line_id) if coordinator.data else line_id
        self._attr_name = f"{line_name} leak"

    @property
    def is_on(self) -> bool:
        """Return true if the line reports a leak."""
        if self.coordinator.data is None:
            return False
        line = self.coordinator.data.get("lines", {}).get(self._line_id, {})
        # For wired sensors, state is a bitmask; for wireless, state byte directly indicates leak
        state = line.get("state", 0)
        return bool(state & 0x01) if line.get("wire") else bool(state)