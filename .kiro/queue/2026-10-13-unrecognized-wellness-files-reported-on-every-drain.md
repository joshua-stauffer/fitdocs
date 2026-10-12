---
id: 2026-10-13-unrecognized-wellness-files-reported-on-every-drain
title: "An unrecognized wellness-suffix file under the default leave-in-place inbox is re-probed and re-reported on every drain, with no record that would quiet it"
status: open
importance: low
importance_why: The cost is repeated noise plus a re-probe per drain, and the design already documents how to silence a file; nothing is lost or mis-filed.
effort: S
kind: gap
area: wellness-store, src/fitdocs/inbox.py, src/fitdocs/sync.py
created: 2026-10-13
surfaced_by: /kiro-spec-batch phase 12 (wellness-store spec, controller queue triage)
pinned_at: 86cdf14
resume_command: "do: once wellness-store has landed, decide whether an unrecognized wellness candidate should get a quiet record (a keyed-by-content entry that is reported once and then counted, as quarantine does for failures) or whether the documented [inbox] ignore pattern is the whole answer, and record the decision in docs/inbox.md [queue: .kiro/queue/2026-10-13-unrecognized-wellness-files-reported-on-every-drain.md]"
context:
  - .kiro/specs/wellness-store/design.md
  - .kiro/specs/wellness-store/requirements.md
  - src/fitdocs/inbox.py
  - src/fitdocs/quarantine.py
  - docs/inbox.md
blocked_by: [wellness-store]
---

## What

wellness-store makes every inbox file whose extension a registered wellness
format reads (today only `.json`) a candidate. A candidate no format claims
(or that several claim) is reported in a new "Unrecognized" channel and left
untouched (Req 1.4, 1.5). Under the default disposition, leave-in-place, a
handled file is skipped on later drains only because "its content is already
archived; the archive copy is the processed marker". An unrecognized file has
no archive copy and no quarantine entry, so every drain probes it again and
lists it again, indefinitely. Unlike a quarantined file, nothing records that
it was seen. The design accepts this and documents `[inbox] ignore` as the
silencer; this item records that the choice is open to revisit once a real
inbox shows how common stray `.json` files are.

## Why it matters

An inbox that also receives unrelated `.json` files (exports from other tools)
gets the same "Unrecognized" row on every `fitdocs sync`, which trains the
athlete to ignore the row that would one day name a real unreadable wellness
export. Each drain also re-reads the file (a head read, and a whole-file JSON
parse for a `.json` up to the 64 MiB probe limit).

## Evidence

Read at `86cdf14`.

- `src/fitdocs/inbox.py:100-104` -- leave-in-place "is a no-op by
  construction ... Re-drains skip it because its content is already archived;
  the archive copy is the processed marker, so no disposition-specific state
  is invented". The default is `Disposition.LEAVE` (`:198-203`).
- `.kiro/specs/wellness-store/design.md:540-544` -- `recognize`: none or
  several claimants give `Unrecognized`; `:1724` -- "No format / several
  formats | identify | `unrecognized`, left in place | exit 0".
- `.kiro/specs/wellness-store/design.md:1260` -- `DrainReport.unrecognized`
  (a plain tuple of notes, no persistent state); `:1325-1328` -- the
  `Unrecognized` row is rendered unconditionally.
- `.kiro/specs/wellness-store/requirements.md:125-126` -- Req 1.4 and 1.5
  (unrecognized and ambiguous files are left untouched and reported) and
  `:127` -- Req 1.6 (other extensions are ignored silently).
- `.kiro/specs/wellness-store/design.md:1373-1374` -- `docs/inbox.md` will
  describe "silencing a file with `[inbox] ignore`".
- Contrast: Req 2.6 (`requirements.md:143`) records a candidate that is
  recognized but invalid in the quarantine record, so later drains report it
  "as quarantined without parsing it again".

## How to pick it up

1. Land wellness-store first, then run a drain over an inbox holding one
   stray `.json` twice and confirm the second drain lists it again.
2. Read `src/fitdocs/quarantine.py` and the quarantine handling in
   `src/fitdocs/sync.py` to see what a content-keyed record would cost and
   what `--retry-quarantined` would then mean for it.
3. Decide, then either extend the record or write the decision into
   `docs/inbox.md` beside the silencing instructions.

## Open questions

- Is a stray `.json` common enough to justify state? A record keyed by
  content hash would force a full hash per drain for every stray file, which
  the leave-in-place design avoids for recognized files only because their
  archive entry short-circuits it.
