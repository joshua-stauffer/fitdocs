"""Donation units and the base-wins rule (channel-merge Req 2.1-2.8).

A *unit* is the set of ``Samples`` channels donated together: every per-sample
channel but the time offset is its own unit, except latitude and longitude,
which are one position unit. The base keeps a unit it records at any sample;
an extra's values for an open unit are read at the placed indices.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Final

from fitdocs.compose.types import Placement
from fitdocs.model import Samples

POSITION_UNIT: Final[tuple[str, ...]] = ("latitude_deg", "longitude_deg")
"""Latitude and longitude: donated together or not at all (Req 2.4)."""


def _units() -> tuple[tuple[str, ...], ...]:
    units: list[tuple[str, ...]] = []
    for field in dataclasses.fields(Samples):
        if field.name == "time_s" or field.name in POSITION_UNIT[1:]:
            continue
        units.append(POSITION_UNIT if field.name == POSITION_UNIT[0] else (field.name,))
    return tuple(units)


DONATION_UNITS: Final[tuple[tuple[str, ...], ...]] = _units()
"""Every ``Samples`` field but ``time_s``, in field order, position as one
unit at latitude's place (Req 2.8); each channel is in exactly one unit."""


def records(values: Sequence[object | None]) -> bool:
    """Whether any value is not ``None`` (``0`` is a recorded value)."""
    return any(v is not None for v in values)


def base_keeps(unit: tuple[str, ...], base: Samples) -> bool:
    """Whether the base records any channel of ``unit`` at any sample
    (Req 2.1, 2.2)."""
    return any(records(getattr(base, name)) for name in unit)


def placed_values(
    values: Sequence[object | None], placement: Placement
) -> tuple[object | None, ...]:
    """One value per base sample: the extra's value at the placed index, or
    ``None`` where nothing is placed (Req 2.5, 2.6)."""
    return tuple(None if i is None else values[i] for i in placement.extra_index)
