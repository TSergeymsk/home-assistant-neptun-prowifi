"""Switch platform for Neptun Local."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
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
    """Set up Neptun switches."""
    coordinator: NeptunCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NeptunCleaningSwitch(coordinator)])


class NeptunCleaningSwitch(NeptunEntity, SwitchEntity):
    """Switch to enable/disable cleaning mode."""

    _attr_name = "Cleaning mode"
    _attr_icon = "mdi:water-off"

    def __init__(self, coordinator: NeptunCoordinator) -> None:
        super().__init__(coordinator, "cleaning_mode")

    @property
    def is_on(self) -> bool | None:
        """Return true if cleaning mode is enabled."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("flag_dry", False)

    async def async_turn_on(self, **kwargs) -> None:
        """Enable cleaning mode."""
        await self.coordinator.async_set_cleaning_mode(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable cleaning mode."""
        await self.coordinator.async_set_cleaning_mode(False)