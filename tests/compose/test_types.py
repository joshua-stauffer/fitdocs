"""The composition result values and the package marker (channel-merge 1.2;
Req 7.2; design.md § ComposeTypes, M24).

`SourceContribution`'s field names and order are a cross-spec seam read by
`render/views.py::_head` (`.devices`, `.channels`), so they are pinned by
equality against literals.
"""

from __future__ import annotations

import dataclasses
import typing
from datetime import UTC, datetime

import pytest

import fitdocs
import fitdocs.compose
from fitdocs.compose import types
from fitdocs.identity.kinds import SourceKind
from fitdocs.model import Activity, DeviceInfo
from tests.compose.builders import make_activity


def _field_names(cls: type) -> list[str]:
    return [f.name for f in dataclasses.fields(cls)]


def _hints(cls: type) -> dict[str, object]:
    return typing.get_type_hints(cls)


def _contribution(**overrides: object) -> types.SourceContribution:
    values: dict[str, object] = {
        "sha256": "a" * 64,
        "kind": SourceKind.ORIGINAL,
        "manufacturer": "garmin",
        "devices": (),
        "channels": ("heart_rate_bpm",),
        "alignment": None,
    }
    values.update(overrides)
    return types.SourceContribution(**values)  # type: ignore[arg-type]


class TestSourceContributionSeam:
    def test_field_names_in_order(self) -> None:
        assert _field_names(types.SourceContribution) == [
            "sha256",
            "kind",
            "manufacturer",
            "devices",
            "channels",
            "alignment",
        ]

    def test_devices_is_a_tuple_of_device_info(self) -> None:
        assert _hints(types.SourceContribution)["devices"] == tuple[DeviceInfo, ...]

    def test_kind_is_the_identity_source_kind(self) -> None:
        assert _hints(types.SourceContribution)["kind"] is SourceKind

    def test_channels_and_manufacturer_and_alignment_annotations(self) -> None:
        hints = _hints(types.SourceContribution)
        assert hints["channels"] == tuple[str, ...]
        assert hints["manufacturer"] == (str | None)
        assert hints["alignment"] == (types.ExtraAlignment | None)

    def test_devices_carries_the_given_devices(self) -> None:
        device = DeviceInfo(
            device_index=0,
            manufacturer="garmin",
            product_name="Forerunner",
            serial_number=7,
            software_version=1.5,
            battery_status=None,
        )
        assert _contribution(devices=(device,)).devices == (device,)


class TestValueShapes:
    def test_stretch_lag_fields(self) -> None:
        assert _field_names(types.StretchLag) == ["start", "stop", "lag_s", "key"]
        hints = _hints(types.StretchLag)
        assert hints["start"] is int
        assert hints["stop"] is int
        assert hints["lag_s"] is int
        assert hints["key"] == (str | None)

    def test_extra_alignment_fields(self) -> None:
        assert _field_names(types.ExtraAlignment) == ["hour_shift_s", "stretches"]
        hints = _hints(types.ExtraAlignment)
        assert hints["hour_shift_s"] is int
        assert hints["stretches"] == tuple[types.StretchLag, ...]

    def test_placement_fields(self) -> None:
        assert _field_names(types.Placement) == ["alignment", "extra_index"]
        hints = _hints(types.Placement)
        assert hints["alignment"] is types.ExtraAlignment
        assert hints["extra_index"] == tuple[int | None, ...]

    def test_channel_provenance_fields(self) -> None:
        assert _field_names(types.ChannelProvenance) == ["base", "extras"]
        hints = _hints(types.ChannelProvenance)
        assert hints["base"] is types.SourceContribution
        assert hints["extras"] == tuple[types.SourceContribution, ...]

    def test_composition_fields(self) -> None:
        assert _field_names(types.Composition) == ["activity", "provenance"]
        hints = _hints(types.Composition)
        assert hints["activity"] is Activity
        assert hints["provenance"] is types.ChannelProvenance


class TestBuilders:
    def test_an_omitted_channel_is_all_none_not_zero(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        activity = make_activity(start, [0, 1, 2], power_w=[10, 20, 30])
        assert activity.samples.power_w == (10, 20, 30)
        assert activity.samples.heart_rate_bpm == (None, None, None)
        assert activity.samples.form_power_w == (None, None, None)
        assert activity.samples.latitude_deg == (None, None, None)


class TestFrozen:
    def test_every_value_is_frozen(self) -> None:
        lag = types.StretchLag(start=0, stop=3, lag_s=1, key="distance_m")
        alignment = types.ExtraAlignment(hour_shift_s=0, stretches=(lag,))
        placement = types.Placement(alignment=alignment, extra_index=(0, None, 2))
        contribution = _contribution()
        provenance = types.ChannelProvenance(base=contribution, extras=())
        activity = make_activity(datetime(2026, 1, 1, tzinfo=UTC), [0, 1])
        composition = types.Composition(activity=activity, provenance=provenance)
        for value, attribute in (
            (lag, "lag_s"),
            (alignment, "hour_shift_s"),
            (placement, "extra_index"),
            (contribution, "devices"),
            (provenance, "extras"),
            (composition, "activity"),
        ):
            assert dataclasses.is_dataclass(value)
            with pytest.raises(dataclasses.FrozenInstanceError):
                setattr(value, attribute, None)


class TestPackageMarker:
    def test_all_is_empty(self) -> None:
        assert fitdocs.compose.__all__ == []

    def test_root_package_re_exports_no_composition_name(self) -> None:
        composition_names = {
            "StretchLag",
            "ExtraAlignment",
            "Placement",
            "SourceContribution",
            "ChannelProvenance",
            "Composition",
        }
        assert composition_names.isdisjoint(fitdocs.__all__)
        assert composition_names.isdisjoint(dir(fitdocs))
        assert "compose" not in fitdocs.__all__
