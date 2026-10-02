"""Channel-merge end-to-end suite over temp data roots.

One headed section per task (tasks.md, Test File Ownership): this file grows a
section each for the render seam (4.1), arrival order and regeneration (4.2) and
an aged page and the document-format version (5.1). A task edits only its own
section. The load and benchmark passes are tests/test_compose_passes_e2e.py.
"""

from __future__ import annotations

import hashlib
import itertools
import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

import fitdocs.sync as sync_module
from fitdocs import contract
from fitdocs.cli import app
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


# --- arrival order, regeneration, drain and summaries (4.2) ------------------

_RUN_FILES = ("healthfit", "stryd_a", "stryd_b")
_ORDERS = list(itertools.permutations(_RUN_FILES))
_RUNNING_DYNAMICS = re.compile(r"\n## Running Dynamics\n.*?(?=\n## |\Z)", re.DOTALL)
_UUID_LINE = re.compile(r"^uuid: .*$", re.MULTILINE)

# The Running Dynamics Form power row of the run pair (stryd_a's form power)
# and of the trio (stryd_b's, one watt higher at every sample).
_FORM_POWER_ROW_A = "| Form power | 62 w | 52–72 w | 90% |"
_FORM_POWER_ROW_B = "| Form power | 63 w | 53–73 w | 90% |"


def _dynamics_form_power_row(text: str) -> str:
    section = _RUNNING_DYNAMICS.search(text)
    assert section is not None, "the page has no Running Dynamics section"
    rows = _FORM_POWER_ROW.findall(section.group(0))
    assert len(rows) == 1, rows
    return str(rows[0])


def _tree(data_root: Path) -> dict[str, bytes]:
    """Every file under the data root (pages, charts, archive), by relative path."""
    return {
        path.relative_to(data_root).as_posix(): path.read_bytes()
        for path in sorted(data_root.rglob("*"))
        if path.is_file()
    }


def _sync_run_files(
    tmp_path: Path, label: str, order: Sequence[str], *, one_run: bool
) -> Path:
    """Sync the run trio's files in ``order`` into a fresh data root.

    ``one_run`` stages all three in one source directory, names prefixed with
    their position so a sorted directory listing yields ``order``; otherwise
    each file is its own sync run, in ``order``.
    """
    files = dict(zip(_RUN_FILES, merge.run_trio_fit_bytes(), strict=True))
    data_root = tmp_path / label / "data"
    data_root.mkdir(parents=True)
    work = tmp_path / label / "work"
    if one_run:
        _sync(
            _stage(
                work, **{f"{i}_{name}": files[name] for i, name in enumerate(order)}
            ),
            data_root,
        )
    else:
        for i, name in enumerate(order):
            _sync(_stage(work / str(i), **{name: files[name]}), data_root)
    return data_root


@pytest.fixture(scope="module")
def trio_baseline(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    """The trio synced in the canonical order, one run per file."""
    root = tmp_path_factory.mktemp("trio-baseline")
    return _tree(_sync_run_files(root, "base", _RUN_FILES, one_run=False))


def test_the_trio_baseline_takes_form_power_from_the_higher_ranked_stryd_file(
    trio_baseline: dict[str, bytes], tmp_path: Path
) -> None:
    """Precondition of the arrival-order tests: the baseline is non-trivial and
    its form power is ``stryd_b``'s, which differs from the pair's (``stryd_a``).
    """
    pages = [n for n in trio_baseline if re.fullmatch(r"workouts/[^/]+\.md", n)]
    pages = [n for n in pages if n != f"{WORKOUTS_DIR}/{DECLARATION_FILENAME}"]
    assert len(pages) == 1, pages
    assets = [n for n in trio_baseline if n.startswith("workouts/assets/")]
    assert len(assets) >= 3, assets
    text = trio_baseline[pages[0]].decode("utf-8")
    assert _dynamics_form_power_row(text) == _FORM_POWER_ROW_B
    _page, pair_text = _run_pair_page(tmp_path, "one-run")
    assert _dynamics_form_power_row(pair_text) == _FORM_POWER_ROW_A


@pytest.mark.parametrize("one_run", [True, False], ids=["one-run", "three-runs"])
@pytest.mark.parametrize("order", _ORDERS, ids=["-".join(o) for o in _ORDERS])
def test_the_run_trio_gives_the_same_pages_and_assets_in_every_arrival_order(
    tmp_path: Path,
    trio_baseline: dict[str, bytes],
    order: tuple[str, ...],
    one_run: bool,
) -> None:
    """Req 1.3, 5.1: whichever order the three files arrive in, and whether in
    one run or across three, every file under the data root (page, charts,
    archive) is byte-identical to the baseline, and the Running Dynamics Form
    power row is ``stryd_b``'s. Mutation: take the extras in the listed
    (arrival) order instead of rank order in ``_render_activity``.
    """
    data_root = _sync_run_files(tmp_path, "case", order, one_run=one_run)
    tree = _tree(data_root)
    page = _only_page(data_root)
    text = page.read_text(encoding="utf-8")
    assert _dynamics_form_power_row(text) == _FORM_POWER_ROW_B
    assert tree == trio_baseline


def test_regen_reproduces_the_synced_run_trio_byte_for_byte(tmp_path: Path) -> None:
    """Req 5.1: ``regen`` over a synced trio rewrites the page and leaves every
    file under the data root as the sync left it. Mutation: take the extras in
    the listed (arrival) order instead of rank order in ``_render_activity``.
    """
    data_root = _sync_run_files(tmp_path, "regen", _RUN_FILES, one_run=False)
    before = _tree(data_root)
    assert len(before) > 3
    synced = _only_page(data_root).read_text(encoding="utf-8")
    assert _dynamics_form_power_row(synced) == _FORM_POWER_ROW_B
    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)
    assert report.failures == ()
    assert len(report.written) == 1
    assert _tree(data_root) == before


def test_drain_of_the_run_pair_writes_the_page_and_assets_sync_writes(
    tmp_path: Path,
) -> None:
    """Req 5.1: the inbox drain and a plain sync of the same two files leave
    byte-identical data roots, the page carrying the Stryd file's form power.
    Mutation: ``drain`` plans with the reversed precedence.
    """
    synced, synced_text = _run_pair_page(tmp_path, "one-run")
    drained, drained_text = _run_pair_page(tmp_path, "drain")
    assert _dynamics_form_power_row(synced_text) == _FORM_POWER_ROW_A
    assert drained_text == synced_text
    assert drained.name == synced.name
    tree = _tree(synced.parent.parent)
    assert any(n.startswith("workouts/assets/") for n in tree)
    assert _tree(drained.parent.parent) == tree


def test_the_page_filename_and_uuid_are_those_the_healthfit_copy_alone_produces(
    tmp_path: Path,
) -> None:
    """Req 1.6: the composed trio keeps the HealthFit copy's identity.

    The filename and the ``uuid`` line are satisfied by the fixture whichever
    file is the base (all three files compute one stem, and only the HealthFit
    copy carries a session uuid), so they are a regression check only. What
    discriminates is the recorded base identity: ``source_kind``,
    ``source_elapsed_s``, ``source_distance_m`` and ``source_device`` equal the
    HealthFit-alone page's and differ from the Stryd-alone page's. Mutations:
    read the identity from the first extra's parse in ``_page_task``; rank the
    members with the reversed precedence.
    """
    healthfit, stryd_a, _stryd_b = merge.run_trio_fit_bytes()
    alone = tmp_path / "alone" / "data"
    alone.mkdir(parents=True)
    _sync(_stage(tmp_path / "alone" / "work", healthfit=healthfit), alone)
    stryd = tmp_path / "stryd" / "data"
    stryd.mkdir(parents=True)
    _sync(_stage(tmp_path / "stryd" / "work", stryd_a=stryd_a), stryd)
    composed = _sync_run_files(tmp_path, "trio", _RUN_FILES, one_run=True)

    alone_text = _only_page(alone).read_text(encoding="utf-8")
    stryd_text = _only_page(stryd).read_text(encoding="utf-8")
    composed_text = _only_page(composed).read_text(encoding="utf-8")
    keys = ("source_kind", "source_elapsed_s", "source_distance_m", "source_device")

    def recorded(text: str) -> list[str]:
        front = text.split("---\n", 2)[1]
        lines = [
            line
            for key in keys
            for line in front.splitlines()
            if line.startswith(f"{key}: ")
        ]
        assert len(lines) == len(keys), lines
        return lines

    assert recorded(composed_text) == recorded(alone_text)
    assert recorded(stryd_text) != recorded(alone_text)
    assert _only_page(composed).name == _only_page(alone).name
    assert _UUID_LINE.findall(composed_text) == _UUID_LINE.findall(alone_text)


def _ride_page(tmp_path: Path, label: str, *, copy_first: bool) -> str:
    garmin, copy = merge.ride_pair_fit_bytes()
    data_root = tmp_path / label / "data"
    data_root.mkdir(parents=True)
    work = tmp_path / label / "work"
    if copy_first:
        _sync(_stage(work / "a", copy=copy), data_root)
        _sync(_stage(work / "b", garmin=garmin), data_root)
    else:
        _sync(_stage(work / "both", garmin=garmin, copy=copy), data_root)
    return _only_page(data_root).read_text(encoding="utf-8")


@pytest.mark.parametrize("copy_first", [False, True], ids=["one-run", "copy-first"])
def test_the_ride_pair_page_shows_the_donated_heart_rate_and_states_power_alignment(
    tmp_path: Path, copy_first: bool
) -> None:
    """Req 5.1, 7.1: the Garmin original records no heart rate; the page's
    summary table and frontmatter show the average of the copy's donated values,
    and the copy's row of Channel Sources names the power alignment. Mutation:
    compute metrics from the base instead of the composition in ``_page_task``.
    """
    garmin, copy = merge.ride_pair_fit_bytes()
    alone = tmp_path / "alone" / "data"
    alone.mkdir(parents=True)
    _sync(_stage(tmp_path / "alone" / "work", garmin=garmin), alone)
    alone_text = _only_page(alone).read_text(encoding="utf-8")
    assert "\n| Avg HR | " not in alone_text
    assert "avg_hr_bpm" not in alone_text

    text = _ride_page(tmp_path, "pair", copy_first=copy_first)
    assert "| Avg HR | 140 bpm (max 189 bpm) |" in text
    assert "\navg_hr_bpm: 140\n" in text
    copy_row = (
        f"| `{_ref(copy)}` | extra | phone copy | Heart rate "
        "| 3 stretches: 3 by power |"
    )
    section = _CHANNEL_SOURCES.search(text)
    assert section is not None
    assert copy_row in section.group(0).splitlines()
    assert _table_refs(text) == [_ref(garmin), _ref(copy)]


# --- an aged page and the document-format version (5.1) ----------------------

_PRE_CHANNEL_MERGE_DOC_VERSION: int = 8
"""The document-format version `contract.DOC_VERSION` held on `main` before the
channel-merge spec's task 5.1 advanced it to 9 (see that constant's own
docstring: "Raised from ``8`` to ``9`` by channel-merge"). Named here, with its
provenance, rather than left as a bare literal in a test body; a run-pair page
aged to this version is one regeneration must bring current."""

_runner = CliRunner()
_CHART_LINK = re.compile(r"!\[[^\]]*\]\(([^)\s]+\.svg)\)")


def test_a_pre_channel_merge_run_pair_page_is_out_of_date_and_regen_restores_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 8.1, 8.2, 8.5: a run-pair page stamped with the previous version and
    lacking its Channel Sources section is reported out of date by ``check``;
    ``regen`` writes the section back, stamps the current version and rewrites
    the chart assets deleted beforehand; a second ``check`` reports it current.
    Mutations: leave ``DOC_VERSION`` at 8 (the precondition); make the audit's
    ``version < DOC_VERSION`` branch ``False`` (``check`` reports nothing); drop
    the section in ``_append_channel_sources``; make ``_write_assets`` write
    nothing."""
    # A forward assertion: a later sibling advance leaves it true.
    assert contract.DOC_VERSION > _PRE_CHANNEL_MERGE_DOC_VERSION

    monkeypatch.delenv("FITDOCS_DATA", raising=False)
    monkeypatch.setattr(
        "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
    )
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    data_root = tmp_path / "data"
    data_root.mkdir()
    healthfit, stryd = merge.run_pair_fit_bytes()
    source = _stage(tmp_path / "src", healthfit=healthfit, stryd=stryd)
    synced = _runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert synced.exit_code == 0, synced.output

    page = _only_page(data_root)
    synced_text = page.read_text(encoding="utf-8")
    assert f"\ndoc_version: {contract.DOC_VERSION}\n" in synced_text
    assert _table_refs(synced_text) == [_ref(healthfit), _ref(stryd)]

    # Age the page: drop the section (heading up to the next heading or the end)
    # and record the old version; delete the chart assets the first sync wrote
    # so that only regeneration can bring them back.
    section = _CHANNEL_SOURCES.search(synced_text)
    assert section is not None
    aged = synced_text[: section.start()] + synced_text[section.end() :]
    aged = aged.replace(
        f"\ndoc_version: {contract.DOC_VERSION}\n",
        f"\ndoc_version: {_PRE_CHANNEL_MERGE_DOC_VERSION}\n",
        1,
    )
    page.write_text(aged, encoding="utf-8")
    charts = [page.parent / rel for rel in _CHART_LINK.findall(synced_text)]
    assert charts and all(chart.is_file() for chart in charts)
    for chart in charts:
        chart.unlink()

    # The aging really happened: preconditions are live.
    assert "## Channel Sources" not in aged
    assert f"\ndoc_version: {_PRE_CHANNEL_MERGE_DOC_VERSION}\n" in aged
    assert f"\ndoc_version: {contract.DOC_VERSION}\n" not in aged
    assert not any(chart.exists() for chart in charts)

    stale = _runner.invoke(app, ["check", "--out", str(data_root)])
    assert stale.exit_code == 1, stale.output
    assert page.name in stale.output
    assert (
        f"doc_version is {_PRE_CHANNEL_MERGE_DOC_VERSION}, below the current"
        in stale.output
    )
    assert "No findings" not in stale.output

    restored = _runner.invoke(app, ["regen", "--out", str(data_root)])
    assert restored.exit_code == 0, restored.output

    text = _only_page(data_root).read_text(encoding="utf-8")
    assert text == synced_text
    assert _table_refs(text) == [_ref(healthfit), _ref(stryd)]
    assert f"\ndoc_version: {contract.DOC_VERSION}\n" in text
    assert all(chart.is_file() for chart in charts)

    current = _runner.invoke(app, ["check", "--out", str(data_root)])
    assert current.exit_code == 0, current.output
    assert "No findings" in current.output
