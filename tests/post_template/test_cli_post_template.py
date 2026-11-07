"""The ``fitdocs post-template`` command (post-templates task 5.2).

Requirements 5.10, 9.1, 9.2, 9.5, 9.7, 9.8, 10.1, 10.2, 10.6, 10.13, 10.14, 10.15,
11.1, 11.2, 11.3. Most tests drive the real command through ``CliRunner`` over a
copy of the shared indexed data root (four pages, a real index) and the real
resolver. The emptied-region test uses the 5.1 sync ``World`` instead, and the
registration test uses no data root. The seams are the index refresh (wrapped to
count calls), ``cli._today``, and, for the interrupt rows, the engine functions
that are made to raise.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from fitdocs import cli as cli_module
from fitdocs import contract
from fitdocs.cli import app
from fitdocs.docmerge import extract_regions, replace_region
from fitdocs.index.location import resolve_index_location
from fitdocs.post_template import engine as engine_module
from fitdocs.post_template.region import render_filled
from fitdocs.publish.ledger import (
    PublicationRecord,
    PublishLedger,
    save_ledger,
    workout_page_key,
)
from fitdocs.publish.request import Post
from tests.post_template._index import (
    AM,
    EXAMPLE_SQL,
    FIXTURE_TODAY,
    MON,
    PAGES,
    PM,
    REST,
    FixturePage,
    IndexedPostRoot,
    page_text,
)
from tests.post_template.test_sync_pass import World, fill_stamp_count

runner = CliRunner()

COUNT_SQL = "SELECT count(*)::INT FROM pages WHERE start_time_local <= $as_of"
#: Page n (in start order) composes "Run n": the pages that start no later than it.
RUN = {"MON": 1, "AM": 2, "PM": 3, "REST": 4}


def good(title: str = "Run {n}", since: str = "2021-01-01") -> str:
    return f'since = {since}\ntitle = "{title}"\n\n[vars.n]\nsql = "{COUNT_SQL}"\n'


GOOD = good()
SHARE = (
    "since = 2021-01-01\n"
    'title = "Share {share}"\n\n'
    f"[vars.share]\nsql = '''\n{EXAMPLE_SQL}'''\n"
)
REFUSED_FILE = "bogus = 1\n" + GOOD
BAD_SQL = 'since = 2021-01-01\ntitle = "Run {n}"\n\n[vars.n]\nsql = "SELECT 1"\n'
AS_OF = datetime(2021, 9, 1, 12, 0, 0)
OLD_DIGEST = hashlib.sha256(b"an earlier template").hexdigest()


def stem(page: FixturePage) -> str:
    return Path(page.path).stem


# --------------------------------------------------------------------------- #
# The environment
# --------------------------------------------------------------------------- #


class Env:
    """A private indexed data root, and the process environment that finds it."""

    def __init__(
        self, fixture: IndexedPostRoot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.fixture = fixture
        self.root = fixture.root
        self.monkeypatch = monkeypatch
        monkeypatch.setenv("HOME", str(fixture.home))
        monkeypatch.setenv("FITDOCS_INDEX_DIR", fixture.environ["FITDOCS_INDEX_DIR"])
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        monkeypatch.delenv("FITDOCS_DATA", raising=False)
        monkeypatch.setattr(cli_module, "_today", lambda: FIXTURE_TODAY)
        self.index_calls: list[Any] = []
        index_pass = cli_module._run_index_pass

        def counting(data_root: Path, *, handoff: Any) -> Any:
            self.index_calls.append(handoff)
            return index_pass(data_root, handoff=handoff)

        monkeypatch.setattr(cli_module, "_run_index_pass", counting)

    def run(self, *args: str, out: bool = True) -> Result:
        tail = ["--out", str(self.root)] if out else []
        return runner.invoke(app, ["post-template", *args, *tail])

    def command(self, *args: str) -> Result:
        return runner.invoke(app, [*args, "--out", str(self.root)])

    def template(self, text: str) -> None:
        (self.root / "post-template.toml").write_text(text, encoding="utf-8")

    def tree(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in sorted(self.root.rglob("*"))
            if path.is_file()
        }

    def path(self, page: FixturePage) -> Path:
        return self.root / page.path

    def bytes_of(self, page: FixturePage) -> bytes:
        return self.path(page).read_bytes()

    def post(self, page: FixturePage) -> str:
        return extract_regions(self.path(page).read_text(encoding="utf-8"))["post"]

    def set_post(self, page: FixturePage, content: str) -> None:
        text = self.path(page).read_text(encoding="utf-8")
        replaced = replace_region(text, "post", content)
        assert replaced is not None
        self.path(page).write_text(replaced, encoding="utf-8")
        refreshed = runner.invoke(app, ["index", "--out", str(self.root)])
        assert refreshed.exit_code == 0, refreshed.output

    def land(self, *pages: FixturePage) -> None:
        save_ledger(
            self.root,
            PublishLedger(
                "alpha",
                "connector-alpha",
                tuple(
                    PublicationRecord(
                        page=workout_page_key(page.key),
                        publication_id=hashlib.sha256(page.key.encode()).hexdigest()[
                            :32
                        ],
                        digest=hashlib.sha256(b"posted").hexdigest(),
                    )
                    for page in pages
                ),
            ),
        )

    def break_ledgers(self) -> None:
        path = self.root / ".fitdocs" / "publish" / "alpha.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ledger_version = 99\n", encoding="utf-8")

    def remove_index(self) -> None:
        location = resolve_index_location(
            self.root, self.fixture.environ, self.fixture.home
        )
        location.database.unlink()
        location.wal.unlink(missing_ok=True)

    def add_page(self, name: str, day: int, post: str) -> FixturePage:
        page = FixturePage(
            name,
            f"workouts/2021-09-{day:02d}-0700-run.md",
            hashlib.sha256(name.encode()).hexdigest(),
            datetime(2021, 9, day, 7, 0, 0),
            10.0,
        )
        self.path(page).write_text(page_text(page, post=post), encoding="utf-8")
        return page


@pytest.fixture
def env(post_root_copy: IndexedPostRoot, monkeypatch: pytest.MonkeyPatch) -> Env:
    return Env(post_root_copy, monkeypatch)


def filled(title: str, template_text: str = GOOD) -> str:
    """A post region as a fill writes it (the digest is only the template's)."""
    from fitdocs.post_template.template import parse_post_template

    digest = parse_post_template(
        template_text.encode(), path=Path("post-template.toml")
    ).digest
    return render_filled(Post(title, ""), template_digest=digest, as_of=AS_OF)


def stamp_count(region: str) -> int:
    return sum(
        contract.POST_FILL_STAMP.fullmatch(line) is not None
        for line in region.splitlines()
    )


# --------------------------------------------------------------------------- #
# Exit codes
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Case:
    args: tuple[str, ...]
    code: int
    template: str | None = GOOD
    setup: Callable[[Env], None] | None = None
    needle: str | None = None
    writes_nothing: bool = True
    refreshes: int = 0


def _unreadable(env: Env) -> None:
    env.break_ledgers()


def _no_index(env: Env) -> None:
    env.remove_index()


def _interrupt_refill(env: Env) -> None:
    def interrupted(*args: object, **kwargs: object) -> object:
        raise KeyboardInterrupt

    env.monkeypatch.setattr(engine_module, "run_refill", interrupted)


def _interrupt_check(env: Env) -> None:
    def interrupted(*args: object, **kwargs: object) -> object:
        raise KeyboardInterrupt

    env.monkeypatch.setattr(engine_module, "run_check", interrupted)


def _interrupt_index(env: Env) -> None:
    def interrupted(*args: object, **kwargs: object) -> object:
        raise KeyboardInterrupt

    env.monkeypatch.setattr(cli_module, "_run_index_pass", interrupted)


CASES: dict[str, Case] = {
    "check-ok": Case(("check",), 0),
    "check-yes": Case(("check", "--yes"), 2, needle="--yes"),
    "check-yes-pages": Case(("check", "--yes", stem(MON)), 2, needle="--yes"),
    "check-missing-file": Case(
        ("check",), 2, template=None, needle="post-template.toml"
    ),
    "check-refused-file": Case(("check",), 1, template=REFUSED_FILE, needle="bogus"),
    "check-unreadable-ledgers": Case(
        ("check",), 1, setup=_unreadable, needle="alpha.toml"
    ),
    "check-refused-sql": Case(("check",), 1, template=BAD_SQL, needle="$as_of"),
    "check-unknown-page": Case(("check", "no-such-page"), 2, needle="no-such-page"),
    "check-no-index": Case(("check",), 1, setup=_no_index),
    "check-failed-page": Case(("check", stem(REST)), 1, template=SHARE),
    "check-interrupt": Case(("check",), 130, setup=_interrupt_check),
    "refill-ok": Case(("refill",), 0),
    "refill-yes-ok": Case(("refill", "--yes"), 0, writes_nothing=False, refreshes=1),
    "refill-missing-file": Case(
        ("refill", "--yes"), 2, template=None, needle="post-template.toml"
    ),
    "refill-refused-file": Case(
        ("refill", "--yes"), 2, template=REFUSED_FILE, needle="bogus"
    ),
    "refill-unknown-page": Case(
        ("refill", "--yes", "no-such-page"), 2, needle="no-such-page"
    ),
    "refill-unreadable-ledgers": Case(
        ("refill", "--yes"), 2, setup=_unreadable, needle="alpha.toml"
    ),
    "refill-refused-sql": Case(
        ("refill", "--yes"), 2, template=BAD_SQL, needle="$as_of"
    ),
    "refill-no-index": Case(("refill", "--yes"), 1, setup=_no_index),
    "refill-failed-page": Case(
        ("refill", "--yes"), 1, template=SHARE, writes_nothing=False, refreshes=1
    ),
    "refill-interrupt": Case(("refill", "--yes"), 130, setup=_interrupt_refill),
    "refill-interrupt-in-refresh": Case(
        ("refill", "--yes"), 130, setup=_interrupt_index, writes_nothing=False
    ),
}


@pytest.mark.parametrize("case", CASES.values(), ids=CASES)
def test_each_exit_cause_has_its_own_code(env: Env, case: Case) -> None:
    if case.template is not None:
        env.template(case.template)
    if case.setup is not None:
        case.setup(env)
    before = env.tree()

    result = runner.invoke(app, ["post-template", *case.args, "--out", str(env.root)])

    assert result.exit_code == case.code, result.output
    if case.needle is not None:
        assert case.needle in result.output
    if case.writes_nothing:
        assert env.tree() == before
    else:
        assert env.tree() != before
    if case.code != 130:
        assert len(env.index_calls) == case.refreshes


def test_a_clean_write_changes_every_eligible_page(env: Env) -> None:
    """The control for the exit-2 rows: the same call with the fault removed writes."""
    env.template(GOOD)
    result = env.run("refill", "--yes")
    assert result.exit_code == 0, result.output
    for page in PAGES:
        assert stamp_count(env.post(page)) == 1


def test_the_interrupt_in_the_refresh_keeps_what_was_written(env: Env) -> None:
    env.template(GOOD)
    _interrupt_index(env)
    result = env.run("refill", "--yes")
    assert result.exit_code == 130
    assert all(stamp_count(env.post(page)) == 1 for page in PAGES)
    assert "interrupted" in result.stderr.lower()


def test_an_interrupt_says_so_on_stderr(env: Env) -> None:
    env.template(GOOD)
    _interrupt_refill(env)
    result = env.run("refill", "--yes")
    assert result.exit_code == 130
    assert "interrupted" in result.stderr.lower()


def test_check_reports_a_refused_file_and_unreadable_ledgers_together(
    env: Env,
) -> None:
    env.template(REFUSED_FILE)
    env.break_ledgers()
    result = env.run("check")
    assert result.exit_code == 1, result.output
    assert "bogus" in result.output
    assert "alpha.toml" in result.output


def test_check_still_runs_the_sql_checks_when_ledgers_are_unreadable(
    env: Env,
) -> None:
    env.template(BAD_SQL)
    env.break_ledgers()
    result = env.run("check")
    assert result.exit_code == 1, result.output
    assert "alpha.toml" in result.output
    assert "$as_of" in result.output
    assert "Eligible pages" not in result.output


def test_refill_with_refused_sql_writes_nothing_though_pages_are_eligible(
    env: Env,
) -> None:
    env.template(BAD_SQL)
    before = env.tree()
    result = env.run("refill", "--yes", "--format", "json")
    assert result.exit_code == 2
    assert env.tree() == before
    assert any("$as_of" in problem for problem in json.loads(result.stdout)["problems"])
    assert env.index_calls == []


def test_refill_with_unreadable_ledgers_refuses_before_reading_the_index(
    env: Env,
) -> None:
    env.template(GOOD)
    env.break_ledgers()
    env.remove_index()  # were the index tried first, the exit would be 1
    result = env.run("refill", "--yes")
    assert result.exit_code == 2, result.output


def test_a_named_unknown_page_beats_unreadable_ledgers(env: Env) -> None:
    env.template(GOOD)
    env.break_ledgers()
    result = env.run("refill", "no-such-page")
    assert result.exit_code == 2
    assert "no-such-page" in result.output
    assert "alpha.toml" not in result.output


# --------------------------------------------------------------------------- #
# Pages resolve the way publish resolves them
# --------------------------------------------------------------------------- #


def test_pages_resolve_by_name_with_or_without_suffix_or_by_path_once_each(
    env: Env,
) -> None:
    env.template(GOOD)
    env.monkeypatch.chdir(env.root / "workouts")
    result = env.run(
        "check",
        f"{stem(REST)}.md",
        f"./{stem(MON)}.md",
        stem(AM),
        stem(AM),
        "--format",
        "json",
    )
    assert result.exit_code == 0, result.output
    pages = [row["page"] for row in json.loads(result.stdout)["pages"]]
    assert pages == [MON.path, AM.path, REST.path]


# --------------------------------------------------------------------------- #
# The data root
# --------------------------------------------------------------------------- #


def test_the_data_root_comes_from_the_environment_without_out(env: Env) -> None:
    env.template(GOOD)
    env.monkeypatch.setenv("FITDOCS_DATA", str(env.root))
    result = env.run("check", out=False)
    assert result.exit_code == 0, result.output
    assert "Template: post-template.toml" in result.output


def test_out_beats_the_environment(
    env: Env, per_test_directory: Callable[[str], Path]
) -> None:
    env.template(GOOD)
    elsewhere = per_test_directory("elsewhere")
    env.monkeypatch.setenv("FITDOCS_DATA", str(elsewhere))
    result = env.run("check")
    assert result.exit_code == 0, result.output
    assert "Template: post-template.toml" in result.output


# --------------------------------------------------------------------------- #
# Refill: dry run, write, landed naming, the index
# --------------------------------------------------------------------------- #


def test_refill_without_yes_writes_nothing_and_with_yes_writes(env: Env) -> None:
    env.template(GOOD)
    env.land(AM)
    before = env.tree()

    dry = env.run("refill")

    assert dry.exit_code == 0, dry.output
    assert env.tree() == before
    assert env.index_calls == []
    assert "would_fill 3" in dry.output
    assert "Wrote" not in dry.output

    wet = env.run("refill", "--yes")

    assert wet.exit_code == 0, wet.output
    for page in (MON, PM, REST):
        region = env.post(page)
        assert stamp_count(region) == 1
        assert region.splitlines()[-1] == f"Run {RUN[page.name]}"
    assert env.bytes_of(AM) == before[AM.path]
    assert "filled 3" in wet.output
    assert "Wrote 3 pages" in wet.output
    assert "will update the posted" not in wet.output
    assert env.index_calls == [None]

    named = env.run("refill", "--yes", stem(AM))

    assert named.exit_code == 0, named.output
    assert env.post(AM).splitlines()[-1] == "Run 2"
    update = [
        line for line in named.output.splitlines() if "will update the posted" in line
    ]
    assert len(update) == 1
    assert AM.path in update[0]
    assert all(page.path not in update[0] for page in (MON, PM, REST))
    assert env.index_calls == [None, None]
    drift = env.command("query", "--schema")
    assert drift.exit_code == 0, drift.output
    assert "Behind: false" in drift.output
    assert "Changed: 0" in drift.output


def test_a_second_refill_has_nothing_to_write_and_does_not_refresh(env: Env) -> None:
    env.template(GOOD)
    assert env.run("refill", "--yes").exit_code == 0
    assert env.index_calls == [None]
    again = env.run("refill", "--yes")
    assert again.exit_code == 0, again.output
    assert "unchanged 4" in again.output
    assert "Wrote" not in again.output
    assert env.index_calls == [None]


def test_the_refresh_output_does_not_enter_json_and_follows_the_report_in_text(
    env: Env,
) -> None:
    env.template(GOOD)
    as_json = env.run("refill", "--yes", "--format", "json")
    assert as_json.exit_code == 0, as_json.output
    assert json.loads(as_json.stdout)["wrote"] == [page.path for page in PAGES]
    assert "Index:" in as_json.stderr

    env.template(good("Again {n}"))
    as_text = env.run("refill", "--yes")
    lines = as_text.stdout.splitlines()
    wrote = next(i for i, line in enumerate(lines) if line.startswith("Wrote"))
    refresh = next(i for i, line in enumerate(lines) if line.startswith("Index:"))
    assert wrote < refresh


def test_a_bare_refill_leaves_published_pages_and_reports_them_but_naming_refills(
    env: Env,
) -> None:
    env.template(GOOD)
    assert env.run("refill", "--yes").exit_code == 0
    env.template(good("Again {n}"))
    env.land(AM, PM)
    held = {page.name: env.bytes_of(page) for page in PAGES}

    bare = env.run("refill", "--yes")

    assert bare.exit_code == 0, bare.output
    assert env.bytes_of(AM) == held["AM"]
    assert env.bytes_of(PM) == held["PM"]
    assert env.post(MON).splitlines()[-1] == "Again 1"
    assert env.post(REST).splitlines()[-1] == "Again 4"
    assert "2 published pages left out; name a page to refill it." in bare.output

    named = env.run("refill", "--yes", stem(AM))

    assert named.exit_code == 0, named.output
    assert env.post(AM).splitlines()[-1] == "Again 2"
    assert env.bytes_of(PM) == held["PM"]
    assert "left out" not in named.output
    assert AM.path in named.output.split("will update the posted")[1]


def test_an_athletes_page_is_never_touched(env: Env) -> None:
    env.template(GOOD)
    env.set_post(REST, "My own words")
    mine = env.bytes_of(REST)

    bare = env.run("refill", "--yes")

    assert bare.exit_code == 0, bare.output
    assert env.bytes_of(REST) == mine
    assert "1 Athlete's page left out." in bare.output
    assert stamp_count(env.post(MON)) == 1

    named = env.run("refill", "--yes", stem(REST), "--format", "json")

    assert named.exit_code == 0, named.output
    assert env.bytes_of(REST) == mine
    [row] = json.loads(named.stdout)["pages"]
    assert (row["page"], row["state"], row["code"]) == (
        REST.path,
        "athletes",
        "athletes_text",
    )


def test_an_emptied_region_is_refilled_by_the_next_sync(
    per_test_directory: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    world = World(per_test_directory, monkeypatch)
    world.add_run("sync")
    world.add_ride("sync")
    first = world.sync()
    assert first.exit_code == 0, first.output
    world.build_index()
    world.template()
    out = ["--out", str(world.root)]
    filled_run = runner.invoke(app, ["post-template", "refill", "--yes", *out])
    assert filled_run.exit_code == 0, filled_run.output
    one, other = world.pages()
    held = world.post_region(other)
    assert fill_stamp_count(held) == 1 and fill_stamp_count(world.post_region(one)) == 1
    other_bytes = other.read_bytes()
    composed = world.post_region(one).splitlines()[-1]
    assert composed.startswith("Run ")
    text = one.read_text(encoding="utf-8")
    emptied = replace_region(text, "post", "")
    assert emptied is not None
    one.write_text(emptied, encoding="utf-8")
    assert world.post_region(one) == ""

    synced = runner.invoke(app, ["sync", "--no-prompt", *out])

    assert fill_stamp_count(world.post_region(one)) == 1, synced.output
    assert world.post_region(one).splitlines()[-1] == composed
    assert other.read_bytes() == other_bytes


# --------------------------------------------------------------------------- #
# Check
# --------------------------------------------------------------------------- #


def _mixed_world(env: Env) -> None:
    """Eligible: PM, E1, E2 (3). Not: MON (before since), AM (landed), REST
    (the athlete's), E3 (filled). Older template: E3 only."""
    env.template(good(since="2021-09-07"))
    env.land(AM)
    env.set_post(REST, "My own words")
    env.add_page("E1", 20, contract.POST_PLACEHOLDER)
    env.add_page("E2", 21, contract.POST_PLACEHOLDER)
    other = render_filled(Post("Old", ""), template_digest=OLD_DIGEST, as_of=AS_OF)
    env.add_page("E3", 22, other)


def test_check_without_pages_counts_what_the_next_sync_would_fill(env: Env) -> None:
    _mixed_world(env)
    before = env.tree()

    result = env.run("check")

    assert result.exit_code == 0, result.output
    assert "Eligible pages: 3" in result.output
    assert "Filled from an earlier template: 1" in result.output
    assert env.tree() == before
    assert env.index_calls == []

    as_json = json.loads(env.run("check", "--format", "json").stdout)
    assert (as_json["waiting"], as_json["older_template"], as_json["pages"]) == (
        3,
        1,
        [],
    )


def test_check_with_pages_shows_values_and_the_composed_post(env: Env) -> None:
    env.template(good("Run {n} here"))
    env.land(AM)
    env.set_post(REST, "My own words")
    before = env.tree()

    result = env.run("check", stem(AM), stem(REST))

    assert result.exit_code == 0, result.output
    assert env.tree() == before
    am_block, rest_block = result.stdout.split(REST.path)
    assert "state: waiting" in am_block
    assert "landed post: yes" in am_block
    assert "variable n: 2" in am_block
    assert "post title: Run 2 here" in am_block
    assert "state: athletes" in rest_block
    assert "variable n: 4" in rest_block
    assert "post title: Run 4 here" in rest_block
    assert "result: athletes_text" in rest_block


# --------------------------------------------------------------------------- #
# JSON and text carry the same results
# --------------------------------------------------------------------------- #


def _text_rows(text: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        if line.startswith("workouts/"):
            current = {"variables": []}
            rows[line] = current
        elif current is not None and line.startswith("  variable "):
            name, _, value = line.removeprefix("  variable ").partition(": ")
            current["variables"].append((name, value))
        elif current is not None and line.startswith("  "):
            key, _, value = line.strip().partition(": ")
            current[key] = value
        elif not line.startswith(" "):
            current = None
    return rows


def _same_results(text: str, as_json: dict[str, Any]) -> None:
    text_rows = _text_rows(text)
    assert list(text_rows) == [row["page"] for row in as_json["pages"]]
    assert len(text_rows) >= 3
    for row in as_json["pages"]:
        shown = text_rows[row["page"]]
        assert shown["state"] == row["state"]
        assert shown["result"] == row["code"]
        assert shown["in window"] == ("yes" if row["in_window"] else "no")
        assert shown["landed post"] == ("yes" if row["landed"] else "no")
        assert shown["variables"] == [(v["name"], v["value"]) for v in row["variables"]]
        if row["post"] is not None:
            assert shown["post title"] == row["post"]["title"]
    tally = ", ".join(f"{code} {n}" for code, n in as_json["counts"].items())
    assert f"Pages: {tally}" in text


def test_check_text_and_json_carry_the_same_results(env: Env) -> None:
    env.template(good("Run {n}"))
    env.land(AM)
    env.set_post(REST, "My own words")
    env.set_post(MON, filled("Filled"))
    pages = (stem(MON), stem(AM), stem(REST))

    text = env.run("check", *pages)
    as_json = json.loads(env.run("check", *pages, "--format", "json").stdout)

    assert text.exit_code == 0
    _same_results(text.stdout, as_json)
    assert f"Eligible pages: {as_json['waiting']}" in text.stdout
    assert as_json["command"] == "check"


def test_refill_text_and_json_carry_the_same_results(env: Env) -> None:
    env.template(good("Run {n}"))
    env.land(AM)
    env.set_post(REST, "My own words")
    pages = (stem(MON), stem(AM), stem(REST))

    text = env.run("refill", *pages)
    as_json = json.loads(env.run("refill", *pages, "--format", "json").stdout)

    assert text.exit_code == 0
    _same_results(text.stdout, as_json)
    assert as_json["command"] == "refill"
    assert as_json["writing"] is False
    assert as_json["landed_changed"] == [AM.path]
    assert AM.path in text.stdout.split("will update the posted")[1]


def test_the_format_option_accepts_only_text_and_json(env: Env) -> None:
    env.template(GOOD)
    assert env.run("check", "--format", "yaml").exit_code == 2


def test_the_form_must_be_check_or_refill(env: Env) -> None:
    env.template(GOOD)
    assert env.run("explain").exit_code == 2


def test_the_command_is_registered_and_listed_in_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert "post-template" in result.stdout
