"""The valid fixture site every later site-build test derives from (9.1).

Here the tree under ``fixtures/site`` is the thing under test, so each test's
``Dies on:`` line names an edit to the fixture tree rather than to production
code.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from collections.abc import Hashable
from pathlib import Path
from typing import Any

import yaml
from scripts.sitebuild.model import (
    ANNOTATION_MARKER,
    HERO_ACTION_KEYS,
    HERO_KEYS,
    HOME_PAGE,
    OPTIONAL_KEYS,
    REQUIRED_KEYS,
    SECTIONS,
)

ROOT = Path(__file__).resolve().parents[2]
SITE = Path(__file__).resolve().parent / "fixtures" / "site"

HOME, WHY, GET_STARTED, GUIDES, LLMS, REFERENCE = SECTIONS[:6]

ANNOTATION_SENTINEL = "ANNOTSENTINELAMBER"
NOTES_SENTINEL = "NOTESSENTINELFERN"
PRIVATE_SENTINEL = "PRIVATESENTINELONYX"
DRAFT_SENTINEL = "DRAFTSENTINELCOBALT"
DOTFILE_SENTINEL = "DOTFILESENTINELWILLOW"
DRAFT_TITLE = "Command reference"

DOCS_URL = (
    "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/configuration.md"
    "#load-calculator-selection-and-training-load-computation"
)

# Every file of the tree, content-relative. Pinning the whole set keeps an
# unlisted extra file (athlete data, a stray asset) from riding along.
EXPECTED_FILES = frozenset(
    {
        "index.md",
        "why.md",
        "get-started/install.md",
        "get-started/first-run.md",
        "guides/nested/deep.md",
        "llms/prompts.md",
        "reference/cli.md",
        "_notes.md",
        "_private/secret.md",
        ".editor-state",
        "images/diagram.svg",
    }
)
EXCLUDED_FILES = frozenset({"_notes.md", "_private/secret.md", ".editor-state"})

_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
_ANNOTATION_TAIL = re.compile(
    r"\A\n\n---\nAnnotations: 0,\d+ SHA-256 [0-9a-f]{64}  \n"
    r"(&Claude: [^\n]*  \n)+@Josh:   \n\Z"
)


class _StrictLoader(yaml.SafeLoader):
    """A safe loader that refuses a mapping with a repeated key."""

    def construct_mapping(
        self, node: yaml.MappingNode, deep: bool = False
    ) -> dict[Hashable, Any]:
        keys = [self.construct_object(k, deep=deep) for k, _ in node.value]
        repeated = sorted({str(k) for k in keys if keys.count(k) > 1})
        if repeated:
            raise yaml.YAMLError(f"duplicate keys: {repeated}")
        return super().construct_mapping(node, deep=deep)


def _files() -> dict[str, Path]:
    """Every file under the fixture tree, keyed by content-relative path."""
    return {
        p.relative_to(SITE).as_posix(): p
        for p in sorted(SITE.rglob("*"))
        if p.is_file()
    }


def _text(relative: str) -> str:
    """The file's text decoded from its bytes, so a carriage return survives."""
    return (SITE / relative).read_bytes().decode("utf-8")


def _split(relative: str) -> tuple[dict[str, Any], str]:
    """Frontmatter mapping and the text after its closing line."""
    lines = _text(relative).split("\n")
    assert lines[0] == "---", relative
    close = lines.index("---", 1)
    front = yaml.load("\n".join(lines[1:close]), Loader=_StrictLoader)
    assert isinstance(front, dict), relative
    return front, "\n".join(lines[close + 1 :])


def _without_annotation(text: str) -> str:
    i = text.rfind(ANNOTATION_MARKER)
    return text if i < 0 else text[: i + 1]


def _slug(heading: str) -> str:
    """An ASCII approximation of GitHub's heading anchor.

    Lowercase, drop every character but word characters, ``-`` and space, then
    turn spaces into ``-``. It adds no ``-1`` suffix for a repeated heading and
    does not model non-ASCII text; it is adequate for the headings used here,
    which the tests require to be unique.
    """
    text = heading.replace("`", "").strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def _headings(text: str) -> list[str]:
    """ATX heading texts outside fenced code blocks (column-0 fences only)."""
    found: list[str] = []
    fenced = False
    for line in text.split("\n"):
        if line.startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced:
            match = re.fullmatch(r"#{1,6} +(.+?) *", line)
            if match:
                found.append(match.group(1))
    return found


def _pages() -> dict[str, tuple[dict[str, Any], str]]:
    """Every markdown file no `_` or `.` path component excludes, drafts included."""
    return {
        path: _split(path)
        for path in _files()
        if path.endswith(".md")
        and not any(c.startswith(("_", ".")) for c in path.split("/"))
    }


def test_the_tree_holds_exactly_the_expected_files() -> None:
    """The fixture tree is the listed species and nothing else (9.1).

    Dies on: deleting any fixture file, or adding an unlisted one.
    """
    assert set(_files()) == EXPECTED_FILES
    assert len(EXPECTED_FILES) == 11


def test_home_page_carries_the_hero_and_a_link_to_why() -> None:
    """`index.md` is the Home page with two hero actions and no tagline (3.4).

    Dies on: deleting `hero_title`, adding `hero_tagline`, removing `primary: true`,
    adding `primary` to the second action, changing its `href`, dropping the
    `why.md#...` link, moving it into a code fence, or removing the Why heading
    it points at.
    """
    assert HOME_PAGE == "index.md"
    front, body = _split("index.md")
    assert front["section"] == HOME
    assert front["hero_title"] == "Fixture hero title"
    assert "hero_tagline" not in front
    actions = front["hero_actions"]
    assert len(actions) == 2
    assert [a.get("primary", False) for a in actions] == [True, False]
    assert actions[1]["href"] == "get-started/install/"
    assert actions[0]["href"].startswith("https://")
    prose = _without_annotation(body)
    assert "```" not in prose
    assert "(why.md#why-a-fixture-exists)" in prose
    why_slugs = [_slug(h) for h in _headings(_split("why.md")[1])]
    assert why_slugs.count("why-a-fixture-exists") == 1


def test_hero_site_path_names_an_included_page() -> None:
    """The install action's site path is an included page's URL path (2.3).

    Dies on: renaming `get-started/install.md`, drafting it, or changing the
    action's `href` to a path no page has.
    """
    front, _ = _split("index.md")
    href = front["hero_actions"][1]["href"]
    assert href.endswith("/")
    included = {p: f for p, (f, _) in _pages().items() if f.get("draft") is not True}
    assert href.removesuffix("/") + ".md" in included


def test_why_page_has_rule_annotation_and_docs_link() -> None:
    """The Why page keeps a plain rule and links a real `docs/` heading (1.7, 6.3).

    Dies on: removing the blank line before the plain `---` line (which makes
    it a setext underline), removing the rule, wrapping it in a code fence,
    deleting the docs URL, or renaming the `[load]` heading in
    `docs/configuration.md` (or moving it into a fence) away from the linked
    anchor.
    """
    front, body = _split("why.md")
    assert front["section"] == WHY
    prose = _without_annotation(body)
    assert prose != body
    assert "\n\n---\n\n" in prose
    assert "```" not in prose
    assert f"({DOCS_URL})" in prose
    docs = (ROOT / "docs" / "configuration.md").read_bytes().decode("utf-8")
    anchors = [_slug(h) for h in _headings(docs)]
    target = DOCS_URL.rsplit("#", 1)[1]
    assert anchors.count(target) == 1


def test_annotation_blocks_have_the_pkm_shape() -> None:
    """Home and Why each end in one annotation block of the documented shape (1.6).

    Dies on: dropping the trailing newline of `why.md`, changing `0,1` to a
    non-numeric count, shortening the hash, removing the two trailing spaces
    of the `@Josh:` line, or giving any other page an annotation marker.
    """
    for path in ("index.md", "why.md"):
        text = _text(path)
        assert text.count(ANNOTATION_MARKER) == 1, path
        assert _ANNOTATION_TAIL.match(text[text.rfind(ANNOTATION_MARKER) :]), path
    others = [
        p
        for p in _files()
        if p not in ("index.md", "why.md") and ANNOTATION_MARKER in _text(p)
    ]
    assert others == []


def test_annotation_sentinel_is_only_inside_annotation_blocks() -> None:
    """The sentinel word is in the Why annotation and nowhere else (1.8).

    Dies on: copying the word into the Why body, into another file, or removing
    it from the annotation.
    """
    holders = {p for p in _files() if ANNOTATION_SENTINEL in _text(p)}
    assert holders == {"why.md"}
    text = _text("why.md")
    assert ANNOTATION_SENTINEL in text[text.rfind(ANNOTATION_MARKER) :]
    assert ANNOTATION_SENTINEL not in _without_annotation(text)


def test_get_started_orders_disagree_with_alphabetical_order() -> None:
    """Two Get started pages, listed against their alphabetical order (3.2).

    Dies on: giving `first-run.md` order 1, or `install.md` order 2 (the orders
    then agree with the path order), moving `install.md` out of the section,
    or adding a third Get started page.
    """
    pages = {p: f for p, (f, _) in _pages().items() if f["section"] == GET_STARTED}
    assert sorted(pages) == ["get-started/first-run.md", "get-started/install.md"]
    by_path = [pages[p]["order"] for p in sorted(pages)]
    by_title = [
        pages[p]["order"] for p in sorted(pages, key=lambda p: pages[p]["title"])
    ]
    assert by_path == [2, 1]
    assert by_title == [2, 1]


def test_get_started_pages_carry_a_code_block_and_an_image_link() -> None:
    """One Get started page has a fenced block, the other an image link (1.5).

    Dies on: removing or indenting a fence line in `install.md`, emptying the
    block, changing the image path or dropping the `!` in `first-run.md`,
    putting a fence in `first-run.md`, or deleting `images/diagram.svg`.
    """
    install = _split("get-started/install.md")[1].split("\n")
    fences = [i for i, line in enumerate(install) if line.startswith("```")]
    assert [install[i] for i in fences] == ["```sh", "```"]
    assert "".join(install[fences[0] + 1 : fences[1]]).strip()
    first_run = _split("get-started/first-run.md")[1]
    assert "\n![A diagram of the pipeline](../images/diagram.svg)\n" in first_run
    assert "```" not in first_run
    svg = _text("images/diagram.svg")
    assert svg.startswith("<svg ")
    assert "</svg>" in svg


def test_remaining_sections_have_their_pages() -> None:
    """A nested guide, one LLMs page and one drafted Reference page (2.4).

    Dies on: moving `deep.md` up a level, changing the LLMs page's section,
    removing `draft: true`, adding a second Reference page (`reference/api.md`),
    copying the drafted page's title anywhere in an included page's file, or copying its
    sentinel into another file.
    """
    pages = _pages()
    assert pages["guides/nested/deep.md"][0]["section"] == GUIDES
    llms = [p for p, (f, _) in pages.items() if f["section"] == LLMS]
    assert llms == ["llms/prompts.md"]
    reference = {p: f for p, (f, _) in pages.items() if f["section"] == REFERENCE}
    assert list(reference) == ["reference/cli.md"]
    assert reference["reference/cli.md"]["draft"] is True
    assert reference["reference/cli.md"]["title"] == DRAFT_TITLE
    assert DRAFT_SENTINEL in pages["reference/cli.md"][1]
    assert {p for p in _files() if DRAFT_SENTINEL in _text(p)} == {"reference/cli.md"}
    for path in pages:
        if path != "reference/cli.md":
            assert DRAFT_TITLE not in _text(path), path


def test_excluded_species_carry_distinct_sentinels() -> None:
    """`_notes.md`, `_private/secret.md` and a dotfile each hold their own word (1.4).

    Dies on: removing a sentinel word, giving two files the same one, copying
    one into an included page, or renaming `.editor-state` (for example to
    `.DS_Store`).
    """
    expected = {
        "_notes.md": NOTES_SENTINEL,
        "_private/secret.md": PRIVATE_SENTINEL,
        ".editor-state": DOTFILE_SENTINEL,
    }
    assert set(expected) == EXCLUDED_FILES
    assert len(set(expected.values())) == 3
    for path, word in expected.items():
        assert {p for p in _files() if word in _text(p)} == {path}, word


def test_every_page_has_valid_frontmatter_and_a_unique_slot() -> None:
    """Every page has contract frontmatter; no non-draft slot repeats (2.1, 2.3, 2.6).

    Dies on: deleting `description`, adding an unknown key such as `tags`,
    putting `hero_title` on `why.md`, setting `template` on `index.md`, writing
    `draft: "no"`, repeating the `order` key, adding `icon` to a hero action,
    emptying a hero label, using a section outside `SECTIONS`, writing `order`
    as a string or boolean, or giving two pages of one section the same `order`.
    """
    pages = _pages()
    assert len(pages) == 7
    slots: list[tuple[str, int]] = []
    for path, (front, _) in pages.items():
        allowed = set(REQUIRED_KEYS + OPTIONAL_KEYS)
        if path == HOME_PAGE:
            allowed |= set(HERO_KEYS)
        assert set(front) <= allowed, (path, sorted(set(front) - allowed))
        assert set(REQUIRED_KEYS) <= set(front), path
        for key in ("title", "description"):
            assert isinstance(front[key], str) and front[key].strip(), (path, key)
        assert front["section"] in SECTIONS, path
        assert type(front["order"]) is int, path
        if "draft" in front:
            assert type(front["draft"]) is bool, path
        if front.get("draft") is not True:
            slots.append((front["section"], front["order"]))
    assert len(slots) == 6
    assert len(set(slots)) == len(slots)
    assert {s for s, _ in slots} == set(SECTIONS[:5])
    home = pages[HOME_PAGE][0]
    assert isinstance(home["hero_title"], str) and home["hero_title"].strip()
    for action in home["hero_actions"]:
        assert set(action) <= set(HERO_ACTION_KEYS), action
        for key in ("label", "href"):
            assert isinstance(action[key], str) and action[key].strip(), action
        if "primary" in action:
            assert type(action["primary"]) is bool, action
        assert action["href"].startswith("https://") or action["href"].endswith("/")


def test_links_are_relative_markdown_links_or_the_docs_url() -> None:
    """Pages link with relative `.md` paths, one image, and the one docs URL (2.10).

    Dies on: linking `why.md` as `/why/`, adding an absolute link other than the
    docs URL, pointing a `.md` link at a page that does not exist, or writing a
    reference-style link definition, an HTML anchor or an HTML image.
    """
    seen: list[str] = []
    for path in _pages():
        text = _without_annotation(_text(path))
        assert not re.search(r"^ {0,3}\[[^\]]+\]:", text, flags=re.MULTILINE), path
        assert not re.search(r"<\s*(a|img)\b|href\s*=", text, flags=re.IGNORECASE), path
        for target in _LINK.findall(text):
            seen.append(target)
            if target.startswith("https://"):
                assert target == DOCS_URL, (path, target)
                continue
            file_part = target.split("#", 1)[0]
            assert not file_part.startswith("/"), (path, target)
            assert file_part.endswith((".md", ".svg")), (path, target)
            assert (SITE / path).parent.joinpath(file_part).resolve().is_file(), (
                path,
                target,
            )
    assert sorted(seen) == sorted(
        ["why.md#why-a-fixture-exists", DOCS_URL, "../images/diagram.svg"]
    )


def test_no_file_carries_the_package_version_literal() -> None:
    """The fixture never repeats the package's version (9.1).

    Dies on: writing the `pyproject.toml` version string into any fixture file.
    """
    with (ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+\S*", version)
    files = _files()
    assert files
    assert [p for p in files if version in _text(p)] == []


def test_every_file_is_a_utf8_regular_file_with_unix_newlines() -> None:
    """Every file is a UTF-8 regular file with `\\n` line ends and no BOM (9.1).

    Dies on: adding a symbolic link, a non-UTF-8 byte sequence, a carriage
    return or a byte-order mark to any file of the tree.
    """
    entries = sorted(SITE.rglob("*"))
    assert len(entries) > len(EXPECTED_FILES)
    for entry in entries:
        assert not entry.is_symlink(), entry
        assert entry.is_dir() or entry.is_file(), entry
        if entry.is_file():
            data = entry.read_bytes()
            text = data.decode("utf-8")
            assert "\r" not in text, entry
            assert not text.startswith("\ufeff"), entry


def _ignored(paths: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        cwd=ROOT,
        input="\n".join(paths) + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    return result.stdout.splitlines()


def test_git_ignores_no_fixture_file() -> None:
    """Every fixture file is one git would commit (9.1).

    Dies on: renaming `.editor-state` to `.DS_Store`, or naming any fixture file
    or directory after an ignored pattern such as `data/` or `*.fit`.
    """
    relative = SITE.relative_to(ROOT).as_posix()
    paths = [f"{relative}/{p}" for p in _files()]
    assert len(paths) == len(EXPECTED_FILES)
    probe = f"{relative}/.DS_Store"
    assert _ignored([probe]) == [probe]
    assert _ignored(paths) == []
