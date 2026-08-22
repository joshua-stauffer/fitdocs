---
id: 2026-07-30-trimpresult-frozenness-unpinned
title: TrimpResult's frozen-ness is pinned by nothing, unlike all three of its sibling record types
status: open
importance: medium
importance_why: Removing `frozen=True` leaves the full suite green, and every neighbouring frozen type in the same layer has an explicit is-frozen test — so this is an inconsistency in an established pattern rather than a deliberate omission, and immutability is a property this codebase treats as load-bearing.
effort: S
kind: gap
area: fit-ingest, src/fitdocs/metrics/stress.py, tests/metrics/test_stress.py
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 13.4 review — found by mutation)
pinned_at: 224de66
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-trimpresult-frozenness-unpinned.md] Add the missing is-frozen test for TrimpResult, matching its three sibling record types"
context:
  - src/fitdocs/metrics/stress.py
  - tests/metrics/test_stress.py
  - tests/metrics/test_types.py
blocked_by: []
---

## What

`TrimpResult` in `src/fitdocs/metrics/stress.py` is declared
`@dataclass(frozen=True)`, and it genuinely is frozen at runtime — assigning to
`.value` raises `FrozenInstanceError`.

Nothing tests it. Removing `frozen=True` leaves the full suite green.

Its three sibling record types in the same layer each have an explicit
is-frozen test in `tests/metrics/test_types.py` (`ZoneSpec`, `AthleteInputs`,
`DerivedMetrics`). `TrimpResult` — introduced later, by task 11 — is the odd
one out.

## Why it matters

Medium rather than low for two reasons.

**It is an inconsistency in an established pattern, not a considered
omission.** Three neighbours have the test; this one was simply missed when the
type was added. That is the kind of gap that stays open indefinitely because
nobody notices a *missing* test, and it quietly weakens a convention the layer
otherwise applies uniformly.

**Immutability is load-bearing here.** `TrimpResult` carries a computed metric
value and the weighting pair that produced it, and Req 17.6 requires the two
travel together so two athletes' training-impulse numbers are never compared
without that distinction visible. A mutable result is a value that can be
separated from its own provenance after the fact — precisely what the pairing
exists to prevent.

The property holds today. This is about it continuing to hold.

## Evidence

Found by mutation during the task 13.4 review, at `ffea172` (now `224de66`):

```
# src/fitdocs/metrics/stress.py — @dataclass(frozen=True) -> @dataclass
uv run pytest  ->  2254 passed
```

Unchanged from the baseline. Confirmed the property does hold at HEAD:
constructing `TrimpResult(value=1.0, weighting=None)` and assigning to `.value`
raises `dataclasses.FrozenInstanceError: cannot assign to field 'value'`.

Sibling tests that this one lacks: `tests/metrics/test_types.py:80`, `:138`,
`:243`. A grep for `frozen` in `tests/metrics/test_stress.py` returns nothing.

## How to pick it up

1. Read one of the three sibling is-frozen tests in
   `tests/metrics/test_types.py` and match its idiom exactly — this is a
   consistency fix, not a place to invent a new shape.
2. Add the equivalent for `TrimpResult`. It lives in
   `src/fitdocs/metrics/stress.py` rather than `types.py`, so decide whether
   the test belongs in `tests/metrics/test_stress.py` (co-located with the
   type) or alongside its siblings in `tests/metrics/test_types.py`; prefer
   wherever a reader would look first.
3. Verify by mutation, per `.kiro/steering/change-protocol.md` § Fixture
   Discrimination: removing `frozen=True` must red your new test, and reverting
   must restore green. Run it through `uv run pytest`, never `uv run python -c`.
4. While there, check whether any *other* record type added since task 8 is
   missing the same test — `grep -n "frozen=True" src/fitdocs/**/*.py` against
   the is-frozen tests that exist. If `TrimpResult` was missed, a sibling may
   have been too.

Done looks like: removing `frozen=True` from `TrimpResult` reds a named test.
