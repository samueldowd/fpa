# Unreleased

- Add Funnel bottles remaining and Reset on each device (19 entities/machine). The local counter starts at 4, decrements once per distinct reported completed preparation, stays within 0–4, persists across restarts, and resets on funnel removal or Reset.
- Keep all existing reported sensors and machine start safeguards independent of this counter; Funnel cleaning needed remains API-derived.

# 1.0.0

Local first-fork build, 2026-10-19. Publication and hardware verification have not been performed.

- Preserve original summary/device identity and `fpa.turn_on` contract.
- Add current settings, independent alerts including heating/cooling, named preset selection, guarded Start, Refresh and latest-preparation timestamp (17 entities/machine).
- Persist selected IDs/minimal guards, centralize conservative start checks, and never replay an ambiguous command.
- Provide cached entry/device diagnostics with bounded redacted pre-merge updates and merged shadow.
- Modernize summary metadata to HA enum; add heating/cooling/bottle-check states and visible translated errors.
- Ship a self-contained MIT client adaptation, conventional HACS layout and literal English translations.

Minimum supported HA: 2025.10.4. Tested current: 2026.10.2. See the validation report for actual checks, provenance and remaining limits.
