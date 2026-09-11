"""Tests for `fitdocs.performance.sources` (design: PerformanceSources; task
1.2; Req 2.9, 3.7, 4.8, 8.1, 8.2, 8.4, 8.5, 8.6, 8.8, 9.8).

Covers: no arithmetic in the module; every cited constant bound to exactly
one governing record, matching the design's constant table row by row
(governing record, corroborators, agreements, notes, locators); a
module-namespace walk asserts every module-level ``SECONDARY_ATTESTATION``
citation (governing or corroborator) is named in ``BLOCKED_CITATIONS``;
every pending constant has a blocking method and no numeric value anywhere
in the module; the module's Coggan record agrees with the shipped
channels-layer Coggan record on authors, year and work while carrying its
own locator; the module's import allowlist (shared citation vocabulary, the
method vocabulary, stdlib only, and no relative import); and that ``0.95``
and other phrasings of the unverified twenty-minute power factor appear
nowhere under ``src/fitdocs/performance/``.
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib
import re

import pytest

import fitdocs.performance.sources as sources
from fitdocs.citation import (
    Agreement,
    Citation,
    CitedConstant,
    Departure,
    FitdocsChoice,
    VerificationStatus,
)
from fitdocs.load.channels.sources import COGGAN_TSS
from fitdocs.performance.types import DerivationMethod


def _module_source() -> str:
    return pathlib.Path(sources.__file__).resolve().read_text(encoding="utf-8")


def _module_tree() -> ast.AST:
    path = pathlib.Path(sources.__file__).resolve()
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


# --- No arithmetic (design: "Holds no arithmetic") --------------------------


def test_module_holds_no_arithmetic() -> None:
    tree = _module_tree()
    arithmetic_ops = (
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.MatMult,
    )
    unary_arithmetic_ops = (ast.UAdd, ast.USub)
    arithmetic_builtins = {"sum", "pow", "abs", "round", "divmod", "min", "max"}
    nodes = list(ast.walk(tree))
    assert nodes, "the walk collected nothing"
    for node in nodes:
        assert not (
            isinstance(node, ast.BinOp) and isinstance(node.op, arithmetic_ops)
        ), ast.dump(node)
        assert not (
            isinstance(node, ast.AugAssign) and isinstance(node.op, arithmetic_ops)
        ), ast.dump(node)
        assert not (
            isinstance(node, ast.UnaryOp) and isinstance(node.op, unary_arithmetic_ops)
        ), ast.dump(node)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in arithmetic_builtins
        ):
            raise AssertionError(ast.dump(node))


# --- Import allowlist --------------------------------------------------------


def test_module_imports_only_citation_types_and_stdlib() -> None:
    """Named requirement of task 1.2's pins: this module imports only the
    shared citation vocabulary (``fitdocs.citation``), the method vocabulary
    (``fitdocs.performance.types``) and the standard library -- never
    ``fitdocs.load.channels.sources``, which only the *test* may import
    (design.md's own statement of this rule, "PerformanceSources" section,
    Validation note). Every ``ImportFrom``
    is asserted absolute (``level == 0``) rather than merely filtered to
    absolute ones before classification -- a relative import such as
    ``from ..load.channels import sources`` has ``level == 2`` and would
    previously have been silently skipped by the classification loop,
    passing this test despite reaching the forbidden module by a relative
    path instead of an absolute one."""
    tree = _module_tree()
    internal_imports: set[str] = set()
    stdlib_imports: set[str] = set()
    import_from_nodes = [
        node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ]
    assert import_from_nodes, "the walk found no ImportFrom nodes"
    for node in import_from_nodes:
        assert node.level == 0, ast.dump(node)
        module = node.module or ""
        if module.startswith("fitdocs"):
            internal_imports.add(module)
        else:
            stdlib_imports.add(module.split(".")[0])
    for import_node in ast.walk(tree):
        if isinstance(import_node, ast.Import):
            for alias in import_node.names:
                if alias.name.startswith("fitdocs"):
                    internal_imports.add(alias.name)
                else:
                    stdlib_imports.add(alias.name.split(".")[0])
    assert internal_imports == {"fitdocs.citation", "fitdocs.performance.types"}, (
        internal_imports
    )
    allowed_stdlib = {"__future__", "dataclasses", "typing"}
    assert stdlib_imports <= allowed_stdlib, stdlib_imports


# --- Every cited constant has exactly one governing record ------------------


def test_constant_sources_has_exactly_eleven_constants() -> None:
    assert len(sources.CONSTANT_SOURCES) == 11
    names = {c.name for c in sources.CONSTANT_SOURCES}
    assert len(names) == 11  # pairwise distinct


def test_every_module_level_cited_constant_is_registered_in_constant_sources() -> None:
    """Walks ``vars(sources)`` directly (mirroring
    ``tests/metrics/test_sources.py``'s own registry-vs-namespace walk)
    rather than only asserting ``len(CONSTANT_SOURCES) == 11`` -- so a
    twelfth module-level ``CitedConstant`` left out of the tuple reddens
    here even though it would not change the tuple's own length."""
    module_level = [
        value for value in vars(sources).values() if isinstance(value, CitedConstant)
    ]
    assert module_level, "the walk found no module-level CitedConstant records"
    registered_ids = {id(c) for c in sources.CONSTANT_SOURCES}
    for constant in module_level:
        assert id(constant) in registered_ids, constant.name


def test_every_constant_source_field_is_a_sealed_source_record() -> None:
    """Every ``CitedConstant.source`` is exactly one ``Citation`` or one
    ``FitdocsChoice`` -- the sealed union -- never neither, never something
    else. This is what "exactly one governing record each" means
    mechanically: the dataclass shape already forbids two, so the test
    proves *presence and correct sealing* of the one it does carry."""
    for constant in sources.CONSTANT_SOURCES:
        assert isinstance(constant.source, Citation | FitdocsChoice), constant.name


def test_rounding_half_offset_is_a_cited_constant_governed_by_a_fitdocs_choice() -> (
    None
):
    """Design: ROUNDING_HALF_OFFSET is a CitedConstant (value 0.5) governed
    by a FitdocsChoice, exactly like RIEGEL_SOLVE_TARGET_S -- so the
    arithmetic module's 0.5 is reached through a bound record."""
    assert sources.ROUNDING_HALF_OFFSET.value == 0.5
    assert isinstance(sources.ROUNDING_HALF_OFFSET.source, FitdocsChoice)
    assert sources.ROUNDING_HALF_OFFSET.source is sources.ROUNDING_HALF_OFFSET_CHOICE


def test_constant_table_bindings_match_the_design_exactly() -> None:
    """Every one of the eleven constants bound to the exact governing record
    the design's constant table names, by identity -- not merely by value,
    so a constant silently repointed at a different but equal-valued record
    would still fail this test. Also walks the design table's own
    "Corroborators" column per row: the exact set of corroborator citation
    keys, each row's ``Agreement``, a non-empty ``locator`` on every
    corroboration, ``DRAKE_2024``'s agreement pinned to ``AGREES`` (the only
    AGREES row the design table states), and a required ``note`` on every
    corroboration whose agreement is not AGREES."""
    expected: dict[str, tuple[float, object, frozenset[str]]] = {
        "riegel_exponent": (1.06, sources.RIEGEL_1981, frozenset({"drake_2024"})),
        "riegel_min_duration_s": (210.0, sources.RIEGEL_1981, frozenset()),
        "riegel_max_duration_s": (13800.0, sources.RIEGEL_1981, frozenset()),
        "riegel_solve_target_s": (
            3600.0,
            sources.RIEGEL_SOLVE_TARGET_CHOICE,
            frozenset(),
        ),
        "lthr_min_duration_s": (
            1500.0,
            sources.LTHR_DURATION_WINDOW_CHOICE,
            frozenset({"mcgehee_2005", "dumke_2006"}),
        ),
        "lthr_max_duration_s": (
            4500.0,
            sources.LTHR_DURATION_WINDOW_CHOICE,
            frozenset({"mcgehee_2005", "dumke_2006"}),
        ),
        "effort_span_tolerance": (
            0.05,
            sources.EFFORT_SPAN_TOLERANCE_CHOICE,
            frozenset(),
        ),
        "ftp_definition_min_duration_s": (
            3000.0,
            sources.COGGAN_2003,
            frozenset({"borszcz_2018"}),
        ),
        "ftp_definition_max_duration_s": (
            4200.0,
            sources.COGGAN_2003,
            frozenset({"borszcz_2018"}),
        ),
        "ftp_short_protocol_floor_s": (
            900.0,
            sources.FTP_SHORT_PROTOCOL_FLOOR_CHOICE,
            frozenset(),
        ),
        "rounding_half_offset": (0.5, sources.ROUNDING_HALF_OFFSET_CHOICE, frozenset()),
    }
    by_name = {c.name: c for c in sources.CONSTANT_SOURCES}
    assert set(by_name) == set(expected)
    saw_drake = False
    for name, (value, governing, corroborator_keys) in expected.items():
        constant = by_name[name]
        assert constant.value == value, name
        assert constant.source is governing, name
        actual_keys = frozenset(c.citation.key for c in constant.corroborators)
        assert actual_keys == corroborator_keys, name
        for corroboration in constant.corroborators:
            assert corroboration.locator, (name, corroboration.citation.key)
            if corroboration.agreement is not Agreement.AGREES:
                assert corroboration.note, (name, corroboration.citation.key)
            if corroboration.citation.key == "drake_2024":
                saw_drake = True
                assert corroboration.agreement is Agreement.AGREES, name
    assert saw_drake, "the walk never reached the DRAKE_2024 corroboration"


# --- Secondary-attestation tracked set (Req 8.4) -----------------------------


def test_every_module_level_secondary_attestation_citation_is_tracked() -> None:
    """Design's PerformanceSources states ``BLOCKED_CITATIONS`` names *every*
    citation this module carries under ``SECONDARY_ATTESTATION`` -- governing
    or corroborator, not only a constant's governing record. Walks every
    module-level ``Citation`` directly (mirroring
    ``tests/metrics/test_sources.py``'s own module-namespace walk), rather
    than only ``sources.CONSTANT_SOURCES``'s governing sources, so a
    corroborator carrying ``SECONDARY_ATTESTATION`` but omitted from the
    tracked set still reddens here."""
    citations = [
        value for value in vars(sources).values() if isinstance(value, Citation)
    ]
    assert citations, "the walk found no module-level Citation records"
    for citation in citations:
        if citation.verification == VerificationStatus.SECONDARY_ATTESTATION:
            assert citation.key in sources.BLOCKED_CITATIONS, citation.key


def test_blocked_citations_names_exactly_the_five_secondary_attestation_keys() -> None:
    expected = frozenset(
        {"riegel_1981", "drake_2024", "mcgehee_2005", "dumke_2006", "borszcz_2018"}
    )
    assert expected == sources.BLOCKED_CITATIONS


def test_riegel_1981_carries_secondary_attestation() -> None:
    """Named mutation (task 1.2's pin): flipping this citation's status to
    PRIMARY_TEXT must redden a test. This assertion is exactly the one that
    reds under that mutation."""
    assert sources.RIEGEL_1981.verification == VerificationStatus.SECONDARY_ATTESTATION
    assert sources.RIEGEL_1981.key in sources.BLOCKED_CITATIONS


def test_riegel_1981_note_states_the_jstor_text_has_not_been_read() -> None:
    """Named mutation (round 3): asserts the not-read statement on the
    locator field directly rather than a substring check over
    locator+note, which the note's own unrelated "... not read from this
    citation" sentence (about RIEGEL_SOLVE_TARGET_CHOICE, not the JSTOR
    text) previously satisfied on its own, leaving the locator's actual
    "not read by this project" wording unchecked."""
    locator = sources.RIEGEL_1981.locator or ""
    assert "not read by this project" in locator
    text = locator + (sources.RIEGEL_1981.note or "")
    assert "jstor" in text.lower()


def test_four_corroborators_carry_secondary_attestation_and_no_locator() -> None:
    """Req 8.4/8.6: none of the four corroborator-only citations has been
    read by this project -- each carries ``SECONDARY_ATTESTATION`` and a
    ``None`` locator (unlike ``COGGAN_2003``, whose locator is populated
    because it *was* read)."""
    for citation in (
        sources.DRAKE_2024,
        sources.MCGEHEE_2005,
        sources.DUMKE_2006,
        sources.BORSZCZ_2018,
    ):
        assert citation.verification == VerificationStatus.SECONDARY_ATTESTATION, (
            citation.key
        )
        assert citation.locator is None, citation.key


# --- Pending constants and blocked methods (Req 8.5) -------------------------


def test_pending_constants_names_exactly_the_twenty_minute_factor() -> None:
    assert len(sources.PENDING_CONSTANTS) == 1
    pending = sources.PENDING_CONSTANTS[0]
    assert pending.name == "ftp_twenty_minute_power_factor"
    assert pending.blocks is DerivationMethod.TWENTY_MINUTE_POWER_FACTOR


def test_every_pending_constant_has_a_blocking_method_in_blocked_methods() -> None:
    for pending in sources.PENDING_CONSTANTS:
        assert pending.blocks in sources.BLOCKED_METHODS, pending.name


def test_blocked_methods_names_exactly_the_twenty_minute_factor() -> None:
    assert (
        frozenset({DerivationMethod.TWENTY_MINUTE_POWER_FACTOR})
        == sources.BLOCKED_METHODS
    )


_PENDING_VALUE_PATTERN = re.compile(r"(?<!\d)(?:0?\.95\d*|95\s*(?:%|percent)|95e-?\d)")
"""Matches ``0.95``, ``(0.95)``, ``0.950``, ``.95``, ``95 %``, ``95 percent``
and ``95e-2`` -- every phrasing this session found plausible for smuggling
the unverified twenty-minute power factor into prose -- while rejecting a
bare ``95`` that names something else entirely, such as ``95 W``, ``95 s``
or the year ``1995``: none of those carries a decimal point, a percent sign,
the word "percent" or scientific-notation ``e``, so none matches. The
previous form of this pattern, ``(?<![\\d.])\\.?95(?!\\d)``, had both
defects at once: ``re.search`` against it on ``"0.95"`` returns ``None``
(the lookbehind at the "." position sees the preceding "0", a digit, and
rejects the match), while it matches ``"95 W"`` (the optional leading dot is
absent, "95" is followed by a space rather than a digit, so the lookahead
``(?!\\d)`` is satisfied) -- silently missing the exact value this test
exists to catch while flagging unrelated text. See
:func:`test_pending_value_pattern_matches_intended_phrasings` and
:func:`test_pending_value_pattern_rejects_unrelated_text` for a direct,
parametrised proof of both claims."""


@pytest.mark.parametrize(
    "text",
    [
        "0.95",
        "(0.95)",
        "0.950",
        ".95",
        "a factor of 95 %",
        "roughly 95 percent",
        "9.5e1 is not this, but 95e-2 is",
    ],
)
def test_pending_value_pattern_matches_intended_phrasings(text: str) -> None:
    assert _PENDING_VALUE_PATTERN.search(text), text


@pytest.mark.parametrize(
    "text",
    [
        "95 W",
        "95 s",
        "in 1995",
        "95",
    ],
)
def test_pending_value_pattern_rejects_unrelated_text(text: str) -> None:
    assert not _PENDING_VALUE_PATTERN.search(text), text


def test_no_pending_value_phrasing_appears_on_any_pending_constant_field() -> None:
    """8.5: no numeric phrasing of the unverified factor appears anywhere in
    a PendingConstant record -- swept with :data:`_PENDING_VALUE_PATTERN`
    over every field, not merely a literal ``0.95`` substring check."""
    for pending in sources.PENDING_CONSTANTS:
        for field_value in (
            pending.name,
            pending.suspected_work,
            pending.suspected_locator,
            pending.what_would_resolve,
        ):
            assert not _PENDING_VALUE_PATTERN.search(field_value), field_value


def test_pending_constant_has_no_value_or_factor_field() -> None:
    """8.5: ``PendingConstant`` has no dataclass field named ``value`` or
    ``factor`` -- checked through ``dataclasses.fields`` (real introspection
    of the frozen dataclass's declared fields), not ``hasattr``, which would
    be ``False`` for an annotation-only attribute either way and prove
    nothing."""
    field_names = {f.name for f in dataclasses.fields(sources.PendingConstant)}
    assert field_names, "the walk found no dataclass fields on PendingConstant"
    assert "value" not in field_names
    assert "factor" not in field_names


def test_the_number_0_95_appears_nowhere_in_the_performance_package() -> None:
    """Req 8.5's strongest form: the unverified twenty-minute factor's
    numeric value, 0.95, and the phrasings :data:`_PENDING_VALUE_PATTERN`
    matches, do not appear anywhere in this package -- not in this module,
    not anywhere else under ``src/fitdocs/performance/``."""
    package_dir = pathlib.Path(sources.__file__).resolve().parent
    py_files = sorted(package_dir.rglob("*.py"))
    assert py_files, "the walk found no files under src/fitdocs/performance/"
    for path in py_files:
        text = path.read_text(encoding="utf-8")
        assert "0.95" not in text, path
        assert not _PENDING_VALUE_PATTERN.search(text), path


def test_borszcz_carries_the_measured_forty_watt_limits_of_agreement() -> None:
    """Req 4.8: a derived FTP entry's provenance carries the measured limits
    of agreement Borszcz et al. (2018) reports. Checked across the
    citation's own note and every corroboration note naming it, so the
    figure is not required to live in one specific field to pass."""
    text = sources.BORSZCZ_2018.note or ""
    for constant in sources.CONSTANT_SOURCES:
        for corroboration in constant.corroborators:
            if corroboration.citation.key == sources.BORSZCZ_2018.key:
                text += corroboration.note or ""
    assert "40 W" in text, text


# --- Coggan cross-module agreement (Req 8.8) --------------------------------


def test_coggan_record_agrees_with_the_shipped_channels_layer_record() -> None:
    """This module's Coggan (2003) record agrees with the shipped
    channels-layer Coggan record on authors, year and work, while carrying
    its own locator (Req 8.8). Only this test may import both modules."""
    mine = sources.COGGAN_2003
    theirs = COGGAN_TSS
    assert mine.authors == theirs.authors
    assert mine.year == theirs.year
    assert mine.work == theirs.work
    assert mine.locator != theirs.locator
    assert mine.key != theirs.key


# --- Departure (the coaching protocol) --------------------------------------


def test_departures_records_the_coaching_protocol_as_not_implemented() -> None:
    assert len(sources.DEPARTURES) == 1
    departure = sources.DEPARTURES[0]
    assert isinstance(departure, Departure)
    assert "twenty" in departure.subject.lower() or "20" in departure.subject
    assert "10" in departure.reason
    assert "mcgehee" in departure.reason.lower()
    assert "dumke" in departure.reason.lower()


def test_departure_subjects_are_unique() -> None:
    subjects = [d.subject for d in sources.DEPARTURES]
    assert len(subjects) == len(set(subjects))


# --- Shape sanity over the FitdocsChoice records ----------------------------


def test_all_fitdocschoice_records_carry_fitdocs_measured_verification() -> None:
    choices = [
        value for value in vars(sources).values() if isinstance(value, FitdocsChoice)
    ]
    assert len(choices) == 5, choices
    for record in choices:
        assert record.verification == VerificationStatus.FITDOCS_MEASURED, record.key
        assert record.measurement is None, record.key


def test_every_fitdocschoice_carries_non_empty_justification_and_search_basis() -> None:
    """Req 8.2: every ``FitdocsChoice`` this module carries states both why
    the value was chosen and what was searched before choosing it -- neither
    field may be empty."""
    choices = [
        value for value in vars(sources).values() if isinstance(value, FitdocsChoice)
    ]
    assert choices, "the walk found no FitdocsChoice records"
    for record in choices:
        assert record.justification, record.key
        assert record.search_basis, record.key


def test_exactly_six_citation_records_are_module_level_finals() -> None:
    citation_instances = [
        value for value in vars(sources).values() if isinstance(value, Citation)
    ]
    assert len(citation_instances) == 6, citation_instances
    keys = {c.key for c in citation_instances}
    assert len(keys) == 6


def test_riegel_1981_and_coggan_are_the_only_governing_citations() -> None:
    """Of the six citations, only RIEGEL_1981 and COGGAN_2003 govern a
    constant in CONSTANT_SOURCES -- DRAKE_2024, MCGEHEE_2005, DUMKE_2006 and
    BORSZCZ_2018 appear only as corroborators."""
    governing_keys = {
        c.source.key for c in sources.CONSTANT_SOURCES if isinstance(c.source, Citation)
    }
    assert governing_keys == {sources.RIEGEL_1981.key, sources.COGGAN_2003.key}


def test_corroborator_only_citations_are_referenced_as_corroborators() -> None:
    corroborator_keys: set[str] = set()
    for constant in sources.CONSTANT_SOURCES:
        for corroboration in constant.corroborators:
            corroborator_keys.add(corroboration.citation.key)
    assert corroborator_keys == {
        sources.DRAKE_2024.key,
        sources.MCGEHEE_2005.key,
        sources.DUMKE_2006.key,
        sources.BORSZCZ_2018.key,
    }


def test_all_citation_and_constant_keys_are_pairwise_distinct() -> None:
    citation_instances = [
        value for value in vars(sources).values() if isinstance(value, Citation)
    ]
    choice_instances = [
        value for value in vars(sources).values() if isinstance(value, FitdocsChoice)
    ]
    keys = [c.key for c in citation_instances] + [c.key for c in choice_instances]
    assert len(keys) == len(set(keys))


def test_module_does_not_reference_a_working_document_under_docs_reference() -> None:
    text = _module_source()
    assert "docs/reference" not in text


def test_cited_constant_type_is_used_for_every_binding() -> None:
    for constant in sources.CONSTANT_SOURCES:
        assert isinstance(constant, CitedConstant)
