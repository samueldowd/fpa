"""Independent reported machine alerts and activity flags."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FpaConfigEntry
from .coordinator import DeviceCoordinator
from .entity import FpaEntity

DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="making_bottle",
        translation_key="making_bottle",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    BinarySensorEntityDescription(
        key="water_only", translation_key="water_only", icon="mdi:water"
    ),
    BinarySensorEntityDescription(
        key="bottle_missing",
        translation_key="bottle_missing",
        icon="mdi:cup-off-outline",
    ),
    BinarySensorEntityDescription(
        key="funnel_cleaning_needed",
        translation_key="funnel_cleaning_needed",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    BinarySensorEntityDescription(
        key="funnel_out",
        translation_key="funnel_out",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    BinarySensorEntityDescription(
        key="lid_open",
        translation_key="lid_open",
        device_class=BinarySensorDeviceClass.OPENING,
    ),
    BinarySensorEntityDescription(
        key="low_water",
        translation_key="low_water",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    BinarySensorEntityDescription(
        key="heating", translation_key="heating", icon="mdi:thermometer-chevron-up"
    ),
    BinarySensorEntityDescription(
        key="cooling", translation_key="cooling", icon="mdi:thermometer-chevron-down"
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FpaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add nine binary sensors per machine, including unknown optional flags."""
    async_add_entities(
        FpaBinarySensor(coordinator, description)
        for coordinator in entry.runtime_data.devices.values()
        for description in DESCRIPTIONS
    )


class FpaBinarySensor(FpaEntity, BinarySensorEntity):
    """An independent nullable field; missing never means false."""

    def __init__(
        self, coordinator: DeviceCoordinator, description: BinarySensorEntityDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        key = self.entity_description.key
        source = (
            self.coordinator.data.settings
            if key in {"making_bottle", "water_only"}
            else self.coordinator.data.alerts
        )
        return getattr(source, key)
