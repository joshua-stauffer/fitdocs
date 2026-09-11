"""Tests for the training-history document (load-history spec).

One headed section per task (tasks.md, Test File Ownership): the document
vocabulary and the frontmatter emitter -> task 4.2 (this section). Task 4.3
adds the body sections and the two goldens beneath ``tests/history/golden/``
in its own section below; neither task edits the other's.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from fitdocs import contract
from fitdocs.contract import EffortKind, EffortTag
from fitdocs.history import model as history_model
from fitdocs.history import page
from fitdocs.history.documents import PageRecord, SkippedPage
from fitdocs.history.model import ModelSeries
from fitdocs.history.series import (
    Coverage,
    CriterionPoints,
    DailySeries,
    MethodologyChoice,
    WeekRow,
    build_daily_series,
    coverage_report,
    criterion_points,
    partition_pages,
    select_methodology,
    suppressed_weeks,
    week_rows,
)
from fitdocs.history.sources import SEED_CONSTANTS, ConstantProvenance, ModelConstants

# ==============================================================================
# 4.2: the document vocabulary and the frontmatter emitter (Req 5.8, 6.4)
# ==============================================================================


def _full_frontmatter() -> str:
    """A frontmatter block with every optional value populated -- the
    golden-path fixture the order and round-trip tests share."""
    return page.render_frontmatter(
        methodology="banister_1991",
        methodology_source="configured",
        constants_provenance="seeds",
        tau_fitness_days=45.0,
        tau_fatigue_days=15.0,
        k_fitness=1.0,
        k_fatigue=2.0,
        coverage_threshold=0.8,
        series_start=date(2023, 1, 5),
        series_end=date(2024, 6, 30),
        pages_read=612,
        pages_with_load=530,
        criterion_points=7,
    )


def test_history_type_differs_from_workout_type() -> None:
    """Req 5.8: a history page and a workout page must never be mistaken for
    one another by a scan that reads ``type``.

    Mutation: set ``HISTORY_TYPE = contract.WORKOUT_TYPE`` in page.py -- this
    assertion reds directly.
    """
    assert page.HISTORY_TYPE != contract.WORKOUT_TYPE
    assert page.HISTORY_TYPE == "training-history"


def test_history_title_matches_the_design_exactly() -> None:
    """Pins the exact title string design.md:1263 specifies.

    Mutation W: change ``HISTORY_TITLE`` to ``"training_history"`` (the type
    value with underscores, a plausible copy/paste of the wrong constant) --
    this assertion reds.
    """
    assert page.HISTORY_TITLE == "Training Load History"


def test_history_frontmatter_keys_exact_order() -> None:
    """Pins the declared key tuple itself, independent of what the emitter
    actually writes (see test below for that pairing).

    Mutation: swap any two adjacent entries in ``HISTORY_FRONTMATTER_KEYS`` --
    this assertion reds.
    """
    assert page.HISTORY_FRONTMATTER_KEYS == (
        "title",
        "type",
        "generator",
        "history_version",
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


def _emitted_key_order(block: str) -> list[str]:
    keys: list[str] = []
    for line in block.splitlines():
        if line in (contract.FRONTMATTER_FENCE,):
            continue
        if ":" in line:
            keys.append(line.split(":", 1)[0])
    return keys


def test_render_frontmatter_emits_keys_in_the_declared_order() -> None:
    """The emitter's own, independently-spelled key order must match
    ``HISTORY_FRONTMATTER_KEYS`` exactly, for a fixture where every optional
    value is present (so no key is skipped).

    Named mutation (tasks.md): reorder the keys in the emitter's body -- this
    assertion reds; ``test_history_frontmatter_keys_exact_order`` above stays
    green because the *declared* tuple is untouched, proving the two tests
    pin independent claims.
    """
    block = _full_frontmatter()
    assert _emitted_key_order(block) == list(page.HISTORY_FRONTMATTER_KEYS)


def test_render_frontmatter_opens_and_closes_with_the_shared_fence() -> None:
    """Req 5.8: the block opens and closes with
    ``contract.FRONTMATTER_FENCE`` -- the *closing* fence is the block's
    actual last line, not merely present somewhere after the opening one.

    Not independently mutation-pinned against a hardcoded ``"---"``: the two
    values are identical today, so this assertion cannot by itself
    discriminate importing the constant from re-spelling it. That
    discrimination is instead
    ``test_page_module_spells_no_contract_vocabulary_itself`` below, which
    scans the module's own source for the literal.

    Mutation X: append a stray line after the closing fence (~page.py:229)
    -- ``lines[-1] == contract.FRONTMATTER_FENCE`` reds because the fence is
    no longer the last line.
    Mutation N: drop the trailing newline the function returns (~page.py:230)
    -- ``block.endswith(contract.FRONTMATTER_FENCE + "\\n")`` reds.
    """
    block = _full_frontmatter()
    lines = block.splitlines()
    assert lines[0] == contract.FRONTMATTER_FENCE
    assert lines[-1] == contract.FRONTMATTER_FENCE
    assert block.endswith(contract.FRONTMATTER_FENCE + "\n")


def test_page_module_spells_no_contract_vocabulary_itself() -> None:
    """The module never re-spells, as a second literal of its own, any of the
    vocabulary it is required to import from :mod:`fitdocs.contract` instead:
    the fence, the ``type``/``generator`` key names, the generator name, or
    the workout-type marker (mirrors
    ``tests/test_contract_consumers.py:296-318``, the same guard applied to
    the converted workout consumers).

    Mutation: replace ``contract.FRONTMATTER_FENCE`` with a literal ``"---"``
    at the top of ``render_frontmatter`` (~page.py:183) -- this assertion
    reds as the sole failure; every other test in this module still passes
    because the literal and the imported constant are equal in value, which
    is exactly why this scan -- over the module's own AST, not its output --
    is the only thing that can tell the two apart.
    """
    tree = ast.parse(inspect.getsource(page))
    forbidden = {
        contract.FRONTMATTER_FENCE,
        contract.TYPE_KEY,
        contract.GENERATOR_KEY,
        contract.GENERATOR,
        contract.WORKOUT_TYPE,
    }
    assert any(
        isinstance(node, ast.Constant) and node.value == page.HISTORY_TYPE
        for node in ast.walk(tree)
    ), "the scan did not see page.py's own body"

    spelled = sorted(
        {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in forbidden
        }
    )
    assert not spelled, spelled


def test_render_frontmatter_round_trip_types() -> None:
    """Req 6.4: every key reads back through the document contract's own
    parser with the expected type, including the criterion-point count as an
    integer.

    Mutation: emit ``criterion_points`` as a quoted string
    (``f'"{criterion_points}"'``) -- this assertion reds on the
    ``isinstance(..., int)`` check while the block still parses.
    """
    block = _full_frontmatter()
    parsed = contract.parse_frontmatter(block)
    assert parsed is not None

    assert parsed["title"] == page.HISTORY_TITLE
    assert isinstance(parsed["title"], str)
    assert parsed[contract.TYPE_KEY] == page.HISTORY_TYPE
    assert parsed[contract.TYPE_KEY] != contract.WORKOUT_TYPE
    assert parsed[contract.GENERATOR_KEY] == contract.GENERATOR
    assert parsed[page.HISTORY_VERSION_KEY] == page.HISTORY_VERSION
    assert isinstance(parsed[page.HISTORY_VERSION_KEY], int)
    assert parsed["methodology"] == "banister_1991"
    assert parsed["methodology_source"] == "configured"
    assert parsed["constants_provenance"] == "seeds"
    for key in (
        "tau_fitness_days",
        "tau_fatigue_days",
        "k_fitness",
        "k_fatigue",
        "coverage_threshold",
    ):
        assert isinstance(parsed[key], float), key
    assert parsed["tau_fitness_days"] == pytest.approx(45.0)
    assert parsed["tau_fatigue_days"] == pytest.approx(15.0)
    assert parsed["k_fitness"] == pytest.approx(1.0)
    assert parsed["k_fatigue"] == pytest.approx(2.0)
    assert parsed["coverage_threshold"] == pytest.approx(0.8)
    assert parsed["series_start"] == "2023-01-05"
    assert parsed["series_end"] == "2024-06-30"
    assert isinstance(parsed["pages_read"], int)
    assert parsed["pages_read"] == 612
    assert isinstance(parsed["pages_with_load"], int)
    assert parsed["pages_with_load"] == 530
    assert isinstance(parsed["criterion_points"], int)
    assert parsed["criterion_points"] == 7


def test_render_frontmatter_omits_unknown_values_rather_than_zero() -> None:
    """A value that is genuinely unknown -- no methodology could be chosen,
    no constant set resolved, no page in the series at all -- is omitted from
    the block entirely, never emitted as a fabricated zero.

    Named mutation (tasks.md): emit an unknown value as zero -- e.g. replace
    every ``if x is not None:`` guard with unconditional emission using
    ``x or 0.0`` -- this assertion reds because the key becomes present with
    a fabricated ``0.0``/``""`` instead of staying absent.
    """
    block = page.render_frontmatter(
        methodology=None,
        methodology_source=None,
        constants_provenance=None,
        tau_fitness_days=None,
        tau_fatigue_days=None,
        k_fitness=None,
        k_fatigue=None,
        coverage_threshold=None,
        series_start=None,
        series_end=None,
        pages_read=0,
        pages_with_load=0,
        criterion_points=0,
    )
    parsed = contract.parse_frontmatter(block)
    assert parsed is not None

    omittable = {
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
    }
    for key in omittable:
        assert key not in parsed, (key, parsed[key])

    # The three real, always-known counts stay present, and a real zero is a
    # real value -- distinguishable from "the key is entirely absent" above.
    assert parsed["pages_read"] == 0
    assert parsed["pages_with_load"] == 0
    assert parsed["criterion_points"] == 0
    assert isinstance(parsed["criterion_points"], int)


def test_identifier_quoting_plain_token_is_emitted_bare() -> None:
    block = page.render_frontmatter(
        methodology="banister_1991",
        methodology_source=None,
        constants_provenance=None,
        tau_fitness_days=None,
        tau_fatigue_days=None,
        k_fitness=None,
        k_fatigue=None,
        coverage_threshold=None,
        series_start=None,
        series_end=None,
        pages_read=0,
        pages_with_load=0,
        criterion_points=0,
    )
    assert "methodology: banister_1991\n" in block
    parsed = contract.parse_frontmatter(block)
    assert parsed is not None
    assert parsed["methodology"] == "banister_1991"


def test_identifier_quoting_dotted_token_is_emitted_bare() -> None:
    block = page.render_frontmatter(
        methodology="banister.v2",
        methodology_source=None,
        constants_provenance=None,
        tau_fitness_days=None,
        tau_fatigue_days=None,
        k_fitness=None,
        k_fatigue=None,
        coverage_threshold=None,
        series_start=None,
        series_end=None,
        pages_read=0,
        pages_with_load=0,
        criterion_points=0,
    )
    assert "methodology: banister.v2\n" in block
    parsed = contract.parse_frontmatter(block)
    assert parsed is not None
    assert parsed["methodology"] == "banister.v2"


def test_identifier_with_a_colon_is_quoted() -> None:
    """The colon fixture, ``"vendor: custom"``, pins the "unparseable bare"
    branch specifically: a colon immediately followed by a space is YAML
    block-mapping syntax, so a buggy implementation that emitted this bare
    would make the whole block fail to parse (``contract.parse_frontmatter``
    returns ``None``), not merely round-trip to a subtly wrong value.

    The parse-result assertions are checked *before* the emitted-line
    assertion below, on purpose: under the "emit bare regardless" mutation
    (tasks.md) the block genuinely fails to parse (a bare
    ``methodology: vendor: custom`` line is not valid YAML), so
    ``assert parsed is not None`` is what actually goes red first, matching
    the claim this docstring makes -- were the line check ordered first
    instead, *it* would red first (the fixture types differ) without ever
    exercising the parse failure this test means to pin.

    This fixture also contains a space, but does not by itself pin the space
    rule: the colon is what makes a bare emission unparseable, so a widened
    identifier pattern that still rejected colons (but accepted spaces) would
    stay green here. ``test_identifier_with_only_a_space_is_quoted`` below
    covers the space alone.
    """
    block = page.render_frontmatter(
        methodology="vendor: custom",
        methodology_source=None,
        constants_provenance=None,
        tau_fitness_days=None,
        tau_fatigue_days=None,
        k_fitness=None,
        k_fatigue=None,
        coverage_threshold=None,
        series_start=None,
        series_end=None,
        pages_read=0,
        pages_with_load=0,
        criterion_points=0,
    )
    parsed = contract.parse_frontmatter(block)
    assert parsed is not None
    assert parsed["methodology"] == "vendor: custom"
    assert 'methodology: "vendor: custom"\n' in block


def test_identifier_with_only_a_space_is_quoted() -> None:
    """A space alone (no colon, no other punctuation) must still trigger
    quoting: ``_IDENTIFIER_PATTERN`` (``[A-Za-z0-9_.-]+``) excludes the space
    character, so ``"vendor custom"`` cannot fullmatch it and falls to the
    quoted branch.

    Mutation: widen ``_IDENTIFIER_PATTERN`` to ``[A-Za-z0-9_. -]+`` (adding a
    space to the allowed character class) -- this fixture would then
    fullmatch and be emitted bare (``methodology: vendor custom\\n``,
    unquoted); this assertion reds while
    ``test_identifier_with_a_colon_is_quoted`` stays green, because a bare
    ``vendor custom`` still parses as valid YAML (no colon), so the colon
    fixture alone cannot catch this mutation.
    """
    block = page.render_frontmatter(
        methodology="vendor custom",
        methodology_source=None,
        constants_provenance=None,
        tau_fitness_days=None,
        tau_fatigue_days=None,
        k_fitness=None,
        k_fatigue=None,
        coverage_threshold=None,
        series_start=None,
        series_end=None,
        pages_read=0,
        pages_with_load=0,
        criterion_points=0,
    )
    assert 'methodology: "vendor custom"\n' in block
    parsed = contract.parse_frontmatter(block)
    assert parsed is not None
    assert parsed["methodology"] == "vendor custom"


def test_identifier_with_a_quote_is_quoted_and_escaped() -> None:
    block = page.render_frontmatter(
        methodology='need"escape',
        methodology_source=None,
        constants_provenance=None,
        tau_fitness_days=None,
        tau_fatigue_days=None,
        k_fitness=None,
        k_fatigue=None,
        coverage_threshold=None,
        series_start=None,
        series_end=None,
        pages_read=0,
        pages_with_load=0,
        criterion_points=0,
    )
    assert 'methodology: "need\\"escape"\n' in block
    parsed = contract.parse_frontmatter(block)
    assert parsed is not None
    assert parsed["methodology"] == 'need"escape'


def test_identifier_with_a_backslash_is_quoted_and_backslash_escaped() -> None:
    """A literal backslash in the identifier is quoted (it is not in
    ``_IDENTIFIER_PATTERN``) and must itself be escaped as ``\\\\`` -- doubled
    -- inside the quoted output, per design.md:1221's quoting rule
    (``"`` and ``\\`` escaped), not merely passed through unescaped.

    Mutation: remove the ``.replace("\\\\", "\\\\\\\\")`` call inside
    ``_format_identifier`` (~page.py:140), leaving only the ``"`` escape --
    this assertion reds because the emitted line carries a single, bare
    ``\\`` instead of a doubled ``\\\\``, and is the sole failure (the
    quote-escaping test above is unaffected, since its fixture has no
    backslash).
    """
    block = page.render_frontmatter(
        methodology="a\\b",
        methodology_source=None,
        constants_provenance=None,
        tau_fitness_days=None,
        tau_fatigue_days=None,
        k_fitness=None,
        k_fatigue=None,
        coverage_threshold=None,
        series_start=None,
        series_end=None,
        pages_read=0,
        pages_with_load=0,
        criterion_points=0,
    )
    assert 'methodology: "a\\\\b"\n' in block
    parsed = contract.parse_frontmatter(block)
    assert parsed is not None
    assert parsed["methodology"] == "a\\b"


def test_identifier_with_an_apostrophe_is_quoted_and_passed_through() -> None:
    """An apostrophe is not part of ``_IDENTIFIER_PATTERN`` (so the value
    falls to the quoted branch), and is not one of the two characters this
    module's quoting rule escapes (``\\`` and ``"``) -- it must appear in the
    quoted output verbatim, unescaped, and round-trip to the original string
    unchanged.

    Mutation A: append ``.replace("'", "\\\\'")`` inside ``_format_identifier``
    (~page.py:141) -- the apostrophe would then be rewritten as a bare
    backslash followed by an apostrophe, which is not a valid escape inside a
    double-quoted YAML string; ``contract.parse_frontmatter`` then fails to
    parse the whole block and returns ``None`` -- the silently-broken block a
    reader would only discover downstream, not a value that merely differs.
    This is the sole failure: no other fixture in this module contains an
    apostrophe, so no other test observes the mutation.
    """
    block = page.render_frontmatter(
        methodology="vendor's custom",
        methodology_source=None,
        constants_provenance=None,
        tau_fitness_days=None,
        tau_fatigue_days=None,
        k_fitness=None,
        k_fatigue=None,
        coverage_threshold=None,
        series_start=None,
        series_end=None,
        pages_read=0,
        pages_with_load=0,
        criterion_points=0,
    )
    assert 'methodology: "vendor\'s custom"\n' in block
    parsed = contract.parse_frontmatter(block)
    assert parsed is not None
    assert parsed["methodology"] == "vendor's custom"


def test_control_character_in_identifier_raises() -> None:
    """Mutation: delete the ``_reject_control_characters`` call inside
    ``_format_identifier`` -- this assertion reds because the call that used
    to raise instead falls through to the bare-token branch (a control
    character never matches ``_IDENTIFIER_PATTERN``, so it would actually
    fall to the quoted branch and embed the raw byte -- either way, no
    exception is raised and this ``pytest.raises`` block fails).
    """
    with pytest.raises(ValueError):
        page.render_frontmatter(
            methodology="bad\x01id",
            methodology_source=None,
            constants_provenance=None,
            tau_fitness_days=None,
            tau_fatigue_days=None,
            k_fitness=None,
            k_fatigue=None,
            coverage_threshold=None,
            series_start=None,
            series_end=None,
            pages_read=0,
            pages_with_load=0,
            criterion_points=0,
        )


def test_control_character_in_quoted_field_raises() -> None:
    """The same control-character guard applies to every plain (non-identifier)
    quoted field, not only the methodology identifier -- ``methodology_source``
    is routed through ``_quote`` rather than ``_format_identifier``.

    Mutation H: delete the ``_reject_control_characters`` call inside
    ``_quote`` (page.py's other call site) -- this ``pytest.raises`` block
    fails because ``str.replace`` on ``"x\\x01y"`` raises nothing and the
    control byte would instead be embedded, unrejected, in the block.
    """
    with pytest.raises(ValueError):
        page.render_frontmatter(
            methodology=None,
            methodology_source="x\x01y",
            constants_provenance=None,
            tau_fitness_days=None,
            tau_fatigue_days=None,
            k_fitness=None,
            k_fatigue=None,
            coverage_threshold=None,
            series_start=None,
            series_end=None,
            pages_read=0,
            pages_with_load=0,
            criterion_points=0,
        )


def test_newline_in_identifier_raises() -> None:
    with pytest.raises(ValueError):
        page.render_frontmatter(
            methodology="bad\nid",
            methodology_source=None,
            constants_provenance=None,
            tau_fitness_days=None,
            tau_fatigue_days=None,
            k_fitness=None,
            k_fatigue=None,
            coverage_threshold=None,
            series_start=None,
            series_end=None,
            pages_read=0,
            pages_with_load=0,
            criterion_points=0,
        )


def test_float_formatting_is_explicit_not_platform_repr() -> None:
    """Every number is formatted by an explicit rule (four decimal places)
    so no platform's default ``str``/``repr`` can leak in.

    Mutation: replace ``f"{value:.4f}"`` with ``str(value)`` in
    ``_format_float`` -- ``0.1 + 0.7`` would then round-trip through Python's
    shortest-repr float formatting instead of the fixed rule; this assertion
    pins the fixed-decimal *form* directly (a trailing, non-truncated
    ``0.8000``), which ``str(0.1 + 0.7)`` (``"0.7999999999999999"``) would
    not produce, so the mutation reds it.
    """
    block = page.render_frontmatter(
        methodology=None,
        methodology_source=None,
        constants_provenance=None,
        tau_fitness_days=0.1 + 0.7,
        tau_fatigue_days=None,
        k_fitness=None,
        k_fatigue=None,
        coverage_threshold=None,
        series_start=None,
        series_end=None,
        pages_read=0,
        pages_with_load=0,
        criterion_points=0,
    )
    assert "tau_fitness_days: 0.8000\n" in block


# ==============================================================================
# 4.3: body sections and goldens (Req 2.2, 2.5, 2.7, 2.11, 3.5, 3.7, 3.10,
# 5.4-5.10, 6.1-6.5)
# ==============================================================================
#
# The fixture archive below is built as real `PageRecord`/`SkippedPage`
# values and driven through the *actual* `history.series` and `history.model`
# functions (never hand-built `WeekRow`/`Coverage`/`CriterionPoints`
# instances), so every number the golden carries is traceable to the eight
# `PageRecord`s and one `SkippedPage` declared in `_FIXTURE_PAGES` /
# `_FIXTURE_SKIPPED` -- see `_build_kwargs`'s docstring for the arithmetic.

_THRESHOLD = 0.80  # SEED_CONSTANTS' own COVERAGE_THRESHOLD.value; tests are
# outside test_constant_guard.py's scan, so no exemption entry is needed here.

_GOLDEN_DIR = Path(__file__).parent / "golden"
_GOLDEN_MARKDOWN_PATH = _GOLDEN_DIR / "training_load_history.md"
_GOLDEN_SVG_PATH = _GOLDEN_DIR / "training_load_history_chart.svg"


def _record(
    path: str,
    day: date,
    *,
    load: float | None = None,
    methodology: str | None = None,
    effort: EffortTag | None = None,
    tag_problem: str | None = None,
) -> PageRecord:
    return PageRecord(
        path=path,
        day=day,
        load=load,
        methodology=methodology,
        effort=effort,
        tag_problem=tag_problem,
    )


_FIXTURE_PAGES: tuple[PageRecord, ...] = (
    # -- week 1 (2024-01-01..07, ISO (2024, 1)): a full week, not suppressed.
    _record(
        "workouts/2024-01-01.md",
        date(2024, 1, 1),
        load=10.0,
        methodology="banister_1991",
    ),
    _record(
        "workouts/2024-01-03.md",
        date(2024, 1, 3),
        load=12.0,
        methodology="banister_1991",
        effort=EffortTag(
            kind=EffortKind.RACE, distance_m=10000.0, time_s=2400.0, event="Winter 10K"
        ),
    ),  # the race WITH a result
    _record(
        "workouts/2024-01-05.md",
        date(2024, 1, 5),
        load=8.0,
        methodology="banister_1991",
        effort=EffortTag(
            kind=EffortKind.RACE, distance_m=5000.0, time_s=1500.0, event="Spring 5K"
        ),
    ),  # the SECOND race with a result (round-2 remediation item 1: distinct
    # date from the Winter 10K above, so `criterion.earliest`/`.latest` are
    # no longer tied -- Req 6.2). TEST stays unobserved throughout the
    # fixture, so "0 test" is still a real derivation, not a coincidence of
    # an empty archive.
    _record(
        "workouts/2024-01-07.md",
        date(2024, 1, 7),
        load=15.0,
        methodology="banister_1991",
    ),
    # -- week 2 (2024-01-08..14, ISO (2024, 2)): the rest week -- zero
    # *included* pages, so every day is genuine rest (design.md's "day
    # classification" flow: no documents that day -> pages = 0, complete).
    # The one page dated inside this week records another methodology and
    # is EXCLUDED, never entering the included daily series at all.
    _record(
        "workouts/2024-01-10.md",
        date(2024, 1, 10),
        load=5.0,
        methodology="trimp_legacy",
    ),
    # -- a SECOND excluded-methodology page, dated in 2023 -- a calendar
    # year that otherwise holds no page at all (round-2 remediation item 6):
    # `coverage_report` must still emit a `"2023"` row for it, with
    # `pages == 0` (nothing *included* falls in 2023) but `pages_excluded`
    # carrying this one page, so the empty-period coverage rule (Req 3.6,
    # `pages == 0` -> fraction 1.0 -> "100.0%") is exercised on a row that
    # is not also the archive-wide `"all"` row.
    _record(
        "workouts/2023-12-20.md",
        date(2023, 12, 20),
        load=4.0,
        methodology="trimp_legacy",
    ),
    # -- week 3 (2024-01-15.., ISO (2024, 3)): the suppressed week. The
    # series' own span ends at the last *contributing* page (2024-01-17,
    # the malformed-tag page below), so only 2024-01-15..17 (3 days) of
    # this ISO week actually fall inside `series.days` -- a partial week.
    _record("workouts/2024-01-15.md", date(2024, 1, 15)),  # unknown load
    _record(
        "workouts/2024-01-16.md",
        date(2024, 1, 16),
        effort=EffortTag(
            kind=EffortKind.RACE, distance_m=5000.0, time_s=None, event="Local 5K"
        ),
    ),  # the race with NO result -- unknown load too
    _record(
        "workouts/2024-01-17.md",
        date(2024, 1, 17),
        load=6.0,
        methodology="banister_1991",
        tag_problem="effort_time_s must be a positive number, got 'DNF'",
    ),  # the malformed tag -- Req 3.9: its load still counts
)

_FIXTURE_SKIPPED: tuple[SkippedPage, ...] = (
    SkippedPage(
        path="workouts/mystery-date.md", reason="document date could not be read"
    ),
)


@dataclass(frozen=True)
class _FixtureResult:
    series: DailySeries
    model: ModelSeries
    weeks: tuple[WeekRow, ...]
    coverage: tuple[Coverage, ...]
    criterion: CriterionPoints
    markers: tuple[tuple[int, PageRecord], ...]
    choice: MethodologyChoice
    constants: ModelConstants
    threshold: float
    skipped: tuple[SkippedPage, ...]
    pages_read: int


def _build_kwargs() -> _FixtureResult:
    """Drive `_FIXTURE_PAGES` through the real `series`/`model` pipeline and
    return `page.render_history`'s own keyword arguments.

    The arithmetic every golden number traces to (round-2 remediation:
    `_FIXTURE_PAGES` now carries 9 pages -- the original 8 plus one more
    `"trimp_legacy"` page dated 2023-12-20, item 6 -- and 2024-01-05 now
    carries a second race tag with a result, item 1):

    - `select_methodology` resolves to `"banister_1991"` (configured):
      5 pages record it, 2 record no methodology at all (2024-01-15,
      2024-01-16 -- no load), and 2 (2024-01-10 and 2023-12-20) record
      `"trimp_legacy"` -- one excluded methodology, count 2.
    - `partition_pages` includes every page except the two `trimp_legacy`
      ones: 7 included (`pages_read` -- together with the 2 excluded pages
      -- is 9; the 1 `SkippedPage` is a separate, unattributable count,
      Req 3.10).
    - The included pages' dates span 2024-01-01 (first) to 2024-01-17
      (last *contributing* -- the last page recording a load under the
      chosen methodology), 17 calendar days. The excluded 2023-12-20 page
      never enters the included daily series, so the span is unaffected --
      it only adds a `"2023"` row to the coverage statement (below).
    - Week (2024, 1) (2024-01-01..07, 7 days): 4 pages, all 4 record a
      load -- coverage 4/4 = 100%, not suppressed. 2024-01-05 additionally
      carries a race tag with a result (`time_s=1500.0`), which does not
      change its `load` (still 8.0) or the week's coverage.
    - Week (2024, 2) (2024-01-08..14, 7 days): 0 included pages at all --
      coverage 0/0 defined as 1.0 (Req 3.6), not suppressed. The rest
      week.
    - Week (2024, 3) (2024-01-15..17 only, 3 in-span days -- a partial
      week): 3 pages, only 1 (2024-01-17, the malformed-tag page) records
      a load -- coverage 1/3 ~= 33.3% < 80% -- suppressed.
    - `coverage_report`'s per-year rows: `"2023"` gets `pages=0`,
      `pages_with_load=0` (nothing *included* falls in 2023 -- only the
      excluded page does), `pages_excluded=(("trimp_legacy", 1),)`,
      fraction 1.0 (Req 3.6's empty-period rule) -- 100.0%. `"2024"` gets
      `pages=7`, `pages_with_load=5`, `pages_excluded=(("trimp_legacy",
      1),)` (only the one 2024-dated excluded page). `"all"` aggregates
      both years' excluded pages: `pages_excluded=(("trimp_legacy", 2),)`.
    - `criterion_points` walks the FULL 9-page scan (tasks.md's
      Implementation Notes for 3.5/4.3, not just the included partition):
      2024-01-03 (race, time_s=2400.0) and 2024-01-05 (race,
      time_s=1500.0) both count -- 2 criterion points, kind RACE, TEST
      unobserved (0, derived by the page); earliest 2024-01-03, latest
      2024-01-05 -- two distinct dates (round-2 item 1: the two counted
      points are no longer tied). 2024-01-16 (race, no time_s) is excluded
      as "no official time" (count 1); 2024-01-17's malformed tag is
      excluded individually (count 1) -- 2 tagged pages excluded from the
      count of 2.
    - Three race markers, in day order: 2024-01-03 (day index 2 -- 2024-01-01
      is index 0) with a result, 2024-01-05 (day index 4) with a result, and
      2024-01-16 (day index 15) with none.
    """
    choice = select_methodology(
        _FIXTURE_PAGES, requested=None, configured="banister_1991"
    )
    assert isinstance(choice, MethodologyChoice), (
        "fixture archive must resolve a methodology cleanly, not a "
        f"MethodologyProblem: {choice!r}"
    )
    included, excluded = partition_pages(_FIXTURE_PAGES, choice)
    series = build_daily_series(included)
    assert series is not None, "fixture archive must record at least one load"
    model = history_model.run_model(
        [day.recorded_load for day in series.days], SEED_CONSTANTS
    )
    suppressed = suppressed_weeks(series, _THRESHOLD)
    weeks = week_rows(series, model, suppressed)
    coverage = coverage_report(series, excluded, choice, len(_FIXTURE_SKIPPED))
    criterion = criterion_points(_FIXTURE_PAGES)
    markers = tuple(
        ((record.day - series.start).days, record)
        for record in included
        if record.effort is not None and record.effort.kind is EffortKind.RACE
    )
    return _FixtureResult(
        series=series,
        model=model,
        weeks=weeks,
        coverage=coverage,
        criterion=criterion,
        markers=markers,
        choice=choice,
        constants=SEED_CONSTANTS,
        threshold=_THRESHOLD,
        skipped=_FIXTURE_SKIPPED,
        pages_read=len(included) + len(excluded),
    )


def _render() -> page.RenderedHistory:
    kwargs = _build_kwargs()
    return page.render_history(
        series=kwargs.series,
        model=kwargs.model,
        weeks=kwargs.weeks,
        coverage=kwargs.coverage,
        criterion=kwargs.criterion,
        markers=kwargs.markers,
        choice=kwargs.choice,
        constants=SEED_CONSTANTS,
        threshold=kwargs.threshold,
        skipped=kwargs.skipped,
        pages_read=kwargs.pages_read,
    )


# --- fixture arithmetic sanity (independent of render_history's own output) -


def test_fixture_methodology_and_partition() -> None:
    kwargs = _build_kwargs()
    choice = kwargs.choice
    assert choice.methodology == "banister_1991"
    assert choice.source == "configured"
    assert choice.excluded == (("trimp_legacy", 2),)


def test_fixture_span_and_week_coverage() -> None:
    kwargs = _build_kwargs()
    series = kwargs.series
    assert series.start == date(2024, 1, 1)
    assert series.end == date(2024, 1, 17)
    weeks = kwargs.weeks
    assert [w.suppressed for w in weeks] == [False, False, True]
    assert weeks[1].pages == 0 and weeks[1].pages_with_load == 0
    assert weeks[2].pages == 3 and weeks[2].pages_with_load == 1


def test_fixture_criterion_points() -> None:
    criterion = _build_kwargs().criterion
    assert criterion.count == 2
    assert dict(criterion.by_kind) == {EffortKind.RACE: 2}
    assert EffortKind.TEST not in dict(criterion.by_kind)
    assert sum(n for _, n in criterion.excluded) + len(criterion.malformed) == 2
    # Req 6.2 -- earliest and latest are no longer tied (round-2 item 1):
    # two distinct counted dates, not one date repeated.
    assert criterion.earliest == date(2024, 1, 3)
    assert criterion.latest == date(2024, 1, 5)
    assert criterion.earliest != criterion.latest


def test_coverage_report_has_a_2023_row_with_full_coverage_from_zero_pages() -> None:
    """Req 3.6: a calendar year with zero *included* pages (only an
    excluded one falls in it) is still reported, with its coverage defined
    as complete (fraction 1.0) rather than as zero -- nothing is missing
    from a period that holds no page at all.

    Mutation N7 (review round 2, item 6): replace `_render_coverage_section`'s
    `row.fraction` with `row.pages_with_load / row.pages` -- for this row
    (`pages == 0`) that raises `ZeroDivisionError`, which propagates out of
    `_render()` and fails the last assertion below (and every other test in
    this module that calls `_render()`, since the section is built before
    the ones after it in the fixed section order -- a fixture-arithmetic
    check on `Coverage` alone, without calling `_render()`, would not
    reach `page.py`'s rendering code at all and would stay green under this
    mutation, so the rendered-text assertion is the one that actually pins
    it).
    """
    coverage = _build_kwargs().coverage
    labels = [row.label for row in coverage]
    assert "2023" in labels
    row_2023 = next(row for row in coverage if row.label == "2023")
    assert row_2023.pages == 0
    assert row_2023.pages_with_load == 0
    assert row_2023.fraction == 1.0
    assert row_2023.pages_excluded == (("trimp_legacy", 1),)
    markdown = _render().markdown
    assert "- 2023: 0 pages, 0 recording a load (100.0%)" in markdown


def test_all_coverage_row_differs_from_the_first_row() -> None:
    """Reachability check for N12b below: the fixture must actually produce
    a first row that differs from the `"all"` row, or a mutation reading
    the wrong one would go unnoticed by coincidence.
    """
    coverage = _build_kwargs().coverage
    assert coverage[0].label != "all"
    all_row = next(row for row in coverage if row.label == "all")
    assert all_row.pages_with_load != coverage[0].pages_with_load


def test_frontmatter_pages_with_load_reads_the_all_row_not_the_first_row() -> None:
    """Mutation N12b (review round 2, item 6): replace `render_history`'s
    `next(row for row in coverage if row.label == "all")` with
    `next(iter(coverage))` -- with the 2023 row now first, the frontmatter's
    `pages_with_load` would read `0` (the 2023 row's own value) instead of
    the archive-wide `5`.
    """
    kwargs = _build_kwargs()
    all_row = next(row for row in kwargs.coverage if row.label == "all")
    parsed = contract.parse_frontmatter(_render().markdown)
    assert parsed is not None
    assert parsed["pages_with_load"] == all_row.pages_with_load
    assert parsed["pages_with_load"] != kwargs.coverage[0].pages_with_load


def test_contiguous_bands_groups_runs_and_isolates_gaps() -> None:
    """`_contiguous_bands` groups a set of day indices into contiguous
    inclusive `CalendarBand` ranges, sorted ascending -- pinned directly
    (independent of the suppressed-week wiring above it) against a fixture
    with two separate multi-index runs (0-2, 5-6) and one isolated
    single-index run (9), so a mutation that merges everything into one
    band from the min to the max is distinguishable from correct grouping.

    Mutation M6 (review round 3, item 2): replace `_contiguous_bands`'s
    body with `(CalendarBand(min(indices), max(indices)),)` if `indices`
    else `()` -- the three-band assertion below reds, since the mutated
    version returns a single `CalendarBand(0, 9)` instead.
    """
    bands = page._contiguous_bands({0, 1, 2, 5, 6, 9})
    assert bands == (
        page.CalendarBand(start_index=0, end_index=2),
        page.CalendarBand(start_index=5, end_index=6),
        page.CalendarBand(start_index=9, end_index=9),
    )
    assert page._contiguous_bands(set()) == ()


def test_suppressed_day_indices_handles_a_partial_first_week() -> None:
    """`_suppressed_day_indices` matches suppression by each day's own ISO
    `(year, week)` against the suppressed `WeekRow`s (Req 3.8) -- never by
    walking a fixed 7-day offset from a week's `monday`, which would
    mishandle a *partial* first (or last) week whose in-span day count is
    shorter than 7.

    The fixture archive here has its first ISO week (2024, 1) -- Jan 1-7,
    2024 -- suppressed, and the series itself starts mid-week, at 2024-01-03
    (a Wednesday), so only 5 of that week's 7 calendar days
    (01-03..01-07) actually fall inside `series.days`. A Monday-anchored
    offset walk (`offset = (week.monday - series.start).days` -- here
    negative, since `monday` 2024-01-01 precedes `series.start` 2024-01-03
    -- then `range(offset, offset + week.days_in_span)`) computes a
    *negative* starting index (`-2`) instead of `0`, so the suppressed band
    it would produce is `CalendarBand(start_index=-2, end_index=2)`, not
    `CalendarBand(start_index=0, end_index=4)`. Under that mutation the
    `0 <= start_index` bound reds first (this test is the sole failing
    test), and the exact-band assertion and the `values[:5] == (None,) * 5`
    assertion red as well; `spec.days == 6`, `values[5] is not None` and
    the two preconditions stay green, because a shifted band still leaves
    day 5 unsuppressed.

    Mutation: replace `_suppressed_day_indices`'s ISO-key matching loop
    with the Monday-anchored offset walk described above.
    """
    pages = (
        _record(
            "workouts/2024-01-03.md",
            date(2024, 1, 3),
            load=10.0,
            methodology="banister_1991",
        ),
        _record("workouts/2024-01-04.md", date(2024, 1, 4)),  # no load
        _record("workouts/2024-01-05.md", date(2024, 1, 5)),  # no load
        _record("workouts/2024-01-06.md", date(2024, 1, 6)),  # no load
        _record(
            "workouts/2024-01-08.md",
            date(2024, 1, 8),
            load=5.0,
            methodology="banister_1991",
        ),
    )
    choice = select_methodology(pages, requested=None, configured="banister_1991")
    assert isinstance(choice, MethodologyChoice)
    included, _excluded = partition_pages(pages, choice)
    series = build_daily_series(included)
    assert series is not None
    model = history_model.run_model(
        [day.recorded_load for day in series.days], SEED_CONSTANTS
    )
    suppressed = suppressed_weeks(series, _THRESHOLD)
    weeks = week_rows(series, model, suppressed)

    # Precondition: the fixture actually reaches the scenario this test
    # names -- week 1 is suppressed, and it is a partial (5-day) week.
    week_one = next(w for w in weeks if (w.iso_year, w.iso_week) == (2024, 1))
    assert week_one.suppressed is True
    assert week_one.days_in_span == 5

    spec = page._build_chart(series, model, weeks, ())
    assert spec.days == 6
    assert all(0 <= b.start_index <= b.end_index < spec.days for b in spec.suppressed)
    assert spec.suppressed == (page.CalendarBand(start_index=0, end_index=4),)
    assert spec.series[0].values[:5] == (None,) * 5
    assert spec.series[0].values[5] is not None


def test_plural_singular_branch() -> None:
    """`_plural` returns the bare singular noun when `count == 1`, never
    the pluralised form. The golden's six `_plural` counts (0, 7, 7 in the
    coverage rows, 2 criterion points, 2 tagged pages, 2 excluded pages)
    exercise only the plural branch; the singular branch is observed here directly and
    through the coverage section in
    `test_coverage_section_pluralises_a_single_page_count`.

    Mutation M5 (review round 3, item 4): delete the `if count == 1:
    return singular` branch from `_plural` so it always returns the
    plural -- the two `count == 1` assertions below (`_plural(1, "page")` and
    `_plural(1, "criterion point", "criterion points")`) red, and so does
    `test_coverage_section_pluralises_a_single_page_count` (two
    `test_page.py` failures, plus the constant guard's exemption failures
    for the deleted `== 1` literal); the `count == 2` assertions are
    unaffected.
    """
    assert page._plural(1, "page") == "page"
    assert page._plural(2, "page") == "pages"
    assert page._plural(1, "criterion point", "criterion points") == "criterion point"
    assert page._plural(2, "criterion point", "criterion points") == "criterion points"


def test_coverage_section_pluralises_a_single_page_count() -> None:
    """`_render_coverage_section` routes its `row.pages` count through
    `_plural` (round-4 remediation item 2) rather than hard-coding the
    literal ``"pages"`` noun -- so a row whose `pages` count is 1 reads
    "1 page", never the grammatically-wrong "1 pages" every other fixture
    row in this module's golden (0, 7, 7) fails to exercise.

    The fixture's two counts differ (`pages=1`, `pages_with_load=0`) so the
    test can tell WHICH count is routed through `_plural`.

    Mutations: revert `_render_coverage_section` to
    `f"- {row.label}: {row.pages} pages, ..."` -- this assertion reds,
    since the rendered line would then read "1 pages" instead of "1 page";
    route the wrong count, `_plural(row.pages_with_load, "page")` -- reds
    too, since 0 pluralises to "1 pages".
    """
    coverage = (
        Coverage(
            label="2025",
            pages=1,
            pages_with_load=0,
            pages_excluded=(),
            pages_skipped=None,
        ),
    )
    rendered = page._render_coverage_section(coverage)
    assert "- 2025: 1 page, 0 recording a load (0.0%); excluded: none" in rendered
    assert "1 pages" not in rendered


# --- goldens ------------------------------------------------------------


def test_markdown_matches_committed_golden() -> None:
    assert _GOLDEN_MARKDOWN_PATH.exists(), f"missing golden: {_GOLDEN_MARKDOWN_PATH}"
    rendered = _render()
    assert rendered.markdown == _GOLDEN_MARKDOWN_PATH.read_text(encoding="utf-8")


def test_svg_matches_committed_golden() -> None:
    assert _GOLDEN_SVG_PATH.exists(), f"missing golden: {_GOLDEN_SVG_PATH}"
    rendered = _render()
    assert rendered.chart_svg == _GOLDEN_SVG_PATH.read_text(encoding="utf-8")


def test_render_is_byte_identical_across_calls() -> None:
    first = _render()
    second = _render()
    assert first.markdown == second.markdown
    assert first.chart_svg == second.chart_svg


# --- section order, presence and content -----------------------------------


def test_section_order_is_fixed() -> None:
    """Req 5.8/5.9's "sections, in order" (design.md:1229-1232): the
    generated banner, the title, the chart section, the constants section,
    the coverage section, the criterion section, the weekly table, and the
    skipped-and-excluded list.

    Mutation: swap `_render_coverage_section` and `_render_criterion_section`
    in `page.render_history`'s body list -- this assertion reds because the
    coverage heading would then appear after the criterion heading.
    """
    markdown = _render().markdown
    headings = [
        contract.DOC_BANNER,
        f"# {page.HISTORY_TITLE}",
        "## Training Load Chart",
        "## Model Constants",
        "## Coverage",
        "## Criterion-Performance Report",
        "## Weekly Table",
        "## Skipped and Excluded",
    ]
    positions = [markdown.index(h) for h in headings]
    assert positions == sorted(positions), positions


def test_chart_link_is_relative_and_uses_forward_slashes() -> None:
    rendered = _render()
    assert rendered.chart_rel_path == "assets/training-load-history-fitness.svg"
    assert f"]({rendered.chart_rel_path})" in rendered.markdown
    assert "\\" not in rendered.chart_rel_path


def test_race_list_shows_result_and_no_fabricated_result() -> None:
    """Req 5.4, 5.5: a race with a result shows it; a race with none is
    still marked (dated) but shows no fabricated result.

    Results are rendered through the shared `fitdocs.render.format`
    functions (`fmt_duration`, `fmt_distance_km`; round-2 remediation item
    7), not a raw-seconds `_fmt1(tag.time_s)`.

    Mutation: change `_marker_result_text` to return
    `"no result recorded — finished in 0:00"` (appending a fabricated
    duration rather than replacing the sentence) when `tag.time_s is None`
    -- the negative assertion below reds, because the literal substring
    `"finished in 0:00"` now appears in the markdown, while the positive
    `"2024-01-16 — no result recorded"` assertion above it stays green
    (that substring is still present, as a prefix of the longer, now
    fabricated, text). Either full replacement (`"finished in 0:00"` or a
    bare `"0:00"`) instead reds the positive assertion first, since the
    marker line would then read `"2024-01-16 — finished in 0:00"` and no
    longer contain `"no result recorded"` at all -- the negative assertion
    is the one this docstring pins because it is the only mutation of the
    two that the positive assertion alone would not already catch.
    """
    markdown = _render().markdown
    assert "2024-01-03 — Winter 10K — finished in 40:00 (10.00 km)" in markdown
    assert "2024-01-05 — Spring 5K — finished in 25:00 (5.00 km)" in markdown
    assert "2024-01-16 — no result recorded" in markdown
    assert "finished in 0:00" not in markdown


def test_criterion_section_earliest_and_latest_are_distinct_dates() -> None:
    """Req 6.2: with two counted criterion points on different dates, the
    earliest and latest dates the page states must be the two distinct
    dates, not one date reported for both.

    Mutation N1 (review round 2, item 1): swap `criterion.earliest` and
    `criterion.latest` in `_render_criterion_section`'s f-string -- with
    the two dates now distinct, this reds because the sentence would read
    "Earliest 2024-01-05, latest 2024-01-03" instead.
    Mutation N1b: print `criterion.latest` for both positions -- reds
    because the earliest date (2024-01-03) would no longer appear at all.
    """
    markdown = _render().markdown
    assert "Earliest 2024-01-03, latest 2024-01-05." in markdown


def test_never_fitted_sentence_is_present_verbatim() -> None:
    """Copy assertion for the never-fitted sentence (Req 2.5, 2.10).

    Mutation: delete the `_NEVER_FITTED_SENTENCE` line from
    `_render_constants_section` -- this assertion reds directly.
    """
    assert page._NEVER_FITTED_SENTENCE in _render().markdown


def test_caveat_sentences_are_present_verbatim() -> None:
    """Copy assertion for both caveat sentences (Req 3.7), printed every
    time regardless of whether a suppression is present in this run.

    Mutation: delete either sentence from `_render_constants_section` --
    the corresponding half of this assertion reds.
    """
    markdown = _render().markdown
    assert page._CAVEAT_ZERO_START_SENTENCE in markdown
    assert page._CAVEAT_SUPPRESSED_GAP_SENTENCE in markdown


def test_constants_origin_line_is_printed_verbatim() -> None:
    """The origin line carries a lead-in (round-2 item 2), but the origin
    text itself, following it, is verbatim and unaltered.

    Mutation: truncate `constants.origin` before interpolating it in
    `_render_constants_section` (e.g. `constants.origin[:20]`) -- this
    assertion reds because the full string no longer appears as a
    contiguous substring.
    """
    markdown = _render().markdown
    assert SEED_CONSTANTS.origin in markdown
    assert f"Origin: {SEED_CONSTANTS.origin}" in markdown


def test_constants_paragraph_configured_and_fitted_wording() -> None:
    """Req 2.7: where the athlete configures different constants, the page
    states plainly that they are the athlete's own, not the shipped seeds
    -- for both the `CONFIGURED` and `FITTED` provenances, each rendered
    from a `dataclasses.replace(SEED_CONSTANTS, ...)` instance so the test
    exercises `render_history`'s actual provenance branch rather than a
    hand-built `ModelConstants`.

    Mutation N2 (review round 2, item 2): replace
    `_PROVENANCE_WORDING[ConstantProvenance.CONFIGURED]` with the `SEEDS`
    entry's own text -- the "seeds wording absent" half of the configured
    assertion below reds, because `"fitdocs' shipped seed values"` would
    then appear in a configured-provenance render.
    Mutation N3: the same substitution for `FITTED` -- the fitted
    assertion's "seeds wording absent" half reds identically, and is the
    sole failure (the configured fixture is unaffected by an edit to the
    `FITTED` entry, and vice versa).
    """
    kwargs = _build_kwargs()

    def _render_with(constants: ModelConstants) -> str:
        return page.render_history(
            series=kwargs.series,
            model=kwargs.model,
            weeks=kwargs.weeks,
            coverage=kwargs.coverage,
            criterion=kwargs.criterion,
            markers=kwargs.markers,
            choice=kwargs.choice,
            constants=constants,
            threshold=kwargs.threshold,
            skipped=kwargs.skipped,
            pages_read=kwargs.pages_read,
        ).markdown

    seeds_wording = page._PROVENANCE_WORDING[ConstantProvenance.SEEDS]

    configured = dataclasses.replace(
        SEED_CONSTANTS,
        provenance=ConstantProvenance.CONFIGURED,
        origin="the athlete's own [history] settings table.",
    )
    configured_markdown = _render_with(configured)
    assert (
        page._PROVENANCE_WORDING[ConstantProvenance.CONFIGURED] in configured_markdown
    )
    assert seeds_wording not in configured_markdown
    assert f"Origin: {configured.origin}" in configured_markdown

    fitted = dataclasses.replace(
        SEED_CONSTANTS,
        provenance=ConstantProvenance.FITTED,
        origin="fitted by performance-model-fit to the athlete's own archive.",
    )
    fitted_markdown = _render_with(fitted)
    assert page._PROVENANCE_WORDING[ConstantProvenance.FITTED] in fitted_markdown
    assert seeds_wording not in fitted_markdown
    assert f"Origin: {fitted.origin}" in fitted_markdown


def test_no_spec_citations_leak_into_the_rendered_page() -> None:
    """The rendered page is what an athlete reads, not this spec's own
    internal cross-reference vocabulary -- no `"Req N"` citation of any
    kind should appear anywhere in the markdown body (round-2 item 3).

    Mutation: reinstate the `" (Req 2.2)"` suffix on
    `_DAILY_AVERAGE_SCALE_SENTENCE`, or the `" (Req 3.3, 3.4)"` suffix on
    the coverage-threshold sentence in `_render_constants_section` -- this
    assertion reds directly.
    """
    markdown = _render().markdown
    assert re.search(r"Req [0-9]", markdown) is None


def test_no_conclusion_sentence_is_present() -> None:
    assert page._NO_CONCLUSION_SENTENCE in _render().markdown


def test_criterion_section_states_the_exclusion_list() -> None:
    """Req 6.3: the criterion section names every excluded group with its
    reason, and every malformed tag individually with its path and
    description.

    Mutation: in `_render_criterion_section`, delete the two `for` loops
    appending `criterion.excluded`/`criterion.malformed` rows -- the golden
    test reds (the exclusion lines vanish) and this direct assertion reds
    too, more narrowly.
    """
    markdown = _render().markdown
    assert "race or test tag recorded with no official time" in markdown
    assert "workouts/2024-01-17.md" in markdown
    assert "effort_time_s must be a positive number, got 'DNF'" in markdown


def test_criterion_section_derives_zero_for_an_unobserved_kind() -> None:
    """tasks.md's Implementation Notes for 4.3: `CriterionPoints.by_kind`
    omits a kind with zero observations entirely; the page derives 0 for it
    when printing "a race, b test" rather than omitting the "test" clause.

    Mutation: change `_render_criterion_section` to print only
    `race_count` (dropping the `test_count` term from the f-string) --
    this assertion reds because "0 test" no longer appears.
    """
    assert "2 race, 0 test" in _render().markdown


def test_malformed_group_states_its_own_count() -> None:
    """Req 6.3; design.md ~1240-1252: the malformed-tag group is itself one
    of the exclusion groups and must carry a count line the way the `hard`
    and `no official time` groups do, not just the bare per-path bullets.

    Mutation (review round 2, item 4): drop the
    `lines.append(f"- {malformed_count} with a malformed tag:")` call from
    `_render_criterion_section`, keeping only the per-path loop -- this
    assertion reds because the count line disappears while the per-path
    line (pinned by `test_criterion_section_states_the_exclusion_list`
    above) still renders, proving the two assertions pin independent
    claims.
    """
    markdown = _render().markdown
    assert "- 1 with a malformed tag:" in markdown


def test_suppressed_week_shows_a_dash_never_a_zero() -> None:
    """Req 3.7: a suppressed week's fitness/fatigue/form are shown as a
    dash and the suppression is named, never as `0.0`.

    Mutation: in `page._fmt1_or_dash`, replace `_DASH if value is None else
    _fmt1(value)` with `_fmt1(value or 0.0)` -- the suppressed week's row
    would then read `0.0 | 0.0 | 0.0` instead of `— | — | —`, and this
    assertion reds.
    """
    markdown = _render().markdown
    assert "| — | — | — | suppressed" in markdown
    # The suppressed week's own row never carries a bare 0.0 in place of
    # a dash for its three model columns.
    assert "| 0.0 | 0.0 | 0.0 |" not in markdown


def test_period_row_prints_no_skipped_count_only_the_archive_row_does() -> None:
    """Req 3.10: a skipped document is unattributable to any period, so a
    period row prints nothing where the skipped count would go; only the
    archive-wide ("all") row states it.

    Mutation: in `_render_coverage_section`, change
    `if row.pages_skipped is not None` to `if True` (always append the
    `"; skipped: ..."` clause, defaulting to 0 for `None` via `row.pages_skipped
    or 0`) -- a period row would then read "skipped: 0", and this assertion
    reds because that substring would appear.
    """
    markdown = _render().markdown
    assert "; skipped: 1" in markdown  # the archive-wide row
    assert "2024: " in markdown
    year_line = next(
        line for line in markdown.splitlines() if line.startswith("- 2024:")
    )
    assert "skipped" not in year_line


def test_float_formatting_uses_the_explicit_rule_not_platform_repr() -> None:
    """The body's number-formatting rule (loads/model values to one
    decimal, coverage as a percentage to one decimal) must be an explicit
    format spec, never the language's default `str()`/`repr()`.

    Mutation: replace `f"{value:.1f}"` with `str(value)` in `page._fmt1` --
    `0.1 + 0.7` would then render as `0.7999999999999999` instead of the
    fixed-decimal `0.8`, and this assertion (which pins the fixed form
    directly) reds.
    """
    assert page._fmt1(0.1 + 0.7) == "0.8"
    assert page._fmt1(0.1 + 0.7) != str(0.1 + 0.7)
    assert page._fmt_pct(1 / 3) == "33.3%"
    assert page._fmt_pct(1 / 3) != str(1 / 3)


def test_forbidden_phrases_never_appear() -> None:
    """Req 2.11, 5.10: no forecast, zone, readiness verdict, recommendation,
    plan, cycle or block content anywhere on the page.

    Mutation: add the sentence "Recommended next block: an easy week." to
    `_render_constants_section`'s returned lines -- this assertion reds
    (matches `recommend\\w*` and the standalone word `block`).
    """
    markdown = _render().markdown
    match = page._FORBIDDEN_PHRASE_PATTERN.search(markdown)
    assert match is None, f"forbidden phrase found: {match.group(0)!r}"


def test_forbidden_phrase_pattern_actually_matches_forbidden_text() -> None:
    """Reachability check for the assertion above: the pattern is not
    vacuously unmatchable -- including the plural forms and the two named
    phrases the round-2 remediation adds (item 5: "training zones",
    "training blocks", "overload warning", "the coach's verdict"), plus
    round-3 positive controls for the `forecast|plan|cycle` alternatives
    and negative controls for the trailing `\\b`.

    Mutation: drop the `s?` from `(?:zone|plan|cycle|block)s?` in
    `_FORBIDDEN_PHRASE_PATTERN` -- the plural assertions below (`"training
    zones"`, `"training blocks"`) red because the pattern no longer matches
    a trailing `s`.
    Mutation: drop `overload` from the alternation -- the "overload warning"
    assertion below reds, as the sole failure (no other fixture here
    contains the word "overload").
    Mutation: drop `verdict` from the alternation -- the "coach verdict"
    assertion below reds, as the sole failure. (A "readiness verdict"
    fixture would NOT isolate this: "readiness" alone already matches the
    pattern's own `readiness` alternative, so a verdict-only fixture is
    required to pin `verdict` independently of `readiness`.)
    Mutation F5: drop `forecast\\w*` from the alternation -- the "a forecast
    of next month" assertion below reds, as the sole failure.
    Mutation F7: drop `plan` from the `(?:zone|plan|cycle|block)` group --
    the "the training plan" assertion below reds, as the sole failure.
    Mutation F8: drop `cycle` from the `(?:zone|plan|cycle|block)` group --
    the "the next cycle" assertion below reds, as the sole failure (the
    separate "a cycling workout" fixture below does not contain the
    literal substring "cycle", so it cannot substitute for this one).
    Mutation F9: drop the trailing `\\b` from `_FORBIDDEN_PHRASE_PATTERN` --
    "planned" and "blocked" start matching (the bare `plan`/`block`
    literal is now free to sit inside a longer word), so both negative
    controls below red; the positive-match assertions above stay green,
    so this mutation is not visible without the negative controls.
    """
    assert page._FORBIDDEN_PHRASE_PATTERN.search("a readiness score") is not None
    assert page._FORBIDDEN_PHRASE_PATTERN.search("we recommend resting") is not None
    assert page._FORBIDDEN_PHRASE_PATTERN.search("next training block") is not None
    assert page._FORBIDDEN_PHRASE_PATTERN.search("training zones") is not None
    assert page._FORBIDDEN_PHRASE_PATTERN.search("training blocks") is not None
    assert page._FORBIDDEN_PHRASE_PATTERN.search("overload warning") is not None
    assert page._FORBIDDEN_PHRASE_PATTERN.search("the coach's verdict") is not None
    assert page._FORBIDDEN_PHRASE_PATTERN.search("a forecast of next month") is not None
    assert page._FORBIDDEN_PHRASE_PATTERN.search("the training plan") is not None
    assert page._FORBIDDEN_PHRASE_PATTERN.search("the next cycle") is not None
    assert page._FORBIDDEN_PHRASE_PATTERN.search("nothing forbidden here") is None
    # "cycling" is a legitimate word a training document may use, and is
    # not a match: "cycle" is not a substring of "cycling" ("cycl-e" vs
    # "cycl-ing" diverge at the fifth letter), so neither the bare word nor
    # the `s?`-pluralised form the round-2 pattern adds accidentally
    # widens to catch it.
    assert page._FORBIDDEN_PHRASE_PATTERN.search("a cycling workout") is None
    # "planned" and "blocked" carry the literal substrings "plan"/"block"
    # but not as a whole word -- the trailing `\b` must reject them.
    assert page._FORBIDDEN_PHRASE_PATTERN.search("the trip was planned") is None
    assert page._FORBIDDEN_PHRASE_PATTERN.search("the door was blocked") is None


# --- regeneration writer (developer utility; pytest does not run this) ------
def main() -> None:
    _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    rendered = _render()
    _GOLDEN_MARKDOWN_PATH.write_text(rendered.markdown, encoding="utf-8")
    _GOLDEN_SVG_PATH.write_text(rendered.chart_svg, encoding="utf-8")
    print(f"wrote {_GOLDEN_MARKDOWN_PATH}")
    print(f"wrote {_GOLDEN_SVG_PATH}")


if __name__ == "__main__":
    main()
