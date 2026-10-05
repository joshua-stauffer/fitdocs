"""The append-only registration point for analytics-index producers."""

from __future__ import annotations

from typing import Final

from fitdocs.index.bookkeeping import BOOKKEEPING_TABLES
from fitdocs.index.core.computed import CORE_COMPUTED
from fitdocs.index.core.documents import CORE_DOCUMENTS
from fitdocs.index.producer import ComputedProducer, CorpusProducer, DocumentProducer
from fitdocs.index.schema import ResolvedTable, resolve_tables

DOCUMENT_PRODUCERS: Final[tuple[DocumentProducer, ...]] = (CORE_DOCUMENTS,)
COMPUTED_PRODUCERS: Final[tuple[ComputedProducer, ...]] = (CORE_COMPUTED,)
CORPUS_PRODUCERS: Final[tuple[CorpusProducer, ...]] = ()


def registered_tables() -> tuple[ResolvedTable, ...]:
    """Resolve bookkeeping and every producer currently registered by tier."""
    return resolve_tables(
        DOCUMENT_PRODUCERS,
        COMPUTED_PRODUCERS,
        CORPUS_PRODUCERS,
        BOOKKEEPING_TABLES,
    )
