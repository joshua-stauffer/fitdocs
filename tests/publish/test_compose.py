"""The post region, composition and the post digest (publish-core Req 3.2-3.7,
4.7, 5.6, 6.1-6.5)."""

from __future__ import annotations

import dataclasses
import hashlib

import pytest

from fitdocs.publish.compose import (
    PostOverride,
    Refusal,
    compose_post,
    override_templates,
    post_digest,
    read_post_region,
)
from fitdocs.publish.outcomes import PublishCode
from fitdocs.publish.request import Post
from fitdocs.publish.template import (
    TargetTemplates,
    parse_template,
)
from fitdocs.publish.values import PLACEHOLDERS


def _t(title: str, description: str = "") -> TargetTemplates:
    return TargetTemplates(
        parse_template(title, names=PLACEHOLDERS),
        parse_template(description, names=PLACEHOLDERS),
    )


def _refusal(result: object) -> Refusal:
    assert isinstance(result, Refusal), result
    return result


def _override(result: object) -> PostOverride:
    assert isinstance(result, PostOverride), result
    return result


# --------------------------------------------------------------------------- #
# read_post_region: nothing left is no override (3.2)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "content",
    [
        "",
        "\n",
        "  \n\t\n   ",
        "<!-- write a post here -->",
        "<!-- a -->\n\n<!-- b -->\n",
        "\n<!--\nmulti\nline\n-->\n\n",
        "<!-- a --> <!-- b -->",
        "\r\n<!-- a -->\r\n\r\n",
    ],
)
def test_hidden_comments_and_blank_lines_alone_are_no_override(content: str) -> None:
    assert read_post_region(content) is None


# --------------------------------------------------------------------------- #
# read_post_region: title, description (3.3, 3.4)
# --------------------------------------------------------------------------- #


def test_title_only_region_has_an_empty_description() -> None:
    assert read_post_region("Race day") == PostOverride("Race day", "")
    assert read_post_region("\n\n  Race day  \n\n \n") == PostOverride("Race day", "")


def test_title_blank_line_description() -> None:
    got = read_post_region("Title\n\nline one\n\nline three\n")
    assert got == PostOverride("Title", "line one\n\nline three")


def test_tab_only_leading_line_counts_as_blank() -> None:
    assert read_post_region("\t\nTitle\n\nbody") == PostOverride("Title", "body")


def test_leading_and_trailing_blank_lines_are_dropped_around_everything() -> None:
    got = read_post_region(" \n\n  Title  \n\nbody\n\n   \n\n")
    assert got == PostOverride("Title", "body")


def test_title_line_is_stripped_but_description_keeps_its_indent() -> None:
    got = read_post_region("   Title\t\n\n  indented\nnext")
    assert got == PostOverride("Title", "  indented\nnext")


def test_whitespace_only_second_line_counts_as_blank() -> None:
    assert read_post_region("T\n  \t \nD") == PostOverride("T", "D")


# --------------------------------------------------------------------------- #
# read_post_region: line endings
# --------------------------------------------------------------------------- #


def test_crlf_and_bare_cr_read_like_lf() -> None:
    want = PostOverride("T", "a\nb")
    assert read_post_region("T\r\n\r\na\r\nb\r\n") == want
    assert read_post_region("T\r\ra\rb") == want
    assert read_post_region("T\n\na\nb\n") == want


def test_crlf_title_only() -> None:
    assert read_post_region("Title\r\n") == PostOverride("Title", "")
    assert read_post_region("Title\r") == PostOverride("Title", "")


def test_crlf_missing_blank_line_is_still_invalid() -> None:
    assert _refusal(read_post_region("T\r\nD\r\n")).code is PublishCode.POST_INVALID


# --------------------------------------------------------------------------- #
# read_post_region: hidden comments (3.6, 3.7)
# --------------------------------------------------------------------------- #


def test_comment_inside_the_title_line_is_removed() -> None:
    assert read_post_region("Race <!-- note --> day") == PostOverride("Race  day", "")
    assert read_post_region("<!-- lead --> Title") == PostOverride("Title", "")
    assert read_post_region("Title <!-- trail -->") == PostOverride("Title", "")


def test_comment_line_before_the_title_is_not_the_title() -> None:
    got = read_post_region("<!-- note -->\nTitle\n\nbody")
    assert got == PostOverride("Title", "body")


def test_comment_only_line_after_the_title_is_the_blank_line() -> None:
    assert read_post_region("T\n<!-- c -->\nD") == PostOverride("T", "D")


def test_multiline_comment_between_title_and_description() -> None:
    got = read_post_region("T\n<!-- a\nb -->\n\nD")
    assert got == PostOverride("T", "\nD")


def test_comment_inside_the_description_is_removed() -> None:
    got = read_post_region("T\n\nA <!-- x --> B\n<!-- y\nz -->\nC")
    assert got == PostOverride("T", "A  B\n\nC")


def test_comment_closed_by_first_closer_only() -> None:
    got = read_post_region("A <!-- x --> B --> C")
    assert got == PostOverride("A  B --> C", "")


def test_stray_closer_without_opener_is_text() -> None:
    assert read_post_region("--> T") == PostOverride("--> T", "")


@pytest.mark.parametrize(
    "content",
    [
        "T <!-- oops",
        "<!-- a --> T <!--",
        "<!-- never closed",
        "T\n\nbody <!-- oops\nstill open",
        "<!-->",
        "<!--->",
        "<!-- a --> <!-- b",
    ],
)
def test_unclosed_comment_is_post_invalid(content: str) -> None:
    got = _refusal(read_post_region(content))
    assert got.code is PublishCode.POST_INVALID
    assert got.detail is not None and "comment" in got.detail


def test_partial_comment_openers_are_plain_text() -> None:
    assert read_post_region("a <! b <!- c") == PostOverride("a <! b <!- c", "")


# --------------------------------------------------------------------------- #
# read_post_region: a missing blank line (3.7)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "content", ["T\nD", "T\nD\n\nE", "\nT\nD\n", "T <!-- c -->\nD"]
)
def test_title_followed_by_a_non_blank_line_is_post_invalid(content: str) -> None:
    got = _refusal(read_post_region(content))
    assert got.code is PublishCode.POST_INVALID
    assert got.detail is not None and "blank" in got.detail


# --------------------------------------------------------------------------- #
# override_templates (3.5, 4.7)
# --------------------------------------------------------------------------- #


def test_override_templates_parse_like_any_template() -> None:
    got = override_templates(
        PostOverride(
            "X {distance_km} {{km}}", "{?Time: {moving_time}\n}{?Pace: {pace_per_km}}"
        )
    )
    assert isinstance(got, TargetTemplates)
    assert got.title == parse_template("X {distance_km} {{km}}", names=PLACEHOLDERS)
    assert got.description == parse_template(
        "{?Time: {moving_time}\n}{?Pace: {pace_per_km}}", names=PLACEHOLDERS
    )


def test_every_known_placeholder_is_accepted_in_an_override() -> None:
    text = " ".join("{" + n + "}" for n in PLACEHOLDERS)
    assert isinstance(override_templates(PostOverride(text, text)), TargetTemplates)


def test_unknown_placeholder_in_the_title_names_title_and_position() -> None:
    got = _refusal(override_templates(PostOverride("Ride {pace}", "")))
    assert got.code is PublishCode.TEMPLATE_INVALID
    assert got.detail == "title, line 1, column 6: unknown placeholder {pace}"


def test_syntax_error_in_the_description_names_description_and_position() -> None:
    got = _refusal(override_templates(PostOverride("ok", "Line\nBad {")))
    assert got.code is PublishCode.TEMPLATE_INVALID
    assert got.detail == (
        "description, line 2, column 5: "
        "unterminated placeholder (write '{{' for a literal brace)"
    )


def test_title_error_is_reported_before_a_description_error() -> None:
    got = _refusal(override_templates(PostOverride("{nope}", "{nada}")))
    assert got.detail is not None and got.detail.startswith("title, ")


def test_comment_text_never_reaches_template_parsing() -> None:
    region = "T {title} <!-- {bogus} { -->\n\nbody <!-- {pace} -->{distance_km}"
    override = _override(read_post_region(region))
    templates = override_templates(override)
    assert isinstance(templates, TargetTemplates)
    post = compose_post(templates, {"title": "X", "distance_km": "5.00"})
    assert post == Post("T X", "body 5.00")


# --------------------------------------------------------------------------- #
# compose_post (5.6, 6.1, 6.2, 6.3, 6.5)
# --------------------------------------------------------------------------- #

VALUES = {"title": "Morning Run", "distance_km": "5.00", "pace_per_km": None}


def test_compose_fills_title_and_description() -> None:
    got = compose_post(
        _t("{title} - {distance_km} km", "Distance: {distance_km} km"), VALUES
    )
    assert got == Post("Morning Run - 5.00 km", "Distance: 5.00 km")


def test_optional_clause_without_a_value_contributes_nothing() -> None:
    got = compose_post(
        _t(
            "{title}",
            "{?Dist: {distance_km}\n}{?Pace: {pace_per_km}\n}{?Z: {calories_kcal}}",
        ),
        {**VALUES, "calories_kcal": None},
    )
    assert got == Post("Morning Run", "Dist: 5.00")


def test_bare_missing_value_in_the_title_is_value_missing() -> None:
    got = _refusal(compose_post(_t("{title} {pace_per_km}"), VALUES))
    assert got.code is PublishCode.VALUE_MISSING
    assert got.detail == "pace_per_km"


def test_bare_missing_value_in_the_description_is_value_missing() -> None:
    got = _refusal(
        compose_post(_t("{title}", "x {distance_km}\n{pace_per_km}"), VALUES)
    )
    assert got.code is PublishCode.VALUE_MISSING
    assert got.detail == "pace_per_km"


def test_absent_name_is_a_missing_value_not_a_default() -> None:
    got = _refusal(compose_post(_t("{title}", "{calories_kcal}"), VALUES))
    assert (got.code, got.detail) == (PublishCode.VALUE_MISSING, "calories_kcal")


def test_title_is_reported_missing_before_the_description() -> None:
    got = _refusal(compose_post(_t("{pace_per_km}", "{calories_kcal}"), VALUES))
    assert got.detail == "pace_per_km"


def test_missing_value_is_reported_before_an_empty_title() -> None:
    got = _refusal(compose_post(_t("  ", "{calories_kcal}"), VALUES))
    assert got.code is PublishCode.VALUE_MISSING


@pytest.mark.parametrize("title", ["", "   ", "{?x {pace_per_km}}", " \t "])
def test_empty_title_is_title_empty(title: str) -> None:
    got = _refusal(compose_post(_t(title, "body"), VALUES))
    assert got.code is PublishCode.TITLE_EMPTY
    assert got.detail is None


def test_zero_value_is_text_and_is_not_missing() -> None:
    got = compose_post(
        _t("{distance_km}", "{distance_mi}"),
        {"distance_km": "0", "distance_mi": "0.00"},
    )
    assert got == Post("0", "0.00")


def test_title_interior_spaces_and_tabs_are_kept() -> None:
    assert compose_post(_t("Race  day\tx"), VALUES) == Post("Race  day\tx", "")


def test_comment_removed_title_keeps_its_double_space_through_composition() -> None:
    override = _override(read_post_region("Race <!-- n --> day"))
    templates = override_templates(override)
    assert isinstance(templates, TargetTemplates)
    assert compose_post(templates, VALUES) == Post("Race  day", "")


def test_title_is_stripped() -> None:
    assert compose_post(_t("  {title} \t"), VALUES) == Post("Morning Run", "")


@pytest.mark.parametrize(
    "template",
    [
        "A\nB",
        "A \n  B",
        "A\r\nB",
        "A\rB",
        "A\u2028B",
        "A\u2029B",
        "A\x85B",
        "A\x0bB",
        "A\x0cB",
        "A\n\n\nB",
        "\nA\n B \n",
    ],
)
def test_title_is_single_line_whatever_line_break_it_carries(template: str) -> None:
    got = compose_post(_t(template), VALUES)
    assert isinstance(got, Post)
    assert got.title == "A B"
    assert len(got.title.splitlines()) == 1


def test_value_borne_line_break_cannot_split_the_title() -> None:
    got = compose_post(_t("{title}"), {"title": "a\nb\u2028c"})
    assert got == Post("a b c", "")


def test_description_line_endings_are_newlines() -> None:
    got = compose_post(_t("T", "a\r\nb\rc{title}"), {"title": "x\r\ny"})
    assert got == Post("T", "a\nb\ncx\ny")


def test_description_drops_leading_blank_lines_but_not_indent() -> None:
    got = compose_post(_t("T", "\n  \n\r\n  indented\nnext"), VALUES)
    assert got == Post("T", "  indented\nnext")


def test_only_the_end_of_the_description_is_stripped() -> None:
    assert compose_post(_t("T", "a  \nb "), VALUES) == Post("T", "a  \nb")


def test_description_has_no_trailing_whitespace() -> None:
    assert compose_post(_t("T", "x \n\n \t\n"), VALUES) == Post("T", "x")
    assert compose_post(_t("T", "x{?\n{pace_per_km}\n}"), VALUES) == Post("T", "x")


def test_description_keeps_interior_blank_lines() -> None:
    assert compose_post(_t("T", "a\n\nb"), VALUES) == Post("T", "a\n\nb")


def test_empty_description_is_not_a_refusal() -> None:
    assert compose_post(_t("T", ""), VALUES) == Post("T", "")
    assert compose_post(_t("T", "\n\n"), VALUES) == Post("T", "")


def test_values_are_inserted_literally() -> None:
    got = compose_post(_t("{title}", "{title}"), {"title": "{pace_per_km} {{"})
    assert got == Post("{pace_per_km} {{", "{pace_per_km} {{")


def test_identical_inputs_compose_identical_bytes() -> None:
    def make() -> Post:
        got = compose_post(
            _t("{title} é", "{?Dist: {distance_km}\r\n}tail \n"), dict(VALUES)
        )
        assert isinstance(got, Post)
        return got

    a, b = make(), make()
    assert a is not b
    assert a == b
    assert a.title.encode() == b.title.encode()
    assert a.description.encode() == b.description.encode()
    assert post_digest(a) == post_digest(b)
    assert a == Post("Morning Run é", "Dist: 5.00\ntail")


def test_each_target_composes_its_own_post() -> None:
    one = compose_post(_t("{title}", "A"), VALUES)
    two = compose_post(_t("{distance_km} km", "B"), VALUES)
    assert one == Post("Morning Run", "A")
    assert two == Post("5.00 km", "B")
    assert isinstance(one, Post) and isinstance(two, Post)
    assert post_digest(one) != post_digest(two)


def test_region_to_post_end_to_end_crlf() -> None:
    region = "\r\nRace: {title}\r\n\r\n{?Dist: {distance_km} km\r\n}<!-- n -->\r\n"
    templates = override_templates(_override(read_post_region(region)))
    assert isinstance(templates, TargetTemplates)
    assert compose_post(templates, VALUES) == Post("Race: Morning Run", "Dist: 5.00 km")


# --------------------------------------------------------------------------- #
# post_digest (6.4)
# --------------------------------------------------------------------------- #


def test_digest_is_the_pinned_sha256_of_the_json_pair() -> None:
    got = post_digest(Post("Morning run", "Distance: 5.00 km\nTime: 25:00"))
    assert got == "082c9ed84f02a5531ef865e0300d882423ecccd77ca7190f400280ac49b9cb72"
    expect = hashlib.sha256(
        b'["Morning run","Distance: 5.00 km\\nTime: 25:00"]'
    ).hexdigest()
    assert got == expect


def test_digest_keeps_non_ascii_unescaped_in_utf8() -> None:
    assert post_digest(Post("é", "d")) == (
        "6e8bec5b4d87b78a2b7175699ba2bc318a1ac886b7b2facc41edee01975faf21"
    )


def test_digest_is_lowercase_hex_of_64_chars() -> None:
    got = post_digest(Post("a", "b"))
    assert len(got) == 64 and got == got.lower() and int(got, 16) >= 0


def test_digest_changes_with_the_title_alone_or_the_description_alone() -> None:
    base = Post("t", "d")
    assert post_digest(Post("t2", "d")) != post_digest(base)
    assert post_digest(Post("t", "d2")) != post_digest(base)


def test_digest_is_unambiguous_across_the_title_description_boundary() -> None:
    digests = {
        post_digest(Post("ab", "c")),
        post_digest(Post("a", "bc")),
        post_digest(Post("a", "")),
        post_digest(Post("", "a")),
        post_digest(Post("a\nb", "")),
        post_digest(Post("a", "\nb")),
    }
    assert len(digests) == 6


def test_equal_posts_share_a_digest() -> None:
    a, b = Post("t", "d"), Post("t", "d")
    assert a is not b
    assert post_digest(a) == post_digest(b)


def test_a_post_holds_exactly_a_title_and_a_description() -> None:
    assert [f.name for f in dataclasses.fields(Post)] == ["title", "description"]


@pytest.mark.parametrize(
    ("cls", "names"),
    [(Refusal, ["code", "detail"]), (PostOverride, ["title", "description"])],
)
def test_refusal_and_override_are_frozen_with_no_defaults(
    cls: type, names: list[str]
) -> None:
    assert [f.name for f in dataclasses.fields(cls)] == names
    assert getattr(cls, "__dataclass_params__").frozen  # noqa: B009
    assert all(
        f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
        for f in dataclasses.fields(cls)
    )


def test_refusal_and_override_reject_assignment() -> None:
    refusal = Refusal(PublishCode.TITLE_EMPTY, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        refusal.detail = "x"  # type: ignore[misc]
    override = PostOverride("t", "d")
    with pytest.raises(dataclasses.FrozenInstanceError):
        override.title = "x"  # type: ignore[misc]
