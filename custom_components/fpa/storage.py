"""Versioned HA-managed selections and minimal restart guard, never bottle history."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .models import integer

STORAGE_VERSION = 1


class FpaStorage:
    """Entry-isolated storage with ordered saves and a deliberately narrow schema."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store(hass, STORAGE_VERSION, f"fpa.{entry_id}")
        self._lock = asyncio.Lock()
        self._records: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        raw = await self._store.async_load()
        if not isinstance(raw, dict) or not isinstance(raw.get("devices"), dict):
            return
        for device_id, record in raw["devices"].items():
            if isinstance(device_id, str) and isinstance(record, dict):
                selected_id = integer(record.get("selected_id"))
                guard = record.get("guard", {})
                self._records[device_id] = {
                    "selected_id": selected_id
                    if selected_id is not None and selected_id > 0
                    else None,
                    "guard": self._safe_guard(guard),
                }

    @staticmethod
    def _safe_guard(guard: Any) -> dict[str, Any]:
        if not isinstance(guard, dict):
            return {}
        return {
            "occupied": guard.get("occupied") is True,
            "uncertain": guard.get("uncertain") is True,
            "pending": guard.get("pending") is True,
            "last_preparation": guard.get("last_preparation")
            if isinstance(guard.get("last_preparation"), (int, float))
            and not isinstance(guard.get("last_preparation"), bool)
            else None,
        }

    def get(self, device_id: str) -> dict[str, Any]:
        return deepcopy(self._records.get(device_id, {}))

    async def async_save(
        self, device_id: str, selected_id: int | None, guard: dict
    ) -> None:
        self._records[device_id] = {
            "selected_id": selected_id,
            "guard": self._safe_guard(guard),
        }
        async with self._lock:
            await self._store.async_save({"devices": deepcopy(self._records)})
