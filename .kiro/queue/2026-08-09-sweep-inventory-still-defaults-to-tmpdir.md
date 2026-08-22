---
id: 2026-08-09-sweep-inventory-still-defaults-to-tmpdir
title: build_sweep_inventory still defaults its scratch root to the temp directory whose cleanup destroyed the purge artifacts
status: open
importance: medium
importance_why: It is the one remaining tool that writes a one-shot purge artifact into $TMPDIR by default, which is exactly how ten artifacts were lost on 2026-08-07; adopt.py has already moved to ~/.fitdocs-purge/.
effort: S
kind: bug
area: scripts/purge
created: 2026-08-09
surfaced_by: reviewer subagent during /kiro-impl encumbered-content-purge (review of the artifact reconstruction and task 7.1)
pinned_at: 8391e47
resume_command: "do: Change build_sweep_inventory.py's default --out root from $TMPDIR/fitdocs-purge/ to the durable scratch root ~/.fitdocs-purge/ that adopt.py already records, so a caller who omits --out cannot write a one-shot artifact somewhere the OS temp cleaner reaches."
context:
  - scripts/purge/build_sweep_inventory.py
  - scripts/purge/adopt.py
  - .kiro/queue/closed/2026-08-07-scratch-artifacts-lost-to-tmpdir-cleanup.md
blocked_by: []
---

## What

`scripts/purge/build_sweep_inventory.py` computes its default output path from
`os.environ["TMPDIR"]`, giving `$TMPDIR/fitdocs-purge/sweep-inventory.tsv`. Its
module docstring also documents that location as "the already-established
scratch root every other out-of-repository artifact in this purge lives in".

That is no longer true. `scripts/purge/adopt.py:32` records the durable root as
`~/.fitdocs-purge/`, and every artifact was moved there after the loss.

## Why it matters

The macOS temp cleaner emptied `$TMPDIR/fitdocs-purge/` on 2026-08-07,
destroying ten one-shot artifacts, five of which were still missing until
2026-08-09. This script is the last one whose *default* puts a fresh artifact
back in that directory. A caller who omits `--out` silently re-creates the
exact failure mode, and the docstring actively tells them it is the right
place.

## Evidence

- `scripts/purge/build_sweep_inventory.py:16,19,41` — the `$TMPDIR` default and
  the docstring claim
- `scripts/purge/adopt.py:32` — records `~/.fitdocs-purge/` as the scratch root
- `.kiro/queue/closed/2026-08-07-scratch-artifacts-lost-to-tmpdir-cleanup.md` —
  the original loss

## How to pick it up

Change the default and correct the docstring's claim in the same change. Both
runs of this script on 2026-08-09 passed `--out` explicitly, so nothing depends
on the current default.

Done when omitting `--out` writes to the durable root.
