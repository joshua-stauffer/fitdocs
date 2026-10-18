"""Published guidance for the morning-of block and its report."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fitdocs.contract import CONTRACT_VERSION, DOC_VERSION
from tests._changelog_view import V0_1_0, unreleased_since

ROOT = Path(__file__).resolve().parents[2]


def _flat(text: str) -> str:
    return " ".join(text.split())


def _section(path: str, heading: str, level: int = 2) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    if path == "CHANGELOG.md":
        text = unreleased_since(text, V0_1_0)
    return text.partition(f"{'#' * level} {heading}\n")[2].split(
        f"\n{'#' * level} ", 1
    )[0]


@pytest.mark.parametrize(
    "statement",
    (
        "The `Morning Of` block before Training Load shows resting heart rate, "
        "HRV and sleep from the normalized wellness series, and no other "
        "wellness signal.",
        "It shows the wellness day equal to the workout page's date; see "
        "[Wellness day](#wellness-day).",
        "The 7-day means include that day and the preceding six days; normal "
        "ranges and 60-day means use the preceding 60 days, excluding that day.",
        "Each row names its source and the origins of the values contributing "
        "to its displayed figures.",
        "Garmin values add `Data source: Garmin` when they are the sole origin, "
        "or `Data sources: Garmin and other sources` when other or unknown "
        "origins also contribute.",
        "An absent figure is `–`, not zero.",
        "Pages refresh on every `fitdocs sync` (with or without a source), "
        "`fitdocs pull --sync` and `fitdocs regen`.",
        "The block is fitdocs-owned: hand edits are replaced when the pass "
        "refreshes it from the series.",
        "It states no readiness verdict or score and makes no training recommendation.",
        "It shares `fitdocs recovery`'s numbers for the same day and source.",
    ),
    ids=(
        "figures",
        "page-day-and-link",
        "windows",
        "sources-and-origins",
        "garmin-lines",
        "absence",
        "refresh-commands",
        "edits-replaced",
        "no-verdict",
        "recovery-numbers",
    ),
)
def test_wellness_block_guidance(statement: str) -> None:
    section = _flat(_section("docs/wellness.md", "Wellness on workout pages"))
    assert statement in section


def test_wellness_day_link_resolves_to_a_heading() -> None:
    section = _section("docs/wellness.md", "Wellness on workout pages")
    target = re.search(r"\[Wellness day\]\(#([^)]*)\)", section)
    anchor = target.group(1) if target is not None else ""
    text = (ROOT / "docs/wellness.md").read_text(encoding="utf-8")
    headings = {
        re.sub(r"[^\w -]", "", heading).lower().replace(" ", "-")
        for heading in re.findall(r"(?m)^#{1,6} (.+)$", text)
    }
    assert anchor in headings


@pytest.mark.parametrize(
    "statement",
    (
        "`Morning of:` lines follow the drain report.",
        "`Morning of: 1 page updated, 1 block removed.` means blocks were "
        "refreshed, or cleared when their wellness figures disappeared; "
        "no athlete action is needed.",
        "Counts use singular or plural, and a zero-count clause is omitted.",
        "`Morning of: could not update <doc>: <detail>` means that page could "
        "not be refreshed: read the reason and tell the athlete; damaged "
        "markers need a human.",
        "`Morning of: 1 page has no morning-of region (written by an older "
        "fitdocs, or the region markers were removed); run 'fitdocs regen' to "
        "add it.` (or `2 pages have` for two) means a region is missing.",
        "Run `fitdocs regen` only when `fitdocs check` or the release notes "
        "call for it; never run it as part of the routine pair.",
        "`Morning of: not refreshed; the wellness series could not be read: "
        "<reason>.` means the series was unavailable.",
        "`Morning of: not refreshed; <ExceptionType>: <message>.` means the "
        "pass raised an error.",
        "Neither `not refreshed` line needs athlete action; the next run retries.",
    ),
    ids=(
        "ordering",
        "updated-removed-action",
        "count-grammar",
        "failed-action",
        "missing-line",
        "conditional-regen",
        "unavailable-line",
        "error-line",
        "retry-action",
    ),
)
def test_workouts_skill_morning_report(statement: str) -> None:
    section = _flat(
        _section("src/fitdocs/skills/fitdocs-workouts/SKILL.md", "Reading the report")
    )
    assert statement in section


def test_upgrading_names_archived_wellness_and_rebuild_order() -> None:
    section = _flat(
        _section("docs/upgrading.md", "When a release moves the document format")
    )
    assert (
        "For the morning-of block it also reads the archived wellness files "
        "through the wellness series, which it rebuilds first."
    ) in section


@pytest.mark.parametrize(
    ("heading", "entry"),
    (
        (
            "Added",
            "Workout pages gain a `Morning Of` block with the day's wellness "
            "signals and sleep against the athlete's own per-source baselines. "
            "Every `fitdocs sync`, `fitdocs pull --sync` and `fitdocs regen` "
            "refreshes it from the wellness series; it states no readiness verdict.",
        ),
        (
            "Changed",
            "The generated document format advances (`doc_version` 9 to 10) "
            "to add the morning-of region. Run `fitdocs regen` once after "
            "upgrading to bring existing workout pages to the current format.",
        ),
        (
            "Changed",
            "The ownership contract (wiki-contract) advances from version `14` "
            "to `15`: fitdocs owns the refreshed morning-of region and its "
            "pass. Run `fitdocs regen` once to refresh existing pages and "
            "their ownership declarations.",
        ),
        (
            "Changed",
            "A change confined to the morning-of block is a document-only "
            "change in the analytics index: it updates the document without "
            "recomputing the page's computed values.",
        ),
    ),
    ids=(
        "block-and-refresh",
        "doc-version-and-action",
        "contract-version-and-action",
        "index-document-only",
    ),
)
def test_morning_release_entries(heading: str, entry: str) -> None:
    unreleased = _section("CHANGELOG.md", "[Unreleased]")
    section = unreleased.partition(f"### {heading}\n")[2].split("\n### ", 1)[0]
    entries = [_flat(part) for part in section.split("\n- ")[1:]]
    assert entry in entries


@pytest.mark.parametrize("kind", ("doc", "contract"))
def test_release_versions_match_contract(kind: str) -> None:
    changed = _flat(_section("CHANGELOG.md", "[Unreleased]"))
    if kind == "doc":
        match = re.search(
            r"\(`doc_version` (\d+) to (\d+)\) to add the morning-of region", changed
        )
        actual = tuple(map(int, match.groups())) if match else ()
        expected = (DOC_VERSION - 1, DOC_VERSION)
    else:
        match = re.search(
            r"advances from version `(\d+)` to `(\d+)`: "
            r"fitdocs owns the refreshed morning-of",
            changed,
        )
        actual = tuple(map(int, match.groups())) if match else ()
        expected = (int(CONTRACT_VERSION) - 1, int(CONTRACT_VERSION))
    assert actual == expected


def test_structure_records_morning_dependency_boundary() -> None:
    section = _flat(
        _section(".kiro/steering/structure.md", "Code Organization Principles")
    )
    assert (
        "`morning` (the morning-of block and its pass) imports the `wellness` "
        "and `recovery` facades, `contract`, `docmerge`, `docio`, `layout`, the "
        "render layer's absence marker and wellness attribution helpers and "
        "the chart kit's value formatter; only `cli` imports `morning.engine`; "
        "`render` never imports `morning`."
    ) in section
