"""Orchestrate one pull over the selected instances (design.md "PullEngine",
Req 1.9, 6.4-6.9, 6.12, 6.13, 7.2, 7.4, 7.7, 8.5, 11.5, 13.4).

:func:`run_pull` is the whole engine for this task: per instance, in
design.md's stated order, it loads the ledger, sweeps archived deliveries
(unless dry run), refuses a connector that does not declare
``PULL_ACTIVITIES``, computes the listing window start, lists and validates
the connector's activities, classifies each one, advances the watermark --
never backward, see :func:`_compute_watermark` -- over the contiguous run of
start-grouped entries that end up final, and saves the ledger in a
``finally`` so a save happens on every exit -- success, an instance error, or
an interruption (``KeyboardInterrupt`` is re-raised after the save completes,
never swallowed).

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

Task 4.4 adds credential resolution's failure handling (a not-connected
instance, a login-style token renewal, per-item and per-instance failure
isolation) and redaction of connector-supplied reasons beyond the plain
``redactor.redact`` pass this task already applies to every note and ledger
detail. This task calls :func:`fitdocs.connectors.credentials.
resolve_credentials` unconditionally as the hook task 4.4 extends -- for the
``AuthStyle.NONE`` connectors this task's own pins use (the folder connector,
the scripted puller), it always answers with a credential access that has no
values, so nothing here depends on the failure handling task 4.4 adds. This
task also does not catch ``AuthFailure``/``ConnectorError`` from listing or
fetching, nor isolate one item's ordinary exception from the rest of the
instance (Req 6.10, 6.11) -- both are task 4.4. Any exception a connector
raises here, including ``KeyboardInterrupt``, propagates through this
module's own ``finally``-save and out of :func:`run_pull` unmodified.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, cast

from fitdocs import layout
from fitdocs.connectors.credentials import CredentialStore, resolve_credentials
from fitdocs.connectors.delivery import deliver, delivery_name, is_fit, sweep
from fitdocs.connectors.http import CallMode, HttpClient, Transport
from fitdocs.connectors.ledger import (
    Ledger,
    LedgerEntry,
    LedgerError,
    Outcome,
    load_ledger,
    save_ledger,
)
from fitdocs.connectors.protocol import (
    ActivityPuller,
    Capability,
    ConnectorSession,
    Declined,
    Deferred,
    Fetched,
    RemoteActivity,
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
            instance.error is not None or len(instance.failed) > 0
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

    try:
        if not options.dry_run:
            sweep_result = sweep(inbox, data_root, ledger)
            ledger = sweep_result.ledger
            removed = sweep_result.removed
            for failed_path, sweep_reason in sweep_result.failures:
                deferred.append(
                    PullNote(subject=failed_path, detail=redactor.redact(sweep_reason))
                )

        if Capability.PULL_ACTIVITIES not in connector.capabilities:
            error = PullNote(
                subject=name,
                detail=redactor.redact("does not pull activities"),
            )
        else:
            credentials = resolve_credentials(name, connector, store, environ, redactor)
            since = _window_start(
                options.since, ledger.watermark, instance.lookback_days
            )
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
            puller = cast(ActivityPuller, connector)

            listing = puller.list_activities(session, since)
            listed = len(listing.activities)

            for note in listing.deferred:
                deferred.append(
                    PullNote(subject=note.subject, detail=redactor.redact(note.reason))
                )

            valid_entries: list[RemoteActivity] = []
            seen_ids: set[str] = set()
            for activity in listing.activities:
                reason = _validate_entry(activity)
                if reason is not None:
                    failed.append(
                        PullNote(
                            subject=activity.remote_id, detail=redactor.redact(reason)
                        )
                    )
                    continue
                if activity.remote_id in seen_ids:
                    failed.append(
                        PullNote(
                            subject=activity.remote_id,
                            detail=redactor.redact(
                                f"remote id {activity.remote_id!r} listed more "
                                "than once"
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

            for activity in ordered:
                existing_entry = ledger.get(activity.remote_id)

                if ledger.is_final(activity.remote_id, activity.revision):
                    held.append(activity.remote_id)
                    continue

                if not activity.original_available:
                    detail = redactor.redact(activity.unavailable_reason or "")
                    ledger = ledger.with_entry(
                        LedgerEntry(
                            remote_id=activity.remote_id,
                            outcome=Outcome.SKIPPED,
                            revision=activity.revision,
                            detail=detail,
                        )
                    )
                    skipped.append(PullNote(subject=activity.remote_id, detail=detail))
                    continue

                if options.dry_run:
                    would_fetch.append(activity.remote_id)
                    continue

                outcome = puller.fetch_activity(session, activity)

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
                    skipped.append(PullNote(subject=activity.remote_id, detail=detail))
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
                    skipped.append(PullNote(subject=activity.remote_id, detail=detail))
                    continue

                if (
                    existing_entry is not None
                    and existing_entry.pending is not None
                    and existing_entry.sha256 == sha
                ):
                    # A new revision of an id already pending, with the same
                    # bytes (a metadata-only change upstream): keep the
                    # existing inbox copy and its pending location exactly as
                    # it is, only the revision moves forward (R2 controller
                    # ruling). Neither `deliver` nor the archive/held-hash
                    # dedup check below run for this id. Nothing was written
                    # this run, so it is reported as `held` (Req 6.8, "already
                    # held"), not `delivered`, even though the ledger entry's
                    # own outcome stays `DELIVERED`.
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
                    held.append(activity.remote_id)
                    continue

                # A new revision of an id already pending, with *different*
                # bytes: the old inbox copy is left in place, released from
                # the ledger's tracking (this `with_entry` below replaces its
                # record entirely) -- the drain treats it as any other
                # untracked inbox file it discovers (R2 controller ruling).
                file_name = delivery_name(activity)
                try:
                    result = deliver(inbox, name, file_name, data, sha)
                except OSError as exc:
                    failed.append(
                        PullNote(
                            subject=activity.remote_id,
                            detail=redactor.redact(f"{type(exc).__name__}: {exc}"),
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
                    Delivered(remote_id=activity.remote_id, path=result.rel)
                )
                held_hashes.add(sha)

            if not options.dry_run:
                watermark = _compute_watermark(listing.activities, ledger)
                if watermark is not None and (
                    ledger.watermark is None or watermark >= ledger.watermark
                ):
                    ledger = ledger.with_watermark(watermark)
    finally:
        if not options.dry_run:
            has_content = bool(ledger.entries) or ledger.watermark is not None
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

    Each instance is pulled independently by :func:`_pull_one`; nothing here
    isolates one instance's uncaught exception from the rest -- that is task
    4.4's per-instance failure isolation (Req 6.10). An uncaught exception
    (including ``KeyboardInterrupt``) from one instance's pull propagates out
    of this function after that instance's own ``finally`` has saved its
    ledger.
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
