---
id: 2026-07-29-citedconstant-departure-field-is-dead-surface
title: CitedConstant.departure is never assigned and no Departure is linkable to the constant it governs
status: open
importance: medium
importance_why: Req 16.5 wants the departure recorded alongside the citation; a consumer reading CONSTANT_SOURCES cannot find the departure that applies to a value, so the two records are adjacent in a file rather than linked.
effort: S
kind: gap
area: fit-ingest, src/fitdocs/citation.py, src/fitdocs/metrics/sources.py
created: 2026-07-29
surfaced_by: /kiro-impl fit-ingest (task 9.4 review round 1)
pinned_at: bf588a5
resume_command: "/kiro-impl fit-ingest 12.1 [queue: .kiro/queue/2026-07-29-citedconstant-departure-field-is-dead-surface.md] Link each Departure to the constant it governs, or record why the field stays unused"
context:
  - src/fitdocs/citation.py
  - src/fitdocs/metrics/sources.py
  - .kiro/specs/fit-ingest/design.md
  - .kiro/specs/fit-ingest/requirements.md
blocked_by: []
---

## What

`CitedConstant` carries a `departure: Departure | None = None` field. Nothing
in `src/` ever assigns it — `grep -rn "departure=" src/` returns no matches.
Task 9.4 landed `DEPARTURES` as a standalone module-level tuple instead, and
`Departure.subject` is free text (`trimp-weighting-sex-neutral-default`), not a
constant name that can be resolved back to an entry in `CONSTANT_SOURCES`.

So the two halves of Req 16.5 are both present but unlinked: a reader holding
`BANISTER_MALE_COEFFICIENT` has no programmatic route to the
`trimp-coefficient-over-morton` departure that governs it, and a reader holding
that departure has no route back to the constant.

## Why it matters

Req 16.5 asks for a deliberate departure to be recorded *with* the value it
departs on, and the whole point of Amendment 1 is that provenance is queryable
rather than narrated. Right now answering "does this number depart from its
source, and how?" requires a human to read both collections and match them by
eye — which is the state the amendment was written to end.

It also leaves a typed field that looks load-bearing and is not. A later
session will either assign it inconsistently (some constants linked, some not)
or delete it as dead, and neither should happen by accident.

Medium rather than high: nothing is *wrong* today, both records exist and are
correct and pinned, and no rendered document depends on the link yet. The cost
is that task 12.1's `ConstantGuard` cannot assert the relationship, and
whatever consumes provenance downstream will have to.

## Evidence

At `bf588a5` with task 9.4's work applied:

- `src/fitdocs/citation.py` — `CitedConstant.departure: Departure | None = None`
  is declared, with the class docstring saying the type "Binds a value to its
  governing source, its corroborators, **any deliberate departure**, and the
  value it replaced".
- `grep -rn "departure=" src/` — no matches. Every one of the ten
  `CitedConstant` bindings leaves it defaulted.
- `src/fitdocs/metrics/sources.py` — `DEPARTURES` is a module-level
  `tuple[Departure, ...]` of three entries; `Departure.subject` values are
  free-text slugs with no correspondence to any `CitedConstant.name`
  (`trimp_coefficient_banister_male` vs `trimp-coefficient-over-morton`).
- `.kiro/specs/fit-ingest/design.md:476` — traceability maps 16.5 to
  "`Departure`, `DEPARTURES`"; `:779` shows the `departure` field on the
  dataclass. The design declares both and does not say how they connect.
- `tests/metrics/test_sources.py` — `test_none_of_the_ten_constants_records_a_previous_value_or_departure`
  asserts the field is `None` on all ten. That test is correct for task 9.3/9.4
  as scoped; it also means the current emptiness is pinned, so any future
  linking must update it deliberately.

Reported by the task-9.4 round-1 reviewer; the greps and file readings above
were confirmed in this session.

## How to pick it up

1. Read Req 16.5 and `design.md`'s citation-layer section, then decide whether
   the link should be (a) `CitedConstant.departure` populated on the constants
   that depart, with `DEPARTURES` derived from the registry, (b) `Departure`
   gaining a field naming the constant(s) it governs, or (c) the field removed
   and the standalone tuple documented as the only representation. Note the
   third departure (`trimp-coefficient-over-morton`) governs **two** constants
   (male and female coefficient) and the first governs a *behavior* rather than
   a constant at all, so a one-to-one field may not fit — that asymmetry is the
   real design question and is why this is not a two-line fix.
2. Whichever is chosen, task 12.1's `ConstantGuard` is where the invariant gets
   asserted; coordinate with it rather than landing a guard twice.
3. If the answer is (c), say so in `design.md` explicitly and delete the field,
   so the next reader does not re-ask this.

Done means: either every departure is programmatically reachable from the
constant it governs (and a guard asserts it), or the design records why it is
not and the unused field is gone.
