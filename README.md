# Formula Pro Advanced WiFi for Home Assistant

Bring your Baby Brezza Formula Pro Advanced **WiFi** into Home Assistant. See what the machine is doing, notice when it needs attention, choose a saved preset, and deliberately start a preparation from the same interface you use for the rest of your home.

[Get started](docs/USER_GUIDE.md#installation) · [Full user guide](docs/USER_GUIDE.md) · [Entity reference](docs/USER_GUIDE.md#entities)

## Why add your Formula Pro to Home Assistant?

The manufacturer's app sets up your machine and saved presets. This integration makes its status and controls available alongside your other Home Assistant devices, so you can check the machine in your existing dashboard and use its reported state in automations you create.

| What you want to do | How the integration helps |
|---|---|
| **See what needs attention** | Separate alerts show low water, an open lid, a removed or unclean funnel, and a missing bottle. Heating, cooling, and preparation activity are visible too. [See the alerts](docs/USER_GUIDE.md#binary-sensors). |
| **Check the reported settings** | See selected volume, temperature setting, powder setting, and water-only mode rather than relying on a preset's name. [Explore the sensors](docs/USER_GUIDE.md#sensors). |
| **Choose a familiar preset and start it intentionally** | A named dropdown remembers your selection; a separate Start button requests preparation. Choosing a preset alone never changes the machine or dispenses. [See everyday use](docs/USER_GUIDE.md#everyday-use). |
| **Check the latest preparation** | A timestamp sensor shows the newest cloud-reported completion with that preparation's settings. Home Assistant Recorder can retain the observations under your normal history settings. [Understand preparation history](docs/USER_GUIDE.md#updates-and-preparation-history). |
| **Pick up changes made in the app** | Refresh data reloads presets and current machine data without restarting the integration. [See the controls](docs/USER_GUIDE.md#select-and-buttons). |
| **Understand a blocked start or connection problem** | Home Assistant's native diagnostics download includes cached status, guard reasons, and bounded, redacted cloud updates. [Diagnose a problem](docs/USER_GUIDE.md#download-diagnostics). |

## Ways to use it in your home

### A quick check from your existing dashboard

Add the machine's status and alert entities to a dashboard you already use. See whether it is making a bottle, heating or cooling, or reporting something that needs your attention. The integration supplies standard Home Assistant entities; you choose how to display them.

### Your own reminders for machine alerts

Use Low water or Funnel cleaning needed as a trigger or condition in an automation you create—for example, to send yourself a notification when an alert appears. These are ways to use the supplied entities; notification automations are not installed for you. [Browse the available alerts](docs/USER_GUIDE.md#binary-sensors).

### A deliberate preparation shortcut

Choose a saved cloud preset, then press **Start selected preset** when you intend to prepare it. Shared safeguards check machine alerts, pending requests, and bottle occupancy before sending a command. [Learn why a start may be blocked](docs/USER_GUIDE.md#start-protection) or [see action and script examples](docs/USER_GUIDE.md#actions-and-examples).

### A shared view of the latest reported preparation

See the latest reported completion and the settings associated with it, including preparations discovered from the machine or app. This is preparation status, not a feeding or intake log. After a connection outage, only the newest preparation is published. [Read the history and retention details](docs/USER_GUIDE.md#updates-and-preparation-history).

## What appears in Home Assistant?

Each machine appears as a device with **17 entities**: five sensors, nine binary sensors, a preset dropdown, and two buttons. Together they cover the machine summary, current settings, individual alerts, latest preparation, preset selection, Start, and Refresh.

State updates arrive through the manufacturer cloud's push connection. Preset selection is remembered across Home Assistant restarts, and renamed presets keep their identity. [See the complete entity catalog](docs/USER_GUIDE.md#entities).

## Getting started

You need a **Formula Pro Advanced WiFi**, **Home Assistant 2025.10.4 or newer**, internet access, and a manufacturer account with the machine and saved presets configured in the app. [Check compatibility and prerequisites](docs/USER_GUIDE.md#requirements).

1. [Install through HACS or manually](docs/USER_GUIDE.md#installation).
2. [Add the integration and sign in](docs/USER_GUIDE.md#configuration-and-upgrades).
3. [Choose a preset and use the standard controls](docs/USER_GUIDE.md#everyday-use).

Already using the original `ha-fpa` integration? This fork preserves its summary entity and `fpa.turn_on` action. Follow the [upgrade and rollback instructions](docs/USER_GUIDE.md#replacing-upstream-and-rolling-back).

## Scope and support

This integration uses saved cloud presets. It does not provide local-only control, preset editing, or stop/pause controls. Reported settings are not measurements of water temperature, powder mass, or infant intake. [Read the limitations](docs/USER_GUIDE.md#limitations-and-support).

For help, start with [troubleshooting](docs/USER_GUIDE.md#troubleshooting) and [reviewed diagnostics](docs/USER_GUIDE.md#download-diagnostics), then [report an issue](https://github.com/samueldowd/fpa/issues). [Release notes](docs/RELEASE_NOTES.md) and the [validation report](docs/IMPLEMENTATION_VALIDATION.md) describe the release and its verification limits.

This is an independent community project, unaffiliated with Baby Brezza, extending [joncar/ha-fpa](https://github.com/joncar/ha-fpa) and its MIT-licensed client. See [development and attribution](docs/USER_GUIDE.md#development-and-attribution) for credits and maintenance details.
