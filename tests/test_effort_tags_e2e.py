"""End-to-end effort-tag round trip through the installed CLI (task 5.2).

Drives the installed entry point through :class:`typer.testing.CliRunner`
(never the engine functions directly, mirroring ``tests/test_cli_check.py``
and ``tests/load/test_cli_load.py``), fully offline: the tile-fetch seam
(``fitdocs.tiles._default_fetch``) is monkeypatched to return deterministic
bytes, exactly as those two modules do, so no real basemap fetch is ever
attempted. On top of that, every CLI invocation in this module additionally
runs under ``socket.socket`` replaced with the ``_no_socket`` guard
``tests.test_determinism`` uses (also reused, unmodified, by
``tests.test_wiki_contract_e2e``'s own full round trip) -- so "no socket
opened" is asserted mechanically here, not merely implied by the mocked seam.

Covers requirements 1.2, 2.7, 2.8, 3.4, 4.1, 4.2, 4.3, 4.6, 4.8 (design:
SurfacePins, E2E / CLI Tests): a hand-added, quoted-wikilink effort tag and a
hand-edited ``notes`` region survive ``sync --force`` and ``regen``
byte-for-byte with ``check`` exiting 0 after each; the ``load`` pass, forced
onto a real document *edit* with a stub calculator requiring no athlete
input (mirroring ``tests/load/test_cli_load.py``'s ``_FieldFreeCalculator``
pattern), leaves the tag and the note byte-identical across that edit too
(Req 4.3) -- asserted only after first confirming the edit actually
happened (``load_value:`` present where it was absent before), since an
edit the load pass *skips* proves nothing about preservation. The tagged
document's body (everything after the closing frontmatter fence) equals an
otherwise-identical untagged render's body; the same survival holds on a
strength-modality fixture; two consecutive ``regen`` runs are byte-identical;
a malformed tag makes ``check`` exit 1 with the new finding kind while
``regen`` still exits 0, prints a warning whose ``Warnings`` count is
nonzero (zero on a clean baseline regen of the same document) and whose
listing pairs the document's own path with a detail naming the offending
key, and preserves the lines; and deleting the document and regenerating
yields a fresh, untagged document with no warning naming an effort key.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest
from typer.testing import CliRunner

from fitdocs import Modality
from fitdocs.cli import app
from fitdocs.contract import DOC_BANNER
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.docmerge import begin_marker, end_marker, extract_regions
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.load import registry as load_registry
from fitdocs.load.types import (
    Activity,
    AthleteField,
    Computed,
    DerivedMetrics,
    InteractionSession,
    LoadContext,
    LoadOutcome,
    LoadResult,
    ProfileView,
)
from tests import test_confinement
from tests.fixtures import builder
from tests.test_determinism import _no_socket

runner = CliRunner()

# No pinned timezone here: unlike tests that call the engine's sync()/regen()
# directly, the CLI resolves the *system* local timezone itself
# (cli._local_tz()), so a test-local tz constant would be unused and
# misleading. Document stems are found by substring (see _doc), not by an
# exact, tz-derived stem, so this module never needs one.

_STUB_CALCULATOR_ID = "stub-effort-tags-e2e"

_WARNINGS_ROW_RE = re.compile(r"Warnings\D*(\d+)")


class _FieldFreeStubCalculator:
    """A calculator requiring no athlete input, so a forced ``--calculator``
    reaches ``Computed`` under ``CliRunner``'s non-interactive session
    (mirrors ``tests/load/test_cli_load.py::_FieldFreeCalculator``, used
    there under its own ``--calculator`` (Req 8.4) test). Supports every
    modality so the same stub drives both the run and the strength fixture
    below.
    """

    calculator_id = _STUB_CALCULATOR_ID
    display_name = "Effort-Tags E2E Stub Calculator"
    supported_modalities = frozenset(Modality)

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=42.0,
                basis="stub e2e basis",
                non_selected=(),
                flags=(),
                inputs_used=(),
                notes=(),
            )
        )


_VALID_TAG = (
    "effort: race\n"
    "effort_distance_m: 42195\n"
    "effort_time_s: 10692\n"
    'effort_event: "[[Boston Marathon 2024]]"\n'
)
_MALFORMED_TAG = (
    "effort: race\n"
    "effort_distance_m: 42195\n"
    "effort_time_s: abc\n"
    'effort_event: "[[Boston Marathon 2024]]"\n'
)
_NOTE = "Felt strong through mile 20; held the same pace to the finish."
_STRENGTH_NOTE = "Left knee felt a little tight on the last set of squats."


@pytest.fixture(autouse=True)
def _offline_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every ``sync``/``regen`` network-free (mirrors ``test_cli_check.py``).

    This is the offline mechanism this module uses: the tile *fetch* seam is
    monkeypatched, never a settings file disabling tiles.
    """
    monkeypatch.setattr(
        "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
    )


def _put(source_dir: Path, name: str, data: bytes) -> Path:
    source_dir.mkdir(parents=True, exist_ok=True)
    path = source_dir / name
    path.write_bytes(data)
    return path


def _doc(data_root: Path, needle: str) -> Path:
    """The single workout document whose filename contains ``needle``."""
    return next(
        p
        for p in (data_root / WORKOUTS_DIR).glob("*.md")
        if needle in p.name and p.name != DECLARATION_FILENAME
    )


def _add_frontmatter_key(text: str, line: str) -> str:
    """Insert an extra frontmatter line just before the closing ``---`` fence
    (mirrors ``tests/test_sync.py::_add_frontmatter_key`` / the design's
    placement rule: after every managed key, before the closing fence)."""
    first_idx = text.index("---\n")
    second_idx = text.index("---\n", first_idx + len("---\n"))
    return text[:second_idx] + line + text[second_idx:]


def _replace_tag(text: str, old: str, new: str) -> str:
    assert old in text, "the tag under replacement must already be present"
    return text.replace(old, new, 1)


def _set_region(text: str, region_id: str, content: str) -> str:
    """Replace a preserved region's inner content (mirrors ``tests/test_sync.py``)."""
    begin, end = begin_marker(region_id), end_marker(region_id)
    start = text.index(begin)
    finish = text.index(end) + len(end)
    return text[:start] + f"{begin}\n{content}\n{end}" + text[finish:]


def _warnings_count(output: str) -> int:
    """The ``Warnings`` summary-table row's count, parsed from CLI ``output``
    (robust to the table's box-drawing/spacing rather than depending on it)."""
    match = _WARNINGS_ROW_RE.search(output)
    assert match, f"no Warnings row found in output: {output!r}"
    return int(match.group(1))


@contextlib.contextmanager
def _forced_stub_calculator() -> Iterator[None]:
    """Register :class:`_FieldFreeStubCalculator` as the *only* calculator for
    the duration of the block, then restore the registry exactly as it was
    (mirrors ``tests/load/conftest.py::isolated_registry`` + its
    per-calculator fixtures, reimplemented locally since those fixtures are
    scoped to ``tests/load/`` by pytest's conftest hierarchy and are not
    visible here)."""
    saved = dict(load_registry._REGISTRY)
    load_registry._REGISTRY.clear()
    load_registry.register(_FieldFreeStubCalculator())
    try:
        yield
    finally:
        load_registry._REGISTRY.clear()
        load_registry._REGISTRY.update(saved)


def _body(text: str) -> str:
    """Everything after ``DOC_BANNER`` -- the closing-fence-onward document body
    (``_assemble`` in ``render/views.py`` builds
    ``f"{build_frontmatter(ctx)}\\n{DOC_BANNER}\\n\\n{body}\\n"``, so slicing on
    the banner isolates the body regardless of frontmatter length)."""
    return text.split(DOC_BANNER, 1)[1]


# --- 2.7: the tag renders no consequence in the body --------------------------


def test_tagged_document_body_equals_untagged_render_body(tmp_path: Path) -> None:
    """A hand-added, forcibly-resynced effort tag changes only the frontmatter;
    the body an otherwise-identical untagged document renders is unchanged."""
    with mock.patch("socket.socket", _no_socket):
        untagged_root = tmp_path / "untagged"
        untagged_root.mkdir()
        untagged_source = tmp_path / "untagged-src"
        _put(untagged_source, "run.fit", builder.run_fit_bytes())
        result = runner.invoke(
            app, ["sync", str(untagged_source), "--out", str(untagged_root)]
        )
        assert result.exit_code == 0, result.output
        untagged_body = _body(_doc(untagged_root, "run").read_text(encoding="utf-8"))

        tagged_root = tmp_path / "tagged"
        tagged_root.mkdir()
        tagged_source = tmp_path / "tagged-src"
        _put(tagged_source, "run.fit", builder.run_fit_bytes())
        result = runner.invoke(
            app, ["sync", str(tagged_source), "--out", str(tagged_root)]
        )
        assert result.exit_code == 0, result.output
        doc = _doc(tagged_root, "run")
        doc.write_text(
            _add_frontmatter_key(doc.read_text(encoding="utf-8"), _VALID_TAG),
            encoding="utf-8",
        )
        result = runner.invoke(
            app,
            ["sync", str(tagged_source), "--out", str(tagged_root), "--force"],
        )
        assert result.exit_code == 0, result.output
        tagged_text = doc.read_text(encoding="utf-8")
        assert _VALID_TAG in tagged_text

        assert _body(tagged_text) == untagged_body


# --- 3.4, 4.1, 4.2, 4.3, 4.6: carry through sync --force / regen / load -------


def _survives_sync_regen_load(
    tmp_path: Path, fixture_name: str, fixture_bytes: bytes, note: str
) -> None:
    """Sync ``fixture_bytes`` into an empty data root, hand-add a valid tag
    (quoted wikilink event) and edit ``notes``, then run ``sync --force`` and
    ``regen``: after each, the tag lines and the note survive byte-for-byte
    and ``check`` exits 0. Finally, force the load pass to actually *edit*
    the document (Req 4.3 is about what the load pass leaves alone when it
    fills the load region -- a pass that only skips proves nothing) and
    re-check the same survival across that edit."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    source = tmp_path / "src"
    _put(source, fixture_name, fixture_bytes)

    with mock.patch("socket.socket", _no_socket):
        result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
        assert result.exit_code == 0, result.output

        doc = _doc(data_root, fixture_name.split(".")[0])
        edited = _add_frontmatter_key(doc.read_text(encoding="utf-8"), _VALID_TAG)
        edited = _set_region(edited, "notes", note)
        doc.write_text(edited, encoding="utf-8")

        for args in (
            ["sync", str(source), "--out", str(data_root), "--force"],
            ["regen", "--out", str(data_root)],
        ):
            result = runner.invoke(app, args)
            assert result.exit_code == 0, result.output
            rewritten = doc.read_text(encoding="utf-8")
            assert _VALID_TAG in rewritten
            assert extract_regions(rewritten)["notes"] == note

            check_result = runner.invoke(app, ["check", "--out", str(data_root)])
            assert check_result.exit_code == 0, check_result.output

        # Precondition (falsity in the starting state): no load value has
        # been filled yet -- the only shipped calculator (``threshold``)
        # declares required athlete inputs and there is no ``athlete.toml``
        # here, so the load passes sync/regen already ran above skipped this
        # document and were no-ops on the load region.
        before_load = doc.read_text(encoding="utf-8")
        assert "load_value:" not in before_load

        with _forced_stub_calculator():
            load_result = runner.invoke(
                app,
                [
                    "load",
                    "--out",
                    str(data_root),
                    "--calculator",
                    _STUB_CALCULATOR_ID,
                ],
            )
        assert load_result.exit_code == 0, load_result.output
        assert f"[{_STUB_CALCULATOR_ID}]" in load_result.output

        # Postcondition: the load pass actually edited the document this
        # time (the precondition above was false; now it is true) -- only
        # now does byte-identity of the tag and the note across that edit
        # mean anything.
        after_load = doc.read_text(encoding="utf-8")
        assert "load_value:" in after_load
        assert _VALID_TAG in after_load
        assert extract_regions(after_load)["notes"] == note

        check_result = runner.invoke(app, ["check", "--out", str(data_root)])
        assert check_result.exit_code == 0, check_result.output


def test_run_fixture_tag_and_note_survive_sync_regen_load(tmp_path: Path) -> None:
    _survives_sync_regen_load(tmp_path, "run.fit", builder.run_fit_bytes(), _NOTE)


def test_strength_fixture_tag_and_note_survive_sync_regen_load(
    tmp_path: Path,
) -> None:
    """2.8: the tag is accepted on any modality, here a strength session."""
    _survives_sync_regen_load(
        tmp_path, "strength.fit", builder.strength_fit_bytes(), _STRENGTH_NOTE
    )


# --- 4.6: regenerating twice over an unchanged tag is byte-identical ----------


def test_regenerating_twice_over_a_tagged_document_is_byte_identical(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    source = tmp_path / "src"
    _put(source, "run.fit", builder.run_fit_bytes())

    with mock.patch("socket.socket", _no_socket):
        result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
        assert result.exit_code == 0, result.output

        doc = _doc(data_root, "run")
        edited = _add_frontmatter_key(doc.read_text(encoding="utf-8"), _VALID_TAG)
        edited = _set_region(edited, "notes", _NOTE)
        doc.write_text(edited, encoding="utf-8")

        first = runner.invoke(app, ["regen", "--out", str(data_root)])
        assert first.exit_code == 0, first.output
        first_bytes = doc.read_bytes()

        second = runner.invoke(app, ["regen", "--out", str(data_root)])
        assert second.exit_code == 0, second.output
        second_bytes = doc.read_bytes()

        assert first_bytes == second_bytes


# --- 3.4: malformed tag -- check exits 1 with the new kind, regen exits 0 ----


def test_malformed_tag_fails_check_but_regen_still_succeeds_and_preserves(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    source = tmp_path / "src"
    _put(source, "run.fit", builder.run_fit_bytes())

    with mock.patch("socket.socket", _no_socket):
        result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
        assert result.exit_code == 0, result.output

        # Falsity-in-the-starting-state baseline: a plain regen of the
        # still-untagged document warns about nothing at all -- so a later
        # nonzero Warnings count, and a warning naming this document, are
        # both genuine observations rather than an ever-present artifact of
        # a successful regen (which always lists the document under
        # "Written:" regardless of any warning).
        baseline_regen = runner.invoke(app, ["regen", "--out", str(data_root)])
        assert baseline_regen.exit_code == 0, baseline_regen.output
        assert _warnings_count(baseline_regen.output) == 0

        doc = _doc(data_root, "run")
        doc_ref = f"{WORKOUTS_DIR}/{doc.name}"
        tagged = _add_frontmatter_key(doc.read_text(encoding="utf-8"), _VALID_TAG)
        doc.write_text(tagged, encoding="utf-8")
        assert _VALID_TAG in doc.read_text(encoding="utf-8")

        # Replace the valid tag with a malformed one.
        malformed = _replace_tag(
            doc.read_text(encoding="utf-8"), _VALID_TAG, _MALFORMED_TAG
        )
        doc.write_text(malformed, encoding="utf-8")

        check_result = runner.invoke(app, ["check", "--out", str(data_root)])
        assert check_result.exit_code == 1
        # Distinctive to the new finding kind's detail and remedy (matches
        # tests/test_cli_check.py's own fragments for this finding).
        assert "malformed effort tag" in check_result.output
        assert (
            "effort_time_s: must be a positive number of seconds" in check_result.output
        )
        assert "correct the named effort key(s) by hand" in check_result.output

        regen_result = runner.invoke(app, ["regen", "--out", str(data_root)])
        assert regen_result.exit_code == 0, regen_result.output
        # The count itself changed from the baseline (0 -> 1) -- not merely
        # present, which an untagged regen's own "Written:" listing would
        # satisfy regardless of any warning.
        assert _warnings_count(regen_result.output) == 1
        # The warning listing pairs THIS document's own path with a detail
        # naming the offending key, adjacently -- not just "doc.name appears
        # somewhere in the output" (it always does, via "Written:").
        assert f"  {doc_ref}\n    carries an effort tag" in regen_result.output
        assert (
            "not in effect until corrected: "
            "effort_time_s: must be a positive number of seconds"
        ) in regen_result.output

        preserved = doc.read_text(encoding="utf-8")
        assert _MALFORMED_TAG in preserved


# --- 4.8: deleting the document, then regen, yields a fresh untagged doc -----


def test_deleted_document_regenerates_untagged_with_no_warning(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    source = tmp_path / "src"
    _put(source, "run.fit", builder.run_fit_bytes())

    with mock.patch("socket.socket", _no_socket):
        result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
        assert result.exit_code == 0, result.output

        doc = _doc(data_root, "run")
        tagged = _add_frontmatter_key(doc.read_text(encoding="utf-8"), _VALID_TAG)
        doc.write_text(tagged, encoding="utf-8")
        assert "effort:" in doc.read_text(encoding="utf-8")

        doc.unlink()
        assert not doc.exists()

        regen_result = runner.invoke(app, ["regen", "--out", str(data_root)])
        assert regen_result.exit_code == 0, regen_result.output
        assert "effort" not in regen_result.output

        fresh = _doc(data_root, "run")
        fresh_text = fresh.read_text(encoding="utf-8")
        assert not any(line.startswith("effort") for line in fresh_text.splitlines())

        check_result = runner.invoke(app, ["check", "--out", str(data_root)])
        assert check_result.exit_code == 0, check_result.output


# --- confinement: this feature registered no new writing entry point --------


def test_no_new_writing_entry_point_was_registered() -> None:
    """The four registered writing entry points (Req 7.5/7.6, wiki-contract)
    are unchanged by this feature -- no fifth entry point was added.

    The generic per-entry-point confinement guard itself lives, unduplicated,
    in ``tests/test_confinement.py`` (reused there, not reimplemented here);
    this pins only that the *registry* this feature could have widened still
    names exactly the four entry points that predate it.
    """
    assert {
        entry_point.id for entry_point in test_confinement.WRITING_ENTRY_POINTS
    } == {"sync", "regen", "load", "drain"}
