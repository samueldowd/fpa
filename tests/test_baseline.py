"""Trace the supplied sanitized export to actual vendor payloads."""


def test_fixture_reconstructs_wire_protocol(device_payload):
    assert device_payload["deviceId"] == "00000000-0000-4000-8000-000000000001"
    assert "raw_shadow" not in device_payload
    assert (
        device_payload["shadow"]["state"]["reported"]["hardware"]["alerts"][
            "tempHeating"
        ]
        is False
    )
    assert device_payload["bottleCreationLog"][0]["completionTimestamp"] == "1735732721"
    assert device_payload["bottleCreationLog"][6]["bottleId"] is None


def test_fixture_preserves_inconsistencies_without_guessing(device_payload):
    misleading = device_payload["bottles"][2]
    assert misleading["title"] == "Preset 3 oz"
    assert misleading["volume"] == 4
    assert misleading["powder"] == 4
    assert misleading["formula"]["setting"] == 5
    water = device_payload["bottles"][3]
    assert water["temperature"] == 0
    assert water["waterOnly"] is False
    assert all(v is None for v in water["formula"].values())
