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
    replace = os.replace

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
        replace(src, dst)

    monkeypatch.setattr(os, "replace", observe)
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
