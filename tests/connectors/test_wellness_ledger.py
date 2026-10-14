"""Wellness ledger values, persistence, and malformed-record refusals."""

from __future__ import annotations

import os
import tomllib
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import tomli_w

from fitdocs.connectors.ledger import (
    ACTIVITY_LEDGER_VERSION,
    LEDGER_VERSION,
    WELLNESS_LEDGER_VERSION,
    Ledger,
    LedgerEntry,
    LedgerError,
    Outcome,
    WellnessDayEntry,
    WellnessLedger,
    WellnessPending,
    load_ledger,
    save_ledger,
)
from fitdocs.layout import connector_ledger_path
from tests.fixtures.builder import FIT_TIMESTAMP_BASE

_TIME = datetime(1989, 12, 31, tzinfo=UTC) + timedelta(seconds=FIT_TIMESTAMP_BASE)
_DAY = _TIME.date()
_A, _B, _C, _D, _E = (letter * 64 for letter in "abcde")


def _day(offset: int) -> date:
    return _DAY + timedelta(days=offset)


def _pending(path: str = "source/b.json", sha: str = _B) -> WellnessPending:
    return WellnessPending(path, sha, "intervals-icu", ".json")


def _wellness() -> WellnessLedger:
    return WellnessLedger(
        through=_day(5),
        origins=("apple-health", "garmin", "polar"),
        days=(
            WellnessDayEntry(_day(1), None, _B),
            WellnessDayEntry(_day(2), "revision-a", _C),
            WellnessDayEntry(_day(3), "revision-z", _A),
        ),
        pending=(
            WellnessPending("source/a.json", _E, "intervals-icu", ".json"),
            WellnessPending("source/b.csv", _D, "polar", ".csv"),
        ),
    )


def test_version_constants_and_trailing_wellness_default() -> None:
    assert (LEDGER_VERSION, ACTIVITY_LEDGER_VERSION, WELLNESS_LEDGER_VERSION) == (
        2,
        1,
        2,
    )
    assert [(f.name, f.default) for f in fields(Ledger)][-1] == ("wellness", None)


@pytest.mark.parametrize(
    "value,field",
    [
        (WellnessDayEntry(_DAY, None, _A), "day"),
        (_pending(), "path"),
        (WellnessLedger(), "through"),
    ],
)
def test_wellness_values_are_frozen(value: Any, field: str) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(value, field, None)


def test_entry_distinguishes_missing_from_no_revision() -> None:
    ledger = _wellness()
    assert ledger.entry(_day(1)) == WellnessDayEntry(_day(1), None, _B)
    assert ledger.entry(_day(2)) == WellnessDayEntry(_day(2), "revision-a", _C)
    assert ledger.entry(_day(3)) == WellnessDayEntry(_day(3), "revision-z", _A)
    assert ledger.entry(_day(9)) is None


def test_with_days_replaces_and_adds_sorted_without_losing_other_fields() -> None:
    ledger = _wellness()
    before = deepcopy(ledger)
    updated = ledger.with_days(
        [(_day(4), "new-z"), (_day(2), "new-a"), (_day(0), None)], _D
    )
    assert ledger == before
    assert updated == replace(
        before,
        days=(
            WellnessDayEntry(_day(0), None, _D),
            WellnessDayEntry(_day(1), None, _B),
            WellnessDayEntry(_day(2), "new-a", _D),
            WellnessDayEntry(_day(3), "revision-z", _A),
            WellnessDayEntry(_day(4), "new-z", _D),
        ),
    )


def test_pending_add_replace_remove_sorted_and_preserve_days() -> None:
    ledger = _wellness()
    before = deepcopy(ledger)
    replacement = WellnessPending("source/a.json", _A, "synthetic-a", ".a1")
    updated = ledger.with_pending(replacement)
    assert ledger == before
    assert updated == replace(
        before,
        pending=(
            WellnessPending("source/a.json", _A, "synthetic-a", ".a1"),
            WellnessPending("source/b.csv", _D, "polar", ".csv"),
        ),
    )
    updated_before = deepcopy(updated)
    removed = updated.without_pending("source/b.csv")
    assert updated == updated_before
    assert removed == replace(
        updated_before,
        pending=(WellnessPending("source/a.json", _A, "synthetic-a", ".a1"),),
    )
    unknown = updated.without_pending("missing")
    assert updated == updated_before
    assert unknown == updated_before


def test_origins_are_sorted_distinct_and_keep_the_other_fields() -> None:
    ledger = _wellness()
    before = deepcopy(ledger)
    updated = ledger.with_origins(iter(["wahoo", "apple-health", "wahoo", "polar"]))
    assert ledger == before
    assert updated == replace(before, origins=("apple-health", "polar", "wahoo"))


@pytest.mark.parametrize("method", ["with_entry", "without", "with_watermark"])
def test_activity_copies_keep_wellness(method: str) -> None:
    old = LedgerEntry("b", Outcome.ALREADY_HELD, sha256=_B)
    ledger = Ledger("intervals", _TIME, (old,), _wellness())
    before = deepcopy(ledger)
    if method == "with_entry":
        new = LedgerEntry("a", Outcome.SKIPPED, detail="synthetic skip")
        expected = replace(before, entries=(new, old))
        updated = ledger.with_entry(new)
    elif method == "without":
        expected = replace(before, entries=())
        updated = ledger.without("b")
    else:
        expected = replace(before, watermark=_TIME + timedelta(days=1))
        updated = ledger.with_watermark(_TIME + timedelta(days=1))
    assert ledger == before
    assert updated == expected


def test_with_wellness_keeps_activity_keyspace() -> None:
    ledger = Ledger(
        "intervals", _TIME, (LedgerEntry("a", Outcome.ALREADY_HELD, sha256=_A),)
    )
    before = deepcopy(ledger)
    expected = replace(before, wellness=_wellness())
    updated = ledger.with_wellness(_wellness())
    assert ledger == before
    assert updated == expected


@pytest.mark.parametrize(
    "through,oldest,newest,expected",
    [
        (None, 4, 6, 6),
        (5, 3, 7, 7),
        (5, 6, 8, 8),
        (5, 7, 9, 5),
        (5, 2, 4, 5),
        (5, 5, 5, 5),
    ],
)
def test_coverage_contiguous_and_monotonic(
    through: int | None, oldest: int, newest: int, expected: int
) -> None:
    ledger = replace(_wellness(), through=None if through is None else _day(through))
    before = deepcopy(ledger)
    updated = ledger.with_coverage(_day(oldest), _day(newest))
    assert ledger == before
    assert updated == replace(before, through=_day(expected))


def test_forget_uses_latest_sha_and_lowers_before_earliest_dropped_day() -> None:
    ledger = (
        WellnessLedger(through=_day(8), origins=("polar",))
        .with_days([(_day(4), "old"), (_day(2), None)], _A)
        .with_days([(_day(6), "other")], _B)
        .with_pending(_pending("source/lost.json", _A))
        .with_pending(_pending())
    )
    ledger = ledger.with_days([(_day(2), "latest")], _C)
    before = deepcopy(ledger)
    updated = ledger.forget("source/lost.json")
    assert ledger == before
    assert updated == replace(
        before,
        through=_day(3),
        days=(
            WellnessDayEntry(_day(2), "latest", _C),
            WellnessDayEntry(_day(6), "other", _B),
        ),
        pending=(_pending(),),
    )
    unknown = ledger.forget("missing")
    assert ledger == before
    assert unknown == before


@pytest.mark.parametrize("through", [None, 0])
def test_forget_does_not_raise_or_advance_an_earlier_mark(through: int | None) -> None:
    ledger = (
        WellnessLedger(through=None if through is None else _day(through))
        .with_days([(_day(3), None)], _A)
        .with_pending(_pending(sha=_A))
    )
    before = deepcopy(ledger)
    updated = ledger.forget("source/b.json")
    assert ledger == before
    assert updated == replace(before, days=(), pending=())


def test_forget_pending_with_no_latest_day_keeps_mark() -> None:
    ledger = _wellness()
    before = deepcopy(ledger)
    updated = ledger.forget("source/b.csv")
    assert ledger == before
    assert updated == replace(
        before,
        pending=(WellnessPending("source/a.json", _E, "intervals-icu", ".json"),),
    )


def test_activity_only_literal_golden(tmp_path: Path) -> None:
    ledger = Ledger(
        "intervals", None, (LedgerEntry("a", Outcome.ALREADY_HELD, sha256=_A),)
    )
    save_ledger(tmp_path, "source", ledger)
    assert (
        connector_ledger_path(tmp_path, "source").read_bytes()
        == b'ledger_version = 1\nconnector = "intervals"\n\n'
        b'[[entries]]\nremote_id = "a"\noutcome = "already-held"\n'
        b'sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n'
    )


def test_wellness_roundtrip_stable_order_and_omission(tmp_path: Path) -> None:
    wellness = (
        WellnessLedger(through=_day(5))
        .with_days(
            [(_day(3), "revision-z"), (_day(1), None), (_day(2), "revision-a")], _A
        )
        .with_days([(_day(2), "revision-a")], _C)
        .with_days([(_day(1), None)], _B)
        .with_pending(WellnessPending("source/b.csv", _D, "polar", ".csv"))
        .with_pending(WellnessPending("source/a.json", _E, "intervals-icu", ".json"))
        .with_origins(["polar", "garmin", "polar", "apple-health"])
    )
    assert wellness == _wellness()
    ledger = Ledger(
        "intervals",
        _TIME,
        (LedgerEntry("a", Outcome.ALREADY_HELD, sha256=_B),),
        wellness,
    )
    assert save_ledger(tmp_path, "source", ledger) is True
    path = connector_ledger_path(tmp_path, "source")
    data = tomllib.loads(path.read_text())
    assert data["ledger_version"] == 2
    assert data["wellness"] == {
        "through": _day(5),
        "origins": ["apple-health", "garmin", "polar"],
        "days": [
            {"day": _day(1), "sha256": _B},
            {"day": _day(2), "revision": "revision-a", "sha256": _C},
            {"day": _day(3), "revision": "revision-z", "sha256": _A},
        ],
        "pending": [
            {
                "path": "source/a.json",
                "sha256": _E,
                "format": "intervals-icu",
                "suffix": ".json",
            },
            {"path": "source/b.csv", "sha256": _D, "format": "polar", "suffix": ".csv"},
        ],
    }
    assert load_ledger(tmp_path, "source", connector_id="intervals") == ledger
    before = path.read_bytes()
    os.utime(path, ns=(1234567890, 1234567890))
    assert save_ledger(tmp_path, "source", ledger) is False
    assert (path.read_bytes(), path.stat().st_mtime_ns) == (before, 1234567890)


def test_empty_wellness_table_is_present_and_roundtrips(tmp_path: Path) -> None:
    ledger = Ledger("intervals", None, (), WellnessLedger())
    save_ledger(tmp_path, "source", ledger)
    data = tomllib.loads(connector_ledger_path(tmp_path, "source").read_text())
    assert data == {
        "ledger_version": 2,
        "connector": "intervals",
        "entries": [],
        "wellness": {"days": [], "pending": []},
    }
    assert load_ledger(tmp_path, "source", connector_id="intervals") == ledger


def _table() -> dict[str, Any]:
    return {
        "through": _day(5),
        "origins": ["garmin", "polar"],
        "days": [
            {"day": _day(1), "revision": "revision-a", "sha256": _A},
            {"day": _day(2), "sha256": _B},
        ],
        "pending": [
            {
                "path": "source/a.json",
                "sha256": _C,
                "format": "intervals-icu",
                "suffix": ".json",
            },
            {
                "path": "source/b.json",
                "sha256": _A,
                "format": "polar",
                "suffix": ".csv",
            },
        ],
    }


_INVALID: list[tuple[str, str, object]] = [
    ("through", "through", _TIME),
    ("through-text", "through", "synthetic"),
    ("through-bool", "through", True),
    ("origin-type", "origins", [7]),
    ("origin-bool", "origins", [True]),
    ("origin-slug", "origins", ["Garmin"]),
    ("origin-empty", "origins", [""]),
    ("origin-end", "origins", ["garmin-"]),
    ("origin-newline", "origins", ["garmin\n"]),
    ("origin-sort", "origins", ["polar", "garmin"]),
    ("origin-duplicate", "origins", ["garmin", "garmin"]),
    ("day-missing", "day", None),
    ("day-datetime", "day", _TIME),
    ("day-text", "day", "synthetic"),
    ("day-bool", "day", False),
    ("day-sort", "days", "reverse"),
    ("day-duplicate", "days", "duplicate"),
    ("revision-empty", "revision", ""),
    ("revision-long", "revision", "r" * 513),
    ("revision-control", "revision", "r\x00"),
    ("revision-del", "revision", "r\x7f"),
    ("revision-c1-start", "revision", "r\x80"),
    ("revision-c1-end", "revision", "r\x9f"),
    ("revision-type", "revision", 7),
    ("revision-bool", "revision", False),
    ("revision-bool-true", "revision", True),
    ("day-sha-missing", "day-sha", None),
    ("day-sha-type", "day-sha", 7),
    ("day-sha-bool", "day-sha", True),
    ("day-sha-short", "day-sha", "a" * 63),
    ("day-sha-long", "day-sha", "a" * 65),
    ("day-sha-upper", "day-sha", "A" * 64),
    ("day-sha-nonhex", "day-sha", "g" * 64),
    ("path-sort", "pending", "reverse"),
    ("path-duplicate", "pending", "duplicate"),
    ("path-missing", "path", None),
    ("path-type", "path", 7),
    ("path-bool", "path", True),
    ("path-empty", "path", ""),
    ("path-absolute", "path", "/escape.json"),
    ("path-dotdot", "path", "source/../escape.json"),
    ("path-dot", "path", "source/./a.json"),
    ("path-empty-segment", "path", "source//a.json"),
    ("path-trailing", "path", "source/"),
    ("pending-sha-missing", "pending-sha", None),
    ("pending-sha-type", "pending-sha", 7),
    ("pending-sha-bool", "pending-sha", False),
    ("pending-sha-short", "pending-sha", "b" * 63),
    ("pending-sha-long", "pending-sha", "b" * 65),
    ("pending-sha-upper", "pending-sha", "B" * 64),
    ("pending-sha-nonhex", "pending-sha", "z" * 64),
    ("format-missing", "format", None),
    ("format-type", "format", 7),
    ("format-bool", "format", False),
    ("format-empty", "format", ""),
    ("format-slug", "format", "Intervals-icu"),
    ("format-end", "format", "intervals-icu-"),
    ("format-newline", "format", "polar\n"),
    ("suffix-missing", "suffix", None),
    ("suffix-type", "suffix", 7),
    ("suffix-bool", "suffix", True),
    ("suffix-fit", "suffix", ".fit"),
    ("suffix-empty", "suffix", ""),
    ("suffix-dot", "suffix", "json"),
    ("suffix-upper", "suffix", ".JSON"),
    ("suffix-end", "suffix", ".jsonx-"),
    ("suffix-newline", "suffix", ".json\n"),
]


def _invalid_table(field: str, value: object) -> dict[str, Any]:
    table = _table()
    if field in {"through", "origins"}:
        table[field] = value
    elif field in {"days", "pending"}:
        if value == "reverse":
            table[field].reverse()
        else:
            table[field][1] = table[field][0].copy()
    elif field in {"day", "revision", "day-sha"}:
        if field == "day":
            table["days"] = [table["days"][0]]
        key = "sha256" if field == "day-sha" else field
        if value is None:
            table["days"][0].pop(key)
        else:
            table["days"][0][key] = value
    else:
        key = "sha256" if field == "pending-sha" else field
        index = 1
        if field == "path":
            table["pending"] = [table["pending"][1]]
            index = 0
        if value is None:
            table["pending"][index].pop(key)
        else:
            table["pending"][index][key] = value
    return table


def _value(table: dict[str, Any]) -> WellnessLedger:
    return WellnessLedger(
        table.get("through"),
        tuple(table.get("origins", ())),
        tuple(
            WellnessDayEntry(raw.get("day"), raw.get("revision"), raw.get("sha256"))
            for raw in table.get("days", ())
        ),
        tuple(
            WellnessPending(
                raw.get("path"), raw.get("sha256"), raw.get("format"), raw.get("suffix")
            )
            for raw in table.get("pending", ())
        ),
    )


@pytest.mark.parametrize("operation", ["load", "save"])
@pytest.mark.parametrize("name,field,value", _INVALID, ids=[row[0] for row in _INVALID])
def test_invalid_wellness_refused_on_load_and_save_without_writes(
    tmp_path: Path, name: str, field: str, value: object, operation: str
) -> None:
    table = _invalid_table(field, value)
    path = connector_ledger_path(tmp_path, "source")
    path.parent.mkdir(parents=True)
    raw = tomli_w.dumps(
        {
            "ledger_version": 2,
            "connector": "intervals",
            "entries": [],
            "wellness": table,
        }
    ).encode()
    path.write_bytes(raw)
    os.utime(path, ns=(1234567890, 1234567890))
    if operation == "load":
        with pytest.raises(LedgerError) as exc:
            load_ledger(tmp_path, "source", connector_id="intervals")
        assert str(path) in str(exc.value)
    else:
        with pytest.raises(ValueError):
            save_ledger(
                tmp_path, "source", Ledger("intervals", None, (), _value(table))
            )
    assert (path.read_bytes(), path.stat().st_mtime_ns) == (raw, 1234567890)


@pytest.mark.parametrize(
    "version,wellness", [(1, {}), (3, {}), (True, None), ("2", None)]
)
def test_invalid_version_refused_naming_file_without_writes(
    tmp_path: Path, version: object, wellness: object
) -> None:
    path = connector_ledger_path(tmp_path, "source")
    path.parent.mkdir(parents=True)
    document: dict[str, object] = {"ledger_version": version, "connector": "intervals"}
    if wellness is not None:
        document["wellness"] = wellness
    raw = tomli_w.dumps(document).encode()
    path.write_bytes(raw)
    os.utime(path, ns=(1234567890, 1234567890))
    with pytest.raises(LedgerError) as exc:
        load_ledger(tmp_path, "source", connector_id="intervals")
    assert str(path) in str(exc.value)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == (raw, 1234567890)


@pytest.mark.parametrize(
    "field,value",
    [
        ("wellness", 7),
        ("origins", "a"),
        ("days", 7),
        ("days", [7]),
        ("pending", 7),
        ("pending", [7]),
    ],
)
def test_wellness_container_shapes_refused(
    tmp_path: Path, field: str, value: object
) -> None:
    table = _table()
    table[field] = value
    path = connector_ledger_path(tmp_path, "source")
    path.parent.mkdir(parents=True)
    path.write_text(
        tomli_w.dumps(
            {
                "ledger_version": 2,
                "connector": "intervals",
                "wellness": value if field == "wellness" else table,
            }
        )
    )
    with pytest.raises(LedgerError, match=str(path)):
        load_ledger(tmp_path, "source", connector_id="intervals")


def test_revision_length_boundary_and_optional_tables(tmp_path: Path) -> None:
    ledger = Ledger(
        "intervals",
        None,
        (),
        WellnessLedger().with_days([(_day(2), "r" * 512), (_day(1), None)], _A),
    )
    save_ledger(tmp_path, "source", ledger)
    assert load_ledger(tmp_path, "source", connector_id="intervals") == ledger


def test_forget_multiple_days_uses_earliest_and_retains_other_sha() -> None:
    ledger = (
        WellnessLedger(through=_day(8))
        .with_days([(_day(4), "later"), (_day(1), "earlier")], _A)
        .with_days([(_day(2), "decoy")], _C)
        .with_pending(_pending(sha=_A))
    )
    before = deepcopy(ledger)
    updated = ledger.forget("source/b.json")
    assert ledger == before
    assert updated == replace(
        before,
        through=_day(0),
        days=(WellnessDayEntry(_day(2), "decoy", _C),),
        pending=(),
    )


def test_origins_can_be_cleared() -> None:
    ledger = _wellness()
    before = deepcopy(ledger)
    updated = ledger.with_origins([])
    assert ledger == before
    assert updated == replace(before, origins=())


def test_load_accepts_absent_optional_wellness_collections(tmp_path: Path) -> None:
    path = connector_ledger_path(tmp_path, "source")
    path.parent.mkdir(parents=True)
    path.write_text('ledger_version = 2\nconnector = "intervals"\n\n[wellness]\n')
    assert load_ledger(tmp_path, "source", connector_id="intervals") == Ledger(
        "intervals", None, (), WellnessLedger()
    )


@pytest.mark.parametrize("revision", [" ", "r\u0020", "r\u007e", "r\u00a0", "r" * 512])
def test_valid_revision_boundaries_roundtrip(tmp_path: Path, revision: str) -> None:
    ledger = Ledger(
        "intervals", None, (), WellnessLedger().with_days([(_DAY, revision)], _A)
    )
    save_ledger(tmp_path, "source", ledger)
    assert load_ledger(tmp_path, "source", connector_id="intervals") == ledger


def test_numeric_slug_and_suffix_roundtrip(tmp_path: Path) -> None:
    ledger = Ledger(
        "intervals",
        None,
        (),
        WellnessLedger(origins=("0-9",)).with_pending(
            WellnessPending("source/n.json", _A, "1-2", ".a0")
        ),
    )
    save_ledger(tmp_path, "source", ledger)
    assert load_ledger(tmp_path, "source", connector_id="intervals") == ledger


def test_pending_add_sorts_and_keeps_other_fields() -> None:
    ledger = _wellness()
    before = deepcopy(ledger)
    pending = WellnessPending("source/0.json", "f" * 64, "synthetic", ".txt")
    updated = ledger.with_pending(pending)
    assert ledger == before
    assert updated == replace(
        before,
        pending=(
            WellnessPending("source/0.json", "f" * 64, "synthetic", ".txt"),
            WellnessPending("source/a.json", _E, "intervals-icu", ".json"),
            WellnessPending("source/b.csv", _D, "polar", ".csv"),
        ),
    )


def test_save_mixed_wellness_has_literal_data(tmp_path: Path) -> None:
    ledger = Ledger(
        "intervals",
        _TIME,
        (LedgerEntry("activity", Outcome.ALREADY_HELD, sha256=_D),),
        _wellness(),
    )
    save_ledger(tmp_path, "source", ledger)
    data = tomllib.loads(connector_ledger_path(tmp_path, "source").read_text())
    assert data == {
        "ledger_version": 2,
        "connector": "intervals",
        "watermark": _TIME,
        "entries": [{"remote_id": "activity", "outcome": "already-held", "sha256": _D}],
        "wellness": {
            "through": _day(5),
            "origins": ["apple-health", "garmin", "polar"],
            "days": [
                {"day": _day(1), "sha256": _B},
                {"day": _day(2), "revision": "revision-a", "sha256": _C},
                {"day": _day(3), "revision": "revision-z", "sha256": _A},
            ],
            "pending": [
                {
                    "path": "source/a.json",
                    "sha256": _E,
                    "format": "intervals-icu",
                    "suffix": ".json",
                },
                {
                    "path": "source/b.csv",
                    "sha256": _D,
                    "format": "polar",
                    "suffix": ".csv",
                },
            ],
        },
    }


def test_load_hand_authored_mixed_wellness(tmp_path: Path) -> None:
    path = connector_ledger_path(tmp_path, "source")
    path.parent.mkdir(parents=True)
    path.write_text(
        f"""ledger_version = 2
connector = "intervals"
watermark = {_TIME.isoformat()}

[[entries]]
remote_id = "activity"
outcome = "already-held"
sha256 = "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"

[wellness]
through = {_day(5).isoformat()}
origins = ["apple-health", "garmin", "polar"]

[[wellness.days]]
day = {_day(1).isoformat()}
sha256 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

[[wellness.days]]
day = {_day(2).isoformat()}
revision = "revision-a"
sha256 = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"

[[wellness.days]]
day = {_day(3).isoformat()}
revision = "revision-z"
sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

[[wellness.pending]]
path = "source/a.json"
sha256 = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
format = "intervals-icu"
suffix = ".json"

[[wellness.pending]]
path = "source/b.csv"
sha256 = "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
format = "polar"
suffix = ".csv"
"""
    )
    assert load_ledger(tmp_path, "source", connector_id="intervals") == Ledger(
        "intervals",
        _TIME,
        (LedgerEntry("activity", Outcome.ALREADY_HELD, sha256=_D),),
        WellnessLedger(
            through=_day(5),
            origins=("apple-health", "garmin", "polar"),
            days=(
                WellnessDayEntry(_day(1), None, _B),
                WellnessDayEntry(_day(2), "revision-a", _C),
                WellnessDayEntry(_day(3), "revision-z", _A),
            ),
            pending=(
                WellnessPending("source/a.json", _E, "intervals-icu", ".json"),
                WellnessPending("source/b.csv", _D, "polar", ".csv"),
            ),
        ),
    )
