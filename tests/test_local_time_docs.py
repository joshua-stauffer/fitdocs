"""Published statements of the local-time fix (workout-docs Amendment 6).

The release notes name the page-format advance and its action, the install
guide says which clock names and dates a page, and the version history in
``fitdocs.contract`` records why ``DOC_VERSION`` moved. Each pin is the
sentence a reader acts on, so deleting or rewording it reddens this module.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from fitdocs import contract
from fitdocs.contract import DOC_VERSION
from tests._changelog_view import V0_1_0, read_unreleased_since

ROOT = Path(__file__).resolve().parents[1]


def _flat(text: str) -> str:
    return " ".join(text.split())


def _unreleased_changed() -> list[str]:
    text = read_unreleased_since(ROOT / "CHANGELOG.md", V0_1_0)
    unreleased = text.partition("## [Unreleased]\n")[2].split("\n## [", 1)[0]
    section = unreleased.partition("### Changed\n")[2].split("\n### ", 1)[0]
    return [_flat(part) for part in section.split("\n- ")[1:]]


def _local_time_entry() -> str:
    entries = [
        entry
        for entry in _unreleased_changed()
        if entry.startswith("Workout pages state the local time")
    ]
    assert len(entries) == 1, entries
    return entries[0]


def test_release_note_names_the_advance_to_the_current_version() -> None:
    match = re.search(r"\(`doc_version` (\d+) to (\d+)\)", _local_time_entry())
    assert match is not None
    assert tuple(map(int, match.groups())) == (DOC_VERSION - 1, DOC_VERSION)


def test_release_note_states_the_rule_the_action_and_the_renames() -> None:
    entry = _local_time_entry()
    assert (
        "A page's `date`, `start_time`, title and heading come from the "
        "time-zone offset its `.fit` file records"
    ) in entry
    assert (
        "A file that records no offset is dated in this computer's time zone "
        "at the offset it had on the activity's own date."
    ) in entry
    assert "run `fitdocs regen` once after upgrading to correct existing pages" in entry
    assert (
        "That `regen` also renames every page whose filename fitdocs chose and "
        "whose local start moved, together with its charts, and warns for each; "
        "a filename you chose is kept."
    ) in entry
    assert (
        "Links to a renamed page's previous filename, in your own notes or "
        "elsewhere, are not updated."
    ) in entry


def test_install_guide_says_which_clock_names_a_page() -> None:
    text = _flat((ROOT / "docs/install.md").read_text(encoding="utf-8"))
    assert (
        "The local time is the clock your device kept, so a run recorded on a "
        "trip keeps that trip's time of day and date; when the file does not "
        "record its time zone, it is this computer's time zone at the offset it "
        "had on the activity's date (where the system names no time zone fitdocs "
        "can read, as on Windows, today's offset)."
    ) in text


def test_version_history_records_the_local_time_advance() -> None:
    history = _flat(inspect.getsource(contract))
    assert "Raised from ``10`` to ``11`` by the local-time fix" in history
    assert (
        "``regen`` also renames each page whose filename fitdocs chose, with its "
        "charts, when its corrected local start gives a different name"
    ) in history
