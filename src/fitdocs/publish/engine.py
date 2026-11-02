"""One publish run over the selected pages and targets: the decision and the
dry run, posting, recording and the published-region refresh (publish-core
Req 2.3-2.7, 3.8, 7.5-7.8, 8.1-8.8, 10.3-10.5, 11.7, 12.2, 12.5-12.8, 13.5).

For each selected page, in order, and each target the page opts in to, in
target-name order, the run either refuses the pair with a code and a
fitdocs-written detail or decides ``WOULD_POST``, ``WOULD_UPDATE`` or
``UNCHANGED`` from the ledger's landed digest, keeping the composed post of a
pair that would be posted or updated for the report.

A run without ``plan.posting`` reads the data root and nothing else: it opens
no target, sends no request, saves no ledger and writes no page.

A posting run keeps a working copy of the ledgers (the plan's are never
modified). For each pair that would be posted or updated it opens the target
on first use, mints a publication id when the page has no record, saves the
ledger, sends one request, records the answer and saves the ledger again
before the next request. A target that fails to open gives that code to every
one of its pairs; a stopping answer reports the target's remaining pairs as
not attempted. After each page's pairs its ``published`` region is rebuilt
from every ledger and rewritten only when the bytes differ; a page whose
ledger records are ambiguous is left unwritten and reported. The ``post``
region and every other byte of the page are never touched, and an older or
newer page is never written.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from functools import cache
from pathlib import Path

from fitdocs.contract import POST_REGION, InvalidPublishKey, document_publish_targets
from fitdocs.docio import write_bytes_if_changed
from fitdocs.docmerge import RegionError
from fitdocs.publish.compose import (
    PostOverride,
    Refusal,
    compose_post,
    override_templates,
    post_digest,
    read_post_region,
)
from fitdocs.publish.ledger import (
    PublicationRecord,
    PublishLedger,
    save_ledger,
    workout_page_key,
)
from fitdocs.publish.links import (
    PublishedRegionMissing,
    published_content,
    replace_published,
)
from fitdocs.publish.outcomes import (
    FAILURE_CODES,
    LANDED_CODES,
    STOPPING_CODES,
    PublishCode,
)
from fitdocs.publish.pages import (
    PageStatus,
    PageView,
    SelectedPage,
    completed_activity,
    read_page,
    sha_index,
    source_shas,
)
from fitdocs.publish.request import (
    CompletedActivity,
    Post,
    PublishRequest,
    valid_label,
)
from fitdocs.publish.settings import PublishSettings
from fitdocs.publish.targets import TargetChannel
from fitdocs.publish.values import page_values

__all__ = [
    "OpenTarget",
    "PublishPlan",
    "PublishReport",
    "ResultRow",
    "decide",
    "run_publish",
]

_PAGE_STATUS_CODES: dict[PageStatus, PublishCode] = {
    PageStatus.OLDER: PublishCode.PAGE_OUT_OF_DATE,
    PageStatus.NEWER: PublishCode.PAGE_NEWER,
    PageStatus.DAMAGED: PublishCode.PAGE_DAMAGED,
}
_POSTING_DECISIONS = frozenset({PublishCode.WOULD_POST, PublishCode.WOULD_UPDATE})


@dataclass(frozen=True)
class PublishPlan:
    data_root: Path
    pages: tuple[SelectedPage, ...]
    considered: tuple[str, ...]  # selected target names, sorted
    configured: frozenset[str]  # every configured publish target
    settings: PublishSettings
    ledgers: Mapping[str, PublishLedger]  # every ledger; the run works on a copy
    posting: bool  # --yes


@dataclass(frozen=True)
class ResultRow:
    page: str
    target: str | None  # None for a page-level row
    code: PublishCode
    decision: PublishCode | None  # set only for a pair that reached a decision
    post: Post | None  # the post of a would-post or would-update pair
    link: str | None
    link_refused: bool
    detail: str | None  # fitdocs-written, never a service's text


@dataclass(frozen=True)
class PublishReport:
    posting: bool
    rows: tuple[ResultRow, ...]
    not_opted_in: int
    configured: int

    @property
    def failed(self) -> bool:
        return any(row.code in FAILURE_CODES for row in self.rows)


OpenTarget = Callable[[str], TargetChannel | PublishCode]


def decide(record: PublicationRecord | None, digest: str) -> PublishCode:
    """Would-post without a landed digest, unchanged when it equals ``digest``,
    otherwise would-update (Req 7.6)."""
    if record is None or record.digest is None:
        return PublishCode.WOULD_POST
    if record.digest == digest:
        return PublishCode.UNCHANGED
    return PublishCode.WOULD_UPDATE


def _row(
    page: SelectedPage,
    target: str | None,
    code: PublishCode,
    *,
    detail: str | None = None,
    decision: PublishCode | None = None,
    post: Post | None = None,
) -> ResultRow:
    return ResultRow(
        page=page.rel,
        target=target,
        code=code,
        decision=decision,
        post=post,
        link=None,
        link_refused=False,
        detail=detail,
    )


@dataclass(frozen=True)
class _Pending:
    """A pair that would be posted or updated, with what sending it needs."""

    row: ResultRow  # the decision row; a dry run reports it as is
    subject: CompletedActivity
    record: PublicationRecord | None
    post: Post
    digest: str


class _Run:
    """The state of one run: the working ledgers and what is open or stopped."""

    def __init__(
        self,
        plan: PublishPlan,
        open_target: OpenTarget,
        now: Callable[[], datetime],
        mint_id: Callable[[], str],
    ) -> None:
        self.plan = plan
        self.open_target = open_target
        self.now = now
        self.mint_id = mint_id
        self.ledgers: dict[str, PublishLedger] = dict(plan.ledgers)
        self.channels: dict[str, TargetChannel] = {}
        self.stopped: dict[str, PublishCode] = {}  # after a stopping answer
        # The code each target that failed to open answers all its pairs with.
        self.unopened: dict[str, PublishCode] = {}


def run_publish(
    plan: PublishPlan,
    *,
    open_target: OpenTarget,
    now: Callable[[], datetime],
    mint_id: Callable[[], str],
) -> PublishReport:
    """Decide every selected page and target; a posting run also sends,
    records and refreshes the published regions."""
    run = _Run(plan, open_target, now, mint_id)
    # Resolved only if a pair has a ledger record; reads pages, writes nothing.
    index = cache(lambda: sha_index(plan.data_root))
    rows: list[ResultRow] = []
    not_opted_in = 0
    for page in plan.pages:
        page_rows, counted = _decide_page(run, page, index)
        rows.extend(page_rows)
        not_opted_in += counted
        if plan.posting:
            rows.extend(_refresh_published(run, page, index))
    return PublishReport(
        posting=plan.posting,
        rows=tuple(rows),
        not_opted_in=not_opted_in,
        configured=len(plan.configured),
    )


def _decide_page(
    run: _Run,
    page: SelectedPage,
    index: Callable[[], Mapping[str, tuple[str, ...]]],
) -> tuple[list[ResultRow], bool]:
    """The page's rows, and whether it counts as opted in to no considered
    target (a named page is listed with its row instead, so it does not)."""
    plan = run.plan
    view = read_page(page)
    if view is None:
        if page.named:
            return [_row(page, None, PublishCode.PAGE_UNREADABLE)], False
        return [], False
    names = document_publish_targets(view.frontmatter)
    if isinstance(names, InvalidPublishKey):
        invalid = _row(page, None, PublishCode.OPT_IN_INVALID, detail=names.detail)
        return [invalid], False
    rows: list[ResultRow] = []
    # --to narrows `considered` below the configured set; only then is an
    # unknown name outside the selection rather than a defect of the page.
    narrowed = frozenset(plan.considered) != plan.configured
    if not narrowed:
        rows.extend(
            _row(page, name, PublishCode.UNKNOWN_TARGET)
            for name in sorted(names)
            if name not in plan.configured
        )
    chosen = sorted(name for name in names if name in plan.considered)
    if not chosen:
        if page.named:
            rows.append(_row(page, None, PublishCode.NOT_OPTED_IN))
        return rows, not page.named
    values = page_values(view.frontmatter)
    for target in chosen:
        outcome = _decide_pair(run, page, view, target, values, index)
        if isinstance(outcome, ResultRow):
            rows.append(outcome)
        elif plan.posting:
            rows.append(_post_pair(run, target, outcome))
        else:
            rows.append(outcome.row)
    return rows, False


def _pages_of_record(
    index: Callable[[], Mapping[str, tuple[str, ...]]], record: PublicationRecord
) -> tuple[str, ...]:
    """Every page recording the digest the record's page key names."""
    return index().get(record.page.partition(":")[2], ())


def _decide_pair(
    run: _Run,
    page: SelectedPage,
    view: PageView,
    target: str,
    values: Mapping[str, str | None],
    index: Callable[[], Mapping[str, tuple[str, ...]]],
) -> ResultRow | _Pending:
    plan = run.plan
    status_code = _PAGE_STATUS_CODES.get(view.status)
    if status_code is not None:
        return _row(page, target, status_code, detail=view.detail)
    subject = completed_activity(view.frontmatter, plan.data_root)
    # A page that records no archived file has no digest to key a record by.
    if subject is None or not subject.source_shas:
        return _row(page, target, PublishCode.ACTIVITY_FACTS_MISSING)
    ledger = run.ledgers.get(target)
    matches = () if ledger is None else ledger.matching(subject.source_shas)
    if len(matches) > 1:
        return _row(
            page,
            target,
            PublishCode.LEDGER_CONFLICT,
            detail="more than one ledger record matches this page",
        )
    record = matches[0] if matches else None
    if record is not None:
        shared = _pages_of_record(index, record)
        if len(shared) > 1:
            return _row(
                page,
                target,
                PublishCode.LEDGER_CONFLICT,
                detail="the ledger record also matches "
                + ", ".join(rel for rel in shared if rel != page.rel),
            )
    else:
        # No record yet: the one a post would mint is keyed by the page's last
        # source digest (see `_post_pair`), so a page sharing it with another
        # is refused now, in a dry run exactly as in a posting run.
        others = [
            rel for rel in index().get(subject.source_shas[-1], ()) if rel != page.rel
        ]
        if others:
            return _row(
                page,
                target,
                PublishCode.LEDGER_CONFLICT,
                detail="the ledger key for this page is also recorded by "
                + ", ".join(others),
            )
    post = _compose(plan, view, target, values)
    if isinstance(post, Refusal):
        return _row(page, target, post.code, detail=post.detail)
    digest = post_digest(post)
    decision = decide(record, digest)
    if decision not in _POSTING_DECISIONS:
        return _row(page, target, decision, decision=decision)
    row = _row(page, target, decision, decision=decision, post=post)
    return _Pending(row=row, subject=subject, record=record, post=post, digest=digest)


def _post_pair(run: _Run, target: str, pending: _Pending) -> ResultRow:
    """Send one pair's request and record the answer (Req 8.1, 8.4-8.8, 10.3-10.5)."""
    row = pending.row
    # A target that failed to open gives every one of its pairs that code
    # (Req 8.6); a pair after a stopping answer was not attempted.
    if target in run.unopened:
        return replace(row, code=run.unopened[target])
    if target in run.stopped:
        return replace(row, code=PublishCode.NOT_ATTEMPTED)
    channel = run.channels.get(target)
    if channel is None:
        opened = run.open_target(target)
        if isinstance(opened, PublishCode):
            run.unopened[target] = opened
            return replace(row, code=opened)
        channel = run.channels[target] = opened
    record = pending.record
    if record is None:
        record = PublicationRecord(
            page=workout_page_key(pending.subject.source_shas[-1]),
            publication_id=run.mint_id(),
        )
    # The id is on disk before the request, so an interruption reuses it.
    _save(run, target, run.ledgers[target].with_record(record))
    delivery = channel.send(
        PublishRequest(
            publication_id=record.publication_id,
            post=pending.post,
            subject=pending.subject,
            recorded_link=record.link,
        )
    )
    # The outcome is on disk before anything else is done with the answer (Req
    # 8.8); its time is when the answer was received (Req 11.1).
    keep_link = delivery.link is not None and valid_label(channel.label)
    outcome = replace(
        record,
        code=delivery.code.value,
        at=run.now(),
        digest=pending.digest if delivery.code in LANDED_CODES else record.digest,
    )
    if keep_link:
        outcome = replace(outcome, link=delivery.link, label=channel.label)
    _save(run, target, run.ledgers[target].with_record(outcome))
    if delivery.code in STOPPING_CODES:
        run.stopped[target] = delivery.code
    return replace(
        row,
        code=delivery.code,
        link=delivery.link if keep_link else None,
        link_refused=delivery.link_refused
        or (delivery.link is not None and not keep_link),
    )


def _save(run: _Run, target: str, ledger: PublishLedger) -> None:
    run.ledgers[target] = ledger
    save_ledger(run.plan.data_root, ledger)


def _refresh_published(
    run: _Run,
    page: SelectedPage,
    index: Callable[[], Mapping[str, tuple[str, ...]]],
) -> list[ResultRow]:
    """Rewrite a current page's published region from every ledger (Req 12.2).

    Records are matched by the page's source digests alone, whatever its
    opt-in, so a link stays after the page stops naming a target and a page
    with no archived-file digest matches nothing. A page whose records are
    ambiguous is left alone and reported; a page that is not current is never
    written (Req 12.8).
    """
    view = read_page(page)
    if view is None or view.status is not PageStatus.CURRENT:
        return []
    shas = source_shas(view.frontmatter)
    links: list[tuple[str, str, str]] = []
    for target, ledger in run.ledgers.items():
        matches = ledger.matching(shas)
        if len(matches) > 1:
            return [
                _ambiguous(
                    page, f"more than one {target} ledger record matches this page"
                )
            ]
        for record in matches:
            if len(_pages_of_record(index, record)) > 1:
                return [
                    _ambiguous(
                        page,
                        f"the {target} ledger record for this page also matches "
                        "another page",
                    )
                ]
            if record.link is not None and record.label is not None:
                links.append((target, record.label, record.link))
    try:
        spliced = replace_published(view.text, published_content(links))
        write_bytes_if_changed(page.path, spliced.encode("utf-8"))
    except (OSError, RegionError, PublishedRegionMissing) as exc:
        detail = str(exc) if not isinstance(exc, OSError) else type(exc).__name__
        return [_row(page, None, PublishCode.PUBLISHED_NOT_WRITTEN, detail=detail)]
    return []


def _ambiguous(page: SelectedPage, why: str) -> ResultRow:
    detail = f"{why}, so its published region was left as it is"
    return _row(page, None, PublishCode.PUBLISHED_NOT_WRITTEN, detail=detail)


def _compose(
    plan: PublishPlan, view: PageView, target: str, values: Mapping[str, str | None]
) -> Post | Refusal:
    """The page's post for one target: its own region, else the target's templates."""
    templates = plan.settings.for_target(target)
    assert view.regions is not None  # a CURRENT page carries its regions
    override = read_post_region(view.regions[POST_REGION])
    if isinstance(override, Refusal):
        return override
    if isinstance(override, PostOverride):
        parsed = override_templates(override)
        if isinstance(parsed, Refusal):
            return parsed
        templates = parsed
    return compose_post(templates, values)
