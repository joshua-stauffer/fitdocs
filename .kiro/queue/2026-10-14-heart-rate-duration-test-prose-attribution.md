---
id: 2026-10-14-heart-rate-duration-test-prose-attribution
title: Correct the heart-rate structural test's attribution to its duration test
status: open
importance: low
importance_why: Coverage catches the fault, but the existing comment attributes it to a test that remains green.
effort: S
kind: docs
area: load-channels, tests/load/channels/test_heart_rate.py
created: 2026-10-14
surfaced_by: /kiro-impl hr-derivation task 1.3 independent review
pinned_at: 08821d5
resume_command: "do: correct the structural heart-rate test's docstring to distinguish its load-expression assertion from numeric duration dependence; reproduce the inline-intensity mutation and restored green tests"
context:
  - tests/load/channels/test_heart_rate.py
  - src/fitdocs/load/channels/heart_rate.py
  - .kiro/specs/load-channels/requirements.md
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

The unchanged docstring of `test_load_assigned_strictly_before_intensity_in_source`
at `tests/load/channels/test_heart_rate.py:335-340` says
`test_load_is_independent_of_scored_duration_while_intensity_is_not` rules out
computing intensity directly from the two impulses. That duration test remains
green for a mathematically equivalent inline expression. The structural test's
own assertion that the intensity expression reads `load` catches it.

## Why it matters

The explanation misstates what each test pins. Correct it to identify the
structural dependency and the numeric duration dependence separately. This
pre-existing prose belongs to load-channels; the dated-input task does not
change that behavior or those assertions.

## Evidence

The independent reviewer replaced intensity with
`math.sqrt((activity_impulse / reference) / (scored_duration_s / 3600))`,
ran both named tests through `uv run --no-sync pytest`, then restored source
bytes and observed green. Its captured trace shows:

```text
FAILED tests/load/channels/test_heart_rate.py::test_load_assigned_strictly_before_intensity_in_source
assert "load" in intensity_line
1 failed, 1 passed, 44 deselected in 0.07s
```

The controller inspected the captured trace, rather than rerunning that
mutation itself. The unchanged misleading paragraph exists at `08821d5`.
Restored relevant regression: 1,605 passed; fresh controller verification of
the task's provenance cases: six passed. No duplicate was found among the
open queue items or roadmap entries.

## How to pick it up

1. Read both named tests and the channel's load and intensity expressions.
2. Correct only the structural test's docstring: it enforces reading `load`;
   the duration test pins the independent numeric dependence of the two results.
3. Apply the inline-expression mutation, run both tests through `uv run pytest`,
   restore from a copied source and confirm green. Done means the prose matches
   the observed failing and passing tests without changing their assertions.
