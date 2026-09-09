---
id: 2026-09-10-declared-dir-enumerations-hand-maintained
title: Two hand-maintained enumerations of declared and owned directories fail by KeyError or go silently stale
status: open
importance: low
importance_why: Every new owned or declared directory (load-history adds one now) trips a KeyError in one test and leaves a stale sentence in another; cheap to make both fail honestly.
effort: S
kind: chore
area: wiki-contract, tests/test_declaration_goldens.py, tests/test_confinement.py
created: 2026-09-10
surfaced_by: /kiro-spec-batch (load-history design, wave 2)
pinned_at: 1251a98
resume_command: "do: in tests/test_declaration_goldens.py make the DECLARED_DIRS parametrisation fail with an assertion that names the directory missing from _GOLDEN_NAMES instead of raising KeyError, and in tests/test_confinement.py replace the prose list of OWNED_PATHS members at lines 29-30 with wording that defers to layout.OWNED_PATHS or with a pinned test; load-history tasks 1.1, 1.2 and 5.4 patch both for their own change, this item is the general fragility"
context:
  - tests/test_declaration_goldens.py
  - tests/test_confinement.py
  - src/fitdocs/layout.py
  - .kiro/specs/load-history/tasks.md
blocked_by: []
---

## What
Two tests describe the set of owned or declared directories by hand:
1. `tests/test_declaration_goldens.py` parametrises over `DECLARED_DIRS` but
   resolves each directory's golden through the hand-maintained dict
   `_GOLDEN_NAMES`; a new declared directory raises `KeyError` inside the
   helper rather than failing an assertion that says what is missing.
2. `tests/test_confinement.py` states in prose which paths `OWNED_PATHS`
   contains ("workouts/, fit-archive/, .cache/, and .fitdocs/ alone"); no
   test holds that sentence to the constant, so it goes stale on every
   change to the set.

## Why it matters
load-history is the first spec to add an owned directory since these tests
were written, and it had to plan around both. The next one will too. A
`KeyError` from a helper is the failure mode the change-protocol's fixture
discrimination section calls out: it masks the evidence the test exists to
produce.

## Evidence
- `tests/test_declaration_goldens.py:36-43` — `_GOLDEN_NAMES` dict and
  `_golden_path` indexing it.
- `tests/test_confinement.py:29-30` — the prose enumeration.
- `.kiro/specs/load-history/tasks.md` tasks 1.1, 1.2, 5.4 — the per-change
  patches.

## How to pick it up
1. Wait for load-history 1.1/1.2 to land so you are not racing the same
   lines; then generalise what they did.
2. Turn the dict lookup into an assertion with a message, and either pin the
   prose to `layout.OWNED_PATHS` in a test or reword it to defer.
3. Run the two test files; done when a synthetic extra entry in
   `DECLARED_DIRS` produces a named assertion failure, not a `KeyError`.
