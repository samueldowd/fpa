# Implementation decisions

## D01 — 2026-10-19, stage A: repository and delivery

The workspace was an empty Git repository on unborn main, with no files, remotes, or changes. Fetch upstream history and branch from d69d8c0a765f8137a04e38f6ae3ea4f95120c488 on `codex/formula-pro-advanced`; use conventional custom_components/fpa layout. The eventual destination is https://github.com/samueldowd/fpa, supplied by the user; delivery remains local. No remote publication or hardware operation. Reversible without registry migration. See validation report for source inventory.

## D02 — 2026-10-19, stage A: controlled client distribution

Upstream integration and client HEAD match both pinned references; published client is 0.0.7 and lacks required lifecycle/raw access. Adapt its protocol in vendor/pybabyfpa with MIT license and source origin. This avoids requiring a PyPI release; it adds fork maintenance, isolated behind api.py. Preserve TLS and injected HA session. Validate through fake transports.

## D03 — 2026-10-19, stage A: supported versions

Provisional minimum HA 2025.10.4 (Python 3.13), current target HA 2026.10.2 (Python 3.14.2+), verified from public package metadata. A prior annual release cycle is a useful support window for typed runtime ownership, native entity restoration and diagnostics. Test both exact versions; revise only based on actual compatibility evidence. This is a tested support cutoff, not a claim that each feature first appeared in 2025.10.
