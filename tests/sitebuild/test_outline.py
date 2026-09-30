"""Page ordering, URL mapping, nav and the llms texts (3.1, 3.2, 4.6, 5.1-5.4).

The tests build ``SiteContent`` values from the model types, so nothing here
touches ``content.py`` or the filesystem.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest
from scripts.sitebuild.model import SECTIONS, Page, SiteContent
from scripts.sitebuild.outline import (
    nav_structure,
    ordered_pages,
    page_path,
    render_llms,
    render_llms_full,
)

SITE_URL = "https://example.test/"


def _page(
    path: str,
    title: str,
    section: str,
    order: int,
    *,
    description: str = "",
    body: str = "",
) -> Page:
    return Page(
        path=path,
        title=title,
        description=description or f"About {title}",
        section=section,
        order=order,
        staged_text=f"---\ntitle: {title}\n---\n" + body,
        body=body,
        hero_title=None,
        hero_tagline=None,
        hero_actions=None,
    )


def _content(pages: tuple[Page, ...]) -> SiteContent:
    return SiteContent(root=Path("unused"), pages=pages, assets=())


# Listed in an order that matches none of: canonical section order,
# alphabetical section order, path order, title order, or `order` value.
# Sections: Reference, Guides, Get started, Project, Home (Why, Working with
# LLMs and Extend are empty).
# Get started holds three pages whose `order` (2, 9, 10) disagrees with
# title order (Alpha, Mid, Zeta), path order (a-mid, b-zeta, c-alpha) and
# listing order (Mid, Alpha, Zeta).
PAGES = (
    _page(
        "reference/index.md",
        "Reference home",
        "Reference",
        1,
        description="Every command",
        body="Reference body.\n",
    ),
    _page(
        "guides/nested/deep.md",
        "Deep guide",
        "Guides",
        1,
        description="A nested guide",
        body="Deep body.\n",
    ),
    _page(
        "get-started/a-mid.md",
        "Mid",
        "Get started",
        10,
        description="Third step",
        body="Mid body.\n",
    ),
    _page(
        "get-started/c-alpha.md",
        "Alpha",
        "Get started",
        9,
        description="Second step",
        body="Alpha body.\n\nSecond paragraph.\n",
    ),
    _page(
        "get-started/b-zeta.md",
        "Zeta",
        "Get started",
        2,
        description="First step",
        body="\nZeta body.\n",
    ),
    _page(
        "changelog.md",
        "Changelog",
        "Project",
        1,
        description="What changed",
        body="Changelog body.\n",
    ),
    _page(
        "index.md",
        "fitdocs",
        "Home",
        1,
        description="The landing page",
        body="Welcome.\n",
    ),
)
SITE = _content(PAGES)

CORRECT_ORDER = [
    ("Home", ["index.md"]),
    (
        "Get started",
        ["get-started/b-zeta.md", "get-started/c-alpha.md", "get-started/a-mid.md"],
    ),
    ("Guides", ["guides/nested/deep.md"]),
    ("Reference", ["reference/index.md"]),
    ("Project", ["changelog.md"]),
]

EXPECTED_LLMS = """\
# Example Docs

> Docs for the example.

## Home

- [fitdocs](https://example.test/): The landing page

## Get started

- [Zeta](https://example.test/get-started/b-zeta/): First step
- [Alpha](https://example.test/get-started/c-alpha/): Second step
- [Mid](https://example.test/get-started/a-mid/): Third step

## Guides

- [Deep guide](https://example.test/guides/nested/deep/): A nested guide

## Reference

- [Reference home](https://example.test/reference/): Every command

## Project

- [Changelog](https://example.test/changelog/): What changed
"""

EXPECTED_LLMS_FULL = """\
# fitdocs
Source: https://example.test/

Welcome.

# Zeta
Source: https://example.test/get-started/b-zeta/

Zeta body.

# Alpha
Source: https://example.test/get-started/c-alpha/

Alpha body.

Second paragraph.

# Mid
Source: https://example.test/get-started/a-mid/

Mid body.

# Deep guide
Source: https://example.test/guides/nested/deep/

Deep body.

# Reference home
Source: https://example.test/reference/

Reference body.

# Changelog
Source: https://example.test/changelog/

Changelog body.
"""


def _llms(content: SiteContent = SITE, site_url: str = SITE_URL) -> str:
    return render_llms(
        content,
        site_name="Example Docs",
        summary="Docs for the example.",
        site_url=site_url,
    )


def test_fixture_listing_order_defeats_the_wrong_orderings() -> None:
    """The fixture disagrees with every wrong ordering rule (3.1, 3.2).

    Dies on: a fixture edit, not a production one: changing the Zeta page's
    `order` from 2 to 12 makes `order` agree with title order, so this test
    goes red (as do the exact-output tests, whose literals assumed 2).
    """
    listed = [p for p in PAGES if p.section == "Get started"]
    right = [p.path for p in sorted(listed, key=lambda p: p.order)]
    assert right != [p.path for p in listed]  # insertion order
    assert right != sorted(p.path for p in listed)  # path order
    assert right != [p.path for p in sorted(listed, key=lambda p: p.title)]
    assert right != [p.path for p in sorted(listed, key=lambda p: -p.order)]
    assert right != [p.path for p in sorted(listed, key=lambda p: str(p.order))]
    sections_listed = list(dict.fromkeys(p.section for p in PAGES))
    canonical = [s for s in SECTIONS if s in sections_listed]
    assert sections_listed != canonical
    assert sorted(sections_listed) != canonical
    assert len(canonical) == 5  # three sections are empty


def test_sections_follow_canonical_order_and_empty_ones_are_omitted() -> None:
    """Sections come out in `SECTIONS` order and empty ones do not appear (3.1).

    Dies on: iterating `sorted(sections)` or the first-seen order instead of
    `SECTIONS`; emitting every section in `SECTIONS`, empty ones included.
    """
    names = [section for section, _pages in ordered_pages(SITE)]
    assert names == [section for section, _paths in CORRECT_ORDER]
    assert "Why" not in names  # an empty section, absent


def test_pages_within_a_section_ascend_by_order_not_by_name_or_position() -> None:
    """`order` decides within a section (3.2).

    Dies on: sorting by title, by path, by string form of `order`, by
    descending `order`, or not sorting (listing order).
    """
    got = [(section, [p.path for p in pages]) for section, pages in ordered_pages(SITE)]
    assert got == CORRECT_ORDER


def test_equal_order_falls_back_to_path_whatever_the_input_order() -> None:
    """Pages tied on `order` sort by path in every input permutation (5.4).

    Dies on: dropping the `p.path` tie-break from the sort key, so a tie keeps
    input order; replacing it with `p.title` or `p.description`.
    """
    tied = (
        _page("guides/c.md", "Mike", "Guides", 1, description="Able"),
        _page("guides/a.md", "Zulu", "Guides", 1, description="Mike"),
        _page("guides/b.md", "Alpha", "Guides", 1, description="Zed"),
    )
    # Titles and descriptions each sort differently from the paths and from
    # each other, so only the path can explain the expected order.
    assert [p.path for p in sorted(tied, key=lambda p: p.title)] != sorted(
        p.path for p in tied
    )
    assert [p.path for p in sorted(tied, key=lambda p: p.description)] != [
        p.path for p in sorted(tied, key=lambda p: p.title)
    ]
    assert [p.path for p in sorted(tied, key=lambda p: p.description)] != sorted(
        p.path for p in tied
    )
    seen: set[tuple[str, ...]] = set()
    for perm in itertools.permutations(tied):
        (_section, pages) = ordered_pages(_content(perm))[0]
        got = tuple(p.path for p in pages)
        assert got == ("guides/a.md", "guides/b.md", "guides/c.md")
        seen.add(tuple(p.path for p in perm))
    assert len(seen) == 6  # all six input orders were exercised


def test_a_section_outside_the_canonical_list_raises() -> None:
    """A page cannot silently drop out of the site (3.1).

    Dies on: skipping pages whose section is not in `SECTIONS` instead of
    raising.
    """
    stray = _page("x.md", "X", "Elsewhere", 1)
    with pytest.raises(ValueError, match="Elsewhere"):
        ordered_pages(_content((*PAGES, stray)))


def test_empty_site_has_no_sections() -> None:
    """No pages give no sections and a nav of nothing (3.1).

    Dies on: emitting a header for every section regardless of content.
    """
    assert ordered_pages(_content(())) == ()
    assert nav_structure(_content(())) == []


@pytest.mark.parametrize(
    ("source", "url_path"),
    [
        ("index.md", ""),
        ("a/index.md", "a/"),
        ("a/b/index.md", "a/b/"),
        ("a/b.md", "a/b/"),
        ("a/b/c.md", "a/b/c/"),
        ("about.md", "about/"),
        ("reindex.md", "reindex/"),
        ("a/index-old.md", "a/index-old/"),
        ("a/reindex.md", "a/reindex/"),
        ("index/index.md", "index/"),
        ("index/page.md", "index/page/"),
        ("a/index.md.md", "a/index.md/"),
    ],
)
def test_page_path_maps_content_paths_to_trailing_slash_urls(
    source: str, url_path: str
) -> None:
    """Every content path maps to its trailing-slash URL path (4.6).

    Dies on: `endswith("index.md")` instead of a whole-name match (turns
    `reindex.md` wrong); replacing only the `.md` suffix
    for index files; dropping the trailing slash; mapping root `index.md` to
    `/` or `index/`.
    """
    assert page_path(source) == url_path


def test_nav_is_section_then_title_to_staged_path_in_order() -> None:
    """The nav is exactly `[{section: [{title: path}, ...]}, ...]` (3.1, 3.2).

    Dies on: emitting URL paths instead of `.md` paths; keying an entry by
    path instead of title; flattening the sections; changing the ordering.
    """
    assert nav_structure(SITE) == [
        {"Home": [{"fitdocs": "index.md"}]},
        {
            "Get started": [
                {"Zeta": "get-started/b-zeta.md"},
                {"Alpha": "get-started/c-alpha.md"},
                {"Mid": "get-started/a-mid.md"},
            ]
        },
        {"Guides": [{"Deep guide": "guides/nested/deep.md"}]},
        {"Reference": [{"Reference home": "reference/index.md"}]},
        {"Project": [{"Changelog": "changelog.md"}]},
    ]


def test_nav_lists_every_page_exactly_once() -> None:
    """No page is dropped or repeated by the nav (3.1).

    Dies on: skipping the last page of each section; emitting the first page
    of each section twice.
    """
    listed = [
        path
        for entry in nav_structure(SITE)
        for items in entry.values()
        for item in items
        for path in item.values()
    ]
    assert len(listed) == len(PAGES)
    assert sorted(listed) == sorted(p.path for p in PAGES)


def test_nav_keeps_pages_with_the_same_title_apart() -> None:
    """Two pages sharing a title both appear, as separate entries (3.1).

    Dies on: building the section's entries as one dict keyed by title, which
    collapses the second page into the first.
    """
    twins = _content(
        (
            _page("guides/one.md", "Same", "Guides", 1),
            _page("guides/two.md", "Same", "Guides", 2),
        )
    )
    assert nav_structure(twins) == [
        {"Guides": [{"Same": "guides/one.md"}, {"Same": "guides/two.md"}]}
    ]


def test_llms_txt_is_exactly_the_expected_text() -> None:
    """`llms.txt` matches the hand-written expectation byte for byte (5.1).

    Dies on: any change to the H1, the blockquote, the H2 headings, the list
    bullet or `: ` separator, the blank-line layout, the section order, the
    URL join, or an added `Optional` section.
    """
    assert _llms() == EXPECTED_LLMS
    assert "Optional" not in _llms()


def test_llms_full_txt_is_exactly_the_expected_text() -> None:
    """`llms-full.txt` matches the hand-written expectation byte for byte (5.2).

    Dies on: any change to the `# title` line, the `Source: ` line, the blank
    line before the body, the blank line between blocks, the page order, or
    the URL join.
    """
    assert render_llms_full(SITE, site_url=SITE_URL) == EXPECTED_LLMS_FULL


@pytest.mark.parametrize("site_url", ["https://example.test", "https://example.test/"])
def test_urls_join_site_url_and_path_with_exactly_one_slash(site_url: str) -> None:
    """Absolute URLs are `site_url` plus the path, whether or not it ends in `/` (4.6).

    Dies on: plain `site_url + path` (drops the slash for the bare form);
    `site_url + "/" + path` (doubles it for the trailing-slash form).
    """
    assert _llms(site_url=site_url) == EXPECTED_LLMS
    assert render_llms_full(SITE, site_url=site_url) == EXPECTED_LLMS_FULL


def test_home_page_url_is_the_site_root() -> None:
    """The home page's absolute URL is `site_url` itself (4.6).

    Dies on: mapping `index.md` to `index/` or `/` in the rendered URL.
    """
    lines = _llms().splitlines()
    assert "- [fitdocs](https://example.test/): The landing page" in lines


def test_renders_are_byte_identical_and_independent_of_input_order() -> None:
    """Two renders match, and so do renders of shuffled input (5.4).

    Dies on: embedding a timestamp or counter in either text; depending on the
    order of `SiteContent.pages` (removing the page sort).
    """
    first = (_llms(), render_llms_full(SITE, site_url=SITE_URL))
    second = (_llms(), render_llms_full(SITE, site_url=SITE_URL))
    assert first == second
    assert first[0] == EXPECTED_LLMS  # non-trivial: compared against a literal
    reversed_site = _content(tuple(reversed(PAGES)))
    assert reversed_site.pages != SITE.pages
    assert _llms(reversed_site) == first[0]
    assert render_llms_full(reversed_site, site_url=SITE_URL) == first[1]


def test_output_is_lf_only_with_exactly_one_trailing_newline() -> None:
    """No CR remains and each text ends in one newline (5.4).

    Dies on: dropping the CRLF or the lone-CR normalisation, including the
    outer pass in `render_llms_full` (a CR in a title); stripping the
    final newline; emitting two; dropping the body strip.
    """
    messy = _content(
        (
            _page(
                "a.md",
                "A",
                "Guides",
                1,
                body="\r\n\r\nLine one\rLine two\r\n\r\n\r\n",
            ),
            _page("b.md", "B\rC", "Guides", 2, body="Bare"),
        )
    )
    index = render_llms(
        messy,
        site_name="N",
        summary="line one\rline two\r\nline three",
        site_url=SITE_URL,
    )
    assert index == (
        "# N\n\n> line one\nline two\nline three\n\n## Guides\n\n"
        "- [A](https://example.test/a/): About A\n"
        "- [B\nC](https://example.test/b/): About B\nC\n"
    )
    for text in (
        index,
        render_llms_full(messy, site_url=SITE_URL),
    ):
        assert "\r" not in text
        assert text.endswith("\n")
        assert not text.endswith("\n\n")
    full = render_llms_full(messy, site_url=SITE_URL)
    assert full == (
        "# A\nSource: https://example.test/a/\n\nLine one\nLine two\n\n"
        "# B\nC\nSource: https://example.test/b/\n\nBare\n"
    )


def test_page_with_an_empty_body_still_gets_its_header() -> None:
    """An empty body leaves the header with no stray blank lines (5.2).

    Dies on: emitting the blank separator and an empty body block, which
    leaves extra blank lines before the next page.
    """
    site = _content(
        (
            _page("a.md", "A", "Guides", 1, body=""),
            _page("b.md", "B", "Guides", 2, body="Text\n"),
        )
    )
    assert render_llms_full(site, site_url=SITE_URL) == (
        "# A\nSource: https://example.test/a/\n\n"
        "# B\nSource: https://example.test/b/\n\nText\n"
    )


def test_full_text_uses_the_body_and_strips_only_newlines() -> None:
    """The block holds `body` alone, with its indentation and trailing spaces (5.2).

    The page's `staged_text` carries frontmatter and the body starts with a
    blank line, so a text built from `staged_text` shows frontmatter lines.

    Dies on: rendering `p.staged_text` instead of `p.body`; `.strip()` in place
    of `.strip("\\n")`, which eats the code indent and the trailing spaces.
    """
    page = _page("a.md", "Coded", "Guides", 1, body="\n    indented code\n\ntext  \n\n")
    assert page.staged_text.startswith("---\ntitle: Coded\n---\n")
    full = render_llms_full(_content((page,)), site_url=SITE_URL)
    assert full == (
        "# Coded\nSource: https://example.test/a/\n\n    indented code\n\ntext  \n"
    )
    assert "---" not in full
    assert "title:" not in full
