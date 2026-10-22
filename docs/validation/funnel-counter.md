# Funnel counter validation — 2026-10-21

Local change based on `87f2c55`, branch `codex/funnel-bottle-counter`.

Each device now exposes six sensors, nine binary sensors, one select, and three buttons (19 entities). The local Funnel bottles remaining sensor starts at 4, decrements on distinct reported completed preparations, and is bounded to 0–4. Funnel removal turning on and the local Reset button restore 4. Its allowance and completion cursor persist in entry-isolated HA storage. Existing API sensors and start safeguards are independent of the allowance.

Validation completed against the final runtime and test changes:

- HA 2026.10.2 / Python 3.14.2: **191 passed**, no skips, eight upstream HACS deprecation warnings.
- HA 2025.10.4 / Python 3.13.11: **191 passed**, no skips.
- Official HA 2026.10.2 hassfest: **1 integration, 0 invalid**; translations and icons included.
- Ruff check and format: passed for all maintained source, tests, and scripts. Three pre-existing untracked `* 2.py` copies were preserved and excluded from lint/format checks; they are not imported by the integration.
- `git diff --check`: passed.

The real HA platform tests verify initial allowance, 19 entities on the existing device, repeated and enriched completion delivery, water-only completion, the zero floor, API cleaning-alert independence in both directions, automatic and manual reset, reset while offline, reload persistence, stale completion replay, device isolation, and corrupt saved-count bounds. All vendor traffic is fake; no live account, production install, or physical dispensing was used.

The existing project virtual environments contained macOS-offloaded dependency files that stalled imports. Temporary environments were built entirely from the existing local cache. Full suites ran with localhost socket permission because two existing transport/diagnostics tests bind temporary loopback servers.

Commands:

```sh
HACS_SOURCE=/private/tmp/fpa-hacs-integration /private/tmp/fpa-funnel-current/bin/python -m pytest -q
PYTHONPYCACHEPREFIX=/private/tmp/fpa-funnel-min-pycache HACS_SOURCE=/private/tmp/fpa-hacs-integration /private/tmp/fpa-funnel-min/bin/python -m pytest -q
PATH=/private/tmp/fpa-funnel-current/bin:$PATH PYTHONPATH=/private/tmp/fpa-ha-core /private/tmp/fpa-funnel-current/bin/python -m script.hassfest --integration-path /Users/sam/Documents/ChatGPT/ha-fpa-new/custom_components/fpa
.venv-current/bin/ruff check --exclude '* 2.py' custom_components tests scripts
.venv-current/bin/ruff format --check --exclude '* 2.py' custom_components tests scripts
git diff --check
```

As with the existing latest-preparation sensor, after an outage only the newest reported completion is counted. An unobserved funnel-removal cycle cannot be reconstructed. Reset provides manual correction. No release was published or deployed.
