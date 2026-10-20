# HA - Formula Pro Advanced user guide

[← Integration overview](../README.md)

Installation, configuration, daily operation, entity and action references, preparation history, and troubleshooting for HA - Formula Pro Advanced.

Monitor a Baby Brezza Formula Pro Advanced **WiFi**, select a saved cloud preset, deliberately start a preparation, and see its latest reported preparation in Home Assistant. Independent alerts and a native diagnostics download help explain stale data and blocked starts.

This community fork extends [joncar/ha-fpa](https://github.com/joncar/ha-fpa). It is independent of Baby Brezza and is not endorsed by the manufacturer. Version **1.0.0** retains the `fpa` domain, original summary entity, and `fpa.turn_on` action.

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration and upgrades](#configuration-and-upgrades)
- [Everyday use](#everyday-use)
- [Entities](#entities)
- [Temperature settings](#temperature-settings)
- [Actions and examples](#actions-and-examples)
- [Start protection](#start-protection)
- [Updates and preparation history](#updates-and-preparation-history)
- [Download diagnostics](#download-diagnostics)
- [Troubleshooting](#troubleshooting)
- [Limitations and support](#limitations-and-support)
- [Development and attribution](#development-and-attribution)

## Requirements

- **Home Assistant 2025.10.4 or newer**. Automated integration tests use **2025.10.4** (Python 3.13) and **2026.10.2** (Python 3.14). The supported minimum covers a prior annual HA release cycle using tested runtime ownership, restoration, entity and diagnostics APIs; compatibility with earlier HA is not claimed.
- A **Formula Pro Advanced WiFi** and manufacturer account, with the machine and saved presets already configured in the manufacturer's app.
- Internet access from HA and the appliance. This integration uses the vendor cloud; it provides no local-only control. Other models and non-WiFi machines are untested.

This build is validated with isolated HA instances and fake cloud transports. Hardware behavior and production installation have not been physically verified for this release. See [validation](IMPLEMENTATION_VALIDATION.md) for the exact evidence and boundary.

## Installation

### HACS custom repository

Use [samueldowd/fpa](https://github.com/samueldowd/fpa) as a HACS custom repository. The steps below install the source published in that repository; HACS default-store inclusion is separate.

1. Open **HACS**, open its top-right menu, and choose **Custom repositories**.
2. Add `https://github.com/samueldowd/fpa` with type/category **Integration**.
3. Find **HA - Formula Pro Advanced**, open it, and choose **Download**.
4. Restart HA, then follow Configuration below. Downloading files in HACS does not add the account integration.

HACS reads the conventional `custom_components/fpa` directory from the published repository. No separate Python package or install-time code download is needed.

### Manual installation from this delivery

1. Make a normal HA backup. If replacing upstream, follow the upgrade instructions before copying files.
2. Extract `fpa-1.0.0.zip` into your HA configuration directory. The result must be **`<config>/custom_components/fpa/manifest.json`**, alongside `__init__.py`, the entity platforms, `translations/`, `vendor/`, and `brand/`. Do not add an extra `fpa-1.0.0` directory level.
3. Restart HA, then add the integration. Source users can copy this repository's complete `custom_components/fpa` directory instead.

## Configuration and upgrades

For a new account, open **Settings → Devices & services → Add integration**, find **HA - Formula Pro Advanced**, and enter the email/password used in the manufacturer's app. Credentials are submitted through the normal HA config flow. HA stores the refresh token; the integration does not retain the password or persist access tokens. Rotated refresh tokens are saved automatically. If authentication expires, use the integration's **Reauthenticate** flow and enter credentials again.

Each account can provide multiple machines. New accounts are deduplicated by an established account identity when available. Existing upstream entries retain their identity/version; a legacy entry with a customized account title may not be recognized as a duplicate, so reuse it instead of adding it again.

### Replacing upstream and rolling back

1. Back up HA. Keep a copy of the installed upstream files or its versioned archive.
2. Use only one `fpa` implementation. Remove the old upstream repository from HACS management **without deleting the integration in Settings or its registry records**. If HACS removes the files, restore the replacement before restarting.
3. Replace the contents of `<config>/custom_components/fpa` with this fork's complete directory. Do not keep a second copy under another folder/domain.
4. Restart HA. The existing refresh-token config entry, summary unique ID, device identity, custom names, areas, and automation references are reused. New entities appear on the same device page.
5. For future published updates, download in HACS and restart HA as prompted. Review [release notes](RELEASE_NOTES.md).

To roll back, stop HA, replace this directory with the saved upstream version, and restart. Keep the existing config entry and original summary registry record. New entities will no longer be supplied by upstream; their history remains subject to Recorder retention. Minimal fork selection/guard storage is not a preparation archive. Restore your normal HA backup if a full rollback is required.

To remove the integration, remove its account entry in Devices & services, then remove its files through HACS or manually and restart. Deleting entries/entities is unnecessary for an upgrade.

## Everyday use

1. Open the machine in **Settings → Devices & services → Devices**.
2. Check the configured values in the manufacturer's app and the **Bottle preset** dropdown's selected attributes. A title can disagree with its configured volume, powder setting or mode; configured cloud values determine the command.
3. Choose a named preset in **Bottle preset**. Selection stays local to HA: it neither changes machine settings nor starts dispensing.
4. When you intentionally want a preparation, check the machine/bottle and press **Start selected preset** once.
5. Observe **Making bottle**, the summary, and **Last preparation**. An accepted request is not proof that the appliance started or completed.

The selected **ID** survives HA restarts and preset renames. Duplicate names gain stable ID suffixes; unnamed presets use `Preset <id>`. A deleted selection is invalidated and never replaced automatically, even if that ID later reappears. Choose a valid preset again. **Refresh data** discovers changes made in the app without reloading the integration.

## Entities

Every machine has **17 entities**: five sensors, nine binary sensors, one select and two buttons. All new entities are enabled by default. Examples use synthetic names; actual entity IDs depend on HA naming and your customizations. New unique IDs use the original device ID plus a stable suffix; the original summary's unique ID stays unchanged.

Live settings, alerts, summary and Start are unavailable unless the cloud transport is connected and a usable snapshot reports the appliance online. An absent field is **unknown**, not zero/false. Last preparation remains historical through outages; the dropdown can use cached presets, and Refresh can be attempted while the appliance is offline.

### Sensors

| Display name | Value and meaning | Attributes/limits |
|---|---|---|
| Existing machine summary | Existing machine name and prioritized enum state | Preserves numeric `temperature`, `powder`, `volume`, `volume_unit`, activity/mode/alert attributes and `bottle_<id>` preset descriptions. |
| Selected volume | Numeric quantity in the reported unit (`oz` is a volume setting) | No mass conversion or statistical state class; not final mixture volume. |
| Temperature setting | Room Temperature, Body Temperature, Above Body Temperature | `temperature_code` retains the raw code. Unexpected codes produce unknown. No degrees unit. |
| Powder setting | Numeric configured setting | No mass/concentration unit or statistical state class. |
| Last preparation | Cloud completion timestamp, timezone-aware internally | `record_id`, `volume`, `volume_unit`, `temperature_setting` (numeric), `powder_setting`, `water_only`, `preset_id`. Nullable IDs/mode remain null. One historical snapshot; no state class. |

Summary raw states retained: `requesting_bottle`, `making_bottle`, `full_bottle`, `funnel_cleaning_needed`, `funnel_out`, `lid_open`, `low_water`, `bottle_missing`, `ready`. Added states: `heating`, `cooling`, and `bottle_check_needed`. Unknown readiness does not produce `ready`. The unsupported custom `fpa__state` device class is replaced by HA's enum metadata without recreating the entity. Alert priority remains compatible; independent alerts show simultaneous conditions.

### Binary sensors

| Name | True means | False means |
|---|---|---|
| Making bottle | Machine reports preparation running | Machine reports not running |
| Water only | Reported water-only mode | Reported formula mode; names do not determine this |
| Bottle missing | Bottle reported absent | Bottle reported present; emptiness is not established |
| Funnel cleaning needed | Cleaning alert active | Alert explicitly clear |
| Funnel removed | Funnel reported removed | Removal alert explicitly clear |
| Lid open | Lid reported open | Lid explicitly closed |
| Low water | Low-water alert active | Alert explicitly clear |
| Heating | Heating activity reported | Activity explicitly false; no measured temperature |
| Cooling | Cooling activity reported | Activity explicitly false; no measured temperature |

Making bottle uses HA's running class; funnel/low-water alerts use problem semantics; Lid open uses opening semantics. Bottle missing retains true = missing without an inverse class. Unsupported/missing heating/cooling values remain unknown and cannot establish readiness.

### Select and buttons

| Name | Function | Availability and attributes |
|---|---|---|
| Bottle preset | Choose a named cloud preset locally | Cached valid list permitted offline. Selected `preset_id`, volume/unit, temperature/powder codes, mode, and description. No automatic first selection. |
| Start selected preset | Deliberately start the selected preset | Requires live state and all shared safeguards. Uses the current cloud definition after fresh preflight. |
| Refresh data | Fetch details, presets, settings, alerts and latest preparation | Diagnostic category. Account reads may work while the machine is offline. Repeated requests coalesce; manual successes have a five-second cooldown. No machine write. |

## Temperature settings

| API code | HA enum state | Display label |
|---|---|---|
| `0` | `room_temperature` | Room Temperature |
| `1` | `body_temperature` | Body Temperature |
| `2` | `above_body_temperature` | Above Body Temperature |

These are settings, not measured water temperatures. Historical `temperature_setting` and the original summary's `temperature` remain numeric codes. Code `0` is valid. No Celsius/Fahrenheit values are guessed.

## Actions and examples

The integration-defined **`fpa.turn_on`** action targets the **original summary sensor** and requires a positive integer `bottle_id`, belonging to that machine. Find IDs in the original sensor's `bottle_<id>` attributes or select a preset and read its `preset_id` attribute. This action does not change the dropdown selection. Wrong targets/IDs, blocked starts and failed/indeterminate commands raise visible HA errors; older automations expecting a silent return may now stop with an error.

**`select.select_option`** and **`button.press`** are standard HA actions. There is no integration-defined `fpa.start_selected_preset` service. These examples use synthetic entity IDs and preset ID `1001`; replace them with your actual entities/ID and exact dropdown option text.

### Intentionally select and start

Run this script only when you deliberately want the appliance to dispense. Selecting the option alone does not dispense.

```yaml
alias: Intentionally prepare selected preset
mode: single
sequence:
  - action: select.select_option
    target:
      entity_id: select.example_baby_brezza_bottle_preset
    data:
      option: Preset 2oz
  - action: button.press
    target:
      entity_id: button.example_baby_brezza_start_selected_preset
```

### Refresh after app changes

```yaml
alias: Refresh Formula Pro data
sequence:
  - action: button.press
    target:
      entity_id: button.example_baby_brezza_refresh_data
```

### Intentionally start by saved ID

```yaml
alias: Intentionally prepare preset 1001
mode: single
sequence:
  - action: fpa.turn_on
    target:
      entity_id: sensor.example_baby_brezza
    data:
      bottle_id: 1001
```

All dispensing examples use the same guards. There is no bypass action. In the UI, select a preset then deliberately press Start, or use **Developer tools → Actions** for the legacy action.

## Start protection

Both Start and `fpa.turn_on` share a per-machine lock and a **fresh details read**, even within the manual refresh cooldown. HA verifies preset ownership/connectivity and blocks pending/running requests, absent bottles, low water, open lids, removed/unclean funnels, heating/cooling, unknown critical safety values, and occupied/uncertain bottles. Disabling the summary does not disable these checks.

A newly reported preparation marks a present bottle occupied, including preparations initiated through the machine or app. Observe **bottle missing**, then replace the bottle, before another HA preparation. After startup/reconnect, a present bottle with uncertain occupancy requires removal/replacement; Refresh or waiting cannot prove it empty. `bottle_check_needed` explains this conservative state. No reset/bypass button is provided.

The integration sends a start once. A timeout or ambiguous transport failure is not automatically retried. HTTP acceptance, observed running and reported preparation are separate outcomes. A pending request has a 30-second observation window; if no start is observed it becomes guarded/uncertain instead of remaining `requesting_bottle` forever. Examine the machine and diagnostics before another deliberate attempt.

These checks cannot inspect bottle contents, guarantee vendor acceptance, or stop the machine after a request. Formula/powder recommendations, writable settings, preset editing and stop/cancel/pause are outside this release.

## Updates and preparation history

Routine state is **cloud push**. Supplementary REST reads occur on setup, reconnect, manual refresh, start preflight, and bounded preparation reconciliation (an immediate read and at most one delayed retry). There is no periodic REST polling loop. One owned subscription per machine is reused across refreshes; transport connectivity and reported appliance connectivity are distinct.

**Last preparation** uses the newest coherent cloud `lastBottle` snapshot or creation record. It recognizes machine/app preparations without requiring a HA start request. It uses that preparation's settings, never today's preset definition. Names and nullable preset IDs cannot establish who initiated it, and the integration does not classify every preparation as successful.

Recorder supplies normal HA history. The sensor value is the **cloud completion time**; a Recorder observation reflects **when HA learned about it**. Consecutive equal-setting preparations remain distinct through completion timestamps/record IDs. Repeated unchanged deliveries and unrelated setting/preset/diagnostic changes do not rewrite history. A later matching record may enrich a missing ID once, potentially creating another observation with the same completion timestamp.

After an outage, only the newest preparation is published; missed intermediate records are not replayed. A last known snapshot can be restored through HA restoration without implying the machine is online. Recorder must include this sensor for history; your filters and purge/retention rules apply. No separate archive, direct Recorder writes, indefinite long-term statistics, counters or consumption estimates are supplied. See [HA Recorder documentation](https://www.home-assistant.io/integrations/recorder/).

## Download diagnostics

Open **Settings → Devices & services → Integrations**, find **HA - Formula Pro Advanced**, and use the entry's menu → **Download diagnostics**. On a machine's device page, use its menu → **Download diagnostics** for that machine only. These use HA's native download route; no custom service or config-folder file is created.

The report includes authentication/transport/appliance status, freshness and safe errors, settings/alerts, aliased presets/selection, guard block reasons, latest preparation/provenance, up to **50 account operation summaries**, and two distinct raw-data views:

- **Latest merged shadow:** redacted accumulated cloud JSON, including available metadata/version; maximum **256 KiB**. Oversize data is omitted with a size/reason marker.
- **Recent received updates:** up to **20 pre-merge JSON messages per machine**, in receipt order, under a combined **256 KiB** cap per machine. Entries retain partial shape, duplicates/old versions, local sequence, UTC receipt time and safe subject. Counts explain eviction/capture failures. An oversized message becomes a metadata-only omission. An empty window explicitly says no update has arrived since entry load.

Messages are sanitized defensive copies captured before merging. Known non-sensitive values and useful nesting/key spelling are retained; unknown scalars are redacted, and non-schema-like keys are replaced. Credentials, URLs, private names, identifiers and arbitrary server errors are excluded/redacted; corresponding IDs use consistent aliases. Raw means **redacted JSON structure**, not original wire bytes. Downloading performs no vendor request, token rotation, state update or buffer reset. Buffers remain in memory across socket reconnects and reset on entry reload/HA restart; they are not written to entity attributes, disk or Recorder.

**Review before sharing.** Exact timestamps can reveal routines. HA adds system metadata, manifests, installed custom-integration details and integration repair issues around the report. In tested HA versions, device filenames also include the registered device name and registry IDs; the hook cannot anonymize those framework fields/filenames. Rename the downloaded file before sharing if needed and inspect the entire content. Diagnostics cannot reconstruct failures outside their bounded window or prove a remote cause.

## Troubleshooting

| Symptom | Check and recovery |
|---|---|
| No presets / no selection | Create saved presets in the app, press Refresh, and select one. Deletion clears selection without fallback. Inspect the refresh outcome. |
| Bottle check/full bottle blocks Start | Remove the bottle until HA observes Bottle missing, then replace it. Check other real alerts. Refresh/restart is not a reset. |
| Heating/cooling or unknown readiness | Wait for actual flags to clear. Missing flags stay unknown; report unsupported data instead of bypassing guards. |
| Data unavailable/stale | Check internet/cloud access and reported appliance connectivity. A connected HA socket alone is insufficient. Use Refresh and cached diagnostics. |
| Accepted request without running/completion | Check the machine and diagnostics. Allow the observation timeout; do not repeatedly press Start or assume a timeout canceled the command. |
| Credentials expired | Use Reauthenticate. Invalid credentials are distinct from DNS/TLS/timeouts/server failures. |
| TLS/certificate failure | Check system time, certificate trust and network interception/proxy setup. Do not disable certificate verification. |
| Unexpected code/unit/optional field | Unknown values are handled cautiously; the temperature sensor does not guess. Download diagnostics. |
| Missing older preparations | Reconnect is latest-only; Recorder filters/purges apply. No lossless replay or vendor archive export is provided. |
| Legacy automation now errors | Starts report blocked/failed outcomes visibly. Target the original summary and current machine-owned preset ID; inspect the reported condition. |

Diagnostics are the first support artifact. If advanced logging is requested, enable only this integration's logger temporarily through HA's normal controls, reproduce once and turn it off. Review logs before sharing; HA/framework logs can contain registry names and entity IDs. Never paste credentials, raw exports, authorization URLs or a full config directory.

## Limitations and support

The vendor API is unofficial and can change. Only saved cloud presets can start; this release supplies no local control, writable settings, preset editing, firmware/error entities, stop controls, custom dashboard, completion events, notification automations, archive, counters, intake estimates or formula recommendations. It does not measure powder mass, water temperature, final mixture volume or infant intake.

Use the [issue tracker](https://github.com/samueldowd/fpa/issues). Include HA/integration versions, reproduction, observed state/error and **reviewed** diagnostics; [the issue template](../.github/ISSUE_TEMPLATE/bug_report.yml) lists requested information. See [release notes](RELEASE_NOTES.md), [validation evidence](IMPLEMENTATION_VALIDATION.md), and [decisions](IMPLEMENTATION_DECISIONS.md).

## Development and attribution

See [development instructions](DEVELOPMENT.md) for pinned environments, offline tests, official validators and reproducible packaging. The integration uses a narrowly maintained adaptation of [joncar/pybabyfpa](https://github.com/joncar/pybabyfpa) **0.0.7**, origin `8f91cdbc38025d753dcd437f15fedeea5c63253a`; [the origin/change note](../custom_components/fpa/vendor/pybabyfpa/ORIGIN.md) documents its maintenance tradeoff. There is one active client implementation, no monkey patch or runtime Git dependency. Upstream integration origin: `d69d8c0a765f8137a04e38f6ae3ea4f95120c488`.

Original integration/client copyright Jon Caruana, MIT licensed. See [LICENSE](../LICENSE) and the [client license](../custom_components/fpa/vendor/pybabyfpa/LICENSE). The geometric project icon is an original asset, not a manufacturer logo. No HA quality-tier, default HACS-store, manufacturer-approval or physical-validation claim is made.
