---
id: 2026-07-30-constant-sources-has-no-production-consumer
title: CONSTANT_SOURCES is read only by tests, so Req 16.6's "a report can name the source of a number" is satisfied only latently
status: open
importance: low
importance_why: The registry is correct and complete; nothing in src/ consumes it, so the requirement it exists to satisfy is demonstrated by no running code and would not notice if the shape stopped being usable.
effort: S
kind: gap
area: fit-ingest, src/fitdocs/metrics/sources.py
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 12.2, reviewer follow-up round 2)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-constant-sources-has-no-production-consumer.md] Decide whether Req 16.6 wants a real consumer of CONSTANT_SOURCES or is satisfied by the registry alone"
context:
  - src/fitdocs/metrics/sources.py
  - .kiro/specs/fit-ingest/requirements.md
  - .kiro/specs/fit-ingest/design.md
  - .kiro/queue/2026-07-28-metrics-eager-init-import-defeats-16-6.md
blocked_by: []
---

## What

Req 16.6 wants a document or report to be able to name the source of a number
it displays. `CONSTANT_SOURCES` in `src/fitdocs/metrics/sources.py` is the
registry built to make that possible — ten `CitedConstant` bindings covering
every value Req 15.6 enumerates.

Nothing in `src/` reads it. The only consumers are tests.

## Why it matters

Low, and filed as such deliberately: the registry is correct, complete, and
guarded (task 12.1), and building a renderer nobody asked for would be worse
than leaving this open.

It matters as a *shape* observation. A data structure whose only consumers are
its own guards is one whose usability is asserted rather than demonstrated. If
the record shape turned out to be awkward for an actual renderer — the wrong
key, a locator that needs formatting, a constant reachable only by importing
the metric machinery — no current test would notice, because no current test
tries to use it the way Req 16.6 describes.

Note this is a *different* clause of Req 16.6 from
`2026-07-28-metrics-eager-init-import-defeats-16-6`, which covers "readable
without computing a metric" (the eager-import problem). That item is about
whether the records are *reachable*; this one is about whether anything
actually *uses* them. They are likely to be picked up together and the
import problem probably has to be solved first.

## Evidence

At `2d69443` plus the uncommitted task 12.2 work:

```
$ grep -rn 'CONSTANT_SOURCES' src/ | grep -v 'sources.py'
src/fitdocs/metrics/power.py:64:is not registered in ``CONSTANT_SOURCES``. The averaging exponent's root is
```

The single hit outside `sources.py` is prose inside a docstring, not a read.

```
$ grep -rln 'CONSTANT_SOURCES' src/ tests/
src/fitdocs/metrics/sources.py
src/fitdocs/metrics/power.py
tests/metrics/test_sources.py
tests/metrics/test_constant_guard.py
```

## How to pick it up

1. Re-read Req 16.6 in `.kiro/specs/fit-ingest/requirements.md` and decide
   what it actually obliges: a capability (the registry exists and is
   well-shaped) or a behaviour (something renders a citation). The wording
   will settle whether this is a real gap or a closed item.
2. If it is a capability only, close this item with that ruling recorded in
   the design's ConstantGuard or MetricsSources section, so the question is
   not re-opened by the next reader who greps for consumers.
3. If it is a behaviour, the smallest honest demonstration is a test that
   consumes the registry the way a renderer would — take a reported metric,
   look up its governing source, and assert the rendered attribution names
   the right work and locator. Resolve
   `2026-07-28-metrics-eager-init-import-defeats-16-6` first or the test
   cannot import the records without pulling in the metric modules.

Done looks like: either a recorded ruling that the registry alone satisfies
16.6, or one consumer exercising it end to end.
