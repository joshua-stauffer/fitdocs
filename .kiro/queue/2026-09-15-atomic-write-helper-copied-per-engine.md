---
id: 2026-09-15-atomic-write-helper-copied-per-engine
title: The temp-file-then-os.replace write is a private copy in seven modules (the count at the latest lander, see the last Update), and connectors adds another
status: open
importance: low
importance_why: Each copy is ten lines and correct today; the cost is that a fix to one (a missing fsync, a temp-file leak on a signal) has to be found and repeated in every other, and nothing pins that the copies agree.
effort: S
kind: chore
area: wiki-contract, src/fitdocs/docio.py, src/fitdocs/load/engine.py, src/fitdocs/history/engine.py, src/fitdocs/tiles.py, src/fitdocs/quarantine.py, src/fitdocs/load/profile.py, src/fitdocs/identity/holds.py, training-blocks
created: 2026-09-15
surfaced_by: /kiro-spec-batch (training-blocks design, Phase 7 wave 1)
pinned_at: 5dff756
resume_command: "do: once training-blocks has shipped, add a shared write_text_atomic(path, text, *, prefix) to src/fitdocs/docio.py (the one enforcement point for document I/O, per wiki-contract's amendment of 2026-07-22), switch every private copy (seven live, see the last Update) to it, keep each caller's temp-file prefix, and widen the per-package boundary allow-lists (tests/history/test_boundary.py, tests/plans/test_boundary.py, tests/load/threshold/test_boundary.py) to admit fitdocs.docio where they do not already"
context:
  - src/fitdocs/docio.py
  - src/fitdocs/load/engine.py
  - src/fitdocs/history/engine.py
  - src/fitdocs/tiles.py
  - src/fitdocs/quarantine.py
  - src/fitdocs/load/profile.py
  - src/fitdocs/identity/holds.py
  - .kiro/specs/training-blocks/design.md
blocked_by: [training-blocks]
---

## What
Five modules each hold their own `tempfile.mkstemp(dir=path.parent, ...)` →
write → `os.replace` helper with a module-specific temp prefix, and
`fitdocs.history.engine`'s docstring records that the copy is deliberate:
importing `fitdocs.load.engine._atomic_write` is exactly what its package
boundary guard forbids. `training-blocks` (design.md, PlanEngine) adds a
sixth copy in `src/fitdocs/plans/engine.py` for the same reason. `docio.py`
-- created by wiki-contract's 2026-07-22 amendment as "one enforcement
point" for reads -- has no write helper at all.

## Why it matters
A defect in the idiom (the `except BaseException` cleanup missing a branch,
a temp file left behind on `KeyboardInterrupt`, a future need for `fsync`)
must be fixed six times, and no test asserts the copies behave alike. The
boundary guards exist to keep engines from importing *each other*, not from
importing a leaf; a leaf helper satisfies both.

## Evidence
- `grep -n "os.replace" src/fitdocs/**/*.py src/fitdocs/*.py` at 3664a0d (re-created as 5dff756 after the 2026-09-16 .git loss, identical tree):
  `load/engine.py:652` (`_atomic_write`, prefix `.load-`),
  `history/engine.py:230` (`_atomic_write`, prefix `.history-`),
  `tiles.py:417` (prefix `.tile-`), `quarantine.py:234`,
  `load/profile.py:545` (prefix `.athlete-`).
- `src/fitdocs/history/engine.py:49-58` -- the docstring stating the copy is
  deliberate and why.
- `.kiro/specs/training-blocks/design.md`, component PlanEngine and
  research.md "Decision: A sixth private atomic-write copy".

## How to pick it up
1. Read `docio.py`'s docstring (`:19-37`) for why the symlink refusal lives
   at the read; the write helper belongs beside it for the same reason.
2. Write `write_text_atomic` once with a test that a failing write leaves no
   temp file and no partial target; switch the six callers; run each
   package's boundary test and widen its allow-list to `fitdocs.docio`.
3. Done when `grep -rn "os.replace" src/fitdocs` hits `docio.py` only.

## Update 2026-09-29 (Phase 8 spec batch)

- training-blocks has shipped, so its copy is live and the live count is
  six: `grep -rn "os.replace(" src/fitdocs` at f500dc1 -> `load/engine.py:667`,
  `history/engine.py:246`, `tiles.py:435`, `quarantine.py:241`,
  `load/profile.py:550`, `plans/engine.py:268` (prefix `.plans-`). The
  `blocked_by: [training-blocks]` precondition is met; the frontmatter is
  left as written.
- Two more private copies are now specified: activity-identity's hold store
  `src/fitdocs/identity/holds.py` (AI task 2.5, "temp file then replace") and
  connectors' `src/fitdocs/connectors/_atomic.py`
  `write_atomic(path, data, *, prefix)` (CN task 1.2; `connectors/design.md`
  § AtomicWriter, ~:1109-1118). Each task appends its own site here and
  advances the count in the title and resume command when it lands, so the
  count moves then; this update deliberately leaves both unchanged.
- The connectors copy is not identical to the six: it `flush`es and
  `os.fsync`s before `os.replace` (no live copy fsyncs; `grep -rn fsync
  src/fitdocs` has no hits). All copies share mkstemp's owner-only mode and a
  dot-prefixed temp name. A shared helper has to offer fsync or adopt it for
  every caller; decide that when consolidating.
- Boundaries: connectors' boundary guard (CN task 6.1) forbids
  `fitdocs.docio`, so consolidating into `fitdocs.docio` must widen it
  (`connectors/design.md` ~:97-100). activity-identity already allows
  `fitdocs.docio` from `identity/holds.py` (`activity-identity/design.md`
  ~:116-119), so nothing widens there.
- Timing: consolidating after both specs land covers all eight sites in one
  change; doing it sooner makes both implementers add copies against a
  moving helper.

## Update 2026-09-30 (activity-identity task 2.5)

- activity-identity's hold store has landed its copy: `src/fitdocs/identity/holds.py`
  `save_holds` (mkstemp prefix `.held-`, `os.replace`, no fsync). The live count
  is now seven (`grep -rn "os.replace(" src/fitdocs`: the six listed in the
  2026-09-29 update plus `identity/holds.py`); the title and the resume command
  were advanced from six to seven. The connectors copy (`connectors/_atomic.py`,
  fsyncing) is still pending and takes the count to eight when it lands.
