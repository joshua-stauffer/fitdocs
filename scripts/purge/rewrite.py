"""`HistoryRewrite`: the gated driver that emits `git filter-repo` commands
through an injected command runner (design.md `#### HistoryRewrite`, Req
5.1, 5.2, 5.3, 6.5, 7.1, 7.2, 7.3, 11.1, 11.2, 11.3, 11.4).

**The driver never runs a mutating git command itself.** Every command it
wants executed is handed to `CommandRunner`, an injected callable -- so a
test can assert on the emitted commands (their shape, their order, their
count) without a real `git filter-repo` invocation ever running. Task 5.3's
own observable states this explicitly: "The driver is never executed for
real in a test." `assert_fresh_clone` is the one place this module calls
`subprocess` directly, and every one of those calls is a **read-only**
query about the repository it is handed (`rev-parse`, `rev-list`,
`cat-file`, `for-each-ref`, `remote`, `worktree list`) -- see
`_git_stdout`. No maintenance command is ever run: `git gc`, `git prune`
and `git reflog expire` are how a repository is made to *look* fresh, and
running one would destroy the difference the assertion exists to detect.

**The gate cannot be skipped by forgetting it, and neither can the fresh
clone.** `run_rewrite` calls `scripts.purge.preflight.gate` itself, as its
first act -- it does not trust a caller to have already done so. A halting
gate result short-circuits before `runner` is ever invoked: zero commands,
in that case, is not an implementation detail, it is what "the gate cannot
be skipped" means at the call boundary this module owns. On a proceeding
gate it then calls `assert_fresh_clone(repo)` for the same reason: Req
7.3's guarantee otherwise rested on task 7.2 remembering to clone first,
which is the remembered-rather-than-asserted shape task 5.5's own checklist
bullet rejects.

**Three verified hazards, each of which under-removes without erroring**
(design.md `#### HistoryRewrite`, "Three verified hazards this invocation
encodes"):

1. **Directive order inside `paths.txt` is load-bearing.** Filter and rename
   directives apply in file order, and a rename mutates the name later
   filter lines match against. In a controlled run, a rename placed before a
   deletion line for a file inside the renamed directory left that file
   ALIVE under its new name. `build_path_directives` therefore emits every
   deletion line before every rename line, and orders the rename block so a
   nested rename (a path inside another renamed path) follows its
   parent-directory rename.
2. **Word-boundary anchors under-match.** `_` is a word character, so a
   `\\b`-anchored pattern cannot match a token embedded in an identifier -- a
   `\\b`-anchored expression set left 6 of 26 token-bearing commit messages
   dirty, every survivor an identifier or a class name.
   `build_replacement_expressions` therefore emits unanchored,
   case-insensitive `regex:` lines, ordered longest-phrase-first so a
   multi-word phrase is consumed before its component words. The same
   function renders both `replace-text.txt` (blob content) and
   `replace-message.txt` (commit messages) -- `--replace-text` and
   `--replace-message` share one parser and syntax.
3. **`--prune-empty` is passed `never`, not left at its default.** Nothing
   would be pruned by measurement (the redaction plan's own
   `would_be_pruned_commits` check, consumed before this module runs,
   guarantees that), but a pruned commit maps to forty zeros in the commit
   map, which would put a hole in Req 9.3's complete mapping.
   `build_filter_repo_command` hard-codes `never`.

**`--prune-degenerate` is deliberately NOT passed, and that is a measured
decision, not an omission**
(`.kiro/queue/2026-08-07-rewrite-preconditions-remembered-not-asserted.md`,
second half; design.md `#### HistoryRewrite`). The open question was whether
a merge whose post-removal tree equals one parent's tree exactly -- which
task 5.2's would-be-pruned check does not model -- could be pruned or
flattened behind this invocation's back. Measured against the real
`git filter-repo` on a throwaway repository built to contain exactly that
merge plus a side branch lying entirely inside the removal set: under the
default (`--prune-degenerate auto`, no `--prune-empty`) both the side
commit and the merge are pruned and the commit map gains **two all-zeros
rows**; under this module's invocation the commit map has **one row per
pre-rewrite commit, no all-zeros row**, the merge survives with **both
parents**, and adding `--prune-degenerate never` on top produces the
identical result. The mechanism, read from the tool's own source after
measuring: `_prunable` returns `False` immediately when `prune_empty` is
`never`, so nothing is ever skipped, so `_SKIPPED_COMMITS` stays empty, and
`_maybe_trim_extra_parents` only ever removes a parent that was itself
skipped. `--prune-empty never` is therefore load-bearing for both cases,
and the flag would be a no-op -- so it is not added, and this paragraph is
the record.

**The mailmap, and every other spec file, is refused if it is not an
absolute path outside the repository.** The mailmap must not be written to
the conventional `.mailmap` at the repository root: that path is tracked,
ships in the sdist under the packaging default, and would carry the address
into precisely the artifact this spec exists to clean.
`_assert_absolute_and_outside_repo` enforces this for all four spec files
(`paths_file`, `replace_text_file`, `replace_message_file`, `mailmap_file`),
which is a strictly more general check than "not the conventional root
path" -- a repo-root `.mailmap` is one specific point inside the region this
check already refuses.

**What this module does NOT do.** It does not compute the redaction plan
(`scripts/purge/plan.py`), it does not decide which addresses or tokens to
replace (those are caller-supplied, scratch, out-of-repository artifacts on
the same footing design.md gives the probe set), and it does not delete or
assert the absence of `refs/original/*` -- that is `QuiescenceGate`'s job
(task 7.1), run separately, before this driver's `repo` argument is even a
fresh clone. This module's `repo` argument is the clone `git filter-repo`
runs against; the gate it calls internally is handed an already-computed
`Quiescence` for whichever repository the caller wants checked.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

import typer

from scripts.purge.preflight import Quiescence, gate

CommandRunner = Callable[[Sequence[str]], None]
"""Injected by the caller. Never a real subprocess call inside this module
or its tests -- see the module docstring."""


class FreshCloneError(RuntimeError):
    """Raised by `assert_fresh_clone` naming *every* property of a fresh,
    non-locally-optimised clone that `repo` does not have, never just the
    first."""


# --- path directives (paths.txt) --------------------------------------------


def build_path_directives(
    removed_paths: Sequence[str],
    rename_pairs: Sequence[tuple[str, str]],
) -> str:
    """Render `git filter-repo --paths-from-file` input.

    Every line in `removed_paths` precedes every rename line -- Hazard 1 in
    the module docstring. `rename_pairs` is `(old_path, new_path)`, and the
    rename block is ordered by ascending path depth (`/`-count) so a
    parent-directory rename precedes a rename nested inside it; ties break
    lexicographically for a deterministic, reproducible spec file.
    """
    ordered_renames = sorted(
        rename_pairs, key=lambda pair: (pair[0].count("/"), pair[0])
    )
    lines = list(removed_paths)
    lines += [f"{old}==>{new}" for old, new in ordered_renames]
    return "\n".join(lines) + ("\n" if lines else "")


# --- replacement expressions (replace-text.txt / replace-message.txt) ------


def build_replacement_expressions(phrases: Sequence[tuple[str, str]]) -> str:
    """Render `git filter-repo --replace-text` / `--replace-message` input.

    `phrases` is `(old, new)` pairs. Rendered as `regex:` lines carrying an
    inline case-insensitive flag and no word-boundary anchor -- Hazard 2 in
    the module docstring -- ordered longest-phrase-first (by character
    length of `old`) so a multi-word phrase is consumed before its component
    words. `re.escape` keeps each pattern a literal match despite the
    `regex:` prefix; the prefix is required because filter-repo's `==>`
    replacement syntax is shared between `literal:` and `regex:` lines, and
    only a `regex:` line accepts the inline `(?i)` flag this hazard rule
    needs.
    """
    ordered = sorted(phrases, key=lambda pair: len(pair[0]), reverse=True)
    lines = [f"regex:(?i){re.escape(old)}==>{new}" for old, new in ordered]
    return "\n".join(lines) + ("\n" if lines else "")


# --- the single filter-repo invocation --------------------------------------


def build_filter_repo_command(
    repo: Path,
    paths_file: Path,
    replace_text_file: Path,
    replace_message_file: Path,
    mailmap_file: Path,
) -> tuple[str, ...]:
    """The one `git filter-repo` invocation carrying all four transforms --
    path removal/renaming, content replacement, and commit metadata --
    matching the shape verified end to end on a throwaway clone during
    design (design.md `#### HistoryRewrite`). `--prune-empty never` is
    hard-coded (Hazard 3); every spec-file path is passed through exactly as
    given, so the caller's absolute-path-outside-the-repository invariant
    (enforced by `_assert_absolute_and_outside_repo` in `run_rewrite`) is
    what the emitted command actually carries.
    """
    return (
        "git",
        "-C",
        str(repo),
        "filter-repo",
        "--invert-paths",
        "--paths-from-file",
        str(paths_file),
        "--replace-text",
        str(replace_text_file),
        "--replace-message",
        str(replace_message_file),
        "--mailmap",
        str(mailmap_file),
        "--prune-empty",
        "never",
    )


def build_remote_add_command(repo: Path, origin_url: str) -> tuple[str, ...]:
    """`git filter-repo` removes `origin` deliberately and renames
    `refs/remotes/origin/*` into local heads; this re-adds it by hand
    afterwards, as design.md's Ordering step 5 requires."""
    return ("git", "-C", str(repo), "remote", "add", "origin", origin_url)


# --- fresh-clone precondition -----------------------------------------------


_TWO_HEX = re.compile(r"^[0-9a-f]{2}$")


def _git_stdout(repo: Path, *args: str) -> str:
    """One **read-only** `git` query rooted at `repo`. Every call site below
    inspects; none mutates. `check=False` deliberately: several of these
    questions ("is there a stash?") are answered by a non-zero exit, which
    is information rather than an error."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    ).stdout


def _unreachable_object_ids(repo: Path) -> frozenset[str]:
    """Every object id `repo`'s object database physically holds that
    nothing reaches. `git cat-file --batch-all-objects` sees what is on
    disk; `git rev-list --objects --all --reflog` is what reaches.

    The reflog is on the reachable side on purpose: a reflog entry is a real
    pin, so counting its objects as unreachable would report a fresh clone
    as unclean.

    An earlier version also unioned in `git for-each-ref --format=%(objectname)`,
    justified by the claim that `rev-list --objects` does not print annotated
    tag object ids. **That claim is false, measured**: on a repository with an
    annotated tag `v1`, `git rev-list --objects --all` prints the tag object's
    own id on a line of its own (`<tag-object-id> v1`), and `--all` means
    "every ref under `refs/`" in any case. The term could therefore never
    change the result -- removing it reds nothing, because nothing it added
    was ever absent -- and an unfalsifiable term resting on a false reason is
    the worst thing to leave on a gate that runs immediately before an
    unrepeatable rewrite. It is gone rather than re-justified."""
    on_disk = {
        line.split(" ", 1)[0]
        for line in _git_stdout(
            repo, "cat-file", "--batch-all-objects", "--batch-check=%(objectname)"
        ).splitlines()
        if line.strip()
    }
    reachable = {
        line.split(" ", 1)[0]
        for line in _git_stdout(
            repo, "rev-list", "--objects", "--all", "--reflog"
        ).splitlines()
        if line.strip()
    }
    return frozenset(on_disk - reachable)


def _loose_object_count(git_dir: Path) -> int:
    """Loose objects under `<git-dir>/objects/`, counted from the two-hex
    fan-out directories only -- `info/` and `pack/` are not fan-out
    directories and their contents are not loose objects."""
    objects = git_dir / "objects"
    if not objects.is_dir():
        return 0
    return sum(
        len([entry for entry in fanout.iterdir() if entry.is_file()])
        for fanout in objects.iterdir()
        if fanout.is_dir() and _TWO_HEX.match(fanout.name)
    )


def _multi_entry_reflogs(git_dir: Path) -> tuple[str, ...]:
    """Every reflog under `<git-dir>/logs/` holding more than one entry,
    named by its path relative to `logs/`. A fresh clone's reflogs each
    hold exactly the clone itself."""
    logs = git_dir / "logs"
    if not logs.is_dir():
        return ()
    return tuple(
        sorted(
            str(log.relative_to(logs))
            for log in logs.rglob("*")
            if log.is_file()
            and len(
                [
                    line
                    for line in log.read_text(errors="replace").splitlines()
                    if line.strip()
                ]
            )
            > 1
        )
    )


def assert_fresh_clone(repo: Path) -> None:
    """Assert `repo` is a **fresh clone taken without the local
    optimisation**, raising `FreshCloneError` naming every property it does
    not have -- never just the first (Req 7.3;
    `.kiro/queue/2026-08-07-rewrite-preconditions-remembered-not-asserted.md`).

    Task 5.3's driver rewrites whatever repository it is handed. Before
    this function existed, the fresh clone Req 7.3 depends on rested on
    task 7.2 *remembering* to clone first -- the remembered-rather-than-
    asserted shape this spec rejects explicitly in task 5.5's own checklist
    bullet. `run_rewrite` calls this itself, as it calls the gate itself,
    so the precondition cannot be skipped by forgetting it.

    The properties, and why each one:

    1. **No unreachable object.** This is what "without the local
       optimisation" means *as a property of the result* rather than as a
       flag someone typed: `git clone --local` (the default for a
       same-filesystem source) hardlinks the whole object directory and
       carries every unreachable object with it, while `--no-local` copies
       only what is reachable. Those unreachable objects are exactly the
       ones design.md `#### HistoryRewrite` step 3 relies on the clone to
       drop, and the ones `LocalVerification`'s own row exists to prove
       absent -- a row that would otherwise pass against a subject that was
       never fresh. Checking the property rather than the flag also catches
       a clone that was correct when taken and has since acquired
       unreachable objects.
    2. **No alternates file.** `<git-dir>/objects/info/alternates` makes a
       repository borrow objects from another object store instead of
       holding them; a rewrite there does not rewrite what is borrowed.
       Task 7.3 asserts the same file absent on its verification clone.
    3. **Fully packed** -- no loose objects.
    4. **Exactly one remote, named `origin`.**
    5. **Single-entry reflogs.** More than one entry means the clone has
       been worked in since it was taken.
    6. **No stash** (`refs/stash`).
    7. **Exactly one worktree.**
    8. **Every local head equal to its `origin` counterpart.**

    (3) through (8) are the sanity checks `git filter-repo` itself makes
    unforced, listed in design.md's Ordering step 3; asserting them here is
    what makes "the working repository fails at least three of these, and
    `--force` is not the answer" a check rather than a note.

    Every query is **read-only** -- see `_git_stdout`. This function never
    runs a maintenance command, and in particular never `git gc`, `git
    prune` or `git reflog expire`: those are how a repository is made to
    *look* fresh, and running one here would erase the very difference this
    assertion exists to detect (a linked worktree's `.git` is a pointer
    into a shared object store, so such a command reaches far beyond its
    argument -- this project has lost objects that way once already).
    """
    problems: list[str] = []
    git_dir_output = _git_stdout(repo, "rev-parse", "--absolute-git-dir").strip()
    if not git_dir_output:
        raise FreshCloneError(
            f"{repo} is not a git repository (git rev-parse "
            "--absolute-git-dir produced nothing), so none of the "
            "fresh-clone properties can be measured against it"
        )
    git_dir = Path(git_dir_output)

    unreachable = _unreachable_object_ids(repo)
    if unreachable:
        problems.append(
            f"holds {len(unreachable)} unreachable object(s); a clone taken "
            "without the local optimisation copies only reachable objects, "
            "so this repository is either not a clone or was cloned with "
            "the (default, same-filesystem) local optimisation"
        )

    if (git_dir / "objects" / "info" / "alternates").exists():
        problems.append(
            "has an objects/info/alternates file, so it borrows objects "
            "from another object store rather than holding them"
        )

    loose = _loose_object_count(git_dir)
    if loose:
        problems.append(f"is not fully packed ({loose} loose object(s))")

    remotes = tuple(
        line.strip()
        for line in _git_stdout(repo, "remote").splitlines()
        if line.strip()
    )
    if remotes != ("origin",):
        problems.append(
            f"does not have exactly one remote named origin (found {list(remotes)})"
        )

    busy_reflogs = _multi_entry_reflogs(git_dir)
    if busy_reflogs:
        problems.append(
            "has reflog(s) with more than one entry, so it has been worked "
            f"in since it was taken: {list(busy_reflogs)}"
        )

    if _git_stdout(repo, "rev-parse", "--verify", "--quiet", "refs/stash").strip():
        problems.append("has a stash (refs/stash exists)")

    worktrees = [
        line
        for line in _git_stdout(repo, "worktree", "list", "--porcelain").splitlines()
        if line.startswith("worktree ")
    ]
    if len(worktrees) != 1:
        problems.append(f"does not have exactly one worktree (found {len(worktrees)})")

    heads = {
        line.split(" ", 1)[1]: line.split(" ", 1)[0]
        for line in _git_stdout(
            repo, "for-each-ref", "--format=%(objectname) %(refname)", "refs/heads/"
        ).splitlines()
        if line.strip()
    }
    remote_heads = {
        line.split(" ", 1)[1]: line.split(" ", 1)[0]
        for line in _git_stdout(
            repo,
            "for-each-ref",
            "--format=%(objectname) %(refname)",
            "refs/remotes/origin/",
        ).splitlines()
        if line.strip()
    }
    for refname, object_id in sorted(heads.items()):
        short = refname[len("refs/heads/") :]
        counterpart = remote_heads.get(f"refs/remotes/origin/{short}")
        if counterpart is None:
            problems.append(
                f"has no refs/remotes/origin/{short} counterpart for {refname}"
            )
        elif counterpart != object_id:
            problems.append(
                f"has {refname} not equal to refs/remotes/origin/{short} "
                "(the clone has moved since it was taken)"
            )

    if problems:
        raise FreshCloneError(
            f"{repo} is not a fresh clone taken without the local "
            "optimisation; it " + "; it ".join(problems)
        )


# --- spec-file placement guard ----------------------------------------------


def _assert_absolute_and_outside_repo(spec_file: Path, repo_root: Path) -> None:
    """Refuse a spec file that is not an absolute path, or that resolves
    inside `repo_root` -- including exactly at `repo_root / ".mailmap"`, the
    conventional path this module must never write to (see the module
    docstring). Applied to all four spec files, not only the mailmap: "every
    spec file passed by absolute path from outside the repository" is one
    rule, not a mailmap-specific carve-out.

    `Path.is_relative_to` is reflexive (`p.is_relative_to(p)` is `True`), so
    the case where `spec_file` resolves to exactly `repo_root` is already
    covered by `is_relative_to` alone -- there is deliberately no separate
    `resolved == resolved_repo_root` clause here.
    """
    if not spec_file.is_absolute():
        raise ValueError(
            f"spec file must be an absolute path outside the repository, "
            f"got a relative path: {spec_file}"
        )
    resolved_repo_root = repo_root.resolve()
    resolved = spec_file.resolve()
    if resolved.is_relative_to(resolved_repo_root):
        raise ValueError(
            f"refusing to use a spec file living inside the repository: "
            f"{spec_file} resolves under {resolved_repo_root}"
        )


# --- orchestration -----------------------------------------------------------


def run_rewrite(
    *,
    quiescence: Quiescence,
    abandoned_branches: tuple[str, ...],
    abandonment_recorded: bool,
    log: Path,
    repo: Path,
    repo_root: Path,
    paths_file: Path,
    replace_text_file: Path,
    replace_message_file: Path,
    mailmap_file: Path,
    origin_url: str,
    runner: CommandRunner,
) -> int:
    """Call the gate first (Req 6.5); refuse on a non-zero result, emitting
    NO command through `runner` and returning the gate's own exit code. On a
    zero result -- which the gate has already logged as `PROCEEDING`, in
    `log`, before returning -- assert `repo` is a fresh clone taken without
    the local optimisation (`assert_fresh_clone`), then validate that all
    four spec files are absolute paths outside `repo_root`, then emit
    exactly two commands, in order: the single `git filter-repo` invocation
    carrying all four transforms, then the `git remote add origin` command
    that restores what filter-repo deliberately removes.

    **The gate is checked before the clone is.** A halting gate short-
    circuits with zero commands emitted and its own exit code returned,
    whatever `repo` is: the gate's finding is the one that must be reported,
    and a repository that is not yet a fresh clone is the *expected* state
    while the gate is still deciding whether the run may proceed at all.
    `assert_fresh_clone` raises rather than returning a code, because unlike
    a gate halt it is not a state an operator can be asked to resolve and
    re-run past -- the answer is always "take the clone".

    Every parameter is keyword-only (the bare `*`) so `repo` and `repo_root`
    -- two `Path` arguments a caller could otherwise transpose silently --
    cannot be swapped by position at a call site.

    Returns `gate`'s exit code: 0 on proceed, non-zero on halt.
    """
    exit_code = gate(quiescence, abandoned_branches, abandonment_recorded, log)
    if exit_code != 0:
        return exit_code

    assert_fresh_clone(repo)

    for spec_file in (
        paths_file,
        replace_text_file,
        replace_message_file,
        mailmap_file,
    ):
        _assert_absolute_and_outside_repo(spec_file, repo_root)

    runner(
        build_filter_repo_command(
            repo, paths_file, replace_text_file, replace_message_file, mailmap_file
        )
    )
    runner(build_remote_add_command(repo, origin_url))
    return 0


def run() -> None:
    """`purge rewrite` -- not yet wired to a CLI-level source for the
    quiescence input, the redaction plan's spec files, the origin url or the
    command runner. The functions above (`run_rewrite` and its parts) are
    implemented and tested (task 5.3); wiring the CLI to real,
    out-of-repository scratch-artifact inputs and a real subprocess runner
    is task 7.2's responsibility, run from `main` in the primary worktree
    once the quiescence gate has already proceeded (task 7.1) -- the same
    posture `scripts/purge/preflight.py::run` and
    `scripts/purge/plan.py::run` state for their own CLI wiring.
    """
    typer.echo(
        "purge rewrite: HistoryRewrite CLI wiring not yet implemented "
        "(run_rewrite is implemented; task 7.2 supplies its scratch-artifact "
        "inputs, real clone path and real command runner at the call site)",
        err=True,
    )
    raise typer.Exit(code=1)
