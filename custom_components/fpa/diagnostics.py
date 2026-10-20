"""Native cached diagnostics, isolated per entry/device and safe while offline."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .models import boolean, mapping, number
from .privacy import MAX_BYTES, MessageWindow, PrivacyContext

_REDACT_KEYS = {
    "password",
    "token",
    "refresh_token",
    "refreshToken",
    "Authorization",
    "authorization",
    "email",
    "cookie",
    "cookies",
    "sessionId",
    "url",
    "firstName",
    "lastName",
    "title",
    "name",
    "location",
}
_LIMITATIONS = [
    "Latest preparation only; no missed-record replay or lossless history guarantee.",
    "Operations (50/account) and messages (20 and 256 KiB/machine) are in memory; reload/restart clears them.",
    "Raw JSON preserves structure with field-aware redactions; unknown scalar values are redacted.",
    "Timestamps may reveal routines. Review before sharing. HA adds system/integration metadata; device download filenames may contain device names and registry IDs.",
]


def attach_diagnostics(runtime) -> None:
    """Attach capture before subscriptions start; no files, network or entities."""
    runtime.diagnostic_context = PrivacyContext()
    runtime.diagnostic_windows = {}

    def capture(device_id, envelope):
        context = runtime.diagnostic_context
        for identifier, device in runtime.devices.items():
            _seed_device(context, identifier, device)
        window = runtime.diagnostic_windows.setdefault(
            device_id, MessageWindow(context)
        )
        window.capture(envelope)

    runtime.capture_message = capture


def _seed_device(context, identifier, device):
    identity = mapping(getattr(device, "identity", {}))
    reported = mapping(mapping(device.raw_shadow.get("state")).get("reported"))
    return context.bind_device(
        identifier,
        identity.get("id"),
        identity.get("wifiMacAddress"),
        identity.get("bleMacAddress"),
        reported.get("wifiMacAddress"),
        reported.get("bleMacAddress"),
    )


def _plain(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in value]
    return value


def _category(value, allowed, fallback="unknown"):
    return value if value in allowed else fallback


def _unit(value):
    return value if value in ("oz", "ml", "mL", "fl oz") else None


def _time(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed.isoformat() if parsed.tzinfo else None
        except ValueError:
            pass
    return None


def _preparation(prep, context):
    return {
        "completed_at": prep.completed_at.isoformat(),
        "record_id": context.alias(prep.record_id, "record"),
        "preset_id": context.alias(prep.preset_id, "preset"),
        "volume": number(prep.volume),
        "volume_unit": _unit(prep.volume_unit),
        "temperature_setting": number(prep.temperature_setting),
        "powder_setting": number(prep.powder_setting),
        "water_only": boolean(prep.water_only),
        "provenance": _category(
            prep.provenance, {"raw_snapshot", "creation_record", "restored"}
        ),
    }


def _preset_discrepancies(preset):
    quantity = re.search(r"(?i)\b(\d+(?:\.\d+)?)\s*(oz|ml)\b", preset.title)
    volume_mismatch = None
    if (
        quantity
        and preset.volume_unit
        and quantity.group(2).lower() == preset.volume_unit.lower()
    ):
        volume_mismatch = number(quantity.group(1)) != preset.volume
    return {
        "title_volume_discrepancy": volume_mismatch,
        "title_water_mode_discrepancy": "water" in preset.title.lower()
        and preset.water_only is False,
    }


def _safe_operations(runtime, context, device_id):
    result = []
    for operation in list(getattr(runtime, "operations", []))[-50:]:
        item = _plain(operation)
        if not isinstance(item, dict) or (
            device_id is not None and item.get("device_id") != device_id
        ):
            continue
        result.append(
            {
                "time": _time(item.get("time") or item.get("timestamp")),
                "device": context.alias(item.get("device_id"), "device"),
                "category": _category(
                    item.get("category"),
                    {
                        "refresh",
                        "authentication",
                        "auth",
                        "connect",
                        "disconnect",
                        "connection",
                        "start",
                        "preparation",
                        "setup",
                        "reconnect",
                    },
                ),
                "status": _category(
                    item.get("status"),
                    {
                        "success",
                        "failed",
                        "failure",
                        "accepted",
                        "rejected",
                        "pending",
                        "timeout",
                        "indeterminate",
                        "connected",
                        "disconnected",
                        "observed",
                        "changed",
                        "observed_start",
                        "updated",
                    },
                ),
                "reason": _category(
                    item.get("reason"),
                    {
                        None,
                        "authentication",
                        "connection",
                        "timeout",
                        "tls",
                        "http",
                        "invalid_response",
                        "invalid_auth",
                        "network",
                        "unavailable",
                        "unknown_preset",
                        "selection_required",
                        "busy",
                        "pending",
                        "making_bottle",
                        "bottle_missing",
                        "funnel_cleaning_needed",
                        "funnel_out",
                        "lid_open",
                        "low_water",
                        "heating",
                        "cooling",
                        "occupied",
                        "uncertain",
                        "bottle_check_needed",
                        "unknown_safety",
                        "not_connected",
                        "observation_timeout",
                        "not_observed",
                        "command_failed",
                        "indeterminate",
                        "completed",
                        "setup",
                        "manual",
                        "preflight",
                        "reconnect",
                        "completion",
                        "completion_retry",
                        "occupied_bottle",
                        "request_pending",
                        "readiness_unverified",
                        "invalid_preset",
                        "preflight_failed",
                        "raw_snapshot",
                        "creation_record",
                        "api_error",
                        "protocol",
                        "command_rejected",
                        "closed",
                        "token_callback",
                        "authentication_failed",
                        "command_timeout",
                        "device_unavailable",
                    },
                ),
                "duration": item.get("duration")
                if isinstance(item.get("duration"), (float, int))
                else None,
                "http_status": item.get("http_status")
                if isinstance(item.get("http_status"), int)
                and 100 <= item["http_status"] <= 599
                else None,
            }
        )
    return result


def _snapshot(runtime, entry, device_id=None):
    # Aliases created for this download must not mutate even diagnostic runtime
    # state; capture owns its own in-memory context between messages.
    context = deepcopy(getattr(runtime, "diagnostic_context", PrivacyContext()))
    devices = getattr(runtime, "devices", {})
    report = {
        "schema_version": 1,
        "integration": {
            "version": "1.0.0",
            "client_origin": "joncar/pybabyfpa",
            "reviewed_client_version": "0.0.7",
            "client_revision": "8f91cdbc38025d753dcd437f15fedeea5c63253a",
            "distribution": "vendored-adaptation",
        },
        "entry": {
            "state": str(entry.state.value),
            "runtime_available": runtime is not None,
            "authenticated": bool(runtime.authenticated) if runtime else None,
            "options": {},
        },
        "devices": {},
        "limitations": list(_LIMITATIONS),
    }
    if runtime is None:
        report["limitations"].append(
            "Runtime is unavailable; no cached device observations exist."
        )
        return report
    for identifier, device in devices.items():
        _seed_device(context, identifier, device)
    for identifier, device in devices.items():
        if device_id is not None and identifier != device_id:
            continue
        alias = context.bind_device(identifier)
        data = device.data
        presets = list(device.presets.values())
        for preset in presets:
            context.alias(preset.id, "preset")
        prep = data.preparation
        prep_data = _preparation(prep, context) if prep else None
        shadow = context.sanitize(device.raw_shadow)
        size = len(json.dumps(shadow, ensure_ascii=True).encode())
        if size > MAX_BYTES:
            shadow = {
                "omitted": "merged_shadow_exceeds_byte_limit",
                "sanitized_bytes": size,
                "max_bytes": MAX_BYTES,
            }
        window = getattr(runtime, "diagnostic_windows", {}).get(identifier)
        messages = window.snapshot() if window else MessageWindow(context).snapshot()
        for update in messages["updates"]:
            if "payload" in update:
                update["payload"] = context.sanitize(
                    update["payload"], already_sanitized=True
                )
        guard = _plain(device.guard)
        # Only known guard semantics; no runtime internals or arbitrary strings.
        guard_data = (
            {
                k: guard.get(k)
                for k in (
                    "pending",
                    "occupied",
                    "uncertain",
                    "running",
                    "indeterminate",
                )
                if k in guard
            }
            if isinstance(guard, dict)
            else {}
        )
        guard_data["block_reasons"] = list(device.block_reasons)
        guard_data["requested_preset_id"] = context.alias(
            device.guard.requested_preset_id, "preset"
        )
        report["devices"][alias] = {
            "connection": {
                "transport_connected": device.transport_connected,
                "appliance_connected": data.connected,
                "last_successful_refresh": _time(device.last_refresh),
                "last_update": _time(device.last_update),
                "connected_at": _time(device.connected_at),
                "disconnected_at": _time(device.disconnected_at),
                "successful_connection_count": device.reconnect_count,
                "reconnect_attempt_count": getattr(
                    runtime.api, "reconnect_attempts", {}
                ).get(identifier)
                if isinstance(getattr(runtime.api, "reconnect_attempts", None), dict)
                else None,
                "last_error_category": _category(
                    device.last_error,
                    {
                        None,
                        "authentication",
                        "connection",
                        "timeout",
                        "tls",
                        "http",
                        "invalid_response",
                        "network",
                        "api_error",
                        "protocol",
                        "command_rejected",
                        "closed",
                        "token_callback",
                        "command_observation_timeout",
                    },
                ),
                "available": device.available,
            },
            "reported_state": {
                "settings": {
                    **_plain(data.settings),
                    "volume_unit": _unit(data.settings.volume_unit),
                },
                "alerts": _plain(data.alerts),
                "unknown_fields": [
                    key
                    for key, value in {
                        **_plain(data.settings),
                        **_plain(data.alerts),
                    }.items()
                    if value is None
                ],
                "shadow_version": data.shadow_version,
            },
            "latest_merged_shadow": shadow,
            "presets": {
                "count": len(presets),
                "selected": context.alias(device.selected_id, "preset"),
                "selected_valid": device.selected_id in device.presets,
                "items": [
                    {
                        "id": context.alias(p.id, "preset"),
                        "title": context.alias(p.id, "preset"),
                        "volume": p.volume,
                        "volume_unit": _unit(p.volume_unit),
                        "temperature": p.temperature,
                        "powder": p.powder,
                        "water_only": p.water_only,
                        "missing_formula_metadata": not any(p.formula.values())
                        if p.formula
                        else True,
                        "powder_metadata_discrepancy": number(p.formula.get("setting"))
                        not in (None, p.powder)
                        if p.formula
                        else False,
                        **_preset_discrepancies(p),
                    }
                    for p in presets
                ],
            },
            "last_preparation": prep_data,
            "command_guard": guard_data,
            "recent_operations": _safe_operations(runtime, context, identifier),
            "recent_websocket_updates": messages,
            "client_observations": _client_observations(device.raw_shadow),
        }
    if device_id is None:
        report["recent_operations"] = _safe_operations(runtime, context, None)
    # Defense in depth; field-aware sanitizer already processes every raw scalar.
    return async_redact_data(report, _REDACT_KEYS - {"title"})


def _client_observations(raw):
    reported = mapping(mapping(raw.get("state")).get("reported"))
    firmware = mapping(reported.get("firmware"))
    errors = mapping(mapping(reported.get("lastBottle")).get("errors"))
    return {
        "firmware": {
            "version": number(firmware.get("version")),
            "isUpdating": boolean(firmware.get("isUpdating")),
        },
        "last_bottle_errors": {
            key: boolean(errors.get(key))
            for key in (
                "powderMotor",
                "wheelMotor",
                "waterMeter",
                "tempSensor",
                "waterLevel",
                "hotWater",
                "lidOpened",
                "funnelRemoved",
            )
        },
    }


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry):
    """Return one cached account snapshot without any API side effects."""
    return _snapshot(getattr(entry, "runtime_data", None), entry)


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
):
    """Restrict to the selected machine; never fall back to all devices."""
    identifier = next(
        (value for domain, value in device.identifiers if domain == "fpa"), None
    )
    if identifier is None:
        report = _snapshot(None, entry)
        report["limitations"].append("Requested machine identity is unavailable.")
        return report
    return _snapshot(getattr(entry, "runtime_data", None), entry, identifier)
