"""Wellness additions to the connectors guide (12.1, 12.2)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from markdown_it import MarkdownIt
from markdown_it.token import Token

from fitdocs.cli import _WELLNESS_REPORT_ROWS
from fitdocs.connectors.intervals import WELLNESS_HISTORY_START
from fitdocs.connectors.settings import _RESERVED_KEYS

_ROOT = Path(__file__).resolve().parents[2]
_DOC = _ROOT / "docs" / "connectors.md"
_GUIDE = (
    tomllib.loads((_ROOT / "pyproject.toml").read_text())["project"]["urls"]["Source"]
    + "/blob/main/docs/wellness.md"
)


_MD = MarkdownIt("commonmark").enable("table")


def _inline(children: list[Token], *, markup: bool = True) -> str:
    pieces = []
    links = []
    for token in children:
        if token.type == "text":
            pieces.append(token.content)
        elif token.type == "code_inline":
            pieces.append(f"`{token.content}`" if markup else token.content)
        elif token.type in {"softbreak", "hardbreak"}:
            pieces.append(" ")
        elif token.type == "link_open":
            links.append(token.attrGet("href") or "")
            if markup:
                pieces.append("[")
        elif token.type == "link_close":
            href = links.pop()
            if markup:
                pieces.append(f"]({href})")
    return " ".join("".join(pieces).split())


def _section(heading: str) -> list[Token]:
    level = len(heading) - len(heading.lstrip("#"))
    title = heading.split(" ", 1)[1]
    expected = [(1, "Connectors")]
    if level == 2:
        expected.append((2, title))
    elif level == 3:
        parent = {"Wellness": "intervals.icu", "Reading the wellness report": "Pulling"}
        expected.extend([(2, parent[title]), (3, title)])
    tokens = _MD.parse(_DOC.read_text(encoding="utf-8"))
    path: list[tuple[int, str]] = []
    matches = []
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        current = int(token.tag[1:])
        while path and path[-1][0] >= current:
            path.pop()
        path.append((current, _inline(tokens[index + 1].children or [], markup=False)))
        if path == expected:
            end = next(
                (
                    later
                    for later in range(index + 3, len(tokens))
                    if tokens[later].type == "heading_open"
                    and int(tokens[later].tag[1:]) <= max(level, 2)
                ),
                len(tokens),
            )
            matches.append(tokens[index + 3 : end])
    return matches[0] if len(matches) == 1 else []


def _body(heading: str) -> str:
    return " ".join(
        _inline(token.children or [])
        for token in _section(heading)
        if token.type == "inline"
    )


def _table_rows(
    heading: str, columns: tuple[str, str, str]
) -> list[tuple[str, str, str]]:
    tables = []
    rows: list[list[str]] | None = None
    for token in _section(heading):
        if token.type == "table_open":
            rows = []
        elif token.type == "tr_open" and rows is not None:
            rows.append([])
        elif token.type == "inline" and rows is not None:
            rows[-1].append(_inline(token.children or []))
        elif token.type == "table_close" and rows is not None:
            if rows and tuple(rows[0]) == columns:
                tables.append(rows[1:])
            rows = None
    if len(tables) != 1:
        return []
    result = []
    for row in tables[0]:
        if len(row) != 3:
            return []
        key = re.fullmatch(r"`([^`]+)`", row[0])
        if key is None:
            return []
        result.append((key.group(1), row[1], row[2]))
    return result


def _report_rows() -> list[tuple[str, str, str]]:
    return _table_rows(
        "### Reading the wellness report", ("Wellness channel", "Printed as", "Meaning")
    )


def _config_rows() -> list[tuple[str, str, str]]:
    rows = _table_rows("## Configuring an instance", ("Key", "Meaning", "Default"))
    keys = [key for key, _meaning, _default in rows]
    complete = all(meaning and default for _key, meaning, default in rows)
    return (
        rows
        if complete and len(keys) == len(set(keys)) and set(keys) == _RESERVED_KEYS
        else []
    )


def _since_item() -> str:
    items = []
    for index, token in enumerate(tokens := _section("## Pulling")):
        if token.type != "list_item_open":
            continue
        depth = 1
        paragraphs: list[str] = []
        label = ""
        for child in tokens[index + 1 :]:
            if child.type == "list_item_open":
                depth += 1
            elif child.type == "list_item_close":
                depth -= 1
                if depth == 0:
                    break
            elif child.type == "inline" and depth == 1:
                if not paragraphs:
                    label = _inline(child.children or [], markup=False)
                paragraphs.append(_inline(child.children or []))
        if re.match(r"^--since\s*:", label):
            items.append(" ".join(paragraphs))
    return items[0] if len(items) == 1 else ""


_REPORT_ROWS = [
    ("listed", "Days listed", "Wellness days returned by the listing."),
    (
        "unchanged",
        "Days unchanged",
        "Days whose revision matches the ledger; no delivery needed.",
    ),
    ("delivered", "Delivered", "Calendar-year files written into the inbox this run."),
    (
        "would_deliver",
        "Would deliver",
        "New or changed wellness days that a dry run would deliver, listed by date.",
    ),
    (
        "held",
        "Already held",
        "Packaged files whose identical bytes are already archived or pending "
        "for this instance.",
    ),
    (
        "failed",
        "Failed",
        "Wellness days or calendar-year groups that failed; the next pull "
        "retries them.",
    ),
    (
        "notices",
        "Notices",
        "Attribution changes that may need the athlete to review import settings.",
    ),
    (
        "error",
        "Error",
        "The wellness step stopped early; activity results remain in their own table.",
    ),
]


def test_report_rows_and_meanings() -> None:
    assert _report_rows() == _REPORT_ROWS


def test_report_rows_match_cli() -> None:
    assert [(label, field) for field, label, _meaning in _report_rows()] == list(
        _WELLNESS_REPORT_ROWS
    )


def test_history_start_matches_connector() -> None:
    assert (
        f"first wellness pull reads from {WELLNESS_HISTORY_START.isoformat()}"
        in _body("### Wellness")
    )


def test_wellness_instance_default() -> None:
    assert [
        default for key, _meaning, default in _config_rows() if key == "wellness"
    ] == ["`false`"]


_PASSAGES = [
    (
        "intro",
        "# Connectors",
        "pull activity `.fit` files and, where enabled, wellness files",
    ),
    (
        "capability",
        "## Configuring an instance",
        "Enable only for a connector that pulls wellness; `true` is refused otherwise.",
    ),
    (
        "lookback",
        "## Configuring an instance",
        "Also the wellness re-check window before its own wellness watermark.",
    ),
    ("since", "## Pulling", "It also starts the wellness listing on that date."),
    (
        "report",
        "### Reading the wellness report",
        "When wellness runs, a separate table follows the activity report, "
        "with all eight rows even at zero.",
    ),
    (
        "names",
        "## Delivery and removal",
        "one file per calendar year of new or changed days, named "
        "`wellness-<first-day>_<last-day><extension>`",
    ),
    (
        "extension",
        "## Delivery and removal",
        "checked by extension before delivery; an invalid package is reported "
        "as failed",
    ),
    (
        "removal",
        "## Delivery and removal",
        "The next pull removes its own wellness delivery only once the "
        "wellness archive holds identical bytes.",
    ),
    (
        "forgotten",
        "## Delivery and removal",
        "If a wellness delivery disappears before archival, its days are "
        "forgotten and the wellness mark moves back so they can be fetched "
        "again.",
    ),
    (
        "ledger",
        "## The ledger",
        "The `[wellness]` records hold the wellness mark, per-day revisions, "
        "attribution and pending wellness deliveries.",
    ),
    (
        "version",
        "## The ledger",
        "A ledger holding wellness records uses format 2; an older fitdocs refuses it.",
    ),
    (
        "enable",
        "### Wellness",
        "Set `wellness = true` in `[connectors.intervals]` to enable wellness "
        "alongside activities.",
    ),
    (
        "backfill",
        "### Wellness",
        "or from `--since YYYY-MM-DD` when given, rather than the activity "
        "pull's last 30 days",
    ),
    (
        "updated",
        "### Wellness",
        "Later pulls re-check `lookback_days` before the wellness mark and "
        "compare each day's `updated` revision.",
    ),
    (
        "requests",
        "### Wellness",
        "one wellness listing GET per window of up to a year, plus one "
        "athlete-settings GET per packaged file",
    ),
    (
        "freshness",
        "### Wellness",
        "Some platforms' wellness reaches intervals.icu only when you open "
        "intervals.icu; the look-back re-check picks up late arrivals.",
    ),
    (
        "attribution",
        "### Wellness",
        "Attribution comes from the athlete's per-platform wellness import "
        "settings, not from guessing from values.",
    ),
    (
        "limits",
        "### Wellness",
        "These settings describe current imports, not per-value history: "
        "manually entered, corrected or historically imported values can be "
        "misattributed.",
    ),
    (
        "ambiguity",
        "### Wellness",
        "A field claimed by multiple platforms has no platform attribution.",
    ),
    (
        "remedy",
        "### Wellness",
        "Review your import settings when attribution changes; use an original "
        "export when you need reliable historical provenance.",
    ),
    (
        "garmin",
        "### Wellness",
        "A 403 message may mean intervals.icu is withholding wellness received "
        "from Garmin.",
    ),
    (
        "disable",
        "### Wellness",
        "Set `wellness = false` to stop wellness requests while keeping "
        "activity pulls.",
    ),
    (
        "export",
        "### Wellness",
        f"Use Garmin's own data export through the [wellness guide]({_GUIDE}) "
        "for Garmin wellness.",
    ),
    (
        "computed",
        "### Wellness",
        "Computed fields (`ctl`, `atl`, `rampRate`, `ctlLoad`, `atlLoad` and "
        "`sportInfo`) are delivered but never imported into the wellness "
        "series.",
    ),
    (
        "allfields",
        "### Wellness",
        "The delivered file holds every field intervals.icu sent, including "
        "wellness comments and null values.",
    ),
    (
        "deleted",
        "### Wellness",
        "A day deleted on intervals.icu is not removed from fitdocs.",
    ),
]


@pytest.mark.parametrize(
    ("name", "heading", "passage"),
    _PASSAGES,
    ids=[name for name, _heading, _passage in _PASSAGES],
)
def test_guide_passage(name: str, heading: str, passage: str) -> None:
    text = _since_item() if name == "since" else _body(heading)
    meaning_key = {"capability": "wellness", "lookback": "lookback_days"}.get(name)
    if meaning_key is not None:
        text = " ".join(
            meaning for key, meaning, _default in _config_rows() if key == meaning_key
        )
    linked = name != "export" or any(
        child.type == "link_open" and child.attrGet("href") == _GUIDE
        for token in _section(heading)
        for child in token.children or []
    )
    assert passage in text and linked
