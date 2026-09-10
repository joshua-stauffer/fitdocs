---
id: 2026-09-10-hint-ordering-test-drives-a-flat-field
title: test_retroactive_question_asked_after_the_hint_confirm drives a flat field, so its observable is the same whether or not the hint decline short-circuits the retroactive question
status: open
importance: low
importance_why: The ordering clause of Req 3.7 is genuinely pinned by two sibling tests that use a benchmark field; this one carries a docstring claiming to observe the short-circuit while its fixture can never reach the question — the "indistinguishable outcome" anti-pattern, harmless today, misleading to the next editor.
effort: S
kind: gap
area: training-load, tests/load/test_prompts.py
created: 2026-09-10
surfaced_by: /kiro-impl training-load (Amendment 4, task 7.3 review)
pinned_at: 52c473e
resume_command: "do: in tests/load/test_prompts.py, rewrite test_retroactive_question_asked_after_the_hint_confirm to use the inline hinted_bench benchmark field with confirms=[None] and activity_date < on, assert the retroactive question is absent from session.asked, and verify by mutation that asking the question before the hint confirm reds it; correct the docstring sentence calling HPL 'benchmark-shaped'"
context:
  - tests/load/test_prompts.py
  - src/fitdocs/load/prompts.py
blocked_by: []
---

## What

`tests/load/test_prompts.py:978` `test_retroactive_question_asked_after_the_hint_confirm`
uses `HPL`, a flat field with no `BenchmarkRef` (`test_prompts.py:52`). The
retroactive question is never asked for a flat field, so "exactly two
questions, no retro text" holds whether or not the hint decline short-circuits
anything. Its docstring says "A decline at the hint confirm (`None`)
short-circuits before the retroactive question is ever asked" and calls `HPL`
"benchmark-shaped".

## Why it matters

Change-protocol § Fixture Discrimination, *indistinguishable outcome*: the
test cannot fail under the mutation it describes. The 7.3 reviewer confirmed
it stays green under both "ask before the value is accepted" and "ask for
flat fields too". The clause is pinned elsewhere
(`test_retroactive_question_reached_when_hint_is_accepted`,
`test_retroactive_question_defaults_to_true_distinct_from_the_hint_confirm`),
so nothing is unpinned — but a test whose docstring names a mechanism it
cannot observe is the prose species this repo's notes call worse than a
missing test.

## Evidence

- `tests/load/test_prompts.py:978-1000` (fixture `HPL`, flat);
  `tests/load/test_prompts.py:52` (`HPL` declaration, no `benchmark=`).
- 7.3 review finding 1 (Opus reviewer, 2026-09-10): green under both named
  mutations; siblings red (4 red total).

## How to pick it up

1. Read the two sibling tests named above for the `hinted_bench` fixture and
   `confirms` queue shape.
2. Rewrite this test over `hinted_bench` with `confirms=[None]` (hint
   declined) and `activity_date < on`; assert the field is still-missing,
   nothing persisted, and no recorded question contains the retroactive
   text.
3. Done: the "ask before the hint confirm" mutation reds this test.
