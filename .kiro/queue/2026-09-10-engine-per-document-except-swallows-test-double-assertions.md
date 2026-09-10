---
id: 2026-09-10-engine-per-document-except-swallows-test-double-assertions
title: apply_load's per-document `except Exception` turns a test double's AssertionError into a report failure, so an engine test that never asserts `report.failures == ()` can pass while its own double raised
status: open
importance: medium
importance_why: Every `apply_load` test that drives a scripted session is one missing `failures == ()` assertion away from a false green; a queue-exhausted double is exactly the signal a wrongly-issued prompt produces, and the engine hides it in a tuple most tests never read.
effort: S
kind: gap
area: training-load, src/fitdocs/load/engine.py, tests/load/test_engine.py, tests/load/test_arbitration_e2e.py, tests/load/test_feature_e2e.py
created: 2026-09-10
surfaced_by: /kiro-impl training-load (Amendment 4, task 7.3 review; confirmed by the 7.4 e2e author)
pinned_at: 52c473e
resume_command: "do: add a suite-wide convention (a shared helper or a conftest assertion) that every apply_load call in tests asserts report.failures == () unless the test is about a failure; audit tests/load/*e2e*.py and tests/load/test_engine.py for calls without it; consider re-raising AssertionError from the per-document isolation in engine.py so a test double's failure can never be filed as a document failure"
context:
  - src/fitdocs/load/engine.py
  - tests/load/test_engine.py
  - tests/load/test_prompt_date_e2e.py
  - .kiro/specs/training-load/tasks.md
blocked_by: []
---

## What

`src/fitdocs/load/engine.py:304` isolates every per-document exception into
`report.failures` (`except Exception as exc:  # noqa: BLE001`). That is the
right contract for a production pass (Req 8.5), but the same clause catches
an `AssertionError` raised by a **test double** — a `ScriptedSession` whose
answer queue ran out because the flow asked a question the test did not
expect — and files it as a document failure. A test that then asserts only
the positive outcome it was written for can stay green.

## Why it matters

The 7.3 reviewer demonstrated it: mutating the retroactive question's
comparison from `activity_date < on` to `>` made the injected-`today` engine
probe red only through its `entry is not None` assertion; the
`AssertionError: no more confirm answers queued` the double raised never
surfaced, because `test_apply_load_stamps_an_accepted_benchmark_with_the_injected_today`
did not read `report.failures`. Every `apply_load` test that drives prompts
carries the same exposure, and the shape recurs whenever a new question is
added to the flow. The 7.4 e2e module only avoids it because every scenario
asserts `report.failures == ()` first — a convention, not a mechanism.

## Evidence

- `src/fitdocs/load/engine.py:304` — the isolation clause.
- 7.3 review (2026-09-10, Opus reviewer, training-load task 7.3): "mutating
  `activity_date < on` to `>` reds `test_apply_load_stamps_an_accepted_benchmark_with_the_injected_today`
  only via its `entry is not None` assertion, never surfacing the
  ScriptedSession's `AssertionError: no more confirm answers queued`".
- 7.4 e2e (`tests/load/test_prompt_date_e2e.py`): mutation "force
  `already_have_it = False`" reds scenario 3 **only** through
  `report.failures == ()` — the double's exhausted queue is visible nowhere
  else.
- Related but distinct: `2026-07-26-prompt-answer-rejected-by-store-becomes-failure`
  (a *store* rejection surfacing as a document failure).

## How to pick it up

1. `grep -n "apply_load(" tests/load/*.py` and list the calls whose test
   never asserts on `report.failures`.
2. Decide the mechanism: (a) a shared `assert_clean(report)` helper adopted
   by every non-failure test, or (b) `engine.py` re-raising `AssertionError`
   (never a production exception type) out of the per-document isolation, so
   a double's failure propagates. (b) changes production behaviour only for a
   class no production code raises; check `tests/load/test_engine.py`'s
   per-document-isolation tests before choosing.
3. Done: a mutation that makes the flow ask one extra question reds every
   prompt-driving engine test, not only the ones that happen to assert the
   failures tuple.
