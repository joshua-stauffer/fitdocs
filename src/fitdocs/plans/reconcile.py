"""Run the reconciling pass through the plan pass's resolver hook
(plan-resolution spec, task 3.1). See "ReconcilePass
(`src/fitdocs/plans/reconcile.py`)" in `.kiro/specs/plan-resolution/design.md`
(Req 2.6, 4.3, 4.6, 5.1, 5.2, 5.4, 6.2, 6.6, 8.4, 8.6, 8.9).

This module, `plans.aggregate` and `plans.placement` are the only modules
of this package that import `fitdocs.history` -- this one for exactly two
names it needs by qualified access, `select_methodology` and
`load_history_settings`, plus the two record types `MethodologyChoice` and
`MethodologyProblem`; imported as the package root (`import fitdocs.history`)
rather than a `from`-import, so the boundary test's forbidden-target scan
can admit exactly this module's root import (its own exemption-map entry)
while every real `fitdocs.history.<submodule>` import stays forbidden
everywhere, this module included. `fitdocs.load.settings` is imported the
same way, for its one reader, `load_load_settings`.

`run_reconcile(data_root, *, today)` reads `fitdocs.toml` once through
`fitdocs.settings.load_settings_document`, projects `[history]` and
`[load]` through `fitdocs.history.load_history_settings` and
`fitdocs.load.settings.load_load_settings` -- their errors (both
`SettingsError` subclasses) propagate before anything else happens --
composes `configured = history.methodology or load.default_calculator`
the way `fitdocs.history.engine.run_history` does, builds a `Reconciler`
and calls `fitdocs.plans.engine.run_plan(data_root, resolve=reconciler)`.
It returns a `ReconcileReport` pairing that call's `PlanReport` with every
resolved block's `BlockReconciliation`, in the plan's own block order, and
the methodology this run chose (or the problem that kept one from being
chosen, or `None` when the resolver was never called at all because no
valid block existed to call it for).

`Reconciler.__call__` is the resolver `run_plan` calls once per valid
block, after that block's own validation and before it is rendered. On its
first call it scans the corpus (`fitdocs.plans.corpus.scan_corpus`) and
selects the methodology this whole run sums under
(`fitdocs.history.select_methodology`); every later call in the same run
reuses both. It never raises for a valid block: a `MethodologyProblem` is
carried on the block's own reconciliation and on the run's methodology,
never turned into an exception that would stop the pass Req 6.6 requires
to keep resolving every row regardless. It builds the block's
`BlockReconciliation` through `reconcile_block`, records it by the block's
own id, and returns the `Resolution` `fitdocs.plans.placement.place_resolution`
builds from it -- the value `run_plan`'s renderers actually consume.

`reconcile_block` is the pure composition the design names: `match_rows`
over the block and the corpus, `aggregate_mesocycles` over the same corpus
with the rows' claimed stems and (when one was chosen) the methodology,
and a `BlockReconciliation` built from both, carrying `match_rows`'s own
override problems verbatim. The `BlockReconciliation` type itself is
**not** defined here -- it is `plans.placement`'s (that module sits below
this one in the import order precisely so the type can live there; see
that module's own docstring), imported here and handed to the report.

No clock is read anywhere in this module: `today` is a plain `date` value
the command resolved and threads through unchanged. Nothing here opens a
file for writing, and nothing here prompts. `fitdocs.toml` is read exactly
once by this module's own call to `load_settings_document`; the file's
*second* read for a given invocation is `run_plan`'s own, an independent
call that module makes for its own `[plans]` table -- this module does not
avoid it, and does not need to, since both reads are pure and agree by
construction on an unchanged file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import fitdocs.history
import fitdocs.load.settings
from fitdocs.layout import settings_path
from fitdocs.plans.aggregate import aggregate_mesocycles
from fitdocs.plans.corpus import Corpus, scan_corpus
from fitdocs.plans.engine import PlanReport, Resolver, run_plan
from fitdocs.plans.matching import match_rows
from fitdocs.plans.model import Block
from fitdocs.plans.placement import BlockReconciliation, place_resolution
from fitdocs.plans.resolution import Resolution
from fitdocs.settings import load_settings_document

__all__ = [
    "ReconcileReport",
    "reconcile_block",
    "run_reconcile",
]


@dataclass(frozen=True)
class ReconcileReport:
    """Everything one `run_reconcile` call did or found (Req 8.6).

    `plan` is the underlying `fitdocs.plans.engine.PlanReport` `run_plan`
    itself returned. `blocks` holds one `BlockReconciliation` per block the
    resolver was actually called for -- every currently valid block, never
    an `invalid` one -- in `plan.blocks`' own order. `methodology` is the
    run's chosen `MethodologyChoice`, the `MethodologyProblem` that kept
    one from being chosen, or `None` when the resolver was never called at
    all (no valid block existed)."""

    plan: PlanReport
    blocks: tuple[BlockReconciliation, ...]
    methodology: (
        fitdocs.history.MethodologyChoice | fitdocs.history.MethodologyProblem | None
    )

    @property
    def failed(self) -> bool:
        """`plan.failed` -- any invalid, blocked or failed block -- or any
        reconciled block carrying an override problem (Req 8.9)."""
        return self.plan.failed or any(block.problems for block in self.blocks)


def reconcile_block(
    block: Block,
    corpus: Corpus,
    *,
    today: date,
    methodology: fitdocs.history.MethodologyChoice | fitdocs.history.MethodologyProblem,
) -> BlockReconciliation:
    """One block's whole reconciliation, pure (Req 2.6, 4.3, 6.2): every
    current row resolved by `match_rows`, every mesocycle's actual-load
    picture built by `aggregate_mesocycles` over the rows' claimed stems
    and, when a real `MethodologyChoice` was made, that choice -- a
    `MethodologyProblem` passes `choice=None` through to the aggregator,
    which is exactly its own documented "no methodology could be chosen"
    case (every mesocycle `not computed`). `problems` carries `match_rows`'s
    own override problems verbatim."""
    match = match_rows(block, corpus, today=today)
    choice = (
        methodology
        if isinstance(methodology, fitdocs.history.MethodologyChoice)
        else None
    )
    mesocycles = aggregate_mesocycles(
        block, corpus, claimed=match.claimed, choice=choice
    )
    return BlockReconciliation(
        block_id=block.id,
        rows=match.rows,
        mesocycles=mesocycles,
        methodology=methodology,
        problems=match.problems,
    )


class Reconciler:
    """The resolver `run_reconcile` hands to `run_plan` (Req 5.1, 5.2,
    5.4): a lazy, once-per-run corpus scan and methodology selection,
    called from the resolver's own first call rather than eagerly, so a
    run over a plan source with no valid block never scans the corpus at
    all (Req 8.4's "opens no file for it" reading extended to the corpus
    scan the design's own postcondition names)."""

    def __init__(self, data_root: Path, *, today: date, configured: str | None) -> None:
        self._data_root = data_root
        self._today = today
        self._configured = configured
        self._corpus: Corpus | None = None
        self._methodology: (
            fitdocs.history.MethodologyChoice
            | fitdocs.history.MethodologyProblem
            | None
        ) = None
        self._blocks: dict[str, BlockReconciliation] = {}

    def __call__(self, block: Block) -> Resolution:
        if self._corpus is None:
            self._corpus = scan_corpus(self._data_root)
            self._methodology = fitdocs.history.select_methodology(
                self._corpus.workouts, requested=None, configured=self._configured
            )
        assert self._corpus is not None
        assert self._methodology is not None
        reconciliation = reconcile_block(
            block, self._corpus, today=self._today, methodology=self._methodology
        )
        self._blocks[block.id] = reconciliation
        return place_resolution(block, reconciliation, self._corpus)

    @property
    def blocks(self) -> dict[str, BlockReconciliation]:
        """Every block reconciled so far, by block id -- a fresh copy each
        read, never the resolver's own mutable dict."""
        return dict(self._blocks)

    @property
    def methodology(
        self,
    ) -> fitdocs.history.MethodologyChoice | fitdocs.history.MethodologyProblem | None:
        """The run's chosen methodology, or `None` before the first
        `__call__` (no valid block resolved yet)."""
        return self._methodology


def run_reconcile(data_root: Path, *, today: date) -> ReconcileReport:
    """Run the whole reconciling pass over `data_root` and return its
    report (Req 2.6, 4.3, 4.6, 5.1, 5.2, 5.4, 6.2, 6.6, 8.4, 8.6, 8.9).

    Reads `fitdocs.toml` once, projects `[history]` and `[load]` -- either
    reader's `SettingsError` propagates before `run_plan` is ever called,
    so a malformed table writes nothing. Composes
    `configured = history.methodology or load.default_calculator`, the way
    `fitdocs.history.engine.run_history` composes the same pair for its own
    run. Calls `fitdocs.plans.engine.run_plan(data_root, resolve=Reconciler(...))`
    and returns a `ReconcileReport` pairing that call's `PlanReport` with
    every resolved block's `BlockReconciliation`, in `plan.blocks`' own
    order, and the resolver's own final `methodology` reading."""
    settings_file = settings_path(data_root)
    document = load_settings_document(data_root)
    history_settings = fitdocs.history.load_history_settings(
        document, settings_file
    )  # HistorySettingsError propagates
    load_settings = fitdocs.load.settings.load_load_settings(
        document, settings_file
    )  # LoadSettingsError propagates
    configured = history_settings.methodology or load_settings.default_calculator

    reconciler = Reconciler(data_root, today=today, configured=configured)
    resolver: Resolver = reconciler
    plan = run_plan(data_root, resolve=resolver)

    resolved = reconciler.blocks
    blocks = tuple(
        resolved[outcome.block_id]
        for outcome in plan.blocks
        if outcome.block_id in resolved
    )
    return ReconcileReport(plan=plan, blocks=blocks, methodology=reconciler.methodology)
