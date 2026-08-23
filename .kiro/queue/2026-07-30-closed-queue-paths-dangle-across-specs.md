---
id: 2026-07-30-closed-queue-paths-dangle-across-specs
title: Closing a queue item silently breaks every spec document that cites it, and nine such paths already dangle in fit-ingest alone
status: open
importance: medium
importance_why: A spec's recorded rationale is frequently a pointer to a queue item. Closing the item moves the file, the pointer dies, and the reasoning behind a shipped decision becomes unreachable to the next reader — silently, because nothing validates these paths.
effort: S
kind: gap
area: .kiro/specs/, .kiro/queue/, tests/test_docs_guarantees.py
created: 2026-07-30
surfaced_by: adversarial review of spec/fit-ingest-np-window-criterion (queue-tier1 batch)
pinned_at: c3d2201
resume_command: "do: add a guard that every .kiro/queue/ path cited in .kiro/specs/** resolves to an existing file, then repair the nine dangling fit-ingest paths -- and settle whether closing an item should rewrite its citations or whether specs should cite an id rather than a path [queue: .kiro/queue/2026-07-30-closed-queue-paths-dangle-across-specs.md]"
context:
  - .kiro/specs/fit-ingest/design.md
  - .kiro/specs/fit-ingest/research.md
  - .kiro/specs/fit-ingest/spec.json
  - .kiro/queue/README.md
  - tests/test_docs_guarantees.py
blocked_by: []
---

## What

Spec documents cite queue items by path — `.kiro/queue/YYYY-MM-DD-<slug>.md` —
as the recorded rationale for a decision. When the item is closed it moves to
`.kiro/queue/closed/`, and every citation to it becomes a dangling path.

Nothing validates these paths, so the breakage is silent and permanent.

In `.kiro/specs/fit-ingest/` alone, nine already fail `test -e`:
`design.md:714`, `design.md:1096`, `research.md:438`, `research.md:539`,
`spec.json:22`, `spec.json:31`, `spec.json:33`, `tasks.md:149`, and one more
found during the same review.

## Why it matters

The queue's whole premise (`.kiro/queue/README.md`) is that closed items are
"kept, not deleted, so a reopened question can find the prior reasoning". That
guarantee holds for the *file* and fails for every *pointer to it*.

The consequence is concrete: a session reading a spec finds a decision, follows
the citation for the reasoning behind it, gets nothing, and either re-derives
the decision from scratch or reverses it without knowing why it was made. This
repo has already paid that cost — several queue items exist precisely because a
later session could not find the earlier ruling.

It also compounds with the closing workflow. Closing an item is the *correct*
action, and doing it correctly is what breaks the citations. The mechanism
punishes the right behaviour.

## Evidence

Established by the reviewer on `spec/fit-ingest-np-window-criterion` at
`9004329`. Each of these paths is cited in a spec document and does not resolve:

```
design.md:714      design.md:1096
research.md:438    research.md:539
spec.json:22       spec.json:31      spec.json:33
tasks.md:149
```

Four *more* were self-inflicted in that single commit — `requirements.md:151`,
`research.md:476`, and two in `spec.json:48` — because the commit cited the
items at their open path while simultaneously closing them. That is the pattern
in miniature: the citation and the close land together and contradict each
other on arrival.

`.kiro/queue/README.md` states the retention guarantee that these dangling
paths defeat.

## How to pick it up

1. Decide the shape first, because it determines everything else:
   - **Guard only** — a test asserting every `.kiro/queue/` path cited under
     `.kiro/specs/**` resolves. Cheap, catches future breakage, but the fix at
     each close is manual.
   - **Cite ids, not paths** — specs reference the item `id` and a resolver
     looks in both directories. Survives closing by construction. Needs one
     helper and a convention change in `.kiro/queue/README.md`.
   - **Rewrite on close** — `/kiro-queue close` greps the specs and repoints.
     Keeps paths readable but puts a mutation of spec documents inside a
     bookkeeping command, which the change protocol would treat as non-trivial.
2. Note the existing guard surface: `tests/test_docs_guarantees.py` already
   scans shipped documentation for prose guarantees, so it is the natural home
   for a path-resolution check.
3. Repair the nine (plus the four from that commit, if that branch has landed
   by the time this is picked up).
4. Done looks like: a test that reds when a cited queue path does not resolve,
   and no dangling citation left in `.kiro/specs/`.

## Open questions

- Should the guard cover `.kiro/steering/` too? Steering documents cite queue
  items as well, and the same breakage applies.
- Does this want to extend to the reverse direction — a closed item whose
  `context:` paths no longer exist? `/kiro-queue` already checks context paths
  at ranking time, but only for items it ranks, and only when it runs.
