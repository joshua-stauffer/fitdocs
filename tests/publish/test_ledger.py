"""The publish ledger (publish-core Req 10.3, 11.1-11.6, 11.8)."""

from __future__ import annotations

import dataclasses
import os
import tomllib
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from fitdocs.layout import OWNED_PATHS, PUBLISH_STATE_DIR, publish_ledger_path
from fitdocs.publish.ledger import (
    PUBLISH_LEDGER_VERSION,
    WORKOUT_PAGE_KIND,
    PublicationRecord,
    PublishLedger,
    PublishLedgerError,
    load_ledgers,
    save_ledger,
    workout_page_key,
)

SHA_A = "a" * 63 + "1"
SHA_B = "b" * 63 + "2"
SHA_C = "c" * 63 + "3"
SHA_D = "d" * 63 + "4"
ID_1 = "1" * 31 + "a"
ID_2 = "2" * 31 + "b"
ID_3 = "3" * 31 + "c"
AT = datetime(2026, 10, 31, 9, 15, 2, tzinfo=UTC)
LINK = "https://example.invalid/a/1"
OLD_NS = 1_600_000_000_000_000_000


def _landed(sha: str, pid: str) -> PublicationRecord:
    return PublicationRecord(
        page=workout_page_key(sha),
        publication_id=pid,
        digest=SHA_D,
        code="posted",
        at=AT,
        link=LINK,
        label="Example",
    )


def _ledger(*records: PublicationRecord, target: str = "t1") -> PublishLedger:
    return PublishLedger(target, "example", records)


def _write(root: Path, target: str, text: str) -> Path:
    path = publish_ledger_path(root, target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _file(*entries: str, version: str = "1", connector: str = '"example"') -> str:
    head = f"ledger_version = {version}\nconnector = {connector}\n"
    return head + "".join(f"\n[[publication]]\n{e}\n" for e in entries)


def _entry(**over: str | None) -> str:
    fields: dict[str, str | None] = {
        "page": f'"workout:{SHA_A}"',
        "id": f'"{ID_1}"',
    }
    fields.update(over)
    return "\n".join(f"{k} = {v}" for k, v in fields.items() if v is not None)


class TestKeysAndPaths:
    def test_workout_page_key(self) -> None:
        assert WORKOUT_PAGE_KIND == "workout"
        assert workout_page_key(SHA_A) == f"workout:{SHA_A}"
        assert workout_page_key(SHA_B) != workout_page_key(SHA_A)

    @pytest.mark.parametrize("bad", ["", "A" * 64, "a" * 63, "a" * 65, "a" * 63 + "\n"])
    def test_a_malformed_digest_has_no_page_key(self, bad: str) -> None:
        with pytest.raises(ValueError):
            workout_page_key(bad)

    def test_ledger_path_is_one_file_per_target_under_owned_state(self) -> None:
        root = Path("/data/root")
        one = publish_ledger_path(root, "alpha")
        two = publish_ledger_path(root, "beta")
        assert one == root / ".fitdocs" / "publish" / "alpha.toml"
        assert two == root / ".fitdocs" / "publish" / "beta.toml"
        assert PUBLISH_STATE_DIR == ".fitdocs/publish"
        assert ".fitdocs/" in OWNED_PATHS

    def test_version_is_one(self) -> None:
        assert PUBLISH_LEDGER_VERSION == 1


class TestRoundTripAndSave:
    def test_round_trip_unsorted_input_is_written_sorted(self, tmp_path: Path) -> None:
        # Page order (A, B, C) is the reverse of id order (3, 2, 1).
        interrupted = PublicationRecord(workout_page_key(SHA_B), ID_2)
        digest_only = PublicationRecord(workout_page_key(SHA_C), ID_1, digest=SHA_A)
        landed = _landed(SHA_A, ID_3)
        ledger = _ledger(digest_only, landed, interrupted)
        pages = [r.page for r in ledger.records]
        assert pages != sorted(pages)
        ids = [r.publication_id for r in sorted(ledger.records, key=lambda r: r.page)]
        assert ids == sorted(ids, reverse=True)

        assert save_ledger(tmp_path, ledger) is True
        path = publish_ledger_path(tmp_path, "t1")
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
        assert [e["page"] for e in parsed["publication"]] == [
            workout_page_key(SHA_A),
            workout_page_key(SHA_B),
            workout_page_key(SHA_C),
        ]
        assert parsed["ledger_version"] == 1
        assert parsed["connector"] == "example"

        loaded = load_ledgers(tmp_path, {"t1": "example"})["t1"]
        assert loaded == _ledger(landed, interrupted, digest_only)
        assert loaded.records[0].at == AT

    def test_absent_fields_are_omitted_not_written(self, tmp_path: Path) -> None:
        save_ledger(
            tmp_path,
            _ledger(
                PublicationRecord(workout_page_key(SHA_B), ID_2),
                PublicationRecord(workout_page_key(SHA_C), ID_3, digest=SHA_A),
                _landed(SHA_A, ID_1),
            ),
        )
        parsed = tomllib.loads(
            publish_ledger_path(tmp_path, "t1").read_text(encoding="utf-8")
        )
        keys = [set(e) for e in parsed["publication"]]
        assert keys == [
            {"page", "id", "digest", "code", "at", "link", "label"},
            {"page", "id"},
            {"page", "id", "digest"},
        ]

    def test_an_empty_ledger_saves_without_publication_entries(
        self, tmp_path: Path
    ) -> None:
        save_ledger(tmp_path, _ledger())
        parsed = tomllib.loads(
            publish_ledger_path(tmp_path, "t1").read_text(encoding="utf-8")
        )
        assert parsed == {"ledger_version": 1, "connector": "example"}
        assert load_ledgers(tmp_path, {"t1": "example"})["t1"] == _ledger()

    def test_the_time_is_saved_in_utc_and_read_back_equal(self, tmp_path: Path) -> None:
        zone = timezone(timedelta(hours=-7))
        local = datetime(2026, 10, 31, 2, 15, 2, tzinfo=zone)
        record = dataclasses.replace(_landed(SHA_A, ID_1), at=local)
        save_ledger(tmp_path, _ledger(record))
        text = publish_ledger_path(tmp_path, "t1").read_text(encoding="utf-8")
        assert "09:15:02" in text
        assert "02:15:02" not in text
        got = load_ledgers(tmp_path, {})["t1"].records[0].at
        assert got == local
        assert got is not None
        assert got.utcoffset() == timedelta(0)

    def test_an_unchanged_save_leaves_bytes_and_mtime_alone(
        self, tmp_path: Path
    ) -> None:
        ledger = _ledger(_landed(SHA_A, ID_1), _landed(SHA_B, ID_2))
        assert save_ledger(tmp_path, ledger) is True
        path = publish_ledger_path(tmp_path, "t1")
        os.utime(path, ns=(OLD_NS, OLD_NS))
        before = path.read_bytes()
        assert path.stat().st_mtime_ns == OLD_NS

        assert save_ledger(tmp_path, ledger) is False
        assert path.read_bytes() == before
        assert path.stat().st_mtime_ns == OLD_NS

        changed = ledger.with_record(_landed(SHA_C, ID_3))
        assert save_ledger(tmp_path, changed) is True
        assert path.read_bytes() != before
        assert path.stat().st_mtime_ns != OLD_NS

    def test_save_creates_the_directory_and_leaves_no_temp_file(
        self, tmp_path: Path
    ) -> None:
        assert not (tmp_path / ".fitdocs").exists()
        save_ledger(tmp_path, _ledger(_landed(SHA_A, ID_1)))
        names = sorted(p.name for p in (tmp_path / ".fitdocs" / "publish").iterdir())
        assert names == ["t1.toml"]

    def test_a_ledger_for_each_target_is_its_own_file(self, tmp_path: Path) -> None:
        save_ledger(tmp_path, _ledger(_landed(SHA_A, ID_1), target="one"))
        save_ledger(tmp_path, _ledger(_landed(SHA_A, ID_2), target="two"))
        loaded = load_ledgers(tmp_path, {})
        assert set(loaded) == {"one", "two"}
        assert loaded["one"].records[0].publication_id == ID_1
        assert loaded["two"].records[0].publication_id == ID_2

    def test_an_unknown_appended_code_is_kept_as_text(self, tmp_path: Path) -> None:
        record = dataclasses.replace(_landed(SHA_A, ID_1), code="appended_later_9")
        save_ledger(tmp_path, _ledger(record))
        got = load_ledgers(tmp_path, {"t1": "example"})["t1"].records[0]
        assert got.code == "appended_later_9"
        assert type(got.code) is str

    def test_only_the_seven_record_fields_exist(self) -> None:
        """Req 11.8: the record has no slot for anything a service returned
        beyond the permitted link and its label."""
        assert [f.name for f in dataclasses.fields(PublicationRecord)] == [
            "page",
            "publication_id",
            "digest",
            "code",
            "at",
            "link",
            "label",
        ]


class TestLoad:
    def test_reading_creates_nothing_and_a_missing_target_is_empty(
        self, tmp_path: Path
    ) -> None:
        loaded = load_ledgers(tmp_path, {"t1": "example", "t2": "other"})
        assert loaded == {
            "t1": PublishLedger("t1", "example", ()),
            "t2": PublishLedger("t2", "other", ()),
        }
        assert list(tmp_path.iterdir()) == []

    def test_an_existing_directory_is_not_added_to_by_reading(
        self, tmp_path: Path
    ) -> None:
        save_ledger(tmp_path, _ledger(_landed(SHA_A, ID_1), target="one"))
        directory = tmp_path / ".fitdocs" / "publish"
        load_ledgers(tmp_path, {"one": "example", "two": "example"})
        assert sorted(p.name for p in directory.iterdir()) == ["one.toml"]

    def test_every_file_present_is_read_even_if_not_configured(
        self, tmp_path: Path
    ) -> None:
        save_ledger(tmp_path, _ledger(_landed(SHA_A, ID_1), target="gone"))
        loaded = load_ledgers(tmp_path, {"t1": "example"})
        assert set(loaded) == {"gone", "t1"}
        assert loaded["gone"].connector == "example"

    def test_an_unconfigured_ledger_is_not_identity_checked_but_is_validated(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "gone", _file(connector='"anything"'))
        assert load_ledgers(tmp_path, {})["gone"].connector == "anything"
        _write(tmp_path, "gone", _file(_entry(page='"nope"')))
        with pytest.raises(PublishLedgerError):
            load_ledgers(tmp_path, {})

    def test_other_files_in_the_directory_are_ignored(self, tmp_path: Path) -> None:
        save_ledger(tmp_path, _ledger(target="one"))
        directory = tmp_path / ".fitdocs" / "publish"
        (directory / "notes.txt").write_text("x", encoding="utf-8")
        (directory / ".one.toml.abcd.tmp").write_text("x", encoding="utf-8")
        (directory / "sub.d").mkdir()
        assert set(load_ledgers(tmp_path, {})) == {"one"}

    def test_a_successful_read_of_a_non_canonical_file_touches_nothing(
        self, tmp_path: Path
    ) -> None:
        text = (
            "ledger_version   =   1\n\n\nconnector = 'example'\n"
            + _file(
                _entry(page=f'"workout:{SHA_C}"', id=f'"{ID_3}"'),
                _entry(page=f'"workout:{SHA_A}"', id=f'"{ID_1}"'),
            )[len(_file()) :]
        )
        path = _write(tmp_path, "t1", text)
        os.utime(path, ns=(OLD_NS, OLD_NS))
        before = path.read_bytes()
        siblings = sorted(p.name for p in path.parent.iterdir())

        loaded = load_ledgers(tmp_path, {"t1": "example"})["t1"]

        assert [r.page for r in loaded.records] == [
            workout_page_key(SHA_C),
            workout_page_key(SHA_A),
        ]
        other = tmp_path / "other"
        other.mkdir()
        save_ledger(other, loaded)
        # Precondition: saving this ledger would change the file.
        assert publish_ledger_path(other, "t1").read_bytes() != before
        assert path.read_bytes() == before
        assert path.stat().st_mtime_ns == OLD_NS
        assert sorted(p.name for p in path.parent.iterdir()) == siblings

    def test_matching_selects_by_source_digest(self) -> None:
        a, b, c = _landed(SHA_A, ID_1), _landed(SHA_B, ID_2), _landed(SHA_C, ID_3)
        ledger = _ledger(c, a, b)
        assert ledger.matching({SHA_A}) == (a,)
        assert ledger.matching([SHA_B, SHA_C]) == (c, b)
        # SHA_D is every record's digest field, but no record's page.
        assert ledger.matching({SHA_D}) == ()
        assert ledger.matching(()) == ()

    def test_with_record_replaces_by_page_and_adds_otherwise(self) -> None:
        a, b = _landed(SHA_A, ID_1), _landed(SHA_B, ID_2)
        ledger = _ledger(a)
        added = ledger.with_record(b)
        assert set(added.records) == {a, b}
        replaced = added.with_record(dataclasses.replace(a, code="rejected"))
        assert len(replaced.records) == 2
        assert [r.code for r in replaced.matching({SHA_A})] == ["rejected"]
        assert ledger.records == (a,)


_REFUSED: dict[str, str] = {
    "invalid_toml": "ledger_version = [\n",
    "not_utf8": "",  # the test writes raw bytes for this case
    "no_version": 'connector = "example"\n',
    "version_zero": _file(version="0"),
    "version_bool": _file(version="true"),
    "version_text": _file(version='"1"'),
    "newer_version": _file(version="2"),
    "newer_version_with_unknown_shape": 'ledger_version = 2\nweird = "x"\n',
    "no_connector": "ledger_version = 1\n",
    "connector_not_text": _file(connector="3"),
    "unknown_top_key": _file() + 'extra = "x"\n',
    "publication_not_array": "ledger_version = 1\nconnector = 'example'\n"
    "[publication]\npage = 'x'\n",
    "entry_not_table": "ledger_version = 1\nconnector = 'example'\npublication = [1]\n",
    "unknown_record_key": _file(_entry(body='"x"')),
    "no_page": _file(f'id = "{ID_1}"'),
    "no_id": _file(f'page = "workout:{SHA_A}"'),
    "page_bad_kind": _file(_entry(page=f'"run:{SHA_A}"')),
    "page_short": _file(_entry(page='"workout:abc"')),
    "page_upper": _file(_entry(page=f'"workout:{SHA_A.upper()}"')),
    "page_not_text": _file(_entry(page="7")),
    "page_duplicate": _file(_entry(), _entry(id=f'"{ID_2}"')),
    "page_long": _file(_entry(page=f'"workout:{SHA_A}0"')),
    "id_long": _file(_entry(id=f'"{ID_1}0"')),
    "digest_long": _file(_entry(digest=f'"{SHA_D}0"')),
    "version_float": _file(version="1.0"),
    "id_short": _file(_entry(id='"abc"')),
    "id_upper": _file(_entry(id=f'"{ID_1.upper()}"')),
    "id_duplicate": _file(_entry(), _entry(page=f'"workout:{SHA_B}"')),
    "digest_short": _file(_entry(digest='"abc"')),
    "digest_not_text": _file(_entry(digest="5")),
    "code_without_at": _file(_entry(code='"posted"')),
    "at_without_code": _file(_entry(at="2026-10-31T09:15:02Z")),
    "code_uppercase": _file(_entry(code='"Posted"', at="2026-10-31T09:15:02Z")),
    "code_leading_digit": _file(_entry(code='"9x"', at="2026-10-31T09:15:02Z")),
    "code_trailing_newline": _file(
        _entry(code='"posted\\n"', at="2026-10-31T09:15:02Z")
    ),
    "at_naive": _file(_entry(code='"posted"', at="2026-10-31T09:15:02")),
    "at_date_only": _file(_entry(code='"posted"', at="2026-10-31")),
    "at_text": _file(_entry(code='"posted"', at='"2026-10-31T09:15:02Z"')),
    "link_without_label": _file(_entry(link=f'"{LINK}"')),
    "label_without_link": _file(_entry(label='"Example"')),
    "link_http": _file(_entry(link='"http://example.invalid/a"', label='"Example"')),
    "link_with_space": _file(
        _entry(link='"https://example.invalid/a b"', label='"Example"')
    ),
    "label_with_bracket": _file(_entry(link=f'"{LINK}"', label='"Ex[ample"')),
    "label_empty": _file(_entry(link=f'"{LINK}"', label='""')),
}


class TestRefusals:
    @pytest.mark.parametrize("case", sorted(_REFUSED))
    def test_a_bad_file_is_refused_naming_it_and_left_untouched(
        self, tmp_path: Path, case: str
    ) -> None:
        path = publish_ledger_path(tmp_path, "t1")
        path.parent.mkdir(parents=True)
        if case == "not_utf8":
            path.write_bytes(b'ledger_version = 1\nconnector = "\xff"\n')
        else:
            path.write_text(_REFUSED[case], encoding="utf-8")
        before = path.read_bytes()
        os.utime(path, ns=(OLD_NS, OLD_NS))
        siblings = sorted(p.name for p in path.parent.iterdir())

        with pytest.raises(PublishLedgerError) as raised:
            load_ledgers(tmp_path, {"t1": "example"})

        assert str(path) in str(raised.value)
        assert path.read_bytes() == before
        assert path.stat().st_mtime_ns == OLD_NS
        assert sorted(p.name for p in path.parent.iterdir()) == siblings

    def test_the_entry_shape_the_refusal_cases_start_from_is_accepted(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path,
            "t1",
            _file(
                _entry(
                    digest=f'"{SHA_D}"',
                    code='"posted"',
                    at="2026-10-31T09:15:02Z",
                    link=f'"{LINK}"',
                    label='"Example"',
                ),
                _entry(page=f'"workout:{SHA_B}"', id=f'"{ID_2}"'),
            ),
        )
        assert len(load_ledgers(tmp_path, {"t1": "example"})["t1"].records) == 2

    @pytest.mark.parametrize("version", ["2", "100"])
    def test_a_newer_version_is_refused_as_newer_not_as_malformed(
        self, tmp_path: Path, version: str
    ) -> None:
        path = _write(tmp_path, "t1", _file(version=version))
        with pytest.raises(PublishLedgerError) as raised:
            load_ledgers(tmp_path, {"t1": "example"})
        reason = str(raised.value).removeprefix(f"publish ledger {path}: ")
        assert reason.startswith(f"is version {version}, newer")

    def test_a_malformed_version_is_not_called_newer(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "t1", _file(version="0"))
        with pytest.raises(PublishLedgerError) as raised:
            load_ledgers(tmp_path, {"t1": "example"})
        reason = str(raised.value).removeprefix(f"publish ledger {path}: ")
        assert "newer" not in reason
        assert reason  # the path prefix was stripped, leaving the reason

    def test_an_empty_connector_is_refused_even_when_the_target_is_not_configured(
        self, tmp_path: Path
    ) -> None:
        """No identity comparison is made here, so only the empty value can
        be what is refused."""
        path = _write(tmp_path, "t1", _file(connector='""'))
        with pytest.raises(PublishLedgerError) as raised:
            load_ledgers(tmp_path, {})
        assert str(path) in str(raised.value)

    def test_a_ledger_for_another_identity_is_refused(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "t1", _file(connector='"someone-else"'))
        os.utime(path, ns=(OLD_NS, OLD_NS))
        before = path.read_bytes()
        with pytest.raises(PublishLedgerError) as raised:
            load_ledgers(tmp_path, {"t1": "example"})
        assert str(path) in str(raised.value)
        assert path.read_bytes() == before
        assert path.stat().st_mtime_ns == OLD_NS

    def test_the_same_publication_id_in_two_targets_is_refused(
        self, tmp_path: Path
    ) -> None:
        save_ledger(tmp_path, _ledger(_landed(SHA_A, ID_1), target="one"))
        save_ledger(tmp_path, _ledger(_landed(SHA_B, ID_1), target="two"))
        with pytest.raises(PublishLedgerError) as raised:
            load_ledgers(tmp_path, {})
        assert "two.toml" in str(raised.value)

    def test_a_file_whose_stem_is_not_a_target_name_is_refused(
        self, tmp_path: Path
    ) -> None:
        directory = tmp_path / ".fitdocs" / "publish"
        directory.mkdir(parents=True)
        (directory / "Bad Name.toml").write_text(_file(), encoding="utf-8")
        with pytest.raises(PublishLedgerError) as raised:
            load_ledgers(tmp_path, {})
        assert "Bad Name.toml" in str(raised.value)

    def test_a_directory_or_symlink_named_like_a_ledger_is_refused(
        self, tmp_path: Path
    ) -> None:
        directory = tmp_path / ".fitdocs" / "publish"
        directory.mkdir(parents=True)
        (directory / "dir.toml").mkdir()
        with pytest.raises(PublishLedgerError) as raised:
            load_ledgers(tmp_path, {})
        assert "dir.toml" in str(raised.value)
        (directory / "dir.toml").rmdir()
        real = tmp_path / "real.toml"
        real.write_text(_file(), encoding="utf-8")
        (directory / "link.toml").symlink_to(real)
        with pytest.raises(PublishLedgerError) as raised:
            load_ledgers(tmp_path, {})
        assert "link.toml" in str(raised.value)

    def test_an_unreadable_file_is_refused_naming_it(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "t1", _file())
        path.chmod(0)
        try:
            if os.access(path, os.R_OK):
                pytest.skip("permissions are not enforced for this user")
            with pytest.raises(PublishLedgerError) as raised:
                load_ledgers(tmp_path, {"t1": "example"})
            assert str(path) in str(raised.value)
            assert "cannot be read" in str(raised.value)
        finally:
            path.chmod(0o644)

    def test_saving_a_record_with_a_link_and_no_label_is_refused(
        self, tmp_path: Path
    ) -> None:
        bad = dataclasses.replace(_landed(SHA_A, ID_1), label=None)
        with pytest.raises(PublishLedgerError) as raised:
            save_ledger(tmp_path, _ledger(bad))
        assert "t1.toml" in str(raised.value)
        assert not (tmp_path / ".fitdocs").exists()

    @pytest.mark.parametrize(
        "bad",
        [
            dataclasses.replace(_landed(SHA_A, ID_1), link=None),
            dataclasses.replace(_landed(SHA_A, ID_1), link="http://example.invalid/"),
            dataclasses.replace(_landed(SHA_A, ID_1), label="a]b"),
            dataclasses.replace(_landed(SHA_A, ID_1), code=None),
            dataclasses.replace(_landed(SHA_A, ID_1), at=None),
            dataclasses.replace(_landed(SHA_A, ID_1), at=AT.replace(tzinfo=None)),
            dataclasses.replace(_landed(SHA_A, ID_1), code="Bad Code"),
            dataclasses.replace(_landed(SHA_A, ID_1), digest="xyz"),
            dataclasses.replace(_landed(SHA_A, ID_1), publication_id="short"),
            dataclasses.replace(_landed(SHA_A, ID_1), page="workout:xyz"),
            dataclasses.replace(_landed(SHA_A, ID_1), page=f"workout:{SHA_A}0"),
            dataclasses.replace(_landed(SHA_A, ID_1), publication_id=ID_1 + "0"),
            dataclasses.replace(_landed(SHA_A, ID_1), digest=SHA_D + "0"),
        ],
    )
    def test_saving_any_violated_invariant_is_refused(
        self, tmp_path: Path, bad: PublicationRecord
    ) -> None:
        with pytest.raises(PublishLedgerError):
            save_ledger(tmp_path, _ledger(bad))
        assert not (tmp_path / ".fitdocs").exists()

    def test_saving_duplicate_pages_or_ids_is_refused(self, tmp_path: Path) -> None:
        a = _landed(SHA_A, ID_1)
        same_page = dataclasses.replace(a, publication_id=ID_2)
        with pytest.raises(PublishLedgerError):
            save_ledger(tmp_path, _ledger(a, same_page))
        with pytest.raises(PublishLedgerError):
            save_ledger(tmp_path, _ledger(a, _landed(SHA_B, ID_1)))
        assert not (tmp_path / ".fitdocs").exists()

    def test_saving_an_invalid_target_or_empty_connector_is_refused(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(PublishLedgerError):
            save_ledger(tmp_path, _ledger(target="../escape"))
        with pytest.raises(PublishLedgerError):
            save_ledger(tmp_path, PublishLedger("t1", "", ()))
        assert list(tmp_path.iterdir()) == []


_NAME_CASES = [
    ("a" * 64, True),
    ("a", True),
    ("0-a", True),
    ("a" * 65, False),
    ("a_b", False),
    ("-a", False),
    ("Ab", False),
    ("", False),
]


class TestTargetNames:
    def test_the_target_name_rule_is_the_connectors_instance_name_rule(self) -> None:
        from fitdocs.connectors.settings import INSTANCE_NAME_PATTERN
        from fitdocs.publish import ledger as module

        assert f"^{module._TARGET_RE.pattern}$" == INSTANCE_NAME_PATTERN

    @pytest.mark.parametrize(("name", "valid"), _NAME_CASES)
    def test_a_target_name_is_accepted_exactly_as_the_connectors_rule_does(
        self, tmp_path: Path, name: str, valid: bool
    ) -> None:
        import re

        from fitdocs.connectors.settings import INSTANCE_NAME_PATTERN

        assert bool(re.fullmatch(INSTANCE_NAME_PATTERN, name)) is valid
        ledger = PublishLedger(name, "example", ())
        if valid:
            save_ledger(tmp_path, ledger)
            assert load_ledgers(tmp_path, {})[name] == ledger
        else:
            with pytest.raises(PublishLedgerError):
                save_ledger(tmp_path, ledger)
            assert list(tmp_path.iterdir()) == []


class TestSaveFailures:
    def test_an_os_error_becomes_a_ledger_error_naming_the_file(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / ".fitdocs").mkdir()
        (tmp_path / ".fitdocs" / "publish").write_text("in the way", encoding="utf-8")
        with pytest.raises(PublishLedgerError) as raised:
            save_ledger(tmp_path, _ledger(_landed(SHA_A, ID_1)))
        assert str(publish_ledger_path(tmp_path, "t1")) in str(raised.value)
        assert (tmp_path / ".fitdocs" / "publish").read_text() == "in the way"

    def test_a_write_failure_becomes_a_ledger_error_and_leaves_no_temp_file(
        self, tmp_path: Path
    ) -> None:
        target = publish_ledger_path(tmp_path, "t1")
        target.mkdir(parents=True)  # a directory where the ledger file goes
        with pytest.raises(PublishLedgerError) as raised:
            save_ledger(tmp_path, _ledger(_landed(SHA_A, ID_1)))
        assert str(target) in str(raised.value)
        assert target.is_dir()
        assert sorted(p.name for p in target.parent.iterdir()) == ["t1.toml"]
