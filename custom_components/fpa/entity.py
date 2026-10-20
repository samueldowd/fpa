"""Common Formula Pro device identity and push subscriptions."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DeviceCoordinator


class FpaEntity(CoordinatorEntity[DeviceCoordinator]):
    """Present cached shared state; entity properties never perform I/O."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DeviceCoordinator, suffix: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            manufacturer="Baby Brezza",
            name=coordinator.title,
        )

    @property
    def available(self) -> bool:
        """Live values require a usable device snapshot and connection."""
        return self.coordinator.available
