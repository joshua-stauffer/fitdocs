---
id: 2026-07-26-task-33-checkpoint-unreferenced-on-main
title: training-load task 3.3's mid-review checkpoint is invisible from main
status: done
importance: high
importance_why: A reviewed, gates-green checkpoint with five known open findings exists only on impl/training-load; nothing on main points to it, so a fresh /kiro-impl 3.3 run starts over and main has already diverged 6 commits past it.
effort: M
kind: chore
area: training-load, src/fitdocs/load/types.py, .kiro/specs/training-load/tasks.md
created: 2026-07-26
surfaced_by: /kiro-queue verification pass
pinned_at: 9469236
resume_command: "do: rebase impl/training-load's 6a077a4 onto main (6 commits ahead), work its five recorded round-2 findings, then either land task 3.3 with the training-load validation class green or discard the branch and record in tasks.md why 3.3 restarts from scratch"
context:
  - .kiro/specs/training-load/tasks.md
  - .kiro/specs/training-load/design.md
  - src/fitdocs/load/types.py
  - .kiro/steering/change-protocol.md
  - .kiro/queue/2026-07-26-supports-call-shape-design-drift.md
blocked_by: []
---

## What

`training-load` task 3.3 ("Repin the calculator contract on a per-pass
context") has a substantial partial implementation committed as `6a077a4` on
branch `impl/training-load` — 11 files, +391/-72, with `pytest` 1754 passing,
`mypy` clean over 55 files and `ruff` clean at that checkpoint.

Nothing reachable from `main` says so. `tasks.md:208` shows 3.3 as `- [ ]` on
both `main` and the branch, which is correct (the commit message states plainly
it is "NOT an approved task" — an independent review rejected it on five open
findings and remediation round 2 is pending). But "unstarted" and "half-built
on a branch, awaiting round 2" are indistinguishable to the next session, and
only the second one is true.

Meanwhile `main` has advanced 6 commits past the branch point (`e16513a`…): the
queue resume-command work, the change-guard `cd` fix, the supplemental-scale
render fix and the document-date reassignment.

## Why it matters

Three concrete costs, in increasing order:

1. **Duplicated work.** A session told to run `/kiro-impl training-load 3.3`
   from `main` sees an unticked task and no local trace of the branch. It
   re-derives `LoadContext`, the `TYPE_CHECKING`-only `LoadSettings` import,
   `supports_activity`, and the `NotConfirmed` → `NotComputed` rename — all of
   which are already built and independently verified — and it re-discovers the
   Protocol-semantics problem the checkpoint already resolved.
2. **A sibling queue item is unactionable as written.**
   `2026-07-26-supports-call-shape-design-drift` opens its "How to pick it up"
   with "Read `src/fitdocs/load/types.py` — the `supports_activity` docstring
   states the contract as shipped." On `main` that function does not exist
   (`grep -rn supports_activity src/ tests/` is empty); it exists only on the
   branch. That item's premise — "the code already went this way, the design
   document did not follow" — is true of the branch and false of `main`.
3. **Rebase cost is monotonic.** The 6 intervening commits do not touch
   `src/fitdocs/load/types.py`, so the rebase is clean *today*. Tasks 3.2, 4.1
   and 4.2 all edit the load layer, and any of them landing first turns this
   into a real conflict.

## Evidence

Verified at `main` = `9469236`:

```
$ git rev-list --left-right --count main...impl/training-load
6	1
$ git log --oneline main..impl/training-load
6a077a4 wip(training-load): task 3.3 contract repin — mid-review checkpoint
$ grep -rn "supports_activity" src/ tests/     # on main
(no output)
$ git grep -n "supports_activity" impl/training-load -- src/
impl/training-load:src/fitdocs/load/types.py:378:def supports_activity(...)
impl/training-load:src/fitdocs/load/__init__.py:44,70
```

- `.kiro/specs/training-load/tasks.md:208` — `- [ ] 3.3` on both refs.
- `6a077a4`'s message records what is verified (`LoadContext` frozen at exactly
  `{activity_date, settings}`; zero runtime `fitdocs.load.*` imports in
  `load/types.py`, proven per module in a fresh subprocess;
  `supports_activity` replacing the Protocol member; `NotComputed`; four stubs
  on the 5-arg `compute`) and the five findings still open:

```
1. the custom-supports branch (types.py:403-405) is dead to the suite
2. DecliningCalculator.supports widens its declared modality (design.md:798-801)
3. supports_activity is absent from the public-surface pin
4. two assertions still use the forbidden attribute read
5. a stale "verified by mypy --strict" comment (mypy scans src/ only)
```

- The branch itself was created under the change protocol — the commit message
  records it was "relocated from an uncommitted main-tree edit into this
  worktree", which is the lifecycle `change-protocol.md` prescribes.

## How to pick it up

1. `git log -1 --format=%B 6a077a4` — the five open findings and the verified
   list are the round-2 work order; do not re-derive them.
2. Rebase onto `main` and confirm the load layer still has no conflict
   (`git rebase main` from the branch; the 6 intervening commits touch
   `.claude/`, `.kiro/queue/`, `src/fitdocs/render/sections.py` and
   `.kiro/specs/athlete-benchmarks/`, none of them `src/fitdocs/load/`).
3. Work findings 1–5, then run the `training-load` validation class and take it
   back through review. Finding 2 (`DecliningCalculator.supports` widening its
   declared modality) is the one with a design implication — `design.md:798-801`
   states the narrowing-only invariant, and the stub is currently violating the
   contract it is meant to exercise.

**Done** means either task 3.3 is `[x]` on `main` with its gates green, or the
branch is deleted and `tasks.md` records that 3.3 restarts clean — so that no
future session has to guess which.

## Resolution (2026-07-26)

Closed by the first branch of the stated Done condition: **task 3.3 is `[x]` on
`main` with its gates green.**

- Round 2 worked all five recorded findings; a third independent review
  confirmed each closed by tracing and mutation rather than by reading (the
  custom-`supports` branch went from `custom: 0` hits to `custom: 7`, and
  reddens under mutation). Verdict APPROVED.
- Branch rebased onto `main` at `e8b4d72` — clean, as this item predicted: zero
  file overlap between the branch's 11 files and the 23 main changed.
- Validation re-run **after** the rebase per `change-protocol.md`: `pytest` 1755
  passed, `mypy src/` clean over 55 files, `ruff check .` clean, all exit 0.
- Merged `--ff-only` as `7f10234`; worktree and branch removed.

The sibling item `2026-07-26-supports-call-shape-design-drift` is now
actionable as written: `supports_activity` exists on `main`, so its premise
("the code already went this way, the design document did not follow") is true
of `main` rather than only of a branch.

On this item's open question — whether the design amendment should land first —
it landed *after*, and the risk it names did materialize in a milder form: two
review rounds were spent before the Protocol-semantics conflict was adjudicated.
The mitigation now in place is `tasks.md`'s Implementation Notes, which record
the ruling and instruct reviewers of tasks 3.2/4.1/5.1 not to reject correct
work for deviating from design.md's stale call shape.

## Open questions

Should the amendment in `2026-07-26-supports-call-shape-design-drift` land
before, with, or after this? Landing the design amendment first makes round 2
reviewable against a design document that matches the intended mechanism;
landing it after risks another reviewer rejecting the same correct work for the
same wrong reason. Sequencing the amendment first is the cheaper order, and it
is a spec-text-only change with no code dependency.
