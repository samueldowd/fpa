# Validation evidence index

The consolidated report is ../IMPLEMENTATION_VALIDATION.md. These files are bounded, synthetic/offline evidence. Exact source provenance is source-provenance.json; the final Git commit/status and archive digest are in ../../dist/DELIVERY.json after the final report commit.

- current/minimum-tests.txt and matching JUnit XML:178 passed each, no skipped functional checks.
- current/minimum-install.txt:171 passed each from the released ZIP extraction.
- artifact-current/minimum-command.txt: archive SHA and verified extracted import path.
- hassfest-current/minimum.txt: original official runners, zero invalid integrations. Minimum output includes an unrelated optional camera fallback warning.
- hacs-local.txt: six unchanged upstream local file validators and precise remote-check exclusions.
- lint-format.txt: lint and formatting outcome; compileall also exited0.
- representative-native-diagnostics.json: full native wrapper around redacted synthetic cached data, manually inspected after sentinel assertions.
- current/minimum-freeze.txt: exact isolated validation tooling versions; these are not integration dependencies.
- readme-*.png: reviewed equivalent Markdown preview at desktop/narrow widths.
- stage-a-client-current.txt and diagnostics-current.txt: bounded earlier/targeted supporting checks; final source-suite results are authoritative.

All runtime tests use fake vendor transports. Localhost HTTP/WebSocket binds are test servers only. Production deployment, physical dispensing and publication were not performed.
