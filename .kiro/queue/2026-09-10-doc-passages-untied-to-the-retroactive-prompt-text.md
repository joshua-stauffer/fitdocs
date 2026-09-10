---
id: 2026-09-10-doc-passages-untied-to-the-retroactive-prompt-text
title: The four documentation passages describing the retroactive-application question are pinned to nothing, so a change to the shipped prompt text or to applies_from's semantics reds no doc guard
status: open
importance: low
importance_why: The repo already guards other guide sentences against the code they describe; these four were added without that guard, and the prompt's wording already changed once on the day it shipped (the "marked as measured later" clause was removed).
effort: S
kind: gap
area: training-load, README.md, docs/ownership-contract.md, docs/contributing-calculators.md, docs/plugins.md, tests/test_docs_guarantees.py, tests/test_contributing_calculators_doc.py
created: 2026-09-10
surfaced_by: /kiro-validate-impl training-load (Amendment 4, coverage + integration dimension)
pinned_at: 52c473e
resume_command: "do: add doc-guard assertions in tests/test_contributing_calculators_doc.py (and the equivalent for README/ownership-contract/plugins) that the four Amendment 4 passages describe the shipped _retroactive_question text, the default, and applies_from's two-tier meaning; verify by changing the prompt wording and seeing a guard red"
context:
  - src/fitdocs/load/prompts.py
  - tests/test_contributing_calculators_doc.py
  - tests/test_docs_guarantees.py
  - README.md
  - docs/ownership-contract.md
  - docs/contributing-calculators.md
  - docs/plugins.md
blocked_by: []
---

## What

`README.md` ("when the activity predates the prompt, fitdocs also asks
whether the answer covers earlier activities too"),
`docs/ownership-contract.md` (the `measured_on` / `applies_from` bullet),
`docs/contributing-calculators.md` (the generic flow may ask; a calculator
never sees it) and `docs/plugins.md` (the two-tier resolution and the
negative `BenchmarkAge`) were all written or corrected on 2026-09-10 against
`src/fitdocs/load/prompts.py` `_retroactive_question` and
`BenchmarkSet.applicable`. No test reads any of them:
`tests/test_contributing_calculators_doc.py` pins other guide sentences
(e.g. `test_guide_states_the_recorded_sample_aggregate_rule`) but none of
these; `tests/test_docs_guarantees.py` enumerates the document set, not
these sentences.

## Why it matters

The change-protocol treats prose that instructs as behaviour. A later prompt
rewording, or a Phase 6 change to what `applies_from` means, leaves four
passages silently stale — the "coverage claim is the most expensive false
prose" species, in user-facing docs.

## Evidence

- Coverage validator, 2026-09-10 (FOLLOW_UPS item 3), on 52c473e; confirmed
  by `grep -n "applies_from\|earlier activities" tests/test_docs_guarantees.py
  tests/test_contributing_calculators_doc.py` → no matches.

## How to pick it up

1. Read how `test_contributing_calculators_doc.py` pins a sentence to the
   code it describes, and reuse the shape.
2. Pin, per passage, the one fact a rewording would break: README's
   condition ("predates"), ownership-contract's two key names, the
   contributing guide's "never sees it", plugins.md's two-tier sentence.
3. Done: changing `_retroactive_question`'s wording or renaming
   `applies_from` reds at least one doc guard.
