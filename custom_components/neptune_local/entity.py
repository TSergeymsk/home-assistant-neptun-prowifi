"""Base entity for Neptun Local."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NeptunCoordinator


class NeptunEntity(CoordinatorEntity[NeptunCoordinator]):
    """Base class for all Neptun entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NeptunCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.host}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.host)},
            name="Neptun ProW+",
            manufacturer="Neptun",
            model="ProW+",
            configuration_url=f"http://{coordinator.host}",
        )

    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        return super().available and self.coordinator.data is not None