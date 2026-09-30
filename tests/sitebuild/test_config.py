"""Generator config rendering and the allowlist (6.4), in two parts.

Part 2 also pins 4.1-4.4 and 4.6 on the checked-in template.

Part 1 builds its templates in memory or under ``tmp_path``; part 2 (3.1, at the
end of the module) loads the checked-in template.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml
from scripts.sitebuild import config
from scripts.sitebuild.model import Problem

NAV: list[dict[str, list[dict[str, str]]]] = [
    {"Home": [{"Welcome": "index.md"}]},
    {"Guides": [{"Deep": "guides/deep.md"}, {"Alpha": "guides/alpha.md"}]},
]

FEATURES_29 = (
    "announce.dismiss",
    "content.action.edit",
    "content.action.view",
    "content.code.annotate",
    "content.code.copy",
    "content.code.select",
    "content.footnote.tooltips",
    "content.lazy",
    "content.tabs.link",
    "content.tooltips",
    "header.autohide",
    "navigation.expand",
    "navigation.footer",
    "navigation.indexes",
    "navigation.instant",
    "navigation.instant.prefetch",
    "navigation.instant.preview",
    "navigation.instant.progress",
    "navigation.path",
    "navigation.prune",
    "navigation.sections",
    "navigation.tabs",
    "navigation.tabs.sticky",
    "navigation.top",
    "navigation.tracking",
    "search.highlight",
    "search.share",
    "toc.follow",
    "toc.integrate",
)


def _template() -> dict[str, Any]:
    """A template that passes the allowlist: palette entries, a toggle, a plugin."""
    return {
        "site_name": "fitdocs",
        "site_url": "https://fitdocs.ai/",
        "use_directory_urls": True,
        "strict": True,
        "extra_css": ["_brand/site.css"],
        "plugins": ["search"],
        "theme": {
            "name": "classic",
            "variant": "classic",
            "font": False,
            "logo": "_brand/logo.svg",
            "favicon": "_brand/favicon.svg",
            "features": ["content.code.copy", "content.action.edit"],
            "palette": [
                {
                    "media": "(prefers-color-scheme)",
                    "toggle": {"icon": "a", "name": "auto"},
                },
                {"media": "(prefers-color-scheme: light)", "scheme": "default"},
                {"scheme": "slate", "primary": "x", "accent": "y"},
            ],
        },
    }


def _check(template: Mapping[str, Any]) -> tuple[Problem, ...]:
    return config.check_config(config.render_config(template, NAV), template)


def _wheres(problems: tuple[Problem, ...]) -> list[str]:
    return [p.where for p in problems]


# --- the constants ---------------------------------------------------------


def test_constants_match_the_design_literals() -> None:
    """The allowlist constants equal the design's lists, spelled out here.

    Dies on: adding, dropping or misspelling any name in `ALLOWED_TOP_LEVEL`,
    `ALLOWED_THEME_KEYS`, `ALLOWED_PALETTE_KEYS`, `ALLOWED_TOGGLE_KEYS`,
    `ALLOWED_SEARCH_OPTIONS` or `ALLOWED_PLUGINS`, or changing
    `BUILD_OWNED_KEYS` or `TEMPLATE_PATH`.
    """
    assert Path("website/mkdocs.template.yml") == config.TEMPLATE_PATH
    assert config.BUILD_OWNED_KEYS == (
        "docs_dir",
        "site_dir",
        "nav",
        "theme.custom_dir",
    )
    assert frozenset(
        {
            "site_name", "site_url", "site_description", "repo_url", "repo_name",
            "edit_uri", "use_directory_urls", "strict", "theme", "extra_css",
            "plugins", "docs_dir", "site_dir", "nav",
        }
    ) == config.ALLOWED_TOP_LEVEL  # fmt: skip
    assert (
        frozenset(
            {
                "name",
                "variant",
                "custom_dir",
                "font",
                "logo",
                "favicon",
                "features",
                "palette",
            }
        )
        == config.ALLOWED_THEME_KEYS
    )
    assert frozenset({"search"}) == config.ALLOWED_PLUGINS
    assert frozenset({"media", "scheme", "primary", "accent", "toggle"}) == (
        config.ALLOWED_PALETTE_KEYS
    )
    assert frozenset({"icon", "name"}) == config.ALLOWED_TOGGLE_KEYS
    assert frozenset({"enabled", "separator"}) == config.ALLOWED_SEARCH_OPTIONS


def test_feature_allowlist_is_the_29_researched_names() -> None:
    """`ALLOWED_FEATURES` is exactly the 29 names of research.md, without the inert one.

    Dies on: adding `search.suggest`, dropping or misspelling any one of the
    29 names.
    """
    assert len(FEATURES_29) == 29
    assert len(set(FEATURES_29)) == 29
    assert frozenset(FEATURES_29) == config.ALLOWED_FEATURES
    assert "search.suggest" not in config.ALLOWED_FEATURES


def test_markdown_extensions_is_not_allowed() -> None:
    """`markdown_extensions` is refused at the top level.

    Dies on: adding `markdown_extensions` to `ALLOWED_TOP_LEVEL`.
    """
    assert "markdown_extensions" not in config.ALLOWED_TOP_LEVEL
    template = _template()
    template["markdown_extensions"] = ["toc"]
    assert _wheres(_check(template)) == ["markdown_extensions"]


# --- load_template ---------------------------------------------------------


def test_load_template_reads_a_mapping(tmp_path: Path) -> None:
    """A valid template loads as its mapping, with no problems.

    Dies on: `load_template` returning `None` or the raw text, or reporting a
    problem for a valid file.
    """
    path = tmp_path / "t.yml"
    path.write_text("site_name: x\ntheme:\n  name: classic\n", encoding="utf-8")
    assert config.load_template(path) == (
        {"site_name": "x", "theme": {"name": "classic"}},
        (),
    )


def test_load_template_reports_a_parse_error_naming_the_file(tmp_path: Path) -> None:
    """A YAML syntax error is one problem that names the template and the position.

    Dies on: letting the `yaml.YAMLError` propagate, or building the problem
    without the file path or the line.
    """
    path = tmp_path / "t.yml"
    path.write_text("site_name: x\nfoo: [unclosed\n", encoding="utf-8")
    loaded, problems = config.load_template(path)
    assert loaded is None
    assert len(problems) == 1
    assert problems[0].path == str(path)
    assert problems[0].where == "3:1"
    assert "\n" not in problems[0].render()


@pytest.mark.parametrize("text", ["- a\n- b\n", "just text\n", "", "42\n"])
def test_load_template_refuses_a_non_mapping(tmp_path: Path, text: str) -> None:
    """A template that is not a mapping is a problem naming the file.

    Dies on: returning the list/scalar/`None` as the template, or returning no
    problem for it.
    """
    path = tmp_path / "t.yml"
    path.write_text(text, encoding="utf-8")
    loaded, problems = config.load_template(path)
    assert loaded is None
    assert [p.path for p in problems] == [str(path)]
    assert "mapping" in problems[0].message


def test_load_template_reports_a_non_utf8_file(tmp_path: Path) -> None:
    """A template that is not valid UTF-8 is a problem naming the file.

    Dies on: catching only `OSError` around the read.
    """
    path = tmp_path / "t.yml"
    path.write_bytes(b"site_name: \xff\n")
    loaded, problems = config.load_template(path)
    assert loaded is None
    assert [p.path for p in problems] == [str(path)]


def test_load_template_reports_a_missing_file(tmp_path: Path) -> None:
    """A missing template is a problem naming it, not an exception.

    Dies on: dropping the `OSError` handling.
    """
    path = tmp_path / "absent.yml"
    loaded, problems = config.load_template(path)
    assert loaded is None
    assert [p.path for p in problems] == [str(path)]


# --- render_config ---------------------------------------------------------


def test_render_sets_the_build_owned_keys() -> None:
    """The rendered config carries `docs_dir`, `site_dir`, the nav and `custom_dir`.

    Dies on: any of the four values changed, or a key not set (each lookup
    then fails or differs).
    """
    rendered = config.render_config(_template(), NAV)
    assert rendered["docs_dir"] == "staged"
    assert rendered["site_dir"] == "html"
    assert rendered["nav"] == NAV
    assert rendered["theme"]["custom_dir"] == "overrides"  # type: ignore[index]


def test_render_keeps_every_template_value() -> None:
    """Template keys other than the build-owned four pass through unchanged.

    Dies on: rendering from a fresh dict that omits template keys, or
    replacing `theme` wholesale with a dict holding only `custom_dir`.
    """
    template = _template()
    rendered = config.render_config(template, NAV)
    expected = copy.deepcopy(template)
    expected["theme"]["custom_dir"] = "overrides"
    expected.update({"docs_dir": "staged", "site_dir": "html", "nav": NAV})
    assert rendered == expected


def test_render_does_not_mutate_the_template() -> None:
    """Rendering leaves the input template, including nested `theme`, untouched.

    Dies on: `dict(template)` instead of a deep copy (the nested `theme`
    gains `custom_dir`), or assigning into `template` directly.
    """
    template = _template()
    before = copy.deepcopy(template)
    rendered = config.render_config(template, NAV)
    assert template == before
    assert "custom_dir" not in template["theme"]
    assert rendered["theme"] is not template["theme"]


def test_render_does_not_alias_the_nav_argument() -> None:
    """Changing the rendered nav leaves the caller's nav list as it was.

    Dies on: `rendered["nav"] = nav` in place of a copy.
    """
    nav = copy.deepcopy(NAV)
    rendered = config.render_config(_template(), nav)
    rendered["nav"][0]["Home"].append({"X": "x.md"})  # type: ignore[index]
    assert nav == NAV


def test_render_adds_a_theme_when_the_template_has_none() -> None:
    """A template without `theme` still gets `theme.custom_dir`.

    Dies on: indexing `template["theme"]` unconditionally, or skipping
    `custom_dir` when `theme` is absent.
    """
    rendered = config.render_config({"site_name": "x"}, NAV)
    assert rendered["theme"] == {"custom_dir": "overrides"}


def test_render_overrides_build_owned_values_written_in_the_template() -> None:
    """A build-owned key in the template does not survive into the render.

    Dies on: `setdefault` in place of assignment for any of the four keys.
    """
    template = _template()
    template["docs_dir"] = "elsewhere"
    template["site_dir"] = "out"
    template["nav"] = [{"Bogus": "x.md"}]
    template["theme"]["custom_dir"] = "mine"
    rendered = config.render_config(template, NAV)
    assert rendered["docs_dir"] == "staged"
    assert rendered["site_dir"] == "html"
    assert rendered["nav"] == NAV
    assert rendered["theme"]["custom_dir"] == "overrides"  # type: ignore[index]


def test_render_leaves_a_non_mapping_theme_for_check_config_to_refuse() -> None:
    """A `theme` that is not a mapping is not silently replaced by the renderer.

    Dies on: rendering `theme` to `{"custom_dir": ...}` regardless of its type
    (the malformed value would vanish and `check_config` would pass).
    """
    template = _template()
    template["theme"] = "classic"
    rendered = config.render_config(template, NAV)
    assert rendered["theme"] == "classic"
    assert _wheres(config.check_config(rendered, template)) == ["theme"]


# --- check_config: clean and accepted shapes -------------------------------


def test_a_clean_template_has_no_problems() -> None:
    """A template within the allowlist renders to a config with no problems.

    Dies on: any check rejecting a build-owned key of the *rendered* config
    (`docs_dir`, `site_dir`, `nav`, `theme.custom_dir`), or a false positive
    on a bare `search` plugin, a palette entry or a toggle.
    """
    assert _check(_template()) == ()


@pytest.mark.parametrize("feature", FEATURES_29)
def test_every_allowed_feature_is_accepted(feature: str) -> None:
    """Each of the 29 features passes.

    Dies on: dropping that name from `ALLOWED_FEATURES`.
    """
    template = _template()
    template["theme"]["features"] = [feature]
    assert _check(template) == ()


def test_every_allowed_top_level_and_theme_key_is_accepted() -> None:
    """A config using every allowed top-level and theme key has no problems.

    Dies on: dropping any allowed key from `ALLOWED_TOP_LEVEL` or
    `ALLOWED_THEME_KEYS`, since the corresponding key is then named.
    """
    template: dict[str, Any] = {
        k: "v" for k in config.ALLOWED_TOP_LEVEL - set(config.BUILD_OWNED_KEYS)
    }
    template["use_directory_urls"] = True
    template["strict"] = True
    template["extra_css"] = ["a.css"]
    template["plugins"] = ["search"]
    template["theme"] = {k: "v" for k in config.ALLOWED_THEME_KEYS - {"custom_dir"}}
    template["theme"]["features"] = []
    template["theme"]["palette"] = []
    assert _check(template) == ()


def test_search_plugin_accepts_enabled_and_separator_in_mapping_form() -> None:
    """`{search: {enabled, separator}}` passes.

    Dies on: rejecting the mapping form of a plugin entry, or dropping
    `enabled` or `separator` from the search options.
    """
    template = _template()
    template["plugins"] = [{"search": {"enabled": True, "separator": "[ ]"}}]
    assert _check(template) == ()
    template["plugins"] = [{"search": None}]
    assert _check(template) == ()


# --- check_config: each refusal class singly -------------------------------


@pytest.mark.parametrize("key", config.BUILD_OWNED_KEYS)
def test_build_owned_key_in_the_template_is_refused_by_name(key: str) -> None:
    """Each build-owned key present in the template is named by its dotted path.

    Dies on: dropping that key from `BUILD_OWNED_KEYS`, checking the
    rendered config (which carries them) instead of the template, or treating
    an empty or null value as absent.
    """
    values: tuple[object, ...] = ("x", "", [], None)
    for value in values:
        template = _template()
        if key == "theme.custom_dir":
            template["theme"]["custom_dir"] = value
        else:
            template[key] = value
        problems = _check(template)
        assert _wheres(problems) == [key]
        assert all(p.path == "website/mkdocs.template.yml" for p in problems)
        assert key in problems[0].message


def test_unknown_top_level_key_is_named() -> None:
    """An unknown top-level key is named.

    Dies on: not checking the top level, or reporting a fixed string instead of
    the key.
    """
    template = _template()
    template["hooks"] = ["x.py"]
    assert _wheres(_check(template)) == ["hooks"]


def test_unknown_theme_key_is_named_by_dotted_path() -> None:
    """An unknown theme key is named `theme.<key>`.

    Dies on: not checking theme keys, or omitting the `theme.` prefix.
    """
    template = _template()
    template["theme"]["icon"] = {"repo": "x"}
    assert _wheres(_check(template)) == ["theme.icon"]


def test_unknown_palette_key_is_named_with_its_entry_index() -> None:
    """An unknown key in palette entry 1 is named `theme.palette[1].<key>`.

    Dies on: not checking palette entries, a fixed index, or checking only
    entry 0.
    """
    template = _template()
    template["theme"]["palette"][1]["bogus"] = 1
    assert _wheres(_check(template)) == ["theme.palette[1].bogus"]


def test_unknown_toggle_key_is_named() -> None:
    """An unknown key inside a palette toggle is named.

    Dies on: not checking toggle keys, or allowing any toggle key.
    """
    template = _template()
    template["theme"]["palette"][0]["toggle"]["tooltip"] = "x"
    assert _wheres(_check(template)) == ["theme.palette[0].toggle.tooltip"]


def test_unknown_feature_is_named() -> None:
    """Unknown features, `search.suggest` among them, are named by dotted path.

    Dies on: not checking features, or adding `search.suggest` to
    `ALLOWED_FEATURES`.
    """
    template = _template()
    template["theme"]["features"] = ["content.code.copy", "search.suggest", "nope.x"]
    assert _wheres(_check(template)) == [
        "theme.features.nope.x",
        "theme.features.search.suggest",
    ]


def test_near_miss_names_are_refused_exactly() -> None:
    """Near-miss spellings (case, trailing space) of allowed names are unknown.

    Dies on: `.lower()` or `.strip()` applied to the name in any one of the
    seven lookups (top-level key, theme key, feature, palette key, toggle key,
    plugin, search option).
    """
    template = _template()
    template["Site_URL"] = "x"
    template["site_name "] = "x"
    template["theme"]["Name"] = "x"
    template["theme"]["logo "] = "x"
    template["theme"]["features"] = ["Content.Code.Copy", "content.code.copy "]
    template["theme"]["palette"][0]["Scheme"] = "x"
    template["theme"]["palette"][0]["media "] = "x"
    template["theme"]["palette"][0]["toggle"]["Icon"] = "x"
    template["theme"]["palette"][0]["toggle"]["name "] = "x"
    template["plugins"] = [
        "Search",
        "search ",
        {"search": {"Enabled": 1, "separator ": 1}},
    ]
    assert _wheres(_check(template)) == sorted(
        [
            "Site_URL",
            "site_name ",
            "theme.Name",
            "theme.logo ",
            "theme.features.Content.Code.Copy",
            "theme.features.content.code.copy ",
            "theme.palette[0].Scheme",
            "theme.palette[0].media ",
            "theme.palette[0].toggle.Icon",
            "theme.palette[0].toggle.name ",
            "plugins.Search",
            "plugins.search ",
            "plugins.search.Enabled",
            "plugins.search.separator ",
        ]
    )


def test_unknown_plugin_is_named_in_both_forms() -> None:
    """An unknown plugin is named `plugins.<name>` as a bare name and as a mapping.

    Dies on: not checking plugins, checking only bare-string entries or only
    mapping entries, or checking only the first name of a multi-name mapping.
    """
    template = _template()
    template["plugins"] = ["search", "llmstxt", {"blog": {"x": 1}}]
    assert _wheres(_check(template)) == ["plugins.blog", "plugins.llmstxt"]
    template["plugins"] = [{"search": None, "rss": None, "blog": None}]
    assert _wheres(_check(template)) == ["plugins.blog", "plugins.rss"]


def test_search_option_other_than_enabled_or_separator_is_named() -> None:
    """A `search` option beyond `enabled` and `separator` is named.

    Dies on: not checking search options, or allowing `lang` or
    `prebuild_index`.
    """
    template = _template()
    template["plugins"] = [
        {"search": {"enabled": True, "lang": "en", "prebuild_index": True}}
    ]
    assert _wheres(_check(template)) == [
        "plugins.search.lang",
        "plugins.search.prebuild_index",
    ]


# --- check_config: several at once, nesting, malformed shapes --------------


def test_every_violation_of_every_class_is_reported_at_once() -> None:
    """One run reports every violation of every class together.

    Dies on: returning after the first problem or the first class, or
    skipping any one class of check.
    """
    template = _template()
    template["hooks"] = 1
    template["docs_dir"] = "x"
    template["theme"]["custom_dir"] = "y"
    template["theme"]["icon"] = 1
    template["theme"]["palette"][0]["bogus"] = 1
    template["theme"]["palette"][2]["toggle"] = {"tooltip": 1}
    template["theme"]["features"].append("nope")
    template["plugins"] = ["search", "llmstxt", {"search": {"lang": "en"}}]
    assert sorted(_wheres(_check(template))) == sorted(
        [
            "hooks",
            "docs_dir",
            "theme.custom_dir",
            "theme.icon",
            "theme.palette[0].bogus",
            "theme.palette[2].toggle.tooltip",
            "theme.features.nope",
            "plugins.llmstxt",
            "plugins.search.lang",
        ]
    )


def test_several_violations_within_one_class_are_all_reported() -> None:
    """Two unknown keys in one palette entry, and in two entries, are all named.

    Dies on: reporting one problem per class, or one per palette entry, or
    stopping at the first offending entry.
    """
    template = _template()
    template["theme"]["palette"][0]["a"] = 1
    template["theme"]["palette"][0]["b"] = 1
    template["theme"]["palette"][2]["c"] = 1
    assert _wheres(_check(template)) == [
        "theme.palette[0].a",
        "theme.palette[0].b",
        "theme.palette[2].c",
    ]


def test_problems_are_sorted_whatever_the_key_order() -> None:
    """Problems come back sorted by `(path, where, message)`.

    Dies on: returning them in discovery order (a template written `zeta`
    before `alpha` would come out unsorted).
    """
    template = _template()
    template["zeta"] = 1
    template["theme"]["zulu"] = 1
    template["alpha"] = 1
    template["theme"]["beta"] = 1
    wheres = _wheres(_check(template))
    assert wheres == ["alpha", "theme.beta", "theme.zulu", "zeta"]
    assert _wheres(_check_unsorted_order(template)) == wheres


def _check_unsorted_order(template: Mapping[str, Any]) -> tuple[Problem, ...]:
    """The same template with its keys in reverse insertion order."""
    reordered = dict(reversed(list(template.items())))
    return config.check_config(config.render_config(reordered, NAV), reordered)


@pytest.mark.parametrize(
    ("mutate", "where"),
    [
        (lambda t: t.__setitem__("theme", ["x"]), "theme"),
        (
            lambda t: t["theme"].__setitem__("features", "content.code.copy"),
            "theme.features",
        ),
        (lambda t: t["theme"].__setitem__("palette", {"scheme": "x"}), "theme.palette"),
        (lambda t: t["theme"]["palette"].__setitem__(1, "slate"), "theme.palette[1]"),
        (
            lambda t: t["theme"]["palette"][0].__setitem__("toggle", "x"),
            "theme.palette[0].toggle",
        ),
        (lambda t: t.__setitem__("theme", 5), "theme"),
        (lambda t: t.__setitem__("plugins", "search"), "plugins"),
        (lambda t: t.__setitem__("plugins", {"llmstxt": {}}), "plugins"),
        (lambda t: t.__setitem__("plugins", [3]), "plugins[0]"),
        (lambda t: t.__setitem__("plugins", [{"search": "on"}]), "plugins.search"),
        (lambda t: t["theme"]["features"].append(7), "theme.features[2]"),
    ],
)
def test_malformed_shapes_are_reported_not_raised(mutate: Any, where: str) -> None:
    """A value of the wrong type is named by path; these eleven shapes do not raise.

    Dies on: iterating a string feature list (one problem per character),
    or dropping the type check for that
    value.
    """
    template = _template()
    mutate(template)
    assert _wheres(_check(template)) == [where]


# --- referenced_assets -----------------------------------------------------


def test_referenced_assets_are_css_logo_and_favicon_in_order() -> None:
    """`extra_css` entries, then `theme.logo`, then `theme.favicon`.

    Dies on: dropping any of the three sources, reordering them, or
    returning a set/list instead of a tuple.
    """
    rendered = config.render_config(
        {
            **_template(),
            "extra_css": ["_brand/b.css", "_brand/a.css"],
        },
        NAV,
    )
    assert config.referenced_assets(rendered) == (
        "_brand/b.css",
        "_brand/a.css",
        "_brand/logo.svg",
        "_brand/favicon.svg",
    )


def test_referenced_assets_skip_absent_keys() -> None:
    """A config with none of the three keys references nothing; one key gives one path.

    Dies on: indexing a missing key, or listing `None` for a missing one.
    """
    assert config.referenced_assets({"site_name": "x"}) == ()
    assert config.referenced_assets({"theme": {"name": "classic"}}) == ()
    assert config.referenced_assets({"theme": {"favicon": "f.svg"}}) == ("f.svg",)
    assert config.referenced_assets({"extra_css": ["a.css"]}) == ("a.css",)


def test_referenced_assets_ignore_other_path_like_values() -> None:
    """Only `extra_css`, `logo` and `favicon` count; other theme values do not.

    Dies on: collecting every string value of the theme mapping.
    """
    rendered = {
        "site_url": "https://fitdocs.ai/",
        "theme": {"name": "classic", "custom_dir": "overrides", "logo": "l.svg"},
    }
    assert config.referenced_assets(rendered) == ("l.svg",)


# --- dump_config -----------------------------------------------------------


def test_dump_is_byte_identical_across_runs() -> None:
    """Dumping the same rendered config twice gives the same text.

    Dies on: a header comment carrying `time.time()` added to `dump_config`.
    """
    rendered = config.render_config(_template(), NAV)
    first = config.dump_config(rendered)
    assert first
    assert config.dump_config(copy.deepcopy(rendered)) == first
    assert config.dump_config(config.render_config(_template(), NAV)) == first


def test_dump_preserves_the_input_key_order() -> None:
    """Top-level and nested keys are written in the order the mapping holds them.

    Dies on: `sort_keys=True` in `dump_config`.
    """
    rendered = config.render_config(_template(), NAV)
    theme = rendered["theme"]
    assert list(rendered) != sorted(rendered)
    assert list(theme) != sorted(theme)  # type: ignore[call-overload]
    loaded = yaml.safe_load(config.dump_config(rendered))
    assert list(loaded) == list(rendered)
    assert list(loaded["theme"]) == list(theme)  # type: ignore[call-overload]


def test_dump_preserves_list_order() -> None:
    """Nav, features and plugin lists keep their order.

    Dies on: sorting lists, or dumping them as sets.
    """
    template = _template()
    template["extra_css"] = ["_brand/z.css", "_brand/a.css"]
    text = config.dump_config(config.render_config(template, NAV))
    loaded = yaml.safe_load(text)
    assert loaded["extra_css"] == ["_brand/z.css", "_brand/a.css"]
    assert loaded["nav"] == NAV
    assert loaded["nav"][1]["Guides"] == [
        {"Deep": "guides/deep.md"},
        {"Alpha": "guides/alpha.md"},
    ]
    assert loaded["theme"]["features"] == ["content.code.copy", "content.action.edit"]


def test_dump_round_trips_through_yaml() -> None:
    """`safe_load(dump)` gives back the rendered config, unicode included.

    Dies on: `allow_unicode=False`, which writes escapes instead of the
    characters.
    """
    template = _template()
    template["site_description"] = "Zürich – training"
    rendered = config.render_config(template, NAV)
    text = config.dump_config(rendered)
    assert yaml.safe_load(text) == rendered
    assert "Zürich – training" in text


def test_dump_writes_shared_objects_out_in_full() -> None:
    """An object reachable twice is written twice, with no `&`/`*` alias syntax.

    Dies on: the default `SafeDumper`, which emits anchors for repeated objects.
    """
    shared = ["content.code.copy"]
    text = config.dump_config({"a": shared, "b": shared})
    assert "&id" not in text
    assert "*id" not in text
    assert yaml.safe_load(text) == {"a": shared, "b": shared}


def test_dump_ends_with_one_newline_and_uses_block_style() -> None:
    """The dump is block-style YAML ending in a single newline.

    Dies on: `default_flow_style=True` (flow braces) or trimming the newline.
    """
    text = config.dump_config({"a": {"b": [1, 2]}})
    assert text == "a:\n  b:\n  - 1\n  - 2\n"


# --- the real template, part 2 (3.1) ---------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_TEMPLATE = REPO_ROOT / config.TEMPLATE_PATH

TEN_FEATURES = [
    "navigation.instant",
    "navigation.tracking",
    "navigation.sections",
    "navigation.path",
    "navigation.top",
    "navigation.footer",
    "toc.follow",
    "search.highlight",
    "content.code.copy",
    "content.action.edit",
]


def _real() -> dict[str, Any]:
    """The checked-in template, loaded through the production loader."""
    loaded, problems = config.load_template(REAL_TEMPLATE)
    assert problems == ()
    assert loaded is not None
    return loaded


def _real_theme() -> dict[str, Any]:
    theme = _real()["theme"]
    assert isinstance(theme, dict)
    return theme


def test_the_real_template_passes_the_allowlist_once_rendered() -> None:
    """The checked-in template renders to a config with no allowlist problem (6.4).

    Dies on: adding `docs_dir: staged` (or any unknown key, feature or plugin)
    to website/mkdocs.template.yml.
    """
    template = _real()
    rendered = config.render_config(template, NAV)
    theme = rendered["theme"]
    assert isinstance(theme, dict)
    # Reachability: the check has a theme, features, palette and plugins to look at.
    assert theme["features"] and theme["palette"] and rendered["plugins"]
    assert config.check_config(rendered, template) == ()


def test_the_real_template_carries_the_url_contract() -> None:
    """Trailing-slash URLs under the production domain (4.6).

    Dies on: `site_url: https://fitdocs.ai/` -> `https://fitdocs.ai` (or
    `use_directory_urls: false`) in the template.
    """
    template = _real()
    assert template["site_url"] == "https://fitdocs.ai/"
    assert template["use_directory_urls"] is True


def test_the_real_template_points_the_edit_link_at_the_content_source() -> None:
    """The edit link opens `website/content/` on `main` (4.4).

    Dies on: `edit_uri: edit/main/website/content/` -> `edit/master/website/content/`,
    or dropping `content.action.edit` from the features.
    """
    template = _real()
    assert template["edit_uri"] == "edit/main/website/content/"
    assert template["repo_url"] == "https://github.com/joshua-stauffer/fitdocs"
    assert "content.action.edit" in _real_theme()["features"]


def test_the_real_template_enables_search_and_the_copy_button() -> None:
    """Full-text search (4.1) and the code copy button (4.3).

    Dies on: `plugins: [search]` -> `plugins: []`, or dropping `content.code.copy`.
    """
    assert _real()["plugins"] == ["search"]
    assert "content.code.copy" in _real_theme()["features"]


def test_the_real_template_has_exactly_the_ten_features_in_order() -> None:
    """The feature list is the ten the design chose, no more (4.1-4.4).

    Dies on: appending `navigation.tabs` to `theme.features`.
    """
    assert _real_theme()["features"] == TEN_FEATURES


def test_the_real_palette_is_auto_then_light_then_dark_each_with_a_toggle() -> None:
    """System default first, then light, then dark, every entry switchable (4.2).

    Dies on: `(prefers-color-scheme: light)` -> `(prefers-color-scheme: dark)` in
    the template, or deleting the light entry's `toggle`.
    """
    palette = _real_theme()["palette"]
    assert [(e["media"], e.get("scheme")) for e in palette] == [
        ("(prefers-color-scheme)", None),
        ("(prefers-color-scheme: light)", "default"),
        ("(prefers-color-scheme: dark)", "slate"),
    ]
    for entry in palette:
        assert entry["primary"] == "custom"
        assert entry["accent"] == "custom"
        assert set(entry["toggle"]) == {"icon", "name"}
    # Pairwise-distinct, so a toggle copied from a neighbour is noticed.
    assert len({e["toggle"]["icon"] for e in palette}) == 3
    assert len({e["toggle"]["name"] for e in palette}) == 3


def test_the_real_template_fixes_theme_and_build_settings() -> None:
    """Material classic, no third-party font, strict, logo and favicon under `_brand/`.

    Dies on: `font: false` -> `font: Inter`, `variant: classic` -> `modern`,
    `strict: true` -> `false`, or `logo: _brand/logo.svg` -> `_brand/logo2.svg`.
    """
    template = _real()
    theme = _real_theme()
    assert theme["name"] == "material"
    assert theme["variant"] == "classic"
    assert theme["font"] is False
    assert theme["logo"] == "_brand/logo.svg"
    assert theme["favicon"] == "_brand/logo.svg"
    assert template["strict"] is True
    assert template["extra_css"] == ["_brand/brand.css"]


def test_the_real_template_references_only_assets_the_site_ships() -> None:
    """Each referenced asset is a file of `website/assets/` under `_brand/` (4.5).

    Dies on: `logo: _brand/logo.svg` -> `_brand/logo2.svg`, or `extra_css` ->
    `_brand/site.css` in the template.
    """
    rendered = config.render_config(_real(), NAV)
    referenced = config.referenced_assets(rendered)
    assert sorted(referenced) == [
        "_brand/brand.css",
        "_brand/logo.svg",
        "_brand/logo.svg",
    ]
    for path in referenced:
        name = path.removeprefix("_brand/")
        assert name != path
        assert (REPO_ROOT / "website" / "assets" / name).is_file()
