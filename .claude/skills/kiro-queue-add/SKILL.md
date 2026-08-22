---
name: kiro-queue-add
description: Record adjacent work surfaced during a session into .kiro/queue/ with enough context for a fresh session to act on it. Use when a session notices an inconsistency, gap, or follow-up it should not fix now.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
argument-hint: "[short description of the follow-up, or omit to sweep this session]"
---

# kiro-queue-add Skill

## Core Mission

Turn "we should deal with that separately" into a queue item a session with
**zero context** can pick up cold. The failure mode is not forgetting to
write the file — it is writing a file so thin that reading it costs more than
rediscovering the problem.

- **Success criteria**:
  - Every item has verifiable evidence, a resume command, and live context paths
  - An agent that never saw this session can start work from the item alone
  - No duplicate of an existing queue item or an open roadmap line

## Execution Steps

### Step 1: Collect Candidates

**With an argument**: that description is the single candidate.

**Without an argument**: sweep this session for work it surfaced but did not
do. Look for things you said or found that match:
- an inconsistency between two specs, or between a spec and the code
- a defect noticed outside the current task's boundary
- a contract, constant, or citation that is wrong or unsourced
- a deferral: "out of scope", "separate session", "handle later"
- a reviewer/validator finding classified `UPSTREAM` or ruled out-of-boundary
- a known limitation accepted by decision, that nobody owns

Discard anything that is: already done, already a `- [ ]` line in
`.kiro/steering/roadmap.md`, already an unchecked task in a spec's `tasks.md`,
or only meaningful inside this conversation.

### Step 2: Deduplicate

- `Glob` `.kiro/queue/*.md` and read the frontmatter of each open item
- `Grep` `.kiro/steering/roadmap.md` for the area and the key symbols
- If a candidate matches an existing item, **update that item** — append to
  `Evidence`, sharpen `How to pick it up`, raise `importance` if this session
  found new consequence — rather than creating a second file
- If a candidate is already an open roadmap line, do not queue it. Say so.

### Step 3: Gather Evidence (mandatory, before writing)

For each surviving candidate, gather evidence that a stranger can check:
- `Grep`/`Read` the exact `file:line` that demonstrates the problem
- `git rev-parse --short HEAD` for `pinned_at`
- Where a claim is behavioral, run the command and quote its real output

Do not write an item whose evidence you have not verified in this run. If the
problem was reported by a subagent and you cannot confirm it, say so in
`Evidence` explicitly ("reported by reviewer subagent, unverified") rather
than presenting it as established.

### Step 4: Write the Item

Write `.kiro/queue/YYYY-MM-DD-<slug>.md` following the format and field table
in `.kiro/queue/README.md` exactly. Use today's date.

Set the fields deliberately:
- `importance` — your honest read, with `importance_why` justifying it in one
  line. Reserve `high` for: wrong or fabricated output reaching a document, a
  contract two specs disagree about, or something whose cost grows with delay.
- `effort` — `S` one sitting, `M` about a day, `L` wants its own spec
- `resume_command` — the exact command a fresh session should run, carrying
  its own item. Prefer a real slash command, and append the queue directive:

  ```
  /kiro-spec-requirements fit-ingest [queue: .kiro/queue/<id>.md] <one-line intent>
  ```

  The feature name stays the first token so existing argument parsing is
  untouched; `[queue: …]` points the receiving skill at this item; the
  trailing line makes the command legible in the ranked list. A bare
  `/kiro-spec-requirements fit-ingest` is **not acceptable** — it regenerates
  the whole spec, and two unrelated items can name it identically. Full
  contract, and the list of skills that honor the directive, in
  `.kiro/queue/README.md`. When no slash command fits, write
  `do: <one-line instruction>`; those are self-describing and need no
  directive. Never leave it empty.
- `context` — repo-relative paths to the **latest** docs holding the reasoning:
  the spec's `design.md`/`requirements.md`, the steering file, the source
  module. Paths, not pasted excerpts.
- `blocked_by` — queue ids or spec names that must land first

Write `How to pick it up` as if for someone who has never seen this repo's
last three months: which file to open first, what to verify, what done means.

### Step 5: Report

List each item written or updated: `id`, `importance`, one-line title, and the
path. Name anything you discarded and why (already tracked, already done,
session-local). Do not claim the queue is now complete — claim only what you
wrote.

## Constraints

- **Never fabricate evidence.** Unverified is stated as unverified.
- **Never duplicate.** Update the existing item or the roadmap owns it.
- **One problem per file.**
- **Do not fix the thing.** This skill records; it does not implement. If the
  fix is genuinely two lines and inside the current task's boundary, do it and
  skip the queue entirely — say that instead.
- **Do not edit `.kiro/steering/roadmap.md`.** The queue is the low-ceremony
  path; promoting an item into the roadmap is a human decision.

## Safety & Fallback

- **`.kiro/queue/` missing**: create it and copy the contract from this
  repo's `.kiro/queue/README.md` if that is also absent.
- **Nothing to queue**: say so plainly and write nothing. An empty sweep is a
  valid outcome and is better than a padded queue.
- **Candidate too vague to evidence**: do not write it. Report it as a loose
  end in your response instead, so the human can decide.
