---
id: 2026-07-29-reference-doc-guards-are-substring-blind
title: The Req 15.5 guards catch only two literal spellings of the working reference document, so any paraphrase of it ships green
status: open
importance: medium
importance_why: These guards are the only mechanical enforcement of Req 15.5 in the metric modules, and the prose they guard is rewritten by every 10.x task — a paraphrased citation is exactly what a docstring rewrite produces.
effort: S
kind: gap
area: fit-ingest, tests/metrics/
created: 2026-07-29
surfaced_by: /kiro-impl fit-ingest (task 10.2, review round 1)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-29-reference-doc-guards-are-substring-blind.md] Widen the Req 15.5 reference-document guards beyond two literal substrings, or fold them into task 12.2's package-wide scan"
context:
  - tests/metrics/test_power.py
  - tests/metrics/test_aggregates.py
  - tests/metrics/test_sources.py
  - .kiro/specs/fit-ingest/requirements.md
  - .kiro/specs/fit-ingest/tasks.md
blocked_by: []
---

## What

`test_module_source_does_not_name_the_working_reference_document`, shipped in
`tests/metrics/test_aggregates.py` (task 10.1) and `tests/metrics/test_power.py`
(task 10.2), asserts that the module source does not contain the substrings
`docs/reference` or `fitdocs-ai-reference`. Requirement 15.5 forbids naming any
working document under the reference directory as a constant's source.

Any naming that avoids those two exact spellings passes. "the fitdocs-ai
reference doc, section 2" satisfies the guard while doing precisely what 15.5
forbids.

## Why it matters

These guards are the only mechanical enforcement of Req 15.5 on the metric
modules, and the prose they cover is rewritten wholesale by every task in major
10 — the second bullet of each is "rewrite the module docstring to name the
records instead of the working reference document". A rewrite is exactly the
operation that turns a path into a paraphrase.

The blindness is not theoretical. In task 10.2 the reviewer found an orphaned
citation ("...per the reference") whose antecedent the diff had deleted, and
proved the guard could not see it: replacing the removed clause with "the
fitdocs-ai reference doc, section 2" left all 230 `tests/metrics/` tests green.
That defect was found by reading, and it is the second prose defect in two
tasks that this guard was present for and blind to.

Note the direction of the blindness is the safe one in the narrow sense — these
are negative assertions, so they do not *falsely* red. But a guard whose
coverage is two string literals invites exactly the confidence Req 15.5 cannot
afford.

## Evidence

At `373405a`:

- The guards: `tests/metrics/test_power.py` and `tests/metrics/test_aggregates.py`,
  each asserting `"docs/reference" not in source` and
  `"fitdocs-ai-reference" not in source`. `tests/metrics/test_sources.py:332-361`
  has the same shape and documents only the bare-filename case.
- Mutation run by the task 10.2 reviewer: replacing the clause at
  `power.py:15-16` with "(the fitdocs-ai reference doc, section 2)" → all 230
  `tests/metrics/` tests pass.
- The complementary mutation (re-inserting the literal path) reds with sole
  failure, confirming the guard works for the spellings it knows.

## How to pick it up

1. Decide the scope first: task 12.2 ("Guard the literal surface of the metric
   modules") ships a package-wide scan and may be the right home. If 12.2 has
   landed, extend it rather than adding a third per-module guard.
2. If widening in place, the cheap improvement is to match on the document's
   distinctive tokens rather than its path — `fitdocs-ai` and `fitdocs_ai` and
   a case-insensitive `fitdocs.ai`, plus `section 2`, plus the bare filename —
   and to assert against a normalized (whitespace- and punctuation-collapsed)
   copy of the source so line wrapping cannot split a token.
3. Accept that no substring guard is complete. State the residual explicitly in
   the test's own docstring rather than implying total coverage — the repo has
   been bitten before by prose claiming coverage a guard does not have.
4. Verify by mutation, in both directions: a paraphrase must now red, and the
   legitimate negative sense (`stress.py`'s own "...rather than to any working
   reference document") must stay green.

## Open questions

Whether Req 15.5's enforcement belongs in per-module tests at all, or only in
12.1/12.2's guard layer. Three near-identical copies now exist; consolidating
them is arguably the real fix.
