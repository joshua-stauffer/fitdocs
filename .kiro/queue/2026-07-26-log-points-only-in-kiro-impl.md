---
id: 2026-07-26-log-points-only-in-kiro-impl
title: Only kiro-impl carries the log read/write points; the other session-level skills do not
status: open
importance: medium
importance_why: kiro-spec-batch dispatches parallel subagents by dependency wave and is the one skill that manufactures concurrency, yet it is the least likely to log — a session entering through it inherits none of the coordination kiro-impl now has.
effort: S
kind: gap
area: .claude/skills/kiro-spec-batch, .claude/skills/kiro-validate-impl, .claude/skills/kiro-queue, .kiro/steering/concurrency.md
created: 2026-07-26
surfaced_by: /kiro-steering making the agent log a first-class session artifact (95bb6a1)
pinned_at: c3d2201
resume_command: "do: Add the shared-log read/write points to the session-level kiro skills that lack them — start with kiro-spec-batch (parallel wave dispatch), then kiro-validate-impl and kiro-queue. Mirror the preflight read+claim and merge-back MERGED/RELEASE pattern already in .claude/skills/kiro-impl/SKILL.md; contract in .kiro/steering/concurrency.md."
context:
  - .kiro/steering/concurrency.md
  - .claude/skills/kiro-impl/SKILL.md
  - .claude/skills/kiro-spec-batch/SKILL.md
  - .claude/skills/kiro-validate-impl/SKILL.md
  - .claude/skills/kiro-queue/SKILL.md
blocked_by: []
---

## What

95bb6a1 made the shared agent log a first-class artifact of every session and
wired the concrete read/write points into `kiro-impl` — preflight read + claim,
choke-point identification, `TOUCHING` before a shared-module task,
`TASK-DONE`/`WARN` in Record Learnings, `MERGED`/`RELEASE` at merge-back.

`kiro-impl` is not the only way a session starts. `kiro-spec-batch`,
`kiro-validate-impl` and `kiro-queue` are all session-level entry points that
can run while a peer is implementing, and none of them mentions the log. A
session entering through one of those reaches the obligation only via
CLAUDE.md and `change-protocol.md` — real, but generic, with no guidance on
what its *own* write points are.

`kiro-spec-batch` is the sharpest case: it creates specs in parallel by
dependency wave, so it is the one skill that manufactures concurrency rather
than merely coexisting with it.

## Why it matters

The steering change works by putting the obligation where a session already
looks. That is why `kiro-impl` got explicit write points rather than a pointer.
The other entry points still have only the pointer, which is the weaker form
the change was made to move away from.

Concretely, each gap has a distinct cost:

- **`kiro-spec-batch`** — parallel subagents writing spec files, with no claim
  recorded. A peer running `/kiro-impl` reads the log, sees no claim, and can
  reasonably conclude a spec is unowned while batch is actively rewriting its
  `tasks.md`.
- **`kiro-validate-impl`** — runs the full suite and reports GO/NO-GO. A
  failure caused by a peer's landed work is exactly the "fails in a way your
  own diff does not explain" read point `concurrency.md` now names, and the
  skill never tells the session to look.
- **`kiro-queue`** — ranks and closes items. Two sessions can pick up the same
  item; a `CLAIM` is the cheapest prevention.

## Evidence

Skills referencing the log at 95bb6a1 — one, out of nineteen:

```
$ grep -rln "agent-log" .claude/skills/
.claude/skills/kiro-impl/SKILL.md
```

Full skill inventory at the same commit (`ls .claude/skills/`):

```
kiro-debug kiro-discovery kiro-impl kiro-queue kiro-queue-add kiro-review
kiro-spec-batch kiro-spec-design kiro-spec-init kiro-spec-quick
kiro-spec-requirements kiro-spec-status kiro-spec-tasks kiro-steering
kiro-steering-custom kiro-validate-design kiro-validate-gap
kiro-validate-impl kiro-verify-completion
```

The obligation those skills are subject to but do not implement —
`.kiro/steering/concurrency.md` at 95bb6a1, "Read points" and "Write points"
tables, plus: *"A session that believes it is solo still writes."*

## How to pick it up

1. Open `.claude/skills/kiro-impl/SKILL.md` and read the four edited regions —
   Preflight ("Read the shared log, then claim the spec" + "Identify choke
   points"), step **a** (`TOUCHING`), step **f** (`TASK-DONE`/`WARN`), and the
   "Both modes — merge-back and the log" block in Step 4. That is the pattern
   to mirror, not to copy verbatim.
2. Triage the nineteen skills first — most should get **nothing**. The test is
   whether the skill is a *session-level entry point* that can hold work while
   a peer runs. Subagent-protocol skills (`kiro-review`, `kiro-debug`,
   `kiro-verify-completion`) explicitly should not log: `concurrency.md` states
   the parent session owns reading and writing on the subagent's behalf, and
   giving subagents a write path would contradict it.
3. Do `kiro-spec-batch` first and most carefully — it is the only one that
   creates concurrency itself. The interesting question there is granularity:
   one claim for the batch run, or one per wave? A batch that claims every spec
   up front blocks peers from all of them for the batch's whole duration, which
   may be worse than not claiming at all.
4. Validation is the `.claude/skills/**` class in `change-protocol.md`: the
   skill exercised once end to end on a real target, or an explicit statement
   of why it cannot be run and what was inspected instead.

Done means: every skill that can start a session and hold work tells that
session when to read the log and what to write, and skills that should stay
silent are silent deliberately rather than by omission.

## Open questions

- `kiro-spec-batch` claim granularity (per-run vs per-wave vs per-spec) — see
  step 3. This determines whether batch is a good log citizen or a peer-starver.
- Should `concurrency.md` name the entry-point skills that owe log points, so a
  future skill is written with it rather than retrofitted? That risks the
  catalog-not-pattern failure `rules/steering-principles.md` warns against.
