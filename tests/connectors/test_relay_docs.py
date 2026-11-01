"""`docs/relay.md`'s relay code table bound to the vocabulary
(relay-server task 8.3; Requirements 16.4).

The operator page lists every relay code with its HTTP status, origin and
explanation. The table is parsed out of the page and compared, row by row and
in order, with `fitdocs.connectors.relay_codes.RELAY_CODES`, so a code added to,
removed from or reworded in the vocabulary reds this file until the page
follows. The page's environment table and versions are bound on the relay side
(`relay/tests/test_docs_relay.py`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fitdocs.connectors.relay_codes import RELAY_CODES, RelayCodeInfo

_PAGE = Path(__file__).resolve().parents[2] / "docs" / "relay.md"
_HEADER = "| Code | Status | Origin | Meaning |"
_NO_STATUS = "—"


def _page_text() -> str:
    assert _PAGE.is_file(), f"the operator page is missing: {_PAGE}"
    return _PAGE.read_text(encoding="utf-8")


def _table_rows(text: str) -> list[list[str]]:
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == _HEADER]
    if len(starts) != 1:
        return []
    rows: list[list[str]] = []
    for line in lines[starts[0] + 2 :]:
        if not line.startswith("|"):
            break
        cells = re.split(r"(?<!\\)\|", line.strip())[1:-1]
        rows.append([cell.strip().replace("\\|", "|") for cell in cells])
    return rows


def _row(info: RelayCodeInfo) -> list[str]:
    return [
        f"`{info.code.value}`",
        _NO_STATUS if info.http_status is None else str(info.http_status),
        info.origin.value,
        info.explanation,
    ]


def _problems(text: str) -> list[str]:
    found = _table_rows(text)
    wanted = [_row(info) for info in RELAY_CODES.values()]
    problems = [f"missing row: {row[0]}" for row in wanted if row not in found]
    problems += [f"unexpected row: {row[0]}" for row in found if row not in wanted]
    if not problems and found != wanted:
        problems.append("the rows are not in the vocabulary's order")
    return problems


def test_the_code_table_is_the_vocabulary() -> None:
    assert _problems(_page_text()) == []


def test_the_code_table_was_actually_read() -> None:
    rows = _table_rows(_page_text())
    assert len(rows) == len(RELAY_CODES) >= 22
    assert all(len(row) == 4 for row in rows)
    # Both origins are present, so the status column is read for both kinds.
    assert {row[2] for row in rows} == {"relay", "client"}


@pytest.mark.parametrize("index", range(len(RELAY_CODES)))
def test_deleting_any_code_row_reds_the_binding(index: int) -> None:
    lines = _page_text().splitlines()
    first = lines.index(_HEADER) + 2
    body = [i for i in range(first, len(lines)) if lines[i].startswith("|")]
    assert len(body) == len(RELAY_CODES), "the row scan found the wrong lines"
    del lines[body[index]]
    problems = _problems("\n".join(lines))
    assert problems == [f"missing row: `{list(RELAY_CODES)[index].value}`"]


def test_changing_a_status_reds_the_binding() -> None:
    text = _page_text()
    changed = text.replace("| `rate-limited` | 429 |", "| `rate-limited` | 503 |", 1)
    assert changed != text, "the fixture changed nothing"
    assert _problems(changed) != []


def test_swapping_two_rows_reds_the_binding() -> None:
    lines = _page_text().splitlines()
    first = lines.index(_HEADER) + 2
    lines[first], lines[first + 1] = lines[first + 1], lines[first]
    assert _problems("\n".join(lines)) == ["the rows are not in the vocabulary's order"]
