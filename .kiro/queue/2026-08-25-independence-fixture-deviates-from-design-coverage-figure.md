---
id: 2026-08-25-independence-fixture-deviates-from-design-coverage-figure
title: The channel-independence fixture uses 30% heart-rate coverage where design.md specifies 40%, deliberately but without a recorded reason
status: open
importance: low
importance_why: Behaviourally equivalent and the deviation is the better choice, but an unrecorded departure from an approved design invites a future session to "fix" it back into a near-tie.
effort: S
kind: docs
area: load-channels, tests/load/channels/test_insufficiency.py, .kiro/specs/load-channels/design.md
created: 2026-08-25
surfaced_by: /kiro-impl load-channels (task 5.2 review; verified by the parent session)
pinned_at: c6c1bb1
resume_command: "do: record why the channel-independence fixture uses 30% heart-rate coverage rather than design.md:1365's 40% -- either a one-clause comment in tests/load/channels/test_insufficiency.py or an amendment to design.md:1365"
context:
  - .kiro/specs/load-channels/design.md
  - tests/load/channels/test_insufficiency.py
blocked_by: []
---

## What

`design.md:1365` specifies the channel-independence fixture as *"one activity
with full power and **40%** heart-rate coverage"*. The shipped fixture
(`tests/load/channels/test_insufficiency.py:593`) uses `_partial(n, 30, 140.0)`
— **30%**.

The deviation is behaviourally inert: both figures sit below the 0.80 default
minimum and produce the same `STREAM_COVERAGE` insufficiency, so the test proves
exactly what the design asked it to.

It is also, on the evidence, the **better** choice — 0.40 sits one hundredth
away from the coverage fixture's 0.41, and near-ties are how this repo's
*tied values* anti-pattern gets in. But nothing in the tree says so.

## Why it matters

An unrecorded departure from an approved design reads as a mistake to the next
person who notices it. The likely repair is to "restore" 0.40 to match the
design — reintroducing the near-tie with 0.41 that the deviation exists to
avoid, and doing it with a commit message that says it is fixing a discrepancy.

The cost of recording it now is one clause. The cost of not recording it is a
silent regression that looks like housekeeping.

## Evidence

Verified by the parent session at `c6c1bb1`.

`design.md:1363-1366`:

> **Channel independence** — one activity with full power and 40% heart-rate
> coverage yields a computed power load and an HR insufficiency in the same
> pass, neither affecting the other.

`tests/load/channels/test_insufficiency.py:591-593`:

```python
    n = 100
    power_full = _partial(n, n, 220.0)
    hr_thin = _partial(n, 30, 140.0)  # fraction 0.30, below the 0.80 default
```

The comment records the *value* and why it is below the minimum, but not why it
departs from the design's figure.

The 0.41 near-tie it avoids is the `STREAM_COVERAGE` power fixture's observed
coverage, asserted in the same module.

## How to pick it up

1. Read `design.md:1363-1366` and `tests/load/channels/test_insufficiency.py:591-593`.
2. Pick one: extend the existing comment to say the design's 40% was moved to
   30% to avoid colliding with the 0.41 coverage fixture, **or** amend
   `design.md:1365` to 30% with the same reason. A design edit needs whatever
   re-approval the spec phase requires; the comment does not.
3. Do not change the fixture value itself.

**Done** looks like: the tree states why 30% rather than 40%, in one of the two
places a reader would look.

## Open questions

- Which artifact should hold the reason? The comment is cheaper and sits where
  a future editor will actually be standing; amending the design keeps the
  approved document accurate. Recording it in the test and leaving design.md
  alone is the lower-ceremony option and probably right for a fixture detail.
