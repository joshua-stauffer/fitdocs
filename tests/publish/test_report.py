"""Text and JSON renderers for publish runs and target listings (publish-core
task 6.4; Req 1.6, 7.9, 7.10, 8.10, 14.1, 14.6).

Both shapes are pinned against full literals. The row fixtures arrive in an
order that differs from the vocabulary order (would_update before would_post,
value_missing before unchanged), repeat one code, and carry pairwise-distinct
pages, titles and links.
"""

from __future__ import annotations

import json

from fitdocs.publish.engine import PublishReport, ResultRow
from fitdocs.publish.outcomes import OUTCOMES, PublishCode, explanation
from fitdocs.publish.report import (
    REPORT_FORMAT,
    render_json,
    render_targets_json,
    render_targets_text,
    render_text,
)
from fitdocs.publish.request import Post
from fitdocs.publish.targets import TargetRow

C = PublishCode


def _row(
    page: str,
    target: str | None,
    code: PublishCode,
    *,
    decision: PublishCode | None = None,
    post: Post | None = None,
    link: str | None = None,
    link_refused: bool = False,
    detail: str | None = None,
) -> ResultRow:
    return ResultRow(
        page=page,
        target=target,
        code=code,
        decision=decision,
        post=post,
        link=link,
        link_refused=link_refused,
        detail=detail,
    )


def _dry_report() -> PublishReport:
    rows = (
        _row(
            "workouts/2026-10-30-run-1.md",
            "alpha",
            C.WOULD_UPDATE,
            decision=C.WOULD_UPDATE,
            post=Post("Run 2026-10-30 07:12", "Distance: 10.02 km\n\nPace: 5:00 /km"),
        ),
        _row(
            "workouts/2026-10-29-ride.md",
            "alpha",
            C.VALUE_MISSING,
            detail="avg_power_w",
        ),
        _row(
            "workouts/2026-10-28-run.md",
            "beta",
            C.WOULD_POST,
            decision=C.WOULD_POST,
            post=Post("Easy ünï", "Line one"),
            link="https://example.test/not-landed",
        ),
        _row(
            "workouts/2026-10-27-run.md",
            "beta",
            C.WOULD_POST,
            decision=C.WOULD_POST,
            post=Post("Tempo", ""),
        ),
        _row(
            "workouts/2026-10-26-run.md",
            "beta",
            C.UNCHANGED,
            decision=C.UNCHANGED,
        ),
        _row("workouts/2026-10-25-run.md", None, C.PAGE_UNREADABLE),
        _row(
            "workouts/2026-10-24-run.md",
            None,
            C.OPT_IN_INVALID,
            detail="<fitdocs text>",
        ),
    )
    return PublishReport(posting=False, rows=rows, not_opted_in=12, configured=2)


def _posting_report() -> PublishReport:
    rows = (
        _row(
            "workouts/a.md",
            "alpha",
            C.POSTED,
            decision=C.WOULD_POST,
            post=Post("Title A", "Body A"),
            link="https://example.test/a/1",
        ),
        _row(
            "workouts/b.md",
            "beta",
            C.UPLOADED,
            decision=C.WOULD_POST,
            post=Post("Title B", "Body B"),
            link="https://example.test/b/2",
        ),
        _row("workouts/c.md", "alpha", C.RATE_LIMITED, decision=C.WOULD_UPDATE),
        _row("workouts/d.md", "alpha", C.NOT_ATTEMPTED, decision=C.WOULD_POST),
        _row("workouts/e.md", "beta", C.POSTED, decision=C.WOULD_POST),
        _row(
            "workouts/f.md",
            "beta",
            C.POSTED,
            decision=C.WOULD_POST,
            link_refused=True,
        ),
        _row(
            "workouts/g.md",
            "alpha",
            C.REJECTED,
            decision=C.WOULD_POST,
            link_refused=True,
        ),
    )
    return PublishReport(posting=True, rows=rows, not_opted_in=0, configured=2)


DRY_TEXT = f"""\
fitdocs publish: dry run; nothing is sent (add --yes to post).
workouts/2026-10-30-run-1.md -> alpha: would_update
  title: Run 2026-10-30 07:12
  description:
    Distance: 10.02 km

    Pace: 5:00 /km
workouts/2026-10-29-ride.md -> alpha: value_missing (avg_power_w)
workouts/2026-10-28-run.md -> beta: would_post
  title: Easy ünï
  description:
    Line one
workouts/2026-10-27-run.md -> beta: would_post
  title: Tempo
workouts/2026-10-26-run.md -> beta: unchanged
workouts/2026-10-25-run.md: page_unreadable
workouts/2026-10-24-run.md: opt_in_invalid (<fitdocs text>)
2 would_post, 1 would_update, 1 unchanged, 1 opt_in_invalid, 1 page_unreadable, \
1 value_missing; 12 pages opted in to no selected target.

would_post: {explanation(C.WOULD_POST)}
would_update: {explanation(C.WOULD_UPDATE)}
unchanged: {explanation(C.UNCHANGED)}
opt_in_invalid: {explanation(C.OPT_IN_INVALID)}
page_unreadable: {explanation(C.PAGE_UNREADABLE)}
value_missing: {explanation(C.VALUE_MISSING)}"""

POSTING_TEXT = f"""\
fitdocs publish: posting.
workouts/a.md -> alpha: posted
  link: https://example.test/a/1
workouts/b.md -> beta: uploaded
  link: https://example.test/b/2
workouts/c.md -> alpha: rate_limited
workouts/d.md -> alpha: not_attempted
workouts/e.md -> beta: posted
workouts/f.md -> beta: posted
  link: refused
workouts/g.md -> alpha: rejected
  link: refused
3 posted, 1 uploaded, 1 rate_limited, 1 rejected, 1 not_attempted; \
0 pages opted in to no selected target.

posted: {explanation(C.POSTED)}
uploaded: {explanation(C.UPLOADED)}
rate_limited: {explanation(C.RATE_LIMITED)}
rejected: {explanation(C.REJECTED)}
not_attempted: {explanation(C.NOT_ATTEMPTED)}"""


def test_dry_run_text_is_pinned_to_a_full_literal() -> None:
    report = _dry_report()
    assert [row.code for row in report.rows] != sorted(
        (row.code for row in report.rows), key=list(OUTCOMES).index
    ), "the fixture must arrive out of vocabulary order"
    assert render_text(report) == DRY_TEXT


def test_posting_text_is_pinned_to_a_full_literal() -> None:
    assert render_text(_posting_report()) == POSTING_TEXT


def test_a_single_unlisted_page_is_singular_and_zero_rows_say_so() -> None:
    one = render_text(
        PublishReport(posting=False, rows=(), not_opted_in=1, configured=1)
    )
    assert one == (
        "fitdocs publish: dry run; nothing is sent (add --yes to post).\n"
        "no results; 1 page opted in to no selected target."
    )
    none = render_text(
        PublishReport(posting=True, rows=(), not_opted_in=0, configured=0)
    )
    assert none == (
        "fitdocs publish: posting.\nno results; 0 pages opted in to no selected target."
    )


def test_the_post_is_printed_for_would_codes_only() -> None:
    posted = _row(
        "workouts/p.md", "alpha", C.POSTED, post=Post("Kept Title", "Kept Body")
    )
    report = PublishReport(posting=True, rows=(posted,), not_opted_in=0, configured=1)
    text = render_text(report)
    assert "Kept Title" not in text
    assert "Kept Body" not in text


def test_a_link_is_printed_only_for_a_landed_code() -> None:
    pairs = tuple(
        _row(
            f"workouts/{code.value}.md",
            "alpha",
            code,
            link=f"https://x.test/{code.value}",
        )
        for code in (C.POSTED, C.UPLOADED, C.UNCHANGED, C.WOULD_POST, C.REJECTED)
    )
    report = PublishReport(posting=True, rows=pairs, not_opted_in=0, configured=1)
    text = render_text(report)
    assert text.count("  link: ") == 2
    assert "  link: https://x.test/posted" in text
    assert "  link: https://x.test/uploaded" in text
    links = {r["code"]: r["link"] for r in json.loads(render_json(report))["results"]}
    assert links == {
        "posted": "https://x.test/posted",
        "uploaded": "https://x.test/uploaded",
        "unchanged": None,
        "would_post": None,
        "rejected": None,
    }


def test_the_refused_marker_follows_the_post_and_link_lines() -> None:
    rows = (
        _row(
            "workouts/w.md",
            "alpha",
            C.WOULD_POST,
            post=Post("T", ""),
            link_refused=True,
        ),
        _row(
            "workouts/l.md",
            "alpha",
            C.POSTED,
            link="https://x.test/l",
            link_refused=True,
        ),
    )
    report = PublishReport(posting=True, rows=rows, not_opted_in=0, configured=1)
    assert render_text(report).split("\n")[1:7] == [
        "workouts/w.md -> alpha: would_post",
        "  title: T",
        "  link: refused",
        "workouts/l.md -> alpha: posted",
        "  link: https://x.test/l",
        "  link: refused",
    ]


DRY_JSON = {
    "format": 1,
    "posting": False,
    "results": [
        {
            "page": "workouts/2026-10-30-run-1.md",
            "target": "alpha",
            "code": "would_update",
            "decision": "would_update",
            "title": "Run 2026-10-30 07:12",
            "description": "Distance: 10.02 km\n\nPace: 5:00 /km",
            "link": None,
            "link_refused": False,
            "detail": None,
        },
        {
            "page": "workouts/2026-10-29-ride.md",
            "target": "alpha",
            "code": "value_missing",
            "decision": None,
            "title": None,
            "description": None,
            "link": None,
            "link_refused": False,
            "detail": "avg_power_w",
        },
        {
            "page": "workouts/2026-10-28-run.md",
            "target": "beta",
            "code": "would_post",
            "decision": "would_post",
            "title": "Easy ünï",
            "description": "Line one",
            "link": None,
            "link_refused": False,
            "detail": None,
        },
        {
            "page": "workouts/2026-10-27-run.md",
            "target": "beta",
            "code": "would_post",
            "decision": "would_post",
            "title": "Tempo",
            "description": "",
            "link": None,
            "link_refused": False,
            "detail": None,
        },
        {
            "page": "workouts/2026-10-26-run.md",
            "target": "beta",
            "code": "unchanged",
            "decision": "unchanged",
            "title": None,
            "description": None,
            "link": None,
            "link_refused": False,
            "detail": None,
        },
        {
            "page": "workouts/2026-10-25-run.md",
            "target": None,
            "code": "page_unreadable",
            "decision": None,
            "title": None,
            "description": None,
            "link": None,
            "link_refused": False,
            "detail": None,
        },
        {
            "page": "workouts/2026-10-24-run.md",
            "target": None,
            "code": "opt_in_invalid",
            "decision": None,
            "title": None,
            "description": None,
            "link": None,
            "link_refused": False,
            "detail": "<fitdocs text>",
        },
    ],
    "counts": {
        "would_post": 2,
        "would_update": 1,
        "unchanged": 1,
        "opt_in_invalid": 1,
        "page_unreadable": 1,
        "value_missing": 1,
    },
    "not_opted_in": 12,
    "explanations": {
        "would_post": explanation(C.WOULD_POST),
        "would_update": explanation(C.WOULD_UPDATE),
        "unchanged": explanation(C.UNCHANGED),
        "opt_in_invalid": explanation(C.OPT_IN_INVALID),
        "page_unreadable": explanation(C.PAGE_UNREADABLE),
        "value_missing": explanation(C.VALUE_MISSING),
    },
}


def _ordered(value: object) -> object:
    """Key order is part of the shape, so compare it as a list of pairs."""
    if isinstance(value, dict):
        return [(key, _ordered(inner)) for key, inner in value.items()]
    if isinstance(value, list):
        return [_ordered(inner) for inner in value]
    return value


def test_dry_run_json_is_pinned_to_a_full_literal_key_order_included() -> None:
    document = json.loads(render_json(_dry_report()))
    assert _ordered(document) == _ordered(DRY_JSON)
    assert render_json(_dry_report()) == json.dumps(
        DRY_JSON, indent=2, ensure_ascii=False
    )
    assert REPORT_FORMAT == 1


def _posting_result(
    page: str,
    target: str,
    code: str,
    *,
    title: str | None = None,
    description: str | None = None,
    link: str | None = None,
    link_refused: bool = False,
) -> dict[str, object]:
    return {
        "page": page,
        "target": target,
        "code": code,
        "decision": "would_update" if code == "rate_limited" else "would_post",
        "title": title,
        "description": description,
        "link": link,
        "link_refused": link_refused,
        "detail": None,
    }


POSTING_JSON = {
    "format": 1,
    "posting": True,
    "results": [
        _posting_result(
            "workouts/a.md",
            "alpha",
            "posted",
            title="Title A",
            description="Body A",
            link="https://example.test/a/1",
        ),
        _posting_result(
            "workouts/b.md",
            "beta",
            "uploaded",
            title="Title B",
            description="Body B",
            link="https://example.test/b/2",
        ),
        _posting_result("workouts/c.md", "alpha", "rate_limited"),
        _posting_result("workouts/d.md", "alpha", "not_attempted"),
        _posting_result("workouts/e.md", "beta", "posted"),
        _posting_result("workouts/f.md", "beta", "posted", link_refused=True),
        _posting_result("workouts/g.md", "alpha", "rejected", link_refused=True),
    ],
    "counts": {
        "posted": 3,
        "uploaded": 1,
        "rate_limited": 1,
        "rejected": 1,
        "not_attempted": 1,
    },
    "not_opted_in": 0,
    "explanations": {
        "posted": explanation(C.POSTED),
        "uploaded": explanation(C.UPLOADED),
        "rate_limited": explanation(C.RATE_LIMITED),
        "rejected": explanation(C.REJECTED),
        "not_attempted": explanation(C.NOT_ATTEMPTED),
    },
}


def test_posting_json_is_pinned_to_a_full_literal_key_order_included() -> None:
    out = render_json(_posting_report())
    assert _ordered(json.loads(out)) == _ordered(POSTING_JSON)
    assert out == json.dumps(POSTING_JSON, indent=2, ensure_ascii=False)


def test_empty_run_json_has_empty_collections() -> None:
    document = json.loads(
        render_json(PublishReport(posting=False, rows=(), not_opted_in=5, configured=0))
    )
    assert document == {
        "format": 1,
        "posting": False,
        "results": [],
        "counts": {},
        "not_opted_in": 5,
        "explanations": {},
    }


# --------------------------------------------------------------------------- #
# The target listing
# --------------------------------------------------------------------------- #

LISTING = (
    TargetRow(
        name="alpha",
        connector="intervals",
        display_name="Intervals.icu",
        capabilities=("push-activity", "annotate-remote-activity"),
        state=C.READY,
    ),
    TargetRow(
        name="beta",
        connector="other",
        display_name="Other Service",
        capabilities=("annotate-remote-activity",),
        state=C.CREDENTIALS_UNREADABLE,
    ),
    TargetRow(
        name="gamma",
        connector="other",
        display_name="Other Service",
        capabilities=("annotate-remote-activity", "resolve-remote-activity"),
        state=C.NOT_CONNECTED,
    ),
)
# Arrival order ready, credentials_unreadable, not_connected; vocabulary order is
# the reverse of that; alphabetical order is credentials_unreadable,
# not_connected, ready -- all three differ.


def test_targets_text_is_pinned_to_a_full_literal() -> None:
    assert render_targets_text(LISTING) == (
        "alpha: intervals (Intervals.icu); "
        "capabilities: push-activity, annotate-remote-activity; state: ready\n"
        "beta: other (Other Service); "
        "capabilities: annotate-remote-activity; state: credentials_unreadable\n"
        "gamma: other (Other Service); "
        "capabilities: annotate-remote-activity, resolve-remote-activity; "
        "state: not_connected\n"
        "\n"
        f"not_connected: {explanation(C.NOT_CONNECTED)}\n"
        f"credentials_unreadable: {explanation(C.CREDENTIALS_UNREADABLE)}\n"
        f"ready: {explanation(C.READY)}"
    )


def test_targets_json_is_pinned_to_a_full_literal_key_order_included() -> None:
    expected = {
        "format": 1,
        "targets": [
            {
                "name": "alpha",
                "connector": "intervals",
                "display_name": "Intervals.icu",
                "capabilities": ["push-activity", "annotate-remote-activity"],
                "state": "ready",
                "explanation": explanation(C.READY),
            },
            {
                "name": "beta",
                "connector": "other",
                "display_name": "Other Service",
                "capabilities": ["annotate-remote-activity"],
                "state": "credentials_unreadable",
                "explanation": explanation(C.CREDENTIALS_UNREADABLE),
            },
            {
                "name": "gamma",
                "connector": "other",
                "display_name": "Other Service",
                "capabilities": [
                    "annotate-remote-activity",
                    "resolve-remote-activity",
                ],
                "state": "not_connected",
                "explanation": explanation(C.NOT_CONNECTED),
            },
        ],
    }
    out = render_targets_json(LISTING)
    assert _ordered(json.loads(out)) == _ordered(expected)
    assert out == json.dumps(expected, indent=2, ensure_ascii=False)


def test_an_empty_listing_says_so_in_both_formats() -> None:
    assert render_targets_text(()) == "No publish target is configured."
    assert json.loads(render_targets_json(())) == {"format": 1, "targets": []}
