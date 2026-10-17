from pathlib import Path

import pytest

from fitdocs.hr_benchmarks.sources import (
    MAX_RULE,
    MAX_STEP_BPM,
    RESTING_CONFIRM_DAYS,
    RESTING_STEP_BPM,
)

_GUIDE = Path(__file__).resolve().parents[2] / "docs" / "configuration.md"


@pytest.mark.parametrize(
    ("phrase", "value"),
    [
        ("Resting disagreement step: more than {value:g} bpm.", RESTING_STEP_BPM.value),
        (
            "Resting confirmation: {value:g} consecutive days.",
            RESTING_CONFIRM_DAYS.value,
        ),
        (
            "Maximum rise step: more than {value:g} bpm above the value in force.",
            MAX_STEP_BPM.value,
        ),
        (
            "Maximum confirmation: {value:g} day (no waiting period).",
            MAX_RULE.confirm_days,
        ),
    ],
    ids=(
        "resting-step",
        "resting-confirmation",
        "maximum-step",
        "maximum-confirmation",
    ),
)
def test_guide_steps_and_confirmation_match_rules(phrase: str, value: int) -> None:
    guide = " ".join(_GUIDE.read_text(encoding="utf-8").split())
    assert phrase.format(value=value) in guide


def test_guide_states_current_takeover_listing_rule() -> None:
    guide = " ".join(_GUIDE.read_text(encoding="utf-8").split())
    assert (
        "`fitdocs check` lists a takeover only while that derived entry is the "
        "latest entry of its kind; a later hand-recorded or derived entry ends "
        "the listing."
    ) in guide


def test_guide_states_the_amended_maximum_rules() -> None:
    guide = " ".join(_GUIDE.read_text(encoding="utf-8").split())
    assert all(
        phrase in guide
        for phrase in (
            "Only run and ride sessions supply it",
            "no evidence is ever dated after the newest qualifying session",
            "A derived maximum never falls",
            "Record a lower maximum by hand.",
            "challenged only by evidence dated after its measurement date",
        )
    )
    assert "applied by applies-from date" not in guide
    assert "back-reach takeover" not in guide
