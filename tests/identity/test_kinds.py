"""Tests for the source-kind classification and the base identity (Req 2.1-2.4, 5.4).

Activities come from :func:`fitdocs.ingest.parse_fit` on the synthetic species of
:mod:`tests.fixtures.identity`; variants are made with ``dataclasses.replace`` on
the parsed activity, and each case names the fields it replaces:

* the kind reads the file's own ``file_id`` manufacturer and the session UUID
  developer field -- ``development`` plus a well-formed UUID is a phone copy,
  any other recorded manufacturer is an original, everything else unknown;
* the device list is never consulted: the tests set it themselves, so a
  HealthFit copy given a Garmin device is still a phone copy, and an original
  given a ``development`` device is still an original;
* the digest is ``None`` unless manufacturer, serial and creation time are all
  recorded, is deterministic, and differs when only the creation time differs;
* the base identity carries the recorded elapsed (not the timer), the recorded
  distance, the digest and the activity's own formatted session UUID.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from types import MappingProxyType

import pytest

import fitdocs.contract
from fitdocs.identity import kinds
from fitdocs.identity.kinds import (
    SourceIdentity,
    SourceKind,
    device_digest,
    source_identity,
    source_kind,
)
from fitdocs.ingest import parse_fit
from fitdocs.model import Activity, DeviceInfo, FileIdentity
from tests.fixtures import identity

_CREATED = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)


def _activity(species: identity.Species) -> Activity:
    return parse_fit(species.data)


def _device(manufacturer: str) -> DeviceInfo:
    return DeviceInfo(
        device_index=0,
        manufacturer=manufacturer,
        product_name="TestDevice",
        serial_number=987_654_321,
        software_version=None,
        battery_status=None,
    )


def _with_manufacturer(activity: Activity, manufacturer: str | None) -> Activity:
    return replace(
        activity,
        file_identity=replace(activity.file_identity, manufacturer=manufacturer),
    )


def _with_developer_fields(activity: Activity, fields: dict[str, object]) -> Activity:
    return replace(activity, developer_fields=MappingProxyType(fields))


def test_fixture_precondition_values_are_what_the_cases_assume() -> None:
    garmin = _activity(identity.garmin_original())
    copy = _activity(identity.healthfit_copy())
    assert garmin.file_identity.manufacturer == "garmin"
    assert copy.file_identity.manufacturer == "development"
    assert copy.developer_fields.get(fitdocs.contract.SESSION_UUID_FIELD) is not None
    assert garmin.developer_fields.get(fitdocs.contract.SESSION_UUID_FIELD) is None


class TestSourceKind:
    def test_garmin_file_is_original(self) -> None:
        assert source_kind(_activity(identity.garmin_original())) is SourceKind.ORIGINAL

    def test_partner_copy_is_original(self) -> None:
        assert source_kind(_activity(identity.partner_copy())) is SourceKind.ORIGINAL

    def test_stryd_file_is_original(self) -> None:
        assert source_kind(_activity(identity.stryd_file())) is SourceKind.ORIGINAL

    def test_healthfit_copy_of_a_garmin_ride_is_a_phone_copy(self) -> None:
        # file_id says development (the fixture); the test itself sets the
        # device list to a single Garmin device, whatever the species records.
        copy = replace(
            _activity(identity.healthfit_copy()), devices=(_device("garmin"),)
        )
        assert copy.file_identity.manufacturer == "development"
        assert [d.manufacturer for d in copy.devices] == ["garmin"]
        assert source_kind(copy) is SourceKind.PHONE_COPY

    def test_device_list_is_not_consulted_for_a_phone_copy(self) -> None:
        copy = _activity(identity.healthfit_copy())
        no_devices = replace(copy, devices=())
        stryd_devices = replace(copy, devices=(_device("stryd"),))
        assert source_kind(no_devices) is SourceKind.PHONE_COPY
        assert source_kind(stryd_devices) is SourceKind.PHONE_COPY

    def test_device_list_is_not_consulted_for_an_original(self) -> None:
        garmin = _activity(identity.garmin_original())
        devices = (_device("development"),)
        assert source_kind(replace(garmin, devices=devices)) is SourceKind.ORIGINAL

    def test_development_without_the_marker_is_unknown(self) -> None:
        copy = _activity(identity.healthfit_copy())
        assert source_kind(_with_developer_fields(copy, {})) is SourceKind.UNKNOWN

    @pytest.mark.parametrize(
        "malformed",
        [
            tuple(range(15)),
            list(range(16)),
            tuple(range(255, 271)),
            "not-a-uuid",
            None,
        ],
    )
    def test_development_with_a_malformed_marker_is_unknown(
        self, malformed: object
    ) -> None:
        copy = _activity(identity.healthfit_copy())
        marked = _with_developer_fields(
            copy, {fitdocs.contract.SESSION_UUID_FIELD: malformed}
        )
        assert source_kind(marked) is SourceKind.UNKNOWN

    def test_marker_without_development_is_original(self) -> None:
        garmin = _activity(identity.garmin_original())
        marked = _with_developer_fields(
            garmin,
            {fitdocs.contract.SESSION_UUID_FIELD: tuple(range(200, 216))},
        )
        assert source_kind(marked) is SourceKind.ORIGINAL

    def test_marker_without_a_manufacturer_is_unknown(self) -> None:
        copy = _activity(identity.healthfit_copy())
        assert source_kind(_with_manufacturer(copy, None)) is SourceKind.UNKNOWN

    def test_a_file_with_no_file_id_is_unknown(self) -> None:
        garmin = _activity(identity.garmin_original())
        bare = replace(
            garmin,
            file_identity=FileIdentity(
                manufacturer=None, product=None, serial_number=None, time_created=None
            ),
        )
        assert source_kind(bare) is SourceKind.UNKNOWN

    def test_a_numeric_manufacturer_is_original(self) -> None:
        # The profile names no manufacturer 4242: ingest records the number as text.
        garmin = _activity(identity.garmin_original())
        assert source_kind(_with_manufacturer(garmin, "4242")) is SourceKind.ORIGINAL

    def test_vocabulary_is_closed(self) -> None:
        assert {k.value for k in SourceKind} == {"original", "phone_copy", "unknown"}
        assert kinds.DEVELOPMENT_MANUFACTURER == "development"


class TestDeviceDigest:
    _FULL = FileIdentity(
        manufacturer="garmin",
        product=3843,
        serial_number=3_300_000_001,
        time_created=_CREATED,
    )

    def test_is_sixteen_lowercase_hex_digits(self) -> None:
        digest = device_digest(self._FULL)
        assert digest is not None
        assert len(digest) == 16
        assert set(digest) <= set("0123456789abcdef")

    def test_serialization_is_pinned(self) -> None:
        assert device_digest(self._FULL) == "6e555121cb7bf003"

    def test_does_not_contain_the_serial(self) -> None:
        digest = device_digest(self._FULL)
        assert digest is not None
        serial = self._FULL.serial_number
        assert serial is not None
        assert str(serial) not in digest
        assert f"{serial:x}" not in digest
        assert digest != f"{serial:016x}"
        plain = f"garmin/{serial}/2024-01-02T03:04:05Z"
        assert digest != plain[:16]

    @pytest.mark.parametrize(
        "missing", ["manufacturer", "serial_number", "time_created"]
    )
    def test_absent_when_any_of_the_three_is_missing(self, missing: str) -> None:
        assert device_digest(replace(self._FULL, **{missing: None})) is None

    def test_product_is_not_required(self) -> None:
        assert device_digest(replace(self._FULL, product=None)) == device_digest(
            self._FULL
        )

    def test_deterministic(self) -> None:
        assert device_digest(self._FULL) == device_digest(replace(self._FULL))

    def test_differs_when_only_the_creation_time_differs(self) -> None:
        later = replace(self._FULL, time_created=_CREATED + timedelta(seconds=1))
        assert device_digest(later) != device_digest(self._FULL)

    def test_differs_when_only_the_serial_differs(self) -> None:
        other = replace(self._FULL, serial_number=3_300_000_002)
        assert device_digest(other) != device_digest(self._FULL)

    def test_differs_when_only_the_manufacturer_differs(self) -> None:
        other = replace(self._FULL, manufacturer="stryd")
        assert device_digest(other) != device_digest(self._FULL)

    def test_same_instant_in_another_zone_gives_the_same_digest(self) -> None:
        zone = timezone(timedelta(hours=-7))
        shifted = replace(self._FULL, time_created=_CREATED.astimezone(zone))
        assert shifted.time_created is not None
        assert shifted.time_created.utcoffset() != timedelta(0)
        assert device_digest(shifted) == device_digest(self._FULL)


class TestSourceIdentity:
    def test_original_takes_recorded_elapsed_not_the_timer(self) -> None:
        species = identity.garmin_original()
        # Pairwise-distinct so a swapped field cannot pass.
        assert len({species.elapsed_s, species.timer_s, species.distance_m}) == 3
        result = source_identity(_activity(species))
        assert result.elapsed_s == species.elapsed_s
        assert result.elapsed_s != species.timer_s
        assert result.distance_m == species.distance_m

    def test_original_has_a_digest_and_no_session_uuid(self) -> None:
        activity = _activity(identity.garmin_original())
        result = source_identity(activity)
        assert result.kind is SourceKind.ORIGINAL
        assert result.device == device_digest(activity.file_identity)
        assert result.device is not None
        assert result.session_uuid is None

    def test_phone_copy_carries_its_own_formatted_session_uuid(self) -> None:
        activity = _activity(identity.healthfit_copy())
        result = source_identity(activity)
        assert result == SourceIdentity(
            kind=SourceKind.PHONE_COPY,
            elapsed_s=identity.healthfit_copy().elapsed_s,
            distance_m=identity.healthfit_copy().distance_m,
            device=device_digest(activity.file_identity),
            session_uuid="c8c9cacb-cccd-cecf-d0d1-d2d3d4d5d6d7",
        )

    def test_absent_values_stay_none(self) -> None:
        activity = _activity(identity.garmin_original())
        bare = replace(
            activity,
            file_identity=FileIdentity(
                manufacturer=None, product=None, serial_number=None, time_created=None
            ),
            summary=replace(
                activity.summary, total_elapsed_time_s=None, total_distance_m=None
            ),
        )
        assert source_identity(bare) == SourceIdentity(
            kind=SourceKind.UNKNOWN,
            elapsed_s=None,
            distance_m=None,
            device=None,
            session_uuid=None,
        )
