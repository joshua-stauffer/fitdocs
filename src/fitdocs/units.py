"""The one unit vocabulary: tokens, index phrases and how each unit is shown.

A leaf module (standard library only) that any layer may import. The analytics
index projects its column-name unit suffixes from `UNITS`; the chart kit reads
the same table to label and format values. Adding or changing a row is a
schema-visible change, never a chart-only change.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class UnitFamily(StrEnum):
    """How a unit's values are formatted."""

    QUANTITY = "quantity"  # number then symbol
    DURATION = "duration"  # seconds shown as h:mm:ss / m:ss
    PACE = "pace"  # seconds per km shown as m:ss
    PERCENT = "percent"  # number then "%"
    CLOCK = "clock"  # marks a date or date-time column's time basis


@dataclass(frozen=True)
class Unit:
    token: str  # suffix without "_"
    phrase: str  # the index's unit phrase (descriptions must contain it)
    symbol: str  # axis-title and value symbol
    family: UnitFamily
    decimals: int  # value-label decimals for QUANTITY and PERCENT floats
    spaced: bool = True  # "12 km" vs "45°"

    @property
    def suffix(self) -> str:
        return "_" + self.token


# Order is load-bearing for overlapping suffixes: the most specific comes
# first (`_s_per_km` before `_km`, `_kn_m` before `_m`). Non-overlapping
# additions append without changing the preceding rows.
UNITS: Final[tuple[Unit, ...]] = (
    Unit("s_per_km", "seconds per kilometre", "min/km", UnitFamily.PACE, 0),
    Unit("local", "local", "local time", UnitFamily.CLOCK, 0),
    Unit("kn_m", "kilonewtons per metre", "kN/m", UnitFamily.QUANTITY, 1),
    Unit("kcal", "kilocalories", "kcal", UnitFamily.QUANTITY, 0),
    Unit("mps", "metres per second", "m/s", UnitFamily.QUANTITY, 2),
    Unit("bpm", "beats per minute", "bpm", UnitFamily.QUANTITY, 0),
    Unit("rpm", "revolutions per minute", "rpm", UnitFamily.QUANTITY, 0),
    Unit("deg", "degrees", "°", UnitFamily.QUANTITY, 1, spaced=False),
    Unit("pct", "percent", "%", UnitFamily.PERCENT, 1, spaced=False),
    Unit("utc", "UTC", "UTC", UnitFamily.CLOCK, 0),
    Unit("mm", "millimetres", "mm", UnitFamily.QUANTITY, 0),
    Unit("ms", "milliseconds", "ms", UnitFamily.QUANTITY, 0),
    Unit("bw", "body weights", "BW", UnitFamily.QUANTITY, 2),
    Unit("kg", "kilograms", "kg", UnitFamily.QUANTITY, 1),
    Unit("km", "kilometres", "km", UnitFamily.QUANTITY, 1),
    Unit("m", "metres", "m", UnitFamily.QUANTITY, 0),
    Unit("s", "seconds", "h:mm:ss", UnitFamily.DURATION, 0),
    Unit("w", "watts", "W", UnitFamily.QUANTITY, 0),
    Unit("c", "degrees Celsius", "°C", UnitFamily.QUANTITY, 1),
    Unit(
        "ml_per_kg_min",
        "millilitres per kilogram per minute",
        "mL/kg/min",
        UnitFamily.QUANTITY,
        1,
    ),
    Unit("brpm", "breaths per minute", "br/min", UnitFamily.QUANTITY, 1),
)


def unit_for_column(name: str) -> Unit | None:
    """The first unit (in table order) whose suffix the column name ends with."""
    for unit in UNITS:
        if name.endswith(unit.suffix):
            return unit
    return None


def unit_named(token: str) -> Unit | None:
    """The unit with exactly this token, or `None`."""
    for unit in UNITS:
        if unit.token == token:
            return unit
    return None
