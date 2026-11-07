"""Text and JSON rendering of a fill report (post-templates task 3.4;
Req 7.4, 7.5, 7.6, 9.2 to 9.6, 10.5 to 10.8, 11.2).

Plain text only: the CLI prints it with markup off. Counts and flags that are
None are not shown in text and are null in JSON.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final

from fitdocs.post_template.engine import PASS_BUDGET_S, PASS_STATEMENT_TIMEOUT_S
from fitdocs.post_template.model import (
    FillCode,
    FillReport,
    PageResult,
    VariableOutcome,
)

__all__ = ["NEXT_STEPS", "render_json", "render_pass_text", "render_text"]

MAX_CAUSE_LINES: Final = 5

#: The fixed next step for each code that can be a cause of a page staying
#: unfilled. A code with no entry (filled, would fill, unchanged, the athlete's
#: text, and the two stop codes, which have stop notes) is never a cause line.
NEXT_STEPS: Final[Mapping[FillCode, str]] = {
    FillCode.VALUE_MISSING: (
        "make it optional with {?...}, write the post by hand, or fix the SQL"
    ),
    FillCode.TITLE_EMPTY: "keep some text in the title, or write the post by hand",
    FillCode.UNSAFE_TEXT: (
        "remove the comment marker from the value or the template, "
        "or write the post by hand"
    ),
    FillCode.NO_START_TIME: "the page records no start time; write the post by hand",
    FillCode.INDEX_BEHIND: "run fitdocs index, then run fitdocs sync again",
    FillCode.SHAPE_INVALID: (
        "fix the SQL so it returns one column and at most one row"
    ),
    FillCode.VALUE_REFUSED: (
        "change the SQL to return an integer, a decimal, a date or one line of "
        "text (fitdocs post-template check says why), or write the post by hand"
    ),
    FillCode.STATEMENT_FAILED: (
        "fix the SQL; fitdocs post-template check shows the database's message"
    ),
    FillCode.PAGE_NOT_CURRENT: (
        "run fitdocs regen to bring the page up to date or repair its markers, "
        "or write the post by hand"
    ),
    FillCode.PAGE_CHANGED: "the page changed during the run; run fitdocs sync again",
    FillCode.WRITE_FAILED: (
        "check the page's permissions and free space, then run fitdocs sync again"
    ),
}

_CODE_ORDER: Final = {code: index for index, code in enumerate(FillCode)}


# --------------------------------------------------------------------------- #
# The pass
# --------------------------------------------------------------------------- #


def _cause_variable(row: PageResult) -> str:
    """What a cause line names: the placeholder a missing value is for (the
    engine puts it in the row's detail), else the variable whose outcome carries
    the row's code, else the empty string."""
    if row.code is FillCode.VALUE_MISSING:
        return row.detail or ""
    for outcome in row.variables:
        if outcome.code is row.code:
            return outcome.name
    return ""


def _stop_note(report: FillReport) -> str:
    if report.stopped is FillCode.TIMED_OUT:
        who = report.stopped_variable or "a statement"
        return (
            f"stopped after {who} took longer than {PASS_STATEMENT_TIMEOUT_S:g} seconds"
        )
    if report.stopped is FillCode.NOT_ATTEMPTED:
        return f"stopped after {PASS_BUDGET_S:g} seconds"
    return ""


def _causes(report: FillReport) -> list[str]:
    groups: dict[tuple[FillCode, str], list[str]] = {}
    for row in report.rows:
        if row.code in NEXT_STEPS:
            groups.setdefault((row.code, _cause_variable(row)), []).append(row.page)
    ranked = sorted(
        groups.items(),
        key=lambda item: (-len(item[1]), _CODE_ORDER[item[0][0]], item[0][1]),
    )
    lines: list[str] = []
    for (code, variable), pages in ranked[:MAX_CAUSE_LINES]:
        subject = f"{code.value} for {variable}" if variable else code.value
        lines.append(
            f"  {len(pages)} {subject}, for example {pages[0]}: {NEXT_STEPS[code]}"
        )
    return lines


def render_pass_text(report: FillReport) -> str:
    """The pass report; empty when there is nothing to say (7.6)."""
    if not report.rows and not report.template_problems and report.unavailable is None:
        return ""
    lines: list[str] = []
    if report.unavailable is not None:
        waiting = "" if report.waiting is None else f" {report.waiting} waiting;"
        lines.append(
            f"Post template:{waiting} {report.unavailable.reason}. "
            f"{report.unavailable.next_step}."
        )
    else:
        head = f"Post template: {len(report.wrote)} filled"
        if report.waiting is not None:
            head += f", {report.waiting} waiting"
        note = _stop_note(report)
        lines.append(f"{head}; {note}." if note else f"{head}.")
    lines.extend(_causes(report))
    if report.template_problems:
        lines.append(
            "The post template has a problem; "
            "run fitdocs post-template check to see it."
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Check and refill: text
# --------------------------------------------------------------------------- #


def _pages(count: int, kind: str) -> str:
    noun = "page" if count == 1 else "pages"
    return f"{count} {kind} {noun} left out"


def _yes_no(flag: bool) -> str:
    return "yes" if flag else "no"


def _variable_line(outcome: VariableOutcome) -> str:
    if outcome.code is not None:
        detail = f": {outcome.detail}" if outcome.detail else ""
        return f"  variable {outcome.name}: {outcome.code.value}{detail}"
    if outcome.value is None:
        return f"  variable {outcome.name}: no value"
    return f"  variable {outcome.name}: {outcome.value}"


def _row_lines(row: PageResult) -> list[str]:
    lines = [row.page]
    lines.append(f"  state: {row.state.value if row.state else 'unclassified'}")
    lines.append(f"  in window: {_yes_no(row.in_window)}")
    if row.landed is not None:
        lines.append(f"  landed post: {_yes_no(row.landed)}")
    lines.append(f"  result: {row.code.value}")
    if row.changed is not None:
        lines.append(f"  text changes: {_yes_no(row.changed)}")
    if row.detail:
        lines.append(f"  detail: {row.detail}")
    lines.extend(_variable_line(outcome) for outcome in row.variables)
    if row.post is not None:
        lines.append(f"  post title: {row.post.title}")
        description = row.post.description.split("\n") if row.post.description else []
        if description:
            lines.append("  post description:")
            lines.extend(f"    {line}".rstrip() for line in description)
        else:
            lines.append("  post description: empty")
    return lines


def _check_stop_note(report: FillReport) -> str:
    if report.stopped is FillCode.TIMED_OUT:
        who = report.stopped_variable or "a statement"
        return f"Stopped: {who} timed out; the pages after it were not attempted."
    if report.stopped is FillCode.NOT_ATTEMPTED:
        return (
            "Stopped: the time budget ran out; the pages after it were not attempted."
        )
    return ""


def render_text(report: FillReport) -> str:
    """The check or refill report as plain text."""
    lines: list[str] = []
    if report.template is None:
        lines.append("Template: not accepted")
    else:
        template = report.template
        lines.append(
            f"Template: {template.path} (since {template.since.isoformat()}, "
            f"digest {template.digest})"
        )
    lines.extend(f"Problem: {problem}" for problem in report.template_problems)
    if report.unavailable is not None:
        reason = report.unavailable.reason
        lines.append(
            f"{reason[:1].upper()}{reason[1:]}. {report.unavailable.next_step}."
        )
    if report.command == "check" and report.waiting is not None:
        lines.append(f"Eligible pages: {report.waiting}")
    if report.command == "check" and report.older_template is not None:
        lines.append(f"Filled from an earlier template: {report.older_template}")
    note = _check_stop_note(report)
    if note:
        lines.append(note)
    for row in report.rows:
        lines.extend(_row_lines(row))
    if report.counts:
        tally = ", ".join(f"{code} {n}" for code, n in report.counts.items())
        lines.append(f"Pages: {tally}")
    if report.writing and report.wrote:
        noun = "page" if len(report.wrote) == 1 else "pages"
        lines.append(f"Wrote {len(report.wrote)} {noun}: {', '.join(report.wrote)}")
    if report.athletes_left_out:
        athletes = _pages(report.athletes_left_out, "Athlete's")
        lines.append(f"{athletes}.")
    if report.published_left_out:
        published = _pages(report.published_left_out, "published")
        lines.append(f"{published}; name a page to refill it.")
    if report.landed_changed:
        lines.append(
            "The next fitdocs publish --yes will update the posted activity for: "
            + ", ".join(report.landed_changed)
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Check and refill: JSON
# --------------------------------------------------------------------------- #


def _row_json(row: PageResult) -> dict[str, Any]:
    return {
        "page": row.page,
        "state": None if row.state is None else row.state.value,
        "in_window": row.in_window,
        "landed": row.landed,
        "code": row.code.value,
        "detail": row.detail,
        "variables": [
            {
                "name": outcome.name,
                "value": outcome.value,
                "code": None if outcome.code is None else outcome.code.value,
                "detail": outcome.detail,
            }
            for outcome in row.variables
        ],
        "post": (
            None
            if row.post is None
            else {"title": row.post.title, "description": row.post.description}
        ),
        "changed": row.changed,
    }


def render_json(report: FillReport) -> str:
    """The check or refill report as JSON carrying the fields the text shows."""
    template = report.template
    unavailable = report.unavailable
    payload: dict[str, Any] = {
        "command": report.command,
        "writing": report.writing,
        "template": (
            None
            if template is None
            else {
                "path": template.path,
                "since": template.since.isoformat(),
                "digest": template.digest,
            }
        ),
        "problems": list(report.template_problems),
        "unavailable": (
            None
            if unavailable is None
            else {"reason": unavailable.reason, "next_step": unavailable.next_step}
        ),
        "pages": [_row_json(row) for row in report.rows],
        "counts": dict(report.counts),
        "waiting": report.waiting,
        "athletes_left_out": report.athletes_left_out,
        "published_left_out": report.published_left_out,
        "older_template": report.older_template,
        "stopped": None if report.stopped is None else report.stopped.value,
        "stopped_variable": report.stopped_variable,
        "wrote": list(report.wrote),
        "landed_changed": list(report.landed_changed),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
