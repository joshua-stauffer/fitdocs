"""Records for the duration set and continuity limit used by mean-max metrics."""

from __future__ import annotations

from typing import Final

from fitdocs.citation import CitedConstant, FitdocsChoice

_SEARCH_BASIS: Final[str] = (
    "Live searches used these query phrases: mean maximal power curve duration "
    "set 1 second 5 seconds 10 seconds 6 hours best efforts; mean maximal "
    "curve pauses gaps moving average duration maximal power published study; "
    "site:pubmed.ncbi.nlm.nih.gov mean maximal power curve durations cycling "
    "1 s 5 s 6 h; mean maximal power gaps cycling curve power data; "
    "site:jsc-journal.com mean maximal power curve duration cycling; mean "
    "maximal power profile cyclists durations 1s 5s 10s 1 hour research; "
    "cycling maximal mean power gap duration samples excluded missing data; "
    "mean maximal power cycling missing data gaps rolling average; cycling "
    "mean maximal power record power profile sampling interval missing samples "
    "duration set 1 s 5 s 6 h study; and power curve cycling maximum gap "
    "interpolation rolling mean power best effort duration. "
    'Strava Help, "How Does the Power Curve Work '
    'for Cycling on Strava?" (https://support.strava.com/en-us/articles/'
    "15401647-how-does-the-power-curve-work-for-cycling), "
    "describes a curve for every covered interval and separately lists nine "
    "Best Efforts intervals; it gives no continuity-gap threshold. TrainingPeaks, "
    '"All About the Mean Max Power Curve" '
    "(https://www.trainingpeaks.com/coach-blog/all-about-the-mean-max-power-curve/), "
    "describes commonly tested durations and its newer nearly-every-duration "
    "curve, but does not define a standard 28-duration set or a gap threshold. "
    'The peer-reviewed study "Power Profile of Top 5 Results in World Tour '
    'Cycling Races" (https://pubmed.ncbi.nlm.nih.gov/34560671/) analyzes '
    "study-selected durations over 5 seconds to 60 minutes; it does not define "
    "a general duration ladder or a gap threshold. Searches for an MMP "
    "continuity, missing-sample, or dropout rule found no published maximum "
    "step for a mean-max curve. These sources therefore do not define either "
    "value recorded here."
)


MEAN_MAX_DURATIONS_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="mean_max_durations_choice",
    justification=(
        "The duration set is a near-logarithmic ladder from a one-second peak "
        "to six hours, with greater density at shorter durations and around "
        "threshold tests. It includes the 900-second, 1200-second and "
        "3600-second durations named by fitdocs's threshold derivations, and "
        "uses the same set for every page and channel so their curves compare."
    ),
    search_basis=_SEARCH_BASIS,
    measurement=None,
)

MEAN_MAX_MAX_STEP_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="mean_max_max_step_choice",
    justification=(
        "A gap breaks a best-effort window and loses data, unlike alignment in "
        "compose/stretches.py, which uses a one-second step. A five-second "
        "maximum step bridges brief dropouts and irregular recording while "
        "holding at most four seconds of a recorded value per step; a longer "
        "stop still breaks continuity when recording is paused."
    ),
    search_basis=_SEARCH_BASIS,
    measurement=None,
)

MEAN_MAX_DURATION_1_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_1_s", 1, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_5_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_5_s", 5, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_10_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_10_s", 10, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_15_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_15_s", 15, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_20_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_20_s", 20, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_30_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_30_s", 30, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_45_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_45_s", 45, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_60_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_60_s", 60, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_120_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_120_s", 120, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_180_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_180_s", 180, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_240_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_240_s", 240, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_300_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_300_s", 300, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_360_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_360_s", 360, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_480_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_480_s", 480, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_600_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_600_s", 600, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_720_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_720_s", 720, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_900_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_900_s", 900, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_1200_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_1200_s", 1200, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_1800_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_1800_s", 1800, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_2400_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_2400_s", 2400, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_2700_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_2700_s", 2700, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_3600_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_3600_s", 3600, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_5400_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_5400_s", 5400, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_7200_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_7200_s", 7200, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_10800_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_10800_s", 10800, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_14400_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_14400_s", 14400, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_18000_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_18000_s", 18000, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATION_21600_S: Final[CitedConstant[int]] = CitedConstant(
    "mean_max_duration_21600_s", 21600, MEAN_MAX_DURATIONS_CHOICE
)

MEAN_MAX_DURATIONS_S: Final[tuple[CitedConstant[int], ...]] = (
    MEAN_MAX_DURATION_1_S,
    MEAN_MAX_DURATION_5_S,
    MEAN_MAX_DURATION_10_S,
    MEAN_MAX_DURATION_15_S,
    MEAN_MAX_DURATION_20_S,
    MEAN_MAX_DURATION_30_S,
    MEAN_MAX_DURATION_45_S,
    MEAN_MAX_DURATION_60_S,
    MEAN_MAX_DURATION_120_S,
    MEAN_MAX_DURATION_180_S,
    MEAN_MAX_DURATION_240_S,
    MEAN_MAX_DURATION_300_S,
    MEAN_MAX_DURATION_360_S,
    MEAN_MAX_DURATION_480_S,
    MEAN_MAX_DURATION_600_S,
    MEAN_MAX_DURATION_720_S,
    MEAN_MAX_DURATION_900_S,
    MEAN_MAX_DURATION_1200_S,
    MEAN_MAX_DURATION_1800_S,
    MEAN_MAX_DURATION_2400_S,
    MEAN_MAX_DURATION_2700_S,
    MEAN_MAX_DURATION_3600_S,
    MEAN_MAX_DURATION_5400_S,
    MEAN_MAX_DURATION_7200_S,
    MEAN_MAX_DURATION_10800_S,
    MEAN_MAX_DURATION_14400_S,
    MEAN_MAX_DURATION_18000_S,
    MEAN_MAX_DURATION_21600_S,
)

MEAN_MAX_MAX_STEP_S: Final[CitedConstant[float]] = CitedConstant(
    "mean_max_max_step_s", 5.0, MEAN_MAX_MAX_STEP_CHOICE
)

MEAN_MAX_SOURCES: Final[tuple[CitedConstant[int] | CitedConstant[float], ...]] = (
    *MEAN_MAX_DURATIONS_S,
    MEAN_MAX_MAX_STEP_S,
)
