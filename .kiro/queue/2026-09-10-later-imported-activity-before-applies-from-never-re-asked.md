---
id: 2026-09-10-later-imported-activity-before-applies-from-never-re-asked
title: An activity imported after the first prompted pass and dated before the recorded applies_from is still unscorable and never re-asked — the prompt-date item's own symptom, narrowed to later imports
status: open
importance: medium
importance_why: fitdocs' primary user imports an archive in batches (the HealthFit listing showed 74 files where the real archive held 2478); every file older than the first batch's earliest activity lands not-computed with seven benchmarks on file, and only a hand edit of applies_from recovers it. Amendment 4 fixed the first pass; this is what it deliberately did not fix.
effort: M
kind: gap
area: training-load, athlete-benchmarks, src/fitdocs/load/prompts.py, src/fitdocs/load/engine.py
created: 2026-09-10
surfaced_by: /kiro-validate-impl training-load (Amendment 4, coverage + integration dimension)
pinned_at: 52c473e
resume_command: "/kiro-spec-requirements training-load [queue: .kiro/queue/2026-09-10-later-imported-activity-before-applies-from-never-re-asked.md] Decide whether the load pass may offer to extend an on-file entry's applies_from when a newly imported activity predates it"
context:
  - .kiro/specs/training-load/requirements.md
  - .kiro/specs/athlete-benchmarks/requirements.md
  - src/fitdocs/load/prompts.py
  - src/fitdocs/load/engine.py
  - tests/load/test_prompt_date_e2e.py
  - .kiro/queue/2026-08-27-not-applicable-has-no-readers.md
blocked_by: []
---

## What

Amendment 4 dates a prompt answer's `applies_from` to the activity that
prompted it — the earliest fillable document in *that* pass. Presence is
deliberately undated (athlete-benchmarks 8.3: a benchmark on file is never
re-asked), so a document imported later and dated before that
`applies_from` finds seven benchmarks on file, none applicable, and no
question. The coverage validator reproduced it end to end: yes-flow on a
2026-06-01 document (`applies_from = 2026-06-01`), then sync a 2026-01-15
file and run the pass again → `computed: []`, the older document in
`skipped` with "no functional-threshold-power benchmark was supplied …",
**0 questions asked**.

## Why it matters

This is the queue item `2026-08-27-prompt-date-strands-historical-documents`'s
own Evidence block, scoped down from "every historical activity" to "every
activity imported after the first prompted pass and older than it". Batch
imports are the normal case for this product. Recovery exists (edit
`applies_from` in `athlete.toml`, documented in `docs/ownership-contract.md`)
but nothing points the athlete at it: the reason text still says the
benchmark "was not supplied" (tracked separately as
`2026-08-27-not-applicable-has-no-readers`).

## Evidence

- Reproduction above (coverage validator, 2026-09-10, on 52c473e; the
  parent did not re-run it — repeat with `tests/load/test_prompt_date_e2e.py`'s
  helpers and a second `_run_fit_bytes` dated earlier).
- `src/fitdocs/load/prompts.py` `collect_missing_fields`: the presence check
  is `profile.has_benchmark(...)`, undated by design (8.3); the question is
  asked only on the path where nothing is on file.
- training-load requirements.md, Amendment 4, the *What this does not do*
  paragraph added 2026-09-10 recording this residual.

## How to pick it up

1. Read Amendment 4 and athlete-benchmarks 8.3/8.4 — the "ask once" rule is
   load-bearing and the fix must not re-ask for the value.
2. Candidate shapes, each a requirements decision: (a) when a fillable
   document predates every entry of a required kind/scope and the earliest
   such entry carries `applies_from`, ask once per pass "extend it back to
   this activity's date?" and rewrite `applies_from` on that entry; (b) do
   nothing but make the not-applicable reason name the entry's
   `applies_from` and the hand edit; (c) both.
3. Done: an e2e scenario — first pass on a later document, second pass
   after importing an earlier one — that scores the earlier document (a/c)
   or prints an actionable reason (b), with the ask-once tests still green.

## Open questions

- Is rewriting an existing entry's `applies_from` from the prompt flow
  compatible with 6.3/6.10 (the store replaces by `(discipline, kind,
  measured_on)`), or does it need its own store operation?
