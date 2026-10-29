"""Entry-owned push state, read reconciliation and conservative start policy."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import ApiError, AuthenticationError, FpaClient
from .funnel import FunnelCounter
from .models import (
    DeviceState,
    Preparation,
    integer,
    latest_from_details,
    mapping,
    newest_preparation,
    normalize_presets,
    normalize_shadow,
    number,
    ordered_shadow_merge,
    preparation_from_bottle,
    preset_options,
)
from .storage import FpaStorage

_LOGGER = logging.getLogger(__name__)
MANUAL_REFRESH_COOLDOWN = 5.0
COMMAND_OBSERVATION_TIMEOUT = 30.0
COMPLETION_RETRY_DELAY = 2.0


@dataclass
class BottleGuard:
    """Minimal shared state; no timeout or refresh is evidence of bottle removal."""

    pending: bool = False
    running: bool = False
    occupied: bool = False
    uncertain: bool = True
    requested_preset_id: int | None = None
    last_preparation: float | None = None

    def persistent(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in asdict(self).items()
            if key in {"pending", "occupied", "uncertain", "last_preparation"}
        }


class FpaRuntime:
    """One authenticated account, one subscription/coordinator per machine."""

    def __init__(self, hass: HomeAssistant, entry, api: FpaClient) -> None:
        self.hass = hass
        self.entry = entry
        self.api = api
        self.devices: dict[str, DeviceCoordinator] = {}
        self.storage = FpaStorage(hass, entry.entry_id)
        self.operations: deque[dict[str, Any]] = deque(maxlen=50)
        self.authenticated = False
        self.closed = False
        self._tasks: set[asyncio.Task] = set()
        self._reauth_requested = False
        self.api.error_callback = self.handle_client_error

    def record_operation(
        self, device_id, category, status, reason=None, duration=None, http_status=None
    ) -> None:
        """Store only callers' fixed codes, never exceptions or remote text."""
        self.operations.append(
            {
                "time": datetime.now(UTC).isoformat(),
                "device_id": device_id,
                "category": category,
                "status": status,
                "reason": reason,
                "duration": round(duration, 3) if duration is not None else None,
                "http_status": http_status,
            }
        )

    def handle_client_error(self, device_id: str, error: ApiError) -> None:
        """React to safe listener failures even when a socket never reconnects."""
        if self.closed or not isinstance(error, ApiError):
            return
        device = self.devices.get(device_id)
        if device is not None:
            device.last_error = error.category
            device._publish()
        self.record_operation(
            device_id, "connection", "failed", error.category, http_status=error.status
        )
        if isinstance(error, AuthenticationError):
            self.authenticated = False
            if not self._reauth_requested:
                self._reauth_requested = True
                self.record_operation(
                    None, "authentication", "failed", "authentication_failed"
                )
                self.entry.async_start_reauth(self.hass)

    def create_task(self, coroutine) -> asyncio.Task:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    def _task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled():
            error = task.exception()
            if error is not None and not isinstance(
                error, (ApiError, HomeAssistantError)
            ):
                # No exception string: transport exceptions can embed auth URLs.
                self.record_operation(
                    None, "background", "failed", "background_failure"
                )

    async def async_setup(self) -> None:
        await self.storage.async_load()
        try:
            await self.api.refresh(self.entry.data["refresh_token"])
            self.authenticated = True
            self.record_operation(None, "authentication", "success")
            account = await self.api.get_me()
            identities = (
                account.get("devices", [])
                if isinstance(account, dict)
                else self.api.devices
            )
            for identity in identities:
                if not isinstance(identity, dict):
                    continue
                device_id = identity.get("deviceId")
                if (
                    not isinstance(device_id, str)
                    or not device_id
                    or device_id in self.devices
                ):
                    continue
                coordinator = DeviceCoordinator(self, identity)
                self.devices[device_id] = coordinator
                # Subscribe first; the read then reconciles any concurrent push.
                await self.api.subscribe(
                    device_id,
                    coordinator.receive_message,
                    coordinator.connection_changed,
                )
                await coordinator._request_refresh("setup")
        except AuthenticationError:
            self.authenticated = False
            self.record_operation(
                None, "authentication", "failed", "authentication_failed"
            )
            raise

    async def async_close(self) -> None:
        if self.closed:
            return
        self.closed = True
        for device in self.devices.values():
            device.close()
        tasks = set(self._tasks)
        for device in self.devices.values():
            tasks.update(device._command_tasks)
        tasks.discard(asyncio.current_task())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self.api.close()
        windows = getattr(self, "diagnostic_windows", None)
        if isinstance(windows, dict):
            windows.clear()
        self.operations.clear()


class DeviceCoordinator(DataUpdateCoordinator[DeviceState]):
    """One atomic state cache and one operation lock shared by all entities."""

    def __init__(self, runtime: FpaRuntime, identity: dict) -> None:
        self.runtime = runtime
        self.identity = deepcopy(identity)
        self.device_id = identity["deviceId"]
        self.title = identity.get("title") or "Formula Pro Advanced"
        super().__init__(runtime.hass, _LOGGER, name="fpa_device", always_update=False)
        self.data = DeviceState()
        self.presets = {}
        stored = runtime.storage.get(self.device_id)
        self.funnel = FunnelCounter.from_storage(stored.get("funnel"))
        self.selected_id = stored.get("selected_id")
        saved_guard = stored.get("guard", {})
        self.guard = BottleGuard(
            occupied=saved_guard.get("occupied") is True,
            uncertain=True,
            last_preparation=saved_guard.get("last_preparation"),
        )
        self.transport_connected = False
        self.last_refresh: datetime | None = None
        self.last_update: datetime | None = None
        self.last_error: str | None = None
        self.connected_at: datetime | None = None
        self.disconnected_at: datetime | None = None
        self.reconnect_count = 0
        self._raw_shadow: dict = {}
        self._lock = asyncio.Lock()
        self._refresh_task: asyncio.Task | None = None
        self._reconcile_task: asyncio.Task | None = None
        self._last_manual = float("-inf")
        self._received_sequence = 0
        self._read_pushes: list[tuple[int, dict]] | None = None
        self._closed = False
        self._needs_bottle_check = True
        self._command_timer: asyncio.TimerHandle | None = None
        self._start_busy = False
        self._command_tasks: set[asyncio.Task] = set()

    @property
    def raw_shadow(self) -> dict:
        return deepcopy(self._raw_shadow)

    @property
    def available(self) -> bool:
        return (
            not self._closed
            and self.transport_connected
            and self.data.connected is True
            and bool(self._raw_shadow)
        )

    @property
    def preset_options(self) -> dict[str, int]:
        return preset_options(self.presets)

    @property
    def block_reasons(self) -> list[str]:
        reasons = []
        if not self.available:
            reasons.append("device_unavailable")
        if self.guard.pending:
            reasons.append("request_pending")
        if self.data.settings.making_bottle is True or self.guard.running:
            reasons.append("making_bottle")
        if self.guard.occupied:
            reasons.append("occupied_bottle")
        if self.guard.uncertain:
            reasons.append("bottle_check_needed")
        critical = {
            "making_bottle": self.data.settings.making_bottle,
            **asdict(self.data.alerts),
        }
        if any(value is None for value in critical.values()):
            reasons.append("readiness_unverified")
        reasons.extend(
            key
            for key, value in asdict(self.data.alerts).items()
            if value is True and key not in ("heating", "cooling")
        )
        return list(dict.fromkeys(reasons))

    @property
    def summary_state(self) -> str | None:
        if self.guard.pending:
            return "requesting_bottle"
        if self.data.settings.making_bottle is True:
            return "making_bottle"
        if self.guard.occupied:
            return "full_bottle"
        for key in (
            "funnel_cleaning_needed",
            "funnel_out",
            "lid_open",
            "low_water",
            "bottle_missing",
        ):
            if getattr(self.data.alerts, key) is True:
                return key
        if self.guard.uncertain:
            return "bottle_check_needed"
        for key in ("heating", "cooling"):
            if getattr(self.data.alerts, key) is True:
                return key
        if self.block_reasons:
            return None
        return "ready"

    def _publish(self, state: DeviceState | None = None) -> None:
        if not self._closed:
            self.async_set_updated_data(state or self.data)

    async def _save(self) -> None:
        await self.runtime.storage.async_save(
            self.device_id,
            self.selected_id,
            self.guard.persistent(),
            self.funnel.persistent(),
        )

    async def async_reset_funnel(self) -> None:
        """Reset the local counter without a cloud or appliance command."""
        self.funnel.reset()
        self._publish()
        await self._save()

    def _schedule_save(self) -> None:
        if not self._closed:
            self.runtime.create_task(self._save())

    def _cancel_command_timer(self) -> None:
        if self._command_timer is not None:
            self._command_timer.cancel()
            self._command_timer = None

    def _accept_state(
        self,
        raw: dict,
        candidate: Preparation | None,
        *,
        reconnect=False,
        initialize_funnel=False,
    ) -> None:
        old_state = self.data
        previous_guard = self.guard.persistent()
        previous_funnel = self.funnel.persistent()
        preparation = newest_preparation(old_state.preparation, candidate)
        state = normalize_shadow(raw, preparation)
        self.funnel.observe(
            preparation, state.alerts.funnel_out, initialize=initialize_funnel
        )
        self._raw_shadow = deepcopy(raw)
        # An outage invalidates evidence of the present bottle's contents.
        if reconnect and state.alerts.bottle_missing is not True:
            self.guard.uncertain = True
        previous_preparation = old_state.preparation
        distinct_record = (
            preparation is not None
            and previous_preparation is not None
            and preparation.completed_at == previous_preparation.completed_at
            and preparation.record_id is not None
            and previous_preparation.record_id is not None
            and preparation.record_id != previous_preparation.record_id
        )
        completed = preparation is not None and (
            self.guard.last_preparation is None
            or preparation.completed_at.timestamp() > self.guard.last_preparation
            or distinct_record
        )
        if completed:
            self.guard.last_preparation = preparation.completed_at.timestamp()
            if state.alerts.bottle_missing is not True:
                self.guard.occupied = True
            self.guard.pending = False
            self._cancel_command_timer()
        if (
            old_state.settings.making_bottle is True
            and state.settings.making_bottle is False
        ):
            # Completion can precede lastBottle; retain original occupied protection.
            if state.alerts.bottle_missing is not True:
                self.guard.occupied = True
            self.guard.pending = False
            self._cancel_command_timer()
            self._schedule_reconciliation()
        if state.settings.making_bottle is True:
            if self.guard.pending:
                self.runtime.record_operation(self.device_id, "start", "observed_start")
            self.guard.pending = False
            self._cancel_command_timer()
        self.guard.running = state.settings.making_bottle is True
        if state.alerts.bottle_missing is True:
            self.guard.occupied = False
            self.guard.uncertain = False
        if preparation != old_state.preparation:
            self.runtime.record_operation(
                self.device_id,
                "preparation",
                "updated",
                preparation.provenance if preparation else None,
            )
        self._publish(state)
        if (
            previous_guard != self.guard.persistent()
            or previous_funnel != self.funnel.persistent()
        ):
            self._schedule_save()

    @staticmethod
    def _reported_bottle(raw: dict) -> dict:
        return mapping(
            mapping(mapping(raw.get("state")).get("reported")).get("lastBottle")
        )

    def _push_candidate(self, patch: dict, merged: dict) -> Preparation | None:
        bottle = self._reported_bottle(patch)
        candidate = preparation_from_bottle(bottle)
        if candidate is not None:
            merged_bottle = self._reported_bottle(merged)
            if all(
                merged_bottle.get(key) == value
                for key, value in bottle.items()
                if key != "errors"
            ):
                return candidate
            self._schedule_reconciliation()
            return None
        incoming_metadata = mapping(
            mapping(mapping(patch.get("metadata")).get("reported")).get("lastBottle")
        )
        if not bottle and not incoming_metadata:
            return None
        # Fields may arrive in several messages. The last field completes a
        # coherent snapshot even when completionTimestamp arrived earlier.
        # Every required leaf must have the same observed metadata generation.
        metadata = mapping(
            mapping(mapping(merged.get("metadata")).get("reported")).get("lastBottle")
        )
        keys = (
            "completionTimestamp",
            "volume",
            "volumeUnit",
            "temperature",
            "powderSetting",
            "waterOnly",
        )
        timestamps = [mapping(metadata.get(key)).get("timestamp") for key in keys]
        incoming_completion_time = number(
            mapping(metadata.get("completionTimestamp")).get("timestamp")
        )
        completion_time = number(
            self._reported_bottle(merged).get("completionTimestamp")
        )
        if (
            incoming_completion_time is not None
            and completion_time is not None
            and incoming_completion_time >= completion_time
            and all(value == incoming_completion_time for value in timestamps)
        ):
            return preparation_from_bottle(self._reported_bottle(merged))
        previous = self.data.preparation
        if "completionTimestamp" in bottle or (
            completion_time is not None
            and (
                previous is None or completion_time > previous.completed_at.timestamp()
            )
        ):
            self._schedule_reconciliation()
        return None

    def receive_message(self, envelope: dict) -> None:
        if self._closed or not isinstance(envelope, dict):
            return
        body = envelope.get("body")
        if not isinstance(body, dict):
            return
        owner = body.get("deviceId", body.get("device_id"))
        if owner != self.device_id:
            return
        capture = getattr(self.runtime, "capture_message", None)
        if capture is not None:
            try:
                capture(self.device_id, envelope)
            except Exception:  # Diagnostic capture must never stop live updates.
                self.runtime.record_operation(
                    self.device_id, "diagnostics", "failed", "capture_failed"
                )
        if envelope.get("subject") != "shadow-update":
            return
        patch = {
            key: deepcopy(value)
            for key, value in body.items()
            if key not in {"deviceId", "device_id"}
        }
        if "state" not in patch:
            return
        self._received_sequence += 1
        version = integer(patch.get("version"))
        current_version = integer(self._raw_shadow.get("version"))
        if (
            version is not None
            and current_version is not None
            and version < current_version
        ):
            return
        if self._read_pushes is not None:
            self._read_pushes.append((self._received_sequence, patch))
        merged = ordered_shadow_merge(self._raw_shadow, patch)
        candidate = self._push_candidate(patch, merged)
        self.last_update = datetime.now(UTC)
        previous = self.data.preparation
        self._accept_state(merged, candidate)
        if self.data.preparation != previous and self.data.preparation is not None:
            self._schedule_reconciliation()

    def connection_changed(self, connected: bool) -> None:
        if self._closed:
            return
        connected = connected is True
        previous = self.transport_connected
        self.transport_connected = connected
        now = datetime.now(UTC)
        if connected and not previous:
            self.connected_at = now
            self.reconnect_count += 1
            self.runtime.record_operation(self.device_id, "connection", "connected")
            self.runtime.create_task(self._background_refresh("reconnect"))
        elif not connected and previous:
            self.disconnected_at = now
            self._needs_bottle_check = True
            self.guard.uncertain = True
            self.runtime.record_operation(self.device_id, "connection", "disconnected")
            self._schedule_save()
        self._publish()

    async def async_select(self, preset_id: int) -> None:
        if preset_id not in self.presets:
            raise ServiceValidationError(
                translation_domain="fpa", translation_key="invalid_preset"
            )
        self.selected_id = preset_id
        await self._save()
        self._publish()

    async def _read_details(self, reason: str) -> None:
        started = time.monotonic()
        self._read_pushes = []
        try:
            details = await self.runtime.api.get_device_details(self.device_id)
            if self._closed:
                return
            if not isinstance(details, dict):
                raise ApiError("protocol")
            owner = details.get("deviceId", details.get("device_id", self.device_id))
            if owner != self.device_id:
                raise ApiError("protocol")
            raw = details.get("shadow")
            if (
                not isinstance(details.get("bottles"), list)
                or not isinstance(raw, dict)
                or not isinstance(mapping(raw.get("state")).get("reported"), dict)
            ):
                raise ApiError("protocol")
            old = self.data.preparation
            candidate = latest_from_details(details, old)
            if isinstance(details.get("bottles"), list):
                self.presets = normalize_presets(details["bottles"])
                if (
                    self.selected_id is not None
                    and self.selected_id not in self.presets
                ):
                    self.selected_id = None
                    await self._save()
            raw = details.get("shadow")
            if isinstance(raw, dict):
                raw = deepcopy(raw)
                incoming = integer(raw.get("version"))
                current = integer(self._raw_shadow.get("version"))
                pushes = self._read_pushes or []
                reset_allowed = reason in {"setup", "reconnect"} and not pushes
                if (
                    current is not None
                    and incoming is not None
                    and incoming < current
                    and not reset_allowed
                ):
                    raw = self.raw_shadow
                else:
                    for _, patch in pushes:
                        patch_version = integer(patch.get("version"))
                        if (
                            incoming is None
                            or patch_version is None
                            or patch_version >= incoming
                        ):
                            raw = ordered_shadow_merge(raw, patch)
                    # A replayed partial new timestamp must not inherit REST's old settings.
                    candidate = newest_preparation(candidate, self.data.preparation)
                self._accept_state(
                    raw,
                    candidate,
                    reconnect=self._needs_bottle_check,
                    initialize_funnel=True,
                )
                self._needs_bottle_check = False
            else:
                raise ApiError("protocol")
            self.last_refresh = datetime.now(UTC)
            self.last_error = None
            self.runtime.record_operation(
                self.device_id, "refresh", "success", reason, time.monotonic() - started
            )
            self._publish()
            if (
                candidate != old
                and candidate is not None
                and candidate.record_id is None
                and reason not in {"completion", "completion_retry"}
            ):
                self._schedule_reconciliation()
        except ApiError as exc:
            self.last_error = exc.category
            if isinstance(exc, AuthenticationError):
                self.runtime.handle_client_error(self.device_id, exc)
            self.runtime.record_operation(
                self.device_id,
                "refresh",
                "failed",
                exc.category,
                time.monotonic() - started,
                exc.status,
            )
            self._publish()
            raise
        finally:
            self._read_pushes = None

    async def _perform_refresh(self, reason: str) -> None:
        async with self._lock:
            if not self._closed:
                await self._read_details(reason)

    async def _request_refresh(self, reason: str) -> None:
        if self._closed:
            return
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = self.runtime.create_task(self._perform_refresh(reason))
        await asyncio.shield(self._refresh_task)

    async def async_refresh(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            try:
                await asyncio.shield(self._refresh_task)
            except ApiError as exc:
                raise HomeAssistantError(
                    translation_domain="fpa", translation_key="refresh_failed"
                ) from exc
            return
        if time.monotonic() - self._last_manual < MANUAL_REFRESH_COOLDOWN:
            return
        try:
            await self._request_refresh("manual")
            self._last_manual = time.monotonic()
        except ApiError as exc:
            raise HomeAssistantError(
                translation_domain="fpa", translation_key="refresh_failed"
            ) from exc

    async def _background_refresh(self, reason: str) -> None:
        try:
            await self._request_refresh(reason)
        except (ApiError, HomeAssistantError):
            pass  # Sanitized outcome already recorded; cached valid data survives.

    def _schedule_reconciliation(self) -> None:
        if self._closed or (
            self._reconcile_task is not None and not self._reconcile_task.done()
        ):
            return
        self._reconcile_task = self.runtime.create_task(self._reconcile_completion())

    async def _reconcile_completion(self) -> None:
        await self._background_refresh("completion")
        preparation = self.data.preparation
        if preparation is None or preparation.record_id is None:
            await asyncio.sleep(COMPLETION_RETRY_DELAY)
            await self._background_refresh("completion_retry")

    def restore_preparation(self, candidate: Preparation | None) -> None:
        chosen = newest_preparation(candidate, self.data.preparation)
        if chosen != self.data.preparation:
            self._publish(replace(self.data, preparation=chosen))

    async def async_start(self, preset_id: int | None = None) -> None:
        """Own and await the command task so unload can cancel it safely."""
        if self._closed:
            raise ServiceValidationError(
                translation_domain="fpa",
                translation_key="blocked_device_unavailable",
            )
        task = asyncio.create_task(self._async_start(preset_id))
        self._command_tasks.add(task)
        try:
            await task
        finally:
            self._command_tasks.discard(task)

    async def _async_start(self, preset_id: int | None = None) -> None:
        if self._start_busy:
            self.runtime.record_operation(
                self.device_id, "start", "rejected", "request_pending"
            )
            raise ServiceValidationError(
                translation_domain="fpa",
                translation_key="blocked_request_pending",
            )
        self._start_busy = True
        try:
            async with self._lock:
                requested_id = self.selected_id if preset_id is None else preset_id
                if requested_id is None:
                    self.runtime.record_operation(
                        self.device_id, "start", "rejected", "selection_required"
                    )
                    raise ServiceValidationError(
                        translation_domain="fpa", translation_key="selection_required"
                    )
                if (
                    isinstance(requested_id, bool)
                    or not isinstance(requested_id, int)
                    or requested_id <= 0
                ):
                    self.runtime.record_operation(
                        self.device_id, "start", "rejected", "invalid_preset"
                    )
                    raise ServiceValidationError(
                        translation_domain="fpa", translation_key="invalid_preset"
                    )
                # Every path performs fresh preflight; never reuse a cooldown read.
                try:
                    await self._read_details("preflight")
                except (ApiError, HomeAssistantError) as exc:
                    self.runtime.record_operation(
                        self.device_id, "start", "rejected", "preflight_failed"
                    )
                    raise HomeAssistantError(
                        translation_domain="fpa", translation_key="refresh_failed"
                    ) from exc
                if requested_id not in self.presets:
                    self.runtime.record_operation(
                        self.device_id, "start", "rejected", "invalid_preset"
                    )
                    raise ServiceValidationError(
                        translation_domain="fpa", translation_key="invalid_preset"
                    )
                if reasons := self.block_reasons:
                    self.runtime.record_operation(
                        self.device_id, "start", "rejected", reasons[0]
                    )
                    raise ServiceValidationError(
                        translation_domain="fpa",
                        translation_key=f"blocked_{reasons[0]}",
                    )
                self.guard.pending = True
                self.guard.requested_preset_id = requested_id
                # Persist the unresolved attempt before the physical command.
                await self._save()
                self._publish()
                # Push callbacks remain live while persisting pending metadata.
                # Recheck immediately before the single physical write.
                if reasons := [
                    reason
                    for reason in self.block_reasons
                    if reason != "request_pending"
                ]:
                    self.guard.pending = False
                    await self._save()
                    self.runtime.record_operation(
                        self.device_id, "start", "rejected", reasons[0]
                    )
                    self._publish()
                    raise ServiceValidationError(
                        translation_domain="fpa",
                        translation_key=f"blocked_{reasons[0]}",
                    )
                try:
                    await self.runtime.api.start_bottle(requested_id)
                except ApiError as exc:
                    self.guard.pending = False
                    definitive = (
                        exc.status is not None
                        and 400 <= exc.status < 500
                        and exc.status != 408
                    )
                    if not definitive:
                        self.guard.uncertain = True
                    self.last_error = exc.category
                    if isinstance(exc, AuthenticationError):
                        self.runtime.handle_client_error(self.device_id, exc)
                    self.runtime.record_operation(
                        self.device_id,
                        "start",
                        "rejected" if definitive else "indeterminate",
                        exc.category,
                        http_status=exc.status,
                    )
                    await self._save()
                    self._publish()
                    raise HomeAssistantError(
                        translation_domain="fpa",
                        translation_key="command_failed"
                        if definitive
                        else "command_indeterminate",
                    ) from exc
                except asyncio.CancelledError:
                    self.guard.pending = False
                    self.guard.uncertain = True
                    await self._save()
                    self._publish()
                    raise
                self.runtime.record_operation(self.device_id, "start", "accepted")
                if self.guard.pending:
                    self._cancel_command_timer()
                    self._command_timer = self.hass.loop.call_later(
                        COMMAND_OBSERVATION_TIMEOUT, self._command_timed_out
                    )
                self._publish()
        except asyncio.CancelledError:
            if self.guard.pending:
                self.guard.pending = False
                self.guard.uncertain = True
                await self._save()
                self._publish()
            raise
        finally:
            self._start_busy = False

    def _command_timed_out(self) -> None:
        self._cancel_command_timer()
        if self._closed or not self.guard.pending:
            return
        self.guard.pending = False
        self.guard.uncertain = True
        self.last_error = "command_observation_timeout"
        self.runtime.record_operation(
            self.device_id, "start", "indeterminate", "observation_timeout"
        )
        self._publish()
        self._schedule_save()
        self.runtime.create_task(self._background_refresh("command_timeout"))

    def close(self) -> None:
        self._closed = True
        self._cancel_command_timer()
