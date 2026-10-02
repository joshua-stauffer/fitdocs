"""Synthetic fixtures for channel composition: a run pair, a run trio, a ride pair.

Every value is synthesized here (no personal data) and every builder is
byte-deterministic. The shapes are the alignment shapes measured on real
Stryd and HealthFit files, scaled down; the design record is
``.kiro/specs/channel-merge/design.md`` (Supporting References).

* :func:`run_pair_fit_bytes` -- ``(healthfit, stryd)`` of one run. Five
  stretches of twelve 1 Hz samples, each separated from the next by a five
  second timestamp step (four instants with no sample). In stretch ``k`` the
  HealthFit distance and power at
  ``t + L_k`` equal the Stryd values at ``t`` with
  ``(L_1..L_5) = (+1, +1, 0, +1, 0)``; heart rate lags the other way (HealthFit
  at ``t - 1`` equals Stryd at ``t``); the HealthFit copy records three trailing
  instants after the last Stryd one.
* :func:`run_trio_fit_bytes` -- the pair plus a second Stryd file of the same
  run, created later, whose form power is one watt higher at every sample.
* :func:`ride_pair_fit_bytes` -- ``(garmin, healthfit)`` of one ride: a Garmin
  original without heart rate and a HealthFit copy carrying it, whose distance
  differs from the original's at every sample while its power equals it but
  for one sample.

Recording devices: each Stryd file names ``stryd`` in ``file_id`` and at
``device_info`` index 0; each HealthFit copy names ``development`` in both. The
``development`` recording device of a HealthFit copy is a synthetic variant;
what a real copy records there is unconfirmed.

Values within each channel of each stretch are pairwise distinct, so a
one-sample misplacement changes every compared value.
"""

from __future__ import annotations

from collections.abc import Mapping

from garmin_fit_sdk.fit import BASE_TYPE  # type: ignore[import-untyped]

from tests.fixtures import builder
from tests.fixtures.builder import DevFieldSpec, Mesg

__all__ = [
    "RUN_LAGS",
    "RUN_START",
    "RIDE_START",
    "ride_pair_fit_bytes",
    "run_pair_fit_bytes",
    "run_trio_fit_bytes",
]

_HOUR_S = 3600

# --- Run --------------------------------------------------------------------

RUN_START = builder.FIT_TIMESTAMP_BASE + 650_000_000
"""The session start ``S`` of every run file (a FIT-epoch second)."""

RUN_LAGS: tuple[int, ...] = (1, 1, 0, 1, 0)
"""``L_1..L_5``: the HealthFit distance and power lag, in seconds, per stretch."""

_RUN_STRETCH_LEN = 12
_RUN_STRIDE = 16  # twelve samples at 0..11, the next stretch at 16: a five second step
_RUN_TRAILING = 3
_RUN_ELAPSED_S = float((len(RUN_LAGS) - 1) * _RUN_STRIDE + _RUN_STRETCH_LEN - 1 + 3)
_RUN_DISTANCE_M = 250.0
_RUN_SERIAL_HEALTHFIT = 4100
_RUN_SERIAL_STRYD = 4101
_RUN_STRYD_B_LATER_S = 600

_SESSION_UUID = tuple(range(40, 56))
_SESSION_UUID_SPEC = DevFieldSpec(
    "SESSION UUID", BASE_TYPE["UINT8"], 0, array=len(_SESSION_UUID)
)

# The seven Stryd developer channels: name, base type, definition number, units.
_STRYD_DESCRIPTIONS: tuple[DevFieldSpec, ...] = (
    DevFieldSpec("Air Power", BASE_TYPE["UINT16"], 11, units="W"),
    DevFieldSpec("Form Power", BASE_TYPE["UINT16"], 2, units="W"),
    DevFieldSpec("Leg Spring Stiffness", BASE_TYPE["FLOAT32"], 1, units="kN/m"),
    DevFieldSpec("Impact", BASE_TYPE["FLOAT32"], 4, units="bw"),
    DevFieldSpec("Leg Spring Stiffness Balance", BASE_TYPE["FLOAT32"], 3, units="%"),
    DevFieldSpec("Impact Loading Rate Balance", BASE_TYPE["FLOAT32"], 6, units="%"),
    DevFieldSpec("Vertical Oscillation Balance", BASE_TYPE["FLOAT32"], 5, units="%"),
)


def _distance(g: int) -> float:
    return round(5.0 + 3.21 * g, 2)


def _power(g: int) -> int:
    return 180 + (7 * g) % 61


def _heart_rate(g: int) -> int:
    return 100 + 2 * g


def _speed(g: int) -> float:
    return round(2.5 + 0.013 * ((7 * g + 3) % 61), 3)


def _cadence(g: int) -> int:
    return 140 + 4 * ((7 * g) % 13)


def _step_length(g: int) -> float:
    return round(900.0 + 6.7 * ((5 * g) % 17), 1)


def _stryd_vertical_oscillation(g: int) -> float:
    return round(70.0 + 1.1 * ((11 * g) % 13), 1)


def _stryd_stance_time(g: int) -> float:
    return round(230.0 + 2.5 * ((5 * g) % 13), 1)


def _stryd_stance_balance(g: int) -> float:
    return round(48.0 + 0.25 * ((7 * g) % 13), 2)


def _form_power(g: int) -> int:
    return 50 + 2 * ((5 * g) % 13)


def _stryd_developer(g: int, form_power_offset_w: int) -> dict[int, object]:
    """Developer values by description position (0..6, the table's order)."""
    return {
        0: 20 + 3 * ((7 * g) % 13),
        1: _form_power(g) + form_power_offset_w,
        2: 8.0 + 0.25 * ((7 * g) % 13),
        3: 1.5 + 0.125 * ((5 * g) % 13),
        4: 50.0 + 0.25 * ((3 * g) % 13),
        5: 50.0 + 0.5 * ((11 * g) % 13),
        6: 49.0 + 0.25 * ((9 * g) % 13),
    }


def _stryd_instants() -> list[tuple[int, int, int]]:
    """``(offset_s, stretch, g)`` for every Stryd sample, in order."""
    return [
        (k * _RUN_STRIDE + i, k, k * _RUN_STRETCH_LEN + i)
        for k in range(len(RUN_LAGS))
        for i in range(_RUN_STRETCH_LEN)
    ]


def _run_laps(
    windows: tuple[tuple[int, int], ...],
    distance_base_m: float,
    with_heart_rate: bool,
) -> list[dict[str, object]]:
    laps: list[dict[str, object]] = []
    for n, (start, end) in enumerate(windows):
        lap: dict[str, object] = {
            "start_time": RUN_START + start,
            "timestamp": RUN_START + end,
            "sport": "running",
            "sub_sport": "generic",
            "total_elapsed_time": float(end - start + 1),
            "total_timer_time": float(end - start + 1),
            "total_distance": distance_base_m + 7.25 * n,
        }
        if with_heart_rate:
            lap["avg_heart_rate"] = 130 + 7 * n
            lap["max_heart_rate"] = 150 + 9 * n
        laps.append(lap)
    return laps


def _stryd_bytes(*, time_created: int, form_power_offset_w: int) -> bytes:
    records: list[tuple[Mesg, Mapping[int, object]]] = []
    for offset, _stretch, g in _stryd_instants():
        native: Mesg = {
            "timestamp": RUN_START + offset,
            "heart_rate": _heart_rate(g),
            "power": _power(g),
            "distance": _distance(g),
            "enhanced_speed": _speed(g),
            "cadence": _cadence(g),
            "step_length": _step_length(g),
            "vertical_oscillation": _stryd_vertical_oscillation(g),
            "stance_time": _stryd_stance_time(g),
            "stance_time_balance": _stryd_stance_balance(g),
        }
        records.append((native, _stryd_developer(g, form_power_offset_w)))
    return builder.developer_field_run_fit_bytes(
        descriptions=_STRYD_DESCRIPTIONS,
        records=records,
        serial=_RUN_SERIAL_STRYD,
        manufacturer="stryd",
        device_manufacturer="stryd",
        product=1,
        time_created=time_created,
        laps=_run_laps(((0, 19), (20, 39), (40, 59), (60, 75)), 61.5, False),
        session_start=RUN_START,
        session_elapsed_s=_RUN_ELAPSED_S + 8.5,
        session_distance_m=_RUN_DISTANCE_M,
    )


def _healthfit_run_bytes() -> bytes:
    records: list[tuple[Mesg, Mapping[int, object]]] = []
    for n, (offset, stretch, g) in enumerate(_stryd_instants()):
        i = g - stretch * _RUN_STRETCH_LEN
        lag = RUN_LAGS[stretch]
        last_in_stretch = i == _RUN_STRETCH_LEN - 1
        if lag == 1 and i == 0:
            distance = round(_distance(g) - 1.5, 2)
            power = 150 + stretch
        elif lag == 1:
            distance = _distance(g - 1)
            power = _power(g - 1)
        else:
            distance = _distance(g)
            power = _power(g)
        heart_rate = 220 + 2 * stretch if last_in_stretch else _heart_rate(g + 1)
        native: Mesg = {
            "timestamp": RUN_START + offset,
            "heart_rate": heart_rate,
            "power": power,
            "distance": distance,
            "enhanced_speed": _speed(g),
            "cadence": _cadence(g) + (1 if i % 2 == 0 else -1),
            "step_length": round(_step_length(g) / 1.008, 1),
            "vertical_oscillation": round(72.0 + 1.3 * ((3 * g) % 13), 1),
            "stance_time": round(225.0 + 3.5 * ((9 * g) % 13), 1),
            "vertical_ratio": round(7.0 + 0.05 * ((7 * g) % 13), 2),
            "position_lat": builder.to_semicircles(40.0 + 0.0001 * n),
            "position_long": builder.to_semicircles(-105.0 + 0.00013 * n),
            "enhanced_altitude": round(1600.0 + 0.2 * ((7 * n) % 61), 1),
        }
        records.append((native, {}))
    last_offset = (len(RUN_LAGS) - 1) * _RUN_STRIDE + _RUN_STRETCH_LEN - 1
    last_g = len(RUN_LAGS) * _RUN_STRETCH_LEN - 1
    for j in range(_RUN_TRAILING):
        n = len(records)
        native = {
            "timestamp": RUN_START + last_offset + 1 + j,
            "heart_rate": 230 + 2 * j,
            "power": 260 + 3 * j,
            "distance": round(_distance(last_g) + 3.21 * (j + 1), 2),
            "enhanced_speed": round(3.5 + 0.011 * j, 3),
            "cadence": 142 + 4 * j,
            "step_length": round(880.0 + 3.3 * j, 1),
            "vertical_oscillation": round(90.0 + 1.3 * j, 1),
            "stance_time": round(270.0 + 3.5 * j, 1),
            "vertical_ratio": round(8.0 + 0.05 * j, 2),
            "position_lat": builder.to_semicircles(40.0 + 0.0001 * n),
            "position_long": builder.to_semicircles(-105.0 + 0.00013 * n),
            "enhanced_altitude": round(1600.0 + 0.2 * ((7 * n) % 61), 1),
        }
        records.append((native, {}))
    return builder.developer_field_run_fit_bytes(
        descriptions=(_SESSION_UUID_SPEC,),
        records=records,
        session_fields={0: list(_SESSION_UUID)},
        serial=_RUN_SERIAL_HEALTHFIT,
        manufacturer="development",
        device_manufacturer="development",
        product=0,
        time_created=RUN_START + 4 * _HOUR_S,
        laps=_run_laps(((0, 11), (16, 27), (32, 43), (48, 59), (64, 78)), 50.0, True),
        session_start=RUN_START,
        session_elapsed_s=_RUN_ELAPSED_S,
        session_distance_m=_RUN_DISTANCE_M,
    )


def run_pair_fit_bytes() -> tuple[bytes, bytes]:
    """``(healthfit, stryd)`` bytes of one synthetic run."""
    return (
        _healthfit_run_bytes(),
        _stryd_bytes(time_created=RUN_START, form_power_offset_w=0),
    )


def run_trio_fit_bytes() -> tuple[bytes, bytes, bytes]:
    """``(healthfit, stryd_a, stryd_b)``: the pair plus a later Stryd file.

    ``stryd_b`` differs from ``stryd_a`` in its ``file_id`` creation time (later)
    and in form power (one watt higher at every sample).
    """
    healthfit, stryd_a = run_pair_fit_bytes()
    stryd_b = _stryd_bytes(
        time_created=RUN_START + _RUN_STRYD_B_LATER_S, form_power_offset_w=1
    )
    return healthfit, stryd_a, stryd_b


# --- Ride -------------------------------------------------------------------

RIDE_START = builder.FIT_TIMESTAMP_BASE + 650_000_000 + 86_400
"""The session start of both ride files (a FIT-epoch second)."""

_RIDE_STRETCHES = 3
_RIDE_STRETCH_LEN = 34
_RIDE_STRIDE = 38  # 34 samples at 0..33, the next stretch at 38: a five second step
_RIDE_ELAPSED_S = float((_RIDE_STRETCHES - 1) * _RIDE_STRIDE + _RIDE_STRETCH_LEN - 1)
_RIDE_DISTANCE_M = 450.0
_RIDE_COPY_DISTANCE_EXTRA_M = 2.0
_RIDE_COPY_MISSING_POWER_G = 50
_RIDE_SERIAL_GARMIN = 4200
_RIDE_SERIAL_HEALTHFIT = 4201
_RIDE_UUID = tuple(range(90, 106))
_RIDE_UUID_SPEC = DevFieldSpec(
    "SESSION UUID", BASE_TYPE["UINT8"], 0, array=len(_RIDE_UUID)
)


def _ride_instants() -> list[tuple[int, int]]:
    """``(offset_s, g)`` for every ride sample, in order."""
    return [
        (k * _RIDE_STRIDE + i, k * _RIDE_STRETCH_LEN + i)
        for k in range(_RIDE_STRETCHES)
        for i in range(_RIDE_STRETCH_LEN)
    ]


def _ride_power(g: int) -> int:
    return 120 + (37 * g) % 103


def _ride_distance(g: int) -> float:
    return round(10.0 + 4.27 * g, 2)


def _ride_copy_distance(g: int) -> float:
    return round(_ride_distance(g) + 0.12 + 0.01 * (g % 80), 2)


def _garmin_ride_bytes() -> bytes:
    mesgs: list[Mesg] = [
        builder._file_id(
            _RIDE_SERIAL_GARMIN,
            manufacturer="garmin",
            product=3843,
            time_created=RIDE_START,
        ),
        builder._device_info(
            _RIDE_SERIAL_GARMIN, "SyntheticGarminEdge", manufacturer="garmin"
        ),
        {"mesg_num": builder._MESG_SPORT, "sport": "cycling", "sub_sport": "generic"},
    ]
    for offset, g in _ride_instants():
        mesgs.append(
            {
                "mesg_num": builder._MESG_RECORD,
                "timestamp": RIDE_START + offset,
                "power": _ride_power(g),
                "distance": _ride_distance(g),
                "speed": round(6.0 + 0.021 * ((7 * g) % 103), 3),
                "enhanced_altitude": round(100.0 + 0.2 * ((7 * g) % 103), 1),
                "temperature": -10 + (7 * g) % 37,
                "position_lat": builder.to_semicircles(40.0 + 0.0001 * g),
                "position_long": builder.to_semicircles(-105.0 + 0.00013 * g),
                "cadence": 60 + (11 * g) % 37,
            }
        )
    last = RIDE_START + int(_RIDE_ELAPSED_S)
    mesgs.append(
        {
            "mesg_num": builder._MESG_SESSION,
            "start_time": RIDE_START,
            "timestamp": last,
            "sport": "cycling",
            "sub_sport": "generic",
            "total_elapsed_time": _RIDE_ELAPSED_S,
            "total_timer_time": _RIDE_ELAPSED_S,
            "total_distance": _RIDE_DISTANCE_M,
        }
    )
    mesgs.append(builder._activity(last - builder.FIT_TIMESTAMP_BASE, _RIDE_ELAPSED_S))
    return builder.encode(mesgs)


def _healthfit_ride_bytes(*, copy_power: bool, shift_s: int) -> bytes:
    records: list[tuple[Mesg, Mapping[int, object]]] = []
    for offset, g in _ride_instants():
        native: Mesg = {
            "timestamp": RIDE_START + shift_s + offset,
            "heart_rate": 90 + 3 * (g % _RIDE_STRETCH_LEN),
            "distance": _ride_copy_distance(g),
        }
        if copy_power and g != _RIDE_COPY_MISSING_POWER_G:
            native["power"] = _ride_power(g)
        records.append((native, {}))
    return builder.developer_field_run_fit_bytes(
        descriptions=(_RIDE_UUID_SPEC,),
        records=records,
        session_fields={0: list(_RIDE_UUID)},
        serial=_RIDE_SERIAL_HEALTHFIT,
        manufacturer="development",
        device_manufacturer="development",
        product=0,
        time_created=RIDE_START + 4 * _HOUR_S,
        session_start=RIDE_START + shift_s,
        session_elapsed_s=_RIDE_ELAPSED_S,
        session_distance_m=_RIDE_DISTANCE_M + _RIDE_COPY_DISTANCE_EXTRA_M,
        sport="cycling",
    )


def ride_pair_fit_bytes(
    *, copy_power: bool = True, copy_shift_h: int = 0
) -> tuple[bytes, bytes]:
    """``(garmin, healthfit)`` bytes of one synthetic ride.

    ``copy_power=False`` leaves power out of the copy (the exact-timestamp
    fallback); ``copy_shift_h`` moves the copy's instants and session start by
    that many whole hours.
    """
    return (
        _garmin_ride_bytes(),
        _healthfit_ride_bytes(copy_power=copy_power, shift_s=copy_shift_h * _HOUR_S),
    )
