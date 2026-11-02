"""The intervals.icu connector (design.md "IntervalsConnector").

Lists, filters and fetches intervals.icu originals for the key's own athlete
with a personal API key, and publishes posts: it sets an activity's name and
description, and, for an instance that turns uploads on, uploads the page's
base file once. This module is the one module in the connectors
package that names the service's address (the service-neutral scan admits it
here, in its own tests and in its own documentation section only). It imports only the
standard library and ``fitdocs.connectors.{errors,http,ledger,protocol,secrets}``,
plus ``fitdocs.identity.matching``, imported inside the publish path's
listing-match helper only (so importing the package loads no identity module),
builds no HTTP client of its own, and reads no clock: ``session.now`` is the
only time source.

Task 3.1 declares the connector, its constants and its settings parser; task
3.2 implements the key check, the credential and the service-message helper;
task 3.3 implements the listing, its date windows and entry mapping, and the
status mapping for data calls; task 3.4 implements the file download.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import math
import re
import zlib
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum, StrEnum
from types import MappingProxyType
from typing import Final, NoReturn
from urllib.parse import quote, urlencode

from fitdocs.connectors.errors import (
    AuthFailure,
    AuthFailureKind,
    ConnectorError,
    ConnectorSettingsError,
)
from fitdocs.connectors.http import (
    MAX_RESPONSE_BYTES,
    HttpResponse,
    TransportError,
    auth_failure_from,
)
from fitdocs.connectors.ledger import LedgerError, load_ledger
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    CompletedActivity,
    ConnectorSession,
    CredentialField,
    Declined,
    Fetched,
    FetchResult,
    Granted,
    Listing,
    Post,
    PublishCode,
    PublishRequest,
    PublishResult,
    RemoteActivity,
    SettingsContext,
    WellnessDay,
    WellnessListing,
    WellnessPackage,
)
from fitdocs.connectors.secrets import Secret

INTERVALS_CONNECTOR_ID: Final[str] = "intervals"
API_BASE: Final[str] = "https://intervals.icu/api/v1"
SELF_ATHLETE: Final[str] = "0"
API_KEY_USERNAME: Final[str] = "API_KEY"
DEFAULT_SOURCES: Final[frozenset[str]] = frozenset({"GARMIN_CONNECT"})
STRAVA_SOURCE: Final[str] = "STRAVA"
SOURCE_NAME_PATTERN: Final[str] = r"^[A-Z][A-Z0-9_]{0,63}$"
FIRST_PULL_DAYS: Final[int] = 30
WINDOW_DAYS: Final[int] = 90
LISTING_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "source",
    "start_date",
    "type",
    "elapsed_time",
    "file_type",
)
MAX_FILE_BYTES: Final[int] = MAX_RESPONSE_BYTES
GZIP_MAGIC: Final[bytes] = b"\x1f\x8b"

STRAVA_REASON: Final[str] = (
    "Strava-sourced: intervals.icu returns only a stub for Strava activities "
    "and shares no file for them"
)
NOT_FIT_REASON: Final[str] = (
    "the original is a {format} file, not FIT; fitdocs ingests FIT files only"
)
NO_FILE_REASON: Final[str] = "intervals.icu holds no original file for this activity"
GZIP_UNREADABLE_MESSAGE: Final[str] = (
    "the downloaded file is gzip data that could not be decompressed"
)
GZIP_OVERSIZE_MESSAGE: Final[str] = (
    "the downloaded file expands past the {limit}-byte size limit when decompressed"
)
DOCUMENT_SNIFF_BYTES: Final[int] = 1024
UTF8_BOM: Final[bytes] = b"\xef\xbb\xbf"
RATE_LIMITED_MESSAGE: Final[str] = (
    "intervals.icu is limiting requests (HTTP 429) and still was after "
    "fitdocs's retries; this pull stopped, and the next pull resumes where "
    "it stopped"
)
UNAVAILABLE_MESSAGE: Final[str] = (
    "intervals.icu is unavailable (HTTP {status}) after fitdocs's retries; "
    "this pull stopped, and the next pull resumes where it stopped"
)
LISTING_STATUS_MESSAGE: Final[str] = (
    "intervals.icu answered the activity listing with HTTP {status}: {message}"
)
DOWNLOAD_STATUS_MESSAGE: Final[str] = (
    "intervals.icu answered HTTP {status} for the original file: {message}"
)

LISTING_FORM_MESSAGE: Final[str] = (
    "intervals.icu's activity listing is not in its documented form: {problem}"
)

SERVICE_MESSAGE_BODY_BYTES: Final[int] = 4096
SERVICE_MESSAGE_CHARS: Final[int] = 300

PUBLISH_UPLOAD_KEY: Final[str] = "publish_upload"
LINK_LABEL: Final[str] = "intervals.icu"

_SOURCE_NAME_RE = re.compile(SOURCE_NAME_PATTERN)


@dataclass(frozen=True)
class IntervalsSettings:
    """Validated ``[connectors.<instance>]`` configuration for an
    ``intervals`` instance."""

    sources: frozenset[str]
    """The service-reported recording sources a pull keeps."""

    publish_upload: bool = False
    """Whether a publish may create an activity from the workout's source
    file; off unless the instance's table sets it to ``true``."""


class IntervalsDownloadError(Exception):
    """One activity's download failed; the framework reports it and retries
    it next pull."""


WELLNESS_HISTORY_START: Final[date] = date(2010, 1, 1)
WELLNESS_WINDOW_DAYS: Final[int] = 365
WELLNESS_FORMAT: Final[str] = "intervals-icu"
WELLNESS_SUFFIX: Final[str] = ".json"
WELLNESS_DELIVERY_FORMAT: Final[str] = "fitdocs.intervals-icu-wellness"
WELLNESS_DELIVERY_VERSION: Final[int] = 1
WELLNESS_ID_PATTERN: Final[str] = r"^\d{4}-\d{2}-\d{2}$"
WELLNESS_KEYS_PATTERN: Final[str] = r"^(?:icu_)?([a-z0-9_]+?)_wellness_keys$"
CONTENT_REVISION_PREFIX: Final[str] = "sha256:"
WELLNESS_LISTING_FORM_MESSAGE: Final[str] = (
    "intervals.icu's wellness listing is not in its documented form: {problem}"
)
ATHLETE_FORM_MESSAGE: Final[str] = (
    "intervals.icu's athlete settings are not in their documented form: {problem}"
)
WELLNESS_STATUS_MESSAGE: Final[str] = (
    "intervals.icu answered the {request} with HTTP {status}: {message}"
)
WELLNESS_REFUSED_MESSAGE: Final[str] = (
    "intervals.icu refused the {request} (HTTP 403): {message}. "
    "intervals.icu may be withholding data it received from Garmin. "
    "Set wellness = false in this instance's table to stop requesting wellness; "
    "Garmin's own data export is the route for Garmin wellness "
    "(see the wellness guide)."
)
_WELLNESS_ID_RE = re.compile(WELLNESS_ID_PATTERN)


class IntervalsConnector:
    """intervals.icu originals through a personal API key."""

    connector_id = INTERVALS_CONNECTOR_ID
    display_name = "intervals.icu"
    auth_style = AuthStyle.API_KEY
    capabilities = frozenset(
        {
            Capability.PULL_ACTIVITIES,
            Capability.PULL_WELLNESS,
            Capability.PUSH_ACTIVITY,
            Capability.ANNOTATE_REMOTE_ACTIVITY,
            Capability.RESOLVE_REMOTE_ACTIVITY,
        }
    )
    link_label = LINK_LABEL
    credential_fields = (
        CredentialField(
            "api_key", "intervals.icu API key (Settings, Developer Settings)", True
        ),
    )

    def parse_settings(
        self, table: Mapping[str, object], context: SettingsContext
    ) -> IntervalsSettings:
        """``sources`` (optional): a non-empty list of upper-case source
        names; absent gives :data:`DEFAULT_SOURCES`. A name the published
        vocabulary lacks is accepted. ``publish_upload`` (optional): a
        boolean; absent is ``False``, any other value is refused. Every other
        key is ignored."""
        upload = table.get(PUBLISH_UPLOAD_KEY, False)
        if not isinstance(upload, bool):
            raise ConnectorSettingsError(
                PUBLISH_UPLOAD_KEY,
                f"{PUBLISH_UPLOAD_KEY} must be true or false, got {upload!r}",
            )
        if "sources" not in table:
            return IntervalsSettings(sources=DEFAULT_SOURCES, publish_upload=upload)
        value = table["sources"]
        if not isinstance(value, list) or not value:
            raise _sources_error(value)
        for item in value:
            if not isinstance(item, str) or not _SOURCE_NAME_RE.fullmatch(item):
                raise _sources_error(item)
        return IntervalsSettings(sources=frozenset(value), publish_upload=upload)

    def verify(
        self, session: ConnectorSession, values: Mapping[str, Secret]
    ) -> Granted:
        """One listing request for the key's own athlete (Req 1.2): ``200``
        grants no reported scopes (Req 1.3); every other answer is a failure
        (Req 1.4). One attempt, never retried: the session's client is in
        AUTH mode."""
        newest_day = session.now().astimezone(UTC).date() - timedelta(days=1)
        url = (
            f"{API_BASE}/athlete/{SELF_ATHLETE}/activities"
            f"?oldest={newest_day.isoformat()}&limit=1&fields=id"
        )
        response = session.http.get(
            url, secret_headers=_auth_headers(session, values["api_key"])
        )
        if response.status == 200:
            return Granted(scopes=None)
        message = _service_message(session, response)
        failure = auth_failure_from(response, service_message=message)
        if failure is not None:
            raise failure
        said = _service_text(session, response)
        raise AuthFailure(
            AuthFailureKind.UNAVAILABLE,
            f"HTTP {response.status}: {said}" if said else message,
        )

    def list_activities(
        self, session: ConnectorSession, since: datetime | None
    ) -> Listing:
        """The key's own athlete's activities from ``since`` (Req 3.1-3.8,
        1.5): one request per overlapping date window, each entry mapped in
        response order, a repeated id listed once. ``since`` absent lists the
        last :data:`FIRST_PULL_DAYS` days."""
        settings = session.settings
        if not isinstance(settings, IntervalsSettings):
            raise ConnectorError(
                "the intervals connector was given another connector's settings"
            )
        now = session.now()
        earliest = (
            since.astimezone(UTC)
            if since is not None
            else now.astimezone(UTC) - timedelta(days=FIRST_PULL_DAYS)
        )
        headers = _auth_headers(session, session.credentials.value("api_key"))
        activities: list[RemoteActivity] = []
        taken: set[str] = set()
        for oldest, newest in _windows(earliest, now.astimezone(UTC).date()):
            query = {"oldest": f"{oldest.isoformat()}T00:00:00"}
            if newest is not None:
                query["newest"] = f"{newest.isoformat()}T00:00:00"
            query["fields"] = ",".join(LISTING_FIELDS)
            response = session.http.get(
                f"{API_BASE}/athlete/{SELF_ATHLETE}/activities?{urlencode(query)}",
                secret_headers=headers,
            )
            for index, entry in enumerate(_listing_entries(session, response)):
                activity = _remote_activity(entry, index, settings, earliest)
                if activity is None or activity.remote_id in taken:
                    continue
                taken.add(activity.remote_id)
                activities.append(activity)
        return Listing(activities=tuple(activities))

    def list_wellness(
        self, session: ConnectorSession, oldest: date | None
    ) -> WellnessListing:
        """List dated opaque wellness records over overlapping year windows."""
        start = oldest or WELLNESS_HISTORY_START
        end = session.now().astimezone(UTC).date() + timedelta(days=1)
        start = min(start, end)
        headers = _auth_headers(session, session.credentials.value("api_key"))
        days: list[WellnessDay] = []
        seen: set[date] = set()
        for window_start, window_end in _wellness_windows(start, end):
            query = {
                "oldest": window_start.isoformat(),
                "newest": window_end.isoformat(),
            }
            response = session.http.get(
                f"{API_BASE}/athlete/{SELF_ATHLETE}/wellness?{urlencode(query)}",
                secret_headers=headers,
            )
            if response.status != 200:
                _raise_for_wellness_status(
                    session, response, request="wellness listing"
                )
            try:
                payload = json.loads(response.body.decode("utf-8"))
            except ValueError:
                raise ConnectorError(
                    WELLNESS_LISTING_FORM_MESSAGE.format(
                        problem="the body is not valid JSON"
                    )
                ) from None
            if not isinstance(payload, list):
                raise ConnectorError(
                    WELLNESS_LISTING_FORM_MESSAGE.format(
                        problem="the body is not a JSON array"
                    )
                )
            for index, record in enumerate(payload):
                if not isinstance(record, dict):
                    raise ConnectorError(
                        WELLNESS_LISTING_FORM_MESSAGE.format(
                            problem=f"entry {index} is not an object"
                        )
                    )
                remote_id = record.get("id")
                if not isinstance(remote_id, str) or not _WELLNESS_ID_RE.fullmatch(
                    remote_id
                ):
                    raise ConnectorError(
                        WELLNESS_LISTING_FORM_MESSAGE.format(
                            problem=f"entry {index} has no YYYY-MM-DD id"
                        )
                    )
                try:
                    day = date.fromisoformat(remote_id)
                except ValueError:
                    raise ConnectorError(
                        WELLNESS_LISTING_FORM_MESSAGE.format(
                            problem=f"entry {index} has invalid calendar date"
                        )
                    ) from None
                if day in seen:
                    continue
                seen.add(day)
                updated = record.get("updated")
                revision = (
                    updated
                    if isinstance(updated, str) and updated
                    else _content_revision(record)
                )
                days.append(WellnessDay(day=day, revision=revision, record=record))
        return WellnessListing(
            oldest=start, newest=end, days=tuple(sorted(days, key=lambda d: d.day))
        )

    def package_wellness(
        self, session: ConnectorSession, days: tuple[WellnessDay, ...]
    ) -> WellnessPackage:
        response = session.http.get(
            f"{API_BASE}/athlete/{SELF_ATHLETE}",
            secret_headers=_auth_headers(session, session.credentials.value("api_key")),
        )
        if response.status != 200:
            _raise_for_wellness_status(
                session, response, request="athlete settings request"
            )
        try:
            athlete = json.loads(response.body.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise ConnectorError(
                ATHLETE_FORM_MESSAGE.format(problem="the body is not valid JSON")
            ) from None
        if not isinstance(athlete, dict):
            raise ConnectorError(
                ATHLETE_FORM_MESSAGE.format(problem="the body is not a JSON object")
            )
        origins = _wellness_origins(athlete)
        records: list[dict[str, object]] = []
        for index, day in enumerate(days):
            if not isinstance(day.record, dict):
                raise ConnectorError(
                    f"intervals.icu's wellness package record {index} is not an object"
                )
            records.append(day.record)
        data = _envelope_bytes(records, origins)
        return WellnessPackage(
            data, WELLNESS_SUFFIX, WELLNESS_FORMAT, frozenset(origins.values())
        )

    def publish(
        self, session: ConnectorSession, request: PublishRequest
    ) -> PublishResult:
        """Answer one publish request with one code (design.md
        "IntervalsPublisher"): the recorded link, the pull record, the facts
        check, the listing match, then the absent branch. Each activity is
        updated at most once; one answered absent is excluded from every
        later step. A link rides only with a landed code, always built from
        a usable identifier. Never raises for an intervals.icu answer."""
        settings = session.settings
        if not isinstance(settings, IntervalsSettings):
            raise ConnectorError(
                "the intervals connector was given another connector's settings"
            )
        headers = _auth_headers(session, session.credentials.value("api_key"))
        subject = request.subject
        absent: set[str] = set()

        def update(activity_id: str) -> PublishResult | None:
            return _publish_update(session, headers, activity_id, request.post, absent)

        linked = _linked_activity(request.recorded_link)
        if linked is not None:
            answered = update(linked)
            if answered is not None:
                return answered
        recorded = _record_activity(session, subject)
        record_unreadable = recorded is PublishCode.LOCAL_RECORD_UNREADABLE
        if recorded is PublishCode.AMBIGUOUS:
            return PublishResult(PublishCode.AMBIGUOUS)
        if isinstance(recorded, str) and recorded not in absent:
            answered = update(recorded)
            if answered is not None:
                return answered
        if subject.start.utcoffset() is None or (
            subject.distance_m is None and subject.elapsed_s is None
        ):
            return PublishResult(PublishCode.ACTIVITY_FACTS_MISSING)
        listed = _list(session, headers, subject)
        if isinstance(listed, PublishCode):
            return PublishResult(listed)
        matched = _match_listing(listed, subject, request.publication_id, absent=absent)
        if isinstance(matched, PublishCode):
            return PublishResult(matched)
        if matched is not None:
            answered = update(matched)
            if answered is not None:
                return answered
        if record_unreadable:
            return PublishResult(PublishCode.LOCAL_RECORD_UNREADABLE)
        if not settings.publish_upload:
            return PublishResult(PublishCode.NOT_FOUND)
        data = _base_file(subject)
        if data is None:
            return PublishResult(PublishCode.ACTIVITY_FILE_MISSING)
        uploaded = _upload(session, headers, data, request.publication_id)
        if isinstance(uploaded, PublishCode):
            return PublishResult(uploaded)
        named = uploaded.activity_id
        if named is None or named in absent:
            return PublishResult(PublishCode.UNCONFIRMED)
        confirmed = _update(session, headers, named, request.post)
        if confirmed is UpdateResult.CONFIRMED:
            return PublishResult(
                PublishCode.UPLOADED if uploaded.created else PublishCode.POSTED,
                _activity_link(named),
            )
        if uploaded.created or confirmed is UpdateResult.ABSENT:
            return PublishResult(PublishCode.UNCONFIRMED)
        return PublishResult(confirmed)

    def fetch_activity(
        self, session: ConnectorSession, activity: RemoteActivity
    ) -> FetchResult:
        """The activity's original file (Req 4.1-4.5, 4.7, 5.1-5.5): ``200``
        is decompressed within the size bound and handed over unmodified,
        unless it is a GPX or TCX document (declined, naming the format);
        ``404`` and ``422`` are an activity with no file (declined); every
        other status goes through :func:`_raise_for_status`."""
        url = f"{API_BASE}/activity/{quote(activity.remote_id, safe='')}/file"
        response = session.http.get(
            url,
            secret_headers=_auth_headers(session, session.credentials.value("api_key")),
        )
        if response.status == 200:
            data = _decompress(response.body)
            document = _document_format(data)
            if document is not None:
                return Declined(NOT_FIT_REASON.format(format=document))
            return Fetched(data)
        if response.status in (404, 422):
            return Declined(NO_FILE_REASON)
        _raise_for_status(session, response, listing=False)


def _windows(earliest: datetime, today: date) -> list[tuple[date, date | None]]:
    """The listing's overlapping ``(oldest, newest)`` date windows (Req 3.1,
    3.2). The first day is the UTC date of ``earliest`` less one day (the
    service's bounds are athlete-local dates and no offset exceeds a day);
    windows start every :data:`WINDOW_DAYS` days while the next start is
    before ``today``; each ``newest`` is one day past the next window's start
    so coverage does not depend on whether the service's bounds are
    inclusive; the last window has none."""
    first = earliest.astimezone(UTC).date() - timedelta(days=1)
    span = (today - first).days
    starts = [first]
    while (starts[-1] - first).days + WINDOW_DAYS < span:
        starts.append(starts[-1] + timedelta(days=WINDOW_DAYS))
    return [
        (
            start,
            starts[position + 1] + timedelta(days=1)
            if position + 1 < len(starts)
            else None,
        )
        for position, start in enumerate(starts)
    ]


def _listing_entries(session: ConnectorSession, response: HttpResponse) -> list[object]:
    if response.status != 200:
        _raise_for_status(session, response, listing=True)
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except ValueError:
        raise ConnectorError(
            LISTING_FORM_MESSAGE.format(problem="the body is not valid JSON")
        ) from None
    if not isinstance(payload, list):
        raise ConnectorError(
            LISTING_FORM_MESSAGE.format(problem="the body is not a JSON array")
        )
    return payload


def _remote_activity(
    entry: object, index: int, settings: IntervalsSettings, earliest: datetime
) -> RemoteActivity | None:
    """One listing entry as a listed activity, or ``None`` when it is omitted
    (Req 3.1, 3.4-3.7); a malformed entry ends the instance (Req 3.8)."""
    if not isinstance(entry, dict):
        raise ConnectorError(
            LISTING_FORM_MESSAGE.format(problem=f"entry {index} is not an object")
        )
    remote_id = entry.get("id")
    if not isinstance(remote_id, str) or not remote_id:
        raise ConnectorError(
            LISTING_FORM_MESSAGE.format(problem=f"entry {index} has no text id")
        )
    source = entry.get("source")
    if not isinstance(source, str) or source not in settings.sources:
        return None
    start = _start(entry.get("start_date"))
    if start is not None and start < earliest:
        return None
    sport = entry.get("type")
    elapsed = entry.get("elapsed_time")
    available = True
    reason: str | None = None
    file_type = entry.get("file_type")
    if source == STRAVA_SOURCE:
        available, reason = False, STRAVA_REASON
    elif (
        isinstance(file_type, str)
        and file_type.strip()
        and file_type.strip().lower() != "fit"
    ):
        available = False
        reason = NOT_FIT_REASON.format(format=file_type.strip().upper())
    duration_s: float | None = None
    if isinstance(elapsed, int) and not isinstance(elapsed, bool) and elapsed >= 0:
        duration_s = float(elapsed)
    return RemoteActivity(
        remote_id=remote_id,
        original_available=available,
        unavailable_reason=reason,
        start=start,
        sport=sport if isinstance(sport, str) and sport else None,
        duration_s=duration_s,
        revision=None,
        suggested_name=None,
    )


def _start(value: object) -> datetime | None:
    """``start_date`` in UTC when it states an offset; otherwise ``None``
    (never read as UTC, never the local zone)."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _decompress(body: bytes) -> bytes:
    """``body`` gunzipped when it starts with :data:`GZIP_MAGIC`, else as
    received (Req 4.2); gzip data that is damaged, truncated or expands past
    :data:`MAX_FILE_BYTES` fails the download (Req 4.3)."""
    if not body.startswith(GZIP_MAGIC):
        return body
    try:
        data = gzip.GzipFile(fileobj=io.BytesIO(body)).read(MAX_FILE_BYTES + 1)
    except (OSError, EOFError, zlib.error):
        raise IntervalsDownloadError(GZIP_UNREADABLE_MESSAGE) from None
    if len(data) > MAX_FILE_BYTES:
        raise IntervalsDownloadError(GZIP_OVERSIZE_MESSAGE.format(limit=MAX_FILE_BYTES))
    return data


def _document_format(data: bytes) -> str | None:
    """``"GPX"`` or ``"TCX"`` when the first :data:`DOCUMENT_SNIFF_BYTES`
    bytes, less a UTF-8 byte-order mark and leading whitespace, begin with
    ``<`` and hold that format's root element (case-insensitively); else
    ``None`` (Req 4.4)."""
    head = data[:DOCUMENT_SNIFF_BYTES].removeprefix(UTF8_BOM).lstrip().lower()
    if not head.startswith(b"<"):
        return None
    if b"<gpx" in head:
        return "GPX"
    if b"<trainingcenterdatabase" in head:
        return "TCX"
    return None


def _raise_for_status(
    session: ConnectorSession, response: HttpResponse, *, listing: bool
) -> NoReturn:
    """The status mapping for a data call (Req 5.1-5.5). 401 and 403 end the
    instance as authentication failures; a 429 or 5xx that survived the
    client's retries ends it as a connector error; any other status ends the
    instance for a listing and fails the one activity for a download."""
    message = _service_message(session, response)
    failure = auth_failure_from(response, service_message=message)
    if response.status in (401, 403) and failure is not None:
        raise failure
    if response.status == 429:
        raise ConnectorError(RATE_LIMITED_MESSAGE)
    if 500 <= response.status < 600:
        raise ConnectorError(UNAVAILABLE_MESSAGE.format(status=response.status))
    if listing:
        raise ConnectorError(
            LISTING_STATUS_MESSAGE.format(status=response.status, message=message)
        )
    raise IntervalsDownloadError(
        DOWNLOAD_STATUS_MESSAGE.format(status=response.status, message=message)
    )


def _sources_error(offending: object) -> ConnectorSettingsError:
    return ConnectorSettingsError(
        "sources",
        "sources must be a non-empty list of upper-case source names "
        f'such as "GARMIN_CONNECT", got {offending!r}',
    )


def _auth_headers(session: ConnectorSession, key: Secret) -> dict[str, Secret]:
    """The Basic credential for username ``API_KEY`` (Req 5.7). Both the bare
    encoded token and the full header value are registered with the session's
    redactor before the request, so a service that echoes either one is
    scrubbed."""
    token = base64.b64encode(f"{API_KEY_USERNAME}:{key.reveal()}".encode()).decode(
        "ascii"
    )
    session.secret(token)
    return {"Authorization": session.secret(f"Basic {token}")}


def _service_text(session: ConnectorSession, response: HttpResponse) -> str:
    """The service's own words, redacted before they are bounded (Req 5.7):
    the whole body (the transport has already bounded it) decoded with
    replacement and passed through the session's redactor, so a secret lying
    across the byte bound is matched whole; then cut to
    :data:`SERVICE_MESSAGE_BODY_BYTES` bytes of that redacted text (a
    multibyte character split by the cut is dropped, not replaced, so the cut
    leaves no stray marker), whitespace collapsed and cut to
    :data:`SERVICE_MESSAGE_CHARS` characters. Empty when the body said
    nothing."""
    text = session.redactor.redact(response.body.decode("utf-8", "replace"))
    # Every character is at least one byte, so a character pre-slice keeps the
    # re-encode at most 4 * SERVICE_MESSAGE_BODY_BYTES bytes.
    head = text[:SERVICE_MESSAGE_BODY_BYTES].encode("utf-8")
    text = head[:SERVICE_MESSAGE_BODY_BYTES].decode("utf-8", "ignore")
    return " ".join(text.split())[:SERVICE_MESSAGE_CHARS]


def _service_message(session: ConnectorSession, response: HttpResponse) -> str:
    """:func:`_service_text`, or ``HTTP <status>`` when it is empty."""
    return _service_text(session, response) or f"HTTP {response.status}"


def _wellness_windows(start: date, end: date) -> list[tuple[date, date]]:
    """Widen the first bound and overlap year windows by one day."""
    starts = [start - timedelta(days=1)]
    while starts[-1] + timedelta(days=WELLNESS_WINDOW_DAYS) < end:
        starts.append(starts[-1] + timedelta(days=WELLNESS_WINDOW_DAYS))
    return [
        (
            window_start,
            starts[index + 1] + timedelta(days=1) if index + 1 < len(starts) else end,
        )
        for index, window_start in enumerate(starts)
    ]


def _content_revision(record: dict[str, object]) -> str:
    canonical = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return (
        CONTENT_REVISION_PREFIX + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    )


def _raise_for_wellness_status(
    session: ConnectorSession, response: HttpResponse, *, request: str
) -> NoReturn:
    message = _service_message(session, response)
    if response.status == 401:
        failure = auth_failure_from(response, service_message=message)
        if failure is not None:
            raise failure
    if response.status == 403:
        raise ConnectorError(
            WELLNESS_REFUSED_MESSAGE.format(request=request, message=message)
        )
    if response.status == 429:
        raise ConnectorError(RATE_LIMITED_MESSAGE)
    if 500 <= response.status < 600:
        raise ConnectorError(UNAVAILABLE_MESSAGE.format(status=response.status))
    raise ConnectorError(
        WELLNESS_STATUS_MESSAGE.format(
            request=request, status=response.status, message=message
        )
    )


def _wellness_origins(athlete: dict[str, object]) -> dict[str, str]:
    switches = {
        "garmin": "icu_garmin_download_wellness",
        "polar": "polar_download_wellness",
        "suunto": "suunto_download_wellness",
        "coros": "coros_download_wellness",
        "zepp": "zepp_download_wellness",
        "huawei": "huawei_download_wellness",
    }
    claims: dict[str, set[str]] = {}
    for key, fields in athlete.items():
        match = re.fullmatch(WELLNESS_KEYS_PATTERN, key)
        if match is None:
            continue
        platform = match.group(1).replace("_", "-")
        if (
            platform in {"icu", "private"}
            or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", platform) is None
        ):
            continue
        switch = switches.get(platform)
        if switch is not None and switch in athlete and athlete[switch] is not True:
            continue
        if not isinstance(fields, list):
            continue
        for field in fields:
            if isinstance(field, str) and field:
                claims.setdefault(field, set()).add(platform)
    return {
        field: next(iter(platforms))
        for field, platforms in claims.items()
        if len(platforms) == 1
    }


def _envelope_bytes(records: list[dict[str, object]], origins: dict[str, str]) -> bytes:
    envelope: dict[str, object] = {
        "format": WELLNESS_DELIVERY_FORMAT,
        "version": WELLNESS_DELIVERY_VERSION,
        "records": sorted(records, key=lambda record: str(record["id"])),
    }
    if origins:
        envelope["origins"] = origins
    return (
        json.dumps(
            envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        + b"\n"
    )


# --- Publish: intervals.icu's answers as publish codes ----------------------
# (intervals-publish design.md "AnswerMapping"; Req 7.1-7.7, 8.2, 8.3)


class CallKind(StrEnum):
    """What a request does, which alone decides how its answers map."""

    READ = "read"  # the listing; retried by the transport
    UPDATE = "update"  # a write that is safe to repeat; retried by the transport
    CREATE = "create"  # a write that creates something; single attempt


class AnswerClass(StrEnum):
    SUCCESS = "success"
    UNAUTHORIZED = "401"
    FORBIDDEN = "403"
    NOT_FOUND = "404"
    RATE_LIMITED = "429"
    CLIENT_ERROR = "other 4xx"
    SERVER_ERROR = "5xx"
    OTHER = "other status"
    NETWORK_FAILURE = "network failure"


SUCCESS_STATUSES: Final[Mapping[CallKind, frozenset[int]]] = MappingProxyType(
    {
        CallKind.READ: frozenset({200}),
        CallKind.UPDATE: frozenset({200}),
        CallKind.CREATE: frozenset({200, 201}),
    }
)


def _row(
    read: PublishCode | None, update: PublishCode | None, create: PublishCode | None
) -> Mapping[CallKind, PublishCode | None]:
    return MappingProxyType(
        {CallKind.READ: read, CallKind.UPDATE: update, CallKind.CREATE: create}
    )


# ``None``: the calling flow decides.
ANSWER_CODES: Final[Mapping[AnswerClass, Mapping[CallKind, PublishCode | None]]] = (
    MappingProxyType(
        {
            AnswerClass.SUCCESS: _row(None, None, None),
            AnswerClass.UNAUTHORIZED: _row(
                PublishCode.AUTH_REJECTED,
                PublishCode.AUTH_REJECTED,
                PublishCode.AUTH_REJECTED,
            ),
            AnswerClass.FORBIDDEN: _row(
                PublishCode.PERMISSION_DENIED,
                PublishCode.PERMISSION_DENIED,
                PublishCode.PERMISSION_DENIED,
            ),
            AnswerClass.NOT_FOUND: _row(
                PublishCode.REJECTED, None, PublishCode.REJECTED
            ),
            AnswerClass.RATE_LIMITED: _row(
                PublishCode.RATE_LIMITED,
                PublishCode.RATE_LIMITED,
                PublishCode.RATE_LIMITED,
            ),
            AnswerClass.CLIENT_ERROR: _row(
                PublishCode.REJECTED, PublishCode.REJECTED, PublishCode.REJECTED
            ),
            AnswerClass.SERVER_ERROR: _row(
                PublishCode.UNAVAILABLE,
                PublishCode.UNAVAILABLE,
                PublishCode.UNCONFIRMED,
            ),
            AnswerClass.OTHER: _row(
                PublishCode.UNAVAILABLE,
                PublishCode.UNCONFIRMED,
                PublishCode.UNCONFIRMED,
            ),
            AnswerClass.NETWORK_FAILURE: _row(
                PublishCode.UNAVAILABLE,
                PublishCode.UNAVAILABLE,
                PublishCode.UNCONFIRMED,
            ),
        }
    )
)

ACTIVITY_ID_PATTERN: Final[str] = r"^[A-Za-z0-9]{1,64}$"
ACTIVITY_LINK_BASE: Final[str] = "https://intervals.icu/activities/"

_SPECIFIC_CLASSES: Final[Mapping[int, AnswerClass]] = MappingProxyType(
    {
        401: AnswerClass.UNAUTHORIZED,
        403: AnswerClass.FORBIDDEN,
        404: AnswerClass.NOT_FOUND,
        429: AnswerClass.RATE_LIMITED,
    }
)


def _answer_class(kind: CallKind, status: int) -> AnswerClass:
    """Classify an HTTP status for one request kind (a transport failure is
    ``AnswerClass.NETWORK_FAILURE``, chosen by the caller)."""
    if status in SUCCESS_STATUSES[kind]:
        return AnswerClass.SUCCESS
    if status in _SPECIFIC_CLASSES:
        return _SPECIFIC_CLASSES[status]
    if 400 <= status <= 499:
        return AnswerClass.CLIENT_ERROR
    if 500 <= status <= 599:
        return AnswerClass.SERVER_ERROR
    return AnswerClass.OTHER


def _answer_code(kind: CallKind, answer: AnswerClass) -> PublishCode | None:
    return ANSWER_CODES[answer][kind]


def _usable_activity_id(activity_id: str) -> bool:
    return re.fullmatch(ACTIVITY_ID_PATTERN, activity_id) is not None


def _activity_link(activity_id: str) -> str:
    """The direct link; called only with a usable identifier."""
    return ACTIVITY_LINK_BASE + activity_id


def _linked_activity(link: str | None) -> str | None:
    """The identifier in a link of exactly the form ``_activity_link`` builds."""
    if link is None or not link.startswith(ACTIVITY_LINK_BASE):
        return None
    activity_id = link[len(ACTIVITY_LINK_BASE) :]
    return activity_id if _usable_activity_id(activity_id) else None


def _record_activity(
    session: ConnectorSession, subject: CompletedActivity
) -> str | PublishCode | None:
    """The activity the instance's pull record names for the page's files.

    Read-only. The base file's digest is read first; the page's other digests
    only when the base names no activity. One identifier in a tier answers it,
    several answer ``AMBIGUOUS``, none (or no digest) answer ``None``. An
    unreadable record answers ``LOCAL_RECORD_UNREADABLE``.
    """
    try:
        ledger = load_ledger(
            session.data_root, session.instance, connector_id=INTERVALS_CONNECTOR_ID
        )
    except LedgerError:
        return PublishCode.LOCAL_RECORD_UNREADABLE
    if not subject.source_shas:
        return None
    base = subject.source_shas[-1]
    for digests in (frozenset({base}), frozenset(subject.source_shas[:-1]) - {base}):
        ids = {
            entry.remote_id
            for entry in ledger.entries
            if entry.sha256 in digests and _usable_activity_id(entry.remote_id)
        }
        if len(ids) > 1:
            return PublishCode.AMBIGUOUS
        if ids:
            return next(iter(ids))
    return None


# --- Publish: the activities listed around the page's start ------------------
# (intervals-publish design.md "ActivityFinding"; Req 3.5, 7.4, 9.3, 9.5)

RESOLVE_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "source",
    "start_date",
    "start_date_local",
    "distance",
    "elapsed_time",
    "external_id",
)
WINDOW_DAYS_BEFORE: Final[int] = 1
WINDOW_DAYS_AFTER: Final[int] = 2


@dataclass(frozen=True)
class ListedActivity:
    """One listing entry, each field ``None`` when absent or malformed."""

    activity_id: str  # a usable identifier
    strava: bool  # source == STRAVA_SOURCE
    start: datetime | None  # start_date with an offset, in UTC
    local_start: datetime | None  # start_date_local's wall clock, naive
    distance_m: float | None  # finite, >= 0, not bool
    elapsed_s: float | None  # int >= 0, not bool
    external_id: str | None  # non-empty text


def _listing_window(start: datetime) -> tuple[str, str]:
    """The ``oldest`` and ``newest`` local date-times that hold the page's
    start in any zone: from one day before the UTC date to two days after."""
    day = start.astimezone(UTC).date()
    oldest = day - timedelta(days=WINDOW_DAYS_BEFORE)
    newest = day + timedelta(days=WINDOW_DAYS_AFTER)
    return f"{oldest.isoformat()}T00:00:00", f"{newest.isoformat()}T00:00:00"


def _local_wall_clock(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=None)
    except ValueError:
        return None


def _listed_activity(entry: object) -> ListedActivity | None:
    if not isinstance(entry, dict):
        return None
    activity_id = entry.get("id")
    if not isinstance(activity_id, str) or not _usable_activity_id(activity_id):
        return None
    distance = entry.get("distance")
    distance_m: float | None = None
    if isinstance(distance, int | float) and not isinstance(distance, bool):
        try:
            as_float = float(distance)
        except OverflowError:
            as_float = math.nan
        if math.isfinite(as_float) and as_float >= 0:
            distance_m = as_float
    elapsed = entry.get("elapsed_time")
    elapsed_s: float | None = None
    if isinstance(elapsed, int) and not isinstance(elapsed, bool) and elapsed >= 0:
        try:
            elapsed_s = float(elapsed)
        except OverflowError:
            elapsed_s = None
    external_id = entry.get("external_id")
    return ListedActivity(
        activity_id=activity_id,
        strava=entry.get("source") == STRAVA_SOURCE,
        start=_start(entry.get("start_date")),
        local_start=_local_wall_clock(entry.get("start_date_local")),
        distance_m=distance_m,
        elapsed_s=elapsed_s,
        external_id=external_id
        if isinstance(external_id, str) and external_id
        else None,
    )


def _listed_activities(body: bytes) -> tuple[ListedActivity, ...] | None:
    """The entries of a listing body, a repeated identifier kept once (first
    wins); ``None`` when the body is not a JSON array of objects each with a
    usable identifier."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, RecursionError):
        return None
    if not isinstance(payload, list):
        return None
    listed: dict[str, ListedActivity] = {}
    for entry in payload:
        parsed = _listed_activity(entry)
        if parsed is None:
            return None
        listed.setdefault(parsed.activity_id, parsed)
    return tuple(listed.values())


def _list(
    session: ConnectorSession,
    headers: Mapping[str, Secret],
    subject: CompletedActivity,
) -> tuple[ListedActivity, ...] | PublishCode:
    """The key's own activities around the page's start, or the code the
    answer maps to (Req 3.5, 7.4, 9.3, 9.5)."""
    oldest, newest = _listing_window(subject.start)
    query = urlencode(
        {"oldest": oldest, "newest": newest, "fields": ",".join(RESOLVE_FIELDS)}
    )
    try:
        response = session.http.get(
            f"{API_BASE}/athlete/{SELF_ATHLETE}/activities?{query}",
            secret_headers=headers,
        )
    except TransportError:
        return _answer_code(CallKind.READ, AnswerClass.NETWORK_FAILURE) or (
            PublishCode.UNAVAILABLE
        )
    answer = _answer_class(CallKind.READ, response.status)
    if answer is not AnswerClass.SUCCESS:
        return _answer_code(CallKind.READ, answer) or PublishCode.UNAVAILABLE
    listed = _listed_activities(response.body)
    if listed is None:
        return PublishCode.UNAVAILABLE
    return listed


def _match_listing(
    listed: Sequence[ListedActivity],
    subject: CompletedActivity,
    publication_id: str,
    *,
    absent: Collection[str],
) -> str | PublishCode | None:
    """The one listed activity that is the page's, ``AMBIGUOUS`` when several
    are, ``NOT_UPDATABLE`` when only a Strava import is, else ``None``.

    Entries answered absent are left out. A non-Strava entry carrying the
    publication id as its external identifier wins; otherwise a non-Strava
    entry for which the identity rule gives the strict tier, the keys carrying
    the page's sport and no device or kind so that sport is not compared and no
    other tier can hold. No step orders candidates: a count above one is the
    answer. With no match, a Strava entry starting within the rule's start
    tolerance of the page (by its instant start, or without one by its local
    wall clock against the page's recorded wall clock) is ``NOT_UPDATABLE``.
    """
    from fitdocs.identity.matching import (
        START_TOLERANCE_S,
        Evidence,
        SessionKey,
        pair_evidence,
    )

    entries = [entry for entry in listed if entry.activity_id not in absent]
    mine = [entry for entry in entries if not entry.strava]

    def one(candidates: Collection[str]) -> str | PublishCode | None:
        if len(candidates) > 1:
            return PublishCode.AMBIGUOUS
        return next(iter(candidates), None)

    by_external = {
        entry.activity_id for entry in mine if entry.external_id == publication_id
    }
    if by_external:
        return one(by_external)

    def key(start: datetime | None, entry: ListedActivity | None) -> SessionKey:
        source = subject if entry is None else entry
        return SessionKey(
            sport=subject.sport,
            start=start,
            elapsed_s=source.elapsed_s,
            distance_m=source.distance_m,
            device=None,
            kind=None,
        )

    page_key = key(subject.start, None)
    strict = {
        entry.activity_id
        for entry in mine
        if pair_evidence(page_key, key(entry.start, entry)) is Evidence.STRICT
    }
    if strict:
        return one(strict)

    wall_clock = subject.start.replace(tzinfo=None)
    for entry in entries:
        if not entry.strava:
            continue
        if entry.start is not None:
            gap = abs((entry.start - subject.start).total_seconds())
        elif entry.local_start is not None:
            gap = abs((entry.local_start - wall_clock).total_seconds())
        else:
            continue
        if gap <= START_TOLERANCE_S:
            return PublishCode.NOT_UPDATABLE
    return None


class UpdateResult(Enum):
    CONFIRMED = "confirmed"
    ABSENT = "absent"


def _update(
    session: ConnectorSession,
    headers: Mapping[str, Secret],
    activity_id: str,
    post: Post,
) -> UpdateResult | PublishCode:
    """Set the activity's name and description to the post's, or the code the
    answer maps to (Req 5.1, 5.2, 5.4-5.6, 9.2, 9.5). The request is safe to
    repeat, so it is unmarked and the data-mode client retries it. The answer
    body is never read."""
    body = json.dumps(
        {"name": post.title, "description": post.description},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    try:
        response = session.http.put(
            f"{API_BASE}/activity/{quote(activity_id, safe='')}",
            body=body,
            headers={"Content-Type": "application/json"},
            secret_headers=headers,
        )
    except TransportError:
        return _answer_code(CallKind.UPDATE, AnswerClass.NETWORK_FAILURE) or (
            PublishCode.UNAVAILABLE
        )
    answer = _answer_class(CallKind.UPDATE, response.status)
    if answer is AnswerClass.SUCCESS:
        return UpdateResult.CONFIRMED
    if answer is AnswerClass.NOT_FOUND:
        return UpdateResult.ABSENT
    return _answer_code(CallKind.UPDATE, answer) or PublishCode.UNAVAILABLE


UPLOAD_FIELD: Final[str] = "file"
UPLOAD_FILENAME: Final[str] = "activity.fit"
MULTIPART_BOUNDARY_PREFIX: Final[str] = "fitdocs-"


@dataclass(frozen=True)
class UploadAnswer:
    created: bool  # 201 (True) or 200 (False)
    activity_id: str | None  # the one usable id the answer names, or None


def _base_file(subject: CompletedActivity) -> bytes | None:
    """The page's base file, only when it is present, readable and hashes to
    the base digest (the last of the page's source digests); otherwise
    ``None`` (Req 6.3)."""
    if subject.base_fit is None or not subject.source_shas:
        return None
    try:
        data = subject.base_fit.read_bytes()
    except OSError:
        return None
    if hashlib.sha256(data).hexdigest() != subject.source_shas[-1]:
        return None
    return data


def _multipart_body(data: bytes, publication_id: str) -> tuple[bytes, str]:
    """The one-part ``multipart/form-data`` body holding ``data`` unmodified,
    and its content type (Req 6.2). The boundary is the first of
    ``fitdocs-<id>``, ``fitdocs-<id>-1``, ``-2``, ... whose delimiter does not
    occur in the file; the same file and id give the same bytes."""
    base = f"{MULTIPART_BOUNDARY_PREFIX}{publication_id}"
    boundary = base
    suffix = 0
    while b"--" + boundary.encode("ascii") in data:
        suffix += 1
        boundary = f"{base}-{suffix}"
    delimiter = b"--" + boundary.encode("ascii")
    head = (
        f'Content-Disposition: form-data; name="{UPLOAD_FIELD}"; '
        f'filename="{UPLOAD_FILENAME}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("ascii")
    body = delimiter + b"\r\n" + head + data + b"\r\n" + delimiter + b"--\r\n"
    return body, f"multipart/form-data; boundary={boundary}"


def _uploaded_activity(body: bytes) -> str | None:
    """The one usable identifier an upload answer names, else ``None``: the
    body is a JSON object whose ``activities`` is a non-empty list of objects
    each holding a usable string ``id``, all naming one identifier (Req
    6.5-6.7)."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, RecursionError):
        return None
    if not isinstance(payload, dict):
        return None
    activities = payload.get("activities")
    if not isinstance(activities, list) or not activities:
        return None
    ids: set[str] = set()
    for entry in activities:
        if not isinstance(entry, dict):
            return None
        activity_id = entry.get("id")
        if not isinstance(activity_id, str) or not _usable_activity_id(activity_id):
            return None
        ids.add(activity_id)
    return next(iter(ids)) if len(ids) == 1 else None


def _upload(
    session: ConnectorSession,
    headers: Mapping[str, Secret],
    data: bytes,
    publication_id: str,
) -> UploadAnswer | PublishCode:
    """Upload the base file once to the key's own athlete, the publication id
    the only query value (Req 6.2, 6.4, 9.5). The request creates something,
    so it is marked single-attempt; a transport failure is unconfirmed."""
    body, content_type = _multipart_body(data, publication_id)
    query = urlencode({"external_id": publication_id})
    try:
        response = session.http.post(
            f"{API_BASE}/athlete/{SELF_ATHLETE}/activities?{query}",
            body=body,
            headers={"Content-Type": content_type},
            secret_headers=headers,
            single_attempt=True,
        )
    except TransportError:
        return _answer_code(CallKind.CREATE, AnswerClass.NETWORK_FAILURE) or (
            PublishCode.UNCONFIRMED
        )
    answer = _answer_class(CallKind.CREATE, response.status)
    if answer is AnswerClass.SUCCESS:
        return UploadAnswer(
            created=response.status == 201,
            activity_id=_uploaded_activity(response.body),
        )
    return _answer_code(CallKind.CREATE, answer) or PublishCode.UNCONFIRMED


def _publish_update(
    session: ConnectorSession,
    headers: Mapping[str, Secret],
    activity_id: str,
    post: Post,
    absent: set[str],
) -> PublishResult | None:
    """Update one activity of a publish request: ``POSTED`` with its link, the
    code of any other answer, or ``None`` after noting the activity absent (or
    when the identifier is not a usable one, which names nothing and so
    receives neither a request nor a link, Req 8.2)."""
    if not _usable_activity_id(activity_id):
        return None
    result = _update(session, headers, activity_id, post)
    if result is UpdateResult.CONFIRMED:
        return PublishResult(PublishCode.POSTED, _activity_link(activity_id))
    if result is UpdateResult.ABSENT:
        absent.add(activity_id)
        return None
    return PublishResult(result)
