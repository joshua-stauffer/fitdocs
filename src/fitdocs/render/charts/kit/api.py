"""The two entry points: validate a request, render a chart.

``render_chart`` looks the kind up in the registry and hands it to
:func:`render_spec`, which runs the three stages: request, data, the kind's
``check``, and only then ``draw``. A stage runs only if every earlier stage
reported nothing; a failing stage raises :class:`ChartError` with all of its
own problems and nothing is drawn.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from fitdocs.render.charts.kit import registry
from fitdocs.render.charts.kit.data import ChartData, Column
from fitdocs.render.charts.kit.problems import ChartError, ChartProblem
from fitdocs.render.charts.kit.schema import ChartRequest, KindSpec, Output
from fitdocs.render.charts.kit.validate import (
    bind_chart,
    bind_request,
    check_data,
    validate_request,
)


@dataclass(frozen=True)
class RenderedChart:
    kind: str
    output: Output
    text: str  # no trailing newline


def validate_chart(
    request: ChartRequest, columns: Sequence[Column]
) -> tuple[ChartProblem, ...]:
    """Stage 1 alone: every request-level problem, from columns without rows."""
    return validate_request(
        request, columns, registry.kind_named(request.kind), registry.kind_names()
    )


def render_spec(
    spec: KindSpec, request: ChartRequest, data: ChartData
) -> RenderedChart:
    """The full pipeline for one kind, whether or not it is registered."""
    problems = validate_request(request, data.columns, spec, registry.kind_names())
    if problems:
        raise ChartError(problems)
    bound = bind_request(request, data.columns, spec)
    problems = check_data(bound, data.rows)
    if problems:
        raise ChartError(problems)
    chart = bind_chart(bound, data.rows)
    problems = spec.check(chart)
    if problems:
        raise ChartError(problems)
    return RenderedChart(spec.name, spec.output, spec.draw(chart))


def render_chart(request: ChartRequest, data: ChartData) -> RenderedChart:
    """Render ``request`` over ``data``; raises :class:`ChartError` on any problem."""
    spec = registry.kind_named(request.kind)
    if spec is None:
        raise ChartError(
            validate_request(request, data.columns, None, registry.kind_names())
        )
    return render_spec(spec, request, data)
