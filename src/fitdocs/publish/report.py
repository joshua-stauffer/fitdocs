"""Text and JSON renderers for a publish run and the target listing
(publish-core Req 1.6, 7.9, 7.10, 8.10, 14.1, 14.6).

Only fitdocs's own words are printed: a code, the code's fixed explanation, a
page name, a target name, a fitdocs-written detail, the composed post, and a
link a landed result kept. Counts and explanations list codes in vocabulary
order, so the output does not depend on the order the rows arrived in.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Final

from fitdocs.publish.engine import PublishReport, ResultRow
from fitdocs.publish.outcomes import (
    LANDED_CODES,
    OUTCOMES,
    PublishCode,
    explanation,
)
from fitdocs.publish.targets import TargetRow

__all__ = [
    "REPORT_FORMAT",
    "render_json",
    "render_targets_json",
    "render_targets_text",
    "render_text",
]

REPORT_FORMAT: Final[int] = 1

_DRY_RUN_LINE: Final[str] = (
    "fitdocs publish: dry run; nothing is sent (add --yes to post)."
)
_POSTING_LINE: Final[str] = "fitdocs publish: posting."
_NO_TARGETS: Final[str] = "No publish target is configured."

#: The codes whose row prints the post it would send.
_POST_PRINTED: Final[frozenset[PublishCode]] = frozenset(
    {PublishCode.WOULD_POST, PublishCode.WOULD_UPDATE}
)


def _counts(rows: Sequence[ResultRow]) -> dict[PublishCode, int]:
    """Row counts by code, listed in vocabulary order; absent codes omitted."""
    held = {row.code for row in rows}
    return {
        code: sum(1 for row in rows if row.code == code)
        for code in OUTCOMES
        if code in held
    }


def _link(row: ResultRow) -> str | None:
    """The link of a landed result only (Req 1.6: the permitted link)."""
    return row.link if row.code in LANDED_CODES else None


def _row_lines(row: ResultRow) -> list[str]:
    subject = row.page if row.target is None else f"{row.page} -> {row.target}"
    head = f"{subject}: {row.code.value}"
    if row.detail is not None:
        head += f" ({row.detail})"
    lines = [head]
    if row.post is not None and row.code in _POST_PRINTED:
        lines.append(f"  title: {row.post.title}")
        if row.post.description != "":
            lines.append("  description:")
            for each in row.post.description.split("\n"):
                lines.append(f"    {each}" if each != "" else "")
    link = _link(row)
    if link is not None:
        lines.append(f"  link: {link}")
    if row.link_refused:
        lines.append("  link: refused")
    return lines


def render_text(report: PublishReport) -> str:
    """The text report: mode line, one block per row, counts, explanations."""
    lines = [_POSTING_LINE if report.posting else _DRY_RUN_LINE]
    for row in report.rows:
        lines.extend(_row_lines(row))
    counts = _counts(report.rows)
    tally = (
        ", ".join(f"{n} {code.value}" for code, n in counts.items())
        if counts
        else "no results"
    )
    pages = "page" if report.not_opted_in == 1 else "pages"
    lines.append(
        f"{tally}; {report.not_opted_in} {pages} opted in to no selected target."
    )
    if counts:
        lines.append("")
        lines.extend(f"{code.value}: {explanation(code)}" for code in counts)
    return "\n".join(lines)


def _dump(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False)


def render_json(report: PublishReport) -> str:
    """The versioned JSON document for a run (``REPORT_FORMAT``)."""
    counts = _counts(report.rows)
    results = [
        {
            "page": row.page,
            "target": row.target,
            "code": row.code.value,
            "decision": None if row.decision is None else row.decision.value,
            "title": None if row.post is None else row.post.title,
            "description": None if row.post is None else row.post.description,
            "link": _link(row),
            "link_refused": row.link_refused,
            "detail": row.detail,
        }
        for row in report.rows
    ]
    return _dump(
        {
            "format": REPORT_FORMAT,
            "posting": report.posting,
            "results": results,
            "counts": {code.value: n for code, n in counts.items()},
            "not_opted_in": report.not_opted_in,
            "explanations": {code.value: explanation(code) for code in counts},
        }
    )


def render_targets_text(rows: Sequence[TargetRow]) -> str:
    """One line per target in the order given, then each state's explanation."""
    if not rows:
        return _NO_TARGETS
    lines = [
        f"{row.name}: {row.connector} ({row.display_name}); "
        f"capabilities: {', '.join(row.capabilities)}; state: {row.state.value}"
        for row in rows
    ]
    held = {row.state for row in rows}
    lines.append("")
    lines.extend(
        f"{code.value}: {explanation(code)}" for code in OUTCOMES if code in held
    )
    return "\n".join(lines)


def render_targets_json(rows: Sequence[TargetRow]) -> str:
    """The versioned JSON listing (``REPORT_FORMAT``)."""
    return _dump(
        {
            "format": REPORT_FORMAT,
            "targets": [
                {
                    "name": row.name,
                    "connector": row.connector,
                    "display_name": row.display_name,
                    "capabilities": list(row.capabilities),
                    "state": row.state.value,
                    "explanation": explanation(row.state),
                }
                for row in rows
            ],
        }
    )
