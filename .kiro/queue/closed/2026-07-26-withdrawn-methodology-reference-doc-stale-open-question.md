---
id: 2026-07-26-withdrawn-methodology-reference-doc-stale-open-question
title: Refresh the writeup's framing now that withdrawal (not licensing) settled its fate
status: dropped
importance: low
importance_why: Purely a research-record freshness issue — the file is explicitly out of shipped-availability scope and not read by any guard, but its own prose now contradicts the roadmap's resolution.
effort: S
kind: docs
area: training-load; the writeup (deleted by encumbered-content-purge task 3.1)
created: 2026-07-26
surfaced_by: task 5.2 (training-load) — inventorying every doc mentioning the third party or the withdrawn methodology before correcting shipped documentation
pinned_at: 7b0e14f
resume_command: "do: No action — dropped 2026-08-05 (encumbered-content-purge task 3.12). encumbered-content-purge task 3.1 already deleted the writeup and both extracted tables from the working tree, per Requirement 4's reversal of their prior retention as a research record; there is no file left for the framing fix this item requested to operate on. If a future session needs the reasoning that led here, read this item's ## Resolution section rather than reopening it."
context:
  - .kiro/steering/roadmap.md
  - .kiro/specs/training-load/design.md
  - .kiro/specs/training-load/tasks.md
blocked_by: []
---

## What
The writeup opened with "Reference for implementing
the first `LoadCalculator`: [the third party]'s [the withdrawn methodology]..." and a
`> **Licensing / attribution — OPEN QUESTION.**` callout describing licensing
permission from the third party as still pending before the methodology could
ship. Both statements were stale even before the file was deleted: the methodology
was withdrawn rather than licensed (training-load Amendment 2, ratified 2026-07-25), and
`.kiro/steering/roadmap.md:67-72` records the licensing question as
"resolved by withdrawal" — the permission was never obtained, and that
gated release rather than being solved. The writeup's own text still
read as if the licensing question was open and the withdrawn methodology was on track to ship.

## Why it matters
Task 5.2 (training-load, Req 13.3) is scoped to ensure no *shipped*
documentation presents the withdrawn methodology as available, and confirmed this file was out of
that boundary by explicit instruction (retained research record, do not
delete). But "not shipped" is not the same as "accurate" — a reader who
opened this file was told a decision was pending that was actually made
five days earlier, in the opposite direction the file implied. Low urgency
because the file was never read by any guard and was clearly namespaced under
`docs/reference/` (README.md already describes that directory as "research
and methodology references backing the specs," not shipped functionality),
but it was a real, verifiable inconsistency nobody had fixed.

## Evidence
- The writeup, lines 1-13 (as of `7b0e14f`): "Reference
  for implementing the first `LoadCalculator`" and the OPEN QUESTION
  licensing callout.
- `.kiro/steering/roadmap.md:67-72`: "**[the withdrawn methodology] licensing — resolved by
  withdrawal (2026-07-25).** ... that permission was never obtained and it
  gated any release of this repository. The methodology is withdrawn from
  the shipped tool (training-load Amendment 2) rather than licensed."
- `.kiro/specs/training-load/design.md:1733`: "**Retained**:
  the writeup and the extracted tables —
  steering records these as research references, not shipped data." (no
  instruction to refresh its prose)
- `git grep -n "OPEN QUESTION"` against the writeup's pre-deletion blob still
  returns the callout at `7b0e14f`.

**Superseded 2026-08-01**: `encumbered-content-purge` task 3.1 deleted the writeup
and the extracted tables from the working tree entirely, per Requirement 4's
reversal of their retention. The framing fix this item describes is moot — there
is no file left to refresh.

## How to pick it up
1. Read the writeup's opening section and the
   `> **Licensing / attribution — OPEN QUESTION.**` callout in full.
2. Read `.kiro/steering/roadmap.md:67-72` for the exact resolution wording to
   mirror.
3. Rewrite the opening paragraph and the callout to state, in past tense,
   that the withdrawn methodology was extracted as research and then withdrawn rather than
   shipped, and why (licensing permission never obtained). Do not touch the
   extracted tables or delete anything — this is
   a framing fix, not a content change.
4. Confirm no test references the callout's exact wording (`grep -rn "OPEN
   QUESTION" tests/`) before editing it.

## Open questions
None — this is a self-contained prose fix once picked up.

## Resolution

Dropped 2026-08-05 (`encumbered-content-purge` task 3.12). `encumbered-content-purge`
task 3.1 deleted the writeup and both extracted tables from the working tree
entirely, per Requirement 4's reversal of their prior retention as a research
record — the "Superseded 2026-08-01" note above already recorded that the
framing fix this item requested has no file left to operate on. The "How to
pick it up" steps above are kept as the record of what would have been done
had the file survived; they are not actionable now and should not be followed.
Renamed to `2026-07-26-withdrawn-methodology-reference-doc-stale-open-question`
from a prior stem built on the third party's surname, under Req 11.2 (no
identifying token survives in a tracked path).
