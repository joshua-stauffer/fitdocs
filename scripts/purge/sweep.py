"""`ReproductionSweep` inventory builder (task 3.2, design.md `####
ReproductionSweep`, Req 1.2, 1.3, 2.3).

Produces a **classified inventory** of every tracked-file hit found by five
independent passes over the working tree, and nothing else -- this module
does not redact, rename or delete anything. Tasks 3.5-3.12 (Major 1's
redaction tasks) and 4.x (the re-based guards) act on what this module
finds; this module only finds and classifies it.

The five passes, matching tasks.md 3.2's own list:

1. **Token + path sweep** (`scan_content_and_path`) -- the standing
   `ForbiddenStrings` matcher (`tests._forbidden_strings.matches`, imported
   rather than reimplemented) run over tracked file *content* and tracked
   *path names* as two separate surfaces, category-tagged (``token`` /
   ``path``) using `load_categorized_entries` below -- a thin,
   category-preserving twin of `tests._forbidden_strings._parse`, which
   deliberately discards category because its own consumers (the guards)
   never need it back. This module does.
2. **Value matcher sweep** (`run_value_matcher_sweep`) -- `ContentOracle.scan`
   (`tests._content_oracle`) run over tracked file content against the
   generated fingerprint data (`tests._content_fingerprints`). Finds
   reproduced *value tables*; by the oracle's own declared limit
   (`tests/_content_oracle.py` module docstring) it cannot see a formula or
   rule written symbolically -- pass 3 exists for exactly that gap.
3. **Symbolic-reproduction probe sweep** (`run_symbolic_probe_sweep`) -- a
   curated, fixed-string probe list (`SYMBOLIC_PROBES` below) for the load
   formula, the discount-generating rule and the worked-example vectors
   written as prose/pseudocode rather than as a table the oracle would
   catch. Every probe string was checked at authoring time against the whole
   tracked tree for collisions with unrelated domain vocabulary (TRIMP,
   Coggan power zones) that also appears in this codebase.
4. **Identity probe sweep** (`run_identity_probe_sweep`) -- a generic
   email-shaped `git grep -P` probe, deliberately carrying no literal
   address of its own (see the function docstring) -- the mechanism Req 5 /
   design.md `#### ContactRedaction` names as "all three personal
   identifiers including the git-constructed username-and-machine-name
   form".
5. **Stale-pointer enumeration** (`run_stale_pointer_sweep`), independent of
   pass 1's own path-category matching -- design.md `#### ReproductionSweep`
   requires this be its *own* enumeration ("no oracle covers it"), run via
   `git grep -lF` directly rather than through `tests._forbidden_strings`, so
   the token/path in-process matcher and the stale-pointer check are two
   independently-implemented mechanisms rather than one call site whose
   own bug would go uncaught by "re-running reproduces the same hit set".

A sixth, ad-hoc pass (`run_basename_probe_sweep`) exists for a documented
gap in pass 1/5's own match data: two of the five removed-path fragments in
`FITDOCS_FORBIDDEN_STRINGS` have basenames that carry no identifying token
(`paces_by_zones.csv`, `sha-rewrite-map-2026-07-26.tsv`), so a tracked file
that references either bare or under a different path prefix is invisible
to a search keyed on the full path string. This is an ad-hoc probe, not a
new match-data entry -- see `_TOKEN_FREE_BASENAME_PROBES`'s docstring for
why adding them to the tsv would be wrong.

Every `git grep` call uses `-F` (fixed string) or `-P` (Perl regex), never
`-E`: this git build's extended-regex mode does not honour `\\b` and returns
empty, which reads as a clean sweep (`change-protocol.md` Fixture
Discrimination; restated in design.md `#### ReproductionSweep`).

The universe is `git ls-files` (`tracked_files` below), never a filesystem
walk -- `tests._forbidden_strings.scan_tree`'s own docstring states plainly
that it does no tracked/ignored filtering and is the caller's job to
restrict; walking a working tree containing `.venv/` with that function
would be both wrong (out of universe) and prohibitively slow, so this module
iterates the tracked-file list directly rather than post-filtering a full
`scan_tree` walk.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tests._content_oracle import scan
from tests._forbidden_strings import ForbiddenStrings, matches

# --- category-preserving match-data loader -----------------------------------


@dataclass(frozen=True)
class CategorizedEntry:
    """One line of the `FITDOCS_FORBIDDEN_STRINGS` file, category kept.

    `tests._forbidden_strings._parse` deliberately discards category ("the
    category is metadata only" -- its own module docstring); this
    classified inventory needs it back, to report which sweep (token vs
    path) produced which hit, so this is a second, narrow parse of the same
    file format rather than a change to that module's contract.
    """

    category: str
    value: str


def parse_categorized_entries(text: str) -> tuple[CategorizedEntry, ...]:
    """Every non-blank, non-`#`-comment line of `text` as a
    `CategorizedEntry`, in file order.

    Mirrors `tests._forbidden_strings._parse`'s line-filtering rules
    exactly (blank lines and `#`-prefixed lines ignored; a line with no tab
    is taken whole, under category ``"uncategorized"`` since the format
    permits an untagged line).
    """
    entries: list[CategorizedEntry] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        category, separator, rest = stripped.partition("\t")
        if separator:
            entries.append(CategorizedEntry(category=category, value=rest))
        else:
            entries.append(CategorizedEntry(category="uncategorized", value=stripped))
    return tuple(entries)


def load_categorized_entries(path: Path) -> tuple[CategorizedEntry, ...]:
    """`parse_categorized_entries` over the file at `path`."""
    return parse_categorized_entries(path.read_text(encoding="utf-8"))


def entries_by_category(
    entries: Sequence[CategorizedEntry],
) -> dict[str, tuple[str, ...]]:
    """Group `entries`' values by category, values in file order within
    each category. A `dict` (not e.g. a `Counter`) because category order
    of first appearance is not load-bearing here -- every category is
    swept independently regardless of position."""
    grouped: dict[str, list[str]] = {}
    for entry in entries:
        grouped.setdefault(entry.category, []).append(entry.value)
    return {category: tuple(values) for category, values in grouped.items()}


# --- universe: git ls-files ---------------------------------------------------


def tracked_files(repo_root: Path) -> tuple[Path, ...]:
    """Every path `git ls-files` reports for `repo_root`, as absolute
    paths. This -- not a filesystem walk -- is the sweep's universe
    (design.md `#### ReproductionSweep`: "The universe is `git ls-files`")."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    names = [name for name in result.stdout.decode("utf-8").split("\0") if name]
    return tuple(repo_root / name for name in names)


# --- hit / unreadable-file records --------------------------------------------


@dataclass(frozen=True)
class SweepHit:
    """One match found by one pass. `matched` is the literal substring for
    passes where recording it adds no new exposure beyond what the
    out-of-repository match data already holds (token, path,
    stale_pointer, symbolic_probe, basename_probe); it is deliberately
    empty for `value_matcher` (the oracle never exposes the matched text)
    and for `identity_probe` (this module carries no literal personal
    address of its own -- see `run_identity_probe_sweep`)."""

    sweep: str
    relative_path: str
    surface: str
    matched: str
    note: str = ""


@dataclass(frozen=True)
class UnreadableFile:
    """A tracked file whose content could not be read as UTF-8 text, so no
    content-surface hit could be produced for it -- recorded explicitly
    rather than silently yielding no hit and no report (the
    `tests._forbidden_strings.scan_tree` docstring's own named risk: "an
    unreadable file whose content carries a forbidden value yields no hit
    and no report")."""

    relative_path: str
    reason: str


# --- pass 1: token + path sweep ------------------------------------------------


def scan_content_and_path(
    files: Sequence[Path],
    root: Path,
    entries: Sequence[CategorizedEntry],
) -> tuple[tuple[SweepHit, ...], tuple[UnreadableFile, ...]]:
    """Pass 1: `tests._forbidden_strings.matches` run over every tracked
    file's content and path name, once per category in `entries`, so a
    content hit and a path-name hit are both recorded and tagged with which
    category (``token`` / ``path``) matched.

    A file that cannot be decoded as UTF-8 or cannot be opened at all
    contributes only a path-surface scan (its path name is still text) and
    an `UnreadableFile` record; it never silently yields nothing.
    """
    grouped = entries_by_category(entries)
    forbidden_by_category = {
        category: ForbiddenStrings(values=values, source=root)
        for category, values in grouped.items()
        if values
    }

    hits: list[SweepHit] = []
    unreadable: list[UnreadableFile] = []
    for path in sorted(files):
        relative = str(path.relative_to(root))

        for category, forbidden in forbidden_by_category.items():
            for value in matches(relative, forbidden):
                hits.append(
                    SweepHit(
                        sweep=category,
                        relative_path=relative,
                        surface="path",
                        matched=value,
                    )
                )

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            unreadable.append(UnreadableFile(relative_path=relative, reason=str(exc)))
            continue
        except OSError as exc:
            unreadable.append(UnreadableFile(relative_path=relative, reason=str(exc)))
            continue

        for category, forbidden in forbidden_by_category.items():
            for value in matches(content, forbidden):
                hits.append(
                    SweepHit(
                        sweep=category,
                        relative_path=relative,
                        surface="content",
                        matched=value,
                    )
                )

    return tuple(hits), tuple(unreadable)


# --- pass 2: value matcher sweep -----------------------------------------------


def run_value_matcher_sweep(
    files: Sequence[Path],
    root: Path,
    *,
    fingerprints: frozenset[str],
    window_lengths: frozenset[int],
    salt: bytes,
) -> tuple[tuple[SweepHit, ...], tuple[UnreadableFile, ...]]:
    """Pass 2: `ContentOracle.scan` over every tracked file's content.
    Reports only that a file matched -- the oracle is one-way by
    construction, so this pass never has a value to record in `matched`.

    A file that cannot be decoded as UTF-8 or cannot be opened at all
    contributes an `UnreadableFile` record and no hit -- the same
    non-silent posture `scan_content_and_path` documents. Both
    `UnicodeDecodeError` and `OSError` are recorded here.
    """
    hits: list[SweepHit] = []
    unreadable: list[UnreadableFile] = []
    for path in sorted(files):
        relative = str(path.relative_to(root))
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            unreadable.append(UnreadableFile(relative_path=relative, reason=str(exc)))
            continue
        except OSError as exc:
            unreadable.append(UnreadableFile(relative_path=relative, reason=str(exc)))
            continue
        if scan(content, fingerprints, window_lengths, salt):
            hits.append(
                SweepHit(
                    sweep="value_matcher",
                    relative_path=relative,
                    surface="content",
                    matched="",
                )
            )
    return tuple(hits), tuple(unreadable)


# --- git grep helper, shared by passes 3-6 -------------------------------------


def _git_grep_files(root: Path, args: Sequence[str]) -> tuple[str, ...]:
    """Repo-relative tracked paths `git grep <args>` reports, one call.

    `git grep` exits 1 for "no match" and >=2 for a genuine failure (a bad
    pattern, not a git repository, etc.) -- these are NOT the same outcome
    and must not collapse into the same empty tuple: exit 1 returns `()`;
    any other nonzero exit raises `RuntimeError` naming the command and
    stderr, so a broken invocation is loud rather than silently read as "no
    hits" (`change-protocol.md`'s swallowed-failure trap).
    """
    result = subprocess.run(
        ["git", "grep", *args],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode == 1:
        return ()
    if result.returncode != 0:
        raise RuntimeError(
            f"git grep {list(args)!r} failed (exit {result.returncode}): "
            f"{result.stderr.decode('utf-8', errors='replace')}"
        )
    raw = result.stdout.decode("utf-8", errors="replace")
    return tuple(name for name in raw.split("\0") if name)


def git_grep_fixed_files(root: Path, needle: str) -> tuple[str, ...]:
    """Every tracked file (repo-relative path) whose content contains
    `needle` literally. Fixed-string (`-F`) mode -- never `-E` (see module
    docstring)."""
    return _git_grep_files(root, ["-lF", "-z", "--", needle])


# --- pass 3: symbolic-reproduction probe sweep ---------------------------------

SYMBOLIC_PROBES: tuple[tuple[str, str], ...] = (
    ("load formula", "points/min"),
    ("load formula", " ppm"),
    ("per-repeat adjustment", "per-repeat adjustment"),
    ("discount-generating rule", "discount lookup"),
    ("discount-generating rule", "discount-generating rule"),
    ("discount-generating rule", "exact-match discount"),
    ("worked-example vector", "workbook vector"),
    ("pace lookup rows", "pace lookup"),
    ("zone table", "zone table"),
)
"""Fixed strings distinctive to the withdrawn methodology's symbolic
reproductions -- Requirement 1.2's own vocabulary (zone table,
points-per-minute, load formula, per-repeat adjustment, discount value,
discount-generating rule, pace lookup) plus phrasing observed directly in
the one dense site this probe set located
(`.kiro/specs/training-load/research.md`, its "methodology extraction"
research-log entry).

Deliberately excludes the bare performance-level abbreviation used
elsewhere in this codebase for a legitimate, unrelated purpose: measured at
authoring time, that abbreviation returns 22 hits across the tree, most of
them the athlete-profile field `tests/load/test_profile.py`'s own
`AthleteField` (a lowercase `garmin.<abbreviation>` config key) -- live
code, not a reproduction. The spelled-out phrase the abbreviation stands
for already contains one of `FITDOCS_FORBIDDEN_STRINGS`'s ``token``-category
values and is caught by pass 1's token sweep instead, so this probe set
does not need to carry either form itself, and does not carry either as a
*bare* word: this module's own tokens/paths were re-measured against the
real match data (never a hand-written pattern) rather than assumed, and
this module carries no ``token``- or ``path``-category value literally
anywhere, including in `_TOKEN_FREE_BASENAME_PROBES`'s own docstring, which
describes the two basename-only entries it names without spelling out their
full path (task 6.3 rewrote that docstring for exactly this reason). It is
not the "carries no literal value of its own" posture
`run_identity_probe_sweep` documents below -- that posture is about never
writing this module's OWN synthesized detection literal (an email
address); it does not extend to naming an already-established path
fragment, it is simply that no such naming happens to occur here any more.

Each probe was checked at authoring time (`git grep -nF`) against the whole
tracked tree for collisions with this codebase's *other* domain vocabulary
(TRIMP, Coggan power zones, `tests/metrics/test_worked_examples.py`) before
being kept."""


def run_symbolic_probe_sweep(root: Path) -> tuple[SweepHit, ...]:
    """Pass 3: `SYMBOLIC_PROBES`, each run through `git_grep_fixed_files`."""
    hits: list[SweepHit] = []
    for label, needle in SYMBOLIC_PROBES:
        for relative in git_grep_fixed_files(root, needle):
            hits.append(
                SweepHit(
                    sweep="symbolic_probe",
                    relative_path=relative,
                    surface="content",
                    matched=needle,
                    note=label,
                )
            )
    return tuple(hits)


# --- pass 4: identity probe sweep ----------------------------------------------

_EMAIL_PATTERN = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

_SAFE_EMAIL_DOMAINS: tuple[str, ...] = (
    "users.noreply.github.com",
    "github.com",
    "example.com",
)
"""Domains an email-shaped match under is classified as NOT a personal
identifier: the maintainer's public GitHub-noreply alias (the address this
purge's Req 5 explicitly does not target), the literal `git@github.com`
remote-URL idiom, and the `example.com` placeholder domain RFC 2606
reserves for exactly this purpose (used in this repository's own synthetic
test fixtures, e.g. `tests/purge/test_rewrite_map_extraction.py`)."""


def _classify_email_domain(email: str) -> str:
    domain = email.rsplit("@", 1)[-1].lower()
    if domain in _SAFE_EMAIL_DOMAINS:
        return "public-or-placeholder"
    if domain.endswith(".local"):
        return "git-constructed-form-candidate"
    return "personal-address-candidate"


def run_identity_probe_sweep(root: Path) -> tuple[SweepHit, ...]:
    """Pass 4: a generic email-shaped `git grep -P` probe over tracked
    content, for "all three personal identifiers including the
    git-constructed username-and-machine-name form" (tasks.md 3.2; design.md
    `#### ContactRedaction`).

    Carries no literal address of its own -- rather than hardcoding the
    third party's address, the maintainer's address, or a guessed
    `<username>@<machine-name>.local` form (none of which belong in a
    module this purge ships), this probes for the general SHAPE any email
    address takes and classifies each match by its domain
    (`_classify_email_domain`) into a category, never storing the address
    itself in a `SweepHit` (`matched` is always ``""`` for this sweep) --
    the same "no literal value" posture `scripts/purge/fingerprints.py`
    keeps for its results record, applied here even though this inventory
    is itself out-of-repository.
    """
    result = subprocess.run(
        ["git", "grep", "-nPoI", "--", _EMAIL_PATTERN],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 1:
        return ()
    if result.returncode != 0:
        raise RuntimeError(
            f"git grep -nPoI (identity probe) failed (exit {result.returncode}): "
            f"{result.stderr}"
        )

    hits: list[SweepHit] = []
    for line in result.stdout.splitlines():
        relative, _, remainder = line.partition(":")
        _lineno, _, email = remainder.partition(":")
        if not relative or not email:
            continue
        category = _classify_email_domain(email)
        hits.append(
            SweepHit(
                sweep="identity_probe",
                relative_path=relative,
                surface="content",
                matched="",
                note=category,
            )
        )
    return tuple(hits)


# --- pass 5: stale-pointer enumeration (Req 2.3) -------------------------------


def run_stale_pointer_sweep(
    root: Path, path_fragments: Sequence[str]
) -> tuple[SweepHit, ...]:
    """Pass 5: `git grep -lF` over `path_fragments` (the ``path``-category
    values from `FITDOCS_FORBIDDEN_STRINGS`), independent of pass 1's
    in-process `matches()` call -- design.md `#### ReproductionSweep`: "Req
    2.3 gets its own enumeration, because no oracle covers it", run as a
    *second*, independently-implemented mechanism (external `git grep`
    subprocess vs pass 1's in-process string search) so a bug in one is not
    invisible to the other."""
    hits: list[SweepHit] = []
    for fragment in path_fragments:
        for relative in git_grep_fixed_files(root, fragment):
            hits.append(
                SweepHit(
                    sweep="stale_pointer",
                    relative_path=relative,
                    surface="content",
                    matched=fragment,
                )
            )
    return tuple(hits)


# --- ad-hoc pass 6: token-free basename probes (documented gap) ---------------

_TOKEN_FREE_BASENAME_PROBES: tuple[str, ...] = (
    "paces_by_zones.csv",
    "sha-rewrite-map-2026-07-26.tsv",
)
"""The two `FITDOCS_FORBIDDEN_STRINGS` ``path``-category entries whose
*basename alone* carries no identifying token -- unlike the other two
removed-file basenames, which each still embed one of the ``token``-category
values (so pass 1's token sweep already reaches a bare mention of either),
neither of these two basenames does. One of the two full path entries is
itself a substring of a separate, shorter ``path``-category entry naming its
containing directory, so a differently-prefixed mention of the file can
still fall back on that shorter entry; the other full path entry has no
such shorter sibling to fall back on for files that reference it under a
different prefix.

Run here as an ad-hoc probe over the bare basename, NOT added as a new
entry to the match data: several tracked files this purge's own Req 2.5
deliberately retains (closed queue items narrating the file's own removal)
would then trip task 4.3's absence guard for holding a name the purge
elects to keep, which would be wrong -- the purge retains the mention, not
the file."""


def run_basename_probe_sweep(root: Path) -> tuple[SweepHit, ...]:
    """Pass 6 (ad hoc): `_TOKEN_FREE_BASENAME_PROBES`, each run through
    `git_grep_fixed_files`."""
    hits: list[SweepHit] = []
    for basename in _TOKEN_FREE_BASENAME_PROBES:
        for relative in git_grep_fixed_files(root, basename):
            hits.append(
                SweepHit(
                    sweep="basename_probe",
                    relative_path=relative,
                    surface="content",
                    matched=basename,
                )
            )
    return tuple(hits)


# --- classification -------------------------------------------------------------

DISPOSITIONS: tuple[str, ...] = (
    "stale_pointer",
    "dead_packaging_entry",
    "guard",
    "retained_historical_subject",
    "ignore_rule_stale_pointer",
    "reproduction_pending_redaction",
    "identity_pending_erasure",
    "judged_not_a_reproduction",
    "sweep_tooling_self_reference",
    "public_or_placeholder_identity",
)
"""Every disposition a `ClassifiedHit` may carry. The first five are
design.md `#### ReproductionSweep`'s own taxonomy for the Req 2.3
stale-pointer enumeration ((a) stale pointer, (b) dead packaging entry,
(c) guard, (d) historical subject retained under Req 2.5, (e) ignore rule
with a stale pointer). The remaining five extend that taxonomy to the other
four passes' hits, which are not references to a removed path and so do
not fit design.md's five classes by themselves:

- `reproduction_pending_redaction` -- a live reproduction of the withdrawn
  methodology (value table, formula, discount rule), still present because
  Major 1's redaction tasks (3.5-3.12) have not yet run. This task (3.2)
  finds and records it; it does not fix it.
- `identity_pending_erasure` -- a personal-identifier candidate (Req 5 /
  11), likewise awaiting a later task (`ContactRedaction` / `IdentityErasure`).
- `judged_not_a_reproduction` -- design.md's own "judged not reproductions,
  recorded so the judgement is reviewable" bucket (bare worked-example
  scalars, input names, withdrawn requirement stubs) or, for this task's
  own vocabulary/vocabulary-description hits, a spec document naming a
  *category* of reproduced material (Requirement 1.2's own acceptance-
  criteria wording) rather than reproducing an instance of it.
- `sweep_tooling_self_reference` -- one of the purge's own new files (task
  2.4 / 3.1 / this task), which legitimately names a removed path or token
  as part of doing the purge and post-dates design.md's modified-files
  table (Trap 3 in this task's own brief).
- `public_or_placeholder_identity` -- an identity-probe hit classified
  `public-or-placeholder` by `_classify_email_domain` (the GitHub-noreply
  alias, the `git@github.com` remote idiom, or the `example.com` synthetic
  fixture placeholder) -- not a personal identifier Req 5 targets.
"""


@dataclass(frozen=True)
class ClassifiedHit:
    """One `SweepHit`, plus the disposition assigned to it and a one-line
    rationale a reviewer can check without re-deriving the judgement."""

    hit: SweepHit
    disposition: str
    rationale: str

    def __post_init__(self) -> None:
        if self.disposition not in DISPOSITIONS:
            raise ValueError(
                f"unknown disposition {self.disposition!r}; "
                f"must be one of {DISPOSITIONS}"
            )


def classify_hit(
    hit: SweepHit,
    overrides: dict[tuple[str, str], tuple[str, str]],
    fine_overrides: dict[tuple[str, str, str], tuple[str, str]] = {},  # noqa: B006
) -> ClassifiedHit:
    """Classify one `SweepHit`.

    Lookup order, most to least specific:

    1. `fine_overrides`, keyed ``(sweep, relative_path, matched)`` -- for the
       rare file that needs a *different* disposition for different matched
       values within the same sweep pass.
    2. `overrides`, keyed ``(sweep, relative_path)`` -- one disposition for
       every hit a given sweep pass produced in a given file; the shape
       every file this task's own sweep run actually produced turned out to
       need, with `fine_overrides` as the documented exception mechanism
       rather than the common case.
    3. Two sweeps carry a built-in auto-rule, needing no per-file override:
       every `value_matcher` hit is `reproduction_pending_redaction` (the
       oracle only fires on a dense, format-matching numeric window, so any
       hit is a detected reproduction by construction); an `identity_probe`
       hit `_classify_email_domain` already tagged `public-or-placeholder`
       is `public_or_placeholder_identity`, and one tagged
       `personal-address-candidate` or `git-constructed-form-candidate` is
       `identity_pending_erasure` -- the probe's own mechanism already did
       the classification work.
    4. Otherwise: raises. This task's own gate against "not in the table
       silently means not considered" -- an un-reviewed hit must be loud,
       never silently folded into a default disposition.
    """
    fine_key = (hit.sweep, hit.relative_path, hit.matched)
    if fine_key in fine_overrides:
        disposition, rationale = fine_overrides[fine_key]
        return ClassifiedHit(hit=hit, disposition=disposition, rationale=rationale)

    coarse_key = (hit.sweep, hit.relative_path)
    if coarse_key in overrides:
        disposition, rationale = overrides[coarse_key]
        return ClassifiedHit(hit=hit, disposition=disposition, rationale=rationale)

    if hit.sweep == "value_matcher":
        return ClassifiedHit(
            hit=hit,
            disposition="reproduction_pending_redaction",
            rationale="ContentOracle only flags a dense, format-matching numeric "
            "window -- unlike the vocabulary-only symbolic_probe hits, any "
            "value_matcher hit is by construction a detected reproduction, not "
            "a mention of one",
        )
    if hit.sweep == "identity_probe" and hit.note == "public-or-placeholder":
        return ClassifiedHit(
            hit=hit,
            disposition="public_or_placeholder_identity",
            rationale="email-shaped match classified public-or-placeholder by "
            "_classify_email_domain (github-noreply alias, git@github.com "
            "remote idiom, or example.com synthetic fixture placeholder)",
        )
    if hit.sweep == "identity_probe" and hit.note in (
        "personal-address-candidate",
        "git-constructed-form-candidate",
    ):
        return ClassifiedHit(
            hit=hit,
            disposition="identity_pending_erasure",
            rationale=f"email-shaped match classified {hit.note} by "
            "_classify_email_domain -- Req 5 / #### ContactRedaction erases it; "
            "this task only records the location",
        )

    raise KeyError(
        f"no classification override for hit {coarse_key!r} (matched={hit.matched!r}) "
        "-- every hit this sweep produces must be classified explicitly (see "
        "classify_hit's docstring); an un-reviewed hit must not silently fall "
        "through to a default disposition"
    )


def classify_hits(
    hits: Sequence[SweepHit],
    overrides: dict[tuple[str, str], tuple[str, str]],
    fine_overrides: dict[tuple[str, str, str], tuple[str, str]] = {},  # noqa: B006
) -> tuple[ClassifiedHit, ...]:
    """`classify_hit` over every hit in `hits`, in order."""
    return tuple(classify_hit(hit, overrides, fine_overrides) for hit in hits)


# --- out-of-repository artifact: write / read round trip ----------------------

_INVENTORY_COLUMNS: tuple[str, ...] = (
    "sweep",
    "relative_path",
    "surface",
    "matched",
    "note",
    "disposition",
    "rationale",
)


def render_inventory_tsv(classified: Sequence[ClassifiedHit]) -> str:
    """Render `classified` as a header row plus one tab-separated data row
    per hit, in the given order -- the same tsv shape
    `FITDOCS_FORBIDDEN_STRINGS` and the extracted rewrite-map rows already
    use for an out-of-repository artifact.

    Raises `ValueError` if any field contains a tab or newline, which would
    silently corrupt the row structure rather than merely looking odd --
    every field here is short, controlled prose, so this should never fire,
    but a field that did contain one must fail loudly, not produce a
    malformed row `parse_inventory_tsv` cannot read back correctly.
    """
    lines = ["\t".join(_INVENTORY_COLUMNS)]
    for item in classified:
        fields = (
            item.hit.sweep,
            item.hit.relative_path,
            item.hit.surface,
            item.hit.matched,
            item.hit.note,
            item.disposition,
            item.rationale,
        )
        for field in fields:
            if "\t" in field or "\n" in field:
                raise ValueError(
                    f"inventory field contains a tab or newline, which would "
                    f"corrupt the tsv row structure: {field!r}"
                )
        lines.append("\t".join(fields))
    return "\n".join(lines) + "\n"


def write_inventory(classified: Sequence[ClassifiedHit], out_path: Path) -> None:
    """Write `render_inventory_tsv(classified)` to `out_path`, creating
    parent directories as needed."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_inventory_tsv(classified), encoding="utf-8")


def parse_inventory_tsv(text: str) -> tuple[dict[str, str], ...]:
    """Read back exactly what `render_inventory_tsv` wrote: one dict per
    data row, keyed by `_INVENTORY_COLUMNS`, in file order. A caller that
    needs `SweepHit`/`ClassifiedHit` objects back can reconstruct them from
    these dicts; kept as plain dicts here so a row with an unrecognized
    `disposition` (e.g. read from a stale artifact after `DISPOSITIONS` has
    changed) can still be read back and inspected rather than raising on
    load.
    """
    lines = text.splitlines()
    if not lines:
        return ()
    header = lines[0].split("\t")
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        values = line.split("\t")
        rows.append(dict(zip(header, values, strict=True)))
    return tuple(rows)


def read_inventory(path: Path) -> tuple[dict[str, str], ...]:
    """`parse_inventory_tsv` over the file at `path`."""
    return parse_inventory_tsv(path.read_text(encoding="utf-8"))


# --- default classification rules, hand-reviewed against a real sweep run -----

GUARD_FILES: frozenset[str] = frozenset(
    {
        "tests/load/test_packaging.py",
        "tests/test_docs_guarantees.py",
        "tests/test_contributing_calculators_doc.py",
        "tests/test_cli.py",
        "tests/test_forbidden_strings_source.py",
    }
)
"""Design.md `#### ReintroductionGuards`' own file list: standing
re-introduction guards that read a token or a removed-path fragment on
purpose, as detection data -- disposition (c), `guard`, re-based (not
redacted away) by Major 4."""

SWEEP_TOOLING_FILES: frozenset[str] = frozenset(
    {
        "scripts/purge/fingerprints.py",
        "tests/purge/test_fingerprints.py",
        "tests/purge/test_tree_removal.py",
        "scripts/purge/rewrite_map.py",
        "tests/purge/test_rewrite_map_extraction.py",
        # This task's (3.2) own three new files. Omitting these three is
        # exactly Trap 3 restated: task 3.1's tooling is listed above, but
        # once this task's own files are tracked, `run_full_sweep`'s
        # universe (`git ls-files`) reaches them too, and without an entry
        # here they would fall through `_token_disposition`'s default
        # branch (`identity_pending_erasure`) or `_reference_disposition`'s
        # default (`stale_pointer`) -- both wrong for tooling that
        # legitimately names a token/path as detection data, not as a
        # reproduction or a stale reference.
        "scripts/purge/sweep.py",
        "scripts/purge/build_sweep_inventory.py",
        "tests/purge/test_sweep.py",
    }
)
"""The purge's own tooling, all new since design.md's modified-files table
was written (task 2.4 / 3.1 / this task's own sibling module) -- Trap 3 in
this task's own brief: these files legitimately name a removed path or
token as part of *doing* the purge (a source path to fingerprint, a needle
set to assert absence against, a docstring recording what was extracted
before deletion), post-date the table, and must be classified rather than
silently dropped for not appearing in it."""

_CLOSED_QUEUE_PREFIX = ".kiro/queue/closed/"

_SYMBOLIC_REPRODUCTION_SITE = ".kiro/specs/training-load/research.md"
"""The one file `SYMBOLIC_PROBES` located carrying an actual reproduction
(its "methodology extraction" research-log entry: real zone counts, the
formula shape, the discount rule's structure, and the workbook test-vector
values) -- every other file the same probes hit only *names the category*
of reproduced material (this spec's own Requirement 1.2 wording, or a
research-log/brief description of what the writeup covered), which is
`judged_not_a_reproduction` (design.md `#### ReproductionSweep`'s own
"judged not reproductions, recorded so the judgement is reviewable"
bucket, extended here to this task's vocabulary hits)."""


def _reference_disposition(relative_path: str) -> tuple[str, str]:
    """Disposition for a `path`/`stale_pointer`/`basename_probe` hit in
    `relative_path` -- design.md `#### ReproductionSweep`'s five-class
    taxonomy for the Req 2.3 stale-pointer enumeration, applied per file."""
    if relative_path == ".gitignore":
        return (
            "ignore_rule_stale_pointer",
            "the ignore rule itself (Req 2.4) is retained; only its pointer "
            "and explanatory comment -- which also reproduces a copyright "
            "notice, Req 11.4 -- need correcting",
        )
    if relative_path in GUARD_FILES:
        return (
            "guard",
            "standing re-introduction guard; re-based onto the shared "
            "matchers by Major 4, not redacted away",
        )
    if relative_path in SWEEP_TOOLING_FILES:
        return (
            "sweep_tooling_self_reference",
            "purge tooling created after design.md's modified-files table; "
            "the path reference is load-bearing to the tooling's own job",
        )
    if relative_path.startswith(_CLOSED_QUEUE_PREFIX):
        return (
            "retained_historical_subject",
            "closed queue item narrating a past, resolved finding about the "
            "removed path -- Req 2.5 retains the mention once token-free",
        )
    return (
        "stale_pointer",
        "live pointer to a path that no longer exists; needs correcting "
        "under Req 2.3/2.4 (Major 1's redaction tasks)",
    )


def _token_disposition(relative_path: str) -> tuple[str, str]:
    """Disposition for a `token` hit in `relative_path`."""
    if relative_path in GUARD_FILES:
        return (
            "guard",
            "standing re-introduction guard; token literal is its own "
            "detection data, re-based (not redacted) by Major 4",
        )
    if relative_path in SWEEP_TOOLING_FILES:
        return (
            "sweep_tooling_self_reference",
            "purge tooling created after design.md's modified-files table",
        )
    return (
        "identity_pending_erasure",
        "identifying token pending erasure under Req 11 (IdentityErasure); "
        "this task only records the location",
    )


def _symbolic_disposition(relative_path: str) -> tuple[str, str]:
    """Disposition for a `symbolic_probe` hit in `relative_path`."""
    if relative_path == _SYMBOLIC_REPRODUCTION_SITE:
        return (
            "reproduction_pending_redaction",
            "the dense symbolic-reproduction site this probe set exists to "
            "find (design.md `#### ReproductionSweep`); redacted by task 3.6, "
            "not by this task",
        )
    return (
        "judged_not_a_reproduction",
        "names the *category* of reproduced material (this spec's own "
        "Requirement 1.2 wording, or a description of what the writeup "
        "covered) rather than reproducing an instance of it",
    )


def build_default_overrides(
    files_by_sweep: dict[str, frozenset[str]],
) -> dict[tuple[str, str], tuple[str, str]]:
    """The hand-reviewed classification rules above, applied to every
    ``(sweep, relative_path)`` pair `files_by_sweep` names -- one call site
    for the rules `_reference_disposition` / `_token_disposition` /
    `_symbolic_disposition` encode, so `classify_hit`'s `overrides` table is
    built from a reviewable function rather than a several-hundred-line
    literal.

    `files_by_sweep` maps a sweep name to the set of relative paths that
    sweep actually hit in a real run -- callers pass the real, freshly
    measured sets (never a hardcoded guess) so this stays correct as the
    tree drifts.
    """
    overrides: dict[tuple[str, str], tuple[str, str]] = {}
    for sweep_name in ("path", "stale_pointer", "basename_probe"):
        for relative_path in files_by_sweep.get(sweep_name, frozenset()):
            overrides[(sweep_name, relative_path)] = _reference_disposition(
                relative_path
            )
    for relative_path in files_by_sweep.get("token", frozenset()):
        overrides[("token", relative_path)] = _token_disposition(relative_path)
    for relative_path in files_by_sweep.get("symbolic_probe", frozenset()):
        overrides[("symbolic_probe", relative_path)] = _symbolic_disposition(
            relative_path
        )
    return overrides


# --- one-shot orchestration ----------------------------------------------------


def run_full_sweep(
    root: Path,
    *,
    forbidden_strings_path: Path,
    fingerprints: frozenset[str],
    window_lengths: frozenset[int],
    salt: bytes,
) -> tuple[tuple[ClassifiedHit, ...], tuple[UnreadableFile, ...]]:
    """Run all six passes over `root`'s tracked files and classify every
    hit. The one-shot entry point task 3.2's status report and
    `scripts/purge/build_sweep_inventory.py` (the CLI-less driver script)
    both call.

    Deterministic: `tracked_files` and every `git grep` call is read-only,
    so calling this twice in a row over an unchanged tree reproduces the
    same hit set (tasks.md 3.2's own observable).
    """
    files = tracked_files(root)
    entries = load_categorized_entries(forbidden_strings_path)
    path_fragments = entries_by_category(entries).get("path", ())

    tp_hits, tp_unreadable = scan_content_and_path(files, root, entries)
    vm_hits, vm_unreadable = run_value_matcher_sweep(
        files, root, fingerprints=fingerprints, window_lengths=window_lengths, salt=salt
    )
    sym_hits = run_symbolic_probe_sweep(root)
    id_hits = run_identity_probe_sweep(root)
    sp_hits = run_stale_pointer_sweep(root, path_fragments)
    bn_hits = run_basename_probe_sweep(root)

    all_hits = tp_hits + vm_hits + sym_hits + id_hits + sp_hits + bn_hits
    unreadable = tp_unreadable + vm_unreadable

    mutable_files_by_sweep: dict[str, set[str]] = {}
    for hit in all_hits:
        mutable_files_by_sweep.setdefault(hit.sweep, set()).add(hit.relative_path)
    files_by_sweep: dict[str, frozenset[str]] = {
        sweep_name: frozenset(paths)
        for sweep_name, paths in mutable_files_by_sweep.items()
    }

    overrides = build_default_overrides(files_by_sweep)
    classified = classify_hits(all_hits, overrides)
    return classified, unreadable
