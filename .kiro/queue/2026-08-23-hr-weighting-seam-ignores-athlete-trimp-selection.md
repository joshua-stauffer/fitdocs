---
id: 2026-08-23-hr-weighting-seam-ignores-athlete-trimp-selection
title: The heart-rate weighting seam ignores the athlete's TrimpWeighting selection
status: open
importance: high
importance_why: The load layer and the shipped metric report different training impulse for the same activity for any athlete carrying a selection; task 3.2 consumes the seam and has no way to thread one through.
effort: S
kind: inconsistency
area: load-channels, src/fitdocs/load/channels/weighting.py, src/fitdocs/metrics/__init__.py
created: 2026-08-23
surfaced_by: /kiro-impl load-channels task 2.1 adversarial review
pinned_at: e48ca61
resume_command: "/kiro-spec-design load-channels [queue: .kiro/queue/2026-08-23-hr-weighting-seam-ignores-athlete-trimp-selection.md] Rule whether HeartRateIntensityModel's Service Interface should accept a weighting selection"
context:
  - src/fitdocs/load/channels/weighting.py
  - src/fitdocs/metrics/__init__.py
  - src/fitdocs/metrics/sources.py
  - .kiro/specs/load-channels/design.md
  - .kiro/specs/load-channels/requirements.md
blocked_by: []
---

## What

`HeartRateIntensityModel`'s Service Interface, as specified in `design.md`
under `#### HeartRateIntensityModel`, defines `activity_impulse` and
`hourly_impulse_at` with no weighting-selection parameter. The shipped
implementer `BanisterTrimpModel` therefore calls
`metrics.sources.weighting_for(None)` unconditionally, resolving the
no-selection default pair.

The shipped metrics facade does not do this. `src/fitdocs/metrics/__init__.py:95`
reads `sources.weighting_for(athlete.trimp_weighting)`, honouring an
athlete-level `TrimpWeighting`. For any athlete carrying a selection, the load
layer's heart-rate channel and the document's own rendered training-impulse
value are computed from different coefficient pairs.

This is a design gap, not an implementation defect: closing it means widening
an approved Service Interface, which is not a task implementer's call.

## Why it matters

Requirement 5.6 requires the seam be "constructed so that a later change to
[the coefficients] changes the shipped metric and this channel's output
consistently". That property holds today only for athletes with no selection.
A re-sourcing of the female pair would move the shipped metric and leave the
seam unchanged — one without the other.

Task 3.2 (the heart-rate channel) consumes this seam and, as the Protocol
stands, has no way to pass a selection through it. The gap is cheapest to
settle before 3.2 is built on top of it.

## Evidence

Measured at `e48ca61` on identical inputs — 3600 s at 150 bpm, resting 40,
max 190, athlete `trimp_weighting = BANISTER_FEMALE`:

- shipped metric: `128.7707138467988`
- weighting seam: `115.11165050078277`

Independently reproduced twice: once by the task 2.1 implementer and once by
the reviewer during round-1 review, agreeing to all printed digits.

Mechanism: `src/fitdocs/metrics/__init__.py:95` passes
`athlete.trimp_weighting`; `src/fitdocs/load/channels/weighting.py` passes
`None`. The divergence is recorded in that module's docstring rather than
papered over — an earlier draft asserted the two could never diverge, and that
claim was removed as false during review.

## How to pick it up

1. Read `#### HeartRateIntensityModel` in `.kiro/specs/load-channels/design.md`
   (the Service Interface table) and the module docstring of
   `src/fitdocs/load/channels/weighting.py`, which states the limitation.
2. Read `src/fitdocs/metrics/__init__.py:95` and
   `src/fitdocs/metrics/sources.py`'s `weighting_for` to see what a selection
   is and where it comes from.
3. Decide the ruling below, then amend `design.md` (Service Interface and the
   component's Inbound list) and re-run `/kiro-impl load-channels 2.1`-adjacent
   work, or record the divergence as a deliberate DIVERGENCE with its reason.

Done looks like: either the Protocol accepts a selection and the seam agrees
with the shipped metric for every athlete, or the divergence is deliberate,
recorded in DIVERGENCES with its reason, and Req 5.6's consistency wording is
amended to match what the code actually guarantees.

## Open questions

- Should `HeartRateIntensityModel` accept a `WeightingPair`/`TrimpWeighting`,
  or should the *channel* resolve it and hand the seam a pair? The latter keeps
  the seam free of athlete concepts, which is why the interface was drawn this
  way in the first place.
- Is per-athlete weighting selection in scope for the load layer at all? If the
  answer is no, Req 5.6's "changes ... consistently" clause needs rewording,
  because it is currently false for any athlete with a selection.
