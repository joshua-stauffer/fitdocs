---
id: 2026-07-30-distribution-req6-assumes-a-bundled-calculator
title: distribution's Requirement 6 and tasks 2.1/3.1/3.2 are premised on a bundled calculator that no longer exists
status: open
importance: high
importance_why: distribution is the only unstarted Phase 3 spec and its dependencies are all met, so it is the next thing a session could pick up in parallel — and it would spend three tasks building a bundled/unencumbered profile split for a methodology withdrawn five days before. The stale half must be separated from the live half before implementation, not during it.
effort: M
kind: inconsistency
area: distribution, .kiro/specs/distribution/requirements.md, .kiro/specs/distribution/tasks.md
created: 2026-07-30
surfaced_by: roadmap sync after fit-ingest Amendment 1 landed — checking whether distribution was parallel-safe against load-channels
pinned_at: c3d2201
resume_command: "/kiro-spec-requirements distribution [queue: .kiro/queue/2026-07-30-distribution-req6-assumes-a-bundled-calculator.md] Amend Requirement 6 to separate the still-live encumbered-content release gate from the now-vacuous bundled-calculator packaging, then regenerate design and tasks against it"
context:
  - .kiro/specs/distribution/requirements.md
  - .kiro/specs/distribution/tasks.md
  - .kiro/steering/roadmap.md
  - src/fitdocs/load/__init__.py
  - .kiro/queue/2026-07-29-sdist-guard-rename-evadable.md
blocked_by: []
---

## What

`distribution` was generated and approved on 2026-07-21. On 2026-07-25
`training-load` Amendment 2 withdrew the third-party methodology: the calculator
implementation, its bundled tables and its packaging were deleted, and
`fitdocs.load` now registers no built-in at all. Nothing revisited
`distribution`, so its Requirement 6 and three of its tasks still describe a
world where an encumbered calculator ships inside the package and must be made
optional.

The requirement does not fail as a whole — it splits cleanly in two, and the
split is the work:

**Now vacuous.** Criterion 6.8 ("the load package shall not export the bundled
calculator's name and shall omit it from its declared public names") and task
3.1 ("the built-in registration becomes a guarded import", "the bundled
calculator's **name is conditionally exported**", "the branded example in the
calculator-selection help text is replaced") have no subject. There is no
built-in registration to guard, no name to conditionally export, and the
package already ships with an empty registry. Task 2.1's "two profiles" — a
bundled profile built from the working tree and an unencumbered one built from
a pruned copy — collapses to one profile, because no prune path removes a
calculator any more. Task 3.2 inherits the same framing.

**Still live, and arguably more important than when it was written.** Criteria
6.1, 6.2, 6.3 and 6.7 (publish no artifact containing the encumbered
methodology's lookup tables, its name or its trademarked terms; inspect the
built artifacts rather than the source tree) still bound, because the encumbered
material still existed in the repo at the time this item was written —
the extracted tables, carrying the third party's copyright notice, were
retained as a research record. **Superseded 2026-08-01**: `encumbered-content-purge`
task 3.1 deleted the extracted tables and the writeup from the working tree
entirely, per Requirement 4's reversal of their retention, so this criterion
group's subject in the tree is gone; whether the artifact-scanning gate this
item describes is still wanted as a standing property (rather than a response
to an artifact that no longer exists) is a decision for whoever next reads this
item. Criterion 6.4 (the tool stays functional with no calculator, states so,
keeps its exit-code contract) is now simply the shipped state rather than a
condition to build toward. 6.5 (documenting how a user obtains a methodology)
is live and unchanged.

## Why it matters

distribution is the last unstarted Phase 3 spec and every dependency it names
is complete, so it is the obvious candidate for parallel work alongside
`load-channels`. A session picking it up cold would follow its approved
`tasks.md` in order and build a profile-selection mechanism, a prune-path
pipeline and a conditional-export guard for an object that is not there — most
of major 2 and all of major 3. That is a day or more of work whose observable
criteria cannot be satisfied as written ("the unencumbered wheel's member set
differs from the bundled one by exactly the pruned paths" has no difference to
measure).

The reverse risk was worse than the wasted effort: the live half of Requirement
6 is a **licensing gate**. If a session resolves the contradiction by deciding
Requirement 6 is obsolete wholesale — an easy reading, since the requirement's
own objective sentence opens "while the bundled methodology's redistribution
permission is unresolved" — the artifact-scanning gate goes with it. At the
time this item was written that mattered because the extracted tables, still
carrying the third party's copyright notice, would lose the check that was
written to keep them out of a published artifact; `2026-07-29-sdist-guard-rename-evadable`
already showed that surface was thinner than it looked. `encumbered-content-purge`
task 3.1 has since deleted those tables from the tree entirely.

## Evidence

Pinned at `ec1ec73`.

No built-in calculator is registered:

```
$ uv run python -c "from fitdocs.load import available; print(available())"
()
```

`src/fitdocs/load/__init__.py:10-12` states it as an invariant:

> Importing this package registers no built-in calculator: ``available()`` is
> […] downstream spec registers one.

`src/fitdocs/plugins.py:220` said the same in prose at the pin. The docstring
then named the withdrawn calculator and the third party directly, unlike its
current wording.

A case-insensitive search of `src/` for the third party's name and the
methodology's trademarked abbreviation returned exactly one hit at the pin:
that docstring. No other code in `src/` named the third party or the
withdrawn methodology.

The encumbered material that kept the gate live still existed in the tree at
the time this item was written — two files under the extracted tables,
carrying the third party's copyright notice. **Superseded 2026-08-01**:
`encumbered-content-purge` task 3.1 deleted them.

The stale task text, verbatim from `.kiro/specs/distribution/tasks.md`:

- task 2.1: "Build the release artifact builder with its **two profiles** …
  the bundled profile builds from the working tree, the unencumbered profile
  builds from a temporary copy with the recorded prune paths removed"
- task 3.1: "The built-in registration becomes a guarded import: when the
  methodology package is absent from the installed distribution the registry
  starts empty" — the registry starts empty unconditionally today
- task 3.1: "today the package imports it, lists it in `__all__`, and
  registers it at import time, so an unencumbered wheel would break
  `from fitdocs.load import *`" — a description of the tree before 2026-07-25

`.kiro/specs/distribution/spec.json` records `updated_at: 2026-07-21T11:20:00Z`
with all three approvals `true`, four days before the withdrawal; no amendment
array exists.

## How to pick it up

1. Read `.kiro/specs/distribution/requirements.md:208-221` (Requirement 6 in
   full) beside the `training-load` Amendment 2 record in
   `.kiro/steering/roadmap.md` › Phase 4 › Existing Spec Updates. The roadmap
   entry is what states the withdrawal shipped; the requirement is what has not
   caught up.
2. Confirm the split above still holds — `available()` empty. The extracted
   tables no longer exist to check as of `encumbered-content-purge` task 3.1;
   confirm whether the "still live" half of Requirement 6 has a subject left
   in the tree at all before amending it.
3. Amend Requirement 6 rather than deleting it. The likely shape: keep 6.1,
   6.2, 6.3, 6.5, 6.7 essentially intact but re-scope their subject from "the
   bundled methodology" to "encumbered material reaching an artifact by any
   path" — which is what 6.7 already reaches for; restate 6.4 as a property to
   assert rather than to achieve; and withdraw or rewrite 6.6 and 6.8, which
   are the two that genuinely have no subject left.
4. Then regenerate `design.md` and `tasks.md` against the amended requirement.
   Majors 2 and 3 are where the churn lands; majors 1, 4, 5, 6 and 7 (version
   identity, changelog, agent-skill packaging, documentation, CI/release
   automation) look unaffected on inspection, which is worth confirming rather
   than assuming.

**Done** looks like: `distribution`'s `tasks.md` contains no task whose
observable criteria reference a bundled calculator, a profile distinction, or a
conditional export — and the artifact-scanning licensing gate survives the
amendment with a named subject that still exists in the tree.

## Open questions

- **Does an unencumbered/bundled profile distinction have any remaining use?**
  If a third party could later ship the withdrawn methodology's calculator as a plugin, the
  release machinery might still want the concept. The alternative reading is
  that plugin distribution is that party's problem and fitdocs builds exactly
  one artifact. This decides whether task 2.1 shrinks or disappears, and it is
  a maintainer call, not an implementer's.
- **Were the extracted tables in scope for the distribution gate at all, or
  are they wholly owned by `training-load`'s packaging guard?** (Moot now that
  `encumbered-content-purge` task 3.1 has deleted them, unless the gate is kept
  as a standing property rather than a response to a specific artifact.) Two specs currently
  reach for the same surface — `training-load` via
  `tests/load/test_packaging.py` and `distribution` via Req 6.2/6.7 — and
  `2026-07-29-sdist-guard-rename-evadable` is open against the first. Whichever
  session amends Requirement 6 should say which spec owns the gate, or the
  hardening work will be done twice or not at all.
