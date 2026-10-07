"""Corpus-level benchmark rows follow the athlete profile's own rule."""

from __future__ import annotations

import dataclasses
from datetime import date, timedelta
from pathlib import Path
from typing import Any, get_type_hints

import pytest

from fitdocs import Sport
from fitdocs.benchmarks import Benchmark, BenchmarkKind, BenchmarkSet
from fitdocs.index.derived.benchmarks import (
    BENCHMARK_PERIODS_TABLE,
    BENCHMARK_PRODUCER,
    BENCHMARKS_TABLE,
    UNIT_TOKENS,
    BenchmarkProducer,
    InForcePeriod,
    in_force_periods,
)
from fitdocs.index.derived.inputs import digest, file_digest
from fitdocs.index.producer import CorpusProducer, CorpusSnapshot, Rows
from fitdocs.index.schema import ColumnSpec, ColumnType, TableSpec
from fitdocs.load.profile import PROFILE_FILENAME, load_profile
from tests.index.derived.conftest import TODAY, build_fixture_root, snapshot_of


def _row_by_key(
    rows: tuple[tuple[object, ...], ...],
) -> dict[tuple[object, ...], tuple[object, ...]]:
    return {(row[0], row[1], row[4]): row for row in rows}


def _add_fractional_and_remaining_kinds(root: Path) -> None:
    profile_path = root / PROFILE_FILENAME
    raw = profile_path.read_text(encoding="utf-8")
    assert raw.count("lthr_bpm = [") == 1
    assert "threshold_pace_s_per_km = [" not in raw
    assert raw.count("max_hr_bpm = [") == 1
    assert "resting_hr_bpm = [" not in raw
    raw = raw.replace(
        "lthr_bpm = [",
        "threshold_pace_s_per_km = [\n"
        "  { value = 274.123456789, measured_on = 2026-02-04 },\n"
        "]\n"
        "lthr_bpm = [",
        1,
    )
    raw = raw.replace(
        "max_hr_bpm = [",
        "resting_hr_bpm = [\n"
        "  { value = 47, measured_on = 2026-01-29 },\n"
        "]\n"
        "max_hr_bpm = [",
        1,
    )
    profile_path.write_text(raw, encoding="utf-8")


def test_public_contract_and_exact_ordered_table_specs() -> None:
    producer: CorpusProducer = BENCHMARK_PRODUCER
    assert isinstance(producer, BenchmarkProducer)
    assert callable(producer.fingerprint)
    assert callable(producer.rows)
    assert get_type_hints(CorpusProducer.fingerprint)["corpus"] is CorpusSnapshot
    assert get_type_hints(CorpusProducer.fingerprint)["return"] is str
    assert get_type_hints(CorpusProducer.rows)["corpus"] is CorpusSnapshot
    assert get_type_hints(CorpusProducer.rows)["return"] == Rows
    assert producer.name == "derived.benchmarks"
    assert producer.tables == (BENCHMARKS_TABLE, BENCHMARK_PERIODS_TABLE)
    assert [table.name for table in producer.tables] == [
        "benchmarks",
        "benchmark_periods",
    ]
    expected_benchmarks_table = TableSpec(
        "benchmarks",
        "One row per benchmark entry in athlete.toml. Equals the athlete "
        "profile's own reading of athlete.toml (the reading fitdocs "
        "derive-benchmarks and the training-load pass use), for the inputs "
        "as of the last refresh.",
        (
            ColumnSpec(
                "kind", ColumnType.VARCHAR, "Benchmark kind recorded in athlete.toml."
            ),
            ColumnSpec(
                "discipline",
                ColumnType.VARCHAR,
                "Sport scope; NULL for athlete-wide benchmarks.",
            ),
            ColumnSpec(
                "value",
                ColumnType.DOUBLE,
                "Recorded value in the unit named by unit; never converted.",
            ),
            ColumnSpec(
                "unit", ColumnType.VARCHAR, "Unit token for the benchmark kind."
            ),
            ColumnSpec(
                "measured_on",
                ColumnType.DATE,
                "Calendar day the benchmark was measured.",
            ),
            ColumnSpec(
                "applies_from",
                ColumnType.DATE,
                "Calendar day the entry applies from; NULL when not recorded.",
            ),
            ColumnSpec(
                "source_kind",
                ColumnType.VARCHAR,
                "Whether the source is derived or measured; NULL when absent.",
            ),
            ColumnSpec(
                "source_method",
                ColumnType.VARCHAR,
                "Derivation method; NULL when not recorded.",
            ),
            ColumnSpec(
                "source_page",
                ColumnType.VARCHAR,
                "Data-root-relative page used to derive the entry; "
                "NULL when not recorded.",
            ),
            ColumnSpec(
                "source_citation",
                ColumnType.VARCHAR,
                "Citation key for a derived entry; NULL when not recorded.",
            ),
        ),
    )
    expected_periods_table = TableSpec(
        "benchmark_periods",
        "One row per period during which one benchmark entry is in force for "
        "its kind and discipline. Equals the athlete profile's own in-force "
        "rule (the rule the training-load pass applies before its "
        "cross-discipline borrowing), for the inputs as of the last refresh. "
        "Per discipline as recorded: no cross-discipline borrowing.",
        (
            ColumnSpec("kind", ColumnType.VARCHAR, "Benchmark kind in force."),
            ColumnSpec(
                "discipline",
                ColumnType.VARCHAR,
                "Recorded sport scope; NULL for athlete-wide benchmarks.",
            ),
            ColumnSpec(
                "starts_on",
                ColumnType.DATE,
                "First calendar day the entry is in force.",
            ),
            ColumnSpec(
                "ends_before",
                ColumnType.DATE,
                "First calendar day the entry is no longer in force; "
                "NULL while still in force.",
            ),
            ColumnSpec(
                "value",
                ColumnType.DOUBLE,
                "Recorded value in the unit named by unit; never converted.",
            ),
            ColumnSpec(
                "unit", ColumnType.VARCHAR, "Unit token for the benchmark kind."
            ),
            ColumnSpec(
                "measured_on",
                ColumnType.DATE,
                "Calendar day the in-force entry was measured.",
            ),
            ColumnSpec(
                "retroactive",
                ColumnType.BOOLEAN,
                "Whether this period precedes the entry's measured day.",
            ),
        ),
    )
    assert expected_benchmarks_table == BENCHMARKS_TABLE
    assert expected_periods_table == BENCHMARK_PERIODS_TABLE
    assert all(table.description.strip() for table in producer.tables)
    assert all(
        column.description.strip()
        for table in producer.tables
        for column in table.columns
    )
    assert "as of the last refresh" in BENCHMARKS_TABLE.description
    assert "as of the last refresh" in BENCHMARK_PERIODS_TABLE.description
    assert "the athlete profile's own" in BENCHMARKS_TABLE.description
    assert "the athlete profile's own" in BENCHMARK_PERIODS_TABLE.description
    assert get_type_hints(BenchmarkProducer.rows)["corpus"] is CorpusSnapshot
    assert get_type_hints(BenchmarkProducer.rows)["return"] == Rows
    assert get_type_hints(BenchmarkProducer.fingerprint) == {
        "corpus": CorpusSnapshot,
        "return": str,
    }
    assert get_type_hints(in_force_periods) == {
        "benchmarks": BenchmarkSet,
        "return": tuple[InForcePeriod, ...],
    }
    assert tuple(field.name for field in dataclasses.fields(InForcePeriod)) == (
        "kind",
        "discipline",
        "starts_on",
        "ends_before",
        "entry",
        "retroactive",
    )
    assert vars(InForcePeriod)["__dataclass_params__"].frozen
    assert get_type_hints(InForcePeriod) == {
        "kind": BenchmarkKind,
        "discipline": Sport | None,
        "starts_on": date,
        "ends_before": date | None,
        "entry": Benchmark,
        "retroactive": bool,
    }


def test_unit_tokens_are_complete_and_use_profile_units() -> None:
    assert set(UNIT_TOKENS) == set(BenchmarkKind)
    assert UNIT_TOKENS == {
        BenchmarkKind.FTP_WATTS: "w",
        BenchmarkKind.LTHR_BPM: "bpm",
        BenchmarkKind.THRESHOLD_PACE_S_PER_KM: "s_per_km",
        BenchmarkKind.MAX_HR_BPM: "bpm",
        BenchmarkKind.RESTING_HR_BPM: "bpm",
    }


def test_benchmark_rows_keep_every_profile_entry_and_only_declared_columns(
    derived_root: Path,
) -> None:
    profile_path = derived_root / PROFILE_FILENAME
    raw = profile_path.read_text(encoding="utf-8")
    assert "ONLY_NOTE_MARKER_73419" not in raw
    assert "ONLY_INPUTS_MARKER_82631" not in raw
    raw = raw.replace(
        "{ value = 260, measured_on = 2026-02-10, applies_from = 2026-01-01 },",
        (
            "{ value = 260, measured_on = 2026-02-10, applies_from = "
            '2026-01-01, note = "ONLY_NOTE_MARKER_73419" },'
        ),
        1,
    )
    assert raw.count("{ value = 283, measured_on = 2026-02-07 }") == 1
    raw = raw.replace(
        "{ value = 283, measured_on = 2026-02-07 }",
        '{ value = 283, measured_on = 2026-02-07, source = { kind = "measured" } }',
        1,
    )
    assert raw.count("lthr_bpm = [") == 1
    raw = raw.replace(
        "lthr_bpm = [",
        "threshold_pace_s_per_km = [\n"
        "  { value = 274.123456789, measured_on = 2026-02-04 },\n"
        "]\n"
        "lthr_bpm = [",
        1,
    )
    assert raw.count("max_hr_bpm = [") == 1
    raw = raw.replace(
        "max_hr_bpm = [",
        "resting_hr_bpm = [\n"
        "  { value = 47, measured_on = 2026-01-29 },\n"
        "]\n"
        "max_hr_bpm = [",
        1,
    )
    raw = raw.replace(
        'inputs = "synthetic-inputs"',
        'inputs = "ONLY_INPUTS_MARKER_82631"',
        1,
    )
    assert "ONLY_NOTE_MARKER_73419" in raw
    assert "ONLY_INPUTS_MARKER_82631" in raw
    profile_path.write_text(raw, encoding="utf-8")
    profile = load_profile(derived_root)
    rows = BENCHMARK_PRODUCER.rows(snapshot_of(derived_root, today=TODAY))["benchmarks"]

    assert len(profile.benchmarks.entries) == 7
    assert len(rows) == len(profile.benchmarks.entries)
    assert all(len(row) == len(BENCHMARKS_TABLE.columns) for row in rows)
    assert all("ONLY_NOTE_MARKER_73419" not in repr(row) for row in rows)
    assert all("ONLY_INPUTS_MARKER_82631" not in repr(row) for row in rows)
    assert all(row[2] != 999 for row in rows)
    assert all(type(row[2]) is float for row in rows)
    assert {row[3] for row in rows} == set(UNIT_TOKENS.values())
    assert {(row[0], row[1], row[4]) for row in rows} == {
        (
            entry.kind.value,
            entry.discipline.value if entry.discipline else None,
            entry.measured_on,
        )
        for entry in profile.benchmarks.entries
    }
    keyed = _row_by_key(tuple(rows))
    for entry in profile.benchmarks.entries:
        key = (
            entry.kind.value,
            entry.discipline.value if entry.discipline else None,
            entry.measured_on,
        )
        row = keyed[key]
        assert row == (
            entry.kind.value,
            entry.discipline.value if entry.discipline else None,
            float(entry.value),
            UNIT_TOKENS[entry.kind],
            entry.measured_on,
            entry.applies_from,
            entry.source.kind.value if entry.source else None,
            entry.source.method if entry.source else None,
            entry.source.document if entry.source else None,
            entry.source.citation if entry.source else None,
        )
    athlete_wide = [row for row in rows if row[0] == BenchmarkKind.MAX_HR_BPM.value]
    assert len(athlete_wide) == 1
    assert athlete_wide[0][1] is None
    assert any(
        row[6:]
        == ("derived", "synthetic-method", "workouts/derived.md", "synthetic-citation")
        for row in rows
    )
    assert any(
        row[6] is None and row[7] is None and row[8] is None and row[9] is None
        for row in rows
    )
    measured = next(row for row in rows if row[0] == "ftp_watts" and row[1] == "Run")
    assert measured[6:] == ("measured", None, None, None)
    precise_pace = next(row for row in rows if row[0] == "threshold_pace_s_per_km")
    assert precise_pace[2] == 274.123456789
    assert precise_pace[3] == "s_per_km"


def test_periods_equal_profile_selection_for_every_day_in_each_recorded_group(
    derived_root: Path,
) -> None:
    _add_fractional_and_remaining_kinds(derived_root)
    profile = load_profile(derived_root)
    entries = profile.benchmarks.entries
    groups: list[tuple[BenchmarkKind, Sport | None]] = []
    for entry in entries:
        group = (entry.kind, entry.discipline)
        if group not in groups:
            groups.append(group)
    periods = in_force_periods(profile.benchmarks)
    assert groups
    assert groups == [
        (BenchmarkKind.FTP_WATTS, Sport.RIDE),
        (BenchmarkKind.FTP_WATTS, Sport.RUN),
        (BenchmarkKind.THRESHOLD_PACE_S_PER_KM, Sport.RUN),
        (BenchmarkKind.LTHR_BPM, Sport.RUN),
        (BenchmarkKind.RESTING_HR_BPM, None),
        (BenchmarkKind.MAX_HR_BPM, None),
    ]
    period_group_order: list[tuple[BenchmarkKind, Sport | None]] = []
    for period in periods:
        group = (period.kind, period.discipline)
        if group not in period_group_order:
            period_group_order.append(group)
    assert period_group_order == groups

    for kind, discipline in groups:
        group_entries = [
            entry
            for entry in entries
            if entry.kind is kind and entry.discipline == discipline
        ]
        first = min(
            entry.applies_from or entry.measured_on for entry in group_entries
        ) - timedelta(days=3)
        last = max(entry.measured_on for entry in group_entries) + timedelta(days=3)
        group_periods = [
            period
            for period in periods
            if period.kind is kind and period.discipline == discipline
        ]
        assert group_periods
        assert group_periods[-1].ends_before is None
        for offset in range((last - first).days + 1):
            day = first + timedelta(days=offset)
            expected = profile.benchmarks.applicable(
                kind, discipline=discipline, on=day
            )
            covering = [
                period
                for period in group_periods
                if period.starts_on <= day
                and (period.ends_before is None or day < period.ends_before)
            ]
            if expected is None:
                assert covering == []
            else:
                assert len(covering) == 1
                assert covering[0].entry == expected
                assert covering[0].retroactive is (day < expected.measured_on)
        assert all(
            left.ends_before == right.starts_on
            for left, right in zip(group_periods, group_periods[1:], strict=False)
        )

    ride = profile.benchmarks.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RIDE, on=date(2026, 2, 11)
    )
    run = profile.benchmarks.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2026, 2, 11)
    )
    assert ride is not None and run is not None
    assert ride.value == 260
    assert ride.value != 271
    ride_entries = [
        entry
        for entry in entries
        if entry.kind is BenchmarkKind.FTP_WATTS and entry.discipline is Sport.RIDE
    ]
    naive = max(
        (
            entry
            for entry in ride_entries
            if entry.applies_from is not None
            and entry.applies_from <= date(2026, 2, 11)
        ),
        key=lambda entry: entry.applies_from or entry.measured_on,
    )
    assert naive.value == 271
    assert naive.value != ride.value
    assert run.value == 283
    assert ride.value != run.value
    ride_period = next(
        period
        for period in periods
        if period.kind is BenchmarkKind.FTP_WATTS
        and period.discipline is Sport.RIDE
        and period.starts_on <= date(2026, 2, 11)
        and (period.ends_before is None or date(2026, 2, 11) < period.ends_before)
    )
    assert ride_period.entry == ride


def test_period_groups_keep_the_order_of_their_first_profile_entry(
    derived_root: Path,
) -> None:
    entries = load_profile(derived_root).benchmarks.entries
    reordered = BenchmarkSet(
        entries=(entries[3], entries[0], entries[4], entries[2], entries[1])
    )
    periods = in_force_periods(reordered)
    first_group_order: list[tuple[BenchmarkKind, Sport | None]] = []
    for period in periods:
        group = (period.kind, period.discipline)
        if group not in first_group_order:
            first_group_order.append(group)
    assert first_group_order == [
        (BenchmarkKind.LTHR_BPM, Sport.RUN),
        (BenchmarkKind.FTP_WATTS, Sport.RIDE),
        (BenchmarkKind.MAX_HR_BPM, None),
        (BenchmarkKind.FTP_WATTS, Sport.RUN),
    ]


def test_period_rows_project_metadata_and_keep_kind_discipline_groups_separate(
    derived_root: Path,
) -> None:
    _add_fractional_and_remaining_kinds(derived_root)
    profile = load_profile(derived_root)
    rows = BENCHMARK_PRODUCER.rows(snapshot_of(derived_root, today=TODAY))[
        "benchmark_periods"
    ]
    assert len(rows) == 9
    assert all(len(row) == len(BENCHMARK_PERIODS_TABLE.columns) for row in rows)
    expected_rows = (
        (
            "ftp_watts",
            "Ride",
            date(2026, 1, 1),
            date(2026, 2, 1),
            260.0,
            "w",
            date(2026, 2, 10),
            True,
        ),
        (
            "ftp_watts",
            "Ride",
            date(2026, 2, 1),
            date(2026, 2, 5),
            271.0,
            "w",
            date(2026, 2, 5),
            True,
        ),
        (
            "ftp_watts",
            "Ride",
            date(2026, 2, 5),
            date(2026, 2, 10),
            271.0,
            "w",
            date(2026, 2, 5),
            False,
        ),
        (
            "ftp_watts",
            "Ride",
            date(2026, 2, 10),
            None,
            260.0,
            "w",
            date(2026, 2, 10),
            False,
        ),
        (
            "ftp_watts",
            "Run",
            date(2026, 2, 7),
            None,
            283.0,
            "w",
            date(2026, 2, 7),
            False,
        ),
        (
            "threshold_pace_s_per_km",
            "Run",
            date(2026, 2, 4),
            None,
            274.123456789,
            "s_per_km",
            date(2026, 2, 4),
            False,
        ),
        (
            "lthr_bpm",
            "Run",
            date(2026, 2, 6),
            None,
            172.0,
            "bpm",
            date(2026, 2, 6),
            False,
        ),
        (
            "resting_hr_bpm",
            None,
            date(2026, 1, 29),
            None,
            47.0,
            "bpm",
            date(2026, 1, 29),
            False,
        ),
        (
            "max_hr_bpm",
            None,
            date(2026, 2, 1),
            None,
            203.0,
            "bpm",
            date(2026, 2, 1),
            False,
        ),
    )
    assert tuple(rows) == expected_rows
    assert {row[0] for row in rows} == {kind.value for kind in BenchmarkKind}
    for row in rows:
        assert isinstance(row[0], str)
        assert isinstance(row[2], date)
        assert row[1] is None or isinstance(row[1], str)
        kind = BenchmarkKind(row[0])
        discipline = Sport(row[1]) if row[1] is not None else None
        entry = profile.benchmarks.applicable(kind, discipline=discipline, on=row[2])
        assert entry is not None
        assert row[4] == float(entry.value)
        assert row[5] == UNIT_TOKENS[entry.kind]
        assert row[6] == entry.measured_on
        assert isinstance(row[7], bool)
        assert row[7] is (row[2] < entry.measured_on)
    for left, right in zip(rows, rows[1:], strict=False):
        if left[:2] == right[:2] and left[3] == right[2]:
            assert (left[4], left[6], left[7]) != (right[4], right[6], right[7])
    ride_run = [row for row in rows if row[0] == BenchmarkKind.FTP_WATTS.value]
    assert {row[1] for row in ride_run} == {Sport.RIDE.value, Sport.RUN.value}
    assert all(
        row[1] is None for row in rows if row[0] == BenchmarkKind.MAX_HR_BPM.value
    )


def test_empty_profile_has_two_empty_tables_and_fingerprint_tracks_profile_only(
    tmp_path: Path,
) -> None:
    root = build_fixture_root(tmp_path / "no-profile")
    (root / PROFILE_FILENAME).unlink()
    snapshot = snapshot_of(root, today=TODAY)
    assert BENCHMARK_PRODUCER.rows(snapshot) == {
        "benchmarks": (),
        "benchmark_periods": (),
    }
    assert in_force_periods(load_profile(root).benchmarks) == ()
    assert BENCHMARK_PRODUCER.fingerprint(snapshot) == digest(
        {"profile": file_digest(root / PROFILE_FILENAME)}
    )

    profile = root / PROFILE_FILENAME
    profile.write_text("profile_version = 2\n", encoding="utf-8")
    first = BENCHMARK_PRODUCER.fingerprint(snapshot)
    empty_profile_snapshot = snapshot_of(root, today=TODAY)
    assert BENCHMARK_PRODUCER.rows(empty_profile_snapshot) == {
        "benchmarks": (),
        "benchmark_periods": (),
    }
    altered_snapshot = dataclasses.replace(
        snapshot,
        today=snapshot.today + timedelta(days=17),
        athlete_fingerprint="changed-fingerprint-is-not-an-input",
        pages=(
            dataclasses.replace(
                snapshot.pages[0],
                document_fingerprint="changed-page-fingerprint-is-not-an-input",
            ),
            *snapshot.pages[1:],
        ),
        left_out=(
            dataclasses.replace(
                snapshot.left_out[0],
                document_fingerprint="changed-left-out-fingerprint-is-not-an-input",
            ),
            *snapshot.left_out[1:],
        ),
    )
    assert first == BENCHMARK_PRODUCER.fingerprint(altered_snapshot)
    settings = root / "fitdocs.toml"
    settings.write_bytes(settings.read_bytes() + b"\n# SETTINGS_MARKER\n")
    assert first == BENCHMARK_PRODUCER.fingerprint(altered_snapshot)
    profile.write_text("profile_version = 2\nftp_watts = 144\n", encoding="utf-8")
    assert first != BENCHMARK_PRODUCER.fingerprint(altered_snapshot)


def test_period_value_object_is_frozen_and_producer_matches_protocol() -> None:
    assert dataclasses.is_dataclass(InForcePeriod)
    assert vars(InForcePeriod)["__dataclass_params__"].frozen
    assert vars(BenchmarkProducer)["__dataclass_params__"].frozen
    period = InForcePeriod(
        BenchmarkKind.FTP_WATTS,
        Sport.RIDE,
        date(2026, 1, 1),
        None,
        Benchmark(
            BenchmarkKind.FTP_WATTS,
            Sport.RIDE,
            200.0,
            date(2025, 12, 1),
        ),
        False,
    )
    mutable_period: Any = period
    with pytest.raises(dataclasses.FrozenInstanceError):
        mutable_period.__setattr__("retroactive", True)
