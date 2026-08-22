"""The load pass reads documents through the document contract (task 2.2).

``tests/load/test_engine.py`` proves the engine's orchestration against real
data roots; this module covers the one place where converging the engine onto
:mod:`fitdocs.contract` deliberately *changes* behavior rather than preserving
it -- archived-source resolution.

The engine used to take the last ``sources`` entry on trust and join it onto the
data root. The contract's :func:`~fitdocs.contract.sha_of_ref` validates the ref
first, so a hand-edited or traversal-shaped entry resolves to nothing instead of
to a path outside ``fit-archive/`` (Req 1.3). The document is then reported as
having no archived source -- the same graceful degradation an empty history
gets -- rather than being scored from a file the archive never held.

Kept in its own module so the existing engine suite stays byte-identical across
the conversion: those tests must pass unchanged, which is what proves the
consolidation was otherwise behavior-preserving.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta, timezone
from pathlib import Path

from fitdocs.athlete import load_athlete_inputs
from fitdocs.contract import parse_frontmatter, source_refs
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.load.engine import DocLoadEntry, apply_load
from fitdocs.load.prompts import NonInteractiveSession
from fitdocs.sync import sync
from tests.fixtures import builder

# PINNED timezone (never the system zone) so document stems are byte-stable.
_TZ = timezone(timedelta(hours=-6))

#: The malformed entry a hand-edit (or a hostile wiki commit) could leave in a
#: ``sources`` history: syntactically ref-shaped, but escaping the archive.
_TRAVERSAL_REF = "fit-archive/../secrets.fit"


class _ServingTiles:
    """An inert basemap-tile source for the setup sync (tiles are a required arg).

    The load pass never looks at the Map section; this just serves deterministic
    bytes for any ref so the setup render cannot fail. Stateless -> shareable.
    """

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


def _build_data_root(tmp_path: Path, fixtures: dict[str, bytes]) -> Path:
    """Render ``fixtures`` into a temp data root via the real sync pipeline."""
    src = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    for name, data in fixtures.items():
        path = src / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    sync(
        src,
        data_root,
        athlete=load_athlete_inputs(data_root),
        tz=_TZ,
        tiles=_ServingTiles(),
    )
    return data_root


def _sources_last(doc: Path) -> str:
    """The document's current (last) ``sources`` archive ref."""
    frontmatter = parse_frontmatter(doc.read_text(encoding="utf-8"))
    assert frontmatter is not None
    refs = source_refs(frontmatter)
    assert refs
    return refs[-1]


def _docs_of(entries: tuple[DocLoadEntry, ...]) -> set[str]:
    return {entry.doc for entry in entries}


def test_malformed_source_entry_resolves_to_nothing(tmp_path: Path) -> None:
    """A traversal-shaped ``sources`` entry is unresolvable, not a stray read.

    The document's history is hand-edited to ``fit-archive/../secrets.fit`` and a
    *perfectly valid* ``.fit`` file is planted at the path that ref would traverse
    to. The decoy is the whole point: an engine that trusted the ref would find a
    real file there, decode it, and score the document from bytes outside the
    archive. Resolving through :func:`fitdocs.contract.sha_of_ref` rejects the ref
    before any path is built, so the pass reports "no archived source" and leaves
    the document byte-identical (Req 1.3, 9.3).

    Mutation caught: restoring ``data_root.joinpath(*ref.split("/"))`` -- the
    document would leave ``failures`` entirely and be processed from the decoy.
    """
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    # Sorted and declaration-filtered: `workouts/` also holds AGENTS.md since
    # task 4.2, and `Path.glob` yields raw directory order -- name order on
    # APFS, hash order on ext4 -- so an unfiltered first match is a CI flake.
    doc = next(
        p
        for p in sorted((data_root / WORKOUTS_DIR).glob("*.md"))
        if p.name != DECLARATION_FILENAME
    )
    rel = doc.relative_to(data_root).as_posix()
    # The decoy: valid FIT bytes at exactly where the traversal ref would land.
    (data_root / "secrets.fit").write_bytes(builder.run_fit_bytes())
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(_sources_last(doc), _TRAVERSAL_REF, 1),
        encoding="utf-8",
    )
    before = doc.read_bytes()

    report = apply_load(data_root, session=NonInteractiveSession())

    assert _docs_of(report.failures) == {rel}
    assert "no archived source" in report.failures[0].detail
    # Never resolved: the decoy was neither scored nor skipped-after-decoding.
    assert rel not in _docs_of(report.computed)
    assert rel not in _docs_of(report.skipped)
    assert doc.read_bytes() == before  # a failure never mutates its document
