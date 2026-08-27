---
id: 2026-08-27-req-7-9-behavioural-half-unpinned
title: Req 7.9's behavioural half has no carrier anywhere — nothing drives a futile configured order through compute
status: open
importance: low
importance_why: Hand-traced as correct, so a missing pin rather than a defect — but the requirement's second clause is unproven end to end.
effort: S
kind: test-gap
area: threshold-load, tests/load/threshold/
created: 2026-08-27
surfaced_by: /kiro-validate-impl threshold-load
pinned_at: 3e14ab9
resume_command: "/kiro-impl threshold-load [queue: .kiro/queue/2026-08-27-req-7-9-behavioural-half-unpinned.md] Pin the futile-order behaviour end to end"
context:
  - .kiro/specs/threshold-load/requirements.md
  - tests/load/test_settings.py
  - tests/load/threshold/test_feature_e2e.py
blocked_by: []
---

## What

Req 7.9 has two clauses: a valid-but-futile order (e.g. `ride = ["pace"]`) is
**accepted** by the reader, and the resulting activities **report that
channel's reason as an ordinary insufficiency**. Only the first is pinned, by
`tests/load/test_settings.py:838`
(`test_futile_configured_order_is_accepted_not_an_error`). Nothing anywhere
configures a futile order and drives an activity through `compute` to assert
the second.

## Why it matters

Hand-traced by the coverage validator: it returns `NotComputed` carrying
pace's `NOT_DEFINED_FOR_MODALITY` detail and does not crash — so this is a
missing pin, not a defect. But the clause that describes what the athlete
actually sees is unproven.

## Evidence

`3e14ab9`. Task 5.3's own review declared 7.9 UNPINNED-here with the reader-half
carrier named; the behavioural half has no carrier in any spec.

## How to pick it up

Add a case to `tests/load/threshold/test_feature_e2e.py` (which already builds
real data roots with real settings files): a Ride configured
`[load.priority] ride = ["pace"]`, asserting the outcome is `NotComputed` and
its reason carries pace's own model-not-defined detail rather than a
configuration error. Verify by mutating the reader to reject futile orders and
observing red.
