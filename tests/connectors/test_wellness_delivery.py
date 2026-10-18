"""WellnessDelivery checks, naming, archive lookup and suffix delivery."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from itertools import islice
from pathlib import Path

import pytest

from fitdocs import layout
from fitdocs.connectors import delivery
from fitdocs.wellness.probe import JSON_PROBE_LIMIT
from tests.fixtures.builder import FIT_TIMESTAMP_BASE

_DAY = (
    datetime(1989, 12, 31, tzinfo=UTC) + timedelta(seconds=FIT_TIMESTAMP_BASE)
).date()
_DATA = b'{"invented": [37, 91], "label": "snow \\u2603"}\n'
_FORMAT = "synthetic-wellness-7"
_ORIGINS = frozenset({"invented-watch-9", "sample-band-2"})


def test_public_constants() -> None:
    assert (
        delivery.MAX_WELLNESS_JSON_BYTES,
        delivery.FORMAT_NAME_PATTERN,
        tuple(delivery.WELLNESS_CHECKS),
        delivery.WELLNESS_CHECKS[".json"],
    ) == (
        JSON_PROBE_LIMIT,
        r"^[a-z0-9]+(-[a-z0-9]+)*$",
        (".json",),
        delivery._json_problem,
    )


@pytest.mark.parametrize(
    ("span", "suffix", "expected"),
    [
        (0, ".json", "2021-09-08_2021-09-08.json"),
        (13, ".JSON", "2021-09-08_2021-09-21.JSON"),
    ],
    ids=["one-day", "multi-day"],
)
def test_wellness_name(span: int, suffix: str, expected: str) -> None:
    assert (
        delivery.wellness_delivery_name(_DAY, _DAY + timedelta(days=span), suffix)
        == "wellness-" + expected
    )


@pytest.mark.parametrize("origins", [_ORIGINS, frozenset()], ids=["origins", "empty"])
@pytest.mark.parametrize(
    "data",
    [
        _DATA,
        '{"invented": "雪"}'.encode(),
        b"null",
        b"{}",
        b"[]",
        b"[37]",
        b'""',
        b'"synthetic"',
        b"37",
        b"0",
        b"0.5",
        b"0.0",
        b"true",
        b"false",
    ],
    ids=[
        "object",
        "unicode",
        "scalar",
        "empty-object",
        "empty-array",
        "array",
        "empty-string",
        "string",
        "integer",
        "zero-integer",
        "float",
        "zero-float",
        "true",
        "false",
    ],
)
def test_passing_package(origins: frozenset[str], data: bytes) -> None:
    assert delivery.wellness_package_problem(data, ".json", _FORMAT, origins) is None


@pytest.mark.parametrize(
    "format",
    [
        "a",
        "synthetic",
        "7",
        "synthetic7",
        "7synthetic",
        "synthetic-watch",
        "7-3",
        "watch-7",
        "7-watch",
    ],
    ids=[
        "minimum-alpha",
        "alpha",
        "numeric",
        "alpha-leading-mixed",
        "numeric-leading-mixed",
        "alpha-segments",
        "numeric-segments",
        "alpha-number-segments",
        "number-alpha-segments",
    ],
)
def test_valid_format_acceptance(format: str) -> None:
    assert delivery.wellness_package_problem(_DATA, ".json", format, _ORIGINS) is None


@pytest.mark.parametrize(
    "origin",
    [
        "a",
        "synthetic",
        "7",
        "synthetic7",
        "7synthetic",
        "synthetic-watch",
        "7-3",
        "watch-7",
        "7-watch",
    ],
    ids=[
        "minimum-alpha",
        "alpha",
        "numeric",
        "alpha-leading-mixed",
        "numeric-leading-mixed",
        "alpha-segments",
        "numeric-segments",
        "alpha-number-segments",
        "number-alpha-segments",
    ],
)
def test_valid_origin_acceptance(origin: str) -> None:
    assert (
        delivery.wellness_package_problem(_DATA, ".json", _FORMAT, frozenset({origin}))
        is None
    )


@pytest.mark.parametrize(
    "format",
    ["Bad-format", "valid!", "valid\n", "-bad", "bad-", "bad--tail", ""],
    ids=["uppercase", "trailing", "newline", "leading", "end", "double", "empty"],
)
def test_format_refusal(format: str) -> None:
    assert delivery.wellness_package_problem(_DATA, ".json", format, _ORIGINS) == (
        f"Wellness format {format!r} is not a lowercase slug."
    )


@pytest.mark.parametrize(
    "suffix", [".fit", ".csv", ".JSON"], ids=["fit", "csv", "case"]
)
def test_suffix_refusal(suffix: str) -> None:
    assert delivery.wellness_package_problem(_DATA, suffix, _FORMAT, _ORIGINS) == (
        f"No wellness check is available for extension {suffix!r}."
    )


@pytest.mark.parametrize(
    "invalid",
    ["Invalid-origin", "valid!", "valid\n", ""],
    ids=["uppercase", "trailing", "newline", "empty"],
)
def test_every_origin_refusal(invalid: str) -> None:
    origins = frozenset({"invented-valid-1", invalid, "other-valid-8"})
    assert delivery.wellness_package_problem(_DATA, ".json", _FORMAT, origins) == (
        f"Wellness origin {invalid!r} is not a lowercase slug."
    )


def test_invalid_origin_after_a_valid_origin() -> None:
    for index in range(128):
        invalid = f"Invalid-origin-{index}"
        origins = frozenset({f"valid-origin-{index}", f"other-valid-{index}", invalid})
        if next(iter(origins)) != invalid:
            break
    else:
        raise RuntimeError("Could not construct a valid-first origin iteration.")
    assert delivery.wellness_package_problem(_DATA, ".json", _FORMAT, origins) == (
        f"Wellness origin {invalid!r} is not a lowercase slug."
    )


def test_empty_data_refusal() -> None:
    assert delivery.wellness_package_problem(b"", ".json", _FORMAT, _ORIGINS) == (
        "Wellness package is empty."
    )


@pytest.mark.parametrize(
    "data",
    [b"not-json", b"{} {}", b"\xef\xbb\xbf{}", b'{"x":"\xff"}'],
    ids=["invalid", "two-documents", "bom", "utf8"],
)
def test_json_refusal(data: bytes) -> None:
    assert delivery.wellness_package_problem(data, ".json", _FORMAT, _ORIGINS) == (
        "Wellness package is not one well-formed UTF-8 JSON document."
    )


@pytest.mark.parametrize("size", [19, 20, 21], ids=["below", "exact", "over"])
def test_json_size_bound(monkeypatch: pytest.MonkeyPatch, size: int) -> None:
    monkeypatch.setattr(delivery, "MAX_WELLNESS_JSON_BYTES", 20)
    data = b'"' + b"a" * (size - 2) + b'"'
    expected = "Wellness JSON package exceeds 20 bytes." if size == 21 else None
    assert (
        delivery.wellness_package_problem(data, ".json", _FORMAT, _ORIGINS) == expected
    )


@pytest.mark.parametrize("tail", [b"", b"x"], ids=["exact", "over"])
def test_json_byte_size_bound(monkeypatch: pytest.MonkeyPatch, tail: bytes) -> None:
    monkeypatch.setattr(delivery, "MAX_WELLNESS_JSON_BYTES", 20)
    data = b'"' + "雪".encode() * 6 + tail + b'"'
    expected = "Wellness JSON package exceeds 20 bytes." if tail else None
    assert (
        delivery.wellness_package_problem(data, ".json", _FORMAT, _ORIGINS) == expected
    )


@pytest.mark.parametrize(
    ("data", "suffix", "format", "origins", "expected"),
    [
        (
            _DATA,
            ".csv",
            "Invalid-format",
            _ORIGINS,
            "Wellness format 'Invalid-format' is not a lowercase slug.",
        ),
        (
            _DATA,
            ".csv",
            _FORMAT,
            frozenset({"Bad-origin"}),
            "No wellness check is available for extension '.csv'.",
        ),
        (
            b"",
            ".json",
            _FORMAT,
            frozenset({"Bad-origin"}),
            "Wellness origin 'Bad-origin' is not a lowercase slug.",
        ),
        (b"", ".json", _FORMAT, _ORIGINS, "Wellness package is empty."),
    ],
    ids=[
        "format-before-suffix",
        "suffix-before-origin",
        "origin-before-empty",
        "empty-before-json",
    ],
)
def test_first_problem(
    data: bytes, suffix: str, format: str, origins: frozenset[str], expected: str
) -> None:
    assert delivery.wellness_package_problem(data, suffix, format, origins) == expected


def test_size_before_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(delivery, "MAX_WELLNESS_JSON_BYTES", 3)
    assert delivery.wellness_package_problem(
        b"\xffbad", ".json", _FORMAT, _ORIGINS
    ) == ("Wellness JSON package exceeds 3 bytes.")


def test_declared_extension_check(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[bytes] = []

    def check(data: bytes) -> str | None:
        seen.append(data)
        return "Synthetic third-extension problem."

    monkeypatch.setattr(
        delivery,
        "WELLNESS_CHECKS",
        {".a": lambda data: None, ".b": lambda data: "Other problem.", ".third": check},
    )
    result = delivery.wellness_package_problem(_DATA, ".third", _FORMAT, _ORIGINS)
    assert (seen, result) == ([_DATA], "Synthetic third-extension problem.")


@pytest.mark.parametrize(
    ("name", "suffix", "expected"),
    [
        (
            "Span.JsOn",
            ".json",
            [
                "Span.JsOn",
                "Span-abc123ef.json",
                "Span-abc123ef-2.json",
                "Span-abc123ef-3.json",
            ],
        ),
        (
            "Span.json",
            ".JSON",
            [
                "Span.json",
                "Span-abc123ef.JSON",
                "Span-abc123ef-2.JSON",
                "Span-abc123ef-3.JSON",
            ],
        ),
        (
            "Span.csv",
            ".json",
            [
                "Span.csv",
                "Span.csv-abc123ef.json",
                "Span.csv-abc123ef-2.json",
                "Span.csv-abc123ef-3.json",
            ],
        ),
        (
            "Span",
            ".json",
            [
                "Span",
                "Span-abc123ef.json",
                "Span-abc123ef-2.json",
                "Span-abc123ef-3.json",
            ],
        ),
    ],
    ids=["matching-case", "verbatim", "different-suffix", "no-suffix"],
)
def test_suffix_candidates(
    tmp_path: Path, name: str, suffix: str, expected: list[str]
) -> None:
    assert list(
        islice(delivery._candidates(tmp_path / name, "abc123ef987654", suffix), 4)
    ) == [tmp_path / item for item in expected]


@pytest.mark.parametrize("occupied", [1, 2], ids=["sha8", "sha8-2"])
def test_json_collision(tmp_path: Path, occupied: int) -> None:
    inbox = tmp_path / "inbox"
    directory = inbox / "invented-instance-4"
    directory.mkdir(parents=True)
    sha = hashlib.sha256(_DATA).hexdigest()
    primary = directory / "wellness-span.json"
    hashed = directory / f"wellness-span-{sha[:8]}.json"
    existing = [primary, hashed][:occupied]
    for index, path in enumerate(existing):
        path.write_bytes(b"invented-existing-" + str(index).encode())
        os.utime(path, ns=(111_000_000_000 + index, 222_000_000_000 + index))
    before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in existing]
    result = delivery.deliver(
        inbox, directory.name, primary.name, _DATA, sha, suffix=".json"
    )
    target = hashed if occupied == 1 else directory / f"wellness-span-{sha[:8]}-2.json"
    assert (
        result,
        target.read_bytes() if target.is_file() else None,
        [(path.read_bytes(), path.stat().st_mtime_ns) for path in existing],
    ) == (
        delivery.DeliveryResult(target.relative_to(inbox).as_posix(), True),
        _DATA,
        before,
    )


def test_json_owned_reuse(tmp_path: Path) -> None:
    directory = tmp_path / "invented-owner-6"
    directory.mkdir()
    path = directory / "same.json"
    path.write_bytes(_DATA)
    os.utime(path, ns=(333_000_000_000, 444_000_000_000))
    sha = hashlib.sha256(_DATA).hexdigest()
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    result = delivery.deliver(
        tmp_path,
        directory.name,
        path.name,
        _DATA,
        sha,
        owned={"invented-owner-6/same.json": sha},
        suffix=".json",
    )
    assert (result, path.read_bytes(), path.stat().st_mtime_ns) == (
        delivery.DeliveryResult("invented-owner-6/same.json", False),
        *before,
    )


def test_json_atomic_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replacements: list[tuple[str, str, bytes, bool]] = []
    link = os.link

    def observe(src: str | Path, dst: str | Path) -> None:
        source, destination = Path(src), Path(dst)
        replacements.append(
            (
                source.name,
                destination.relative_to(tmp_path).as_posix(),
                source.read_bytes(),
                destination.exists(),
            )
        )
        link(src, dst)

    monkeypatch.setattr(os, "link", observe)
    sha = hashlib.sha256(_DATA).hexdigest()
    result = delivery.deliver(
        tmp_path, "invented-atomic-5", "span.json", _DATA, sha, suffix=".json"
    )
    assert [
        (name.startswith(".span.json-"), rel, data, existed)
        for name, rel, data, existed in replacements
    ] == [(True, "invented-atomic-5/span.json", _DATA, False)]
    assert (
        result,
        (tmp_path / "invented-atomic-5/span.json").read_bytes(),
        sorted(path.name for path in (tmp_path / "invented-atomic-5").iterdir()),
    ) == (
        delivery.DeliveryResult("invented-atomic-5/span.json", True),
        _DATA,
        ["span.json"],
    )


@pytest.mark.parametrize(
    "state", ["absent", "directory", "file"], ids=["absent", "directory", "file"]
)
def test_wellness_archive_file_only(tmp_path: Path, state: str) -> None:
    sha = "7" * 64
    path = layout.wellness_archive_path(tmp_path, _FORMAT, sha, ".json")
    if state == "directory":
        path.mkdir(parents=True)
    elif state == "file":
        path.parent.mkdir(parents=True)
        path.write_bytes(b"invented-archive-17")
    assert delivery.wellness_archived(tmp_path, _FORMAT, sha, ".json") is (
        state == "file"
    )


@pytest.mark.parametrize(
    "decoy",
    ["fit", "format", "hash", "suffix", "root"],
    ids=["fit", "format", "hash", "suffix", "root"],
)
def test_wellness_archive_decoys(tmp_path: Path, decoy: str) -> None:
    sha = "8" * 64
    root = tmp_path / "declared-root"
    path = {
        "fit": layout.archive_path(root, sha),
        "format": layout.wellness_archive_path(root, "other-format-3", sha, ".json"),
        "hash": layout.wellness_archive_path(root, _FORMAT, "9" * 64, ".json"),
        "suffix": layout.wellness_archive_path(root, _FORMAT, sha, ".csv"),
        "root": layout.wellness_archive_path(
            tmp_path / "other-root", _FORMAT, sha, ".json"
        ),
    }[decoy]
    path.parent.mkdir(parents=True)
    path.write_bytes(b"invented-decoy-29")
    assert delivery.wellness_archived(root, _FORMAT, sha, ".json") is False


@pytest.mark.parametrize(
    ("root_name", "format", "sha", "suffix"),
    [
        ("first-root", "other-format-3", "6" * 64, ".csv"),
        ("second-root", "synthetic-format-4", "a" * 64, ".JSON"),
    ],
    ids=["alternate", "verbatim"],
)
def test_wellness_archive_parameters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    root_name: str,
    format: str,
    sha: str,
    suffix: str,
) -> None:
    root = tmp_path / root_name
    path = layout.wellness_archive_path(root, format, sha, suffix)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"invented-parameter-47")
    calls: list[tuple[Path, str, str, str]] = []
    compose = layout.wellness_archive_path

    def observed(root: Path, format: str, sha: str, suffix: str) -> Path:
        calls.append((root, format, sha, suffix))
        return compose(root, format, sha, suffix)

    monkeypatch.setattr(layout, "wellness_archive_path", observed)
    result = delivery.wellness_archived(root, format, sha, suffix)
    assert (result, calls) == (True, [(root, format, sha, suffix)])


def _sweep_observe(path: Path) -> tuple[bool, bytes | None, int | None]:
    present = path.is_file()
    return (
        present,
        path.read_bytes() if present else None,
        path.stat().st_mtime_ns if present else None,
    )


def _sweep_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@pytest.fixture
def mixed_sweep(tmp_path: Path) -> dict[str, object]:
    from copy import deepcopy
    from dataclasses import replace

    from fitdocs.connectors.ledger import (
        Ledger,
        LedgerEntry,
        Outcome,
        WellnessDayEntry,
        WellnessLedger,
        WellnessPending,
    )

    inbox, root = tmp_path / "inbox", tmp_path / "root"
    payloads = tuple(
        f'{{"invented": {n}}}\n'.encode() for n in (17, 83, 29, 61, 43, 97)
    )
    hashes = tuple(hashlib.sha256(data).hexdigest() for data in payloads)
    paths = (
        "sample/a-wait.json",
        "sample/c-settled.csv",
        "sample/e-remove.json",
        "sample/m-lost.json",
        "sample/z-changed.json",
    )
    records = tuple(
        WellnessPending(path, sha, fmt, suffix)
        for path, sha, fmt, suffix in zip(
            paths,
            hashes[:5],
            ("wait-1", "settled-2", "remove-3", "lost-4", "changed-5"),
            (".json", ".csv", ".json", ".json", ".json"),
            strict=True,
        )
    )
    days = tuple(
        WellnessDayEntry(_DAY + timedelta(days=offset), revision, hashes[index])
        for offset, revision, index in (
            (1, "settled-rev", 1),
            (4, "removed-rev", 2),
            (8, "lost-earliest", 3),
            (9, "superseded-rev", 4),
            (15, "wait-rev", 0),
            (20, "lost-later", 3),
            (24, "changed-rev", 4),
        )
    )
    activity_path = "sample/zz-activity.fit"
    activity = LedgerEntry(
        "activity-7",
        Outcome.DELIVERED,
        "activity-rev",
        hashes[5],
        pending=activity_path,
    )
    held = LedgerEntry("held-8", Outcome.ALREADY_HELD, "held-rev", hashes[0])
    watermark = datetime.combine(_DAY + timedelta(days=26), datetime.min.time(), UTC)
    origins = ("invented-band-2", "invented-watch-9")
    ledger = Ledger(
        "synthetic-sweep",
        watermark,
        (activity, held),
        WellnessLedger(_DAY + timedelta(days=30), origins, days, records),
    )
    original = deepcopy(ledger)
    for index in (1, 2, 4):
        record = records[index]
        _sweep_write(
            layout.wellness_archive_path(
                root, record.format, record.sha256, record.suffix
            ),
            payloads[index],
        )
    _sweep_write(layout.archive_path(root, hashes[0]), payloads[0])
    _sweep_write(layout.archive_path(root, hashes[5]), payloads[5])
    for index in (0, 2):
        _sweep_write(inbox / paths[index], payloads[index])
    _sweep_write(inbox / paths[4], b'{"invented": 131}\n')
    _sweep_write(inbox / activity_path, payloads[5])
    unknown = "sample/q-unowned.json"
    _sweep_write(inbox / unknown, payloads[2])
    before = {
        path: _sweep_observe(inbox / path) for path in (*paths, activity_path, unknown)
    }
    assert tuple(before[path][0] for path in paths) == (True, False, True, False, True)
    assert before[activity_path][0] and before[unknown][0]
    assert len(set(hashes)) == 6
    assert list(hashes[:5]) != sorted(hashes[:5])
    expected = Ledger(
        "synthetic-sweep",
        watermark,
        (replace(activity, pending=None), held),
        WellnessLedger(
            _DAY + timedelta(days=7),
            origins,
            (days[0], days[1], days[3], days[4], days[6]),
            (records[0],),
        ),
    )
    assert ledger != expected
    result = delivery.sweep(inbox, root, ledger)
    expected_files = dict(before)
    expected_files[paths[2]] = (False, None, None)
    expected_files[activity_path] = (False, None, None)
    return {
        "result": result,
        "ledger": ledger,
        "original": original,
        "expected": expected,
        "files": {path: _sweep_observe(inbox / path) for path in expected_files},
        "expected_files": expected_files,
    }


@pytest.mark.parametrize(
    "field",
    [
        "ledger",
        "removed",
        "failures",
        "original",
        "through",
        "origins",
        "days",
        "pending",
        "activity",
        "identity",
        "watermark",
    ],
)
def test_sweep_mixed_state(mixed_sweep: dict[str, object], field: str) -> None:
    from typing import cast

    from fitdocs.connectors.ledger import Ledger

    result = cast(delivery.SweepResult, mixed_sweep["result"])
    expected = cast(Ledger, mixed_sweep["expected"])
    ledger = cast(Ledger, mixed_sweep["ledger"])
    if field == "ledger":
        assert result.ledger == expected
    elif field == "removed":
        assert result.removed == ("sample/zz-activity.fit", "sample/e-remove.json")
    elif field == "failures":
        assert result.failures == ()
    elif field == "original":
        assert ledger == mixed_sweep["original"]
    elif field == "activity":
        assert result.ledger.entries == expected.entries
    elif field == "identity":
        assert result.ledger.connector_id == "synthetic-sweep"
    elif field == "watermark":
        assert result.ledger.watermark == expected.watermark
    else:
        assert getattr(result.ledger.wellness, field) == getattr(
            expected.wellness, field
        )


@pytest.mark.parametrize(
    "path",
    [
        "sample/a-wait.json",
        "sample/c-settled.csv",
        "sample/e-remove.json",
        "sample/m-lost.json",
        "sample/z-changed.json",
        "sample/zz-activity.fit",
        "sample/q-unowned.json",
    ],
)
def test_sweep_mixed_files(mixed_sweep: dict[str, object], path: str) -> None:
    from typing import cast

    actual = cast(dict[str, object], mixed_sweep["files"])
    expected = cast(dict[str, object], mixed_sweep["expected_files"])
    assert actual[path] == expected[path]


@pytest.fixture
def failing_sweep(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    from copy import deepcopy

    from fitdocs.connectors.ledger import (
        Ledger,
        WellnessDayEntry,
        WellnessLedger,
        WellnessPending,
    )

    inbox, root = tmp_path / "inbox", tmp_path / "root"
    paths = (
        "sample/a-earlier.json",
        "sample/c-read.json",
        "sample/m-remove.csv",
        "sample/z-later.csv",
    )
    payloads = tuple(f'{{"synthetic": {n}}}\n'.encode() for n in (241, 307, 419, 563))
    records = tuple(
        WellnessPending(path, hashlib.sha256(data).hexdigest(), fmt, suffix)
        for path, data, fmt, suffix in zip(
            paths,
            payloads,
            ("early-4", "read-7", "remove-9", "later-3"),
            (".json", ".json", ".csv", ".csv"),
            strict=True,
        )
    )
    days = tuple(
        WellnessDayEntry(_DAY + timedelta(days=n), "revision-" + str(n), p.sha256)
        for n, p in zip((11, 3, 17, 7), records, strict=True)
    )
    days = tuple(sorted(days, key=lambda d: d.day))
    state = WellnessLedger(
        _DAY + timedelta(days=25), ("invented-device-5",), days, records
    )
    ledger = Ledger(
        "failure-sweep", datetime.combine(_DAY, datetime.min.time(), UTC), (), state
    )
    original = deepcopy(ledger)
    for record, data in zip(records, payloads, strict=True):
        _sweep_write(inbox / record.path, data)
        _sweep_write(
            layout.wellness_archive_path(
                root, record.format, record.sha256, record.suffix
            ),
            data,
        )
    before = {path: _sweep_observe(inbox / path) for path in paths}
    assert all(value[0] for value in before.values())
    reader, remover = Path.read_bytes, delivery._remove

    def read(path: Path) -> bytes:
        if path == inbox / paths[1]:
            raise PermissionError("synthetic reader blocked 307")
        return reader(path)

    def remove(path: Path) -> None:
        if path == inbox / paths[2]:
            raise OSError("synthetic unlink blocked 419")
        remover(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(delivery, "_remove", remove)
    result = delivery.sweep(inbox, root, ledger)
    monkeypatch.setattr(Path, "read_bytes", reader)
    expected = Ledger(
        "failure-sweep",
        datetime.combine(_DAY, datetime.min.time(), UTC),
        (),
        WellnessLedger(
            _DAY + timedelta(days=25),
            ("invented-device-5",),
            days,
            (records[1], records[2]),
        ),
    )
    expected_files = {
        paths[0]: (False, None, None),
        paths[1]: before[paths[1]],
        paths[2]: before[paths[2]],
        paths[3]: (False, None, None),
    }
    return {
        "result": result,
        "expected": expected,
        "ledger": ledger,
        "original": original,
        "files": {path: _sweep_observe(inbox / path) for path in paths},
        "expected_files": expected_files,
    }


@pytest.mark.parametrize(
    "field",
    [
        "ledger",
        "removed",
        "failures",
        "original",
        "pending",
        "read-path",
        "read-reason",
        "remove-path",
        "remove-reason",
    ],
)
def test_sweep_failure_state(failing_sweep: dict[str, object], field: str) -> None:
    from typing import cast

    from fitdocs.connectors.ledger import Ledger

    result = cast(delivery.SweepResult, failing_sweep["result"])
    expected = cast(Ledger, failing_sweep["expected"])
    if field == "ledger":
        assert result.ledger == expected
    elif field == "removed":
        assert result.removed == ("sample/a-earlier.json", "sample/z-later.csv")
    elif field == "failures":
        assert result.failures == (
            ("sample/c-read.json", "PermissionError: synthetic reader blocked 307"),
            ("sample/m-remove.csv", "OSError: synthetic unlink blocked 419"),
        )
    elif field == "original":
        assert failing_sweep["ledger"] == failing_sweep["original"]
    elif field == "pending":
        assert result.ledger.wellness is not None and expected.wellness is not None
        assert result.ledger.wellness.pending == expected.wellness.pending
    else:
        index = 0 if field.startswith("read") else 1
        actual = result.failures[index] if len(result.failures) > index else None
        wanted = (
            ("sample/c-read.json", "PermissionError: synthetic reader blocked 307"),
            ("sample/m-remove.csv", "OSError: synthetic unlink blocked 419"),
        )[index]
        assert (
            actual is not None
            and actual[0 if field.endswith("path") else 1]
            == wanted[0 if field.endswith("path") else 1]
        )


@pytest.mark.parametrize(
    "path",
    [
        "sample/a-earlier.json",
        "sample/c-read.json",
        "sample/m-remove.csv",
        "sample/z-later.csv",
    ],
)
def test_sweep_failure_files(failing_sweep: dict[str, object], path: str) -> None:
    from typing import cast

    actual = cast(dict[str, object], failing_sweep["files"])
    expected = cast(dict[str, object], failing_sweep["expected_files"])
    assert actual[path] == expected[path]


@pytest.mark.parametrize(
    "through_offset", [None, 2, 30], ids=["unset", "earlier", "lowered"]
)
def test_sweep_forget_mark(tmp_path: Path, through_offset: int | None) -> None:
    from fitdocs.connectors.ledger import (
        Ledger,
        WellnessDayEntry,
        WellnessLedger,
        WellnessPending,
    )

    sha = hashlib.sha256(b'{"invented": 701}').hexdigest()
    record = WellnessPending("sample/lost.json", sha, "invented-4", ".json")
    through = None if through_offset is None else _DAY + timedelta(days=through_offset)
    state = WellnessLedger(
        through,
        ("invented-device-8",),
        (WellnessDayEntry(_DAY + timedelta(days=8), "lost-rev", sha),),
        (record,),
    )
    ledger = Ledger("mark-sweep", None, (), state)
    result = delivery.sweep(tmp_path / "inbox", tmp_path / "root", ledger)
    wanted = (
        None
        if through_offset is None
        else _DAY + timedelta(days=min(through_offset, 7))
    )
    assert result.ledger == Ledger(
        "mark-sweep", None, (), WellnessLedger(wanted, ("invented-device-8",))
    )


@pytest.mark.parametrize("wellness", [None, "empty"], ids=["none", "empty"])
def test_sweep_activity_without_wellness_pending(
    tmp_path: Path, wellness: str | None
) -> None:
    from fitdocs.connectors.ledger import (
        Ledger,
        LedgerEntry,
        Outcome,
        WellnessDayEntry,
        WellnessLedger,
    )

    sha = hashlib.sha256(b'{"invented": 809}').hexdigest()
    inbox, root = tmp_path / "inbox", tmp_path / "root"
    path = "sample/activity.fit"
    _sweep_write(inbox / path, b'{"invented": 809}')
    _sweep_write(layout.archive_path(root, sha), b'{"invented": 809}')
    state = (
        None
        if wellness is None
        else WellnessLedger(
            _DAY, ("invented-band-4",), (WellnessDayEntry(_DAY, "held-rev", sha),)
        )
    )
    before = _sweep_observe(inbox / path)
    assert before[0]
    entry = LedgerEntry(
        "activity-9", Outcome.DELIVERED, "activity-rev-9", sha, pending=path
    )
    result = delivery.sweep(
        inbox, root, Ledger("activity-sweep", None, (entry,), state)
    )
    assert (result, _sweep_observe(inbox / path)) == (
        delivery.SweepResult(
            Ledger(
                "activity-sweep",
                None,
                (LedgerEntry("activity-9", Outcome.DELIVERED, "activity-rev-9", sha),),
                state,
            ),
            (path,),
            (),
        ),
        (False, None, None),
    )


@pytest.mark.parametrize(
    "field",
    [
        "file",
        "ledger",
        "removed",
        "failures",
        "original",
        "pending",
        "days",
        "through",
        "origins",
    ],
)
def test_sweep_changed_file_with_matching_hash_prefix(
    tmp_path: Path, field: str
) -> None:
    from copy import deepcopy

    from fitdocs.connectors.ledger import (
        Ledger,
        WellnessDayEntry,
        WellnessLedger,
        WellnessPending,
    )

    delivered = b'{"synthetic-collision": 4681}\n'
    changed = b'{"synthetic-collision": 17312}\n'
    sha = hashlib.sha256(delivered).hexdigest()
    changed_sha = hashlib.sha256(changed).hexdigest()
    assert sha != changed_sha
    assert sha[:8] == changed_sha[:8]
    inbox, root = tmp_path / "inbox", tmp_path / "root"
    path = "sample/collision.json"
    record = WellnessPending(path, sha, "synthetic-collision-7", ".json")
    unrelated_sha = hashlib.sha256(b'{"unrelated-synthetic": 593}\n').hexdigest()
    days = (
        WellnessDayEntry(_DAY + timedelta(days=5), "retained-collision-rev", sha),
        WellnessDayEntry(
            _DAY + timedelta(days=13), "retained-other-rev", unrelated_sha
        ),
    )
    origins = ("invented-band-6", "invented-watch-3")
    through = _DAY + timedelta(days=20)
    ledger = Ledger(
        "collision-sweep", None, (), WellnessLedger(through, origins, days, (record,))
    )
    original = deepcopy(ledger)
    expected = Ledger(
        "collision-sweep",
        None,
        (),
        WellnessLedger(
            through,
            origins,
            (
                WellnessDayEntry(
                    _DAY + timedelta(days=5), "retained-collision-rev", sha
                ),
                WellnessDayEntry(
                    _DAY + timedelta(days=13), "retained-other-rev", unrelated_sha
                ),
            ),
        ),
    )
    assert ledger != expected
    _sweep_write(inbox / path, changed)
    _sweep_write(
        layout.wellness_archive_path(root, record.format, sha, record.suffix), delivered
    )
    before = _sweep_observe(inbox / path)
    assert before[0] and before[1] == changed
    result = delivery.sweep(inbox, root, ledger)
    if field == "file":
        assert _sweep_observe(inbox / path) == before
    elif field == "ledger":
        assert result.ledger == expected
    elif field == "removed":
        assert result.removed == ()
    elif field == "failures":
        assert result.failures == ()
    elif field == "original":
        assert ledger == original
    else:
        actual = (
            None
            if result.ledger.wellness is None
            else getattr(result.ledger.wellness, field)
        )
        assert actual == getattr(expected.wellness, field)
