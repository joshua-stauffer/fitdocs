"""Contract pins for the chart-catalog spec's appended values (task 1.1).

The four appended `ProblemCode` members are pinned by value and by relative
order, and by their position after chart-kit's 23 codes. Positions are
compared by index, never by slice, so a later append elsewhere in the enum
cannot red these tests. Task 3.1 appends the registry pins to this module.
"""

from __future__ import annotations

from fitdocs.render.charts.kit.problems import ProblemCode

_CATALOG_CODES: tuple[tuple[str, str], ...] = (
    ("NEGATIVE_VALUE", "negative_value"),
    ("VALUE_ORDER", "value_order"),
    ("SHARED_UNIT", "shared_unit"),
    ("CHANNEL_UNIT", "channel_unit"),
)

_CORE_CODE_COUNT = 23


def _index(name: str) -> int:
    return list(ProblemCode).index(ProblemCode[name])


def test_the_four_codes_are_members_with_their_stable_values() -> None:
    for name, value in _CATALOG_CODES:
        assert ProblemCode[name].value == value
        assert ProblemCode(value) is ProblemCode[name]


def test_the_four_codes_keep_their_relative_order() -> None:
    indexes = [_index(name) for name, _ in _CATALOG_CODES]
    assert indexes == sorted(indexes)
    assert len(set(indexes)) == 4


def test_the_four_codes_all_come_after_chart_kits_twenty_three() -> None:
    last_core = _index("STACK_INCOMPLETE")
    assert last_core == _CORE_CODE_COUNT - 1
    for name, _ in _CATALOG_CODES:
        assert _index(name) > last_core, name


def test_nothing_was_inserted_in_front_of_the_first_catalog_code() -> None:
    # Exactly 23 members precede it, so nothing sits between chart-kit's codes
    # and the catalog's first.
    first = _index("NEGATIVE_VALUE")
    assert first == _CORE_CODE_COUNT
