"""A real Zensical build of the fixture site, and each way a build must fail.

Covers 1.4, 1.8, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2,
5.3, 6.1, 6.2, 6.6, 9.1 and 9.2. Every test needs the generator
(``requires_zensical``): it skips when the docs group is not installed (after a
plain ``uv sync``, for example) and fails under ``FITDOCS_REQUIRE_SITE_TOOLING=1``.
The fixture is built once per module, through ``pipeline.build`` with the real
generator, into a directory outside the repository. Each failure class builds
its own one-edit copy of the fixture in ``tmp_path``.

The HTML is read with ``html.parser``. Expected values that come from the
fixture's design (the nav order, the page URLs, the hero text) are written out
here as literals; only the llms texts and the template-derived repo URL are
recomputed, the llms texts through ``outline``.
"""

from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import pytest
import yaml
from scripts.sitebuild.content import load_content
from scripts.sitebuild.outline import render_llms, render_llms_full
from scripts.sitebuild.pipeline import BuildOutcome, build

from tests.sitebuild.conftest import copy_fixture_tree

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "site"
TEMPLATE = REPO_ROOT / "website" / "mkdocs.template.yml"

# (content path, page URL path, title) in the order the nav must show them.
PAGES = (
    ("index.md", "", "Fixture home"),
    ("why.md", "why/", "Why a fixture"),
    ("get-started/install.md", "get-started/install/", "Install"),
    ("get-started/first-run.md", "get-started/first-run/", "First run"),
    ("guides/nested/deep.md", "guides/nested/deep/", "Deep guide"),
    ("llms/prompts.md", "llms/prompts/", "Prompts"),
)
NAV = (
    ("Home", ("Fixture home",)),
    ("Why", ("Why a fixture",)),
    ("Get started", ("Install", "First run")),
    ("Guides", ("Deep guide",)),
    ("Working with LLMs", ("Prompts",)),
)

ANNOTATION_SENTINELS = ("ANNOTSENTINELAMBER", "a home-page note")
EXCLUDED_SENTINELS = (
    "DRAFTSENTINELCOBALT",  # reference/cli.md, drafted
    "PRIVATESENTINELONYX",  # _private/secret.md
    "NOTESSENTINELFERN",  # _notes.md
    "DOTFILESENTINELWILLOW",  # .editor-state
)
DRAFT_TITLE = "Command reference"
TEXT_SUFFIXES = {".html", ".json", ".txt", ".xml"}


@dataclass
class Built:
    outcome: BuildOutcome
    root: Path

    @property
    def html(self) -> Path:
        return self.root / "html"


@pytest.fixture(scope="module")
def _cache() -> dict[str, Built]:
    return {}


@pytest.fixture
def built(
    requires_zensical: None,
    _cache: dict[str, Built],
    tmp_path_factory: pytest.TempPathFactory,
) -> Built:
    """The fixture site built once per module; a skip or failure precedes any build."""
    if "site" not in _cache:
        root = tmp_path_factory.mktemp("smoke") / "site"
        outcome = build(FIXTURE, root, repo_root=REPO_ROOT)
        _cache["site"] = Built(outcome, root)
    result = _cache["site"]
    assert result.outcome.ok, [p.render() for p in result.outcome.problems]
    return result


# --- HTML parsing -----------------------------------------------------------


def _classes(attrs: dict[str, str | None]) -> set[str]:
    return set((attrs.get("class") or "").split())


@dataclass
class Parsed:
    config: dict[str, object] = field(default_factory=dict)
    edit_hrefs: list[str] = field(default_factory=list)
    stylesheets: list[str] = field(default_factory=list)
    nav: list[tuple[str, str, str]] = field(default_factory=list)  # kind, text, href
    hero_titles: list[str] = field(default_factory=list)
    hero_actions: list[tuple[str, str, set[str]]] = field(default_factory=list)
    chart_srcs: list[str] = field(default_factory=list)
    class_names: set[str] = field(default_factory=set)


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out = Parsed()
        self._config: list[str] = []
        self._in_config = False
        self._nav_depth = 0
        self._capture: tuple[str, str, str] | None = None  # end tag, kind, href
        self._text: list[str] = []
        self._hero_title = False
        self._in_chart = False
        self._capture_classes: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        classes = _classes(a)
        self.out.class_names |= classes
        if tag == "script" and a.get("id") == "__config":
            self._in_config = True
        if tag == "a" and a.get("rel") == "edit":
            self.out.edit_hrefs.append(a.get("href") or "")
        if tag == "link" and a.get("rel") == "stylesheet":
            self.out.stylesheets.append(a.get("href") or "")
        if tag == "nav":
            if self._nav_depth:
                self._nav_depth += 1
            elif "md-nav--primary" in classes:
                self._nav_depth = 1
        if (
            self._nav_depth
            and "md-nav__link" in classes
            and (
                (tag == "label" and (a.get("for") or "").startswith("__nav_"))
                or (tag == "a" and not (a.get("href") or "").startswith("#"))
            )
        ):
            kind = "section" if tag == "label" else "page"
            self._capture = (tag, kind, a.get("href") or "")
            self._text = []
        if tag == "h1" and "fd-hero__title" in classes:
            self._hero_title = True
            self._text = []
        if tag == "a" and "md-button" in classes:
            self._capture = ("a", "action", a.get("href") or "")
            self._capture_classes = classes
            self._text = []
        if tag == "div" and "fd-hero__chart" in classes:
            self._in_chart = True
        if tag == "img" and self._in_chart:
            self.out.chart_srcs.append(a.get("src") or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_config = False
        if tag == "nav" and self._nav_depth:
            self._nav_depth -= 1
        if tag == "div":
            self._in_chart = False
        if self._hero_title and tag == "h1":
            self.out.hero_titles.append(" ".join("".join(self._text).split()))
            self._hero_title = False
        if self._capture and tag == self._capture[0]:
            _end, kind, href = self._capture
            text = " ".join("".join(self._text).split())
            if kind == "action":
                self.out.hero_actions.append((text, href, self._capture_classes))
            else:
                self.out.nav.append((kind, text, href))
            self._capture = None

    def handle_data(self, data: str) -> None:
        if self._in_config:
            self._config.append(data)
        self._text.append(data)

    def close(self) -> None:
        super().close()
        if self._config:
            loaded = json.loads("".join(self._config))
            assert isinstance(loaded, dict)
            self.out.config = loaded


def parse_html(path: Path) -> Parsed:
    collector = _Collector()
    collector.feed(path.read_text(encoding="utf-8"))
    collector.close()
    return collector.out


def page_html(built: Built, location: str) -> Path:
    return built.html / location / "index.html"


def html_files(built: Built) -> list[Path]:
    files = sorted(built.html.rglob("*.html"))
    assert len(files) == 7, files  # six pages and 404.html: the walk is not vacuous
    return files


def text_files(built: Built) -> list[Path]:
    files = sorted(
        p for p in built.html.rglob("*") if p.is_file() and p.suffix in TEXT_SUFFIXES
    )
    assert len(files) >= 10, files
    return files


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def template() -> dict[str, str]:
    loaded = yaml.safe_load(read(TEMPLATE))
    return {k: str(loaded[k]) for k in ("site_name", "site_description", "site_url")}


# --- the successful build ----------------------------------------------------


def test_fixture_build_succeeds_with_six_pages(built: Built) -> None:
    """The fixture builds cleanly through the real generator (6.6, 9.2).

    Dies on: ``generator.run_build`` reporting ``ok = returncode != 0``, or
    ``pipeline.build`` counting ``len(content.assets)`` as the page count.
    """
    assert built.outcome.problems == ()
    assert built.outcome.page_count == 6
    assert built.html.is_dir()
    loaded, problems = load_content(FIXTURE)
    assert problems == ()
    assert loaded is not None
    assert sorted(p.path for p in loaded.pages) == sorted(p[0] for p in PAGES)


def test_every_page_is_written_as_a_directory_index_and_searchable(
    built: Built,
) -> None:
    """Each page is ``<path>/index.html`` and a level-1 search entry (4.1, 4.6).

    Dies on: the template's ``use_directory_urls: true`` turned to ``false``
    (pages become ``<name>.html``); a second mutation, ``content.load_content``
    keeping drafted pages, adds a search entry the equality refuses.
    """
    for _md, location, title in PAGES:
        assert page_html(built, location).is_file(), location
        assert title in read(page_html(built, location))
    index = json.loads(read(built.html / "search.json"))
    page_entries = {
        item["location"]: item["title"]
        for item in index["items"]
        if "#" not in item["location"]
    }
    assert page_entries == {location: title for _md, location, title in PAGES}


def test_nav_lists_sections_and_pages_in_configured_order(built: Built) -> None:
    """The primary nav shows sections in canonical order, pages by ``order`` (3.1, 3.2).

    ``get-started/install.md`` has ``order: 1`` and sorts after ``first-run.md``
    alphabetically, so alphabetical path order cannot produce this nav.

    Dies on: ``outline.ordered_pages`` sorting pages by ``p.path`` alone.
    """
    expected_titles: list[tuple[str, str]] = []
    for section, titles in NAV:
        expected_titles.append(("section", section))
        expected_titles += [("page", t) for t in titles]
    for _md, location, _title in PAGES:
        nav = parse_html(page_html(built, location)).nav
        assert [(k, t) for k, t, _h in nav] == expected_titles, location
        resolved = [
            urljoin(f"http://x/{location}", href).removeprefix("http://x/")
            for kind, _t, href in nav
            if kind == "page"
        ]
        assert resolved == [p[1] for p in PAGES], location


def test_llms_files_sit_at_the_html_root_and_equal_the_outline_renders(
    built: Built,
) -> None:
    """Both llms files equal ``outline``'s renders of the loaded fixture (5.1, 5.2).

    The expected texts are recomputed here from the loaded content and the
    template's own fields.

    Dies on: ``pipeline.build`` passing ``llms_full=""`` to ``plan_tree``, or
    ``stage.plan_tree`` not staging the llms files (Zensical then never copies
    them).
    """
    loaded, problems = load_content(FIXTURE)
    assert loaded is not None and problems == ()
    fields = template()
    expected = render_llms(
        loaded,
        site_name=fields["site_name"],
        summary=fields["site_description"],
        site_url=fields["site_url"],
    )
    expected_full = render_llms_full(loaded, site_url=fields["site_url"])
    assert "Fixture home" in expected and "Deep guide" in expected_full
    assert read(built.html / "llms.txt") == expected
    assert read(built.html / "llms-full.txt") == expected_full
    assert (
        "- [Install](https://fitdocs.ai/get-started/install/): "
        "Install the fixture tool." in expected.splitlines()
    )


def test_llms_files_omit_the_draft_and_the_underscore_pages(built: Built) -> None:
    """Neither llms file holds the drafted title or an excluded page's sentinel (5.3).

    Whole files are searched. The fixture's draft, ``_notes.md`` and
    ``_private/secret.md`` each carry one of the searched tokens.

    Dies on: ``content.load_content`` keeping drafted pages (the
    ``if parsed.drafted: continue`` branch of ``load_content`` is gone).
    """
    for name in ("llms.txt", "llms-full.txt"):
        text = read(built.html / name)
        assert len(text) > 200, name
        for token in (DRAFT_TITLE, *EXCLUDED_SENTINELS):
            assert token not in text, (name, token)


def test_config_script_carries_the_code_copy_and_edit_features(built: Built) -> None:
    """Every page's ``__config`` lists the code-copy and edit features (4.3, 4.4).

    Dies on: ``content.action.edit`` removed from the template's
    ``theme.features`` (a second run with ``content.code.copy`` removed reds
    the same test).
    """
    for _md, location, _title in PAGES:
        features = parse_html(page_html(built, location)).config.get("features")
        assert isinstance(features, list), location
        assert "content.code.copy" in features, location
        assert "content.action.edit" in features, location


def test_every_page_links_its_source_for_editing(built: Built) -> None:
    """Each page, the home page included, has one edit link to its content path (4.4).

    Dies on: the template's ``edit_uri`` changed from ``edit/main/website/content/``
    to ``edit/main/website/docs/``.
    """
    repo_url = yaml.safe_load(read(TEMPLATE))["repo_url"]
    for md, location, _title in PAGES:
        hrefs = parse_html(page_html(built, location)).edit_hrefs
        assert hrefs == [f"{repo_url}/edit/main/website/content/{md}"], location


def test_the_home_page_shows_the_hero_with_two_actions_and_the_chart(
    built: Built,
) -> None:
    """The home page shows the hero title, two actions and the chart (3.3, 3.4, 3.5).

    The fixture's home page has no ``hero_tagline``, so no tagline element may
    appear.

    Dies on: ``website/overrides/home.html`` losing the ``{% if
    page.meta.hero_tagline %}`` guard (an empty tagline element renders), the
    primary-class condition, or the chart ``img``.
    """
    assert "hero_tagline" not in read(FIXTURE / "index.md")
    parsed = parse_html(page_html(built, ""))
    assert parsed.hero_titles == ["Fixture hero title"]
    assert [(t, h) for t, h, _c in parsed.hero_actions] == [
        ("Read the story", "https://example.org/story"),
        ("Install", "./get-started/install/"),
    ]
    assert [("md-button--primary" in c) for _t, _h, c in parsed.hero_actions] == [
        True,
        False,
    ]
    assert parsed.chart_srcs == ["./_brand/hero-chart.svg"]
    assert (built.html / "_brand" / "hero-chart.svg").is_file()
    assert not {c for c in parsed.class_names if "tagline" in c}
    for _md, location, _title in PAGES[1:]:
        other = parse_html(page_html(built, location))
        assert not other.hero_titles and not other.hero_actions, location
        assert not other.chart_srcs, location


def test_brand_css_is_linked_from_every_page(built: Built) -> None:
    """Every page links a stylesheet that resolves to ``_brand/brand.css`` (4.5).

    Dies on: the template's ``extra_css`` list emptied.
    """
    for _md, location, _title in PAGES:
        sheets = parse_html(page_html(built, location)).stylesheets
        targets = [posixpath.normpath(posixpath.join(location, s)) for s in sheets]
        assert "_brand/brand.css" in targets, (location, sheets)
    assert (built.html / "_brand" / "brand.css").is_file()


def test_annotation_blocks_never_reach_the_output(built: Built) -> None:
    """No output file carries an annotation block's text (1.8).

    Both annotated pages are searched, in every html, json, txt and xml file.

    Dies on: ``content.strip_annotation`` returning its text unchanged.
    """
    why = read(FIXTURE / "why.md")
    assert "ANNOTSENTINELAMBER" in why  # the sentinel is really in the source
    assert "a home-page note" in read(FIXTURE / "index.md")
    for path in text_files(built):
        text = read(path)
        for token in ANNOTATION_SENTINELS:
            assert token not in text, (path.name, token)
    assert (built.html / "search.json").is_file()


def test_draft_underscore_and_dot_content_is_absent_from_the_output(
    built: Built,
) -> None:
    """The draft, the ``_`` pages and the dotfile are not staged or built (1.4, 2.4).

    The staged tree is checked beside ``html/``, because Zensical itself skips
    dot-files when it copies assets.

    Dies on: ``content.load_content`` keeping drafted pages (the drafted
    ``reference/cli.md`` is then built, listed in the search index and its
    sentinel written); ``content.discover`` no longer excluding ``.``-prefixed
    names (the dotfile is staged).
    """
    staged = [
        p.relative_to(built.root / "staged").as_posix()
        for p in (built.root / "staged").rglob("*")
    ]
    assert "get-started/install.md" in staged  # the walk is looking at the tree
    for name in staged:
        parts = name.split("/")
        assert not any(p.startswith(".") for p in parts), name
        assert not any(p.startswith("_") and p != "_brand" for p in parts), name
        assert "reference" not in parts and "cli.md" not in parts, name
    names = [p.relative_to(built.html).as_posix() for p in built.html.rglob("*")]
    assert "index.html" in names
    for name in names:
        parts = name.split("/")
        assert not any(p.startswith(".") for p in parts), name
        assert not any(p.startswith("_") and p != "_brand" for p in parts), name
        assert "reference" not in parts, name
        assert "secret" not in parts and "cli" not in parts, name
        assert not name.startswith("_notes"), name
    for path in text_files(built):
        text = read(path)
        for token in (DRAFT_TITLE, *EXCLUDED_SENTINELS):
            assert token not in text, (path.name, token)
    assert (built.html / "get-started" / "install" / "index.html").is_file()
    assert html_files(built)


# --- each failure class -------------------------------------------------------

INSTALL = "get-started/install.md"


@dataclass(frozen=True)
class Failure:
    appended: str
    message: str


FAILURES = {
    "md-link": Failure("See [nothing](missing-page.md).", "page does not exist"),
    "cross-page-anchor": Failure(
        "See [why](../why.md#no-such-anchor).", "anchor does not exist"
    ),
    "same-page-anchor": Failure(
        "See [here](#no-such-anchor).", "anchor does not exist"
    ),
    "drafted-page": Failure("See [cli](../reference/cli.md).", "page does not exist"),
}


@pytest.mark.parametrize("case", sorted(FAILURES))
def test_a_broken_link_fails_the_build_naming_the_file_and_leaves_no_html(
    case: str, requires_zensical: None, tmp_path: Path
) -> None:
    """One edit to a fixture copy fails the build, naming page and line (6.1, 6.2, 6.6).

    The four cases are a broken ``.md`` link, a broken cross-page anchor, a
    broken same-page anchor and a link to the drafted page. Each is built in its
    own copy; the problem names ``get-started/install.md`` with the line of the
    appended link, and no ``html/`` remains.

    Dies on: the template's ``strict: true`` turned to ``false`` (the generator
    then exits 0 and the build passes); for ``drafted-page`` also
    ``content.load_content`` keeping drafted pages (the link then resolves).
    """
    failure = FAILURES[case]
    content = copy_fixture_tree(FIXTURE, tmp_path, "content")
    page = content / INSTALL
    original = page.read_text(encoding="utf-8")
    page.write_text(original + "\n" + failure.appended + "\n", encoding="utf-8")
    line = len(original.splitlines()) + 2
    root = tmp_path / "root"
    outcome = build(content, root, repo_root=REPO_ROOT)
    assert not outcome.ok
    rendered = [p.render() for p in outcome.problems]
    assert len(rendered) == 1, rendered
    assert rendered[0].startswith(f"{INSTALL}: {line}:"), rendered
    assert failure.message in rendered[0], rendered
    assert not (root / "html").exists()
    assert (root / "staged").is_dir()
