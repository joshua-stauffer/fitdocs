from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from fitdocs.wellness import series
from fitdocs.wellness.model import Metric, SeriesValue


def test_year_golden() -> None:
    values = (
        SeriesValue(
            date(2025, 6, 17), Metric.RESTING_HR_BPM, "intervals-icu", None, 52.0, True
        ),
        SeriesValue(
            date(2025, 6, 17), Metric.HRV_SDNN_MS, "intervals-icu", "apple", 48.6, True
        ),
        SeriesValue(
            date(2025, 6, 16), Metric.HRV_SDNN_MS, "intervals-icu", None, 61.0, True
        ),
    )
    expected = (
        b"day,metric,source,origin,value,canonical\n"
        b"2025-06-16,hrv_sdnn_ms,intervals-icu,,61,true\n"
        b"2025-06-17,hrv_sdnn_ms,intervals-icu,apple,48.6,true\n"
        b"2025-06-17,resting_hr_bpm,intervals-icu,,52,true\n"
    )
    assert series.encode_year(values) == expected
    assert series.decode_year(Path("2025.csv"), expected) == tuple(reversed(values))


@pytest.mark.parametrize(
    "value,expected",
    [
        (52.0, "52"),
        (48.6, "48.6"),
        (1e20, "1e+20"),
        (float(2**53), "9007199254740992.0"),
    ],
)
def test_format(value: float, expected: str) -> None:
    assert series.format_value(value) == expected


@pytest.mark.parametrize(
    "header,row,line",
    [
        ("wrong", "2025-01-02,steps,garmin-export,,123,true", 1),
        (series.SERIES_HEADER, "2025-01-02,unknown,garmin-export,,123,true", 2),
        (series.SERIES_HEADER, "2025-02-30,steps,garmin-export,,123,true", 2),
        (series.SERIES_HEADER, "20250102,steps,garmin-export,,123,true", 2),
        (series.SERIES_HEADER, "2025-01-02,steps,garmin-export,,123,yes", 2),
        (series.SERIES_HEADER, "2025-01-02,steps,garmin-export,,123,true,extra", 2),
        (series.SERIES_HEADER, "2025-01-02,steps,garmin-export,,nan,true", 2),
        (series.SERIES_HEADER, "2025-01-02,steps,garmin-export,,123.0,true", 2),
        (series.SERIES_HEADER, "2025-01-02,steps,Garmin,,123,true", 2),
        (series.SERIES_HEADER, "2025-01-02,steps,garmin-export,Bad,123,true", 2),
    ],
    ids=[
        "header",
        "metric",
        "date",
        "date-format",
        "bool",
        "extra",
        "nan",
        "float-format",
        "source",
        "origin",
    ],
)
def test_decode_rejections(header: str, row: str, line: int) -> None:
    with pytest.raises(series.SeriesReadError) as error:
        series.decode_year(Path("wellness/2025.csv"), f"{header}\n{row}\n".encode())
    assert (error.value.path, error.value.line) == ("wellness/2025.csv", line)
    assert str(error.value).startswith(f"wellness/2025.csv:{line}:")


@pytest.mark.parametrize(
    "data",
    [
        b"\xff",
        b"\xef\xbb\xbfday,metric,source,origin,value,canonical\n",
        (series.SERIES_HEADER + "\r\n").encode(),
        series.SERIES_HEADER.encode(),
    ],
    ids=["utf8", "bom", "crlf", "missing-lf"],
)
def test_decode_bad_encoding_and_endings(data: bytes) -> None:
    with pytest.raises(series.SeriesReadError):
        series.decode_year(Path("2025.csv"), data)


def test_decode_unsorted_and_duplicate() -> None:
    row = "2025-01-02,steps,garmin-export,,123,true\n"
    earlier = "2025-01-01,steps,garmin-export,,321,true\n"
    for tail in (earlier, row):
        with pytest.raises(series.SeriesReadError):
            series.decode_year(
                Path("2025.csv"), (series.SERIES_HEADER + "\n" + row + tail).encode()
            )


def staged_values() -> tuple[SeriesValue, ...]:
    return (
        SeriesValue(
            date(2025, 1, 3), Metric.STEPS, "intervals-icu", "apple", 111, True
        ),
        SeriesValue(
            date(2024, 12, 31), Metric.STEPS, "intervals-icu", None, 222, False
        ),
        SeriesValue(
            date(2025, 1, 3), Metric.RESTING_HR_BPM, "garmin-export", "garmin", 53, True
        ),
        SeriesValue(
            date(2025, 1, 3), Metric.STEPS, "garmin-export", "garmin", 444, False
        ),
        SeriesValue(
            date(2024, 12, 31), Metric.STEPS, "garmin-export", "garmin", 555, True
        ),
    )


def test_builder_and_reader(tmp_path: Path) -> None:
    from tests.wellness.builders_series import write_series

    values = staged_values()
    paths = write_series(tmp_path, iter(values))
    assert tuple(path.relative_to(tmp_path).as_posix() for path in paths) == (
        "wellness/2024.csv",
        "wellness/2025.csv",
        "wellness/manifest.toml",
    )
    assert series.read_series(tmp_path).values == tuple(
        sorted(values, key=lambda value: (value.day, value.metric, value.source))
    )
    manifest = series.decode_manifest(paths[-1], paths[-1].read_bytes())
    if not isinstance(manifest, series.Manifest):
        raise RuntimeError("builder produced newer manifest")
    assert (manifest.inputs, manifest.entries) == ("staged-by-test", ())
    assert tuple(item.values for item in manifest.files) == (2, 3)
    from hashlib import sha256

    assert tuple(item.sha256 for item in manifest.files) == tuple(
        sha256(path.read_bytes()).hexdigest() for path in paths[:-1]
    )


def test_builder_bytes(tmp_path: Path) -> None:
    from tests.wellness.builders_series import write_series

    values = staged_values()
    write_series(tmp_path, values)
    for year in (2024, 2025):
        assert (tmp_path / f"wellness/{year}.csv").read_bytes() == series.encode_year(
            item for item in values if item.day.year == year
        )


@pytest.mark.parametrize("kind", ["duplicate", "zero", "two"])
def test_builder_refusals(tmp_path: Path, kind: str) -> None:
    from dataclasses import replace

    from tests.wellness.builders_series import write_series

    value = staged_values()[0]
    invalid = {
        "duplicate": (value, replace(value, canonical=False)),
        "zero": (replace(value, canonical=False),),
        "two": (value, replace(value, source="garmin-export", value=999)),
    }[kind]
    root = tmp_path / "uncreated"
    with pytest.raises(ValueError):
        write_series(root, invalid)
    assert not root.exists()


@pytest.mark.parametrize(
    "method,expected",
    [
        ("is_empty", False),
        ("days", (date(2024, 12, 31), date(2025, 1, 3))),
        ("for_day", (2, 3, 0)),
        ("canonical", 0),
        ("value", 0),
        ("sources", ("garmin-export", "intervals-icu")),
        ("by_source", (4, 3)),
        ("canonical_series", (4, 0)),
    ],
)
def test_lookup(method: str, expected: Any) -> None:
    values = staged_values()
    subject = series.WellnessSeries(
        tuple(sorted(values, key=lambda item: (item.day, item.metric, item.source)))
    )
    day = date(2025, 1, 3)
    metric = Metric.STEPS
    operations: dict[str, Callable[[], object]] = {
        "is_empty": lambda: subject.is_empty(),
        "days": lambda: subject.days(),
        "for_day": lambda: subject.for_day(day),
        "canonical": lambda: subject.canonical(metric, day),
        "value": lambda: subject.value(metric, day, "intervals-icu"),
        "sources": lambda: subject.sources(metric),
        "by_source": lambda: subject.by_source(metric, "garmin-export"),
        "canonical_series": lambda: subject.canonical_series(metric),
    }
    actual = operations[method]()
    if method in ("for_day", "by_source", "canonical_series"):
        expected = tuple(values[index] for index in expected)
    elif method in ("canonical", "value"):
        expected = values[expected]
    assert actual == expected


def test_absent_lookups() -> None:
    subject = series.WellnessSeries(staged_values())
    absent = date(2025, 1, 2)
    assert subject.value(Metric.STEPS, absent, "garmin-export") is None
    assert subject.canonical(Metric.STEPS, absent) is None
    assert subject.value(Metric.STEPS, date(2025, 1, 3), "missing") is None
    assert subject.canonical(Metric.WEIGHT_KG, date(2025, 1, 3)) is None
    assert subject.value(Metric.WEIGHT_KG, date(2025, 1, 3), "intervals-icu") is None


def test_sources_metric() -> None:
    subject = series.WellnessSeries(staged_values())
    assert subject.sources(Metric.RESTING_HR_BPM) == ("garmin-export",)


def test_missing_manifest(tmp_path: Path) -> None:
    assert series.read_series(tmp_path) == series.WellnessSeries()
    assert series.read_series(tmp_path).is_empty()
    assert series.series_files(tmp_path) == ()
    assert not tuple(tmp_path.iterdir())


def test_reader_listed_only_and_files(tmp_path: Path) -> None:
    from tests.wellness.builders_series import write_series

    paths = write_series(tmp_path, staged_values())
    (tmp_path / "wellness/1900.csv").write_bytes(b"invalid unlisted file")
    (tmp_path / "wellness-archive").mkdir()
    (tmp_path / "wellness-archive/decoy.json").write_bytes(b"invalid archive")
    assert series.read_series(tmp_path).values == tuple(
        sorted(staged_values(), key=lambda item: (item.day, item.metric, item.source))
    )
    assert series.series_files(tmp_path) == (paths[-1], *paths[:-1])
    paths[0].unlink()
    assert series.series_files(tmp_path) == (paths[-1], paths[1])
    with pytest.raises(series.SeriesReadError, match="2024.csv"):
        series.read_series(tmp_path)


def manifest_fixture() -> series.Manifest:
    from fitdocs.wellness.merge import Conflict

    return series.Manifest(
        "digest",
        ("garmin-export", "intervals-icu"),
        {Metric.STEPS: ("intervals-icu", "garmin-export")},
        (series.ManifestFile("wellness/2025.csv", "a" * 64, 12),),
        (
            series.ManifestEntry(
                "wellness-archive/garmin-uds/entry.json", "garmin-uds", 3, "superseded"
            ),
        ),
        (
            Conflict(
                date(2025, 1, 3),
                Metric.STEPS,
                "garmin-export",
                "kept.json",
                111.0,
                (("other.json", 222.0), ("third.json", 333.0)),
            ),
        ),
    )


def test_manifest_roundtrip() -> None:
    manifest = manifest_fixture()
    assert (
        series.decode_manifest(Path("manifest.toml"), series.encode_manifest(manifest))
        == manifest
    )


def test_manifest_schema() -> None:
    import tomllib

    manifest = manifest_fixture()
    data = series.encode_manifest(manifest)
    assert tomllib.loads(data.decode()) == {
        "generator": "fitdocs",
        "series_version": 1,
        "inputs": "digest",
        "precedence": {
            "default": ["garmin-export", "intervals-icu"],
            "metrics": {"steps": ["intervals-icu", "garmin-export"]},
        },
        "files": [{"path": "wellness/2025.csv", "sha256": "a" * 64, "values": 12}],
        "entries": [
            {
                "path": "wellness-archive/garmin-uds/entry.json",
                "format": "garmin-uds",
                "rules_version": 3,
                "state": "superseded",
            }
        ],
        "conflicts": [
            {
                "day": date(2025, 1, 3),
                "metric": "steps",
                "source": "garmin-export",
                "kept_entry": "kept.json",
                "kept_value": 111.0,
                "other_entries": ["other.json", "third.json"],
                "other_values": [222.0, 333.0],
            }
        ],
    }


def test_manifest_order() -> None:
    import tomllib

    data = series.encode_manifest(manifest_fixture())
    assert tuple(tomllib.loads(data.decode())) == (
        "generator",
        "series_version",
        "inputs",
        "precedence",
        "files",
        "entries",
        "conflicts",
    )


@pytest.mark.parametrize(
    "old,new",
    [
        ('generator = "fitdocs"', 'generator = "other"'),
        ("series_version = 1", "series_version = 0"),
        ("series_version = 1", "series_version = true"),
        ('path = "wellness/2025.csv"', 'path = "../2025.csv"'),
        ('sha256 = "' + "a" * 64 + '"', 'sha256 = "bad"'),
        ("values = 12", "values = -1"),
        ('state = "superseded"', 'state = "wrong"'),
        ("other_values = [\n    222.0,\n    333.0,\n]", "other_values = []"),
    ],
    ids=[
        "generator",
        "version",
        "version-type",
        "path",
        "digest",
        "count",
        "state",
        "parallel-arrays",
    ],
)
def test_manifest_rejections(old: str, new: str) -> None:
    data = series.encode_manifest(manifest_fixture()).decode()
    if old not in data:
        raise RuntimeError(f"fixture replacement absent: {old!r}")
    with pytest.raises(series.SeriesReadError, match="manifest.toml"):
        series.decode_manifest(Path("manifest.toml"), data.replace(old, new).encode())


def test_manifest_newer_and_invalid(tmp_path: Path) -> None:
    data = b'generator = "fitdocs"\nseries_version = 2\n'
    assert series.decode_manifest(Path("manifest.toml"), data) == series.NewerSeries(2)
    root = tmp_path / "wellness"
    root.mkdir()
    (root / "manifest.toml").write_bytes(data)
    with pytest.raises(series.SeriesReadError, match="newer series version 2"):
        series.read_series(tmp_path)
    (root / "manifest.toml").write_bytes(b"invalid")
    with pytest.raises(series.SeriesReadError, match="invalid manifest"):
        series.read_series(tmp_path)


def test_reader_io_errors(tmp_path: Path) -> None:
    from tests.wellness.builders_series import write_series

    path = tmp_path / "wellness/manifest.toml"
    path.mkdir(parents=True)
    with pytest.raises(series.SeriesReadError, match="manifest.toml"):
        series.read_series(tmp_path)
    path.rmdir()
    paths = write_series(tmp_path, staged_values())
    paths[0].unlink()
    paths[0].mkdir()
    with pytest.raises(series.SeriesReadError, match="2024.csv"):
        series.read_series(tmp_path)


def test_manifest_collection_order() -> None:
    from dataclasses import replace

    from fitdocs.wellness.merge import Conflict

    base = manifest_fixture()
    manifest = replace(
        base,
        metric_orders={
            Metric.STEPS: ("garmin-export",),
            Metric.HRV_SDNN_MS: ("intervals-icu",),
        },
        files=(base.files[0], series.ManifestFile("wellness/2024.csv", "b" * 64, 23)),
        entries=(
            base.entries[0],
            series.ManifestEntry(
                "wellness-archive/earlier.json", "intervals-icu", 2, "contributed"
            ),
        ),
        conflicts=(
            base.conflicts[0],
            Conflict(
                date(2024, 12, 31),
                Metric.STEPS,
                "intervals-icu",
                "early.json",
                444,
                (("late.json", 555),),
            ),
        ),
    )
    decoded = series.decode_manifest(
        Path("manifest.toml"), series.encode_manifest(manifest)
    )
    if not isinstance(decoded, series.Manifest):
        raise RuntimeError("unexpected newer manifest")
    assert (
        tuple(decoded.metric_orders),
        tuple(item.path for item in decoded.files),
        tuple(item.path for item in decoded.entries),
        tuple(item.day for item in decoded.conflicts),
    ) == (
        (Metric.HRV_SDNN_MS, Metric.STEPS),
        ("wellness/2024.csv", "wellness/2025.csv"),
        ("wellness-archive/earlier.json", "wellness-archive/garmin-uds/entry.json"),
        (date(2024, 12, 31), date(2025, 1, 3)),
    )


def test_reader_readonly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.wellness.builders_series import write_series

    paths = write_series(tmp_path, staged_values())
    reads: list[Path] = []
    original = Path.read_bytes

    def read(path: Path) -> bytes:
        reads.append(path)
        return original(path)

    def refuse(*args: object, **kwargs: object) -> None:
        raise RuntimeError("reader attempted write")

    def snapshot() -> dict[str, tuple[bytes, int]]:
        return {
            path.relative_to(tmp_path).as_posix(): (
                path.read_bytes(),
                path.stat().st_mtime_ns,
            )
            for path in sorted(tmp_path.rglob("*"))
            if path.is_file()
        }

    before = snapshot()
    with monkeypatch.context() as recording:
        recording.setattr(Path, "read_bytes", read)
        recording.setattr(Path, "write_bytes", refuse)
        recording.setattr(Path, "mkdir", refuse)
        series.read_series(tmp_path)
        assert tuple(reads) == (paths[-1], *paths[:-1])
    assert snapshot() == before


def test_inputs_digest_canonical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib
    import json
    from dataclasses import replace

    from fitdocs.wellness import registry
    from fitdocs.wellness.archive import ArchiveEntry, ArchiveListing, Orphan
    from fitdocs.wellness.settings import (
        DEFAULT_WELLNESS_SETTINGS,
        WellnessSettings,
        effective_order,
    )

    forms = registry.FORMATS
    entries = tuple(
        ArchiveEntry(forms[0], token * 64, tmp_path / token, token)
        for token in ("z", "a")
    )
    listing = ArchiveListing(entries, ())
    expected = {
        "series_version": 1,
        "formats": sorted([[f.id, f.rules_version] for f in forms]),
        "entries": ["a", "z"],
        "precedence": {
            m.value: list(effective_order(DEFAULT_WELLNESS_SETTINGS, m)) for m in Metric
        },
    }
    digest = series.inputs_digest(listing, DEFAULT_WELLNESS_SETTINGS)
    assert (
        digest
        == hashlib.sha256(
            json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    assert (
        series.inputs_digest(
            ArchiveListing(tuple(reversed(entries)), (Orphan("x", "unknown"),)),
            DEFAULT_WELLNESS_SETTINGS,
        )
        == digest
    )
    monkeypatch.setattr(registry, "FORMATS", tuple(reversed(forms)))
    assert series.inputs_digest(listing, DEFAULT_WELLNESS_SETTINGS) == digest
    monkeypatch.setattr(
        registry, "FORMATS", (*forms[:-1], replace(forms[-1], rules_version=7))
    )
    assert series.inputs_digest(listing, DEFAULT_WELLNESS_SETTINGS) != digest
    monkeypatch.setattr(registry, "FORMATS", forms)
    assert (
        series.inputs_digest(ArchiveListing(entries[:1], ()), DEFAULT_WELLNESS_SETTINGS)
        != digest
    )
    assert (
        series.inputs_digest(listing, WellnessSettings(("intervals-icu",), {}))
        != digest
    )
    assert (
        series.inputs_digest(
            listing, WellnessSettings((), {Metric.WEIGHT_KG: ("intervals-icu",)})
        )
        != digest
    )
