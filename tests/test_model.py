"""Tests for the versioned, dependency-free activity model contract.

These lock the model's public shape and invariants (Req 2.1, 2.2, 2.4, 2.5,
2.6, 12.3): the FIT-epoch conversion helper, module purity (no SDK / internal
imports), frozen immutability, the ``None``-for-absent (never fabricated zero)
convention, and the schema/enum constants.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from datetime import UTC, datetime

import fitdocs.model as model
from fitdocs.model import (
    FIT_EPOCH,
    SCHEMA_VERSION,
    DeviceInfo,
    Lap,
    Modality,
    Provenance,
    SessionSummary,
    Sport,
    StrengthSet,
    fit_datetime,
)

# The FIT epoch expressed as a Unix timestamp, derived independently of the
# model: 1989-12-31 00:00:00 UTC == 631065600 seconds after the Unix epoch.
_FIT_EPOCH_UNIX = 631065600


def test_fit_datetime_zero_is_fit_epoch() -> None:
    expected_epoch = datetime(1989, 12, 31, tzinfo=UTC)
    assert fit_datetime(0) == expected_epoch
    assert expected_epoch == FIT_EPOCH


def test_fit_datetime_one_day_offset() -> None:
    # 86400 s after the FIT epoch is exactly the next midnight UTC.
    assert fit_datetime(86400) == datetime(1990, 1, 1, tzinfo=UTC)


def test_fit_datetime_known_offset_matches_unix_derivation() -> None:
    raw = 1_000_000_000
    # Independent cross-check via the Unix-epoch offset (not via FIT_EPOCH).
    expected = datetime.fromtimestamp(raw + _FIT_EPOCH_UNIX, tz=UTC)
    assert fit_datetime(raw) == expected


def test_fit_datetime_is_timezone_aware_utc() -> None:
    result = fit_datetime(123456)
    assert result.tzinfo is not None
    assert result.utcoffset() == UTC.utcoffset(None)


def test_model_module_does_not_import_sdk_in_subprocess() -> None:
    """A fresh import of the model must not pull in the FIT SDK (Req 2.6)."""
    code = (
        "import sys\n"
        "import fitdocs.model\n"
        "assert 'garmin_fit_sdk' not in sys.modules, sorted(sys.modules)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_model_source_has_no_sdk_or_internal_imports() -> None:
    source = model.__file__ or ""
    assert source, "model.__file__ should be set"
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "garmin_fit_sdk" not in text
    assert "from fitdocs" not in text
    assert "import fitdocs" not in text


def test_schema_version_constant() -> None:
    assert SCHEMA_VERSION == "1.0"


def test_sport_enum_behaves_as_string() -> None:
    assert Sport.RIDE == "Ride"
    assert Sport.RUN == "Run"
    assert isinstance(Sport.RIDE, str)
    assert f"{Sport.RIDE}" == "Ride"


def test_modality_enum_behaves_as_string() -> None:
    assert Modality.STRENGTH == "strength"
    assert Modality.BIKE == "bike"
    assert isinstance(Modality.OTHER, str)


def _sample_summary() -> SessionSummary:
    return SessionSummary(
        sport=None,
        sub_sport=None,
        start_time=None,
        total_elapsed_time_s=None,
        total_timer_time_s=None,
        total_distance_m=None,
        total_calories_kcal=None,
        total_ascent_m=None,
        total_descent_m=None,
        avg_heart_rate_bpm=None,
        max_heart_rate_bpm=None,
        avg_power_w=None,
        max_power_w=None,
        avg_cadence_rpm=None,
        max_cadence_rpm=None,
        avg_speed_mps=None,
        max_speed_mps=None,
    )


def test_provenance_is_frozen() -> None:
    prov = Provenance(sha256="abc", source_path=None, decode_errors=())
    with pytest_raises_frozen():
        prov.sha256 = "def"  # type: ignore[misc]


def test_summary_is_frozen() -> None:
    summary = _sample_summary()
    with pytest_raises_frozen():
        summary.avg_power_w = 200  # type: ignore[misc]


def test_summary_accepts_none_for_absent_fields() -> None:
    summary = _sample_summary()
    assert summary.sport is None
    assert summary.total_distance_m is None
    assert summary.avg_heart_rate_bpm is None


def test_lap_accepts_none_indices_for_unmatched_window() -> None:
    lap = Lap(
        start_time=None,
        total_elapsed_time_s=None,
        total_timer_time_s=None,
        total_distance_m=None,
        avg_heart_rate_bpm=None,
        max_heart_rate_bpm=None,
        avg_power_w=None,
        max_power_w=None,
        avg_cadence_rpm=None,
        avg_speed_mps=None,
        max_speed_mps=None,
        total_ascent_m=None,
        total_descent_m=None,
        start_index=None,
        end_index=None,
    )
    assert lap.start_index is None
    assert lap.end_index is None


def test_recorded_zero_weight_is_preserved_distinct_from_none() -> None:
    """A bodyweight set records ``0.0`` kg; that true zero must survive as a
    zero and never collapse to ``None`` (Req 12.3)."""
    bodyweight = StrengthSet(
        set_type="active",
        start_time=None,
        duration_s=None,
        repetitions=10,
        weight_kg=0.0,
        category="push_up",
        exercise_name=None,
        message_index=0,
    )
    assert bodyweight.weight_kg == 0.0
    assert bodyweight.weight_kg is not None

    unrecorded = StrengthSet(
        set_type="active",
        start_time=None,
        duration_s=None,
        repetitions=None,
        weight_kg=None,
        category=None,
        exercise_name=None,
        message_index=None,
    )
    assert unrecorded.weight_kg is None


def test_device_info_is_frozen_and_optional() -> None:
    device = DeviceInfo(
        device_index=None,
        manufacturer=None,
        product_name=None,
        serial_number=None,
        software_version=None,
        battery_status=None,
    )
    with pytest_raises_frozen():
        device.manufacturer = "garmin"  # type: ignore[misc]


def pytest_raises_frozen() -> object:
    """Context manager asserting a frozen-dataclass mutation is rejected.

    ``dataclasses.FrozenInstanceError`` subclasses ``AttributeError``; accept
    either so the intent (immutability) is what is tested.
    """
    import pytest

    return pytest.raises((dataclasses.FrozenInstanceError, AttributeError))
