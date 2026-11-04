"""Relay targets: the routes, field formats, bounds and outcome sets of a
target that runs on the relay (Strava is the first).

Standard library only, plus relative imports of sibling wire modules: this
file is byte-copied into the relay, where the same relative imports resolve
to the copied siblings. Error messages are fixed text that never interpolates
the input. `target_route` and `connect_page_path` refuse malformed parts with
`EnvelopeError`.
"""

from __future__ import annotations

import base64
import binascii
import math
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from .relay_envelope import EnvelopeError, is_target_id, is_user_code

STRAVA: Final = "strava"
TARGET_ROUTE_PREFIX: Final = "/v1/targets/"
ACTION_CONNECT: Final = "connect"
ACTION_CONNECT_POLL: Final = "connect/poll"
ACTION_PUBLISH: Final = "publish"
ACTION_UPLOAD: Final = "upload"
ACTION_DISCONNECT: Final = "disconnect"
TARGET_ACTIONS: Final[tuple[str, ...]] = (
    ACTION_CONNECT,
    ACTION_CONNECT_POLL,
    ACTION_PUBLISH,
    ACTION_UPLOAD,
    ACTION_DISCONNECT,
)
CONNECT_PAGE_PREFIX: Final = "/connect/"
LINK_FIELD: Final = "link"
PUBLICATION_ID_RE: Final = r"^[0-9a-f]{32}$"
SPORT_RE: Final = r"^[A-Z][A-Za-z]{0,31}$"
MAX_TITLE_CHARS: Final = 255
MAX_DESCRIPTION_CHARS: Final = 8000
MAX_FIT_BYTES: Final = 16 * 1024 * 1024
MAX_UPLOAD_REQUEST_BYTES: Final = 22 * 1024 * 1024

FITDOCS_SPORTS: Final[frozenset[str]] = frozenset(
    {"Ride", "Run", "Swim", "Walk", "Hike", "Rowing", "Workout"}
)
PUBLISH_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "publication_id",
        "sport",
        "start",
        "elapsed_s",
        "distance_m",
        "title",
        "description",
    }
)
UPLOAD_FIELDS: Final[frozenset[str]] = PUBLISH_FIELDS | {"fit"}
PUBLISH_OUTCOMES: Final[frozenset[str]] = frozenset(
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
UPLOAD_OUTCOMES: Final[frozenset[str]] = frozenset(
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

_PUBLICATION_ID = re.compile(PUBLICATION_ID_RE)
_SPORT = re.compile(SPORT_RE)
_FIT_MARKER: Final = b".FIT"
_MAX_FIT_BASE64_CHARS: Final = 4 * ((MAX_FIT_BYTES + 2) // 3)

_MSG_ROUTE: Final = "not a relay target route"
_MSG_PAGE: Final = "not a connect page path"
_MSG_FIELDS: Final = "the fields are not exactly the expected set"
_MSG_ID: Final = "the publication id is malformed"
_MSG_SPORT: Final = "the sport is malformed"
_MSG_START: Final = "the start is not an ISO 8601 time with an offset"
_MSG_NUMBER: Final = "a number is not null or a finite non-negative number"
_MSG_TITLE: Final = "the title is empty, too long or has a control character"
_MSG_DESCRIPTION: Final = "the description is too long or has a control character"
_MSG_FIT: Final = "the file is not base64, is too large or is not a FIT file"


@dataclass(frozen=True)
class PublishFacts:
    publication_id: str
    sport: str
    start: datetime
    elapsed_s: float | None
    distance_m: float | None
    title: str
    description: str


def target_route(target: str, action: str) -> str:
    if not is_target_id(target) or action not in TARGET_ACTIONS:
        raise EnvelopeError(_MSG_ROUTE)
    return f"{TARGET_ROUTE_PREFIX}{target}/{action}"


def connect_page_path(target: str, user_code: str) -> str:
    if not is_target_id(target) or not is_user_code(user_code):
        raise EnvelopeError(_MSG_PAGE)
    return f"{CONNECT_PAGE_PREFIX}{target}?code={user_code}"


def route_outcome(outcome: str | None, allowed: frozenset[str]) -> str | None:
    if isinstance(outcome, str) and outcome in allowed:
        return outcome
    return None


# --------------------------------------------------------------------------- #
# Field checks
# --------------------------------------------------------------------------- #


def _number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EnvelopeError(_MSG_NUMBER)
    try:
        number = float(value)
    except OverflowError:
        raise EnvelopeError(_MSG_NUMBER) from None
    if not math.isfinite(number) or number < 0:
        raise EnvelopeError(_MSG_NUMBER)
    return number


def _has_control(text: str, *, allowed: str = "") -> bool:
    return any(unicodedata.category(c) == "Cc" and c not in allowed for c in text)


def _start(value: object) -> datetime:
    if not isinstance(value, str):
        raise EnvelopeError(_MSG_START)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise EnvelopeError(_MSG_START) from None
    return parsed


def _checked(facts: PublishFacts) -> PublishFacts:
    """Return the facts when every field is in format, else raise."""
    if not isinstance(facts.publication_id, str) or not _PUBLICATION_ID.fullmatch(
        facts.publication_id
    ):
        raise EnvelopeError(_MSG_ID)
    if not isinstance(facts.sport, str) or not _SPORT.fullmatch(facts.sport):
        raise EnvelopeError(_MSG_SPORT)
    if (
        not isinstance(facts.start, datetime)
        or facts.start.tzinfo is None
        or facts.start.utcoffset() is None
    ):
        raise EnvelopeError(_MSG_START)
    _number(facts.elapsed_s)
    _number(facts.distance_m)
    title = facts.title
    if (
        not isinstance(title, str)
        or not 1 <= len(title) <= MAX_TITLE_CHARS
        or _has_control(title)
    ):
        raise EnvelopeError(_MSG_TITLE)
    description = facts.description
    if (
        not isinstance(description, str)
        or len(description) > MAX_DESCRIPTION_CHARS
        or _has_control(description, allowed="\n\t")
    ):
        raise EnvelopeError(_MSG_DESCRIPTION)
    return facts


def _check_fit(fit: bytes) -> bytes:
    if (
        not isinstance(fit, bytes)
        or len(fit) > MAX_FIT_BYTES
        or len(fit) < 12
        or fit[8:12] != _FIT_MARKER
    ):
        raise EnvelopeError(_MSG_FIT)
    return fit


def publish_fields(facts: PublishFacts) -> dict[str, object]:
    checked = _checked(facts)
    return {
        "publication_id": checked.publication_id,
        "sport": checked.sport,
        "start": checked.start.isoformat(),
        "elapsed_s": checked.elapsed_s,
        "distance_m": checked.distance_m,
        "title": checked.title,
        "description": checked.description,
    }


def upload_fields(facts: PublishFacts, fit: bytes) -> dict[str, object]:
    fields = publish_fields(facts)
    fields["fit"] = base64.b64encode(_check_fit(fit)).decode("ascii")
    return fields


def parse_publish_fields(fields: Mapping[str, object]) -> PublishFacts:
    if not isinstance(fields, Mapping) or set(fields) != PUBLISH_FIELDS:
        raise EnvelopeError(_MSG_FIELDS)
    return _parse(fields)


def parse_upload_fields(fields: Mapping[str, object]) -> tuple[PublishFacts, bytes]:
    if not isinstance(fields, Mapping) or set(fields) != UPLOAD_FIELDS:
        raise EnvelopeError(_MSG_FIELDS)
    facts = _parse(fields)
    encoded = fields["fit"]
    if not isinstance(encoded, str) or len(encoded) > _MAX_FIT_BASE64_CHARS:
        raise EnvelopeError(_MSG_FIT)
    try:
        fit = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise EnvelopeError(_MSG_FIT) from None
    return facts, _check_fit(fit)


def _parse(fields: Mapping[str, object]) -> PublishFacts:
    title = fields["title"]
    description = fields["description"]
    return _checked(
        PublishFacts(
            publication_id=fields["publication_id"],  # type: ignore[arg-type]
            sport=fields["sport"],  # type: ignore[arg-type]
            start=_start(fields["start"]),
            elapsed_s=_number(fields["elapsed_s"]),
            distance_m=_number(fields["distance_m"]),
            title=title,  # type: ignore[arg-type]
            description=description,  # type: ignore[arg-type]
        )
    )
