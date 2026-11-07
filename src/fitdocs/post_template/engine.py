"""Fill one workout page's ``post`` region (post-templates task 3.1).

Requirements 3.3, 3.10, 4.1 to 4.6, 5.6 to 5.9, 6.5, 10.4, 10.9 and 10.11. This
module holds the per-page pieces: reading a page once as bytes
(:func:`read_for_fill`) and filling one page (:func:`_fill_page`). The pass,
``check`` and ``refill`` callers extend it; they pick the pages and give each
call its resolver, its statement timeout and whether it may write.

The resolver is declared here as a protocol and ``resolve.SessionResolver``
satisfies it structurally, so this module imports neither ``resolve`` nor
``query``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
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
    PageResult,
    RegionState,
    Unavailable,
    VariableOutcome,
)
from fitdocs.post_template.region import classify, render_filled
from fitdocs.post_template.template import PostTemplate, Variable
from fitdocs.publish.compose import Refusal, compose_post
from fitdocs.publish.ledger import PublishLedger, has_landed_post
from fitdocs.publish.outcomes import PublishCode
from fitdocs.publish.pages import (
    PageStatus,
    PageView,
    SelectedPage,
    _status,
    source_shas,
)
from fitdocs.publish.request import Post
from fitdocs.publish.values import page_values

__all__ = [
    "OpenResolver",
    "PageRead",
    "Resolver",
    "read_for_fill",
]


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
    landed: bool  # a landed publish post is recorded for the page


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
) -> PageResult:
    """Compose a page's post and, when ``writing``, splice it into the page.

    Every failure path leaves the page's bytes as they were (10.9). A timeout
    is returned as ``TIMED_OUT`` with the variable last in ``variables``, for
    the caller to stop the run.
    """
    if read.view.status is not PageStatus.CURRENT or read.view.regions is None:
        detail = _NOT_CURRENT_DETAIL.get(read.view.status, read.view.detail)
        return _result(read, FillCode.PAGE_NOT_CURRENT, detail=detail)
    if read.state is RegionState.ATHLETES:
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
