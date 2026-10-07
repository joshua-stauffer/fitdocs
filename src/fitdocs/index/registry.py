"""The append-only registration point for analytics-index producers."""

from __future__ import annotations

from typing import Final

from fitdocs.index.bookkeeping import BOOKKEEPING_TABLES
from fitdocs.index.core.computed import CORE_COMPUTED
from fitdocs.index.core.documents import CORE_DOCUMENTS
from fitdocs.index.derived.benchmarks import BENCHMARK_PRODUCER
from fitdocs.index.derived.blocks import BLOCK_PRODUCER
from fitdocs.index.derived.load_series import LOAD_SERIES_PRODUCER
from fitdocs.index.derived.mean_max import MEAN_MAX_PRODUCER
from fitdocs.index.producer import ComputedProducer, CorpusProducer, DocumentProducer
from fitdocs.index.schema import ResolvedTable, resolve_tables

DOCUMENT_PRODUCERS: Final[tuple[DocumentProducer, ...]] = (CORE_DOCUMENTS,)
COMPUTED_PRODUCERS: Final[tuple[ComputedProducer, ...]] = (
    CORE_COMPUTED,
    MEAN_MAX_PRODUCER,
)
CORPUS_PRODUCERS: Final[tuple[CorpusProducer, ...]] = (
    LOAD_SERIES_PRODUCER,
    BENCHMARK_PRODUCER,
    BLOCK_PRODUCER,
)


def registered_tables() -> tuple[ResolvedTable, ...]:
    """Resolve bookkeeping and every producer currently registered by tier."""
    return resolve_tables(
        DOCUMENT_PRODUCERS,
        COMPUTED_PRODUCERS,
        CORPUS_PRODUCERS,
        BOOKKEEPING_TABLES,
    )
