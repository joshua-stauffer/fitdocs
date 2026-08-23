---
id: 2026-07-26-line-number-citations-in-tests-go-stale
title: 15 test docstrings cite `engine.py:NNN` line numbers that nothing validates, and an engine edit silently invalidates them
status: open
importance: medium
importance_why: These citations exist to tell the next session where a mutation lives, so a stale one sends a reviewer to the wrong code — and one was already wrong before anyone noticed.
effort: S
kind: chore
area: tooling, tests/load/test_engine.py, tests/load/test_arbitration_e2e.py, tests/test_confinement.py, .kiro/steering/change-protocol.md
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 4.2 review, Finding 2 + FOLLOW_UPS)
pinned_at: c3d2201
resume_command: "do: decide the convention for referring to production code from a test docstring -- stable anchors (function/symbol names) rather than line numbers, or a check that validates the citations -- then convert the 15 existing engine.py:NNN hits [queue: .kiro/queue/2026-07-26-line-number-citations-in-tests-go-stale.md]"
context:
  - tests/load/test_engine.py
  - tests/load/test_arbitration_e2e.py
  - tests/test_confinement.py
  - src/fitdocs/load/engine.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What
Test docstrings across three modules cite line numbers in
`src/fitdocs/load/engine.py` — "the mutation this catches is at
`engine.py:482-491`", "moving it to run after `collect_missing_fields`
(482-491)". `grep -rn "engine\.py:[0-9]" tests/` returns **15 hits**.

Nothing validates them. They are load-bearing prose: their entire purpose is to
tell a later session or reviewer *where* the guarded behavior lives, which is
exactly the information a mutation sweep needs. When they are wrong they send
that reader to unrelated code.

## Why it matters
This is the false-prose species the change protocol's "Prose is not evidence"
section exists for, but applied to a *location* rather than a claim — and
locations rot on every edit to the cited file, with no diff to warn you. The
citation looks precise, which is worse than vague.

Task 4.2 demonstrated the full failure mode in one diff:

- The change shifted `engine.py` by **+8** above the field-collection block and **+11** below it.
- **8** pre-existing citations were silently invalidated. The implementer updated **4**.
- One of those 4 was updated with an **off-by-one**, because it applied a uniform offset rather than reading the cited lines — the diff had itself added a line (`on=today,`) inside the cited range.
- A **9th** citation, `tests/test_confinement.py:115` (`engine.py:385` for the `save_profile` write), was already wrong *before* the change: line 385 at `f7bdf97` is blank. Nobody had noticed.

So the convention fails in three independent ways at once: not updated, updated
wrongly, and already wrong.

## Evidence
At `f7bdf97`:

```
grep -rn "engine\.py:[0-9]" tests/   # 15 hits across 3 files
git show f7bdf97:src/fitdocs/load/engine.py | sed -n '385p'   # blank
```

The 8 invalidated by task 4.2, verified by the reviewer against both base and
post-change `engine.py`: `test_engine.py:730` (364→372), `:969` (511-517→522-528),
`:1205` and `:1251` (264-268→272-276), `:1254` (261-263→269-271), `:1277`
(259-263→267-271), `:1284` (283→291), and `test_arbitration_e2e.py:963`
(261-268→269-276). Task 4.2's round 2 fixes these; the *convention* is what this
item is about.

## Open questions
Which fix, and it is a convention decision:
1. **Stable anchors** — cite the function and symbol (`_compute_document`'s `supports_activity` guard) instead of a line range. Never rots, slightly less precise, requires no tooling. Probably the right default.
2. **A validating check** — a test that parses the citations and asserts the cited lines contain the quoted code. Keeps precision, costs a guard that must itself be kept honest (and see [[2026-07-26-git-resolved-commit-pins-in-tests]] for the adjacent species).
3. **Both** — anchors in prose, and drop line numbers entirely.

## How to pick it up
1. `grep -rn "engine\.py:[0-9]" tests/` and read a few in context to see what each citation is actually *for* — most are "where the mutation this test catches lives".
2. Decide the convention and record it in `.kiro/steering/change-protocol.md` alongside the Fixture Discrimination section, since that is what makes these citations load-bearing in the first place.
3. Convert the 15 hits. Verify each by reading the cited code, not by re-applying an offset — that is what produced the off-by-one above.
4. Done looks like: no unvalidated line-number citation remains, or a check exists that reddens when one goes stale. Include `tests/test_confinement.py:115`, which is wrong today.

## A second, related locational rot: citations to ephemeral artifacts
While fixing the above, a sibling pattern surfaced in the same docstrings —
prose that defends a claim by pointing at something outside the repo entirely.
`tests/load/test_engine.py:939-940` reads:

> `Verified by hand against both mutations (see the round-1 remediation status
> report's EVIDENCE section).`

A subagent status report is a conversation artifact; it is not committed and no
future session can open it. So the citation is unfalsifiable by construction —
strictly weaker than either re-running the mutation or saying nothing. This text
is **pre-existing** (predates task 4.2; only the line numbers on the adjacent
line were touched), so it is recorded here rather than fixed in that task.

Fold this into the same convention decision: a test docstring may cite repo
content (a symbol, a file, a committed spec section) but never a transcript, a
report, or a conversation.

## A third variant: prose naming a failure *mechanism* rather than an assertion
Task 4.2 also shipped "the field would be prompted and reported still missing"
for a mutation that actually reds with `IndexError: pop from an empty deque` —
and the invalidating change was round 2's own addition of a second field to that
same test. Which observable fires depends on how many answers the fixture
queues, so the route is not a durable claim. Fixed in `3e42f7d` by naming the
sole-failure fact instead, but the convention question is the same one: a
"Mutation caught" docstring should name the assertion, never the path.

Also folds in: `.kiro/specs/athlete-benchmarks/research.md:93` cites
`prompts.py:88-89` for the "already have it" skip, now at `prompts.py:110-116`.

Related: [[2026-07-26-tests-that-cannot-fail]] is the umbrella for prose that
claims coverage it does not have; this is the locational variant.
