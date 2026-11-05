"""The Garmin connector (design.md "GarminConnector").

Pulls a Garmin account's activities and daily wellness with the athlete's own
Connect Personal API key. This module is the one module in the connectors
package that names the Personal API host (the service-neutral scan admits it
here and in its own tests only). It imports only the standard library and
``fitdocs.connectors.{delivery,errors,http,ledger,protocol,secrets}``,
builds no HTTP client of its own, and reads no clock.

Task 3.1 declares the connector and implements the key check. Task 3.2 adds
the per-pull state (one token, spacing, rate-limit waits) and the one helper
every Garmin GET goes through. Task 3.3 adds the activity listing and task 3.4
the per-pull limit, and task 3.5 the activity download. The other two pull
operations are placeholders that raise a named :class:`ConnectorError` and
make no request, because the registry requires them once the capabilities are
declared; later tasks replace them.
"""

from __future__ import annotations

import io
import json
import lzma
import math
import re
import zipfile
import zlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Final
from urllib.parse import quote, urlencode
from weakref import WeakKeyDictionary

from fitdocs.connectors.delivery import is_fit
from fitdocs.connectors.errors import AuthFailure, AuthFailureKind, ConnectorError
from fitdocs.connectors.http import (
    MAX_RESPONSE_BYTES,
    HttpClient,
    HttpResponse,
    TransportError,
    auth_failure_from,
)
from fitdocs.connectors.ledger import Ledger, LedgerError, load_ledger
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    ConnectorSession,
    CredentialField,
    Declined,
    Fetched,
    FetchResult,
    Granted,
    Listing,
    ListingDeferral,
    RemoteActivity,
    SettingsContext,
    WellnessDay,
    WellnessListing,
    WellnessPackage,
)
from fitdocs.connectors.secrets import Secret

GARMIN_CONNECTOR_ID: Final[str] = "garmin"
API_BASE: Final[str] = "https://personal.connectapi.garmin.com"
TOKEN_PATH: Final[str] = "/personalapitoken-service/personal-api/personal-api-key/token"
MAX_TOKEN_BYTES: Final[int] = 16 * 1024
REQUEST_SPACING_S: Final[float] = 1.0
RATE_LIMIT_WAITS_S: Final[tuple[float, ...]] = (30.0, 60.0, 120.0, 240.0)
MAX_STATED_WAIT_S: Final[float] = 300.0
MAX_WAITS_PER_PULL_S: Final[float] = 900.0
LISTING_PAGE: Final[int] = 200
LISTING_EARLIEST: Final[date] = date(1990, 1, 1)
LISTING_PATH: Final[str] = "/activitylist-service/activities/search/activities"
ACTIVITIES_PER_PULL: Final[int] = 200

_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_GMT_START_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}")

REJECTED_MESSAGE: Final[str] = (
    "Garmin did not accept the Personal API key (HTTP {status}); the key may "
    "be wrong, expired or deleted. Create a new key on Garmin Connect, then "
    "run `fitdocs connect` again."
)
RATE_LIMITED_MESSAGE: Final[str] = (
    "Garmin is limiting requests (HTTP 429) and refused the key check"
)
UNAVAILABLE_MESSAGE: Final[str] = (
    "Garmin is unavailable or answered unexpectedly (HTTP {status}) to the token "
    "request"
)
NOT_A_TOKEN_MESSAGE: Final[str] = (
    "Garmin's answer to the token request was not understood: it succeeded but "
    "was not a token"
)
PULL_RATE_LIMITED_MESSAGE: Final[str] = (
    "Garmin is limiting requests (HTTP 429); the next pull resumes where this "
    "one stopped."
)
TOKEN_UNREACHABLE_MESSAGE: Final[str] = (
    "Garmin could not be reached for the token request; the next pull resumes "
    "where this one stopped"
)
LISTING_NOT_A_LIST_MESSAGE: Final[str] = (
    "Garmin's activity listing was not understood: it is not a list of activity objects"
)
LISTING_NOT_AN_OBJECT_MESSAGE: Final[str] = (
    "Garmin's activity listing was not understood: entry {position} is not an object"
)
LISTING_NO_ID_MESSAGE: Final[str] = (
    "Garmin's activity listing was not understood: entry {position} has no "
    "positive whole-number identifier"
)
LISTING_REPEATED_MESSAGE: Final[str] = (
    "Garmin's activity listing was not understood: a full page repeated "
    "activities already listed"
)
LISTING_REFUSED_MESSAGE: Final[str] = (
    "Garmin refused the activity listing (HTTP 403). Garmin's terms let it "
    "restrict access; check the key's status on Garmin Connect."
)
LISTING_UNAVAILABLE_MESSAGE: Final[str] = (
    "Garmin is unavailable (HTTP {status}) for the activity listing; the next "
    "pull resumes where this one stopped"
)
LISTING_UNREACHABLE_MESSAGE: Final[str] = (
    "Garmin is unavailable: it could not be reached for the activity listing; "
    "the next pull resumes where this one stopped"
)
LISTING_OTHER_MESSAGE: Final[str] = (
    "Garmin answered the activity listing with an unexpected status (HTTP {status})"
)
LEDGER_UNREADABLE_MESSAGE: Final[str] = (
    "The ledger of what this instance already pulled could not be read, so "
    "no activities were pulled; repair or remove the instance's ledger file "
    "under .fitdocs/connectors, then pull again"
)
DEFERRED_MESSAGE: Final[str] = (
    "{count} more {noun} left for a later pull: the next `fitdocs pull` "
    "continues there, and a pull started with `--since` continues only "
    "with the same `--since`"
)
NOT_BUILT_MESSAGE: Final[str] = (
    "the Garmin connector does not implement {operation} yet"
)


def _mint(session: ConnectorSession, client: HttpClient, key: Secret) -> Secret:
    """One token request with ``key``, in a single attempt (Req 1.2, 7.1, 7.2).

    Takes the client and the key as arguments because a connect session
    refuses ``credentials``. Returns the ``Bearer`` header value with both the
    bare token and that value registered with the session's redactor; every
    other answer is an :class:`AuthFailure` that never quotes the body."""
    response = client.post(
        API_BASE + TOKEN_PATH,
        body=b"",
        headers={"Accept": "*/*"},
        secret_headers={"Authorization": session.secret(f"ApiKey {key.reveal()}")},
        single_attempt=True,
    )
    if response.status == 200:
        token = _token_text(response.body)
        if token is None:
            raise AuthFailure(AuthFailureKind.UNAVAILABLE, NOT_A_TOKEN_MESSAGE)
        session.secret(token)
        return session.secret(f"Bearer {token}")
    if response.status in (401, 403):
        raise AuthFailure(
            AuthFailureKind.REJECTED, REJECTED_MESSAGE.format(status=response.status)
        )
    if response.status == 429:
        limited = auth_failure_from(response, service_message=RATE_LIMITED_MESSAGE)
        retry_after = limited.retry_after_s if limited is not None else None
        raise AuthFailure(
            AuthFailureKind.RATE_LIMITED, RATE_LIMITED_MESSAGE, retry_after
        )
    raise AuthFailure(
        AuthFailureKind.UNAVAILABLE, UNAVAILABLE_MESSAGE.format(status=response.status)
    )


def _token_text(body: bytes) -> str | None:
    """The token when ``body`` is three dot-separated base64url segments of at
    most :data:`MAX_TOKEN_BYTES`, else ``None``."""
    if len(body) > MAX_TOKEN_BYTES:
        return None
    try:
        text = body.decode("ascii").strip()
    except UnicodeDecodeError:
        return None
    return text if _TOKEN_RE.fullmatch(text) else None


@dataclass
class _PullState:
    """What one pull keeps between its requests (design.md "State
    Management"). Nothing here is ever written to disk. ``bearer`` is kept out
    of the repr, though a :class:`Secret` already masks itself."""

    bearer: Secret | None = field(default=None, repr=False)
    mint_error: ConnectorError | AuthFailure | None = None
    used: bool = False
    waited_s: float = 0.0
    consecutive_failures: int = 0


def _rate_limit_wait(
    stated: float | None, repeats: int, waited_s: float
) -> float | None:
    """The wait before repeating a request Garmin answered 429, or ``None``
    when waiting must stop (Req 4.7, 4.8): at most 4 repeats of one request,
    a stated wait of at most 5 minutes, and at most 15 minutes in the pull."""
    if repeats >= len(RATE_LIMIT_WAITS_S):
        return None
    if stated is None:
        wait = RATE_LIMIT_WAITS_S[repeats]
    elif stated > MAX_STATED_WAIT_S:
        return None
    else:
        wait = stated
    if waited_s + wait > MAX_WAITS_PER_PULL_S:
        return None
    return wait


def _remote_activity(entry: object, position: int) -> RemoteActivity:
    """One listing entry as a remote activity (Req 3.5-3.7). Keeps the
    identifier, the stated UTC start, the sport and the elapsed duration;
    nothing else of the entry is read. A missing or malformed identifier is a
    :class:`ConnectorError` naming ``position`` (1-based, across the whole
    listing) that never quotes the entry; any other field that is not stated
    in its documented form is ``None``."""
    if not isinstance(entry, dict):
        raise ConnectorError(LISTING_NOT_AN_OBJECT_MESSAGE.format(position=position))
    activity_id = entry.get("activityId")
    if not isinstance(activity_id, int) or isinstance(activity_id, bool):
        raise ConnectorError(LISTING_NO_ID_MESSAGE.format(position=position))
    if activity_id <= 0:
        raise ConnectorError(LISTING_NO_ID_MESSAGE.format(position=position))
    return RemoteActivity(
        remote_id=str(activity_id),
        original_available=True,
        start=_gmt_start(entry.get("startTimeGMT")),
        sport=_sport(entry.get("activityType")),
        duration_s=_seconds(entry.get("elapsedDuration")),
    )


def _gmt_start(value: object) -> datetime | None:
    """``YYYY-MM-DD HH:MM:SS`` read as UTC, else ``None``."""
    if not isinstance(value, str) or _GMT_START_RE.fullmatch(value) is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _sport(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    key = value.get("typeKey")
    if isinstance(key, str) and key.strip():
        return key
    return None


def _seconds(value: object) -> float | None:
    """A stated finite, non-negative number as seconds, else ``None``. A
    stated 0 is a stated value."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        seconds = float(value)
    except OverflowError:
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds


def _listing_page(body: bytes) -> list[object]:
    """The entries of one listing answer, or a named :class:`ConnectorError`
    that never quotes the body."""
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ConnectorError(LISTING_NOT_A_LIST_MESSAGE) from None
    if not isinstance(data, list):
        raise ConnectorError(LISTING_NOT_A_LIST_MESSAGE)
    return data


def _raise_for_listing(response: HttpResponse) -> None:
    """Map a listing answer that is not 200 (Req 6.1-6.4, 6.7, 6.8). A 429
    never gets here: ``_get`` has already raised it after the waits."""
    status = response.status
    if status == 200:
        return
    if status == 401:
        raise AuthFailure(AuthFailureKind.REJECTED, REJECTED_MESSAGE.format(status=401))
    if status == 403:
        raise AuthFailure(AuthFailureKind.REJECTED, LISTING_REFUSED_MESSAGE)
    if 500 <= status < 600:
        raise ConnectorError(LISTING_UNAVAILABLE_MESSAGE.format(status=status))
    raise ConnectorError(LISTING_OTHER_MESSAGE.format(status=status))


def _limit(
    session: ConnectorSession, activities: tuple[RemoteActivity, ...]
) -> Listing:
    """Entries in start order up to the cut (Req 4.2, 4.3, 4.6): the cut is the
    first not-final entry after :data:`ACTIVITIES_PER_PULL` not-final ones have
    been kept, and everything from it on is withheld, finals included. Finals
    before the cut are listed and not counted. Withholding the finals past the
    cut is what keeps the engine's watermark, computed over the listing, from
    jumping over the withheld entries and stranding them. Final is the
    engine's own test, :meth:`Ledger.is_final`, read from the instance's
    ledger on disk; the sort key is the engine's, so an activity with no start
    comes last, by identifier. The withheld not-final entries are one deferred
    entry naming the count; with none withheld there is no deferral and every
    entry is listed."""
    try:
        ledger: Ledger = load_ledger(
            session.data_root, session.instance, connector_id=GARMIN_CONNECTOR_ID
        )
    except LedgerError:
        raise ConnectorError(LEDGER_UNREADABLE_MESSAGE) from None
    ordered = sorted(
        activities,
        key=lambda activity: (
            activity.start is None,
            activity.start,
            activity.remote_id,
        ),
    )
    not_final = [
        not ledger.is_final(activity.remote_id, activity.revision)
        for activity in ordered
    ]
    cut = len(ordered)
    seen = 0
    for index, pending in enumerate(not_final):
        if not pending:
            continue
        if seen == ACTIVITIES_PER_PULL:
            cut = index
            break
        seen += 1
    remainder = sum(not_final[cut:])
    if remainder == 0:
        return Listing(tuple(ordered))
    reason = DEFERRED_MESSAGE.format(
        count=remainder, noun="activity" if remainder == 1 else "activities"
    )
    return Listing(tuple(ordered[:cut]), (ListingDeferral(session.instance, reason),))


FILE_PATH: Final[str] = "/download-service/files/activity/"
FILE_ACCEPT: Final[str] = (
    "application/zip, application/x-zip-compressed, application/octet-stream"
)
MAX_FILE_BYTES: Final[int] = MAX_RESPONSE_BYTES
CONSECUTIVE_FAILURE_STOP: Final[int] = 5
DOCUMENT_SNIFF_BYTES: Final[int] = 1024
UTF8_BOM: Final[bytes] = b"\xef\xbb\xbf"
FILE_REFUSED_MESSAGE: Final[str] = (
    "Garmin refused the activity download (HTTP 403). Garmin's terms let it "
    "restrict access; check the key's status on Garmin Connect."
)
NO_FILE_MESSAGE: Final[str] = "Garmin holds no file for this activity"
NO_FIT_MESSAGE: Final[str] = "Garmin's download for this activity holds no FIT file"
NOT_FIT_MESSAGE: Final[str] = (
    "Garmin's download for this activity holds no FIT file, only {formats}"
)
SEVERAL_FIT_MESSAGE: Final[str] = (
    "Garmin's download for this activity holds {count} FIT files, so it is not "
    "clear which is the original"
)
ARCHIVE_UNREADABLE_MESSAGE: Final[str] = (
    "Garmin's download for this activity could not be read as a ZIP archive; the "
    "next pull tries it again"
)
FILE_TOO_LARGE_MESSAGE: Final[str] = (
    "A FIT file in Garmin's download for this activity is larger than {limit} "
    "bytes; the next pull tries it again"
)
FILE_UNAVAILABLE_MESSAGE: Final[str] = (
    "Garmin is unavailable (HTTP {status}) for this activity's download; the "
    "next pull tries it again"
)
FILE_OTHER_MESSAGE: Final[str] = (
    "Garmin answered this activity's download with an unexpected status "
    "(HTTP {status}); the next pull tries it again"
)
UNAVAILABLE_STOP_MESSAGE: Final[str] = (
    f"Garmin appears unavailable: {CONSECUTIVE_FAILURE_STOP} downloads in a row "
    "met a server error or could not reach it; the next pull resumes where this "
    "one stopped"
)


class GarminDownloadError(Exception):
    """One activity's download failed (Req 5.6, 6.5, 6.7). Deliberately not a
    :class:`ConnectorError` or :class:`AuthFailure`: the engine ends an
    instance for those and fails only the one activity for anything else. The
    message is the connector's own wording and never quotes Garmin."""


def _document_format(data: bytes) -> str | None:
    """``"GPX"`` or ``"TCX"`` when the first :data:`DOCUMENT_SNIFF_BYTES`
    bytes, less a UTF-8 byte-order mark and leading whitespace, begin with
    ``<`` and hold that format's root element (case-insensitively); else
    ``None`` (Req 5.4). A copy of the intervals connector's, which this module
    may not import."""
    head = data[:DOCUMENT_SNIFF_BYTES].removeprefix(UTF8_BOM).lstrip().lower()
    if not head.startswith(b"<"):
        return None
    if b"<gpx" in head:
        return "GPX"
    if b"<trainingcenterdatabase" in head:
        return "TCX"
    return None


def _read_archive(body: bytes) -> FetchResult:
    """The one FIT member of a downloaded ZIP archive, or why there is not one
    (Req 5.2-5.7). Members are classified from their first
    :data:`DOCUMENT_SNIFF_BYTES` bytes, in memory: a member's name is never
    read, never used as a path, and nothing is extracted or written. A member
    longer than that is read further only when it is the archive's one FIT
    member, and then to at most :data:`MAX_FILE_BYTES` + 1 bytes."""
    limit = MAX_FILE_BYTES
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            fit_members: list[zipfile.ZipInfo] = []
            formats: set[str] = set()
            for info in archive.infolist():
                with archive.open(info) as member:
                    head = member.read(DOCUMENT_SNIFF_BYTES)
                if is_fit(head):
                    fit_members.append(info)
                else:
                    document = _document_format(head)
                    if document is not None:
                        formats.add(document)
            if len(fit_members) > 1:
                return Declined(SEVERAL_FIT_MESSAGE.format(count=len(fit_members)))
            if not fit_members:
                if formats:
                    return Declined(
                        NOT_FIT_MESSAGE.format(formats=" and ".join(sorted(formats)))
                    )
                return Declined(NO_FIT_MESSAGE)
            with archive.open(fit_members[0]) as member:
                data = member.read(limit + 1)
    except (
        zipfile.BadZipFile,
        zlib.error,
        EOFError,
        RuntimeError,
        NotImplementedError,
        OSError,
        ValueError,
        lzma.LZMAError,
    ):
        raise GarminDownloadError(ARCHIVE_UNREADABLE_MESSAGE) from None
    if len(data) > limit:
        raise GarminDownloadError(FILE_TOO_LARGE_MESSAGE.format(limit=limit))
    return Fetched(data)


def _not_built(operation: str) -> ConnectorError:
    return ConnectorError(NOT_BUILT_MESSAGE.format(operation=operation))


class GarminConnector:
    """Garmin activities and wellness through a Connect Personal API key."""

    connector_id = GARMIN_CONNECTOR_ID
    display_name = "Garmin"
    auth_style = AuthStyle.API_KEY
    capabilities = frozenset({Capability.PULL_ACTIVITIES, Capability.PULL_WELLNESS})
    credential_fields = (CredentialField("api_key", "Personal API key", True),)

    def __init__(self) -> None:
        # Keyed by the session's client, held weakly: after a successful mint
        # a pull's state goes with its client (Req 7.2). A failed mint's kept
        # error holds traceback frames that retain the client, so that state
        # stays until the process ends, which is harmless in a one-shot pull.
        self._pulls: WeakKeyDictionary[HttpClient, _PullState] = WeakKeyDictionary()

    def _state(self, session: ConnectorSession) -> _PullState:
        state = self._pulls.get(session.http)
        if state is None:
            state = _PullState()
            self._pulls[session.http] = state
        return state

    @staticmethod
    def _space(session: ConnectorSession, state: _PullState) -> None:
        """One second between distinct requests, none before the pull's first
        (Req 4.1)."""
        if state.used:
            session.sleep(REQUEST_SPACING_S)
        state.used = True

    def _bearer(self, session: ConnectorSession, state: _PullState) -> Secret:
        """The pull's ``Bearer`` header value: one token request at most, and
        a failed one is kept and raised again with no second request (Req 7.2).

        A 401 or 403 answer is the rejected-key failure and a 429 the
        rate-limit failure, so wellness is suppressed after those; anything
        else is a :class:`ConnectorError`."""
        if state.mint_error is not None:
            raise state.mint_error
        if state.bearer is not None:
            return state.bearer
        self._space(session, state)
        try:
            state.bearer = _mint(
                session, session.http, session.credentials.value("api_key")
            )
        except AuthFailure as failure:
            if failure.kind is AuthFailureKind.RATE_LIMITED:
                state.mint_error = AuthFailure(
                    AuthFailureKind.RATE_LIMITED,
                    PULL_RATE_LIMITED_MESSAGE,
                    failure.retry_after_s,
                )
            elif failure.kind is AuthFailureKind.REJECTED:
                state.mint_error = failure
            else:
                state.mint_error = ConnectorError(failure.service_message)
            raise state.mint_error from None
        except TransportError:
            state.mint_error = ConnectorError(TOKEN_UNREACHABLE_MESSAGE)
            raise state.mint_error from None
        return state.bearer

    def _get(
        self,
        session: ConnectorSession,
        url: str,
        headers: Mapping[str, str],
    ) -> HttpResponse:
        """Every Garmin GET: the pull's token, 1 s of spacing, the transport's
        429 retries off, and the rate-limit waits of Req 4.7 to 4.9.

        Any answer but 429 goes back to the caller. A repeat after a wait gets
        no extra spacing."""
        state = self._state(session)
        bearer = self._bearer(session, state)
        self._space(session, state)
        repeats = 0
        while True:
            response = session.http.get(
                url,
                headers=headers,
                secret_headers={"Authorization": bearer},
                retry_rate_limits=False,
            )
            if response.status != 429:
                return response
            limited = auth_failure_from(response)
            stated = limited.retry_after_s if limited is not None else None
            wait = _rate_limit_wait(stated, repeats, state.waited_s)
            if wait is None:
                raise AuthFailure(
                    AuthFailureKind.RATE_LIMITED, PULL_RATE_LIMITED_MESSAGE, stated
                )
            session.sleep(wait)
            state.waited_s += wait
            repeats += 1

    def parse_settings(
        self, table: Mapping[str, object], context: SettingsContext
    ) -> None:
        """Accepts nothing and ignores every key (Req 1.7, 2.1, 2.2)."""
        return None

    def verify(
        self, session: ConnectorSession, values: Mapping[str, Secret]
    ) -> Granted:
        """Mint one token with the key and discard it (Req 1.2, 1.3): scopes
        are absent, not empty, and a key's expiry is never known."""
        _mint(session, session.http, values["api_key"])
        return Granted(scopes=None)

    def list_activities(
        self, session: ConnectorSession, since: datetime | None
    ) -> Listing:
        """Every activity of the key's owner from ``since`` (Req 3.1-3.7),
        oldest first in pages of :data:`LISTING_PAGE`, each identifier once.
        Both date filters are always sent; ``since`` is then applied to each
        entry's UTC start. The listing is then limited per pull by
        :func:`_limit` (Req 4.2, 4.3, 4.6)."""
        floor = None
        if since is not None:
            floor = (since if since.tzinfo else since.replace(tzinfo=UTC)).astimezone(
                UTC
            )
        first_day = (
            LISTING_EARLIEST if floor is None else floor.date() - timedelta(days=1)
        )
        last_day = session.now().astimezone(UTC).date() + timedelta(days=1)
        activities: dict[str, RemoteActivity] = {}
        offset = 0
        while True:
            query = urlencode(
                {
                    "start": offset,
                    "limit": LISTING_PAGE,
                    "sortOrder": "asc",
                    "startDate": first_day.isoformat(),
                    "endDate": last_day.isoformat(),
                }
            )
            try:
                response = self._get(
                    session,
                    f"{API_BASE}{LISTING_PATH}?{query}",
                    {"Accept": "application/json"},
                )
            except TransportError:
                raise ConnectorError(LISTING_UNREACHABLE_MESSAGE) from None
            _raise_for_listing(response)
            page = _listing_page(response.body)
            mapped = [
                _remote_activity(entry, offset + index + 1)
                for index, entry in enumerate(page)
            ]
            before = len(activities)
            for activity in mapped:
                if activity.remote_id in activities:
                    continue
                activities[activity.remote_id] = activity
            if len(page) < LISTING_PAGE:
                break
            if len(activities) == before:
                raise ConnectorError(LISTING_REPEATED_MESSAGE)
            offset += LISTING_PAGE
        return _limit(
            session,
            tuple(
                activity
                for activity in activities.values()
                if floor is None or activity.start is None or activity.start >= floor
            ),
        )

    def fetch_activity(
        self, session: ConnectorSession, activity: RemoteActivity
    ) -> FetchResult:
        """The activity's original FIT file from Garmin's ZIP download (Req
        5.1-5.7, 6.1-6.3, 6.5-6.8). A 401, a 403 or a 429 past the waits ends the
        instance; a server error, a transport failure, an unreadable archive or
        any other status fails this one activity, and the fifth download in a
        row that met a server error or a transport failure ends the activity
        pull. Any other answer to the download, but for a 429 past the waits,
        resets that count."""
        state = self._state(session)
        url = f"{API_BASE}{FILE_PATH}{quote(activity.remote_id, safe='')}"
        try:
            response = self._get(session, url, {"Accept": FILE_ACCEPT})
        except TransportError:
            self._count_failure(state)
            raise
        status = response.status
        if 500 <= status < 600:
            self._count_failure(state)
            raise GarminDownloadError(FILE_UNAVAILABLE_MESSAGE.format(status=status))
        state.consecutive_failures = 0
        if status == 200:
            return _read_archive(response.body)
        if status == 404:
            return Declined(NO_FILE_MESSAGE)
        if status == 401:
            raise AuthFailure(
                AuthFailureKind.REJECTED, REJECTED_MESSAGE.format(status=401)
            )
        if status == 403:
            raise AuthFailure(AuthFailureKind.REJECTED, FILE_REFUSED_MESSAGE)
        raise GarminDownloadError(FILE_OTHER_MESSAGE.format(status=status))

    @staticmethod
    def _count_failure(state: _PullState) -> None:
        """One more download in a row that met a server error or could not
        reach Garmin; the fifth ends the activity pull (Req 6.6)."""
        state.consecutive_failures += 1
        if state.consecutive_failures >= CONSECUTIVE_FAILURE_STOP:
            raise ConnectorError(UNAVAILABLE_STOP_MESSAGE)

    def list_wellness(
        self, session: ConnectorSession, oldest: date | None
    ) -> WellnessListing:
        raise _not_built("the wellness listing")

    def package_wellness(
        self, session: ConnectorSession, days: tuple[WellnessDay, ...]
    ) -> WellnessPackage:
        raise _not_built("wellness packaging")
