---
id: 2026-09-10-rich-session-default-rendering-unpinned
title: RichInteractionSession's visible default marker (`[Y/n]` vs `[y/N]`) is pinned by nothing, so Req 3.9's "offer the affirmative answer as its default" is unobservable at the terminal layer
status: open
importance: low
importance_why: The value the flow passes is pinned at both the prompt and engine level, and the real session's empty-answer-takes-default behaviour is pinned; only the rendered marker the athlete actually reads is untested, so a swapped marker would ship silently.
effort: S
kind: gap
area: training-load, src/fitdocs/load/prompts.py, tests/load/test_prompts.py
created: 2026-09-10
surfaced_by: /kiro-impl training-load (Amendment 4, task 7.3 review)
pinned_at: 52c473e
resume_command: "do: in tests/load/test_prompts.py, assert through a captured Console that RichInteractionSession.confirm prints '[Y/n]' for default=True and '[y/N]' for default=False, and add one composed Rich-session test for the retroactive question (value answer, then an empty line) that ends with applies_from set"
context:
  - src/fitdocs/load/prompts.py
  - tests/load/test_prompts.py
  - .kiro/specs/training-load/requirements.md
blocked_by: []
---

## What

`src/fitdocs/load/prompts.py:298` builds the marker
(`options = "[Y/n]" if default else "[y/N]"`) that tells the athlete which
answer an empty line takes. No test reads it:
`grep -rn "\[Y/n\]\|\[y/N\]" tests/load/test_prompts.py` returns nothing.
`test_rich_confirm_yes_no_default_and_skip` pins that `""` returns the
default and `"s"` returns `None`, and 7.3's tests pin that the retroactive
question is asked with `default=True`; the two halves are never composed
through the real session, and the marker itself is unpinned.

## Why it matters

Requirement 3.9 says the affirmative answer is *offered* as the default. The
offer is the marker. Swapping the two strings ships a prompt that tells the
athlete Enter means "no" while Enter means "yes" — and every test stays
green.

## Evidence

- `src/fitdocs/load/prompts.py:298`.
- `grep -rn "\[Y/n\]" tests/` → no matches (2026-09-10, branch
  `impl/training-load-prompt-date` at 52c473e).
- 7.3 review FOLLOW_UPS item 2 (Opus reviewer, 2026-09-10).

## How to pick it up

1. Read `RichInteractionSession.confirm` and the existing
   `test_rich_confirm_yes_no_default_and_skip` (~line 387 of the test module)
   for the `Console` capture pattern.
2. Add the marker assertion for both defaults, then one composed test:
   `RichInteractionSession(console, input_fn=_queued_input(["275", ""]))`
   through `collect_missing_fields` with a benchmark field and
   `activity_date < on` → the persisted entry carries `applies_from`.
3. Done: swapping the two marker strings, and changing the retroactive
   `default=True` to `False`, each red a test.
