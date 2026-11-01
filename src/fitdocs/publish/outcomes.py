"""The closed, append-only publish vocabulary (publish-core Req 1.1-1.5).

Members are only ever appended; the relay keeps a pinned copy of this file,
so an edit to an existing member or explanation breaks that copy. Imports
only the standard library so the module can be carried alone.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final


class PublishCode(StrEnum):
    """Every outcome a publish run can report, in the pinned order."""

    WOULD_POST = "would_post"
    WOULD_UPDATE = "would_update"
    UNCHANGED = "unchanged"
    NOT_OPTED_IN = "not_opted_in"
    OPT_IN_INVALID = "opt_in_invalid"
    UNKNOWN_TARGET = "unknown_target"
    PAGE_OUT_OF_DATE = "page_out_of_date"
    PAGE_NEWER = "page_newer"
    PAGE_DAMAGED = "page_damaged"
    PAGE_UNREADABLE = "page_unreadable"
    POST_INVALID = "post_invalid"
    TEMPLATE_INVALID = "template_invalid"
    VALUE_MISSING = "value_missing"
    TITLE_EMPTY = "title_empty"
    ACTIVITY_FACTS_MISSING = "activity_facts_missing"
    LEDGER_CONFLICT = "ledger_conflict"
    POSTED = "posted"
    UPLOADED = "uploaded"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    NOT_UPDATABLE = "not_updatable"
    ACTIVITY_FILE_MISSING = "activity_file_missing"
    NOT_CONNECTED = "not_connected"
    CREDENTIALS_UNREADABLE = "credentials_unreadable"
    AUTH_REJECTED = "auth_rejected"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    REJECTED = "rejected"
    UNCONFIRMED = "unconfirmed"
    TARGET_ERROR = "target_error"
    NOT_ATTEMPTED = "not_attempted"
    PUBLISHED_NOT_WRITTEN = "published_not_written"
    READY = "ready"
    LOCAL_RECORD_UNREADABLE = "local_record_unreadable"


@dataclass(frozen=True)
class CodeInfo:
    """One code with its fixed explanation and its five flags."""

    code: PublishCode
    explanation: str
    landed: bool  # the target confirmed the post is on its activity
    failure: bool  # counts toward exit status 1
    from_target: bool  # a target may return it
    stops_target: bool  # nothing more is sent to that target this run
    target_state: bool  # the target listing may show it


def _info(code: PublishCode, flags: str, text: str) -> CodeInfo:
    held = flags.split()
    return CodeInfo(
        code=code,
        explanation=text,
        landed="L" in held,
        failure="F" in held,
        from_target="T" in held,
        stops_target="S" in held,
        target_state="St" in held,
    )


_TABLE: Final[tuple[CodeInfo, ...]] = (
    _info(
        PublishCode.WOULD_POST,
        "",
        (
            "This page has no post on this target yet, and `fitdocs publish --yes` "
            "would post it."
        ),
    ),
    _info(
        PublishCode.WOULD_UPDATE,
        "",
        (
            "This page's post changed since it last landed on this target, and "
            "`fitdocs publish --yes` would update it."
        ),
    ),
    _info(
        PublishCode.UNCHANGED,
        "",
        "This target already carries this page's current post, so nothing is sent.",
    ),
    _info(
        PublishCode.NOT_OPTED_IN,
        "",
        "This page's publish key does not name this target, so nothing is sent.",
    ),
    _info(
        PublishCode.OPT_IN_INVALID,
        "F",
        (
            "This page's publish key is neither a target name nor a list of "
            "distinct target names, so nothing is sent from it."
        ),
    ),
    _info(
        PublishCode.UNKNOWN_TARGET,
        "F",
        (
            "This page's publish key names something that is not a configured "
            "publish target, so nothing is sent to it."
        ),
    ),
    _info(
        PublishCode.PAGE_OUT_OF_DATE,
        "F",
        (
            "This page was written by an older fitdocs; run `fitdocs regen` before "
            "publishing it."
        ),
    ),
    _info(
        PublishCode.PAGE_NEWER,
        "F",
        (
            "This page was written by a newer fitdocs, so this installation does "
            "not publish it."
        ),
    ),
    _info(
        PublishCode.PAGE_DAMAGED,
        "F",
        (
            "This page's region markers are damaged or missing; restore them by "
            "hand before publishing it."
        ),
    ),
    _info(
        PublishCode.PAGE_UNREADABLE,
        "F",
        "This page could not be read as a workout page, so nothing is sent from it.",
    ),
    _info(
        PublishCode.POST_INVALID,
        "F",
        (
            "This page's post region is not a title line, a blank line and a "
            "description, so nothing is sent from it."
        ),
    ),
    _info(
        PublishCode.TEMPLATE_INVALID,
        "F",
        "This page's post region has a template error, so nothing is sent from it.",
    ),
    _info(
        PublishCode.VALUE_MISSING,
        "F",
        (
            "A placeholder outside an optional clause has no value on this page, so"
            " nothing is sent."
        ),
    ),
    _info(
        PublishCode.TITLE_EMPTY,
        "F",
        "The composed title is empty, so nothing is sent.",
    ),
    _info(
        PublishCode.ACTIVITY_FACTS_MISSING,
        "F T",
        "The facts that identify this page's activity are missing, so nothing is sent.",
    ),
    _info(
        PublishCode.LEDGER_CONFLICT,
        "F",
        (
            "The publish ledger holds more than one record for this page, or one "
            "record matches several pages, or a new record's key would match several "
            "pages, so nothing is sent."
        ),
    ),
    _info(
        PublishCode.POSTED,
        "L T",
        "The target's activity now carries this page's title and description.",
    ),
    _info(
        PublishCode.UPLOADED,
        "L T",
        (
            "No matching activity existed, so the target created one from this "
            "page's activity file with its title and description."
        ),
    ),
    _info(
        PublishCode.NOT_FOUND,
        "F T",
        (
            "The target has no activity matching this page and uploading is not "
            "enabled for it, so nothing was changed."
        ),
    ),
    _info(
        PublishCode.AMBIGUOUS,
        "F T",
        (
            "More than one activity on the target matches this page, so nothing was"
            " changed."
        ),
    ),
    _info(
        PublishCode.NOT_UPDATABLE,
        "F T",
        (
            "The matching activity cannot be changed through this target, so "
            "nothing was changed."
        ),
    ),
    _info(
        PublishCode.ACTIVITY_FILE_MISSING,
        "F T",
        (
            "Uploading needs this page's activity file, which is not in the "
            "archive, so nothing was changed."
        ),
    ),
    _info(
        PublishCode.NOT_CONNECTED,
        "F T S St",
        "This target has no usable credentials; run `fitdocs connect` for it.",
    ),
    _info(
        PublishCode.CREDENTIALS_UNREADABLE,
        "F S St",
        (
            "This target's stored credentials could not be read or are not private "
            "to you; fix the file or connect it again."
        ),
    ),
    _info(
        PublishCode.AUTH_REJECTED,
        "F T S",
        "The target refused the stored credentials; connect it again.",
    ),
    _info(
        PublishCode.PERMISSION_DENIED,
        "F T S",
        (
            "The credentials do not allow this change; connect again and grant the "
            "permission it needs."
        ),
    ),
    _info(
        PublishCode.RATE_LIMITED,
        "F T S",
        (
            "The target's rate limit was reached, so nothing more is sent to it in "
            "this run; try again later."
        ),
    ),
    _info(
        PublishCode.UNAVAILABLE,
        "F T S",
        (
            "The target could not be reached or failed on its side, so nothing more"
            " is sent to it in this run; try again later."
        ),
    ),
    _info(
        PublishCode.REJECTED,
        "F T",
        "The target refused the request as invalid, so nothing was changed.",
    ),
    _info(
        PublishCode.UNCONFIRMED,
        "F T",
        (
            "The request was sent but its result is unknown; the next run checks "
            "the target before sending again."
        ),
    ),
    _info(
        PublishCode.TARGET_ERROR,
        "F",
        (
            "The target failed unexpectedly, which is a fitdocs defect, and nothing"
            " more was sent for this page."
        ),
    ),
    _info(
        PublishCode.NOT_ATTEMPTED,
        "F",
        (
            "Nothing was sent, because an earlier result in this run stopped "
            "publishing to this target."
        ),
    ),
    _info(
        PublishCode.PUBLISHED_NOT_WRITTEN,
        "F",
        (
            "The outcomes were recorded, but this page's published region could not"
            " be rewritten; the next `fitdocs publish --yes` rewrites it."
        ),
    ),
    _info(
        PublishCode.READY,
        "St",
        "This target is configured and has the credentials it needs.",
    ),
    _info(
        PublishCode.LOCAL_RECORD_UNREADABLE,
        "F T",
        (
            "This target could not read its own local record of this connection's "
            "activities, so it could not rule out that the activity already exists "
            "and uploaded nothing."
        ),
    ),
)

OUTCOMES: Final[Mapping[PublishCode, CodeInfo]] = MappingProxyType(
    {info.code: info for info in _TABLE}
)
LANDED_CODES: Final[frozenset[PublishCode]] = frozenset(
    c for c, i in OUTCOMES.items() if i.landed
)
FAILURE_CODES: Final[frozenset[PublishCode]] = frozenset(
    c for c, i in OUTCOMES.items() if i.failure
)
TARGET_CODES: Final[frozenset[PublishCode]] = frozenset(
    c for c, i in OUTCOMES.items() if i.from_target
)
STOPPING_CODES: Final[frozenset[PublishCode]] = frozenset(
    c for c, i in OUTCOMES.items() if i.stops_target
)
STATE_CODES: Final[frozenset[PublishCode]] = frozenset(
    c for c, i in OUTCOMES.items() if i.target_state
)


def explanation(code: PublishCode) -> str:
    """The fixed one-sentence explanation of ``code``."""
    return OUTCOMES[code].explanation
