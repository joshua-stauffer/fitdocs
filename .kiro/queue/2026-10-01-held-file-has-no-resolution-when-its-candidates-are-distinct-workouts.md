---
id: 2026-10-01-held-file-has-no-resolution-when-its-candidates-are-distinct-workouts
title: A held file whose candidate pages are distinct workouts, and a Req 4.6 hold with a single candidate page, have no resolution the athlete can act on
status: open
importance: medium
importance_why: A file that is a genuine third workout, or one of two competing groups, stays held and reported forever with a remedy that tells the athlete to delete pages that are not duplicates.
effort: M
kind: gap
area: activity-identity, src/fitdocs/audit.py, docs/ownership-contract.md
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "/kiro-spec-requirements activity-identity [queue: .kiro/queue/2026-10-01-held-file-has-no-resolution-when-its-candidates-are-distinct-workouts.md] Decide how a held file is released when its candidates are not one workout (Req 8.1 names an action for every hold)"
context:
  - .kiro/specs/activity-identity/requirements.md
  - .kiro/specs/activity-identity/design.md
  - src/fitdocs/audit.py
  - src/fitdocs/identity/planning.py
  - docs/ownership-contract.md
blocked_by: []
---

## What
Req 4.5 holds a file that matches two or more existing pages, Req 4.6 holds
every group of a run when two groups each match the same page, and Req 8.1
requires `fitdocs check` to report each hold "with the action that resolves
it". There is exactly one action text, `_REMEDY_ONE_WORKOUT`: "if the candidate
pages are one workout, keep one ..., delete the other, and run `fitdocs regen`".
It is wrong or empty for two shapes:
1. The candidates are genuinely different workouts and the file is neither (a
   tolerance-edge false positive, or a distinct third workout). Nothing releases
   the file. The ownership contract says "in any other case the file stays held,
   and is reported, until the pages change".
2. A Req 4.6 hold has one candidate page. "Keep one, delete the other" has no
   second page to delete, and the finding prints `could be a page of
   <that one page>`.

## Why it matters
Both leave `fitdocs check` reporting an `ambiguous_source` finding permanently
with advice that does not apply. A file the athlete wants on its own page cannot
get one, because every `regen` re-holds it and the archive file must not be
deleted (the archive is immutable input).

## Evidence
Read at `fc5c06d`; the single-candidate hold reproduced with the pure planner.
- `src/fitdocs/audit.py:225-229` `_REMEDY_ONE_WORKOUT`; `:481-486` the hold finding
  (`detail` = `held {name!r}: could be a page of {candidates}; evidence: ...`,
  `remedy=_REMEDY_ONE_WORKOUT`). The same text is reused for duplicate-set
  findings at `:536`.
- `docs/ownership-contract.md:538-541`: "If the candidate pages are one workout,
  keep one ..., delete the other ... In any other case the file stays held, and is
  reported, until the pages change."
- `src/fitdocs/identity/planning.py:252-256`: `Hold(tuple(paths), ...)` is built
  both when `len(found) > 1` and when one page is matched by two groups.
- Repro (`uv run python`): a page `workouts/a.md` with key start t0 and two
  free files with starts t0+0.9 s and t0-0.9 s (same sport, elapsed, distance;
  they do not link to each other, 1.8 s apart) give
  `plan_run(...)` decisions `{c1: Hold(candidates=('workouts/a.md',), evidence=(STRICT,)),
  c2: Hold(candidates=('workouts/a.md',), evidence=(STRICT,))}`.

## How to pick it up
1. Read requirements 4.5-4.7 and 8.1, `design.md`'s hold sections, and
   `docs/ownership-contract.md` "Held files".
2. The maintainer picks the release path (Open questions); then change the
   requirement text, the finding's remedy (one text per hold shape, chosen in
   `_held_findings`), and the contract paragraph together, and pin each remedy in
   `tests/test_audit.py`.

## Open questions
- How does an athlete say "this held file is its own workout"? Candidates: a
  per-file release in the settings file or a sidecar the hold record reads, a
  `fitdocs` flag that plans the file ignoring the tolerance rule, or "delete the
  archive file and the candidate evidence is gone" (contradicts archive
  immutability). Or accept the limitation and make the remedy text say so.
- For a single-candidate hold, what is the action? Unverified idea for the
  picking-up session to test rather than assume: the planner decides a group
  against the pages as they stand at plan time, so the same two files arriving
  in two separate runs may each join the page instead of being held.
