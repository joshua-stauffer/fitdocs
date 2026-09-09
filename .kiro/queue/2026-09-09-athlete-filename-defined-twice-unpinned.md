---
id: 2026-09-09-athlete-filename-defined-twice-unpinned
title: The athlete file name is a literal in two modules with no cross-pin and no layout helper
status: open
importance: low
importance_why: Renaming or relocating athlete.toml in one module silently forks the profile the load layer writes from the one the renderer reads; nothing fails until a user notices zones and benchmarks disagreeing. Phase 6 adds a third writer of that file (performance-benchmarks), which widens the exposure.
effort: S
kind: inconsistency
area: fit-ingest, training-load, src/fitdocs/athlete.py, src/fitdocs/load/profile.py, src/fitdocs/layout.py
created: 2026-09-09
surfaced_by: /kiro-discovery (codebase exploration for Phase 6)
pinned_at: be99755
resume_command: "do: add a single layout-level constant (or helper) for the athlete file name, make athlete.ATHLETE_FILE and profile.PROFILE_FILENAME derive from it or pin them to each other in a test, and confirm tests/test_layout.py covers it"
context:
  - src/fitdocs/athlete.py
  - src/fitdocs/load/profile.py
  - src/fitdocs/layout.py
  - tests/test_layout.py
blocked_by: []
---

## What

`src/fitdocs/athlete.py:39` defines `ATHLETE_FILE: Final[str] = "athlete.toml"`
and `src/fitdocs/load/profile.py:88` defines
`PROFILE_FILENAME: Final[str] = "athlete.toml"`. The two are independent
literals. `src/fitdocs/layout.py` — the module that owns every other data-root
path (`WORKOUTS_DIR`, `ARCHIVE_DIR`, `SETTINGS_FILE`, `CACHE_DIR`,
`TOOL_STATE_DIR`, `OWNED_PATHS`) — has no helper for the athlete file.

## Why it matters

The profile docstring says "the same file workout-docs reads", and that is true
only because two strings happen to match. A change to either one leaves the
renderer reading one file for zones and the load layer writing benchmarks to
another, with no test failing. Phase 6's `performance-benchmarks` pass becomes
a third writer of this file, so the exposure grows.

## Evidence

Measured on `be99755`:

```
$ grep -rlE 'PROFILE_FILENAME' src tests | xargs grep -lE 'ATHLETE_FILE'
(no output — no module or test names both constants)
```

`tests/test_cli.py:287,294,464` and `tests/test_cli_sync_inbox.py:608` write
and assert the literal `"athlete.toml"` directly, so they would keep passing
against either constant alone.

## How to pick it up

One sitting. Either introduce the constant in `layout.py` and import it from
both modules (watch the dependency direction stated in `benchmarks.py:13-15`:
`profile -> benchmarks/athlete -> model`; `layout` sits below all of them and
is already imported by the load engine), or leave both literals and add a test
that asserts they are equal. The first is the fix; the second is the pin.
