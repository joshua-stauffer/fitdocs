# Requirements Document

## Project Description (Input)
**Who has the problem.** An athlete whose LLM assistant writes dashboard pages
in their wiki (Phase 11, `dashboards`) and asks questions of the analytics
index that the eight core chart kinds of `chart-kit` (line, area, bar, hbar,
scatter, histogram, stat, table) cannot show: which days of the year they
trained and how hard; how their zone distribution shifted week by week; two
quantities in different units over one time axis; the spread of a value, not
just its average; best-effort curves over a log duration axis; and many small
series at once.

**Current situation.** `chart-kit` provides a typed data contract, scales,
ticks, unit-aware labels, axes, a legend, one light/dark theme, a declared
append-only kind registry with structured validation, and mark bounds. Its
kinds cover comparison and trend only. The existing calendar chart is a daily
multi-line chart, not a heatmap, and stays untouched.

**What should change.** Eight more kinds are appended to chart-kit's registry,
each a thin module over the shared layer with its own encoding schema, mark
bound, goldens and named mutations: `calendar-heatmap`, `heatmap`,
`dual-axis`, `band`, `box`, `mean-max`, `small-multiples` and `stacked-100`.
They validate, render, theme and bound exactly as the core kinds do. Absent
data is never drawn as zero, and a heatmap cell with no value differs visibly
from a cell whose value is zero, in both themes and for colour-blind viewers.
Any shared-layer addition a kind proves it needs is appended, never edited.
Whichever of `dashboards` and `chart-catalog` lands second updates every
listing or count of registered kinds.

Source: `.kiro/specs/chart-catalog/brief.md`; Phase 11 of
`.kiro/steering/roadmap.md`. Dependencies: `chart-kit`. Parallel with
`dashboards`.

## Requirements
<!-- Will be generated in /kiro-spec-requirements phase -->
