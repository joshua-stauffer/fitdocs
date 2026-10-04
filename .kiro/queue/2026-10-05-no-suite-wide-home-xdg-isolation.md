---
id: 2026-10-05-no-suite-wide-home-xdg-isolation
title: In-process CLI tests outside tests/connectors run against the real HOME and XDG_CACHE_HOME
status: open
importance: medium
importance_why: Once the Phase 10 index writes to a per-user cache, any CLI test that misses the spec-local fixture writes into the developer's real ~/.cache.
effort: M
kind: gap
area: tests/conftest.py, conftest.py, tests/test_confinement.py
created: 2026-10-05
surfaced_by: /kiro-spec-batch phase 10 (analytics-index spec writer)
pinned_at: 19fc92e
resume_command: "do: under the change ritual, add an autouse fixture in tests/conftest.py that points HOME, XDG_CACHE_HOME and XDG_CONFIG_HOME at tmp dirs for every test (with a self-test that Path.home() is not the real home), then run the suite and fix tests that relied on the real HOME; coordinate with analytics-index's FITDOCS_INDEX_DIR fixture"
context:
  - tests/conftest.py
  - conftest.py
  - tests/test_confinement.py
  - .kiro/specs/analytics-index/tasks.md
blocked_by: []
---

## What
Neither `tests/conftest.py` (only `_reset_plugin_discovery`, :18-28) nor the
root `conftest.py` (bytecode hygiene, :36-66) isolates HOME or XDG paths.
Only `tests/connectors` sets its own. The confinement guard snapshots
`tmp_path` only (`tests/test_confinement.py:1103-1151`), so a write to the
real home is invisible to it.

## Why it matters
analytics-index adds a per-user cache location (`$XDG_CACHE_HOME/fitdocs/…`,
`~/.cache/fitdocs/…`) and its own `FITDOCS_INDEX_DIR` autouse fixture under
`tests/index/`. Any CLI test elsewhere that runs a writing command with an
index present, or any future per-user path, would touch the developer's
machine.

## Evidence
- `tests/conftest.py:18-28` and `conftest.py:36-66` at 19fc92e: no HOME/XDG handling.

## How to pick it up
1. Land after analytics-index (its fixture shape informs this one) or before it, but coordinate on the env var names.
2. Add the autouse isolation with a positive control; run the full suite.
3. Consider extending the confinement guard to snapshot the (isolated) HOME.
