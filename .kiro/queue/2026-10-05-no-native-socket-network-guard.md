---
id: 2026-10-05-no-native-socket-network-guard
title: The no-network tests count only Python sockets, so native-code network access (DuckDB) would go unnoticed
status: open
importance: medium
importance_why: Phase 10 makes DuckDB, which can fetch extensions natively, a core dependency; the no-network claim for index/query rests on configuration read-back alone.
effort: M
kind: gap
area: tests/connectors/test_e2e.py, analytics-index, analytics-query
created: 2026-10-05
surfaced_by: /kiro-spec-batch phase 10 (analytics-query spec writer)
pinned_at: 19fc92e
resume_command: "do: research an OS-level network guard usable in CI (e.g. running the no-network command list under a network namespace on Linux / sandbox-exec deny network* on macOS) that would catch a native socket from DuckDB; prototype it on the `query` and `index` rows of tests/connectors/test_e2e.py after Phase 10 lands"
context:
  - tests/connectors/test_e2e.py
  - .kiro/specs/analytics-index/design.md
  - .kiro/specs/analytics-query/design.md
blocked_by: [analytics-index, analytics-query]
---

## What
The agent-run no-network check (`tests/connectors/test_e2e.py:203-246`)
patches Python's socket layer and counts attempts. DuckDB opens sockets from
native code (its httpfs extension autoinstall), which that patch cannot see.
analytics-index and analytics-query turn autoinstall/autoload and external
access off and read the settings back, and a static guard pins that fitdocs
never issues INSTALL/LOAD -- but no test would observe an actual native
connection.

## Why it matters
Discovery measured that default DuckDB config auto-installs httpfs over the
network when SQL mentions https:// (roadmap Phase 10 caveats). A future
setting regression or DuckDB behavior change would pass every test.

## Evidence
- `tests/connectors/test_e2e.py:203-246` at 19fc92e: socket-level counting only.
- analytics-query research.md (Phase 10 batch): probes needed `sandbox-exec` to block native network.

## How to pick it up
1. After both specs land, list where DuckDB connections open in tests.
2. Evaluate an OS-level guard per CI platform (CI is Ubuntu-only: `.github/workflows/ci.yml:41`).
3. Decide whether the guard is a CI-only job or part of the suite.
