"""Classify a post region and write filled text (post-templates task 2.2).

Requirements 4.6, 4.7, 5.1 to 5.4, 5.10 and 8.4. Round trips go through the
real publish reader, override parser and composer; the known-answer digests
were computed apart from the code under test.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from fitdocs import docmerge
from fitdocs.contract import POST_PLACEHOLDER
from fitdocs.post_template.model import RegionState
from fitdocs.post_template.region import FillStamp, classify, render_filled
from fitdocs.publish.compose import (
    Refusal,
    compose_post,
    override_templates,
    read_post_region,
)
from fitdocs.publish.request import Post

# Distinct from every text digest below, so a swap of the two fields is visible.
_TEMPLATE = "ab" * 32
_AS_OF = datetime(2026, 11, 7, 7, 5, 0)
_AS_OF_FRACTION = datetime(2026, 11, 7, 7, 5, 9, 120)

# SHA-256 of the UTF-8 bytes, computed outside this code base.
_RUN = "efcd703bdd4de958ca8faff68a433b50695183502c9d2caebd890c5b9dd94018"
_RUN_DESC = "f2561e370e60de194ae60dd9512edf63bb8b7862e14cdcfcd48b414ab36af100"


def _fill(post: Post, as_of: datetime = _AS_OF) -> str:
    return render_filled(post, template_digest=_TEMPLATE, as_of=as_of)


def _stamp_line(text: str, *, as_of: str = "2026-11-07T07:05:00") -> str:
    digest = hashlib.sha256(text.encode()).hexdigest()
    return (
        f"<!-- fitdocs:post-fill template={_TEMPLATE} as_of={as_of} text={digest} -->"
    )


def _round_trip(post: Post) -> Post | Refusal:
    override = read_post_region(_fill(post))
    assert override is not None and not isinstance(override, Refusal)
    templates = override_templates(override)
    assert not isinstance(templates, Refusal)
    return compose_post(templates, {})


class TestRenderFilled:
    def test_known_answer_title_only(self) -> None:
        assert _fill(Post("Morning Run", "")) == (
            f"<!-- fitdocs:post-fill template={_TEMPLATE}"
            f" as_of=2026-11-07T07:05:00 text={_RUN} -->\nMorning Run"
        )

    def test_known_answer_with_description(self) -> None:
        got = _fill(Post("Morning Run", "42% of this week"))
        assert got == (
            f"<!-- fitdocs:post-fill template={_TEMPLATE}"
            f" as_of=2026-11-07T07:05:00 text={_RUN_DESC} -->"
            "\nMorning Run\n\n42% of this week"
        )

    def test_fractional_as_of_is_six_digits(self) -> None:
        line = _fill(Post("Morning Run", ""), _AS_OF_FRACTION).split("\n")[0]
        assert " as_of=2026-11-07T07:05:09.000120 " in line

    def test_known_answer_outside_latin_1(self) -> None:
        # Digest from `printf ... | shasum -a 256`; the text has a snowman, a
        # ligature that NFKC rewrites, and a no-break space.
        assert _fill(_UNICODE) == (
            f"<!-- fitdocs:post-fill template={_TEMPLATE}"
            f" as_of=2026-11-07T07:05:00 text={_UNICODE_DIGEST} -->"
            "\nCafé ☃\n\n\ufb01 x\u00a0y"
        )

    def test_aware_as_of_is_refused(self) -> None:

        with pytest.raises(ValueError):
            _fill(Post("T", ""), _AS_OF.replace(tzinfo=UTC))

    def test_braces_are_doubled_in_text(self) -> None:
        text = _fill(Post("a{b}", "c}d{")).split("\n", 1)[1]
        assert text == "a{{b}}\n\nc}}d{{"


_UNICODE = Post("Café ☃", "\ufb01 x\u00a0y")
_UNICODE_DIGEST = "1168abce6025e0a1c4e4584bf082021635239159f1feae3677aa0196320ef454"

_POSTS = [
    Post("Morning Run", ""),
    Post("Morning Run", "42% of this week"),
    Post("T {x} }", "{ alone and } alone"),
    Post("{title}", "{title} is literal here"),
    Post("{{", "{{ and }} already doubled"),
    Post("}}", "}}{{"),
    Post("{", "}"),
    Post("{?x}", "{?{title}}"),
    Post("a", "line one\n\nline three\n  indented"),
    Post("Café ☃", "  leading spaces kept"),
    _UNICODE,
]


class TestRoundTrip:
    @pytest.mark.parametrize("post", _POSTS)
    def test_equals_original(self, post: Post) -> None:
        assert _round_trip(post) == post

    @pytest.mark.parametrize("as_of", [_AS_OF, _AS_OF_FRACTION])
    def test_stamp_is_removed_by_the_reader_for_both_as_of_forms(
        self, as_of: datetime
    ) -> None:
        post = Post("Morning Run", "d")
        override = read_post_region(_fill(post, as_of))
        assert override is not None and not isinstance(override, Refusal)
        assert override.title == "Morning Run"


class TestClassifyFilled:
    @pytest.mark.parametrize("as_of", [_AS_OF, _AS_OF_FRACTION])
    @pytest.mark.parametrize("post", _POSTS)
    def test_own_output_is_filled_with_its_stamp(
        self, post: Post, as_of: datetime
    ) -> None:
        content = _fill(post, as_of)
        state, stamp = classify(content)
        text = content.split("\n", 1)[1]
        assert state is RegionState.FILLED
        assert stamp == FillStamp(
            _TEMPLATE, as_of, hashlib.sha256(text.encode()).hexdigest()
        )

    def test_stamp_fields_are_not_swapped(self) -> None:
        state, stamp = classify(_fill(Post("Morning Run", "")))
        assert state is RegionState.FILLED
        assert stamp is not None
        assert (stamp.template, stamp.text) == (_TEMPLATE, _RUN)


class TestClassifyAthletes:
    def _text(self) -> tuple[str, str]:
        content = _fill(Post("Morning Run", "42% of this week"))
        return content.split("\n", 1)[0], content.split("\n", 1)[1]

    def test_changed_character(self) -> None:
        stamp, text = self._text()
        assert classify(stamp + "\n" + text.replace("42%", "43%")) == (
            RegionState.ATHLETES,
            None,
        )

    @pytest.mark.parametrize(
        ("old", "new"),
        [
            ("☃", "☂"),
            ("\u00a0", " "),
            ("\ufb01", "fi"),
            ("é", "e"),
            ("\u00e9", "e\u0301"),
        ],
    )
    def test_non_ascii_edit(self, old: str, new: str) -> None:
        content = _fill(_UNICODE)
        assert old in content
        assert classify(content.replace(old, new)) == (RegionState.ATHLETES, None)

    @pytest.mark.parametrize(
        "edit",
        [
            lambda t: t.replace("Café", "Café ", 1),
            lambda t: t.replace("Café", " Café", 1),
            lambda t: t.replace("Café", "\tCafé", 1),
            lambda t: t + "\t",
            lambda t: t + " ",
        ],
    )
    def test_whitespace_only_edit_keeps_the_text(
        self, edit: Callable[[str], str]
    ) -> None:
        stamp, text = _fill(_UNICODE).split("\n", 1)
        assert classify(stamp + "\n" + edit(text)) == (RegionState.ATHLETES, None)

    def test_leading_space_on_first_line_of_text(self) -> None:
        stamp, text = _fill(Post("Morning Run", "")).split("\n", 1)
        assert classify(stamp + "\n " + text)[0] is RegionState.ATHLETES

    def test_added_trailing_newline(self) -> None:
        content = _fill(Post("Morning Run", ""))
        assert classify(content + "\n")[0] is RegionState.ATHLETES

    def test_crlf(self) -> None:
        content = _fill(Post("Morning Run", "42% of this week"))
        assert classify(content.replace("\n", "\r\n"))[0] is RegionState.ATHLETES

    def test_crlf_after_the_stamp_only(self) -> None:
        stamp, text = self._text()
        assert classify(stamp + "\n" + text.replace("\n", "\r\n"))[0] is (
            RegionState.ATHLETES
        )

    def test_stamp_removed(self) -> None:
        _, text = self._text()
        assert classify(text) == (RegionState.ATHLETES, None)

    def test_stamp_with_wrong_text_digest(self) -> None:
        _, text = self._text()
        line = _stamp_line("something else")
        assert classify(line + "\n" + text)[0] is RegionState.ATHLETES

    def test_digest_of_template_in_text_field(self) -> None:
        _, text = self._text()
        line = (
            f"<!-- fitdocs:post-fill template={_RUN}"
            f" as_of=2026-11-07T07:05:00 text={_TEMPLATE} -->"
        )
        assert classify(line + "\n" + text)[0] is RegionState.ATHLETES

    def test_stamp_not_on_first_line(self) -> None:
        content = _fill(Post("Morning Run", ""))
        assert classify("\n" + content)[0] is RegionState.ATHLETES
        assert classify(" " + content)[0] is RegionState.ATHLETES

    def test_text_above_the_stamp(self) -> None:
        stamp, text = self._text()
        assert classify("note\n" + stamp + "\n" + text)[0] is RegionState.ATHLETES

    def test_second_stamp_below_the_first(self) -> None:
        stamp, text = self._text()
        other = _stamp_line("other", as_of="2026-11-08T07:05:00")
        assert classify(stamp + "\n" + other + "\n" + text)[0] is RegionState.ATHLETES

    def test_doubled_stamp_line(self) -> None:
        stamp, text = self._text()
        assert classify(stamp + "\n" + stamp + "\n" + text)[0] is RegionState.ATHLETES

    def test_text_after_the_stamp_on_its_line(self) -> None:
        stamp, text = self._text()
        assert classify(stamp + " x\n" + text)[0] is RegionState.ATHLETES

    def test_unparseable_as_of_with_matching_digest(self) -> None:
        text = "Morning Run"
        for bad in (
            "2026-13-07T07:05:00",
            "2026-11-31T07:05:00",
            "2026-11-07T24:05:00",
        ):
            assert classify(_stamp_line(text, as_of=bad) + "\n" + text) == (
                RegionState.ATHLETES,
                None,
            )

    def test_unparseable_as_of_without_text_is_waiting(self) -> None:
        line = _stamp_line("x", as_of="2026-13-07T07:05:00")
        assert classify(line) == (RegionState.WAITING, None)

    def test_athletes_own_text(self) -> None:
        assert classify("My own post\n\nbody") == (RegionState.ATHLETES, None)

    def test_other_comment_is_athletes(self) -> None:
        assert classify("<!-- a note -->")[0] is RegionState.ATHLETES
        assert classify("<!-- never closed")[0] is RegionState.ATHLETES


class TestClassifyWaiting:
    @pytest.mark.parametrize(
        "content",
        [
            "",
            "   \n",
            POST_PLACEHOLDER,
            "\n" + POST_PLACEHOLDER + "\n",
        ],
    )
    def test_untouched_or_emptied(self, content: str) -> None:
        assert classify(content) == (RegionState.WAITING, None)

    @pytest.mark.parametrize("rest", ["", "\n", "\n  \n\n", "  "])
    def test_text_deleted_stamp_kept(self, rest: str) -> None:
        stamp = _fill(Post("Morning Run", "42% of this week")).split("\n")[0]
        assert classify(stamp + rest) == (RegionState.WAITING, None)

    def test_text_deleted_stamp_kept_with_blank_text_whose_digest_matches(self) -> None:
        # The blank text hashes to the stamp's digest; waiting still wins.
        assert classify(_stamp_line("  ") + "\n  ") == (RegionState.WAITING, None)

    def test_two_stamps_and_no_text(self) -> None:
        a = _stamp_line("a")
        b = _stamp_line("b", as_of="2026-11-08T07:05:00")
        assert classify(a + "\n" + b + "\n") == (RegionState.WAITING, None)


class TestStampIsNotAMarker:
    @pytest.mark.parametrize("post", _POSTS)
    def test_no_marker_in_filled_content(self, post: Post) -> None:
        assert docmerge._MARKER_RE.search(_fill(post)) is None  # noqa: SLF001

    def test_filled_region_survives_the_region_scan(self) -> None:
        content = _fill(Post("Morning Run", "d"))
        page = "# t\n\n" + docmerge.region_block("post", content) + "\nafter\n"
        assert docmerge.extract_regions(page) == {"post": content}
