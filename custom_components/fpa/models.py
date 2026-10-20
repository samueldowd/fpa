"""Immutable interpretation of reported cloud data; no Home Assistant dependency."""

from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

TEMPERATURE_STATES = {
    0: "room_temperature",
    1: "body_temperature",
    2: "above_body_temperature",
}
TEMPERATURE_LABELS = {
    0: "Room Temperature",
    1: "Body Temperature",
    2: "Above Body Temperature",
}


def number(value: Any) -> int | float | None:
    """Normalize real numeric wire values, excluding booleans and non-finite values."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(result):
        return None
    return int(result) if result.is_integer() else result


def integer(value: Any) -> int | None:
    result = number(value)
    return result if isinstance(result, int) else None


def boolean(value: Any) -> bool | None:
    """Unknown/null are never implicitly false; accept only actual JSON booleans."""
    return value if isinstance(value, bool) else None


def epoch(value: Any) -> datetime | None:
    result = number(value)
    if result is None or result <= 0:
        return None
    try:
        return datetime.fromtimestamp(result, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def mapping(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def deep_merge(base: Mapping, patch: Mapping) -> dict:
    """Merge dictionaries defensively; explicit null replaces rather than deletes."""
    merged = deepcopy(dict(base))
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def ordered_shadow_merge(base: Mapping, patch: Mapping) -> dict:
    """Reject older per-field shadow metadata, even without envelope versions.

    Unknown metadata does not invent an order. Envelope versions are checked by
    the coordinator before this helper is called.
    """
    filtered = deepcopy(dict(patch))
    old_metadata = mapping(base.get("metadata"))
    new_metadata = mapping(filtered.get("metadata"))

    def prune(values: dict, incoming_metadata: dict, previous_metadata: dict) -> None:
        for key in list(values):
            value = values[key]
            incoming = mapping(incoming_metadata.get(key))
            previous = mapping(previous_metadata.get(key))
            if isinstance(value, dict):
                prune(value, incoming, previous)
                continue
            incoming_time = number(incoming.get("timestamp"))
            previous_time = number(previous.get("timestamp"))
            if (
                incoming_time is not None
                and previous_time is not None
                and incoming_time < previous_time
            ):
                values.pop(key)
                incoming_metadata.pop(key, None)

    state = mapping(filtered.get("state"))
    for section, values in state.items():
        if isinstance(values, dict):
            prune(
                values,
                mapping(new_metadata.get(section)),
                mapping(old_metadata.get(section)),
            )

    def prune_metadata(incoming: dict, previous: dict) -> None:
        for key, value in list(incoming.items()):
            if not isinstance(value, dict):
                continue
            previous_value = mapping(previous.get(key))
            incoming_time = number(value.get("timestamp"))
            previous_time = number(previous_value.get("timestamp"))
            if (
                incoming_time is not None
                and previous_time is not None
                and incoming_time < previous_time
            ):
                incoming.pop(key)
            else:
                prune_metadata(value, previous_value)

    # Metadata can arrive without its corresponding state leaf. It still must
    # never regress proof retained from a newer field update.
    prune_metadata(new_metadata, old_metadata)
    return deep_merge(base, filtered)


@dataclass(frozen=True)
class Settings:
    temperature: int | None = None
    powder: int | float | None = None
    volume: int | float | None = None
    volume_unit: str | None = None
    making_bottle: bool | None = None
    water_only: bool | None = None


@dataclass(frozen=True)
class Alerts:
    bottle_missing: bool | None = None
    funnel_cleaning_needed: bool | None = None
    funnel_out: bool | None = None
    lid_open: bool | None = None
    low_water: bool | None = None
    heating: bool | None = None
    cooling: bool | None = None


@dataclass(frozen=True)
class Preparation:
    completed_at: datetime
    record_id: int | str | None = None
    volume: int | float | None = None
    volume_unit: str | None = None
    temperature_setting: int | None = None
    powder_setting: int | float | None = None
    water_only: bool | None = None
    preset_id: int | None = None
    provenance: str = "raw_snapshot"

    @property
    def attributes(self) -> dict[str, Any]:
        """Return a new immutable-preparation attribute snapshot per request."""
        return {
            "record_id": self.record_id,
            "volume": self.volume,
            "volume_unit": self.volume_unit,
            "temperature_setting": self.temperature_setting,
            "powder_setting": self.powder_setting,
            "water_only": self.water_only,
            "preset_id": self.preset_id,
        }


@dataclass(frozen=True)
class Preset:
    id: int
    title: str
    temperature: int | None = None
    powder: int | float | None = None
    volume: int | float | None = None
    volume_unit: str | None = None
    water_only: bool | None = None
    formula: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def description(self) -> str:
        """Describe configured values without treating a title as instructions."""
        amount = (
            f"{self.volume} {self.volume_unit}"
            if self.volume is not None and self.volume_unit
            else "Volume unavailable"
        )
        temperature = TEMPERATURE_LABELS.get(
            self.temperature, "Temperature unavailable"
        )
        powder = (
            f"Powder setting {self.powder}"
            if self.powder is not None
            else "Powder setting unavailable"
        )
        mode = (
            "Water only"
            if self.water_only is True
            else "Formula"
            if self.water_only is False
            else "Mode unavailable"
        )
        formula = " ".join(
            str(self.formula[key])
            for key in ("brand", "type", "stage")
            if self.formula.get(key) is not None
        )
        return "; ".join(
            part
            for part in (self.title, amount, temperature, powder, mode, formula)
            if part
        )


@dataclass(frozen=True)
class DeviceState:
    connected: bool | None = None
    settings: Settings = field(default_factory=Settings)
    alerts: Alerts = field(default_factory=Alerts)
    preparation: Preparation | None = None
    shadow_version: int | None = None


def normalize_shadow(
    raw: Mapping, preparation: Preparation | None = None
) -> DeviceState:
    reported = mapping(mapping(raw.get("state")).get("reported"))
    settings = mapping(reported.get("settings"))
    alerts = mapping(mapping(reported.get("hardware")).get("alerts"))
    unit = settings.get("volumeUnit")
    return DeviceState(
        connected=boolean(reported.get("connected")),
        settings=Settings(
            temperature=integer(settings.get("temperature")),
            powder=number(settings.get("powder")),
            volume=number(settings.get("volume")),
            volume_unit=unit if isinstance(unit, str) else None,
            making_bottle=boolean(settings.get("makingBottle")),
            water_only=boolean(settings.get("waterOnly")),
        ),
        alerts=Alerts(
            **{
                target: boolean(alerts.get(source))
                for target, source in {
                    "bottle_missing": "bottleMissing",
                    "funnel_cleaning_needed": "funnelCleaningNeeded",
                    "funnel_out": "funnelOut",
                    "lid_open": "lidOpen",
                    "low_water": "lowWater",
                    "heating": "tempHeating",
                    "cooling": "tempCooling",
                }.items()
            }
        ),
        preparation=preparation,
        shadow_version=integer(raw.get("version")),
    )


def normalize_presets(values: Any) -> dict[int, Preset]:
    presets = {}
    if not isinstance(values, list):
        return presets
    for raw in values:
        if (
            not isinstance(raw, dict)
            or (preset_id := integer(raw.get("id"))) is None
            or preset_id <= 0
        ):
            continue
        title = raw.get("title")
        unit = raw.get("volumeUnit")
        formula = mapping(raw.get("formula"))
        presets[preset_id] = Preset(
            id=preset_id,
            title=title.strip()
            if isinstance(title, str) and title.strip()
            else f"Preset {preset_id}",
            temperature=integer(raw.get("temperature")),
            powder=number(raw.get("powder")),
            volume=number(raw.get("volume")),
            volume_unit=unit if isinstance(unit, str) else None,
            water_only=boolean(raw.get("waterOnly")),
            formula=MappingProxyType(
                {
                    key: deepcopy(formula.get(key))
                    for key in (
                        "territory",
                        "brand",
                        "type",
                        "stage",
                        "setting",
                        "model",
                        "density",
                    )
                    if formula.get(key) is None
                    or isinstance(formula.get(key), (str, int, float, bool))
                }
            ),
        )
    return presets


def preset_options(presets: Mapping[int, Preset]) -> dict[str, int]:
    """Deterministic collision-free labels, including titles resembling suffixes."""
    titles = [preset.title for preset in presets.values()]
    options = {}
    for preset_id, preset in sorted(presets.items()):
        label = (
            f"{preset.title} [{preset_id}]"
            if titles.count(preset.title) > 1
            else preset.title
        )
        while label in options or any(
            other.id != preset_id and other.title == label for other in presets.values()
        ):
            label = f"{label} [{preset_id}]"
        options[label] = preset_id
    return options


def preparation_from_bottle(
    raw: Any, *, provenance: str = "raw_snapshot"
) -> Preparation | None:
    """Only complete preparation settings establish a coherent raw candidate."""
    if (
        not isinstance(raw, dict)
        or (completed := epoch(raw.get("completionTimestamp"))) is None
    ):
        return None
    volume = number(raw.get("volume"))
    temperature = integer(raw.get("temperature"))
    powder = number(raw.get("powderSetting"))
    unit = raw.get("volumeUnit")
    if (
        volume is None
        or volume <= 0
        or temperature is None
        or powder is None
        or not isinstance(unit, str)
        or not unit
    ):
        return None
    record_id = raw.get("id")
    return Preparation(
        completed_at=completed,
        record_id=record_id
        if isinstance(record_id, (str, int)) and not isinstance(record_id, bool)
        else None,
        volume=volume,
        volume_unit=unit,
        temperature_setting=temperature,
        powder_setting=powder,
        water_only=boolean(raw.get("waterOnly")),
        preset_id=integer(raw.get("bottleId")),
        provenance=provenance,
    )


def newest_preparation(*candidates: Preparation | None) -> Preparation | None:
    """Keep newest; a same-time raw delivery cannot undo matching-record enrichment."""
    newest = None
    for candidate in candidates:
        if candidate is None:
            continue
        if newest is None or candidate.completed_at > newest.completed_at:
            newest = candidate
        elif candidate.completed_at == newest.completed_at:
            if newest.record_id is not None and candidate.record_id is None:
                continue
            if (
                newest.record_id is not None
                and candidate.record_id is not None
                and newest.record_id != candidate.record_id
            ):
                # Stable order independent of API list order; numeric IDs when available.
                left, right = integer(newest.record_id), integer(candidate.record_id)
                if left is not None and right is not None and right < left:
                    continue
                if (left is None or right is None) and str(candidate.record_id) < str(
                    newest.record_id
                ):
                    continue
            newest = candidate
    return newest


def latest_from_details(
    details: Mapping, previous: Preparation | None = None
) -> Preparation | None:
    raw = mapping(details.get("shadow"))
    bottle = mapping(
        mapping(mapping(raw.get("state")).get("reported")).get("lastBottle")
    )
    candidates = [previous, preparation_from_bottle(bottle)]
    logs = details.get("bottleCreationLog")
    if isinstance(logs, list):
        candidates.extend(
            preparation_from_bottle(item, provenance="creation_record") for item in logs
        )
    return newest_preparation(*candidates)
