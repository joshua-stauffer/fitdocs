---
id: 2026-09-11-ownership-doc-placement-unconditional
title: The published contract states the user-key placement rule unconditionally, and it is false after a load pass
status: done
importance: high
importance_why: A published user-facing guarantee is false of the state a user sees whenever training load is computed, and the nearest pin cannot reach the case.
effort: S
kind: docs
area: effort-tags, docs/ownership-contract.md, src/fitdocs/load/docedit.py, tests/test_sync.py
created: 2026-09-11
surfaced_by: /kiro-impl effort-tags 4.2 review, reconfirmed by 5.3 feature validation
pinned_at: d1147a0
resume_command: "/kiro-impl effort-tags [queue: .kiro/queue/2026-09-11-ownership-doc-placement-unconditional.md] Scope the Frontmatter Ownership placement sentence to a rebuild, and pin the post-load ordering"
context:
  - docs/ownership-contract.md
  - src/fitdocs/load/docedit.py
  - tests/test_sync.py
  - .kiro/specs/wiki-contract/requirements.md
blocked_by: []
---

## What

`docs/ownership-contract.md` states the placement rule twice with different
scope. `## Frontmatter Ownership` (~117-126) says user-owned keys are "carried
over verbatim, unchanged, and **placed after the managed keys**" with no
qualifier. The sibling `## User-Owned Frontmatter Keys` section (~196) scopes
the same rule correctly: "*When a document's frontmatter block is rebuilt*, the
carried user-owned lines are placed after every managed key."

The unconditional form is false once a load pass produces a result.
`src/fitdocs/load/docedit.py:289` builds `[lines[0], *kept, *managed,
*lines[close:]]` -- the carried user lines are inside `kept`, so the three
`load_*` keys are appended *after* them.

wiki-contract criterion 6.6, added by effort-tags task 4.3, is correctly scoped
to a full rebuild and is NOT affected. This is a defect in the published
document only.

## Why it matters

The ownership contract is the document fitdocs points users and agents at to
answer "what does the tool own and what do I own". A user who hand-adds an
effort tag and then runs `fitdocs load` sees their keys sitting before three
tool-written keys, contradicting the document they were told to trust. Two
sections of one document disagreeing is worse than either wording alone.

## Evidence

Executed during task 5.3 validation at `e39b35f`:

```
apply_frontmatter_load(doc_with_all_four_effort_keys, LoadResult(...)) ->
  effort/effort_distance_m/effort_time_s/effort_event at indices 4-7
  load_value/load_methodology/load_basis at indices 8-10
  "ALL user-owned lines placed AFTER the managed keys?" -> False
```

Cause: `src/fitdocs/load/docedit.py:289`.

The nearest existing pin is
`tests/test_sync.py::test_carried_lines_sit_after_the_last_managed_key` (~2082),
which passes `athlete=None` at lines 2087 and 2096 -- so no load pass ever runs
and the assertion never reaches the case. This is the `unreachable scenario`
anti-pattern from `.kiro/steering/change-protocol.md` hiding a false published
guarantee rather than a weak test.

## How to pick it up

1. Read both sections of `docs/ownership-contract.md` and `wiki-contract`
   criterion 6.6 (which shows the wording that is already correct).
2. Decide the fix: either scope the `## Frontmatter Ownership` sentence the way
   the sibling section does, or state both placements explicitly (rebuild vs
   after a load pass). Prefer describing what the code does over softening.
3. Add the missing pin: a test that runs a load pass to `Computed` (force a
   field-free stub calculator via `--calculator`, pattern at
   `tests/load/test_cli_load.py::_FieldFreeCalculator`) and asserts the observed
   ordering. Without it the new wording is unpinned too.

Done looks like: the document says one thing about placement, that thing is
true on both paths, and a test reds if the ordering changes.
