"""The declared, append-only registry of chart kinds and its description.

Kinds are declared, not discovered: a kind module exports ``KIND`` and is
imported and appended to :data:`KINDS` here. Every function reads ``KINDS`` at
call time and keeps no import-time index, so a test that replaces the module
attribute sees its own kinds.
"""

from __future__ import annotations

from typing import Final, TypedDict

from fitdocs.render.charts.kit.kinds import (
    area,
    band,
    bar,
    box,
    calendar_heatmap,
    dual_axis,
    hbar,
    heatmap,
    histogram,
    line,
    mean_max,
    scatter,
    small_multiples,
    stacked_100,
    stat,
    table,
)
from fitdocs.render.charts.kit.schema import KindSpec

KINDS: Final[tuple[KindSpec, ...]] = (
    line.KIND,
    area.KIND,
    bar.KIND,
    hbar.KIND,
    scatter.KIND,
    histogram.KIND,
    stat.KIND,
    table.KIND,
    calendar_heatmap.KIND,
    heatmap.KIND,
    dual_axis.KIND,
    band.KIND,
    box.KIND,
    mean_max.KIND,
    small_multiples.KIND,
    stacked_100.KIND,
)

CORE_KIND_NAMES: Final = (
    "line",
    "area",
    "bar",
    "hbar",
    "scatter",
    "histogram",
    "stat",
    "table",
)


class ChannelListing(TypedDict):
    name: str
    required: bool
    accepts: list[str]
    description: str


class OptionListing(TypedDict):
    name: str
    type: str
    default: bool | int | float | str | None
    choices: list[str]
    minimum: float | None
    maximum: float | None
    description: str


class BoundListing(TypedDict):
    limit: int
    counts: str
    over: str
    rule: str


class KindListing(TypedDict):
    name: str
    description: str
    output: str
    channels: list[ChannelListing]
    options: list[OptionListing]
    bound: BoundListing
    max_series: int | None


def kind_named(name: str) -> KindSpec | None:
    """The registered kind called ``name``, or ``None``."""
    for spec in KINDS:
        if spec.name == name:
            return spec
    return None


def kind_names() -> tuple[str, ...]:
    """The registered kind names in registration order."""
    return tuple(spec.name for spec in KINDS)


def _listing(spec: KindSpec) -> KindListing:
    return {
        "name": str(spec.name),
        "description": str(spec.description),
        "output": spec.output.value,
        "channels": [
            {
                "name": str(c.name),
                "required": c.required,
                "accepts": [k.value for k in c.accepts],
                "description": str(c.description),
            }
            for c in spec.channels
        ],
        "options": [
            {
                "name": str(o.name),
                "type": o.type.value,
                "default": o.default,
                "choices": [str(choice) for choice in o.choices],
                "minimum": o.minimum,
                "maximum": o.maximum,
                "description": str(o.description),
            }
            for o in spec.options
        ],
        "bound": {
            "limit": spec.bound.limit,
            "counts": str(spec.bound.counts),
            "over": spec.bound.over.value,
            "rule": str(spec.bound.rule),
        },
        "max_series": spec.max_series,
    }


def describe_kinds() -> tuple[KindListing, ...]:
    """A JSON-ready description of every registered kind, in registration order."""
    return tuple(_listing(spec) for spec in KINDS)
