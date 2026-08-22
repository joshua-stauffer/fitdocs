"""`QuiescenceGate`: refuse the history rewrite while a peer's work is
unlanded (Req 6.1-6.6, design.md `#### QuiescenceGate`).

Two functions carry the whole contract. `inspect` is a **read-only**
snapshot of everything the gate cares about -- every branch other than
`main`, every worktree other than the primary one, every dirty *tracked*
path (with its porcelain status) in any of those trees, and any surviving
`refs/original/*` backup ref. It opens no ref for write and expires
nothing, so it is safe to call at any moment.

`gate` turns that snapshot plus an explicit abandonment record into a
proceed/halt decision, and writes **exactly one** line to the shared agent
log either way, before returning. `abandoned_branches` is an EXPLICIT
CALLER INPUT, never derived from live refs: an earlier draft derived the
two abandoned branch names from `refs/original/*`, and those refs were
deleted during this spec's own design phase -- which would have made that
tuple empty and discharged Req 6.6's "record the abandonment, naming each
branch" obligation by accident rather than by decision, with the gate
passing silently. `Quiescence.surviving_original_refs` is reported for
information only and never relaxes the check.

`gate` rejects `abandoned_branches` if it is empty **or if any entry is
blank after stripping**: `("",)` is exactly what `tuple(out.split("\n"))`
produces over empty command output, so an unguarded blank entry would let
the same derivation-from-empty accident back in through a populated-looking
tuple. What `gate` does **not** do is check that `abandoned_branches` names
this spec's two specific branches, or any particular count -- `gate` is a
generic function with no knowledge of which branches a given run is
supposed to abandon. Confirming the record names the branches a caller
actually intended (this spec's task 7.1 obligation is "naming both
`impl/athlete-benchmarks` and `impl/training-load`") is the CALLER's
responsibility, decided here explicitly rather than left silently
ambiguous.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import typer

_SESSION_ID = "purge-preflight"


@dataclass(frozen=True)
class Quiescence:
    """A read-only snapshot of everything the quiescence gate cares about."""

    extra_branches: tuple[str, ...]
    extra_worktrees: tuple[str, ...]
    dirty_trees: tuple[tuple[str, str], ...]
    surviving_original_refs: tuple[str, ...]

    @property
    def quiet(self) -> bool:
        """True iff there is no extra branch, no extra worktree, and no
        dirty tracked path anywhere. `surviving_original_refs` never
        participates here -- it is informational only (Req 6.6)."""
        return not (self.extra_branches or self.extra_worktrees or self.dirty_trees)


def _git(repo: Path, *args: str) -> str:
    """Run a read-only git subcommand rooted at `repo` and return its
    stdout. Every caller in this module passes a read-only subcommand
    (`for-each-ref`, `worktree list`, `status --porcelain`); none of them
    opens a ref for write or touches a reflog."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _extra_branches(repo: Path) -> tuple[str, ...]:
    """Every ref under `refs/heads` other than `main` (Req 6.1)."""
    out = _git(repo, "for-each-ref", "refs/heads", "--format=%(refname:short)")
    return tuple(sorted(name for name in out.splitlines() if name and name != "main"))


def _worktree_paths(repo: Path) -> tuple[str, ...]:
    """Every worktree path, primary first. `git worktree list` always lists
    the main working tree before any linked worktree, regardless of the
    order they were added in."""
    out = _git(repo, "worktree", "list", "--porcelain")
    paths = []
    for line in out.splitlines():
        if line.startswith("worktree "):
            paths.append(line[len("worktree ") :])
    return tuple(paths)


def _dirty_paths(worktree: str) -> tuple[tuple[str, str], ...]:
    """Every dirty **tracked** path in `worktree`, paired with its porcelain
    status line. `??` (untracked) entries are excluded: Req 6.1/6.2 scope
    the check to a tracked file that is "modified or staged", not to
    untracked content sitting in the tree."""
    out = _git(Path(worktree), "status", "--porcelain")
    dirty = []
    for line in out.splitlines():
        if not line or line.startswith("??"):
            continue
        dirty.append((worktree, line))
    return tuple(dirty)


def _surviving_original_refs(repo: Path) -> tuple[str, ...]:
    """Every ref still present under `refs/original/`, reported on
    `Quiescence` for information only -- it never makes `quiet` False
    (Req 6.6)."""
    out = _git(repo, "for-each-ref", "refs/original", "--format=%(refname)")
    return tuple(sorted(name for name in out.splitlines() if name))


def inspect(repo: Path) -> Quiescence:
    """Read-only. Opens no ref for write, expires nothing. Safe to run at
    any moment (Req 6.1)."""
    extra_branches = _extra_branches(repo)
    worktree_paths = _worktree_paths(repo)
    extra_worktrees = worktree_paths[1:]
    dirty_trees: tuple[tuple[str, str], ...] = ()
    for worktree in worktree_paths:
        dirty_trees += _dirty_paths(worktree)
    surviving_original_refs = _surviving_original_refs(repo)
    return Quiescence(
        extra_branches=extra_branches,
        extra_worktrees=extra_worktrees,
        dirty_trees=dirty_trees,
        surviving_original_refs=surviving_original_refs,
    )


def _describe_halt(q: Quiescence) -> str:
    """Name exactly what a quiescence failure found: every extra branch,
    every extra worktree path, every dirty path with its porcelain status
    (Req 6.2). "Not quiet" alone is useless to the peer who has to act on
    it."""
    parts = []
    if q.extra_branches:
        parts.append("branches=" + ",".join(q.extra_branches))
    if q.extra_worktrees:
        parts.append("worktrees=" + ",".join(q.extra_worktrees))
    if q.dirty_trees:
        dirty = ";".join(f"{tree}:{status}" for tree, status in q.dirty_trees)
        parts.append("dirty=" + dirty)
    return " ".join(parts)


def _append_log_line(log: Path, event: str, body: str) -> None:
    """Append exactly one tab-separated line -- UTC timestamp, session id,
    event, body -- matching `.kiro/steering/concurrency.md`'s shared
    agent-log format. This is the only write `gate` performs."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{timestamp}\t{_SESSION_ID}\t{event}\t{body}\n"
    with log.open("a") as handle:
        handle.write(line)


def gate(
    q: Quiescence,
    abandoned_branches: tuple[str, ...],
    abandonment_recorded: bool,
    log: Path,
) -> int:
    """0 to proceed, non-zero to halt. Writes exactly one line to the shared
    agent log either way, BEFORE returning.

    `abandoned_branches` is an EXPLICIT CALLER INPUT, never derived from
    live refs -- see the module docstring.
    """
    if not q.quiet:
        _append_log_line(log, "HALT", _describe_halt(q))
        return 1
    if not abandoned_branches or any(not name.strip() for name in abandoned_branches):
        _append_log_line(
            log,
            "HALT",
            "abandonment not recorded: no abandoned branch named",
        )
        return 1
    if not abandonment_recorded:
        _append_log_line(
            log,
            "HALT",
            "abandonment not recorded: abandonment_recorded is False for "
            + ",".join(abandoned_branches),
        )
        return 1
    _append_log_line(
        log,
        "PROCEEDING",
        "quiescence gate proceeding; abandoned branches: "
        + ",".join(abandoned_branches),
    )
    return 0


def run() -> None:
    """`purge preflight` -- not yet wired to a CLI-level abandonment source.
    `inspect`/`gate` are implemented (task 5.1); the caller that supplies
    `abandoned_branches` and `abandonment_recorded` from a recorded decision
    is task 7.1's responsibility, run from `main` in the primary worktree.
    """
    typer.echo(
        "purge preflight: QuiescenceGate CLI wiring not yet implemented"
        " (task 7.1 supplies the abandonment record at the call site)",
        err=True,
    )
    raise typer.Exit(code=1)
