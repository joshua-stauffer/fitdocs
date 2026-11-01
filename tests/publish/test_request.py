"""The publish request and result values and the link and label rules.

Covers publish-core Req 9.3, 9.4 (the values a target receives and returns)
and 12.3 (one link rule, one label rule).
"""

from __future__ import annotations

import ast
import dataclasses
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import get_type_hints
from urllib.parse import urlsplit

import pytest

from fitdocs.publish import request
from fitdocs.publish.outcomes import PublishCode
from fitdocs.publish.request import (
    MAX_LABEL_LENGTH,
    MAX_LINK_LENGTH,
    CompletedActivity,
    Post,
    PublishRequest,
    PublishResult,
    valid_label,
    valid_link,
)

_PREFIX = "https://example.com/"


def _link_of_length(n: int) -> str:
    return _PREFIX + "a" * (n - len(_PREFIX))


def _activity() -> CompletedActivity:
    return CompletedActivity(
        sport="Run",
        start=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        elapsed_s=None,
        distance_m=None,
        source_shas=("a" * 64,),
        base_fit=None,
    )


# --- values -----------------------------------------------------------------


def test_bounds_are_the_pinned_literals() -> None:
    assert MAX_LINK_LENGTH == 2048
    assert MAX_LABEL_LENGTH == 64


@pytest.mark.parametrize(
    ("cls", "fields"),
    [
        (Post, ["title", "description"]),
        (
            CompletedActivity,
            ["sport", "start", "elapsed_s", "distance_m", "source_shas", "base_fit"],
        ),
        (PublishRequest, ["publication_id", "post", "subject", "recorded_link"]),
        (PublishResult, ["code", "link"]),
    ],
)
def test_value_fields_are_the_pinned_names_in_order(
    cls: type, fields: list[str]
) -> None:
    assert [f.name for f in dataclasses.fields(cls)] == fields


def test_value_field_types() -> None:
    assert get_type_hints(Post) == {"title": str, "description": str}
    assert get_type_hints(CompletedActivity) == {
        "sport": str,
        "start": datetime,
        "elapsed_s": float | None,
        "distance_m": float | None,
        "source_shas": tuple[str, ...],
        "base_fit": Path | None,
    }
    assert get_type_hints(PublishRequest) == {
        "publication_id": str,
        "post": Post,
        "subject": CompletedActivity,
        "recorded_link": str | None,
    }
    assert get_type_hints(PublishResult) == {
        "code": PublishCode,
        "link": str | None,
    }


def test_values_are_frozen_dataclasses() -> None:
    for cls in (Post, CompletedActivity, PublishRequest, PublishResult):
        assert dataclasses.is_dataclass(cls)
        assert getattr(cls, "__dataclass_params__").frozen  # noqa: B009
    post = Post(title="t", description="")
    with pytest.raises(dataclasses.FrozenInstanceError):
        post.title = "x"  # type: ignore[misc]


def test_result_link_defaults_to_none_not_a_fabricated_value() -> None:
    assert PublishResult(PublishCode.POSTED).link is None
    assert PublishResult(PublishCode.POSTED, "https://example.com/x").link == (
        "https://example.com/x"
    )


@pytest.mark.parametrize(
    "cls", [Post, CompletedActivity, PublishRequest, PublishResult]
)
def test_only_the_result_link_has_a_default(cls: type) -> None:
    # A defaulted field lets a caller omit data and silently read "absent".
    defaults = {f.name: (f.default, f.default_factory) for f in dataclasses.fields(cls)}
    expected = {
        name: (
            None if (cls, name) == (PublishResult, "link") else dataclasses.MISSING,
            dataclasses.MISSING,
        )
        for name in defaults
    }
    assert defaults == expected


def test_request_carries_the_subject_and_post_unflattened() -> None:
    post = Post("T", "D")
    subject = _activity()
    req = PublishRequest("0" * 32, post, subject, None)
    assert req.post is post
    assert req.subject is subject
    assert req.recorded_link is None
    assert req == PublishRequest("0" * 32, post, subject, None)
    assert req != PublishRequest("1" * 32, post, subject, None)


# --- link rule --------------------------------------------------------------


def test_link_accepts_a_plain_https_link() -> None:
    assert valid_link("https://example.com/activities/1")
    assert valid_link("https://example.com")
    assert valid_link("https://example.com:8443/a?b=c&d=e#f")


def test_link_length_bound_exact_and_one_past() -> None:
    assert len(_link_of_length(MAX_LINK_LENGTH)) == MAX_LINK_LENGTH
    assert valid_link(_link_of_length(MAX_LINK_LENGTH))
    assert not valid_link(_link_of_length(MAX_LINK_LENGTH + 1))


@pytest.mark.parametrize(
    "link",
    [
        "http://example.com/a",
        "HTTPS://example.com/a",
        "ftp://example.com/a",
        "//example.com/a",
        "example.com/a",
        " https://example.com/a",
        "xhttps://example.com/a",
        "",
        "https:/example.com",
    ],
)
def test_link_must_start_https_scheme(link: str) -> None:
    assert not valid_link(link)


@pytest.mark.parametrize(
    "link",
    ["https://", "https:///path", "https://:443/a", "https://user@/a", "https://?q=1"],
)
def test_link_needs_a_host(link: str) -> None:
    assert not valid_link(link)


@pytest.mark.parametrize(
    "char",
    [" ", "\t", "\n", "\r", "\x0b", "\x0c", "\x85", "\xa0", " ", " ", "　"],
)
def test_link_refuses_each_whitespace_character(char: str) -> None:
    assert valid_link("https://example.com/a")
    assert not valid_link(f"https://example.com/a{char}b")
    assert not valid_link(f"https://example.com/ab{char}")


@pytest.mark.parametrize(
    "char", ["\x00", "\x01", "\x1b", "\x1f", "\x7f", "\x80", "\x9f"]
)
def test_link_refuses_each_control_character(char: str) -> None:
    assert not valid_link(f"https://example.com/a{char}b")
    assert not valid_link(f"https://example.com/ab{char}")


def test_link_control_range_ends_exactly_at_the_c1_block() -> None:
    # U+00A1 is printable; the control ranges must not swallow it.
    assert valid_link("https://example.com/¡")
    assert valid_link("https://example.com/\x21")


@pytest.mark.parametrize("char", list('<>()[]"`\\'))
def test_link_refuses_each_markdown_breaking_character(char: str) -> None:
    assert not valid_link(f"https://example.com/a{char}b")
    assert not valid_link(f"https://example.com/ab{char}")


@pytest.mark.parametrize(
    "link",
    ["https://a\uff03b/x", "https://ex\uff0fample.com", "https://a\uff20b"],
)
def test_link_refuses_a_netloc_the_url_parser_raises_on(link: str) -> None:
    # Fullwidth # / @ in the netloc make urlsplit raise ValueError (NFKC check).
    with pytest.raises(ValueError, match="NFKC"):
        urlsplit(link)
    assert valid_link(link) is False


@pytest.mark.parametrize("char", list("'*_{}|~^!#%&+,-./:;=?@$"))
def test_link_does_not_refuse_other_punctuation(char: str) -> None:
    assert valid_link(f"https://example.com/a{char}b")


@pytest.mark.parametrize(
    "value", [None, 1, b"https://example.com/a", ["https://x.com"], object()]
)
def test_link_rejects_non_strings(value: object) -> None:
    assert not valid_link(value)


# --- label rule -------------------------------------------------------------


def test_label_accepts_ordinary_text() -> None:
    assert valid_label("Strava")
    assert valid_label("a b")
    assert valid_label("Run: 10 km (easy)")


def test_label_must_be_non_empty() -> None:
    assert not valid_label("")
    assert valid_label("a")


def test_label_length_bound_exact_and_one_past() -> None:
    assert valid_label("a" * MAX_LABEL_LENGTH)
    assert not valid_label("a" * (MAX_LABEL_LENGTH + 1))


@pytest.mark.parametrize(
    "char", ["\x00", "\x01", "\t", "\n", "\r", "\x1b", "\x1f", "\x7f", "\x80", "\x9f"]
)
def test_label_refuses_each_control_character(char: str) -> None:
    assert valid_label("ab")
    assert not valid_label(f"a{char}b")
    assert not valid_label(f"ab{char}")
    assert not valid_label(char)


@pytest.mark.parametrize("char", ["[", "]"])
def test_label_refuses_each_bracket(char: str) -> None:
    assert not valid_label(f"a{char}b")
    assert not valid_label(char)


@pytest.mark.parametrize("char", ["\u2028", "\u2029"])
def test_label_refuses_each_unicode_line_separator(char: str) -> None:
    assert valid_label("ab")
    assert not valid_label(f"a{char}b")
    assert not valid_label(f"ab{char}")
    assert not valid_label(char)


def test_label_allows_what_only_the_link_rule_refuses() -> None:
    # The two rules are distinct: a label may hold spaces and other markup.
    assert valid_label("a b")
    assert valid_label('<a>(b)"`\\')
    assert valid_label(" ¡")


@pytest.mark.parametrize("value", [None, 1, b"abc", ["abc"], object()])
def test_label_rejects_non_strings(value: object) -> None:
    assert not valid_label(value)


# --- imports ----------------------------------------------------------------


def _module_path() -> Path:
    assert request.__file__ is not None
    return Path(request.__file__)


def test_module_imports_only_the_standard_library_and_the_vocabulary() -> None:
    tree = ast.parse(_module_path().read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import"
            assert node.module is not None
            names.add(node.module)
    assert names, "the walk found no imports at all"
    for name in names:
        root = name.split(".")[0]
        assert root in sys.stdlib_module_names or name == "fitdocs.publish.outcomes", (
            name
        )


def test_fresh_interpreter_loads_only_the_leaf_modules() -> None:
    code = (
        "import sys\n"
        "import fitdocs.publish.request\n"
        "print(sorted(m for m in sys.modules\n"
        "             if m == 'fitdocs' or m.startswith('fitdocs.')))\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    loaded = ast.literal_eval(result.stdout.strip())
    assert loaded == [
        "fitdocs",
        "fitdocs.publish",
        "fitdocs.publish.outcomes",
        "fitdocs.publish.request",
    ]
