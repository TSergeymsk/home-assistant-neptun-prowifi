"""Sensor platform for Neptun Local."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import NeptunCoordinator
from .entity import NeptunEntity


@dataclass(frozen=True, kw_only=True)
class NeptunSensorDescription(SensorEntityDescription):
    """Describe a Neptun sensor."""
    value_fn: Callable[[dict], float | int | str | None]


SENSOR_TYPES: tuple[NeptunSensorDescription, ...] = (
    NeptunSensorDescription(
        key="status",
        name="Status",
        icon="mdi:water-alert",
        value_fn=lambda d: d.get("status_name"),
    ),
    NeptunSensorDescription(
        key="valve_state",
        name="Valve state",
        icon="mdi:valve",
        value_fn=lambda d: "open" if d.get("valve_state_open") else "closed",
    ),
    NeptunSensorDescription(
        key="sensor_count",
        name="Wireless sensor count",
        icon="mdi:access-point",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("sensor_count"),
    ),
    NeptunSensorDescription(
        key="relay_count",
        name="Relay count",
        icon="mdi:electric-switch",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("relay_count"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neptun sensors from a config entry."""
    coordinator: NeptunCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[NeptunSensor] = [
        NeptunSensor(coordinator, description) for description in SENSOR_TYPES
    ]

    # Add sensors for each line (wired and wireless)
    if coordinator.data:
        for line_id, line_data in coordinator.data.get("lines", {}).items():
            if "value" in line_data:  # counter
                entities.append(
                    NeptunLineSensor(
                        coordinator,
                        line_id,
                        "value",
                        f"{line_data.get('name', line_id)} value",
                        icon="mdi:counter",
                        state_class=SensorStateClass.TOTAL_INCREASING,
                    )
                )
            if "signal" in line_data:  # wireless sensor
                entities.append(
                    NeptunLineSensor(
                        coordinator,
                        line_id,
                        "signal",
                        f"{line_data.get('name', line_id)} signal",
                        icon="mdi:signal",
                        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
                    )
                )
            if "battery" in line_data:  # wireless sensor battery
                entities.append(
                    NeptunLineSensor(
                        coordinator,
                        line_id,
                        "battery",
                        f"{line_data.get('name', line_id)} battery",
                        icon="mdi:battery",
                        device_class=SensorDeviceClass.BATTERY,
                        native_unit_of_measurement=PERCENTAGE,
                    )
                )

    async_add_entities(entities)


class NeptunSensor(NeptunEntity, SensorEntity):
    """Representation of a Neptun sensor."""

    entity_description: NeptunSensorDescription

    def __init__(
        self,
        coordinator: NeptunCoordinator,
        description: NeptunSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_name = description.name

    @property
    def native_value(self):
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class NeptunLineSensor(NeptunEntity, SensorEntity):
    """Sensor for a specific line (sensor or counter)."""

    def __init__(
        self,
        coordinator: NeptunCoordinator,
        line_id: str,
        data_key: str,
        name: str,
        icon: str | None = None,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        native_unit_of_measurement: str | None = None,
    ) -> None:
        """Initialize the line sensor."""
        super().__init__(coordinator, f"{line_id}_{data_key}")
        self._line_id = line_id
        self._data_key = data_key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = native_unit_of_measurement

    @property
    def native_value(self):
        """Return the value from the line data."""
        if self.coordinator.data is None:
            return None
        line = self.coordinator.data.get("lines", {}).get(self._line_id, {})
        return line.get(self._data_key)