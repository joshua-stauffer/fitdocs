"""Tests for the file-identity read and the undocumented-message count (Req 1.1-1.7).

Every input is an encoded ``.fit`` file decoded by :func:`fitdocs.ingest.parse_fit`
(the synthetic species of :mod:`tests.fixtures.identity` and small files built
here), plus a few hand-built decoded message dicts for the type guards and the
count:

* the first ``file_id`` message supplies manufacturer, product, serial number and
  creation time; a second message that differs in every field is ignored (1.5);
* an unrecorded value is ``None`` -- a file with no ``file_id`` yields four
  ``None``, a file without a serial yields ``None`` there and keeps the rest (1.2);
* the manufacturer is the profile's name, or the recorded number as text (1.3);
* the product is the recorded integer, ``0`` included, never the SDK's
  ``garmin_product`` name (1.3);
* the creation time is an aware UTC instant (1.4);
* the undocumented count is the number of messages under all-digit decoded keys,
  ``0`` (not ``None``) when there are none (1.6);
* the additive defaults leave hand-built values valid and the schema version
  unmoved (1.7); the golden snapshots pin the rest of 1.7.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import timedelta

from fitdocs.ingest import parse_fit
from fitdocs.ingest.decode import decode_fit
from fitdocs.ingest.file_id import count_undocumented_messages, extract_file_identity
from fitdocs.model import (
    SCHEMA_VERSION,
    Activity,
    FileIdentity,
    Provenance,
    fit_datetime,
)
from tests.fixtures import builder, identity
from tests.fixtures.builder import FIT_TIMESTAMP_BASE, Mesg

_RECORD: Mesg = {
    "mesg_num": builder._MESG_RECORD,
    "timestamp": FIT_TIMESTAMP_BASE,
    "heart_rate": 120,
}

_ALL_ABSENT = FileIdentity(
    manufacturer=None, product=None, serial_number=None, time_created=None
)


def _file_id_mesg(
    *,
    manufacturer: str | int | None,
    product: int | None,
    serial: int | None,
    time_created: int | None,
) -> Mesg:
    mesg = builder._file_id(
        serial or 0,
        manufacturer=manufacturer or "garmin",  # type: ignore[arg-type]
        product=product or 0,
        time_created=time_created or 0,
    )
    if product is None:
        del mesg["product"]
    if time_created is None:
        del mesg["time_created"]
    if serial is None:
        del mesg["serial_number"]
    if manufacturer is None:
        del mesg["manufacturer"]
    return mesg


def _parse(*mesgs: Mesg) -> Activity:
    return parse_fit(builder.encode([*mesgs, _RECORD]))


# --- Req 1.1, 1.3, 1.4: the recorded values ---------------------------------


def test_garmin_file_exposes_name_product_serial_and_utc_time() -> None:
    species = identity.garmin_original()
    file_identity = parse_fit(species.data).file_identity

    assert file_identity.manufacturer == "garmin"
    assert file_identity.product == 3843
    assert file_identity.serial_number == species.serial
    assert file_identity.time_created == fit_datetime(species.time_created)
    created = file_identity.time_created
    assert created is not None
    assert created.utcoffset() == timedelta(0)


def test_garmin_product_name_subfield_is_not_the_product() -> None:
    """The SDK adds ``garmin_product`` (a name); the number counts."""
    species = identity.garmin_original()
    file_id = decode_fit(species.data).messages["file_id_mesgs"][0]

    assert file_id["garmin_product"] == "edge_1040"  # precondition: the name is there
    assert parse_fit(species.data).file_identity.product == 3843


def test_development_file_keeps_a_recorded_zero_product() -> None:
    species = identity.healthfit_copy()
    file_identity = parse_fit(species.data).file_identity

    assert file_identity.manufacturer == "development"
    assert file_identity.product == 0
    assert file_identity.serial_number == species.serial
    assert file_identity.time_created == fit_datetime(species.time_created)


def test_stryd_file_exposes_its_own_values() -> None:
    species = identity.stryd_file()
    file_identity = parse_fit(species.data).file_identity

    assert file_identity.manufacturer == "stryd"
    assert file_identity.product == 1
    assert file_identity.serial_number == species.serial
    assert file_identity.time_created == fit_datetime(species.time_created)


def test_unnamed_manufacturer_is_the_recorded_number_as_text() -> None:
    activity = _parse(
        _file_id_mesg(
            manufacturer=65000,
            product=77,
            serial=4_200_000_001,
            time_created=FIT_TIMESTAMP_BASE + 5,
        )
    )
    file_identity = activity.file_identity

    assert file_identity.manufacturer == "65000"
    assert file_identity.product == 77


# --- Req 1.2: absence is None -----------------------------------------------


def test_file_without_file_id_exposes_all_four_as_none() -> None:
    assert _parse().file_identity == _ALL_ABSENT


def test_missing_serial_is_none_and_the_other_values_stay() -> None:
    created = FIT_TIMESTAMP_BASE + 90
    file_identity = _parse(
        _file_id_mesg(
            manufacturer="stryd", product=9, serial=None, time_created=created
        )
    ).file_identity

    assert file_identity.serial_number is None
    assert file_identity.manufacturer == "stryd"
    assert file_identity.product == 9
    assert file_identity.time_created == fit_datetime(created)


def test_missing_manufacturer_is_none_not_an_empty_string() -> None:
    file_identity = _parse(
        _file_id_mesg(
            manufacturer=None,
            product=9,
            serial=4_200_000_033,
            time_created=FIT_TIMESTAMP_BASE + 90,
        )
    ).file_identity

    assert file_identity.manufacturer is None
    assert file_identity.serial_number == 4_200_000_033


def test_missing_product_is_none_and_the_other_values_stay() -> None:
    created = FIT_TIMESTAMP_BASE + 91
    file_identity = _parse(
        _file_id_mesg(
            manufacturer="stryd",
            product=None,
            serial=4_200_000_044,
            time_created=created,
        )
    ).file_identity

    assert file_identity == FileIdentity(
        manufacturer="stryd",
        product=None,
        serial_number=4_200_000_044,
        time_created=fit_datetime(created),
    )


def test_missing_creation_time_is_none_and_the_other_values_stay() -> None:
    file_identity = _parse(
        _file_id_mesg(
            manufacturer="development",
            product=13,
            serial=4_200_000_055,
            time_created=None,
        )
    ).file_identity

    assert file_identity == FileIdentity(
        manufacturer="development",
        product=13,
        serial_number=4_200_000_055,
        time_created=None,
    )


def test_extractor_reads_only_what_the_message_records() -> None:
    assert extract_file_identity([{"manufacturer": "garmin"}]) == FileIdentity(
        "garmin", None, None, None
    )


def test_extractor_drops_values_that_are_not_genuine_integers() -> None:
    """A bool is not a product or serial; a non-int is not a creation time."""
    file_identity = extract_file_identity(
        [
            {
                "manufacturer": "garmin",
                "product": True,
                "serial_number": False,
                "time_created": "yesterday",
            }
        ]
    )

    assert file_identity == FileIdentity(
        manufacturer="garmin", product=None, serial_number=None, time_created=None
    )
    assert extract_file_identity([]) == _ALL_ABSENT


# --- Req 1.5: the first file_id wins ----------------------------------------


def test_two_file_id_messages_use_the_first_in_every_field() -> None:
    first_created = FIT_TIMESTAMP_BASE + 100
    file_identity = _parse(
        _file_id_mesg(
            manufacturer="garmin",
            product=3843,
            serial=4_200_000_011,
            time_created=first_created,
        ),
        _file_id_mesg(
            manufacturer="stryd",
            product=12,
            serial=4_200_000_022,
            time_created=FIT_TIMESTAMP_BASE + 200,
        ),
    ).file_identity

    assert file_identity == FileIdentity(
        manufacturer="garmin",
        product=3843,
        serial_number=4_200_000_011,
        time_created=fit_datetime(first_created),
    )


# --- Req 1.6: the undocumented-message count --------------------------------


def test_spliced_file_reports_its_known_undocumented_count() -> None:
    species = identity.garmin_original()
    assert species.undocumented == identity.UNDOCUMENTED_COUNT  # precondition

    assert parse_fit(species.data).provenance.undocumented_messages == 3


def test_count_is_messages_not_keys() -> None:
    data = identity.splice_undocumented(identity.partner_copy().data, 7)

    assert parse_fit(data).provenance.undocumented_messages == 7


def test_file_without_undocumented_messages_counts_zero_not_none() -> None:
    count = parse_fit(identity.partner_copy().data).provenance.undocumented_messages

    assert count == 0
    assert count is not None


def test_count_ignores_documented_message_types() -> None:
    messages: dict[str, list[dict[str, object]]] = {
        "record_mesgs": [{"heart_rate": 1}, {"heart_rate": 2}],
        "65281": [{"0": 1}, {"0": 2}],
        "12": [{"0": 1}],
    }

    assert count_undocumented_messages(messages) == 3


# --- Req 1.7: additive defaults ----------------------------------------------


def test_new_fields_default_to_absent_and_the_schema_version_holds() -> None:
    provenance = Provenance(sha256="0" * 64, source_path=None, decode_errors=())
    by_name = {f.name: f for f in fields(Activity)}

    assert provenance.undocumented_messages is None
    assert by_name["file_identity"].default_factory() == _ALL_ABSENT  # type: ignore[misc]
    assert SCHEMA_VERSION == "1.0"
