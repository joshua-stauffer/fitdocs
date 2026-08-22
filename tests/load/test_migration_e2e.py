"""End-to-end proof of the result-format migration lifecycle (task 6.2).

Every scenario drives :func:`fitdocs.load.engine.apply_load` over a real
temporary data root built through the actual sync pipeline (never a
hand-mocked payload string beyond the *synthetic v1 test data* from
``tests/load/test_render.py``, which is invented test data shaped to match
the v1 payload format used before the withdrawn methodology was withdrawn),
and asserts on both the returned
:class:`~fitdocs.load.engine.LoadReport` bucket AND whether the document's
bytes changed -- the task's own Observable -- per the requirements this module
pins: 7.4, 7.7, 11.2, 11.3, 11.4, 13.4, 13.5.

Deliberately its own module (task 6.2's boundary), disjoint from
``tests/load/test_arbitration_e2e.py`` (task 6.1) and from task 6.3's
command-surface/feature modules. It does not duplicate
``tests/load/test_engine.py``'s existing SUPERSEDED-region tests (task 4.1's
own boundary) -- each test below either drives a genuinely new combination
(a SUPERSEDED region recomputed with *nothing* registered; several
prior-format UNSUPPORTED documents refilled or re-rendered *together*, the
"twenty-four such documents" regression guard at data-root scale) or, for
bullet 3's restore case, uses a session that *raises* on any prompt rather
than one that merely declines non-interactively, so a wrongly-triggered
prompt fails loudly instead of being silently absorbed.
"""

from __future__ import annotations

from datetime import timedelta, timezone
from pathlib import Path

from fitdocs.athlete import load_athlete_inputs
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.load import registry
from fitdocs.load.docedit import (
    RegionState,
    classify_load_region,
    read_frontmatter_load,
    replace_load_region,
    strip_frontmatter_load,
)
from fitdocs.load.engine import DocLoadEntry, apply_load
from fitdocs.load.prompts import NonInteractiveSession
from fitdocs.sync import sync
from tests.fixtures import builder
from tests.load.conftest import ComputingCalculator
from tests.load.test_render import _V1_UNSUPPORTED_LINE, _V1_WITHDRAWN_COMPUTED_LINE

_TZ = timezone(timedelta(hours=-6))


# --- shared scaffolding (self-contained: no cross-import from sibling e2e
# modules, matching task 6.1's precedent of a fully independent module) ------


class _ServingTiles:
    """Inert basemap-tile source: the engine only cares about the load region."""

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: object) -> dict[object, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}  # type: ignore[union-attr]


_TILES: _ServingTiles = _ServingTiles()


def _build_data_root(tmp_path: Path, fixtures: dict[str, bytes]) -> Path:
    """Render ``fixtures`` into a temp data root via the real sync pipeline."""
    src = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    for name, data in fixtures.items():
        path = src / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    sync(src, data_root, athlete=load_athlete_inputs(data_root), tz=_TZ, tiles=_TILES)
    return data_root


def _docs(data_root: Path, needle: str) -> list[Path]:
    """Every workout document whose filename contains ``needle``, sorted."""
    candidates = (data_root / WORKOUTS_DIR).glob("*.md")
    return sorted(p for p in candidates if needle in p.name)


def _doc(data_root: Path, needle: str) -> Path:
    return _docs(data_root, needle)[0]


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


# A distinct-timestamp RUN fixture generator, so several documents can be
# rendered into the same data root without colliding filenames -- a thin call
# onto the shared ``builder.small_sport_fit_bytes`` (the same generator
# ``tests/load/test_arbitration_e2e.py`` uses for its own generic-sport
# fixtures).
_RUN_SPEED_MPS = 3.3
_RUN_HR_BASE = 120


def _run_fit_bytes(serial: int, *, day_offset: int = 0) -> bytes:
    return builder.small_sport_fit_bytes(
        serial,
        "running",
        timestamp_offset=day_offset * 86_400,
        speed_mps=_RUN_SPEED_MPS,
        hr_base=_RUN_HR_BASE,
    )


class _ScriptedSession:
    """A FIFO-queue :class:`InteractionSession` that RAISES on any prompt
    beyond what is queued -- including when *nothing at all* is queued, so a
    scenario claiming "no prompt" fails loudly (surfacing as a per-document
    failure) rather than a decline being silently absorbed. Mirrors
    ``tests/load/test_arbitration_e2e.py``'s ``_ScriptedSession``, built
    independently here (this module imports no test helper from that one).
    """

    def __init__(
        self,
        *,
        confirms: list[bool | None] | None = None,
        ints: list[int | None] | None = None,
        floats: list[float | None] | None = None,
    ) -> None:
        self._confirms = list(confirms or [])
        self._ints = list(ints or [])
        self._floats = list(floats or [])

    def _pop(self, queue: list[object], kind: str) -> object:
        if not queue:
            raise AssertionError(f"unexpected {kind} prompt: none queued")
        return queue.pop(0)

    def confirm(self, question: str, *, default: bool = True) -> bool | None:
        answer = self._pop(self._confirms, "confirm")  # type: ignore[arg-type]
        assert answer is None or isinstance(answer, bool)
        return answer

    def ask_int(
        self,
        question: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
        default: int | None = None,
    ) -> int | None:
        answer = self._pop(self._ints, "ask_int")  # type: ignore[arg-type]
        assert answer is None or isinstance(answer, int)
        return answer

    def ask_float(
        self,
        question: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
        default: float | None = None,
    ) -> float | None:
        answer = self._pop(self._floats, "ask_float")  # type: ignore[arg-type]
        assert answer is None or isinstance(answer, (int, float))
        return None if answer is None else float(answer)

    def choose(
        self,
        question: str,
        options: object,
        *,
        default_index: int | None = None,
    ) -> int | None:
        raise AssertionError("choose() not expected in this module's scenarios")

    def inform(self, message: str) -> None:
        pass


def _compute_run_session(*, level: int = 7) -> _ScriptedSession:
    """A full compute script for a placeholder RUN doc with an empty profile."""
    return _ScriptedSession(ints=[level], confirms=[True])


# =============================================================================
# Bullet 1: a prior-format COMPUTED region -- skipped byte-identical on an
# ordinary pass, recomputed into the current format when something supports
# it, or the honest unsupported state when nothing does (Req 11.2, 11.3,
# 11.4, 13.4, 13.5).
# =============================================================================


def test_prior_format_computed_document_skipped_then_recomputed_when_supported(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A recorded prior-format (v1, from the withdrawn calculator) ``computed``
    result is skipped byte-identical on an ordinary pass -- landing in *none* of
    computed/restored/unsupported, only ``skipped``, with a reason naming the
    recorded version and methodology (Req 11.2, 11.3, 13.4) -- and, once
    ``--recompute`` is explicitly requested with a supporting calculator
    registered, is recomputed from the archived source into the current
    format (Req 11.4, 13.5).

    Mutation caught: removing the ``RegionState.SUPERSEDED`` guard at
    ``engine.py``'s skip branch would route the ordinary pass into the compute
    path instead, changing the document's bytes and moving it out of
    ``skipped``; a mutation making the ordinary pass write to
    ``buckets.restored`` while leaving bytes unchanged would satisfy the byte
    check alone but is caught by the explicit bucket-disjointness assertions.
    """
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    superseded = replace_load_region(
        run.read_text(encoding="utf-8"), _V1_WITHDRAWN_COMPUTED_LINE
    )
    run.write_text(superseded, encoding="utf-8")
    assert classify_load_region(superseded).state is RegionState.SUPERSEDED
    before = run.read_bytes()

    ordinary_report = apply_load(data_root, session=NonInteractiveSession())

    assert run.read_bytes() == before  # not one byte changed
    rel = _rel(data_root, run)
    assert rel in _docs_of(ordinary_report.skipped)
    assert rel not in _docs_of(ordinary_report.computed)
    assert rel not in _docs_of(ordinary_report.restored)
    assert rel not in _docs_of(ordinary_report.unsupported)
    skip_entry = next(e for e in ordinary_report.skipped if e.doc == rel)
    assert "format version 1" in skip_entry.detail  # exact token, not bare digit
    assert "withdrawn-v1" in skip_entry.detail  # message-only, never a routed field

    recompute_report = apply_load(
        data_root, session=_compute_run_session(level=7), recompute=True
    )

    assert rel in _docs_of(recompute_report.computed)
    assert rel not in _docs_of(recompute_report.skipped)
    assert rel not in _docs_of(recompute_report.unsupported)
    after = run.read_text(encoding="utf-8")
    assert run.read_bytes() != before
    assert classify_load_region(after).state is RegionState.COMPUTED
    assert "withdrawn-v1" not in after
    assert read_frontmatter_load(after)["load_value"] == 70


def test_prior_format_computed_recompute_nothing_registered_is_unsupported(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    """The other half of bullet 1: with an explicit recomputation request but
    NO registered calculator, a recorded prior-format ``computed`` result does
    not stay protected -- it receives the honest unsupported state, exactly
    the ordinary arbitration/unsupported-state rules a placeholder document
    would get (Req 11.4, 13.5, 7.7). ``test_engine.py``'s own SUPERSEDED
    ``--recompute`` test drives this with a supporting calculator registered
    and never with an empty registry, so this is the genuinely new half.

    Mutation caught: routing a SUPERSEDED region straight to
    ``buckets.unsupported`` without actually re-arbitrating (e.g. skipping
    ``arbitrate``/``supports_activity`` for this state) would still land the
    document in ``report.unsupported``, but the byte content would not be the
    ordinary current-format unsupported rendering -- caught by asserting the
    classified state and the payload's recorded sport, not merely the bucket.
    """
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    superseded = replace_load_region(
        run.read_text(encoding="utf-8"), _V1_WITHDRAWN_COMPUTED_LINE
    )
    run.write_text(superseded, encoding="utf-8")
    assert classify_load_region(superseded).state is RegionState.SUPERSEDED
    before = run.read_bytes()
    assert registry.available() == ()

    report = apply_load(data_root, session=NonInteractiveSession(), recompute=True)

    rel = _rel(data_root, run)
    assert rel in _docs_of(report.unsupported)
    assert rel not in _docs_of(report.skipped)
    assert rel not in _docs_of(report.computed)
    assert run.read_bytes() != before
    classification = classify_load_region(run.read_text(encoding="utf-8"))
    assert classification.state is RegionState.UNSUPPORTED
    assert classification.payload is not None
    assert classification.payload.sport == "Run"
    after = run.read_text(encoding="utf-8")
    assert "withdrawn-v1" not in after
    assert read_frontmatter_load(after) == {}  # honest absence, no fabricated keys


# =============================================================================
# Bullet 2: several prior-format UNSUPPORTED documents in one data root -- the
# regression guard for the twenty-four such documents in the maintainer's own
# data root (Req 7.7, 11.2, 11.3, 13.4).
# =============================================================================

_MIGRATION_FIXTURES: dict[str, bytes] = {
    f"run-{i}.fit": _run_fit_bytes(4100 + i, day_offset=i) for i in range(3)
}


def _stamp_all_unsupported(data_root: Path, docs: list[Path]) -> None:
    for doc in docs:
        stamped = replace_load_region(
            doc.read_text(encoding="utf-8"), _V1_UNSUPPORTED_LINE
        )
        doc.write_text(stamped, encoding="utf-8")
        assert classify_load_region(stamped).state is RegionState.UNSUPPORTED


def test_prior_format_unsupported_documents_all_computed_once_a_supporter_is_registered(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """Several documents carrying a recorded prior-format ``unsupported``
    stamp record no result to protect (Req 7.7): with no recomputation
    request at all and a stub calculator registered that supports their
    sport, every one of them computes (Req 11.2, 11.3 -- there is nothing
    here for those to protect).

    Regression guard for the twenty-four such documents measured in the
    maintainer's own data root: freezing this state (treating a prior-format
    *unsupported* stamp the same as a prior-format *computed* one) would have
    made the retroactive-fill requirement unobservable for that entire
    existing corpus.

    Mutation caught: classifying a non-current ``"unsupported"``-stamped
    region as ``SUPERSEDED`` (collapsing the two prior-format cases) would
    route every document into ``report.skipped`` byte-identical instead of
    ``report.computed`` -- asserted over the *whole* set, not one document, so
    a mutation special-casing only the first-scanned document is still caught.
    """
    data_root = _build_data_root(tmp_path, _MIGRATION_FIXTURES)
    docs = _docs(data_root, "run-")
    assert len(docs) == 3
    _stamp_all_unsupported(data_root, docs)

    report = apply_load(
        data_root,
        session=_ScriptedSession(ints=[7], confirms=[True, True, True]),
    )

    expected = {_rel(data_root, doc) for doc in docs}
    assert expected <= _docs_of(report.computed)
    assert report.skipped == ()
    assert report.unsupported == ()
    assert report.failures == ()
    for doc in docs:
        assert classify_load_region(doc.read_text(encoding="utf-8")).state is (
            RegionState.COMPUTED
        )


def test_prior_format_unsupported_docs_nothing_registered_rerender_unsupported(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    """The mirror case, same data root shape: with NOTHING registered at all,
    every prior-format ``unsupported``-stamped document is re-rendered into
    the current format -- a no-op-equivalent honest state, not a frozen
    prior-format record -- and reported unsupported on the first pass; a
    second identical pass then writes nothing at all, for every document
    (Req 7.7, 13.4).

    Mutation caught: treating the non-current unsupported stamp as
    unconditionally protected (the SUPERSEDED branch, wrongly widened) would
    leave every document's bytes unchanged and land them in
    ``report.skipped`` instead of ``report.unsupported`` on the first pass;
    asserting the *whole-root* byte snapshot on the second pass (rather than
    one document) catches a mutation that only stabilizes some of the set.
    """
    data_root = _build_data_root(tmp_path, _MIGRATION_FIXTURES)
    docs = _docs(data_root, "run-")
    assert len(docs) == 3
    _stamp_all_unsupported(data_root, docs)
    assert registry.available() == ()

    first = apply_load(data_root, session=NonInteractiveSession())

    expected = {_rel(data_root, doc) for doc in docs}
    assert expected <= _docs_of(first.unsupported)
    assert first.skipped == ()
    assert first.computed == ()
    for doc in docs:
        region = classify_load_region(doc.read_text(encoding="utf-8"))
        assert region.state is RegionState.UNSUPPORTED
        # ``payload`` is populated only for a *current*-format region, so this is
        # the half that pins "re-renders them into the current format" rather
        # than merely "re-renders them": a prior-format unsupported stamp also
        # classifies UNSUPPORTED, so the state assertion alone holds before the
        # pass as well and survives a writer emitting the prior-format marker.
        assert region.payload is not None
    stable = _snapshot(data_root)

    second = apply_load(data_root, session=NonInteractiveSession())

    assert _snapshot(data_root) == stable  # byte-stable from the second pass onward
    assert second.unsupported == ()
    assert second.skipped == ()
    assert second.computed == ()


# =============================================================================
# Bullet 3: a regenerated computed document has its load frontmatter
# re-derived from the preserved section by a non-interactive pass, with no
# prompt and no recomputation (Req 7.4).
# =============================================================================


def test_regenerated_document_rederives_frontmatter_without_prompt_or_recompute(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A COMPUTED document whose managed load frontmatter keys were reset (a
    regen) has them restored from the preserved training-load section,
    without recomputation and without prompting (Req 7.4). The pass is driven
    by a session that RAISES on any prompt at all (empty queues), so a
    wrongly-triggered recompute or field re-collection surfaces as a per-doc
    failure rather than being silently absorbed by a decline.

    Mutation caught: if restore recomputed instead of re-deriving, the empty-
    queue session would raise on the first ``confirm``/``ask_int`` call,
    moving the document into ``report.failures``; if restore rewrote the
    training-load section itself, the region payload would differ from the
    one preserved before the simulated regen.
    """
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    apply_load(data_root, session=_compute_run_session(level=7))
    computed_text = run.read_text(encoding="utf-8")
    assert classify_load_region(computed_text).state is RegionState.COMPUTED
    region_before = classify_load_region(computed_text).payload

    # Simulate a regen: strip the managed frontmatter keys, keep the region.
    run.write_text(strip_frontmatter_load(computed_text), encoding="utf-8")
    assert read_frontmatter_load(run.read_text(encoding="utf-8")) == {}

    report = apply_load(data_root, session=_ScriptedSession())

    rel = _rel(data_root, run)
    assert rel in _docs_of(report.restored)
    assert report.computed == ()
    assert report.failures == ()
    restored_text = run.read_text(encoding="utf-8")
    fm = read_frontmatter_load(restored_text)
    assert fm["load_value"] == 70  # re-derived, not recomputed (level stayed 7)
    # the preserved training-load section content is unchanged by a restore
    assert classify_load_region(restored_text).payload == region_before
