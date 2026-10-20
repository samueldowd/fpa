"""Prove raw-update retention boundaries and recursive privacy behavior."""

import json
from copy import deepcopy
from datetime import datetime

from custom_components.fpa.privacy import (
    MAX_BYTES,
    REDACTED,
    MessageWindow,
    PrivacyContext,
)


def message(sequence=1):
    return {
        "subject": "shadow-update",
        "body": {
            "deviceId": "PRIVATE_DEVICE_UUID",
            "version": sequence,
            "state": {
                "reported": {
                    "connected": True,
                    "settings": {"volume": 2},
                    "password": "SECRET_PASSWORD",
                    "extra": [
                        {
                            "accessToken": "SECRET_TOKEN",
                            "nested": {
                                "url": "https://SECRET_URL",
                                "unknown": "PRIVATE_CHILD",
                            },
                        }
                    ],
                }
            },
        },
    }


def test_premerge_copy_and_recursive_unknown_field_redaction():
    context = PrivacyContext()
    context.bind_device("PRIVATE_DEVICE_UUID")
    window = MessageWindow(context)
    original = message()
    source = deepcopy(original)
    window.capture(original)
    original["body"]["state"]["reported"]["settings"]["volume"] = 9
    snap = window.snapshot()
    payload = snap["updates"][0]["payload"]
    assert payload["body"]["state"]["reported"]["settings"] == {"volume": 2}
    assert "hardware" not in payload["body"]["state"]["reported"]
    assert payload["body"]["deviceId"] == "device_1"
    assert source["body"]["state"]["reported"]["password"] == "SECRET_PASSWORD"
    assert original["body"]["state"]["reported"]["password"] == "SECRET_PASSWORD"
    text = json.dumps(snap)
    assert all(
        token not in text
        for token in (
            "SECRET_PASSWORD",
            "SECRET_TOKEN",
            "SECRET_URL",
            "PRIVATE_CHILD",
            "PRIVATE_DEVICE_UUID",
        )
    )
    assert datetime.fromisoformat(snap["updates"][0]["received_at"]).tzinfo is not None
    assert context.sanitize(payload, already_sanitized=True) == payload


def test_duplicates_out_of_order_and_count_eviction():
    window = MessageWindow(PrivacyContext())
    for i in range(25):
        window.capture(message(100 - i))
    snap = window.snapshot()
    assert len(snap["updates"]) == 20
    assert snap["evicted"] == 5
    assert [x["sequence"] for x in snap["updates"]] == list(range(6, 26))
    assert snap["updates"][-1]["payload"]["body"]["version"] == 76
    before = deepcopy(snap)
    assert window.snapshot() == before  # export doesn't consume the window


def test_bytes_eviction_and_oversize_metadata_only():
    window = MessageWindow(PrivacyContext())
    for _ in range(10):
        value = message()
        value["body"]["rows"] = [{"volume": 12345}] * 4000
        window.capture(value)
    snap = window.snapshot()
    assert snap["retained_bytes"] <= MAX_BYTES
    assert snap["evicted"] > 0
    oversized = message()
    oversized["body"]["rows"] = [{"volume": 12345}] * 30000
    window.capture(oversized)
    last = window.snapshot()["updates"][-1]
    assert last["payload_omitted"] == "message_exceeds_byte_limit"
    assert "payload" not in last
    assert window.snapshot()["oversized"] == 1
    assert json.loads(json.dumps(window.snapshot()))


def test_unfamiliar_scalar_values_and_subjects_are_never_trusted():
    context = PrivacyContext()
    raw = {
        "subject": "wss://SECRET_SUBJECT",
        "unfamiliar": {"count": 7, "ok": True, "null": None},
        "volumeUnit": "SECRET_UNIT",
    }
    assert context.sanitize(raw) == {
        "subject": REDACTED,
        "unfamiliar": {"count": REDACTED, "ok": REDACTED, "null": None},
        "volumeUnit": REDACTED,
    }
    assert MessageWindow(context).snapshot()["empty_reason"]


def test_capture_failure_is_bounded_and_does_not_escape():
    value = message()
    value["body"]["loop"] = value
    window = MessageWindow(PrivacyContext())
    window.capture(value)
    assert window.failures == 1
    window.capture(message())
    assert len(window.entries) == 1


def test_raw_identifiers_resembling_aliases_are_not_trusted():
    context = PrivacyContext()
    raw = {"deviceId": "device_1", "userId": "account_987654321"}
    safe = context.sanitize(raw)
    assert safe["deviceId"] != raw["deviceId"]
    assert safe["userId"] != raw["userId"]
    assert context.sanitize(safe, already_sanitized=True) == safe
