"""The intervals.icu connector (design.md "IntervalsConnector").

Lists, filters and fetches intervals.icu originals for the key's own athlete
with a personal API key. This module is the one module in the connectors
package that names the service's address (the service-neutral scan admits it
here, in its own tests and in its own documentation section only). It imports only the
standard library and ``fitdocs.connectors.{errors,http,protocol,secrets}``,
builds no HTTP client of its own, and reads no clock: ``session.now`` is the
only time source.

Task 3.1 declares the connector, its constants and its settings parser; the
three operations raise :class:`NotImplementedError` until later tasks
implement the key check, the listing and the file fetch.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from fitdocs.connectors.errors import ConnectorSettingsError
from fitdocs.connectors.http import MAX_RESPONSE_BYTES
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

_SOURCE_NAME_RE = re.compile(SOURCE_NAME_PATTERN)
_NOT_YET = "implemented by a later intervals-connector task (3.2-3.4)"


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
        raise NotImplementedError(_NOT_YET)

    def list_activities(
        self, session: ConnectorSession, since: datetime | None
    ) -> Listing:
        raise NotImplementedError(_NOT_YET)

    def fetch_activity(
        self, session: ConnectorSession, activity: RemoteActivity
    ) -> FetchResult:
        raise NotImplementedError(_NOT_YET)


def _sources_error(offending: object) -> ConnectorSettingsError:
    return ConnectorSettingsError(
        "sources",
        "sources must be a non-empty list of upper-case source names "
        f'such as "GARMIN_CONNECT", got {offending!r}',
    )
