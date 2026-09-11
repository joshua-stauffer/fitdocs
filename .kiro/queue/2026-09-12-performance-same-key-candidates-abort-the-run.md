---
id: 2026-09-12-performance-same-key-candidates-abort-the-run
title: Two same-key derivation candidates abort the run instead of one declining
status: open
importance: medium
importance_why: A run that should write one accepted entry and decline the other instead raises ProfileError and writes nothing at all.
effort: S
kind: bug
area: performance-benchmarks, src/fitdocs/performance/engine.py
created: 2026-09-12
surfaced_by: /kiro-impl performance-benchmarks (adversarial reviews, 2026-09-11/12)
pinned_at: d4fbc6f
resume_command: "/kiro-impl performance-benchmarks [queue: .kiro/queue/2026-09-12-performance-same-key-candidates-abort-the-run.md] decide and implement same-key candidate handling in the pass"
context:
  - src/fitdocs/performance/engine.py
  - src/fitdocs/load/profile.py
blocked_by: []
---

## What

Two tagged pages of the same sport dated the same day are both accepted by the
pass. `with_derived_benchmarks` builds a document with two entries at one key,
and `AthleteProfile.__post_init__`'s re-parse of that document raises
`ProfileError` on the FIRST run — fatal, nothing written.

## Why it matters

The engine has no code path that declines the second candidate by name; the
failure mode is a crash on the first run, not a graceful decline, so a run
that should write one accepted entry and decline the other writes nothing at
all.

## Evidence

(4.3 r2 reviewer, CORRECTS the 4.3 reviewer's earlier note) "two tagged pages
of the same sport dated the same day are both accepted; with_derived_benchmarks
builds a document with two entries at one key and AthleteProfile.__post_init__'s
re-parse raises ProfileError from engine.py on the FIRST run -- fatal, nothing
written." The earlier 4.3 reviewer note ("the merge keeps one, so `written`
is True every run though bytes are identical") is explicitly superseded by
this correction — the merge does NOT dedupe.

## How to pick it up

1. Read `with_derived_benchmarks` and the merge/build path in
   `src/fitdocs/performance/engine.py`, and `AthleteProfile.__post_init__`'s
   re-parse in `src/fitdocs/load/profile.py`.
2. Reproduce: two tagged pages, same sport, same `measured_on` date, both
   producing a derivation candidate.
3. Decide same-key handling (see Open questions) and implement it in the pass
   before the document is built, so the re-parse never sees a duplicate key.

## Open questions

- Decline the second candidate by name (like `SUPERSEDED_BY_RECORDED`), or
  abort the run with a clear diagnostic instead of the current uncontrolled
  `ProfileError`?
</content>
