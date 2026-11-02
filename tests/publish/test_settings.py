"""The ``[publish]`` settings reader and built-in default (publish-core task
4.4; Req 4.1, 4.2, 4.3, 4.6, 4.8)."""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import pytest

from fitdocs.publish.settings import (
    DEFAULT_DESCRIPTION,
    DEFAULT_TEMPLATES,
    DEFAULT_TITLE,
    PublishSettings,
    PublishSettingsError,
    load_publish_settings,
)
from fitdocs.publish.template import render
from fitdocs.publish.values import PLACEHOLDERS
from fitdocs.settings import SettingsError

FILE = Path("/data/fitdocs.toml")
TARGETS = ("intervals", "strava")


def load(
    document: dict[str, object], targets: tuple[str, ...] = TARGETS
) -> PublishSettings:
    return load_publish_settings(document, settings_file=FILE, targets=targets)


def refusal(document: dict[str, object]) -> str:
    with pytest.raises(PublishSettingsError) as info:
        load(document)
    return str(info.value)


def sources(settings: PublishSettings, name: str) -> tuple[str, str]:
    t = settings.for_target(name)
    return t.title.source, t.description.source


# ------------------------------------------------------------ built-in default


def test_default_title_and_description_literals() -> None:
    assert DEFAULT_TITLE == "{title}"
    assert DEFAULT_DESCRIPTION.count("{?") == 7
    assert DEFAULT_DESCRIPTION.count("\n") == 7
    assert DEFAULT_TEMPLATES.title.source == DEFAULT_TITLE
    assert DEFAULT_TEMPLATES.description.source == DEFAULT_DESCRIPTION


def test_default_with_only_title_yields_title_and_empty_description() -> None:
    values: dict[str, str | None] = dict.fromkeys(PLACEHOLDERS)
    values["title"] = "Morning run"
    assert render(DEFAULT_TEMPLATES.title, values) == "Morning run"
    assert render(DEFAULT_TEMPLATES.description, values) == ""


def test_default_description_literal() -> None:
    assert DEFAULT_DESCRIPTION == (
        "{?Distance: {distance_km} km\n}"
        "{?Time: {moving_time}\n}"
        "{?Pace: {pace_per_km} /km\n}"
        "{?Speed: {speed_kmh} km/h\n}"
        "{?Average heart rate: {avg_hr_bpm} bpm\n}"
        "{?Average power: {avg_power_w} W\n}"
        "{?Elevation gain: {elevation_gain_m} m\n}"
    )


@pytest.mark.parametrize(
    ("name", "value", "line"),
    [
        ("distance_km", "11.11", "Distance: 11.11 km\n"),
        ("moving_time", "22:22", "Time: 22:22\n"),
        ("pace_per_km", "3:33", "Pace: 3:33 /km\n"),
        ("speed_kmh", "44.4", "Speed: 44.4 km/h\n"),
        ("avg_hr_bpm", "155", "Average heart rate: 155 bpm\n"),
        ("avg_power_w", "266", "Average power: 266 W\n"),
        ("elevation_gain_m", "377", "Elevation gain: 377 m\n"),
    ],
)
def test_default_description_with_one_placeholder_renders_only_its_line(
    name: str, value: str, line: str
) -> None:
    values: dict[str, str | None] = dict.fromkeys(PLACEHOLDERS)
    values["title"] = "t"
    values[name] = value
    assert render(DEFAULT_TEMPLATES.description, values) == line


def test_default_description_includes_each_clause_with_its_value() -> None:
    values: dict[str, str | None] = dict.fromkeys(PLACEHOLDERS)
    values.update(
        distance_km="10.00",
        moving_time="50:00",
        pace_per_km="5:00",
        speed_kmh="12.0",
        avg_hr_bpm="150",
        avg_power_w="250",
        elevation_gain_m="120",
    )
    assert render(DEFAULT_TEMPLATES.description, values) == (
        "Distance: 10.00 km\nTime: 50:00\nPace: 5:00 /km\nSpeed: 12.0 km/h\n"
        "Average heart rate: 150 bpm\nAverage power: 250 W\n"
        "Elevation gain: 120 m\n"
    )


# ------------------------------------------------------------ resolution order


def test_absent_table_gives_default_for_every_target() -> None:
    s = load({})
    assert set(s.per_target) == set(TARGETS)
    for name in TARGETS:
        assert sources(s, name) == (DEFAULT_TITLE, DEFAULT_DESCRIPTION)


def test_no_targets_gives_empty_mapping() -> None:
    assert load({"publish": {"title": "{title}"}}, targets=()).per_target == {}


def test_table_wide_replaces_default_per_field() -> None:
    s = load({"publish": {"title": "T {title}"}})
    assert sources(s, "strava") == ("T {title}", DEFAULT_DESCRIPTION)
    s = load({"publish": {"description": "D {sport}"}})
    assert sources(s, "strava") == (DEFAULT_TITLE, "D {sport}")


def test_target_replaces_table_wide_and_default_per_field_and_per_target() -> None:
    doc: dict[str, object] = {
        "publish": {
            "title": "wide-title {title}",
            "description": "wide-desc",
            "targets": {
                "strava": {"title": "strava-title {title}"},
                "intervals": {"description": "intervals-desc"},
            },
        }
    }
    s = load(doc)
    assert sources(s, "strava") == ("strava-title {title}", "wide-desc")
    assert sources(s, "intervals") == ("wide-title {title}", "intervals-desc")


def test_target_overrides_default_without_table_wide() -> None:
    s = load({"publish": {"targets": {"strava": {"description": "d"}}}})
    assert sources(s, "strava") == (DEFAULT_TITLE, "d")
    assert sources(s, "intervals") == (DEFAULT_TITLE, DEFAULT_DESCRIPTION)


def test_empty_description_is_a_value_not_absence() -> None:
    s = load({"publish": {"description": ""}})
    assert sources(s, "strava")[1] == ""
    s = load(
        {"publish": {"description": "wide", "targets": {"strava": {"description": ""}}}}
    )
    assert sources(s, "strava")[1] == ""


def test_target_table_may_be_empty() -> None:
    s = load({"publish": {"targets": {"strava": {}}}})
    assert sources(s, "strava") == (DEFAULT_TITLE, DEFAULT_DESCRIPTION)


def test_description_may_span_lines() -> None:
    s = load({"publish": {"description": "a\nb"}})
    assert sources(s, "strava")[1] == "a\nb"


def test_other_top_level_tables_are_ignored() -> None:
    s = load({"tiles": {"x": 1}, "publish": {"title": "{title}!"}})
    assert sources(s, "strava")[0] == "{title}!"


# ------------------------------------------------------------------- refusals


def test_error_type_is_a_settings_error() -> None:
    assert issubclass(PublishSettingsError, SettingsError)


@pytest.mark.parametrize(
    ("document", "where"),
    [
        ({"publish": "x"}, "[publish]"),
        ({"publish": {"targets": "x"}}, "[publish.targets]"),
        ({"publish": {"targets": {"strava": 3}}}, "[publish.targets.strava]"),
    ],
)
def test_non_table_is_refused_naming_file_and_table(
    document: dict[str, object], where: str
) -> None:
    message = refusal(document)
    assert str(FILE) in message
    assert f"{where} must be a table" in message


@pytest.mark.parametrize(
    ("document", "where"),
    [
        ({"publish": {"colour": "x"}}, "[publish]"),
        (
            {"publish": {"targets": {"strava": {"colour": "x"}}}},
            "[publish.targets.strava]",
        ),
    ],
)
def test_unknown_key_is_refused_naming_file_table_and_key(
    document: dict[str, object], where: str
) -> None:
    message = refusal(document)
    assert str(FILE) in message
    assert f"{where} has unknown key 'colour'" in message


@pytest.mark.parametrize("key", ["title", "description"])
@pytest.mark.parametrize("bad", [5, True, ["a"], {"a": 1}])
def test_non_string_value_is_refused_in_both_tables(key: str, bad: object) -> None:
    message = refusal({"publish": {key: bad}})
    assert str(FILE) in message
    assert f"[publish] {key} must be text" in message
    message = refusal({"publish": {"targets": {"strava": {key: bad}}}})
    assert f"[publish.targets.strava] {key} must be text" in message


#: Every code point ruling 4.2(C) refuses (categories Cc, Zl, Zp), each
#: inside a title, so a hand-listed subset cannot pass for the predicate.
_EVERY_NOT_SINGLE_LINE_CHARACTER = tuple(
    f"a{chr(c)}b"
    for c in range(sys.maxunicode + 1)
    if unicodedata.category(chr(c)) in {"Cc", "Zl", "Zp"}
)


@pytest.mark.parametrize(
    "newline",
    [
        "a\nb",
        "a\rb",
        "a\r\nb",
        "{?x{title}\n}",
        "a\u2028b",
        "a\u2029b",
        "a\x0bb",
        "a\x85b",
        "a\tb",
        "{title}\n",
        "\n{title}",
        *_EVERY_NOT_SINGLE_LINE_CHARACTER,
    ],
)
def test_title_that_is_not_single_line_text_is_refused_in_both_tables(
    newline: str,
) -> None:
    message = refusal({"publish": {"title": newline}})
    assert str(FILE) in message
    assert "[publish] title must be a single line" in message
    message = refusal({"publish": {"targets": {"intervals": {"title": newline}}}})
    assert "[publish.targets.intervals] title must be a single line" in message


@pytest.mark.parametrize(
    "title",
    [
        "\U0001f3c3\u200d\u2642\ufe0f {title}",
        "a\u00a0{title}",
        "{title}\u200b",
    ],
)
def test_single_line_title_with_format_or_space_characters_is_accepted(
    title: str,
) -> None:
    s = load({"publish": {"title": title}})
    assert sources(s, "strava")[0] == title
    s = load({"publish": {"targets": {"strava": {"title": title}}}})
    assert sources(s, "strava")[0] == title


def test_description_with_crlf_is_accepted_unchanged() -> None:
    s = load({"publish": {"description": "a\r\nb"}})
    assert sources(s, "strava")[1] == "a\r\nb"


def test_targets_key_inside_a_target_table_is_an_unknown_key() -> None:
    message = refusal({"publish": {"targets": {"strava": {"targets": {}}}}})
    assert str(FILE) in message
    assert "[publish.targets.strava] has unknown key 'targets'" in message


def test_publish_unknown_key_message_lists_targets_among_expected() -> None:
    message = refusal({"publish": {"colour": "x"}})
    assert "(expected one of title, description, targets)" in message
    message = refusal({"publish": {"targets": {"strava": {"colour": "x"}}}})
    assert "(expected one of title, description)" in message


def test_template_error_names_file_table_key_position_and_reason() -> None:
    message = refusal({"publish": {"description": "ab\n  {nope}"}})
    assert str(FILE) in message
    assert "[publish] description" in message
    assert "line 2, column 3" in message
    assert "unknown placeholder {nope}" in message


def test_template_error_in_target_table_names_that_table() -> None:
    message = refusal({"publish": {"targets": {"strava": {"title": "{title"}}}})
    assert "[publish.targets.strava] title" in message
    assert "line 1, column 1" in message


def test_syntax_error_is_refused_for_description_too() -> None:
    message = refusal({"publish": {"description": "a }"}})
    assert "[publish] description" in message
    assert "line 1, column 3" in message


def test_target_that_is_not_configured_is_refused() -> None:
    message = refusal({"publish": {"targets": {"garmin": {"title": "x"}}}})
    assert str(FILE) in message
    assert "[publish.targets.garmin]" in message
    assert "not a configured publish target" in message
    assert "intervals, strava" in message


def test_unconfigured_target_is_refused_even_with_no_targets_configured() -> None:
    with pytest.raises(PublishSettingsError, match="none configured"):
        load({"publish": {"targets": {"garmin": {}}}}, targets=())


def test_non_table_target_entry_is_refused_before_membership() -> None:
    message = refusal({"publish": {"targets": {"garmin": 3}}})
    assert "must be a table" in message
