---
id: 2026-07-28-root-public-surface-doc-unguarded
title: The plugin docs' copy of the fitdocs root surface is guarded by nothing
status: open
importance: medium
importance_why: The doc is the contract third-party plugin authors read; it goes stale silently on every root-surface change, and fit-ingest task 11 is about to make one.
effort: S
kind: gap
area: docs/plugins.md, tests/test_docs_guarantees.py
created: 2026-07-28
surfaced_by: independent task-graph review during /kiro-spec-tasks fit-ingest
pinned_at: c3d2201
resume_command: "do: add a test to tests/test_docs_guarantees.py asserting the fitdocs root surface list in docs/plugins.md matches fitdocs.__all__, mirroring the existing fitdocs.load guard"
context:
  - docs/plugins.md
  - tests/test_docs_guarantees.py
  - tests/test_public_api.py
  - .kiro/specs/fit-ingest/tasks.md
blocked_by: []
---

## What

`docs/plugins.md` publishes two public-surface lists as prose: one for
`fitdocs.load` and one for the `fitdocs` package root. Only the first is
guarded. `tests/test_docs_guarantees.py` asserts that everything
`fitdocs.load.__all__` exports appears in the doc; there is no equivalent
assertion tying the root list to `fitdocs.__all__`.

So the root list drifts silently. `tests/test_public_api.py:119` does pin
`fitdocs.__all__` — but against `_EXPECTED`, a list inside that same test
file. Adding a name updates `__all__` and `_EXPECTED` together and leaves the
documentation untouched, with the suite green.

## Why it matters

That list is what a third-party plugin author reads to learn what they may
import. A stale list is wrong in the direction that costs someone else time:
a name exists but is undocumented, so it looks unsupported.

The gap is about to be exercised. fit-ingest Amendment 1 task 11 adds
`TrimpWeighting` to the root surface. That task now carries a bullet telling
the implementer to update the prose by hand, which closes *this* instance —
and leaves the next one to chance, which is why the guard is the real fix.

## Evidence

Verified at `9df1d7b`:

- `docs/plugins.md:249-255` — the "From `fitdocs`:" block, 19 names as prose.
- `tests/test_docs_guarantees.py:297,327,344` — the only `__all__` assertions
  in the file, all against `fitdocs.load.__all__`. `:327` is the
  set-difference check that has no root-surface counterpart.
- `tests/test_public_api.py:119` — `assert set(fitdocs.__all__) == set(_EXPECTED)`,
  where `_EXPECTED` is declared in that test module, not read from the doc.

Distinct from `.kiro/queue/2026-07-26-plugin-surface-list-stale-after-amendment-3.md`,
which is about the `fitdocs.load` block's *content* being stale. This is about
the root block having no guard at all.

**Update 2026-07-29, `/kiro-impl fit-ingest` task 11 (commit `0ae83aa` on
`impl/fit-ingest`, NOT merged to main):** the instance this item predicted
happened exactly as described, and the guard is still the real fix.

- `TrimpWeighting` was added to `fitdocs.__all__`, to `_EXPECTED` in
  `tests/test_public_api.py`, and to `docs/plugins.md` — the last **only**
  because task 11's own text carried a bullet instructing it by hand. The root
  block is now 20 names.
- Confirmed by execution in that run: the doc's listed set and
  `set(fitdocs.__all__)` currently agree in both directions, so there is no
  live staleness — only the missing guard.
- Re-confirmed at `0ae83aa`: `tests/test_docs_guarantees.py:266-291` is still
  the listed-name-imports check (one direction only), and `:294-334` is still
  the completeness guard covering `fitdocs.load` alone.

**Do not cite `2026-07-26-plugin-surface-list-stale-after-amendment-3.md` as
tracking this gap.** A task-11 status report did; a verify pass then showed
that item covers the `From fitdocs.load:` list and `plugin-api/design.md`'s
copy, not the root block. This item is the one that owns it.

**Concurrency warning.** A peer session (`queue-top7`, worktree
`../fitdocs-pluginapi`, branch `chore/plugin-api-surface-guard`) has been
editing `tests/test_docs_guarantees.py`, adding three guards over
`.kiro/specs/plugin-api/design.md`. Task 11 deliberately did **not** add the
root guard for that reason. Re-read the shared agent log and check whether
that branch has merged before starting, or expect a conflict in the one file
this item must edit.

## How to pick it up

1. Read `tests/test_docs_guarantees.py` around `:290-330` — the
   `fitdocs.load` guard is the pattern to mirror, including how it parses the
   fenced block out of the markdown and its `deliberately_undocumented`
   escape set.
2. Add the root-surface equivalent. Keep the escape set, since a name may be
   exported but deliberately undocumented; make it explicit rather than
   implicit.
3. Give it a positive control — assert the parse found a non-empty list before
   comparing, so a renamed heading cannot make the guard pass by scanning
   nothing (`.kiro/steering/change-protocol.md`'s *vacuous walk* anti-pattern).
4. Done means: deleting a name from the doc's root block reddens the new test,
   and the mutation is recorded per the Fixture Discrimination gate.
