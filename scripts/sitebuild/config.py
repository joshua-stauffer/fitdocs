"""Render the generator config from the template and refuse what it would ignore.

The pinned generator silently drops unknown keys, plugins and theme features, so
for those classes the allowlist here is the only thing that notices a typo
(6.4). Standard library, PyYAML and scripts.sitebuild only.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import yaml

from scripts.sitebuild.model import Problem

TEMPLATE_PATH: Final = Path("website/mkdocs.template.yml")  # relative to repo root

ALLOWED_TOP_LEVEL: Final[frozenset[str]] = frozenset(
    {
        "site_name",
        "site_url",
        "site_description",
        "repo_url",
        "repo_name",
        "edit_uri",
        "use_directory_urls",
        "strict",
        "theme",
        "extra_css",
        "plugins",
        "docs_dir",
        "site_dir",
        "nav",
    }
)
ALLOWED_THEME_KEYS: Final[frozenset[str]] = frozenset(
    {"name", "variant", "custom_dir", "font", "logo", "favicon", "features", "palette"}
)
ALLOWED_PALETTE_KEYS: Final[frozenset[str]] = frozenset(
    {"media", "scheme", "primary", "accent", "toggle"}
)
ALLOWED_TOGGLE_KEYS: Final[frozenset[str]] = frozenset({"icon", "name"})
# The 29 names the zensical 0.0.65 bundle references (research.md). `search.suggest`
# is left out: the generator accepts it and does nothing with it.
ALLOWED_FEATURES: Final[frozenset[str]] = frozenset(
    {
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
    }
)
ALLOWED_PLUGINS: Final[frozenset[str]] = frozenset({"search"})
ALLOWED_SEARCH_OPTIONS: Final[frozenset[str]] = frozenset({"enabled", "separator"})
BUILD_OWNED_KEYS: Final[tuple[str, ...]] = (
    "docs_dir",
    "site_dir",
    "nav",
    "theme.custom_dir",
)

_DOCS_DIR: Final = "staged"
_SITE_DIR: Final = "html"
_CUSTOM_DIR: Final = "overrides"


def load_template(path: Path) -> tuple[dict[str, object] | None, tuple[Problem, ...]]:
    """Read the template as a mapping, or return one problem naming the file."""
    name = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, (Problem(name, "", f"cannot read the config template: {exc}"),)
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"{mark.line + 1}:{mark.column + 1}" if mark is not None else ""
        reason = getattr(exc, "problem", None) or "invalid YAML"
        return None, (Problem(name, where, f"invalid config template YAML: {reason}"),)
    if not isinstance(loaded, dict):
        return None, (Problem(name, "", "the config template must be a mapping"),)
    return loaded, ()


def render_config(
    template: Mapping[str, object], nav: list[dict[str, list[dict[str, str]]]]
) -> dict[str, object]:
    """Copy the template and set the build-owned keys; the input is untouched.

    ``docs_dir``, ``site_dir`` and ``nav`` are always set. ``theme.custom_dir`` is
    set when ``theme`` is absent, null or a mapping; any other ``theme`` is left
    for ``check_config`` to refuse.
    """
    rendered: dict[str, object] = copy.deepcopy(dict(template))
    rendered["docs_dir"] = _DOCS_DIR
    rendered["site_dir"] = _SITE_DIR
    rendered["nav"] = copy.deepcopy(nav)
    theme = rendered.get("theme")
    if theme is None:
        rendered["theme"] = {"custom_dir": _CUSTOM_DIR}
    elif isinstance(theme, dict):
        theme["custom_dir"] = _CUSTOM_DIR
    return rendered


def check_config(
    config: Mapping[str, object], template: Mapping[str, object]
) -> tuple[Problem, ...]:
    """Every allowlist violation of the rendered config, plus build-owned keys.

    Build-owned keys are looked for in the *template*, since the rendered config
    carries them whenever ``theme`` is absent or a mapping. Each problem names a
    dotted key, feature or plugin.
    """
    where_path = TEMPLATE_PATH.as_posix()
    found: list[tuple[str, str]] = []

    def add(where: str, message: str) -> None:
        found.append((where, message))

    for key in BUILD_OWNED_KEYS:
        if _has_dotted(template, key):
            add(key, f"{key} is set by the build and must not be in the template")

    for key in config:
        if key not in ALLOWED_TOP_LEVEL:
            add(str(key), f"unknown top-level key {key!r}")

    theme = config.get("theme")
    if theme is not None:
        if not isinstance(theme, Mapping):
            add("theme", "theme must be a mapping")
        else:
            _check_theme(theme, add)

    plugins = config.get("plugins")
    if plugins is not None:
        _check_plugins(plugins, add)

    return tuple(Problem(where_path, w, m) for w, m in sorted(found))


def _has_dotted(mapping: Mapping[str, object], dotted: str) -> bool:
    head, _, rest = dotted.partition(".")
    if head not in mapping:
        return False
    if not rest:
        return True
    child = mapping[head]
    return isinstance(child, Mapping) and _has_dotted(child, rest)


def _check_theme(theme: Mapping[Any, Any], add: Any) -> None:
    for key in theme:
        if key not in ALLOWED_THEME_KEYS:
            add(f"theme.{key}", f"unknown theme key {key!r}")

    features = theme.get("features")
    if features is not None:
        if not isinstance(features, list):
            add("theme.features", "theme.features must be a list")
        else:
            for i, feature in enumerate(features):
                if not isinstance(feature, str):
                    add(f"theme.features[{i}]", "a theme feature must be a string")
                elif feature not in ALLOWED_FEATURES:
                    add(
                        f"theme.features.{feature}",
                        f"unknown theme feature {feature!r}",
                    )

    palette = theme.get("palette")
    if palette is not None:
        if not isinstance(palette, list):
            add("theme.palette", "theme.palette must be a list")
        else:
            for i, entry in enumerate(palette):
                _check_palette_entry(i, entry, add)


def _check_palette_entry(index: int, entry: object, add: Any) -> None:
    at = f"theme.palette[{index}]"
    if not isinstance(entry, Mapping):
        add(at, "a palette entry must be a mapping")
        return
    for key in entry:
        if key not in ALLOWED_PALETTE_KEYS:
            add(f"{at}.{key}", f"unknown palette key {key!r}")
    toggle = entry.get("toggle")
    if toggle is None:
        return
    if not isinstance(toggle, Mapping):
        add(f"{at}.toggle", "a palette toggle must be a mapping")
        return
    for key in toggle:
        if key not in ALLOWED_TOGGLE_KEYS:
            add(f"{at}.toggle.{key}", f"unknown palette toggle key {key!r}")


def _check_plugins(plugins: object, add: Any) -> None:
    if not isinstance(plugins, list):
        add("plugins", "plugins must be a list")
        return
    for i, entry in enumerate(plugins):
        if isinstance(entry, str):
            options: Mapping[Any, Any] = {entry: None}
        elif isinstance(entry, Mapping):
            options = entry
        else:
            add(f"plugins[{i}]", "a plugin must be a name or a one-name mapping")
            continue
        for name, opts in options.items():
            if name not in ALLOWED_PLUGINS:
                add(f"plugins.{name}", f"unknown plugin {name!r}")
            elif opts is None:
                continue
            elif not isinstance(opts, Mapping):
                add(
                    f"plugins.{name}",
                    f"the options of plugin {name!r} must be a mapping",
                )
            else:
                for opt in opts:
                    if opt not in ALLOWED_SEARCH_OPTIONS:
                        add(
                            f"plugins.{name}.{opt}",
                            f"unknown option {opt!r} for plugin {name!r}",
                        )


def referenced_assets(config: Mapping[str, object]) -> tuple[str, ...]:
    """The paths the generator reads but never checks: ``extra_css``, logo, favicon."""
    paths: list[str] = []
    css = config.get("extra_css")
    if isinstance(css, list):
        paths.extend(item for item in css if isinstance(item, str))
    theme = config.get("theme")
    if isinstance(theme, Mapping):
        for key in ("logo", "favicon"):
            value = theme.get(key)
            if isinstance(value, str):
                paths.append(value)
    return tuple(paths)


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def dump_config(config: Mapping[str, object]) -> str:
    """The config as block-style YAML in the mapping's own key order."""
    return yaml.dump(
        dict(config),
        Dumper=_Dumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
