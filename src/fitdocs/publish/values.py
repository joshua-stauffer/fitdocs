"""A workout page's managed values as fixed-format text (publish-core Req 5.1-5.5).

Each value is text produced from what a ``fitdocs.contract`` reader returns for
the page, or ``None``.  ``None`` means the page has no such value, and it is
not rendered as ``"0"``, an empty string or any other default.  The three text
values (title, sport and load methodology) are passed on verbatim, without
stripping, unless they hold a control character or a line or paragraph
separator; then they have no value, and a methodology with no value or only
whitespace takes the load value with it.  A figure the page records as zero is
rendered as zero.  Miles, pace and speed are derived by fixed arithmetic, and
only from present, positive, finite inputs, so a zero input gives them no
value.  The module imports the contract and the standard library.
"""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Mapping
from typing import Final

from fitdocs.contract import (
    DATE_KEY,
    SPORT_KEY,
    START_TIME_KEY,
    document_date,
    document_load,
    document_modality,
    document_source_identity,
    document_sport,
    document_start_time,
    document_summary,
)

#: The placeholder names, in the order the design publishes them.
PLACEHOLDERS: Final[tuple[str, ...]] = (
    "title",
    SPORT_KEY,
    DATE_KEY,
    START_TIME_KEY,
    "distance_km",
    "distance_mi",
    "moving_time",
    "elapsed_time",
    "pace_per_km",
    "pace_per_mi",
    "speed_kmh",
    "avg_hr_bpm",
    "avg_power_w",
    "elevation_gain_m",
    "calories_kcal",
    "load_value",
    "load_methodology",
)

KM_PER_MILE: Final[float] = 1.609344

_RUN: Final = "run"
_BIKE: Final = "bike"
_SECONDS_PER_HOUR: Final = 3600


def format_duration(seconds: float) -> str:
    """``h:mm:ss`` from one hour up, else ``m:ss``; seconds rounded to whole."""
    total = round(seconds)
    if total >= _SECONDS_PER_HOUR:
        hours, rem = divmod(total, _SECONDS_PER_HOUR)
        minutes, secs = divmod(rem, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


#: Unicode categories a single-line text value may not hold: control
#: characters, and the line and paragraph separators.
_NOT_SINGLE_LINE: Final = frozenset({"Cc", "Zl", "Zp"})


def has_control_character(text: str) -> bool:
    return any(unicodedata.category(ch) in _NOT_SINGLE_LINE for ch in text)


def _verbatim(text: str | None) -> str | None:
    """``text`` unchanged unless it is absent or is not single-line text."""
    if text is None or has_control_character(text):
        return None
    return text


def _duration(seconds: float | None) -> str | None:
    return None if seconds is None else format_duration(seconds)


def _two_decimals(number: float | None) -> str | None:
    return None if number is None else f"{number:.2f}"


def _integer(number: int | None) -> str | None:
    return None if number is None else str(number)


def _positive(number: float | None) -> float | None:
    """``number`` when it is a finite number above zero, else ``None``."""
    if number is None or not math.isfinite(number) or number <= 0:
        return None
    return number


def _pace(seconds: float | None, distance: float | None) -> str | None:
    """``m:ss`` per unit of distance from positive time and distance."""
    time_s, length = _positive(seconds), _positive(distance)
    if time_s is None or length is None:
        return None
    per_unit = _positive(time_s / length)
    if per_unit is None:
        return None
    minutes, secs = divmod(round(per_unit), 60)
    return f"{minutes}:{secs:02d}"


def _speed_kmh(distance_km: float | None, seconds: float | None) -> str | None:
    km, time_s = _positive(distance_km), _positive(seconds)
    if km is None or time_s is None:
        return None
    speed = km / (time_s / _SECONDS_PER_HOUR)
    return f"{speed:.1f}" if math.isfinite(speed) else None


def page_values(frontmatter: Mapping[str, object]) -> Mapping[str, str | None]:
    """Every placeholder's text for the page, or ``None`` where it has no value."""
    summary = document_summary(frontmatter)
    identity = document_source_identity(frontmatter)
    load = document_load(frontmatter)
    day = document_date(frontmatter)
    start = document_start_time(frontmatter)
    modality = document_modality(frontmatter)

    distance_km = summary.distance_km
    distance_mi = (
        distance_km / KM_PER_MILE
        if distance_km is not None and distance_km > 0
        else None
    )
    ride = modality == _BIKE
    run = modality == _RUN
    usable_load = (
        load
        if load is not None
        and load.value >= 0
        and load.methodology.strip()
        and _verbatim(load.methodology) is not None
        else None
    )

    values: dict[str, str | None] = {
        "title": _verbatim(summary.title),
        SPORT_KEY: _verbatim(document_sport(frontmatter)),
        DATE_KEY: None if day is None else day.isoformat(),
        START_TIME_KEY: None if start is None else start.strftime("%H:%M"),
        "distance_km": _two_decimals(distance_km),
        "distance_mi": _two_decimals(distance_mi),
        "moving_time": _duration(summary.moving_time_s),
        "elapsed_time": _duration(identity.elapsed_s),
        "pace_per_km": _pace(summary.moving_time_s, distance_km) if run else None,
        "pace_per_mi": _pace(summary.moving_time_s, distance_mi) if run else None,
        "speed_kmh": _speed_kmh(distance_km, summary.moving_time_s) if ride else None,
        "avg_hr_bpm": _integer(summary.avg_hr_bpm),
        "avg_power_w": _integer(summary.avg_power_w),
        "elevation_gain_m": (
            None
            if summary.elevation_gain_m is None
            else f"{summary.elevation_gain_m:.0f}"
        ),
        "calories_kcal": _integer(summary.calories_kcal),
        "load_value": None if usable_load is None else f"{usable_load.value + 0.0:.0f}",
        "load_methodology": (None if usable_load is None else usable_load.methodology),
    }
    return {name: values[name] for name in PLACEHOLDERS}
