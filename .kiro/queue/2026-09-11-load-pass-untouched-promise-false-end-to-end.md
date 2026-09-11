---
id: 2026-09-11-load-pass-untouched-promise-false-end-to-end
title: The contract's "leaves that region and its frontmatter keys untouched" promise is false end-to-end
status: open
importance: medium
importance_why: Published prose that is true of one pass in isolation and false of the command a user actually runs.
effort: S
kind: docs
area: docs/ownership-contract.md
created: 2026-09-11
surfaced_by: review of queue item 2026-09-11-ownership-doc-placement-unconditional
pinned_at: 1dc8633
resume_command: "do: make the ownership contract's load-region promise true of the commands a user runs, not just of the pass in isolation"
context:
  - docs/ownership-contract.md
  - src/fitdocs/load/engine.py
blocked_by:
  - 2026-09-11-regen-destroys-load-keys-on-foreign-or-superseded-region
---

## What

`docs/ownership-contract.md:368-372` promises that when a user has hand-authored
the `load` region, the training-load pass "leaves that region and its frontmatter
keys untouched".

True of the pass. False of `regen` and `sync`, where the engine's frontmatter
rebuild has already dropped the three `load_*` keys before the pass runs and
declines to restore them. See
`2026-09-11-regen-destroys-load-keys-on-foreign-or-superseded-region` for the
reproduction.

## Why it matters

This is the sentence a user reads to decide whether hand-authoring the `load`
region is safe. It describes a component; the user runs a command. The gap
between them is exactly the data loss the sibling item reports, so the prose
actively reassures the user about the thing that will bite them.

It is also the same defect class as the item this was found while fixing: a
published sentence that is true of the code path its author read and false of
the file the user ends up with.

## Evidence

`docs/ownership-contract.md:368-372` versus the CLI reproduction in the sibling
item -- a FOREIGN-region document loses all three keys across one `fitdocs regen`.

## How to pick it up

**Do the sibling item first.** If the behavior changes, this sentence may become
true as written and need no edit at all -- fixing the prose first risks
documenting a bug that is about to be fixed.

1. Read the Overwrite Semantics bullets for `load`, `regen` and `sync` together
   -- the promise is split across them, which is how the end-to-end case fell
   between.
2. Once the behavior is settled, make each bullet true of the command it names,
   not of the pass it describes.
3. Verify by driving the real CLI on a FOREIGN-region document, not by reading
   `engine.py`.

Done looks like: every Overwrite Semantics bullet is true of running that
command end to end.
