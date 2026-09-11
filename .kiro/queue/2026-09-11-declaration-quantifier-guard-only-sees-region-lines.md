---
id: 2026-09-11-declaration-quantifier-guard-only-sees-region-lines
title: The declaration quantifier guard only inspects lines containing "region"
status: open
importance: medium
importance_why: New declaration prose that does not mention a region is unguarded; only the byte-golden notices, and it cannot say why the change is wrong.
effort: S
kind: gap
area: tests/test_declaration.py, src/fitdocs/declaration.py
created: 2026-09-11
surfaced_by: /kiro-impl effort-tags 4.1
pinned_at: d1147a0
resume_command: "do: widen the declaration quantifier guard beyond lines that mention a region, or record why it is deliberately narrow"
context:
  - tests/test_declaration.py
  - src/fitdocs/declaration.py
  - .kiro/specs/effort-tags/design.md
blocked_by: []
---

## What

`tests/test_declaration.py`'s quantifier guard exists to stop declaration prose
quantifying over documents rather than over keys or regions. Its selection
predicate (`_QUANTIFIER_WORDS`, ~line 126, applied at ~135-136) only examines
lines where `"region" in line.lower()`.

Task 4.1 added a sentence naming the four user-owned keys. It mentions no
region, so the guard does not look at it.

The test's NAME is honest --
`test_no_declaration_quantifies_over_documents_near_a_region_mention` says "near
a region mention". This is a coverage gap, not a misleading name.

## Why it matters

The declaration is written into every user's `workouts/AGENTS.md`, where other
agents read it as instruction. A sentence quantifying over documents is a claim
fitdocs cannot keep. The byte-golden catches any change to the fragment, but a
golden failure says "these bytes differ", not "this sentence makes a claim about
documents" -- and a session regenerating the golden makes the failure disappear
without ever learning why the sentence was wrong.

## Evidence

Measured during task 4.1 at `1b940b1`: adding "...carried unchanged through
regeneration **in every document**" to the user-key fragment -- a
document-quantifying sentence with no region mention -- reds ONLY the byte-golden:
**1 failed, 3262 passed**.

By contrast, rewriting the fragment as "The rest of **every** frontmatter
**region**..." reds
`test_no_declaration_quantifies_over_documents_near_a_region_mention[workouts/]`,
confirming the guard is live over lines it does select.

Design-sanctioned at `.kiro/specs/effort-tags/design.md:788-791`, which chose a
region-scoped guard deliberately -- so widening it is a decision, not a bug fix.

## How to pick it up

1. Read the guard and `design.md:788-791` for why it was scoped to regions.
2. Decide: widen the predicate to every declaration line, or keep it narrow and
   record the reasoning where the next author of a fragment will see it.
3. If you widen it, expect existing true sentences to trip it -- that triage is
   the actual work, and it is what makes the guard trustworthy afterwards.
4. Prove it either way by mutation: a document-quantifying sentence with no
   region mention must red the guard, not only the golden.

Done looks like: either the guard sees prose that does not mention a region, or
its narrowness is documented at the point of use.
