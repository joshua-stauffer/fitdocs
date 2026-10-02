"""Channel-merge end-to-end suite over temp data roots (engine level).

One headed section per task (tasks.md, Test File Ownership): this file grows a
section each for the render seam (4.1), arrival order and regeneration (4.2) and
the load and performance engines (5.1). A task edits only its own section.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import timedelta, timezone
from pathlib import Path

import pytest

import fitdocs.sync as sync_module
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.docmerge import begin_marker, end_marker
from fitdocs.inbox import DEFAULT_INBOX_SETTINGS
from fitdocs.layout import WORKOUTS_DIR, source_ref
from fitdocs.quarantine import QuarantineRecord
from fitdocs.render import DocContext, RenderedDoc, TileRef, render_document
from fitdocs.sync import SyncReport, drain, regen, sync
from tests.fixtures import merge

# A fixed -06:00 zone so stems never depend on where the suite runs.
_TZ = timezone(timedelta(hours=-6))


class _ServingTiles:
    """Serves placeholder PNG bytes for any ref (the run fixtures record GPS)."""

    attribution = "test"

    def resolve(self, refs: Sequence[TileRef]) -> dict[TileRef, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


_TILES = _ServingTiles()

_CHANNEL_SOURCES = re.compile(r"\n## Channel Sources\n.*?(?=\n## |\Z)", re.DOTALL)
_TABLE_REF = re.compile(r"^\| `(fit-archive/[0-9a-f]{64}\.fit)` \|", re.MULTILINE)
_FORM_POWER_ROW = re.compile(r"^\| Form power \| .* \|$", re.MULTILINE)


def _ref(data: bytes) -> str:
    return source_ref(hashlib.sha256(data).hexdigest())


def _stage(source: Path, **files: bytes) -> Path:
    source.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (source / f"{name}.fit").write_bytes(data)
    return source


def _sync(source: Path, data_root: Path) -> SyncReport:
    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    assert report.failures == ()
    return report


def _only_page(data_root: Path) -> Path:
    pages = [
        p
        for p in sorted((data_root / WORKOUTS_DIR).glob("*.md"))
        if p.name != DECLARATION_FILENAME
    ]
    assert len(pages) == 1, [p.name for p in pages]
    return pages[0]


def _table_refs(text: str) -> list[str]:
    section = _CHANNEL_SOURCES.search(text)
    assert section is not None, "the page has no Channel Sources section"
    return _TABLE_REF.findall(section.group(0))


def _drain(source: Path, data_root: Path) -> SyncReport:
    report = drain(
        source,
        data_root,
        settings=DEFAULT_INBOX_SETTINGS,
        processed_dir=None,
        quarantine=QuarantineRecord(entries=()),
        athlete=None,
        tz=_TZ,
        tiles=_TILES,
        sleep=lambda _seconds: None,
    ).sync
    assert report.failures == ()
    return report


# --- the render seam (4.1) ---------------------------------------------------


def _run_pair_page(tmp_path: Path, mode: str) -> tuple[Path, str]:
    """Sync the run pair into a fresh data root by ``mode``; return the page."""
    healthfit, stryd = merge.run_pair_fit_bytes()
    data_root = tmp_path / mode / "data"
    data_root.mkdir(parents=True)
    work = tmp_path / mode / "work"
    if mode == "one-run":
        _sync(_stage(work / "both", healthfit=healthfit, stryd=stryd), data_root)
    elif mode == "drain":
        _drain(_stage(work / "both", healthfit=healthfit, stryd=stryd), data_root)
    elif mode == "base-first":
        _sync(_stage(work / "a", healthfit=healthfit), data_root)
        _sync(_stage(work / "b", stryd=stryd), data_root)
    elif mode == "extra-first":
        _sync(_stage(work / "a", stryd=stryd), data_root)
        _sync(_stage(work / "b", healthfit=healthfit), data_root)
    else:
        assert mode == "regen"
        _sync(_stage(work / "a", healthfit=healthfit), data_root)
        _sync(_stage(work / "b", stryd=stryd), data_root)
        report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)
        assert report.failures == ()
        assert len(report.written) == 1
    page = _only_page(data_root)
    return page, page.read_text(encoding="utf-8")


def test_a_single_healthfit_run_has_no_form_power_and_no_channel_sources(
    tmp_path: Path,
) -> None:
    """The starting state of the pair tests: the base alone lacks both."""
    healthfit, _ = merge.run_pair_fit_bytes()
    data_root = tmp_path / "data"
    data_root.mkdir()
    _sync(_stage(tmp_path / "work", healthfit=healthfit), data_root)
    text = _only_page(data_root).read_text(encoding="utf-8")
    assert _FORM_POWER_ROW.search(text) is None
    assert "## Channel Sources" not in text


@pytest.mark.parametrize(
    "mode", ["one-run", "drain", "base-first", "extra-first", "regen"]
)
def test_the_run_pair_renders_one_page_with_form_power_and_both_files_named(
    tmp_path: Path, mode: str
) -> None:
    """Req 1.1, 5.1: every path the page task is reached by (a planned sync run,
    a drain, a later arrival joining a page from the archive, a regen) renders
    the base's page with the Stryd file's form power and names both files, base
    first. Mutations: compose from the base alone in ``_render_activity`` (no
    form power row); pass no provenance to the render context (no section).
    """
    healthfit, stryd = merge.run_pair_fit_bytes()
    assert _ref(healthfit) != _ref(stryd)
    _page, text = _run_pair_page(tmp_path, mode)
    dynamics = text.split("## Running Dynamics", 1)[1].split("\n## ", 1)[0]
    assert _FORM_POWER_ROW.search(dynamics) is not None
    assert _table_refs(text) == [_ref(healthfit), _ref(stryd)]


def test_the_run_pair_page_is_the_same_whichever_path_made_it(
    tmp_path: Path,
) -> None:
    """Req 5.1: the five paths write byte-identical pages (one tree each)."""
    texts = {
        mode: _run_pair_page(tmp_path, mode)[1]
        for mode in ("one-run", "drain", "base-first", "extra-first", "regen")
    }
    assert len(set(texts.values())) == 1, sorted(texts)
    dynamics = texts["one-run"].split("## Running Dynamics", 1)[1].split("\n## ", 1)[0]
    assert _FORM_POWER_ROW.search(dynamics) is not None


def test_the_page_identity_comes_from_the_base_not_the_composition(
    tmp_path: Path,
) -> None:
    """Activity-identity 5.4 / channel-merge 1.6: the page keeps the HealthFit
    copy's identity -- its recorded kind and its ``sources`` list (ascending
    rank, base last) -- though the Stryd file's channels are rendered.
    Mutation: derive the identity keys from the first extra's parse instead
    of the base's.
    """
    healthfit, stryd = merge.run_pair_fit_bytes()
    _page, text = _run_pair_page(tmp_path, "one-run")
    front = text.split("---\n", 2)[1]
    assert "source_kind: phone_copy" in front
    assert f"- {_ref(stryd)}\n- {_ref(healthfit)}\n" in front


def test_a_single_file_page_is_byte_identical_to_its_render_without_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 5.1: a page with no extra renders as it did before composition.

    The page task is spied: its context carries a provenance with no extra
    (the precondition), and rendering that same context with the provenance
    removed gives the page's exact bytes. Mutation: the seam lists the base as
    an extra of itself (a Channel Sources section appears).
    """
    healthfit, _ = merge.run_pair_fit_bytes()
    contexts: list[DocContext] = []
    real = sync_module.render_document

    def spy(ctx: DocContext) -> RenderedDoc:
        contexts.append(ctx)
        return real(ctx)

    monkeypatch.setattr(sync_module, "render_document", spy)
    data_root = tmp_path / "data"
    data_root.mkdir()
    _sync(_stage(tmp_path / "work", healthfit=healthfit), data_root)
    assert len(contexts) == 1
    provenance = contexts[0].channel_provenance
    assert provenance is not None and provenance.extras == ()
    expected = render_document(replace(contexts[0], channel_provenance=None))
    assert expected.markdown == render_document(contexts[0]).markdown
    page = _only_page(data_root).read_text(encoding="utf-8")
    assert page == expected.markdown
    assert begin_marker("notes") in page and end_marker("notes") in page
