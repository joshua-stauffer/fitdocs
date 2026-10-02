"""Deterministic synthetic ``.fit`` fixture construction for the test suite.

This test-support module encodes hand-authored, fully synthetic activities with
``garmin_fit_sdk.Encoder`` so the suite never depends on personal ``.fit`` data
(the hard data-root rule) and golden snapshots stay stable. Every series is a
fixed, hand-chosen constant -- no wall-clock time and no unseeded randomness --
so building any fixture twice yields byte-identical output (Req 13.2).

Fixture families:

* :func:`run_fit_bytes` -- outdoor run: GPS position, heart rate, cadence, and
  three laps, using the *enhanced* speed/altitude channels (no power, so the
  absent-power path is exercised downstream).
* :func:`ride_fit_bytes` -- ride: power, heart rate, cadence, plain ``speed``
  (no GPS/altitude), exercising the non-enhanced channel path.
* :func:`hike_fit_bytes` -- a small ``Modality.OTHER`` document (``Sport.HIKE``
  via the ``"hiking"`` FIT sport label): heart rate and distance only, no GPS,
  power, or laps. A thin :func:`small_sport_fit_bytes` call (see below).
* :func:`small_sport_fit_bytes` -- a small, parameterized fixture (sport label,
  serial, timestamp offset, record count, speed, heart-rate base all
  adjustable) for tests that need several non-colliding documents of one sport,
  or a sport ``run``/``ride``/``strength`` don't cover (rowing, walking, hiking)
  -- built from the same shared private message helpers as every other family
  here, not a new mechanism.
* :func:`strength_fit_bytes` -- strength session whose ``set_mesgs`` deliberately
  omit fields (one set missing both weight and repetitions), include a bodyweight
  ``weight=0`` set (a true zero, not missing), and carry ``category`` /
  ``category_subtype`` so later name resolution has inputs -- one subtype is
  intentionally unresolvable.
* :func:`minimal_fit_bytes` -- records only, with no ``session`` message.
* :func:`non_fit_bytes` -- bytes with no valid FIT header.
* :func:`truncated_fit_bytes` -- a valid file cut short so its integrity check
  fails while the header still survives.
* :func:`bad_message_fit_bytes` -- a valid file with trailing garbage that decodes
  overall (records still present) while surfacing a message-level decoder error;
  this is the *crafted-bytes* path -- no decoder stubbing was needed.

Real-shaped variants (task 1.6), reproducing shapes found in the user's real
HealthFit corpus for the workout-docs layer (all byte-deterministic, Req 4.1):

* :func:`run_native_power_sparse_hr_fit_bytes` -- outdoor run with native running
  power on every sample and *sparse* heart rate (~60% coverage, real ``None``
  holes).
* :func:`run_no_gps_fit_bytes` -- outdoor run with NO GPS position and NO altitude
  (decoded lat/long/altitude entirely ``None``).
* :func:`ride_no_power_fit_bytes` -- ride with NO power channel (HR + speed only).
* :func:`ride_power_dropout_fit_bytes` -- ride long enough (90 records, 89 s
  span) to compute a real normalized power, with a genuine 10 s mid-stream
  power-channel dropout (real ``None`` holes, contiguous rather than sparse)
  between two distinguishable plateaus.
* :func:`strength_no_sets_fit_bytes` -- strength session with HR-only records and
  NO ``set_mesgs`` at all (decoded ``sets`` is empty).
* :func:`session_dev_fields_fit_bytes` -- run whose session carries HealthFit
  developer fields, including a 16-byte ``SESSION UUID`` and the recognized
  supplementals (``WORKOUT RPE ESTIMATED``, ``SESSION WEATHER HUMIDITY``,
  ``AVG METs``, ``SESSION INDOOR``).
* :func:`reexport_a_fit_bytes` / :func:`reexport_b_fit_bytes` -- a re-export pair
  recording the SAME ``SESSION UUID`` yet different bytes (differing serial), so
  their sha256 hashes differ while the stable session identity is identical.

Running-dynamics families (spec running-dynamics), the raw shapes measured in
real Stryd and HealthFit files:

* :func:`developer_field_run_fit_bytes` -- the one developer-field encoding helper:
  given :class:`DevFieldSpec` descriptions and per-record values it writes a
  valid run, every developer field registered before the first write.
* :func:`stryd_run_fit_bytes` -- run with twelve Stryd-shaped field descriptions
  (key != definition number), placeholder zeros at record 0 and across a pause,
  a uint16 sentinel, float32 values, four laps without heart rate or cadence.
* :func:`run_native_dynamics_fit_bytes` -- the HealthFit-copy shape: native
  vertical oscillation, stance time and vertical ratio, and a ``SESSION UUID``
  containing 255.

Values passed to the Encoder are real-world units (m, m/s, m, bpm, W, kg); the
Encoder un-applies FIT scale/offset internally, so decoding with
``apply_scale_and_offset=True`` returns the same real-world values. Positions are
passed as semicircles via :func:`to_semicircles`.

The ``*_messages`` builders (:func:`run_messages`, :func:`ride_messages`,
:func:`strength_messages`, :func:`minimal_messages`) return the *decoded* message
dict (``dict[str, list[dict]]``) so later extractor unit-tests can work with
synthetic message dicts directly, identical to what the real decoder produces.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from garmin_fit_sdk import Decoder, Encoder, Stream  # type: ignore[import-untyped]
from garmin_fit_sdk.fit import BASE_TYPE  # type: ignore[import-untyped]

# Documentation-only aliases (this module is pulled into mypy's scope transitively,
# but these two are deliberately untyped shorthands for FIT message payloads).
Mesg = dict[str, object]
MessagesDict = dict[str, list[dict[str, object]]]

# --- Deterministic constants ------------------------------------------------

FIT_TIMESTAMP_BASE = 1_000_000_000
"""Fixed FIT-epoch second used as t0 for every fixture (never wall-clock time)."""

# Global FIT message numbers, from the SDK profile ``mesg_num`` type table.
_MESG_FILE_ID = 0
_MESG_SPORT = 12
_MESG_SESSION = 18
_MESG_LAP = 19
_MESG_RECORD = 20
_MESG_DEVICE_INFO = 23
_MESG_ACTIVITY = 34
_MESG_SET = 225
_MESG_DEVELOPER_DATA_ID = 207
_MESG_FIELD_DESCRIPTION = 206

_SEMICIRCLES_PER_DEGREE = 2**31 / 180


def to_semicircles(degrees: float) -> int:
    """Convert decimal degrees to FIT semicircles: ``round(deg * 2**31 / 180)``."""
    return round(degrees * _SEMICIRCLES_PER_DEGREE)


# --- Encode / decode helpers ------------------------------------------------


def encode(mesgs: Sequence[Mesg]) -> bytes:
    """Encode an ordered sequence of profile messages into ``.fit`` bytes.

    Each message dict must carry a ``mesg_num`` key (the global FIT message
    number); the remaining keys are profile field names in real-world units.
    """
    encoder = Encoder()
    for mesg in mesgs:
        encoder.write_mesg(mesg)
    return bytes(encoder.close())


def decode_messages(data: bytes) -> tuple[MessagesDict, list[object]]:
    """Decode ``.fit`` bytes with the flags task 2's decode wrapper mirrors.

    ``apply_scale_and_offset=True``, ``expand_components=True``,
    ``convert_datetimes_to_dates=False``; SDK defaults are kept for the rest. The
    stream is reset before reading (both ``is_fit``/``check_integrity`` advance
    it -- the documented pitfall).
    """
    stream = Stream.from_byte_array(data)
    decoder = Decoder(stream)
    stream.reset()
    messages, errors = decoder.read(
        apply_scale_and_offset=True,
        expand_components=True,
        convert_datetimes_to_dates=False,
    )
    return messages, list(errors)


# --- Shared message builders ------------------------------------------------


def _file_id(
    serial: int,
    *,
    manufacturer: str = "garmin",
    product: int = 1,
    time_created: int = FIT_TIMESTAMP_BASE,
) -> Mesg:
    return {
        "mesg_num": _MESG_FILE_ID,
        "type": "activity",
        "manufacturer": manufacturer,
        "product": product,
        "serial_number": serial,
        "time_created": time_created,
    }


def _device_info(
    serial: int, product_name: str, *, manufacturer: str = "garmin"
) -> Mesg:
    return {
        "mesg_num": _MESG_DEVICE_INFO,
        "timestamp": FIT_TIMESTAMP_BASE,
        "device_index": 0,
        "manufacturer": manufacturer,
        "serial_number": serial,
        "product": 1,
        "software_version": 4.2,
        "battery_status": "good",
        "product_name": product_name,
    }


def _activity(end_offset: int, total_timer_time_s: float) -> Mesg:
    return {
        "mesg_num": _MESG_ACTIVITY,
        "timestamp": FIT_TIMESTAMP_BASE + end_offset,
        "total_timer_time": total_timer_time_s,
        "num_sessions": 1,
        "type": "manual",
    }


# --- Run fixture ------------------------------------------------------------

_RUN_RECORD_COUNT = 10
_RUN_START_LAT_DEG = 40.0
_RUN_START_LON_DEG = -105.0
_RUN_SPEED_MPS = 3.3
_RUN_BASE_ALTITUDE_M = 1600.0
# Inclusive record-index windows for the three laps (cover all 10 records).
_RUN_LAP_WINDOWS = ((0, 3), (4, 6), (7, 9))


def _run_records() -> list[Mesg]:
    records: list[Mesg] = []
    for i in range(_RUN_RECORD_COUNT):
        records.append(
            {
                "mesg_num": _MESG_RECORD,
                "timestamp": FIT_TIMESTAMP_BASE + i,
                "position_lat": to_semicircles(_RUN_START_LAT_DEG + 0.0001 * i),
                "position_long": to_semicircles(_RUN_START_LON_DEG + 0.0001 * i),
                "distance": _RUN_SPEED_MPS * i,
                "enhanced_speed": _RUN_SPEED_MPS,
                "enhanced_altitude": _RUN_BASE_ALTITUDE_M + i,
                "heart_rate": 120 + 3 * i,
                "cadence": 85,
                "temperature": 20,
            }
        )
    return records


def _run_laps() -> list[Mesg]:
    laps: list[Mesg] = []
    for start, end in _RUN_LAP_WINDOWS:
        heart_rates = [120 + 3 * i for i in range(start, end + 1)]
        laps.append(
            {
                "mesg_num": _MESG_LAP,
                "start_time": FIT_TIMESTAMP_BASE + start,
                "timestamp": FIT_TIMESTAMP_BASE + end,
                "sport": "running",
                "sub_sport": "generic",
                "total_elapsed_time": float(end - start + 1),
                "total_timer_time": float(end - start + 1),
                "total_distance": _RUN_SPEED_MPS * (end - start),
                "avg_heart_rate": round(sum(heart_rates) / len(heart_rates)),
                "max_heart_rate": max(heart_rates),
                "avg_speed": _RUN_SPEED_MPS,
                "max_speed": _RUN_SPEED_MPS,
                "avg_cadence": 85,
                "total_ascent": end - start,
                "total_descent": 0,
            }
        )
    return laps


def _run_session() -> Mesg:
    return {
        "mesg_num": _MESG_SESSION,
        "start_time": FIT_TIMESTAMP_BASE,
        "timestamp": FIT_TIMESTAMP_BASE + (_RUN_RECORD_COUNT - 1),
        "sport": "running",
        "sub_sport": "generic",
        "total_elapsed_time": float(_RUN_RECORD_COUNT - 1),
        "total_timer_time": float(_RUN_RECORD_COUNT - 1),
        "total_distance": _RUN_SPEED_MPS * (_RUN_RECORD_COUNT - 1),
        "total_calories": 60,
        "total_ascent": _RUN_RECORD_COUNT - 1,
        "total_descent": 0,
        "avg_heart_rate": 133,
        "max_heart_rate": 120 + 3 * (_RUN_RECORD_COUNT - 1),
        "avg_speed": _RUN_SPEED_MPS,
        "max_speed": _RUN_SPEED_MPS,
        "avg_cadence": 85,
        "max_cadence": 85,
    }


def run_mesgs() -> list[Mesg]:
    """Ordered encoder messages for the outdoor-run fixture."""
    mesgs: list[Mesg] = [
        _file_id(1001),
        _device_info(1001, "SyntheticRunWatch"),
        {"mesg_num": _MESG_SPORT, "sport": "running", "sub_sport": "generic"},
    ]
    mesgs.extend(_run_records())
    mesgs.extend(_run_laps())
    mesgs.append(_run_session())
    mesgs.append(_activity(_RUN_RECORD_COUNT - 1, float(_RUN_RECORD_COUNT - 1)))
    return mesgs


# --- Ride fixture -----------------------------------------------------------

_RIDE_RECORD_COUNT = 10
_RIDE_SPEED_MPS = 8.0


def _ride_records() -> list[Mesg]:
    records: list[Mesg] = []
    for i in range(_RIDE_RECORD_COUNT):
        records.append(
            {
                "mesg_num": _MESG_RECORD,
                "timestamp": FIT_TIMESTAMP_BASE + i,
                # Alternating power (mean 200 W) so variability is non-trivial;
                # plain ``speed`` (not enhanced) exercises the fallback channel.
                "power": 190 if i % 2 == 0 else 210,
                "heart_rate": 130 + 2 * i,
                "cadence": 90,
                "speed": _RIDE_SPEED_MPS,
                "distance": _RIDE_SPEED_MPS * i,
            }
        )
    return records


def _ride_session() -> Mesg:
    return {
        "mesg_num": _MESG_SESSION,
        "start_time": FIT_TIMESTAMP_BASE,
        "timestamp": FIT_TIMESTAMP_BASE + (_RIDE_RECORD_COUNT - 1),
        "sport": "cycling",
        "sub_sport": "generic",
        "total_elapsed_time": float(_RIDE_RECORD_COUNT - 1),
        "total_timer_time": float(_RIDE_RECORD_COUNT - 1),
        "total_distance": _RIDE_SPEED_MPS * (_RIDE_RECORD_COUNT - 1),
        "total_calories": 80,
        "avg_power": 200,
        "max_power": 210,
        "avg_heart_rate": 139,
        "max_heart_rate": 130 + 2 * (_RIDE_RECORD_COUNT - 1),
        "avg_cadence": 90,
        "max_cadence": 90,
        "avg_speed": _RIDE_SPEED_MPS,
        "max_speed": _RIDE_SPEED_MPS,
    }


def ride_mesgs() -> list[Mesg]:
    """Ordered encoder messages for the ride fixture."""
    mesgs: list[Mesg] = [
        _file_id(1002),
        _device_info(1002, "SyntheticRideComputer"),
        {"mesg_num": _MESG_SPORT, "sport": "cycling", "sub_sport": "generic"},
    ]
    mesgs.extend(_ride_records())
    mesgs.append(_ride_session())
    mesgs.append(_activity(_RIDE_RECORD_COUNT - 1, float(_RIDE_RECORD_COUNT - 1)))
    return mesgs


# --- Small parameterized sport fixture (rowing / hiking / walking / etc.) ---
#
# A small, generic sport-labelled fixture for tests that need a document for a
# sport ``run``/``ride``/``strength`` don't cover (e.g. a Modality.OTHER hike
# or a rowing/walking document), or several non-colliding documents of the SAME
# sport (distinct ``serial``/``timestamp_offset`` per call). Built from the same
# shared ``_file_id``/``_device_info``/``_activity`` private helpers as every
# other fixture family in this module, so callers outside ``builder`` have no
# reason to reach into those directly.

_SMALL_SPORT_RECORD_COUNT = 5
_SMALL_SPORT_SPEED_MPS = 1.2
_SMALL_SPORT_HR_BASE = 100

_HIKE_SERIAL = 1099


def small_sport_fit_bytes(
    serial: int,
    fit_sport: str,
    *,
    sub_sport: str = "generic",
    timestamp_offset: int = 0,
    record_count: int = _SMALL_SPORT_RECORD_COUNT,
    speed_mps: float = _SMALL_SPORT_SPEED_MPS,
    hr_base: int = _SMALL_SPORT_HR_BASE,
) -> bytes:
    """Encoded ``.fit`` bytes for a small, parameterized sport fixture.

    Records carry only ``heart_rate`` (``hr_base + i``) and ``distance``
    (``speed_mps * i``) -- no GPS, power, or laps. ``timestamp_offset`` (in FIT
    seconds, i.e. from :data:`FIT_TIMESTAMP_BASE`) lets callers render several
    documents of the same sport into one data root without filename collisions.
    Deterministic: fixed constants only, no wall-clock time.
    """
    base = FIT_TIMESTAMP_BASE + timestamp_offset
    mesgs: list[Mesg] = [
        _file_id(serial),
        _device_info(serial, f"Synthetic{fit_sport.title()}Watch"),
        {"mesg_num": _MESG_SPORT, "sport": fit_sport, "sub_sport": sub_sport},
    ]
    for i in range(record_count):
        mesgs.append(
            {
                "mesg_num": _MESG_RECORD,
                "timestamp": base + i,
                "heart_rate": hr_base + i,
                "distance": speed_mps * i,
            }
        )
    mesgs.append(
        {
            "mesg_num": _MESG_SESSION,
            "start_time": base,
            "timestamp": base + (record_count - 1),
            "sport": fit_sport,
            "sub_sport": sub_sport,
            "total_elapsed_time": float(record_count - 1),
            "total_timer_time": float(record_count - 1),
            "total_distance": speed_mps * (record_count - 1),
            "avg_heart_rate": round(hr_base + (record_count - 1) / 2),
            "max_heart_rate": hr_base + (record_count - 1),
        }
    )
    mesgs.append(_activity(record_count - 1, float(record_count - 1)))
    return encode(mesgs)


def hike_fit_bytes() -> bytes:
    """Encoded ``.fit`` bytes for a small ``Modality.OTHER`` hike document.

    ``Sport.HIKE`` via the ``"hiking"`` FIT sport label; heart rate and
    distance only, no GPS/power/laps -- a thin :func:`small_sport_fit_bytes`
    call with a fixed serial, so it is deterministic across builds.
    """
    return small_sport_fit_bytes(_HIKE_SERIAL, "hiking")


# --- Strength fixture -------------------------------------------------------

_STRENGTH_RECORD_COUNT = 6


def _strength_records() -> list[Mesg]:
    return [
        {
            "mesg_num": _MESG_RECORD,
            "timestamp": FIT_TIMESTAMP_BASE + i,
            "heart_rate": 100 + 2 * i,
        }
        for i in range(_STRENGTH_RECORD_COUNT)
    ]


def _strength_sets() -> list[Mesg]:
    return [
        # 0: fully populated -- barbell bench press, 60 kg x 10.
        {
            "mesg_num": _MESG_SET,
            "message_index": 0,
            "start_time": FIT_TIMESTAMP_BASE + 10,
            "timestamp": FIT_TIMESTAMP_BASE + 50,
            "duration": 40.0,
            "repetitions": 10,
            "weight": 60.0,
            "set_type": "active",
            "category": [0],  # bench_press
            "category_subtype": [1],  # barbell_bench_press
        },
        # 1: bodyweight -- weight 0.0 is a recorded true zero, not missing data.
        {
            "mesg_num": _MESG_SET,
            "message_index": 1,
            "start_time": FIT_TIMESTAMP_BASE + 120,
            "timestamp": FIT_TIMESTAMP_BASE + 165,
            "duration": 45.0,
            "repetitions": 15,
            "weight": 0.0,
            "set_type": "active",
            "category": [22],  # push_up
            "category_subtype": [1],
        },
        # 2: partial -- weight and repetitions deliberately absent; the subtype
        #    999 has no profile name, so name resolution must yield None.
        {
            "mesg_num": _MESG_SET,
            "message_index": 2,
            "start_time": FIT_TIMESTAMP_BASE + 240,
            "timestamp": FIT_TIMESTAMP_BASE + 270,
            "duration": 30.0,
            "set_type": "active",
            "category": [0],  # bench_press
            "category_subtype": [999],  # unresolvable
        },
        # 3: rest -- only type + duration recorded.
        {
            "mesg_num": _MESG_SET,
            "message_index": 3,
            "start_time": FIT_TIMESTAMP_BASE + 300,
            "timestamp": FIT_TIMESTAMP_BASE + 330,
            "duration": 30.0,
            "set_type": "rest",
        },
    ]


def _strength_session() -> Mesg:
    return {
        "mesg_num": _MESG_SESSION,
        "start_time": FIT_TIMESTAMP_BASE,
        "timestamp": FIT_TIMESTAMP_BASE + 360,
        "sport": "training",
        "sub_sport": "strength_training",
        "total_elapsed_time": 360.0,
        "total_timer_time": 360.0,
        "total_calories": 120,
        "avg_heart_rate": 105,
        "max_heart_rate": 130,
    }


def strength_mesgs() -> list[Mesg]:
    """Ordered encoder messages for the strength-session fixture."""
    mesgs: list[Mesg] = [
        _file_id(1003),
        _device_info(1003, "SyntheticGymWatch"),
        {
            "mesg_num": _MESG_SPORT,
            "sport": "training",
            "sub_sport": "strength_training",
        },
    ]
    mesgs.extend(_strength_records())
    mesgs.extend(_strength_sets())
    mesgs.append(_strength_session())
    mesgs.append(_activity(360, 360.0))
    return mesgs


# --- Strength session WITH GPS positions (route-maps map-guard fixture) ------
#
# A strength session -- ``sport: "training"`` / ``sub_sport: "strength_training"``,
# so the decoded modality is STRENGTH -- whose records ALSO carry a complete GPS
# position pair. This is the exact shape the sync engine's strength map-guard
# must suppress: after ``parse_fit`` the activity is STRENGTH modality YET
# ``plan_map`` over its decoded lat/long returns a NON-None plan. It combines the
# GPS-bearing record shape (cf. :func:`_run_records`) with the strength
# sets/session, so the engine's ``modality is not STRENGTH`` guard -- not an
# absent route -- is the only thing keeping tiles from being resolved for it.
# Additive: reuses the existing strength sets/session, touching no other fixture.

_STRENGTH_GPS_RECORD_COUNT = 6
_STRENGTH_GPS_START_LAT_DEG = 40.0
_STRENGTH_GPS_START_LON_DEG = -105.0


def _strength_gps_records() -> list[Mesg]:
    # Heart rate (as in the HR-carrying strength records) PLUS a complete GPS
    # position pair on every sample, so the decoded lat/long channels frame a
    # real route and ``plan_map`` returns a non-None plan.
    return [
        {
            "mesg_num": _MESG_RECORD,
            "timestamp": FIT_TIMESTAMP_BASE + i,
            "position_lat": to_semicircles(_STRENGTH_GPS_START_LAT_DEG + 0.0001 * i),
            "position_long": to_semicircles(_STRENGTH_GPS_START_LON_DEG + 0.0001 * i),
            "heart_rate": 100 + 2 * i,
        }
        for i in range(_STRENGTH_GPS_RECORD_COUNT)
    ]


def strength_with_gps_mesgs() -> list[Mesg]:
    """Ordered messages: strength session whose records carry GPS position.

    STRENGTH modality (``strength_training`` sub-sport) yet a complete position
    pair per record, so ``plan_map`` over the decoded lat/long returns non-None.
    Reuses the strength sets/session so it renders exactly as the strength view.
    """
    mesgs: list[Mesg] = [
        _file_id(1017),
        _device_info(1017, "SyntheticGymGpsWatch"),
        {
            "mesg_num": _MESG_SPORT,
            "sport": "training",
            "sub_sport": "strength_training",
        },
    ]
    mesgs.extend(_strength_gps_records())
    mesgs.extend(_strength_sets())
    mesgs.append(_strength_session())
    mesgs.append(_activity(360, 360.0))
    return mesgs


def strength_with_gps_fit_bytes() -> bytes:
    """Encoded strength session whose records carry GPS (STRENGTH modality + route)."""
    return encode(strength_with_gps_mesgs())


# --- Minimal fixture (records only, no session) -----------------------------

_MINIMAL_RECORD_COUNT = 4


def minimal_mesgs() -> list[Mesg]:
    """Ordered encoder messages for the minimal fixture: records, no session."""
    mesgs: list[Mesg] = [_file_id(1004)]
    for i in range(_MINIMAL_RECORD_COUNT):
        mesgs.append(
            {
                "mesg_num": _MESG_RECORD,
                "timestamp": FIT_TIMESTAMP_BASE + i,
                "heart_rate": 100 + i,
                "distance": float(i),
            }
        )
    return mesgs


# --- Real-shaped variants (task 1.6) ----------------------------------------
#
# These reproduce the shapes found in the user's real HealthFit corpus so the
# workout-docs layer can be exercised against them: native running power with
# sparse heart rate, an outdoor run without GPS/altitude, a ride without power, a
# strength session that carries NO ``set_mesgs`` (HR-only records), and
# session-scoped developer fields (including a 16-byte ``SESSION UUID``) plus a
# re-export pair (same UUID, different bytes). Every value is a fixed constant, so
# each variant is byte-identical on rebuild (workout-docs Req 4.1).

# --- Run with native power + sparse heart rate ---

_NP_RECORD_COUNT = 10
# Heart rate is deliberately absent on these record indices, leaving 6 of 10
# samples covered (~60%) so the decoded ``heart_rate_bpm`` array has real ``None``
# holes rather than a fabricated fill.
_NP_HR_MISSING_INDICES = frozenset({2, 5, 8, 9})
_NP_START_LAT_DEG = 40.0
_NP_START_LON_DEG = -105.0
_NP_SPEED_MPS = 3.3
_NP_BASE_ALTITUDE_M = 1600.0


def _native_power_sparse_hr_records() -> list[Mesg]:
    records: list[Mesg] = []
    for i in range(_NP_RECORD_COUNT):
        record: Mesg = {
            "mesg_num": _MESG_RECORD,
            "timestamp": FIT_TIMESTAMP_BASE + i,
            "position_lat": to_semicircles(_NP_START_LAT_DEG + 0.0001 * i),
            "position_long": to_semicircles(_NP_START_LON_DEG + 0.0001 * i),
            "distance": _NP_SPEED_MPS * i,
            "enhanced_speed": _NP_SPEED_MPS,
            "enhanced_altitude": _NP_BASE_ALTITUDE_M + i,
            # Native running power on every sample (mean 245 W, non-trivial spread).
            "power": 240 if i % 2 == 0 else 250,
            "cadence": 85,
            "temperature": 20,
        }
        if i not in _NP_HR_MISSING_INDICES:
            record["heart_rate"] = 120 + 3 * i
        records.append(record)
    return records


def _native_power_sparse_hr_session() -> Mesg:
    return {
        "mesg_num": _MESG_SESSION,
        "start_time": FIT_TIMESTAMP_BASE,
        "timestamp": FIT_TIMESTAMP_BASE + (_NP_RECORD_COUNT - 1),
        "sport": "running",
        "sub_sport": "generic",
        "total_elapsed_time": float(_NP_RECORD_COUNT - 1),
        "total_timer_time": float(_NP_RECORD_COUNT - 1),
        "total_distance": _NP_SPEED_MPS * (_NP_RECORD_COUNT - 1),
        "total_calories": 65,
        "total_ascent": _NP_RECORD_COUNT - 1,
        "total_descent": 0,
        "avg_power": 245,
        "max_power": 250,
        "avg_heart_rate": 131,
        "max_heart_rate": 141,
        "avg_speed": _NP_SPEED_MPS,
        "max_speed": _NP_SPEED_MPS,
        "avg_cadence": 85,
        "max_cadence": 85,
    }


def run_native_power_sparse_hr_mesgs() -> list[Mesg]:
    """Ordered messages: outdoor run with native power and sparse heart rate."""
    mesgs: list[Mesg] = [
        _file_id(1010),
        _device_info(1010, "SyntheticPowerRunWatch"),
        {"mesg_num": _MESG_SPORT, "sport": "running", "sub_sport": "generic"},
    ]
    mesgs.extend(_native_power_sparse_hr_records())
    mesgs.append(_native_power_sparse_hr_session())
    mesgs.append(_activity(_NP_RECORD_COUNT - 1, float(_NP_RECORD_COUNT - 1)))
    return mesgs


# --- Outdoor run without GPS / altitude ---

_NOGPS_RECORD_COUNT = 10
_NOGPS_SPEED_MPS = 3.2


def _no_gps_records() -> list[Mesg]:
    # No ``position_lat``/``position_long`` and no altitude channel at all, so the
    # decoded lat/long/altitude arrays are entirely ``None`` (GPS-off outdoor run).
    return [
        {
            "mesg_num": _MESG_RECORD,
            "timestamp": FIT_TIMESTAMP_BASE + i,
            "distance": _NOGPS_SPEED_MPS * i,
            "speed": _NOGPS_SPEED_MPS,
            "heart_rate": 120 + 2 * i,
            "cadence": 84,
        }
        for i in range(_NOGPS_RECORD_COUNT)
    ]


def _no_gps_session() -> Mesg:
    return {
        "mesg_num": _MESG_SESSION,
        "start_time": FIT_TIMESTAMP_BASE,
        "timestamp": FIT_TIMESTAMP_BASE + (_NOGPS_RECORD_COUNT - 1),
        "sport": "running",
        "sub_sport": "generic",
        "total_elapsed_time": float(_NOGPS_RECORD_COUNT - 1),
        "total_timer_time": float(_NOGPS_RECORD_COUNT - 1),
        "total_distance": _NOGPS_SPEED_MPS * (_NOGPS_RECORD_COUNT - 1),
        "total_calories": 55,
        # No ascent/descent -- there is no altitude channel to derive climb from.
        "avg_heart_rate": 129,
        "max_heart_rate": 120 + 2 * (_NOGPS_RECORD_COUNT - 1),
        "avg_speed": _NOGPS_SPEED_MPS,
        "max_speed": _NOGPS_SPEED_MPS,
        "avg_cadence": 84,
        "max_cadence": 84,
    }


def run_no_gps_mesgs() -> list[Mesg]:
    """Ordered messages: outdoor run with no GPS position and no altitude."""
    mesgs: list[Mesg] = [
        _file_id(1011),
        _device_info(1011, "SyntheticNoGpsWatch"),
        {"mesg_num": _MESG_SPORT, "sport": "running", "sub_sport": "generic"},
    ]
    mesgs.extend(_no_gps_records())
    mesgs.append(_no_gps_session())
    mesgs.append(_activity(_NOGPS_RECORD_COUNT - 1, float(_NOGPS_RECORD_COUNT - 1)))
    return mesgs


# --- Ride without power ---

_RIDE_NP_RECORD_COUNT = 10
_RIDE_NP_SPEED_MPS = 8.0


def _ride_no_power_records() -> list[Mesg]:
    # No ``power`` channel, so the decoded ``power_w`` array is entirely ``None``
    # and the hero chart falls back to the heart-rate + speed pairing.
    return [
        {
            "mesg_num": _MESG_RECORD,
            "timestamp": FIT_TIMESTAMP_BASE + i,
            "heart_rate": 130 + 2 * i,
            "cadence": 90,
            "speed": _RIDE_NP_SPEED_MPS,
            "distance": _RIDE_NP_SPEED_MPS * i,
        }
        for i in range(_RIDE_NP_RECORD_COUNT)
    ]


def _ride_no_power_session() -> Mesg:
    return {
        "mesg_num": _MESG_SESSION,
        "start_time": FIT_TIMESTAMP_BASE,
        "timestamp": FIT_TIMESTAMP_BASE + (_RIDE_NP_RECORD_COUNT - 1),
        "sport": "cycling",
        "sub_sport": "generic",
        "total_elapsed_time": float(_RIDE_NP_RECORD_COUNT - 1),
        "total_timer_time": float(_RIDE_NP_RECORD_COUNT - 1),
        "total_distance": _RIDE_NP_SPEED_MPS * (_RIDE_NP_RECORD_COUNT - 1),
        "total_calories": 70,
        # No avg_power / max_power at all -- the absent-power ride shape.
        "avg_heart_rate": 139,
        "max_heart_rate": 130 + 2 * (_RIDE_NP_RECORD_COUNT - 1),
        "avg_cadence": 90,
        "max_cadence": 90,
        "avg_speed": _RIDE_NP_SPEED_MPS,
        "max_speed": _RIDE_NP_SPEED_MPS,
    }


def ride_no_power_mesgs() -> list[Mesg]:
    """Ordered messages: ride with no power channel (HR + speed only)."""
    mesgs: list[Mesg] = [
        _file_id(1012),
        _device_info(1012, "SyntheticNoPowerBike"),
        {"mesg_num": _MESG_SPORT, "sport": "cycling", "sub_sport": "generic"},
    ]
    mesgs.extend(_ride_no_power_records())
    mesgs.append(_ride_no_power_session())
    mesgs.append(_activity(_RIDE_NP_RECORD_COUNT - 1, float(_RIDE_NP_RECORD_COUNT - 1)))
    return mesgs


# --- Ride with a mid-stream power dropout ---
#
# Unlike every other ride/power fixture above (10 records, span 9 s -- too
# short to ever clear NP_MIN_SPAN_S, so none of them exercises a real
# normalized-power VALUE), this one is long enough (90 records, span 89 s) to
# actually compute NP, and carries a genuine 10 s power-channel dropout
# (real ``None`` holes, the same "sparse channel" shape
# ``_native_power_sparse_hr_records`` above uses for heart rate) between two
# distinguishable power plateaus -- so the committed golden this builds
# demonstrates the 2026-07-30 absent-power-sample forward-fill ruling
# (``fitdocs.metrics.power._resample_power_1hz``) on a real rendered
# document, not only in a unit test.

_POWER_DROPOUT_RECORD_COUNT = 90
_POWER_DROPOUT_SPEED_MPS = 7.5
# Contiguous dropout in the middle of the ride -- a device losing the power
# signal for ten seconds -- not sparse/random holes.
_POWER_DROPOUT_INDICES = frozenset(range(40, 50))
_POWER_DROPOUT_LOW_W = 220
_POWER_DROPOUT_HIGH_W = 260


def _power_dropout_records() -> list[Mesg]:
    records: list[Mesg] = []
    for i in range(_POWER_DROPOUT_RECORD_COUNT):
        record: Mesg = {
            "mesg_num": _MESG_RECORD,
            "timestamp": FIT_TIMESTAMP_BASE + i,
            "heart_rate": 130 + (i % 20),
            "cadence": 88,
            "speed": _POWER_DROPOUT_SPEED_MPS,
            "distance": _POWER_DROPOUT_SPEED_MPS * i,
        }
        if i not in _POWER_DROPOUT_INDICES:
            record["power"] = _POWER_DROPOUT_LOW_W if i < 40 else _POWER_DROPOUT_HIGH_W
        records.append(record)
    return records


def _power_dropout_session() -> Mesg:
    n = _POWER_DROPOUT_RECORD_COUNT
    recorded_count = n - len(_POWER_DROPOUT_INDICES)
    avg_power = round(
        (40 * _POWER_DROPOUT_LOW_W + 40 * _POWER_DROPOUT_HIGH_W) / recorded_count
    )
    return {
        "mesg_num": _MESG_SESSION,
        "start_time": FIT_TIMESTAMP_BASE,
        "timestamp": FIT_TIMESTAMP_BASE + (n - 1),
        "sport": "cycling",
        "sub_sport": "generic",
        "total_elapsed_time": float(n - 1),
        "total_timer_time": float(n - 1),
        "total_distance": _POWER_DROPOUT_SPEED_MPS * (n - 1),
        "total_calories": 210,
        "avg_power": avg_power,
        "max_power": _POWER_DROPOUT_HIGH_W,
        "avg_heart_rate": 140,
        "max_heart_rate": 149,
        "avg_cadence": 88,
        "max_cadence": 88,
        "avg_speed": _POWER_DROPOUT_SPEED_MPS,
        "max_speed": _POWER_DROPOUT_SPEED_MPS,
    }


def ride_power_dropout_mesgs() -> list[Mesg]:
    """Ordered messages: ride long enough to compute NP, with a genuine 10 s
    mid-stream power-channel dropout between two distinguishable plateaus
    (220 W then 260 W)."""
    mesgs: list[Mesg] = [
        _file_id(1014),
        _device_info(1014, "SyntheticPowerDropoutBike"),
        {"mesg_num": _MESG_SPORT, "sport": "cycling", "sub_sport": "generic"},
    ]
    mesgs.extend(_power_dropout_records())
    mesgs.append(_power_dropout_session())
    mesgs.append(
        _activity(
            _POWER_DROPOUT_RECORD_COUNT - 1, float(_POWER_DROPOUT_RECORD_COUNT - 1)
        )
    )
    return mesgs


def ride_power_dropout_fit_bytes() -> bytes:
    """Encoded ride long enough to compute NP, with a genuine mid-stream
    power dropout (see :func:`ride_power_dropout_mesgs`)."""
    return encode(ride_power_dropout_mesgs())


# --- Strength session: HR-only records, NO set messages ---

_STRENGTH_NOSETS_RECORD_COUNT = 8
# Heart rate drops on these indices -- sparse HR is a real strength-file trait.
_STRENGTH_NOSETS_HR_MISSING_INDICES = frozenset({3, 6})


def _strength_no_sets_records() -> list[Mesg]:
    # Records carry ONLY timestamp + heart rate (no distance, no power) -- the
    # exact shape of the user's real strength exports.
    records: list[Mesg] = []
    for i in range(_STRENGTH_NOSETS_RECORD_COUNT):
        record: Mesg = {
            "mesg_num": _MESG_RECORD,
            "timestamp": FIT_TIMESTAMP_BASE + i,
        }
        if i not in _STRENGTH_NOSETS_HR_MISSING_INDICES:
            record["heart_rate"] = 100 + 2 * i
        records.append(record)
    return records


def _strength_no_sets_session() -> Mesg:
    return {
        "mesg_num": _MESG_SESSION,
        "start_time": FIT_TIMESTAMP_BASE,
        "timestamp": FIT_TIMESTAMP_BASE + (_STRENGTH_NOSETS_RECORD_COUNT - 1),
        "sport": "training",
        "sub_sport": "strength_training",
        "total_elapsed_time": float(_STRENGTH_NOSETS_RECORD_COUNT - 1),
        "total_timer_time": float(_STRENGTH_NOSETS_RECORD_COUNT - 1),
        "total_calories": 90,
        "avg_heart_rate": 105,
        "max_heart_rate": 114,
        # No total_distance and no power fields -- HR-summary shape only.
    }


def strength_no_sets_mesgs() -> list[Mesg]:
    """Ordered messages: strength session, HR-only records, NO set messages."""
    mesgs: list[Mesg] = [
        _file_id(1013),
        _device_info(1013, "SyntheticGymHrWatch"),
        {
            "mesg_num": _MESG_SPORT,
            "sport": "training",
            "sub_sport": "strength_training",
        },
    ]
    mesgs.extend(_strength_no_sets_records())
    mesgs.append(_strength_no_sets_session())
    mesgs.append(
        _activity(
            _STRENGTH_NOSETS_RECORD_COUNT - 1,
            float(_STRENGTH_NOSETS_RECORD_COUNT - 1),
        )
    )
    # NB: deliberately NO ``_MESG_SET`` messages appended -> decoded sets is empty.
    return mesgs


# --- Session-scoped developer fields + re-export pair ---

# A fixed 16-byte session identifier (distinct byte values) -- the HealthFit
# ``SESSION UUID`` shape. Held IDENTICAL across the re-export pair so both files
# resolve to the same downstream activity identity despite differing bytes.
_SESSION_UUID_BYTES: tuple[int, ...] = tuple(range(100, 116))

# HealthFit session-scoped developer fields as ``(name, fit_base_type_id,
# array_len)``; ``array_len`` is ``None`` for a scalar. The UUID is a 16-long
# UINT8 array.
#
# These MIRROR HealthFit's real encoding rather than an idealized one, because an
# idealized fixture is exactly what let the 100x ``Avg METs`` defect ship: METs
# and humidity are UINT16 HUNDREDTHS (integer base types cannot express 9.5, so
# the writer stores 950), and the field descriptions declare NO ``scale``. Values
# stay integers, so the encoded bytes are stable (Req 4.1).
_SESSION_DEV_FIELD_SPECS: tuple[tuple[str, int, int | None], ...] = (
    ("SESSION UUID", BASE_TYPE["UINT8"], 16),
    ("SESSION INDOOR", BASE_TYPE["UINT8"], None),
    ("SESSION WEATHER HUMIDITY", BASE_TYPE["UINT16"], None),
    ("WORKOUT RPE ESTIMATED", BASE_TYPE["UINT8"], None),
    ("AVG METs", BASE_TYPE["UINT16"], None),
)

_SESSION_DEV_FIELD_VALUES: dict[str, object] = {
    "SESSION UUID": list(_SESSION_UUID_BYTES),
    "SESSION INDOOR": 0,
    "SESSION WEATHER HUMIDITY": 5500,  # hundredths -> 55%
    "WORKOUT RPE ESTIMATED": 1,  # a flag, not a value: only ever 0/1 in the wild
    "AVG METs": 950,  # hundredths -> 9.5
}


def _encode_run_with_developer_fields(
    serial: int,
    scale_overrides: dict[str, tuple[int | None, int | None]] | None = None,
    *,
    time_created: int = FIT_TIMESTAMP_BASE,
) -> bytes:
    """Encode a valid run whose session carries the HealthFit developer fields.

    Follows the SDK convention (see ``tests/ingest/test_summary.py``): each
    developer field is registered on the encoder BEFORE any message is written,
    then the ``developer_data_id`` and ``field_description`` messages are emitted
    ahead of the session that records the values -- keyed by the SAME string
    handles the encoder was given. ``serial`` distinguishes the re-export pair's
    bytes while every recorded developer value (the ``SESSION UUID`` included)
    stays identical, so the pair shares one stable identity yet different sha256.

    ``scale_overrides`` optionally declares a ``(scale, offset)`` pair on a
    named field's description (either element ``None`` leaves that term
    UNDECLARED on the wire, matching ``field_description``'s real shape); a
    name absent from the mapping declares neither, as every field does by
    default. ``time_created`` is the ``file_id`` creation time (FIT-epoch seconds).
    """
    dev_data_id: Mesg = {
        "mesg_num": _MESG_DEVELOPER_DATA_ID,
        "developer_data_index": 0,
        "application_id": list(range(16)),
    }
    encoder = Encoder()
    recorded_values: dict[str, object] = {}
    field_description_mesgs: list[Mesg] = []
    for index, (name, base_type, array_len) in enumerate(_SESSION_DEV_FIELD_SPECS):
        field_desc: Mesg = {
            "mesg_num": _MESG_FIELD_DESCRIPTION,
            "developer_data_index": 0,
            "field_definition_number": index,
            "fit_base_type_id": base_type,
            "field_name": name,
        }
        if array_len is not None:
            field_desc["array"] = array_len
        if scale_overrides is not None and name in scale_overrides:
            scale, offset = scale_overrides[name]
            if scale is not None:
                field_desc["scale"] = scale
            if offset is not None:
                field_desc["offset"] = offset
        handle = f"k{index}"
        encoder.add_developer_field(handle, dev_data_id, field_desc)
        field_description_mesgs.append(field_desc)
        recorded_values[handle] = _SESSION_DEV_FIELD_VALUES[name]

    session: Mesg = {**_run_session(), "developer_fields": recorded_values}
    ordered: list[Mesg] = [
        _file_id(serial, time_created=time_created),
        dev_data_id,
        *field_description_mesgs,
        _device_info(serial, "SyntheticDevFieldWatch"),
        {"mesg_num": _MESG_SPORT, "sport": "running", "sub_sport": "generic"},
        *_run_records(),
        session,
        _activity(_RUN_RECORD_COUNT - 1, float(_RUN_RECORD_COUNT - 1)),
    ]
    for mesg in ordered:
        encoder.write_mesg(mesg)
    return bytes(encoder.close())


# --- Developer-field run helper + running-dynamics families -----------------

_DEV_FIELD_RUN_SERIAL = 1201
_STRYD_SERIAL = 1202
_NATIVE_DYNAMICS_SERIAL = 1203


@dataclass(frozen=True)
class DevFieldSpec:
    """One field_description, in file order; its position is its SDK key."""

    name: str
    base_type: int  # a garmin_fit_sdk BASE_TYPE code
    definition_number: int
    units: str | None = None  # None: not written
    scale: int | float | None = None  # None: undeclared on the wire
    offset: int | float | None = None  # None: undeclared on the wire
    native_mesg_num: int | None = None  # None: not written
    developer_data_index: int = 0
    array: int | None = None  # element count; None: a scalar field


def _handle(position: int) -> str:
    """The SDK handle a description's position is registered under."""
    return f"k{position}"


def _application_id(developer_data_index: int) -> list[int]:
    """A fixed synthetic 16-byte application id, one per developer index."""
    return [(developer_data_index * 16 + j) % 256 for j in range(16)]


def _description_mesg(spec: DevFieldSpec) -> Mesg:
    mesg: Mesg = {
        "mesg_num": _MESG_FIELD_DESCRIPTION,
        "developer_data_index": spec.developer_data_index,
        "field_definition_number": spec.definition_number,
        "fit_base_type_id": spec.base_type,
        "field_name": spec.name,
    }
    if spec.units is not None:
        mesg["units"] = spec.units
    if spec.scale is not None:
        mesg["scale"] = spec.scale
    if spec.offset is not None:
        mesg["offset"] = spec.offset
    if spec.native_mesg_num is not None:
        mesg["native_mesg_num"] = spec.native_mesg_num
    if spec.array is not None:
        mesg["array"] = spec.array
    return mesg


def _encode_with_developer_descriptions(
    descriptions: Sequence[DevFieldSpec], file_id: Mesg, body: Sequence[Mesg]
) -> bytes:
    """The one Encoder sequence for every developer-field fixture.

    Every description is registered with ``Encoder.add_developer_field`` BEFORE
    the first write. The file then carries ``file_id``, one ``developer_data_id``
    per distinct index, the descriptions in order, and ``body``. A ``body``
    message's ``developer_fields`` maps a description's POSITION to its value;
    it is rewritten to the SDK handles here.
    """
    indices = sorted({spec.developer_data_index for spec in descriptions})
    data_ids: dict[int, Mesg] = {
        index: {
            "mesg_num": _MESG_DEVELOPER_DATA_ID,
            "developer_data_index": index,
            "application_id": _application_id(index),
        }
        for index in indices
    }
    encoder = Encoder()
    description_mesgs: list[Mesg] = []
    for position, spec in enumerate(descriptions):
        mesg = _description_mesg(spec)
        encoder.add_developer_field(
            _handle(position), data_ids[spec.developer_data_index], mesg
        )
        description_mesgs.append(mesg)
    encoder.write_mesg(file_id)
    for index in indices:
        encoder.write_mesg(data_ids[index])
    for mesg in description_mesgs:
        encoder.write_mesg(mesg)
    for mesg in body:
        written = dict(mesg)
        positional = written.get("developer_fields")
        if positional is not None:
            assert isinstance(positional, Mapping)
            written["developer_fields"] = {
                _handle(position): value for position, value in positional.items()
            }
        encoder.write_mesg(written)
    return bytes(encoder.close())


def developer_field_run_fit_bytes(
    *,
    descriptions: Sequence[DevFieldSpec],
    records: Sequence[tuple[Mapping[str, object], Mapping[int, object]]],
    session_fields: Mapping[int, object] | None = None,
    serial: int = _DEV_FIELD_RUN_SERIAL,
    manufacturer: str = "garmin",
    product: int = 1,
    time_created: int = FIT_TIMESTAMP_BASE,
    device_manufacturer: str | None = None,
) -> bytes:
    """Encode a valid run carrying arbitrary developer fields.

    ``descriptions`` are written in order (a description's position is its SDK
    key). Each ``records`` entry is ``(native_fields, developer_values)``: the
    native record fields in real-world units (``timestamp`` defaults to
    ``FIT_TIMESTAMP_BASE + i``), and a map from description position to the value
    that record carries. A position absent from the map is not recorded.
    ``session_fields`` maps position to a value on the session message; ``None``
    writes no developer field on the session.

    ``manufacturer`` goes to ``file_id``; the recording device (``device_info``
    index 0) uses ``device_manufacturer``, which follows ``manufacturer`` when
    ``None``.
    """
    if not records:
        raise ValueError("developer_field_run_fit_bytes needs at least one record")
    device = manufacturer if device_manufacturer is None else device_manufacturer
    record_mesgs: list[Mesg] = []
    for i, (native, recorded) in enumerate(records):
        mesg: Mesg = {
            "mesg_num": _MESG_RECORD,
            "timestamp": FIT_TIMESTAMP_BASE + i,
            **native,
        }
        if recorded:
            mesg["developer_fields"] = dict(recorded)
        record_mesgs.append(mesg)
    first = record_mesgs[0]["timestamp"]
    last = record_mesgs[-1]["timestamp"]
    assert isinstance(first, int) and isinstance(last, int)
    session: Mesg = {
        "mesg_num": _MESG_SESSION,
        "start_time": first,
        "timestamp": last,
        "sport": "running",
        "sub_sport": "generic",
        "total_elapsed_time": float(last - first),
        "total_timer_time": float(last - first),
    }
    if session_fields:
        session["developer_fields"] = dict(session_fields)
    body: list[Mesg] = [
        _device_info(serial, "SyntheticDevFieldWatch", manufacturer=device),
        {"mesg_num": _MESG_SPORT, "sport": "running", "sub_sport": "generic"},
        *record_mesgs,
        session,
        _activity(last - FIT_TIMESTAMP_BASE, float(last - first)),
    ]
    return _encode_with_developer_descriptions(
        descriptions,
        _file_id(
            serial,
            manufacturer=manufacturer,
            product=product,
            time_created=time_created,
        ),
        body,
    )


# --- Stryd-shaped fixture ---------------------------------------------------

_STRYD_RECORD_COUNT = 44
_STRYD_PAUSE = frozenset({20, 21, 22})  # a three-record pause
_STRYD_PLACEHOLDERS = frozenset({0}) | _STRYD_PAUSE
_STRYD_SENTINEL_INDEX = 10  # Form Power 65535, Air Power non-zero
_STRYD_ZERO_BALANCE_INDEX = 12  # Vertical Oscillation Balance 0.0 mid-run
_STRYD_ZERO_AIR_INDEX = 14  # Air Power 0 with non-zero Form Power
_STRYD_HUMIDITY_104_INDEX = 30
_STRYD_LAP_WINDOWS = ((0, 10), (11, 21), (22, 32), (33, 43))
_STRYD_RUN_PROFILE = "Steady Run"

_STRYD_DESCRIPTIONS: tuple[DevFieldSpec, ...] = (
    DevFieldSpec("Air Power", BASE_TYPE["UINT16"], 11, units="W"),
    DevFieldSpec("Form Power", BASE_TYPE["UINT16"], 2, units="W"),
    DevFieldSpec("Leg Spring Stiffness", BASE_TYPE["FLOAT32"], 1, units="kN/m"),
    DevFieldSpec("Impact", BASE_TYPE["FLOAT32"], 4, units="bw"),
    DevFieldSpec("Leg Spring Stiffness Balance", BASE_TYPE["FLOAT32"], 3, units="%"),
    DevFieldSpec("Impact Loading Rate Balance", BASE_TYPE["FLOAT32"], 6, units="%"),
    DevFieldSpec("Vertical Oscillation Balance", BASE_TYPE["FLOAT32"], 5, units="%"),
    DevFieldSpec("Speed", BASE_TYPE["FLOAT32"], 8, units="m/s", native_mesg_num=6),
    DevFieldSpec("Distance", BASE_TYPE["FLOAT32"], 9, units="m", native_mesg_num=5),
    DevFieldSpec(
        "Stryd Temperature", BASE_TYPE["SINT8"], 10, units="C", native_mesg_num=13
    ),
    DevFieldSpec("Stryd Humidity", BASE_TYPE["UINT8"], 12, units="%"),
    DevFieldSpec("Run Profile", BASE_TYPE["STRING"], 0),
)
_STRYD_RUN_PROFILE_POSITION = 11


def _stryd_records() -> list[tuple[Mesg, dict[int, object]]]:
    """Native record fields and developer values for every Stryd record."""
    records: list[tuple[Mesg, dict[int, object]]] = []
    distance = 0.0
    for i in range(_STRYD_RECORD_COUNT):
        placeholder = i in _STRYD_PLACEHOLDERS
        speed = 0.0 if placeholder else round(3.0 + 0.05 * (i % 7), 3)
        distance = round(distance + speed, 2)
        native: Mesg = {
            "position_lat": to_semicircles(40.0 + 0.0001 * i),
            "position_long": to_semicircles(-105.0 + 0.0001 * i),
            "distance": distance,
            "enhanced_speed": speed,
            "enhanced_altitude": 1600.0 + 0.2 * (i % 6),
            "power": 0 if placeholder else 200 + 3 * (i % 9),
            "heart_rate": 0 if placeholder else 140 + (i * 3) % 17,
            "cadence": 0 if placeholder else 170 + i % 5,
            "step_length": 0.0 if placeholder else 1000.0 + 12.5 * (i % 8),
            "vertical_oscillation": 0.0 if placeholder else 80.0 + 1.5 * (i % 9),
            "stance_time": 0.0 if placeholder else 240.0 + 2.5 * (i % 10),
            "stance_time_balance": 0.0 if placeholder else 49.0 + 0.25 * (i % 6),
        }
        recorded: dict[int, object]
        if placeholder:
            recorded = {pos: 0 for pos in (0, 1)}
            recorded.update({pos: 0.0 for pos in (2, 3, 4, 5, 6, 7)})
        else:
            recorded = {
                0: 20 + 3 * (i % 6),
                1: 50 + 2 * (i % 8),
                # Two-decimal values (integer hundredths) that float32 cannot hold:
                # no hundredths count here is a multiple of 25, the only two-decimal
                # numbers a float32 represents exactly. Position 6 is recorded as
                # 0.0 at _STRYD_ZERO_BALANCE_INDEX (below), an intended exemption.
                2: (903 + 7 * (i % 13)) / 100,
                3: (151 + 9 * (i % 7)) / 100,
                4: (4851 + 25 * (i % 9)) / 100,
                5: (5051 + 30 * (i % 7)) / 100,
                6: (4901 + 20 * (i % 8)) / 100,
                7: round(speed + 0.37, 2),
            }
            if i == _STRYD_SENTINEL_INDEX:
                recorded[1] = 65535
            if i == _STRYD_ZERO_BALANCE_INDEX:
                recorded[6] = 0.0
            if i == _STRYD_ZERO_AIR_INDEX:
                recorded[0] = 0
        # Developer Distance: off the native value everywhere, and off the
        # float32-exact hundredths (multiples of 25) like the other float32 series.
        hundredths = round((distance * 1.02 + 5.01) * 100)
        if hundredths % 25 == 0:
            hundredths += 1
        recorded[8] = hundredths / 100
        recorded[9] = 18 + i % 4
        recorded[10] = 104 if i == _STRYD_HUMIDITY_104_INDEX else 60 + i % 5
        records.append((native, recorded))
    return records


def _stryd_laps() -> list[Mesg]:
    """Four laps without heart rate or cadence."""
    laps: list[Mesg] = []
    for start, end in _STRYD_LAP_WINDOWS:
        laps.append(
            {
                "mesg_num": _MESG_LAP,
                "start_time": FIT_TIMESTAMP_BASE + start,
                "timestamp": FIT_TIMESTAMP_BASE + end,
                "sport": "running",
                "sub_sport": "generic",
                "total_elapsed_time": float(end - start + 1),
                "total_timer_time": float(end - start + 1),
            }
        )
    return laps


def stryd_run_fit_bytes(*, manufacturer: str = "stryd") -> bytes:
    """Encoded run shaped like a Stryd developer-field file.

    ``manufacturer`` names the writer: it is written into ``file_id`` and the
    ``device_info`` at device index 0, and nowhere else.
    """
    record_mesgs: list[Mesg] = []
    for i, (native, recorded) in enumerate(_stryd_records()):
        record_mesgs.append(
            {
                "mesg_num": _MESG_RECORD,
                "timestamp": FIT_TIMESTAMP_BASE + i,
                **native,
                "developer_fields": recorded,
            }
        )
    laps = _stryd_laps()
    last_lap_start = laps[-1]["start_time"]
    assert isinstance(last_lap_start, int)
    elapsed = float(_STRYD_RECORD_COUNT - 1)
    session: Mesg = {
        "mesg_num": _MESG_SESSION,
        "start_time": FIT_TIMESTAMP_BASE,
        # The session's timestamp is the fourth lap's START, as in the measured file.
        "timestamp": last_lap_start,
        "sport": "running",
        "sub_sport": "generic",
        "num_laps": 1,
        "total_elapsed_time": elapsed,
        "total_timer_time": elapsed,
        "developer_fields": {_STRYD_RUN_PROFILE_POSITION: _STRYD_RUN_PROFILE},
    }
    body: list[Mesg] = [
        _device_info(_STRYD_SERIAL, "SyntheticStrydPod", manufacturer=manufacturer),
        {"mesg_num": _MESG_SPORT, "sport": "running", "sub_sport": "generic"},
        *record_mesgs,
        *laps,
        session,
        _activity(_STRYD_RECORD_COUNT - 1, elapsed),
    ]
    return _encode_with_developer_descriptions(
        _STRYD_DESCRIPTIONS,
        _file_id(_STRYD_SERIAL, manufacturer=manufacturer),
        body,
    )


# --- Native-dynamics (HealthFit-copy) fixture -------------------------------

_NATIVE_DYNAMICS_RECORD_COUNT = 20
# A NEW identifier containing 255 (the byte value a per-element sentinel filter
# would drop); ``_SESSION_UUID_BYTES`` is left as it was.
_NATIVE_DYNAMICS_UUID_BYTES: tuple[int, ...] = (255, *range(40, 55))


def run_native_dynamics_fit_bytes() -> bytes:
    """Encoded run shaped like a HealthFit copy that carries native dynamics.

    Records hold ``vertical_oscillation``, ``stance_time`` and ``vertical_ratio``
    (no balance, no step length, no developer record fields); the session
    carries HealthFit's developer fields with a ``SESSION UUID`` containing 255.
    """
    descriptions = tuple(
        DevFieldSpec(name, base_type, index, array=array_len)
        for index, (name, base_type, array_len) in enumerate(_SESSION_DEV_FIELD_SPECS)
    )
    values = {
        **_SESSION_DEV_FIELD_VALUES,
        "SESSION UUID": list(_NATIVE_DYNAMICS_UUID_BYTES),
    }
    session_fields = {
        index: values[name]
        for index, (name, _, _) in enumerate(_SESSION_DEV_FIELD_SPECS)
    }
    records: list[tuple[Mesg, dict[int, object]]] = []
    distance = 0.0
    for i in range(_NATIVE_DYNAMICS_RECORD_COUNT):
        speed = round(3.1 + 0.05 * (i % 6), 3)
        distance = round(distance + speed, 2)
        records.append(
            (
                {
                    "position_lat": to_semicircles(40.0 + 0.0001 * i),
                    "position_long": to_semicircles(-105.0 + 0.0001 * i),
                    "distance": distance,
                    "enhanced_speed": speed,
                    "heart_rate": 130 + (i * 2) % 9,
                    "vertical_oscillation": 85.0 + 1.0 * (i % 7),
                    "stance_time": 250.0 + 3.0 * (i % 5),
                    "vertical_ratio": 7.0 + 0.1 * (i % 6),
                },
                {},
            )
        )
    return developer_field_run_fit_bytes(
        descriptions=descriptions,
        records=records,
        session_fields=session_fields,
        serial=_NATIVE_DYNAMICS_SERIAL,
    )


# --- Encoded-byte builders --------------------------------------------------


def run_fit_bytes() -> bytes:
    """Encoded ``.fit`` bytes for the outdoor-run fixture."""
    return encode(run_mesgs())


def ride_fit_bytes() -> bytes:
    """Encoded ``.fit`` bytes for the ride fixture."""
    return encode(ride_mesgs())


def _device_info_by_code(
    serial: int, device_index: int, manufacturer: str, product: int
) -> Mesg:
    """A device message that records a product code and no product name text."""
    return {
        "mesg_num": _MESG_DEVICE_INFO,
        "timestamp": FIT_TIMESTAMP_BASE,
        "device_index": device_index,
        "manufacturer": manufacturer,
        "serial_number": serial,
        "product": product,
    }


def garmin_devices_ride_fit_bytes() -> bytes:
    """Encoded ``.fit`` bytes for a ride recorded with four distinct devices.

    The ride fixture's one device message is replaced by four with
    pairwise-distinct serials, none recording a product name: index 0 (the
    recording device) Garmin code 3843, index 1 Dynastream code 3300, index 2
    Garmin code 65000, index 3 Wahoo code 3843.
    """
    mesgs = ride_mesgs()
    at = next(i for i, m in enumerate(mesgs) if m["mesg_num"] == _MESG_DEVICE_INFO)
    mesgs[at : at + 1] = [
        _device_info_by_code(1101, 0, "garmin", 3843),
        _device_info_by_code(1102, 1, "dynastream", 3300),
        _device_info_by_code(1103, 2, "garmin", 65000),
        _device_info_by_code(1104, 3, "wahoo_fitness", 3843),
    ]
    return encode(mesgs)


def strength_fit_bytes() -> bytes:
    """Encoded ``.fit`` bytes for the strength-session fixture."""
    return encode(strength_mesgs())


def minimal_fit_bytes() -> bytes:
    """Encoded ``.fit`` bytes for the minimal (session-less) fixture."""
    return encode(minimal_mesgs())


def run_native_power_sparse_hr_fit_bytes() -> bytes:
    """Encoded run with native power on every sample and sparse heart rate."""
    return encode(run_native_power_sparse_hr_mesgs())


def run_no_gps_fit_bytes() -> bytes:
    """Encoded run with no GPS position and no altitude channel."""
    return encode(run_no_gps_mesgs())


def ride_no_power_fit_bytes() -> bytes:
    """Encoded ride with no power channel (HR + speed hero fallback)."""
    return encode(ride_no_power_mesgs())


def strength_no_sets_fit_bytes() -> bytes:
    """Encoded strength session: HR-only records and NO set messages."""
    return encode(strength_no_sets_mesgs())


def session_dev_fields_fit_bytes() -> bytes:
    """Encoded run carrying session-scoped HealthFit developer fields."""
    return _encode_run_with_developer_fields(1014)


# ``AVG METs`` declared with an EXPLICIT ``scale=100`` on the SAME raw byte
# (950) the undeclared fixture above uses -- so ingest decodes it to 9.5
# itself (fit-ingest Req 14.2, as amended) rather than fitdocs having to guess
# the hundredths convention. This is the scenario Amendment 2 exists to serve:
# a writer that DOES declare its scale. ``SESSION WEATHER HUMIDITY`` is left
# undeclared, so one file exercises BOTH paths -- render must apply its
# hundredths fallback to Humidity while NOT re-applying it to Avg METs.
_DECLARED_SCALE_OVERRIDES: dict[str, tuple[int | None, int | None]] = {
    "AVG METs": (100, None),
}


def session_dev_fields_declared_scale_fit_bytes() -> bytes:
    """Encoded run like :func:`session_dev_fields_fit_bytes` but ``AVG METs``
    declares ``scale=100`` on its ``field_description`` (Req 14.2, as amended).

    Proves the render layer does not double-scale an already-decoded value:
    the raw wire byte is IDENTICAL (950) to the undeclared fixture, but here
    ingest decodes it to ``9.5`` itself, and ``render/sections.py`` must
    render ``9.5`` -- not ``0.095`` -- by consulting
    ``Activity.developer_fields_declared_scale`` rather than blindly applying
    its own hundredths-guess fallback.
    """
    return _encode_run_with_developer_fields(
        1017, scale_overrides=_DECLARED_SCALE_OVERRIDES
    )


_REEXPORT_B_CREATED_LATER_S = 1


def reexport_a_fit_bytes() -> bytes:
    """Re-export pair, file A: fixed ``SESSION UUID``, serial 1015."""
    return _encode_run_with_developer_fields(1015)


def reexport_b_fit_bytes() -> bytes:
    """Re-export pair, file B: SAME ``SESSION UUID``, serial 1016 -> different bytes.

    Its ``file_id`` creation time is one second later than file A's, so a
    canonical rank keyed on creation time keeps the pair in order A, B.
    """
    return _encode_run_with_developer_fields(
        1016, time_created=FIT_TIMESTAMP_BASE + _REEXPORT_B_CREATED_LATER_S
    )


# --- Corrupt / degenerate variants ------------------------------------------

# A fixed non-FIT payload whose first byte (0x66, 'f') is neither valid FIT
# header size (12 or 14), so ``is_fit`` rejects it immediately.
_NON_FIT_PAYLOAD = b"fitdocs synthetic non-FIT payload; not a valid header.\n" * 8

# A minimal valid file plus a stray record-definition-shaped tail: the header,
# body, and file CRC stay intact (integrity passes) but the decoder's file loop
# then fails to parse the trailing bytes, surfacing a message-level error.
_TRAILING_GARBAGE = bytes([0x40, 0x00, 0x00, 0xFF, 0xFF, 0x01, 0x00, 0x01, 0x00])


def non_fit_bytes() -> bytes:
    """Bytes with no valid FIT header (``is_fit`` is False)."""
    return _NON_FIT_PAYLOAD


def truncated_fit_bytes() -> bytes:
    """A valid run file cut to half length: header survives, integrity fails."""
    data = run_fit_bytes()
    return data[: len(data) // 2]


def bad_message_fit_bytes() -> bytes:
    """A valid file that decodes overall yet yields a message-level decode error.

    Crafted-bytes path (no decoder stubbing): the minimal file's header, body,
    and CRC are untouched -- so ``is_fit`` and ``check_integrity`` both pass --
    but ``read`` then tries to parse the appended tail as a further chained file,
    collecting an error while the already-decoded records remain in the result.
    """
    return minimal_fit_bytes() + _TRAILING_GARBAGE


# --- Decoded-message builders (for extractor unit-tests) --------------------


def run_messages() -> MessagesDict:
    """Decoded message dict for the run fixture (as the real decoder yields it)."""
    return decode_messages(run_fit_bytes())[0]


def ride_messages() -> MessagesDict:
    """Decoded message dict for the ride fixture."""
    return decode_messages(ride_fit_bytes())[0]


def strength_messages() -> MessagesDict:
    """Decoded message dict for the strength fixture."""
    return decode_messages(strength_fit_bytes())[0]


def minimal_messages() -> MessagesDict:
    """Decoded message dict for the minimal fixture."""
    return decode_messages(minimal_fit_bytes())[0]
