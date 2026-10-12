"""The engine's view of "rows for this SQL", independent of the query layer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from fitdocs.dashboards.problems import Problem
from fitdocs.render.charts.kit import ChartData


@dataclass(frozen=True)
class Fetched:
    data: ChartData  # columns typed, units applied


@dataclass(frozen=True)
class SourceUnavailable:
    state: str  # "not_built" | "needs_rebuild" | "busy" | "unverified"
    message: str  # one sentence, e.g. "the index is not built."
    fix: str  # e.g. "Run `fitdocs index` to build it."


class ChartSource(Protocol):
    def fetch(
        self, sql: str, *, today: date, page: str, chart: str, line: int
    ) -> Fetched | tuple[Problem, ...]: ...

    def close(self) -> None: ...


SourceOpener = Callable[[], ChartSource | SourceUnavailable]
