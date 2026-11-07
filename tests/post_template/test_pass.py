"""The automatic pass (post-templates task 3.2).

Requirements 2.5, 6.2, 6.3, 6.4, 6.6, 6.7, 6.8, 7.1, 7.2, 7.3 and 8.5. `run_pass`
runs over real pages and real publish ledgers on disk, a FAKE resolver that
records every call, a scripted clock and an opener that counts. Each exclusion
rule (state, window, landed) has a decoy that only that rule excludes (a symlink
is also refused by the page reader),
and the clock is scripted so that the exact page the budget stops at is pinned.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest

from fitdocs import contract
from fitdocs.post_template import engine
from fitdocs.post_template.engine import IndexGate, run_pass
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
from fitdocs.post_template.region import render_filled
from fitdocs.post_template.template import PostTemplate, Variable, parse_post_template
from fitdocs.publish.ledger import (
    PublicationRecord,
    PublishLedger,
    save_ledger,
    workout_page_key,
)
from fitdocs.publish.request import Post
from tests.post_template.test_engine import _AS_OF, _page_text, _splice

_Make = Callable[[str], Path]

_SINCE = date(2021, 9, 1)
_OPEN = IndexGate(open=True, reason=None, next_step=None)
_NAMES = ("alpha", "mike", "zulu")
_VALUES = {"alpha": "A", "mike": "M", "zulu": "Z"}


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _key(name: str) -> str:
    """The base (last) source digest of the page called `name`."""
    return _sha(f"{name}-base")


def _old(name: str) -> str:
    """The older source digest of the page called `name`."""
    return _sha(f"{name}-old")


# --------------------------------------------------------------------------- #
# The world: a data root, pages, a template
# --------------------------------------------------------------------------- #


@dataclass
class World:
    root: Path
    originals: dict[str, bytes] = field(default_factory=dict)

    def page(
        self,
        name: str,
        *,
        day: str = "2021-09-05",
        post: str = contract.POST_PLACEHOLDER,
        version: int = contract.DOC_VERSION,
        extra_front: str = "",
    ) -> str:
        """Write `workouts/<name>.md` and return its data-root-relative path."""
        text = _page_text(
            day=day,
            post=post,
            version=version,
            sources=(_old(name), _key(name)),
        )
        if extra_front:
            marker = "generator: fitdocs\n"
            assert text.count(marker) == 1
            text = text.replace(marker, marker + extra_front + "\n")
        path = self.root / "workouts" / f"{name}.md"
        data = text.encode("utf-8")
        path.write_bytes(data)
        self.originals[name] = data
        return f"workouts/{name}.md"

    def bytes_of(self, name: str) -> bytes:
        return (self.root / "workouts" / f"{name}.md").read_bytes()

    def untouched(self, *names: str) -> bool:
        return all(self.bytes_of(n) == self.originals[n] for n in names)

    def ledger(self, target: str, *records: tuple[str, str | None]) -> None:
        """Write a ledger; each record is (source digest, landed digest)."""
        save_ledger(
            self.root,
            PublishLedger(
                target,
                f"connector-{target}",
                tuple(
                    PublicationRecord(
                        page=workout_page_key(sha),
                        publication_id=_sha(f"id-{target}-{sha}")[:32],
                        digest=digest,
                    )
                    for sha, digest in records
                ),
            ),
        )


@pytest.fixture
def world(per_test_directory: _Make) -> World:
    root = per_test_directory("pass")
    (root / "workouts").mkdir()
    return World(root)


def _template(world: World) -> PostTemplate:
    text = 'since = 2021-09-01\ntitle = "{zulu} {alpha} {mike} {sport}"\n'
    for name in _NAMES:
        text += f'\n[vars.{name}]\nsql = "SELECT 1 -- {name}"\n'
    return parse_post_template(text.encode(), path=world.root / "post-template.toml")


def _filled_post(template: PostTemplate) -> str:
    return render_filled(
        Post("Z A M Run", ""), template_digest=template.digest, as_of=_AS_OF
    )


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class Clock:
    """Returns the scripted values in turn; reading past the script fails."""

    def __init__(self, *values: float) -> None:
        self.values = values
        self.calls = 0

    def __call__(self) -> float:
        self.calls += 1
        if self.calls > len(self.values):
            raise AssertionError(f"the clock was read {self.calls} times")
        return self.values[self.calls - 1]


def _steady(reads: int = 40) -> Clock:
    return Clock(*([5.0] * reads))


def _forbidden_clock() -> Clock:
    return Clock()


class PassResolver:
    """Records every call. `outcomes` maps (page key, variable) to an outcome."""

    def __init__(
        self,
        *,
        problems: tuple[str, ...] = (),
        outcomes: dict[tuple[str, str], VariableOutcome] | None = None,
        behind: frozenset[str] = frozenset(),
        raises: tuple[str, BaseException] | None = None,
    ) -> None:
        self.problems = problems
        self.outcomes = outcomes or {}
        self.behind = behind
        self.raises = raises  # (where, error): "check", "current" or "resolve"
        self.calls: list[tuple[object, ...]] = []
        self.closed = 0

    def _maybe_raise(self, where: str) -> None:
        if self.raises is not None and self.raises[0] == where:
            raise self.raises[1]

    def check(self, template: PostTemplate) -> tuple[str, ...]:
        self.calls.append(("check", template))
        self._maybe_raise("check")
        return self.problems

    def page_is_current(self, page_key: str | None, path: str, data: bytes) -> bool:
        self.calls.append(("current", page_key, path))
        self._maybe_raise("current")
        return page_key not in self.behind

    def resolve(
        self, variable: Variable, binding: Binding, *, timeout_s: float
    ) -> VariableOutcome:
        assert binding.page_key is not None
        self.calls.append(("resolve", binding.page_key, variable.name, timeout_s))
        self._maybe_raise("resolve")
        return self.outcomes.get((binding.page_key, variable.name)) or VariableOutcome(
            variable.name, _VALUES[variable.name], None, None
        )

    def close(self) -> None:
        self.closed += 1

    def keys_seen(self) -> list[str]:
        """Page keys in the order they were first asked about."""
        seen: list[str] = []
        for call in self.calls:
            if call[0] in ("current", "resolve") and call[1] not in seen:
                seen.append(str(call[1]))
        return seen


class Opener:
    def __init__(
        self, result: PassResolver | Unavailable | None, *, forbidden: bool = False
    ) -> None:
        self.result = result
        self.forbidden = forbidden
        self.calls = 0

    def __call__(self) -> PassResolver | Unavailable:
        self.calls += 1
        assert not self.forbidden, "no resolver may be opened on this path"
        assert self.result is not None
        return self.result


def _timed_out(name: str) -> VariableOutcome:
    return VariableOutcome(name, None, FillCode.TIMED_OUT, f"{name} was slow")


def _run(
    world: World,
    template: PostTemplate,
    opener: Opener,
    clock: Clock,
    *,
    gate: IndexGate = _OPEN,
) -> FillReport:
    return run_pass(
        world.root, template, gate=gate, open_resolver=opener, monotonic=clock
    )


def _expected(
    template: PostTemplate,
    *,
    waiting: int,
    unavailable: Unavailable | None = None,
    problems: tuple[str, ...] = (),
    rows: tuple[PageResult, ...] = (),
    stopped: FillCode | None = None,
    stopped_variable: str | None = None,
) -> FillReport:
    return FillReport(
        command="pass",
        writing=True,
        template=TemplateSummary("post-template.toml", _SINCE, template.digest),
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


def _resolved() -> tuple[VariableOutcome, ...]:
    return tuple(VariableOutcome(n, _VALUES[n], None, None) for n in _NAMES)


def _row(
    name: str,
    code: FillCode,
    *,
    detail: str | None = None,
    variables: tuple[VariableOutcome, ...] = (),
    post: Post | None = None,
    changed: bool | None = None,
) -> PageResult:
    return PageResult(
        page=f"workouts/{name}.md",
        state=RegionState.WAITING,
        in_window=True,
        landed=False,
        code=code,
        detail=detail,
        variables=variables,
        post=post,
        changed=changed,
    )


def _filled_row(name: str) -> PageResult:
    return _row(
        name,
        FillCode.FILLED,
        variables=_resolved(),
        post=Post("Z A M Run", ""),
        changed=True,
    )


def _spy_ledger_loads(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    calls: list[Path] = []
    real = engine.load_ledgers

    def spy(data_root: Path, configured: object) -> object:
        calls.append(data_root)
        return real(data_root, configured)  # type: ignore[arg-type]

    monkeypatch.setattr(engine, "load_ledgers", spy)
    return calls


def _forbid_ledger_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(data_root: Path, configured: object) -> object:
        raise AssertionError("no ledger may be read on this path")

    monkeypatch.setattr(engine, "load_ledgers", refuse)


# --------------------------------------------------------------------------- #
# No candidate: an empty report, no ledger read, no resolver, no clock
# --------------------------------------------------------------------------- #


def _no_workouts_directory(world: World) -> None:
    (world.root / "workouts").rmdir()


def _empty_directory(world: World) -> None:
    return None


def _out_of_window(world: World) -> None:
    world.page("early", day="2021-08-31")


def _filled_in_window(world: World) -> None:
    world.page("done", post=_filled_post(_template(world)))


def _athletes_in_window(world: World) -> None:
    world.page("mine", post="My own words")


def _older_format(world: World) -> None:
    world.page("old", version=contract.DOC_VERSION - 1)


def _newer_format(world: World) -> None:
    world.page("new", version=contract.DOC_VERSION + 1)


def _not_a_workout(world: World) -> None:
    (world.root / "workouts" / "note.md").write_text(
        "---\ntype: note\n---\nbody\n", encoding="utf-8"
    )


def _symlink_to_a_waiting_page(world: World) -> None:
    world.page("real")
    elsewhere = world.root / "elsewhere.md"
    (world.root / "workouts" / "real.md").rename(elsewhere)
    (world.root / "workouts" / "linked.md").symlink_to(elsewhere)


def _not_a_markdown_file(world: World) -> None:
    world.page("plain")
    (world.root / "workouts" / "plain.md").rename(world.root / "workouts" / "plain.txt")


_NO_CANDIDATE = {
    "no-directory": _no_workouts_directory,
    "empty-directory": _empty_directory,
    "out-of-window": _out_of_window,
    "filled": _filled_in_window,
    "athletes": _athletes_in_window,
    "older-format": _older_format,
    "newer-format": _newer_format,
    "not-a-workout": _not_a_workout,
    "symlink": _symlink_to_a_waiting_page,
    "not-markdown": _not_a_markdown_file,
}


class TestNoCandidate:
    @pytest.mark.parametrize("build", _NO_CANDIDATE.values(), ids=_NO_CANDIDATE)
    def test_the_report_is_empty_and_nothing_is_read_or_opened(
        self,
        world: World,
        monkeypatch: pytest.MonkeyPatch,
        build: Callable[[World], None],
    ) -> None:
        build(world)
        template = _template(world)
        real_load = engine.load_ledgers
        _forbid_ledger_loads(monkeypatch)
        before = {p: p.read_bytes() for p in world.root.rglob("*") if p.is_file()}
        # A closed gate must not matter either: nothing is Eligible.
        closed = IndexGate(open=False, reason="not built", next_step="run it")
        report = _run(
            world,
            template,
            Opener(None, forbidden=True),
            _forbidden_clock(),
            gate=closed,
        )
        assert report == _expected(template, waiting=0)
        assert not report.failed
        assert before == {
            p: p.read_bytes() for p in world.root.rglob("*") if p.is_file()
        }
        # The positive control: the same decoys plus one Waiting page.
        monkeypatch.setattr(engine, "load_ledgers", real_load)
        (world.root / "workouts").mkdir(exist_ok=True)
        world.page("wanted")
        again = _run(world, template, Opener(PassResolver()), _steady())
        assert [row.page for row in again.rows] == ["workouts/wanted.md"]


# --------------------------------------------------------------------------- #
# Which pages, in what order
# --------------------------------------------------------------------------- #


class TestCandidates:
    def test_the_pages_are_waiting_in_the_window_in_file_name_order(
        self, world: World
    ) -> None:
        """Creation order c, a, d, b; date order d, b, a, c; names a, b, c, d."""
        world.page("c", day="2021-09-09")
        world.page("a", day="2021-09-05")
        world.page("d", day="2021-09-01")
        world.page("b", day="2021-09-03")
        world.page("empty-region", day="2021-09-04", post="")
        decoys = {
            "0-early": world.page("0-early", day="2021-08-31"),
            "1-done": world.page("1-done", post=_filled_post(_template(world))),
            "2-mine": world.page("2-mine", post="Mine"),
            "3-old": world.page("3-old", version=contract.DOC_VERSION - 1),
        }
        template = _template(world)
        resolver = PassResolver()
        report = _run(world, template, Opener(resolver), _steady())
        order = ["a", "b", "c", "d", "empty-region"]
        assert [row.page for row in report.rows] == [f"workouts/{n}.md" for n in order]
        assert resolver.keys_seen() == [_key(n) for n in order]
        assert report.wrote == tuple(f"workouts/{n}.md" for n in order)
        assert set(decoys) == {"0-early", "1-done", "2-mine", "3-old"}
        assert world.untouched(*decoys)

    def test_a_window_start_day_is_in_and_the_day_before_is_out(
        self, world: World
    ) -> None:
        world.page("on-the-day", day="2021-09-01")
        world.page("day-before", day="2021-08-31")
        resolver = PassResolver()
        report = _run(world, _template(world), Opener(resolver), _steady())
        assert [r.page for r in report.rows] == ["workouts/on-the-day.md"]

    def test_a_filled_page_is_never_asked_about(self, world: World) -> None:
        template = _template(world)
        world.page("filled", post=_filled_post(template))
        world.page("waiting")
        resolver = PassResolver()
        report = _run(world, template, Opener(resolver), _steady())
        assert resolver.keys_seen() == [_key("waiting")]
        assert [r.page for r in report.rows] == ["workouts/waiting.md"]
        assert world.untouched("filled")

    def test_an_athletes_page_is_never_asked_about(self, world: World) -> None:
        world.page("mine", post="My own words")
        world.page("waiting")
        resolver = PassResolver()
        report = _run(world, _template(world), Opener(resolver), _steady())
        assert [r.page for r in report.rows] == ["workouts/waiting.md"]
        assert resolver.keys_seen() == [_key("waiting")]
        assert world.untouched("mine")

    def test_a_page_out_of_the_window_is_never_asked_about(self, world: World) -> None:
        world.page("early", day="2021-08-31")
        world.page("waiting")
        resolver = PassResolver()
        _run(world, _template(world), Opener(resolver), _steady())
        assert resolver.keys_seen() == [_key("waiting")]
        assert world.untouched("early")

    def test_a_symlinked_page_is_not_filled_through_the_link(
        self, world: World
    ) -> None:
        world.page("real")
        elsewhere = world.root / "elsewhere.md"
        (world.root / "workouts" / "real.md").rename(elsewhere)
        original = elsewhere.read_bytes()
        (world.root / "workouts" / "linked.md").symlink_to(elsewhere)
        world.page("waiting")
        resolver = PassResolver()
        report = _run(world, _template(world), Opener(resolver), _steady())
        assert [r.page for r in report.rows] == ["workouts/waiting.md"]
        assert elsewhere.read_bytes() == original


class TestOptedIn:
    def test_a_page_is_eligible_whether_or_not_it_opted_in_to_a_target(
        self, world: World
    ) -> None:
        """Req 6.2: a `publish` key, valid or not, neither adds nor removes a page."""
        world.page("a-plain")
        world.page("b-opted", extra_front="publish: [some-target]")
        world.page("c-two", extra_front="publish: [one, two]")
        world.page("d-invalid", extra_front="publish: 3")
        world.page("e-empty", extra_front="publish: []")
        report = _run(world, _template(world), Opener(PassResolver()), _steady())
        names = ["a-plain", "b-opted", "c-two", "d-invalid", "e-empty"]
        assert [r.page for r in report.rows] == [f"workouts/{n}.md" for n in names]
        assert report.wrote == tuple(f"workouts/{n}.md" for n in names)


# --------------------------------------------------------------------------- #
# Landed posts
# --------------------------------------------------------------------------- #


class TestLanded:
    def test_every_candidate_landed_gives_the_empty_report(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world.page("a")
        world.page("b")
        world.page("c")
        # a: by its base source in one ledger, b: by its OLDER source in another,
        # c: by both. The ledgers are read, the gate and the resolver are not.
        world.ledger("first", (_key("a"), _sha("posted a")), (_key("c"), _sha("c1")))
        world.ledger("second", (_old("b"), _sha("posted b")), (_old("c"), _sha("c2")))
        template = _template(world)
        reads = _spy_ledger_loads(monkeypatch)
        closed = IndexGate(open=False, reason="not built", next_step="run it")
        report = _run(
            world,
            template,
            Opener(None, forbidden=True),
            _forbidden_clock(),
            gate=closed,
        )
        assert reads == [world.root]
        assert report == _expected(template, waiting=0)
        assert world.untouched("a", "b", "c")

    def test_landed_pages_are_left_out_and_the_rest_are_filled(
        self, world: World
    ) -> None:
        for name in ("a", "b", "c", "d", "e", "f"):
            world.page(name)
        world.ledger(
            "first",
            (_key("a"), _sha("posted")),  # a: landed by its base source
            (_key("c"), None),  # c: a record with no landed digest
            (_sha("someone else"), _sha("posted")),  # another file's record
        )
        world.ledger(
            "second",
            (_old("b"), _sha("posted")),  # b: landed by its older source, in 2nd ledger
            (_key("e"), None),  # e: no landed digest here either
        )
        template = _template(world)
        resolver = PassResolver()
        report = _run(world, template, Opener(resolver), _steady())
        assert resolver.keys_seen() == [_key(n) for n in ("c", "d", "e", "f")]
        assert [r.page for r in report.rows] == [f"workouts/{n}.md" for n in "cdef"]
        assert all(not row.landed for row in report.rows)
        assert world.untouched("a", "b")
        assert report.waiting == 0

    def test_ledgers_are_read_once_after_the_candidates_are_known(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world.page("a")
        world.page("b")
        reads = _spy_ledger_loads(monkeypatch)
        _run(world, _template(world), Opener(PassResolver()), _steady())
        assert reads == [world.root]

    def test_unreadable_ledgers_are_reported_with_the_candidate_count(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for name in ("a", "b", "c"):
            world.page(name)
        world.page("early", day="2021-08-31")
        world.page("done", post=_filled_post(_template(world)))
        world.page("mine", post="Mine")
        world.ledger("good", (_key("a"), None))
        broken = world.root / ".fitdocs" / "publish" / "zz.toml"
        broken.write_text("this is [not valid", encoding="utf-8")
        template = _template(world)
        reads = _spy_ledger_loads(monkeypatch)
        report = _run(world, template, Opener(None, forbidden=True), _forbidden_clock())
        assert reads == [world.root]
        assert report.waiting == 3
        assert report.rows == ()
        assert report.stopped is None
        assert report.template_problems == ()
        assert report.unavailable is not None
        assert str(broken) in report.unavailable.reason
        assert report.unavailable.reason.startswith(
            "the publish records cannot be read (publish ledger "
        )
        assert report.unavailable.next_step == (
            "fix the file it names, then run fitdocs sync again"
        )
        assert report.failed
        assert report == _expected(template, waiting=3, unavailable=report.unavailable)
        assert world.untouched("a", "b", "c", "early", "done", "mine")


# --------------------------------------------------------------------------- #
# Each unavailable path writes nothing
# --------------------------------------------------------------------------- #


def _two_waiting_one_landed(world: World) -> None:
    world.page("a")
    world.page("b")
    world.page("landed")
    world.page("early", day="2021-08-31")
    world.ledger("t", (_key("landed"), _sha("posted")))


class TestUnavailable:
    def test_a_closed_gate_is_reported_with_the_eligible_count(
        self, world: World
    ) -> None:
        _two_waiting_one_landed(world)
        template = _template(world)
        gate = IndexGate(
            open=False, reason="the index is not built", next_step="run fitdocs index"
        )
        opener = Opener(None, forbidden=True)
        report = _run(world, template, opener, _forbidden_clock(), gate=gate)
        assert report == _expected(
            template,
            waiting=2,
            unavailable=Unavailable("the index is not built", "run fitdocs index"),
        )
        assert report.failed
        assert opener.calls == 0
        assert world.untouched("a", "b", "landed", "early")

    def test_a_closed_gate_without_words_still_says_something(
        self, world: World
    ) -> None:
        world.page("a")
        gate = IndexGate(open=False, reason=None, next_step=None)
        report = _run(
            world,
            _template(world),
            Opener(None, forbidden=True),
            _forbidden_clock(),
            gate=gate,
        )
        assert report.unavailable == Unavailable(
            "the index is not ready", "run fitdocs index"
        )
        assert report.waiting == 1

    def test_an_open_gate_with_words_set_is_still_open(self, world: World) -> None:
        world.page("a")
        gate = IndexGate(open=True, reason="stale words", next_step="stale step")
        report = _run(
            world, _template(world), Opener(PassResolver()), _steady(), gate=gate
        )
        assert report.unavailable is None
        assert report.wrote == ("workouts/a.md",)

    def test_an_unavailable_resolver_is_reported_with_the_eligible_count(
        self, world: World
    ) -> None:
        _two_waiting_one_landed(world)
        template = _template(world)
        unavailable = Unavailable("the index is not built", "run fitdocs index")
        opener = Opener(unavailable)
        report = _run(world, template, opener, _steady())
        assert report == _expected(template, waiting=2, unavailable=unavailable)
        assert report.unavailable is unavailable
        assert opener.calls == 1
        assert world.untouched("a", "b", "landed", "early")

    def test_a_refused_template_sql_is_reported_once_and_nothing_is_written(
        self, world: World
    ) -> None:
        _two_waiting_one_landed(world)
        template = _template(world)
        resolver = PassResolver(problems=("alpha: no $as_of", "mike: a clock"))
        report = _run(world, template, Opener(resolver), _steady())
        assert report == _expected(
            template, waiting=2, problems=("alpha: no $as_of", "mike: a clock")
        )
        assert report.unavailable is None
        assert report.failed
        assert resolver.calls == [("check", template)]
        assert resolver.closed == 1
        assert world.untouched("a", "b", "landed", "early")

    def test_a_clean_check_is_run_once_before_any_page(self, world: World) -> None:
        world.page("a")
        world.page("b")
        template = _template(world)
        resolver = PassResolver()
        _run(world, template, Opener(resolver), _steady())
        checks = [i for i, c in enumerate(resolver.calls) if c[0] == "check"]
        assert checks == [0]
        assert resolver.calls[0] == ("check", template)


# --------------------------------------------------------------------------- #
# A whole pass
# --------------------------------------------------------------------------- #


class TestFilling:
    def test_the_pages_are_filled_with_the_five_second_statement_limit(
        self, world: World
    ) -> None:
        for name in ("c", "a", "b"):
            world.page(name)
        template = _template(world)
        resolver = PassResolver()
        report = _run(world, template, Opener(resolver), _steady())
        assert report == _expected(
            template,
            waiting=0,
            rows=tuple(_filled_row(n) for n in "abc"),
        )
        for name in "abc":
            assert world.bytes_of(name) == _splice(
                world.originals[name], _filled_post(template)
            )
        expected_calls: list[tuple[object, ...]] = [("check", template)]
        for name in "abc":
            expected_calls.append(("current", _key(name), f"workouts/{name}.md"))
            expected_calls += [("resolve", _key(name), n, 5.0) for n in _NAMES]
        assert resolver.calls == expected_calls
        assert resolver.closed == 1
        assert not report.failed

    def test_a_page_that_fails_is_left_waiting_and_the_pass_goes_on(
        self, world: World
    ) -> None:
        for name in "abcd":
            world.page(name)
        template = _template(world)
        failure = VariableOutcome("mike", None, FillCode.STATEMENT_FAILED, "no column")
        resolver = PassResolver(
            outcomes={(_key("b"), "mike"): failure}, behind=frozenset({_key("c")})
        )
        report = _run(world, template, Opener(resolver), _steady())
        assert report.rows == (
            _filled_row("a"),
            _row(
                "b",
                FillCode.STATEMENT_FAILED,
                detail="no column",
                variables=(VariableOutcome("alpha", "A", None, None), failure),
            ),
            _row(
                "c",
                FillCode.INDEX_BEHIND,
                detail="the index does not hold this page as it is now",
            ),
            _filled_row("d"),
        )
        assert report.waiting == 2
        assert report.wrote == ("workouts/a.md", "workouts/d.md")
        assert (report.stopped, report.stopped_variable) == (None, None)
        assert report.failed
        assert world.untouched("b", "c")
        assert resolver.keys_seen() == [_key(n) for n in "abcd"]

    def test_an_unfilled_page_counts_as_waiting_whatever_its_code(
        self, world: World
    ) -> None:
        for name in "abc":
            world.page(name)
        resolver = PassResolver(behind=frozenset({_key("a"), _key("b"), _key("c")}))
        report = _run(world, _template(world), Opener(resolver), _steady())
        assert report.waiting == 3
        assert report.wrote == ()


# --------------------------------------------------------------------------- #
# The 30 second budget
# --------------------------------------------------------------------------- #


class TestBudget:
    def test_the_pass_stops_before_the_page_at_which_thirty_seconds_have_gone(
        self, world: World
    ) -> None:
        """Start 100. Checks: 110 (fill a), 129.99 (fill b), 130.0 (stop).

        A `>` instead of `>=` fills c and stops at d; a check after each page
        stops one page late; a limit of 29 stops b; a limit of 31 fills c.
        """
        for name in "abcde":
            world.page(name)
        template = _template(world)
        resolver = PassResolver()
        clock = Clock(100.0, 110.0, 129.99, 130.0, 131.0)
        report = _run(world, template, Opener(resolver), clock)
        left = "the 30 second budget ran out"
        assert report.rows == (
            _filled_row("a"),
            _filled_row("b"),
            _row("c", FillCode.NOT_ATTEMPTED, detail=left),
            _row("d", FillCode.NOT_ATTEMPTED, detail=left),
            _row("e", FillCode.NOT_ATTEMPTED, detail=left),
        )
        assert report.stopped is FillCode.NOT_ATTEMPTED
        assert report.stopped_variable is None
        assert report.waiting == 3
        assert report.wrote == ("workouts/a.md", "workouts/b.md")
        assert clock.calls == 4  # the start, then one check per page tried
        assert resolver.keys_seen() == [_key("a"), _key("b")]
        assert resolver.closed == 1
        assert world.untouched("c", "d", "e")
        assert report.failed

    def test_time_spent_opening_and_checking_counts_against_the_budget(
        self, world: World
    ) -> None:
        """The opener waits 20 s on a busy index and `check` takes 10 more: the
        pass began 30 s ago, so no page is tried (Req 7.2)."""
        for name in "ab":
            world.page(name)
        now = [100.0]
        resolver = PassResolver()
        real_check = resolver.check

        def slow_check(template: PostTemplate) -> tuple[str, ...]:
            now[0] += 10.0
            return real_check(template)

        resolver.check = slow_check  # type: ignore[method-assign]

        def opener() -> PassResolver:
            now[0] += 20.0
            return resolver

        report = run_pass(
            world.root,
            _template(world),
            gate=_OPEN,
            open_resolver=opener,
            monotonic=lambda: now[0],
        )
        assert [r.code for r in report.rows] == [FillCode.NOT_ATTEMPTED] * 2
        assert report.stopped is FillCode.NOT_ATTEMPTED
        assert report.waiting == 2
        assert [c[0] for c in resolver.calls] == ["check"]
        assert world.untouched("a", "b")

    def test_the_budget_counts_from_the_start_not_from_zero(self, world: World) -> None:
        for name in "abcd":
            world.page(name)
        clock = Clock(1000.0, 1029.0, 1030.0)
        report = _run(world, _template(world), Opener(PassResolver()), clock)
        assert report.wrote == ("workouts/a.md",)
        assert report.stopped is FillCode.NOT_ATTEMPTED

    def test_a_pass_that_is_already_out_of_time_tries_no_page(
        self, world: World
    ) -> None:
        for name in "abcd":
            world.page(name)
        template = _template(world)
        resolver = PassResolver()
        report = _run(world, template, Opener(resolver), Clock(7.0, 37.0))
        assert [r.code for r in report.rows] == [FillCode.NOT_ATTEMPTED] * 4
        assert report.waiting == 4
        assert report.stopped is FillCode.NOT_ATTEMPTED
        assert resolver.calls == [("check", template)]
        assert world.untouched(*"abcd")

    def test_a_pass_within_the_budget_is_not_stopped(self, world: World) -> None:
        for name in "abcd":
            world.page(name)
        clock = Clock(0.0, 1.0, 2.0, 3.0, 29.999)
        report = _run(world, _template(world), Opener(PassResolver()), clock)
        assert report.stopped is None
        assert report.wrote == tuple(f"workouts/{n}.md" for n in "abcd")
        assert clock.calls == 5


# --------------------------------------------------------------------------- #
# The first timeout
# --------------------------------------------------------------------------- #


class TestTimeout:
    @pytest.mark.parametrize("slow", ["a", "c", "e"], ids=["first", "middle", "last"])
    def test_the_pass_stops_at_the_first_timeout(self, world: World, slow: str) -> None:
        for name in "abcde":
            world.page(name)
        template = _template(world)
        timed_out = _timed_out("mike")
        resolver = PassResolver(outcomes={(_key(slow), "mike"): timed_out})
        clock = _steady()
        report = _run(world, template, Opener(resolver), clock)
        position = "abcde".index(slow)
        left = "mike timed out on an earlier page"
        rows = [_filled_row(n) for n in "abcde"[:position]]
        rows.append(
            _row(
                slow,
                FillCode.TIMED_OUT,
                detail="mike was slow",
                variables=(VariableOutcome("alpha", "A", None, None), timed_out),
            )
        )
        rows += [
            _row(n, FillCode.NOT_ATTEMPTED, detail=left)
            for n in "abcde"[position + 1 :]
        ]
        assert report.rows == tuple(rows)
        assert report.stopped is FillCode.TIMED_OUT
        assert report.stopped_variable == "mike"
        assert report.waiting == 5 - position
        assert report.wrote == tuple(f"workouts/{n}.md" for n in "abcde"[:position])
        assert clock.calls == 1 + position + 1  # no budget check after the stop
        assert resolver.keys_seen() == [_key(n) for n in "abcde"[: position + 1]]
        assert world.untouched(*"abcde"[position:])
        assert resolver.closed == 1
        assert report.failed

    def test_the_variable_named_is_the_one_that_timed_out_not_the_first(
        self, world: World
    ) -> None:
        world.page("a")
        world.page("b")
        resolver = PassResolver(outcomes={(_key("a"), "zulu"): _timed_out("zulu")})
        report = _run(world, _template(world), Opener(resolver), _steady())
        assert report.stopped_variable == "zulu"
        assert report.rows[1].detail == "zulu timed out on an earlier page"

    def test_a_statement_that_fails_without_timing_out_does_not_stop_the_pass(
        self, world: World
    ) -> None:
        for name in "abc":
            world.page(name)
        failure = VariableOutcome("alpha", None, FillCode.VALUE_REFUSED, "no")
        resolver = PassResolver(outcomes={(_key("a"), "alpha"): failure})
        report = _run(world, _template(world), Opener(resolver), _steady())
        assert report.stopped is None
        assert report.wrote == ("workouts/b.md", "workouts/c.md")

    def test_a_timeout_and_the_budget_name_different_things(self, world: World) -> None:
        """A timeout on the page the budget would have allowed is the timeout."""
        for name in "ab":
            world.page(name)
        resolver = PassResolver(outcomes={(_key("a"), "mike"): _timed_out("mike")})
        report = _run(world, _template(world), Opener(resolver), Clock(0.0, 29.9))
        assert report.stopped is FillCode.TIMED_OUT
        assert report.rows[1].detail != "the 30 second budget ran out"


# --------------------------------------------------------------------------- #
# The resolver is closed on every path
# --------------------------------------------------------------------------- #


def _complete(world: World) -> tuple[PassResolver, Clock]:
    world.page("a")
    world.page("b")
    return PassResolver(), _steady()


def _refused(world: World) -> tuple[PassResolver, Clock]:
    world.page("a")
    return PassResolver(problems=("alpha: refused",)), _steady()


def _budget(world: World) -> tuple[PassResolver, Clock]:
    world.page("a")
    world.page("b")
    return PassResolver(), Clock(0.0, 1.0, 31.0)


def _timeout(world: World) -> tuple[PassResolver, Clock]:
    world.page("a")
    world.page("b")
    return PassResolver(outcomes={(_key("a"), "alpha"): _timed_out("alpha")}), _steady()


def _failure_row(world: World) -> tuple[PassResolver, Clock]:
    world.page("a")
    return PassResolver(behind=frozenset({_key("a")})), _steady()


_CLOSES = {
    "complete": _complete,
    "refused-sql": _refused,
    "budget-stop": _budget,
    "timeout-stop": _timeout,
    "failed-row": _failure_row,
}

_RAISES = {
    "check": RuntimeError("check blew up"),
    "current": RuntimeError("freshness blew up"),
    "resolve": RuntimeError("resolve blew up"),
    "interrupt": KeyboardInterrupt(),
}


class TestClose:
    @pytest.mark.parametrize("build", _CLOSES.values(), ids=_CLOSES)
    def test_the_resolver_is_opened_once_and_closed_once(
        self, world: World, build: Callable[[World], tuple[PassResolver, Clock]]
    ) -> None:
        resolver, clock = build(world)
        opener = Opener(resolver)
        _run(world, _template(world), opener, clock)
        assert (opener.calls, resolver.closed) == (1, 1)

    @pytest.mark.parametrize("where", _RAISES, ids=list(_RAISES))
    def test_a_raised_error_still_closes_the_resolver_and_propagates(
        self, world: World, where: str
    ) -> None:
        world.page("a")
        world.page("b")
        error = _RAISES[where]
        site = "resolve" if where == "interrupt" else where
        resolver = PassResolver(raises=(site, error))
        with pytest.raises(type(error)) as caught:
            _run(world, _template(world), Opener(resolver), _steady())
        assert caught.value is error
        assert resolver.closed == 1
        assert world.untouched("a", "b")

    def test_the_resolver_is_closed_after_its_last_use(self, world: World) -> None:
        world.page("a")
        events: list[str] = []
        resolver = PassResolver()
        real_close = resolver.close

        def close() -> None:
            events.append(f"close after {len(resolver.calls)} calls")
            real_close()

        resolver.close = close  # type: ignore[method-assign]
        _run(world, _template(world), Opener(resolver), _steady())
        assert events == ["close after 5 calls"]  # check, current, three resolves

    @pytest.mark.parametrize(
        "path", ["no-candidate", "gate-closed", "resolver-unavailable", "ledgers"]
    )
    def test_a_path_that_opens_no_resolver_closes_none(
        self, world: World, path: str
    ) -> None:
        gate = _OPEN
        unavailable = Unavailable("r", "n")
        if path != "no-candidate":
            world.page("a")
        if path == "ledgers":
            (world.root / ".fitdocs" / "publish").mkdir(parents=True)
            (world.root / ".fitdocs" / "publish" / "bad.toml").write_text(
                "[", encoding="utf-8"
            )
        if path == "gate-closed":
            gate = IndexGate(open=False, reason="r", next_step="n")
        resolver = PassResolver()
        opener = Opener(unavailable if path == "resolver-unavailable" else resolver)
        if path in ("gate-closed", "ledgers", "no-candidate"):
            opener = Opener(None, forbidden=True)
        _run(world, _template(world), opener, _steady(), gate=gate)
        assert resolver.closed == 0
        assert resolver.calls == []
