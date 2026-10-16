"""The Garmin attribution line for a page's contributing files.

A pure wording module: :func:`attribution_line` decides whether a page names
Garmin as a data source and words the single line the views place beneath the
title. The rule reads only each file's recording device (the FIT creator,
which ingest normalizes to ``device_index == 0``); no line is produced unless
at least one contributing file's recording device is made by Garmin.
"""

from __future__ import annotations

import collections.abc
from collections.abc import Sequence
from enum import StrEnum
from typing import Final

from fitdocs.model import Activity, DeviceInfo

GARMIN_MANUFACTURER: Final[str] = "garmin"
RECORDING_DEVICE_INDEX: Final[int] = 0
SOLE_SOURCE_PREFIX: Final[str] = "Data source: "
SOURCES_PREFIX: Final[str] = "Data sources: "
OTHER_DEVICES: Final[str] = "other devices"

_BRAND: Final[str] = "Garmin"


def recording_device(devices: Sequence[DeviceInfo]) -> DeviceInfo | None:
    """The first device recorded at index 0, else ``None``."""
    for device in devices:
        if device.device_index == RECORDING_DEVICE_INDEX:
            return device
    return None


def garmin_label(devices: Sequence[DeviceInfo]) -> str | None:
    """``Garmin <model>`` when the recording device is a Garmin, else ``None``."""
    device = recording_device(devices)
    if device is None or device.manufacturer != GARMIN_MANUFACTURER:
        return None
    model = " ".join((device.product_name or "").split())
    if not model:
        return _BRAND
    lowered = model.lower()
    if lowered == _BRAND.lower() or lowered.startswith(_BRAND.lower() + " "):
        return model
    return f"{_BRAND} {model}"


def attribution_line(
    base: Activity, donor_devices: Sequence[Sequence[DeviceInfo]] = ()
) -> str | None:
    """The attribution line for the base file and its donors, or ``None``."""
    contributors = (base.devices, *donor_devices)
    labels: list[str] = []
    has_other = False
    for devices in contributors:
        label = garmin_label(devices)
        if label is None:
            has_other = True
        elif label not in labels:
            labels.append(label)
    if not labels:
        return None
    if len(labels) == 1 and not has_other:
        return f"{SOLE_SOURCE_PREFIX}{labels[0]}"
    names = [*labels, OTHER_DEVICES] if has_other else labels
    return f"{SOURCES_PREFIX}{', '.join(names[:-1])} and {names[-1]}"


GARMIN_ORIGIN: Final[str] = "garmin"


class WellnessAttribution(StrEnum):
    NONE = "none"
    SOLE = "sole"
    CONTRIBUTING = "contributing"


def wellness_attribution(
    origins: collections.abc.Iterable[str | None],
) -> WellnessAttribution:
    recorded = set(origins)
    if GARMIN_ORIGIN not in recorded:
        return WellnessAttribution.NONE
    if recorded == {GARMIN_ORIGIN}:
        return WellnessAttribution.SOLE
    return WellnessAttribution.CONTRIBUTING


def wellness_attribution_line(attribution: WellnessAttribution) -> str | None:
    if attribution is WellnessAttribution.SOLE:
        return SOLE_SOURCE_PREFIX + "Garmin"
    if attribution is WellnessAttribution.CONTRIBUTING:
        return SOURCES_PREFIX + "Garmin and other sources"
    return None
