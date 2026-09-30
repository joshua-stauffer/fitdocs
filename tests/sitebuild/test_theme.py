"""The theme: home override, brand stylesheet, logo (3.3, 3.4, 3.5, 4.4, 4.5).

Everything here reads the checked-in files under ``website/``. The render tests
run ``home.html`` through Jinja (a dependency of the generator, so they sit
behind ``requires_zensical``) with the generator's own ``actions.html`` partial
as the parent block's content.
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from scripts.sitebuild.model import HERO_KEYS

REPO_ROOT = Path(__file__).resolve().parents[2]
WEBSITE = REPO_ROOT / "website"
HOME = WEBSITE / "overrides" / "home.html"
BRAND_CSS = WEBSITE / "assets" / "brand.css"
LOGO = WEBSITE / "assets" / "logo.svg"

EDIT_URL = "https://github.com/x/edit/main/website/content/index.md"
BODY = "BODYSENTINEL"

# The values brand.css owns (4.5): its custom properties and the palette colors.
BRAND_TOKENS = (
    "--md-primary-fg-color",
    "--md-primary-bg-color",
    "--md-accent-fg-color",
    "--md-typeset-a-color",
    "--md-text-font",
    "--md-code-font",
    "#1f2933",
    "#b8324b",
    "#f07d8e",
)


# --- Jinja helpers ----------------------------------------------------------


def _jinja() -> Any:
    return importlib.import_module("jinja2")


def _generator_templates() -> Path:
    spec = importlib.util.find_spec("zensical")
    assert spec is not None and spec.origin is not None
    templates = Path(spec.origin).parent / "templates"
    assert (templates / "partials" / "actions.html").is_file()
    return templates


def _render(
    meta: dict[str, Any],
    *,
    overrides: Path | None = None,
    features: tuple[str, ...] = ("content.action.edit",),
) -> str:
    """Render ``home.html`` over a stand-in ``main.html`` whose content block is the
    generator's real edit-action partial followed by the page body."""
    jinja2 = _jinja()
    parent = (
        '{% block content %}{% include "partials/actions.html" %}'
        + BODY
        + "{% endblock %}"
    )
    env = jinja2.Environment(
        loader=jinja2.ChoiceLoader(
            [
                jinja2.FileSystemLoader(str(overrides or HOME.parent)),
                jinja2.DictLoader({"main.html": parent}),
                jinja2.FileSystemLoader(str(_generator_templates())),
            ]
        ),
        autoescape=True,
    )
    env.filters["url"] = lambda value: f"URL[{value}]"
    page = SimpleNamespace(meta=meta, edit_url=EDIT_URL)
    rendered: str = env.get_template("home.html").render(
        page=page,
        features=list(features),
        lang=SimpleNamespace(t=lambda key: key),
        config=SimpleNamespace(
            theme=SimpleNamespace(icon=SimpleNamespace(edit=None, view=None))
        ),
    )
    return rendered


ACTIONS = [
    {"label": "Primary label", "href": "guide-one/", "primary": True},
    {"label": "Plain label", "href": "https://example.org/two"},
    {"label": "Third label", "href": "guide-three/", "primary": False},
]


# --- hero keys sit inside conditionals (3.3, 3.4) ---------------------------


def _unguarded_hero_uses(source: str) -> list[str]:
    """Hero-key and action-variable uses that no enclosing ``if`` tests.

    A use is guarded when an enclosing ``if`` (statement or inline) tests the same
    hero key in its condition and the use sits in that ``if``'s body, not its
    ``else``. The ``action`` loop variable counts as a use of ``hero_actions``.
    """
    nodes = _jinja().nodes
    tree = _jinja().Environment().parse(source)
    found: list[str] = []

    def keys_in(root: Any) -> set[str]:
        found_keys: set[str] = set()
        for n in [root, *root.find_all((nodes.Getattr, nodes.Getitem))]:
            if isinstance(n, nodes.Getattr) and n.attr in HERO_KEYS:
                found_keys.add(n.attr)
            elif (
                isinstance(n, nodes.Getitem)
                and isinstance(n.arg, nodes.Const)
                and n.arg.value in HERO_KEYS
            ):
                found_keys.add(n.arg.value)
        return found_keys

    def visit(node: Any, guards: frozenset[str], in_test: bool) -> None:
        if isinstance(node, nodes.If | nodes.CondExpr):
            visit(node.test, guards, True)
            body = node.body if isinstance(node, nodes.If) else [node.expr1]
            other = node.else_ if isinstance(node, nodes.If) else [node.expr2]
            for child in body:
                visit(child, guards | keys_in(node.test), in_test)
            for child in other or []:
                visit(child, guards, in_test)
            for child in getattr(node, "elif_", []):
                visit(child, guards, in_test)
            return
        if not in_test:
            if isinstance(node, nodes.Getattr) and node.attr in HERO_KEYS:
                if node.attr not in guards:
                    found.append(node.attr)
            elif isinstance(node, nodes.Getitem) and isinstance(node.arg, nodes.Const):
                if node.arg.value in HERO_KEYS and node.arg.value not in guards:
                    found.append(str(node.arg.value))
            elif (
                isinstance(node, nodes.Name)
                and node.name == "action"
                and node.ctx == "load"
                and "hero_actions" not in guards
            ):
                found.append("action")
        for child in node.iter_child_nodes():
            visit(child, guards, in_test)

    visit(tree, frozenset(), False)
    return found


def _mentioned_keys(source: str) -> set[str]:
    nodes = _jinja().nodes
    tree = _jinja().Environment().parse(source)
    return {n.attr for n in tree.find_all(nodes.Getattr) if n.attr in HERO_KEYS}


def test_every_hero_key_in_home_html_sits_inside_its_own_if(
    requires_zensical: None,
) -> None:
    """No hero key, and no action entry, is used outside an `if` on that key (3.3, 3.4).

    Dies on: `{% if page.meta.hero_tagline %}` -> `{% if true %}` in
    website/overrides/home.html.
    """
    source = HOME.read_text(encoding="utf-8")
    assert _mentioned_keys(source) == set(HERO_KEYS)
    assert _unguarded_hero_uses(source) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("{{ page.meta.hero_title }}", ["hero_title"]),
        (
            "{% if page.meta.hero_title %}{{ page.meta.hero_tagline }}{% endif %}",
            ["hero_tagline"],
        ),
        (
            "{% if page.meta.hero_title %}{% else %}"
            "{{ page.meta.hero_title }}{% endif %}",
            ["hero_title"],
        ),
        (
            "{% for action in page.meta.hero_actions %}{{ action.label }}{% endfor %}",
            ["hero_actions", "action"],
        ),
        ("{{ page.meta['hero_tagline'] }}", ["hero_tagline"]),
        (
            "{{ page.meta.hero_title if page.meta.hero_tagline else '' }}",
            ["hero_title"],
        ),
    ],
)
def test_the_guard_scan_flags_each_unguarded_shape(
    requires_zensical: None, source: str, expected: list[str]
) -> None:
    """The scan reports each shape it exists to catch.

    Dies on: `node.attr not in guards` -> `False` in `_unguarded_hero_uses`
    (this test file's own scan), which stops it reporting attribute uses
    (hero keys read with dot syntax).
    """
    assert _unguarded_hero_uses(source) == expected


def test_a_guarded_use_is_not_flagged(requires_zensical: None) -> None:
    """The scan accepts a use inside an `if` on the same key.

    Dies on: `guards | keys_in(node.test)` -> `guards` in `_unguarded_hero_uses`
    (this test file's own scan), which flags every guarded use.
    """
    source = (
        "{% if page.meta.hero_actions %}"
        "{% for action in page.meta.hero_actions %}{{ action.label }}{% endfor %}"
        "{% endif %}"
    )
    assert _unguarded_hero_uses(source) == []


# --- rendered behavior (3.3, 3.4, 3.5, 4.4) ---------------------------------


def _hero_html(html: str) -> str:
    match = re.search(r'<section[^>]*class="fd-hero"[^>]*>.*?</section>', html, re.S)
    assert match is not None
    return match.group(0)


def _visible(hero: str) -> str:
    """The hero's text with tags stripped and whitespace collapsed."""
    return " ".join(re.sub(r"<[^>]*>", " ", hero).split())


def test_present_hero_keys_render_with_button_classes_and_url_filtered_links(
    requires_zensical: None,
) -> None:
    """Title, tagline and actions render; only `primary` gets its class (3.3).

    Dies on: `{% if action.primary %}` -> `{% if not action.primary %}` in home.html,
    or `{{ action.href | url }}` -> `{{ action.href }}`.
    """
    html = _render(
        {"hero_title": "TITLE-X", "hero_tagline": "TAGLINE-Y", "hero_actions": ACTIONS}
    )
    hero = _hero_html(html)
    assert re.search(r"<h1[^>]*>TITLE-X</h1>", hero)
    assert re.search(r"<p[^>]*>TAGLINE-Y</p>", hero)
    buttons = re.findall(r'<a class="([^"]*)" href="([^"]*)">([^<]*)</a>', hero)
    assert buttons == [
        ("md-button md-button--primary", "URL[guide-one/]", "Primary label"),
        ("md-button", "URL[https://example.org/two]", "Plain label"),
        ("md-button", "URL[guide-three/]", "Third label"),
    ]


@pytest.mark.parametrize(
    "present",
    [
        {"hero_title": "ONLY-TITLE"},
        {"hero_tagline": "ONLY-TAGLINE"},
        {"hero_actions": ACTIONS},
    ],
)
def test_an_omitted_hero_key_omits_its_element_and_nothing_replaces_it(
    requires_zensical: None, present: dict[str, Any]
) -> None:
    """With one key set, only its element appears; the others leave no trace (3.4).

    Dies on: `{% if page.meta.hero_title %}` -> `{% if true %}` in home.html (or
    the same for the tagline or the actions guard), or adding
    `{% else %}<p>default tagline</p>` / `{% else %}<h2>fitdocs</h2>` after the
    tagline's or title's block.
    """
    hero = _hero_html(_render(present))
    expected = {
        "hero_title": "fd-hero__title" in hero,
        "hero_tagline": "fd-hero__tagline" in hero,
        "hero_actions": "fd-hero__actions" in hero,
    }
    assert expected == {key: key in present for key in HERO_KEYS}
    # `md-button` also appears in the actions only.
    assert ("md-button" in hero) == ("hero_actions" in present)
    assert hero.count("<h1") == ("hero_title" in present)
    values = [present.get("hero_title"), present.get("hero_tagline")]
    values += [a["label"] for a in present.get("hero_actions", [])]
    assert _visible(hero) == " ".join(v for v in values if v)


def test_no_hero_keys_leaves_only_the_chart(requires_zensical: None) -> None:
    """A home page with no hero keys renders no title, tagline, or action element (3.4).

    Dies on: `{% if page.meta.hero_title %}` -> `{% if true %}` in home.html (or
    the same for the tagline or the actions guard), or `{% else %}<p>default
    tagline</p>` / `{% else %}<h2>fitdocs</h2>` after the tagline's or title's block.
    """
    hero = _hero_html(_render({}))
    for cls in ("fd-hero__title", "fd-hero__tagline", "fd-hero__actions", "md-button"):
        assert cls not in hero
    assert "fd-hero__chart" in hero
    assert _visible(hero) == ""


def test_the_hero_shows_the_demo_chart_with_demo_alt_text(
    requires_zensical: None,
) -> None:
    """The chart is `_brand/hero-chart.svg` via `url`; the alt text says demo (3.5).

    Dies on: `_brand/hero-chart.svg` -> `_brand/hero.svg`, or `Demo chart:` ->
    `Chart:` in the alt text in home.html.
    """
    hero = _hero_html(_render({}))
    match = re.search(r'<img src="([^"]*)" alt="([^"]*)"', hero)
    assert match is not None
    assert match.group(1) == "URL[_brand/hero-chart.svg]"
    assert "demo" in match.group(2).lower()
    assert (WEBSITE / "assets" / "hero-chart.svg").is_file()


def test_home_keeps_the_edit_action_and_the_page_body(requires_zensical: None) -> None:
    """The page's edit link survives the override, next to the body (4.4).

    Dies on: deleting `{{ super() }}` from home.html.
    """
    with_edit = _render({})
    assert f'href="{EDIT_URL}"' in with_edit
    assert 'rel="edit"' in with_edit
    assert BODY in with_edit
    # Falsity in the starting state: no link when the feature is off.
    without_edit = _render({}, features=())
    assert 'rel="edit"' not in without_edit
    assert BODY in without_edit


def test_the_render_helper_sees_a_home_that_drops_the_edit_action(
    requires_zensical: None, tmp_path: Path
) -> None:
    """A home without `super()` loses the edit link, and the body (4.4).

    Dies on: `overrides or HOME.parent` -> `HOME.parent` in `_render` (this test
    file's own helper), which ignores the edited copy and finds the link again.
    """
    text = HOME.read_text(encoding="utf-8")
    assert text.count("{{ super() }}") == 1
    (tmp_path / "home.html").write_text(
        text.replace("{{ super() }}", ""), encoding="utf-8"
    )
    html = _render({}, overrides=tmp_path)
    assert 'rel="edit"' not in html
    assert BODY not in html


def test_home_extends_the_generators_main_template(requires_zensical: None) -> None:
    """`home.html` extends `main.html`, overriding only the content block (4.4).

    Dies on: `{% extends "main.html" %}` -> `{% extends "base.html" %}`, or adding a
    second block such as `{% block header %}` to home.html.
    """
    nodes = _jinja().nodes
    tree = _jinja().Environment().parse(HOME.read_text(encoding="utf-8"))
    extends = list(tree.find_all(nodes.Extends))
    assert [e.template.value for e in extends] == ["main.html"]
    assert [b.name for b in tree.find_all(nodes.Block)] == ["content"]


# --- brand.css (4.5) --------------------------------------------------------


def _css_props(css: str, selector: str) -> dict[str, str]:
    """Merged declarations of each top-level rule listing ``selector``."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    merged: dict[str, str] = {}
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if selector not in [s.strip() for s in selectors.split(",")]:
            continue
        for decl in body.split(";"):
            name, sep, value = decl.partition(":")
            if sep:
                merged[name.strip()] = " ".join(value.split())
    return merged


SCHEMES = ('[data-md-color-scheme="default"]', '[data-md-color-scheme="slate"]')


def _brand() -> str:
    return BRAND_CSS.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("scheme", "accent"),
    [(SCHEMES[0], "#b8324b"), (SCHEMES[1], "#f07d8e")],
)
def test_brand_css_defines_the_palette_for_each_scheme(
    scheme: str, accent: str
) -> None:
    """Header colors are shared; accent and link color differ per scheme (4.5).

    Dies on: `--md-accent-fg-color: #b8324b` -> `#f07d8e` in the default block of
    brand.css (or the slate accent -> `#b8324b`), or deleting `--md-typeset-a-color`.
    """
    props = _css_props(_brand(), scheme)
    assert props["--md-primary-fg-color"] == "#1f2933"
    assert props["--md-primary-bg-color"] == "#ffffff"
    assert props["--md-accent-fg-color"] == accent
    assert props["--md-typeset-a-color"] == accent


@pytest.mark.parametrize("scheme", SCHEMES)
def test_brand_css_defines_system_font_stacks_for_each_scheme(scheme: str) -> None:
    """Text and code fonts are system stacks in both schemes, naming no web font (4.5).

    Dies on: `--md-text-font: system-ui, ...` -> `Inter, sans-serif` in brand.css,
    or deleting `--md-code-font` from the shared block.
    """
    props = _css_props(_brand(), scheme)
    text_font = props["--md-text-font"]
    code_font = props["--md-code-font"]
    assert text_font.startswith("system-ui,")
    assert code_font.startswith("ui-monospace,")
    for family in ("Inter", "JetBrains", "Roboto Mono", "http"):
        assert family not in text_font + code_font


def _luminance(color: str) -> float:
    assert re.fullmatch(r"#[0-9a-f]{6}", color)
    red, green, blue = (int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


@pytest.mark.parametrize("scheme", SCHEMES)
def test_the_chart_sits_on_a_light_card_in_both_schemes(scheme: str) -> None:
    """The card behind the chart takes a light color from each scheme (3.5, 4.5).

    Dies on: `--fd-hero-card-bg: #f5f7fa` -> `#1e2129` in the slate block of
    brand.css, or `background-color: var(--fd-hero-card-bg)` -> `transparent` in
    the `.fd-hero__chart` rule.
    """
    card = _css_props(_brand(), scheme)["--fd-hero-card-bg"]
    assert _luminance(card) > 0.9
    assert (
        _css_props(_brand(), ".fd-hero__chart")["background-color"]
        == "var(--fd-hero-card-bg)"
    )


def test_brand_css_styles_every_hero_class_home_html_uses() -> None:
    """Each `fd-hero` class in home.html has a rule in brand.css (3.3).

    Dies on: renaming `fd-hero__tagline` to `fd-hero__lede` in home.html.
    """
    used = set(re.findall(r"fd-hero[\w-]*", HOME.read_text(encoding="utf-8")))
    assert used >= {"fd-hero", "fd-hero__title", "fd-hero__tagline", "fd-hero__actions"}
    assert "fd-hero__chart" in used
    for cls in used:
        assert _css_props(_brand(), f".{cls}"), cls


# --- one place for brand values (4.5) ---------------------------------------


LEAK_RULES = (
    ("custom-property", re.compile(r"--(md|fd)-[\w-]+\s*:")),
    (
        "color-function",
        re.compile(r"\b(rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(", re.I),
    ),
    ("font-family", re.compile(r"font-family", re.I)),
)


SKIPPED_TOP_DIRS = ("build", "content")


def _site_files(root: Path) -> Iterable[Path]:
    """Every regular file under ``root``, except ``build/`` (generated output) and
    ``content/`` (the maintainer's pages, not the theme)."""
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.relative_to(root).parts[0] not in SKIPPED_TOP_DIRS:
            yield path


def _brand_leaks(root: Path) -> list[tuple[str, str]]:
    """(file, rule or token) per brand value outside assets/brand.css.

    Hex tokens are matched ignoring case.
    """
    leaks: list[tuple[str, str]] = []
    for path in _site_files(root):
        if path == root / "assets" / "brand.css":
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        leaks += [(path.name, t) for t in BRAND_TOKENS if t in text.lower()]
        leaks += [(path.name, n) for n, rule in LEAK_RULES if rule.search(text)]
    return leaks


def test_no_other_website_file_defines_a_brand_value() -> None:
    """Palette, custom-property and font values appear in brand.css alone (4.5).

    Dies on: adding `stroke="#b8324b"`, or `fill="rgb(184, 50, 75)"`, to
    website/assets/logo.svg, or a `<style>` block declaring
    `--md-default-bg-color` to website/overrides/home.html.
    """
    scanned = {p.name for p in _site_files(WEBSITE)}
    assert {
        "brand.css",
        "home.html",
        "logo.svg",
        "hero-chart.svg",
        "mkdocs.template.yml",
    } <= scanned
    # Non-vacuity: brand.css holds every token and declares custom properties.
    css = _brand()
    assert [t for t in BRAND_TOKENS if t not in css.lower()] == []
    assert LEAK_RULES[0][1].search(css)
    assert _brand_leaks(WEBSITE) == []


def _copy_website(tmp_path: Path) -> Path:
    copy = tmp_path / "website"
    shutil.copytree(WEBSITE, copy, ignore=shutil.ignore_patterns(*SKIPPED_TOP_DIRS))
    return copy


@pytest.mark.parametrize(
    ("relative", "planted", "label"),
    [
        ("overrides/home.html", "#B8324B", "#b8324b"),
        ("assets/logo.svg", "#f07d8e", "#f07d8e"),
        ("mkdocs.template.yml", "--md-text-font", "--md-text-font"),
        ("assets/hero-chart.svg", "#1F2933", "#1f2933"),
        ("assets/logo.svg", 'fill="rgb(184, 50, 75)"', "color-function"),
        ("assets/logo.svg", 'fill="hsl(0 50% 50%)"', "color-function"),
        (
            "overrides/home.html",
            "<style>:root{--md-default-bg-color:#000000}</style>",
            "custom-property",
        ),
        ("overrides/home.html", "<style>p{font-family:serif}</style>", "font-family"),
        ("assets/extra.js", "const c = '#b8324b';", "#b8324b"),
        ("overrides/brand.css", "--md-accent-fg-color: #00ff00;", "custom-property"),
    ],
)
def test_the_leak_scan_finds_a_value_planted_in_each_kind_of_file(
    tmp_path: Path, relative: str, planted: str, label: str
) -> None:
    """The scan reports a brand value planted in a copy of `website/` (4.5).

    Dies on: `if path == root / "assets" / "brand.css"` -> `if True` in
    `_brand_leaks` (this test file's own scan), or `path == ...` -> `path.name ==
    "brand.css"` there, or deleting a rule from `LEAK_RULES`.
    """
    copy = _copy_website(tmp_path)
    assert _brand_leaks(copy) == []
    target = copy / relative
    old = target.read_text(encoding="utf-8") if target.exists() else ""
    target.write_text(old + f"\n{planted}\n", encoding="utf-8")
    assert (target.name, label) in _brand_leaks(copy)


def test_the_leak_scan_skips_the_maintainers_content(tmp_path: Path) -> None:
    """A page under `website/content/` may discuss colours and fonts (4.5).

    Dies on: `SKIPPED_TOP_DIRS = ("build", "content")` -> `("build",)` in this test
    file.
    """
    copy = _copy_website(tmp_path)
    page = copy / "content" / "page.md"
    page.parent.mkdir(exist_ok=True)
    page.write_text(
        "font-family: x; color: #b8324b; --md-primary-fg-color: #000\n",
        encoding="utf-8",
    )
    assert page in set(copy.rglob("*.md"))
    assert _brand_leaks(copy) == []


def test_the_leak_scan_skips_the_generated_build_tree(tmp_path: Path) -> None:
    """A local build's own CSS under `website/build/` is not a leak (4.5).

    Dies on: `path.relative_to(root).parts[0] not in SKIPPED_TOP_DIRS` -> `True` in
    `_site_files` (this test file's own scan).
    """
    copy = _copy_website(tmp_path)
    generated = copy / "build" / "site" / "html" / "x.css"
    generated.parent.mkdir(parents=True)
    generated.write_text("--md-primary-fg-color: #000;", encoding="utf-8")
    assert generated in set(copy.rglob("*.css"))
    assert _brand_leaks(copy) == []


# --- logo.svg ---------------------------------------------------------------


def test_the_logo_is_a_utf8_vector_placeholder() -> None:
    """The logo is well-formed SVG text with no embedded raster (4.5).

    Dies on: adding `<image href="data:image/png;base64,AAAA"/>` to logo.svg.
    """
    text = LOGO.read_bytes().decode("utf-8")
    root = ET.fromstring(text)
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    tags = {el.tag.rpartition("}")[2] for el in root.iter()}
    assert tags & {"path", "polyline", "line"}
    assert tags.isdisjoint({"image", "foreignObject", "script"})
    assert "data:" not in text
