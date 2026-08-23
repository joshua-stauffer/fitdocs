---
id: 2026-08-09-modified-files-table-sample-eroded
title: The sweep's modified-files sample has eroded to two entries under one prefix, and the superset check it feeds is correspondingly weak
status: done
importance: medium
importance_why: The check reads as a tree-wide coverage assertion and is now a two-file one; each task that drove a module to zero tokens removed another entry, and only a non-empty check stands between it and vacuity.
effort: S
kind: gap
area: encumbered-content-purge, tests/purge/test_sweep.py
created: 2026-08-09
surfaced_by: /kiro-impl encumbered-content-purge (task 6.1 review, round 2)
pinned_at: c3d2201
resume_command: "do: Decide whether _MODIFIED_FILES_TABLE_SAMPLE in tests/purge/test_sweep.py should be re-populated with live token-bearing paths, replaced by a different coverage assertion, or retired with its weakness recorded."
context:
  - tests/purge/test_sweep.py
  - .kiro/specs/encumbered-content-purge/design.md
blocked_by: []
---

## What

`_MODIFIED_FILES_TABLE_SAMPLE` in `tests/purge/test_sweep.py` feeds a superset
check that reads as a broad coverage assertion over the sweep inventory. It now
holds **two** entries, both under `.kiro/specs/`, while the live sweep spans
four top-level prefixes.

Task 4.2 already recorded the mechanism: "every Major 4 task that drives a
module to zero tokens removes another entry, and there are two such tasks left."
Both of those tasks have since landed. The erosion is the designed consequence
of the purge succeeding, not a defect in any one change — but nothing re-based
the check as its needles disappeared.

## Why it matters

A superset check over a two-element set is nearly vacuous, and it does not
announce that. The only thing standing between it and complete vacuity is a
non-empty assertion.

The specific risk is misreading rather than breakage: a later session looking
for "is the sweep's coverage pinned?" finds a superset check and a comment block
naming six path prefixes, and concludes the answer is yes. Task 6.1's
classification made exactly that mistake in prose — it described the check as
"spanning `.kiro/specs/`, `.kiro/steering/`, `.kiro/queue/`, `docs/`, `tests/`
and `src/`", six prefixes lifted from the comment block above the tuple, which
lists paths *deliberately excluded*. The tuple's real contents are two entries
under one prefix.

## Evidence

AST-evaluated from the source rather than read:

```
entries: 2
    .kiro/specs/distribution/design.md
    .kiro/specs/encumbered-content-purge/brief.md
distinct top-level prefixes: ['.kiro']
```

The live sweep's coverage set spans four prefixes (`.kiro/queue`, `.kiro/specs`,
`scripts`, `tests`) — matching neither the tuple nor the six-prefix description.

The `PINNED` label the classification gives the underlying requirement is
sound and unaffected: mutating the walk's `check=True` to `check=False` reds
`test_tracked_files_raises_rather_than_silently_return_an_empty_universe` as a
sole failure. It is the *sample* that has eroded, not the walk.

## How to pick it up

Read the tuple and the comment block above it first, and note that the comment
enumerates exclusions rather than contents — that is what misled the
classification, and it will mislead the next reader the same way.

Three options, in rough order of preference: re-populate the sample from paths
that still carry a token (there are few, by construction, and Req 2.5's
retained fragments are the obvious candidates); replace the superset check with
an assertion that actually scales with the tree; or retire it and record in the
test's own docstring that sweep coverage is pinned by the non-vacuous-walk
assertion alone.

Whichever is chosen, the comment block should stop looking like a contents list.

Done when the check either asserts something proportionate to its apparent
scope, or says plainly that it does not.

## Open questions

Whether this survives Major 7 at all. The sweep inventory is a pre-rewrite
artifact and several of its consumers are one-shot; if the check has no
post-rewrite role, retiring it is cheaper than re-basing it.

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
