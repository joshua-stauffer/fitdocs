"""Tests for the public parsing entry point (Req 1.1, 1.4, 2.1-2.4, 13.1).

These exercise :func:`fitdocs.ingest.parse_fit` -- the orchestrator that composes
the decode wrapper and every extractor into one frozen :class:`Activity`. The
orchestrator performs no extraction logic of its own; it is verified here through
its observable outputs on the synthetic byte fixtures:

* each fixture (run/ride/strength/minimal) parses to a complete Activity with the
  right schema version, sport/modality/indoor flag, populated summary, and
  provenance whose ``sha256`` is the content hash of the source bytes (Req 2.1);
* message-level decoder errors ride on ``provenance.decode_errors`` rather than
  aborting the parse (Req 1.4), and the content hash is a 64-hex digest (Req 2.3);
* the decode error taxonomy propagates -- non-FIT input and a truncated file raise
  their typed errors before any Activity is built (Req 1.1);
* the start-time policy is applied: a session's start when present, else the first
  record timestamp (Req 2.4);
* parsing from a file is side-effect-free -- the source bytes are untouched and no
  files are written (Req 13.1);
* the two carried-forward robustness fixes hold end-to-end: an unknown enum decoded
  as a raw int no longer crashes the whole-file parse (Part B), and a ``'creator'``
  device index surfaces as the true int ``0`` (Part C).
"""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from fitdocs.ingest import parse_fit
from fitdocs.ingest.decode import DecodeResult, decode_fit
from fitdocs.ingest.errors import FitIntegrityError, NotFitFileError
from fitdocs.model import (
    SCHEMA_VERSION,
    Activity,
    Modality,
    Sport,
    fit_datetime,
)
from tests.fixtures import builder
from tests.fixtures.builder import FIT_TIMESTAMP_BASE

# The fixed FIT-epoch second the fixture builder anchors every fixture to.
TS0 = FIT_TIMESTAMP_BASE


# --- Each fixture -> a complete Activity (Req 2.1) --------------------------


def test_run_fixture_parses_to_complete_activity(run_fit_bytes: bytes) -> None:
    """The run fixture parses to a Run Activity with 3 projected laps (Req 2.1)."""
    activity = parse_fit(run_fit_bytes)

    assert isinstance(activity, Activity)
    assert activity.schema_version == SCHEMA_VERSION
    assert activity.sport is Sport.RUN
    assert activity.modality is Modality.RUN
    assert activity.is_indoor is False

    # Summary populated straight from the session message.
    assert activity.summary.sport == "running"
    assert activity.summary.total_calories_kcal == 60

    # Provenance carries the content hash of the exact source bytes.
    assert activity.provenance.sha256 == hashlib.sha256(run_fit_bytes).hexdigest()

    # Ten records extracted; the three laps project onto contiguous inclusive
    # index windows that tile every record (0..9).
    assert len(activity.samples.time_s) == 10
    assert len(activity.laps) == 3
    assert [(lap.start_index, lap.end_index) for lap in activity.laps] == [
        (0, 3),
        (4, 6),
        (7, 9),
    ]
    # The run carries GPS and heart rate but no power.
    assert activity.samples.latitude_deg[0] is not None
    assert all(hr is not None for hr in activity.samples.heart_rate_bpm)
    assert all(power is None for power in activity.samples.power_w)


def test_ride_fixture_parses_with_power(ride_fit_bytes: bytes) -> None:
    """The ride fixture parses to a Ride Activity with a power channel (Req 2.1)."""
    activity = parse_fit(ride_fit_bytes)

    assert activity.sport is Sport.RIDE
    assert activity.modality is Modality.BIKE
    assert activity.is_indoor is False
    # Power present on every sample; the session avg power maps through.
    assert all(power is not None for power in activity.samples.power_w)
    assert activity.summary.avg_power_w == 200


def test_strength_fixture_parses_with_sets(strength_fit_bytes: bytes) -> None:
    """The strength fixture parses to a Workout/strength Activity with sets (2.1)."""
    activity = parse_fit(strength_fit_bytes)

    # training -> Workout label; strength_training sub-sport -> strength modality.
    assert activity.sport is Sport.WORKOUT
    assert activity.modality is Modality.STRENGTH
    assert activity.is_indoor is False
    assert len(activity.sets) == 4
    assert [s.message_index for s in activity.sets] == [0, 1, 2, 3]
    assert activity.sets[0].exercise_name == "barbell_bench_press"


def test_minimal_fixture_has_no_session_and_falls_back(
    minimal_fit_bytes: bytes,
) -> None:
    """A session-less file parses; start_time falls back to the first record (2.4)."""
    activity = parse_fit(minimal_fit_bytes)

    assert isinstance(activity, Activity)
    # No session message -> unknown sport -> Workout fallback, summary mostly None.
    assert activity.sport is Sport.WORKOUT
    assert activity.summary.sport is None
    assert activity.summary.start_time is None
    assert activity.summary.total_distance_m is None
    # Records still extracted; start_time anchors to the first record timestamp.
    assert len(activity.samples.time_s) == 4
    assert activity.start_time == fit_datetime(TS0)


# --- Provenance: content hash + collected decode errors (Req 2.3, 1.4) ------


def test_provenance_sha256_is_the_content_hash(run_fit_bytes: bytes) -> None:
    """provenance.sha256 is the 64-hex content hash of the source bytes (Req 2.3)."""
    activity = parse_fit(run_fit_bytes)

    digest = activity.provenance.sha256
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)
    assert digest == decode_fit(run_fit_bytes).sha256


def test_bad_message_errors_ride_on_provenance(bad_message_fit_bytes: bytes) -> None:
    """A message-level decoder error is collected, not raised (Req 1.4)."""
    activity = parse_fit(bad_message_fit_bytes)

    assert isinstance(activity, Activity)
    assert activity.provenance.decode_errors  # non-empty


# --- Error taxonomy propagates before any Activity (Req 1.1) ----------------


def test_non_fit_bytes_raise_not_fit_error(non_fit_bytes: bytes) -> None:
    """Non-FIT input raises NotFitFileError, never an Activity (Req 1.1, 1.2)."""
    with pytest.raises(NotFitFileError):
        parse_fit(non_fit_bytes)


def test_truncated_bytes_raise_integrity_error(truncated_fit_bytes: bytes) -> None:
    """A truncated file raises FitIntegrityError (Req 1.1, 1.3)."""
    with pytest.raises(FitIntegrityError):
        parse_fit(truncated_fit_bytes)


# --- start_time policy (Req 2.4) --------------------------------------------


def test_start_time_uses_session_start_when_present(run_fit_bytes: bytes) -> None:
    """A session-bearing fixture anchors start_time to the session start (Req 2.4)."""
    activity = parse_fit(run_fit_bytes)

    assert activity.start_time == activity.summary.start_time
    assert activity.start_time == fit_datetime(TS0)
    assert activity.start_time is not None
    assert activity.start_time.tzinfo is not None


def test_start_time_falls_back_to_first_record(minimal_fit_bytes: bytes) -> None:
    """With no session message start_time is the first record timestamp (Req 2.4)."""
    activity = parse_fit(minimal_fit_bytes)

    assert activity.summary.start_time is None
    assert activity.start_time == fit_datetime(TS0)


# --- Purity / no side effects (Req 13.1) ------------------------------------


def test_parsing_a_file_leaves_it_unchanged(
    run_fit_bytes: bytes, tmp_path: Path
) -> None:
    """Parsing from a path writes nothing and never mutates the source (Req 13.1)."""
    source = tmp_path / "activity.fit"
    source.write_bytes(run_fit_bytes)
    before = source.read_bytes()
    listing_before = sorted(p.name for p in tmp_path.iterdir())

    activity = parse_fit(source)

    assert isinstance(activity, Activity)
    # Source bytes untouched and no new files appeared in the directory.
    assert source.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == listing_before


def test_parse_accepts_a_path_and_bytes_identically(
    run_fit_bytes: bytes, tmp_path: Path
) -> None:
    """A path and its bytes parse to the same provenance hash; path is recorded."""
    source = tmp_path / "activity.fit"
    source.write_bytes(run_fit_bytes)

    from_bytes = parse_fit(run_fit_bytes)
    from_path = parse_fit(source)

    assert from_path.provenance.sha256 == from_bytes.provenance.sha256
    assert from_path.provenance.source_path == str(source)
    assert from_bytes.provenance.source_path is None


# --- Part C: creator device index surfaces as 0 end-to-end ------------------


def test_creator_device_index_is_zero_end_to_end(run_fit_bytes: bytes) -> None:
    """The run fixture's 'creator' device surfaces as device_index 0 (Part C)."""
    activity = parse_fit(run_fit_bytes)

    assert len(activity.devices) == 1
    assert activity.devices[0].device_index == 0


# --- Part B: an unknown-enum int does not crash the whole-file parse --------


def test_int_enum_fields_do_not_crash_whole_file_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An int-valued sport/manufacturer parses without crashing (Part B).

    The decoder normally stringifies enums, but an UNKNOWN enum stays a raw int.
    Rather than encode such a file, the real decoded run messages are mutated to
    carry an int ``sport`` and an int ``manufacturer`` and fed through a stubbed
    ``decode_fit`` so ``parse_fit`` exercises the exact same end-to-end path. The
    whole-file parse must still return an Activity, with the int values faithfully
    coerced to their string representations (never crashing, never fabricated).
    """
    messages = copy.deepcopy(builder.run_messages())
    messages["session_mesgs"][0]["sport"] = 999  # unknown sport enum -> raw int
    messages["device_info_mesgs"][0]["manufacturer"] = 7  # unknown mfr -> raw int

    stub = DecodeResult(messages=messages, errors=(), sha256="0" * 64, source_path=None)
    monkeypatch.setattr("fitdocs.ingest.decode_fit", lambda source: stub)

    activity = parse_fit(b"ignored -- decode_fit is stubbed")

    assert isinstance(activity, Activity)
    # Faithful raw representation, not a crash and not a fabricated default.
    assert activity.summary.sport == "999"
    assert activity.devices[0].manufacturer == "7"
    # An unknown sport string still maps to the never-failing Workout fallback.
    assert activity.sport is Sport.WORKOUT


# --- developer_fields_declared_scale wiring (Req 14.2, as amended) ----------


def test_parse_fit_wires_declared_scale_names_end_to_end(
    session_dev_fields_declared_scale_fit_bytes: bytes,
) -> None:
    """``parse_fit`` populates ``developer_fields_declared_scale`` end-to-end.

    ``AVG METs`` declares ``scale=100`` in this fixture (Req 14.2, as
    amended): its value is decoded (``9.5``, not the raw ``950``) AND its name
    is reported in the declared-scale set, while its undeclared sibling
    ``SESSION WEATHER HUMIDITY`` is decoded unchanged and absent from that set.
    """
    activity = parse_fit(session_dev_fields_declared_scale_fit_bytes)

    assert activity.developer_fields["AVG METs"] == pytest.approx(9.5)
    assert "AVG METs" in activity.developer_fields_declared_scale
    assert activity.developer_fields["SESSION WEATHER HUMIDITY"] == 5500
    assert "SESSION WEATHER HUMIDITY" not in activity.developer_fields_declared_scale
