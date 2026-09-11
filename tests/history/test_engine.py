"""Tests for the `history` package's one writing module (load-history spec,
task 5.2; Req 1.9, 1.10, 4.2, 7.4, 7.5, 7.6, 8.1, 8.5, 8.6). See the
"HistoryEngine (`src/fitdocs/history/engine.py`)" component in
`.kiro/specs/load-history/design.md`.

Every fixture here is a synthetically written page tree under `tmp_path`,
built from real frontmatter fences and real `fitdocs.contract` vocabulary --
the same pattern `tests/history/test_documents.py` uses, and read by the
actual `scan_documents` -> ... -> `render_history` pipeline `run_history`
itself calls. No `.fit` file is read and no real wiki page is ever used.
"""

from __future__ import annotations

import stat
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import pytest

import fitdocs.history.engine as engine_module
from fitdocs import contract
from fitdocs.history.engine import (
    MethodologyConfigurationError,
    run_history,
)
from fitdocs.history.model import ModelSeries, run_model
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.settings import SettingsError

_DOC_REL = "history/training-load-history.md"
_CHART_REL = "history/assets/training-load-history-fitness.svg"


def _write(root: Path, relpath: str, text: str) -> Path:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _page(
    *,
    day: str,
    load_value: float | None = None,
    load_methodology: str | None = None,
    effort_lines: str = "",
) -> str:
    """A minimal, syntactically valid fitdocs workout document -- a real
    frontmatter fence and real vocabulary, matching `test_documents.py`'s own
    `_page` fixture builder."""
    lines = ["---", "title: Test Workout", "type: workout", f'date: "{day}"']
    if load_value is not None:
        lines.append(f"load_value: {load_value}")
    if load_methodology is not None:
        lines.append(f"load_methodology: {load_methodology}")
    if effort_lines:
        lines.append(effort_lines)
    lines.append("---")
    lines.append("")
    lines.append("# Test Workout")
    lines.append("")
    return "\n".join(lines) + "\n"


def _write_page(
    root: Path,
    name: str,
    *,
    day: str,
    load_value: float | None = None,
    load_methodology: str | None = None,
    effort_lines: str = "",
) -> Path:
    return _write(
        root,
        f"{WORKOUTS_DIR}/{name}.md",
        _page(
            day=day,
            load_value=load_value,
            load_methodology=load_methodology,
            effort_lines=effort_lines,
        ),
    )


def _write_settings(root: Path, text: str) -> Path:
    return _write(root, "fitdocs.toml", text)


# ==============================================================================
# 1.10 / controller decision: the empty archive is gated BEFORE methodology
# resolution, and writes/refreshes nothing.
# ==============================================================================


def test_empty_archive_writes_nothing_reports_no_failure_and_sets_the_note(
    tmp_path: Path,
) -> None:
    """No page anywhere records a load. Even with a methodology *configured*
    (`[load].default_calculator`), the run must complete quietly -- Req 1.10 --
    not raise a `MethodologyConfigurationError`.

    Named mutation: swap the engine's gate order so `select_methodology` runs
    before the "every page's load is None" check -- `select_methodology`
    would then see `configured="banister_1991"` recorded by no page and
    return a `MethodologyProblem`, which the (mutated) engine raises as a
    `MethodologyConfigurationError`; this test's `run_history` call would
    raise instead of returning, so the assertion on `report.note` never even
    executes -- the run itself reports FAILED via the uncaught
    `MethodologyConfigurationError`, which is the strongest possible red for
    an assertion this test never reaches."""
    _write_page(tmp_path, "unscored", day="2024-01-01")
    _write_settings(tmp_path, '[load]\ndefault_calculator = "banister_1991"\n')

    report = run_history(tmp_path)

    assert report.document is None
    assert report.chart is None
    assert report.note is not None
    assert report.failures == ()
    assert report.methodology is None


def test_empty_archive_refreshes_no_declarations_and_creates_no_directory(
    tmp_path: Path,
) -> None:
    """The empty-archive path writes nothing at all -- not even the
    ownership-declaration refresh `ensure_declarations` would otherwise
    perform (tasks.md's controller decision: "no outputs and no declaration
    refresh"). Named mutation: move the `ensure_declarations(data_root)` call
    (or an equivalent call) ahead of the empty-archive `return` -- `history/`
    would then exist (as `AGENTS.md`'s own parent) even though nothing else
    was written, and this assertion reds."""
    _write_page(tmp_path, "unscored", day="2024-01-01")

    run_history(tmp_path)

    assert not (tmp_path / "history").exists()


# ==============================================================================
# 8.5: determinism -- two runs over an unchanged tree write byte-identical
# files and produce equal reports.
# ==============================================================================


def _write_mixed_archive(root: Path) -> None:
    """Pages recording the chosen methodology (contributing and one with a
    race tag), one recording no load at all (in-span), one recording no load
    dated *before* the contributing span (out-of-span), one recording a
    different, excluded methodology, and one undated page (skipped)."""
    _write_page(
        root, "p1", day="2024-01-01", load_value=5.0, load_methodology="banister_1991"
    )
    _write_page(
        root, "p2", day="2024-01-02", load_value=5.0, load_methodology="banister_1991"
    )
    _write_page(
        root,
        "p3",
        day="2024-01-03",
        load_value=5.0,
        load_methodology="banister_1991",
        effort_lines="effort: race\neffort_distance_m: 5000\neffort_time_s: 1200",
    )
    _write_page(root, "p4-unscored-inspan", day="2024-01-04")
    _write_page(root, "p5-unscored-outofspan", day="2023-12-25")
    _write_page(
        root, "p6", day="2024-01-10", load_value=5.0, load_methodology="banister_1991"
    )
    _write_page(
        root,
        "p7-other-methodology",
        day="2024-01-05",
        load_value=3.0,
        load_methodology="trimp_legacy",
    )
    _write(
        root, f"{WORKOUTS_DIR}/p8-undated.md", _page(day="").replace('date: ""\n', "")
    )


def test_two_runs_over_an_unchanged_tree_write_identical_bytes_and_equal_reports(
    tmp_path: Path,
) -> None:
    _write_mixed_archive(tmp_path)

    first = run_history(tmp_path, methodology="banister_1991")
    doc_bytes_1 = (tmp_path / _DOC_REL).read_bytes()
    chart_bytes_1 = (tmp_path / _CHART_REL).read_bytes()

    second = run_history(tmp_path, methodology="banister_1991")
    doc_bytes_2 = (tmp_path / _DOC_REL).read_bytes()
    chart_bytes_2 = (tmp_path / _CHART_REL).read_bytes()

    assert doc_bytes_1 == doc_bytes_2
    assert chart_bytes_1 == chart_bytes_2
    assert first == second
    assert first.document == _DOC_REL
    assert first.chart == _CHART_REL


def test_the_report_shape_pins_every_page_bucket_precisely(tmp_path: Path) -> None:
    """Pins Req 8.6's report fields against the exact `_write_mixed_archive`
    fixture, whose arithmetic is stated in that helper's own docstring-like
    inline comments above:

    - `pages_read` = 7 (every scanned, dated, recognized page; the undated
      `p8` is a `SkippedPage`, counted separately).
    - `pages_contributing` = 4 (`p1`, `p2`, `p3`, `p6` -- the pages whose
      load actually feeds the daily series).
    - `pages_without_load` = 2 (`p4`, `p5` -- no `load_value` at all).
    - `pages_excluded` = (("trimp_legacy", 1),) -- only `p7`.
    - `pages_out_of_span` = 1 (`p5`, dated 2023-12-25, before the
      contributing span's own start 2024-01-01; `p4`, dated 2024-01-04, is
      *inside* the span and must not be counted here).
    - `criterion_points` = 1 (`p3`'s well-formed race tag with a time).
    - `suppressed_weeks` = 1 (ISO week (2024, 1): pages_with_load 3 / pages 4
      = 75% < the 80% seed threshold).

    Named mutation: change `pages_out_of_span`'s filter from `page.load is
    None and not (series.start <= page.day <= series.end)` to merely `page.load
    is None` (i.e. count every load-less page, not only the out-of-span ones)
    -- `pages_out_of_span` becomes 2 instead of 1 and this test reds, while
    `pages_without_load` (a separate, correct assertion at 2) stays green --
    the two assertions are not confounded.

    The written document's own `Coverage` section carries the same skipped
    count on its archive-wide `all:` row (`_render_coverage_section`'s own
    `"; skipped: {row.pages_skipped}"` clause, fed by `coverage_report`'s
    `skipped` parameter). Named mutation for that wiring: change the
    engine's `coverage_report(series, excluded, choice, len(scan.skipped))`
    call to pass `len([])` instead of `len(scan.skipped)` -- the archive-wide
    row's `pages_skipped` would read `0`, its rendered line would carry
    `skipped: 0` instead of `skipped: 1`, and the coverage-line assertion
    below reds while `report.skipped` (read directly off `scan.skipped`,
    never through `coverage_report`) stays a red herring at its own correct
    length."""
    _write_mixed_archive(tmp_path)

    report = run_history(tmp_path, methodology="banister_1991")

    assert report.pages_read == 7
    assert report.pages_contributing == 4
    assert report.pages_without_load == 2
    assert report.pages_excluded == (("trimp_legacy", 1),)
    assert report.pages_out_of_span == 1
    assert report.criterion_points == 1
    assert report.suppressed_weeks == 1
    assert len(report.skipped) == 1
    assert report.skipped[0].path == f"{WORKOUTS_DIR}/p8-undated.md"
    assert report.methodology == "banister_1991"
    assert report.note is None

    assert report.document is not None
    markdown = (tmp_path / _DOC_REL).read_text(encoding="utf-8")
    all_coverage_lines = [
        line for line in markdown.splitlines() if line.startswith("- all:")
    ]
    assert len(all_coverage_lines) == 1
    assert "skipped: 1" in all_coverage_lines[0]


def test_criterion_points_count_is_not_confounded_with_the_number_of_distinct_kinds(
    tmp_path: Path,
) -> None:
    """Two well-formed RACE tags -> `report.criterion_points == 2` while the
    underlying `CriterionPoints.by_kind` has exactly one entry (one kind,
    RACE, observed twice) -- a tied fixture that defeats a mutation
    confusing "how many points" with "how many kinds". Named mutation:
    change the engine's `criterion_points=criterion.count` to
    `criterion_points=len(criterion.by_kind)` -- `report.criterion_points`
    would read 1 instead of 2, and the assertion below reds."""
    _write_page(
        tmp_path,
        "p1",
        day="2024-01-01",
        load_value=5.0,
        load_methodology="banister_1991",
        effort_lines="effort: race\neffort_distance_m: 5000\neffort_time_s: 1200",
    )
    _write_page(
        tmp_path,
        "p2",
        day="2024-01-02",
        load_value=5.0,
        load_methodology="banister_1991",
        effort_lines="effort: race\neffort_distance_m: 10000\neffort_time_s: 2400",
    )

    report = run_history(tmp_path, methodology="banister_1991")

    assert report.criterion_points == 2


# ==============================================================================
# 7.6: the foreign-file rule at both output paths.
# ==============================================================================


def test_a_foreign_file_at_either_output_path_survives_unchanged_and_is_reported(
    tmp_path: Path,
) -> None:
    """Neither output path carries `contract.GENERATED_PREFIX` -- both are
    left completely untouched and both are named in `report.foreign`.

    Named mutation: delete the `_is_foreign_occupant` check ahead of the
    chart write (write through it unconditionally) -- the chart bytes would
    become the freshly rendered SVG instead of the original foreign text,
    and the first assertion below reds; the same mutation on the document
    branch reds the second."""
    _write_mixed_archive(tmp_path)
    foreign_chart = "not an svg fitdocs ever wrote\n"
    foreign_doc = "not a fitdocs document\n"
    _write(tmp_path, _CHART_REL, foreign_chart)
    _write(tmp_path, _DOC_REL, foreign_doc)

    report = run_history(tmp_path, methodology="banister_1991")

    assert (tmp_path / _CHART_REL).read_text(encoding="utf-8") == foreign_chart
    assert (tmp_path / _DOC_REL).read_text(encoding="utf-8") == foreign_doc
    assert report.chart is None
    assert report.document is None
    assert sorted(report.foreign) == sorted([_CHART_REL, _DOC_REL])
    assert report.failures == ()


def test_a_directory_and_non_utf8_bytes_at_the_output_paths_are_both_foreign(
    tmp_path: Path,
) -> None:
    """Req 7.6's other occupant classes, distinct from the plain-text-but-
    not-generated case the previous test covers: a directory occupying the
    chart path, and a document path holding bytes that are not valid UTF-8.
    Both must be recognized as foreign and left completely untouched --
    `report.failures` stays empty (neither is an `OSError` this run raises
    itself; both are classified before any write is even attempted).

    Named mutation, two variants, both observed directly (neither behaves as
    a naive reading of the `except` clause would suggest):

    - Change `_is_foreign_occupant`'s `except (OSError, UnicodeDecodeError):
      return True` to `except UnicodeDecodeError: return False` -- with
      `OSError` no longer caught at all, `path.read_text` on the directory
      path raises `IsADirectoryError` *uncaught* inside
      `_is_foreign_occupant` itself, and `run_history` raises before
      returning a report. The test reds at `run_history(...)`, before any
      assertion runs.
    - Change it instead to `except OSError: return False` -- the directory
      occupying the chart path is now classified not-foreign, so the run
      attempts the chart write: `_atomic_write`'s own `os.replace` of its
      temp file onto the chart path raises `IsADirectoryError` (a file can
      never be renamed onto a directory), which lands in `report.failures` as an
      ordinary write failure, not `report.foreign`. That failure sets
      `chart_failed`, which short-circuits the document branch before it is
      ever attempted -- so the non-UTF-8 document is also never classified.
      `report.foreign` comes back `()`, and the FIRST assertion below
      (`sorted(report.foreign) == sorted([_CHART_REL, _DOC_REL])`) reds."""
    _write_mixed_archive(tmp_path)
    chart_dir = tmp_path / _CHART_REL
    chart_dir.mkdir(parents=True)
    (chart_dir / "occupant.txt").write_text("a directory occupies this path\n")
    document_path = tmp_path / _DOC_REL
    document_path.parent.mkdir(parents=True, exist_ok=True)
    foreign_document_bytes = b"\xff\xfe\x00\x01not valid utf-8\n"
    document_path.write_bytes(foreign_document_bytes)

    report = run_history(tmp_path, methodology="banister_1991")

    assert sorted(report.foreign) == sorted([_CHART_REL, _DOC_REL])
    assert report.failures == ()
    assert chart_dir.is_dir()
    assert [p.name for p in chart_dir.iterdir()] == ["occupant.txt"]
    assert document_path.read_bytes() == foreign_document_bytes


# ==============================================================================
# Write order and torn-state safety (design.md, tasks.md's named mutation).
# ==============================================================================


@pytest.fixture
def _restore_permissions() -> Iterator[list[Path]]:
    """Paths this test chmods restrictively; restored to writable at
    teardown so `tmp_path`'s own cleanup never trips over a locked
    directory."""
    locked: list[Path] = []
    yield locked
    for path in locked:
        path.chmod(stat.S_IRWXU)


def test_a_chart_write_failure_aborts_before_the_document_is_attempted(
    tmp_path: Path, _restore_permissions: list[Path]
) -> None:
    """The chart's own directory is unwritable; the document's directory is
    not. A failure entry names the chart, and -- the torn-state pin -- the
    document is never even attempted: it does not exist on disk and carries
    no report outcome of its own (not written, not foreign, not a second
    failure).

    Named mutation: write the document before the chart (swap the two
    branches' order without changing the `chart_failed` short-circuit
    accordingly) -- the document would be written successfully despite the
    chart failure, and `assert report.document is None` below reds, together
    with the file-existence assertion."""
    _write_mixed_archive(tmp_path)
    assets_dir = tmp_path / "history" / "assets"
    assets_dir.mkdir(parents=True)
    assets_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # read+traverse, no write
    _restore_permissions.append(assets_dir)

    report = run_history(tmp_path, methodology="banister_1991")

    assert report.chart is None
    assert report.document is None
    assert len(report.failures) == 1
    failed_path, reason = report.failures[0]
    assert failed_path == _CHART_REL
    assert reason
    assert not (tmp_path / _DOC_REL).exists()
    # No partial/temp file left behind in the locked directory either -- here
    # `mkstemp` itself never succeeds (the directory denies write), so this
    # is trivially true regardless of the cleanup line; the dedicated test
    # below discriminates that line directly.
    assert list(assets_dir.iterdir()) == []


def test_a_replace_failure_after_the_temp_file_exists_leaves_no_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unlike the locked-directory scenario above (where `mkstemp` itself
    never succeeds, so "no partial file" holds trivially), this fails
    *after* the temp file is created -- `os.replace` itself raises -- so the
    assertion below actually exercises `_atomic_write`'s own
    `except BaseException: tmp_path.unlink(missing_ok=True); raise` cleanup.

    Named mutation: delete `tmp_path.unlink(missing_ok=True)` from
    `_atomic_write`'s `except` clause -- the `.history-*.tmp` file the mocked
    `os.replace` left behind survives, and the glob assertion below reds."""
    _write_mixed_archive(tmp_path)

    real_replace = engine_module.os.replace

    def _failing_replace(src: object, dst: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(engine_module.os, "replace", _failing_replace)

    report = run_history(tmp_path, methodology="banister_1991")

    monkeypatch.setattr(engine_module.os, "replace", real_replace)

    assert report.chart is None
    assert len(report.failures) == 1
    assert not (tmp_path / _CHART_REL).exists()
    assets_dir = tmp_path / "history" / "assets"
    assert list(assets_dir.glob(".history-*.tmp")) == []


# ==============================================================================
# Methodology resolution: a MethodologyProblem becomes a SettingsError
# subclass, raised before anything is written.
# ==============================================================================


def test_an_ambiguous_methodology_raises_a_settings_error_before_any_write(
    tmp_path: Path,
) -> None:
    _write_page(
        tmp_path,
        "a",
        day="2024-01-01",
        load_value=5.0,
        load_methodology="banister_1991",
    )
    _write_page(
        tmp_path, "b", day="2024-01-02", load_value=5.0, load_methodology="trimp_legacy"
    )

    with pytest.raises(MethodologyConfigurationError) as excinfo:
        run_history(tmp_path)

    assert isinstance(excinfo.value, SettingsError)
    assert "banister_1991" in str(excinfo.value)
    assert "trimp_legacy" in str(excinfo.value)
    assert not (tmp_path / "history").exists()


def test_a_malformed_history_settings_table_propagates_before_any_write(
    tmp_path: Path,
) -> None:
    _write_page(
        tmp_path,
        "a",
        day="2024-01-01",
        load_value=5.0,
        load_methodology="banister_1991",
    )
    _write_settings(tmp_path, "[history]\ntau_fitness_days = true\n")

    with pytest.raises(SettingsError):
        run_history(tmp_path)

    assert not (tmp_path / "history").exists()


def test_history_methodology_setting_beats_the_load_default_calculator(
    tmp_path: Path,
) -> None:
    """Req 4.2/design.md:975's stated precedence: `[history].methodology`
    beats `[load].default_calculator`. Named mutation: swap the `or` operands
    in the engine (`configured = load_settings.default_calculator or
    history_settings.methodology`) -- the run would then resolve
    `"trimp_legacy"` (`[load]`'s own setting) instead of `"banister_1991"`,
    and the assertion below reds."""
    _write_page(
        tmp_path,
        "a",
        day="2024-01-01",
        load_value=5.0,
        load_methodology="banister_1991",
    )
    _write_page(
        tmp_path, "b", day="2024-01-02", load_value=3.0, load_methodology="trimp_legacy"
    )
    _write_settings(
        tmp_path,
        '[history]\nmethodology = "banister_1991"\n'
        '[load]\ndefault_calculator = "trimp_legacy"\n',
    )

    report = run_history(tmp_path)

    assert report.methodology == "banister_1991"


def test_a_requested_methodology_beats_the_configured_one(
    tmp_path: Path,
) -> None:
    """Req 4.2's other half of the precedence: a caller-supplied `requested`
    methodology beats whatever `[load].default_calculator` (or
    `[history].methodology`) configures. Named mutation: swap the
    `requested=`/`configured=` keyword arguments in the engine's
    `select_methodology(...)` call -- `requested` would then carry
    `"trimp_legacy"` (the configured value) and `configured` would carry
    `"banister_1991"` (the caller's request); since `"trimp_legacy"` is
    recorded by a page, `select_methodology` would resolve it instead, and
    the assertion below reds."""
    _write_page(
        tmp_path,
        "a",
        day="2024-01-01",
        load_value=5.0,
        load_methodology="banister_1991",
    )
    _write_page(
        tmp_path, "b", day="2024-01-02", load_value=3.0, load_methodology="trimp_legacy"
    )
    _write_settings(tmp_path, '[load]\ndefault_calculator = "trimp_legacy"\n')

    report = run_history(tmp_path, methodology="banister_1991")

    assert report.methodology == "banister_1991"


# ==============================================================================
# Implementation Notes (from 4.3 review): the engine passes RACE markers
# only -- render_history labels EVERY marker it is handed as a race.
# ==============================================================================


def _races_section(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    try:
        start = lines.index("Races:")
    except ValueError:
        return []
    entries = []
    for line in lines[start + 1 :]:
        if not line or not line[0].isdigit():
            break
        entries.append(line)
    return entries


def test_only_race_tagged_pages_become_chart_markers_never_test_tags(
    tmp_path: Path,
) -> None:
    """Named mutation: relax the marker filter from `effort.kind is
    EffortKind.RACE` to `effort is not None` -- the TEST-tagged page would
    also become a marker, `_races_section` would return two entries instead
    of one, and this test reds."""
    _write_page(
        tmp_path,
        "race-page",
        day="2024-01-01",
        load_value=5.0,
        load_methodology="banister_1991",
        effort_lines="effort: race\neffort_distance_m: 5000\neffort_time_s: 1200",
    )
    _write_page(
        tmp_path,
        "test-page",
        day="2024-01-02",
        load_value=5.0,
        load_methodology="banister_1991",
        effort_lines="effort: test\neffort_time_s: 600",
    )

    report = run_history(tmp_path, methodology="banister_1991")
    assert report.document is not None
    markdown = (tmp_path / _DOC_REL).read_text(encoding="utf-8")

    entries = _races_section(markdown)
    assert len(entries) == 1
    assert "2024-01-01" in entries[0]
    assert "2024-01-02" not in " ".join(entries)


def test_a_race_page_dated_before_the_series_start_is_not_a_chart_marker(
    tmp_path: Path,
) -> None:
    """A load-less race page dated before the daily series even starts has
    no day index on the chart to mark (`series.start <= day <= series.end`
    is the marker filter's own span half, not just the effort-kind half the
    previous test pins) -- so it produces no `Races:` entry, and instead
    counts toward `report.pages_out_of_span` (Req 1.8, 3.10): it is
    included (no load, so `partition_pages` never excludes it) but its date
    falls outside `[series.start, series.end]`, which `build_daily_series`
    never folded into any `DayLoad`.

    Named mutation: drop `and series.start <= record.day <= series.end` from
    the marker-comprehension's filter in `run_history` -- the out-of-span
    race page would gain a (negative, out-of-range) day index and become a
    marker, so `_races_section` would return one entry instead of zero and
    the first assertion below reds."""
    _write_page(
        tmp_path,
        "loaded-page",
        day="2024-01-10",
        load_value=5.0,
        load_methodology="banister_1991",
    )
    _write_page(
        tmp_path,
        "early-race",
        day="2024-01-01",
        effort_lines="effort: race\neffort_distance_m: 5000\neffort_time_s: 1200",
    )

    report = run_history(tmp_path, methodology="banister_1991")
    assert report.document is not None
    markdown = (tmp_path / _DOC_REL).read_text(encoding="utf-8")

    assert _races_section(markdown) == []
    assert report.pages_out_of_span == 1


def _marker_group_count(chart_text: str) -> int:
    return chart_text.count('class="marker"')


def test_a_race_page_excluded_by_methodology_but_inside_the_span_is_still_a_marker(
    tmp_path: Path,
) -> None:
    """Req 5.4 ("when a page is tagged as a race, mark that page's date on
    the chart") does not condition the marking on the page's load
    methodology -- a tag is a fact about the page, independent of whether
    its load happened to fall in the chosen methodology's partition (the
    criterion-point precedent above). The marker filter's span half still
    applies, so this fixture dates the excluded-methodology race page
    *inside* `[series.start, series.end]` -- unlike the criterion-points
    fixture above (whose 'excluded-race' page at 2024-01-02 is *outside*
    the one-day span its own 'chosen' page produces), which would mask this
    choice by failing the span filter regardless of the marker source.

    Named mutation: keep sourcing the marker comprehension from `included`
    instead of `scan.pages` -- `partition_pages` drops this page because its
    `load_methodology` is `trimp_legacy` while the run resolves
    `banister_1991`, so it would never reach the marker comprehension at
    all; `_races_section` would return zero entries instead of one, and the
    chart would carry zero marker groups instead of one, and both
    assertions below red."""
    _write_page(
        tmp_path,
        "chosen-start",
        day="2024-01-01",
        load_value=5.0,
        load_methodology="banister_1991",
    )
    _write_page(
        tmp_path,
        "chosen-end",
        day="2024-01-05",
        load_value=5.0,
        load_methodology="banister_1991",
    )
    _write_page(
        tmp_path,
        "other-methodology-race",
        day="2024-01-03",
        load_value=3.0,
        load_methodology="trimp_legacy",
        effort_lines="effort: race\neffort_distance_m: 5000\neffort_time_s: 1200",
    )

    report = run_history(tmp_path, methodology="banister_1991")
    assert report.document is not None
    markdown = (tmp_path / _DOC_REL).read_text(encoding="utf-8")
    chart_text = (tmp_path / _CHART_REL).read_text(encoding="utf-8")

    entries = _races_section(markdown)
    assert len(entries) == 1
    assert "2024-01-03" in entries[0]
    assert _marker_group_count(chart_text) == 1


def test_race_markers_carry_the_day_index_of_their_own_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 5.4 ("mark that page's date on the chart"): the engine hands
    `render_history` one `(day_index, record)` per in-span race, where
    `day_index` is that page's offset from `series.start` -- pinned by
    spying on the exact tuples, because the page-level marker tests only
    count entries and read the date text, which the index does not affect.
    The fixture deliberately puts one race on the span's LAST day (so an
    exclusive end bound loses it) and the other off-centre (so a mirrored
    index cannot collide with the true one at the span's midpoint).

    Named mutations: make the span check `< series.end` (the last-day race
    vanishes: only `(1, 2024-01-02)` recorded); compute the index as
    `(series.end - record.day).days` (the tuples become `(3, ...)`,
    `(0, ...)`); add one to the index (`(2, ...)`, `(5, ...)`). Each reds
    the tuple assertion below."""
    from datetime import date

    _write_page(
        tmp_path,
        "start",
        day="2024-01-01",
        load_value=5.0,
        load_methodology="banister_1991",
    )
    _write_page(
        tmp_path,
        "race-mid",
        day="2024-01-02",
        load_value=4.0,
        load_methodology="banister_1991",
        effort_lines="effort: race\neffort_time_s: 1200",
    )
    _write_page(
        tmp_path,
        "race-last",
        day="2024-01-05",
        load_value=6.0,
        load_methodology="banister_1991",
        effort_lines="effort: race\neffort_time_s: 1300",
    )

    real_render = engine_module.render_history
    seen: list[tuple[tuple[int, date], ...]] = []

    def spy(*args: object, **kwargs: object) -> object:
        markers = kwargs["markers"]
        seen.append(tuple((i, r.day) for i, r in markers))  # type: ignore[attr-defined]
        return real_render(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(engine_module, "render_history", spy)
    report = run_history(tmp_path, methodology="banister_1991")
    assert report.document is not None
    assert seen == [((1, date(2024, 1, 2)), (4, date(2024, 1, 5)))]
    chart_text = (tmp_path / _CHART_REL).read_text(encoding="utf-8")
    assert _marker_group_count(chart_text) == 2


# ==============================================================================
# Implementation Notes (from 3.4/3.5 review): criterion_points takes the
# FULL scan, not the partition -- an excluded-methodology page's race tag
# still counts.
# ==============================================================================


def test_criterion_points_counts_a_race_page_excluded_by_methodology(
    tmp_path: Path,
) -> None:
    """Named mutation: pass `included` instead of `scan.pages` to
    `criterion_points` -- the excluded-methodology race page would no longer
    be walked at all, `report.criterion_points` would be `0`, and this test
    reds."""
    _write_page(
        tmp_path,
        "chosen",
        day="2024-01-01",
        load_value=5.0,
        load_methodology="banister_1991",
    )
    _write_page(
        tmp_path,
        "excluded-race",
        day="2024-01-02",
        load_value=3.0,
        load_methodology="trimp_legacy",
        effort_lines="effort: race\neffort_distance_m: 5000\neffort_time_s: 1200",
    )

    report = run_history(tmp_path, methodology="banister_1991")

    assert report.criterion_points == 1


# ==============================================================================
# The recursion runs exactly once over the whole span, never per week.
# ==============================================================================


def test_run_model_is_called_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Named mutation: call `run_model` once per `WeekRow` instead of once
    for the whole `DailySeries` -- `calls` would read `>= 3` for a
    three-week fixture, not `1`, and this test reds."""
    _write_page(
        tmp_path,
        "p1",
        day="2024-01-01",
        load_value=5.0,
        load_methodology="banister_1991",
    )
    _write_page(
        tmp_path,
        "p2",
        day="2024-01-20",
        load_value=5.0,
        load_methodology="banister_1991",
    )

    calls = 0

    def _counting_run_model(daily_loads: object, constants: object) -> ModelSeries:
        nonlocal calls
        calls += 1
        return run_model(daily_loads, constants)  # type: ignore[arg-type]

    monkeypatch.setattr(engine_module, "run_model", _counting_run_model)

    run_history(tmp_path, methodology="banister_1991")

    assert calls == 1


# ==============================================================================
# Structural: no `today`/clock-shaped parameter on the public entry point
# (the full clock scan across the package is task 5.4's; this only pins this
# module's own signature, which is all 5.2 controls).
# ==============================================================================


def test_run_history_takes_no_date_or_clock_parameter() -> None:
    import inspect

    signature = inspect.signature(run_history)
    for name in signature.parameters:
        assert "date" not in name.lower()
        assert "today" not in name.lower()
        assert "clock" not in name.lower()


# ==============================================================================
# Req 7.4: a history run creates, modifies and deletes files only inside the
# owned `history/` location (and the declared directories the ownership
# refresh legitimately touches) -- never a workout document, a workout
# asset, an archived source, the athlete profile or the settings file. The
# full confinement guard (every writing entry point, every owned prefix) is
# task 5.4's; this pins only what this module's own test fixtures can show:
# every file that existed before the run and is not under `history/` is
# untouched, byte-for-byte, afterward.
# ==============================================================================


#: The two ownership declarations `ensure_declarations` may legitimately
#: create or rewrite on a data root that has never been synced (the design's
#: own stated exception, tasks.md's 5.2 bullet) -- excluded from the
#: before/after snapshot below so this test pins the *narrowed* claim: no
#: workout document, workout asset or archived source is ever touched.
_DECLARATION_PATHS = {Path("workouts/AGENTS.md"), Path("fit-archive/AGENTS.md")}


def _snapshot(root: Path) -> dict[Path, bytes]:
    return {
        rel: path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
        and "history" not in (rel := path.relative_to(root)).parts
        and rel not in _DECLARATION_PATHS
    }


def test_a_run_never_modifies_a_workout_document_asset_or_archived_source(
    tmp_path: Path,
) -> None:
    """Named mutation: have the engine additionally `_atomic_write` a marker
    byte into the *first* scanned workout document (a one-line addition
    right after the scan) -- `before` and `after` would then disagree on
    that document's own bytes, and this test reds."""
    _write_mixed_archive(tmp_path)
    _write_settings(tmp_path, '[load]\ndefault_calculator = "banister_1991"\n')

    before = _snapshot(tmp_path)
    run_history(tmp_path)
    after = _snapshot(tmp_path)

    assert before == after


# ==============================================================================
# CRITICAL (remediation round 2): the written chart must be valid XML, and
# must be recognized as fitdocs' own on a later run.
# ==============================================================================


def test_the_written_chart_is_well_formed_xml_and_recognized_as_generated(
    tmp_path: Path,
) -> None:
    """`xml.etree.ElementTree.fromstring` must accept the written chart file
    whole -- an SVG file is XML, and an XML comment's content may never
    contain `--`. Also pins that the marker this module writes is recognized
    by `contract.is_generated`, and that a second run treats its own chart as
    its own (not foreign).

    Named mutation: write `contract.DOC_BANNER + "\\n" + rendered.chart_svg`
    instead of `_CHART_MARKER + "\\n" + rendered.chart_svg` (the pre-fix
    code) -- `contract.DOC_BANNER`'s prose contains a literal ` -- `, which
    is forbidden inside an XML comment's content, and `ET.fromstring` raises
    `xml.etree.ElementTree.ParseError` instead of returning -- the strongest
    possible red for this assertion."""
    _write_mixed_archive(tmp_path)

    run_history(tmp_path, methodology="banister_1991")
    chart_text = (tmp_path / _CHART_REL).read_text(encoding="utf-8")

    ET.fromstring(chart_text)  # must not raise xml.etree.ElementTree.ParseError
    assert contract.is_generated(chart_text)

    second = run_history(tmp_path, methodology="banister_1991")

    assert second.foreign == ()
    assert second.chart == _CHART_REL


# ==============================================================================
# O1: the atomic-write idiom itself -- os.replace called with the two
# output paths as `dst` and a temp sibling as `src`.
# ==============================================================================


def test_atomic_write_uses_os_replace_with_temp_siblings_for_both_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Named mutation: replace `_atomic_write`'s body with a direct
    `path.write_text(text, encoding="utf-8")` (bypassing `os.replace`
    entirely) -- `calls` would be empty instead of holding two entries, and
    the length assertion below reds."""
    _write_mixed_archive(tmp_path)
    calls: list[tuple[Path, Path]] = []
    real_replace = engine_module.os.replace

    def _spy_replace(src: object, dst: object) -> None:
        calls.append((Path(str(src)), Path(str(dst))))
        real_replace(src, dst)

    monkeypatch.setattr(engine_module.os, "replace", _spy_replace)

    run_history(tmp_path, methodology="banister_1991")

    assert len(calls) == 2
    dsts = {dst for _, dst in calls}
    assert dsts == {tmp_path / _CHART_REL, tmp_path / _DOC_REL}
    for src, dst in calls:
        assert src.parent == dst.parent
        assert src != dst
        assert src.name.startswith(engine_module._TMP_PREFIX)


def test_a_replace_failure_only_on_the_document_path_leaves_the_chart_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unlike the chart-only failure fixture above, this fails `os.replace`
    selectively -- only when its `dst` is the document path -- so the chart
    write must succeed and survive while the document write fails cleanly.

    Named mutation: change the document write's `except OSError as exc:
    failures.append((document_rel, _reason(exc)))` to `except OSError:
    pass` -- the failure would go unreported (`report.failures == ()`
    instead of holding one entry) while the document still does not exist,
    and the `failures` assertion below reds."""
    _write_mixed_archive(tmp_path)
    document_path = tmp_path / _DOC_REL
    real_replace = engine_module.os.replace

    def _selective_failing_replace(src: object, dst: object) -> None:
        if Path(str(dst)) == document_path:
            raise OSError("simulated replace failure")
        real_replace(src, dst)

    monkeypatch.setattr(engine_module.os, "replace", _selective_failing_replace)

    report = run_history(tmp_path, methodology="banister_1991")

    assert report.chart == _CHART_REL
    assert report.document is None
    assert len(report.failures) == 1
    failed_path, reason = report.failures[0]
    assert failed_path == _DOC_REL
    assert reason
    assert not document_path.exists()
    assert (tmp_path / _CHART_REL).exists()
    assert list((tmp_path / "history").glob(".history-*.tmp")) == []


# ==============================================================================
# Req 8.1: a second run over changed data rewrites the document with
# different bytes -- the write is not a one-time "only if absent" op.
# ==============================================================================


def test_a_second_run_with_new_data_rewrites_the_document_with_different_bytes(
    tmp_path: Path,
) -> None:
    """Named mutation: change the document branch's `else:` (after the
    foreign check) to `elif not document_path.exists():` -- on the second
    run the document already exists (and is not foreign), so the mutated
    branch would skip the write entirely, `second.document` would read
    `None` instead of `_DOC_REL`, and the assertions below red."""
    _write_mixed_archive(tmp_path)

    first = run_history(tmp_path, methodology="banister_1991")
    first_bytes = (tmp_path / _DOC_REL).read_bytes()

    _write_page(
        tmp_path,
        "p9-new",
        day="2024-01-11",
        load_value=8.0,
        load_methodology="banister_1991",
    )
    second = run_history(tmp_path, methodology="banister_1991")
    second_bytes = (tmp_path / _DOC_REL).read_bytes()

    assert first.document == _DOC_REL
    assert second.document == _DOC_REL
    assert first_bytes != second_bytes


# ==============================================================================
# Req 1.10: a GENERATED page and chart already at the output paths are left
# byte-identical on the empty-archive path -- the gate returns before either
# output is even considered, so nothing is unlinked either.
# ==============================================================================


def test_pre_existing_generated_outputs_survive_the_empty_archive_path_byte_identical(
    tmp_path: Path,
) -> None:
    """Named mutation: add `history_doc_path(data_root).unlink(missing_ok=True)`
    (and the matching chart unlink) immediately before the empty-archive
    `return` -- the pre-seeded document would no longer exist afterward, and
    the first assertion below reds."""
    _write_page(tmp_path, "unscored", day="2024-01-01")
    doc_text = contract.DOC_BANNER + "\nold generated document\n"
    chart_text = engine_module._CHART_MARKER + "\n<svg>old chart</svg>\n"
    _write(tmp_path, _DOC_REL, doc_text)
    _write(tmp_path, _CHART_REL, chart_text)

    report = run_history(tmp_path)

    assert (tmp_path / _DOC_REL).read_text(encoding="utf-8") == doc_text
    assert (tmp_path / _CHART_REL).read_text(encoding="utf-8") == chart_text
    assert report.document is None
    assert report.chart is None


# ==============================================================================
# O14: fitdocs.toml is read exactly once, no matter how many per-table
# readers project it.
# ==============================================================================


def test_load_settings_document_is_read_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Named mutation: call `load_settings_document(data_root)` a second time
    (e.g. duplicating the call ahead of `load_load_settings`) -- `calls`
    would read `2` instead of `1`, and the assertion below reds."""
    _write_mixed_archive(tmp_path)
    calls = 0
    real_load_settings_document = engine_module.load_settings_document

    def _counting_load_settings_document(data_root: Path) -> object:
        nonlocal calls
        calls += 1
        return real_load_settings_document(data_root)

    monkeypatch.setattr(
        engine_module, "load_settings_document", _counting_load_settings_document
    )

    run_history(tmp_path, methodology="banister_1991")

    assert calls == 1


# ==============================================================================
# O10: a symlink at either output path is foreign, and is never read
# through to decide otherwise.
# ==============================================================================


def test_a_symlink_at_the_chart_path_is_foreign_without_being_read_through(
    tmp_path: Path,
) -> None:
    """The symlink's target itself carries the chart's own generated marker
    -- so a mutated `_is_foreign_occupant` that dropped its `is_symlink()`
    check and fell through to a content read would see generated text and
    call the path NOT foreign.

    Named mutation: delete the `if path.is_symlink(): return True` line from
    `_is_foreign_occupant` -- the write would then proceed through the
    symlink (replacing it with a plain file at `chart_path`), so `report.chart`
    would read `_CHART_REL` instead of `None` and `chart_path.is_symlink()`
    would read `False`; both assertions below red."""
    _write_mixed_archive(tmp_path)
    target = tmp_path / "outside-target.svg"
    target.write_text(
        engine_module._CHART_MARKER + "\n<svg>target</svg>\n", encoding="utf-8"
    )
    chart_path = tmp_path / _CHART_REL
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    chart_path.symlink_to(target)

    report = run_history(tmp_path, methodology="banister_1991")

    assert report.chart is None
    assert _CHART_REL in report.foreign
    assert chart_path.is_symlink()


# ==============================================================================
# O5: ownership declarations are refreshed before either write is even
# attempted -- true even when the chart write itself then fails.
# ==============================================================================


def test_declarations_are_refreshed_before_the_chart_write_is_attempted(
    tmp_path: Path, _restore_permissions: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reuses the chart-write-failure fixture: the chart directory is locked
    unwritable before the run, so the write itself must fail -- yet
    `ensure_declarations` must already have run, because the design's
    sequence places the refresh immediately before the write attempts, not
    after a successful one. The chart write failure is caught by the write
    block's own `except OSError`, so `run_history` runs on to its own return
    regardless of where `ensure_declarations` sits -- a bare "does
    `history/AGENTS.md` exist once `run_history` has returned" assertion
    cannot tell the two orderings apart (both leave it written by the time
    the function returns). This instead spies on `_is_foreign_occupant`,
    the write block's own first call for the chart path -- made whether that
    write then succeeds or fails -- and records how many times it had
    already run at the moment `ensure_declarations` itself was called.

    Named mutation: move the `ensure_declarations(data_root)` call to after
    the chart/document write block -- `_is_foreign_occupant` would already
    have been called once (for the chart path) by the time
    `ensure_declarations` finally runs, so `calls_before_declarations` would
    read `[1]` instead of `[0]` and the assertion below reds."""
    _write_mixed_archive(tmp_path)
    assets_dir = tmp_path / "history" / "assets"
    assets_dir.mkdir(parents=True)
    assets_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # read+traverse, no write
    _restore_permissions.append(assets_dir)

    foreign_call_count = 0
    real_is_foreign_occupant = engine_module._is_foreign_occupant

    def _counting_is_foreign_occupant(path: Path) -> bool:
        nonlocal foreign_call_count
        foreign_call_count += 1
        return real_is_foreign_occupant(path)

    monkeypatch.setattr(
        engine_module, "_is_foreign_occupant", _counting_is_foreign_occupant
    )

    calls_before_declarations: list[int] = []
    real_ensure_declarations = engine_module.ensure_declarations

    def _recording_ensure_declarations(data_root: Path) -> None:
        calls_before_declarations.append(foreign_call_count)
        real_ensure_declarations(data_root)

    monkeypatch.setattr(
        engine_module, "ensure_declarations", _recording_ensure_declarations
    )

    report = run_history(tmp_path, methodology="banister_1991")

    assert report.chart is None
    assert (tmp_path / "history" / "AGENTS.md").exists()
    assert calls_before_declarations == [0]
