---
id: 2026-08-09-pin-repair-reports-a-count-not-the-tokens
title: The pin repair tool reports how many identifier-shaped tokens it left alone but not which, so the provenance record cannot name them
status: done
importance: medium
importance_why: Task 8.1 runs this once after the rewrite and task 8.2 must record what it found; a bare integer forces 8.x to re-derive the token list from a repository whose pre-rewrite state no longer exists.
effort: S
kind: gap
area: encumbered-content-purge, scripts/purge/pins.py
created: 2026-08-09
surfaced_by: /kiro-impl encumbered-content-purge (task 5.6 review, round 1)
pinned_at: c3d2201
resume_command: "do: Decide before task 8.1 runs whether ReferenceRepair should return the unrepaired identifier-shaped tokens themselves rather than only their count, since 8.2's provenance record is written after the pre-rewrite repository is gone."
context:
  - scripts/purge/pins.py
  - .kiro/specs/encumbered-content-purge/tasks.md
  - .kiro/specs/encumbered-content-purge/design.md
blocked_by: []
---

## What

Task 5.6's brief says the tool must "**Report** every identifier-shaped token it
did not rewrite, with a count. Silent non-repair would read as completeness."

`scripts/purge/pins.py` reports the **count**. `RepairReport` exposes
`total_other_identifier_tokens -> int`, and no API returns the tokens
themselves. The requirement's first clause — report *every token* — is
satisfied only in the sense that the number of them is disclosed.

## Why it matters

The consumer is task 8.1, which runs the repair once against the real joined
commit map after the rewrite, and task 8.2, which writes the provenance record
from what 8.1 found.

A count answers "did anything go unrepaired?" but not "what, and does it
matter?" — and by the time 8.2 is writing, the pre-rewrite repository has been
destroyed, so re-deriving the list means reconstructing identifiers that no
longer resolve anywhere. The cheap moment to capture them is while the tool is
already walking every file.

This is not a correctness defect in the repair itself: leaving non-pin
references exactly as written is deliberate and correct — they resolve through
the commit map, and rewriting prose that records what was true at a moment
would falsify it. The gap is only in what the run tells its consumer.

## Evidence

`scripts/purge/pins.py::count_other_identifier_tokens` returns an `int`;
`FileRepairResult.other_identifier_token_count` is an `int`;
`RepairReport.total_other_identifier_tokens` sums them. Nothing in the module
returns the matched substrings, and no test asserts they are available, because
none could.

Two related observations from the same review, both minor and both arguing the
list is more informative than the number: the token regex counts a plain
seven-digit decimal as identifier-shaped
(`count_other_identifier_tokens("created on 20260726 at noon") == 1`), and it
is case-sensitive to lowercase hex, so the count includes some false positives
and may miss uppercase spellings. A count carries those distortions invisibly;
a list makes them obvious to a reader.

## How to pick it up

Read `count_other_identifier_tokens` and the two dataclasses it feeds, then
tasks 8.1 and 8.2 in `tasks.md` to see exactly what the provenance record is
required to say about unrepaired references.

The change is small — return the matched values alongside the count, keyed by
file — but it touches a module whose tests took three review rounds, so the
existing count assertions and their mutations should be preserved rather than
replaced. Note that a list of identifiers is not sensitive under Req 11.1: a
commit identifier carries no token by construction.

Done when 8.2 can name what went unrepaired without re-reading a repository
that no longer exists, or when a deliberate decision that the count suffices is
recorded in the design.

## Open questions

Whether the false-positive classes (bare decimals, uppercase hex) should be
narrowed at the same time. Narrowing changes the count, and the count is
currently pinned by tests — so the two changes want to land together with their
assertions re-based in the same commit rather than sequentially.

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
