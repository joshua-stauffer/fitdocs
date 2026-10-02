"""The intervals.icu connector (design.md "IntervalsConnector").

Lists, filters and fetches intervals.icu originals for the key's own athlete
with a personal API key. This module is the one module in the connectors
package that names the service's address (the service-neutral scan admits it
here, in its own tests and in its own documentation section only). It imports only the
standard library and ``fitdocs.connectors.{errors,http,protocol,secrets}``,
builds no HTTP client of its own, and reads no clock: ``session.now`` is the
only time source.

Task 3.1 declares the connector, its constants and its settings parser; task
3.2 implements the key check, the credential and the service-message helper;
task 3.3 implements the listing, its date windows and entry mapping, and the
status mapping for data calls. The file fetch raises
:class:`NotImplementedError` until task 3.4 implements it.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Final
from urllib.parse import urlencode

from fitdocs.connectors.errors import (
    AuthFailure,
    AuthFailureKind,
    ConnectorError,
    ConnectorSettingsError,
)
from fitdocs.connectors.http import (
    MAX_RESPONSE_BYTES,
    HttpResponse,
    auth_failure_from,
)
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    ConnectorSession,
    CredentialField,
    FetchResult,
    Granted,
    Listing,
    RemoteActivity,
    SettingsContext,
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
NO_FILE_REASON: Final[str] = (
    "intervals.icu holds no original file for this activity (HTTP 404)"
)
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

_SOURCE_NAME_RE = re.compile(SOURCE_NAME_PATTERN)
_NOT_YET = "implemented by a later intervals-connector task (3.4)"


@dataclass(frozen=True)
class IntervalsSettings:
    """Validated ``[connectors.<instance>]`` configuration for an
    ``intervals`` instance."""

    sources: frozenset[str]
    """The service-reported recording sources a pull keeps."""


class IntervalsDownloadError(Exception):
    """One activity's download failed; the framework reports it and retries
    it next pull."""


class IntervalsConnector:
    """intervals.icu originals through a personal API key."""

    connector_id = INTERVALS_CONNECTOR_ID
    display_name = "intervals.icu"
    auth_style = AuthStyle.API_KEY
    capabilities = frozenset({Capability.PULL_ACTIVITIES})
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
        vocabulary lacks is accepted. Every other key is ignored."""
        if "sources" not in table:
            return IntervalsSettings(sources=DEFAULT_SOURCES)
        value = table["sources"]
        if not isinstance(value, list) or not value:
            raise _sources_error(value)
        for item in value:
            if not isinstance(item, str) or not _SOURCE_NAME_RE.fullmatch(item):
                raise _sources_error(item)
        return IntervalsSettings(sources=frozenset(value))

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
        raise AuthFailure(
            AuthFailureKind.UNAVAILABLE, f"HTTP {response.status}: {message}"
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

    def fetch_activity(
        self, session: ConnectorSession, activity: RemoteActivity
    ) -> FetchResult:
        raise NotImplementedError(_NOT_YET)


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


def _raise_for_status(
    session: ConnectorSession, response: HttpResponse, *, listing: bool
) -> None:
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


def _service_message(session: ConnectorSession, response: HttpResponse) -> str:
    """The service's own words, bounded and redacted (Req 5.7): the first
    :data:`SERVICE_MESSAGE_BODY_BYTES` body bytes, whitespace collapsed,
    passed through the session's redactor, then cut to
    :data:`SERVICE_MESSAGE_CHARS` characters; ``HTTP <status>`` when empty."""
    text = response.body[:SERVICE_MESSAGE_BODY_BYTES].decode("utf-8", "replace")
    text = session.redactor.redact(" ".join(text.split()))
    return text[:SERVICE_MESSAGE_CHARS] or f"HTTP {response.status}"
