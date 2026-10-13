"""Release-note and steering pins for dashboards task 8.2 (Requirements 19.1,
19.4, 19.5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fitdocs.contract import CONTRACT_VERSION

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHANGELOG = _REPO_ROOT / "CHANGELOG.md"
_STEERING = _REPO_ROOT / ".kiro" / "steering"
_BULLET_START = "- `fitdocs dashboard`"
_GUIDE_URL = "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/dashboards.md"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _section(text: str, heading: str) -> str:
    """The body of the one `heading` line, up to the next heading of its level."""
    lines = text.splitlines()
    matches = [index for index, line in enumerate(lines) if line == heading]
    if len(matches) != 1:
        raise ValueError(f"expected one {heading!r} heading, found {len(matches)}")
    level = len(heading) - len(heading.lstrip("#"))
    stop = "#" * level + " "
    body: list[str] = []
    for line in lines[matches[0] + 1 :]:
        if line.startswith(stop):
            break
        body.append(line)
    return "\n".join(body)


def _bullets(section: str) -> tuple[str, ...]:
    bullets: list[list[str]] = []
    for line in section.splitlines():
        if line.startswith("- "):
            bullets.append([line])
        elif bullets:
            bullets[-1].append(line)
    return tuple("\n".join(lines) for lines in bullets)


def _unreleased_dashboard_entry(text: str) -> str:
    added = _section(_section(text, "## [Unreleased]"), "### Added")
    matching = tuple(b for b in _bullets(added) if b.startswith(_BULLET_START))
    if len(matching) != 1:
        raise ValueError(
            f"expected one unreleased dashboard entry, found {len(matching)}"
        )
    return matching[0]


def _released_text(text: str) -> str:
    return text.split("## [Unreleased]", 1)[1].split("\n## [", 1)[1]


def _steering_bullet(text: str, opener: str) -> str:
    """The one top-level bullet of `text` that starts with `opener`."""
    found = [b for b in _bullets(text) if b.startswith(opener)]
    if len(found) != 1:
        raise ValueError(f"expected one {opener!r} bullet, found {len(found)}")
    return _flat(found[0])


def test_unreleased_added_has_exactly_one_dashboard_entry_naming_everything() -> None:
    text = _CHANGELOG.read_text(encoding="utf-8")
    entry = _flat(_unreleased_dashboard_entry(text))

    for form in ("`check`", "`refresh`", "`freeze`", "`kinds`"):
        assert form in entry, form
    assert (
        "`fitdocs sync` (with or without a source), `fitdocs pull --sync`, "
        "`fitdocs regen` and `fitdocs load` run the dashboard pass right after the "
        "index refresh"
    ) in entry
    assert "`kinds` lists the chart kinds" in entry
    assert "`fitdocs-dashboards` skill" in entry
    assert f"]({_GUIDE_URL})" in entry
    assert f"advances to version {CONTRACT_VERSION}" in entry
    assert "run `fitdocs sync` or `fitdocs regen` once" in entry
    assert "`dashboards/AGENTS.md`" in entry
    assert (
        "`fitdocs.toml` settings schema: `[plans] path` is now refused when it "
        "is `dashboards` or inside it (exit status `2`)"
    ) in entry
    assert "move them and set `[plans] path` to the new directory" in entry


def test_the_dashboard_entry_is_absent_from_every_released_section() -> None:
    released = _released_text(_CHANGELOG.read_text(encoding="utf-8"))
    assert released.strip(), "the released sections were not found"
    assert "`fitdocs dashboard`" not in released
    assert "`fitdocs-dashboards`" not in released
    assert _GUIDE_URL not in released


_SYNTHETIC_CHANGELOG = f"""# Changelog

## [Unreleased]

### Added

- `fitdocs query` is a neighbor.
- `fitdocs dashboard` is the entry.
  Its continuation line.
- Another neighbor.

### Changed

- `fitdocs dashboard` appears under Changed only.

## [98.76.54] - 2026-09-19

### Added

- `fitdocs dashboard` appears only in this released section, with
  [a link]({_GUIDE_URL}).
"""


def test_the_entry_parser_keeps_continuations_and_ignores_neighbors() -> None:
    entry = _unreleased_dashboard_entry(_SYNTHETIC_CHANGELOG)
    assert entry == "- `fitdocs dashboard` is the entry.\n  Its continuation line."


def test_a_second_dashboard_bullet_is_refused() -> None:
    doubled = _SYNTHETIC_CHANGELOG.replace(
        "- Another neighbor.", "- `fitdocs dashboard` again.", 1
    )
    with pytest.raises(ValueError, match="found 2"):
        _unreleased_dashboard_entry(doubled)


def test_a_released_or_changed_bullet_cannot_stand_in_for_the_entry() -> None:
    without = _SYNTHETIC_CHANGELOG.replace(
        "- `fitdocs dashboard` is the entry.\n  Its continuation line.\n", "", 1
    )
    with pytest.raises(ValueError, match="found 0"):
        _unreleased_dashboard_entry(without)


def test_tech_states_the_exception_and_the_shared_sandbox() -> None:
    tech = (_STEERING / "tech.md").read_text(encoding="utf-8")

    architecture = _flat(
        tech.split("## Architecture", 1)[1].split("## Core Technologies", 1)[0]
    )
    assert (
        "never read back into a document, except the chart regions and chart "
        "assets of dashboard pages under `dashboards/`; workout, history and "
        "block documents never read it."
    ) in architecture

    network = _flat(
        tech.split("## Network and Credentials", 1)[1].split(
            "## Development Standards", 1
        )[0]
    )
    assert (
        "`fitdocs query` runs agent SQL read-only under a locked DuckDB "
        "configuration with external access and extension loading off. "
        "`fitdocs dashboard` and the dashboard pass run chart SQL through the "
        "same sandbox."
    ) in network


def test_structure_states_the_dashboards_imports_and_the_query_importers() -> None:
    structure = (_STEERING / "structure.md").read_text(encoding="utf-8")
    organization = structure.split("## Code Organization Principles", 1)[1]

    query = _steering_bullet(organization, "- `query`")
    assert "only `cli` and `dashboards` import it;" in query
    assert "it never imports `duckdb` or an index writer." in query

    dashboards = _steering_bullet(organization, "- `dashboards`")
    assert "imports `query` (in `dashboards.binding` only)" in dashboards
    assert (
        "the chart kit facade (`render.charts.kit`, and `kit.format` in "
        "`dashboards.region` only)"
    ) in dashboards
    assert "`units` (in `dashboards.binding` and `dashboards.engine`)" in dashboards
    assert (
        "`layout` and `contract` (allowed in `dashboards.storage` and "
        "`dashboards.engine`; today only `dashboards.storage` imports them)"
    ) in dashboards
    assert "`yaml` (in `dashboards.directive` only)" in dashboards
    assert "only `cli` imports it, and only lazily;" in dashboards
    assert "it never imports `duckdb`, `index` or a clock." in dashboards


def test_the_steering_bullet_finder_refuses_a_missing_or_repeated_bullet() -> None:
    text = "- `query` one\n  more\n- `dashboards` two\n- `dashboards` three\n"
    assert _steering_bullet(text, "- `query`") == "- `query` one more"
    with pytest.raises(ValueError, match="found 2"):
        _steering_bullet(text, "- `dashboards`")
    with pytest.raises(ValueError, match="found 0"):
        _steering_bullet(text, "- `units`")
