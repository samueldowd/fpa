# Completed definition of done

All applicable items below are verified by the stage/requirement tables and final evidence in [IMPLEMENTATION_VALIDATION.md](IMPLEMENTATION_VALIDATION.md). Conditional critical-failure handling has no unresolved instance; the transient usage interruption was preserved and resumed. Source is the tested commit recorded in that report. Remote publication and hardware checks remain outside the build boundary.


Every checked item must have evidence: test name/result, validation output, reviewed file, or a recorded observation. Keep this checklist in the repository, update it as work proceeds, and map each item to `docs/IMPLEMENTATION_VALIDATION.md`. Apply these checks automatically and continue through them without user stage sign-off. Completion means the implemented, validated, packaged integration plus README and reports; production deployment is not a dependency.

### Scope and compatibility

- [x] S01: Per machine, three current-setting sensors and nine binary sensors exist with documented semantics; the temperature enum uses the supplied `0`/`1`/`2` mapping and preserves raw codes in legacy/historical data.
- [x] S02: Original domain, device identifier, summary unique ID/entity references, and `fpa.turn_on` service/argument survive upgrade.
- [x] Existing summary raw states/attribute keys remain compatible; new states/metadata fixes are documented.
- [x] No deferred frontend, archive, counters, estimates, writable settings, firmware/error entities, new event system, or unsupported commands slipped into the change.
- [x] Expected entity set is documented (17 per machine including summary), with any necessary deviation explained.

### Presets and controls

- [x] S03: Named dropdown and Start selected preset button exist for each machine; selection performs no cloud write.
- [x] S04: Stable selected ID survives restart/rename; duplicates are disambiguated; deletion invalidates without fallback.
- [x] S05: Refresh updates presets, current data, and latest preparation without reconnect duplication or guard reset.
- [x] Both command entry paths use the same per-device lock, preset-ownership validation, fresh preflight, and start policy.
- [x] S06: Occupied/uncertain bottle prevents another start, including after restart and on-device preparations.
- [x] Start failures are visible and translated; pending/indeterminate states are bounded and safe; commands are not automatically replayed.

### Preparation history

- [x] S07: Exactly one last-preparation timestamp entity per machine has coherent recorded settings attributes.
- [x] Preparations initiated outside HA update it; no initiator claim is inferred from missing/present preset IDs.
- [x] Identical consecutive settings remain distinct; duplicate unchanged records do not create another preparation change.
- [x] Current settings, preset edits, and diagnostics do not rewrite last-preparation attributes.
- [x] S08: Reconnect publishes newest only, without backfill/replay or direct Recorder writes.
- [x] Recorder integration test verifies timestamp/settings association; retention and observation-time limits are documented.
- [x] No separate preparation-history persistence was added; local storage holds only selection/minimal guard metadata.

### State, lifecycle, and diagnostics

- [x] S09: Heating/cooling come from real raw fields, with unknown handling; firmware/error entities remain deferred.
- [x] Push, manual refresh, setup, reconnect, and command preflight converge without stale overwrites.
- [x] Transport/device connectivity are distinguished; critical missing values do not become ready/false.
- [x] Token rotation/reauthentication and failure classification are tested; TLS verification remains enabled.
- [x] Reload/unload leave no duplicate listeners, tasks, or closed shared HA sessions.
- [x] S10: Native Download Diagnostics works at entry and device level, including offline/minimal-runtime cases.
- [x] Report covers freshness, presets/selection, guards, last preparation, and recent safe operation outcomes.
- [x] S11: Diagnostics include up to 20 pre-merge received JSON updates per machine plus the latest merged raw shadow, with UTC receipt times, message subjects, stable receipt ordering, consistent aliases, and privacy redaction.
- [x] Message count/byte limits, oldest-entry eviction, explicit oversized-payload omissions, empty windows, reconnect preservation, and reload/restart resets are tested; no buffer is written to disk, Recorder, entity attributes, or normal logs.
- [x] Diagnostics are cached/read-only, bounded, cross-device isolated, and reviewed by the agent as part of validation.
- [x] Privacy tests prove seeded integration-controlled secrets/names/identifiers cannot survive in the serialized report or captured logs; HA-controlled wrapper/filename metadata has been inspected and documented.
- [x] Diagnostic JSON and entity output do not expose raw WebSocket authorization URLs or unsanitized exceptions.

### Packaging, tests, and handoff

- [x] Chosen source SHAs, client distribution/attribution, supported HA/Python baselines, and maintenance tradeoffs are recorded.
- [x] HACS layout, manifests, version, translations, brand assets, license, and dependency declarations are valid.
- [x] HACS validation, hassfest, lint/format, and meaningful test matrix pass on the minimum and current supported HA versions.
- [x] Fresh-install and upgrade-from-upstream scenarios pass in isolated HA with fake cloud data.
- [x] A reproducible installable artifact is delivered with the correct integration layout and required runtime files; the final response links it with the README and reports.
- [x] S12: Comprehensive root README explains purpose/capabilities, prerequisites, HACS/manual installation, configuration/upgrades, every provided entity/action, practical usage, start protection, data/history, diagnostics/privacy, troubleshooting, limitations, support, and attribution.
- [x] README entity/action tables and temperature/history/message-buffer descriptions match the completed release; standard HA actions are distinguished from `fpa.turn_on`.
- [x] README examples validate against mocked state; a fresh install/upgrade can be completed from its instructions alone; links/anchors and rendered Markdown have been reviewed.
- [x] README has no unfinished template text, unverified badges/compatibility promises, private screenshots, or deferred features represented as available.
- [x] No original user export, credentials, child-identifying fixture, or personal screenshot appears in committed files.
- [x] S13: Stages A–F progressed continuously through validated exit criteria using subagents or a synchronous workflow; the only early stopping conditions were an explicit user interruption or a documented critical failure after reasonable recovery efforts.
- [x] S14: `docs/IMPLEMENTATION_DECISIONS.md` documents material agent choices/assumptions, rationale/alternatives, scope effects, and validation, with no routine approval dependency.
- [x] S15: Git is used in the project's own repository on a recorded implementation branch, with meaningful commits/checkpoints, preserved initial user changes, explicit staging, and no unrelated/private files included.
- [x] Final Git diff/status and base/final/tested revisions are recorded; agent-owned deliverables are committed, any unrelated remaining changes are identified, and validations remain traceable to the tested code.
- [x] Any critical-failure/interruption checkpoint preserves completed work and evidence; a critical-failure report explains impact, remedies tried, remaining work, and concrete proceeding options with a recommendation.
- [x] Final integrated-source checks and affected earlier checks were rerun as needed; results are tied to the tested revision/tree and are not based only on isolated subagent assertions.
- [x] `docs/IMPLEMENTATION_VALIDATION.md` contains each stage's checks/outcomes/evidence, failures/corrections/reruns, requirement/checklist mapping, unresolved items, and separate hardware/deployment status; the final response links it and the decision log.
- [x] Final implementation report distinguishes completed automated checks, pending live validation, known vendor limitations, and any release/deployment work not performed.
