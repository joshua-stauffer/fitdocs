"""What produced a file, and the identity values a page records for its base.

Pure: every value is read from the activity's own ``file_id`` identity and its
session developer field, never from the device list (a HealthFit copy of a
Garmin ride lists a Garmin device but was written by HealthFit). Absent values
stay ``None``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC
from enum import StrEnum
from typing import Final

from fitdocs.contract import SESSION_UUID_FIELD, format_session_uuid
from fitdocs.model import Activity, FileIdentity

__all__ = [
    "DEVELOPMENT_MANUFACTURER",
    "SourceIdentity",
    "SourceKind",
    "device_digest",
    "source_identity",
    "source_kind",
]

DEVELOPMENT_MANUFACTURER: Final[str] = "development"
"""The ``file_id`` manufacturer HealthFit writes into every file it produces."""

_DIGEST_HEX_DIGITS: Final[int] = 16


class SourceKind(StrEnum):
    """What produced a file. Closed."""

    ORIGINAL = "original"
    PHONE_COPY = "phone_copy"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SourceIdentity:
    """The base values a page records for the file it follows."""

    kind: SourceKind
    elapsed_s: float | None
    distance_m: float | None
    device: str | None
    session_uuid: str | None


def source_kind(activity: Activity) -> SourceKind:
    """Classify a file from its own ``file_id`` and session developer field.

    ``PHONE_COPY`` when the manufacturer is ``development`` and a well-formed
    session UUID is recorded; ``ORIGINAL`` when a manufacturer is recorded and
    is not ``development``; otherwise ``UNKNOWN``.
    """
    manufacturer = activity.file_identity.manufacturer
    if manufacturer is None:
        return SourceKind.UNKNOWN
    if manufacturer != DEVELOPMENT_MANUFACTURER:
        return SourceKind.ORIGINAL
    if format_session_uuid(activity.developer_fields.get(SESSION_UUID_FIELD)):
        return SourceKind.PHONE_COPY
    return SourceKind.UNKNOWN


def device_digest(identity: FileIdentity) -> str | None:
    """16 hex digits identifying the recording device and creation instant.

    ``None`` unless manufacturer, serial and creation time are all recorded.
    The serial itself never appears in the result.
    """
    if (
        identity.manufacturer is None
        or identity.serial_number is None
        or identity.time_created is None
    ):
        return None
    created = identity.time_created.astimezone(UTC)
    text = (
        f"{identity.manufacturer}/{identity.serial_number}/{created:%Y-%m-%dT%H:%M:%SZ}"
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:_DIGEST_HEX_DIGITS]


def source_identity(activity: Activity) -> SourceIdentity:
    """The identity values a page records for the activity as its base."""
    return SourceIdentity(
        kind=source_kind(activity),
        elapsed_s=activity.summary.total_elapsed_time_s,
        distance_m=activity.summary.total_distance_m,
        device=device_digest(activity.file_identity),
        session_uuid=format_session_uuid(
            activity.developer_fields.get(SESSION_UUID_FIELD)
        ),
    )
