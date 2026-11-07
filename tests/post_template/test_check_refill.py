"""Check and refill (post-templates task 3.3).

Requirements 9.2 to 9.6 and 10.2, 10.3, 10.5 to 10.8, 10.10, 10.12. `run_check`
and `run_refill` run over real pages and real publish ledgers on disk and a FAKE
resolver that records every call. Each selection-table row is its own case with
a control page that a bare refill takes, so a page left out is left out by
exactly the row's rule (a named run takes only the named page). Expected bytes
are the page's original bytes, kept by the World.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from fitdocs import contract
from fitdocs.post_template import engine
from fitdocs.post_template.engine import (
    COMMAND_STATEMENT_TIMEOUT_S,
    run_check,
    run_refill,
)
from fitdocs.post_template.model import (
    FillCode,
    FillReport,
    RegionState,
    Unavailable,
    VariableOutcome,
)
from fitdocs.post_template.region import render_filled
from fitdocs.post_template.template import PostTemplate, PostTemplateError
from fitdocs.publish.ledger import PublishLedgerError, load_ledgers
from fitdocs.publish.pages import SelectedPage, select_pages
from fitdocs.publish.request import Post
from tests.post_template.test_engine import _AS_OF
from tests.post_template.test_pass import (
    Opener,
    PassResolver,
    World,
    _key,
    _template,
    _timed_out,
)


@pytest.fixture
def world(per_test_directory: Callable[[str], Path]) -> World:
    root = per_test_directory("check-refill")
    (root / "workouts").mkdir()
    return World(root)


_OLD_DIGEST = hashlib.sha256(b"an earlier template").hexdigest()
_STALE = Post("stale text", "")
_SAME = Post("Z A M Run", "")  # what the test template composes for every page
_IN = "2021-09-05"
_OUT = "2021-08-31"  # before the template's since of 2021-09-01


def _filled_text(
    template: PostTemplate, post: Post = _STALE, *, digest: str | None = None
) -> str:
    return render_filled(post, template_digest=digest or template.digest, as_of=_AS_OF)


def _post_for(template: PostTemplate, kind: str) -> str:
    return {
        "waiting": contract.POST_PLACEHOLDER,
        "filled-stale": _filled_text(template, _STALE),
        "filled-same": _filled_text(template, _SAME),
        "filled-older-template": _filled_text(template, _STALE, digest=_OLD_DIGEST),
        "athletes": "My own words",
    }[kind]


def _add(
    world: World,
    template: PostTemplate,
    name: str,
    kind: str,
    *,
    day: str = _IN,
    version: int = contract.DOC_VERSION,
) -> str:
    return world.page(name, day=day, post=_post_for(template, kind), version=version)


def _land(world: World, *names: str, unlanded: tuple[str, ...] = ()) -> None:
    """One ledger: the named pages landed, `unlanded` recorded without a digest."""
    records = [(_key(n), hashlib.sha256(b"posted").hexdigest()) for n in names]
    records += [(_key(n), None) for n in unlanded]
    world.ledger("alpha", *records)


def _ledgers(world: World) -> dict:  # type: ignore[type-arg]
    return load_ledgers(world.root, {})


def _named(world: World, *names: str) -> tuple[SelectedPage, ...]:
    return select_pages(world.root, names, cwd=world.root)


def _refill(
    world: World,
    template: PostTemplate,
    resolver: PassResolver,
    *names: str,
    writing: bool = True,
) -> FillReport:
    return run_refill(
        world.root,
        template,
        _named(world, *names) if names else (),
        writing=writing,
        ledgers=_ledgers(world),
        open_resolver=Opener(resolver),
    )


def _check(
    world: World,
    template: PostTemplate | PostTemplateError,
    resolver: PassResolver | Unavailable,
    *names: str,
    ledgers: object = None,
) -> FillReport:
    return run_check(
        world.root,
        template,
        _named(world, *names) if names else (),
        ledgers=_ledgers(world) if ledgers is None else ledgers,  # type: ignore[arg-type]
        open_resolver=Opener(resolver),  # type: ignore[arg-type]
    )


def _pages(report: FillReport) -> list[str]:
    return [
        row.page.removeprefix("workouts/").removesuffix(".md") for row in report.rows
    ]


def _tree(world: World) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in world.root.rglob("*") if p.is_file()}


# --------------------------------------------------------------------------- #
# The selection table, row by row
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Row:
    kind: str
    day: str = _IN
    landed: bool = False
    version: int = contract.DOC_VERSION
    taken: bool = False  # a bare refill refills it
    athletes: int = 0  # a bare refill counts it as the athlete's
    published: int = 0  # a bare refill counts it as published
    named: FillCode | None = None  # what naming it gives


_STALE_OLD = contract.DOC_VERSION - 1

BARE_ROWS = {
    "waiting-eligible": Row("waiting", taken=True, named=FillCode.FILLED),
    "filled-unpublished": Row("filled-stale", taken=True, named=FillCode.FILLED),
    "filled-same-unpublished": Row("filled-same", taken=True, named=FillCode.UNCHANGED),
    "filled-older-template": Row(
        "filled-older-template", taken=True, named=FillCode.FILLED
    ),
    "filled-published": Row(
        "filled-stale", landed=True, published=1, named=FillCode.FILLED
    ),
    "waiting-published": Row(
        "waiting", landed=True, published=1, named=FillCode.FILLED
    ),
    "athletes": Row("athletes", athletes=1, named=FillCode.ATHLETES_TEXT),
    "athletes-published": Row(
        "athletes", landed=True, athletes=1, named=FillCode.ATHLETES_TEXT
    ),
    "waiting-out-of-window": Row("waiting", day=_OUT, named=FillCode.FILLED),
    "filled-out-of-window": Row("filled-stale", day=_OUT, named=FillCode.FILLED),
    "filled-published-out-of-window": Row(
        "filled-stale", day=_OUT, landed=True, named=FillCode.FILLED
    ),
    "athletes-out-of-window": Row("athletes", day=_OUT, named=FillCode.ATHLETES_TEXT),
    "older-format": Row("waiting", version=_STALE_OLD, named=FillCode.PAGE_NOT_CURRENT),
}


class TestBareRefillSelection:
    @pytest.mark.parametrize("row", BARE_ROWS.values(), ids=BARE_ROWS)
    @pytest.mark.parametrize("writing", [True, False], ids=["yes", "dry"])
    def test_each_row_is_taken_or_left_out_by_its_own_rule(
        self, world: World, row: Row, writing: bool
    ) -> None:
        template = _template(world)
        _add(world, template, "aa-control", "waiting")
        _add(world, template, "subject", row.kind, day=row.day, version=row.version)
        if row.landed:
            _land(world, "subject")
        resolver = PassResolver()
        report = _refill(world, template, resolver, writing=writing)
        taken = ["aa-control"] + (["subject"] if row.taken else [])
        assert _pages(report) == taken
        assert report.athletes_left_out == row.athletes
        assert report.published_left_out == row.published
        assert report.waiting == 0
        assert report.command == "refill"
        assert report.writing is writing
        if not row.taken:
            assert world.untouched("subject")
            assert resolver.keys_seen() == [_key("aa-control")]
        assert report.template is not None
        assert report.template.digest == template.digest

    def test_a_bare_refill_leaves_a_published_filled_page_and_counts_it(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa-open", "filled-stale")
        _add(world, template, "bb-posted", "filled-stale")
        _add(world, template, "cc-posted", "filled-stale")
        _land(world, "bb-posted", "cc-posted")
        report = _refill(world, template, PassResolver())
        assert _pages(report) == ["aa-open"]
        assert report.published_left_out == 2
        assert report.wrote == ("workouts/aa-open.md",)
        assert world.untouched("bb-posted", "cc-posted")
        assert not world.untouched("aa-open")

    def test_the_same_published_page_named_is_refilled(self, world: World) -> None:
        template = _template(world)
        _add(world, template, "aa-open", "filled-stale")
        _add(world, template, "bb-posted", "filled-stale")
        _land(world, "bb-posted")
        report = _refill(world, template, PassResolver(), "bb-posted")
        assert _pages(report) == ["bb-posted"]
        assert report.rows[0].code is FillCode.FILLED
        assert report.published_left_out == 0
        assert report.athletes_left_out == 0
        assert report.wrote == ("workouts/bb-posted.md",)
        assert world.untouched("aa-open")
        assert not world.untouched("bb-posted")

    def test_rows_come_in_file_name_order(self, world: World) -> None:
        template = _template(world)
        for name in ("cc", "aa", "dd", "bb"):
            _add(world, template, name, "waiting")
        report = _refill(world, template, PassResolver())
        assert _pages(report) == ["aa", "bb", "cc", "dd"]


class TestNamedRefillSelection:
    @pytest.mark.parametrize("row", BARE_ROWS.values(), ids=BARE_ROWS)
    def test_a_named_page_gets_the_rule_for_its_state_only(
        self, world: World, row: Row
    ) -> None:
        assert row.named is not None
        template = _template(world)
        _add(world, template, "aa-control", "waiting")
        _add(world, template, "subject", row.kind, day=row.day, version=row.version)
        if row.landed:
            _land(world, "subject")
        report = _refill(world, template, PassResolver(), "subject")
        assert _pages(report) == ["subject"]
        assert report.rows[0].code is row.named
        assert report.athletes_left_out == 0
        assert report.published_left_out == 0
        assert world.untouched("aa-control")
        if row.named is not FillCode.FILLED:
            assert world.untouched("subject")
        else:
            assert not world.untouched("subject")

    def test_a_named_athletes_page_is_left_alone_and_never_resolved(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa-mine", "athletes")
        _add(world, template, "bb-wait", "waiting")
        resolver = PassResolver()
        report = _refill(world, template, resolver, "aa-mine", "bb-wait")
        mine, wait = report.rows
        assert mine.code is FillCode.ATHLETES_TEXT
        assert mine.state is RegionState.ATHLETES
        assert mine.detail is not None and "athlete's own text" in mine.detail
        assert (mine.post, mine.variables, mine.changed) == (None, (), None)
        assert wait.code is FillCode.FILLED
        assert _key("aa-mine") not in resolver.keys_seen()
        assert not report.failed
        assert world.untouched("aa-mine")

    def test_named_pages_are_taken_in_file_name_order(self, world: World) -> None:
        template = _template(world)
        for name in ("cc", "aa", "bb"):
            _add(world, template, name, "waiting")
        report = _refill(world, template, PassResolver(), "cc", "aa", "bb")
        assert _pages(report) == ["aa", "bb", "cc"]


# --------------------------------------------------------------------------- #
# Refill: dry run, landed naming, failures, timeouts
# --------------------------------------------------------------------------- #


class TestRefillWriting:
    def test_a_dry_run_gives_the_flag_and_the_text_and_writes_nothing(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa-stale", "filled-stale")
        _add(world, template, "bb-same", "filled-same")
        _add(world, template, "cc-new", "waiting")
        before = _tree(world)
        resolver = PassResolver()
        report = _refill(world, template, resolver, writing=False)
        by_page = {row.page: row for row in report.rows}
        stale = by_page["workouts/aa-stale.md"]
        same = by_page["workouts/bb-same.md"]
        new = by_page["workouts/cc-new.md"]
        assert (stale.code, stale.changed, stale.post) == (
            FillCode.WOULD_FILL,
            True,
            _SAME,
        )
        assert (same.code, same.changed, same.post) == (
            FillCode.UNCHANGED,
            False,
            _SAME,
        )
        assert (new.code, new.changed, new.post) == (FillCode.WOULD_FILL, True, _SAME)
        assert report.wrote == ()
        assert _tree(world) == before
        assert resolver.closed == 1

    def test_a_write_changes_the_stale_page_and_leaves_the_same_text_alone(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa-stale", "filled-stale")
        _add(world, template, "bb-same", "filled-same")
        report = _refill(world, template, PassResolver())
        assert [row.code for row in report.rows] == [
            FillCode.FILLED,
            FillCode.UNCHANGED,
        ]
        assert report.wrote == ("workouts/aa-stale.md",)
        assert world.untouched("bb-same")
        assert (world.root / "workouts/aa-stale.md").read_text().count(
            _filled_text(template, _SAME)
        ) == 1

    @pytest.mark.parametrize("writing", [True, False], ids=["yes", "dry"])
    def test_only_a_changed_and_landed_page_is_named(
        self, world: World, writing: bool, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        template = _template(world)
        _add(world, template, "aa-changed-landed", "filled-stale")
        _add(world, template, "bb-changed-open", "filled-stale")
        _add(world, template, "cc-same-landed", "filled-same")
        _add(world, template, "dd-same-open", "filled-same")
        _add(world, template, "ee-changed-landed", "waiting")
        _add(world, template, "ff-failed-landed", "filled-stale")
        _add(world, template, "gg-writefail-landed", "filled-stale")
        _add(world, template, "hh-edited-landed", "filled-stale")
        _land(
            world,
            "aa-changed-landed",
            "cc-same-landed",
            "ee-changed-landed",
            "ff-failed-landed",
            "gg-writefail-landed",
            "hh-edited-landed",
            unlanded=("bb-changed-open",),
        )
        real_write = engine.write_bytes_if_changed

        def failing_write(path: Path, data: bytes) -> None:
            if path.name.startswith("gg-"):
                raise OSError(13, "Permission denied")
            real_write(path, data)

        monkeypatch.setattr(engine, "write_bytes_if_changed", failing_write)

        class Editing(PassResolver):
            def resolve(self, variable, binding, *, timeout_s):  # type: ignore[no-untyped-def]
                if binding.page_key == _key("hh-edited-landed"):
                    path = world.root / "workouts" / "hh-edited-landed.md"
                    path.write_bytes(path.read_bytes() + b" edit")
                return super().resolve(variable, binding, timeout_s=timeout_s)

        resolver = Editing(
            outcomes={
                (_key("ff-failed-landed"), "mike"): VariableOutcome(
                    "mike", None, FillCode.STATEMENT_FAILED, "boom"
                )
            }
        )
        report = _refill(
            world,
            template,
            resolver,
            "aa-changed-landed",
            "bb-changed-open",
            "cc-same-landed",
            "dd-same-open",
            "ee-changed-landed",
            "ff-failed-landed",
            "gg-writefail-landed",
            "hh-edited-landed",
            writing=writing,
        )
        landed = {row.page.split("/")[1][:2]: row.landed for row in report.rows}
        assert landed == {
            "aa": True,
            "bb": False,
            "cc": True,
            "dd": False,
            "ee": True,
            "ff": True,
            "gg": True,
            "hh": True,
        }
        codes = {row.page.split("/")[1][:2]: row.code for row in report.rows}
        if writing:
            assert codes["gg"] is FillCode.WRITE_FAILED
            assert codes["hh"] is FillCode.PAGE_CHANGED
            assert report.landed_changed == (
                "workouts/aa-changed-landed.md",
                "workouts/ee-changed-landed.md",
            )
        else:
            assert codes["gg"] is codes["hh"] is FillCode.WOULD_FILL
            assert report.landed_changed == (
                "workouts/aa-changed-landed.md",
                "workouts/ee-changed-landed.md",
                "workouts/gg-writefail-landed.md",
                "workouts/hh-edited-landed.md",
            )

    def test_a_landed_athletes_page_in_check_is_not_named(self, world: World) -> None:
        template = _template(world)
        _add(world, template, "aa-mine", "athletes")
        _add(world, template, "bb-waiting", "waiting")
        _land(world, "aa-mine", "bb-waiting")
        report = _check(world, template, PassResolver(), "aa-mine", "bb-waiting")
        mine = report.rows[0]
        assert (mine.code, mine.changed, mine.landed) == (
            FillCode.ATHLETES_TEXT,
            True,
            True,
        )
        assert report.landed_changed == ("workouts/bb-waiting.md",)

    def test_a_failed_refill_keeps_the_pages_text(self, world: World) -> None:
        template = _template(world)
        _add(world, template, "aa-ok", "filled-stale")
        _add(world, template, "bb-fails", "filled-stale")
        _add(world, template, "cc-ok", "filled-stale")
        resolver = PassResolver(
            outcomes={
                (_key("bb-fails"), "alpha"): VariableOutcome(
                    "alpha", None, FillCode.VALUE_REFUSED, "a float"
                )
            }
        )
        report = _refill(world, template, resolver)
        assert [row.code for row in report.rows] == [
            FillCode.FILLED,
            FillCode.VALUE_REFUSED,
            FillCode.FILLED,
        ]
        assert report.rows[1].detail == "a float"
        assert report.rows[1].post is None
        assert world.untouched("bb-fails")
        assert report.wrote == ("workouts/aa-ok.md", "workouts/cc-ok.md")
        assert report.failed
        assert report.stopped is None

    def test_a_timeout_stops_the_run_and_keeps_the_earlier_pages(
        self, world: World
    ) -> None:
        template = _template(world)
        for name in ("aa", "bb", "cc", "dd"):
            _add(world, template, name, "filled-stale")
        resolver = PassResolver(outcomes={(_key("bb"), "mike"): _timed_out("mike")})
        report = _refill(world, template, resolver)
        assert [row.code for row in report.rows] == [
            FillCode.FILLED,
            FillCode.TIMED_OUT,
            FillCode.NOT_ATTEMPTED,
            FillCode.NOT_ATTEMPTED,
        ]
        assert report.stopped is FillCode.TIMED_OUT
        assert report.stopped_variable == "mike"
        assert report.wrote == ("workouts/aa.md",)
        assert not world.untouched("aa")
        assert world.untouched("bb", "cc", "dd")
        assert _key("cc") not in resolver.keys_seen()
        assert _key("dd") not in resolver.keys_seen()
        assert all("mike" in (row.detail or "") for row in report.rows[2:])
        assert resolver.closed == 1

    def test_each_statement_is_allowed_thirty_seconds(self, world: World) -> None:
        assert COMMAND_STATEMENT_TIMEOUT_S == 30.0
        template = _template(world)
        _add(world, template, "aa", "waiting")
        resolver = PassResolver()
        _refill(world, template, resolver)
        timeouts = [c[3] for c in resolver.calls if c[0] == "resolve"]
        assert timeouts == [30.0, 30.0, 30.0]

    def test_a_page_the_index_does_not_hold_is_left_as_it_was(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa-ok", "filled-stale")
        _add(world, template, "bb-behind", "filled-stale")
        resolver = PassResolver(behind=frozenset({_key("bb-behind")}))
        report = _refill(world, template, resolver)
        row = report.rows[1]
        assert row.code is FillCode.INDEX_BEHIND
        assert row.detail is not None and "run fitdocs index" in row.detail
        assert row.variables == ()
        assert row.post is None
        assert world.untouched("bb-behind")
        assert report.failed
        assert report.stopped is None
        assert report.wrote == ("workouts/aa-ok.md",)
        assert not any(
            c[0] == "resolve" and c[1] == _key("bb-behind") for c in resolver.calls
        )

    def test_the_template_sql_is_checked_once_and_a_problem_writes_nothing(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa", "waiting")
        _add(world, template, "bb", "waiting")
        resolver = PassResolver(problems=("alpha: $foo is not allowed",))
        before = _tree(world)
        report = _refill(world, template, resolver)
        assert report.template_problems == ("alpha: $foo is not allowed",)
        assert report.rows == ()
        assert [c[0] for c in resolver.calls] == ["check"]
        assert resolver.closed == 1
        assert report.failed
        assert _tree(world) == before

    def test_an_unavailable_index_is_reported_and_nothing_is_written(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa", "waiting")
        before = _tree(world)
        gone = Unavailable("the index is not built", "run fitdocs index")
        report = run_refill(
            world.root,
            template,
            (),
            writing=True,
            ledgers=_ledgers(world),
            open_resolver=Opener(gone),  # type: ignore[arg-type]
        )
        assert report.unavailable == gone
        assert report.rows == ()
        assert report.failed
        assert _tree(world) == before

    def test_refused_sql_is_reported_even_when_no_page_needs_the_index(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa-mine", "athletes")
        resolver = PassResolver(problems=("alpha: $foo is not allowed",))
        report = _refill(world, template, resolver, "aa-mine")
        assert report.template_problems == ("alpha: $foo is not allowed",)
        assert report.rows == ()
        assert resolver.closed == 1
        assert report.failed

    def test_an_unavailable_index_is_reported_when_a_bare_refill_has_nothing_to_do(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa-mine", "athletes")
        _add(world, template, "bb-posted", "filled-stale")
        _land(world, "bb-posted")
        gone = Unavailable("the index is busy", "try again")
        report = run_refill(
            world.root,
            template,
            (),
            writing=True,
            ledgers=_ledgers(world),
            open_resolver=Opener(gone),  # type: ignore[arg-type]
        )
        assert report.unavailable == gone
        assert report.rows == ()
        assert report.athletes_left_out == 1
        assert report.published_left_out == 1
        assert report.failed

    def test_a_page_that_becomes_unreadable_mid_run_is_ignored_by_a_bare_refill(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Selection saw a workout page; reading it then fails (a race)."""
        template = _template(world)
        _add(world, template, "aa-wait", "waiting")
        _add(world, template, "bb-gone", "waiting")
        real = engine.read_for_fill

        def racing(page: SelectedPage, **kwargs: object):  # type: ignore[no-untyped-def]
            if page.rel.endswith("bb-gone.md"):
                (world.root / page.rel).unlink()
            return real(page, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(engine, "read_for_fill", racing)
        report = _refill(world, template, PassResolver())
        assert _pages(report) == ["aa-wait"]
        assert not report.failed

    def test_a_page_that_is_not_a_workout_is_ignored_by_a_bare_refill(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa-wait", "waiting")
        (world.root / "workouts" / "note.md").write_text(
            "---\ntype: note\n---\nbody\n", encoding="utf-8"
        )
        report = _refill(world, template, PassResolver())
        assert _pages(report) == ["aa-wait"]
        assert not report.failed

    @pytest.mark.parametrize("where", ["check", "current", "resolve"])
    def test_the_resolver_is_closed_when_it_raises(
        self, world: World, where: str
    ) -> None:
        template = _template(world)
        _add(world, template, "aa", "waiting")
        resolver = PassResolver(raises=(where, RuntimeError("boom")))
        with pytest.raises(RuntimeError, match="boom"):
            _refill(world, template, resolver)
        assert resolver.closed == 1
        assert world.untouched("aa")


# --------------------------------------------------------------------------- #
# Check
# --------------------------------------------------------------------------- #


class TestCheckWithoutPages:
    def _world(self, world: World) -> PostTemplate:
        template = _template(world)
        _add(world, template, "e1", "waiting")
        _add(world, template, "e2", "waiting")
        _add(world, template, "posted", "waiting")
        _add(world, template, "early", "waiting", day=_OUT)
        _add(world, template, "current-1", "filled-stale")
        _add(world, template, "older-1", "filled-older-template")
        _add(world, template, "older-2", "filled-older-template")
        _add(world, template, "mine", "athletes")
        _add(world, template, "old-format", "waiting", version=_STALE_OLD)
        _land(world, "posted")
        return template

    def test_the_eligible_and_older_template_counts_and_nothing_is_written(
        self, world: World
    ) -> None:
        template = self._world(world)
        before = _tree(world)
        resolver = PassResolver()
        report = _check(world, template, resolver)
        assert report.command == "check"
        assert report.writing is False
        assert report.waiting == 2
        assert report.older_template == 2
        assert report.rows == ()
        assert report.template_problems == ()
        assert report.unavailable is None
        assert not report.failed
        assert [c[0] for c in resolver.calls] == ["check"]
        assert resolver.closed == 1
        assert _tree(world) == before

    def test_a_filled_page_with_the_current_digest_is_not_older(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa", "filled-stale")
        _add(world, template, "bb", "filled-same")
        report = _check(world, template, PassResolver())
        assert report.older_template == 0
        assert report.waiting == 0

    def test_an_older_template_page_is_counted_out_of_the_window_too(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa", "filled-older-template", day=_OUT)
        _land(world, "aa")
        report = _check(world, template, PassResolver())
        assert report.older_template == 1

    def test_sql_problems_are_reported_with_the_counts(self, world: World) -> None:
        template = self._world(world)
        resolver = PassResolver(problems=("alpha: no $as_of", "mike: not a SELECT"))
        report = _check(world, template, resolver)
        assert report.template_problems == ("alpha: no $as_of", "mike: not a SELECT")
        assert report.waiting == 2
        assert report.older_template == 2
        assert report.failed

    def test_a_refused_file_carries_its_problems_and_the_sql_is_not_checked(
        self, world: World
    ) -> None:
        self._world(world)
        error = PostTemplateError(("p.toml: title: must be text", "p.toml: x: odd"))
        resolver = PassResolver()
        report = _check(world, error, resolver)
        assert report.template is None
        assert report.template_problems == error.problems
        assert report.waiting is None and report.older_template is None
        assert report.rows == ()
        assert [c[0] for c in resolver.calls] == []
        assert report.failed
        assert resolver.closed == 1

    def test_an_unavailable_index_still_reports_the_files_problems(
        self, world: World
    ) -> None:
        self._world(world)
        error = PostTemplateError(("p.toml: title: must be text",))
        gone = Unavailable("the index is not built", "run fitdocs index")
        report = _check(world, error, gone)
        assert report.template_problems == error.problems
        assert report.waiting is None and report.older_template is None
        assert report.rows == ()
        assert report.unavailable is not None
        assert "SQL was not checked" in report.unavailable.reason
        assert "the index is not built" in report.unavailable.reason
        assert report.unavailable.next_step == "run fitdocs index"
        assert report.failed

    def test_an_unavailable_index_with_a_good_file_still_counts(
        self, world: World
    ) -> None:
        template = self._world(world)
        gone = Unavailable("the index needs a rebuild", "run fitdocs index")
        report = _check(world, template, gone)
        assert report.template is not None
        assert report.template_problems == ()
        assert report.unavailable is not None
        assert "SQL was not checked" in report.unavailable.reason
        assert "needs a rebuild" in report.unavailable.reason
        assert (report.waiting, report.older_template) == (2, 2)
        assert report.failed

    def test_unreadable_ledgers_are_a_problem_and_the_rest_is_still_checked(
        self, world: World
    ) -> None:
        template = self._world(world)
        resolver = PassResolver(problems=("alpha: no $as_of",))
        report = _check(
            world,
            template,
            resolver,
            ledgers=PublishLedgerError("publish ledger /x/alpha.json: bad json"),
        )
        assert report.waiting is None
        assert report.older_template == 2
        assert report.template is not None
        assert report.template_problems[0] == "alpha: no $as_of"
        assert len(report.template_problems) == 2
        assert "publish records cannot be read" in report.template_problems[1]
        assert "/x/alpha.json" in report.template_problems[1]
        assert [c[0] for c in resolver.calls] == ["check"]
        assert report.failed


class TestUnreadableNamedPage:
    """A named page that cannot be read keeps its PAGE_NOT_CURRENT row."""

    def _setup(self, world: World) -> PostTemplate:
        template = _template(world)
        _add(world, template, "aa-wait", "waiting")
        (world.root / "workouts" / "bb-bad.md").write_bytes(
            b"---\ntype: workout\n---\n\xff\xfe bad\n"
        )
        _add(world, template, "cc-wait", "waiting")
        names = [p.rel for p in _named(world, "aa-wait", "bb-bad", "cc-wait")]
        assert names == [f"workouts/{n}.md" for n in ("aa-wait", "bb-bad", "cc-wait")]
        return template

    def _assert_row(self, report: FillReport, codes: list[FillCode]) -> None:
        assert _pages(report) == ["aa-wait", "bb-bad", "cc-wait"]
        bad = report.rows[1]
        assert bad.code is FillCode.PAGE_NOT_CURRENT
        assert (bad.state, bad.variables, bad.post) == (None, (), None)
        assert [r.code for r in report.rows] == codes

    def test_check_with_a_working_resolver(self, world: World) -> None:
        template = self._setup(world)
        report = _check(world, template, PassResolver(), "aa-wait", "bb-bad", "cc-wait")
        self._assert_row(
            report,
            [FillCode.WOULD_FILL, FillCode.PAGE_NOT_CURRENT, FillCode.WOULD_FILL],
        )

    def test_check_with_an_unavailable_index(self, world: World) -> None:
        template = self._setup(world)
        gone = Unavailable("the index is not built", "run fitdocs index")
        report = _check(world, template, gone, "aa-wait", "bb-bad", "cc-wait")
        self._assert_row(
            report,
            [
                FillCode.NOT_ATTEMPTED,
                FillCode.PAGE_NOT_CURRENT,
                FillCode.NOT_ATTEMPTED,
            ],
        )

    def test_check_with_refused_sql(self, world: World) -> None:
        template = self._setup(world)
        resolver = PassResolver(problems=("alpha: no $as_of",))
        report = _check(world, template, resolver, "aa-wait", "bb-bad", "cc-wait")
        self._assert_row(
            report,
            [
                FillCode.NOT_ATTEMPTED,
                FillCode.PAGE_NOT_CURRENT,
                FillCode.NOT_ATTEMPTED,
            ],
        )

    def test_refill(self, world: World) -> None:
        template = self._setup(world)
        report = _refill(
            world, template, PassResolver(), "aa-wait", "bb-bad", "cc-wait"
        )
        self._assert_row(
            report, [FillCode.FILLED, FillCode.PAGE_NOT_CURRENT, FillCode.FILLED]
        )
        assert report.failed


class TestCheckWithPages:
    def test_each_named_page_shows_its_state_window_landed_values_and_post(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa-wait", "waiting")
        _add(world, template, "bb-fill", "filled-same", day=_OUT)
        _add(world, template, "cc-mine", "athletes")
        _add(world, template, "dd-stale", "filled-stale")
        _add(world, template, "ee-unnamed", "waiting")
        _land(world, "bb-fill", "cc-mine")
        before = _tree(world)
        resolver = PassResolver()
        report = _check(
            world, template, resolver, "aa-wait", "bb-fill", "cc-mine", "dd-stale"
        )
        wait, fill, mine, stale = report.rows
        values = (
            VariableOutcome("alpha", "A", None, None),
            VariableOutcome("mike", "M", None, None),
            VariableOutcome("zulu", "Z", None, None),
        )
        assert (wait.state, wait.in_window, wait.landed) == (
            RegionState.WAITING,
            True,
            False,
        )
        assert (wait.code, wait.changed, wait.post) == (
            FillCode.WOULD_FILL,
            True,
            _SAME,
        )
        assert (fill.state, fill.in_window, fill.landed) == (
            RegionState.FILLED,
            False,
            True,
        )
        assert (fill.code, fill.changed, fill.post) == (
            FillCode.UNCHANGED,
            False,
            _SAME,
        )
        assert (mine.state, mine.in_window, mine.landed) == (
            RegionState.ATHLETES,
            True,
            True,
        )
        assert (mine.code, mine.changed, mine.post) == (
            FillCode.ATHLETES_TEXT,
            True,
            _SAME,
        )
        assert (stale.code, stale.state) == (FillCode.WOULD_FILL, RegionState.FILLED)
        for row in report.rows:
            assert row.variables == values
        assert _pages(report) == ["aa-wait", "bb-fill", "cc-mine", "dd-stale"]
        assert not report.failed
        assert _tree(world) == before
        assert resolver.closed == 1

    def test_an_athletes_page_that_cannot_be_composed_says_why(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa-mine", "athletes")
        absent = VariableOutcome("mike", None, None, None)
        resolver = PassResolver(outcomes={(_key("aa-mine"), "mike"): absent})
        report = _check(world, template, resolver, "aa-mine")
        (row,) = report.rows
        assert row.code is FillCode.VALUE_MISSING
        assert row.post is None
        assert row.state is RegionState.ATHLETES
        assert row.variables[1] == absent
        assert world.untouched("aa-mine")

    def test_a_variable_with_no_value_shows_why_and_the_page_has_no_post(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa", "waiting")
        failed = VariableOutcome("alpha", None, FillCode.STATEMENT_FAILED, "no column")
        resolver = PassResolver(outcomes={(_key("aa"), "alpha"): failed})
        report = _check(world, template, resolver, "aa")
        (row,) = report.rows
        assert row.code is FillCode.STATEMENT_FAILED
        assert row.variables == (failed,)
        assert row.post is None
        assert report.failed

    def test_a_page_the_index_does_not_hold_is_flagged(self, world: World) -> None:
        template = _template(world)
        _add(world, template, "aa-ok", "waiting")
        _add(world, template, "bb-behind", "athletes")
        resolver = PassResolver(behind=frozenset({_key("bb-behind")}))
        report = _check(world, template, resolver, "aa-ok", "bb-behind")
        assert report.rows[0].code is FillCode.WOULD_FILL
        behind = report.rows[1]
        assert behind.code is FillCode.INDEX_BEHIND
        assert behind.detail is not None and "fitdocs index" in behind.detail
        assert behind.variables == ()
        assert report.failed

    def test_a_page_that_is_not_current_gets_its_row_without_the_index(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa-old", "waiting", version=_STALE_OLD)
        resolver = PassResolver()
        report = _check(world, template, resolver, "aa-old")
        assert report.rows[0].code is FillCode.PAGE_NOT_CURRENT
        assert report.rows[0].state is None
        assert not any(c[0] in ("current", "resolve") for c in resolver.calls)

    def test_the_pages_state_window_and_landed_are_shown_when_the_sql_is_refused(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa-wait", "waiting")
        _add(world, template, "bb-mine", "athletes", day=_OUT)
        _land(world, "bb-mine")
        resolver = PassResolver(problems=("alpha: no $as_of",))
        report = _check(world, template, resolver, "aa-wait", "bb-mine")
        assert report.template_problems == ("alpha: no $as_of",)
        wait, mine = report.rows
        assert (wait.state, wait.in_window, wait.landed) == (
            RegionState.WAITING,
            True,
            False,
        )
        assert (mine.state, mine.in_window, mine.landed) == (
            RegionState.ATHLETES,
            False,
            True,
        )
        for row in report.rows:
            assert row.code is FillCode.NOT_ATTEMPTED
            assert (row.detail, row.variables, row.post, row.changed) == (
                None,
                (),
                None,
                None,
            )
        assert [c[0] for c in resolver.calls] == ["check"]

    def test_the_pages_state_window_and_landed_are_shown_when_the_index_is_unavailable(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa-wait", "waiting", day=_OUT)
        _add(world, template, "bb-fill", "filled-stale")
        _land(world, "bb-fill")
        gone = Unavailable("the index is not built", "run fitdocs index")
        report = _check(world, template, gone, "aa-wait", "bb-fill")
        wait, fill = report.rows
        assert (wait.state, wait.in_window, wait.landed) == (
            RegionState.WAITING,
            False,
            False,
        )
        assert (fill.state, fill.in_window, fill.landed) == (
            RegionState.FILLED,
            True,
            True,
        )
        assert {r.code for r in report.rows} == {FillCode.NOT_ATTEMPTED}
        assert report.unavailable is not None

    def test_a_refused_file_shows_no_page_rows(self, world: World) -> None:
        template = _template(world)
        _add(world, template, "aa-wait", "waiting")
        error = PostTemplateError(("p.toml: title: must be text",))
        report = _check(world, error, PassResolver(), "aa-wait")
        assert report.rows == ()
        gone = Unavailable("the index is not built", "run fitdocs index")
        assert _check(world, error, gone, "aa-wait").rows == ()

    def test_unreadable_ledgers_show_pages_without_a_landed_flag(
        self, world: World
    ) -> None:
        template = _template(world)
        _add(world, template, "aa-posted", "filled-stale")
        _land(world, "aa-posted")
        resolver = PassResolver()
        report = _check(
            world,
            template,
            resolver,
            "aa-posted",
            ledgers=PublishLedgerError("publish ledger /x: bad"),
        )
        (row,) = report.rows
        assert row.landed is None
        assert row.code is FillCode.WOULD_FILL
        assert report.landed_changed == ()
        assert report.waiting is None
        assert "publish records cannot be read" in report.template_problems[0]
        assert report.failed

    def test_check_stops_at_the_first_timeout(self, world: World) -> None:
        template = _template(world)
        for name in ("aa", "bb", "cc"):
            _add(world, template, name, "waiting")
        resolver = PassResolver(outcomes={(_key("bb"), "alpha"): _timed_out("alpha")})
        report = _check(world, template, resolver, "aa", "bb", "cc")
        assert [row.code for row in report.rows] == [
            FillCode.WOULD_FILL,
            FillCode.TIMED_OUT,
            FillCode.NOT_ATTEMPTED,
        ]
        assert report.stopped_variable == "alpha"
        timeouts = {c[3] for c in resolver.calls if c[0] == "resolve"}
        assert timeouts == {30.0}

    def test_check_never_writes_whatever_the_state(self, world: World) -> None:
        template = _template(world)
        for name, kind in (
            ("aa", "waiting"),
            ("bb", "athletes"),
            ("cc", "filled-stale"),
        ):
            _add(world, template, name, kind)
        before = _tree(world)
        _check(world, template, PassResolver(), "aa", "bb", "cc")
        assert _tree(world) == before

    def test_check_does_not_call_the_write_path(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(*args: object, **kwargs: object) -> None:
            raise AssertionError("check must not write")

        monkeypatch.setattr(engine, "write_bytes_if_changed", refuse)
        template = _template(world)
        _add(world, template, "aa", "waiting")
        report = _check(world, template, PassResolver(), "aa")
        assert report.rows[0].code is FillCode.WOULD_FILL
