# Formula Pro Advanced WiFi: autonomous build instructions for Codex

Prepared October 19, 2026, America/New_York; incorporates the user's subsequent scope and execution-policy clarifications.

**Begin building on receipt of these instructions.** Deliver the implemented, validated, HACS-installable integration, comprehensive README, installation artifact, per-stage validation report, and documented agent decisions. Carry out the work continuously through completion using internal subagents or synchronous execution. Do not return only another plan, stop after a stage, or request routine approval of implementation choices or validation results.

The agent is empowered to make and implement decisions in the best interest of achieving this objective, within the agreed functional scope and the execution policy in section 11. Continue until the objective is complete, the user explicitly interrupts the work, or a critical failure leaves no viable path to required progress after reasonable recovery efforts. Document material agent decisions as they are made. At a critical failure, preserve the work and provide the failure description, recovery attempts, and concrete options for proceeding.

Start with the source revisions/references in section 2 and the accompanying [sanitized reference JSON](babybrezza-reference-sanitized.json). Establish a suitable fork or working repository, inspect the current upstream changes, set up the test environment, and execute stages A–F. Repository/workspace setup, implementation, dependency setup, tests, packaging, documentation, and validation are part of this assignment; they do not require separate stage-by-stage user instructions. The required delivery does not depend on deploying to the user's live HA installation or operating the physical appliance.

## 1. Outcome and agreed scope

Extend the existing `joncar/ha-fpa` Home Assistant custom integration while preserving its existing device, summary sensor, and `fpa.turn_on` action. Retain cloud push updates. Add current-setting sensors, individual machine-alert binary sensors, a named preset selector, a button that starts the selected preset, a data-refresh button, one last-preparation sensor per machine, and Home Assistant's native Download Diagnostics support.

The user explicitly accepted these decisions:

| ID | Requirement |
|---|---|
| S01 | Include separate current-setting sensors and machine-alert binary sensors. |
| S02 | Keep the existing summary sensor and `fpa.turn_on` action compatible. |
| S03 | Provide a dropdown of named cloud presets and a Start selected preset button. Choosing a preset must not change machine settings or start dispensing. |
| S04 | Remember the selected preset across HA restarts. If it is deleted, require a new selection; never silently select another preset. |
| S05 | Provide a Refresh data button, including refreshing cloud presets. |
| S06 | Preserve protection against a second preparation before the completed bottle has been removed. Report blocked/failed starts visibly. |
| S07 | Use one last-preparation timestamp sensor per machine, with that preparation's settings as attributes. Rely on Recorder for history. |
| S08 | After reconnecting, show only the newest cloud-reported preparation. Do not replay missed intermediate preparations into Recorder. |
| S09 | Include heating/cooling entities. Defer firmware entities and detailed last-bottle-error entities. |
| S10 | Implement native Download Diagnostics so common failures can be investigated without first retrieving HA logs. |
| S11 | Include a bounded, redacted copy of the last 20 received WebSocket updates per machine, captured before merging, alongside the latest merged raw shadow in Download Diagnostics. |
| S12 | Ship a comprehensive, user-facing root `README.md` explaining purpose/capabilities, supported entities and services/actions, installation/configuration, everyday use, diagnostics, limitations, and support, following HACS documentation conventions. |
| S13 | Execute stages A–F continuously and autonomously using available internal subagents or a synchronous workflow. Validate each exit criterion, repair failures, and continue until completion, an explicit user interruption, or a critical failure as defined in section 11. Deliver a consolidated per-stage validation report. |
| S14 | Make necessary implementation decisions in the objective's best interest, document material choices/assumptions and their validation, and provide a checkpoint plus failure description and options if a critical failure prevents completion. |
| S15 | Use Git in the project's own repository throughout implementation: inspect/preserve existing work, establish a working branch, make meaningful local commits/checkpoints, and tie validation, decisions, and final delivery to recorded source revisions. |

User clarification: the three temperature-setting codes are `0` = Room Temperature, `1` = Body Temperature, and `2` = Above Body Temperature. Treat this supplied mapping as an implementation requirement; no further mapping investigation is needed.

The following technical choices make those requirements implementable. They are design decisions in this plan, not additional claims about the vendor API: use stable preset IDs internally; centralize device state and start safeguards; retain bounded in-memory diagnostic operation summaries and pre-merge WebSocket updates; make missing safety information block starts; use a narrowly maintained API-client copy if an adequate separately released library is unavailable.

### Explicit exclusions

- No custom dashboard/card, history table, timeline, or other frontend project.
- No separate bottle-history database, archive, per-bottle entities, missed-record replay, Recorder SQL writes, or changes to Recorder retention.
- No daily/weekly counters, long-term preparation statistics, volume totals, consumption tracking, inventory estimates, or cost calculations.
- No new completion event entity, custom event stream, automatic Logbook entry system, or notification automations in this iteration.
- No writable volume/temperature/powder controls, cloud preset editing, arbitrary-parameter preparation, stop/cancel/pause commands, firmware updates, or local Wi-Fi/Bluetooth control.
- No firmware or detailed error entities. Existing firmware/error fields may appear in a carefully limited diagnostic snapshot as described below; that does not create those deferred features.
- No automatic correction of inconsistent preset names/settings, formula recommendations, or claims about actual powder mass, measured temperature, final mixture volume, or infant intake.
- The completion target is an implemented, validated, packaged integration and its documentation/reports. HACS default-store submission, production HA replacement, and physical dispensing are not required to achieve this target and must not become reasons to wait for user participation.

## 2. Evidence baseline and references supplied with this plan

The repositories were downloaded for read-only inspection at these revisions:

| Source | Reviewed revision | Relevant files |
|---|---|---|
| [joncar/ha-fpa](https://github.com/joncar/ha-fpa/tree/d69d8c0a765f8137a04e38f6ae3ea4f95120c488) | `d69d8c0a765f8137a04e38f6ae3ea4f95120c488` | `sensor.py`, `__init__.py`, `config_flow.py`, `services.yaml`, `manifest.json`, `hacs.json`, translations, validation workflow. |
| [joncar/pybabyfpa](https://github.com/joncar/pybabyfpa/tree/8f91cdbc38025d753dcd437f15fedeea5c63253a) | `8f91cdbc38025d753dcd437f15fedeea5c63253a` | `src/pybabyfpa/__init__.py`, packaging metadata, README, LICENSE. |

Source observations: `ha-fpa` 0.7.0 declares `pybabyfpa==0.0.7`, forwards only the sensor platform, and declares `cloud_push`. The library performs an initial details GET, receives `shadow-update` messages through a WebSocket, and starts saved presets with a PUT. Its simplified shadow omits heating/cooling and last-preparation data that exist in the supplied raw shadow. The current summary contains local request/full-bottle inference, and its availability uses the library's WebSocket-connection flag. See the pinned source links above for the exact baseline.

Before implementing, inspect current upstream changes and record the chosen base SHA. Reconcile useful upstream fixes; do not assume these revisions are permanently current. Preserve this scope if upstream has added unrelated features.

### User data reference

The reviewed `babybrezza_devices.json` contains one machine, four saved presets, ten returned creation-log records, a simplified shadow, and a raw cloud shadow. The screenshot shows the existing summary sensor and attributes. Its state/settings differ from the export because they are different observations; do not treat the screenshot and JSON as one atomic snapshot.

Use the accompanying [sanitized reference JSON](babybrezza-reference-sanitized.json) to build fixtures. It replaces personal names, identifiers, addresses, and absolute timestamps while preserving field names, types, nulls, relative times, and relationships. It is an export-shaped reference, not the literal response body of the vendor details endpoint. Reconstruct the wire-format fixtures: map preset fields such as `volume_unit` to `volumeUnit`, `water_only` to `waterOnly`; map log fields similarly; use `raw_shadow` as the wire-format `shadow`.

Important cases retained in that reference:

- A preset named as 3 oz has configured volume 4 oz.
- That preset has powder setting 4 while its formula metadata lists setting 5.
- A preset named `2oz Water` has `water_only: false`.
- Formula metadata may consist entirely of null fields.
- Creation logs include string volumes and string epoch timestamps, and some preset IDs are null.
- A preset ID appears on records with differing historical settings. Current preset definitions cannot reconstruct past preparations.
- `tempHeating`/`tempCooling` are present in raw alerts but absent from the simplified shadow.
- The raw last-preparation timestamp matches the latest returned log record in this one sample. Do not generalize that correspondence without matching each record.

Never commit the original user's export or screenshot to a public repository. Build regression fixtures from this sanitized reference and synthetic variations.

## 3. Entity contract

Create these entities for every supported machine. The suffixes below describe stable unique-ID components, not mandatory entity IDs: HA and users own entity-ID naming. Preserve the original summary sensor's unique ID exactly; use `<device_id>_<suffix>` for new entities. Link all entities to the existing device identifier `(fpa, device_id)`.

### Sensors: five total, including the existing sensor

| Unique-ID suffix | Name | Value/source | Entity semantics |
|---|---|---|---|
| Existing unique ID, unchanged | Existing machine summary | Shared machine state plus existing request/full-bottle inference | Preserve existing entity, raw state strings, useful attributes, registry customizations, and action targeting. Add heating/cooling states only as additive behavior. |
| `selected_volume` | Selected volume | Reported `settings.volume` and `volumeUnit` | Numeric selected quantity. Use the verified volume unit; do not interpret `oz` as mass. No state class initially. |
| `temperature_setting` | Temperature setting | Reported `settings.temperature` | Enum sensor using the confirmed mapping below, with the original numeric code in a `temperature_code` attribute. No temperature device class or degrees unit. |
| `powder_setting` | Powder setting | Reported `settings.powder` | Numeric setting code, no mass/concentration unit and no statistical state class. |
| `last_preparation` | Last preparation | Reported completion timestamp | Timestamp device class; timezone-aware UTC datetime internally; immutable preparation settings as attributes. No state class. See section 7. |

Use one shared temperature-setting mapping throughout sensors, preset descriptions, and diagnostics:

| API code | Enum state | English display label |
|---|---|---|
| `0` | `room_temperature` | Room Temperature |
| `1` | `body_temperature` | Body Temperature |
| `2` | `above_body_temperature` | Above Body Temperature |

Store the enum's display labels in the integration's translations. Preserve numeric codes in historical preparation attributes and the existing summary sensor's `temperature` attribute. Do not convert these settings into guessed Celsius/Fahrenheit values. An unexpected code makes the new temperature-setting sensor unknown while retaining the raw code for diagnostics; do not default to another setting. Distinguish absent/null values from code `0`, which is a valid setting.

Use a supported enum representation for the summary rather than retaining the invalid custom `fpa__state` device class if the selected HA baseline requires that modernization. Preserve its raw existing states: `requesting_bottle`, `making_bottle`, `full_bottle`, `funnel_cleaning_needed`, `funnel_out`, `lid_open`, `low_water`, `bottle_missing`, `ready`. Any migration of translation/device-class metadata must not recreate or rename the entity. Document that metadata correction.

### Binary sensors: nine total

| Suffix | Name | Reported field | Device class / interpretation |
|---|---|---|---|
| `making_bottle` | Making bottle | `settings.makingBottle` | Running, if appropriate to the chosen HA API. |
| `water_only` | Water only | `settings.waterOnly` | True means the machine reports water-only mode. No guessed mode from preset names. |
| `bottle_missing` | Bottle missing | `hardware.alerts.bottleMissing` | True means missing; use no device class if a standard one would invert this meaning. |
| `funnel_cleaning_needed` | Funnel cleaning needed | `funnelCleaningNeeded` | Problem. |
| `funnel_out` | Funnel removed | `funnelOut` | Problem or no device class; preserve true = removed. |
| `lid_open` | Lid open | `lidOpen` | Opening. |
| `low_water` | Low water | `lowWater` | Problem. |
| `heating` | Heating | `tempHeating` | Activity flag, not a measured temperature. |
| `cooling` | Cooling | `tempCooling` | Activity flag, not a measured temperature. |

An absent optional field is unknown, not false. If a partial push omits a field, retain the previous value from the same valid shadow generation; a complete snapshot genuinely lacking it establishes unknown. Expose independent alerts even if several are active together. Do not create duplicate inverse Bottle present or derived Ready entities in this iteration; summary/safeguards provide the relevant assessment.

### Controls: three total

| Suffix | Name | Behavior |
|---|---|---|
| `preset` | Bottle preset | `SelectEntity` listing cloud preset names. Selection is local to HA, remembered by stable preset ID. |
| `start_selected_preset` | Start selected preset | `ButtonEntity`; invokes the same guarded command path as the legacy action. |
| `refresh_data` | Refresh data | `ButtonEntity`, diagnostic category; read-only fetch of current device details, presets, and latest preparation. |

Expected baseline: 17 entities per machine, including the existing summary sensor. Enable the new functional entities by default. Do not add connection, firmware, error, counter, or estimate entities just because their data appears in diagnostics. If a platform API necessitates a small adjustment, record it and preserve the behavior contract.

### Shared HA entity requirements

- Use entity descriptions, stable translation keys, and appropriate supported device classes. Do not put network requests in entity property getters.
- New entities use HA device/entity naming conventions. Respect user-renamed devices and entities.
- Live machine state is unavailable when there is no usable current device connection/snapshot. The last-preparation sensor can retain its last known historical value during an outage; it must never imply that value is live machine status.
- The selector can remain usable with a cached valid preset list; the start operation must independently validate connectivity and current machine state. Refresh can remain available when the device itself is offline but the account API can be queried.
- Do not add frequently changing diagnostic counters/times to the last-preparation sensor. Keep its attributes tied to that preparation.

Reference: [sensor entity requirements](https://contributors.home-assistant.io/core/entities/sensor/), [binary sensors](https://contributors.home-assistant.io/core/entities/binary-sensor/), [select entities](https://contributors.home-assistant.io/core/entities/select/), and [button entities](https://contributors.home-assistant.io/core/entities/button/). HA requires timezone-aware datetime values for timestamp sensors; changed attributes can cause Recorder writes, so avoid unrelated attribute churn.

## 4. Architecture and API-client ownership

Separate protocol handling, normalized device state, command policy, and entity presentation. A practical file layout is:

| File or directory | Responsibility |
|---|---|
| `custom_components/fpa/__init__.py` | Entry setup/unload, platforms, runtime initialization. |
| `api.py` | Integration-facing API adapter, typed exceptions, safe operation summaries. |
| `vendor/pybabyfpa/` | Narrowly adapted client source when needed; origin/license recorded. |
| `models.py` | Normalized settings, alerts, presets, preparation snapshot, connection health. |
| `coordinator.py` | Shared account/device state, push dispatch, refresh reconciliation, per-device command policy. |
| `entity.py` | Common device identity, availability, coordinator subscriptions. |
| `sensor.py`, `binary_sensor.py` | Summary, current settings, last preparation, individual alerts. |
| `select.py`, `button.py` | Preset dropdown and buttons. |
| `diagnostics.py` | Allowlisted, redacted JSON export from cached runtime data. |
| `storage.py` | Versioned selection and minimal restart-safe guard metadata. Not a preparation archive. |
| `config_flow.py` | Existing login plus robust errors/reauthentication. |
| `services.yaml` | Existing `fpa.turn_on` contract. |
| `translations/en.json` | Complete literal English UI text, names, states, and errors. |
| `tests/` | Synthetic fixtures and behavior/integration tests. |

### Client distribution choice

The existing public library lacks several accessors and lifecycle controls this scope needs. Prefer a separately maintained, exact-version dependency if an adequate released client exists when implementation begins. Do not require the user to publish to PyPI simply to finish this fork.

For a self-contained first fork when no adequate release is available, the concrete fallback is a narrowly modified copy of `pybabyfpa` under the integration's `vendor/` directory. Preserve its MIT license, original attribution, upstream SHA, and a concise changes list. Use relative imports and remove the unused external requirement so only one implementation is active. Explain this maintenance tradeoff in the README. Keep this client independent of HA classes so it can later be upstreamed or extracted without redesigning the entities.

Do not spread private `_data` access through entities, monkey-patch an installed package, load runtime code from a Git branch, or add a hidden install-time download. Expose a defensive raw-shadow snapshot and typed heating/cooling/last-preparation access through the controlled client boundary. Restrict protocol changes to the reads, start command, normalization, lifecycle, and error handling required by this plan.

### Runtime model

Use typed `ConfigEntry.runtime_data` for entry-owned state. One account client owns authentication and the device subscriptions. Each machine has shared normalized state, an operation lock, preset selection, request state, and the occupied-bottle guard. All entity platforms subscribe to this same runtime. Disabled entities must not disable state tracking or safety checks.

Use HA's shared async HTTP session, and close only sockets/tasks owned by the client. Do not close HA's session. A push-oriented `DataUpdateCoordinator` with no recurring update interval, or an equivalent well-scoped dispatcher, is appropriate. Choose one shared update mechanism rather than separate polling in every entity.

References: [runtime data](https://contributors.home-assistant.io/core/quality-scale/runtime-data/), [shared web session](https://contributors.home-assistant.io/core/quality-scale/inject-websession/), [fetching data](https://contributors.home-assistant.io/core/integrations/fetching-data/).

## 5. Updates, refreshes, and lifecycle

### Initial setup

1. Load minimal local storage for this entry.
2. Establish authentication from the stored refresh token; save a rotated refresh token when returned, without causing unnecessary reloads.
3. Fetch device identity/details and normalize them before creating new entity states.
4. Reconcile stored preset IDs against the fresh list.
5. Initialize the last-preparation snapshot from the newest valid cloud candidate.
6. Establish exactly one owned device subscription per device. Register listeners before messages can be lost, or perform a reconciled initial fetch after subscribing.
7. Forward all four platforms and publish consistent cached states.

Connection/authentication failure classification must use actual API responses and typed network exceptions; do not treat every API failure as invalid credentials. Use `ConfigEntryNotReady` for recoverable initial connection failures and `ConfigEntryAuthFailed` for genuinely invalid/expired credentials, following [setup failure guidance](https://contributors.home-assistant.io/core/integrations/setup-failures/).

### Push processing

- Receive the existing cloud `shadow-update` stream; validate device identity and normalize incremental updates.
- Capture a defensive copy of each received JSON update before shadow merging/normalization, for the bounded per-machine diagnostic buffer in section 8. Capture must not mutate the message, block processing with I/O, or cause a separate entity/Recorder update.
- Correctly deep-merge partial shadow dictionaries without deleting unrelated sibling fields. Define treatment of explicit null values separately from absent keys.
- Track relevant shadow versions/generations when available. Ignore demonstrably older updates; handle a documented version reset through a new full-snapshot generation rather than permanently ignoring all future messages.
- Publish fresh immutable snapshots to entities so callbacks never observe half-updated settings/history.
- Use reported `lastBottle` changes to recognize preparations regardless of whether they were requested by HA, the app, or the machine controls. Do not require an observed `makingBottle` transition.
- Distinguish transport connectivity from the device's reported `connected` value. An open HA WebSocket is not proof that the appliance is online.

### Refresh data button

- Perform the device-details read for the targeted machine, refresh presets/settings/alerts/latest preparation, reconcile selection, then explicitly notify entities.
- Do not reconnect just to refresh; the old library's `connect_to_device` must not be called on every press because that can create another listener.
- Do not call an account refresh method that replaces all device objects behind active subscriptions without reconciling them.
- Serialize refreshes against start preflight reads for the same device. Coalesce repeated refresh requests; use a modest internal minimum interval, initially five seconds for manual requests. Start preflight reads are not skipped because of that cooldown.
- A refresh must not clear an occupied-bottle guard, select a replacement preset, dispatch a start, change settings, or fabricate a completion.
- A failed read preserves previously valid data with an explicit failure/freshness assessment; it does not replace everything with zeros/false.
- Surface failure to the user and record a sanitized operation summary. No reload or restart is required to see a renamed, added, deleted, or edited preset.

### Reconnect and latest-record reconciliation

After a successful reconnect, request one details refresh to reconcile changes missed while disconnected. Coalesce a details read after an observed preparation completion to obtain its optional creation-record ID; allow a bounded retry for eventual consistency, without continuous polling. Latest preparation can still update from a valid full `lastBottle` snapshot if that read fails. A failed enrichment read must not discard it.

There is no new periodic REST polling loop in this iteration. Routine state remains push-driven; REST reads occur on setup, reconnect, explicit refresh, command preflight, and bounded completion reconciliation. If vendor behavior makes this insufficient, report the observed limitation rather than quietly adding aggressive polling.

### Shutdown and failure handling

- Own, retain, cancel, and await WebSocket, ping/heartbeat, backoff, refresh, and command-timeout tasks.
- Put connection establishment inside reconnect exception handling, including DNS/TLS/handshake failures.
- Ensure unexpected message shapes and closed sockets cannot leave a permanently dead listener task.
- Serialize account token refreshes across device connections. Persist replacements safely.
- Cancel subscriptions and delayed callbacks on unload; close owned sockets; do not emit HA updates after unload.
- Clean up partially initialized resources after failed setup. Reload must not duplicate listeners, entity services, or tasks.
- Keep retries/backoff bounded and avoid log floods. Preserve TLS certificate verification. The earlier local certificate error is not permission to disable TLS verification.

## 6. Preset selection and start safeguards

### Dropdown identity and persistence

Use the preset ID as identity and the title as presentation. Persist the selected ID per config entry and machine through HA-managed versioned storage. Do not store only the displayed title, because names may change or be duplicated.

| Situation | Required behavior |
|---|---|
| First setup, no remembered ID | No automatic selection and no automatic start. Ask for a selection through normal entity state/error behavior. |
| Selected preset renamed | Keep the same selected ID and update its display label. |
| Duplicate names | Disambiguate deterministically with a stable ID suffix; never choose the first matching name. |
| Blank name | Display a neutral `Preset <id>` fallback. |
| Selected preset deleted | Clear active selection, invalidate the remembered choice, and block start until the user selects a currently valid preset. |
| Deleted ID later reappears | Do not silently reactivate a choice that was explicitly invalidated as deleted. |
| Preset list fetch fails | Retain last known mapping, expose the read failure, and require successful start preflight validation before using it. |
| Preset settings edited under the same ID | Refresh the details; selection remains by ID. Start uses its current cloud definition. |
| Multiple machines/accounts | Lists and stored selection stay isolated by entry and device identity. |

Expose only the selected preset's useful descriptive attributes if needed: ID, configured volume/unit, setting codes, mode, and nullable formula description. Do not place complete raw cloud responses or a growing history list in attributes. Missing formula metadata must render as unavailable information, never `None None`. Inconsistent preset titles/settings remain visible in diagnostics but are not automatically repaired or used as authorization to change formula settings.

### One shared start command

Both `button.press` on Start selected preset and the existing `fpa.turn_on` action must enter the same guarded method. The legacy action continues accepting a positive integer `bottle_id` and targeting the existing summary sensor. It does not change the dropdown selection unless the user explicitly selects a different option.

For each command:

1. Acquire the per-machine operation lock; reject/coalesce concurrent start requests so one physical preparation cannot be triggered twice.
2. Resolve the requested preset to this machine's current preset list. Reject unknown/deleted IDs and IDs belonging to another machine; never trust the caller's ID alone.
3. Perform one fresh read preflight and reconcile it with any newer pushes received during the request. Require a healthy device connection and known critical alert/activity values.
4. Reject an already requested/running preparation, absent bottle, cleaning-needed funnel, removed funnel, open lid, low water, heating, cooling, or occupied/uncertain-bottle guard. Where an optional heating/cooling flag is unsupported, do not falsely report false; treat readiness as unverified unless independent API evidence establishes it is safe to proceed.
5. Mark a request as pending before sending the command; preserve the current preset ID for this attempt even if the dropdown changes during the await.
6. Send the saved-preset start command once. Do not automatically replay a dispensing command after a timeout or ambiguous transport failure.
7. Distinguish request accepted, observed start, reported preparation, rejected, and indeterminate outcome. Acceptance alone is not completion.
8. Use a bounded observation timeout (initial design target: 30 seconds) and finite HTTP timeouts. A timeout must not leave `requesting_bottle` stuck forever or reopen the start guard without reconciliation. Timings are implementation constants to verify, not claims about vendor guarantees.
9. Raise translated `HomeAssistantError`/`ServiceValidationError` as appropriate for visible failures; do not merely log and return success. Record sanitized reason codes for diagnostics.

No method can guarantee the machine will accept a start or validate the physical contents of the bottle. The goal is to preserve existing protections and avoid bypasses in the new controls.

### Occupied-bottle guard across paths and restarts

Maintain this centrally, not on the summary sensor instance. A newly reported preparation while the bottle remains present marks it as occupied. Observing bottle missing clears that occupied state; a subsequent present bottle can become eligible again when other checks pass. This applies equally to preparations initiated outside HA.

Persist only the minimal guard state and last relevant preparation timestamp needed to survive restart; this is not an archive. A new completion timestamp discovered on reconnect can invalidate prior readiness. If HA restarts/reconnects with a bottle present and cannot establish whether the current bottle is empty, mark the guard uncertain and require an observed removal/replacement before another HA start. Explain that message plainly. Refreshing data or waiting for a timeout is not evidence of removal. Do not expose a bypass/reset button in this iteration.

### Summary compatibility

Keep the existing relative alert priorities and legacy raw states wherever the same inputs apply. Put new heating/cooling states before otherwise returning `ready`. Pending/running/occupied tracking must remain consistent with the shared guard; a healthy-looking summary must never bypass it. During an uncertain guard, use a clearly documented additive state such as `bottle_check_needed`, with a translation explaining removal/replacement. Unknown required data must not yield `ready`.

## 7. Last-preparation sensor and Recorder behavior

This is the entire preparation-history feature for this iteration. Use one entity per machine. No separate archive, list attribute, per-preset history sensor, or direct Recorder manipulation.

### Snapshot shape

| Field | Required meaning |
|---|---|
| State | UTC completion timestamp from the cloud, converted from epoch seconds to a timezone-aware datetime. |
| `record_id` | Creation-log ID when a matching record is known; otherwise null. |
| `volume` | Normalized numeric value from that preparation record/snapshot. |
| `volume_unit` | Reported unit for that volume. |
| `temperature_setting` | Recorded numeric code: `0` = Room Temperature, `1` = Body Temperature, `2` = Above Body Temperature. Preserve the code, not current selected settings or guessed measured degrees. |
| `powder_setting` | Recorded setting, not a mass estimate. |
| `water_only` | Recorded mode; null if genuinely unknown. |
| `preset_id` | Log's preset ID when known, otherwise null. A null value does not establish an on-device origin. |

Do not add a mutable current preset name by default. If a capture-time name is included, freeze it for that preparation and document that it is a lookup label, not historical proof. Do not add initiator/source attribution: the supplied API data does not establish it. Do not classify every reported preparation as successful; detailed error interpretation is deferred.

### Candidate selection and updates

- Build candidates from valid complete `lastBottle` reports and returned creation records. Parse actual values rather than relying on the library's inaccurate scalar type annotations.
- Select the newest valid completion timestamp, independent of list ordering. For equal timestamps, use known record IDs and actual record contents to distinguish a legitimate change; do not deduplicate by volume/settings alone.
- Do not regress to an older preparation when a late response or reconnect snapshot arrives.
- Prefer the matching log record's historical settings when its timestamp and identity are coherently associated. Do not borrow settings from a different preparation or today's preset definition.
- When a partial push changes a completion timestamp, ensure the accompanying preparation fields form a coherent snapshot before publishing. Use field metadata/version information when available; otherwise reconcile with a full details read. Never combine a new timestamp with known-old bottle settings simply because dictionaries were merged.
- Publish the timestamp and attributes together. A repeated delivery of the same unchanged preparation produces no new history update. If a later read legitimately supplies a previously missing record/preset ID, one attribute enrichment is allowed; document that Recorder may store another snapshot with the same completion timestamp.
- Consecutive equal-setting preparations still update because their completion timestamps/IDs differ.
- Changes to current machine settings, a preset rename, connection timestamps, diagnostics, or refresh counts must not change the last-preparation attributes.
- With no valid preparation data, expose unknown; do not use the current time, zero epoch, a request time, or a guessed completion.

### Startup, outage, and retention contract

Initialize from the newest cloud record. If several preparations happened while offline, publish only the newest. Do not replay older records, trigger completion notifications, or rewrite HA timestamps.

Use `RestoreSensor`/HA's restoration mechanisms if needed to preserve one last known snapshot when setup has usable partial data but no newer preparation. Restore its timestamp and companion attributes coherently; do not create a custom preparation store. Restoration does not prove current appliance connectivity, and stale server data must not overwrite a newer valid restored snapshot.

Recorder stores HA state observations under the user's normal recording/retention rules. The sensor's value retains the cloud completion time, while HA's history entry reflects when HA received/published the observation. Explain this distinction in documentation. The integration must not force `last_changed`, write to Recorder tables, change include/exclude filters, or promise lossless capture during outages. Full snapshots follow Recorder purge settings and do not become indefinite long-term statistics. Reference: [Recorder](https://www.home-assistant.io/integrations/recorder/).

## 8. Download Diagnostics: required behavior

Home Assistant's native diagnostics support lets an integration provide JSON through the entry menu. Implement `diagnostics.py` with `async_get_config_entry_diagnostics`; additionally provide `async_get_device_diagnostics` to restrict exports to the chosen machine. Use native download behavior, not a custom service, endpoint, dashboard button, or file written into the user's config folder. HA's documentation describes the entry/device download hooks and nested redaction helper. [Official diagnostics guidance](https://contributors.home-assistant.io/core/integrations/diagnostics/).

### Purpose and limits

The download should answer: Is the account authenticated? Is HA connected to the cloud? Does the machine report itself online? Are updates arriving? Which safety condition blocked the last start? Is the selected ID still valid? Did refresh succeed? Which last-preparation data was available?

It is a point-in-time report plus bounded sanitized operation summaries and received WebSocket updates, not a complete log or packet capture. It cannot reconstruct failures before its in-memory record window, guarantee a remote cause, or replace all logs. State these limits in the README and report schema. Here, raw JSON means the received/merged JSON structure with privacy redactions applied; it does not promise original wire bytes or unredacted payload values.

Downloading diagnostics must not call the vendor API, rotate tokens, reconnect, press a button, or change any state. Take a defensive snapshot of cached runtime data. This makes downloads available during cloud/device outages and avoids diagnostics introducing side effects.

HA adds its own wrapper around the integration's data, including system/integration metadata. Its device download filename may also contain the registered device name. Inspect that behavior on the actual supported HA versions; the integration's hook does not control the entire wrapper or filename. Keep secrets out of any integration-created repair-issue placeholders as well. Test the full download with representative synthetic registry/system metadata, and document any HA-controlled metadata/filename exposure rather than promising the entire file is anonymous. Do not modify global diagnostics routes or rename a user's device just to alter a download filename. Reference: [HA diagnostics implementation](https://github.com/home-assistant/core/blob/dev/homeassistant/components/diagnostics/__init__.py).

### Required report schema

| Section | Include |
|---|---|
| `schema_version` | Integration-defined version of the diagnostic structure. |
| `integration` | Installed integration version, reviewed/client origin and version, supported runtime metadata not already supplied by HA's wrapper. Do not duplicate the whole HA system report. |
| `entry` | Entry load/auth state and option names/values that are safe. Omit raw config-entry data and title. |
| `devices` | Consistent per-download aliases such as `device_1`; no real device UUID, numeric cloud ID, MAC, account ID, personal title, room, or area name. |
| `connection` | HA transport connected, reported appliance connected, reconnect attempt count, connection/disconnection/update times or ages, last successful details refresh, last sanitized error category. Explicit unknowns if not yet observed. |
| `reported_state` | Current setting codes/volume/unit, known alerts including heating/cooling, and shadow version. Include knowledge/availability status separately from boolean false. |
| `latest_merged_shadow` | Redacted defensive copy of the latest merged raw cloud shadow before integration normalization, including available state/metadata/version fields. Distinguish this from both normalized `reported_state` and individual received messages. Bound this section to 256 KiB of serialized JSON; if too large, return an explicit omission/size explanation rather than invalid truncated JSON. |
| `presets` | Count; aliased IDs; selected/valid flags; configured quantities/modes; missing-metadata markers; discrepancy flags. Replace every free-text title with an alias. |
| `last_preparation` | The normalized latest snapshot with aliased record/preset IDs. No full creation-log list. Include whether it came from a coherent raw snapshot or matching log record; that is data provenance, not initiator attribution. |
| `command_guard` | Pending/requested/running/occupied/uncertain state and explicit current block reasons. |
| `recent_operations` | Up to 50 in-memory entries across the account, filtered for device exports. Each: UTC time, operation category, device alias, safe status/reason code, duration, and safe HTTP status when known. |
| `recent_websocket_updates` | Per-machine buffer of at most 20 received JSON updates in receipt order. Each has a local sequence number, timezone-aware UTC `received_at`, `subject`, and redacted original message `payload` captured before merge. Include retention/eviction/oversize metadata. See the buffer contract below. |
| `client_observations` | Bounded known raw fields useful for debugging, including firmware version/updating flag and last-bottle error booleans if cached. These remain diagnostic fields, not deferred entities or controls. Omit firmware location/download URLs. |
| `limitations` | Latest-only history, partial/missing fields, operation-window bounds, and unavailable data explanations. |

Record successful and failed refreshes, authentication state transitions, connect/disconnect outcomes, start rejection reasons, command acceptance/timeout, and normalized preparation changes. Retain received JSON updates only through the separately bounded/redacted buffer below; do not create an unrestricted payload log. Operation summaries and message buffers are diagnostic context, not a historical bottle ledger; keep them in memory and discard on entry reload/restart. Never put either buffer into entity attributes, Recorder, or normal HA logs.

### Received WebSocket buffer contract

- Keep the last 20 received JSON updates per machine, subject to a total serialized-buffer limit of 256 KiB per machine. Evict oldest entries when either limit is reached. The count is per machine, not a shared account-wide list; report the configured count/byte limits and eviction totals so a shorter window is explainable.
- Capture the parsed JSON message envelope before passing it to shadow merging or field normalization. The `payload` retains the received envelope/body and original key spelling, nesting, nulls, and safe value types. It is a defensive copy, not a reference to an object that subsequent merges can change.
- Attach HA's UTC receipt timestamp and a local monotonically increasing receipt sequence. Retain server-supplied timestamps/versions inside the payload where safe. Do not substitute the receipt time for the vendor's preparation time.
- Preserve partial updates as partial: do not populate missing fields from the cached shadow. The separate `latest_merged_shadow` shows their accumulated result. Include both in the same diagnostics snapshot so missing/changed fields and interpretation can be compared.
- Keep messages in receipt order, including duplicate and older-version updates even if normal state processing rejects them. Do not filter the diagnostic buffer down to changes that modified an entity. This window is intended to explain ordering/merge problems.
- Route only messages reliably associated with the relevant machine to its buffer. Unknown subjects with an identifiable device can be captured with sanitized subject/payload values; do not guess ownership for unassociated messages or include another device's data. Report safe unassociated-message counts at account level if useful.
- Apply the field-aware privacy policy to each independent captured copy and again at export. Preserve useful raw structure without allowing unknown/free-text fields to bypass redaction. Keep approved non-sensitive machine values; retain unfamiliar field names/nesting for troubleshooting but redact unclassified scalar values until they are explicitly reviewed. Never capture authentication handshakes, outgoing credentials, headers, socket URLs, ping/pong transport frames, or arbitrary non-JSON text as raw payloads.
- If an individual sanitized message exceeds the byte cap, retain a small metadata-only entry with its receipt time/sequence, safe subject, byte count, and `payload_omitted` reason. Do not retain the oversized body, slice JSON text into an invalid document, or silently pretend it was a complete payload. Parsing/capture errors must not break live state processing; expose a safe omission/failure counter instead.
- Use no filesystem writes for the buffer. Reset it on entry unload/reload and HA restart; a temporary socket reconnect within the same loaded entry preserves the remaining window. A diagnostic download does not clear the buffer.
- Snapshot the message window, latest merged shadow, and normalized state consistently during download without initiating reads. A report with zero captured messages must explain that capture has not yet received an update; setup REST data can still supply the merged shadow.
- The buffer adds no entity, completion event, preparation archive, Recorder history, or command path. It does not change the latest-only history decision in S07/S08.

Capture useful subcomponent failures without allowing one missing field or unloaded client to make the entire download fail. If runtime data is unavailable, return a safe minimal entry-status report instead of an exception or raw configuration dump. Device exports must never leak another device's operations.

### Privacy and redaction contract

Construct an allowlisted top-level report first, then use `async_redact_data` for defense in depth. The raw-shadow/message sections additionally require the recursive, field-aware sanitization described above to preserve structure while controlling values. A blacklist of obvious token keys alone is insufficient. Diagnostic references may use consistent aliases generated from the current snapshot; use the same aliases across raw messages, merged shadow, presets, and normalized state so they remain comparable. Do not expose a reversible identifier mapping or stable unsalted hash of real identifiers.

Exclude or redact all of the following, including nested dictionaries, list entries, errors, and any registry-derived structures:

- Passwords, access tokens, refresh tokens, Authorization headers, session IDs/cookies, and the credential-bearing WebSocket URL/query string.
- Email addresses, account/user IDs, child names, device names, preset titles, entry titles, user-customized entity names/IDs, and area/location names.
- Device UUIDs, raw cloud numeric IDs, Wi-Fi/BLE MACs, IP addresses, and unneeded unique identifiers.
- Raw free-text server error bodies, exception strings/tracebacks, request headers, URLs with secrets, and full raw config entries.

Do not simply pass `str(exception)` into the report or regular logs: WebSocket exceptions can embed the URL containing Authorization. Store safe exception classes/categories and approved reason codes instead. Errors such as TLS verification failure should still be recognizable without exposing their request URL or credentials.

Exact preparation/operation/message timestamps can reveal household routines. Include only the latest preparation and bounded operation/message windows needed for support, exclude child-identifying labels, and document that users should review the download before sharing. Do not describe the file as anonymous or secret-free solely because a helper was called.

Required privacy verification: use deliberately seeded secret and personal-data sentinel strings in every integration-controlled nested location, serialize the entire final downloaded JSON, and assert none survives in its body. Separately inspect framework-controlled wrapper fields and response filenames; report their limits instead of asserting control the integration does not have. Verify the original cached objects have not been mutated by redaction. The agent must inspect a representative report as part of validation; this is not a human review gate. Keep the allowlist/redaction tests under version control.

The extensive schema above is this project's proposed support design. HA supplies the download hooks/redaction helper; it does not collect these integration-specific operational observations automatically.

## 9. Compatibility, configuration, and errors

- Retain domain `fpa`, the existing device identifiers, the original summary unique ID, existing service name, integer `bottle_id` argument, and existing config-entry refresh-token compatibility.
- Do not require users to delete/recreate their integration or entities. Avoid changing entry version unless persistent data actually needs migration; implement and test migration if it does.
- Preserve registry custom names, areas, enabled states, and existing automation references through upgrade.
- Preserve existing summary attribute keys, including `bottle_<id>`. Correct null-description output without renaming those keys. Add the new dedicated entities rather than removing old attributes in this release.
- Start failures become visible errors rather than silent log-only returns; document this intentional behavior improvement for existing automations.
- Keep authentication secrets only in HA-managed configuration. Persist rotated refresh tokens; do not persist access tokens or passwords unnecessarily.
- Add reauthentication for expired/invalid credentials; avoid duplicate account entries where an established safe account identity is available. Do not use rotating tokens as account unique IDs or rewrite old entry identity blindly.
- Recover from transient DNS/TLS/timeouts as connectivity failures. Do not replace them with invalid-auth errors or advise disabling certificate checks.
- Use translated literal text in `translations/en.json`, including new entity names, states, button names, and actionable error explanations. The existing core translation references must be resolved to actual English strings for a custom integration.
- No new options UI is necessary for the agreed feature set. Keep timeouts/cooldowns as documented internal constants for this iteration rather than expanding user configuration.

Reference: [config entries and unload lifecycle](https://contributors.home-assistant.io/core/integrations/config-entries/) and [custom-integration translations](https://contributors.home-assistant.io/core/integrations/translations/#custom-integrations). Custom integrations ship complete translation files themselves; core-only reference resolution must not be assumed.

## 10. HACS packaging and development guidance

Treat this as a Home Assistant integration distributed through HACS. HA's entity/lifecycle/configuration guidance governs runtime behavior; HACS governs repository/distribution expectations. Passing HACS checks alone does not establish correctness or a Home Assistant quality tier.

### Repository and manifest

- Use the conventional single integration layout under `custom_components/fpa/` for the new fork, with `hacs.json`, README, license, tests, and workflows at repository root. The upstream root-content layout is supported with its flag, but this fork should choose one layout consistently. Remove/update `content_in_root` when moving the code.
- Include all runtime files, vendor sources/licenses if used, translations, and required brand assets in the installable integration directory.
- Keep `manifest.json` valid with domain, name, version, codeowners, documentation, issue tracker, config-flow declaration, and accurate dependency metadata. Preserve `cloud_push`; these supplementary reads do not turn the design into a recurring poller.
- Point documentation/issues/codeowners to the actual new project/maintainers once a fork exists; never invent an account or imply the original author supports the fork.
- Declare a tested minimum HA version in HACS metadata. Do not retain upstream's `2023.5.0` claim if modern runtime APIs are used without testing it. Choose the minimum against the actual APIs during bootstrap and test that minimum plus the then-current stable HA version.
- Remove obsolete/unrecognized metadata only after validation against the chosen HACS version; do not copy the old manifest blindly.
- Preserve MIT attribution and the distinction between this community project and the manufacturer.

The official [HACS integration requirements](https://www.hacs.xyz/docs/publish/integration/) describe repository layout, manifest keys, brand assets, and release handling. The [general publishing guide](https://www.hacs.xyz/docs/publish/start/) covers `hacs.json`, version metadata, and repository information. Releases should use versioned, reviewable artifacts; default-store inclusion is separate from installing a custom repository.

### Validation and maintenance

- Add lint/format checks, meaningful tests, HA hassfest validation, and HACS validation to pull requests and pushes. Resolve dependency compatibility against the selected HA test versions.
- Use least-privilege CI permissions; no production credentials or cloud access in tests. Pin workflow actions using the repository's chosen update policy, and keep pins maintained.
- Confirm installable files are included by HACS, including the vendor client if used. Test the artifact, not just imports from a developer checkout.
- Record the origin of any borrowed client code and keep its modifications focused. Avoid runtime package installation hacks or unpinned Git dependencies.
- Use quality-scale rules as an engineering checklist—especially unique IDs, runtime ownership, correct availability, action exceptions, unload, reauth, diagnostics, and tests. Do not claim a Gold/Platinum rating merely because diagnostics exist.
- Include an issue template requesting the integration/HA version, reproduction, and reviewed diagnostics. Warn users not to paste credentials, raw unsanitized exports, or a complete config directory.
- Document how to switch from upstream to the same-domain fork without running both copies. Preserve config entries and registry records; do not solve an upgrade by deleting them. Provide rollback steps and recommend a normal HA backup before deployment.

References: [HACS validation action](https://www.hacs.xyz/docs/publish/action/), [hassfest for custom components](https://contributors.home-assistant.io/blog/2020/04/16/hassfest/), [manifest reference](https://contributors.home-assistant.io/core/integrations/manifest/), [integration quality rules](https://contributors.home-assistant.io/core/quality-scale/rules/).

### Required finished README.md

The finished product must include a comprehensive root `README.md`, written for someone discovering the integration and for someone installing/using it. This is a required release deliverable, not a placeholder, a link back to this planning conversation, or a developer-only design document. It must describe the actual implemented release and remain understandable without reading code or the implementation plan.

HACS explicitly requires a README with usage information. Use the [HACS publishing guidance](https://www.hacs.xyz/docs/publish/start/#readme) and the [Home Assistant integration-page structure](https://contributors.home-assistant.io/writing/reference/integration-page/) as the basis: introduce purpose, explain prerequisites/setup, describe supported functionality, and provide usable examples and troubleshooting. Adapt the structure to plain GitHub Markdown; do not copy HA website-only Liquid tags or imply those site-build requirements apply to a HACS README. The detailed content requirements below are this project's documentation acceptance criteria, beyond HACS's minimum usage-information requirement. The [integration blueprint linked by HACS](https://github.com/ludeeus/integration_blueprint) can provide presentation inspiration; do not inherit its sample features, polling assumptions, or template text as product claims.

Use this reader-oriented outline, with a table of contents and clear navigation:

| README section | Required content |
|---|---|
| Purpose and feature overview | Explain that this community integration connects the WiFi Formula Pro Advanced to HA for status/alerts, named preset selection/start, latest-preparation history, and troubleshooting. Identify the fork's relationship to upstream and manufacturer independence. Lead with user outcomes rather than internal class/module details. |
| Compatibility and prerequisites | State supported/tested hardware and HA versions, cloud/internet/account requirements, and the need to have the machine and saved presets configured through the manufacturer's app. Distinguish verified support from untested models; do not claim non-WiFi or local-only compatibility. |
| Installation | Provide HACS custom-repository installation as the primary route, using the actual repository URL/category and verified UI steps, followed by required restart/reload/setup steps. Include a concise manual-install fallback with the correct `custom_components/fpa` path and package contents. Explain that HACS downloading and adding the HA integration are separate steps. |
| Configuration and upgrading from upstream | Walk through adding the integration, credential entry, and reauthentication without putting credentials into example files. Explain same-domain replacement, preserving existing config entries/registries, avoiding simultaneous copies, updating, rollback, and removal. State the tested minimum versions and link release notes. |
| Entity catalog | Group all provided entities by Sensors, Binary sensors, Select, and Buttons. For each, give the display name, purpose, value/options or true/false meaning, significant attributes/units, availability/default-enabled behavior, and notable limitations. Include the existing summary sensor, raw summary states, three current-setting sensors, nine binary sensors, last preparation, named preset dropdown, and both buttons. Explain that illustrated entity IDs vary with user naming. |
| Temperature settings | Show `0` = Room Temperature, `1` = Body Temperature, `2` = Above Body Temperature, with readable new sensor labels and retained raw codes in history/legacy attributes. Explain that these are settings rather than measured water temperatures. |
| Preset controls and everyday use | Give the complete UI flow: choose a named preset, deliberately press Start selected preset, then observe machine activity/result. Explain that selection alone does not change the machine or dispense. Cover remembered ID, rename/duplicate handling, deleted preset/no fallback, and Refresh data after app changes. Explain that configured values take precedence over misleading preset names. |
| Services/actions reference | Document the retained `fpa.turn_on` action with its target, required positive integer `bottle_id`, how to find the ID, and blocked/failed behavior. Document use of the standard `select.select_option` and `button.press` actions for the new entities; distinguish these standard HA actions from integration-defined actions. Do not invent an `fpa.start_selected_preset` service just because a button exists. |
| Practical usage examples | Include short UI instructions and copyable, validated YAML/script examples for selecting a preset and deliberately starting it, refreshing data, and using the legacy start action. Include a read-only example of using an alert or last-preparation sensor in an automation if helpful. Clearly identify synthetic entity IDs/preset IDs and replacement points. Do not require custom cards, automatically install automations, introduce a deferred completion event, or suggest bypassing start guards. Make every dispensing example explicitly intentional. |
| Start protection and status | Explain all relevant block reasons, request accepted versus observed start/completion, occupancy protection, and why removal/replacement may be required after an uncertain restart. Provide user recovery steps, not a bypass. Clarify that HA can start only a saved cloud preset; writable settings and stop/cancel controls are not provided in this release. |
| Data updates and preparation history | Explain push updates and when REST reads occur; describe refresh without promising a fixed polling interval. Explain the one timestamp sensor, recorded settings attributes, machine/app/HA-initiated preparations, unknown initiator attribution, latest-only reconnect behavior, HA observation time versus cloud completion time, Recorder inclusion/retention, and absence of a separate archive or lossless outage recovery. |
| Download Diagnostics and privacy | Give verified entry/device-page download instructions and explain the normalized state, latest merged shadow, recent operation summaries, and up to 20 pre-merge received WebSocket updates per machine. State receipt timestamps, redactions, count/byte caps, explicit omissions, reconnect retention, reload/restart reset, no disk/Recorder storage, and no vendor call on download. Note that raw means structure-preserving redacted JSON, not unredacted wire capture; disclose framework metadata/filename limits and advise reviewing before sharing. |
| Troubleshooting and FAQ | Organize by symptom, likely category, and recovery: no presets/invalid selection, stale data or connection loss, blocked start/occupied bottle, accepted request without observed start, credential expiry, TLS certificate problems, unknown values, and missing historical records. Point users to diagnostics first; keep advanced safe logging instructions secondary and never ask for credentials or unsanitized socket URLs. |
| Known limitations, support, and attribution | List actual release limitations/deferred controls succinctly, link the actual fork's issue tracker and release notes, explain what to include in a report, and credit upstream/client authors and MIT licensing. Keep contributor/development details short or link a separate document. Do not present the future roadmap as available capability or invent release status, compatibility, approval, or quality-tier badges. |

Readability and maintenance requirements:

- Put a concise purpose/features summary near the top, then installation/configuration and usage references. Readers should quickly answer what it does, whether it supports their device, and how to get started.
- Use plain language, meaningful headings, compact comparison/reference tables, and numbered setup steps. Keep protocol internals and developer architecture out of the main usage path.
- Use GitHub-compatible Markdown and working relative/absolute links. Prefer UI instructions first, with YAML examples as a useful supplement. If using collapsible advanced examples, ensure essential steps remain visible without expanding them.
- Add a small number of accurate project/HACS/version badges or My Home Assistant links only after real repository/status targets exist. Do not imply HACS default-store inclusion, official manufacturer endorsement, or a formal HA quality rating.
- Screenshots are optional. If included, capture the actual implemented standard HA entities/controls, sanitize names/IDs, supply alt text, and avoid presenting a proposed custom dashboard as part of the shipped integration.
- Derive entity/action tables and examples from the completed implementation, not only from this plan. Verify actual labels, attributes, service schemas, error wording, and HA UI paths against the supported version before marking documentation complete.
- Validate example YAML and execute applicable examples against mocked integration state. Check links/anchors and inspect the rendered README on GitHub or an equivalent Markdown preview. A fresh-install/upgrade walkthrough in isolated HA must be achievable from README instructions alone.
- Update documentation in the same change as user-visible behavior. Keep the README as the main discovery/use reference even if detailed developer or troubleshooting material is split into linked files.

## 11. Autonomous implementation and continuation policy

Stages A–F are one continuous build assignment. Each stage must leave integrated changes, tests, and recorded exit-criterion evidence. Begin immediately, perform validation yourself or through internal subagents, repair failures, and advance. Do not wait for a user message between stages, convert a stage report into a request for sign-off, or end with an offer to continue work that remains in scope.

### Automatic execution and validation policy

1. Execute stages in dependency order, automatically evaluate their exit criteria, record the result, and proceed to the next stage when the criteria pass. These are agent-owned validation checks. A stage boundary, code-review finding, failing test with a viable fix, long-running check, or routine implementation uncertainty is not a stopping point.
2. Use internal subagents where available and helpful, or execute synchronously in the same task. Either mode must produce the same integrated code, validation evidence, and final report. Internal subagents are explicitly authorized; lack of subagent tools must not block progress. Do not create separate user-owned chats or scheduled jobs just to advance stages.
3. In a delegated workflow, the primary agent owns sequencing, shared interfaces, integration, conflict resolution, exit-criterion decisions, and the final report. Assign bounded tasks with explicit file ownership, dependencies, expected tests, and report requirements. Parallelize independent work only after required model/runtime contracts are established; avoid simultaneous conflicting edits to shared files.
4. Require each subagent to return changed files, validations actually run, observed outcomes, remaining concerns, and any deviations. A subagent's assertion that its work is finished is not an exit-criterion pass: the primary agent must inspect the integrated changes and run the relevant checks against the integrated tree. Prefer independent review/test work when helpful; sequential self-review is acceptable when running synchronously.
5. If a required check fails, diagnose and fix the implementation or test environment, rerun affected checks, and continue. Explore materially different remedies when necessary rather than repeating the same unsuccessful step indefinitely. Do not weaken assertions, drop requirements, suppress safety/privacy failures, or relabel a required check optional merely to advance. Retain a concise record of the failure and its resolution.
6. Revalidate earlier criteria when later changes affect them. Evidence is valid for the source revision/tree and environment tested, not every subsequent edit. After integration, run the applicable final suite and package/documentation checks against the final tree; do not rely solely on isolated subagent or earlier-stage results.
7. Resolve routine implementation choices, dependency setup, local test failures, and integration conflicts without user sign-off. Provide concise progress updates describing results and next work; do not substitute progress messages for validation evidence or treat them as approval requests. Questions or status requests from the user steer the work; they do not cancel it unless the user explicitly interrupts, pauses, stops, or replaces the objective.
8. Exercise delegated judgment on architecture, client distribution, supported runtime versions, dependency/tool selection, repository layout, test strategy, work sequencing, and other implementation details. Prefer decisions that preserve the agreed behavior, compatibility, privacy, reproducibility, and maintainability. Record material choices and assumptions in the decision log; uncertainty alone is not a reason to stop and ask the user to choose.
9. Set up or reuse a suitable fork/working repository and isolated environment without a separate planning round. Use available authenticated repository context when its ownership is clear; if remote setup is unavailable, continue implementation and validation in a local Git repository. Resolve install/tool/version issues with compatible environments or equivalent checks where they establish the same criterion. Missing live vendor credentials do not block the offline build. Record what was actually run rather than treating a configured CI workflow as completed validation.
10. Live HA replacement, physical dispensing, and HACS default-store submission are not required exit checks. Use isolated HA and fake cloud data to complete the build. Record any unperformed physical verification as a limitation; do not stop to solicit it. Prepare the installable artifact, README, and reports so the implementation is usable and reviewable without production deployment.
11. Respect applicable platform access controls and protect existing user work. If access prevents a necessary step, first try safe, workable alternatives within the objective. Do not attempt to override enforced controls or expose credentials. Only an irrecoverable obstacle to required completion meets the critical-failure stopping rule below.
12. Continue until all stages and required deliverables are complete. Stop early only for an explicit user interruption or a critical failure. Do not stop because the work spans multiple stages, a subagent finished, a normal test failed, another context continuation is needed, or a reasonable decision has not been made by the user.

### Decision authority and required decision log

Create `docs/IMPLEMENTATION_DECISIONS.md` and keep it current. Make necessary decisions and implement them; the log documents decisions rather than submitting them for approval. Record material implementation choices, interpretations, tradeoffs, departures from suggested technical defaults, and assumptions that could affect behavior or supportability. Routine formatting and trivial local choices need not each receive an entry.

Each entry must include a stable decision ID, date/stage, the question or assumption, decision made, alternatives considered, rationale tied to the objective, scope/compatibility/privacy effects, and validating evidence or follow-up. Note whether the choice is reversible and record later changes/superseding decisions. Link relevant validation evidence and code locations when available. Do not store secrets in either report.

The agreed functional requirements remain authoritative. The agent may adapt architecture, tools, implementation order, and technical defaults to achieve them; it must not silently remove accepted capabilities, expand into unrelated features, invent API support, bypass dispensing safeguards, or hide failed checks. Reconcile apparent technical conflicts using the user-confirmed intent and document the resolution. If no responsible decision can meet a mandatory requirement, treat that as a potential critical failure after investigating alternatives.

### Git workflow in the project folder

Use Git as the implementation's version-control system under S15. Git setup, branches, commits, checkpoints, and integration are part of autonomous execution, not new user-approval gates.

1. Before edits, identify the project's repository root, current branch/HEAD, remotes, working-tree changes, staged changes, and untracked files. Typical inspection commands include `git rev-parse --show-toplevel`, `git status --short`, `git branch --show-current`, and `git log -1`. Inspect remote configuration without exposing embedded credentials. Record the starting revision and relevant initial work in the validation report.
2. Reuse the correct existing project repository. If none exists, clone the upstream/fork into a dedicated project folder, or initialize a local repository in that folder when cloning is unavailable and a usable source copy exists. Preserve source provenance and license attribution. Do not initialize Git in a broad parent/workspace folder containing unrelated projects, create an accidental nested repository, replace an existing `.git` directory, or discard upstream history merely for convenience. If the current folder belongs to an unrelated parent repository, establish the implementation in its own suitable project checkout.
3. Work on a descriptive implementation branch consistent with project instructions, reusing an appropriate existing task branch when available. Record its name and base commit. Create/switch branches only when existing work is preserved. Do not make destructive assumptions about a clean checkout or reset the default branch to obtain one.
4. Preserve pre-existing user changes and their staged/unstaged state. Do not overwrite, discard, silently stash, or include unrelated files in implementation commits. Inspect diffs and stage explicitly owned paths or hunks; avoid indiscriminate staging of the entire workspace. If user and agent edits overlap, preserve the user's work, reconcile the intended change, and document any material resolution.
5. Commit coherent, reviewable changes as the implementation progresses, normally at validated stage milestones or smaller meaningful units. Use clear commit messages describing the behavior/change. Include corresponding tests, README changes, and relevant decision/validation updates. A commit is a checkpoint, not proof of correctness; record actual test outcomes separately. Do not wait until the end to put all work into one unreviewable commit.
6. Before committing, review staged changes for unintended files, credentials, personal fixtures, raw production diagnostics, or private data. Maintain a suitable `.gitignore` for virtual environments, dependency caches, editor/OS files, test caches, and temporary build output. Keep only intentionally selected, sanitized evidence under version control. Deliver generated installation artifacts separately unless the repository deliberately versions them.
7. Use the existing configured Git identity/signing and applicable repository conventions. Do not invent an author identity, change global Git settings, disable required hooks/signing, or use verification-bypass flags merely to get a commit through. Resolve available local configuration from verified context when appropriate, document material choices, and continue independent implementation/validation while diagnosing a Git environment issue under the normal recovery policy.
8. In a shared checkout, the primary agent owns Git index/branch/commit operations. Subagents should return their file changes and validation evidence without competing branch switches, index writes, resets, or commits in that checkout. Use isolated Git worktrees only when appropriate to the repository and task; the primary agent integrates their changes deliberately and reruns affected validation against the resulting tree.
9. Prefer additive commits for corrective work and preserve reviewable history. Do not use destructive cleanup/reset operations, discard user work, rewrite shared history, or force-push. Resolve conflicts within the agreed scope and record meaningful decisions; ordinary merge conflicts are work to resolve, not automatic stopping points.
10. Record tested commit IDs and any uncommitted source-tree/diff fingerprint in `docs/IMPLEMENTATION_VALIDATION.md`. Associate decision-log entries and stage outcomes with the code they describe. If later commits change relevant code, revalidate affected behavior. Documentation-only commits after a source validation must identify the source revision actually tested rather than imply an unrun suite was executed on a different tree.
11. At completion, commit the agent-owned deliverables and report the repository path, branch, base/final commit IDs, and final Git status. If initial unrelated changes remain, describe them without claiming the whole checkout is clean or committing them. Review the final diff against the recorded base to confirm scope, attribution, and absence of private data. Local version control does not require a remote push to complete this assignment.
12. At a user interruption or critical failure, preserve a resumable Git checkpoint where feasible, clearly identify any incomplete/WIP work, and record the revision plus remaining uncommitted owned changes. Never label a WIP checkpoint as a validated release. Git operations must support the continuation policy, not create routine pauses at each commit.

### Critical failure and user-interruption handling

A critical failure is an obstacle that prevents meeting a mandatory requirement and cannot be resolved responsibly using available access, reasonable recovery attempts, alternative tooling/environments, compatible dependency choices, or another sound implementation approach. Examples include inaccessible essential source with no usable copy, an unrecoverable required test/runtime environment, an unfixable safety/privacy/compatibility defect, or an essential external access constraint with no valid fallback. A recoverable error, lack of a preferred tool, missing remote hosting for a locally buildable result, or absence of optional hardware verification is not a critical failure.

Before declaring one, inspect the cause, attempt materially different plausible remedies, and complete any independent required work that can still proceed. Do not use a fixed arbitrary retry count as permission to abandon useful progress. Never mark an unrun/failed requirement as passed to avoid a failure report.

At a critical failure, preserve the source, evidence, decision log, and a resumable checkpoint. Provide:

1. The failed operation/requirement and its practical impact, with a precise explanation of why it prevents completion.
2. Sanitized error evidence, recovery approaches tried, observed results, and why available alternatives are insufficient.
3. The work/stages completed, outstanding requirements, repository/branch/artifact locations, and the exact next step for resuming.
4. Concrete options for proceeding, preferably two or three where viable, with a recommended option, tradeoffs, and any exact user input or external change needed. Do not invent options that cannot work.

If the user explicitly interrupts or pauses, stop launching new work, end active work safely, and save a concise progress checkpoint with remaining steps and validation status. Provide the requested update without calling unfinished work complete. On resumption, continue from that checkpoint and the latest user instructions rather than restarting the project.

### Stage validation ownership and minimum evidence

Use the detailed test matrix in section 12; this table identifies the minimum stage-level evidence to gather automatically. These are offline checks using synthetic data, fake cloud transports, and isolated HA where applicable, not claims of physical-device validation.

| Stage | Required automatic exit-criterion validation |
|---|---|
| A | Record base/current revisions and chosen runtime/client/package decisions; validate sanitized-to-wire fixture conversion; establish a runnable harness and compatibility assertions for original device/summary identity, states, attributes, and action schema. |
| B | Exercise setup/authentication, token rotation, incremental merge/order, manual/reconnect reads, connection failure recovery, shared-session ownership, and repeated unload/reload with a fake transport; confirm no orphaned tasks, duplicate listeners, or leaked secret sentinels. |
| C | Instantiate the agreed read-only entities in HA tests; verify temperature mapping and unknown/availability behavior; verify independent alerts, outside-HA preparation recognition, coherent timestamp/settings snapshots, no unrelated history churn, and Recorder-backed persistence. |
| D | Test selector identity/persistence/deletion and read-only refresh; exercise both start entry paths, all guard conditions, concurrent requests, command ambiguity/timeouts, and restart occupancy handling; assert at most one start write and no automatic replay. |
| E | Retrieve entry/device diagnostics through the HA test download path; verify schema, offline/minimal-runtime behavior, zero vendor-call side effects, pre-merge message/merged-shadow fidelity, count/byte/lifecycle limits, cross-device isolation, and serialized-output/log privacy sentinels. |
| F | Run the supported HA-version matrix and final applicable suite on the integrated tree; validate HACS/hassfest, packaging, translations, install/upgrade in isolated HA, README examples/links/rendering, and final definition-of-done coverage; review representative sanitized downloads and outstanding limitations. |

### Required validation report deliverable

Create `docs/IMPLEMENTATION_VALIDATION.md` in the finished repository and link it in the final implementation response alongside `docs/IMPLEMENTATION_DECISIONS.md`. Keep sanitized supporting artifacts under `docs/validation/` (or an equivalently documented evidence directory). Update the report as work proceeds, then reconcile it with the final integrated code before delivery. Record actual validations only; do not prepopulate successful outcomes for work not yet performed.

The report must include:

- Project repository path, working branch, starting/base and final commit IDs, relevant initial/final working-tree state, and tested revision or source-tree/diff fingerprint when uncommitted changes are being validated; chosen HA/Python/client versions; test environment; execution mode; and any subagent responsibilities. Distinguish the tested source from later documentation-only report edits.
- A summary row for each stage A–F with its exit criterion, status, checks performed, outcome/counts where available, and links to evidence. Use `PASS`, `FAIL`, or `BLOCKED` for evaluated stages; use `IN PROGRESS`, `INTERRUPTED`, or `NOT STARTED` where accurate in an interruption/critical-failure checkpoint. Reconcile results before a completion report.
- For each applicable validation: actual command or test identifier, relevant environment/working directory, execution time/date, observed result/exit status, and an evidence link. Never include credentials, raw personal payloads, or credential-bearing commands/URLs. Record unavailable CI/remote checks honestly rather than claiming that configuring a workflow means it ran.
- Failures encountered, corrective changes, rerun outcomes, and any evidence invalidated/replaced by later edits. Keep this concise; retain useful sanitized output rather than dumping every console line.
- A requirement-to-evidence mapping for S01–S15, the temperature mapping, and the definition-of-done items. Explain any legitimately not-applicable check individually; missing access or an unimplemented requirement is not “not applicable.” Link material implementation decisions to their validation and resulting behavior.
- Automated validation separated from code review, simulated HA/cloud behavior, optional hardware validation, and publication/deployment. List hardware checks not performed and the limitations that therefore remain.
- An overall result: implementation complete with required automated validation passed, or an explicit user-interruption/critical-failure checkpoint with unresolved items. Do not issue an early final report for merely recoverable unfinished work; continue correcting it. Required failed/blocked automated checks prevent a claim that all stages passed. Optional unperformed hardware checks do not invalidate an accurately labeled offline-validation result.

Supporting artifacts may include test summaries/JUnit output, validator output, sanitized diagnostic snapshots, packaging/file inventories, and documentation review evidence. Keep them bounded, readable, and secret-free; do not commit full virtual environments, caches, unrestricted logs, production exports, or appliance histories. The final user-facing report should link the consolidated report and briefly summarize each stage's result without requiring the user to inspect every artifact.

### Stage A — Establish the baseline and fixtures

1. Read applicable repository instructions; inspect current upstream diffs against the pinned references.
2. Record source SHAs, chosen HA/Python test baselines, packaging layout, and client distribution choice.
3. Establish a test harness using synthetic wire-format fixtures derived from the supplied sanitized export.
4. Add baseline compatibility tests for existing device/summary identity, states, attributes, and `fpa.turn_on` service schema before refactoring.
5. Initialize the validation report and decision log, and record material bootstrap choices immediately rather than reconstructing them only at the end.
6. Establish the project Git root/implementation branch, preserve initial changes, add appropriate ignore rules, and create a meaningful baseline/first implementation checkpoint as appropriate to the existing history.

Exit criterion: baseline behavior and agreed scope are traceable; no cloud credentials or raw personal fixtures are needed to run tests.

### Stage B — Establish client/runtime reliability

1. Add typed normalized models and required raw-shadow accessors.
2. Correct partial-update handling, HTTP error parsing, nullable fields, task ownership, reconnect failures, and close behavior in the controlled client boundary.
3. Integrate shared HA session, typed runtime ownership, token persistence, and per-device update/operation locks.
4. Implement initial/reconnect/manual read reconciliation without separate entity pollers.

Exit criterion: setup, push, refresh, reconnect, and unload produce one coherent state stream per machine with no leaked tasks or secrets.

### Stage C — Add read-only entities and last preparation

1. Add current-setting sensors and nine binary sensors with correct missing-value semantics.
2. Add the single timestamp sensor, source reconciliation, atomic settings snapshot, restoration as needed, and latest-only reconnect behavior.
3. Preserve the summary entity/service contract and add heating/cooling/uncertain state handling without discarding old states.

Exit criterion: all read-only outputs match fixtures, on-device/app preparations update history, and unrelated settings/refreshes do not churn its attributes.

### Stage D — Add preset controls and shared guards

1. Implement stable-ID dropdown labels and persistence.
2. Add the read-only Refresh data button and the dispensing Start selected preset button.
3. Route both legacy and button starts through the same serialized preflight and occupancy policy.
4. Add visible translated failures, bounded pending state, indeterminate-result handling, and no automatic command replay.

Exit criterion: no entry path can bypass protection; renamed/deleted/duplicate presets and concurrent requests behave as specified.

### Stage E — Add native diagnostics

1. Instrument bounded sanitized runtime operation summaries and per-machine pre-merge received-message capture.
2. Implement entry/device download hooks, the allowlisted report, and consistent redacted raw-message/merged-shadow sections.
3. Add sentinel privacy tests, snapshot tests, unavailable-runtime cases, cross-device isolation, receipt ordering, count/size eviction, oversized payload handling, and lifecycle-reset tests.

Exit criterion: a downloadable report explains the major failure categories while offline, includes the bounded received-message window and latest merged shadow, performs zero vendor calls, and contains none of the seeded private values.

### Stage F — Package, document, and validate

1. Finalize HACS layout/metadata/translations/attribution and the comprehensive user README required by S12, including migration/rollback, complete entity/action references, practical examples, diagnostics, and limitations.
2. Run the test matrix and validation workflows; inspect representative downloaded JSON.
3. Validate fresh install and upgrade from the old integration in an isolated HA instance with a fake API by following the README alone; validate its action examples and inspect rendered Markdown/navigation.
4. Finalize `docs/IMPLEMENTATION_VALIDATION.md` with stage A–F results, requirement/checklist evidence, corrections/reruns, unresolved issues, and known limitations. Ensure its results refer to the final integrated source tested.
5. Package a reproducible installable artifact and finalize `docs/IMPLEMENTATION_DECISIONS.md`. Record the hardware-validation boundary in section 13 without waiting for a physical test or production installation.
6. Review the final project diff and Git status, commit agent-owned deliverables, and record final branch/revision/status information alongside the source revision actually validated.

Exit criterion: all required automated checklist items are met, the installable artifact/README/reports are delivered, and evidence refers to the final source tested. Record unperformed hardware checks separately. Recover required failed/blocked checks autonomously; only an unresolved critical failure prevents further progress and requires the failure/options report.

## 12. Required test matrix

Tests must verify behavior and failure boundaries rather than simply mirror method implementations. Use HA's supported test patterns compatible with the chosen test baseline; if using a custom-integration pytest harness, pin a version compatible with each HA matrix target. Run applicable validations automatically at each stage, retain evidence in the report, and rerun affected checks after integration or corrective changes. No real vendor login or appliance command belongs in CI.

| Test family | Required cases and expected evidence |
|---|---|
| Setup/auth | Existing refresh-token entry loads; rotated token persists; real invalid credentials trigger reauth; DNS/TLS/5xx failures remain connection errors; failed setup cleans resources. |
| Identity/compatibility | Existing summary/device/unique ID preserved; user customizations survive; legacy action schema and target remain; meaningful old attributes and state strings remain. |
| Normalization | String/int epoch and volume parsing; null formula and null preset ID; temperature codes `0`, `1`, and `2` map to the exact supplied labels/enum states; code `0` is not treated as absent; unexpected codes remain unknown with raw diagnostic evidence; historical codes and legacy numeric attributes are preserved; unknown setting/unit and malformed optional data do not crash all entities; unknown is not coerced to false/zero. |
| Push merge/order | Incremental updates preserve sibling fields; explicit null handled; new/old versions reconciled; out-of-order details response does not regress newer push state; invalid device message isolated. |
| Availability | HA socket open/device disconnected; socket lost/device cached true; missing critical fields; disconnected last-preparation snapshot remains historical rather than falsely live. |
| Heating/cooling | Both independent flags available; simultaneous flags do not disappear; missing flags remain unknown; summary/preflight do not claim readiness while active/unverified. |
| Preparation recognition | No HA request; no observed activity transition; a full cloud lastBottle/log still updates the timestamp sensor. Origin remains unspecified. |
| Preparation identity | Same settings on successive bottles; duplicate delivery; equal timestamps with distinct record IDs; nullable IDs; out-of-order records; no timestamp regression. |
| Snapshot integrity | Late/partial lastBottle update cannot combine new timestamp and old settings; matching log enriches only the same preparation; current-setting/preset edits do not rewrite history. |
| Recorder behavior | At least two distinct timestamp snapshots are stored with correct companion attributes in a Recorder-backed test; duplicate unchanged input does not add another meaningful preparation change; no archive or direct DB write is used. |
| Reconnect/history | Several records discovered after outage publish only newest; no replay; original completion time is sensor value; no fabricated completion during refresh/start request. |
| Selector | Selection does not call vendor writes; stable ID survives rename/restart; duplicate/blank names; deleted preset invalidates selection; no automatic fallback; multi-device isolation. |
| Refresh | Reads current presets/settings/history; no start/write call; no extra subscriptions; deletion/rename visible; repeated presses coalesce; error reported; guard not reset. |
| Start validation | Wrong/missing preset; other-device ID; disconnected device; missing bottle; low water; open lid; funnel removed/cleaning; heating/cooling; unknown safety fields. Both button and legacy service reject consistently. |
| Start concurrency | Rapid double press and simultaneous legacy/button request result in at most one PUT; dropdown changes mid-command do not switch requested ID. |
| Command outcomes | HTTP success without observed start; real start; timeout before/after transmission; auth/network failure; no automatic replay; pending state does not stick forever; ambiguous outcome remains guarded. |
| Occupancy/restart | On-device completion guards present bottle; refresh cannot clear it; observed removal/replacement clears appropriately; restart with uncertain present bottle requires a check; disabled summary does not disable tracking. |
| Lifecycle | Repeated reloads leave no duplicate listeners or pending tasks; reconnect handshake/ping failures recover; shared HA session remains open; unload cancels delayed work. |
| Diagnostics content | Entry/device schemas and snapshots; all required state/guard/freshness sections; missing runtime; device offline; stale data; recent failed operation has safe meaningful reason. |
| WebSocket diagnostic capture | Partial messages preserved before merge; subsequent merges cannot change captured copies; duplicate/out-of-order messages retained in receipt order; timestamps/sequence recorded; last 20 limit; 256 KiB cap/oldest eviction; oversized metadata-only entry; unknown/non-JSON handling cannot break state processing. |
| WebSocket diagnostic lifecycle | Per-machine isolation; empty startup window explained; reconnect preserves window within entry lifetime; unload/reload/restart clears it; download does not clear it or trigger state updates; raw buffer and merged snapshot appear together. |
| Diagnostics privacy | Sentinel secrets in integration-controlled config, raw shadow, individual raw messages/subjects, names, URLs, exceptions, nested lists, and unfamiliar fields never appear; IDs aliased consistently across raw/normalized sections; other-device info absent; source objects unmodified. Inspect the actual framework wrapper/filename and disclose any HA-controlled metadata. |
| Diagnostics side effects | Download makes no vendor calls, changes no runtime state, writes no files, and is bounded in size. |
| Packaging/localization | All shipped files load from the HACS artifact; literal English strings render; hassfest/HACS checks pass; minimum/current HA targets pass; fork cannot coexist as another `fpa` implementation. |
| README accuracy and usability | Complete capability/entity/action reference agrees with the implementation; standard and integration-defined actions are distinguished; YAML examples parse and work against mocks; installation/upgrade succeeds from README alone; links/anchors/rendering work; temperature/history/diagnostic limits and privacy are accurate; no template placeholders, personal screenshots, fabricated compatibility, or roadmap-as-feature claims remain. |

## 13. Physical verification boundary: not a build-completion gate

Complete this assignment using automated tests, isolated HA, fake cloud transports, and agent review. Missing physical-device access must not delay or stop implementation. Do not claim these checks establish unobserved hardware behavior. Do not deploy into the user's live HA, change formula/powder settings, create production presets, or start physical dispensing simply to make an implementation test pass.

The following hardware checklist is for subsequent operational verification and reporting only; it requires no action from the user to finish the autonomous build:

1. The original entity and automations remain identifiable after upgrade.
2. Dropdown names match the app, selecting does not alter the machine, and refresh detects a deliberate app-side preset change.
3. Machine-initiated preparation updates last-preparation time/settings without any HA start request.
4. A deliberately requested HA preparation produces one command and the expected live status/history.
5. Another start is blocked while the completed bottle remains present; removal/replacement restores eligibility.
6. Heating/cooling and genuine observable alerts reflect machine state without inducing hazardous faults.
7. Restart/reload preserves selection and conservative occupied-bottle handling.
8. Native diagnostics downloads from the entry and device pages and explains a benign blocked-start/connection case without credentials or personal labels. Confirm received WebSocket JSON is included before merging, with receipt timestamps, redactions, and the separate latest merged shadow.

A live preparation is not necessary to finish the implementation assignment. Record physical confirmation as not performed where applicable, deliver the completed build/reports, and distinguish that limitation from any required automated check that failed.

## 14. Definition of done

Every checked item must have evidence: test name/result, validation output, reviewed file, or a recorded observation. Keep this checklist in the repository, update it as work proceeds, and map each item to `docs/IMPLEMENTATION_VALIDATION.md`. Apply these checks automatically and continue through them without user stage sign-off. Completion means the implemented, validated, packaged integration plus README and reports; production deployment is not a dependency.

### Scope and compatibility

- [ ] S01: Per machine, three current-setting sensors and nine binary sensors exist with documented semantics; the temperature enum uses the supplied `0`/`1`/`2` mapping and preserves raw codes in legacy/historical data.
- [ ] S02: Original domain, device identifier, summary unique ID/entity references, and `fpa.turn_on` service/argument survive upgrade.
- [ ] Existing summary raw states/attribute keys remain compatible; new states/metadata fixes are documented.
- [ ] No deferred frontend, archive, counters, estimates, writable settings, firmware/error entities, new event system, or unsupported commands slipped into the change.
- [ ] Expected entity set is documented (17 per machine including summary), with any necessary deviation explained.

### Presets and controls

- [ ] S03: Named dropdown and Start selected preset button exist for each machine; selection performs no cloud write.
- [ ] S04: Stable selected ID survives restart/rename; duplicates are disambiguated; deletion invalidates without fallback.
- [ ] S05: Refresh updates presets, current data, and latest preparation without reconnect duplication or guard reset.
- [ ] Both command entry paths use the same per-device lock, preset-ownership validation, fresh preflight, and start policy.
- [ ] S06: Occupied/uncertain bottle prevents another start, including after restart and on-device preparations.
- [ ] Start failures are visible and translated; pending/indeterminate states are bounded and safe; commands are not automatically replayed.

### Preparation history

- [ ] S07: Exactly one last-preparation timestamp entity per machine has coherent recorded settings attributes.
- [ ] Preparations initiated outside HA update it; no initiator claim is inferred from missing/present preset IDs.
- [ ] Identical consecutive settings remain distinct; duplicate unchanged records do not create another preparation change.
- [ ] Current settings, preset edits, and diagnostics do not rewrite last-preparation attributes.
- [ ] S08: Reconnect publishes newest only, without backfill/replay or direct Recorder writes.
- [ ] Recorder integration test verifies timestamp/settings association; retention and observation-time limits are documented.
- [ ] No separate preparation-history persistence was added; local storage holds only selection/minimal guard metadata.

### State, lifecycle, and diagnostics

- [ ] S09: Heating/cooling come from real raw fields, with unknown handling; firmware/error entities remain deferred.
- [ ] Push, manual refresh, setup, reconnect, and command preflight converge without stale overwrites.
- [ ] Transport/device connectivity are distinguished; critical missing values do not become ready/false.
- [ ] Token rotation/reauthentication and failure classification are tested; TLS verification remains enabled.
- [ ] Reload/unload leave no duplicate listeners, tasks, or closed shared HA sessions.
- [ ] S10: Native Download Diagnostics works at entry and device level, including offline/minimal-runtime cases.
- [ ] Report covers freshness, presets/selection, guards, last preparation, and recent safe operation outcomes.
- [ ] S11: Diagnostics include up to 20 pre-merge received JSON updates per machine plus the latest merged raw shadow, with UTC receipt times, message subjects, stable receipt ordering, consistent aliases, and privacy redaction.
- [ ] Message count/byte limits, oldest-entry eviction, explicit oversized-payload omissions, empty windows, reconnect preservation, and reload/restart resets are tested; no buffer is written to disk, Recorder, entity attributes, or normal logs.
- [ ] Diagnostics are cached/read-only, bounded, cross-device isolated, and reviewed by the agent as part of validation.
- [ ] Privacy tests prove seeded integration-controlled secrets/names/identifiers cannot survive in the serialized report or captured logs; HA-controlled wrapper/filename metadata has been inspected and documented.
- [ ] Diagnostic JSON and entity output do not expose raw WebSocket authorization URLs or unsanitized exceptions.

### Packaging, tests, and handoff

- [ ] Chosen source SHAs, client distribution/attribution, supported HA/Python baselines, and maintenance tradeoffs are recorded.
- [ ] HACS layout, manifests, version, translations, brand assets, license, and dependency declarations are valid.
- [ ] HACS validation, hassfest, lint/format, and meaningful test matrix pass on the minimum and current supported HA versions.
- [ ] Fresh-install and upgrade-from-upstream scenarios pass in isolated HA with fake cloud data.
- [ ] A reproducible installable artifact is delivered with the correct integration layout and required runtime files; the final response links it with the README and reports.
- [ ] S12: Comprehensive root README explains purpose/capabilities, prerequisites, HACS/manual installation, configuration/upgrades, every provided entity/action, practical usage, start protection, data/history, diagnostics/privacy, troubleshooting, limitations, support, and attribution.
- [ ] README entity/action tables and temperature/history/message-buffer descriptions match the completed release; standard HA actions are distinguished from `fpa.turn_on`.
- [ ] README examples validate against mocked state; a fresh install/upgrade can be completed from its instructions alone; links/anchors and rendered Markdown have been reviewed.
- [ ] README has no unfinished template text, unverified badges/compatibility promises, private screenshots, or deferred features represented as available.
- [ ] No original user export, credentials, child-identifying fixture, or personal screenshot appears in committed files.
- [ ] S13: Stages A–F progressed continuously through validated exit criteria using subagents or a synchronous workflow; the only early stopping conditions were an explicit user interruption or a documented critical failure after reasonable recovery efforts.
- [ ] S14: `docs/IMPLEMENTATION_DECISIONS.md` documents material agent choices/assumptions, rationale/alternatives, scope effects, and validation, with no routine approval dependency.
- [ ] S15: Git is used in the project's own repository on a recorded implementation branch, with meaningful commits/checkpoints, preserved initial user changes, explicit staging, and no unrelated/private files included.
- [ ] Final Git diff/status and base/final/tested revisions are recorded; agent-owned deliverables are committed, any unrelated remaining changes are identified, and validations remain traceable to the tested code.
- [ ] Any critical-failure/interruption checkpoint preserves completed work and evidence; a critical-failure report explains impact, remedies tried, remaining work, and concrete proceeding options with a recommendation.
- [ ] Final integrated-source checks and affected earlier checks were rerun as needed; results are tied to the tested revision/tree and are not based only on isolated subagent assertions.
- [ ] `docs/IMPLEMENTATION_VALIDATION.md` contains each stage's checks/outcomes/evidence, failures/corrections/reruns, requirement/checklist mapping, unresolved items, and separate hardware/deployment status; the final response links it and the decision log.
- [ ] Final implementation report distinguishes completed automated checks, pending live validation, known vendor limitations, and any release/deployment work not performed.

## 15. Reference index for the implementing agent

Reopen the applicable official pages when implementing; APIs and packaging rules can change. The source revisions in section 2 preserve the reviewed baseline.

| Topic | Primary reference |
|---|---|
| Existing integration | [Pinned ha-fpa source](https://github.com/joncar/ha-fpa/tree/d69d8c0a765f8137a04e38f6ae3ea4f95120c488) |
| Existing protocol client | [Pinned pybabyfpa source](https://github.com/joncar/pybabyfpa/tree/8f91cdbc38025d753dcd437f15fedeea5c63253a) |
| HACS integration repository requirements | [HACS integration publishing](https://www.hacs.xyz/docs/publish/integration/) |
| HACS metadata/versioning | [HACS general publishing](https://www.hacs.xyz/docs/publish/start/) |
| README usage requirement | [HACS README guidance](https://www.hacs.xyz/docs/publish/start/#readme) |
| User-facing documentation structure | [HA integration-page structure](https://contributors.home-assistant.io/writing/reference/integration-page/) |
| HACS-linked README presentation example | [Integration blueprint](https://github.com/ludeeus/integration_blueprint) |
| HACS CI | [HACS validation action](https://www.hacs.xyz/docs/publish/action/) |
| HA integration layout | [Integration file structure](https://contributors.home-assistant.io/core/integrations/file-structure/) |
| HA manifest | [Manifest reference](https://contributors.home-assistant.io/core/integrations/manifest/) |
| Data fetching/push coordinator | [Fetching data](https://contributors.home-assistant.io/core/integrations/fetching-data/) |
| Config entry lifecycle | [Config entries](https://contributors.home-assistant.io/core/integrations/config-entries/) |
| Runtime ownership | [Runtime-data rule](https://contributors.home-assistant.io/core/quality-scale/runtime-data/) |
| Shared HTTP session | [Inject-websession rule](https://contributors.home-assistant.io/core/quality-scale/inject-websession/) |
| Setup/auth failures | [Setup failures and exceptions](https://contributors.home-assistant.io/core/integrations/setup-failures/) |
| Sensor/restore semantics | [Sensor entity](https://contributors.home-assistant.io/core/entities/sensor/) |
| Binary sensor semantics | [Binary sensor entity](https://contributors.home-assistant.io/core/entities/binary-sensor/) |
| Dropdown | [Select entity](https://contributors.home-assistant.io/core/entities/select/) |
| Buttons | [Button entity](https://contributors.home-assistant.io/core/entities/button/) |
| Native download/privacy | [Diagnostics](https://contributors.home-assistant.io/core/integrations/diagnostics/) |
| Native wrapper/download behavior | [HA diagnostics implementation](https://github.com/home-assistant/core/blob/dev/homeassistant/components/diagnostics/__init__.py) |
| English/localized text | [Translations, especially custom integrations](https://contributors.home-assistant.io/core/integrations/translations/#custom-integrations) |
| Recorder/retention | [Recorder](https://www.home-assistant.io/integrations/recorder/) |
| Engineering checklist | [All integration quality rules](https://contributors.home-assistant.io/core/quality-scale/rules/) |
| Custom component validation | [Hassfest for custom components](https://contributors.home-assistant.io/blog/2020/04/16/hassfest/) |
| Local persistent-state helper implementation | [HA storage helper](https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/storage.py) |
| Local restore-state helper implementation | [HA restore-state helper](https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/restore_state.py) |

## 16. Execution directive: begin building and continue to completion

Begin implementing the Formula Pro Advanced WiFi integration now according to these instructions and the definition-of-done checklist. Establish or reuse a suitable fork/working repository, inspect current upstream source and applicable repository instructions, set up the environment, and preserve the agreed scope and existing identities/actions. Use the sanitized reference only as fixture input, reconstructing actual vendor wire-format payloads. Implement entities, shared push/read reconciliation, preset selection/start/refresh controls, conservative shared guards, latest-only Recorder history, and native redacted diagnostics including the last 20 received WebSocket updates per machine and the latest merged shadow. Ship the comprehensive user-facing root README specified by S12, with accurate capabilities, complete entity/action references, verified setup/use examples, diagnostics/privacy, limitations, and support guidance modeled on HACS documentation conventions.

Execute stages A–F as one continuous implementation task under S13. Use internal subagents where helpful and available, or work synchronously. Automatically run exit-criterion checks, fix failures, revalidate affected work, integrate delegated changes, and continue. The primary agent owns the integrated result and actual validation evidence. Exercise judgment in the objective's best interest and document material choices in `docs/IMPLEMENTATION_DECISIONS.md` under S14. Use Git in the project folder throughout under S15: inspect/preserve existing work, establish the implementation branch, make coherent commits/checkpoints, and record tested revisions and final status. The primary agent coordinates Git operations in any shared checkout. Do not wait for manual validation, a stage approval, a routine implementation decision, a preferred tool, a physical test, or a production deployment. Preserve user work and comply with actual platform access controls while pursuing workable alternatives.

Continue until completion, an explicit user interruption, or a critical failure meeting section 11's definition. Ordinary failures require investigation and correction, not an early final response. At a critical failure, preserve a resumable checkpoint and provide the failure description/impact, evidence, remedies attempted, and concrete options for proceeding with a recommendation. At a user interruption, preserve progress and follow the user's direction. Never mark an unavailable or failed required check as passed.

Maintain and deliver `docs/IMPLEMENTATION_VALIDATION.md` with per-stage status, exact checks/outcomes, sanitized supporting evidence, tested revision/environment, failure/correction/rerun history, S01–S15/checklist mapping, and remaining limitations. Run required final checks against the integrated source. Deliver the installable artifact, README, validation report, and decision log; the final response must link them, summarize stage A–F results, and identify the project repository, branch, final commit, and any remaining working-tree changes. Keep tests offline and do not send physical dispensing commands as part of automated validation. Make the result reproducible and HACS-installable, document the chosen API-client distribution and minimum HA version, and distinguish validated implementation behavior from unperformed physical confirmation. Do not expand the feature set or claim unverified API capabilities. Begin work rather than returning another plan or asking whether to proceed.
