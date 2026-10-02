"""Donation units and the base-wins rule (channel-merge 2.1, 2.2, 2.4, 2.5,
2.6, 2.8; design.md § Donation).

The expected unit list is written out as literals; the model-derived checks
are separate tests.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

from fitdocs.compose.donation import (
    DONATION_UNITS,
    POSITION_UNIT,
    base_keeps,
    placed_values,
    records,
)
from fitdocs.compose.types import ExtraAlignment, Placement
from fitdocs.model import DYNAMICS_CHANNELS, Samples

from .builders import make_activity

_START = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)

_EXPECTED_UNITS: tuple[tuple[str, ...], ...] = (
    ("heart_rate_bpm",),
    ("power_w",),
    ("cadence_rpm",),
    ("speed_mps",),
    ("distance_m",),
    ("altitude_m",),
    ("latitude_deg", "longitude_deg"),
    ("temperature_c",),
    ("stance_time_ms",),
    ("stance_time_balance_pct",),
    ("vertical_oscillation_mm",),
    ("vertical_oscillation_balance_pct",),
    ("vertical_ratio_pct",),
    ("step_length_mm",),
    ("leg_spring_stiffness_kn_m",),
    ("leg_spring_stiffness_balance_pct",),
    ("form_power_w",),
    ("air_power_w",),
    ("impact_bw",),
    ("impact_loading_rate_balance_pct",),
)


def _placement(index: tuple[int | None, ...]) -> Placement:
    return Placement(
        alignment=ExtraAlignment(hour_shift_s=0, stretches=()),
        extra_index=index,
    )


class TestUnits:
    def test_units_are_exactly_the_expected_literal_list(self) -> None:
        assert DONATION_UNITS == _EXPECTED_UNITS

    def test_units_cover_every_channel_but_time_once(self) -> None:
        flat = [name for unit in DONATION_UNITS for name in unit]
        wanted = [f.name for f in dataclasses.fields(Samples) if f.name != "time_s"]
        assert len(wanted) == 21, "the model's channel count changed"
        assert sorted(flat) == sorted(wanted)
        assert "time_s" not in flat

    def test_every_dynamics_channel_is_its_own_unit(self) -> None:
        assert len(DYNAMICS_CHANNELS) == 12
        for name in DYNAMICS_CHANNELS:
            assert (name,) in DONATION_UNITS

    def test_position_is_one_unit_of_two_at_latitudes_place(self) -> None:
        assert POSITION_UNIT == ("latitude_deg", "longitude_deg")
        assert DONATION_UNITS.count(POSITION_UNIT) == 1
        assert ("latitude_deg",) not in DONATION_UNITS
        assert ("longitude_deg",) not in DONATION_UNITS
        assert DONATION_UNITS.index(POSITION_UNIT) == 6


class TestRecords:
    def test_zero_and_false_values_count_as_recorded(self) -> None:
        assert records([None, 0, None]) is True
        assert records([None, 0.0]) is True

    def test_all_none_and_empty_are_not_recorded(self) -> None:
        assert records([None, None, None]) is False
        assert records([]) is False


class TestBaseKeeps:
    def test_channel_recorded_on_51_percent_of_samples_is_kept(self) -> None:
        n = 100
        hr = [150 + i if i < 51 else None for i in range(n)]
        base = make_activity(_START, list(range(n)), heart_rate_bpm=hr).samples
        assert sum(v is not None for v in base.heart_rate_bpm) == 51
        assert base_keeps(("heart_rate_bpm",), base) is True

    def test_channel_recorded_at_a_single_sample_is_kept(self) -> None:
        power: list[int | None] = [None] * 20
        power[13] = 245
        base = make_activity(_START, list(range(20)), power_w=power).samples
        assert base_keeps(("power_w",), base) is True

    def test_channel_recorded_only_as_zero_is_kept(self) -> None:
        base = make_activity(_START, [0, 1, 2], cadence_rpm=[None, 0.0, None]).samples
        assert base_keeps(("cadence_rpm",), base) is True

    def test_unrecorded_channel_is_not_kept(self) -> None:
        base = make_activity(_START, [0, 1, 2], heart_rate_bpm=[140, 141, 142]).samples
        assert base_keeps(("power_w",), base) is False
        assert base_keeps(("form_power_w",), base) is False

    def test_a_recorded_channel_keeps_only_its_own_unit(self) -> None:
        base = make_activity(_START, [0, 1, 2], heart_rate_bpm=[140, 141, 142]).samples
        assert base_keeps(("heart_rate_bpm",), base) is True
        assert base_keeps(("speed_mps",), base) is False

    def test_dynamics_channel_is_judged_by_its_own_array(self) -> None:
        base = make_activity(_START, [0, 1, 2], air_power_w=[None, 12.5, None]).samples
        assert base_keeps(("air_power_w",), base) is True
        assert base_keeps(("form_power_w",), base) is False

    def test_position_kept_when_base_records_latitude_alone(self) -> None:
        base = make_activity(_START, [0, 1], latitude_deg=[51.5, 51.6]).samples
        assert base_keeps(POSITION_UNIT, base) is True

    def test_position_kept_when_base_records_longitude_alone(self) -> None:
        base = make_activity(_START, [0, 1], longitude_deg=[None, -0.1]).samples
        assert base_keeps(POSITION_UNIT, base) is True

    def test_position_open_when_base_records_neither(self) -> None:
        base = make_activity(_START, [0, 1], altitude_m=[10.0, 11.0]).samples
        assert base_keeps(POSITION_UNIT, base) is False


class TestPlacedValues:
    def test_values_follow_a_non_identity_placement(self) -> None:
        extra = (11, 22, 33, 44, 55)
        out = placed_values(extra, _placement((3, None, 0, 4, 1)))
        assert out == (44, None, 11, 55, 22)

    def test_result_has_one_entry_per_base_sample(self) -> None:
        out = placed_values((7, 8, 9, 10, 11, 12), _placement((5, 2, None)))
        assert out == (12, 9, None)
        assert isinstance(out, tuple)

    def test_unplaced_base_samples_are_none_not_zero(self) -> None:
        out = placed_values((11, 22, 33), _placement((None, 2, None)))
        assert out == (None, 33, None)
        assert out[0] is None
        assert out[2] is None

    def test_nothing_placed_leaves_every_sample_none(self) -> None:
        out = placed_values((11, 22), _placement((None, None, None)))
        assert out == (None, None, None)
        assert all(v is None for v in out)

    def test_values_pass_through_exactly_as_decoded(self) -> None:
        extra: tuple[object | None, ...] = (0, None, 0.0, 61.25, 1e-9, 245, 7)
        index = (3, 0, 1, 2, 4, 5, 6)
        out = placed_values(extra, _placement(index))
        assert out == (61.25, 0, None, 0.0, 1e-9, 245, 7)
        assert tuple(type(v) for v in out) == (
            float,
            int,
            type(None),
            float,
            float,
            int,
            int,
        )
        for slot, source in enumerate(index):
            assert out[slot] is extra[source]
