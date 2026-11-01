"""The publishing readers in :mod:`fitdocs.contract` (publish-core 2.1; Req 2.1, 5.2).

``document_publish_targets`` reads the ``publish`` key; ``document_summary``
reads the page's title and headline figures under the exact frontmatter keys the
workout renderer emits. Both do not raise on any value, and an unusable value is
absent (``None``), not a fabricated ``0``.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import fitdocs.render.frontmatter as renderer
from fitdocs import contract
from fitdocs.contract import (
    PUBLISH_KEY,
    InvalidPublishKey,
    SummaryReading,
    document_publish_targets,
    document_summary,
    parse_frontmatter,
)

# --- the publish key -----------------------------------------------------------


def test_publish_key_is_the_literal_and_is_user_owned() -> None:
    assert PUBLISH_KEY == "publish"
    assert PUBLISH_KEY in contract.USER_KEYS


@pytest.mark.parametrize(
    "frontmatter",
    [None, {}, {"title": "x"}, {PUBLISH_KEY: []}],
    ids=["none", "empty", "other-keys", "empty-list"],
)
def test_absent_key_or_empty_list_is_no_targets(
    frontmatter: dict[str, object] | None,
) -> None:
    assert document_publish_targets(frontmatter) == ()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("intervals", ("intervals",)),
        (["strava"], ("strava",)),
        (["strava", "intervals", "a b"], ("strava", "intervals", "a b")),
        (["b", "a"], ("b", "a")),
        (" ", (" ",)),
        (["strava", "  "], ("strava", "  ")),
    ],
    ids=[
        "one-name",
        "one-in-list",
        "three-in-order",
        "order-kept-not-sorted",
        "whitespace-name-is-a-name",
        "whitespace-name-in-list",
    ],
)
def test_names_read_as_those_names_in_order(
    value: object, expected: tuple[str, ...]
) -> None:
    result = document_publish_targets({PUBLISH_KEY: value})
    assert result == expected
    assert isinstance(result, tuple)


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        None,
        0,
        3,
        1.5,
        "",
        {"a": "b"},
        {"strava"},
        ("strava",),
        [""],
        ["strava", ""],
        ["strava", "strava"],
        ["a", "b", "a"],
        [True],
        ["strava", False],
        [None],
        [3],
        [["strava"]],
        [{"a": 1}],
        [[]],
    ],
    ids=repr,
)
def test_every_other_shape_is_an_invalid_key_with_a_reason(value: object) -> None:
    result = document_publish_targets({PUBLISH_KEY: value})
    assert isinstance(result, InvalidPublishKey)
    assert result.detail


def test_duplicate_reason_names_the_repeated_name() -> None:
    result = document_publish_targets({PUBLISH_KEY: ["strava", "intervals", "strava"]})
    assert isinstance(result, InvalidPublishKey)
    assert "strava" in result.detail
    assert "intervals" not in result.detail


def test_names_are_not_normalized() -> None:
    assert document_publish_targets({PUBLISH_KEY: ["Strava", "strava"]}) == (
        "Strava",
        "strava",
    )
    assert document_publish_targets({PUBLISH_KEY: [" a", "a"]}) == (" a", "a")


# --- the summary ---------------------------------------------------------------

FULL: dict[str, object] = {
    "title": "Run 2026-03-04 07:30",
    "distance_km": 10.25,
    "moving_time": "1:02:03",
    "avg_hr_bpm": 151,
    "avg_power_w": 233,
    "elevation_gain_m": 45.5,
    "calories_kcal": 702,
}


def test_full_frontmatter_reads_every_field_distinctly() -> None:
    assert document_summary(FULL) == SummaryReading(
        title="Run 2026-03-04 07:30",
        distance_km=10.25,
        moving_time_s=3723.0,
        avg_hr_bpm=151,
        avg_power_w=233,
        elevation_gain_m=45.5,
        calories_kcal=702,
    )


def test_summary_keys_are_ones_the_renderer_writes() -> None:
    source = inspect.getsource(renderer)
    for key in FULL:
        assert f'data["{key}"]' in source, key


@pytest.mark.parametrize("frontmatter", [None, {}], ids=["none", "empty"])
def test_absent_frontmatter_is_all_none(frontmatter: dict[str, object] | None) -> None:
    assert document_summary(frontmatter) == SummaryReading(
        None, None, None, None, None, None, None
    )


NUMERIC = [
    ("distance_km", "distance_km"),
    ("elevation_gain_m", "elevation_gain_m"),
    ("avg_hr_bpm", "avg_hr_bpm"),
    ("avg_power_w", "avg_power_w"),
    ("calories_kcal", "calories_kcal"),
]


@pytest.mark.parametrize(("key", "field"), NUMERIC)
@pytest.mark.parametrize(
    "bad",
    [
        True,
        False,
        "12",
        "12.5",
        "",
        None,
        float("nan"),
        float("inf"),
        float("-inf"),
        -1,
        -0.5,
        [1],
        {"a": 1},
        10**400,
    ],
    ids=lambda v: repr(v)[:20],
)
def test_unusable_numbers_are_none_not_zero(key: str, field: str, bad: object) -> None:
    reading = document_summary({**FULL, key: bad})
    assert getattr(reading, field) is None


@pytest.mark.parametrize(("key", "field"), NUMERIC)
def test_a_true_zero_is_kept_and_a_missing_key_is_none(key: str, field: str) -> None:
    zero = getattr(document_summary({key: 0}), field)
    assert zero == 0
    assert zero is not None
    assert getattr(document_summary({}), field) is None


def test_one_bad_field_leaves_the_others_intact() -> None:
    reading = document_summary({**FULL, "distance_km": True, "moving_time": "bad"})
    assert reading.distance_km is None
    assert reading.moving_time_s is None
    assert reading.title == FULL["title"]
    assert reading.avg_hr_bpm == 151
    assert reading.calories_kcal == 702


def test_int_and_float_are_both_accepted_and_distance_is_a_float() -> None:
    distance = document_summary({"distance_km": 10}).distance_km
    assert distance == 10.0
    assert isinstance(distance, float)
    assert document_summary({"elevation_gain_m": 0.1}).elevation_gain_m == 0.1


@pytest.mark.parametrize("tie", [0.5, 1.5, 2.5, 3.5, 150.5, 151.5, 233.5, 234.5])
@pytest.mark.parametrize("key", ["avg_hr_bpm", "avg_power_w", "calories_kcal"])
def test_ties_round_half_to_even_exactly_as_the_renderer_does(
    key: str, tie: float
) -> None:
    """The renderer writes ``int(round(x))``; half-to-even, not half-up."""
    field = getattr(document_summary({key: tie}), key)
    assert field == int(round(tie))
    assert isinstance(field, int)


def test_the_tie_table_separates_half_even_from_half_up() -> None:
    assert [int(round(t)) for t in (150.5, 233.5, 2.5)] == [150, 234, 2]
    assert document_summary({"avg_hr_bpm": 150.5}).avg_hr_bpm == 150
    assert document_summary({"avg_power_w": 233.5}).avg_power_w == 234
    assert document_summary({"calories_kcal": 2.5}).calories_kcal == 2


GOLDEN_DOCS = sorted((Path(__file__).parent / "render" / "golden_docs").glob("*.md"))


def test_every_golden_page_reads_a_title_and_moving_time() -> None:
    """The renderer quotes some moving times (``'1:18'``); the reader takes them."""
    assert len(GOLDEN_DOCS) >= 10
    for page in GOLDEN_DOCS:
        frontmatter = parse_frontmatter(page.read_text(encoding="utf-8"))
        reading = document_summary(frontmatter)
        assert reading.title, page.name
        assert reading.moving_time_s is not None, page.name


def test_the_golden_pages_include_a_quoted_moving_time() -> None:
    texts = [page.read_text(encoding="utf-8") for page in GOLDEN_DOCS]
    assert any("moving_time: '" in text for text in texts)
    assert any("moving_time: 0:" in text for text in texts)


def test_whole_number_fields_are_ints_rounded_like_the_renderer() -> None:
    reading = document_summary(
        {"avg_hr_bpm": 150.4, "avg_power_w": 233.6, "calories_kcal": 700.0}
    )
    assert (reading.avg_hr_bpm, reading.avg_power_w, reading.calories_kcal) == (
        150,
        234,
        700,
    )
    assert isinstance(reading.avg_hr_bpm, int)
    assert isinstance(reading.calories_kcal, int)


@pytest.mark.parametrize(
    "bad", [None, "", "   ", "\n", 5, True, ["x"], {"a": 1}], ids=repr
)
def test_unusable_title_is_none(bad: object) -> None:
    assert document_summary({"title": bad}).title is None


def test_title_is_kept_verbatim() -> None:
    assert document_summary({"title": " Long run "}).title == " Long run "


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("0:00", 0.0),
        ("0:01", 1.0),
        ("5:07", 307.0),
        ("05:07", 307.0),
        ("59:59", 3599.0),
        ("1:00:00", 3600.0),
        ("1:02:03", 3723.0),
        ("01:02:03", 3723.0),
        ("0:00:00", 0.0),
        ("0:59:59", 3599.0),
        ("10:00:00", 36000.0),
        ("123:45:06", 123 * 3600 + 45 * 60 + 6.0),
    ],
)
def test_moving_time_accepted_shapes(text: str, seconds: float) -> None:
    value = document_summary({"moving_time": text}).moving_time_s
    assert value == seconds
    assert isinstance(value, float)


@pytest.mark.parametrize(
    "text",
    [
        "60:00",
        "61:05",
        "99:59",
        "100:00",
        "1:60:00",
        "1:00:60",
        "1:99:00",
        "0:60:00",
        "1:5:00",
        "1:00:5",
        "5:7",
        "5:070",
        "5:",
        ":30",
        "",
        "1",
        "90",
        "1:2:3:4",
        "1:02:03:04",
        " 5:07",
        "5:07 ",
        "5:07\n",
        "5.07",
        "-5:07",
        "-1:00:00",
        "+5:07",
        "5:07.5",
        "1:02:03.5",
        "\u0663:00",
        "5:0\u0663",
        "\u0661:00:00",
        "1:0\u0663:00",
        "1:00:0\u0663",
        "\u0663:\u0660\u0660",
        "1h2m3s",
        "PT1H",
        "nan",
        "inf",
        "1:1000000:00",
        "1" * 5000 + ":00:00",
    ],
    ids=lambda v: repr(v)[:24],
)
def test_moving_time_refused_shapes(text: str) -> None:
    assert document_summary({"moving_time": text}).moving_time_s is None


@pytest.mark.parametrize(
    "bad", [3723, 3723.0, True, 0, None, ["1:00"], float("nan")], ids=repr
)
def test_moving_time_only_from_a_string(bad: object) -> None:
    assert document_summary({"moving_time": bad}).moving_time_s is None


def test_readers_do_not_raise_on_adversarial_values() -> None:
    nasty: list[object] = [
        None,
        True,
        10**5000,
        float("nan"),
        "x" * 10000,
        [],
        {},
        object(),
    ]
    for value in nasty:
        frontmatter = {k: value for k in [*FULL, PUBLISH_KEY]}
        assert document_summary(frontmatter) is not None
        assert document_publish_targets(frontmatter) is not None
