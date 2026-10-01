---
id: 2026-10-01-same-files-give-one-page-in-one-run-and-two-pages-across-runs-when-a-match-chains
title: Files that match only through each other (A~B, B~C, not A~C) form one page in one run but two pages across separate runs, which Req 5.7 forbids and Req 3.10 causes
status: open
importance: low
importance_why: Needs three files whose starts chain within the 1 s tolerance without the outer two matching, so it is rare; but it makes the page set depend on arrival timing, which is the property Req 5.7 exists to guarantee.
effort: M
kind: inconsistency
area: activity-identity, src/fitdocs/identity/planning.py, src/fitdocs/identity/matching.py
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "/kiro-spec-requirements activity-identity [queue: .kiro/queue/2026-10-01-same-files-give-one-page-in-one-run-and-two-pages-across-runs-when-a-match-chains.md] Decide how Req 5.7 (same files, any order or run split, same page) and Req 3.10 (compare against the page's base values only) coexist for a chained match"
context:
  - .kiro/specs/activity-identity/requirements.md
  - .kiro/specs/activity-identity/design.md
  - src/fitdocs/identity/planning.py
  - src/fitdocs/identity/matching.py
blocked_by: []
---

## What
Req 4.2 groups a run's free files by chaining ("directly or through other such
files"), and a group matches a page when any member matches the page's base. Req
3.10 compares an incoming file with an existing page through the page's recorded
base values, session UUID and source list only, never through its extras. So
with a page whose base is A, a file B within tolerance of A, and a file C within
tolerance of B but not of A: B and C arriving in one run are one group and both
join A's page; B arriving in one run and C in a later one leaves C unmatched
(compared only with A), so C becomes its own page. Req 5.7 says the same set of
files reaches a page "in any order, across one run or several" with byte
identical output.

## Why it matters
The page set depends on how arrivals were batched (an inbox drained at
different times), which is the order dependence Req 4.8 and 5.7 were written to
remove. Nothing reconciles it afterwards: the new page is not a duplicate of A's
under Req 8.3, whose base-identity comparison also sees only A's base.

## Evidence
Reproduced at `fc5c06d` with the pure planner (`uv run python`), keys sharing
sport, elapsed 3600 s and distance 10 km, starts A=t0, B=t0+0.9 s, C=t0+1.8 s,
page record `workouts/a.md` with `key=A`:
- `plan_run([B, C], index)` -> `{'b': Join, 'c': Join}`
- `plan_run([C], index)` (the run after B joined, A still the base) -> `{'c': Fresh}`
- Code: `src/fitdocs/identity/planning.py:217-234` (candidate pages found by
  comparing group members with `record.key`, the page's base key only);
  `src/fitdocs/identity/planning.py:49-55` (`PageRecord` carries one `key`);
  requirements 3.10, 4.2, 5.7 at
  `.kiro/specs/activity-identity/requirements.md:157, 167, 190`.

## How to pick it up
1. Read the three requirements and `design.md`'s RunPlanner section; confirm the
   repro with the planner before choosing.
2. Take the maintainer's decision (Open questions), then amend the requirement
   text or the planner to match, and pin the chosen behavior with the repro as a
   test in `tests/identity/test_planning.py`.

## Open questions
- Amend Req 5.7 to carve out chained matches (the rule is deliberately
  base-only, so a later file can match only the base), or record extras' keys
  on the page so a later file can chain through them (conflicts with Req 3.10's
  "page values only" and grows the frontmatter), or have `regen` re-evaluate
  separate pages for chain evidence (merging pages is forbidden by Req 4.9)?
