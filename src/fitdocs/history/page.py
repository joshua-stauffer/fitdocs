"""The training-history document's own vocabulary, and its frontmatter block
(load-history spec, task 4.2; Req 5.8, 6.4).

This module declares the document's identity once, in one place: its
``type`` value, its title, its format version and the frontmatter key that
carries it, and the ordered tuple of every key the frontmatter block emits.
Nothing here re-spells the vocabulary :mod:`fitdocs.contract` already owns --
the ``---`` fence, the ``type``/``generator`` key names, the generator name
itself -- every one of those is imported from ``contract`` and used as-is. A
test asserts :data:`HISTORY_TYPE` differs from ``contract.WORKOUT_TYPE``, so a
history page and a workout page are never mistaken for one another by any
scan that reads ``type`` (Req 5.8).

**The frontmatter block is emitted as ordered plain text lines, never through
a YAML library.** Every value the block carries is machine-generated and
drawn from a closed set -- fixed strings, integers, and ISO dates -- except
one: the methodology identifier, a calculator id an athlete's settings (or a
plugin) may supply. That one free value is emitted bare when it is a plain
token (``[A-Za-z0-9_.-]+``) and double-quoted, with ``\\`` and ``"`` escaped,
otherwise; a control character or a newline anywhere in it is a hard failure
rather than a block quietly broken past the point a YAML parser can still
read it back. :mod:`fitdocs.render.frontmatter` -- the package's one YAML
*emission* touchpoint, and workout-docs' file -- is neither imported nor
touched by this module.

**Every number is formatted by one explicit rule** (four decimal places, via
Python's own ``f"{value:.4f}"`` format spec) so no platform's default float
representation -- scientific notation, a trailing ``.0`` some readers drop,
a locale-specific separator -- can leak into the bytes. **A value that is
genuinely unknown is omitted from the block entirely, never emitted as a
fabricated zero**: every constant this module accepts is ``| None``-typed for
exactly this reason, and the emitter skips a ``None`` field's key and value
outright rather than writing a placeholder a later reader could mistake for a
real, computed number.

``pages_read``, ``pages_with_load`` and ``criterion_points`` (Req 6.1, 6.4)
are the three counts this module always writes: unlike a constant that may be
genuinely absent, a real archive always has these counts -- zero is itself a
meaningful, real answer, never a stand-in for "unknown" -- so each is a
required ``int`` parameter, not an optional one, and the frontmatter round
trip always reads each one back as an ``int``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final

from fitdocs import contract, layout
from fitdocs.history.documents import PageRecord, SkippedPage
from fitdocs.history.model import ModelSeries
from fitdocs.history.series import (
    Coverage,
    CriterionPoints,
    DailySeries,
    MethodologyChoice,
    WeekRow,
)
from fitdocs.history.sources import ConstantProvenance, ModelConstants
from fitdocs.render import format
from fitdocs.render.charts.calendar import (
    CalendarBand,
    CalendarChartSpec,
    CalendarMarker,
    CalendarSeries,
    render_calendar_chart,
)
from fitdocs.render.charts.palette import FATIGUE_COLOR, FITNESS_COLOR, FORM_COLOR

# --- document vocabulary (Req 5.8) -------------------------------------------

HISTORY_TYPE: Final[str] = "training-history"
"""The frontmatter ``type`` value identifying the training-history document.

Distinct from :data:`fitdocs.contract.WORKOUT_TYPE` by construction -- a test
pins the inequality directly, so no future edit to either constant can quietly
make the two document kinds indistinguishable to a scan that reads ``type``.
"""

HISTORY_TITLE: Final[str] = "Training Load History"
"""The document's fixed title -- both the frontmatter ``title`` value and (task
4.3) the page's own heading text."""

HISTORY_VERSION: Final[int] = 1
"""The training-history document format's own version number -- independent of
:data:`fitdocs.contract.DOC_VERSION`, which versions the *workout* document
format instead."""

HISTORY_VERSION_KEY: Final[str] = "history_version"
"""The frontmatter key carrying :data:`HISTORY_VERSION`."""

HISTORY_FRONTMATTER_KEYS: Final[tuple[str, ...]] = (
    "title",
    contract.TYPE_KEY,
    contract.GENERATOR_KEY,
    HISTORY_VERSION_KEY,
    "methodology",
    "methodology_source",
    "constants_provenance",
    "tau_fitness_days",
    "tau_fatigue_days",
    "k_fitness",
    "k_fatigue",
    "coverage_threshold",
    "series_start",
    "series_end",
    "pages_read",
    "pages_with_load",
    "criterion_points",
)
"""Every frontmatter key this document emits, in emission order (Req 5.8).

Declared once, here, as the single source of truth for the key order; the
order :func:`render_frontmatter` actually writes is spelled independently in
that function's body (matching the design's key list, design.md:1224-1228) so
a test comparing the two catches either one drifting from the other."""

# --- emission rules -----------------------------------------------------------

_IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9_.-]+")
"""The plain-token shape a methodology identifier may be emitted bare in."""


def _reject_control_characters(value: str, *, field: str) -> None:
    """Raise if ``value`` carries a control character or newline anywhere.

    ``str.isprintable()`` is false for exactly this class of character (and
    true for an ordinary space, which a plain identifier may legitimately
    contain) -- the ASCII/Unicode "control or separator other than space"
    definition Python's own stdlib already carries, so this function spells no
    numeric code-point literal of its own.
    """
    if not value.isprintable():
        raise ValueError(
            f"{field} contains a control character or newline -- this would "
            "either break the frontmatter block's YAML syntax outright or "
            "silently embed an unreadable byte in it, so it is a hard "
            "failure rather than best-effort quoting"
        )


def _quote(value: str, *, field: str) -> str:
    """Double-quote ``value`` for the frontmatter block, escaping ``\\`` and
    ``"``. Used for every plain (non-identifier) string value the block
    carries."""
    _reject_control_characters(value, field=field)
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _format_identifier(value: str, *, field: str) -> str:
    """Format the one free value -- a methodology/calculator id -- per the
    design's quoting rule: bare when it is a plain token, double-quoted and
    escaped otherwise. A control character or newline is a hard failure
    regardless of which branch would otherwise apply."""
    _reject_control_characters(value, field=field)
    if _IDENTIFIER_PATTERN.fullmatch(value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _format_float(value: float) -> str:
    """Format a frontmatter float to a fixed four decimal places -- an
    explicit rule so no platform's default ``repr``/``str`` (scientific
    notation, a dropped trailing ``.0``) can leak into the bytes."""
    return f"{value:.4f}"


def render_frontmatter(
    *,
    methodology: str | None,
    methodology_source: str | None,
    constants_provenance: str | None,
    tau_fitness_days: float | None,
    tau_fatigue_days: float | None,
    k_fitness: float | None,
    k_fatigue: float | None,
    coverage_threshold: float | None,
    series_start: date | None,
    series_end: date | None,
    pages_read: int,
    pages_with_load: int,
    criterion_points: int,
) -> str:
    """Render the training-history document's frontmatter block, as ordered
    plain text lines fenced by :data:`fitdocs.contract.FRONTMATTER_FENCE`
    (Req 5.8, 6.4).

    Every ``| None``-typed parameter is a value that may genuinely be unknown
    -- no methodology could be selected, no constant set resolved, no page in
    the series at all -- and is omitted from the block entirely when ``None``,
    never emitted as a fabricated zero or empty string. ``pages_read``,
    ``pages_with_load`` and ``criterion_points`` are real counts that are
    always known (zero is itself a real, meaningful answer for each), so they
    are required and always written.

    Returns the block including its opening and closing fence lines and a
    trailing newline; the result parses through
    :func:`fitdocs.contract.parse_frontmatter` directly.
    """
    lines: list[str] = [contract.FRONTMATTER_FENCE]
    lines.append(f"title: {_quote(HISTORY_TITLE, field='title')}")
    lines.append(
        f"{contract.TYPE_KEY}: {_quote(HISTORY_TYPE, field=contract.TYPE_KEY)}"
    )
    lines.append(
        f"{contract.GENERATOR_KEY}: "
        f"{_quote(contract.GENERATOR, field=contract.GENERATOR_KEY)}"
    )
    lines.append(f"{HISTORY_VERSION_KEY}: {HISTORY_VERSION}")
    if methodology is not None:
        lines.append(
            f"methodology: {_format_identifier(methodology, field='methodology')}"
        )
    if methodology_source is not None:
        lines.append(
            f"methodology_source: "
            f"{_quote(methodology_source, field='methodology_source')}"
        )
    if constants_provenance is not None:
        lines.append(
            f"constants_provenance: "
            f"{_quote(constants_provenance, field='constants_provenance')}"
        )
    if tau_fitness_days is not None:
        lines.append(f"tau_fitness_days: {_format_float(tau_fitness_days)}")
    if tau_fatigue_days is not None:
        lines.append(f"tau_fatigue_days: {_format_float(tau_fatigue_days)}")
    if k_fitness is not None:
        lines.append(f"k_fitness: {_format_float(k_fitness)}")
    if k_fatigue is not None:
        lines.append(f"k_fatigue: {_format_float(k_fatigue)}")
    if coverage_threshold is not None:
        lines.append(f"coverage_threshold: {_format_float(coverage_threshold)}")
    if series_start is not None:
        lines.append(
            f"series_start: {_quote(series_start.isoformat(), field='series_start')}"
        )
    if series_end is not None:
        lines.append(
            f"series_end: {_quote(series_end.isoformat(), field='series_end')}"
        )
    lines.append(f"pages_read: {pages_read}")
    lines.append(f"pages_with_load: {pages_with_load}")
    lines.append(f"criterion_points: {criterion_points}")
    lines.append(contract.FRONTMATTER_FENCE)
    return "\n".join(lines) + "\n"


# ==============================================================================
# Body sections (task 4.3; Req 2.2, 2.5, 2.7, 2.11, 3.5, 3.7, 3.10, 5.4-5.10,
# 6.1-6.5). Everything below the frontmatter block: the generated banner, the
# title, the chart with its numbered race list, the constants-and-scale
# paragraph, the coverage statement, the criterion-performance section, the
# weekly table, and the skipped-and-excluded list -- in that fixed order.
# ==============================================================================


_CHART_Y_LABEL: Final[str] = "fitness / fatigue / form (daily-average load)"

_DASH: Final[str] = "—"
"""The one glyph a suppressed week's fitness/fatigue/form values are shown
as -- never a fabricated ``0.0`` (Req 3.7, the "shown as a dash" rule)."""

_PROVENANCE_WORDING: Final[dict[ConstantProvenance, str]] = {
    ConstantProvenance.SEEDS: "fitdocs' shipped seed values",
    ConstantProvenance.CONFIGURED: (
        "the athlete's own configured values -- not fitdocs' shipped defaults"
    ),
    ConstantProvenance.FITTED: (
        "values fitted to the athlete's own data -- not fitdocs' shipped defaults"
    ),
}
"""How the constants paragraph names a :class:`ConstantProvenance` in prose
(Req 2.5, 2.7, 2.10). The configured and fitted wordings each state plainly
that the constants are *not* the shipped defaults (Req 2.7's own words --
"that they are the athlete's, not the shipped ones"), while never repeating
the SEEDS entry's exact phrase ("shipped seed values") -- so a mutation that
mislabels a configured or fitted set with the seeds wording is
distinguishable by substring search, not merely by meaning."""

_NEVER_FITTED_SENTENCE: Final[str] = (
    "fitdocs' shipped seed constants are illustrative starting values from "
    "the primary literature and were never fitted to any athlete."
)
"""Req 2.5's own wording requirement, printed on every page regardless of
which constant set is actually in force (Req 2.5, 2.10) -- copy-pinned so a
later edit cannot quietly soften it."""

_DAILY_AVERAGE_SCALE_SENTENCE: Final[str] = (
    "Fitness and fatigue are reported on the recursion's own daily-average "
    "scale -- each accumulator multiplied by its weighting and by "
    "(1 - e^(-1/tau)) -- so the number is in the same per-day units as a "
    "single day's load no matter how long the archive has been running."
)

_CAVEAT_ZERO_START_SENTENCE: Final[str] = (
    "The fitness and fatigue accumulators start at zero, so the earliest "
    "weeks of the series understate them."
)
_CAVEAT_SUPPRESSED_GAP_SENTENCE: Final[str] = (
    "Values reported after a suppressed period understate fitness and "
    "fatigue by whatever load went unrecorded during it."
)

_NO_CONCLUSION_SENTENCE: Final[str] = "fitdocs draws no conclusion from this count."

_FORBIDDEN_PHRASE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(forecast\w*|readiness|verdict|overload|recommend\w*"
    r"|(?:zone|plan|cycle|block)s?)\b",
    re.IGNORECASE,
)
"""Every phrase this document must never carry (Req 2.11, 5.10): no
forecast, zone, readiness verdict, overload warning, recommendation, plan,
cycle or block content -- singular or plural (``zones``, ``blocks``, ...).
Word-bounded on both ends, so a longer word that merely carries one of
these as a leading substring (``planned``, ``blocked``) never trips it,
and a word that never contains the literal substring at all (``cycling``
does not contain ``cycle``) is unaffected either way. Exported for the
test module's own forbidden-phrase assertion."""


def _fmt1(value: float) -> str:
    """Format a load or model value to one decimal place -- the explicit
    rule this task's body sections use for every such number, so no
    platform's default ``str``/``repr`` of a float can leak into the bytes."""
    return f"{value:.1f}"


def _fmt1_or_dash(value: float | None) -> str:
    """A suppressed week's fitness/fatigue/form is ``None`` and is shown as
    :data:`_DASH`, never as a fabricated ``0.0`` (Req 3.7)."""
    return _DASH if value is None else _fmt1(value)


def _fmt_pct(fraction: float) -> str:
    """Format a coverage fraction as a percentage to one decimal place."""
    return f"{fraction:.1%}"


def _fmt_date_or_none(value: date | None) -> str:
    return "none" if value is None else value.isoformat()


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    """``singular`` for ``count == 1``, else ``plural`` (default:
    ``singular`` with an ``s`` appended) -- used everywhere this module
    counts a noun so a count of one never reads as "1 pages"/"1 criterion
    points"."""
    if count == 1:
        return singular
    return plural if plural is not None else f"{singular}s"


def _suppressed_day_indices(series: DailySeries, weeks: Sequence[WeekRow]) -> set[int]:
    """Every index into `series.days` that falls inside a suppressed
    `WeekRow` (Req 3.8), found by matching each day's own ISO `(year, week)`
    against the suppressed rows' -- never by walking a fixed 7-day offset
    from `monday`, so a partial first/last week is handled the same way as
    a full one."""
    suppressed_keys = {
        (week.iso_year, week.iso_week) for week in weeks if week.suppressed
    }
    indices: set[int] = set()
    for index, day_load in enumerate(series.days):
        iso_year, iso_week, _weekday = day_load.day.isocalendar()
        if (iso_year, iso_week) in suppressed_keys:
            indices.add(index)
    return indices


def _contiguous_bands(indices: set[int]) -> tuple[CalendarBand, ...]:
    """Group a set of day indices into contiguous inclusive `CalendarBand`
    ranges, sorted ascending."""
    bands: list[CalendarBand] = []
    run_start: int | None = None
    previous: int | None = None
    for index in sorted(indices):
        if run_start is None:
            run_start = index
        elif previous is not None and index != previous + 1:
            bands.append(CalendarBand(start_index=run_start, end_index=previous))
            run_start = index
        previous = index
    if run_start is not None and previous is not None:
        bands.append(CalendarBand(start_index=run_start, end_index=previous))
    return tuple(bands)


def _build_chart(
    series: DailySeries,
    model: ModelSeries,
    weeks: Sequence[WeekRow],
    markers: Sequence[tuple[int, PageRecord]],
) -> CalendarChartSpec:
    """Build the `CalendarChartSpec` from the assembled series (Req 5.2,
    5.3, 5.4): markers numbered in the order given, suppressed bands from
    the weekly table's own `suppressed` flags, and a `None` value on every
    suppressed day of each of the three series (Req 3.8) -- never the
    model's real, computed value for a day the coverage statement says was
    too thin to draw."""
    suppressed_indices = _suppressed_day_indices(series, weeks)
    day_count = len(series.days)

    def _values(raw: tuple[float, ...]) -> tuple[float | None, ...]:
        return tuple(
            None if index in suppressed_indices else raw[index]
            for index in range(day_count)
        )

    chart_markers = tuple(
        CalendarMarker(day_index=day_index, number=number)
        for number, (day_index, _record) in enumerate(markers, start=1)
    )
    return CalendarChartSpec(
        start=series.start,
        days=day_count,
        series=(
            CalendarSeries("fitness", FITNESS_COLOR, _values(model.fitness)),
            CalendarSeries("fatigue", FATIGUE_COLOR, _values(model.fatigue)),
            CalendarSeries("form", FORM_COLOR, _values(model.form)),
        ),
        markers=chart_markers,
        suppressed=_contiguous_bands(suppressed_indices),
        y_label=_CHART_Y_LABEL,
    )


def _marker_result_text(record: PageRecord) -> str:
    """The result a race marker's own tag records, or "no result recorded"
    (Req 5.5) -- never a fabricated result for a race with none.

    The recorded time is rendered through the shared
    :func:`fitdocs.render.format.fmt_duration` (``h:mm:ss``/``m:ss``), not
    this module's own ``_fmt1`` (raw seconds to one decimal) -- a duration
    is not a load or model value, and the shared formatter is what every
    other document in the package already uses for one. The distance is
    shown alongside it, through :func:`fitdocs.render.format.fmt_distance_km`,
    only when the tag actually carries one.
    """
    tag = record.effort
    if tag is None or tag.time_s is None:
        return "no result recorded"
    event_prefix = f"{tag.event} — " if tag.event else ""
    duration = format.fmt_duration(tag.time_s)
    assert duration is not None  # tag.time_s is not None, checked above
    distance = format.fmt_distance_km(tag.distance_m)
    distance_suffix = f" ({distance})" if distance is not None else ""
    return f"{event_prefix}finished in {duration}{distance_suffix}"


def _render_chart_section(
    chart_rel_path: str, markers: Sequence[tuple[int, PageRecord]]
) -> str:
    lines = [
        "## Training Load Chart",
        "",
        f"![{HISTORY_TITLE} chart]({chart_rel_path})",
    ]
    if markers:
        lines.append("")
        lines.append("Races:")
        for number, (_day_index, record) in enumerate(markers, start=1):
            lines.append(
                f"{number}. {record.day.isoformat()} — {_marker_result_text(record)}"
            )
    return "\n".join(lines)


def _render_constants_section(constants: ModelConstants, threshold: float) -> str:
    wording = _PROVENANCE_WORDING[constants.provenance]
    return "\n".join(
        [
            "## Model Constants",
            "",
            f"This page's curve was computed with {wording}: "
            f"tau_fitness = {_fmt1(constants.tau_fitness_days)} days, "
            f"tau_fatigue = {_fmt1(constants.tau_fatigue_days)} days, "
            f"k_fitness = {_fmt1(constants.k_fitness)}, "
            f"k_fatigue = {_fmt1(constants.k_fatigue)}.",
            "",
            f"Origin: {constants.origin}",
            "",
            _DAILY_AVERAGE_SCALE_SENTENCE,
            "",
            _NEVER_FITTED_SENTENCE,
            "",
            f"A period whose share of pages recording a load falls below "
            f"{_fmt_pct(threshold)} has its curve suppressed rather than "
            f"drawn.",
            "",
            _CAVEAT_ZERO_START_SENTENCE,
            "",
            _CAVEAT_SUPPRESSED_GAP_SENTENCE,
        ]
    )


def _fmt_excluded(pairs: Sequence[tuple[str, int]]) -> str:
    if not pairs:
        return "none"
    return ", ".join(f"{name}: {count}" for name, count in pairs)


def _render_coverage_section(coverage: Sequence[Coverage]) -> str:
    lines = ["## Coverage", ""]
    for row in coverage:
        pct = _fmt_pct(row.fraction)
        line = (
            f"- {row.label}: {row.pages} {_plural(row.pages, 'page')}, "
            f"{row.pages_with_load} recording a load ({pct}); "
            f"excluded: {_fmt_excluded(row.pages_excluded)}"
        )
        if row.pages_skipped is not None:
            line += f"; skipped: {row.pages_skipped}"
        lines.append(line)
    return "\n".join(lines)


def _render_criterion_section(criterion: CriterionPoints) -> str:
    counts_by_kind = dict(criterion.by_kind)
    race_count = counts_by_kind.get(contract.EffortKind.RACE, 0)
    test_count = counts_by_kind.get(contract.EffortKind.TEST, 0)
    excluded_total = sum(count for _reason, count in criterion.excluded) + len(
        criterion.malformed
    )
    lines = [
        "## Criterion-Performance Report",
        "",
        f"{criterion.count} "
        f"{_plural(criterion.count, 'criterion point')}: {race_count} race, "
        f"{test_count} test — pages carrying a valid effort tag of kind "
        "race or test together with an official time. Earliest "
        f"{_fmt_date_or_none(criterion.earliest)}, latest "
        f"{_fmt_date_or_none(criterion.latest)}.",
        "",
        f"Excluded from the count: {excluded_total} "
        f"{_plural(excluded_total, 'tagged page')}.",
    ]
    for reason, count in criterion.excluded:
        lines.append(f"- {count}: {reason}")
    if criterion.malformed:
        malformed_count = len(criterion.malformed)
        lines.append(f"- {malformed_count} with a malformed tag:")
        for path, description in criterion.malformed:
            lines.append(f"  - `{path}`: {description}")
    lines.append("")
    lines.append(_NO_CONCLUSION_SENTENCE)
    return "\n".join(lines)


def _render_weekly_table(weeks: Sequence[WeekRow]) -> str:
    lines = [
        "## Weekly Table",
        "",
        "| Week (Monday) | Total load | Sessions | Pages w/ load | Fitness | "
        "Fatigue | Form | Note |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for week in weeks:
        note = "suppressed — coverage below threshold" if week.suppressed else ""
        lines.append(
            f"| {week.monday.isoformat()} | {_fmt1(week.total_load)} | "
            f"{week.sessions} | {week.pages_with_load}/{week.pages} | "
            f"{_fmt1_or_dash(week.fitness)} | {_fmt1_or_dash(week.fatigue)} | "
            f"{_fmt1_or_dash(week.form)} | {note} |"
        )
    return "\n".join(lines)


def _render_skipped_excluded_section(
    skipped: Sequence[SkippedPage], choice: MethodologyChoice
) -> str:
    lines = ["## Skipped and Excluded", ""]
    lines.append("Skipped (date could not be read):")
    if skipped:
        for page in skipped:
            lines.append(f"- `{page.path}` — {page.reason}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("Excluded (recording another methodology):")
    if choice.excluded:
        for methodology, count in choice.excluded:
            lines.append(f"- {methodology}: {count} {_plural(count, 'page')}")
    else:
        lines.append("- none")
    return "\n".join(lines)


@dataclass(frozen=True)
class RenderedHistory:
    """The two artifacts a history run writes (Req 5.1): the document's own
    markdown, its chart SVG, and the doc-relative link the markdown embeds
    the chart with."""

    markdown: str
    chart_svg: str
    chart_rel_path: str


def render_history(
    *,
    series: DailySeries,
    model: ModelSeries,
    weeks: Sequence[WeekRow],
    coverage: Sequence[Coverage],
    criterion: CriterionPoints,
    markers: Sequence[tuple[int, PageRecord]],
    choice: MethodologyChoice,
    constants: ModelConstants,
    threshold: float,
    skipped: Sequence[SkippedPage],
    pages_read: int,
) -> RenderedHistory:
    """Render the training-history document, in full (Req 2.2, 2.5, 2.7,
    2.11, 3.5, 3.7, 3.10, 5.4-5.10, 6.1-6.5).

    Pure: no `Path`, no clock, no I/O -- every value the document states is
    read from an argument, never from the filesystem or the wall clock. The
    same inputs always render byte-identical output.

    Section order, fixed: the frontmatter block; the generated banner; the
    title; the chart with its numbered race list; the constants-and-scale
    paragraph; the coverage statement; the criterion-performance section;
    the weekly table; the skipped-and-excluded list.
    """
    all_coverage = next(row for row in coverage if row.label == "all")
    chart_rel_path = layout.history_asset_rel_path(layout.HISTORY_CHART)
    chart_spec = _build_chart(series, model, weeks, markers)
    chart_svg = render_calendar_chart(chart_spec)

    frontmatter = render_frontmatter(
        methodology=choice.methodology,
        methodology_source=choice.source,
        constants_provenance=constants.provenance,
        tau_fitness_days=constants.tau_fitness_days,
        tau_fatigue_days=constants.tau_fatigue_days,
        k_fitness=constants.k_fitness,
        k_fatigue=constants.k_fatigue,
        coverage_threshold=threshold,
        series_start=series.start,
        series_end=series.end,
        pages_read=pages_read,
        pages_with_load=all_coverage.pages_with_load,
        criterion_points=criterion.count,
    )

    body = "\n\n".join(
        [
            frontmatter.rstrip("\n"),
            contract.DOC_BANNER,
            f"# {HISTORY_TITLE}",
            _render_chart_section(chart_rel_path, markers),
            _render_constants_section(constants, threshold),
            _render_coverage_section(coverage),
            _render_criterion_section(criterion),
            _render_weekly_table(weeks),
            _render_skipped_excluded_section(skipped, choice),
        ]
    )
    markdown = body + "\n"
    return RenderedHistory(
        markdown=markdown, chart_svg=chart_svg, chart_rel_path=chart_rel_path
    )
