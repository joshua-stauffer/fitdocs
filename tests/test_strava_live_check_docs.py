"""The Strava live-check procedure and its record template exist (strava-publish
task 8, Requirements 18.1, 18.2).

The check itself is the maintainer's and is never run here; these tests read
the two files only. They pin that the procedure's first section states the
write to a real account and that the record has a row for each of the four
steps.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCEDURE = ROOT / "relay" / "LIVE_CHECK_STRAVA.md"
RECORD = ROOT / "relay" / "LIVE_CHECK_STRAVA_RECORD.md"

STEPS = (
    "connect",
    "publish an update to one activity",
    "follow the link",
    "disconnect",
)


def _flat(text: str) -> str:
    return " ".join(text.split())


def _sections(text: str) -> list[str]:
    parts = re.split(r"^## ", text, flags=re.MULTILINE)
    return parts[1:]


def test_both_files_exist_and_are_non_empty() -> None:
    for path in (PROCEDURE, RECORD):
        assert path.is_file(), path
        assert path.read_text(encoding="utf-8").strip(), path


def test_first_section_states_the_real_account_write() -> None:
    sections = _sections(PROCEDURE.read_text(encoding="utf-8"))
    assert len(sections) >= 3, "the procedure lost its sections"
    first = _flat(sections[0])
    assert first.startswith("1. This writes to a real account")
    assert "writes to a real Strava account" in first
    # The statement is the first section's, not a later one's.
    assert "writes to a real Strava account" not in _flat(" ".join(sections[1:]))


def test_record_has_one_row_per_step_with_codes_and_a_note() -> None:
    text = RECORD.read_text(encoding="utf-8")
    table = text.split("| Step |", 1)[1].split("\n\n", 1)[0]
    rows = [line for line in table.splitlines()[2:] if line.startswith("|")]
    assert len(rows) == len(STEPS)
    for index, (row, step) in enumerate(zip(rows, STEPS, strict=True), start=1):
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert cells[0] == f"{index}. {step}" or cells[0].startswith(f"{index}. {step}")
        assert len(cells) == 3
        assert cells[1] == "" and cells[2] == "", "the template ships unfilled"
    assert "fitdocs code observed" in table
    assert "fitdocs-written note" in table


def test_record_says_it_holds_only_reported_codes() -> None:
    flat = _flat(RECORD.read_text(encoding="utf-8"))
    assert "only with the codes the maintainer reports" in flat
    assert "never with Strava Data" in flat
