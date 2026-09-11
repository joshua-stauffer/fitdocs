"""End-to-end and feature-level validation for `fitdocs history`
(load-history spec, task 5.6; Req 1.10, 7.6, 8.5, 8.6).

Drives the installed CLI (`typer.testing.CliRunner`, never the engine
functions directly -- the same pattern `tests/test_cli_history.py` and
`tests/test_effort_tags_e2e.py` use) over a single synthetic archive built
from real frontmatter fences and real `fitdocs.contract` vocabulary. No
`.fit` file is read and no real wiki page is ever used.

The archive is built to exercise, in one run: a contributing methodology
(`banister_1991`) with several dated pages, a second, excluded methodology
(`trimp_legacy`), a race tagged page with an official time (a criterion
point and a chart marker), a page with a malformed effort tag, an undated
(skipped) page, and -- the review finding this task's brief calls out by
name -- a series spanning an ISO-year boundary with exactly one of the two
years' own ISO week 1 suppressed (thin coverage) and the *other* year's week
1 left as ordinary, uncovered rest days (full 1.0 coverage, never
suppressed). `_suppressed_day_indices` (`src/fitdocs/history/page.py`) keys
a suppressed week by the pair `(iso_year, iso_week)`; keying by `iso_week`
alone -- the exact regression the 4.3 review flagged as unpinned because
every fixture up to now was single-year -- would conflate the two week-1s
and suppress days that should be plotted (a single-field key can only ever
add days, never drop them), producing a second, non-adjacent band eleven
months from the first. The two weeks in this fixture are eleven months
apart, so no single contiguous band can cover both under the correct
keying.

Fake-system-date coverage (8.5's "across different calendar days," the
behavioural half of the clock scan the raw-text clock scan in
`tests/history/test_boundary.py` already covers structurally): CPython's
`datetime.date`/`datetime.datetime` are immutable C types and cannot be
monkeypatched directly (`cannot set 'today' attribute of immutable type`),
and `datetime.datetime.now()` reads the system clock through a C-level call
that bypasses the Python `time.time()` wrapper entirely, so a hook on
`time.time` does not reach it (a name-binding shim of the kind freezegun
installs is deliberately not used: neither history module binds a
`datetime` name, so such a shim would pin nothing). `datetime.date.today()`,
however, *is* implemented in terms
of `time.time()` plus a local-time conversion, so this module fakes the
system date behaviourally by monkeypatching `time.time` to two widely
different timestamps, and belts-and-suspenders sets `TZ` (with
`time.tzset()`) and `SOURCE_DATE_EPOCH` for the run's duration. `run_history`
reads no clock at all (Req 1.1, pinned separately at the unit level), so the
two runs are expected to be byte-identical regardless; a production
regression that injected `date.today()` into the rendered markdown was
tried against this test during review and reddened it (see the test's own
docstring for the mutation and its result).
"""

from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitdocs import contract, layout
from fitdocs.cli import app
from fitdocs.layout import WORKOUTS_DIR

runner = CliRunner()

_DOC_REL = "history/training-load-history.md"
_CHART_REL = "history/assets/training-load-history-fitness.svg"

# The two ISO-year-boundary weeks this fixture keys its cross-year assertion
# on: 2023's own week 1 (2023-01-02..2023-01-08, left as bare rest days, full
# coverage) and 2024's own week 1 (2024-01-01..2024-01-07, seeded with seven
# load-less pages, thin coverage -- suppressed). Both are ISO week number 1;
# only the second is suppressed.
_UNCOVERED_WEEK_START = "2023-01-02"
_SUPPRESSED_WEEK_DAYS = (
    "2024-01-01",
    "2024-01-02",
    "2024-01-03",
    "2024-01-04",
    "2024-01-05",
    "2024-01-06",
    "2024-01-07",
)
_SERIES_START = "2022-12-15"
_SERIES_END = "2024-02-01"


def _write(root: Path, relpath: str, text: str) -> Path:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _page(
    *,
    day: str | None,
    load_value: float | None = None,
    load_methodology: str | None = None,
    effort_lines: str = "",
) -> str:
    """A minimal, syntactically valid fitdocs workout document -- matching
    `tests/history/test_engine.py` and `tests/test_cli_history.py`'s own
    `_page` fixture builder byte for byte, so this archive is read by the
    same real pipeline those modules exercise. `day=None` omits the `date`
    key entirely (the undated, skipped-page fixture)."""
    lines = ["---", "title: Test Workout", "type: workout"]
    if day is not None:
        lines.append(f'date: "{day}"')
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
    day: str | None,
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


def _write_archive(root: Path) -> None:
    """The one archive every test in this module reads (built fresh per
    `tmp_path`). See the module docstring for what each page contributes."""
    _write_page(
        root,
        "a-earliest",
        day=_SERIES_START,
        load_value=5.0,
        load_methodology="banister_1991",
    )
    _write_page(
        root,
        "b-race",
        day="2022-12-20",
        load_value=5.0,
        load_methodology="banister_1991",
        effort_lines=(
            "effort: race\neffort_distance_m: 5000\neffort_time_s: 1200\n"
            'effort_event: "Test 5K"'
        ),
    )
    _write_page(
        root,
        "c-excluded",
        day="2022-12-25",
        load_value=5.0,
        load_methodology="trimp_legacy",
    )
    _write_page(
        root,
        "d-malformed",
        day="2022-12-27",
        load_value=5.0,
        load_methodology="banister_1991",
        effort_lines=("effort: race\neffort_distance_m: 3000\neffort_time_s: abc"),
    )
    _write_page(root, "e-undated", day=None)
    for index, day in enumerate(_SUPPRESSED_WEEK_DAYS):
        _write_page(root, f"f-suppressed-{index}", day=day)
    _write_page(
        root,
        "g-latest",
        day=_SERIES_END,
        load_value=5.0,
        load_methodology="banister_1991",
    )


def _row(output: str, label: str) -> str:
    """The value cell of the report table row whose left cell is `label`
    (mirrors `tests/test_cli_history.py::_row`, duplicated locally since this
    module owns no shared import from that one)."""
    import re

    match = re.search(rf"│\s*{re.escape(label)}\s*│\s*(\S+)\s*│", output)
    assert match, f"no report row for {label!r} in:\n{output}"
    return match.group(1)


def _run(root: Path) -> object:
    return runner.invoke(
        app, ["history", "--out", str(root), "--methodology", "banister_1991"]
    )


@contextmanager
def _fake_system_date(fixed_timestamp: float, *, tz: str) -> Iterator[None]:
    """Fake the running process's own idea of "today" for the duration of
    the block (see the module docstring's "Fake-system-date coverage"
    paragraph for why `time.time` -- not `datetime.date.today` or
    `datetime.datetime.now` directly -- is the hook used). Reach: the hook
    fakes every read that goes through Python `time.time` -- `date.today()`,
    `datetime.today()`, a direct `time.time()` -- and does NOT reach
    `datetime.now()`, `time.localtime()`, `time.gmtime()` or
    `time.strftime()`, which are covered structurally by
    `tests/history/test_boundary.py` (`TestClockScan`'s substring scan and
    `TestImportClosure`'s allow-list). Also sets `SOURCE_DATE_EPOCH` (which
    nothing under `src/` reads) and `TZ`, restoring both afterward."""
    original_time = time.time
    original_tz = os.environ.get("TZ")
    original_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    time.time = lambda: fixed_timestamp  # type: ignore[assignment]
    os.environ["TZ"] = tz
    os.environ["SOURCE_DATE_EPOCH"] = str(int(fixed_timestamp))
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        yield
    finally:
        time.time = original_time
        if original_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original_tz
        if original_epoch is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = original_epoch
        if hasattr(time, "tzset"):
            time.tzset()


# ==============================================================================
# Success path: both outputs at the owned paths, the full report, the
# frontmatter's own criterion-point count (Req 8.1, 8.6).
# ==============================================================================


def test_success_writes_owned_paths_reports_counts_and_pins_frontmatter(
    tmp_path: Path,
) -> None:
    """Named mutation (owned-paths pin): write the document or chart to any
    path other than `layout.history_doc_path`/`layout.history_asset_path`
    (e.g. a stray `history/index.md`) -- the two `.exists()` assertions
    below, pinned to the *layout* functions themselves rather than to the
    hardcoded relative strings this module's other tests use -- the
    corresponding `.exists()` assertion reds (both, if both outputs move).

    Named mutation (frontmatter pin): drop the `criterion_points` key from
    `render_frontmatter` (`src/fitdocs/history/page.py`) -- `parsed` no
    longer carries the key at all, so `parsed["criterion_points"]` raises
    `KeyError` and the assertion below reds; a mutation that instead prints
    a fabricated `0` is caught separately since this fixture's own
    criterion-point count is 1 (`b-race`, a race tag with a recorded time),
    never 0 -- a pre-satisfied fixture is exactly the anti-pattern this
    count is built to avoid."""
    _write_archive(tmp_path)

    result = runner.invoke(
        app, ["history", "--out", str(tmp_path), "--methodology", "banister_1991"]
    )
    assert result.exit_code == 0, result.output

    doc_path = layout.history_doc_path(tmp_path)
    chart_path = layout.history_asset_path(tmp_path, layout.HISTORY_CHART)
    assert doc_path.exists()
    assert chart_path.exists()
    # Sanity: the layout functions and this module's own hardcoded relative
    # strings must agree, or the rest of this module's assertions (which use
    # the strings, matching the report's own printed text) would be testing
    # the wrong file.
    assert doc_path == tmp_path / _DOC_REL
    assert chart_path == tmp_path / _CHART_REL

    output = result.output
    assert _row(output, "Pages read") == "12"
    assert _row(output, "Contributing") == "4"
    assert _row(output, "Criterion points") == "1"
    assert "trimp_legacy: 1" in output

    doc_text = doc_path.read_text(encoding="utf-8")
    parsed = contract.parse_frontmatter(doc_text)
    assert parsed is not None
    assert parsed["criterion_points"] == 1
    assert isinstance(parsed["criterion_points"], int)


def test_the_written_chart_is_well_formed_xml(tmp_path: Path) -> None:
    """Named mutation: none needed as a fresh regression here -- the 5.2
    review found the chart once broken as XML (a `DOC_BANNER`-prefixed
    write, whose embedded `--` is invalid inside an XML comment); this test
    exists so that regression is pinned at the CLI's own writer, not only at
    the engine level `tests/history/test_engine.py` already covers. A
    non-well-formed rewrite (e.g. reintroducing `contract.DOC_BANNER` as the
    chart's leading line) makes `ET.fromstring` raise
    `xml.etree.ElementTree.ParseError` and this test reds."""
    _write_archive(tmp_path)

    result = _run(tmp_path)
    assert result.exit_code == 0, result.output

    chart_text = layout.history_asset_path(tmp_path, layout.HISTORY_CHART).read_text(
        encoding="utf-8"
    )
    ET.fromstring(chart_text)  # must not raise


# ==============================================================================
# Cross-ISO-year-boundary suppressed week (4.3 review finding).
# ==============================================================================


def test_suppressed_band_keys_by_iso_year_not_week_number_alone(
    tmp_path: Path,
) -> None:
    """2023's own ISO week 1 (`_UNCOVERED_WEEK_START`, bare rest days, full
    coverage) and 2024's own ISO week 1 (`_SUPPRESSED_WEEK_DAYS`, seven
    load-less pages, thin coverage) share an ISO week *number* but are
    eleven months apart and are not suppressed together: only the second is.

    Named mutation (the one the task brief names by name): in
    `_suppressed_day_indices` (`src/fitdocs/history/page.py`), key
    `suppressed_keys` by `week.iso_week` alone (drop `week.iso_year`) and
    match `iso_week in suppressed_keys` instead of the `(iso_year, iso_week)`
    pair. Both week 1s now compare equal under the (wrong) single-field key,
    so *every* day of 2023's own week 1 -- a week this fixture leaves fully
    covered and never suppressed -- is masked `None` in the chart's three
    series and gains its own `class="suppressed-band"` rect, alongside the
    genuinely suppressed 2024 week. The band-count assertion below (exactly
    one) reds, because the mutated code emits two non-adjacent bands (the
    two week-1s are eleven months apart, so no contiguous-run merge could
    ever hide the second one), and the specific-week assertion (the sole
    band's day-index range corresponds to `_SUPPRESSED_WEEK_DAYS`, not
    `_UNCOVERED_WEEK_START`) reds too if only one band happened to survive
    some other collapsing.

    Reachability precondition, asserted first: both weeks actually appear in
    the rendered series at all (their dates fall inside `series_start`/`end`
    -- this module's own fixture spans `_SERIES_START`..`_SERIES_END`, which
    encloses both), and the falsity-in-the-starting-state precondition --
    the uncovered week is *not* suppressed under the correct implementation
    -- is asserted before the band-count check that would catch its wrongful
    inclusion."""
    _write_archive(tmp_path)

    result = _run(tmp_path)
    assert result.exit_code == 0, result.output

    doc_text = layout.history_doc_path(tmp_path).read_text(encoding="utf-8")
    parsed = contract.parse_frontmatter(doc_text)
    assert parsed is not None
    # Reachability/falsity precondition: the series really does span both
    # target weeks (a fixture whose span excluded either one would pin
    # nothing about the cross-year key).
    assert parsed["series_start"] == "2022-12-15"
    assert parsed["series_end"] == "2024-02-01"

    chart_text = layout.history_asset_path(tmp_path, layout.HISTORY_CHART).read_text(
        encoding="utf-8"
    )
    root = ET.fromstring(chart_text)
    band_rects = [el for el in root.iter() if el.get("class") == "suppressed-band"]
    # Exactly one band: the 2024 week-1 seven-page, load-less week. The 2023
    # week-1 (bare rest days, full coverage) contributes none.
    assert len(band_rects) == 1, (
        f"expected exactly one suppressed band (the 2024 week-1 only), "
        f"got {len(band_rects)}: {[r.attrib for r in band_rects]}"
    )

    from datetime import date as _date

    series_start = _date.fromisoformat("2022-12-15")
    suppressed_start_index = (
        _date.fromisoformat(_SUPPRESSED_WEEK_DAYS[0]) - series_start
    ).days
    suppressed_end_index = (
        _date.fromisoformat(_SUPPRESSED_WEEK_DAYS[-1]) - series_start
    ).days
    uncovered_start_index = (
        _date.fromisoformat(_UNCOVERED_WEEK_START) - series_start
    ).days

    (band,) = band_rects
    x = float(band.attrib["x"])
    width = float(band.attrib["width"])
    day_count = (
        _date.fromisoformat(_SERIES_END) - _date.fromisoformat(_SERIES_START)
    ).days + 1
    assert width > 0  # non-degenerate band (sanity: real width)

    # Recompute the *exact* expected band geometry -- the same formula
    # `_render_suppressed_bands`/`_x_for_index` use (module-private, so
    # duplicated here rather than imported): a day-index maps onto
    # `_PLOT_LEFT + (index / (days - 1)) * _PLOT_WIDTH`, and a band extends
    # half a day-step past its own start/end index.
    _PLOT_LEFT = 56.0
    _PLOT_RIGHT = 800.0 - 20.0
    _PLOT_WIDTH = _PLOT_RIGHT - _PLOT_LEFT
    _step = _PLOT_WIDTH / max(day_count - 1, 1)

    def _x_for_index(index: int) -> float:
        return _PLOT_LEFT + (index / max(day_count - 1, 1)) * _PLOT_WIDTH

    expected_left = max(_PLOT_LEFT, _x_for_index(suppressed_start_index) - _step / 2)
    expected_right = min(_PLOT_RIGHT, _x_for_index(suppressed_end_index) + _step / 2)
    assert x == pytest.approx(expected_left, abs=0.1)
    assert width == pytest.approx(expected_right - expected_left, abs=0.1)

    # And the uncovered week's own day index must fall entirely outside the
    # rendered band -- the mutation this test names would instead produce a
    # *second* band there (caught by the count assertion above), or, if some
    # other implementation error collapsed the two into one wide band
    # spanning both, that wide band's left edge would sit at or before the
    # uncovered week's own x position, which this assertion also catches.
    uncovered_x = _x_for_index(uncovered_start_index)
    assert not (x <= uncovered_x <= x + width)


# ==============================================================================
# Byte-identical determinism: two runs, and two runs under two different
# fake system dates (Req 8.5).
# ==============================================================================


def test_two_runs_produce_byte_identical_document_and_chart(tmp_path: Path) -> None:
    """Named mutation: none new here -- `tests/history/test_engine.py`
    already pins this at the engine level; this run exists so the same
    property is demonstrated through the installed CLI over this module's
    own cross-year fixture, since a determinism break specific to this
    fixture's shape (e.g. dict/set iteration order over the suppressed-week
    keys) would not necessarily be caught by a smaller, single-year one."""
    _write_archive(tmp_path)

    first = _run(tmp_path)
    assert first.exit_code == 0, first.output
    doc_bytes_1 = layout.history_doc_path(tmp_path).read_bytes()
    chart_bytes_1 = layout.history_asset_path(
        tmp_path, layout.HISTORY_CHART
    ).read_bytes()

    second = _run(tmp_path)
    assert second.exit_code == 0, second.output
    doc_bytes_2 = layout.history_doc_path(tmp_path).read_bytes()
    chart_bytes_2 = layout.history_asset_path(
        tmp_path, layout.HISTORY_CHART
    ).read_bytes()

    assert doc_bytes_1 == doc_bytes_2
    assert chart_bytes_1 == chart_bytes_2


def test_two_runs_under_different_fake_system_dates_are_byte_identical(
    tmp_path: Path,
) -> None:
    """See the module docstring's "Fake-system-date coverage" paragraph for
    the mechanism and why it is `time.time`, not `datetime.date.today`/
    `datetime.datetime.now` directly.

    Named mutation (the one the task brief names by name): have the engine
    or the page renderer write `datetime.date.today().isoformat()` into the
    rendered markdown (e.g. append a stray "Generated: {date.today()}" line
    in `render_history`) -- run under 2019-06-01 first and 2031-11-20
    second, the two dates this test actually fakes render two different
    strings into that line, and the byte-identical assertion below reds.
    Without the mutation, `run_history` reads no clock at all, so the two
    runs are expected to be, and are, identical regardless of which of the
    two fake dates was active."""
    _write_archive(tmp_path)

    with _fake_system_date(
        time.mktime((2019, 6, 1, 12, 0, 0, 0, 0, -1)), tz="America/New_York"
    ):
        first = _run(tmp_path)
        assert first.exit_code == 0, first.output
        doc_bytes_1 = layout.history_doc_path(tmp_path).read_bytes()
        chart_bytes_1 = layout.history_asset_path(
            tmp_path, layout.HISTORY_CHART
        ).read_bytes()

    # A second, independent archive directory: this test is about the
    # *bytes produced from the same inputs*, not about idempotence over a
    # single directory (the previous test already covers that), so writing
    # into a fresh directory rules out any of the first run's own output
    # (foreign-file handling, declaration files) leaking into the second.
    second_root = tmp_path / "second"
    second_root.mkdir()
    _write_archive(second_root)

    with _fake_system_date(
        time.mktime((2031, 11, 20, 3, 0, 0, 0, 0, -1)), tz="Pacific/Auckland"
    ):
        second = _run(second_root)
        assert second.exit_code == 0, second.output
        doc_bytes_2 = layout.history_doc_path(second_root).read_bytes()
        chart_bytes_2 = layout.history_asset_path(
            second_root, layout.HISTORY_CHART
        ).read_bytes()

    assert doc_bytes_1 == doc_bytes_2
    assert chart_bytes_1 == chart_bytes_2


# ==============================================================================
# Empty archive: nothing written, no failure reported (Req 1.10).
# ==============================================================================


def test_empty_archive_writes_nothing_and_reports_no_failure(tmp_path: Path) -> None:
    """Named mutation: covered structurally at the engine level already
    (`tests/history/test_engine.py`); this is the CLI-level restatement Req
    1.10 asks for directly -- exit 0 (not a failure), and neither owned path
    created."""
    _write_page(tmp_path, "unscored", day="2024-01-01")

    result = _run(tmp_path)

    assert result.exit_code == 0, result.output
    assert not layout.history_doc_path(tmp_path).exists()
    assert not layout.history_asset_path(tmp_path, layout.HISTORY_CHART).exists()


# ==============================================================================
# Foreign-file rule: a pre-occupied owned path survives untouched, reported
# (Req 7.6).
# ==============================================================================


def test_foreign_file_at_the_document_path_survives_untouched_and_is_reported(
    tmp_path: Path,
) -> None:
    """Named mutation: covered at the engine level in `tests/history/
    test_engine.py`; restated here through the CLI's own report text, over
    this module's own multi-page archive rather than a minimal one."""
    _write_archive(tmp_path)
    doc_path = layout.history_doc_path(tmp_path)
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text("not fitdocs content\n", encoding="utf-8")

    result = _run(tmp_path)

    assert result.exit_code == 0, result.output
    assert _DOC_REL in result.output
    assert doc_path.read_text(encoding="utf-8") == "not fitdocs content\n"
