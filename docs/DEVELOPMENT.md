# Development and local release

All tests are offline. Do not supply vendor credentials or start a physical appliance. Use the sanitized fixture in tests/fixtures/reference.json; conftest reconstructs actual camelCase wire payloads. The export itself is not a vendor REST response.

## Environments

Use Python 3.13.11 for the minimum target and Python 3.14.2 for current. These isolated environments were used locally:

```sh
uv venv --python 3.13.11 .venv-min
uv pip install --python .venv-min/bin/python -r requirements/minimum.txt
uv venv --python 3.14.2 .venv-current
uv pip install --python .venv-current/bin/python -r requirements/current.txt
```

The custom-integration harness pins HA 2025.10.4 and 2026.10.2 respectively. The minimum environment additionally pins pycares 4.11.0 because current 5.x removes the result types required by its older aiodns. This is a test-environment pin, not an integration runtime dependency or patch. HA manages production dependencies. The vendored client uses HA's injected aiohttp session.

## Tests and validation

Clone HACS source at the recorded revision to execute genuine local validators; tests never fetch tooling themselves:

```sh
git clone https://github.com/hacs/integration.git /tmp/fpa-hacs
git -C /tmp/fpa-hacs checkout 694f741f10e744e2d3f6cc31d84b89d26d0d0f03
HACS_SOURCE=/tmp/fpa-hacs .venv-current/bin/python -m pytest -q
HACS_SOURCE=/tmp/fpa-hacs .venv-min/bin/python -m pytest -q
.venv-current/bin/ruff check custom_components tests scripts
.venv-current/bin/ruff format --check custom_components tests scripts
.venv-current/bin/python scripts/validate_hacs.py --hacs-source /tmp/fpa-hacs
```

Native diagnostics and one client test bind an ephemeral localhost test server; the runtime never contacts the real vendor in these tests. A sandbox must permit localhost binding. Recorder tests use actual temporary SQLite through HA Recorder, not direct integration database writes. HACS tooling tests require HACS_SOURCE; without it, four explicit upstream-tool contract cases skip. The final recorded matrix sets it, so no checks silently disappear.

For hassfest, clone Home Assistant Core and select tag 2026.10.2. Run the original runner with the current environment on PATH (ruff is required):

```sh
git clone --branch 2026.10.2 --depth 1 https://github.com/home-assistant/core.git /tmp/fpa-ha-core
PATH="$PWD/.venv-current/bin:$PATH" PYTHONPATH=/tmp/fpa-ha-core \
  .venv-current/bin/python -m script.hassfest \
  --integration-path "$PWD/custom_components/fpa"
```

The official runner validates all applicable custom-integration plugins. Its dependencies are included in requirements/current.txt. HACS local validation invokes unchanged upstream validators through a filesystem adapter with networking disabled. It verifies the actual manifests, layout, README, local brand asset, MIT license and optional categories. GitHub repository metadata, remote Docker Action, releases and default-store inclusion are publication checks and are not represented as completed local tests. The workflow runs those when a published repository executes CI.

## Build and inspect the delivered artifact

```sh
.venv-current/bin/python scripts/build_release.py
.venv-current/bin/python scripts/validate_artifact.py --python .venv-current/bin/python
```

The reproducible archive contains only custom_components/fpa runtime files, including vendor license, translations and icon. ZIP entries have fixed timestamps, ordering and modes; SHA256SUMS and inventory.json describe the bytes. The extraction validator starts a fresh Python process from the extracted install and runs the HA behavior, upgrade, documentation-script and Recorder tests against the packaged component. It asserts module paths resolve inside the extraction. Source-tree tests cannot substitute for that check.

CI pins action revisions and matching HA test harness versions. Dependabot tracks actions and declared Python tooling. See IMPLEMENTATION_VALIDATION.md for tested source fingerprints, exact outcomes, failure/correction history and hardware/publication boundaries; IMPLEMENTATION_DECISIONS.md records material choices. No formal HA quality tier is claimed.
