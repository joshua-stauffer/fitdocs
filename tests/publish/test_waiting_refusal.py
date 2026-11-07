"""The waiting refusal in the publish engine (post-templates task 4.2).

Requirements 5.10 and 12.1, 12.4-12.7, 12.9 and 12.10. Pages are real files in
a temporary data root; the scripted publishing connector records every send.
A Filled region is built with the region module's own renderer so the round
trip through the publish reader is the real one. Expected posts and rows are
literals; the publish engine imports nothing from the template package, but
these tests may.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from fitdocs.contract import POST_PLACEHOLDER
from fitdocs.docmerge import begin_marker, end_marker, region_block
from fitdocs.post_template.region import render_filled
from fitdocs.publish.engine import PublishPlan, PublishReport, ResultRow
from fitdocs.publish.ledger import PublishLedger, load_ledgers
from fitdocs.publish.outcomes import PublishCode
from fitdocs.publish.request import Post, PublishResult
from tests.publish.test_engine import (
    CONNECTOR,
    DEFAULT_POST,
    OTHER_POST,
    SHA_A,
    SHA_B,
    SHA_C,
    Env,
    _by_target,
    _codes,
    _digest,
    _fm,
    _record,
    _ref,
    _settings,
    _snapshot,
    replace_ledgers,
)

#: ``run_page`` dates its pages 2026-03-04.
PAGE_DAY = date(2026, 3, 4)
STAMP_DIGEST = "ab" * 32
AS_OF = datetime(2026, 11, 7, 6, 30)

FILLED_POST = Post("Easy 10 {km} run", "Load 24% of the week\nShare {x} of load")
REFILLED_POST = Post("Easy 10 {km} run", "Load 31% of the week")


@pytest.fixture
def env(tmp_path: Path) -> Env:
    root = tmp_path / "data"
    root.mkdir()
    return Env(root)


def _waiting_row(target: str, page: str = "workouts/a.md") -> ResultRow:
    return ResultRow(
        page=page,
        target=target,
        code=PublishCode.POST_WAITING,
        decision=None,
        post=None,
        link=None,
        link_refused=False,
        detail=None,
    )


def _plan(
    env: Env, *, since: date | None = PAGE_DAY, posting: bool = False, **options: object
) -> PublishPlan:
    plan = env.plan(posting=posting, **options)  # type: ignore[arg-type]
    return replace(plan, post_template_since=since)


def _filled(post: Post = FILLED_POST) -> str:
    return render_filled(post, template_digest=STAMP_DIGEST, as_of=AS_OF)


def _ledger_dir_untouched(env: Env) -> bool:
    return not (env.root / ".fitdocs").exists()


class TestThePlanField:
    def test_a_plan_has_no_template_since_unless_given_one(self, env: Env) -> None:
        env.write("a.md")
        assert env.plan().post_template_since is None
        assert _plan(env, since=PAGE_DAY).post_template_since == PAGE_DAY


class TestTheRefusal:
    @pytest.mark.parametrize("posting", [False, True])
    def test_an_eligible_page_is_refused_for_each_selected_target_and_nothing_is_sent(
        self, env: Env, posting: bool
    ) -> None:
        page = env.write("a.md", _fm(publish=["alpha", "beta"]), post="")
        before = _snapshot(env.root)
        report = env.run(_plan(env, posting=posting))
        assert report.rows == (_waiting_row("alpha"), _waiting_row("beta"))
        assert report.failed is True
        assert report.posting is posting
        assert env.spy.opened == []
        assert env.spy.publisher.publish_calls == []
        assert env.spy.mints == 0
        assert env.spy.clock_calls == 0
        assert _ledger_dir_untouched(env)
        assert _snapshot(env.root) == before
        assert page.exists()

    def test_only_the_selected_targets_are_refused(self, env: Env) -> None:
        env.write("a.md", _fm(publish=["alpha", "beta"]))
        report = env.run(_plan(env, considered=("beta",)))
        assert report.rows == (_waiting_row("beta"),)

    def test_each_page_is_refused_for_its_own_targets(self, env: Env) -> None:
        env.write("a.md", _fm(publish="alpha"))
        env.write("b.md", _fm(sources=[_ref(SHA_B)], publish="beta"))
        report = env.run(_plan(env))
        assert report.rows == (
            _waiting_row("alpha", "workouts/a.md"),
            _waiting_row("beta", "workouts/b.md"),
        )

    @pytest.mark.parametrize(
        "content",
        ["", "   \n\n  ", POST_PLACEHOLDER, "\n" + POST_PLACEHOLDER + "\n\n"],
    )
    def test_a_region_left_empty_or_with_the_placeholder_is_waiting(
        self, env: Env, content: str
    ) -> None:
        env.write("a.md", post=content)
        report = env.run(_plan(env))
        assert report.rows == (_waiting_row("alpha"),)

    def test_a_region_with_its_markers_adjacent_is_waiting(self, env: Env) -> None:
        body = f"# Run\n\n{begin_marker('post')}\n{end_marker('post')}\n"
        body += region_block("published", "")
        env.write("a.md", body=body)
        assert env.run(_plan(env)).rows == (_waiting_row("alpha"),)

    def test_a_region_the_athlete_emptied_after_a_fill_is_waiting_again(
        self, env: Env
    ) -> None:
        page = env.write("a.md", post=_filled())
        assert env.run(_plan(env)).rows[0].code is PublishCode.WOULD_POST
        emptied = page.read_text(encoding="utf-8").replace(_filled(), "")
        assert emptied != page.read_text(encoding="utf-8")
        page.write_text(emptied, encoding="utf-8")
        assert env.run(_plan(env)).rows == (_waiting_row("alpha"),)

    def test_the_window_includes_the_day_it_opens_and_excludes_the_day_before(
        self, env: Env
    ) -> None:
        env.write("a.md")
        on = env.run(_plan(env, since=PAGE_DAY))
        after = env.run(_plan(env, since=date(2026, 3, 3)))
        before = env.run(_plan(env, since=date(2026, 3, 5)))
        assert on.rows == (_waiting_row("alpha"),)
        assert after.rows == (_waiting_row("alpha"),)
        assert [r.code for r in before.rows] == [PublishCode.WOULD_POST]
        assert before.rows[0].post == DEFAULT_POST

    def test_a_page_with_no_date_is_outside_the_window(self, env: Env) -> None:
        env.write("a.md", _fm(date=None))
        (row,) = env.run(_plan(env, since=date(2000, 1, 1))).rows
        assert row.code is PublishCode.WOULD_POST


class TestNoRefusal:
    @pytest.mark.parametrize("posting", [False, True])
    def test_without_a_template_a_waiting_page_is_posted_with_the_target_template(
        self, env: Env, posting: bool
    ) -> None:
        env.write("a.md", _fm(publish=["alpha", "beta"]), post=POST_PLACEHOLDER)
        env.spy.publisher.publish_script.extend(
            [PublishResult(PublishCode.POSTED), PublishResult(PublishCode.POSTED)]
        )
        report = env.run(_plan(env, since=None, posting=posting))
        expected = PublishCode.POSTED if posting else PublishCode.WOULD_POST
        assert [(r.target, r.code) for r in report.rows] == [
            ("alpha", expected),
            ("beta", expected),
        ]
        assert [r.post for r in report.rows] == [DEFAULT_POST, DEFAULT_POST]
        assert len(env.spy.publisher.publish_calls) == (2 if posting else 0)

    def test_text_the_athlete_wrote_is_sent_not_refused(self, env: Env) -> None:
        env.write("a.md", post="My title\n\nMy words")
        (row,) = env.run(_plan(env)).rows
        assert row.code is PublishCode.WOULD_POST
        assert row.post == Post("My title", "My words")

    def test_text_the_athlete_added_under_a_stamp_is_theirs(self, env: Env) -> None:
        edited = _filled() + " edited"
        env.write("a.md", post=edited)
        (row,) = env.run(_plan(env)).rows
        assert row.code is PublishCode.WOULD_POST
        assert row.post == Post(
            "Easy 10 {km} run", "Load 24% of the week\nShare {x} of load edited"
        )

    def test_a_foreign_comment_in_the_region_is_not_waiting(self, env: Env) -> None:
        env.write("a.md", post="<!-- my own note -->")
        (row,) = env.run(_plan(env)).rows
        assert row.code is not PublishCode.POST_WAITING

    def test_a_landed_record_on_another_target_lifts_the_refusal_for_both(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(publish=["alpha", "beta"]))
        settings = _settings(
            ("alpha", "beta"),
            {"publish": {"targets": {"beta": {"title": "B: {title}"}}}},
        )
        records = {"alpha": [_record(SHA_A, digest=_digest(DEFAULT_POST), number=1)]}
        report = env.run(_plan(env, settings=settings, records=records))
        rows = _by_target(report)
        alpha = rows[("workouts/a.md", "alpha")]
        beta = rows[("workouts/a.md", "beta")]
        assert len(report.rows) == 2
        assert alpha.code is PublishCode.UNCHANGED
        assert (beta.code, beta.decision) == (
            PublishCode.WOULD_POST,
            PublishCode.WOULD_POST,
        )
        assert beta.post == Post("B: Morning Run", DEFAULT_POST.description)

    def test_a_landed_record_on_an_unselected_target_lifts_the_refusal(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(publish=["alpha", "beta"]))
        records = {"alpha": [_record(SHA_A, digest=_digest(DEFAULT_POST), number=1)]}
        report = env.run(_plan(env, considered=("beta",), records=records))
        assert [(r.target, r.code) for r in report.rows] == [
            ("beta", PublishCode.WOULD_POST)
        ]

    def test_a_landed_record_in_an_unconfigured_targets_ledger_lifts_the_refusal(
        self, env: Env
    ) -> None:
        env.write("a.md")
        plan = _plan(env)
        ledgers = dict(plan.ledgers)
        ledgers["gamma"] = PublishLedger(
            "gamma",
            CONNECTOR,
            (_record(SHA_A, digest=_digest(DEFAULT_POST), number=1),),
        )
        report = env.run(replace(plan, ledgers=ledgers))
        assert [(r.target, r.code) for r in report.rows] == [
            ("alpha", PublishCode.WOULD_POST)
        ]

    def test_a_landed_record_on_the_pairs_own_target_lifts_the_refusal(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(publish=["alpha", "beta"]))
        records = {"beta": [_record(SHA_A, digest=_digest(OTHER_POST), number=1)]}
        report = env.run(_plan(env, records=records))
        assert [(r.target, r.code) for r in report.rows] == [
            ("alpha", PublishCode.WOULD_POST),
            ("beta", PublishCode.WOULD_UPDATE),
        ]

    def test_a_landed_record_keyed_by_an_earlier_source_still_counts(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(sources=[_ref(SHA_B), _ref(SHA_A)], publish="alpha"))
        env.write(
            "b.md", _fm(sources=[_ref(SHA_C)], publish="alpha", date="2026-03-05")
        )
        records = {"alpha": [_record(SHA_B, digest=_digest(DEFAULT_POST), number=1)]}
        report = env.run(_plan(env, records=records))
        assert _codes(report) == [
            ("workouts/a.md", "alpha", PublishCode.UNCHANGED),
            ("workouts/b.md", "alpha", PublishCode.POST_WAITING),
        ]

    def test_a_record_that_never_landed_does_not_lift_the_refusal(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(publish=["alpha", "beta"]))
        records = {
            "alpha": [_record(SHA_A, digest=None, number=1, code="unknown_result")]
        }
        report = env.run(_plan(env, records=records))
        assert report.rows == (_waiting_row("alpha"), _waiting_row("beta"))

    def test_a_page_not_opted_in_to_a_selected_target_is_counted_as_today(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(publish=None))
        report = env.run(_plan(env))
        assert report.rows == ()
        assert report.not_opted_in == 1


class TestPrecedence:
    """Each fixture is Waiting, in the window and unlanded, so only order decides."""

    def test_an_out_of_date_page_keeps_its_own_refusal(self, env: Env) -> None:
        env.write("a.md", _fm(doc_version=11), post="")
        (row,) = env.run(_plan(env)).rows
        assert row.code is PublishCode.PAGE_OUT_OF_DATE

    def test_missing_activity_facts_keep_their_own_refusal(self, env: Env) -> None:
        env.write("a.md", _fm(start_time=None), post="")
        (row,) = env.run(_plan(env)).rows
        assert row.code is PublishCode.ACTIVITY_FACTS_MISSING

    def test_a_page_with_no_archived_file_keeps_the_facts_refusal(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(sources=[]), post="")
        (row,) = env.run(_plan(env)).rows
        assert row.code is PublishCode.ACTIVITY_FACTS_MISSING

    def test_two_matching_records_keep_the_conflict(self, env: Env) -> None:
        env.write("a.md", _fm(sources=[_ref(SHA_B), _ref(SHA_A)]), post="")
        records = {
            "alpha": [
                _record(SHA_A, digest=None, number=1, code=None, at=None),
                _record(SHA_B, digest=None, number=2, code=None, at=None),
            ]
        }
        (row,) = env.run(_plan(env, records=records)).rows
        assert row.code is PublishCode.LEDGER_CONFLICT

    def test_a_record_shared_with_another_page_keeps_the_conflict(
        self, env: Env
    ) -> None:
        env.write("a.md", post="")
        env.write("b.md", _fm(sources=[_ref(SHA_C), _ref(SHA_A)]), post="")
        records = {"alpha": [_record(SHA_A, digest=None, number=1)]}
        report = env.run(_plan(env, records=records))
        assert _codes(report) == [
            ("workouts/a.md", "alpha", PublishCode.LEDGER_CONFLICT),
            ("workouts/b.md", "alpha", PublishCode.LEDGER_CONFLICT),
        ]

    def test_a_key_shared_with_another_page_and_no_record_keeps_the_conflict(
        self, env: Env
    ) -> None:
        env.write("a.md", post="")
        env.write("b.md", _fm(sources=[_ref(SHA_C), _ref(SHA_A)]), post="")
        report = env.run(_plan(env))
        assert _codes(report) == [
            ("workouts/a.md", "alpha", PublishCode.LEDGER_CONFLICT),
            ("workouts/b.md", "alpha", PublishCode.LEDGER_CONFLICT),
        ]

    def test_the_refusal_comes_before_the_composition(self, env: Env) -> None:
        settings = _settings(("alpha", "beta"), {"publish": {"title": ""}})
        env.write("a.md", post="")
        (row,) = env.run(_plan(env, settings=settings)).rows
        assert row.code is PublishCode.POST_WAITING

    def test_the_refusal_comes_before_the_decision(self, env: Env) -> None:
        env.write("a.md", post="")
        records = {"alpha": [_record(SHA_A, digest=None, number=1)]}
        (row,) = env.run(_plan(env, records=records)).rows
        assert (row.code, row.decision) == (PublishCode.POST_WAITING, None)

    def test_the_refusal_needs_no_index_or_query_machinery(
        self, env: Env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env.write("a.md", post="")
        for name in (
            "duckdb",
            "fitdocs.query",
            "fitdocs.index",
            "fitdocs.post_template",
        ):
            monkeypatch.setitem(sys.modules, name, None)
        assert env.run(_plan(env)).rows == (_waiting_row("alpha"),)

    def test_a_page_that_cannot_be_read_as_current_is_never_refused_as_waiting(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(doc_version=11), post="")
        env.write("b.md", _fm(sources=[_ref(SHA_B)], doc_version=99), post="")
        report = env.run(_plan(env))
        assert [r.code for r in report.rows] == [
            PublishCode.PAGE_OUT_OF_DATE,
            PublishCode.PAGE_NEWER,
        ]


class TestAFilledPageIsDecidedAsToday:
    def test_would_post_then_unchanged_once_landed_then_would_update_after_a_refill(
        self, env: Env
    ) -> None:
        page = env.write("a.md", post=_filled())
        text = page.read_text(encoding="utf-8")

        first = env.run(_plan(env))
        assert [(r.code, r.post) for r in first.rows] == [
            (PublishCode.WOULD_POST, FILLED_POST)
        ]
        assert first.failed is False

        env.spy.publisher.publish_script.append(PublishResult(PublishCode.POSTED))
        posted = env.run(_plan(env, posting=True))
        assert [(r.code, r.post) for r in posted.rows] == [
            (PublishCode.POSTED, FILLED_POST)
        ]
        assert len(env.spy.publisher.publish_calls) == 1
        assert env.spy.publisher.publish_calls[0][1].post == FILLED_POST

        ledgers = load_ledgers(env.root, {"alpha": CONNECTOR, "beta": CONNECTOR})
        plan = replace_ledgers(_plan(env), ledgers)
        assert plan.post_template_since == PAGE_DAY
        again = env.run(plan)
        assert [(r.code, r.post) for r in again.rows] == [(PublishCode.UNCHANGED, None)]

        page.write_text(
            text.replace(_filled(), _filled(REFILLED_POST)), encoding="utf-8"
        )
        assert _filled(REFILLED_POST) in page.read_text(encoding="utf-8")
        refilled_plan = replace_ledgers(_plan(env), ledgers)
        assert refilled_plan.post_template_since == PAGE_DAY
        changed = env.run(refilled_plan)
        assert [(r.code, r.post) for r in changed.rows] == [
            (PublishCode.WOULD_UPDATE, REFILLED_POST)
        ]

    def test_a_filled_page_is_not_refused_in_a_posting_run_with_a_second_target(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(publish=["alpha", "beta"]), post=_filled())
        report: PublishReport = env.run(_plan(env))
        assert [(r.target, r.code) for r in report.rows] == [
            ("alpha", PublishCode.WOULD_POST),
            ("beta", PublishCode.WOULD_POST),
        ]
