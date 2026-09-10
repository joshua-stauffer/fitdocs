---
id: 2026-09-10-activity-qa-flags-staleness-guard-neutralises-retroactive-anchors
title: activity-qa-flags' staleness design guards `measured_on <= activity_date` before calling benchmark_age and reports a violation as not-assessed, so every athlete-declared retroactive anchor would surface as not-assessed instead of current — and its stated rationale is now false
status: open
importance: high
importance_why: Amendment 4's primary case (a first-time athlete's archive scored against a prompt answer applied retroactively) produces exactly the anchors this guard rejects; implemented as designed, the staleness flag on every such document would be wrong, and the design forbids removing the guard on a premise athlete-benchmarks Amendment 1 revised.
effort: S
kind: cross-spec-conflict
area: activity-qa-flags, athlete-benchmarks, src/fitdocs/benchmarks.py
created: 2026-09-10
surfaced_by: /kiro-validate-impl training-load (Amendment 4, design + boundary dimension)
pinned_at: 52c473e
resume_command: "/kiro-spec-design activity-qa-flags [queue: .kiro/queue/2026-09-10-activity-qa-flags-staleness-guard-neutralises-retroactive-anchors.md] Amend the StalenessSurfacing component for athlete-benchmarks Amendment 1: a negative benchmark_age is a declared retroactive entry, not a guard violation"
context:
  - .kiro/specs/activity-qa-flags/design.md
  - .kiro/specs/activity-qa-flags/research.md
  - .kiro/specs/activity-qa-flags/tasks.md
  - .kiro/specs/athlete-benchmarks/requirements.md
  - .kiro/specs/athlete-benchmarks/design.md
  - src/fitdocs/benchmarks.py
blocked_by: []
---

## What

athlete-benchmarks Amendment 1 (2026-09-10, landed with training-load
Amendment 4) revised criterion 4.6: `benchmark_age` no longer raises for a
measurement after the activity; it returns a negative `age_days` and a
current verdict, because the store can now return an entry the athlete
declared (`applies_from`) to stand in for earlier activities. Its
`cross_spec` note says activity-qa-flags "must read a negative age as
'measured after this activity, applied by declaration', not as stale".

activity-qa-flags (phase `tasks-generated`, spec.json `updated_at`
2026-07-25, nothing dated 2026-09-10 in any of its files) still designs its
`StalenessSurfacing` component around the old rule: it guards
`measured_on <= activity_date` **before** calling `benchmark_age`, converts a
violation into *not-assessed*, and justifies never removing that guard with
"athlete-benchmarks specifies `benchmark_age` as *raising* on a benchmark
measured after the activity". The selection-semantics revalidation trigger
in athlete-benchmarks' design fired; threshold-load was re-checked
(Amendment 2), activity-qa-flags was not.

## Why it matters

The anchors this feature exists to create — a prompt answer measured today
and declared to apply back to a 2019 activity — are precisely the ones the
guard rejects. Implemented as designed, every such document reports
staleness as *not-assessed*, the athlete never sees "measured N days after
this activity, applied by your declaration", and the design text tells the
implementer the guard is load-bearing. The premise is false in shipped code:
`benchmark_age` has no ordering guard left.

## Evidence

- `src/fitdocs/benchmarks.py` `benchmark_age` (after 0804c93): only
  `window_days < 1` raises; `age_days = (activity_date - measured_on).days`
  may be negative; `is_stale = age_days > window_days`.
- `.kiro/specs/athlete-benchmarks/requirements.md` 4.6 "(revised by Amendment
  1)" and the Amendment 1 `cross_spec` entry in
  `.kiro/specs/athlete-benchmarks/spec.json` naming activity-qa-flags.
- `.kiro/specs/activity-qa-flags/design.md` — StalenessSurfacing: the
  pre-call guard and its rationale (reported by the design-validation
  reviewer at lines ~1120-1132 and ~1181 as of 52c473e); the same premise in
  `research.md` (~338-345) and `tasks.md` (~347-348). The reviewer's line
  numbers were not independently re-read by the parent; the `grep -n
  'raising\|raises'` over that design.md at 52c473e is the check to repeat.
- `.kiro/specs/activity-qa-flags/spec.json` `updated_at: 2026-07-25`.

## How to pick it up

1. Read athlete-benchmarks Amendment 1 (requirements.md) and the revised
   `StalenessCalculation` component (design.md), then activity-qa-flags'
   `StalenessSurfacing` component, research.md's staleness section and the
   task that implements the guard.
2. Amend the component: no pre-call ordering guard; a negative `age_days`
   is surfaced as its own honest state (measured after the activity, applied
   by the athlete's declaration, with both dates), never as stale and never
   as not-assessed; the removal-forbidden note is retired with its premise.
   Read `Benchmark.applies_from` off the resolved anchor to say so.
3. Done: the spec's requirements/design/tasks agree with athlete-benchmarks
   4.6 as revised, and the design's revalidation-trigger obligation is
   recorded as discharged in athlete-benchmarks' amendment record.

## Open questions

- Should the retroactive case be a fourth verdict of the existing staleness
  flag, or a separate flag? athlete-benchmarks only promises the sign of the
  age; the surfacing vocabulary is activity-qa-flags' to choose.
