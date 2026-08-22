---
name: kiro-queue
description: Produce a freshly ranked list of open follow-up work from .kiro/queue/ and the roadmap's open items, each with the command to pick it up. Also closes and drops items. Use to decide what to work on next.
allowed-tools: Read, Glob, Grep, Bash, Edit, Write
argument-hint: "[ | close <id> [reason] | drop <id> <reason> | <focus area>]"
---

# kiro-queue Skill

## Core Mission

Answer one question: **what should I pick up next, and how do I start it?**

The ranking is produced fresh each run by reading every open item together —
not by sorting the `importance` field. An item's stored `importance` was one
session's local read; ranking is a global judgment about what the whole list
looks like today, against the repo as it actually is now.

- **Success criteria**:
  - Every ranked entry carries a runnable resume command and live context paths
  - Items already resolved by later commits are caught, not ranked
  - The ordering is justified in one line each, so it can be argued with

## Modes

| Invocation | Behavior |
|---|---|
| `/kiro-queue` | Rank everything open |
| `/kiro-queue <focus>` | Rank everything, then flag which items touch `<focus>` |
| `/kiro-queue close <id> [reason]` | Step 5 |
| `/kiro-queue drop <id> <reason>` | Step 5 |

## Execution Steps

### Step 1: Load the Full List

Read all of it before ranking any of it. The point of this skill is that the
list is judged whole.

- `Glob` `.kiro/queue/*.md` → read every open item in full (frontmatter + body)
- Read `.kiro/steering/roadmap.md` → collect **open** `- [ ]` lines under
  `Existing Spec Updates` and `Direct Implementation Candidates`. These are
  surfaced follow-ups that predate the queue; rank them alongside queue items
  and mark them `roadmap-owned`. Do not copy them into `.kiro/queue/`.
- Read `.kiro/steering/product.md` and `tech.md` for the standing priorities
- For each spec named in any item's `area` or `blocked_by`: read its
  `spec.json` `phase` and count `- [x]`/`- [ ]` in `tasks.md`, so "blocked by
  spec X" resolves to a real state rather than an assumption
- `git log --oneline -20` for what has moved recently
- `cat "$(git rev-parse --git-common-dir)/agent-log"` — a peer may be mid-`CLAIM`
  on the same item id this run is about to rank, resume, or close. This run
  itself does not hold a claim just by ranking (ranking only reads), but the
  read still matters: a `possibly resolved` verdict in Step 2 is stronger
  evidence when a peer's `MERGED` line explains why, and a `Resume:` printed
  in Step 4 for an item a peer already holds sends the next session into a
  collision this list could have prevented

### Step 2: Verify Each Item Still Applies

An unverified queue is a queue of ghosts. Before ranking, check each item
cheaply against the repo as it stands:

- Read the `file:line` in `Evidence` — does the problem still exist there?
- `Grep` for the symbol, constant, or string the item is about
- `git log --oneline <pinned_at>..HEAD -- <context paths>` — what landed in
  this area since the evidence was gathered?

Classify each: **stands** / **possibly resolved** / **cannot verify**.
Rank only what stands. Never auto-close: a `possibly resolved` item goes in
its own section for the human to confirm, with the evidence that suggests it
is done.

### Step 3: Rank

Weigh these against each other. They are listed in priority order, but a
strong signal low on the list can outrank a weak one above it — say so when it
does.

1. **Output integrity.** Anything that puts a wrong, fabricated, or
   silently-defaulted value into a rendered document outranks everything else.
   This is the project's hard rule (`CLAUDE.md`, `tech.md`): absent data is
   `None`, never a fabricated `0`.
2. **Contract disagreement.** Two specs or a spec and the code reading the
   same surface differently. These get more expensive with every spec that
   builds on the wrong reading.
3. **Blocking.** How many queue items, specs, or roadmap lines are gated on
   this one. Resolve `blocked_by` transitively; an item whose blocker is
   unlanded is not rankable — it goes in **Blocked**.
4. **Decay cost.** Does waiting make it harder? Anything that changes already
   rendered output grows by every document written in the meantime
   (migration-by-regen scope). Anything touching an in-flight spec is cheapest
   before that spec's tasks land.
5. **Effort against value.** An `S` that unblocks an `L` goes first.
6. **Staleness.** An item open a long time is either more urgent than its
   `importance` claims or should be dropped. Say which.

Where your ranking contradicts an item's stored `importance`, say so and why —
that disagreement is information.

### Step 4: Report

```md
## Queue — ranked <date>   (<N> open · <M> blocked · <K> to confirm)

### Pick up next

1. **<title>**  ·  <kind> · effort <S|M|L> · <area>
   Why now: <one line — the ranking argument, not a restatement of the title>
   Resume:  <resume_command>
   Context: <path> · <path>
   Item:    .kiro/queue/<id>.md
   <optional: "Stored importance: medium — ranked higher because …">

2. …

### Blocked
- **<title>** — waiting on <blocker> (<its real state from Step 1>)

### Likely resolved — confirm and close
- **<title>** — <what landed>: <commit/file evidence>. Close with
  `/kiro-queue close <id>`

### Roadmap-owned (ranked, but tracked in roadmap.md)
- **<title>** — <one line> · Resume: <command> · roadmap.md:<line>

### Could not verify
- **<title>** — <what could not be checked and why>
```

Rules for the report:
- Keep it scannable. One line of reasoning per item, not a paragraph.
- Every `Resume:` must be runnable as written, **including its
  `[queue: <path>]` directive and trailing intent** — that is what tells the
  receiving session which item it is picking up. Never print the command
  stripped back to `/<skill> <feature>`. If the item stored `do: …`, print the
  instruction verbatim.
- If an item's stored `resume_command` is a bare slash command with no
  directive, print it with the directive supplied (`[queue: .kiro/queue/<id>.md]`
  plus the item's title) and flag the item as needing that field repaired.
- Every `Context:` path must exist — check before printing. A dead path in the
  report is worse than no path.
- If the queue is empty and the roadmap has no open follow-ups, say exactly
  that. Do not invent work to fill the list.

### Step 5: Close / Drop

Two sessions can pick the same item off a freshly ranked list at once; a
`CLAIM` is the cheapest prevention there is. Before step 1 below, re-check the
log read from Step 1 (or re-read it if this invocation started fresh) for a
live `CLAIM` naming this `<id>` — if a peer holds one, do not close over
their in-flight work: stop and report, unless the claiming session itself
already closed it (`MERGED`/`RELEASE`) or the maintainer has confirmed that
session is gone, in which case take it. Claim staleness is defined once, in
`.kiro/steering/concurrency.md` § Stale claims — no skill in this repo
carries a local heuristic for it. (This skill carried one before that section
existed; see
`.kiro/queue/2026-07-27-stale-claim-recovery-undefined.md` for that history.)
Either way, claim the item yourself before proceeding:

```bash
LOG="$(git rev-parse --git-common-dir)/agent-log"
printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "queue-close" CLAIM "<id> (verifying before close/drop)" >> "$LOG"
```

`/kiro-queue close <id> [reason]`:
1. Verify it is actually done — read the code or run the test. Do not close on
   assertion. **If you cannot verify, say so, leave it open, and release the
   claim you just took** (below) — a claim without a resolution is exactly the
   case a `RELEASE` exists for; leaving it live turns the log into a lock on
   an item nobody is actually working, contradicting concurrency.md.
2. Set `status: done` (or `promoted` with the spec name), append a
   `## Resolution` section with the evidence and date
3. `git mv`/move the file to `.kiro/queue/closed/`

`/kiro-queue drop <id> <reason>`: same, with `status: dropped` and the reason
recorded in `## Resolution`. A reason is required — a dropped item with no
reason will be rediscovered and requeued by the next session.

A `close`/`drop` that succeeds is the item's own resolution, not open
coordination-relevant work — `RELEASE` is unnecessary once the file itself
records `status: done` / `status: dropped` in `.kiro/queue/closed/`, which is
legible to any later reader without a log line. A verification attempt that
does **not** succeed (step 1 above) is the one path where the claim must still
be released explicitly, since the item stays open and nothing else retires it:
```bash
LOG="$(git rev-parse --git-common-dir)/agent-log"
printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "queue-close" RELEASE "<id> left open — could not verify (<why>)" >> "$LOG"
```

## Constraints

- **Rank the whole list, every time.** No cached ordering, no sorting by the
  stored `importance` field.
- **Verify before ranking.** An item that no longer reproduces is not a
  priority, it is noise.
- **Never auto-close.** Closing is the human's call; this skill proposes.
- **Never edit `.kiro/steering/roadmap.md`.** Roadmap items are read and
  ranked, not moved or rewritten.
- **Do not start the work.** This skill hands over; it does not implement.

## Safety & Fallback

- **`.kiro/queue/` missing or empty**: report the roadmap-owned items alone
  and note the queue is empty. Do not create placeholder items.
- **Malformed item** (missing frontmatter, unparseable): rank it last under
  **Could not verify**, name the missing fields, and suggest the fix.
- **`<id>` not found on close/drop**: list the open ids and stop.
