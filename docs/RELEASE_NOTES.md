# 1.1.0

## What's changed

- **Start requests:** Reported heating or cooling alone no longer blocks a start. Both states remain visible. Missing activity values still leave readiness unverified, and the other start safeguards remain in place. This addresses the persistent cooling report in issue #7.
- **Funnel counter:** Confirmed water-only preparations no longer reduce Funnel bottles remaining. Formula and unknown-mode preparations continue to count; unknown runs later identified as water-only and previously counted runs are not automatically corrected. This addresses issue #9.
- **Funnel allowance:** The local counter starts at 4, persists across restarts, and resets on funnel removal or the Reset button. The appliance-reported funnel cleaning alert and start safeguards remain independent of the counter.

Both fixes passed the Home Assistant test matrix and HACS and Hassfest validation. They have not been verified on the affected physical appliance. A command accepted by the cloud does not guarantee that the appliance started or completed a preparation.

# 1.0.0

Local first-fork build, 2026-10-19. Publication and hardware verification have not been performed.

- Preserve original summary/device identity and `fpa.turn_on` contract.
- Add current settings, independent alerts including heating/cooling, named preset selection, guarded Start, Refresh and latest-preparation timestamp (17 entities/machine).
- Persist selected IDs/minimal guards, centralize conservative start checks, and never replay an ambiguous command.
- Provide cached entry/device diagnostics with bounded redacted pre-merge updates and merged shadow.
- Modernize summary metadata to HA enum; add heating/cooling/bottle-check states and visible translated errors.
- Ship a self-contained MIT client adaptation, conventional HACS layout and literal English translations.

Minimum supported HA: 2025.10.4. Tested current: 2026.10.2. See the validation report for actual checks, provenance and remaining limits.
