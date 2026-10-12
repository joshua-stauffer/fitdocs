"""Shared builders for the chart kit's tests.

Data builders: they construct the kit's frozen records from plain
literals. Render helpers are appended by the task that introduces rendering.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from fitdocs.render.charts.kit.data import ChartData, Column, Value, ValueKind
from fitdocs.render.charts.kit.schema import ChartRequest, OptionValue


@dataclass(frozen=True)
class Case:
    """One golden case: a name, the request and the data it renders."""

    name: str
    request: ChartRequest
    data: ChartData


def column(
    name: str,
    kind: ValueKind = ValueKind.NUMBER,
    *,
    unit: str | None = None,
    label: str | None = None,
) -> Column:
    return Column(name, kind, unit=unit, label=label)


def chart_data(columns: Sequence[Column], rows: Iterable[Sequence[Value]]) -> ChartData:
    """Freeze ``columns`` and ``rows`` into tuples, keeping order and ``None``."""
    return ChartData(tuple(columns), tuple(tuple(row) for row in rows))


def chart_request(
    kind: str,
    *,
    ref: str = "c1",
    title: str = "Title",
    channels: Mapping[str, str] | None = None,
    options: Mapping[str, OptionValue] | None = None,
) -> ChartRequest:
    return ChartRequest(
        ref,
        kind,
        title,
        dict(channels) if channels is not None else {},
        dict(options) if options is not None else {},
    )
