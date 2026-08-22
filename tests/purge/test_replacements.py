r"""`scripts/purge/replacements.py`: the `--replace-text` rule generator
(task 6.4, design.md `#### HistoryRewrite`, Req 3.3, 3.4, 11.1, 11.2, 11.8).

Two classes of test:

- **Mechanics** (no `FITDOCS_FORBIDDEN_STRINGS` needed): every fixture uses
  synthetic tokens (`Foo Bar`, `Bar`, `Foo Bar Corp`, `FBC`) shaped like the
  real four-row token category (2 words / 1 word / 3 words / 1 word) but
  holding no forbidden value at all -- this file's own content is scanned
  by the standing token guard, so it must be able to stay green with the
  source unset.
- **Acceptance** (gated on `FITDOCS_FORBIDDEN_STRINGS` via
  `tests._forbidden_strings.require`, skipping -- never silently passing --
  when it is unset): the six invariants, measured against the real object
  database, matching the skip/fail contract Req 11.8 requires (`require`
  skips only on unset; a set-but-broken source still raises through
  `tests._forbidden_strings.load`, exercised directly in
  `test_source_set_but_broken_raises_rather_than_skips` below).

**If you are editing the identity rule's anchors, the adjacency table is
the gate -- not this suite.** Four review rounds each found a real defect on
an adjacency axis nobody had enumerated in advance: the orphan union term,
letter case, substring containment, then the lookbehind's character class
and the lookahead's alphabet. Fixing them one at a time did not converge, so
`test_identity_rule_adjacency_matches_email_shape` bounds the space instead:
700 cells, each expecting redaction exactly when `_EMAIL_SHAPE` -- production's
own definition of an address, used here as an ORACLE -- says the bare address
is present as a complete token.

The reason that matters is concrete. **A proposed anchor that passes this
suite is not thereby correct.** A carefully reviewed candidate,
`(?![A-Za-z0-9-])(?!\.[A-Za-z])`, was offered as a verified green drop-in;
it was green, and it disagreed with the oracle 48 times in one product space
and 60 in another measured independently -- including under-redactions
(`<addr>7`, `<addr>-`, `<addr>-based`, `<addr>.c`) that leave a real identity
intact, which in a one-shot rewrite means it survives into published history.
It was green because the suite had no cell for those shapes, which is exactly
what the table now supplies. Change an anchor only with the table re-run and
its expectations re-derived from the oracle, never from what the anchor is
expected to do.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest
from scripts.purge.plan import read_blob_text
from scripts.purge.replacements import (
    _ABBREVIATIONS_BEFORE_PERIOD,
    ReplacementRule,
    _case_matched_adjective,
    _token_tier_rules,
    apply_rules,
    build_rules,
    given_name_rules,
    identity_email_rule,
    load_tokens,
    notice_phrase,
    notice_rules,
    observed_case_variants,
    observed_notice_case_variants,
    render_masked_table,
    render_rules,
    scan_commit_messages_for_rules,
    scan_repo_for_rules,
    trademark_mark_rule,
)

from tests._forbidden_strings import (
    _TRADEMARK_MARK,
    ForbiddenStringsSourceError,
    _count_notice_phrase,
    _whitespace_tolerant_pattern,
    load,
    require,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _commit_blob(repo: Path, name: str, content: str) -> None:
    (repo / name).write_text(content, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-m", f"add {name}")


def _remove_blob(repo: Path, name: str) -> None:
    """Delete `name` in a follow-up commit, so its content survives only in
    reachable HISTORY and is absent from the tip tree. Several fixtures below
    need exactly that shape: `identity_leak_addresses` sanctions any candidate
    address the tip still holds (task 6.3 emptied the tip, so what remains
    there is by construction not what this rewrite removes), so a fixture that
    leaves its planted address at the tip is asserting the sanctioned branch,
    not the leak branch."""
    _git(repo, "rm", "-q", name)
    _git(repo, "commit", "-m", f"remove {name}")


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    return repo


# --- pure mechanics: whitespace / case helpers -------------------------------


def test_whitespace_tolerant_pattern_joins_words_with_flexible_whitespace() -> None:
    pattern = _whitespace_tolerant_pattern("Foo Bar Corp")
    assert pattern == r"Foo\ Bar\ Corp".replace(r"\ ", r"\s+")


def test_whitespace_tolerant_pattern_matches_across_a_line_wrap() -> None:
    import re

    pattern = _whitespace_tolerant_pattern("Foo Bar")
    assert re.search(pattern, "Foo\n  Bar")
    assert re.search(pattern, "Foo Bar")
    # Mutation: dropping \s+ in favour of a literal space reds this test --
    # a plain space cannot span the newline above.
    assert not re.search(r"\bFoo Bar\b", "Foo\n  Bar")


@pytest.mark.parametrize(
    "variant,expected",
    [
        ("FOO", "WITHDRAWN"),
        ("Foo", "Withdrawn"),
        ("foo", "withdrawn"),
        ("fOO", "withdrawn"),
    ],
)
def test_case_matched_adjective(variant: str, expected: str) -> None:
    assert _case_matched_adjective(variant) == expected


# --- given-name exception rules -----------------------------------------------


def test_given_name_rules_consume_parenthetical_email_wholesale() -> None:
    rules = given_name_rules("Foo Bar")
    text = "permission from Foo (coach@example-fake-domain.test) covering reuse"
    result = apply_rules(text, rules)
    assert result == "permission from the third party covering reuse"
    # Mutation: dropping the email-shape requirement from the pattern (using
    # bare `Foo\s*\([^)]*\)` instead) would still pass this assertion, so
    # pin that the parenthetical content is inspected, not just its shape:
    assert "coach@example-fake-domain.test" not in result


def test_given_name_rules_do_not_fire_on_non_email_parenthetical() -> None:
    r"""Mutation C2: dropping the `@` requirement from the parenthetical
    email pattern (`rf"\b{name}\s*\([^)\n]*@[^)\n]*\)"` ->
    `rf"\b{name}\s*\([^)\n]*\)"`) still consumes the parenthetical
    wholesale, so `test_given_name_rules_consume_parenthetical_email_
    wholesale` above stays green under it -- that test's parenthetical
    happens to contain an email either way. Pinning on a parenthetical
    that is NOT email-shaped reds the mutation: the un-mutated pattern must
    leave it untouched entirely."""
    rules = given_name_rules("Foo Bar")
    text = "ask Foo (not an email) about the schedule"
    assert apply_rules(text, rules) == text


def test_given_name_rules_handle_bare_possessive() -> None:
    rules = given_name_rules("Foo Bar")
    result = apply_rules("this is not Foo's problem", rules)
    assert result == "this is not the third party's problem"


def test_given_name_rules_do_not_fire_on_the_ordinary_word_false_positive() -> None:
    """Mirrors the real trap: the given name is an ordinary English verb.
    Neither exception pattern is anchored on a bare word, so an imperative
    sentence using the same word is untouched."""
    rules = given_name_rules("Foo Bar")
    text = "- Foo the Banister and Minetti citations as superseded"
    assert apply_rules(text, rules) == text


def test_given_name_rules_derive_from_first_word_only() -> None:
    """Mutation: hard-coding `full_name.split()[1]` (the surname) instead of
    `[0]` would still compile and run, but would target the wrong word --
    caught here by using a full name whose two words are distinguishable."""
    rules = given_name_rules("Alpha Beta")
    assert apply_rules("Alpha's turn", rules) == "the third party's turn"
    assert apply_rules("Beta's turn", rules) == "Beta's turn"


# --- identity-leak email rule: denylist, not allowlist -------------------------
#
# Item (this fix): the original `identity_email_rule` took no arguments and
# redacted any email whose domain was not on a curated safe list -- an
# ALLOWLIST. That polarity ate every synthetic fixture address this test
# file itself plants (`coach@example-fake-domain.test`,
# `coach@not-a-safe-domain.test`, `real.user@Some-Real-Machine.local`,
# `fake@nope.test`), which only surfaced once this file was first committed
# to `HEAD` -- invariant 6 (the tip no-op, below) can only see a TRACKED
# blob. `identity_email_rule` is now a DENYLIST: `repo` and `tokens` are
# required so it can derive the specific addresses actually present from
# the corpus (`identity_leak_addresses`), never redacting anything merely
# because its domain looks unfamiliar.

_SYNTHETIC_TOKENS: tuple[str, ...] = ("Foo Bar", "Bar", "Foo Bar Corp", "FBC")


def test_identity_email_rule_redacts_address_whose_domain_carries_a_forbidden_token(
    tmp_path: Path,
) -> None:
    """Mirrors the real third-party leak: their contact address's domain is
    built from their own surname token (see `_token_domain_addresses`'s own
    docstring, never spelled out here). Here the synthetic surname-alone
    token `Bar` (`_SYNTHETIC_TOKENS`) is a substring of
    `coach@barcorp.test`'s domain.

    The blob is removed in a follow-up commit so the address lives in
    reachable history but NOT at the tip -- the real corpus's own shape
    after task 6.3 emptied the tip. A token-carrying address still present
    at the tip is a separate, guarded state
    (`test_identity_leak_addresses_raises_when_a_token_carrying_address_is_at_the_tip`
    below)."""
    repo = _init_repo(tmp_path)
    _commit_blob(repo, "contact.md", 'contact = "coach@barcorp.test"\n')
    _remove_blob(repo, "contact.md")

    rule = identity_email_rule(repo, _SYNTHETIC_TOKENS)
    text = 'contact = "coach@barcorp.test"'
    assert apply_rules(text, [rule]) == 'contact = "a redacted email address"'


def test_identity_email_rule_redacts_orphaned_commit_identity_address(
    tmp_path: Path,
) -> None:
    """Mirrors the real maintainer's-address / git-constructed-hostname
    leak: an address used as a commit's own author/committer identity that
    is present in the object database but reachable from NO live ref (the
    real corpus's reflog-only dangling commit, design.md
    `#### ContactRedaction`), while also appearing as ordinary text in a
    reachable blob (the same shape the real corpus's own design docs use,
    quoting/describing the dangling commit's identity).

    `notes.md` is removed in a follow-up commit, so the address is absent
    from the tip. That is both the realistic shape -- task 6.3 emptied the
    real tip -- and now a requirement: `identity_leak_addresses` RAISES on a
    confirmed (token-corroborated or orphan-derived) address that is still
    at the tip, which is what keeps its result tip-disjoint and therefore
    clone-independent. `..._raises_when_an_orphan_address_is_at_the_tip`
    below pins that raise.

    **What this test does NOT pin, stated because an earlier revision of
    this docstring claimed it did.** It is not a discriminating pin for the
    orphan term in `identity_leak_addresses`'s union, because after the two
    guards that term is redundant UP TO CASE: guard 1 forces
    `orphan <= token_domain | candidates` and guard 2 forces
    `orphan & tip == set()`, both compared case-folded, so every orphan
    address is already supplied by `token_domain` or by the tip-absent part
    of `candidates` -- possibly in a different casing.

    Re-measured after guard 1 became case-folded, because that edit changed
    this claim: restoring the orphan term now reds exactly one test,
    `..._guard_1_folds_case_when_corroborating`, where in the round that
    removed the term it reddened nothing. It remains true that no test here
    pins the term, and that removing it changed no redacted text (the rule
    is `(?i:...)`), but "provably inert" was the wrong strength and is not
    claimed any more.

    The orphan source is still load-bearing -- in guard 2 -- and this test
    still pins the end-to-end redaction of an orphan-derived identity, which
    is the behaviour the real corpus needs."""
    repo = _init_repo(tmp_path)
    _commit_blob(repo, "README.md", "an ordinary tip file with no address\n")
    _commit_blob(
        repo,
        "notes.md",
        "the dangling commit carried ghost@lost-machine.local in its headers\n",
    )
    _remove_blob(repo, "notes.md")
    (repo / "orphan.md").write_text("orphan content\n", encoding="utf-8")
    _git(repo, "add", "orphan.md")
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.email=ghost@lost-machine.local",
            "-c",
            "user.name=Ghost",
            "commit",
            "-m",
            "orphan commit",
        ],
        check=True,
        capture_output=True,
    )
    orphan_commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _git(repo, "reset", "--hard", "HEAD~1")
    _git(repo, "reflog", "expire", "--expire=now", "--all")
    # Falsity in the starting state: the orphan commit is genuinely
    # unreachable from any ref, but still present in the object database.
    assert (
        subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", orphan_commit],
            capture_output=True,
        ).returncode
        == 0
    )
    assert orphan_commit not in _reachable_ids(repo)

    from scripts.purge.replacements import (
        _orphaned_commit_identity_addresses,
        _reachable_identity_leak_candidates,
        _tip_tree_addresses,
    )

    # Reachability: the orphan-commit source genuinely names this address...
    assert "ghost@lost-machine.local" in _orphaned_commit_identity_addresses(repo)
    # ...it is corroborated by the blob-text scan, so guard 1 does not fire...
    assert "ghost@lost-machine.local" in _reachable_identity_leak_candidates(repo)
    # ...and it is genuinely absent from the tip, so guard 2 does not either.
    assert "ghost@lost-machine.local" not in _tip_tree_addresses(repo)
    assert _tip_tree_addresses(repo) == frozenset(), (
        "the tip must hold no address at all here, or the assertions above "
        "stop distinguishing the two guards"
    )

    rule = identity_email_rule(repo, _SYNTHETIC_TOKENS)
    text = "the dangling commit carried ghost@lost-machine.local in its headers"
    result = apply_rules(text, [rule])
    assert "ghost@lost-machine.local" not in result
    assert (
        result == "the dangling commit carried a redacted email address in its headers"
    )


def _reachable_ids(repo: Path) -> set[str]:
    listed = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    return set(listed)


def test_identity_email_rule_does_not_match_inside_a_longer_address(
    tmp_path: Path,
) -> None:
    """The identity rule must not fire on a denylisted address that is only
    a SUBSTRING of a longer, different address. Unanchored it did, in both
    directions, and the output is a mangled form -- which task 6.4's
    invariant 4 forbids outright, and which the one-shot rewrite would have
    produced against real history with no way to correct it:

        `<denylisted>.example`  ->  `a redacted email address.example`
        `pre<denylisted>`       ->  `prea redacted email address`

    Both are asserted below, because the fix has two independent halves (a
    lookbehind and a lookahead) and a test carrying only one direction
    leaves the other free to regress. The exact address is still redacted in
    the same assertion block, so this cannot pass by the rule having stopped
    matching altogether -- which is the failure mode a pure "leaves it
    alone" test would hide.

    Mutations, each measured: deleting the lookahead
    `(?![A-Za-z0-9.-])` reds the suffix assertion; deleting the lookbehind
    `(?<![A-Za-z0-9._%+-])` reds the prefix assertion."""
    repo = _init_repo(tmp_path)
    _commit_blob(repo, "contact.md", 'contact = "coach@barcorp.test"\n')
    _remove_blob(repo, "contact.md")

    rule = identity_email_rule(repo, _SYNTHETIC_TOKENS)

    # Falsity in the starting state: the rule genuinely does redact the
    # address on its own, so the two negatives below are about anchoring
    # rather than about an inert rule.
    assert apply_rules("write to coach@barcorp.test today", [rule]) == (
        "write to a redacted email address today"
    )

    suffix = "write to coach@barcorp.test.example today"
    assert apply_rules(suffix, [rule]) == suffix
    prefix = "write to notcoach@barcorp.test today"
    assert apply_rules(prefix, [rule]) == prefix


# --- the adjacency space, table-driven ---------------------------------------
#
# Four review rounds each found a real defect on an adjacency axis nobody had
# enumerated: the orphan term, letter case, substring containment, and then
# the lookbehind's character class and the lookahead's alphabet. Fixing them
# one at a time does not terminate. This table bounds the space instead.
#
# ONE RULE governs every cell, and the expectation is never hand-written:
#
#     redact exactly when the adjacent text cannot be part of a longer
#     `_EMAIL_SHAPE` token.
#
# `_EMAIL_SHAPE` is production's own definition of what an address is, so it
# is the ORACLE here -- `_email_shape_finds_whole_address` below asks it
# directly, exactly as a reviewer would, rather than reasoning about what the
# anchors ought to do. That makes this a comparison of two independent
# implementations (the rule's lookarounds vs the shape regex), not a
# restatement of one of them.
#
# If a future session finds "another adjacency case", either it is already a
# row here, or `test_identity_rule_adjacency_table_is_complete` is failing and
# says which class is missing. There are no deliberate exceptions: the anchors
# and the oracle agree on every cell.

_ADJACENCY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("line-start", ""),
    ("space", " "),
    ("newline", "\n"),
    ("letter", "x"),
    ("upper-letter", "X"),
    ("digit", "7"),
    ("dot", "x."),
    ("underscore", "x_"),
    ("percent", "x%"),
    ("plus", "x+"),
    ("hyphen", "x-"),
    ("bare-dot", "."),
    ("bare-underscore", "_"),
    ("bare-percent", "%"),
    ("bare-plus", "+"),
    ("bare-hyphen", "-"),
    ("angle-open", "<"),
    ("paren-open", "("),
    ("bracket-open", "["),
    ("double-quote", '"'),
    ("single-quote", "'"),
    ("comma", ","),
    ("semicolon", ";"),
    ("colon", ":"),
    ("at-sign", "x@"),
)
"""Every character class `_EMAIL_SHAPE`'s LOCAL-PART half uses
(`A-Za-z`, `0-9`, `.`, `_`, `%`, `+`, `-`), each both after a letter and
bare, plus line start, whitespace, and the punctuation an address is
conventionally wrapped in.

The bare forms are not redundant with the `x`-prefixed ones: a mutation
narrowing the lookbehind from `[A-Za-z0-9._%+-]` to `[A-Za-z0-9]` survives a
table containing only alphanumeric predecessors, because `not<addr>` is
blocked either way. `x.<addr>` is what distinguishes them, and it is a real
mangling (`mail x.<addr> here` -> `mail x.a redacted email address here`)."""

_ADJACENCY_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("line-end", ""),
    ("space", " "),
    ("newline", "\n"),
    ("letter", "x"),
    ("upper-letter", "X"),
    ("digit", "7"),
    ("dot-then-end", "."),
    ("dot-then-space", ". "),
    ("dot-then-newline", ".\n"),
    ("dot-then-paren", ".)"),
    ("dot-then-letters", ".example"),
    ("dot-then-digit", ".7"),
    ("dot-digit-dot-letters", ".7.example"),
    ("digit-dot-letters", "7.example"),
    ("underscore", "_"),
    ("percent", "%"),
    ("plus", "+"),
    ("hyphen", "-"),
    ("hyphen-word", "-based"),
    ("hyphen-word-dot-letters", "-based.example"),
    ("double-dot", ".."),
    ("angle-close", ">"),
    ("paren-close", ")"),
    ("bracket-close", "]"),
    ("double-quote", '"'),
    ("comma", ","),
    ("semicolon", ";"),
    ("colon", ":"),
)
"""Every character class `_EMAIL_SHAPE`'s DOMAIN half uses (`A-Za-z`, `0-9`,
`.`, `-`), the local-part-only characters too (`_`, `%`, `+`, which cannot
extend a domain and must therefore NOT suppress), line end, whitespace,
closing punctuation, and the multi-character shapes where one trailing
character is not enough to decide: `.example` extends the address and `.` at
a sentence end does not; `7` alone does not extend it but `7.example` does."""


@pytest.fixture(scope="module")
def _adjacency_rule(tmp_path_factory: pytest.TempPathFactory) -> ReplacementRule:
    """The identity rule for one synthetic denylisted address, built once."""
    repo = _init_repo(tmp_path_factory.mktemp("adjacency"))
    _commit_blob(repo, "contact.md", 'contact = "coach@barcorp.test"\n')
    _remove_blob(repo, "contact.md")
    return identity_email_rule(repo, _SYNTHETIC_TOKENS)


def _email_shape_finds_whole_address(text: str, address: str) -> bool:
    """The ORACLE: does production's own `_EMAIL_SHAPE` find `address` in
    `text` as a COMPLETE match, rather than as part of a longer address?

    `_EMAIL_SHAPE` is imported from `scripts.purge.replacements`, never
    re-spelled here -- a copy would drift from the thing it is meant to
    check, and the whole value of this oracle is that it is the same object
    production reasons with."""
    from scripts.purge.replacements import _EMAIL_SHAPE

    lowered = address.lower()
    return any(m.group(0).lower() == lowered for m in _EMAIL_SHAPE.finditer(text))


@pytest.mark.parametrize(
    "suffix_id,suffix", _ADJACENCY_SUFFIXES, ids=[i for i, _ in _ADJACENCY_SUFFIXES]
)
@pytest.mark.parametrize(
    "prefix_id,prefix", _ADJACENCY_PREFIXES, ids=[i for i, _ in _ADJACENCY_PREFIXES]
)
def test_identity_rule_adjacency_matches_email_shape(
    _adjacency_rule: ReplacementRule,
    prefix_id: str,
    prefix: str,
    suffix_id: str,
    suffix: str,
) -> None:
    r"""The rule redacts a cell exactly when `_EMAIL_SHAPE` says the bare
    address is present as a complete token, over the full product of prefix
    and suffix contexts (700 cells).

    Both failure directions are caught here, and both are real:
    over-matching produces the mangled forms invariant 4 forbids;
    under-matching leaves a real identity in reachable history, which is the
    worse of the two.

    Mutations, each measured against this table on the current tree, with
    the cell count each reds:

    - narrowing the lookbehind to `[A-Za-z0-9]` -> 220 cells, the
      `bare-dot`/`bare-underscore`/`bare-percent`/`bare-plus`/`bare-hyphen`
      and `x.`-style prefix rows. **This mutation survived the entire suite
      before this table existed**, and the blob it mangles is
      `mail x.<addr> here`;
    - deleting `(?![A-Za-z])` -> 24 cells, the `letter`/`upper-letter`
      suffix rows;
    - deleting `(?![A-Za-z0-9.-]*\.[A-Za-z]{2,})` -> 49 failures: 48 cells,
      the `dot-then-letters` family, plus the counterexample test above;
    - restoring the earlier `(?![A-Za-z0-9.-])` lookahead -> 108 cells, the
      sentence-final `dot-then-*`, `digit` and `hyphen` rows -- i.e. exactly
      the under-redactions that anchor caused;
    - removing all anchors -> 437 failures: 436 cells, plus that same
      counterexample test."""
    address = "coach@barcorp.test"
    text = f"{prefix}{address}{suffix}"
    expected_redaction = _email_shape_finds_whole_address(text, address)

    result = apply_rules(text, [_adjacency_rule])

    if expected_redaction:
        assert result != text, (
            f"UNDER-redaction at prefix={prefix_id!r} suffix={suffix_id!r}: "
            "_EMAIL_SHAPE finds the bare address as a complete token here, "
            "so a real identity would survive the rewrite"
        )
        assert address not in result
        assert "a redacted email address" in result
    else:
        assert result == text, (
            f"OVER-redaction at prefix={prefix_id!r} suffix={suffix_id!r}: "
            "the address here is only part of a longer address, so "
            "redacting it produces a mangled form (invariant 4)"
        )


def test_identity_rule_adjacency_table_is_complete() -> None:
    """The completeness half, and the positive control for the table above.

    Three things a green parametrised table cannot tell you on its own:
    that it covers the classes it claims to, that both outcomes actually
    occur in it (a table that is all-redact or all-leave pins only one
    branch), and that the oracle is not simply always agreeing because it is
    always returning the same answer."""
    prefixes = {value for _id, value in _ADJACENCY_PREFIXES}
    suffixes = {value for _id, value in _ADJACENCY_SUFFIXES}

    # Every character class `_EMAIL_SHAPE` uses appears on both sides.
    for character in "xX7._%+-":
        assert any(character in value for value in prefixes), character
    for character in "xX7.-":
        assert any(character in value for value in suffixes), character
    # ...including bare (non-alphanumeric-led) prefixes, without which a
    # narrowed lookbehind survives.
    assert {".", "_", "%", "+", "-"} <= prefixes

    address = "coach@barcorp.test"
    outcomes = {
        _email_shape_finds_whole_address(f"{p}{address}{s}", address)
        for p in prefixes
        for s in suffixes
    }
    assert outcomes == {True, False}, (
        "the oracle must say BOTH redact and leave-alone across this table; "
        f"got only {outcomes} -- every cell is pinning the same branch"
    )
    assert len(prefixes) * len(suffixes) >= 600


def test_identity_email_rule_leaves_an_arbitrary_unknown_domain_address_untouched(
    tmp_path: Path,
) -> None:
    """The polarity pin. `coach@barcorp.test` (token-domain leak) and
    `ghost@lost-machine.local` (orphaned-commit-identity leak) ARE
    redacted; `someone@totally-unrelated-domain.test` -- shaped exactly the
    same, on a domain that is neither -- is NOT. Reverting
    `identity_email_rule` to allowlist polarity (redact anything not on a
    curated safe list) reds this: an unrelated, unlisted domain would then
    be treated as unsafe and redacted too."""
    repo = _init_repo(tmp_path)
    _commit_blob(repo, "contact.md", 'contact = "coach@barcorp.test"\n')
    _remove_blob(repo, "contact.md")
    _commit_blob(
        repo,
        "notes.md",
        "the dangling commit carried ghost@lost-machine.local in its headers\n",
    )
    # Both confirmed addresses must be off the tip, or guard 2 raises before
    # this test reaches the polarity it is here to measure.
    _remove_blob(repo, "notes.md")
    (repo / "orphan.md").write_text("orphan\n", encoding="utf-8")
    _git(repo, "add", "orphan.md")
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.email=ghost@lost-machine.local",
            "-c",
            "user.name=Ghost",
            "commit",
            "-m",
            "orphan commit",
        ],
        check=True,
        capture_output=True,
    )
    _git(repo, "reset", "--hard", "HEAD~1")
    _git(repo, "reflog", "expire", "--expire=now", "--all")

    rule = identity_email_rule(repo, _SYNTHETIC_TOKENS)

    real_leaks = 'contact = "coach@barcorp.test"', "seen: ghost@lost-machine.local"
    for text in real_leaks:
        assert "a redacted email address" in apply_rules(text, [rule]), text

    unrelated = "seen once: someone@totally-unrelated-domain.test"
    assert apply_rules(unrelated, [rule]) == unrelated


# --- the reachability defect: a genuinely pruned object database -------------
#
# `_orphaned_commit_identity_addresses` depends on unreachable commit objects
# still being physically present. Every OTHER orphan-commit test in this file
# stops at `reflog expire --expire=now --all`, which leaves the object
# present (an unreachable commit is not the same thing as a pruned one --
# `_iter_all_local_objects`'s own corrected docstring names the distinction).
# `_prune_unreachable` below additionally runs `git gc --prune=now`, which is
# what a real `git clone --no-local` (tasks.md 7.2's own prescribed clone) or
# an aged `git gc --auto` produces: the unreachable commit object is gone from
# the database entirely, not merely unreachable from a ref.
#
# The FIRST remediation of that defect made the orphan source the AUTHORITY
# and raised whenever the reachability-independent blob-text scan named an
# address the orphan diff could not corroborate. That guard is unsatisfiable:
# no fresh clone carries unreachable objects at all, so it raised
# unconditionally and red nine acceptance tests. The polarity is now
# inverted -- the two reachability-independent sources (token-domain match and
# blob-text candidate scan) are the contributing sources, the orphan source
# checks rather than contributes, and
# what separates a real leak from this suite's own synthetic fixtures is
# TIP-ABSENCE rather than a `tests/` path prefix.


def _prune_unreachable(repo: Path) -> None:
    """`reflog expire --expire=now --all` + `gc --prune=now`.

    Only ever called on a repository this module created with `git init`
    under `tmp_path`. Never on a clone and never on a worktree: a
    same-filesystem clone hardlinks its source's object directory and a
    linked worktree's `.git` is a pointer file, so in both cases these
    commands reach objects that are not the caller's to destroy."""
    _git(repo, "reflog", "expire", "--expire=now", "--all")
    _git(repo, "gc", "--prune=now")


def _make_orphan_commit(repo: Path, name: str, identity: str) -> str:
    """Commit `name` under author/committer `identity`, then reset it away,
    returning the now-unreachable commit id."""
    (repo / name).write_text("orphan content\n", encoding="utf-8")
    _git(repo, "add", name)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            f"user.email={identity}",
            "-c",
            "user.name=Ghost",
            "commit",
            "-m",
            "orphan commit",
        ],
        check=True,
        capture_output=True,
    )
    orphan_commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _git(repo, "reset", "--hard", "HEAD~1")
    return orphan_commit


def test_identity_leak_addresses_survives_a_genuinely_pruned_repository(
    tmp_path: Path,
) -> None:
    """The regression pin for the blocker this remediation clears. The
    unreachable commit object is GONE, so `_orphaned_commit_identity_
    addresses` returns `()` -- and the derivation must still name the leaked
    address, from the reachability-independent blob-text scan alone, without
    raising.

    Mutation: restoring the old polarity (`raise if candidates -
    token_domain - orphan`) reds this test -- that expression is exactly this
    repository's state. The old test asserted `pytest.raises` here; a fresh
    clone and this working repository both look like this, so the old guard
    could never be satisfied by any repository the rewrite actually runs
    against."""
    repo = _init_repo(tmp_path)
    _commit_blob(
        repo,
        "notes.md",
        "the dangling commit carried ghost@pruned-machine.local in its headers\n",
    )
    # Removed at the tip: this is the leak branch, not the sanctioned branch.
    _remove_blob(repo, "notes.md")
    orphan_commit = _make_orphan_commit(repo, "orphan.md", "ghost@pruned-machine.local")
    _prune_unreachable(repo)

    from scripts.purge.replacements import (
        _orphaned_commit_identity_addresses,
        _reachable_identity_leak_candidates,
        _tip_tree_addresses,
        identity_leak_addresses,
    )

    # Falsity in the starting state: the orphan commit is now genuinely GONE
    # from the object database, not merely unreachable -- this is what
    # distinguishes this fixture from every other orphan-commit test above.
    assert (
        subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", orphan_commit],
            capture_output=True,
        ).returncode
        != 0
    )
    # Reachability: the reachability-DEPENDENT source is genuinely empty...
    assert _orphaned_commit_identity_addresses(repo) == ()
    # ...the reachability-INDEPENDENT source genuinely finds the address...
    assert "ghost@pruned-machine.local" in _reachable_identity_leak_candidates(repo)
    # ...and the tip genuinely does not hold it, so the partition classifies
    # it as a leak rather than sanctioning it.
    assert "ghost@pruned-machine.local" not in _tip_tree_addresses(repo)

    assert identity_leak_addresses(repo, _SYNTHETIC_TOKENS) == (
        "ghost@pruned-machine.local",
    )


def test_identity_leak_addresses_raises_when_the_orphan_source_names_an_unseen_address(
    tmp_path: Path,
) -> None:
    """The FIRST of the two genuine inconsistencies. The orphan-commit source
    names an identity that neither reachability-independent source found
    anywhere -- so a clone, which has no unreachable objects to read, would
    silently drop it. That is the original defect's real shape and must halt.

    Note what is deliberately NOT here: no blob anywhere quotes this
    identity. In the real corpus both orphan-derived addresses DO also appear
    in reachable blob text (measured), which is why this condition is
    vacuously satisfied there and by every fresh clone.

    Mutation: replacing the `unseen` guard's body with `pass` reds this test
    and nothing else."""
    repo = _init_repo(tmp_path)
    _commit_blob(repo, "notes.md", "nothing quotes the orphan identity here\n")
    _make_orphan_commit(repo, "orphan.md", "ghost@unseen-machine.local")
    _git(repo, "reflog", "expire", "--expire=now", "--all")

    from scripts.purge.replacements import (
        _orphaned_commit_identity_addresses,
        _reachable_identity_leak_candidates,
        _token_domain_addresses,
        identity_leak_addresses,
    )

    # Reachability: the orphan source really does name it, and neither
    # reachability-independent source does -- the scenario is live.
    assert _orphaned_commit_identity_addresses(repo) == ("ghost@unseen-machine.local",)
    assert _reachable_identity_leak_candidates(repo) == ()
    assert _token_domain_addresses(repo, _SYNTHETIC_TOKENS) == ()

    with pytest.raises(ValueError, match="commit-identity diff") as excinfo:
        identity_leak_addresses(repo, _SYNTHETIC_TOKENS)

    # The diagnostic names the address by masked SHA-256 tag, never by
    # value: an error message saying which identity leaked is exactly the
    # shape that leaks it again, and this one lands in pytest output, CI
    # logs and review reports. Mutation: `_masked_address` returning its
    # argument unchanged reds both assertions.
    message = str(excinfo.value)
    assert "ghost@unseen-machine.local" not in message
    assert _masked("ghost@unseen-machine.local") in message


def test_identity_leak_addresses_guard_1_folds_case_when_corroborating(
    tmp_path: Path,
) -> None:
    """Guard 1 asks whether the reachability-independent sources found the
    orphan-named address ANYWHERE, and it asks case-insensitively -- the
    same comparison semantics guard 2 uses.

    Without folding, an orphan identity recorded as `Ghost@Machine.local`
    whose only blob-text appearance is the lower-case rendering would raise
    with a message saying neither source "found it anywhere in reachable
    blob text", which would simply be false: the address was found, in a
    different casing. A false diagnostic on a halting path is worse than a
    silent one, because it sends the reader looking for a leak that is not
    there.

    Mutation: reverting `unseen` to the exact-string
    `orphan - token_domain - candidates` reds this test and nothing else."""
    repo = _init_repo(tmp_path)
    _commit_blob(repo, "notes.md", "seen in history: ghost@machine.local\n")
    _remove_blob(repo, "notes.md")
    _make_orphan_commit(repo, "orphan.md", "Ghost@Machine.local")
    _git(repo, "reflog", "expire", "--expire=now", "--all")

    from scripts.purge.replacements import (
        _orphaned_commit_identity_addresses,
        _reachable_identity_leak_candidates,
        identity_leak_addresses,
    )

    # Reachability: the two sources genuinely disagree on CASE and only on
    # case -- an exact-string guard 1 would therefore genuinely fire here.
    assert _orphaned_commit_identity_addresses(repo) == ("Ghost@Machine.local",)
    candidates = set(_reachable_identity_leak_candidates(repo))
    assert "ghost@machine.local" in candidates
    assert "Ghost@Machine.local" not in candidates

    assert identity_leak_addresses(repo, _SYNTHETIC_TOKENS) == ("ghost@machine.local",)


def test_identity_leak_addresses_raises_when_a_token_carrying_address_is_at_the_tip(
    tmp_path: Path,
) -> None:
    """The SECOND genuine inconsistency. A token-corroborated address is
    still present in the tip tree, so the tip holds a forbidden value --
    contradicting task 6.3 (which emptied it) and the three standing guards
    that keep it empty, and with them this derivation's whole tip-absence
    sanctioning rule.

    Contrast with `test_identity_email_rule_redacts_address_whose_domain_
    carries_a_forbidden_token` above, whose fixture is byte-identical except
    that it removes the blob in a follow-up commit: the only varied dimension
    is tip-presence.

    Mutation: replacing guard 2's body (`if confirmed_at_tip:`) with `pass`
    reds this test AND its orphan-source sibling
    `..._raises_when_an_orphan_address_is_at_the_tip` -- 2 red, measured, not
    a sole failure, because one guard now covers both confirming sources.
    The mutation that isolates THIS test is narrowing guard 2 the other way,
    to `orphan & tip`; the sibling's own docstring records the mirror-image
    narrowing, and that one IS a sole failure."""
    repo = _init_repo(tmp_path)
    _commit_blob(repo, "contact.md", 'contact = "coach@barcorp.test"\n')

    from scripts.purge.replacements import (
        _tip_tree_addresses,
        _token_domain_addresses,
        identity_leak_addresses,
    )

    # Reachability: the token-domain source really does name it, and the tip
    # really does still hold it.
    assert _token_domain_addresses(repo, _SYNTHETIC_TOKENS) == ("coach@barcorp.test",)
    assert "coach@barcorp.test" in _tip_tree_addresses(repo)

    with pytest.raises(ValueError, match="tip tree") as excinfo:
        identity_leak_addresses(repo, _SYNTHETIC_TOKENS)

    # Masked, for the same reason as the sibling raise-path test above.
    message = str(excinfo.value)
    assert "coach@barcorp.test" not in message
    assert _masked("coach@barcorp.test") in message


def test_identity_leak_addresses_raises_when_an_orphan_address_is_at_the_tip(
    tmp_path: Path,
) -> None:
    """Guard 2 covers BOTH confirming sources, not only the token-domain
    one. An address that some unreachable commit carries as its own
    author/committer identity is a real leaked identity by construction, so
    the tip still holding it is the same task 6.3 contradiction as a
    token-carrying address at the tip, and must halt for the same reason.

    It is also the one place the un-partitioned confirming sources could
    make the result CLONE-DEPENDENT, which is what this whole task exists to
    remove: in a repository that still holds unreachable objects this
    address is confirmed and denylisted, while in a clone that does not the
    orphan source goes empty, the same address is merely a tip-present
    candidate, and it is sanctioned away -- two different denylists from the
    same history, silently. Halting is what forecloses that.

    Contrast with `test_identity_email_rule_redacts_orphaned_commit_
    identity_address` above, whose fixture is identical except that it
    removes `notes.md` in a follow-up commit: the only varied dimension is
    tip-presence.

    Mutation: narrowing guard 2 back to `token_domain & tip` reds this test
    and nothing else."""
    repo = _init_repo(tmp_path)
    # Left AT the tip, deliberately -- this is the state under test.
    _commit_blob(
        repo,
        "notes.md",
        "the dangling commit carried ghost@lost-machine.local in its headers\n",
    )
    _make_orphan_commit(repo, "orphan.md", "ghost@lost-machine.local")
    _git(repo, "reflog", "expire", "--expire=now", "--all")

    from scripts.purge.replacements import (
        _orphaned_commit_identity_addresses,
        _tip_tree_addresses,
        _token_domain_addresses,
        identity_leak_addresses,
    )

    # Reachability: the orphan source really does name it, the tip really
    # does still hold it, and -- this is what makes the test discriminate
    # between guard 2's two halves -- the token-domain source does NOT name
    # it, so the narrowed guard would let it through.
    assert _orphaned_commit_identity_addresses(repo) == ("ghost@lost-machine.local",)
    assert "ghost@lost-machine.local" in _tip_tree_addresses(repo)
    assert _token_domain_addresses(repo, _SYNTHETIC_TOKENS) == ()

    with pytest.raises(ValueError, match="tip tree") as excinfo:
        identity_leak_addresses(repo, _SYNTHETIC_TOKENS)

    message = str(excinfo.value)
    assert "ghost@lost-machine.local" not in message
    assert _masked("ghost@lost-machine.local") in message


def test_identity_leak_addresses_partitions_candidates_by_tip_presence(
    tmp_path: Path,
) -> None:
    """The partition itself, with both branches live in one repository and
    two pairwise-distinct addresses so neither can stand in for the other.

    `sanctioned@kept-at-tip.local` survives to the tip -- the shape of this
    suite's own synthetic fixtures, and of every documented example the tip
    carries; `leaked@dropped-before-tip.local` exists only in history. Both
    are candidates (asserted below, so this does not silently pin an empty
    scan). Only the second is a leak.

    Mutation: dropping the `_absent_from_tip` filter from
    `identity_leak_addresses`'s union reds
    this test."""
    repo = _init_repo(tmp_path)
    _commit_blob(repo, "history.md", "old note: leaked@dropped-before-tip.local\n")
    _remove_blob(repo, "history.md")
    _commit_blob(repo, "fixtures.md", "fixture: sanctioned@kept-at-tip.local\n")

    from scripts.purge.replacements import (
        _reachable_identity_leak_candidates,
        _tip_tree_addresses,
        identity_leak_addresses,
    )

    # Reachability: BOTH addresses are candidates -- the partition is what
    # separates them, not the scan.
    assert set(_reachable_identity_leak_candidates(repo)) == {
        "leaked@dropped-before-tip.local",
        "sanctioned@kept-at-tip.local",
    }
    tip = _tip_tree_addresses(repo)
    assert "sanctioned@kept-at-tip.local" in tip
    assert "leaked@dropped-before-tip.local" not in tip

    assert identity_leak_addresses(repo, _SYNTHETIC_TOKENS) == (
        "leaked@dropped-before-tip.local",
    )


def test_identity_leak_addresses_folds_case_when_sanctioning_against_the_tip(
    tmp_path: Path,
) -> None:
    """The tip comparison folds case, and it has to.

    `identity_email_rule` emits its address alternation under `(?i:...)`, so
    a rule built from `fixture@kept-at-tip.local` also matches
    `Fixture@Kept-At-Tip.local`. If the tip comparison were exact-string,
    the lower-case rendering (present only in history) would be classified a
    leak while the mixed-case rendering sitting AT the tip would be rewritten
    by the resulting rule -- the identity rule changing a tip blob, which is
    exactly what `identity_leak_addresses` claims by construction it cannot
    do.

    The two renderings differ ONLY by case, which is the single varied
    dimension: everything else about them is identical, so nothing but the
    folding can separate the outcomes.

    Mutation: reverting `_at_tip` to an exact-string `addresses & tip` reds
    this test and nothing else."""
    repo = _init_repo(tmp_path)
    _commit_blob(repo, "history.md", "old note: fixture@kept-at-tip.local\n")
    _remove_blob(repo, "history.md")
    _commit_blob(repo, "fixtures.md", "fixture: Fixture@Kept-At-Tip.local\n")

    from scripts.purge.replacements import (
        _reachable_identity_leak_candidates,
        _tip_tree_addresses,
        identity_leak_addresses,
    )

    # Reachability: the lower-case rendering IS a candidate, and the tip
    # holds ONLY the mixed-case one -- so an exact-string comparison would
    # genuinely fail to sanction it. Without this the test pins nothing.
    candidates = set(_reachable_identity_leak_candidates(repo))
    assert "fixture@kept-at-tip.local" in candidates
    tip = _tip_tree_addresses(repo)
    assert "Fixture@Kept-At-Tip.local" in tip
    assert "fixture@kept-at-tip.local" not in tip

    assert identity_leak_addresses(repo, _SYNTHETIC_TOKENS) == ()


def test_identity_leak_addresses_uses_tip_absence_not_a_tests_path_prefix(
    tmp_path: Path,
) -> None:
    """Two addresses that the retired `tests/` path-prefix scope and the
    tip-absence rule classify differently, so the fixture separates the two
    mechanisms rather than merely exercising one.

    - `probe@under-tests.local` lives only under `tests/` and only in
      history. The old prefix scope excluded `tests/` outright, so it would
      never have been a candidate at all; tip-absence makes it a leak, which
      it is. **This is the direction restoring the prefix scope reds.**
      Re-measured on the current tree: that mutation reds 2 -- this test,
      and `test_identity_denylist_is_exactly_the_leaks_the_tip_does_not_hold`,
      whose `len(sanctioned) >= 5` bound also fires because the mutation
      drops the real corpus's sanctioned population from 5 to 4. It is not a
      sole failure. (It was one when first measured, before that bound was
      tightened from 4 to 5 -- which is why this sentence was re-measured
      rather than carried forward.)
    - `probe@outside-tests.local` lives at a non-`tests/` path and survives
      to the tip. This one is NOT pinned by restoring the prefix scope:
      under that mutation it is still a candidate, and tip-absence still
      sanctions it, so the result is unchanged and the mutation stays green
      on this half. It is pinned instead by dropping `_absent_from_tip` from
      the union -- the same mutation
      `..._partitions_candidates_by_tip_presence` names. Stated precisely
      because an earlier revision of this docstring claimed the prefix-scope
      mutation reddened both directions; it reddens one, and the claim was
      about the wholesale pre-remediation design rather than about the
      mutation the sentence attached to.

    The reason the prefix scope had to go at all: an earlier revision of
    `_reachable_identity_leak_candidates`'s own docstring quoted this
    suite's fixtures by value at a `scripts/` path, so the scope excluded
    the fixtures' real home and admitted the prose copy describing them --
    three false candidates, self-inflicted."""
    repo = _init_repo(tmp_path)
    (repo / "tests").mkdir()
    _commit_blob(
        repo, "tests/fixture_notes.md", "fixture address: probe@under-tests.local\n"
    )
    _remove_blob(repo, "tests/fixture_notes.md")
    (repo / "docs").mkdir()
    _commit_blob(repo, "docs/notes.md", "documented shape: probe@outside-tests.local\n")

    from scripts.purge.replacements import (
        _reachable_identity_leak_candidates,
        identity_leak_addresses,
    )

    # Reachability: the `tests/`-only address IS scanned now. Under the old
    # prefix scope this assertion alone was false.
    assert "probe@under-tests.local" in _reachable_identity_leak_candidates(repo)

    assert identity_leak_addresses(repo, _SYNTHETIC_TOKENS) == (
        "probe@under-tests.local",
    )


def test_identity_leak_addresses_does_not_raise_when_nothing_is_found() -> None:
    """The negative control for the raise-path tests above: an ordinary
    synthetic repository with no `.local` address, no rewrite-map-arrow text
    and no orphan commit anywhere carries no evidence for any source to
    find, so nothing is inconsistent and `identity_leak_addresses` returns
    cleanly -- this is what keeps every OTHER mechanics test in this file
    (all built on freshly initialised, never-orphaned repositories) green
    without each one needing to plant an orphan commit of its own.

    An empty union is explicitly NOT an error: `identity_email_rule` handles
    it with `_NEVER_MATCHES`."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo = _init_repo(tmp_path)
        _commit_blob(repo, "a.md", "nothing interesting here at all\n")
        from scripts.purge.replacements import identity_leak_addresses

        assert identity_leak_addresses(repo, _SYNTHETIC_TOKENS) == ()


# --- per-token tier ordering: the definite/indefinite/sentence/general/mopup --


def _rules_for_synthetic_third_party() -> tuple[ReplacementRule, ...]:
    from scripts.purge.replacements import _token_tier_rules

    return _token_tier_rules("Bar", "third_party", "surname alone (synthetic)")


def _rules_for_synthetic_methodology() -> tuple[ReplacementRule, ...]:
    from scripts.purge.replacements import _token_tier_rules

    return _token_tier_rules("FBC", "withdrawn_methodology", "abbreviation (synthetic)")


def test_definite_article_guard_avoids_the_the() -> None:
    rules = _rules_for_synthetic_third_party()
    assert apply_rules("the Bar calculator", rules) == "the third party calculator"
    assert apply_rules("The Bar calculator", rules) == "The third party calculator"
    # Mutation: deleting the definite-article guard tier (leaving only
    # general) reds this -- "the Bar" would become "the the third party".
    assert "the the" not in apply_rules("the Bar calculator", rules)


def test_definite_article_guard_survives_a_line_wrap() -> None:
    """Root-cause regression. A fixed-width lookbehind (`(?<=\\bthe\\s)`)
    only ever asserts exactly one whitespace character, so real wrapped
    prose ("the\\n  Bar") fell through the old tier (a) entirely and was
    caught by the general tier instead, producing "the\\n  the third
    party" -- the real "the the" mangled form a real `git filter-repo` run
    measured 6 times in the rewritten repository (e.g.
    `docs/ownership-contract.md`: "...tested max heart rate, the\\n
    <Surname> performance level..."). Constructs that exact wrapped shape
    against the synthetic token."""
    rules = _rules_for_synthetic_third_party()
    text = "tested max heart rate, the\n  Bar performance level"
    result = apply_rules(text, rules)
    assert result == "tested max heart rate, the third party performance level"
    assert "the the" not in result


def test_indefinite_article_guard_normalises_an_to_a() -> None:
    rules = _rules_for_synthetic_methodology()
    assert apply_rules("an FBC result", rules) == "a withdrawn result"
    assert apply_rules("An FBC result", rules) == "A withdrawn result"
    assert apply_rules("a FBC result", rules) == "a withdrawn result"
    assert apply_rules("A FBC result", rules) == "A withdrawn result"
    # Mutation: skipping article normalisation (emitting "an withdrawn")
    # reds this -- the named mangled form.
    assert "an withdrawn" not in apply_rules("an FBC result", rules)
    assert "An withdrawn" not in apply_rules("An FBC result", rules)


def test_sentence_start_guard_preserves_capital() -> None:
    rules = _rules_for_synthetic_third_party()
    text = "Prior sentence ends. Bar stays registered and healthy"
    result = apply_rules(text, rules)
    assert result == "Prior sentence ends. The third party stays registered and healthy"
    # Mutation: dropping the sentence-start tier reds this -- general alone
    # lowercases "Bar" into "the third party" at a true sentence start.
    assert "ends. the third party" not in result


def test_sentence_start_guard_survives_a_paragraph_break() -> None:
    """Root-cause regression, sentence-start-guard half. `(?<=[.!?]\\s)` is
    also fixed-width, so a paragraph break between the sentence-ending
    punctuation and the token ("gate.\\n\\nBar stays...") fell through the
    old tier (c) and was lowercased by the general tier -- a real, measured
    site: `.kiro/specs/threshold-load/brief.md` ("...cleared its
    sufficiency gate.\\n\\n<Surname> stays registered..."). Constructs that
    exact wrapped shape against the synthetic token."""
    rules = _rules_for_synthetic_third_party()
    text = "cleared its sufficiency gate.\n\nBar stays registered"
    result = apply_rules(text, rules)
    assert result == "cleared its sufficiency gate.\n\nThe third party stays registered"
    assert "gate.\n\nthe third party" not in result


def test_sentence_start_guard_covers_start_of_blob() -> None:
    rules = _rules_for_synthetic_third_party()
    assert (
        apply_rules("Bar stays registered", rules) == "The third party stays registered"
    )


def test_definite_article_guard_does_not_double_a_trailing_methodology_word() -> None:
    """Item 7's root cause: `bare`/`cap`/`lower` for the withdrawn_methodology
    family are themselves the two-word phrase "withdrawn methodology" /
    "The withdrawn methodology". Replacing only the token in "the FBC
    methodology" and leaving the source's own following "methodology" word
    in place produces "the withdrawn methodology methodology" -- measured
    in 6 blobs + 1 commit message of the rewritten repository. The
    trailing-word consumption must fire regardless of which tier (article,
    sentence-start, or general) handles the surrounding context."""
    rules = _rules_for_synthetic_methodology()

    mid_sentence = apply_rules("the FBC methodology was retired", rules)
    assert mid_sentence == "the withdrawn methodology was retired"
    assert "methodology methodology" not in mid_sentence

    sentence_start = apply_rules(
        "Prior sentence ends. FBC methodology stays retired", rules
    )
    assert sentence_start == (
        "Prior sentence ends. The withdrawn methodology stays retired"
    )
    assert "methodology methodology" not in sentence_start

    blob_start = apply_rules("FBC methodology stays retired", rules)
    assert blob_start == "The withdrawn methodology stays retired"
    assert "methodology methodology" not in blob_start

    general = apply_rules("we discussed FBC methodology today", rules)
    assert general == "we discussed the withdrawn methodology today"
    assert "methodology methodology" not in general

    # The indefinite-article guard was never broken (the bare adjective
    # composes correctly with a literal following "methodology" as
    # adjective + noun) -- pinned so a regression there is caught too.
    indefinite = apply_rules("an FBC methodology was retired", rules)
    assert indefinite == "a withdrawn methodology was retired"
    assert "methodology methodology" not in indefinite


def test_general_tier_lowercases_mid_sentence() -> None:
    rules = _rules_for_synthetic_third_party()
    assert apply_rules("we discussed Bar today", rules) == (
        "we discussed the third party today"
    )


def test_identifier_mopup_produces_valid_identifier_forms() -> None:
    """Realistic Python-constant convention upper-cases whatever word it
    embeds regardless of the word's natural title-casing (measured in the
    real corpus: the surname's title-case form has a separate all-caps case
    variant embedded inside an all-caps module constant) -- so the mop-up is
    exercised through the "BAR" (all-caps) case variant's
    own tier rules, matching what `build_rules` would generate for that
    observed variant, not the "Bar" (title-case) variant's."""
    from scripts.purge.replacements import _token_tier_rules

    upper_rules = _token_tier_rules("BAR", "third_party", "surname alone (synthetic)")
    assert apply_rules("_BAR_TABLE_VALUES", upper_rules) == "_WITHDRAWN_TABLE_VALUES"

    title_rules = _rules_for_synthetic_third_party()
    assert apply_rules("BarCalculator", title_rules) == "WithdrawnCalculator"

    lower_rules = _token_tier_rules("bar", "third_party", "surname alone (synthetic)")
    assert apply_rules('_bar_id = "bar"', lower_rules) == (
        '_withdrawn_id = "the third party"'
    )
    # the quoted "bar" is boundary-guarded content, not embedded in an
    # identifier, so the general tier (not the mop-up) reaches it -- pinned
    # by the full-sentence-shaped replacement above rather than "withdrawn".


def test_identifier_mopup_is_unreachable_by_word_boundary_alone() -> None:
    """Mutation: dropping tier (e) (identifier mop-up) entirely reds this --
    the embedded form is untouched by every \\b-anchored tier."""
    from scripts.purge.replacements import _token_tier_rules

    all_rules = _token_tier_rules("BAR", "third_party", "x")
    all_but_mopup = tuple(
        rule for rule in all_rules if rule.kind != "identifier mop-up (unanchored)"
    )
    assert apply_rules("_BAR_TABLE_VALUES", all_but_mopup) == "_BAR_TABLE_VALUES"
    assert apply_rules("_BAR_TABLE_VALUES", all_rules) != "_BAR_TABLE_VALUES"


def test_tier_ordering_is_article_then_sentence_general_mopup() -> None:
    kinds = [rule.kind for rule in _rules_for_synthetic_third_party()]
    assert kinds.index(
        "definite-article guard: definite article (lowercase)"
    ) < kinds.index("general")
    assert kinds.index("sentence-start guard: start of blob") < kinds.index("general")
    assert kinds.index("general") < kinds.index("identifier mop-up (unanchored)")


def test_dotted_module_path_gets_bare_adjective_not_sentence_phrase() -> None:
    """Item 1: design.md `#### IdentityErasure`'s own fix -- "the lower-case
    module segment of that dotted module path ... becomes `withdrawn`",
    never the sentence-shaped `the third party`. Without the dedicated tier,
    tier (d)'s plain `\\b`-anchored general rule reaches the same text (`.`
    is a non-word character) and substitutes the sentence-shaped phrase
    instead -- measured in a real rewritten repository: 59 blobs carrying
    `load.the third party`, 15 blobs across 12 paths newly failing
    `ast.parse`."""
    rules = _rules_for_synthetic_third_party()
    assert apply_rules("fitdocs.load.Bar", rules) == "fitdocs.load.Withdrawn"
    # Mutation: deleting the dotted-module-path tier reds this -- tier (d)
    # alone produces the sentence-shaped phrase after the dot instead.
    assert "the third party" not in apply_rules("fitdocs.load.Bar", rules)


def test_dotted_module_path_case_matches_the_observed_variant() -> None:
    upper_rules = _token_tier_rules("BAR", "third_party", "surname alone (synthetic)")
    assert apply_rules("fitdocs.load.BAR", upper_rules) == "fitdocs.load.WITHDRAWN"

    title_rules = _token_tier_rules("Bar", "third_party", "surname alone (synthetic)")
    assert apply_rules("fitdocs.load.Bar", title_rules) == "fitdocs.load.Withdrawn"


def test_dotted_module_path_tier_precedes_general_tier() -> None:
    kinds = [rule.kind for rule in _rules_for_synthetic_third_party()]
    assert kinds.index("dotted module path segment") < kinds.index("general")


def test_noun_core_guard_scoped_to_methodology_family_only() -> None:
    """N4: the `if family == "withdrawn_methodology":` guard around
    `noun_core`'s trailing-word consumption must stay scoped to that one
    family. Deleting the guard (so every family consumes a following
    "methodology" word) would silently drop the noun from a sentence like
    "a computed result naming the *Surname* methodology" -- exactly the
    redact-don't-falsify claim Req 11.6 makes about what a sentence still
    states after redaction."""
    rules = _rules_for_synthetic_third_party()
    result = apply_rules("naming the Bar methodology unchanged", rules)
    assert result == "naming the third party methodology unchanged"
    # Mutation: removing the family guard reds this -- "methodology" would
    # be silently consumed and dropped by the definite-article guard.
    assert "methodology" in result


def test_trailing_methodology_word_stays_optional_not_mandatory() -> None:
    """N6: the trailing `(?:\\s+methodology\\b)?` group inside `noun_core`
    must stay optional. Of 1239 real methodology-family token occurrences,
    only 7 are followed by the literal word "methodology" -- making the
    group mandatory would strand the other 1232 occurrences past tiers
    (a)/(c)/(d) entirely, dropping them onto the identifier mop-up's bare
    adjective instead of the full sentence-shaped replacement."""
    rules = _rules_for_synthetic_methodology()
    result = apply_rules("we discussed FBC results today", rules)
    assert result == "we discussed the withdrawn methodology results today"
    # Mutation: making the trailing group mandatory reds this -- "FBC" with
    # no following "methodology" word falls through to the mop-up and
    # becomes the bare adjective alone ("withdrawn"), not the full phrase.
    assert "the withdrawn methodology results" in result


def test_trailing_methodology_word_consumed_regardless_of_case() -> None:
    """N9: a deliberate choice, pinned either way rather than left
    unstated. The trailing word is matched case-insensitively
    (`[Mm]ethodology`) so a capitalised trailing occurrence (e.g. a heading
    reading "the FBC Methodology") is consumed too, rather than left behind
    as a case-mismatched duplicate noun ("the withdrawn methodology
    Methodology")."""
    rules = _rules_for_synthetic_methodology()
    result = apply_rules("the FBC Methodology is retired", rules)
    assert result == "the withdrawn methodology is retired"
    # Mutation: reverting to a case-sensitive `methodology`-only match reds
    # this -- the capitalised trailing word is left behind unconsumed.
    assert "Methodology" not in result


def test_sentence_start_guard_does_not_fire_after_an_abbreviation() -> None:
    """Item 4: `[.!?]\\s+` alone cannot distinguish "e.g." / "vs." from a
    genuine sentence end, so without the abbreviation guard the
    sentence-start tier wrongly capitalises the token there -- measured: 15
    real sites, e.g. `.kiro/steering/structure.md`, `.kiro/steering/tech.md`,
    `.kiro/specs/fit-ingest/requirements.md`, all reading `(e.g. <token>)`
    and becoming `(e.g. <Capitalised replacement>)`."""
    rules = _rules_for_synthetic_third_party()
    for abbreviation in _ABBREVIATIONS_BEFORE_PERIOD:
        text = f"a note ({abbreviation}. Bar's implementation) follows"
        result = apply_rules(text, rules)
        assert "The third party" not in result, (
            f"abbreviation {abbreviation!r} wrongly triggered the "
            f"sentence-start guard: {result!r}"
        )
        assert "the third party" in result


def test_abbreviation_list_contents_are_pinned_independently() -> None:
    """Pin `_ABBREVIATIONS_BEFORE_PERIOD`'s **contents** against a literal
    written out here, not against the constant under test.

    Every other assertion about the abbreviation guard derives its
    expectation from the constant: the loop above iterates it, and invariant
    4b builds its detector regex from it. So both production and detector
    move together and an edit to the list is invisible to the whole suite --
    measured, with real consequences in a real rewrite:

    * adding ``"copy"`` (an ordinary word at a genuine sentence end before a
      token) changes the redacted output of **2 real objects**, turning
      ``...travels with every copy. The withdrawn methodology prepends...``
      into a lowercase sentence start -- an invariant-5 violation the suite
      does not see;
    * removing ``"e.g"`` changes **14 real objects** back to
      ``(e.g. The withdrawn methodology ...)`` -- the very
      over-capitalisation this tier exists to prevent.

    The next step after this task is a maintainer review of the rendered
    rule table, which is exactly the moment someone might edit this list.
    A change there must red here rather than pass silently.

    The two behavioural assertions below are the ones that actually bite: a
    genuine sentence end after a non-abbreviation word must still capitalise,
    and ``e.g.`` specifically must not.
    """
    assert _ABBREVIATIONS_BEFORE_PERIOD == (
        "vs",
        "e.g",
        "i.e",
        "etc",
        "Mr",
        "Mrs",
        "Dr",
        "cf",
    )

    rules = _rules_for_synthetic_third_party()
    # "copy" is NOT an abbreviation: a genuine sentence end, must capitalise.
    assert apply_rules("it travels with every copy. Bar prepends a line", rules) == (
        "it travels with every copy. The third party prepends a line"
    )
    # "e.g." IS an abbreviation: not a sentence end, must stay lowercase.
    assert apply_rules("a note (e.g. Bar's implementation) follows", rules) == (
        "a note (e.g. the third party's implementation) follows"
    )


def test_sentence_start_guard_still_fires_at_a_genuine_sentence_end() -> None:
    """The abbreviation guard must not swallow the real case it is modelled
    on -- a genuine sentence end that merely happens to share a trailing
    substring with no abbreviation in the list."""
    rules = _rules_for_synthetic_third_party()
    result = apply_rules("Prior sentence ends. Bar stays registered", rules)
    assert result == "Prior sentence ends. The third party stays registered"


def test_longer_phrase_ordering_prevents_partial_containment() -> None:
    """Mirrors the real "a *Surname*\\n*Point* *System* zone" hazard
    (line-wrapped inside a 3-word methodology-name phrase): a 1-word
    surname rule must never fire on a piece of a longer phrase. Applying the
    3-word tier fully before the 1-word tier (as `build_rules` orders them)
    leaves the embedded surname alone once the phrase is already consumed."""
    from scripts.purge.replacements import _token_tier_rules

    long_rules = _token_tier_rules("Foo Bar Corp", "withdrawn_methodology", "long")
    short_rules = _token_tier_rules("Bar", "third_party", "short")
    text = "onto a Foo Bar\n  Corp zone, each return"
    after_long = apply_rules(text, long_rules)
    assert "Bar" not in after_long
    after_both = apply_rules(after_long, short_rules)
    assert after_both == after_long  # nothing left for the short rule to touch

    # Reversed order reproduces the real hazard: the short rule fires on the
    # embedded surname before the long rule ever runs.
    after_short_first = apply_rules(text, short_rules)
    assert after_short_first != text
    assert "Corp zone" in after_short_first  # "Foo Bar" partially consumed


# =============================================================================
# The copyright notice and the trademark mark (task 6.5, Req 11.4, 11.6, 11.12)
#
# NOTHING BELOW SPELLS THE RESERVED-RIGHTS PHRASE OR THE TRADEMARK MARK. Both
# are matched by the rules under test, and this file is a tracked blob at the
# tip, where invariant 6 requires the rule set to be a no-op; a fixture that
# merely *looks* like the thing being redacted gets redacted, which is the
# same trap `scripts/purge/replacements.py`'s module docstring records for the
# email allowlist. Every fixture below composes the phrase from
# `notice_phrase()` and the mark from `_TRADEMARK_MARK`, both at run time.
#
# The standing tip guard for these two needles --
# `test_the_notice_phrase_and_mark_are_absent_from_every_tracked_file` -- and
# its own independent survivor counter moved to
# `tests/test_forbidden_strings.py` / `tests/_forbidden_strings.py`
# (encumbered-content-purge task 7.2, design.md `#### MachineryRetirement`
# Phase R0). `_count_notice_phrase`, imported above from
# `tests._forbidden_strings`, is that same counter -- every test below that
# uses it is measuring `notice_rules`'s own redaction behaviour, not the tip
# guard, which is why they stayed here.
# =============================================================================

_NOTICE_PHRASE = notice_phrase()


def _tracked_text_files() -> dict[str, str]:
    """Every tracked file's WORKING-TREE text (not `HEAD`'s), so an
    uncommitted re-introduction is caught in the run that made it."""
    listed = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    texts: dict[str, str] = {}
    unread: dict[str, str] = {}
    for name in listed.split("\0"):
        if not name:
            continue
        path = _REPO_ROOT / name
        if not path.is_file():
            unread[name] = "not a regular file"
            continue
        try:
            texts[name] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            unread[name] = "not UTF-8"
        except OSError as exc:
            unread[name] = f"unreadable: {exc.strerror}"
    # A guard that silently skips what it cannot read reports "absent" for a
    # file it never looked at. The skipped set is returned to the caller under
    # a reserved key so every caller must decide about it out loud; the two
    # guards below assert it is exactly the one known binary fixture family.
    _UNREADABLE.clear()
    _UNREADABLE.update(unread)
    return texts


_UNREADABLE: dict[str, str] = {}
"""Tracked files `_tracked_text_files` could not read, from the most recent
call -- see the comment there."""


def _assert_unreadable_set_is_known() -> None:
    """Every tracked file the walk could not read, named. `.fit` fixtures are
    binary by nature and cannot carry a notice as text; anything else appearing
    here is a hole in both guards below and must be dealt with, not skipped."""
    unexpected = {
        name: why
        for name, why in _UNREADABLE.items()
        if not name.endswith((".fit", ".png", ".gz"))
    }
    assert not unexpected, (
        "tracked file(s) neither read nor accounted for by either notice "
        f"guard: {unexpected}"
    )


def _notice_rules() -> tuple[ReplacementRule, ...]:
    return notice_rules(_NOTICE_PHRASE)


def _notice_and_mark_rules() -> tuple[ReplacementRule, ...]:
    return (*_notice_rules(), trademark_mark_rule())


@pytest.mark.parametrize(
    "prefix",
    [
        pytest.param("© 2026 Foo Bar. ", id="sign-year-name-period"),
        pytest.param("(c) 2026 Foo Bar. ", id="ascii-sign"),
        pytest.param("(C) 2026 Foo Bar. ", id="ascii-sign-upper"),
        pytest.param("Copyright (c) Foo Bar. ", id="word-and-ascii-sign"),
        pytest.param("Copyright © 2026 Foo Bar. ", id="word-and-sign"),
        pytest.param("copyright © 2026 Foo Bar. ", id="lowercase-word"),
        pytest.param("© Foo Bar, ", id="comma-separated-no-year"),
        pytest.param("(c)\n2026 Foo Bar. ", id="wrapped-after-the-sign"),
        pytest.param("Copyright ", id="word-only"),
    ],
)
def test_notice_rules_consume_the_whole_notice_not_only_the_phrase(
    prefix: str,
) -> None:
    """Every real notice shape, in the form it has AFTER the token rules have
    replaced the attribution -- the order `build_rules` emits these in. The
    whole notice goes, mark and attribution included; leaving
    `<sign> 2026 <redacted>. <replacement>` standing is exactly the residue
    task 6.5 exists to remove."""
    text = f'the workbook is marked "{prefix}{_NOTICE_PHRASE}" and permission'

    result = apply_rules(text, _notice_rules())

    assert result == (
        'the workbook is marked "[redacted third-party copyright notice]" '
        "and permission"
    )
    assert "©" not in result
    assert "Foo Bar" not in result


def test_bare_phrase_is_redacted_where_no_mark_precedes_it() -> None:
    """The eight real sites where prose quotes the phrase alone -- no mark,
    no attribution. Req 11.4 is about the notice at any commit, and the
    fragment is the notice's own text."""
    text = f"three files carry an `{_NOTICE_PHRASE}` copyright notice naming"

    result = apply_rules(text, _notice_rules())

    # `a`, not `an`: the article tier owns this shape (see
    # `test_notice_article_tier_normalises_an_and_keeps_the_code_span`), and
    # `an [redacted ...]` is the ungrammatical output an earlier revision of
    # this module shipped.
    assert result == (
        "three files carry a `[redacted third-party copyright notice]` "
        "copyright notice naming"
    )


def test_notice_rules_leave_an_unrelated_copyright_sign_untouched() -> None:
    """The dominant hazard, pinned. The bare copyright sign and the word
    `copyright` each occur in the hundreds across dozens of paths in this
    history -- the exact figures move with every commit that discusses this
    work, so they are recorded against a named commit in
    `notice_rules`' docstring rather than stated present-tense here. A rule
    keyed on either would be irreversible over-redaction. These rules are
    keyed on the phrase, so a sign with no phrase behind it is not a notice
    they touch."""
    text = (
        "Copyright (c) 2020 Somebody Else\n"
        "SPDX-License-Identifier: MIT\n"
        "© the packaging metadata, and the word copyright in prose.\n"
    )

    assert apply_rules(text, _notice_rules()) == text


def test_notice_body_stops_at_the_measured_width() -> None:
    """The attribution span is bounded (`_NOTICE_BODY_MAX_WIDTH`, 40; widest
    real gap 23). Beyond it the mark is NOT consumed -- a documented,
    measured limitation rather than an unbounded match that could reach
    across a paragraph into unrelated prose. The phrase itself is still
    redacted, by the bare rule."""
    from scripts.purge.replacements import _NOTICE_BODY_MAX_WIDTH

    over = "x" * (_NOTICE_BODY_MAX_WIDTH + 1)
    result = apply_rules(f"© {over} {_NOTICE_PHRASE}", _notice_rules())
    assert result == f"© {over} [redacted third-party copyright notice]"

    under = "x" * (_NOTICE_BODY_MAX_WIDTH - 2)
    result = apply_rules(f"© {under} {_NOTICE_PHRASE}", _notice_rules())
    assert result == "[redacted third-party copyright notice]"


def test_notice_body_does_not_cross_a_quote_or_a_code_span() -> None:
    """A match must not start at a mark inside one quoted string and end at a
    phrase inside the next one -- `"` and `` ` `` are excluded from the body
    alphabet for exactly this. The sign belonging to the first quotation
    survives; the phrase in the second is redacted on its own."""
    text = f'said "© 2026 A" then "{_NOTICE_PHRASE}"'

    result = apply_rules(text, _notice_rules())

    assert result == 'said "© 2026 A" then "[redacted third-party copyright notice]"'


def test_notice_body_does_not_swallow_a_second_notice() -> None:
    """The body alphabet excludes the mark itself, so the leftmost mark
    cannot reach past a nearer one -- two adjacent notices are two matches,
    not one match eating the text between them."""
    text = f"© 2026 A. © 2026 B. {_NOTICE_PHRASE}"

    result = apply_rules(text, _notice_rules())

    assert result == "© 2026 A. [redacted third-party copyright notice]"


@pytest.mark.parametrize(
    "continuation",
    [
        pytest.param("\n# ", id="hash-comment"),
        pytest.param("\n#", id="hash-comment-no-space"),
        pytest.param("\n## ", id="repeated-hash"),
        pytest.param("\n> ", id="blockquote"),
        pytest.param("\n// ", id="slash-comment"),
        pytest.param("\n* ", id="list-bullet"),
        pytest.param("\n| ", id="table-cell"),
        pytest.param("\n\n> ", id="blank-line-then-blockquote"),
    ],
)
def test_notice_rule_matches_a_phrase_wrapped_onto_a_continuation_line(
    continuation: str,
) -> None:
    """The defect a whitespace-only pattern leaves behind, one shape per row.

    Measured over reachable history at `40eb36e`: whitespace-only tolerance
    finds 49 occurrences in 31 blobs, continuation tolerance finds 60 in 42.
    The 11 difference is 10 notices in `pyproject.toml` comments and one in
    `tests/purge/test_tree_removal.py` -- notices that a whitespace-only rule
    leaves standing in a real one-shot rewrite while every check built on the
    same helper reports zero survivors."""
    head, tail = _NOTICE_PHRASE.rsplit(" ", 1)
    text = f"{head}{continuation}{tail}"

    assert _count_notice_phrase(text) == 1, "the oracle must see this as present"
    assert apply_rules(text, _notice_rules()) == (
        "[redacted third-party copyright notice]"
    )


def test_notice_rule_matches_a_whole_notice_wrapped_onto_a_comment_line() -> None:
    """The real `pyproject.toml` shape: mark, attribution and a phrase that
    wraps onto the next comment line, inside one comment block."""
    head, tail = _NOTICE_PHRASE.rsplit(" ", 1)
    text = f"# The workbook is marked © 2026 Foo Bar. {head}\n# {tail} and so"

    assert _count_notice_phrase(text) == 1
    assert apply_rules(text, _notice_rules()) == (
        "# The workbook is marked [redacted third-party copyright notice] and so"
    )


def test_notice_article_tier_normalises_an_and_keeps_the_code_span() -> None:
    """The one real site where the bare phrase follows an article, in the
    shape it actually has -- the article, a line wrap, then the phrase inside
    a code span. `an [redacted ...]` is ungrammatical, which is what an
    earlier revision of this module shipped; the article tier consumes `an`
    and re-emits `a`, exactly as the token tiers' indefinite-article guard
    does for `an <adjective>`, while the captured group puts the wrap and the
    backtick back untouched."""
    text = f"three files carry an\n`{_NOTICE_PHRASE}` copyright notice naming"

    result = apply_rules(text, _notice_rules())

    assert result == (
        "three files carry a\n`[redacted third-party copyright notice]` "
        "copyright notice naming"
    )
    assert "an [" not in result and "an `[" not in result


def test_notice_article_tier_preserves_the_capital() -> None:
    """`An` at a sentence start becomes `A`, never a lower-case `a`."""
    text = f"An {_NOTICE_PHRASE} line is a notice."
    assert apply_rules(text, _notice_rules()) == (
        "A [redacted third-party copyright notice] line is a notice."
    )


def test_notice_article_tier_does_not_fire_on_a_word_ending_in_a() -> None:
    """`(?<![A-Za-z])` in front of the article: a word ending in `a`
    immediately before the phrase (`data <phrase>`) must not have that `a`
    eaten out of it and replaced."""
    text = f"data {_NOTICE_PHRASE} here"
    assert apply_rules(text, _notice_rules()) == (
        "data [redacted third-party copyright notice] here"
    )


def test_notice_prefix_consumes_the_word_and_the_ascii_sign_together() -> None:
    """`Copyright (c) ...` is consumed whole -- no `Copyright ` left dangling
    in front of the redaction.

    What this pins is that the prefix alternation carries the bare WORD at
    all, not the order it is written in. Reversing the alternation is an
    equivalent mutant (measured twice, reds nothing, byte-identical over the
    corpus): a backtracking engine falls back to the longer alternative at the
    same position anyway. Removing the word alternative
    (`m19_prefix_without_the_word`) reds this test and six sibling rows, 7 in
    all -- measured on this tree."""
    text = f"marked Copyright (c) 2026 Foo Bar. {_NOTICE_PHRASE} here"
    assert apply_rules(text, _notice_rules()) == (
        "marked [redacted third-party copyright notice] here"
    )


def test_a_marker_that_does_not_open_a_line_is_not_a_continuation() -> None:
    """A `#` in the middle of a line is a character, not a continuation
    marker, and the words either side of it are not the phrase.

    This is the rule/oracle symmetry that an earlier revision broke in the
    other direction: with markers allowed anywhere, the rule matched prose the
    independent counter did not count -- including this module's own
    docstrings, which it then rewrote, while both tip guards reported the tree
    clean because the counter could not see what the rule was matching. The
    generator rewriting its own source is how that surfaced."""
    head, tail = _NOTICE_PHRASE.rsplit(" ", 1)
    text = f"{head} # {tail}"

    assert _count_notice_phrase(text) == 0, "the oracle must not count this"
    assert apply_rules(text, _notice_rules()) == text


def test_every_notice_and_mark_rule_compiles_as_bytes() -> None:
    """**The consumer compiles these patterns as BYTES, not as `str`.**
    `git_filter_repo.py::FilteringOptions.get_replace_text` opens the rule
    file `'br'` and compiles each `regex:` line's raw bytes, and it compiles
    every one of them BEFORE rewriting anything -- so a single pattern that is
    valid only as `str` aborts the whole one-shot run.

    Measured, not hypothesised: a pattern spelling the copyright sign
    `\\u00a9` compiles fine here and raises `bad escape \\u` as bytes, which
    is exactly what an earlier revision of this module emitted."""
    for rule in _notice_and_mark_rules():
        re.compile(rule.pattern.encode("utf-8"))
        re.compile(rule.pattern)


def test_notice_rules_behave_identically_in_the_bytes_domain() -> None:
    """Compiling is necessary, not sufficient: a character class holding a
    multi-byte character compiles as bytes and means something else there (a
    class of individual bytes, which shreds an em dash). This applies the same
    rules both ways over every shape this section exercises and requires the
    results to agree."""
    head, tail = _NOTICE_PHRASE.rsplit(" ", 1)
    corpus = "\n".join(
        (
            f'the workbook is marked "© 2026 Foo Bar. {_NOTICE_PHRASE}" and',
            f"# © 2026 Foo Bar, {head}\n# {tail} -- kept out",
            f"> Copyright (c) 2026 Foo Bar. {_NOTICE_PHRASE}",
            f"three files carry an\n`{_NOTICE_PHRASE}` copyright notice",
            f"an em dash — and a sign © in unrelated prose, {_NOTICE_PHRASE}",
            f"FBC{_TRADEMARK_MARK} name and System{_TRADEMARK_MARK} mark",
            "© 2020 Somebody Else, licensed under MIT — untouched",
            # THE CELL THAT MAKES THIS TEST BITE: a multi-byte character
            # INSIDE the attribution, between the mark and the phrase. A
            # negated character class holding the mark excludes its LEAD BYTE
            # `\xe2` when compiled as bytes, and the em dash (`\xe2\x80\x94`)
            # shares that lead byte -- so as bytes the attribution stops dead
            # at the dash and the notice SURVIVES, while as str it is
            # redacted. With every non-ASCII character outside the
            # attribution spans, as an earlier revision of this fixture had
            # it, the divergence cannot occur and the test is a hollow pin.
            # Lead bytes `\xc2` and `\xe2` alone cover em and en dashes,
            # curly quotes, the ellipsis, the section and degree signs,
            # guillemets and arrows -- all pervasive in this repository.
            f"© 2026 Acme — Ltd. {_NOTICE_PHRASE}",
            f"© 2026 Acme « Ltd » §3. {_NOTICE_PHRASE}",
            f"Copyright (c) 2026 Acme… Ltd. {head}\n# {tail}",
        )
    )

    as_str = apply_rules(corpus, _notice_and_mark_rules())

    as_bytes = corpus.encode("utf-8")
    for rule in _notice_and_mark_rules():
        as_bytes = re.sub(
            rule.pattern.encode("utf-8"), rule.replacement.encode("utf-8"), as_bytes
        )

    assert as_bytes.decode("utf-8") == as_str
    assert "—" in as_str, "the em dash must survive both domains intact"
    assert as_str.count("©") == 1, "only the unrelated sign may remain"
    # Reachability: the attribution-internal cells must actually have been
    # redacted, or the equality above compares two identical no-ops.
    assert "Acme" not in as_str, as_str
    assert _count_notice_phrase(as_str) == 0, as_str


def test_notice_rule_matches_a_line_wrapped_phrase() -> None:
    """Six real sites wrap the phrase across a line break; a fixed-space
    pattern is blind to every one of them."""
    wrapped = "\n  ".join(_NOTICE_PHRASE.split())
    result = apply_rules(f"© 2026 Foo Bar. {wrapped}", _notice_rules())
    assert result == "[redacted third-party copyright notice]"


def test_notice_rule_does_not_fire_on_a_partial_phrase() -> None:
    """A rule matching part of the phrase is a new mangling source
    (invariant 4). Neither the first two words nor the last two are the
    notice."""
    words = _NOTICE_PHRASE.split()
    for partial in (" ".join(words[:2]), " ".join(words[1:])):
        text = f"© 2026 Foo Bar. {partial} here"
        assert apply_rules(text, _notice_rules()) == text


def test_notice_rules_are_ordered_whole_notice_before_bare_phrase() -> None:
    """Order is load-bearing, the same way the token tiers' is. Reversed, the
    bare rule consumes the phrase first and the prefixed rule can never fire
    -- leaving the mark and the attribution standing."""
    prefixed, article_lower, article_upper, bare = _notice_rules()
    assert "mark, attribution" in prefixed.kind
    assert "indefinite article" in article_lower.kind
    assert "indefinite article" in article_upper.kind
    assert "bare" in bare.kind

    text = f"© 2026 Foo Bar. {_NOTICE_PHRASE}"
    assert apply_rules(text, (prefixed, bare)) == (
        "[redacted third-party copyright notice]"
    )
    reversed_result = apply_rules(text, (bare, prefixed))
    assert reversed_result == (
        "© 2026 Foo Bar. [redacted third-party copyright notice]"
    )


def test_trademark_mark_is_deleted_without_splitting_the_words_around_it() -> None:
    """The mark is a claim, not a record: it goes, and nothing is put in its
    place. It sits mid-word at every real site, so any substituted wording
    would split the surrounding words."""
    text = f"WITHDRAWN{_TRADEMARK_MARK} name and the System{_TRADEMARK_MARK} mark"

    result = apply_rules(text, (trademark_mark_rule(),))

    assert result == "WITHDRAWN name and the System mark"
    assert _TRADEMARK_MARK not in result


def test_notice_and_mark_rules_carry_no_inline_case_insensitivity() -> None:
    """`rewrite.py::build_replacement_expressions`'s `(?i)` is what this
    module exists to avoid; a notice rule that reintroduced it inline would
    make the per-variant rules collide exactly as the token rules would."""
    for rule in _notice_and_mark_rules():
        assert "(?i" not in rule.pattern, rule.kind


def test_no_notice_or_mark_rule_replacement_reintroduces_what_it_removes() -> None:
    """A replacement carrying the phrase or the mark would make the rules
    non-idempotent and would falsify every "zero surviving occurrences"
    measurement taken after them."""
    for rule in _notice_and_mark_rules():
        assert _NOTICE_PHRASE not in rule.replacement
        assert _TRADEMARK_MARK not in rule.replacement


# --- the notice adjacency table (the oracle, not the suite, is the gate) -----

_NOTICE_ADJACENCY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("line-start", ""),
    ("space", " "),
    ("newline", "\n"),
    ("letter", "x"),
    ("upper-letter", "X"),
    ("digit", "7"),
    ("underscore", "_"),
    ("hyphen", "-"),
    ("period", "."),
    ("dot-space", ". "),
    ("quote", '"'),
    ("backtick", "`"),
    ("paren-open", "("),
    ("sign", "©"),
    ("sign-year-name", "© 2026 Foo Bar. "),
    ("ascii-sign-year-name", "(c) 2026 Foo Bar. "),
    ("word-sign-name", "Copyright (c) Foo Bar. "),
    ("word-only", "Copyright "),
    ("sign-then-quote", '© 2026 "A" '),
    ("sign-beyond-the-body-bound", "© " + "y" * 45 + " "),
    ("letter-run-ending-in-a-letter", "© 2026 FooBar"),
)
"""Both halves of the space: the characters that can sit immediately before
the phrase (every class the whole-word oracle distinguishes -- letters,
digits, underscore, punctuation, whitespace, line start) and the notice
prefixes the prefixed rule is supposed to consume, including two that it must
NOT consume (a body over the width bound, and a body crossing a quote)."""

_NOTICE_ADJACENCY_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("line-end", ""),
    ("space", " "),
    ("newline", "\n"),
    ("letter", "x"),
    ("upper-letter", "X"),
    ("letters", "ly"),
    ("digit", "7"),
    ("underscore", "_"),
    ("hyphen", "-"),
    ("period", "."),
    ("period-space", ". "),
    ("comma", ","),
    ("double-quote", '"'),
    ("backtick", "`"),
    ("paren-close", ")"),
    ("bracket-close", "]"),
    ("colon", ":"),
    ("semicolon", ";"),
)


def _phrase_present_as_whole_words(text: str, phrase: str) -> bool:
    """The ORACLE for the adjacency table: is the phrase present as
    consecutive whole words, case-sensitively?

    Delegates to `_count_notice_phrase`, which is implemented by splitting and
    comparing word lists and shares nothing with the production pattern -- the
    independence task 6.4's identity oracle established, applied here. A
    regex with lookarounds would be the thing under test restated, and a
    restated anchor is what four review rounds cost that task."""
    assert phrase == _NOTICE_PHRASE, "the table is built for the real phrase"
    return _count_notice_phrase(text, fold_case=False) > 0


@pytest.mark.parametrize(
    "suffix_id,suffix",
    _NOTICE_ADJACENCY_SUFFIXES,
    ids=[i for i, _ in _NOTICE_ADJACENCY_SUFFIXES],
)
@pytest.mark.parametrize(
    "prefix_id,prefix",
    _NOTICE_ADJACENCY_PREFIXES,
    ids=[i for i, _ in _NOTICE_ADJACENCY_PREFIXES],
)
def test_notice_rule_adjacency_matches_whole_words(
    prefix_id: str, prefix: str, suffix_id: str, suffix: str
) -> None:
    """The notice rules redact a cell exactly when the phrase is present as
    consecutive whole words, over the full product of prefix and suffix
    contexts (360 cells).

    Both failure directions are real. Over-matching mangles a longer word
    into a redaction notice (invariant 4); under-matching leaves a third
    party's copyright notice in reachable history, which is what Req 11.4
    forbids unconditionally."""
    text = f"{prefix}{_NOTICE_PHRASE}{suffix}"
    expected_redaction = _phrase_present_as_whole_words(text, _NOTICE_PHRASE)

    result = apply_rules(text, _notice_rules())

    if expected_redaction:
        assert result != text, (
            f"UNDER-redaction at prefix={prefix_id!r} suffix={suffix_id!r}: "
            "the phrase stands here as whole words, so a third party's "
            "copyright notice would survive the rewrite"
        )
        assert _NOTICE_PHRASE not in result
        assert "[redacted third-party copyright notice]" in result
    else:
        assert result == text, (
            f"OVER-redaction at prefix={prefix_id!r} suffix={suffix_id!r}: "
            "the phrase is part of a longer word here, so redacting it "
            "produces a mangled form (invariant 4)"
        )


def test_notice_adjacency_table_is_complete() -> None:
    """The completeness half and the positive control: the classes the table
    claims to cover are in it, and the oracle says BOTH redact and
    leave-alone across it rather than pinning one branch everywhere."""
    prefixes = {value for _id, value in _NOTICE_ADJACENCY_PREFIXES}
    suffixes = {value for _id, value in _NOTICE_ADJACENCY_SUFFIXES}

    for character in "xX7_-.":
        assert any(value.endswith(character) for value in prefixes), character
        assert any(value.startswith(character) for value in suffixes), character
    assert "" in prefixes and "" in suffixes

    outcomes = {
        _phrase_present_as_whole_words(f"{p}{_NOTICE_PHRASE}{s}", _NOTICE_PHRASE)
        for p in prefixes
        for s in suffixes
    }
    assert outcomes == {True, False}, (
        "the oracle must say BOTH redact and leave-alone across this table; "
        f"got only {outcomes} -- every cell is pinning the same branch"
    )
    assert len(prefixes) * len(suffixes) >= 300


@pytest.mark.parametrize(
    "prefix_id,expected_mark_survives",
    [
        ("sign-year-name", False),
        ("ascii-sign-year-name", False),
        ("word-sign-name", False),
        ("word-only", False),
        ("sign-then-quote", True),
        ("sign-beyond-the-body-bound", True),
    ],
)
def test_notice_prefix_consumption_over_the_adjacency_prefixes(
    prefix_id: str, expected_mark_survives: bool
) -> None:
    """The other half of the prefixed rule: the phrase always goes (the table
    above), and the mark in front of it goes exactly when it is close enough
    and not separated by a quote. The two `True` rows are the documented
    limits of `_NOTICE_BODY_PATTERN`, not accidents."""
    prefix = dict(_NOTICE_ADJACENCY_PREFIXES)[prefix_id]
    result = apply_rules(f"{prefix}{_NOTICE_PHRASE}", _notice_rules())

    assert _NOTICE_PHRASE not in result
    marks_present = "©" in result or "(c)" in result or "Copyright" in result
    assert marks_present is expected_mark_survives, result


def test_notice_variant_discovery_finds_a_variant_only_ever_comment_wrapped(
    tmp_path: Path,
) -> None:
    """`observed_notice_case_variants` must find a case variant whose ONLY
    occurrence in the repository is wrapped onto a comment continuation line.

    This is the hazard that makes the notice's own discovery function
    necessary rather than decorative: `observed_case_variants` joins words
    with `\\s+`, so against this fixture it returns nothing at all for the
    upper-case variant, and `build_rules` then emits **no rule for it** --
    a whole case variant of the notice left standing in history with every
    other check reporting success. Equivalence on the real corpus (where the
    one variant also appears unwrapped) is a property of that corpus, not of
    the function, which is why this fixture supplies a repository where the
    two functions genuinely disagree."""
    upper = _NOTICE_PHRASE.upper()
    head, tail = upper.rsplit(" ", 1)
    repo = _init_repo(tmp_path)
    _commit_blob(repo, "pyproject.toml", f"# a notice: {head}\n# {tail} -- kept\n")

    variants = observed_notice_case_variants(repo)

    assert upper in variants, variants
    # The discovered variant is the phrase, not the phrase with a comment
    # marker embedded in it: the old normaliser (`" ".join(match.split())`)
    # would have produced a bogus variant carrying the marker, and
    # `notice_rules` would have emitted a rule matching nothing.
    for variant in variants:
        assert all(word.isalpha() for word in variant.split()), variant
        assert "#" not in variant

    # The wrap-blind function is the counterfactual, and it must disagree --
    # otherwise this fixture is not exercising the difference at all.
    assert observed_case_variants(repo, notice_phrase()) == (), (
        "the fixture no longer distinguishes the two discovery functions"
    )

    source = tmp_path / "forbidden.tsv"
    _write_synthetic_forbidden_strings(source)
    rules = build_rules(repo, source)
    assert any(rule.kind.startswith("copyright ") for rule in rules), (
        "no notice rule was emitted for a variant only ever seen comment-wrapped"
    )
    (redacted,) = scan_repo_for_rules(repo, rules).values()
    assert _count_notice_phrase(redacted) == 0, redacted


def test_notice_separator_does_not_backtrack_catastrophically() -> None:
    """A line-leading run of continuation markers must cost linear time, not
    exponential.

    The first version of `_NOTICE_CONTINUATION_MARKERS` was an ambiguous
    nested quantifier: measured on that pattern with a non-matching tail, 16
    markers cost 0.006s, 18 cost 0.023s, 20 cost 0.093s, 22 cost 0.372s and 24
    cost 1.416s -- a ratio of 4.07, 4.06, 4.00, 3.80 per two markers, putting
    40 markers at roughly 26 hours. Nothing in
    this corpus triggers it, which is exactly why only a timing guard catches
    it: both tip guards run this pattern over ARBITRARY tracked files, and a
    reviewer's variant of the same shape ran for over half an hour against a
    four-and-a-half-minute baseline before being killed.

    The bound is deliberately loose (a second, against a linear form that
    needs 3e-05s for 2000 markers) so this measures the exponent, not the
    machine."""
    import time

    rules = _notice_rules()
    head, tail = _NOTICE_PHRASE.rsplit(" ", 1)
    # Markers, then a tail that cannot complete the phrase: the worst case for
    # a backtracking engine, since it must exhaust every way to split the run.
    pathological = f"{head}\n" + "#" * 40 + f" {tail[:-1]}"

    started = time.perf_counter()
    result = apply_rules(pathological, rules)
    elapsed = time.perf_counter() - started

    assert result == pathological, "the fixture must NOT match; it is the worst case"
    assert elapsed < 1.0, (
        f"the continuation separator took {elapsed:.3f}s over 40 markers -- "
        "an ambiguous nested quantifier is back"
    )


def test_build_rules_appends_notice_and_mark_rules_after_every_token_tier(
    tmp_path: Path,
) -> None:
    """The wiring: `build_rules` discovers the phrase's case variants in the
    repository the same way it discovers a token's, emits both notice rules
    per variant AFTER every token tier, and ends with exactly one mark
    rule."""
    repo = _init_repo(tmp_path)
    _commit_blob(
        repo,
        "notes.md",
        f'the Foo Bar Corp workbook is marked "© 2026 Foo Bar. '
        f'{_NOTICE_PHRASE}" and the FBC{_TRADEMARK_MARK} name was used.\n',
    )
    source = tmp_path / "forbidden.tsv"
    _write_synthetic_forbidden_strings(source)

    rules = build_rules(repo, source)

    kinds = [rule.kind for rule in rules]
    notice_indices = [i for i, k in enumerate(kinds) if k.startswith("copyright ")]
    assert len(notice_indices) == 4, kinds
    assert kinds[-1] == "trademark mark: deleted"
    assert kinds.count("trademark mark: deleted") == 1
    last_token_tier = max(
        i for i, rule in enumerate(rules) if rule.token_role not in {"(notice)"}
    )
    assert min(notice_indices) > last_token_tier

    (redacted,) = scan_repo_for_rules(repo, rules).values()
    assert _NOTICE_PHRASE not in redacted
    assert _TRADEMARK_MARK not in redacted
    assert "©" not in redacted
    assert "[redacted third-party copyright notice]" in redacted


def test_build_rules_emits_a_notice_rule_set_per_observed_case_variant(
    tmp_path: Path,
) -> None:
    """One rule per observed case variant, discovered from the corpus --
    never assumed, and never collapsed by an inline `(?i)`."""
    repo = _init_repo(tmp_path)
    _commit_blob(
        repo,
        "notes.md",
        f"{_NOTICE_PHRASE}\n{_NOTICE_PHRASE.lower()}\n",
    )
    source = tmp_path / "forbidden.tsv"
    _write_synthetic_forbidden_strings(source)

    rules = build_rules(repo, source)

    notice = [rule for rule in rules if rule.kind.startswith("copyright ")]
    assert len(notice) == 8, [rule.kind for rule in notice]

    (redacted,) = scan_repo_for_rules(repo, rules).values()
    assert _NOTICE_PHRASE not in redacted
    assert _NOTICE_PHRASE.lower() not in redacted


# --- rendering: masking, ordering never re-sorted -----------------------------


def test_render_rules_uses_regex_prefix_and_arrow_and_preserves_order() -> None:
    rules = _rules_for_synthetic_third_party()[:3]
    rendered = render_rules(rules)
    lines = rendered.splitlines()
    assert len(lines) == 3
    assert all(line.startswith("regex:") for line in lines)
    assert all("==>" in line for line in lines)
    # Item 9: `lines[0] != lines[1]` (the old assertion) is not an order
    # check -- it is true for any two distinct rules regardless of
    # rendering order. Pin the actual per-line content in input order, and
    # separately pin that reversing the input reverses the output.
    for line, rule in zip(lines, rules, strict=True):
        assert line == f"regex:{rule.pattern}==>{rule.replacement}"
    reversed_rendered = render_rules(tuple(reversed(rules)))
    assert reversed_rendered.splitlines() == list(reversed(lines))


def test_render_masked_table_never_reproduces_the_pattern() -> None:
    rules = _rules_for_synthetic_third_party()
    table = render_masked_table(rules)
    for rule in rules:
        assert rule.pattern not in table
    # the replacement text (token-free) IS allowed to appear
    assert "third party" in table


def test_render_masked_table_reports_shape_not_value() -> None:
    rules = _rules_for_synthetic_third_party()
    table = render_masked_table(rules)
    header, *rows = table.splitlines()
    assert header.split("\t") == [
        "index",
        "token_role",
        "kind",
        "pattern_length",
        "replacement",
    ]
    assert len(rows) == len(rules)


# --- case-variant discovery, against a synthetic repository ------------------


def test_observed_case_variants_finds_every_distinct_case_form(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_blob(repo, "a.md", "Bar is here")
    _commit_blob(repo, "b.md", "BAR is here too")
    _commit_blob(repo, "c.md", "and bar again")
    variants = observed_case_variants(repo, "Bar")
    assert set(variants) == {"Bar", "BAR", "bar"}


def test_observed_case_variants_normalises_wrapped_whitespace(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_blob(repo, "a.md", "Foo\n  Bar wrapped across a line")
    variants = observed_case_variants(repo, "Foo Bar")
    assert variants == ("Foo Bar",)


def test_observed_case_variants_finds_nothing_when_absent(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_blob(repo, "a.md", "nothing relevant here")
    assert observed_case_variants(repo, "Bar") == ()


# --- load_tokens: category filtering ------------------------------------------


def test_load_tokens_reads_only_the_token_category(tmp_path: Path) -> None:
    source = tmp_path / "forbidden.tsv"
    source.write_text(
        "token\tFoo Bar\n"
        "token\tBar\n"
        "token\tFoo Bar Corp\n"
        "token\tFBC\n"
        "path\tdocs/reference/foo.md\n",
        encoding="utf-8",
    )
    tokens = load_tokens(source)
    assert tokens == ("Foo Bar", "Bar", "Foo Bar Corp", "FBC")


# --- build_rules: end-to-end over a synthetic repository ----------------------


def _write_synthetic_forbidden_strings(path: Path) -> None:
    path.write_text(
        "token\tFoo Bar\n"
        "token\tBar\n"
        "token\tFoo Bar Corp\n"
        "token\tFBC\n"
        "path\tdocs/reference/foo-bar.md\n",
        encoding="utf-8",
    )


def test_build_rules_raises_when_token_count_does_not_match_role_table(
    tmp_path: Path,
) -> None:
    """Mutation: this pins that `build_rules` refuses to guess a role
    assignment for a differently-shaped file rather than silently zipping
    a mismatched list (which `zip` would do without error)."""
    repo = _init_repo(tmp_path)
    _commit_blob(repo, "a.md", "irrelevant")
    source = tmp_path / "forbidden.tsv"
    source.write_text("token\tOnly One\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expected"):
        build_rules(repo, source)


def test_build_rules_raises_on_row_order_drift_with_matching_count(
    tmp_path: Path,
) -> None:
    """Item 8: a same-count file whose rows are reordered must not silently
    scramble the family/role mapping -- `_TOKEN_ROLES` is index-keyed and
    never compares against a literal token value, so the only signal
    available is each row's word-count shape (2, 1, 3, 1 in file order).
    Reversing the four rows produces (1, 3, 1, 2), a mismatch at every
    position, which is exactly the scenario the reviewer measured (101
    rules, family mapping scrambled, no error) before this remediation."""
    repo = _init_repo(tmp_path)
    _commit_blob(repo, "a.md", "irrelevant")
    source = tmp_path / "forbidden.tsv"
    source.write_text(
        "token\tFBC\ntoken\tFoo Bar Corp\ntoken\tBar\ntoken\tFoo Bar\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="shape"):
        build_rules(repo, source)


def test_build_rules_end_to_end_over_synthetic_repository(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit_blob(
        repo,
        "notes.md",
        "the Foo Bar Corp workbook is marked with a Foo Bar Corp symbol.\n"
        "FBC ships its data. an FBC result was seen.\n"
        "Foo Bar. Foo Bar's permission was required from Foo (fake@nope.test).\n"
        "not Foo the Banister citation.\n"
        "_FBC_TABLE_VALUES lives beside BarCalculator.\n",
    )
    source = tmp_path / "forbidden.tsv"
    _write_synthetic_forbidden_strings(source)
    rules = build_rules(repo, source)
    assert rules  # non-empty

    changed = scan_repo_for_rules(repo, rules)
    assert changed, "the synthetic repository's only blob should be rewritten"
    (result,) = changed.values()

    for forbidden in ("Foo Bar Corp", "FBC", "Foo Bar", "Bar"):
        assert forbidden not in result, forbidden

    for mangled in ("the the", "a the", "an withdrawn", "An withdrawn", "Withdrawned"):
        assert mangled not in result, mangled

    assert "_WITHDRAWN_TABLE_VALUES" in result
    assert "WithdrawnCalculator" in result
    assert "Foo the Banister" in result  # false positive untouched


def test_build_rules_is_ordered_given_name_email_then_longest_token_first() -> None:
    """Structural ordering check using the synthetic four-token shape --
    the given-name rules and the email rule precede every token tier, and
    each token's own tiers are contiguous and appear longest-word-count
    first."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo = _init_repo(tmp_path)
        _commit_blob(
            repo,
            "a.md",
            "Foo Bar Corp, Foo Bar, FBC, Bar all appear once, lower and upper: "
            "foo bar corp FBC bar FOO BAR CORP\n",
        )
        source = tmp_path / "forbidden.tsv"
        _write_synthetic_forbidden_strings(source)
        rules = build_rules(repo, source)

    roles_in_order = [rule.token_role for rule in rules]
    assert roles_in_order[0] == "full name (given + surname)"
    assert roles_in_order[1] == "full name (given + surname)"
    assert roles_in_order[2] == "(cross-cutting)"

    # After the fixed prelude, every remaining role-run is contiguous.
    remainder = roles_in_order[3:]
    seen_roles: list[str] = []
    for role in remainder:
        if not seen_roles or seen_roles[-1] != role:
            seen_roles.append(role)
    assert len(seen_roles) == len(set(seen_roles)), (
        f"a token's tiers were not contiguous: {seen_roles}"
    )
    # Longest phrase (3-word "former proper name") before the 2-word full
    # name's own token-tier block, before either 1-word token.
    assert seen_roles.index("former proper name, in full") < seen_roles.index(
        "full name (given + surname)"
    )


# --- scan_commit_messages_for_rules -------------------------------------------


def test_scan_commit_messages_for_rules_finds_changed_messages(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "a.md").write_text("x", encoding="utf-8")
    _git(repo, "add", "a.md")
    _git(repo, "commit", "-m", "mentions Bar in the subject")
    rules = _rules_for_synthetic_third_party()
    changed = scan_commit_messages_for_rules(repo, rules)
    assert len(changed) == 1
    (message,) = changed.values()
    assert "Bar" not in message
    assert "the third party" in message


# --- forbidden-strings skip/fail contract (Req 11.8) --------------------------


def test_source_set_but_broken_raises_rather_than_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins that a set-but-broken `FITDOCS_FORBIDDEN_STRINGS` value is a
    hard failure, never collapsed into the same skip an unset variable
    produces -- Req 11.8's own distinction, re-pinned here because this
    module is a direct consumer of that contract."""
    missing = tmp_path / "does-not-exist.tsv"
    monkeypatch.setenv("FITDOCS_FORBIDDEN_STRINGS", str(missing))
    with pytest.raises(ForbiddenStringsSourceError):
        load(_REPO_ROOT)


def test_source_unset_is_a_skip_not_a_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FITDOCS_FORBIDDEN_STRINGS", raising=False)
    with pytest.raises(pytest.skip.Exception):
        require(_REPO_ROOT)


# =============================================================================
# Acceptance: the six invariants, measured against the real object database.
# =============================================================================


def _surviving_content_blob_ids() -> frozenset[str]:
    """Blob ids the redaction plan marks `literal_replaceable` in content,
    excluding any blob that is exclusively found at a path the plan marks
    `removed` (that whole-blob deletion is `build_path_directives`'s job,
    not this module's) -- task 6.4's own definition of "surviving blob
    content". Reads the scratch plan artifacts task 5.2 produces; skips
    (not fails) if they are not present, since their absence is a
    plan-artifact availability question, not a `FITDOCS_FORBIDDEN_STRINGS`
    question and must not be collapsed into that contract."""
    content_path = Path.home() / ".fitdocs-purge" / "plan-content.tsv"
    paths_path = Path.home() / ".fitdocs-purge" / "plan-paths.tsv"
    if not content_path.exists() or not paths_path.exists():
        pytest.skip(f"redaction plan artifacts not found at {content_path.parent}")

    from scripts.purge.plan import parse_content_plan_tsv, parse_path_plan_tsv

    content_matches = parse_content_plan_tsv(content_path.read_text(encoding="utf-8"))
    path_matches = parse_path_plan_tsv(paths_path.read_text(encoding="utf-8"))
    removed_paths = frozenset(
        m.path for m in path_matches if m.disposition == "removed"
    )

    literal_replaceable = frozenset(
        m.blob_id for m in content_matches if m.disposition == "literal_replaceable"
    )
    if not literal_replaceable:
        return literal_replaceable

    # blob -> every path it has ever lived at, from git's own object walk.
    listed = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "rev-list", "--objects", "--all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    blob_paths: dict[str, set[str]] = {}
    for line in listed.splitlines():
        if " " not in line:
            continue
        blob_id, path = line.split(" ", 1)
        if blob_id in literal_replaceable:
            blob_paths.setdefault(blob_id, set()).add(path)

    surviving = set()
    for blob_id in literal_replaceable:
        paths = blob_paths.get(blob_id, set())
        if not paths or not paths.issubset(removed_paths):
            surviving.add(blob_id)
    return frozenset(surviving)


@pytest.fixture(scope="module")
def _built_rules() -> tuple[ReplacementRule, ...]:
    forbidden_strings_path = require(_REPO_ROOT).source
    return build_rules(_REPO_ROOT, forbidden_strings_path)


@pytest.fixture(scope="module")
def _applied_content(
    _built_rules: tuple[ReplacementRule, ...],
) -> dict[str, tuple[str, str]]:
    """`blob_id -> (original, redacted)` for every surviving-content blob --
    computed once and shared by every content invariant test below."""
    surviving = _surviving_content_blob_ids()
    result: dict[str, tuple[str, str]] = {}
    for blob_id in surviving:
        original = read_blob_text(_REPO_ROOT, blob_id)
        result[blob_id] = (original, apply_rules(original, _built_rules))
    return result


@pytest.fixture(scope="module")
def _applied_commit_messages(
    _built_rules: tuple[ReplacementRule, ...],
) -> dict[str, tuple[str, str]]:
    """`commit_id -> (original, redacted)` for every commit message
    reachable from any ref -- item 4: at least one real mangled-form
    lowercasing site is a commit message, not a blob, so invariants 4 and 5
    must measure this population too, not only `_applied_content`."""
    listed = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "rev-list", "--all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    result: dict[str, tuple[str, str]] = {}
    for commit_id in listed:
        original = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "log", "-1", "--format=%B", commit_id],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        result[commit_id] = (original, apply_rules(original, _built_rules))
    return result


def _tokens_surviving_in(text: str, tokens: Sequence[str]) -> tuple[str, ...]:
    """Every token of `tokens` still standing in `text`, case-insensitively
    and tolerating a line wrap inside a multi-word token.

    **Wrap-tolerant, and deliberately not by the rules' own mechanism.** The
    rules are built by running each multi-word token through
    `_whitespace_tolerant_pattern`; if this check called that helper (or
    `tests._forbidden_strings.matches`, which now does), a defect in it would
    make the rule and its own invariant blind in exactly the same place, and
    the invariant would score zero survivors while survivors stood -- which
    is not hypothetical: task 6.5's first survivor counter was built that way
    and passed at 49 -> 0 with the notice still in 11 blobs. Here the
    tolerance is derived the other way round, by collapsing every whitespace
    run in BOTH operands to a single space and then doing a flat substring
    test. Same population, independent construction, so the two can disagree.

    Before this, the check was `token.lower() in redacted.lower()` -- flat, so
    a multi-word token surviving across a line break counted as absent. That
    is the population this exists to see: 37 of the 485 wrap-tolerant
    occurrences in the real object database are wrapped, in 13 (token, blob)
    pairs where the flat test found none of the token at all.

    `str.split()` and the `\\s+` the rules join words with split on the
    **identical** set of code points -- measured exhaustively over all
    0x110000, both difference sets empty. So this oracle's tolerance is
    neither wider nor narrower than the rule's; independence here comes from
    the construction (collapse-then-substring versus a joined pattern), not
    from a difference in what counts as whitespace.

    One consequence worth stating, because it is invisible rather than
    asymmetric: both decline U+200B (zero width space) and U+00AD (soft
    hyphen), so a token separated by either is missed by the rule **and** by
    this oracle alike. That is a shared blind spot, not a safe direction --
    nothing here would red if such a separation existed. None does in the
    corpus, and `_whitespace_tolerant_pattern` is where a fix would go.
    """
    normalised = " ".join(text.lower().split())
    return tuple(
        token for token in tokens if " ".join(token.lower().split()) in normalised
    )


def test_tokens_surviving_in_sees_a_multi_word_token_split_by_a_line_break() -> None:
    """The invariants below are only as good as this oracle, and its whole
    reason to exist is the wrapped case -- so pin that directly rather than
    inferring it from two invariants that (correctly) find nothing.

    Fixture text is synthetic; the real tokens are never spelled in this
    repository. The `Planted, Token Phrase` and `Planted and a Token Phrase`
    cases pin that the tolerance stops at whitespace: an oracle that joined
    the words with anything wider would report survivors that are not there
    and red the invariants for no reason.
    """
    tokens = ("Planted Token Phrase", "SingleWordToken")

    assert _tokens_surviving_in("prose naming Planted Token Phrase here", tokens) == (
        "Planted Token Phrase",
    )
    assert _tokens_surviving_in("prose naming Planted\nToken Phrase here", tokens) == (
        "Planted Token Phrase",
    )
    assert _tokens_surviving_in("prose naming planted token\nphrase here", tokens) == (
        "Planted Token Phrase",
    )
    assert _tokens_surviving_in("prose naming SingleWordToken here", tokens) == (
        "SingleWordToken",
    )
    # A single-word token is not found split across a wrap: a word does not
    # wrap, and matching one that appears to would be a false survivor.
    assert _tokens_surviving_in("prose naming SingleWord\nToken here", tokens) == ()
    assert _tokens_surviving_in("Planted, Token Phrase", tokens) == ()
    assert _tokens_surviving_in("Planted and a Token Phrase", tokens) == ()
    assert _tokens_surviving_in("nothing of interest here", tokens) == ()
    # BOTH operands are normalised, not only the text. A token arriving from
    # `FITDOCS_FORBIDDEN_STRINGS` with a doubled space or a tab between its
    # words is the same token, and the rule built from it matches
    # single-spaced text (`_whitespace_tolerant_pattern` joins with `\s+`
    # whatever the token's own spacing was), so an oracle that normalised
    # only the text would miss a survivor the rule was aimed at.
    assert _tokens_surviving_in(
        "naming Planted Token Phrase", ("Planted  Token\tPhrase",)
    ) == ("Planted  Token\tPhrase",)


def test_invariant_1_zero_identifying_tokens_in_surviving_blob_content(
    _applied_content: dict[str, tuple[str, str]],
) -> None:
    if not _applied_content:
        pytest.skip("no surviving literal_replaceable content blobs to check")
    forbidden_strings = require(_REPO_ROOT)
    tokens = load_tokens(forbidden_strings.source)
    survivors: dict[str, tuple[str, ...]] = {}
    for blob_id, (_original, redacted) in _applied_content.items():
        hit = _tokens_surviving_in(redacted, tokens)
        if hit:
            survivors[blob_id] = hit
    assert not survivors, (
        f"invariant 1 violated in {len(survivors)} blob(s): {survivors}"
    )


def test_invariant_1_catches_a_token_wrapped_in_a_would_be_surviving_blob(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invariant 1 asserts an absence, and over this corpus the absence is
    real -- so the invariant returns the same verdict whichever oracle it
    calls, and swapping `_tokens_surviving_in` back for the flat check does
    not red it. An unpinned call site, so pin it counterfactually: feed the
    invariant an `_applied_content` whose redacted text carries a multi-word
    token split across a line break -- exactly the shape 37 occurrences in
    the real object database have -- and require the invariant to fail.

    **The token set is monkeypatched to one synthetic multi-word token, and
    that is load-bearing.** The first version of this test built its fixture
    from a REAL multi-word token and left the real token list in place. It
    passed under the very mutation it exists to catch, because that token's
    first word is itself a single-word token in the same list, so the flat
    check raised too -- for the wrong reason, on a different token. The
    scenario the test names (only a wrapped multi-word occurrence present)
    was never reached. With one synthetic token, "the flat check finds
    nothing here" holds by construction, and is asserted below rather than
    assumed.

    `require` is still called, and its `pytest.skip` when
    `FITDOCS_FORBIDDEN_STRINGS` is unset is deliberate: this test sits with
    the other named complementary skips of the unset configuration rather
    than silently passing there (Req 11.8).
    """
    require(_REPO_ROOT)
    token = "Planted Token Phrase"
    monkeypatch.setattr(
        "tests.purge.test_replacements.load_tokens", lambda _source: (token,)
    )
    words = token.split()
    wrapped = f"a paragraph of prose naming {words[0]}\n{' '.join(words[1:])} here\n"
    # The fixture really is invisible to the check this replaced -- if the
    # flat test could see it, the counterfactual would prove nothing.
    assert token.lower() not in wrapped.lower()

    with pytest.raises(AssertionError, match="invariant 1 violated in 1 blob"):
        test_invariant_1_zero_identifying_tokens_in_surviving_blob_content(
            {"0" * 40: ("", wrapped)}
        )


def test_invariant_2_zero_identifying_tokens_in_commit_messages(
    _built_rules: tuple[ReplacementRule, ...],
) -> None:
    forbidden_strings = require(_REPO_ROOT)
    tokens = load_tokens(forbidden_strings.source)
    changed = scan_commit_messages_for_rules(_REPO_ROOT, _built_rules)
    listed = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "rev-list", "--all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    survivors: dict[str, tuple[str, ...]] = {}
    for commit_id in listed:
        original = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "log", "-1", "--format=%B", commit_id],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        message = changed.get(commit_id, original)
        # Same wrap-tolerant oracle as invariant 1, for the same reason and
        # then some: a commit message is hard-wrapped at ~72 columns, so it
        # is if anything likelier than a blob to split a multi-word token
        # across a line.
        hit = _tokens_surviving_in(message, tokens)
        if hit:
            survivors[commit_id] = hit
    assert not survivors, (
        f"invariant 2 violated in {len(survivors)} commit(s): {survivors}"
    )


def test_invariant_3_zero_identity_leaks(
    _applied_content: dict[str, tuple[str, str]],
    _applied_commit_messages: dict[str, tuple[str, str]],
) -> None:
    """The denylisted identity-leak addresses (`identity_leak_addresses`,
    derived fresh from the real object database -- never a domain
    allowlist) must be absent from every surviving blob's redacted text AND
    every commit message's redacted text.

    Item 6: an earlier revision of this docstring claimed the given name is
    also covered here -- false. A bare given name (the possessive or
    parenthetical-email exception sites `given_name_rules` targets) has no
    email shape and is not one of `identity_leak_addresses`'s values. The
    given name's two exception rules are exercised directly, against
    synthetic tokens, by the mechanics tests above (`test_given_name_rules_*`);
    this test does not re-measure them against the real object database."""
    if not _applied_content and not _applied_commit_messages:
        pytest.skip("no surviving content or commit messages to check")

    from scripts.purge.replacements import identity_leak_addresses

    forbidden_strings = require(_REPO_ROOT)
    tokens = load_tokens(forbidden_strings.source)
    addresses = identity_leak_addresses(_REPO_ROOT, tokens)
    assert addresses, "expected at least the three real addresses to be found"
    lowered_addresses = tuple(address.lower() for address in addresses)

    # Every diagnostic below reports the MASKED tag, never the address: this
    # assertion only ever fires when a real identity survived, so an
    # unmasked message would print the leaked value into pytest output, CI
    # logs and any review report quoting them -- the exact failure mode that
    # required a commit on this branch to be amended.
    leaks: dict[str, tuple[str, ...]] = {}
    for blob_id, (_original, redacted) in _applied_content.items():
        lowered = redacted.lower()
        hit = tuple(
            _masked(address) for address in lowered_addresses if address in lowered
        )
        if hit:
            leaks[blob_id] = hit
    assert not leaks, f"invariant 3 violated (blob content, masked tags): {leaks}"

    message_leaks: dict[str, tuple[str, ...]] = {}
    for commit_id, (_original, redacted) in _applied_commit_messages.items():
        lowered = redacted.lower()
        hit = tuple(
            _masked(address) for address in lowered_addresses if address in lowered
        )
        if hit:
            message_leaks[commit_id] = hit
    assert not message_leaks, (
        f"invariant 3 violated (commit messages, masked tags): {message_leaks}"
    )


_MANGLED_WORD_BOUNDARIED_NEEDLES: tuple[str, ...] = (
    r"\bwithdrawnwithdrawn\b",
    r"\bWITHDRAWNWITHDRAWN\b",
    # Item 3: wrap-tolerant (`\s+`, not a literal single space) -- the
    # production regex a fixed-width `\s` allowed through is exactly what
    # the root cause exploited, so a detector using the same fixed-width
    # assumption cannot see the failure it exists to catch.
    r"\bthe\s+the\b",
    r"\bThe\s+the\b",
    r"\ba\s+the\b",
    r"\bA\s+the\b",
    r"\ban\s+withdrawn\b",
    r"\bAn\s+withdrawn\b",
    # Item 7: "the withdrawn methodology methodology" and its capitalised /
    # sentence-start variants -- the same duplicate-noun shape as "the the",
    # generalised to the withdrawn_methodology family's two-word bare form.
    r"\bwithdrawn\s+methodology\s+methodology\b",
    r"\bWithdrawn\s+methodology\s+methodology\b",
    r"\bThe\s+withdrawn\s+methodology\s+methodology\b",
)
"""Word-boundaried needles -- a naive substring check false-positives on
ordinary prose ("dat**a the** repository") that merely happens to contain
the same six characters, which is not the named mangled form at all."""

_MANGLED_PLAIN_SUBSTRING_NEEDLES: tuple[str, ...] = (
    "an_withdrawn",
    "Withdrawned",
    "withdrawnrunning",
)
"""Checked as plain substrings deliberately: both are themselves
identifier/word fragments, so a word-boundaried check would under-match the
exact real-history instances that motivated naming them."""


def _mangled_form_counts(text: str) -> dict[str, int]:
    """`needle -> occurrence count` in `text`, over every invariant-4
    needle. Used to compute a delta against the original (pre-redaction)
    text rather than an absolute count over the redacted text alone -- item
    4: an absolute count both false-positives on a mangled-looking shape
    that was already present in the source before the rules ever ran (not
    something the rules introduced) and is the wrong question regardless,
    since what invariant 4 actually claims is that the rules do not
    *introduce* a mangled form, not that none exists anywhere in history for
    unrelated reasons."""
    counts: dict[str, int] = {}
    for pattern in _MANGLED_WORD_BOUNDARIED_NEEDLES:
        found = len(re.findall(pattern, text))
        if found:
            counts[pattern] = found
    for needle in _MANGLED_PLAIN_SUBSTRING_NEEDLES:
        found = text.count(needle)
        if found:
            counts[needle] = found
    return counts


def test_invariant_4_zero_mangled_forms(
    _applied_content: dict[str, tuple[str, str]],
    _applied_commit_messages: dict[str, tuple[str, str]],
) -> None:
    """Item 4: measured over both surviving blob content and commit
    messages, as a delta against each object's own original (pre-redaction)
    text -- never an absolute count over the redacted text alone."""
    if not _applied_content and not _applied_commit_messages:
        pytest.skip("no surviving content or commit messages to check")

    offenders: dict[str, dict[str, int]] = {}
    for label, population in (
        ("blob", _applied_content),
        ("commit", _applied_commit_messages),
    ):
        for object_id, (original, redacted) in population.items():
            before = _mangled_form_counts(original)
            after = _mangled_form_counts(redacted)
            introduced = {
                needle: after.get(needle, 0) - before.get(needle, 0)
                for needle in set(before) | set(after)
                if after.get(needle, 0) > before.get(needle, 0)
            }
            if introduced:
                offenders[f"{label}:{object_id}"] = introduced
    assert not offenders, f"invariant 4 violated: {offenders}"


_DOTTED_PATH_MANGLED_NEEDLES: tuple[str, ...] = (
    r"\.the third party\b",
    r"\.The third party\b",
    r"\.the withdrawn methodology\b",
    r"\.The withdrawn methodology\b",
)
"""Item 1: the sentence-shaped replacement directly after a `.` is exactly
`load.the third party`, the mangled shape a real rewritten repository
carried 59 times before the dotted-module-path tier existed. A dot is a
non-word character, so tier (d)'s plain `\\b`-anchored rule reaches this
text too; the dedicated tier must win, never tier (d)."""


def _dotted_path_mangled_form_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for pattern in _DOTTED_PATH_MANGLED_NEEDLES:
        found = len(re.findall(pattern, text))
        if found:
            counts[pattern] = found
    return counts


def test_invariant_1b_zero_dotted_module_path_mangled_forms(
    _applied_content: dict[str, tuple[str, str]],
    _applied_commit_messages: dict[str, tuple[str, str]],
) -> None:
    """Item 1's own real-corpus acceptance check, measured the same delta
    way invariant 4 is -- against each object's own original text, so a
    pre-existing occurrence unrelated to the rules is never counted."""
    if not _applied_content and not _applied_commit_messages:
        pytest.skip("no surviving content or commit messages to check")

    offenders: dict[str, dict[str, int]] = {}
    for label, population in (
        ("blob", _applied_content),
        ("commit", _applied_commit_messages),
    ):
        for object_id, (original, redacted) in population.items():
            before = _dotted_path_mangled_form_counts(original)
            after = _dotted_path_mangled_form_counts(redacted)
            introduced = {
                needle: after.get(needle, 0) - before.get(needle, 0)
                for needle in set(before) | set(after)
                if after.get(needle, 0) > before.get(needle, 0)
            }
            if introduced:
                offenders[f"{label}:{object_id}"] = introduced
    assert not offenders, f"invariant 1b (dotted module path) violated: {offenders}"


# `_ABBREVIATIONS_BEFORE_PERIOD` is imported from `scripts.purge.replacements`
# (see the top-of-file import block) -- never redefined here. This is the
# exact list production code excludes from the sentence-start tier (see
# `replacements.py`'s own docstring on the constant). A hand-copied second
# list is how the guard and the check that measures it drift apart;
# importing the one list makes that impossible rather than merely unlikely.

_SENTENCE_START_NEEDLES: tuple[str, ...] = (
    "the third party",
    "the withdrawn methodology",
    # Item 3: the email rule's replacement is unconditionally lower-case
    # ("a redacted email address") with no sentence-start tier of its own --
    # this detector was structurally blind to a redacted email landing at a
    # true sentence start, which is exactly the same class of bug invariant
    # 5 exists to catch for the token families.
    "a redacted email address",
)

_abbreviation_before_re = re.compile(
    r"(?:" + "|".join(re.escape(a) for a in _ABBREVIATIONS_BEFORE_PERIOD) + r")\Z"
)
_sentence_start_needle_re = re.compile(
    r"[.!?]\s+(?:" + "|".join(re.escape(n) for n in _SENTENCE_START_NEEDLES) + r")\b"
)
_blob_start_needle_re = re.compile(
    r"\A(?:" + "|".join(re.escape(n) for n in _SENTENCE_START_NEEDLES) + r")\b"
)


def _sentence_start_lowercase_count(text: str) -> int:
    """Item 3: wrap-tolerant (`[.!?]\\s+`, consuming the punctuation and
    whitespace as part of the match) rather than the fixed-width
    `[.!?]\\s` lookbehind the old detector used -- independent of
    `replacements.py`'s own production-code whitespace assumption, so a
    regression to fixed-width matching in either place is still caught by
    the other."""
    count = 0
    for match in _sentence_start_needle_re.finditer(text):
        preceding = text[: match.start()]
        if _abbreviation_before_re.search(preceding):
            continue
        count += 1
    if _blob_start_needle_re.match(text):
        count += 1
    return count


def test_invariant_5_zero_sentence_start_lowercasings(
    _applied_content: dict[str, tuple[str, str]],
    _applied_commit_messages: dict[str, tuple[str, str]],
) -> None:
    """Item 4: measured over both surviving blob content and commit
    messages (one real lowercasing site the reviewer measured is a commit
    message), as a delta against each object's own original text."""
    if not _applied_content and not _applied_commit_messages:
        pytest.skip("no surviving content or commit messages to check")

    offenders: dict[str, int] = {}
    for label, population in (
        ("blob", _applied_content),
        ("commit", _applied_commit_messages),
    ):
        for object_id, (original, redacted) in population.items():
            before = _sentence_start_lowercase_count(original)
            after = _sentence_start_lowercase_count(redacted)
            delta = after - before
            if delta > 0:
                offenders[f"{label}:{object_id}"] = delta
    assert not offenders, f"invariant 5 violated: {offenders}"


_CAP_NEEDLES: tuple[str, ...] = (
    "The third party",
    "The withdrawn methodology",
)
"""The capitalised sentence-shaped forms tier (c) emits. Item 4 is the
mirror image of invariant 5: invariant 5 catches a real sentence start left
lowercase; this catches the opposite mistake -- a *non*-sentence-start
(immediately after an abbreviation such as "e.g." or "vs.") wrongly
capitalised, because `[.!?]\\s+` alone cannot tell the two apart."""

_abbreviation_over_cap_re = re.compile(
    r"(?:"
    + "|".join(re.escape(a) for a in _ABBREVIATIONS_BEFORE_PERIOD)
    + r")[.!?]\s+(?:"
    + "|".join(re.escape(n) for n in _CAP_NEEDLES)
    + r")\b"
)


def _abbreviation_over_capitalisation_count(text: str) -> int:
    return len(_abbreviation_over_cap_re.findall(text))


def test_invariant_4b_zero_abbreviation_over_capitalisation(
    _applied_content: dict[str, tuple[str, str]],
    _applied_commit_messages: dict[str, tuple[str, str]],
) -> None:
    """Item 4's own real-corpus acceptance check, measured the same delta
    way invariant 5 is. Pre-existing: 15 real sites (`.kiro/steering/
    structure.md`, `.kiro/steering/tech.md`, `.kiro/specs/fit-ingest/
    requirements.md`, among others) read `(e.g. <token>)` and, without the
    abbreviation guard on tier (c), became `(e.g. <Capitalised
    replacement>)`."""
    if not _applied_content and not _applied_commit_messages:
        pytest.skip("no surviving content or commit messages to check")

    offenders: dict[str, int] = {}
    for label, population in (
        ("blob", _applied_content),
        ("commit", _applied_commit_messages),
    ):
        for object_id, (original, redacted) in population.items():
            before = _abbreviation_over_capitalisation_count(original)
            after = _abbreviation_over_capitalisation_count(redacted)
            delta = after - before
            if delta > 0:
                offenders[f"{label}:{object_id}"] = delta
    assert not offenders, (
        f"invariant 4b (abbreviation over-capitalisation) violated: {offenders}"
    )


@pytest.fixture(scope="module")
def _blob_paths() -> dict[str, frozenset[str]]:
    """Every blob id git's object walk finds, across all history, mapped to
    every path it has ever lived at -- shared by the dotted-module-path
    `ast.parse` acceptance check below, which needs to know *which* changed
    blobs are `.py` files. `_applied_content` only carries blob ids, never
    paths."""
    listed = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "rev-list", "--objects", "--all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    blob_paths: dict[str, set[str]] = {}
    for line in listed.splitlines():
        if " " not in line:
            continue
        blob_id, path = line.split(" ", 1)
        blob_paths.setdefault(blob_id, set()).add(path)
    return {blob_id: frozenset(paths) for blob_id, paths in blob_paths.items()}


def test_acceptance_changed_python_blobs_still_ast_parse(
    _applied_content: dict[str, tuple[str, str]],
    _blob_paths: dict[str, frozenset[str]],
) -> None:
    """Item 1's own acceptance check, named directly in the remediation:
    every `.py` blob the rules actually change must still `ast.parse`. The
    dotted-module-path tier exists specifically because, without it, the
    general tier's sentence-shaped substitution right after a `.` breaks a
    dotted import or attribute expression -- measured in a real rewritten
    repository: 15 blobs across 12 distinct paths newly failed to parse,
    four of them at paths the rewrite does not remove."""
    import ast

    if not _applied_content:
        pytest.skip("no surviving content blobs to check")

    offenders: dict[str, tuple[str, ...]] = {}
    for blob_id, (original, redacted) in _applied_content.items():
        if redacted == original:
            continue
        paths = _blob_paths.get(blob_id, frozenset())
        if not any(path.endswith(".py") for path in paths):
            continue
        try:
            ast.parse(original)
        except SyntaxError:
            continue  # already unparseable before the rules ran; not this claim
        try:
            ast.parse(redacted)
        except SyntaxError as exc:
            offenders[blob_id] = (str(exc), *sorted(paths))
    assert not offenders, f"newly unparseable .py blob(s): {offenders}"


def _head_blob_ids() -> tuple[str, ...]:
    """Every blob id reachable from the `HEAD` tree only -- deliberately
    narrower than `enumerate_blob_ids` (which walks every ref's full
    history). Invariant 6 is about the **tip**, not the whole object
    database; scanning history here would silently widen the check past
    what task 6.4 actually claims."""
    listed = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "ls-tree", "-r", "--name-only", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    checked = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "cat-file", "--batch-check=%(objectname)"],
        input="\n".join(f"HEAD:{path}" for path in listed if path) + "\n",
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return tuple(
        sorted({line.strip() for line in checked.splitlines() if line.strip()})
    )


def test_invariant_6_tip_no_op(_built_rules: tuple[ReplacementRule, ...]) -> None:
    """Applying the rules to every blob at HEAD changes nothing -- true only
    because task 6.3 emptied the tip of forbidden values, and the cheapest
    available proof the rules are scoped correctly."""
    changed: dict[str, str] = {}
    for blob_id in _head_blob_ids():
        original = read_blob_text(_REPO_ROOT, blob_id)
        updated = apply_rules(original, _built_rules)
        if updated != original:
            changed[blob_id] = updated
    assert not changed, (
        f"invariant 6 (tip no-op) violated -- {len(changed)} blob(s) changed: "
        f"{sorted(changed)[:10]}"
    )


def test_invariant_6_tip_no_op_over_the_working_tree(
    _built_rules: tuple[ReplacementRule, ...],
) -> None:
    """Invariant 6 at the **prospective** tip: the same claim, measured over
    every tracked file's working-tree text rather than `HEAD`'s blobs.

    The test above cannot see an edit that has not been committed yet, so it
    reports the tip one commit behind the session making it -- and the change
    that most easily violates invariant 6 is a session pasting a notice, an
    address or a token into a spec file, a queue item or a test fixture, which
    stays uncommitted for exactly as long as it takes to run the suite and
    believe it. Task 6.5 hit this directly: adding the notice rules turned
    five already-tracked files (this spec's own `requirements.md` and
    `tasks.md`, and three queue items, every one of which quoted the notice
    while discussing it) into tip blobs the rule set rewrites."""
    changed: dict[str, int] = {}
    texts = _tracked_text_files()
    assert len(texts) > 100, (
        f"the walk is looking at the wrong directory -- {len(texts)} files"
    )
    _assert_unreadable_set_is_known()

    # Req 3.3: the rule set demonstrably rewrites a genuinely present notice
    # in this same run, in both the flat and the comment-wrapped shape, before
    # the absence claim below means anything.
    for control in (
        f"a notice: {_NOTICE_PHRASE}.",
        "# {}\n# {}".format(*_NOTICE_PHRASE.rsplit(" ", 1)),
        f"the {_TRADEMARK_MARK} mark",
    ):
        assert apply_rules(control, _built_rules) != control, control

    for name, original in texts.items():
        updated = apply_rules(original, _built_rules)
        if updated != original:
            changed[name] = sum(
                1 for a, b in zip(original, updated, strict=False) if a != b
            )
    assert not changed, (
        "invariant 6 (tip no-op) violated in the WORKING TREE -- the rule set "
        f"rewrites {len(changed)} tracked file(s): {sorted(changed)}"
    )


# =============================================================================
# Acceptance: the copyright notice and the trademark mark over the whole
# reachable corpus (task 6.5, Req 11.4 -- unconditional over every commit).
#
# These scan EVERY reachable blob, not `_applied_content`'s
# `literal_replaceable` subset: a blob can carry the notice and no identifying
# token at all (a quotation of the notice with the name already redacted is
# exactly that shape, and there are such blobs), so the plan-derived
# population would silently miss them.
# =============================================================================


@pytest.fixture(scope="module")
def _whole_corpus(
    _built_rules: tuple[ReplacementRule, ...],
) -> dict[str, tuple[str, str]]:
    """`blob_id -> (original, redacted)` for every reachable blob, read in one
    batched `git cat-file` rather than one subprocess per blob."""
    from scripts.purge.plan import enumerate_blob_ids
    from scripts.purge.replacements import _batch_blob_texts

    blob_ids = enumerate_blob_ids(_REPO_ROOT)
    texts = _batch_blob_texts(_REPO_ROOT, blob_ids)
    return {
        blob_id: (text, apply_rules(text, _built_rules))
        for blob_id, text in texts.items()
    }


def test_acceptance_zero_surviving_notice_phrase_or_trademark_mark(
    _whole_corpus: dict[str, tuple[str, str]],
    _applied_commit_messages: dict[str, tuple[str, str]],
) -> None:
    """Req 11.4's own observable: after the full rule set, no reachable blob
    and no reachable commit message carries the reserved-rights phrase or the
    trademark mark.

    The positive control is the first half of this test, not an afterthought:
    a corpus that never held them would pass the second half for free."""
    populations = (("blob", _whole_corpus), ("commit", _applied_commit_messages))

    before = sum(
        _count_notice_phrase(original) + original.count(_TRADEMARK_MARK)
        for _label, population in populations
        for original, _redacted in population.values()
    )
    if before == 0:
        # After task 7.2 this population is empty BY CONSTRUCTION: the rewrite
        # removes every notice from every reachable object, so the positive
        # control below can no longer be satisfied and the survivor check
        # becomes vacuous rather than false. Skip, loudly and by name -- the
        # same posture every pre-existing invariant test in this file takes
        # when its population empties, rather than a green pass that would
        # read as evidence.
        pytest.skip(
            "no reachable object holds the notice -- expected only after "
            "task 7.2's rewrite; nothing left for this check to measure"
        )
    assert before > 40, (
        "the corpus under test holds only "
        f"{before} notice occurrence(s) -- too few for the survivor check "
        "below to mean anything, and not the empty post-rewrite state either"
    )

    survivors: dict[str, tuple[int, int]] = {}
    for label, population in populations:
        for object_id, (_original, redacted) in population.items():
            counts = (
                _count_notice_phrase(redacted),
                redacted.count(_TRADEMARK_MARK),
            )
            if any(counts):
                survivors[f"{label}:{object_id}"] = counts
    assert not survivors, (
        "Req 11.4 violated -- (phrase, mark) counts surviving the rule set: "
        f"{survivors}"
    )


def test_acceptance_unrelated_copyright_population_is_untouched(
    _whole_corpus: dict[str, tuple[str, str]],
    _applied_commit_messages: dict[str, tuple[str, str]],
) -> None:
    """The dominant hazard of task 6.5, measured rather than argued.

    The bare copyright sign occurs in the hundreds across dozens of paths and
    the word `copyright` in the hundreds more -- licence headers, packaging
    metadata and this spec's own prose about the notice. The rules are keyed
    on the phrase, so every object that does not carry the phrase must come
    through with its sign count and its `copyright` count unchanged. This is
    the check that would have caught a rule keyed on the sign or the word,
    which is irreversible over-redaction in a one-shot rewrite."""
    sign = "©"
    populations = (("blob", _whole_corpus), ("commit", _applied_commit_messages))

    unrelated_signs = 0
    unrelated_objects = 0
    offenders: dict[str, tuple[int, int, int, int]] = {}
    for label, population in populations:
        for object_id, (original, redacted) in population.items():
            if _count_notice_phrase(original):
                continue
            unrelated_objects += 1
            unrelated_signs += original.count(sign)
            counts = (
                original.count(sign),
                redacted.count(sign),
                original.lower().count("copyright"),
                redacted.lower().count("copyright"),
            )
            if counts[0] != counts[1] or counts[2] != counts[3]:
                offenders[f"{label}:{object_id}"] = counts
    if not unrelated_signs:
        pytest.skip(
            "no reachable object carries a copyright sign -- nothing left "
            "for this check to measure"
        )
    assert unrelated_signs > 100, (
        "the unrelated copyright-sign population is too small for this check "
        f"to mean anything ({unrelated_signs} signs in {unrelated_objects} "
        "objects)"
    )
    assert not offenders, (
        "objects with no notice lost a copyright sign or the word copyright "
        "(id -> signs before/after, words before/after): "
        f"{offenders}"
    )


def test_acceptance_no_object_loses_more_signs_than_it_has_notices(
    _whole_corpus: dict[str, tuple[str, str]],
    _applied_commit_messages: dict[str, tuple[str, str]],
) -> None:
    """The other half of the same claim, for the objects that DO carry the
    notice: a notice removes at most the one mark standing in front of it, so
    no object may lose more signs than it has phrase occurrences. An
    over-reaching body pattern shows up here as a blob that lost signs it had
    no notices for."""
    sign = "©"
    populations = (("blob", _whole_corpus), ("commit", _applied_commit_messages))

    removed_total = 0
    notices_total = 0
    offenders: dict[str, tuple[int, int]] = {}
    for label, population in populations:
        for object_id, (original, redacted) in population.items():
            notices = _count_notice_phrase(original)
            if not notices:
                continue
            removed = original.count(sign) - redacted.count(sign)
            removed_total += removed
            notices_total += notices
            if removed > notices or removed < 0:
                offenders[f"{label}:{object_id}"] = (removed, notices)
    if not notices_total:
        # Empty by construction after task 7.2 -- see the sibling test.
        pytest.skip(
            "no reachable object carries the notice -- expected only after "
            "task 7.2's rewrite; nothing left for this check to measure"
        )
    assert removed_total > 0, (
        "not one copyright sign was removed anywhere -- the prefixed notice "
        "rule is not firing, and every notice is keeping its mark"
    )
    assert not offenders, (
        "object(s) lost more copyright signs than they have notices "
        f"(id -> (signs removed, notices)): {offenders}"
    )


# =============================================================================
# Acceptance: the identity denylist is clone-independent (task 6.4 remediation,
# `.kiro/queue/2026-08-10-6-4-identity-derivation-guard-unsatisfiable.md`).
#
# The queue item's "Done when" is that `identity_leak_addresses` returns the
# same real addresses in this working repository, in a `git clone --mirror`
# of it and in a `git clone --no-local` of it. Every address below is named by
# a masked SHA-256 tag or by a set relation -- never by value, and never
# counted from a hard-coded list of literals.
#
# IF YOU ADD AN ACCEPTANCE ASSERTION HERE, MASK THE OPERANDS THEMSELVES.
# Supplying an explicit assertion message is NOT enough and does not suppress
# anything: verified by execution, pytest's assertion rewriting prints BOTH
# operands of a failing `==` or `<=` in full even when a message is given, so
# `assert derived == expected, "..."` over real addresses puts them verbatim
# into pytest output, CI logs and any review report quoting them. Map to
# `_masked(...)` on both sides first, then compare -- that is what every
# assertion below does.
# =============================================================================


def _unreachable_commit_ids(repo: Path) -> frozenset[str]:
    """Every commit object `repo`'s LOCAL object database physically holds
    that is reachable from no ref -- `git cat-file --batch-all-objects
    --batch-check` (which sees every object on disk) minus `git rev-list
    --all` (which sees only the reachable ones). This is exactly the
    population `_orphaned_commit_identity_addresses` reads, measured
    independently of it so it can serve as that function's precondition."""
    checked = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "cat-file",
            "--batch-all-objects",
            "--batch-check=%(objectname) %(objecttype)",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    all_commits = {
        line.split(" ", 1)[0]
        for line in checked.splitlines()
        if line.endswith(" commit")
    }
    return frozenset(all_commits - _reachable_ids(repo))


def _clone(source: Path, destination: Path, *flags: str) -> Path:
    """`git clone` `source` into `destination`. Read-only with respect to
    `source`: no maintenance command is ever run against a clone in this
    file, because a same-filesystem clone hardlinks its source's object
    directory."""
    subprocess.run(
        ["git", "clone", "--quiet", *flags, str(source), str(destination)],
        check=True,
        capture_output=True,
    )
    return destination


@pytest.fixture(scope="module")
def _real_tokens() -> tuple[str, ...]:
    return load_tokens(require(_REPO_ROOT).source)


@pytest.fixture(scope="module")
def _real_denylist(_real_tokens: tuple[str, ...]) -> tuple[str, ...]:
    from scripts.purge.replacements import identity_leak_addresses

    return identity_leak_addresses(_REPO_ROOT, _real_tokens)


def test_identity_denylist_is_exactly_the_leaks_the_tip_does_not_hold(
    _real_tokens: tuple[str, ...], _real_denylist: tuple[str, ...]
) -> None:
    """The real corpus holds exactly THREE identity-leak addresses: the third
    party's contact address (whose domain carries their surname token), the
    maintainer's personal mailbox, and git's constructed machine identity.
    Every other email-shaped `.local` string reachable in this history is
    this suite's own fixture or a documented shape, and every one of those is
    present at the tip.

    Asserting the exact count is what stops this passing on a superset -- the
    scan finds SEVEN candidates, and an implementation that returned
    everything it found (the pre-remediation shape of the union) would
    satisfy any "contains at least the real ones" assertion. Asserting that
    the tip-present candidates are ABSENT is what stops it passing on the
    sanctioned ones specifically.

    Mutations: dropping `_absent_from_tip` from the union reds the count
    and the
    disjointness; returning `candidates` alone (dropping `token_domain`) reds
    the count and the token-domain membership assertion."""
    from scripts.purge.replacements import (
        _reachable_identity_leak_candidates,
        _tip_tree_addresses,
        _token_domain_addresses,
    )

    candidates = frozenset(_reachable_identity_leak_candidates(_REPO_ROOT))
    tip = _tip_tree_addresses(_REPO_ROOT)
    token_domain = frozenset(_token_domain_addresses(_REPO_ROOT, _real_tokens))
    sanctioned = candidates & tip

    # Reachability: the sanctioned population is genuinely non-empty, so the
    # disjointness assertion below is not vacuous.
    assert len(sanctioned) >= 5, (
        "expected the tip to still hold several email-shaped fixture and "
        f"documented-shape addresses; found {len(sanctioned)}. Measured 5 "
        "at the time of writing (of 7 candidates); this is a LOWER bound "
        "deliberately, because the population only grows as this suite "
        "gains fixtures. If a change ever DID remove an email-shaped string "
        "from the tip, the assertion that reds is the count assertion "
        "below, not the tip-disjointness one and not this one: the address "
        "becomes tip-ABSENT, so it joins the denylist and the count moves "
        "off 3, while `denylist & tip` stays empty precisely because it is "
        "no longer at the tip"
    )
    # ...and the token-domain source genuinely contributes exactly one.
    assert len(token_domain) == 1

    # Every relation below is asserted over MASKED TAG SETS rather than over
    # the addresses. pytest's assertion rewriting prints the operands of a
    # failing comparison in full, and these are precisely the assertions
    # that fire when the derivation regresses -- an unmasked operand would
    # put the real addresses into pytest output, CI logs and any review
    # report quoting them, which is the whole reason `_masked_address`
    # exists. Set relations are preserved as long as the mapping is
    # injective over this population (8 hex characters, well under 50
    # distinct values, so a collision is ~1e-7 and would be visible as a
    # tag appearing twice). The honest limit: a collision is NOT harmless
    # in one direction -- if an unexplained address collided with a
    # candidate's tag, the two subset assertions below would pass where the
    # unmasked comparison would have failed. That is accepted deliberately
    # here, at that probability, against the certainty of printing a real
    # address every time one of these assertions fires. Verified by
    # execution that the printing is real: pytest's rewriting prints both
    # operands of a failing `<=` or `==` IN FULL, and supplying an explicit
    # message does not suppress it.
    denylist_tags = {_masked(a) for a in _real_denylist}
    token_domain_tags = {_masked(a) for a in token_domain}
    candidate_tags = {_masked(a) for a in candidates}
    tip_tags = {_masked(a) for a in tip}
    sanctioned_tags = {_masked(a) for a in sanctioned}

    assert len(_real_denylist) == 3, (
        f"expected exactly the three real identity leaks; got "
        f"{sorted(denylist_tags)} (masked SHA-256 tags)"
    )
    assert token_domain_tags <= denylist_tags, (
        "the token-corroborated address must be in the denylist; "
        f"missing {sorted(token_domain_tags - denylist_tags)}"
    )
    assert not (denylist_tags & sanctioned_tags), (
        "a tip-present (therefore sanctioned) candidate reached the "
        f"denylist: {sorted(denylist_tags & sanctioned_tags)}"
    )
    assert not (denylist_tags & tip_tags), (
        "the denylist must hold nothing the tip holds -- this is the "
        "MEASUREMENT of the one thing `identity_leak_addresses` establishes "
        "by construction: tip-disjointness AS A SET OF CASE-FOLDED "
        "_EMAIL_SHAPE TOKENS (guard 2 plus the `_absent_from_tip` filter). "
        "It does NOT establish that the identity rule leaves every tip blob "
        "alone -- the rule matches substrings, this compares whole tokens "
        "-- and it is not a measurement of invariant 6 for the rule set as "
        "a whole either, since the per-token tiers are not derived from the "
        "tip at all. `test_invariant_6_tip_no_op` is what covers both of "
        f"those. Offending tags: {sorted(denylist_tags & tip_tags)}"
    )
    assert denylist_tags <= (candidate_tags | token_domain_tags), (
        "the denylist must come from the two reachability-independent "
        "sources; unexplained "
        f"{sorted(denylist_tags - candidate_tags - token_domain_tags)}"
    )


def _masked(address: str) -> str:
    from scripts.purge.replacements import _masked_address

    return _masked_address(address)


@pytest.mark.parametrize(
    "flags,orphans_expected",
    [
        (("--mirror",), "same as source"),
        (("--no-local", "--bare"), "none"),
    ],
    ids=["mirror", "no-local"],
)
def test_identity_denylist_is_identical_in_a_clone(
    tmp_path: Path,
    flags: tuple[str, ...],
    orphans_expected: str,
    _real_tokens: tuple[str, ...],
    _real_denylist: tuple[str, ...],
) -> None:
    """The queue item's "Done when", proven rather than reasoned.

    `--no-local` is the clone design.md `#### HistoryRewrite` step 3 and
    tasks.md 7.2 prescribe, and it transfers only REACHABLE objects -- the
    exact condition under which the pre-remediation guard raised
    unconditionally. `--mirror` defaults to a local, object-directory-
    hardlinking clone, so it carries whatever unreachable objects the source
    has.

    Both preconditions are asserted rather than assumed: without them a clone
    that silently failed to be the kind of clone it is named after would pin
    nothing at all. No maintenance command is ever run against either clone
    (`_clone`'s docstring says why)."""
    clone = _clone(_REPO_ROOT, tmp_path / "clone.git", *flags)

    # Reachability: this really is the kind of clone this case is named for.
    unreachable = _unreachable_commit_ids(clone)
    if orphans_expected == "none":
        assert unreachable == frozenset(), (
            "a --no-local clone must carry no unreachable commit object at "
            f"all; found {len(unreachable)}"
        )
    else:
        assert unreachable == _unreachable_commit_ids(_REPO_ROOT), (
            "a --mirror clone must carry exactly the source's unreachable "
            "commit population"
        )
    # ...and it really is at the same tip, so the tip-absence partition is
    # being asked the same question.
    assert (
        subprocess.run(
            ["git", "-C", str(clone), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )

    from scripts.purge.replacements import identity_leak_addresses

    # Masked on both sides for the same reason as the sibling acceptance
    # test above: a failing equality would otherwise print both tuples of
    # real addresses in full.
    clone_tags = tuple(_masked(a) for a in identity_leak_addresses(clone, _real_tokens))
    source_tags = tuple(_masked(a) for a in _real_denylist)
    assert clone_tags == source_tags
    # Falsity in the starting state guard: an empty result would satisfy the
    # equality above only if the working repository also derived nothing.
    assert len(_real_denylist) == 3
