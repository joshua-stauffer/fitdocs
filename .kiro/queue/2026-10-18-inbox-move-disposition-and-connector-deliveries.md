---
id: 2026-10-18-inbox-move-disposition-and-connector-deliveries
title: Under disposition = "move", the drain may relocate a connector's pending delivery that the next pull expects at its own path
status: open
importance: medium
importance_why: A user who opts into "move" with any connector configured could see deliveries treated as lost and re-fetched every pull, or never swept; the docs promise both behaviours without saying how they combine.
effort: S
kind: gap
area: inbox, connectors, src/fitdocs/inbox.py, src/fitdocs/connectors/pull.py, docs/inbox.md
created: 2026-10-18
surfaced_by: Phase 12 follow-ups, configuring the maintainer's independent inbox (chose "leave" because of this)
pinned_at: 0c4b8b5
resume_command: "do: test a folder or intervals delivery under [inbox] disposition = \"move\" through drain then pull; either exempt connector deliveries from the move or teach the pull's sweep to accept a moved, archived delivery, and document the result in docs/inbox.md [queue: .kiro/queue/2026-10-18-inbox-move-disposition-and-connector-deliveries.md]"
context:
  - docs/inbox.md
  - docs/connectors.md
  - src/fitdocs/inbox.py
  - src/fitdocs/connectors/pull.py
blocked_by: []
---

## What
`docs/inbox.md` says the opt-in `"move"` disposition relocates every
successfully archived file to `processed_dir`. It also says connector
deliveries under `<inbox>/<name>/` are removed by the *next pull* once
archived (the "one carve-out"). `src/fitdocs/inbox.py` has no special case
for connector deliveries (`grep -n -i "deliver\|connector" src/fitdocs/inbox.py`
finds nothing at 0c4b8b5). So under "move" a delivery is probably moved by
the drain before the pull's sweep looks for it at its delivery path.

## Why it matters
The pull recognises its pending deliveries by path and bytes. A delivery that
vanished before being swept has, for intervals wellness, been seen to make the
pull forget those days and re-deliver them (the wellness-pull re-validation's
"lost delivery" run, which used an unarchived file). Whether an archived but
moved delivery loops, is re-fetched, or is accepted is untested.

## Evidence
Code read at 0c4b8b5 (no move/delivery coupling). Behaviour UNVERIFIED: no
test or run combines "move" with a connector. The maintainer's inbox was
configured with "leave" for this reason.

## How to pick it up
Write a drain-then-pull test with "move" and a folder connector delivery,
observe the outcome, decide the rule, then pin and document it.
