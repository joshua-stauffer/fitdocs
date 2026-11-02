"""The publish engine's posting run (publish-core task 6.3).

Requirements 1.6, 2.7, 3.8, 8.1-8.8, 10.3-10.5, 12.2, 12.5, 12.7 and 12.8, over
a temporary data root with real pages and ledgers on disk and the scripted
publishing connector behind ``open_target``. Ledger state is read back from
the ledger FILE (``load_ledgers``), never from an object the engine holds, and
expected posts and region text are literals. Ids come from the ``_id``
helper and digests from ``post_digest`` over literal posts (that function is
pinned by the compose tests), never from anything the engine computed.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

import fitdocs.publish.engine as engine_module
from fitdocs.connectors.protocol import ConnectorSession
from fitdocs.docmerge import RegionError, extract_regions, region_block
from fitdocs.layout import publish_ledger_path
from fitdocs.publish.engine import PublishReport, ResultRow, run_publish
from fitdocs.publish.ledger import (
    PublicationRecord,
    PublishLedger,
    load_ledgers,
    save_ledger,
    workout_page_key,
)
from fitdocs.publish.links import PublishedRegionMissing
from fitdocs.publish.outcomes import STOPPING_CODES, TARGET_CODES, PublishCode
from fitdocs.publish.request import Post, PublishRequest, PublishResult
from tests.publish.conftest import ScriptedPublisher
from tests.publish.test_engine import (
    CLOCK,
    CONNECTOR,
    CURRENT_VERSION,
    DEFAULT_POST,
    LINK,
    OTHER_POST,
    SHA_A,
    SHA_B,
    SHA_C,
    Env,
    _digest,
    _fm,
    _id,
    _record,
    _ref,
    _settings,
    _snapshot,
    replace_ledgers,
)

LINK_B = "https://example.org/b/2"
TARGETS = {"alpha": CONNECTOR, "beta": CONNECTOR}
LABEL = "Scripted post"
STOPPING_CODES_PINNED = [
    PublishCode.NOT_CONNECTED,
    PublishCode.AUTH_REJECTED,
    PublishCode.PERMISSION_DENIED,
    PublishCode.RATE_LIMITED,
    PublishCode.UNAVAILABLE,
]


@pytest.fixture
def env(tmp_path: Path) -> Env:
    root = tmp_path / "data"
    root.mkdir()
    return Env(root)


class ReadingPublisher(ScriptedPublisher):
    """Reads every ledger FILE at the moment of each call, before answering."""

    def __init__(self, root: Path, **options: object) -> None:
        super().__init__(**options)  # type: ignore[arg-type]
        self.root = root
        self.seen: list[dict[str, PublishLedger]] = []

    def publish(
        self, session: ConnectorSession, request: PublishRequest
    ) -> PublishResult:
        self.seen.append(load_ledgers(self.root, TARGETS))
        return super().publish(session, request)


def _ledgers(env: Env) -> dict[str, PublishLedger]:
    return load_ledgers(env.root, TARGETS)


def _record_on_disk(env: Env, target: str, sha: str) -> PublicationRecord:
    (record,) = _ledgers(env)[target].matching([sha])
    return record


def _region(path: Path) -> str:
    return extract_regions(path.read_text(encoding="utf-8"))["published"]


def _post_run(env: Env, **plan_options: object) -> PublishReport:
    """A posting run over the ledgers as they are on disk now."""
    plan = env.plan(posting=True, **plan_options)  # type: ignore[arg-type]
    return env.run(replace_ledgers(plan, _ledgers(env)))


def _script(publisher: ScriptedPublisher, *outcomes: object) -> None:
    publisher.publish_script.extend(outcomes)


def _posted(link: str | None = LINK) -> PublishResult:
    return PublishResult(PublishCode.POSTED, link)


def _pairs(report: PublishReport) -> list[tuple[str, str | None, PublishCode]]:
    return [(row.page, row.target, row.code) for row in report.rows]


def _linked(label: str, link: str) -> str:
    return f"Published: [{label}]({link})"


# ------------------------------------------------------------- one first post


class TestFirstPost:
    def test_posts_records_and_links_without_touching_the_other_regions(
        self, env: Env
    ) -> None:
        page = env.write("a.md", post="My title\n\nMy words")
        before = page.read_text(encoding="utf-8")
        assert _region(page) == ""
        _script(env.spy.publisher, _posted())
        report = _post_run(env, considered=("alpha",))
        assert report.posting is True
        assert report.rows == (
            ResultRow(
                page="workouts/a.md",
                target="alpha",
                code=PublishCode.POSTED,
                decision=PublishCode.WOULD_POST,
                post=Post("My title", "My words"),
                link=LINK,
                link_refused=False,
                detail=None,
            ),
        )
        (call,) = env.spy.publisher.publish_calls
        request = call[1]
        assert request.publication_id == _id(901)
        assert request.post == Post("My title", "My words")
        assert request.recorded_link is None
        assert request.subject.source_shas == (SHA_A,)
        assert _record_on_disk(env, "alpha", SHA_A) == PublicationRecord(
            page=workout_page_key(SHA_A),
            publication_id=_id(901),
            digest=_digest(Post("My title", "My words")),
            code="posted",
            at=CLOCK,
            link=LINK,
            label=LABEL,
        )
        expected = before.replace(
            region_block("published", ""),
            region_block("published", _linked(LABEL, LINK)),
        )
        assert expected != before
        assert page.read_text(encoding="utf-8") == expected
        assert env.spy.mints == 1
        assert env.spy.clock_calls == 1

    def test_a_new_record_is_keyed_by_the_base_file_the_last_source(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(sources=[_ref(SHA_A), _ref(SHA_B)]))
        _script(env.spy.publisher, _posted())
        _post_run(env, considered=("alpha",))
        (record,) = _ledgers(env)["alpha"].records
        assert record.page == workout_page_key(SHA_B)

    def test_a_page_recording_no_archived_file_is_not_sent(self, env: Env) -> None:
        env.write("a.md", _fm(sources=[]))
        report = _post_run(env, considered=("alpha",))
        assert _pairs(report) == [
            ("workouts/a.md", "alpha", PublishCode.ACTIVITY_FACTS_MISSING)
        ]
        assert env.spy.opened == []
        assert env.spy.mints == 0
        assert not publish_ledger_path(env.root, "alpha").exists()

    def test_a_dry_run_refuses_a_page_recording_no_archived_file_alike(
        self, env: Env
    ) -> None:
        env.write("a.md", _fm(sources=[]))
        before = _snapshot(env.root)
        report = env.run(env.plan(considered=("alpha",)))
        assert _pairs(report) == [
            ("workouts/a.md", "alpha", PublishCode.ACTIVITY_FACTS_MISSING)
        ]
        assert _snapshot(env.root) == before

    def test_the_target_opens_once_for_all_its_pairs(self, env: Env) -> None:
        env.write("a.md")
        env.write("b.md", _fm(sources=[_ref(SHA_B)]))
        _script(env.spy.publisher, _posted(LINK), _posted(LINK_B))
        _post_run(env, considered=("alpha",))
        assert env.spy.opened == ["alpha"]
        assert len(env.spy.publisher.publish_calls) == 2


# ----------------------------------------------------------- second run, edits


class TestSecondRun:
    def test_a_second_posting_run_sends_nothing_and_changes_nothing(
        self, env: Env
    ) -> None:
        env.write("a.md")
        _script(env.spy.publisher, _posted())
        first = _post_run(env, considered=("alpha",))
        assert first.rows[0].code is PublishCode.POSTED
        assert _region(env.root / "workouts" / "a.md") == _linked(LABEL, LINK)
        ledger_file = publish_ledger_path(env.root, "alpha")
        assert ledger_file.is_file()
        before = _snapshot(env.root)
        report = _post_run(env, considered=("alpha",))
        assert report.rows == (
            ResultRow(
                page="workouts/a.md",
                target="alpha",
                code=PublishCode.UNCHANGED,
                decision=PublishCode.UNCHANGED,
                post=None,
                link=None,
                link_refused=False,
                detail=None,
            ),
        )
        assert len(env.spy.publisher.publish_calls) == 1
        assert env.spy.opened == ["alpha"]
        assert env.spy.mints == 1
        assert env.spy.clock_calls == 1
        assert _snapshot(env.root) == before

    def test_an_edited_post_region_is_an_update_with_the_same_id_and_link_kept(
        self, env: Env
    ) -> None:
        page = env.write("a.md", post="First\n\nOne")
        _script(env.spy.publisher, _posted(LINK), _posted(None))
        _post_run(env, considered=("alpha",))
        first = _record_on_disk(env, "alpha", SHA_A)
        assert first.digest == _digest(Post("First", "One"))
        page.write_text(
            page.read_text(encoding="utf-8").replace(
                region_block("post", "First\n\nOne"),
                region_block("post", "Second\n\nTwo"),
            ),
            encoding="utf-8",
        )
        report = _post_run(env, considered=("alpha",))
        (row,) = report.rows
        assert (row.code, row.decision) == (
            PublishCode.POSTED,
            PublishCode.WOULD_UPDATE,
        )
        assert row.post == Post("Second", "Two")
        assert row.link is None
        request = env.spy.publisher.publish_calls[1][1]
        assert request.publication_id == _id(901)
        assert request.recorded_link == LINK
        assert request.post == Post("Second", "Two")
        second = _record_on_disk(env, "alpha", SHA_A)
        assert second.publication_id == _id(901)
        assert second.digest == _digest(Post("Second", "Two"))
        assert second.digest != first.digest
        # The update answered without a link: the recorded one stands.
        assert (second.link, second.label) == (LINK, LABEL)
        assert _region(page) == _linked(LABEL, LINK)
        assert env.spy.mints == 1

    def test_an_edited_template_is_an_update(self, env: Env) -> None:
        env.write("a.md")
        _script(env.spy.publisher, _posted(), _posted())
        _post_run(env, considered=("alpha",))
        settings = _settings(("alpha", "beta"), {"publish": {"title": "T {title}"}})
        report = _post_run(env, considered=("alpha",), settings=settings)
        (row,) = report.rows
        assert row.decision is PublishCode.WOULD_UPDATE
        assert row.post == Post("T Morning Run", DEFAULT_POST.description)
        assert env.spy.publisher.publish_calls[1][1].post == row.post
        assert _record_on_disk(env, "alpha", SHA_A).digest == _digest(row.post)

    def test_a_new_link_replaces_the_recorded_one(self, env: Env) -> None:
        page = env.write("a.md")
        old = _record(
            SHA_A, digest=_digest(OTHER_POST), number=7, link=LINK, label="Old label"
        )
        _write_ledger(env, {"alpha": [old]})
        _script(env.spy.publisher, _posted(LINK_B))
        _post_run(env, considered=("alpha",))
        record = _record_on_disk(env, "alpha", SHA_A)
        assert (record.link, record.label) == (LINK_B, LABEL)
        assert _region(page) == _linked(LABEL, LINK_B)


def _write_ledger(
    env: Env, records: dict[str, list[PublicationRecord]]
) -> dict[str, PublishLedger]:
    """Put ledgers on disk the way a previous run left them."""
    ledgers = {
        name: PublishLedger(name, CONNECTOR, tuple(records.get(name, ())))
        for name in TARGETS
    }
    for ledger in ledgers.values():
        save_ledger(env.root, ledger)
    return ledgers


# ----------------------------------------------- ids and saves around a request


class TestIdsAndSaves:
    def test_the_id_is_in_the_ledger_file_when_the_target_is_called(
        self, env: Env
    ) -> None:
        reading = ReadingPublisher(env.root)
        env.spy.publisher = reading
        env.write("a.md")
        _script(reading, _posted())
        _post_run(env, considered=("alpha",))
        (during,) = reading.seen
        # Before the call the file holds the id and no outcome at all.
        assert during["alpha"].records == (
            PublicationRecord(page=workout_page_key(SHA_A), publication_id=_id(901)),
        )
        assert _record_on_disk(env, "alpha", SHA_A).code == "posted"

    def test_each_outcome_is_on_disk_before_the_next_request_same_target(
        self, env: Env
    ) -> None:
        reading = ReadingPublisher(env.root)
        env.spy.publisher = reading
        env.write("a.md")
        env.write("b.md", _fm(sources=[_ref(SHA_B)]))
        _script(reading, _posted(LINK), _posted(LINK_B))
        _post_run(env, considered=("alpha",))
        first, second = reading.seen
        assert first["alpha"].records == (
            PublicationRecord(page=workout_page_key(SHA_A), publication_id=_id(901)),
        )
        assert second["alpha"].records == (
            PublicationRecord(
                page=workout_page_key(SHA_A),
                publication_id=_id(901),
                digest=_digest(DEFAULT_POST),
                code="posted",
                at=CLOCK,
                link=LINK,
                label=LABEL,
            ),
            PublicationRecord(page=workout_page_key(SHA_B), publication_id=_id(902)),
        )

    def test_a_targets_outcome_is_on_disk_before_another_targets_request(
        self, env: Env
    ) -> None:
        reading = ReadingPublisher(env.root)
        env.spy.publishers["beta"] = reading
        env.write("a.md", _fm(publish=["alpha", "beta"]))
        _script(env.spy.publisher, _posted(LINK))
        _script(reading, _posted(LINK_B))
        _post_run(env)
        (during,) = reading.seen
        (alpha,) = during["alpha"].records
        assert (alpha.code, alpha.digest, alpha.link) == (
            "posted",
            _digest(DEFAULT_POST),
            LINK,
        )
        assert during["beta"].records == (
            PublicationRecord(page=workout_page_key(SHA_A), publication_id=_id(902)),
        )

    def test_an_interrupted_attempts_id_is_reused_by_the_next_run(
        self, env: Env
    ) -> None:
        env.write("a.md")
        _script(env.spy.publisher, KeyboardInterrupt())
        with pytest.raises(KeyboardInterrupt):
            _post_run(env, considered=("alpha",))
        interrupted = _record_on_disk(env, "alpha", SHA_A)
        assert interrupted == PublicationRecord(
            page=workout_page_key(SHA_A), publication_id=_id(901)
        )
        _script(env.spy.publisher, _posted())
        report = _post_run(env, considered=("alpha",))
        assert report.rows[0].decision is PublishCode.WOULD_POST
        assert env.spy.publisher.publish_calls[1][1].publication_id == _id(901)
        assert env.spy.mints == 1
        assert _record_on_disk(env, "alpha", SHA_A).publication_id == _id(901)

    def test_the_outcome_is_on_disk_before_the_region_is_written(
        self, env: Env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env.write("a.md")
        _script(env.spy.publisher, _posted())

        def interrupt(*_args: object, **_kwargs: object) -> object:
            raise KeyboardInterrupt

        monkeypatch.setattr(engine_module, "write_bytes_if_changed", interrupt)
        with pytest.raises(KeyboardInterrupt):
            _post_run(env, considered=("alpha",))
        record = _record_on_disk(env, "alpha", SHA_A)
        assert (record.code, record.digest, record.link) == (
            "posted",
            _digest(DEFAULT_POST),
            LINK,
        )

    def test_the_time_is_read_after_the_answer_not_before_the_request(
        self, env: Env
    ) -> None:
        reads: list[datetime] = []
        before_call: list[int] = []

        def clock() -> datetime:
            reads.append(datetime(2026, 11, 1, 10, len(reads), tzinfo=CLOCK.tzinfo))
            return reads[-1]

        class Counting(ScriptedPublisher):
            def publish(
                self, session: ConnectorSession, request: PublishRequest
            ) -> PublishResult:
                before_call.append(len(reads))
                return super().publish(session, request)

        counting = Counting()
        env.spy.publisher = counting
        env.write("a.md")
        _script(counting, _posted())
        run_publish(
            env.plan(posting=True, considered=("alpha",)),
            open_target=env.spy.open_target,
            now=clock,
            mint_id=env.spy.mint_id,
        )
        assert before_call == [0]
        assert len(reads) == 1
        assert _record_on_disk(env, "alpha", SHA_A).at == reads[0]

    def test_an_id_already_recorded_is_handed_unchanged(self, env: Env) -> None:
        env.write("a.md")
        _write_ledger(
            env,
            {
                "alpha": [
                    PublicationRecord(
                        page=workout_page_key(SHA_A), publication_id=_id(7)
                    )
                ]
            },
        )
        _script(env.spy.publisher, _posted())
        _post_run(env, considered=("alpha",))
        assert env.spy.publisher.publish_calls[0][1].publication_id == _id(7)
        assert env.spy.mints == 0

    def test_ids_differ_per_page_and_per_target(self, env: Env) -> None:
        env.write("a.md", _fm(publish=["alpha", "beta"]))
        env.write("b.md", _fm(sources=[_ref(SHA_B)], publish=["alpha", "beta"]))
        beta = ScriptedPublisher()
        env.spy.publishers["beta"] = beta
        _script(env.spy.publisher, _posted(), _posted())
        _script(beta, _posted(), _posted())
        _post_run(env)
        ids = [
            record.publication_id
            for ledger in _ledgers(env).values()
            for record in ledger.records
        ]
        assert sorted(ids) == [_id(901), _id(902), _id(903), _id(904)]


# --------------------------------------------------------- unconfirmed results


class TestUnconfirmed:
    def test_an_unconfirmed_first_post_is_not_landed_and_is_sent_again(
        self, env: Env
    ) -> None:
        env.write("a.md")
        _script(env.spy.publisher, PublishResult(PublishCode.UNCONFIRMED))
        report = _post_run(env, considered=("alpha",))
        (row,) = report.rows
        assert (row.code, row.decision) == (
            PublishCode.UNCONFIRMED,
            PublishCode.WOULD_POST,
        )
        assert report.failed is True
        record = _record_on_disk(env, "alpha", SHA_A)
        assert (record.digest, record.code, record.at) == (None, "unconfirmed", CLOCK)
        assert _region(env.root / "workouts" / "a.md") == ""
        _script(env.spy.publisher, _posted())
        again = _post_run(env, considered=("alpha",))
        assert again.rows[0].decision is PublishCode.WOULD_POST
        assert again.rows[0].code is PublishCode.POSTED
        assert env.spy.publisher.publish_calls[1][1].publication_id == _id(901)

    def test_an_unconfirmed_update_keeps_the_earlier_landed_digest(
        self, env: Env
    ) -> None:
        env.write("a.md")
        _write_ledger(
            env, {"alpha": [_record(SHA_A, digest=_digest(OTHER_POST), number=7)]}
        )
        _script(env.spy.publisher, PublishResult(PublishCode.UNCONFIRMED))
        _post_run(env, considered=("alpha",))
        record = _record_on_disk(env, "alpha", SHA_A)
        assert (record.digest, record.code) == (_digest(OTHER_POST), "unconfirmed")
        _script(env.spy.publisher, _posted())
        again = _post_run(env, considered=("alpha",))
        assert again.rows[0].decision is PublishCode.WOULD_UPDATE

    @pytest.mark.parametrize(
        "code",
        [PublishCode.RATE_LIMITED, PublishCode.UNCONFIRMED],
        ids=["rate limited", "unconfirmed"],
    )
    def test_a_non_landed_update_keeps_the_recorded_link_and_digest(
        self, env: Env, code: PublishCode
    ) -> None:
        page = env.write("a.md")
        _write_ledger(
            env,
            {
                "alpha": [
                    _record(
                        SHA_A,
                        digest=_digest(OTHER_POST),
                        number=7,
                        link=LINK,
                        label=LABEL,
                    )
                ]
            },
        )
        _script(env.spy.publisher, PublishResult(code))
        report = _post_run(env, considered=("alpha",))
        assert report.rows[0].decision is PublishCode.WOULD_UPDATE
        assert report.rows[0].code is code
        record = _record_on_disk(env, "alpha", SHA_A)
        assert (record.code, record.digest) == (code.value, _digest(OTHER_POST))
        assert (record.link, record.label) == (LINK, LABEL)
        assert _region(page) == _linked(LABEL, LINK)

    def test_a_target_failure_is_recorded_without_stopping_the_target(
        self, env: Env
    ) -> None:
        env.write("a.md")
        env.write("b.md", _fm(sources=[_ref(SHA_B)]))
        _script(
            env.spy.publisher, RuntimeError("SENTINEL-service-text"), _posted(LINK_B)
        )
        report = _post_run(env, considered=("alpha",))
        written = publish_ledger_path(env.root, "alpha").read_text(encoding="utf-8")
        assert "SENTINEL" not in written + repr(report)
        assert [row.code for row in report.rows] == [
            PublishCode.TARGET_ERROR,
            PublishCode.POSTED,
        ]
        record = _record_on_disk(env, "alpha", SHA_A)
        assert (record.code, record.digest, record.link) == ("target_error", None, None)

    def test_a_non_stopping_failure_lets_the_next_pair_go(self, env: Env) -> None:
        env.write("a.md")
        env.write("b.md", _fm(sources=[_ref(SHA_B)]))
        _script(env.spy.publisher, PublishResult(PublishCode.REJECTED), _posted())
        report = _post_run(env, considered=("alpha",))
        assert [row.code for row in report.rows] == [
            PublishCode.REJECTED,
            PublishCode.POSTED,
        ]


# ------------------------------------------------------------- stopping codes


class TestStopping:
    def _two_pages_two_targets(self, env: Env) -> None:
        env.write("a.md", _fm(publish=["alpha", "beta"]))
        env.write("b.md", _fm(sources=[_ref(SHA_B)], publish=["alpha", "beta"]))

    def test_the_stopping_codes_are_the_ones_pinned_here(self) -> None:
        assert frozenset(STOPPING_CODES_PINNED) == STOPPING_CODES & TARGET_CODES

    @pytest.mark.parametrize("code", STOPPING_CODES_PINNED, ids=lambda c: c.value)
    def test_a_stopping_answer_stops_that_target_while_the_second_continues(
        self, env: Env, code: PublishCode
    ) -> None:
        self._two_pages_two_targets(env)
        beta = ScriptedPublisher()
        env.spy.publishers["beta"] = beta
        _script(env.spy.publisher, PublishResult(code))
        _script(beta, _posted(LINK), _posted(LINK_B))
        report = _post_run(env)
        assert _pairs(report) == [
            ("workouts/a.md", "alpha", code),
            ("workouts/a.md", "beta", PublishCode.POSTED),
            ("workouts/b.md", "alpha", PublishCode.NOT_ATTEMPTED),
            ("workouts/b.md", "beta", PublishCode.POSTED),
        ]
        skipped = report.rows[2]
        assert skipped.decision is PublishCode.WOULD_POST
        assert skipped.post == DEFAULT_POST
        assert (skipped.link, skipped.link_refused) == (None, False)
        assert len(env.spy.publisher.publish_calls) == 1
        assert len(beta.publish_calls) == 2
        # The skipped pair left no record: only the attempted page has one.
        (alpha_record,) = _ledgers(env)["alpha"].records
        assert alpha_record.page == workout_page_key(SHA_A)
        assert (alpha_record.code, alpha_record.digest) == (code.value, None)
        assert len(_ledgers(env)["beta"].records) == 2
        assert env.spy.mints == 3
        assert env.spy.clock_calls == 3
        assert report.failed is True

    @pytest.mark.parametrize(
        "code",
        [PublishCode.NOT_CONNECTED, PublishCode.CREDENTIALS_UNREADABLE],
        ids=["not connected", "credentials unreadable"],
    )
    def test_a_target_that_fails_to_open_gives_every_one_of_its_pairs_the_code(
        self, env: Env, code: PublishCode
    ) -> None:
        self._two_pages_two_targets(env)
        beta = ScriptedPublisher()
        env.spy.publishers["beta"] = beta
        env.spy.refuse["alpha"] = code
        _script(beta, _posted(LINK), _posted(LINK_B))
        report = _post_run(env)
        assert _pairs(report) == [
            ("workouts/a.md", "alpha", code),
            ("workouts/a.md", "beta", PublishCode.POSTED),
            ("workouts/b.md", "alpha", code),
            ("workouts/b.md", "beta", PublishCode.POSTED),
        ]
        # Every pair of the unopened target keeps its decision and its post.
        alpha_rows = [row for row in report.rows if row.target == "alpha"]
        assert [(row.decision, row.post) for row in alpha_rows] == [
            (PublishCode.WOULD_POST, DEFAULT_POST),
            (PublishCode.WOULD_POST, DEFAULT_POST),
        ]
        assert env.spy.opened == ["alpha", "beta"]
        assert env.spy.publisher.publish_calls == []
        assert not publish_ledger_path(env.root, "alpha").exists()
        assert env.spy.mints == 2

    def test_unreadable_credentials_are_reported_for_the_pair(self, env: Env) -> None:
        env.write("a.md")
        env.spy.refuse["alpha"] = PublishCode.CREDENTIALS_UNREADABLE
        report = _post_run(env, considered=("alpha",))
        assert _pairs(report) == [
            ("workouts/a.md", "alpha", PublishCode.CREDENTIALS_UNREADABLE)
        ]


# ---------------------------------------------------------- published region


class TestPublishedRegion:
    def test_links_from_two_targets_appear_in_target_name_order(self, env: Env) -> None:
        page = env.write("a.md", _fm(publish=["alpha", "beta"]))
        env.spy.publishers["alpha"] = ScriptedPublisher(link_label="Alpha post")
        env.spy.publishers["beta"] = ScriptedPublisher(link_label="Beta post")
        _script(env.spy.publishers["alpha"], _posted(LINK))
        _script(env.spy.publishers["beta"], _posted(LINK_B))
        # The plan lists the ledgers beta first, so insertion order is not name order.
        plan = env.plan(configured=("beta", "alpha"), posting=True)
        env.run(plan)
        assert _region(page) == (
            f"Published: [Alpha post]({LINK}) · [Beta post]({LINK_B})"
        )

    def test_a_hand_edit_is_replaced_and_nothing_is_sent(self, env: Env) -> None:
        page = env.write("a.md", published="my own words")
        _write_ledger(
            env,
            {
                "alpha": [
                    PublicationRecord(
                        page=workout_page_key(SHA_A),
                        publication_id=_id(7),
                        digest=_digest(DEFAULT_POST),
                        code="posted",
                        at=CLOCK,
                        link=LINK,
                        label=LABEL,
                    )
                ]
            },
        )
        report = _post_run(env, considered=("alpha",))
        assert report.rows[0].code is PublishCode.UNCHANGED
        assert env.spy.opened == []
        assert _region(page) == _linked(LABEL, LINK)

    def test_a_region_with_no_recorded_link_is_emptied(self, env: Env) -> None:
        page = env.write("a.md", _fm(publish=None), published="my own words")
        report = _post_run(env, considered=("alpha",))
        assert report.rows == ()
        assert _region(page) == ""

    def test_a_record_without_a_link_adds_nothing_to_the_region(self, env: Env) -> None:
        page = env.write("a.md", _fm(publish=["alpha", "beta"]))
        _write_ledger(
            env,
            {
                "alpha": [_record(SHA_A, digest=_digest(DEFAULT_POST), number=1)],
                "beta": [
                    PublicationRecord(
                        page=workout_page_key(SHA_A),
                        publication_id=_id(2),
                        digest=_digest(DEFAULT_POST),
                        code="posted",
                        at=CLOCK,
                        link=LINK_B,
                        label=LABEL,
                    )
                ],
            },
        )
        _post_run(env)
        assert _region(page) == _linked(LABEL, LINK_B)

    def test_a_page_that_stopped_naming_a_target_keeps_its_link(self, env: Env) -> None:
        page = env.write("a.md", _fm(publish="beta"))
        env.spy.publishers["alpha"] = ScriptedPublisher(link_label="Alpha post")
        env.spy.publishers["beta"] = ScriptedPublisher(link_label="Beta post")
        _write_ledger(
            env,
            {
                "alpha": [
                    PublicationRecord(
                        page=workout_page_key(SHA_A),
                        publication_id=_id(7),
                        digest=_digest(DEFAULT_POST),
                        code="posted",
                        at=CLOCK,
                        link=LINK,
                        label="Alpha post",
                    )
                ]
            },
        )
        _script(env.spy.publishers["beta"], _posted(LINK_B))
        report = _post_run(env)
        assert _pairs(report) == [("workouts/a.md", "beta", PublishCode.POSTED)]
        assert env.spy.publishers["alpha"].publish_calls == []
        assert "alpha" not in env.spy.opened
        assert _region(page) == (
            f"Published: [Alpha post]({LINK}) · [Beta post]({LINK_B})"
        )
        assert _record_on_disk(env, "alpha", SHA_A).publication_id == _id(7)

    def test_a_link_of_a_target_the_run_does_not_consider_stays_beside_a_new_one(
        self, env: Env
    ) -> None:
        # The page opts in to both targets; the run considers beta only, so
        # alpha's recorded link is kept by the refresh, not by the decision.
        page = env.write("a.md", _fm(publish=["alpha", "beta"]), published="stale")
        env.spy.publishers["alpha"] = ScriptedPublisher(link_label="Alpha post")
        env.spy.publishers["beta"] = ScriptedPublisher(link_label="Beta post")
        _write_ledger(
            env,
            {
                "alpha": [
                    _record(
                        SHA_A,
                        digest=_digest(DEFAULT_POST),
                        number=7,
                        link=LINK,
                        label="Alpha post",
                    )
                ]
            },
        )
        _script(env.spy.publishers["beta"], _posted(LINK_B))
        report = _post_run(env, considered=("beta",))
        assert _pairs(report) == [("workouts/a.md", "beta", PublishCode.POSTED)]
        assert env.spy.publishers["alpha"].publish_calls == []
        assert _region(page) == (
            f"Published: [Alpha post]({LINK}) · [Beta post]({LINK_B})"
        )

    @pytest.mark.parametrize(
        "publish",
        [None, [], "alpha"],
        ids=["no key", "empty list", "other target"],
    )
    def test_the_region_is_refreshed_whatever_the_pages_opt_in(
        self, env: Env, publish: object
    ) -> None:
        fm = _fm(publish=publish)
        if publish == []:
            fm["publish"] = []
        page = env.write("a.md", fm, published="stale")
        _write_ledger(
            env,
            {
                "beta": [
                    PublicationRecord(
                        page=workout_page_key(SHA_A),
                        publication_id=_id(7),
                        digest=_digest(DEFAULT_POST),
                        code="posted",
                        at=CLOCK,
                        link=LINK_B,
                        label=LABEL,
                    )
                ]
            },
        )
        # The page never opts in to a considered target, yet beta's link shows.
        _post_run(env, considered=("beta",) if publish == "alpha" else ("alpha",))
        assert _region(page) == _linked(LABEL, LINK_B)

    @pytest.mark.parametrize(
        "version", [CURRENT_VERSION - 1, CURRENT_VERSION + 1], ids=["older", "newer"]
    )
    def test_an_older_or_newer_page_is_never_written(
        self, env: Env, version: int
    ) -> None:
        page = env.write("a.md", _fm(doc_version=version), published="stale")
        _write_ledger(
            env,
            {"alpha": [_record(SHA_A, digest=None, number=1, link=LINK, label=LABEL)]},
        )
        before = _snapshot(env.root)
        report = _post_run(env)
        assert [row.code for row in report.rows] == [
            PublishCode.PAGE_OUT_OF_DATE
            if version < CURRENT_VERSION
            else PublishCode.PAGE_NEWER
        ]
        assert _region(page) == "stale"
        assert _snapshot(env.root) == before

    def test_a_damaged_page_is_reported_once_and_never_written(self, env: Env) -> None:
        page = env.write("a.md", body="# Run\n\nno regions here\n")
        before = page.read_bytes()
        report = _post_run(env, considered=("alpha",))
        assert _pairs(report) == [("workouts/a.md", "alpha", PublishCode.PAGE_DAMAGED)]
        assert page.read_bytes() == before

    def test_an_unreadable_named_page_is_reported_and_nothing_else_happens(
        self, env: Env
    ) -> None:
        page = env.write("a.md")
        page.write_bytes(b"---\n\xff\xfe\n---\n")
        report = _post_run(env, pages=env.pages("a.md"))
        assert _pairs(report) == [("workouts/a.md", None, PublishCode.PAGE_UNREADABLE)]
        assert page.read_bytes() == b"---\n\xff\xfe\n---\n"

    def test_a_page_without_sport_or_start_still_gets_its_region_refreshed(
        self, env: Env
    ) -> None:
        page = env.write("a.md", _fm(start_time=None), published="stale")
        _write_ledger(
            env,
            {
                "alpha": [
                    _record(
                        SHA_A,
                        digest=_digest(DEFAULT_POST),
                        number=1,
                        link=LINK,
                        label=LABEL,
                    )
                ]
            },
        )
        report = _post_run(env, considered=("alpha",))
        assert _pairs(report) == [
            ("workouts/a.md", "alpha", PublishCode.ACTIVITY_FACTS_MISSING)
        ]
        assert env.spy.opened == []
        assert _region(page) == _linked(LABEL, LINK)

    def test_a_dry_run_never_writes_the_region(self, env: Env) -> None:
        page = env.write("a.md", published="stale")
        _write_ledger(
            env,
            {
                "alpha": [
                    _record(
                        SHA_A,
                        digest=_digest(DEFAULT_POST),
                        number=1,
                        link=LINK,
                        label=LABEL,
                    )
                ]
            },
        )
        before = _snapshot(env.root)
        report = env.run(env.plan(considered=("alpha",)))
        assert report.posting is False
        assert _snapshot(env.root) == before
        assert _region(page) == "stale"


class TestAmbiguousRecords:
    def test_two_matching_records_leave_the_page_alone(self, env: Env) -> None:
        page = env.write(
            "a.md", _fm(sources=[_ref(SHA_A), _ref(SHA_B)]), published="stale"
        )
        _write_ledger(
            env,
            {
                "alpha": [
                    _record(
                        SHA_A,
                        digest=_digest(DEFAULT_POST),
                        number=1,
                        link=LINK,
                        label=LABEL,
                    ),
                    _record(
                        SHA_B,
                        digest=_digest(DEFAULT_POST),
                        number=2,
                        link=LINK_B,
                        label=LABEL,
                    ),
                ]
            },
        )
        report = _post_run(env, considered=("alpha",))
        assert _pairs(report) == [
            ("workouts/a.md", "alpha", PublishCode.LEDGER_CONFLICT),
            ("workouts/a.md", None, PublishCode.PUBLISHED_NOT_WRITTEN),
        ]
        assert report.rows[1].detail == (
            "more than one alpha ledger record matches this page, "
            "so its published region was left as it is"
        )
        assert report.failed is True
        assert _region(page) == "stale"

    def test_pages_sharing_a_would_be_key_are_both_refused_and_nothing_is_posted(
        self, env: Env
    ) -> None:
        a = env.write("a.md")
        b = env.write("b.md")
        report = _post_run(env, considered=("alpha",))
        assert _pairs(report) == [
            ("workouts/a.md", "alpha", PublishCode.LEDGER_CONFLICT),
            ("workouts/b.md", "alpha", PublishCode.LEDGER_CONFLICT),
        ]
        assert report.rows[0].detail == (
            "the ledger key for this page is also recorded by workouts/b.md"
        )
        assert report.rows[1].detail == (
            "the ledger key for this page is also recorded by workouts/a.md"
        )
        assert env.spy.publisher.publish_calls == []
        assert env.spy.opened == []
        assert _region(a) == ""
        assert _region(b) == ""

    def test_a_dry_run_decides_the_shared_key_exactly_as_a_posting_run(
        self, env: Env
    ) -> None:
        env.write("a.md")
        env.write("b.md")
        dry = env.run(env.plan(considered=("alpha",)))
        posting = _post_run(env, considered=("alpha",))
        assert dry.posting is False
        assert [(r.page, r.target, r.code, r.detail) for r in dry.rows] == [
            (r.page, r.target, r.code, r.detail) for r in posting.rows
        ]
        assert {r.code for r in dry.rows} == {PublishCode.LEDGER_CONFLICT}

    def test_the_check_uses_the_digest_a_post_would_mint_not_the_first(
        self, env: Env
    ) -> None:
        # Only the first digest is shared; the key a post mints is the last.
        env.write("a.md", _fm(sources=[_ref(SHA_A), _ref(SHA_B)]))
        env.write("b.md", _fm(sources=[_ref(SHA_A), _ref(SHA_C)]))
        _script(env.spy.publisher, _posted(), _posted(LINK_B))
        report = _post_run(env, considered=("alpha",))
        assert [r.code for r in report.rows] == [PublishCode.POSTED] * 2

    def test_two_linkless_records_still_leave_the_page_alone(self, env: Env) -> None:
        page = env.write(
            "a.md", _fm(sources=[_ref(SHA_A), _ref(SHA_B)]), published="stale"
        )
        _write_ledger(
            env,
            {
                "alpha": [
                    _record(SHA_A, digest=_digest(DEFAULT_POST), number=1),
                    _record(SHA_B, digest=_digest(DEFAULT_POST), number=2),
                ]
            },
        )
        report = _post_run(env, considered=("alpha",))
        assert _pairs(report) == [
            ("workouts/a.md", "alpha", PublishCode.LEDGER_CONFLICT),
            ("workouts/a.md", None, PublishCode.PUBLISHED_NOT_WRITTEN),
        ]
        assert report.rows[1].detail == (
            "more than one alpha ledger record matches this page, "
            "so its published region was left as it is"
        )
        assert _region(page) == "stale"

    def test_a_linkless_record_shared_by_two_pages_leaves_both_alone(
        self, env: Env
    ) -> None:
        a = env.write("a.md", published="stale")
        b = env.write("b.md", published="stale")
        _write_ledger(
            env,
            {"alpha": [_record(SHA_A, digest=_digest(DEFAULT_POST), number=1)]},
        )
        report = _post_run(env, considered=("alpha",))
        detail = (
            "the alpha ledger record for this page also matches another page, "
            "so its published region was left as it is"
        )
        assert [(r.page, r.target, r.code, r.detail) for r in report.rows] == [
            (
                "workouts/a.md",
                "alpha",
                PublishCode.LEDGER_CONFLICT,
                ("the ledger record also matches workouts/b.md"),
            ),
            ("workouts/a.md", None, PublishCode.PUBLISHED_NOT_WRITTEN, detail),
            (
                "workouts/b.md",
                "alpha",
                PublishCode.LEDGER_CONFLICT,
                ("the ledger record also matches workouts/a.md"),
            ),
            ("workouts/b.md", None, PublishCode.PUBLISHED_NOT_WRITTEN, detail),
        ]
        assert _region(a) == "stale"
        assert _region(b) == "stale"

    def test_a_shared_record_in_a_ledger_the_run_does_not_consider_still_counts(
        self, env: Env
    ) -> None:
        # Neither page opts in to anything and the run considers beta only, so
        # alpha is neither opted in to nor considered and no pair is decided;
        # alpha's one linked record, shared by both pages, still makes both
        # pages ambiguous.
        a = env.write("a.md", _fm(publish=None), published="stale")
        b = env.write("b.md", _fm(publish=None), published="stale")
        _write_ledger(
            env,
            {
                "alpha": [
                    _record(
                        SHA_A,
                        digest=_digest(DEFAULT_POST),
                        number=1,
                        link=LINK,
                        label=LABEL,
                    )
                ]
            },
        )
        report = _post_run(env, considered=("beta",))
        detail = (
            "the alpha ledger record for this page also matches another page, "
            "so its published region was left as it is"
        )
        assert [(r.page, r.target, r.code, r.detail) for r in report.rows] == [
            ("workouts/a.md", None, PublishCode.PUBLISHED_NOT_WRITTEN, detail),
            ("workouts/b.md", None, PublishCode.PUBLISHED_NOT_WRITTEN, detail),
        ]
        assert _region(a) == "stale"
        assert _region(b) == "stale"

    def test_ambiguity_in_a_ledger_the_run_does_not_consider_still_counts(
        self, env: Env
    ) -> None:
        # The page opts in to beta only and the run considers beta only, so
        # alpha is neither opted in to nor considered; its two records (both
        # with links) still make the page ambiguous.
        page = env.write(
            "a.md",
            _fm(sources=[_ref(SHA_A), _ref(SHA_B)], publish="beta"),
            published="stale",
        )
        _write_ledger(
            env,
            {
                "alpha": [
                    _record(
                        SHA_A,
                        digest=_digest(DEFAULT_POST),
                        number=1,
                        link=LINK,
                        label=LABEL,
                    ),
                    _record(
                        SHA_B,
                        digest=_digest(DEFAULT_POST),
                        number=2,
                        link=LINK_B,
                        label=LABEL,
                    ),
                ]
            },
        )
        _script(env.spy.publisher, _posted(LINK_B))
        report = _post_run(env, considered=("beta",))
        assert _pairs(report) == [
            ("workouts/a.md", "beta", PublishCode.POSTED),
            ("workouts/a.md", None, PublishCode.PUBLISHED_NOT_WRITTEN),
        ]
        assert report.rows[1].detail == (
            "more than one alpha ledger record matches this page, "
            "so its published region was left as it is"
        )
        assert _region(page) == "stale"


# ------------------------------------------------------------ refused links


class TestLinks:
    def test_a_link_that_is_not_https_is_not_kept_and_is_reported(
        self, env: Env
    ) -> None:
        page = env.write("a.md")
        _script(env.spy.publisher, _posted("http://example.org/x"))
        report = _post_run(env, considered=("alpha",))
        (row,) = report.rows
        assert (row.code, row.link, row.link_refused) == (
            PublishCode.POSTED,
            None,
            True,
        )
        record = _record_on_disk(env, "alpha", SHA_A)
        assert (record.code, record.link, record.label) == ("posted", None, None)
        assert record.digest == _digest(DEFAULT_POST)
        assert _region(page) == ""

    def test_a_label_that_cannot_be_written_drops_the_link(self, env: Env) -> None:
        page = env.write("a.md")
        env.spy.publisher = ScriptedPublisher(link_label="bad [label]")
        _script(env.spy.publisher, _posted())
        report = _post_run(env, considered=("alpha",))
        (row,) = report.rows
        assert (row.code, row.link, row.link_refused) == (
            PublishCode.POSTED,
            None,
            True,
        )
        record = _record_on_disk(env, "alpha", SHA_A)
        assert (record.link, record.label) == (None, None)
        assert _region(page) == ""

    def test_a_pair_that_offers_no_link_is_not_a_refusal(self, env: Env) -> None:
        env.write("a.md")
        _script(env.spy.publisher, _posted(None))
        (row,) = _post_run(env, considered=("alpha",)).rows
        assert (row.link, row.link_refused) == (None, False)


# ---------------------------------------------------------- failed rewrites


class TestFailedRewrite:
    @pytest.mark.parametrize(
        ("error", "detail"),
        [
            (PermissionError("secret path /x"), "PermissionError"),
            (RegionError("region trouble"), "region trouble"),
            (PublishedRegionMissing("no region"), "no region"),
        ],
        ids=["os", "region", "missing"],
    )
    def test_a_failed_rewrite_is_reported_and_the_outcomes_are_kept(
        self,
        env: Env,
        monkeypatch: pytest.MonkeyPatch,
        error: Exception,
        detail: str,
    ) -> None:
        page = env.write("a.md")
        before = page.read_bytes()
        _script(env.spy.publisher, _posted())

        def fail(*_args: object, **_kwargs: object) -> object:
            raise error

        target = (
            "write_bytes_if_changed"
            if isinstance(error, OSError)
            else "replace_published"
        )
        monkeypatch.setattr(engine_module, target, fail)
        report = _post_run(env, considered=("alpha",))
        assert [(row.target, row.code, row.detail) for row in report.rows] == [
            ("alpha", PublishCode.POSTED, None),
            (None, PublishCode.PUBLISHED_NOT_WRITTEN, detail),
        ]
        assert report.rows[1].page == "workouts/a.md"
        assert report.failed is True
        assert page.read_bytes() == before
        assert _record_on_disk(env, "alpha", SHA_A).digest == _digest(DEFAULT_POST)
        monkeypatch.undo()
        again = _post_run(env, considered=("alpha",))
        assert [row.code for row in again.rows] == [PublishCode.UNCHANGED]
        assert len(env.spy.publisher.publish_calls) == 1
        assert _region(page) == _linked(LABEL, LINK)

    def test_each_page_is_refreshed_right_after_its_own_pairs(
        self, env: Env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env.write("a.md")
        env.write("b.md", _fm(sources=[_ref(SHA_B)]))
        _script(env.spy.publisher, _posted(LINK), _posted(LINK_B))

        def fail(*_args: object, **_kwargs: object) -> object:
            raise PermissionError("x")

        monkeypatch.setattr(engine_module, "write_bytes_if_changed", fail)
        report = _post_run(env, considered=("alpha",))
        assert _pairs(report) == [
            ("workouts/a.md", "alpha", PublishCode.POSTED),
            ("workouts/a.md", None, PublishCode.PUBLISHED_NOT_WRITTEN),
            ("workouts/b.md", "alpha", PublishCode.POSTED),
            ("workouts/b.md", None, PublishCode.PUBLISHED_NOT_WRITTEN),
        ]
