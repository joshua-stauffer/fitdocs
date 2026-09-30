"""Running-dynamics channel policy (running-dynamics 3.1-3.3, 4.1-4.4, 5.2-5.4, 5.6).

The unit cases call :func:`fitdocs.ingest.dynamics.extract_dynamics` on hand-built
records whose twelve channels hold pairwise-distinct non-zero values (``_base``),
then override the samples under test. The per-channel cases change one channel
at one sample, so the other eleven hold non-zero values there; the all-zeros,
zero-type and value-type cases change more than one. The whole-file cases decode
the Stryd fixture, the native-dynamics fixture and files built by
``developer_field_run_fit_bytes``. Expected tables below are literals written from
requirements 3.1, 4.1 and 5.2-5.4, not read from the module under test.
"""

from __future__ import annotations

import pytest

from fitdocs import Activity, parse_fit
from fitdocs.ingest.dynamics import (
    DEVELOPER_DYNAMICS_NAMES,
    GATES,
    NATIVE_DYNAMICS_FIELDS,
    PLACEHOLDER_ZERO_CHANNELS,
    extract_dynamics,
)
from fitdocs.ingest.records import extract_samples
from fitdocs.model import DYNAMICS_CHANNELS, DeveloperChannel, Modality
from tests.fixtures import builder
from tests.fixtures.builder import (
    BASE_TYPE,
    DevFieldSpec,
    developer_field_run_fit_bytes,
    run_fit_bytes,
    run_native_dynamics_fit_bytes,
    stryd_run_fit_bytes,
)

_ABSENT = object()
_N = 3  # samples in a unit case

_NATIVE_BY_CHANNEL = {
    "stance_time_ms": "stance_time",
    "stance_time_balance_pct": "stance_time_balance",
    "vertical_oscillation_mm": "vertical_oscillation",
    "vertical_ratio_pct": "vertical_ratio",
    "step_length_mm": "step_length",
}
_NAME_BY_CHANNEL = {
    "vertical_oscillation_balance_pct": "Vertical Oscillation Balance",
    "leg_spring_stiffness_kn_m": "Leg Spring Stiffness",
    "leg_spring_stiffness_balance_pct": "Leg Spring Stiffness Balance",
    "form_power_w": "Form Power",
    "air_power_w": "Air Power",
    "impact_bw": "Impact",
    "impact_loading_rate_balance_pct": "Impact Loading Rate Balance",
}
# gate channel -> the balance / air power channel it gates (5.3, 5.4)
_PARTNER = {
    "stance_time_ms": "stance_time_balance_pct",
    "vertical_oscillation_mm": "vertical_oscillation_balance_pct",
    "leg_spring_stiffness_kn_m": "leg_spring_stiffness_balance_pct",
    "impact_bw": "impact_loading_rate_balance_pct",
    "form_power_w": "air_power_w",
}
_GATED = sorted(_PARTNER.values())
_PLACEHOLDER = sorted(
    {
        "stance_time_ms",
        "vertical_oscillation_mm",
        "vertical_ratio_pct",
        "step_length_mm",
        "leg_spring_stiffness_kn_m",
        "form_power_w",
        "impact_bw",
    }
)
_NATIVE_CHANNELS = sorted(_NATIVE_BY_CHANNEL)
_DEVELOPER_CHANNELS = sorted(_NAME_BY_CHANNEL)


def _base(channel: str, sample: int) -> float:
    """A non-zero value unique to (channel, sample)."""
    return 100.0 * (DYNAMICS_CHANNELS.index(channel) + 1) + sample + 0.25


def _developer(
    name: str,
    values: list[object],
    *,
    index: int = 0,
    application_id: str | None = None,
    declared_scale: bool = False,
) -> DeveloperChannel:
    return DeveloperChannel(
        name=name,
        units=None,
        developer_data_index=index,
        field_definition_number=None,
        application_id=application_id,
        declared_scale=declared_scale,
        values=tuple(values),
    )


def _inputs(
    overrides: dict[tuple[str, int], object],
) -> tuple[list[dict[str, object]], dict[str, DeveloperChannel]]:
    """Records and developer channels: ``_base`` everywhere except ``overrides``.

    An override value of ``_ABSENT`` leaves a native key out of the record and
    writes ``None`` into a developer channel's ``values``.
    """
    records: list[dict[str, object]] = [{} for _ in range(_N)]
    developer_values: dict[str, list[object]] = {
        name: [] for name in _NAME_BY_CHANNEL.values()
    }
    for channel in DYNAMICS_CHANNELS:
        for sample in range(_N):
            value = overrides.get((channel, sample), _base(channel, sample))
            native = _NATIVE_BY_CHANNEL.get(channel)
            if native is not None:
                if value is not _ABSENT:
                    records[sample][native] = value
            else:
                developer_values[_NAME_BY_CHANNEL[channel]].append(
                    None if value is _ABSENT else value
                )
    developer = {
        name: _developer(name, values) for name, values in developer_values.items()
    }
    return records, developer


def _expected(
    changes: dict[tuple[str, int], float | None],
) -> dict[str, tuple[float | None, ...]]:
    """``_base`` values everywhere except ``changes``."""
    return {
        channel: tuple(changes.get((channel, s), _base(channel, s)) for s in range(_N))
        for channel in DYNAMICS_CHANNELS
    }


def _run(
    overrides: dict[tuple[str, int], object],
) -> dict[str, tuple[float | None, ...]]:
    records, developer = _inputs(overrides)
    return extract_dynamics(records, developer)


# --- Table invariants --------------------------------------------------------


def test_native_keys_and_name_table_values_partition_the_channel_set() -> None:
    assert len(NATIVE_DYNAMICS_FIELDS) == 5
    assert len(DEVELOPER_DYNAMICS_NAMES) == 7
    native = set(NATIVE_DYNAMICS_FIELDS)
    developer = set(DEVELOPER_DYNAMICS_NAMES.values())
    assert len(developer) == 7
    assert native.isdisjoint(developer)
    assert native | developer == set(DYNAMICS_CHANNELS)


def test_placeholder_set_and_gate_keys_partition_the_channel_set() -> None:
    assert len(PLACEHOLDER_ZERO_CHANNELS) == 7
    assert len(GATES) == 5
    assert PLACEHOLDER_ZERO_CHANNELS.isdisjoint(GATES)
    assert PLACEHOLDER_ZERO_CHANNELS | set(GATES) == set(DYNAMICS_CHANNELS)
    assert set(GATES.values()) <= PLACEHOLDER_ZERO_CHANNELS
    assert len(set(GATES.values())) == 5  # one partner per gate


def test_the_exact_gate_pairs_and_placeholder_set() -> None:
    assert dict(GATES) == {
        "stance_time_balance_pct": "stance_time_ms",
        "vertical_oscillation_balance_pct": "vertical_oscillation_mm",
        "leg_spring_stiffness_balance_pct": "leg_spring_stiffness_kn_m",
        "impact_loading_rate_balance_pct": "impact_bw",
        "air_power_w": "form_power_w",
    }
    assert set(PLACEHOLDER_ZERO_CHANNELS) == {
        "stance_time_ms",
        "vertical_oscillation_mm",
        "vertical_ratio_pct",
        "step_length_mm",
        "leg_spring_stiffness_kn_m",
        "form_power_w",
        "impact_bw",
    }


def test_the_exact_name_table_and_native_map() -> None:
    assert dict(DEVELOPER_DYNAMICS_NAMES) == {
        "Form Power": "form_power_w",
        "Air Power": "air_power_w",
        "Leg Spring Stiffness": "leg_spring_stiffness_kn_m",
        "Impact": "impact_bw",
        "Leg Spring Stiffness Balance": "leg_spring_stiffness_balance_pct",
        "Impact Loading Rate Balance": "impact_loading_rate_balance_pct",
        "Vertical Oscillation Balance": "vertical_oscillation_balance_pct",
    }
    assert dict(NATIVE_DYNAMICS_FIELDS) == {
        "step_length_mm": "step_length",
        "vertical_oscillation_mm": "vertical_oscillation",
        "stance_time_ms": "stance_time",
        "stance_time_balance_pct": "stance_time_balance",
        "vertical_ratio_pct": "vertical_ratio",
    }


# --- extract_dynamics: sources (3.1, 4.1, 4.2) ---------------------------------


def test_every_channel_reads_its_own_source_with_no_conversion() -> None:
    result = _run({})
    assert result == _expected({})
    assert tuple(result) == DYNAMICS_CHANNELS
    all_values = [v for series in result.values() for v in series]
    assert len(set(all_values)) == len(all_values) == 12 * _N  # pairwise distinct


def test_each_developer_channel_is_read_from_its_named_field_only() -> None:
    """Swap the values of two developer fields and exactly their channels move."""
    records, developer = _inputs({})
    swapped = dict(developer)
    swapped["Form Power"] = _developer("Form Power", list(developer["Impact"].values))
    swapped["Impact"] = _developer("Impact", list(developer["Form Power"].values))
    result = extract_dynamics(records, swapped)
    base = _run({})
    assert result["form_power_w"] == base["impact_bw"]
    assert result["impact_bw"] == base["form_power_w"]
    for channel in set(DYNAMICS_CHANNELS) - {"form_power_w", "impact_bw"}:
        assert result[channel] == base[channel], channel


# --- 3.2, 3.3: absence -----------------------------------------------------------


@pytest.mark.parametrize("channel", _NATIVE_CHANNELS)
def test_an_absent_native_value_is_none_only_at_that_sample(channel: str) -> None:
    result = _run({(channel, 1): _ABSENT})
    changes: dict[tuple[str, int], float | None] = {(channel, 1): None}
    if channel in _PARTNER:
        changes[(_PARTNER[channel], 1)] = None
    assert result == _expected(changes)


def test_records_with_no_dynamics_and_no_developer_give_all_none() -> None:
    result = extract_dynamics([{"heart_rate": 150}, {}, {"power": 0}], {})
    assert tuple(result) == DYNAMICS_CHANNELS
    assert all(series == (None, None, None) for series in result.values())


def test_no_records_gives_empty_series() -> None:
    assert extract_dynamics([], {}) == {name: () for name in DYNAMICS_CHANNELS}


# --- 5.2: placeholder zeros, each of the seven ---------------------------------


@pytest.mark.parametrize("channel", _PLACEHOLDER)
def test_a_zero_placeholder_alone_beside_non_zero_values_is_none(
    channel: str,
) -> None:
    changes: dict[tuple[str, int], float | None] = {(channel, 0): None}
    if channel in _PARTNER:
        changes[(_PARTNER[channel], 0)] = None  # its partner is gated out with it
    assert _run({(channel, 0): 0}) == _expected(changes)


@pytest.mark.parametrize("channel", _PLACEHOLDER)
def test_only_zero_is_a_placeholder_a_negative_value_is_kept(channel: str) -> None:
    assert _run({(channel, 0): -1.5}) == _expected({(channel, 0): -1.5})


def test_developer_values_keep_their_integer_type() -> None:
    result = _run({("form_power_w", 0): 301, ("impact_bw", 0): 4.5})
    assert type(result["form_power_w"][0]) is int
    assert type(result["impact_bw"][0]) is float


@pytest.mark.parametrize("zero", [0, 0.0])
def test_placeholder_zero_is_none_for_int_and_float_zero(zero: float) -> None:
    result = _run({("step_length_mm", 2): zero, ("form_power_w", 2): zero})
    assert result["step_length_mm"][2] is None
    assert result["form_power_w"][2] is None


# --- 5.3, 5.4: gated channels ----------------------------------------------------


@pytest.mark.parametrize("gated", _GATED)
def test_a_recorded_zero_of_a_gated_channel_is_kept_beside_its_gate(
    gated: str,
) -> None:
    result = _run({(gated, 0): 0.0})
    assert result[gated][0] is not None
    assert result[gated][0] == 0
    assert result == _expected({(gated, 0): 0.0})


@pytest.mark.parametrize("gate", sorted(_PARTNER))
def test_an_absent_gate_channel_gates_its_partner_only(gate: str) -> None:
    """The gate is absent, not zero; its partner holds a recorded non-zero value."""
    partner = _PARTNER[gate]
    assert _base(partner, 0) != 0
    result = _run({(gate, 0): _ABSENT})
    assert result == _expected({(gate, 0): None, (partner, 0): None})


@pytest.mark.parametrize("gate", sorted(_PARTNER))
def test_a_placeholder_zero_gate_gates_a_non_zero_partner(gate: str) -> None:
    """Placeholders run before gates: the gate's zero is already ``None``."""
    partner = _PARTNER[gate]
    result = _run({(gate, 1): 0})
    assert result[gate][1] is None
    assert result[partner][1] is None
    assert result == _expected({(gate, 1): None, (partner, 1): None})


def test_a_sample_of_all_zeros_is_all_none() -> None:
    result = _run({(channel, 0): 0 for channel in DYNAMICS_CHANNELS})
    assert all(series[0] is None for series in result.values())
    assert all(series[1:] == _expected({})[c][1:] for c, series in result.items())


# --- developer values that are not real numbers (4.2) ----------------------------


@pytest.mark.parametrize("bad", [(1.0, 2.0), "12", True, b"x"])
@pytest.mark.parametrize("channel", _DEVELOPER_CHANNELS)
def test_a_recognized_developer_value_that_is_not_a_number_is_none(
    channel: str, bad: object
) -> None:
    result = _run({(channel, 1): bad})
    changes: dict[tuple[str, int], float | None] = {(channel, 1): None}
    if channel in _PARTNER:
        changes[(_PARTNER[channel], 1)] = None
    assert result == _expected(changes)


def test_a_native_value_that_is_not_a_number_raises_like_every_native_channel() -> None:
    records, developer = _inputs({})
    records[1]["stance_time"] = "240"
    with pytest.raises(TypeError):
        extract_dynamics(records, developer)


def test_developer_fields_with_native_names_never_fill_native_channels() -> None:
    """A developer field named like a native field loses to the native record value
    and fills nothing when the native value is absent."""
    records, developer = _inputs({("stance_time_ms", 1): _ABSENT})
    decoys = {
        name: _developer(name, [-1.0 * (i + 1)] * _N)
        for i, name in enumerate(
            [
                "Stance Time",
                "stance_time",
                "Vertical Oscillation",
                "vertical_oscillation",
                "Vertical Ratio",
                "Step Length",
                "Stance Time Balance",
            ]
        )
    }
    result = extract_dynamics(records, {**developer, **decoys})
    expected = _expected(
        {("stance_time_ms", 1): None, ("stance_time_balance_pct", 1): None}
    )
    assert result == expected


# --- extract_samples wiring -------------------------------------------------------


def test_extract_samples_defaults_to_no_developer_fields() -> None:
    ts = builder.FIT_TIMESTAMP_BASE
    samples, _ = extract_samples(
        [{"timestamp": ts, "stance_time": 250.0}, {"timestamp": ts + 1}], None
    )
    assert samples.stance_time_ms == (250.0, None)
    assert samples.form_power_w == (None, None)


def test_extract_samples_aligns_developer_values_with_the_retained_records() -> None:
    ts = builder.FIT_TIMESTAMP_BASE
    records: list[dict[str, object]] = [
        {"timestamp": ts, "stance_time": 251.0},
        {"stance_time": 999.0},  # no timestamp: not retained
        {"timestamp": ts + 2, "stance_time": 253.0},
    ]
    developer = {"Form Power": _developer("Form Power", [301, 303])}
    samples, _ = extract_samples(records, None, developer=developer)
    assert samples.time_s == (0.0, 2.0)
    assert samples.stance_time_ms == (251.0, 253.0)
    assert samples.form_power_w == (301, 303)


# --- whole files ------------------------------------------------------------------


def _position(name: str) -> int:
    """A Stryd fixture description's position (its key in the recorded values)."""
    return [spec.name for spec in builder._STRYD_DESCRIPTIONS].index(name)


def _stryd_expected() -> dict[str, list[float | None]]:
    """Each channel, computed from the fixture's own recorded series."""
    expected: dict[str, list[float | None]] = {c: [] for c in DYNAMICS_CHANNELS}
    for i, (native, recorded) in enumerate(builder._stryd_records()):
        placeholder = i in builder._STRYD_PLACEHOLDERS

        def dev(name: str, recorded: dict[int, object] = recorded) -> float | None:
            value = recorded[_position(name)]
            return value if isinstance(value, int | float) else None

        stance = None if placeholder else native["stance_time"]
        oscillation = None if placeholder else native["vertical_oscillation"]
        form = (
            None
            if placeholder or i == builder._STRYD_SENTINEL_INDEX
            else dev("Form Power")
        )
        stiffness = None if placeholder else dev("Leg Spring Stiffness")
        impact = None if placeholder else dev("Impact")
        expected["stance_time_ms"].append(stance)
        expected["stance_time_balance_pct"].append(
            None if stance is None else native["stance_time_balance"]
        )
        expected["vertical_oscillation_mm"].append(oscillation)
        expected["vertical_oscillation_balance_pct"].append(
            None if oscillation is None else dev("Vertical Oscillation Balance")
        )
        expected["vertical_ratio_pct"].append(None)
        expected["step_length_mm"].append(
            None if placeholder else native["step_length"]
        )
        expected["leg_spring_stiffness_kn_m"].append(stiffness)
        expected["leg_spring_stiffness_balance_pct"].append(
            None if stiffness is None else dev("Leg Spring Stiffness Balance")
        )
        expected["form_power_w"].append(form)
        expected["air_power_w"].append(None if form is None else dev("Air Power"))
        expected["impact_bw"].append(impact)
        expected["impact_loading_rate_balance_pct"].append(
            None if impact is None else dev("Impact Loading Rate Balance")
        )
    return expected


def _channels(activity: Activity) -> dict[str, tuple[float | None, ...]]:
    return {name: getattr(activity.samples, name) for name in DYNAMICS_CHANNELS}


def test_the_stryd_fixture_dynamics_equal_the_rule_applied_to_its_series() -> None:
    activity = parse_fit(stryd_run_fit_bytes())
    channels = _channels(activity)
    expected = _stryd_expected()
    for name in DYNAMICS_CHANNELS:
        assert channels[name] == tuple(expected[name]), name


def test_the_stryd_fixture_pins_placeholders_pause_sentinel_and_kept_zeros() -> None:
    samples = parse_fit(stryd_run_fit_bytes()).samples
    pause = sorted(builder._STRYD_PLACEHOLDERS)
    assert pause == [0, 20, 21, 22]
    for name in DYNAMICS_CHANNELS:
        series = getattr(samples, name)
        assert [series[i] for i in pause] == [None] * 4, name
        if name != "vertical_ratio_pct":  # the fixture carries no native ratio
            recorded = [i for i in range(44) if i not in pause and i != 10]
            assert all(series[i] is not None for i in recorded), name
    # the mid-run recorded 0.0 balance is a real value beside a real oscillation
    assert samples.vertical_oscillation_mm[12] is not None
    assert samples.vertical_oscillation_balance_pct[12] == 0.0
    assert samples.vertical_oscillation_balance_pct[12] is not None
    # the uint16 sentinel: form power not recorded, so air power is gated out too
    assert samples.form_power_w[10] is None
    assert samples.air_power_w[10] is None
    # air power recorded 0 beside non-zero form power stays 0
    assert samples.form_power_w[14] is not None and samples.form_power_w[14] > 0
    assert samples.air_power_w[14] == 0
    assert samples.air_power_w[14] is not None
    # vertical ratio is not native to this fixture
    assert samples.vertical_ratio_pct == (None,) * 44


_WRITERS = [
    ("stryd", None),
    ("garmin", None),
    ("stryd", "garmin"),
    ("garmin", "stryd"),
    ("coros", None),
]


@pytest.mark.parametrize(("manufacturer", "device"), _WRITERS)
def test_the_twelve_channels_do_not_depend_on_which_application_wrote_the_file(
    manufacturer: str, device: str | None
) -> None:
    baseline = _channels(parse_fit(stryd_run_fit_bytes()))
    assert any(v is None for v in baseline["form_power_w"])
    assert any(v is not None for v in baseline["form_power_w"])
    activity = parse_fit(_stryd_with_writer(manufacturer, device))
    assert _channels(activity) == baseline


def test_stryd_run_fit_bytes_garmin_writer_yields_the_same_twelve_channels() -> None:
    assert _channels(parse_fit(stryd_run_fit_bytes(manufacturer="garmin"))) == (
        _channels(parse_fit(stryd_run_fit_bytes()))
    )


def _stryd_with_writer(manufacturer: str, device: str | None) -> bytes:
    records = [
        ({**native}, dict(recorded)) for native, recorded in builder._stryd_records()
    ]
    return developer_field_run_fit_bytes(
        descriptions=builder._STRYD_DESCRIPTIONS,
        records=records,
        manufacturer=manufacturer,
        device_manufacturer=device,
    )


def test_the_native_dynamics_fixture_fills_its_three_channels_and_nothing_else() -> (
    None
):
    activity = parse_fit(run_native_dynamics_fit_bytes())
    samples = activity.samples
    n = 20
    assert len(samples.time_s) == n
    assert samples.vertical_oscillation_mm == pytest.approx(
        tuple(85.0 + 1.0 * (i % 7) for i in range(n))
    )
    assert samples.stance_time_ms == pytest.approx(
        tuple(250.0 + 3.0 * (i % 5) for i in range(n))
    )
    assert samples.vertical_ratio_pct == pytest.approx(
        tuple(7.0 + 0.1 * (i % 6) for i in range(n))
    )
    filled = {"vertical_oscillation_mm", "stance_time_ms", "vertical_ratio_pct"}
    others = [c for c in DYNAMICS_CHANNELS if c not in filled]
    assert len(others) == 9
    for name in others:
        assert getattr(samples, name) == (None,) * n, name


def test_a_file_without_dynamics_has_every_dynamics_channel_none() -> None:
    samples = parse_fit(run_fit_bytes()).samples
    n = len(samples.time_s)
    assert n > 0
    for name in DYNAMICS_CHANNELS:
        assert getattr(samples, name) == (None,) * n, name


# --- names that are not in the table (4.3) ----------------------------------------

_UINT16 = BASE_TYPE["UINT16"]
_FLOAT32 = BASE_TYPE["FLOAT32"]

_UNRECOGNIZED = (
    "Form power",  # case differs
    "FORM POWER",
    "Form Power ",  # trailing space
    "Stryd Form Power",
    "Power",
    "Stryd Humidity",
    "Stryd Temperature",
    "Speed",
    "Distance",
    "Stance Time",
    "Vertical Oscillation",
    "Vertical Ratio",
    "Step Length",
    "Stance Time Balance",
    "air power",
    "impact",
    "Leg Spring Stiffness balance",
)


def test_unrecognized_developer_names_fill_no_channel_and_stay_generic() -> None:
    descriptions = tuple(
        DevFieldSpec(name, _UINT16, 20 + i) for i, name in enumerate(_UNRECOGNIZED)
    )
    records = [
        ({}, {i: 500 + 10 * s + i for i in range(len(_UNRECOGNIZED))}) for s in range(4)
    ]
    activity = parse_fit(
        developer_field_run_fit_bytes(descriptions=descriptions, records=records)
    )
    for name in DYNAMICS_CHANNELS:
        assert getattr(activity.samples, name) == (None,) * 4, name
    assert set(activity.record_developer_fields) == set(_UNRECOGNIZED)
    assert activity.record_developer_fields["Form power"].values == (
        500,
        510,
        520,
        530,
    )


def test_developer_speed_and_distance_never_fill_the_native_channels() -> None:
    """Developer ``Speed``/``Distance`` differ from, and never stand in for, native."""
    descriptions = (
        DevFieldSpec("Speed", _FLOAT32, 8, units="m/s", native_mesg_num=20),
        DevFieldSpec("Distance", _FLOAT32, 9, units="m", native_mesg_num=20),
        DevFieldSpec("Power", _UINT16, 10, units="W", native_mesg_num=20),
    )
    records = [
        (
            {"enhanced_speed": 3.5, "distance": 10.5, "power": 210},
            {0: 7.5, 1: 99.5, 2: 77},
        ),
        ({}, {0: 8.5, 1: 100.5, 2: 78}),
        (
            {"enhanced_speed": 0.0, "distance": 0.0, "power": 0},
            {0: 9.5, 1: 101.5, 2: 79},
        ),
    ]
    samples = parse_fit(
        developer_field_run_fit_bytes(descriptions=descriptions, records=records)
    ).samples
    assert samples.speed_mps == (3.5, None, 0.0)
    assert samples.distance_m == (10.5, None, 0.0)
    assert samples.power_w == (210, None, 0)


def test_a_recognized_name_carrying_an_array_value_is_none_at_that_sample() -> None:
    descriptions = (
        DevFieldSpec("Form Power", _UINT16, 2, array=2),
        DevFieldSpec("Air Power", _UINT16, 11),
    )
    records = [
        ({}, {0: [301, 302], 1: 41}),
        ({}, {0: 303, 1: 42}),
        ({}, {0: [304, 305], 1: 43}),
    ]
    activity = parse_fit(
        developer_field_run_fit_bytes(descriptions=descriptions, records=records)
    )
    values = activity.record_developer_fields["Form Power"].values
    assert isinstance(values[0], tuple)  # the array really reached the policy
    assert activity.samples.form_power_w == (None, 303, None)
    assert activity.samples.air_power_w == (None, 42, None)  # gated on form power


def test_recognized_names_fill_their_channels_from_a_minimal_file() -> None:
    names = list(_NAME_BY_CHANNEL.values())
    descriptions = tuple(
        DevFieldSpec(name, _UINT16, 30 + i) for i, name in enumerate(names)
    )
    # Vertical Oscillation Balance is gated on native oscillation: records carry it
    records = [
        ({"vertical_oscillation": 80.0 + s}, {i: 10 * (i + 1) + s for i in range(7)})
        for s in range(3)
    ]
    samples = parse_fit(
        developer_field_run_fit_bytes(descriptions=descriptions, records=records)
    ).samples
    for i, channel in enumerate(_NAME_BY_CHANNEL):
        assert getattr(samples, channel) == tuple(10 * (i + 1) + s for s in range(3))


def _cycling_file_with_dynamics() -> bytes:
    """A cycling file whose records carry native dynamics and Stryd-named fields."""
    descriptions = (
        DevFieldSpec("Form Power", _UINT16, 2),
        DevFieldSpec("Air Power", _UINT16, 11),
    )
    body = [
        builder._device_info(1301, "SyntheticRideComputer"),
        {"mesg_num": builder._MESG_SPORT, "sport": "cycling", "sub_sport": "generic"},
    ]
    for i in range(3):
        body.append(
            {
                "mesg_num": builder._MESG_RECORD,
                "timestamp": builder.FIT_TIMESTAMP_BASE + i,
                "stance_time": (0.0, 251.0, 252.0)[i],
                "stance_time_balance": (49.5, 50.5, 51.5)[i],
                "developer_fields": {0: (0, 311, 312)[i], 1: (41, 42, 0)[i]},
            }
        )
    body.append(
        {
            "mesg_num": builder._MESG_SESSION,
            "start_time": builder.FIT_TIMESTAMP_BASE,
            "timestamp": builder.FIT_TIMESTAMP_BASE + 2,
            "sport": "cycling",
            "sub_sport": "generic",
            "total_elapsed_time": 2.0,
            "total_timer_time": 2.0,
        }
    )
    body.append(builder._activity(2, 2.0))
    return builder._encode_with_developer_descriptions(
        descriptions, builder._file_id(1301), body
    )


def test_a_cycling_file_gets_the_same_channels_the_sport_plays_no_part() -> None:
    activity = parse_fit(_cycling_file_with_dynamics())
    assert activity.modality is Modality.BIKE  # the file really is not a run
    samples = activity.samples
    assert samples.stance_time_ms == (None, 251.0, 252.0)
    assert samples.stance_time_balance_pct == (None, 50.5, 51.5)
    assert samples.form_power_w == (None, 311, 312)
    assert samples.air_power_w == (None, 42, 0)


# --- developer identity and declared scale (4.2, 4.4) ---------------------------


def test_a_channel_from_any_developer_index_or_application_fills() -> None:
    records, developer = _inputs({})
    moved = {
        name: _developer(
            name,
            list(channel.values),
            index=i + 1,
            application_id=f"{i + 1:032x}",
            declared_scale=bool(i % 2),
        )
        for i, (name, channel) in enumerate(developer.items())
    }
    assert {c.developer_data_index for c in moved.values()} == set(range(1, 8))
    assert extract_dynamics(records, moved) == _run({})


def test_recognized_names_at_mixed_developer_indices_fill_in_a_whole_file() -> None:
    descriptions = (
        DevFieldSpec("Form Power", _UINT16, 2, developer_data_index=1),
        DevFieldSpec("Air Power", _UINT16, 11, developer_data_index=0),
        DevFieldSpec("Impact", _FLOAT32, 4, developer_data_index=2),
    )
    records = [({}, {0: 300 + s, 1: 40 + s, 2: 4.5 + s}) for s in range(3)]
    activity = parse_fit(
        developer_field_run_fit_bytes(descriptions=descriptions, records=records)
    )
    indices = {
        n: c.developer_data_index for n, c in activity.record_developer_fields.items()
    }
    assert indices == {"Form Power": 1, "Air Power": 0, "Impact": 2}
    assert activity.samples.form_power_w == (300, 301, 302)
    assert activity.samples.air_power_w == (40, 41, 42)
    assert activity.samples.impact_bw == (4.5, 5.5, 6.5)


def test_a_recognized_channel_with_a_declared_scale_holds_the_scaled_value() -> None:
    descriptions = (
        DevFieldSpec("Leg Spring Stiffness", _UINT16, 1, scale=100),
        DevFieldSpec("Leg Spring Stiffness Balance", _UINT16, 3, scale=10),
    )
    records = [({}, {0: 912 + 10 * s, 1: 505 + s}) for s in range(3)]
    activity = parse_fit(
        developer_field_run_fit_bytes(descriptions=descriptions, records=records)
    )
    assert all(c.declared_scale for c in activity.record_developer_fields.values())
    assert activity.samples.leg_spring_stiffness_kn_m == pytest.approx(
        (9.12, 9.22, 9.32)
    )
    assert activity.samples.leg_spring_stiffness_balance_pct == pytest.approx(
        (50.5, 50.6, 50.7)
    )
