---
id: 2026-10-05-index-refresh-fails-whole-on-unloadable-athlete-toml
title: An athlete.toml the index refresh cannot load fails the whole refresh, including producers that never read it
status: open
importance: low
importance_why: A typo in athlete.toml stops every index table refreshing (mean-max, load series, blocks) though only profile-dependent ones need it; narrowed analytics-derived Req 8.5 to match.
effort: S
kind: inconsistency
area: analytics-index, analytics-derived
created: 2026-10-05
surfaced_by: /kiro-spec-batch phase 10 (analytics-derived Step 3.5 review)
pinned_at: 19fc92e
resume_command: "do: after analytics-index lands, decide whether refresh step 6 (load_athlete_inputs -> FAILED) should instead record athlete inputs as unavailable and let producers that do not depend on them refresh; if yes, amend analytics-index and restore analytics-derived Req 8.5's 'malformed athlete profile' wording"
context:
  - .kiro/specs/analytics-index/design.md
  - .kiro/specs/analytics-derived/requirements.md
  - .kiro/specs/analytics-derived/research.md
  - src/fitdocs/athlete.py
blocked_by: [analytics-index]
---

## What
analytics-index's refresh loads athlete inputs at step 6; an `athlete.toml`
that is not valid TOML, has a bad profile version or bad flat keys raises
`AthleteFileError` there and the refresh returns FAILED before any producer
runs (analytics-index design.md, Refresh section; `src/fitdocs/athlete.py`
62-91, 115-118, 130-183). analytics-derived therefore narrowed its Req 8.5
from "malformed athlete profile" to "a malformed benchmark entry in the
athlete profile" during its Step 3.5 review.

## Why it matters
Failure isolation is a Phase 10 principle ("index failures never cost the
pipeline"; one producer failing should not stop the others). Here one input
file stops all producers, including those that do not read it.

## Evidence
- analytics-derived research.md "Upstream issue 5" (Phase 10 spec batch).
- analytics-derived requirements.md Req 8.5 (narrowed wording).

## How to pick it up
1. Read analytics-index design § Refresh step 6 and the producer seam: which producers consume athlete inputs?
2. Decide: keep (documented) or degrade gracefully per producer.
3. If changing, it is an analytics-index amendment plus restoring derived Req 8.5.
