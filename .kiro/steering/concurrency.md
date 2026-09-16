# Concurrent Implementation Sessions

How two or more agent sessions implement different specs at the same time
without corrupting each other's evidence. Applies to any session running
`/kiro-impl` (or hand-implementing spec tasks).

`change-protocol.md` is the prerequisite: it puts *every* non-trivial change —
spec work or not, concurrent or not — in its own worktree, and defines when a
change is done. This document adds what a second session makes necessary.

**Do not skip this because you believe you are the only session running.** You
cannot establish that from inside your own worktree, and the log obligations
below are what make the answer knowable — to you now, and to whoever starts
next. A session is solo only until it isn't, and by then the coordination it
skipped is unrecoverable.

## The Rule

**One git worktree per session. Never two sessions in one working tree.
Every session reads and writes the shared log.**

A session claims a spec, works it to completion in its own worktree on its
own branch, merges that branch back into `main` itself, and pushes `main`. The
worktree is already required by the change protocol, as is pushing every
commit as it is made; concurrency is what makes sharing one tree unsafe rather
than merely untidy.

The two halves are one rule. Worktree isolation is what makes the sessions
independent, and that independence is exactly what leaves them blind to each
other: nothing in a session's own tree reveals that a peer exists. The log is
the only channel back. Isolation without the log is not concurrency, it is
three sessions racing toward the same merge.

## Why (the coupling that breaks)

Three parts of the implementation protocol read whole-tree mutable state,
so two sessions in one tree produce confidently wrong verdicts:

1. **`git diff` is the reviewer's primary source of truth.** In a shared
   tree it returns the union of both sessions' uncommitted work. The
   reviewer either rejects on a peer's changes or approves code it never
   examined — the review gate fails silently.
2. **RED/GREEN runs against the tree.** A peer's half-written module can
   turn a genuine RED green, or a genuine GREEN red. "Fresh evidence" is
   then fresh evidence about the wrong tree.
3. **Preflight baselines assume a still tree.** `git status --porcelain`
   taken as a baseline is meaningless when a peer is writing concurrently.

Commits race too: staging is per-path, not per-hunk, so committing a file a
peer is mid-edit in captures their partial work under your message.

Separate worktrees fix all four mechanically — `git diff`, `pytest`, and the
baseline all become per-session and correct — with no protocol changes.

## Session Lifecycle

The lifecycle is the one in `change-protocol.md` — log read and claim, worktree,
branch, per-task commits each pushed as it is made, rebase and a
`--force-with-lease` push of the rebased branch, post-rebase validation,
`--ff-only` merge, `git push origin main`, teardown of the local and remote
branch — with the branch named `impl/<spec>`.

Two additions concurrency imposes:

- **Rebase early and often** — daily at minimum, and immediately whenever the
  log shows a peer merged. Long-lived branches are the only real merge risk;
  per-task commits rebase cheaply. Each rebase is followed by
  `git push --force-with-lease origin impl/<spec>`: the rebase made new
  commits, and they are as unpushed as any other until they are on the remote.
- **Keep the log current throughout** — the claim before the first edit, the
  merge once it lands, and every `WARN` or `NOTE` in between, at the read and
  write points below. This runs the whole length of the lifecycle; it is not
  a step at either end.

## Merge-Back Is In Scope

A spec is **not complete** when its last task is checked off. On top of the
change-protocol Definition of Done, a spec run owes:

1. All tasks `[x]` (or explicitly `_Blocked:_` with reasons reported)
2. Feature-level validation passing, re-run after the rebase
3. `main` pushed to `origin` — a merge is landed nowhere until it is
4. A log line recorded for the merge

A session that leaves an unmerged branch has not finished. If merge-back is
blocked (a genuine semantic conflict with a peer's landed work), that is a
finding to report, not a state to leave behind.

## Concurrency Pattern

- **Claim at spec granularity.** One spec is worked by at most one session.
  Never split a spec's tasks across sessions — task dependencies and the
  shared `## Implementation Notes` assume one writer.
- **Prefer specs with disjoint boundaries.** Before claiming, check whether
  an in-flight spec's tasks touch the same modules as yours.
- **Choke points force serialization.** Modules that many specs extend
  cannot be safely co-edited in the same window; the second claimant either
  picks a different spec or waits. Find them before claiming:

  ```bash
  grep -ho 'src/fitdocs/[a-zA-Z0-9_/]*\.py' .kiro/specs/*/tasks.md \
    | sort | uniq -c | sort -rn | head
  ```

  As of 2026-07-25 `load/settings.py` and `load/types.py` dominate the
  count: the load-cluster specs (training-load, threshold-load,
  load-channels, activity-qa-flags, athlete-benchmarks) all extend them and
  should be run one at a time. Treat the CLI entry point as a choke point
  too even when the count is low — every spec that adds a command lands
  there, whether or not tasks.md names the file.
- **Two sessions is the practical ceiling.** Review and merge attention are
  the bottleneck, not compute.

## The Shared Agent Log

The log is a **first-class artifact of every session**, on the same footing as
the branch and the commits — not a courtesy extended by sessions that already
know a peer is running. Keeping it current is part of doing the work, not
paperwork about the work.

**Location**: `$(git rev-parse --git-common-dir)/agent-log`

The shared `.git` directory resolves to the same absolute path from every
linked worktree, so one file is visible to all sessions, is never committed,
never merge-conflicts, and never diverges by branch.

**Format**: append-only, one line per event, `printf` with `>>` — never
`Edit`, never a rewrite. Concurrent appends of short lines do not interleave.
Four tab-separated fields: UTC timestamp, session id, event, body. The
session id is stable for the life of the session and names the work rather
than the agent — a session on `impl/<spec>` logs as `impl-<spec>`.

```bash
LOG="$(git rev-parse --git-common-dir)/agent-log"
printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$SESSION" CLAIM "<spec> (worktree <path>, branch <name>)" >> "$LOG"
```

Naming the worktree and branch in a `CLAIM` is good practice — it is part of
what a maintainer will ask for when confirming a claim is abandoned (see
"Stale claims" below) — but it is not a required field, and the census of
this repo's own log confirms not every claim carries it.

### Read points

Read the log — the whole file, or everything since your last read — at each
of these. Reading is cheap; the state it describes is not recoverable any
other way.

| Read when | What you are looking for |
|---|---|
| Session start, before claiming | Live claims, so you don't take a spec a peer holds |
| Before rebasing | What landed since you branched, and what the peer says about it |
| Before entering a choke-point module | A peer `TOUCHING` it, or one who already changed its shape |
| On resume after any pause | Everything — a paused session's picture of the repo is stale |
| When something fails in a way your own diff does not explain | A peer `WARN` about that same class of failure |

### Write points

Write at each of these, unprompted, as the event happens — not batched at the
end, where a peer can no longer act on it.

| Event | Write when |
|---|---|
| `CLAIM` | You begin work on a spec or change — before the first edit |
| `TOUCHING <path>` | A task enters a choke-point or otherwise peer-visible module |
| `TASK-DONE` | A task is approved and committed, and changes what peers may assume |
| `MERGED` | A branch lands on `main` and `main` is pushed — this is what frees a choke point |
| `RELEASE` | You abandon or park a claim, so the spec is takeable again |
| `BLOCKED` | You cannot proceed, and a peer's work is why |
| `WARN` | You found something that will bite a peer: a shared surface you changed, a landed API they must consume rather than re-add, a trap that cost you review rounds |
| `NOTE` | Anything else a peer would want before their next decision |
| `OVERRIDE` | You are taking a `CLAIM` the maintainer has confirmed is abandoned — see "Stale claims" below |

`WARN` and `NOTE` carry most of the value in practice, and are the two a
session is most likely to skip. The entries that have actually saved work here
were not claims — they were lines like *"contract.document_date is now on my
branch, consume it, do not add a second"* and *"an AST guard asserting a module
is not imported is bypassed by alternate spellings"*. A claim tells a peer
where you are. A warning changes what they do.

**Write the body for a peer who has not seen your transcript.** Name the
module, spec, commit, or branch — not "the fix" or "that issue". A line only
its writer can decode did not coordinate anything.

**A session that believes it is solo still writes.** It cannot know that: a
peer may start an hour in, and the log is the only place they can discover
what is already in flight. The read points are what tell you whether you are
solo — writing is what makes that answer available to whoever asks next.

**What the log is**: the durable shared memory of a multi-session run — who
holds what, which choke points are hot, what landed and needs rebasing onto,
and what a peer learned the hard way.

**What the log is not**: a lock. Reads are point-in-time, so a claim has a
race window; worktree isolation, not the log, is what makes concurrency
*safe*. The log only makes it *coordinated*. Do not build correctness
guarantees on it, and do not assume a subagent has read it — the parent
session owns both reading and writing on its behalf.

### Stale claims

Nothing above defines when a `CLAIM` expires, and two earlier attempts at a
mechanical expiry rule for it both failed the same way. Both tried to infer
a hidden variable — is the claiming session's process still running — from
signals that are not a function of that variable at all: worktree/branch
presence, `git status` cleanliness, commit recency, whether the log keeps
naming the target, whether the session id keeps appearing. **No Boolean
combination of non-injective signals is injective.** Requiring all of them
(conjunctive) routed every ambiguous case into a false negative — a
permanent lock, exactly what this document forbids. Requiring any one of
them (disjunctive) routed the same ambiguity into a false positive —
overriding claims that were still live. Re-weighting or recombining the same
signals cannot fix this; the rule below does not use them to infer death at
all.

**No git artifact in this repo establishes that a session is dead.** State
plainly what each observable actually conflates, so a future round does not
re-derive an inference rule from one of them:

- **Worktree/branch absence** conflates *not yet created* (a `CLAIM` is
  written before `git worktree add`, per `change-protocol.md`'s own
  lifecycle), *torn down after a successful `MERGED`* (that lifecycle's own
  final step), and *the session died before either*. Three states, one
  observation.
- **A clean `git status --porcelain`** is the baseline of a session between
  commits, alive or dead — it does not distinguish them.
- **No commit since the `CLAIM`** is the state of a session in review, in a
  debug pass, or simply reading — `impl-fit-ingest` went from 06:57 to 07:21
  one day with no commit, alive throughout — and it is equally the state of
  a dead one.
- **No further log line naming the target** is misleading in both
  directions: peers routinely write about a target they do not own — 15
  distinct session ids name `fit-ingest` in this log, 14 of them not its
  claimant — so a later line proves nothing about the claimant specifically,
  and its absence proves nothing about whether the claimant is alive.
- **No further line from that session id** fails outright the moment an id
  is reused: ids that skills mandate as fixed labels —
  `kiro-spec-batch/SKILL.md:22` ("Use `spec-batch` as this session's id") and
  `kiro-queue/SKILL.md`'s hardcoded `queue-close` — are reused by
  construction across runs, so "no line from this id" can be false forever
  after the claim it described is long dead.

#### Rule 1 — a claim is closed only by a positive line

A `CLAIM` is closed when the claiming session itself later writes a `MERGED`
or a `RELEASE` naming the same target. Nothing else closes it. This is
decisive and needs no window: one grep across the log tells you whether
either line exists. It also matches how claims actually end in this repo —
the live log holds 46 `CLAIM` lines against 35 `MERGED` and 2 `RELEASE`; an
open claim with neither is not an anomaly to explain away, it is simply not
yet closed.

#### Rule 2 — an unclosed claim is not inferred stale from git or log state

The signals enumerated above (worktree/branch presence, status, commit
recency, later log activity) are useful context, never a verdict. Do not
build a check, timer, or heuristic — local to a skill or otherwise — that
treats any of them, alone or combined, as proof a claiming session is gone.

#### Rule 3 — an unclosed claim you want is a maintainer question, not a timer

Every session in this log was maintainer-started, so the maintainer can
answer in one exchange what no window of any length, and no combination of
the signals above, can establish from inside a worktree: whether that
session is still running. Present the evidence and ask, rather than waiting —
this is material for the maintainer to weigh, not signals for you to score:

- the `CLAIM` line itself — session id, target, timestamp
- whether the named worktree and branch exist, and their state if so
  (`git worktree list`, `git -C <path> status --porcelain`, last commit)
- the last log line, if any, from that session id or naming the same target

Record the maintainer's answer before taking the work, then file your own
claim for the same target:

```bash
LOG="$(git rev-parse --git-common-dir)/agent-log"
printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "<session>" OVERRIDE \
  "<target>: maintainer confirmed <claiming-session> is not running — taking it" >> "$LOG"
printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "<session>" CLAIM \
  "<target> (worktree <path>, branch <name>)" >> "$LOG"
```

This is a question with a one-exchange answer, not a wait with a fixed
period — that is what keeps it from reinstating the lock this document
forbids elsewhere. If the maintainer is unavailable — including an
autonomous or scheduled run with no maintainer in the loop — the claim
stands, and it stands equally if the maintainer says the session may still
be running; pick different work.

## Not Allowed

(On top of the change-protocol prohibitions, which still apply.)

- Two sessions in one working tree, under any framing
- Splitting one spec's tasks across concurrent sessions
- Treating a log line as a lock you may proceed against. The only two ways
  an unclosed `CLAIM` stops blocking you are Rule 1 (its own session closed
  it with `MERGED`/`RELEASE`) and Rule 3 (the maintainer confirmed the
  session is gone) — no inference from worktree, git, or log state ever
  substitutes for either
- Inferring a claiming session is dead from worktree/branch presence, `git
  status`, commit recency, or log activity (Rule 2) — ask the maintainer
  instead (Rule 3)
- Working a spec without a `CLAIM`, or landing a merge without a `MERGED`
- Dropping the log partway through a long session — an abandoned log is worse
  than none, because peers still read it and now believe you stopped
- Keeping a finding that would cost a peer review rounds inside your own
  transcript

---
_Document the contract, not the current branch list_
