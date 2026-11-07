"""Rendering of the pass, check and refill reports (post-templates task 3.4;
Req 7.4, 7.5, 7.6, 11.2, and what 9.2 to 9.6, 10.5 to 10.8 need shown)."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from fitdocs.post_template.model import (
    FillCode,
    FillReport,
    PageResult,
    RegionState,
    TemplateSummary,
    Unavailable,
    VariableOutcome,
)
from fitdocs.post_template.report import (
    NEXT_STEPS,
    render_json,
    render_pass_text,
    render_text,
)
from fitdocs.publish.request import Post
from tests.post_template.test_check_refill import _check, _refill
from tests.post_template.test_pass import (
    Opener,
    PassResolver,
    World,
    _key,
    _run,
    _steady,
    _template,
)

# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _row(
    page: str,
    code: FillCode,
    *,
    variable: str | None = None,
    landed: bool | None = False,
    changed: bool | None = None,
    state: RegionState | None = RegionState.WAITING,
    detail: str | None = None,
    post: Post | None = None,
) -> PageResult:
    variables = (
        ()
        if variable is None
        else (VariableOutcome(variable, None, code, "the reason"),)
    )
    return PageResult(
        page=page,
        state=state,
        in_window=True,
        landed=landed,
        code=code,
        detail=detail,
        variables=variables,
        post=post,
        changed=changed,
    )


def _pass(
    *rows: PageResult,
    waiting: int | None = 0,
    problems: tuple[str, ...] = (),
    unavailable: Unavailable | None = None,
    stopped: FillCode | None = None,
    stopped_variable: str | None = None,
) -> FillReport:
    return FillReport(
        command="pass",
        writing=True,
        template=TemplateSummary("post-template.toml", date(2026, 1, 2), "ab" * 32),
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


def _lines(text: str) -> list[str]:
    return text.split("\n")


def _causes(text: str) -> list[str]:
    return [line for line in _lines(text) if line.startswith("  ")]


# --------------------------------------------------------------------------- #
# The pass
# --------------------------------------------------------------------------- #


class TestPassEmpty:
    def test_nothing_to_say_is_empty(self) -> None:
        assert render_pass_text(_pass(waiting=0)) == ""

    @pytest.mark.parametrize(
        "report",
        [
            _pass(_row("runs/a.md", FillCode.FILLED), waiting=0),
            _pass(problems=("post-template.toml: title: bad",), waiting=3),
            _pass(unavailable=Unavailable("the index is busy", "try again"), waiting=3),
        ],
        ids=["rows-only", "problems-only", "unavailable-only"],
    )
    def test_any_one_thing_to_say_is_not_empty(self, report: FillReport) -> None:
        assert render_pass_text(report) != ""


class TestPassFirstLine:
    def test_counts_come_from_filled_rows_and_the_waiting_field(self) -> None:
        report = _pass(
            _row("runs/a.md", FillCode.FILLED),
            _row("runs/b.md", FillCode.FILLED),
            _row("runs/c.md", FillCode.FILLED),
            _row("runs/d.md", FillCode.FILLED),
            _row("runs/e.md", FillCode.VALUE_MISSING, variable="v"),
            waiting=7,
        )
        assert (
            _lines(render_pass_text(report))[0] == "Post template: 4 filled, 7 waiting."
        )

    def test_zero_waiting_is_shown(self) -> None:
        report = _pass(_row("runs/a.md", FillCode.FILLED), waiting=0)
        assert render_pass_text(report) == "Post template: 1 filled, 0 waiting."

    def test_none_waiting_is_hidden(self) -> None:
        report = _pass(_row("runs/a.md", FillCode.FILLED), waiting=None)
        text = render_pass_text(report)
        assert text == "Post template: 1 filled."
        assert "None" not in text

    def test_timeout_note_names_the_variable(self) -> None:
        report = _pass(
            _row("runs/a.md", FillCode.FILLED),
            _row("runs/b.md", FillCode.TIMED_OUT, variable="weekly_km"),
            _row("runs/c.md", FillCode.NOT_ATTEMPTED),
            waiting=2,
            stopped=FillCode.TIMED_OUT,
            stopped_variable="weekly_km",
        )
        assert _lines(render_pass_text(report))[0] == (
            "Post template: 1 filled, 2 waiting; "
            "stopped after weekly_km took longer than 5 seconds."
        )

    def test_a_different_variable_name_is_named(self) -> None:
        report = _pass(
            _row("runs/b.md", FillCode.TIMED_OUT, variable="load_trend"),
            waiting=1,
            stopped=FillCode.TIMED_OUT,
            stopped_variable="load_trend",
        )
        first = _lines(render_pass_text(report))[0]
        assert "load_trend" in first
        assert "weekly_km" not in first

    def test_budget_note_has_no_variable(self) -> None:
        report = _pass(
            _row("runs/a.md", FillCode.FILLED),
            _row("runs/c.md", FillCode.NOT_ATTEMPTED),
            waiting=1,
            stopped=FillCode.NOT_ATTEMPTED,
        )
        assert _lines(render_pass_text(report))[0] == (
            "Post template: 1 filled, 1 waiting; stopped after 30 seconds."
        )

    def test_stop_rows_are_not_cause_lines(self) -> None:
        report = _pass(
            _row("runs/b.md", FillCode.TIMED_OUT, variable="weekly_km"),
            _row("runs/c.md", FillCode.NOT_ATTEMPTED),
            waiting=2,
            stopped=FillCode.TIMED_OUT,
            stopped_variable="weekly_km",
        )
        assert _causes(render_pass_text(report)) == []

    def test_unavailable_replaces_the_counts_line(self) -> None:
        report = _pass(
            waiting=4, unavailable=Unavailable("the index is busy", "run fitdocs index")
        )
        assert render_pass_text(report) == (
            "Post template: 4 waiting; the index is busy. run fitdocs index."
        )

    def test_unavailable_with_unknown_waiting_hides_it(self) -> None:
        report = _pass(
            waiting=None,
            unavailable=Unavailable("the index is busy", "run fitdocs index"),
        )
        text = render_pass_text(report)
        assert text == "Post template: the index is busy. run fitdocs index."

    def test_a_problem_names_the_check_command(self) -> None:
        report = _pass(problems=("post-template.toml: title: bad",), waiting=3)
        lines = _lines(render_pass_text(report))
        assert lines[0] == "Post template: 0 filled, 3 waiting."
        assert lines[-1] == (
            "The post template has a problem; "
            "run fitdocs post-template check to see it."
        )

    def test_no_problem_no_check_line(self) -> None:
        report = _pass(_row("runs/a.md", FillCode.FILLED), waiting=0)
        assert "post-template check" not in render_pass_text(report)


# Distinct counts, assigned so that count order differs from FillCode order:
# FillCode order is value_missing, title_empty, unsafe_text, ... shape_invalid,
# value_refused, ... write_failed.
_SIX_CAUSES: list[tuple[FillCode, int]] = [
    (FillCode.VALUE_MISSING, 1),
    (FillCode.TITLE_EMPTY, 2),
    (FillCode.UNSAFE_TEXT, 3),
    (FillCode.SHAPE_INVALID, 4),
    (FillCode.VALUE_REFUSED, 5),
    (FillCode.WRITE_FAILED, 6),
]


def _six_cause_report() -> FillReport:
    rows: list[PageResult] = []
    for code, count in _SIX_CAUSES:
        for number in range(count):
            rows.append(_row(f"runs/{code.value}-{number}.md", code))
    return _pass(*rows, waiting=sum(count for _, count in _SIX_CAUSES))


class TestPassCauses:
    def test_five_lines_kept_by_count_and_the_sixth_dropped(self) -> None:
        causes = _causes(render_pass_text(_six_cause_report()))
        assert len(causes) == 5
        # the five largest groups, largest first; value_missing is dropped
        kept = [
            line.split()[1].rstrip(",")
            for line in causes  # "<count> <code> ..."
        ]
        assert kept == [
            "write_failed",
            "value_refused",
            "shape_invalid",
            "unsafe_text",
            "title_empty",
        ]
        assert all("value_missing" not in line for line in causes)

    def test_each_line_carries_its_count(self) -> None:
        causes = _causes(render_pass_text(_six_cause_report()))
        assert [line.split()[0] for line in causes] == ["6", "5", "4", "3", "2"]

    def test_five_groups_are_all_shown(self) -> None:
        report = _pass(
            *[_row(f"runs/{c.value}.md", c) for c, _ in _SIX_CAUSES[:5]], waiting=5
        )
        assert len(_causes(render_pass_text(report))) == 5

    def test_equal_counts_order_by_code_then_variable(self) -> None:
        report = _pass(
            _row("runs/w.md", FillCode.WRITE_FAILED),
            _row("runs/v-b.md", FillCode.VALUE_REFUSED, variable="b_var"),
            _row("runs/v-a.md", FillCode.VALUE_REFUSED, variable="a_var"),
            _row("runs/t.md", FillCode.TITLE_EMPTY),
            waiting=4,
        )
        subjects = [
            " ".join(line.split()[1:4]) for line in _causes(render_pass_text(report))
        ]
        assert subjects[0].startswith("title_empty")
        assert subjects[1].startswith("value_refused for a_var")
        assert subjects[2].startswith("value_refused for b_var")
        assert subjects[3].startswith("write_failed")

    def test_value_missing_is_grouped_by_the_placeholder_in_the_row_detail(
        self,
    ) -> None:
        # the shape the engine gives: no variable outcome carries the code, and
        # the row's detail is the placeholder that had no value
        report = _pass(
            _row("runs/a.md", FillCode.VALUE_MISSING, detail="alpha"),
            _row("runs/b.md", FillCode.VALUE_MISSING, detail="alpha"),
            _row("runs/c.md", FillCode.VALUE_MISSING, detail="alpha"),
            _row("runs/d.md", FillCode.VALUE_MISSING, detail="beta"),
            waiting=4,
        )
        causes = _causes(render_pass_text(report))
        assert len(causes) == 2
        assert causes[0].startswith(
            "  3 value_missing for alpha, for example runs/a.md"
        )
        assert causes[1].startswith("  1 value_missing for beta, for example runs/d.md")

    def test_value_missing_without_a_detail_names_nothing(self) -> None:
        (line,) = _causes(
            render_pass_text(
                _pass(_row("runs/a.md", FillCode.VALUE_MISSING), waiting=1)
            )
        )
        assert line.startswith("  1 value_missing, for example runs/a.md:")

    def test_equal_counts_put_value_missing_before_title_empty(self) -> None:
        # code order, not alphabetical order of the code strings
        report = _pass(
            _row("runs/t.md", FillCode.TITLE_EMPTY),
            _row("runs/m.md", FillCode.VALUE_MISSING, detail="x"),
            waiting=2,
        )
        subjects = [line.split()[1] for line in _causes(render_pass_text(report))]
        assert subjects == ["value_missing", "title_empty,"]

    def test_a_timeout_with_no_variable_named_says_a_statement(self) -> None:
        report = _pass(
            _row("runs/a.md", FillCode.NOT_ATTEMPTED),
            waiting=1,
            stopped=FillCode.TIMED_OUT,
            stopped_variable=None,
        )
        assert _lines(render_pass_text(report))[0] == (
            "Post template: 0 filled, 1 waiting; "
            "stopped after a statement took longer than 5 seconds."
        )

    def test_the_variable_named_is_the_one_carrying_the_rows_code(self) -> None:
        row = replace(
            _row("runs/a.md", FillCode.VALUE_REFUSED),
            variables=(
                VariableOutcome("resolved_var", "5", None, None),
                VariableOutcome("missing_var", None, FillCode.VALUE_MISSING, "x"),
                VariableOutcome("refused_var", None, FillCode.VALUE_REFUSED, "y"),
            ),
        )
        (line,) = _causes(render_pass_text(_pass(row, waiting=1)))
        assert line.startswith("  1 value_refused for refused_var,")

    def test_example_is_the_first_page_in_row_order(self) -> None:
        report = _pass(
            _row("runs/zeta.md", FillCode.TITLE_EMPTY),
            _row("runs/alpha.md", FillCode.TITLE_EMPTY),
            _row("runs/mid.md", FillCode.TITLE_EMPTY),
            waiting=3,
        )
        (line,) = _causes(render_pass_text(report))
        assert "for example runs/zeta.md:" in line
        assert "runs/alpha.md" not in line

    def test_each_group_has_its_own_example(self) -> None:
        report = _pass(
            _row("runs/t1.md", FillCode.TITLE_EMPTY),
            _row("runs/u1.md", FillCode.UNSAFE_TEXT),
            _row("runs/t2.md", FillCode.TITLE_EMPTY),
            _row("runs/u2.md", FillCode.UNSAFE_TEXT),
            waiting=4,
        )
        by_code = {
            line.split()[1].rstrip(","): line
            for line in _causes(render_pass_text(report))
        }
        assert "runs/t1.md" in by_code["title_empty"]
        assert "runs/u1.md" in by_code["unsafe_text"]

    def test_filled_rows_are_not_causes(self) -> None:
        report = _pass(
            _row("runs/a.md", FillCode.FILLED),
            _row("runs/b.md", FillCode.FILLED),
            waiting=0,
        )
        assert _causes(render_pass_text(report)) == []

    def test_a_cause_without_a_variable_reads_cleanly(self) -> None:
        report = _pass(_row("runs/a.md", FillCode.NO_START_TIME), waiting=1)
        (line,) = _causes(render_pass_text(report))
        assert line.startswith("  1 no_start_time, for example runs/a.md:")


# Pinned by hand, not read back from NEXT_STEPS, so a swapped entry is red.
_EXPECTED_STEPS: dict[FillCode, str] = {
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
    FillCode.SHAPE_INVALID: "fix the SQL so it returns one column and at most one row",
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


class TestNextSteps:
    def test_the_table_has_exactly_the_pinned_codes(self) -> None:
        assert dict(NEXT_STEPS) == _EXPECTED_STEPS

    def test_the_steps_are_pairwise_distinct(self) -> None:
        assert len(set(_EXPECTED_STEPS.values())) == len(_EXPECTED_STEPS)

    @pytest.mark.parametrize("code", sorted(_EXPECTED_STEPS, key=lambda c: c.value))
    def test_a_cause_line_ends_with_its_codes_step(self, code: FillCode) -> None:
        report = _pass(_row("runs/a.md", code), waiting=1)
        (line,) = _causes(render_pass_text(report))
        assert line.endswith(": " + _EXPECTED_STEPS[code])

    @pytest.mark.parametrize(
        "code",
        [
            c
            for c in FillCode
            if c not in _EXPECTED_STEPS
            and c not in (FillCode.TIMED_OUT, FillCode.NOT_ATTEMPTED, FillCode.FILLED)
        ],
    )
    def test_codes_with_no_step_are_not_cause_lines(self, code: FillCode) -> None:
        report = _pass(_row("runs/a.md", code), waiting=1)
        assert _causes(render_pass_text(report)) == []


# --------------------------------------------------------------------------- #
# Check and refill
# --------------------------------------------------------------------------- #


def _full_report(command: str = "check") -> FillReport:
    """Every field non-default and pairwise distinct."""
    filled_landed = _row(
        "runs/2026-03-01-landed-filled.md",
        FillCode.FILLED,
        landed=True,
        changed=True,
        state=RegionState.FILLED,
        detail="wrote it",
        post=Post("Title A 111", "line one 112\nline two 113"),
    )
    would_landed = _row(
        "runs/2026-03-02-landed-would.md",
        FillCode.WOULD_FILL,
        landed=True,
        changed=True,
        state=RegionState.WAITING,
        post=Post("Title B 121", ""),
    )
    unchanged_landed = _row(
        "runs/2026-03-03-landed-same.md",
        FillCode.UNCHANGED,
        landed=True,
        changed=False,
        state=RegionState.FILLED,
        post=Post("Title C 131", "same 132"),
    )
    would_unlanded = _row(
        "runs/2026-03-04-unlanded-would.md",
        FillCode.WOULD_FILL,
        landed=False,
        changed=True,
        post=Post("Title D 141", "desc 142"),
    )
    missing = PageResult(
        page="runs/2026-03-05-missing.md",
        state=RegionState.WAITING,
        in_window=False,
        landed=None,
        code=FillCode.VALUE_MISSING,
        detail="no row for share 151",
        variables=(
            VariableOutcome("share_var", "  padded 152 ", None, None),
            VariableOutcome("gone_var", None, FillCode.VALUE_MISSING, "no rows 153"),
            VariableOutcome("absent_var", None, None, None),
        ),
        post=None,
        changed=None,
    )
    athletes = _row(
        "runs/2026-03-06-athletes.md",
        FillCode.ATHLETES_TEXT,
        state=RegionState.ATHLETES,
        landed=False,
        changed=None,
    )
    unclassified = PageResult(
        page="runs/2026-03-07-unclassified.md",
        state=None,
        in_window=True,
        landed=False,
        code=FillCode.PAGE_NOT_CURRENT,
        detail="older format 161",
        variables=(),
        post=None,
        changed=None,
    )
    return FillReport(
        command=command,  # type: ignore[arg-type]
        writing=True,
        template=TemplateSummary("post-template-x.toml", date(2026, 2, 3), "cd" * 32),
        template_problems=("post-template-x.toml: title: problem 171",),
        waiting=181,
        unavailable=Unavailable("Index is busy 191", "wait and retry 192"),
        rows=(
            filled_landed,
            would_landed,
            unchanged_landed,
            would_unlanded,
            missing,
            athletes,
            unclassified,
        ),
        athletes_left_out=201,
        published_left_out=202,
        older_template=211,
        stopped=FillCode.TIMED_OUT,
        stopped_variable="slow_var",
    )


class TestJsonHoldsWhatTextShows:
    def test_top_level_key_set_is_fixed(self) -> None:
        data = json.loads(render_json(_full_report()))
        assert set(data) == {
            "command",
            "writing",
            "template",
            "problems",
            "unavailable",
            "pages",
            "counts",
            "waiting",
            "athletes_left_out",
            "published_left_out",
            "older_template",
            "stopped",
            "stopped_variable",
            "wrote",
            "landed_changed",
        }

    def test_nested_key_sets_are_fixed(self) -> None:
        data = json.loads(render_json(_full_report()))
        assert set(data["template"]) == {"path", "since", "digest"}
        assert set(data["unavailable"]) == {"reason", "next_step"}
        for page in data["pages"]:
            assert set(page) == {
                "page",
                "state",
                "in_window",
                "landed",
                "code",
                "detail",
                "variables",
                "post",
                "changed",
            }
            for variable in page["variables"]:
                assert set(variable) == {"name", "value", "code", "detail"}
        assert set(data["pages"][0]["post"]) == {"title", "description"}

    def test_header_values_are_at_their_keys(self) -> None:
        report = _full_report()
        data = json.loads(render_json(report))
        assert data["command"] == "check"
        assert data["writing"] is True
        assert data["template"] == {
            "path": "post-template-x.toml",
            "since": "2026-02-03",
            "digest": "cd" * 32,
        }
        assert data["problems"] == ["post-template-x.toml: title: problem 171"]
        assert data["unavailable"] == {
            "reason": "Index is busy 191",
            "next_step": "wait and retry 192",
        }
        assert data["waiting"] == 181
        assert data["athletes_left_out"] == 201
        assert data["published_left_out"] == 202
        assert data["older_template"] == 211
        assert data["stopped"] == "timed_out"
        assert data["stopped_variable"] == "slow_var"
        assert data["counts"] == {
            "filled": 1,
            "would_fill": 2,
            "unchanged": 1,
            "value_missing": 1,
            "page_not_current": 1,
            "athletes_text": 1,
        }
        assert list(data["counts"]) == [
            "filled",
            "would_fill",
            "unchanged",
            "value_missing",
            "page_not_current",
            "athletes_text",
        ]
        assert data["wrote"] == ["runs/2026-03-01-landed-filled.md"]
        assert data["landed_changed"] == [
            "runs/2026-03-01-landed-filled.md",
            "runs/2026-03-02-landed-would.md",
        ]

    def test_rows_hold_every_field_in_order(self) -> None:
        data = json.loads(render_json(_full_report()))
        pages = data["pages"]
        assert [p["page"] for p in pages] == [
            "runs/2026-03-01-landed-filled.md",
            "runs/2026-03-02-landed-would.md",
            "runs/2026-03-03-landed-same.md",
            "runs/2026-03-04-unlanded-would.md",
            "runs/2026-03-05-missing.md",
            "runs/2026-03-06-athletes.md",
            "runs/2026-03-07-unclassified.md",
        ]
        assert pages[0] == {
            "page": "runs/2026-03-01-landed-filled.md",
            "state": "filled",
            "in_window": True,
            "landed": True,
            "code": "filled",
            "detail": "wrote it",
            "variables": [],
            "post": {
                "title": "Title A 111",
                "description": "line one 112\nline two 113",
            },
            "changed": True,
        }
        assert pages[1]["post"] == {"title": "Title B 121", "description": ""}
        assert pages[2]["changed"] is False
        assert pages[2]["landed"] is True
        missing = pages[4]
        assert missing["in_window"] is False
        assert missing["landed"] is None
        assert missing["changed"] is None
        assert missing["post"] is None
        assert missing["code"] == "value_missing"
        assert missing["variables"] == [
            {
                "name": "share_var",
                "value": "  padded 152 ",
                "code": None,
                "detail": None,
            },
            {
                "name": "gone_var",
                "value": None,
                "code": "value_missing",
                "detail": "no rows 153",
            },
            {"name": "absent_var", "value": None, "code": None, "detail": None},
        ]
        assert pages[6]["state"] is None
        assert pages[5]["state"] == "athletes"

    def test_every_value_the_text_prints_is_in_the_json_at_its_key(self) -> None:
        report = _full_report()
        text = render_text(report)
        data = json.loads(render_json(report))
        # (printed token, the value the JSON holds for it)
        printed = [
            ("post-template-x.toml", data["template"]["path"]),
            ("2026-02-03", data["template"]["since"]),
            ("cd" * 32, data["template"]["digest"]),
            ("post-template-x.toml: title: problem 171", data["problems"][0]),
            ("Index is busy 191", data["unavailable"]["reason"]),
            ("wait and retry 192", data["unavailable"]["next_step"]),
            ("slow_var", data["stopped_variable"]),
            ("runs/2026-03-01-landed-filled.md", data["pages"][0]["page"]),
            ("wrote it", data["pages"][0]["detail"]),
            ("Title A 111", data["pages"][0]["post"]["title"]),
            ("line one 112", data["pages"][0]["post"]["description"].split("\n")[0]),
            ("line two 113", data["pages"][0]["post"]["description"].split("\n")[1]),
            ("Title B 121", data["pages"][1]["post"]["title"]),
            ("Title C 131", data["pages"][2]["post"]["title"]),
            ("same 132", data["pages"][2]["post"]["description"]),
            ("Title D 141", data["pages"][3]["post"]["title"]),
            ("desc 142", data["pages"][3]["post"]["description"]),
            ("no row for share 151", data["pages"][4]["detail"]),
            ("share_var", data["pages"][4]["variables"][0]["name"]),
            ("  padded 152 ", data["pages"][4]["variables"][0]["value"]),
            ("gone_var", data["pages"][4]["variables"][1]["name"]),
            ("no rows 153", data["pages"][4]["variables"][1]["detail"]),
            ("absent_var", data["pages"][4]["variables"][2]["name"]),
            ("older format 161", data["pages"][6]["detail"]),
            ("181", str(data["waiting"])),
            ("201", str(data["athletes_left_out"])),
            ("202", str(data["published_left_out"])),
            ("211", str(data["older_template"])),
        ]
        for token, held in printed:
            assert token in text, token
            assert held == token, token

    def test_the_states_codes_and_flags_the_text_prints_match_the_json(self) -> None:
        report = _full_report()
        text = render_text(report)
        data = json.loads(render_json(report))
        for page in data["pages"]:
            block = text.split(page["page"] + "\n", 1)[1].split("\n  result:", 1)
            head, rest = block[0], block[1].split("\n", 1)[0]
            assert f"state: {page['state'] or 'unclassified'}" in head
            assert f"in window: {'yes' if page['in_window'] else 'no'}" in head
            assert rest.strip() == page["code"]
            if page["landed"] is None:
                assert "landed post" not in head
            else:
                assert f"landed post: {'yes' if page['landed'] else 'no'}" in head
        for code, n in data["counts"].items():
            assert f"{code} {n}" in text

    def test_refill_json_names_its_command_and_has_the_same_keys(self) -> None:
        check = json.loads(render_json(_full_report("check")))
        refill = json.loads(render_json(_full_report("refill")))
        assert refill["command"] == "refill"
        assert set(refill) == set(check)

    def test_json_is_valid_with_non_ascii_text_verbatim(self) -> None:
        report = replace(
            _full_report(),
            rows=(
                _row("runs/ü.md", FillCode.WOULD_FILL, post=Post("Zürich 10 km", "é")),
            ),
        )
        raw = render_json(report)
        assert "Zürich 10 km" in raw
        assert json.loads(raw)["pages"][0]["page"] == "runs/ü.md"


class TestTextHidesNoneAndShowsReal:
    def _none_report(self) -> FillReport:
        row = PageResult(
            page="runs/a.md",
            state=RegionState.WAITING,
            in_window=True,
            landed=None,
            code=FillCode.NOT_ATTEMPTED,
            detail="the index is busy",
            variables=(),
            post=None,
            changed=None,
        )
        return FillReport(
            command="check",
            writing=False,
            template=TemplateSummary("post-template.toml", date(2026, 2, 3), "ef" * 32),
            template_problems=(),
            waiting=None,
            unavailable=None,
            rows=(row,),
            athletes_left_out=0,
            published_left_out=0,
            older_template=None,
            stopped=None,
            stopped_variable=None,
        )

    def test_none_counts_and_flags_are_not_printed(self) -> None:
        text = render_text(self._none_report())
        assert "None" not in text
        assert "Eligible" not in text
        assert "earlier template" not in text
        assert "landed" not in text
        assert "text changes" not in text

    def test_json_carries_them_as_null(self) -> None:
        data = json.loads(render_json(self._none_report()))
        assert data["waiting"] is None
        assert data["older_template"] is None
        assert data["pages"][0]["landed"] is None
        assert data["pages"][0]["changed"] is None

    def test_zero_counts_are_shown_when_real(self) -> None:
        report = replace(self._none_report(), waiting=0, older_template=0)
        text = render_text(report)
        assert "Eligible pages: 0" in _lines(text)
        assert "Filled from an earlier template: 0" in _lines(text)

    def test_false_flags_are_shown_when_real(self) -> None:
        row = replace(self._none_report().rows[0], landed=False, changed=False)
        text = render_text(replace(self._none_report(), rows=(row,)))
        assert "  landed post: no" in _lines(text)
        assert "  text changes: no" in _lines(text)

    def test_true_flags_are_shown(self) -> None:
        row = replace(self._none_report().rows[0], landed=True, changed=True)
        text = render_text(replace(self._none_report(), rows=(row,)))
        assert "  landed post: yes" in _lines(text)
        assert "  text changes: yes" in _lines(text)

    def test_a_refused_template_is_said_and_the_problems_listed(self) -> None:
        report = replace(
            self._none_report(),
            template=None,
            template_problems=("p.toml: a: one", "p.toml: b: two"),
            rows=(),
        )
        lines = _lines(render_text(report))
        assert lines[0] == "Template: not accepted"
        assert lines[1:3] == ["Problem: p.toml: a: one", "Problem: p.toml: b: two"]

    def test_the_accepted_template_line(self) -> None:
        assert _lines(render_text(self._none_report()))[0] == (
            "Template: post-template.toml (since 2026-02-03, digest " + "ef" * 32 + ")"
        )

    def test_earlier_template_count_is_a_check_figure_only(self) -> None:
        refill = replace(self._none_report(), command="refill", older_template=4)
        assert "earlier template" not in render_text(refill)

    def test_eligible_is_a_check_figure_only(self) -> None:
        refill = replace(self._none_report(), command="refill", waiting=0)
        assert "Eligible" not in render_text(refill)


class TestCheckAndRefillSections:
    def test_unavailable_is_printed_as_written_and_capitalized(self) -> None:
        report = replace(
            _full_report("check"),
            unavailable=Unavailable("the SQL was not checked: index busy", "retry"),
        )
        assert "The SQL was not checked: index busy. retry." in _lines(
            render_text(report)
        )
        assert render_text(report).count("not checked") == 1

    def test_refill_prints_unavailable_the_same_way(self) -> None:
        text = render_text(_full_report("refill"))
        assert "Index is busy 191. wait and retry 192." in _lines(text)

    def test_no_unavailable_line_when_available(self) -> None:
        text = render_text(replace(_full_report(), unavailable=None))
        assert "busy" not in text

    def test_variable_lines(self) -> None:
        text = render_text(_full_report())
        assert "  variable share_var:   padded 152 " in text
        assert "  variable gone_var: value_missing: no rows 153" in text
        assert "  variable absent_var: no value" in text

    def test_variable_failure_without_detail(self) -> None:
        outcome = VariableOutcome("v", None, FillCode.TIMED_OUT, None)
        row = replace(_row("runs/a.md", FillCode.TIMED_OUT), variables=(outcome,))
        text = render_text(replace(_full_report(), rows=(row,)))
        assert "  variable v: timed_out\n" in text + "\n"

    def test_composed_post_with_description_lines(self) -> None:
        text = render_text(_full_report())
        assert "  post title: Title A 111" in text
        assert "  post description:\n    line one 112\n    line two 113" in text

    def test_blank_description_lines_carry_no_trailing_space(self) -> None:
        row = _row("runs/a.md", FillCode.WOULD_FILL, post=Post("t", "one\n\ntwo"))
        text = render_text(replace(_full_report(), rows=(row,)))
        assert "    one\n\n    two" in text
        assert not any(line != line.rstrip() for line in _lines(text))

    def test_empty_description_is_said(self) -> None:
        assert "  post title: Title B 121\n  post description: empty" in render_text(
            _full_report()
        )

    def test_no_post_prints_no_post_lines_for_that_page(self) -> None:
        text = render_text(_full_report())
        block = text.split("runs/2026-03-05-missing.md\n", 1)[1].split("runs/2026", 1)[
            0
        ]
        assert "post title" not in block
        assert "post description" not in block

    def test_stop_note_names_the_variable(self) -> None:
        assert (
            "Stopped: slow_var timed out; the pages after it were not attempted."
            in render_text(_full_report())
        )

    def test_stop_note_other_variable_and_budget(self) -> None:
        other = replace(_full_report(), stopped_variable="other_var")
        assert "Stopped: other_var timed out;" in render_text(other)
        budget = replace(
            _full_report(), stopped=FillCode.NOT_ATTEMPTED, stopped_variable=None
        )
        assert "Stopped: the time budget ran out;" in render_text(budget)
        assert "timed out" not in render_text(budget)

    def test_a_check_timeout_with_no_variable_says_a_statement(self) -> None:
        text = render_text(replace(_full_report(), stopped_variable=None))
        assert "Stopped: a statement timed out;" in text
        assert "None" not in text

    def test_no_stop_no_note(self) -> None:
        text = render_text(replace(_full_report(), stopped=None, stopped_variable=None))
        assert "Stopped" not in text

    def test_left_out_counts_with_the_naming_note_on_the_last_line(self) -> None:
        lines = _lines(render_text(_full_report("refill")))
        assert "201 Athlete's pages left out." in lines
        assert "202 published pages left out; name a page to refill it." in lines
        assert lines.count("name a page to refill it") == 0
        assert sum("name a page to refill it" in line for line in lines) == 1

    def test_only_published_left_out(self) -> None:
        text = render_text(replace(_full_report(), athletes_left_out=0))
        assert "Athlete's" not in text
        assert "202 published pages left out; name a page to refill it." in text

    def test_only_athletes_left_out(self) -> None:
        text = render_text(replace(_full_report(), published_left_out=0))
        assert "201 Athlete's pages left out." in _lines(text)
        assert "published pages left out" not in text
        assert not any("name a page" in line for line in _lines(text))

    def test_a_cause_with_prose_detail_names_no_placeholder(self) -> None:
        rows = [
            _row("runs/a.md", FillCode.NO_START_TIME, detail="the page has no start"),
            _row("runs/b.md", FillCode.INDEX_BEHIND, detail="index copy differs"),
        ]
        causes = _causes(render_pass_text(_pass(*rows, waiting=2)))
        assert [c.split(":")[0] for c in causes] == [
            "  1 no_start_time, for example runs/a.md",
            "  1 index_behind, for example runs/b.md",
        ]

    def test_a_single_left_out_page_of_each_kind_is_singular(self) -> None:
        text = render_text(
            replace(_full_report(), athletes_left_out=1, published_left_out=1)
        )
        assert "1 Athlete's page left out." in _lines(text)
        assert "1 published page left out; name a page to refill it." in _lines(text)

    def test_nothing_left_out_prints_nothing_about_it(self) -> None:
        text = render_text(
            replace(_full_report(), athletes_left_out=0, published_left_out=0)
        )
        assert "left out" not in text
        assert "name a page" not in text

    def test_landed_changed_names_only_filled_or_would_fill_with_a_landed_post(
        self,
    ) -> None:
        text = render_text(_full_report())
        (notice,) = [line for line in _lines(text) if "fitdocs publish --yes" in line]
        assert "runs/2026-03-01-landed-filled.md" in notice
        assert "runs/2026-03-02-landed-would.md" in notice
        assert "landed-same" not in notice  # unchanged, though landed
        assert "unlanded-would" not in notice  # would fill, not landed
        assert "update the posted activity" in notice

    def test_no_landed_change_no_notice(self) -> None:
        row = _row("runs/a.md", FillCode.WOULD_FILL, landed=False, post=Post("t", ""))
        text = render_text(replace(_full_report(), rows=(row,)))
        assert "fitdocs publish --yes" not in text

    def test_wrote_line_only_when_writing(self) -> None:
        report = _full_report()
        assert "Wrote 1 page: runs/2026-03-01-landed-filled.md" in render_text(report)
        assert "Wrote" not in render_text(replace(report, writing=False))

    def test_wrote_line_lists_every_written_page(self) -> None:
        extra = _row("runs/zz-second.md", FillCode.FILLED, changed=True)
        report = _full_report()
        report = replace(report, rows=(*report.rows, extra))
        assert (
            "Wrote 2 pages: runs/2026-03-01-landed-filled.md, runs/zz-second.md"
            in render_text(report)
        )

    def test_writing_run_that_wrote_nothing_has_no_wrote_line(self) -> None:
        row = _row("runs/a.md", FillCode.VALUE_MISSING)
        assert "Wrote" not in render_text(replace(_full_report(), rows=(row,)))

    def test_a_row_without_detail_prints_no_detail_line(self) -> None:
        row = _row("runs/a.md", FillCode.WOULD_FILL, detail=None)
        text = render_text(replace(_full_report(), rows=(row,)))
        assert "detail" not in text
        assert "None" not in text

    def test_counts_line(self) -> None:
        assert (
            "Pages: filled 1, would_fill 2, unchanged 1, value_missing 1, "
            "page_not_current 1, athletes_text 1"
        ) in render_text(_full_report())

    def test_no_rows_no_counts_line(self) -> None:
        assert "Pages:" not in render_text(replace(_full_report(), rows=()))


# --------------------------------------------------------------------------- #
# Reports from the real engine
# --------------------------------------------------------------------------- #


@pytest.fixture
def world(per_test_directory: Callable[[str], Path]) -> World:
    root = per_test_directory("report")
    (root / "workouts").mkdir()
    return World(root)


def _absent(name: str, variable: str) -> tuple[tuple[str, str], VariableOutcome]:
    return (_key(name), variable), VariableOutcome(variable, None, None, None)


class TestRealEngineReports:
    def test_a_real_pass_names_each_placeholder_that_had_no_value(
        self, world: World
    ) -> None:
        template = _template(world)
        for name in ("a", "b", "c", "d"):
            world.page(name)
        resolver = PassResolver(
            outcomes=dict(
                [_absent("a", "mike"), _absent("b", "mike"), _absent("c", "alpha")]
            )
        )
        report = _run(world, template, Opener(resolver), _steady())
        assert [
            row.detail for row in report.rows if row.code is FillCode.VALUE_MISSING
        ] == [
            "mike",
            "mike",
            "alpha",
        ]
        lines = _lines(render_pass_text(report))
        assert lines[0] == "Post template: 1 filled, 3 waiting."
        assert lines[1].startswith(
            "  2 value_missing for mike, for example workouts/a.md:"
        )
        assert lines[2].startswith(
            "  1 value_missing for alpha, for example workouts/c.md:"
        )
        assert len(lines) == 3

    def test_a_real_check_with_the_index_unavailable_says_not_checked_once(
        self, world: World
    ) -> None:
        template = _template(world)
        world.page("a")
        gone = Unavailable("the index is not built", "run fitdocs index")
        report = _check(world, template, gone)
        text = render_text(report)
        assert (
            "The SQL was not checked: the index is not built. run fitdocs index."
            in _lines(text)
        )
        assert text.count("not checked") == 1
        assert json.loads(render_json(report))["unavailable"]["reason"] == (
            "the SQL was not checked: the index is not built"
        )

    def test_a_real_refill_does_not_print_an_earlier_template_count(
        self, world: World
    ) -> None:
        template = _template(world)
        world.page("a")
        report = _refill(world, template, PassResolver(), writing=False)
        assert report.older_template is None
        assert "earlier template" not in render_text(report)
        assert json.loads(render_json(report))["older_template"] is None

    def test_a_real_check_prints_the_earlier_template_count(self, world: World) -> None:
        template = _template(world)
        world.page("a")
        report = _check(world, template, PassResolver())
        assert "Filled from an earlier template: 0" in _lines(render_text(report))
