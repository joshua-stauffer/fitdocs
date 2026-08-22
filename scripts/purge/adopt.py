"""`HistoryReplacement`'s carry-over checklist, the identity precondition, and
the scratch-to-target move (design.md `#### HistoryReplacement`, Req 5.3,
7.3, 11.13).

**Re-scoped at task 7.3 from the retired `CloneAdoption` mechanism to
Decision 7's fixed constraints** (maintainer, 2026-08-17): the working
directory and its untracked material are never moved and never deleted, so
none of it needs a carry-over item any more -- `data/`, the Req 1.7 source
workbooks, the data-root pointer file and the root `agent-log` symlink all
stay exactly where they are through the `.git` swap. What *does* move is
`.git` itself, swapped for a fresh one built from a `--no-local` clone of the
certified tip, with the old `.git` archived rather than deleted. The
checklist's universe is therefore now **the old `.git` directory's own
non-standard entries**, enumerated at run time by `build_checklist`, with the
shared agent log first among them -- it lives at
`$(git rev-parse --git-common-dir)/agent-log`, so the swap moves it out from
under every session that depends on it, and it is untracked, exists in one
place, and is the record of how this purge was coordinated.

**The checklist is asserted, not remembered.** `assert_carry_over` walks
every `CarryOverItem` a caller hands it and raises `CarryOverError` naming
*every* item it could not accept -- never just the first, never a silent
pass over an empty item list (an empty sequence raises too, rather than
trivially "passing" having asserted nothing), and never a blank path
(`Path("")` normalises to `Path('.')`, whose `.exists()` is always `True`;
a blank path is treated as missing rather than as a satisfied item).

**Existence is not transfer, and existence at the source is precisely the
false positive** (`.kiro/queue/2026-08-09-adopt-checklist-can-destroy-`
`carried-material.md`, originally raised against the retired mechanism and
still the reasoning this module runs on). The `HistoryReplacement` swap moves
the old `.git` directory to an out-of-tree archive; a checklist that only
asked `Path.exists()` about a caller-supplied root would pass every
assertion against the *doomed* `.git` -- its contents really do still exist
at that moment -- moments before the swap moves it out from under the
checklist's own destination paths. The shared agent log is untracked, exists
in exactly one place on disk and in no commit, and the fresh `--no-local`
clone that becomes the new `.git` carries only reachable git objects, so it
carries none of it. This module therefore asks a different question:

- `assert_carry_over` takes a **non-defaultable, keyword-only
  `doomed_root`** -- the directory the caller is about to destroy -- and
  refuses any item whose path resolves inside it. Naming the doomed root is
  not optional, so "which root did I build this against?" cannot be left
  implicit at the call site.
- A `CarryOverItem` that is **carried** names both a `source` (inside the
  doomed root) and a destination `path` (outside it). It is accepted only
  when the destination exists, is *not the same file as* the source
  (`Path.samefile`, so a checklist pointed at the source cannot satisfy
  itself), and its **content digest equals the source's** -- byte-for-byte
  for a file, and over the sorted relative path, kind and content of every
  entry for a directory. A same-named empty placeholder at the destination
  is rejected, where an existence check would accept it.
- A `CarryOverItem` that is **preserved in place** (`source is None`) is the
  other real class the dataclass supports: an item that is not carried
  anywhere and simply must survive, asserted present *and* outside the
  doomed root. `build_checklist` does not currently produce one of these --
  under Decision 7 the working directory never moves, so nothing it enumerates
  needs to be preserved in place rather than carried -- but `assert_carry_over`
  still accepts a caller-supplied item of this class directly.

Because the destination content is compared against the source, the source
must still be intact when the checklist runs: **copy, assert, then vacate**
-- never move-then-assert, which would leave the source half-gone with
nothing yet proven. The copy must
also **preserve symlinks rather than dereference them** (`cp -a`, or
`shutil.copytree(..., symlinks=True)`): a directory's links are part of
what the digest compares, so a dereferencing copy is reported as a
difference.

**Three false passes were found by attacking this checklist rather than by
reading it, and all three are closed** -- each is a case where a plausible
implementation accepts material that is about to be destroyed:

- A destination that *resolves* into the doomed root without naming it
  literally: a symlink pointing at the doomed file, or a `../`-spelled
  path. Both are caught only because `_is_within` resolves the path side
  before comparing, and for a preserved-in-place item that resolution is
  the only guard there is.
- A destination spelled with different case than the doomed root. On a
  case-folding filesystem -- this repository's own -- the two name the same
  directory while a path-component comparison says otherwise, so
  `_is_within` falls back to filesystem identity (`Path.samefile`).
- A symlink *inside* a carried directory. Following it made two trees with
  differently-targeted links digest identically, and containment on the
  item's own path says nothing about what the tree contains. Entries that
  are symlinks now digest as their link target, and a destination directory
  holding a link back into the doomed root is refused outright
  (`_entries_linking_into`).

`build_checklist` takes the fresh (destination) `.git` directory and the old
(doomed) `.git` directory as two separately-named, keyword-only arguments
and refuses outright if they are the same directory or if either contains
the other, so the single mistake this whole guard exists to prevent is
caught before an item is even built.

**The enumeration is the deliverable** (task 7.3, design.md
`#### HistoryReplacement` step 6). `build_checklist` lists `old_git_dir`'s
own top-level entries at run time -- never a remembered, hand-typed
inventory -- and classifies each one:

- `agent-log` is always built as the first checklist item, present or not
  (the same "always checked, never conditional" posture the retired
  `CloneAdoption` checklist already applied to it): `source=old_git_dir /
  "agent-log"`, `path=fresh_git_dir / "agent-log"`.
- Standard git furniture -- `HEAD`, `config`, `description`, `index`,
  `info`, `objects`, `refs`, `logs`, `hooks`, `packed-refs`,
  `COMMIT_EDITMSG`, `ORIG_HEAD`, `FETCH_HEAD`, `MERGE_HEAD`, `MERGE_MSG`,
  `MERGE_MODE`, `SQUASH_MSG`, `shallow`, `branches`, `worktrees` -- is
  deliberately not carried: the archive keeps it whole, and the fresh `.git`
  must not inherit state from the history being replaced -- design.md
  `#### HistoryReplacement` step 4 has it already a real, verified
  `--no-local` clone by the time this checklist runs (step 6), a caller-side
  ordering this module does not itself enforce or test.
  `_STANDARD_GIT_FURNITURE` is measured against a real `git init` repository
  after a commit and a `gc`, and against this repository's own primary
  `.git`, not assumed.
- `lost-found` -- real `.fit` activity files a past `fsck` extracted -- is
  likewise not carried, for the same reason and by the same design clause.
- **Any other entry halts the build outright**, raising `CarryOverError`
  naming every one found, rather than silently skipping it. Silence is the
  failure mode this enumeration exists to avoid: a foreign entry nobody
  anticipated is exactly the shape of state a remembered inventory would
  miss. (Measured, not hypothetical: this repository's own primary `.git`
  currently carries `sha-rewrite-map-2026-07-26.tsv`, a scratch artifact
  left behind by the retired rewrite machinery -- precisely the kind of
  entry this halt exists to surface for a decision before the swap, rather
  than silently leaving it in the archive unremarked or silently carrying
  it into the replacement.)

**Retired with the working-tree carry-over it belonged to**: the root
`agent-log` symlink item, the real-activity corpus (`data/`) item, the
`source_material_paths` and `scratch_artifacts` parameters and the
`_REQUIRED_SCRATCH_LABELS` label set, and `detect_data_root_forms`. Every one
of these existed to carry working-tree state across a *move* of the
repository directory; Decision 7 constraint 1 makes that move never happen,
so the working tree (and everything in it) needs no checklist item at all --
the root `agent-log` symlink in particular survives the `.git` swap
unchanged on disk and resolves again the moment the log is present in the
new `.git` at the same relative path, which is an observable Decision 7
itself states rather than a guard this module still needs to assert.

**The identity precondition is asserted in both scopes independently.**
`assert_commit_identity` reads `git config --local user.email` and `git
config --global user.email` as two separate subprocess calls and checks
each against the expected non-personal address on its own -- not the
single effective value `git config user.email` would report (local
overrides global, so that form can never surface a global-only drift). A
fresh clone inherits global configuration, so global drift is the one
setting whose corruption would silently violate Req 5.3 on every
post-rewrite commit while every local check kept passing.

**`move_clone` never removes anything to make room.** It refuses -- raising
`AdoptionError`, never overwriting -- if its target already exists, rather
than relying on `shutil.move`'s own default behavior for an existing
directory target (which nests the source inside it rather than raising).
The two directory moves `HistoryReplacement`'s swap performs (the old `.git`
to the archive path, the fresh `.git` into its place) are deliberately kept
out of this module, orchestrated by the replacement driver only once every
pre-swap verification row is green. Note this is narrower than "no code path
in this module ever removes a directory": `shutil.move`'s own cross-device
fallback is `copytree` then `rmtree` of *its source argument* (the directory
being moved *from*, never `target`) when `clone` and `target` sit on
different filesystems.

**Req 11.13 -- stated position, not a guard.** The untracked state this
module's checklist carries still contains an identifying token (design.md
`#### HistoryReplacement` states the same position): the shared agent log
carried between the two `.git` directories, whose *content* carries tokens
across several lines (position: recorded acceptance with a named hazard --
it is the append-only record peer sessions coordinate through, redacting it
would falsify what earlier sessions said, and the hazard is a future
packaging change that follows symlinks). The untracked source workbooks at
the repository root carry a token in their *filenames* too, but this module
no longer touches them at all under Decision 7 (they are never moved, so
they carry no checklist item); their position belongs to design.md
`#### HistoryReplacement`, not to this module. Neither position is verified
by a guard in this module; the agent log's is declared here to match
design.md, and this task's status report records Req 11.13 as UNPINNED for
this boundary.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import typer

_AGENT_LOG_NAME = "agent-log"

_LOST_FOUND_NAME = "lost-found"

_STANDARD_GIT_FURNITURE: frozenset[str] = frozenset(
    {
        "HEAD",
        "config",
        "description",
        "index",
        "info",
        "objects",
        "refs",
        "logs",
        "hooks",
        "packed-refs",
        "COMMIT_EDITMSG",
        "ORIG_HEAD",
        "FETCH_HEAD",
        "MERGE_HEAD",
        "MERGE_MSG",
        "MERGE_MODE",
        "SQUASH_MSG",
        "shallow",
        "branches",
        "worktrees",
    }
)
"""Top-level `.git` entries a normal use of git creates that carry no
purge-relevant state of their own and are not carried by `build_checklist`
-- the archive keeps them whole, and the fresh `.git` must not inherit
furniture from the history being replaced (design.md `#### HistoryReplacement`
puts a real, verified `--no-local` clone in place before this checklist
runs, a caller-side ordering this module does not itself enforce or test).
`HEAD`, `config`, `description`, `index`, `info`,
`objects`, `refs`, `logs`, `hooks` and `packed-refs` are measured against a
real `git init` repository after a commit and a `git gc`; `COMMIT_EDITMSG`,
`ORIG_HEAD`, `FETCH_HEAD` and `worktrees` are measured against this
repository's own primary `.git`
(`$(git rev-parse --git-common-dir)`) as it stands while this task is
implemented. `MERGE_HEAD`, `MERGE_MSG`, `MERGE_MODE`, `SQUASH_MSG`,
`shallow` and `branches` are not present on either measured repository but
are git's own documented plumbing entries, not this purge's concern; if one
of them is ever measured absent from this set in practice, `git`'s own
behaviour -- not this module -- is what created it. `lost-found` is
deliberately not in this set: it is real `.fit` activity a past `fsck`
extracted, checked and excluded on its own (`_LOST_FOUND_NAME`), not folded
into "furniture" a reader might assume is content-free."""


class CarryOverError(RuntimeError):
    """Raised by `assert_carry_over` naming every checklist item it could
    not accept, never just the first -- and by `build_checklist` when
    `clone_git_dir` and `old_git_dir` are not two distinct, non-nested
    directories, when `old_git_dir` cannot be enumerated, or when the
    enumeration finds a `.git`-resident entry no checklist item
    anticipates."""


class IdentityError(RuntimeError):
    """Raised by `assert_commit_identity` naming every scope (local,
    global, or both) whose configured `user.email` does not match the
    expected non-personal address."""


class AdoptionError(RuntimeError):
    """Raised by `move_clone` when its target already exists -- this module
    never removes a directory to make room, including the pre-adoption
    source repository."""


@dataclass(frozen=True, kw_only=True)
class CarryOverItem:
    """One row of the carry-over checklist.

    - `name` -- human-readable, and what a failure is reported under.
    - `path` -- where the item must be found **after** the carry-over: the
      destination, outside the doomed root.
    - `source` -- where a *carried* item is carried from, inside the doomed
      root. `None` marks the other class: an item **preserved in place**,
      which is not transferred anywhere and only has to survive somewhere
      outside the doomed root.

    Every field is keyword-only (`kw_only=True`): `path` and `source` are
    two `Path` arguments whose transposition is exactly the mistake this
    checklist exists to catch, and a positional constructor would let a
    caller swap them silently."""

    name: str
    path: Path
    source: Path | None = None


def _is_blank(path: Path) -> bool:
    """`Path("")` normalises to `Path('.')`, whose `.exists()` is always
    `True` -- a blank (or exactly `.`) path string is treated as missing
    rather than as a satisfied checklist item."""
    return str(path) in ("", ".")


def _is_within(path: Path, root: Path) -> bool:
    """Whether `path` resolves inside `root` (or *is* `root`).

    Both sides are resolved first, and the `path` side matters most: a
    destination that is a **symlink into** the doomed root, or one spelled
    with `..` that lands in it, is caught only because `path.resolve()` runs
    before the comparison. For a preserved-in-place item this is the *sole*
    guard -- `samefile` and the content digest never run for one -- so the
    resolution is load-bearing rather than tidy-looking.
    `Path.is_relative_to` is reflexive, so the equal case needs no separate
    clause, and neither side has to exist.

    **The string comparison is not the whole answer on a case-folding
    filesystem**, which is what this repository sits on. Measured: with a
    doomed root spelled `Source-Repo`, a path spelled `source-repo/...`
    names the very same directory to the operating system, while
    `is_relative_to` -- a pure path-component comparison -- says it does
    not, and the item is accepted and then deleted. So where the two
    disagree, the filesystem's own answer wins: the resolved path and each
    of its ancestors is compared to the root by identity (`Path.samefile`,
    st_dev/st_ino), which folds exactly as the filesystem does. That
    comparison needs both sides to exist, hence the string check first --
    a destination that does not exist yet is still refused by the string
    form, and the identity form only ever *adds* rejections.
    """
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if resolved_path.is_relative_to(resolved_root):
        return True
    if not resolved_root.exists():
        return False
    for candidate in (resolved_path, *resolved_path.parents):
        try:
            if candidate.samefile(resolved_root):
                return True
        except OSError:
            continue
    return False


def _content_digest(path: Path) -> str:
    """A content digest of `path`, for comparing a carried item against the
    copy it was carried from.

    A **file** digests as its bytes. A **directory** digests as the sorted
    sequence of its entries' relative paths, each with a kind marker and,
    for a file, its bytes -- so a destination directory that exists but is
    missing an entry, or holds a same-named entry with different content,
    digests differently. The kind marker is not decoration: an empty
    directory and a zero-byte file both hash to sha256's empty digest, and
    only the `dir:`/`file:` prefix distinguishes them.

    **The top-level `path` follows symlinks; entries *inside* a directory do
    not.** The two cases want opposite answers and the difference is
    measured, not assumed:

    - At the top level, the root `agent-log` symlink must point at the
      *clone's* git directory rather than the old one, so the two links'
      targets differ by design while the log content they resolve to must
      be identical. `read_bytes` follows, which is what compares content.
    - Inside a directory, following was a **false pass**: a symlinked
      subdirectory is `is_dir()`-true, `rglob` does not descend into it, and
      it therefore digested as a contentless `dir` entry -- two trees whose
      links pointed at different directories with different content digested
      identically. Entries that are symlinks are now digested as their
      **link target text**, which also makes the carried copy's link
      structure part of what is compared. A carry-over step must therefore
      preserve links rather than dereference them (`cp -a`, or
      `shutil.copytree(..., symlinks=True)`); a dereferencing copy is a
      genuine difference and is reported as one.

    Raises `OSError` (`FileNotFoundError` for a missing path or a dangling
    symlink) -- callers turn that into a named checklist failure rather than
    letting it escape."""
    digest = hashlib.sha256()
    if path.is_dir():
        for entry in sorted(path.rglob("*")):
            relative = entry.relative_to(path)
            digest.update(str(relative).encode("utf-8"))
            if entry.is_symlink():
                digest.update(b"\0link\0")
                digest.update(os.readlink(entry).encode("utf-8"))
            elif entry.is_dir():
                digest.update(b"\0dir\0")
            else:
                digest.update(b"\0file\0")
                digest.update(entry.read_bytes())
            digest.update(b"\0")
        return "dir:" + digest.hexdigest()
    digest.update(path.read_bytes())
    return "file:" + digest.hexdigest()


def _entries_linking_into(root: Path, doomed_root: Path) -> tuple[str, ...]:
    """Every symlink inside the directory `root` whose target resolves into
    `doomed_root`, named by its path relative to `root`.

    Containment is checked on an item's own path, which says nothing about
    what a *carried directory* contains: a tree copied with its links
    preserved can carry a link pointing back into the repository that is
    about to be deleted, and that link dangles the moment it is. The digest
    cannot catch this either -- source and destination agree, which is
    exactly the problem. Returns an empty tuple for a non-directory."""
    if not root.is_dir():
        return ()
    return tuple(
        sorted(
            str(entry.relative_to(root))
            for entry in root.rglob("*")
            if entry.is_symlink() and _is_within(entry, doomed_root)
        )
    )


def _transfer_problem(item: CarryOverItem, doomed_root: Path) -> str | None:
    """The one reason `item` cannot be accepted, or `None` if it can.

    Checked in this order, because each check would report a misleading
    reason if an earlier one were skipped:

    1. a blank destination (`_is_blank`) -- `Path('.')` exists everywhere;
    2. a destination inside `doomed_root` -- **the queue item's defect**: an
       item that is about to be deleted, however present it is right now;
    3. a destination that does not exist (a dangling symlink included,
       since `exists()` follows);
    4. a destination **directory** containing a symlink that points back
       into `doomed_root` (`_entries_linking_into`) -- checked for both item
       classes, because containment is a fact about an item's own path and
       says nothing about what a carried tree holds inside it;
    5. for a carried item only: a blank or missing source (nothing to
       compare against means nothing was proven), a destination that is the
       *same file* as its source (`Path.samefile` -- a checklist pointed at
       the source satisfying itself), and finally a destination whose
       content digest differs from the source's."""
    if _is_blank(item.path):
        return "blank destination path"
    if _is_within(item.path, doomed_root):
        return (
            f"destination {item.path} resolves inside the doomed root "
            f"{doomed_root}, which is about to be destroyed"
        )
    if not item.path.exists():
        return f"missing at the destination {item.path}"
    dangling_links = _entries_linking_into(item.path, doomed_root)
    if dangling_links:
        return (
            f"destination {item.path} contains symlink(s) pointing back "
            f"into the doomed root {doomed_root}, which will dangle once it "
            f"is destroyed: {list(dangling_links)}"
        )
    if item.source is None:
        return None
    if _is_blank(item.source):
        return "blank source path"
    if not item.source.exists():
        return (
            f"source {item.source} is already gone, so the copy at "
            f"{item.path} cannot be verified against it -- copy, assert, "
            "then vacate"
        )
    if item.path.samefile(item.source):
        return (
            f"destination {item.path} is the same file as its source "
            f"{item.source}; existence at the source is not transfer"
        )
    try:
        destination_digest = _content_digest(item.path)
        source_digest = _content_digest(item.source)
    except OSError as error:
        return f"could not be read to compare content: {error}"
    if destination_digest != source_digest:
        return (
            f"content at {item.path} differs from the source {item.source} "
            f"({destination_digest} != {source_digest})"
        )
    return None


def assert_carry_over(items: Sequence[CarryOverItem], *, doomed_root: Path) -> None:
    """Assert every item in `items` survives the destruction of
    `doomed_root`, raising `CarryOverError` naming *every* item it could not
    accept and why -- not merely reporting that the checklist failed, and
    never a silent pass over an empty item list: `items` being empty raises
    too, rather than trivially succeeding having asserted nothing.

    `doomed_root` is **keyword-only and has no default**: the directory
    about to be destroyed is the one fact this assertion is meaningless
    without, so a caller must name it rather than inherit it. See
    `_transfer_problem` for the per-item rules and the module docstring for
    why existence alone is the false positive."""
    if not items:
        raise CarryOverError(
            "assert_carry_over called with zero items; a silent pass over "
            "an empty checklist asserts nothing"
        )
    problems = [
        f"{item.name}\n      reason: {problem}"
        for item, problem in (
            (item, _transfer_problem(item, doomed_root)) for item in items
        )
        if problem is not None
    ]
    if problems:
        # One entry per line, each opened by the fixed "\n  - " marker and
        # naming the item BEFORE its reason. Item names legitimately contain
        # both ": " and parentheses (e.g. "gitignored source material:
        # workbook" and "... corpus (data/)"), so neither can separate a
        # name from its reason; a newline can, and no name holds one.
        raise CarryOverError(
            "carry-over checklist failed; unaccepted item(s):\n  - "
            + "\n  - ".join(problems)
        )


def build_checklist(
    *, clone_git_dir: Path, old_git_dir: Path
) -> tuple[CarryOverItem, ...]:
    """Assemble the `HistoryReplacement` carry-over checklist (task 7.3,
    design.md `#### HistoryReplacement` step 6) by enumerating `old_git_dir`
    at run time -- never a remembered, hand-typed inventory.

    **Both paths are named, separately, and neither has a default.** The
    single mistake this checklist exists to prevent is building it against
    the *doomed* `.git`, where every item would pass because the files do
    still exist a moment before the swap archives them. Raises
    `CarryOverError` before enumerating anything if `clone_git_dir` and
    `old_git_dir` are the same directory or if either contains the other.

    Raises `CarryOverError` if `old_git_dir` is not a directory -- nothing
    to enumerate means nothing was checked, not a vacuous empty checklist.

    **The enumeration is the deliverable.** Every top-level entry of
    `old_git_dir` is classified:

    - `agent-log` becomes the checklist's first item, always -- present or
      not, `source=old_git_dir / "agent-log"`,
      `path=clone_git_dir / "agent-log"`. `_content_digest` follows the
      top-level symlink it is not (the log is an ordinary file inside
      `.git`), so this is a plain content comparison.
    - An entry in `_STANDARD_GIT_FURNITURE`, or named `lost-found`, is
      recognised and deliberately not carried: the archive keeps it whole.
    - Any other entry is **foreign**, and halts the build outright, raising
      `CarryOverError` naming *every* foreign entry found -- not merely the
      first -- rather than silently leaving it behind or silently carrying
      it. Silence is the failure mode this enumeration exists to avoid.

    Building the checklist proves nothing on its own; `assert_carry_over` is
    what checks it, and it needs the doomed root (`old_git_dir`) named again
    there.
    """
    for label, inner in (
        ("clone_git_dir", clone_git_dir),
        ("old_git_dir", old_git_dir),
    ):
        other_label = "old_git_dir" if label == "clone_git_dir" else "clone_git_dir"
        other = old_git_dir if label == "clone_git_dir" else clone_git_dir
        if _is_blank(inner):
            raise CarryOverError(
                f"build_checklist called with a blank {label}; a blank path "
                "normalises to the process working directory and would "
                "make the containment check meaningless"
            )
        if _is_within(inner, other):
            raise CarryOverError(
                f"build_checklist called with {label}={inner} and "
                f"{other_label}={other}: the two must be distinct, "
                "non-nested directories. A checklist built against the "
                "doomed .git passes every assertion against files that are "
                "about to be archived out from under it, which is the one "
                "failure this checklist exists to prevent"
            )
    if not old_git_dir.is_dir():
        raise CarryOverError(
            f"build_checklist called with old_git_dir={old_git_dir}, which "
            "is not a directory; there is nothing to enumerate, and a "
            "checklist built from zero enumerated entries would never "
            "check the .git-resident state at all"
        )

    foreign = sorted(
        entry.name
        for entry in old_git_dir.iterdir()
        if entry.name != _AGENT_LOG_NAME
        and entry.name != _LOST_FOUND_NAME
        and entry.name not in _STANDARD_GIT_FURNITURE
    )
    if foreign:
        raise CarryOverError(
            "build_checklist found .git-resident entr"
            + ("y" if len(foreign) == 1 else "ies")
            + f" no checklist item anticipates: {foreign} -- halting for a "
            "decision rather than silently leaving it in the archive "
            "unremarked or silently carrying it into the replacement"
        )

    return (
        CarryOverItem(
            name="shared agent log",
            path=clone_git_dir / _AGENT_LOG_NAME,
            source=old_git_dir / _AGENT_LOG_NAME,
        ),
    )


def _git_config_value(
    repo_root: Path, scope: str, env: Mapping[str, str]
) -> str | None:
    """`git config <scope> user.email` run rooted at `repo_root`, or `None`
    if that scope has no `user.email` set (non-zero exit)."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "config", scope, "user.email"],
        capture_output=True,
        text=True,
        env=dict(env),
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def assert_commit_identity(
    repo_root: Path,
    non_personal_address: str,
    *,
    env: Mapping[str, str] | None = None,
) -> None:
    """Assert `git config user.email` resolves to `non_personal_address` in
    **both** the local and the global scope, checked independently -- never
    the single effective (local-overrides-global) value. Raises
    `IdentityError` naming every scope that does not match, not merely the
    first. `env` defaults to `os.environ`; a test overrides
    `GIT_CONFIG_GLOBAL` there to point at a scratch file rather than the
    real machine-wide global config."""
    resolved_env = dict(os.environ) if env is None else dict(env)
    local = _git_config_value(repo_root, "--local", resolved_env)
    global_ = _git_config_value(repo_root, "--global", resolved_env)
    problems = []
    if local != non_personal_address:
        problems.append(
            f"local user.email is {local!r}, expected {non_personal_address!r}"
        )
    if global_ != non_personal_address:
        problems.append(
            f"global user.email is {global_!r}, expected {non_personal_address!r}"
        )
    if problems:
        raise IdentityError("; ".join(problems))


def move_clone(clone: Path, target: Path) -> Path:
    """Move the verified clone at `clone` to `target` -- the original
    absolute repository path. Refuses with `AdoptionError` if `target`
    already exists,
    rather than letting `shutil.move` nest `clone` inside an existing
    `target` directory (its own default behavior for an existing directory
    destination, which would neither raise nor actually replace anything).
    This module contains no code path that removes a directory to make
    room -- vacating `target` first is the caller's responsibility, done
    only after verification has passed."""
    if target.exists():
        raise AdoptionError(
            f"refusing to move the adopted clone onto an existing path "
            f"{target}; this module contains no code path that removes a "
            "directory to make room, including the pre-adoption source "
            "repository"
        )
    shutil.move(str(clone), str(target))
    return target


def run() -> None:
    """`purge adopt` -- not yet wired to the replacement driver.
    `build_checklist`, `assert_carry_over`, `assert_commit_identity` and
    `move_clone` above are implemented and tested; the CLI wiring belongs
    to `scripts/purge/replace.py` (task 7.6, design.md `#### HistoryReplacement`,
    which supersedes the retired `CloneAdoption` component this module
    served before task 7.3), rather than this module driving itself from
    the command line. The order in which the driver calls these functions
    is stated by design.md `#### HistoryReplacement`, not here.
    """
    typer.echo(
        "purge adopt: not yet wired to the replacement driver (task 7.6 "
        "orchestrates this module's functions from scripts/purge/replace.py; "
        "supersedes the retired CloneAdoption CLI wiring this stub named "
        "before task 7.3)",
        err=True,
    )
    raise typer.Exit(code=1)
