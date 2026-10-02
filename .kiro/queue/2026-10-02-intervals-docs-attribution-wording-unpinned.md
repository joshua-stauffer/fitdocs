---
id: 2026-10-02-intervals-docs-attribution-wording-unpinned
title: docs/connectors.md's Garmin attribution wording is not pinned to render/attribution.py, and it describes only the single-source line
status: open
importance: low
importance_why: The doc is true today. Nothing fails if the attribution wording changes, and the doc will be incomplete once channel-merge wires donor devices.
effort: S
kind: gap
area: intervals-connector, docs/connectors.md, src/fitdocs/render/attribution.py, tests/connectors/test_intervals_docs.py
created: 2026-10-02
surfaced_by: /kiro-impl intervals-connector (4.2 review, feature validation)
pinned_at: 9d08482
resume_command: "/kiro-impl intervals-connector [queue: .kiro/queue/2026-10-02-intervals-docs-attribution-wording-unpinned.md] Pin the docs' attribution wording to render/attribution.py and describe the multi-source line"
context:
  - docs/connectors.md
  - src/fitdocs/render/attribution.py
  - tests/connectors/test_intervals_docs.py
  - .kiro/specs/intervals-connector/design.md
  - .kiro/specs/channel-merge/tasks.md
blocked_by: []
---

## What
docs/connectors.md, under `### Garmin attribution` in its `## intervals.icu`
section, says a page whose recording device is a Garmin carries `Data source:
Garmin <model>` beneath its title. Two gaps:
- No test ties that text to `render/attribution.py`'s `SOLE_SOURCE_PREFIX`
  (`"Data source: "`).
- The section never shows the `Data sources: …, … and other devices` form
  that `attribution_line` produces for several contributors. That form only
  reaches pages once channel-merge wires donor devices into
  `render/views.py::_head` (intervals-connector design.md ruling R2).

## Why it matters
If someone changes the wording in `attribution.py`, the docs go stale and no
test fails. Once channel-merge lands, composed pages will carry the plural
line, which the docs do not describe.

## Evidence
- `docs/connectors.md:184`: `` `Data source: Garmin <model>` directly beneath its title ``.
- `src/fitdocs/render/attribution.py:19`: `SOLE_SOURCE_PREFIX: Final[str] = "Data source: "`.
- `grep -n "SOLE_SOURCE_PREFIX\|Data source" tests/connectors/test_intervals_docs.py`
  finds nothing at 9d08482.
- The 4.2 reviewer changed the attribution wording (mutation O9) and the suite
  stayed green (reviewer subagent; not re-run by the controller).

## How to pick it up
1. Read `attribution.py` (`SOLE_SOURCE_PREFIX`, the plural prefix and the
   "other devices" constant) and the docs section.
2. In `tests/connectors/test_intervals_docs.py`, read the section by its
   heading and assert it quotes the prefixes built from the module's
   constants. Mutate a constant and confirm the test goes red.
3. If channel-merge has landed, add one sentence and an example for the
   `Data sources: … and other devices` form.
