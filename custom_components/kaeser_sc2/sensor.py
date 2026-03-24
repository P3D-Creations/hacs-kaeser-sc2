"""Sensor platform for Kaeser Sigma Control 2."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, UnitOfPressure, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CompressorData
from .const import CONF_NAME, DOMAIN, MANUFACTURER, MODEL
from .util import slugify_name
from .coordinator import KaeserSC2Coordinator


@dataclass(frozen=True, kw_only=True)
class KaeserSensorDescription(SensorEntityDescription):
    """Extended sensor description with value extractor."""

    value_fn: Callable[[CompressorData], Any]
    unit_fn: Callable[[CompressorData], str | None] | None = None


SENSOR_DESCRIPTIONS: tuple[KaeserSensorDescription, ...] = (
    KaeserSensorDescription(
        key="pressure",
        translation_key="pressure",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        value_fn=lambda d: d.pressure,
        unit_fn=lambda d: (
            UnitOfPressure.PSI
            if d.pressure_unit.lower() == "psi"
            else UnitOfPressure.BAR
            if d.pressure_unit.lower() == "bar"
            else d.pressure_unit
        ),
    ),
    KaeserSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        value_fn=lambda d: d.temperature,
        unit_fn=lambda d: (
            UnitOfTemperature.FAHRENHEIT
            if "F" in d.temperature_unit
            else UnitOfTemperature.CELSIUS
        ),
    ),
    KaeserSensorDescription(
        key="state",
        translation_key="state",
        icon="mdi:air-conditioner",
        value_fn=lambda d: d.state,
    ),
    KaeserSensorDescription(
        key="run_hours",
        translation_key="run_hours",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        icon="mdi:timer-outline",
        value_fn=lambda d: d.run_hours,
    ),
    KaeserSensorDescription(
        key="maintenance_in",
        translation_key="maintenance_in",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        icon="mdi:wrench-clock",
        value_fn=lambda d: d.maintenance_in,
    ),
    KaeserSensorDescription(
        key="key_switch",
        translation_key="key_switch",
        icon="mdi:key-variant",
        value_fn=lambda d: d.key_switch,
    ),
    KaeserSensorDescription(
        key="pa_status",
        translation_key="pa_status",
        icon="mdi:remote",
        value_fn=lambda d: d.pa_status,
    ),
    KaeserSensorDescription(
        key="controller_time",
        translation_key="controller_time",
        icon="mdi:clock-outline",
        value_fn=lambda d: d.controller_time,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: KaeserSC2Coordinator = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]
    name = entry.data.get(CONF_NAME, host)
    slug = slugify_name(name)

    entities = [
        KaeserSensor(coordinator, desc, host, name, slug)
        for desc in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class KaeserSensor(CoordinatorEntity[KaeserSC2Coordinator], SensorEntity):
    """A sensor backed by the SC2 coordinator."""

    entity_description: KaeserSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KaeserSC2Coordinator,
        description: KaeserSensorDescription,
        host: str,
        name: str,
        slug: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._host = host
        self._device_name = name
        self._slug = slug
        self._attr_unique_id = f"{slug}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._host)},
            name=self._device_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
            configuration_url=f"http://{self._host}",
        )

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return units — dynamic for pressure/temperature."""
        if self.entity_description.unit_fn and self.coordinator.data:
            return self.entity_description.unit_fn(self.coordinator.data)
        return self.entity_description.native_unit_of_measurement

    @property
    def available(self) -> bool:
        return super().available and (
            self.coordinator.data is not None and self.coordinator.data.online
        )
