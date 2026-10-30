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

    entities = [NeptunAlarmSensor(coordinator)]

    if coordinator.data:
        for line_id in coordinator.data.get("lines", {}):
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
        return bool(status & 0x01)  # ALARM bit


class NeptunLeakSensor(NeptunEntity, BinarySensorEntity):
    """Leak sensor for a specific line."""

    _attr_device_class = BinarySensorDeviceClass.MOISTURE

    def __init__(self, coordinator: NeptunCoordinator, line_id: str) -> None:
        super().__init__(coordinator, f"{line_id}_leak")
        self._line_id = line_id
        
        # Делаем имена красивее: line0 -> Leak line 1, line4 -> Leak line 5
        display_num = line_id.replace("line", "")
        try:
            display_num = str(int(display_num) + 1)
        except ValueError:
            pass
        self._attr_name = f"Leak line {display_num}"

    @property
    def is_on(self) -> bool:
        """Return true if the line reports a leak."""
        if self.coordinator.data is None:
            return False
        line = self.coordinator.data.get("lines", {}).get(self._line_id, {})
        state = line.get("state", 0)
        
        # Для проводных датчиков (wire=True) бит 0x01 означает протечку.
        # Для беспроводных (wire=False) ненулевое состояние означает протечку.
        if line.get("wire"):
            return bool(state & 0x01)
        return bool(state)