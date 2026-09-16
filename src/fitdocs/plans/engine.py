"""The package's one writing module: orchestration, the writes, and the run
report (training-blocks spec, task 4.2). See "PlanEngine
(`src/fitdocs/plans/engine.py`)" in `.kiro/specs/training-blocks/design.md`
(Req 1.1, 1.2, 1.10, 2.11, 3.9, 4.1, 4.9, 5.1, 5.5-5.7, 6.3, 7.8-7.10, 8.1,
8.4-8.7, 8.10).

This module and `plans/page.py` are the package's **only** importers of
`fitdocs.contract` -- and this module binds exactly one name from it,
`is_generated`, mirroring `fitdocs.history.engine`'s own foreign-occupant
idiom without importing that package (`fitdocs.history` is off limits by
the plan's hard rules).

**Existence rule** (Req 1.10): the plan-source directory is resolved
lexically by `plans.settings.resolve_plans_dir`, which already raises
`PlanSettingsError` for a resolution to the data root itself or inside an
owned path. This module adds the remaining two branches: absent and
unconfigured (`PlanSettings.path is None`) yields a `PlanReport.note` and
touches nothing on disk; absent and configured, or present but not a
directory (either way), raises `PlanSettingsError` so the CLI's existing
`except SettingsError` handler maps it to the configuration exit.

**Discovery** is top-level `*.toml` files only (`Path.iterdir`, never
`Path.glob("**/*")`), sorted by name; a symlinked entry is never parsed --
it is reported `invalid` with one problem naming it a symlink. Every entry
is parsed before any write (`plans.source.load_block`), so one block's
failure can never half-render a sibling.

**Declarations** are refreshed at most once per run, through
`fitdocs.declaration.ensure_declarations`, immediately before the first
valid block's write step -- never when every discovered source is invalid.
That function iterates every `fitdocs.layout.DECLARED_DIRS` entry, so a run
with a valid block may also create or rewrite `workouts/AGENTS.md`,
`history/AGENTS.md` and `fit-archive/AGENTS.md` -- inside the owned set,
not a violation, and stated here so the confinement task's negative half is
phrased precisely (design.md, "PlanEngine" component).

**Per valid block**, in write order: the resolver is called exactly once,
before rendering; both renderers run before anything is read from disk (a
`ValueError` from either is a `failed` outcome carrying "render" as its
path); the existing block page's `notes` region is merged into the fresh
render when a generated page is already present (`RegionError` -> `failed`,
the page left untouched); every write target -- the block page, the pages
directory, and every current row's planned page -- is checked for a
foreign occupant (`_is_foreign_occupant`, the same symlink-first idiom
`fitdocs.history.engine` uses) before anything is written; one foreign
occupant blocks the whole block, nothing written or removed. Only then are
bytes compared and writes attempted: planned pages first (atomic,
`.plans-`-prefixed temp file, `os.replace`), then stale generated planned
pages removed, then the block page last -- so a block page never links to a
planned page this run did not actually write, and a write failure partway
through never reaches the block page (Req 8.7). An `OSError` on any of
these steps ends that block's writes with a `failed` outcome naming the
path in progress and the reason; the next block still proceeds.

This module takes no `today` and calls no clock -- the only dates involved
are the source's own, already baked into the parsed `Block` (Req 8.4). It
has no code path that writes under the resolved plan-source directory: every
write path is composed from `fitdocs.layout.block_doc_path`,
`fitdocs.layout.block_pages_dir` or `fitdocs.layout.planned_doc_path`, or
comes from `fitdocs.declaration.ensure_declarations` -- never from
`source_dir` itself.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, TypeAlias

from fitdocs.contract import is_generated
from fitdocs.declaration import (
    DECLARATION_FILENAME,
    DeclarationState,
    ensure_declarations,
)
from fitdocs.docmerge import RegionError, merge_regions
from fitdocs.layout import (
    BLOCKS_DIR,
    PLAN_SOURCE_SUFFIX,
    block_doc_path,
    block_pages_dir,
    planned_doc_path,
    settings_path,
)
from fitdocs.plans.block_page import render_block_page
from fitdocs.plans.model import Block, PlanProblem
from fitdocs.plans.planned_page import render_planned_page
from fitdocs.plans.resolution import Resolution, unresolved
from fitdocs.plans.settings import (
    PlanSettingsError,
    load_plan_settings,
    resolve_plans_dir,
)
from fitdocs.plans.source import PlanValidationError, load_block
from fitdocs.settings import load_settings_document

__all__ = [
    "BlockOutcome",
    "BlockStatus",
    "PlanReport",
    "Resolver",
    "run_plan",
]

#: The planned/block page markdown extension the stale-removal scan and the
#: unsourced scan both key on -- a plain string, never a shared constant,
#: matching `fitdocs.layout`'s own composition of `f"{block_id}.md"`.
_MD_SUFFIX: Final[str] = ".md"

#: This module's own atomic-write temp-file prefix -- distinct from every
#: other engine's, per the plan's hard rule that the literal `.plans-` (not
#: a forbidden spelling) names this package's writes.
_TMP_PREFIX: Final[str] = ".plans-"
_TMP_SUFFIX: Final[str] = ".tmp"


class BlockStatus(StrEnum):
    """One block's outcome for a single `run_plan` call (Req 8.6)."""

    RENDERED = "rendered"
    UNCHANGED = "unchanged"
    INVALID = "invalid"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class BlockOutcome:
    """One source's outcome, in the order `run_plan` discovered it."""

    source: str
    """The source file, as a report path (Req 8.6)."""

    block_id: str
    """The source's file stem -- set even when `status` is `INVALID`."""

    status: BlockStatus

    written: tuple[str, ...]
    """Report paths, in write order: planned pages before the block page."""

    removed: tuple[str, ...]
    """Stale generated planned pages removed, as report paths."""

    problems: tuple[PlanProblem, ...]
    """Every problem, when `status` is `INVALID`; empty otherwise."""

    foreign: tuple[str, ...]
    """Blocking occupant paths when `status` is `BLOCKED`; non-generated
    files left alone in the pages directory when `status` is `RENDERED` or
    `UNCHANGED` (Req 7.9); empty otherwise."""

    failures: tuple[tuple[str, str], ...]
    """`(path, reason)` pairs; `path` is `"render"` for a renderer failure,
    else the write path in progress when an `OSError` was raised."""


@dataclass(frozen=True)
class PlanReport:
    """Everything one `run_plan` call did or found (Req 8.6)."""

    source_dir: str
    """The resolved plan-source directory, as a report path."""

    blocks: tuple[BlockOutcome, ...]
    """Source order -- the fixed, sorted-by-name discovery order."""

    unsourced: tuple[str, ...]
    """`blocks/*.md` (other than the ownership declaration) and
    `blocks/<dir>/` entries with no matching source, as report paths."""

    declarations_foreign: tuple[str, ...]
    """Declared directories whose declaration file is foreign, as report
    paths -- populated only on a run that refreshed declarations at all."""

    note: str | None
    """Set on the two no-op paths: an unconfigured, absent plan-source
    directory, or a present, empty one. `None` otherwise."""

    @property
    def failed(self) -> bool:
        """Whether any block is `INVALID`, `BLOCKED` or `FAILED` (Req 8.9)."""
        return any(
            outcome.status
            in (BlockStatus.INVALID, BlockStatus.BLOCKED, BlockStatus.FAILED)
            for outcome in self.blocks
        )


Resolver: TypeAlias = Callable[[Block], Resolution]
"""`resolve(block) -> Resolution`, called once per valid block, after
validation and before rendering (Cross-spec obligations (training-blocks
↔ plan-resolution), item 3). `run_plan`'s default resolver ignores its
argument and returns `plans.resolution.unresolved()`."""


def _report_path(data_root: Path, path: Path) -> str:
    """`path`, data-root-relative POSIX when it lies inside `data_root`,
    else absolute POSIX -- the plan-source directory may resolve outside
    the data root, unlike every rendered path (Req 8.6)."""
    try:
        return path.relative_to(data_root).as_posix()
    except ValueError:
        return path.as_posix()


def _read_text_if_present(path: Path) -> str | None:
    """`path`'s UTF-8 text, or `None` when it is absent, unreadable, or not
    valid UTF-8 -- callers that need to distinguish "foreign" from "absent"
    precisely use `_is_foreign_occupant` instead; this helper is only for
    contexts (the notes-region merge, the stale-file scan) where "could not
    be read as fitdocs' own text" is enough on its own."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError):
        return None


def _is_foreign_occupant(path: Path) -> bool:
    """Whether something occupies `path` this run must not write through
    (Req 7.8): a symlink (checked first, before any read through it), a
    directory, an unreadable file, a file that is not valid UTF-8, or a
    readable file whose text carries no line starting
    `contract.GENERATED_PREFIX`. Absence is never foreign. Mirrors
    `fitdocs.history.engine._is_foreign_occupant` -- the same occupant
    classes, the same reason, held here as this module's own copy."""
    if path.is_symlink():
        return True
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    except (OSError, UnicodeDecodeError):
        return True
    return not is_generated(text)


def _pages_dir_is_foreign(path: Path) -> bool:
    """Whether a block's pages directory is occupied by something other
    than "absent" or "a real directory" (Req 7.8): a symlink (even one
    pointing at a directory) or a plain file is foreign; absence is not."""
    if path.is_symlink():
        return True
    if not path.exists():
        return False
    return not path.is_dir()


def _atomic_write(path: Path, text: str) -> None:
    """Write `text` to `path` as a whole-file atomic replace: a
    `.plans-`-prefixed temp file in the same directory, then `os.replace`
    (Req 8.7). `newline=""` preserves the exact string bytes; the temp file
    is removed on any failure, so a crash never leaves a partial file."""
    directory = path.parent
    fd, tmp_name = tempfile.mkstemp(
        dir=directory, prefix=_TMP_PREFIX, suffix=_TMP_SUFFIX
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _reason(exc: OSError) -> str:
    """A concise, non-empty failure reason -- the error kind and message,
    the same shape `fitdocs.history.engine._reason` reports."""
    message = str(exc).strip()
    kind = type(exc).__name__
    return f"{kind}: {message}" if message else kind


def _discover(source_dir: Path) -> list[Path]:
    """Top-level `*.toml` entries of `source_dir`, sorted by name -- no
    recursion (`Path.iterdir`, never `Path.glob("**/*")`). A directory
    named with the suffix is excluded; a symlinked file is included here
    and reported `invalid` by the caller (Req 1.1, 8.1)."""
    candidates = [
        entry
        for entry in source_dir.iterdir()
        if entry.suffix == PLAN_SOURCE_SUFFIX and not entry.is_dir()
    ]
    candidates.sort(key=lambda entry: entry.name)
    return candidates


def _unsourced(data_root: Path, discovered_ids: set[str]) -> tuple[str, ...]:
    """`blocks/*.md` (other than the ownership declaration) and
    `blocks/<dir>/` whose stem/name has no discovered source -- listed,
    never touched (Req 7.10). `discovered_ids` includes invalid sources'
    ids too: a source that failed to parse still exists, so its pre-existing
    pages are not "unsourced"."""
    blocks_root = data_root / BLOCKS_DIR
    if not blocks_root.is_dir():
        return ()
    results: list[str] = []
    for child in sorted(blocks_root.iterdir(), key=lambda entry: entry.name):
        if child.name == DECLARATION_FILENAME:
            continue
        if child.is_dir():
            if child.name not in discovered_ids:
                results.append(_report_path(data_root, child))
        elif child.suffix == _MD_SUFFIX and child.stem not in discovered_ids:
            results.append(_report_path(data_root, child))
    return tuple(results)


def _render_and_write(
    data_root: Path, source_report: str, block: Block, resolver: Resolver
) -> BlockOutcome:
    """Render, merge, foreign-check and write one valid block (Req 4.9,
    5.1, 5.5-5.7, 6.3, 7.8, 7.9, 8.5-8.7)."""
    block_id = block.id
    resolution = resolver(block)

    block_page_path = block_doc_path(data_root, block_id)
    pages_dir = block_pages_dir(data_root, block_id)
    planned_paths = {
        row.id: planned_doc_path(data_root, block_id, row.id)
        for row in block.current.rows
    }

    try:
        fresh_planned = {
            row.id: render_planned_page(block, row, resolution)
            for row in block.current.rows
        }
        fresh_block_text = render_block_page(block, resolution)
    except ValueError as exc:
        return BlockOutcome(
            source=source_report,
            block_id=block_id,
            status=BlockStatus.FAILED,
            written=(),
            removed=(),
            problems=(),
            foreign=(),
            failures=(("render", str(exc)),),
        )

    existing_block_text = _read_text_if_present(block_page_path)
    if existing_block_text is not None and is_generated(existing_block_text):
        try:
            fresh_block_text = merge_regions(fresh_block_text, existing_block_text)
        except RegionError as exc:
            return BlockOutcome(
                source=source_report,
                block_id=block_id,
                status=BlockStatus.FAILED,
                written=(),
                removed=(),
                problems=(),
                foreign=(),
                failures=((_report_path(data_root, block_page_path), str(exc)),),
            )

    foreign_blocking: list[str] = []
    if _is_foreign_occupant(block_page_path):
        foreign_blocking.append(_report_path(data_root, block_page_path))
    if _pages_dir_is_foreign(pages_dir):
        foreign_blocking.append(_report_path(data_root, pages_dir))
    for planned_path in planned_paths.values():
        if _is_foreign_occupant(planned_path):
            foreign_blocking.append(_report_path(data_root, planned_path))
    if foreign_blocking:
        return BlockOutcome(
            source=source_report,
            block_id=block_id,
            status=BlockStatus.BLOCKED,
            written=(),
            removed=(),
            problems=(),
            foreign=tuple(foreign_blocking),
            failures=(),
        )

    current_ids = set(planned_paths)
    stale_remove: list[Path] = []
    kept_foreign: list[str] = []
    if pages_dir.is_dir():
        for child in sorted(pages_dir.iterdir(), key=lambda entry: entry.name):
            if child.is_dir() or child.suffix != _MD_SUFFIX:
                continue
            if child.stem in current_ids:
                continue
            if child.is_symlink():
                kept_foreign.append(_report_path(data_root, child))
                continue
            text = _read_text_if_present(child)
            if text is not None and is_generated(text):
                stale_remove.append(child)
            else:
                kept_foreign.append(_report_path(data_root, child))

    written: list[str] = []
    removed: list[str] = []
    current_path: Path | None = None
    try:
        if block.current.rows:
            current_path = pages_dir
            pages_dir.mkdir(parents=True, exist_ok=True)
        for row in block.current.rows:
            planned_path = planned_paths[row.id]
            current_path = planned_path
            text = fresh_planned[row.id]
            if not planned_path.exists() or planned_path.read_bytes() != text.encode(
                "utf-8"
            ):
                _atomic_write(planned_path, text)
                written.append(_report_path(data_root, planned_path))
        for stale_path in stale_remove:
            current_path = stale_path
            stale_path.unlink()
            removed.append(_report_path(data_root, stale_path))
        current_path = block_page_path
        if not block_page_path.exists() or block_page_path.read_bytes() != (
            fresh_block_text.encode("utf-8")
        ):
            _atomic_write(block_page_path, fresh_block_text)
            written.append(_report_path(data_root, block_page_path))
    except OSError as exc:
        assert current_path is not None
        return BlockOutcome(
            source=source_report,
            block_id=block_id,
            status=BlockStatus.FAILED,
            written=tuple(written),
            removed=tuple(removed),
            problems=(),
            foreign=(),
            failures=((_report_path(data_root, current_path), _reason(exc)),),
        )

    status = BlockStatus.RENDERED if (written or removed) else BlockStatus.UNCHANGED
    return BlockOutcome(
        source=source_report,
        block_id=block_id,
        status=status,
        written=tuple(written),
        removed=tuple(removed),
        problems=(),
        foreign=tuple(kept_foreign),
        failures=(),
    )


def run_plan(data_root: Path, *, resolve: Resolver | None = None) -> PlanReport:
    """Run the whole plan pass over `data_root` and return its report (Req
    1.1, 1.2, 1.10, 2.11, 3.9, 4.1, 4.9, 5.1, 5.5-5.7, 6.3, 7.8-7.10, 8.1,
    8.4-8.7, 8.10).

    Reads `fitdocs.toml` once, projects `[plans]`, resolves the source
    directory. Raises `fitdocs.settings.SettingsError` for a malformed
    settings file, and `plans.settings.PlanSettingsError` (itself a
    `SettingsError`) for a malformed `[plans]` table, a source directory
    resolving inside an owned path or to the data root, an absent
    *configured* directory, or a present, non-directory path.

    Discovers every top-level `*.toml` entry, sorted by name; parses each
    before any write. Scans `blocks/` for unsourced pages and directories.
    Refreshes ownership declarations once, only when at least one block is
    valid. Renders, merges, foreign-checks and writes each valid block in
    turn -- one block's `failed` or `blocked` outcome never stops the next.

    `resolve` is called once per valid block, after validation and before
    rendering; the default ignores its argument and returns
    `plans.resolution.unresolved()`. Takes no `today` and calls no clock.
    """
    settings_file = settings_path(data_root)
    document = load_settings_document(data_root)
    plan_settings = load_plan_settings(document, settings_file)
    source_dir = resolve_plans_dir(data_root, plan_settings, settings_file)
    source_report = _report_path(data_root, source_dir)

    if not source_dir.exists():
        if plan_settings.path is None:
            return PlanReport(
                source_dir=source_report,
                blocks=(),
                unsourced=(),
                declarations_foreign=(),
                note=f"no plan source directory at {source_report}",
            )
        raise PlanSettingsError(
            f"{settings_file}: [plans] path resolves to {source_dir}, "
            "which does not exist"
        )
    if not source_dir.is_dir():
        raise PlanSettingsError(
            f"{settings_file}: [plans] path resolves to {source_dir}, "
            "which is not a directory"
        )

    entries = _discover(source_dir)

    discovered_ids: set[str] = set()
    parsed: list[tuple[Path, Block | None, tuple[PlanProblem, ...]]] = []
    for entry in entries:
        block_id = entry.stem
        discovered_ids.add(block_id)
        if entry.is_symlink():
            parsed.append(
                (
                    entry,
                    None,
                    (
                        PlanProblem(
                            entry="file",
                            field=None,
                            message=(
                                "is a symlink; a plan source must be a regular file"
                            ),
                        ),
                    ),
                )
            )
            continue
        try:
            loaded_block = load_block(entry, block_id=block_id)
        except PlanValidationError as exc:
            parsed.append((entry, None, exc.problems))
            continue
        parsed.append((entry, loaded_block, ()))

    unsourced = _unsourced(data_root, discovered_ids)

    valid_blocks = [block for _, block, _ in parsed if block is not None]
    declarations_foreign: tuple[str, ...] = ()
    if valid_blocks:
        declaration_outcomes = ensure_declarations(data_root)
        declarations_foreign = tuple(
            outcome.path
            for outcome in declaration_outcomes
            if outcome.state == DeclarationState.FOREIGN
        )

    default_resolver: Resolver = lambda parsed_block: unresolved()  # noqa: E731
    resolver: Resolver = resolve if resolve is not None else default_resolver

    outcomes: list[BlockOutcome] = []
    for entry, block, problems in parsed:
        block_id = entry.stem
        entry_report = _report_path(data_root, entry)
        if block is None:
            outcomes.append(
                BlockOutcome(
                    source=entry_report,
                    block_id=block_id,
                    status=BlockStatus.INVALID,
                    written=(),
                    removed=(),
                    problems=problems,
                    foreign=(),
                    failures=(),
                )
            )
            continue
        outcomes.append(_render_and_write(data_root, entry_report, block, resolver))

    note = None if entries else f"no plan sources under {source_report}"

    return PlanReport(
        source_dir=source_report,
        blocks=tuple(outcomes),
        unsourced=unsourced,
        declarations_foreign=declarations_foreign,
        note=note,
    )
