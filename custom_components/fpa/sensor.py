"""Reported settings and preparation, plus a local funnel allowance per machine."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import voluptuous as vol
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import SERVICE_TURN_ON
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import FpaConfigEntry
from .const import ATTR_BOTTLE_ID, DOMAIN, SUMMARY_STATES
from .coordinator import DeviceCoordinator
from .entity import FpaEntity
from .models import TEMPERATURE_STATES, Preparation

STATE_TO_ICON = {
    "requesting_bottle": "mdi:transfer-down",
    "making_bottle": "mdi:transfer-down",
    "full_bottle": "mdi:cup",
    "funnel_cleaning_needed": "mdi:liquid-spot",
    "funnel_out": "mdi:filter-off-outline",
    "lid_open": "mdi:projector-screen-variant-off-outline",
    "low_water": "mdi:water-off",
    "bottle_missing": "mdi:cup-off-outline",
    "ready": "mdi:cup-outline",
    "heating": "mdi:thermometer-chevron-up",
    "cooling": "mdi:thermometer-chevron-down",
    "bottle_check_needed": "mdi:cup-water",
}

SETTING_DESCRIPTIONS = (
    SensorEntityDescription(
        key="selected_volume", translation_key="selected_volume", icon="mdi:cup-water"
    ),
    SensorEntityDescription(
        key="temperature_setting",
        translation_key="temperature_setting",
        device_class=SensorDeviceClass.ENUM,
        options=list(TEMPERATURE_STATES.values()),
        icon="mdi:thermometer",
    ),
    SensorEntityDescription(
        key="powder_setting", translation_key="powder_setting", icon="mdi:spoon-sugar"
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FpaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add reported sensors and the local funnel allowance for each machine."""
    entities: list[SensorEntity] = []
    for coordinator in entry.runtime_data.devices.values():
        entities.append(FpaMainSensor(coordinator))
        entities.extend(
            FpaSettingSensor(coordinator, description)
            for description in SETTING_DESCRIPTIONS
        )
        entities.append(FpaLastPreparationSensor(coordinator))
        entities.append(FpaFunnelRemainingSensor(coordinator))
    async_add_entities(entities)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_TURN_ON,
        {vol.Required(ATTR_BOTTLE_ID): cv.positive_int},
        _async_handle_turn_on,
    )


async def _async_handle_turn_on(entity: SensorEntity, call: ServiceCall) -> None:
    """Retain the legacy target while rejecting other setting sensors visibly."""
    if not isinstance(entity, FpaMainSensor):
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="invalid_target"
        )
    await entity.turn_on(**call.data)


class FpaMainSensor(FpaEntity, SensorEntity):
    """The original entity and attribute contract, with shared safeguards."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(SUMMARY_STATES)
    _attr_translation_key = "summary"
    _attr_has_entity_name = False

    def __init__(self, coordinator: DeviceCoordinator) -> None:
        super().__init__(coordinator, "summary")
        self._attr_unique_id = coordinator.device_id
        self._attr_name = coordinator.title

    @property
    def native_value(self) -> str | None:
        return self.coordinator.summary_state

    @property
    def assumed_state(self) -> bool:
        return self.coordinator.guard.pending

    @property
    def icon(self) -> str:
        return STATE_TO_ICON.get(self.native_value, "mdi:baby-bottle")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        settings = self.coordinator.data.settings
        alerts = self.coordinator.data.alerts
        attributes = {
            "temperature": settings.temperature,
            "powder": settings.powder,
            "volume": settings.volume,
            "volume_unit": settings.volume_unit,
            "making_bottle": settings.making_bottle,
            "water_only": settings.water_only,
            "bottle_missing": alerts.bottle_missing,
            "funnel_cleaning_needed": alerts.funnel_cleaning_needed,
            "funnel_out": alerts.funnel_out,
            "lid_open": alerts.lid_open,
            "low_water": alerts.low_water,
        }
        attributes.update(
            {
                f"bottle_{preset.id}": preset.description
                for preset in self.coordinator.presets.values()
            }
        )
        return attributes

    async def turn_on(self, **kwargs: Any) -> None:
        """Start a requested saved preset through the common guarded path."""
        await self.coordinator.async_start(kwargs[ATTR_BOTTLE_ID])


class FpaSettingSensor(FpaEntity, SensorEntity):
    """One reported setting, without inferred physical measurements."""

    def __init__(
        self, coordinator: DeviceCoordinator, description: SensorEntityDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | float | str | None:
        settings = self.coordinator.data.settings
        if self.entity_description.key == "selected_volume":
            return settings.volume
        if self.entity_description.key == "temperature_setting":
            return TEMPERATURE_STATES.get(settings.temperature)
        return settings.powder

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.key == "selected_volume":
            return self.coordinator.data.settings.volume_unit
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key == "temperature_setting":
            return {"temperature_code": self.coordinator.data.settings.temperature}
        return None


class FpaFunnelRemainingSensor(FpaEntity, SensorEntity):
    """Local bottles remaining; never a source for reported cleaning alerts."""

    _attr_translation_key = "funnel_bottles_remaining"
    _attr_icon = "mdi:baby-bottle-outline"

    def __init__(self, coordinator: DeviceCoordinator) -> None:
        super().__init__(coordinator, "funnel_bottles_remaining")

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> int:
        return self.coordinator.funnel.remaining


class FpaLastPreparationSensor(FpaEntity, RestoreSensor):
    """Retain one complete historical snapshot through outages and restarts."""

    _attr_translation_key = "last_preparation"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:baby-bottle-outline"

    def __init__(self, coordinator: DeviceCoordinator) -> None:
        super().__init__(coordinator, "last_preparation")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        restored = await self.async_get_last_sensor_data()
        state = await self.async_get_last_state()
        if restored is None or state is None:
            return
        completed_at = restored.native_value
        if not isinstance(completed_at, datetime) or completed_at.tzinfo is None:
            return
        if dt_util.parse_datetime(state.state) != completed_at:
            # Sensor-specific data and attributes must describe the same saved
            # observation; a partial/corrupt restoration cannot mix them.
            return
        completed_at = completed_at.astimezone(UTC)
        attributes = state.attributes
        required = {
            "record_id",
            "volume",
            "volume_unit",
            "temperature_setting",
            "powder_setting",
            "water_only",
            "preset_id",
        }
        if not required.issubset(attributes):
            return
        self.coordinator.restore_preparation(
            Preparation(
                completed_at=completed_at,
                record_id=attributes["record_id"],
                volume=attributes["volume"],
                volume_unit=attributes["volume_unit"],
                temperature_setting=attributes["temperature_setting"],
                powder_setting=attributes["powder_setting"],
                water_only=attributes["water_only"],
                preset_id=attributes["preset_id"],
                provenance="restored",
            )
        )

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> datetime | None:
        preparation = self.coordinator.data.preparation
        return preparation.completed_at if preparation else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        preparation = self.coordinator.data.preparation
        return preparation.attributes if preparation else {}
