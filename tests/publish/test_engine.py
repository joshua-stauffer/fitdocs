"""The publish engine's decision and dry run (publish-core task 6.2).

Requirements 2.3-2.6, 7.5-7.8, 11.7, 12.6 and 13.5, over a temporary data
root with real pages written to disk and a real ledger mapping. The scripted
publishing connector stands behind ``open_target`` so a dry run that opens a
target or sends a request is seen by what the connector recorded.

Posts are pinned as literals. Digests in the ledger are computed with
``post_digest`` over literal posts, never over the engine's output.
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
import yaml

import fitdocs.publish.engine as engine_module
from fitdocs.connectors.protocol import ConnectorSession
from fitdocs.docmerge import region_block
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.publish.compose import post_digest
from fitdocs.publish.engine import (
    PublishPlan,
    PublishReport,
    ResultRow,
    decide,
    run_publish,
)
from fitdocs.publish.ledger import (
    PublicationRecord,
    PublishLedger,
    load_ledgers,
    save_ledger,
    workout_page_key,
)
from fitdocs.publish.outcomes import PublishCode
from fitdocs.publish.pages import SelectedPage, select_pages
from fitdocs.publish.pages import sha_index as real_sha_index
from fitdocs.publish.request import Post
from fitdocs.publish.settings import PublishSettings, load_publish_settings
from fitdocs.publish.targets import TargetChannel
from tests.publish.conftest import ScriptedPublisher, run_page

SHA_A = "a" * 63 + "1"
SHA_B = "b" * 63 + "2"
SHA_C = "c" * 63 + "3"
CONNECTOR = "scripted-publisher"
#: The landed document-format version a current page carries.
CURRENT_VERSION = 12

DEFAULT_POST = Post(
    title="Morning Run",
    description=(
        "Distance: 12.50 km\nTime: 58:20\nPace: 4:40 /km\n"
        "Average heart rate: 149 bpm\nAverage power: 231 W\nElevation gain: 88 m"
    ),
)
OTHER_POST = Post(title="Something else", description="entirely")
CLOCK = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
LINK = "https://example.org/a/1"


def _ref(sha: str) -> str:
    return f"fit-archive/{sha}.fit"


def _id(number: int) -> str:
    return f"{number:032x}"


def _fm(**changes: object) -> dict[str, object]:
    """A current run page's frontmatter opting in to ``alpha``; ``None`` removes."""
    base: dict[str, object] = {
        "type": "workout",
        "doc_version": CURRENT_VERSION,
        "sources": [_ref(SHA_A)],
        "source_distance_m": 12500.25,
        "publish": "alpha",
    }
    page = run_page()
    page.update(base)
    for key, value in changes.items():
        if value is None:
            page.pop(key, None)
        else:
            page[key] = value
    return page


def _record(
    sha: str,
    *,
    digest: str | None,
    number: int,
    link: str | None = None,
    label: str | None = None,
    code: str | None = "posted",
    at: datetime | None = CLOCK,
) -> PublicationRecord:
    """A record; ``digest``, ``code`` and ``at`` vary independently."""
    return PublicationRecord(
        page=workout_page_key(sha),
        publication_id=_id(number),
        digest=digest,
        code=code,
        at=at,
        link=link,
        label=label,
    )


def _digest(post: Post) -> str:
    return post_digest(post)


def _snapshot(root: Path) -> dict[str, tuple[str, int, bytes | None]]:
    """``root`` itself and every name under it, with kind, mtime in ns and bytes."""
    seen: dict[str, tuple[str, int, bytes | None]] = {
        ".": ("dir", root.lstat().st_mtime_ns, None)
    }
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        rel = path.relative_to(root).as_posix()
        if path.is_file():
            seen[rel] = ("file", info.st_mtime_ns, path.read_bytes())
        else:
            seen[rel] = ("dir", info.st_mtime_ns, None)
    return seen


@dataclass
class Spy:
    """Records everything a dry run must never do."""

    publisher: ScriptedPublisher = field(default_factory=ScriptedPublisher)
    #: A target named here is served by its own publisher instead of ``publisher``.
    publishers: dict[str, ScriptedPublisher] = field(default_factory=dict)
    #: A target named here fails to open with this code.
    refuse: dict[str, PublishCode] = field(default_factory=dict)
    opened: list[str] = field(default_factory=list)
    clock_calls: int = 0
    mints: int = 0

    def open_target(self, name: str) -> TargetChannel | PublishCode:
        self.opened.append(name)
        if name in self.refuse:
            return self.refuse[name]
        publisher = self.publishers.get(name, self.publisher)
        return TargetChannel(
            name=name,
            label=publisher.link_label,
            publisher=publisher,
            session=cast(ConnectorSession, None),
        )

    def now(self) -> datetime:
        self.clock_calls += 1
        return CLOCK

    def mint_id(self) -> str:
        self.mints += 1
        return _id(900 + self.mints)


class Env:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.spy = Spy()

    def write(
        self,
        name: str,
        fm: Mapping[str, object] | None = None,
        *,
        post: str = "",
        published: str = "",
        body: str | None = None,
    ) -> Path:
        workouts = self.root / WORKOUTS_DIR
        workouts.mkdir(parents=True, exist_ok=True)
        if body is None:
            body = (
                "# Run\n\n"
                + region_block("notes", "my notes")
                + region_block("post", post)
                + region_block("published", published)
            )
        text = f"---\n{yaml.safe_dump(dict(fm or _fm()), sort_keys=False)}---\n\n{body}"
        path = workouts / name
        path.write_text(text, encoding="utf-8")
        return path

    def pages(self, *names: str) -> tuple[SelectedPage, ...]:
        return select_pages(self.root, names, cwd=self.root)

    def plan(
        self,
        *,
        pages: tuple[SelectedPage, ...] | None = None,
        configured: Sequence[str] = ("alpha", "beta"),
        considered: Sequence[str] | None = None,
        settings: PublishSettings | None = None,
        records: Mapping[str, Sequence[PublicationRecord]] | None = None,
        posting: bool = False,
    ) -> PublishPlan:
        chosen = sorted(configured if considered is None else considered)
        ledgers = {
            name: PublishLedger(name, CONNECTOR, tuple((records or {}).get(name, ())))
            for name in configured
        }
        return PublishPlan(
            data_root=self.root,
            pages=self.pages() if pages is None else pages,
            considered=tuple(chosen),
            configured=frozenset(configured),
            settings=settings or _settings(configured),
            ledgers=ledgers,
            posting=posting,
        )

    def run(self, plan: PublishPlan) -> PublishReport:
        return run_publish(
            plan,
            open_target=self.spy.open_target,
            now=self.spy.now,
            mint_id=self.spy.mint_id,
        )


def _settings(
    targets: Sequence[str], document: Mapping[str, object] | None = None
) -> PublishSettings:
    return load_publish_settings(
        dict(document or {}), settings_file=Path("fitdocs.toml"), targets=targets
    )


@pytest.fixture
def env(tmp_path: Path) -> Env:
    root = tmp_path / "data"
    root.mkdir()
    return Env(root)


def _by_target(report: PublishReport) -> dict[tuple[str, str | None], ResultRow]:
    return {(row.page, row.target): row for row in report.rows}


def _codes(report: PublishReport) -> list[tuple[str, str | None, PublishCode]]:
    return [(row.page, row.target, row.code) for row in report.rows]


# --------------------------------------------------------------------- decide


class TestDecide:
    def test_no_record_is_would_post(self) -> None:
        assert decide(None, _digest(DEFAULT_POST)) is PublishCode.WOULD_POST

    def test_a_record_without_a_landed_digest_is_would_post(self) -> None:
        record = _record(SHA_A, digest=None, number=1)
        assert record.digest is None
        assert decide(record, _digest(DEFAULT_POST)) is PublishCode.WOULD_POST

    def test_an_equal_digest_is_unchanged(self) -> None:
        record = _record(SHA_A, digest=_digest(DEFAULT_POST), number=1)
        assert decide(record, _digest(DEFAULT_POST)) is PublishCode.UNCHANGED

    def test_a_different_digest_is_would_update(self) -> None:
        record = _record(SHA_A, digest=_digest(OTHER_POST), number=1)
        assert decide(record, _digest(DEFAULT_POST)) is PublishCode.WOULD_UPDATE


# ------------------------------------------------------------------ decisions


class TestDecisions:
    def test_would_post_keeps_the_exact_post(self, env: Env) -> None:
        env.write("a.md")
        report = env.run(env.plan(considered=("alpha",)))
        (row,) = report.rows
        assert row == ResultRow(
            page="workouts/a.md",
            target="alpha",
            code=PublishCode.WOULD_POST,
            decision=PublishCode.WOULD_POST,
            post=DEFAULT_POST,
            link=None,
            link_refused=False,
            detail=None,
        )
        assert report.posting is False

    def test_a_record_with_no_landed_digest_is_would_post(self, env: Env) -> None:
        env.write("a.md")
        records = {"alpha": [_record(SHA_A, digest=None, number=1)]}
        report = env.run(env.plan(records=records))
        (row,) = report.rows
        assert row.code is PublishCode.WOULD_POST
        assert row.post == DEFAULT_POST

    def test_an_attempt_without_a_landed_digest_is_would_post(self, env: Env) -> None:
        env.write("a.md")
        unknown = _record(SHA_A, digest=None, number=1, code="unknown_result", at=CLOCK)
        assert (unknown.digest, unknown.code, unknown.at) == (
            None,
            "unknown_result",
            CLOCK,
        )
        assert decide(unknown, _digest(DEFAULT_POST)) is PublishCode.WOULD_POST
        (row,) = env.run(env.plan(records={"alpha": [unknown]})).rows
        assert row.code is PublishCode.WOULD_POST
        assert row.post == DEFAULT_POST

    def test_would_update_keeps_the_new_post(self, env: Env) -> None:
        env.write("a.md")
        records = {"alpha": [_record(SHA_A, digest=_digest(OTHER_POST), number=1)]}
        report = env.run(env.plan(records=records))
        (row,) = report.rows
        assert (row.code, row.decision) == (
            PublishCode.WOULD_UPDATE,
            PublishCode.WOULD_UPDATE,
        )
        assert row.post == DEFAULT_POST

    def test_unchanged_keeps_no_post(self, env: Env) -> None:
        env.write("a.md")
        records = {"alpha": [_record(SHA_A, digest=_digest(DEFAULT_POST), number=1)]}
        report = env.run(env.plan(records=records))
        (row,) = report.rows
        assert (row.code, row.decision) == (
            PublishCode.UNCHANGED,
            PublishCode.UNCHANGED,
        )
        assert row.post is None

    def test_each_target_is_composed_and_decided_separately(self, env: Env) -> None:
        env.write("a.md", _fm(publish=["alpha", "beta"]))
        settings = _settings(
            ("alpha", "beta"),
            {"publish": {"targets": {"beta": {"title": "B: {title}"}}}},
        )
        beta_post = Post("B: Morning Run", DEFAULT_POST.description)
        records = {
            "alpha": [_record(SHA_A, digest=_digest(DEFAULT_POST), number=1)],
            "beta": [_record(SHA_A, digest=_digest(DEFAULT_POST), number=2)],
        }
        report = env.run(env.plan(settings=settings, records=records))
        rows = _by_target(report)
        assert rows[("workouts/a.md", "alpha")].code is PublishCode.UNCHANGED
        beta = rows[("workouts/a.md", "beta")]
        assert beta.code is PublishCode.WOULD_UPDATE
        assert beta.post == beta_post

    def test_a_record_keyed_by_an_earlier_source_still_matches(self, env: Env) -> None:
        env.write("a.md", _fm(sources=[_ref(SHA_B), _ref(SHA_A)]))
        records = {"alpha": [_record(SHA_B, digest=_digest(DEFAULT_POST), number=1)]}
        (row,) = env.run(env.plan(records=records)).rows
        assert row.code is PublishCode.UNCHANGED

    def test_a_target_without_a_ledger_has_never_posted(self, env: Env) -> None:
        env.write("a.md")
        plan = replace_ledgers(env.plan(), {})
        assert plan.ledgers == {}
        (row,) = env.run(plan).rows
        assert row.code is PublishCode.WOULD_POST

    def test_a_record_for_another_page_is_not_this_pages(self, env: Env) -> None:
        env.write("a.md")
        records = {"alpha": [_record(SHA_C, digest=_digest(DEFAULT_POST), number=1)]}
        (row,) = env.run(env.plan(records=records)).rows
        assert row.code is PublishCode.WOULD_POST

    def test_the_post_region_replaces_the_template(self, env: Env) -> None:
        env.write("a.md", post="Race {title}\n\nbib {distance_km}")
        (row,) = env.run(env.plan()).rows
        assert row.post == Post("Race Morning Run", "bib 12.50")

    def test_a_post_region_with_only_a_comment_uses_the_template(
        self, env: Env
    ) -> None:
        env.write("a.md", post="<!-- write a post here -->")
        (row,) = env.run(env.plan()).rows
        assert row.post == DEFAULT_POST

    def test_the_post_region_is_decided_against_the_ledger(self, env: Env) -> None:
        env.write("a.md", post="Race\n\nbody")
        digest = _digest(Post("Race", "body"))
        records = {"alpha": [_record(SHA_A, digest=digest, number=1)]}
        (row,) = env.run(env.plan(records=records)).rows
        assert row.code is PublishCode.UNCHANGED

    def test_the_settings_template_is_decided_against_the_ledger(
        self, env: Env
    ) -> None:
        env.write("a.md")
        records = {"alpha": [_record(SHA_A, digest=_digest(DEFAULT_POST), number=1)]}
        settings = _settings(("alpha", "beta"), {"publish": {"title": "T {title}"}})
        (row,) = env.run(env.plan(records=records, settings=settings)).rows
        assert row.code is PublishCode.WOULD_UPDATE
        assert row.post == Post("T Morning Run", DEFAULT_POST.description)


class TestOrder:
    def test_pages_in_plan_order_then_targets_in_name_order(self, env: Env) -> None:
        env.write("a.md", _fm(publish=["beta", "alpha"]))
        env.write("b.md", _fm(sources=[_ref(SHA_B)], publish=["beta", "alpha"]))
        report = env.run(env.plan())
        assert _codes(report) == [
            ("workouts/a.md", "alpha", PublishCode.WOULD_POST),
            ("workouts/a.md", "beta", PublishCode.WOULD_POST),
            ("workouts/b.md", "alpha", PublishCode.WOULD_POST),
            ("workouts/b.md", "beta", PublishCode.WOULD_POST),
        ]

    def test_a_target_outside_the_considered_set_is_not_decided(self, env: Env) -> None:
        env.write("a.md", _fm(publish=["alpha", "beta"]))
        report = env.run(env.plan(considered=("beta",)))
        assert _codes(report) == [("workouts/a.md", "beta", PublishCode.WOULD_POST)]

    def test_the_report_counts_the_configured_targets(self, env: Env) -> None:
        env.write("a.md")
        report = env.run(
            env.plan(configured=("alpha", "beta", "gamma"), considered=("alpha",))
        )
        assert report.configured == 3


# ------------------------------------------------------------------- refusals


class TestPageRefusals:
    def test_a_named_unreadable_page_is_reported(self, env: Env) -> None:
        path = env.write("a.md")
        path.write_bytes(b"\xff\xfe not utf-8")
        pages = env.pages("a")
        assert pages[0].named
        report = env.run(env.plan(pages=pages))
        assert report.rows == (
            ResultRow(
                "workouts/a.md",
                None,
                PublishCode.PAGE_UNREADABLE,
                None,
                None,
                None,
                False,
                None,
            ),
        )
        assert report.not_opted_in == 0

    def test_an_unnamed_unreadable_page_is_skipped_and_not_counted(
        self, env: Env
    ) -> None:
        env.write("a.md").write_bytes(b"\xff\xfe")
        gone = SelectedPage(
            env.root / WORKOUTS_DIR / "a.md", "workouts/a.md", named=False
        )
        report = env.run(env.plan(pages=(gone,)))
        assert report.rows == ()
        assert report.not_opted_in == 0

    @pytest.mark.parametrize(
        ("value", "detail"),
        [
            (5, "the publish key must be one name or a list of names"),
            (
                ["alpha", "alpha"],
                "the publish list names 'alpha' more than once",
            ),
            ("", "the publish key is an empty name"),
        ],
    )
    def test_an_invalid_opt_in_is_a_page_row_with_its_detail(
        self, env: Env, value: object, detail: str
    ) -> None:
        env.write("a.md", _fm(publish=value))
        report = env.run(env.plan())
        assert report.rows == (
            ResultRow(
                "workouts/a.md",
                None,
                PublishCode.OPT_IN_INVALID,
                None,
                None,
                None,
                False,
                detail,
            ),
        )
        assert report.not_opted_in == 0

    def test_an_invalid_opt_in_is_reported_whatever_the_page_state(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(publish=5, doc_version=11))
        (row,) = env.run(env.plan()).rows
        assert row.code is PublishCode.OPT_IN_INVALID

    def test_an_unknown_name_is_reported_and_the_others_still_decided(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(publish=["zeta", "alpha", "ghost"]))
        report = env.run(env.plan())
        assert [(r.target, r.code) for r in report.rows] == [
            ("ghost", PublishCode.UNKNOWN_TARGET),
            ("zeta", PublishCode.UNKNOWN_TARGET),
            ("alpha", PublishCode.WOULD_POST),
        ]
        unknown = report.rows[0]
        assert (unknown.decision, unknown.post, unknown.detail) == (None, None, None)
        assert report.not_opted_in == 0

    def test_to_excludes_an_unknown_name(self, env: Env) -> None:
        env.write("a.md", _fm(publish=["ghost", "alpha"]))
        report = env.run(env.plan(considered=("alpha",)))
        assert _codes(report) == [("workouts/a.md", "alpha", PublishCode.WOULD_POST)]

    def test_a_configured_target_outside_to_is_not_unknown(self, env: Env) -> None:
        env.write("a.md", _fm(publish="beta"))
        report = env.run(env.plan(considered=("alpha",)))
        assert report.rows == ()
        assert report.not_opted_in == 1

    @pytest.mark.parametrize(
        ("version", "code"),
        [
            (11, PublishCode.PAGE_OUT_OF_DATE),
            (None, PublishCode.PAGE_OUT_OF_DATE),
            (13, PublishCode.PAGE_NEWER),
        ],
    )
    def test_older_and_newer_pages_are_refused_per_target(
        self, env: Env, version: int | None, code: PublishCode
    ) -> None:
        env.write("a.md", _fm(publish=["alpha", "beta"], doc_version=version))
        report = env.run(env.plan())
        assert [(r.target, r.code, r.decision, r.post) for r in report.rows] == [
            ("alpha", code, None, None),
            ("beta", code, None, None),
        ]

    def test_a_damaged_page_carries_the_region_detail(self, env: Env) -> None:
        env.write("a.md", body="# Run\n\n<!-- fitdocs:begin post -->\nno end\n")
        (row,) = env.run(env.plan()).rows
        assert row.code is PublishCode.PAGE_DAMAGED
        assert row.detail
        assert row.decision is None
        assert row.post is None

    def test_a_current_page_missing_a_region_is_damaged(self, env: Env) -> None:
        env.write("a.md", body="# Run\n\n" + region_block("notes", "n"))
        (row,) = env.run(env.plan()).rows
        assert row.code is PublishCode.PAGE_DAMAGED
        assert row.detail == "the page has no post region; run fitdocs regen"

    def test_no_activity_facts_is_refused(self, env: Env) -> None:
        env.write("a.md", _fm(start_time=None))
        (row,) = env.run(env.plan()).rows
        assert row.code is PublishCode.ACTIVITY_FACTS_MISSING
        assert (row.decision, row.post) == (None, None)

    def test_a_naive_start_is_no_activity_fact(self, env: Env) -> None:
        env.write("a.md", _fm(start_time="2026-03-04T07:05:00"))
        (row,) = env.run(env.plan()).rows
        assert row.code is PublishCode.ACTIVITY_FACTS_MISSING


class TestCompositionRefusals:
    def test_a_post_region_without_a_blank_line(self, env: Env) -> None:
        env.write("a.md", post="title\nbody")
        (row,) = env.run(env.plan()).rows
        assert (row.code, row.detail) == (
            PublishCode.POST_INVALID,
            "the line after the post title must be blank",
        )
        assert (row.decision, row.post) == (None, None)

    def test_a_template_error_in_the_post_region(self, env: Env) -> None:
        env.write("a.md", post="{nope}\n\nbody")
        (row,) = env.run(env.plan()).rows
        assert row.code is PublishCode.TEMPLATE_INVALID
        assert row.detail is not None
        assert row.detail.startswith("title, ")

    def test_a_missing_value_names_the_placeholder(self, env: Env) -> None:
        env.write("a.md", _fm(avg_power_w=None), post="{avg_power_w}\n\nbody")
        (row,) = env.run(env.plan()).rows
        assert (row.code, row.detail) == (PublishCode.VALUE_MISSING, "avg_power_w")

    def test_an_empty_title(self, env: Env) -> None:
        settings = _settings(("alpha", "beta"), {"publish": {"title": ""}})
        env.write("a.md")
        (row,) = env.run(env.plan(settings=settings)).rows
        assert (row.code, row.detail) == (PublishCode.TITLE_EMPTY, None)
        assert (row.decision, row.post) == (None, None)

    def test_a_refusal_is_not_decided_against_the_ledger(self, env: Env) -> None:
        env.write("a.md", post="title\nbody")
        records = {"alpha": [_record(SHA_A, digest=_digest(DEFAULT_POST), number=1)]}
        (row,) = env.run(env.plan(records=records)).rows
        assert row.code is PublishCode.POST_INVALID


class TestLedgerConflict:
    def test_two_records_for_one_page(self, env: Env) -> None:
        env.write("a.md", _fm(sources=[_ref(SHA_B), _ref(SHA_A)]))
        records = {
            "alpha": [
                _record(SHA_A, digest=_digest(DEFAULT_POST), number=1),
                _record(SHA_B, digest=_digest(DEFAULT_POST), number=2),
            ]
        }
        (row,) = env.run(env.plan(records=records)).rows
        assert (row.code, row.detail) == (
            PublishCode.LEDGER_CONFLICT,
            "more than one ledger record matches this page",
        )
        assert (row.decision, row.post) == (None, None)

    def test_one_record_matching_two_pages(self, env: Env) -> None:
        env.write("a.md")
        env.write("b.md", _fm(sources=[_ref(SHA_C), _ref(SHA_A)]))
        records = {"alpha": [_record(SHA_A, digest=_digest(DEFAULT_POST), number=1)]}
        report = env.run(env.plan(records=records))
        assert [(r.page, r.code, r.detail) for r in report.rows] == [
            (
                "workouts/a.md",
                PublishCode.LEDGER_CONFLICT,
                "the ledger record also matches workouts/b.md",
            ),
            (
                "workouts/b.md",
                PublishCode.LEDGER_CONFLICT,
                "the ledger record also matches workouts/a.md",
            ),
        ]

    def test_the_shared_record_is_found_though_only_one_page_is_selected(
        self, env: Env
    ) -> None:
        env.write("a.md")
        env.write("b.md", _fm(sources=[_ref(SHA_C), _ref(SHA_A)]))
        records = {"alpha": [_record(SHA_A, digest=_digest(DEFAULT_POST), number=1)]}
        pages = env.pages("a")
        assert len(pages) == 1
        (row,) = env.run(env.plan(pages=pages, records=records)).rows
        assert row.code is PublishCode.LEDGER_CONFLICT

    def test_the_record_found_by_an_earlier_source_is_the_one_checked_for_sharing(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(sources=[_ref(SHA_B), _ref(SHA_A)]))
        env.write("b.md", _fm(sources=[_ref(SHA_B)], publish=None))
        records = {"alpha": [_record(SHA_B, digest=_digest(DEFAULT_POST), number=1)]}
        (row,) = env.run(env.plan(records=records)).rows
        assert (row.page, row.code, row.detail) == (
            "workouts/a.md",
            PublishCode.LEDGER_CONFLICT,
            "the ledger record also matches workouts/b.md",
        )

    def test_a_record_keyed_by_a_sha_no_other_page_has_is_no_conflict(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(sources=[_ref(SHA_B), _ref(SHA_A)]))
        env.write("b.md", _fm(sources=[_ref(SHA_B)], publish=None))
        records = {"alpha": [_record(SHA_A, digest=_digest(DEFAULT_POST), number=1)]}
        (row,) = env.run(env.plan(records=records)).rows
        assert (row.page, row.code, row.detail) == (
            "workouts/a.md",
            PublishCode.UNCHANGED,
            None,
        )

    def test_a_record_without_a_landed_digest_still_conflicts_when_shared(
        self, env: Env
    ) -> None:
        env.write("a.md")
        env.write("b.md", _fm(sources=[_ref(SHA_C), _ref(SHA_A)]))
        records = {"alpha": [_record(SHA_A, digest=None, number=1)]}
        report = env.run(env.plan(records=records))
        assert [(r.page, r.code) for r in report.rows] == [
            ("workouts/a.md", PublishCode.LEDGER_CONFLICT),
            ("workouts/b.md", PublishCode.LEDGER_CONFLICT),
        ]

    def test_two_records_without_a_landed_digest_conflict(self, env: Env) -> None:
        env.write("a.md", _fm(sources=[_ref(SHA_B), _ref(SHA_A)]))
        records = {
            "alpha": [
                _record(SHA_A, digest=None, number=1),
                _record(SHA_B, digest=None, number=2),
            ]
        }
        (row,) = env.run(env.plan(records=records)).rows
        assert (row.code, row.detail) == (
            PublishCode.LEDGER_CONFLICT,
            "more than one ledger record matches this page",
        )

    def test_a_record_in_another_targets_ledger_is_no_conflict(self, env: Env) -> None:
        env.write("a.md", _fm(publish=["alpha", "beta"]))
        env.write("b.md", _fm(sources=[_ref(SHA_A), _ref(SHA_C)], publish="beta"))
        records = {"alpha": [_record(SHA_A, digest=_digest(DEFAULT_POST), number=1)]}
        rows = _by_target(env.run(env.plan(records=records)))
        assert rows[("workouts/b.md", "beta")].code is PublishCode.WOULD_POST

    def test_the_page_index_is_read_once_per_run_and_only_when_a_pair_is_decided(
        self, env: Env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[Path] = []
        real = real_sha_index

        def counting(data_root: Path) -> Mapping[str, tuple[str, ...]]:
            calls.append(data_root)
            return real(data_root)

        monkeypatch.setattr(engine_module, "sha_index", counting)
        env.write("a.md", _fm(publish=["alpha", "beta"]))
        env.write("b.md", _fm(sources=[_ref(SHA_B)], publish=["alpha", "beta"]))
        # Nothing to decide (no target considered): the index is never read.
        env.run(env.plan(considered=()))
        assert calls == []
        # A no-record pair checks its would-be key against the index (Req 7.6).
        env.run(env.plan())
        assert len(calls) == 1
        calls.clear()
        records = {
            "alpha": [_record(SHA_A, digest=_digest(DEFAULT_POST), number=1)],
            "beta": [_record(SHA_B, digest=_digest(DEFAULT_POST), number=2)],
        }
        env.run(env.plan(records=records))
        assert len(calls) == 1


class TestPrecedence:
    """Adjacent refusals, each fixture failing both rules so only order decides."""

    def test_the_opt_in_is_read_before_the_page_state(self, env: Env) -> None:
        env.write("a.md", _fm(publish=5, doc_version=11))
        assert [r.code for r in env.run(env.plan()).rows] == [
            PublishCode.OPT_IN_INVALID
        ]

    def test_the_page_state_comes_before_the_activity_facts(self, env: Env) -> None:
        env.write("a.md", _fm(doc_version=11, start_time=None))
        (row,) = env.run(env.plan()).rows
        assert row.code is PublishCode.PAGE_OUT_OF_DATE

    def test_the_activity_facts_come_before_the_ledger(self, env: Env) -> None:
        env.write("a.md", _fm(start_time=None, sources=[_ref(SHA_B), _ref(SHA_A)]))
        records = {
            "alpha": [
                _record(SHA_A, digest=_digest(DEFAULT_POST), number=1),
                _record(SHA_B, digest=_digest(DEFAULT_POST), number=2),
            ]
        }
        (row,) = env.run(env.plan(records=records)).rows
        assert row.code is PublishCode.ACTIVITY_FACTS_MISSING

    def test_the_ledger_comes_before_the_composition(self, env: Env) -> None:
        env.write("a.md", _fm(sources=[_ref(SHA_B), _ref(SHA_A)]), post="title\nbody")
        records = {
            "alpha": [
                _record(SHA_A, digest=_digest(DEFAULT_POST), number=1),
                _record(SHA_B, digest=_digest(DEFAULT_POST), number=2),
            ]
        }
        (row,) = env.run(env.plan(records=records)).rows
        assert row.code is PublishCode.LEDGER_CONFLICT

    def test_a_shared_record_is_a_conflict_before_the_post_region_is_read(
        self, env: Env
    ) -> None:
        env.write("a.md", post="title\nbody")
        env.write("b.md", _fm(sources=[_ref(SHA_C), _ref(SHA_A)]))
        records = {"alpha": [_record(SHA_A, digest=_digest(DEFAULT_POST), number=1)]}
        report = env.run(env.plan(records=records))
        assert _codes(report) == [
            ("workouts/a.md", "alpha", PublishCode.LEDGER_CONFLICT),
            ("workouts/b.md", "alpha", PublishCode.LEDGER_CONFLICT),
        ]

    def test_the_post_region_is_refused_before_the_template_renders(
        self, env: Env
    ) -> None:
        settings = _settings(("alpha", "beta"), {"publish": {"title": ""}})
        env.write("a.md", post="title\nbody")
        (row,) = env.run(env.plan(settings=settings)).rows
        assert row.code is PublishCode.POST_INVALID


class TestNotOptedIn:
    def test_pages_that_opt_in_to_nothing_considered_are_counted_not_listed(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(publish=None))
        env.write("b.md", _fm(sources=[_ref(SHA_B)], publish=[]))
        env.write("c.md", _fm(sources=[_ref(SHA_C)], publish="beta"))
        report = env.run(env.plan(considered=("alpha",)))
        assert report.rows == ()
        assert report.not_opted_in == 3

    def test_a_named_page_is_listed_and_not_counted(self, env: Env) -> None:
        env.write("a.md", _fm(publish=None))
        pages = env.pages("a")
        report = env.run(env.plan(pages=pages))
        assert report.rows == (
            ResultRow(
                "workouts/a.md",
                None,
                PublishCode.NOT_OPTED_IN,
                None,
                None,
                None,
                False,
                None,
            ),
        )
        assert report.not_opted_in == 0

    def test_a_named_page_opting_in_elsewhere_is_listed(self, env: Env) -> None:
        env.write("a.md", _fm(publish="beta"))
        report = env.run(env.plan(pages=env.pages("a"), considered=("alpha",)))
        assert _codes(report) == [("workouts/a.md", None, PublishCode.NOT_OPTED_IN)]

    def test_a_page_opting_in_to_one_considered_target_is_not_counted(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(publish=["alpha", "beta"]))
        report = env.run(env.plan(considered=("beta",)))
        assert report.not_opted_in == 0
        assert len(report.rows) == 1

    def test_a_page_naming_only_an_unknown_target_opts_in_to_none(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(publish="ghost"))
        report = env.run(env.plan())
        assert _codes(report) == [
            ("workouts/a.md", "ghost", PublishCode.UNKNOWN_TARGET)
        ]
        assert report.not_opted_in == 1

    def test_a_named_page_naming_only_an_unknown_target_is_listed_twice(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(publish="ghost"))
        report = env.run(env.plan(pages=env.pages("a")))
        assert _codes(report) == [
            ("workouts/a.md", "ghost", PublishCode.UNKNOWN_TARGET),
            ("workouts/a.md", None, PublishCode.NOT_OPTED_IN),
        ]
        assert report.not_opted_in == 0

    def test_an_older_page_naming_nothing_is_counted(self, env: Env) -> None:
        env.write("a.md", _fm(publish=None, doc_version=11))
        report = env.run(env.plan())
        assert (report.rows, report.not_opted_in) == ((), 1)


class TestFailed:
    def test_a_decision_alone_is_not_a_failure(self, env: Env) -> None:
        env.write("a.md")
        env.write("b.md", _fm(sources=[_ref(SHA_B)], publish=None))
        report = env.run(env.plan())
        assert [r.code for r in report.rows] == [PublishCode.WOULD_POST]
        assert report.failed is False

    def test_a_refusal_is_a_failure(self, env: Env) -> None:
        env.write("a.md")
        env.write("b.md", _fm(sources=[_ref(SHA_B)], doc_version=11))
        report = env.run(env.plan())
        assert report.failed is True

    def test_an_unchanged_pair_and_a_listed_unnamed_page_are_not_failures(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(publish=None))
        report = env.run(env.plan(pages=env.pages("a")))
        assert [r.code for r in report.rows] == [PublishCode.NOT_OPTED_IN]
        assert report.failed is False


# --------------------------------------------------------------------- dry run


class TestDryRun:
    def _populate(self, env: Env) -> tuple[Mapping[str, PublishLedger], PublishPlan]:
        env.write("a.md", _fm(publish=["alpha", "beta"]))  # would_update + would_post
        env.write(
            "b.md",
            _fm(sources=[_ref(SHA_B)]),
            published="stale links line",
        )  # unchanged, with a link the page does not show
        env.write("c.md", _fm(sources=[_ref(SHA_C)], doc_version=11))  # refused
        env.write("d.md", _fm(sources=[_ref("d" * 63 + "4")], publish=None))
        alpha = PublishLedger(
            "alpha",
            CONNECTOR,
            (
                _record(SHA_A, digest=_digest(OTHER_POST), number=1),
                _record(
                    SHA_B,
                    digest=_digest(DEFAULT_POST),
                    number=2,
                    link=LINK,
                    label="Scripted post",
                ),
            ),
        )
        beta = PublishLedger("beta", CONNECTOR, ())
        return {"alpha": alpha, "beta": beta}, env.plan()

    def _age(self, root: Path) -> None:
        """Give every name an old mtime so any later touch shows."""
        old = 1_000_000_000
        for path in sorted(root.rglob("*"), reverse=True):
            os.utime(path, (old, old), follow_symlinks=False)
        os.utime(root, (old, old))

    def test_a_dry_run_leaves_the_whole_tree_untouched_without_a_ledger_directory(
        self, env: Env
    ) -> None:
        ledgers, plan = self._populate(env)
        self._age(env.root)
        before = _snapshot(env.root)
        assert not (env.root / ".fitdocs").exists()
        report = env.run(replace_ledgers(plan, ledgers))
        assert {r.code for r in report.rows} >= {
            PublishCode.WOULD_POST,
            PublishCode.WOULD_UPDATE,
            PublishCode.UNCHANGED,
            PublishCode.PAGE_OUT_OF_DATE,
        }
        assert len(before) >= 4
        assert _snapshot(env.root) == before
        assert not (env.root / ".fitdocs").exists()

    def test_a_dry_run_leaves_existing_ledgers_and_pages_untouched(
        self, env: Env
    ) -> None:
        ledgers, plan = self._populate(env)
        for ledger in ledgers.values():
            save_ledger(env.root, ledger)
        loaded = load_ledgers(env.root, {"alpha": CONNECTOR, "beta": CONNECTOR})
        self._age(env.root)
        before = _snapshot(env.root)
        assert any(rel.startswith(".fitdocs/publish/") for rel in before)
        report = env.run(replace_ledgers(plan, loaded))
        assert PublishCode.WOULD_UPDATE in {r.code for r in report.rows}
        assert _snapshot(env.root) == before

    def test_a_dry_run_opens_nothing_sends_nothing_and_reads_no_clock(
        self, env: Env
    ) -> None:
        ledgers, plan = self._populate(env)
        report = env.run(replace_ledgers(plan, ledgers))
        assert any(r.post is not None for r in report.rows)
        assert env.spy.opened == []
        assert env.spy.publisher.publish_calls == []
        assert env.spy.clock_calls == 0
        assert env.spy.mints == 0

    def test_a_dry_run_leaves_the_planned_ledgers_unmodified(self, env: Env) -> None:
        ledgers, plan = self._populate(env)
        before = dict(ledgers)
        assert len(before) == 2
        plan = replace_ledgers(plan, ledgers)
        env.run(plan)
        assert dict(plan.ledgers) == before

    def test_the_same_inputs_give_the_same_report(self, env: Env) -> None:
        ledgers, plan = self._populate(env)
        plan = replace_ledgers(plan, ledgers)
        first = env.run(plan)
        assert len(first.rows) == 4
        assert env.run(plan) == first


def replace_ledgers(
    plan: PublishPlan, ledgers: Mapping[str, PublishLedger]
) -> PublishPlan:
    return dataclasses.replace(plan, ledgers=ledgers)
