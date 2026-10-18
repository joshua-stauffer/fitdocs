"""Published statements of the local-start rename (activity-identity Amendment 2).

The ownership contract states the rename beside the base-change and settle
renames (A2.2), the workouts declaration carries it in its rename sentence, and
the contract version's history records why the version advanced (A2.3). Each
pin is the sentence a reader relies on.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from fitdocs import contract, declaration
from fitdocs.contract import CONTRACT_VERSION

ROOT = Path(__file__).resolve().parents[1]


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_contract_states_the_local_start_rename() -> None:
    text = _flat((ROOT / "docs/ownership-contract.md").read_text(encoding="utf-8"))
    assert (
        "and a page whose filename is the one fitdocs computed from the local "
        "start time its own `start_time` records is moved to the newly computed "
        "name when that local start changes"
    ) in text
    assert "with two exceptions, each renamed with the same chart-asset cleanup" in text
    head = text.split(" ## ", 1)[0]
    assert f"**Contract version:** `{CONTRACT_VERSION}`" in head
    assert (
        "A workout page whose filename fitdocs chose from its local start time "
        "now follows that start time when it changes"
    ) in head


def test_workouts_declaration_states_the_local_start_rename() -> None:
    golden = (ROOT / "tests/declaration_golden/workouts.AGENTS.md").read_text(
        encoding="utf-8"
    )
    sentence = (
        "or, when fitdocs chose its filename from its local start time, when "
        "that local start time changes; links to its previous filename are not "
        "updated."
    )
    assert sentence in _flat(declaration._RENAMES)
    assert sentence in _flat(golden)


def test_contract_version_history_records_the_rename() -> None:
    history = _flat(inspect.getsource(contract))
    assert CONTRACT_VERSION == "16"
    assert "Raised from ``15`` to ``16`` by the local-time fix" in history
    assert (
        "A page whose filename fitdocs chose from its local start time is "
        "renamed, with its chart assets and a rename warning, when that local "
        "start changes"
    ) in history
