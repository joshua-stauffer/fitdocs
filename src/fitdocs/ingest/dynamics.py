"""Running-dynamics channel policy: record values -> the twelve dynamics channels.

The one table set that decides where each of :data:`fitdocs.model.DYNAMICS_CHANNELS`
comes from and when a recorded value means "no reading" (running-dynamics 3.1-3.3,
4.1-4.4, 5.2-5.4, 5.6):

- five channels come from native ``record`` fields (:data:`NATIVE_DYNAMICS_FIELDS`);
- seven come from record-level developer fields recognised by EXACT name
  (:data:`DEVELOPER_DYNAMICS_NAMES`) -- no case folding, no prefix match, no look
  at the writing application, the description's units or its native slots;
- a recorded ``0`` of seven channels is a device's "no reading" placeholder
  (:data:`PLACEHOLDER_ZERO_CHANNELS`) and becomes ``None``;
- each of the other five (balances and air power) is a *real* value at ``0`` but
  meaningless beside a missing partner, so it is ``None`` exactly where its gate
  channel is ``None`` (:data:`GATES`). Gates are read after the placeholder rule,
  per sample.

Absent stays ``None``; nothing here fabricates a value. A native value is read with
the strict :func:`fitdocs.ingest._fields.float_or_none` (a non-numeric one raises
:class:`TypeError`, as every other native channel does); a recognised developer
value that is not a real number (a tuple, a string, a ``bool``) is ``None``.

``records`` imports this module; this module never imports ``records``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from fitdocs.ingest._fields import float_or_none
from fitdocs.model import DYNAMICS_CHANNELS, DeveloperChannel

NATIVE_DYNAMICS_FIELDS: Final[Mapping[str, str]] = {
    "stance_time_ms": "stance_time",
    "stance_time_balance_pct": "stance_time_balance",
    "vertical_oscillation_mm": "vertical_oscillation",
    "vertical_ratio_pct": "vertical_ratio",
    "step_length_mm": "step_length",
}
"""Channel -> the native FIT ``record`` field it is read from."""

DEVELOPER_DYNAMICS_NAMES: Final[Mapping[str, str]] = {
    "Vertical Oscillation Balance": "vertical_oscillation_balance_pct",
    "Leg Spring Stiffness": "leg_spring_stiffness_kn_m",
    "Leg Spring Stiffness Balance": "leg_spring_stiffness_balance_pct",
    "Form Power": "form_power_w",
    "Air Power": "air_power_w",
    "Impact": "impact_bw",
    "Impact Loading Rate Balance": "impact_loading_rate_balance_pct",
}
"""Exact developer ``field_name`` -> channel."""

_NAME_FOR_CHANNEL: Final[Mapping[str, str]] = {
    channel: name for name, channel in DEVELOPER_DYNAMICS_NAMES.items()
}

PLACEHOLDER_ZERO_CHANNELS: Final[frozenset[str]] = frozenset(
    {
        "stance_time_ms",
        "vertical_oscillation_mm",
        "vertical_ratio_pct",
        "step_length_mm",
        "leg_spring_stiffness_kn_m",
        "form_power_w",
        "impact_bw",
    }
)
"""Channels whose recorded ``0`` is a placeholder, read as ``None``."""

GATES: Final[Mapping[str, str]] = {
    "stance_time_balance_pct": "stance_time_ms",
    "vertical_oscillation_balance_pct": "vertical_oscillation_mm",
    "leg_spring_stiffness_balance_pct": "leg_spring_stiffness_kn_m",
    "air_power_w": "form_power_w",
    "impact_loading_rate_balance_pct": "impact_bw",
}
"""Gated channel -> the channel that must be present for it to be kept."""


def _developer_number(value: object) -> float | None:
    """A developer value that is a real number, unchanged; anything else ``None``."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value


def _raw_column(
    channel: str,
    retained_records: Sequence[Mapping[str, object]],
    developer: Mapping[str, DeveloperChannel],
) -> list[float | None]:
    """One channel's values as recorded, before the placeholder and gate rules."""
    native = NATIVE_DYNAMICS_FIELDS.get(channel)
    if native is not None:
        return [float_or_none(record.get(native)) for record in retained_records]
    source = developer.get(_NAME_FOR_CHANNEL[channel])
    if source is None:
        return [None] * len(retained_records)
    return [_developer_number(value) for value in source.values]


def extract_dynamics(
    retained_records: Sequence[Mapping[str, object]],
    developer: Mapping[str, DeveloperChannel],
) -> dict[str, tuple[float | None, ...]]:
    """The twelve dynamics channels, one entry per retained record.

    ``developer`` is the record-level developer mapping
    (:attr:`fitdocs.model.Activity.record_developer_fields`), index-aligned with
    ``retained_records``. Keys are :data:`fitdocs.model.DYNAMICS_CHANNELS`, in order.
    """
    columns = {
        channel: _raw_column(channel, retained_records, developer)
        for channel in DYNAMICS_CHANNELS
    }
    for channel in PLACEHOLDER_ZERO_CHANNELS:
        columns[channel] = [None if value == 0 else value for value in columns[channel]]
    for gated, gate in GATES.items():
        columns[gated] = [
            None if gate_value is None else value
            for value, gate_value in zip(columns[gated], columns[gate], strict=True)
        ]
    return {channel: tuple(columns[channel]) for channel in DYNAMICS_CHANNELS}
