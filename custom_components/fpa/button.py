"""Selected-preset start and read-only refresh buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FpaConfigEntry
from .coordinator import DeviceCoordinator
from .entity import FpaEntity

DESCRIPTIONS = (
    ButtonEntityDescription(
        key="start_selected_preset",
        translation_key="start_selected_preset",
        icon="mdi:baby-bottle",
    ),
    ButtonEntityDescription(
        key="refresh_data",
        translation_key="refresh_data",
        icon="mdi:refresh",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FpaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add two buttons for each machine."""
    async_add_entities(
        FpaButton(coordinator, description)
        for coordinator in entry.runtime_data.devices.values()
        for description in DESCRIPTIONS
    )


class FpaButton(FpaEntity, ButtonEntity):
    """Route commands centrally; a refresh never opens another subscription."""

    def __init__(
        self, coordinator: DeviceCoordinator, description: ButtonEntityDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        if self.entity_description.key == "refresh_data":
            return True
        return self.coordinator.available

    async def async_press(self) -> None:
        if self.entity_description.key == "refresh_data":
            await self.coordinator.async_refresh()
        else:
            await self.coordinator.async_start()
