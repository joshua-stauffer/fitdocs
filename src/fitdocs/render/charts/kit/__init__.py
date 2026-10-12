"""The chart kit: validated, deterministic charts from typed tabular data.

The kit turns a ``ChartRequest`` and typed ``ChartData`` into SVG or markdown,
or into structured problems. It is pure: no clock, randomness, environment,
file or network access.

Allowed imports: the standard library, ``fitdocs.render.charts.{svg,series,
palette}``, ``fitdocs.units`` and earlier kit modules in the design's
dependency order. The public facade is added by a later task; nothing is
re-exported here yet.
"""
