"""The versioned, immutable activity-model contract.

This module is the bottom of the fitdocs dependency stack: it imports nothing
internal and never imports the ``garmin-fit-sdk``, so downstream consumers
(workout-docs rendering, training-load calculation) can depend on it with zero
FIT-format knowledge (Req 2.6). Every FIT-specific field name, unit, and
encoding is normalized here into plain, typed dataclasses.

Contract highlights:

- **Versioned** — every :class:`Activity` is stamped with
  :data:`SCHEMA_VERSION`; any breaking shape change bumps it so downstream
  consumers can detect contract drift (Req 2.2).
- **Immutable & deterministic** — all types are ``@dataclass(frozen=True)`` and
  every sequence is a ``tuple``, making instances hashable and golden-file
  friendly (Req 13).
- **Honest about absence** — every field a device may omit is typed ``X | None``
  and carries ``None`` when the device did not record it. ``None`` is reserved
  exclusively for "not recorded"; a recorded ``0`` (for example zero power while
  coasting, or a bodyweight set's ``0.0`` kg) is preserved as a real zero
  (Req 2.5, 12.3).
- **Units** — seconds (``s``), metres (``m``), metres per second (``mps``),
  kilograms (``kg``), degrees Celsius (``c``), beats per minute (``bpm``),
  watts (``w``), revolutions per minute (``rpm``), degrees (``deg``).

Invariants documented here are *enforced* by the ingest extractors, not by the
dataclasses themselves; the model states the contract those extractors uphold:

- all :class:`Samples` channel arrays share one length;
- :attr:`Samples.time_s` is non-decreasing;
- :attr:`Activity.laps` and :attr:`Activity.sets` preserve recorded order.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Final

SCHEMA_VERSION: Final[str] = "1.0"
"""Schema-version identifier stamped on every :class:`Activity` (Req 2.2)."""

FIT_EPOCH: Final[datetime] = datetime(1989, 12, 31, tzinfo=UTC)
"""The FIT timestamp epoch: 1989-12-31 00:00:00 UTC (timezone-aware)."""


def fit_datetime(raw: int) -> datetime:
    """Convert FIT epoch seconds to a timezone-aware UTC datetime (Req 2.4).

    ``raw`` is the number of seconds since the FIT epoch
    (1989-12-31 00:00:00 UTC). This is the single shared conversion helper every
    ingest extractor applies; it uses only the standard library so the model
    stays dependency-free.
    """
    return FIT_EPOCH + timedelta(seconds=raw)


class Sport(StrEnum):
    """Normalized activity sport label (the raw FIT string lives on
    :attr:`SessionSummary.sport`)."""

    RIDE = "Ride"
    RUN = "Run"
    SWIM = "Swim"
    WALK = "Walk"
    HIKE = "Hike"
    ROWING = "Rowing"
    WORKOUT = "Workout"


class Modality(StrEnum):
    """Coarse movement modality used by downstream metric selection."""

    RUN = "run"
    BIKE = "bike"
    SWIM = "swim"
    STRENGTH = "strength"
    OTHER = "other"


@dataclass(frozen=True)
class Provenance:
    """Where an activity came from and how cleanly it decoded."""

    sha256: str
    """Content hash of the source ``.fit`` bytes (Req 2.3)."""
    source_path: str | None
    """Source file path, or ``None`` when decoded from an in-memory buffer."""
    decode_errors: tuple[str, ...]
    """Stringified message-level decoder errors, surfaced not swallowed (Req 1.4)."""


@dataclass(frozen=True)
class Samples:
    """Parallel per-sample channel arrays of equal length (Req 3.1).

    Every array is indexed identically: index ``i`` describes the same sample
    across all channels. A channel the device did not record at index ``i``
    holds ``None`` there; :attr:`time_s` is the offset in seconds since the
    activity start and is non-decreasing.
    """

    time_s: tuple[float, ...]
    heart_rate_bpm: tuple[int | None, ...]
    power_w: tuple[int | None, ...]
    cadence_rpm: tuple[float | None, ...]
    speed_mps: tuple[float | None, ...]
    distance_m: tuple[float | None, ...]
    altitude_m: tuple[float | None, ...]
    latitude_deg: tuple[float | None, ...]
    longitude_deg: tuple[float | None, ...]
    temperature_c: tuple[float | None, ...]


@dataclass(frozen=True)
class SessionSummary:
    """Recorded session-level values, verbatim — no derivation (Req 4.1).

    ``sport``/``sub_sport`` are the raw FIT strings; the normalized
    :class:`Sport`/:class:`Modality` labels live on :class:`Activity`.
    """

    sport: str | None
    sub_sport: str | None
    start_time: datetime | None
    total_elapsed_time_s: float | None
    total_timer_time_s: float | None
    total_distance_m: float | None
    total_calories_kcal: int | None
    total_ascent_m: float | None
    total_descent_m: float | None
    avg_heart_rate_bpm: int | None
    max_heart_rate_bpm: int | None
    avg_power_w: int | None
    max_power_w: int | None
    avg_cadence_rpm: float | None
    max_cadence_rpm: float | None
    avg_speed_mps: float | None
    max_speed_mps: float | None


@dataclass(frozen=True)
class Lap:
    """One recorded lap, projected onto inclusive sample index ranges (Req 4.3).

    :attr:`start_index` and :attr:`end_index` are inclusive indices into
    :class:`Samples`; both are ``None`` when the lap could not be matched to any
    records (Req 4.4), while its recorded summary fields are still preserved.
    """

    start_time: datetime | None
    total_elapsed_time_s: float | None
    total_timer_time_s: float | None
    total_distance_m: float | None
    avg_heart_rate_bpm: int | None
    max_heart_rate_bpm: int | None
    avg_power_w: int | None
    max_power_w: int | None
    avg_cadence_rpm: float | None
    avg_speed_mps: float | None
    max_speed_mps: float | None
    total_ascent_m: float | None
    total_descent_m: float | None
    start_index: int | None
    end_index: int | None


@dataclass(frozen=True)
class StrengthSet:
    """One strength-training set as recorded; unresolved fields stay ``None``.

    ``weight_kg`` keeps recorded zeros: a bodyweight set records ``0.0`` kg,
    which is a true zero, not missing data (Req 12.3). ``exercise_name`` is
    ``None`` when it cannot be resolved — never guessed (Req 6.3, 6.5).
    """

    set_type: str | None
    start_time: datetime | None
    duration_s: float | None
    repetitions: int | None
    weight_kg: float | None
    category: str | None
    exercise_name: str | None
    message_index: int | None


@dataclass(frozen=True)
class DeviceInfo:
    """A device that contributed to the activity; absent fields are ``None``."""

    device_index: int | None
    manufacturer: str | None
    product_name: str | None
    serial_number: int | None
    software_version: float | None
    battery_status: str | None


@dataclass(frozen=True)
class Activity:
    """The root aggregate: a fully normalized, versioned activity.

    Identity is content-based (:attr:`Provenance.sha256`); there is no other
    persistence or identity. :attr:`summary` and :attr:`samples` are always
    present objects (their fields/arrays may be ``None``/empty); :attr:`laps`,
    :attr:`sets`, and :attr:`devices` preserve recorded order.
    """

    schema_version: str
    provenance: Provenance
    sport: Sport
    modality: Modality
    is_indoor: bool
    start_time: datetime | None
    summary: SessionSummary
    laps: tuple[Lap, ...]
    samples: Samples
    sets: tuple[StrengthSet, ...]
    devices: tuple[DeviceInfo, ...]
    developer_fields: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({})
    )
    """Session-scoped developer-defined FIT fields, keyed by described field name
    with raw decoded values (array values as tuples). A read-only mapping that is
    *empty* -- never ``None`` -- when the file describes no such fields or the
    session records none of them (Req 14.1, 14.3). The default keeps this field
    additive; the ingest orchestrator populates it explicitly."""
    developer_fields_declared_scale: frozenset[str] = field(default_factory=frozenset)
    """Names of :attr:`developer_fields` keys whose ``field_description``
    declared a ``scale`` and/or ``offset`` (Req 14.2, as amended). A name in
    this set has ALREADY been decoded against that declaration by ingest --
    the value is a unit-correct number, not a raw undecoded integer needing a
    caller-applied convention. A name NOT in this set (every field in every
    corpus file today) was passed through unchanged because none was
    declared, and a caller that applies its own known convention to it (for
    example ``render/sections.py``'s hundredths guess for ``AVG METs``) is
    still choosing an interpretation, not double-decoding. The default keeps
    this field additive; the ingest orchestrator populates it explicitly."""
