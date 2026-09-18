---
name: fitdocs-workouts
description: Processes the fitdocs inbox -- new .fit files waiting to become workout documents -- by draining it and reading the resulting report. Use when new .fit files have arrived, or when the wiki's workouts look stale and a fresh sync is due.
license: MIT
compatibility: Requires the fitdocs command to be installed and on the agent's path.
metadata:
  version: 0.1.0
---

# Process the fitdocs inbox

## When this applies

- New `.fit` files have arrived in the configured inbox, however they got
  there -- a watch export, a manual drop, another tool's script.
- The wiki's workouts look stale: no recent workout documents exist even
  though the athlete has presumably been training.

## Commands to run

Run, routinely, in this order:

1. `fitdocs sync --no-prompt` -- with no source argument this drains the
   configured inbox rather than an explicit directory. `--no-prompt` keeps
   an unattended agent from ever blocking on a training-load prompt (it has
   the same effect stdin being a non-terminal already has for an
   unattended run; pass it explicitly rather than relying on that); any
   document the load pass would otherwise have prompted for is simply left
   uncomputed. Run `fitdocs sync --no-prompt --retry-quarantined` instead,
   only when the user has asked you to re-attempt files already recorded
   as quarantined -- never on your own initiative (see Quarantined below).
2. `fitdocs check` -- confirms the data root still matches the installed
   contract. Run it after a drain to confirm the tree is healthy, or any
   time you want to check the tree without draining anything.

```bash
fitdocs sync --no-prompt
fitdocs check
```

Run `fitdocs regen` separately, and only when it is actually called for --
either `fitdocs check` reported a document whose remedy reads "run
`fitdocs regen` to bring it to the current format", or a fitdocs upgrade's
release notes say the generated-document format changed. Never run it as
part of the routine pair above, and never run it speculatively.

```bash
fitdocs regen
```

## Reading the report

`fitdocs sync`'s drain prints an inbox path followed by a counts table with
eight rows, but they are not eight peers of one partition. Every admitted
file lands in exactly one of written / skipped / failed; a file not yet
admitted lands in exactly one of deferred / quarantined instead. Warnings
annotate a file alongside whichever of those it landed in -- never a
partition of their own. Moved and move-failures describe what happened
*afterward* to a file already counted as written or skipped: whether its
now-archived source was also relocated out of the inbox.

| Channel | Field | Meaning | Do |
|---------|-------|---------|----|
| Written | `written` | A workout document was produced or updated from an admitted file. | Nothing needed. |
| Skipped | `skipped` | Either the file's bytes were already archived (finished work), or the matched document already records a newer document-format version and was left untouched (nothing archived; it stays that way until the tool is upgraded to recognize that format). | Nothing needed for the already-archived case; for the newer-format case, nothing to do now -- it is retried automatically on a later run. |
| Failed | `failures` | The file could not be processed for a reason the report names. | Read the message; fix the source file if you can, or report the reason to the user. |
| Warnings | `warnings` | A non-fatal condition annotated alongside an admitted file's written/skipped/failed outcome -- never its own outcome, and never changes which of the three the file landed in. | Read it; it usually needs nothing further. |
| Deferred | `deferred` | The file was not yet observed stable across the settle interval, or a stable file could not be read -- left completely untouched either way. | No action -- it is reconsidered automatically on the next drain. |
| Quarantined | `quarantined` | The file previously failed for a source-level reason and is remembered rather than retried. | This needs the user, not the agent -- never retry a quarantined file on your own judgment. |
| Moved | `moved` | A written or skipped file's now-archived source was additionally relocated out of the inbox (only when the disposition is configured to move files). | Nothing needed. |
| Move failures | `move_failures` | The file was processed successfully -- its content is already archived, counted as written or skipped -- but relocating it out of the inbox afterward failed. | Nothing to do: the file stays in the inbox and the move is retried automatically on the next drain. This is never a reason to reprocess the file. |

## Ownership boundary

The fitdocs-owned tree -- the directories fitdocs writes generated content
into -- is tool-owned: an agent maintaining this wiki never hand-edits
generated content there. Some regions inside those documents are the
author's own and are preserved across every fitdocs write. The authority
for exactly which paths and regions are owned, in this data root, is the
`AGENTS.md` declaration fitdocs emits inside the owned tree itself; the
[published ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md)
is the detail behind it. Read those rather than assuming a boundary from
this skill.

## Further reading

- [Inbox interface](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/inbox.md) -- default location, every settings key, drain semantics, and the safeguards.
- [Ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md) -- the published detail behind the in-tree declaration.
- [Configuration](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/configuration.md) -- the data-root contract and `fitdocs.toml`.
