"""`RedactionPlan`: classify every historical blob and every historical path
(design.md `#### RedactionPlan`, Req 5.1, 7.1, 9.3, 11.1, 11.2).

**Two enumerations, not one.**

- *Content*: `enumerate_blob_ids` walks every object reachable from any ref
  (`git rev-list --objects --all` filtered to blobs via `git cat-file
  --batch-check`) and `classify_blob_content` runs each blob's text through
  `tests._content_oracle.scan` (the value matcher), `tests._forbidden_strings
  .matches` (the forbidden-string matcher) and a probe set for the symbolic
  reproductions and all three personal identifiers (the third party's
  address, the maintainer's address, and the git-constructed
  username-and-machine-name form -- all three are email-shaped, so one
  regex probe reaches all three, the same posture
  `scripts/purge/sweep.py::run_identity_probe_sweep` documents for the same
  reason).
- *Path*: `enumerate_paths` walks every path at every commit in the
  **complete** form (`git rev-list --all | ls-tree -r --name-only | sort
  -u`), never the parent-relative added-files log filter (`--diff-filter=A`
  misses a path introduced by the root commit), and `classify_path` runs
  each unique path through `tests._forbidden_strings.matches`.

**Blob identifiers, never basenames.** `enumerate_blob_ids` returns git's own
content-addressed object ids. Two files with identical basenames but
different content (the withdrawn calculator package's own copy of a lookup
table, differing from the `docs/reference/` copy by a prepended copyright
line) hash to two different ids and both appear as separate rows -- nothing
here de-duplicates by basename, because nothing here even sees a basename;
`classify_blob_content` never looks at a path.

**A blob's bytes are not guaranteed to be UTF-8.** `read_blob_text` decodes
with `errors="replace"` rather than skipping an undecodable blob. A `try`/
`except` around a scan that drops what would not decode turns "cannot
decode" into "not scanned", and the width of that exemption is whatever the
exception covers -- here, potentially any blob at all. A blob this function
cannot decode cleanly still gets scanned, as its best-effort text, rather
than silently omitted from the plan.

**The would-be-pruned check the rewrite depends on** (`would_be_pruned_commits`,
raised as `WouldBePrunedError` by `build_redaction_plan`) answers, for every
commit reachable from any ref, whether at least one of its changed paths
survives the removal set. This module does not run `git-filter-repo` itself
and makes no claim about what its `--prune-empty` flag does -- design.md
`#### HistoryRewrite` records that decision separately. What this check
does is halt here, before the rewrite ever runs, on any commit whose
changed paths lie entirely inside the removal set -- because Req 9.3's
complete pre-rewrite-to-post-rewrite commit mapping must not depend on the
rewrite tool's own flag behaving as expected.

**Emit identifiers and dispositions only.** `ContentMatch` never carries the
matched substring -- only the blob id, which pass matched it, and a
disposition (`literal_replaceable` / `not_pattern_tractable`). `PathMatch`
carries the path string itself (an identifier the rewrite's `paths.txt`
needs operationally, not "content" in the sense this module's `no content`
observable means) plus a disposition and, for a rename, its target stem.
`fingerprints`, `window_lengths`, `salt`, `forbidden` and `rename_targets`
are every one of them caller-supplied: this module holds no probe value,
no removed-path fragment and no rename-target mapping of its own, the same
"scratch artifacts, live outside the repository" posture design.md states
for the probe set, the replacement specs and the mailmap.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import typer
from tests._content_oracle import scan
from tests._forbidden_strings import ForbiddenStrings, matches

from scripts.purge.sweep import _EMAIL_PATTERN as _EMAIL_PATTERN_SOURCE
from scripts.purge.sweep import SYMBOLIC_PROBES as SYMBOLIC_PROBES

# --- symbolic-reproduction probe set --------------------------------------
#
# `SYMBOLIC_PROBES` is IMPORTED from `scripts/purge/sweep.py`, not
# re-authored here: an earlier draft of this module kept a hand-copied
# duplicate and claimed the duplication was deliberate ("a second,
# independently-authored probe set ... so a bug in one is not invisible to
# the other"), which was false -- `plan.SYMBOLIC_PROBES ==
# sweep.SYMBOLIC_PROBES` was `True` by construction, so the copy would have
# reproduced any bug in the original rather than exposing it, and nothing
# guarded the two from drifting apart. Importing the one definition removes
# both problems at once. Every needle is fixed-string and case-sensitive,
# checked with `in`, mirroring `git grep -F` (no `-i`).

_EMAIL_PATTERN = re.compile(_EMAIL_PATTERN_SOURCE)
"""`scripts/purge/sweep.py::_EMAIL_PATTERN`, compiled -- imported for the
same reason `SYMBOLIC_PROBES` is (see above), rather than kept as a second,
independent copy of the same regex text.

Generic email shape -- carries no literal address of its own. Reaches all
three personal identifiers design.md `#### RedactionPlan` names (the third
party's address, the maintainer's address, and the git-constructed
username-and-machine-name `<user>@<host>.local` form), because all three
match this one shape. `classify_blob_content` does not classify by domain
the way `scripts/purge/sweep.py::_classify_email_domain` does for the
working-tree sweep -- a domain-based allowlist for
`users.noreply.github.com` / `example.com` would need to hold those
domain strings, and holding them here would be one more thing this module
would have to get right to avoid under- or over-flagging; the caller
consuming a `ContentMatch` tagged `identity_probe` is expected to inspect
the blob itself (out of process, never through this module) before
deciding disposition, exactly as `ForbiddenStrings`' and the oracle's hits
already require a human or a later pass to turn a location into an action."""


# --- content enumeration ----------------------------------------------------


def enumerate_blob_ids(repo: Path) -> tuple[str, ...]:
    """Every blob object id reachable from any ref in `repo`, deduplicated
    and sorted. Never a basename, never a path -- git's own content address."""
    listed = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--objects", "--all"],
        check=True,
        capture_output=True,
        text=True,
    )
    all_ids = [line.split(" ", 1)[0] for line in listed.stdout.splitlines() if line]
    if not all_ids:
        return ()
    checked = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "cat-file",
            "--batch-check=%(objectname) %(objecttype)",
        ],
        input="\n".join(all_ids) + "\n",
        check=True,
        capture_output=True,
        text=True,
    )
    blob_ids: set[str] = set()
    for line in checked.stdout.splitlines():
        object_name, _, object_type = line.partition(" ")
        if object_type == "blob":
            blob_ids.add(object_name)
    return tuple(sorted(blob_ids))


def read_blob_text(repo: Path, blob_id: str) -> str:
    """`blob_id`'s raw bytes, decoded permissively. A git blob is bytes, not
    guaranteed text -- `errors="replace"` scans a best-effort decoding of
    every blob rather than raising or silently skipping an undecodable one
    (see the module docstring)."""
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-p", blob_id],
        check=True,
        capture_output=True,
    )
    return result.stdout.decode("utf-8", errors="replace")


CONTENT_DISPOSITIONS: tuple[str, ...] = ("literal_replaceable", "not_pattern_tractable")
"""Every disposition a `ContentMatch` may carry -- `literal_replaceable`
(handled by `--replace-text`, because the matching pass exposes the literal
substring that matched) or `not_pattern_tractable` (handled by
`--strip-blobs-with-ids`, because it does not)."""


@dataclass(frozen=True)
class ContentMatch:
    """One blob, one pass, one disposition. Never the matched substring --
    "emit identifiers and dispositions only" (design.md `#### RedactionPlan`)."""

    blob_id: str
    pass_name: str
    disposition: str

    def __post_init__(self) -> None:
        if self.disposition not in CONTENT_DISPOSITIONS:
            raise ValueError(
                f"unknown content disposition {self.disposition!r}; "
                f"must be one of {CONTENT_DISPOSITIONS}"
            )


def classify_blob_content(
    blob_id: str,
    text: str,
    *,
    fingerprints: frozenset[str],
    window_lengths: frozenset[int],
    salt: bytes,
    forbidden: ForbiddenStrings,
) -> tuple[ContentMatch, ...]:
    """Every pass `text` (already-decoded content of `blob_id`) matches, each
    reported at most once per pass. Pass order: value matcher, forbidden
    strings, symbolic probe, identity probe."""
    hits: list[ContentMatch] = []
    if scan(text, fingerprints, window_lengths, salt):
        hits.append(
            ContentMatch(
                blob_id=blob_id,
                pass_name="value_matcher",
                disposition="not_pattern_tractable",
            )
        )
    if matches(text, forbidden):
        hits.append(
            ContentMatch(
                blob_id=blob_id,
                pass_name="forbidden_strings",
                disposition="literal_replaceable",
            )
        )
    if any(needle in text for _label, needle in SYMBOLIC_PROBES):
        hits.append(
            ContentMatch(
                blob_id=blob_id,
                pass_name="symbolic_probe",
                disposition="literal_replaceable",
            )
        )
    if _EMAIL_PATTERN.search(text):
        hits.append(
            ContentMatch(
                blob_id=blob_id,
                pass_name="identity_probe",
                disposition="literal_replaceable",
            )
        )
    return tuple(hits)


def build_content_plan(
    repo: Path,
    *,
    fingerprints: frozenset[str],
    window_lengths: frozenset[int],
    salt: bytes,
    forbidden: ForbiddenStrings,
) -> tuple[ContentMatch, ...]:
    """`classify_blob_content` over every blob `enumerate_blob_ids` finds,
    in blob-id order. Every blob is read and scanned -- none are skipped for
    being undecodable (see `read_blob_text`)."""
    matches_out: list[ContentMatch] = []
    for blob_id in enumerate_blob_ids(repo):
        text = read_blob_text(repo, blob_id)
        matches_out.extend(
            classify_blob_content(
                blob_id,
                text,
                fingerprints=fingerprints,
                window_lengths=window_lengths,
                salt=salt,
                forbidden=forbidden,
            )
        )
    return tuple(matches_out)


# --- path enumeration --------------------------------------------------------


def enumerate_paths(repo: Path) -> tuple[str, ...]:
    """Every path that has ever existed at any commit reachable from any ref
    in `repo`, deduplicated and sorted -- the **complete** enumeration form
    (`git rev-list --all | xargs -n1 git ls-tree -r --name-only | sort -u`),
    not the parent-relative added-files log filter (`git log --diff-filter=A`),
    which misses a path introduced by the root commit (design.md's Technology
    Stack row for `git`, and this task's own text: "Use the complete path
    enumeration form")."""
    revisions = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    paths: set[str] = set()
    for revision in revisions:
        listed = subprocess.run(
            ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", revision],
            check=True,
            capture_output=True,
            text=True,
        )
        paths.update(line for line in listed.stdout.splitlines() if line)
    return tuple(sorted(paths))


PATH_DISPOSITIONS: tuple[str, ...] = ("removed", "renamed")


@dataclass(frozen=True)
class PathMatch:
    """One historical path and its disposition. `target_stem` is set only
    for a `renamed` disposition -- the same neutral stems task 3.3 fixed and
    3.12 applied to the tree (design.md `#### IdentityErasure`'s queue path
    stems table), so the tip and the history agree."""

    path: str
    disposition: str
    target_stem: str | None = None

    def __post_init__(self) -> None:
        if self.disposition not in PATH_DISPOSITIONS:
            raise ValueError(
                f"unknown path disposition {self.disposition!r}; "
                f"must be one of {PATH_DISPOSITIONS}"
            )
        if self.disposition == "renamed" and self.target_stem is None:
            raise ValueError("a renamed PathMatch must carry a target_stem")
        if self.disposition == "removed" and self.target_stem is not None:
            raise ValueError("a removed PathMatch must not carry a target_stem")


def classify_path(
    path: str,
    forbidden: ForbiddenStrings,
    rename_targets: Mapping[str, str],
) -> PathMatch | None:
    """`path`'s disposition, or `None` if `path` matches neither
    `rename_targets` nor `forbidden` -- an unmatched path is not emitted at
    all, since there is nothing to report about it.

    `rename_targets` is checked first: a path being renamed still matches
    `forbidden` (its old name carries the very token being erased), so
    checking `forbidden` first would misclassify every rename as a removal.
    """
    if path in rename_targets:
        return PathMatch(
            path=path, disposition="renamed", target_stem=rename_targets[path]
        )
    if matches(path, forbidden):
        return PathMatch(path=path, disposition="removed")
    return None


def build_path_plan(
    repo: Path,
    forbidden: ForbiddenStrings,
    rename_targets: Mapping[str, str],
) -> tuple[PathMatch, ...]:
    """`classify_path` over every path `enumerate_paths` finds, keeping only
    the matched ones, in path order."""
    plan: list[PathMatch] = []
    for path in enumerate_paths(repo):
        classified = classify_path(path, forbidden, rename_targets)
        if classified is not None:
            plan.append(classified)
    return tuple(plan)


# --- would-be-pruned check ---------------------------------------------------


def commit_changed_paths(repo: Path, commit: str) -> tuple[str, ...]:
    """Every path `commit` changed relative to its parent(s), deduplicated
    and sorted. `--root` diffs a parentless (root) commit against the empty
    tree rather than reporting nothing; `-m` diffs a merge commit against
    each parent in turn rather than reporting nothing for it either -- both
    flags are no-ops for an ordinary single-parent commit.

    `-m`'s per-parent diffing is an incomplete substitute for a true
    combined diff, not a safe default: it can UNION IN a path a merge
    commit's own tree does not actually change relative to at least one
    parent, so `would_be_pruned_commits` can under-flag a merge whose
    post-removal tree is genuinely empty against every parent (verified: a
    merge resolving one parent's addition away reports that addition as
    "changed" against the OTHER parent, even though the merge's own tree
    equals the first parent's exactly). That is strictly better than git's
    own default for a merge commit, which reports no changed path at all --
    but it is a documented coverage gap in `would_be_pruned_commits`, not a
    claim that over-reporting is harmless."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "diff-tree",
            "--root",
            "-m",
            "--no-commit-id",
            "--name-only",
            "-r",
            commit,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(sorted({line for line in result.stdout.splitlines() if line}))


def _is_removed(
    path: str,
    forbidden: ForbiddenStrings,
    rename_targets: Mapping[str, str],
) -> bool:
    classified = classify_path(path, forbidden, rename_targets)
    return classified is not None and classified.disposition == "removed"


def would_be_pruned_commits(
    repo: Path,
    forbidden: ForbiddenStrings,
    rename_targets: Mapping[str, str],
) -> tuple[str, ...]:
    """Every commit reachable from any ref whose **entire** changed-path set
    lies inside the removal set (`disposition == "removed"`) -- a commit
    whose diff `--invert-paths` would empty out. A commit with an empty
    changed-path set (e.g. an already-empty merge) is not reported: it has
    nothing that could be removed by this plan, so it is not what this check
    exists to catch."""
    revisions = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    pruned: list[str] = []
    for commit in revisions:
        changed = commit_changed_paths(repo, commit)
        if not changed:
            continue
        if all(_is_removed(path, forbidden, rename_targets) for path in changed):
            pruned.append(commit)
    return tuple(pruned)


class WouldBePrunedError(RuntimeError):
    """Raised by `build_redaction_plan` when `would_be_pruned_commits` finds
    at least one commit. Halting here, rather than letting the rewrite
    silently retain such a commit empty or silently drop it, is what keeps
    Req 9.3's complete pre-to-post commit mapping from gaining a hole."""


# --- orchestration ------------------------------------------------------------


@dataclass(frozen=True)
class RedactionPlan:
    """The whole plan: every classified content match, every classified path
    match. Renders to two identifier-and-disposition tables and nothing
    else -- see `render_content_plan_tsv` / `render_path_plan_tsv`."""

    content_matches: tuple[ContentMatch, ...]
    path_matches: tuple[PathMatch, ...]


def build_redaction_plan(
    repo: Path,
    *,
    fingerprints: frozenset[str],
    window_lengths: frozenset[int],
    salt: bytes,
    forbidden: ForbiddenStrings,
    rename_targets: Mapping[str, str],
) -> RedactionPlan:
    """Run the would-be-pruned check first and halt on any hit
    (`WouldBePrunedError`), then build both enumerations. Order matters: a
    plan built over a history where a commit would be pruned to empty is not
    a plan `HistoryRewrite` can safely consume, so this function never
    returns one."""
    pruned = would_be_pruned_commits(repo, forbidden, rename_targets)
    if pruned:
        raise WouldBePrunedError(
            f"{len(pruned)} commit(s) would be pruned to empty by the "
            f"removal set (Req 9.3): {', '.join(pruned)}"
        )
    content_matches = build_content_plan(
        repo,
        fingerprints=fingerprints,
        window_lengths=window_lengths,
        salt=salt,
        forbidden=forbidden,
    )
    path_matches = build_path_plan(repo, forbidden, rename_targets)
    return RedactionPlan(content_matches=content_matches, path_matches=path_matches)


# --- out-of-repository artifact: write / read round trip --------------------

_CONTENT_COLUMNS: tuple[str, ...] = ("blob_id", "pass_name", "disposition")
_PATH_COLUMNS: tuple[str, ...] = ("path", "disposition", "target_stem")


def _check_no_tab_or_newline(fields: Sequence[str]) -> None:
    for field in fields:
        if "\t" in field or "\n" in field:
            raise ValueError(
                f"plan field contains a tab or newline, which would corrupt "
                f"the tsv row structure: {field!r}"
            )


def render_content_plan_tsv(content_matches: Sequence[ContentMatch]) -> str:
    """Render `content_matches` as a header row plus one tab-separated data
    row per match, in the given order. Carries only `blob_id`, `pass_name`
    and `disposition` -- no matched substring, no blob content."""
    lines = ["\t".join(_CONTENT_COLUMNS)]
    for item in content_matches:
        fields = (item.blob_id, item.pass_name, item.disposition)
        _check_no_tab_or_newline(fields)
        lines.append("\t".join(fields))
    return "\n".join(lines) + "\n"


def render_path_plan_tsv(path_matches: Sequence[PathMatch]) -> str:
    """Render `path_matches` as a header row plus one tab-separated data row
    per match, in the given order."""
    lines = ["\t".join(_PATH_COLUMNS)]
    for item in path_matches:
        fields = (item.path, item.disposition, item.target_stem or "")
        _check_no_tab_or_newline(fields)
        lines.append("\t".join(fields))
    return "\n".join(lines) + "\n"


def _parse_row(line: str, columns: Sequence[str]) -> tuple[str, ...]:
    fields = tuple(line.split("\t"))
    if len(fields) != len(columns):
        raise ValueError(
            f"malformed plan row {line!r}: expected {len(columns)} tab-separated "
            f"fields ({columns}), got {len(fields)}"
        )
    return fields


def parse_content_plan_tsv(text: str) -> tuple[ContentMatch, ...]:
    """The inverse of `render_content_plan_tsv`: every data row, in file
    order, as a `ContentMatch`. Raises `ValueError` (via `ContentMatch.
    __post_init__`) on a row carrying a disposition `render_content_plan_tsv`
    never writes -- including a `PathMatch`-shaped row read from the wrong
    file, whose third field is never one of `CONTENT_DISPOSITIONS`.

    The blank-line skip below is dead code against this module's own
    output: `render_content_plan_tsv` always ends with exactly one trailing
    newline, so `str.splitlines()` never produces a trailing empty element,
    and no row in between is ever blank. It exists only for a plan file a
    human has hand-edited after the fact -- a stray blank line left by a
    manual edit is skipped rather than raising on `_parse_row`'s field
    count."""
    lines = text.splitlines()
    if not lines:
        return ()
    rows: list[ContentMatch] = []
    for line in lines[1:]:
        if not line:
            continue
        blob_id, pass_name, disposition = _parse_row(line, _CONTENT_COLUMNS)
        rows.append(
            ContentMatch(blob_id=blob_id, pass_name=pass_name, disposition=disposition)
        )
    return tuple(rows)


def parse_path_plan_tsv(text: str) -> tuple[PathMatch, ...]:
    """The inverse of `render_path_plan_tsv`: every data row, in file order,
    as a `PathMatch`. An empty `target_stem` field reads back as `None`,
    matching what `render_path_plan_tsv` writes for a `removed` row. Raises
    `ValueError` (via `PathMatch.__post_init__`) on a row carrying a
    disposition `render_path_plan_tsv` never writes -- including a
    `ContentMatch`-shaped row read from the wrong file, whose second field
    is never one of `PATH_DISPOSITIONS`.

    Same dead-code note as `parse_content_plan_tsv`'s blank-line skip: it is
    unreachable from this module's own output and exists only for a
    hand-edited plan file."""
    lines = text.splitlines()
    if not lines:
        return ()
    rows: list[PathMatch] = []
    for line in lines[1:]:
        if not line:
            continue
        path, disposition, target_stem = _parse_row(line, _PATH_COLUMNS)
        rows.append(
            PathMatch(
                path=path,
                disposition=disposition,
                target_stem=target_stem or None,
            )
        )
    return tuple(rows)


def write_redaction_plan(
    plan: RedactionPlan, content_out: Path, path_out: Path, *, repo_root: Path
) -> None:
    """Write both tables to `content_out` / `path_out`, creating parent
    directories as needed.

    `repo_root` is required, and both destinations are refused if either
    resolves inside it -- the same posture `tests._forbidden_strings.load`
    takes for its own source path, for the same reason: a rendered path
    plan necessarily carries forbidden path fragments (every `removed` row
    IS one), so writing it inside the repository would make this artifact
    the very thing Req 11.2 forbids.
    """
    resolved_repo_root = repo_root.resolve()
    for destination in (content_out, path_out):
        resolved = destination.resolve()
        if resolved == resolved_repo_root or resolved.is_relative_to(
            resolved_repo_root
        ):
            raise ValueError(
                f"refusing to write a redaction plan inside the repository "
                f"working tree: {destination} resolves under {resolved_repo_root}"
            )
    content_out.parent.mkdir(parents=True, exist_ok=True)
    content_out.write_text(
        render_content_plan_tsv(plan.content_matches), encoding="utf-8"
    )
    path_out.parent.mkdir(parents=True, exist_ok=True)
    path_out.write_text(render_path_plan_tsv(plan.path_matches), encoding="utf-8")


def read_redaction_plan(content_path: Path, path_path: Path) -> RedactionPlan:
    """`RedactionPlan` read back from `content_path` / `path_path` -- the
    inverse of `write_redaction_plan`, using `parse_content_plan_tsv` /
    `parse_path_plan_tsv`."""
    return RedactionPlan(
        content_matches=parse_content_plan_tsv(
            content_path.read_text(encoding="utf-8")
        ),
        path_matches=parse_path_plan_tsv(path_path.read_text(encoding="utf-8")),
    )


def run() -> None:
    """`purge plan` -- not yet wired to a CLI-level source for `fingerprints`,
    `forbidden` and `rename_targets`. The functions above (`build_redaction_plan`
    and its parts) are implemented and tested (task 5.2); wiring the CLI to a
    real, out-of-repository scratch source is a later task's responsibility,
    run from `main` in the primary worktree -- the same posture
    `scripts/purge/preflight.py::run` states for its own CLI wiring.
    """
    typer.echo(
        "purge plan: RedactionPlan CLI wiring not yet implemented "
        "(build_redaction_plan is implemented; a later task supplies its "
        "scratch-artifact inputs at the call site)",
        err=True,
    )
    raise typer.Exit(code=1)
