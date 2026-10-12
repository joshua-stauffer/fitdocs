---
id: 2026-10-13-dashboards-over-wellness-daily-owe-garmin-attribution
title: "Dashboards charting wellness_daily owe Garmin attribution, and the dashboards spec has no attribution mechanism and may not import the shared rule"
status: open
importance: medium
importance_why: Garmin-origin values charted on a dashboard fall under intervals.icu API terms section 1.1 and Garmin's brand guidelines, which the maintainer's recovery page and morning block already honour; a dashboard is the one wellness surface that would not.
effort: M
kind: gap
area: dashboards, wellness-store, recovery, src/fitdocs/render/attribution.py
created: 2026-10-13
surfaced_by: /kiro-spec-batch phase 12 (wellness-store and recovery specs, controller queue triage)
pinned_at: 86cdf14
resume_command: "/kiro-spec-design dashboards [queue: .kiro/queue/2026-10-13-dashboards-over-wellness-daily-owe-garmin-attribution.md] Decide how a dashboard that charts wellness_daily carries Garmin attribution, and whether the dashboards import rules admit the shared wellness_attribution rule"
context:
  - .kiro/specs/dashboards/design.md
  - .kiro/specs/dashboards/requirements.md
  - .kiro/specs/wellness-store/design.md
  - .kiro/specs/recovery/design.md
  - .kiro/specs/intervals-connector/research.md
  - src/fitdocs/render/attribution.py
blocked_by: [wellness-store, recovery]
---

## What

Once wellness-store lands, the analytics index gains a `wellness_daily` table
whose `origin` column records the platform that measured each value (for
example `garmin`). `fitdocs dashboards` renders charts from user-written SQL
over the index, so a dashboard can chart `wellness_daily` values whose origin
is Garmin. Those surfaces owe Garmin attribution, and the dashboards spec has
nothing for it: no mention of attribution anywhere in its requirements or
design, and its allowed-dependency list forbids importing any
`fitdocs.render` module except the chart kit facade, which rules out calling
the shared rule that recovery adds (`wellness_attribution` in
`src/fitdocs/render/attribution.py`, recovery task 3.3).

A second, related gap: a dashboard cannot draw recovery's normal-range bands
without recomputing them, because no index table holds the baselines. Recovery
lists "a baselines index table" as a non-goal. A table built from the
`fitdocs.recovery` library would let a dashboard show the same bands the
recovery page shows.

## Why it matters

The attribution duty comes from the terms of the API that supplies the data.
wellness-store's own docs plan says so in one sentence and names "a dashboard
over `wellness_daily`" as the example. If dashboards ship first and nobody
revisits, the maintainer's own dashboards would show Garmin-origin values with
no attribution while the recovery page and morning block carry it. Without the
baselines table, a dashboard of the same signals will disagree with the
recovery page's bands or recompute them in SQL.

## Evidence

Read at `86cdf14`.

- `.kiro/specs/intervals-connector/research.md:97-133` -- the terms: API terms
  section 1.1 ("if your application displays information derived from
  Garmin-sourced data, you must display attribution to Garmin"), Garmin's
  "Combined or derived data" and "Visual and social media" sections.
- `.kiro/specs/wellness-store/design.md:1475-1488` -- the `wellness_daily`
  columns, including `origin`; `:1368-1371` -- the docs sentence that "any
  surface that charts or prints `garmin`-origin values, a dashboard over
  `wellness_daily` for example, owes Garmin attribution"; `:119-120` -- the
  columns are a revalidation trigger for "dashboards over wellness".
- `grep -rli attribution .kiro/specs/dashboards` -- no matches at `86cdf14`.
- `.kiro/specs/dashboards/design.md:95` -- "Never: ... any other
  `fitdocs.render` module" (the only render import allowed is the chart kit
  facade, `:81-87`).
- `.kiro/specs/recovery/design.md:61-65` and `:1111-1140` -- the shared names
  `GARMIN_ORIGIN`, `WellnessAttribution`, `wellness_attribution`,
  `wellness_attribution_line`, appended to `src/fitdocs/render/attribution.py`
  (recovery task 3.3, `tasks.md:510-515`). Today that module holds only the
  workout-page names (`src/fitdocs/render/attribution.py:1-40`).
- `.kiro/specs/recovery/design.md:42` and `:1396` -- no baselines index table.
- Related, not duplicate: `.kiro/queue/2026-09-29-garmin-attribution-scope-decisions.md`
  (chart images and aggregate pages, for activity data).

## How to pick it up

1. Read the three Evidence blocks above, then dashboards `requirements.md` and
   `design.md` § Region and § Source (what the engine knows about a chart's
   SQL and result columns).
2. Decide the mechanism. Candidates: an attribution line the engine adds when
   a chart's result carries an `origin` column holding `garmin`, a field on
   the chart directive the author sets, or a documented duty on the author
   only. Each has a cost: reading result columns is stricter than reading SQL
   text but only sees what the query selected.
3. If the shared rule is to be reused, decide where it lives so the import rule
   is not broken (a pure stdlib helper outside `fitdocs.render` is one option;
   widening the allow-list is the other). Record the answer as an amendment to
   dashboards and, if a table is wanted, a baselines-table amendment to
   recovery and analytics-derived.

## Open questions

- Is a chart image a "visual asset" needing attribution in the image itself
  (queue item above)? The answer changes whether a line on the page is enough.
- Does the maintainer want recovery's bands on dashboards badly enough to pay
  for a baselines table that must be rebuilt whenever a baseline constant
  changes (`BASELINES_VERSION`, recovery `design.md:131-133`)?
