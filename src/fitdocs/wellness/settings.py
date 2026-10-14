"""Read the wellness table of an already-parsed settings document."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from fitdocs.settings import SettingsError
from fitdocs.wellness import registry
from fitdocs.wellness.model import Metric

WELLNESS_TABLE: Final[str] = "wellness"


@dataclass(frozen=True)
class WellnessSettings:
    precedence: tuple[str, ...]
    metric_precedence: Mapping[Metric, tuple[str, ...]]


DEFAULT_WELLNESS_SETTINGS: Final[WellnessSettings] = WellnessSettings((), {})


class WellnessSettingsError(SettingsError):
    """The wellness table contains invalid configuration."""


def _error(data_root: Path, key: str, detail: str) -> WellnessSettingsError:
    return WellnessSettingsError(f"{data_root / 'fitdocs.toml'}: {key} {detail}")


def _source_list(raw: object, *, data_root: Path, key: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise _error(data_root, key, "must be a list of source identifiers")
    sources: list[str] = []
    for index, item in enumerate(raw):
        item_key = f"{key}[{index}]"
        if not isinstance(item, str):
            raise _error(data_root, item_key, "must be a string")
        if registry.source_named(item) is None:
            raise _error(data_root, item_key, f"unknown source {item!r}")
        if item in sources:
            raise _error(data_root, item_key, f"duplicate source {item!r}")
        sources.append(item)
    return tuple(sources)


def load_wellness_settings(
    document: Mapping[str, object], *, data_root: Path
) -> WellnessSettings:
    if WELLNESS_TABLE not in document:
        return DEFAULT_WELLNESS_SETTINGS
    table = document[WELLNESS_TABLE]
    if not isinstance(table, Mapping):
        raise _error(data_root, "[wellness]", "must be a table")
    precedence = _source_list(
        table.get("precedence", []), data_root=data_root, key="[wellness] precedence"
    )
    raw_metrics = table.get("metric_precedence", {})
    if not isinstance(raw_metrics, Mapping):
        raise _error(data_root, "[wellness] metric_precedence", "must be a table")
    metric_precedence: dict[Metric, tuple[str, ...]] = {}
    for name, raw in raw_metrics.items():
        key = f"[wellness] metric_precedence.{name}"
        metric = next((metric for metric in Metric if metric.value == name), None)
        if metric is None:
            raise _error(data_root, key, f"unknown metric {name!r}")
        metric_precedence[metric] = _source_list(raw, data_root=data_root, key=key)
    return WellnessSettings(precedence, metric_precedence)


def effective_order(settings: WellnessSettings, metric: Metric) -> tuple[str, ...]:
    configured = settings.metric_precedence.get(metric, settings.precedence)
    return configured + tuple(
        source for source in registry.default_source_order() if source not in configured
    )
