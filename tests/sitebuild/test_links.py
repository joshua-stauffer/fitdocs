"""Link extraction, GitHub heading slugs and the link checks (2.10, 2.12, 6.1, 6.3).

Pages are built from the model types and checked against a ``docs/`` tree in
``tmp_path``. The one test that reads the real repository ``docs/`` tree is the
fixture site's own docs link.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.sitebuild.content import load_content
from scripts.sitebuild.links import Link, check_links, extract_links, github_slugs
from scripts.sitebuild.model import Asset, HeroAction, Page, SiteContent

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "site"
DOCS = "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/"
FRONTMATTER = "---\ntitle: T\ndescription: D\nsection: Why\norder: 1\n---\n"
FRONTMATTER_LINES = FRONTMATTER.count("\n")


def _page(
    path: str,
    body: str = "",
    hero: tuple[HeroAction, ...] | None = None,
) -> Page:
    return Page(
        path=path,
        title="T",
        description="D",
        section="Home" if path == "index.md" else "Why",
        order=1,
        staged_text=FRONTMATTER + body,
        body=body,
        hero_title=None,
        hero_tagline=None,
        hero_actions=hero,
    )


def _site(*pages: Page, assets: tuple[str, ...] = ()) -> SiteContent:
    return SiteContent(
        root=Path("unused"),
        pages=pages,
        assets=tuple(Asset(rel, Path("unused") / rel) for rel in assets),
    )


def _repo(tmp_path: Path, **docs: str) -> Path:
    """A repo root whose ``docs/`` holds ``docs`` (name with ``__`` for ``/``)."""
    for name, text in docs.items():
        target = tmp_path / "docs" / name.replace("__", "/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (tmp_path / "docs").mkdir(exist_ok=True)
    return tmp_path


def _targets(body: str, first_line: int = 1) -> list[tuple[str, int]]:
    return [
        (link.target, link.line) for link in extract_links(body, first_line=first_line)
    ]


def _messages(content: SiteContent, root: Path) -> list[str]:
    return [problem.render() for problem in check_links(content, repo_root=root)]


# --- extract_links -------------------------------------------------------------


def test_inline_links_and_images_are_found_at_their_file_lines() -> None:
    """Inline links and images, with titles and paren targets, at file lines.

    Dies on: `base = first_line + start` becoming `base = start` in
    `extract_links` (every line number drops by first_line).
    """
    body = (
        "Intro [a](one.png) text\n"
        '![alt](two.png "a title") and [b](<three four.png>)\n'
        "\n"
        "[c](five(1).png 'x') [![img](six.png)](seven/) [empty]()\n"
    )
    assert _targets(body, first_line=10) == [
        ("one.png", 10),
        ("two.png", 11),
        ("three four.png", 11),
        ("five(1).png", 13),
        ("six.png", 13),
        ("seven/", 13),
    ]


def test_reference_definitions_are_found_and_footnotes_are_not() -> None:
    """A `[id]: target` definition is a link; a `[^n]: text` footnote is not.

    Dies on: deleting the `for match in _REFERENCE_DEF.finditer(masked):` loop in
    `extract_links` (no definition is found).
    """
    body = (
        'See [x] and [y]. <a href="h.png">\n\n'
        "[x]: asset.png\n[y]: <other file.png>\n[^1]: a note\n[i](i.png)\n[z]: <>\n"
    )
    assert _targets(body) == [
        ("h.png", 1),
        ("asset.png", 3),
        ("other file.png", 4),
        ("i.png", 6),
    ]


def test_html_href_and_src_are_found_with_either_quote_inside_tags_only() -> None:
    """`href` / `src` in a tag, either quote, unescaped and stripped; prose is not.

    Dies on: `_HTML_ATTR` losing its single-quote alternative (`src='two.png'`
    is missed).
    """
    body = (
        'Say href="prose.png" in prose.\n'
        "<a href=\"one.md#x\">a</a> <img src='two.png'>\n"
        '<a\n  class="k"\n  HREF = "three.png">t</a>\n'
        '<a href="q.png?a=1&amp;b=2"> <img src=" padded.png "></a>\n'
    )
    links = extract_links(body, first_line=1)
    assert links == (
        Link("one.md#x", 2, True),
        Link("two.png", 2, True),
        Link("three.png", 5, True),
        Link("q.png?a=1&b=2", 6, True),
        Link("padded.png", 6, True),
    )


def test_targets_in_fences_are_ignored_and_a_link_after_a_close_is_found() -> None:
    """Backtick/tilde fences, longer fences and 3-space indents hide links.

    Dies on: `_outside_fences` closing on any fence line (drop the
    `len(closing.group(1)) >= fence[1]` and `closing.group(1)[0] == fence[0]`
    checks), so a shorter or different fence line ends the block early.
    """
    body = (
        "[before](a.png)\n"
        "```\n[in1](b.png)\n```\n"
        "[after1](c.png)\n"
        "~~~\n[in2](d.png)\n~~~\n"
        "````\n```\n[in3](e.png)\n```\n````\n"
        "~~~~\n```\n[in4](f.png)\n~~~\n[in5](g.png)\n~~~~\n"
        "   ```\n[in6](h.png)\n   ```\n"
        "```\n[in7](j.png)\n~~~\n[in8](k.png)\n```\n"
        "[after2](i.png)\n"
    )
    assert _targets(body) == [("a.png", 1), ("c.png", 5), ("i.png", 28)]


def test_unclosed_fences_hide_the_rest_and_backtick_info_is_no_fence() -> None:
    """An unclosed fence runs to the end; ```` ``` a`b ```` is not a fence opener.

    Dies on: dropping the `and "`" in opening.group(2)` guard in
    `_outside_fences` (line 1 opens a fence that hides `[kept]`) or making an
    unclosed fence stop at the next blank line.
    """
    kept = "``` a`b\n[kept](k.png)\n"
    assert _targets(kept) == [("k.png", 2)]
    unclosed = "[seen](s.png)\n```\n[hidden](h.png)\n\n[also](x.png)\n"
    assert _targets(unclosed) == [("s.png", 1)]


def test_a_four_space_indented_fence_is_not_a_fence() -> None:
    """A fence indented four spaces does not hide the links after it.

    Dies on: `_FENCE_OPEN` allowing ` {0,4}` (or any `{0,N}` above 3) of indent.
    """
    body = "    ```\n[shown](s.png)\n"
    assert _targets(body) == [("s.png", 2)]


def test_code_spans_of_equal_backtick_runs_hide_targets() -> None:
    """A span closes on a run of the same length; other runs do not close it.

    Dies on: `_mask` closing a span on any backtick run (`m - k == size`
    becoming `True`), or `_mask` not masking spans at all.
    """
    body = (
        "`[in1](a.png)` then [out1](b.png)\n"
        "``code ` [in2](c.png) ``after [out2](d.png)\n"
        "`open [out3](e.png)\n"
        "\n"
        "a `x\ny [in4](f.png)` [out4](g.png)\n"
    )
    assert _targets(body) == [
        ("b.png", 1),
        ("d.png", 2),
        ("e.png", 3),
        ("g.png", 6),
    ]


def test_escaped_bracket_and_span_boundaries() -> None:
    """`\\[t](u)` is text; a backtick pairs across neither a blank line nor a fence.

    Dies on: `_opens` returning `True` at its first line (the escaped opener
    counts as a link).
    """
    body = (
        "\\[t](escaped.png) and [ok](ok.png)\n\nstray ` tick\n\n[end](end.png) `\n\n"
        "`stray\n```\nfenced\n```\n[out](out.png) `\n"
    )
    assert _targets(body) == [("ok.png", 1), ("end.png", 5), ("out.png", 11)]


def test_a_shorter_bracket_does_not_open_a_link() -> None:
    """`[a] b](x.png)` has no matching opener before its `](`.

    Dies on: `_opens` not incrementing depth at `]` (`pass` in place of
    `depth += 1`).
    """
    assert _targets("[a] b](x.png) and [c [d]](y.png)\n") == [("y.png", 1)]


def test_only_a_bare_fence_line_of_enough_length_closes_a_fence() -> None:
    """A closing fence has no info string, at most 3 spaces of indent, and may end CR.

    Dies on: the closing pattern in `_outside_fences` accepting text after the
    fence characters (`[ \t]*` becoming `.*`) hides the second link; accepting any
    indent hides the third; dropping the `rstrip()` misses the CRLF close.
    """
    with_info = "```\n```js\n[in1](a.png)\n```\n[out1](b.png)\n"
    assert _targets(with_info) == [("b.png", 5)]
    deep_close = "```\n[in2](c.png)\n    ```\n[in3](d.png)\n```\n[out2](e.png)\n"
    assert _targets(deep_close) == [("e.png", 6)]
    crlf = "```\r\n[in4](f.png)\r\n```\r\n[out3](g.png)\r\n"
    assert _targets(crlf) == [("g.png", 4)]


def test_a_tilde_fence_may_carry_backticks_in_its_info_string() -> None:
    """Only a backtick fence is refused a backtick in its info string.

    Dies on: the opener refusing a backtick in any fence's info string (the
    `opening.group(1)[0] == "`"` test dropped).
    """
    assert _targets("~~~ a`b\n[in](a.png)\n~~~\n[out](b.png)\n") == [("b.png", 4)]


def test_a_tag_written_inside_a_code_span_is_not_scanned() -> None:
    """An `<a href>` inside backticks is code, not a link.

    Dies on: `extract_links` scanning `_HTML_TAG` over `original` instead of
    `masked`.
    """
    body = '`<a href="x.md">` and <a href="y.png">\n'
    assert extract_links(body, first_line=1) == (Link("y.png", 1, True),)


def test_attribute_names_need_a_word_boundary_and_empty_values_are_skipped() -> None:
    """Only `href`, `src` and `xlink:href` are link attributes; `href=""` is empty.

    Dies on: `_HTML_ATTR` guarding with `\\b` instead of `(?<![\\w:.-])`
    (`data-href` is found), dropping `:` or `.` from that class (`v-bind:href`,
    `:href` or `data.src` is found), widening `xlink:href` to `(?:\\w+:)?`
    (`xlink:src` and `foo:href` are found), dropping `xlink:href` (it is
    missed), or dropping the `if target:` after the HTML attribute scan (an
    empty target).
    """
    body = (
        '<a data-href="d.md" href="">t</a> <img xsrc="e.png" src="f.png">\n'
        '<a :href="a.md" v-bind:href="b.md" data.src="c.md" XLINK:HREF="g.svg">\n'
        '<a xlink:src="z.md" foo:href="y.md">\n'
    )
    assert _targets(body) == [("f.png", 1), ("g.svg", 2)]


def test_unquoted_attribute_values_are_found_and_flagged() -> None:
    """`href=install.md` and `src=x.svg` are extracted, marked unquoted.

    Dies on: dropping the `(?P<uq>...)` alternative from `_HTML_ATTR` (nothing
    is extracted), `Link(..., group == "uq")` becoming `Link(..., False)`, or
    the unquoted class excluding `=` (`a.png?x=1` is cut to `a.png?x`).
    """
    body = (
        '<a href=install.md>a</a> <img src=x.svg/> <a href="q.md"> '
        "<a href=#a> <img src=a.png?x=1>\n"
    )
    assert extract_links(body, first_line=1) == (
        Link("install.md", 1, True, True),
        Link("x.svg/", 1, True, True),
        Link("q.md", 1, True, False),
        Link("#a", 1, True, True),
        Link("a.png?x=1", 1, True, True),
    )


def test_relative_unquoted_html_links_are_problems_and_are_not_resolved() -> None:
    """Relative unquoted `href` / `src` fail with file and line, even for a real asset.

    Dies on: deleting the `if link.unquoted:` report in `check_links` (the
    missing page and asset go unreported), letting the report fall through
    to the asset check (`x.svg` exists, so it would pass), or reporting before
    the fragment-only skip (`href=#a` is flagged).
    """
    body = (
        "<a href=install.md>a</a> <a href=#a>a</a> <img src=a.png?x=1>\n\n"
        "<img src=missing.svg> <img src=x.svg>\n"
        "<a href=https://example.org/a.md>abs</a>\n"
    )
    content = _site(_page("why.md", body), assets=("x.svg",))
    line = FRONTMATTER_LINES + 1
    msg = "has an unquoted attribute value that the generator does not rewrite"
    assert _messages(content, ROOT) == [
        f"why.md: {line}: raw HTML link a.png?x=1 {msg}: quote the value",
        f"why.md: {line}: raw HTML link install.md {msg}: quote the value",
        f"why.md: {line + 2}: raw HTML link missing.svg {msg}: quote the value",
        f"why.md: {line + 2}: raw HTML link x.svg {msg}: quote the value",
    ]


def test_an_xlink_href_asset_is_checked_like_an_href() -> None:
    """A missing `xlink:href` asset is reported, a present one is not.

    Dies on: dropping `(?:xlink:)?` from `_HTML_ATTR` (the missing asset goes
    unreported).
    """
    body = '<svg><use xlink:href="nope.svg"/><use xlink:href="x.svg"/></svg>\n'
    content = _site(_page("why.md", body), assets=("x.svg",))
    assert _messages(content, ROOT) == [
        f"why.md: {FRONTMATTER_LINES + 1}: link nope.svg is neither an included "
        "asset nor a page URL"
    ]


def test_a_parenthesised_title_and_a_next_line_definition_target_are_handled() -> None:
    """`[a](x.png (t))` ends at the title; `[r]:` may take its target next line.

    Dies on: `_INLINE_DEST` losing its `\\([^()]*\\)` title alternative, or
    `_REFERENCE_DEF` losing its `\\n?` (the next-line target is missed).
    """
    body = "[a](x.png (t))\n\n[r]:\n  y.png\n"
    assert _targets(body) == [("x.png", 1), ("y.png", 4)]


# --- github_slugs -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("# [load]", {"load"}),
        ("# `[load]`: calculator selection", {"load-calculator-selection"}),
        ("# C++ & Python", {"c--python"}),
        ("# snake_case name", {"snake_case-name"}),
        ("# TSS / hrTSS \u2014 load", {"tss--hrtss--load"}),
        ("# \U0001f680 Launch", {"-launch"}),
        ("# Caf\u00e9 r\u00e9sum\u00e9", {"caf\u00e9-r\u00e9sum\u00e9"}),
        ("# The `load` command", {"the-load-command"}),
        ("# a - b", {"a---b"}),
        (
            "# \u24b6 b \U0001f130\U0001f150\U0001f170",
            {"\u24d0-b-\U0001f130\U0001f150\U0001f170"},
        ),
        ("# TSS-based", {"tss-based"}),
    ],
)
def test_slug_conformance_table(markdown: str, expected: set[str]) -> None:
    """The task's conformance table, one heading per row.

    Dies on: `_keeps` returning `True` for every character (no punctuation,
    symbol or emoji is removed).
    """
    assert github_slugs(markdown) == frozenset(expected)


def test_repeated_headings_get_numbered_suffixes() -> None:
    """The second and third `Setup` become `setup-1` and `setup-2`.

    Dies on: deleting the `while slug in occurrences:` loop in `github_slugs`
    (every repeat maps to `setup`).
    """
    assert github_slugs("# Setup\n## Setup\n### Setup\n## Other\n") == frozenset(
        {"setup", "setup-1", "setup-2", "other"}
    )


def test_a_heading_that_already_looks_like_a_suffixed_slug_is_renumbered() -> None:
    """After `a`, `a`, the heading `a-1` collides with the second one: `a-1-1`.

    Dies on: the duplicate loop replaced by a per-base counter
    (`n = occurrences.get(base, 0)`), which would give `a-1` twice.
    """
    assert github_slugs("# a\n# a\n# a-1\n") == frozenset({"a", "a-1", "a-1-1"})


def test_alphabetic_symbol_ranges_are_kept_to_their_exact_ends() -> None:
    """Each end of github-slugger's four Alphabetic `So` ranges is kept; the code
    point just outside each end is removed.

    Dies on: shifting one end of a `_ALPHABETIC_SYMBOLS` range by one, for seven
    of the eight ends and for the start `0x24B6` moved outward. Moving that start
    inward survives: `lower()` maps `0x24B6` to `0x24D0` before `_keeps` sees it.
    """
    inside = [0x24B6, 0x24E9, 0x1F130, 0x1F149, 0x1F150, 0x1F169, 0x1F170, 0x1F189]
    outside = [0x24B5, 0x24EA, 0x1F12F, 0x1F14A, 0x1F14F, 0x1F16A, 0x1F16F, 0x1F18A]
    for point in inside:
        char = chr(point)
        assert github_slugs(f"# a{char}b") == frozenset({f"a{char.lower()}b"}), hex(
            point
        )
    for point in outside:
        assert github_slugs(f"# a{chr(point)}b") == frozenset({"ab"}), hex(point)


def test_empty_headings_take_part_in_numbering() -> None:
    """A bare `#` slugs to the empty string and a second one to `-1`.

    Dies on: `_heading_texts` skipping headings with no text.
    """
    assert github_slugs("#\n#\n") == frozenset({"", "-1"})


def test_underscore_is_kept_and_other_connectors_follow_the_category() -> None:
    """`_` (Connector_Punctuation) and the tie `\u203f` are kept.

    Dies on: `_keeps` dropping category `Pc` (adding `"Pc"` to
    `_DROPPED_CATEGORIES`).
    """
    assert github_slugs("# a_b\u203fc") == frozenset({"a_b\u203fc"})


def test_letters_are_not_limited_to_ascii_and_marks_and_numerals_are_kept() -> None:
    """Non-ASCII letters, a combining mark and a letter-numeral survive.

    Dies on: `_keeps` keeping only ASCII word characters
    (`return char.isascii() and (char.isalnum() or char in "_- ")`).
    """
    assert github_slugs("# Cafe\u0301 \u2163 \u0416\u0443\u043a") == frozenset(
        {"cafe\u0301-\u2173-\u0436\u0443\u043a"}
    )


def test_each_removed_category_is_removed() -> None:
    """One character of each removed family vanishes from the slug.

    Dies on: `_keeps` for a family: dropping `"No"` from
    `_DROPPED_CATEGORIES` keeps `\u00b2`; changing `"SZ"` keeps `$`, `+` or NBSP;
    dropping `"Pd"` keeps the en dash; dropping `"Cf"` keeps the zero-width space.
    """
    removed = {
        "superscript two": "\u00b2",
        "dollar (Sc)": "$",
        "plus (Sm)": "+",
        "no-break space (Zs)": "\u00a0",
        "en dash (Pd)": "\u2013",
        "zero-width space (Cf)": "\u200b",
        "left quote (Pi)": "\u201c",
        "right quote (Pf)": "\u201d",
        "open paren (Ps)": "(",
        "close paren (Pe)": ")",
        "slash (Po)": "/",
    }
    for name, char in removed.items():
        assert github_slugs(f"# a{char}b") == frozenset({"ab"}), name


def test_hyphens_and_spaces_are_not_collapsed_or_trimmed() -> None:
    """Runs of spaces and hyphens survive one for one.

    Dies on: `github_slugs` collapsing `-` runs (`re.sub("-+", "-", base)`).
    """
    assert github_slugs("# a  --  b") == frozenset({"a------b"})


def test_only_atx_headings_outside_fences_count() -> None:
    """Fenced `#` lines, indented code, `#tag` and setext underlines are ignored.

    Dies on: `_heading_texts` reading `lines` instead of `_outside_fences(lines)`
    (the fenced heading is counted), or `_ATX` allowing a missing space.
    """
    markdown = (
        "```\n# fenced backtick\n```\n"
        "~~~\n## fenced tilde\n~~~\n"
        "    # indented four\n"
        "#nospace\n"
        "Setext\n======\n"
        "## Real ##\n"
        "   ### Three\n"
    )
    assert github_slugs(markdown) == frozenset({"real", "three"})


# --- check_links: assets -------------------------------------------------------------


def test_asset_targets_resolve_relative_to_the_page_with_dotdot_normalised() -> None:
    """A present asset passes; a missing one names file, line and target.

    Dies on: `_resolve` joining onto the content root instead of the page's
    directory (`directory = ""`).
    """
    body = (
        "![ok](../../images/diagram.svg)\n"
        "![bad](../images/diagram.svg)\n"
        "![query](../../images/diagram.svg?v=2#top)\n"
        "![space](../../images/my%20pic.png)\n"
    )
    content = _site(
        _page("guides/nested/deep.md", body),
        assets=("images/diagram.svg", "images/my pic.png"),
    )
    problems = check_links(content, repo_root=ROOT)
    assert [p.render() for p in problems] == [
        "guides/nested/deep.md: "
        f"{FRONTMATTER_LINES + 2}: link ../images/diagram.svg is neither an "
        "included asset nor a page URL"
    ]


def test_an_asset_link_out_of_the_content_root_is_a_problem() -> None:
    """`../` past the root fails even when the remaining path names an asset.

    Dies on: `_resolve` returning `joined` without the `..` guard.
    """
    content = _site(
        _page("why.md", "[x](../images/diagram.svg)\n"), assets=("images/diagram.svg",)
    )
    assert _messages(content, ROOT) == [
        f"why.md: {FRONTMATTER_LINES + 1}: link ../images/diagram.svg leaves the "
        "content root"
    ]


def test_directory_urls_of_included_pages_are_valid_targets() -> None:
    """A link to an included page's directory URL passes; an unknown one fails.

    Dies on: the `page_urls` membership becoming `assets` (or the reverse), or
    `_resolve` marking only a literal trailing slash as directory form (`.`
    from `guides/index.md` resolves to `guides`, which is no page URL).
    """
    content = _site(
        _page("index.md", "[a](get-started/install/) [b](get-started/nope/) [h](./)\n"),
        _page("get-started/install.md"),
        _page("get-started/first-run.md", "[up](install/) [root](../)\n"),
        _page("guides/index.md", "[self](.) [home](..)\n"),
    )
    assert _messages(content, ROOT) == [
        f"index.md: {FRONTMATTER_LINES + 1}: link get-started/nope/ is neither an "
        "included asset nor a page URL"
    ]


def test_a_root_relative_target_is_resolved_from_the_content_root() -> None:
    """`/images/diagram.svg` from a nested page is the asset at the root.

    Dies on: `_resolve` using the page's directory for a leading `/`.
    """
    content = _site(
        _page("guides/nested/deep.md", "![x](/images/diagram.svg)\n"),
        assets=("images/diagram.svg",),
    )
    assert check_links(content, repo_root=ROOT) == ()


# --- check_links: page links --------------------------------------------------------


def test_markdown_syntax_page_links_are_left_to_the_generator() -> None:
    """Missing `.md` targets in inline, image and reference syntax are not reported.

    Dies on: the `.md` branch reporting for every link (dropping the
    `if link.html:` condition).
    """
    body = "[a](missing.md#x) ![b](gone.md)\n\n[r]: nowhere.md\n"
    assert check_links(_site(_page("why.md", body)), repo_root=ROOT) == ()


def test_raw_html_page_links_name_the_file_and_line() -> None:
    """`<a href>` and `<img src>` at a `.md` target are problems with file and line.

    Dies on: the `.md` branch skipping HTML links (`continue` without the
    `if link.html:` report), or `first_line` ignoring the frontmatter.
    """
    body = (
        'ok <a href="other.png">x</a>\n\n'
        'text <a href="other.md#h">y</a> <img src="b.md">\n'
    )
    line = FRONTMATTER_LINES + 3
    assert _messages(_site(_page("why.md", body), assets=("other.png",)), ROOT) == [
        f"why.md: {line}: raw HTML link to page b.md: use markdown link syntax so "
        "the generator checks it",
        f"why.md: {line}: raw HTML link to page other.md#h: use markdown link syntax "
        "so the generator checks it",
    ]


def test_absolute_mailto_and_anchor_links_are_not_checked_here() -> None:
    """https, protocol-relative, `mailto:` and `#anchor` targets raise nothing.

    Dies on: `check_links` treating a target with a scheme as relative (the
    `_is_absolute(target)` branch removed), which reports `https://example.org/a.png`;
    or the docs-URL test using `DOCS_URL_PREFIX.search` (a docs URL inside a query
    string is checked).
    """
    body = (
        "[a](https://example.org/a.png) [b](//example.org/b.png) "
        "[c](mailto:me@example.org) [d](#section) "
        "[e](https://github.com/other/fitdocs/blob/main/docs/nope.md#x) "
        f"[f](https://example.org/?u={DOCS}nope.md)\n"
    )
    assert check_links(_site(_page("why.md", body)), repo_root=ROOT) == ()


# --- check_links: hero hrefs --------------------------------------------------------


def _hero(*hrefs: str) -> tuple[HeroAction, ...]:
    return tuple(HeroAction(f"L{i}", href, i == 0) for i, href in enumerate(hrefs))


def test_hero_hrefs_must_be_included_page_urls_or_https() -> None:
    """A good relative and https href pass; every other kind names its action.

    Dies on: the hero relative check comparing to anything but `page_urls`
    (e.g. accepting any relative href), or dropping the `https://` prefix test.
    """
    hero = _hero(
        "get-started/install/",  # 0 good
        "https://example.org/story",  # 1 good
        "get-started/nope/",  # 2 unknown page
        "get-started/install",  # 3 missing slash
        "http://example.org/x",  # 4 not https
        "mailto:me@example.org",  # 5 not https
        "why/",  # 6 a page that is not included
    )
    content = _site(_page("index.md", "", hero), _page("get-started/install.md"))
    assert _messages(content, ROOT) == [
        "index.md: hero_actions[2].href: href get-started/nope/ is not the URL path "
        "of an included page",
        "index.md: hero_actions[3].href: href get-started/install is not the URL path "
        "of an included page",
        "index.md: hero_actions[4].href: absolute href http://example.org/x must be "
        "https://",
        "index.md: hero_actions[5].href: absolute href mailto:me@example.org must be "
        "https://",
        "index.md: hero_actions[6].href: href why/ is not the URL path of an included "
        "page",
    ]


def test_hero_href_may_name_the_home_page_by_its_empty_path() -> None:
    """The home page's URL path is the empty string, and another page's is not.

    Dies on: the page-URL set being built from `page.path` instead of
    `page_path(page.path)`.
    """
    content = _site(_page("index.md", "", _hero("", "index.md")))
    assert _messages(content, ROOT) == [
        "index.md: hero_actions[1].href: href index.md is not the URL path of an "
        "included page"
    ]


def test_a_plain_http_hero_docs_url_needs_https(tmp_path: Path) -> None:
    """An existing `http://` docs file is still not an acceptable hero href.

    Dies on: the hero branch testing `DOCS_URL_PREFIX` before the `https://`
    requirement (the http docs URL then passes).
    """
    root = _repo(tmp_path, **{"there.md": "# Here\n"})
    http = DOCS.replace("https://", "http://") + "there.md#here"
    content = _site(_page("index.md", "", _hero(http)))
    assert _messages(content, root) == [
        f"index.md: hero_actions[0].href: absolute href {http} must be https://"
    ]


def test_a_hero_href_to_docs_is_checked_like_a_body_link(tmp_path: Path) -> None:
    """A hero href into `docs/` needs its file to exist.

    Dies on: the hero loop skipping `check_absolute_or_docs`.
    """
    root = _repo(tmp_path, **{"there.md": "# Here\n"})
    content = _site(
        _page("index.md", "", _hero(DOCS + "there.md#here", DOCS + "gone.md"))
    )
    assert _messages(content, root) == [
        f"index.md: hero_actions[1].href: docs URL {DOCS}gone.md: docs/gone.md does "
        "not exist in the repository"
    ]


# --- check_links: docs URLs ----------------------------------------------------------


def test_docs_urls_check_file_then_anchor(tmp_path: Path) -> None:
    """A valid URL passes; a missing file and a missing anchor each fail.

    Dies on: `_check_docs_url` returning `None` before the anchor test, or
    before the file test (`candidate.is_file()` dropped).
    """
    root = _repo(tmp_path, **{"guide.md": "# Guide\n\n## The `[load]` step\n"})
    body = (
        f"[ok]({DOCS}guide.md#the-load-step)\n"
        f"[nofile]({DOCS}absent.md#x)\n"
        f"[noanchor]({DOCS}guide.md#the-other-step)\n"
        f"[nofrag]({DOCS}guide.md)\n"
    )
    assert _messages(_site(_page("why.md", body)), root) == [
        f"why.md: {FRONTMATTER_LINES + 2}: docs URL {DOCS}absent.md#x: docs/absent.md "
        "does not exist in the repository",
        f"why.md: {FRONTMATTER_LINES + 3}: docs URL {DOCS}guide.md#the-other-step: "
        "anchor #the-other-step matches no heading in docs/guide.md",
    ]


def test_docs_anchors_follow_github_slugs_not_a_simpler_slugger(tmp_path: Path) -> None:
    """Duplicate suffixes, underscores, accents and fences decide what anchors exist.

    Dies on: `_check_docs_url` using a slugger that drops `_`, omits `-N`
    suffixes or counts fenced headings (each changes which lines fail).
    """
    text = "# Setup\n## Setup\n## snake_case\n## Caf\u00e9\n```\n# Fenced only\n```\n"
    root = _repo(tmp_path, **{"a.md": text})
    body = (
        f"[1]({DOCS}a.md#setup)\n"
        f"[2]({DOCS}a.md#setup-1)\n"
        f"[3]({DOCS}a.md#snake_case)\n"
        f"[4]({DOCS}a.md#caf%C3%A9)\n"
        f"[5]({DOCS}a.md#setup-2)\n"
        f"[6]({DOCS}a.md#snakecase)\n"
        f"[7]({DOCS}a.md#fenced-only)\n"
    )
    failing = [
        p.where for p in check_links(_site(_page("why.md", body)), repo_root=root)
    ]
    assert failing == [str(FRONTMATTER_LINES + n) for n in (5, 6, 7)]


def test_docs_url_accepts_http_subdirectories_and_non_markdown_files(
    tmp_path: Path,
) -> None:
    """`http://`, a nested or encoded file name and a non-`.md` fragment behave.

    Dies on: `DOCS_URL_PREFIX` requiring `https` (`https?` becoming `https`, so
    the missing-file `http://` URL goes unchecked), or the anchor check applying
    to non-`.md` files (`candidate.suffix != ".md"` dropped).
    """
    root = _repo(
        tmp_path,
        **{
            "reference__cli.md": "# CLI\n",
            "sample.toml": "a = 1\n",
            "my file.md": "# Mine\n",
        },
    )
    http = DOCS.replace("https://", "http://")
    body = (
        f"[a]({http}reference/cli.md#cli) [b]({DOCS}sample.toml#L1) "
        f"[c]({DOCS}my%20file.md#mine)\n"
        f"[bad]({http}absent.md)\n"
    )
    assert _messages(_site(_page("why.md", body)), root) == [
        f"why.md: {FRONTMATTER_LINES + 2}: docs URL {http}absent.md: docs/absent.md "
        "does not exist in the repository"
    ]


def test_docs_url_cannot_escape_the_docs_tree(tmp_path: Path) -> None:
    """`docs/../secret.md` exists in the repo but is not under `docs/`.

    Dies on: `_check_docs_url` dropping the `root not in candidate.parents` test.
    """
    root = _repo(tmp_path, **{"ok.md": "# ok\n"})
    (root / "secret.md").write_text("# s\n", encoding="utf-8")
    body = f"[x]({DOCS}../secret.md) [dir]({DOCS})\n"
    line = FRONTMATTER_LINES + 1
    assert _messages(_site(_page("why.md", body)), root) == [
        f"why.md: {line}: docs URL {DOCS}../secret.md: docs/../secret.md does not "
        "exist in the repository",
        f"why.md: {line}: docs URL {DOCS}: docs/ does not exist in the repository",
    ]


def test_an_unreadable_docs_file_with_a_fragment_is_a_problem(tmp_path: Path) -> None:
    """A docs `.md` that is not UTF-8 cannot have its anchors checked.

    Dies on: the read-error branch of `_check_docs_url` returning `None`.
    """
    root = _repo(tmp_path)
    (root / "docs" / "latin.md").write_bytes(b"# caf\xe9\n")
    body = f"[x]({DOCS}latin.md#caf)\n"
    assert _messages(_site(_page("why.md", body)), root) == [
        f"why.md: {FRONTMATTER_LINES + 1}: docs URL {DOCS}latin.md#caf: "
        "docs/latin.md cannot be read: UnicodeDecodeError"
    ]


def test_a_directory_link_missing_its_slash_says_so() -> None:
    """`get-started/install` names a page but lacks the trailing slash.

    Dies on: dropping the `resolved + "/" in page_urls` hint (the generic
    message is used).
    """
    content = _site(
        _page("index.md", "[a](get-started/install)\n"),
        _page("get-started/install.md"),
    )
    assert _messages(content, ROOT) == [
        f"index.md: {FRONTMATTER_LINES + 1}: link get-started/install is missing "
        "its trailing slash: get-started/install/ is a page URL"
    ]


# --- check_links: aggregate ---------------------------------------------------


def test_every_violation_is_reported_once_and_sorted(tmp_path: Path) -> None:
    """Problems from three pages come out sorted, and an exact repeat is one problem.

    Dies on: `check_links` returning `tuple(problems)` instead of the sorted
    tuple, or collecting into a list rather than a set (the repeated link is
    reported twice).
    """
    root = _repo(tmp_path)
    why = _page("why.md", "[a](z.png) [a](z.png)\n\n[b](y.png)\n\n[c](w.png)\n")
    install = _page("get-started/install.md", "[c](x.png)\n\n[e](u.png)\n")
    home = _page("index.md", "", _hero("nope/", "http://example.org/"))
    problems = check_links(_site(why, install, home), repo_root=root)
    assert len(problems) == 7
    assert {p.path for p in problems} == {
        "why.md",
        "get-started/install.md",
        "index.md",
    }
    assert problems == tuple(
        sorted(problems, key=lambda p: (p.path, p.where, p.message))
    )


# --- the fixture site ---------------------------------------------------------------


def test_the_fixture_site_passes_including_its_link_into_the_real_docs_tree() -> None:
    """The fixture's `docs/` link is found, and the site has no link problems.

    Dies on: `_keeps` treating punctuation (`[`, `]`, `:`) as kept, so the real
    heading `` `[load]`: calculator selection ... `` slugs differently.
    """
    content, problems = load_content(FIXTURE)
    assert problems == ()
    assert content is not None
    why = next(page for page in content.pages if page.path == "why.md")
    docs_links = [
        link.target
        for link in extract_links(why.body, first_line=1)
        if link.target.startswith(DOCS)
    ]
    assert docs_links == [
        DOCS
        + "configuration.md#load-calculator-selection-and-training-load-computation"
    ]
    assert check_links(content, repo_root=ROOT) == ()
