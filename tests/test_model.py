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
import typing
from datetime import UTC, datetime

import fitdocs.model as model
from fitdocs.model import (
    DYNAMICS_CHANNELS,
    FIT_EPOCH,
    SCHEMA_VERSION,
    Activity,
    DeveloperChannel,
    DeviceInfo,
    Lap,
    Modality,
    Provenance,
    Samples,
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


# --- running-dynamics channels (running-dynamics 1.1, 1.3, 3.3, 3.4) ---------

_TEN_EXISTING = {
    "heart_rate_bpm": (),
    "power_w": (),
    "cadence_rpm": (),
    "speed_mps": (),
    "distance_m": (),
    "altitude_m": (),
    "latitude_deg": (),
    "longitude_deg": (),
    "temperature_c": (),
}


def _samples(
    time_s: tuple[float, ...], **dynamics: tuple[float | None, ...]
) -> Samples:
    """A Samples with the ten existing channels sized to ``time_s``."""
    n = len(time_s)
    existing: dict[str, tuple[typing.Any, ...]] = {
        name: (None,) * n for name in _TEN_EXISTING
    }
    return Samples(time_s=time_s, **existing, **dynamics)


def test_dynamics_channels_are_the_twelve_names_in_design_order() -> None:
    assert DYNAMICS_CHANNELS == (
        "stance_time_ms",
        "stance_time_balance_pct",
        "vertical_oscillation_mm",
        "vertical_oscillation_balance_pct",
        "vertical_ratio_pct",
        "step_length_mm",
        "leg_spring_stiffness_kn_m",
        "leg_spring_stiffness_balance_pct",
        "form_power_w",
        "air_power_w",
        "impact_bw",
        "impact_loading_rate_balance_pct",
    )
    assert len(set(DYNAMICS_CHANNELS)) == len(DYNAMICS_CHANNELS) == 12


def test_dynamics_channels_are_samples_fields_after_temperature_with_default() -> None:
    fields = dataclasses.fields(Samples)
    by_name = {f.name: f for f in fields}
    hints = typing.get_type_hints(Samples)
    for name in DYNAMICS_CHANNELS:
        assert name in by_name, name
        assert hints[name] == tuple[float | None, ...], name
        assert by_name[name].default == (), name
    names = [f.name for f in fields]
    assert names[names.index("temperature_c") + 1 :] == list(DYNAMICS_CHANNELS)


def test_empty_dynamics_channels_fill_to_none_per_sample() -> None:
    samples = _samples((0.0, 1.0, 2.0))
    assert samples.time_s == (0.0, 1.0, 2.0)  # non-vacuous: three samples
    for name in DYNAMICS_CHANNELS:
        assert getattr(samples, name) == (None, None, None), name


def test_dynamics_channels_stay_empty_with_zero_samples() -> None:
    samples = _samples(())
    for name in DYNAMICS_CHANNELS:
        assert getattr(samples, name) == (), name


def test_supplied_dynamics_channel_is_kept_and_only_the_empty_ones_fill() -> None:
    samples = _samples((0.0, 1.0, 2.0), stance_time_ms=(241.5, 0.0, 250.25))
    assert samples.stance_time_ms == (241.5, 0.0, 250.25)
    others = [n for n in DYNAMICS_CHANNELS if n != "stance_time_ms"]
    for name in others:
        assert getattr(samples, name) == (None, None, None), name


def test_dynamics_channel_length_mismatch_raises_naming_the_field() -> None:
    import pytest

    for name in DYNAMICS_CHANNELS:
        with pytest.raises(ValueError, match=name):
            _samples((0.0, 1.0, 2.0), **{name: (1.0, 2.0)})
    # A non-empty channel beside zero samples is also neither 0 nor len(time_s).
    with pytest.raises(ValueError, match="form_power_w"):
        _samples((), form_power_w=(1.0, 2.0))


def test_developer_channel_is_a_frozen_dataclass_of_seven_fields() -> None:
    assert [f.name for f in dataclasses.fields(DeveloperChannel)] == [
        "name",
        "units",
        "developer_data_index",
        "field_definition_number",
        "application_id",
        "declared_scale",
        "values",
    ]
    channel = DeveloperChannel(
        name="Power",
        units="watts",
        developer_data_index=0,
        field_definition_number=3,
        application_id="ab" * 16,
        declared_scale=False,
        values=(1, None),
    )
    with pytest_raises_frozen():
        channel.name = "x"  # type: ignore[misc]


def test_activity_without_record_developer_fields_has_empty_read_only_mapping() -> None:
    import pytest

    activity = Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(sha256="0", source_path=None, decode_errors=()),
        sport=Sport.RUN,
        modality=Modality.RUN,
        is_indoor=False,
        start_time=None,
        summary=_sample_summary(),
        laps=(),
        samples=_samples(()),
        sets=(),
        devices=(),
    )
    assert len(activity.record_developer_fields) == 0
    with pytest.raises(TypeError):
        activity.record_developer_fields["x"] = None  # type: ignore[index]
    names = [f.name for f in dataclasses.fields(Activity)]
    assert names[-1] == "record_developer_fields"
    assert names[-2] == "developer_fields_declared_scale"
