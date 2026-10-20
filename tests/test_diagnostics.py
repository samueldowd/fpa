"""Native HTTP download privacy, isolation, bounded snapshots and no writes."""

import json
import os
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fpa.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)


class FakeApi:
    """Offline API; every operation accounted so downloads cannot hide reads."""

    def __init__(self, payloads):
        self.payloads = {d["deviceId"]: deepcopy(d) for d in payloads}
        self.reads = 0
        self.writes = 0
        self.listeners = {}

    async def refresh(self, token):
        pass

    async def get_me(self):
        return {
            "devices": [
                {k: d[k] for k in ("deviceId", "id", "title")}
                for d in self.payloads.values()
            ]
        }

    async def get_device_details(self, device_id):
        self.reads += 1
        return deepcopy(self.payloads[device_id])

    async def start_bottle(self, preset_id):
        self.writes += 1
        raise AssertionError("diagnostics must never dispense")

    async def subscribe(self, device_id, callback, connection):
        self.listeners[device_id] = (callback, connection)
        connection(True)

    async def close(self):
        self.listeners.clear()


@pytest.fixture
async def loaded(hass, device_payload):
    other = deepcopy(device_payload)
    other.update(deviceId="PRIVATE_OTHER_UUID", title="PRIVATE_OTHER_TITLE", id=202)
    other.update(wifiMacAddress="020000000003", bleMacAddress="020000000004")
    other["shadow"]["state"]["reported"].update(
        wifiMacAddress="020000000003", bleMacAddress="020000000004"
    )
    for bottle in other["bottles"]:
        bottle["id"] += 10000
    device_payload = deepcopy(device_payload)
    device_payload["title"] = "PRIVATE_DEVICE_TITLE"
    device_payload["shadow"]["state"]["reported"].update(
        {
            "userId": "PRIVATE_ACCOUNT_ID",
            "email": "PRIVATE_EMAIL@example.test",
            "nested": [
                {
                    "authorization": "SECRET_AUTH",
                    "unfamiliar": {
                        "name": "PRIVATE_CHILD",
                        "token": "SECRET_NESTED_TOKEN",
                    },
                }
            ],
        }
    )
    device_payload["bottles"][0]["title"] = "PRIVATE_PRESET_TITLE"
    api = FakeApi([device_payload, other])
    entry = MockConfigEntry(
        domain="fpa",
        title="PRIVATE_ENTRY_TITLE",
        data={"refresh_token": "SECRET_REFRESH_TOKEN"},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.fpa.FpaClient", return_value=api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry, api, device_payload
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def test_entry_device_native_download_full_body_and_framework_filename(
    hass, hass_client, loaded, caplog
):
    entry, api, source = loaded
    runtime = entry.runtime_data
    device_id = source["deviceId"]
    coordinator = runtime.devices[device_id]
    envelope = {
        "subject": "shadow-update",
        "body": {
            "deviceId": device_id,
            "version": 351709,
            "state": {
                "reported": {
                    "settings": {"temperature": 0},
                    "secret": "SECRET_WS",
                    "url": "wss://example.test/?Authorization=SECRET_SOCKET_URL",
                    "title": "PRIVATE_MESSAGE_TITLE",
                }
            },
        },
    }
    coordinator.receive_message(envelope)
    runtime.record_operation(device_id, "start", "rejected", "bottle_missing")
    before = (
        api.reads,
        api.writes,
        deepcopy(coordinator.raw_shadow),
        deepcopy(envelope),
    )
    aliases_before = deepcopy(runtime.diagnostic_context._mapping)
    assert await async_setup_component(hass, "diagnostics", {})
    await hass.async_block_till_done()
    client = await hass_client()
    response = await client.get(f"/api/diagnostics/config_entry/{entry.entry_id}")
    assert response.status == 200
    downloaded = await response.json()
    text = json.dumps(downloaded)
    for sentinel in (
        "PRIVATE_ENTRY_TITLE",
        "PRIVATE_DEVICE_TITLE",
        "PRIVATE_OTHER_TITLE",
        "PRIVATE_OTHER_UUID",
        "PRIVATE_ACCOUNT_ID",
        "PRIVATE_CHILD",
        "PRIVATE_EMAIL",
        "PRIVATE_PRESET_TITLE",
        "PRIVATE_MESSAGE_TITLE",
        "SECRET_AUTH",
        "SECRET_NESTED_TOKEN",
        "SECRET_REFRESH_TOKEN",
        "SECRET_WS",
        "SECRET_SOCKET_URL",
        device_id,
    ):
        assert sentinel not in text
        assert sentinel not in caplog.text
    report = downloaded["data"]
    assert report["schema_version"] == 1
    assert len(report["devices"]) == 2
    data = next(
        d
        for d in report["devices"].values()
        if d["reported_state"]["settings"]["temperature"] == 0
    )
    raw = data["recent_websocket_updates"]["updates"][0]["payload"]
    assert raw["body"]["state"]["reported"]["settings"] == {"temperature": 0}
    assert data["latest_merged_shadow"]["state"]["reported"]["settings"]["volume"] == 2
    assert data["presets"]["selected_valid"] is False
    assert data["presets"]["items"][2]["title_volume_discrepancy"] is True
    assert data["presets"]["items"][2]["powder_metadata_discrepancy"] is True
    assert data["presets"]["items"][3]["title_water_mode_discrepancy"] is True
    assert data["recent_operations"][-1]["reason"] == "bottle_missing"
    assert "home_assistant" in downloaded and "integration_manifest" in downloaded
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", "fpa", device_id)
    device = dr.async_get(hass).async_get(registry.async_get(entity_id).device_id)
    response = await client.get(
        f"/api/diagnostics/config_entry/{entry.entry_id}/device/{device.id}"
    )
    assert response.status == 200
    # HA, not our hook, builds a filename from the real device name/registry ID.
    assert "PRIVATE_DEVICE_TITLE" in response.headers["Content-Disposition"]
    device_download = await response.json()
    assert len(device_download["data"]["devices"]) == 1
    assert "PRIVATE_" not in json.dumps(device_download)
    assert (api.reads, api.writes, coordinator.raw_shadow, envelope) == before
    assert runtime.diagnostic_context._mapping == aliases_before
    if directory := os.environ.get("FPA_EVIDENCE_DIR"):
        # Test evidence only; the production diagnostics hook never writes files.
        (Path(directory) / "representative-native-diagnostics.json").write_text(
            json.dumps(downloaded, indent=2) + "\n"
        )


async def test_offline_snapshot_isolated_unknown_owner_and_missing_runtime(
    hass, loaded
):
    entry, api, source = loaded
    runtime = entry.runtime_data
    chosen = runtime.devices[source["deviceId"]]
    other = runtime.devices["PRIVATE_OTHER_UUID"]
    chosen.connection_changed(False)
    runtime.capture_message(
        other.device_id,
        {
            "subject": "shadow-update",
            "body": {"deviceId": other.device_id, "version": 42},
        },
    )
    before = api.reads
    isolated = await async_get_device_diagnostics(
        hass, entry, SimpleNamespace(identifiers={("fpa", chosen.device_id)})
    )
    assert len(isolated["devices"]) == 1
    assert "PRIVATE_OTHER" not in json.dumps(isolated)
    machine = next(iter(isolated["devices"].values()))
    assert machine["connection"]["transport_connected"] is False
    assert machine["last_preparation"] is not None
    assert machine["recent_websocket_updates"]["empty_reason"]
    empty = await async_get_device_diagnostics(
        hass, entry, SimpleNamespace(identifiers={("other", chosen.device_id)})
    )
    assert empty["devices"] == {}
    missing = MockConfigEntry(domain="fpa", data={"refresh_token": "SECRET_UNLOADED"})
    report = await async_get_config_entry_diagnostics(hass, missing)
    assert report["entry"]["runtime_available"] is False
    assert "SECRET_UNLOADED" not in json.dumps(report)
    assert api.reads == before


async def test_buffer_reconnect_preserved_close_clears(hass, loaded):
    entry, api, source = loaded
    runtime = entry.runtime_data
    device = runtime.devices[source["deviceId"]]
    for version in (351710, 351709, 351709):
        device.receive_message(
            {
                "subject": "shadow-update",
                "body": {
                    "deviceId": device.device_id,
                    "version": version,
                    "state": {"reported": {"connected": True}},
                },
            }
        )
    device.receive_message(
        {
            "subject": "unknown_PRIVATE_SUBJECT",
            "body": {"deviceId": device.device_id, "unknown": "PRIVATE_FREE_TEXT"},
        }
    )
    window = runtime.diagnostic_windows[device.device_id]
    before = window.snapshot()
    assert [v["payload"]["body"].get("version") for v in before["updates"]] == [
        351710,
        351709,
        351709,
        None,
    ]
    device.connection_changed(False)
    device.connection_changed(True)
    await hass.async_block_till_done()
    assert window.snapshot() == before
    await runtime.async_close()
    assert runtime.diagnostic_windows == {}


async def test_oversized_merged_shadow_is_valid_json_omission(hass, loaded):
    entry, api, source = loaded
    device = entry.runtime_data.devices[source["deviceId"]]
    device._raw_shadow["rows"] = [{"volume": 12345}] * 30000
    report = await async_get_config_entry_diagnostics(hass, entry)
    shadow = next(iter(report["devices"].values()))["latest_merged_shadow"]
    assert shadow["omitted"] == "merged_shadow_exceeds_byte_limit"
    assert json.loads(json.dumps(report))


async def test_explicit_null_and_private_units_do_not_crash_or_leak(hass, loaded):
    from dataclasses import replace

    entry, api, source = loaded
    device = entry.runtime_data.devices[source["deviceId"]]
    original = device.data
    device._raw_shadow["state"] = None
    device.data = replace(
        original,
        settings=replace(original.settings, volume_unit="PRIVATE_UNIT"),
        preparation=replace(original.preparation, volume_unit="PRIVATE_HISTORY_UNIT"),
    )
    report = await async_get_config_entry_diagnostics(hass, entry)
    assert "PRIVATE_" not in json.dumps(report)
    assert (
        next(iter(report["devices"].values()))["client_observations"]["firmware"][
            "version"
        ]
        is None
    )


async def test_device_aliases_consistent_across_raw_and_normalized(hass, loaded):
    entry, api, source = loaded
    report = await async_get_config_entry_diagnostics(hass, entry)
    alias, data = next(iter(report["devices"].items()))
    raw = data["latest_merged_shadow"]["state"]["reported"]
    assert raw["wifiMacAddress"] == alias
    assert raw["bleMacAddress"] == alias
    assert data["last_preparation"]["record_id"].startswith("record_")
