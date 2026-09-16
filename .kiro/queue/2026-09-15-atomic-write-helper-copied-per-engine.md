---
id: 2026-09-15-atomic-write-helper-copied-per-engine
title: The temp-file-then-os.replace write is a private copy in five modules, and training-blocks adds a sixth
status: open
importance: low
importance_why: Each copy is ten lines and correct today; the cost is that a fix to one (a missing fsync, a temp-file leak on a signal) has to be found and repeated in every other, and nothing pins that the copies agree.
effort: S
kind: chore
area: wiki-contract, src/fitdocs/docio.py, src/fitdocs/load/engine.py, src/fitdocs/history/engine.py, src/fitdocs/tiles.py, src/fitdocs/quarantine.py, src/fitdocs/load/profile.py, training-blocks
created: 2026-09-15
surfaced_by: /kiro-spec-batch (training-blocks design, Phase 7 wave 1)
pinned_at: 5dff756
resume_command: "do: once training-blocks has shipped, add a shared write_text_atomic(path, text, *, prefix) to src/fitdocs/docio.py (the one enforcement point for document I/O, per wiki-contract's amendment of 2026-07-22), switch the six private copies to it, keep each caller's temp-file prefix, and widen the per-package boundary allow-lists (tests/history/test_boundary.py, tests/plans/test_boundary.py, tests/load/threshold/test_boundary.py) to admit fitdocs.docio where they do not already"
context:
  - src/fitdocs/docio.py
  - src/fitdocs/load/engine.py
  - src/fitdocs/history/engine.py
  - src/fitdocs/tiles.py
  - src/fitdocs/quarantine.py
  - src/fitdocs/load/profile.py
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
