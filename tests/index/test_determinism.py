"""End-to-end index row determinism across ingestion and build paths."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date, timedelta, timezone
from pathlib import Path

import pytest

from fitdocs.contract import is_workout_document
from fitdocs.docio import read_frontmatter
from fitdocs.index import corpus, derive, registry
from fitdocs.index.bookkeeping import IndexMeta
from fitdocs.index.build import run_index_command
from fitdocs.index.core.computed import CORE_COMPUTED
from fitdocs.index.core.documents import CORE_DOCUMENTS
from fitdocs.index.fingerprint import athlete_fingerprint
from fitdocs.index.handoff import HandoffCollector
from fitdocs.index.schema import SCHEMA_VERSION, ResolvedTable, TableSpec
from fitdocs.index.store import (
    create_index,
    create_schema,
    duckdb_version,
    open_index,
    read_bookkeeping,
    write_meta,
)
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.load import registry as load_registry
from fitdocs.load.engine import apply_load
from fitdocs.load.prompts import NonInteractiveSession
from fitdocs.load.types import (
    AthleteField,
    Computed,
    InteractionSession,
    LoadContext,
    LoadOutcome,
    LoadResult,
    ProfileView,
    QualityFlag,
)
from fitdocs.metrics.types import AthleteInputs, DerivedMetrics, ZoneSpec
from fitdocs.model import Activity, Modality
from fitdocs.sync import sync
from fitdocs.version import tool_version
from tests.fixtures import builder, merge
from tests.index.conftest import _SyntheticTiles

_TODAY = date(2044, 5, 6)
_ATHLETE = AthleteInputs(
    ftp_watts=237.5,
    resting_hr_bpm=53,
    max_hr_bpm=194,
    hr_zones=ZoneSpec((111.0, 139.0, 177.0)),
    power_zones=ZoneSpec((121.5, 201.25, 260.75)),
    pace_zones=ZoneSpec((245.0, 333.0, 499.0)),
)


class _DeterministicLoadCalculator:
    calculator_id = "index-determinism-fixture"
    display_name = "Index determinism fixture"
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
            LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=42.25,
                basis="synthetic selected channel",
                non_selected=(),
                flags=(
                    QualityFlag(
                        key="synthetic-signal",
                        label="Synthetic signal",
                        verdict="detected",
                        detail="Synthetic fixture verdict",
                    ),
                ),
                inputs_used=(),
                notes=(),
            )
        )


@contextmanager
def _fixture_calculator() -> Iterator[None]:
    previous = dict(load_registry._REGISTRY)
    load_registry._REGISTRY.clear()
    load_registry.register(_DeterministicLoadCalculator())
    try:
        yield
    finally:
        load_registry._REGISTRY.clear()
        load_registry._REGISTRY.update(previous)


def _source_groups() -> tuple[tuple[str, tuple[tuple[str, bytes], ...]], ...]:
    healthfit_run, stryd_run = merge.run_pair_fit_bytes()
    garmin_ride, healthfit_ride = merge.ride_pair_fit_bytes()
    return (
        (
            "run",
            (("healthfit.fit", healthfit_run), ("stryd.fit", stryd_run)),
        ),
        (
            "ride",
            (("garmin.fit", garmin_ride), ("healthfit.fit", healthfit_ride)),
        ),
        ("strength", (("strength.fit", builder.strength_fit_bytes()),)),
        (
            "hike",
            (("hike.fit", builder.small_sport_fit_bytes(8101, "hiking")),),
        ),
        (
            "walk",
            (
                (
                    "walk.fit",
                    builder.small_sport_fit_bytes(
                        8102, "walking", timestamp_offset=8_640_000
                    ),
                ),
            ),
        ),
    )


def _populate_corpus(
    tmp_path: Path,
    *,
    group_order: Sequence[str] | None = None,
    reverse_file_creation: bool = False,
    handoff: HandoffCollector | None = None,
) -> tuple[Path, tuple[str, ...]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    data_root = tmp_path / "data"
    data_root.mkdir()
    groups = dict(_source_groups())
    names = tuple(group_order or groups)
    assert set(names) == set(groups)
    written: list[str] = []
    for group_name in names:
        source = tmp_path / f"source-{group_name}"
        source.mkdir()
        files = groups[group_name]
        creation = tuple(reversed(files)) if reverse_file_creation else files
        for filename, payload in creation:
            (source / filename).write_bytes(payload)
        report = sync(
            source,
            data_root,
            athlete=_ATHLETE,
            tz=timezone(timedelta(hours=-6)),
            tiles=_SyntheticTiles(),
            on_rendered=None if handoff is None else handoff.add,
        )
        assert report.failures == ()
        written.extend(report.written)

    with _fixture_calculator():
        load_report = apply_load(
            data_root,
            session=NonInteractiveSession(),
            calculator_id=_DeterministicLoadCalculator.calculator_id,
        )
    assert load_report.failures == ()
    pages = tuple(
        path
        for path in sorted((data_root / WORKOUTS_DIR).glob("*.md"))
        if is_workout_document(read_frontmatter(path))
    )
    assert len(pages) == 5
    assert len(set(written)) == 5
    assert set(written) == {path.relative_to(data_root).as_posix() for path in pages}
    return data_root, tuple(written)


def _create_empty_index(database: Path, data_root: Path) -> None:
    tables = registry.registered_tables()
    with create_index(database) as connection:
        create_schema(connection, tables)
        write_meta(
            connection,
            IndexMeta(
                schema_version=SCHEMA_VERSION,
                fitdocs_version=tool_version(),
                duckdb_version=duckdb_version(),
                data_root=str(data_root.resolve()),
                athlete_fingerprint=athlete_fingerprint(None),
            ),
        )


def _refresh(
    database: Path,
    data_root: Path,
    *,
    handoff: HandoffCollector | None = None,
) -> None:
    from fitdocs.index.refresh import RefreshInputs, reconcile

    with open_index(database, read_only=False) as connection:
        bookkeeping = read_bookkeeping(connection)
        assert bookkeeping is not None
        reconcile(
            connection,
            bookkeeping,
            RefreshInputs(data_root, _ATHLETE, handoff, _TODAY, None),
        )


def _core_rows(database: Path) -> dict[str, tuple[tuple[object, ...], ...]]:
    tables: list[TableSpec] = [
        table
        for producer in (CORE_DOCUMENTS, CORE_COMPUTED)
        for table in producer.tables
    ]
    rows: dict[str, tuple[tuple[object, ...], ...]] = {}
    empty_tables: list[str] = []
    trivial_tables: list[str] = []
    with open_index(database, read_only=True) as connection:
        for table in tables:
            result = connection.execute(
                f'SELECT * FROM "{table.name}" ORDER BY ALL'
            ).fetchall()
            if not result:
                empty_tables.append(table.name)
            elif not any(
                value is not None and value != "" for row in result for value in row[1:]
            ):
                trivial_tables.append(table.name)
            rows[table.name] = tuple(result)
    assert empty_tables == [], f"core producer tables must be nonempty: {empty_tables}"
    assert trivial_tables == [], (
        f"core producer rows must be substantive: {trivial_tables}"
    )
    return rows


def _make_index_for_root(
    database: Path,
    data_root: Path,
    *,
    handoff: HandoffCollector | None = None,
) -> dict[str, tuple[tuple[object, ...], ...]]:
    _create_empty_index(database, data_root)
    _refresh(database, data_root, handoff=handoff)
    return _core_rows(database)


def test_core_rows_are_equal_for_all_five_indexing_paths(
    tmp_path: Path,
    core_registry: tuple[ResolvedTable, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff = HandoffCollector()
    template_root, normal_creation = _populate_corpus(
        tmp_path / "template", handoff=handoff
    )
    assert handoff.retained_samples > 0
    handed_speed_metrics: list[float] = []
    for scanned_page in corpus.scan_workout_pages(template_root).pages:
        handed = handoff.take(scanned_page.page_key, scanned_page.sources)
        assert handed is not None
        speed = handed.metrics.avg_speed_mps
        if speed is not None:
            handed_speed_metrics.append(speed)
    assert any(speed != round(speed) for speed in handed_speed_metrics)

    # Path-order incremental indexing: keep the archive complete, then add the
    # rendered workout documents to the scan one at a time in their exact path
    # order and reconcile after each addition.
    incremental_root = tmp_path / "incremental-data"
    shutil.copytree(template_root, incremental_root)
    incremental_pages = tuple(sorted((incremental_root / WORKOUTS_DIR).glob("*.md")))
    parked = tuple((page, page.read_bytes()) for page in incremental_pages)
    for page, _payload in parked:
        page.unlink()
    incremental_database = tmp_path / "incremental.duckdb"
    _create_empty_index(incremental_database, incremental_root)
    for page, payload in parked:
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_bytes(payload)
        _refresh(incremental_database, incremental_root)
    path_order_rows = _core_rows(incremental_database)

    # Reverse creation order and deliberately shuffled mtimes on an otherwise
    # byte-identical corpus.
    reverse_root, reverse_creation = _populate_corpus(
        tmp_path / "reverse",
        group_order=tuple(reversed(tuple(dict(_source_groups())))),
        reverse_file_creation=True,
    )
    assert reverse_creation == tuple(reversed(normal_creation))
    reverse_pages = tuple(sorted((reverse_root / WORKOUTS_DIR).glob("*.md")))
    for index, page in enumerate(reversed(reverse_pages), start=1):
        stamp = 1_700_000_000 + index * 10_000
        os.utime(page, (stamp, stamp))
    reverse_database = tmp_path / "reverse.duckdb"
    reverse_rows = _make_index_for_root(reverse_database, reverse_root)

    handoff_root = tmp_path / "handoff-data"
    shutil.copytree(template_root, handoff_root)
    handoff_database = tmp_path / "handoff.duckdb"
    original_derive = derive.derive_page
    handoff_derivations: list[tuple[object, ...]] = []
    rederived_derivations: list[tuple[object, ...]] = []

    def observe_derive(
        data_root: Path, sources: Sequence[str], athlete: AthleteInputs | None
    ) -> object:
        call = (data_root, tuple(sources), athlete)
        if data_root == handoff_root:
            handoff_derivations.append(call)
        elif data_root == derived_root:
            rederived_derivations.append(call)
        return original_derive(data_root, sources, athlete)

    derived_root = tmp_path / "rederived-data"
    shutil.copytree(template_root, derived_root)
    with monkeypatch.context() as observer:
        observer.setattr(derive, "derive_page", observe_derive)
        handoff_rows = _make_index_for_root(
            handoff_database, handoff_root, handoff=handoff
        )
        assert handoff_derivations == []

        derived_database = tmp_path / "rederived.duckdb"
        derived_rows = _make_index_for_root(derived_database, derived_root)
        assert len(rederived_derivations) == 5
    assert derive.derive_page is original_derive

    rebuild_root = tmp_path / "rebuild-data"
    shutil.copytree(template_root, rebuild_root)
    index_base = tmp_path / "index-cache"
    home = tmp_path / "home"
    home.mkdir()
    report = run_index_command(
        rebuild_root,
        environ={"FITDOCS_INDEX_DIR": str(index_base)},
        home=home,
        athlete=_ATHLETE,
        today=_TODAY,
        rebuild=True,
        progress=None,
    )
    assert report.result is not None
    assert report.outcome.value == "built"
    from fitdocs.index.location import resolve_index_location

    rebuild_database = resolve_index_location(
        rebuild_root, {"FITDOCS_INDEX_DIR": str(index_base)}, home
    ).database
    rebuild_rows = _core_rows(rebuild_database)

    for label, rows in (
        ("reverse creation", reverse_rows),
        ("handover", handoff_rows),
        ("re-derivation", derived_rows),
        ("rebuild", rebuild_rows),
    ):
        assert rows == path_order_rows, f"core rows differ for {label}"
