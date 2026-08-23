---
id: 2026-08-23-tasks-md-says-renamed-where-design-says-nothing-was-renamed
title: tasks.md says the remote was "renamed" with no inexactness caution, while design.md says nothing was renamed — and an executor wrote the false account into the durable record
status: open
importance: medium
importance_why: This is a proven-harmful contradiction, not a latent one: it already produced a false statement in the shipped provenance record, which took three review rounds to find and correct. The wording is still there, and 9.2 is not the last task that will read it.
effort: S
kind: inconsistency
area: encumbered-content-purge
created: 2026-08-23
surfaced_by: /kiro-impl encumbered-content-purge task 9.2 (review round 2 root cause)
pinned_at: c786326
resume_command: "do: carry design.md's nothing-is-renamed caution into tasks.md's task 9.2 and 8.4 bullets, so an executor reading tasks.md alone cannot write a repository rename into the record again"
context:
  - .kiro/specs/encumbered-content-purge/tasks.md
  - .kiro/specs/encumbered-content-purge/design.md
  - docs/reference/history-rewrites.md
blocked_by: []
---

## What

`tasks.md` task 9.2's own bullet instructs the executor to record *"the remote
**renamed** rather than deleted-and-recreated"*, with no caution attached.

`design.md` says the opposite in terms:

> *(Amendment 3 makes that word inexact and it is kept for continuity:
> **nothing is renamed**. A new empty repository stands beside a retained old
> one, permanently. "Rename" describes which URL the project publishes under,
> not what happened to any repository — the same caution applies to task 8.4's
> title.)*

## Why it matters

**This already caused the defect it predicts.** Task 9.2's implementer read
`tasks.md`, took "renamed" at face value, and wrote into
`docs/reference/history-rewrites.md` that `fitdocs_oss` was renamed to
`fitdocs` — and then *invented a justification for it*: that a rename "already
produces a repository at the new name, so recreating one there would have
collided with it." That clause appears in no source.

It was refuted by the record's own evidence: task 8.4 measured **both**
repositories before the push, which is not what a rename looks like. Correcting
it took a full review round across six separate sites in the document.

The irony is sharp and worth preserving: `design.md:105` states that `tasks.md`
is **deliberately excluded** from the read-through-the-amendment carve-out
*"because it is executed rather than read"* — *"A task list that has to be read
through an amendment is a task list that will be executed without one."* That
reasoning is correct, and this bullet is exactly the case it failed to catch.

Req 8.6 is what makes this a correctness issue rather than a style one: it asks
which action was *required* versus *assumed*, and task 9.2's own text warns
that "a record naming a step nobody performed fails it as surely as an
omission."

## Evidence

- `.kiro/specs/encumbered-content-purge/tasks.md`, task 9.2 body: "the remote
  **renamed** rather than deleted-and-recreated *(Amendment 2, 2026-08-22)*" —
  no caution
- `.kiro/specs/encumbered-content-purge/design.md`, Amendment 2 section:
  "nothing is renamed" (quoted above), and the tasks.md-is-executed rationale
- `~/.fitdocs-purge/remote-8-4.txt` measured both repositories pre-push — now
  destroyed at task 9.4, but its content is reproduced in the record's
  section 7
- The corrected account is in `docs/reference/history-rewrites.md` sections 3
  and 7, landed at commit `881e564`

## How to pick it up

Open `tasks.md` and find every bullet in tasks 8.4 and 9.2 using "rename" or
"renamed". Attach `design.md`'s caution inline — one clause is enough: *the
word describes which URL the project publishes under, not an operation
performed on any repository; nothing was renamed.*

Do **not** rewrite the landed record; it is already correct as of `881e564`.
This is about the instruction that produced the error, so the next executor
reading `tasks.md` alone cannot repeat it.

While there, check task 8.4's title for the same word — `design.md` names it
explicitly as carrying the same inexactness.

Done when no bullet in `tasks.md` asserts a rename without its caution.
