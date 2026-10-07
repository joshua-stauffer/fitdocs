---
id: 2026-10-07-confinement-snapshot-dangling-links
title: Shared confinement snapshot follows dangling symlinks before comparing writes
status: open
importance: low
importance_why: A dangling link aborts the shared test inventory before its confinement assertion can identify the changed path.
effort: S
kind: bug
area: tests/test_confinement.py, shared confinement infrastructure
created: 2026-10-07
surfaced_by: /kiro-impl analytics-derived task 5.4 independent review
pinned_at: 953ee7e
resume_command: "do: repair tests/test_confinement.py _snapshot to inventory dangling symlinks without following them; preserve existing file-content, mtime and directory assertions, and add discriminating no-follow controls"
context:
  - tests/test_confinement.py
  - .kiro/steering/change-protocol.md
  - .kiro/specs/analytics-derived/tasks.md
  - .kiro/queue/README.md
blocked_by: []
---

## What

The existing shared `_snapshot` checks `is_dir()` and otherwise calls
`read_bytes()` and `stat()`. A dangling symlink therefore raises
`FileNotFoundError` before the entry-point guard compares before/after state.
The derived-specific inventory uses `lstat()` and records link targets, but
the entry-point harness still takes the original shared snapshot too.
Changing that shared policy is outside analytics-derived task 5.4.

## Why it matters

A future negative control that writes a dangling link fails while taking a
snapshot instead of producing the intended confinement assertion. It also
prevents the harness from testing roots that already contain such a link.
This is a test infrastructure issue; this observation establishes no
production write defect.

## Evidence

- At `953ee7e`, `tests/test_confinement.py:212` defines `_snapshot`; its loop
  at lines 224–230 follows links through `is_dir`, `read_bytes`, and `stat`.
- Controller verified on 2026-10-07 with `env -u UV_CACHE_DIR uv run python`:
  load `_snapshot` using `runpy.run_path('tests/test_confinement.py')`, create
  a temporary root with `dangling.symlink_to('absent-target')`, and call
  `_snapshot(root)`. Actual output, exit 0 after catching the observed error:
  `CONFIRMED: existing _snapshot raises FileNotFoundError on a dangling symlink`.
- Task 5.4 review also reproduced this during a production-write negative
  control. That control was qualified as confounded, not claimed as a
  passing derived confinement pin.

## How to pick it up

1. Read the shared snapshot, `_touched`, and the entry-point dispatcher,
   along with the change protocol's fixture discrimination rules. Reproduce
   the temporary dangling-link case against the latest tree.
2. Decide the shared inventory representation for symlinks, then add tests
   that distinguish no-follow behavior and link-target changes without
   weakening existing file bytes, same-content mtime, or directory controls.
3. Repair the shared helper in an isolated worktree. Run its scoped suite,
   independently mutate the new controls, and run the canonical regression
   gate before landing. Preserve every existing entry-point permission.
