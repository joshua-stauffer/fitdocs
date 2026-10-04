"""Synthetic ``.fit`` files with the measured identity shapes (activity-identity).

Every value here is a synthetic constant; none comes from an athlete's archive.
:func:`session_fit_bytes` builds one small session with a caller-chosen
``file_id``, one ``device_info`` and, optionally, the HealthFit ``SESSION UUID``
developer field and spliced messages of an undocumented global number. The
named species below are thin calls to it:

* ``garmin_original`` -- a Garmin device file with undocumented messages;
* ``partner_copy`` -- the same recording with the same ``file_id`` and none of
  the undocumented messages;
* ``healthfit_copy`` / ``healthfit_shifted`` -- a HealthFit-style copy, and the
  same copy with its start shifted by whole hours;
* ``healthfit_reexport_pair`` -- two exports sharing one session UUID;
* ``stryd_file`` -- a Stryd-style file;
* ``ten_k_pair`` -- two different 10 k runs, the counter-example.

Times are FIT-epoch seconds (the builder's ``FIT_TIMESTAMP_BASE`` convention).
"""

from __future__ import annotations

from dataclasses import dataclass

from garmin_fit_sdk import Encoder  # type: ignore[import-untyped]
from garmin_fit_sdk.crc_calculator import CrcCalculator  # type: ignore[import-untyped]

from tests.fixtures import builder
from tests.fixtures.builder import Mesg

UNDOCUMENTED_GLOBAL_NUMBER = 0xFF01
"""A global message number the SDK profile lacks; the decoder files it under
``str(65281)``."""

_SPLICE_LOCAL_TYPE = 15
_UINT8_BASE_TYPE_ID = 0x02
_HEADER_CRC_OFFSET = 12
_HEADER_SIZE_WITH_CRC = 14
_DATA_SIZE_OFFSET = 4
_RECORD_COUNT = 5
_HOUR_S = 3600

_START = builder.FIT_TIMESTAMP_BASE + 700_000_000
_ELAPSED_S = 3000.0
_DISTANCE_M = 9_000.0

_ORIGINAL_SERIAL = 3_300_000_001
_HEALTHFIT_SERIAL = 3_300_000_002
_STRYD_SERIAL = 3_300_000_003
_SESSION_UUID = tuple(range(200, 216))
_OTHER_SESSION_UUID = tuple(range(20, 36))


def splice_undocumented(data: bytes, count: int) -> bytes:
    """Append ``count`` messages of :data:`UNDOCUMENTED_GLOBAL_NUMBER` to a file.

    The messages go after the last encoded message; the header's data size and
    both CRCs are recomputed so the result still passes the SDK's integrity
    check. ``count == 0`` returns the input unchanged. Each message
    carries its 1-based index as a ``uint8``, whose value 255 is the FIT
    invalid marker a decoder drops, so ``count`` may not exceed 254.
    """
    if count < 0:
        raise ValueError("count must be non-negative")
    if count > 254:
        raise ValueError("count must not exceed 254")
    if count == 0:
        return data
    header_size = data[0]
    if header_size not in (12, _HEADER_SIZE_WITH_CRC):
        raise ValueError(f"unexpected FIT header size {header_size}")
    body = bytearray(data[header_size:-2])
    body.append(0x40 | _SPLICE_LOCAL_TYPE)  # definition message header
    body += bytes([0, 0])  # reserved, little-endian architecture
    body += UNDOCUMENTED_GLOBAL_NUMBER.to_bytes(2, "little")
    body += bytes([1, 0, 1, _UINT8_BASE_TYPE_ID])  # one field: number 0, size 1
    for i in range(count):
        body += bytes([_SPLICE_LOCAL_TYPE, i + 1])
    header = bytearray(data[:header_size])
    header[_DATA_SIZE_OFFSET : _DATA_SIZE_OFFSET + 4] = len(body).to_bytes(4, "little")
    if header_size == _HEADER_SIZE_WITH_CRC:
        header[_HEADER_CRC_OFFSET:_HEADER_SIZE_WITH_CRC] = CrcCalculator.calculate_crc(
            header, 0, _HEADER_CRC_OFFSET
        ).to_bytes(2, "little")
    content = bytes(header) + bytes(body)
    file_crc = int(CrcCalculator.calculate_crc(content, 0, len(content)))
    return content + file_crc.to_bytes(2, "little")


def session_fit_bytes(
    *,
    sport: str,
    start: int,
    elapsed_s: float,
    timer_s: float,
    distance_m: float | None,
    manufacturer: str,
    product: int,
    serial: int,
    time_created: int,
    session_uuid: tuple[int, ...] | None = None,
    undocumented: int = 0,
    with_position: bool = False,
    device_manufacturer: str | None = None,
) -> bytes:
    """Encode one small session as ``.fit`` bytes.

    ``file_id`` carries ``manufacturer`` / ``product`` / ``serial`` /
    ``time_created`` as given. One ``device_info`` (index 0) is written through
    the builder with ``device_manufacturer`` (default: ``manufacturer``).
    ``session_uuid`` (16 byte values), when given, is recorded as the HealthFit
    ``SESSION UUID`` developer field on the session, registered with the
    builder's own field description. ``undocumented`` messages are spliced in
    with :func:`splice_undocumented`. ``distance_m=None`` records no distance,
    neither on the session nor on any record.
    """
    end = start + round(elapsed_s)
    dev_data_id: Mesg = {
        "mesg_num": builder._MESG_DEVELOPER_DATA_ID,
        "developer_data_index": 0,
        "application_id": list(range(16)),
    }
    encoder = Encoder()
    session_extra: Mesg = {}
    field_descriptions: list[Mesg] = []
    if session_uuid is not None:
        # The builder's own registration of the SESSION UUID field (index 0).
        name, base_type, array_len = builder._SESSION_DEV_FIELD_SPECS[0]
        field_desc: Mesg = {
            "mesg_num": builder._MESG_FIELD_DESCRIPTION,
            "developer_data_index": 0,
            "field_definition_number": 0,
            "fit_base_type_id": base_type,
            "field_name": name,
            "array": array_len,
        }
        encoder.add_developer_field("k0", dev_data_id, field_desc)
        field_descriptions.append(field_desc)
        session_extra["developer_fields"] = {"k0": list(session_uuid)}

    records: list[Mesg] = []
    for i in range(_RECORD_COUNT):
        fraction = i / (_RECORD_COUNT - 1)
        record: Mesg = {
            "mesg_num": builder._MESG_RECORD,
            "timestamp": start + round(elapsed_s * fraction),
            "heart_rate": 140 + i,
        }
        if distance_m is not None:
            record["distance"] = distance_m * fraction
        if with_position:
            record["position_lat"] = builder.to_semicircles(40.0 + 0.0001 * i)
            record["position_long"] = builder.to_semicircles(-105.0 + 0.0001 * i)
        records.append(record)

    ordered: list[Mesg] = [
        builder._file_id(
            serial,
            manufacturer=manufacturer,
            product=product,
            time_created=time_created,
        ),
        *([dev_data_id, *field_descriptions] if session_uuid is not None else []),
        builder._device_info(
            serial,
            "SyntheticIdentityDevice",
            manufacturer=device_manufacturer or manufacturer,
        ),
        {"mesg_num": builder._MESG_SPORT, "sport": sport, "sub_sport": "generic"},
        *records,
        {
            "mesg_num": builder._MESG_SESSION,
            "start_time": start,
            "timestamp": end,
            "sport": sport,
            "sub_sport": "generic",
            "total_elapsed_time": elapsed_s,
            "total_timer_time": timer_s,
            **({} if distance_m is None else {"total_distance": distance_m}),
            **session_extra,
        },
        {
            "mesg_num": builder._MESG_ACTIVITY,
            "timestamp": end,
            "total_timer_time": timer_s,
            "num_sessions": 1,
            "type": "manual",
        },
    ]
    for mesg in ordered:
        encoder.write_mesg(mesg)
    return splice_undocumented(bytes(encoder.close()), undocumented)


@dataclass(frozen=True)
class Species:
    """One named fixture and the values its tests pin."""

    data: bytes
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


def _species(
    *,
    sport: str = "running",
    manufacturer: str,
    product: int,
    serial: int,
    time_created: int,
    start: int,
    elapsed_s: float,
    timer_s: float,
    distance_m: float,
    undocumented: int = 0,
    session_uuid: tuple[int, ...] | None = None,
    device_manufacturer: str | None = None,
) -> Species:
    data = session_fit_bytes(
        sport=sport,
        start=start,
        elapsed_s=elapsed_s,
        timer_s=timer_s,
        distance_m=distance_m,
        manufacturer=manufacturer,
        product=product,
        serial=serial,
        time_created=time_created,
        session_uuid=session_uuid,
        undocumented=undocumented,
        device_manufacturer=device_manufacturer,
    )
    return Species(
        data=data,
        sport=sport,
        manufacturer=manufacturer,
        product=product,
        serial=serial,
        time_created=time_created,
        device_manufacturer=device_manufacturer or manufacturer,
        start=start,
        elapsed_s=elapsed_s,
        timer_s=timer_s,
        distance_m=distance_m,
        undocumented=undocumented,
        session_uuid=session_uuid,
    )


UNDOCUMENTED_COUNT = 3


def garmin_original() -> Species:
    """A Garmin device file: product 3843, created at the start, timer < elapsed."""
    return _species(
        manufacturer="garmin",
        product=3843,
        serial=_ORIGINAL_SERIAL,
        time_created=_START,
        start=_START,
        elapsed_s=_ELAPSED_S,
        timer_s=_ELAPSED_S - 120.0,
        distance_m=_DISTANCE_M,
        undocumented=UNDOCUMENTED_COUNT,
    )


def partner_copy() -> Species:
    """The original's ``file_id`` and recording, without undocumented messages."""
    return _species(
        manufacturer="garmin",
        product=3843,
        serial=_ORIGINAL_SERIAL,
        time_created=_START,
        start=_START,
        elapsed_s=_ELAPSED_S,
        timer_s=_ELAPSED_S - 120.0,
        distance_m=_DISTANCE_M,
        undocumented=0,
    )


def healthfit_copy() -> Species:
    """A HealthFit-style copy of the Garmin recording.

    ``file_id`` manufacturer ``development`` with its own serial and a creation
    time hours later; timer equals elapsed; elapsed within 1 s and distance
    within 5 m of the original; the session UUID is recorded. ``device_info``
    says ``garmin`` (a synthetic variant: a copy of a Garmin recording).
    """
    return _species(
        manufacturer="development",
        product=0,
        serial=_HEALTHFIT_SERIAL,
        time_created=_START + 4 * _HOUR_S,
        start=_START,
        elapsed_s=_ELAPSED_S + 0.5,
        timer_s=_ELAPSED_S + 0.5,
        distance_m=_DISTANCE_M + 2.0,
        session_uuid=_SESSION_UUID,
        device_manufacturer="garmin",
    )


def healthfit_shifted() -> Species:
    """The HealthFit copy with its start shifted two hours later."""
    base = healthfit_copy()
    return _species(
        manufacturer=base.manufacturer,
        product=base.product,
        serial=base.serial,
        time_created=base.time_created,
        start=base.start + 2 * _HOUR_S,
        elapsed_s=base.elapsed_s,
        timer_s=base.timer_s,
        distance_m=base.distance_m,
        session_uuid=base.session_uuid,
        device_manufacturer=base.device_manufacturer,
    )


def healthfit_reexport_pair() -> tuple[Species, Species]:
    """(older, newer) HealthFit exports of one recording, one session UUID.

    The older export is shifted one hour; the newer carries the corrected
    start and a later creation time.
    """
    older = _species(
        manufacturer="development",
        product=0,
        serial=_HEALTHFIT_SERIAL,
        time_created=_START + 4 * _HOUR_S,
        start=_START + _HOUR_S,
        elapsed_s=_ELAPSED_S,
        timer_s=_ELAPSED_S,
        distance_m=_DISTANCE_M,
        session_uuid=_OTHER_SESSION_UUID,
        device_manufacturer="garmin",
    )
    newer = _species(
        manufacturer="development",
        product=0,
        serial=_HEALTHFIT_SERIAL,
        time_created=_START + 5 * _HOUR_S,
        start=_START,
        elapsed_s=_ELAPSED_S,
        timer_s=_ELAPSED_S,
        distance_m=_DISTANCE_M,
        session_uuid=_OTHER_SESSION_UUID,
        device_manufacturer="garmin",
    )
    return older, newer


def stryd_file() -> Species:
    """A Stryd-style file: ``stryd`` in ``file_id`` and ``device_info``.

    Starts when the HealthFit copy starts; distance equal to the copy's to
    0.01 m; elapsed 8.5 s longer.
    """
    copy = healthfit_copy()
    return _species(
        manufacturer="stryd",
        product=1,
        serial=_STRYD_SERIAL,
        time_created=copy.start,
        start=copy.start,
        elapsed_s=copy.elapsed_s + 8.5,
        timer_s=copy.elapsed_s + 8.5,
        distance_m=copy.distance_m,
        device_manufacturer="stryd",
    )


def ten_k_pair() -> tuple[Species, Species]:
    """Two different 10 k runs a day and 17 minutes apart (the counter-example).

    Elapsed differs by 60 s and distance by 200 m; each has its own serial.
    """
    first = _species(
        manufacturer="garmin",
        product=3843,
        serial=_ORIGINAL_SERIAL + 10,
        time_created=_START,
        start=_START,
        elapsed_s=3000.0,
        timer_s=3000.0,
        distance_m=10_000.0,
    )
    second_start = _START + 24 * _HOUR_S + 17 * 60
    second = _species(
        manufacturer="garmin",
        product=3843,
        serial=_ORIGINAL_SERIAL + 11,
        time_created=second_start,
        start=second_start,
        elapsed_s=3060.0,
        timer_s=3060.0,
        distance_m=10_200.0,
    )
    return first, second
