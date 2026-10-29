"""Fake-cloud tests: push/read races, no replay, guarded starts and lifecycle."""

import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fpa.api import AuthenticationError, CommandError, ConnectionError
from custom_components.fpa.coordinator import DeviceCoordinator, FpaRuntime


class FakeClient:
    def __init__(self, details):
        self.details = deepcopy(details)
        self.devices = [{key: details[key] for key in ("id", "deviceId", "title")}]
        self.refresh = AsyncMock()
        self.get_me = AsyncMock(return_value={"devices": self.devices})
        self.get_device_details = AsyncMock(
            side_effect=lambda _: deepcopy(self.details)
        )
        self.start_bottle = AsyncMock()
        self.subscribe = AsyncMock()
        self.close = AsyncMock()


@pytest.fixture
async def runtime(hass, device_payload):
    entry = MockConfigEntry(domain="fpa", data={"refresh_token": "synthetic"})
    entry.add_to_hass(hass)
    api = FakeClient(device_payload)
    runtime = FpaRuntime(hass, entry, api)
    entry.runtime_data = runtime
    await runtime.async_setup()
    device = next(iter(runtime.devices.values()))
    # Subscription owns transport; set connected without automatic reconnect read.
    device.transport_connected = True
    yield runtime
    await runtime.async_close()


def coordinator(runtime):
    return next(iter(runtime.devices.values()))


def push(device, reported, version=None, metadata=None):
    body = {"deviceId": device.device_id, "state": {"reported": reported}}
    if version is not None:
        body["version"] = version
    if metadata is not None:
        body["metadata"] = metadata
    device.receive_message({"subject": "shadow-update", "body": body})


def ready(runtime):
    device = coordinator(runtime)
    # The first fixture reports bottle absent. Replacement establishes known empty.
    runtime.api.details["shadow"]["state"]["reported"]["hardware"]["alerts"][
        "bottleMissing"
    ] = False
    push(device, {"hardware": {"alerts": {"bottleMissing": False}}})
    return device


async def test_setup_owns_one_subscription_and_unknown_selection(runtime):
    device = coordinator(runtime)
    assert len(runtime.devices) == 1
    assert device.selected_id is None
    assert device.data.preparation.record_id == 9010
    assert device.summary_state == "bottle_missing"
    assert device.presets[1004].temperature == 0
    runtime.api.subscribe.assert_awaited_once()
    assert device.update_interval is None
    assert not device.guard.occupied


async def test_selection_is_local_survives_rename_and_invalidates_deletion(runtime):
    device = coordinator(runtime)
    await device.async_select(1001)
    runtime.api.start_bottle.assert_not_awaited()
    assert runtime.storage.get(device.device_id)["selected_id"] == 1001
    runtime.api.details["bottles"][0]["title"] = "Renamed"
    await device.async_refresh()
    assert device.selected_id == 1001
    assert device.preset_options["Renamed"] == 1001
    runtime.api.details["bottles"] = runtime.api.details["bottles"][1:]
    await device._request_refresh("test")
    assert device.selected_id is None
    runtime.api.details["bottles"].append({"id": 1001, "title": "Returns"})
    await device._request_refresh("test")
    assert device.selected_id is None
    with pytest.raises(ServiceValidationError):
        await device.async_select(9999)


async def test_fresh_preflight_and_no_dropdown_change_for_legacy_start(runtime):
    device = ready(runtime)
    await device.async_select(1001)
    count = runtime.api.get_device_details.await_count
    await device.async_start(1002)
    assert runtime.api.get_device_details.await_count == count + 1
    runtime.api.start_bottle.assert_awaited_once_with(1002)
    assert device.selected_id == 1001
    assert device.guard.requested_preset_id == 1002
    assert device.summary_state == "requesting_bottle"
    assert runtime.storage.get(device.device_id)["guard"]["pending"] is True
    with pytest.raises(ServiceValidationError):
        await device.async_start(1002)
    runtime.api.start_bottle.assert_awaited_once()


@pytest.mark.parametrize(
    "field",
    [
        "bottleMissing",
        "funnelCleaningNeeded",
        "funnelOut",
        "lidOpen",
        "lowWater",
    ],
)
async def test_every_alert_blocks_both_start_paths(runtime, field):
    device = ready(runtime)
    await device.async_select(1001)
    runtime.api.details["shadow"]["state"]["reported"]["hardware"]["alerts"][field] = (
        True
    )
    with pytest.raises(ServiceValidationError):
        await device.async_start()
    with pytest.raises(ServiceValidationError):
        await device.async_start(1001)
    runtime.api.start_bottle.assert_not_awaited()


@pytest.mark.parametrize("field", ["tempHeating", "tempCooling"])
@pytest.mark.parametrize("preset_id", [None, 1001])
async def test_temperature_activity_alone_does_not_block_start(runtime, field, preset_id):
    device = ready(runtime)
    await device.async_select(1001)
    alerts = runtime.api.details["shadow"]["state"]["reported"]["hardware"]["alerts"]
    alerts[field] = True
    await device.async_start(preset_id)
    runtime.api.start_bottle.assert_awaited_once_with(1001)
    assert getattr(
        device.data.alerts, "heating" if field == "tempHeating" else "cooling"
    )


@pytest.mark.parametrize("field", ["tempHeating", "tempCooling"])
@pytest.mark.parametrize(
    "blocker",
    ["bottleMissing", "funnelCleaningNeeded", "funnelOut", "lidOpen", "lowWater"],
)
@pytest.mark.parametrize("preset_id", [None, 1001])
async def test_temperature_activity_does_not_bypass_other_alerts(
    runtime, field, blocker, preset_id
):
    device = ready(runtime)
    await device.async_select(1001)
    alerts = runtime.api.details["shadow"]["state"]["reported"]["hardware"]["alerts"]
    alerts[field] = alerts[blocker] = True
    with pytest.raises(ServiceValidationError):
        await device.async_start(preset_id)
    runtime.api.start_bottle.assert_not_awaited()


@pytest.mark.parametrize("field", ["tempHeating", "tempCooling"])
async def test_unknown_temperature_activity_still_blocks_start(runtime, field):
    device = ready(runtime)
    del runtime.api.details["shadow"]["state"]["reported"]["hardware"]["alerts"][field]
    with pytest.raises(ServiceValidationError):
        await device.async_start(1001)
    assert "readiness_unverified" in device.block_reasons
    runtime.api.start_bottle.assert_not_awaited()


async def test_missing_readiness_and_offline_block(runtime):
    device = ready(runtime)
    del runtime.api.details["shadow"]["state"]["reported"]["hardware"]["alerts"][
        "tempHeating"
    ]
    with pytest.raises(ServiceValidationError):
        await device.async_start(1001)
    assert device.data.alerts.heating is None
    assert "readiness_unverified" in device.block_reasons
    runtime.api.details["shadow"]["state"]["reported"]["connected"] = False
    with pytest.raises(ServiceValidationError):
        await device.async_start(1001)
    assert not device.available
    runtime.api.start_bottle.assert_not_awaited()


async def test_ownership_and_deleted_preset_block(runtime):
    device = ready(runtime)
    with pytest.raises(ServiceValidationError):
        await device.async_start(9999)
    with pytest.raises(ServiceValidationError):
        await device.async_start()
    runtime.api.start_bottle.assert_not_awaited()


async def test_concurrent_starts_only_send_once(runtime):
    device = ready(runtime)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow_start(_):
        entered.set()
        await release.wait()

    runtime.api.start_bottle.side_effect = slow_start
    first = asyncio.create_task(device.async_start(1001))
    await entered.wait()
    with pytest.raises(ServiceValidationError):
        await device.async_start(1002)
    release.set()
    await first
    assert runtime.api.start_bottle.await_count == 1


@pytest.mark.parametrize(
    "error,uncertain",
    [(ConnectionError("timeout"), True), (CommandError("rejected", 422), False)],
)
async def test_command_failure_never_replays_or_leaves_pending(
    runtime, error, uncertain
):
    device = ready(runtime)
    runtime.api.start_bottle.side_effect = error
    with pytest.raises(HomeAssistantError):
        await device.async_start(1001)
    assert not device.guard.pending
    assert device.guard.uncertain is uncertain
    assert runtime.api.start_bottle.await_count == 1
    assert not any(record.get("status") == "accepted" for record in runtime.operations)


async def test_observation_timeout_requires_removal_even_after_refresh(runtime):
    device = ready(runtime)
    await device.async_start(1001)
    device._command_timed_out()
    assert not device.guard.pending
    assert device.guard.uncertain
    assert device.summary_state == "bottle_check_needed"
    await device._request_refresh("test")
    assert device.guard.uncertain
    with pytest.raises(ServiceValidationError):
        await device.async_start(1001)
    runtime.api.start_bottle.assert_awaited_once()
    push(device, {"hardware": {"alerts": {"bottleMissing": True}}})
    push(device, {"hardware": {"alerts": {"bottleMissing": False}}})
    assert not device.guard.uncertain


async def test_external_completion_occupies_and_removal_clears(runtime):
    device = ready(runtime)
    bottle = deepcopy(runtime.api.details["shadow"]["state"]["reported"]["lastBottle"])
    bottle["completionTimestamp"] += 60
    push(device, {"lastBottle": bottle})
    assert device.guard.occupied
    assert device.summary_state == "full_bottle"
    await device._request_refresh("test")
    assert device.guard.occupied
    push(device, {"hardware": {"alerts": {"bottleMissing": True}}})
    assert not device.guard.occupied
    assert not device.guard.uncertain
    assert (
        device.data.preparation.completed_at.timestamp()
        == bottle["completionTimestamp"]
    )


async def test_push_start_observation_and_completion_transition(runtime):
    device = ready(runtime)
    await device.async_start(1001)
    push(device, {"settings": {"makingBottle": True}})
    assert not device.guard.pending
    assert device.summary_state == "making_bottle"
    push(device, {"settings": {"makingBottle": False}})
    assert device.guard.occupied
    assert device.summary_state == "full_bottle"


async def test_refresh_coalescing_cooldown_and_preflight_not_skipped(runtime):
    device = ready(runtime)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow_read(_):
        entered.set()
        await release.wait()
        return deepcopy(runtime.api.details)

    runtime.api.get_device_details.side_effect = slow_read
    before = runtime.api.get_device_details.await_count
    first = asyncio.create_task(device.async_refresh())
    await entered.wait()
    second = asyncio.create_task(device.async_refresh())
    release.set()
    await asyncio.gather(first, second)
    assert runtime.api.get_device_details.await_count == before + 1
    await device.async_refresh()
    assert runtime.api.get_device_details.await_count == before + 1
    await device.async_start(1001)
    assert runtime.api.get_device_details.await_count == before + 2


async def test_partial_new_completion_does_not_borrow_old_settings(runtime):
    device = coordinator(runtime)
    previous = device.data.preparation
    push(
        device,
        {
            "lastBottle": {
                "completionTimestamp": previous.completed_at.timestamp() + 100
            }
        },
    )
    assert device.data.preparation == previous
    assert (
        device.raw_shadow["state"]["reported"]["lastBottle"]["completionTimestamp"]
        != previous.completed_at.timestamp()
    )
    assert device._reconcile_task is not None


async def test_partial_completion_metadata_proves_coherence(runtime):
    device = coordinator(runtime)
    previous = device.data.preparation
    stamp = previous.completed_at.timestamp() + 100
    metadata = {
        "reported": {
            "lastBottle": {
                key: {"timestamp": stamp}
                for key in (
                    "completionTimestamp",
                    "volume",
                    "volumeUnit",
                    "temperature",
                    "powderSetting",
                    "waterOnly",
                )
            }
        }
    }
    push(device, {"lastBottle": {"completionTimestamp": stamp}}, metadata=metadata)
    assert device.data.preparation.completed_at.timestamp() == stamp
    assert device.data.preparation.volume == previous.volume


async def test_stale_push_kept_for_diagnostics_but_ignored_for_live(runtime):
    device = coordinator(runtime)
    runtime.capture_message = lambda machine, envelope: captured.append(
        deepcopy(envelope)
    )
    captured = []
    push(device, {"settings": {"volume": 9}}, version=device.data.shadow_version - 1)
    assert len(captured) == 1
    assert device.data.settings.volume == 2
    push(device, {"settings": {"volume": 9}}, version=device.data.shadow_version + 1)
    assert device.data.settings.volume == 9
    assert device.data.settings.powder == 5


async def test_newer_push_during_old_details_cannot_be_overwritten(runtime):
    device = coordinator(runtime)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow_read(_):
        result = deepcopy(runtime.api.details)
        entered.set()
        await release.wait()
        return result

    runtime.api.get_device_details.side_effect = slow_read
    task = asyncio.create_task(device.async_refresh())
    await entered.wait()
    push(device, {"settings": {"volume": 8}}, version=device.data.shadow_version + 1)
    release.set()
    await task
    assert device.data.settings.volume == 8


async def test_unknown_version_push_is_replayed_over_inflight_read(runtime):
    device = coordinator(runtime)

    async def interleaved(_):
        push(device, {"settings": {"volume": 8}})
        return deepcopy(runtime.api.details)

    runtime.api.get_device_details.side_effect = interleaved
    await device.async_refresh()
    assert device.data.settings.volume == 8


async def test_full_version_reset_opens_generation_but_old_manual_does_not(runtime):
    device = coordinator(runtime)
    runtime.api.details["shadow"]["version"] = 1
    runtime.api.details["shadow"]["state"]["reported"]["settings"]["volume"] = 8
    await device._request_refresh("manual")
    assert device.data.settings.volume == 2
    await device._request_refresh("reconnect")
    assert device.data.shadow_version == 1
    push(device, {"settings": {"volume": 9}}, version=2)
    assert device.data.settings.volume == 9


async def test_failed_refresh_retains_data_and_selection(runtime):
    device = coordinator(runtime)
    await device.async_select(1001)
    previous = device.data
    runtime.api.get_device_details.side_effect = ConnectionError("tls")
    with pytest.raises(HomeAssistantError):
        await device.async_refresh()
    assert device.data == previous
    assert device.selected_id == 1001
    assert device.last_error == "tls"


async def test_reconnect_latest_only_and_guard_uncertain(runtime):
    device = ready(runtime)
    original = device.data.preparation
    runtime.api.details["bottleCreationLog"].extend(
        [
            {
                **runtime.api.details["bottleCreationLog"][0],
                "id": 9990,
                "completionTimestamp": str(original.completed_at.timestamp() + 30),
            },
            {
                **runtime.api.details["bottleCreationLog"][0],
                "id": 9991,
                "completionTimestamp": str(original.completed_at.timestamp() + 60),
            },
        ]
    )
    device.connection_changed(False)
    assert not device.available
    assert device.guard.uncertain
    device.connection_changed(True)
    await device._request_refresh("reconnect")
    assert device.data.preparation.record_id == 9991
    changes = [op for op in runtime.operations if op["category"] == "preparation"]
    assert len(changes) == 2  # One setup observation, one newest reconnect observation.
    assert device.guard.occupied


async def test_restore_newer_history_does_not_regress(runtime):
    device = coordinator(runtime)
    previous = device.data.preparation
    newer = replace(
        previous,
        completed_at=previous.completed_at + timedelta(days=1),
        provenance="restored",
    )
    device.restore_preparation(newer)
    await device._request_refresh("manual")
    assert device.data.preparation == newer
    device.restore_preparation(previous)
    assert device.data.preparation == newer


async def test_capture_failure_unknown_subject_ownership_and_close(runtime):
    device = coordinator(runtime)

    def failed_capture(*_):
        raise ValueError("not exported")

    runtime.capture_message = failed_capture
    push(device, {"settings": {"volume": 8}})
    assert device.data.settings.volume == 8
    device.receive_message(
        {
            "subject": "shadow-update",
            "body": {
                "deviceId": "another-device",
                "state": {"reported": {"settings": {"volume": 99}}},
            },
        }
    )
    assert device.data.settings.volume == 8
    await runtime.async_close()
    previous = device.data
    push(device, {"settings": {"volume": 9}})
    assert device.data == previous
    assert not device.available
    assert not runtime._tasks
    runtime.api.close.assert_awaited_once()


async def test_storage_only_contains_guard_selection_and_local_funnel_counter(runtime):
    device = coordinator(runtime)
    await device.async_select(1001)
    stored = runtime.storage.get(device.device_id)
    assert set(stored) == {"selected_id", "guard", "funnel"}
    assert set(stored["guard"]) == {
        "pending",
        "occupied",
        "uncertain",
        "last_preparation",
    }
    second = DeviceCoordinator(runtime, runtime.api.devices[0])
    assert second.selected_id == 1001
    assert second.guard.uncertain
    assert not second.guard.pending
    assert second.data.preparation is None
    second.close()


async def test_guard_and_selection_changes_notify_listeners_without_state_change(
    runtime,
):
    device = ready(runtime)
    notifications = []
    unsubscribe = device.async_add_listener(
        lambda: notifications.append(device.selected_id)
    )
    state = device.data
    await device.async_select(1001)
    assert device.data == state
    assert notifications[-1] == 1001
    device.connection_changed(False)
    assert len(notifications) >= 2
    unsubscribe()


async def test_preflight_missing_shadow_cannot_use_old_cached_readiness(runtime):
    device = ready(runtime)
    state = device.data
    runtime.api.details.pop("shadow")
    with pytest.raises(HomeAssistantError):
        await device.async_start(1001)
    assert device.data == state
    assert device.last_error == "protocol"
    runtime.api.start_bottle.assert_not_awaited()


async def test_safety_push_during_guard_persistence_blocks_before_physical_write(
    runtime,
):
    device = ready(runtime)
    original_save = device._save
    writes = 0

    async def interleaved_save():
        nonlocal writes
        writes += 1
        await original_save()
        if writes == 1:
            push(device, {"hardware": {"alerts": {"lidOpen": True}}})

    device._save = interleaved_save
    with pytest.raises(ServiceValidationError):
        await device.async_start(1001)
    runtime.api.start_bottle.assert_not_awaited()
    assert not device.guard.pending
    assert device.data.alerts.lid_open


async def test_canceled_command_becomes_uncertain_and_is_not_replayed(runtime):
    device = ready(runtime)
    entered = asyncio.Event()

    async def pending_command(_):
        entered.set()
        await asyncio.Future()

    runtime.api.start_bottle.side_effect = pending_command
    task = asyncio.create_task(device.async_start(1001))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not device.guard.pending
    assert device.guard.uncertain
    assert not device._start_busy
    runtime.api.start_bottle.assert_awaited_once()


async def test_persisted_selection_loads_and_pending_never_replays(runtime):
    from custom_components.fpa.storage import FpaStorage

    device = ready(runtime)
    await device.async_select(1002)
    await device.async_start(1002)
    fresh = FpaStorage(runtime.hass, runtime.entry.entry_id)
    await fresh.async_load()
    saved = fresh.get(device.device_id)
    assert saved["selected_id"] == 1002
    assert saved["guard"]["pending"]
    runtime.storage = fresh
    restarted = DeviceCoordinator(runtime, runtime.api.devices[0])
    assert restarted.selected_id == 1002
    assert restarted.guard.uncertain
    assert not restarted.guard.pending
    runtime.api.start_bottle.assert_awaited_once()
    restarted.close()


async def test_metadata_discards_older_field_even_without_shadow_version(runtime):
    device = coordinator(runtime)
    original = device.raw_shadow["metadata"]["reported"]["settings"]["volume"][
        "timestamp"
    ]
    metadata = {"reported": {"settings": {"volume": {"timestamp": original - 1}}}}
    push(device, {"settings": {"volume": 99}}, metadata=metadata)
    assert device.data.settings.volume == 2
    assert (
        device.raw_shadow["metadata"]["reported"]["settings"]["volume"]["timestamp"]
        == original
    )


async def test_current_and_preset_changes_do_not_mutate_preparation_attributes(runtime):
    device = coordinator(runtime)
    previous = device.data.preparation
    attributes = previous.attributes
    push(device, {"settings": {"volume": 9, "temperature": 0, "powder": 2}})
    await device.async_select(1002)
    runtime.api.details["bottles"][1]["title"] = "Another name"
    await device.async_refresh()
    assert device.data.preparation == previous
    assert device.data.preparation.attributes == attributes


async def test_auth_failure_on_read_starts_reauth_and_preserves_cache(runtime):
    device = coordinator(runtime)
    previous = device.data
    # The HA method is a sync callback; use a sync mock to check dispatch.
    from unittest.mock import Mock

    runtime.entry.async_start_reauth = Mock()
    runtime.api.get_device_details.side_effect = AuthenticationError()
    with pytest.raises(HomeAssistantError):
        await device.async_refresh()
    assert device.data == previous
    assert not runtime.authenticated
    runtime.entry.async_start_reauth.assert_called_once_with(runtime.hass)


@pytest.mark.parametrize("value", [None, {}, "bad"])
async def test_preflight_requires_fresh_preset_list_and_preserves_display_cache(
    runtime, value
):
    device = ready(runtime)
    presets = device.presets
    runtime.api.details["bottles"] = value
    with pytest.raises(HomeAssistantError):
        await device.async_start(1001)
    assert device.presets == presets
    assert device.last_error == "protocol"
    runtime.api.start_bottle.assert_not_awaited()
    assert any(
        op["category"] == "refresh" and op["status"] == "failed"
        for op in runtime.operations
    )


async def test_malformed_read_identity_is_safe_recorded_failure(runtime):
    device = coordinator(runtime)
    runtime.api.details["deviceId"] = "another-device"
    previous = device.data
    with pytest.raises(HomeAssistantError):
        await device.async_refresh()
    assert device.data == previous
    assert device.last_error == "protocol"
    assert runtime.operations[-1]["category"] == "refresh"
    assert runtime.operations[-1]["status"] == "failed"


async def test_unload_cancels_and_awaits_inflight_start(runtime):
    device = ready(runtime)
    entered = asyncio.Event()

    async def long_command(_):
        entered.set()
        await asyncio.Future()

    runtime.api.start_bottle.side_effect = long_command
    caller = asyncio.create_task(device.async_start(1001))
    await entered.wait()
    await runtime.async_close()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert not device._command_tasks
    assert not device.guard.pending
    assert device.guard.uncertain
    assert runtime.storage.get(device.device_id)["guard"]["uncertain"]
    runtime.api.start_bottle.assert_awaited_once()
    runtime.api.close.assert_awaited_once()


async def test_partial_preparation_fields_complete_coherently_in_later_message(runtime):
    device = coordinator(runtime)
    previous = device.data.preparation
    stamp = previous.completed_at.timestamp() + 100
    push(
        device,
        {"lastBottle": {"completionTimestamp": stamp}},
        metadata={
            "reported": {"lastBottle": {"completionTimestamp": {"timestamp": stamp}}}
        },
    )
    assert device.data.preparation == previous
    values = {
        "volume": 4,
        "volumeUnit": "oz",
        "temperature": 0,
        "powderSetting": 6,
        "waterOnly": True,
    }
    for key, value in values.items():
        push(
            device,
            {"lastBottle": {key: value}},
            metadata={"reported": {"lastBottle": {key: {"timestamp": stamp}}}},
        )
    assert device.data.preparation.completed_at.timestamp() == stamp
    assert device.data.preparation.volume == 4
    assert device.data.preparation.temperature_setting == 0
    assert device.data.preparation.powder_setting == 6
    assert device.data.preparation.water_only is True


async def test_websocket_auth_failure_starts_reauth_once_even_without_reconnect(
    runtime,
):
    from unittest.mock import Mock

    device = coordinator(runtime)
    runtime.entry.async_start_reauth = Mock()
    callback = runtime.api.error_callback
    callback(device.device_id, AuthenticationError(status=401))
    assert not runtime.authenticated
    assert device.last_error == "authentication"
    runtime.entry.async_start_reauth.assert_called_once_with(runtime.hass)
    callback(device.device_id, AuthenticationError(status=403))
    runtime.entry.async_start_reauth.assert_called_once()
    assert any(
        op["category"] == "authentication" and op["status"] == "failed"
        for op in runtime.operations
    )
    await runtime.async_close()
    callback(device.device_id, AuthenticationError())
    runtime.entry.async_start_reauth.assert_called_once()


async def test_completion_enrichment_retries_once_and_then_stops(runtime, monkeypatch):
    device = coordinator(runtime)
    # A coherent raw completion remains publishable even when log enrichment fails.
    bottle = deepcopy(runtime.api.details["shadow"]["state"]["reported"]["lastBottle"])
    bottle["completionTimestamp"] += 100
    runtime.api.get_device_details.side_effect = ConnectionError("timeout")
    monkeypatch.setattr("custom_components.fpa.coordinator.COMPLETION_RETRY_DELAY", 0)
    before = runtime.api.get_device_details.await_count
    push(device, {"lastBottle": bottle})
    await device._reconcile_task
    assert runtime.api.get_device_details.await_count == before + 2
    assert (
        device.data.preparation.completed_at.timestamp()
        == bottle["completionTimestamp"]
    )
    assert device.data.preparation.record_id is None
    await asyncio.sleep(0)
    assert runtime.api.get_device_details.await_count == before + 2


async def test_distinct_known_record_at_equal_completion_time_marks_occupied(runtime):
    device = ready(runtime)
    previous = device.data.preparation
    assert not device.guard.occupied
    changed = deepcopy(runtime.api.details["bottleCreationLog"][0])
    changed["id"] += 1
    runtime.api.details["bottleCreationLog"].append(changed)
    await device._request_refresh("manual")
    assert device.data.preparation.completed_at == previous.completed_at
    assert device.data.preparation.record_id == previous.record_id + 1
    assert device.guard.occupied
    with pytest.raises(ServiceValidationError):
        await device.async_start(1001)
    runtime.api.start_bottle.assert_not_awaited()


async def test_same_time_missing_record_id_enrichment_does_not_reoccupy(runtime):
    device = ready(runtime)
    previous = device.data.preparation
    device.data = replace(
        device.data,
        preparation=replace(
            previous, record_id=None, preset_id=None, provenance="raw_snapshot"
        ),
    )
    assert not device.guard.occupied
    await device._request_refresh("manual")
    assert device.data.preparation == previous
    assert not device.guard.occupied
    assert not device.guard.uncertain


@pytest.mark.parametrize("status", [401, 403])
async def test_command_auth_rejection_requests_reauth_without_replaying_write(
    runtime, status
):
    from unittest.mock import Mock

    device = ready(runtime)
    runtime.entry.async_start_reauth = Mock()
    runtime.api.start_bottle.side_effect = AuthenticationError(status=status)
    reads_before = runtime.api.get_device_details.await_count
    with pytest.raises(HomeAssistantError) as raised:
        await device.async_start(1001)
    assert raised.value.translation_key == "command_failed"
    assert runtime.api.get_device_details.await_count == reads_before + 1
    runtime.api.start_bottle.assert_awaited_once_with(1001)
    runtime.api.refresh.assert_awaited_once()  # Setup only; no command retry/rotation.
    runtime.entry.async_start_reauth.assert_called_once_with(runtime.hass)
    assert not runtime.authenticated
    assert device.last_error == "authentication"
    assert not device.guard.pending
    assert not device.guard.uncertain  # Explicit HTTP rejection did not dispense.
    assert any(
        op["category"] == "start"
        and op["status"] == "rejected"
        and op["http_status"] == status
        for op in runtime.operations
    )
    # A second safe transport observation of the same failure must not open
    # duplicate reauthentication flows or replay the failed physical command.
    runtime.api.error_callback(device.device_id, AuthenticationError(status=status))
    runtime.entry.async_start_reauth.assert_called_once()
    runtime.api.start_bottle.assert_awaited_once()
