"""The numeric-literal guard over `fitdocs.performance.models` and (task 3.4)
`fitdocs.performance.derive` (task 1.3; Req 8.1, 8.3), imitating
`tests/metrics/test_constant_guard.py`'s pattern:
parse the module as source text, collect every numeric `ast.Constant` its
syntax tree actually contains, and require each one to be named in
`_EXEMPTIONS` at its exact `(line, col_offset, value)` -- a walk over
`CONSTANT_SOURCES` could only ever confirm what is already registered there
(it cannot see a bare number that was never routed through a `CitedConstant`
at all), so this is a second, independent check with no shared state.

`_SCANNED_MODULES` is a tuple, not a single module, so task 3.4 can append
`derive.py` to it later without restructuring this file, per tasks.md §
Test File Ownership: "`tests/performance/test_constant_guard.py` (new) →
1.3 creates it for the arithmetic module; 3.4 extends its scanned-module
list to the derivation module."

A bare numeric `ast.Constant` is not the only way a methodology constant can
be smuggled past the exemption scan: `exponent = float("1.06")` never
produces an `ast.Constant` of type `int`/`float` at all, since the literal
is a `str` argument to a `float(...)` call. `_numeric_literals` below also
treats a `float`/`int` call over a single string constant as a literal for
exactly that reason, and
`test_riegel_and_rounding_constant_assignments_read_only_cited_sources`
independently walks `models.py`'s assignments to prove the module contains
exactly four assignments to its three constant-holding names (`exponent`,
`target_s`, `offset`) whose right-hand side is a `sources.<NAME>.value`
read -- `RIEGEL_EXPONENT` once, `RIEGEL_SOLVE_TARGET_S` twice,
`ROUNDING_HALF_OFFSET` once -- so replacing any one of them with a literal
or a call drops the count or breaks the multiset.
"""

from __future__ import annotations

import ast
import enum
import pathlib
from collections import Counter
from dataclasses import dataclass
from types import ModuleType

from fitdocs.performance import derive, models

_SCANNED_MODULES: tuple[ModuleType, ...] = (models, derive)
"""Task 3.4 appends `derive` here, per the note above -- the tuple restructure
no other task needed to make."""


class ExemptionCategory(enum.Enum):
    """The reasons a numeric literal in a scanned module may go uncited."""

    UNIT_CONVERSION = "unit_conversion"
    ARITHMETIC_IDENTITY = "arithmetic_identity"
    INDEX = "index"


@dataclass(frozen=True)
class LiteralExemption:
    """One numeric literal this scan is told to pass over, and why.
    `col_offset` is load-bearing alongside `line` and `value`, exactly as in
    the metrics guard: two distinct AST nodes on the same line can share a
    `(line, value)` pair while being two different sites."""

    module: str
    line: int
    col_offset: int
    value: int | float
    category: ExemptionCategory
    reason: str


# --- exemption list (Req 8.3) ------------------------------------------------
#
# Every entry below was checked against `models.py`'s exact source line and
# column. None is a cited constant (those are `sources.FOO.value` attribute
# accesses, never bare literals -- see
# `test_a_cited_constant_access_does_not_appear_as_a_literal` below); each is
# either an arithmetic identity (a loop bound, a consecutive-pair index, an
# additive-identity accumulator start, a divisor/sign guard) or the one
# registered unit conversion (metres to kilometres).

_EXEMPTIONS: tuple[LiteralExemption, ...] = (
    LiteralExemption(
        "models.py",
        53,
        44,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`value > 0` is the positivity boundary `_is_finite_positive` tests "
        "against; zero is the definition of non-positive, not a "
        "methodology constant.",
    ),
    LiteralExemption(
        "models.py",
        69,
        54,
        1.0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`1.0 / exponent` takes the Riegel exponent's multiplicative "
        "inverse -- the model's own algebraic solve for distance given "
        "time, not an independent literal.",
    ),
    LiteralExemption(
        "models.py",
        83,
        38,
        1000.0,
        ExemptionCategory.UNIT_CONVERSION,
        "converts the equivalent distance from metres to kilometres before "
        "dividing the one-hour solve target by it, to report pace per "
        "kilometre.",
    ),
    LiteralExemption(
        "models.py",
        98,
        19,
        0.0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`total_weight` starts at the additive identity before summing "
        "each covered interval's duration.",
    ),
    LiteralExemption(
        "models.py",
        99,
        21,
        0.0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`covered_weight` starts at the additive identity before summing "
        "the subset of the span whose earlier sample is not `None`.",
    ),
    LiteralExemption(
        "models.py",
        100,
        19,
        0.0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`weighted_sum` starts at the additive identity before summing "
        "each covered interval's value-times-duration contribution.",
    ),
    LiteralExemption(
        "models.py",
        101,
        23,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "the number of consecutive sample pairs among `n` samples is one "
        "fewer than the sample count.",
    ),
    LiteralExemption(
        "models.py",
        102,
        24,
        1,
        ExemptionCategory.INDEX,
        "`time_s[i + 1]` indexes the consecutive pair's later sample.",
    ),
    LiteralExemption(
        "models.py",
        103,
        17,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`dt <= 0` excludes a non-positive interval from the sum; only a "
        "positive elapsed interval between samples contributes, matching "
        "`stream_coverage`'s own guard.",
    ),
    LiteralExemption(
        "models.py",
        111,
        23,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`total_weight <= 0` is the zero-span absent-data guard; a "
        "non-positive total span cannot support a mean.",
    ),
    LiteralExemption(
        "models.py",
        111,
        46,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`covered_weight <= 0` is the wholly-unrecorded-stream absent-data "
        "guard; zero covered weight cannot support a mean, a distinct "
        "AST site from the `total_weight` guard on the same line.",
    ),
    LiteralExemption(
        "models.py",
        125,
        12,
        0.0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`total` starts at the additive identity before summing each "
        "positive consecutive interval's duration.",
    ),
    LiteralExemption(
        "models.py",
        126,
        23,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "the number of consecutive sample pairs among `n` samples is one "
        "fewer than the sample count.",
    ),
    LiteralExemption(
        "models.py",
        127,
        24,
        1,
        ExemptionCategory.INDEX,
        "`time_s[i + 1]` indexes the consecutive pair's later sample.",
    ),
    LiteralExemption(
        "models.py",
        128,
        16,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`dt > 0` is the same positive-interval guard `stream_coverage` "
        "uses before crediting a span.",
    ),
    LiteralExemption(
        "models.py",
        131,
        16,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`total <= 0` is the absent-data guard for a zero or negative recorded span.",
    ),
    LiteralExemption(
        "models.py",
        144,
        16,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`value >= 0` is the sign test choosing which direction "
        "'away from zero' means for the rounding offset.",
    ),
    LiteralExemption(
        "derive.py",
        69,
        44,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`value > 0` is the positivity boundary `_finite_positive` tests "
        "against -- the same arithmetic identity as `models.py`'s own "
        "`_is_finite_positive`; zero is the definition of non-positive, "
        "not a methodology constant.",
    ),
)


def _numeric_literals(
    module: ModuleType,
) -> list[tuple[int, int, int | float | str]]:
    """Every `(line, col_offset, value)` triple for a numeric (non-`bool`)
    `Constant` node anywhere in `module`'s own source, plus one entry per
    `float(...)`/`int(...)` call over a single string constant (e.g.
    `float("1.06")`) -- a call that smuggles a methodology constant past the
    plain-`Constant` scan above by wrapping it in a string, at the call
    node's own `(line, col_offset)` with the quoted string as `value`."""
    path = pathlib.Path(module.__file__ or "").resolve()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    literals: list[tuple[int, int, int | float | str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        ):
            literals.append((node.lineno, node.col_offset, node.value))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("float", "int")
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            literals.append((node.lineno, node.col_offset, node.args[0].value))
    return literals


def _exemptions_by_module() -> dict[str, set[tuple[int, int, int | float]]]:
    by_module: dict[str, set[tuple[int, int, int | float]]] = {}
    for exemption in _EXEMPTIONS:
        by_module.setdefault(exemption.module, set()).add(
            (exemption.line, exemption.col_offset, exemption.value)
        )
    return by_module


def test_every_numeric_literal_in_models_is_exempted() -> None:
    """Every numeric literal the scan finds in `models.py` must be named in
    `_EXEMPTIONS` at its exact line, column and value. A bare number added
    to the module that is not already covered by name, line, column and
    value reddens this test. Asserts non-vacuity at every stage: the module
    tuple is non-empty, the walk finds at least one literal per module, and
    at least one literal overall -- a walk that silently scanned zero files
    would otherwise pass trivially."""
    assert _SCANNED_MODULES, "the scanned-module tuple is empty"
    exemptions_by_module = _exemptions_by_module()
    scanned_modules = 0
    scanned_literals = 0
    for module in _SCANNED_MODULES:
        module_name = pathlib.Path(module.__file__ or "").name
        literals = _numeric_literals(module)
        assert literals, f"the walk found no numeric literals in {module_name}"
        scanned_modules += 1
        allowed = exemptions_by_module.get(module_name, set())
        for line, col_offset, value in literals:
            scanned_literals += 1
            assert (line, col_offset, value) in allowed, (
                f"{module_name}:{line}:{col_offset} literal {value!r} is "
                "neither read from a CitedConstant nor present in _EXEMPTIONS"
            )
    assert scanned_modules == len(_SCANNED_MODULES), (
        "the walk did not reach every scanned module"
    )
    assert scanned_literals, "the walk found no numeric literals to check at all"


def test_no_exemption_entry_is_unused() -> None:
    """Every entry in `_EXEMPTIONS` must actually match a numeric literal
    the scan finds in its named module, at its named line, column and
    value -- an entry that matches nothing (a stale site, a typo'd line or
    column, a speculative entry for a literal never written) reddens this
    test rather than sitting unused forever."""
    found_by_module: dict[str, set[tuple[int, int, int | float | str]]] = {}
    for module in _SCANNED_MODULES:
        module_name = pathlib.Path(module.__file__ or "").name
        found_by_module[module_name] = set(_numeric_literals(module))

    assert _EXEMPTIONS, "the exemption list is empty -- nothing to check for use"
    for exemption in _EXEMPTIONS:
        found = found_by_module.get(exemption.module, set())
        assert (exemption.line, exemption.col_offset, exemption.value) in found, (
            f"{exemption.module}:{exemption.line}:{exemption.col_offset} "
            f"value {exemption.value!r} is an unused exemption entry -- no "
            "such literal was found in the scan"
        )


def test_a_cited_constant_access_does_not_appear_as_a_literal() -> None:
    """Reading a value through its `CitedConstant` (`sources.FOO.value`) is
    an `ast.Attribute` access, never an `ast.Constant` literal, so none of
    the four `sources.<NAME>.value` reads `models.py` performs
    (`RIEGEL_EXPONENT` once, `RIEGEL_SOLVE_TARGET_S` twice,
    `ROUNDING_HALF_OFFSET` once) ever needs an `_EXEMPTIONS` entry of its
    own. Checked directly against the module's own AST: every
    `ast.Attribute` node whose attribute name is `"value"` and whose own
    value is itself an `ast.Attribute` on the `sources` module name is one
    of these reads -- exactly four must be found, or the walk either missed
    a read or is proving nothing."""
    path = pathlib.Path(models.__file__ or "").resolve()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    sourced_value_reads = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "value"
            and isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "sources"
        ):
            sourced_value_reads += 1
    assert sourced_value_reads == 4, (
        "expected exactly four `sources.FOO.value` reads in models.py "
        "(RIEGEL_EXPONENT once, RIEGEL_SOLVE_TARGET_S twice, "
        f"ROUNDING_HALF_OFFSET once); found {sourced_value_reads}"
    )


_CONSTANT_ASSIGNMENT_NAMES = frozenset({"exponent", "target_s", "offset"})


def _constant_assignment_source_reads(module: ModuleType) -> list[str]:
    """The `<NAME>` in `sources.<NAME>.value`, one entry per `ast.Assign` in
    `module` whose sole target is one of `_CONSTANT_ASSIGNMENT_NAMES` and
    whose right-hand side is exactly that attribute access. An assignment to
    one of those names from anything else (a bare literal, a `float(...)`/
    `int(...)` call, a different attribute chain) contributes no entry,
    which is exactly what should make this list too short or wrong."""
    path = pathlib.Path(module.__file__ or "").resolve()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    reads: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if node.targets[0].id not in _CONSTANT_ASSIGNMENT_NAMES:
            continue
        value = node.value
        if (
            isinstance(value, ast.Attribute)
            and value.attr == "value"
            and isinstance(value.value, ast.Attribute)
            and isinstance(value.value.value, ast.Name)
            and value.value.value.id == "sources"
        ):
            reads.append(value.value.attr)
    return reads


def test_riegel_and_rounding_constant_assignments_read_only_cited_sources() -> None:
    """`models.py` holds its cited constants in exactly three
    assignment-target names (`exponent`, `target_s`, `offset`) before using
    them in arithmetic. `exponent = float("1.06")` or `offset = float("0.5")`
    is caught three ways in this file -- by `_numeric_literals`' float/int
    -over-string branch, by the exact-four sourced-read count, and by this
    walk; this is the test that also pins *which* name each assignment
    reads. There are
    exactly four such assignments in the module (`target_s` is assigned
    once in each of the two Riegel functions), and together they read
    `RIEGEL_EXPONENT` once, `RIEGEL_SOLVE_TARGET_S` twice and
    `ROUNDING_HALF_OFFSET` once -- checked as an exact multiset so that
    substituting one cited name for another (which would leave the *set* of
    names unchanged, since `RIEGEL_EXPONENT` already appears once) still
    fails this assertion."""
    reads = _constant_assignment_source_reads(models)
    assert reads, "the walk found no exponent/target_s/offset assignments at all"
    assert len(reads) == 4, (
        f"expected exactly 4 assignments of exponent/target_s/offset read "
        f"from a `sources.*.value` attribute access; found {len(reads)}: {reads!r}"
    )
    assert Counter(reads) == Counter(
        {
            "RIEGEL_EXPONENT": 1,
            "RIEGEL_SOLVE_TARGET_S": 2,
            "ROUNDING_HALF_OFFSET": 1,
        }
    ), f"expected exactly this multiset of sourced names; found {Counter(reads)!r}"
