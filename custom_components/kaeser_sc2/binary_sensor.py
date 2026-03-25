"""Binary sensor platform for Kaeser Sigma Control 2."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CompressorData
from .const import CONF_NAME, DOMAIN, MANUFACTURER, MODEL
from .coordinator import KaeserSC2Coordinator
from .util import slugify_name


@dataclass(frozen=True, kw_only=True)
class KaeserBinarySensorDescription(BinarySensorEntityDescription):
    """Extended binary sensor description."""

    value_fn: Callable[[CompressorData], bool]
    raw_state_fn: Callable[[CompressorData], str] | None = None
    led_color: str | None = None  # Hardcoded LED colour matching SC2 firmware


def _led_on(val: str) -> bool:
    """Return True if LED is on or flashing."""
    return val in ("on", "flash")


BINARY_SENSOR_DESCRIPTIONS: tuple[KaeserBinarySensorDescription, ...] = (
    KaeserBinarySensorDescription(
        key="led_error",
        translation_key="led_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:alert-circle",
        value_fn=lambda d: _led_on(d.led_error),
        raw_state_fn=lambda d: d.led_error,
        led_color="red",
    ),
    KaeserBinarySensorDescription(
        key="led_com_error",
        translation_key="led_com_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:lan-disconnect",
        value_fn=lambda d: _led_on(d.led_com_error),
        raw_state_fn=lambda d: d.led_com_error,
        led_color="red",
    ),
    KaeserBinarySensorDescription(
        key="led_maintenance",
        translation_key="led_maintenance",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:wrench",
        value_fn=lambda d: _led_on(d.led_maintenance),
        raw_state_fn=lambda d: d.led_maintenance,
        led_color="orange",
    ),
    KaeserBinarySensorDescription(
        key="led_voltage",
        translation_key="led_voltage",
        device_class=BinarySensorDeviceClass.POWER,
        icon="mdi:flash",
        value_fn=lambda d: _led_on(d.led_voltage),
        raw_state_fn=lambda d: d.led_voltage,
        led_color="green",
    ),
    KaeserBinarySensorDescription(
        key="led_load",
        translation_key="led_load",
        icon="mdi:engine",
        value_fn=lambda d: _led_on(d.led_load),
        raw_state_fn=lambda d: d.led_load,
        led_color="green",
    ),
    KaeserBinarySensorDescription(
        key="led_idle",
        translation_key="led_idle",
        icon="mdi:sleep",
        value_fn=lambda d: _led_on(d.led_idle),
        raw_state_fn=lambda d: d.led_idle,
        led_color="green",
    ),
    KaeserBinarySensorDescription(
        key="led_remote",
        translation_key="led_remote",
        icon="mdi:remote-desktop",
        value_fn=lambda d: _led_on(d.led_remote),
        raw_state_fn=lambda d: d.led_remote,
        led_color="green",
    ),
    KaeserBinarySensorDescription(
        key="led_clock",
        translation_key="led_clock",
        icon="mdi:clock-outline",
        value_fn=lambda d: _led_on(d.led_clock),
        raw_state_fn=lambda d: d.led_clock,
        led_color="green",
    ),
    KaeserBinarySensorDescription(
        key="led_power_on",
        translation_key="led_power_on",
        device_class=BinarySensorDeviceClass.POWER,
        icon="mdi:power",
        value_fn=lambda d: _led_on(d.led_power_on),
        raw_state_fn=lambda d: d.led_power_on,
        led_color="green",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    coordinator: KaeserSC2Coordinator = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]
    name = entry.data.get(CONF_NAME, host)
    slug = slugify_name(name)

    entities = [
        KaeserBinarySensor(coordinator, desc, host, name, slug)
        for desc in BINARY_SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class KaeserBinarySensor(
    CoordinatorEntity[KaeserSC2Coordinator], BinarySensorEntity
):
    """A binary sensor backed by the SC2 coordinator."""

    entity_description: KaeserBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KaeserSC2Coordinator,
        description: KaeserBinarySensorDescription,
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
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose LED raw state and colour as entity attributes."""
        attrs: dict[str, Any] = {}
        desc = self.entity_description
        if desc.raw_state_fn and self.coordinator.data:
            attrs["led_raw_state"] = desc.raw_state_fn(self.coordinator.data)
        if desc.led_color:
            attrs["led_color"] = desc.led_color
        return attrs if attrs else None

    @property
    def available(self) -> bool:
        return super().available and (
            self.coordinator.data is not None and self.coordinator.data.online
        )
