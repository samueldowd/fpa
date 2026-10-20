"""Load the fork over an upstream-v1-shaped entry and existing registries."""

from unittest.mock import patch

import pytest
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_diagnostics import FakeApi


@pytest.mark.parametrize("disabled", [False, True])
async def test_upstream_entry_and_registry_preserved_on_first_fork_load(
    hass, device_payload, disabled
):
    entry = MockConfigEntry(
        domain="fpa",
        version=1,
        data={"refresh_token": "upstream-v1-token"},
        title="Renamed account",
    )
    entry.add_to_hass(hass)
    area = ar.async_get(hass).async_create("Example kitchen")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("fpa", device_payload["deviceId"])},
        manufacturer="Baby Brezza",
        name=device_payload["title"],
    )
    dr.async_get(hass).async_update_device(
        device.id, name_by_user="My machine", area_id=area.id
    )
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor",
        "fpa",
        device_payload["deviceId"],
        config_entry=entry,
        device_id=device.id,
        suggested_object_id="existing_bottle_maker",
        disabled_by=er.RegistryEntryDisabler.USER if disabled else None,
    )
    registry.async_update_entity(
        old.entity_id, name="Existing custom name", icon="mdi:cup", area_id=area.id
    )
    api = FakeApi([device_payload])
    with patch("custom_components.fpa.FpaClient", return_value=api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        current = registry.async_get(old.entity_id)
        assert current.unique_id == device_payload["deviceId"]
        assert current.entity_id == old.entity_id
        assert current.device_id == device.id
        assert current.name == "Existing custom name" and current.icon == "mdi:cup"
        assert current.area_id == area.id
        assert current.disabled_by == (
            er.RegistryEntryDisabler.USER if disabled else None
        )
        assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 17
        assert entry.version == 1 and entry.data["refresh_token"] == "upstream-v1-token"
        updated_device = dr.async_get(hass).async_get(device.id)
        assert (
            updated_device.name_by_user == "My machine"
            and updated_device.area_id == area.id
        )
        # Shared safety tracking continues even when the original entity is disabled.
        coordinator = entry.runtime_data.devices[device_payload["deviceId"]]
        assert coordinator.guard.uncertain is False
        assert coordinator.data.alerts.bottle_missing is True
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
