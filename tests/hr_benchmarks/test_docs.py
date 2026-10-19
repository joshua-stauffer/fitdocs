import re
import tomllib
from datetime import timedelta
from pathlib import Path

import pytest

from fitdocs import Sport
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.hr_benchmarks.sources import (
    MAX_RULE,
    MAX_STEP_BPM,
    RESTING_CONFIRM_DAYS,
    RESTING_STEP_BPM,
)
from fitdocs.load.channels.heart_rate import _MISSING_NAMES
from fitdocs.load.profile import AthleteProfile
from fitdocs.load.threshold.anchors import resolve

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


def _flat_key_section() -> str:
    guide = _GUIDE.read_text(encoding="utf-8")
    start = guide.index("**Undated profile keys never anchor training load.**")
    return guide[start : guide.index("\nResting evidence is", start)]


def test_guide_says_undated_keys_never_anchor_load_and_names_the_fix() -> None:
    """A profile carrying ``max_hr_bpm = 194`` still gets "missing: ... a
    maximum heart rate (max_hr_bpm)" from the load pass, because the
    calculator reads only dated entries. The guide must say so, quote the
    message the heart-rate channel really prints, and name both fixes."""
    section = " ".join(_flat_key_section().split())
    assert _MISSING_NAMES["max_hr"] == "a maximum heart rate (max_hr_bpm)"
    assert f"lists `{_MISSING_NAMES['max_hr']}` as missing" in section
    assert "fitdocs's built-in training-load calculator never reads them" in section
    assert "`fitdocs derive-benchmarks`" in section
    assert "`fitdocs load --recompute`" in section


def test_guide_example_entry_anchors_load_and_the_flat_key_does_not() -> None:
    """The guide's TOML example, read by the real profile and anchor
    resolver: the dated entry is in force from its ``measured_on`` and not
    before, and the flat key alone resolves to nothing."""
    (example,) = re.findall(r"```toml\n(.*?)```", _flat_key_section(), re.S)
    flat_only = AthleteProfile(data={"max_hr_bpm": 194})
    with_entry = AthleteProfile(data={"max_hr_bpm": 194, **tomllib.loads(example)})
    measured_on = with_entry.benchmarks.entries[0].measured_on

    assert not flat_only.has_benchmark(BenchmarkKind.MAX_HR_BPM, discipline=None)
    flat_anchors = resolve(flat_only, sport=Sport.RUN, on=measured_on)
    assert flat_anchors.max_hr is None
    assert (BenchmarkKind.MAX_HR_BPM, None) in flat_anchors.not_on_file

    anchors = resolve(with_entry, sport=Sport.RUN, on=measured_on)
    assert anchors.max_hr is not None and anchors.max_hr.value == 194
    earlier = resolve(with_entry, sport=Sport.RUN, on=measured_on - timedelta(days=1))
    assert earlier.max_hr is None
