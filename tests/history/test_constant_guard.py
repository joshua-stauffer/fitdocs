"""The independent numeric-literal scan over `src/fitdocs/history/` (task
2.1; Req 2.4, 2.6, 2.8, 2.10, 3.4). See the "ModelSources
(`src/fitdocs/history/sources.py`)" component in
`.kiro/specs/load-history/design.md` -- "Validation" bullet.

A registry walk (`tests/history/test_sources.py`) can only ever confirm what
somebody already registered in `CONSTANT_SOURCES`. This module is a second,
independent check that can fail when a constant is *not* registered at all --
a bare number sitting directly in a module's own source, never routed
through a `CitedConstant`. It parses **every `.py` file the package
currently contains** as source text, discovered by walking the package
directory rather than a fixed module list -- design.md's own stated reason:
"it neither reds before its siblings land nor silently skips a module a
later task adds". Today that is `__init__.py` and `sources.py`; a later
task's `model.py`, `documents.py`, `series.py`, `page.py`, `engine.py` and
`settings.py` are swept in automatically once they exist, with no edit to
the walk itself.

Every literal the scan finds must be named in `_EXEMPTIONS` at its exact
site, with a reason. A site is keyed by *what the literal means* --
`(module, enclosing assignment's target name, keyword/field name or
positional index the literal sits under, value)` -- not by its line and
column. A prose-only edit above the table (adding a sentence to a
docstring, inserting a blank line) shifts every line below it but changes
no site's meaning, so it must never red this scan; only a literal actually
moving to a different assignment target, a different keyword, or a
different value is a site change. Unlike the metrics layer's own guard
(which excludes `metrics/sources.py` from its scan entirely, because that
module's literals are themselves the citation values), this package's own
citation module IS in scope -- design.md's "holds no bare numeric literal
carrying a methodological choice" bullet frames the `CitedConstant.value=`
site itself as the one place a methodologically significant number is
*allowed* to be spelled: it is the canonical declaration a caller elsewhere
is required to read through `.value`, not a second, un-cited copy of the
number. Each such site below carries its own `CITED_CONSTANT_VALUE`
exemption, one per constant. Entries and literal occurrences are matched
one-to-one by count at each `(module, target, site, value)` key, so a NEW
bare literal landing anywhere else reds this scan -- and so does a second,
accidental copy of an exempted number inside `sources.py` under the same
target and slot, rather than riding on the sibling entry.

A third, independent assertion carries the package-wide `docs/reference`
rule directly (a string is not a numeric literal): the substring
`"docs/reference"` (built from two pieces here so this file itself is not a
counterexample to what it tests) must appear nowhere under
`src/fitdocs/history/`.
"""

from __future__ import annotations

import ast
import enum
import pathlib
from collections import Counter
from dataclasses import dataclass

import fitdocs.history.sources as sources

_SiteKey = tuple[str | None, str | None, int | float]


def _package_dir() -> pathlib.Path:
    package_dir = pathlib.Path(sources.__file__).resolve().parent
    assert package_dir.name == "history", (
        f"the walk is looking at the wrong directory -- resolved to "
        f"{package_dir} instead of a directory named 'history'"
    )
    return package_dir


def _package_python_files() -> list[pathlib.Path]:
    """Every `.py` file directly under the package, discovered by walking the
    directory -- never a hardcoded module list (design.md's own stated
    reason: this must neither red before its siblings land nor silently
    skip a module a later task adds)."""
    package_dir = _package_dir()
    files = sorted(package_dir.glob("*.py"))
    assert files, "the walk found no .py files under the history package"
    return files


class ExemptionCategory(enum.Enum):
    """The reasons a numeric literal in this package is permitted to appear
    un-routed through a `CitedConstant.value` read elsewhere."""

    CITATION_YEAR = "citation_year"
    """A `Citation`'s own `year` field -- a bibliographic fact, not a
    methodologically significant value the model computes with."""

    CITED_CONSTANT_VALUE = "cited_constant_value"
    """The `value=` argument of a `CitedConstant` construction itself -- the
    one canonical site a methodologically significant number is declared;
    every other module reads it back through `.value`, never respells it."""


@dataclass(frozen=True)
class LiteralExemption:
    """One numeric literal this scan is told to pass over, and why.

    `module` is the file's own name (`"sources.py"`, not an import path).
    `target`, `site` and `value` together identify the exact AST `Constant`
    node the exemption excuses by *meaning*, not by position: `target` is
    the `id` of the `Name` the nearest enclosing `Assign`/`AnnAssign`
    binds (e.g. `"TAU_FITNESS_SEED_DAYS"`), and `site` is the keyword name
    (or `"positional[i]"`) of the call argument slot the literal sits in
    directly (e.g. `"value"`). A literal moving to a different target, a
    different keyword, or a different value is a distinct site and needs
    its own entry; a literal's file merely shifting line/column (a
    docstring edit, a blank line inserted above it) is not, and must not
    require a new entry."""

    module: str
    target: str | None
    site: str | None
    value: int | float
    category: ExemptionCategory
    reason: str


_EXEMPTIONS: tuple[LiteralExemption, ...] = (
    LiteralExemption(
        "sources.py",
        "MORTON_1990_RECURSION",
        "year",
        1990,
        ExemptionCategory.CITATION_YEAR,
        "MORTON_1990_RECURSION.year -- the publication year of the cited "
        "paper, a bibliographic fact rather than a methodologically "
        "significant model value.",
    ),
    LiteralExemption(
        "sources.py",
        "BANISTER_1991_TIME_CONSTANTS",
        "year",
        1991,
        ExemptionCategory.CITATION_YEAR,
        "BANISTER_1991_TIME_CONSTANTS.year -- the publication year of the "
        "cited chapter, a bibliographic fact rather than a methodologically "
        "significant model value.",
    ),
    LiteralExemption(
        "sources.py",
        "TAU_FITNESS_SEED_DAYS",
        "value",
        45.0,
        ExemptionCategory.CITED_CONSTANT_VALUE,
        "TAU_FITNESS_SEED_DAYS.value -- the canonical declaration site for "
        "the shipped fitness time constant; every other module reads this "
        "back through TAU_FITNESS_SEED_DAYS.value, never respells 45.0.",
    ),
    LiteralExemption(
        "sources.py",
        "TAU_FATIGUE_SEED_DAYS",
        "value",
        15.0,
        ExemptionCategory.CITED_CONSTANT_VALUE,
        "TAU_FATIGUE_SEED_DAYS.value -- the canonical declaration site for "
        "the shipped fatigue time constant; every other module reads this "
        "back through TAU_FATIGUE_SEED_DAYS.value, never respells 15.0.",
    ),
    LiteralExemption(
        "sources.py",
        "K_FITNESS_SEED",
        "value",
        1.0,
        ExemptionCategory.CITED_CONSTANT_VALUE,
        "K_FITNESS_SEED.value -- the canonical declaration site for the "
        "shipped fitness weighting; every other module reads this back "
        "through K_FITNESS_SEED.value, never respells 1.0.",
    ),
    LiteralExemption(
        "sources.py",
        "K_FATIGUE_SEED",
        "value",
        1.0,
        ExemptionCategory.CITED_CONSTANT_VALUE,
        "K_FATIGUE_SEED.value -- the canonical declaration site for the "
        "shipped fatigue weighting; every other module reads this back "
        "through K_FATIGUE_SEED.value, never respells 1.0. A distinct site "
        "from K_FITNESS_SEED.value above (different target), even though "
        "both values are 1.0.",
    ),
    LiteralExemption(
        "sources.py",
        "COVERAGE_THRESHOLD",
        "value",
        0.8,
        ExemptionCategory.CITED_CONSTANT_VALUE,
        "COVERAGE_THRESHOLD.value -- the canonical declaration site for the "
        "shipped coverage threshold; every other module reads this back "
        "through COVERAGE_THRESHOLD.value, never respells 0.80.",
    ),
)


def _build_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    """Every node's immediate parent, computed once per tree so the site
    lookup below can walk upward from a `Constant` without `ast` itself
    tracking parent links."""
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _enclosing_target_name(
    node: ast.AST, parents: dict[ast.AST, ast.AST]
) -> str | None:
    """Walk upward from `node` to the nearest enclosing `Assign`/`AnnAssign`
    and return the single `Name` target it binds, or `None` if that
    assignment has no single `Name` target (or none is found before the
    module root)."""
    current: ast.AST | None = node
    while current is not None:
        parent = parents.get(current)
        if isinstance(parent, ast.AnnAssign) and isinstance(parent.target, ast.Name):
            return parent.target.id
        if isinstance(parent, ast.Assign) and len(parent.targets) == 1:
            target = parent.targets[0]
            if isinstance(target, ast.Name):
                return target.id
        current = parent
    return None


def _enclosing_call_site(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str | None:
    """Walk upward from `node` to the nearest ancestor that is a direct
    argument of an `ast.Call` -- a keyword's `value` or one of `call.args`
    -- and name that slot: the keyword's own name, or `"positional[i]"`.
    `None` if no such call is found before the module root."""
    child = node
    parent = parents.get(child)
    while parent is not None:
        if isinstance(parent, ast.keyword) and parent.value is child:
            return parent.arg
        if isinstance(parent, ast.Call):
            for index, arg in enumerate(parent.args):
                if arg is child:
                    return f"positional[{index}]"
        child = parent
        parent = parents.get(child)
    return None


def _numeric_literal_sites(
    path: pathlib.Path,
) -> list[tuple[str | None, str | None, int | float]]:
    """Every `(target, site, value)` triple for a numeric (non-`bool`)
    `Constant` node anywhere in `path`'s source -- the whole tree, not only
    top-level statements."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    parents = _build_parent_map(tree)
    sites: list[tuple[str | None, str | None, int | float]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        ):
            target = _enclosing_target_name(node, parents)
            site = _enclosing_call_site(node, parents)
            sites.append((target, site, node.value))
    return sites


def _exemptions_by_module() -> dict[str, Counter[_SiteKey]]:
    by_module: dict[str, Counter[_SiteKey]] = {}
    for exemption in _EXEMPTIONS:
        by_module.setdefault(exemption.module, Counter())[
            (exemption.target, exemption.site, exemption.value)
        ] += 1
    return by_module


def test_every_numeric_literal_under_the_package_is_exempted() -> None:
    """Every numeric literal the walk finds, in every `.py` file currently
    under `src/fitdocs/history/`, must be matched one-to-one by count with
    an `_EXEMPTIONS` entry at its exact site (enclosing assignment target,
    keyword/position, value). Named mutations: change
    `SEED_CONSTANTS.tau_fitness_days=TAU_FITNESS_SEED_DAYS.value` to
    `SEED_CONSTANTS.tau_fitness_days=45.0` in the module under test -- a new,
    un-exempted `ast.Constant` node lands where an `ast.Attribute` read used
    to be (1 found, 0 entries) and this assertion reds; spell a second
    `45.0` under `TAU_FITNESS_SEED_DAYS` at the same `value` slot (e.g.
    inside a `str(dict(value=45.0))` in its note) -- same key, 2 found,
    1 entry -- and this assertion reds too, rather than the copy riding on
    the sibling entry."""
    exemptions_by_module = _exemptions_by_module()
    scanned_files = 0
    scanned_literals = 0
    for path in _package_python_files():
        scanned_files += 1
        allowed = exemptions_by_module.get(path.name, Counter())
        found = Counter(_numeric_literal_sites(path))
        scanned_literals += sum(found.values())
        for key, count in found.items():
            target, site, value = key
            assert count == allowed[key], (
                f"{path.name}: literal {value!r} under target {target!r} "
                f"site {site!r}: {count} found, {allowed[key]} exemption "
                "entries -- a literal here is neither read from a "
                "CitedConstant nor matched one-to-one in _EXEMPTIONS"
            )
    assert scanned_files, "the walk did not reach any package module"
    assert scanned_literals, "the walk found no numeric literals to check at all"


def test_no_exemption_entry_is_unused() -> None:
    """Every entry in `_EXEMPTIONS` must be matched one-to-one by count with
    a numeric literal the scan finds, at its named module, target, site and
    value -- an over-broad, stale (0 found) or duplicated (2 entries, 1
    found) entry silently re-opens the hole this guard exists to close."""
    found_by_module: dict[str, Counter[_SiteKey]] = {}
    for path in _package_python_files():
        found_by_module[path.name] = Counter(_numeric_literal_sites(path))

    assert _EXEMPTIONS, "the exemption list is empty -- nothing to check for use"
    for module, allowed in _exemptions_by_module().items():
        found = found_by_module.get(module, Counter())
        for key, count in allowed.items():
            target, site, value = key
            assert count == found[key], (
                f"{module}: target {target!r} site {site!r} value {value!r}: "
                f"{count} exemption entries, {found[key]} literals found -- "
                "a stale or duplicated exemption entry"
            )


def test_a_cited_constant_access_does_not_appear_as_a_literal() -> None:
    """`SEED_CONSTANTS`'s four fields read a `CitedConstant`'s own `.value`
    (an `ast.Attribute` access), never a bare numeric literal -- checked
    directly against the actual source, not only asserted by the equality
    test in `test_sources.py` (which cannot tell a genuine attribute read
    from a literal that happens to match). Tied-value defense:
    `k_fitness` and `k_fatigue` both read a `CitedConstant` whose `.value`
    is `1.0`, so a swap between `K_FITNESS_SEED.value` and
    `K_FATIGUE_SEED.value` would not change either value and would pass an
    equality check unnoticed -- this walk instead pins which module-level
    name (`K_FITNESS_SEED` vs. `K_FATIGUE_SEED`, `TAU_FITNESS_SEED_DAYS` vs.
    `TAU_FATIGUE_SEED_DAYS`) each keyword reads by its own AST `Name.id`.
    Named mutation: swap the two keywords' sources so
    `k_fitness=K_FATIGUE_SEED.value` and `k_fatigue=K_FITNESS_SEED.value` in
    the module under test -- this assertion reds (M10)."""
    expected_names = {
        "tau_fitness_days": "TAU_FITNESS_SEED_DAYS",
        "tau_fatigue_days": "TAU_FATIGUE_SEED_DAYS",
        "k_fitness": "K_FITNESS_SEED",
        "k_fatigue": "K_FATIGUE_SEED",
    }
    package_dir = _package_dir()
    path = package_dir / "sources.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    checked = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ModelConstants"
        ):
            for keyword in node.keywords:
                if keyword.arg in expected_names:
                    checked += 1
                    assert (
                        isinstance(keyword.value, ast.Attribute)
                        and keyword.value.attr == "value"
                    ), (
                        f"SEED_CONSTANTS.{keyword.arg} is not read through "
                        "a '.value' attribute access"
                    )
                    assert isinstance(keyword.value.value, ast.Name), (
                        f"SEED_CONSTANTS.{keyword.arg} does not read a "
                        "module-level CitedConstant's own .value attribute"
                    )
                    assert keyword.value.value.id == expected_names[keyword.arg], (
                        f"SEED_CONSTANTS.{keyword.arg} reads "
                        f"{keyword.value.value.id}.value, not "
                        f"{expected_names[keyword.arg]}.value"
                    )
    assert checked == 4, f"the walk found only {checked} of 4 SEED_CONSTANTS fields"


def test_reference_directory_is_named_nowhere_under_the_history_package() -> None:
    """Package-wide hard rule: no module under `src/fitdocs/history/` names
    the reference-docs tree. Built from two pieces so this assertion is not
    itself a counterexample."""
    forbidden = "docs" + "/reference"
    for path in _package_python_files():
        text = path.read_text(encoding="utf-8")
        assert forbidden not in text, path.name


def test_no_module_under_the_package_names_a_clock_function() -> None:
    """Package-wide hard rule: no module under `src/fitdocs/history/` names
    a clock function -- checked here alongside the other package-wide string
    rules this guard already owns, over the same file list."""
    forbidden_names = ("datetime.now", "time.time", "date.today")
    for path in _package_python_files():
        text = path.read_text(encoding="utf-8")
        for forbidden in forbidden_names:
            assert forbidden not in text, (path.name, forbidden)
