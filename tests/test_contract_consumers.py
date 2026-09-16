"""Anti-drift guard: converted consumers read documents only through the contract.

:mod:`fitdocs.contract` exists so that a document one command recognizes is never
invisible to, or differently understood by, another (Req 1.1, 1.2). That
guarantee is only as strong as the *absence* of second opinions: the moment a
consumer reintroduces its own ``---`` fence test, its own ``yaml.safe_load``, or
its own ``sources`` reader, the two interpretations can drift apart without a
single behavioral test failing -- both copies work, they simply stop agreeing at
some edge.

Behavioral tests cannot catch that, because a faithful duplicate *passes* them.
So this module asserts a structural property instead, over a registry of the
modules that have been converted:

* the module imports no YAML parser and names no ``yaml`` symbol -- frontmatter
  parsing happens in exactly one place in the package;
* the module spells no document vocabulary of its own -- no bare ``---`` fence
  and no bare ``"workout"`` type literal;
* the private duplicate readers it used to carry are gone by name, so a revert
  that restores one fails here rather than silently shadowing the contract;
* the reader, region-id, and key-set names the module binds are the contract's
  *same objects*, not same-named copies.

:data:`CONVERTED_MODULES` is the registry of converted modules and
:data:`CONTRACT_BINDINGS` records what each one must bind by identity. Converting
a further consumer is an append to both, not a rewrite of the assertions below --
and :func:`test_every_converted_module_declares_its_contract_bindings` fails if
someone appends to only one of them.

Two package-wide scans close the same gap from the other direction: one asserts
that the session-UUID format has exactly one implementation anywhere in
:mod:`fitdocs`, and one that no module in the render layer spells a region id for
itself (Req 1.4). Both are source scans over files rather than over the registry,
so a *new* module that reintroduces either duplicate is caught without anyone
remembering to register it.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import ModuleType
from typing import Final

import pytest

import fitdocs
import fitdocs.audit
import fitdocs.cli
import fitdocs.contract
import fitdocs.declaration
import fitdocs.docio
import fitdocs.history.documents
import fitdocs.history.page
import fitdocs.layout
import fitdocs.load.docedit
import fitdocs.load.engine
import fitdocs.performance.derive
import fitdocs.performance.engine
import fitdocs.plans.engine
import fitdocs.plans.page
import fitdocs.render.frontmatter
import fitdocs.render.sections
import fitdocs.render.views
import fitdocs.sync

#: Every module whose document reading has been converted onto the contract.
#: ``sync`` was the first; the load engine and the load document editor are the
#: second wave; the render layer and the layout leaf are the third; this
#: feature's own new modules -- the shared read (``docio``), the ownership
#: declaration (``declaration``), the read-only audit (``audit``), and the CLI
#: shell (``cli``) -- are the fourth. Omitting a module this feature itself
#: added would leave exactly the surface most likely to grow a second
#: interpretation unguarded (proven: injecting ``_fence = "---"``,
#: ``_type = "workout"``, ``_region = "notes"`` into ``audit.py`` passed the
#: full suite before this wave was registered). A fifth wave, this feature's
#: own two modules (``performance/engine``, the impure pass, and
#: ``performance/derive``, the pure leaf that reads the tag vocabulary the
#: contract publishes), is registered below for the identical reason: a
#: faithful local re-implementation of a bound reader -- a copy of
#: ``is_workout_document`` appended to ``performance/engine.py`` using the
#: contract's own key constants -- passed every test outside this file and
#: failed only the identity binding here.
CONVERTED_MODULES: Final[tuple[ModuleType, ...]] = (
    fitdocs.sync,
    fitdocs.load.engine,
    fitdocs.load.docedit,
    fitdocs.render.frontmatter,
    fitdocs.render.views,
    fitdocs.render.sections,
    fitdocs.layout,
    fitdocs.docio,
    fitdocs.declaration,
    fitdocs.audit,
    fitdocs.cli,
    # load-history (task 5.4): the package's one filesystem read
    # (`documents.py`, binding the load keys, the date reader, the
    # effort-tag reader and the workout-document test by identity) and the
    # page module (`page.py`), which also imports `fitdocs.contract` -- the
    # design's "only importer" sentence names `documents.py` alone, but
    # `page.py` reaches the same shared vocabulary (`TYPE_KEY`,
    # `GENERATOR_KEY`, `GENERATOR`, `FRONTMATTER_FENCE`, `DOC_BANNER`,
    # `EffortKind`) through the qualified `contract.NAME` form rather than a
    # from-import, so it binds no name directly on its own module namespace
    # and its `CONTRACT_BINDINGS` entry is empty -- it is registered so the
    # structural checks (no YAML, no bare fence/workout literal, no private
    # duplicate reader) apply to it, the same reason `cli.py` above is
    # registered with an empty binding list.
    fitdocs.history.documents,
    fitdocs.history.page,
    fitdocs.performance.engine,
    fitdocs.performance.derive,
    # training-blocks (task 4.4): the two modules the plan's hard rule
    # names as this package's only importers of `fitdocs.contract` --
    # `page.py` (binding the seven names it from-imports) and `engine.py`
    # (binding the generated-marker predicate). Registered so the same
    # structural checks (no YAML, no bare fence/workout literal, no
    # private duplicate reader) apply here too; the import-closure pin in
    # `tests/plans/test_boundary.py::TestContractImporters` is what keeps
    # this registration at exactly two -- a third module importing the
    # contract reds that test before it could slip past this registry
    # unregistered.
    fitdocs.plans.page,
    fitdocs.plans.engine,
)

#: The one converted module allowed to name ``yaml`` at all. The frontmatter
#: builder is the package's sole YAML *emitter* -- it serializes the managed
#: block with a single ``safe_dump`` -- and emission is not a second opinion
#: about what a document says. It is still forbidden from *reading* YAML: a
#: loader here would be exactly the duplicate interpretation this file exists to
#: prevent, so the emitter is held to a stricter check than a blanket ban.
YAML_EMITTERS: Final[frozenset[str]] = frozenset({"fitdocs.render.frontmatter"})

#: The only ``yaml`` attributes a :data:`YAML_EMITTERS` module may reach for.
_YAML_EMISSION_ATTRS: Final[frozenset[str]] = frozenset({"safe_dump"})

#: Private helper names a converted module must no longer define. Each was a
#: local duplicate of a contract reader or constant; a revert that restores one
#: is a second interpretation of the document format and fails here.
FORBIDDEN_LOCAL_NAMES: Final[tuple[str, ...]] = (
    "_FENCE",
    "_FRONTMATTER_FENCE",
    "_LOAD_REGION_ID",
    "_NOTES_PLACEHOLDER",
    "_UUID_BYTE_COUNT",
    "_WORKOUT_PLACEHOLDER",
    "_WORKOUT_TYPE",
    "_format_session_uuid",
    "_frontmatter_close_index",
    "_parse_frontmatter",
    "_session_uuid",
    "_sha_of_ref",
    "_sources",
)

#: Per converted module, the contract names it must bind *by identity*. Each
#: entry is the set of readers, ids, and constants that module took from the
#: contract; the assertion is ``is``, not ``==``, because a same-named local
#: re-implementation satisfies every behavioral test and every import-shaped
#: check, and only object identity rules it out.
CONTRACT_BINDINGS: Final[dict[str, tuple[str, ...]]] = {
    "fitdocs.sync": (
        "document_uuid",
        "effort_tag",
        "is_workout_document",
        "parse_frontmatter",
        "sha_of_ref",
        "source_refs",
        "unmanaged_keys",
        "user_owned_lines",
    ),
    "fitdocs.load.engine": (
        "is_workout_document",
        "parse_frontmatter",
        "sha_of_ref",
        "source_refs",
    ),
    "fitdocs.load.docedit": (
        "LOAD_KEYS",
        "LOAD_NOT_COMPUTED",
        "LOAD_REGION",
        "frontmatter_close_index",
        "parse_frontmatter",
    ),
    "fitdocs.render.frontmatter": (
        "DOC_VERSION",
        "DOC_VERSION_KEY",
        "FRONTMATTER_FENCE",
        "SOURCES_KEY",
        "TYPE_KEY",
        "UUID_KEY",
        "WORKOUT_TYPE",
        "format_session_uuid",
    ),
    "fitdocs.render.views": (
        "NOTES_PLACEHOLDER",
        "WORKOUT_PLACEHOLDER",
        "WORKOUT_REGION",
        "region_block",
    ),
    "fitdocs.render.sections": (
        "LOAD_NOT_COMPUTED",
        "LOAD_REGION",
        "NOTES_REGION",
        "region_block",
    ),
    "fitdocs.layout": ("format_session_uuid",),
    "fitdocs.docio": ("parse_frontmatter",),
    "fitdocs.declaration": (
        "CONTRACT_VERSION",
        "EFFORT_KEYS",
        "GENERATED_PREFIX",
        "GENERATOR",
        "USER_REGIONS",
        "is_generated",
    ),
    "fitdocs.audit": (
        "DOC_VERSION",
        "document_version",
        "effort_tag",
        "is_workout_document",
        "parse_frontmatter",
        "unmanaged_keys",
    ),
    # `cli.py` binds no contract name directly -- it delegates document
    # interpretation entirely to `audit`, `declaration`, and `sync`. It is
    # still registered above so a future direct contract literal or duplicate
    # reader added to the CLI is caught the moment it appears.
    "fitdocs.cli": (),
    "fitdocs.history.documents": (
        "LOAD_KEYS",
        "document_date",
        "effort_tag",
        "is_workout_document",
    ),
    # `page.py` binds no contract name directly (see the CONVERTED_MODULES
    # comment above) -- registered for the structural checks only, the same
    # shape as `fitdocs.cli`.
    "fitdocs.history.page": (),
    "fitdocs.performance.engine": (
        "EffortTag",
        "InvalidEffortTag",
        "document_date",
        "effort_tag",
        "is_workout_document",
        "sha_of_ref",
        "source_refs",
    ),
    "fitdocs.performance.derive": (
        "EffortKind",
        "EffortTag",
    ),
    "fitdocs.plans.page": (
        "DOC_BANNER",
        "FRONTMATTER_FENCE",
        "GENERATOR",
        "GENERATOR_KEY",
        "TYPE_KEY",
        "NOTES_REGION",
        "NOTES_PLACEHOLDER",
    ),
    "fitdocs.plans.engine": ("is_generated",),
}

#: Document vocabulary no converted module may spell for itself: the frontmatter
#: fence and the workout-type marker both have exactly one definition, in the
#: contract.
FORBIDDEN_LITERALS: Final[tuple[str, ...]] = (
    fitdocs.contract.FRONTMATTER_FENCE,
    fitdocs.contract.WORKOUT_TYPE,
)

_MODULE_IDS: Final[tuple[str, ...]] = tuple(
    module.__name__ for module in CONVERTED_MODULES
)


def _module_ast(module: ModuleType) -> ast.Module:
    """The module's own source, parsed -- the only thing a structural test can read."""
    return ast.parse(inspect.getsource(module))


@pytest.mark.parametrize("module", CONVERTED_MODULES, ids=_MODULE_IDS)
def test_converted_module_parses_no_yaml_of_its_own(module: ModuleType) -> None:
    """A converted consumer imports no YAML parser and names no ``yaml`` symbol.

    Frontmatter parsing lives in :func:`fitdocs.contract.parse_frontmatter` and
    nowhere else, so ``yaml`` is reachable from exactly one module in the
    package. Any ``import yaml``, ``from yaml import ...``, or bare ``yaml.``
    reference in a converted module is a second parser in the making.

    A :data:`YAML_EMITTERS` module is the one exception, and a narrower rule
    rather than a waiver: the frontmatter builder *writes* the managed block, so
    it may name ``yaml`` -- but only to serialize, and only under that name. The
    rule has two halves, and both are enforced here:

    * *how it reaches YAML* -- a plain ``import yaml`` and nothing else. An alias
      (``import yaml as _y``) or a member import (``from yaml import safe_load``)
      binds the library to a name the attribute scan below cannot see, so the
      emission check would pass over a loader without ever looking at it.
    * *what it reaches for* -- every ``yaml`` attribute it touches must be in
      :data:`_YAML_EMISSION_ATTRS`, i.e. ``safe_dump`` alone. Reaching for
      ``safe_load`` (or any other loader) is the duplicate interpretation this
      file exists to prevent, and fails just as loudly here as the blanket ban
      fails elsewhere.

    Mutation caught: reintroducing a local ``_parse_frontmatter`` that calls
    ``yaml.safe_load`` -- which would pass every behavioral test in the suite --
    and the same loader smuggled in under ``from yaml import safe_load`` or
    ``import yaml as _y``.
    """
    tree = _module_ast(module)
    if module.__name__ in YAML_EMITTERS:
        unqualified: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                unqualified += [
                    f"import {alias.name} as {alias.asname}"
                    for alias in node.names
                    if alias.name.split(".")[0] == "yaml" and alias.asname is not None
                ]
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.split(".")[0] == "yaml"
            ):
                unqualified += [
                    f"from {node.module} import {alias.name}" for alias in node.names
                ]
        assert not unqualified, (
            f"{module.__name__} reaches YAML by an unqualified name ({unqualified}); "
            "the emitter must use a plain `import yaml`, so that every attribute it "
            "touches is visible to the emission check"
        )
        loaders = sorted(
            {
                node.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "yaml"
                and node.attr not in _YAML_EMISSION_ATTRS
            }
        )
        assert not loaders, (
            f"{module.__name__} reads YAML ({loaders}); the emitter may only "
            f"serialize ({sorted(_YAML_EMISSION_ATTRS)}) -- reading a document "
            "belongs to fitdocs.contract.parse_frontmatter"
        )
        return
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [
                alias.name for alias in node.names if alias.name.split(".")[0] == "yaml"
            ]
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.module.split(".")[0] == "yaml":
                offenders.append(node.module)
        elif isinstance(node, ast.Name) and node.id == "yaml":
            offenders.append(node.id)
    assert not offenders, (
        f"{module.__name__} references YAML directly ({sorted(set(offenders))}); "
        "frontmatter parsing belongs to fitdocs.contract.parse_frontmatter"
    )


@pytest.mark.parametrize("module", CONVERTED_MODULES, ids=_MODULE_IDS)
def test_converted_module_spells_no_document_vocabulary_of_its_own(
    module: ModuleType,
) -> None:
    """The fence and the workout-type marker appear as literals only in the contract.

    A converted consumer compares against :data:`fitdocs.contract.WORKOUT_TYPE`
    and :data:`fitdocs.contract.FRONTMATTER_FENCE`; re-spelling either as a bare
    string is how one command's idea of "is this a fitdocs document?" drifts from
    another's (Req 1.1).
    """
    tree = _module_ast(module)
    spelled = sorted(
        {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in FORBIDDEN_LITERALS
        }
    )
    assert not spelled, (
        f"{module.__name__} spells document vocabulary itself ({spelled}); "
        "import the constant from fitdocs.contract instead"
    )


@pytest.mark.parametrize("module", CONVERTED_MODULES, ids=_MODULE_IDS)
def test_converted_module_defines_no_duplicate_readers(module: ModuleType) -> None:
    """None of the retired private duplicates is defined or bound any more.

    Checks the module namespace rather than only the source, so a duplicate
    resurrected by any route -- a redefinition, a re-import from a sibling -- is
    caught.
    """
    resurrected = [name for name in FORBIDDEN_LOCAL_NAMES if hasattr(module, name)]
    assert not resurrected, (
        f"{module.__name__} still defines {resurrected}; "
        "the contract's readers are the single definition"
    )


@pytest.mark.parametrize("module", CONVERTED_MODULES, ids=_MODULE_IDS)
def test_converted_module_binds_the_contract_definitions_themselves(
    module: ModuleType,
) -> None:
    """A converted module's readers *are* the contract's objects, not copies.

    Identity, not equality: a local re-implementation with the same name would
    satisfy every behavioral test and every import-shaped check, and only an
    ``is`` comparison against :mod:`fitdocs.contract` rules it out (Req 1.1-1.4).
    Applies to constants as well as functions -- ``LOAD_REGION`` and
    ``LOAD_KEYS`` re-spelled locally would drift from the published region and
    managed-key policy exactly as a duplicated parser would (Req 1.4, 6.2).
    """
    for name in CONTRACT_BINDINGS[module.__name__]:
        assert hasattr(module, name), f"{module.__name__} does not use contract.{name}"
        assert getattr(module, name) is getattr(fitdocs.contract, name), (
            f"{module.__name__}.{name} is not fitdocs.contract.{name}"
        )


def test_every_converted_module_declares_its_contract_bindings() -> None:
    """The binding registry covers exactly the converted modules -- no silent gaps.

    Converting a consumer without listing what it binds would leave the identity
    check above vacuously green for that module, which is the one failure mode
    this whole file exists to prevent.
    """
    assert set(CONTRACT_BINDINGS) == set(_MODULE_IDS)


# --------------------------------------------------------------------------- #
# Package-wide scans: duplicates that no registry entry would notice
# --------------------------------------------------------------------------- #

_PACKAGE_ROOT: Final[Path] = Path(fitdocs.__file__).resolve().parent


def _package_sources(subdir: str = "") -> dict[str, ast.Module]:
    """Every ``.py`` file under the installed package, parsed, keyed by rel path.

    A *file* scan, not an import-and-inspect: it sees modules nobody registered
    and modules nobody imports, which is precisely the blind spot the registries
    above have.
    """
    root = _PACKAGE_ROOT / subdir if subdir else _PACKAGE_ROOT
    return {
        str(path.relative_to(_PACKAGE_ROOT).as_posix()): ast.parse(
            path.read_text(encoding="utf-8")
        )
        for path in sorted(root.rglob("*.py"))
    }


def test_the_session_uuid_format_has_exactly_one_implementation() -> None:
    """Only :mod:`fitdocs.contract` implements the recorded session identity.

    The identity a document records under ``uuid`` decides which document a
    re-export converges onto, and it was formatted in three places -- the
    frontmatter builder, the layout's ``activity_uid``, and the contract. Three
    faithful copies pass every behavioral test and disagree only at an edge (a
    16-element ``list`` rather than a ``tuple``, say), at which point one command
    writes an identity another cannot match (Req 1.1).

    The proxy is the ``uuid`` module itself: it exists in this package for
    exactly one purpose, so "which files name ``uuid``?" answers "how many
    implementations are there?" without pattern-matching on function bodies.
    """
    naming_uuid = sorted(
        rel
        for rel, tree in _package_sources().items()
        if any(
            (isinstance(node, ast.Import) and any(a.name == "uuid" for a in node.names))
            or (isinstance(node, ast.ImportFrom) and node.module == "uuid")
            or (isinstance(node, ast.Name) and node.id == "uuid")
            for node in ast.walk(tree)
        )
    )
    assert naming_uuid == ["contract.py"], (
        f"the session-UUID format is implemented in {naming_uuid}; "
        "fitdocs.contract.format_session_uuid is the single implementation"
    )


def test_the_render_layer_spells_no_region_id() -> None:
    """No module under ``fitdocs/render`` carries a region id as a bare literal.

    One region-ownership policy means one *spelling* of each region id (Req 1.4):
    the renderer that emits a region, the merge that preserves it, and the load
    pass that fills it must all name the same constant. A literal ``"load"`` or
    ``"notes"`` in a ``region_block`` call is how a renamed region silently stops
    being preserved -- the document still renders, and only the merge quietly
    drops the user's content.
    """
    offenders = {
        rel: sorted(
            {
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in fitdocs.contract.PRESERVED_REGIONS
            }
        )
        for rel, tree in _package_sources("render").items()
    }
    spelled = {rel: found for rel, found in offenders.items() if found}
    assert not spelled, (
        f"the render layer spells region ids itself ({spelled}); "
        "import NOTES_REGION / WORKOUT_REGION / LOAD_REGION from fitdocs.contract"
    )


def test_docedit_re_exports_the_managed_load_keys() -> None:
    """``FRONTMATTER_LOAD_KEYS`` still names the contract's tuple, unchanged.

    The consolidation moved the definition into the contract but must not move
    the *name*: existing importers of
    :data:`fitdocs.load.docedit.FRONTMATTER_LOAD_KEYS` keep working, and they get
    the same object the contract publishes rather than a divergent copy (Req 6.2).
    """
    assert fitdocs.load.docedit.FRONTMATTER_LOAD_KEYS is fitdocs.contract.LOAD_KEYS, (
        "docedit.FRONTMATTER_LOAD_KEYS must re-export contract.LOAD_KEYS itself"
    )
    assert "FRONTMATTER_LOAD_KEYS" in fitdocs.load.docedit.__all__
