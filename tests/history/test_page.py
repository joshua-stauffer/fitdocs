"""Tests for the training-history document (load-history spec).

One headed section per task (tasks.md, Test File Ownership): the document
vocabulary and the frontmatter emitter -> task 4.2 (this section). Task 4.3
adds the body sections and the two goldens beneath ``tests/history/golden/``
in its own section below; neither task edits the other's.
"""

from __future__ import annotations

import ast
import inspect
from datetime import date

import pytest

from fitdocs import contract
from fitdocs.history import page

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
