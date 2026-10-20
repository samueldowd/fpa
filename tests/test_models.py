"""Normalization, immutable history and honest missing-data semantics."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from custom_components.fpa.models import (
    TEMPERATURE_STATES,
    deep_merge,
    latest_from_details,
    newest_preparation,
    normalize_presets,
    normalize_shadow,
    number,
    preparation_from_bottle,
    preset_options,
)


def test_actual_wire_values_and_historical_settings(device_payload):
    preparation = latest_from_details(device_payload)
    assert preparation.completed_at == datetime.fromtimestamp(1735732721, UTC)
    assert preparation.record_id == 9010
    assert preparation.preset_id == 1004
    assert preparation.volume == 2
    assert preparation.temperature_setting == 1  # Current preset 1004 is temperature 0.
    assert preparation.powder_setting == 5  # Current preset 1004 is powder 6.
    assert preparation.provenance == "creation_record"
    assert preparation.completed_at.tzinfo is UTC
    assert "provenance" not in preparation.attributes
    attributes = preparation.attributes
    attributes["volume"] = 999
    assert preparation.volume == 2
    with pytest.raises(FrozenInstanceError):
        preparation.volume = 99


def test_current_temperature_zero_and_unknown_are_distinct(device_payload):
    raw = device_payload["shadow"]
    raw["state"]["reported"]["settings"]["temperature"] = 0
    assert normalize_shadow(raw).settings.temperature == 0
    assert TEMPERATURE_STATES[0] == "room_temperature"
    raw["state"]["reported"]["settings"]["temperature"] = None
    assert normalize_shadow(raw).settings.temperature is None
    raw["state"]["reported"]["settings"]["temperature"] = 99
    assert normalize_shadow(raw).settings.temperature == 99
    assert TEMPERATURE_STATES.get(99) is None


def test_optional_missing_is_unknown_and_partial_null_is_explicit(device_payload):
    raw = device_payload["shadow"]
    del raw["state"]["reported"]["hardware"]["alerts"]["tempHeating"]
    assert normalize_shadow(raw).alerts.heating is None
    patch = {"state": {"reported": {"settings": {"temperature": None}}}}
    merged = deep_merge(raw, patch)
    assert normalize_shadow(merged).settings.temperature is None
    assert normalize_shadow(merged).settings.volume == 2
    assert raw["state"]["reported"]["settings"]["temperature"] == 1
    patch["state"]["reported"]["settings"]["temperature"] = 88
    assert normalize_shadow(merged).settings.temperature is None


@pytest.mark.parametrize(
    "value", [None, True, False, "NaN", float("inf"), {}, [], "bad"]
)
def test_invalid_numbers_are_unknown(value):
    assert number(value) is None


def test_log_order_and_duplicate_delivery_do_not_regress(device_payload):
    expected = latest_from_details(device_payload)
    device_payload["bottleCreationLog"].reverse()
    assert latest_from_details(device_payload) == expected
    old = deepcopy(device_payload)
    old["bottleCreationLog"] = old["bottleCreationLog"][:-1]
    old["shadow"]["state"]["reported"].pop("lastBottle")
    assert latest_from_details(old, expected) == expected
    assert latest_from_details(device_payload, expected) == expected


def test_matching_record_enrichment_and_equal_setting_next_preparation(device_payload):
    raw = device_payload["shadow"]["state"]["reported"]["lastBottle"]
    first = preparation_from_bottle(raw)
    enriched = latest_from_details(device_payload)
    assert newest_preparation(first, enriched) == enriched
    assert newest_preparation(enriched, first) == enriched
    raw["completionTimestamp"] += 1
    next_preparation = preparation_from_bottle(raw)
    assert newest_preparation(enriched, next_preparation) == next_preparation
    assert enriched.attributes["volume"] == next_preparation.attributes["volume"]
    assert enriched.completed_at != next_preparation.completed_at


@pytest.mark.parametrize(
    "missing",
    ["volume", "volumeUnit", "temperature", "powderSetting", "completionTimestamp"],
)
def test_incomplete_preparation_never_borrows_current_settings(device_payload, missing):
    raw = deepcopy(device_payload["shadow"]["state"]["reported"]["lastBottle"])
    raw.pop(missing)
    assert preparation_from_bottle(raw) is None


def test_presets_names_null_metadata_and_inconsistencies_preserved(device_payload):
    presets = normalize_presets(device_payload["bottles"])
    assert presets[1003].volume == 4
    assert presets[1003].powder == 4
    assert presets[1003].formula["setting"] == 5
    assert presets[1004].water_only is False
    assert "None" not in presets[1002].description
    assert "Room Temperature" in presets[1004].description
    with pytest.raises(TypeError):
        presets[1003].formula["setting"] = 999
    device_payload["bottles"][2]["formula"]["setting"] = 999
    assert presets[1003].formula["setting"] == 5


def test_duplicate_blank_and_suffix_lookalike_names_are_unambiguous(device_payload):
    bottles = device_payload["bottles"]
    bottles[0]["title"] = "Same"
    bottles[1]["title"] = "Same"
    bottles[2]["title"] = "Same [1001]"
    bottles[3]["title"] = "   "
    presets = normalize_presets(bottles)
    options = preset_options(presets)
    assert len(options) == 4
    assert set(options.values()) == {1001, 1002, 1003, 1004}
    assert options["Preset 1004"] == 1004
    assert preset_options(presets) == options


def test_older_metadata_without_state_leaf_does_not_regress_coherence(device_payload):
    from custom_components.fpa.models import ordered_shadow_merge

    raw = device_payload["shadow"]
    original = raw["metadata"]["reported"]["lastBottle"]["volume"]["timestamp"]
    patch = {
        "state": {"reported": {"settings": {"temperature": 0}}},
        "metadata": {
            "reported": {"lastBottle": {"volume": {"timestamp": original - 1}}}
        },
    }
    result = ordered_shadow_merge(raw, patch)
    assert (
        result["metadata"]["reported"]["lastBottle"]["volume"]["timestamp"] == original
    )
    assert result["state"]["reported"]["settings"]["temperature"] == 0
    assert raw["state"]["reported"]["settings"]["temperature"] == 1


def test_large_integer_preset_identity_is_never_rounded_through_float(device_payload):
    from custom_components.fpa.models import integer

    identifier = 2**63 - 1
    assert integer(identifier) == identifier
    assert integer(str(identifier)) == identifier
    device_payload["bottles"][0]["id"] = identifier
    assert normalize_presets(device_payload["bottles"])[identifier].id == identifier
