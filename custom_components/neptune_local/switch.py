"""Switch platform for Neptun Local."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up Neptun switches."""
    coordinator: NeptunCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        NeptunMainValveSwitch(coordinator, entry),
        NeptunCleaningModeSwitch(coordinator, entry),
    ]
    async_add_entities(entities, update_before_add=True)


class NeptunBaseSwitch(CoordinatorEntity[NeptunCoordinator], SwitchEntity):
    """Base class for Neptun switches."""
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


class NeptunMainValveSwitch(NeptunBaseSwitch):
    _attr_icon = "mdi:valve"
    
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "main_valve", "Main valve")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get("valve_state_open", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_valve(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_valve(False)


class NeptunCleaningModeSwitch(NeptunBaseSwitch):
    _attr_icon = "mdi:water-pump"
    
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "cleaning_mode", "Cleaning mode")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get("flag_dry", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_cleaning_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_cleaning_mode(False)