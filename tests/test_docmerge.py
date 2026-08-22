"""Tests for the region marker contract and safe merge (design: RegionMerger).

These lock the pure string helpers in :mod:`fitdocs.docmerge`
(``src/fitdocs/docmerge.py``) that guard user-authored and tool-filled content
across regeneration (Req 10.1-10.4, 11.3):

* the marker grammar -- ``begin_marker`` / ``end_marker`` / ``region_block``
  emit HTML-comment delimiters on their own lines, and ``region_block`` composes
  a region that round-trips through ``extract_regions`` verbatim (10.1);
* ``extract_regions`` recovers each region's inner content byte-for-byte and
  raises :class:`RegionError` on unbalanced, duplicated, out-of-order, or nested
  markers so damage is a loud conflict, never a silent misread (10.3);
* ``merge_regions`` carries each preserved region's existing content -- notes,
  workout, and the training-load-filled ``load`` region alike -- verbatim into a
  fresh render, fully replacing generated content outside regions (10.2, 10.4,
  11.3), and raises :class:`RegionError` rather than dropping a region the fresh
  render lacks (10.3);
* the merge grammar composes and recovers exactly the region ids the document
  contract preserves -- the policy constants themselves (``PRESERVED_REGIONS``,
  ``LOAD_NOT_COMPUTED``) now live in :mod:`fitdocs.contract` and are pinned by
  ``tests/test_contract.py``; they are imported here only as realistic inputs.

The module is a pure string module (no file I/O), so every case is exercised on
literal markdown strings.
"""

from __future__ import annotations

import pytest

from fitdocs.contract import LOAD_NOT_COMPUTED, PRESERVED_REGIONS
from fitdocs.docmerge import (
    RegionError,
    begin_marker,
    end_marker,
    extract_regions,
    merge_regions,
    region_block,
)


def _doc(
    notes: str, workout: str, load: str, *, tail: str = "generated devices\n"
) -> str:
    """A three-region document shaped like a rendered strength doc.

    Headings and the trailing section live *outside* the regions -- they are the
    generated (non-editable) content that regeneration must fully replace.
    """
    return (
        "# 2026-07-12 Strength\n\n"
        "## Notes\n\n"
        f"{region_block('notes', notes)}"
        "\n## Workout\n\n"
        f"{region_block('workout', workout)}"
        "\n## Training Load\n\n"
        f"{region_block('load', load)}"
        f"\n## Device & Data Quality\n\n{tail}"
    )


# --------------------------------------------------------------------------- #
# The grammar covers exactly the contract's preserved regions
# --------------------------------------------------------------------------- #


def test_every_preserved_region_round_trips_through_the_grammar() -> None:
    """The generic mechanism handles each id the contract preserves."""
    for region_id in PRESERVED_REGIONS:
        block = region_block(region_id, f"content of {region_id}")
        assert extract_regions(block) == {region_id: f"content of {region_id}"}


# --------------------------------------------------------------------------- #
# Marker grammar
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("region_id", ["notes", "workout", "load"])
def test_begin_marker_exact_string(region_id: str) -> None:
    assert begin_marker(region_id) == f"<!-- fitdocs:begin:{region_id} -->"


@pytest.mark.parametrize("region_id", ["notes", "workout", "load"])
def test_end_marker_exact_string(region_id: str) -> None:
    assert end_marker(region_id) == f"<!-- fitdocs:end:{region_id} -->"


def test_region_block_newline_layout_is_pinned() -> None:
    # begin-marker line, one content line, end-marker line -- each newline
    # terminated. This exact layout is the round-trip contract.
    assert region_block("notes", "hello") == (
        "<!-- fitdocs:begin:notes -->\nhello\n<!-- fitdocs:end:notes -->\n"
    )


# --------------------------------------------------------------------------- #
# region_block + extract_regions round-trip (verbatim)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "content",
    [
        "hello",
        "",
        "line one\nline two\nline three",
        "para one\n\npara two with blank line above",
        "trailing newline\n",
        "  leading spaces and\ttabs preserved  ",
        "## A heading, - a list item, and <!-- a commentish line -->",
        "| col | col |\n| --- | --- |\n| a | b |",
    ],
)
def test_round_trip_recovers_content_verbatim(content: str) -> None:
    recovered = extract_regions(region_block("notes", content))
    assert recovered == {"notes": content}


def test_extract_multiple_regions_in_document_order() -> None:
    doc = _doc("my notes", "3x5 squats", "computed load")
    assert extract_regions(doc) == {
        "notes": "my notes",
        "workout": "3x5 squats",
        "load": "computed load",
    }


def test_extract_ignores_indented_lookalike_and_id_is_matched_exactly() -> None:
    # A marker for a *different* id (notes2) is its own region, never confused
    # with `notes`; an indented lookalike is not a marker at all.
    doc = region_block("notes", "real notes") + region_block("notes2", "other")
    extracted = extract_regions(doc)
    assert extracted["notes"] == "real notes"
    assert extracted["notes2"] == "other"


# --------------------------------------------------------------------------- #
# merge_regions -- carry existing content, replace generated content
# --------------------------------------------------------------------------- #


def test_merge_carries_all_three_regions_and_replaces_generated_text() -> None:
    fresh = _doc(
        "_Add your notes here._",
        "_Describe the workout performed._",
        LOAD_NOT_COMPUTED,
        tail="FRESH generated devices\n",
    )
    existing = _doc(
        "My real notes\nwith a second line",
        "Squat 3x5 @ 100 kg\nBench 3x8 @ 60 kg",
        "**TSS:** 42 - **IF:** 0.85",
        tail="STALE generated devices\n",
    )

    merged = merge_regions(fresh, existing)
    recovered = extract_regions(merged)

    # All three preserved regions carry the existing (user/tool) content verbatim.
    assert recovered["notes"] == "My real notes\nwith a second line"
    assert recovered["workout"] == "Squat 3x5 @ 100 kg\nBench 3x8 @ 60 kg"
    assert recovered["load"] == "**TSS:** 42 - **IF:** 0.85"

    # Content OUTSIDE the regions comes from the fresh render (10.4).
    assert "FRESH generated devices" in merged
    assert "STALE generated devices" not in merged


def test_merge_load_region_carried_over_byte_for_byte() -> None:
    # A tool-filled load region with computed numbers must survive identically
    # (11.3): no reformatting, no whitespace changes.
    computed = "| Method | Load |\n| --- | --- |\n| Stub | 87.5 |\n\n_Model: v2_"
    fresh = _doc("n", "w", LOAD_NOT_COMPUTED)
    existing = _doc("n", "w", computed)

    merged = merge_regions(fresh, existing)
    assert extract_regions(merged)["load"] == computed


def test_merge_against_identical_document_is_a_no_op() -> None:
    doc = _doc("notes", "workout", "load")
    assert merge_regions(doc, doc) == doc


def test_merge_keeps_fresh_region_absent_from_existing() -> None:
    # A region present in fresh but NOT in existing (a newly generated doc, or a
    # newly added region) is kept from fresh -- not a conflict.
    fresh = (
        "## Notes\n\n"
        f"{region_block('notes', 'placeholder notes')}"
        "\n## Training Load\n\n"
        f"{region_block('load', LOAD_NOT_COMPUTED)}"
        "\ntail\n"
    )
    existing = f"## Notes\n\n{region_block('notes', 'user notes')}\nold tail\n"

    merged = merge_regions(fresh, existing)
    recovered = extract_regions(merged)
    assert recovered["notes"] == "user notes"  # carried from existing
    assert recovered["load"] == LOAD_NOT_COMPUTED  # kept from fresh
    assert "tail" in merged


def test_merge_against_regionless_existing_returns_fresh_unchanged() -> None:
    fresh = _doc("placeholder", "placeholder", LOAD_NOT_COMPUTED)
    existing = "# Some hand-written doc with no fitdocs markers at all\n"
    assert merge_regions(fresh, existing) == fresh


# --------------------------------------------------------------------------- #
# merge_regions -- conflicts (never overwrite)
# --------------------------------------------------------------------------- #


def test_merge_raises_when_existing_has_region_fresh_lacks() -> None:
    # Silent content loss is forbidden: existing has a `workout` region that the
    # fresh render does not, so merge conflicts instead of dropping it (10.3).
    fresh = (
        "## Notes\n\n"
        f"{region_block('notes', 'placeholder')}"
        "\n## Training Load\n\n"
        f"{region_block('load', LOAD_NOT_COMPUTED)}"
        "\n"
    )
    existing = _doc("notes", "user workout content", "load")

    with pytest.raises(RegionError) as excinfo:
        merge_regions(fresh, existing)
    assert "workout" in str(excinfo.value)


def test_merge_propagates_region_error_from_damaged_existing() -> None:
    # existing damaged (missing end marker) -> conflict-on-damage path (10.3).
    fresh = _doc("n", "w", LOAD_NOT_COMPUTED)
    existing = _doc("n", "w", "load").replace(end_marker("load") + "\n", "", 1)

    with pytest.raises(RegionError):
        merge_regions(fresh, existing)


# --------------------------------------------------------------------------- #
# extract_regions -- damage detection
# --------------------------------------------------------------------------- #


def test_extract_raises_on_begin_without_end() -> None:
    md = f"{begin_marker('notes')}\nsome content\n"
    with pytest.raises(RegionError) as excinfo:
        extract_regions(md)
    assert "notes" in str(excinfo.value)


def test_extract_raises_on_end_without_begin() -> None:
    md = f"some content\n{end_marker('notes')}\n"
    with pytest.raises(RegionError) as excinfo:
        extract_regions(md)
    assert "notes" in str(excinfo.value)


def test_extract_raises_on_duplicate_region_id() -> None:
    md = region_block("notes", "first") + region_block("notes", "second")
    with pytest.raises(RegionError) as excinfo:
        extract_regions(md)
    assert "notes" in str(excinfo.value)


def test_extract_raises_on_out_of_order_end_before_begin() -> None:
    md = f"{end_marker('notes')}\ncontent\n{begin_marker('notes')}\n"
    with pytest.raises(RegionError):
        extract_regions(md)


def test_extract_raises_on_nested_begins() -> None:
    md = (
        f"{begin_marker('notes')}\n"
        "outer\n"
        f"{begin_marker('workout')}\n"
        "inner\n"
        f"{end_marker('workout')}\n"
        f"{end_marker('notes')}\n"
    )
    with pytest.raises(RegionError):
        extract_regions(md)


def test_extract_raises_on_mismatched_end_id() -> None:
    md = f"{begin_marker('notes')}\ncontent\n{end_marker('load')}\n"
    with pytest.raises(RegionError):
        extract_regions(md)
