"""Offline HA entity contract, compatibility and restoration checks."""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorExtraStoredData
from homeassistant.core import State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fpa.api import FpaClient
from custom_components.fpa.models import Preparation
from custom_components.fpa.sensor import (
    FpaLastPreparationSensor,
)


@pytest.fixture
async def configured(hass, device_payload, identity):
    """Load real HA platforms against a completely fake cloud transport."""
    api = MagicMock(spec=FpaClient)
    api.refresh_token = "test-refresh"
    api.refresh = AsyncMock()
    api.get_me = AsyncMock(return_value={"devices": [identity]})
    api.get_device_details = AsyncMock(side_effect=lambda _: deepcopy(device_payload))
    api.start_bottle = AsyncMock()
    api.close = AsyncMock()

    async def subscribe(device_id, on_message, on_connection):
        on_connection(True)

    api.subscribe = AsyncMock(side_effect=subscribe)
    entry = MockConfigEntry(
        domain="fpa", title="Example account", data={"refresh_token": "test-refresh"}
    )
    entry.add_to_hass(hass)
    with patch("custom_components.fpa.FpaClient", return_value=api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry, api, entry.runtime_data.devices[identity["deviceId"]]
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


def entity_id(hass, coordinator, domain, suffix=None):
    unique_id = (
        coordinator.device_id if suffix is None else f"{coordinator.device_id}_{suffix}"
    )
    return er.async_get(hass).async_get_entity_id(domain, "fpa", unique_id)


async def test_seventeen_entities_preserve_original_identity_and_attributes(
    hass, configured
):
    entry, api, coordinator = configured
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(entries) == 17
    assert len({entity.device_id for entity in entries}) == 1
    device = dr.async_get(hass).async_get(
        registry.async_get(entity_id(hass, coordinator, "sensor")).device_id
    )
    assert device is not None
    summary = hass.states.get(entity_id(hass, coordinator, "sensor"))
    assert summary.state == "bottle_missing"
    assert summary.attributes["device_class"] == "enum"
    assert summary.attributes["temperature"] == 1
    assert {
        "temperature",
        "powder",
        "volume",
        "volume_unit",
        "making_bottle",
        "water_only",
        "bottle_missing",
        "funnel_cleaning_needed",
        "funnel_out",
        "lid_open",
        "low_water",
    }.issubset(summary.attributes)
    for preset in coordinator.presets.values():
        assert f"bottle_{preset.id}" in summary.attributes
        assert "None None" not in summary.attributes[f"bottle_{preset.id}"]
    assert (
        hass.states.get(
            entity_id(hass, coordinator, "sensor", "temperature_setting")
        ).state
        == "body_temperature"
    )
    selected_volume = hass.states.get(
        entity_id(hass, coordinator, "sensor", "selected_volume")
    )
    assert selected_volume.state == "2"
    assert selected_volume.attributes["unit_of_measurement"] == "oz"
    assert "state_class" not in selected_volume.attributes
    assert "device_class" not in selected_volume.attributes
    assert not api.start_bottle.called


async def test_controls_share_central_command_and_selection_has_no_write(
    hass, configured
):
    entry, api, coordinator = configured
    preset_id = next(iter(coordinator.presets))
    selector_id = entity_id(hass, coordinator, "select", "preset")
    assert hass.states.get(selector_id).state == "unknown"
    label = next(
        label
        for label, value in coordinator.preset_options.items()
        if value == preset_id
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": selector_id, "option": label},
        blocking=True,
    )
    assert coordinator.selected_id == preset_id
    api.start_bottle.assert_not_called()

    with patch.object(coordinator, "async_start", new_callable=AsyncMock) as start:
        await hass.services.async_call(
            "button",
            "press",
            {
                "entity_id": entity_id(
                    hass, coordinator, "button", "start_selected_preset"
                )
            },
            blocking=True,
        )
        start.assert_awaited_once_with()
        start.reset_mock()
        await hass.services.async_call(
            "fpa",
            "turn_on",
            {
                "entity_id": entity_id(hass, coordinator, "sensor"),
                "bottle_id": preset_id,
            },
            blocking=True,
        )
        start.assert_awaited_once_with(preset_id)
        assert coordinator.selected_id == preset_id

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "fpa",
            "turn_on",
            {
                "entity_id": entity_id(hass, coordinator, "sensor", "powder_setting"),
                "bottle_id": preset_id,
            },
            blocking=True,
        )
    with patch.object(coordinator, "async_refresh", new_callable=AsyncMock) as refresh:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_id(hass, coordinator, "button", "refresh_data")},
            blocking=True,
        )
        refresh.assert_awaited_once_with()
    api.subscribe.assert_awaited_once()


async def test_nullable_independent_flags_and_temperature_zero(hass, configured):
    entry, api, coordinator = configured
    coordinator.receive_message(
        {
            "subject": "shadow-update",
            "body": {
                "deviceId": coordinator.device_id,
                "state": {
                    "reported": {
                        "settings": {"temperature": 0},
                        "hardware": {
                            "alerts": {
                                "lowWater": True,
                                "lidOpen": True,
                                "tempHeating": None,
                            }
                        },
                    }
                },
            },
        }
    )
    await hass.async_block_till_done()
    assert (
        hass.states.get(
            entity_id(hass, coordinator, "sensor", "temperature_setting")
        ).state
        == "room_temperature"
    )
    assert (
        hass.states.get(
            entity_id(hass, coordinator, "binary_sensor", "low_water")
        ).state
        == "on"
    )
    assert (
        hass.states.get(entity_id(hass, coordinator, "binary_sensor", "lid_open")).state
        == "on"
    )
    assert (
        hass.states.get(entity_id(hass, coordinator, "binary_sensor", "heating")).state
        == "unknown"
    )
    coordinator.receive_message(
        {
            "subject": "shadow-update",
            "body": {
                "deviceId": coordinator.device_id,
                "state": {"reported": {"settings": {"temperature": 99}}},
            },
        }
    )
    await hass.async_block_till_done()
    unknown = hass.states.get(
        entity_id(hass, coordinator, "sensor", "temperature_setting")
    )
    assert unknown.state == "unknown"
    assert unknown.attributes["temperature_code"] == 99


async def test_outage_preserves_history_cached_selection_and_refresh(hass, configured):
    entry, api, coordinator = configured
    historical_id = entity_id(hass, coordinator, "sensor", "last_preparation")
    before = hass.states.get(historical_id)
    assert before.state != "unknown"
    coordinator.connection_changed(False)
    await hass.async_block_till_done()
    assert (
        hass.states.get(entity_id(hass, coordinator, "sensor")).state == "unavailable"
    )
    after = hass.states.get(historical_id)
    assert before.state == after.state
    assert before.attributes == after.attributes
    assert (
        hass.states.get(entity_id(hass, coordinator, "select", "preset")).state
        != "unavailable"
    )
    assert (
        hass.states.get(entity_id(hass, coordinator, "button", "refresh_data")).state
        != "unavailable"
    )


async def test_history_is_immutable_when_current_settings_and_presets_change(
    hass, configured
):
    entry, api, coordinator = configured
    historical_id = entity_id(hass, coordinator, "sensor", "last_preparation")
    before = hass.states.get(historical_id)
    preparation = coordinator.data.preparation
    coordinator.receive_message(
        {
            "subject": "shadow-update",
            "body": {
                "deviceId": coordinator.device_id,
                "state": {
                    "reported": {
                        "settings": {"temperature": 2, "volume": 8, "powder": 7}
                    }
                },
            },
        }
    )
    await hass.async_block_till_done()
    after = hass.states.get(historical_id)
    assert before.state == after.state
    assert before.attributes == after.attributes
    assert before.last_updated == after.last_updated
    assert coordinator.data.preparation == preparation


@pytest.mark.parametrize("cloud_newer", [False, True])
async def test_restore_sensor_never_regresses_or_combines_current_settings(
    hass, configured, cloud_newer
):
    entry, api, coordinator = configured
    cloud = coordinator.data.preparation
    assert cloud is not None
    restored_time = cloud.completed_at + timedelta(days=-1 if cloud_newer else 1)
    restored = Preparation(
        completed_at=restored_time,
        record_id=9001,
        volume=3,
        volume_unit="oz",
        temperature_setting=0,
        powder_setting=4,
        water_only=True,
        preset_id=None,
        provenance="restored",
    )
    sensor = FpaLastPreparationSensor(coordinator)
    sensor.hass = hass
    sensor.async_write_ha_state = MagicMock()
    with (
        patch.object(
            sensor,
            "async_get_last_sensor_data",
            return_value=SensorExtraStoredData(restored_time, None),
        ),
        patch.object(
            sensor,
            "async_get_last_state",
            return_value=State(
                "sensor.restored", restored_time.isoformat(), restored.attributes
            ),
        ),
    ):
        await sensor.async_added_to_hass()
    chosen = cloud if cloud_newer else restored
    assert sensor.native_value == chosen.completed_at
    assert sensor.extra_state_attributes == chosen.attributes
    await sensor.async_will_remove_from_hass()


async def test_incomplete_restoration_is_ignored(hass, configured):
    entry, api, coordinator = configured
    coordinator.data = replace(coordinator.data, preparation=None)
    sensor = FpaLastPreparationSensor(coordinator)
    sensor.hass = hass
    sensor.async_write_ha_state = MagicMock()
    restored_time = datetime(2025, 1, 2, tzinfo=UTC)
    with (
        patch.object(
            sensor,
            "async_get_last_sensor_data",
            return_value=SensorExtraStoredData(restored_time, None),
        ),
        patch.object(
            sensor,
            "async_get_last_state",
            return_value=State(
                "sensor.restored", restored_time.isoformat(), {"volume": 3}
            ),
        ),
    ):
        await sensor.async_added_to_hass()
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}
    await sensor.async_will_remove_from_hass()


async def test_registry_customizations_survive_reload(hass, configured):
    entry, api, coordinator = configured
    registry = er.async_get(hass)
    summary_id = entity_id(hass, coordinator, "sensor")
    registry.async_update_entity(
        summary_id, name="My bottle maker", icon="mdi:cup", disabled_by=None
    )
    device = dr.async_get(hass).async_get(
        registry.async_get(entity_id(hass, coordinator, "sensor")).device_id
    )
    dr.async_get(hass).async_update_device(device.id, name_by_user="Kitchen appliance")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(summary_id).name == "My bottle maker"
    assert registry.async_get(summary_id).icon == "mdi:cup"
    assert registry.async_get(summary_id).unique_id == coordinator.device_id
    assert dr.async_get(hass).async_get(device.id).name_by_user == "Kitchen appliance"
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 17


async def test_equal_timestamp_restore_keeps_current_cloud_record(hass, configured):
    entry, api, coordinator = configured
    cloud = coordinator.data.preparation
    assert cloud is not None and cloud.record_id is not None
    stale = replace(cloud, volume=99, powder_setting=99, provenance="restored")
    sensor = FpaLastPreparationSensor(coordinator)
    sensor.hass = hass
    sensor.async_write_ha_state = MagicMock()
    with (
        patch.object(
            sensor,
            "async_get_last_sensor_data",
            return_value=SensorExtraStoredData(stale.completed_at, None),
        ),
        patch.object(
            sensor,
            "async_get_last_state",
            return_value=State(
                "sensor.restored", stale.completed_at.isoformat(), stale.attributes
            ),
        ),
    ):
        await sensor.async_added_to_hass()
    assert sensor.extra_state_attributes == cloud.attributes
    await sensor.async_will_remove_from_hass()


async def test_restore_rejects_mismatched_timestamp_and_attributes(hass, configured):
    entry, api, coordinator = configured
    cloud = coordinator.data.preparation
    sensor = FpaLastPreparationSensor(coordinator)
    sensor.hass = hass
    sensor.async_write_ha_state = MagicMock()
    newer = cloud.completed_at + timedelta(days=1)
    with (
        patch.object(
            sensor,
            "async_get_last_sensor_data",
            return_value=SensorExtraStoredData(newer, None),
        ),
        patch.object(
            sensor,
            "async_get_last_state",
            return_value=State(
                "sensor.restored", cloud.completed_at.isoformat(), cloud.attributes
            ),
        ),
    ):
        await sensor.async_added_to_hass()
    assert sensor.native_value == cloud.completed_at
    assert sensor.extra_state_attributes == cloud.attributes
    await sensor.async_will_remove_from_hass()


async def test_accounts_and_devices_keep_selection_and_services_isolated(
    hass, configured, device_payload, identity
):
    first_entry, first_api, first = configured
    other_identity = {
        **identity,
        "deviceId": "00000000-0000-4000-8000-000000000002",
        "id": 202,
        "title": "Other machine",
    }
    other_payload = {**deepcopy(device_payload), **other_identity}
    other_api = MagicMock(spec=FpaClient)
    other_api.refresh = AsyncMock()
    other_api.get_me = AsyncMock(return_value={"devices": [other_identity]})
    other_api.get_device_details = AsyncMock(return_value=other_payload)
    other_api.start_bottle = AsyncMock()
    other_api.close = AsyncMock()

    async def subscribe(device_id, on_message, on_connection):
        on_connection(True)

    other_api.subscribe = AsyncMock(side_effect=subscribe)
    other_entry = MockConfigEntry(
        domain="fpa", title="Other account", data={"refresh_token": "other-token"}
    )
    other_entry.add_to_hass(hass)
    with patch("custom_components.fpa.FpaClient", return_value=other_api):
        assert await hass.config_entries.async_setup(other_entry.entry_id)
        await hass.async_block_till_done()
    other = other_entry.runtime_data.devices[other_identity["deviceId"]]
    assert (
        len(er.async_entries_for_config_entry(er.async_get(hass), first_entry.entry_id))
        == 17
    )
    assert (
        len(er.async_entries_for_config_entry(er.async_get(hass), other_entry.entry_id))
        == 17
    )
    selected_id = next(iter(first.presets))
    await first.async_select(selected_id)
    assert first.selected_id == selected_id
    assert other.selected_id is None
    with (
        patch.object(first, "async_start", new_callable=AsyncMock) as first_start,
        patch.object(other, "async_start", new_callable=AsyncMock) as other_start,
    ):
        await hass.services.async_call(
            "fpa",
            "turn_on",
            {"entity_id": entity_id(hass, other, "sensor"), "bottle_id": selected_id},
            blocking=True,
        )
        first_start.assert_not_awaited()
        other_start.assert_awaited_once_with(selected_id)
        assert await hass.config_entries.async_unload(other_entry.entry_id)
        await hass.services.async_call(
            "fpa",
            "turn_on",
            {"entity_id": entity_id(hass, first, "sensor"), "bottle_id": selected_id},
            blocking=True,
        )
        first_start.assert_awaited_once_with(selected_id)
    other_api.close.assert_awaited_once()
    first_api.close.assert_not_awaited()


@pytest.mark.parametrize(
    "reason,action",
    [
        ("device_unavailable", "Check the machine and cloud connection"),
        ("request_pending", "wait for that request to resolve"),
        ("making_bottle", "Wait for it to finish"),
        ("occupied_bottle", "replace it with an empty bottle"),
        ("bottle_check_needed", "Remove the bottle, check or empty it"),
        ("readiness_unverified", "Refresh data and check the machine"),
        ("bottle_missing", "Place an empty bottle under the funnel"),
        ("funnel_cleaning_needed", "Clean and reinstall the funnel"),
        ("funnel_out", "Reinstall the funnel"),
        ("lid_open", "Close the machine lid"),
        ("low_water", "Refill the water tank"),
        ("heating", "Wait for heating to finish"),
        ("cooling", "Wait for cooling to finish"),
    ],
)
async def test_blocked_start_resolves_actionable_translation(
    hass, configured, reason, action
):
    """Real HA action errors resolve English guidance while diagnostics keep codes."""
    from unittest.mock import PropertyMock

    from homeassistant.helpers.translation import async_get_translations

    entry, api, coordinator = configured
    translations = await async_get_translations(hass, "en", "exceptions", ["fpa"])
    key = f"blocked_{reason}"
    expected = translations[f"component.fpa.exceptions.{key}.message"]
    with patch.object(
        type(coordinator),
        "block_reasons",
        new_callable=PropertyMock,
        return_value=[reason],
    ):
        with pytest.raises(ServiceValidationError) as raised:
            await hass.services.async_call(
                "fpa",
                "turn_on",
                {
                    "entity_id": entity_id(hass, coordinator, "sensor"),
                    "bottle_id": next(iter(coordinator.presets)),
                },
                blocking=True,
            )
    error = raised.value
    assert error.translation_key == key
    assert error.translation_placeholders is None
    assert str(error) == expected.rstrip(".")
    assert action in str(error)
    assert key not in str(error)
    if "_" in reason:
        assert reason not in str(error)
    assert coordinator.runtime.operations[-1]["reason"] == reason
    api.start_bottle.assert_not_awaited()
