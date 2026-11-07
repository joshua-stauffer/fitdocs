"""Parse and validate the post template (post-templates task 2.1).

Requirements 1.2, 1.4 to 1.15 and 5.5. Every rule has a fixture whose only
fault is that rule, and the expected problems are asserted as exact lists.
The two loading tests whose message comes from the operating system match its
start instead.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from fitdocs.layout import POST_TEMPLATE_FILE, post_template_path
from fitdocs.post_template.template import (
    PostTemplate,
    PostTemplateError,
    Variable,
    load_post_template,
    parse_post_template,
)
from fitdocs.publish.template import Placeholder, Text
from fitdocs.settings import SettingsError

_Make = Callable[[str], Path]
_PATH = Path("/data/post-template.toml")
_W = str(_PATH)

_VALID = """\
since = 2026-11-07
title = "Run {distance_km} {tempo}"
description = "{?Pace {pace_per_km}}\\nLong: {longest}"

[vars.tempo]
sql = "select 1"

[vars.longest]
sql = "select 2"
"""


def _parse(text: str) -> PostTemplate:
    return parse_post_template(text.encode("utf-8"), path=_PATH)


def _problems(text: str | bytes) -> list[str]:
    data = text if isinstance(text, bytes) else text.encode("utf-8")
    with pytest.raises(PostTemplateError) as caught:
        parse_post_template(data, path=_PATH)
    return list(caught.value.problems)


def _swap(old: str, new: str, *, base: str = _VALID) -> str:
    assert base.count(old) == 1, old
    return base.replace(old, new)


# --------------------------------------------------------------------------- #
# A valid file
# --------------------------------------------------------------------------- #


def test_a_valid_file_parses_into_its_parts() -> None:
    template = _parse(_VALID)
    assert template.path == _PATH
    assert template.since == date(2026, 11, 7)
    assert type(template.since) is date
    assert template.templates.title.source == "Run {distance_km} {tempo}"
    assert template.templates.description.source == (
        "{?Pace {pace_per_km}}\nLong: {longest}"
    )
    assert template.templates.title.parts[0] == Text("Run ")
    assert template.templates.title.parts[1] == Placeholder("distance_km")
    assert template.variables == (
        Variable("longest", "select 2"),
        Variable("tempo", "select 1"),
    )  # sorted by name, not file order


def test_an_absent_description_is_empty_text_and_absent_vars_are_an_empty_tuple() -> (
    None
):
    template = _parse('since = 2026-11-07\ntitle = "Run {distance_km}"\n')
    assert template.templates.description.source == ""
    assert template.templates.description.parts == ()
    assert template.variables == ()


def test_a_multiline_description_is_allowed_but_a_title_is_one_line() -> None:
    assert _parse(_VALID).templates.description.source.count("\n") == 1
    newline_title = _swap("Run {distance_km}", "Run\\n{distance_km}")
    assert _problems(newline_title) == [
        f"{_W}: title: must be one line, with no control character "
        "or line or paragraph separator"
    ]


def test_a_variable_used_in_only_one_key_is_used() -> None:
    only_description = _swap("Run {distance_km} {tempo}", "Run", base=_VALID)
    assert _problems(only_description) == [
        f"{_W}: vars.tempo: the variable is not used by title or description"
    ]
    only_title = _swap("\\nLong: {longest}", "", base=_VALID)
    assert _problems(only_title) == [
        f"{_W}: vars.longest: the variable is not used by title or description"
    ]


def test_a_variable_used_only_inside_a_clause_is_used() -> None:
    text = _swap("{?Pace {pace_per_km}}", "{?Pace {pace_per_km} {tempo}}")
    text = _swap("Run {distance_km} {tempo}", "Run", base=text)
    assert [v.name for v in _parse(text).variables] == ["longest", "tempo"]


# --------------------------------------------------------------------------- #
# 1.14: UTF-8 and TOML
# --------------------------------------------------------------------------- #


def test_invalid_utf8_is_refused_naming_the_file() -> None:
    assert _problems(b'since = 2026-11-07\ntitle = "\xff"\n') == [
        f"{_W}: is not valid UTF-8: 'utf-8' codec can't decode byte 0xff "
        "in position 28: invalid start byte"
    ]


def test_invalid_toml_is_refused_naming_the_file_and_the_place() -> None:
    assert _problems("since = 2026-11-07\ntitle = \n") == [
        f"{_W}: is not valid TOML: Invalid value (at line 2, column 9)"
    ]


# --------------------------------------------------------------------------- #
# 1.4, 1.5: keys
# --------------------------------------------------------------------------- #


def test_both_required_keys_missing_are_both_named() -> None:
    assert _problems("description = 'D'\n") == [
        f"{_W}: since: required key is missing",
        f"{_W}: title: required key is missing",
    ]


@pytest.mark.parametrize("missing", ["since", "title"])
def test_each_required_key_alone_is_required(missing: str) -> None:
    other = {"since": 'title = "T"\n', "title": "since = 2026-11-07\n"}[missing]
    assert _problems(other) == [f"{_W}: {missing}: required key is missing"]


def test_two_unknown_keys_are_each_named() -> None:
    text = _VALID + "\n[extra]\nx = 1\n"
    text = text.replace("since = 2026-11-07\n", "since = 2026-11-07\nzzz = 1\n")
    assert _problems(text) == [
        f"{_W}: zzz: not a recognized key",
        f"{_W}: extra: not a recognized key",
    ]


def test_a_missing_required_key_and_an_unknown_key_come_in_that_order() -> None:
    assert _problems('title = "T"\nzzz = 1\n') == [
        f"{_W}: since: required key is missing",
        f"{_W}: zzz: not a recognized key",
    ]


# --------------------------------------------------------------------------- #
# 1.6: since is a TOML date only
# --------------------------------------------------------------------------- #

_SINCE_MESSAGE = (
    "since: must be a TOML date without a time, written like since = 2026-11-07"
)


@pytest.mark.parametrize(
    "value",
    [
        "2026-11-07T10:00:00",  # local datetime (a date subclass)
        "2026-11-07T10:00:00Z",  # offset datetime
        "2026-11-07 10:00:00+01:00",
        "10:00:00",
        '"2026-11-07"',
        "20261107",
        "true",
    ],
)
def test_since_that_is_not_a_plain_date_is_refused(value: str) -> None:
    text = _swap("2026-11-07", value)
    assert _problems(text) == [f"{_W}: {_SINCE_MESSAGE}"]


# --------------------------------------------------------------------------- #
# 1.7 to 1.10: title and description
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("key", ["title", "description"])
def test_non_text_is_refused(key: str) -> None:
    text = _VALID.replace(
        next(line for line in _VALID.splitlines() if line.startswith(key)),
        f"{key} = 5",
    )
    assert _problems(text) == [f"{_W}: {key}: must be text"]


@pytest.mark.parametrize("char", ["\\n", "\\u2028", "\\u2029", "\\u0007", "\\r"])
def test_a_title_with_a_control_character_or_separator_is_refused(char: str) -> None:
    text = _swap("Run {distance_km}", f"Run{char}{{distance_km}}")
    assert _problems(text) == [
        f"{_W}: title: must be one line, with no control character "
        "or line or paragraph separator"
    ]


def test_a_description_may_hold_newlines_and_separators() -> None:
    text = _swap("\\nLong", "\\u2028\\r\\nLong")
    assert " " in _parse(text).templates.description.source


@pytest.mark.parametrize("marker", ["<!--", "-->", "--!>"])
@pytest.mark.parametrize("key", ["title", "description"])
def test_a_comment_marker_in_the_text_is_refused(key: str, marker: str) -> None:
    old = "Run {distance_km}" if key == "title" else "Long:"
    text = _swap(old, f"{old} {marker}")
    assert _problems(text) == [
        f"{_W}: {key}: must not contain {marker!r}, "
        "which can damage the page's region markers"
    ]


@pytest.mark.parametrize(
    ("old", "new", "problem"),
    [
        (
            "Run {distance_km}",
            "<!-- Run {distance_km}",
            "title: must not contain '<!--', "
            "which can damage the page's region markers",
        ),
        (
            "Long:",
            "Long: -->",
            "description: must not contain '-->', "
            "which can damage the page's region markers",
        ),
        (
            "Run {distance_km}",
            "Run\\n{distance_km}",
            "title: must be one line, with no control character "
            "or line or paragraph separator",
        ),
    ],
)
def test_a_text_problem_does_not_hide_an_unused_variable(
    old: str, new: str, problem: str
) -> None:
    text = _swap(old, new) + "\n[vars.spare]\nsql = 'select 3'\n"
    assert _problems(text) == [
        f"{_W}: {problem}",
        f"{_W}: vars.spare: the variable is not used by title or description",
    ]


def test_two_markers_in_one_key_are_both_named() -> None:
    text = _swap("Long:", "Long: <!-- -->")
    assert _problems(text) == [
        f"{_W}: description: must not contain '<!--', "
        "which can damage the page's region markers",
        f"{_W}: description: must not contain '-->', "
        "which can damage the page's region markers",
    ]


def test_a_typo_in_the_title_is_located_by_line_and_column() -> None:
    text = _swap("Run {distance_km}", "Run {typo}")
    assert _problems(text) == [
        f"{_W}: title: line 1, column 5 of the value: unknown placeholder {{typo}}"
    ]


def test_a_typo_in_the_description_is_located_on_its_own_line() -> None:
    text = _swap("Long: {longest}", "Long: {longest}\\n  {typo}")
    assert _problems(text) == [
        f"{_W}: description: line 3, column 3 of the value: "
        "unknown placeholder {typo}"
    ]


def test_a_grammar_error_that_is_not_a_name_is_located() -> None:
    text = _swap("Run {distance_km}", "Run }")
    assert _problems(text) == [
        f"{_W}: title: line 1, column 5 of the value: "
        "a lone '}' (write '}}' for a literal brace)"
    ]


def test_a_declared_variable_is_a_known_name_but_an_undeclared_one_is_not() -> None:
    text = _swap("{tempo}", "{tempos}")
    problems = _problems(text)
    assert problems == [
        f"{_W}: title: line 1, column 19 of the value: unknown placeholder {{tempos}}"
    ]


def test_a_grammar_error_hides_the_unused_check_rather_than_faking_it() -> None:
    text = _swap("Run {distance_km} {tempo}", "{typo}")
    assert _problems(text) == [
        f"{_W}: title: line 1, column 1 of the value: unknown placeholder {{typo}}"
    ]


# --------------------------------------------------------------------------- #
# 1.11 to 1.13: vars
# --------------------------------------------------------------------------- #


def test_vars_that_is_not_a_table_is_refused() -> None:
    text = 'since = 2026-11-07\ntitle = "T"\nvars = 3\n'
    assert _problems(text) == [
        f"{_W}: vars: must be a table of tables, one per variable"
    ]


def test_an_entry_that_is_not_a_table_is_refused_naming_the_variable() -> None:
    text = 'since = 2026-11-07\ntitle = "T {tempo}"\n[vars]\ntempo = 5\nother = "x"\n'
    assert _problems(text) == [
        f"{_W}: vars.tempo: must be a table holding exactly `sql`",
        f"{_W}: vars.other: must be a table holding exactly `sql`",
        f"{_W}: vars.other: the variable is not used by title or description",
    ]


def test_an_entry_without_sql_is_refused() -> None:
    text = _swap('[vars.tempo]\nsql = "select 1"\n', "[vars.tempo]\n")
    assert _problems(text) == [f"{_W}: vars.tempo: lacks the key `sql`"]


def test_an_entry_with_another_key_is_refused_and_sql_alone_is_accepted() -> None:
    text = _swap('sql = "select 1"\n', 'sql = "select 1"\nnote = "x"\nmore = 1\n')
    assert _problems(text) == [
        f"{_W}: vars.tempo: holds the unknown key 'note'",
        f"{_W}: vars.tempo: holds the unknown key 'more'",
    ]


def test_an_entry_with_neither_sql_nor_only_sql_names_both_faults() -> None:
    text = _swap('sql = "select 1"\n', 'note = "x"\n')
    assert _problems(text) == [
        f"{_W}: vars.tempo: lacks the key `sql`",
        f"{_W}: vars.tempo: holds the unknown key 'note'",
    ]


@pytest.mark.parametrize("value", ["5", "true", "['select 1']", "{ a = 1 }"])
def test_sql_that_is_not_text_is_refused(value: str) -> None:
    text = _swap('sql = "select 1"', f"sql = {value}")
    assert _problems(text) == [f"{_W}: vars.tempo.sql: must be text"]


def test_a_variable_that_lacks_sql_is_still_a_declared_name() -> None:
    """Its `{tempo}` in the title is not reported as an unknown placeholder."""
    text = _swap('sql = "select 1"', "sql = 5")
    assert _problems(text) == [f"{_W}: vars.tempo.sql: must be text"]


@pytest.mark.parametrize(
    ("toml_key", "name"),
    [
        ('"Bad"', "Bad"),
        ('"2x"', "2x"),
        ('"a-b"', "a-b"),
        ('"a b"', "a b"),
        ('""', ""),
        ('"_x"', "_x"),
        ('"a\\n"', "a\n"),
        ('"caf\\u00e9"', "caf\u00e9"),
    ],
)
def test_a_name_off_the_grammar_is_refused(toml_key: str, name: str) -> None:
    text = _VALID + f"\n[vars.{toml_key}]\nsql = 'select 3'\n"
    assert _problems(text) == [
        f"{_W}: vars.{name}: the name must be lowercase letters, digits "
        "and underscores, starting with a letter"
    ]


def test_a_name_equal_to_a_page_placeholder_is_refused() -> None:
    text = _swap("{tempo}", "{load_value}").replace("[vars.tempo]", "[vars.load_value]")
    assert _problems(text) == [f"{_W}: vars.load_value: the name is a page placeholder"]


def test_an_unused_variable_is_refused_naming_it() -> None:
    text = _VALID + "\n[vars.spare]\nsql = 'select 3'\n"
    assert _problems(text) == [
        f"{_W}: vars.spare: the variable is not used by title or description"
    ]


def test_each_unused_variable_is_named() -> None:
    text = _VALID + "\n[vars.spare]\nsql = 'x'\n[vars.extra]\nsql = 'y'\n"
    assert _problems(text) == [
        f"{_W}: vars.spare: the variable is not used by title or description",
        f"{_W}: vars.extra: the variable is not used by title or description",
    ]


# --------------------------------------------------------------------------- #
# Every problem together
# --------------------------------------------------------------------------- #


def test_problems_in_different_keys_are_reported_together() -> None:
    text = _swap("2026-11-07", "2026-11-07T10:00:00")
    text = _swap("Long:", "Long: <!--", base=text)
    assert _problems(text) == [
        f"{_W}: {_SINCE_MESSAGE}",
        f"{_W}: description: must not contain '<!--', "
        "which can damage the page's region markers",
    ]


def test_problems_across_all_four_areas_come_in_rule_order() -> None:
    text = _swap("2026-11-07", "'later'")
    text = _swap("Run {distance_km}", "Run {typo}", base=text)
    text = _swap('sql = "select 2"', "sql = 2", base=text)
    text += "\n[vars.load_value]\nsql = 'select 3'\n"
    assert _problems(text) == [
        f"{_W}: {_SINCE_MESSAGE}",
        f"{_W}: title: line 1, column 5 of the value: unknown placeholder {{typo}}",
        f"{_W}: vars.longest.sql: must be text",
        f"{_W}: vars.load_value: the name is a page placeholder",
    ]


def test_every_kind_of_problem_comes_out_in_rule_order() -> None:
    text = """\
zzz = 1
since = "later"
title = "Run {typo}"
description = "Long: <!--"

[vars.a]
note = "x"

[vars.load_value]
sql = "select 1"
"""
    assert _problems(text) == [
        f"{_W}: zzz: not a recognized key",
        f"{_W}: {_SINCE_MESSAGE}",
        f"{_W}: title: line 1, column 5 of the value: unknown placeholder {{typo}}",
        f"{_W}: description: must not contain '<!--', "
        "which can damage the page's region markers",
        f"{_W}: vars.a: lacks the key `sql`",
        f"{_W}: vars.a: holds the unknown key 'note'",
        f"{_W}: vars.load_value: the name is a page placeholder",
    ]


def test_the_error_is_a_settings_error_and_str_joins_the_problems() -> None:
    text = _swap("2026-11-07", "1").replace('title = "Run', 'title = "<!-- Run')
    with pytest.raises(SettingsError) as caught:
        _parse(text)
    error = caught.value
    assert isinstance(error, PostTemplateError)
    assert len(error.problems) == 2
    assert str(error) == "\n".join(error.problems)
    assert isinstance(error.problems, tuple)


# --------------------------------------------------------------------------- #
# 5.5: the digest
# --------------------------------------------------------------------------- #


def _sha(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_TWO_VARS = """\
since = 2026-11-07
title = "T {b} {a}"
description = "D"

[vars.b]
sql = "select 2"

[vars.a]
sql = "select 1"
"""


def test_the_digest_is_pinned_to_its_byte_recipe() -> None:
    expected = _sha('["T {b} {a}","D",[["a","select 1"],["b","select 2"]]]')
    assert _parse(_TWO_VARS).digest == expected


def test_the_digest_keeps_non_ascii_text_as_utf8_and_strips_only_final_newlines() -> (
    None
):
    text = _TWO_VARS.replace('"T {b} {a}"', '"Caf\\u00e9 {b} {a}"')
    text = text.replace('"select 1"', '"select 1 \\r\\n\\n"')
    text = text.replace('"D"', '"D\\n\\n"')
    expected = _sha('["Café {b} {a}","D\\n\\n",[["a","select 1 "],["b","select 2"]]]')
    assert _parse(text).digest == expected


def test_the_digest_ignores_since_comments_order_and_layout() -> None:
    base = _parse(_TWO_VARS).digest
    moved = _TWO_VARS.replace("2026-11-07", "2025-01-02")
    commented = "# top\n" + _TWO_VARS.replace(
        'sql = "select 2"', 'sql = "select 2"  # why'
    )
    reordered = """\
description = "D"
title = "T {b} {a}"
[vars.a]
sql = "select 1"
[vars.b]
sql="select 2"
since    =   2026-11-07
""".replace("since    =   2026-11-07\n", "")
    reordered = "since = 2026-11-07\n" + reordered
    trailing_newline = _TWO_VARS.replace('"select 2"', '"select 2\\n"')
    for variant in (moved, commented, reordered, trailing_newline):
        assert _parse(variant).digest == base


def test_the_digest_changes_with_each_input_it_covers() -> None:
    base = _parse(_TWO_VARS).digest
    variants = {
        "title": _TWO_VARS.replace('"T {b} {a}"', '"U {b} {a}"'),
        "description": _TWO_VARS.replace('"D"', '"E"'),
        "first sql": _TWO_VARS.replace("select 1", "select 9"),
        "second sql": _TWO_VARS.replace("select 2", "select 9"),
        "sql whitespace": _TWO_VARS.replace("select 2", "select  2"),
        "sql trailing space": _TWO_VARS.replace('"select 2"', '"select 2 "'),
        "a renamed": _TWO_VARS.replace("{a}", "{c}").replace("[vars.a]", "[vars.c]"),
        "b renamed": _TWO_VARS.replace("{b}", "{c}").replace("[vars.b]", "[vars.c]"),
        "sql swapped": _TWO_VARS.replace("select 1", "TMP")
        .replace("select 2", "select 1")
        .replace("TMP", "select 2"),
        "title and description swapped": _TWO_VARS.replace(
            '"T {b} {a}"', '"D"', 1
        ).replace('description = "D"', 'description = "T {b} {a}"'),
        "title boundary moved": _TWO_VARS.replace('"T {b} {a}"', '"T {b}"').replace(
            '"D"', '" {a}D"'
        ),
    }
    digests = {name: _parse(text).digest for name, text in variants.items()}
    for name, digest in digests.items():
        assert digest != base, name
    assert len(set(digests.values())) == len(digests)


def test_the_digest_is_lowercase_hex_of_sixty_four() -> None:
    digest = _parse(_TWO_VARS).digest
    assert len(digest) == 64
    assert digest == digest.lower()
    assert set(digest) <= set("0123456789abcdef")


# --------------------------------------------------------------------------- #
# 1.1, 1.2, 1.3, 1.14: loading
# --------------------------------------------------------------------------- #


def test_an_absent_file_gives_none(per_test_directory: _Make) -> None:
    root = per_test_directory("absent")
    (root / f"{POST_TEMPLATE_FILE}.bak").write_text(_VALID, encoding="utf-8")
    (root / "fitdocs.toml").write_text(_VALID, encoding="utf-8")
    assert load_post_template(root) is None


def test_the_file_is_read_from_the_top_of_the_data_root_and_left_alone(
    per_test_directory: _Make,
) -> None:
    root = per_test_directory("present")
    path = post_template_path(root)
    path.write_bytes(_VALID.encode("utf-8"))
    os.utime(path, (1_000_000_000, 1_000_000_000))
    before = sorted(p.name for p in root.iterdir())
    template = load_post_template(root)
    assert template is not None
    assert template.path == path
    assert template.digest == _parse(_VALID).digest
    assert path.read_bytes() == _VALID.encode("utf-8")
    assert path.stat().st_mtime == 1_000_000_000
    assert sorted(p.name for p in root.iterdir()) == before


def test_a_file_one_level_down_is_not_the_template(per_test_directory: _Make) -> None:
    root = per_test_directory("nested")
    (root / "sub").mkdir()
    (root / "sub" / POST_TEMPLATE_FILE).write_text(_VALID, encoding="utf-8")
    assert load_post_template(root) is None


def test_a_directory_is_refused_naming_the_path(per_test_directory: _Make) -> None:
    root = per_test_directory("dir")
    post_template_path(root).mkdir()
    with pytest.raises(PostTemplateError) as caught:
        load_post_template(root)
    assert caught.value.problems == (
        f"{post_template_path(root)}: is not a regular file",
    )


def test_a_symlink_is_refused_even_to_a_valid_file(per_test_directory: _Make) -> None:
    root = per_test_directory("link")
    target = root / "real.toml"
    target.write_text(_VALID, encoding="utf-8")
    post_template_path(root).symlink_to(target)
    with pytest.raises(PostTemplateError) as caught:
        load_post_template(root)
    assert caught.value.problems == (
        f"{post_template_path(root)}: is a symlink, not a file",
    )


def test_a_dangling_symlink_is_refused_not_absent(per_test_directory: _Make) -> None:
    root = per_test_directory("dangling")
    post_template_path(root).symlink_to(root / "missing.toml")
    with pytest.raises(PostTemplateError) as caught:
        load_post_template(root)
    assert caught.value.problems == (
        f"{post_template_path(root)}: is a symlink, not a file",
    )


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_an_unreadable_file_is_refused_naming_the_path(
    per_test_directory: _Make,
) -> None:
    root = per_test_directory("unreadable")
    path = post_template_path(root)
    path.write_text(_VALID, encoding="utf-8")
    path.chmod(0)
    try:
        with pytest.raises(PostTemplateError) as caught:
            load_post_template(root)
    finally:
        path.chmod(0o644)
    assert len(caught.value.problems) == 1
    assert caught.value.problems[0].startswith(f"{path}: could not be read: ")


def test_a_loaded_invalid_file_names_the_real_path(per_test_directory: _Make) -> None:
    root = per_test_directory("invalid")
    path = post_template_path(root)
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(PostTemplateError) as caught:
        load_post_template(root)
    assert caught.value.problems[0].startswith(f"{path}: is not valid UTF-8")
