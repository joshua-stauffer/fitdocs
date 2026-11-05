"""The Garmin connector's activity download and archive reading (garmin-connector
task 3.5; Req 5.1-5.7, 6.1-6.3, 6.5-6.8).

Everything runs against a scripted transport with zip archives built in memory
by ``zipfile``: no network, a synthetic key, a synthetic token.
"""

from __future__ import annotations

import contextlib
import io
import json
import struct
import zipfile
import zlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import pytest

import fitdocs.connectors.garmin as garmin_module
from fitdocs.connectors.credentials import env_var_name
from fitdocs.connectors.errors import AuthFailure, AuthFailureKind, ConnectorError
from fitdocs.connectors.garmin import GarminConnector, GarminDownloadError
from fitdocs.connectors.http import (
    RETRYABLE_STATUSES,
    HttpRequest,
    HttpResponse,
    TransportError,
)
from fitdocs.connectors.protocol import (
    Declined,
    Fetched,
    RemoteActivity,
    SettingsContext,
)
from fitdocs.connectors.pull import PullOptions, run_pull
from fitdocs.connectors.secrets import Redactor
from fitdocs.connectors.settings import load_connectors_settings
from tests.connectors.test_garmin import (
    _KEY,
    _MARKER,
    _TOKEN,
    _entry,
    _Pull,
    _text,
    _token_ok,
)
from tests.fixtures import builder

_FIT = builder.run_fit_bytes()
_OTHER_FIT = builder.ride_fit_bytes()
_GPX = b'<?xml version="1.0"?>\n<gpx version="1.1"><trk/></gpx>'
_TCX = (
    b'<?xml version="1.0"?>\n'
    b"<TrainingCenterDatabase><Activities/></TrainingCenterDatabase>"
)
_ACTIVITY = RemoteActivity(remote_id="4001", original_available=True)
_ZIP_ACCEPT = "application/zip, application/x-zip-compressed, application/octet-stream"
_FILE_URL = (
    "https://personal.connectapi.garmin.com/download-service/files/activity/4001"
)
_CLOCK = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def _zip(*members: tuple[str, bytes], method: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=method) as archive:
        for name, data in members:
            archive.writestr(name, data)
    return buffer.getvalue()


def _download(archive: bytes) -> HttpResponse:
    return _text(archive)


def _fetch(
    *answers: HttpResponse | TransportError,
    root: Path = Path("/nonexistent-data-root"),
) -> tuple[_Pull, object]:
    pull = _Pull([_token_ok(), *answers], data_root=root)
    return pull, GarminConnector().fetch_activity(pull.session, _ACTIVITY)


def _failure(
    *answers: HttpResponse | TransportError,
) -> tuple[_Pull, Exception]:
    pull = _Pull([_token_ok(), *answers])
    with pytest.raises(Exception) as excinfo:
        GarminConnector().fetch_activity(pull.session, _ACTIVITY)
    return pull, excinfo.value


def _declined(archive: bytes) -> str:
    _, result = _fetch(_download(archive))
    assert isinstance(result, Declined)
    return result.reason


def _per_activity(error: Exception) -> None:
    """The engine ends an instance for these two and fails one activity for any
    other exception."""
    assert not isinstance(error, ConnectorError | AuthFailure)


# --------------------------------------------------------------------------
# The request (Req 5.1; design "Service routes")
# --------------------------------------------------------------------------


def test_the_download_is_one_get_of_the_files_route_with_the_zip_accept_types() -> None:
    pull, result = _fetch(_download(_zip(("a.fit", _FIT))))
    assert result == Fetched(_FIT)
    [download] = pull.gets()
    assert download.url == _FILE_URL
    assert download.headers["Accept"] == _ZIP_ACCEPT
    assert set(download.secret_headers) == {"Authorization"}
    assert download.secret_headers["Authorization"].reveal() == f"Bearer {_TOKEN}"
    assert _TOKEN not in download.url
    assert _TOKEN not in repr(download.headers)
    assert download.single_attempt is False
    assert len(pull.fake.requests) == 2  # the token, then the one download
    assert pull.redacted_at_get == [True]


def test_the_identifier_is_url_encoded_in_the_path() -> None:
    activity = RemoteActivity(remote_id="40/01 ?x", original_available=True)
    pull = _Pull([_token_ok(), _download(_zip(("a.fit", _FIT)))])
    GarminConnector().fetch_activity(pull.session, activity)
    [download] = pull.gets()
    assert urlsplit(download.url).path == (
        "/download-service/files/activity/40%2F01%20%3Fx"
    )
    assert urlsplit(download.url).query == ""


# --------------------------------------------------------------------------
# The archive table (Req 5.2-5.4, 5.7)
# --------------------------------------------------------------------------


def test_one_fit_member_is_handed_over_byte_for_byte() -> None:
    _, result = _fetch(_download(_zip(("4001_ACTIVITY.fit", _FIT))))
    assert isinstance(result, Fetched)
    assert result.data == _FIT
    assert len(_FIT) > 100


@pytest.mark.parametrize("fit_first", [True, False], ids=["fit-first", "fit-second"])
def test_one_fit_member_beside_other_members_is_handed_over_wherever_it_sits(
    fit_first: bool,
) -> None:
    others = [("route.gpx", _GPX), ("notes.txt", b"plain text"), ("empty", b"")]
    members = (
        [("device.fit", _FIT), *others]
        if fit_first
        else [*others, ("device.fit", _FIT)]
    )
    _, result = _fetch(_download(_zip(*members)))
    assert result == Fetched(_FIT)


def test_a_directory_entry_and_a_zero_byte_member_are_no_fit_file() -> None:
    reason = _declined(_zip(("folder/", b""), ("folder/zero.fit", b"")))
    assert reason == garmin_module.NO_FIT_MESSAGE
    assert "GPX" not in reason and "TCX" not in reason


def test_a_member_is_a_fit_file_by_its_content_whatever_it_is_named() -> None:
    # Named like a document but holding FIT, beside a member named like FIT
    # holding a document: a name-based classifier delivers the wrong bytes or
    # declines.
    archive = _zip(("x.fit", _GPX), ("activity.gpx", _FIT))
    _, result = _fetch(_download(archive))
    assert result == Fetched(_FIT)


def test_a_member_named_like_a_path_traversal_is_delivered_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "work" / "deeper"
    work.mkdir(parents=True)
    monkeypatch.chdir(work)
    spied: list[str] = []

    def refuse(self: zipfile.ZipFile, *args: object, **kwargs: object) -> str:
        spied.append("extract")
        raise AssertionError("the module extracts nothing")

    monkeypatch.setattr(zipfile.ZipFile, "extract", refuse)
    monkeypatch.setattr(zipfile.ZipFile, "extractall", refuse)

    def tree() -> dict[str, int]:
        return {
            str(path.relative_to(tmp_path)): path.stat().st_size
            for path in sorted(tmp_path.rglob("*"))
            if path.is_file()
        }

    archive = _zip(
        ("../../evil.fit", _FIT),
        ("/abs/path/evil.gpx", _GPX),
        ("..\\..\\evil2.tcx", _TCX),
    )
    before = tree()
    _, result = _fetch(_download(archive), root=tmp_path)
    assert result == Fetched(_FIT)
    assert tree() == before == {}
    assert spied == []
    assert not list(tmp_path.parent.glob("evil*"))
    assert not list(tmp_path.glob("**/evil*"))


def test_several_fit_members_are_declined_with_the_count() -> None:
    three = _zip(("a.fit", _FIT), ("b.fit", _OTHER_FIT), ("c.bin", _FIT))
    reason = _declined(three)
    assert "3" in reason and "FIT" in reason
    two = _declined(_zip(("a.fit", _FIT), ("route.gpx", _GPX), ("b.fit", _OTHER_FIT)))
    assert "2" in two and "3" not in two
    assert two != reason


def test_several_fit_members_are_declined_even_when_one_is_over_the_size_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(garmin_module, "MAX_FILE_BYTES", len(_OTHER_FIT) - 1)
    reason = _declined(_zip(("a.fit", _FIT), ("b.fit", _OTHER_FIT)))
    assert "2" in reason


@pytest.mark.parametrize(
    ("members", "named", "not_named"),
    [
        ([("a.gpx", _GPX)], ["GPX"], ["TCX"]),
        ([("a.tcx", _TCX)], ["TCX"], ["GPX"]),
        ([("a.fit", _GPX)], ["GPX"], ["TCX"]),
        ([("a.gpx", b"\xef\xbb\xbf  \n" + _GPX.upper())], ["GPX"], ["TCX"]),
        ([("a.dat", _GPX), ("b.dat", _TCX)], ["GPX", "TCX"], []),
    ],
    ids=["gpx", "tcx", "gpx-named-fit", "gpx-bom-upper", "both"],
)
def test_no_fit_member_with_gpx_or_tcx_names_the_format_by_content(
    members: list[tuple[str, bytes]], named: list[str], not_named: list[str]
) -> None:
    reason = _declined(_zip(*members))
    for word in named:
        assert word in reason
    for word in not_named:
        assert word not in reason
    assert "a.gpx" not in reason and "a.fit" not in reason and ".dat" not in reason
    assert reason != garmin_module.NO_FIT_MESSAGE


@pytest.mark.parametrize(
    "members",
    [
        [],
        [("notes.txt", b"hello"), ("blob.bin", bytes(range(256)))],
        [("route.gpx", b"just some text mentioning <gpx but not starting with <")],
        [("short.fit", _FIT[:11])],
    ],
    ids=["empty-archive", "other-members", "gpx-word-not-document", "short-fit-prefix"],
)
def test_no_fit_member_and_no_document_is_declined_as_holding_no_fit_file(
    members: list[tuple[str, bytes]],
) -> None:
    reason = _declined(_zip(*members))
    assert reason == garmin_module.NO_FIT_MESSAGE
    assert "no FIT file" in reason
    assert "GPX" not in reason and "TCX" not in reason
    for name, _ in members:
        assert name not in reason


def test_a_404_is_declined_as_garmin_holding_no_file() -> None:
    pull, result = _fetch(_text(f"nothing {_MARKER}", 404))
    assert isinstance(result, Declined)
    assert result.reason == garmin_module.NO_FILE_MESSAGE
    assert "holds no file" in result.reason
    assert _MARKER not in result.reason
    assert len(pull.gets()) == 1


# --------------------------------------------------------------------------
# Content is classified from its first bytes only (Req 5.7, 6.5)
# --------------------------------------------------------------------------


def test_a_huge_non_fit_member_is_never_read_past_its_first_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    huge = b"<gpx>" + b"\0" * (8 * 1024 * 1024)
    archive = _zip(("big.gpx", huge), ("device.fit", _FIT))
    assert len(archive) < 64 * 1024
    returned: list[int] = []
    real = zipfile.ZipExtFile.read

    def spy(self: zipfile.ZipExtFile, n: int | None = -1) -> bytes:
        data = real(self, n)
        returned.append(len(data))
        return data

    monkeypatch.setattr(zipfile.ZipExtFile, "read", spy)
    _, result = _fetch(_download(archive))
    assert result == Fetched(_FIT)
    assert len(huge) > 8 * 1024 * 1024
    # The FIT member is read in full (classification head, then the member);
    # the 8 MiB member contributes at most its first kilobyte.
    assert sum(returned) <= len(_FIT) + len(_FIT) + 1024 + 1
    assert max(returned) <= 1024


def test_a_huge_non_fit_member_never_counts_against_the_size_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(garmin_module, "MAX_FILE_BYTES", len(_FIT))
    archive = _zip(("big.gpx", _GPX + b"\0" * (4 * len(_FIT))), ("a.fit", _FIT))
    _, result = _fetch(_download(archive))
    assert result == Fetched(_FIT)


# --------------------------------------------------------------------------
# The size bound (Req 5.6)
# --------------------------------------------------------------------------


def test_a_fit_member_of_exactly_the_bound_is_handed_over_and_one_more_byte_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(garmin_module, "MAX_FILE_BYTES", len(_FIT))
    _, result = _fetch(_download(_zip(("a.fit", _FIT))))
    assert result == Fetched(_FIT)
    monkeypatch.setattr(garmin_module, "MAX_FILE_BYTES", len(_FIT) - 1)
    _, error = _failure(_download(_zip(("a.fit", _FIT))))
    assert type(error) is GarminDownloadError
    _per_activity(error)
    assert str(len(_FIT) - 1) in str(error)


def test_a_bomb_sized_fit_member_is_stopped_by_the_read_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limit = 64 * 1024
    monkeypatch.setattr(garmin_module, "MAX_FILE_BYTES", limit)
    bomb = _FIT[:14] + b"\0" * (6 * 1024 * 1024)
    archive = _zip(("bomb.fit", bomb))
    assert len(archive) < limit
    returned: list[int] = []
    real = zipfile.ZipExtFile.read

    def spy(self: zipfile.ZipExtFile, n: int | None = -1) -> bytes:
        data = real(self, n)
        returned.append(len(data))
        return data

    monkeypatch.setattr(zipfile.ZipExtFile, "read", spy)
    _, error = _failure(_download(archive))
    assert type(error) is GarminDownloadError
    assert returned and sum(returned) > limit  # the bound was reached...
    assert max(returned) <= limit + 1  # ...and never read past
    assert sum(returned) <= limit + 1 + 1024


def test_a_header_that_lies_about_the_size_never_hands_over_bytes() -> None:
    stored = _zip(("a.fit", _FIT), method=zipfile.ZIP_STORED)
    central = stored.index(b"PK\x01\x02")
    lied = bytearray(stored)
    # Central directory entry: uncompressed size sits 24 bytes in.
    struct.pack_into("<I", lied, central + 24, 20)
    with zipfile.ZipFile(io.BytesIO(bytes(lied))) as archive:
        assert archive.infolist()[0].file_size == 20 != len(_FIT)
    _, error = _failure(_download(bytes(lied)))
    assert type(error) is GarminDownloadError


# --------------------------------------------------------------------------
# An archive that cannot be read (Req 5.6, 6.8)
# --------------------------------------------------------------------------


def _flip(archive: bytes, needle: bytes, offset: int) -> bytes:
    """``archive`` with one byte changed ``offset`` bytes into ``needle``'s
    first appearance."""
    at = archive.index(needle) + offset
    changed = bytearray(archive)
    changed[at] ^= 0x01
    return bytes(changed)


def _set_flag_bit_zero(archive: bytes) -> bytes:
    changed = bytearray(archive)
    local = archive.index(b"PK\x03\x04")
    central = archive.index(b"PK\x01\x02")
    changed[local + 6] |= 0x01
    changed[central + 8] |= 0x01
    return bytes(changed)


def _unknown_method(archive: bytes) -> bytes:
    changed = bytearray(archive)
    struct.pack_into("<H", changed, archive.index(b"PK\x03\x04") + 8, 99)
    struct.pack_into("<H", changed, archive.index(b"PK\x01\x02") + 10, 99)
    return bytes(changed)


def _unreadable_archives() -> dict[str, tuple[bytes, type[BaseException]]]:
    stored = _zip(("a.fit", _FIT), method=zipfile.ZIP_STORED)
    deflated = _zip(("a.fit", _FIT))
    return {
        "empty-body": (b"", zipfile.BadZipFile),
        "garbage": (f"<html>{_MARKER}</html>".encode(), zipfile.BadZipFile),
        "json-error": (json.dumps({"error": _MARKER}).encode(), zipfile.BadZipFile),
        "truncated": (stored[: len(stored) // 2], zipfile.BadZipFile),
        "crc-failure": (_flip(stored, _FIT, 100), zipfile.BadZipFile),
        "corrupt-deflate": (_flip(deflated, b"a.fit", 5 + 30), zlib.error),
        "encrypted": (_set_flag_bit_zero(stored), RuntimeError),
        "unknown-compression": (_unknown_method(stored), NotImplementedError),
    }


@pytest.mark.parametrize("case", sorted(_unreadable_archives()))
def test_an_archive_that_cannot_be_read_is_a_per_activity_failure(case: str) -> None:
    archive, raised = _unreadable_archives()[case]
    # The precondition: Python itself refuses this archive, in this way.
    with pytest.raises(raised), zipfile.ZipFile(io.BytesIO(archive)) as opened:
        for info in opened.infolist():
            opened.open(info).read()
    pull, error = _failure(_download(archive))
    assert type(error) is GarminDownloadError
    _per_activity(error)
    text = f"{error} {error!r}"
    assert _MARKER not in text
    assert "a.fit" not in text
    assert error.__cause__ is None and error.__suppress_context__
    assert "ZIP" in str(error)
    assert len(pull.gets()) == 1


@pytest.mark.parametrize(
    "exc",
    [
        zipfile.BadZipFile,
        zlib.error,
        EOFError,
        RuntimeError,
        NotImplementedError,
        OSError,
    ],
)
def test_each_way_the_zip_reader_fails_is_a_per_activity_failure_that_quotes_nothing(
    exc: type[Exception], monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _download(_zip(("a.fit", _FIT)))

    def refuse(self: zipfile.ZipFile, *args: object, **kwargs: object) -> object:
        raise exc(f"secret detail {_MARKER} a.fit")

    monkeypatch.setattr(zipfile.ZipFile, "open", refuse)
    _, error = _failure(archive)
    assert type(error) is GarminDownloadError
    assert _MARKER not in f"{error} {error!r}"
    assert error.__cause__ is None and error.__suppress_context__


def test_a_failed_read_of_the_zip_directory_is_also_a_per_activity_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError(f"disk {_MARKER}")

    archive = _download(_zip(("a.fit", _FIT)))
    monkeypatch.setattr(zipfile.ZipFile, "infolist", refuse)
    _, error = _failure(archive)
    assert type(error) is GarminDownloadError
    assert _MARKER not in f"{error} {error!r}"


# --------------------------------------------------------------------------
# Statuses (Req 6.1, 6.2, 6.3, 6.5, 6.7, 6.8)
# --------------------------------------------------------------------------


def test_a_401_ends_the_instance_as_a_rejected_key_with_the_new_key_step() -> None:
    pull, error = _failure(
        _text(f"no {_MARKER}", 401), _download(_zip(("a.fit", _FIT)))
    )
    assert isinstance(error, AuthFailure)
    assert error.kind is AuthFailureKind.REJECTED
    assert "Create a new key on Garmin Connect" in error.service_message
    assert "`fitdocs connect`" in error.service_message
    assert "401" in error.service_message
    assert _MARKER not in error.service_message
    assert len(pull.gets()) == 1


def test_a_403_ends_the_instance_as_a_refusal_that_is_no_fitdocs_bug() -> None:
    pull, error = _failure(
        _text(f"no {_MARKER}", 403), _download(_zip(("a.fit", _FIT)))
    )
    assert isinstance(error, AuthFailure)
    assert error.kind is AuthFailureKind.REJECTED
    message = error.service_message
    assert "refused" in message and "download" in message
    assert "terms" in message and "Garmin Connect" in message
    assert "bug" not in message.lower()
    assert "403" in message
    assert _MARKER not in message
    assert len(pull.gets()) == 1


def test_a_429_past_the_waits_ends_the_instance_as_rate_limited() -> None:
    answers = [_text(f"slow {_MARKER}", 429, **{"retry-after": "9999"})]
    pull, error = _failure(*answers, _download(_zip(("a.fit", _FIT))))
    assert isinstance(error, AuthFailure)
    assert error.kind is AuthFailureKind.RATE_LIMITED
    assert "429" in error.service_message
    assert "next pull resumes" in error.service_message
    assert _MARKER not in error.service_message
    assert len(pull.gets()) == 1


@pytest.mark.parametrize("status", [500, 502, 503, 504, 599])
def test_a_server_error_past_the_retries_fails_the_one_activity_naming_the_status(
    status: int,
) -> None:
    pull, error = _failure(*[_text(f"oops {_MARKER}", status)] * 3)
    assert type(error) is GarminDownloadError
    _per_activity(error)
    assert f"HTTP {status}" in str(error)
    assert _MARKER not in f"{error} {error!r}"
    assert len(pull.gets()) == (3 if status in RETRYABLE_STATUSES else 1)


@pytest.mark.parametrize("status", [400, 410, 418, 422, 204, 301, 302, 451])
def test_any_other_status_fails_the_one_activity_naming_the_status(status: int) -> None:
    pull, error = _failure(_text(f"odd {_MARKER}", status))
    assert type(error) is GarminDownloadError
    _per_activity(error)
    assert f"HTTP {status}" in str(error)
    assert _MARKER not in f"{error} {error!r}"
    assert len(pull.gets()) == 1


def test_a_200_that_is_not_an_archive_never_quotes_the_body() -> None:
    _, error = _failure(_text(f"<html>{_MARKER}</html>"))
    assert type(error) is GarminDownloadError
    assert _MARKER not in f"{error} {error!r}"


def test_a_failure_to_mint_the_token_is_the_listings_instance_ending_error() -> None:
    pull = _Pull([_text("no", 503)])
    with pytest.raises(ConnectorError):
        GarminConnector().fetch_activity(pull.session, _ACTIVITY)
    assert pull.gets() == []


# --------------------------------------------------------------------------
# Five in a row (Req 6.6)
# --------------------------------------------------------------------------


def _outage(status: int = 503) -> list[HttpResponse | TransportError]:
    """One download that meets a server error on every attempt."""
    return [_text(f"down {_MARKER}", status)] * 3


def _unreachable() -> list[HttpResponse | TransportError]:
    return [
        TransportError("ConnectError to https://personal.connectapi.garmin.com")
    ] * 3


class _Run:
    """Several downloads in one pull, on one connector."""

    def __init__(self, script: list[HttpResponse | TransportError]) -> None:
        self.pull = _Pull([_token_ok(), *script])
        self.connector = GarminConnector()

    def fetch(self) -> object:
        return self.connector.fetch_activity(self.pull.session, _ACTIVITY)


def test_the_fifth_failed_download_in_a_row_ends_the_activity_pull() -> None:
    run = _Run([r for _ in range(6) for r in _outage()])
    for _ in range(4):
        with pytest.raises(GarminDownloadError):
            run.fetch()
    with pytest.raises(ConnectorError) as stopped:
        run.fetch()
    error = stopped.value
    assert type(error) is ConnectorError
    assert error.args == (garmin_module.UNAVAILABLE_STOP_MESSAGE,)
    assert "appears unavailable" in str(error)
    assert "next pull resumes" in str(error)
    assert _MARKER not in str(error)
    assert len(run.pull.gets()) == 15


@pytest.mark.parametrize("status", [501, 505, 599])
def test_every_server_error_status_counts_toward_the_five_in_a_row(
    status: int,
) -> None:
    run = _Run([_text(f"down {_MARKER}", status)] * 5)
    for _ in range(4):
        with pytest.raises(GarminDownloadError):
            run.fetch()
    with pytest.raises(ConnectorError) as stopped:
        run.fetch()
    assert stopped.value.args == (garmin_module.UNAVAILABLE_STOP_MESSAGE,)
    assert len(run.pull.gets()) == 5


def test_transport_failures_count_with_server_errors_and_reach_the_engine_bare() -> (
    None
):
    run = _Run(
        [
            *_unreachable(),
            *_outage(500),
            *_unreachable(),
            *_outage(502),
            *_unreachable(),
        ]
    )
    with pytest.raises(TransportError) as first:
        run.fetch()
    _per_activity(first.value)
    with pytest.raises(GarminDownloadError):
        run.fetch()
    with pytest.raises(TransportError):
        run.fetch()
    with pytest.raises(GarminDownloadError):
        run.fetch()
    with pytest.raises(ConnectorError) as stopped:
        run.fetch()
    assert stopped.value.args == (garmin_module.UNAVAILABLE_STOP_MESSAGE,)


def test_five_transport_failures_alone_end_the_activity_pull() -> None:
    run = _Run([r for _ in range(5) for r in _unreachable()])
    for _ in range(4):
        with pytest.raises(TransportError):
            run.fetch()
    with pytest.raises(ConnectorError) as stopped:
        run.fetch()
    assert stopped.value.args == (garmin_module.UNAVAILABLE_STOP_MESSAGE,)


def _good() -> list[HttpResponse | TransportError]:
    return [_download(_zip(("a.fit", _FIT)))]


_RESETTING: dict[str, list[HttpResponse | TransportError]] = {
    "success": _good(),
    "no-file": [_text("none", 404)],
    "declined-archive": [_download(_zip(("a.gpx", _GPX)))],
    "unreadable-archive": [_download(b"not a zip")],
    "other-status": [_text("bad", 400)],
    "waited-out-429": [_text("slow", 429, **{"retry-after": "7"}), *_good()],
}


@pytest.mark.parametrize("breaker", sorted(_RESETTING))
def test_the_count_starts_again_after_a_reset_and_stops_on_the_fifth_after_it(
    breaker: str,
) -> None:
    run = _Run(
        [
            *[r for _ in range(4) for r in _outage()],
            *_RESETTING[breaker],
            *[r for _ in range(5) for r in _outage()],
        ]
    )
    for _ in range(4):
        with pytest.raises(GarminDownloadError):
            run.fetch()
    with contextlib.suppress(GarminDownloadError):
        run.fetch()
    for _ in range(4):
        with pytest.raises(GarminDownloadError):
            run.fetch()
    with pytest.raises(ConnectorError) as stopped:
        run.fetch()
    assert stopped.value.args == (garmin_module.UNAVAILABLE_STOP_MESSAGE,)


def test_the_count_belongs_to_the_pull_not_the_connector() -> None:
    connector = GarminConnector()
    first = _Pull([_token_ok(), *[r for _ in range(4) for r in _outage()]])
    for _ in range(4):
        with pytest.raises(GarminDownloadError):
            connector.fetch_activity(first.session, _ACTIVITY)
    second = _Pull([_token_ok(), *_outage()])
    with pytest.raises(GarminDownloadError):
        connector.fetch_activity(second.session, _ACTIVITY)


# --------------------------------------------------------------------------
# A FIT member as long as a real one, past the classifying read (Req 5.2, 5.6)
# --------------------------------------------------------------------------

_BIG_FIT = _FIT + bytes(range(256)) * 16


@pytest.mark.parametrize(
    "method", [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED], ids=["stored", "deflated"]
)
def test_a_fit_member_longer_than_the_classifying_read_is_handed_over_whole(
    method: int,
) -> None:
    assert len(_BIG_FIT) > garmin_module.DOCUMENT_SNIFF_BYTES
    _, result = _fetch(_download(_zip(("a.fit", _BIG_FIT), method=method)))
    assert result == Fetched(_BIG_FIT)


def test_a_crc_failure_past_the_classifying_read_fails_the_activity() -> None:
    stored = _zip(("a.fit", _BIG_FIT), method=zipfile.ZIP_STORED)
    past = garmin_module.DOCUMENT_SNIFF_BYTES + 100
    _, error = _failure(_download(_flip(stored, _BIG_FIT, past)))
    assert type(error) is GarminDownloadError


@pytest.mark.parametrize("fit_first", [True, False], ids=["fit-first", "fit-second"])
def test_a_member_that_cannot_be_read_fails_the_activity_beside_a_good_fit_member(
    fit_first: bool,
) -> None:
    # The unreadable member may be a second FIT file, so "exactly one" is not
    # established (Req 5.2, 5.3, 5.6).
    fit = ("a.fit", _FIT)
    side = ("side.bin", _OTHER_FIT)
    good = _zip(*([fit, side] if fit_first else [side, fit]), method=zipfile.ZIP_STORED)
    _, error = _failure(_download(_flip(good, _OTHER_FIT, 100)))
    assert type(error) is GarminDownloadError
    _per_activity(error)


# --------------------------------------------------------------------------
# Members are entries, never names (Req 5.7)
# --------------------------------------------------------------------------


def _same_name(*contents: bytes) -> bytes:
    with pytest.warns(UserWarning, match="Duplicate name"):
        return _zip(*[("same.fit", data) for data in contents])


@pytest.mark.parametrize(
    "contents", [(_FIT, _GPX), (_GPX, _FIT)], ids=["fit-first", "fit-last"]
)
def test_members_sharing_a_name_are_read_by_entry(
    contents: tuple[bytes, bytes],
) -> None:
    _, result = _fetch(_download(_same_name(*contents)))
    assert result == Fetched(_FIT)


def test_two_fit_members_sharing_a_name_are_two_and_the_name_is_not_quoted() -> None:
    reason = _declined(_same_name(_FIT, _OTHER_FIT))
    assert "2" in reason
    assert "same.fit" not in reason


def test_a_document_root_in_the_classifying_read_is_named_and_one_past_it_is_not() -> (
    None
):
    near = b"<!--" + b"x" * 900 + b"-->" + _GPX
    assert "GPX" in _declined(_zip(("a.dat", near)))
    far = b"<!--" + b"x" * 1100 + b"-->" + _GPX
    assert _declined(_zip(("a.dat", far))) == garmin_module.NO_FIT_MESSAGE


def test_reading_an_archive_opens_no_file(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("the archive is read in memory")

    pull = _Pull(
        [_token_ok(), _download(_zip(("a.fit", _FIT), ("route.gpx", _GPX)))],
    )
    with monkeypatch.context() as patched:
        patched.setattr("builtins.open", refuse)
        patched.setattr("os.open", refuse)
        result = GarminConnector().fetch_activity(pull.session, _ACTIVITY)
    assert result == Fetched(_FIT)


# --------------------------------------------------------------------------
# A download goes through the pull's spacing and waits (Req 6.3, 4.1, 4.7)
# --------------------------------------------------------------------------


def test_a_download_answered_429_is_waited_out_and_repeated() -> None:
    pull = _Pull(
        [
            _token_ok(),
            _text("slow", 429, **{"retry-after": "7"}),
            _download(_zip(("a.fit", _FIT))),
        ]
    )
    result = GarminConnector().fetch_activity(pull.session, _ACTIVITY)
    assert result == Fetched(_FIT)
    assert len(pull.gets()) == 2
    assert pull.sleeps == [1.0, 7.0]


def test_downloads_are_spaced_by_the_pull() -> None:
    run = _Run([*_good(), *_good()])
    run.fetch()
    run.fetch()
    assert run.pull.sleeps == [1.0, 1.0]


# --------------------------------------------------------------------------
# What the ZIP reader raises outside the design's list (Req 5.6, 6.8)
# --------------------------------------------------------------------------


def _flagged_name_not_utf8() -> bytes:
    stored = _zip(("a.fit", _FIT), method=zipfile.ZIP_STORED)
    changed = bytearray(stored)
    local = stored.index(b"PK\x03\x04")
    central = stored.index(b"PK\x01\x02")
    struct.pack_into("<H", changed, local + 6, 0x800)
    struct.pack_into("<H", changed, central + 8, 0x800)
    changed[local + 30] = 0xFF
    changed[central + 46] = 0xFF
    return bytes(changed)


def _central_directory_offset_past_the_file() -> bytes:
    stored = _zip(("a.fit", _FIT), method=zipfile.ZIP_STORED)
    changed = bytearray(stored)
    end = stored.index(b"PK\x05\x06")
    struct.pack_into("<I", changed, end + 16, len(stored) + 1000)
    return bytes(changed)


def _corrupt_lzma() -> bytes:
    packed = _zip(("a.fit", _BIG_FIT), method=zipfile.ZIP_LZMA)
    return _flip(packed, b"a.fit", 5 + 30)


@pytest.mark.parametrize(
    "archive",
    [_flagged_name_not_utf8, _central_directory_offset_past_the_file, _corrupt_lzma],
    ids=["flagged-name-not-utf8", "negative-seek", "corrupt-lzma"],
)
def test_every_other_way_the_reader_refuses_an_archive_is_in_the_connectors_own_words(
    archive: Callable[[], bytes],
) -> None:
    _, error = _failure(_download(archive()))
    assert type(error) is GarminDownloadError
    assert str(error) == garmin_module.ARCHIVE_UNREADABLE_MESSAGE


# --------------------------------------------------------------------------
# Through the engine (Req 5.3-5.6, 6.5, 6.6)
# --------------------------------------------------------------------------


def _engine(
    tmp_path: Path,
    answers: dict[str, Callable[[], list[HttpResponse | TransportError]]],
) -> object:
    """Pull an instance whose listing holds ``answers``' identifiers, with one
    scripted download per activity (re-attempts consume more of its list)."""
    pending = {key: list(value()) for key, value in answers.items()}
    entries = [
        _entry(int(key), gmt=f"2026-03-0{index + 1} 08:00:00")
        for index, key in enumerate(sorted(answers))
    ]

    def transport(request: HttpRequest, timeout: float) -> HttpResponse:
        if request.method == "POST":
            return _token_ok()
        path = urlsplit(request.url).path
        if path.endswith("/search/activities"):
            return _text(json.dumps(entries))
        outcome = pending[path.rsplit("/", 1)[1]].pop(0)
        if isinstance(outcome, TransportError):
            raise outcome
        return outcome

    instances = load_connectors_settings(
        {"connectors": {"garmin": {}}},
        settings_file=tmp_path / "fitdocs.toml",
        context=SettingsContext(data_root=tmp_path, inbox=tmp_path / "inbox"),
    )
    return run_pull(
        tmp_path,
        instances,
        inbox=tmp_path / "inbox",
        store=None,
        transport=transport,
        options=PullOptions(since=None, dry_run=False),
        environ={env_var_name("garmin", "api_key"): _KEY},
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=Redactor(),
    )


def test_the_engine_records_each_outcome_of_the_archive_table(tmp_path: Path) -> None:
    report = _engine(
        tmp_path,
        {
            "1001": lambda: [_download(_zip(("a.gpx", _GPX), ("a.fit", _FIT)))],
            "1002": lambda: [_download(_zip(("a.fit", _FIT), ("b.fit", _OTHER_FIT)))],
            "1003": lambda: [_download(_zip(("a.tcx", _TCX)))],
            "1004": lambda: [_text("no", 404)],
            "1005": lambda: [_download(b"not a zip")],
            "1006": lambda: [_text("odd", 400)],
        },
    )
    [instance] = report.instances  # type: ignore[attr-defined]
    assert instance.error is None
    assert [d.remote_id for d in instance.delivered] == ["1001"]
    skipped = {note.subject: note.detail for note in instance.skipped}
    assert sorted(skipped) == ["1002", "1003", "1004"]
    assert "2" in skipped["1002"] and "TCX" in skipped["1003"]
    assert skipped["1004"] == garmin_module.NO_FILE_MESSAGE
    failed = {note.subject: note.detail for note in instance.failed}
    assert sorted(failed) == ["1005", "1006"]
    assert failed["1005"].startswith("GarminDownloadError: ")
    assert "HTTP 400" in failed["1006"]
    assert not any(
        "not a zip" in text for text in [*failed.values(), *skipped.values()]
    )
    delivered = sorted((tmp_path / "inbox").rglob("*"))
    assert [p.read_bytes() for p in delivered if p.is_file()] == [_FIT]


def test_five_failed_downloads_in_a_row_end_the_instance_through_the_engine(
    tmp_path: Path,
) -> None:
    report = _engine(
        tmp_path,
        {
            "2001": _unreachable,
            "2002": lambda: _outage(),
            "2003": lambda: _outage(500),
            "2004": lambda: _outage(502),
            "2005": lambda: _outage(504),
            "2006": lambda: _good(),
        },
    )
    [instance] = report.instances  # type: ignore[attr-defined]
    assert [note.subject for note in instance.failed] == [
        "2001",
        "2002",
        "2003",
        "2004",
    ]
    assert instance.failed[0].detail.startswith("TransportError: ")
    assert instance.failed[1].detail.startswith("GarminDownloadError: ")
    assert instance.error is not None
    assert "appears unavailable" in instance.error.detail
    assert "next pull resumes" in instance.error.detail
    assert instance.delivered == ()
    assert _MARKER not in instance.error.detail
    assert not any(_MARKER in note.detail for note in instance.failed)
