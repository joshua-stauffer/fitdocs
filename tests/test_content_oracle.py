"""Unit tests for `tests/_content_oracle.py`, the shared numeric-value
matcher (`ContentOracle`, Req 3.2, 3.7).

This module owns tokenisation, canonicalisation, entropy estimation,
windowing, digesting and scanning as the *single* shared definition -- no
guard and no script is allowed to write a second, so these tests are the only
place that definition is pinned directly.
"""

from __future__ import annotations

from tests._content_oracle import (
    DIGEST_HEX_LENGTH,
    ENTROPY_FLOOR_BITS,
    canonical,
    digest,
    entropy_bits,
    scan,
    tokens,
    windows,
)

# --- tokens() -----------------------------------------------------------


def test_tokens_finds_integers_decimals_and_clock_times_in_document_order() -> None:
    text = "warm up 5:30 then 12.5 km at 401 W"

    assert tokens(text) == ["5:30", "12.5", "401"]


def test_tokens_on_text_with_no_digits_emits_no_tokens() -> None:
    # Positive control for the walk this function performs over the text:
    # an input with nothing to find must return the empty list, not a
    # spurious match born of an over-eager pattern.
    assert tokens("no numbers in this sentence at all") == []


# --- canonical() ----------------------------------------------------------


def test_canonical_matches_two_spellings_of_one_decimal_value() -> None:
    assert canonical("12.50") == canonical("12.5")
    assert canonical(".5") == canonical("0.5")


def test_canonical_does_not_match_two_different_decimal_values() -> None:
    assert canonical("12.5") != canonical("12.6")


def test_canonical_matches_two_spellings_of_one_clock_time() -> None:
    # "1:02:03" and "01:02:03" are the same instant (3723 seconds) spelled
    # with and without a leading zero on the hour.
    assert canonical("1:02:03") == canonical("01:02:03")


def test_canonical_does_not_match_two_different_clock_times() -> None:
    assert canonical("1:02:03") != canonical("1:02:04")


def test_canonical_converts_clock_times_to_total_seconds() -> None:
    # "60:00" (MM:SS) and "1:00:00" (H:MM:SS) are the same instant -- 3600
    # total seconds -- spelled with a different number of colon-separated
    # fields, which only holds if each field is weighted by 60 (not any other
    # base). Both fixtures above (a leading-zero pair, and a
    # differing-final-digit pair) hold under any positional base, since they
    # never cross a field boundary at a different weight -- this is the
    # fixture design.md's Testing Strategy names explicitly ("MM:SS versus
    # H:MM:SS") to tell `* 60` apart from any other multiplier.
    assert canonical("60:00") == canonical("1:00:00") == "3600"
    # Pin an absolute value too, not only an equivalence, so the actual units
    # the docstring and this module's name promise (seconds) are asserted
    # rather than merely "these two spellings agree on something".
    assert canonical("1:02:03") == "3723"


def test_canonical_strips_thousands_separators_and_leading_zeros_on_integers() -> None:
    assert canonical("1,234") == canonical("01234")


def test_canonical_does_not_match_two_different_integers() -> None:
    # Mirrors the decimal and clock-time negative fixtures above. Pins
    # *trailing* zeros as significant: a mutant that strips them too (e.g.
    # `.strip("0")` in place of `.lstrip("0")`) collapses "100" and "1000"
    # both down to "1", corrupting two different values into one.
    assert canonical("100") != canonical("1")
    assert canonical("1000") != canonical("1")


def test_canonical_of_all_zero_digits_is_the_single_digit_zero() -> None:
    # The integer branch's `digits if digits else "0"` guard: stripping every
    # leading zero from "0" or "000" leaves the empty string, which must fall
    # back to "0" rather than being returned as-is -- an empty canonical form
    # for a real, present token would digest differently than any other
    # window containing a zero, silently mismatching a stored fingerprint.
    assert canonical("000") == canonical("0") == "0"


# --- entropy_bits() --------------------------------------------------------


def test_entropy_bits_depends_only_on_digit_count_not_on_format_or_value() -> None:
    # Same digit count (3), three different format classes and three
    # different values -- all must carry identical entropy, because the
    # guessing entropy an attacker faces comes from the FORMAT CLASS (how
    # many digit characters are present) only, never from which digits they
    # happen to be or which punctuation surrounds them.
    assert entropy_bits("123") == entropy_bits("9.87") == entropy_bits("456")


def test_entropy_bits_grows_with_digit_count() -> None:
    assert entropy_bits("12") < entropy_bits("12345")


# --- windows() --------------------------------------------------------------


def test_windows_over_trivially_small_integers_emits_no_window() -> None:
    # Five one-digit tokens carry ~3.32 bits each, ~16.6 bits total -- nowhere
    # near a 96-bit floor. The whole run is a tail that cannot reach the
    # floor, and must be dropped rather than emitted short.
    toks = ["1", "2", "3", "4", "5"]

    assert windows(toks, ENTROPY_FLOOR_BITS) == []


def test_windows_emits_minimal_length_windows_and_advances_past_each() -> None:
    # Two-digit tokens carry ~6.64 bits each. With floor=6.0, a single token
    # already clears it, so each of the first two tokens becomes its own
    # one-token window (minimal length -- extending to two tokens would not
    # be minimal). The final one-digit token (~3.32 bits) cannot reach 6.0
    # bits alone and is a dropped tail, not a short window.
    toks = ["12", "34", "5"]

    assert windows(toks, 6.0) == [(0, 1), (1, 1)]


def test_windows_advances_the_cursor_past_each_multi_token_window() -> None:
    # Two runs of four one-digit tokens each, floor=10.0 -- each run needs all
    # four of its own tokens (three only reach ~9.97 bits, still short), so
    # the correctly-behaving cursor lands on (0, 4) then (4, 4). A cursor that
    # merely crawls forward one token at a time (`cursor += 1` in place of
    # `cursor = end`) would instead re-enter the accumulation loop from every
    # intermediate offset, emitting (0,4), (1,4), (2,4), (3,4), (4,4) --
    # five windows, not two, and the first four overlap. Every other `windows`
    # fixture in this file emits either single-token windows or a single
    # window, where `cursor = end` and `cursor += 1` are the same statement;
    # this is the one case that tells them apart.
    toks = ["1", "2", "3", "4"] * 2

    assert windows(toks, 10.0) == [(0, 4), (4, 4)]


def test_windows_extends_only_as_far_as_needed_to_clear_the_floor() -> None:
    # Four one-digit tokens, ~3.32 bits each. floor=10.0 needs all four
    # (3 tokens only reach ~9.97 bits, still short) -- so the emitted window
    # must be exactly the whole run, not a longer or shorter one.
    toks = ["1", "2", "3", "4"]

    assert windows(toks, 10.0) == [(0, 4)]


def test_windows_over_a_single_sufficiently_long_token_still_emits_a_window() -> None:
    # The floor is a property of realistic *short* tokens (the shape an
    # identifying value takes), not a mathematical guarantee against any
    # single token whatsoever: a token with enough digit characters of its
    # own clears the floor unaided. 29 one-digit characters carry
    # 29 * log2(10) =~ 96.3 bits, just over ENTROPY_FLOOR_BITS (96.0).
    long_token = "1" * 29

    assert windows([long_token], ENTROPY_FLOOR_BITS) == [(0, 1)]


def test_windows_emits_a_window_whose_entropy_exactly_equals_the_floor() -> None:
    # `entropy_bits("12")` is exactly the floor passed here, so this pins the
    # `>=` in `windows()`'s clearing test against a `>` mutant: under `>=`,
    # the single token clears the floor immediately and is emitted as its own
    # one-token window. Under `>`, the token never "clears" a floor equal to
    # its own entropy, the single-token list is exhausted still short, and
    # the whole (one-token) run is dropped as an unreachable tail -- emitting
    # `[]` instead.
    floor = entropy_bits("12")

    assert windows(["12"], floor) == [(0, 1)]


def test_windows_over_an_empty_token_list_emits_no_window() -> None:
    # Positive control for the walk `windows()` performs: emptying its input
    # collection must not vacuously satisfy anything -- it must return
    # exactly the empty list because there is nothing to walk.
    assert windows([], ENTROPY_FLOOR_BITS) == []


# --- digest() ----------------------------------------------------------------


def test_digest_is_deterministic_for_the_same_tokens_and_salt() -> None:
    toks = ["12.5", "401"]
    salt = b"fixed-salt"

    assert digest(toks, salt) == digest(toks, salt)


def test_digest_differs_for_different_tokens() -> None:
    salt = b"fixed-salt"

    assert digest(["12.5"], salt) != digest(["12.6"], salt)


def test_digest_differs_for_different_salts() -> None:
    toks = ["12.5", "401"]

    assert digest(toks, b"salt-one") != digest(toks, b"salt-two")


def test_digest_length_clears_the_entropy_floor() -> None:
    # `DIGEST_HEX_LENGTH` (32 hex chars = 128 bits) and `ENTROPY_FLOOR_BITS`
    # (96.0) are both security parameters the module chose and wrote
    # rationales for -- neither was pinned at all before this test. Assert
    # the returned digest's actual length (catches `DIGEST_HEX_LENGTH` being
    # silently truncated, e.g. to 8) and the relation the module's own
    # docstrings claim between the two constants (catches `ENTROPY_FLOOR_BITS`
    # being silently lowered, e.g. to 64.0, since a truncated digest below the
    # entropy floor would make Req 3.7's "cannot be read back" collapse to a
    # brute-force search over the smaller of the two).
    assert len(digest(["1"], b"salt")) == DIGEST_HEX_LENGTH == 32
    assert DIGEST_HEX_LENGTH * 4 >= ENTROPY_FLOOR_BITS == 96.0


def test_digest_is_equal_for_two_spellings_of_the_same_canonical_value() -> None:
    # Canonicalisation happens before digesting, so "12.50" and "12.5"
    # (which canonicalise equal) must digest equal too.
    salt = b"fixed-salt"

    assert digest(["12.50"], salt) == digest(["12.5"], salt)


def test_digest_pins_the_underlying_hash_primitive_and_call_shape() -> None:
    # Every other digest() test compares digest() against digest(), which is
    # self-consistent under ANY hash primitive (e.g. a mutant swapping
    # hashlib.sha256 for hashlib.md5 leaves them all green). Req 3.7's
    # "cannot be read back" rests on one-wayness, so the primitive itself, the
    # salt-prefix ordering, and the truncation must be pinned against the real
    # implementation, not merely against each other.
    import hashlib

    assert (
        digest(["1"], b"salt")
        == hashlib.sha256(b"salt" + b"1").hexdigest()[:DIGEST_HEX_LENGTH]
    )


def test_digest_uses_a_separator_between_joined_tokens() -> None:
    # Without a separator between canonicalised tokens, distinct token windows
    # can collide: "1" + "23" and "12" + "3" concatenate to the same digits
    # ("123") even though they are different windows over different tokens.
    # This is the window-boundary ambiguity `"|".join` defends against -- a
    # mutant swapping it for `"".join` would digest these two windows equal,
    # a direct false-positive vector for every guard that re-bases onto scan().
    salt = b"fixed-salt"

    assert digest(["1", "23"], salt) != digest(["12", "3"], salt)


# --- scan() ------------------------------------------------------------------


def test_scan_finds_a_match_at_a_non_zero_offset() -> None:
    # The fingerprinted window is the single token "333", sitting at token
    # index 2 -- preceded by two tokens ("111", "222") that do not match.
    # Only a scan that tries every offset (not merely offset zero) can find
    # it, which is the property that makes a match phase-independent.
    text = "noise 111 222 333 444 more noise"
    salt = b"fixed-salt"
    target_digest = digest(["333"], salt)

    assert scan(text, frozenset({target_digest}), frozenset({1}), salt) is True


def test_scan_reports_no_match_when_nothing_fingerprinted_is_present() -> None:
    text = "noise 111 222 333 444 more noise"
    salt = b"fixed-salt"
    unrelated_digest = digest(["999"], salt)

    assert scan(text, frozenset({unrelated_digest}), frozenset({1}), salt) is False


def test_scan_with_an_empty_fingerprint_set_reports_no_match() -> None:
    # Positive control for the walk `scan()` performs over offsets and
    # lengths: emptying the fingerprint set it checks against must not
    # vacuously report a match -- there is nothing to have matched.
    text = "noise 111 222 333 444 more noise"
    salt = b"fixed-salt"

    assert scan(text, frozenset(), frozenset({1}), salt) is False


def test_scan_with_an_empty_length_set_reports_no_match() -> None:
    # Positive control for the same walk from the other axis: emptying the
    # set of stored window lengths leaves nothing to check either, even
    # though the fingerprint set itself is non-empty.
    text = "noise 111 222 333 444 more noise"
    salt = b"fixed-salt"
    target_digest = digest(["333"], salt)

    assert scan(text, frozenset({target_digest}), frozenset(), salt) is False


def test_scan_does_not_match_a_length_that_overruns_the_token_list() -> None:
    # `scan()`'s `if end > token_count: continue` guard skips a window whose
    # length would run past the end of the token list. Without it, Python
    # slicing silently truncates: `toks[2:7]` over three tokens is just
    # `toks[2:3]`, identical to what a genuine length-1 window at the same
    # offset would digest. The stored fingerprint here is only ever recorded
    # against length 5 (never length 1), so with the guard in place, offset 2
    # length 5 must be skipped and `scan` must report no match -- a mutant
    # that deletes the guard would digest the truncated 1-token tail, match
    # the fingerprint, and wrongly report `True`.
    text = "1 2 3"
    salt = b"fixed-salt"
    fingerprint_for_last_token_alone = digest(["3"], salt)

    result = scan(
        text, frozenset({fingerprint_for_last_token_alone}), frozenset({5}), salt
    )

    assert result is False


def test_scan_never_raises_on_text_with_no_numeric_tokens_at_all() -> None:
    salt = b"fixed-salt"

    result = scan("no digits here", frozenset({"deadbeef"}), frozenset({1}), salt)

    assert result is False


def test_scan_does_not_raise_on_a_token_with_more_than_4300_digit_characters() -> None:
    # CPython 3.11+ raises `ValueError: Exceeds the limit (4300 digits) for
    # integer string conversion` converting a >4300-digit string to `int`
    # (`sys.get_int_max_str_digits()`) -- verified by execution: 4300 digits
    # converts fine, 4301 raises. `canonical()`'s integer branch used to
    # round-trip through `int(token.replace(",", ""))`, which made `scan()`
    # raise on this input instead of the total function both the module
    # docstring and design.md's ContentOracle Postcondition promise ("never
    # opens a file and never raises on malformed input"). A malformed-nothing
    # input like "no digits here" (the case above) cannot pin this: it never
    # reaches the integer branch at all.
    text = "noise " + "1" * 4301 + " more noise"
    salt = b"fixed-salt"

    result = scan(text, frozenset({"deadbeef"}), frozenset({1}), salt)

    assert result is False
