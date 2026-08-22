"""Shape guard for `tests/_content_fingerprints.py`, the generated data
module task 2.4's one-shot generator produced (design.md `####
ContentOracle`, Req 3.2, 3.7).

That module is irreproducible once task 3.1 deletes the source material it
was measured against. Before encumbered-content-purge task 4.1 re-based the
sdist guard onto it, nothing else in the suite imported it, and it was
reachable only by mypy (`tests/_content_fingerprints.py` in
`pyproject.toml`'s `files` list); `tests/load/test_packaging.py` now imports
`FINGERPRINTS`, `SALT` and `WINDOW_LENGTHS` from it directly. This test
asserts its SHAPE only: that it
binds exactly the allowed top-level names; that its recorded entropy floor
and digest length agree with the oracle's own; that its salt, digest set and
window-length set are non-empty and well-formed; that `SOURCE_COUNT` is a
positive integer; and that the digest set and window-length set each have
the exact recorded count, not merely a non-empty one. It asserts no value --
a wrong salt would still collapse detection to nothing without this test
ever comparing to what was actually removed, but a truncation of either set
no longer would: the exact-count assertions below red on a single dropped
element.
"""

from __future__ import annotations

from tests import _content_fingerprints as generated
from tests._content_oracle import DIGEST_HEX_LENGTH, ENTROPY_FLOOR_BITS

_ALLOWED_TOP_LEVEL_NAMES = {
    "SALT",
    "ENTROPY_FLOOR_BITS",
    "DIGEST_HEX_LENGTH",
    "GENERATED_AT",
    "SOURCE_COUNT",
    "WINDOW_LENGTHS",
    "FINGERPRINTS",
}


def _module_bindings() -> set[str]:
    # `from __future__ import annotations` itself binds a module-level name
    # ("annotations") that is not part of the generated data -- excluded
    # alongside dunders.
    return {
        name
        for name in vars(generated)
        if not name.startswith("__") and name != "annotations"
    }


def test_module_binds_exactly_the_seven_allowed_names() -> None:
    assert _module_bindings() == _ALLOWED_TOP_LEVEL_NAMES


def test_recorded_entropy_floor_and_digest_length_agree_with_the_oracle() -> None:
    assert generated.ENTROPY_FLOOR_BITS == ENTROPY_FLOOR_BITS
    assert generated.DIGEST_HEX_LENGTH == DIGEST_HEX_LENGTH


def test_fingerprints_and_window_lengths_are_non_empty() -> None:
    assert generated.FINGERPRINTS, "an empty fingerprint set makes detection vacuous"
    assert generated.WINDOW_LENGTHS, (
        "an empty window-length set makes detection vacuous"
    )


def test_every_fingerprint_is_lowercase_hex_of_the_recorded_length() -> None:
    for fingerprint in generated.FINGERPRINTS:
        assert len(fingerprint) == generated.DIGEST_HEX_LENGTH
        assert fingerprint == fingerprint.lower()
        assert all(character in "0123456789abcdef" for character in fingerprint)


def test_window_lengths_are_positive_integers() -> None:
    for length in generated.WINDOW_LENGTHS:
        assert isinstance(length, int)
        assert length > 0


def test_salt_is_non_empty_bytes() -> None:
    assert isinstance(generated.SALT, bytes)
    assert len(generated.SALT) > 0


def test_source_count_is_positive() -> None:
    assert isinstance(generated.SOURCE_COUNT, int)
    assert generated.SOURCE_COUNT > 0


def test_fingerprints_and_window_lengths_have_the_expected_counts() -> None:
    # A partial truncation of either set (Major 2's species one level down)
    # would still pass the non-emptiness check above -- pin the exact counts
    # too. Counts are shape, not value (Req 3.7 permits recording a count).
    assert len(generated.FINGERPRINTS) == 434
    assert len(generated.WINDOW_LENGTHS) == 14
