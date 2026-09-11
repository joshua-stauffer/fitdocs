"""The boundary and purity of this feature's four pure modules -- `types.py`,
`sources.py`, `models.py`, `derive.py` (task 5.1; Req 8.3, 9.2, 9.3, 10.1,
10.2, 10.6, 10.7). `fitdocs.performance.engine` is deliberately excluded: it
is impure by design (task 4.1) and is not this module's concern.

**Adopted, not re-derived.** The layer shape below is copied from
`tests/load/channels/test_purity.py` (the original, six-round-hardened
allowlist idiom: import-target-and-name allowlist, module-namespace
allowlist, dynamic-import call scan, an I/O-and-clock denylist, a
builtin-reference allowlist, and a dunder-attribute-and-name allowlist) by
way of the more compact restatement of the first five of those six layers in
`tests/load/threshold/test_boundary.py`, which this module's own layer
functions mirror line-for-line in shape. See both modules' docstrings for
the multi-round history that produced this idiom; it is not re-litigated
here.

**Layer 6 (dunder-attribute-and-name allowlist)** is imported directly from
`tests/load/channels/test_purity.py::_dunder_attribute_violations` rather
than copied, so the two guards cannot silently drift apart -- the same
"adopted, not a second hand-written copy" discipline `test_reachability.py`
already applies to `io_clock_prompt_violations` below. It closes the route
none of layers 1-5 sees at all: a function-scope
`(lambda: None).__globals__["__builtins__"]["__import__"](...)` binds no
module-level name (so layer 2's namespace scan never sees it), is not a
`from`/`import` statement (so layer 1 never sees it), is not a call to a
name in `_DYNAMIC_IMPORT_CALLEES` (so layer 3 never sees it, since
`__import__` here is reached through a dunder-attribute chain, not called
by its own bare name), and never spells `open`/`input`/a clock method (so
layer 4 never sees it) -- confirmed dead against all five prior layers
before this layer existed (`TestDunderAttributeBoundary` below asserts
layers 1, 3, 4 and 5 stay green on that source).

Unlike the channels guard (one flat allowlist for a nine-module package),
this module pins a **separate** allowlist per pure module, because design.md
"Allowed Dependencies" grants each of the four a different, narrower surface
-- `types.py` may not import `sources.py`; `sources.py` may not import
`fitdocs.contract`; only `derive.py` may import all three of its siblings.
Merging them into one flat set would silently admit `types.py` importing
something only `derive.py` is entitled to.

**(1.2 -> 5.1) implementation-notes ruling, applied directly**: an
import-allowlist that filters on `node.level == 0` alone (i.e. "handle level
0, ignore the rest") would silently *admit* a relative import that resolves
to an unsanctioned target, because a level-0-only filter never inspects a
level > 0 node at all. `_import_allowlist_violations` below asserts
`node.level == 0` explicitly for every `ast.ImportFrom` and rejects
anything else outright (see `test_relative_import_is_rejected_outright`) --
never resolves a relative import and checks the resolved name against the
allowlist, which is exactly the shape that ruling warns against.
"""

from __future__ import annotations

import ast
import builtins
import inspect
from pathlib import Path
from types import ModuleType

from fitdocs.performance import derive, models, sources, types
from tests.load.channels.test_purity import _dunder_attribute_violations

_PURE_MODULES: tuple[ModuleType, ...] = (types, sources, models, derive)


def _source_for(module: ModuleType) -> tuple[str, str]:
    path = inspect.getsourcefile(module)
    assert path is not None, f"could not locate source for {module.__name__}"
    return Path(path).read_text(encoding="utf-8"), path


# ---------------------------------------------------------------------------
# Layer 1: import-target-and-name allowlist, one set per pure module
# ---------------------------------------------------------------------------

# Every `from <target> import <name>` each module's own source actually
# contains today (measured directly against this branch's four files, the
# same "measure the real files, do not invent" discipline the channels guard
# documents), matched against design.md's "Allowed Dependencies" section.
# `math` is a bare `import math` in both `models.py` and `derive.py` and has
# no importable "name" of its own -- see `_ALLOWED_BARE_IMPORTS` below.
_ALLOWED_IMPORT_NAMES: dict[str, dict[str, frozenset[str]]] = {
    "fitdocs.performance.types": {
        "__future__": frozenset({"annotations"}),
        "dataclasses": frozenset({"dataclass"}),
        "datetime": frozenset({"date"}),
        "enum": frozenset({"StrEnum"}),
        "fitdocs": frozenset({"Sport"}),
        "fitdocs.benchmarks": frozenset({"BenchmarkKind"}),
        "fitdocs.load.channels.types": frozenset({"InsufficiencyReason"}),
    },
    "fitdocs.performance.sources": {
        "__future__": frozenset({"annotations"}),
        "dataclasses": frozenset({"dataclass"}),
        "typing": frozenset({"Final"}),
        "fitdocs.citation": frozenset(
            {
                "Agreement",
                "Citation",
                "CitedConstant",
                "Corroboration",
                "Departure",
                "FitdocsChoice",
                "VerificationStatus",
            }
        ),
        "fitdocs.performance.types": frozenset({"DerivationMethod"}),
    },
    "fitdocs.performance.models": {
        "__future__": frozenset({"annotations"}),
        "collections.abc": frozenset({"Sequence"}),
        "fitdocs.model": frozenset({"Samples"}),
        "fitdocs.performance": frozenset({"sources"}),
    },
    "fitdocs.performance.derive": {
        "__future__": frozenset({"annotations"}),
        "datetime": frozenset({"date"}),
        "typing": frozenset({"assert_never"}),
        "fitdocs": frozenset({"Sport"}),
        "fitdocs.benchmarks": frozenset({"BenchmarkKind"}),
        "fitdocs.contract": frozenset({"EffortKind", "EffortTag"}),
        "fitdocs.load.channels.sufficiency": frozenset({"evaluate"}),
        "fitdocs.load.channels.types": frozenset(
            {"ChannelId", "ChannelInsufficient", "SufficiencySettings"}
        ),
        "fitdocs.model": frozenset({"Activity"}),
        "fitdocs.performance": frozenset({"models", "sources"}),
        "fitdocs.performance.types": frozenset(
            {
                "DeclineReason",
                "DerivationDeclined",
                "DerivationMethod",
                "DerivationOutcome",
                "DerivedBenchmark",
            }
        ),
    },
}

_ALLOWED_BARE_IMPORTS: dict[str, frozenset[str]] = {
    "fitdocs.performance.types": frozenset(),
    "fitdocs.performance.sources": frozenset(),
    "fitdocs.performance.models": frozenset({"math"}),
    "fitdocs.performance.derive": frozenset({"math"}),
}


def _import_allowlist_violations(
    source: str, *, module_name: str, filename: str = "<test>"
) -> list[str]:
    """Every import-shaped escape from `module_name`'s own sanctioned
    surface. `ast.Import` (`import x`) is rejected outright whenever it is
    dotted -- **not**, as an earlier revision of this docstring claimed, because
    `tests/load/threshold/test_boundary.py` has some general rule that "a
    dotted `import` binds only its root, which is not separately
    allowlisted": that guard admits a whole-module dotted `import` freely for
    any sanctioned target that is not name-restricted (e.g. `import
    fitdocs.model`; see its own `_import_violations`, the `ast.Import` branch,
    which rejects a *sanctioned* dotted target only when `alias.name in
    _ALLOWED_NAMES_BY_TARGET`). The real reason a dotted `import` is rejected
    here is that every target in `_ALLOWED_IMPORT_NAMES` above is
    name-restricted -- each entry allowlists a specific set of importable
    *names* from that target, never the target as a whole -- so a whole-module
    `import` of any dotted target can never respect a restriction that is
    stated over names rather than over the module object. A bare, non-dotted
    `import` is rejected whenever its target is not in
    `_ALLOWED_BARE_IMPORTS[module_name]`.
    `ast.ImportFrom` asserts
    `node.level == 0` explicitly and rejects anything else -- see the module
    docstring's (1.2 -> 5.1) note -- then checks the target against
    `_ALLOWED_IMPORT_NAMES[module_name]` and the imported name(s) against
    that target's own allowlisted set.
    """
    allowed_names = _ALLOWED_IMPORT_NAMES[module_name]
    allowed_bare = _ALLOWED_BARE_IMPORTS[module_name]
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = alias.name
                if "." in target:
                    violations.append(
                        f"L{node.lineno}: import {target} -- dotted `import` "
                        f"binds only its root package"
                    )
                elif target not in allowed_bare:
                    violations.append(
                        f"L{node.lineno}: import {target} not allowlisted"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0:
                violations.append(
                    f"L{node.lineno}: relative import (level {node.level}) -- "
                    f"only level 0 (absolute) imports are ever sanctioned"
                )
                continue
            module = node.module or ""
            names_for_target = allowed_names.get(module)
            if names_for_target is None:
                violations.append(
                    f"L{node.lineno}: from {module} import ... not allowlisted"
                )
                continue
            for alias in node.names:
                if alias.name not in names_for_target:
                    violations.append(
                        f"L{node.lineno}: from {module} import {alias.name} "
                        f"-- name not in that target's own allowlisted set "
                        f"{sorted(names_for_target)}"
                    )
    return violations


class TestImportAllowlist:
    def test_every_pure_module_has_no_import_violation(self) -> None:
        for module in _PURE_MODULES:
            source, path = _source_for(module)
            offenders = _import_allowlist_violations(
                source, module_name=module.__name__, filename=path
            )
            assert offenders == [], f"{module.__name__}: {offenders}"

    def test_scan_is_not_vacuous_and_covers_exactly_four_modules(self) -> None:
        assert [m.__name__ for m in _PURE_MODULES] == [
            "fitdocs.performance.types",
            "fitdocs.performance.sources",
            "fitdocs.performance.models",
            "fitdocs.performance.derive",
        ]
        scanned_imports = 0
        for module in _PURE_MODULES:
            source, _ = _source_for(module)
            tree = ast.parse(source)
            found = sum(
                1
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
            )
            assert found > 0, f"{module.__name__}: the walk found no import at all"
            scanned_imports += found
        assert scanned_imports > 0

    def test_relative_import_is_rejected_outright(self) -> None:
        # (1.2 -> 5.1): a relative import must be caught even though it
        # would, if resolved, land on a sanctioned sibling target.
        offenders = _import_allowlist_violations(
            "from .types import DerivationMethod\n",
            module_name="fitdocs.performance.sources",
        )
        assert offenders != [], "relative import from .types was not caught"
        offenders = _import_allowlist_violations(
            "from . import types\n", module_name="fitdocs.performance.sources"
        )
        assert offenders != [], "relative import `from . import types` was not caught"

    def test_channels_shaped_import_of_this_package_is_caught(self) -> None:
        # Planted violation named by the task brief: a channels-shaped
        # module importing this package as a whole-module alias.
        offenders = _import_allowlist_violations(
            "import fitdocs.performance.types as t\n",
            module_name="fitdocs.performance.derive",
        )
        assert offenders != [], "import fitdocs.performance.types as t was not caught"

    def test_import_of_render_sync_or_cli_is_caught(self) -> None:
        for module_name in (m.__name__ for m in _PURE_MODULES):
            for offending_source in (
                "from fitdocs.render import build_page\n",
                "from fitdocs.sync import run\n",
                "from fitdocs.cli import main\n",
                "from fitdocs.docio import read_frontmatter\n",
                "from fitdocs.layout import OWNED_PATHS\n",
                "from fitdocs.load.profile import load_profile\n",
                "from fitdocs.load.engine import run_pass\n",
            ):
                offenders = _import_allowlist_violations(
                    offending_source, module_name=module_name
                )
                assert offenders != [], (
                    f"{module_name}: {offending_source!r} was not caught"
                )

    def test_sanctioned_imports_are_not_flagged(self) -> None:
        # Negative control: every module's real, current source must pass
        # its own allowlist cleanly (already exercised above, restated here
        # against a hand-written snippet so this is not the same assertion
        # twice under a different name).
        offenders = _import_allowlist_violations(
            "from fitdocs.performance import models, sources\n",
            module_name="fitdocs.performance.derive",
        )
        assert offenders == []
        offenders = _import_allowlist_violations(
            "import math\n", module_name="fitdocs.performance.models"
        )
        assert offenders == []

    def test_bare_import_of_this_package_sibling_is_still_dotted_and_rejected(
        self,
    ) -> None:
        offenders = _import_allowlist_violations(
            "import fitdocs.performance.sources\n",
            module_name="fitdocs.performance.derive",
        )
        assert offenders != [], (
            "a bare dotted `import fitdocs.performance.sources` was not caught "
            "-- only the sanctioned `from fitdocs.performance import sources` "
            "form is allowed"
        )

    def test_every_allowlist_entry_is_a_measured_import(self) -> None:
        """`_ALLOWED_IMPORT_NAMES`/`_ALLOWED_BARE_IMPORTS` must equal, not
        merely be a superset of, each pure module's real, current
        level-0 imports -- an allowlist that pins a superset can be widened
        (e.g. adding an unused
        `"fitdocs.load.settings": frozenset({"load_load_settings"})` entry to
        `_ALLOWED_IMPORT_NAMES["fitdocs.performance.types"]`) and the
        `test_every_pure_module_has_no_import_violation` scan above stays
        green regardless, since that scan only ever rejects what the source
        does not use -- it never rejects an allowlist entry the source
        itself never reaches for. This test parses each module's own source
        fresh and asserts equality against the measured surface, so a
        widened allowlist is caught even though nothing in the source
        changed.
        """
        for module in _PURE_MODULES:
            source, _ = _source_for(module)
            tree = ast.parse(source)
            measured_from: dict[str, set[str]] = {}
            measured_bare: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 0:
                    target = node.module or ""
                    measured_from.setdefault(target, set()).update(
                        alias.name for alias in node.names
                    )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if "." not in alias.name:
                            measured_bare.add(alias.name)
            measured_from_frozen = {
                target: frozenset(names) for target, names in measured_from.items()
            }
            assert measured_from_frozen == _ALLOWED_IMPORT_NAMES[module.__name__], (
                f"{module.__name__}: allowlist entries not equal to the "
                f"module's own measured `from ... import ...` surface"
            )
            assert frozenset(measured_bare) == _ALLOWED_BARE_IMPORTS[module.__name__], (
                f"{module.__name__}: allowlist bare-import entries not equal "
                f"to the module's own measured `import ...` surface"
            )


# ---------------------------------------------------------------------------
# Layer 2: module-namespace allowlist
# ---------------------------------------------------------------------------


def _sanctioned_namespace_owners(module_name: str) -> frozenset[str]:
    return frozenset(_ALLOWED_IMPORT_NAMES[module_name].keys()) | {"builtins"}


_NAMESPACE_OWNER_REDIRECTS: dict[str, frozenset[str]] = {
    # `fitdocs`'s own top-level `__init__.py` lazily re-exports several
    # names (`Sport`, `Activity`, `Samples`, ...) that are actually *defined*
    # in `fitdocs.model` -- `Sport.__module__` reports the defining module,
    # not the package the sanctioned import statement names. Measured, not
    # assumed: `fitdocs.Sport.__module__ == "fitdocs.model"`.
    "fitdocs": frozenset({"fitdocs.model"}),
}


def _namespace_violations(module: ModuleType) -> list[tuple[str, str]]:
    allowed_owners = _sanctioned_namespace_owners(module.__name__)
    # Bare "fitdocs" is deliberately excluded from the *prefix* allowance
    # below: every sanctioned fitdocs.* owner must appear explicitly, either
    # as its own key in `_ALLOWED_IMPORT_NAMES` or via
    # `_NAMESPACE_OWNER_REDIRECTS`, so a bare top-level match can never
    # substitute for an unsanctioned fitdocs.* owner the way it could for a
    # genuine stdlib module -- mirrors
    # `tests/load/threshold/test_boundary.py`'s own exclusion of bare
    # `fitdocs` from its `allowed_top_levels` set. It remains in
    # `allowed_owners` itself (the exact-match set) so `owner == "fitdocs"`
    # and the `_NAMESPACE_OWNER_REDIRECTS` gate below (keyed on membership in
    # `allowed_owners`) still work.
    prefix_allowed_owners = allowed_owners - {"fitdocs"}
    offenders: list[tuple[str, str]] = []
    for name, value in vars(module).items():
        if name.startswith("__"):
            continue
        # Restricted to imported classes/functions/modules -- the shapes an
        # import statement actually binds. A module-level type alias built
        # from a `|` union (e.g. `DerivationOutcome = A | B`) produces a
        # `types.UnionType` *instance*, whose own `__module__` names the
        # stdlib `types` module that defines that instance's class, not the
        # module that defines the alias -- an unrelated quirk this layer
        # must not mistake for an unsanctioned import of the stdlib `types`
        # module. Such names are not imports at all, so they are outside
        # this layer's own stated scope (an imported name), not a gap in it.
        if not (
            inspect.isclass(value)
            or inspect.isfunction(value)
            or inspect.ismodule(value)
        ):
            continue
        owner = (
            value.__name__
            if inspect.ismodule(value)
            else getattr(value, "__module__", None)
        )
        if owner is None:
            continue
        if owner == module.__name__:
            continue
        if owner in allowed_owners:
            continue
        # A `from fitdocs.performance import sources` binds a *submodule*
        # object whose own `__name__` is `fitdocs.performance.sources`, not
        # the sanctioned target key `fitdocs.performance` the import
        # statement itself names -- allow any submodule of a sanctioned
        # package target, the same submodule allowance
        # `tests/load/threshold/test_boundary.py`'s own namespace layer
        # grants for its sibling-package target.
        if any(owner.startswith(f"{allowed}.") for allowed in prefix_allowed_owners):
            continue
        if any(
            owner in redirects
            for key, redirects in _NAMESPACE_OWNER_REDIRECTS.items()
            if key in allowed_owners
        ):
            continue
        top_level = owner.split(".")[0]
        if top_level in {
            "__future__",
            "dataclasses",
            "datetime",
            "enum",
            "typing",
            "math",
        }:
            continue
        offenders.append((name, owner))
    return offenders


class TestNamespaceBoundary:
    def test_every_pure_module_namespace_is_clean(self) -> None:
        for module in _PURE_MODULES:
            offenders = _namespace_violations(module)
            assert offenders == [], f"{module.__name__}: {offenders}"


# ---------------------------------------------------------------------------
# Layer 3: dynamic-import call scan
# ---------------------------------------------------------------------------

_DYNAMIC_IMPORT_CALLEES: frozenset[str] = frozenset(
    {"__import__", "import_module", "exec", "eval"}
)


def _dynamic_import_violations(source: str, *, filename: str = "<test>") -> list[str]:
    tree = ast.parse(source, filename=filename)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in _DYNAMIC_IMPORT_CALLEES:
            offenders.append(f"L{node.lineno}: {func.id}(...) call")
        elif isinstance(func, ast.Attribute) and func.attr == "import_module":
            offenders.append(f"L{node.lineno}: ...import_module(...) call")
    return offenders


class TestDynamicImportBoundary:
    def test_every_pure_module_has_no_dynamic_import_call(self) -> None:
        for module in _PURE_MODULES:
            source, path = _source_for(module)
            offenders = _dynamic_import_violations(source, filename=path)
            assert offenders == [], f"{module.__name__}: {offenders}"

    def test_dunder_import_call_is_caught(self) -> None:
        offenders = _dynamic_import_violations('__import__("fitdocs.render")\n')
        assert offenders != []

    def test_importlib_import_module_call_is_caught(self) -> None:
        offenders = _dynamic_import_violations(
            'import importlib\nimportlib.import_module("fitdocs.render")\n'
        )
        assert offenders != []


# ---------------------------------------------------------------------------
# Layer 4: I/O-and-clock denylist
# ---------------------------------------------------------------------------

_FORBIDDEN_BARE_CALLS: frozenset[str] = frozenset({"open", "input"})
_FORBIDDEN_METHOD_NAMES: frozenset[str] = frozenset(
    {
        "today",
        "now",
        "utcnow",
        "fromtimestamp",
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
        "open",
        "sleep",
        "connect",
        "recv",
        "send",
    }
)
_FORBIDDEN_IO_MODULES: frozenset[str] = frozenset(
    {
        "pathlib",
        "os",
        "io",
        "socket",
        "ssl",
        "http",
        "urllib",
        "urllib3",
        "requests",
        "httpx",
        "time",
        "random",
        "subprocess",
        "tempfile",
        "shutil",
        "glob",
        "getpass",
    }
)


def io_clock_prompt_violations(source: str, *, filename: str = "<test>") -> list[str]:
    """Every reference in `source` to a filesystem, network, process, clock,
    or prompting interface. Shared -- deliberately, not by accident -- with
    `test_reachability.py`, which imports this exact function to prove "the
    same scan" establishes the pure modules reach none of these interfaces
    (task 5.1's own wording), rather than a second, independently-written
    copy that could silently drift from this one.
    """
    tree = ast.parse(source, filename=filename)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _FORBIDDEN_IO_MODULES:
                    offenders.append(f"L{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in _FORBIDDEN_IO_MODULES:
                offenders.append(f"L{node.lineno}: from {node.module} import ...")
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_METHOD_NAMES:
            offenders.append(f"L{node.lineno}: .{node.attr} reference")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _FORBIDDEN_BARE_CALLS
        ):
            offenders.append(f"L{node.lineno}: {node.func.id}(...) call")
    return offenders


class TestNoFilesystemNetworkClockOrPromptReference:
    def test_every_pure_module_has_no_forbidden_reference(self) -> None:
        for module in _PURE_MODULES:
            source, path = _source_for(module)
            offenders = io_clock_prompt_violations(source, filename=path)
            assert offenders == [], f"{module.__name__}: {offenders}"

    def test_open_call_is_caught(self) -> None:
        offenders = io_clock_prompt_violations("open('x')\n")
        assert offenders != []

    def test_clock_attribute_access_is_caught(self) -> None:
        offenders = io_clock_prompt_violations(
            "from datetime import date\ndate.today()\n"
        )
        assert offenders != []

    def test_pathlib_import_is_caught(self) -> None:
        offenders = io_clock_prompt_violations("import pathlib\n")
        assert offenders != []

    def test_ordinary_datetime_field_use_is_not_flagged(self) -> None:
        # Negative control: `Benchmark.measured_on: date` and ordinary
        # non-clock attribute access on a `date` field must not be flagged.
        offenders = io_clock_prompt_violations(
            "from datetime import date\nmeasured_on: date\nx = measured_on.year\n"
        )
        assert offenders == []


# ---------------------------------------------------------------------------
# Layer 5: builtin-reference allowlist
# ---------------------------------------------------------------------------

_ALLOWED_BUILTINS: frozenset[str] = frozenset(
    {
        "AssertionError",
        "ValueError",
        "abs",
        "bool",
        "classmethod",
        "dict",
        "float",
        "frozenset",
        "int",
        "isinstance",
        "len",
        "list",
        "max",
        "min",
        "next",
        "range",
        "str",
        "sum",
        "tuple",
    }
)
_ALLOWED_BUILTIN_SHADOWS: frozenset[str] = frozenset()


def _locally_bound_names(tree: ast.AST) -> set[str]:
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
    return bound


def _builtin_shadow_violations(tree: ast.AST) -> list[str]:
    builtin_names = frozenset(dir(builtins))
    violations: list[str] = []
    for node in ast.walk(tree):
        name: str | None = None
        lineno = getattr(node, "lineno", 0)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound_name = alias.asname or alias.name.split(".")[0]
                if (
                    bound_name in builtin_names
                    and bound_name not in _ALLOWED_BUILTIN_SHADOWS
                ):
                    violations.append(
                        f"L{node.lineno}: import binds builtin-spelled "
                        f"name `{bound_name}`"
                    )
            continue
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            name = node.id
        elif isinstance(node, ast.arg):
            name = node.arg
        if (
            name is not None
            and name in builtin_names
            and name not in _ALLOWED_BUILTIN_SHADOWS
        ):
            violations.append(f"L{lineno}: local binding shadows builtin `{name}`")
    return violations


def _builtin_allowlist_violations(
    source: str, *, filename: str = "<test>"
) -> list[str]:
    tree = ast.parse(source, filename=filename)
    bound = _locally_bound_names(tree)
    builtin_names = frozenset(dir(builtins))
    violations: list[str] = list(_builtin_shadow_violations(tree))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in builtin_names
            and node.id not in bound
            and node.id not in _ALLOWED_BUILTINS
        ):
            violations.append(f"L{node.lineno}: builtin `{node.id}` not allowlisted")
        elif (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == "__builtins__"
        ) or (isinstance(node, ast.Attribute) and node.attr == "__builtins__"):
            violations.append(f"L{node.lineno}: `__builtins__` referenced directly")
    return violations


class TestBuiltinReferenceBoundary:
    def test_every_pure_module_has_no_unsanctioned_builtin_reference(self) -> None:
        for module in _PURE_MODULES:
            source, path = _source_for(module)
            offenders = _builtin_allowlist_violations(source, filename=path)
            assert offenders == [], f"{module.__name__}: {offenders}"

    def test_aliased_dunder_import_is_caught(self) -> None:
        offenders = _builtin_allowlist_violations(
            '_i = __import__\n_i("fitdocs.render")\n'
        )
        assert offenders != []

    def test_aliased_open_at_function_scope_is_caught(self) -> None:
        offenders = _builtin_allowlist_violations(
            'def f():\n    _o = open\n    _o("x")\n'
        )
        assert offenders != []

    def test_parameter_named_open_is_a_shadow_violation(self) -> None:
        offenders = _builtin_allowlist_violations("def f(open):\n    return open\n")
        assert offenders != []

    def test_ordinary_sanctioned_builtins_are_not_flagged(self) -> None:
        snippet = (
            "def f(x):\n"
            "    if isinstance(x, (int, float)):\n"
            "        return bool(len([x]))\n"
            "    return frozenset(tuple({1, 2}))\n"
        )
        offenders = _builtin_allowlist_violations(snippet)
        assert offenders == []


# ---------------------------------------------------------------------------
# Layer 6: dunder-attribute-and-name allowlist (round-3 remediation)
# ---------------------------------------------------------------------------
#
# `_dunder_attribute_violations` is imported, not copied, from
# `tests/load/channels/test_purity.py` -- see that function's own docstring
# for the full two-round history (round 5's attribute rule, round 6's
# bare-name fix) that produced it. It closes a route none of layers 1-5
# above sees: a function-scope
# `(lambda: None).__globals__["__builtins__"]["__import__"](...)` binds no
# module-level name, so layer 2 (`_namespace_violations`, which only walks
# `vars(module)`) never sees it; it is neither an `ast.Import` nor an
# `ast.ImportFrom`, so layer 1 never sees it; the callee is an
# `ast.Attribute` (`... .__import__`), never a bare `ast.Name` matching
# `_DYNAMIC_IMPORT_CALLEES`, so layer 3 never sees it; and it names no
# filesystem, network, clock or prompt interface, so layer 4 never sees it
# either.


class TestDunderAttributeBoundary:
    def test_every_pure_module_has_no_dunder_attribute_violation(self) -> None:
        for module in _PURE_MODULES:
            source, path = _source_for(module)
            offenders = _dunder_attribute_violations(source, filename=path)
            assert offenders == [], f"{module.__name__}: {offenders}"

    def test_globals_builtins_import_route_is_caught(self) -> None:
        # The exact escape named by the round-3 remediation: appending this
        # to a pure module leaves every prior layer green (see the module
        # docstring's Layer 6 note) because no module-level name is ever
        # bound and no forbidden call, method or filesystem/network/clock
        # token is ever spelled.
        offending_source = (
            "def _mut():\n"
            '    return (lambda: None).__globals__["__builtins__"]'
            '["__import__"]("fitdocs.render", fromlist=["build_page"])\n'
        )
        offenders = _dunder_attribute_violations(offending_source)
        assert offenders != [], (
            "the __globals__/__builtins__/__import__ attribute-chain route "
            "was not caught"
        )
        # Confirm the escape really is invisible to every prior layer,
        # rather than merely asserting it in prose: none of layers 1, 3,
        # 4 and 5 flags this same source (layer 2 needs a live module
        # namespace, which a source string does not have).
        assert (
            _import_allowlist_violations(
                offending_source, module_name="fitdocs.performance.derive"
            )
            == []
        )
        assert _dynamic_import_violations(offending_source) == []
        assert io_clock_prompt_violations(offending_source) == []
        assert _builtin_allowlist_violations(offending_source) == []

    def test_bare_builtins_subscript_route_is_caught(self) -> None:
        # The bare-name half of the same rule: `__builtins__` referenced
        # directly (no `.` in the expression at all) as a plain module
        # global, subscripted rather than attribute-accessed.
        offending_source = '_b = __builtins__["__import__"]\n_b("fitdocs.render")\n'
        offenders = _dunder_attribute_violations(offending_source)
        assert offenders != [], "bare `__builtins__` subscript was not caught"

    def test_ordinary_non_dunder_source_is_not_flagged(self) -> None:
        # Negative control: an ordinary module using only sanctioned names
        # must not be flagged by this layer.
        offenders = _dunder_attribute_violations(
            "from datetime import date\nmeasured_on: date\nx = measured_on.year\n"
        )
        assert offenders == []
