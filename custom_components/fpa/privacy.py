"""Bounded, structure-preserving diagnostic copies. Never retain raw secrets."""

from __future__ import annotations

import json
import re
from collections import deque
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

REDACTED = "**REDACTED**"
MAX_MESSAGES = 20
MAX_BYTES = 256 * 1024
_KEY = re.compile(r"^[a-z][A-Za-z_0-9-]{0,63}$")
_BOOLEANS = {
    "connected",
    "makingBottle",
    "waterOnly",
    "lidOpen",
    "lowWater",
    "tempHeating",
    "bottleMissing",
    "tempCooling",
    "funnelCleaningNeeded",
    "funnelOut",
    "isUpdating",
    "powderMotor",
    "wheelMotor",
    "waterMeter",
    "tempSensor",
    "waterLevel",
    "hotWater",
    "lidOpened",
    "funnelRemoved",
}
_NUMBERS = {
    "temperature",
    "powder",
    "powderSetting",
    "volume",
    "version",
    "timestamp",
    "completionTimestamp",
}
_IDENTITIES = {
    "deviceId": "device",
    "device_id": "device",
    "wifiMacAddress": "device",
    "bleMacAddress": "device",
    "userId": "account",
    "accountId": "account",
    "bottleId": "preset",
    "preset_id": "preset",
    "record_id": "record",
    "id": "identifier",
}
_SETTINGS = {
    "temperature",
    "powder",
    "volume",
    "volumeUnit",
    "makingBottle",
    "waterOnly",
}
_ALERTS = {
    "lidOpen",
    "lowWater",
    "tempHeating",
    "bottleMissing",
    "tempCooling",
    "funnelCleaningNeeded",
    "funnelOut",
}
_ERRORS = {
    "powderMotor",
    "wheelMotor",
    "waterMeter",
    "tempSensor",
    "waterLevel",
    "hotWater",
    "lidOpened",
    "funnelRemoved",
}
_PREPARATION = {
    "volume",
    "volumeUnit",
    "temperature",
    "powderSetting",
    "waterOnly",
    "completionTimestamp",
}
_REPORTED_PATHS = (
    {("connected",)}
    | {("settings", field) for field in _SETTINGS}
    | {("hardware", "alerts", field) for field in _ALERTS}
    | {("lastBottle", field) for field in _PREPARATION}
    | {("lastBottle", "errors", field) for field in _ERRORS}
    | {("firmware", field) for field in ("version", "isUpdating")}
)


def _reviewed_path(path: tuple[str, ...], key: str) -> bool:
    """Approved names only carry approved values at known protocol locations."""
    location = tuple(part for part in (*path, key) if part)
    if location[:1] == ("body",):
        location = location[1:]
    if location in {("subject",), ("version",), ("timestamp",)}:
        return True
    if location[:2] == ("state", "reported"):
        return location[2:] in _REPORTED_PATHS
    if location[:2] == ("metadata", "reported") and location[-1:] == ("timestamp",):
        field = location[2:-1]
        return field in _REPORTED_PATHS or field in {
            ("userId",),
            ("wifiMacAddress",),
            ("bleMacAddress",),
            ("firmware", "location"),
        }
    return False


class PrivacyContext:
    """In-memory aliases with no reversible mapping included in exports."""

    def __init__(self) -> None:
        self._mapping: dict[tuple[str, str], str] = {}
        self._counters: dict[str, int] = {}

    def alias(self, value: Any, kind: str = "identifier") -> str | None:
        if value is None:
            return None
        key = (kind, str(value))
        if key not in self._mapping:
            self._counters[kind] = self._counters.get(kind, 0) + 1
            candidate = f"{kind}_{self._counters[kind]}"
            if candidate == str(value):
                self._counters[kind] += 1
                candidate = f"{kind}_{self._counters[kind]}"
            self._mapping[key] = candidate
        return self._mapping[key]

    def bind_device(self, device_id: str, *other_ids: Any) -> str:
        alias = self.alias(device_id, "device")
        for value in other_ids:
            if value is not None:
                self._mapping[("device", str(value))] = alias
                self._mapping[("identifier", str(value))] = alias
        return alias

    def sanitize(
        self,
        value: Any,
        key: str = "",
        path: tuple[str, ...] = (),
        *,
        already_sanitized: bool = False,
    ) -> Any:
        """Unknown scalars are redacted; explicit nulls/nesting remain visible."""
        if value is None:
            return None
        if isinstance(value, dict):
            return {
                k
                if isinstance(k, str) and _KEY.fullmatch(k)
                else "redacted_key": self.sanitize(
                    v,
                    k if isinstance(k, str) else "",
                    (*path, key),
                    already_sanitized=already_sanitized,
                )
                for k, v in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [
                self.sanitize(v, key, path, already_sanitized=already_sanitized)
                for v in value
            ]
        if key in _IDENTITIES:
            if already_sanitized and value in self._mapping.values():
                return value
            kind = _IDENTITIES[key]
            if key == "id":
                if any(part in {"lastBottle", "bottleCreationLog"} for part in path):
                    kind = "record"
                elif "bottles" in path:
                    kind = "preset"
            return self.alias(value, kind)
        if not _reviewed_path(path, key):
            return REDACTED
        if isinstance(value, bool):
            return value if key in _BOOLEANS else REDACTED
        if key in _NUMBERS and isinstance(value, (int, float, str)):
            if isinstance(value, str):
                if len(value) < 32 and re.fullmatch(r"-?\d+(\.\d+)?", value):
                    return value
            elif isinstance(value, int) or (
                value == value and abs(value) != float("inf")
            ):
                return value
        if key == "volumeUnit" and value in ("oz", "ml", "mL", "fl oz"):
            return value
        if key == "subject" and value == "shadow-update":
            return value
        return REDACTED


class MessageWindow:
    """Last 20 sanitized pre-merge JSON updates, at most 256 KiB."""

    def __init__(self, context: PrivacyContext) -> None:
        self.context = context
        self.entries: deque[tuple[dict, int]] = deque()
        self.sequence = 0
        self.bytes = 0
        self.evicted = 0
        self.oversized = 0
        self.failures = 0

    def capture(self, envelope: dict) -> None:
        self.sequence += 1
        try:
            payload = self.context.sanitize(deepcopy(envelope))
            entry = {
                "sequence": self.sequence,
                "received_at": datetime.now(UTC).isoformat(),
                "subject": "shadow-update"
                if envelope.get("subject") == "shadow-update"
                else REDACTED,
                "payload": payload,
            }
            size = len(json.dumps(entry, ensure_ascii=True, allow_nan=False).encode())
            if size > MAX_BYTES:
                self.oversized += 1
                entry.pop("payload")
                entry.update(
                    payload_omitted="message_exceeds_byte_limit", sanitized_bytes=size
                )
                size = len(json.dumps(entry).encode())
            while self.entries and (
                len(self.entries) >= MAX_MESSAGES or self.bytes + size > MAX_BYTES
            ):
                _, removed = self.entries.popleft()
                self.bytes -= removed
                self.evicted += 1
            self.entries.append((entry, size))
            self.bytes += size
        except (TypeError, ValueError, RecursionError, OverflowError):
            self.failures += 1

    def snapshot(self) -> dict:
        return {
            "max_count": MAX_MESSAGES,
            "max_bytes": MAX_BYTES,
            "retained_bytes": self.bytes,
            "evicted": self.evicted,
            "oversized": self.oversized,
            "capture_failures": self.failures,
            "empty_reason": "no_updates_received_since_entry_load"
            if not self.entries
            else None,
            "updates": deepcopy([entry for entry, _ in self.entries]),
        }
