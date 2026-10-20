# Implementation validation

**Result: COMPLETE — stages A–F PASS for the required offline build.** No failed, blocked or skipped functional checks remain. Production deployment, remote publication and physical dispensing were not performed and are not completion gates.

## Source and delivery provenance

- Project: `/Users/sam/Documents/ChatGPT/ha-fpa-new`; branch: `codex/formula-pro-advanced`.
- Initial state: empty existing Git repository on unborn main; no files, remotes, staged work or user changes. Existing Git metadata retained. No unrelated work was overwritten or committed.
- Upstream integration/base: `d69d8c0a765f8137a04e38f6ae3ea4f95120c488`; client origin: `8f91cdbc38025d753dcd437f15fedeea5c63253a`. Both upstream HEADs matched the supplied baseline; published client remained0.0.7.
- Checkpoints: `e785976` baseline/harness; `230300e` integrated functionality; **tested source commit `9842b579dc0904a9de88cc7709e96741b91c11b0`** packaging and review corrections.
- Final evidence/documentation is committed after the tested source; those later changes do not change the runtime. The final commit ID and clean/remaining status are recorded after committing in the local [delivery receipt](../dist/DELIVERY.json), avoiding a self-referential commit hash. Final response also identifies that commit.
- Runtime tree SHA-256: `ef371fa4718422bdc113921fdf9aa23b6546e6d0769471bbead4376d100e0485`. Formula: SHA-256 of sorted runtime inventory lines `path`, NUL, file SHA-256, newline. Exact file inventory is in `dist/inventory.json`.
- Install archive: [fpa-1.0.0.zip](../dist/fpa-1.0.0.zip), **25 runtime files**, SHA-256 `9ec6b538be5fe2ea8deefc0186e5710fbdf772cf1cd5ab281107486deb9774a5`. The archive and checksums are generated locally, excluded from Git, and reproducible.
- Build started2026-10-19 America/New_York; evidence has actual UTC timestamps. [Source/environment provenance](validation/source-provenance.json) records the final source fingerprint and observation time. Original personal export/screenshot were never imported or committed; fixtures are sanitized/synthetic.

## Environments and actual checks

All commands below ran from the project root, except the extraction checks, which run a fresh process from a temporary installed directory and assert that imports resolve there. No real account login or vendor/appliance command was used. Localhost servers only exercise fake transports and HA HTTP downloads.

| Check | Minimum | Current | Evidence |
|---|---|---|---|
| Python / HA / harness |3.13.11 /2025.10.4 /0.13.289 |3.14.2 /2026.10.2 /0.13.373 |[minimum freeze](validation/minimum-freeze.txt), [current freeze](validation/current-freeze.txt) |
| Full source suite, exit0 |**178 passed,0 skipped** |**178 passed,0 skipped** |[minimum](validation/minimum-tests.txt), [current](validation/current-tests.txt), JUnit files alongside |
| Extracted ZIP install suite, exit0 |**171 passed** |**171 passed** |[minimum install](validation/minimum-install.txt), [current install](validation/current-install.txt) |
| Official hassfest, exit0 |1 integration,0 invalid |1 integration,0 invalid |[minimum](validation/hassfest-minimum.txt), [current](validation/hassfest-current.txt) |
| Genuine HACS local validators |6 pass through the matrix |6 pass plus direct runner |[HACS](validation/hacs-local.txt) |
| Ruff lint / formatting / compile |Shared source checked |All pass;35 Python files formatted |[lint/format](validation/lint-format.txt); compileall exit0 |
| Package bytes / contents |Same reproducible ZIP |Same reproducible ZIP |`test_packaging.py`, inventory and SHA256SUMS |

Source-suite commands: `HACS_SOURCE=/private/tmp/fpa-hacs-integration .venv-current/bin/python -m pytest -q --junitxml=docs/validation/current-junit.xml` and the equivalent `.venv-min` command. The current run additionally sets FPA_EVIDENCE_DIR to retain the verified redacted sample. Both exit0. The minimum suite was reconfirmed after optional validator tooling was installed, again178 passed.

Artifact commands: `.venv-current/bin/python scripts/validate_artifact.py --python .venv-current/bin/python --label current` and equivalent minimum invocation. Both exit0 and confirm the runtime import lives inside the extracted ZIP. Seven checkout/tooling cases (six HACS contracts plus packaging) are intentionally outside the installed-runtime run; all seven run and pass in the full source suite. No functional case is skipped.

Official validators: original `script.hassfest` from Core2026.10.2 (`8d7fd8b68677c2585be36ec86043308f403875b8`) and Core2025.10.4 (`c960bd2845d51764c270409cbbf79ab0440ff75e`), with the corresponding environment on PATH/PYTHONPATH. All applicable custom-integration plugins ran. The minimum runner logs an unrelated optional-camera-library fallback warning; it still exits0 with0 invalid integrations. There is no FPA dependency on that camera library. Current HACS tooling emits8 upstream deprecation warnings; the project does not suppress them or change assertions.

HACS: `scripts/validate_hacs.py` uses unchanged Validator classes from `hacs/integration@694f741f10e744e2d3f6cc31d84b89d26d0d0f03` through a local filesystem adapter with network disabled. Checks: hacs.json, integration manifest, README, local brand asset, complete MIT license, optional integration categories. Missing/invalid content negative cases fail as expected. An optional categories warning is retained. Local license classification is narrower than GitHub's license API.

## Per-stage exit evidence

| Stage | Status | Exit criterion and evidence |
|---|---|---|
| A — baseline/fixtures |PASS |Base/client SHAs/current upstream recorded; original identity/action/state contract inspected; sanitized export reconstructed into actual camelCase fixtures, preserving string epochs, nulls and inconsistencies; runnable harness and checkpoint established. `test_baseline`, config/entity/upgrade tests. |
| B — client/runtime |PASS |One subscription per device; injected session remains open; actual localhost HTTP/WebSocket lifetime check; setup/rotation/reauth and transient failure classification; partial merge/order/metadata/read races; coalesced reconnect/manual reads; unload/reload task cancellation. `test_client`, `test_models`, `test_runtime`, `test_config_flow`. |
| C — entities/history |PASS |17 real HA entities per machine including5 sensors and9 binaries; independent nullable flags; exact0/1/2 temperature mapping; coherent immutable newest preparation; restoration/outages; actual file-backed SQLite Recorder stores two associated timestamp/settings snapshots, with no unrelated churn/replay. `test_entities`, `test_models`, `test_recorder`. |
| D — controls/guards |PASS |ID persistence/rename/deletion/duplicates; selection performs no cloud write; shared legacy/button preflight and locks; every alert/unknown blocks; occupancy/restarts/external preparations; concurrent starts at most one PUT; no replay/indeterminate timeout; in-flight unload cancellation;13 translated actionable errors via actual HA service. `test_runtime`, `test_entities`, `test_documentation`, `test_upgrade`. |
| E — diagnostics |PASS |Native entry/device HTTP downloads include full HA wrapper; no vendor calls or state/alias mutation; offline/minimal runtime; independent premerge capture and merged shadow; duplicates/old versions,20-count/256KiB limits/omission/eviction, lifecycle/isolation; recursive known-path privacy and source immutability. `test_privacy`, `test_diagnostics`, client transport-capture tests. |
| F — release/docs |PASS |Both exact HA suites178/178, extracted install171/171, both official hassfest versions, six real HACS local validators, lint/format/compile, deterministic package; complete README examples execute through HA Script and actual guarded entities with fake API; original-v1-shaped entry/registry upgrade preserves names/areas/enablement; rendered Markdown/anchors reviewed. Reports/decision log/checklist/source checkpoints delivered. |

Test counts are independently recorded in both JUnit files:

| Test file | Minimum passed | Current passed |
|---|---|---|
| `test_baseline.py` | 2 | 2 |
| `test_client.py` | 35 | 35 |
| `test_config_flow.py` | 15 | 15 |
| `test_diagnostics.py` | 6 | 6 |
| `test_documentation.py` | 4 | 4 |
| `test_entities.py` | 25 | 25 |
| `test_hacs_validation.py` | 6 | 6 |
| `test_models.py` | 22 | 22 |
| `test_packaging.py` | 1 | 1 |
| `test_privacy.py` | 8 | 8 |
| `test_recorder.py` | 2 | 2 |
| `test_runtime.py` | 50 | 50 |
| `test_upgrade.py` | 2 | 2 |

## Requirement and checklist mapping

| Requirement | Evidence and resulting behavior |
|---|---|
| S01 |Entity/platform tests verify3 current-setting sensors and9 binaries; model tests unknown/null semantics and preserved numeric historical codes. |
| S02 |Original summary UUID/device tuple/domain/action/schema/attributes preserved; first-load upstream-v1-shaped entry and registries survive with user names, areas, icon and enabled/disabled state. |
| S03 |Actual select/button/service tests: local selection, deliberate start, same coordinator command, configured preset values. |
| S04 |Runtime storage/restart/rename/duplicate/deletion tests; deleted IDs never silently return as selected. |
| S05 |Refresh tests prove current lists/settings/history, coalescing/cooldown, no new subscription or command, failed-read preservation, no guard reset. |
| S06 |All alert/readiness/occupancy/restart/concurrency/timeout/auth/cancellation tests; shared guards stay active with summary disabled. |
| S07 |Exactly one timestamp sensor per machine; actual Recorder association and frozen companion attributes; only HA restoration, no preparation store. |
| S08 |Out-of-order/missed records resolve newest only, including real Recorder history test; no replay or direct database manipulation. |
| S09 |Independent heating/cooling from raw flags; missing remains unknown; no firmware/error entities. |
| S10 |Entry/device native HTTP download, full wrapper serialization, no-runtime/offline cases and zero side effects. |
| S11 |Defensive premerge capture/receipt order/UTC/partial shape,20 messages and256KiB caps per machine, merged-shadow cap, oversize metadata, privacy aliases, reconnect retention and unload/reset tests. |
| S12 |README catalog/action contracts verified against implemented source;3 YAML examples run through actual HA Script; links/anchors and rendered desktop/narrow preview inspected. |
| S13 |Stages progressed without stage sign-off. A usage-limit interruption preserved the workspace; user-requested resumption audited state and realigned all agents, then completed integrated validation. No pending stage is presented as done. |
| S14 |D01–D13 in IMPLEMENTATION_DECISIONS.md record choices, alternatives/rationale, effects, reversibility and evidence. |
| S15 |Original history preserved; project-only branch/verified local author, explicit staging and coherent checkpoints; source/tested/final revisions and receipt/status traceable; no remote push or unrelated changes. |
| Temperature mapping |All3 supplied enum states/display labels, valid0, unknown unexpected code, preserved numeric summary/history, no guessed degrees. |
| Full definition of done |[CHECKLIST.md](CHECKLIST.md) retains every section14 item and maps it to the stage/evidence above. Conditional critical-failure items are not applicable because no unresolved critical failure occurred; interruption/resumption evidence is recorded. |

## Review, failures and corrections

- Network sandbox prevented source fetch/localhost test binds; authorized network/localhost execution resolved this. TLS trust/tool bootstrap issues were corrected in tooling; production TLS verification remains enabled.
- Minimum test dependencies needed compatible pycares4.x for the older aiodns types. Actual Recorder setup replaced a failing framework mock on Python3.14; no functional assertions were weakened.
- Review found and corrected stale/malformed preflight reuse, concurrent-push safety between persistence and PUT, active command teardown, WebSocket/command auth propagation, distinct equal-time record occupancy, metadata-only order and exact integer ID parsing. Dedicated regressions pass on both versions.
- Privacy review corrected null-shadow handling, unclassified units, identifier metadata structure, raw IDs resembling aliases, export alias-state mutation, safe field names under unknown branches, and missing attempt-count/version metadata. Native HTTP sentinel/body/filename and buffer tests pass; captured raw sources remain unchanged.
- README links initially pointed at documentation not yet written; final static links pass. Artifact validation initially used a relative interpreter after changing directory; corrected to an absolute venv path, and both extracted suites pass. Neither was an appliance/runtime defect.
- Only the dedicated README preview folder was served for browser review; the initially proposed broad project server was rejected and replaced with this narrower permitted approach. The browser and server were closed after review.
- Earlier failing or superseded verbose synthetic outputs were replaced by concise correction notes and final passing evidence. Current results apply to the recorded integrated source, not isolated agent assertions or earlier counts.

## Manual review and exact limits

The primary inspected [representative native diagnostics](validation/representative-native-diagnostics.json): required sections, coherent normalized/raw comparison, partial message vs merged snapshot, discrepancy flags, consistent aliases and zero seeded PRIVATE_/SECRET_ values. Full entry/device body serialization is tested; HA's device filename deliberately retains its synthetic registered name and registry ID, proving the hook does not control it. HA also adds system/integration/custom-component/repair metadata; no anonymity claim is made.

The README rendered through a GitHub-style Markdown parser and real Chromium preview. Contents navigation reached the entity catalog; tables and code were inspected on desktop and a390px viewport (tables scroll horizontally as needed). [Top](validation/readme-top.png), [catalog](validation/readme-entities.png), [narrow](validation/readme-mobile.png). Internal file links/anchors are also checked automatically. No production screenshots or proposed custom dashboard are included.

Fresh-install evidence uses the exact ZIP path described in README and actual HA setup/config/entity tests. Upgrade evidence seeds the upstream-v1 entry/device/summary registry contract before the first fork load, including disabled state, and verifies preservation. This is an isolated compatibility simulation, not a live upgrade of the user's HA or proof of unobserved vendor behavior.

**Not performed:** real vendor login/device observation/physical preparation; production deployment; remote GitHub publication, CI workflow execution or Docker HACS Action; GitHub metadata/license detection/releases/default-store submission. These are outside this local delivery. Six genuine HACS local file validators and both official hassfest runners did run and pass. The HACS route in README is explicitly conditional on later publication; the local ZIP is immediately usable for manual installation.

No custom UI/archive/counters/estimates/writable settings/firmware-error entities/event stream/notifications/unsupported commands were added. No required offline failure or access blocker remains. The final handoff contains the installable archive, README, consolidated evidence, decision log and clean committed source.

## Documentation follow-up — 2026-10-20

The root [README](../README.md) now previews the integration's benefits, use cases, capabilities, and prerequisites. The detailed content and all three YAML examples moved to [USER_GUIDE.md](USER_GUIDE.md), with contextual links from the overview and a return link from the guide. The documentation tests now read the examples from the guide and verify local file links and section fragments in both documents.

Focused verification: `.venv-current/bin/python -m pytest -q tests/test_documentation.py` passed **5 tests**. Targeted Ruff lint and formatting passed. No runtime files changed. The original full-suite, package, and validator results above remain evidence for their recorded release revision; those checks and the release archive were not regenerated for this documentation change. The publication statements above describe the original local delivery, not subsequent repository activity.

## Display-name follow-up — 2026-10-20

The repository source now displays **HA - Formula Pro Advanced** in HACS, Home Assistant's integration metadata, and the setup title. The README and user guide use that name when referring to the integration; the supported hardware remains the Formula Pro Advanced WiFi. The domain remains `fpa`; no executable behavior, entity identity, action, or account-entry title changed.

Focused verification: JSON parsing confirmed matching HACS/manifest names and setup titles in both translation files, with all other manifest fields and translations preserved. `.venv-current/bin/python -m pytest -q tests/test_documentation.py -k internal_links` passed **2 tests**, with the 3 unchanged script examples deselected. Ruff lint and formatting checks passed for the two edited module docstrings; `git diff --check` passed. No full runtime suite or package rebuild was needed for this label change. The original ZIP, receipt, and release evidence above remain historical artifacts with the original display name.
