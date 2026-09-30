"""Pins for the connector ledger: entries, invariants, watermark, file format.

Every malformed-shape fixture is written as raw TOML bytes rather than
through :func:`save_ledger`. Apart from ``foreign_connector`` (foreign only
relative to the loader's ``connector_id`` argument), each is a shape the
writer refuses to produce (:func:`save_ledger` runs every
in-memory ledger through the same :func:`fitdocs.connectors.ledger._invariant_violation`
check :func:`load_ledger` applies, and raises :class:`ValueError` before
writing anything if it fails -- pinned directly by the
``test_save_ledger_refuses_*`` tests below, each of which also asserts no
file is left on disk). The watermark, sort, and write-if-different pins
build :class:`Ledger`/:class:`LedgerEntry` values directly and deliberately
violate the property under test (an out-of-order tuple for the sort pin, a
backdated mtime for the write-if-different pin, an earlier watermark for the
monotonic pin) so a broken implementation is visible rather than
accidentally satisfied by a pre-sorted fixture.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import tomli_w

from fitdocs.connectors.ledger import (
    LEDGER_VERSION,
    Ledger,
    LedgerEntry,
    LedgerError,
    Outcome,
    load_ledger,
    save_ledger,
)
from fitdocs.layout import connector_ledger_path


def _write_raw(data_root: Path, instance: str, document: dict[str, object]) -> Path:
    path = connector_ledger_path(data_root, instance)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tomli_w.dumps(document).encode("utf-8"))
    return path


def _valid_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "ledger_version": LEDGER_VERSION,
        "connector": "folder",
        "entries": [],
    }
    document.update(overrides)
    return document


# --- Absent path / non-regular-file path (Req 7.5, 7.6) ----------------------


def test_load_ledger_absent_file_yields_empty_ledger_for_the_named_connector(
    tmp_path: Path,
) -> None:
    ledger = load_ledger(tmp_path, "healthfit", connector_id="folder")
    assert ledger == Ledger(connector_id="folder", watermark=None, entries=())


def test_load_ledger_absent_file_creates_no_directory(tmp_path: Path) -> None:
    load_ledger(tmp_path, "healthfit", connector_id="folder")
    assert not (tmp_path / ".fitdocs").exists()


def test_load_ledger_directory_at_the_ledger_path_raises_not_treated_as_absent(
    tmp_path: Path,
) -> None:
    path = connector_ledger_path(tmp_path, "healthfit")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir()  # a directory sits where the ledger file would be
    with pytest.raises(LedgerError, match=str(path)):
        load_ledger(tmp_path, "healthfit", connector_id="folder")


# --- Round trip ---------------------------------------------------------------


def test_round_trip_preserves_entries_and_watermark(tmp_path: Path) -> None:
    watermark = datetime(2026, 9, 20, 7, 12, 0, tzinfo=UTC)
    ledger = Ledger(
        connector_id="folder",
        watermark=watermark,
        entries=(
            LedgerEntry(
                remote_id="2026/2026-09-20-run.fit",
                outcome=Outcome.DELIVERED,
                revision="481233:1758352320000000000",
                sha256="3f" * 32,
                pending="healthfit/2026-09-20-run.fit",
            ),
            LedgerEntry(
                remote_id="i123",
                outcome=Outcome.SKIPPED,
                detail="no original file: the activity came from a service "
                "that does not share originals",
            ),
        ),
    )
    changed = save_ledger(tmp_path, "healthfit", ledger)
    assert changed is True

    loaded = load_ledger(tmp_path, "healthfit", connector_id="folder")
    assert loaded == ledger


def test_round_trip_with_no_watermark_and_no_entries(tmp_path: Path) -> None:
    ledger = Ledger(connector_id="folder", watermark=None, entries=())
    save_ledger(tmp_path, "healthfit", ledger)
    loaded = load_ledger(tmp_path, "healthfit", connector_id="folder")
    assert loaded == ledger


# --- Save: exact-text golden, sorted, write-if-different, atomic -------------


_GOLDEN_LEDGER = Ledger(
    connector_id="folder",
    watermark=datetime(2026, 9, 20, 7, 12, 0, tzinfo=UTC),
    entries=(
        LedgerEntry(
            remote_id="delivered-id",
            outcome=Outcome.DELIVERED,
            revision="rev-1",
            sha256="a" * 64,
            pending="healthfit/delivered.fit",
        ),
        LedgerEntry(remote_id="held-id", outcome=Outcome.ALREADY_HELD, sha256="b" * 64),
        LedgerEntry(
            remote_id="skipped-id", outcome=Outcome.SKIPPED, detail="no original file"
        ),
    ),
)

# Hand-written, not produced by calling anything under test: what tomli_w (not
# this module) is independently known to emit for the equivalent raw dict --
# see the docstring note about tomli_w's datetime spelling.
_GOLDEN_TEXT = (
    'ledger_version = 1\nconnector = "folder"\n'
    "watermark = 2026-09-20 07:12:00+00:00\n\n"
    '[[entries]]\nremote_id = "delivered-id"\n'
    'revision = "rev-1"\noutcome = "delivered"\n'
    'sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n'
    'pending = "healthfit/delivered.fit"\n\n'
    '[[entries]]\nremote_id = "held-id"\noutcome = "already-held"\n'
    'sha256 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"\n\n'
    '[[entries]]\nremote_id = "skipped-id"\n'
    'outcome = "skipped"\ndetail = "no original file"\n'
)


def test_save_ledger_writes_the_exact_documented_text(tmp_path: Path) -> None:
    # NOTE (CONCERNS): design.md's own "Ledger file" example spells the
    # watermark ``2026-09-20T07:12:00Z``; tomli_w -- which this module is
    # required to use, and must not hand-roll TOML instead of -- serializes
    # an aware datetime as ``2026-09-20 07:12:00+00:00`` (a space rather than
    # "T", and an explicit "+00:00" offset rather than "Z"). Both spellings
    # are the same RFC 3339 instant and both round-trip identically through
    # tomllib; this golden pins tomli_w's actual spelling, not design's
    # literal example text, and that gap is called out in CONCERNS.
    save_ledger(tmp_path, "healthfit", _GOLDEN_LEDGER)
    text = connector_ledger_path(tmp_path, "healthfit").read_text()
    assert text == _GOLDEN_TEXT
    # the golden's [[entries]] blocks are the array-of-tables form design.md
    # documents, and the loader reads it back to the same ledger
    loaded = load_ledger(tmp_path, "healthfit", connector_id="folder")
    assert loaded == _GOLDEN_LEDGER


def test_save_ledger_writes_entries_sorted_even_from_an_unsorted_ledger(
    tmp_path: Path,
) -> None:
    # Deliberately unsorted and non-alphabetic-by-any-other-key insertion
    # order: "zebra" then "apple" then "mango" -- alphabetical sort produces
    # apple, mango, zebra, a different order than any coincidental ordering
    # (insertion order, reverse-insertion order) could produce.
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(
            LedgerEntry(
                remote_id="zebra", outcome=Outcome.ALREADY_HELD, sha256="a" * 64
            ),
            LedgerEntry(
                remote_id="apple", outcome=Outcome.ALREADY_HELD, sha256="b" * 64
            ),
            LedgerEntry(
                remote_id="mango", outcome=Outcome.ALREADY_HELD, sha256="c" * 64
            ),
        ),
    )
    save_ledger(tmp_path, "healthfit", ledger)

    text = connector_ledger_path(tmp_path, "healthfit").read_text()
    positions = {
        name: text.index(f'remote_id = "{name}"')
        for name in ("zebra", "apple", "mango")
    }
    assert positions["apple"] < positions["mango"] < positions["zebra"]


def test_second_save_of_unchanged_ledger_returns_false_and_does_not_rewrite(
    tmp_path: Path,
) -> None:
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(
            LedgerEntry(remote_id="a", outcome=Outcome.ALREADY_HELD, sha256="a" * 64),
        ),
    )
    assert save_ledger(tmp_path, "healthfit", ledger) is True

    path = connector_ledger_path(tmp_path, "healthfit")
    # Backdate the mtime so an unconditional rewrite (which would set it to
    # "now") is visible rather than accidentally already matching "now".
    past = (datetime.now(UTC) - timedelta(days=1)).timestamp()
    os.utime(path, (past, past))

    changed = save_ledger(tmp_path, "healthfit", ledger)

    assert changed is False
    assert path.stat().st_mtime == pytest.approx(past, abs=1.0)


def test_save_ledger_of_a_changed_ledger_returns_true_and_rewrites(
    tmp_path: Path,
) -> None:
    ledger = Ledger(connector_id="folder", watermark=None, entries=())
    save_ledger(tmp_path, "healthfit", ledger)
    path = connector_ledger_path(tmp_path, "healthfit")
    past = (datetime.now(UTC) - timedelta(days=1)).timestamp()
    os.utime(path, (past, past))

    changed = save_ledger(
        tmp_path,
        "healthfit",
        ledger.with_entry(
            LedgerEntry(remote_id="a", outcome=Outcome.ALREADY_HELD, sha256="a" * 64)
        ),
    )

    assert changed is True
    assert path.stat().st_mtime != pytest.approx(past, abs=1.0)


def test_save_ledger_creates_the_connector_state_directory_on_demand(
    tmp_path: Path,
) -> None:
    assert not (tmp_path / ".fitdocs").exists()
    ledger = Ledger(connector_id="folder", watermark=None, entries=())
    save_ledger(tmp_path, "healthfit", ledger)
    assert connector_ledger_path(tmp_path, "healthfit").is_file()


def test_save_ledger_omits_the_watermark_key_when_absent(tmp_path: Path) -> None:
    ledger = Ledger(connector_id="folder", watermark=None, entries=())
    save_ledger(tmp_path, "healthfit", ledger)
    text = connector_ledger_path(tmp_path, "healthfit").read_text()
    assert "watermark" not in text


def test_save_ledger_writes_through_write_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, bytes, str]] = []

    def fake_write_atomic(path: Path, data: bytes, *, prefix: str) -> None:
        calls.append((path, data, prefix))
        path.write_bytes(data)

    monkeypatch.setattr("fitdocs.connectors.ledger.write_atomic", fake_write_atomic)

    ledger = Ledger(connector_id="folder", watermark=None, entries=())
    changed = save_ledger(tmp_path, "healthfit", ledger)

    assert changed is True
    assert len(calls) == 1
    called_path, called_data, called_prefix = calls[0]
    assert called_path == connector_ledger_path(tmp_path, "healthfit")
    assert called_prefix == "healthfit"
    assert called_data == connector_ledger_path(tmp_path, "healthfit").read_bytes()


def test_second_save_of_unchanged_ledger_does_not_call_write_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = Ledger(connector_id="folder", watermark=None, entries=())
    save_ledger(tmp_path, "healthfit", ledger)

    calls: list[object] = []
    monkeypatch.setattr(
        "fitdocs.connectors.ledger.write_atomic", lambda *a, **k: calls.append((a, k))
    )
    changed = save_ledger(tmp_path, "healthfit", ledger)

    assert changed is False
    assert calls == []


# --- Save: refuses an invalid in-memory ledger, writes nothing (Finding 1) ---


def test_save_ledger_refuses_delivered_without_sha256_and_writes_nothing(
    tmp_path: Path,
) -> None:
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(LedgerEntry(remote_id="a", outcome=Outcome.DELIVERED),),
    )
    with pytest.raises(ValueError, match="sha256"):
        save_ledger(tmp_path, "healthfit", ledger)
    assert not connector_ledger_path(tmp_path, "healthfit").exists()


def test_save_ledger_refuses_duplicate_remote_ids_and_writes_nothing(
    tmp_path: Path,
) -> None:
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(
            LedgerEntry(remote_id="a", outcome=Outcome.ALREADY_HELD, sha256="a" * 64),
            LedgerEntry(remote_id="a", outcome=Outcome.ALREADY_HELD, sha256="b" * 64),
        ),
    )
    with pytest.raises(ValueError, match="duplicate"):
        save_ledger(tmp_path, "healthfit", ledger)
    assert not connector_ledger_path(tmp_path, "healthfit").exists()


def test_save_ledger_refuses_skipped_with_pending_and_writes_nothing(
    tmp_path: Path,
) -> None:
    # A valid 'detail' is present, isolating this rejection to the
    # pending-only-on-delivered check rather than the detail-required one.
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(
            LedgerEntry(
                remote_id="a",
                outcome=Outcome.SKIPPED,
                detail="no original",
                pending="healthfit/a.fit",
            ),
        ),
    )
    with pytest.raises(ValueError, match="pending"):
        save_ledger(tmp_path, "healthfit", ledger)
    assert not connector_ledger_path(tmp_path, "healthfit").exists()


@pytest.mark.parametrize(
    "entry",
    [
        LedgerEntry(remote_id="a", outcome=Outcome.ALREADY_HELD, sha256="not-hex"),
        LedgerEntry(remote_id="a", outcome=Outcome.ALREADY_HELD, sha256="a" * 64 + "0"),
        LedgerEntry(
            remote_id="a", outcome=Outcome.SKIPPED, detail="dup", sha256="nothex"
        ),
    ],
    ids=["not_hex", "too_long", "on_skipped"],
)
def test_save_ledger_refuses_invalid_sha256_and_writes_nothing(
    tmp_path: Path, entry: LedgerEntry
) -> None:
    ledger = Ledger(connector_id="folder", watermark=None, entries=(entry,))
    with pytest.raises(ValueError, match="sha256"):
        save_ledger(tmp_path, "healthfit", ledger)
    assert not connector_ledger_path(tmp_path, "healthfit").exists()


def test_save_ledger_refuses_unsafe_pending_path_and_writes_nothing(
    tmp_path: Path,
) -> None:
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(
            LedgerEntry(
                remote_id="a",
                outcome=Outcome.DELIVERED,
                sha256="a" * 64,
                pending="../escape.fit",
            ),
        ),
    )
    with pytest.raises(ValueError, match="pending"):
        save_ledger(tmp_path, "healthfit", ledger)
    assert not connector_ledger_path(tmp_path, "healthfit").exists()


def test_save_ledger_refuses_naive_watermark_and_writes_nothing(tmp_path: Path) -> None:
    ledger = Ledger(
        connector_id="folder",
        watermark=datetime(2026, 9, 20, 7, 12, 0),  # no tzinfo
        entries=(),
    )
    with pytest.raises(ValueError, match="timezone"):
        save_ledger(tmp_path, "healthfit", ledger)
    assert not connector_ledger_path(tmp_path, "healthfit").exists()


# --- Load: every malformed shape raises LedgerError naming the file --------


def test_load_ledger_unreadable_file_raises(tmp_path: Path) -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("permission bits are not enforced when running as root")
    path = _write_raw(tmp_path, "healthfit", _valid_document())
    path.chmod(0o000)
    try:
        with pytest.raises(LedgerError, match="could not be read") as excinfo:
            load_ledger(tmp_path, "healthfit", connector_id="folder")
        assert str(path) in str(excinfo.value)
    finally:
        path.chmod(0o644)


def test_load_ledger_invalid_toml_raises(tmp_path: Path) -> None:
    path = connector_ledger_path(tmp_path, "healthfit")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"this is not [ valid toml")
    with pytest.raises(LedgerError, match="not valid TOML") as excinfo:
        load_ledger(tmp_path, "healthfit", connector_id="folder")
    assert str(path) in str(excinfo.value)


def test_load_ledger_matching_connector_does_not_raise(tmp_path: Path) -> None:
    _write_raw(tmp_path, "healthfit", _valid_document(connector="folder"))
    ledger = load_ledger(tmp_path, "healthfit", connector_id="folder")
    assert ledger.connector_id == "folder"


def test_load_ledger_current_format_does_not_raise(tmp_path: Path) -> None:
    # LEDGER_VERSION == 1 is the format's first version, so there is no
    # genuinely older version to fixture; this pins only "the current,
    # matching version is accepted", not "an older version is accepted".
    _write_raw(tmp_path, "healthfit", _valid_document(ledger_version=LEDGER_VERSION))
    load_ledger(tmp_path, "healthfit", connector_id="folder")


def test_load_ledger_delivered_with_sha256_does_not_raise(tmp_path: Path) -> None:
    document = _valid_document(
        entries=[{"remote_id": "a", "outcome": "delivered", "sha256": "a" * 64}]
    )
    _write_raw(tmp_path, "healthfit", document)
    ledger = load_ledger(tmp_path, "healthfit", connector_id="folder")
    assert ledger.get("a") is not None


def test_load_ledger_skipped_with_detail_does_not_raise(tmp_path: Path) -> None:
    document = _valid_document(
        entries=[{"remote_id": "a", "outcome": "skipped", "detail": "no original"}]
    )
    _write_raw(tmp_path, "healthfit", document)
    ledger = load_ledger(tmp_path, "healthfit", connector_id="folder")
    assert ledger.get("a") is not None


def test_load_ledger_pending_on_delivered_does_not_raise(tmp_path: Path) -> None:
    document = _valid_document(
        entries=[
            {
                "remote_id": "a",
                "outcome": "delivered",
                "sha256": "a" * 64,
                "pending": "healthfit/a.fit",
            }
        ]
    )
    _write_raw(tmp_path, "healthfit", document)
    ledger = load_ledger(tmp_path, "healthfit", connector_id="folder")
    entry = ledger.get("a")
    assert entry is not None and entry.pending == "healthfit/a.fit"


# --- Parametrized: every malformed document raises LedgerError naming the file


def _delivered_no_sha256_document() -> dict[str, object]:
    return _valid_document(entries=[{"remote_id": "a", "outcome": "delivered"}])


def _already_held_no_sha256_document() -> dict[str, object]:
    return _valid_document(entries=[{"remote_id": "a", "outcome": "already-held"}])


def _skipped_no_detail_document() -> dict[str, object]:
    return _valid_document(entries=[{"remote_id": "a", "outcome": "skipped"}])


def _pending_on_already_held_document() -> dict[str, object]:
    return _valid_document(
        entries=[
            {
                "remote_id": "a",
                "outcome": "already-held",
                "sha256": "a" * 64,
                "pending": "healthfit/a.fit",
            }
        ]
    )


def _pending_on_skipped_with_detail_document() -> dict[str, object]:
    # A valid 'detail' is present, isolating this fixture to the
    # pending-only-on-delivered check rather than the detail-required one
    # (Finding 3).
    return _valid_document(
        entries=[
            {
                "remote_id": "a",
                "outcome": "skipped",
                "detail": "no original file",
                "pending": "healthfit/a.fit",
            }
        ]
    )


def _invalid_outcome_document() -> dict[str, object]:
    # sha256 and detail are both supplied so a broken implementation that
    # silently coerces "bogus" to some valid Outcome member cannot slip past
    # this check only to be (accidentally) caught by the sha256- or
    # detail-required invariant instead.
    return _valid_document(
        entries=[
            {
                "remote_id": "a",
                "outcome": "bogus",
                "sha256": "a" * 64,
                "detail": "irrelevant",
            }
        ]
    )


def _duplicate_remote_id_document() -> dict[str, object]:
    return _valid_document(
        entries=[
            {"remote_id": "a", "outcome": "already-held", "sha256": "a" * 64},
            {"remote_id": "a", "outcome": "already-held", "sha256": "b" * 64},
        ]
    )


def _unsorted_entries_document() -> dict[str, object]:
    return _valid_document(
        entries=[
            {"remote_id": "zebra", "outcome": "already-held", "sha256": "a" * 64},
            {"remote_id": "apple", "outcome": "already-held", "sha256": "b" * 64},
        ]
    )


def _invalid_sha256_too_short_document() -> dict[str, object]:
    return _valid_document(
        entries=[{"remote_id": "a", "outcome": "already-held", "sha256": "abc"}]
    )


def _invalid_sha256_uppercase_document() -> dict[str, object]:
    return _valid_document(
        entries=[{"remote_id": "a", "outcome": "already-held", "sha256": "A" * 64}]
    )


def _invalid_sha256_too_long_document() -> dict[str, object]:
    # Valid lowercase hex for the first 64 characters, so a prefix match
    # (rather than a full match) would accept it.
    return _valid_document(
        entries=[
            {"remote_id": "a", "outcome": "already-held", "sha256": "a" * 64 + "0"}
        ]
    )


def _invalid_sha256_on_skipped_document() -> dict[str, object]:
    return _valid_document(
        entries=[
            {
                "remote_id": "a",
                "outcome": "skipped",
                "detail": "dup",
                "sha256": "not-hex",
            }
        ]
    )


def _pending_document(pending: str) -> dict[str, object]:
    return _valid_document(
        entries=[
            {
                "remote_id": "a",
                "outcome": "delivered",
                "sha256": "a" * 64,
                "pending": pending,
            }
        ]
    )


def _pending_absolute_document() -> dict[str, object]:
    return _valid_document(
        entries=[
            {
                "remote_id": "a",
                "outcome": "delivered",
                "sha256": "a" * 64,
                "pending": "/etc/passwd",
            }
        ]
    )


def _pending_dotdot_document() -> dict[str, object]:
    return _valid_document(
        entries=[
            {
                "remote_id": "a",
                "outcome": "delivered",
                "sha256": "a" * 64,
                "pending": "healthfit/../../escape.fit",
            }
        ]
    )


def _missing_ledger_version_document() -> dict[str, object]:
    document = _valid_document()
    del document["ledger_version"]
    return document


def _ledger_version_wrong_type_document() -> dict[str, object]:
    return _valid_document(ledger_version="1")


def _newer_format_document() -> dict[str, object]:
    return _valid_document(ledger_version=LEDGER_VERSION + 1)


def _connector_wrong_type_document() -> dict[str, object]:
    return _valid_document(connector=7)


def _foreign_connector_document() -> dict[str, object]:
    return _valid_document(connector="intervals")


def _entries_wrong_type_document() -> dict[str, object]:
    return _valid_document(entries=5)


def _entry_not_table_document() -> dict[str, object]:
    return _valid_document(entries=["not-a-table"])


def _watermark_wrong_type_document() -> dict[str, object]:
    return _valid_document(watermark="2026-09-20T07:12:00Z")


def _watermark_naive_document() -> dict[str, object]:
    return _valid_document(watermark=datetime(2026, 9, 20, 7, 12, 0))  # no tzinfo


_MALFORMED_DOCUMENTS: list[tuple[str, Callable[[], dict[str, object]]]] = [
    ("missing_ledger_version", _missing_ledger_version_document),
    ("ledger_version_wrong_type", _ledger_version_wrong_type_document),
    ("newer_format", _newer_format_document),
    ("connector_wrong_type", _connector_wrong_type_document),
    ("foreign_connector", _foreign_connector_document),
    ("entries_wrong_type", _entries_wrong_type_document),
    ("entry_not_table", _entry_not_table_document),
    ("duplicate_remote_id", _duplicate_remote_id_document),
    ("unsorted_entries", _unsorted_entries_document),
    ("invalid_outcome", _invalid_outcome_document),
    ("delivered_no_sha256", _delivered_no_sha256_document),
    ("already_held_no_sha256", _already_held_no_sha256_document),
    ("skipped_no_detail", _skipped_no_detail_document),
    ("pending_on_already_held", _pending_on_already_held_document),
    ("pending_on_skipped_with_detail", _pending_on_skipped_with_detail_document),
    ("invalid_sha256_too_short", _invalid_sha256_too_short_document),
    ("invalid_sha256_uppercase", _invalid_sha256_uppercase_document),
    ("invalid_sha256_too_long", _invalid_sha256_too_long_document),
    ("invalid_sha256_on_skipped", _invalid_sha256_on_skipped_document),
    ("pending_empty", lambda: _pending_document("")),
    ("pending_dot", lambda: _pending_document(".")),
    ("pending_trailing_dot", lambda: _pending_document("healthfit/.")),
    ("pending_trailing_slash", lambda: _pending_document("healthfit/")),
    ("pending_empty_segment", lambda: _pending_document("healthfit//a.fit")),
    ("pending_absolute", _pending_absolute_document),
    ("pending_dotdot", _pending_dotdot_document),
    ("watermark_wrong_type", _watermark_wrong_type_document),
    ("watermark_naive", _watermark_naive_document),
]


@pytest.mark.parametrize(
    "name,build_document",
    _MALFORMED_DOCUMENTS,
    ids=[n for n, _ in _MALFORMED_DOCUMENTS],
)
def test_load_ledger_every_malformed_document_raises_naming_the_file(
    tmp_path: Path, name: str, build_document: Callable[[], dict[str, object]]
) -> None:
    path = _write_raw(tmp_path, "healthfit", build_document())
    with pytest.raises(LedgerError) as excinfo:
        load_ledger(tmp_path, "healthfit", connector_id="folder")
    assert str(path) in str(excinfo.value), (
        f"{name}: LedgerError message does not name the file: {excinfo.value}"
    )


# --- Ledger value: get, with_entry, without ----------------------------------


def test_get_returns_none_for_an_unknown_remote_id() -> None:
    ledger = Ledger(connector_id="folder", watermark=None, entries=())
    assert ledger.get("missing") is None


def test_get_returns_the_matching_entry_not_merely_the_first_one() -> None:
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(
            LedgerEntry(remote_id="a", outcome=Outcome.ALREADY_HELD, sha256="a" * 64),
            LedgerEntry(remote_id="b", outcome=Outcome.ALREADY_HELD, sha256="b" * 64),
        ),
    )
    found = ledger.get("b")
    assert found is not None
    assert found.remote_id == "b"
    assert found.sha256 == "b" * 64


def test_with_entry_adds_a_new_entry_and_keeps_sort() -> None:
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(
            LedgerEntry(remote_id="b", outcome=Outcome.ALREADY_HELD, sha256="a" * 64),
        ),
    )
    updated = ledger.with_entry(
        LedgerEntry(remote_id="a", outcome=Outcome.ALREADY_HELD, sha256="b" * 64)
    )
    assert [e.remote_id for e in updated.entries] == ["a", "b"]
    # original is untouched
    assert [e.remote_id for e in ledger.entries] == ["b"]


def test_with_entry_replaces_an_existing_entry_sharing_the_id() -> None:
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(
            LedgerEntry(remote_id="a", outcome=Outcome.ALREADY_HELD, sha256="a" * 64),
        ),
    )
    updated = ledger.with_entry(
        LedgerEntry(remote_id="a", outcome=Outcome.SKIPPED, detail="now skipped")
    )
    assert len(updated.entries) == 1
    entry = updated.get("a")
    assert entry is not None
    assert entry.outcome is Outcome.SKIPPED
    assert entry.detail == "now skipped"


def test_without_removes_the_matching_entry_and_leaves_others() -> None:
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(
            LedgerEntry(remote_id="a", outcome=Outcome.ALREADY_HELD, sha256="a" * 64),
            LedgerEntry(remote_id="b", outcome=Outcome.ALREADY_HELD, sha256="b" * 64),
        ),
    )
    updated = ledger.without("a")
    assert [e.remote_id for e in updated.entries] == ["b"]


def test_without_missing_id_leaves_entries_unchanged() -> None:
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(
            LedgerEntry(remote_id="a", outcome=Outcome.ALREADY_HELD, sha256="a" * 64),
        ),
    )
    updated = ledger.without("missing")
    assert updated.entries == ledger.entries


def test_pending_entries_returns_only_entries_with_a_pending_location() -> None:
    # Includes a DELIVERED entry whose pending is already None (a delivery
    # the sweep has already resolved) alongside a still-pending DELIVERED
    # entry and an ALREADY_HELD entry -- so a broken filter that keys off
    # outcome rather than the pending field itself (e.g. "outcome is
    # DELIVERED") cannot pass by coincidence (Finding 4).
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(
            LedgerEntry(
                remote_id="a",
                outcome=Outcome.DELIVERED,
                sha256="a" * 64,
                pending="healthfit/a.fit",
            ),
            LedgerEntry(remote_id="b", outcome=Outcome.ALREADY_HELD, sha256="b" * 64),
            LedgerEntry(
                remote_id="c", outcome=Outcome.DELIVERED, sha256="c" * 64, pending=None
            ),
        ),
    )
    assert [e.remote_id for e in ledger.pending_entries()] == ["a"]


# --- is_final: revision equality, None vs string (Req 7.7) -------------------


def test_is_final_true_when_revision_is_none_and_entrys_revision_is_none() -> None:
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(
            LedgerEntry(remote_id="a", outcome=Outcome.ALREADY_HELD, sha256="a" * 64),
        ),
    )
    assert ledger.is_final("a", None) is True


def test_is_final_false_when_entry_revision_none_but_asked_revision_is_string() -> None:
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(
            LedgerEntry(remote_id="a", outcome=Outcome.ALREADY_HELD, sha256="a" * 64),
        ),
    )
    assert ledger.is_final("a", "rev-1") is False


def test_is_final_true_when_revisions_match() -> None:
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(
            LedgerEntry(
                remote_id="a",
                outcome=Outcome.ALREADY_HELD,
                sha256="a" * 64,
                revision="rev-1",
            ),
        ),
    )
    assert ledger.is_final("a", "rev-1") is True


def test_is_final_false_when_revisions_differ() -> None:
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(
            LedgerEntry(
                remote_id="a",
                outcome=Outcome.ALREADY_HELD,
                sha256="a" * 64,
                revision="rev-1",
            ),
        ),
    )
    assert ledger.is_final("a", "rev-2") is False


def test_is_final_false_when_asked_revision_none_but_entry_revision_is_string() -> None:
    # The reverse direction of the None/string asymmetry (Finding 5): an
    # entry that *has* a revision is not final "at no particular revision".
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(
            LedgerEntry(
                remote_id="a",
                outcome=Outcome.ALREADY_HELD,
                sha256="a" * 64,
                revision="rev-1",
            ),
        ),
    )
    assert ledger.is_final("a", None) is False


def test_is_final_false_for_an_unknown_remote_id() -> None:
    ledger = Ledger(connector_id="folder", watermark=None, entries=())
    assert ledger.is_final("missing", None) is False


# --- Watermark: never moves backward (Req 7.2) -------------------------------


def test_with_watermark_sets_the_first_watermark() -> None:
    ledger = Ledger(connector_id="folder", watermark=None, entries=())
    t = datetime(2026, 9, 20, tzinfo=UTC)
    updated = ledger.with_watermark(t)
    assert updated.watermark == t


def test_with_watermark_advances_forward() -> None:
    t1 = datetime(2026, 9, 20, tzinfo=UTC)
    t2 = datetime(2026, 9, 21, tzinfo=UTC)
    ledger = Ledger(connector_id="folder", watermark=t1, entries=())
    updated = ledger.with_watermark(t2)
    assert updated.watermark == t2


def test_with_watermark_same_value_does_not_raise() -> None:
    t = datetime(2026, 9, 20, tzinfo=UTC)
    ledger = Ledger(connector_id="folder", watermark=t, entries=())
    updated = ledger.with_watermark(t)
    assert updated.watermark == t


def test_with_watermark_refuses_to_move_backward() -> None:
    t1 = datetime(2026, 9, 20, tzinfo=UTC)
    t0 = datetime(2026, 9, 19, tzinfo=UTC)
    ledger = Ledger(connector_id="folder", watermark=t1, entries=())
    with pytest.raises(ValueError):
        ledger.with_watermark(t0)
    # the original ledger's watermark is untouched by the failed attempt
    assert ledger.watermark == t1
