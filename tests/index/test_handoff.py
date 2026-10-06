"""Tests for the bounded sync-to-index rendered-page hand-off."""

from __future__ import annotations

import inspect
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Final, get_type_hints

from fitdocs.compose.types import ChannelProvenance, Composition, SourceContribution
from fitdocs.identity.kinds import SourceKind
from fitdocs.index import handoff as handoff_module
from fitdocs.index.handoff import HANDOFF_SAMPLE_BUDGET, HandoffCollector
from fitdocs.layout import source_ref
from fitdocs.metrics.types import AthleteInputs, DerivedMetrics
from fitdocs.sync import RenderedPage
from tests.compose.builders import make_activity


def test_importing_handoff_does_not_import_sync_engine() -> None:
    script = """
import sys
assert 'fitdocs.sync' not in sys.modules
import fitdocs.index.handoff
assert 'fitdocs.sync' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=Path(__file__).parents[2],
    )
    assert completed.returncode == 0, completed.stderr


def _page(
    doc_ref: str,
    sha: str,
    sample_count: int,
    *,
    sources: tuple[str, ...] | None = None,
    athlete: AthleteInputs | None = None,
) -> RenderedPage:
    activity = make_activity(
        start=datetime(2024, 1, 2),
        offsets=tuple(float(index) for index in range(sample_count)),
        sha256=sha,
    )
    contribution = SourceContribution(
        sha256=sha,
        kind=SourceKind.ORIGINAL,
        manufacturer="synthetic-maker",
        devices=(),
        channels=(),
        alignment=None,
    )
    composition = Composition(
        activity=activity,
        provenance=ChannelProvenance(base=contribution, extras=()),
    )
    return RenderedPage(
        doc_ref=doc_ref,
        sources=sources if sources is not None else (source_ref(sha),),
        composition=composition,
        metrics=DerivedMetrics(),
        athlete=athlete,
    )


def test_public_budget_and_collector_contract() -> None:
    assert HANDOFF_SAMPLE_BUDGET == 250_000
    assert get_type_hints(handoff_module)["HANDOFF_SAMPLE_BUDGET"] == Final[int]
    assert inspect.signature(HandoffCollector).parameters["budget"].default == 250_000
    assert get_type_hints(HandoffCollector.__init__) == {
        "budget": int,
        "return": type(None),
    }
    assert get_type_hints(
        HandoffCollector.add, localns={"RenderedPage": RenderedPage}
    ) == {
        "page": RenderedPage,
        "return": type(None),
    }
    assert get_type_hints(
        HandoffCollector.take, localns={"RenderedPage": RenderedPage}
    ) == {
        "page_key": str,
        "sources": Sequence[str],
        "return": RenderedPage | None,
    }
    retained = inspect.getattr_static(HandoffCollector, "retained_samples")
    assert isinstance(retained, property)
    assert retained.fset is None
    assert get_type_hints(retained.fget) == {"return": int}


def test_admission_includes_exact_budget_and_drops_one_over() -> None:
    collector = HandoffCollector(budget=4)
    three_samples = _page("workouts/first.md", "1" * 64, 3)
    one_sample = _page("workouts/second.md", "2" * 64, 1)
    over_budget = _page("workouts/third.md", "3" * 64, 1)

    collector.add(three_samples)
    collector.add(one_sample)
    assert collector.retained_samples == 4
    assert collector.take("2" * 64, one_sample.sources) is one_sample

    collector.add(over_budget)

    assert collector.retained_samples == 4
    assert collector.take("3" * 64, over_budget.sources) is None
    assert collector.take("1" * 64, three_samples.sources) is three_samples


def test_repeated_base_replaces_and_adjusts_count_without_losing_other_entries() -> (
    None
):
    collector = HandoffCollector(budget=6)
    first = _page("workouts/first.md", "a" * 64, 3)
    other = _page("workouts/other.md", "b" * 64, 2)
    moved = _page("workouts/renamed.md", "a" * 64, 4)
    replacement = _page("workouts/renamed-again.md", "a" * 64, 1)

    collector.add(first)
    collector.add(other)
    assert collector.retained_samples == 5

    collector.add(moved)
    assert collector.retained_samples == 6
    assert collector.take("a" * 64, moved.sources) is moved

    collector.add(replacement)
    assert collector.retained_samples == 3
    assert collector.take("a" * 64, replacement.sources) is replacement
    assert collector.take("b" * 64, other.sources) is other


def test_moved_doc_ref_is_found_by_the_unchanged_base_sha() -> None:
    collector = HandoffCollector(budget=8)
    original = _page("workouts/old-name.md", "d" * 64, 2)
    moved = _page("workouts/new-name.md", "d" * 64, 3)
    assert original.sources == moved.sources

    collector.add(original)
    collector.add(moved)

    assert collector.take("d" * 64, moved.sources) is moved
    assert collector.retained_samples == 3


def test_over_budget_replacement_drops_stale_entry_and_preserves_other_key() -> None:
    collector = HandoffCollector(budget=5)
    old = _page("workouts/old.md", "4" * 64, 2)
    other = _page("workouts/other.md", "5" * 64, 2)
    too_large = _page("workouts/new.md", "4" * 64, 4)

    collector.add(old)
    collector.add(other)
    assert collector.retained_samples == 4

    collector.add(too_large)

    assert collector.retained_samples == 2
    assert collector.take("4" * 64, old.sources) is None
    assert collector.take("5" * 64, other.sources) is other


def test_take_requires_exact_sources_and_unknown_base_returns_none() -> None:
    collector = HandoffCollector(budget=8)
    sources = (source_ref("c" * 64), source_ref("a" * 64))
    page = _page("workouts/current.md", "a" * 64, 2, sources=sources)
    collector.add(page)

    assert collector.take("a" * 64, list(sources)) is page
    assert collector.take("a" * 64, (source_ref("d" * 64), *sources[1:])) is None
    assert collector.take("a" * 64, tuple(reversed(sources))) is None
    assert collector.take("f" * 64, sources) is None
    assert collector.take("a" * 64, sources) is page


def test_zero_sample_page_fits_zero_budget_and_is_retrievable() -> None:
    collector = HandoffCollector(budget=0)
    empty = _page("workouts/empty.md", "e" * 64, 0)

    collector.add(empty)

    assert collector.retained_samples == 0
    assert collector.take("e" * 64, empty.sources) is empty


def test_zero_budget_rejects_positive_page_but_keeps_empty_page() -> None:
    collector = HandoffCollector(budget=0)
    empty = _page("workouts/empty.md", "e" * 64, 0)
    positive = _page("workouts/positive.md", "f" * 64, 1)
    assert len(positive.composition.activity.samples.time_s) == 1

    collector.add(empty)
    collector.add(positive)

    assert collector.retained_samples == 0
    assert collector.take("f" * 64, positive.sources) is None
    assert collector.take("e" * 64, empty.sources) is empty


def _assert_invalid_sources_preserve_capacity(sources: tuple[str, ...]) -> None:
    collector = HandoffCollector(budget=3)
    peer = _page("workouts/peer.md", "b" * 64, 2)
    invalid = _page("workouts/invalid.md", "a" * 64, 1, sources=sources)
    collector.add(peer)

    error: Exception | None = None
    try:
        collector.add(invalid)
    except Exception as caught:
        error = caught
    assert error is None
    assert collector.retained_samples == 2
    assert collector.take("b" * 64, peer.sources) is peer

    valid = _page("workouts/valid.md", "c" * 64, 1)
    collector.add(valid)
    assert collector.retained_samples == 3
    assert collector.take("c" * 64, valid.sources) is valid


def test_empty_sources_do_not_raise_or_consume_capacity() -> None:
    _assert_invalid_sources_preserve_capacity(())


def test_nonarchive_final_source_does_not_consume_capacity_or_collide() -> None:
    _assert_invalid_sources_preserve_capacity(("foreign/source.fit",))


def test_populated_rendered_page_is_retained_as_the_complete_object() -> None:
    athlete = AthleteInputs(ftp_watts=271.5, resting_hr_bpm=53, max_hr_bpm=189)
    sources = (source_ref("c" * 64), source_ref("a" * 64))
    base_page = _page("workouts/populated.md", "a" * 64, 2, sources=sources)
    metrics = DerivedMetrics(distance_m=1234.5, avg_power_w=219.25)
    base = base_page.composition.provenance.base
    donor = replace(base, sha256="c" * 64, manufacturer="distinct-donor")
    provenance = replace(base_page.composition.provenance, extras=(donor,))
    composition = replace(base_page.composition, provenance=provenance)
    page = replace(base_page, composition=composition, metrics=metrics, athlete=athlete)

    assert page.athlete is athlete
    assert page.metrics is metrics
    assert page.metrics.distance_m == 1234.5
    assert page.metrics.avg_power_w == 219.25
    assert page.composition.provenance.extras == (donor,)
    assert page.composition.activity.samples.time_s == (0.0, 1.0)

    collector = HandoffCollector(budget=2)
    collector.add(page)

    assert collector.take("a" * 64, page.sources) is page
