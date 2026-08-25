---
id: 2026-08-25-heart-rate-inputs-used-values-unpinned
title: The heart-rate channel's inputs_used impulse and reference values are unpinned — swapping them leaves the whole suite green
status: open
importance: medium
importance_why: Req 1.3 requires inputs_used to name the values that produced the result; the two values it exists to report can be swapped with 2684 tests still passing, and a docstring beside them claims the opposite.
effort: S
kind: gap
area: load-channels, src/fitdocs/load/channels/heart_rate.py, tests/load/channels/test_heart_rate.py
created: 2026-08-25
surfaced_by: /kiro-impl load-channels (task 5.1 review round 3, reviewer mutation M4; reproduced by the parent session)
pinned_at: 7f5b7c9
resume_command: "/kiro-impl load-channels [queue: .kiro/queue/2026-08-25-heart-rate-inputs-used-values-unpinned.md] Pin the heart-rate channel's inputs_used impulse and reference VALUES, not just their key presence"
context:
  - src/fitdocs/load/channels/heart_rate.py
  - tests/load/channels/test_heart_rate.py
  - .kiro/specs/load-channels/requirements.md
blocked_by: []
---

## What

`src/fitdocs/load/channels/heart_rate.py:261-262` reports the two numbers that
produce the heart-rate load:

```python
("impulse",   f"{activity_impulse:g}"),
("reference", f"{reference:g}"),
```

`tests/load/channels/test_heart_rate.py:1052-1053` asserts only that the **keys
exist**:

```python
assert "impulse" in inputs
assert "reference" in inputs
```

Every sibling key in the same assertion block pins a **value** (`inputs["lthr_bpm"]
== "165"`, `inputs["resting_hr_bpm"] == "48"`, `inputs["max_hr_bpm"] == "190"`,
`inputs["lthr_measured_on"] == measured.isoformat()`). The two values the field
exists to carry are the two nothing checks.

This is the repo's named **ever-present token** anti-pattern: asserting the mere
presence of something emitted on every run.

## Why it matters

Req 1.3 requires `inputs_used` to name the values that produced the result — it
is what lets a caller report what a number anchored to. A reader of a generated
document sees `impulse` and `reference`; if they are transposed, every heart-rate
document reports two numbers under the wrong labels and **nothing in the suite
objects**.

Worse, the code carries a comment asserting the property that is not pinned.
`heart_rate.py:263-264`:

> `# Req 1.3: the values reported here are the ones the computation` …

That is exactly this spec's most-repeated defect species — prose claiming a
guarantee no assertion enforces, which tells the next editor the coverage exists.

Task 5.1 is unaffected: its claim is that the raw impulse *moves* under a
coefficient rescale, which stays true even under the swap (both values scale by
the same factor). So this is task 3.2 / Req 1.3 ground, not 5.1's, and it was
handed off rather than charged to that task.

## Evidence

Measured at `7f5b7c9`. Production mutation — the two values **fully swapped**:

```python
("impulse",   f"{reference:g}"),
("reference", f"{activity_impulse:g}"),
```

```
$ uv run pytest -q
2684 passed, 5 skipped in 24.38s
```

Reverted, and `git diff --stat HEAD -- src/` confirmed empty afterwards.

Originally reviewer mutation M4 on the task 5.1 round-3 review; the parent
session reproduced it independently before filing, and read
`test_heart_rate.py:1048-1058` to confirm the presence-only assertions.

Note a full swap is the *weakest* possible mutation here — it changes both
values and still passes, so any narrower single-value error passes too.

## How to pick it up

1. Read `tests/load/channels/test_heart_rate.py:1048-1058`. The fix is to assert
   the two values the way the four sibling keys already do.
2. Compute the expected `impulse` and `reference` independently of
   `heart_rate.compute` — do not build them by calling the function under test
   (see `.kiro/queue/2026-08-25-test-power-worked-examples-build-expected-from-function-under-test.md`
   for the same pattern; `tests/load/channels/test_worked_examples.py` shows the
   stronger convention).
3. **Use pairwise-distinct values.** If the fixture makes `impulse` and
   `reference` numerically close or equal, the swap stays green and the new
   assertion pins nothing — this repo's *tied values* anti-pattern.
4. Verify by re-running the swap mutation above and confirming it now reds.
   Run it through `uv run pytest`, not a bare interpreter.
5. Re-read the `# Req 1.3` comment at `heart_rate.py:263-264` and either make it
   true or delete it.

**Done** looks like: swapping the two values reds a named test, the expected
values are derived independently, and no comment claims a guarantee the suite
does not enforce.

## Open questions

None. The gap is measured and the fix is mechanical.
