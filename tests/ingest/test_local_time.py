"""Tests for the recorded local-time offset (Amendment 8, Req 4.13, 4.14).

Every encoded input is a small ``.fit`` file decoded by
:func:`fitdocs.ingest.parse_fit`; the type guards use hand-built decoded
``activity`` messages:

* the first ``activity`` message's ``local_timestamp`` minus its ``timestamp``
  is the offset, with its sign: east of UTC is positive, west negative, and a
  recorded zero is a real zero (4.13);
* a difference that is not a whole number of 15-minute steps from -12 h to
  +14 h, a missing or non-integer value, or no ``activity`` message gives
  ``None`` (4.14);
* the additive default leaves hand-built activities valid and the schema
  version unmoved.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import timedelta

import pytest

from fitdocs.ingest import parse_fit
from fitdocs.ingest.local_time import extract_local_offset
from fitdocs.model import SCHEMA_VERSION, Activity
from tests.fixtures import builder
from tests.fixtures.builder import FIT_TIMESTAMP_BASE, Mesg

_END = FIT_TIMESTAMP_BASE + 600


def _activity_mesg(local_delta_s: int | None) -> Mesg:
    mesg = builder._activity(600, 600.0)
    if local_delta_s is not None:
        mesg["local_timestamp"] = _END + local_delta_s
    return mesg


def _parse(*activity_mesgs: Mesg) -> Activity:
    record: Mesg = {
        "mesg_num": builder._MESG_RECORD,
        "timestamp": FIT_TIMESTAMP_BASE,
        "heart_rate": 120,
    }
    return parse_fit(
        builder.encode([builder._file_id(4200000201), record, *activity_mesgs])
    )


# --- Req 4.13: the recorded offset -----------------------------------------


@pytest.mark.parametrize(
    ("delta_s", "offset"),
    [
        (2 * 3600, timedelta(hours=2)),
        (-5 * 3600, timedelta(hours=-5)),
        (5 * 3600 + 45 * 60, timedelta(hours=5, minutes=45)),
        (-12 * 3600, timedelta(hours=-12)),
        (14 * 3600, timedelta(hours=14)),
        (0, timedelta(0)),
    ],
    ids=["east", "west", "quarter-hour", "westmost", "eastmost", "zero"],
)
def test_offset_is_local_timestamp_minus_timestamp(
    delta_s: int, offset: timedelta
) -> None:
    assert _parse(_activity_mesg(delta_s)).local_offset == offset


def test_first_activity_message_wins() -> None:
    first = _activity_mesg(-4 * 3600)
    second = _activity_mesg(2 * 3600)
    assert _parse(first, second).local_offset == timedelta(hours=-4)


# --- Req 4.14: no recorded offset ------------------------------------------


@pytest.mark.parametrize(
    "delta_s",
    [
        -12 * 3600 - 15 * 60,
        14 * 3600 + 15 * 60,
        3600 + 1,
        2 * 3600 + 7 * 60,
    ],
    ids=["west-of-range", "east-of-range", "one-second-off", "not-quarter-hour"],
)
def test_implausible_difference_is_none(delta_s: int) -> None:
    assert _parse(_activity_mesg(delta_s)).local_offset is None


def test_activity_without_local_timestamp_is_none() -> None:
    assert _parse(_activity_mesg(None)).local_offset is None


def test_file_without_activity_message_is_none() -> None:
    assert _parse().local_offset is None


@pytest.mark.parametrize(
    "mesg",
    [
        # A bool read as 0 or 1 would give a valid one-hour offset here.
        {"timestamp": 1 - 3600, "local_timestamp": True},
        {"timestamp": False, "local_timestamp": 3600},
        {"timestamp": _END, "local_timestamp": float(_END + 3600)},
        {"timestamp": str(_END), "local_timestamp": _END + 3600},
        {"local_timestamp": _END + 3600},
    ],
    ids=[
        "bool-local",
        "bool-timestamp",
        "float-local",
        "text-timestamp",
        "no-timestamp",
    ],
)
def test_values_that_are_not_genuine_integers_are_none(
    mesg: dict[str, object],
) -> None:
    assert extract_local_offset([mesg]) is None


def test_no_messages_is_none() -> None:
    assert extract_local_offset([]) is None


# --- additive default --------------------------------------------------------


def test_field_defaults_to_absent_and_the_schema_version_holds() -> None:
    by_name = {f.name: f for f in fields(Activity)}

    assert by_name["local_offset"].default is None
    assert SCHEMA_VERSION == "1.0"
