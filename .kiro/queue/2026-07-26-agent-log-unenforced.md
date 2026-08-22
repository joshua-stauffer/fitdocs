---
id: 2026-07-26-agent-log-unenforced
title: The shared agent log is the only Development Rule with no hook behind it
status: open
importance: medium
importance_why: The rule was just strengthened precisely because sessions abandon the log mid-run, and the abandonment failure mode is silence — the one thing a guidance-only rule cannot detect, and the one thing a Stop hook can.
effort: S
kind: gap
area: .claude/hooks, .kiro/steering/concurrency.md, CLAUDE.md
created: 2026-07-26
surfaced_by: /kiro-steering making the agent log a first-class session artifact (95bb6a1)
pinned_at: 95bb6a1
resume_command: "do: Add a Stop-hook check (.claude/hooks/log-guard.py, or a branch inside the existing change-guard.py) that nudges when a session committed to a branch or merged to main without appending to $(git rev-parse --git-common-dir)/agent-log. Advisory only — never gate on claims; read .kiro/steering/concurrency.md 'What the log is not' first."
context:
  - .kiro/steering/concurrency.md
  - .kiro/steering/change-protocol.md
  - .claude/hooks/change-guard.py
  - .claude/hooks/queue-guard.py
  - .claude/settings.json
  - CLAUDE.md
blocked_by: []
---

## What

CLAUDE.md's `## Development Rules` now carries three obligations. Two have
executable enforcement behind them; the third does not:

| Rule | Enforcement |
|---|---|
| Every non-trivial change runs the worktree ritual | `.claude/hooks/change-guard.py` (PreToolUse + Stop) |
| Surfaced follow-up work goes in the queue | `.claude/hooks/queue-guard.py` (Stop) |
| The shared agent log is a first-class artifact | **none** |

As of 95bb6a1 the log obligation is stated in four places (CLAUDE.md,
`change-protocol.md` step 0 and Definition of Done item 7, `concurrency.md`
read/write-point tables, `kiro-impl` preflight and per-task steps) and rests
entirely on a session choosing to comply.

## Why it matters

The change that created this asymmetry was made *because* guidance alone was
not holding: sessions that received explicit direction coordinated well, and
sessions that drifted away from the log produced merge conflicts. Strengthening
the prose raises the floor, but it addresses the same lever that had already
proven partially leaky.

The specific failure mode is **silence** — a session stops writing partway
through a long run. Nothing in the transcript looks wrong, no tool call fails,
and peers reading the log see a session that appears to have stopped when it is
in fact still editing shared modules. `concurrency.md` now names this
explicitly under Not Allowed ("an abandoned log is worse than none, because
peers still read it and now believe you stopped"). A Stop hook is the natural
detector: it fires exactly when the session ends, which is exactly when an
unwritten log becomes permanent.

Note the ceiling. A hook can observe silence; it cannot observe *quality*, and
the highest-value entries are `WARN`/`NOTE` lines whose value is entirely in
their content. This buys the floor, not the ceiling.

## Evidence

Hooks present, and what they cover — `ls .claude/hooks/` at 95bb6a1:

```
change-guard.py
queue-guard.py
```

Wiring, from `.claude/settings.json`:

```
PreToolUse: change-guard.py
Stop:       queue-guard.py
Stop:       change-guard.py
```

Neither hook knows the log exists:

```
$ grep -rln "agent-log" .claude/hooks/
(no matches)
```

The obligation it would enforce, for contrast — `CLAUDE.md:85`, added in
95bb6a1: *"The shared agent log is a first-class artifact of every session —
read it before you start, write it as you go."*

The live log itself is the behavioral evidence that the artifact is real and
load-bearing — 47 lines across five session ids when this item was written, and
still growing, since peers appended during the writing of it:

```
$ cut -f2 "$(git rev-parse --git-common-dir)/agent-log" | sort -u
impl-athlete-benchmarks
impl-load-channels
impl-training-load
queue-resume
steering-log-protocol
```

It carries cross-session saves that no other channel did — `impl-training-load`
warning that `contract.document_date` had landed on its branch so
`athlete-benchmarks` would consume it rather than add a second. Note the log is
in `.git/`, so it is never committed and a picking-up session will see a
different, longer file than these numbers describe.

## How to pick it up

1. Read `.kiro/steering/concurrency.md`, specifically **"What the log is not"**
   — this is the binding constraint on the whole item. The log is explicitly
   *not* a lock; claims have a race window by design. A hook that blocks a
   session because a peer holds a `CLAIM` would convert an advisory artifact
   into a lock and contradict the steering doc. Nudge on **silence**, never
   gate on **claims**.
2. Read `.claude/hooks/queue-guard.py` — it is the closest precedent: a Stop
   hook that blocks once on a missing artifact, with an escape. Decide whether
   this is a third hook (`log-guard.py`) or a branch inside `change-guard.py`,
   which already resolves the tree, the branch, and `main`-vs-worktree state
   the check needs.
3. Candidate condition, to sharpen rather than adopt as written: at Stop, if
   the session committed to a branch or merged to `main`, and appended nothing
   to `$(git rev-parse --git-common-dir)/agent-log` during the session, block
   once with the `printf` line pre-filled. Decide how the hook establishes
   "during the session" — the log has no session-scoped marker, so this likely
   needs a byte-offset or line-count baseline captured at first invocation.
4. Validation is the `.claude/hooks/**` class in `change-protocol.md`: a
   synthetic payload through **every** branch, at least one that fires and one
   that passes, with output shown. Hooks fail silent, so only execution proves
   them.

Done means: a session that ends with commits on a branch and no log line gets
exactly one nudge naming the command to fix it; a session that logged normally
sees nothing; and no path through the hook blocks a session on account of a
*peer's* claim.

## Open questions

- Third hook or a branch in `change-guard.py`? The state it needs is already
  computed there, but that file is the change-protocol enforcer and mixing
  coordination into it may blur which rule a block belongs to.
- Should the nudge be blocking (like `queue-guard.py`) or advisory-only output?
  Blocking matches the other two rules; advisory matches the log's explicitly
  non-authoritative status. This is a judgment call the picking-up session
  should put to the human rather than settle alone.
