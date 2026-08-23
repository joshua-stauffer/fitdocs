---
id: 2026-08-24-task-3-2-bullet-demands-a-retired-intervals-icu-claim
title: Task 3.2's bullet demands an intervals.icu interop claim its own citation retired
status: open
importance: high
importance_why: An approved task bullet instructs the implementer to write a claim that a standing guard exists to prevent, and following it produced exactly that overclaim once already.
effort: S
kind: inconsistency
area: load-channels, .kiro/specs/load-channels/tasks.md, src/fitdocs/load/channels/sources.py
created: 2026-08-24
surfaced_by: /kiro-impl load-channels task 3.2 adversarial review
pinned_at: 4aba266
resume_command: "/kiro-spec-tasks load-channels [queue: .kiro/queue/2026-08-24-task-3-2-bullet-demands-a-retired-intervals-icu-claim.md] Correct task 3.2's intervals.icu bullet to match the 2026-07-26 citation correction"
context:
  - .kiro/specs/load-channels/tasks.md
  - src/fitdocs/load/channels/sources.py
  - src/fitdocs/load/channels/heart_rate.py
  - tests/load/channels/test_sources.py
blocked_by: []
---

## What

Task 3.2's bullet in `tasks.md` requires the heart-rate module to document that
intervals.icu "computes the heart-rate **load** the same way and requires the
same three inputs, so the load is an interop match rather than a divergence."

`INTERVALS_ICU_HRSS`'s note in `sources.py` says the opposite is what the
sources support: "Neither post publishes HRSS's formula, so that is the extent
of what the read text supports here; it does not establish that fitdocs'
heart-rate load is a numerically exact interop match with intervals.icu's
HRSS." The note is dated **Resolved 2026-07-26** and records that the module
docstring and the `heart_rate_reported_intensity` divergence entry *previously*
asserted exactly this and were rolled back to claim only the shared scale.

`tests/load/channels/test_sources.py:1089` carries a standing guard against the
claim returning to the `Divergence` record.

The task bullet was written 2026-07-25 — one day before the correction — and
was never updated. It is the only place in the spec still demanding the retired
wording.

## Why it matters

The bullet is not inert prose: it is an instruction an implementer follows. It
produced the overclaim once already, in `heart_rate.py`'s first draft, written
one file over from where the standing guard reaches. Two sub-claims are
independently unsourced — "computes the same way" (the source publishes no
formula at all) and "requires the same three inputs" (neither cited post
mentions HRSS's inputs).

Left as is, the next session to regenerate or re-run this task reproduces the
same defect, and the guard that exists to catch it is in a module the task does
not touch.

## Evidence

At `4aba266`:

- `.kiro/specs/load-channels/tasks.md`, task 3.2, the intervals.icu bullet
- `src/fitdocs/load/channels/sources.py` `INTERVALS_ICU_HRSS.note`, ~lines
  326-338, carrying the "Resolved 2026-07-26" record
- `tests/load/channels/test_sources.py:1089` — `assert "exact interop match"
  not in combined`, with the reason "INTERVALS_ICU_HRSS publishes no formula
  and cannot support it"
- the `heart_rate_reported_intensity` `DIVERGENCES` entry, which says "on the
  same scale ... directly comparable ... Numeric identity is not claimed"

The implementation has been corrected in place: `heart_rate.py`'s docstring now
claims only the shared scale and states explicitly that it does not claim
intervals.icu computes the load the same way. The spec text is what remains
wrong.

## How to pick it up

1. Read the bullet in `tasks.md`, then `INTERVALS_ICU_HRSS.note` and the
   `heart_rate_reported_intensity` entry in `sources.py`.
2. Rewrite the bullet to demand what the citation supports: the same scale and
   definition, directly comparable, numeric identity not claimed.
3. Check whether Req 5.x in `requirements.md` carries the same stale wording —
   if it does, the amendment is a requirements change, not a tasks change, and
   `spec.json`'s approval flags need the maintainer's attention.

Done looks like: no artifact in the spec instructs a future session to write a
claim the standing guard forbids.

## Open questions

- Does the corresponding requirement section carry the retired wording too? If
  so this needs a requirements amendment and a re-approval, not a task edit.
- Should the standing guard in `test_sources.py` be widened to sweep module
  docstrings as well as the `Divergence` records, so the next occurrence is
  caught wherever it lands rather than only in `sources.py`?
