"""Pure computation from scanned pages to the daily series, the weekly
table, coverage and the criterion-point report (load-history spec). See the
"SeriesAssembly (`src/fitdocs/history/series.py`)" component in
`.kiro/specs/load-history/design.md`.

This module is created by task 3.2 and extended by 3.3, 3.4 and 3.5 in that
order; each task adds only its own functions. Task 3.2 adds methodology
resolution and the partition it drives (Req 4.1-4.6):

- `select_methodology` is the pure selection rule: an explicitly requested
  methodology beats a configured one, which beats a single methodology
  observed across the archive. More than one methodology observed with
  nothing requested or configured, and a requested or configured identifier
  no page records, each yield a `MethodologyProblem` -- never a guess and
  never a silent majority ("never a guess" is design.md's wording; "never a
  silent majority" is tasks.md's). The case of nothing
  requested, nothing configured, and *no* methodology observed at all (an
  archive of unscored pages only) is governed by Req 1.10 -- "complete
  without reporting a failure" -- which `HistoryEngine` (task 5.2) satisfies
  by gating on "no page records a load" *before* calling this function, so
  this function's own empty-counts branch is never the engine's path to a
  configuration exit. It still returns a `MethodologyProblem` here,
  defensively: there is no id available to report as chosen under any of the
  three `MethodologyChoice.source` values, and a fabricated choice would be
  worse than an unreachable-in-practice problem.
- `partition_pages` splits the archive by the chosen methodology: a page
  recording the chosen methodology, and a page recording no load at all,
  are included; any page recording a different methodology is excluded.

No module in this package names a clock function, imports a YAML parser, or
spells the forbidden reference-docs path (package-wide rules the constant
guard checks independently). This module holds no bare numeric literal at all --
every count comparison below is done either by plain truthiness on the
`Counter` itself, or through structural pattern matching on a *sorted* list of
observed methodology names, never through a length or an index literal.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from fitdocs.history.documents import PageRecord

__all__ = [
    "MethodologyChoice",
    "MethodologyProblem",
    "partition_pages",
    "select_methodology",
]


@dataclass(frozen=True)
class MethodologyChoice:
    """The one methodology a run's series is summed under, and how it was
    chosen (Req 4.1-4.3, 4.6).

    `source` names which of the three inputs produced `methodology`, so the
    page can say the methodology was inferred rather than configured (Req
    4.3). `excluded` is every *other* observed methodology and its page
    count, sorted by methodology name so the report renders identically
    every run (Req 4.6) -- the same information `partition_pages` uses to
    build the actual excluded `PageRecord`s.
    """

    methodology: str
    source: Literal["requested", "configured", "inferred"]
    excluded: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class MethodologyProblem:
    """The archive's pages do not resolve to one methodology (Req 4.4, 4.5).

    `detail` names every methodology found with its page count and the
    action that resolves the problem -- never a guess, never a silent
    majority.
    """

    detail: str


def _observed_counts(pages: Sequence[PageRecord]) -> Counter[str]:
    """How many pages record each methodology, over pages that record a
    load at all (`PageRecord.methodology is not None`, the 3.1 invariant
    that `load is None` iff `methodology is None`)."""
    return Counter(page.methodology for page in pages if page.methodology is not None)


def _methodology_list(counts: Counter[str]) -> str:
    """Every observed methodology and its page count, sorted by name, in
    the fixed prose form every `MethodologyProblem.detail` embeds."""
    return ", ".join(
        f"{name!r} ({count} pages)" for name, count in sorted(counts.items())
    )


def _excluded(counts: Counter[str], chosen: str) -> tuple[tuple[str, int], ...]:
    """Every observed methodology other than `chosen`, sorted by name."""
    return tuple(
        (name, count) for name, count in sorted(counts.items()) if name != chosen
    )


def _present_clause(counts: Counter[str]) -> str:
    """The clause naming what is actually present, kept coherent when
    `counts` is empty: `_methodology_list` on an empty `Counter` renders as
    an empty string, so "methodologies present: ." is never emitted -- an
    archive that records no methodology at all says so plainly instead."""
    if not counts:
        return "no page in the archive records a methodology"
    return f"methodologies present: {_methodology_list(counts)}"


def select_methodology(
    pages: Sequence[PageRecord],
    *,
    requested: str | None,
    configured: str | None,
) -> MethodologyChoice | MethodologyProblem:
    """Resolve the one methodology the series is summed under (Req 4.1-4.5).

    Precedence: `requested` beats `configured` beats a single methodology
    observed across `pages`. A `requested` or `configured` identifier that
    no page records is a `MethodologyProblem` naming every methodology
    actually present and its count (Req 4.5) -- resolved before the
    observed-archive rule even runs, because a caller-supplied identifier
    that matches no page is wrong regardless of what else the archive
    contains. More than one methodology observed with neither `requested`
    nor `configured` set is also a `MethodologyProblem` (Req 4.4). The
    degenerate case of none observed at all is governed by Req 1.10, which
    `HistoryEngine` gates before ever calling this function; this branch
    returns a `MethodologyProblem` only defensively, since there is no
    candidate id to report as `MethodologyChoice.source="inferred"`.
    """
    counts = _observed_counts(pages)

    if requested is not None:
        if requested not in counts:
            action = (
                (
                    "Choose one of the present methodologies, or record loads "
                    f"under {requested!r} before requesting it."
                )
                if counts
                else (
                    f"No methodology can be chosen until one is recorded; run "
                    f"`fitdocs load` to record loads, then request {requested!r} "
                    "again."
                )
            )
            return MethodologyProblem(
                f"requested methodology {requested!r} is recorded by no page "
                f"in the archive; {_present_clause(counts)}. {action}"
            )
        return MethodologyChoice(requested, "requested", _excluded(counts, requested))

    if configured is not None:
        if configured not in counts:
            action = (
                (
                    "Update [history].methodology or [load].default_calculator to "
                    "one of the present methodologies, or pass --methodology to "
                    "choose one explicitly."
                )
                if counts
                else (
                    "No methodology can be chosen until one is recorded; run "
                    "`fitdocs load` to record loads under one first."
                )
            )
            return MethodologyProblem(
                f"configured methodology {configured!r} is recorded by no page "
                f"in the archive; {_present_clause(counts)}. {action}"
            )
        return MethodologyChoice(
            configured, "configured", _excluded(counts, configured)
        )

    match sorted(counts):
        case []:
            return MethodologyProblem(
                "no page in the archive records a methodology, and none was "
                "requested or configured. Pass --methodology, set "
                "[history].methodology, or [load].default_calculator once "
                "loads are recorded under one."
            )
        case [only]:
            return MethodologyChoice(only, "inferred", _excluded(counts, only))
        case _:
            return MethodologyProblem(
                "the archive records more than one methodology and none was "
                f"requested or configured: {_methodology_list(counts)}. Pass "
                "--methodology, or set [history].methodology or "
                "[load].default_calculator, to choose one."
            )


def partition_pages(
    pages: Sequence[PageRecord], choice: MethodologyChoice
) -> tuple[tuple[PageRecord, ...], tuple[PageRecord, ...]]:
    """Split `pages` by the chosen methodology (Req 4.1, 4.6).

    A page recording the chosen methodology, and a page recording no load
    at all (`methodology is None`), are *included*. A page recording any
    other methodology is *excluded*. Returns `(included, excluded)`, each in
    the input's own order.
    """
    included = tuple(
        page
        for page in pages
        if page.methodology is None or page.methodology == choice.methodology
    )
    excluded = tuple(
        page
        for page in pages
        if page.methodology is not None and page.methodology != choice.methodology
    )
    return included, excluded
