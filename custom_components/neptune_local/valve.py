"""Valve platform for Neptun Local."""

from __future__ import annotations

from homeassistant.components.valve import (
    ValveEntity,
    ValveEntityFeature,
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
    """Set up the Neptun valve."""
    coordinator: NeptunCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NeptunValve(coordinator)])


class NeptunValve(NeptunEntity, ValveEntity):
    """Representation of the Neptun main valve."""

    _attr_name = "Main valve"
    _attr_supported_features = ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE
    _attr_reports_position = False

    def __init__(self, coordinator: NeptunCoordinator) -> None:
        super().__init__(coordinator, "main_valve")

    @property
    def is_closed(self) -> bool | None:
        """Return if the valve is closed."""
        if self.coordinator.data is None:
            return None
        return not self.coordinator.data.get("valve_state_open", False)

    async def async_open_valve(self) -> None:
        """Open the valve."""
        await self.coordinator.async_set_valve(True)

    async def async_close_valve(self) -> None:
        """Close the valve."""
        await self.coordinator.async_set_valve(False)