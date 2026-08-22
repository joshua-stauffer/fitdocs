"""`ForbiddenStrings` (design.md `#### ForbiddenStrings`, Req 3.3, 3.4, 3.7,
11.7, 11.8, 11.9, 11.10): the only remaining mechanism by which the fitdocs
repository can detect that an identifying token -- or a removed-path
fragment -- has come back.

This module holds no forbidden string itself. The match data is read at run
time from the file named by a single, neutrally-named environment variable,
`FITDOCS_FORBIDDEN_STRINGS` -- the name carries no token, satisfying Req
11.10 for the key as well as for the values it names.

`load()`'s only silent outcome is an UNSET variable, which returns `None`.
Every other broken state -- a missing file, an unreadable file, an empty
file, or a path that resolves inside the repository working tree -- raises
`ForbiddenStringsSourceError` instead of collapsing into that same `None`.
Collapsing any of those four into "absent" is the vacuous-walk anti-pattern
`change-protocol.md` names: a guard built on a silently-absent source reports
success having checked nothing. `require()` is the skip-or-load helper the
guards call -- it turns the ONE legitimate silent outcome (unset) into a
`pytest.skip`, which is a distinguishable result a caller must observe as a
skip, never mistake for a pass (Req 11.8).

File format: one entry per line, optionally `<category>\\t<value>` (the
category is metadata only -- `matches()` does not distinguish by category,
so a category-tagged token line and a category-tagged removed-path-fragment
line are both just strings to search for). A line with no tab is taken
whole. Blank lines and lines starting with ``#`` are ignored. 2.3 is what
populates this file's contents (out-of-repository); this module only reads
whatever format it defines.

`matches()` is wrap-tolerant for a multi-word value and a flat substring
test for a single-word one -- see its docstring for the measurement that
forced that, and `_wrap_tolerant_pattern` for why the pattern is the
redaction rules' own.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

ENV_VAR = "FITDOCS_FORBIDDEN_STRINGS"
"""Name of the single environment variable `load` reads. Neutrally named so
the key itself carries no identifying token (Req 11.10)."""


class ForbiddenStringsSourceError(RuntimeError):
    """Raised by `load` when `FITDOCS_FORBIDDEN_STRINGS` is set but names a
    source that cannot be used: missing, unreadable, empty (including a file
    of only comments and blank lines), or resolving inside the repository
    working tree.

    Deliberately distinct from `load` returning `None` -- that return is
    reserved for the variable being unset, the only outcome Req 11.8 allows
    to be silent.
    """


@dataclass(frozen=True)
class ForbiddenStrings:
    """The loaded match data: every string to search for, and the resolved
    path it came from.

    `values` is never empty -- construction rejects an empty tuple, so this
    invariant holds regardless of how an instance is built, not only when it
    comes through `load`.
    """

    values: tuple[str, ...]
    source: Path

    def __post_init__(self) -> None:
        if not self.values:
            raise ValueError("ForbiddenStrings.values must not be empty")


@dataclass(frozen=True)
class Hit:
    """One place `scan_tree` found a match: the file's path (relative to the
    scanned root), which surface matched (``"content"`` or ``"path"``), and
    every forbidden string found on that surface."""

    path: Path
    surface: str
    found: tuple[str, ...]


def _parse(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        _category, separator, rest = stripped.partition("\t")
        values.append(rest if separator else stripped)
    return tuple(values)


def load(repo_root: Path) -> ForbiddenStrings | None:
    """Read the file named by `FITDOCS_FORBIDDEN_STRINGS`.

    Returns `None` when the variable is unset -- the ONLY silent outcome,
    and it is never a pass. Raises `ForbiddenStringsSourceError` when the
    variable is set but the file is missing, unreadable, empty, or resolves
    inside `repo_root`.
    """
    raw = os.environ.get(ENV_VAR)
    if raw is None:
        return None

    candidate = Path(raw)
    try:
        resolved_source = candidate.resolve(strict=True)
    except OSError as exc:
        raise ForbiddenStringsSourceError(
            f"{ENV_VAR}={raw!r} names a path that does not exist"
        ) from exc

    resolved_repo_root = repo_root.resolve()
    if resolved_source == resolved_repo_root or resolved_source.is_relative_to(
        resolved_repo_root
    ):
        raise ForbiddenStringsSourceError(
            f"{ENV_VAR}={raw!r} resolves to {resolved_source}, which lies "
            f"inside the repository working tree {resolved_repo_root}"
        )

    try:
        text = resolved_source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ForbiddenStringsSourceError(
            f"{ENV_VAR}={raw!r} names a file that could not be read: {resolved_source}"
        ) from exc

    values = _parse(text)
    if not values:
        raise ForbiddenStringsSourceError(
            f"{ENV_VAR}={raw!r} names a source with no entries: {resolved_source}"
        )

    return ForbiddenStrings(values=values, source=resolved_source)


def require(repo_root: Path) -> ForbiddenStrings:
    """`load`, or `pytest.skip` naming `FITDOCS_FORBIDDEN_STRINGS` when it is
    unset.

    Skipping is the distinguishable result Req 11.8 demands in place of a
    guard reporting success having checked nothing. A broken (rather than
    unset) source still raises `ForbiddenStringsSourceError` here -- only the
    genuinely-unset case becomes a skip.
    """
    forbidden_strings = load(repo_root)
    if forbidden_strings is None:
        pytest.skip(f"{ENV_VAR} is unset; forbidden-string checks skipped")
    return forbidden_strings


def _whitespace_tolerant_pattern(phrase: str) -> str:
    """`phrase`'s words, `re.escape`d, joined by `\\s+` -- tolerates a
    line-wrap landing between any two words of a multi-word phrase (measured:
    the 3-word methodology name and the 2-word full name both wrap across a
    line in real history).

    **Moved here from `scripts/purge/replacements.py`** (encumbered-content-
    purge task 7.2, design.md `#### MachineryRetirement` Phase R0). This
    module's own `_wrap_tolerant_pattern` below used to lazily IMPORT this
    helper from `scripts.purge.replacements` -- the arrow ran backwards for a
    module the design already designates a survivor: `scripts/purge/` is the
    machinery Req 12.1 retires, `tests/_forbidden_strings.py` is a guard
    helper Req 12.2 requires to survive it, so the dependency now runs
    `scripts/purge/` -> `tests/_forbidden_strings.py`, never the other
    direction. `scripts/purge/replacements.py::build_rules` (and the token
    tier and case-variant-discovery functions it calls) import this function
    from here for the remainder of that module's life."""
    words = phrase.split()
    return r"\s+".join(re.escape(word) for word in words)


def _wrap_tolerant_pattern(value: str) -> re.Pattern[str]:
    """`value`'s words joined by a flexible whitespace run, compiled case-
    insensitively.

    Built from `_whitespace_tolerant_pattern` above -- the SAME helper
    `scripts/purge/replacements.py::build_rules` uses to make the redaction
    rules wrap-tolerant -- so that what this matcher looks for and what the
    rules replace cannot drift apart. That was the whole defect: the rules
    were wrap-tolerant and every check on them was a flat substring test, so
    no check could observe whether the rules had done their job on a wrapped
    occurrence.

    **No cache of its own, deliberately.** `matches` is on the hot path of
    guards that scan every tracked file (632) and, through
    `scripts/purge/plan.py` and `scripts/purge/verify.py`, every reachable
    blob (1936), so a compiled-pattern cache keyed by value is the obvious
    thing to add here -- and measured over that real corpus it buys nothing,
    because `re.compile` already keeps its own cache keyed by (pattern
    string, flags). Like for like, at this call site, best of three passes
    over all 1936 blobs: 0.449s as written, 0.441s with a module-level dict
    cache in front of it. A cache that cannot be measured also cannot be
    pinned -- an identity assertion (`_wrap_tolerant_pattern(v) is
    _wrap_tolerant_pattern(v)`) passes with the dict removed, because `re`'s
    own cache hands back the same object; that assertion was written, it
    survived the mutation that deletes the dict, and it was deleted with the
    dict rather than kept as a pin of `re`'s behaviour dressed up as a pin
    of ours.

    Sharing the helper with the rules is safe HERE, where this matcher is
    the thing being checked as much as a checker; it is deliberately NOT
    shared by the checks that measure the rules' output -- see
    `tests/purge/test_replacements.py::_tokens_surviving_in`, which derives
    the same tolerance by whitespace normalisation instead, so that a defect
    in this helper cannot make the rule and its own invariant agree.
    """
    return re.compile(_whitespace_tolerant_pattern(value), re.IGNORECASE)


# --- Copyright-notice / trademark-mark constants and the notice/mark tip
# guard's independent survivor counter (encumbered-content-purge task 7.2,
# design.md `#### MachineryRetirement` Phase R0, Req 3.3, 11.4, 11.6, 11.8,
# 11.9, 11.12, 12.2) --------------------------------------------------------
#
# Moved here from `scripts/purge/replacements.py` and
# `tests/purge/test_replacements.py`. The guard's own pytest test function,
# `test_the_notice_phrase_and_mark_are_absent_from_every_tracked_file`, lives
# in `tests/test_forbidden_strings.py` (a guard is a test, not library code);
# everything it is BUILT FROM -- the constants and the independent survivor
# counter -- lives here instead, as ordinary importable library code, so that
# `scripts/purge/replacements.py`'s rule builders (which need the constants)
# and `tests/purge/test_replacements.py`'s surviving `notice_rules`-behaviour
# tests (which need the counter) can both import from one place without a
# test module importing from a sibling test module.
#
# Two properties survive the move unchanged, because they are the whole
# reason the earlier location was safe:
#
# - **The phrase is never spelled contiguously in this module's own source**
#   (or in `scripts/purge/replacements.py`'s, or in
#   `tests/test_forbidden_strings.py`'s): it is kept as a word tuple
#   (`_NOTICE_PHRASE_WORDS`) and assembled into a contiguous string only at
#   run time, by whichever caller needs it (`scripts/purge/replacements.py
#   ::notice_phrase`, or a plain `" ".join(...)` where only the flat form is
#   needed) -- every one of those callers is itself a tracked blob at the
#   tip, where the redaction rules `notice_rules` builds require the whole
#   rule set to be a no-op (`scripts/purge/replacements.py`'s own module
#   docstring, "invariant 6").
# - **The survivor counter below shares no implementation with
#   `_whitespace_tolerant_pattern` / `_wrap_tolerant_pattern` above.** A
#   counter that called the same pattern the redaction rule was built from
#   could not disagree with that rule -- which is exactly how it went from
#   scoring the corpus 49 -> 0 while 11 comment-wrapped notices stood
#   untouched in a real rewrite (`scripts/purge/replacements.py`'s own
#   `_NOTICE_WORD_SEPARATOR` docstring records the incident). The counter
#   below is built from nothing above: it splits and compares word lists of
#   its own, never a second copy of `_NOTICE_WORD_SEPARATOR`'s pattern.

_COPYRIGHT_SIGN = "\u00a9"
"""The copyright sign, spelled as a Python string escape so this module's own
source never carries the character. `scripts/purge/replacements.py`'s
notice-rule patterns interpolate this exact value (never re-typing the
escape, never importing it re-spelled), which is what keeps those patterns
safe in git filter-repo's BYTES domain -- see that module's "EVERY PATTERN IN
THIS SECTION IS COMPILED TWICE" section header for why a `\\uXXXX` escape
written directly into a pattern string is not equivalent."""

_TRADEMARK_MARK = "\u2122"
"""The trademark mark, spelled as an escape. Unlike the sign, the mark IS a
needle the notice/mark tip guard removes on sight, so a literal in tracked
source would make the file that carried it match the guard's own rule."""

_NOTICE_PHRASE_WORDS: tuple[str, ...] = ("All", "Rights", "Reserved")
"""The reserved-rights phrase, **as separate words on purpose**: a source
file that spelled it contiguously would be a match for the notice/mark tip
guard below and for `scripts/purge/replacements.py::notice_rules`'s own
emitted rules, and this module, `scripts/purge/replacements.py` and
`tests/test_forbidden_strings.py` are all tracked blobs at the tip.

This is NOT a forbidden value: it names nobody, which is exactly why no
matcher in `matches()` above flags it. It is not read from
`FITDOCS_FORBIDDEN_STRINGS` and must not be added to it."""

_NOTICE_CONTINUATION_MARKERS = r"[ \t\r#>*|/]"
"""One character of a line's continuation prefix: horizontal whitespace, a `#`
comment marker (TOML, INI, shell, YAML, Python), a `/` (as in `//`), a
markdown blockquote `>`, the `*` list bullet, a table cell `|`. ASCII only, so
it means the same thing in both the `str` and the `--replace-text` bytes
domain `scripts/purge/replacements.py` also compiles this shape in.

**This is the set observed in the real corpus this shape was measured
against, not the complete set of things a line can open with.** It notably
omits `-`, which is the commoner markdown bullet, and `+`, `;`, `%`, `!` and
`"`. This module's own independent survivor counter (`_count_notice_phrase`
/ `_notice_word_chunks` / `_NOTICE_CONTINUATION_STRIP`, below) omits the
same characters (deliberately spelled a second, independent time rather than
built from this constant), so no test in this module or in
`tests/test_forbidden_strings.py`, which imports and calls the counter but
does not redefine it, can catch a widening of this set on its own -- a later
reader must re-measure the real corpus rather than assume the omission stays
safe.

**A flat class, deliberately, and this is a performance contract rather than
a style choice.** An ambiguous nested quantifier here (a run of markers split
between an inner `+` and an outer `*` in exponentially many ways) measured at
roughly 4x cost per two extra markers -- 24 markers took 1.416s against a
non-matching tail, putting 40 markers at roughly 26 hours. This flat class
costs 3e-05s at 2000 markers instead, for the identical match spans over
every case actually observed."""

_NOTICE_WORD_SEPARATOR = (
    rf"(?:[ \t\r\f\v]*(?:\n{_NOTICE_CONTINUATION_MARKERS}*)+"
    r"|[ \t\r\f\v]+)"
)
"""What may stand between two words of the reserved-rights phrase: either a
run of plain horizontal whitespace, or one or more LINE BREAKS, each followed
by whatever continuation prefix the next line opens with (possibly none at
all -- a plain, uncommented line wrap is the zero-marker case of the same
branch).

Every repetition inside the first branch begins with a mandatory `\n`, so no
input can be split between iterations in more than one way -- see
`_NOTICE_CONTINUATION_MARKERS` for what the ambiguous version cost.

**This is why the notice phrase does not reuse `_whitespace_tolerant_pattern`
above, and the difference is worth 11 surviving notices.** That helper joins
words with `\\s+`, which is right for the identifying tokens (measured: not
one of the 485 multi-word token occurrences in this repository's history is
comment-wrapped) and wrong here: the notice lives in `pyproject.toml`
comments and markdown blockquotes, where a wrap puts `# ` or `> ` between the
words. Measured over every reachable blob at the time this was first
measured: 49 occurrences in 31 blobs with whitespace-only tolerance against
**60 occurrences in 42 blobs** with continuation tolerance -- 11 notices that
a whitespace-only rule left standing in a real rewrite, 10 of them in
`pyproject.toml` and one in `tests/purge/test_tree_removal.py`.

Explicit ASCII whitespace rather than `\\s`, because `\\s` is Unicode-aware as
`str` and ASCII-only as bytes; spelling it out keeps the rule identical in
both domains and keeps it in step with the independent survivor counter
below, which splits on the same class."""


_NOTICE_CONTINUATION_STRIP = re.compile(r"^[ \t\r#>*|/]*")
"""A line's leading continuation prefix -- whitespace, comment markers,
blockquote markers, bullets, table cells -- stripped so a notice that wraps
onto a continuation line reads as consecutive words.

Flat, and matching what `_NOTICE_CONTINUATION_MARKERS` above admits,
character for character. The two are written independently (a per-line `sub`
here, a repetition inside one compiled pattern there) but they must admit the
same prefixes: a rule looser than this oracle rewrites text the oracle does
not count -- which is how the rule generator once came to rewrite its own
docstrings while both tip guards called the tree clean.

Two limits a later reader must not read past. **The character-for-character
claim is about these two constants only**, not about the whole comparison:
`_ASCII_WHITESPACE_SPLIT` below also treats `\\f` and `\\v` as whitespace, so
for a form feed or vertical tab immediately after a newline this oracle counts
a phrase the rule does not match. That asymmetry is in the safe direction: the
oracle being *stricter* than the rule reds an acceptance test rather than
passing one silently. **And both sides omit the same characters** -- `-`,
`+`, `;`, `%`, `!`, `"` -- so no test in this suite can catch that omission;
see `_NOTICE_CONTINUATION_MARKERS` for why it is safe today and what must be
re-measured before it is ever widened."""

_ASCII_WHITESPACE_SPLIT = re.compile(r"[ \t\n\r\f\v]+")


def _notice_word_chunks(text: str) -> list[str]:
    """`text` as whitespace-delimited chunks, with each line's leading
    continuation markers removed first.

    **Deliberately built from nothing above, and that is the whole point.**
    An earlier version of this counter called the same
    `_whitespace_tolerant_pattern` the redaction rule was built from, so it
    could not disagree with the rule: it scored the corpus 49 -> 0 and passed
    while 11 comment-wrapped notices stood untouched in a real rewrite. A
    check that shares an implementation with the code under test measures
    nothing. This is the same independence
    `tests/purge/test_replacements.py`'s own identity-rule adjacency oracle
    has against the identity anchors -- splitting and comparing word lists,
    never a second copy of the pattern."""
    stripped = "\n".join(
        _NOTICE_CONTINUATION_STRIP.sub("", line) for line in text.split("\n")
    )
    return _ASCII_WHITESPACE_SPLIT.split(stripped)


def _is_ascii_letter(character: str) -> bool:
    return character.isascii() and character.isalpha()


def _count_notice_phrase(text: str, *, fold_case: bool = True) -> int:
    """How many times the reserved-rights phrase stands in `text` as
    consecutive whole words, tolerating a wrap onto a continuation line.

    The structure mirrors what `scripts/purge/replacements.py::notice_rules`
    can actually match, without being that rule: **between** the phrase's
    words only whitespace and continuation markers may stand (so a chunk
    carrying trailing punctuation, as in a three-element word tuple
    `("All", ...)`, is not the phrase -- the comma is something no rule can
    cross), while **outside** it any non-letter may (a quote, a backtick, a
    bracket, a digit), because the rule's own anchors are
    `(?<![A-Za-z])`/`(?![A-Za-z])` rather than `\\b`.

    Case-folded by default: if a variant appears that a case-variant scan
    does not reach, a case-sensitive counter would report zero survivors
    while one stood in the corpus."""
    words = list(_NOTICE_PHRASE_WORDS)
    chunks = _notice_word_chunks(text)
    if fold_case:
        words = [word.lower() for word in words]
        chunks = [chunk.lower() for chunk in chunks]

    hits = 0
    span = len(words)
    for index in range(len(chunks) - span + 1):
        window = chunks[index : index + span]
        if any(window[k] != words[k] for k in range(1, span - 1)):
            continue  # an interior word must be a chunk of its own, exactly
        first, last = window[0], window[-1]
        if not first.endswith(words[0]) or not last.startswith(words[-1]):
            continue
        before = first[: -len(words[0])]
        after = last[len(words[-1]) :]
        if before and _is_ascii_letter(before[-1]):
            continue
        if after and _is_ascii_letter(after[0]):
            continue
        hits += 1
    return hits


def matches(text: str, forbidden_strings: ForbiddenStrings) -> tuple[str, ...]:
    """Every value of `forbidden_strings` present in `text`, case-
    insensitively, in `forbidden_strings.values` order.

    Returns every match rather than only the first, so a failure message can
    name what it found without the caller holding a second copy of the data.

    **A multi-word value is matched wrap-tolerantly.** Markdown prose wraps,
    so a value whose words land either side of a line break is present in the
    document even though `value in text` is `False`. Measured over every
    reachable blob at `89b06b8`: the two multi-word values of the real
    source occur 448 times flat and 485 times wrap-tolerantly -- 37 wrapped
    occurrences, in 13 (value, blob) pairs where the flat test saw NONE of
    the value at all. Any whitespace run matches, including a blank line;
    nothing else does, so `Planted, Token` and `Planted and then Token` are
    not matches.

    **A single-word value keeps the flat test exactly.** A word cannot wrap,
    so there is nothing to tolerate; taking the flat branch for it is both
    the cheaper path and the one that cannot regress -- it is character-for-
    character the pre-existing behaviour. Measured over this repository's
    real corpus (1936 blobs, 42.7 MB, 9 values of which 7 are single-word),
    best of three passes each: the old flat matcher 0.169s, this function as
    written 0.459s, and this function with every value taking the regex
    branch 1.445s. So wrap tolerance costs ~0.3s per full-corpus scan and
    the single-word branch saves ~1.0s of it; both wrap-tolerant forms find
    1152 (value, blob) pairs where flat finds 1139 -- the 13 pairs the queue
    item measured. The same branch takes a value that is empty or all
    whitespace, which has no words to join. For an all-whitespace value that
    genuinely saves you, since its wrap-tolerant pattern would otherwise be
    the empty pattern and match every text; for an empty value it changes
    nothing, because the flat branch matches every text too. `_parse` cannot
    produce either, and `__post_init__` rejects only an empty tuple rather
    than an empty member, so this is defensive only.
    """
    lowered = text.lower()
    found: list[str] = []
    for value in forbidden_strings.values:
        if len(value.split()) > 1:
            if _wrap_tolerant_pattern(value).search(text):
                found.append(value)
        elif value.lower() in lowered:
            found.append(value)
    return tuple(found)


def scan_tree(root: Path, forbidden_strings: ForbiddenStrings) -> tuple[Hit, ...]:
    """Scan every file under `root` -- both its content and its path name --
    for `forbidden_strings`.

    `root` is a parameter, not a repository constant, so a positive control
    can run against a synthetic tree containing a planted instance -- task
    4.2's documentation guard corpus builder is expected to take `root` the
    same way, for the same reason. A file whose content cannot be read is
    scanned on its path name only; its content is skipped rather than
    raising, since a scan must run to completion (Req 3.1) even over a
    binary file. That covers two cases, not one: a file that cannot be
    decoded as UTF-8, and a file that cannot be opened at all (an
    unreadable mode, a broken symlink). **The second case is silent**: an
    unreadable file whose content carries a forbidden value yields no hit
    and no report, which is the "scanned nothing, said nothing" shape this
    module is otherwise careful to avoid. Task 4.3, which runs this against
    the real tree, owes a report of files it could not read -- absence of a
    hit here does not mean absence of the value.

    Walks the tree in full, dot-paths included. That is load-bearing rather
    than incidental: this repository keeps its token-bearing prose under
    `.kiro/`, so a walk that skipped dot-directories would miss the
    material and still report a clean scan.

    Walks every file under `root` with no tracked/ignored filtering of its
    own -- design.md's Service Interface describes the scan as covering
    "every tracked file", so a caller scanning a real repository working
    tree (task 4.3) is responsible for restricting `root`'s contents (e.g.
    a git-tracked-only worktree, or an equivalent filter) before calling
    this function, so that ignored paths such as `.venv/` or `dist/` are
    not walked.
    """
    hits: list[Hit] = []
    files = sorted(candidate for candidate in root.rglob("*") if candidate.is_file())
    for path in files:
        relative = path.relative_to(root)

        path_matches = matches(str(relative), forbidden_strings)
        if path_matches:
            hits.append(Hit(path=relative, surface="path", found=path_matches))

        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        content_matches = matches(content, forbidden_strings)
        if content_matches:
            hits.append(Hit(path=relative, surface="content", found=content_matches))

    return tuple(hits)
