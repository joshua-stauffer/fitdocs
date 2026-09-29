"""Rank a page's files: the total order, the base and extras, the session UUID.

Pure. The rank of a file is decided by four keys, in order (Req 2.8): the
position of its precedence entry, the number of messages the FIT profile does
not define (more first), its creation time (later first, absent last) and its
content hash (ascending). The keys form a total order, so the roles of a set
of files do not depend on the order they arrived in.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from fitdocs.identity.kinds import SourceKind, source_identity
from fitdocs.model import Activity

__all__ = [
    "DEFAULT_PRECEDENCE",
    "PageRoles",
    "Precedence",
    "PrecedenceEntry",
    "SourceMember",
    "page_session_uuid",
    "rank_key",
    "rank_members",
    "resolve_precedence",
    "source_member",
]


@dataclass(frozen=True)
class PrecedenceEntry:
    """One position of the precedence: a kind, or ``original:<manufacturer>``."""

    kind: SourceKind
    manufacturer: str | None = None

    def __post_init__(self) -> None:
        if self.manufacturer is not None and self.kind is not SourceKind.ORIGINAL:
            raise ValueError("a manufacturer belongs only to an original entry")


Precedence = tuple[PrecedenceEntry, ...]

DEFAULT_PRECEDENCE: Final[Precedence] = (
    PrecedenceEntry(SourceKind.ORIGINAL, "garmin"),
    PrecedenceEntry(SourceKind.PHONE_COPY),
    PrecedenceEntry(SourceKind.ORIGINAL),
    PrecedenceEntry(SourceKind.UNKNOWN),
)
"""Maintainer decision 2026-09-29: a Garmin file, then the HealthFit phone
copy, then every other original (a Stryd file), then unknown files."""

_APPEND_ORDER: Final[tuple[SourceKind, ...]] = (
    SourceKind.ORIGINAL,
    SourceKind.PHONE_COPY,
    SourceKind.UNKNOWN,
)


def resolve_precedence(entries: Sequence[PrecedenceEntry]) -> Precedence:
    """A configured list replaces the default; unnamed kinds are appended.

    Only a bare kind entry names a kind; an ``original:<m>`` entry never does.
    The default's ``original:garmin`` is not appended.
    """
    named = {entry.kind for entry in entries if entry.manufacturer is None}
    appended = tuple(
        PrecedenceEntry(kind) for kind in _APPEND_ORDER if kind not in named
    )
    return tuple(entries) + appended


@dataclass(frozen=True)
class SourceMember:
    """One resolved file of a page, with what its rank reads."""

    ref: str
    sha: str
    kind: SourceKind
    manufacturer: str | None
    undocumented_messages: int | None
    time_created: datetime | None
    session_uuid: str | None


def source_member(ref: str, sha: str, activity: Activity) -> SourceMember:
    """Build a member from a parsed file.

    Manufacturer and creation time come from the file's own ``file_id``, never
    from the device list.
    """
    identity = source_identity(activity)
    return SourceMember(
        ref=ref,
        sha=sha,
        kind=identity.kind,
        manufacturer=activity.file_identity.manufacturer,
        undocumented_messages=activity.provenance.undocumented_messages,
        time_created=activity.file_identity.time_created,
        session_uuid=identity.session_uuid,
    )


def _position(member: SourceMember, precedence: Precedence) -> int:
    if member.kind is SourceKind.ORIGINAL and member.manufacturer is not None:
        specific = PrecedenceEntry(SourceKind.ORIGINAL, member.manufacturer)
        if specific in precedence:
            return precedence.index(specific)
    return precedence.index(PrecedenceEntry(member.kind))


def rank_key(
    member: SourceMember, precedence: Precedence
) -> tuple[int, int, float, str]:
    """The four keys of Req 2.8; lower is better.

    Raises ``ValueError`` when the precedence has no entry for the member's
    kind (a list that :func:`resolve_precedence` did not complete).
    """
    count = member.undocumented_messages
    created = member.time_created
    return (
        _position(member, precedence),
        1 if count is None else -count,
        float("inf") if created is None else -created.timestamp(),
        member.sha,
    )


@dataclass(frozen=True)
class PageRoles:
    """A page's base, its extras (best first) and its unresolved references."""

    base: SourceMember
    extras: tuple[SourceMember, ...]
    unresolved: tuple[str, ...]

    @property
    def sources(self) -> tuple[str, ...]:
        """Ascending rank, the base last (Req 5.2)."""
        return (
            self.unresolved
            + tuple(member.ref for member in reversed(self.extras))
            + (self.base.ref,)
        )


def rank_members(
    resolved: Sequence[SourceMember],
    unresolved: Sequence[str],
    precedence: Precedence,
) -> PageRoles:
    """The base is the lowest key; the rest are extras, best first.

    Precondition: at least one resolved member. Unresolved references keep the
    order given and are never the base.
    """
    if not resolved:
        raise ValueError("a page needs at least one resolved member")
    ranked = sorted(resolved, key=lambda member: rank_key(member, precedence))
    return PageRoles(
        base=ranked[0], extras=tuple(ranked[1:]), unresolved=tuple(unresolved)
    )


def page_session_uuid(roles: PageRoles, recorded: str | None) -> str | None:
    """The session UUID of the first of base, extras that carries one, else
    the page's recorded value, else ``None`` (Req 5.5)."""
    for member in (roles.base, *roles.extras):
        if member.session_uuid is not None:
            return member.session_uuid
    return recorded
