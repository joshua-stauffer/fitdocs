---
id: 2026-09-30-running-dynamics-design-m11-equivalent-mutant
title: running-dynamics design.md names an equivalent mutant as M11 and lacks gate-pair and identity mutations
status: open
importance: low
importance_why: Any future re-run of M1-M12 (the 6.1 sweep recipe) will see M11 survive and waste a round; the missing mutation classes may regress unnoticed in a redesign.
effort: S
kind: docs
area: running-dynamics, .kiro/specs/running-dynamics/design.md
created: 2026-09-30
surfaced_by: /kiro-impl running-dynamics
pinned_at: 8b07b9f
resume_command: "do: correct .kiro/specs/running-dynamics/design.md Testing Strategy M11 and add gate-pair-identity and recognition-identity mutations to its list"
context:
  - .kiro/specs/running-dynamics/design.md
  - .kiro/specs/running-dynamics/tasks.md
blocked_by: []
---

## What
design.md § Testing Strategy gives M11 as `math.ceil(k / 100 * n)`, claiming it yields 4 where the integer nearest-rank rule yields 3 on n=30, k=10. That is false, and the same wrong claim is in tasks.md 3.2. M1-M12 also have no mutation for swapped gate pairs (M6 only removes a gate) or for recognition that reads the developer index or declared scale.

## Why it matters
M11 as written can never red, so re-running the recipe reports a false gap. The two missing classes were real survivors during implementation. Tests now kill them, but a redesign reading only the design's list would not regrow those tests.

## Evidence
`python3 -c "import math; print(10/100*30, math.ceil(10/100*30), (10*30+99)//100)"` prints `3.0 3 3`. Over k in {10, 90} and n in 1..1999 the two forms never differ (checked this session). The tasks.md Implementation Notes (3.2, 6.1) record the replacement `(k*n)//100 + 1`, which reds `tests/render/test_dynamics.py::test_average_p10_p90_on_thirty_pairwise_distinct_values`.

## How to pick it up
1. In design.md § Testing Strategy, replace M11 with `(k*n)//100 + 1`.
2. Add M13 (swap two GATES targets; reds tests/ingest/test_dynamics.py::test_an_absent_gate_channel_gates_its_partner_only) and M14 (ignore channels with developer_data_index > 0 or declared_scale; reds test_a_channel_from_any_developer_index_or_application_fills).
3. Spec docs only; no code change.
