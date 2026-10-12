---
id: 2026-10-13-driven-capabilities-published-but-read-by-nothing
title: "DRIVEN_CAPABILITIES is published by the connectors package but no source module reads it; the registry and the pull engine hard-code their capability checks"
status: open
importance: low
importance_why: The constant and the checks agree today and a test pins the constant; the cost is that a capability added to one and not the other drifts silently, which wellness-pull is about to make easier by widening the set.
effort: S
kind: inconsistency
area: connectors, src/fitdocs/connectors/protocol.py, src/fitdocs/connectors/registry.py, src/fitdocs/connectors/pull.py
created: 2026-10-13
surfaced_by: /kiro-spec-batch phase 12 (wellness-pull spec, controller queue triage)
pinned_at: 86cdf14
resume_command: "do: either make src/fitdocs/connectors/registry.py (conformance check) and pull.py (capability gate) derive their checks from DRIVEN_CAPABILITIES, or stop exporting it and say in protocol.py why the checks are spelled out; after wellness-pull widens the set, pin that every driven capability has a registry rule and a pull step [queue: .kiro/queue/2026-10-13-driven-capabilities-published-but-read-by-nothing.md]"
context:
  - src/fitdocs/connectors/protocol.py
  - src/fitdocs/connectors/registry.py
  - src/fitdocs/connectors/pull.py
  - src/fitdocs/connectors/__init__.py
  - tests/connectors/test_protocol.py
  - .kiro/specs/wellness-pull/design.md
blocked_by: []
---

## What

`DRIVEN_CAPABILITIES` says which of the nine connector capabilities the
framework actually drives (today only `PULL_ACTIVITIES`). It is defined in
`protocol.py`, re-exported from the package, and pinned by tests, but nothing
in `src/` reads it. The registry's conformance check and the pull engine each
spell the capability out: `registry.py` tests `PULL_ACTIVITIES` by name to
decide which methods must be callable, and `pull.py` refuses an instance whose
connector lacks `PULL_ACTIVITIES` by name. The set is documentation that
looks like a source of truth.

## Why it matters

A capability added to `DRIVEN_CAPABILITIES` without the matching registry
rule and pull step (or the reverse) passes every check and drifts. wellness-pull
widens the set to two members (`PULL_WELLNESS`), so the number of places that
must agree grows (a second registry rule and a second pull step) while the
constant still guards neither.

## Evidence

Read at `86cdf14`.

- `src/fitdocs/connectors/protocol.py:141-143` -- the definition,
  `frozenset({Capability.PULL_ACTIVITIES})`.
- `grep -rn "DRIVEN_CAPABILITIES" src` -- only `protocol.py:141`, and the
  re-export at `src/fitdocs/connectors/__init__.py:54` and `:93`.
- `src/fitdocs/connectors/registry.py:193-207` -- the conformance check tests
  `Capability.PULL_ACTIVITIES` by name and demands `list_activities` and
  `fetch_activity`.
- `src/fitdocs/connectors/pull.py:420` -- `if Capability.PULL_ACTIVITIES not in
  connector.capabilities` gates the instance.
- `tests/connectors/test_protocol.py:194` pins the value; `tests/connectors/test_surface.py:20`
  and `:71` pin the export.
- `.kiro/specs/wellness-pull/research.md:15-21` and `design.md:132-134` record
  the same observation ("re-exported but read by no `src/` module"); design
  `:527` widens the set to `{PULL_ACTIVITIES, PULL_WELLNESS}`, and task 1.2
  (`tasks.md:155-161`) makes it hold both, with no reader added.

## How to pick it up

1. Read `protocol.py:58-146` (`CapabilityInfo.driven`, `CAPABILITIES`) next
   to `registry.py:111-212` (`validate_connector`) and `pull.py:410-450`.
2. Choose between deriving the checks (a table from a driven capability to its
   required methods, consumed by the registry, and a single gate in the pull
   engine) and deleting the export. The table is small and pays off once
   wellness-pull has two entries.
3. Done when adding a driven capability without a registry rule fails a named
   test, shown by a mutation that adds a member to the set only.
