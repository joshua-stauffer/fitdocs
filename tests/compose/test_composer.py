"""Composing one activity and its channel provenance (channel-merge Req 1.1-1.5,
2.1-2.5, 2.7, 3.10, 5.2, 5.4, 7.1; design.md § Composer).

Every activity is hand-built with values that differ across files and samples,
and expected values are written as literals.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from fitdocs import parse_fit
from fitdocs.compose.alignment import align_extra
from fitdocs.compose.composer import compose_activity
from fitdocs.compose.donation import placed_values
from fitdocs.identity.kinds import SourceKind
from fitdocs.identity.roles import DEFAULT_PRECEDENCE, rank_members, source_member
from fitdocs.metrics import compute_metrics
from fitdocs.metrics.types import AthleteInputs, DerivedMetrics, ZoneSpec
from fitdocs.model import (
    DYNAMICS_CHANNELS,
    Activity,
    DeveloperChannel,
    DeviceInfo,
    Modality,
    Sport,
    StrengthSet,
)
from tests.fixtures import builder, merge

from .builders import make_activity, make_lap, make_summary

_START = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
_TEN = tuple(range(10))

# ---------------------------------------------------------------------------
# Unit section (task 2.4)
# ---------------------------------------------------------------------------


def _device(index: int, manufacturer: str) -> DeviceInfo:
    return DeviceInfo(
        device_index=index,
        manufacturer=manufacturer,
        product_name=f"product-{index}",
        serial_number=9000 + index,
        software_version=None,
        battery_status=None,
    )


class TestNoExtra:
    def test_the_activity_is_the_base_object_itself(self) -> None:
        base = make_activity(
            _START,
            range(6),
            heart_rate_bpm=(101, 102, 103, 104, 105, 106),
            power_w=(None, 201, None, 203, None, None),
            latitude_deg=(1.5, 1.6, 1.7, 1.8, 1.9, 2.0),
            longitude_deg=(7.5, 7.6, 7.7, 7.8, 7.9, 8.0),
            sha256="a" * 64,
            manufacturer="garmin",
        )
        composition = compose_activity(base, ())
        assert composition.activity is base
        assert composition.provenance.extras == ()
        contribution = composition.provenance.base
        assert contribution.sha256 == "a" * 64
        assert contribution.manufacturer == "garmin"
        assert contribution.kind is SourceKind.ORIGINAL
        assert contribution.alignment is None
        assert contribution.channels == (
            "heart_rate_bpm",
            "power_w",
            "latitude_deg",
            "longitude_deg",
        )


class TestBaseWins:
    def _fixture(self) -> tuple[Activity, Activity]:
        base = make_activity(
            _START,
            _TEN,
            heart_rate_bpm=tuple(range(101, 111)),
            speed_mps=(None, 2.5, 2.75, None, 3.0, 3.25, None, 3.5, 3.75, 4.0),
        )
        extra = make_activity(
            _START,
            _TEN,
            heart_rate_bpm=tuple(range(201, 211)),
            speed_mps=tuple(float(v) for v in range(5, 15)),
            power_w=tuple(range(301, 311)),
            cadence_rpm=tuple(float(v) + 0.5 for v in range(60, 70)),
        )
        return base, extra

    def test_a_channel_the_base_records_stays_the_bases(self) -> None:
        base, extra = self._fixture()
        assert all(v is None for v in base.samples.power_w)
        composed = compose_activity(base, [extra]).activity
        assert composed.samples.heart_rate_bpm == tuple(range(101, 111))
        assert composed.samples.power_w == tuple(range(301, 311))

    def test_donated_values_keep_their_decoded_type_and_identity(self) -> None:
        base, extra = self._fixture()
        composed = compose_activity(base, [extra]).activity
        assert [type(v) for v in composed.samples.power_w] == [int] * 10
        assert [type(v) for v in composed.samples.cadence_rpm] == [float] * 10
        assert all(
            got is want
            for got, want in zip(
                composed.samples.cadence_rpm, extra.samples.cadence_rpm, strict=True
            )
        )

    def test_composed_samples_have_the_bases_instants_when_the_extra_differs(
        self,
    ) -> None:
        base = make_activity(
            _START,
            (0, 1, 2, 5, 6, 7),
            heart_rate_bpm=(101, 102, 103, 104, 105, 106),
        )
        extra = make_activity(
            _START,
            range(20),
            cadence_rpm=tuple(float(v) for v in range(60, 80)),
        )
        assert len(extra.samples.time_s) != len(base.samples.time_s)
        composed = compose_activity(base, [extra]).activity
        assert composed.samples.time_s == (0.0, 1.0, 2.0, 5.0, 6.0, 7.0)
        assert composed.samples.cadence_rpm == (60.0, 61.0, 62.0, 65.0, 66.0, 67.0)

    def test_base_provenance_lists_what_the_base_records_in_field_order(
        self,
    ) -> None:
        base, extra = self._fixture()
        provenance = compose_activity(base, [extra]).provenance
        assert provenance.base.channels == ("heart_rate_bpm", "speed_mps")
        assert provenance.base.alignment is None
        assert provenance.extras[0].channels == ("power_w", "cadence_rpm")


class TestPartialCoverage:
    @pytest.mark.parametrize(
        "recorded",
        [
            (101, None, 103, 104, None, 106, None, 108, 109, None),
            (None, None, None, None, None, 175, None, None, None, None),
        ],
        ids=["six-of-ten", "one-of-ten"],
    )
    def test_the_base_keeps_its_gaps_while_an_extra_records_every_sample(
        self, recorded: tuple[int | None, ...]
    ) -> None:
        base = make_activity(_START, _TEN, heart_rate_bpm=recorded)
        extra = make_activity(
            _START,
            _TEN,
            heart_rate_bpm=tuple(range(201, 211)),
            power_w=tuple(range(301, 311)),
        )
        assert None in base.samples.heart_rate_bpm
        assert any(v is not None for v in base.samples.heart_rate_bpm)
        assert None not in extra.samples.heart_rate_bpm
        composed = compose_activity(base, [extra]).activity
        assert composed.samples.heart_rate_bpm == recorded
        assert composed.samples.power_w == tuple(range(301, 311))


class TestRank:
    def _extras(self) -> tuple[Activity, Activity]:
        first = make_activity(
            _START, _TEN, power_w=tuple(range(301, 311)), sha256="1" * 64
        )
        second = make_activity(
            _START, _TEN, power_w=tuple(range(401, 411)), sha256="2" * 64
        )
        return first, second

    def test_the_higher_ranked_extra_donates_the_channel(self) -> None:
        base = make_activity(_START, _TEN, heart_rate_bpm=tuple(range(101, 111)))
        first, second = self._extras()
        composition = compose_activity(base, [first, second])
        assert composition.activity.samples.power_w == tuple(range(301, 311))
        assert [c.channels for c in composition.provenance.extras] == [
            ("power_w",),
            (),
        ]
        assert [c.sha256 for c in composition.provenance.extras] == [
            "1" * 64,
            "2" * 64,
        ]

    def test_swapping_the_ranks_swaps_the_donor(self) -> None:
        base = make_activity(_START, _TEN, heart_rate_bpm=tuple(range(101, 111)))
        first, second = self._extras()
        composition = compose_activity(base, [second, first])
        assert composition.activity.samples.power_w == tuple(range(401, 411))
        assert [c.sha256 for c in composition.provenance.extras] == [
            "2" * 64,
            "1" * 64,
        ]
        assert [c.channels for c in composition.provenance.extras] == [
            ("power_w",),
            (),
        ]


class TestAgainstTheBaseAlone:
    def test_a_later_extra_is_not_aligned_against_an_earlier_donation(self) -> None:
        base = make_activity(_START, range(12), heart_rate_bpm=tuple(range(101, 113)))

        def dist(t: int) -> float:
            return 1000.0 + 3.25 * t

        first = make_activity(
            _START,
            range(12),
            distance_m=tuple(dist(t) for t in range(12)),
            sha256="1" * 64,
        )
        second = make_activity(
            _START,
            range(12),
            distance_m=tuple(dist(t + 1) for t in range(12)),
            cadence_rpm=tuple(float(v) for v in range(60, 72)),
            sha256="2" * 64,
        )
        composition = compose_activity(base, [first, second])
        assert composition.provenance.extras[0].channels == ("distance_m",)
        alignment = composition.provenance.extras[1].alignment
        assert alignment is not None
        assert [(s.lag_s, s.key) for s in alignment.stretches] == [(0, None)]
        assert composition.activity.samples.cadence_rpm == (
            60.0,
            61.0,
            62.0,
            63.0,
            64.0,
            65.0,
            66.0,
            67.0,
            68.0,
            69.0,
            70.0,
            71.0,
        )


class TestNoMixingOfOneChannel:
    def test_a_lower_ranked_extra_never_fills_the_donors_gaps(self) -> None:
        base = make_activity(_START, _TEN, heart_rate_bpm=tuple(range(101, 111)))
        first = make_activity(_START, range(4, 10), power_w=tuple(range(305, 311)))
        second = make_activity(_START, _TEN, power_w=tuple(range(401, 411)))
        composition = compose_activity(base, [first, second])
        assert composition.activity.samples.power_w == (
            None,
            None,
            None,
            None,
            305,
            306,
            307,
            308,
            309,
            310,
        )
        assert [c.channels for c in composition.provenance.extras] == [
            ("power_w",),
            (),
        ]


class TestSkippedExtras:
    def _base(self) -> Activity:
        return make_activity(_START, _TEN, heart_rate_bpm=tuple(range(101, 111)))

    def test_an_extra_whose_values_land_on_no_base_instant_is_skipped(self) -> None:
        base = self._base()
        far = make_activity(
            _START,
            range(100, 110),
            power_w=tuple(range(701, 711)),
            sha256="1" * 64,
        )
        near = make_activity(
            _START, _TEN, power_w=tuple(range(801, 811)), sha256="2" * 64
        )
        placement = align_extra(base, far)
        assert placement.extra_index == (None,) * 10
        assert placed_values(far.samples.power_w, placement) == (None,) * 10
        composition = compose_activity(base, [far, near])
        assert composition.activity.samples.power_w == tuple(range(801, 811))
        skipped, donor = composition.provenance.extras
        assert (skipped.channels, skipped.alignment) == ((), None)
        assert donor.channels == ("power_w",)
        assert donor.alignment is not None

    def test_the_skipped_extras_values_alone_leave_the_channel_absent(self) -> None:
        base = self._base()
        far = make_activity(_START, range(100, 110), power_w=tuple(range(701, 711)))
        composition = compose_activity(base, [far])
        assert composition.activity.samples.power_w == (None,) * 10
        assert composition.provenance.extras[0].channels == ()
        assert composition.provenance.extras[0].alignment is None

    def test_an_extra_recording_only_channels_the_base_keeps_has_no_alignment(
        self,
    ) -> None:
        base = self._base()
        extra = make_activity(_START, _TEN, heart_rate_bpm=tuple(range(201, 211)))
        composition = compose_activity(base, [extra])
        contribution = composition.provenance.extras[0]
        assert contribution.channels == ()
        assert contribution.alignment is None
        samples = composition.activity.samples
        assert samples.heart_rate_bpm == tuple(range(101, 111))
        for field in dataclasses.fields(samples):
            if field.name not in ("time_s", "heart_rate_bpm"):
                assert getattr(samples, field.name) == (None,) * 10, field.name


class TestPosition:
    def test_position_comes_whole_from_the_extra_recording_both(self) -> None:
        base = make_activity(_START, _TEN, heart_rate_bpm=tuple(range(101, 111)))
        lat_only = make_activity(
            _START,
            _TEN,
            latitude_deg=tuple(10.0 + v / 4 for v in range(10)),
        )
        both = make_activity(
            _START,
            _TEN,
            latitude_deg=tuple(20.0 + v / 4 for v in range(10)),
            longitude_deg=tuple(30.0 + v / 4 for v in range(10)),
        )
        composition = compose_activity(base, [lat_only, both])
        samples = composition.activity.samples
        assert samples.latitude_deg == (
            20.0,
            20.25,
            20.5,
            20.75,
            21.0,
            21.25,
            21.5,
            21.75,
            22.0,
            22.25,
        )
        assert samples.longitude_deg == (
            30.0,
            30.25,
            30.5,
            30.75,
            31.0,
            31.25,
            31.5,
            31.75,
            32.0,
            32.25,
        )
        first, second = composition.provenance.extras
        assert first.channels == ()
        assert second.channels == ("latitude_deg", "longitude_deg")

    def test_a_base_recording_one_coordinate_keeps_the_whole_position_unit(
        self,
    ) -> None:
        base = make_activity(
            _START, _TEN, latitude_deg=tuple(1.0 + v / 4 for v in range(10))
        )
        extra = make_activity(
            _START,
            _TEN,
            latitude_deg=tuple(20.0 + v / 4 for v in range(10)),
            longitude_deg=tuple(30.0 + v / 4 for v in range(10)),
        )
        composed = compose_activity(base, [extra]).activity
        assert composed.samples.latitude_deg == (
            1.0,
            1.25,
            1.5,
            1.75,
            2.0,
            2.25,
            2.5,
            2.75,
            3.0,
            3.25,
        )
        assert composed.samples.longitude_deg == (None,) * 10


class TestBalanceChannel:
    def test_a_donated_balance_keeps_its_value_where_stance_time_is_none(
        self,
    ) -> None:
        base = make_activity(
            _START,
            _TEN,
            stance_time_ms=(
                210.0,
                None,
                212.0,
                213.0,
                None,
                215.0,
                216.0,
                217.0,
                218.0,
                219.0,
            ),
        )
        extra = make_activity(
            _START,
            _TEN,
            stance_time_ms=tuple(250.0 + v for v in range(10)),
            stance_time_balance_pct=tuple(50.0 + v / 4 for v in range(10)),
        )
        assert base.samples.stance_time_ms[1] is None
        assert base.samples.stance_time_ms[4] is None
        composed = compose_activity(base, [extra]).activity
        assert composed.samples.stance_time_ms == (
            210.0,
            None,
            212.0,
            213.0,
            None,
            215.0,
            216.0,
            217.0,
            218.0,
            219.0,
        )
        assert composed.samples.stance_time_balance_pct == (
            50.0,
            50.25,
            50.5,
            50.75,
            51.0,
            51.25,
            51.5,
            51.75,
            52.0,
            52.25,
        )


class TestAlignmentIsApplied:
    def test_each_stretch_is_placed_at_its_own_lag(self) -> None:
        def dist(t: int) -> float:
            return 1000.0 + 3.25 * t

        base = make_activity(_START, range(20), distance_m=tuple(map(dist, range(20))))
        extra_offsets = (*range(0, 8), *range(12, 20))
        extra_distance = (
            *(dist(t + 1) for t in range(0, 8)),
            *(dist(t) for t in range(12, 20)),
        )
        extra = make_activity(
            _START,
            extra_offsets,
            distance_m=extra_distance,
            cadence_rpm=tuple(float(v) for v in range(60, 76)),
        )
        composition = compose_activity(base, [extra])
        alignment = composition.provenance.extras[0].alignment
        assert alignment is not None
        assert [(s.lag_s, s.key) for s in alignment.stretches] == [
            (1, "distance_m"),
            (0, "distance_m"),
        ]
        assert composition.activity.samples.cadence_rpm == (
            None,
            60.0,
            61.0,
            62.0,
            63.0,
            64.0,
            65.0,
            66.0,
            67.0,
            None,
            None,
            None,
            68.0,
            69.0,
            70.0,
            71.0,
            72.0,
            73.0,
            74.0,
            75.0,
        )
        assert composition.activity.samples.distance_m == (
            1000.0,
            1003.25,
            1006.5,
            1009.75,
            1013.0,
            1016.25,
            1019.5,
            1022.75,
            1026.0,
            1029.25,
            1032.5,
            1035.75,
            1039.0,
            1042.25,
            1045.5,
            1048.75,
            1052.0,
            1055.25,
            1058.5,
            1061.75,
        )
        assert composition.provenance.extras[0].channels == ("cadence_rpm",)


class TestSessionValueWins:
    def test_the_bases_recorded_session_average_beats_the_donated_samples_mean(
        self,
    ) -> None:
        """Req 5.2. The base records a session average heart rate of 150 and no
        heart-rate sample; the extra donates ten samples averaging 205.5. The
        page's average is the base's 150. Mutations: compute the average from
        the samples before the session value in ``avg_heart_rate_bpm``; blank
        the base's session average in ``compose_activity``."""
        base = make_activity(
            _START,
            _TEN,
            summary=make_summary(start_time=_START, avg_heart_rate_bpm=150),
        )
        extra = make_activity(_START, _TEN, heart_rate_bpm=tuple(range(201, 211)))
        composed = compose_activity(base, [extra]).activity
        assert composed.samples.heart_rate_bpm == tuple(range(201, 211))
        assert compute_metrics(base).avg_heart_rate_bpm == 150
        assert compute_metrics(composed).avg_heart_rate_bpm == 150


class TestBaseOwnedFields:
    def _pair(self) -> tuple[Activity, Activity]:
        base = make_activity(
            _START,
            _TEN,
            heart_rate_bpm=tuple(range(101, 111)),
            laps=(
                make_lap(total_distance_m=1000.5, avg_heart_rate_bpm=151),
                make_lap(total_distance_m=1001.5, avg_heart_rate_bpm=152),
            ),
            summary=make_summary(
                start_time=_START, avg_heart_rate_bpm=150, avg_power_w=None
            ),
            devices=(_device(0, "garmin"),),
            developer_fields={"BASE FIELD": 11},
            sha256="b" * 64,
            manufacturer="garmin",
        )
        base = dataclasses.replace(
            base,
            record_developer_fields={
                "base_rd": DeveloperChannel(
                    name="base_rd",
                    units=None,
                    developer_data_index=0,
                    field_definition_number=1,
                    application_id=None,
                    declared_scale=False,
                    values=tuple(range(500, 510)),
                )
            },
            developer_fields_declared_scale=frozenset({"BASE FIELD"}),
            sets=(StrengthSet("active", _START, 30.5, 8, 60.5, "squat", "SQUAT", 1),),
        )
        extra = make_activity(
            _START + timedelta(seconds=3),
            _TEN,
            power_w=tuple(range(301, 311)),
            laps=(
                make_lap(total_distance_m=2000.5, avg_heart_rate_bpm=161),
                make_lap(total_distance_m=2001.5, avg_heart_rate_bpm=162),
                make_lap(total_distance_m=2002.5, avg_heart_rate_bpm=163),
            ),
            summary=make_summary(
                start_time=_START + timedelta(seconds=3),
                avg_heart_rate_bpm=160,
                avg_power_w=333,
            ),
            devices=(_device(5, "stryd"),),
            developer_fields={"EXTRA FIELD": 22},
            sha256="c" * 64,
            manufacturer="stryd",
            sport=Sport.RIDE,
            modality=Modality.BIKE,
        )
        extra = dataclasses.replace(
            extra,
            is_indoor=True,
            record_developer_fields={
                "extra_rd": DeveloperChannel(
                    name="extra_rd",
                    units="w",
                    developer_data_index=1,
                    field_definition_number=2,
                    application_id="x",
                    declared_scale=True,
                    values=tuple(range(600, 610)),
                )
            },
            developer_fields_declared_scale=frozenset({"EXTRA FIELD"}),
            sets=(StrengthSet("active", _START, 45.5, 12, 80.5, "lunge", "LUNGE", 2),),
        )
        return base, extra

    @pytest.mark.parametrize(
        "name",
        [
            "laps",
            "summary",
            "record_developer_fields",
            "developer_fields",
            "developer_fields_declared_scale",
            "devices",
            "sets",
            "sport",
            "modality",
            "is_indoor",
            "start_time",
            "provenance",
            "file_identity",
        ],
    )
    def test_the_field_is_the_bases_object(self, name: str) -> None:
        base, extra = self._pair()
        assert getattr(extra, name) != getattr(base, name)
        composed = compose_activity(base, [extra]).activity
        assert composed.samples.power_w == (
            None,
            None,
            None,
            301,
            302,
            303,
            304,
            305,
            306,
            307,
        )
        assert getattr(composed, name) is getattr(base, name)


class TestContributions:
    def test_each_contribution_carries_its_own_files_devices(self) -> None:
        d_base = (_device(0, "garmin"),)
        d_quiet = (_device(1, "hrm"), _device(2, "hrm"))
        d_donor = (_device(3, "stryd"),)
        base = make_activity(
            _START,
            _TEN,
            heart_rate_bpm=tuple(range(101, 111)),
            devices=d_base,
        )
        quiet = make_activity(
            _START, _TEN, heart_rate_bpm=tuple(range(201, 211)), devices=d_quiet
        )
        donor = make_activity(
            _START, _TEN, power_w=tuple(range(301, 311)), devices=d_donor
        )
        composition = compose_activity(base, [quiet, donor])
        provenance = composition.provenance
        assert provenance.base.devices == (_device(0, "garmin"),)
        assert provenance.extras[0].devices == (
            _device(1, "hrm"),
            _device(2, "hrm"),
        )
        assert provenance.extras[1].devices == (_device(3, "stryd"),)
        assert provenance.extras[0].channels == ()
        assert provenance.extras[1].channels == ("power_w",)
        assert composition.activity.devices == (_device(0, "garmin"),)

    def test_each_contribution_carries_its_own_hash_kind_and_manufacturer(
        self,
    ) -> None:
        phone_copy = make_activity(
            _START,
            _TEN,
            heart_rate_bpm=tuple(range(101, 111)),
            sha256="a" * 64,
            manufacturer="development",
            developer_fields={"SESSION UUID": tuple(range(16))},
        )
        unknown = make_activity(
            _START, _TEN, power_w=tuple(range(301, 311)), sha256="b" * 64
        )
        original = make_activity(
            _START,
            _TEN,
            cadence_rpm=tuple(float(v) for v in range(60, 70)),
            sha256="c" * 64,
            manufacturer="stryd",
        )
        provenance = compose_activity(phone_copy, [unknown, original]).provenance
        got = [
            (c.sha256, c.kind, c.manufacturer)
            for c in (provenance.base, *provenance.extras)
        ]
        assert got == [
            ("a" * 64, SourceKind.PHONE_COPY, "development"),
            ("b" * 64, SourceKind.UNKNOWN, None),
            ("c" * 64, SourceKind.ORIGINAL, "stryd"),
        ]


class TestDeterminism:
    def test_the_same_inputs_compose_to_equal_results_twice(self) -> None:
        base = make_activity(_START, _TEN, heart_rate_bpm=tuple(range(101, 111)))
        extra = make_activity(_START, _TEN, power_w=tuple(range(301, 311)))
        first = compose_activity(base, [extra])
        second = compose_activity(base, [extra])
        assert first.activity.samples.power_w == tuple(range(301, 311))
        assert first == second


# ---------------------------------------------------------------------------
# Measured-pair section (task 2.5)
#
# The run pair, run trio and ride pair of ``tests/fixtures/merge.py``, parsed
# from bytes and composed (channel-merge Req 2.1, 2.2, 3.3, 3.5, 3.6, 3.8, 5.1,
# 5.3, 9.1, 9.2; design.md § Testing Strategy M1-M6). Expected values are
# literals, or are read from the raw decoded Stryd messages (never from the
# composer, the alignment or the donation modules).
# ---------------------------------------------------------------------------

_RUN_STRYD_LAGS = (1, 1, 0, 1, 0)  # the HealthFit copy's lag per stretch
_RUN_STRETCH_STRIDE_S = 16  # stretch k's samples sit at offsets 16k..16k+11
_RUN_STRETCH_LEN = 12
_RUN_BASE_SAMPLES = 63  # five stretches of twelve, then three trailing instants
_RUN_PLACED_FIRST_LAST = (
    # (first placed base index, last placed base index) per stretch; stretch 0
    # at lag +1 loses its last sample (base offset 12 does not exist).
    (1, 11),
    (13, 23),
    (24, 35),
    (37, 47),
    (48, 59),
)
_RUN_TRAILING = (60, 61, 62)

# donated channel -> (raw record key, developer-field position or None); the
# position is the description order of the Stryd file's developer table
# (Air Power 0, Form Power 1, Leg Spring Stiffness 2, Impact 3, Leg Spring
# Stiffness Balance 4, Impact Loading Rate Balance 5, Vertical Oscillation
# Balance 6).
_RUN_DONATED: dict[str, tuple[str, int | None]] = {
    "stance_time_balance_pct": ("stance_time_balance", None),
    "vertical_oscillation_balance_pct": ("", 6),
    "leg_spring_stiffness_kn_m": ("", 2),
    "leg_spring_stiffness_balance_pct": ("", 4),
    "form_power_w": ("", 1),
    "air_power_w": ("", 0),
    "impact_bw": ("", 3),
    "impact_loading_rate_balance_pct": ("", 5),
}

_HR_FED_FIELDS = (
    "avg_heart_rate_bpm",  # aggregates.py:203 reads samples.heart_rate_bpm
    "max_heart_rate_bpm",  # aggregates.py:212
    "efficiency_factor",  # power.py:285 divides by the average heart rate
    "decoupling_pct",  # power.py:358 pairs output with heart rate per half
    "hr_time_in_zone_s",  # metrics/__init__.py: zones of samples.heart_rate_bpm
    "trimp",  # stress.py:158 reads samples.heart_rate_bpm
    "trimp_weighting",  # set together with trimp (metrics/__init__.py)
)

_ATHLETE = AthleteInputs(
    ftp_watts=250.0,
    resting_hr_bpm=50,
    max_hr_bpm=190,
    hr_zones=ZoneSpec((110.0, 140.0, 170.0)),
    power_zones=ZoneSpec((150.0, 200.0, 250.0)),
    pace_zones=ZoneSpec((330.0, 400.0)),
)


def _raw_stryd(data: bytes, channel: str) -> dict[int, object]:
    """The Stryd file's raw decoded value of ``channel`` by second offset."""
    key, position = _RUN_DONATED[channel]
    messages, errors = builder.decode_messages(data)
    assert errors == []
    out: dict[int, object] = {}
    records: list[dict[str, Any]] = messages["record_mesgs"]
    for record in records:
        offset = record["timestamp"] - merge.RUN_START
        out[offset] = (
            record[key] if position is None else record["developer_fields"][position]
        )
    return out


def _expected_run_series(
    raw: dict[int, object], base_offsets: tuple[float, ...]
) -> tuple[object | None, ...]:
    """Per base sample: the Stryd value at the instant minus the stretch's lag.

    Stretch ``k`` places Stryd offsets ``16k..16k+11`` on base offsets plus its
    lag; a base offset no placed Stryd sample reaches is ``None``.
    """
    series: list[object | None] = []
    for t in base_offsets:
        value: object | None = None
        for k, lag in enumerate(_RUN_STRYD_LAGS):
            start = k * _RUN_STRETCH_STRIDE_S
            source = int(t) - lag
            if start <= source < start + _RUN_STRETCH_LEN:
                value = raw[source]
        series.append(value)
    return tuple(series)


def _fields_differing(
    a: DerivedMetrics, b: DerivedMetrics, names: tuple[str, ...] = ()
) -> set[str]:
    fields = {f.name for f in dataclasses.fields(DerivedMetrics)} - set(names)
    return {n for n in sorted(fields) if getattr(a, n) != getattr(b, n)}


class TestRunPair:
    @pytest.fixture
    def pair(self) -> tuple[Activity, Activity, bytes]:
        healthfit, stryd = merge.run_pair_fit_bytes()
        return parse_fit(healthfit), parse_fit(stryd), stryd

    def test_the_ranking_premise_healthfit_base_and_stryd_extra(
        self, pair: tuple[Activity, Activity, bytes]
    ) -> None:
        base, extra, _ = pair
        members = [
            source_member("hf", base.provenance.sha256, base),
            source_member("st", extra.provenance.sha256, extra),
        ]
        for ordered in (members, members[::-1]):
            roles = rank_members(ordered, (), DEFAULT_PRECEDENCE)
            assert roles.base.ref == "hf"
            assert [m.ref for m in roles.extras] == ["st"]

    def test_the_fixture_shape_the_assertions_stand_on(
        self, pair: tuple[Activity, Activity, bytes]
    ) -> None:
        base, extra, _ = pair
        assert len(base.samples.time_s) == _RUN_BASE_SAMPLES
        assert len(extra.samples.time_s) == 60
        assert [lap.total_distance_m for lap in base.laps] == [
            50.0,
            57.25,
            64.5,
            71.75,
            79.0,
        ]
        assert len(extra.laps) == 4
        # The base records none of the donated channels; the extra records all.
        for channel in _RUN_DONATED:
            assert not any(v is not None for v in getattr(base.samples, channel))
            assert all(v is not None for v in getattr(extra.samples, channel))

    def test_form_power_at_each_stretchs_first_and_last_placed_sample(
        self, pair: tuple[Activity, Activity, bytes]
    ) -> None:
        base, extra, stryd = pair
        form_power = compose_activity(base, [extra]).activity.samples.form_power_w
        raw = _raw_stryd(stryd, "form_power_w")
        # Hand-written per stretch: (first, last placed base index) and the
        # Stryd instants (offsets) they carry: instant minus the stretch's lag.
        cases = [
            ((1, 11), (0, 10)),  # lag +1
            ((13, 23), (16, 26)),  # lag +1 (base index 13 is offset 17)
            ((24, 35), (32, 43)),  # lag 0
            ((37, 47), (48, 58)),  # lag +1 (base index 37 is offset 49)
            ((48, 59), (64, 75)),  # lag 0
        ]
        assert tuple(c[0] for c in cases) == _RUN_PLACED_FIRST_LAST
        for (first, last), (first_source, last_source) in cases:
            assert form_power[first] == raw[first_source]
            assert form_power[last] == raw[last_source]
        # Literal anchors, independent of the raw table: Stryd form power is
        # 50 + 2 * ((5 g) % 13) at Stryd sample g (offsets 0, 10, 32, 43 are
        # g = 0, 10, 24, 35).
        assert (form_power[1], form_power[11]) == (50, 72)
        assert (form_power[24], form_power[35]) == (56, 62)

    def test_the_whole_composed_series_is_the_stryd_series_at_each_lag(
        self, pair: tuple[Activity, Activity, bytes]
    ) -> None:
        base, extra, stryd = pair
        composed = compose_activity(base, [extra]).activity.samples
        for channel in _RUN_DONATED:
            expected = _expected_run_series(
                _raw_stryd(stryd, channel), base.samples.time_s
            )
            assert getattr(composed, channel) == expected, channel
        assert sum(v is not None for v in composed.form_power_w) == 57

    def test_every_stretch_is_aligned_by_distance_at_its_own_lag(
        self, pair: tuple[Activity, Activity, bytes]
    ) -> None:
        base, extra, _ = pair
        alignment = compose_activity(base, [extra]).provenance.extras[0].alignment
        assert alignment is not None
        assert alignment.hour_shift_s == 0
        assert [(s.start, s.stop) for s in alignment.stretches] == [
            (0, 12),
            (12, 24),
            (24, 36),
            (36, 48),
            (48, 60),
        ]
        assert [s.key for s in alignment.stretches] == ["distance_m"] * 5
        assert [s.lag_s for s in alignment.stretches] == [1, 1, 0, 1, 0]

    def test_the_three_trailing_base_samples_hold_none_in_every_donated_channel(
        self, pair: tuple[Activity, Activity, bytes]
    ) -> None:
        base, extra, _ = pair
        composed = compose_activity(base, [extra]).activity.samples
        # Precondition: the base does record something at those instants.
        assert all(base.samples.heart_rate_bpm[i] is not None for i in _RUN_TRAILING)
        for channel in _RUN_DONATED:
            for i in _RUN_TRAILING:
                assert getattr(composed, channel)[i] is None, (channel, i)

    def test_step_length_and_cadence_are_the_healthfit_values(
        self, pair: tuple[Activity, Activity, bytes]
    ) -> None:
        base, extra, _ = pair
        composed = compose_activity(base, [extra]).activity.samples
        # Precondition: the Stryd file's values differ at every sample.
        assert all(
            a != b
            for a, b in zip(
                extra.samples.step_length_mm, base.samples.step_length_mm, strict=False
            )
        )
        assert composed.step_length_mm == base.samples.step_length_mm
        assert composed.cadence_rpm == base.samples.cadence_rpm
        assert composed.step_length_mm[:3] == (892.9, 926.1, 959.3)
        assert composed.cadence_rpm[:3] == (141, 167, 145)

    def test_the_laps_are_the_healthfit_laps(
        self, pair: tuple[Activity, Activity, bytes]
    ) -> None:
        base, extra, _ = pair
        laps = compose_activity(base, [extra]).activity.laps
        assert len(laps) == 5
        assert laps == base.laps
        assert laps != extra.laps

    def test_every_donated_channel_is_a_running_dynamics_channel(
        self, pair: tuple[Activity, Activity, bytes]
    ) -> None:
        base, extra, _ = pair
        composition = compose_activity(base, [extra])
        changed = {
            f.name
            for f in dataclasses.fields(base.samples)
            if getattr(composition.activity.samples, f.name)
            != getattr(base.samples, f.name)
        }
        assert changed == set(_RUN_DONATED)
        assert changed <= set(DYNAMICS_CHANNELS)
        assert set(composition.provenance.extras[0].channels) == changed
        assert composition.activity.samples.time_s == base.samples.time_s

    def test_the_metrics_of_the_composition_equal_those_of_the_base_alone(
        self, pair: tuple[Activity, Activity, bytes]
    ) -> None:
        base, extra, _ = pair
        composition = compose_activity(base, [extra])
        for athlete in (None, _ATHLETE):
            alone = compute_metrics(base, athlete)
            composed = compute_metrics(composition.activity, athlete)
            assert composed == alone
        # The comparison is non-trivial: the athlete's fields are all computed.
        full = compute_metrics(composition.activity, _ATHLETE)
        assert full.avg_heart_rate_bpm is not None
        assert full.trimp is not None
        assert full.hr_time_in_zone_s is not None
        assert full.power_time_in_zone_s is not None
        assert full.decoupling_pct is not None


class TestRunTrio:
    def test_the_highest_ranked_extra_donates_and_the_other_supplies_nothing(
        self,
    ) -> None:
        healthfit, stryd_a, stryd_b = merge.run_trio_fit_bytes()
        base, a, b = parse_fit(healthfit), parse_fit(stryd_a), parse_fit(stryd_b)
        members = [
            source_member(name, act.provenance.sha256, act)
            for name, act in (("a", a), ("b", b), ("hf", base))
        ]
        roles = rank_members(members, (), DEFAULT_PRECEDENCE)
        assert roles.base.ref == "hf"
        assert [m.ref for m in roles.extras] == ["b", "a"]

        composition = compose_activity(base, [b, a])
        form_power = composition.activity.samples.form_power_w
        assert form_power == _expected_run_series(
            _raw_stryd(stryd_b, "form_power_w"), base.samples.time_s
        )
        assert (form_power[1], form_power[24]) == (51, 57)
        # stryd_a's form power is one watt lower at every sample.
        assert _raw_stryd(stryd_a, "form_power_w")[0] == 50
        extra_b, extra_a = composition.provenance.extras
        assert extra_b.sha256 == b.provenance.sha256
        assert set(DYNAMICS_CHANNELS) >= set(extra_b.channels) >= {"form_power_w"}
        assert extra_a.sha256 == a.provenance.sha256
        assert extra_a.channels == ()
        assert extra_a.alignment is None


def _ride(
    *, copy_power: bool = True, copy_shift_h: int = 0
) -> tuple[Activity, Activity]:
    garmin, healthfit = merge.ride_pair_fit_bytes(
        copy_power=copy_power, copy_shift_h=copy_shift_h
    )
    return parse_fit(garmin), parse_fit(healthfit)


# The copy's heart rate: 90 + 3 * (g % 34) in each of three stretches of 34.
_RIDE_HEART_RATE = tuple(90 + 3 * i for i in range(34)) * 3


class TestRidePair:
    def test_the_ranking_premise_garmin_base_and_healthfit_extra(self) -> None:
        base, extra = _ride()
        members = [
            source_member("g", base.provenance.sha256, base),
            source_member("h", extra.provenance.sha256, extra),
        ]
        for ordered in (members, members[::-1]):
            roles = rank_members(ordered, (), DEFAULT_PRECEDENCE)
            assert roles.base.ref == "g"
            assert [m.ref for m in roles.extras] == ["h"]

    def test_heart_rate_is_donated_with_every_stretch_aligned_by_power_at_lag_0(
        self,
    ) -> None:
        base, extra = _ride()
        assert not any(v is not None for v in base.samples.heart_rate_bpm)
        composition = compose_activity(base, [extra])
        assert composition.activity.samples.heart_rate_bpm == _RIDE_HEART_RATE
        contribution = composition.provenance.extras[0]
        assert contribution.channels == ("heart_rate_bpm",)
        alignment = contribution.alignment
        assert alignment is not None
        assert alignment.hour_shift_s == 0
        assert [(s.start, s.stop, s.lag_s, s.key) for s in alignment.stretches] == [
            (0, 34, 0, "power_w"),
            (34, 68, 0, "power_w"),
            (68, 102, 0, "power_w"),
        ]

    def test_the_average_heart_rate_is_the_mean_of_the_donated_values(self) -> None:
        base, extra = _ride()
        composition = compose_activity(base, [extra])
        assert compute_metrics(base).avg_heart_rate_bpm is None
        # Three stretches of 90, 93, .., 189 each average 139.5.
        assert compute_metrics(composition.activity).avg_heart_rate_bpm == 139.5

    def test_every_metric_not_fed_by_heart_rate_equals_the_base_alone(self) -> None:
        base, extra = _ride()
        composed = compose_activity(base, [extra]).activity
        alone_m = compute_metrics(base, _ATHLETE)
        composed_m = compute_metrics(composed, _ATHLETE)
        # The heart-rate-fed fields are exactly the ones that move (each is
        # computed in the composition and absent from the base alone).
        assert _fields_differing(alone_m, composed_m) == set(_HR_FED_FIELDS)
        for name in _HR_FED_FIELDS:
            assert getattr(alone_m, name) is None, name
            assert getattr(composed_m, name) is not None, name
        assert _fields_differing(alone_m, composed_m, _HR_FED_FIELDS) == set()
        # Non-trivial: power, distance and elevation fields are computed.
        for name in ("avg_power_w", "normalized_power_w", "distance_m", "power_tss"):
            assert getattr(alone_m, name) is not None, name

    def test_with_no_copy_power_every_stretch_falls_back(self) -> None:
        base, extra = _ride(copy_power=False)
        assert not any(v is not None for v in extra.samples.power_w)
        composition = compose_activity(base, [extra])
        alignment = composition.provenance.extras[0].alignment
        assert alignment is not None
        assert [(s.start, s.stop, s.lag_s, s.key) for s in alignment.stretches] == [
            (0, 34, 0, None),
            (34, 68, 0, None),
            (68, 102, 0, None),
        ]
        assert composition.activity.samples.heart_rate_bpm == _RIDE_HEART_RATE

    def test_shifted_one_hour_the_shift_is_recorded_and_heart_rate_lands_alike(
        self,
    ) -> None:
        base, extra = _ride(copy_shift_h=1)
        # Precondition: the copy starts an hour after the base.
        assert base.start_time is not None and extra.start_time is not None
        assert (extra.start_time - base.start_time).total_seconds() == 3600
        composition = compose_activity(base, [extra])
        alignment = composition.provenance.extras[0].alignment
        assert alignment is not None
        assert alignment.hour_shift_s == 3600
        assert [(s.lag_s, s.key) for s in alignment.stretches] == [(0, "power_w")] * 3
        plain_base, plain_extra = _ride()
        unshifted = compose_activity(plain_base, [plain_extra])
        assert (
            composition.activity.samples.heart_rate_bpm
            == unshifted.activity.samples.heart_rate_bpm
            == _RIDE_HEART_RATE
        )


class TestPartialCoverageOnTheRunPair:
    def test_a_trimmed_heart_rate_composes_to_exactly_the_trimmed_heart_rate(
        self,
    ) -> None:
        healthfit, stryd = merge.run_pair_fit_bytes()
        full, extra = parse_fit(healthfit), parse_fit(stryd)
        kept = [(5 * i) % 63 < 32 for i in range(63)]
        assert sum(kept) == 32  # 51% of 63 samples, scattered over the run
        trimmed_hr = tuple(
            v if keep else None
            for v, keep in zip(full.samples.heart_rate_bpm, kept, strict=True)
        )
        base = dataclasses.replace(
            full, samples=dataclasses.replace(full.samples, heart_rate_bpm=trimmed_hr)
        )
        # Preconditions: the base has gaps and the extra records every sample.
        assert any(v is None for v in trimmed_hr)
        assert all(v is not None for v in extra.samples.heart_rate_bpm)
        composition = compose_activity(base, [extra])
        assert composition.activity.samples.heart_rate_bpm == trimmed_hr
        assert composition.provenance.extras[0].channels.count("heart_rate_bpm") == 0
        # Gaps stay None where the extra places a value: the placed positions
        # are those at which the untrimmed composition donates form power.
        donated = compose_activity(full, [extra]).activity.samples.form_power_w
        placed_gaps = [
            i for i, keep in enumerate(kept) if not keep and donated[i] is not None
        ]
        assert len(placed_gaps) >= 10
        heart_rate = composition.activity.samples.heart_rate_bpm
        assert all(heart_rate[i] is None for i in placed_gaps)
