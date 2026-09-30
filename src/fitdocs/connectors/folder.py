"""The built-in local-folder connector (design.md "FolderConnector",
Req 13.1-13.9).

The network-free reference connector: a local directory as a source. It
requires no authentication, pulls activities, and reuses the inbox's own
candidate-selection and stability-check rules (:mod:`fitdocs.inbox`) rather
than re-implementing them, so a file this connector lists obeys exactly the
same ``.fit``-extension, dot-component, and junk-pattern rules a file
dropped directly into the inbox does.

Reads only: :meth:`FolderConnector.list_activities` and
:meth:`FolderConnector.fetch_activity` never write, move, rename, or delete
anything under the configured source directory (Req 13.5) -- pinned by
``tests/connectors/test_folder.py``'s before/after tree snapshot, which
records every entry's kind (file or directory), permission bits,
modification time, and (for files) bytes, so a stray ``mkdir`` or ``chmod``
reds it exactly as a stray write would -- and neither makes a network
request (Req 13.9).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from fitdocs import inbox as inbox_module
from fitdocs.connectors.errors import ConnectorError, ConnectorSettingsError
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    ConnectorSession,
    CredentialField,
    Deferred,
    Fetched,
    FetchResult,
    Listing,
    ListingDeferral,
    RemoteActivity,
    SettingsContext,
)

FOLDER_CONNECTOR_ID: Final[str] = "folder"


@dataclass(frozen=True)
class FolderSettings:
    """Validated ``[connectors.<instance>]`` configuration for a ``folder``
    instance (design: "FolderConnector")."""

    source: Path
    """The resolved, lexically normalized source directory."""

    settle_seconds: float
    """The settle interval this instance uses; defaults to the inbox's own
    default (:data:`fitdocs.inbox.DEFAULT_INBOX_SETTINGS`.settle_seconds)."""


class FolderConnector:
    """A local directory as a source (Req 13.1-13.9)."""

    connector_id = FOLDER_CONNECTOR_ID
    display_name = "Local folder"
    auth_style = AuthStyle.NONE
    capabilities = frozenset({Capability.PULL_ACTIVITIES})
    credential_fields: tuple[CredentialField, ...] = ()

    def parse_settings(
        self, table: Mapping[str, object], context: SettingsContext
    ) -> FolderSettings:
        """Validate ``path`` (required) and ``settle_seconds`` (optional).

        ``path``: an absolute path is used as given; a relative path is
        joined to ``context.data_root``. Both are lexically normalized with
        ``os.path.normpath`` -- no filesystem access, so a containment
        violation is reachable before any I/O, matching
        :func:`fitdocs.inbox._resolve_inbox_relative`'s rule. Refused when
        the resolved path equals, lies inside, or contains
        ``context.inbox`` -- each case checked and reported separately, and
        the message names both paths (Req 13.7).

        ``settle_seconds``: optional, a non-negative real number, not a
        ``bool`` (``bool`` subclasses ``int`` in Python); defaults to
        :data:`fitdocs.inbox.DEFAULT_INBOX_SETTINGS`.settle_seconds
        (Req 13.1). Unknown keys are ignored.
        """
        raw_path = table.get("path")
        if not isinstance(raw_path, str) or raw_path == "":
            raise ConnectorSettingsError(
                "path",
                f"path must be a non-empty string, got {raw_path!r} "
                f"({type(raw_path).__name__})",
            )

        candidate = Path(raw_path)
        joined = candidate if candidate.is_absolute() else context.data_root / candidate
        source = Path(os.path.normpath(joined))
        inbox_path = Path(os.path.normpath(context.inbox))

        if source == inbox_path:
            raise ConnectorSettingsError(
                "path", f"path {source} must not equal the inbox {inbox_path}"
            )
        if _contains(inbox_path, source):
            raise ConnectorSettingsError(
                "path",
                f"path {source} must not lie inside the inbox {inbox_path}",
            )
        if _contains(source, inbox_path):
            raise ConnectorSettingsError(
                "path",
                f"path {source} must not contain the inbox {inbox_path}",
            )

        settle_seconds = self._settle_seconds(table)

        return FolderSettings(source=source, settle_seconds=settle_seconds)

    def _settle_seconds(self, table: Mapping[str, object]) -> float:
        if "settle_seconds" not in table:
            return inbox_module.DEFAULT_INBOX_SETTINGS.settle_seconds
        value = table["settle_seconds"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ConnectorSettingsError(
                "settle_seconds",
                f"settle_seconds must be a non-negative number, got {value!r} "
                f"({type(value).__name__})",
            )
        return float(value)

    def list_activities(
        self, session: ConnectorSession, since: datetime | None
    ) -> Listing:
        """List every stable ``.fit`` file under the configured source
        (Req 13.2, 13.3, 13.8).

        ``since`` is ignored (Req 13.8): the folder connector states no
        start time for anything it lists, so a pull always considers the
        whole source tree. Candidates come from
        :func:`fitdocs.inbox.select_candidates` under
        :data:`fitdocs.inbox.DEFAULT_INBOX_SETTINGS` -- the inbox's own
        ``.fit``-extension, dot-component, and junk-pattern rules, never
        reimplemented here -- then settled through
        :func:`fitdocs.inbox.settle` using the session's injected
        ``sleep``; anything unstable becomes a deferral rather than a
        listed activity (Req 13.3). A stable candidate that cannot be
        ``stat``'d a second time (to compute its revision) is likewise
        deferred rather than listed or failed.
        """
        del since
        settings = cast(FolderSettings, session.settings)
        source = settings.source
        if not source.is_dir():
            raise ConnectorError(
                f"{source}: folder connector source is missing or not a directory"
            )

        candidates = inbox_module.select_candidates(
            source, inbox_module.DEFAULT_INBOX_SETTINGS
        )
        settled = inbox_module.settle(
            candidates,
            settle_seconds=settings.settle_seconds,
            sleep=session.sleep,
        )

        deferred: list[ListingDeferral] = [
            ListingDeferral(subject=note.subject, reason=note.detail)
            for note in settled.deferred
        ]

        activities: list[RemoteActivity] = []
        for stable in settled.stable:
            try:
                info = stable.path.stat()
            except OSError:
                deferred.append(
                    ListingDeferral(
                        subject=stable.rel,
                        reason=(
                            f"{stable.rel}: could not be observed "
                            "(vanished or unreadable)"
                        ),
                    )
                )
                continue
            activities.append(
                RemoteActivity(
                    remote_id=stable.rel,
                    original_available=True,
                    revision=f"{info.st_size}:{info.st_mtime_ns}",
                    suggested_name=stable.path.name,
                )
            )

        return Listing(activities=tuple(activities), deferred=tuple(deferred))

    def fetch_activity(
        self, session: ConnectorSession, activity: RemoteActivity
    ) -> FetchResult:
        """Read ``activity``'s bytes from the source directory
        (Req 13.3).

        A read failure (``OSError`` -- an unreadable file, or one whose
        cloud placeholder has not been downloaded yet) is a deferral, never
        a failure. A ``stat`` taken after the read that disagrees with
        ``activity.revision`` means the file changed while being read, also
        a deferral. Otherwise the bytes are returned.
        """
        settings = cast(FolderSettings, session.settings)
        path = settings.source / activity.remote_id
        try:
            data = path.read_bytes()
        except OSError:
            return Deferred(
                "could not be read (a cloud file that has not been "
                "downloaded yet is deferred until it is)"
            )

        try:
            info = path.stat()
        except OSError:
            return Deferred("changed while being read")

        revision = f"{info.st_size}:{info.st_mtime_ns}"
        if revision != activity.revision:
            return Deferred("changed while being read")

        return Fetched(data=data)


def _contains(parent: Path, child: Path) -> bool:
    """Whether ``child`` lies strictly inside ``parent`` (both already
    lexically normalized). ``parent == child`` is checked by the caller
    separately, so this only answers the strict-containment question."""
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return child != parent
