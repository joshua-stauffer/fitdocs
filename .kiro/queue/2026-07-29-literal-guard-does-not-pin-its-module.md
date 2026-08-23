---
id: 2026-07-29-literal-guard-does-not-pin-its-module
title: The "no bare constant literal" AST guard passes when pointed at a different module
status: open
importance: low
importance_why: The guard's positive control proves it scanned something, not that it scanned the right thing; task 12.1's ConstantGuard supersedes it, so this is cheap hardening rather than a live hole.
effort: S
kind: gap
area: fit-ingest, tests/metrics/test_aggregates.py
created: 2026-07-29
surfaced_by: /kiro-impl fit-ingest (task 10.1, review rounds 2-3)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-29-literal-guard-does-not-pin-its-module.md] Assert the literal-scan guard scans the module it names, and fold the check into task 12.1's ConstantGuard if that has landed"
context:
  - tests/metrics/test_aggregates.py
  - .kiro/specs/fit-ingest/tasks.md
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

`test_module_source_has_no_bare_threshold_or_window_literal` in
`tests/metrics/test_aggregates.py` walks the AST of `aggregates.py` and asserts
neither `0.5` nor `10` appears as a numeric constant. It guards against the
scan being vacuous with `assert len(constants) > 5`.

That control proves the walk found *something*. It does not prove it found the
right module: redirecting the walk at `fitdocs.metrics.stress` leaves the test
passing, because that module also has more than five numeric constants and none
of them is `0.5` or `10`.

## Why it matters

Low, and deliberately filed as such. The guard is correct today and the
redirection is not a mutation anyone would make by accident. It matters only as
the shape: this is the "vacuous walk" anti-pattern one step removed — the walk
is non-empty, but its subject is unpinned, so the assertion could be satisfied
by scanning the wrong thing.

Task 12.1 ships a `ConstantGuard` that scans the numeric-literal surface of the
metric modules as a whole and supersedes this per-module test. The cheapest
outcome is that 12.1 absorbs it; this item exists so that decision is made
rather than defaulted into.

## Evidence

At `4449d3e`, mutating the guard to walk `stress` instead of `aggregates`:

```
uv run pytest tests/metrics/test_aggregates.py -k has_no_bare  →  1 passed
```

Confirmed independently in review rounds 2 and 3 of task 10.1, both times as a
declared residual rather than a rejection ground.

**Update, 2026-07-30 (task 12.2, branch `impl/fit-ingest`, not yet merged).**
This class recurred inside task 12.2's own new ConstantGuard and was caught
there, which both confirms the shape is live and supplies the fix. The Req
15.5 walk in `tests/metrics/test_constant_guard.py` shipped with the same
kind of control this item describes — `assert len(python_files) >= 6,
"the walk is looking at the wrong directory"` — and a reviewer defeated it by
re-pointing the walk **one** directory up, from `src/fitdocs/metrics/` to
`src/fitdocs/`. That directory holds 19 `.py` files, so the `>= 6` threshold
passed, and because the glob is non-recursive the metrics package was not
scanned at all. With the forbidden string planted in two scanned modules the
suite still reported `4 passed`.

Two transferable points this item did not previously carry:

- **A count threshold is not a positive control.** It proves the walk found
  something; naming the subject is what proves it found the right thing. The
  original mutation run against this class (re-pointing far away, to a
  directory with too few files) reds for the wrong reason and so proves
  nothing about the near miss, which is the regression that actually happens.
- **The accepted fix is two assertions, not one.** 12.2 now asserts both
  `package_dir.name == "metrics"` and that the seven known metrics filenames
  are a subset of those found. The reviewer verified both are load-bearing:
  re-pointing one directory up reds on the name check, while re-pointing at
  `tests/metrics/` — a real sibling directory *also* named `metrics` — reds
  only via the filename subset assertion.

## How to pick it up

1. Task 12.1 has landed and task 12.2 ships a `ConstantGuard` whose literal
   scan covers `aggregates.py` in full (`tests/metrics/test_constant_guard.py`,
   on `impl/fit-ingest`). Confirm that on current `main`, then delete
   `test_module_source_has_no_bare_threshold_or_window_literal` from
   `tests/metrics/test_aggregates.py` rather than hardening it — the narrower
   test is now redundant, and a redundant guard with a weak positive control
   is worse than none.
2. If for any reason the narrower test is kept, do not add
   `assert len(constants) > 5`-style hardening. Copy 12.2's pair: assert the
   resolved module/package **by name**, and assert the expected members are
   present.
3. Verify by mutation, and pick the *near* miss: redirect the walk one level
   up or at a same-named sibling, not at something far away. Run it through
   `uv run pytest` (`.kiro/steering/change-protocol.md` § Fixture
   Discrimination — a bare `uv run python -c` reads stale bytecode).

Done looks like: no walking guard in the metrics test tree can be re-pointed
at a neighbouring directory and stay green.
