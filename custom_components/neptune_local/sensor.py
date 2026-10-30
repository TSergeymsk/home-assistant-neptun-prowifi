"""Sensor platform for Neptun Local integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
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
    """Set up Neptun sensors."""
    coordinator: NeptunCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []

    # Основные сенсоры системы
    entities.append(NeptunStatusSensor(coordinator, entry))
    entities.append(NeptunValveSensor(coordinator, entry))
    entities.append(NeptunSensorCountSensor(coordinator, entry))
    entities.append(NeptunRelayCountSensor(coordinator, entry))

    # Сенсоры линий (счётчики и беспроводные датчики)
    if coordinator.data:
        for line_id, line_data in coordinator.data.get("lines", {}).items():
            if line_data.get("type") == "counter":
                entities.append(NeptunCounterSensor(coordinator, entry, line_id))
            if line_data.get("wire") is False:  # беспроводной датчик
                entities.append(NeptunSignalSensor(coordinator, entry, line_id))
                entities.append(NeptunBatterySensor(coordinator, entry, line_id))

    async_add_entities(entities, update_before_add=True)


class NeptunBaseSensor(CoordinatorEntity[NeptunCoordinator], SensorEntity):
    """Base class for Neptun sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NeptunCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
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

        # Всегда используем entry_id для identifiers (стабильная привязка)
        identifiers = {(DOMAIN, self._entry.entry_id)}
        
        # MAC-адрес добавляем в connections (если он есть)
        connections = set()
        if mac:
            connections.add((CONNECTION_NETWORK_MAC, mac))

        info = DeviceInfo(
            identifiers=identifiers,
            connections=connections,
            name="Neptun ProW+",           # Жестко заданное имя
            manufacturer="Neptun",
            model="ProW+",                 # Жестко заданная модель
            sw_version=data.get("version"),
        )
        if mac:
            info["serial_number"] = mac    # Серийный номер = MAC
        return info

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success


class NeptunStatusSensor(NeptunBaseSensor):
    """Overall system status sensor."""

    _attr_icon = "mdi:shield-check"

    def __init__(self, coordinator: NeptunCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "status", "Status")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.get("status_name")


class NeptunValveSensor(NeptunBaseSensor):
    """Main valve state sensor."""

    _attr_icon = "mdi:valve"

    def __init__(self, coordinator: NeptunCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "valve_state", "Valve state")

    @property
    def native_value(self) -> str | None:
        return "open" if self.coordinator.data.get("valve_state_open") else "closed"


class NeptunSensorCountSensor(NeptunBaseSensor):
    """Wireless sensor count."""

    _attr_icon = "mdi:access-point"
    _attr_native_unit_of_measurement = "pcs"

    def __init__(self, coordinator: NeptunCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "sensor_count", "Wireless sensors")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("sensor_count")


class NeptunRelayCountSensor(NeptunBaseSensor):
    """Relay count."""

    _attr_icon = "mdi:electric-switch"
    _attr_native_unit_of_measurement = "pcs"

    def __init__(self, coordinator: NeptunCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "relay_count", "Relays")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("relay_count")


class NeptunCounterSensor(NeptunBaseSensor):
    """Counter value for a wired line."""

    _attr_icon = "mdi:counter"
    _attr_state_class = SensorDeviceClass.WATER
    _attr_native_unit_of_measurement = "m³"

    def __init__(
        self, coordinator: NeptunCoordinator, entry: ConfigEntry, line_id: str
    ) -> None:
        super().__init__(
            coordinator, entry, f"{line_id}_value", f"{line_id.capitalize()} counter"
        )
        self._line_id = line_id

    @property
    def native_value(self) -> int | None:
        line = self.coordinator.data.get("lines", {}).get(self._line_id, {})
        return line.get("value")


class NeptunSignalSensor(NeptunBaseSensor):
    """Signal level for a wireless sensor."""

    _attr_icon = "mdi:signal"
    _attr_native_unit_of_measurement = "dB"

    def __init__(
        self, coordinator: NeptunCoordinator, entry: ConfigEntry, line_id: str
    ) -> None:
        super().__init__(
            coordinator, entry, f"{line_id}_signal", f"{line_id.capitalize()} signal"
        )
        self._line_id = line_id

    @property
    def native_value(self) -> int | None:
        line = self.coordinator.data.get("lines", {}).get(self._line_id, {})
        return line.get("signal")


class NeptunBatterySensor(NeptunBaseSensor):
    """Battery level for a wireless sensor."""

    _attr_icon = "mdi:battery"
    _attr_native_unit_of_measurement = "%"
    _attr_device_class = SensorDeviceClass.BATTERY

    def __init__(
        self, coordinator: NeptunCoordinator, entry: ConfigEntry, line_id: str
    ) -> None:
        super().__init__(
            coordinator, entry, f"{line_id}_battery", f"{line_id.capitalize()} battery"
        )
        self._line_id = line_id

    @property
    def native_value(self) -> int | None:
        line = self.coordinator.data.get("lines", {}).get(self._line_id, {})
        return line.get("battery")