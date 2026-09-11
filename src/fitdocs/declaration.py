"""The in-tree ownership declaration: ``AGENTS.md`` (design: DeclarationWriter).

fitdocs is installed into markdown wikis it does not control, and an LLM agent
maintaining that wiki reads whatever agent-instruction file sits nearest to the
files it is about to touch before it decides whether "improving" them is safe.
This module composes that file's text purely from :mod:`fitdocs.contract`'s
constants -- so the declaration can never state a policy the code does not
implement -- and places it inside every directory :data:`~fitdocs.layout.DECLARED_DIRS`
names (Req 3.1-3.6).

Two things happen here and nowhere else:

- **Composition** (:func:`declaration_text`) is pure: given a directory name it
  returns deterministic markdown built only from `contract` constants and that
  name. It contains no frontmatter (Req 3.7) and no repo-relative documentation
  path -- the pointer to the published ownership contract is a project
  documentation URL, because this text lands in a user's tree that has no
  repository layout, and the same text may ship in a distribution artifact
  whose file list excludes the documentation directory. Every prose claim it
  can make lives in a module-level fragment table, each written exactly once
  and reused by both directories -- `declaration_text` only selects and orders
  fragments, so a claim can never be fixed in one directory's text while an
  unpinned copy stands in the other's. The two emitted texts are pinned as
  committed byte-goldens under ``tests/declaration_golden/`` rather than
  substring assertions.
- **Placement** (:func:`ensure_declarations`) writes only when a directory's
  declaration is absent or its content differs from what fitdocs would write,
  and never over a file that lacks :data:`fitdocs.contract.GENERATED_PREFIX` --
  a foreign file is left untouched and reported (Req 3.5, 3.6). Its read-only
  counterpart, :func:`inspect_declarations`, classifies each directory without
  writing anything, which is what lets a read-only command (task 6) reuse it.

This module does **not** decide *when* a run refreshes declarations -- wiring
``ensure_declarations`` into ``sync`` and ``regen`` is task 4.2's job. It writes
only inside the directories `layout.DECLARED_DIRS` names: never at the data
root, never in the cache directory (`layout.CACHE_DIR`), never in the
tool-state directory (`layout.TOOL_STATE_DIR`).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from fitdocs.contract import (
    CONTRACT_VERSION,
    EFFORT_KEYS,
    GENERATED_PREFIX,
    GENERATOR,
    USER_REGIONS,
    is_generated,
)
from fitdocs.layout import (
    ARCHIVE_DIR,
    DECLARED_DIRS,
)

__all__ = [
    "CONTRACT_DOCUMENTATION_URL",
    "DECLARATION_FILENAME",
    "DeclarationOutcome",
    "DeclarationState",
    "declaration_path",
    "declaration_text",
    "ensure_declarations",
    "inspect_declarations",
]

DECLARATION_FILENAME: Final[str] = "AGENTS.md"
"""The conventional agent-instruction filename fitdocs places in each owned
directory (Req 3.1). Widely recognized by LLM coding and wiki agents as the
file to read before editing a directory's contents."""

# The published ownership contract's URL. This is a *project documentation
# URL*, never a repo-relative path (`docs/ownership-contract.md`): this text is
# written into a user's data root, which has no repository layout at all, and
# the same text may ship inside a distribution artifact whose file manifest
# excludes the `docs/` directory entirely. A single named constant so the
# sibling `distribution` spec -- which owns declaring `[project.urls]` in
# `pyproject.toml` -- can retarget it in exactly one place once that URL is
# formally published; today `pyproject.toml` has no `[project.urls]` section,
# so this is derived by hand from the project's existing published repository
# URL (`README.md`) and the path the published contract is planned to occupy
# (`docs/ownership-contract.md`, task 7.1).
CONTRACT_DOCUMENTATION_URL: Final[str] = (
    "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md"
)


class DeclarationState(StrEnum):
    """A per-directory outcome of composing or inspecting its declaration."""

    CURRENT = "current"
    """Present, fitdocs-generated, and its content already matches."""

    WRITTEN = "written"
    """Created or refreshed by this :func:`ensure_declarations` call."""

    MISSING = "missing"
    """Absent. Only :func:`inspect_declarations` reports this state."""

    STALE = "stale"
    """Present, fitdocs-generated, content differs. Inspect-only."""

    FOREIGN = "foreign"
    """Present but carries no :data:`fitdocs.contract.GENERATED_PREFIX` marker
    -- never overwritten, by either function."""


@dataclass(frozen=True)
class DeclarationOutcome:
    """One directory's declaration state, as reported by either placement
    function."""

    directory: str
    """The declared directory, data-root-relative and POSIX (e.g.
    ``"workouts/"``) -- one of :data:`fitdocs.layout.DECLARED_DIRS`."""

    path: str
    """The declaration's own path, data-root-relative and POSIX (e.g.
    ``"workouts/AGENTS.md"``)."""

    state: DeclarationState
    """What this call found or did."""


# --- claim fragment table ----------------------------------------------------
#
# Every prose claim the emitted text can possibly make is written here EXACTLY
# ONCE, as a named fragment, and reused by both directories. `declaration_text`
# below only *selects and orders* fragments for a given directory -- it holds no
# prose string literal that is not one of these names. This is deliberate: three
# review rounds each fixed a false sentence in one of the two hand-written
# branches this replaced, and each left an unexamined copy of the same claim (or
# a related one) standing in the other branch, or introduced a new one while
# fixing it. A single shared table makes that shape of mistake structurally
# impossible -- there is nowhere for a second, unpinned copy of a claim to hide.
#
# Each fragment's comment names the exact code that makes it true, so a future
# change that breaks the claim has a specific site to re-check.
#
# Scope, per the 2026-07-22 amendment (task 4.1, spec.json amendments): the
# emitted text carries ONLY the elements Req 3.2/3.2a/3.3 mandate, plus one
# actionable rule (never add a region marker fitdocs did not write). No fragment
# quantifies over documents ("each"/"every"/"all documents"/"any document"),
# because only `render_strength` emits `WORKOUT_REGION` -- 8 of 9 golden
# documents carry `notes` + `load` alone (`src/fitdocs/render/views.py`:
# `render_run_ride` ~146, `render_strength` ~183-202, `render_generic` ~214).

_WRITTEN_AND_OWNED: Final[str] = (
    "The contents of `{directory}` are written and tool-owned by fitdocs."
)
# CLAIM ANCHOR: every writer into `layout.DECLARED_DIRS` is fitdocs itself --
# `ensure_declarations` here, `sync._write_outputs` (sync.py:567) for documents
# and assets, and `load.engine`'s atomic temp-file-then-`os.replace` document
# rewrite (engine.py:476), which a `write_text` grep does not surface. True of
# both `workouts/` and `fit-archive/` -- fitdocs is the one that copies an
# export's bytes into `fit-archive/<sha>.fit`, even though those bytes
# originate outside fitdocs (Req 3.2).

_REGIONS: Final[str] = (
    "This directory holds generated workout documents; the user-owned "
    "regions are {user_regions_list}. The region markers actually present in "
    "a document are authoritative for which of them it reserves -- check the "
    "document itself rather than assuming."
)
# CLAIM ANCHOR: `contract.USER_REGIONS` names the ids; `render/views.py`'s
# `render_strength` (~202) is the only view that emits `WORKOUT_REGION`,
# `render_run_ride` (~146) and `render_generic` (~214) emit only `notes` +
# `load`. Deliberately makes NO claim about which documents have which region
# -- that is the false claim shape Req 3.2a forbids and rounds 2/3 both stated
# (Req 3.2).

_USER_KEYS: Final[str] = (
    "The frontmatter keys {user_keys_list} are user-owned: fitdocs never "
    "writes them and carries them unchanged through regeneration. The rest "
    "of the frontmatter block is tool-owned and rebuilt on regeneration."
)
# CLAIM ANCHOR: `contract.USER_KEYS`; `sync._process_file`'s carry of the
# existing document's user-owned keys forward; `render.frontmatter.
# build_frontmatter`'s append of the carried keys after the managed ones; the
# unmanaged-key drop for everything else (`contract` docstring around
# `USER_KEYS`/`MANAGED_KEYS`). Quantifies over *keys*, never over documents --
# it uses none of `_QUANTIFIER_WORDS`
# (`tests/test_declaration.py::test_no_declaration_quantifies_over_documents`),
# so it does not trip that guard (Req 6.4). Workouts only: the archive
# declaration gains nothing but the restated version.

_REDERIVABILITY_DOCS: Final[str] = (
    "The *generated* content of the documents in this directory is "
    "re-derivable: fitdocs rebuilds it by regeneration from the archived "
    "sources under `{archive_dir}/`, the athlete profile, the configured "
    "timezone, and the tile source. Content inside a document's region "
    "markers is not re-derived by regeneration -- it is carried over from "
    "the document itself, so regenerating a deleted document brings back "
    "only the generated content, not what its regions held."
)
# CLAIM ANCHOR: `sync.regen(data_root, *, athlete, tz, tiles)` (sync.py:281-287)
# -- regeneration depends on all four inputs, not the archive and athlete
# profile alone; `tz` and `tiles` are required parameters, not optional ones.
# The second clause is anchored on `sync._process_file` (sync.py:554-559):
# `merge_regions(rendered.markdown, existing_text)` runs ONLY when
# `find_document` matches, so region content is COPIED from the existing
# document and is never derived from the four inputs above. Delete the
# document and regen silently rebuilds it with the placeholder -- no failure,
# no warning; `tests/test_sync.py::test_regen_cannot_recover_region_content_
# once_the_document_is_deleted` pins that behavior. Scoping this claim is
# mandatory under Req 3.2a ("no claim that is false of the directory it is
# placed in"); an unscoped "the documents are re-derivable" is the sentence
# that licenses an agent to delete and regenerate, and it destroys the user's
# writing. The clause quantifies over *region markers*, which covers the
# tool-filled `load` region without naming it -- hence "not re-derived **by
# regeneration**" rather than "not re-derived": `fitdocs load` DOES rebuild
# the `load` region from the archived source and the athlete profile
# (`load/engine.py:339` via `docedit.replace_load_region`), so the unqualified
# form would be false of `load` (Req 3.2).

_IMMUTABILITY: Final[str] = (
    "These files are immutable inputs: they must not be edited, renamed, or "
    "deleted while a document still references them."
)
# CLAIM ANCHOR: Req 3.3's mandated statement verbatim in substance. True
# because `sync.regen` (sync.py:281-352) and `sync.sync` read an archived
# source's bytes and never rewrite it; nothing in the module ever opens
# `fit-archive/*.fit` for writing after the initial archive commit.

_NEVER_ADD_MARKER: Final[str] = (
    "Never add a region marker to a document that does not already have "
    "one: doing so makes the next regeneration refuse to write that "
    "document until the added marker is removed by hand."
)
# CLAIM ANCHOR: `docmerge.merge_regions` (docmerge.py:130-149) raises
# `RegionError` when `existing` holds a region id `fresh` lacks; that call
# happens in `sync._process_file` (sync.py:554-559) BEFORE
# `_write_outputs` -- so nothing is written for that document, and removing
# the stray marker (leaving nothing for `merge_regions` to object to) fully
# restores regeneration on the next run. "Permanently break" would be false;
# this fragment claims no such thing (the one actionable rule Req 3.2a's
# amendment retains).

_OWNER_BLOCK: Final[str] = (
    "## Ownership\n\n"
    "Owner: `{generator}`.\n"
    "Ownership contract version: `{contract_version}`.\n"
    "Published ownership contract: {contract_url}\n"
)
# CLAIM ANCHOR: `contract.GENERATOR`, `contract.CONTRACT_VERSION`,
# `CONTRACT_DOCUMENTATION_URL` -- literal constant values, not prose claims
# about behavior (Req 3.2).


def _english_list(items: Iterable[str]) -> str:
    """Join ``items`` as an English list: ``"a"``, ``"a and b"``, or
    ``"a, b, and c"`` -- correct regardless of how many regions `contract`
    declares.

    A plain ``" and ".join`` reads wrong the moment a third item is added
    (``"a and b and c"``), so this is used everywhere a region list is
    rendered into prose, even though today's region sets happen to have one
    or two members.
    """
    values = list(items)
    if len(values) <= 1:
        return "".join(values)
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def declaration_text(directory: str) -> str:
    """The declaration text for ``directory`` (Req 3.1, 3.2, 3.2a, 3.3, 3.4).

    Deterministic and pure: depends only on `contract` constants and
    ``directory`` itself, so the same directory always yields byte-identical
    text (an invariant :func:`ensure_declarations` depends on to decide when a
    file is already current). Every produced text begins with a line starting
    ``GENERATED_PREFIX`` (Req 3.6's recognition marker).

    Composed by *selecting and ordering* named fragments from the module-level
    claim table above -- this function contains no prose string literal that
    is not one of those names. Per the 2026-07-22 amendment (task 4.1), the
    text carries only the elements Req 3.2/3.2a/3.3 mandate plus the one
    actionable "never add a region marker" rule; all further editing guidance
    is deferred to the published ownership contract (task 7.1), reached by
    ``CONTRACT_DOCUMENTATION_URL``.

    For the directory holding generated documents (``workouts/``): the
    written-and-tool-owned statement, the user-owned region names, the
    user-owned effort-tag frontmatter keys (Req 6.4), and re-derivability by
    regeneration (Req 3.2), plus the never-add-a-marker rule. For the source
    archive (``fit-archive/``): the written-and-tool-owned statement and the
    immutable-inputs statement (Req 3.3) -- the re-derivability,
    user-owned-region, and user-owned-key elements do not apply here (Req
    3.2a, 6.4), so this branch never selects those fragments.

    No fragment quantifies over documents ("each"/"every"/"all
    documents"/"any document"): only :func:`~fitdocs.render.views.render_strength`
    emits :data:`~fitdocs.contract.WORKOUT_REGION`, so a document-distributive
    claim about regions would be false for most golden documents (Req 3.2a).

    The emitted text is plain markdown with no YAML frontmatter (Req 3.4, 3.7):
    it is readable without fitdocs installed, renders correctly in common
    markdown renderers, and is invisible to every ``workouts/*.md`` document
    scan because those scans require a leading frontmatter fence this file
    never opens with.
    """
    user_regions_list = _english_list(f"`{region}`" for region in USER_REGIONS)
    user_keys_list = _english_list(f"`{key}`" for key in EFFORT_KEYS)

    owner_block = _OWNER_BLOCK.format(
        generator=GENERATOR,
        contract_version=CONTRACT_VERSION,
        contract_url=CONTRACT_DOCUMENTATION_URL,
    )

    if directory == ARCHIVE_DIR + "/":
        heading = "Source Archive"
        body = (
            f"{_WRITTEN_AND_OWNED.format(directory=directory)}\n\n{_IMMUTABILITY}\n\n"
        )
    else:
        heading = "Generated Workout Documents"
        body = (
            f"{_WRITTEN_AND_OWNED.format(directory=directory)}\n\n"
            f"{_REGIONS.format(user_regions_list=user_regions_list)}\n\n"
            f"{_USER_KEYS.format(user_keys_list=user_keys_list)}\n\n"
            f"{_REDERIVABILITY_DOCS.format(archive_dir=ARCHIVE_DIR)}\n\n"
            f"{_NEVER_ADD_MARKER}\n\n"
        )

    return (
        f"{GENERATED_PREFIX}: this file is maintained by fitdocs and "
        "rewritten whenever its content differs from what fitdocs would "
        "write -->\n"
        f"# AGENTS.md -- {heading}\n\n"
        f"{body}"
        f"{owner_block}"
    )


def declaration_path(data_root: Path, directory: str) -> Path:
    """The filesystem path of ``directory``'s declaration under ``data_root``."""
    return data_root / directory / DECLARATION_FILENAME


def _relative_path(directory: str) -> str:
    """The declaration's data-root-relative POSIX path for ``directory``."""
    return f"{directory}{DECLARATION_FILENAME}"


class _Unreadable:
    """Sentinel: something occupies ``path``, but it is not a readable fitdocs
    declaration.

    Distinct from ``None`` (nothing there at all) so both entry points can
    tell "absent" apart from "present but unusable" -- a symlink (dangling or
    not), a directory, a file this process cannot open, or a file that is not
    valid UTF-8. Every one of these routes to
    :attr:`DeclarationState.FOREIGN`: none of them is a file fitdocs wrote, and
    none of them may ever be written through (Req 3.6, 7.5, 7.6).
    """


_UNREADABLE: Final[_Unreadable] = _Unreadable()


def _read_existing(path: Path) -> str | _Unreadable | None:
    """The declaration file's text, ``None`` if nothing is there, or
    :data:`_UNREADABLE` if something is there but is not a readable fitdocs
    declaration.

    A symlink at ``path`` is reported :data:`_UNREADABLE` unconditionally,
    *before* any attempt to read through it -- ``Path.exists()`` follows
    symlinks and reads a dangling one as absent, which would let a write land
    outside the data root through it (Req 7.5, 7.6). A directory, a
    permission error, or a non-UTF-8 file degrades to :data:`_UNREADABLE`
    rather than raising, so a hostile or damaged occupant never stops the run
    (Req 3.6).
    """
    if path.is_symlink():
        return _UNREADABLE
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError):
        return _UNREADABLE


def ensure_declarations(data_root: Path) -> tuple[DeclarationOutcome, ...]:
    """Write or refresh every declared directory's ``AGENTS.md`` (Req 3.1, 3.5, 3.6).

    For each directory in :data:`fitdocs.layout.DECLARED_DIRS`, in order:

    - absent -> the parent directory is created (only now, and only because a
      write is about to happen) and the current text is written; reported
      :attr:`~DeclarationState.WRITTEN`.
    - present but not fitdocs-generated (no line starts
      :data:`fitdocs.contract.GENERATED_PREFIX`), or present but not a
      readable fitdocs file at all (a symlink, a directory, an unreadable
      file, or one that is not valid UTF-8) -> left completely untouched;
      reported :attr:`~DeclarationState.FOREIGN` (Req 3.6, 7.5, 7.6).
    - present, fitdocs-generated, content already matches -> left untouched
      (bytes and mtime); reported :attr:`~DeclarationState.CURRENT` (Req 3.5).
    - present, fitdocs-generated, content differs -> rewritten; reported
      :attr:`~DeclarationState.WRITTEN`.

    Never creates a directory it will not write into, so a read-only caller
    never triggers directory creation by mistake -- that is exactly why
    :func:`inspect_declarations` is a separate function rather than a
    read-only flag on this one.
    """
    outcomes: list[DeclarationOutcome] = []
    for directory in DECLARED_DIRS:
        text = declaration_text(directory)
        path = declaration_path(data_root, directory)
        existing = _read_existing(path)

        if existing is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            state = DeclarationState.WRITTEN
        elif isinstance(existing, _Unreadable) or not is_generated(existing):
            state = DeclarationState.FOREIGN
        elif existing == text:
            state = DeclarationState.CURRENT
        else:
            path.write_text(text, encoding="utf-8")
            state = DeclarationState.WRITTEN

        outcomes.append(
            DeclarationOutcome(
                directory=directory, path=_relative_path(directory), state=state
            )
        )
    return tuple(outcomes)


def inspect_declarations(data_root: Path) -> tuple[DeclarationOutcome, ...]:
    """Classify every declared directory's declaration without writing anything.

    The read-only counterpart to :func:`ensure_declarations` (Req 8.5): for
    each directory in :data:`fitdocs.layout.DECLARED_DIRS`, reports
    :attr:`~DeclarationState.MISSING` (absent), :attr:`~DeclarationState.FOREIGN`
    (present, not fitdocs-generated -- including a symlink, a directory, an
    unreadable file, or one that is not valid UTF-8), :attr:`~DeclarationState.STALE`
    (present, fitdocs-generated, content differs), or :attr:`~DeclarationState.CURRENT`
    (present, fitdocs-generated, content matches). Creates no directory, writes
    no file, and never returns :attr:`~DeclarationState.WRITTEN`.
    """
    outcomes: list[DeclarationOutcome] = []
    for directory in DECLARED_DIRS:
        text = declaration_text(directory)
        path = declaration_path(data_root, directory)
        existing = _read_existing(path)

        if existing is None:
            state = DeclarationState.MISSING
        elif isinstance(existing, _Unreadable) or not is_generated(existing):
            state = DeclarationState.FOREIGN
        elif existing == text:
            state = DeclarationState.CURRENT
        else:
            state = DeclarationState.STALE

        outcomes.append(
            DeclarationOutcome(
                directory=directory, path=_relative_path(directory), state=state
            )
        )
    return tuple(outcomes)
