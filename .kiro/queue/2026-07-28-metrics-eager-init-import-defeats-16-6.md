---
id: 2026-07-28-metrics-eager-init-import-defeats-16-6
title: "`metrics/__init__.py`'s eager sibling import makes Req 16.6's \"readable without computing a metric\" structurally unachievable"
status: open
importance: medium
importance_why: Req 16.6 wants the citation records readable by a document or report without pulling in the metric machinery, and `fitdocs/metrics/__init__.py` imports `aggregates`, `power`, `stress` and `zones` on any `fitdocs.metrics.*` import — so the property cannot hold no matter how `sources.py` is written. Task 9.1 discovered this by writing the obvious test and finding it unreachable, then narrowed the test honestly. Nothing enforces 16.6 structurally today, and nothing will until this import changes.
effort: M
kind: gap
area: fit-ingest, src/fitdocs/metrics/__init__.py, src/fitdocs/metrics/sources.py
created: 2026-07-28
surfaced_by: /kiro-impl fit-ingest (task 9.1 — implementer CONCERN, independently confirmed by the reviewer)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-28-metrics-eager-init-import-defeats-16-6.md] Decide whether Req 16.6's import-isolation is a real requirement and, if so, make metrics/__init__.py lazy"
context:
  - src/fitdocs/metrics/__init__.py
  - src/fitdocs/metrics/sources.py
  - src/fitdocs/__init__.py
  - .kiro/specs/fit-ingest/requirements.md
  - .kiro/specs/fit-ingest/design.md
blocked_by: []
---

## What

Requirement 16.6 asks that the citation records be independently importable —
"so a document or report can name the source of a number without computing a
metric", in the design's words for `MetricsSources`.

`src/fitdocs/metrics/__init__.py:41` reads:

```python
from fitdocs.metrics import aggregates, power, stress, zones
```

Python runs a package's `__init__` before any submodule of it, so
`import fitdocs.metrics.sources` necessarily executes that line first. A fresh
interpreter that imports only the records ends up with all four
arithmetic-bearing metric modules loaded. No amount of care inside `sources.py`
can change that; the property is defeated one level up.

## Why it matters

Two distinct costs.

**The requirement is unpinnable as written.** Task 9.1 wrote the natural test —
assert no arithmetic-bearing sibling lands in `sys.modules` after importing the
records in a subprocess — and found it could never fail. That is the
*unreachable scenario* anti-pattern from `.kiro/steering/change-protocol.md`
§ Fixture Discrimination. The task narrowed it honestly to an SDK check plus a
static AST check of the module's own imports and said so in the test docstring,
which is the right call for that boundary. But the consequence is that 16.6's
actual claim is now enforced by nothing.

**It already produced a false statement in shipped code.** The same task's
module docstring asserted the module was importable "without pulling in the
`garmin-fit-sdk` or any arithmetic-bearing sibling module". The first half is
true; the second is false, and it was contradicted by the task's own test
docstring in the same change. That is worth recording because it shows the
shape of the hazard: the requirement reads as though it holds, so an author
writing prose about the module will state it, and only an executed subprocess
check reveals otherwise.

Note this is not an argument that the eager import is *wrong*. It may be
deliberate — it makes `from fitdocs.metrics import compute_metrics` and the
facade work without callers importing submodules. The question is whether 16.6
means what it says.

## Evidence

At `8e72bfc`, in a fresh subprocess:

```
python -c "import fitdocs.metrics.sources, sys;
           print([m for m in sys.modules if m.startswith('fitdocs.metrics')])"
→ fitdocs.metrics, fitdocs.metrics.aggregates, fitdocs.metrics.power,
  fitdocs.metrics.stress, fitdocs.metrics.zones, fitdocs.metrics.sources, ...
```

`src/fitdocs/metrics/__init__.py:41` is the cause. Confirmed independently by
the task 9.1 reviewer, which also verified that `garmin_fit_sdk` is genuinely
absent — so the SDK half of the claim stands and only the sibling half fails.

Contrast with the package root, which solves the same problem the other way:
`src/fitdocs/__init__.py` uses lazy PEP 562 `__getattr__` re-exports with a
`TYPE_CHECKING` block, specifically so that `import fitdocs.model` does not pull
`garmin_fit_sdk` into every consumer (recorded in `tasks.md`'s Implementation
Notes for task 6). The technique to make `metrics` lazy already exists in this
codebase.

## How to pick it up

1. **Decide the requirement question first, because it determines whether there
   is any work.** Read Req 16.6 in `.kiro/specs/fit-ingest/requirements.md` and
   the `MetricsSources` "Independently importable" bullet in `design.md`. Either:
   - 16.6 means literal import isolation → make `metrics/__init__.py` lazy and
     pin it with the subprocess test task 9.1 could not write; or
   - 16.6 means only "reading a record computes nothing at import time" → say so
     in the requirement, and record that the sibling modules are loaded but
     inert. The current wording invites the stronger reading.
2. If making it lazy: follow the root package's PEP 562 `__getattr__` pattern
   rather than inventing one. Check every consumer of `from fitdocs.metrics
   import ...` still resolves, and confirm `compute_metrics` remains importable
   from `fitdocs.metrics` — that is the facade's public entry point.
3. Done looks like: the subprocess assertion that task 9.1 wanted to write is
   both **writable and failing** under a deliberate re-introduction of the eager
   import. Per `.kiro/steering/change-protocol.md`, run that as the mutation — a
   guard never shown to fail is not a guard, and this specific guard was already
   found unreachable once.

## Open questions

Whether 16.6 was ever intended as literal import isolation or as "no
computation on import". The design's phrasing ("so a document or report can name
the source of a number without computing a metric") supports the weaker reading;
the requirement's placement alongside the layering rules supports the stronger.
This is a maintainer call and it decides between a one-line requirements
clarification and a refactor of the metrics package's import surface.
