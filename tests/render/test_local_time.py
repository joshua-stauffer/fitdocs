"""A page's local date and time (workout-docs Amendment 6, Req 2.9, 2.10, 5.13).

One rule names, dates and titles a page: the activity's start in the offset its
recording device kept when the file records one (fit-ingest Req 4.13), and
otherwise in the zone the caller passes, at the offset that zone had on the
activity's own date. Every case checks all five places that state the local
time -- the filename stem, ``date``, ``start_time``, ``title`` and the H1 -- so
no one of them can follow a different rule from the rest.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

import pytest
import yaml

from fitdocs import compute_metrics, parse_fit
from fitdocs.layout import doc_stem
from fitdocs.render import DocContext, render_document
from fitdocs.render.frontmatter import build_frontmatter

_BERLIN = ZoneInfo("Europe/Berlin")
_NEW_YORK = ZoneInfo("America/New_York")
_UID = "0" * 64


def _ctx(
    run_fit_bytes: bytes,
    start: datetime,
    offset: timedelta | None,
    tz: tzinfo,
) -> DocContext:
    activity = dataclasses.replace(
        parse_fit(run_fit_bytes), start_time=start, local_offset=offset
    )
    return DocContext(
        activity=activity,
        metrics=compute_metrics(activity),
        athlete=None,
        doc_stem=doc_stem(activity, _UID, tz, lambda _: False),
        source_refs=("fit-archive/aaaa.fit",),
        tz=tz,
    )


@pytest.mark.parametrize(
    ("start", "offset", "tz", "local"),
    [
        (
            datetime(2018, 12, 2, 22, 16, 44, tzinfo=UTC),
            timedelta(hours=-5),
            _BERLIN,
            "2018-12-02T17:16:44-05:00",
        ),
        (
            datetime(2024, 11, 3, 6, 27, 5, tzinfo=UTC),
            timedelta(hours=1),
            _NEW_YORK,
            "2024-11-03T07:27:05+01:00",
        ),
        (
            datetime(2020, 2, 25, 21, 30, 35, tzinfo=UTC),
            timedelta(hours=13),
            _BERLIN,
            "2020-02-26T10:30:35+13:00",
        ),
        (
            datetime(2024, 3, 1, 23, 40, tzinfo=UTC),
            timedelta(0),
            _BERLIN,
            "2024-03-01T23:40:00+00:00",
        ),
        (
            datetime(2024, 1, 10, 17, 5, 21, tzinfo=UTC),
            None,
            _BERLIN,
            "2024-01-10T18:05:21+01:00",
        ),
        (
            datetime(2024, 7, 10, 16, 5, 21, tzinfo=UTC),
            None,
            _BERLIN,
            "2024-07-10T18:05:21+02:00",
        ),
    ],
    ids=[
        "recorded-west-previous-day",
        "recorded-wins-over-zone",
        "recorded-east-next-day",
        "recorded-zero",
        "zone-winter",
        "zone-summer",
    ],
)
def test_every_local_time_on_the_page_follows_one_rule(
    run_fit_bytes: bytes,
    start: datetime,
    offset: timedelta | None,
    tz: tzinfo,
    local: str,
) -> None:
    ctx = _ctx(run_fit_bytes, start, offset, tz)
    day, clock = local[:10], local[11:16]

    front = yaml.safe_load(build_frontmatter(ctx).strip().strip("-"))
    h1 = [
        line
        for line in render_document(ctx).markdown.splitlines()
        if line.startswith("# ")
    ]

    assert ctx.doc_stem == f"{day}-run-{clock.replace(':', '')}"
    assert front["date"] == day
    assert front["start_time"] == local
    assert front["title"] == f"Run {day} {clock}"
    assert h1 == [f"# Run {day} {clock}"]
