---
id: 2026-08-09-adopt-checklist-can-destroy-carried-material
title: Task 7.4's carry-over checklist asserts existence only, so pointing it at the source root destroys the material it claims to carry
status: done
importance: high
importance_why: 7.4 destroys the old repository directory. If build_checklist is handed the source root rather than the clone root, every assertion passes against files that are about to be deleted, and the Req 1.7 source material, data/ and the agent log are lost with no copy anywhere.
effort: M
kind: bug
area: encumbered-content-purge, scripts/purge/adopt.py
created: 2026-08-09
surfaced_by: reviewer subagent during /kiro-impl encumbered-content-purge (review of the artifact reconstruction and task 7.1)
pinned_at: 8391e47
resume_command: "do: Before running task 7.4, make the carry-over checklist prove the carried material exists at the CLONE root and has been physically moved, not merely that some path exists. Require build_checklist to take the clone root, and move data/, the Req 1.7 source material and the agent log across before the old directory is vacated."
context:
  - scripts/purge/adopt.py
  - .kiro/specs/encumbered-content-purge/tasks.md
  - .kiro/specs/encumbered-content-purge/design.md
blocked_by: []
---

## What

`assert_carry_over` in `scripts/purge/adopt.py` is a pure `Path.exists()` check,
and `repo_root` is a caller-supplied argument. Nothing in the module constrains
which repository root the checklist is built against.

Task 7.4 moves the verified clone to the original absolute repository path and
destroys the old repository directory. If the checklist is built against the
**source** root — the doomed one — every assertion passes, because the files do
still exist at the moment of the check. They are then deleted.

`move_clone` explicitly leaves vacating the target directory to 7.4, and no
code in the module moves the carried material.

## Why it matters

`design.md` lists `data/`, the Requirement 1.7 source material (two `.xlsx`
workbooks and the reference-text scans, currently untracked at the repository
root) and the shared agent log as "carried across". They are **untracked**, so
they exist in exactly one place on disk and in no commit. The clone created in
7.2 copies only git objects, so it carries none of them.

A checklist that asserts existence rather than transfer therefore reports a
clean carry-over at the exact moment the only copy is about to be destroyed.
This is the highest-consequence hazard remaining in Major 7 and it is
unrecoverable: the material is not on the remote either.

## Evidence

- `scripts/purge/adopt.py:160-180` — `assert_carry_over` is pure `exists()`
- `scripts/purge/adopt.py:230-262` — `repo_root` is caller-supplied
- `scripts/purge/adopt.py:359-377` — `move_clone` leaves vacating to 7.4
- `.kiro/specs/encumbered-content-purge/design.md:1582-1598` — lists the
  carried material; no code moves it

## How to pick it up

Do not treat this as a code-only fix. The reviewer of 7.4 must require that the
checklist is built against the clone root and that each carried item is
verified **present at the destination** before the source directory is vacated
— a content check, not an existence check, since existence at the source is
exactly the false positive.

Consider making the root a non-defaultable, explicitly-named parameter so a
caller cannot pass the wrong one positionally, in the same spirit as
`run_rewrite`'s keyword-only `repo`/`repo_root` pair.

Done when 7.4 cannot pass its checklist against a directory it is about to
delete.

## Resolution (2026-08-17, `impl/rewrite-preconditions` off `89b06b8`)

Fixed in code and in `tasks.md` 7.4, as this item required — not as a code-only
change.

`scripts/purge/adopt.py`:

- `CarryOverItem` is now `kw_only` and carries `path` (the destination) and
  `source` (where a carried item is carried *from*; `None` marks the other
  class, an artifact preserved in place). Two `Path` fields whose transposition
  is the whole hazard can no longer be filled positionally.
- `assert_carry_over(items, *, doomed_root)` — non-defaultable and keyword-only
  — refuses any item resolving inside the doomed root, any destination that is
  the *same file* as its source (`Path.samefile`, which catches a hard link
  whose path is legitimately outside), any destination whose **content digest**
  differs from the source's (byte-for-byte for a file; over every entry's
  relative path, kind and content for a directory), and any carried item whose
  source has already vanished — the move-then-assert order, which proves
  nothing. It names every unaccepted item with its reason, never just the first.
- `build_checklist` takes `clone_root`/`clone_git_dir` and
  `source_root`/`source_git_dir` as four separately-named keyword arguments and
  refuses outright if the two roots are equal or nested, so the mistake is
  caught before an item is built. Source-material paths must lie under the
  source root.
- `detect_data_root_forms` now distinguishes the two classes correctly: the
  pointer file is at the repository root and is *carried*; the environment
  variable names a data root elsewhere that nothing moves and is *preserved in
  place* (still refused if it resolves inside the doomed root).

The regression test builds the checklist the old way — every destination the
still-present file at the source root — asserts those paths do exist (so the
old `Path.exists()` implementation demonstrably passed it) and proves the new
code names every one of them. Twelve further mutations of the new guards were
each caught by a named test.

`tasks.md` 7.4 now requires **copy, assert, then vacate** in that order (the
content comparison needs the source intact), the checklist built against the
clone root and asserted with the source root named as the doomed root, and it
records the symlink trap: the carried root `agent-log` link must be relative or
be re-pointed after the move, since an absolute link into the scratch clone
path dangles the moment the clone is moved into place.

### Review round 2 (2026-08-17) — three false passes closed

An independent reviewer attacked the new checklist rather than reading it and
found three ways a plausible implementation still accepts material that is
about to be destroyed. All three are now closed and pinned:

- **The directory digest's content component was unpinned.** The tests covered
  "missing one entry" (names differ) and "copied whole"; nothing covered the
  realistic `data/` failure — an interrupted `cp -R`/`rsync` leaving every
  filename present with one file truncated. Deleting `entry.read_bytes()` left
  the whole suite green. Now pinned by a parametrized fixture covering both
  truncation to zero length and a same-name/different-bytes edit, with the
  entry-name equality of the two trees asserted so nothing else can be doing
  the rejecting.
- **`_is_within`'s destination resolution was unpinned**, and for a
  preserved-in-place item it is the *only* guard — `samefile` and the digest
  never run. Now pinned by a destination that is a symlink into the doomed
  root and one spelled with `../`, each asserted to look outside the doomed
  root before resolution.
- **Case folding.** On this repository's own filesystem a doomed root spelled
  `Source-Repo` and a destination spelled `source-repo/...` name the same
  directory, while `Path.is_relative_to` compares components and says
  otherwise — a measured false pass. `_is_within` now falls back to filesystem
  identity (`Path.samefile` over the resolved path and its ancestors). The
  test probes whether the filesystem folds case and skips, named, where it
  does not.

Two further gaps closed in the same round: a symlink *inside* a carried
directory used to digest as a contentless `dir` entry (two trees with
differently-targeted links digested identically), so directory entries that
are symlinks now digest as their link target; and a carried tree containing a
link back into the doomed root is refused outright, since the digest cannot
catch that one — source and destination agree exactly, which is the problem.
Consequence for the operator, now in `tasks.md` 7.4: the carry-over copy must
**preserve** symlinks (`cp -a`), not dereference them.

The `dir:`/`file:` kind prefix and the blank-source branch were also unpinned
and are now covered — an empty directory and a zero-byte file hash to the same
sha256 digest, so the prefix is the only thing separating them.
