"""Wiring the declaration refresh into sync and regen (task 4.2, Req 3.5-3.8).

Task 4.1 shipped ``fitdocs.declaration``'s standalone unit (``ensure_declarations``,
``inspect_declarations``); ``tests/test_declaration.py`` covers that module in
isolation. This module covers task 4.2's job -- *wiring* that unit into the two
engine entry points this spec implements (``sync`` and ``regen``) as one shared
step, ``fitdocs.sync.refresh_declarations``:

* a first run creates both declarations (Req 3.1, wired through the entry points);
* a second run with no new files leaves every path under the data root byte- and
  mtime-identical, declarations included (Req 3.8);
* a foreign declaration is preserved untouched, becomes a document-scoped
  :class:`~fitdocs.sync.DocWarning`, and never affects the written/skipped/failed
  partition or the exit code (Req 3.6);
* ``load`` never places declarations -- it never creates the owned tree (design:
  DeclarationWriter Implementation Notes);
* sync, regen, and load all report unchanged document counts with declarations
  present (Req 3.7 -- a declaration's frontmatter-less text is invisible to every
  ``workouts/*.md`` document scan, proved end to end rather than assumed);
* the refresh has exactly one implementation, reachable from both entry points
  (the design's explicit rule: "every engine entry point that writes into the
  owned tree refreshes the declarations", not "sync and regen do").
"""

from __future__ import annotations

import ast
import inspect
import os
import time
from datetime import timedelta, timezone
from pathlib import Path

from fitdocs.declaration import DECLARATION_FILENAME, declaration_path
from fitdocs.layout import ARCHIVE_DIR, DECLARED_DIRS, WORKOUTS_DIR
from fitdocs.load import engine as load_engine
from fitdocs.load.engine import apply_load
from fitdocs.load.prompts import NonInteractiveSession
from fitdocs.sync import DocWarning, SyncReport, refresh_declarations, regen, sync
from tests.fixtures import builder

_TZ = timezone(timedelta(hours=-6))
_WORKOUTS = f"{WORKOUTS_DIR}/"
_ARCHIVE = f"{ARCHIVE_DIR}/"


class _Tiles:
    """Minimal offline tile source: serves deterministic bytes for any ref."""

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: object) -> dict[object, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


_TILES = _Tiles()


def _put(source_dir: Path, name: str, data: bytes) -> Path:
    path = source_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    """Bytes and mtime (ns) of every file under ``root``."""
    state: dict[str, tuple[bytes, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            state[path.relative_to(root).as_posix()] = (
                path.read_bytes(),
                path.stat().st_mtime_ns,
            )
    return state


def _age_all(root: Path) -> None:
    """Push every file's mtime distinctly into the past (avoids fs-granularity
    flakiness in a byte-and-mtime comparison)."""
    old = time.time() - 3600
    for path in root.rglob("*"):
        if path.is_file():
            os.utime(path, (old, old))


def _stage_run(source_dir: Path) -> None:
    _put(source_dir, "run.fit", builder.run_fit_bytes())


def _sync(source_dir: Path, data_root: Path) -> SyncReport:
    return sync(source_dir, data_root, athlete=None, tz=_TZ, tiles=_TILES)


def _regen(data_root: Path) -> SyncReport:
    return regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)


def _declared_paths(data_root: Path) -> list[Path]:
    return [declaration_path(data_root, directory) for directory in DECLARED_DIRS]


# --- first run creates both declarations -------------------------------------


def test_first_sync_run_creates_both_declarations(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _stage_run(source)

    _sync(source, data_root)

    for path in _declared_paths(data_root):
        assert path.is_file()
        assert path.name == DECLARATION_FILENAME


def test_first_regen_run_creates_both_declarations(tmp_path: Path) -> None:
    # regen takes no source directory -- an empty data root still gets its
    # declarations, because the refresh runs before any document processing,
    # not conditioned on there being anything to regenerate.
    data_root = tmp_path / "data"
    data_root.mkdir()

    report = _regen(data_root)

    assert report.written == ()
    assert report.failures == ()
    for path in _declared_paths(data_root):
        assert path.is_file()


# --- second run: whole data root byte- and mtime-identical (Req 3.8) --------


def test_second_sync_run_leaves_the_whole_data_root_byte_and_mtime_identical(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _stage_run(source)

    _sync(source, data_root)
    _age_all(data_root)
    before = _snapshot(data_root)

    second = _sync(source, data_root)

    after = _snapshot(data_root)
    assert second.written == ()
    assert len(second.skipped) == 1
    # Every path -- documents, assets, archive, AND both declarations -- is
    # untouched: same bytes, same mtime.
    assert after == before


def test_second_regen_run_rewrites_docs_byte_identically_leaves_declarations_alone(
    tmp_path: Path,
) -> None:
    """``regen`` always rewrites every document unconditionally (Req 4.1: byte-
    identical content, not a no-op) -- that write-every-time behavior predates
    this task and is untouched by it. The declarations are different: refreshed
    through the same write-when-different ``ensure_declarations`` rule sync
    uses, so *they* stay byte- and mtime-identical across a second regen with
    nothing else changed.
    """
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _stage_run(source)
    _sync(source, data_root)

    _regen(data_root)  # first regen: re-renders once, may touch mtimes
    _age_all(data_root)
    before = _snapshot(data_root)

    second = _regen(data_root)

    after = _snapshot(data_root)
    assert second.failures == ()
    # Content is byte-identical everywhere (Req 4.1, pre-existing behavior).
    assert {key: value[0] for key, value in after.items()} == {
        key: value[0] for key, value in before.items()
    }
    # The two declarations specifically are untouched down to the mtime: regen's
    # unconditional per-document rewrite does not apply to them.
    declaration_keys = [
        declaration_path(data_root, directory).relative_to(data_root).as_posix()
        for directory in DECLARED_DIRS
    ]
    for key in declaration_keys:
        assert after[key] == before[key]


# --- foreign declaration: warning, never a failure, exit stays 0 (Req 3.6) --


def _plant_foreign(data_root: Path, directory: str) -> Path:
    (data_root / directory).mkdir(parents=True, exist_ok=True)
    path = declaration_path(data_root, directory)
    path.write_text("# hands off, this is mine\n", encoding="utf-8")
    return path


def test_sync_preserves_a_foreign_declaration_and_reports_only_a_warning(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    # TWO sources, deliberately: the refresh runs ONCE PER RUN, not per file, so
    # a foreign declaration yields exactly one warning no matter how many files
    # are processed. With a single source a per-file refresh would be
    # indistinguishable from a once-per-run one and the placement requirement
    # (Req 3.5, "once per run ... before per-file processing") would go
    # unenforced.
    _put(source, "run.fit", builder.run_fit_bytes())
    _put(source, "ride.fit", builder.ride_fit_bytes())
    foreign = _plant_foreign(data_root, _WORKOUTS)
    foreign_text = foreign.read_text(encoding="utf-8")

    report = _sync(source, data_root)

    # Never touched.
    assert foreign.read_text(encoding="utf-8") == foreign_text
    # Never a failure; both files still process and write their documents.
    assert report.failures == ()
    assert len(report.written) == 2
    # Exactly one warning names the foreign declaration's data-root-relative
    # path -- one per RUN, not one per processed file.
    expected_doc = f"{_WORKOUTS}{DECLARATION_FILENAME}"
    matching = [w for w in report.warnings if w.doc == expected_doc]
    assert len(matching) == 1
    assert matching[0].detail  # non-empty, human-readable


def test_regen_preserves_a_foreign_declaration_and_reports_only_a_warning(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    foreign = _plant_foreign(data_root, _ARCHIVE)
    foreign_text = foreign.read_text(encoding="utf-8")

    report = _regen(data_root)

    assert foreign.read_text(encoding="utf-8") == foreign_text
    assert report.failures == ()
    expected_doc = f"{_ARCHIVE}{DECLARATION_FILENAME}"
    matching = [w for w in report.warnings if w.doc == expected_doc]
    assert len(matching) == 1


def test_refresh_declarations_appends_a_warning_per_foreign_directory(
    tmp_path: Path,
) -> None:
    # Unit-level check of the shared step itself, isolated from either entry
    # point: both declared directories foreign -> two warnings, one per path.
    data_root = tmp_path / "data"
    _plant_foreign(data_root, _WORKOUTS)
    _plant_foreign(data_root, _ARCHIVE)
    warnings: list[DocWarning] = []

    refresh_declarations(data_root, warnings)

    docs = {w.doc for w in warnings}
    assert docs == {
        f"{_WORKOUTS}{DECLARATION_FILENAME}",
        f"{_ARCHIVE}{DECLARATION_FILENAME}",
    }


# --- load never places declarations ------------------------------------------


def test_load_does_not_create_declarations_on_a_fresh_data_root(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()

    apply_load(data_root, session=NonInteractiveSession())

    for path in _declared_paths(data_root):
        assert not path.exists()


def test_load_does_not_remove_or_alter_an_existing_foreign_declaration(
    tmp_path: Path,
) -> None:
    # If sync already placed real declarations, a subsequent load run must not
    # touch them either way -- it never calls the refresh at all.
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _stage_run(source)
    _sync(source, data_root)
    before = _snapshot(data_root)

    apply_load(data_root, session=NonInteractiveSession())

    after = {
        key: value
        for key, value in _snapshot(data_root).items()
        if key.endswith(DECLARATION_FILENAME)
    }
    before_declarations = {
        key: value
        for key, value in before.items()
        if key.endswith(DECLARATION_FILENAME)
    }
    assert after == before_declarations


def test_load_engine_module_never_imports_the_declaration_refresh() -> None:
    """Structural pin: ``load/engine.py`` has no path to placing declarations.

    ``load`` never creates the owned tree (design: DeclarationWriter
    Implementation Notes), so its source must name neither
    ``ensure_declarations`` nor the shared ``refresh_declarations`` step.
    """
    source = inspect.getsource(load_engine)
    assert "ensure_declarations" not in source
    assert "refresh_declarations" not in source


# --- Req 3.7: declarations invisible to document scans, proved end to end ---


def _workout_doc_count(data_root: Path) -> int:
    """Number of files under ``workouts/`` fitdocs recognizes as workout
    documents -- computed the same way :func:`fitdocs.sync.find_document` does,
    so this count is exactly what the engine itself would see."""
    from fitdocs.contract import is_workout_document, parse_frontmatter

    workouts_dir = data_root / WORKOUTS_DIR
    if not workouts_dir.is_dir():
        return 0
    count = 0
    for path in workouts_dir.glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        frontmatter = parse_frontmatter(text)
        if frontmatter is not None and is_workout_document(frontmatter):
            count += 1
    return count


def test_sync_regen_load_report_unchanged_document_counts_with_declarations_present(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    _put(source, "ride.fit", builder.ride_fit_bytes())

    first = _sync(source, data_root)
    assert len(first.written) == 2
    count_after_sync = _workout_doc_count(data_root)
    assert count_after_sync == 2
    # Both declarations really are present alongside the two documents, each
    # ending in ``.md`` -- the exact shape that would inflate a naive
    # ``glob("*.md")`` count if the scans did not filter on frontmatter.
    assert (data_root / WORKOUTS_DIR / DECLARATION_FILENAME).is_file()
    assert (data_root / ARCHIVE_DIR / DECLARATION_FILENAME).is_file()
    assert len(list((data_root / WORKOUTS_DIR).glob("*.md"))) == 3

    second_sync = _sync(source, data_root)
    assert second_sync.written == ()
    assert _workout_doc_count(data_root) == count_after_sync

    regen_report = _regen(data_root)
    assert regen_report.failures == ()
    assert len(regen_report.written) == 2
    assert _workout_doc_count(data_root) == count_after_sync

    load_report = apply_load(data_root, session=NonInteractiveSession())
    assert load_report.failures == ()
    total_load_outcomes = (
        len(load_report.computed)
        + len(load_report.restored)
        + len(load_report.unsupported)
        + len(load_report.skipped)
    )
    assert total_load_outcomes == count_after_sync


# --- exactly one implementation, reachable from both entry points -----------


def _calls_refresh_declarations(func: object) -> bool:
    """Does ``func``'s own body contain a direct call to ``refresh_declarations``?

    An AST walk over the function's source, not a substring search over the
    whole module -- so a future refactor that renames or removes the call from
    ``sync``/``regen`` (rather than duplicating the refresh elsewhere) is
    caught precisely, and a copy of the name in a docstring or comment cannot
    produce a false pass.
    """
    tree = ast.parse(inspect.getsource(func))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "refresh_declarations"
        ):
            return True
    return False


def test_sync_and_regen_both_call_the_shared_refresh_step() -> None:
    assert _calls_refresh_declarations(sync)
    assert _calls_refresh_declarations(regen)


def test_refresh_declarations_is_defined_exactly_once_in_the_sync_module() -> None:
    """Guards against a second, inlined copy of the refresh logic.

    Parses the whole ``sync.py`` module and counts top-level function
    definitions named ``refresh_declarations``: exactly one, not zero (moved
    elsewhere without updating the callers) and not two (a duplicate body
    introduced instead of a shared call).
    """
    import fitdocs.sync as sync_module

    tree = ast.parse(inspect.getsource(sync_module))
    definitions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "refresh_declarations"
    ]
    assert len(definitions) == 1


def test_load_command_registers_no_entry_point_for_the_refresh() -> None:
    """``load`` is not a writing-into-the-tree entry point for this step.

    A structural complement to the ``load``-specific tests above: the CLI's
    ``load`` command path is built entirely on ``apply_load``, which this
    module already proved never calls the refresh.
    """
    import fitdocs.cli as cli_module

    source = inspect.getsource(cli_module.load_command)
    assert "refresh_declarations" not in source
    assert "ensure_declarations" not in source
