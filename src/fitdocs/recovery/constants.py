"""The recovery method's numeric choices, rules and governing source records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final

from fitdocs.citation import (
    Agreement,
    Citation,
    CitedConstant,
    Corroboration,
    Departure,
    FitdocsChoice,
    SourceRecord,
    VerificationStatus,
)
from fitdocs.wellness import Metric


class Transform(StrEnum):
    """Scale on which the windows are computed."""

    LINEAR = "linear"
    LOG = "log"


@dataclass(frozen=True)
class BaselineMethod:
    """A single metric's transform, windows, minimums and optional range."""

    metric: Metric
    transform: Transform
    rolling_days: int
    min_rolling: int
    baseline_days: int
    min_baseline: int
    range_multiple: float | None


@dataclass(frozen=True)
class MethodRule:
    """A method statement with one governing source and any departures."""

    key: str
    statement: str
    source: SourceRecord
    corroborators: tuple[Corroboration, ...] = ()
    departure: Departure | None = None


PLEWS_2013_SPORTS_MED: Final[Citation] = Citation(
    key="PLEWS_2013_SPORTS_MED",
    authors="Plews DJ, Laursen PB, Stanley J, Kilding AE, Buchheit M",
    year=2013,
    work=(
        "Training adaptation and heart rate variability in elite endurance "
        "athletes: opening the door to effective monitoring. Sports Med. "
        "43(9):773–781. doi:10.1007/s40279-013-0071-8"
    ),
    locator="§3, pp.774–775; §5, pp.779–780",
    verification=VerificationStatus.PRIMARY_TEXT,
)

PLEWS_2014_IJSPP: Final[Citation] = Citation(
    key="PLEWS_2014_IJSPP",
    authors=("Plews DJ, Laursen PB, Le Meur Y, Hausswirth C, Kilding AE, Buchheit M"),
    year=2014,
    work=(
        "Monitoring training with heart-rate variability: how much "
        "compliance is needed for valid assessment? Int J Sports Physiol "
        "Perform. 9(5):783–790. doi:10.1123/IJSPP.2013-0455"
    ),
    locator="abstract, p.783; Practical Applications and Conclusions, p.789",
    verification=VerificationStatus.PRIMARY_TEXT,
)

VESTERINEN_2016: Final[Citation] = Citation(
    key="VESTERINEN_2016",
    authors=(
        "Vesterinen V, Nummela A, Heikura I, Laine T, Hynynen E, Botella J, Häkkinen K"
    ),
    year=2016,
    work=(
        "Individual endurance training prescription with heart rate "
        "variability. Med Sci Sports Exerc. 48(7):1347–1354. "
        "doi:10.1249/MSS.0000000000000910"
    ),
    locator=(
        "Methods, “HRV guided training”, paragraph 2; Discussion, "
        "“Methodological issues to use HRV in training prescription”"
    ),
    verification=VerificationStatus.PRIMARY_TEXT,
)

PLEWS_2013_IJSPP: Final[Citation] = Citation(
    key="PLEWS_2013_IJSPP",
    authors="Plews DJ, Laursen PB, Kilding AE, Buchheit M",
    year=2013,
    work=(
        "Evaluating training adaptation with heart-rate measures: a "
        "methodological comparison. Int J Sports Physiol Perform. "
        "8(6):688–691. doi:10.1123/ijspp.8.6.688"
    ),
    locator=(
        "Experimental Protocol and Statistical Analysis, p.689; Discussion, p.690"
    ),
    verification=VerificationStatus.PRIMARY_TEXT,
)

ROLLING_DAYS: Final[CitedConstant[int]] = CitedConstant(
    name="ROLLING_DAYS",
    value=7,
    source=PLEWS_2013_SPORTS_MED,
    corroborators=(
        Corroboration(
            citation=PLEWS_2013_IJSPP,
            locator="Statistical Analysis, p.689",
            agreement=Agreement.AGREES,
        ),
    ),
)

MIN_ROLLING_VALUES: Final[CitedConstant[int]] = CitedConstant(
    name="MIN_ROLLING_VALUES",
    value=3,
    source=PLEWS_2014_IJSPP,
    departure=Departure(
        subject="MIN_ROLLING_VALUES",
        source_specifies=(
            "Plews 2014, Practical Applications and Conclusions p.789: "
            "three in trained triathletes, approximately five in "
            "recreational athletes"
        ),
        fitdocs_does="Require three present days for each of nine methods",
        reason=(
            "One explicit missingness rule across metrics; no claim that "
            "three establishes validity for every population/signal"
        ),
    ),
)

BASELINE_DAYS: Final[CitedConstant[int]] = CitedConstant(
    name="BASELINE_DAYS",
    value=60,
    source=FitdocsChoice(
        key="BASELINE_DAYS",
        justification=(
            "maintainer's 2026-10-12 decision for a longer personal baseline"
        ),
        search_basis=(
            "six candidates in task 1.1; Altini primary unavailable and no "
            "opened work specifies this 60-day method"
        ),
    ),
    departure=Departure(
        subject="BASELINE_DAYS",
        source_specifies=(
            "Vesterinen 2016, Methods “HRV guided training”, paragraphs "
            "2–3: four-week reference periodically updated"
        ),
        fitdocs_does="Use D−60 through D−1",
        reason=(
            "Approved personal as-of baseline excludes the judged day and "
            "implements the maintainer's longer-window decision"
        ),
    ),
)

MIN_BASELINE_VALUES: Final[CitedConstant[int]] = CitedConstant(
    name="MIN_BASELINE_VALUES",
    value=30,
    source=FitdocsChoice(
        key="MIN_BASELINE_VALUES",
        justification="at least half the 60-day window before estimating variation",
        search_basis="no minimum of 30 found in the five opened works",
    ),
)

RANGE_SD_MULTIPLE: Final[CitedConstant[float]] = CitedConstant(
    name="RANGE_SD_MULTIPLE",
    value=0.5,
    source=VESTERINEN_2016,
    departure=Departure(
        subject="RANGE_SD_MULTIPLE",
        source_specifies=(
            "Vesterinen 2016, Methods “HRV guided training”, paragraphs "
            "1–3: raw RMSSD, four weeks, training prescription"
        ),
        fitdocs_does=(
            "Use 0.5 SD for log HRV and linear resting HR over preceding 60 "
            "days; descriptive marking only"
        ),
        reason=(
            "Preserve approved transparent windows and separate metrics while "
            "keeping the display descriptive"
        ),
    ),
)

CONSTANTS: Final[tuple[CitedConstant[int] | CitedConstant[float], ...]] = (
    ROLLING_DAYS,
    MIN_ROLLING_VALUES,
    BASELINE_DAYS,
    MIN_BASELINE_VALUES,
    RANGE_SD_MULTIPLE,
)

RULES: Final[tuple[MethodRule, ...]] = (
    MethodRule(
        key="LOG_TRANSFORM",
        statement=(
            "HRV is averaged as the natural log of its values and shown back in ms."
        ),
        source=PLEWS_2013_SPORTS_MED,
        corroborators=(
            Corroboration(
                citation=PLEWS_2013_IJSPP,
                locator="Experimental Protocol, p.689",
                agreement=Agreement.AGREES,
            ),
        ),
    ),
    MethodRule(
        key="SDNN_APPLICATION",
        statement="The same method is applied to SDNN, never mixed with rMSSD.",
        source=FitdocsChoice(
            key="SDNN_APPLICATION",
            justification=(
                "display each HRV definition separately with one transparent method"
            ),
            search_basis="opened works study rMSSD, no SDNN counterpart verified",
        ),
        departure=Departure(
            subject="SDNN_APPLICATION",
            source_specifies=(
                "Plews 2013 Sports Med, §3 pp.774–775: preferred index is ln rMSSD"
            ),
            fitdocs_does="Apply log averaging/range independently to SDNN",
            reason=(
                "Show each platform's HRV definition separately without "
                "unsupported SDNN/rMSSD conversion"
            ),
        ),
    ),
    MethodRule(
        key="RESTING_HR_APPLICATION",
        statement=(
            "Resting HR uses the same windows and range on its own values (no log)."
        ),
        source=FitdocsChoice(
            key="RESTING_HR_APPLICATION",
            justification=(
                "one descriptive rolling/baseline comparison on resting "
                "HR's own linear values"
            ),
            search_basis=(
                "Plews 2013 IJSPP and Buchheit discuss averaged HR, but no "
                "identical 60-day/0.5-SD resting-HR method verified"
            ),
        ),
        corroborators=(
            Corroboration(
                citation=PLEWS_2013_IJSPP,
                locator="Discussion, p.690",
                agreement=Agreement.OMITS,
                note=(
                    "supports weekly HR averaging but not fitdocs's full range method"
                ),
            ),
        ),
        departure=Departure(
            subject="RESTING_HR_APPLICATION",
            source_specifies=(
                "Vesterinen 2016, Methods “HRV guided training”: range "
                "applied to RMSSD; Plews 2013 IJSPP Discussion p.690 "
                "supports weekly HR averaging"
            ),
            fitdocs_does=(
                "Apply the approved windows/range to linear resting HR values"
            ),
            reason=(
                "A single explicit descriptive comparison rule; no "
                "published claim of this exact resting-HR range"
            ),
        ),
    ),
    MethodRule(
        key="COMPARED_QUANTITY",
        statement=(
            "A day is marked when its seven-day mean lies outside the normal range."
        ),
        source=replace(PLEWS_2013_SPORTS_MED, locator="Fig.4, p.779; §5, pp.779–780"),
        corroborators=(
            Corroboration(
                citation=VESTERINEN_2016,
                locator="Methods, “HRV guided training”, paragraphs 1–3",
                agreement=Agreement.AGREES,
                note=(
                    "supports comparison of seven-day averages, not "
                    "fitdocs's log/60-day descriptive method"
                ),
            ),
        ),
        departure=Departure(
            subject="COMPARED_QUANTITY",
            source_specifies=(
                "Plews 2013 Sports Med, Fig.4 p.779: weekly ln rMSSD "
                "comparison with individual SWC and confidence intervals"
            ),
            fitdocs_does=(
                "Mark a seven-day mean outside either bound, without confidence "
                "intervals or training instructions"
            ),
            reason=(
                "Describe the athlete's own figures rather than infer "
                "performance, health or training decisions"
            ),
        ),
    ),
    MethodRule(
        key="SAMPLE_SD",
        statement="The SD is the sample SD (n − 1) of the baseline days.",
        source=FitdocsChoice(
            key="SAMPLE_SD",
            justification="n−1 sample estimate of baseline-day variation",
            search_basis="no explicit denominator verified in the opened candidates",
        ),
    ),
    MethodRule(
        key="SLEEP_METHOD",
        statement=("Sleep signals get a seven-day mean and a 60-day mean, no range."),
        source=FitdocsChoice(
            key="SLEEP_METHOD",
            justification=(
                "descriptive recent and longer sleep averages, no "
                "unsupported normal range"
            ),
            search_basis=(
                "no matching sleep-range method verified in the opened HRV works"
            ),
        ),
    ),
    MethodRule(
        key="PER_SOURCE",
        statement="Every computation uses one source and one metric.",
        source=FitdocsChoice(
            key="PER_SOURCE",
            justification=(
                "maintainer's 2026-10-12 decision because platform definitions differ"
            ),
            search_basis=(
                "opened works do not establish comparability of "
                "export-source definitions"
            ),
        ),
    ),
    MethodRule(
        key="SHOWN_SOURCE",
        statement=(
            "The shown source is the day's canonical source, carried for at "
            "most six days; only the source identifier is carried, never "
            "the value."
        ),
        source=FitdocsChoice(
            key="SHOWN_SOURCE",
            justification=(
                "use canonical source and bridge only gaps within the "
                "seven-day rolling window, carrying the source identifier, "
                "never the value"
            ),
            search_basis="no source-carry policy in the opened works",
        ),
    ),
)

BASELINED_METRICS: Final[tuple[Metric, ...]] = (
    Metric.HRV_SDNN_MS,
    Metric.HRV_RMSSD_MS,
    Metric.RESTING_HR_BPM,
)
SLEEP_METRICS: Final[tuple[Metric, ...]] = (
    Metric.SLEEP_S,
    Metric.SLEEP_DEEP_S,
    Metric.SLEEP_LIGHT_S,
    Metric.SLEEP_REM_S,
    Metric.SLEEP_AWAKE_S,
    Metric.SLEEP_HR_BPM,
)
METHODS: Final[Mapping[Metric, BaselineMethod]] = {
    **{
        metric: BaselineMethod(
            metric=metric,
            transform=Transform.LOG
            if metric in (Metric.HRV_SDNN_MS, Metric.HRV_RMSSD_MS)
            else Transform.LINEAR,
            rolling_days=ROLLING_DAYS.value,
            min_rolling=MIN_ROLLING_VALUES.value,
            baseline_days=BASELINE_DAYS.value,
            min_baseline=MIN_BASELINE_VALUES.value,
            range_multiple=RANGE_SD_MULTIPLE.value,
        )
        for metric in BASELINED_METRICS
    },
    **{
        metric: BaselineMethod(
            metric=metric,
            transform=Transform.LINEAR,
            rolling_days=ROLLING_DAYS.value,
            min_rolling=MIN_ROLLING_VALUES.value,
            baseline_days=BASELINE_DAYS.value,
            min_baseline=MIN_BASELINE_VALUES.value,
            range_multiple=None,
        )
        for metric in SLEEP_METRICS
    },
}


def lookback_days(methods: Mapping[Metric, BaselineMethod]) -> int:
    """Calendar days before D needed by the longest configured window."""
    return max(
        max(method.baseline_days, method.rolling_days - 1)
        for method in methods.values()
    )


LOOKBACK_DAYS: Final[int] = lookback_days(METHODS)
BASELINES_VERSION: Final[int] = 1
