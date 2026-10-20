# Implementation interfaces

Build contract for the internal parallel implementation. See BUILD_SPEC.md for all behavior requirements.

## Client (client agent)

`api.py` reexports `FpaClient`, `ApiError`, `AuthenticationError`, `ConnectionError`, `CommandError` from vendor. Exceptions carry safe `category` and optional `status`; their strings never contain server text, URLs, or identities.

`FpaClient(session, token_callback=None)` uses injected shared aiohttp session. Async methods: `login(email,password)`, `refresh(refresh_token)`, `get_me()` returns account dict with `devices` (wire identities), `get_device_details(device_id)` returns wire dict without mutation, `start_bottle(bottle_id)` one write, `subscribe(device_id, on_message, on_connection)` idempotent owned subscription, `close()`. `subscribe` returns immediately; callbacks synchronous: message takes parsed envelope, connection takes bool. Credentials available as `.refresh_token`, `.email`, `.account_id` when established non-rotating identity, `.devices` list of wire identity dicts. Token callback receives rotated refresh token synchronously. Reconnect authenticates under client lock; on connection True runtime schedules reconciliation; callback false invalidates freshness. Expose safe connection observations if useful. No HA imports in vendor.

## Runtime/models (runtime agent)

`FpaRuntime(hass, entry, api)` entry-owned account runtime. `await async_setup()` loads storage/auth/details and subscriptions; `await async_close()` owns teardown. `.devices` dict by UUID -> `DeviceCoordinator`. `.api`, `.entry`, `.hass`. runtime diagnostics invokes `record_operation(device_id|None, category, status, reason=None, duration=None, http_status=None)` (bounded safe records). Agent may implement `.operations` directly; primary handles final privacy export.

`DeviceCoordinator` extends DataUpdateCoordinator, no periodic interval. Attributes: `.device_id`, `.title`, `.data` immutable `DeviceState`, `.selected_id`, `.presets` mapping int -> Preset, `.guard` (pending,occupied,uncertain etc), `.raw_shadow` defensive copy, `.transport_connected`, `.last_refresh`, `.last_error`. Methods `async_select(preset_id)`, `async_refresh()` read-only manual cooldown/coalescing, `async_start(preset_id=None)` common legacy/button path (None resolves selected), `receive_message(envelope)` and `connection_changed(bool)`. Expose `.available`, `.summary_state`, `.block_reasons`, `.preset_options` mapping display label -> ID. Store selection/minimal guard only. Diagnostics uses `.websocket_buffer` lazily attached by primary via hook if needed; call optional runtime `.capture_message(device_id,envelope)` before processing.

`DeviceState`: frozen dataclass with `.connected: bool|None`, `.settings` immutable normalized Settings (`temperature`, `powder`, `volume`, `volume_unit`, `making_bottle`, `water_only`), `.alerts` immutable Alerts (`bottle_missing`, `funnel_cleaning_needed`, `funnel_out`, `lid_open`, `low_water`, `heating`, `cooling`), `.preparation: Preparation|None`, `.shadow_version: int|None`. `Preparation` frozen `.completed_at` aware UTC datetime, `.record_id`, `.volume`, `.volume_unit`, `.temperature_setting`, `.powder_setting`, `.water_only`, `.preset_id`, `.provenance`; `.attributes` dictionary with specified public attributes (exclude provenance). `Preset`: `.id`, `.title`, `.temperature`, `.powder`, `.volume`, `.volume_unit`, `.water_only`, `.formula` safe nullable dict, `.description` plain useful no None text. `TEMPERATURE_STATES` maps 0,1,2 -> room_temperature/body_temperature/above_body_temperature. Helpers may be added; coordinate changes with entity agent.

## HA integration/entities (entities agent)

Own __init__, entity, sensor, binary_sensor, select, button, config_flow, const, strings, translations, services, manifest, hacs.json. Target minimum HA 2025.10.4, current 2026.10.2. Python 3.13/3.14. Preserve original summary unique ID=device UUID and device identifier `(fpa,UUID)`, legacy target service. New IDs UUID_suffix. `.runtime_data=FpaRuntime`. Runtime setup owns authentication; reauth errors typed. 17 entities/device. Historical sensor restores coherent timestamp/settings only via HA RestoreSensor; compare restored candidate with runtime data without regressing.

## Ownership

Primary: tests/conftest.py and shared fixtures, diagnostics + privacy module, packaging/CI/docs/reports, environment, Git operations, final validation. Client agent: api.py, vendor/**, tests/test_client.py. Runtime agent: models.py, coordinator.py, storage.py, tests/test_models.py, tests/test_runtime.py. Entity agent: files above, tests/test_entities.py, tests/test_config_flow.py. Do not operate Git index/branch/commits. Communicate interface changes promptly. Tests offline only.
