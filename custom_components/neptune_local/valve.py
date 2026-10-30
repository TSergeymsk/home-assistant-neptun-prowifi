"""Valve platform for Neptun Local."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.valve import (
    ValveEntity,
    ValveEntityFeature,
    ValveDeviceClass,
)
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
    """Set up Neptun valves."""
    coordinator: NeptunCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        NeptunMainValve(coordinator, entry),
    ]
    async_add_entities(entities, update_before_add=True)


class NeptunBaseValve(CoordinatorEntity[NeptunCoordinator], ValveEntity):
    """Base class for Neptun valves."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: NeptunCoordinator, entry: ConfigEntry, key: str, name: str
    ) -> None:
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

        # Единый идентификатор для привязки к одному устройству
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


class NeptunMainValve(NeptunBaseValve):
    """Main water valve."""

    _attr_device_class = ValveDeviceClass.WATER
    _attr_supported_features = ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE

    def __init__(self, coordinator: NeptunCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "main_valve_entity", "Main valve")

    @property
    def is_closed(self) -> bool | None:
        """Return True if the valve is closed."""
        state = self.coordinator.data.get("valve_state_open")
        if state is None:
            return None
        return not state

    async def async_open_valve(self, **kwargs: Any) -> None:
        """Open the valve."""
        await self.coordinator.async_set_valve(True)

    async def async_close_valve(self, **kwargs: Any) -> None:
        """Close the valve."""
        await self.coordinator.async_set_valve(False)