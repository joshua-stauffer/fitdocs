"""Wellness configuration and live per-metric source order."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from fitdocs.settings import SettingsError
from fitdocs.wellness.model import Metric
from fitdocs.wellness.settings import (
    DEFAULT_WELLNESS_SETTINGS,
    WELLNESS_TABLE,
    WellnessSettings,
    WellnessSettingsError,
    effective_order,
    load_wellness_settings,
)
from fitdocs.wellness.spec import SourceKind, SourceSpec
from tests.wellness._helpers import use_formats

DEVICE = SourceSpec("z-device", "Test device", SourceKind.DEVICE)
HUB = SourceSpec("b-hub", "Test hub", SourceKind.HUB)
RELAY = SourceSpec("a-relay", "Test relay", SourceKind.RELAY)
DEFAULT_ORDER = ("z-device", "b-hub", "a-relay")


@pytest.fixture(autouse=True)
def sources(monkeypatch: pytest.MonkeyPatch) -> None:
    use_formats(monkeypatch, (), (RELAY, DEVICE, HUB))


@pytest.mark.parametrize(
    "document", [{}, {"wellness": {}}, {"wellness": {"future": 7}}]
)
def test_absent_configuration(document: dict[str, object], tmp_path: Path) -> None:
    settings = load_wellness_settings(document, data_root=tmp_path)
    assert settings == WellnessSettings((), {}) == DEFAULT_WELLNESS_SETTINGS
    assert effective_order(settings, Metric.WEIGHT_KG) == DEFAULT_ORDER
    assert WELLNESS_TABLE == "wellness"


def test_partial_global_order(tmp_path: Path) -> None:
    settings = load_wellness_settings(
        {"wellness": {"precedence": ["b-hub", "a-relay"]}}, data_root=tmp_path
    )
    assert settings.precedence == ("b-hub", "a-relay")
    assert effective_order(settings, Metric.WEIGHT_KG) == (
        "b-hub",
        "a-relay",
        "z-device",
    )


@pytest.mark.parametrize(
    ("override", "expected"),
    [(["a-relay"], ("a-relay", "z-device", "b-hub")), ([], DEFAULT_ORDER)],
)
def test_metric_override(
    override: list[str], expected: tuple[str, ...], tmp_path: Path
) -> None:
    settings = load_wellness_settings(
        {
            "wellness": {
                "precedence": ["b-hub", "a-relay"],
                "metric_precedence": {"resting_hr_bpm": override},
            }
        },
        data_root=tmp_path,
    )
    assert settings.metric_precedence == {Metric.RESTING_HR_BPM: tuple(override)}
    assert effective_order(settings, Metric.RESTING_HR_BPM) == expected
    assert effective_order(settings, Metric.WEIGHT_KG) == (
        "b-hub",
        "a-relay",
        "z-device",
    )


@pytest.mark.parametrize("use_default", [False, True])
def test_defaults_consult_registry_at_call_time(
    use_default: bool, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = (
        DEFAULT_WELLNESS_SETTINGS
        if use_default
        else load_wellness_settings({}, data_root=tmp_path)
    )
    use_formats(monkeypatch, (), (HUB, RELAY))
    assert effective_order(settings, Metric.WEIGHT_KG) == ("b-hub", "a-relay")


def test_removed_source_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    use_formats(monkeypatch, (), (HUB, RELAY))
    with pytest.raises(WellnessSettingsError):
        load_wellness_settings(
            {"wellness": {"precedence": ["z-device"]}}, data_root=tmp_path
        )


def test_reader_uses_document_without_opening_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("settings reader opened a file")

    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    settings = load_wellness_settings(
        {"unrelated": False, "wellness": {"future": None, "precedence": ["a-relay"]}},
        data_root=tmp_path / "absent",
    )
    assert effective_order(settings, Metric.WEIGHT_KG) == (
        "a-relay",
        "z-device",
        "b-hub",
    )


def test_settings_are_frozen() -> None:
    settings = WellnessSettings((), {})
    with pytest.raises(FrozenInstanceError):
        settings.precedence = ("a-relay",)  # type: ignore[misc]


@pytest.mark.parametrize(
    ("table", "key", "reason"),
    [
        pytest.param(None, "[wellness]", "must be a table", id="table-null"),
        pytest.param([], "[wellness]", "must be a table", id="table-list"),
        pytest.param("bad", "[wellness]", "must be a table", id="table-string"),
        pytest.param(
            {"precedence": "b-hub"},
            "[wellness] precedence",
            "must be a list",
            id="global-string",
        ),
        pytest.param(
            {"precedence": None},
            "[wellness] precedence",
            "must be a list",
            id="global-null",
        ),
        pytest.param(
            {"precedence": ("b-hub",)},
            "[wellness] precedence",
            "must be a list",
            id="global-tuple",
        ),
        pytest.param(
            {"precedence": {}},
            "[wellness] precedence",
            "must be a list",
            id="global-table",
        ),
        pytest.param(
            {"precedence": ["b-hub", 7]},
            "[wellness] precedence[1]",
            "must be a string",
            id="global-number",
        ),
        pytest.param(
            {"precedence": [False]},
            "[wellness] precedence[0]",
            "must be a string",
            id="global-bool",
        ),
        pytest.param(
            {"precedence": [None]},
            "[wellness] precedence[0]",
            "must be a string",
            id="global-entry-null",
        ),
        pytest.param(
            {"precedence": ["b-hub", "missing"]},
            "[wellness] precedence[1]",
            "unknown source",
            id="global-unknown",
        ),
        pytest.param(
            {"precedence": ["b-hub", "a-relay", "b-hub"]},
            "[wellness] precedence[2]",
            "duplicate source",
            id="global-duplicate",
        ),
        pytest.param(
            {"metric_precedence": []},
            "[wellness] metric_precedence",
            "must be a table",
            id="metrics-list",
        ),
        pytest.param(
            {"metric_precedence": None},
            "[wellness] metric_precedence",
            "must be a table",
            id="metrics-null",
        ),
        pytest.param(
            {"metric_precedence": {"mystery": []}},
            "[wellness] metric_precedence.mystery",
            "unknown metric",
            id="metric-unknown",
        ),
        pytest.param(
            {"metric_precedence": {7: []}},
            "[wellness] metric_precedence.7",
            "unknown metric",
            id="metric-number",
        ),
        pytest.param(
            {"metric_precedence": {"weight_kg": "b-hub"}},
            "[wellness] metric_precedence.weight_kg",
            "must be a list",
            id="metric-string",
        ),
        pytest.param(
            {"metric_precedence": {"weight_kg": None}},
            "[wellness] metric_precedence.weight_kg",
            "must be a list",
            id="metric-null",
        ),
        pytest.param(
            {"metric_precedence": {"weight_kg": [7]}},
            "[wellness] metric_precedence.weight_kg[0]",
            "must be a string",
            id="metric-entry-number",
        ),
        pytest.param(
            {"metric_precedence": {"weight_kg": ["missing"]}},
            "[wellness] metric_precedence.weight_kg[0]",
            "unknown source",
            id="metric-source-unknown",
        ),
        pytest.param(
            {"metric_precedence": {"weight_kg": ["b-hub", "a-relay", "b-hub"]}},
            "[wellness] metric_precedence.weight_kg[2]",
            "duplicate source",
            id="metric-duplicate",
        ),
    ],
)
def test_invalid_configuration(
    table: object, key: str, reason: str, tmp_path: Path
) -> None:
    with pytest.raises(WellnessSettingsError) as caught:
        load_wellness_settings({"wellness": table}, data_root=tmp_path)
    assert isinstance(caught.value, SettingsError)
    assert str(tmp_path / "fitdocs.toml") in str(caught.value)
    assert key in str(caught.value)
    assert reason in str(caught.value)
