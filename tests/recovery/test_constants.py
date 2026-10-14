"""Recovery's approved method configuration and citation records."""

from __future__ import annotations

import re
from dataclasses import FrozenInstanceError, asdict, replace

import pytest

from fitdocs.citation import (
    Citation,
    CitedConstant,
    FitdocsChoice,
    SourceRecord,
    VerificationStatus,
)
from fitdocs.recovery import constants as c
from fitdocs.wellness import Metric

_EXPECTED_METHODS = (
    ("hrv_sdnn_ms", "log", 7, 3, 60, 30, 0.5),
    ("hrv_rmssd_ms", "log", 7, 3, 60, 30, 0.5),
    ("resting_hr_bpm", "linear", 7, 3, 60, 30, 0.5),
    ("sleep_s", "linear", 7, 3, 60, 30, None),
    ("sleep_deep_s", "linear", 7, 3, 60, 30, None),
    ("sleep_light_s", "linear", 7, 3, 60, 30, None),
    ("sleep_rem_s", "linear", 7, 3, 60, 30, None),
    ("sleep_awake_s", "linear", 7, 3, 60, 30, None),
    ("sleep_hr_bpm", "linear", 7, 3, 60, 30, None),
)


def test_methods_match_the_normative_table() -> None:
    assert (
        tuple(
            (
                str(metric),
                str(method.transform),
                method.rolling_days,
                method.min_rolling,
                method.baseline_days,
                method.min_baseline,
                method.range_multiple,
            )
            for metric, method in c.METHODS.items()
        )
        == _EXPECTED_METHODS
    )


def test_method_keys_match_their_records() -> None:
    assert tuple(c.METHODS) == tuple(method.metric for method in c.METHODS.values())


def test_metric_selections() -> None:
    assert tuple(map(str, c.BASELINED_METRICS)) == (
        "hrv_sdnn_ms",
        "hrv_rmssd_ms",
        "resting_hr_bpm",
    )
    assert tuple(map(str, c.SLEEP_METRICS)) == (
        "sleep_s",
        "sleep_deep_s",
        "sleep_light_s",
        "sleep_rem_s",
        "sleep_awake_s",
        "sleep_hr_bpm",
    )


def test_constants_and_rules_have_unique_keys() -> None:
    assert len({record.name for record in c.CONSTANTS}) == len(c.CONSTANTS)
    assert len({record.key for record in c.RULES}) == len(c.RULES)


def test_constant_values_and_order() -> None:
    assert tuple((record.name, record.value) for record in c.CONSTANTS) == (
        ("ROLLING_DAYS", 7),
        ("MIN_ROLLING_VALUES", 3),
        ("BASELINE_DAYS", 60),
        ("MIN_BASELINE_VALUES", 30),
        ("RANGE_SD_MULTIPLE", 0.5),
    )


def test_rule_keys_and_order() -> None:
    assert tuple(record.key for record in c.RULES) == (
        "LOG_TRANSFORM",
        "SDNN_APPLICATION",
        "RESTING_HR_APPLICATION",
        "COMPARED_QUANTITY",
        "SAMPLE_SD",
        "SLEEP_METHOD",
        "PER_SOURCE",
        "SHOWN_SOURCE",
    )


def _check_source(source: SourceRecord) -> None:
    if isinstance(source, Citation):
        assert source.verification is VerificationStatus.PRIMARY_TEXT
        assert source.locator
    else:
        assert source.justification.strip()
        assert source.search_basis.strip()


def test_real_governing_records() -> None:
    for record in (*c.CONSTANTS, *c.RULES):
        _check_source(record.source)


@pytest.mark.parametrize("invalid", ["locator", "verification"])
def test_record_check_rejects_invalid_citations(invalid: str) -> None:
    source = Citation(
        "synthetic",
        "Synthetic author",
        2000,
        "Synthetic work",
        "Synthetic section",
        VerificationStatus.PRIMARY_TEXT,
    )
    bad = (
        replace(source, locator=None)
        if invalid == "locator"
        else replace(source, verification=VerificationStatus.SECONDARY_ATTESTATION)
    )
    with pytest.raises(AssertionError):
        _check_source(bad)


@pytest.mark.parametrize("invalid", ["justification", "search_basis"])
def test_record_check_rejects_empty_choices(invalid: str) -> None:
    source = FitdocsChoice("synthetic", "Synthetic reason", "Synthetic search")
    bad = (
        replace(source, justification=" ")
        if invalid == "justification"
        else replace(source, search_basis=" ")
    )
    with pytest.raises(AssertionError):
        _check_source(bad)


def test_lookback_and_version() -> None:
    assert (c.LOOKBACK_DAYS, c.lookback_days(c.METHODS), c.BASELINES_VERSION) == (
        60,
        60,
        1,
    )


@pytest.mark.parametrize("rolling, baseline, expected", [(70, 20, 69), (8, 83, 83)])
def test_lookback_uses_both_windows(rolling: int, baseline: int, expected: int) -> None:
    method = c.BaselineMethod(
        Metric.SLEEP_S, c.Transform.LINEAR, rolling, 3, baseline, 10, None
    )
    assert c.lookback_days({Metric.SLEEP_S: method}) == expected


@pytest.mark.parametrize("kind", ["method", "rule"])
def test_method_records_are_frozen(kind: str) -> None:
    record = next(iter(c.METHODS.values())) if kind == "method" else c.RULES[0]
    with pytest.raises(FrozenInstanceError):
        setattr(record, "metric" if kind == "method" else "statement", "changed")


_EXPECTED_CITATIONS = {
    "ROLLING_DAYS": (
        "PLEWS_2013_SPORTS_MED",
        "Plews DJ, Laursen PB, Stanley J, Kilding AE, Buchheit M",
        2013,
        "Training adaptation and heart rate variability in elite endurance athletes: "
        "opening the door to effective monitoring. Sports Med. 43(9):773–781. "
        "doi:10.1007/s40279-013-0071-8",
        "§3, pp.774–775; §5, pp.779–780",
        "primary_text",
        None,
    ),
    "MIN_ROLLING_VALUES": (
        "PLEWS_2014_IJSPP",
        "Plews DJ, Laursen PB, Le Meur Y, Hausswirth C, Kilding AE, Buchheit M",
        2014,
        "Monitoring training with heart-rate variability: how much compliance is "
        "needed for valid assessment? Int J Sports Physiol Perform. 9(5):783–790. "
        "doi:10.1123/IJSPP.2013-0455",
        "abstract, p.783; Practical Applications and Conclusions, p.789",
        "primary_text",
        None,
    ),
    "RANGE_SD_MULTIPLE": (
        "VESTERINEN_2016",
        "Vesterinen V, Nummela A, Heikura I, Laine T, Hynynen E, Botella J, Häkkinen K",
        2016,
        "Individual endurance training prescription with heart rate variability. "
        "Med Sci Sports Exerc. 48(7):1347–1354. doi:10.1249/MSS.0000000000000910",
        "Methods, “HRV guided training”, paragraph 2; Discussion, "
        "“Methodological issues to use HRV in training prescription”",
        "primary_text",
        None,
    ),
    "LOG_TRANSFORM": (
        "PLEWS_2013_SPORTS_MED",
        "Plews DJ, Laursen PB, Stanley J, Kilding AE, Buchheit M",
        2013,
        "Training adaptation and heart rate variability in elite endurance athletes: "
        "opening the door to effective monitoring. Sports Med. 43(9):773–781. "
        "doi:10.1007/s40279-013-0071-8",
        "§3, pp.774–775; §5, pp.779–780",
        "primary_text",
        None,
    ),
    "COMPARED_QUANTITY": (
        "PLEWS_2013_SPORTS_MED",
        "Plews DJ, Laursen PB, Stanley J, Kilding AE, Buchheit M",
        2013,
        "Training adaptation and heart rate variability in elite endurance athletes: "
        "opening the door to effective monitoring. Sports Med. 43(9):773–781. "
        "doi:10.1007/s40279-013-0071-8",
        "Fig.4, p.779; §5, pp.779–780",
        "primary_text",
        None,
    ),
}
_EXPECTED_CHOICES = {
    "BASELINE_DAYS": (
        "maintainer's 2026-10-12 decision for a longer personal baseline",
        "six candidates in task 1.1; Altini primary unavailable and no opened work "
        "specifies this 60-day method",
    ),
    "MIN_BASELINE_VALUES": (
        "at least half the 60-day window before estimating variation",
        "no minimum of 30 found in the five opened works",
    ),
    "SDNN_APPLICATION": (
        "display each HRV definition separately with one transparent method",
        "opened works study rMSSD, no SDNN counterpart verified",
    ),
    "RESTING_HR_APPLICATION": (
        "one descriptive rolling/baseline comparison on resting HR's own linear values",
        "Plews 2013 IJSPP and Buchheit discuss averaged HR, but no identical "
        "60-day/0.5-SD resting-HR method verified",
    ),
    "SAMPLE_SD": (
        "n−1 sample estimate of baseline-day variation",
        "no explicit denominator verified in the opened candidates",
    ),
    "SLEEP_METHOD": (
        "descriptive recent and longer sleep averages, no unsupported normal range",
        "no matching sleep-range method verified in the opened HRV works",
    ),
    "PER_SOURCE": (
        "maintainer's 2026-10-12 decision because platform definitions differ",
        "opened works do not establish comparability of export-source definitions",
    ),
    "SHOWN_SOURCE": (
        "use canonical source and bridge only gaps within the seven-day "
        "rolling window, "
        "carrying the source identifier, never the value",
        "no source-carry policy in the opened works",
    ),
}
_EXPECTED_DEPARTURES = {
    "MIN_ROLLING_VALUES": (
        "Plews 2014, Practical Applications and Conclusions p.789: three in trained "
        "triathletes, approximately five in recreational athletes",
        "Require three present days for each of nine methods",
        "One explicit missingness rule across metrics; no claim that three establishes "
        "validity for every population/signal",
    ),
    "BASELINE_DAYS": (
        "Vesterinen 2016, Methods “HRV guided training”, paragraphs 2–3: "
        "four-week reference periodically updated",
        "Use D−60 through D−1",
        "Approved personal as-of baseline excludes the judged day and implements "
        "the maintainer's longer-window decision",
    ),
    "RANGE_SD_MULTIPLE": (
        "Vesterinen 2016, Methods “HRV guided training”, paragraphs 1–3: "
        "raw RMSSD, four weeks, training prescription",
        "Use 0.5 SD for log HRV and linear resting HR over preceding 60 days; "
        "descriptive marking only",
        "Preserve approved transparent windows and separate metrics while keeping "
        "the display descriptive",
    ),
    "SDNN_APPLICATION": (
        "Plews 2013 Sports Med, §3 pp.774–775: preferred index is ln rMSSD",
        "Apply log averaging/range independently to SDNN",
        "Show each platform's HRV definition separately without unsupported "
        "SDNN/rMSSD conversion",
    ),
    "RESTING_HR_APPLICATION": (
        "Vesterinen 2016, Methods “HRV guided training”: range applied to RMSSD; "
        "Plews 2013 IJSPP Discussion p.690 supports weekly HR averaging",
        "Apply the approved windows/range to linear resting HR values",
        "A single explicit descriptive comparison rule; no published claim of "
        "this exact resting-HR range",
    ),
    "COMPARED_QUANTITY": (
        "Plews 2013 Sports Med, Fig.4 p.779: weekly ln rMSSD comparison with "
        "individual SWC and confidence intervals",
        "Mark a seven-day mean outside either bound, without confidence "
        "intervals or training instructions",
        "Describe the athlete's own figures rather than infer performance, health or "
        "training decisions",
    ),
}
_EXPECTED_STATEMENTS = {
    "LOG_TRANSFORM": "HRV is averaged as the natural log of its values "
    "and shown back in ms.",
    "SDNN_APPLICATION": "The same method is applied to SDNN, never mixed with rMSSD.",
    "RESTING_HR_APPLICATION": "Resting HR uses the same windows and range on its own "
    "values (no log).",
    "COMPARED_QUANTITY": "A day is marked when its seven-day mean lies outside the "
    "normal range.",
    "SAMPLE_SD": "The SD is the sample SD (n − 1) of the baseline days.",
    "SLEEP_METHOD": "Sleep signals get a seven-day mean and a 60-day mean, no range.",
    "PER_SOURCE": "Every computation uses one source and one metric.",
    "SHOWN_SOURCE": "The shown source is the day's canonical source, carried for at "
    "most six days; only the source identifier is carried, never the value.",
}
_EXPECTED_CORROBORATORS = {
    "ROLLING_DAYS": (
        ("PLEWS_2013_IJSPP", "Statistical Analysis, p.689", "agrees", None),
    ),
    "LOG_TRANSFORM": (
        ("PLEWS_2013_IJSPP", "Experimental Protocol, p.689", "agrees", None),
    ),
    "RESTING_HR_APPLICATION": (
        (
            "PLEWS_2013_IJSPP",
            "Discussion, p.690",
            "omits",
            "supports weekly HR averaging but not fitdocs's full range method",
        ),
    ),
    "COMPARED_QUANTITY": (
        (
            "VESTERINEN_2016",
            "Methods, “HRV guided training”, paragraphs 1–3",
            "agrees",
            "supports comparison of seven-day averages, not fitdocs's log/60-day "
            "descriptive method",
        ),
    ),
}


def _records() -> dict[str, CitedConstant[int] | CitedConstant[float] | c.MethodRule]:
    return {**{r.name: r for r in c.CONSTANTS}, **{r.key: r for r in c.RULES}}


@pytest.mark.parametrize("key, expected", _EXPECTED_CITATIONS.items())
def test_approved_citation_metadata(key: str, expected: tuple[object, ...]) -> None:
    source = _records()[key].source
    assert tuple(asdict(source).values()) == expected


@pytest.mark.parametrize("key, expected", _EXPECTED_CHOICES.items())
def test_approved_choice_metadata(key: str, expected: tuple[str, str]) -> None:
    source = _records()[key].source
    assert asdict(source) == {
        "key": key,
        "justification": expected[0],
        "search_basis": expected[1],
        "measurement": None,
        "verification": "fitdocs_measured",
    }


@pytest.mark.parametrize(
    "key",
    (
        "ROLLING_DAYS",
        "MIN_ROLLING_VALUES",
        "BASELINE_DAYS",
        "MIN_BASELINE_VALUES",
        "RANGE_SD_MULTIPLE",
        "LOG_TRANSFORM",
        "SDNN_APPLICATION",
        "RESTING_HR_APPLICATION",
        "COMPARED_QUANTITY",
        "SAMPLE_SD",
        "SLEEP_METHOD",
        "PER_SOURCE",
        "SHOWN_SOURCE",
    ),
)
def test_approved_departures_and_corroborators(key: str) -> None:
    record = _records()[key]
    departure = record.departure
    expected = _EXPECTED_DEPARTURES.get(key)
    assert (tuple(asdict(departure).values()) if departure else None) == (
        (key, *expected) if expected else None
    )
    assert tuple(
        (item.citation.key, item.locator, str(item.agreement), item.note)
        for item in record.corroborators
    ) == _EXPECTED_CORROBORATORS.get(key, ())


@pytest.mark.parametrize("key, statement", _EXPECTED_STATEMENTS.items())
def test_approved_rule_statements(key: str, statement: str) -> None:
    assert next(rule.statement for rule in c.RULES if rule.key == key) == statement


@pytest.mark.parametrize("reverse", [False, True])
def test_lookback_takes_the_longest_method(reverse: bool) -> None:
    methods = [
        c.BaselineMethod(Metric.SLEEP_S, c.Transform.LINEAR, 70, 3, 20, 10, None),
        c.BaselineMethod(Metric.SLEEP_HR_BPM, c.Transform.LINEAR, 8, 3, 83, 10, None),
    ]
    if reverse:
        methods.reverse()
    assert c.lookback_days({method.metric: method for method in methods}) == 83


_EXPECTED_CORROBORATING_CITATIONS = {
    "PLEWS_2013_IJSPP": (
        "PLEWS_2013_IJSPP",
        "Plews DJ, Laursen PB, Kilding AE, Buchheit M",
        2013,
        "Evaluating training adaptation with heart-rate measures: a methodological "
        "comparison. Int J Sports Physiol Perform. 8(6):688–691. "
        "doi:10.1123/ijspp.8.6.688",
        "Experimental Protocol and Statistical Analysis, p.689; Discussion, p.690",
        "primary_text",
        None,
    ),
    "VESTERINEN_2016": (
        "VESTERINEN_2016",
        "Vesterinen V, Nummela A, Heikura I, Laine T, Hynynen E, Botella J, Häkkinen K",
        2016,
        "Individual endurance training prescription with heart rate variability. "
        "Med Sci Sports Exerc. 48(7):1347–1354. doi:10.1249/MSS.0000000000000910",
        "Methods, “HRV guided training”, paragraph 2; Discussion, "
        "“Methodological issues to use HRV in training prescription”",
        "primary_text",
        None,
    ),
}


@pytest.mark.parametrize("key, wrappers", _EXPECTED_CORROBORATORS.items())
def test_full_corroborating_citation_metadata(
    key: str, wrappers: tuple[tuple[object, ...], ...]
) -> None:
    assert tuple(
        tuple(asdict(item.citation).values()) for item in _records()[key].corroborators
    ) == tuple(
        _EXPECTED_CORROBORATING_CITATIONS[str(wrapper[0])] for wrapper in wrappers
    )


_PRINTABLE_METADATA_PATTERN = re.compile(
    r"\b(readiness|ready|verdicts?|overload\w*|recommend\w*|forecast\w*|scores?|"
    r"status|advice|advis\w*|should|warn\w*)\b",
    re.IGNORECASE,
)


def _source_text(source: SourceRecord) -> list[str]:
    if isinstance(source, Citation):
        return [source.authors, str(source.year), source.work, source.locator or ""]
    return [source.justification]


def _printable_metadata() -> str:
    fields: list[str] = []
    for record in (*c.CONSTANTS, *c.RULES):
        fields.extend(_source_text(record.source))
        if isinstance(record, c.MethodRule):
            fields.append(record.statement)
        for item in record.corroborators:
            fields.extend(_source_text(item.citation))
            fields.extend([item.locator, str(item.citation.verification)])
            if item.note is not None:
                fields.append(item.note)
        if record.departure is not None:
            fields.extend(
                [
                    record.departure.source_specifies,
                    record.departure.fitdocs_does,
                    record.departure.reason,
                ]
            )
    return "\n".join(fields)


def _check_printable(text: str) -> None:
    assert text
    assert _PRINTABLE_METADATA_PATTERN.search(text) is None


def test_printable_metadata_matches_descriptive_page_guard() -> None:
    _check_printable(_printable_metadata())


@pytest.mark.parametrize(
    "term",
    [
        "readiness",
        "ready",
        "verdict",
        "verdicts",
        "overload",
        "overloaded",
        "recommend",
        "recommendations",
        "forecast",
        "forecasts",
        "score",
        "scores",
        "status",
        "advice",
        "advisor",
        "should",
        "warn",
        "warnings",
        "READY",
    ],
)
def test_printable_guard_rejects_forbidden_terms(term: str) -> None:
    with pytest.raises(AssertionError):
        _check_printable(f"Synthetic {term} text")


def test_printable_guard_rejects_empty_text() -> None:
    with pytest.raises(AssertionError):
        _check_printable("")
