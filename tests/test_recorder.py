"""Actual SQLite Recorder observations from the offline HA integration.

Recorder alone writes its database. Tests query committed history through HA's
read-only history API, including full preparation attributes.
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import recorder as recorder_helper
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.fpa.api import FpaClient


@pytest.fixture
async def recorded_entry(hass, device_payload, identity, tmp_path):
    """Start real file-backed Recorder before adding offline integration entities."""
    recorder_helper.async_initialize_recorder(hass)
    assert await async_setup_component(
        hass,
        "recorder",
        {
            "recorder": {
                "db_url": f"sqlite:///{tmp_path / 'history.db'}",
                "commit_interval": 0,
                "auto_purge": False,
                "auto_repack": False,
            }
        },
    )
    recorder_instance = get_instance(hass)
    api = MagicMock(spec=FpaClient)
    api.refresh = AsyncMock()
    api.get_me = AsyncMock(return_value={"devices": [identity]})
    api.get_device_details = AsyncMock(side_effect=lambda _: deepcopy(device_payload))
    api.start_bottle = AsyncMock()
    api.close = AsyncMock()

    async def subscribe(device_id, on_message, on_connection):
        on_connection(True)

    api.subscribe = AsyncMock(side_effect=subscribe)
    entry = MockConfigEntry(
        domain="fpa", title="Recorder test", data={"refresh_token": "offline-test"}
    )
    entry.add_to_hass(hass)
    with patch("custom_components.fpa.FpaClient", return_value=api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data.devices[identity["deviceId"]]
        sensor_id = er.async_get(hass).async_get_entity_id(
            "sensor", "fpa", f"{coordinator.device_id}_last_preparation"
        )
        assert sensor_id is not None
        await async_wait_recording_done(hass)
        yield coordinator, api, sensor_id, recorder_instance
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def committed_history(hass, recorder, sensor_id):
    """Read actual committed rows with attributes, without history coalescing."""
    await async_wait_recording_done(hass)
    result = await recorder.async_add_executor_job(
        partial(
            get_significant_states,
            hass,
            datetime.now(UTC) - timedelta(days=1),
            entity_ids=[sensor_id],
            include_start_time_state=False,
            significant_changes_only=False,
            minimal_response=False,
            no_attributes=False,
        )
    )
    return result.get(sensor_id, [])


def preparation_record(timestamp, record_id, *, volume, temperature, powder):
    """Return synthetic creation-log wire data, including real string scalars."""
    return {
        "id": record_id,
        "completionTimestamp": str(timestamp),
        "volume": str(volume),
        "volumeUnit": "oz",
        "temperature": temperature,
        "powderSetting": powder,
        "waterOnly": False,
        "bottleId": None,
    }


def set_latest_details(payload, records):
    """Supply actual complete wire snapshots and logs; never touch Recorder."""
    newest = max(records, key=lambda item: int(item["completionTimestamp"]))
    payload["bottleCreationLog"] = deepcopy(records)
    shadow = payload["shadow"]
    shadow["version"] += 1
    shadow["timestamp"] = int(newest["completionTimestamp"]) + 1
    reported = shadow["state"]["reported"]
    reported["lastBottle"] = {
        key: (int(value) if key == "completionTimestamp" else value)
        for key, value in newest.items()
        if key not in {"id", "bottleId"}
    }
    metadata = shadow["metadata"]["reported"]["lastBottle"]
    for key in reported["lastBottle"]:
        metadata[key] = {"timestamp": int(newest["completionTimestamp"])}


def send_shadow(coordinator, patch):
    coordinator.receive_message(
        {
            "subject": "shadow-update",
            "body": {"deviceId": coordinator.device_id, **deepcopy(patch)},
        }
    )


async def test_recorder_stores_coherent_snapshots_without_duplicate_or_unrelated_churn(
    recorded_entry, hass, device_payload
):
    coordinator, api, sensor_id, recorder = recorded_entry
    initial = coordinator.data.preparation
    assert initial is not None
    rows = await committed_history(hass, recorder, sensor_id)
    assert len(rows) == 1
    assert rows[0].state == initial.completed_at.isoformat()
    assert rows[0].attributes["volume"] == initial.volume
    assert rows[0].attributes["temperature_setting"] == initial.temperature_setting
    assert rows[0].attributes["powder_setting"] == initial.powder_setting

    timestamp = int(initial.completed_at.timestamp()) + 60
    record = preparation_record(timestamp, 9011, volume=3, temperature=0, powder=4)
    set_latest_details(device_payload, [record, *device_payload["bottleCreationLog"]])
    # Current selected settings intentionally differ from the reported preparation.
    device_payload["shadow"]["state"]["reported"]["settings"].update(
        {"volume": 8, "temperature": 2, "powder": 7}
    )
    await coordinator.async_refresh()
    rows = await committed_history(hass, recorder, sensor_id)
    assert len(rows) == 2
    assert rows[1].state == datetime.fromtimestamp(timestamp, UTC).isoformat()
    assert {key: rows[1].attributes[key] for key in record_keys()} == {
        "record_id": 9011,
        "volume": 3,
        "volume_unit": "oz",
        "temperature_setting": 0,
        "powder_setting": 4,
        "water_only": False,
        "preset_id": None,
    }
    # The historical value keeps cloud time; the Recorder observation uses receipt time.
    assert rows[1].last_updated > datetime.fromtimestamp(timestamp, UTC)
    committed = [(row.state, dict(row.attributes), row.last_updated) for row in rows]

    send_shadow(coordinator, device_payload["shadow"])
    send_shadow(coordinator, device_payload["shadow"])
    send_shadow(coordinator, {"state": {"reported": {"settings": {"volume": 9}}}})
    # Renaming a preset, reconnecting, refreshing freshness, and diagnostic counters
    # are live/runtime changes, not properties of the historical preparation.
    device_payload["bottles"][0]["title"] = "Renamed preset"
    coordinator.runtime.record_operation(coordinator.device_id, "refresh", "success")
    coordinator.connection_changed(False)
    coordinator.connection_changed(True)
    await hass.async_block_till_done()
    rows = await committed_history(hass, recorder, sensor_id)
    assert [
        (row.state, dict(row.attributes), row.last_updated) for row in rows
    ] == committed
    api.start_bottle.assert_not_awaited()


def record_keys():
    return {
        "record_id",
        "volume",
        "volume_unit",
        "temperature_setting",
        "powder_setting",
        "water_only",
        "preset_id",
    }


async def test_recorder_reconnect_publishes_only_latest_missed_preparation(
    recorded_entry, hass, device_payload
):
    coordinator, api, sensor_id, recorder = recorded_entry
    initial = coordinator.data.preparation
    assert initial is not None
    timestamp = int(initial.completed_at.timestamp())
    coordinator.connection_changed(False)
    # Out-of-order returned logs model three preparations missed during an outage.
    missed = [
        preparation_record(timestamp + 10, 9011, volume=3, temperature=0, powder=4),
        preparation_record(timestamp + 30, 9013, volume=5, temperature=2, powder=6),
        preparation_record(timestamp + 20, 9012, volume=4, temperature=1, powder=5),
    ]
    set_latest_details(device_payload, missed)
    await async_wait_recording_done(hass)
    assert len(await committed_history(hass, recorder, sensor_id)) == 1
    coordinator.connection_changed(True)
    await hass.async_block_till_done()
    rows = await committed_history(hass, recorder, sensor_id)
    assert [row.state for row in rows] == [
        initial.completed_at.isoformat(),
        datetime.fromtimestamp(timestamp + 30, UTC).isoformat(),
    ]
    assert rows[-1].attributes["record_id"] == 9013
    assert rows[-1].attributes["volume"] == 5
    assert rows[-1].attributes["temperature_setting"] == 2
    assert rows[-1].attributes["powder_setting"] == 6
    assert rows[-1].attributes["preset_id"] is None
    assert len(rows) == 2
    api.start_bottle.assert_not_awaited()
