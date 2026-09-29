"""Self-tests for the identity fixtures in ``tests/fixtures/identity.py``.

Each named species must decode without decode errors, pass the SDK integrity
check, and carry exactly the ``file_id``, ``device_info`` manufacturer, session
values, session UUID and undocumented-message count the identity tests rely on.
The expected values below are literals, not read back from the species.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import pytest
from garmin_fit_sdk import Decoder, Stream  # type: ignore[import-untyped]

from fitdocs import parse_fit
from tests.fixtures import builder, identity
from tests.fixtures.identity import Species

_UNDOCUMENTED_KEY = "65281"

_UUID_A = tuple(range(200, 216))
_UUID_B = tuple(range(20, 36))


@dataclass(frozen=True)
class Expected:
    sport: str
    manufacturer: str
    product: int
    serial: int
    time_created: int
    device_manufacturer: str
    start: int
    elapsed_s: float
    timer_s: float
    distance_m: float
    undocumented: int
    session_uuid: tuple[int, ...] | None


_CASES: dict[str, tuple[Callable[[], Species], Expected]] = {
    "garmin_original": (
        identity.garmin_original,
        Expected(
            "running",
            "garmin",
            3843,
            3300000001,
            1700000000,
            "garmin",
            1700000000,
            3000.0,
            2880.0,
            9000.0,
            3,
            None,
        ),
    ),
    "partner_copy": (
        identity.partner_copy,
        Expected(
            "running",
            "garmin",
            3843,
            3300000001,
            1700000000,
            "garmin",
            1700000000,
            3000.0,
            2880.0,
            9000.0,
            0,
            None,
        ),
    ),
    "healthfit_copy": (
        identity.healthfit_copy,
        Expected(
            "running",
            "development",
            0,
            3300000002,
            1700014400,
            "garmin",
            1700000000,
            3000.5,
            3000.5,
            9002.0,
            0,
            _UUID_A,
        ),
    ),
    "healthfit_shifted": (
        identity.healthfit_shifted,
        Expected(
            "running",
            "development",
            0,
            3300000002,
            1700014400,
            "garmin",
            1700007200,
            3000.5,
            3000.5,
            9002.0,
            0,
            _UUID_A,
        ),
    ),
    "healthfit_reexport_older": (
        lambda: identity.healthfit_reexport_pair()[0],
        Expected(
            "running",
            "development",
            0,
            3300000002,
            1700014400,
            "garmin",
            1700003600,
            3000.0,
            3000.0,
            9000.0,
            0,
            _UUID_B,
        ),
    ),
    "healthfit_reexport_newer": (
        lambda: identity.healthfit_reexport_pair()[1],
        Expected(
            "running",
            "development",
            0,
            3300000002,
            1700018000,
            "garmin",
            1700000000,
            3000.0,
            3000.0,
            9000.0,
            0,
            _UUID_B,
        ),
    ),
    "stryd_file": (
        identity.stryd_file,
        Expected(
            "running",
            "stryd",
            1,
            3300000003,
            1700000000,
            "stryd",
            1700000000,
            3009.0,
            3009.0,
            9002.0,
            0,
            None,
        ),
    ),
    "ten_k_first": (
        lambda: identity.ten_k_pair()[0],
        Expected(
            "running",
            "garmin",
            3843,
            3300000011,
            1700000000,
            "garmin",
            1700000000,
            3000.0,
            3000.0,
            10000.0,
            0,
            None,
        ),
    ),
    "ten_k_second": (
        lambda: identity.ten_k_pair()[1],
        Expected(
            "running",
            "garmin",
            3843,
            3300000012,
            1700087420,
            "garmin",
            1700087420,
            3060.0,
            3060.0,
            10200.0,
            0,
            None,
        ),
    ),
}


def _decoded(name: str) -> tuple[dict[str, list[dict[str, object]]], list[object]]:
    return builder.decode_messages(_CASES[name][0]().data)


@pytest.mark.parametrize("name", sorted(_CASES))
def test_species_decodes_cleanly_and_passes_integrity(name: str) -> None:
    data = _CASES[name][0]().data
    _, errors = builder.decode_messages(data)
    assert errors == []
    assert Decoder(Stream.from_byte_array(data)).check_integrity() is True


@pytest.mark.parametrize("name", sorted(_CASES))
def test_species_carries_the_stated_identity_and_session(name: str) -> None:
    expected = _CASES[name][1]
    messages, _ = _decoded(name)

    (file_id,) = messages["file_id_mesgs"]
    assert file_id["manufacturer"] == expected.manufacturer
    assert file_id["product"] == expected.product
    assert file_id["serial_number"] == expected.serial
    assert file_id["time_created"] == expected.time_created

    (device,) = messages["device_info_mesgs"]
    assert device["manufacturer"] == expected.device_manufacturer

    (session,) = messages["session_mesgs"]
    assert session["sport"] == expected.sport
    assert session["start_time"] == expected.start
    assert session["total_elapsed_time"] == expected.elapsed_s
    assert session["total_timer_time"] == expected.timer_s
    assert session["total_distance"] == expected.distance_m

    assert len(messages.get(_UNDOCUMENTED_KEY, [])) == expected.undocumented


@pytest.mark.parametrize("name", sorted(_CASES))
def test_species_record_stream_spans_the_session(name: str) -> None:
    expected = _CASES[name][1]
    messages, _ = _decoded(name)
    end = expected.start + round(expected.elapsed_s)

    records = messages["record_mesgs"]
    assert records[0]["timestamp"] == expected.start
    assert records[-1]["timestamp"] == end
    assert records[-1]["distance"] == expected.distance_m
    (session,) = messages["session_mesgs"]
    assert session["timestamp"] == end
    (activity,) = messages["activity_mesgs"]
    assert activity["timestamp"] == end


@pytest.mark.parametrize("name", sorted(_CASES))
def test_species_session_uuid_is_recorded_only_where_stated(name: str) -> None:
    expected = _CASES[name][1]
    activity = parse_fit(_CASES[name][0]().data)
    assert activity.developer_fields.get("SESSION UUID") == expected.session_uuid


def test_partner_copy_shares_the_original_file_id_with_fewer_undocumented() -> None:
    original, _ = _decoded("garmin_original")
    partner, _ = _decoded("partner_copy")
    assert partner["file_id_mesgs"] == original["file_id_mesgs"]
    assert _UNDOCUMENTED_KEY in original
    assert _UNDOCUMENTED_KEY not in partner
    assert _CASES["partner_copy"][0]().data != _CASES["garmin_original"][0]().data


def test_the_reexport_pair_shares_one_uuid_and_differs_in_bytes() -> None:
    older, newer = identity.healthfit_reexport_pair()
    assert older.data != newer.data
    assert older.session_uuid == newer.session_uuid


def test_position_is_recorded_only_when_asked() -> None:
    def records(with_position: bool) -> list[dict[str, object]]:
        data = identity.session_fit_bytes(
            sport="running",
            start=1700000000,
            elapsed_s=100.0,
            timer_s=100.0,
            distance_m=300.0,
            manufacturer="garmin",
            product=3843,
            serial=1,
            time_created=1700000000,
            with_position=with_position,
        )
        return builder.decode_messages(data)[0]["record_mesgs"]

    assert all("position_lat" in r for r in records(True))
    assert all("position_lat" not in r for r in records(False))


def test_splice_refuses_a_count_one_byte_cannot_index() -> None:
    with pytest.raises(ValueError, match="must not exceed 254"):
        identity.splice_undocumented(builder.run_fit_bytes(), 255)


def test_splice_accepts_the_largest_count_every_index_decodes_for() -> None:
    spliced = identity.splice_undocumented(builder.run_fit_bytes(), 254)
    messages, errors = builder.decode_messages(spliced)
    assert errors == []
    assert len(messages[_UNDOCUMENTED_KEY]) == 254
    # The decoder keys an undocumented message's fields by their integer number.
    last = cast("dict[int, int]", messages[_UNDOCUMENTED_KEY][-1])
    assert last == {0: 254}


def test_splice_of_zero_messages_returns_the_input_bytes() -> None:
    data = builder.run_fit_bytes()
    assert identity.splice_undocumented(data, 0) == data


def test_splice_appends_exactly_the_requested_count() -> None:
    data = builder.run_fit_bytes()
    for count in (1, 2, 7):
        spliced = identity.splice_undocumented(data, count)
        messages, errors = builder.decode_messages(spliced)
        assert errors == []
        assert len(messages[_UNDOCUMENTED_KEY]) == count
        assert Decoder(Stream.from_byte_array(spliced)).check_integrity() is True
