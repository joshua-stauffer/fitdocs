"""The publish template grammar and renderer (publish-core Req 4.4, 4.5, 5.7)."""

from __future__ import annotations

import dataclasses

import pytest

from fitdocs.publish.template import (
    Clause,
    MissingValue,
    Placeholder,
    TargetTemplates,
    Template,
    TemplateSyntaxError,
    Text,
    parse_template,
    render,
)

NAMES = ("x", "y", "dist_2", "km")


def parse(text: str) -> Template:
    return parse_template(text, names=NAMES)


def error_of(text: str) -> TemplateSyntaxError:
    with pytest.raises(TemplateSyntaxError) as info:
        parse(text)
    return info.value


# ---------------------------------------------------------------- structure


def test_empty_template_is_no_parts() -> None:
    assert parse("") == Template("", ())


def test_plain_text_is_one_text_part_and_keeps_source() -> None:
    t = parse("hello world")
    assert t.source == "hello world"
    assert t.parts == (Text("hello world"),)


def test_placeholder_between_text() -> None:
    assert parse("a {x} b").parts == (Text("a "), Placeholder("x"), Text(" b"))


def test_name_with_digits_and_underscore_in_set() -> None:
    assert parse("{dist_2}").parts == (Placeholder("dist_2"),)


def test_escapes_become_literal_braces_in_one_text_part() -> None:
    assert parse("{{a}}").parts == (Text("{a}"),)


def test_escaped_brace_is_not_a_placeholder() -> None:
    assert parse("{{x}}").parts == (Text("{x}"),)


def test_clause_holds_text_and_placeholders() -> None:
    assert parse("{?a {x} b}").parts == (
        Clause((Text("a "), Placeholder("x"), Text(" b"))),
    )


def test_clause_leading_space_text_is_kept() -> None:
    assert parse("{? {x}}").parts == (Clause((Text(" "), Placeholder("x"))),)


def test_clause_closes_on_single_brace_after_placeholder() -> None:
    assert parse("{?{x}}").parts == (Clause((Placeholder("x"),)),)


def test_clause_then_text_after_close() -> None:
    assert parse("{?{x}}tail").parts == (Clause((Placeholder("x"),)), Text("tail"))


def test_clause_with_two_placeholders() -> None:
    assert parse("{?{x}/{y}}").parts == (
        Clause((Placeholder("x"), Text("/"), Placeholder("y"))),
    )


def test_escaped_close_inside_clause_is_text_not_closer() -> None:
    # {?{x}}}} scans left to right: the placeholder, then `}}` (a literal
    # brace inside the clause), then `}` closing the clause.
    assert parse("{?{x}}}}").parts == (Clause((Placeholder("x"), Text("}"))),)


def test_escaped_open_inside_clause_is_text() -> None:
    assert parse("{?{{{x}}").parts == (Clause((Text("{"), Placeholder("x"))),)


def test_double_brace_after_clause_text_is_escape_not_closer() -> None:
    assert parse("{?a}}{x}}").parts == (Clause((Text("a}"), Placeholder("x"))),)


def test_crlf_text_is_preserved() -> None:
    assert parse("a\r\n{x}").parts == (Text("a\r\n"), Placeholder("x"))


def test_template_parts_are_tuples_and_frozen() -> None:
    t = parse("{?{x}}")
    assert isinstance(t.parts, tuple)
    assert isinstance(t.parts[0], Clause) and isinstance(t.parts[0].parts, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.source = "z"  # type: ignore[misc]


def test_target_templates_pair() -> None:
    title, desc = parse("{x}"), parse("{y}")
    pair = TargetTemplates(title, desc)
    assert pair.title is title and pair.description is desc
    assert [f.name for f in dataclasses.fields(TargetTemplates)] == [
        "title",
        "description",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        pair.title = desc  # type: ignore[misc]


# ------------------------------------------------------------------- errors


@pytest.mark.parametrize(
    ("text", "line", "column", "reason_part"),
    [
        ("a}", 1, 2, "lone '}'"),
        ("a{", 1, 2, "unterminated placeholder"),
        ("}}}", 1, 3, "lone '}'"),
        ("{x", 1, 1, "unterminated placeholder"),
        ("ab {x", 1, 4, "unterminated placeholder"),
        ("{pace}", 1, 1, "unknown placeholder {pace}"),
        ("ab {pace}", 1, 4, "unknown placeholder {pace}"),
        ("{ x}", 1, 1, "invalid placeholder"),
        ("{x }", 1, 1, "invalid placeholder"),
        ("a{ x }", 1, 2, "invalid placeholder"),
        ("{}", 1, 1, "invalid placeholder"),
        ("{X}", 1, 1, "invalid placeholder"),
        ("{1x}", 1, 1, "invalid placeholder"),
        ("{x{y}}", 1, 1, "invalid placeholder"),
        ("{?}", 1, 1, "at least one placeholder"),
        ("ab {?plain}", 1, 4, "at least one placeholder"),
        ("{?{x}{?{y}}}", 1, 6, "another clause"),
        ("{?a {?b}}", 1, 5, "another clause"),
        ("{?{x}", 1, 1, "unterminated optional clause"),
        ("ab {?{x} cd", 1, 4, "unterminated optional clause"),
        ("{?{x}}}", 1, 1, "unterminated optional clause"),
        ("{?{x}} }", 1, 8, "lone '}'"),
        ("{?{pace}}", 1, 3, "unknown placeholder {pace}"),
    ],
)
def test_syntax_error_position_and_reason(
    text: str, line: int, column: int, reason_part: str
) -> None:
    err = error_of(text)
    assert (err.line, err.column) == (line, column)
    assert reason_part in err.reason
    assert str(err) == f"line {line}, column {column}: {err.reason}"


def test_syntax_error_is_a_value_error() -> None:
    assert isinstance(error_of("}"), ValueError)


def test_position_resets_column_after_newline() -> None:
    err = error_of("first\nsecond {pace}\nthird")
    assert (err.line, err.column) == (2, 8)


def test_position_on_third_line_start_of_line() -> None:
    err = error_of("a\nb\n}")
    assert (err.line, err.column) == (3, 1)


def test_position_with_crlf_counts_only_lf_as_line_break() -> None:
    err = error_of("a\r\nb {pace}")
    assert (err.line, err.column) == (2, 3)


def test_position_after_crlf_lone_brace_at_line_start() -> None:
    err = error_of("a\r\n}")
    assert (err.line, err.column) == (2, 1)


def test_unterminated_clause_position_is_clause_start_on_later_line() -> None:
    err = error_of("one\n{?{x}\ntwo")
    assert (err.line, err.column) == (2, 1)


def test_name_set_decides_known_names() -> None:
    assert parse_template("{pace}", names=("pace",)).parts == (Placeholder("pace"),)
    with pytest.raises(TemplateSyntaxError):
        parse_template("{pace}", names=())


def test_name_outside_the_pattern_is_rejected_even_if_in_the_set() -> None:
    with pytest.raises(TemplateSyntaxError) as info:
        parse_template("{Pace}", names=("Pace",))
    assert (info.value.line, info.value.column) == (1, 1)


def test_first_error_wins_left_to_right() -> None:
    err = error_of("{pace} }")
    assert (err.line, err.column) == (1, 1)


# ------------------------------------------------------------------- render


def test_render_fills_placeholders() -> None:
    assert render(parse("{x} and {y}!"), {"x": "1", "y": "2"}) == "1 and 2!"


def test_render_empty_template_is_empty_string() -> None:
    assert render(parse(""), {}) == ""


def test_render_escapes_as_literal_braces() -> None:
    assert render(parse("{{{x}}}"), {"x": "7"}) == "{7}"


def test_render_zero_string_is_a_value_not_absent() -> None:
    assert render(parse("{x}"), {"x": "0"}) == "0"


def test_render_empty_string_is_a_value_not_absent() -> None:
    assert render(parse("a{x}b"), {"x": ""}) == "ab"


def test_render_absent_bare_placeholder_is_missing_not_zero() -> None:
    assert render(parse("a {x} b"), {"x": None}) == MissingValue("x")


def test_render_key_not_in_mapping_is_missing() -> None:
    assert render(parse("{x}"), {}) == MissingValue("x")


def test_render_reports_first_missing_left_to_right() -> None:
    assert render(parse("{y} {x}"), {"x": None, "y": None}) == MissingValue("y")
    assert render(parse("{x} {y}"), {"x": None, "y": None}) == MissingValue("x")


def test_render_skips_present_and_reports_later_missing() -> None:
    assert render(parse("{x} {y}"), {"x": "1", "y": None}) == MissingValue("y")


def test_render_clause_with_all_values_includes_text() -> None:
    assert render(parse("a{? ({x}/{y})}"), {"x": "1", "y": "2"}) == "a (1/2)"


def test_render_clause_with_absent_value_renders_nothing() -> None:
    assert render(parse("a{? ({x})}b"), {"x": None}) == "ab"


def test_render_clause_with_any_absent_value_renders_nothing() -> None:
    t = parse("a{?{x}/{y}}b")
    assert render(t, {"x": "1", "y": None}) == "ab"
    assert render(t, {"x": None, "y": "2"}) == "ab"
    assert render(t, {"x": "1", "y": "2"}) == "a1/2b"


def test_render_clause_absent_value_is_not_zero_filled() -> None:
    assert render(parse("[{?{x}}]"), {"x": None}) == "[]"


def test_render_absent_clause_value_does_not_make_template_missing() -> None:
    assert render(parse("{?{x}}{y}"), {"x": None, "y": "2"}) == "2"


def test_render_missing_bare_after_dropped_clause_is_still_missing() -> None:
    assert render(parse("{?{x}}{y}"), {"x": None, "y": None}) == MissingValue("y")


def test_render_clause_keeps_escaped_close_text() -> None:
    t = parse("{?{x}}}}z")
    assert render(t, {"x": "1"}) == "1}z"
    assert render(t, {"x": None}) == "z"


def test_render_values_are_inserted_literally_never_reparsed() -> None:
    hostile = "{x} {{ }} {?{y}} }"
    assert render(parse("<{x}>"), {"x": hostile, "y": "BAD"}) == f"<{hostile}>"
    assert render(parse("{?[{x}]}"), {"x": hostile, "y": "BAD"}) == f"[{hostile}]"


def test_render_preserves_multiline_and_crlf_text() -> None:
    assert render(parse("{x}\r\n{y}\n"), {"x": "1", "y": "2"}) == "1\r\n2\n"


def test_render_is_repeatable() -> None:
    t = parse("{x}{?{y}}")
    values = {"x": "1", "y": None}
    assert render(t, values) == render(t, values) == "1"


def test_render_clause_key_missing_from_mapping_renders_nothing() -> None:
    assert render(parse("a{?[{x}]}b"), {}) == "ab"
    assert render(parse("{?{x}/{y}}"), {"x": "1"}) == ""


def test_render_clause_empty_string_is_a_value() -> None:
    assert render(parse("a{?[{x}]}b"), {"x": ""}) == "a[]b"


def test_stray_brace_reason_is_one_line_and_omits_following_text() -> None:
    err = error_of("oops { here\nsecret paragraph } tail")
    assert (err.line, err.column) == (1, 6)
    assert "\n" not in err.reason
    assert "secret" not in err.reason and "here" not in err.reason
    assert "invalid placeholder" in err.reason
    assert "\n" not in str(err)
