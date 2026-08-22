---
id: 2026-08-18-assert-untouched-is-blind-to-move-aside-and-back
title: The rehearsal's real-repository safety assertion cannot see a move-aside-and-back of .git
status: open
importance: high
importance_why: It is the assertion protecting the one thing this spec exists to protect, and its blind spot is the exact evasion a reviewer already planted successfully against replace.py in task 7.6.
effort: S
kind: gap
area: encumbered-content-purge, tests/purge/test_replace_rehearsal.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.7, parent-run mutation probe after five reviewer dispatches died on API 529)
pinned_at: aeabf8e
resume_command: "do: close the move-aside-and-back blind spot in test_replace_rehearsal.py::_assert_untouched, or state the exemption with the measurement that justifies it"
context:
  - tests/purge/test_replace_rehearsal.py
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

`_assert_untouched` is task 7.7's answer to the observable "no rehearsal step
touched the working repository". It compares the real repository's `HEAD`
against a snapshot taken before the rehearsal, plus the `(st_dev, st_ino)`
and `st_mtime_ns` of `real_repo / ".git"` -- in the worktree this test runs
in, a small regular pointer file (`gitdir: <path>`), not a directory.

(Originally written and measured against a scratch repository where `.git`
is a real directory; re-measured below against the pointer-file shape the
assertion actually faces in this worktree.)

Measured against a scratch repository where `.git` is a real directory: it
detects two of three tamper classes and is **blind to the third**.

| Probe | Result (scratch repo, `.git` a real directory) |
|---|---|
| A new entry written inside `.git` (changes the directory mtime) | DETECTED |
| `.git` moved aside and moved back (`adopt.move_clone` out and in) | **NOT DETECTED** |
| `HEAD` moved to a different commit via `update-ref` | DETECTED |

**Re-measured against the shape the assertion actually faces.** This test
runs in `/Users/josh/code/fitdocs-purge-major7`, a worktree, where
`real_repo / ".git"` is a 73-byte regular pointer file (`gitdir: <path to
the real gitdir>`), not a directory -- confirmed via `ls -la`/`file`/`stat`.
Re-running probe A against that shape (writing a new file inside the real
gitdir the pointer points at, not inside the pointer file itself) leaves the
pointer file's `(st_dev, st_ino)` **and** `st_mtime_ns` unchanged:

| Probe | Result (worktree, `.git` a pointer file) |
|---|---|
| A new entry written inside the real gitdir the pointer points at | **NOT DETECTED** -- the pointer file itself is untouched |
| `.git` moved aside and moved back (`adopt.move_clone` out and in) | **NOT DETECTED** |
| `HEAD` moved to a different commit via `update-ref` | DETECTED |

So in the worktree where this test actually runs, the
`(st_dev, st_ino, st_mtime_ns)` stat detects neither tamper class **measured**
against the pointer-file shape above -- but it is not inert: a byte-identical
rewrite of the pointer file (`rm` + `cp`) changes its `(st_dev, st_ino)` while
leaving `git rev-parse HEAD` unchanged, so for that tamper class the stat arm
is the sole detector, and the "realistic mis-wiring" probe below (a fresh
`.git` swapped in) is caught by it too. The original scratch-repo measurement
for probe A is not wrong, only not representative of the running system -- it
stays labelled above as a scratch-repository result. The conclusion (a
move-aside-and-back is undetected) is unaffected either way and stays.

## Why it matters

The task 7.6 Implementation Notes record that a reviewer probing the then-new
`replace.py` guard planted exactly this — "a move-aside-and-back of the repo
root" — and it left the suite green. The countermeasure landed for `replace.py`.
The assertion written one task later to protect the *real repository* has the
same hole.

Severity is bounded and should be stated honestly rather than inflated: a
rename within one filesystem preserves the inode, and a directory's own mtime
is unchanged by renaming it (the parent's mtime changes, not its own), so the
end state after a move-aside-and-back is genuinely identical. The realistic
mis-wiring this assertion guards against — a `repo_root` argument accidentally
pointing at the real repository, so the driver archives the real `.git` and
swaps a fresh one in — DOES change `(st_dev, st_ino)` and IS caught. What is
uncovered is the transient window in which the real repository is disassembled
and reassembled.

The implementer declared this assertion outside its mutation sweep, on the
stated ground that "no production code path in scope could plausibly touch the
real repo, so there is no meaningful mutation to name". That reasoning is what
the measurement contradicts: meaningful mutations exist, two of them fire, and
running them is what found the third that does not.

## Evidence

Measured at `aeabf8e` in the worktree, through `uv run pytest` (never a bare
interpreter), with a temporary probe test appended to the module and then
removed; the module was restored byte-identical afterwards (matching
`shasum -a 256`).

The probe called `_assert_untouched` against scratch repositories under
`tmp_path` only — never the real repository — snapshotting, tampering, and
re-calling. Arm A and arm C raised `AssertionError`; arm B printed
`PROBE ARM 2: move-aside-and-back NOT DETECTED` and the call returned cleanly.

## How to pick it up

Two coherent resolutions.

(a) Close it: additionally snapshot something a rename cannot preserve — for
example the mtime of the *parent* directory of `.git`, or a recorded
`(st_dev, st_ino, st_mtime_ns)` for a specific file *inside* `.git` such as
`HEAD`, which a move-aside-and-back leaves untouched but a disassembly does
not. Then re-run all three probe arms and pin the third.

(b) Declare it: state in the helper's docstring that a move-aside-and-back is
outside what the assertion detects, with the reason (rename preserves inode and
directory mtime) and the argument that the end state is identical. A declared
gap is acceptable in this repo; an undeclared one is the defect.

Do NOT resolve it by asserting the exemption without measuring — this queue
item exists because the exemption was asserted rather than measured.
