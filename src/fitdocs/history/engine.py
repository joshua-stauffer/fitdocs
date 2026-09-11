"""The `history` package's one writing module: orchestration, the two
writes, and the run report (load-history spec, task 5.2). See the
"HistoryEngine (`src/fitdocs/history/engine.py`)" component in
`.kiro/specs/load-history/design.md` (Req 1.9, 1.10, 4.2, 7.4, 7.5, 7.6, 8.1,
8.5, 8.6).

This module reads `fitdocs.toml` exactly once, through
:func:`fitdocs.settings.load_settings_document`, and projects it through both
per-table readers -- :func:`fitdocs.history.settings.load_history_settings`
for `[history]` and :func:`fitdocs.load.settings.load_load_settings` for
`[load]` (reading only `LoadSettings.default_calculator`, never extending
that table). It scans the archive once (`fitdocs.history.documents.scan_documents`),
resolves the one methodology the curve is summed under, builds the daily
series, runs the recursion once, aggregates the weekly table, the coverage
statement and the criterion-point count, renders the page, and writes it.

**The empty-archive gate runs before methodology resolution** (controller
decision, 2026-09-11, tasks.md "Implementation Notes"). The design's own
engine order -- resolve first, then build the series -- would turn "no page
in the whole archive records a load" into a `MethodologyProblem` and thus a
configuration exit, contradicting Req 1.10's "shall complete without
reporting a failure" and this plan's own "the empty archive writes nothing,
reports no failure" pin. So this module checks "every `PageRecord.load is
None`" first, and on that path writes nothing at all -- no outputs, no
declaration refresh, because the refresh only happens on a run that reaches
its write step.

**Ownership declarations** are refreshed, through the existing
`fitdocs.declaration.ensure_declarations`, once a run reaches its write step
-- immediately before the two writes, exactly where the design's sequence
diagram places it. That function iterates *every* entry in
`fitdocs.layout.DECLARED_DIRS`, so a history run may create or rewrite
`workouts/AGENTS.md` and `fit-archive/AGENTS.md`, and may create those
directories, on a data root that has never been synced -- inside the owned
set, not a violation (tasks.md's own framing, restated here because the
negative half this module actually honours is narrower: it never writes or
alters a `workouts/*.md` document, a `workouts/assets/` file, or a
`fit-archive/*.fit` source itself).

**Foreign-file rule (Req 7.6).** Before writing either output, this module
reads whatever currently occupies that path. A symlink, a directory, an
unreadable file or one that is not valid UTF-8 is treated the same as a file
whose text does not start a line with `contract.GENERATED_PREFIX` --
foreign, left untouched, and named in the report -- mirroring
`fitdocs.declaration`'s own `_read_existing` symlink-first handling (Req
7.5, 7.6): `Path.is_file()` alone follows symlinks and would read a dangling
one as merely absent. Absence is not foreign; the file is written.

**Write order and torn-state safety.** The chart is written first, the
document second, and each write is the same atomic
temp-file-in-the-same-directory-then-`os.replace` idiom
`fitdocs.load.engine._atomic_write` uses (a private helper of that module,
not imported here -- this module holds its own copy, because importing
`fitdocs.load.engine` from this package is exactly what the package boundary
guard (task 5.4) forbids by name). A chart write that raises aborts the run
before the document is ever attempted, so a crash never leaves a document
that cites a chart that was never written, and the document write failing on
its own is reported without disturbing an already-written chart.

Because the history chart carries no provenance marker of its own
(`fitdocs.render.charts.calendar.render_calendar_chart`'s own postcondition
is "a well-formed single `<svg>` element" -- design.md:1186 -- nothing else),
this module prepends its own module-local `_CHART_MARKER` as a line at the
top of the chart file before writing it, so a later run's foreign-file check
(`contract.is_generated`, a scan of *every* line, not only the first --
placement here is not what recognition depends on) can recognize a chart
this tool wrote; the marker sits at the top specifically because that is a
placement this module's own XML-validity constraint (below) allows without
inspecting the rest of `render_calendar_chart`'s output. `_CHART_MARKER` is
deliberately **not** `contract.DOC_BANNER`: the banner's prose contains a
literal ` -- ` em-dash rendered as two hyphens, which is forbidden inside an
XML comment's content (`--` may not appear between `<!--` and `-->`); an SVG
file is XML, and a banner-prefixed chart fails `xml.etree.ElementTree.fromstring`.
`_CHART_MARKER` is instead built as `f"{contract.GENERATED_PREFIX} -->"` --
an HTML/XML comment whose only content is a single space, the module's own
provenance text and a single space, none of it containing `--` -- so the
written file is valid XML and `contract.is_generated` (a line-prefix scan
against `GENERATED_PREFIX`) still recognizes it. The marker is not part of
`RenderedHistory.chart_svg` itself (task 4.3's own golden pins that string
with no such line) -- it is this module's own write-time addition, never
re-read by `render_calendar_chart` or by anything under `fitdocs.render.charts`.
`render_calendar_chart`'s own output starts directly with `<svg`, carrying no
`<?xml ...?>` declaration, so a leading HTML-style comment line is valid
placement -- were an XML declaration ever added, the marker would need to move
after it, since a comment preceding an XML declaration is itself invalid XML.

This module takes no `today` parameter and calls no clock. It writes no
`workouts/*.md` document, no `workouts/assets/` file and no
`fit-archive/*.fit` source, and neither `athlete.toml` nor `fitdocs.toml`
itself -- the narrowed form of "nothing under `workouts/`", deliberate
because the declaration refresh above legitimately writes
`workouts/AGENTS.md`.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fitdocs import contract
from fitdocs.contract import EffortKind
from fitdocs.declaration import ensure_declarations
from fitdocs.history.documents import DocumentScan, SkippedPage, scan_documents
from fitdocs.history.model import run_model
from fitdocs.history.page import render_history
from fitdocs.history.series import (
    MethodologyChoice,
    MethodologyProblem,
    build_daily_series,
    coverage_report,
    criterion_points,
    partition_pages,
    select_methodology,
    suppressed_weeks,
    week_rows,
)
from fitdocs.history.settings import load_history_settings, resolve_constants
from fitdocs.history.sources import COVERAGE_THRESHOLD
from fitdocs.layout import history_doc_path, settings_path
from fitdocs.load.settings import load_load_settings
from fitdocs.settings import SettingsError, load_settings_document

__all__ = [
    "HistoryReport",
    "MethodologyConfigurationError",
    "run_history",
]

#: The note this module states on the report when no page in the whole
#: archive records a load at all (Req 1.10) -- a single constant so the two
#: places that could plausibly need this wording (the report and, were a
#: caller ever to print it standalone) never drift apart.
_EMPTY_ARCHIVE_NOTE = (
    "no page in the archive records a load; nothing was written, and any "
    "existing history page was left untouched"
)

#: The temp-file prefix this module's own atomic-write idiom uses --
#: distinct from `fitdocs.load.engine`'s own `.load-` prefix, since the two
#: modules never share a helper (see the module docstring).
_TMP_PREFIX = ".history-"
_TMP_SUFFIX = ".tmp"

#: The chart file's own write-time provenance marker (see the module
#: docstring's "Because the history chart carries no provenance marker of its
#: own" paragraph) -- an XML-comment-safe alternative to `contract.DOC_BANNER`,
#: which contains a forbidden `--` inside an XML comment's content. Built from
#: `contract.GENERATED_PREFIX` so `contract.is_generated` still recognizes it
#: (that function matches on the prefix alone, at column zero).
_CHART_MARKER = f"{contract.GENERATED_PREFIX} -->"


class MethodologyConfigurationError(SettingsError):
    """A `MethodologyProblem` raised as a configuration fault (Req 4.4, 4.5).

    Subclasses the shared `fitdocs.settings.SettingsError`, exactly like
    `fitdocs.history.settings.HistorySettingsError`, so a CLI's existing
    `except SettingsError` handler maps this to the configuration exit with
    no new branch. Carries `MethodologyProblem.detail` verbatim as its
    message -- the ambiguous-methodology and configured-but-absent messages
    `select_methodology` already built.
    """


@dataclass(frozen=True)
class HistoryReport:
    """Everything a history run did or found (Req 8.6).

    `document`/`chart` are the data-root-relative paths actually written,
    `None` when that output was not written (the empty-archive path, a
    foreign occupant, or a write failure). `pages_read` is every page
    `scan_documents` placed (never counting a `SkippedPage`); `pages_excluded`
    is `MethodologyChoice.excluded` -- every other observed methodology and
    its page count; `pages_out_of_span` counts an *included*, load-less page
    whose date falls before the series' first contributing day or after its
    last (`fitdocs.history.series`'s own "left for a later pass to report"
    pages, Req 1.8, 3.10) -- always a subset of `pages_without_load`, since a
    page that actually records a load is by construction inside the span
    its own date helps define. `foreign` and `failures` name every output
    path left alone or that could not be written; `note` is set only on the
    empty-archive path.
    """

    document: str | None
    chart: str | None
    pages_read: int
    pages_contributing: int
    pages_without_load: int
    pages_excluded: tuple[tuple[str, int], ...]
    pages_out_of_span: int
    skipped: tuple[SkippedPage, ...]
    suppressed_weeks: int
    criterion_points: int
    methodology: str | None
    foreign: tuple[str, ...]
    failures: tuple[tuple[str, str], ...]
    note: str | None


def _relative_posix(data_root: Path, path: Path) -> str:
    """`path`, relative to `data_root`, in forward-slash form -- matching
    `fitdocs.history.documents`'s own (private) helper of the same name and
    intent, never a leaked absolute path in the report."""
    return path.relative_to(data_root).as_posix()


def _is_foreign_occupant(path: Path) -> bool:
    """True when something occupies `path` that this run must not write
    through (Req 7.6): a symlink (checked first and unconditionally, before
    any attempt to read through it -- `Path.is_file()` alone follows
    symlinks and would read a dangling one as merely absent), a directory, an
    unreadable file, a file that is not valid UTF-8, or a readable file whose
    text carries no line starting `contract.GENERATED_PREFIX`. Absence is
    never foreign -- `False` -- because there is nothing there to protect.
    Mirrors `fitdocs.declaration`'s own `_read_existing` handling of the same
    occupant classes for the same reason (Req 7.5, 7.6)."""
    if path.is_symlink():
        return True
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    except (OSError, UnicodeDecodeError):
        return True
    return not contract.is_generated(text)


def _atomic_write(path: Path, text: str) -> None:
    """Write `text` to `path` as a whole-file atomic replace -- the same
    temp-file-in-the-same-directory-then-`os.replace` idiom
    `fitdocs.load.engine._atomic_write` uses, held here as this module's own
    copy rather than an import (see the module docstring's "Write order and
    torn-state safety" section). `newline=""` disables newline translation
    so the exact string bytes are preserved; the temporary file is removed
    on any failure, so a crash never leaves a partial file at `path`."""
    directory = path.parent
    fd, tmp_name = tempfile.mkstemp(
        dir=directory, prefix=_TMP_PREFIX, suffix=_TMP_SUFFIX
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _reason(exc: OSError) -> str:
    """A concise, non-empty failure reason naming the error kind and its
    message -- the same shape `fitdocs.load.engine._reason` reports."""
    message = str(exc).strip()
    kind = type(exc).__name__
    return f"{kind}: {message}" if message else kind


def _empty_archive_report(scan: DocumentScan) -> HistoryReport:
    """The report for Req 1.10's empty-archive case: nothing written, no
    failure, the note set. `pages_read` and `pages_without_load` are both
    `len(scan.pages)` -- every scanned page, since none of them records a
    load by this path's own precondition (the gate that routes here is
    exactly `all(page.load is None for page in scan.pages)`). The
    criterion-point count is still computed -- it reads only `scan.pages`'
    own effort tags, needs no chosen methodology, and tasks.md's own report
    bullet lists it as one of the report's standing fields, with only `note`
    called out as the field this path adds."""
    return HistoryReport(
        document=None,
        chart=None,
        pages_read=len(scan.pages),
        pages_contributing=0,
        pages_without_load=len(scan.pages),
        pages_excluded=(),
        pages_out_of_span=0,
        skipped=scan.skipped,
        suppressed_weeks=0,
        criterion_points=criterion_points(scan.pages).count,
        methodology=None,
        foreign=(),
        failures=(),
        note=_EMPTY_ARCHIVE_NOTE,
    )


def run_history(data_root: Path, *, methodology: str | None = None) -> HistoryReport:
    """Run the whole history pass over `data_root` and return its report
    (Req 1.9, 1.10, 4.2, 7.4, 7.5, 7.6, 8.1, 8.5, 8.6).

    Reads `fitdocs.toml` once, projects `[history]` and `[load]`. Raises
    whatever `fitdocs.settings.SettingsError` subclass either table reader
    raises for a malformed table -- before any document is read. Scans the
    archive once; if every scanned page's `load` is `None`, returns
    immediately with nothing written (Req 1.10) and no declaration refresh.
    Otherwise resolves the one methodology the series is summed under,
    raising `MethodologyConfigurationError` (itself a `SettingsError`) on a
    `MethodologyProblem`, still before anything is written. Builds the daily
    series, runs the recursion once, aggregates the weekly table, the
    coverage statement (over the full scan's skipped count) and the
    criterion-point count (over the *full* scan, `scan.pages` -- Implementation
    Notes for 5.2/4.3: a criterion point is a fact about the tag, independent
    of which methodology the page's own load, if any, was recorded under).
    Refreshes the ownership declarations, then writes the chart and the
    document, each honouring the foreign-file rule and each reported by its
    own outcome.

    No `today` parameter, no clock read anywhere in this function or in
    anything it calls.
    """
    settings_file = settings_path(data_root)
    settings_document = load_settings_document(data_root)  # SettingsError propagates
    history_settings = load_history_settings(
        settings_document, settings_file
    )  # HistorySettingsError propagates
    load_settings = load_load_settings(
        settings_document, settings_file
    )  # LoadSettingsError propagates

    scan = scan_documents(data_root)

    if all(page.load is None for page in scan.pages):
        return _empty_archive_report(scan)

    configured = history_settings.methodology or load_settings.default_calculator
    choice = select_methodology(
        scan.pages, requested=methodology, configured=configured
    )
    if isinstance(choice, MethodologyProblem):
        raise MethodologyConfigurationError(choice.detail)
    assert isinstance(choice, MethodologyChoice)  # narrows for the type checker

    included, excluded = partition_pages(scan.pages, choice)
    series = build_daily_series(included)
    # `choice.methodology` is guaranteed present among `scan.pages`' own
    # methodologies (`select_methodology`'s own postcondition on every
    # non-Problem branch), and a page recording a methodology always records
    # a load with it (`documents._read_load`'s own invariant) -- so at least
    # one included page has `load is not None`, and `build_daily_series`
    # cannot return `None` here.
    assert series is not None, (
        "a resolved MethodologyChoice guarantees at least one loaded, "
        "included page -- build_daily_series must not return None here"
    )

    constants = resolve_constants(history_settings)
    threshold = (
        history_settings.coverage_threshold
        if history_settings.coverage_threshold is not None
        else COVERAGE_THRESHOLD.value
    )

    daily_loads = [day.recorded_load for day in series.days]
    model = run_model(daily_loads, constants)
    suppressed = suppressed_weeks(series, threshold)
    weeks = week_rows(series, model, suppressed)
    coverage = coverage_report(series, excluded, choice, len(scan.skipped))
    criterion = criterion_points(scan.pages)

    # Race markers only (Implementation Notes for 5.2, from the 4.3 review):
    # `render_history` labels EVERY marker it is handed as a race, so a
    # non-race effort must never reach it. Sourced from the FULL scan
    # (`scan.pages`), not the methodology partition (`included`) --
    # controller decision, 2026-09-11 remediation round 4: Req 5.4 ("when a
    # page is tagged as a race, mark that page's date on the chart") does
    # not condition on methodology, and the criterion-point precedent
    # (Implementation Notes above `criterion_points`) already treats a tag
    # as a fact about the page independent of its load's methodology -- a
    # race page excluded from `included` by `partition_pages` because it
    # records a different methodology is still marked, provided it falls
    # inside the span. Confined to pages the daily series can actually
    # place -- `series.start <= day <= series.end` -- because
    # `CalendarChartSpec`'s own precondition (design.md:1186) is "every
    # index is in range"; a race page (load-less or excluded) dated outside
    # the span (the same `pages_out_of_span` class the report counts) has no
    # day index to mark on a chart that draws nothing there (Req 1.8).
    markers = tuple(
        ((record.day - series.start).days, record)
        for record in scan.pages
        if record.effort is not None
        and record.effort.kind is EffortKind.RACE
        and series.start <= record.day <= series.end
    )

    rendered = render_history(
        series=series,
        model=model,
        weeks=weeks,
        coverage=coverage,
        criterion=criterion,
        markers=markers,
        choice=choice,
        constants=constants,
        threshold=threshold,
        skipped=scan.skipped,
        pages_read=len(scan.pages),
    )

    ensure_declarations(data_root)

    document_path = history_doc_path(data_root)
    chart_path = document_path.parent / rendered.chart_rel_path
    document_rel = _relative_posix(data_root, document_path)
    chart_rel = _relative_posix(data_root, chart_path)

    foreign: list[str] = []
    failures: list[tuple[str, str]] = []
    written_chart: str | None = None
    written_document: str | None = None

    # Chart first (Req 7.4, torn-state safety): a write failure here aborts
    # before the document is ever attempted, so a crash never leaves a
    # document that cites a chart this run never wrote.
    if _is_foreign_occupant(chart_path):
        foreign.append(chart_rel)
    else:
        try:
            chart_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(chart_path, _CHART_MARKER + "\n" + rendered.chart_svg)
            written_chart = chart_rel
        except OSError as exc:
            failures.append((chart_rel, _reason(exc)))

    chart_failed = bool(failures)
    if not chart_failed:
        if _is_foreign_occupant(document_path):
            foreign.append(document_rel)
        else:
            try:
                document_path.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write(document_path, rendered.markdown)
                written_document = document_rel
            except OSError as exc:
                failures.append((document_rel, _reason(exc)))

    pages_without_load = len([page for page in scan.pages if page.load is None])
    pages_contributing = len([page for page in included if page.load is not None])
    pages_out_of_span = len(
        [
            page
            for page in included
            if page.load is None and not (series.start <= page.day <= series.end)
        ]
    )

    return HistoryReport(
        document=written_document,
        chart=written_chart,
        pages_read=len(scan.pages),
        pages_contributing=pages_contributing,
        pages_without_load=pages_without_load,
        pages_excluded=choice.excluded,
        pages_out_of_span=pages_out_of_span,
        skipped=scan.skipped,
        suppressed_weeks=len(suppressed),
        criterion_points=criterion.count,
        methodology=choice.methodology,
        foreign=tuple(foreign),
        failures=tuple(failures),
        note=None,
    )
