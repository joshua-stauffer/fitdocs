"""Bounded, in-memory hand-off from the sync engine to index refresh."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from fitdocs.contract import sha_of_ref
from fitdocs.sync import RenderedPage

HANDOFF_SAMPLE_BUDGET: Final[int] = 250_000


class HandoffCollector:
    """Retain recently rendered pages up to a sample-count budget."""

    def __init__(self, budget: int = HANDOFF_SAMPLE_BUDGET) -> None:
        self._budget = budget
        self._pages: dict[str, RenderedPage] = {}
        self._sample_counts: dict[str, int] = {}
        self._retained_samples = 0

    @property
    def retained_samples(self) -> int:
        """The current sum of samples held by retained pages."""
        return self._retained_samples

    def add(self, page: RenderedPage) -> None:
        """Retain a page by its base archive SHA when it fits the budget."""
        if not page.sources:
            return
        page_key = sha_of_ref(page.sources[-1])
        if page_key is None:
            return

        if page_key in self._sample_counts:
            old_count = self._sample_counts.pop(page_key)
            self._pages.pop(page_key)
            self._retained_samples -= old_count

        sample_count = len(page.composition.activity.samples.time_s)
        if self._retained_samples + sample_count > self._budget:
            return

        self._pages[page_key] = page
        self._sample_counts[page_key] = sample_count
        self._retained_samples += sample_count

    def take(self, page_key: str, sources: Sequence[str]) -> RenderedPage | None:
        """Return the hand-off only when its source sequence still matches."""
        page = self._pages.get(page_key)
        if page is None or page.sources != tuple(sources):
            return None
        return page
