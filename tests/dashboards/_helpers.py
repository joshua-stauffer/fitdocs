"""Shared builders for the dashboards tests: pages, data, a fake source, snapshots."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from threading import Timer

from fitdocs.dashboards.problems import Problem
from fitdocs.dashboards.source import (
    ChartSource,
    Fetched,
    SourceOpener,
    SourceUnavailable,
)
from fitdocs.query.command import QueryEnvironment
from fitdocs.render.charts.kit import ChartData, Column, Value, ValueKind

# -- page text ---------------------------------------------------------------


def directive_block(keys: Sequence[tuple[str, str]], *, ending: str = "\n") -> str:
    """A chart directive: opener, ``key: value`` lines in the given order, closer.

    Values are written verbatim (no quoting is added). A value may span lines
    with ``"\\n"``; every line of it, like every other line, ends with
    ``ending``.
    """
    text = "\n".join(
        ["<!-- fitdocs:chart", *(f"{key}: {value}" for key, value in keys), "-->"]
    )
    return "".join(line + ending for line in text.split("\n"))


def region_block(
    chart_id: str, body: str = "", *, ending: str = "\n", closed: bool = True
) -> str:
    """A generated region: begin marker, the body lines, and (if closed) the end marker.

    ``body`` is split on newlines and each line gets ``ending``; an empty body
    yields no body lines.
    """
    lines = [f"<!-- fitdocs:begin:chart:{chart_id} -->"]
    if body:
        lines.extend(body.split("\n"))
    if closed:
        lines.append(f"<!-- fitdocs:end:chart:{chart_id} -->")
    return "".join(line + ending for line in lines)


def page_text(
    *parts: str,
    frontmatter: Mapping[str, str] | None = None,
    ending: str = "\n",
    bom: bool = False,
) -> str:
    """A dashboard page: optional BOM and frontmatter, then the parts in order.

    ``parts`` are used as given (directive and region blocks carry their own
    endings); a part that does not end with a line ending gets ``ending``.
    """
    out: list[str] = []
    if bom:
        out.append("﻿")
    if frontmatter is not None:
        out.append("---" + ending)
        out.extend(f"{key}: {value}{ending}" for key, value in frontmatter.items())
        out.append("---" + ending)
    for part in parts:
        out.append(part if part.endswith(("\n", "\r")) else part + ending)
    return "".join(out)


# -- typed chart data ----------------------------------------------------------


def number_column(name: str, *, unit: str | None = None) -> Column:
    return Column(name, ValueKind.NUMBER, unit)


def category_column(name: str) -> Column:
    return Column(name, ValueKind.CATEGORY)


def date_column(name: str) -> Column:
    return Column(name, ValueKind.DATE)


def chart_data(columns: Sequence[Column], rows: Sequence[Sequence[Value]]) -> ChartData:
    return ChartData(tuple(columns), tuple(tuple(row) for row in rows))


def category_number_data(
    pairs: Sequence[tuple[str | None, float | None]],
    *,
    category: str = "label",
    number: str = "value",
) -> ChartData:
    """Two columns, a category and a number; rows in the order given."""
    return chart_data(
        (category_column(category), number_column(number)),
        [(label, value) for label, value in pairs],
    )


def date_number_data(
    pairs: Sequence[tuple[date | None, float | None]],
    *,
    day: str = "day",
    number: str = "value",
) -> ChartData:
    """Two columns, a date and a number; rows in the order given."""
    return chart_data(
        (date_column(day), number_column(number)),
        [(when, value) for when, value in pairs],
    )


# -- a fake chart source ------------------------------------------------------


@dataclass(frozen=True)
class FetchCall:
    sql: str
    today: date
    page: str
    chart: str
    line: int


@dataclass
class FakeSource:
    """A :class:`ChartSource` answering from a table of queued results per SQL.

    ``results[sql]`` is a list; each ``fetch`` pops the first entry (the last
    one repeats once the list has a single entry left). An SQL with no entry
    raises ``AssertionError``, so an unexpected query is loud.
    """

    results: dict[str, list[Fetched | tuple[Problem, ...]]] = field(
        default_factory=dict
    )
    calls: list[FetchCall] = field(default_factory=list)
    closed: int = 0
    opened: int = 0
    misused: list[str] = field(default_factory=list)

    def queue(self, sql: str, *answers: ChartData | tuple[Problem, ...]) -> None:
        wrapped: list[Fetched | tuple[Problem, ...]] = [
            Fetched(answer) if isinstance(answer, ChartData) else answer
            for answer in answers
        ]
        self.results.setdefault(sql, []).extend(wrapped)

    def fetch(
        self, sql: str, *, today: date, page: str, chart: str, line: int
    ) -> Fetched | tuple[Problem, ...]:
        self.calls.append(FetchCall(sql, today, page, chart, line))
        if sql not in self.results or not self.results[sql]:
            self.misused.append(sql)
            raise AssertionError(f"FakeSource has no result queued for {sql!r}")
        queue = self.results[sql]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def close(self) -> None:
        self.closed += 1

    def opener(self) -> SourceOpener:
        def open_source() -> ChartSource | SourceUnavailable:
            self.opened += 1
            return self

        return open_source


def unavailable_opener(unavailable: SourceUnavailable) -> SourceOpener:
    """An opener that reports the source unavailable."""

    def open_source() -> ChartSource | SourceUnavailable:
        return unavailable

    return open_source


@dataclass
class MustNotOpen:
    """An opener that raises ``AssertionError`` and counts the attempts."""

    attempts: int = 0

    def __call__(self) -> ChartSource | SourceUnavailable:
        self.attempts += 1
        raise AssertionError("the source was opened")


def must_not_open() -> ChartSource | SourceUnavailable:
    """An opener for runs that must not reach the source."""
    raise AssertionError("the source was opened")


# -- data roots and file snapshots ----------------------------------------------


def make_data_root(tmp_path: Path, name: str = "data") -> Path:
    """An empty data root directory under ``tmp_path``."""
    root = tmp_path / name
    root.mkdir()
    return root


def write_page(root: Path, name: str, text: str) -> Path:
    """Write ``text`` as ``dashboards/<name>.md`` under ``root``, bytes unchanged."""
    directory = root / "dashboards"
    directory.mkdir(exist_ok=True)
    path = directory / f"{name}.md"
    path.write_bytes(text.encode("utf-8"))
    return path


FileState = tuple[bytes, int]


def snapshot_of(path: Path) -> dict[str, FileState]:
    """Bytes and ``st_mtime_ns`` of every file under ``path``, by relative path."""
    state: dict[str, FileState] = {}
    for current, _directories, names in os.walk(path):
        for name in names:
            file = Path(current) / name
            state[file.relative_to(path).as_posix()] = (
                file.read_bytes(),
                file.stat().st_mtime_ns,
            )
    return state


def assert_untouched(
    before: Mapping[str, FileState], after: Mapping[str, FileState]
) -> None:
    """Fail unless the same files exist with the same bytes and mtimes."""
    assert before, "the snapshot is empty, so nothing was compared"
    assert sorted(after) == sorted(before), "the set of files changed"
    for name, (data, mtime) in before.items():
        assert after[name][0] == data, f"{name}: bytes changed"
        assert after[name][1] == mtime, f"{name}: st_mtime_ns changed"


# -- the query environment --------------------------------------------------------


def query_environment(
    environ: Mapping[str, str],
    home: Path,
    *,
    pid: int = 74123,
    on_wait: Callable[[int | None], None] | None = None,
) -> QueryEnvironment:
    """A deterministic :class:`QueryEnvironment` over the given environment."""
    return QueryEnvironment(
        environ=dict(environ),
        home=home,
        pid=pid,
        monotonic=lambda: 0.0,
        sleep=lambda _delay: None,
        on_wait=on_wait if on_wait is not None else (lambda _pid: None),
        is_running=lambda _pid: False,
        timer=Timer,
    )
