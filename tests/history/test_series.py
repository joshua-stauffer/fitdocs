"""Tests for `fitdocs.history.series` (load-history spec). See the
"SeriesAssembly (`src/fitdocs/history/series.py`)" component in
`.kiro/specs/load-history/design.md`.

`tests/history/test_series.py` carries one headed section per task: this
file currently holds only task 3.2's "methodology" section. Fixtures build
`PageRecord`s directly (the type task 3.1 already owns and tests through its
own real-frontmatter fixtures) rather than writing a page tree, because this
module is pure and never touches the filesystem.
"""

from __future__ import annotations

from datetime import date

from fitdocs.history.documents import PageRecord
from fitdocs.history.series import (
    MethodologyChoice,
    MethodologyProblem,
    partition_pages,
    select_methodology,
)

# ---------------------------------------------------------------------------
# methodology (task 3.2)
# ---------------------------------------------------------------------------


def _page(
    path: str,
    day: date,
    methodology: str | None,
    load: float | None = None,
) -> PageRecord:
    """A `PageRecord` with only the fields `series.py` reads populated
    meaningfully; `load` defaults to `1.0` whenever a `methodology` is given,
    preserving the 3.1 invariant `load is None` iff `methodology is None`."""
    if methodology is not None and load is None:
        load = 1.0
    return PageRecord(
        path=path,
        day=day,
        load=load,
        methodology=methodology,
        effort=None,
        tag_problem=None,
    )


_D1 = date(2024, 1, 1)
_D2 = date(2024, 1, 2)
_D3 = date(2024, 1, 3)


def test_single_methodology_is_inferred() -> None:
    pages = [
        _page("a.md", _D1, "banister"),
        _page("b.md", _D2, "banister"),
    ]
    result = select_methodology(pages, requested=None, configured=None)
    assert result == MethodologyChoice("banister", "inferred", ())


def test_methodology_configured_wins_with_two_observed() -> None:
    pages = [_page(f"old{i}.md", _D1, "old") for i in range(3)] + [
        _page(f"new{i}.md", _D2, "new") for i in range(5)
    ]
    result = select_methodology(pages, requested=None, configured="old")
    assert isinstance(result, MethodologyChoice)
    assert result.methodology == "old"
    assert result.source == "configured"
    assert result.excluded == (("new", 5),)


def test_methodology_requested_wins_with_two_observed() -> None:
    pages = [_page(f"old{i}.md", _D1, "old") for i in range(3)] + [
        _page(f"new{i}.md", _D2, "new") for i in range(5)
    ]
    result = select_methodology(pages, requested="new", configured=None)
    assert isinstance(result, MethodologyChoice)
    assert result.methodology == "new"
    assert result.source == "requested"
    assert result.excluded == (("old", 3),)


def test_methodology_requested_beats_configured_when_both_set_and_differ() -> None:
    """Confounded-fixture defense: `requested` and `configured` differ, and
    the two observed methodologies carry different counts, so a precedence
    swap (configured wins) would pick a different, wrong methodology than
    this test's `requested="alpha"` -- verified directly by mutation."""
    pages = [_page(f"alpha{i}.md", _D1, "alpha") for i in range(2)] + [
        _page(f"beta{i}.md", _D2, "beta") for i in range(4)
    ]
    result = select_methodology(pages, requested="alpha", configured="beta")
    assert isinstance(result, MethodologyChoice)
    assert result.methodology == "alpha"
    assert result.source == "requested"
    # `excluded` must be computed against the *chosen* methodology
    # ("alpha", the requested one), not against `configured` -- a swap
    # would exclude "alpha" (the chosen one) instead of "beta".
    assert result.excluded == (("beta", 4),)


def test_methodology_two_with_neither_is_an_ambiguous_problem() -> None:
    """Different counts (2 vs 5) so a most-common fallback is a real,
    detectably-wrong alternative to the problem this rule must return."""
    pages = [_page(f"jog{i}.md", _D1, "jog") for i in range(2)] + [
        _page(f"cycle{i}.md", _D2, "cycle") for i in range(5)
    ]
    result = select_methodology(pages, requested=None, configured=None)
    assert isinstance(result, MethodologyProblem)
    assert "'cycle' (5 pages)" in result.detail
    assert "'jog' (2 pages)" in result.detail
    # Pins the listed order too (name-ascending, "cycle" before "jog"): the
    # insertion order here is "jog" then "cycle", so a dropped `sorted()` in
    # `_methodology_list` would leave "jog" ahead of "cycle" instead.
    assert result.detail.index("'cycle'") < result.detail.index("'jog'")
    # The action must name both a CLI flag and the config keys that resolve
    # the problem (Req 4.4 "how to choose one"; design.md ~975, ~1411).
    assert "--methodology" in result.detail
    assert "[history].methodology" in result.detail


def test_methodology_requested_id_absent_from_archive_is_a_problem() -> None:
    pages = [_page("a.md", _D1, "banister")]
    result = select_methodology(pages, requested="tss", configured=None)
    assert isinstance(result, MethodologyProblem)
    assert "'tss'" in result.detail
    assert "'banister' (1 pages)" in result.detail
    # The action this branch names: choose one of the present methodologies.
    assert "Choose one of the present methodologies" in result.detail


def test_methodology_configured_id_absent_from_archive_is_a_problem() -> None:
    pages = [_page("a.md", _D1, "banister")]
    result = select_methodology(pages, requested=None, configured="tss")
    assert isinstance(result, MethodologyProblem)
    assert "'tss'" in result.detail
    assert "'banister' (1 pages)" in result.detail
    # The action this branch names: the config keys and the CLI flag.
    assert "[load].default_calculator" in result.detail
    assert "--methodology" in result.detail


def test_methodology_configured_id_absent_with_no_methodology_observed_at_all() -> None:
    """`configured` names an id, but the archive's pages record no
    methodology at all (unscored-only archive) -- the "methodologies
    present: ." fragment must not appear, and the only followable action
    (record loads first) must."""
    pages = [
        _page("a.md", _D1, None),
        _page("b.md", _D2, None),
    ]
    result = select_methodology(pages, requested=None, configured="banister")
    assert isinstance(result, MethodologyProblem)
    assert "present: ." not in result.detail
    assert "no page in the archive records a methodology" in result.detail
    assert "fitdocs load" in result.detail


def test_methodology_requested_id_absent_with_no_methodology_observed_at_all() -> None:
    """`requested` names an id, but the archive's pages record no
    methodology at all (unscored-only archive) -- the "methodologies
    present: ." fragment must not appear, the "record loads first" action
    must, and the *other* absent-id action (naming present methodologies to
    choose from) must not, since there are none to choose from."""
    pages = [
        _page("a.md", _D1, None),
        _page("b.md", _D2, None),
    ]
    result = select_methodology(pages, requested="x", configured=None)
    assert isinstance(result, MethodologyProblem)
    assert "present: ." not in result.detail
    assert "no page in the archive records a methodology" in result.detail
    assert "fitdocs load" in result.detail
    assert "Choose one of the present methodologies" not in result.detail


def test_methodology_archive_of_unscored_pages_only_is_a_problem() -> None:
    pages = [
        _page("a.md", _D1, None),
        _page("b.md", _D2, None),
    ]
    result = select_methodology(pages, requested=None, configured=None)
    assert isinstance(result, MethodologyProblem)


def test_excluded_is_sorted_by_methodology_name() -> None:
    """Observed in an order that is *not* already alphabetical, and with the
    alphabetically-first methodology carrying the *smaller* count (1 vs 3):
    name-ascending order yields `(("alpha", 1), ("zulu", 3))`, while a
    count-descending fallback (e.g. `Counter.most_common()`) would yield the
    reverse -- so the two orderings are distinguishable, not confounded."""
    pages = (
        [_page(f"z{i}.md", _D1, "zulu") for i in range(3)]
        + [_page("a.md", _D2, "alpha")]
        + [_page("m.md", _D3, "mango")]
    )
    result = select_methodology(pages, requested="mango", configured=None)
    assert isinstance(result, MethodologyChoice)
    assert result.excluded == (("alpha", 1), ("zulu", 3))


def test_methodology_partition_includes_chosen_and_unscored_excludes_other() -> None:
    """Fixture order deliberately matches neither day order nor path order,
    for both `included` and `excluded`:

    - `included`: `chosen` is the latest day (`_D3`) and the lexically later
      path (`z-chosen.md`), but is listed first; `unscored` is the earliest
      day (`_D1`) and lexically earlier path (`a-unscored.md`). A
      `partition_pages` that re-sorted `included` by day, or by path, would
      return `(unscored, chosen)` here instead of `(chosen, unscored)`.
    - `excluded`: `other2` (`y-other.md`, `_D2`) is listed before `other`
      (`b-other.md`, `_D1`) even though `other`'s path sorts earlier and its
      day is earlier. A `partition_pages` that re-sorted `excluded` by path,
      or by day, would return `(other, other2)` here instead of the input
      order `(other2, other)`.
    """
    chosen = _page("z-chosen.md", _D3, "banister")
    unscored = _page("a-unscored.md", _D1, None)
    other2 = _page("y-other.md", _D2, "tss")
    other = _page("b-other.md", _D1, "tss")
    choice = MethodologyChoice("banister", "inferred", (("tss", 2),))

    included, excluded = partition_pages([chosen, unscored, other2, other], choice)

    assert included == (chosen, unscored)
    assert excluded == (other2, other)
