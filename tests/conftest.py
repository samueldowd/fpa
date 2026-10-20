"""Shared sanitized fixtures and isolated Home Assistant setup."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading this local integration in isolated HA only."""
    yield


@pytest.fixture
def reference():
    return json.loads((Path(__file__).parent / "fixtures/reference.json").read_text())


def wire_device(reference, index=0):
    """Reconstruct vendor wire shape; the supplied export isn't a REST response."""
    source = deepcopy(reference["devices"][index])
    mapping = {
        "device_id": "deviceId", "wifi_mac_address": "wifiMacAddress",
        "ble_mac_address": "bleMacAddress", "volume_unit": "volumeUnit",
        "water_only": "waterOnly", "bottle_creation_log": "bottleCreationLog",
        "bottle_id": "bottleId", "powder_setting": "powderSetting",
        "completion_timestamp": "completionTimestamp",
    }

    def convert(value):
        if isinstance(value, dict):
            return {mapping.get(k, k): convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [convert(v) for v in value]
        return value

    raw_shadow = source.pop("raw_shadow")
    source.pop("shadow")
    result = convert(source)
    result["shadow"] = raw_shadow
    return result


@pytest.fixture
def device_payload(reference):
    return wire_device(reference)


@pytest.fixture
def identity(device_payload):
    return {k: device_payload[k] for k in ("id", "deviceId", "title", "wifiMacAddress", "bleMacAddress")}
