"""Strict directive parsing: the text as written, every mistake named."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import pytest
import yaml

from fitdocs.dashboards import directive as directive_module
from fitdocs.dashboards.directive import (
    MAX_ID_LENGTH,
    OPTIONAL_KEYS,
    REQUIRED_KEYS,
    Directive,
    Mode,
    parse_directive,
)
from fitdocs.dashboards.problems import DashboardCode, Problem, Source
from tests.dashboards._helpers import directive_block

OPEN_LINE = 40
PAGE = "wk"
ACCEPTED = (
    "id",
    "kind",
    "mode",
    "title",
    "sql",
    "channels",
    "options",
    "window",
    "show_rows",
)

BASE: list[tuple[str, str]] = [
    ("id", "tile"),
    ("kind", "bar"),
    ("mode", "relative"),
    ("title", "Weekly km"),
    ("sql", "|\n  SELECT 1 AS a"),
]


def body_of(keys: Sequence[tuple[str, str]]) -> str:
    """The directive body: the block's lines between opener and closer."""
    lines = directive_block(keys).splitlines(keepends=True)
    return "".join(lines[1:-1])


def keys_with(**replace: str) -> list[tuple[str, str]]:
    """BASE with the named keys' values replaced, order kept."""
    unknown = set(replace) - {key for key, _ in BASE}
    assert not unknown, unknown
    return [(key, replace.get(key, value)) for key, value in BASE]


def parse(keys: Sequence[tuple[str, str]]) -> Directive | tuple[Problem, ...]:
    return parse_directive(body_of(keys), open_line=OPEN_LINE, page=PAGE)


def parse_ok(keys: Sequence[tuple[str, str]]) -> Directive:
    result = parse(keys)
    assert isinstance(result, Directive), result
    return result


def parse_bad(keys: Sequence[tuple[str, str]]) -> tuple[Problem, ...]:
    result = parse(keys)
    assert isinstance(result, tuple), result
    assert result, "a refusal carries at least one problem"
    return result


def only(problems: tuple[Problem, ...]) -> Problem:
    assert len(problems) == 1, problems
    return problems[0]


def test_accepted_key_constants_are_the_design_order() -> None:
    assert REQUIRED_KEYS + OPTIONAL_KEYS == ACCEPTED
    assert MAX_ID_LENGTH == 64


# -- a valid directive -------------------------------------------------------


def test_valid_directive_fields() -> None:
    directive = parse_ok(
        [
            ("id", "tile"),
            ("kind", "bar"),
            ("mode", "frozen"),
            ("title", "Weekly km"),
            ("sql", "|\n  SELECT 1 AS a"),
            ("channels", "\n  y: km\n  x: day"),
            ("options", "\n  color: red\n  n: 5\n  flag: no"),
            ("window", "last 12 weeks"),
            ("show_rows", "true"),
        ]
    )
    assert directive == Directive(
        chart_id="tile",
        kind="bar",
        mode=Mode.FROZEN,
        title="Weekly km",
        sql="SELECT 1 AS a\n",
        channels={"y": "km", "x": "day"},
        options={"color": "red", "n": "5", "flag": "no"},
        window="last 12 weeks",
        show_rows=True,
        line=OPEN_LINE,
    )
    assert list(directive.channels) == ["y", "x"]


def test_optional_keys_absent_are_none_empty_and_false() -> None:
    directive = parse_ok(BASE)
    assert directive.mode is Mode.RELATIVE
    assert directive.window is None
    assert directive.show_rows is False
    assert dict(directive.channels) == {}
    assert dict(directive.options) == {}


def test_keys_may_come_in_any_order() -> None:
    directive = parse_ok(list(reversed(BASE)))
    assert directive.chart_id == "tile"
    assert directive.sql == "SELECT 1 AS a\n"


@pytest.mark.parametrize("title", ["", '""', "''"])
def test_empty_title_is_passed_through(title: str) -> None:
    directive = parse_ok(keys_with(title=title))
    assert directive.title == ""


@pytest.mark.parametrize("show_rows, expected", [("true", True), ("false", False)])
def test_show_rows_literals(show_rows: str, expected: bool) -> None:
    keys = [*BASE, ("show_rows", show_rows)]
    assert parse_ok(keys).show_rows is expected


def test_empty_channels_mapping_is_valid() -> None:
    directive = parse_ok([*BASE, ("channels", "{}"), ("options", "{}")])
    assert dict(directive.channels) == {}


# -- 4.1: the text as written ------------------------------------------------


@pytest.mark.parametrize("chart_id", ["2026-10-11", "012"])
def test_numeric_looking_ids_are_the_strings_written(chart_id: str) -> None:
    directive = parse_ok(keys_with(id=chart_id))
    assert directive.chart_id == chart_id
    assert isinstance(directive.chart_id, str)


@pytest.mark.parametrize(
    "mode, written",
    [
        ("no", "'no'"),
        ("off", "'off'"),
        ("true", "'true'"),
        ("1", "'1'"),
        ("~", "'~'"),
        ("Relative", "'Relative'"),
        ("", "''"),
    ],
)
def test_mode_reaches_validation_as_the_string_written(mode: str, written: str) -> None:
    problem = only(parse_bad(keys_with(mode=mode)))
    assert problem.code == DashboardCode.MODE_VALUE.value
    assert written in problem.message
    assert problem.accepted == ("relative", "frozen")
    assert problem.line == OPEN_LINE + 1 + 2


def test_numeric_and_date_values_stay_text_in_mappings() -> None:
    directive = parse_ok(
        [*BASE, ("options", "\n  d: 2026-10-11\n  z: 012\n  b: yes\n  n: null")]
    )
    assert dict(directive.options) == {
        "d": "2026-10-11",
        "z": "012",
        "b": "yes",
        "n": "null",
    }


@pytest.mark.parametrize(
    "indicator, expected",
    [("|", "SELECT 1\n"), ("|-", "SELECT 1"), ("|+", "SELECT 1\n\n")],
)
def test_literal_block_sql_in_every_chomping(indicator: str, expected: str) -> None:
    sql = f"{indicator}\n  SELECT 1" + ("\n" if indicator == "|+" else "")
    assert parse_ok(keys_with(sql=sql)).sql == expected


def test_sql_text_is_kept_exactly_including_comments_and_indent() -> None:
    sql = "|\n  SELECT a -- c\n    FROM t # not a comment\n  WHERE x"
    assert (
        parse_ok(keys_with(sql=sql)).sql
        == "SELECT a -- c\n  FROM t # not a comment\nWHERE x\n"
    )


# -- 4.2: syntax, shape, duplicates, tags, anchors ---------------------------


@pytest.mark.parametrize("index", [0, 2, 4])
def test_yaml_syntax_error_is_reported_at_the_page_line(index: int) -> None:
    keys = keys_with()
    keys[index] = ("title", "a: b")  # a second mapping value on one line
    problem = only(parse_bad(keys))
    assert problem.code == DashboardCode.YAML_SYNTAX.value
    assert problem.line == OPEN_LINE + index + 1


def test_yaml_syntax_error_on_body_line_three() -> None:
    keys = [("id", "tile"), ("kind", "bar"), ("title", "a: b"), *BASE[2:]]
    problem = only(parse_bad(keys))
    assert problem.code == DashboardCode.YAML_SYNTAX.value
    assert problem.line == OPEN_LINE + 3
    assert problem.source is Source.DASHBOARD
    assert problem.page == PAGE


@pytest.mark.parametrize(
    "body",
    ['id: "\\UFFFFFFFF"\n', "id: " + "[" * 5000 + "]" * 5000 + "\n"],
    ids=["overflow", "recursion"],
)
def test_a_body_pyyaml_cannot_load_is_a_syntax_problem_not_a_raise(body: str) -> None:
    result = parse_directive(body, open_line=OPEN_LINE, page=PAGE)
    assert isinstance(result, tuple)
    problem = only(result)
    assert problem.code == DashboardCode.YAML_SYNTAX.value
    assert problem.line == OPEN_LINE  # no mark to report: the opening fence


@pytest.mark.parametrize("body", ["- a\n- b\n", "just text\n", "", "[a, b]\n"])
def test_a_body_that_is_not_a_mapping_is_refused(body: str) -> None:
    result = parse_directive(body, open_line=OPEN_LINE, page=PAGE)
    assert isinstance(result, tuple)
    problem = only(result)
    assert problem.code == DashboardCode.YAML_SHAPE.value
    assert problem.line == OPEN_LINE + 1


def test_duplicate_key_is_named_at_its_second_line() -> None:
    keys = [BASE[0], BASE[1], ("title", "First"), BASE[2], ("title", "Second")]
    problem = only(parse_bad([*keys, BASE[4]]))
    assert problem.code == DashboardCode.DUPLICATE_KEY.value
    assert "'title'" in problem.message
    assert problem.line == OPEN_LINE + 1 + 4


def test_duplicate_key_inside_a_mapping_is_refused() -> None:
    options = "\n  color: red\n  size: 3\n  color: blue"
    problem = only(parse_bad([*BASE, ("options", options)]))
    assert problem.code == DashboardCode.DUPLICATE_KEY.value
    assert "'color'" in problem.message
    assert problem.line == OPEN_LINE + 10


@pytest.mark.parametrize(
    "key, value, index",
    [
        ("id", "!!int 5", 0),
        ("kind", "!!str bar", 1),
        ("!!str mode", "relative", 2),
        ("!!int title", "x", 3),
        ("!local title", "x", 3),
        ("title", "!!binary aGk=", 3),
    ],
)
def test_explicit_tags_are_refused(key: str, value: str, index: int) -> None:
    keys = keys_with()
    keys[index] = (key, value)
    problem = only(parse_bad(keys))
    assert problem.code == DashboardCode.YAML_SHAPE.value
    assert "tag" in problem.message
    assert problem.line == OPEN_LINE + 1 + index


def test_an_explicit_tag_on_a_nested_collection_is_refused() -> None:
    problem = only(parse_bad([*BASE, ("options", "!!map\n  a: b")]))
    assert problem.code == DashboardCode.YAML_SHAPE.value
    assert problem.line == OPEN_LINE + 7


def test_anchor_and_alias_are_each_named_at_their_line() -> None:
    keys = keys_with(kind="&t bar", title="*t")
    problems = parse_bad(keys)
    assert [p.code for p in problems] == [DashboardCode.YAML_SHAPE.value] * 2
    anchor, alias = problems
    assert "anchor" in anchor.message
    assert anchor.line == OPEN_LINE + 2
    assert "alias" in alias.message
    assert alias.line == OPEN_LINE + 4


def test_an_alias_with_no_anchor_is_a_shape_problem_not_a_syntax_one() -> None:
    problem = only(parse_bad(keys_with(kind="*nowhere")))
    assert problem.code == DashboardCode.YAML_SHAPE.value
    assert "alias" in problem.message


def test_a_non_text_key_is_refused() -> None:
    body = body_of(BASE) + "? [a, b]\n: c\n"
    result = parse_directive(body, open_line=OPEN_LINE, page=PAGE)
    assert isinstance(result, tuple)
    problem = only(result)
    assert problem.code == DashboardCode.YAML_SHAPE.value
    assert problem.line == OPEN_LINE + 7


def test_a_scalar_that_resolves_to_a_non_text_type_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Give the loader the stock resolvers back: `no` then resolves to a bool.
    monkeypatch.setattr(
        directive_module._StrictLoader,
        "yaml_implicit_resolvers",
        yaml.SafeLoader.yaml_implicit_resolvers,
    )
    problems = parse_bad(keys_with(mode="no", id="2026-10-11"))
    assert [(p.code, p.line) for p in problems] == [
        (DashboardCode.YAML_SHAPE.value, OPEN_LINE + 1),
        (DashboardCode.YAML_SHAPE.value, OPEN_LINE + 3),
    ]
    assert all("type" in p.message for p in problems)


# -- 4.3: required and accepted keys -----------------------------------------


def test_missing_and_unknown_keys_come_in_order_with_accepted() -> None:
    keys = [
        ("sql", "|\n  SELECT 1"),
        ("zeta", "1"),
        ("id", "tile"),
        ("alpha", "2"),
        ("mode", "relative"),
    ]
    problems = parse_bad(keys)
    assert [(p.code, p.option) for p in problems] == [
        (DashboardCode.MISSING_KEY.value, "kind"),
        (DashboardCode.MISSING_KEY.value, "title"),
        (DashboardCode.UNKNOWN_KEY.value, "alpha"),
        (DashboardCode.UNKNOWN_KEY.value, "zeta"),
    ]
    assert all(p.accepted == ACCEPTED for p in problems)
    for problem in problems:
        assert f"`{problem.option}`" in problem.message
    missing_kind, missing_title, alpha, zeta = problems
    assert missing_kind.line == missing_title.line == OPEN_LINE
    assert alpha.line == OPEN_LINE + 1 + 4  # sql block is two lines, zeta, id, alpha
    assert zeta.line == OPEN_LINE + 1 + 2


def test_every_required_key_missing_alone_is_named() -> None:
    for name in REQUIRED_KEYS:
        problem = only(parse_bad([(k, v) for k, v in BASE if k != name]))
        assert problem.code == DashboardCode.MISSING_KEY.value
        assert f"`{name}`" in problem.message


# -- 4.4: the chart id -------------------------------------------------------


def test_ids_of_64_characters_are_valid_and_65_are_not() -> None:
    long_id = "a" * 31 + "-" + "b" * 32
    assert len(long_id) == 64
    assert parse_ok(keys_with(id=long_id)).chart_id == long_id
    problem = only(parse_bad(keys_with(id=long_id + "c")))
    assert problem.code == DashboardCode.ID_GRAMMAR.value
    assert problem.line == OPEN_LINE + 1


@pytest.mark.parametrize(
    "chart_id", ["Tile", "tiLe", "a--b", "-a", "a-", "a_b", "a b", "é", ""]
)
def test_ids_outside_the_grammar_are_refused_with_the_rule(chart_id: str) -> None:
    problem = only(parse_bad(keys_with(id=chart_id)))
    assert problem.code == DashboardCode.ID_GRAMMAR.value
    assert "lowercase" in problem.message
    assert "64" in problem.message


def test_a_non_scalar_id_is_an_id_problem() -> None:
    problem = only(parse_bad(keys_with(id="[a, b]")))
    assert problem.code == DashboardCode.ID_GRAMMAR.value


# -- 4.7: the sql style ------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        ">\n  SELECT 1",
        ">-\n  SELECT 1",
        "SELECT 1",
        "SELECT 1 # x",
        '"SELECT 1"',
        "'SELECT 1'",
        "",
        "[SELECT 1]",
    ],
)
def test_sql_other_than_a_literal_block_is_refused(sql: str) -> None:
    keys = [BASE[0], BASE[1], ("sql", sql), BASE[2], BASE[3]]
    problem = only(parse_bad(keys))
    assert problem.code == DashboardCode.SQL_STYLE.value
    assert "fold" in problem.message
    assert problem.line == OPEN_LINE + 1 + 2


# -- 4.9: field shapes -------------------------------------------------------


@pytest.mark.parametrize(
    "title",
    ['"a\\nb"', "|\n  a\n  b", '"a\\rb"'],
)
def test_multi_line_title_is_refused(title: str) -> None:
    problem = only(parse_bad(keys_with(title=title)))
    assert problem.code == DashboardCode.FIELD_VALUE.value
    assert "`title`" in problem.message
    assert problem.line == OPEN_LINE + 1 + 3


def test_a_collection_title_is_refused() -> None:
    problem = only(parse_bad(keys_with(title="[a]")))
    assert problem.code == DashboardCode.FIELD_VALUE.value
    assert "`title`" in problem.message


def test_multi_line_window_is_refused() -> None:
    problem = only(parse_bad([*BASE, ("window", "|\n  a\n  b")]))
    assert problem.code == DashboardCode.FIELD_VALUE.value
    assert "`window`" in problem.message
    assert problem.line == OPEN_LINE + 7


@pytest.mark.parametrize("value", ["yes", "no", "True", "1", "on", "", "~", "'maybe'"])
def test_show_rows_other_than_true_or_false_is_refused(value: str) -> None:
    problem = only(parse_bad([*BASE, ("show_rows", value)]))
    assert problem.code == DashboardCode.FIELD_VALUE.value
    assert "`show_rows`" in problem.message
    assert problem.line == OPEN_LINE + 7


@pytest.mark.parametrize(
    "name, value",
    [
        ("channels", "[a, b]"),
        ("channels", "\n  - a\n  - b"),
        ("channels", "x"),
        ("channels", ""),
        ("channels", "\n  y:\n    - km"),
        ("channels", "\n  y: |\n    a\n    b"),
        ("options", "\n  color:\n    red: 1"),
        ("options", "\n  color: [red]"),
        ("options", '\n  color: "a\\nb"'),
        ("options", "x"),
        ("channels", "\n  ? |\n    a\n    b\n  : v"),
        ("options", "\n  ? |\n    a\n    b\n  : v"),
    ],
)
def test_channels_and_options_must_map_names_to_single_line_scalars(
    name: str, value: str
) -> None:
    problem = only(parse_bad([*BASE, (name, value)]))
    assert problem.code == DashboardCode.FIELD_VALUE.value
    assert f"`{name}`" in problem.message
    assert problem.line == OPEN_LINE + 7


def test_a_collection_kind_is_refused() -> None:
    problem = only(parse_bad(keys_with(kind="[bar]")))
    assert problem.code == DashboardCode.FIELD_VALUE.value
    assert "`kind`" in problem.message


# -- 4.10: only declared keys are read; kind is passed through ---------------


def test_an_unregistered_kind_passes_through_unchanged() -> None:
    assert parse_ok(keys_with(kind="no-such-kind")).kind == "no-such-kind"


def test_problems_of_one_directive_are_returned_together_in_key_order() -> None:
    keys = keys_with(id="Bad", mode="no", title='"a\\nb"')
    keys.append(("show_rows", "yes"))
    problems = parse_bad(keys)
    assert [(p.code, p.line) for p in problems] == [
        (DashboardCode.ID_GRAMMAR.value, OPEN_LINE + 1),
        (DashboardCode.MODE_VALUE.value, OPEN_LINE + 3),
        (DashboardCode.FIELD_VALUE.value, OPEN_LINE + 4),
        (DashboardCode.FIELD_VALUE.value, OPEN_LINE + 7),
    ]
    assert all(p.source is Source.DASHBOARD and p.page == PAGE for p in problems)


# -- the SQL fingerprint -----------------------------------------------------


def test_sql_sha256_of_a_known_string() -> None:
    directive = parse_ok(keys_with(sql="|-\n  abc"))
    assert directive.sql == "abc"
    expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert directive.sql_sha256 == expected


def test_sql_sha256_is_over_the_utf8_bytes() -> None:
    directive = parse_ok(keys_with(sql="|-\n  SELECT 'é'"))
    assert directive.sql_sha256 == (
        "d3294563d51ee68e13015d1c86c1829e4b28d91642986e3ddfddd12f1a4b6d34"
    )


def parse_scanned(keys: Sequence[tuple[str, str]]) -> Directive:
    """Parse a body as the scanner hands it over: no newline after the last line."""
    body = body_of(keys)
    assert body.endswith("\n")
    result = parse_directive(body[:-1], open_line=OPEN_LINE, page=PAGE)
    assert isinstance(result, Directive), result
    return result


def test_sql_sha256_ignores_the_final_newline_a_following_key_gives_the_block() -> None:
    others = [(k, v) for k, v in BASE if k != "sql"]
    last = parse_scanned([*others, ("sql", "|\n  select 1")])
    first = parse_scanned([("sql", "|\n  select 1"), *others])
    assert (last.sql, first.sql) == ("select 1", "select 1\n")
    assert last.sql_sha256 == first.sql_sha256


def test_sql_sha256_strips_only_trailing_line_breaks() -> None:
    inner = parse_scanned(keys_with(sql="|\n  select 1\n\n  from t"))
    assert inner.sql == "select 1\n\nfrom t"
    mid = parse_ok(keys_with(sql="|\n  select 1\n\n  from t"))
    assert mid.sql_sha256 == inner.sql_sha256
    assert inner.sql_sha256 == hashlib.sha256(b"select 1\n\nfrom t").hexdigest()
    blanks = parse_ok(keys_with(sql="|+\n  select 1\n\n"))
    assert blanks.sql.endswith("\n\n"), "the keep indicator holds blank lines"
    assert blanks.sql_sha256 == hashlib.sha256(b"select 1").hexdigest()
    led = parse_scanned(keys_with(sql="|\n\n  select 1"))
    assert led.sql == "\nselect 1", "a leading blank line is part of the SQL"
    assert led.sql_sha256 == hashlib.sha256(b"\nselect 1").hexdigest()
    spaced = parse_ok(keys_with(sql="|\n  select 1   "))
    assert spaced.sql_sha256 == hashlib.sha256(b"select 1   ").hexdigest()


# -- key problems and field problems together ----------------------------------


def test_key_and_field_problems_are_returned_together_in_order() -> None:
    keys = [
        ("sql", "|\n  SELECT 1"),
        ("zeta", "1"),
        ("id", "Bad"),
        ("mode", "relative"),
        ("title", '"a\\nb"'),
        ("show_rows", "yes"),
    ]
    problems = parse_bad(keys)
    assert [(p.code, p.line, p.option) for p in problems] == [
        (DashboardCode.MISSING_KEY.value, OPEN_LINE, "kind"),
        (DashboardCode.UNKNOWN_KEY.value, OPEN_LINE + 3, "zeta"),
        (DashboardCode.ID_GRAMMAR.value, OPEN_LINE + 4, "id"),
        (DashboardCode.FIELD_VALUE.value, OPEN_LINE + 6, "title"),
        (DashboardCode.FIELD_VALUE.value, OPEN_LINE + 7, "show_rows"),
    ]


def test_key_and_field_problems_carry_the_chart_id_when_it_is_valid() -> None:
    keys = [
        ("id", "tile"),
        ("mode", "no"),
        ("title", '"a\\nb"'),
        ("sql", ">\n  SELECT 1"),
        ("zeta", "1"),
        ("show_rows", "yes"),
    ]
    problems = parse_bad(keys)
    assert [p.code for p in problems] == [
        DashboardCode.MISSING_KEY.value,
        DashboardCode.UNKNOWN_KEY.value,
        DashboardCode.MODE_VALUE.value,
        DashboardCode.FIELD_VALUE.value,
        DashboardCode.SQL_STYLE.value,
        DashboardCode.FIELD_VALUE.value,
    ]
    assert [p.chart for p in problems] == ["tile"] * 6
    assert [p.option for p in problems] == [
        "kind",
        "zeta",
        "mode",
        "title",
        "sql",
        "show_rows",
    ]


def test_an_invalid_id_is_not_named_as_the_chart() -> None:
    problem = only(parse_bad(keys_with(id="Bad")))
    assert problem.chart is None
    assert "'Bad'" in problem.message


@pytest.mark.parametrize("chart_id", ["[a, b]", "{a: b}"])
def test_a_non_scalar_id_message_does_not_print_none(chart_id: str) -> None:
    problem = only(parse_bad(keys_with(id=chart_id)))
    assert problem.code == DashboardCode.ID_GRAMMAR.value
    assert "None" not in problem.message
    assert "lowercase" in problem.message


# -- text kept byte for byte -------------------------------------------------


def test_quoted_values_keep_their_whitespace_and_case() -> None:
    directive = parse_ok(
        [
            ("id", "tile"),
            ("kind", '" Bar_Chart "'),
            ("mode", "relative"),
            ("title", '" Weekly km "'),
            ("sql", "|\n  SELECT 1"),
            ("channels", '\n  " Y ": " Km "'),
            ("options", '\n  " C ": " Red "'),
            ("window", '" Last 12 weeks "'),
        ]
    )
    assert directive.kind == " Bar_Chart "
    assert directive.title == " Weekly km "
    assert directive.window == " Last 12 weeks "
    assert dict(directive.channels) == {" Y ": " Km "}
    assert dict(directive.options) == {" C ": " Red "}


def test_a_folded_plain_title_is_accepted_as_one_line() -> None:
    directive = parse_ok(keys_with(title="a\n  b"))
    assert directive.title == "a b"


# -- page lines count "\n" only ----------------------------------------------

BREAKS = ["\u2028", "\u2029", "\u0085", "\r"]


@pytest.mark.parametrize("brk", BREAKS)
def test_other_line_breaks_do_not_shift_a_syntax_error_line(brk: str) -> None:
    body = f'id: tile\ntitle: "a{brk}b"\nkind: x: y\n'
    result = parse_directive(body, open_line=OPEN_LINE, page=PAGE)
    assert isinstance(result, tuple)
    problem = only(result)
    assert problem.code == DashboardCode.YAML_SYNTAX.value
    assert problem.line == OPEN_LINE + 3


@pytest.mark.parametrize("brk", BREAKS)
def test_other_line_breaks_do_not_shift_a_key_problem_line(brk: str) -> None:
    keys = keys_with(title=f'"a{brk}b"')
    keys.append(("zeta", "1"))
    problems = parse_bad(keys)
    assert [(p.code, p.line) for p in problems] == [
        (DashboardCode.UNKNOWN_KEY.value, OPEN_LINE + 7)
    ]


@pytest.mark.parametrize("brk", BREAKS)
def test_a_control_character_error_is_reported_at_its_page_line(brk: str) -> None:
    body = f'id: tile\ntitle: "a{brk}b"\nkind: a\x01b\n'
    result = parse_directive(body, open_line=OPEN_LINE, page=PAGE)
    assert isinstance(result, tuple)
    problem = only(result)
    assert problem.code == DashboardCode.YAML_SYNTAX.value
    assert problem.line == OPEN_LINE + 3


# -- remaining branches --------------------------------------------------------


def test_a_second_document_is_a_syntax_problem_at_the_separator() -> None:
    body = "id: tile\n---\nkind: bar\n"
    result = parse_directive(body, open_line=OPEN_LINE, page=PAGE)
    assert isinstance(result, tuple)
    problem = only(result)
    assert problem.code == DashboardCode.YAML_SYNTAX.value
    assert problem.line == OPEN_LINE + 2


def test_a_non_mapping_body_is_reported_at_its_first_content_line() -> None:
    result = parse_directive("\n\n- a\n", open_line=OPEN_LINE, page=PAGE)
    assert isinstance(result, tuple)
    problem = only(result)
    assert problem.code == DashboardCode.YAML_SHAPE.value
    assert problem.line == OPEN_LINE + 3


def test_a_control_character_message_says_the_text_is_not_valid_yaml() -> None:
    result = parse_directive("id: a\x01b\n", open_line=OPEN_LINE, page=PAGE)
    assert isinstance(result, tuple)
    assert "not valid YAML" in only(result).message


def test_duplicate_keys_are_found_inside_sequences() -> None:
    problem = only(parse_bad([*BASE, ("options", "\n  - {a: 1, a: 2}")]))
    assert problem.code == DashboardCode.DUPLICATE_KEY.value
    assert problem.line == OPEN_LINE + 8


def test_the_same_key_in_different_mappings_is_not_a_duplicate() -> None:
    keys = [*BASE, ("channels", "\n  title: a"), ("options", "\n  title: b")]
    directive = parse_ok(keys)
    assert dict(directive.channels) == {"title": "a"}
    assert dict(directive.options) == {"title": "b"}


def test_a_non_scalar_mode_message_does_not_print_none() -> None:
    problem = only(parse_bad(keys_with(mode="[relative]")))
    assert problem.code == DashboardCode.MODE_VALUE.value
    assert "None" not in problem.message
    assert problem.accepted == ("relative", "frozen")


def test_channels_and_options_cannot_be_mutated() -> None:
    directive = parse_ok([*BASE, ("channels", "\n  y: km")])
    with pytest.raises(TypeError):
        directive.channels["y"] = "x"  # type: ignore[index]


def test_a_quoted_mode_with_spaces_is_not_trimmed_into_a_valid_one() -> None:
    problem = only(parse_bad(keys_with(mode='" relative "')))
    assert problem.code == DashboardCode.MODE_VALUE.value
    assert "' relative '" in problem.message


def test_a_collection_window_is_refused() -> None:
    problem = only(parse_bad([*BASE, ("window", "[a]")]))
    assert problem.code == DashboardCode.FIELD_VALUE.value
    assert "`window`" in problem.message
