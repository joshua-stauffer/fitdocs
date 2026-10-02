"""Composing one activity and its channel provenance (channel-merge Req 1.1-1.5,
2.1-2.5, 2.7, 3.10, 5.2, 5.4, 7.1; design.md § Composer).

Every activity is hand-built with values that differ across files and samples,
and expected values are written as literals.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from fitdocs.compose.alignment import align_extra
from fitdocs.compose.composer import compose_activity
from fitdocs.compose.donation import placed_values
from fitdocs.identity.kinds import SourceKind
from fitdocs.model import (
    Activity,
    DeveloperChannel,
    DeviceInfo,
    Modality,
    Sport,
    StrengthSet,
)

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
