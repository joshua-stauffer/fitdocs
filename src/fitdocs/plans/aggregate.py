"""The package's one load aggregator: per mesocycle, the actual load summed
from the logged-workout corpus, its coverage, and the unplanned workouts
(plan-resolution spec, task 2.3). See "Aggregator
(`src/fitdocs/plans/aggregate.py`)" in `.kiro/specs/plan-resolution/design.md`
(Req 1.3, 1.4, 3.6, 4.2, 6.1-6.4, 6.7, 6.8).

Pure: no `Path`, no clock, no I/O. This module, and the `plans.reconcile`
and `plans.placement` modules this spec adds (2.4 and 3.1 append their
entries to the exemption map), may import `fitdocs.history` -- its package
root alone, never a submodule (design "Allowed Dependencies").
Imported as a whole module (`import fitdocs.history`, referenced as
`fitdocs.history.MethodologyChoice` / `fitdocs.history.partition_pages`)
rather than a `from`-import: this keeps the boundary test's forbidden-name
scan able to admit exactly the package root for this module -- a real
`fitdocs.history.<submodule>` import stays forbidden for every module,
this one included (the exemption map this task introduces in
`tests/plans/test_boundary.py`).

The history package's `partition_pages` is the only methodology logic this
module uses; nothing about methodology selection or exclusion is
re-implemented here. A load is read off `LoggedWorkout.load` and summed --
never computed, never defaulted to zero when absent.
"""

from __future__ import annotations

from dataclasses import dataclass

import fitdocs.history
from fitdocs.plans.corpus import Corpus, LoggedWorkout
from fitdocs.plans.model import Block

__all__ = [
    "MesocycleLoad",
    "aggregate_mesocycles",
]


def _require_load(page: LoggedWorkout) -> float:
    """`page.load`, or a raised `ValueError` when it is `None` -- `total`'s
    own refusal to fabricate a `0` for a `scored` page that is out of
    contract (a hand-built `MesocycleLoad`; `aggregate_mesocycles` itself
    never puts such a page in `scored`)."""
    if page.load is None:
        raise ValueError("a scored page carries no load")
    return page.load


@dataclass(frozen=True)
class MesocycleLoad:
    """One mesocycle's actual-load picture: the dated workouts in its
    window, their partition under the chosen methodology, and the
    workouts in the window no block row claims (Req 1.3, 1.4, 3.6, 4.2,
    6.1-6.4, 6.7, 6.8).

    `pages` holds every dated workout in `[starts, ends]` regardless of
    whether any block row claims it (design's own postcondition: the
    block's rows never affect `pages`). `scored`, `unscored` and
    `excluded` are all empty when `methodology is None` (no methodology
    could be chosen); with a `choice`, they are all empty only when the
    mesocycle's window holds no dated page at all. `unplanned` is a subset
    of `pages`, in `pages`' own order (which is already
    `LoggedWorkout.order_key` order, since `pages` is read straight off
    the corpus).
    """

    number: int
    target: float | None
    methodology: str | None  # the chosen one, or None when none could be chosen
    pages: tuple[LoggedWorkout, ...]
    #: Every page here carries a load: `aggregate_mesocycles` is the only
    #: production call site this dataclass has, and it builds `scored` by
    #: filtering on `page.load is not None`. A hand-built `MesocycleLoad`
    #: that violates this (a `scored` page with `load is None`) is out of
    #: contract; `total` below raises `ValueError` rather than silently
    #: dropping such a page, since production code never produces one but
    #: CLAUDE.md's hard rule against a fabricated `0` still applies.
    scored: tuple[LoggedWorkout, ...]
    unscored: tuple[LoggedWorkout, ...]
    excluded: tuple[LoggedWorkout, ...]  # scored under another methodology
    unplanned: tuple[LoggedWorkout, ...]

    @property
    def total(self) -> float | None:
        """The sum of `scored`'s own loads, or `None` when `scored` is
        empty (Req 6.4) -- never a fabricated `0`. Raises `ValueError` if
        any `scored` page carries no load: out of contract for a
        `MesocycleLoad` built by `aggregate_mesocycles`, which only ever
        puts a page with a load in `scored`."""
        if not self.scored:
            return None
        return sum(_require_load(page) for page in self.scored)

    @property
    def lower_bound(self) -> bool:
        """Whether `total` understates the mesocycle's true load: some
        `total` exists and at least one considered workout is unscored
        (Req 6.3)."""
        return self.total is not None and bool(self.unscored)

    @property
    def considered(self) -> int:
        """`scored` plus `unscored` -- never `excluded` (Req 6.2)."""
        return len(self.scored) + len(self.unscored)

    @property
    def percent_of_target(self) -> int | None:
        """The integer percent of `target` that `total` represents, or
        `None` when either is absent (Req 6.5's number)."""
        if self.target is None or self.total is None:
            return None
        return round(100 * self.total / self.target)


def aggregate_mesocycles(
    block: Block,
    corpus: Corpus,
    *,
    claimed: frozenset[str],
    choice: fitdocs.history.MethodologyChoice | None,
) -> tuple[MesocycleLoad, ...]:
    """One `MesocycleLoad` per entry of `block.mesocycles`, in the same
    ascending order (Req 1.3, 1.4, 3.6, 4.2, 6.1-6.4, 6.7, 6.8).

    Per mesocycle: `pages = corpus.within(starts, ends)` (dated pages only;
    unknown-sport pages included). With `choice` given, `pages` is split by
    `fitdocs.history.partition_pages` under that choice into `included` and
    `excluded`; `included` further splits into `scored` (`load is not
    None`) and `unscored` (the rest) by this function alone -- reading
    `load`, never computing it. Without a `choice`, every partition is
    empty and `methodology` is `None`. `unplanned` is every page in the
    window whose stem is absent from `claimed`.
    """
    results = []
    for mesocycle in block.mesocycles:
        pages = corpus.within(mesocycle.starts, mesocycle.ends)

        if choice is not None:
            included, excluded = fitdocs.history.partition_pages(pages, choice)
            scored = tuple(page for page in included if page.load is not None)
            unscored = tuple(page for page in included if page.load is None)
            methodology: str | None = choice.methodology
        else:
            scored = ()
            unscored = ()
            excluded = ()
            methodology = None

        unplanned = tuple(page for page in pages if page.stem not in claimed)

        results.append(
            MesocycleLoad(
                number=mesocycle.number,
                target=mesocycle.target_load,
                methodology=methodology,
                pages=pages,
                scored=scored,
                unscored=unscored,
                excluded=excluded,
                unplanned=unplanned,
            )
        )
    return tuple(results)
