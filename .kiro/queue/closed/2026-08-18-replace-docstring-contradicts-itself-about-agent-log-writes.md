---
id: 2026-08-18-replace-docstring-contradicts-itself-about-agent-log-writes
title: replace.py's module docstring says old_git_dir is unwritten before the pre-swap rows, but the shared agent log lives inside it
status: done
importance: medium
importance_why: Exactly one of two sibling sentences is false whichever way the log's location is resolved, and task 8.2's operator reads this docstring to know what a pre-swap failure leaves behind.
effort: S
kind: inconsistency
area: encumbered-content-purge, scripts/purge/replace.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.6 review round 4)
pinned_at: c3d2201
resume_command: "do: settle whether run_replace's `log` parameter is deliberately decoupled from old_git_dir/agent-log, then correct whichever of replace.py's two sibling docstring sentences is false under that answer"
context:
  - scripts/purge/replace.py
  - scripts/purge/adopt.py
  - .kiro/specs/encumbered-content-purge/design.md
blocked_by: []
---

## What

`replace.py`'s module docstring makes two claims that cannot both be true:

- *"What is NOT written before the pre-swap rows have all passed is
  `old_git_dir`'s own content and the working directory — neither is opened
  for write before that point."*
- a sibling sentence listing what "are the only things this driver ever writes
  to directly", which omits the agent log entirely.

The shared agent log lives at `$(git rev-parse --git-common-dir)/agent-log` —
that is, **inside `old_git_dir`**, which is exactly why it is the carry-over
checklist's first item. So `gate`'s `PROCEEDING` line and
`_append_certified_tip_line`'s `CERTIFIED_TIP` line are appended into
`old_git_dir`'s own content **before** the pre-swap rows run.

## Why it matters

No behavioural consequence: the writes are append-only coordination records
and the crash-safety posture is unaffected — a pre-swap failure still discards
only the scratch clone. The problem is that task 8.2's operator reads this
docstring to know what a pre-swap failure leaves behind, and it currently
says "nothing in `old_git_dir`" when two log lines will be there.

The shipped test reads "untouched" only because it deliberately points
`log` at `tmp_path / "agent-log"` — a *different* file from the `agent_log`
it asserts on. That is a legitimate test-isolation choice, but it means the
test cannot notice the docstring's claim being false in the real wiring.

## Evidence

Reported by the task 7.6 reviewer, which measured it rather than reading it:
re-running the shipped pre-swap-failure scenario with the single change
`log = old_git_dir / "agent-log"` appends two lines into `old_git_dir`'s own
content before the pre-swap rows, and the failure does not undo them.

Supporting: `scripts/purge/adopt.py`'s module docstring states the log's
location; the carry-over checklist's first item is built with
`source=old_git_dir / "agent-log"`.

Repro script the reviewer left at
`$TMPDIR/.../scratchpad/rev76/probe_oldgit.py` (session-scoped; re-derive
rather than relying on it).

Not independently re-derived by the controller.

## How to pick it up

First settle the design question, because it decides which sentence to fix:
is `run_replace`'s `log` parameter **deliberately** decoupled from
`old_git_dir/agent-log` (so a real run should pass a log path outside the
doomed root), or does the real run pass the in-`.git` log and simply accept
the two appended lines? `design.md` › `HistoryReplacement` step 1 and
Decision 7 point 4 are the relevant text.

Then correct whichever sentence is false under that answer — and prefer
deleting the absolute claim to qualifying it. Done when the two sibling
sentences agree with each other and with the wiring task 8.2 will use.

## Resolution

**Closed `done` 2026-08-23 — the subject was retired, and retirement is the
resolution.** Post-purge queue triage after `encumbered-content-purge`
completed (spec 57/57, `87ce085`).

This item's subject was the purge's own one-shot tooling: a module under
`scripts/purge/`, a test under `tests/purge/`, or a precondition on a purge
task that has since run. Task 9.3 (`c18ec26`) deleted `scripts/` entire and
`tests/purge/` less three relocations; `ls scripts/ tests/purge/` errors on
`HEAD`. The operation those modules governed — sweep, redact, replace, adopt,
verify — executed to completion and is not repeatable: the history replacement
is a fresh root (`c3d2201`) with no mapping by construction.

There is therefore no future run for this defect to affect, and no code left to
carry it. The retirement record is `docs/reference/history-rewrites.md` § 8.

Checked before closing: the item's subject does not survive in the three
relocated guards (`tests/_forbidden_strings.py`, `tests/test_forbidden_strings.py`,
`tests/_content_oracle.py`). Items whose subject *did* survive were kept open
in the same triage.
