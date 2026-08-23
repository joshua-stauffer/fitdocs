---
id: 2026-08-09-conftest-cache-proofing-misses-scripts
title: conftest purges __pycache__ only under src/, but mutation-gated production code now lives in scripts/purge/
status: done
importance: high
importance_why: Every mutation run against scripts/purge/ depends on a human remembering `rm -rf scripts/purge/__pycache__`; forgotten, a same-size mutation silently does not apply and the reviewer records a survivor that never ran. That is the exact failure conftest's cache-proofing exists to prevent.
effort: S
kind: bug
area: conftest.py, .kiro/steering/change-protocol.md
created: 2026-08-09
surfaced_by: reviewer subagent during /kiro-impl encumbered-content-purge (task 6.4 review)
pinned_at: c3d2201
resume_command: "do: Extend conftest.py's bytecode cache-proofing to cover scripts/ as well as src/, so mutation runs against scripts/purge/ cannot silently fail to apply, and drop the remembered `rm -rf scripts/purge/__pycache__` step from the task briefs that currently carry it."
context:
  - conftest.py
  - .kiro/steering/change-protocol.md
  - scripts/purge/
blocked_by: []
---

## What

`conftest.py` purges stale bytecode caches, but scopes itself to `src/`:

    _SRC = Path(__file__).parent / "src"

`scripts/` is inside both the pytest and the mypy perimeter, and since the
`encumbered-content-purge` spec it holds eleven production modules that
reviewers mutate as a matter of course.

## Why it matters

Cache-proofing exists because a mutation that changes a file *without changing
its size* can leave a stale `.pyc` in place, so the mutated source is never
executed. The test then passes, and the reviewer records a **survivor that
never ran** — a false negative in exactly the evidence the review protocol
treats as strongest.

Because `scripts/` is outside the guard, every task brief touching
`scripts/purge/` now carries `rm -rf scripts/purge/__pycache__` as a step a
human has to remember. That is precisely the class of remembered step the
conftest hook was written to eliminate, and it has to be repeated in every
implementer and reviewer prompt indefinitely.

## Evidence

- `conftest.py` — `_SRC = Path(__file__).parent / "src"`, the only root purged
- `pyproject.toml` `[tool.mypy] files` includes `scripts`
- `scripts/purge/` holds eleven modules, all inside the pytest perimeter
- The instruction appears verbatim in the task briefs for 6.3, 6.4 and their
  reviews, and in the shared agent log as a standing warning

## How to pick it up

Extend the purge to `scripts/` (or to every configured perimeter root, derived
rather than hard-coded, so a future root cannot be missed the same way). Then
remove the remembered step from the briefs and from the standing log warning,
so the two do not drift apart.

Worth checking whether any other perimeter root is equally uncovered.

Done when a same-size mutation to a `scripts/purge/` module cannot silently
fail to apply.

## Resolution

**Closed `done` 2026-08-23 — the subject was retired, and retirement is the
resolution.** Post-purge queue triage after `encumbered-content-purge`
completed (spec 57/57, `87ce085`).

This item's subject was the purge's own one-shot tooling: a module under
`scripts/purge/`, a test under `tests/purge/`, or a precondition on a purge
task that has since run. Task 9.3 (`c18ec26`) deleted `scripts/` entire and
`tests/purge/` less three relocations; `ls scripts/ tests/purge/` errors on
`HEAD`. The operation those modules governed — sweep, redact, replace, adopt,
verify — executed to completion and is not repeatable: the history replacement
is a fresh root (`c3d2201`) with no mapping by construction.

There is therefore no future run for this defect to affect, and no code left to
carry it. The retirement record is `docs/reference/history-rewrites.md` § 8.

Checked before closing: the item's subject does not survive in the three
relocated guards (`tests/_forbidden_strings.py`, `tests/test_forbidden_strings.py`,
`tests/_content_oracle.py`). Items whose subject *did* survive were kept open
in the same triage.
