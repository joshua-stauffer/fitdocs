"""One publish run over the selected pages and targets: the decision and the
dry run (publish-core Req 2.3-2.6, 7.5-7.8, 11.7, 12.6, 13.5).

For each selected page, in order, and each target the page opts in to, in
target-name order, the run either refuses the pair with a code and a
fitdocs-written detail or decides ``WOULD_POST``, ``WOULD_UPDATE`` or
``UNCHANGED`` from the ledger's landed digest, keeping the composed post of a
pair that would be posted or updated for the report.

A run without ``plan.posting`` reads the data root and nothing else: it opens
no target, sends no request, saves no ledger and writes no page. The ledgers
arrive loaded in the plan and are never modified here. Posting, recording and
the published-region refresh are a later task's addition to
:func:`run_publish`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from pathlib import Path

from fitdocs.contract import POST_REGION, InvalidPublishKey, document_publish_targets
from fitdocs.publish.compose import (
    PostOverride,
    Refusal,
    compose_post,
    override_templates,
    post_digest,
    read_post_region,
)
from fitdocs.publish.ledger import PublicationRecord, PublishLedger
from fitdocs.publish.outcomes import FAILURE_CODES, PublishCode
from fitdocs.publish.pages import (
    PageStatus,
    PageView,
    SelectedPage,
    completed_activity,
    read_page,
    sha_index,
)
from fitdocs.publish.request import Post
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
    ledgers: Mapping[str, PublishLedger]  # every ledger; read, never modified here
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


def run_publish(
    plan: PublishPlan,
    *,
    open_target: OpenTarget,
    now: Callable[[], datetime],
    mint_id: Callable[[], str],
) -> PublishReport:
    """Decide every selected page and target; a dry run stops there."""
    if plan.posting:
        raise NotImplementedError("posting is not part of the decision step")
    # Resolved only if a pair has a ledger record; reads pages, writes nothing.
    index = cache(lambda: sha_index(plan.data_root))
    rows: list[ResultRow] = []
    not_opted_in = 0
    for page in plan.pages:
        page_rows, counted = _decide_page(plan, page, index)
        rows.extend(page_rows)
        not_opted_in += counted
    return PublishReport(
        posting=False,
        rows=tuple(rows),
        not_opted_in=not_opted_in,
        configured=len(plan.configured),
    )


def _decide_page(
    plan: PublishPlan,
    page: SelectedPage,
    index: Callable[[], Mapping[str, tuple[str, ...]]],
) -> tuple[list[ResultRow], bool]:
    """The page's rows, and whether it counts as opted in to no considered
    target (a named page is listed with its row instead, so it does not)."""
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
        rows.append(_decide_pair(plan, page, view, target, values, index))
    return rows, False


def _decide_pair(
    plan: PublishPlan,
    page: SelectedPage,
    view: PageView,
    target: str,
    values: Mapping[str, str | None],
    index: Callable[[], Mapping[str, tuple[str, ...]]],
) -> ResultRow:
    status_code = _PAGE_STATUS_CODES.get(view.status)
    if status_code is not None:
        return _row(page, target, status_code, detail=view.detail)
    subject = completed_activity(view.frontmatter, plan.data_root)
    if subject is None:
        return _row(page, target, PublishCode.ACTIVITY_FACTS_MISSING)
    ledger = plan.ledgers.get(target)
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
        shared = index().get(record.page.partition(":")[2], ())
        if len(shared) > 1:
            return _row(
                page,
                target,
                PublishCode.LEDGER_CONFLICT,
                detail="the ledger record also matches "
                + ", ".join(rel for rel in shared if rel != page.rel),
            )
    post = _compose(plan, view, target, values)
    if isinstance(post, Refusal):
        return _row(page, target, post.code, detail=post.detail)
    decision = decide(record, post_digest(post))
    return _row(
        page,
        target,
        decision,
        decision=decision,
        post=post if decision in _POSTING_DECISIONS else None,
    )


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
