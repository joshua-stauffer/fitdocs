---
id: 2026-09-30-stress-reload-breaks-power-tss-identity
title: tests/metrics/test_stress.py reloads the stress module and breaks test_power's identity check when metrics runs first
status: open
importance: medium
importance_why: The suite is green only because tests/load sorts before tests/metrics; any reordering or subset run reds it.
effort: S
kind: bug
area: training-load, tests/metrics/test_stress.py, tests/load/channels/test_power.py
created: 2026-09-30
surfaced_by: /kiro-impl running-dynamics
pinned_at: 8b07b9f
resume_command: "do: make tests/metrics/test_stress.py stop leaking an importlib.reload of fitdocs.metrics.stress into later tests"
context:
  - tests/metrics/test_stress.py
  - tests/load/channels/test_power.py
  - src/fitdocs/metrics/stress.py
blocked_by: []
---

## What
`tests/metrics/test_stress.py` calls `importlib.reload(stress)` (lines 518 and 525), which rebinds `fitdocs.metrics.stress.power_tss` to a new function object. `fitdocs.load.channels.power` still holds the old object, so `tests/load/channels/test_power.py::test_power_tss_name_is_the_real_shipped_object_by_identity` (identity assert at line 287) fails whenever it runs after the reload.

## Why it matters
A green full suite depends on directory order. Any subset run, a future directory rename, or test randomization reds it for a reason unrelated to the change under test. That is the failure 2026-07-29-no-test-order-randomization predicts.

## Evidence
At 8b07b9f:

```
$ uv run pytest -q -p no:randomly tests/metrics/test_stress.py tests/load/channels/test_power.py
FAILED tests/load/channels/test_power.py::test_power_tss_name_is_the_real_shipped_object_by_identity
1 failed, 63 passed
```

The full `uv run pytest -q` passes (5890).

## How to pick it up
1. Read tests/metrics/test_stress.py:505-530 to see why it reloads (probably an import-purity or env check).
2. Replace the reload with a subprocess probe (the pattern tests/test_preserved_guarantees.py uses), or restore the original module object in a fixture finalizer. `sys.modules['fitdocs.metrics.stress'] = original` alone is not enough, because `from … import` bindings already hold the old function.
3. Done when the two-file command above passes, and the whole suite also passes in reversed directory order.
