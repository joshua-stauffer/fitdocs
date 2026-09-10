"""Tests for :func:`fitdocs.contract.user_owned_lines` (task 1.3, Req 2.6, 3.2,
4.4, 4.5, 5.5).

Each fixture is a hand-built fenced block (``"\\n".join(...).split("\\n")``,
the lossless decomposition :func:`fitdocs.contract.frontmatter_close_index`
requires). The function is pure and line-level: it parses no YAML and
validates nothing, so a malformed tag is carried exactly like a valid one
(see the malformed fixture below).
"""

from fitdocs.contract import user_owned_lines


def _lines(text: str) -> list[str]:
    return text.split("\n")


# --- a user key between two managed keys (Req 2.6, 4.5) ---------------------


def test_user_key_between_two_managed_keys() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: Easy Run",
                "effort: race",
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == ("effort: race",)


# --- a user key after the load keys at the end (Req 4.5) --------------------


def test_user_key_after_load_keys_at_the_end() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: Easy Run",
                "load_ctl: 42.0",
                "load_atl: 10.0",
                "effort: test",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == ("effort: test",)


# --- a block-scalar event spanning two indented lines (Req 2.6, 3.2) --------


def test_block_scalar_event_spans_two_indented_lines() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: Boston",
                "effort: race",
                "effort_event: >-",
                "  Boston",
                "  Marathon",
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == (
        "effort: race",
        "effort_event: >-",
        "  Boston",
        "  Marathon",
    )


# --- a block-scalar continuation line that itself embeds a colon (Req 2.6,
# 3.2) -- the ``" "``/``"\t"`` indent exclusion, not the colon guard, must be
# what keeps this line from starting a new entry. A colon-free continuation
# (above) cannot discriminate indent-exclusion from colon-exclusion, because
# either guard alone rejects it.


def test_block_scalar_continuation_line_embeds_a_colon() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: Boston",
                "effort_event: >-",
                "  Boston: A Race",
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == (
        "effort_event: >-",
        "  Boston: A Race",
    )


# --- a quoted key (Req 2.6, 3.2) ---------------------------------------------


def test_quoted_key_is_recognized_after_stripping_quotes() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: Easy Run",
                "'effort': hard",
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == ("'effort': hard",)


# --- sibling quote-handling cases (Req 2.6, 3.2) -----------------------------
#
# The matched-pair rule (``key[0] == key[-1] and key[0] in "'\""``) only
# strips a *matched* pair of one of the two quote characters. A double-quoted
# key must be recognized identically to the single-quoted case above; a
# mismatched pair or a doubled pair still satisfies the entry-start
# predicate (the first character is not excluded and the line contains
# ``:``), so the line *is* an entry start -- it just is not a user one,
# because the key text that survives quote stripping is not in USER_KEYS
# (``"effort'`` unchanged for the mismatched pair, ``"effort"`` after one
# pair comes off the doubled one). That is enough to end any carry already
# in progress, even though the line itself is never carried.


def test_double_quoted_key_is_recognized_after_stripping_quotes() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: Easy Run",
                '"effort": hard',
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == ('"effort": hard',)


def test_mismatched_quoted_key_is_not_recognized() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: Easy Run",
                "\"effort': hard",
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == ()


def test_doubled_quoted_key_is_not_recognized() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: Easy Run",
                '""effort"": hard',
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == ()


# --- whitespace before the colon is stripped from the key (Req 2.6, 3.2) ---
#
# ``effort : race`` is valid YAML with key ``effort``; the key extraction
# must strip trailing whitespace from the text before ``:``, not just
# leading/trailing quotes.


def test_whitespace_before_colon_is_stripped_from_key() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: Easy Run",
                "effort : race",
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == ("effort : race",)


# --- a user key followed by a comment line (Req 4.5) -------------------------
#
# The comment line embeds a colon (``# note: my fastest 10k``) so that the
# ``":" in line`` guard cannot reject it before the ``#`` exclusion is ever
# consulted: a colon-less comment is decided by the colon guard, not the
# ``#`` guard, and pins nothing about ``#``.


def test_user_key_followed_by_comment_line() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: Easy Run",
                "effort: hard",
                "# note: my fastest 10k",
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == (
        "effort: hard",
        "# note: my fastest 10k",
    )


# --- a managed sources list immediately before the user key (Req 4.5) ------


def test_managed_sources_list_immediately_before_user_key() -> None:
    """The ``sources:`` list's column-zero ``- `` items must not be mistaken
    for entry starts -- including a dash-value line that itself embeds a
    colon (inside a quoted wikilink), which is exactly the shape that would
    expose a parser that stops excluding ``-`` lines from starting an entry.
    """
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: Easy Run",
                "sources:",
                "- archive/2024-01-01.fit",
                "- archive/2024-01-02.fit",
                "effort_event:",
                '- "[[Boston: A Race]]"',
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == (
        "effort_event:",
        '- "[[Boston: A Race]]"',
    )


# --- two user keys in reverse documentation order (Req 4.5, 5.5) -----------


def test_two_user_keys_in_reverse_documentation_order() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: Easy Run",
                "effort_time_s: 3600",
                "effort: test",
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == (
        "effort_time_s: 3600",
        "effort: test",
    )


# --- a column-zero, colon-less continuation line (Req 2.6, 3.2) -------------
#
# The function is line-level and validates nothing: a continuation line with
# no colon at all -- not indented, not a comment, not a ``-`` item -- must
# still be carried because it never satisfies the entry-start guard's
# ``":" in line`` clause, so ``carrying`` is left unchanged from the
# preceding user entry.


def test_column_zero_colonless_continuation_is_carried() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: Easy Run",
                "effort: hard",
                "plaincontinuation",
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == (
        "effort: hard",
        "plaincontinuation",
    )


# --- no user-owned entry exists (Req 5.5) ------------------------------------
#
# The overwhelming majority of documents in the wiki: a well-formed fence
# with no effort tag at all. This is the shape the docstring's "no
# user-owned entry exists" clause describes and must return ``()``, not a
# sentinel or a non-empty default.


def test_fenced_block_with_no_user_key_returns_empty_tuple() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: Easy Run",
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == ()


# --- a malformed tag, carried identically (Req 3.2, 4.4) --------------------


def test_malformed_tag_carried_identically() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: Easy Run",
                "effort: Marathon",
                "effort_distance_m: -5",
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == (
        "effort: Marathon",
        "effort_distance_m: -5",
    )


# --- no fence (Req 5.5) ------------------------------------------------------


def test_no_fence_returns_empty_tuple() -> None:
    lines = _lines(
        "\n".join(
            [
                "title: Easy Run",
                "effort: race",
            ]
        )
    )
    assert user_owned_lines(lines) == ()


def test_unterminated_block_returns_empty_tuple() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: Easy Run",
                "effort: race",
            ]
        )
    )
    assert user_owned_lines(lines) == ()


# --- a user key immediately after the opening fence (Req 2.6) --------------
#
# The scan starts at ``lines[1]``, immediately after the opening fence, not
# one line later. This fixture contains no other user key, so an off-by-one
# start that skips the first in-fence line would silently drop the only
# user-owned entry rather than merely misattributing it.


def test_user_key_first_line_inside_fence() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "effort: race",
                "title: Easy Run",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == ("effort: race",)


# --- a blank line inside a user entry's continuation (Req 3.2, 4.5) ---------
#
# The design enumerates blank lines as one of the four continuation kinds a
# carried entry may contain. Deleting the ``line and`` non-empty guard from
# the entry-start test does not change behavior on any other fixture in this
# file -- ``line[0]`` is only ever evaluated when ``line`` is truthy -- but a
# blank line here reaches ``line[0]`` on an empty string and raises
# ``IndexError`` in the mutant, defeating "Never raises" outright.


def test_blank_line_inside_user_entry_is_carried() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: x",
                "effort_event: >-",
                "",
                "  Boston",
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == ("effort_event: >-", "", "  Boston")


# --- verbatim trailing whitespace on a carried line (Req 3.2) --------------
#
# Every returned line must be an element of ``lines``, unmodified -- leading
# whitespace is already pinned by the indented block-scalar fixtures above;
# this fixture pins the trailing side, which nothing else in this file
# exercises.


def test_trailing_whitespace_is_preserved_verbatim() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: x",
                "effort: race   ",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == ("effort: race   ",)


# --- the key line itself embeds a colon in its value (Req 2.6) -------------
#
# tasks.md's own shape: the key is the text before the *first* colon. Both
# existing colon-in-value fixtures put the colon on an indented or ``- ``
# line, so the exclusion tuple decides those lines before key extraction is
# ever reached. Here the key line itself is unindented and un-dashed, so key
# extraction is the guard that must get it right.


def test_key_line_itself_embeds_a_colon_in_its_value() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: x",
                'effort_event: "[[Boston: A Race]]"',
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == ('effort_event: "[[Boston: A Race]]"',)


# --- a tab-indented continuation line (Req 3.2) -----------------------------
#
# The indent exclusion is a tuple of two whitespace characters, space and
# tab, and each arm needs its own colon-carrying fixture. The space arm is
# pinned by the colon-carrying continuation fixture above and by nothing
# else -- the colon-free continuations cannot discriminate the indent
# exclusion from the colon guard, for the reason noted above that fixture.
# The tab arm is pinned by this fixture and by nothing else. The
# continuation carries a colon so that the exclusion tuple, not the colon
# guard, is what is under test.


def test_tab_indented_continuation_is_carried() -> None:
    lines = _lines(
        "\n".join(
            [
                "---",
                "title: x",
                "effort_event: >-",
                "\tBoston: A Race",
                "sport: running",
                "---",
                "",
            ]
        )
    )
    assert user_owned_lines(lines) == ("effort_event: >-", "\tBoston: A Race")
