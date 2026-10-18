---
id: 2026-09-12-sufficiency-zero-samples-and-fabricated-observed
title: sufficiency.evaluate treats present zero as covered and fabricates observed=0.0 for unmeasurable spans
status: done
importance: low
importance_why: A zero-HR activity scores a zero impulse rather than declining, and an unmeasurable span reports a fabricated 0.0 instead of an absent value, contrary to tech.md's absent-data rule.
effort: S
kind: bug
area: load-channels, src/fitdocs/load/channels/sufficiency.py
created: 2026-09-12
surfaced_by: /kiro-impl performance-benchmarks (adversarial reviews, 2026-09-11/12)
pinned_at: d4fbc6f
resume_command: "do: fix sufficiency.evaluate's zero-sample coverage check and its observed=0.0 fabrication at sufficiency.py:118"
context:
  - src/fitdocs/load/channels/sufficiency.py
blocked_by: []
---

## What

`sufficiency.evaluate` treats a present `0` sample as covered, so a
zero-HR activity scores a zero impulse in the load pass rather than
declining. Separately, `observed = 0.0 if coverage is None`
(`sufficiency.py:118`) fabricates an observed value for an unmeasurable
span. performance-benchmarks routes around this in its own leaves, but the
load pass still reports the fabricated value.

## Why it matters

tech.md's data-root contract states absent data is `None`, never a
fabricated `0` or default. `observed = 0.0` for an unmeasurable span is
exactly that fabrication, and it currently ships in the load pass's output.

## Evidence

- (3.2 reviewer) "sufficiency.evaluate treats a present 0 sample as
  covered; a zero-HR activity scores a zero impulse in the load pass rather
  than declining. load-channels owner."
- (3.2 r3 reviewer) "sufficiency.evaluate fabricates observed=0.0 for an
  unmeasurable span (sufficiency.py:118 `observed = 0.0 if coverage is
  None`), contrary to tech.md's absent-data rule; the load pass still
  reports it. load-channels."

## How to pick it up

1. Read `sufficiency.evaluate` in `src/fitdocs/load/channels/sufficiency.py`,
   including the `observed = 0.0 if coverage is None` line at ~118.
2. Change the zero-sample check to distinguish "present zero" from
   "absent" so a zero-HR activity declines rather than scoring zero
   impulse.
3. Replace the `observed = 0.0` fabrication with `None` (or the module's
   established absent-value convention) for an unmeasurable span, and
   confirm the load pass's consumers handle that `None` correctly.
</content>

## Resolution (2026-10-18)

Fabricated-observed half fixed on main at aaf0a1a (chore/q-sufficiency; full suite 26760 passed,
branch CI green, independent Opus review APPROVED): a TOO_SHORT decline for a stream with no
measurable recorded span now carries observed=None and the detail "<stream> has no measurable
recorded span; the minimum duration is Ns" instead of a fabricated 0.0 / "span 0s". Test:
tests/load/channels/test_sufficiency.py::test_no_measurable_span_reports_too_short_with_no_observed_span.

The "present zero counts as covered" half is NOT a defect against the spec: load-channels Req 2.10
(requirements.md:159) says a recorded zero is recorded data, and
test_recorded_zero_counts_as_covered_distinctly_from_none pins it; step 2 of "How to pick it up"
contradicts that requirement. Whether heart rate 0 should instead count as a dropout is a maintainer
decision, moved to .kiro/queue/2026-10-18-heart-rate-zero-as-dropout-decision.md.
