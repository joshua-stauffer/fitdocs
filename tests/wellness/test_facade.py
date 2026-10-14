"""The public wellness consumer interface."""

from importlib import import_module

import pytest

import fitdocs.wellness as wellness

_EXPECTED = (
    "Metric",
    "MetricInfo",
    "METRICS",
    "accept_value",
    "wellness_day_of_sleep_end",
    "SourceKind",
    "SeriesValue",
    "WellnessSeries",
    "SeriesReadError",
    "read_series",
    "series_files",
    "WellnessSettings",
    "WellnessSettingsError",
    "DEFAULT_WELLNESS_SETTINGS",
    "load_wellness_settings",
    "effective_order",
)
_BINDINGS = [
    ("Metric", "model"),
    ("MetricInfo", "model"),
    ("METRICS", "model"),
    ("accept_value", "model"),
    ("wellness_day_of_sleep_end", "model"),
    ("SourceKind", "spec"),
    ("SeriesValue", "model"),
    ("WellnessSeries", "series"),
    ("SeriesReadError", "series"),
    ("read_series", "series"),
    ("series_files", "series"),
    ("WellnessSettings", "settings"),
    ("WellnessSettingsError", "settings"),
    ("DEFAULT_WELLNESS_SETTINGS", "settings"),
    ("load_wellness_settings", "settings"),
    ("effective_order", "settings"),
]


def test_exact_exports() -> None:
    assert tuple(wellness.__all__) == _EXPECTED


@pytest.mark.parametrize("name,module", _BINDINGS)
def test_bindings(name: str, module: str) -> None:
    assert getattr(wellness, name) is getattr(
        import_module("fitdocs.wellness." + module), name
    )
