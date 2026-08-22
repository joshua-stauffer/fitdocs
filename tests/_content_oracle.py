"""`ContentOracle` (design.md `#### ContentOracle`, Req 3.2, 3.7): the single
shared definition of tokenisation, canonicalisation, entropy estimation,
windowing, digesting and scanning of numeric values.

No guard and no script may write a second definition of any of these steps --
`scripts/purge/fingerprints.py`'s one-shot generator (task 2.4) and every
guard that re-bases onto this oracle (Major 4) import this module rather than
reimplementing any piece of it.

This module holds no value from the removed material -- only the mechanism.
Task 2.4 is what generates and stores the actual salt, digest set and window
lengths measured against the real files, in a sibling module
(`tests/_content_fingerprints.py`), kept apart so the matcher and its data can
be reviewed separately. `scan()` below is pure and total: it never opens a
file and never raises on malformed input, so it runs on a fresh clone with no
environment (Req 3.1).

Declared limit (Req 3.7, and load-bearing twice): a single isolated value is
not detected here, by construction -- `windows()` only ever emits a window
once its accumulated entropy clears `ENTROPY_FLOOR_BITS`, and one token alone
falls far short of that floor for any realistic format. An identifying token
is exactly one isolated low-entropy value, so this oracle cannot guard
identity; `ForbiddenStrings` exists as a separate mechanism for exactly that
reason, not as "one more digest".
"""

from __future__ import annotations

import hashlib
import math
import re

ENTROPY_FLOOR_BITS = 96.0
"""Minimum guessing entropy, in bits, that a token window must clear before
this module will treat it as fingerprintable.

The threat model this floor defends against is an attacker who knows only a
window's FORMAT CLASS -- how many digit characters it has and how they are
punctuated -- and not the value itself (see `entropy_bits`). 96 bits keeps a
brute-force guess over that search space far outside anything practical, and
sits comfortably clear of the ~2**64 point at which a generic birthday-style
search against the truncated digest below (`DIGEST_HEX_LENGTH`) becomes a
realistic concern. It is also chosen well above the handful of bits any
short numeric token of the kind this domain's tables actually carry supplies
alone, so an isolated short value -- the shape an identifying token takes --
falls short of the floor and needs several consecutive tokens to combine
before `windows()` will emit anything (see the module docstring's declared
limit). This is a property of realistic short tokens, not a mathematical
guarantee: a single token with enough digit characters of its own (roughly
29 or more, at this floor) clears it unaided.
"""

DIGEST_HEX_LENGTH = 32
"""Length, in hex characters, of the truncated digest `digest()` returns --
128 bits of the underlying SHA-256 output. Chosen so truncation itself is not
the weak link relative to `ENTROPY_FLOOR_BITS`: 128 bits of digest space is
far larger than the 96-bit floor the windows it digests are required to
clear."""

_LOG2_10 = math.log2(10)

_CLOCK = r"\d{1,2}(?::\d{2}){1,2}"
_DECIMAL = r"\d+\.\d+|\.\d+"
_INTEGER = r"\d{1,3}(?:,\d{3})+|\d+"
_TOKEN_RE = re.compile(f"(?:{_CLOCK})|(?:{_DECIMAL})|(?:{_INTEGER})")


def tokens(text: str) -> list[str]:
    """Numeric and clock-time tokens, in document order."""
    return [match.group(0) for match in _TOKEN_RE.finditer(text)]


def canonical(token: str) -> str:
    """Format-independent form of `token`.

    Clock times (``h:mm:ss`` or ``mm:ss``) canonicalise to their total
    seconds as a decimal string, so a leading zero on the hour or minute does
    not change the result. Decimals canonicalise through `float`'s own
    canonical repr, so trailing zeros and a missing leading zero before the
    point do not change the result. Integers strip thousands separators
    (``,``) and *leading* zeros only -- trailing zeros are significant, so
    "100" and "1000" canonicalise to different values ("100" and "1000"),
    never to the same one.

    Two spellings *of one value*, within the same token class (clock,
    decimal or integer), canonicalise equal. That is the only guarantee: it
    does NOT extend across token classes, nor to values outside float's
    range or precision:

    - Clock times and integers deliberately share a codomain -- both
      canonicalise to a plain digit string of total seconds/value, so
      "1:00:00" and "3600" collide by design (`3600 == 60 * 60`, the same
      collision as "60" and "1:00").
    - Any decimal whose magnitude exceeds float range canonicalises to
      "inf" (e.g. a token of 4300+ digits before the point), collapsing
      distinct-looking inputs together.
    - Two decimals differing only beyond float's ~17 significant digits
      canonicalise equal: "1.00000000000000001" and "1.00000000000000002"
      both give "1.0", and digest equal under one salt.

    So two *different* values can canonicalise equal in each of the three
    cases above. Every one of them collapses distinct values together, which
    for a detector is a false positive -- noisy, never a miss. No case makes
    a value that IS present fail to match.
    """
    if ":" in token:
        total_seconds = 0
        for part in token.split(":"):
            total_seconds = total_seconds * 60 + int(part)
        return str(total_seconds)
    if "." in token:
        return repr(float(token))
    # Strip textually rather than round-tripping through `int()`: CPython
    # 3.11+ raises `ValueError` converting a >4300-digit string to `int`
    # (`sys.get_int_max_str_digits()`), which would make this function --
    # and `scan()`, which calls it through `digest()` -- raise on a long
    # enough digit run instead of the total function both promise.
    digits = token.replace(",", "").lstrip("0")
    return digits if digits else "0"


def entropy_bits(token: str) -> float:
    """Guessing entropy, in bits, an attacker faces who knows only `token`'s
    FORMAT CLASS -- its count of digit characters -- and not its value.

    Deliberately ignores which digits are actually present and ignores
    punctuation (``:``, ``.``, ``,``): two tokens with the same digit count
    carry identical entropy regardless of format or value, treating each
    digit as an independent draw from ten possibilities. This is a
    conservative floor, not a measurement of the specific token's real
    predictability -- using the actual value here would leak information
    about which value was present, which is exactly what this function must
    not do.
    """
    digit_count = sum(1 for character in token if character.isdigit())
    return digit_count * _LOG2_10


def windows(toks: list[str], floor: float) -> list[tuple[int, int]]:
    """Minimal-length ``(offset, length)`` windows over `toks`, each clearing
    `floor` bits of entropy, advancing the cursor past each emitted window. A
    tail that cannot reach `floor` is dropped rather than emitted short."""
    result: list[tuple[int, int]] = []
    token_count = len(toks)
    cursor = 0
    while cursor < token_count:
        accumulated = 0.0
        end = cursor
        while end < token_count and accumulated < floor:
            accumulated += entropy_bits(toks[end])
            end += 1
        if accumulated >= floor:
            result.append((cursor, end - cursor))
            cursor = end
        else:
            # The remaining tokens are a tail that cannot reach the floor --
            # dropped rather than emitted as a short window.
            break
    return result


def digest(toks: list[str], salt: bytes) -> str:
    """Truncated hex digest over `salt` and the canonical join of `toks`."""
    canonical_join = "|".join(canonical(token) for token in toks)
    full_digest = hashlib.sha256(salt + canonical_join.encode("utf-8"))
    return full_digest.hexdigest()[:DIGEST_HEX_LENGTH]


def scan(text: str, fps: frozenset[str], lengths: frozenset[int], salt: bytes) -> bool:
    """True if any window of any length in `lengths`, at ANY offset in
    `text`'s tokens, digests into `fps`. Trying every offset (not merely
    offset zero) is what makes a match phase-independent."""
    toks = tokens(text)
    token_count = len(toks)
    for offset in range(token_count):
        for length in lengths:
            end = offset + length
            if end > token_count:
                continue
            if digest(toks[offset:end], salt) in fps:
                return True
    return False
