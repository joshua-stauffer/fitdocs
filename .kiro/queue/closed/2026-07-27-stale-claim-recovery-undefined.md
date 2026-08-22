---
id: 2026-07-27-stale-claim-recovery-undefined
title: A CLAIM in the shared log has no expiry, so a dead session blocks an item forever
status: done
importance: medium
importance_why: Three skills now instruct sessions not to take claimed work, and none defines when a claim goes stale. A session that dies mid-run leaves work permanently untakeable — which turns the log into the lock concurrency.md says it must never be.
effort: S
kind: gap
area: .kiro/steering/concurrency.md, .claude/skills/
created: 2026-07-27
surfaced_by: adversarial review of chore/agent-log-enforcement (queue sweep 2026-07-27)
pinned_at: 80cc5c5
resume_command: "do: define stale-claim recovery in .kiro/steering/concurrency.md — when a CLAIM expires, how a session confirms the claimant is gone, and what it may then do — and reconcile the three skills that tell sessions not to take claimed work (kiro-impl/SKILL.md:48, kiro-queue/SKILL.md:150, kiro-spec-batch/SKILL.md:89) against it [queue: .kiro/queue/2026-07-27-stale-claim-recovery-undefined.md]"
context:
  - .kiro/steering/concurrency.md
  - .claude/skills/kiro-impl/SKILL.md
  - .claude/skills/kiro-queue/SKILL.md
  - .claude/skills/kiro-spec-batch/SKILL.md
blocked_by: []
---

## What

`concurrency.md` is explicit that the shared log is **not a lock** and that
correctness guarantees must not be built on it. But three skills now instruct a
session not to take work another session has claimed, and nothing anywhere
defines when a claim expires or how a session establishes that a claimant is
gone:

- `.claude/skills/kiro-impl/SKILL.md:48` — "if one is held, do not take it"
- `.claude/skills/kiro-queue/SKILL.md:150` — "stop and report it rather than
  closing"
- `.claude/skills/kiro-spec-batch/SKILL.md:89` — per-wave RELEASE lives inside
  the wave-completion checklist

In each case a session that crashes, is interrupted, or simply ends without
reaching its RELEASE leaves a live claim behind. The next session reads
"claimed", declines to take it, and the work is untakeable by construction.
There is no staleness test in any of the three.

## Why it matters

This is the failure mode `concurrency.md` explicitly writes the log's design
against. Without an expiry rule the advisory convention hardens into a real
lock with no unlock path — and the cost lands exactly on the multi-session
runs the log exists to coordinate. A session that dies mid-wave in
`kiro-spec-batch` can strand a whole dependency wave.

Partly pre-existing: the shape is already in `kiro-impl` and predates the
`chore/agent-log-enforcement` work. That branch propagated it to two more
skills, which is what made it worth writing down.

## Evidence

Identified by the adversarial reviewer of `chore/agent-log-enforcement`
(2026-07-27), finding F4 and follow-up 1. The three cited skill lines were read
directly. `concurrency.md`'s "What the log is not" section states the
constraint the current text contradicts.

Concrete case the reviewer traced through `kiro-queue`: `SKILL.md:148-154`
writes `CLAIM <id>` **before** verification; `:159` says "if you cannot verify,
say so and leave it open"; `:167-170` then declares RELEASE unnecessary "once
the file itself records `status: done` / `status: dropped`" — which is exactly
the case that did not happen on the leave-it-open path. The item stays open
carrying a never-released claim.

## Addendum 2026-07-27 (debug escalation, `chore/agent-log-enforcement`)

Two things changed since this item was written; neither closes it.

**1. `kiro-queue` no longer miscites steering (resolved).** `SKILL.md:150-155`
attributed a specific staleness definition to `concurrency.md`. It is not
there — `grep -in stale .kiro/steering/concurrency.md` returns one hit, line
143, about a *paused session's picture of the repo*, unrelated. The definition
was invented in the skill. It is now marked explicitly as the skill's own
working heuristic, citing `concurrency.md` only for what it does say (the log
is not a lock) and pointing here for the real fix. **The ask below is
unchanged**: the heuristic still needs to become a steering rule, and the three
skills still need reconciling in one change.

**2. The three skills have drifted further apart, not closer.** As of
`chore/agent-log-enforcement` the branch narrows the lock in one skill and
newly creates one in another:

| Skill | What it now says | Staleness escape? |
|---|---|---|
| `kiro-impl/SKILL.md:48` | "if one is held, do not take it" | none — flat prohibition |
| `kiro-queue/SKILL.md:150` | "if a peer holds one **and it is not stale**" | yes, local heuristic |
| `kiro-spec-batch/SKILL.md:22` | "if one is **live**, drop that feature from this run" | "live" undefined |

`kiro-spec-batch`'s rule is the new one and the sharpest: it is a *lock the
branch created*, on the one skill that "manufactures concurrency rather than
merely coexisting with it" (its own words), and it can strand a whole
dependency wave. "Live" is undefined there, so a session must either read it
as `kiro-impl`'s flat prohibition or import `kiro-queue`'s heuristic — and
nothing tells it which. Whatever expiry rule lands must define "live" once and
be cited identically by all three.

## How to pick it up

1. Read `.kiro/steering/concurrency.md` in full, especially "What the log is
   not" — the fix must not smuggle a lock in through the expiry rule either.
2. Decide the expiry rule. A wall-clock TTL is the obvious candidate; an
   alternative is "a claim whose session has no log line since <window> may be
   taken, with a note recorded". Whatever it is, it must be checkable from the
   log alone, since a peer session is invisible from inside another worktree.
3. Reconcile all three skills against it in the same change — every copy of a
   rule moves together, per change-protocol.md's steering validation row.

Done looks like: a session reading a claim it believes is stale has an
explicit, recorded procedure, and no path leaves work permanently untakeable.

## Resolution

Closed 2026-07-29, merged to `main` as `212d046` (branch
`chore/claim-recovery-and-prose-grep`, `--ff-only`, validated after rebase:
2092 passed, all gates clean, steering residue sweep clean).
**Resolved by a maintainer ruling, after two mechanical rules were tried and
rejected.**

**Root cause (debug subagent, 2026-07-29)**: the rule tried to decide a
hidden variable — is the claiming session's process still running — from
signals that are not a function of it. Worktree/branch absence conflates
*not yet created* (the `CLAIM` is written before `git worktree add`, per
`change-protocol.md`'s own lifecycle), *torn down after a successful MERGED*
(that lifecycle's final step), and *died*. A clean `git status` is the
baseline of any session between commits. "No commit since the CLAIM" is the
state of a session in review. "A later line naming the target" is written by
peers — 15 distinct session ids name `fit-ingest` in the log, 14 not its
claimant. **No Boolean combination of non-injective signals is injective.**

Round 0 composed them conjunctively → every ambiguity became a false
negative, a permanent lock. Round 1 went disjunctive → the same ambiguity
became a false positive, overriding live claims. Both rounds were competent;
a third would fail in a third direction.

**The approved rule** (`.kiro/steering/concurrency.md` § Stale claims):
1. A `CLAIM` is closed **only** by a `MERGED` or `RELEASE` from the claiming
   session naming the same target. One grep, no window.
2. An unclosed claim is **never** inferred stale from git or log state. The
   observables are context, never a verdict; no skill may carry a local
   heuristic. The preamble enumerates what each one conflates, so a future
   round cannot re-derive an inference rule from one of them.
3. An unclosed claim you want is a **maintainer question, not a timer** —
   present the evidence, ask, record an `OVERRIDE` with the answer, then file
   your own `CLAIM`.

`kiro-impl`, `kiro-queue` and `kiro-spec-batch` now carry one word-identical
sentence deferring to that section; `kiro-spec-batch`'s inline paraphrase was
deleted rather than reworded. `kiro-queue`'s self-described "local working
heuristic" blockquote — which named this item as the open work — is gone.

**Accepted limitation, stated in the text**: an autonomous or scheduled run
with no maintainer in the loop cannot recover an abandoned claim at all. That
is honest rather than a concession — the preamble establishes that no
observable distinguishes a dead session from a live one, so declining is the
correct answer.

**Related follow-up, not closed here**: ~9 claims in the live log are
unclosed under Rule 1 (46 `CLAIM` vs 35 `MERGED` + 2 `RELEASE`) and are now
maintainer-gated by design. A visibility report for that backlog is worth
having.
