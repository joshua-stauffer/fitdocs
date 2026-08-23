# Follow-up Queue

Sessions constantly surface work they should not do: an inconsistency noticed
while implementing something else, a contract that two specs read differently,
a coefficient with a bad citation, a test that only passes by accident. That
work is real, it is not in `tasks.md`, and it evaporates when the session ends.

This directory is where it lands instead.

## Contract

- One file per item: `.kiro/queue/YYYY-MM-DD-<slug>.md`. The filename stem is
  the item `id`.
- Open items live here. Closed ones move to `.kiro/queue/closed/` with their
  `status` updated — they are kept, not deleted, so a reopened question can
  find the prior reasoning.
- Items are written by `/kiro-queue-add` and ranked by `/kiro-queue`. Both are
  fine to write by hand; the format is the interface, not the skill.
- **This queue is not the roadmap.** `.kiro/steering/roadmap.md` owns planned
  spec work. The queue owns unplanned work that a session tripped over. If an
  item grows into a spec, close it with `status: promoted` and a pointer to the
  spec. Never copy a roadmap line into the queue — `/kiro-queue` already reads
  the roadmap's open `Existing Spec Updates` and `Direct Implementation
  Candidates` and ranks them alongside queue items.

## Item format

```markdown
---
id: 2026-07-25-trimp-coefficients
title: Re-source the Banister TRIMP coefficients from primary literature
status: open
importance: high
importance_why: Changes every rendered doc's trimp value; cost grows per doc.
effort: S
kind: inconsistency
area: fit-ingest, src/fitdocs/metrics/stress.py
created: 2026-07-25
surfaced_by: /kiro-validate-impl training-load
pinned_at: c3d2201
resume_command: "/kiro-spec-requirements fit-ingest [queue: .kiro/queue/2026-07-25-trimp-coefficients.md] Re-source the Banister TRIMP coefficients from primary literature"
context:
  - .kiro/specs/fit-ingest/design.md
  - src/fitdocs/metrics/stress.py
blocked_by: []
---

## What
<The gap, in one paragraph. What is inconsistent, missing, or wrong.>

## Why it matters
<Consequence if nobody does this. Concrete, not "it would be nice".>

## Evidence
<file:line, commit SHA, command + output. Verifiable, not remembered.>

## How to pick it up
<The first three moves for a session with zero context. Which files to read
first, what to check, what "done" looks like.>

## Open questions
<Decisions the picking-up session cannot make alone. Omit if none.>
```

### Fields

| Field | Values | Notes |
|---|---|---|
| `id` | `YYYY-MM-DD-<slug>` | Matches the filename stem |
| `status` | `open` `blocked` `done` `dropped` `promoted` | Non-`open` lives in `closed/` |
| `importance` | `high` `medium` `low` | The surfacing session's read — advisory |
| `importance_why` | one line | Required. Justifies the `importance` value |
| `effort` | `S` `M` `L` | S: one sitting. M: a day. L: wants a spec |
| `kind` | `bug` `inconsistency` `gap` `chore` `research` `docs` `spec-work` | |
| `area` | spec name and/or paths | Comma-separated |
| `surfaced_by` | command or short phrase | What was running when this was noticed |
| `pinned_at` | short commit SHA | HEAD when the evidence was gathered, or the epoch value below |
| `resume_command` | slash command + queue directive, or `do: <instruction>` | Never empty. See below |
| `context` | list of repo-relative paths | Live paths — always resolve to latest |
| `blocked_by` | list of queue ids / spec names | `[]` when unblocked |

### The epoch pin convention (history replacement, 2026-08-22)

This repository's history was replaced on 2026-08-22 (`docs/reference/history-rewrites.md`):
a fresh root commit, `c3d2201` (short form), now carries the certified tree,
and no pre-replacement commit identifier resolves against it or ever will —
there is no mapping by construction. Every **open** item whose `pinned_at`
was gathered before that date has its field set to `c3d2201`, the
replacement root's short commit id, applied uniformly with no per-item
judgement (`scripts/purge/pins.py`).

**This is a documented epoch marker, not a substitution.** A pin equal to
`c3d2201` means the item's evidence predates the replacement and its
original pin is permanently unresolvable — never a claim that `c3d2201` is
that original pin's post-replacement counterpart. `/kiro-queue`'s `git log
--oneline <pinned_at>..HEAD` still resolves against it, which is the
property the convention exists to preserve.

**Closed items are untouched.** Their pins recorded what was true when the
evidence was gathered and `closed/` is out of `/kiro-queue`'s ranking scope,
so rewriting them would falsify the record for no consumer. A closed item's
`pinned_at` may therefore still name a pre-replacement identifier, and that
identifier is permanently unresolvable.

### Resume commands

A bare slash command is not enough. `/kiro-spec-requirements fit-ingest`
regenerates the whole spec; it says nothing about *which* follow-up prompted
the run, and two unrelated items can name the identical command. The command
must carry its own item.

```
/kiro-spec-requirements fit-ingest [queue: .kiro/queue/2026-07-25-trimp-coefficients.md] Re-source the Banister TRIMP coefficients from primary literature
```

Three parts, in this order:

1. **The command and its normal arguments.** The feature name stays the first
   token, so every skill's existing argument parsing is untouched.
2. **`[queue: <path>]`** — the machine-readable pointer. The receiving skill
   reads that file and gets `Evidence`, `How to pick it up`, and the
   `context` paths without the invoking session having to restate them.
3. **The one-line intent**, so the command is legible to a human scanning the
   ranked list without opening the item.

`do:` items need no directive — they carry their instruction inline and are
already self-describing.

Skills that honor the directive: `kiro-spec-requirements`, `kiro-spec-design`,
`kiro-spec-tasks`, `kiro-impl`, `kiro-discovery`. Naming any other command is
allowed, but the trailing directive will be read by a human rather than acted
on automatically — and a skill that interpolates `$ARGUMENTS` straight into a
path will break on it, so check before choosing one.

### Rules

1. **Evidence must be verifiable.** `file:line`, a commit, a command and its
   output. An item that cannot be checked cannot be ranked, and a reader with
   no memory of the session cannot act on it.
2. **Absent information is stated as unknown**, never invented — the same rule
   the code follows for missing data (`None`, never a fabricated `0`).
3. **`context` holds live repo paths, not pasted content.** Paths track the
   latest version by construction; `pinned_at` records what the evidence was
   read against, so a reader can diff the delta.
4. **Write for a session with no context.** If `How to pick it up` needs this
   session's conversation to make sense, it is not finished.
5. **One item per file, one problem per item.** Two problems that happen to
   share a file are two items.
