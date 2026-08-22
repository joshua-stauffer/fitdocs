"""Tests for the lap projector (Req 4.3, 4.4).

These exercise :func:`fitdocs.ingest.laps.extract_laps` on hand-built
``lap_mesgs`` dicts and hand-constructed ``record_timestamps`` tuples (the
projector works on plain decoded dicts plus a chronological timestamp tuple, so
no binary fixtures are needed for the unit cases) plus one integration-style
check that decodes the run fixture. Coverage:

* three chronological laps aligned to a record-timestamp tuple project onto
  inclusive index ranges that are contiguous, non-overlapping, and cover every
  record (Req 4.3);
* each lap carries its mapped recorded summary fields, with absent fields
  ``None`` and recorded zeros preserved (Req 4.3, 12.3);
* the enhanced avg/max-speed variant wins when present/non-None, else the basic
  variant (Req 3.3 parity);
* a lap starting after every record, a lap lacking a ``start_time``, and every
  lap when there are no records at all get ``None`` index ranges while keeping
  their recorded summary fields (Req 4.4);
* an empty lap list yields an empty tuple, and the returned tuple preserves the
  original message order regardless of ``start_time`` order.
"""

from __future__ import annotations

from fitdocs.ingest.laps import extract_laps
from fitdocs.ingest.records import extract_samples
from fitdocs.model import Lap, fit_datetime
from tests.fixtures.builder import decode_messages

# A fixed FIT-epoch second used as t0 (never wall-clock time).
TS0 = 1_000_000_000


def _timestamps(count: int) -> tuple[object, ...]:
    """A non-decreasing tuple of ``count`` record timestamps at 1 s spacing."""
    return tuple(fit_datetime(TS0 + i) for i in range(count))


def _covered_indices(laps: tuple[Lap, ...]) -> list[int]:
    """Flatten every lap's inclusive [start_index, end_index] window in order."""
    covered: list[int] = []
    for lap in laps:
        assert lap.start_index is not None
        assert lap.end_index is not None
        covered.extend(range(lap.start_index, lap.end_index + 1))
    return covered


# --- Three-lap projection (Req 4.3) -----------------------------------------


def test_three_laps_tile_record_stream_without_overlap() -> None:
    """Three chronological laps project onto contiguous inclusive ranges (Req 4.3).

    Fifteen records with lap starts at indices 0, 5, and 10 yield the inclusive
    windows [0,4], [5,9], [10,14]: their union is every record index exactly once
    (contiguous, non-overlapping, complete).
    """
    record_timestamps = _timestamps(15)
    laps_in = [
        {"start_time": TS0 + 0},
        {"start_time": TS0 + 5},
        {"start_time": TS0 + 10},
    ]

    laps = extract_laps(laps_in, record_timestamps)

    assert [(lap.start_index, lap.end_index) for lap in laps] == [
        (0, 4),
        (5, 9),
        (10, 14),
    ]
    # Contiguous + non-overlapping + covering: the ordered union is 0..14 exactly.
    covered = _covered_indices(laps)
    assert covered == list(range(15))
    assert len(covered) == len(set(covered))  # no index attributed twice


def test_output_preserves_message_order_not_start_time_order() -> None:
    """Laps are returned in original message order; ranges follow start_time (4.3).

    Given laps in reverse-chronological message order, the output stays in that
    message order while each lap still receives its own start_time-derived window.
    """
    record_timestamps = _timestamps(15)
    laps_in = [
        {"start_time": TS0 + 10},  # message index 0
        {"start_time": TS0 + 5},  # message index 1
        {"start_time": TS0 + 0},  # message index 2
    ]

    laps = extract_laps(laps_in, record_timestamps)

    assert [(lap.start_index, lap.end_index) for lap in laps] == [
        (10, 14),
        (5, 9),
        (0, 4),
    ]
    # Together they still tile the whole stream, just reported message-first.
    assert sorted(_covered_indices(laps)) == list(range(15))


# --- Summary field mapping (Req 4.3, 12.3) ----------------------------------


def test_lap_summary_fields_mapped_from_recorded_keys() -> None:
    """A fully populated lap maps each recorded field onto the :class:`Lap` (4.3)."""
    record_timestamps = _timestamps(5)
    lap_in = {
        "start_time": TS0,
        "total_elapsed_time": 300.0,
        "total_timer_time": 295.0,
        "total_distance": 1000.0,
        "avg_heart_rate": 150,
        "max_heart_rate": 165,
        "avg_power": 220,
        "max_power": 260,
        "avg_cadence": 88,
        "avg_speed": 3.5,
        "max_speed": 4.0,
        "total_ascent": 12,
        "total_descent": 8,
    }

    (lap,) = extract_laps([lap_in], record_timestamps)

    assert lap.start_time == fit_datetime(TS0)
    assert lap.total_elapsed_time_s == 300.0
    assert lap.total_timer_time_s == 295.0
    assert lap.total_distance_m == 1000.0
    assert lap.avg_heart_rate_bpm == 150
    assert lap.max_heart_rate_bpm == 165
    assert lap.avg_power_w == 220
    assert lap.max_power_w == 260
    assert lap.avg_cadence_rpm == 88
    assert lap.avg_speed_mps == 3.5
    assert lap.max_speed_mps == 4.0
    assert lap.total_ascent_m == 12
    assert lap.total_descent_m == 8
    # A projected single lap covers the whole record stream, inclusive.
    assert (lap.start_index, lap.end_index) == (0, 4)


def test_absent_fields_none_and_recorded_zeros_preserved() -> None:
    """Absent summary keys are ``None`` while a recorded ``0`` stays a real zero.

    ``avg_power``/``max_power`` are unrecorded (stay ``None``); ``total_descent``
    is a recorded ``0`` and must be preserved, never dropped (Req 12.3).
    """
    record_timestamps = _timestamps(3)
    lap_in = {
        "start_time": TS0,
        "total_distance": 500.0,
        "total_ascent": 0,
        "total_descent": 0,
    }

    (lap,) = extract_laps([lap_in], record_timestamps)

    assert lap.avg_power_w is None
    assert lap.max_power_w is None
    assert lap.avg_heart_rate_bpm is None
    assert lap.avg_speed_mps is None
    # Recorded zeros preserved, not confused with "not recorded".
    assert lap.total_ascent_m == 0
    assert lap.total_descent_m == 0


def test_enhanced_speed_preferred_else_basic() -> None:
    """Enhanced avg/max speed wins when present; basic is used otherwise (Req 3.3)."""
    record_timestamps = _timestamps(4)
    enhanced = {
        "start_time": TS0,
        "enhanced_avg_speed": 3.9,
        "avg_speed": 3.5,
        "enhanced_max_speed": 4.5,
        "max_speed": 4.0,
    }
    basic = {"start_time": TS0, "avg_speed": 3.5, "max_speed": 4.0}
    enhanced_none = {
        "start_time": TS0,
        "enhanced_avg_speed": None,
        "avg_speed": 3.5,
        "enhanced_max_speed": None,
        "max_speed": 4.0,
    }

    lap_enhanced = extract_laps([enhanced], record_timestamps)[0]
    lap_basic = extract_laps([basic], record_timestamps)[0]
    lap_none = extract_laps([enhanced_none], record_timestamps)[0]

    assert (lap_enhanced.avg_speed_mps, lap_enhanced.max_speed_mps) == (3.9, 4.5)
    assert (lap_basic.avg_speed_mps, lap_basic.max_speed_mps) == (3.5, 4.0)
    # Present-but-None enhanced falls back to the basic variant per sample.
    assert (lap_none.avg_speed_mps, lap_none.max_speed_mps) == (3.5, 4.0)


def test_component_expanded_enhanced_speed_falls_back_to_basic() -> None:
    """A list-valued ``enhanced_*`` speed (FIT component expansion) is not usable,
    so the basic scalar is used and parsing must not crash (Req 3.3).

    Real-data regression: with ``expand_components=True`` the decoder returns a
    lap's ``enhanced_avg_speed`` as a redundant array (e.g. ``[3.17, 3.17]``) while
    the plain ``avg_speed`` carries the same value as a clean scalar. This shape
    crashed ``parse_fit`` on 16/22 of the maintainer's real files before the
    enhanced-preference helper learned to fall back to the basic scalar.
    """
    record_timestamps = _timestamps(4)
    expanded = {
        "start_time": TS0,
        "enhanced_avg_speed": [3.17, 3.17],  # component-expanded array
        "avg_speed": 3.17,  # clean scalar coexists (equals the array elements)
        "enhanced_max_speed": [4.0, 4.0],
        "max_speed": 4.0,
    }
    # A list-valued enhanced with NO basic scalar: honest absence, still no crash.
    no_basic = {"start_time": TS0, "enhanced_avg_speed": [2.5, 2.5]}

    (lap,) = extract_laps([expanded], record_timestamps)
    (lap_no_basic,) = extract_laps([no_basic], record_timestamps)

    assert lap.avg_speed_mps == 3.17
    assert lap.max_speed_mps == 4.0
    assert lap_no_basic.avg_speed_mps is None  # no fabrication, no crash


# --- Unmatched / degenerate laps (Req 4.4) ----------------------------------


def test_lap_starting_after_all_records_gets_none_indices() -> None:
    """A lap whose start is after every record keeps its summary but has no window.

    Two aligned laps still tile the stream while the trailing lap -- starting past
    the final record -- reports ``None`` indices with summary intact (Req 4.4).
    """
    record_timestamps = _timestamps(5)
    laps_in = [
        {"start_time": TS0 + 0},
        {"start_time": TS0 + 3},
        {"start_time": TS0 + 100, "total_distance": 42.0},  # after every record
    ]

    laps = extract_laps(laps_in, record_timestamps)

    assert (laps[0].start_index, laps[0].end_index) == (0, 2)
    assert (laps[1].start_index, laps[1].end_index) == (3, 4)
    assert laps[2].start_index is None
    assert laps[2].end_index is None
    assert laps[2].total_distance_m == 42.0  # summary preserved
    # The two matched laps still cover the whole stream exactly.
    assert _covered_indices(laps[:2]) == list(range(5))


def test_lap_without_start_time_gets_none_indices() -> None:
    """A lap lacking ``start_time`` cannot be projected -> ``None`` indices (4.4)."""
    record_timestamps = _timestamps(5)
    lap_in = {"total_distance": 250.0, "avg_heart_rate": 140}

    (lap,) = extract_laps([lap_in], record_timestamps)

    assert lap.start_time is None
    assert lap.start_index is None
    assert lap.end_index is None
    assert lap.total_distance_m == 250.0  # summary preserved
    assert lap.avg_heart_rate_bpm == 140


def test_no_records_gives_every_lap_none_indices() -> None:
    """With no records, every lap gets ``None`` indices, summaries preserved (4.4)."""
    laps_in = [
        {"start_time": TS0, "total_distance": 100.0},
        {"start_time": TS0 + 60, "total_distance": 200.0},
    ]

    laps = extract_laps(laps_in, ())

    for lap in laps:
        assert lap.start_index is None
        assert lap.end_index is None
    assert laps[0].total_distance_m == 100.0
    assert laps[1].total_distance_m == 200.0


def test_empty_lap_list_returns_empty_tuple() -> None:
    """No lap messages -> an empty tuple (never ``None``)."""
    assert extract_laps([], _timestamps(3)) == ()


# --- Integration with the run fixture (Req 4.3) -----------------------------


def test_run_fixture_laps_tile_decoded_record_stream(run_fit_bytes: bytes) -> None:
    """Integration: the run fixture's three laps tile its decoded record stream.

    Record timestamps come from the record extractor (as the orchestrator will
    wire them); the three fixture laps then project onto contiguous inclusive
    windows covering every record without overlap (Req 4.3).
    """
    messages, _ = decode_messages(run_fit_bytes)
    _, record_timestamps = extract_samples(messages["record_mesgs"], None)

    laps = extract_laps(messages["lap_mesgs"], record_timestamps)

    assert len(laps) == 3
    covered = _covered_indices(laps)
    assert covered == list(range(len(record_timestamps)))  # contiguous, complete
    assert len(covered) == len(set(covered))  # non-overlapping
