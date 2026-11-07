"""Shared value types of the post-template package.

Defined once so that `resolve` and `engine` do not import each other. Values
only: the one behavior here is the report's derived counts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from fitdocs.publish.request import Post


class FillCode(StrEnum):
    FILLED = "filled"
    WOULD_FILL = "would_fill"
    UNCHANGED = "unchanged"  # refill composed the text the page holds (10.11)
    VALUE_MISSING = "value_missing"  # 4.2
    TITLE_EMPTY = "title_empty"  # 4.4
    UNSAFE_TEXT = "unsafe_text"  # 4.5: composed text holds a comment marker
    NO_START_TIME = "no_start_time"  # 3.3
    INDEX_BEHIND = "index_behind"  # 6.5, 9.6, 10.10
    SHAPE_INVALID = "shape_invalid"  # 3.5
    VALUE_REFUSED = "value_refused"  # 3.7, 3.8, 3.9
    STATEMENT_FAILED = "statement_failed"
    TIMED_OUT = "timed_out"  # 7.3, 10.12
    NOT_ATTEMPTED = "not_attempted"  # after a stop (7.3)
    PAGE_NOT_CURRENT = "page_not_current"  # older, newer, damaged or unreadable (5.9)
    PAGE_CHANGED = "page_changed"  # edited during the run (5.8)
    WRITE_FAILED = "write_failed"
    ATHLETES_TEXT = "athletes_text"  # 10.5


class RegionState(StrEnum):
    WAITING = "waiting"
    FILLED = "filled"
    ATHLETES = "athletes"


#: Codes of a row that is not a failure: the page was filled, would be, already
#: held the text, or holds the athlete's own text. Every other code fails.
_NOT_FAILING: frozenset[FillCode] = frozenset(
    {
        FillCode.FILLED,
        FillCode.WOULD_FILL,
        FillCode.UNCHANGED,
        FillCode.ATHLETES_TEXT,
    }
)


@dataclass(frozen=True)
class Binding:
    as_of: datetime  # naive local wall clock (3.1)
    page_key: str | None  # None: the page records no archived base


@dataclass(frozen=True)
class VariableOutcome:
    name: str
    value: str | None  # None: absent (3.4) or failed
    code: FillCode | None  # None: resolved, value present or absent
    detail: str | None  # fitdocs-written, or the database's message


@dataclass(frozen=True)
class PageResult:
    page: str  # data-root-relative POSIX path
    state: RegionState | None  # None when the page could not be classified
    in_window: bool
    # the page has a landed publish post (10.7, 9.3); None: check could not
    # read the ledgers, so the flag is not shown
    landed: bool | None
    code: FillCode
    detail: str | None
    variables: tuple[VariableOutcome, ...]
    post: Post | None  # composed post, when there is one
    changed: bool | None  # refill and check: would the text change


@dataclass(frozen=True)
class Unavailable:
    reason: str  # fitdocs-written: "the index is not built", and so on
    next_step: str  # "run fitdocs index", and so on


@dataclass(frozen=True)
class TemplateSummary:
    path: str  # data-root-relative
    since: date
    digest: str


@dataclass(frozen=True)
class FillReport:
    command: Literal["pass", "check", "refill"]
    writing: bool
    template: TemplateSummary | None  # None when the file was refused
    template_problems: tuple[str, ...]  # 1.x and 2.x, located
    # pass: Eligible pages left unfilled, or candidates when ledgers are
    # unreadable (7.5, 6.4, 6.8); check: Eligible pages (9.2), None when the
    # ledgers cannot be read and the count is not shown; refill: 0
    waiting: int | None
    unavailable: (
        Unavailable | None
    )  # gate closed, index unavailable, ledgers unreadable
    rows: tuple[PageResult, ...]
    athletes_left_out: int  # 10.6
    published_left_out: int  # 10.6: a bare refill skips pages with a landed post
    older_template: int | None  # 9.2; None: check without a parsed template
    stopped: FillCode | None  # TIMED_OUT or NOT_ATTEMPTED after budget (7.4)
    stopped_variable: str | None

    @property
    def wrote(self) -> tuple[str, ...]:
        """Pages written this run. `PageResult.landed` is a publish record's
        state, not a write, so a written page is one whose code is FILLED."""
        return tuple(row.page for row in self.rows if row.code is FillCode.FILLED)

    @property
    def landed_changed(self) -> tuple[str, ...]:
        """Pages whose text changes (or would) and that have a landed post (10.7).

        The next ``fitdocs publish --yes`` updates the posted activity for these.
        """
        return tuple(
            row.page
            for row in self.rows
            if row.code in (FillCode.FILLED, FillCode.WOULD_FILL) and row.landed is True
        )

    @property
    def counts(self) -> Mapping[str, int]:
        """Rows per code, in `FillCode` order; codes with no row are absent."""
        tally = {code: 0 for code in FillCode}
        for row in self.rows:
            tally[row.code] += 1
        return {code.value: n for code, n in tally.items() if n}

    @property
    def failed(self) -> bool:
        """Any problem, an unavailable index, or a failing row."""
        return (
            bool(self.template_problems)
            or self.unavailable is not None
            or any(row.code not in _NOT_FAILING for row in self.rows)
        )
