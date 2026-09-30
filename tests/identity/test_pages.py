"""Tests for the page scan (Req 3.9, 3.10, 7.4).

The scenarios mirror the ``find_document`` tests in ``tests/test_sync.py``
(session UUID before sources, first in path order, symlink refused, a garbled
neighbour skipped), asserted here against the index directly. Files are written
in an order that is not their sorted order and the values that tell two pages
apart differ pairwise; what reds is: records come out in path order, and the
first match in path order wins (a later-wins pick reds). A scan-side reversal
alone does not red, because ``PageIndex`` re-sorts its records.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.identity.kinds import SourceKind
from fitdocs.identity.matching import SessionKey, pair_evidence
from fitdocs.identity.pages import page_record, scan_pages
from fitdocs.identity.planning import duplicate_sets
from fitdocs.layout import WORKOUTS_DIR

_SESSION = "00010203-0405-0607-0809-0a0b0c0d0e0f"
_OTHER_SESSION = "ffffffff-0405-0607-0809-0a0b0c0d0e0f"
_REF = "fit-archive/" + ("a" * 64) + ".fit"
_OTHER_REF = "fit-archive/" + ("b" * 64) + ".fit"
_START = datetime(2026, 7, 12, 7, 30, 0, tzinfo=UTC)
_DEVICE = "0123456789abcdef"


def _md(
    *,
    session: str | None = None,
    sources: Sequence[str] = (),
    workout: bool = True,
    extra: dict[str, object] | None = None,
    omit: Sequence[str] = (),
) -> str:
    data: dict[str, object] = {"title": "Run"}
    if workout:
        data["type"] = "workout"
    data["doc_version"] = 1
    if session is not None:
        data["uuid"] = session
    data["sport"] = "Run"
    data["start_time"] = _START.isoformat()
    if sources:
        data["sources"] = list(sources)
    if extra:
        data.update(extra)
    for key in omit:
        del data[key]
    dumped = yaml.safe_dump(data, sort_keys=False)
    return f"---\n{dumped}---\n\nbody\n"


def _write(root: Path, name: str, text: str) -> Path:
    workouts = root / "workouts"
    workouts.mkdir(parents=True, exist_ok=True)
    path = workouts / name
    path.write_text(text, encoding="utf-8")
    return path


def _key(
    *,
    elapsed_s: float | None = 3000.0,
    distance_m: float | None = 10_000.0,
    device: str | None = None,
    kind: SourceKind | None = SourceKind.ORIGINAL,
) -> SessionKey:
    return SessionKey("Run", _START, elapsed_s, distance_m, device, kind)


def test_session_uuid_wins_over_sources(tmp_path: Path) -> None:
    # The sources page sorts first and is written last.
    uuid_page = _write(tmp_path, "zzz.md", _md(session=_SESSION, sources=[_OTHER_REF]))
    _write(tmp_path, "aaa.md", _md(sources=[_REF]))
    found = scan_pages(tmp_path).exact_match(_SESSION, _REF)
    assert found is not None
    assert found.path == str(uuid_page)
    assert found.sources == (_OTHER_REF,)


def test_sources_match_when_no_page_holds_the_uuid(tmp_path: Path) -> None:
    page = _write(tmp_path, "m.md", _md(sources=[_OTHER_REF, _REF]))
    found = scan_pages(tmp_path).exact_match(_SESSION, _REF)
    assert found is not None
    assert found.path == str(page)
    assert found.sources == (_OTHER_REF, _REF)


def test_first_in_path_order_wins(tmp_path: Path) -> None:
    _write(tmp_path, "ccc.md", _md(session=_SESSION, sources=[_REF]))
    first = _write(tmp_path, "aaa.md", _md(session=_SESSION, sources=[_OTHER_REF]))
    _write(tmp_path, "bbb.md", _md(session=_SESSION, sources=[_REF, _OTHER_REF]))
    found = scan_pages(tmp_path).exact_match(_SESSION, "fit-archive/none.fit")
    assert found is not None
    assert found.path == str(first)


def test_first_sources_match_in_path_order_wins(tmp_path: Path) -> None:
    _write(tmp_path, "ccc.md", _md(sources=[_REF]))
    first = _write(tmp_path, "aaa.md", _md(sources=[_OTHER_REF, _REF]))
    found = scan_pages(tmp_path).exact_match(None, _REF)
    assert found is not None
    assert found.path == str(first)


def test_records_are_in_path_order(tmp_path: Path) -> None:
    for name in ("ccc.md", "aaa.md", "bbb.md"):
        _write(tmp_path, name, _md(sources=[_REF]))
    records = scan_pages(tmp_path).records
    assert [Path(r.path).name for r in records] == ["aaa.md", "bbb.md", "ccc.md"]


def test_symlink_is_refused(tmp_path: Path) -> None:
    real = _write(tmp_path / "elsewhere", "real.md", _md(session=_SESSION))
    workouts = tmp_path / "workouts"
    workouts.mkdir()
    (workouts / "aaa-link.md").symlink_to(real)
    assert scan_pages(tmp_path).records == ()
    assert scan_pages(tmp_path).exact_match(_SESSION, _REF) is None


def test_symlink_does_not_shadow_a_regular_page(tmp_path: Path) -> None:
    real = _write(tmp_path / "elsewhere", "real.md", _md(session=_SESSION))
    page = _write(tmp_path, "zzz.md", _md(session=_SESSION, sources=[_REF]))
    (tmp_path / "workouts" / "aaa-link.md").symlink_to(real)
    found = scan_pages(tmp_path).exact_match(_SESSION, _REF)
    assert found is not None
    assert found.path == str(page)


def test_garbled_neighbour_is_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "aaa.md", "---\n: : [unterminated\n---\nbody\n")
    _write(tmp_path, "bbb.md", "no frontmatter at all\n")
    (tmp_path / "workouts" / "ccc.md").write_bytes(b"\xff\xfe---\n")
    page = _write(tmp_path, "ddd.md", _md(session=_SESSION))
    records = scan_pages(tmp_path).records
    assert [r.path for r in records] == [str(page)]


def test_non_workout_files_are_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "aaa.md", _md(session=_SESSION, workout=False))
    _write(tmp_path, "bbb.txt", _md(session=_SESSION))
    nested = tmp_path / "workouts" / "sub"
    nested.mkdir()
    (nested / "ccc.md").write_text(_md(session=_SESSION), encoding="utf-8")
    assert scan_pages(tmp_path).records == ()


def test_declaration_file_is_never_a_record(tmp_path: Path) -> None:
    from fitdocs.declaration import declaration_text

    _write(tmp_path, DECLARATION_FILENAME, declaration_text(f"{WORKOUTS_DIR}/"))
    assert scan_pages(tmp_path).records == ()


def test_absent_workouts_directory_is_an_empty_index(tmp_path: Path) -> None:
    index = scan_pages(tmp_path)
    assert index.records == ()
    assert index.exact_match(_SESSION, _REF) is None


def test_edited_uuid_holding_a_sha_still_matches_exactly(tmp_path: Path) -> None:
    sha = "c" * 64
    page = _write(tmp_path, "a.md", _md(session=sha))
    found = scan_pages(tmp_path).exact_match(sha, _REF)
    assert found is not None
    assert found.path == str(page)


def test_empty_recorded_uuid_reads_as_none(tmp_path: Path) -> None:
    _write(tmp_path, "a.md", _md(session=""))
    (record,) = scan_pages(tmp_path).records
    assert record.session_uuid is None


def test_record_key_of_a_page_with_identity_keys(tmp_path: Path) -> None:
    identity: dict[str, object] = {
        "source_kind": "phone_copy",
        "source_elapsed_s": 3001.5,
        "source_distance_m": 10_002.25,
        "source_device": _DEVICE,
    }
    path = _write(tmp_path, "a.md", _md(session=_SESSION, extra=identity))
    (record,) = scan_pages(tmp_path).records
    assert record.path == str(path)
    assert record.session_uuid == _SESSION
    assert record.key.sport == "Run"
    assert record.key.start == _START
    assert record.key.elapsed_s == 3001.5
    assert record.key.distance_m == 10_002.25
    assert record.key.device == _DEVICE
    assert record.key.kind is SourceKind.PHONE_COPY


def test_unknown_recorded_kind_reads_as_none(tmp_path: Path) -> None:
    _write(tmp_path, "a.md", _md(extra={"source_kind": "carrier_pigeon"}))
    (record,) = scan_pages(tmp_path).records
    assert record.key.kind is None


def _legacy_records(root: Path) -> tuple[SessionKey, SessionKey]:
    # Legacy pages carry every value an activity-derived key would read, in
    # other spellings, so a key built from any of them shows up as not-None.
    extra: dict[str, object] = {
        "distance_km": 10.0,
        "duration_s": 3000,
        "elapsed_s": 3000,
        "device": _DEVICE,
    }
    _write(root, "a.md", _md(session=_SESSION, sources=[_REF], extra=extra))
    _write(root, "b.md", _md(session=_OTHER_SESSION, sources=[_OTHER_REF], extra=extra))
    first, second = scan_pages(root).records
    return first.key, second.key


def test_legacy_page_key_has_no_identity_values(tmp_path: Path) -> None:
    first, _ = _legacy_records(tmp_path)
    assert first.sport == "Run"
    assert first.start == _START
    assert first.elapsed_s is None
    assert first.distance_m is None
    assert first.device is None
    assert first.kind is None


def test_legacy_page_matches_nothing_by_rule(tmp_path: Path) -> None:
    first, second = _legacy_records(tmp_path)
    assert pair_evidence(first, second) is None
    assert pair_evidence(second, first) is None
    for other in (
        _key(),
        _key(device=_DEVICE),
        _key(kind=SourceKind.PHONE_COPY),
        _key(elapsed_s=None, distance_m=None),
    ):
        assert pair_evidence(first, other) is None
        assert pair_evidence(other, first) is None


def test_page_without_start_matches_nothing() -> None:
    # Everything but the start agrees with ``_key()``, so only the missing start
    # keeps the pair from matching.
    record = page_record(
        Path("x.md"),
        {
            "type": "workout",
            "sport": "Run",
            "source_kind": "original",
            "source_elapsed_s": 3000.0,
            "source_distance_m": 10_000.0,
        },
    )
    assert record.key.sport == "Run"
    assert record.key.start is None
    assert record.session_uuid is None
    assert record.sources == ()
    assert pair_evidence(record.key, _key()) is None
    assert pair_evidence(_key(), record.key) is None


def test_pages_without_a_usable_sport_link_to_nothing(tmp_path: Path) -> None:
    identity: dict[str, object] = {
        "source_kind": "original",
        "source_elapsed_s": 3000.0,
        "source_distance_m": 10_000.0,
        "source_device": _DEVICE,
    }
    # Each kind of unusable sport twice, so that two pages of the same kind
    # are compared with each other as well as with the other kinds.
    variants: list[dict[str, object]] = [
        {},
        {},
        {"sport": 7},
        {"sport": 7},
        {"sport": ""},
        {"sport": ""},
    ]
    names = ("p4.md", "p1.md", "p6.md", "p2.md", "p5.md", "p3.md")
    refs = [f"fit-archive/{c * 64}.fit" for c in "cdefgh"]
    uuids = [f"00000000-0000-0000-0000-00000000000{n}" for n in range(1, 7)]
    for name, variant, page_uuid, ref in zip(names, variants, uuids, refs, strict=True):
        omit = () if variant else ("sport",)
        text = _md(
            session=page_uuid, sources=[ref], extra={**identity, **variant}, omit=omit
        )
        if not variant:
            assert "sport:" not in text
        _write(tmp_path, name, text)
    index = scan_pages(tmp_path)
    assert len(index.records) == 6
    for i, a in enumerate(index.records):
        for b in index.records[i + 1 :]:
            assert pair_evidence(a.key, b.key) is None
            assert pair_evidence(b.key, a.key) is None
    assert duplicate_sets(index) == ()
    for page_uuid, ref in zip(uuids, refs, strict=True):
        by_uuid = index.exact_match(page_uuid, "fit-archive/none.fit")
        by_ref = index.exact_match(None, ref)
        assert by_uuid is not None and by_uuid.session_uuid == page_uuid
        assert by_ref is not None and by_ref.sources == (ref,)


@pytest.mark.parametrize("bad", [-1.0, float("nan"), True, "3000"])
def test_unusable_recorded_numbers_read_as_none(bad: object) -> None:
    record = page_record(
        Path("x.md"),
        {"type": "workout", "source_elapsed_s": bad, "source_distance_m": bad},
    )
    assert record.key.elapsed_s is None
    assert record.key.distance_m is None
