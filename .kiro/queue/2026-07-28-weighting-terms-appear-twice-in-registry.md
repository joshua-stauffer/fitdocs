---
id: 2026-07-28-weighting-terms-appear-twice-in-registry
title: The registry guard asserts "exactly once" for weighting terms that exist once per fitted curve
status: open
importance: medium
importance_why: Task 12.1 cannot write the assertion as specified; an implementer will silently reinterpret 15.6 or weaken the completeness guard that carries 16.3.
effort: S
kind: inconsistency
area: fit-ingest, .kiro/specs/fit-ingest/design.md
created: 2026-07-28
surfaced_by: /kiro-spec-tasks fit-ingest -y
pinned_at: c3d2201
resume_command: "/kiro-validate-design fit-ingest [queue: .kiro/queue/2026-07-28-weighting-terms-appear-twice-in-registry.md] Reconcile the CONSTANT_SOURCES completeness assertion with the per-curve multiplicity of the weighting terms"
context:
  - .kiro/specs/fit-ingest/design.md
  - .kiro/specs/fit-ingest/requirements.md
  - .kiro/specs/fit-ingest/tasks.md
blocked_by: []
---

## What

The design states two invariants over `CONSTANT_SOURCES` that cannot both hold
as written once Req 17 makes the training-impulse weighting selectable.

Req 15.6 enumerates "the training-impulse weighting coefficient and exponent"
as items, and the ConstantGuard is specified to assert that "every value Req
15.6 names is present **exactly once** and classified". But Req 17 and the
design's own `WEIGHTING_PAIRS` table give a coefficient and an exponent **per
fitted curve** — `BANISTER_MALE` (0.64, 1.92) and `BANISTER_FEMALE` (0.86,
1.67) — and a separate invariant requires that "every coefficient and exponent
in it also appears in `CONSTANT_SOURCES`". So the registry holds four
weighting-term constants where the completeness assertion expects two.

A second, smaller edge of the same seam: the design's classification table
gives rows only for the male pair's sites (`stress.py:55`, `stress.py:58`).
The female pair's values are named nowhere but the `WEIGHTING_PAIRS` table, so
under 15.6's "leaving none unclassified" clause it is not stated whether they
are separately classified constants or the same two items instantiated twice.

This is a *design* seam, not a requirements defect: 15.6 enumerates the values
a metric is computed from and is silent on multiplicity, which was correct
before the weighting became selectable in the same amendment.

## Why it matters

Task 12.1 is specified to write this assertion, and it is the assertion that
makes an unregistered constant fail — one half of what carries Req 16.3. An
implementer meeting the contradiction has three bad options and no stated
rule: count curve-instantiated terms as one item (weakening the guard to a
name match), assert "at least once" (losing the duplicate-registration
detection), or add female rows to the classification table on their own
authority. The third is probably right, but it is a spec decision being made
inside a test file, which is exactly the drift Amendment 1 exists to stop.

Cost is low now and rises once the guard is written and other assertions are
layered on top of its shape.

## Evidence

Verified at `737550a`:

- `.kiro/specs/fit-ingest/requirements.md:431` — Criterion 15.6 enumerates
  "the training-impulse weighting coefficient and exponent" as items, with no
  per-curve qualifier.
- `.kiro/specs/fit-ingest/design.md:1516` — ConstantGuard: "every value Req
  15.6 names is present exactly once and classified".
- `.kiro/specs/fit-ingest/design.md:1657` — the Testing Strategy repeats it:
  "every value Req 15.6 names appears exactly once in `CONSTANT_SOURCES` and
  is classified".
- `.kiro/specs/fit-ingest/design.md:1195-1196` — `WEIGHTING_PAIRS` table:
  `BANISTER_MALE` → (0.64, 1.92), `BANISTER_FEMALE` → (0.86, 1.67).
- `.kiro/specs/fit-ingest/design.md:1196` (invariants block) — "every
  coefficient and exponent in it also appears in `CONSTANT_SOURCES`".
- `.kiro/specs/fit-ingest/design.md:1064-1065` — the classification table's
  only weighting rows cite `stress.py:55` and `stress.py:58`, i.e. the male
  pair; no row exists for the female pair.

Not a duplicate of `.kiro/queue/closed/2026-07-26-amendment-1-constant-count-ambiguous.md`,
which settled how many *items* the 15.6 enumeration has (seven items, eight
named constants). This is the orthogonal question of how many *registry
entries* one enumerated item may have.

## How to pick it up

1. Read `design.md`'s MetricsSources section (the classification table and the
   `WEIGHTING_PAIRS` table) and then its ConstantGuard section — the two
   invariants are about 450 lines apart, which is why this survived the design
   gate.
2. Decide the rule and state it in one place. The likely answer, which
   `tasks.md` 9.3 already anticipates in prose ("instantiated once per fitted
   curve … every term a pair holds must also appear in the registry"), is that
   an enumerated 15.6 *item* maps to one registry entry per selection it is
   defined for, and the completeness assertion checks that every enumerated
   item is covered rather than that every item has exactly one entry.
3. Give the female pair rows in the classification table so 15.6's
   "leaving none unclassified" is satisfied structurally, with the same
   governing source and locator as the male pair.
4. Done means: `design.md` states the multiplicity rule once, the ConstantGuard
   assertion in `tasks.md` 12.1 is writable verbatim from the design, and no
   reading of 15.6 is left to the implementer.

## Open questions

- Whether reconciling this needs a requirements amendment or is a design-only
  refinement of an underspecified criterion. **The precedent one step over has
  since been reversed, so do not follow it.**
  `.kiro/queue/closed/2026-07-28-np-window-start-has-no-criterion.md` originally
  recorded the judgement that Req 8.4's silence on a start condition meant the
  design could refine it with no amendment owed. That was overturned on
  2026-07-30: an amendment *was* owed and made — criterion 8.9 now requires the
  complete-window start condition, because design prose plus a test turned out
  to be too weak to hold a value-moving behaviour in place. The approvals
  question that had been the reason to defer was settled in the same change
  (the maintainer's fast-track authorization *is* the reopening decision, and
  `spec.json` records it).

  So the live precedent now runs the other way: where a criterion's silence
  lets shipped behaviour be reverted without anything failing, amend the
  requirement rather than refine the design.
