---
id: 2026-07-28-np-window-start-has-no-criterion
title: The NP rolling-window start condition changes reported values but has no acceptance criterion of its own
status: done
importance: medium
importance_why: The only value-moving change in fit-ingest Amendment 1 is pinned by design prose and one test, not by a criterion. A later session simplifying `_trailing_rolling_mean` back to partial windows would move every athlete's NP, IF, VI and TSS again with no requirement to catch it.
effort: S
kind: gap
area: fit-ingest, .kiro/specs/fit-ingest/requirements.md
created: 2026-07-28
surfaced_by: /kiro-validate-design fit-ingest (design revision for the three gate findings)
pinned_at: 59014ea
resume_command: "/kiro-spec-requirements fit-ingest [queue: .kiro/queue/2026-07-28-np-window-start-has-no-criterion.md] Add an acceptance criterion for the normalized-power rolling-window start condition, which Req 8.4 leaves unstated"
context:
  - .kiro/specs/fit-ingest/requirements.md
  - .kiro/specs/fit-ingest/design.md
  - .kiro/specs/fit-ingest/research.md
  - src/fitdocs/metrics/power.py
blocked_by: []
---

## What

The maintainer ruled 2026-07-27 that fitdocs' normalized-power rolling mean
should follow Coggan's step 1 fully: emit only complete 30-second windows,
dropping the partial-window averages the first pass emitted over the first 29
points. That ruling is now recorded in `design.md` (PowerSeriesMetrics, and
Decision D7 in `research.md`) and it moves reported NP, IF, VI, TSS and bike EF.

Req 8.4 — the criterion that governs normalized power — mandates "1 Hz
resampling with coasting as zero, a trailing rolling mean, and a power mean,
whose window width, averaging exponent and minimum required span are sourced and
cited per Requirement 15." It says nothing about where the rolling mean starts.

So the new behavior is authorized (it does not contradict 8.4) but not
*required*. Nothing in `requirements.md` would fail if it were reverted.

## Why it matters

This is the single value-moving change in Amendment 1 — the reason
`contract.DOC_VERSION` advances 3 → 4 and every committed document goes stale
until regenerated. It is currently held in place by design prose plus the test at
Testing Strategy §13. Both are real, and neither is a criterion.

The specific failure mode: `_trailing_rolling_mean`'s partial-window form is the
*simpler* implementation (`count = min(i + 1, window)` and emit at every index).
A future session tidying that function, or a reviewer asking why the first 29
points are discarded, has no requirement to point at — only a design paragraph
and a test whose intent has to be read. If it flips back, every athlete's NP
moves a second time and a second `DOC_VERSION` bump is owed, for a change nobody
decided to make.

Not urgent: the design and the test do hold today, and Amendment 1 has not been
implemented yet. The cost is that the weakest link in a value-moving change is
prose.

## Evidence

Verified on `main` at `59014ea` (design revision on branch
`spec/fit-ingest-a1-design-revision`, not yet merged when this was written):

- `.kiro/specs/fit-ingest/requirements.md`, criterion 8.4 — full text quoted
  above; `grep -n "rolling" requirements.md` finds no mention of a start
  condition, partial windows, or complete windows anywhere in the document.
- `src/fitdocs/metrics/power.py:87-101` — `_trailing_rolling_mean`, whose
  docstring states the current behavior explicitly: "The window is partial
  (shorter) for the first `window - 1` points rather than dropping them."
- `src/fitdocs/metrics/power.py:123` — the call site,
  `_trailing_rolling_mean(resampled, _NP_ROLLING_WINDOW_S)`.
- `.kiro/specs/fit-ingest/design.md`, PowerSeriesMetrics — the new requirement in
  design form ("The rolling mean emits only complete windows"), with the ruling
  and the value-movement consequence.
- `.kiro/specs/fit-ingest/research.md`, Decision D7 — the alternatives weighed
  (record a `Departure` vs conform vs defer) and why conformance was chosen.
- `.kiro/queue/2026-07-27-np-rolling-window-starts-at-zero.md` — the item that
  found the divergence. It is about the *defect*; this item is about the absent
  criterion, and closing that one does not close this one.

## How to pick it up

1. Read Req 8.4 in `.kiro/specs/fit-ingest/requirements.md` and the
   PowerSeriesMetrics section of `design.md` — the design already states the
   behavior precisely enough to lift into a criterion.
2. Decide the form. Either extend 8.4 in place, or add a criterion under
   Requirement 8 stating that the rolling mean contributes only windows of the
   full cited width, and that a stream shorter than one full window reports
   `None`. Prefer extending 8.4 if the amendment record can carry the revision
   cleanly — it is the same behavior, more fully specified.
3. Note this reopens `approvals.requirements.approved`, which is currently
   `true`. That is the reason this was queued rather than folded into the design
   revision: flipping an approved requirements document is a maintainer decision,
   not a design-gate side effect.
4. Keep the criterion about the *start condition*, not the window width — the
   width is already covered by 8.4 and cited to `COGGAN_2003`. Two criteria for
   one number would be worse than none.

Done looks like: reverting `_trailing_rolling_mean` to partial windows fails a
criterion, not just a test.

## Resolution

Closed 2026-07-30. Note first: this item's own "Not urgent" and "Amendment 1
has not been implemented yet" (above) were true when written (`59014ea`,
pre-design) and are false now — Amendment 1 shipped complete at `68be52c`
(47/47 tasks, `main`). The criterion below governs shipped behavior, not
planned behavior.

Added criterion 8.9 to `.kiro/specs/fit-ingest/requirements.md` (a new
criterion under Requirement 8, not a renumbering — the item's own point 4
above, keep the width in 8.4 and the start condition separate, was followed):

> 9. _(added by Amendment 1, revision 2026-07-30)_ The rolling mean criterion
> 8.4 establishes shall contribute only windows spanning the full cited
> width: it shall not average over a shorter span at the start of the power
> stream, and a power-stream span insufficient to complete one such window
> shall report normalized power as `None`.

A `### Revision (2026-07-30)` subsection under `## Amendment 1` records why
and points back at this file. `tasks.md`'s 13.1 requirements tag now reads
`8.4, 8.9`; `design.md`'s traceability (component table, Service-Interface
annotations, PowerSeriesMetrics Detail table) now carries 8.9 as well, and
its criterion count is reconciled from 98 to 99 in `spec.json`'s `phase_note`.
This item's own point 3 said adding the criterion reopens
`approvals.requirements.approved` and that flipping it is a maintainer
decision, not a design-gate side effect — the maintainer's explicit
fast-track authorization for this narrow, evidence-only addition *is* that
decision, so the flag is left `true` deliberately rather than silently.
`spec.json`'s amendments array states this explicitly so the two documents
agree.
