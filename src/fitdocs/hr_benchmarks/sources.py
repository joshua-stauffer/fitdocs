"""Heart-rate constants and their governing fitdocs choices."""

from __future__ import annotations

from typing import Final

from fitdocs.benchmarks import BenchmarkKind
from fitdocs.citation import CitedConstant, FitdocsChoice
from fitdocs.hr_benchmarks.types import HrMethod, KindRule

RESTING_BASELINE_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="resting_hr_baseline_choice",
    justification=(
        "A source-specific 28-day median smooths daily variation; at least "
        "half the window must carry values."
    ),
    search_basis=(
        "Approved hr-derivation design, HrSources; no external publication "
        "was consulted in task 2.1."
    ),
    measurement=(
        "The design measured 937 Garmin daily values: within-window IQR "
        "8.69 bpm; the 28-day median moves 0.32 bpm/day."
    ),
)

RESTING_TIMELINE_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="resting_hr_timeline_choice",
    justification=(
        "A 3 bpm step and 14 consecutive confirmation days limit timeline "
        "churn while following sustained changes."
    ),
    search_basis=(
        "Approved hr-derivation design, HrSources; no external publication "
        "was consulted in task 2.1."
    ),
    measurement=(
        "The design measured 20 entries over 937 values with confirmation; "
        "step 3 without confirmation gave 45 entries, with 14 days 20. "
        "Reserve fraction moves under 1 % per 3 bpm."
    ),
)

MAX_SAMPLE_REJECTION_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="max_hr_sample_rejection_choice",
    justification=(
        "The design places 30 bpm below exercising heart rate and 230 bpm "
        "above recorded human maxima; a 10 bpm/s rate limit rejects abrupt "
        "sensor jumps."
    ),
    search_basis=(
        "Approved hr-derivation design, HrSources; no external publication "
        "was consulted in task 2.1."
    ),
    measurement=(
        "The design measured 1,675 samples rejected across 2,475 sessions "
        "with heart rate."
    ),
)

MAX_SUSTAINED_PEAK_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="max_hr_sustained_peak_choice",
    justification=(
        "A 30-second sustained mean reduces single-sample spikes; a maximum "
        "10-second gap excludes dropouts from a continuous stretch."
    ),
    search_basis=(
        "Approved hr-derivation design, HrSources; no external publication "
        "was consulted in task 2.1."
    ),
    measurement=(
        "The design measured 2,371 sessions with a peak; single-sample "
        "maximum exceeds it by 2.54 bpm mean, and by more than 10 bpm in "
        "2.5 %."
    ),
)

MAX_RECENCY_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="max_hr_recency_choice",
    justification=(
        "A 365-day window bounds which sessions must corroborate a peak "
        "together, and the median of the three highest sustained peaks "
        "prevents one artefact session setting the value. A derived maximum "
        "never falls: the athlete records a lower maximum by hand."
    ),
    search_basis=(
        "Approved hr-derivation design, HrSources; no external publication "
        "was consulted in task 2.1."
    ),
    measurement=(
        "The design compared 365 and 730 days; 730 days changed the entry count by one."
    ),
)

MAX_TIMELINE_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="max_hr_timeline_choice",
    justification=(
        "A 2 bpm step limits timeline churn under the write-time "
        "disagreement rule, with no confirmation delay."
    ),
    search_basis=(
        "Approved hr-derivation design, HrSources; no external publication "
        "was consulted in task 2.1."
    ),
    measurement=(
        "Amendment 1 (2026-10-17) measured, over the maintainer's data root, "
        "no derived entry with the hand entry, whose applies-from date "
        "precedes all history and which no later run or bike evidence "
        "exceeded by more than the step, and 9 rising entries without it; "
        "the withdrawn falling rule gave 21, 5 dated after the newest "
        "session."
    ),
)

ROUNDING_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="hr_rounding_choice",
    justification=(
        "A half-unit offset expresses a positive halfway baseline or peak "
        "as whole bpm rounded up."
    ),
    search_basis=(
        "Approved hr-derivation design, HrSources; no external publication "
        "was consulted in task 2.1."
    ),
    measurement=(
        "The design specifies that halfway values round up; this is an "
        "arithmetic convention, not an empirical measurement."
    ),
)

RESTING_WINDOW_DAYS: Final[CitedConstant[int]] = CitedConstant(
    name="resting_window_days",
    value=28,
    source=RESTING_BASELINE_CHOICE,
)

RESTING_MIN_VALUES: Final[CitedConstant[int]] = CitedConstant(
    name="resting_min_values",
    value=14,
    source=RESTING_BASELINE_CHOICE,
)

RESTING_STEP_BPM: Final[CitedConstant[int]] = CitedConstant(
    name="resting_step_bpm",
    value=3,
    source=RESTING_TIMELINE_CHOICE,
)

RESTING_CONFIRM_DAYS: Final[CitedConstant[int]] = CitedConstant(
    name="resting_confirm_days",
    value=14,
    source=RESTING_TIMELINE_CHOICE,
)

MAX_PLAUSIBLE_LOW_BPM: Final[CitedConstant[int]] = CitedConstant(
    name="max_plausible_low_bpm",
    value=30,
    source=MAX_SAMPLE_REJECTION_CHOICE,
)

MAX_PLAUSIBLE_HIGH_BPM: Final[CitedConstant[int]] = CitedConstant(
    name="max_plausible_high_bpm",
    value=230,
    source=MAX_SAMPLE_REJECTION_CHOICE,
)

MAX_RATE_BPM_PER_S: Final[CitedConstant[int]] = CitedConstant(
    name="max_rate_bpm_per_s",
    value=10,
    source=MAX_SAMPLE_REJECTION_CHOICE,
)

MAX_GAP_S: Final[CitedConstant[int]] = CitedConstant(
    name="max_gap_s",
    value=10,
    source=MAX_SUSTAINED_PEAK_CHOICE,
)

MAX_PEAK_WINDOW_S: Final[CitedConstant[int]] = CitedConstant(
    name="max_peak_window_s",
    value=30,
    source=MAX_SUSTAINED_PEAK_CHOICE,
)

MAX_WINDOW_DAYS: Final[CitedConstant[int]] = CitedConstant(
    name="max_window_days",
    value=365,
    source=MAX_RECENCY_CHOICE,
)

MAX_TOP_SESSIONS: Final[CitedConstant[int]] = CitedConstant(
    name="max_top_sessions",
    value=3,
    source=MAX_RECENCY_CHOICE,
)

MAX_STEP_BPM: Final[CitedConstant[int]] = CitedConstant(
    name="max_step_bpm",
    value=2,
    source=MAX_TIMELINE_CHOICE,
)

ROUNDING_HALF_OFFSET: Final[CitedConstant[float]] = CitedConstant(
    name="rounding_half_offset",
    value=0.5,
    source=ROUNDING_CHOICE,
)

CONSTANT_SOURCES: Final[tuple[CitedConstant[int] | CitedConstant[float], ...]] = (
    RESTING_WINDOW_DAYS,
    RESTING_MIN_VALUES,
    RESTING_STEP_BPM,
    RESTING_CONFIRM_DAYS,
    MAX_PLAUSIBLE_LOW_BPM,
    MAX_PLAUSIBLE_HIGH_BPM,
    MAX_RATE_BPM_PER_S,
    MAX_GAP_S,
    MAX_PEAK_WINDOW_S,
    MAX_WINDOW_DAYS,
    MAX_TOP_SESSIONS,
    MAX_STEP_BPM,
    ROUNDING_HALF_OFFSET,
)

RESTING_RULE: Final[KindRule] = KindRule(
    kind=BenchmarkKind.RESTING_HR_BPM,
    method=HrMethod.RESTING_HR_SERIES_MEDIAN,
    citation_key=RESTING_TIMELINE_CHOICE.key,
    step_bpm=RESTING_STEP_BPM.value,
    confirm_days=RESTING_CONFIRM_DAYS.value,
    rises_only=False,
)

MAX_RULE: Final[KindRule] = KindRule(
    kind=BenchmarkKind.MAX_HR_BPM,
    method=HrMethod.MAX_HR_SUSTAINED_PEAK,
    citation_key=MAX_TIMELINE_CHOICE.key,
    step_bpm=MAX_STEP_BPM.value,
    confirm_days=1,
    rises_only=True,
)

BLOCKED_CITATIONS: Final[frozenset[str]] = frozenset()
