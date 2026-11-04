"""Pins for the shared Strava wire module (strava-publish task 1.2; Req 5.1,
5.3, 5.4, 5.6, 6.2, 15.3).

Every pinned constant, field set and outcome set below is a literal written
in this file from "SharedTargetWire" in the strava-publish design.md, not
imported from the module, so a change to the module reds the pin rather than
the pin tracking the module. The title, description and file bounds are each
tested at the bound and one past it.
"""

from __future__ import annotations

import ast
import base64
import dataclasses
from collections.abc import Callable
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

import pytest

import fitdocs.connectors.relay_targets as rt
from fitdocs.connectors.protocol import TARGET_CODES
from fitdocs.connectors.relay_envelope import EnvelopeError
from fitdocs.connectors.relay_targets import (
    PublishFacts,
    connect_page_path,
    parse_publish_fields,
    parse_upload_fields,
    publish_fields,
    route_outcome,
    target_route,
    upload_fields,
)
from fitdocs.model import Sport

PID = "0123456789abcdef0123456789abcdef"
FIT = b"\x0e\x10\x00\x00\x00\x00\x00\x00.FITabc"
FIT_NEEDS_STANDARD_ALPHABET = b"\x0e\x10\x00\x00\x00\x00\x00\x00.FIT\xfb\xff\xfe"
START = datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone(timedelta(hours=-5)))


def facts(**over: object) -> PublishFacts:
    base = PublishFacts(
        PID, "Run", START, 3600.0, 10000.5, "Morning run", "line one\n\tline two"
    )
    return dataclasses.replace(base, **over)  # type: ignore[arg-type]


def pub(**over: object) -> dict[str, object]:
    fields = publish_fields(facts())
    fields.update(over)
    return fields


def upl(**over: object) -> dict[str, object]:
    fields = upload_fields(facts(), FIT)
    fields.update(over)
    return fields


def refused(call: Callable[[], object], message: str | None = None) -> str:
    with pytest.raises(EnvelopeError) as info:
        call()
    if message is not None:
        assert str(info.value) == message
    return str(info.value)


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #


def test_constants_are_pinned() -> None:
    assert rt.STRAVA == "strava"
    assert rt.TARGET_ROUTE_PREFIX == "/v1/targets/"
    assert rt.ACTION_CONNECT == "connect"
    assert rt.ACTION_CONNECT_POLL == "connect/poll"
    assert rt.ACTION_PUBLISH == "publish"
    assert rt.ACTION_UPLOAD == "upload"
    assert rt.ACTION_DISCONNECT == "disconnect"
    assert rt.TARGET_ACTIONS == (
        "connect",
        "connect/poll",
        "publish",
        "upload",
        "disconnect",
    )
    assert rt.CONNECT_PAGE_PREFIX == "/connect/"
    assert rt.LINK_FIELD == "link"
    assert rt.PUBLICATION_ID_RE == r"^[0-9a-f]{32}$"
    assert rt.SPORT_RE == r"^[A-Z][A-Za-z]{0,31}$"
    assert rt.MAX_TITLE_CHARS == 255
    assert rt.MAX_DESCRIPTION_CHARS == 8000
    assert rt.MAX_FIT_BYTES == 16777216
    assert rt.MAX_UPLOAD_REQUEST_BYTES == 23068672


def test_field_sets_are_pinned() -> None:
    publish = {
        "publication_id",
        "sport",
        "start",
        "elapsed_s",
        "distance_m",
        "title",
        "description",
    }
    assert frozenset(publish) == rt.PUBLISH_FIELDS
    assert frozenset(publish | {"fit"}) == rt.UPLOAD_FIELDS


def test_fitdocs_sports_literal_equals_the_model_sports() -> None:
    assert (
        frozenset({"Ride", "Run", "Swim", "Walk", "Hike", "Rowing", "Workout"})
        == rt.FITDOCS_SPORTS
    )
    assert {s.value for s in Sport} == rt.FITDOCS_SPORTS


PUBLISH_OUTCOMES = frozenset(
    {
        "posted",
        "not_found",
        "ambiguous",
        "not_updatable",
        "not_connected",
        "auth_rejected",
        "permission_denied",
        "rate_limited",
        "unavailable",
        "rejected",
        "activity_facts_missing",
    }
)
UPLOAD_OUTCOMES = frozenset(
    {
        "posted",
        "uploaded",
        "ambiguous",
        "not_updatable",
        "not_connected",
        "auth_rejected",
        "permission_denied",
        "rate_limited",
        "unavailable",
        "rejected",
        "unconfirmed",
        "activity_facts_missing",
    }
)


def test_outcome_sets_are_pinned_literals() -> None:
    assert rt.PUBLISH_OUTCOMES == PUBLISH_OUTCOMES
    assert rt.UPLOAD_OUTCOMES == UPLOAD_OUTCOMES
    assert "not_found" not in rt.UPLOAD_OUTCOMES
    assert "uploaded" not in rt.PUBLISH_OUTCOMES


def test_outcome_sets_are_within_publish_cores_target_codes() -> None:
    target_values = {c.value for c in TARGET_CODES}
    assert target_values, "TARGET_CODES is empty"
    assert target_values >= rt.PUBLISH_OUTCOMES
    assert target_values >= rt.UPLOAD_OUTCOMES


def test_route_outcome_passes_only_members() -> None:
    assert route_outcome("not_found", rt.PUBLISH_OUTCOMES) == "not_found"
    assert route_outcome("not_found", rt.UPLOAD_OUTCOMES) is None
    assert route_outcome("uploaded", rt.PUBLISH_OUTCOMES) is None
    assert route_outcome("uploaded", rt.UPLOAD_OUTCOMES) == "uploaded"
    assert route_outcome(None, rt.UPLOAD_OUTCOMES) is None
    assert route_outcome("nonsense", rt.UPLOAD_OUTCOMES) is None


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #


def test_paths() -> None:
    for action in ("connect", "connect/poll", "publish", "upload", "disconnect"):
        assert target_route("strava", action) == f"/v1/targets/strava/{action}"
    assert connect_page_path("strava", "BCDF-GHJK") == "/connect/strava?code=BCDF-GHJK"


@pytest.mark.parametrize(
    "call",
    [
        lambda: target_route("Strava", "publish"),
        lambda: target_route("strava/x", "publish"),
        lambda: target_route("strava", "../publish"),
        lambda: target_route("strava", "nonsense"),
        lambda: connect_page_path("strava", "bcdf-ghjk"),
        lambda: connect_page_path("strava", "BCDF-GHJK&x=1"),
        lambda: connect_page_path("a/b", "BCDF-GHJK"),
    ],
)
def test_malformed_path_parts_are_refused(call: Callable[[], object]) -> None:
    refused(call)


# --------------------------------------------------------------------------- #
# Codec
# --------------------------------------------------------------------------- #


def test_publish_fields_round_trip_and_shape() -> None:
    fields = publish_fields(facts())
    assert set(fields) == rt.PUBLISH_FIELDS
    assert fields["start"] == "2026-03-04T05:06:07-05:00"
    assert fields["elapsed_s"] == 3600.0
    assert parse_publish_fields(fields) == facts()


def test_absent_numbers_are_null_and_round_trip() -> None:
    fields = publish_fields(facts(elapsed_s=None, distance_m=None))
    assert fields["elapsed_s"] is None and fields["distance_m"] is None
    parsed = parse_publish_fields(fields)
    assert parsed.elapsed_s is None and parsed.distance_m is None


def test_zero_numbers_are_kept_not_treated_as_absent() -> None:
    parsed = parse_publish_fields(pub(elapsed_s=0, distance_m=0.0))
    assert parsed.elapsed_s == 0.0 and parsed.distance_m == 0.0
    assert parsed.elapsed_s is not None and parsed.distance_m is not None


def test_integer_numbers_are_accepted() -> None:
    assert parse_publish_fields(pub(elapsed_s=60, distance_m=1000)).distance_m == 1000.0


def test_upload_round_trip_carries_standard_base64() -> None:
    fit = FIT_NEEDS_STANDARD_ALPHABET
    standard = base64.b64encode(fit).decode("ascii")
    assert standard != base64.urlsafe_b64encode(fit).decode("ascii")
    fields = upload_fields(facts(), fit)
    assert set(fields) == rt.UPLOAD_FIELDS
    assert fields["fit"] == standard
    assert parse_upload_fields(fields) == (facts(), fit)


def test_naive_start_is_refused_on_parse_and_encode() -> None:
    refused(
        lambda: parse_publish_fields(pub(start="2026-03-04T05:06:07")),
        "the start is not an ISO 8601 time with an offset",
    )
    refused(lambda: publish_fields(facts(start=datetime(2026, 3, 4, 5, 6, 7))))


@pytest.mark.parametrize(
    "start", [None, 1772600000, "yesterday", "", "2026-13-01T00:00:00Z"]
)
def test_unparseable_start_is_refused(start: object) -> None:
    refused(lambda: parse_publish_fields(pub(start=start)))


def test_non_datetime_start_is_refused_on_encode() -> None:
    msg = "the start is not an ISO 8601 time with an offset"
    refused(lambda: publish_fields(facts(start="2026-03-04T05:06:07-05:00")), msg)


class _NoOffset(tzinfo):
    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None

    def dst(self, dt: datetime | None) -> timedelta | None:
        return None

    def tzname(self, dt: datetime | None) -> str | None:
        return None


def test_aware_looking_start_without_an_offset_is_refused_on_encode() -> None:
    start = datetime(2026, 3, 4, 5, 6, 7, tzinfo=_NoOffset())
    assert start.tzinfo is not None and start.utcoffset() is None
    refused(
        lambda: publish_fields(facts(start=start)),
        "the start is not an ISO 8601 time with an offset",
    )


def test_offset_start_is_accepted() -> None:
    assert parse_publish_fields(
        pub(start="2026-03-04T05:06:07Z")
    ).start.utcoffset() == timedelta(0)


@pytest.mark.parametrize("name", ["elapsed_s", "distance_m"])
@pytest.mark.parametrize(
    "bad",
    [
        True,
        False,
        -1,
        -0.5,
        float("nan"),
        float("inf"),
        float("-inf"),
        "12",
        [1],
        {"a": 1},
    ],
)
def test_bad_numbers_are_refused(name: str, bad: object) -> None:
    refused(
        lambda: parse_publish_fields(pub(**{name: bad})),
        "a number is not null or a finite non-negative number",
    )


@pytest.mark.parametrize("name", ["elapsed_s", "distance_m"])
@pytest.mark.parametrize("bad", [True, -1.0, float("nan"), float("inf")])
def test_bad_numbers_are_refused_on_encode(name: str, bad: object) -> None:
    refused(lambda: publish_fields(facts(**{name: bad})))


def test_title_bounds() -> None:
    assert parse_publish_fields(pub(title="x")).title == "x"
    assert len(parse_publish_fields(pub(title="x" * 255)).title) == 255
    msg = "the title is empty, too long or has a control character"
    refused(lambda: parse_publish_fields(pub(title="x" * 256)), msg)
    refused(lambda: parse_publish_fields(pub(title="")), msg)
    refused(lambda: publish_fields(facts(title="x" * 256)), msg)


def test_non_control_format_and_separator_characters_are_accepted() -> None:
    for text in ("\U0001f3c3\u200d\u2642\ufe0f run", "a\u2028b", "a\u200bb"):
        for field in ("title", "description"):
            fields = publish_fields(facts(**{field: text}))
            assert fields[field] == text
            assert getattr(parse_publish_fields(fields), field) == text


@pytest.mark.parametrize("char", ["\n", "\t", "\x00", "\x1b", "\x7f", "\x85"])
def test_title_control_characters_are_refused(char: str) -> None:
    refused(lambda: parse_publish_fields(pub(title=f"a{char}b")))
    refused(lambda: publish_fields(facts(title=f"a{char}b")))


def test_description_bounds_and_controls() -> None:
    assert parse_publish_fields(pub(description="")).description == ""
    assert len(parse_publish_fields(pub(description="d" * 8000)).description) == 8000
    msg = "the description is too long or has a control character"
    refused(lambda: parse_publish_fields(pub(description="d" * 8001)), msg)
    assert parse_publish_fields(pub(description="a\nb\tc")).description == "a\nb\tc"
    for char in ("\r", "\x00", "\x1b", "\x7f", "\x85"):
        _refuse_description(char, msg)


def _refuse_description(char: str, msg: str) -> None:
    refused(lambda: parse_publish_fields(pub(description=f"a{char}b")), msg)
    refused(lambda: publish_fields(facts(description=f"a{char}b")), msg)


@pytest.mark.parametrize(
    "bad", [PID.upper(), PID[:-1], PID + "0", PID + "\n", "g" * 32, "", None, 7]
)
def test_bad_publication_id_is_refused(bad: object) -> None:
    refused(
        lambda: parse_publish_fields(pub(publication_id=bad)),
        "the publication id is malformed",
    )


@pytest.mark.parametrize(
    "bad", ["run", "", "R" * 33, "Run1", "Run Out", "Run\n", None, 3]
)
def test_bad_sport_is_refused(bad: object) -> None:
    refused(lambda: parse_publish_fields(pub(sport=bad)), "the sport is malformed")


def test_sport_format_admits_unlisted_but_well_formed_labels() -> None:
    assert parse_publish_fields(pub(sport="R" + "a" * 31)).sport == "R" + "a" * 31


def test_non_string_text_fields_are_refused() -> None:
    refused(lambda: parse_publish_fields(pub(title=5)))
    refused(lambda: parse_publish_fields(pub(description=None)))


def test_any_extra_or_missing_field_is_refused() -> None:
    msg = "the fields are not exactly the expected set"
    refused(lambda: parse_publish_fields({**pub(), "extra": 1}), msg)
    refused(
        lambda: parse_publish_fields({k: v for k, v in pub().items() if k != "title"}),
        msg,
    )
    refused(lambda: parse_publish_fields(upl()), msg)
    refused(lambda: parse_upload_fields({**upl(), "extra": 1}), msg)
    refused(lambda: parse_upload_fields(pub()), msg)
    refused(
        lambda: parse_upload_fields({k: v for k, v in upl().items() if k != "fit"}), msg
    )
    refused(lambda: parse_publish_fields([]), msg)  # type: ignore[arg-type]


@pytest.mark.parametrize("not_a_mapping", [None, 7])
def test_a_non_mapping_is_refused_not_iterated(not_a_mapping: object) -> None:
    msg = "the fields are not exactly the expected set"
    refused(lambda: parse_publish_fields(not_a_mapping), msg)  # type: ignore[arg-type]
    refused(lambda: parse_upload_fields(not_a_mapping), msg)  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["elapsed_s", "distance_m"])
def test_an_integer_too_large_for_a_float_is_refused(name: str) -> None:
    msg = "a number is not null or a finite non-negative number"
    refused(lambda: parse_publish_fields(pub(**{name: 10**400})), msg)
    refused(lambda: publish_fields(facts(**{name: 10**400})), msg)


# --------------------------------------------------------------------------- #
# The file
# --------------------------------------------------------------------------- #

FIT_MSG = "the file is not base64, is too large or is not a FIT file"


def fit_of(size: int, marker: bytes = b".FIT") -> bytes:
    return b"\x0e\x10\x00\x00\x00\x00\x00\x00" + marker + b"\x00" * (size - 12)


def test_file_bound_is_inclusive() -> None:
    at_bound = fit_of(16 * 1024 * 1024)
    assert parse_upload_fields(upload_fields(facts(), at_bound))[1] == at_bound
    over = fit_of(16 * 1024 * 1024 + 1)
    refused(lambda: upload_fields(facts(), over), FIT_MSG)
    encoded = base64.b64encode(over).decode("ascii")
    refused(lambda: parse_upload_fields(upl(fit=encoded)), FIT_MSG)


def test_minimal_file_is_twelve_bytes() -> None:
    assert parse_upload_fields(upload_fields(facts(), fit_of(12)))[1] == fit_of(12)
    refused(lambda: upload_fields(facts(), fit_of(12)[:11]), FIT_MSG)


def test_file_without_the_marker_is_refused() -> None:
    for bad in (fit_of(20, b".FIX"), b".FIT" + b"\x00" * 16, b"\x00" * 20, b""):
        _refuse_file(bad)


def _refuse_file(bad: bytes) -> None:
    refused(lambda: upload_fields(facts(), bad), FIT_MSG)
    encoded = base64.b64encode(bad).decode("ascii")
    refused(lambda: parse_upload_fields(upl(fit=encoded)), FIT_MSG)


@pytest.mark.parametrize(
    "bad",
    [
        "not base64!",
        "abc",
        "====",
        base64.urlsafe_b64encode(b"\xfb\xff\xfe" * 8).decode(),
        5,
        None,
    ],
)
def test_undecodable_file_is_refused(bad: object) -> None:
    refused(lambda: parse_upload_fields(upl(fit=bad)), FIT_MSG)


def _refuse_encoded(bad: str) -> None:
    refused(lambda: parse_upload_fields(upl(fit=bad)), FIT_MSG)


def test_base64_with_stray_characters_is_refused() -> None:
    good = base64.b64encode(FIT).decode("ascii")
    assert parse_upload_fields(upl(fit=good))[1] == FIT
    for bad in (good[:4] + "\n" + good[4:], good[:4] + " " + good[4:], good + "\n"):
        _refuse_encoded(bad)


def test_non_bytes_file_is_refused() -> None:
    refused(lambda: upload_fields(facts(), "text"), FIT_MSG)  # type: ignore[arg-type]
    lookalike = bytearray(fit_of(20))
    assert len(lookalike) >= 12 and lookalike[8:12] == b".FIT"
    refused(lambda: upload_fields(facts(), lookalike), FIT_MSG)  # type: ignore[arg-type]


def test_sampled_errors_do_not_interpolate_the_input() -> None:
    secret = "SECRET-TOKEN-xyz"
    for call in (
        lambda: parse_publish_fields(pub(title=secret + "\x00")),
        lambda: parse_publish_fields(pub(start=secret)),
        lambda: parse_publish_fields(pub(sport=secret)),
        lambda: parse_publish_fields(pub(publication_id=secret)),
        lambda: parse_upload_fields(upl(fit=secret)),
        lambda: parse_publish_fields({**pub(), secret: 1}),
        lambda: target_route(secret, "publish"),
        lambda: connect_page_path("strava", secret),
    ):
        assert secret not in refused(call)


# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #


def test_module_imports_only_stdlib_and_relative_siblings() -> None:
    tree = ast.parse(Path(rt.__file__).read_text(encoding="utf-8"))
    absolute: set[str] = set()
    relative: list[tuple[int, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            absolute.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                assert node.module is not None
                absolute.add(node.module.split(".")[0])
            else:
                relative.append((node.level, node.module))
    assert absolute, "the walk found no imports; it is looking at the wrong file"
    assert absolute <= {
        "__future__",
        "base64",
        "binascii",
        "collections",
        "dataclasses",
        "datetime",
        "math",
        "re",
        "typing",
        "unicodedata",
    }
    assert "fitdocs" not in absolute
    assert relative == [(1, "relay_envelope")]
