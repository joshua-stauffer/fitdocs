"""Fill one workout page's ``post`` region (post-templates task 3.1).

Requirements 3.3, 3.10, 4.1 to 4.6, 5.6 to 5.9, 6.5, 10.4, 10.9 and 10.11. This
module holds the per-page pieces: reading a page once as bytes
(:func:`read_for_fill`) and filling one page (:func:`_fill_page`). The pass
(:func:`run_pass`, task 3.2; Requirements 2.5, 6.2 to 6.4, 6.6 to 6.8, 7.1 to
7.3 and 8.5), ``check`` and ``refill`` callers extend it; they pick the pages
and give each call its resolver, its statement timeout and whether it may
write.

The resolver is declared here as a protocol and ``resolve.SessionResolver``
satisfies it structurally, so this module imports neither ``resolve`` nor
``query``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Final, Protocol

from fitdocs.contract import (
    POST_REGION,
    document_date,
    document_start_time,
    is_workout_document,
    sha_of_ref,
    source_refs,
)
from fitdocs.docio import read_document, write_bytes_if_changed
from fitdocs.docmerge import replace_region
from fitdocs.post_template.model import (
    Binding,
    FillCode,
    FillReport,
    PageResult,
    RegionState,
    TemplateSummary,
    Unavailable,
    VariableOutcome,
)
from fitdocs.post_template.region import classify, render_filled
from fitdocs.post_template.template import PostTemplate, PostTemplateError, Variable
from fitdocs.publish.compose import Refusal, compose_post
from fitdocs.publish.ledger import (
    PublishLedger,
    PublishLedgerError,
    has_landed_post,
    load_ledgers,
)
from fitdocs.publish.outcomes import PublishCode
from fitdocs.publish.pages import (
    PageStatus,
    PageView,
    SelectedPage,
    _status,
    select_pages,
    source_shas,
)
from fitdocs.publish.request import Post
from fitdocs.publish.values import page_values

__all__ = [
    "COMMAND_STATEMENT_TIMEOUT_S",
    "PASS_BUDGET_S",
    "PASS_STATEMENT_TIMEOUT_S",
    "IndexGate",
    "OpenResolver",
    "PageRead",
    "Resolver",
    "read_for_fill",
    "run_check",
    "run_pass",
    "run_refill",
]

PASS_STATEMENT_TIMEOUT_S: Final = 5.0  # 7.1
PASS_BUDGET_S: Final = 30.0  # 7.2
COMMAND_STATEMENT_TIMEOUT_S: Final = 30.0  # 10.12, and check


class Resolver(Protocol):
    def check(self, template: PostTemplate) -> tuple[str, ...]: ...

    def page_is_current(self, page_key: str | None, path: str, data: bytes) -> bool: ...

    def resolve(
        self, variable: Variable, binding: Binding, *, timeout_s: float
    ) -> VariableOutcome: ...

    def close(self) -> None: ...


class OpenResolver(Protocol):
    def __call__(self) -> Resolver | Unavailable: ...


@dataclass(frozen=True)
class PageRead:
    """A workout page, read once: its bytes, its status and what the run needs."""

    selected: SelectedPage
    data: bytes  # the exact file, for the freshness check and the re-read compare
    view: PageView
    state: RegionState | None  # None unless the page is current
    in_window: bool
    landed: bool | None  # a landed publish post is recorded; None: ledgers unread


_COMMENT_MARKERS: Final = ("<!--", "-->", "--!>")

#: A page that cannot be filled because of its own format, by status.
_NOT_CURRENT_DETAIL: Final[dict[PageStatus, str]] = {
    PageStatus.OLDER: "the page was written by an older fitdocs; run fitdocs regen",
    PageStatus.NEWER: "the page was written by a newer fitdocs",
}

#: The refusals `compose_post` can give, as fill codes.
_REFUSAL_CODES: Final[dict[PublishCode, FillCode]] = {
    PublishCode.VALUE_MISSING: FillCode.VALUE_MISSING,
    PublishCode.TITLE_EMPTY: FillCode.TITLE_EMPTY,
}


def _result(
    read: PageRead,
    code: FillCode,
    *,
    detail: str | None = None,
    variables: tuple[VariableOutcome, ...] = (),
    post: Post | None = None,
    changed: bool | None = None,
) -> PageResult:
    return PageResult(
        page=read.selected.rel,
        state=read.state,
        in_window=read.in_window,
        landed=read.landed,
        code=code,
        detail=detail,
        variables=variables,
        post=post,
        changed=changed,
    )


def read_for_fill(
    page: SelectedPage, *, since: date, ledgers: Iterable[PublishLedger]
) -> PageRead | PageResult:
    """Read a page once as bytes, and decide its state, window and landed post.

    A page that cannot be read, or is not a workout page, gives its
    ``PAGE_NOT_CURRENT`` row instead.
    """
    document = read_document(page.path)
    if (
        document is None
        or document.frontmatter is None
        or not is_workout_document(document.frontmatter)
    ):
        return PageResult(
            page=page.rel,
            state=None,
            in_window=False,
            landed=False,
            code=FillCode.PAGE_NOT_CURRENT,
            detail="the page could not be read as a workout page",
            variables=(),
            post=None,
            changed=None,
        )
    frontmatter = document.frontmatter
    view = _status(frontmatter, document.text)
    state = None
    if view.regions is not None:
        state, _ = classify(view.regions[POST_REGION])
    day = document_date(frontmatter)
    return PageRead(
        selected=page,
        data=document.data,
        view=view,
        state=state,
        in_window=day is not None and day >= since,
        landed=has_landed_post(ledgers, source_shas(frontmatter)),
    )


def _unsafe_marker(post: Post) -> str | None:
    """Where the composed post holds a comment marker, if it does."""
    for label, text in (("title", post.title), ("description", post.description)):
        for marker in _COMMENT_MARKERS:
            if marker in text:
                return f"the composed {label} holds {marker!r}"
    return None


def _text_below_stamp(content: str) -> str:
    return content.partition("\n")[2]


def _fill_page(
    read: PageRead,
    template: PostTemplate,
    resolver: Resolver,
    *,
    writing: bool,
    timeout_s: float,
    show_athletes: bool = False,
) -> PageResult:
    """Compose a page's post and, when ``writing``, splice it into the page.

    ``show_athletes`` is for ``check`` (9.4): an Athlete's page is composed too,
    never written, and still reports ``ATHLETES_TEXT``.

    Every failure path leaves the page's bytes as they were (10.9). A timeout
    is returned as ``TIMED_OUT`` with the variable last in ``variables``, for
    the caller to stop the run.
    """
    if read.view.status is not PageStatus.CURRENT or read.view.regions is None:
        detail = _NOT_CURRENT_DETAIL.get(read.view.status, read.view.detail)
        return _result(read, FillCode.PAGE_NOT_CURRENT, detail=detail)
    if read.state is RegionState.ATHLETES and not show_athletes:
        return _result(
            read,
            FillCode.ATHLETES_TEXT,
            detail="the post region holds the athlete's own text",
        )

    frontmatter = read.view.frontmatter
    start = document_start_time(frontmatter)
    if start is None:
        return _result(
            read, FillCode.NO_START_TIME, detail="the page records no start time"
        )
    refs = source_refs(frontmatter)
    binding = Binding(
        start.replace(tzinfo=None), sha_of_ref(refs[-1]) if refs else None
    )
    rel = read.selected.rel
    if not resolver.page_is_current(binding.page_key, rel, read.data):
        return _result(
            read,
            FillCode.INDEX_BEHIND,
            detail="the index does not hold this page as it is now",
        )

    outcomes: list[VariableOutcome] = []
    values: dict[str, str | None] = dict(page_values(frontmatter))
    for variable in sorted(template.variables, key=lambda v: v.name):
        outcome = resolver.resolve(variable, binding, timeout_s=timeout_s)
        outcomes.append(outcome)
        if outcome.code is not None:
            return _result(
                read,
                outcome.code,
                detail=outcome.detail,
                variables=tuple(outcomes),
            )
        values[variable.name] = outcome.value
    variables = tuple(outcomes)

    composed = compose_post(template.templates, values)
    if isinstance(composed, Refusal):
        return _result(
            read,
            _REFUSAL_CODES[composed.code],
            detail=composed.detail,
            variables=variables,
        )
    unsafe = _unsafe_marker(composed)
    if unsafe is not None:
        return _result(read, FillCode.UNSAFE_TEXT, detail=unsafe, variables=variables)

    content = render_filled(
        composed, template_digest=template.digest, as_of=binding.as_of
    )
    changed = _text_below_stamp(content) != _text_below_stamp(
        read.view.regions[POST_REGION]
    )
    if read.state is RegionState.ATHLETES:
        return _result(
            read,
            FillCode.ATHLETES_TEXT,
            detail="the post region holds the athlete's own text",
            variables=variables,
            post=composed,
            changed=changed,
        )
    if not changed:
        return _result(
            read,
            FillCode.UNCHANGED,
            variables=variables,
            post=composed,
            changed=False,
        )
    if not writing:
        return _result(
            read,
            FillCode.WOULD_FILL,
            variables=variables,
            post=composed,
            changed=True,
        )

    again = read_document(read.selected.path)
    if again is None or again.data != read.data:
        return _result(
            read,
            FillCode.PAGE_CHANGED,
            detail="the page was edited while it was being filled; the edit is kept",
            variables=variables,
            post=composed,
            changed=True,
        )
    updated = replace_region(read.view.text, POST_REGION, content)
    if updated is None:
        raise AssertionError("a current page holds a post region")
    try:
        write_bytes_if_changed(read.selected.path, updated.encode("utf-8"))
    except OSError as exc:
        return _result(
            read,
            FillCode.WRITE_FAILED,
            detail=f"the page could not be written: {exc.strerror or exc}",
            variables=variables,
            post=composed,
            changed=True,
        )
    return _result(
        read, FillCode.FILLED, variables=variables, post=composed, changed=True
    )


@dataclass(frozen=True)
class IndexGate:
    """Whether the sync's index refresh left an index the pass may read."""

    open: bool
    reason: str | None  # fitdocs-written, set when closed
    next_step: str | None


def _pass_report(
    template: PostTemplate,
    *,
    waiting: int,
    unavailable: Unavailable | None = None,
    problems: tuple[str, ...] = (),
    rows: tuple[PageResult, ...] = (),
    stopped: FillCode | None = None,
    stopped_variable: str | None = None,
) -> FillReport:
    return FillReport(
        command="pass",
        writing=True,
        template=TemplateSummary(template.path.name, template.since, template.digest),
        template_problems=problems,
        waiting=waiting,
        unavailable=unavailable,
        rows=rows,
        athletes_left_out=0,
        published_left_out=0,
        older_template=0,
        stopped=stopped,
        stopped_variable=stopped_variable,
    )


def _waiting_candidates(data_root: Path, since: date) -> list[PageRead]:
    """Waiting pages in the window, in file-name order, landed flag unset."""
    candidates: list[PageRead] = []
    for page in select_pages(data_root, (), cwd=data_root):
        read = read_for_fill(page, since=since, ledgers=())
        if (
            isinstance(read, PageRead)
            and read.state is RegionState.WAITING
            and read.in_window
        ):
            candidates.append(read)
    return candidates


def run_pass(
    data_root: Path,
    template: PostTemplate,
    *,
    gate: IndexGate,
    open_resolver: OpenResolver,
    monotonic: Callable[[], float],
) -> FillReport:
    """Fill the Eligible pages: Waiting, in the window, with no landed post.

    The budget starts when the gate has passed, and is checked before each
    page. Nothing is written unless the gate is open, the resolver opened and
    the template's SQL was accepted.
    """
    candidates = _waiting_candidates(data_root, template.since)
    if not candidates:
        return _pass_report(template, waiting=0)
    try:
        ledgers = load_ledgers(data_root, {})
    except PublishLedgerError as exc:
        return _pass_report(
            template,
            waiting=len(candidates),
            unavailable=Unavailable(
                f"the publish records cannot be read ({exc})",
                "fix the file it names, then run fitdocs sync again",
            ),
        )
    eligible = [
        read
        for read in candidates
        if not has_landed_post(ledgers.values(), source_shas(read.view.frontmatter))
    ]
    if not eligible:
        return _pass_report(template, waiting=0)
    if not gate.open:
        return _pass_report(
            template,
            waiting=len(eligible),
            unavailable=Unavailable(
                gate.reason or "the index is not ready",
                gate.next_step or "run fitdocs index",
            ),
        )
    started = monotonic()
    resolver = open_resolver()
    if isinstance(resolver, Unavailable):
        return _pass_report(template, waiting=len(eligible), unavailable=resolver)
    try:
        problems = resolver.check(template)
        if problems:
            return _pass_report(template, waiting=len(eligible), problems=problems)
        rows: list[PageResult] = []
        stopped: FillCode | None = None
        stopped_variable: str | None = None
        left_over = f"the {PASS_BUDGET_S:g} second budget ran out"
        done = 0
        while done < len(eligible):
            if monotonic() - started >= PASS_BUDGET_S:
                stopped = FillCode.NOT_ATTEMPTED
                break
            result = _fill_page(
                eligible[done],
                template,
                resolver,
                writing=True,
                timeout_s=PASS_STATEMENT_TIMEOUT_S,
            )
            rows.append(result)
            done += 1
            if result.code is FillCode.TIMED_OUT:
                stopped = FillCode.TIMED_OUT
                stopped_variable = result.variables[-1].name
                left_over = f"{stopped_variable} timed out on an earlier page"
                break
        rows.extend(
            _result(read, FillCode.NOT_ATTEMPTED, detail=left_over)
            for read in eligible[done:]
        )
    finally:
        resolver.close()
    return _pass_report(
        template,
        waiting=sum(row.code is not FillCode.FILLED for row in rows),
        rows=tuple(rows),
        stopped=stopped,
        stopped_variable=stopped_variable,
    )


# --------------------------------------------------------------------------- #
# check and refill
# --------------------------------------------------------------------------- #


class _NoResolver:
    """Stands in for a resolver on rows that never reach the index."""

    def check(self, template: PostTemplate) -> tuple[str, ...]:
        raise AssertionError("this row never reaches the index")

    def page_is_current(self, page_key: str | None, path: str, data: bytes) -> bool:
        raise AssertionError("this row never reaches the index")

    def resolve(
        self, variable: Variable, binding: Binding, *, timeout_s: float
    ) -> VariableOutcome:
        raise AssertionError("this row never reaches the index")

    def close(self) -> None:
        raise AssertionError("this row never reaches the index")


def _report(
    command: str,
    *,
    writing: bool,
    template: PostTemplate | None,
    problems: tuple[str, ...] = (),
    waiting: int | None,
    unavailable: Unavailable | None = None,
    rows: tuple[PageResult, ...] = (),
    athletes_left_out: int = 0,
    published_left_out: int = 0,
    older_template: int | None = None,
    stopped: FillCode | None = None,
    stopped_variable: str | None = None,
) -> FillReport:
    assert command in ("check", "refill")
    return FillReport(
        command=command,  # type: ignore[arg-type]
        writing=writing,
        template=(
            None
            if template is None
            else TemplateSummary(template.path.name, template.since, template.digest)
        ),
        template_problems=problems,
        waiting=waiting,
        unavailable=unavailable,
        rows=rows,
        athletes_left_out=athletes_left_out,
        published_left_out=published_left_out,
        older_template=older_template,
        stopped=stopped,
        stopped_variable=stopped_variable,
    )


def _read_pages(
    pages: tuple[SelectedPage, ...],
    *,
    since: date,
    ledgers: Iterable[PublishLedger],
) -> list[PageRead | PageResult]:
    return [read_for_fill(page, since=since, ledgers=ledgers) for page in pages]


def _fill_entries(
    entries: list[PageRead | PageResult],
    template: PostTemplate,
    resolver: Resolver,
    *,
    writing: bool,
    show_athletes: bool,
) -> tuple[tuple[PageResult, ...], FillCode | None, str | None]:
    """Fill each entry in order; stop at the first timeout (10.12).

    Rows that need no index (an Athlete's page named in a refill, a page that
    is not current) are decided without the resolver. Returns the rows, and
    the stop code and variable.
    """
    rows: list[PageResult] = []
    stopped: FillCode | None = None
    stopped_variable: str | None = None
    left_over = ""
    for entry in entries:
        if isinstance(entry, PageResult):
            rows.append(entry)
            continue
        if stopped is not None:
            rows.append(_result(entry, FillCode.NOT_ATTEMPTED, detail=left_over))
            continue
        needs_index = entry.state in (RegionState.WAITING, RegionState.FILLED) or (
            show_athletes and entry.state is RegionState.ATHLETES
        )
        result = _fill_page(
            entry,
            template,
            resolver if needs_index else _NoResolver(),
            writing=writing,
            timeout_s=COMMAND_STATEMENT_TIMEOUT_S,
            show_athletes=show_athletes,
        )
        if result.code is FillCode.INDEX_BEHIND:  # 9.6, 10.10: name the next step
            result = replace(result, detail=f"{result.detail}; run fitdocs index")
        rows.append(result)
        if result.code is FillCode.TIMED_OUT:
            stopped = FillCode.TIMED_OUT
            stopped_variable = result.variables[-1].name
            left_over = f"{stopped_variable} timed out on an earlier page"
    return tuple(rows), stopped, stopped_variable


def _all_pages(data_root: Path) -> tuple[SelectedPage, ...]:
    return select_pages(data_root, (), cwd=data_root)


def run_check(
    data_root: Path,
    template: PostTemplate | PostTemplateError,
    pages: tuple[SelectedPage, ...],
    *,
    ledgers: Mapping[str, PublishLedger] | PublishLedgerError,
    open_resolver: OpenResolver,
) -> FillReport:
    """Validate the template and its SQL, count what the next sync would fill,
    and show each named page. Writes nothing.

    Unreadable ledgers are one more problem, with ``waiting`` None and pages
    shown without a landed flag. An unavailable index still reports the
    template's own problems and says the SQL was not checked.
    """
    parsed = None if isinstance(template, PostTemplateError) else template
    problems: tuple[str, ...] = (
        tuple(template.problems) if isinstance(template, PostTemplateError) else ()
    )
    readable = not isinstance(ledgers, PublishLedgerError)
    ledger_list = (
        list(ledgers.values()) if not isinstance(ledgers, PublishLedgerError) else []
    )

    # Without the file there is no `since` and no digest, so neither count is known.
    waiting: int | None = None if not readable or parsed is None else 0
    older: int | None = None if parsed is None else 0
    reads: dict[str, PageRead | PageResult] = {}
    if parsed is not None:
        for page in _all_pages(data_root):
            read = read_for_fill(page, since=parsed.since, ledgers=ledger_list)
            if isinstance(read, PageRead):
                if not readable:
                    read = replace(read, landed=None)
                elif (
                    read.state is RegionState.WAITING
                    and read.in_window
                    and not read.landed
                ):
                    assert waiting is not None
                    waiting += 1
                if read.state is RegionState.FILLED and read.view.regions is not None:
                    _, stamp = classify(read.view.regions[POST_REGION])
                    if stamp is not None and stamp.template != parsed.digest:
                        assert older is not None
                        older += 1
        for page in pages:
            read = read_for_fill(page, since=parsed.since, ledgers=ledger_list)
            if isinstance(read, PageRead) and not readable:
                read = replace(read, landed=None)
            reads[page.rel] = read
    ledger_problems: tuple[str, ...] = ()
    if isinstance(ledgers, PublishLedgerError):
        ledger_problems = (
            f"the publish records cannot be read ({ledgers}); "
            "fix the file it names, then run the check again",
        )

    def report(**more: object) -> FillReport:
        return _report(
            "check",
            writing=False,
            template=parsed,
            problems=problems + ledger_problems,
            waiting=waiting,
            older_template=older,
            **more,  # type: ignore[arg-type]
        )

    def unchecked() -> tuple[PageResult, ...]:
        """Req 9.3: a named page still shows its state, window and landed flag."""
        if parsed is None:  # no `since`, so no window to show
            return ()
        return tuple(
            entry
            if isinstance(entry, PageResult)
            else _result(entry, FillCode.NOT_ATTEMPTED)
            for entry in (reads[page.rel] for page in pages)
        )

    resolver = open_resolver()
    if isinstance(resolver, Unavailable):
        return report(
            unavailable=Unavailable(
                f"the SQL was not checked: {resolver.reason}", resolver.next_step
            ),
            rows=unchecked(),
        )
    try:
        if parsed is None:
            return report()
        sql_problems = resolver.check(parsed)
        if sql_problems:
            problems += sql_problems
            return report(rows=unchecked())
        rows, stopped, stopped_variable = _fill_entries(
            [reads[page.rel] for page in pages],
            parsed,
            resolver,
            writing=False,
            show_athletes=True,
        )
        return report(rows=rows, stopped=stopped, stopped_variable=stopped_variable)
    finally:
        resolver.close()


def run_refill(
    data_root: Path,
    template: PostTemplate,
    pages: tuple[SelectedPage, ...],
    *,
    writing: bool,
    ledgers: Mapping[str, PublishLedger],
    open_resolver: OpenResolver,
) -> FillReport:
    """Recompute posts: named pages (Waiting or Filled), else the Eligible and
    unpublished Filled pages in the window.

    A bare refill counts the Athlete's pages and the published pages it leaves
    out. The ledgers arrive already loaded.
    """
    ledger_list = list(ledgers.values())
    entries: list[PageRead | PageResult] = []
    athletes = published = 0
    for read in _read_pages(
        pages or _all_pages(data_root), since=template.since, ledgers=ledger_list
    ):
        if pages or isinstance(read, PageResult):
            if pages:
                entries.append(read)
            continue
        if read.state is None or not read.in_window:
            continue
        if read.state is RegionState.ATHLETES:
            athletes += 1
        elif read.landed:
            published += 1
        else:
            entries.append(read)

    def report(**more: object) -> FillReport:
        return _report(
            "refill",
            writing=writing,
            template=template,
            waiting=0,
            athletes_left_out=athletes,
            published_left_out=published,
            **more,  # type: ignore[arg-type]
        )

    resolver = open_resolver()
    if isinstance(resolver, Unavailable):
        return report(unavailable=resolver)
    try:
        problems = resolver.check(template)
        if problems:
            return report(problems=problems)
        rows, stopped, stopped_variable = _fill_entries(
            entries, template, resolver, writing=writing, show_athletes=False
        )
        return report(rows=rows, stopped=stopped, stopped_variable=stopped_variable)
    finally:
        resolver.close()
