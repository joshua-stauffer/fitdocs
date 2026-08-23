---
id: 2026-07-29-b91-session-summation-locator-under-specified
title: B91's session-summation claim is cited to one page but attested across pp. 406-409
status: open
importance: low
importance_why: Task 12.3 reproduces each work's published worked example and will follow these locators; an under-specified one sends it to a page that carries only part of the claim.
effort: S
kind: inconsistency
area: fit-ingest, docs/reference/banister-trimp-primary-sources.md, src/fitdocs/metrics/sources.py
created: 2026-07-29
surfaced_by: /kiro-impl fit-ingest (task 9.4 review rounds 1 and 3)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest 12.3 [queue: .kiro/queue/2026-07-29-b91-session-summation-locator-under-specified.md] Reconcile the B91 session-summation locator across the extraction doc and the integration departure"
context:
  - docs/reference/banister-trimp-primary-sources.md
  - src/fitdocs/metrics/sources.py
  - tests/metrics/test_sources.py
blocked_by: []
---

## What

Two places cite Banister (1991) for the claim that training-impulse scores are
summed over segments of near-constant heart rate, each segment contributing its
own average HR. Neither locator covers the whole claim, and they disagree with
each other:

- `src/fitdocs/metrics/sources.py:620` (the `trimp-per-sample-integration`
  departure's `source_specifies`) cites **"Banister (1991) p. 408"**.
- `docs/reference/banister-trimp-primary-sources.md` §1 cites the subperiod
  split at **"(pp. 406, 409)"** — omitting 408.

The task-9.4 reviewer read the actual page scans and found the claim is
attested across three pages: p. 406 has "during activities when HR reaches
steady state" (the near-constant condition), p. 408's final line begins
"Training impulse scores from each phase of a [training session are added to
give session totals]" (the summation, completing on p. 409), and p. 409's
Fig. 9.5 caption supplies "an average HR of about 150" (the per-segment
average). `pp. 406-409` is the exact locator.

Neither citation is **false** — B91 does say all of it, and the reviewer
explicitly ruled this non-blocking for task 9.4 on that basis. But each names a
page that carries only part of what it is cited for.

## Why it matters

Task 12.3 reproduces each cited work's published worked example, and it will
navigate by these locators. Sending it to p. 408 alone for a claim whose
conditions are on p. 406 and whose per-segment average is on p. 409 means it
either re-derives the page range or records a partial reading — and 12.3 is
precisely the task where a locator has to be exact.

The extraction doc's omission of 408 is the more consequential half: p. 408 is
where the summation sentence actually starts, and §1 skips it.

Low importance because no value moves and no claim is wrong; this is locator
precision in an artifact whose whole purpose is locator precision.

## Evidence

At `bf588a5` with task 9.4's work applied:

- `src/fitdocs/metrics/sources.py:620` — "Both Banister (1991) p. 408 and
  Morton (1990) p. 1172 sum the …". Note this string is pinned by
  `BACKSTOP_INTEGRATION_SOURCE_SPECIFIES` in `tests/metrics/test_sources.py`,
  so changing it is a coordinated two-file edit plus a re-run of that record's
  mutation — which is why it was not done inside task 9.4.
- `docs/reference/banister-trimp-primary-sources.md` §1 — locates the subperiod
  split at "pp. 406, 409".
- The page scans in this worktree under
  `bannister_physiological_testing_of_the_high_performance_athlete/` — the
  task-9.4 reviewer read them directly and reported: p. 408's final line is
  "Training impulse scores from each phase of a", continuing onto p. 409; the
  steady-state condition is p. 406; the "average HR of about 150" is the
  Fig. 9.5 caption on p. 409.

Reported by the task-9.4 reviewer across rounds 1 and 3 (round 1 withdrew a
different locator finding after reading the same scans, so the readings are
first-hand rather than inferred from the extraction).

## How to pick it up

1. Open the p. 406-409 scans and confirm the three attestations for yourself —
   this item exists because a second-hand locator was wrong, so do not take the
   summary above as the evidence.
2. Fix `docs/reference/banister-trimp-primary-sources.md` §1 to name the full
   range. That file is a working document, not a citation source, so it can be
   edited freely (Req 15.5 forbids *citing* it, not maintaining it).
3. Decide whether to widen `sources.py:620` to `pp. 406-409`. If yes, retype
   `BACKSTOP_INTEGRATION_SOURCE_SPECIFIES` by hand to match — never copy it out
   of the module — and re-run that record's discrimination mutation.
4. While there, check whether any other locator in `sources.py` or the
   extraction doc cites a single page for a claim that spans several. Only the
   B91 summation was checked.

Done means: the extraction doc and the departure record name the same page
range, and that range covers every clause each is cited for.
