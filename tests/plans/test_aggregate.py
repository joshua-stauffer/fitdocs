"""Tests for the package's load aggregator (plan-resolution spec, task 2.3;
Req 1.3, 1.4, 3.6, 4.2, 6.1-6.4, 6.7, 6.8). See "Aggregator
(`src/fitdocs/plans/aggregate.py`)" in `.kiro/specs/plan-resolution/design.md`.

Every `Block` here is built from inline TOML text through the wave-1 parser
(`parse_block(text, block_id=...)`, `tests/plans/test_source.py`'s own
pattern) -- no fixture file of this task's own. Every `LoggedWorkout` is
constructed directly through `_logged(...)`, never through a filesystem
scan (`plans.corpus` is task 2.1's, already pinned by
`tests/plans/test_corpus.py`) -- so `Corpus` instances here are built by
hand too, in the same `order_key`-sorted order `scan_corpus` itself always
produces (never relied on to sort itself).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

import fitdocs.history
from fitdocs.model import Sport
from fitdocs.plans.aggregate import MesocycleLoad, aggregate_mesocycles
from fitdocs.plans.corpus import Corpus, LoggedWorkout
from fitdocs.plans.model import Block
from fitdocs.plans.source import parse_block

# ===========================================================================
# Fixture builders
# ===========================================================================


def _logged(
    stem: str,
    *,
    day: date | None,
    load: float | None = None,
    methodology: str | None = None,
    sport: Sport | None = Sport.RUN,
    start_time: datetime | None = None,
) -> LoggedWorkout:
    """One `LoggedWorkout`, constructed directly -- never through a
    filesystem scan. `sport` defaults to `Sport.RUN`; this module reads no
    sport (design's own "any sport" rule), and `TestUnknownSport` below
    passes `sport=None` to pin that. `start_time` defaults to absent; the
    same-day ordering test below passes aware values to pin `order_key`'s
    start-time component."""
    return LoggedWorkout(
        stem=stem,
        path=f"workouts/{stem}.md",
        day=day,
        sport=sport,
        modality=None,
        indoor=None,
        start_time=start_time,
        load=load,
        methodology=methodology,
    )


def _corpus(*workouts: LoggedWorkout) -> Corpus:
    """`workouts`, sorted by `order_key` -- the same order `scan_corpus`
    itself always produces, never relied on to sort itself."""
    return Corpus(workouts=tuple(sorted(workouts, key=lambda w: w.order_key)))


_TWO_MESOCYCLE_SOURCE = """\
title = "Aggregate test block"
starts = 2026-01-01
ends = 2026-01-14
goal = "A block for aggregator tests."
mesocycle_days = 7

[[mesocycle]]
number = 1
target_load = 1200
focus = "Base"

[[workout]]
id = "w1-thu"
date = 2026-01-01
sport = "Run"
title = "Easy run"
summary = "Zone 2"
prescription = "30 minutes easy."
"""


def _two_mesocycle_block() -> Block:
    return parse_block(_TWO_MESOCYCLE_SOURCE, block_id="aggregate-test-block")


_EMPTY_SOURCE = """\
title = "Empty window test block"
starts = 2026-06-01
ends = 2026-06-07
goal = "A block with no targeted mesocycle."
mesocycle_days = 7

[[workout]]
id = "w1-mon"
date = 2026-06-01
sport = "Run"
title = "Easy run"
summary = "Zone 2"
prescription = "30 minutes easy."
"""


def _empty_window_block() -> Block:
    return parse_block(_EMPTY_SOURCE, block_id="empty-window-block")


_CHOICE = fitdocs.history.MethodologyChoice("banister", "inferred", ())


# ===========================================================================
# Pins
# ===========================================================================


class TestSumAndCoverage:
    def test_three_scored_pages_sum_exactly(self) -> None:
        block = _two_mesocycle_block()
        corpus = _corpus(
            _logged("a", day=date(2026, 1, 2), load=100.0, methodology="banister"),
            _logged("b", day=date(2026, 1, 3), load=250.0, methodology="banister"),
            _logged("c", day=date(2026, 1, 4), load=430.0, methodology="banister"),
        )
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        meso1 = results[0]
        assert meso1.total == 780.0
        assert meso1.considered == 3
        assert meso1.lower_bound is False
        assert meso1.methodology == "banister"

    def test_a_fourth_unscored_page_gives_a_lower_bound_without_changing_total(
        self,
    ) -> None:
        block = _two_mesocycle_block()
        corpus = _corpus(
            _logged("a", day=date(2026, 1, 2), load=100.0, methodology="banister"),
            _logged("b", day=date(2026, 1, 3), load=250.0, methodology="banister"),
            _logged("c", day=date(2026, 1, 4), load=430.0, methodology="banister"),
            _logged("d", day=date(2026, 1, 5), load=None, methodology=None),
        )
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        meso1 = results[0]
        assert meso1.total == 780.0
        assert meso1.considered == 4
        assert meso1.lower_bound is True

    def test_a_page_under_another_methodology_is_excluded_not_considered_not_summed(
        self,
    ) -> None:
        block = _two_mesocycle_block()
        other = _logged("x", day=date(2026, 1, 2), load=999.0, methodology="tss")
        scored = _logged("a", day=date(2026, 1, 3), load=100.0, methodology="banister")
        corpus = _corpus(scored, other)
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        meso1 = results[0]
        assert meso1.total == 100.0
        assert meso1.considered == 1
        assert other not in meso1.scored
        assert other not in meso1.unscored
        assert meso1.excluded == (other,)
        # `pages` holds every dated page in the window regardless of
        # partition (design's own postcondition): `other` is excluded from
        # scoring but still in `pages`, and the three partitions together
        # account for every page in `pages`, no more and no fewer.
        assert other in meso1.pages
        assert set(meso1.scored) | set(meso1.unscored) | set(meso1.excluded) == set(
            meso1.pages
        )
        # The typed cross-check for 1.2: partition_pages returns the
        # reconciler's own LoggedWorkout instances, by identity.
        assert meso1.excluded[0] is other
        assert meso1.scored[0] is scored
        # `other`'s day (2026-01-02) precedes `scored`'s (2026-01-03), while
        # its stem ("x") sorts after `scored`'s ("a") -- so this fixture
        # distinguishes order_key order from mere stem order.
        assert meso1.unplanned == (other, scored)
        assert meso1.lower_bound is False

    def test_coverage_count_three_of_five_excludes_the_sixth_page(self) -> None:
        block = _two_mesocycle_block()
        corpus = _corpus(
            _logged("a", day=date(2026, 1, 2), load=100.0, methodology="banister"),
            _logged("b", day=date(2026, 1, 3), load=250.0, methodology="banister"),
            _logged("c", day=date(2026, 1, 4), load=430.0, methodology="banister"),
            _logged("d", day=date(2026, 1, 5), load=None, methodology=None),
            _logged("e", day=date(2026, 1, 6), load=None, methodology=None),
            _logged("f", day=date(2026, 1, 7), load=555.0, methodology="tss"),
        )
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        meso1 = results[0]
        assert len(meso1.scored) == 3
        assert len(meso1.unscored) == 2
        assert meso1.considered == 5
        assert len(meso1.excluded) == 1

    def test_only_unscored_pages_give_an_absent_total(self) -> None:
        block = _two_mesocycle_block()
        corpus = _corpus(
            _logged("a", day=date(2026, 1, 2), load=None, methodology=None),
            _logged("b", day=date(2026, 1, 3), load=None, methodology=None),
        )
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        meso1 = results[0]
        assert meso1.total is None
        assert meso1.lower_bound is False
        assert meso1.percent_of_target is None


class TestWindow:
    def test_empty_window_yields_every_field_empty_and_total_absent(self) -> None:
        block = _empty_window_block()
        corpus = _corpus(
            _logged("a", day=date(2026, 7, 1), load=200.0, methodology="banister"),
        )
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        meso1 = results[0]
        assert meso1.pages == ()
        assert meso1.scored == ()
        assert meso1.unscored == ()
        assert meso1.excluded == ()
        assert meso1.unplanned == ()
        assert meso1.total is None

    def test_each_mesocycles_own_window_is_pinned_to_its_own_bounds(self) -> None:
        """Four pages, one on each mesocycle's own first and last day
        (`_two_mesocycle_block`'s windows are 2026-01-01..01-07 and
        2026-01-08..01-14), pairwise-distinct non-symmetric loads: this
        distinguishes `mesocycle.starts`/`mesocycle.ends` from a window
        pinned to the block's own bounds, or offset by one day at either
        edge."""
        block = _two_mesocycle_block()
        meso1_first = _logged(
            "m1-first", day=date(2026, 1, 1), load=100.0, methodology="banister"
        )
        meso1_last = _logged(
            "m1-last", day=date(2026, 1, 7), load=250.0, methodology="banister"
        )
        meso2_first = _logged(
            "m2-first", day=date(2026, 1, 8), load=400.0, methodology="banister"
        )
        meso2_last = _logged(
            "m2-last", day=date(2026, 1, 14), load=800.0, methodology="banister"
        )
        corpus = _corpus(meso1_first, meso1_last, meso2_first, meso2_last)
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        assert results[0].pages == (meso1_first, meso1_last)
        assert results[0].total == 350.0
        assert results[1].pages == (meso2_first, meso2_last)
        assert results[1].total == 1200.0

    def test_a_page_on_the_last_day_is_in_and_the_day_after_is_out(self) -> None:
        block = _empty_window_block()  # bounds 2026-06-01..2026-06-07
        on_last_day = _logged(
            "last", day=date(2026, 6, 7), load=100.0, methodology="banister"
        )
        day_after = _logged(
            "after", day=date(2026, 6, 8), load=100.0, methodology="banister"
        )
        corpus = _corpus(on_last_day, day_after)
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        meso1 = results[0]
        assert on_last_day in meso1.pages
        assert day_after not in meso1.pages


class TestUnknownSport:
    def test_an_unknown_sport_page_is_included_scored_and_summed(self) -> None:
        block = _two_mesocycle_block()
        unknown_sport = _logged(
            "unknown-sport",
            day=date(2026, 1, 2),
            load=150.0,
            methodology="banister",
            sport=None,
        )
        corpus = _corpus(unknown_sport)
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        meso1 = results[0]
        assert unknown_sport in meso1.pages
        assert unknown_sport in meso1.scored
        assert meso1.total == 150.0


class TestUnplanned:
    def test_claimed_and_override_claimed_stems_are_absent_unclaimed_is_present(
        self,
    ) -> None:
        block = _two_mesocycle_block()
        claimed_direct = _logged(
            "claimed-direct", day=date(2026, 1, 2), load=110.0, methodology="banister"
        )
        claimed_override = _logged(
            "claimed-override",
            day=date(2026, 1, 3),
            load=230.0,
            methodology="banister",
        )
        unclaimed = _logged(
            "unclaimed", day=date(2026, 1, 4), load=370.0, methodology="banister"
        )
        corpus = _corpus(claimed_direct, claimed_override, unclaimed)
        results = aggregate_mesocycles(
            block,
            corpus,
            claimed=frozenset({"claimed-direct", "claimed-override"}),
            choice=_CHOICE,
        )
        meso1 = results[0]
        assert [w.stem for w in meso1.unplanned] == ["unclaimed"]
        assert meso1.total == 710.0
        assert meso1.considered == 3
        assert claimed_direct in meso1.scored
        assert claimed_override in meso1.scored

    def test_unplanned_is_reported_in_order_key_order_not_stem_order(
        self,
    ) -> None:
        """Stems named opposite to day order (round-2 lesson: a set-equality
        fixture cannot see a reversal): the earlier day carries the
        alphabetically later stem, so a list-equality check on `unplanned`
        distinguishes `order_key` order from mere stem order. (`_corpus`
        itself always sorts by `order_key` regardless of insertion order --
        that ordering is not this test's to demonstrate, so the workouts
        are passed to it in the order opposite the expected output, to
        make no claim about insertion order at all.)"""
        block = _two_mesocycle_block()
        earlier_day_later_stem = _logged(
            "z-early-day", day=date(2026, 1, 2), load=None, methodology=None
        )
        later_day_earlier_stem = _logged(
            "a-late-day", day=date(2026, 1, 3), load=None, methodology=None
        )
        corpus = _corpus(later_day_earlier_stem, earlier_day_later_stem)
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        meso1 = results[0]
        assert [w.stem for w in meso1.unplanned] == [
            "z-early-day",
            "a-late-day",
        ]

    def test_unplanned_on_one_day_follows_start_time_not_stem(self) -> None:
        """Two same-day pages whose start times run opposite to their stems:
        `order_key`'s start-time component decides, so a day-then-stem sort
        (which the previous test cannot tell from `order_key`) reports them
        reversed. Passed to `_corpus` in the order opposite the expected
        output."""
        block = _two_mesocycle_block()
        later_start_earlier_stem = _logged(
            "a-late-start",
            day=date(2026, 1, 2),
            start_time=datetime(2026, 1, 2, 18, 0, tzinfo=UTC),
        )
        earlier_start_later_stem = _logged(
            "z-early-start",
            day=date(2026, 1, 2),
            start_time=datetime(2026, 1, 2, 6, 0, tzinfo=UTC),
        )
        corpus = _corpus(later_start_earlier_stem, earlier_start_later_stem)
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        meso1 = results[0]
        assert [w.stem for w in meso1.unplanned] == [
            "z-early-start",
            "a-late-start",
        ]

    def test_an_unmatched_page_still_counts_toward_the_sum(self) -> None:
        """The block's rows never affect `pages`: a page no row claims is
        still scored and summed (only `unplanned` differs)."""
        block = _two_mesocycle_block()
        unmatched = _logged(
            "unmatched-stem", day=date(2026, 1, 2), load=444.0, methodology="banister"
        )
        corpus = _corpus(unmatched)
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        meso1 = results[0]
        assert meso1.total == 444.0
        assert unmatched in meso1.scored
        assert meso1.unplanned == (unmatched,)


class TestNoChoice:
    def test_no_choice_every_partition_is_empty_but_pages_and_total_is_absent(
        self,
    ) -> None:
        block = _two_mesocycle_block()
        page = _logged("a", day=date(2026, 1, 2), load=100.0, methodology="banister")
        corpus = _corpus(page)
        results = aggregate_mesocycles(block, corpus, claimed=frozenset(), choice=None)
        meso1 = results[0]
        assert len(meso1.pages) == 1
        assert meso1.scored == ()
        assert meso1.unscored == ()
        assert meso1.excluded == ()
        assert meso1.total is None
        assert meso1.methodology is None
        # `considered` is scored plus unscored -- both empty here -- never
        # the page count: `len(pages) - len(excluded)` would read 1.
        assert meso1.considered == 0
        # With no `choice`, `unplanned` still derives from `pages` and
        # `claimed` alone: the unclaimed page here is `unplanned` even
        # though every partition is empty.
        assert meso1.unplanned == (page,)


class TestPercentOfTarget:
    def test_1180_of_1200_is_98(self) -> None:
        block = _two_mesocycle_block()
        corpus = _corpus(
            _logged("a", day=date(2026, 1, 2), load=700.0, methodology="banister"),
            _logged("b", day=date(2026, 1, 3), load=480.0, methodology="banister"),
        )
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        meso1 = results[0]
        assert meso1.total == 1180.0
        assert meso1.percent_of_target == 98

    def test_1195_of_1200_rounds_up_to_100(self) -> None:
        block = _two_mesocycle_block()
        corpus = _corpus(
            _logged("a", day=date(2026, 1, 2), load=700.0, methodology="banister"),
            _logged("b", day=date(2026, 1, 3), load=495.0, methodology="banister"),
        )
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        meso1 = results[0]
        assert meso1.total == 1195.0
        assert meso1.percent_of_target == 100

    def test_percent_is_absent_without_a_target(self) -> None:
        block = _two_mesocycle_block()
        corpus = _corpus(
            _logged("a", day=date(2026, 1, 9), load=700.0, methodology="banister"),
        )
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        meso2 = results[1]
        assert meso2.target is None
        assert meso2.percent_of_target is None


class TestAscendingOrder:
    def test_one_entry_per_mesocycle_ascending_number(self) -> None:
        block = _two_mesocycle_block()
        corpus = _corpus()
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        assert isinstance(results, tuple)
        assert [m.number for m in results] == [1, 2]
        assert all(isinstance(m, MesocycleLoad) for m in results)


class TestUndatedPages:
    def test_an_undated_page_appears_in_no_field_at_all(self) -> None:
        """`corpus.within` never returns an undated page (Req 1.3): an
        undated, unclaimed page is absent from `pages`, and therefore from
        every field derived from `pages` -- `scored`, `unscored`,
        `excluded` and `unplanned` alike."""
        block = _two_mesocycle_block()
        undated = _logged("undated", day=None, load=500.0, methodology="banister")
        dated = _logged("a", day=date(2026, 1, 2), load=100.0, methodology="banister")
        corpus = _corpus(undated, dated)
        results = aggregate_mesocycles(
            block, corpus, claimed=frozenset(), choice=_CHOICE
        )
        meso1 = results[0]
        assert undated not in meso1.pages
        assert undated not in meso1.scored
        assert undated not in meso1.unscored
        assert undated not in meso1.excluded
        assert undated not in meso1.unplanned


class TestOutOfContractScoredPage:
    def test_a_hand_built_scored_page_with_no_load_raises_rather_than_fabricating_zero(
        self,
    ) -> None:
        """`total`'s own refusal to fabricate a `0`: a `MesocycleLoad` that
        violates its own `scored` contract (never producible by
        `aggregate_mesocycles` itself) must raise, not silently drop the
        offending page."""
        bad_scored = _logged("bad", day=date(2026, 1, 2), load=None, methodology=None)
        meso = MesocycleLoad(
            number=1,
            target=None,
            methodology="banister",
            pages=(bad_scored,),
            scored=(bad_scored,),
            unscored=(),
            excluded=(),
            unplanned=(),
        )
        with pytest.raises(ValueError):
            _ = meso.total
