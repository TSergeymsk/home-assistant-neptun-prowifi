"""Binary sensor platform for Neptun Local."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo, CONNECTION_NETWORK_MAC

from .const import DOMAIN
from .coordinator import NeptunCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neptun binary sensors."""
    coordinator: NeptunCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = [
        NeptunAlarmBinarySensor(coordinator, entry),
        NeptunLeak1BinarySensor(coordinator, entry),
        NeptunLeak2BinarySensor(coordinator, entry),
        NeptunLeak3BinarySensor(coordinator, entry),
        NeptunLeak4BinarySensor(coordinator, entry),
    ]
    async_add_entities(entities, update_before_add=True)


class NeptunBaseBinarySensor(CoordinatorEntity[NeptunCoordinator], BinarySensorEntity):
    """Base class for Neptun binary sensors."""
    _attr_has_entity_name = True

    def __init__(self, coordinator: NeptunCoordinator, entry: ConfigEntry, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        data = self.coordinator.data or {}
        mac = data.get("mac")

        info = DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Neptun ProW+",
            manufacturer="Neptun",
            model="ProW+",
            sw_version=data.get("version"),
        )
        if mac:
            info["connections"] = {(CONNECTION_NETWORK_MAC, mac)}
            info["serial_number"] = mac
        return info

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success


class NeptunAlarmBinarySensor(NeptunBaseBinarySensor):
    _attr_icon = "mdi:alarm-light"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "alarm", "Alarm")

    @property
    def is_on(self) -> bool:
        status = self.coordinator.data.get("status", 0)
        return bool(status & 0x01)


class NeptunLeak1BinarySensor(NeptunBaseBinarySensor):
    _attr_icon = "mdi:water-alert"
    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "leak1", "Leak line 1")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get("lines", {}).get("line0", {}).get("state") == 1


class NeptunLeak2BinarySensor(NeptunBaseBinarySensor):
    _attr_icon = "mdi:water-alert"
    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "leak2", "Leak line 2")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get("lines", {}).get("line1", {}).get("state") == 1


class NeptunLeak3BinarySensor(NeptunBaseBinarySensor):
    _attr_icon = "mdi:water-alert"
    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "leak3", "Leak line 3")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get("lines", {}).get("line2", {}).get("state") == 1


class NeptunLeak4BinarySensor(NeptunBaseBinarySensor):
    _attr_icon = "mdi:water-alert"
    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "leak4", "Leak line 4")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get("lines", {}).get("line3", {}).get("state") == 1