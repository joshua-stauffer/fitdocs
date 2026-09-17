"""Tests for the `plans` package's one corpus read (plan-resolution spec,
task 2.1; Req 1.1, 1.3, 1.4, 1.5, 1.6, 1.7). See "CorpusScan
(`src/fitdocs/plans/corpus.py`)" in `.kiro/specs/plan-resolution/design.md`.

Every fixture here is a synthetically written page tree under `tmp_path`,
built from real frontmatter fences and real `fitdocs.contract` vocabulary --
the same pattern `tests/history/test_documents.py` and
`tests/history/test_engine.py::_page` use -- and read by the actual
`scan_corpus` -> `docio.read_frontmatter` / `fitdocs.contract` pipeline. No
`.fit` file is read and no real wiki page is ever used.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

import pytest

from fitdocs import docmerge
from fitdocs.contract import DATE_KEY, LOAD_REGION
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.model import Modality, Sport
from fitdocs.plans.corpus import Corpus, LoggedWorkout, scan_corpus


def _write(root: Path, relpath: str, text: str) -> Path:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _page(
    *,
    doc_type: str = "workout",
    day: str | None = "2026-09-10",
    sport: str | None = "Run",
    modality: str | None = None,
    indoor: bool | None = None,
    start_time: str | None = None,
    load_value: float | None = None,
    load_methodology: str | None = None,
    body: str = "",
) -> str:
    """A minimal, syntactically valid fitdocs document -- a real frontmatter
    fence and real vocabulary, matching `tests/history/test_engine.py`'s own
    `_page` fixture builder, extended with the sport/modality/indoor/
    start_time lines this corpus reads."""
    lines = ["---", "title: Test Workout", f"type: {doc_type}"]
    if day is not None:
        lines.append(f'{DATE_KEY}: "{day}"')
    if sport is not None:
        lines.append(f"sport: {sport}")
    if modality is not None:
        lines.append(f"modality: {modality}")
    if indoor is not None:
        lines.append(f"indoor: {'true' if indoor else 'false'}")
    if start_time is not None:
        lines.append(f'start_time: "{start_time}"')
    if load_value is not None:
        lines.append(f"load_value: {load_value}")
    if load_methodology is not None:
        lines.append(f"load_methodology: {load_methodology}")
    lines.append("---")
    lines.append("")
    lines.append("# Test Workout")
    if body:
        lines.append("")
        lines.append(body)
    lines.append("")
    return "\n".join(lines) + "\n"


# --- one page of every shape (Req 1.1-1.7) -------------------------------------


def test_a_full_page_reads_every_field(tmp_path: Path) -> None:
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/full.md",
        _page(
            day="2026-09-10",
            sport="Run",
            modality="run",
            indoor=True,
            start_time="2026-09-10T07:00:00-04:00",
            load_value=150.0,
            load_methodology="banister",
        ),
    )

    corpus = scan_corpus(tmp_path)

    assert corpus.workouts == (
        LoggedWorkout(
            stem="full",
            path=f"{WORKOUTS_DIR}/full.md",
            day=date(2026, 9, 10),
            sport=Sport.RUN,
            modality=Modality.RUN,
            indoor=True,
            start_time=datetime.fromisoformat("2026-09-10T07:00:00-04:00"),
            load=150.0,
            methodology="banister",
        ),
    )


def test_an_undated_page_belongs_to_no_day(tmp_path: Path) -> None:
    """Req 1.3: a page whose date could not be read is `day=None`, never a
    fabricated date."""
    _write(tmp_path, f"{WORKOUTS_DIR}/undated.md", _page(day=None))

    corpus = scan_corpus(tmp_path)

    assert len(corpus.workouts) == 1
    assert corpus.workouts[0].day is None


def test_an_unknown_sport_spelling_is_absent(tmp_path: Path) -> None:
    """Req 1.4: an unrecognized sport spelling maps to `None`, never raises,
    and the page still counts (it is still present in the corpus)."""
    _write(tmp_path, f"{WORKOUTS_DIR}/unknown-sport.md", _page(sport="Unicycling"))

    corpus = scan_corpus(tmp_path)

    assert len(corpus.workouts) == 1
    assert corpus.workouts[0].sport is None


def test_an_unknown_modality_spelling_is_absent(tmp_path: Path) -> None:
    """An unrecognized modality spelling maps to `None`, never raises, and
    never fabricates the first `Modality` enum member -- the page still
    counts (it is still present in the corpus)."""
    _write(tmp_path, f"{WORKOUTS_DIR}/unknown-modality.md", _page(modality="hopscotch"))

    corpus = scan_corpus(tmp_path)

    assert len(corpus.workouts) == 1
    assert corpus.workouts[0].modality is None


def test_a_lowercase_sport_spelling_is_absent(tmp_path: Path) -> None:
    """Req 1.4: `Sport`'s own values are title-cased (`"Run"`, not `"run"`)
    -- the raw recorded spelling is mapped by value, never case-normalised
    first, so a lowercase spelling is an unrecognized spelling, not a
    match. (Whitespace is pinned separately, by
    `test_a_padded_and_quoted_sport_spelling_is_absent`.)"""
    _write(tmp_path, f"{WORKOUTS_DIR}/lowercase-sport.md", _page(sport="run"))

    corpus = scan_corpus(tmp_path)

    assert len(corpus.workouts) == 1
    assert corpus.workouts[0].sport is None


def test_a_padded_and_quoted_sport_spelling_is_absent(tmp_path: Path) -> None:
    """Req 1.4: the raw recorded sport string is mapped by *value*, never
    stripped or normalised first -- ``sport: " Run "`` (the fixture builder
    writes ``sport: {sport}`` unquoted, so the literal quotes and padding
    below become part of the YAML-quoted string PyYAML hands back) reads as
    the five-character string ``" Run "`` (a leading and trailing space),
    not `Sport.RUN`'s own `"Run"`, so
    it is an unrecognized spelling, not a match. Named mutation:
    `Sport(value.strip())` would strip the padding first and match."""
    _write(tmp_path, f"{WORKOUTS_DIR}/padded-sport.md", _page(sport='" Run "'))

    corpus = scan_corpus(tmp_path)

    assert len(corpus.workouts) == 1
    assert corpus.workouts[0].sport is None


def test_a_capitalized_modality_spelling_is_absent(tmp_path: Path) -> None:
    """`Modality`'s own values are lowercase (e.g. `"run"`) -- the raw
    recorded spelling is mapped by value, never lowercased first, so
    ``modality: Run`` is an unrecognized spelling, not a match. Named
    mutation: `Modality(value.lower())` would lowercase it first and
    match."""
    _write(tmp_path, f"{WORKOUTS_DIR}/capitalized-modality.md", _page(modality="Run"))

    corpus = scan_corpus(tmp_path)

    assert len(corpus.workouts) == 1
    assert corpus.workouts[0].modality is None


def test_no_modality_reads_none(tmp_path: Path) -> None:
    _write(tmp_path, f"{WORKOUTS_DIR}/no-modality.md", _page(modality=None))

    corpus = scan_corpus(tmp_path)

    assert corpus.workouts[0].modality is None


def test_no_indoor_reads_none(tmp_path: Path) -> None:
    """An absent `indoor` key reads `None`, never a fabricated `False`."""
    _write(tmp_path, f"{WORKOUTS_DIR}/no-indoor.md", _page(indoor=None))

    corpus = scan_corpus(tmp_path)

    assert corpus.workouts[0].indoor is None


def test_indoor_true_reads_true(tmp_path: Path) -> None:
    _write(tmp_path, f"{WORKOUTS_DIR}/indoor.md", _page(indoor=True))

    corpus = scan_corpus(tmp_path)

    assert corpus.workouts[0].indoor is True


def test_indoor_false_reads_false(tmp_path: Path) -> None:
    """An explicit `indoor: false` reads `False`, distinct from an absent
    key reading `None` -- the two must not collapse onto one value."""
    _write(tmp_path, f"{WORKOUTS_DIR}/outdoor.md", _page(indoor=False))

    corpus = scan_corpus(tmp_path)

    assert corpus.workouts[0].indoor is False


def test_no_start_time_reads_none(tmp_path: Path) -> None:
    _write(tmp_path, f"{WORKOUTS_DIR}/no-start.md", _page(start_time=None))

    corpus = scan_corpus(tmp_path)

    assert corpus.workouts[0].start_time is None


def test_a_naive_start_time_reads_none(tmp_path: Path) -> None:
    """`document_start_time` never guesses a timezone the document did not
    record -- a naive value is honest absence, not a fabricated offset."""
    text = _page(start_time=None).replace(
        "---\n\n# Test Workout",
        'start_time: "2026-09-10T07:00:00"\n---\n\n# Test Workout',
    )
    _write(tmp_path, f"{WORKOUTS_DIR}/naive-start.md", text)

    corpus = scan_corpus(tmp_path)

    assert corpus.workouts[0].start_time is None


def test_an_unscored_page_reads_no_load_and_no_methodology(tmp_path: Path) -> None:
    """Req 1.5: never a fabricated load of zero -- `load` and `methodology`
    are both `None` together."""
    _write(tmp_path, f"{WORKOUTS_DIR}/unscored.md", _page())

    corpus = scan_corpus(tmp_path)

    assert corpus.workouts[0].load is None
    assert corpus.workouts[0].methodology is None


def test_a_load_without_a_methodology_is_unscored(tmp_path: Path) -> None:
    """Req 1.5: a load value without a methodology beside it is unscored,
    never a load with a fabricated methodology."""
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/no-methodology.md",
        _page(load_value=120.0),
    )

    corpus = scan_corpus(tmp_path)

    assert corpus.workouts[0].load is None
    assert corpus.workouts[0].methodology is None


@pytest.mark.parametrize("methodology", ["banister", "trimp"])
def test_a_scored_page_reads_its_own_methodology(
    tmp_path: Path, methodology: str
) -> None:
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/scored-{methodology}.md",
        _page(load_value=100.0, load_methodology=methodology),
    )

    corpus = scan_corpus(tmp_path)

    assert corpus.workouts[0].load == 100.0
    assert corpus.workouts[0].methodology == methodology


# --- exclusions (Req 1.1, 1.6) --------------------------------------------------


def test_a_planned_workout_page_is_excluded(tmp_path: Path) -> None:
    """Req 1.1, 1.6: only a recognized workout document is a member of the
    corpus -- a `planned-workout` page (real vocabulary, real frontmatter
    fence) must never appear."""
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/planned.md",
        _page(doc_type="planned-workout"),
    )

    corpus = scan_corpus(tmp_path)

    assert corpus.workouts == ()


def test_a_symlink_to_a_valid_page_is_excluded(tmp_path: Path) -> None:
    """Reachability control (design.md's own phrasing): the symlink's
    *target* is itself a valid page that a scan of its own directory
    includes -- proven by the companion assertion below -- so the exclusion
    below is the only thing that can make this fixture fail."""
    target = _write(tmp_path, f"{WORKOUTS_DIR}/real.md", _page())
    if os.name == "nt":  # pragma: no cover - platform guard, not under test
        pytest.skip("symlinks require elevated privileges on this platform")
    link_path = tmp_path / WORKOUTS_DIR / "linked.md"
    link_path.symlink_to(target)

    corpus = scan_corpus(tmp_path)

    # Reachability precondition: the target itself is a valid page.
    assert corpus.by_stem("real") is not None
    assert corpus.by_stem("linked") is None
    assert [w.stem for w in corpus.workouts] == ["real"]


def test_a_non_utf8_file_is_excluded(tmp_path: Path) -> None:
    """The bad file is an otherwise-valid page (real frontmatter, would scan
    cleanly on its own) with one invalid byte spliced into its *body*, past
    the frontmatter fence -- so this discriminates a scan that reads through
    `fitdocs.docio.read_frontmatter` (which refuses an undecodable file
    outright) from a lenient decode that tolerates the bad byte and would
    still find a well-formed frontmatter fence ahead of it. The clean
    sibling file (the same bytes, minus the bad byte) is the fixture's own
    reachability precondition: it proves the fixture *would* be scanned if
    the encoding were valid, so the exclusion below is the only thing that
    can make this fixture pass."""
    path = tmp_path / WORKOUTS_DIR
    path.mkdir(parents=True, exist_ok=True)
    page_text = _page(day="2026-09-10")
    (path / "clean.md").write_bytes(page_text.encode("utf-8"))
    (path / "bad-encoding.md").write_bytes(page_text.encode("utf-8") + b"\xff\n")

    corpus = scan_corpus(tmp_path)

    # Reachability precondition: the clean sibling (same bytes, valid
    # encoding) is scanned.
    assert corpus.by_stem("clean") is not None
    assert corpus.by_stem("bad-encoding") is None
    assert [w.stem for w in corpus.workouts] == ["clean"]


def test_a_page_in_a_subdirectory_is_not_scanned(tmp_path: Path) -> None:
    """A real, otherwise-valid page sits one directory down -- the fixture
    only discriminates because the nested page is itself valid; if the scan
    ever switched from `glob` to `rglob` this page would appear."""
    _write(tmp_path, f"{WORKOUTS_DIR}/nested/buried.md", _page())
    _write(tmp_path, f"{WORKOUTS_DIR}/top-level.md", _page())

    corpus = scan_corpus(tmp_path)

    assert [w.stem for w in corpus.workouts] == ["top-level"]


def test_an_absent_workouts_directory_is_an_empty_corpus(tmp_path: Path) -> None:
    corpus = scan_corpus(tmp_path)

    assert corpus == Corpus(workouts=())


def test_two_scans_of_an_unchanged_root_are_equal(tmp_path: Path) -> None:
    """Design.md's own stated postcondition, over a multi-page fixture:
    scanning the same, unchanged root twice yields equal `Corpus` values."""
    _write(tmp_path, f"{WORKOUTS_DIR}/one.md", _page(day="2026-09-10"))
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/two.md",
        _page(day="2026-09-11", load_value=100.0, load_methodology="banister"),
    )
    _write(tmp_path, f"{WORKOUTS_DIR}/three.md", _page(day=None))

    assert scan_corpus(tmp_path) == scan_corpus(tmp_path)


# --- ordering (design.md 3.8) ---------------------------------------------------


def test_two_same_day_pages_sort_by_start_time_not_stem(tmp_path: Path) -> None:
    """Named mutation: sorting by stem alone -- dropping start time from the
    key -- would reverse this order, since the stems are named opposite to
    their start times (`zzz-early` starts before `aaa-late`)."""
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/zzz-early.md",
        _page(day="2026-09-10", start_time="2026-09-10T06:00:00-04:00"),
    )
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/aaa-late.md",
        _page(day="2026-09-10", start_time="2026-09-10T18:00:00-04:00"),
    )

    corpus = scan_corpus(tmp_path)

    assert [w.stem for w in corpus.workouts] == ["zzz-early", "aaa-late"]


def test_two_dated_pages_sort_by_day_not_stem(tmp_path: Path) -> None:
    """Named mutation: sorting by stem alone, or substituting a constant
    sentinel for `day` in the ordering key regardless of its actual value
    (which falls through to the same stem comparison, both start times
    being absent), would both red this test -- the stems here are named
    opposite to their days (`zzz-first` is the earlier day, `aaa-second`
    the later one), so either mutation sorts alphabetically by stem and
    produces `["aaa-second", "zzz-first"]`, not the by-day order asserted
    below."""
    _write(tmp_path, f"{WORKOUTS_DIR}/zzz-first.md", _page(day="2026-09-10"))
    _write(tmp_path, f"{WORKOUTS_DIR}/aaa-second.md", _page(day="2026-09-11"))

    corpus = scan_corpus(tmp_path)

    assert [w.stem for w in corpus.workouts] == ["zzz-first", "aaa-second"]


def test_undated_sorts_after_every_dated_page(tmp_path: Path) -> None:
    """Named mutation: sorting by stem alone would agree with the rule when
    an undated page's stem happens to sort after a dated page's -- the
    stems here are named opposite to the rule (`aaa-undated` would sort
    *first* by stem) so only the actual dated-before-undated rule produces
    this order."""
    _write(tmp_path, f"{WORKOUTS_DIR}/aaa-undated.md", _page(day=None))
    _write(tmp_path, f"{WORKOUTS_DIR}/zzz-dated.md", _page(day="2026-09-10"))

    corpus = scan_corpus(tmp_path)

    assert [w.stem for w in corpus.workouts] == ["zzz-dated", "aaa-undated"]


def test_missing_start_time_sorts_after_a_recorded_one_on_the_same_day(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/no-start.md",
        _page(day="2026-09-10", start_time=None),
    )
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/with-start.md",
        _page(day="2026-09-10", start_time="2026-09-10T06:00:00-04:00"),
    )

    corpus = scan_corpus(tmp_path)

    assert [w.stem for w in corpus.workouts] == ["with-start", "no-start"]


def test_order_key_ties_on_stem_when_day_and_start_time_both_agree() -> None:
    """`order_key`'s own final tiebreak (design.md 3.8) is the stem itself
    -- pinned directly against two `LoggedWorkout` records built with
    identical `day` and no `start_time`, bypassing `scan_corpus` and the
    coincidental stem-order `sorted(glob())` already produces, so this
    would catch a tiebreak dropped from the key (e.g. substituted with
    `""`, which every record shares and so leaves the pre-sort order
    undisturbed) even though the file-glob-order tests above cannot."""
    same_day = date(2026, 9, 10)
    later_stem = LoggedWorkout(
        stem="b",
        path=f"{WORKOUTS_DIR}/b.md",
        day=same_day,
        sport=None,
        modality=None,
        indoor=None,
        start_time=None,
        load=None,
        methodology=None,
    )
    earlier_stem = LoggedWorkout(
        stem="a",
        path=f"{WORKOUTS_DIR}/a.md",
        day=same_day,
        sport=None,
        modality=None,
        indoor=None,
        start_time=None,
        load=None,
        methodology=None,
    )

    ordered = sorted([later_stem, earlier_stem], key=lambda w: w.order_key)

    assert [w.stem for w in ordered] == ["a", "b"]


# --- Corpus.by_stem / on_day / within (design.md's own contract) ---------------


def test_by_stem_is_total_over_workouts(tmp_path: Path) -> None:
    _write(tmp_path, f"{WORKOUTS_DIR}/one.md", _page(day="2026-09-10"))

    corpus = scan_corpus(tmp_path)

    found = corpus.by_stem("one")
    assert found is not None
    assert found.stem == "one"
    assert corpus.by_stem("missing") is None


def test_by_stem_matches_exactly_not_by_prefix(tmp_path: Path) -> None:
    """Named mutation: matching by a `startswith` prefix rather than
    equality would make `by_stem("on")` return `one`'s record instead of
    `None`, and would make `by_stem("one")` ambiguous between `one` and
    `one-more`."""
    _write(tmp_path, f"{WORKOUTS_DIR}/one.md", _page(day="2026-09-10"))
    _write(tmp_path, f"{WORKOUTS_DIR}/one-more.md", _page(day="2026-09-11"))

    corpus = scan_corpus(tmp_path)

    found_one = corpus.by_stem("one")
    found_one_more = corpus.by_stem("one-more")
    assert found_one is not None
    assert found_one.path == f"{WORKOUTS_DIR}/one.md"
    assert found_one_more is not None
    assert found_one_more.path == f"{WORKOUTS_DIR}/one-more.md"
    assert corpus.by_stem("on") is None


def test_on_day_returns_only_that_days_workouts(tmp_path: Path) -> None:
    """Named mutation: `workout.day is None or workout.day == day` would
    admit `undated` into both days' results below -- an undated page
    belongs to no day, not to every day. `day1`'s two same-day pages also
    pin `on_day`'s own order: the stems are named opposite to their start
    times, so only an actual `workouts`-order (start-time) traversal
    produces `["zzz-early", "aaa-late"]` -- a `reversed()` mutation would
    produce the other order and red that assertion."""
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/zzz-early.md",
        _page(day="2026-09-10", start_time="2026-09-10T06:00:00-04:00"),
    )
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/aaa-late.md",
        _page(day="2026-09-10", start_time="2026-09-10T18:00:00-04:00"),
    )
    _write(tmp_path, f"{WORKOUTS_DIR}/day2.md", _page(day="2026-09-11"))
    _write(tmp_path, f"{WORKOUTS_DIR}/undated.md", _page(day=None))

    corpus = scan_corpus(tmp_path)

    assert [w.stem for w in corpus.on_day(date(2026, 9, 10))] == [
        "zzz-early",
        "aaa-late",
    ]
    assert [w.stem for w in corpus.on_day(date(2026, 9, 11))] == ["day2"]


def test_within_is_inclusive_at_both_edges(tmp_path: Path) -> None:
    """The three in-window stems are named opposite to alphabetical-vs-day
    order (`sorted()` by stem gives `first-day, last-day, mid-day`; by day
    it is `first-day, mid-day, last-day`), so the list equality below pins
    `within`'s own `order_key` order, not just membership. Named mutation:
    `tuple(reversed(...))` in `within` would produce
    `["last-day", "mid-day", "first-day"]` and red this assertion."""
    _write(tmp_path, f"{WORKOUTS_DIR}/first-day.md", _page(day="2026-09-10"))
    _write(tmp_path, f"{WORKOUTS_DIR}/mid-day.md", _page(day="2026-09-12"))
    _write(tmp_path, f"{WORKOUTS_DIR}/last-day.md", _page(day="2026-09-14"))
    _write(tmp_path, f"{WORKOUTS_DIR}/before.md", _page(day="2026-09-09"))
    _write(tmp_path, f"{WORKOUTS_DIR}/after.md", _page(day="2026-09-15"))

    corpus = scan_corpus(tmp_path)

    within = corpus.within(date(2026, 9, 10), date(2026, 9, 14))
    assert [w.stem for w in within] == ["first-day", "mid-day", "last-day"]


def test_within_never_returns_an_undated_workout(tmp_path: Path) -> None:
    """Named mutation: including undated pages in `within` would put
    `undated` in this window -- design.md's own stated postcondition."""
    _write(tmp_path, f"{WORKOUTS_DIR}/undated.md", _page(day=None))
    _write(tmp_path, f"{WORKOUTS_DIR}/in-window.md", _page(day="2026-09-10"))

    corpus = scan_corpus(tmp_path)

    within = corpus.within(date(2020, 1, 1), date(2030, 1, 1))
    assert {w.stem for w in within} == {"in-window"}


# --- Req 1.7: activity-quality flags never read, never exclude -----------------


def test_a_page_whose_load_region_carries_a_quality_flag_line_is_still_present(
    tmp_path: Path,
) -> None:
    """Req 1.7: a page whose body carries a real `load` region (the same
    marker pair `fitdocs.docmerge` renders and the same rendered
    `**Quality flags:**` line `fitdocs.load.render.render_computed` produces)
    is still a corpus member, with its load and methodology read correctly
    -- this scan has no flag-based exclusion of any kind. Named mutation: a
    scanner that skipped any page whose text contains `**Quality flags:**`
    would exclude this page and this test alone would go red."""
    load_region = docmerge.region_block(
        LOAD_REGION,
        "**Quality flags:**\n- **HR dropout:** suspect — sensor gap detected"
        " mid-workout",
    )
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/flagged.md",
        _page(
            load_value=200.0,
            load_methodology="banister",
            body=load_region,
        ),
    )

    corpus = scan_corpus(tmp_path)

    assert len(corpus.workouts) == 1
    assert corpus.workouts[0].load == 200.0
    assert corpus.workouts[0].methodology == "banister"
