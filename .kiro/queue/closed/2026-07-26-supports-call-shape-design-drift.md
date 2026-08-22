---
id: 2026-07-26-supports-call-shape-design-drift
title: design.md still prescribes `calculator.supports(activity)`, which Protocol semantics make unimplementable
status: closed
closed_at: 2026-07-26
closed_by: /kiro-impl training-load (between tasks 3.2 and 4.1)
closed_note: "Amended as specified. All three done-criteria verified: `grep -c 'calculator\\.supports('` 6 -> 0; the folded `default[ ]*implementation` count 3 -> 0; and both class-C sites byte-identical to pre-amendment HEAD (line 324 -> 325, and the narrowing-only invariant 799-803 -> 806-812, each diffed explicitly rather than eyeballed). The 6/6/2 class split held exactly and every line number in the site table was still accurate. The `LoadContracts` ruling of step 3 was added as a new bullet placed after the invariant block, so the invariant's bytes were not disturbed. Three `supports(activity)` occurrences remain by design: 325 and 808 are class C, and 815 is inside the new ruling, quoting the rejected Amendment 3 form it exists to explain."
importance: high
importance_why: Twelve design.md sites describe a call shape the shipped code cannot use; tasks 3.2, 4.1 and 5.1 are written against it and their reviewers will reject correct work.
effort: S
kind: inconsistency
area: training-load, .kiro/specs/training-load/design.md
created: 2026-07-26
surfaced_by: /kiro-impl training-load (task 3.3, two adversarial review rounds)
pinned_at: 33059d7
resume_command: "do: amend .kiro/specs/training-load/design.md so the engine asks supports_activity(calculator, activity) at lines 611, 1077, 1088, 1169, 1512 and 1609; reword 31, 76, 640, 1061, 1097 and 1149 so the Protocol gains no mandatory member; drop the default-implementation clause at 795-796, which no grep for supports(activity) finds — and leave 324 (threshold-load defining its own supports) and 799-803 (the narrowing-only invariant) byte-identical. Work from the three-class site table in this item; a find-and-replace corrupts class C"
context:
  - .kiro/specs/training-load/design.md
  - .kiro/specs/training-load/requirements.md
  - .kiro/specs/training-load/tasks.md
  - src/fitdocs/load/types.py
  - .kiro/queue/2026-07-26-task-33-checkpoint-unreferenced-on-main.md
blocked_by: []
---

## What

`design.md` prescribes the calculator support question as the attribute call
`calculator.supports(activity)`, with a default implementation supplied as a
body on the `LoadCalculator` `Protocol`. That is not expressible in Python. A
`Protocol` method body is inherited **only by explicit subclasses**, so a
duck-typed calculator never receives the default; and declaring the member on
the Protocol simultaneously makes it **mandatory** for structural conformance,
which is the opposite of requirements.md criterion 1.14's "a methodology that
declares nothing more specific shall answer it by its declared modalities".

Task 3.3 resolved this under a parent ruling that criterion 1.14 governs and
the call shape does not: the question is asked through a module-level
`supports_activity(calculator, activity)` in `src/fitdocs/load/types.py`, which
uses a calculator's own `supports` when it defines one and falls back to the
modality-membership test otherwise. The **semantics** design.md specifies —
pure, prompt-free, athlete-data-free, asked before field collection, permitted
to narrow a declared modality but never widen it — are unchanged and were
implemented as written.

**Correction (2026-07-26): that resolution IS on `main` now.** An earlier
revision of this item said it lived only on the unmerged branch
`impl/training-load` at `6a077a4`, a mid-review checkpoint. That is stale:
task 3.3 landed on `main` as `7f10234`, is checked off in `tasks.md`, and
`supports_activity` is at `src/fitdocs/load/types.py:378` in the working tree.
`6a077a4` is superseded (still reachable as a loose object, but not an ancestor
of `impl/training-load`, which now just tracks `main`).

So the code half is done and only the **design half remains**: `design.md` still
prescribes the attribute call `calculator.supports(activity)`, which no longer
matches the shipped mechanism. That is the entire remaining scope of this item.

The design document was not amended by task 3.3 because
`.kiro/specs/training-load/` lay outside that task's declared boundary.

## Why it matters

Tasks 3.2 (arbitration), 4.1 (the engine gate) and 5.1 (the contributor guide)
are all written against the attribute-call shape, and each is reviewed against
design.md by an independent adversarial reviewer. An implementer who follows the
branch's mechanism will be rejected for deviating from design.md; one who
follows design.md will write `calculator.supports(activity)`, which is a static
type error (`"LoadCalculator" has no attribute "supports"`) — true on `main`,
where the Protocol declares no such member, and true on the branch, where the
member form was deliberately removed — and an `AttributeError` at runtime
against every duck-typed calculator, including the installed plugin fixture and
every plain-class shape in `docs/`. Task 5.1's worked example would teach plugin
authors a call that cannot work.

## Evidence

- `requirements.md:283` (criterion 1.14) — "...and a methodology that declares
  nothing more specific shall answer it by its declared modalities."
- `design.md:1512` — "the engine asks `calculator.supports(activity)` — a
  pure, prompt-free question whose default implementation is the modality
  membership test".
- `design.md:799-803` — the narrowing-only invariant. Correct as written and
  must survive the amendment verbatim.

### The complete site list (re-verified against `main` = `33059d7`)

`design.md` holds **14** occurrences of `supports(activity)`, of which 6 are the
literal attribute call. **12 of the 14 need touching; 2 must not be.** An earlier
version of this item's `resume_command` listed six sites, one of which was the
narrowing-only invariant that must *not* change and one of which (now line 611)
was missing entirely. The three classes below are not interchangeable — **a
find-and-replace over `supports(activity)` corrupts class C.**

> **Treat the line numbers as hints and locate each site by its quoted text.**
> They have already drifted once: `bb5fabf` added two lines near 315, moving
> every site below it by +2 (the numbers here are post-drift, verified at
> `33059d7`). The stable invariant is the class split — 6 / 6 / 2 — plus the
> two counts in the code block below.

**Class A — the engine asking. Change the mechanism to
`supports_activity(calculator, activity)`:**

| Line | Text |
|---|---|
| 611 | "the engine calls `calculator.supports(activity)`, whose default implementation *is* the modality test it replaces" |
| 1077 | "First a **support check** — `calculator.supports(activity)`, a pure…" |
| 1088 | "narrows the survivors by `calculator.supports(activity)`**" |
| 1169 | "comprehension over candidates to a single `calculator.supports(activity)` call" |
| 1512 | "the engine asks `calculator.supports(activity)` — a pure, prompt-free question whose default implementation is the modality membership test" |
| 1609 | "comprehension over candidates to a single `calculator.supports(activity)` call" |

Two of these — **611** and **1512** — also carry the phrase "**default
implementation**", which is the Protocol-body assumption itself and must go with
the call shape: there is no default *implementation*, there is a fallback
*inside* `supports_activity`. The phrase occurs exactly 3 times in the document
(611, 795, 1512) and **wraps across a line break at all three**, so a plain
line-based `grep 'default implementation'` finds only 795. Use:

```
$ tr '\n' ' ' < .kiro/specs/training-load/design.md \
    | grep -o 'default[ ]*implementation' | wc -l      # 3 before, 0 after
```

**Class A′ — one site that no grep for `supports(activity)` will find.** Lines
**795-796** open the same bullet whose tail is the class C invariant, and they
carry the Protocol-default framing in its purest form: "a pure, athlete-data-free
question about one activity, **with a default implementation equal to the
modality test it replaces** (`activity.modality in self.supported_modalities`)".
Amend the default-implementation clause here too — but note the boundary
carefully: **795-796 change, 799-803 do not**, and they are consecutive lines of
one bullet. This is the site most likely to be missed, because it names neither
`calculator.supports` nor `supports(activity)`.

**Class B — bare `supports(activity)` describing the question. Reword so the
`Protocol` gains no mandatory member; the question's name is now the
module-level function:**

| Line | Why it needs touching |
|---|---|
| 31 | "`LoadCalculator` **gains** a `supports(activity)` question" — the flatly wrong one. The Protocol gains nothing; `supports` is an *optional* member a calculator may define |
| 76 | "the `supports(activity)` question" — in the amendment summary list |
| 640 | "**The no-default branch narrows candidates by `supports(activity)`**" |
| 1061 | "It *does* ask `supports(activity)` when narrowing candidates" |
| 1097 | "no-default path `supports(activity)` is therefore asked twice" |
| 1149 | "`supports(activity)` — so it now also covers…" |

**Class C — leave exactly as written. These describe a calculator *defining* its
own narrowing, which is still `supports` under the shipped mechanism:**

| Line | Text | Why it stays |
|---|---|---|
| 324 | instructs `threshold-load` to "implement `supports(activity)` as `activity.sport in SUPPORTED_SPORTS`" | Correct and load-bearing. `supports_activity` uses a calculator's own `supports` when it defines one, so this cross-spec instruction is exactly right. Rewriting it to `supports_activity` would tell another spec to implement the engine's dispatcher |
| 799-803 | the narrowing-only invariant — "`supports` may only ever *narrow* the declaration, never widen it" | The item's original note is right: verbatim. Note 799 contains a bare `supports(activity)` inside the invariant block, which is why a blind replace reaches it |

Counts to check the amendment against, at `33059d7`:

```
$ grep -c 'calculator\.supports(' .kiro/specs/training-load/design.md
6
$ grep -c 'supports(activity)' .kiro/specs/training-load/design.md
13
```

### Reproductions (gathered on the branch during task 3.3's review)

- Reproduced by the round-0 reviewer: `hasattr(cls, "supports")` is `False` for
  `ComputingCalculator`, `ScopedFieldCalculator` and `HintedCalculator` in
  `tests/load/conftest.py`; mypy reports a duck-typed calculator carrying the
  5-arg `compute` but no `supports` as `missing following "LoadCalculator"
  protocol member: supports`.
- Reproduced again as a discriminating mutation in round 1: reverting
  `supports_activity` to the literal `return calculator.supports(activity)` and
  running it against a plain non-subclassing `StubCalculator` yields
  `AttributeError: 'StubCalculator' object has no attribute 'supports'`.
- The resolution and its rationale are recorded in commit `7f10234` on `main`
  (task 3.3). The checkpoint `6a077a4` that an earlier revision of this item
  cited is superseded by it.

## How to pick it up

1. **Read `src/fitdocs/load/types.py:378` directly** — `supports_activity` is on
   `main` (task 3.3, `7f10234`); its docstring states the contract and the
   narrowing-only obligation as shipped. `git log -1 --format=%B 7f10234` has
   the ruling and its reasoning. (Ignore any instruction to read `6a077a4`
   instead — that was this item's earlier, now-corrected reading of where the
   work lived.)
2. Work the site table above class by class. Class A changes mechanism, class B
   changes wording, class C is untouched. The purity, the ordering (asked before
   field collection) and the narrowing-only direction are all correct as written
   and must be preserved word for word — only the *mechanism* moves.
3. Add one sentence at the `LoadContracts` component recording *why* the member
   form was rejected, so it is not re-proposed by a later spec — the same way
   the import-direction ruling is recorded.
4. Done looks like: `grep -c 'calculator\.supports(' design.md` returns 0; the
   12 class A and class B lines name either `supports_activity(calculator,
   activity)` or an optional `supports` a calculator may define; the class A′
   clause at 795-796 no longer claims a default implementation; line 324 and
   lines 799-803 are byte-identical to before; and the folded
   `default[ ]*implementation` count above goes from 3 to 0.

**Do this before task 3.2, 4.1 or 5.1 is dispatched.** Task 3.3 has landed
(`7f10234`), so the urgency the earlier revision attached to "round 2" is spent
— but the three tasks that consume this question have not started, and each is
reviewed against this document. Leaving it un-amended points an implementer at
`calculator.supports(activity)`, which is a static type error against the
shipped `Protocol` and an `AttributeError` against every duck-typed calculator.
This is spec text with no code dependency, so nothing blocks it.
`/kiro-spec-status training-load` should be clean either way.

## Open questions

Whether `plugin-api`'s published surface list should name `supports_activity`
as plugin-author API. It is exported from `fitdocs.load` and a calculator author
never needs to call it — only to optionally *define* `supports` — so it is
arguably layer-internal. Task 5.2 already owes that spec a surface-list
reconciliation for the `NotConfirmed` → `NotComputed` rename and could settle
both together.
