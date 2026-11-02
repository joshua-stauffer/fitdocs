---
id: 2026-11-01-relay-design-file-structure-plan-names
title: 'relay-server design names backend classes and test files differently from the code'
status: open
importance: medium
importance_why: The design is the traceability source for later specs (relay-intervals, strava-publish); stale names send a reader to files that do not exist.
effort: S
kind: docs
area: .kiro/specs/relay-server/design.md, relay/tests
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 2.2 review; 4.6; /kiro-validate-impl relay-server
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-relay-design-file-structure-plan-names.md] Bring the design's class and test-file names in line with the code"
context:
  - .kiro/specs/relay-server/design.md
  - .kiro/specs/relay-server/tasks.md
  - relay/tests
  - relay/src/fitdocs_relay/storage
blocked_by: []
---

## What
The design text disagrees with itself and with the implementation in two ways. (1) Backend classes: the file tree and the how-to-add-an-area list say `SqliteStorage`/`PostgresStorage`, while the component heading and traceability table say `SqliteBackend`/`PostgresBackend`. The controller ruled `Backend` and that is what was implemented. (2) The File Structure Plan names test files that do not exist (`test_migrate.py`, `test_routes.py`, `test_envelope_server.py`, `test_dockerfile.py`, `tests/connectors/test_cli_relay.py`, `test_wire_examples.py`), and several real files and directories are unlisted.

## Why it matters
A later session following the plan greps for files that are not there, and the unlisted modules are invisible to anyone using the plan as a map.

## Evidence
- `.kiro/specs/relay-server/design.md:406-407` and `:1234` say Storage; `:620` and `:1243` say Backend.
- `design.md:420-428` and `:449` name the stale test files; `relay/tests/` actually holds test_envelope_replay.py (design:424 says test_wire_examples.py), test_registration_routes.py, test_core_routes.py, test_app_pipeline.py, test_probes.py, test_e2e.py, test_shared_imports.py, test_image.py, conformance/, storage/, serve_child/, e2e_child/ and conftest.py.
- Verify with `ls relay/tests` against the design block.

## How to pick it up
1. Rename the Storage class mentions to Backend (design.md:406, 407, 1234).
2. Regenerate the test block of the File Structure Plan from `ls -R relay/tests`; also list `relay/LICENSE`, `relay/.python-version`, `tests/connectors/test_relay_register.py`, `tests/connectors/test_relay_offline.py` if they exist.
3. Done when every path in the plan resolves and every real relay test module is listed.
