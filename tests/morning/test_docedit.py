"""Read and replace morning content inside workout documents."""

from typing import Literal

import pytest

from fitdocs.contract import (
    LOAD_NOT_COMPUTED,
    LOAD_REGION,
    MORNING_PLACEHOLDER,
    MORNING_REGION,
    NOTES_PLACEHOLDER,
    NOTES_REGION,
)
from fitdocs.docmerge import (
    RegionError,
    begin_marker,
    end_marker,
    extract_regions,
    region_block,
)
from fitdocs.morning.docedit import (
    MorningRegionMissing,
    read_morning,
    replace_morning,
)
from tests.morning.builders import rendered_page, workout_page

_STALE = "Stale morning summary: Ω"


@pytest.mark.parametrize(
    "content",
    ("", "\nMorning: élan\nSecond line\n\n", r"\g<0> $1"),
    ids=("empty", "multiline", "literal-backslash"),
)
def test_replace_roundtrips_content(content: str) -> None:
    page = workout_page(morning=_STALE)
    assert read_morning(page) == _STALE

    result = replace_morning(page, content)
    expected = page.replace(
        region_block(MORNING_REGION, _STALE), region_block(MORNING_REGION, content)
    )

    assert result == expected
    assert read_morning(result) == content


def test_replace_preserves_rendered_page_bytes() -> None:
    notes = "Athlete notes: café 🏃  \nKeep this indentation.\n"
    load = "Computed load: 123.4\nMethod: synthetic threshold  "
    page = (
        rendered_page()
        .replace(
            region_block(NOTES_REGION, NOTES_PLACEHOLDER),
            region_block(NOTES_REGION, notes),
        )
        .replace(
            region_block(LOAD_REGION, LOAD_NOT_COMPUTED),
            region_block(LOAD_REGION, load),
        )
        .replace(
            region_block(MORNING_REGION, MORNING_PLACEHOLDER),
            region_block(MORNING_REGION, _STALE),
        )
    )
    assert read_morning(page) == _STALE
    regions = extract_regions(page)
    assert (regions[NOTES_REGION], regions[LOAD_REGION]) == (notes, load)
    begin = begin_marker(MORNING_REGION)
    end = end_marker(MORNING_REGION)
    prefix, inner_and_suffix = page.split(begin + "\n", 1)
    _, suffix = inner_and_suffix.split("\n" + end, 1)
    content = "New morning: naïve\n\nUpdated figures.\n"
    expected = (prefix + begin + "\n" + content + "\n" + end + suffix).encode()

    result = replace_morning(page, content)

    assert result.split(begin + "\n", 1)[0].encode() == prefix.encode()
    assert result.split("\n" + end, 1)[1].encode() == suffix.encode()
    assert result.encode() == expected


def test_missing_morning_reads_none() -> None:
    page = region_block(NOTES_REGION, "Notes") + region_block(LOAD_REGION, "Load")

    assert read_morning(page) is None


def test_missing_morning_cannot_be_replaced() -> None:
    page = region_block(NOTES_REGION, "Notes") + region_block(LOAD_REGION, "Load")

    with pytest.raises(MorningRegionMissing):
        replace_morning(page, "New morning")


@pytest.mark.parametrize("operation", ("read", "replace"))
@pytest.mark.parametrize(
    "damage",
    ("missing-end", "mismatched-end", "nested", "duplicate", "other-region"),
)
def test_damaged_markers_raise(
    operation: Literal["read", "replace"], damage: str
) -> None:
    morning = region_block(MORNING_REGION, _STALE)
    if damage == "missing-end":
        page = begin_marker(MORNING_REGION) + "\n" + _STALE + "\n"
    elif damage == "mismatched-end":
        page = morning.replace(end_marker(MORNING_REGION), end_marker(LOAD_REGION))
    elif damage == "nested":
        page = begin_marker(NOTES_REGION) + "\n" + morning + end_marker(NOTES_REGION)
    elif damage == "duplicate":
        page = morning + morning
    else:
        page = morning + begin_marker(NOTES_REGION) + "\nUnclosed notes\n"

    with pytest.raises(RegionError):
        if operation == "read":
            read_morning(page)
        else:
            replace_morning(page, "New morning")


def test_replace_ignores_inline_begin_in_notes() -> None:
    notes = region_block(
        NOTES_REGION, "Marker example: " + begin_marker(MORNING_REGION) + "\nExample"
    )
    page = notes + region_block(MORNING_REGION, _STALE)

    result = replace_morning(page, "New morning")

    assert result == notes + region_block(MORNING_REGION, "New morning")


def test_replace_ignores_inline_end_in_content() -> None:
    stale = _STALE + "\n" + end_marker(MORNING_REGION) + " example\nStill stale"
    page = region_block(MORNING_REGION, stale) + region_block(LOAD_REGION, "Load")

    result = replace_morning(page, "New morning")

    assert result == region_block(MORNING_REGION, "New morning") + region_block(
        LOAD_REGION, "Load"
    )


def test_morning_id_is_exact() -> None:
    neighbor = region_block(MORNING_REGION + "2", "Neighboring content")
    page = neighbor + region_block(MORNING_REGION, _STALE)
    assert read_morning(page) == _STALE

    result = replace_morning(page, "New morning")

    assert result == neighbor + region_block(MORNING_REGION, "New morning")
