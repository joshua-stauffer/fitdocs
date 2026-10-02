"""Self-tests for the channel-composition fixtures in ``tests/fixtures/merge.py``.

Every premise a later composition test relies on is asserted here from the raw
FIT messages (``builder.decode_messages``), with no ``fitdocs`` code between the
bytes and the assertion; the one exception is the final section, which asks
``fitdocs.identity`` how the files relate. The expected values are literals, not
read back from the fixture module.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence

import pytest

from fitdocs import parse_fit
from fitdocs.identity.matching import (
    Evidence,
    SessionKey,
    pair_evidence,
    session_key,
)
from fitdocs.identity.roles import (
    DEFAULT_PRECEDENCE,
    PageRoles,
    rank_members,
    source_member,
)
from fitdocs.model import DYNAMICS_CHANNELS
from tests.fixtures import builder, merge

Messages = dict[str, list[dict[str, object]]]
Record = dict[str, object]

_RUN_START = 1_650_000_000
_RIDE_START = 1_650_086_400
_LAGS = (1, 1, 0, 1, 0)

# What the Stryd file records and the HealthFit copy does not, by raw field
# name, and the channel each one is.
_STRYD_ONLY = {
    "stance_time_balance": "stance_time_balance_pct",
    "Air Power": "air_power_w",
    "Form Power": "form_power_w",
    "Leg Spring Stiffness": "leg_spring_stiffness_kn_m",
    "Impact": "impact_bw",
    "Leg Spring Stiffness Balance": "leg_spring_stiffness_balance_pct",
    "Impact Loading Rate Balance": "impact_loading_rate_balance_pct",
    "Vertical Oscillation Balance": "vertical_oscillation_balance_pct",
}


def _decode(data: bytes) -> Messages:
    messages, errors = builder.decode_messages(data)
    assert errors == []
    return messages


def _num(mesg: Mapping[str, object], key: str) -> float:
    value = mesg[key]
    assert isinstance(value, int | float) and not isinstance(value, bool), key
    return float(value)


def _records(data: bytes) -> list[Record]:
    """Records with developer fields lifted to ``record[<field name>]`` (a developer
    field is keyed by its description's position)."""
    messages = _decode(data)
    names = {
        position: str(d["field_name"])
        for position, d in enumerate(messages.get("field_description_mesgs", []))
    }
    out: list[Record] = []
    for rec in messages["record_mesgs"]:
        flat: Record = {k: v for k, v in rec.items() if k != "developer_fields"}
        dev = rec.get("developer_fields", {})
        assert isinstance(dev, dict)
        for number, value in dev.items():
            flat[names[number]] = value
        out.append(flat)
    return out


def _offsets(records: Sequence[Record], start: int) -> list[int]:
    return [int(_num(r, "timestamp")) - start for r in records]


def _stretches(offsets: Sequence[int]) -> list[tuple[int, int]]:
    """``(first, last)`` offset of each run of 1 s steps."""
    spans: list[tuple[int, int]] = []
    first = prev = offsets[0]
    for t in offsets[1:]:
        if t - prev > 1:
            spans.append((first, prev))
            first = t
        prev = t
    spans.append((first, prev))
    return spans


def _series(records: Sequence[Record], start: int, channel: str) -> dict[int, float]:
    return {
        int(_num(r, "timestamp")) - start: _num(r, channel)
        for r in records
        if channel in r
    }


def _agreement(
    healthfit: Mapping[int, float],
    other: Mapping[int, float],
    other_span: tuple[int, int],
    healthfit_span: tuple[int, int],
    lag: int,
    tolerance: float,
) -> tuple[int, int]:
    """(matched, compared): ``healthfit[t + lag]`` against ``other[t]``."""
    matched = compared = 0
    for t in range(other_span[0], other_span[1] + 1):
        u = t + lag
        if t not in other or u not in healthfit:
            continue
        if not healthfit_span[0] <= u <= healthfit_span[1]:
            continue
        compared += 1
        if abs(healthfit[u] - other[t]) <= tolerance:
            matched += 1
    return matched, compared


_NOT_CHANNELS = {"timestamp"}


def _assert_distinct_per_stretch(
    records: Sequence[Record], start: int, label: str
) -> None:
    offsets = _offsets(records, start)
    spans = _stretches(offsets)
    channels = {k for r in records for k in r} - _NOT_CHANNELS
    assert channels, label
    for first, last in spans:
        window = [
            r for r, t in zip(records, offsets, strict=True) if first <= t <= last
        ]
        for channel in sorted(channels):
            values = [r[channel] for r in window if channel in r]
            assert len(values) == len(set(map(str, values))), (label, channel, first)


def _device_zero(data: bytes) -> Record:
    zero = [
        m for m in _decode(data)["device_info_mesgs"] if m["device_index"] == "creator"
    ]
    assert len(zero) == 1
    return zero[0]


def _file_id(data: bytes) -> Record:
    return _decode(data)["file_id_mesgs"][0]


def _session(data: bytes) -> Record:
    sessions = _decode(data)["session_mesgs"]
    assert len(sessions) == 1
    return sessions[0]


@pytest.fixture(scope="module")
def pair() -> tuple[bytes, bytes]:
    return merge.run_pair_fit_bytes()


@pytest.fixture(scope="module")
def hf_run(pair: tuple[bytes, bytes]) -> list[Record]:
    return _records(pair[0])


@pytest.fixture(scope="module")
def stryd_run(pair: tuple[bytes, bytes]) -> list[Record]:
    return _records(pair[1])


@pytest.fixture(scope="module")
def rides() -> tuple[bytes, bytes]:
    return merge.ride_pair_fit_bytes()


# --- every file is a valid FIT file ------------------------------------------


def _all_files() -> dict[str, bytes]:
    healthfit, stryd = merge.run_pair_fit_bytes()
    trio = merge.run_trio_fit_bytes()
    garmin, copy = merge.ride_pair_fit_bytes()
    return {
        "run_healthfit": healthfit,
        "run_stryd": stryd,
        "trio_stryd_b": trio[2],
        "ride_garmin": garmin,
        "ride_copy": copy,
        "ride_copy_no_power": merge.ride_pair_fit_bytes(copy_power=False)[1],
        "ride_copy_shifted": merge.ride_pair_fit_bytes(copy_shift_h=1)[1],
    }


@pytest.mark.parametrize("name", sorted(_all_files()))
def test_every_fixture_file_decodes_cleanly_and_passes_the_integrity_check(
    name: str,
) -> None:
    from garmin_fit_sdk import Decoder, Stream  # type: ignore[import-untyped]

    data = _all_files()[name]
    assert Decoder(Stream.from_byte_array(data)).check_integrity()
    messages = _decode(data)
    assert len(messages["record_mesgs"]) > 0
    assert len(messages["session_mesgs"]) == 1


def test_building_each_fixture_twice_gives_identical_bytes() -> None:
    builds: tuple[Callable[[], object], ...] = (
        merge.run_pair_fit_bytes,
        merge.run_trio_fit_bytes,
        merge.ride_pair_fit_bytes,
        lambda: merge.ride_pair_fit_bytes(copy_power=False),
        lambda: merge.ride_pair_fit_bytes(copy_shift_h=1),
    )
    for build in builds:
        first = build()
        assert first == build()
        assert first  # a non-empty result, so the equality above compares bytes


# --- run pair: layout --------------------------------------------------------


def test_stryd_has_five_stretches_of_twelve_one_hertz_samples_with_gaps(
    stryd_run: list[Record],
) -> None:
    offsets = _offsets(stryd_run, _RUN_START)
    spans = _stretches(offsets)
    assert spans == [(0, 11), (16, 27), (32, 43), (48, 59), (64, 75)]
    assert len(offsets) == 60
    for (_, prev_last), (next_first, _) in zip(spans, spans[1:], strict=False):
        assert next_first - prev_last >= 3
    for first, last in spans:
        inside = [t for t in offsets if first <= t <= last]
        assert inside == list(range(first, last + 1))


def test_healthfit_has_the_stryd_instants_plus_three_trailing(
    hf_run: list[Record], stryd_run: list[Record]
) -> None:
    hf = _offsets(hf_run, _RUN_START)
    st = _offsets(stryd_run, _RUN_START)
    assert set(st) <= set(hf)
    assert sorted(set(hf) - set(st)) == [76, 77, 78]
    assert max(st) == 75
    trailing = [r for r, t in zip(hf_run, hf, strict=True) if t > 75]
    for channel in ("heart_rate", "power", "distance", "enhanced_speed", "cadence"):
        assert all(channel in r for r in trailing), channel


def test_the_stryd_file_has_no_position_and_the_healthfit_copy_has_it_everywhere(
    hf_run: list[Record], stryd_run: list[Record]
) -> None:
    for channel in ("position_lat", "position_long"):
        assert not any(channel in r for r in stryd_run), channel
        assert all(channel in r for r in hf_run), channel


# --- run pair: alignment premises --------------------------------------------


def test_per_stretch_distance_and_power_lag_is_plus1_plus1_0_plus1_0(
    hf_run: list[Record], stryd_run: list[Record]
) -> None:
    st_spans = _stretches(_offsets(stryd_run, _RUN_START))
    hf_spans = _stretches(_offsets(hf_run, _RUN_START))
    assert len(st_spans) == len(hf_spans) == 5
    for channel in ("distance", "power"):
        hf = _series(hf_run, _RUN_START, channel)
        st = _series(stryd_run, _RUN_START, channel)
        for k, (st_span, hf_span) in enumerate(zip(st_spans, hf_spans, strict=True)):
            matched, compared = _agreement(hf, st, st_span, hf_span, _LAGS[k], 0.0)
            assert compared == 12 - _LAGS[k], (channel, k)
            assert matched == compared, (channel, k)
            for lag in (-2, -1, 0, 1, 2):
                if lag == _LAGS[k]:
                    continue
                matched, compared = _agreement(hf, st, st_span, hf_span, lag, 0.0)
                assert compared >= 9, (channel, k, lag)
                assert 2 * matched < compared, (channel, k, lag)


def test_the_first_healthfit_instant_of_a_plus1_stretch_equals_no_stryd_value(
    hf_run: list[Record], stryd_run: list[Record]
) -> None:
    st_spans = _stretches(_offsets(stryd_run, _RUN_START))
    for channel in ("distance", "power"):
        hf = _series(hf_run, _RUN_START, channel)
        st = _series(stryd_run, _RUN_START, channel)
        for k, (first, last) in enumerate(st_spans):
            if _LAGS[k] != 1:
                continue
            stretch_values = {st[t] for t in range(first, last + 1)}
            assert hf[first] not in stretch_values, (channel, k)


def test_heart_rate_agrees_at_minus_one_and_at_neither_zero_nor_plus_one(
    hf_run: list[Record], stryd_run: list[Record]
) -> None:
    st_spans = _stretches(_offsets(stryd_run, _RUN_START))
    hf_spans = _stretches(_offsets(hf_run, _RUN_START))
    hf = _series(hf_run, _RUN_START, "heart_rate")
    st = _series(stryd_run, _RUN_START, "heart_rate")
    for k, (st_span, hf_span) in enumerate(zip(st_spans, hf_spans, strict=True)):
        assert _agreement(hf, st, st_span, hf_span, -1, 0.0) == (11, 11), k
        assert _agreement(hf, st, st_span, hf_span, 0, 0.0)[0] == 0, k
        assert _agreement(hf, st, st_span, hf_span, 1, 0.0)[0] == 0, k


def test_step_length_is_eight_tenths_of_a_percent_higher_in_the_stryd_file(
    hf_run: list[Record], stryd_run: list[Record]
) -> None:
    hf = _series(hf_run, _RUN_START, "step_length")
    st = _series(stryd_run, _RUN_START, "step_length")
    common = sorted(set(hf) & set(st))
    assert len(common) == 60
    for t in common:
        assert abs(st[t] / hf[t] - 1.008) < 1e-4, t


def test_cadence_differs_by_one_alternating_in_each_stretch(
    hf_run: list[Record], stryd_run: list[Record]
) -> None:
    hf = _series(hf_run, _RUN_START, "cadence")
    st = _series(stryd_run, _RUN_START, "cadence")
    for first, last in _stretches(_offsets(stryd_run, _RUN_START)):
        diffs = [hf[t] - st[t] for t in range(first, last + 1)]
        assert diffs == [1.0, -1.0] * 6, first


def test_values_are_pairwise_distinct_within_every_channel_of_every_stretch(
    hf_run: list[Record], stryd_run: list[Record]
) -> None:
    _assert_distinct_per_stretch(hf_run, _RUN_START, "healthfit")
    _assert_distinct_per_stretch(stryd_run, _RUN_START, "stryd")


# --- run pair: channels -------------------------------------------------------


def test_stryd_only_channels_are_all_running_dynamics_channels(
    hf_run: list[Record], stryd_run: list[Record]
) -> None:
    stryd_names = {k for r in stryd_run for k in r}
    hf_names = {k for r in hf_run for k in r}
    stryd_only = stryd_names - hf_names
    assert stryd_only == set(_STRYD_ONLY)
    assert {_STRYD_ONLY[n] for n in stryd_only} <= set(DYNAMICS_CHANNELS)
    # every non-dynamics channel the Stryd file records is in the copy too
    for channel in ("heart_rate", "power", "distance", "enhanced_speed", "cadence"):
        assert all(channel in r for r in stryd_run), channel
        assert all(channel in r for r in hf_run), channel


def test_the_healthfit_copy_has_no_developer_record_channels_and_no_stance_balance(
    pair: tuple[bytes, bytes],
) -> None:
    messages = _decode(pair[0])
    assert all("developer_fields" not in r for r in messages["record_mesgs"])
    assert not any("stance_time_balance" in r for r in messages["record_mesgs"])
    assert [d["field_name"] for d in messages["field_description_mesgs"]] == [
        "SESSION UUID"
    ]


def test_laps_differ_in_count_and_value_and_only_healthfit_has_heart_rate(
    pair: tuple[bytes, bytes],
) -> None:
    hf_laps = _decode(pair[0])["lap_mesgs"]
    st_laps = _decode(pair[1])["lap_mesgs"]
    assert (len(st_laps), len(hf_laps)) == (4, 5)
    assert all("avg_heart_rate" in lap for lap in hf_laps)
    assert not any("avg_heart_rate" in lap for lap in st_laps)
    for key in ("total_distance", "total_elapsed_time"):
        hf_values = {lap[key] for lap in hf_laps}
        st_values = {lap[key] for lap in st_laps}
        assert hf_values.isdisjoint(st_values), key


# --- run pair: sessions, identity values, devices ------------------------------


def test_run_sessions_carry_the_measured_start_elapsed_and_distance(
    pair: tuple[bytes, bytes],
) -> None:
    hf, st = _session(pair[0]), _session(pair[1])
    assert hf["start_time"] == st["start_time"] == _RUN_START
    assert hf["total_elapsed_time"] == 78.0
    assert st["total_elapsed_time"] == 86.5
    assert hf["total_distance"] == st["total_distance"] == 250.0
    assert hf["sport"] == st["sport"] == "running"


def test_the_healthfit_copy_records_a_session_uuid_and_the_stryd_file_does_not(
    pair: tuple[bytes, bytes],
) -> None:
    hf = _decode(pair[0])
    descriptions = hf["field_description_mesgs"]
    assert [(d["field_name"], d["field_definition_number"]) for d in descriptions] == [
        ("SESSION UUID", 0)
    ]
    assert hf["session_mesgs"][0]["developer_fields"] == {
        0: list(range(40, 56)),
    }
    assert "developer_fields" not in _session(pair[1])


def test_run_recording_devices_and_file_id_manufacturers_are_not_garmin(
    pair: tuple[bytes, bytes],
) -> None:
    healthfit, stryd = pair
    assert _file_id(healthfit)["manufacturer"] == "development"
    assert _device_zero(healthfit)["manufacturer"] == "development"
    assert _file_id(stryd)["manufacturer"] == "stryd"
    assert _device_zero(stryd)["manufacturer"] == "stryd"


# --- run trio ------------------------------------------------------------------


def test_the_trio_is_the_pair_plus_a_later_stryd_file_with_form_power_one_higher() -> (
    None
):
    healthfit, stryd_a, stryd_b = merge.run_trio_fit_bytes()
    pair_healthfit, pair_stryd = merge.run_pair_fit_bytes()
    assert healthfit == pair_healthfit
    assert stryd_a == pair_stryd
    assert stryd_b != stryd_a

    assert _num(_file_id(stryd_b), "time_created") > _num(
        _file_id(stryd_a), "time_created"
    )
    rec_a, rec_b = _records(stryd_a), _records(stryd_b)
    assert len(rec_a) == len(rec_b) == 60
    for a, b in zip(rec_a, rec_b, strict=True):
        assert _num(b, "Form Power") == _num(a, "Form Power") + 1
        assert {k: v for k, v in a.items() if k != "Form Power"} == {
            k: v for k, v in b.items() if k != "Form Power"
        }
    assert _session(stryd_a) == _session(stryd_b)
    assert _decode(stryd_a)["lap_mesgs"] == _decode(stryd_b)["lap_mesgs"]
    for data in (stryd_a, stryd_b):
        assert _file_id(data)["manufacturer"] == "stryd"
        assert _device_zero(data)["manufacturer"] == "stryd"


# --- ride pair -----------------------------------------------------------------


def test_the_garmin_ride_has_three_stretches_of_34_samples_and_no_heart_rate(
    rides: tuple[bytes, bytes],
) -> None:
    records = _records(rides[0])
    offsets = _offsets(records, _RIDE_START)
    assert _stretches(offsets) == [(0, 33), (38, 71), (76, 109)]
    assert len(offsets) == 102
    for channel in (
        "power",
        "distance",
        "speed",
        "enhanced_altitude",
        "temperature",
        "position_lat",
        "position_long",
        "cadence",
    ):
        assert all(channel in r for r in records), channel
    assert not any("heart_rate" in r for r in records)
    session = _session(rides[0])
    assert "avg_heart_rate" not in session and "max_heart_rate" not in session
    assert session["sport"] == "cycling"
    assert session["start_time"] == _RIDE_START
    assert session["total_elapsed_time"] == 109.0
    assert session["total_distance"] == 450.0
    messages = _decode(rides[0])
    assert "developer_data_id_mesgs" not in messages
    assert all("developer_fields" not in m for m in messages["session_mesgs"])
    _assert_distinct_per_stretch(records, _RIDE_START, "garmin ride")


def test_the_ride_copy_has_the_same_instants_heart_rate_everywhere_and_no_position(
    rides: tuple[bytes, bytes],
) -> None:
    original, copy = _records(rides[0]), _records(rides[1])
    assert _offsets(copy, _RIDE_START) == _offsets(original, _RIDE_START)
    assert _session(rides[1])["start_time"] == _session(rides[0])["start_time"]
    assert _session(rides[1])["sport"] == "cycling"
    assert all("heart_rate" in r for r in copy)
    for channel in ("position_lat", "position_long"):
        assert not any(channel in r for r in copy), channel
    _assert_distinct_per_stretch(copy, _RIDE_START, "ride copy")


def test_the_ride_copy_power_is_missing_on_one_sample_and_equals_the_original_elsewhere(
    rides: tuple[bytes, bytes],
) -> None:
    original, copy = _records(rides[0]), _records(rides[1])
    missing = [i for i, r in enumerate(copy) if "power" not in r]
    assert len(missing) == 1
    for i, (o, c) in enumerate(zip(original, copy, strict=True)):
        assert "power" in o
        if i not in missing:
            assert c["power"] == o["power"], i


def test_ride_copy_distance_matches_at_no_lag_and_power_only_at_lag_zero(
    rides: tuple[bytes, bytes],
) -> None:
    original, copy = _records(rides[0]), _records(rides[1])
    spans = _stretches(_offsets(original, _RIDE_START))
    assert len(spans) == 3
    o_distance = _series(original, _RIDE_START, "distance")
    c_distance = _series(copy, _RIDE_START, "distance")
    assert all(abs(c_distance[t] - o_distance[t]) >= 0.1 for t in o_distance)
    o_power = _series(original, _RIDE_START, "power")
    c_power = _series(copy, _RIDE_START, "power")
    for k, span in enumerate(spans):
        for lag in (-2, -1, 0, 1, 2):
            matched, compared = _agreement(
                c_distance, o_distance, span, span, lag, 0.005
            )
            assert compared >= 32, (k, lag)
            assert matched == 0, (k, lag)
            matched, compared = _agreement(c_power, o_power, span, span, lag, 0.0)
            if lag == 0:
                expected = 33 if k == 1 else 34
                assert (matched, compared) == (expected, expected), k
            else:
                assert matched == 0, (k, lag)
    totals = (
        _num(_session(rides[0]), "total_distance"),
        _num(_session(rides[1]), "total_distance"),
    )
    assert abs(totals[0] - totals[1]) <= 5.0


def test_ride_copy_power_off_leaves_no_power_and_a_shift_moves_every_instant_an_hour(
    rides: tuple[bytes, bytes],
) -> None:
    garmin, no_power = merge.ride_pair_fit_bytes(copy_power=False)
    assert garmin == rides[0]
    assert not any("power" in r for r in _records(no_power))
    assert all("heart_rate" in r and "distance" in r for r in _records(no_power))

    shifted_garmin, shifted = merge.ride_pair_fit_bytes(copy_shift_h=1)
    assert shifted_garmin == rides[0]
    base, moved = _records(rides[1]), _records(shifted)
    assert _offsets(moved, _RIDE_START) == [
        t + 3600 for t in _offsets(base, _RIDE_START)
    ]
    assert _session(shifted)["start_time"] == _RIDE_START + 3600
    assert _session(rides[1])["start_time"] == _RIDE_START
    assert [{k: v for k, v in r.items() if k != "timestamp"} for r in moved] == [
        {k: v for k, v in r.items() if k != "timestamp"} for r in base
    ]


def test_ride_recording_devices_garmin_original_and_development_copy(
    rides: tuple[bytes, bytes],
) -> None:
    garmin, copy = rides
    assert _file_id(garmin)["manufacturer"] == "garmin"
    assert _device_zero(garmin)["manufacturer"] == "garmin"
    assert _file_id(copy)["manufacturer"] == "development"
    assert _device_zero(copy)["manufacturer"] == "development"


def test_the_ride_copy_records_a_session_uuid_and_the_original_does_not(
    rides: tuple[bytes, bytes],
) -> None:
    copy = _decode(rides[1])
    assert [d["field_name"] for d in copy["field_description_mesgs"]] == [
        "SESSION UUID"
    ]
    assert copy["session_mesgs"][0]["developer_fields"] == {0: list(range(90, 106))}
    assert "field_description_mesgs" not in _decode(rides[0])


# --- identity joins every pair and ranks the base first --------------------------


def _key(data: bytes) -> SessionKey:
    return session_key(parse_fit(data))


def _roles(files: Mapping[str, bytes]) -> PageRoles:
    members = [
        source_member(ref, hashlib.sha256(data).hexdigest(), parse_fit(data))
        for ref, data in files.items()
    ]
    return rank_members(members, [], DEFAULT_PRECEDENCE)


def test_identity_joins_every_run_pair_and_trio_pair_strictly() -> None:
    healthfit, stryd_a, stryd_b = merge.run_trio_fit_bytes()
    keys = {"hf": _key(healthfit), "a": _key(stryd_a), "b": _key(stryd_b)}
    for left, right in (("hf", "a"), ("hf", "b"), ("a", "b")):
        assert pair_evidence(keys[left], keys[right]) is Evidence.STRICT, (left, right)
        assert pair_evidence(keys[right], keys[left]) is Evidence.STRICT, (left, right)


def test_identity_joins_the_ride_strictly_and_the_shifted_ride_by_shift() -> None:
    garmin, copy = merge.ride_pair_fit_bytes()
    assert pair_evidence(_key(garmin), _key(copy)) is Evidence.STRICT
    garmin, shifted = merge.ride_pair_fit_bytes(copy_shift_h=1)
    assert pair_evidence(_key(garmin), _key(shifted)) is Evidence.SHIFTED
    assert pair_evidence(_key(shifted), _key(garmin)) is Evidence.SHIFTED


def test_under_the_default_precedence_the_healthfit_copy_leads_the_run_trio() -> None:
    healthfit, stryd_a, stryd_b = merge.run_trio_fit_bytes()
    roles = _roles({"stryd_a": stryd_a, "hf": healthfit, "stryd_b": stryd_b})
    assert roles.base.ref == "hf"
    assert [m.ref for m in roles.extras] == ["stryd_b", "stryd_a"]
    reordered = _roles({"stryd_b": stryd_b, "stryd_a": stryd_a, "hf": healthfit})
    assert reordered.base.ref == "hf"
    assert [m.ref for m in reordered.extras] == ["stryd_b", "stryd_a"]


def test_under_the_default_precedence_the_garmin_original_leads_the_ride_copy() -> None:
    garmin, copy = merge.ride_pair_fit_bytes()
    roles = _roles({"copy": copy, "garmin": garmin})
    assert roles.base.ref == "garmin"
    assert [m.ref for m in roles.extras] == ["copy"]
