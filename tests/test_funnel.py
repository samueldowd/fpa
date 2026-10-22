"""Local funnel counter behavior, real HA entities, and durable deduplication."""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

import pytest

from custom_components.fpa.coordinator import DeviceCoordinator
from custom_components.fpa.funnel import FunnelCounter
from custom_components.fpa.storage import FpaStorage

from . import test_entities

configured = test_entities.configured
entity_id = test_entities.entity_id


def push(coordinator, reported):
    coordinator.receive_message(
        {
            "subject": "shadow-update",
            "body": {
                "deviceId": coordinator.device_id,
                "state": {"reported": reported},
            },
        }
    )


def completion(coordinator, *, seconds=1, record_id=None):
    bottle = deepcopy(coordinator.raw_shadow["state"]["reported"]["lastBottle"])
    bottle["completionTimestamp"] = (
        coordinator.data.preparation.completed_at.timestamp() + seconds
    )
    if record_id is not None:
        bottle["id"] = record_id
    else:
        bottle.pop("id", None)
    return {"lastBottle": bottle}


async def test_allowance_bounds_resets_and_api_alert_independence(hass, configured):
    _, api, coordinator = configured
    counter_id = entity_id(hass, coordinator, "sensor", "funnel_bottles_remaining")
    cleaning_id = entity_id(
        hass, coordinator, "binary_sensor", "funnel_cleaning_needed"
    )
    removed_id = entity_id(hass, coordinator, "binary_sensor", "funnel_out")
    reset_id = entity_id(hass, coordinator, "button", "reset_funnel_counter")
    assert hass.states.get(counter_id).state == "4"
    assert hass.states.get(cleaning_id).state == "off"
    assert hass.states.get(removed_id).state == "off"

    for expected in (3, 2, 1, 0, 0):
        reported = completion(coordinator)
        reported["lastBottle"]["waterOnly"] = expected == 3
        push(coordinator, reported)
        await hass.async_block_till_done()
        assert hass.states.get(counter_id).state == str(expected)
        push(coordinator, reported)
        await hass.async_block_till_done()
        assert hass.states.get(counter_id).state == str(expected)
    assert hass.states.get(cleaning_id).state == "off"
    assert "funnel_cleaning_needed" not in coordinator.block_reasons

    push(coordinator, {"hardware": {"alerts": {"funnelCleaningNeeded": True}}})
    await hass.async_block_till_done()
    assert hass.states.get(cleaning_id).state == "on"
    assert hass.states.get(counter_id).state == "0"

    push(coordinator, {"hardware": {"alerts": {"funnelOut": True}}})
    await hass.async_block_till_done()
    assert hass.states.get(removed_id).state == "on"
    assert hass.states.get(counter_id).state == "4"
    assert hass.states.get(cleaning_id).state == "on"
    push(coordinator, completion(coordinator))
    await hass.async_block_till_done()
    assert hass.states.get(counter_id).state == "3"
    push(coordinator, {"hardware": {"alerts": {"funnelOut": True}}})
    await hass.async_block_till_done()
    assert hass.states.get(counter_id).state == "3"

    coordinator.connection_changed(False)
    await hass.async_block_till_done()
    assert hass.states.get(counter_id).state == "3"
    assert hass.states.get(reset_id).state != "unavailable"
    reads = api.get_device_details.await_count
    await hass.services.async_call(
        "button", "press", {"entity_id": reset_id}, blocking=True
    )
    assert hass.states.get(counter_id).state == "4"
    assert coordinator.data.alerts.funnel_cleaning_needed is True
    assert api.get_device_details.await_count == reads
    api.start_bottle.assert_not_awaited()


async def test_counter_survives_reload_without_recounting_history(hass, configured):
    entry, _, coordinator = configured
    counter_id = entity_id(hass, coordinator, "sensor", "funnel_bottles_remaining")
    latest = completion(coordinator)
    push(coordinator, latest)
    await hass.async_block_till_done()
    assert hass.states.get(counter_id).state == "3"
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    restarted = entry.runtime_data.devices[coordinator.device_id]
    assert hass.states.get(counter_id).state == "3"
    push(restarted, latest)
    await hass.async_block_till_done()
    assert hass.states.get(counter_id).state == "3"
    push(restarted, completion(restarted, seconds=2))
    await hass.async_block_till_done()
    assert hass.states.get(counter_id).state == "2"
    await restarted.async_reset_funnel()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(counter_id).state == "4"


async def test_completion_enrichment_and_reset_replays_do_not_count(hass, configured):
    _, _, coordinator = configured
    counter_id = entity_id(hass, coordinator, "sensor", "funnel_bottles_remaining")
    push(coordinator, completion(coordinator))
    await hass.async_block_till_done()
    assert hass.states.get(counter_id).state == "3"
    enriched = completion(coordinator, seconds=0, record_id=9991)
    push(coordinator, enriched)
    await hass.async_block_till_done()
    assert hass.states.get(counter_id).state == "3"
    await coordinator.async_reset_funnel()
    push(coordinator, enriched)
    await hass.async_block_till_done()
    assert hass.states.get(counter_id).state == "4"
    push(coordinator, completion(coordinator, seconds=0, record_id=9992))
    await hass.async_block_till_done()
    assert hass.states.get(counter_id).state == "3"


async def test_manual_reset_is_device_local(hass, configured):
    _, api, coordinator = configured
    push(coordinator, completion(coordinator))
    await hass.async_block_till_done()
    assert coordinator.funnel.remaining == 3
    other = DeviceCoordinator(
        coordinator.runtime,
        {**coordinator.identity, "deviceId": "second-machine"},
    )
    other.funnel.remaining = 1
    await coordinator.async_reset_funnel()
    assert coordinator.funnel.remaining == 4
    assert other.funnel.remaining == 1
    assert (
        coordinator.runtime.storage.get(coordinator.device_id)["funnel"]["remaining"]
        == 4
    )
    assert coordinator.runtime.storage.get(other.device_id) == {}
    other.close()
    api.start_bottle.assert_not_awaited()


@pytest.mark.parametrize(
    "remaining,expected", [(-10, 0), (10, 4), (None, 4), (True, 4), ("bad", 4), (2, 2)]
)
async def test_storage_load_clamps_counter(hass, remaining, expected):
    storage = FpaStorage(hass, "counter-test")
    with patch.object(
        storage._store,
        "async_load",
        return_value={"devices": {"one": {"funnel": {"remaining": remaining}}}},
    ):
        await storage.async_load()
    assert storage.get("one")["funnel"]["remaining"] == expected
    assert FunnelCounter.from_storage(storage.get("missing")).remaining == 4


async def test_cursor_without_initial_history_and_unknown_removal(hass, configured):
    _, _, coordinator = configured
    counter = FunnelCounter()
    counter.observe(None, False, initialize=True)
    preparation = coordinator.data.preparation
    counter.observe(preparation, False)
    assert counter.remaining == 3
    counter.observe(preparation, True)
    assert counter.remaining == 4
    newer = replace(
        preparation, completed_at=preparation.completed_at + timedelta(seconds=1)
    )
    counter.observe(newer, None)
    assert counter.remaining == 3
    counter.observe(newer, True)
    assert counter.remaining == 3
    counter.observe(newer, False)
    counter.observe(newer, True)
    assert counter.remaining == 4
    # Historical data and stale completions cannot consume a new allowance.
    counter.observe(preparation, False)
    assert counter.remaining == 4


async def test_record_cursor_does_not_carry_id_to_new_anonymous_completion(
    hass, configured
):
    _, _, coordinator = configured
    previous = coordinator.data.preparation
    counter = FunnelCounter()
    counter.observe(previous, False, initialize=True)
    newer = replace(
        previous,
        completed_at=previous.completed_at + timedelta(seconds=1),
        record_id=None,
    )
    counter.observe(newer, False)
    assert counter.remaining == 3
    assert counter.record_id is None
    counter.observe(replace(newer, record_id=9993), False)
    assert counter.remaining == 3
