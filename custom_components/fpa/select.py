"""Local, restart-safe selection of a named cloud preset."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FpaConfigEntry
from .const import DOMAIN
from .coordinator import DeviceCoordinator
from .entity import FpaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FpaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add one selector per machine without choosing a default."""
    async_add_entities(
        FpaPresetSelect(coordinator)
        for coordinator in entry.runtime_data.devices.values()
    )


class FpaPresetSelect(FpaEntity, SelectEntity):
    """Cloud names are presentation; stable IDs retain the user's choice."""

    _attr_translation_key = "preset"
    _attr_icon = "mdi:format-list-bulleted"

    def __init__(self, coordinator: DeviceCoordinator) -> None:
        super().__init__(coordinator, "preset")

    @property
    def available(self) -> bool:
        return bool(self.coordinator.presets)

    @property
    def options(self) -> list[str]:
        return list(self.coordinator.preset_options)

    @property
    def current_option(self) -> str | None:
        selected = self.coordinator.selected_id
        return next(
            (
                label
                for label, preset_id in self.coordinator.preset_options.items()
                if preset_id == selected
            ),
            None,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        preset = self.coordinator.presets.get(self.coordinator.selected_id)
        if preset is None:
            return {}
        return {
            "preset_id": preset.id,
            "volume": preset.volume,
            "volume_unit": preset.volume_unit,
            "temperature_setting": preset.temperature,
            "powder_setting": preset.powder,
            "water_only": preset.water_only,
            "description": preset.description,
        }

    async def async_select_option(self, option: str) -> None:
        preset_id = self.coordinator.preset_options.get(option)
        if preset_id is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_preset"
            )
        await self.coordinator.async_select(preset_id)
