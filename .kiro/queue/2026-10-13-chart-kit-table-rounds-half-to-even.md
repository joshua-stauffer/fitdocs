---
id: 2026-10-13-chart-kit-table-rounds-half-to-even
title: The chart kit formats a number with Python's format(), which rounds half to even, so 31.25 km shows as 31.2 in a table, and the rule is documented only for durations
status: open
importance: low
importance_why: A value that sits exactly on a rounding boundary prints the lower neighbour about half the time; users comparing a table to their own arithmetic can see an off-by-one in the last digit.
effort: S
kind: inconsistency
area: chart-kit, src/fitdocs/render/charts/kit/format.py, .kiro/specs/chart-kit/design.md
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 8.3 reviewer)
pinned_at: 0a98d5c
resume_command: "do: decide whether kit number formatting should round half away from zero or stay half-even; either way state the rule in the chart-kit design next to format_duration's and in docs/dashboards.md, and pin it with one boundary test per unit decimals value [queue: .kiro/queue/2026-10-13-chart-kit-table-rounds-half-to-even.md]"
context:
  - src/fitdocs/render/charts/kit/format.py
  - src/fitdocs/render/charts/kit/kinds/table.py
  - src/fitdocs/units.py
  - .kiro/specs/chart-kit/design.md
  - docs/dashboards.md
blocked_by: []
---

## What
A numeric cell (a table cell, and any value label that goes through `format_value`) is formatted by `_fixed` (`src/fitdocs/render/charts/kit/format.py:86`),
which calls `format(value, ".{decimals}f")`. That rounds half to even on the
exact binary value. A column with a one-decimal unit (`km`, `kg`, `deg`, `pct`,
`c`, `kn_m` in `src/fitdocs/units.py`) therefore shows a value that is exactly
halfway as the even neighbour. The chart-kit design states half-to-even only for
`format_duration` (`design.md:893`); nothing states it for numbers.

## Why it matters
`31.25` in a `distance_km` column prints `31.2`, and `31.35` prints `31.4`, which
looks inconsistent to a reader and differs from how most spreadsheets round.
The behaviour may be intended; it is undocumented, so a user or agent cannot
tell a bug from a rule.

## Evidence
Run at 0a98d5c against the real kit (`render_chart(ChartRequest(ref="t", kind="table", title="T"), data)`
with `Column("distance_km", ValueKind.NUMBER, "km")`):

```
31.25 -> | 31.2 |
31.35 -> | 31.4 |
0.25  -> | 0.2  |
0.35  -> | 0.3  |
2.675 -> | 2.7  |
```

(0.35 and 2.675 are not exactly representable, so they round by their stored
value; 31.25 and 0.25 are exact halves.) Without a unit the table prints up to
two decimals, trimmed (`_trimmed`, `format.py:93`), so `31.25` prints `31.25`.
`.kiro/specs/chart-kit/design.md:893`: "`format_duration`: round half-to-even to whole seconds".

## How to pick it up
1. Decide the rule. Half-to-even on the stored binary value is defensible and is what `format()` does; the alternative is `Decimal` quantisation with `ROUND_HALF_UP`, which changes bytes of already-rendered images and tables, so the golden SVGs and tables would move.
2. Whichever is chosen, add one sentence to the chart-kit design (§ format) and to the number-formatting paragraph of `docs/dashboards.md`, and one boundary test per `decimals` value.
3. Check whether a change in output bytes needs a kit contract-version note (chart-kit design § versioning, if present).

## Open questions
Whether to change the behaviour or only document it. Documenting costs nothing and changes no bytes.
