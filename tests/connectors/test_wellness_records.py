"""Ownership contract records for wellness-pull (12.4)."""

from __future__ import annotations

from pathlib import Path

import pytest
from markdown_it import MarkdownIt
from markdown_it.token import Token

from tests._changelog_view import current_changelog
from tests.identity.test_contract_docs import _contract_version_history

_ROOT = Path(__file__).resolve().parents[2]
_DOC = _ROOT / "docs" / "ownership-contract.md"
_MD = MarkdownIt("commonmark")


def _inline(token: Token) -> str:
    pieces = []
    for child in token.children or []:
        if child.type == "text":
            pieces.append(child.content)
        elif child.type == "code_inline":
            pieces.append(f"`{child.content}`")
        elif child.type in {"softbreak", "hardbreak"}:
            pieces.append(" ")
        elif child.type == "html_inline" and not child.content.startswith("<!--"):
            return ""
    return " ".join("".join(pieces).split())


def _section(title: str | None) -> list[Token]:
    expected = [(1, "fitdocs Ownership Contract")]
    if title is not None:
        expected.append((2, title))
    path: list[tuple[int, str]] = []
    matches = []
    tokens = _MD.parse(_DOC.read_text(encoding="utf-8"))
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        level = int(token.tag[1:])
        while path and path[-1][0] >= level:
            path.pop()
        path.append((level, _inline(tokens[index + 1])))
        if path == expected:
            end = next(
                (
                    later
                    for later in range(index + 3, len(tokens))
                    if tokens[later].type == "heading_open"
                    and (title is None or int(tokens[later].tag[1:]) <= level)
                ),
                len(tokens),
            )
            matches.append(tokens[index + 3 : end])
    return matches[0] if len(matches) == 1 else []


def _pull() -> str:
    items = []
    tokens = _section("Overwrite Semantics of Every Writing Operation")
    for index, token in enumerate(tokens):
        if token.type != "list_item_open" or token.level != 1:
            continue
        paragraphs = []
        for child in tokens[index + 1 :]:
            if child.type == "list_item_close" and child.level == token.level:
                break
            if child.type == "inline" and child.level == token.level + 2:
                paragraphs.append(_inline(child))
        if paragraphs and paragraphs[0].startswith("`pull` —"):
            items.append(" ".join(paragraphs))
    return items[0] if len(items) == 1 else ""


@pytest.mark.parametrize(
    "passage",
    [
        "fetches new activity files and, for an instance with wellness enabled, "
        "wellness files from each configured connector instance and writes each "
        "one it accepts under `<inbox>/<name>/`",
        "A wellness delivery holds the records the service returned, named "
        "`wellness-<first>_<last>.json`, and is removed by a later pull only once "
        "`wellness-archive/` holds identical bytes.",
        "never writes, alters, or deletes a `workouts/*.md` document, a "
        "`fit-archive/*` archived source, a `wellness-archive/*` archived wellness "
        "file, a `wellness/*` series file, the athlete profile, or the settings file",
    ],
    ids=["inbox", "removal", "write-limits"],
)
def test_pull_bullet_states_wellness_guarantees(passage: str) -> None:
    assert passage in _pull()


@pytest.mark.parametrize(
    "passage",
    [
        "the data root gains an owned location.",
        "`recovery/` holds the recovery page `recovery/recovery.md` and its "
        "charts under `recovery/assets/`",
        "written by `fitdocs recovery` from the wellness series and the "
        "workout documents and rewritten only when their content changes",
        "a chart the page no longer shows is removed.",
        "Run `fitdocs sync`, `fitdocs regen`, `fitdocs history` or "
        "`fitdocs recovery` once to place `recovery/AGENTS.md`.",
    ],
    ids=["reason", "owned-content", "source-and-rewrites", "removal", "action"],
)
def test_version_history_states_recovery(passage: str) -> None:
    assert passage in _contract_version_history().replace("``", "`")


def _record_text(token: Token) -> str:
    pieces = []
    links = []
    for child in token.children or []:
        if child.type == "text":
            pieces.append(child.content)
        elif child.type == "code_inline":
            pieces.append(f"`{child.content}`")
        elif child.type in {"softbreak", "hardbreak"}:
            pieces.append(" ")
        elif child.type == "link_open":
            links.append(child.attrGet("href") or "")
            pieces.append("[")
        elif child.type == "link_close":
            pieces.append(f"]({links.pop()})")
        elif child.type == "html_inline" and not child.content.startswith("<!--"):
            return ""
    return " ".join("".join(pieces).split())


def _record_section(file: str, headings: tuple[str, ...]) -> list[Token]:
    text = (_ROOT / file).read_text(encoding="utf-8")
    if file == "CHANGELOG.md":
        text = current_changelog(text)
    tokens = _MD.parse(text)
    expected = list(enumerate(headings, start=1))
    ancestry: list[tuple[int, str]] = []
    matches = []
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or token.level != 0:
            continue
        level = int(token.tag[1:])
        while ancestry and ancestry[-1][0] >= level:
            ancestry.pop()
        ancestry.append((level, _record_text(tokens[index + 1])))
        if ancestry == expected:
            end = next(
                (
                    later
                    for later in range(index + 3, len(tokens))
                    if tokens[later].type == "heading_open" and tokens[later].level == 0
                ),
                len(tokens),
            )
            matches.append(tokens[index + 3 : end])
    return matches[0] if len(matches) == 1 else []


def _record_paragraphs(tokens: list[Token]) -> list[str]:
    return [
        _record_text(token)
        for token in tokens
        if token.type == "inline" and token.level == 1
    ]


def _changelog_item(category: str, prefix: str) -> str:
    tokens = _record_section("CHANGELOG.md", ("Changelog", "[Unreleased]", category))
    items = []
    for index, token in enumerate(tokens):
        if token.type != "list_item_open" or token.level != 1:
            continue
        paragraphs = []
        for child in tokens[index + 1 :]:
            if child.type == "list_item_close" and child.level == token.level:
                break
            if child.type == "inline" and child.level == token.level + 2:
                paragraphs.append(_record_text(child))
        if paragraphs and paragraphs[0].startswith(prefix):
            items.append(" ".join(paragraphs))
    return items[0] if len(items) == 1 else ""


def test_wellness_intake_names_enabled_pull_and_links_connector() -> None:
    passage = (
        "The intervals.icu pull delivers wellness files into the inbox: set "
        "`wellness = true` on your connector instance and run `fitdocs pull --sync`. "
        "See [wellness pulling](connectors.md#wellness) for setup and limits."
    )
    tokens = _record_section(
        "docs/wellness.md", ("Wellness", "Get files into the inbox")
    )
    assert any(
        token.type == "inline"
        and token.level == 1
        and _record_text(token) == passage
        and any(
            child.type == "link_open"
            and child.attrGet("href") == "connectors.md#wellness"
            for child in token.children or []
        )
        for token in tokens
    )


@pytest.mark.parametrize(
    ("feature", "heading"),
    [
        (
            "connectors",
            "Amendment 4 (2026-10-15): pull-wellness driven by wellness-pull",
        ),
        (
            "intervals-connector",
            "Amendment 1 (2026-10-15): wellness listing and packaging by wellness-pull",
        ),
    ],
)
def test_upstream_amendment_records_wellness_pull(feature: str, heading: str) -> None:
    assert "Landed by wellness-pull." in _record_paragraphs(
        _record_section(
            f".kiro/specs/{feature}/requirements.md", ("Requirements Document", heading)
        )
    )


@pytest.mark.parametrize(
    ("category", "prefix", "passage"),
    [
        (
            "Added",
            "The intervals.icu wellness pull",
            "`fitdocs pull` delivers wellness files",
        ),
        (
            "Added",
            "The intervals.icu wellness pull",
            "`fitdocs.toml` settings schema gains the optional `wellness` key",
        ),
        (
            "Added",
            "The intervals.icu wellness pull",
            "field attribution from intervals.icu's per-platform "
            "wellness import settings",
        ),
        (
            "Added",
            "The intervals.icu wellness pull",
            "a separate wellness report table",
        ),
        (
            "Changed",
            "Connector ledger format",
            "ledger format 2 when it holds wellness records",
        ),
        (
            "Changed",
            "Connector ledger format",
            "An older fitdocs refuses such a ledger",
        ),
        (
            "Changed",
            "Connector ledger format",
            "set `wellness = true` on the instance and run `fitdocs pull --sync`",
        ),
        (
            "Changed",
            "Ownership contract version advances from `11` to `12`",
            "wellness deliveries into the instance's inbox, their removal once "
            "identical bytes are archived, and the pull never writing the wellness "
            "archive or series",
        ),
    ],
    ids=[
        "pull",
        "key",
        "attribution",
        "report",
        "ledger",
        "old-reader",
        "action",
        "contract",
    ],
)
def test_unreleased_wellness_records(category: str, prefix: str, passage: str) -> None:
    assert passage in _changelog_item(category, prefix)
