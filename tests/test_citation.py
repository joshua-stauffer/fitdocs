"""Tests for the shared citation vocabulary (``fitdocs.citation``, Amendment 1).

Covers Requirements 15.2, 15.8, 15.9, 16.1, 16.4, 16.5, 16.6, 16.7 -- see
``.kiro/specs/fit-ingest/requirements.md`` and the "CitationVocabulary
(`src/fitdocs/citation.py`)" component in design.md.

This module is itself named in ``[tool.mypy].files`` in ``pyproject.toml``, so
strict mypy reads it; ``test_primary_text_on_fitdocs_choice_is_a_static_type_error``
below carries a ``# type: ignore[arg-type]`` mypy would flag as *unused* the
moment ``FitdocsChoice.verification`` stops being pinned to
``Literal[VerificationStatus.FITDOCS_MEASURED]`` -- that is Req 16.4's negative
claim, verified by ``uv run mypy`` rather than at runtime (dataclasses do not
enforce field types at construction time).
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib
import subprocess
import sys
import typing

import pytest

import fitdocs.citation as citation
from fitdocs.citation import (
    Agreement,
    Citation,
    CitedConstant,
    Corroboration,
    Departure,
    FitdocsChoice,
    SourceRecord,
    VerificationStatus,
)


def test_module_does_not_import_sdk_in_subprocess() -> None:
    """A fresh import of the citation vocabulary must not pull in the FIT SDK
    or any other fitdocs module (16.6: readable by any consumer without
    computing a metric)."""
    code = (
        "import sys\n"
        "import fitdocs.citation\n"
        "assert 'garmin_fit_sdk' not in sys.modules, sorted(sys.modules)\n"
        "internal = [m for m in sys.modules "
        "if m.startswith('fitdocs.') and m != 'fitdocs.citation']\n"
        "assert internal == [], internal\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_module_source_has_no_sdk_or_internal_imports() -> None:
    source = citation.__file__ or ""
    assert source, "citation.__file__ should be set"
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "garmin_fit_sdk" not in text
    assert "from fitdocs" not in text
    assert "import fitdocs" not in text


def test_module_holds_no_arithmetic_and_no_records() -> None:
    """The module defines shapes only -- no module-level record instance and
    no arithmetic (tasks.md 8.1 bullet 2).

    The scan is not statement-form-based: enumerating which *statements* to
    look inside (``Assign``, ``AnnAssign``, ``Expr``, recursing only into
    ``ClassDef``/``FunctionDef``) is exactly what made a value hidden inside
    an ``if``/``try``/``for`` block or a function's ``return`` invisible to
    an earlier version of this scan. Instead this walks the *entire* module
    (``ast.walk(tree)``), with no exclusions, and asserts no ``ast.BinOp``
    with an arithmetic operator and no ``ast.Call`` to a record type appears
    anywhere in it. The module's own ``str | None`` field annotations and
    the ``SourceRecord = Citation | FitdocsChoice`` union assignment do not
    need to be exempted and are not exempted: ``|`` parses to
    ``ast.BinOp(op=ast.BitOr)``, and ``ast.BitOr`` is not one of the
    arithmetic operators this scan checks for (see ``arithmetic_ops``
    below), so those nodes simply never match either assertion. A records
    tuple, a records dict, an ``if``/``try``/``for`` block, or a module-level
    ``def`` whose body constructs a record or computes arithmetic and
    ``return``s it are all visible to the scan and would fail it.

    Separately, every module-*scope* assignment target (``ast.Assign`` or
    ``ast.AnnAssign``, including one nested inside a module-level ``if``/
    ``try``/``for``/``while``/``with`` -- anything short of a new class or
    function scope) is only the type alias (``SourceRecord``) or the
    ``TypeVar`` (``_N``)."""
    source = citation.__file__ or ""
    assert source, "citation.__file__ should be set"
    tree = ast.parse(pathlib.Path(source).read_text(), filename=source)

    record_type_names = {
        "Citation",
        "FitdocsChoice",
        "Corroboration",
        "Departure",
        "CitedConstant",
    }
    # Deliberately strict: only the two names this module actually assigns
    # at module scope are permitted. Adding a legitimate `__all__ = [...]`
    # later would red this guard too -- intentional, not an oversight; widen
    # this set explicitly if that day comes.
    permitted_assign_targets = {"SourceRecord", "_N"}

    def module_scope_statements(node: ast.AST) -> list[ast.stmt]:
        """Statements reachable without crossing into a new class or function
        scope: recurses into control-flow bodies (``if``/``try``/``for``/
        ``while``/``with``) but never into ``ClassDef``, ``FunctionDef``,
        ``AsyncFunctionDef`` or ``Lambda``."""
        collected: list[ast.stmt] = []
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.stmt):
                collected.append(child)
            if isinstance(
                child,
                (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
            ):
                continue
            collected.extend(module_scope_statements(child))
        return collected

    module_statements = module_scope_statements(tree)
    assigns = [
        node
        for node in module_statements
        if isinstance(node, (ast.Assign, ast.AnnAssign))
    ]
    assert assigns, "the module-scope walk found no assignments to scan"
    top_level = list(ast.iter_child_nodes(tree))
    class_defs = [node for node in top_level if isinstance(node, ast.ClassDef)]
    assert class_defs, "the walk found no class definitions to scan"

    # every module-scope assignment target is one of the two permitted names.
    for assign_node in assigns:
        if isinstance(assign_node, ast.Assign):
            names = {t.id for t in assign_node.targets if isinstance(t, ast.Name)}
        elif isinstance(assign_node, ast.AnnAssign) and isinstance(
            assign_node.target, ast.Name
        ):
            names = {assign_node.target.id}
        else:
            names = {"<non-name>"}
        assert names <= permitted_assign_targets, ast.dump(assign_node)

    # arithmetic/record-call scan over the whole module, no exclusions.
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

    for node in ast.walk(tree):
        if isinstance(node, ast.AugAssign):
            pytest.fail(ast.dump(node))

    scanned_nodes = list(ast.walk(tree))
    assert scanned_nodes, "the module-wide walk collected nothing"
    calls_found = [node for node in scanned_nodes if isinstance(node, ast.Call)]
    assert calls_found, (
        "the module-wide walk found no ast.Call nodes at all -- "
        "positive control for the record-call scan below (the module's own "
        "`TypeVar(...)` call should always be found)"
    )

    for node in scanned_nodes:
        assert not (
            isinstance(node, ast.BinOp) and isinstance(node.op, arithmetic_ops)
        ), ast.dump(node)
        assert not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in record_type_names
        ), ast.dump(node)


def test_verification_status_has_exactly_three_members() -> None:
    members = {member.value for member in VerificationStatus}
    assert members == {"primary_text", "secondary_attestation", "fitdocs_measured"}
    assert isinstance(VerificationStatus.PRIMARY_TEXT, str)


def _assert_field_contract(cls: type, expected: list[tuple[str, object, bool]]) -> None:
    """Assert every field of a citation-vocabulary dataclass matches
    ``expected`` in declared order: field name, resolved type hint, and
    whether the field is required (carries neither a ``default`` nor a
    ``default_factory``). Uses ``dataclasses.fields`` and
    ``typing.get_type_hints`` rather than ``hasattr``/``dir`` -- a dataclass
    field with no default is absent from ``vars(instance)`` either way, and
    ``dir()`` omits annotation-only members, so either would be vacuous here."""
    fields = dataclasses.fields(cls)
    assert [f.name for f in fields] == [name for name, _, _ in expected]
    hints = typing.get_type_hints(cls)
    for field, (name, hint, required) in zip(fields, expected, strict=True):
        assert hints[name] == hint, name
        has_default = (
            field.default is not dataclasses.MISSING
            or field.default_factory is not dataclasses.MISSING
        )
        assert has_default is not required, name


def test_citation_carries_the_16_1_fields() -> None:
    """16.1: a published-work record states authors, year, work, locator and
    verification status -- all required (no default), in declared order,
    plus the optional trailing ``note``."""
    _assert_field_contract(
        Citation,
        [
            ("key", str, True),
            ("authors", str, True),
            ("year", int, True),
            ("work", str, True),
            ("locator", str | None, True),
            ("verification", VerificationStatus, True),
            ("note", str | None, False),
        ],
    )


def test_citation_is_frozen() -> None:
    made = Citation(
        key="k",
        authors="A",
        year=1990,
        work="W",
        locator="p1",
        verification=VerificationStatus.PRIMARY_TEXT,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        made.year = 1991  # type: ignore[misc]


def test_fitdocs_choice_carries_the_15_8_15_9_fields_in_place_of_authorship() -> None:
    """15.8, 15.9, 16.7: justification and search_basis stand in for the
    authors/year/work/locator a Citation supplies; there is no field a
    fitdocs-chosen record could leave blank instead. ``key`` and both prose
    fields are required; ``measurement`` and ``verification`` are optional
    (the latter pinned to FITDOCS_MEASURED, checked separately below)."""
    _assert_field_contract(
        FitdocsChoice,
        [
            ("key", str, True),
            ("justification", str, True),
            ("search_basis", str, True),
            ("measurement", str | None, False),
            (
                "verification",
                typing.Literal[VerificationStatus.FITDOCS_MEASURED],
                False,
            ),
        ],
    )
    forbidden = {"authors", "year", "work", "locator"}
    names = {f.name for f in dataclasses.fields(FitdocsChoice)}
    assert names.isdisjoint(forbidden)


def test_fitdocs_choice_verification_defaults_to_fitdocs_measured() -> None:
    choice = FitdocsChoice(key="k", justification="j", search_basis="s")
    assert choice.verification == VerificationStatus.FITDOCS_MEASURED


def test_fitdocs_choice_measurement_defaults_to_none() -> None:
    """15.8: an absent measurement is ``None``, never a fabricated empty
    string -- the absent-is-``None`` rule (CLAUDE.md, tech.md) applies to
    this field the same as it does to the sibling optionals pinned by
    ``test_cited_constant_corroborators_default_to_empty``."""
    choice = FitdocsChoice(key="k", justification="j", search_basis="s")
    assert choice.measurement is None


def test_fitdocs_choice_verification_field_is_pinned_to_a_single_literal() -> None:
    """16.4, structurally: the field type is exactly
    ``Literal[VerificationStatus.FITDOCS_MEASURED]``, a one-member literal, not
    the full ``VerificationStatus`` enum -- there is no value of this field
    that spells ``PRIMARY_TEXT``."""
    hints = typing.get_type_hints(FitdocsChoice, include_extras=True)
    verification_hint = hints["verification"]
    assert typing.get_origin(verification_hint) is typing.Literal
    assert typing.get_args(verification_hint) == (VerificationStatus.FITDOCS_MEASURED,)


def test_primary_text_on_fitdocs_choice_is_a_static_type_error() -> None:
    """16.4's negative claim: mypy rejects this construction; the
    ``# type: ignore[arg-type]`` below is what keeps it green. Widening
    ``FitdocsChoice.verification`` to plain ``VerificationStatus`` in
    production makes the ignore *unused*, which strict mypy reports as an
    error -- verified with ``uv run mypy``, not by this assertion (dataclasses
    do not enforce field types at runtime, so this line constructs cleanly)."""
    choice = FitdocsChoice(
        key="k",
        justification="j",
        search_basis="s",
        verification=VerificationStatus.PRIMARY_TEXT,  # type: ignore[arg-type]
    )
    stored: VerificationStatus = choice.verification
    assert stored == VerificationStatus.PRIMARY_TEXT


def test_source_record_is_the_sealed_citation_fitdocs_choice_union() -> None:
    """16.4: SourceRecord is exactly Citation | FitdocsChoice -- no third
    shape, and not merely Citation alone."""
    assert typing.get_args(SourceRecord) == (Citation, FitdocsChoice)


def test_agreement_enum_has_exactly_three_members() -> None:
    """15.2: a corroborating work agrees with, omits, or differs from the
    value -- distinct outcomes, each named."""
    members = {member.value for member in Agreement}
    assert members == {"agrees", "omits", "differs"}
    assert isinstance(Agreement.AGREES, str)


def test_corroboration_carries_its_own_citation_locator_and_agreement() -> None:
    """15.2: a corroborating work is recorded with the locator *within that
    work* -- required, not merely present in the field-name set, and
    ``str`` (not ``str | None``) -- distinct from the governing constant's
    own locator, plus the agreement relation. Declared order matters:
    ``locator`` precedes the optional ``note``, so a field cannot be
    reordered after an optional field without also acquiring a default."""
    _assert_field_contract(
        Corroboration,
        [
            ("citation", Citation, True),
            ("locator", str, True),
            ("agreement", Agreement, True),
            ("note", str | None, False),
        ],
    )


def test_departure_carries_subject_source_and_fitdocs_behavior_and_reason() -> None:
    """16.5: a deliberate departure records what the source specifies, what
    fitdocs does instead, and the reason -- three distinct fields, not one
    free-text note standing in for all three, and every field required (a
    departure with an unstated subject or unstated reason is not recorded
    at all)."""
    _assert_field_contract(
        Departure,
        [
            ("subject", str, True),
            ("source_specifies", str, True),
            ("fitdocs_does", str, True),
            ("reason", str, True),
        ],
    )


def test_cited_constant_binds_one_source_any_corroborators_and_previous_value() -> None:
    """The binding (support for 16.2, consumed one layer up in
    fitdocs.metrics.sources): exactly one ``source`` field -- not a
    collection -- alongside a ``corroborators`` tuple and the value it
    replaced, all in declared order with the correct required/optional
    split."""
    _assert_field_contract(
        CitedConstant,
        [
            ("name", str, True),
            ("value", citation._N, True),
            ("source", SourceRecord, True),
            ("corroborators", tuple[Corroboration, ...], False),
            ("departure", Departure | None, False),
            ("previous_value", citation._N | None, False),
        ],
    )
    hints = typing.get_type_hints(CitedConstant)
    assert hints["source"] is SourceRecord
    assert typing.get_origin(hints["corroborators"]) is tuple


def test_cited_constant_is_generic_over_its_numeric_value() -> None:
    """Req 15.3's "the value it replaced" ties ``previous_value: _N | None``
    to ``value: _N`` through the same type variable -- only true because
    ``CitedConstant`` actually binds ``Generic[_N]``. Deleting that binding
    leaves the field annotations themselves untouched (so the field-contract
    test above stays green) but removes the class from ``Generic``'s MRO."""
    assert typing.Generic in CitedConstant.__mro__
    assert citation._N.__constraints__ == (int, float)


def test_cited_constant_corroborators_default_to_empty() -> None:
    made = CitedConstant(
        name="n",
        value=1.0,
        source=FitdocsChoice(key="k", justification="j", search_basis="s"),
    )
    assert made.corroborators == ()
    assert made.previous_value is None
    assert made.departure is None


def test_all_record_types_are_frozen() -> None:
    """Every citation-vocabulary dataclass is immutable; mutating any field
    after construction raises."""
    citation_obj = Citation(
        key="k",
        authors="A",
        year=1990,
        work="W",
        locator="p1",
        verification=VerificationStatus.PRIMARY_TEXT,
    )
    choice = FitdocsChoice(key="k2", justification="j", search_basis="s")
    corroboration = Corroboration(
        citation=citation_obj, locator="p2", agreement=Agreement.AGREES
    )
    departure = Departure(
        subject="s", source_specifies="x", fitdocs_does="y", reason="r"
    )
    constant = CitedConstant(name="n", value=1, source=choice)
    for instance, field_name, new_value in (
        (citation_obj, "authors", "B"),
        (choice, "justification", "j2"),
        (corroboration, "locator", "p3"),
        (departure, "reason", "r2"),
        (constant, "value", 2),
    ):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, field_name, new_value)
