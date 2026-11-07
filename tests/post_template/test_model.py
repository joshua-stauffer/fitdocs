"""The report's derived counts (post-templates task 1.6)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from typing import get_type_hints

import pytest

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


def _row(page: str, code: FillCode, *, landed: bool = False) -> PageResult:
    return PageResult(
        page=page,
        state=RegionState.WAITING,
        in_window=True,
        landed=landed,
        code=code,
        detail=None,
        variables=(),
        post=None,
        changed=None,
    )


def _report(*rows: PageResult, waiting: int | None = 0) -> FillReport:
    return FillReport(
        command="pass",
        writing=True,
        template=None,
        template_problems=(),
        waiting=waiting,
        unavailable=None,
        rows=rows,
        athletes_left_out=0,
        published_left_out=0,
        older_template=0,
        stopped=None,
        stopped_variable=None,
    )


def test_wrote_is_the_filled_pages_whatever_their_publish_state() -> None:
    report = _report(
        _row("a.md", FillCode.FILLED, landed=False),
        _row("b.md", FillCode.WOULD_FILL, landed=True),
        _row("c.md", FillCode.FILLED, landed=True),
        _row("d.md", FillCode.UNCHANGED, landed=True),
        _row("e.md", FillCode.VALUE_MISSING, landed=False),
    )
    assert report.wrote == ("a.md", "c.md")
    assert _report().wrote == ()


def test_counts_are_per_code_in_fillcode_order_without_empty_codes() -> None:
    report = _report(
        _row("a.md", FillCode.WRITE_FAILED),
        _row("b.md", FillCode.FILLED),
        _row("c.md", FillCode.WRITE_FAILED),
        _row("d.md", FillCode.FILLED),
        _row("e.md", FillCode.FILLED),
    )
    assert dict(report.counts) == {"filled": 3, "write_failed": 2}
    assert list(report.counts) == ["filled", "write_failed"]
    assert dict(_report().counts) == {}


def test_failed_is_false_for_a_clean_report() -> None:
    clean = _report(
        _row("a.md", FillCode.FILLED),
        _row("b.md", FillCode.WOULD_FILL),
        _row("c.md", FillCode.UNCHANGED),
        _row("d.md", FillCode.ATHLETES_TEXT),
    )
    assert clean.failed is False
    assert _report().failed is False


def test_failed_on_each_of_its_causes_alone() -> None:
    base = _report(_row("a.md", FillCode.FILLED))
    assert replace(base, template_problems=("line 2: bad",)).failed is True
    assert (
        replace(base, unavailable=Unavailable("the index is not built", "x")).failed
        is True
    )
    assert _report(
        _row("a.md", FillCode.FILLED), _row("b.md", FillCode.WRITE_FAILED)
    ).failed
    for code in FillCode:
        if code in {
            FillCode.FILLED,
            FillCode.WOULD_FILL,
            FillCode.UNCHANGED,
            FillCode.ATHLETES_TEXT,
        }:
            continue
        assert _report(_row("a.md", FillCode.FILLED), _row("b.md", code)).failed, code


def test_waiting_accepts_none_for_a_count_that_is_not_shown() -> None:
    assert _report(waiting=None).waiting is None
    assert _report(waiting=0).waiting == 0
    assert get_type_hints(FillReport)["waiting"] == (int | None)


def test_fill_codes_are_the_designs_seventeen_in_order() -> None:
    assert [(m.name, m.value) for m in FillCode] == [
        ("FILLED", "filled"),
        ("WOULD_FILL", "would_fill"),
        ("UNCHANGED", "unchanged"),
        ("VALUE_MISSING", "value_missing"),
        ("TITLE_EMPTY", "title_empty"),
        ("UNSAFE_TEXT", "unsafe_text"),
        ("NO_START_TIME", "no_start_time"),
        ("INDEX_BEHIND", "index_behind"),
        ("SHAPE_INVALID", "shape_invalid"),
        ("VALUE_REFUSED", "value_refused"),
        ("STATEMENT_FAILED", "statement_failed"),
        ("TIMED_OUT", "timed_out"),
        ("NOT_ATTEMPTED", "not_attempted"),
        ("PAGE_NOT_CURRENT", "page_not_current"),
        ("PAGE_CHANGED", "page_changed"),
        ("WRITE_FAILED", "write_failed"),
        ("ATHLETES_TEXT", "athletes_text"),
    ]


def test_region_states_are_the_designs_three_in_order() -> None:
    assert [(m.name, m.value) for m in RegionState] == [
        ("WAITING", "waiting"),
        ("FILLED", "filled"),
        ("ATHLETES", "athletes"),
    ]


def test_every_dataclass_is_frozen() -> None:
    values = [
        (Binding(datetime(2026, 1, 1), None), "page_key"),
        (VariableOutcome("n", None, None, None), "name"),
        (_row("a.md", FillCode.FILLED), "page"),
        (Unavailable("r", "s"), "reason"),
        (TemplateSummary("p", date(2026, 1, 1), "d"), "path"),
        (_report(), "writing"),
    ]
    for value, field in values:
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, "x")
