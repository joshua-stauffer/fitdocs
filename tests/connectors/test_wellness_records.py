"""Ownership contract records for wellness-pull (12.4)."""

from __future__ import annotations

from pathlib import Path

import pytest
from markdown_it import MarkdownIt
from markdown_it.token import Token

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


def _head() -> str:
    paragraphs = [
        _inline(token)
        for token in _section(None)
        if token.type == "inline"
        and token.level == 1
        and _inline(token).startswith("What changed at this version:")
    ]
    return paragraphs[0] if len(paragraphs) == 1 else ""


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
        "wellness-pull changes the stated guarantees about what `fitdocs pull` "
        "writes and removes.",
        "For an instance with `wellness = true` the pull also writes wellness "
        "files, `wellness-<first>_<last>.json` holding the records the service "
        "returned, under `<inbox>/<name>/`",
        "removes each one once `wellness-archive/` holds identical bytes; "
        "it never writes `wellness-archive/` or `wellness/`.",
        "A connector's ledger that holds wellness records is ledger format 2.",
        "Nothing is needed for existing documents; set `wellness = true` "
        "on an instance to pull wellness.",
    ],
    ids=["reason", "inbox", "removal-and-limits", "ledger", "action"],
)
def test_current_change_paragraph_states_wellness_pull(passage: str) -> None:
    assert passage in _head()
