---
id: 2026-08-25-test-power-worked-examples-build-expected-from-function-under-test
title: test_power.py's two worked examples build their expected value by calling the function under test, so only a ±0.7% anchor keeps them non-vacuous
status: open
importance: low
importance_why: A self-referential compare that survives any error under ~0.7%; harmless today because a published-value anchor sits beside it, but the pattern is one this repo has been burned by.
effort: S
kind: gap
area: load-channels, tests/load/channels/test_power.py
created: 2026-08-25
surfaced_by: /kiro-impl load-channels (task 5.1 review; verified independently by the parent session)
pinned_at: bf10391
resume_command: "do: replace the self-referential expected values in tests/load/channels/test_power.py's test_worked_example_7080s_np183_ftp215 and test_worked_example_5400s_np220_ftp250 with expectations computed inline from Coggan's formula, following the pattern tests/load/channels/test_worked_examples.py already uses"
context:
  - tests/load/channels/test_power.py
  - tests/load/channels/test_worked_examples.py
  - src/fitdocs/metrics/stress.py
  - .kiro/specs/load-channels/tasks.md
blocked_by: []
---

## What

`tests/load/channels/test_power.py`'s two worked-example tests (task 3.1's)
compute the value they assert by calling the very function they are verifying:

```python
expected = power_tss(183.0, 7080.0, 215.0)
assert expected == pytest.approx(142, abs=1)
...
assert result.load == pytest.approx(expected)
```

The final assertion is `power_tss(...) == power_tss(...)` — this repo's named
**self-referential compare** anti-pattern. It cannot detect any error in
`power_tss` itself, because both sides move together.

What actually keeps the tests honest is the middle line: the
`pytest.approx(142, abs=1)` anchor against the published result. That bounds
the error to roughly ±0.7% — so a wrong `power_tss` that lands within
141–143 passes both tests.

The docstring is candid about it (*"expected derived from the shipped power_tss
formula itself, not hardcoded"*), so this is a known shape rather than a hidden
one — which is why it is `low` and not higher.

## Why it matters

Task 5.1 shipped `tests/load/channels/test_worked_examples.py`, whose five
worked examples each compute their expectation **inline from the published
formula literals** and never call the function under test. The task 5.1
reviewer noted this is strictly stronger than the `test_power.py` pattern.

So the repo now holds two worked-example modules for the same channel using
opposite conventions, one of which is measurably weaker. The risk is not that
today's number is wrong — it is that the weaker pattern is the one a future
task copies, and the ±0.7% window is wide enough to hide a real coefficient
or window defect.

## Evidence

`tests/load/channels/test_power.py:199-226`, both tests. Lines 204 and 222 are
the self-referential expectations; lines 206 and 224 are the anchors that
carry them.

The stronger convention to copy is in
`tests/load/channels/test_worked_examples.py` (task 5.1, staged at `bf10391`),
where each expectation is built from literals — e.g. `210.0/280.0` for the
intensity factor and `duration*np*IF/(ftp*3600)*100` for TSS — with the
published figure asserted separately.

Reported as `FOLLOW_UPS` 3 by the task 5.1 reviewer subagent; the parent
session read `test_power.py:199-226` and confirmed both instances before
filing.

## How to pick it up

1. Open `tests/load/channels/test_power.py:199-226` and
   `tests/load/channels/test_worked_examples.py` side by side. The second file
   is the pattern to copy.
2. Replace each `expected = power_tss(...)` with the value computed inline from
   Coggan's formula using the same literals, keeping the published-result
   anchor alongside it.
3. Verify the change discriminates: perturb `power_tss`'s result by a factor
   inside the old ±0.7% window (e.g. ×1.003) and confirm both tests now red
   where previously they passed. Run it through `uv run pytest` — a bare
   interpreter reads stale bytecode.

**Done** looks like: neither test builds its expectation from the function it
verifies, and a sub-0.7% error in `power_tss` reds them.

## Open questions

None. The fix is mechanical and the pattern to follow already exists in the
tree.
