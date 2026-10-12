"""The chart kit: validated, deterministic charts from typed tabular data.

The kit turns a ``ChartRequest`` and typed ``ChartData`` into SVG or markdown,
or into structured problems. It is pure: no clock, randomness, environment,
file or network access.

Allowed imports: the standard library, ``fitdocs.render.charts.{svg,series,
palette}``, ``fitdocs.units`` and earlier kit modules in the design's
dependency order.
"""

from fitdocs.render.charts.kit.api import (
    RenderedChart,
    render_chart,
    validate_chart,
)
from fitdocs.render.charts.kit.data import ChartData, Column, Value, ValueKind
from fitdocs.render.charts.kit.problems import (
    ChartError,
    ChartProblem,
    ProblemCode,
    ProblemDict,
)
from fitdocs.render.charts.kit.registry import (
    KindListing,
    describe_kinds,
    kind_names,
)
from fitdocs.render.charts.kit.schema import ChartRequest, OptionValue, Output

__all__ = (
    "ValueKind",
    "Value",
    "Column",
    "ChartData",
    "ChartRequest",
    "OptionValue",
    "Output",
    "ProblemCode",
    "ChartProblem",
    "ProblemDict",
    "ChartError",
    "RenderedChart",
    "validate_chart",
    "render_chart",
    "describe_kinds",
    "kind_names",
    "KindListing",
)
