"""The published region: line format, ordering and the splice
(publish-core task 5.2; Req 3.8, 12.2, 12.4, 12.5)."""

from __future__ import annotations

import pytest

from fitdocs.contract import (
    NOTES_REGION,
    POST_REGION,
    PUBLISHED_REGION,
    region_block,
)
from fitdocs.docmerge import RegionError, begin_marker, end_marker, extract_regions
from fitdocs.publish.links import (
    LINK_SEPARATOR,
    PUBLISHED_PREFIX,
    PublishedRegionMissing,
    published_content,
    read_published,
    replace_published,
)

_STALE = "Published: [Old](https://old.example/1)"
_POST_BODY = "A race report.\n\nSecond paragraph, with <!-- a hidden note -->."
_NOTES_BODY = "Felt strong.\n  indented line\n"


def _page(
    *,
    published: str | None = _STALE,
    post: str = _POST_BODY,
    prefix: str = "---\ntype: workout\n---\n\n# Run\n\n",
    suffix: str = "\nTrailing prose, no final newline",
) -> str:
    """A page whose regions are distinct, pairwise-different byte strings."""
    blocks = [
        region_block(NOTES_REGION, _NOTES_BODY),
        region_block(POST_REGION, post),
    ]
    if published is not None:
        blocks.append(region_block(PUBLISHED_REGION, published))
    return prefix + "\n".join(blocks) + suffix


def test_no_link_renders_empty() -> None:
    assert published_content([]) == ""


def test_one_link_line_format() -> None:
    assert (
        published_content([("intervals", "Intervals.icu", "https://i.example/a")])
        == "Published: [Intervals.icu](https://i.example/a)"
    )


def test_the_literals_are_the_landed_ones() -> None:
    assert PUBLISHED_PREFIX == "Published: "
    assert LINK_SEPARATOR == " · "


def test_links_are_joined_by_the_separator_in_target_name_order() -> None:
    # Target-name order differs from label order and from link order and from
    # input order, so only sorting by the target name produces this line.
    records = [
        ("mango", "Zulu", "https://z.example/1"),
        ("apple", "Yankee", "https://y.example/2"),
        ("zebra", "Alpha", "https://a.example/3"),
        ("kiwi", "Xray", "https://x.example/4"),
    ]
    assert published_content(records) == (
        "Published: [Yankee](https://y.example/2)"
        " · [Xray](https://x.example/4)"
        " · [Zulu](https://z.example/1)"
        " · [Alpha](https://a.example/3)"
    )


def test_colliding_labels_keep_every_recorded_link() -> None:
    # Two targets share a label; each record is its own link (Req 12.2).
    records = [
        ("kiwi", "Intervals.icu", "https://k.example/2"),
        ("apple", "Intervals.icu", "https://a.example/1"),
    ]
    assert published_content(records) == (
        "Published: [Intervals.icu](https://a.example/1)"
        " · [Intervals.icu](https://k.example/2)"
    )


def test_label_is_the_text_and_link_the_target_of_the_markdown_link() -> None:
    line = published_content([("t", "The Label", "https://the.example/link")])
    assert line.endswith("[The Label](https://the.example/link)")
    assert "(The Label)" not in line


def test_read_returns_the_inner_content_and_none_without_the_region() -> None:
    assert read_published(_page()) == _STALE
    assert read_published(_page(published=None)) is None


def test_read_raises_on_damaged_markers() -> None:
    damaged = _page().replace("<!-- fitdocs:end:published -->", "")
    with pytest.raises(RegionError):
        read_published(damaged)


@pytest.mark.parametrize(
    "new",
    (
        "",
        "Published: [Intervals.icu](https://i.example/a)",
        r"Published: [A](https://a.example/\g<0>$1)",
    ),
    ids=("empty", "line", "backslash-and-dollar"),
)
def test_splice_changes_only_the_region(new: str) -> None:
    page = _page()
    assert read_published(page) != new, "the fixture must start in a different state"

    result = replace_published(page, new)

    assert read_published(result) == new
    # Every byte outside the region is identical: rebuild the expected page
    # from the same parts with only the region's block swapped.
    old_block = region_block(PUBLISHED_REGION, _STALE)
    assert page.count(old_block) == 1
    assert result == page.replace(old_block, region_block(PUBLISHED_REGION, new))


def test_splice_leaves_the_post_and_notes_regions_byte_identical() -> None:
    page = _page()
    result = replace_published(page, "Published: [A](https://a.example/1)")
    before = extract_regions(page)
    after = extract_regions(result)
    assert before[POST_REGION] == _POST_BODY
    assert after[POST_REGION] == _POST_BODY
    assert after[NOTES_REGION] == _NOTES_BODY
    assert after[POST_REGION] == before[POST_REGION]


def test_splice_when_the_post_region_follows_the_published_region() -> None:
    # Region order on the page must not matter: the post region sits after
    # the published region here.
    page = (
        "head\n"
        + region_block(PUBLISHED_REGION, _STALE)
        + region_block(POST_REGION, _POST_BODY)
        + "tail"
    )
    result = replace_published(page, "NEW")
    assert result == (
        "head\n"
        + region_block(PUBLISHED_REGION, "NEW")
        + region_block(POST_REGION, _POST_BODY)
        + "tail"
    )


def test_splicing_the_current_content_is_the_identity() -> None:
    page = _page()
    assert replace_published(page, _STALE) == page


def test_a_page_without_the_region_is_reported_not_given_one() -> None:
    page = _page(published=None)
    with pytest.raises(PublishedRegionMissing):
        replace_published(page, "Published: [A](https://a.example/1)")
    assert PUBLISHED_REGION not in extract_regions(page), "the fixture has the region"


def test_a_damaged_page_raises_region_error() -> None:
    damaged = _page().replace("<!-- fitdocs:begin:post -->", "")
    with pytest.raises(RegionError):
        replace_published(damaged, "x")


def _adjacent(tail: str) -> str:
    return (
        "head\n"
        + begin_marker(PUBLISHED_REGION)
        + "\n"
        + end_marker(PUBLISHED_REGION)
        + tail
    )


def test_splice_into_adjacent_markers_mid_page() -> None:
    page = _adjacent("\ntail")
    assert read_published(page) == ""
    assert replace_published(page, "X") == (
        "head\n" + region_block(PUBLISHED_REGION, "X") + "tail"
    )


def test_splice_into_adjacent_markers_at_end_of_file() -> None:
    page = _adjacent("")
    assert read_published(page) == ""
    assert replace_published(page, "X") == (
        "head\n" + region_block(PUBLISHED_REGION, "X").rstrip("\n")
    )


def test_splice_replaces_multi_line_stale_content() -> None:
    page = _page(published="line one\n\nline three")
    assert replace_published(page, "NEW") == _page(published="NEW")
