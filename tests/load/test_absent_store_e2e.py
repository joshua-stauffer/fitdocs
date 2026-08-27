"""End-to-end proof of absent-store honesty and no rendered-output drift
(task 6.2, feature validation).

Half A drives :func:`fitdocs.load.engine.apply_load` non-interactively over a
real temporary data root -- built through the actual sync pipeline, exactly
like ``tests/load/test_benchmark_selection_e2e.py`` (task 6.1) -- that never
had an ``athlete.toml`` written into it at all. A stub calculator declares one
required athlete-wide benchmark field (maximum heart rate) so the pass
genuinely reaches every document and genuinely checks the store (Req 1.9,
8.6, 9.1, 9.2, 9.5).

Req 1.11 has two clauses, and this module covers neither -- this fixture's
data root has no ``athlete.toml`` at all, so there are no flat athlete-input
keys for a wrong implementation to disturb, and no assertion here can redden
on either clause.

The first clause -- flat athlete-input keys "remain readable with unchanged
meaning" -- is pinned elsewhere, by ``tests/test_athlete.py::
test_partial_file_maps_only_present_keys`` and
``tests/test_sync_e2e.py::test_athlete_file_present_renders_zone_strip_and_trimp_chip``,
both of which exercise a present ``athlete.toml`` with flat keys and both of
which redden under a mutation at ``src/fitdocs/athlete.py:123`` that replaces
the flat ``max_hr_bpm`` read with ``max_hr_bpm=None``.

The second clause -- flat keys "shall not be derived, overridden, or
reinterpreted from benchmarks" -- is not pinned anywhere in this suite. A
mutation at that same line (``src/fitdocs/athlete.py:123``) that prefers
``data["benchmarks"]["athlete"]["max_hr_bpm"][-1]["value"]`` over the flat
key when that entry is present, falling back to the flat key otherwise,
leaves all 2012 tests passing; neither cited test's fixture holds a flat
``max_hr_bpm`` alongside a ``benchmarks`` table, so neither can redden on
this clause. That gap is tracked at
``.kiro/queue/2026-07-27-req-1-11-prohibition-unpinned.md``.

Half B -- "no golden file edited in this feature's diff" -- is a property of
the whole feature branch's diff, not of one test run, and is discharged as a
mechanical branch-diff check rather than as a test here: ``git rev-parse
17ff340:tests/render`` equals ``git rev-parse HEAD:tests/render`` (and
likewise for ``tests/golden`` and ``tests/declaration_golden``), where
``17ff340`` is this branch's merge-base with ``main``
(``git merge-base main HEAD``) -- the branch point -- rather than ``main``
itself, which peers keep advancing mid-review; confirming those trees are
byte-identical to the branch point; the shipped golden-file document tests
(``tests/render/test_golden_docs.py`` et al.) already re-run unmodified as
part of ``uv run pytest``.
"""

from __future__ import annotations

from datetime import timedelta, timezone
from pathlib import Path

from fitdocs import Modality
from fitdocs.athlete import load_athlete_inputs
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.load import registry
from fitdocs.load.engine import DocLoadEntry, apply_load
from fitdocs.load.profile import PROFILE_FILENAME
from fitdocs.load.prompts import NonInteractiveSession
from fitdocs.load.types import (
    AthleteField,
    BenchmarkRef,
    Computed,
    LoadContext,
    LoadOutcome,
    LoadResult,
    NotComputed,
)
from fitdocs.sync import sync
from tests.fixtures import builder

_TZ = timezone(timedelta(hours=-6))

_MAX_HR_FIELD = AthleteField(
    key="benchmarks.athlete.max_hr_bpm",
    label="Maximum heart rate",
    kind="int",
    minimum=100,
    maximum=230,
    help_text="athlete-wide maximum heart rate in beats per minute",
    benchmark=BenchmarkRef(kind=BenchmarkKind.MAX_HR_BPM, discipline=None),
)


class _ServingTiles:
    """Inert basemap-tile source: this test never inspects rendered maps."""

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: object) -> dict[object, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}  # type: ignore[union-attr]


_TILES: _ServingTiles = _ServingTiles()


class _RequiresMaxHrCalculator:
    """Supports RUN and BIKE; requires the athlete-wide max-HR benchmark and
    resolves it against the activity's date, recording what it observed on the
    profile so the test can assert the store was genuinely queried rather than
    the pass having stopped short of ``compute``."""

    calculator_id = "stub-e2e-requires-max-hr"
    display_name = "Stub E2E Requires Max HR Calculator"
    supported_modalities = frozenset({Modality.RUN, Modality.BIKE})

    def __init__(self) -> None:
        self.observed: list[tuple[bool, bool]] = []
        """One (has_benchmark, resolved_is_none) pair appended per document
        processed -- a list, not a dict, because this fixture's two documents
        share the same activity date."""

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return (_MAX_HR_FIELD,)

    def compute(
        self,
        activity: object,
        metrics: object,
        profile: object,
        session: object,
        context: LoadContext,
    ) -> LoadOutcome:
        has = profile.has_benchmark(BenchmarkKind.MAX_HR_BPM, discipline=None)  # type: ignore[attr-defined]
        resolved = profile.benchmark(  # type: ignore[attr-defined]
            BenchmarkKind.MAX_HR_BPM, discipline=None, on=context.activity_date
        )
        self.observed.append((has, resolved is None))
        if resolved is None:
            return NotComputed(
                reason="max_hr_bpm never provided; nothing on file for the athlete"
            )
        # Unreachable in this test's fixture (no athlete.toml exists at all),
        # kept only so the outcome union above is honestly exhausted.
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=resolved.value,
                basis="unreachable",
                non_selected=(),
                flags=(),
                inputs_used=(),
                notes=(),
            )
        )


def _build_data_root(tmp_path: Path, fixtures: dict[str, bytes]) -> Path:
    """Render ``fixtures`` into a temp data root via the real sync pipeline,
    without ever writing an ``athlete.toml`` -- an absent file is not an
    error (Req 1.9): ``load_athlete_inputs`` returns ``None`` for it, and
    ``load_profile`` (what this module exercises, through ``apply_load``)
    yields an empty profile."""
    src = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    for name, data in fixtures.items():
        path = src / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    sync(src, data_root, athlete=load_athlete_inputs(data_root), tz=_TZ, tiles=_TILES)
    return data_root


def _rel(data_root: Path, doc: Path) -> str:
    return doc.relative_to(data_root).as_posix()


def _docs_of(entries: tuple[DocLoadEntry, ...]) -> set[str]:
    return {entry.doc for entry in entries}


def _snapshot(data_root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(data_root).as_posix(): p.read_bytes()
        for p in sorted(data_root.rglob("*"))
        if p.is_file()
    }


def test_absent_athlete_file_reports_every_document_not_computed_and_creates_nothing(
    tmp_path: Path,
) -> None:
    """A data root with no ``athlete.toml`` at all, driven non-interactively:
    every document is reported not computed with a (non-empty, reachable)
    reason, no file is created anywhere in the data root -- least of all
    ``athlete.toml`` itself -- and the pass exits without raising (Req 1.9,
    8.6, 9.1, 9.2, 9.5).
    """
    data_root = _build_data_root(
        tmp_path,
        {"run.fit": builder.run_fit_bytes(), "ride.fit": builder.ride_fit_bytes()},
    )
    profile_path = data_root / PROFILE_FILENAME
    assert not profile_path.exists(), (
        "sanity: the fixture pipeline itself must never create athlete.toml"
    )

    docs = sorted(
        p
        for p in (data_root / WORKOUTS_DIR).glob("*.md")
        if p.stem[:4].isdigit()  # excludes the sync-authored AGENTS.md
    )
    assert len(docs) == 2, f"expected exactly two workout documents, found {docs}"
    doc_rels = {_rel(data_root, d) for d in docs}

    before = _snapshot(data_root)

    calc = _RequiresMaxHrCalculator()
    registry.register(calc)
    try:
        # threshold-load ships a built-in that also declares RUN/BIKE support
        # (Req 1.1), so both documents would otherwise be genuinely ambiguous
        # between it and this stub; force this stub's id so the scenario under
        # test -- this calculator's own genuinely-empty-store observation --
        # stays deterministic regardless of what else is registered.
        report = apply_load(
            data_root,
            session=NonInteractiveSession(),
            calculator_id=calc.calculator_id,
        )
    finally:
        registry.unregister(calc.calculator_id)

    # --- the pass reached and scored every document: both are reported
    # skipped-with-reason, none computed, none unsupported, none failed ------
    assert _docs_of(report.skipped) == doc_rels
    assert report.computed == ()
    assert report.unsupported == ()
    assert report.failures == ()
    assert report.restored == ()

    for entry in report.skipped:
        assert entry.detail  # every reported document carries a reason
        assert "never provided" in entry.detail

    # --- the calculator itself observed a genuinely empty store for both
    # documents -----------------------------------------------------------
    assert len(calc.observed) == 2
    for has, resolved_is_none in calc.observed:
        assert has is False
        assert resolved_is_none is True

    # --- nothing was created: athlete.toml still does not exist, and no
    # byte anywhere in the data root changed ----------------------------------
    assert not profile_path.exists()
    assert _snapshot(data_root) == before
