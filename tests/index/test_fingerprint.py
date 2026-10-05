from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fitdocs.contract import (
    DOC_VERSION_KEY,
    LOAD_KEYS,
    PRESERVED_REGIONS,
    frontmatter_close_index,
    parse_frontmatter,
)
from fitdocs.docmerge import end_marker, extract_regions, region_block
from fitdocs.index.producer import CorpusSnapshot, Rows
from fitdocs.index.schema import SCHEMA_VERSION, TableSpec
from fitdocs.metrics.types import AthleteInputs, TrimpWeighting, ZoneSpec


def _fingerprint_module() -> Any:
    return importlib.import_module("fitdocs.index.fingerprint")


@pytest.fixture(scope="module")
def rendered_page() -> str:
    from tests.render.test_golden_docs import _render

    return _render("strength_no_sets").markdown


def _frontmatter(page: str) -> dict[str, object]:
    parsed = parse_frontmatter(page)
    assert parsed is not None
    return parsed


def _replace_frontmatter(page: str, key: str, value: object) -> str:
    parsed = _frontmatter(page)
    lines = page.split("\n")
    close = frontmatter_close_index(lines)
    assert close is not None
    parsed[key] = value
    encoded = yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True).rstrip("\n")
    edited = "\n".join([lines[0], encoded, lines[close], *lines[close + 1 :]])
    assert edited.encode("utf-8") != page.encode("utf-8")
    assert _frontmatter(edited)[key] == value
    return edited


def _replace_region(page: str, region_id: str, content: str) -> str:
    regions = extract_regions(page)
    assert region_id in PRESERVED_REGIONS
    assert region_id in regions
    old_block = region_block(region_id, regions[region_id])
    new_block = region_block(region_id, content)
    assert old_block != new_block
    if old_block in page:
        edited = page.replace(old_block, new_block, 1)
    else:
        # The grammar also accepts a final end marker at EOF without its LF.
        old_at_eof = old_block[:-1]
        new_at_eof = new_block[:-1]
        assert old_at_eof in page
        edited = page.replace(old_at_eof, new_at_eof, 1)
    assert edited.encode("utf-8") != page.encode("utf-8")
    assert extract_regions(edited)[region_id] == content
    return edited


def _render_digest(page: str) -> str:
    return cast(str, _fingerprint_module().render_fingerprint(page, _frontmatter(page)))


def test_document_fingerprint_hashes_path_and_page_bytes() -> None:
    fingerprint = _fingerprint_module().document_fingerprint
    path = "2021-09-07-run-1946.md"
    data = b"rendered-page-bytes\x00"
    expected = hashlib.sha256(path.encode("utf-8") + b"\0" + data).hexdigest()

    assert fingerprint(path, data) == expected
    changed_data = data[:-1] + b"!"
    assert changed_data != data
    assert fingerprint(path, changed_data) != expected
    renamed = "archive/2021-09-07-run-1946.md"
    assert renamed != path
    assert fingerprint(renamed, data) != expected


def test_render_fingerprint_has_independent_canonical_digest() -> None:
    page = (
        "---\ntitle: Pinned\nload_value: 11\ncustom_key: user\n---\n"
        "# Entry\n"
        "<!-- fitdocs:begin:notes -->\nprivate-note\n"
        "<!-- fitdocs:end:notes -->\n"
        "<!-- fitdocs:begin:workout -->\nprivate-workout\n"
        "<!-- fitdocs:end:workout -->\n"
        "<!-- fitdocs:begin:load -->\nprivate-load\n"
        "<!-- fitdocs:end:load -->\n"
        "Tail\n"
    )
    frontmatter = {
        "title": "Pinned",
        "load_value": 11,
        "custom_key": "user",
    }
    expected_json = (
        b'{"body":"# Entry\\n'
        b"<!-- fitdocs:begin:notes -->\\n\\n<!-- fitdocs:end:notes -->\\n"
        b"<!-- fitdocs:begin:workout -->\\n\\n<!-- fitdocs:end:workout -->\\n"
        b"<!-- fitdocs:begin:load -->\\n\\n<!-- fitdocs:end:load -->\\n"
        b'Tail\\n","managed":{"title":"Pinned"}}'
    )
    expected = hashlib.sha256(expected_json).hexdigest()

    assert _fingerprint_module().render_fingerprint(page, frontmatter) == expected


def test_render_fingerprint_includes_complete_managed_payload() -> None:
    expected_managed: dict[str, object] = {
        "title": "Synthetic activity",
        "type": "workout",
        "generator": "fitdocs",
        "doc_version": 9,
        "uuid": "synthetic-uuid",
        "date": "2026-10-05",
        "start_time": "2026-10-05T07:08:09",
        "sport": "running",
        "modality": "run",
        "indoor": False,
        "distance_km": 5.25,
        "moving_time": 1200,
        "avg_hr_bpm": 141,
        "avg_power_w": 220,
        "elevation_gain_m": 31.5,
        "calories_kcal": 305,
        "source_kind": "fit",
        "source_elapsed_s": 1210.25,
        "source_distance_m": 5250.0,
        "source_device": "sha256:" + "a" * 64,
        "sources": ["archive:sha256:" + "b" * 64],
    }
    frontmatter = {
        **expected_managed,
        "effort": "race",
        "load_value": 42.0,
        "custom_unmanaged": "ignored",
    }
    expected_payload = {
        "body": "# Managed payload\n",
        "managed": expected_managed,
    }
    expected_json = json.dumps(
        expected_payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    expected = hashlib.sha256(expected_json).hexdigest()

    assert (
        _fingerprint_module().render_fingerprint("# Managed payload\n", frontmatter)
        == expected
    )


def test_render_fingerprint_serializes_non_json_values_with_default_str() -> None:
    page = "---\ntitle: Pinned\n---\n# Typed\n"
    frontmatter = {"title": date(2026, 10, 5)}
    expected = hashlib.sha256(
        b'{"body":"# Typed\\n","managed":{"title":"2026-10-05"}}'
    ).hexdigest()

    assert _fingerprint_module().render_fingerprint(page, frontmatter) == expected


def test_render_fingerprint_signature_does_not_include_a_path() -> None:
    function = _fingerprint_module().render_fingerprint

    assert tuple(inspect.signature(function).parameters) == ("text", "frontmatter")


def test_render_fingerprint_ignores_frontmatter_owned_outside_rendering(
    rendered_page: str,
) -> None:
    original = rendered_page
    original_fingerprint = _render_digest(original)
    changes: list[tuple[str, object]] = [
        ("effort", "race"),
        ("effort_distance_m", 5000.0),
        ("effort_time_s", 1200.0),
        ("effort_event", "Synthetic Run"),
        ("agent_custom", "keep"),
    ]
    for key in LOAD_KEYS:
        new_value: object = 147.25 if key == "load_value" else f"changed-{key}"
        changes.append((key, new_value))

    for key, value in changes:
        edited = _replace_frontmatter(original, key, value)
        edited_frontmatter = _frontmatter(edited)
        assert edited_frontmatter[key] == value
        assert _render_digest(edited) == original_fingerprint


@pytest.mark.parametrize(
    "region_id", ("notes", "workout", "load"), ids=lambda value: value
)
def test_render_fingerprint_ignores_each_region(
    rendered_page: str, region_id: str
) -> None:
    original_fingerprint = _render_digest(rendered_page)
    edited = _replace_region(rendered_page, region_id, f"edit-{region_id}-body")

    assert _render_digest(edited) == original_fingerprint


def test_render_fingerprint_ignores_region_ending_at_eof(
    rendered_page: str,
) -> None:
    marker = end_marker("load")
    marker_start = rendered_page.rfind(marker)
    assert marker_start >= 0
    eof_region_page = rendered_page[: marker_start + len(marker)]
    assert not eof_region_page.endswith("\n")
    assert extract_regions(eof_region_page)["load"]
    original_fingerprint = _render_digest(eof_region_page)

    edited = _replace_region(eof_region_page, "load", "edited EOF load region")

    assert _render_digest(edited) == original_fingerprint


def test_render_fingerprint_keeps_unmanaged_region_content(
    rendered_page: str,
) -> None:
    original = rendered_page + region_block("future", "user content")
    edited = rendered_page + region_block("future", "edited content")
    assert original.encode("utf-8") != edited.encode("utf-8")
    assert extract_regions(original)["future"] == "user content"
    assert extract_regions(edited)["future"] == "edited content"

    assert _render_digest(edited) != _render_digest(original)


@pytest.mark.parametrize(
    ("kind", "key"),
    (("title", "title"), ("sources", "sources"), ("doc_version", DOC_VERSION_KEY)),
    ids=("title", "sources", "doc-version"),
)
def test_render_fingerprint_moves_for_managed_frontmatter(
    rendered_page: str, kind: str, key: str
) -> None:
    parsed = _frontmatter(rendered_page)
    old = parsed[key]
    if kind == "title":
        new: object = f"Changed {old}"
    elif kind == "sources":
        new = ["archive:sha256:" + "a" * 64, "archive:sha256:" + "b" * 64]
    else:
        assert isinstance(old, int)
        new = old + 1
    edited = _replace_frontmatter(rendered_page, key, new)

    assert _render_digest(edited) != _render_digest(rendered_page)


def test_render_fingerprint_moves_for_body_outside_preserved_regions(
    rendered_page: str,
) -> None:
    edited = rendered_page + "A distinct body line outside preserved regions.\n"
    assert edited.encode("utf-8") != rendered_page.encode("utf-8")

    assert _render_digest(edited) != _render_digest(rendered_page)


def test_render_fingerprint_does_not_use_a_renamed_page_path(
    rendered_page: str, tmp_path: Path
) -> None:
    original_path = tmp_path / "pages" / "old-name.md"
    renamed_path = tmp_path / "archive" / "new-name.md"
    original_path.parent.mkdir()
    renamed_path.parent.mkdir()
    page_bytes = rendered_page.encode("utf-8")
    original_path.write_bytes(page_bytes)
    assert original_path.exists()
    assert original_path.read_bytes() == page_bytes
    original_render_fingerprint = _render_digest(original_path.read_text("utf-8"))
    document_fingerprint = _fingerprint_module().document_fingerprint
    original_document_fingerprint = document_fingerprint(
        str(original_path), original_path.read_bytes()
    )

    original_path.rename(renamed_path)

    assert not original_path.exists()
    assert renamed_path.exists()
    renamed_bytes = renamed_path.read_bytes()
    assert renamed_bytes == page_bytes
    renamed_page = renamed_bytes.decode("utf-8")
    assert document_fingerprint(str(renamed_path), renamed_bytes) != (
        original_document_fingerprint
    )
    assert _render_digest(renamed_page) == original_render_fingerprint


def _baseline_athlete() -> AthleteInputs:
    return AthleteInputs(
        ftp_watts=231.25,
        resting_hr_bpm=58,
        max_hr_bpm=193,
        hr_zones=ZoneSpec((110.5, 132.75)),
        power_zones=ZoneSpec((95.0, 237.5)),
        pace_zones=ZoneSpec((249.25, 330.5)),
        trimp_weighting=TrimpWeighting.BANISTER_MALE,
    )


def _changed_athlete(base: AthleteInputs, field_name: str) -> AthleteInputs:
    changes = {
        "ftp_watts": replace(base, ftp_watts=231.5),
        "resting_hr_bpm": replace(base, resting_hr_bpm=59),
        "max_hr_bpm": replace(base, max_hr_bpm=194),
        "hr_zones": replace(base, hr_zones=ZoneSpec((111.5, 133.75))),
        "power_zones": replace(base, power_zones=ZoneSpec((96.0, 239.0))),
        "pace_zones": replace(base, pace_zones=ZoneSpec((250.0, 332.0))),
        "trimp_weighting": replace(
            base, trimp_weighting=TrimpWeighting.BANISTER_FEMALE
        ),
    }
    return changes[field_name]


@pytest.mark.parametrize(
    "field_name",
    (
        "ftp_watts",
        "resting_hr_bpm",
        "max_hr_bpm",
        "hr_zones",
        "power_zones",
        "pace_zones",
        "trimp_weighting",
    ),
)
def test_athlete_fingerprint_moves_for_each_field(field_name: str) -> None:
    fingerprint = _fingerprint_module().athlete_fingerprint
    base = _baseline_athlete()
    changed = _changed_athlete(base, field_name)
    assert getattr(base, field_name) != getattr(changed, field_name)

    assert fingerprint(changed) != fingerprint(base)


def test_athlete_fingerprint_serialization_has_independent_expected_digest() -> None:
    inputs = _baseline_athlete()
    expected_json = (
        b'["231.25",58,193,["110.5","132.75"],'
        b'["95.0","237.5"],["249.25","330.5"],"banister_male"]'
    )
    expected = hashlib.sha256(expected_json).hexdigest()

    assert _fingerprint_module().athlete_fingerprint(inputs) == expected


def test_athlete_fingerprint_uses_absent_literal_and_distinguishes_all_none() -> None:
    fingerprint = _fingerprint_module().athlete_fingerprint
    assert fingerprint(None) == hashlib.sha256(b"absent").hexdigest()
    assert fingerprint(None) != fingerprint(AthleteInputs())


def test_athlete_fingerprint_serializes_nan_by_repr() -> None:
    fingerprint = _fingerprint_module().athlete_fingerprint
    inputs = AthleteInputs(ftp_watts=float("nan"))
    expected = hashlib.sha256(b'["nan",null,null,null,null,null,null]').hexdigest()

    assert fingerprint(inputs) == expected
    assert fingerprint(inputs) == fingerprint(inputs)


def test_athlete_fingerprint_distinguishes_twelfth_significant_digit() -> None:
    fingerprint = _fingerprint_module().athlete_fingerprint
    first = AthleteInputs(ftp_watts=250.000000001)
    second = AthleteInputs(ftp_watts=250.000000002)
    assert repr(first.ftp_watts) != repr(second.ftp_watts)

    assert fingerprint(first) != fingerprint(second)


@pytest.mark.parametrize("field_name", ("hr_zones", "power_zones", "pace_zones"))
def test_athlete_fingerprint_preserves_zone_divider_repr_precision(
    field_name: str,
) -> None:
    first_zone = ZoneSpec((1.12345678901,))
    second_zone = ZoneSpec((1.12345678902,))
    assert repr(first_zone.dividers[0]) != repr(second_zone.dividers[0])
    assert round(first_zone.dividers[0], 10) == round(second_zone.dividers[0], 10)

    if field_name == "hr_zones":
        first = AthleteInputs(hr_zones=first_zone)
        second = AthleteInputs(hr_zones=second_zone)
    elif field_name == "power_zones":
        first = AthleteInputs(power_zones=first_zone)
        second = AthleteInputs(power_zones=second_zone)
    else:
        first = AthleteInputs(pace_zones=first_zone)
        second = AthleteInputs(pace_zones=second_zone)

    assert _fingerprint_module().athlete_fingerprint(first) != (
        _fingerprint_module().athlete_fingerprint(second)
    )


@pytest.mark.parametrize(
    "field",
    ("producer_fingerprint", "fitdocs_version", "schema_version"),
    ids=("producer-fingerprint", "fitdocs-version", "schema-version"),
)
def test_corpus_fingerprint_moves_for_each_argument(field: str) -> None:
    original: tuple[str, str | None, int] = ("producer-a", None, 17)
    changed_by_field: dict[str, tuple[str, str | None, int]] = {
        "producer_fingerprint": ("producer-b", None, 17),
        "fitdocs_version": ("producer-a", "producer-b", 17),
        "schema_version": ("producer-a", None, 18),
    }
    changed_arguments = changed_by_field[field]
    assert changed_arguments != original

    assert _corpus_fingerprint(*changed_arguments) != _corpus_fingerprint(*original)


def _corpus_fingerprint(
    producer_fingerprint: str, version_value: str | None, schema_version: int
) -> str:
    return cast(
        str,
        _fingerprint_module().corpus_fingerprint(
            producer_fingerprint,
            fitdocs_version=version_value,
            schema_version=schema_version,
        ),
    )


def test_corpus_fingerprint_has_independent_canonical_digest() -> None:
    expected_json = (
        b'{"fitdocs_version":null,"producer_fingerprint":"producer-a",'
        b'"schema_version":17}'
    )
    expected = hashlib.sha256(expected_json).hexdigest()

    assert (
        _fingerprint_module().corpus_fingerprint(
            "producer-a", fitdocs_version=None, schema_version=17
        )
        == expected
    )


def _corpus_snapshot() -> CorpusSnapshot:
    return CorpusSnapshot(
        data_root=Path("/synthetic/root"),
        pages=(),
        left_out=(),
        today=date(2026, 10, 5),
        athlete_fingerprint="athlete-fingerprint-synthetic",
    )


class _Producer:
    def __init__(self, value: str = "producer-fingerprint-a") -> None:
        self.value = value
        self.error: Exception | None = None
        self.received_snapshot: CorpusSnapshot | None = None

    @property
    def name(self) -> str:
        return "synthetic.corpus"

    @property
    def tables(self) -> tuple[TableSpec, ...]:
        return ()

    def fingerprint(self, snapshot: CorpusSnapshot) -> str:
        self.received_snapshot = snapshot
        if self.error is not None:
            raise self.error
        return self.value

    def rows(self, snapshot: CorpusSnapshot) -> Rows:
        return {}


def test_combined_corpus_fingerprint_composes_the_three_parts() -> None:
    from fitdocs import version

    producer = _Producer()
    snapshot = _corpus_snapshot()
    assert producer.received_snapshot is None
    expected = cast(
        str,
        _fingerprint_module().corpus_fingerprint(
            "producer-fingerprint-a",
            fitdocs_version=version.tool_version(),
            schema_version=SCHEMA_VERSION,
        ),
    )

    actual = _fingerprint_module().combined_corpus_fingerprint(producer, snapshot)

    assert actual == expected
    assert producer.received_snapshot is snapshot


def test_combined_corpus_fingerprint_reads_tool_version_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fitdocs import version

    producer = _Producer()
    snapshot = _corpus_snapshot()
    fingerprint = _fingerprint_module().combined_corpus_fingerprint
    before = fingerprint(producer, snapshot)
    monkeypatch.setattr(version, "tool_version", lambda: "synthetic-next-version")

    assert fingerprint(producer, snapshot) != before


def test_combined_corpus_fingerprint_moves_when_producer_fingerprint_moves() -> None:
    producer = _Producer("producer-before")
    snapshot = _corpus_snapshot()
    fingerprint = _fingerprint_module().combined_corpus_fingerprint
    before = fingerprint(producer, snapshot)
    producer.value = "producer-after"
    assert producer.value == "producer-after"

    assert fingerprint(producer, snapshot) != before


def test_combined_corpus_fingerprint_propagates_the_same_exception() -> None:
    producer = _Producer()
    error = RuntimeError("synthetic producer fingerprint failure")
    producer.error = error

    with pytest.raises(RuntimeError) as raised:
        _fingerprint_module().combined_corpus_fingerprint(producer, _corpus_snapshot())

    assert raised.value is error
