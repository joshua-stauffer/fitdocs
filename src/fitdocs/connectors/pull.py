"""Orchestrate one pull over the selected instances (design.md "PullEngine",
Req 1.9, 4.7, 6.4-6.13, 7.2, 7.4, 7.7, 8.5, 10.1, 10.2, 10.5, 11.5, 13.4).

:func:`run_pull` is the whole engine: per instance, in design.md's stated
order, it loads the ledger, sweeps archived deliveries (unless dry run),
resolves credentials through the store and the environment (a not-connected
instance ends the instance with its own message, which already names the
connect command and the missing variables; an unreadable, permissive, or
malformed stored credentials file -- a
:class:`fitdocs.connectors.credentials.CredentialStoreError` -- ends the
same way, with that instance's own message, e.g. ``chmod 600 <path>``),
renews a login-style token expiring within the margin through an
authentication-mode session and persists it before any data request -- also
under dry run (Req 4.7, 6.9) -- selects activities and enabled wellness,
builds one data session, computes the activity listing window start, and
lists and validates the connector's activities,
classifies each one, advances the watermark -- never backward, see
:func:`_compute_watermark` -- over the contiguous run of start-grouped
entries that end up final, and saves the ledger in a ``finally`` so a save
happens on every exit -- success, an instance error, or an interruption
(``KeyboardInterrupt`` is re-raised after the save completes, never
swallowed).

An ``AuthFailure``, ``ConnectorError`` or ``CredentialStoreError`` from
credential resolution ends the instance. Any ``Exception`` from token
renewal does likewise. These errors use :func:`_instance_error`: the type
and redacted message, with an ``AuthFailure``'s kind-specific next step or
an unavailable-service next step for ``TransportError``.

A terminal activity listing or fetch error uses the same renderer. An
activity ``AuthFailure`` suppresses wellness; an ordinary terminal activity
error leaves wellness eligible. Other activity fetch exceptions become
failed notes for individual activities and allow the activity loop to
continue. An enabled wellness listing exception becomes that step's own
error and leaves later instances eligible. A ``BaseException`` such as
``KeyboardInterrupt`` propagates after the current ledger holder is saved.
Wellness packages changed days in calendar-year groups, checks their declared
format and extension, and holds bytes already archived or pending. Successful
deliveries update pending records and attribution; held groups update days
only. The current ledger holder is updated after each recorded group.
Every reported or recorded detail passes ``redactor.redact``. Renewed token
values are registered with the redactor before persistence.

A sweep failure (an ``OSError`` reading or removing a pending file,
``connectors/delivery.py``'s ``SweepResult.failures``) is reported as a
deferred note keyed by the pending path, not a failed one -- the file is
left exactly as it is and the next sweep retries it (R1 controller ruling).
A fetched activity whose remote id already has a pending delivery in the
ledger (a new revision of a file already fetched but not yet archived) is
handled specially: if the new bytes hash the same as the pending entry's
recorded ``sha256``, the existing inbox copy and its pending location are
kept untouched and only the ledger entry's revision moves forward -- the
ledger entry's own outcome stays ``DELIVERED``, but since nothing was
written this run, it is reported in ``held`` (Req 6.8, "already held"), not
``delivered``. If the hash differs, that old copy is left in the inbox but
dropped from the ledger's tracking entirely (released, untracked -- the
drain will find it like any other file) and the new bytes are delivered
fresh, reported in ``delivered`` as usual (R2 controller ruling). A
``deliver`` call that raises ``OSError`` becomes a failed note carrying
``f"{type(exc).__name__}: {exc}"`` (redacted) for that one activity; the
instance continues with its remaining entries (controller ruling d).

For an ``AuthStyle.NONE`` connector (the folder connector, the scripted
puller), :func:`fitdocs.connectors.credentials.resolve_credentials` always
answers with a credential access that has no values and never expires,
so token renewal is unnecessary. A
``KeyboardInterrupt``, or any exception this module does not itself catch,
still propagates through this module's own ``finally``-save and out of
:func:`run_pull` unmodified.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Final, cast

from fitdocs import layout
from fitdocs.connectors.credentials import (
    CredentialStore,
    CredentialStoreError,
    resolve_credentials,
)
from fitdocs.connectors.delivery import (
    deliver,
    delivery_name,
    is_fit,
    sweep,
    wellness_archived,
    wellness_delivery_name,
    wellness_package_problem,
)
from fitdocs.connectors.errors import (
    AuthFailure,
    AuthFailureKind,
    ConnectorError,
    next_step,
)
from fitdocs.connectors.http import CallMode, HttpClient, Transport, TransportError
from fitdocs.connectors.ledger import (
    Ledger,
    LedgerEntry,
    LedgerError,
    Outcome,
    WellnessLedger,
    WellnessPending,
    load_ledger,
    save_ledger,
)
from fitdocs.connectors.protocol import (
    ActivityPuller,
    AuthStyle,
    Capability,
    ConnectorSession,
    Declined,
    Deferred,
    Fetched,
    RemoteActivity,
    TokenIssuer,
    WellnessDay,
    WellnessPuller,
)
from fitdocs.connectors.secrets import Redactor
from fitdocs.connectors.settings import ConnectorInstance

__all__ = [
    "PullOptions",
    "PullNote",
    "Delivered",
    "InstancePullReport",
    "PullReport",
    "run_pull",
]

_CONTROL_CHARS_RE: Final[re.Pattern[str]] = re.compile(r"[\x00-\x1f\x7f]")
_MAX_REMOTE_ID_LEN: Final[int] = 512
ATTRIBUTION_DROPPED: Final[str] = (
    "the connector no longer attributes any wellness field to {platform}; "
    "if {platform} data stopped reaching the service, import {platform}'s own "
    "export instead (see the wellness guide)"
)
_MAX_REVISION_LEN: Final[int] = 512

_TOKEN_RENEWAL_MARGIN: Final[timedelta] = timedelta(seconds=60)


@dataclass(frozen=True)
class PullOptions:
    """One run's options (design.md "PullEngine")."""

    since: datetime | None
    """The ``--since`` override (UTC-aware), or ``None``."""

    dry_run: bool


@dataclass(frozen=True)
class PullNote:
    """One reported reason, already redacted."""

    subject: str
    """A remote id, an inbox-relative path, or the instance name."""

    detail: str


@dataclass(frozen=True)
class Delivered:
    """One file delivered into the inbox this run."""

    remote_id: str
    path: str
    """Inbox-relative POSIX path."""


@dataclass(frozen=True)
class WellnessDelivered:
    """A wellness file delivered with its date span and day count."""

    span: str
    days: int
    path: str


@dataclass(frozen=True)
class WellnessPullReport:
    """One instance's wellness listing and delivery outcome."""

    listed: int
    unchanged: int
    delivered: tuple[WellnessDelivered, ...]
    would_deliver: tuple[str, ...]
    held: tuple[str, ...]
    failed: tuple[PullNote, ...]
    notices: tuple[PullNote, ...]
    error: PullNote | None


@dataclass(frozen=True)
class InstancePullReport:
    """One instance's whole pull outcome (design.md "PullEngine")."""

    name: str
    connector_id: str
    listed: int
    delivered: tuple[Delivered, ...]
    would_fetch: tuple[str, ...]
    """Remote ids; non-empty only under ``--dry-run``."""

    held: tuple[str, ...]
    """Remote ids already final in the ledger, or bytes already held."""

    skipped: tuple[PullNote, ...]
    deferred: tuple[PullNote, ...]
    failed: tuple[PullNote, ...]
    removed: tuple[str, ...]
    """Inbox-relative paths removed by the sweep."""

    error: PullNote | None
    """The instance could not pull at all; ``detail`` carries the next step."""

    wellness: WellnessPullReport | None = None


@dataclass(frozen=True)
class PullReport:
    """The whole run's report (design.md "PullEngine")."""

    inbox: str
    dry_run: bool
    instances: tuple[InstancePullReport, ...]

    @property
    def failed(self) -> bool:
        """Whether any instance errored, or any instance has a failed note."""
        return any(
            instance.error is not None
            or len(instance.failed) > 0
            or (
                instance.wellness is not None
                and (
                    instance.wellness.error is not None
                    or len(instance.wellness.failed) > 0
                )
            )
            for instance in self.instances
        )


def _empty_report(
    name: str, connector_id: str, *, error: PullNote | None = None
) -> InstancePullReport:
    return InstancePullReport(
        name=name,
        connector_id=connector_id,
        listed=0,
        delivered=(),
        would_fetch=(),
        held=(),
        skipped=(),
        deferred=(),
        failed=(),
        removed=(),
        error=error,
    )


def _window_start(
    since: datetime | None, watermark: datetime | None, lookback_days: int
) -> datetime | None:
    """The listing window start (design.md "PullEngine" step 5, Req 6.4).

    ``since`` (the ``--since`` override) wins outright when given; otherwise
    the watermark less the instance's look-back when a watermark exists;
    otherwise ``None`` (no earliest start time at all).
    """
    if since is not None:
        return since
    if watermark is not None:
        return watermark - timedelta(days=lookback_days)
    return None


def _instance_error(exc: Exception, *, name: str, redactor: Redactor) -> PullNote:
    """Render ``exc`` as this instance's terminal error (design.md "PullEngine"
    step 9; Req 6.10, 10.2, 10.5): the exception's type and its redacted
    message, matching ``connectors/delivery.py``'s ``deliver`` ``OSError``
    convention this module already follows. An :class:`AuthFailure` additionally
    carries its kind's next step (design.md "ConnectEngine"'s table,
    :func:`fitdocs.connectors.errors.next_step`) -- a plain
    :class:`ConnectorError` (including ``NotConnectedError``) needs no
    addendum, since its own message already states the next step (e.g. the
    ``fitdocs connect <name>`` command and the missing variable names). A
    :class:`~fitdocs.connectors.http.TransportError` also gets an addendum:
    ``HttpClient``'s own :attr:`~fitdocs.connectors.errors.AuthFailureKind.
    UNAVAILABLE`` guidance, with no known retry wait, since
    :func:`fitdocs.connectors.http.auth_failure_from` maps a transport-level
    failure to that same kind (controller ruling, Req 6.10 "with its reason
    and next step").
    """
    detail = redactor.redact(f"{type(exc).__name__}: {exc}")
    if isinstance(exc, AuthFailure):
        step = next_step(exc.kind, name=name, retry_after_s=exc.retry_after_s)
        detail = f"{detail} {step}"
    elif isinstance(exc, TransportError):
        step = next_step(AuthFailureKind.UNAVAILABLE, name=name, retry_after_s=None)
        detail = f"{detail} {step}"
    return PullNote(subject=name, detail=detail)


def _validate_entry(activity: RemoteActivity) -> str | None:
    """The first reason ``activity`` is not a usable listing entry, or ``None``.

    Checks the shape design.md's step 6 names: a non-empty, control-character-free
    ``remote_id`` no longer than 512 characters; a timezone-aware ``start`` when
    given; a non-negative ``duration_s`` when given; and a non-empty
    ``unavailable_reason`` whenever ``original_available`` is ``False``. Does
    not check for a duplicate ``remote_id`` within the listing -- that needs
    the whole listing at once, and is checked separately by the caller.
    """
    remote_id = activity.remote_id
    if (
        not remote_id
        or len(remote_id) > _MAX_REMOTE_ID_LEN
        or _CONTROL_CHARS_RE.search(remote_id)
    ):
        return f"invalid remote id {remote_id!r}"
    if activity.start is not None and activity.start.tzinfo is None:
        return f"{remote_id}: start must be timezone-aware"
    if activity.duration_s is not None and activity.duration_s < 0:
        return f"{remote_id}: duration must not be negative"
    if not activity.original_available and not activity.unavailable_reason:
        return f"{remote_id}: marked unavailable with no reason"
    return None


def _release_replaced_pending(
    held_hashes: set[str],
    owned_paths: dict[str, str],
    replaced: LedgerEntry | None,
    ledger: Ledger,
) -> None:
    """Stop treating a replaced pending delivery as tracked.

    ``replaced`` is the entry this id had before the activity just recorded
    (``ledger`` already holds the replacement). If it was pending, its copy
    is now released: its path leaves ``owned_paths`` (so ``deliver`` never
    "reuses" the released file for another activity) and its hash leaves
    ``held_hashes`` -- unless some other entry in ``ledger`` still pends
    with the same bytes.
    """
    if replaced is None or replaced.pending is None or replaced.sha256 is None:
        return
    if owned_paths.get(replaced.pending) == replaced.sha256:
        del owned_paths[replaced.pending]
    if any(entry.sha256 == replaced.sha256 for entry in ledger.pending_entries()):
        return
    held_hashes.discard(replaced.sha256)


def _compute_watermark(
    entries: Sequence[RemoteActivity], ledger: Ledger
) -> datetime | None:
    """The newest ``start`` of the contiguous, ascending run of *groups* of
    ``entries`` sharing one ``start`` value that are entirely final in
    ``ledger`` (design.md "PullEngine" step 8, Req 7.2, 7.7).

    ``entries`` is the *raw* listing -- every entry this pull saw with an
    aware ``start``, including one that failed validation or repeated a
    remote id (the controller's R(b) ruling: such an entry still blocks,
    because it is unrecorded and so never final). A start-less or naive-start
    entry never participates: it is excluded up front, so it can neither
    advance the watermark nor block it (a naive start cannot even be compared
    to an aware one).

    Entries are grouped by their exact ``start`` value, ascending. A group
    only counts once *every* entry sharing that start is final -- a tie at
    the earliest start where one entry is final and another is not blocks
    the watermark entirely (it never even reaches that start), not just the
    entry that failed; grouping first, rather than walking entry by entry,
    is what keeps such a tie from letting the group's final entry advance
    the watermark before its non-final sibling is (correctly) checked. The
    first group with any non-final entry stops the scan; every group before
    it has already been folded into ``newest``.
    """
    dated = sorted(
        (
            activity
            for activity in entries
            if activity.start is not None and activity.start.tzinfo is not None
        ),
        key=lambda activity: cast(datetime, activity.start),
    )
    newest: datetime | None = None
    index = 0
    total = len(dated)
    while index < total:
        group_start = dated[index].start
        group_is_final = True
        cursor = index
        while cursor < total and dated[cursor].start == group_start:
            if not ledger.is_final(dated[cursor].remote_id, dated[cursor].revision):
                group_is_final = False
            cursor += 1
        if not group_is_final:
            break
        newest = group_start
        index = cursor
    return newest


@dataclass
class _LedgerHolder:
    ledger: Ledger


def _runnable(instance: ConnectorInstance) -> tuple[Capability, ...]:
    return tuple(
        capability
        for capability in Capability
        if capability in instance.connector.capabilities
        and (
            capability is Capability.PULL_ACTIVITIES
            or (capability is Capability.PULL_WELLNESS and instance.wellness)
        )
    )


def _nothing_to_pull_detail(instance: ConnectorInstance) -> str:
    if Capability.PULL_WELLNESS in instance.connector.capabilities:
        return (
            "pulls only wellness, which is not enabled for this instance; "
            f"set wellness = true in [connectors.{instance.name}]"
        )
    return "does not pull activities or wellness"


def _wellness_oldest(
    since: datetime | None, through: date | None, lookback_days: int
) -> date | None:
    if since is not None:
        return since.astimezone(UTC).date()
    if through is not None:
        return through - timedelta(days=lookback_days)
    return None


def _day_problem(day: WellnessDay) -> str | None:
    if type(getattr(day, "day", None)) is not date:
        return "wellness day must be a date"
    revision = getattr(day, "revision", False)
    if revision is not None:
        if not isinstance(revision, str):
            return "wellness revision must be text or absent"
        if not revision or len(revision) > _MAX_REVISION_LEN:
            return "wellness revision must contain 1 to 512 characters"
        if any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in revision):
            return "wellness revision must not contain control characters"
    return None


def _pull_wellness(
    holder: _LedgerHolder,
    *,
    instance: ConnectorInstance,
    session: ConnectorSession,
    options: PullOptions,
    data_root: Path,
    inbox: Path,
    redactor: Redactor,
) -> WellnessPullReport:
    wellness = holder.ledger.wellness or WellnessLedger()
    oldest = _wellness_oldest(options.since, wellness.through, instance.lookback_days)
    puller = cast(WellnessPuller, instance.connector)
    try:
        listing = puller.list_wellness(session, oldest)
    except Exception as exc:
        return WellnessPullReport(
            0,
            0,
            (),
            (),
            (),
            (),
            (),
            _instance_error(exc, name=instance.name, redactor=redactor),
        )
    if (
        type(getattr(listing, "oldest", None)) is not date
        or type(getattr(listing, "newest", None)) is not date
        or listing.oldest > listing.newest
    ):
        return WellnessPullReport(
            0,
            0,
            (),
            (),
            (),
            (),
            (),
            PullNote(
                instance.name,
                redactor.redact("the connector's wellness listing is malformed"),
            ),
        )
    failed: list[PullNote] = []
    seen: set[date] = set()
    changed: list[WellnessDay] = []
    unchanged = 0
    for day in listing.days:
        reason = _day_problem(day)
        day_date = getattr(day, "day", None)
        subject = day_date.isoformat() if type(day_date) is date else "listing"
        if type(day_date) is date:
            if day_date in seen:
                failed.append(
                    PullNote(
                        subject, redactor.redact("wellness date listed more than once")
                    )
                )
                continue
            seen.add(day_date)
        if reason is not None:
            failed.append(PullNote(subject, redactor.redact(reason)))
            continue
        entry = wellness.entry(day.day)
        if entry is None or entry.revision != day.revision:
            changed.append(day)
        else:
            unchanged += 1
    would_deliver = (
        tuple(sorted(day.day.isoformat() for day in changed)) if options.dry_run else ()
    )
    delivered: list[WellnessDelivered] = []
    held: list[str] = []
    notices: list[PullNote] = []
    error: PullNote | None = None
    if not options.dry_run:
        years = sorted({day.day.year for day in changed})
        for year in years:
            group = tuple(
                sorted(
                    (day for day in changed if day.day.year == year),
                    key=lambda day: day.day,
                )
            )
            first, last = group[0].day, group[-1].day
            span = f"{first.isoformat()}..{last.isoformat()}"
            try:
                package = puller.package_wellness(session, group)
            except (AuthFailure, ConnectorError) as exc:
                error = _instance_error(exc, name=instance.name, redactor=redactor)
                break
            except Exception as exc:
                failed.append(
                    PullNote(span, redactor.redact(f"{type(exc).__name__}: {exc}"))
                )
                continue
            problem = wellness_package_problem(
                package.data, package.suffix, package.format, package.origins
            )
            if problem is not None:
                failed.append(PullNote(span, redactor.redact(problem)))
                continue
            sha = hashlib.sha256(package.data).hexdigest()
            pairs = tuple((day.day, day.revision) for day in group)
            if wellness_archived(data_root, package.format, sha, package.suffix) or any(
                p.sha256 == sha for p in wellness.pending
            ):
                wellness = wellness.with_days(pairs, sha)
                held.append(span)
            else:
                try:
                    result = deliver(
                        inbox,
                        instance.name,
                        wellness_delivery_name(first, last, package.suffix),
                        package.data,
                        sha,
                        owned={p.path: p.sha256 for p in wellness.pending},
                        suffix=package.suffix,
                    )
                except OSError as exc:
                    failed.append(
                        PullNote(span, redactor.redact(f"{type(exc).__name__}: {exc}"))
                    )
                    continue
                wellness = wellness.with_days(pairs, sha)
                wellness = wellness.with_pending(
                    WellnessPending(result.rel, sha, package.format, package.suffix)
                )
                delivered.append(WellnessDelivered(span, len(group), result.rel))
                for platform in sorted(set(wellness.origins) - package.origins):
                    notices.append(
                        PullNote(
                            platform,
                            redactor.redact(
                                ATTRIBUTION_DROPPED.format(platform=platform)
                            ),
                        )
                    )
                wellness = wellness.with_origins(package.origins)
            holder.ledger = holder.ledger.with_wellness(wellness)
    if not options.dry_run and error is None and not failed:
        wellness = wellness.with_coverage(listing.oldest, listing.newest)
        holder.ledger = holder.ledger.with_wellness(wellness)
    return WellnessPullReport(
        len(listing.days),
        unchanged,
        tuple(sorted(delivered, key=lambda item: item.span)),
        would_deliver,
        tuple(sorted(held)),
        tuple(sorted(failed, key=lambda note: note.subject)),
        tuple(sorted(notices, key=lambda note: note.subject)),
        error,
    )


def _pull_one(
    instance: ConnectorInstance,
    *,
    data_root: Path,
    inbox: Path,
    store: CredentialStore | None,
    transport: Transport,
    options: PullOptions,
    environ: Mapping[str, str],
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    redactor: Redactor,
) -> InstancePullReport:
    connector = instance.connector
    name = instance.name
    connector_id = connector.connector_id
    ledger_existed = layout.connector_ledger_path(data_root, name).exists()

    try:
        ledger = load_ledger(data_root, name, connector_id=connector_id)
    except LedgerError as exc:
        return _empty_report(
            name,
            connector_id,
            error=PullNote(subject=name, detail=redactor.redact(str(exc))),
        )

    removed: tuple[str, ...] = ()
    delivered: list[Delivered] = []
    would_fetch: list[str] = []
    held: list[str] = []
    skipped: list[PullNote] = []
    deferred: list[PullNote] = []
    failed: list[PullNote] = []
    listed = 0
    error: PullNote | None = None
    wellness_report: WellnessPullReport | None = None
    holder: _LedgerHolder | None = None
    activity_auth_failed = False

    try:
        if not options.dry_run:
            sweep_result = sweep(inbox, data_root, ledger)
            ledger = sweep_result.ledger
            removed = sweep_result.removed
            for failed_path, sweep_reason in sweep_result.failures:
                deferred.append(
                    PullNote(subject=failed_path, detail=redactor.redact(sweep_reason))
                )

        try:
            credentials = resolve_credentials(name, connector, store, environ, redactor)
        except (ConnectorError, CredentialStoreError) as exc:
            error = _instance_error(exc, name=name, redactor=redactor)
        else:
            if (
                connector.auth_style is AuthStyle.LOGIN
                and credentials.expires_at is not None
                and credentials.expires_at <= now() + _TOKEN_RENEWAL_MARGIN
            ):
                auth_http_client = HttpClient(
                    transport, mode=CallMode.AUTH, redactor=redactor, sleep=sleep
                )
                auth_session = ConnectorSession(
                    instance=name,
                    settings=instance.settings,
                    http=auth_http_client,
                    credentials=credentials,
                    data_root=data_root,
                    now=now,
                    sleep=sleep,
                    redactor=redactor,
                )
                try:
                    tokens = cast(TokenIssuer, connector).refresh(auth_session)
                    for token_value in tokens.values.values():
                        redactor.add(token_value)
                    credentials.replace(tokens)
                except Exception as exc:
                    error = _instance_error(exc, name=name, redactor=redactor)

            if error is None:
                runnable = _runnable(instance)
                if not runnable:
                    error = PullNote(
                        subject=name,
                        detail=redactor.redact(_nothing_to_pull_detail(instance)),
                    )
                else:
                    http_client = HttpClient(
                        transport, mode=CallMode.DATA, redactor=redactor, sleep=sleep
                    )
                    session = ConnectorSession(
                        instance=name,
                        settings=instance.settings,
                        http=http_client,
                        credentials=credentials,
                        data_root=data_root,
                        now=now,
                        sleep=sleep,
                        redactor=redactor,
                    )
                    if Capability.PULL_ACTIVITIES in runnable:
                        since = _window_start(
                            options.since, ledger.watermark, instance.lookback_days
                        )
                        puller = cast(ActivityPuller, connector)

                        try:
                            listing = puller.list_activities(session, since)
                        except Exception as exc:
                            activity_auth_failed = isinstance(exc, AuthFailure)
                            error = _instance_error(exc, name=name, redactor=redactor)
                        else:
                            listed = len(listing.activities)

                            for note in listing.deferred:
                                deferred.append(
                                    PullNote(
                                        subject=note.subject,
                                        detail=redactor.redact(note.reason),
                                    )
                                )

                            valid_entries: list[RemoteActivity] = []
                            seen_ids: set[str] = set()
                            for activity in listing.activities:
                                reason = _validate_entry(activity)
                                if reason is not None:
                                    failed.append(
                                        PullNote(
                                            subject=activity.remote_id,
                                            detail=redactor.redact(reason),
                                        )
                                    )
                                    continue
                                if activity.remote_id in seen_ids:
                                    failed.append(
                                        PullNote(
                                            subject=activity.remote_id,
                                            detail=redactor.redact(
                                                f"remote id {activity.remote_id!r} "
                                                "listed more than once"
                                            ),
                                        )
                                    )
                                    continue
                                seen_ids.add(activity.remote_id)
                                valid_entries.append(activity)

                            ordered = sorted(
                                valid_entries,
                                key=lambda activity: (
                                    activity.start is None,
                                    activity.start,
                                    activity.remote_id,
                                ),
                            )

                            held_hashes: set[str] = {
                                entry.sha256
                                for entry in ledger.pending_entries()
                                if entry.sha256 is not None
                            }
                            # `deliver`'s owned-only reuse rule (Req 15.4, R2
                            # controller ruling): only an inbox-relative path
                            # this instance itself already recorded -- a still-
                            # pending delivery, or one made earlier in this same
                            # run -- mapped to the exact sha256 it was recorded
                            # with, may ever be reused. Never a file that merely
                            # happens to have identical bytes, such as one the
                            # athlete's own tool dropped in by hand. Built after
                            # the sweep above, so an entry whose delivery was
                            # just swept away from the inbox is not offered as
                            # owned.
                            owned_paths: dict[str, str] = {
                                entry.pending: entry.sha256
                                for entry in ledger.pending_entries()
                                if entry.pending is not None
                                and entry.sha256 is not None
                            }

                            for activity in ordered:
                                existing_entry = ledger.get(activity.remote_id)

                                if ledger.is_final(
                                    activity.remote_id, activity.revision
                                ):
                                    held.append(activity.remote_id)
                                    continue

                                if not activity.original_available:
                                    detail = redactor.redact(
                                        activity.unavailable_reason or ""
                                    )
                                    ledger = ledger.with_entry(
                                        LedgerEntry(
                                            remote_id=activity.remote_id,
                                            outcome=Outcome.SKIPPED,
                                            revision=activity.revision,
                                            detail=detail,
                                        )
                                    )
                                    skipped.append(
                                        PullNote(
                                            subject=activity.remote_id, detail=detail
                                        )
                                    )
                                    continue

                                if options.dry_run:
                                    would_fetch.append(activity.remote_id)
                                    continue

                                try:
                                    outcome = puller.fetch_activity(session, activity)
                                except (AuthFailure, ConnectorError) as exc:
                                    activity_auth_failed = isinstance(exc, AuthFailure)
                                    error = _instance_error(
                                        exc, name=name, redactor=redactor
                                    )
                                    break
                                except Exception as exc:
                                    failed.append(
                                        PullNote(
                                            subject=activity.remote_id,
                                            detail=redactor.redact(
                                                f"{type(exc).__name__}: {exc}"
                                            ),
                                        )
                                    )
                                    continue

                                if isinstance(outcome, Deferred):
                                    deferred.append(
                                        PullNote(
                                            subject=activity.remote_id,
                                            detail=redactor.redact(outcome.reason),
                                        )
                                    )
                                    continue

                                if isinstance(outcome, Declined):
                                    detail = redactor.redact(outcome.reason)
                                    ledger = ledger.with_entry(
                                        LedgerEntry(
                                            remote_id=activity.remote_id,
                                            outcome=Outcome.SKIPPED,
                                            revision=activity.revision,
                                            detail=detail,
                                        )
                                    )
                                    skipped.append(
                                        PullNote(
                                            subject=activity.remote_id, detail=detail
                                        )
                                    )
                                    continue

                                assert isinstance(outcome, Fetched)
                                data = outcome.data
                                sha = hashlib.sha256(data).hexdigest()

                                if not is_fit(data):
                                    detail = "not a FIT file"
                                    ledger = ledger.with_entry(
                                        LedgerEntry(
                                            remote_id=activity.remote_id,
                                            outcome=Outcome.SKIPPED,
                                            revision=activity.revision,
                                            sha256=sha,
                                            detail=detail,
                                        )
                                    )
                                    skipped.append(
                                        PullNote(
                                            subject=activity.remote_id, detail=detail
                                        )
                                    )
                                    continue

                                if (
                                    existing_entry is not None
                                    and existing_entry.pending is not None
                                    and existing_entry.sha256 == sha
                                ):
                                    # A new revision of an id already pending, with the
                                    # same bytes (a metadata-only change upstream): keep
                                    # the existing inbox copy and its pending location
                                    # exactly as it is, only the revision moves forward
                                    # (R2 controller ruling). Neither `deliver` nor the
                                    # archive/held-hash dedup check below run for this
                                    # id. Nothing was written this run, so it is
                                    # reported in `held` (Req 6.8, "already held"), not
                                    # `delivered`, even though the ledger entry's own
                                    # outcome stays `DELIVERED`.
                                    ledger = ledger.with_entry(
                                        LedgerEntry(
                                            remote_id=activity.remote_id,
                                            outcome=Outcome.DELIVERED,
                                            revision=activity.revision,
                                            sha256=sha,
                                            pending=existing_entry.pending,
                                        )
                                    )
                                    held.append(activity.remote_id)
                                    continue

                                archived = layout.archive_path(data_root, sha).is_file()
                                if archived or sha in held_hashes:
                                    ledger = ledger.with_entry(
                                        LedgerEntry(
                                            remote_id=activity.remote_id,
                                            outcome=Outcome.ALREADY_HELD,
                                            revision=activity.revision,
                                            sha256=sha,
                                        )
                                    )
                                    _release_replaced_pending(
                                        held_hashes,
                                        owned_paths,
                                        existing_entry,
                                        ledger,
                                    )
                                    held.append(activity.remote_id)
                                    continue

                                # A new revision of an id already pending, with
                                # *different* bytes: the old inbox copy is left in
                                # place, released from the ledger's tracking (this
                                # `with_entry` below replaces its record entirely) --
                                # the drain treats it as any other untracked inbox
                                # file it discovers (R2 controller ruling).
                                file_name = delivery_name(activity)
                                try:
                                    result = deliver(
                                        inbox,
                                        name,
                                        file_name,
                                        data,
                                        sha,
                                        owned=owned_paths,
                                    )
                                except OSError as exc:
                                    failed.append(
                                        PullNote(
                                            subject=activity.remote_id,
                                            detail=redactor.redact(
                                                f"{type(exc).__name__}: {exc}"
                                            ),
                                        )
                                    )
                                    continue
                                ledger = ledger.with_entry(
                                    LedgerEntry(
                                        remote_id=activity.remote_id,
                                        outcome=Outcome.DELIVERED,
                                        revision=activity.revision,
                                        sha256=sha,
                                        pending=result.rel,
                                    )
                                )
                                delivered.append(
                                    Delivered(
                                        remote_id=activity.remote_id, path=result.rel
                                    )
                                )
                                _release_replaced_pending(
                                    held_hashes, owned_paths, existing_entry, ledger
                                )
                                held_hashes.add(sha)
                                owned_paths[result.rel] = sha

                            if not options.dry_run:
                                watermark = _compute_watermark(
                                    listing.activities, ledger
                                )
                                if watermark is not None and (
                                    ledger.watermark is None
                                    or watermark >= ledger.watermark
                                ):
                                    ledger = ledger.with_watermark(watermark)

                    if (
                        Capability.PULL_WELLNESS in runnable
                        and not activity_auth_failed
                    ):
                        holder = _LedgerHolder(ledger)
                        wellness_report = _pull_wellness(
                            holder,
                            instance=instance,
                            session=session,
                            options=options,
                            data_root=data_root,
                            inbox=inbox,
                            redactor=redactor,
                        )
                        ledger = holder.ledger
    finally:
        if holder is not None:
            ledger = holder.ledger
        if not options.dry_run:
            has_content = (
                bool(ledger.entries)
                or ledger.watermark is not None
                or ledger.wellness is not None
            )
            if ledger_existed or has_content:
                save_ledger(data_root, name, ledger)

    return InstancePullReport(
        name=name,
        connector_id=connector_id,
        listed=listed,
        delivered=tuple(sorted(delivered, key=lambda item: item.path)),
        would_fetch=tuple(sorted(would_fetch)),
        held=tuple(sorted(held)),
        skipped=tuple(sorted(skipped, key=lambda note: note.subject)),
        deferred=tuple(sorted(deferred, key=lambda note: note.subject)),
        failed=tuple(sorted(failed, key=lambda note: note.subject)),
        removed=tuple(sorted(removed)),
        error=error,
        wellness=wellness_report,
    )


def run_pull(
    data_root: Path,
    instances: Sequence[ConnectorInstance],
    *,
    inbox: Path,
    store: CredentialStore | None,
    transport: Transport,
    options: PullOptions,
    environ: Mapping[str, str],
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    redactor: Redactor,
) -> PullReport:
    """Pull every instance in ``instances``, in the given order (design.md
    "PullEngine").

    Each instance is pulled independently by :func:`_pull_one`, which
    isolates the per-instance failures design.md names -- not connected,
    credentials rejected, an unreadable or malformed stored credentials
    file (:class:`fitdocs.connectors.credentials.CredentialStoreError`), a
    listing exception (including an unreachable source), an authentication
    failure or connector error from listing or a fetch, and *any* exception
    from token renewal (including a ``TransportError`` from the
    authentication-mode session, or a ``CredentialStoreError``/``OSError``
    while persisting the renewed token) -- into that instance's own
    ``error`` report rather than letting them propagate (Req 6.10): one
    instance's authentication failure does not stop the next. An exception
    :func:`_pull_one` does not itself catch (a genuine bug, or
    ``KeyboardInterrupt``) still propagates out of this function after that
    instance's own ``finally`` has saved its ledger.
    """
    reports = tuple(
        _pull_one(
            instance,
            data_root=data_root,
            inbox=inbox,
            store=store,
            transport=transport,
            options=options,
            environ=environ,
            now=now,
            sleep=sleep,
            redactor=redactor,
        )
        for instance in instances
    )
    return PullReport(inbox=str(inbox), dry_run=options.dry_run, instances=reports)
