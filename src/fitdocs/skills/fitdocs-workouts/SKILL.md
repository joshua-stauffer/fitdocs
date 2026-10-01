---
name: fitdocs-workouts
description: Pulls new .fit files from the athlete's configured connectors and drains the inbox into workout documents, then reads the resulting pull and drain reports. Use when new .fit files have arrived, or when the wiki's workouts look stale and a fresh sync is due.
license: MIT
compatibility: Requires the fitdocs command to be installed and on the agent's path.
metadata:
  version: 0.1.0
---

# Process the fitdocs inbox

## When this applies

- New `.fit` files have arrived in the configured inbox, however they got
  there -- a configured connector's pull, a watch export, a manual drop,
  another tool's script.
- The wiki's workouts look stale: no recent workout documents exist even
  though the athlete has presumably been training.

## Commands to run

Run, routinely, in this order:

1. `fitdocs pull --sync --no-prompt` -- fetches new activities from every
   configured connector instance, delivers them into the inbox, and then
   drains the inbox exactly as `fitdocs sync` would (admitting, writing,
   computing load, reconciling). `--no-prompt` keeps an unattended agent
   from ever blocking on a training-load prompt (it has the same effect
   stdin being a non-terminal already has for an unattended run; pass it
   explicitly rather than relying on that); any document the load pass
   would otherwise have prompted for is simply left uncomputed. With no
   connectors configured, this is exactly `fitdocs sync --no-prompt` --
   there is nothing to fetch, so the inbox drain is the whole of it. Run
   `fitdocs sync --no-prompt --retry-quarantined` instead, only when the
   user has asked you to re-attempt files already recorded as quarantined
   -- never on your own initiative (see Quarantined below). Never run
   `fitdocs connect`: it asks the athlete for secrets at a terminal, and an
   agent must never run it.
2. `fitdocs check` -- confirms the data root still matches the installed
   contract. Run it after a pull-and-drain to confirm the tree is healthy,
   or any time you want to check the tree without draining anything.

```bash
fitdocs pull --sync --no-prompt
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

`fitdocs pull` prints, per configured instance, a counts table headed by
that instance's name and connector id. The row for how many items were
`listed` is a cross-cutting count, not a channel of its own; every listed
item lands in at most one of the channels below -- if the instance's pull
ends in an `error` partway through, the items it had not reached yet land
in none.

| Pull channel | Field | Meaning | Do |
|---------------|-------|---------|----|
| Delivered | `delivered` | A new activity was fetched from the connector and written into the inbox for the drain to admit. | Nothing needed -- the chained `--sync` drain already admitted it; on a plain `fitdocs pull` (no `--sync`), the next `fitdocs sync` will. |
| Would fetch | `would_fetch` | Non-empty only under `--dry-run` -- the routine above never passes it, so expect this empty. | Nothing needed in the routine above. |
| Already held | `held` | The item is already recorded as a final outcome in this instance's ledger, its bytes are already archived, or it is identical to this instance's delivery still waiting in the inbox -- nothing to fetch again. | Nothing needed. |
| Skipped | `skipped` | The item was recognized but not delivered, for a reason the report names (for example, the connector declines an activity, or its original file is unavailable, or the fetched bytes are not a FIT file). | Read the detail; nothing further needed -- it is not retried. |
| Deferred | `deferred` | The item could not be listed or fetched yet for a reason expected to resolve on its own (for example, a rate limit), or -- subject an inbox path rather than a remote id -- an earlier delivery that could not be removed from the inbox yet. | No action -- it is reconsidered automatically on the next pull. |
| Failed | `failed` | The item was listed but fetching it failed for a reason the report names, or the listing entry itself was malformed; the instance's pull continues. | Read the message; report it to the user if it recurs -- it is retried automatically on the next pull. |
| Removed | `removed` | An inbox-relative path, delivered by this instance on an earlier pull and now archived (hash-identical), that this pull's sweep removed from the inbox. Only this instance's own archived deliveries are ever removed -- never a hand-dropped file. | Nothing needed -- routine cleanup. |
| Error | `error` | This instance's pull ended early -- either before fetching anything (no credentials, rejected credentials, a rate-limited sign-in, an unreadable ledger, a permissive credentials file, a failed listing, or a missing source) or partway through (an authentication failure on a fetch; anything already delivered stays delivered). Other instances still ran. | Read the printed next step and report it to the user -- never run `fitdocs connect` yourself (it needs an interactive terminal the agent cannot use), and never retry on your own judgment. |

`fitdocs sync`'s own drain (chained here by `--sync`, or run directly by
`fitdocs sync`) prints an inbox path followed by a counts table with eight
rows, but they are not eight peers of one partition. Every admitted file
lands in exactly one of written / skipped / failed; a file not yet admitted
lands in exactly one of deferred / quarantined instead. Warnings annotate a
file alongside whichever of those it landed in -- never a partition of
their own. Moved and move-failures describe what happened *afterward* to a
file already counted as written or skipped: whether its now-archived source
was also relocated out of the inbox.

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
- [Connectors](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/connectors.md) -- what a connector is, `[connectors.<name>]` keys, `fitdocs connect`/`fitdocs pull`, credentials, and what leaves the machine.
- [Ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md) -- the published detail behind the in-tree declaration.
- [Configuration](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/configuration.md) -- the data-root contract and `fitdocs.toml`.
