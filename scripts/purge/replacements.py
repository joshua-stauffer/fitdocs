"""The `--replace-text` / `--replace-message` rule generator for task 7.2's
one-shot history rewrite (task 6.4, design.md `#### HistoryRewrite`, Req
3.3, 3.4, 11.1, 11.2, 11.8).

**Why this module exists and why it is not `rewrite.py`'s
`build_replacement_expressions`.** That function hard-codes an inline
`(?i)` flag on every emitted `regex:` line. Under case-insensitivity a `The
<token>` rule and a `the <token>` rule are the same rule, so whichever is
listed first wins for *both* cases -- there is no way to phrase two rules
that land "The" at a sentence start and "the" mid-sentence. Measured on the
real corpus at commit `3cfe28e`: a case-insensitive rule set satisfies every
other invariant below and fails invariant 5 with 36 sentence-start
lowercasings. This module is the deliberate departure: it emits
**case-sensitive** `regex:` lines (no `(?i)`) and pays for the lost
insensitivity with one rule per **observed case variant** of each token,
scanned from the real object database rather than assumed.

**Never a forbidden value in this file.** Every literal token string this
module's rules are built from is read at run time from the file
`tests._forbidden_strings.ForbiddenStrings` loads (named by
`FITDOCS_FORBIDDEN_STRINGS`) and from the historical object database the
caller points at -- never typed into this module's source. What *is* typed
into this module's source is the **replacement** vocabulary (`_THIRD_PARTY`,
`_WITHDRAWN_METHODOLOGY`, `_WITHDRAWN_ADJECTIVE`), which is token-free by
construction: none of it is a proper noun, and design.md
`#### IdentityErasure`'s vocabulary table is where the prose forms come
from. `identity_email_rule`'s denylisted addresses are likewise never typed
in -- see `identity_leak_addresses` below, and the trap note two paragraphs
down.

**A needle this module matches is never spelled contiguously in it
either**, for a different reason and with a different remedy. The
reserved-rights phrase and the trademark mark (task 6.5) are not forbidden
values -- they name nobody, which is why no matcher in this repository
flags them -- but they ARE matched by rules this module emits, and this
file is a tracked blob at the tip where invariant 6 requires the rule set
to be a no-op. So the phrase lives as a word tuple assembled at run time
(`_NOTICE_PHRASE_WORDS` / `notice_phrase`), the mark as a `\\u2122` escape,
and the copyright sign appears in patterns only as `\\u00a9`. The same
constraint binds this module's test suite and every spec file that
discusses the work. `_NOTICE_PHRASE_WORDS`, `_TRADEMARK_MARK` and
`_COPYRIGHT_SIGN` are imported from `tests._forbidden_strings` (task 7.2,
design.md `#### MachineryRetirement` Phase R0), which is also where the
standing guard now lives:
`tests/test_forbidden_strings.py::
test_the_notice_phrase_and_mark_are_absent_from_every_tracked_file`.

**The allowlist-to-denylist trap, recorded so it is not repeated a third
time.** `identity_email_rule` was originally a negative-lookahead allowlist:
redact any email whose domain was NOT on a short curated list of
known-placeholder domains. That is exactly backwards for a module whose own
test suite is full of synthetic email-shaped fixtures on made-up domains --
an in-repo fixture that merely *looks* like the thing being redacted gets
redacted by a broad allowlist-based rule, because nothing about "not on the
safe list" can distinguish "an unlisted real leak" from "an unlisted
fixture". This bit twice: once for a single fixture hostname (never quoted
here; it lives in `tests/purge/test_sweep.py`), patched by adding it to the
list -- whack-a-mole against every future fixture domain -- and again for
four more fixture addresses at once, only
discovered once `tests/purge/test_replacements.py` itself was first
committed to `HEAD` -- invariant 6 (the tip no-op) can only see a *tracked*
blob, so a fixture added in the same commit as a production change is
invisible to it locally and only fails once that commit lands. The fix
(`identity_leak_addresses`) is a denylist of the specific addresses this
corpus actually contains, derived at run time from THREE independent sources
that all need no literal address typed in: a token-domain match
(`_token_domain_addresses`), a reachable-vs-all commit-identity diff
(`_orphaned_commit_identity_addresses`), and a reachable-blob-TEXT scan
(`_reachable_identity_leak_candidates`). Two of those three sources
CONFIRM rather than merely match a shape -- a forbidden token inside an
address's own domain, and an author/committer header on an unreachable
commit -- but they are not equally unfakeable, and the difference matters.
The orphan-commit source genuinely cannot be imitated from inside a blob:
nothing a file's CONTENT says makes it a commit's author header.
`_token_domain_addresses` CAN be imitated -- this suite's own token-domain
fixture is exactly that, an ordinary blob holding an address whose domain
carries a token -- and what keeps that from happening in the real corpus is
a different mechanism entirely: the standing forbidden-string guard, which
keeps identifying tokens out of tracked files **at the tip**, so no file at
the tip can hold a token-carrying address to be found. Note the scope
carefully. That guard is a tip-only invariant, while
`_token_domain_addresses` scans every REACHABLE blob, and the real
token-carrying address is found at 5 historical sites. So the invariant
prevents a NEW fixture being confirmed; it does not and cannot stop history
supplying token-carrying addresses, which is the entire reason this source
finds anything at all. It is an external invariant this module relies on,
not a property of the match itself.
The third source matches a shape and therefore does find fixtures: measured
on this corpus, 5 of its 7 matches are this suite's own synthetic fixtures
or documented shapes. Those are separated out by tip-presence rather than
by being unfindable, which is what the tip-absence paragraph below is for.
"Derived from what is present" is what stops the denylist eating an
UNRELATED address; it is not on its own what stops it eating a fixture.

**The reachability trap, recorded so it is not repeated either. This
paragraph describes a defect that HAS BEEN FIXED -- it is history, not
current behaviour; for what the module does now see the polarity-correction
paragraph below and `build_rules`'s own docstring.**
`_orphaned_commit_identity_addresses` depends on unreachable commit objects
physically existing in the object database it is handed. Measured at the
time across four repository states derived from the same history: a working
repository and a same-filesystem `git clone --mirror` (which hardlinks the
whole object directory, unreachable objects included) both found all 3 real
addresses; a `git clone --no-local` -- exactly what design.md
`#### HistoryRewrite` step 3 and tasks.md 7.2 prescribe for the actual
rewrite -- and a repository that had had `git reflog expire --expire=now
--all` followed by `git gc --prune=now` run against it both found only 1
(the token-domain address; `_orphaned_commit_identity_addresses` returned
nothing, because the unreachable commit objects it reads were simply gone
from the database, not merely absent from any ref). Nothing about that
raised: an empty tuple is a valid, non-error result, `identity_email_rule`
degraded to a shorter alternation, and it still compiled and matched
something. `build_rules` handed the `--no-local` clone tasks.md 7.2 itself
creates would then silently have shipped a denylist missing two of three
real addresses, permanently, into the one-shot rewrite's `--replace-text`
input. **That is no longer the case: all three repository states are now
measured to derive the identical denylist**, pinned by
`tests/purge/test_replacements.py::test_identity_denylist_is_identical_in_a_clone`,
which builds a real `--mirror` and a real `--no-local` clone and compares.

The fix is not a guard on `_orphaned_commit_identity_addresses` (there is
nothing left in a pruned database for a guard to find) but a THIRD source
that never depends on unreachable commit objects at all:
`_reachable_identity_leak_candidates` scans reachable blob TEXT -- the same
reachable-only enumeration every other function in this module already uses,
across every historical version of every path, not only the tip -- for the
shapes the two real orphan-derived addresses are independently measured to
also appear as (an "old address -> safe alias" rewrite-map mapping, and
git's own `NAME-at-HOST.local` auto-identity form).

**The polarity correction, and the tip-absence rule.** The first attempt at
that fix made the orphan source the AUTHORITY -- it raised whenever the
blob-text scan named an address the orphan diff could not corroborate. That
guard is unsatisfiable: a fresh clone carries no unreachable objects at all,
and neither does a pruned repository, so it raised unconditionally and red
nine acceptance tests. The two reachability-independent sources are now
primary and the orphan source became a CHECKING source: it contributes
nothing to the denylist (the guards make that impossible) and is consulted
only to raise. What separates a real leak from
this suite's own synthetic fixtures -- both of which the blob-text scan
finds, because both are the same shape -- is **tip-absence**: a candidate
present in the tip tree (`_tip_tree_addresses`) is sanctioned, a candidate
absent from it is a leak. Task 6.3 emptied the tip of every forbidden value,
so the tip IS the purge's clean target state. Together with a guard that
refuses to return when a CONFIRMED address (token-corroborated or
orphan-derived) is at the tip, this makes the identity denylist
**tip-disjoint by construction, AS A SET OF CASE-FOLDED `_EMAIL_SHAPE`
TOKENS** -- and that is the whole of what construction buys. It does NOT
follow that the identity rule cannot touch a tip blob: the rule matches
SUBSTRINGS while the sanction compares whole tokens, so the two are not
asking the same question, and closing that gap on one axis at a time has
already cost three review rounds (case folding, then substring anchoring).
The tip no-op is a MEASUREMENT -- `test_invariant_6_tip_no_op` -- for the
identity rule as much as for every other rule the generator emits, and the
per-token tiers are derived from the token list rather than from the tip, so
nothing about them was ever structural either. That rule
supersedes an earlier `tests/` path-prefix scope, which was an ad-hoc path
allowlist and which this very module's docstring defeated by quoting its own
test fixtures by value at a `scripts/` path. `identity_leak_addresses`
raises only on the
two genuine inconsistencies -- see its own docstring -- and every address in
every diagnostic is masked through `_masked_address`, never printed.

**Scope is the token category, not the path category.** `--replace-text`
also sees removed-path-fragment matches (`ForbiddenStrings.values` does not
distinguish -- category is metadata `sweep.py::CategorizedEntry` carries and
`tests._forbidden_strings` discards). This module reads the categorized
form and only ever builds rules from `category == "token"` rows. Path
fragments are `RedactionPlan`'s and `build_path_directives`'s job (whole-path
removal/rename), and task 8.3 already states, as a declared correction, that
a *textual mention* of a token-free path fragment inside some other file's
historical blob is explicitly not a completeness requirement of this
rewrite (Req 9.7.7 governs the working tree; Req 11.2 governs paths that
themselves carry a token) -- so there is no gap this module is silently
leaving for the path category to have covered.

**The ordering tiers, applied to every historical blob in the same
relative order this module emits them (git-filter-repo's own
`apply_replace_text` runs every `regex:` line's `re.sub` in file order,
each seeing the previous line's output -- verified by reading
`git_filter_repo.py::ContentCallback.apply_replace_text`, not assumed).**
Longest token first throughout, so a multi-word phrase is fully consumed
before any of its component words gets a rule of its own -- otherwise a
1-word rule for the surname would fire on a piece of the 3-word
methodology-name phrase before the 3-word rule ever ran (measured: a
methodology-name phrase wrapped across a line, e.g. "a *Surname* *Point*
*System* zone", is invisible to a same-line 3-word pattern but matches a
1-word surname-only pattern first if the 1-word rule runs first -- this
docstring never spells out the real surname or methodology name; see
`tests/purge/test_replacements.py` for the same hazard pinned against a
synthetic token shaped the same way).

1. *Given-name exception phrases* (only for the multi-word "full name"
   token). The given name is deliberately never its own token -- see the
   module-level `given_name_rules` docstring for why -- so its only two real
   uses in all of history are targeted by two narrow, context-bearing
   patterns rather than a bare-word rule.
2. *Denylisted identity-leak email address*, one rule, built from
   `identity_leak_addresses` -- the specific addresses this corpus is
   measured to actually contain, never a domain allowlist (see the trap
   note above and `identity_email_rule`'s own docstring).
3. Per multi-to-single-word token, per observed case variant:
   a. *definite-article guard* (`the `/`The ` immediately before) --
      replaces the token with the **bare** noun phrase, because the
      article is already there; skipping this guard is exactly how "the
      the" appears (measured: 781 real occurrences of `the`/`The` directly
      before one of these four tokens).
   b. *indefinite-article guard* (`a `/`A `/`an `/`An ` immediately before)
      -- replaces the token with the bare adjective `withdrawn`, and
      **normalises the article to `a`/`A`** regardless of which of the four
      forms preceded it, because `withdrawn` starts with a consonant sound
      and `an withdrawn` is the `an_withdrawn` mangled form invariant 4
      names. Measured: 98 real adjectival occurrences (a surname or an
      abbreviation used attributively, e.g. "a *Surname* symbol", "an
      *Abbreviation* result").
   c. *sentence-start guard* (`[.!?]\\s`, or the very start of the blob,
      immediately before) -- replaces the token with the capitalised
      sentence-shaped replacement, so a sentence beginning with the token
      does not lowercase.
   c2. *dotted module path guard* (an immediately preceding literal `.`,
      asserted by a zero-width lookbehind -- a single literal character is
      always fixed-width, unlike tiers (a)/(c)'s whitespace runs, so a
      lookbehind is safe here) -- replaces the token with the
      case-matched bare adjective, never the sentence-shaped phrase.
      Fixes design.md `#### IdentityErasure`'s own vocabulary table:
      *"the lower-case module segment of that dotted module path, wherever
      the path appears in a code span"* becomes `withdrawn`, giving
      `fitdocs.load.withdrawn`. Ordered **before** tier (d) deliberately:
      `.` is a non-word character, so tier (d)'s plain `\\b`-anchored rule
      also matches immediately after a dot and would win first if this
      tier came later, producing `fitdocs.load.the third party` --
      measured in a real rewritten repository: 59 blobs carried that
      exact mangled path, 15 blobs across 12 distinct paths newly failed
      `ast.parse`, four of them at paths the rewrite does not remove.
   d. *general* -- replaces every remaining `\\b`-bounded occurrence with
      the lowercase sentence-shaped (or bare-adjective, for the
      abbreviation family... no: every family uses the sentence-shaped
      lowercase form here) replacement.
   e. *identifier mop-up*, **unanchored** (no `\\b`), in three sub-passes
      (an `an_`/`An_`/`AN_`-prefix normalisation, a trailing `-ed`-suffix
      consumption, then the plain unanchored form) -- catches the token
      embedded in a Python identifier, where `_` being a word character
      means no `\\b`-bounded rule above can ever match (the same hazard
      `rewrite.py`'s own docstring names for commit messages). Replaces
      with the bare adjective, case-matched to the **observed case variant
      itself**, not inferred from the surrounding identifier's own
      convention (`_case_matched_adjective`): a title-case variant
      (`Surname`) embedded inside a CamelCase class name becomes title-case
      `Withdrawn` (`WithdrawnCalculator`), a lower-case variant embedded in
      a local or string value becomes lower-case `withdrawn`, and an
      **all-caps** variant (an acronym token, e.g. `FBC`) embedded inside a
      CamelCase identifier stays all-caps `WITHDRAWN` (`WITHDRAWNCalculator`,
      not `WithdrawnCalculator` -- measured: ×13 in the rewritten repository)
      -- independently the exact replacement design.md
      `#### IdentityErasure` already fixed for the equivalent identifiers
      in the tree.

4. *Copyright-notice rules* (`notice_rules`), per observed case variant of
   the reserved-rights phrase, longest match first: the whole notice (mark,
   attribution and phrase), then the phrase behind an indefinite article
   (normalised to `a`, the same fix tier (b) makes for `an <adjective>`),
   then the bare phrase. Emitted **after** every
   token tier, so the attribution the notice rule has to cross is already
   this module's own replacement vocabulary rather than an unknown name,
   and its width is therefore a measured constant. Task 6.5, Req 11.4;
   keyed on the phrase and never on the copyright sign or the word
   `copyright`, both of which are hundreds of unrelated occurrences.
5. *The trademark-mark rule* (`trademark_mark_rule`), always exactly one,
   deleting the mark outright.

Sub-tier (e) is why a shadowed-looking rule is not dead: tier (d) and tier
(e) both match the same bare surname or abbreviation in isolation, under
different anchoring, and deleting either -- reading them as duplicates --
silently drops either every prose occurrence (deleting d) or every
identifier occurrence (deleting e). This is the shape of the "shadowed
duplicate is not safe to delete" trap, generalised past the
case-preservation instance that first named it.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from tests._forbidden_strings import (
    _COPYRIGHT_SIGN,
    _NOTICE_PHRASE_WORDS,
    _NOTICE_WORD_SEPARATOR,
    _TRADEMARK_MARK,
    _whitespace_tolerant_pattern,
)

from scripts.purge.plan import enumerate_blob_ids, read_blob_text
from scripts.purge.sweep import (
    CategorizedEntry,
    entries_by_category,
    load_categorized_entries,
)

# `_whitespace_tolerant_pattern`, `_COPYRIGHT_SIGN`, `_TRADEMARK_MARK`,
# `_NOTICE_PHRASE_WORDS` and `_NOTICE_WORD_SEPARATOR` used to be DEFINED in
# this module. Moved to `tests/_forbidden_strings.py` (encumbered-content-
# purge task 7.2, design.md `#### MachineryRetirement` Phase R0): that module
# is a survivor of Req 12.1's retirement, this one is not, and the design
# mandates the dependency run `scripts/purge/` -> `tests/_forbidden_strings.py`
# -- never the reverse the pre-task-7.2 lazy import inside
# `tests/_forbidden_strings.py::_wrap_tolerant_pattern` used to carry. This is
# now the ONLY definition of any of the five; nothing below re-spells them.

# --- replacement vocabulary (token-free by construction) --------------------

_THIRD_PARTY = "the third party"
_THIRD_PARTY_CAP = "The third party"
_THIRD_PARTY_BARE = "third party"

_WITHDRAWN_METHODOLOGY = "the withdrawn methodology"
_WITHDRAWN_METHODOLOGY_CAP = "The withdrawn methodology"
_WITHDRAWN_METHODOLOGY_BARE = "withdrawn methodology"

_WITHDRAWN_ADJECTIVE = "withdrawn"
"""The bare adjective used after an indefinite article and as the base form
for the identifier mop-up. Matches design.md `#### IdentityErasure`'s
"lower-case module segment" replacement (`fitdocs.load.withdrawn`) and its
CamelCase class-symbol replacement (`WithdrawnCalculator`) once case-matched
-- see `_case_matched_adjective`."""

_REDACTED_EMAIL = "a redacted email address"

_ABBREVIATIONS_BEFORE_PERIOD: tuple[str, ...] = (
    "vs",
    "e.g",
    "i.e",
    "etc",
    "Mr",
    "Mrs",
    "Dr",
    "cf",
)
"""Words whose trailing period `[.!?]\\s+` cannot distinguish from a genuine
sentence end -- "vs. *Surname*'s implementation" (measured in the real
corpus) is not a new sentence, so tier (c)'s sentence-start guard must not
fire there; unguarded, it capitalises the token immediately after one of
these abbreviations (measured: 15 real sites, e.g.
`.kiro/steering/structure.md`, `.kiro/steering/tech.md`,
`.kiro/specs/fit-ingest/requirements.md`, all reading `(e.g. <token>)` and
becoming `(e.g. <Capitalised replacement>)`).

**This is the single canonical list**, guarding both sides of the same
claim: production code below excludes these abbreviations from the
sentence-start tier, and `tests/purge/test_replacements.py` imports this
exact tuple (never redefines it) to measure that the exclusion holds --
invariant 5's own false-positive list and the guard that keeps it a false
positive can no longer drift apart into two hand-maintained copies."""

_abbreviation_negative_lookbehind = "".join(
    rf"(?<!{re.escape(abbreviation)})" for abbreviation in _ABBREVIATIONS_BEFORE_PERIOD
)
"""One `(?<!...)` per abbreviation, chained rather than joined into a single
alternation -- `re` requires a fixed-width pattern *inside* one lookbehind,
and these abbreviations are not all the same length (`vs` is 2 characters,
`e.g` is 3, `etc` is 3, ...). Chaining N independent negative lookbehinds,
each individually fixed-width, sidesteps that restriction entirely and is
equivalent to "none of these abbreviations ends here". Each assertion is
anchored at the position immediately before the sentence-ending punctuation
tier (c) matches, so it inspects `...e.g` (the abbreviation itself, not the
following period or whitespace)."""

_FAMILIES: dict[str, tuple[str, str, str]] = {
    "third_party": (_THIRD_PARTY, _THIRD_PARTY_CAP, _THIRD_PARTY_BARE),
    "withdrawn_methodology": (
        _WITHDRAWN_METHODOLOGY,
        _WITHDRAWN_METHODOLOGY_CAP,
        _WITHDRAWN_METHODOLOGY_BARE,
    ),
}
"""`family -> (lowercase sentence-shaped, capitalised sentence-shaped, bare)`.
Both families collapse to the *same* bare adjective (`_WITHDRAWN_ADJECTIVE`)
for the indefinite-article guard and the identifier mop-up -- design.md's
vocabulary table gives the abbreviation the same replacement as the full
methodology name, and there is exactly one bare adjective in the whole
vocabulary, not one per family."""


# --- role assignment: index-keyed, not literal-value-keyed -------------------


@dataclass(frozen=True)
class _TokenRole:
    """One `FITDOCS_FORBIDDEN_STRINGS` `token`-category row's role, keyed by
    its position in the file -- the same `(category, index)` keying
    `_CONTENT_EXEMPT_VALUES` used (task 6.3's own remediation cites it) and
    for the same reason: the file's contents are read at run time and this
    module's source must never spell out which literal value occupies which
    row, only what role that row plays."""

    role: str
    family: str
    expected_word_count: int
    derive_given_name: bool = False


_TOKEN_ROLES: tuple[_TokenRole, ...] = (
    _TokenRole(
        role="full name (given + surname)",
        family="third_party",
        expected_word_count=2,
        derive_given_name=True,
    ),
    _TokenRole(role="surname alone", family="third_party", expected_word_count=1),
    _TokenRole(
        role="former proper name, in full",
        family="withdrawn_methodology",
        expected_word_count=3,
    ),
    _TokenRole(
        role="trademarked abbreviation",
        family="withdrawn_methodology",
        expected_word_count=1,
    ),
)
"""Fixed to the four token-category rows `FITDOCS_FORBIDDEN_STRINGS` holds
at the time this module was written (task 2.3's enumeration). `build_rules`
raises `ValueError` rather than guessing if the loaded token count ever
drifts from this -- this generator is a one-shot tool tied to one measured
shape, not a general-purpose one, and the "no task rests on a count" rule
(tasks.md's own execution rules) is about requirement coverage, not about
inventing role-inference heuristics for data this module was never asked to
generalise over.

**Count alone does not catch every reordering** (measured: reversing these
four rows keeps the count at 4 and silently scrambles the family mapping
instead of raising). `build_rules` therefore also checks each row's
`expected_word_count` against the loaded token's actual word count --
`(2, 1, 3, 1)` in file order. This catches a full reversal (which produces
`(1, 3, 1, 2)`, a mismatch at every position) and any drift that changes a
row's word count, without ever comparing against a literal token value.
It does **not** catch a swap between two rows of equal word count (the two
1-word rows, "surname alone" and "trademarked abbreviation"): that
residual gap is a known, accepted limitation of a word-count-shape check,
not a claim that ordering is fully verified."""


def load_tokens(forbidden_strings_path: Path) -> tuple[str, ...]:
    """Every `category == "token"` value from `forbidden_strings_path`, in
    file order -- never the `path` category (see the module docstring's
    "Scope is the token category" section)."""
    entries: Sequence[CategorizedEntry] = load_categorized_entries(
        forbidden_strings_path
    )
    return entries_by_category(entries).get("token", ())


# --- rule representation ------------------------------------------------------


@dataclass(frozen=True)
class ReplacementRule:
    """One `regex:PATTERN==>REPLACEMENT` line. `pattern` is already a
    complete, case-sensitive regular expression (never wrapped in `(?i)`)
    -- built by this module's functions, never hand-authored. `kind` and
    `token_role` are audit metadata only: they are never written to the
    rendered rule file, only to the masked review table (`render_masked_table`),
    so a reviewer can see *what* each rule is and in *what order* without the
    pattern ever reproducing the value it matches."""

    pattern: str
    replacement: str
    kind: str
    token_role: str


def render_rules(rules: Sequence[ReplacementRule]) -> str:
    """Render `rules` as `git filter-repo --replace-text` /
    `--replace-message` input, in the given order -- order is significant
    and is never re-sorted here (see the module docstring's ordering
    tiers)."""
    lines = [f"regex:{rule.pattern}==>{rule.replacement}" for rule in rules]
    return "\n".join(lines) + ("\n" if lines else "")


def render_masked_table(rules: Sequence[ReplacementRule]) -> str:
    """A reviewable rendering that never reproduces a rule's `pattern` --
    only its position, `token_role`, `kind`, the pattern's length (a shape,
    not a value), and its (token-free) `replacement`. This is what task
    6.4's "render the rule set with every token masked" observable is:
    reviewing the *order and structure* of the ruleset without the reviewer
    ever having the literal forbidden text put in front of them."""
    header = "index\ttoken_role\tkind\tpattern_length\treplacement"
    lines = [header]
    for index, rule in enumerate(rules):
        lines.append(
            "\t".join(
                (
                    str(index),
                    rule.token_role,
                    rule.kind,
                    str(len(rule.pattern)),
                    rule.replacement,
                )
            )
        )
    return "\n".join(lines) + "\n"


# --- case-variant discovery ---------------------------------------------------
#
# `_whitespace_tolerant_pattern` moved to `tests/_forbidden_strings.py` (task
# 7.2) and is imported at module scope above.


def observed_case_variants(repo: Path, phrase: str) -> tuple[str, ...]:
    """Every distinct case form `phrase` (whitespace-normalised to single
    spaces) appears as, anywhere in `repo`'s object database, found by a
    case-insensitive, whitespace-tolerant scan of every blob -- "one rule
    per observed case variant of each token", built at run time from the
    real history rather than assumed.

    Reuses `scripts.purge.plan.enumerate_blob_ids` / `read_blob_text` rather
    than re-implementing blob enumeration -- the same posture `plan.py`
    itself takes toward `scripts/purge/sweep.py`'s `SYMBOLIC_PROBES`.
    """
    pattern = re.compile(_whitespace_tolerant_pattern(phrase), re.IGNORECASE)
    variants: set[str] = set()
    for blob_id in enumerate_blob_ids(repo):
        text = read_blob_text(repo, blob_id)
        for match in pattern.finditer(text):
            variants.add(" ".join(match.group(0).split()))
    return tuple(sorted(variants))


# --- case classification -------------------------------------------------------


def _case_matched_adjective(variant: str) -> str:
    """`_WITHDRAWN_ADJECTIVE`, cased to match `variant`'s own case shape:
    all-upper -> all-upper, title-case -> title-case, else (including
    all-lower and mixed) -> lower. Used by the identifier mop-up, where the
    surrounding identifier's own convention (a token's embedded form inside
    an all-caps module constant, inside a CamelCase class symbol, or inside
    a lower-case local variable or string literal) is exactly what the
    replacement must match to stay a
    syntactically valid identifier or a plausible string value."""
    if variant.isupper():
        return _WITHDRAWN_ADJECTIVE.upper()
    if variant.istitle():
        return _WITHDRAWN_ADJECTIVE.title()
    return _WITHDRAWN_ADJECTIVE


# --- given-name exception rules ------------------------------------------------


def given_name_rules(full_name: str) -> tuple[ReplacementRule, ...]:
    """The two narrow exception rules for the bare given name -- derived
    from `full_name`'s first word, never a separate token of its own.

    **Why the given name never gets a rule of its own.** It is an ordinary
    English word. Measured: unguarded, it matches inside "Markdown" across
    292 tip blobs; even `\\b`-guarded, it still matches the standalone
    English verb throughout `.claude/skills/` task-list prose ("Mark the
    Banister and Minetti citations..."). Measured exhaustively over the
    real object database (every blob, minus every occurrence already
    covered by the whitespace-tolerant full-name phrase): the given name
    has exactly two real standalone uses in all of history, both inside one
    blob, neither adjacent to the surname on the same line:

    1. `<given> (<parenthetical email>)` -- an attribution followed by a
       contact address in parentheses. Matched generically by an email
       shape inside parentheses, not a literal address, and the whole match
       (including the parenthetical) is replaced by the sentence-shaped
       family replacement -- dropping the email is deliberate: it is also
       an identity leak (invariant 3), and this rule removes both at once
       rather than leaving `<replacement> (<email untouched>)`.
    2. `<given>'s` -- a bare possessive. Matched literally (word-boundaried)
       and replaced by the possessive form of the sentence-shaped
       replacement.

    Both patterns are narrow enough that they do not fire on the
    "Mark the Banister" false positives (neither is followed by `'s` or a
    parenthetical email), which is exactly the property that makes it safe
    to have no third, catch-all rule for the bare given name.
    """
    given = full_name.split()[0]
    escaped = re.escape(given)
    return (
        ReplacementRule(
            pattern=rf"\b{escaped}\s*\([^)\n]*@[^)\n]*\)",
            replacement=_THIRD_PARTY,
            kind="given-name exception: parenthetical email",
            token_role="full name (given + surname)",
        ),
        ReplacementRule(
            pattern=rf"\b{escaped}'s\b",
            replacement=f"{_THIRD_PARTY}'s",
            kind="given-name exception: possessive",
            token_role="full name (given + surname)",
        ),
    )


# --- identity-leak email rule --------------------------------------------------

_EMAIL_SHAPE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
"""The same generic email shape `scripts/purge/sweep.py::_EMAIL_PATTERN` and
`scripts/purge/plan.py::_EMAIL_PATTERN` use -- carries no literal address of
its own. Used here only to FIND email-shaped strings worth checking against
a forbidden token or a commit's own identity headers, never to classify a
found address by domain (see the module docstring's allowlist-to-denylist
trap note)."""

_COMMIT_HEADER_EMAIL = re.compile(r"^(?:author|committer) .*<([^>]*)>", re.MULTILINE)
"""Matches a commit object's own `author `/`committer ` header line,
capturing the address between angle brackets -- the fixed shape `git`
itself always writes a commit object in, never a per-repository
assumption."""


def _token_domain_addresses(repo: Path, tokens: Sequence[str]) -> tuple[str, ...]:
    """Every email-shaped string anywhere in `repo`'s object database whose
    address text contains one of `tokens` (case-insensitively) -- the third
    party's own contact address is built on a domain carrying their own
    surname (measured: their address's domain contains the surname token
    this purge already redacts everywhere else), so this needs no literal
    address of its own, only the token list every other rule in this module
    already loads from `FITDOCS_FORBIDDEN_STRINGS`."""
    lowered_tokens = tuple(token.lower() for token in tokens if token)
    if not lowered_tokens:
        return ()
    found: set[str] = set()
    for blob_id in enumerate_blob_ids(repo):
        text = read_blob_text(repo, blob_id)
        for match in _EMAIL_SHAPE.finditer(text):
            address = match.group(0)
            lowered = address.lower()
            if any(token in lowered for token in lowered_tokens):
                found.add(address)
    return tuple(sorted(found))


def _iter_all_local_objects(repo: Path) -> Iterator[tuple[str, str, bytes]]:
    """Every object `repo`'s LOCAL object database physically holds -- id,
    type, raw content -- via `git cat-file --batch-all-objects --batch`,
    deliberately NOT `enumerate_blob_ids`'s own `git rev-list --objects
    --all` (which only reaches objects reachable from a ref).

    **Corrected 2026-08-09** (the claim below previously said "a
    reflog-only dangling commit" as if there were exactly one; measured
    directly, there is not). The real object database this module was
    written against holds **572 unreachable commit objects**, not one. The
    git-constructed `NAME-at-HOST.local` identity design.md
    `#### ContactRedaction` names sits on exactly **1** of them (still
    reflog-reachable at measurement time, which is why `git gc --auto`'s own
    two-week grace period had not yet swept it). The maintainer's personal
    mailbox address sits on **248** of them, of which **82 are not
    reflog-reachable at all** -- ordinary `git gc --auto` fodder once they
    age past that same two-week window, with no reflog entry standing
    between them and collection. Neither figure is "the reflog", singular;
    both are `git fsck --unreachable`'s own population, most of it not
    reflog-protected.

    A real same-filesystem `git clone --mirror` defaults to a `--local`
    clone, which hardlinks the whole object directory, unreachable objects
    included -- `scripts/purge/verify.py`'s own
    `check_reflog_and_unreachable_gone` docstring makes the identical
    observation for the opposite reason (why `--no-local` is required
    there). **A `--no-local` clone or a pruned repository does NOT carry
    these 572 objects at all** -- see the module docstring's "reachability
    trap" note and `_reachable_identity_leak_candidates` below, which is the
    source that does not depend on this function's on-disk reality holding.
    This function reads that on-disk reality rather than assuming every
    object of interest is ref-reachable, but a caller must not assume this
    function's input repository still has it."""
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch-all-objects", "--batch"],
        check=True,
        capture_output=True,
    )
    data = result.stdout
    pos = 0
    while pos < len(data):
        newline = data.index(b"\n", pos)
        header = data[pos:newline].decode("ascii")
        object_id, object_type, size_text = header.split(" ")
        size = int(size_text)
        start = newline + 1
        content = data[start : start + size]
        pos = start + size + 1  # the single LF `cat-file --batch` appends
        yield object_id, object_type, content


def _reachable_commit_ids(repo: Path) -> frozenset[str]:
    listed = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    return frozenset(listed)


def _orphaned_commit_identity_addresses(repo: Path) -> tuple[str, ...]:
    """Every author/committer email address that appears on some commit
    object `repo`'s local object database physically holds, but on NO
    commit reachable from any live ref -- derives the maintainer's own
    address and the git-constructed `NAME-at-HOST.local` machine-hostname
    form without ever typing either into this module. Both exist ONLY on
    unreachable commits (design.md `#### ContactRedaction`; see
    `_iter_all_local_objects`'s corrected docstring for the real population
    -- 572 unreachable commit objects, not "a" dangling commit); every
    commit reachable from a ref uses the safe GitHub-noreply alias instead,
    so the set difference names exactly the leaked identities -- no domain
    allowlist required, and no assumption that these are the only two
    identities this could ever find: whatever set difference the corpus
    happens to produce is what gets redacted.

    **This function alone is not the denylist's whole story.** It depends
    on the unreachable commit objects it diffs against still being
    physically present in `repo`'s local object database -- a `--no-local`
    clone or a pruned repository has none of them, and this function then
    returns `()`, silently, not an error. `identity_leak_addresses` below
    is what makes that loud, by cross-checking this function's result
    against `_reachable_identity_leak_candidates`, a source that does not
    need any of these 572 objects to still exist."""
    reachable_ids = _reachable_commit_ids(repo)
    reachable_addresses: set[str] = set()
    all_addresses: set[str] = set()
    for object_id, object_type, content in _iter_all_local_objects(repo):
        if object_type != "commit":
            continue
        text = content.decode("utf-8", errors="replace")
        addresses = _COMMIT_HEADER_EMAIL.findall(text)
        all_addresses.update(addresses)
        if object_id in reachable_ids:
            reachable_addresses.update(addresses)
    return tuple(sorted(all_addresses - reachable_addresses))


_REWRITE_MAP_ARROW = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    r"\s*(?:->|→)\s*"
    r"[A-Za-z0-9._%+-]+@users\.noreply\.github\.com"
)
"""Matches the shape a prior email rewrite's own commit map documents --
`<old, real address> -> <new, safe noreply alias>` -- the exact convention
the deleted prior-rewrite map file's prose header used (measured: still
present, reachable, in an earlier committed version of that file, even
though the path itself was later removed by task 6.3's own remediation;
never named by path here, per the standing forbidden-string guard this
module is itself scanned by -- see `forbidden-strings.tsv`'s `path`-category
rows). Carries no literal address of its own: the right-hand side is
anchored on GitHub's own
fixed `users.noreply.github.com` domain -- the same safe alias
`scripts/purge/sweep.py::_SAFE_EMAIL_DOMAINS` already names -- never a
guessed or typed identity, and the left-hand side is the generic
`_EMAIL_SHAPE` shape, not a domain or token match. `re.search` over this
pattern, not `re.findall` with a capture group, deliberately: the whole
match (not a sub-group) is sliced apart below, which keeps this regex a
single flat alternation-free pattern that is trivially fixed-width-safe --
there is no lookbehind here to make width matter, but keeping the shape
simple keeps that true if the pattern is ever extended."""

_GIT_CONSTRUCTED_HOSTNAME_DOMAIN = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.local\b", re.IGNORECASE
)
"""Matches git's own well-documented auto-identity shape: when
`user.email` is unset, `git commit` constructs a `NAME-at-HOST.local` form
as the author/committer identity. `scripts/purge/sweep.py`'s
`_classify_email_domain` already tags the identical shape
"git-constructed-form-candidate" for its own tip-only working-tree sweep;
this is the same domain test, applied instead to full reachable history.
Carries no literal address: any `.local`-domain email-shaped match
qualifies -- including this repository's own synthetic test fixtures, which
is why `identity_leak_addresses` partitions this source's output by
tip-presence rather than trusting every match to be a real leak."""


def _reachable_blob_path_pairs(repo: Path) -> tuple[tuple[str, str], ...]:
    """Every `(blob_id, path)` pair `git rev-list --objects --all` names for
    a reachable BLOB (never a tree or a commit) -- the same reachable-only
    enumeration `enumerate_blob_ids` performs (`scripts/purge/plan.py`), but
    keeping each blob's path alongside its id so a caller can scope a scan
    by path shape (e.g. "never under `tests/`") without re-deriving the
    blob-to-path association itself. A blob's content can be named at more
    than one path across history (an unchanged file across many commits
    repeats the same pair; two different paths sharing byte-identical
    content share a blob id under two different paths) -- both are kept,
    deliberately: this function answers "was this content ever reachable at
    this path", not "what is this blob's canonical path"."""
    listed = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--objects", "--all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    named: list[tuple[str, str]] = []
    for line in listed.splitlines():
        if not line:
            continue
        object_id, _, path = line.partition(" ")
        if not path:
            continue  # a commit or an unnamed root tree, never worth scanning
        named.append((object_id, path))
    if not named:
        return ()
    checked = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "cat-file",
            "--batch-check=%(objectname) %(objecttype)",
        ],
        input="\n".join(object_id for object_id, _path in named) + "\n",
        check=True,
        capture_output=True,
        text=True,
    )
    blob_ids: set[str] = set()
    for line in checked.stdout.splitlines():
        object_name, _, object_type = line.partition(" ")
        if object_type == "blob":
            blob_ids.add(object_name)
    return tuple(
        (object_id, path) for object_id, path in named if object_id in blob_ids
    )


def _batch_blob_texts(repo: Path, blob_ids: Sequence[str]) -> dict[str, str]:
    """`blob_id -> decoded text` for every id in `blob_ids`, fetched with a
    single `git cat-file --batch` process rather than one `git cat-file -p`
    subprocess per blob (what a naive per-id `read_blob_text` loop over a
    multi-thousand-blob history costs -- measured, minutes rather than
    seconds on this repository's own object database). Parses the same
    `<id> <type> <size>\\n<content>\\n` stream `_iter_all_local_objects`
    above already parses for `--batch-all-objects`, here driven instead by
    an explicit id list on stdin (`--batch` without `--batch-all-objects`)."""
    if not blob_ids:
        return {}
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        input=("\n".join(blob_ids) + "\n").encode("utf-8"),
        check=True,
        capture_output=True,
    )
    data = result.stdout
    texts: dict[str, str] = {}
    pos = 0
    while pos < len(data):
        newline = data.index(b"\n", pos)
        header = data[pos:newline].decode("ascii")
        parts = header.split(" ")
        object_id = parts[0]
        if parts[1] == "missing":
            pos = newline + 1
            continue
        size = int(parts[2])
        start = newline + 1
        content = data[start : start + size]
        pos = start + size + 1  # the single LF `cat-file --batch` appends
        texts[object_id] = content.decode("utf-8", errors="replace")
    return texts


def _reachable_identity_leak_candidates(repo: Path) -> tuple[str, ...]:
    """The reachability-INDEPENDENT source for `identity_leak_addresses` --
    every *candidate* identity-leak address findable purely from reachable
    blob TEXT (`_reachable_blob_path_pairs`/`_batch_blob_texts`, the same
    reachable-only enumeration `enumerate_blob_ids` performs, across every
    historical version of every path, never only the tip), with no
    dependence on the unreachable commit objects
    `_orphaned_commit_identity_addresses` needs. A `--no-local` clone or a
    repository that has had `reflog expire --expire=now --all` and `gc
    --prune=now` run against it still carries every reachable blob -- that
    is what "reachable" means -- so this source finds the same real
    addresses even when the object database the caller was handed has lost
    every unreachable commit object (see the module docstring's
    "reachability trap" note).

    Two shapes, both scoped to every reachable blob at every path:

    1. `_REWRITE_MAP_ARROW` -- an "old address -> safe noreply alias"
       mapping line, as a prior email rewrite's own commit map documents it.
    2. `_GIT_CONSTRUCTED_HOSTNAME_DOMAIN` -- git's own auto-identity
       `NAME-at-HOST.local` form.

    **These are CANDIDATES, not confirmed leaks, and this function
    deliberately does not decide which is which.** This repository's own
    test suite plants synthetic addresses of exactly shape 2 as fixtures
    (`tests/purge/test_replacements.py`'s orphan-commit, pruned-repository
    and unrelated-domain fixtures; `tests/purge/test_sweep.py`'s
    git-constructed-form classification fixture -- referred to here by path
    and role only, never quoted by value), so an unfiltered scan folds every
    one of those into the denylist. That is the SAME allowlist-to-denylist
    trap the module docstring names, reached from the opposite direction (an
    over-eager source rather than an over-eager allowlist).

    **The discrimination lives in `identity_leak_addresses`, as tip-absence
    (`_tip_tree_addresses`), and it SUPERSEDES the `tests/` path-prefix
    scope this function used to apply to shape 2.** That prefix scope was an
    ad-hoc path allowlist, and it was defeated by this very module: an
    earlier revision of this docstring quoted its own test fixtures by
    value, at a `scripts/` path, so the scope excluded the fixtures' real
    home and admitted the copy in the prose that described them -- three
    false candidates, self-inflicted. Tip-absence is a structural fact
    rather than a path or value guess, it is reachability-independent (the
    tip tree exists in every clone, exactly as reachable history does), and
    it is what makes the identity DENYLIST tip-disjoint by construction --
    as a set of case-folded `_EMAIL_SHAPE` tokens, which is the exact and
    only claim. It does not follow that the rule built from that denylist
    leaves every tip blob alone: the rule matches substrings, the sanction
    compares whole tokens. The tip no-op is measured, by
    `test_invariant_6_tip_no_op`, for this rule as for every other rule
    `build_rules` emits -- the per-token tiers are not derived from the tip
    at all. Task 6.3 emptied the tip of every
    forbidden value, so anything the tip still holds is by construction not
    something this rewrite removes.
    """
    pairs = _reachable_blob_path_pairs(repo)
    unique_blob_ids = sorted({object_id for object_id, _path in pairs})
    texts = _batch_blob_texts(repo, unique_blob_ids)

    found: set[str] = set()
    for text in texts.values():
        for match in _REWRITE_MAP_ARROW.finditer(text):
            address = _EMAIL_SHAPE.search(match.group(0))
            if address:
                found.add(address.group(0))
        for match in _GIT_CONSTRUCTED_HOSTNAME_DOMAIN.finditer(text):
            found.add(match.group(0))
    return tuple(sorted(found))


def _tip_tree_blob_ids(repo: Path) -> tuple[str, ...]:
    """Every blob id `git ls-tree -r HEAD` names -- the tip tree, and only
    the tip tree (never a historical version of any path, never an
    unreachable object). Present in every clone of `repo`, whatever its
    object database has been pruned of, because a clone that could not
    reproduce its own `HEAD` tree would not be a clone."""
    listed = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    blob_ids: list[str] = []
    for line in listed.splitlines():
        metadata, _, _path = line.partition("\t")
        fields = metadata.split()
        if len(fields) >= 3 and fields[1] == "blob":
            blob_ids.append(fields[2])
    return tuple(sorted(set(blob_ids)))


def _tip_tree_addresses(repo: Path) -> frozenset[str]:
    """Every email-shaped string (`_EMAIL_SHAPE`, the same generic shape
    `sweep.py` and `plan.py` use) in any blob of `repo`'s tip tree.

    This is the sanctioning half of `identity_leak_addresses`'s partition.
    Task 6.3 emptied the tip of every forbidden value and retired the
    exemption table, and three standing guards keep it empty, so the tip is
    the purge's clean TARGET state: an address the tip still holds is, by
    construction, not one this rewrite is removing -- it is a synthetic
    fixture, a documented shape, or a safe alias. Deriving that judgement
    from the tip tree rather than from a path prefix or a domain list means
    it needs no allowlist of its own and cannot go stale as fixtures move."""
    texts = _batch_blob_texts(repo, _tip_tree_blob_ids(repo))
    found: set[str] = set()
    for text in texts.values():
        for match in _EMAIL_SHAPE.finditer(text):
            found.add(match.group(0))
    return frozenset(found)


def _masked_address(address: str) -> str:
    """An 8-hex-character SHA-256 tag standing in for `address` -- stable
    across runs, so two reports can be compared, and **not readable back
    from the tag alone**. That is the whole of the claim: the digest is
    unsalted and truncated over a low-entropy, guessable value, so anyone
    who already holds a candidate address can confirm a match by hashing it.
    This defends against a value appearing verbatim in output that is
    copied, logged, or pasted into a report -- not against an adversary
    testing a guess.

    Every diagnostic this module raises is masked through this function.
    An error message naming which identity leaked is exactly the shape that
    leaks it again: this module's own predecessor interpolated the raw
    addresses into its `ValueError`, which put them verbatim into pytest
    output, CI logs and review reports -- the same failure mode as the
    incident record that had to be amended (see
    `.kiro/queue/2026-08-10-6-4-identity-derivation-guard-unsatisfiable.md`).
    The same posture as `render_masked_table`: report the shape, never the
    value."""
    return hashlib.sha256(address.encode("utf-8")).hexdigest()[:8]


def _at_tip(addresses: set[str], tip: frozenset[str]) -> set[str]:
    """The members of `addresses` the tip tree holds, compared
    CASE-INSENSITIVELY.

    Case folding is load-bearing rather than tidy. `identity_email_rule`
    emits its address alternation under `(?i:...)`, because an email address
    is conventionally case-insensitive and the same real address is rendered
    differently in different blobs. An exact-string comparison here would
    therefore let a tip blob holding a differently-cased rendering of a
    denylisted address slip past the sanction, while the case-insensitive
    rule would still rewrite that tip blob.

    **It is a trade, not a free improvement.** Folding also WIDENS the
    sanction: a real leaked address present only in history is sanctioned
    away if any unrelated tip fixture differs from it by case alone -- a
    genuine leak silently dropped from the denylist, which is the more
    expensive direction of the two. That is judged acceptable because the
    rule is `(?i:...)` regardless, so an address the tip holds in ANY casing
    would be rewritten at the tip if it were denylisted; the two halves have
    to agree, and agreeing case-insensitively is the half that matches the
    rule. Measured on the real corpus: no derived address differs from a tip
    address by case alone, so folding changes the current result not at all
    -- today. That is a measurement, and it can stop being true."""
    folded = {address.lower() for address in tip}
    return {address for address in addresses if address.lower() in folded}


def _absent_from_tip(addresses: set[str], tip: frozenset[str]) -> set[str]:
    """The complement of `_at_tip` within `addresses` -- same case folding,
    same reason."""
    return addresses - _at_tip(addresses, tip)


def identity_leak_addresses(repo: Path, tokens: Sequence[str]) -> tuple[str, ...]:
    """The complete denylist: every specific address this purge has
    actually found in `repo`'s object database, from three independent,
    corpus-driven sources -- never a literal value typed into this module.
    See `_token_domain_addresses`, `_orphaned_commit_identity_addresses` and
    `_reachable_identity_leak_candidates`.

    **Two sources CONTRIBUTE; the third CHECKS.** The returned denylist is
    built from `_token_domain_addresses` (a token match over reachable blob
    text) and `_reachable_identity_leak_candidates` (two shape matches over
    reachable blob text). Both are reachability-INDEPENDENT: they work in
    any clone of any repository, because every clone carries every reachable
    object. That is the polarity remediation -- the original guard made the
    reachability-DEPENDENT source the authority and therefore raised
    unconditionally against every fresh clone, and against this working
    repository once its unreachable objects were pruned.

    **`_orphaned_commit_identity_addresses` contributes nothing to the
    result, by construction, and is consulted for the two guards only.** It
    is not omitted as an oversight and its removal from the union is not a
    weakening -- the guards make its contribution impossible:

    - guard 1 forces `orphan <= token_domain | candidates` **up to case**
      (it compares case-folded, since round 4), so any address it could
      contribute is already supplied by one of the two contributing sources
      -- possibly in a different casing;
    - guard 2 forces `orphan & tip == set()`, likewise case-folded, so it
      can add nothing to the tip-disjointness the result establishes either.

    **"Up to case" is the exact strength of this, and it is weaker than
    "inert".** Restoring the orphan term is observable: it reds
    `test_identity_leak_addresses_guard_1_folds_case_when_corroborating`,
    whose orphan identity and blob-text rendering differ only in casing, so
    the restored term would add the second rendering to the denylist. The
    practical consequence is nil -- `identity_email_rule` matches
    `(?i:...)`, so both renderings redact the same text either way -- but
    the term is redundant up to case, not provably dead, and the difference
    is worth a sentence because guard 1's comparison semantics is what
    decides it.

    An orphan-ONLY address is therefore an ERROR that guard 1 raises on,
    never a silent contribution -- the loud-not-silent posture the original
    defect existed to establish. The source stays load-bearing in guard 2,
    which is what stops a confirmed identity sitting at the tip from making
    the whole result clone-dependent.

    **The candidate partition.** `_reachable_identity_leak_candidates` finds
    shapes, not verdicts -- this repository's own test fixtures are shaped
    like the thing being redacted. A candidate present in the TIP tree
    (`_tip_tree_addresses`) is sanctioned and dropped; a candidate absent
    from it is a leak. Task 6.3 emptied the tip, so the tip is the purge's
    clean target state. The other two sources are NOT partitioned this way,
    because both are confirmations rather than shape matches: a token in an
    address's own domain, and an author/committer header on an unreachable
    commit, are things a fixture inside a blob cannot manufacture. Guard 2
    below is what covers them instead -- for those two sources, an address
    at the tip is an ERROR rather than a sanction.

    **Raises `ValueError`** in exactly two genuinely inconsistent states,
    with every address masked (`_masked_address`):

    1. `_orphaned_commit_identity_addresses` names an address that NEITHER
       reachability-independent source found at all. That is the original
       defect's real shape -- evidence of a leaked identity that the sources
       this derivation now relies on would miss -- and it must halt loudly.
       It is vacuously satisfied wherever the orphan source is empty (a
       fresh clone, a pruned repository), which is the point: an absent
       source is not an inconsistency.
    2. A CONFIRMED address -- token-corroborated or orphan-commit-derived --
       is present in the tip tree. The tip would then still hold a real
       leaked identity, contradicting task 6.3 and the three standing
       guards, and this derivation's whole sanctioning rule with it. It also
       makes the result clone-dependent, since a clone without unreachable
       objects would sanction the same address away silently.

    **What this guarantees, and what it does not.** Read together, guard 2
    and the `_absent_from_tip` filter make the returned denylist
    **tip-disjoint by construction, as a set of case-folded `_EMAIL_SHAPE`
    tokens**: this function either returns addresses the tip does not
    contain under that comparison, or it raises. That is precisely what
    `test_identity_denylist_is_exactly_the_leaks_the_tip_does_not_hold`'s
    `denylist & tip` assertion measures, and it is the entire construction
    claim.

    **It does NOT follow that the rule built from this denylist leaves every
    tip blob unchanged, and that stronger claim is deliberately not made
    here.** The gap is that `identity_email_rule` matches SUBSTRINGS of blob
    text while this function compares WHOLE `_EMAIL_SHAPE` tokens against
    the tip -- two different questions, so set-disjointness of the tokens
    does not imply the pattern misses. Two axes of that gap have already
    been found and closed one at a time (case folding, then substring
    anchoring in `identity_email_rule`), which is exactly the reason not to
    assert that the last one is closed. **The tip no-op is a MEASUREMENT:**
    `tests/purge/test_replacements.py::test_invariant_6_tip_no_op`, which
    applies the whole emitted rule set to every tip blob and asserts nothing
    changes. It covers this rule on the same footing as every other -- the
    given-name exceptions and the per-token, per-case-variant tiers are
    derived from the token list and from `observed_case_variants`, neither
    of which consults the tip, so nothing in the rule set was ever
    structurally guaranteed against the tip.

    Nor does it make the denylist a complete list of every identity ever
    leaked. Guard 2 catches a confirmed address at the tip; nothing catches
    an address that is a real leak, is absent from the tip, and matches
    none of the three sources' shapes -- such an address is simply never
    found, silently. The sources are the coverage; the guards only keep the
    sources from contradicting each other.

    **It deliberately does NOT raise merely because the orphan source is
    empty, or because the union is empty.** A freshly initialised repository
    with a single commit -- as most of this module's own mechanics tests use
    -- legitimately has zero unreachable commits and nothing for any source
    to find; raising on that shape would fail every one of those tests for a
    reason unrelated to what they measure. `identity_email_rule` already
    handles the empty case explicitly, via `_NEVER_MATCHES`."""
    token_domain = set(_token_domain_addresses(repo, tokens))
    orphan = set(_orphaned_commit_identity_addresses(repo))
    candidates = set(_reachable_identity_leak_candidates(repo))
    tip = _tip_tree_addresses(repo)

    # Guard 1 folds case for the same reason guard 2 does, and so that one
    # comparison semantics governs both: without folding, "neither
    # reachability-independent source found it anywhere in reachable blob
    # text" could be printed when a differently-cased rendering WAS found,
    # which would be a false diagnostic on a halting path.
    seen_folded = {address.lower() for address in token_domain | candidates}
    unseen = {address for address in orphan if address.lower() not in seen_folded}
    if unseen:
        raise ValueError(
            "identity-leak derivation is inconsistent: the reachable-vs-all "
            "commit-identity diff (_orphaned_commit_identity_addresses) "
            "names "
            f"{sorted(_masked_address(address) for address in unseen)} "
            "(SHA-256 tags, never the values) as a leaked identity, but "
            "neither reachability-independent source found it anywhere in "
            "reachable blob text. Those two sources are what a fresh clone "
            "has to work from, so a leak only the local object database's "
            "unreachable commits can see would be silently dropped by every "
            "clone this rewrite runs against."
        )

    confirmed_at_tip = _at_tip(token_domain | orphan, tip)
    if confirmed_at_tip:
        raise ValueError(
            "identity-leak derivation is inconsistent: a CONFIRMED leaked "
            "identity is still present in the tip tree. The token-domain "
            "match (_token_domain_addresses) and/or the reachable-vs-all "
            "commit-identity diff (_orphaned_commit_identity_addresses) "
            f"name {sorted(_masked_address(a) for a in confirmed_at_tip)} "
            "(SHA-256 tags, never the values), and `git ls-tree -r HEAD` "
            "still contains it. Task 6.3 emptied the tip of every forbidden "
            "value, so this means either the tip has regressed or this "
            "derivation's tip-absence sanctioning rule no longer holds -- "
            "fix the tip before generating rules from it. Halting here is "
            "also what keeps the returned denylist tip-disjoint: neither of "
            "these two sources is filtered by tip-presence (only "
            "`candidates` is), so without this guard a confirmed address "
            "sitting at the tip would enter the denylist in a repository "
            "that still holds unreachable objects and be sanctioned away in "
            "a clone that does not -- a clone-DEPENDENT result, which is "
            "the one property this derivation exists to remove."
        )

    # `orphan` is deliberately ABSENT from this union. The two guards above
    # have already made it a CHECKING source rather than a contributing one,
    # by construction rather than by preference:
    #
    #   - guard 1 forces `orphan <= token_domain | candidates` UP TO CASE
    #     (both guards compare case-folded), so every address the orphan
    #     source could have contributed here is already supplied by one of
    #     the other two terms, possibly in a different casing;
    #   - guard 2 forces `orphan & tip == set()`, likewise case-folded.
    #
    # An orphan-ONLY address is therefore an ERROR that guard 1 raises on,
    # never a silent contribution to the denylist -- which is the
    # loud-not-silent posture the original defect existed to establish, now
    # expressed in the shape of the code rather than in a comment apologising
    # for a term that never fires. That is not a weakening: the orphan
    # source stays load-bearing in guard 2, which is what stops a confirmed
    # identity at the tip from making the result clone-dependent.
    #
    # "Up to case" is the honest strength. Re-measured after round 4 made
    # guard 1 case-folded: restoring `| _absent_from_tip(orphan, tip)` reds
    # `test_identity_leak_addresses_guard_1_folds_case_when_corroborating`,
    # where in round 3 -- when guard 1 compared exact strings -- it reddened
    # nothing at all. The rule is `(?i:...)`, so the redacted text is
    # identical either way; the claim is narrower than it was, not the
    # design.
    #
    # Both remaining terms are tip-disjoint AS CASE-FOLDED `_EMAIL_SHAPE`
    # TOKENS -- `token_domain` because guard 2 refuses to return when it
    # meets the tip, `candidates` because that intersection is removed here.
    # That is the whole claim; it does NOT extend to "the rule cannot touch
    # a tip blob", because the rule matches substrings and this comparison
    # is over whole tokens. `test_invariant_6_tip_no_op` is what measures
    # the tip no-op.
    #
    # `_absent_from_tip` folds case because the rule is `(?i:...)`: an
    # exact-string comparison would sanction nothing when the tip held a
    # differently-cased rendering of a denylisted address. Measured on the
    # real corpus: no address differs from a tip address by case alone, so
    # folding changes the current result not at all. It also WIDENS the
    # sanction -- see `_at_tip`'s docstring for that cost.
    found = token_domain | _absent_from_tip(candidates, tip)
    return tuple(sorted(found))


_NEVER_MATCHES = r"(?!)"
"""A permanently-failing zero-width assertion -- a valid, complete regex on
its own that matches nothing at any position (`re.sub(_NEVER_MATCHES, ...,
text) == text` for any `text`). Used when `identity_leak_addresses` finds
nothing to redact (every mechanics and synthetic-repository test in this
suite, none of which carries any of the three real addresses) so
`identity_email_rule` always returns exactly one rule -- the fixed
"given-name, then email, then per-token tiers" ordering `build_rules` and
`test_build_rules_is_ordered_given_name_email_then_longest_token_first`
rely on holds regardless of whether this particular repo has anything for
this rule to find."""


def identity_email_rule(repo: Path, tokens: Sequence[str]) -> ReplacementRule:
    """The one rule for "an address `identity_leak_addresses` has confirmed,
    by scanning `repo`'s own object database, is a real identity leak" -- a
    DENYLIST of specific addresses, never an allowlist of what to leave
    alone. See the module docstring's trap note for why the allowlist this
    replaced was wrong, and the docstring of `identity_leak_addresses` and
    its three sources for where each denylisted address comes from -- and
    for the condition under which this raises `ValueError` instead of
    returning a rule.

    **The anchoring rule, in one line: redact at a position exactly when the
    adjacent text cannot extend the match to a longer `_EMAIL_SHAPE`
    token.** That is what makes the 700 cells of
    `tests/purge/test_replacements.py::test_identity_rule_adjacency_matches_email_shape`
    derivable rather than arbitrary, and it is the rule the lookarounds
    below implement -- see the comment there for how each one follows from
    it, and that test module's docstring for why the table, not a green
    suite, is the gate on any change to them."""
    addresses = identity_leak_addresses(repo, tokens)
    if not addresses:
        pattern = _NEVER_MATCHES
    else:
        alternation = "|".join(re.escape(address) for address in addresses)
        # `(?i:...)` scopes case-insensitivity to the address alternation --
        # matches this module's overall case-sensitive-by-default posture
        # (see the module docstring's departure from `(?i)`), while still
        # tolerating a differently-cased rendering of the same real address
        # (email addresses are conventionally case-insensitive; the prior
        # domain-based rule applied the same reasoning to its own
        # domain-exclusion group).
        #
        # The three lookarounds implement exactly one rule:
        #
        #     redact at this position exactly when the adjacent text CANNOT
        #     be part of a longer `_EMAIL_SHAPE` token.
        #
        # Not "is the next character in the domain alphabet" -- that was the
        # earlier, wrong justification, and it is wrong in BOTH directions.
        # `_EMAIL_SHAPE` is the module's own definition of what an address
        # is, and it is the oracle
        # `tests/purge/test_replacements.py::test_identity_rule_adjacency_
        # matches_email_shape` checks these anchors against, over the full
        # product of prefix and suffix contexts: 25 x 28 = 700 cells, 0
        # disagreements. That table is the reason this comment can describe
        # a rule rather than a list of patched cases.
        #
        # Both failure directions are real and neither is theoretical:
        #
        # - OVER-matching mangles (invariant 4). Unanchored, a blob reading
        #   `<denylisted>.example` becomes `a redacted email address.example`
        #   and `pre<denylisted>` becomes `prea redacted email address` --
        #   both measured before the anchors existed.
        # - UNDER-matching leaves a real identity in history, which is worse.
        #   A sentence-final `<denylisted>.` is a complete `_EMAIL_SHAPE`
        #   token and must be redacted; so is `<denylisted>7` and
        #   `<denylisted>-based`, because in none of those can the trailing
        #   text extend the address into a longer valid one.
        #
        # `\b` will not do the job -- an address ends in a word character but
        # `.` and `-` are non-word, so `\b` asserts nothing useful at either
        # end.
        #
        # Behind: any local-part character means this match starts INSIDE a
        # longer address. The lookbehind is a single character class and so
        # fixed-width, which `re` requires.
        # Ahead: a letter extends the TLD (`.testx`), and any run of domain
        # characters followed by `.` plus two letters adds a further label
        # (`.example`, `7.example`) -- those are the only two ways a longer
        # `_EMAIL_SHAPE` token can exist here, so they are the only two
        # suppressions. A trailing `.`, digit or `-` NOT followed by such a
        # label extends nothing, and is therefore redacted.
        pattern = (
            rf"(?<![A-Za-z0-9._%+-])(?i:{alternation})"
            r"(?![A-Za-z])(?![A-Za-z0-9.-]*\.[A-Za-z]{2,})"
        )
    return ReplacementRule(
        pattern=pattern,
        replacement=_REDACTED_EMAIL,
        kind="identity leak: denylisted address",
        token_role="(cross-cutting)",
    )


# --- per-token, per-case-variant rule generation -------------------------------


def _token_tier_rules(
    variant: str, family: str, role: str
) -> tuple[ReplacementRule, ...]:
    """Sub-tiers (a)-(e) of the module docstring's ordering, for one
    already-whitespace-normalised case `variant` of one token in `family`."""
    lower, cap, bare = _FAMILIES[family]
    core = _whitespace_tolerant_pattern(variant)
    adjective_matched = _case_matched_adjective(variant)

    # A literal, unwrapped `\s` between an article/punctuation and the token
    # is the root cause a real filter-repo run exposed: a lookbehind is
    # fixed-width, so `(?<=\bthe\s)` can only ever assert exactly one
    # whitespace character, and real prose wraps a line there ("the\n
    # <token>", "gate.\n\n<token>"). Tiers (a) and (c) below therefore
    # *consume* the article/punctuation as part of the match (the way tier
    # (b) already did) instead of asserting it via a lookbehind, so any run
    # of wrapping whitespace -- not just one space -- is tolerated.
    #
    # `noun_core` additionally consumes a literal trailing "methodology"
    # word for the withdrawn_methodology family only: `bare`/`cap`/`lower`
    # for that family already end in the word "methodology" (see
    # `_FAMILIES`), so a tier that replaces only the token and leaves the
    # source's own following "methodology" word in place produces the
    # "methodology methodology" duplicate (measured: "the FBC methodology"
    # -> "the withdrawn methodology methodology" without this). The
    # indefinite-article guard (b) and the identifier mop-up (e) are
    # deliberately excluded: (b)'s replacement is the bare adjective
    # `withdrawn`, which already composes correctly with a literal
    # following "methodology" as adjective + noun ("a withdrawn
    # methodology"), and (e) never sees prose word-spacing at all.
    #
    # The trailing word is matched case-insensitively (`[Mm]ethodology`),
    # a deliberate choice, not an oversight: `lower`/`cap`/`bare` all end in
    # the lowercase word "methodology", so a literal-case-only match leaves
    # a capitalised trailing occurrence ("the FBC Methodology", e.g. a
    # markdown heading) unconsumed, producing "the withdrawn methodology
    # Methodology" -- the same duplicate-noun mangled shape this whole
    # group exists to avoid, just case-shifted. Measured: zero real
    # occurrences of a capitalised trailing "Methodology" exist in the
    # current corpus either way, so this costs nothing today and only
    # forecloses the shape for any future or as-yet-unscanned occurrence.
    noun_core = core
    if family == "withdrawn_methodology":
        noun_core = rf"{core}(?:\s+[Mm]ethodology\b)?"

    rules: list[ReplacementRule] = []

    # (a) definite-article guard -- consumes "the"/"The" plus the token (and
    # the withdrawn_methodology family's optional trailing "methodology"
    # word, via `noun_core`) as part of the match, then re-emits the article
    # verbatim ahead of the plain lowercase bare form (`bare`, never
    # case-matched to the token: the token's own case shape is irrelevant
    # here, only the already-correct article's case is what carries
    # capitalisation).
    for article, article_kind in (
        ("the", "definite article (lowercase)"),
        ("The", "definite article (capitalised)"),
    ):
        rules.append(
            ReplacementRule(
                pattern=rf"\b{article}\s+{noun_core}\b",
                replacement=f"{article} {bare}",
                kind=f"definite-article guard: {article_kind}",
                token_role=role,
            )
        )

    # (b) indefinite-article guard -- the article is matched (and consumed)
    # as PART of the pattern, not via a lookbehind: a lookbehind would leave
    # the original "an"/"An" text in place while also inserting the
    # normalised "a "/"A " prefix, producing "an a withdrawn" (measured).
    # Consuming the whole "<article> <token>" span and replacing it with the
    # normalised article plus the bare adjective is what actually replaces
    # "an" with "a" rather than merely prepending a second article.
    for article, normalised in (("a", "a"), ("A", "A"), ("an", "a"), ("An", "A")):
        rules.append(
            ReplacementRule(
                pattern=rf"\b{article}\s+{core}\b",
                replacement=f"{normalised} {_WITHDRAWN_ADJECTIVE}",
                kind=f"indefinite-article guard: {article!r} -> {normalised!r}",
                token_role=role,
            )
        )

    # (c) sentence-start guard. The "after sentence-ending punctuation"
    # variant consumes the punctuation plus the run of whitespace that
    # follows it (captured in group 1 and replayed verbatim), for the same
    # fixed-width-lookbehind reason as tier (a) -- `[.!?]\s+` tolerates a
    # paragraph break, `[.!?]\s` (or a lookbehind built from it) does not.
    # The "start of blob" variant stays a lookbehind: `\A` is zero-width by
    # construction and never consumes anything, so it never had a
    # fixed-width problem to begin with.
    #
    # `_abbreviation_negative_lookbehind` guards the punctuation variant
    # only -- an abbreviation like "e.g" or "vs" is exactly the thing
    # `[.!?]\s+` cannot itself distinguish from a genuine sentence end
    # (measured: 15 real sites, `(e.g. <token>)` wrongly capitalised
    # without this). The blob-start variant needs no such guard: there is
    # no preceding text for an abbreviation to be.
    rules.append(
        ReplacementRule(
            pattern=(_abbreviation_negative_lookbehind + rf"([.!?]\s+){noun_core}\b"),
            replacement=rf"\1{cap}",
            kind="sentence-start guard: after sentence-ending punctuation",
            token_role=role,
        )
    )
    rules.append(
        ReplacementRule(
            pattern=rf"(?<=\A){noun_core}\b",
            replacement=cap,
            kind="sentence-start guard: start of blob",
            token_role=role,
        )
    )

    # (c2) dotted module path guard -- design.md `#### IdentityErasure`'s own
    # fix: "the lower-case module segment of that dotted module path,
    # wherever the path appears in a code span" becomes the bare adjective
    # (`fitdocs.load.withdrawn`), never the sentence-shaped phrase tier (d)
    # would otherwise substitute. A `.` is a single character, so the
    # lookbehind is always fixed-width (unlike tiers (a)/(c)'s whitespace
    # runs) and needs no consume-and-replay trick. Ordered before tier (d)
    # deliberately: `.` is a non-word character, so tier (d)'s `\b`-anchored
    # rule also matches right after a dot, and being unordered relative to
    # (d) would leave whichever tier is listed first winning arbitrarily.
    # Uses `core`, not `noun_core`: a dotted module path is never followed
    # by a literal "methodology" word, so there is nothing for the
    # withdrawn_methodology family's optional trailing-word group to do
    # here, and applying it would be a needless generalisation past what is
    # actually observed.
    rules.append(
        ReplacementRule(
            pattern=rf"(?<=\.){core}\b",
            replacement=adjective_matched,
            kind="dotted module path segment",
            token_role=role,
        )
    )

    # (d) general
    rules.append(
        ReplacementRule(
            pattern=rf"\b{noun_core}\b",
            replacement=lower,
            kind="general",
            token_role=role,
        )
    )

    # (e) identifier mop-up -- unanchored, in three sub-passes, most-specific
    # (longest match) first, so a wider match is fully consumed before a
    # shorter, more generic one gets a turn at what is left.

    # (e1) an identifier-style `an_<token>` / `An_<token>` / `AN_<token>`
    # prefix, joined by an underscore rather than English prose's space --
    # `\s+` cannot see it (an underscore is a word character, so tier (b)'s
    # `\b{article}\s+...` never fires here either). Left alone, the bare
    # mop-up leaves the original "an_" untouched and produces the literal
    # `an_withdrawn` substring invariant 4 names -- measured in a real test
    # function name built from the abbreviation token in this identifier
    # shape (`test_..._carries_an_<abbreviation>_derived_constant`).
    # Consuming the article-looking prefix too and normalising it the same
    # way tier (b) normalises real "an" avoids it.
    for article, normalised in (("an", "a"), ("An", "A"), ("AN", "A")):
        rules.append(
            ReplacementRule(
                pattern=f"{article}_{core}",
                replacement=f"{normalised}_{adjective_matched}",
                kind=f"identifier mop-up: {article!r}_-prefix normalisation",
                token_role=role,
            )
        )

    # (e2) a trailing "-ed" suffix directly against the token, forming a
    # coined verb (measured in real history: a "de-<Surname>ed" comment,
    # coining the surname into a verb). `adjective_matched` ("withdrawn") is
    # already a past-participle-shaped word; appending the original "-ed"
    # on top produces `Withdrawned`, the exact mangled form invariant 4
    # names, so this sub-pass consumes the suffix rather than leaving it.
    rules.append(
        ReplacementRule(
            pattern=f"{core}ed\\b",
            replacement=adjective_matched,
            kind="identifier mop-up: trailing '-ed' suffix consumed",
            token_role=role,
        )
    )

    # (e3) the plain unanchored mop-up -- whatever is left, most commonly
    # the token embedded inside an ordinary identifier or string literal.
    rules.append(
        ReplacementRule(
            pattern=core,
            replacement=adjective_matched,
            kind="identifier mop-up (unanchored)",
            token_role=role,
        )
    )

    return tuple(rules)


# --- copyright-notice and trademark-mark rules (task 6.5, Req 11.4) ------------
#
# EVERY PATTERN IN THIS SECTION IS COMPILED TWICE, IN TWO DIFFERENT DOMAINS,
# AND MUST MEAN THE SAME THING IN BOTH. `apply_rules` below compiles it as a
# `str` regex against decoded blob text; `git filter-repo` reads the rendered
# rule file with `open(filename, 'br')` and compiles the raw BYTES
# (`git_filter_repo.py::FilteringOptions.get_replace_text`). Two consequences,
# both measured rather than reasoned about, and both of which broke a first
# draft of this section:
#
# 1. `\uXXXX` IS NOT AN ESCAPE IN A BYTES REGEX. A pattern spelling the
#    copyright sign as `\u00a9` compiles fine as `str` and raises
#    `bad escape \u` as bytes -- and filter-repo compiles every regex before
#    it rewrites anything, so ONE such pattern aborts the whole one-shot run
#    with the history untouched. Verified end to end on a throwaway mirror.
#    The remedy is to interpolate the CHARACTER (from a `str` constant whose
#    own source spelling is an escape, so no needle is contiguous in tracked
#    source) rather than to write an escape into the pattern text.
# 2. A CHARACTER CLASS CONTAINING A MULTI-BYTE CHARACTER IS A CLASS OF BYTES.
#    `[^"`<sign><mark>]` encoded to UTF-8 excludes the individual bytes
#    `\xc2 \xa9 \xe2 \x84 \xa2`, so as bytes it also refuses the first byte
#    of every other character in those ranges -- an em dash is shredded rather
#    than matched. That is why the attribution body below is a TEMPERED token
#    (`(?!<mark>)[^"`]`) instead: the exclusions that must be understood as
#    characters live in a lookahead, where a multi-byte alternative is a
#    sequence of bytes and means exactly what it means as text, and the class
#    itself contains only ASCII.
#
# `test_every_notice_and_mark_rule_compiles_as_bytes` pins the first (every
# emitted pattern compiles in both domains) and
# `test_notice_rules_behave_identically_in_the_bytes_domain` pins the second
# (the two domains produce identical output over a fixture whose attributions
# CONTAIN multi-byte characters -- which is where the difference bites, and
# where an earlier version of that fixture did not put them).

# `_COPYRIGHT_SIGN`, `_TRADEMARK_MARK` and `_NOTICE_PHRASE_WORDS` moved to
# `tests/_forbidden_strings.py` (task 7.2) and are imported at module scope
# above; the VALUEs are exactly what they were, interpolated into the
# patterns below the same way, which is what keeps them byte-domain safe.

_REDACTED_NOTICE = "[redacted third-party copyright notice]"
"""What a removed notice is replaced by (Req 11.6: redact the identity,
retain the record, do not falsify what the record states; Req 11.12: no
replacement proper name).

Square brackets are the ordinary editorial convention for material removed
from a quotation, and most sites this lands at are prose quoting the notice
-- `the workbook is marked "<notice>" and redistribution permission was
never obtained`, `two "<notice>" CSVs`. Not all of them are: the `.gitignore`
site is a bare comment (`# <notice> -- kept out of the repo until ...`), where
the bracketed form reads as the editorial marker it is rather than as a
sentence the file is asserting. The surrounding text goes on saying exactly
what it said before -- that a third party's notice was there, and what
followed from it -- with the notice itself no longer reproduced.

**The one site where the bare phrase follows an article** (there is exactly
one, not several: `carry an <notice> copyright notice naming ...` in this
spec's own `requirements.md` history) does NOT read correctly with a bracketed
noun phrase dropped into it -- `carry an [redacted ...]` is ungrammatical.
That is what `notice_rules`' article tier is for, and it is the same fix the
token tiers already make for `an <adjective>`: the article is consumed and
re-emitted as `a`, giving `carry a `<notice>` copyright notice`. Measured, not
assumed -- an earlier revision of this docstring claimed eight article sites
and claimed the bracket read correctly at them, and both claims were false."""

_NOTICE_MARK_PATTERN = rf"(?:{re.escape(_COPYRIGHT_SIGN)}|\([cC]\))"
"""The copyright sign or its ASCII rendering, both observed in real history
(`<sign> 2026 ...`, `(c) 2026 ...`). The sign is interpolated as a character,
never as a `\\u` escape -- see this section's header."""

_NOTICE_WORD_PATTERN = r"[Cc]opyright"
"""Case-sensitive by construction (a character class, never an inline
`(?i)`) -- see the module docstring's departure from `(?i)`."""

_NOTICE_PREFIX_PATTERN = (
    rf"(?:{_NOTICE_WORD_PATTERN}\s*{_NOTICE_MARK_PATTERN}"
    rf"|{_NOTICE_MARK_PATTERN}|{_NOTICE_WORD_PATTERN})"
)
"""`Copyright (c)` / `Copyright <sign>` written first, longest-first, for
readability only.

**The order is NOT load-bearing, and the claim that it was has now been wrong
twice.** A backtracking engine tries every alternative at the same start
position, so when the bare-word alternative matches and the rest of the
pattern then fails, the engine falls back to the word-plus-mark alternative at
that same position and matches anyway. Reversing this alternation is an
EQUIVALENT MUTANT: byte-identical output over every reachable blob, and not
one test reds. Measured twice -- first by a reviewer against the earlier body
pattern, then again here after the body was tightened, on the theory that
refusing `(c)` inside the body would make the order matter. It does not, for
the reason above.

What is load-bearing is that the word alternative EXISTS at all: without it,
`Copyright (c) ...` matches only from `(c)` and leaves `Copyright ` standing
in front of the redaction. That is what
`test_notice_prefix_consumes_the_word_and_the_ascii_sign_together` pins, and
dropping the word alternative (`m19_prefix_without_the_word`) is the mutation
that reds it, along with six sibling rows -- 7 tests in all, re-measured on
this tree rather than carried forward."""

_NOTICE_BODY_MAX_WIDTH = 40
"""How far the attribution between a notice mark and the reserved-rights
phrase may run. **Measured, not guessed**: over every reachable blob, with
this module's token rules already applied (which is the order these rules
run in), the widest real gap is 23 characters -- ` 2026 <the sentence-shaped
replacement>. `. 40 leaves margin for a longer attribution without letting a
match reach across a paragraph.

Counted in CHARACTERS as `str` and in BYTES as filter-repo runs it (see this
section's header). Every real attribution is ASCII, where the two are the
same; a non-ASCII attribution would get a slightly tighter bound under
filter-repo than under `apply_rules`, which is the safe direction -- it can
only leave a mark standing, never reach further."""

_NOTICE_BODY_PATTERN = (
    rf'(?:(?!{_NOTICE_MARK_PATTERN}|{re.escape(_TRADEMARK_MARK)})[^"`])'
    rf"{{0,{_NOTICE_BODY_MAX_WIDTH}}}?"
)
"""The attribution between the mark and the phrase: a year, a name (or, at
this point in the rule order, the token rules' own replacement for one) and
punctuation. A **tempered** token -- "any character that is not a quote or a
backtick, and that does not begin a notice mark" -- rather than a negated
class, so that the multi-byte exclusions live in a lookahead and survive the
bytes domain intact (this section's header, point 2).

Newlines are permitted: one real site wraps between `(c)` and the year. Four
things are excluded, each for a reason:

- `"` and `` ` ``: a match must not run out of one quoted string or code span
  and into another. Every quoted real site keeps the quote OUTSIDE the notice.
- the copyright sign, `(c)`, and the mark: excluding them forces a match to
  start at the *nearest* preceding mark, so two adjacent notices cannot be
  swallowed by one match. It does NOT make `_NOTICE_PREFIX_PATTERN`'s
  alternation order load-bearing -- see that constant's docstring, and note
  that this sentence previously claimed the opposite two constants away from
  the docstring denying it. Re-measured against the tempered body: reordering
  the alternation changes the output of 0 of 1930 reachable blobs and of five
  hand-built `Copyright`-prefixed shapes.

Non-greedy, so the shortest attribution that reaches a phrase wins."""

# `_NOTICE_CONTINUATION_MARKERS` and `_NOTICE_WORD_SEPARATOR` moved to
# `tests/_forbidden_strings.py` (task 7.2) and `_NOTICE_WORD_SEPARATOR` is
# imported at module scope above -- `notice_phrase_pattern` below consumes
# it unchanged.


def notice_phrase() -> str:
    """The reserved-rights phrase, assembled at run time -- never a
    contiguous literal in tracked source. See `_NOTICE_PHRASE_WORDS`."""
    return " ".join(_NOTICE_PHRASE_WORDS)


def notice_phrase_pattern(variant: str) -> str:
    """`variant`'s words joined by `_NOTICE_WORD_SEPARATOR` -- the notice's
    own wrap-tolerant pattern, deliberately NOT
    `_whitespace_tolerant_pattern` (see that constant's docstring for the 11
    notices the difference is worth, and for why the token rules keep the
    narrower helper)."""
    return _NOTICE_WORD_SEPARATOR.join(re.escape(word) for word in variant.split())


def observed_notice_case_variants(repo: Path) -> tuple[str, ...]:
    """Every distinct case form the reserved-rights phrase appears in across
    `repo`'s reachable blobs, normalised to its words joined by single spaces.

    The notice's counterpart to `observed_case_variants`, which cannot be
    reused for two independent reasons: it joins words with `\\s+` (blind to a
    comment-wrapped notice) and it normalises a match with `" ".join(...split())`,
    which would turn a wrapped occurrence into a bogus variant carrying the
    continuation marker between the words, and emit a rule for it. Here the
    normalisation
    keeps only the letter runs, so every wrap shape collapses to the one
    variant it actually is."""
    pattern = re.compile(notice_phrase_pattern(notice_phrase()), re.IGNORECASE)
    blob_ids = enumerate_blob_ids(repo)
    variants: set[str] = set()
    for text in _batch_blob_texts(repo, blob_ids).values():
        for match in pattern.finditer(text):
            variants.add(" ".join(re.findall(r"[A-Za-z]+", match.group(0))))
    return tuple(sorted(variants))


def notice_rules(variant: str) -> tuple[ReplacementRule, ...]:
    """The three rules for one observed case variant of the reserved-rights
    phrase, **longest match first**: the whole notice (mark, attribution and
    phrase); then the bare phrase with the indefinite article in front of it;
    then the bare phrase alone.

    The order is load-bearing in exactly the way the token tiers' is. With a
    shorter rule first it consumes the phrase at a real notice site and the
    longer rule can never fire, leaving `<sign> 2026 <redacted>. <replacement>`
    (or `an [redacted ...]`) standing -- the residue task 6.5 exists to remove.

    **Wrap tolerance is not a nicety, and whitespace is not the whole of it.**
    The phrase is built through `notice_phrase_pattern`, which tolerates both a
    plain line wrap and a wrap onto a comment or blockquote continuation line.
    Measured over every reachable blob: a flat pattern finds 46 occurrences in
    28 blobs, whitespace-tolerance finds 49 in 31, and continuation-tolerance
    finds **60 in 42**. Each of those gaps is a set of notices a rule built on
    the narrower pattern leaves standing in the real rewrite, and this rewrite
    gets a single attempt.

    **Anchoring.** The phrase is bounded by `(?<![A-Za-z])` and `(?![A-Za-z])`,
    which is the letter-run rule
    `tests/purge/test_replacements.py::test_notice_rule_adjacency_matches_whole_words`
    checks against an independent whole-word oracle over the full product of
    prefix and suffix contexts. Letters, not `\\b`: `\\b` would refuse
    `<phrase>7` (both sides word characters) while the phrase is plainly
    present there, and would accept nothing extra in return.

    **Scope.** These rules are keyed on the phrase, never on the copyright sign
    or the word `copyright` alone. Measured at `40eb36e`, the tree this
    docstring ships on: the phrase occurs 60 times across 17 paths, the bare
    sign 235 times across 51 paths, and the word `copyright` 671 times
    word-boundaried across 40 --
    and the overwhelming majority of the latter two are licence headers,
    packaging metadata and this spec's own prose about the notice. A rule keyed
    on either would be irreversible over-redaction of material this purge has
    no business touching. The mark and the word are consumed here only when
    they stand within `_NOTICE_BODY_MAX_WIDTH` of the phrase, which is what
    makes them part of a notice rather than a mention of one. (Counts move with
    every commit that discusses this work; they are true of the named commit,
    not of whatever tree you are reading them on.)
    """
    phrase = notice_phrase_pattern(variant)
    anchored = rf"(?<![A-Za-z]){phrase}(?![A-Za-z])"
    opener = "[" + chr(0x60) + "\"']?"
    rules = [
        ReplacementRule(
            pattern=rf"{_NOTICE_PREFIX_PATTERN}{_NOTICE_BODY_PATTERN}{anchored}",
            replacement=_REDACTED_NOTICE,
            kind="copyright notice: mark, attribution and reserved-rights phrase",
            token_role="(notice)",
        )
    ]
    for article, replacement_article in (("a", "a"), ("A", "A")):
        rules.append(
            ReplacementRule(
                pattern=(
                    rf"(?<![A-Za-z]){article}n?"
                    rf"({_NOTICE_WORD_SEPARATOR}{opener}){anchored}"
                ),
                replacement=rf"{replacement_article}\1{_REDACTED_NOTICE}",
                kind="copyright notice: indefinite article normalised to 'a'",
                token_role="(notice)",
            )
        )
    rules.append(
        ReplacementRule(
            pattern=anchored,
            replacement=_REDACTED_NOTICE,
            kind="copyright notice: bare reserved-rights phrase",
            token_role="(notice)",
        )
    )
    return tuple(rules)


def trademark_mark_rule() -> ReplacementRule:
    """The trademark mark, deleted outright.

    Deleted rather than replaced by any text: the mark is a claim, not a
    record, and it appears mid-word (`<abbreviation><mark> name`,
    `<phrase><mark> and`), where substituting any wording at all would split
    the surrounding words -- the mangled shape invariant 4 forbids. Removing
    it leaves the sentence around it intact and still saying what it said.

    Emitted unconditionally, like `identity_email_rule`'s `_NEVER_MATCHES`
    fallback: one rule always, so the rule set's shape does not depend on
    what a particular repository happens to contain."""
    return ReplacementRule(
        pattern=re.escape(_TRADEMARK_MARK),
        replacement="",
        kind="trademark mark: deleted",
        token_role="(notice)",
    )


def _word_count(token: str) -> int:
    return len(token.split())


def build_rules(
    repo: Path, forbidden_strings_path: Path
) -> tuple[ReplacementRule, ...]:
    """The complete, ordered rule set for `--replace-text` / `--replace-message`
    over `repo`'s object database, driven by the `token` category of
    `forbidden_strings_path`.

    Order, matching the module docstring exactly:
    1. Given-name exception rules (derived from the full-name token).
    2. The identity-leak email rule.
    3. Per token, longest word-count first; per token, every observed case
       variant; per variant, sub-tiers (a)-(e).
    4. Per observed case variant of the reserved-rights phrase
       (`observed_notice_case_variants`, which tolerates a comment-wrapped
       occurrence where `observed_case_variants` does not), the four
       copyright-notice rules (`notice_rules`) -- **after** every token
       tier, so a notice's attribution has already become this module's own
       replacement vocabulary by the time the notice rule reads it, and the
       one span the notice rule must cross is a known, measured width.
    5. The trademark-mark rule (`trademark_mark_rule`), always exactly one.

    Raises `ValueError` if the loaded token count does not match
    `_TOKEN_ROLES`, or if any row's word count does not match that row's
    `expected_word_count` -- this generator is tied to one measured shape of
    `FITDOCS_FORBIDDEN_STRINGS`, not a general one, and the word-count check
    catches most (not all -- see `_TOKEN_ROLES`'s docstring) row-order
    drift, not only row-count drift. Also raises `ValueError` (propagated
    from `identity_leak_addresses`, via `identity_email_rule`) on either of
    the two genuinely inconsistent identity derivations that function names.

    **`repo` may be any clone.** The identity denylist is derived from
    reachable blob text and the tip tree, both of which every clone carries;
    the unreachable-commit source only ever raises. Measured on the real
    corpus:
    the working repository, a same-filesystem `git clone --mirror` and a
    `git clone --no-local` (exactly the clone design.md `#### HistoryRewrite`
    step 3 and tasks.md 7.2 prescribe) all derive the identical denylist.
    That was NOT true of the first version of this module -- see the module
    docstring's "reachability trap" note for what changed and why.
    """
    tokens = load_tokens(forbidden_strings_path)
    if len(tokens) != len(_TOKEN_ROLES):
        raise ValueError(
            f"expected {len(_TOKEN_ROLES)} token-category rows in "
            f"{forbidden_strings_path}, found {len(tokens)}: this "
            "generator's role table is index-keyed to a measured shape "
            "and does not infer roles for a different one"
        )

    shape_mismatches = [
        (index, _word_count(token), role.expected_word_count)
        for index, (token, role) in enumerate(zip(tokens, _TOKEN_ROLES, strict=True))
        if _word_count(token) != role.expected_word_count
    ]
    if shape_mismatches:
        raise ValueError(
            f"token order/shape drift detected in {forbidden_strings_path}: "
            f"row(s) {[m[0] for m in shape_mismatches]} did not match this "
            "generator's expected per-row word-count shape "
            f"{tuple(r.expected_word_count for r in _TOKEN_ROLES)} (got "
            f"{[m[1] for m in shape_mismatches]}) -- this generator's role "
            "table is index-keyed and does not guess a role assignment for "
            "a reordered file"
        )

    rules: list[ReplacementRule] = []

    full_name_token = next(
        token
        for token, role in zip(tokens, _TOKEN_ROLES, strict=True)
        if role.derive_given_name
    )
    rules.extend(given_name_rules(full_name_token))
    rules.append(identity_email_rule(repo, tokens))

    ordered = sorted(
        zip(tokens, _TOKEN_ROLES, strict=True),
        key=lambda pair: _word_count(pair[0]),
        reverse=True,
    )
    for token, role in ordered:
        for variant in observed_case_variants(repo, token):
            rules.extend(_token_tier_rules(variant, role.family, role.role))

    for variant in observed_notice_case_variants(repo):
        rules.extend(notice_rules(variant))
    rules.append(trademark_mark_rule())

    return tuple(rules)


# --- simulation (for tests and for reviewing the effect without a real run) --


def apply_rules(text: str, rules: Sequence[ReplacementRule]) -> str:
    """Apply `rules` to `text` exactly the way `git filter-repo`'s own
    `ContentCallback.apply_replace_text` applies its `regexes` list: one
    `re.sub` per rule, in order, each seeing the previous rule's output.
    Verified against `git_filter_repo.py` (installed at
    `~/.local/share/uv/tools/git-filter-repo`) rather than assumed -- see
    the module docstring's ordering-tiers preamble.

    This is a pure-Python simulation, not a real `git filter-repo`
    invocation: task 6.4 builds and tests the rule set, task 7.2 is the one
    real run, over the one real repository, with no rollback."""
    result = text
    for rule in rules:
        result = re.sub(rule.pattern, rule.replacement, result)
    return result


def scan_repo_for_rules(repo: Path, rules: Sequence[ReplacementRule]) -> dict[str, str]:
    """`apply_rules` over every blob `enumerate_blob_ids(repo)` finds,
    returning only the blobs the rules actually changed (`blob_id ->
    new_text`) -- an empty result over `HEAD`'s own object database is
    invariant 6 (the tip no-op)."""
    changed: dict[str, str] = {}
    for blob_id in enumerate_blob_ids(repo):
        original = read_blob_text(repo, blob_id)
        updated = apply_rules(original, rules)
        if updated != original:
            changed[blob_id] = updated
    return changed


def scan_commit_messages_for_rules(
    repo: Path, rules: Sequence[ReplacementRule]
) -> dict[str, str]:
    """`apply_rules` over every commit message reachable from any ref,
    returning only the ones the rules actually changed
    (`commit_id -> new_message`)."""
    listed = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    changed: dict[str, str] = {}
    for commit_id in listed:
        original = subprocess.run(
            ["git", "-C", str(repo), "log", "-1", "--format=%B", commit_id],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        updated = apply_rules(original, rules)
        if updated != original:
            changed[commit_id] = updated
    return changed
