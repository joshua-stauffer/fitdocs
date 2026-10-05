"""Contracts and inputs for analytics-index row producers.

Producers are pure: they do not write files, access the network, read the
clock, or import DuckDB. Given the same input, a producer returns the same
rows as a multiset. A producer returns a mapping containing every declared
table and no undeclared table; each declared table may have zero rows. Each
row contains values for declared columns only, because the store prepends
``page_key`` to per-page rows. Datetime values are naive.

A corpus producer fingerprints every input it reads and includes ``today`` in
its fingerprint when it uses that value. A producer that reads workout pages
fingerprints both ``CorpusSnapshot.pages`` and ``CorpusSnapshot.left_out``
instead of globbing workout files itself. Corpus snapshots are constructed
only by ``corpus.corpus_snapshot``. If row generation or fingerprinting
raises, the refresh rolls back or skips that unit, then retries it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Protocol

from fitdocs.compose.types import ChannelProvenance
from fitdocs.index.schema import TableSpec
from fitdocs.load.render import LoadPayload
from fitdocs.metrics.types import AthleteInputs, DerivedMetrics
from fitdocs.model import Activity

SqlValue = str | int | float | bool | date | datetime | tuple[str, ...] | None
Row = tuple[SqlValue, ...]
Rows = Mapping[str, Sequence[Row]]

LoadStatus = Literal["computed", "unsupported", "not_computed", "unreadable"]


@dataclass(frozen=True)
class LoadRegionReading:
    status: LoadStatus
    payload: LoadPayload | None


@dataclass(frozen=True)
class PageDocument:
    page_key: str
    path: str
    text: str
    frontmatter: Mapping[str, object]
    sources: tuple[str, ...]
    load: LoadRegionReading


@dataclass(frozen=True)
class PageComputed:
    document: PageDocument
    activity: Activity
    metrics: DerivedMetrics
    provenance: ChannelProvenance
    athlete: AthleteInputs | None
    athlete_fingerprint: str


@dataclass(frozen=True)
class CorpusPage:
    page_key: str
    path: str
    frontmatter: Mapping[str, object]
    document_fingerprint: str


@dataclass(frozen=True)
class CorpusLeftOut:
    path: str
    document_fingerprint: str


@dataclass(frozen=True)
class CorpusSnapshot:
    data_root: Path
    pages: tuple[CorpusPage, ...]
    left_out: tuple[CorpusLeftOut, ...]
    today: date
    athlete_fingerprint: str


class DocumentProducer(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def tables(self) -> tuple[TableSpec, ...]: ...

    def rows(self, page: PageDocument) -> Rows: ...


class ComputedProducer(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def tables(self) -> tuple[TableSpec, ...]: ...

    def rows(self, page: PageComputed) -> Rows: ...


class CorpusProducer(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def tables(self) -> tuple[TableSpec, ...]: ...

    def fingerprint(self, corpus: CorpusSnapshot) -> str: ...

    def rows(self, corpus: CorpusSnapshot) -> Rows: ...
