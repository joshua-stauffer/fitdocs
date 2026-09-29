"""The content contract constants and shared value types (2.1, 2.2, 2.3, 2.9)."""

from __future__ import annotations

import dataclasses
import itertools
from pathlib import Path

import pytest
from scripts.sitebuild import model
from scripts.sitebuild.model import (
    Asset,
    ContentSource,
    HeroAction,
    Page,
    Problem,
    ResolvedContent,
    SiteContent,
)


def test_sections_are_the_eight_canonical_names_in_order() -> None:
    """`SECTIONS` is the canonical list, in canonical order (2.2).

    Dies on: swapping two names in `SECTIONS`, dropping one, or changing the
    case of one.
    """
    assert model.SECTIONS == (
        "Home",
        "Why",
        "Get started",
        "Guides",
        "Working with LLMs",
        "Reference",
        "Extend",
        "Project",
    )


def test_page_key_tuples_match_the_contract_literals() -> None:
    """The key tuples hold the contract's names (2.1, 2.3).

    Dies on: renaming `order` in `REQUIRED_KEYS`, or dropping `draft` from
    `OPTIONAL_KEYS`.
    """
    assert model.REQUIRED_KEYS == ("title", "description", "section", "order")
    assert model.OPTIONAL_KEYS == ("draft",)
    assert model.HERO_KEYS == ("hero_title", "hero_tagline", "hero_actions")
    assert model.HERO_ACTION_KEYS == ("label", "href", "primary")


def test_page_key_tuples_are_disjoint_and_duplicate_free() -> None:
    """No key name is in two of the page-level tuples or twice in one (2.3).

    Dies on: changing `OPTIONAL_KEYS` to `("draft", "order")`, which puts
    `order` in two tuples.
    """
    tuples = {
        "REQUIRED_KEYS": model.REQUIRED_KEYS,
        "OPTIONAL_KEYS": model.OPTIONAL_KEYS,
        "HERO_KEYS": model.HERO_KEYS,
    }
    assert all(tuples.values()), "an empty tuple makes disjointness vacuous"
    for name, keys in tuples.items():
        assert len(set(keys)) == len(keys), f"{name} repeats a key"
    for (left, left_keys), (right, right_keys) in itertools.combinations(
        tuples.items(), 2
    ):
        assert not set(left_keys) & set(right_keys), f"{left} overlaps {right}"


def test_names_and_paths_constants_are_the_design_literals() -> None:
    """The single-value constants equal the design's literals (1.4, 2.11).

    Dies on: changing `BRAND_DIR` to `"brand"` (a name content could reach),
    or dropping `llms-full.txt` from `RESERVED_ROOT_NAMES`.
    """
    assert model.HOME_PAGE == "index.md"
    assert model.HOME_TEMPLATE == "home.html"
    assert model.RESERVED_ROOT_NAMES == ("llms.txt", "llms-full.txt")
    assert model.BRAND_DIR == "_brand"
    assert model.CONTENT_ENV_VAR == "FITDOCS_SITE_CONTENT"
    assert model.ANNOTATION_MARKER == "\n\n---\nAnnotations:"


def test_content_source_values_are_the_labels_shown_to_the_maintainer() -> None:
    """Each `ContentSource` member's value is its display label (1.2).

    Dies on: changing `ContentSource.DEFAULT` to `"default"`.
    """
    assert {member.name: str(member) for member in ContentSource} == {
        "OPTION": "--content",
        "ENVIRONMENT": "FITDOCS_SITE_CONTENT",
        "DEFAULT": "default website/content/",
    }
    assert str(ContentSource.ENVIRONMENT) == model.CONTENT_ENV_VAR


def test_value_types_have_the_designed_fields_in_order() -> None:
    """Field names and order of every value type match the design (2.1, 2.9).

    Dies on: swapping `where` and `message` in `Problem`, or renaming
    `Page.staged_text`.
    """
    expected: dict[type, list[str]] = {
        ResolvedContent: ["path", "source"],
        Problem: ["path", "where", "message"],
        HeroAction: ["label", "href", "primary"],
        Page: [
            "path",
            "title",
            "description",
            "section",
            "order",
            "staged_text",
            "body",
            "hero_title",
            "hero_tagline",
            "hero_actions",
        ],
        Asset: ["path", "source"],
        SiteContent: ["root", "pages", "assets"],
    }
    for cls, names in expected.items():
        assert [f.name for f in dataclasses.fields(cls)] == names, cls.__name__


def test_value_types_are_frozen() -> None:
    """Every value type refuses attribute assignment.

    Dies on: removing `frozen=True` from any one of the six dataclasses.
    """
    problem = Problem("a.md", "order", "bad")
    with pytest.raises(dataclasses.FrozenInstanceError):
        problem.message = "changed"  # type: ignore[misc]
    resolved = ResolvedContent(Path("x"), ContentSource.OPTION)
    with pytest.raises(dataclasses.FrozenInstanceError):
        resolved.path = Path("y")  # type: ignore[misc]
    action = HeroAction("Go", "https://example.org/", True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        action.primary = False  # type: ignore[misc]
    asset = Asset("images/a.svg", Path("a.svg"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        asset.path = "b"  # type: ignore[misc]
    content = SiteContent(Path("."), (), ())
    with pytest.raises(dataclasses.FrozenInstanceError):
        content.root = Path("elsewhere")  # type: ignore[misc]
    page = Page("a.md", "t", "d", "Why", 1, "s", "b", None, None, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        page.order = 2  # type: ignore[misc]


def test_problem_fields_are_positional_path_where_message() -> None:
    """`Problem(a, b, c)` binds path, where, message in that order (2.9).

    Dies on: swapping the `where` and `message` declarations in `Problem`.
    """
    problem = Problem("one", "two", "three")
    assert (problem.path, problem.where, problem.message) == ("one", "two", "three")


@pytest.mark.parametrize(
    ("path", "where", "message", "expected"),
    [
        ("a.md", "order", "must be an integer", "a.md: order: must be an integer"),
        ("", "order", "must be an integer", "order: must be an integer"),
        ("a.md", "", "must be an integer", "a.md: must be an integer"),
        ("a.md", "order", "", "a.md: order"),
        ("", "", "must be an integer", "must be an integer"),
        ("a.md", "", "", "a.md"),
        ("", "order", "", "order"),
        ("", "", "", ""),
    ],
)
def test_render_joins_only_the_non_empty_fields(
    path: str, where: str, message: str, expected: str
) -> None:
    """Empty fields vanish with their separator; the others join with `": "` (2.9).

    Dies on: joining all three fields unconditionally (`": ".join([path,
    where, message])`), which leaves a doubled or leading `": "`.
    """
    assert Problem(path, where, message).render() == expected


@pytest.mark.parametrize(
    "terminator", ["\n", "\r\n", "\r", "\x0b", "\x0c", "\x85", "\u2028", "\u2029"]
)
def test_render_replaces_a_line_break_in_the_message_with_one_space(
    terminator: str,
) -> None:
    """A line break inside the message becomes one space; none survives (2.9).

    Dies on: replacing only `"\\n"` (leaves `\\r`, `\\x0b`, `\\u2028` ...), replacing
    with `""` (`"onetwo"`), or replacing each character of `"\\r\\n"` (two spaces).
    """
    rendered = Problem("a.md", "order", f"one{terminator}two").render()
    assert rendered == "a.md: order: one two"
    assert len(rendered.splitlines()) == 1


@pytest.mark.parametrize("field", ["path", "where", "message"])
def test_render_is_one_line_whichever_field_carries_the_break(field: str) -> None:
    """A break in any field (a file name may hold one) renders as one line (2.9).

    Dies on: sanitising only `message` in `render()`.
    """
    values = {"path": "a.md", "where": "order", "message": "bad"}
    values[field] = "x\ny"
    rendered = Problem(**values).render()
    assert "\n" not in rendered
    assert rendered.count(": ") == 2
    assert "x y" in rendered


def test_render_treats_a_field_that_is_only_a_line_break_as_empty() -> None:
    """A `where` of just a newline is dropped like an empty one (2.9).

    Dies on: filtering empty fields before replacing line breaks, which leaves
    `"a.md: : bad"`.
    """
    assert Problem("a.md", "\n", "bad").render() == "a.md: bad"


def test_render_leaves_no_trailing_space_for_a_trailing_newline() -> None:
    """A message ending in a newline has no trailing space (2.9).

    Dies on: replacing `"\\n"` with `" "` character by character instead of
    joining the lines, which yields `"a.md: bad "`.
    """
    assert Problem("a.md", "", "bad\n").render() == "a.md: bad"


def test_render_keeps_all_field_text_that_is_not_a_line_break() -> None:
    """Spaces and tabs inside, before and after a field are kept verbatim (2.9).

    A file name such as ` a  b.md` must not be renamed in the report.

    Dies on: collapsing whitespace with `" ".join(f.split())`, or stripping each
    line with `l.strip()` in `render`.
    """
    problem = Problem(" a  b.md", "\tkey", "two  spaces ")
    assert problem.render() == " a  b.md: \tkey: two  spaces "


def test_render_keeps_a_whitespace_only_field_because_it_is_not_empty() -> None:
    """A field of spaces is non-empty, so it stays and keeps its separators (2.9).

    Dies on: dropping fields that are blank after `strip()` instead of fields
    that are empty.
    """
    assert Problem("a.md", " ", "bad").render() == "a.md:  : bad"
