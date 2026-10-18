---
id: 2026-10-18-morning-docs-claim-other-signals
title: The wellness guide says the Morning Of block shows "other wellness signals", which Req 5.3 forbids, and a test pins the false sentence
status: open
importance: medium
importance_why: The published guide misstates what every workout page shows. Req 11.4 ("what it shows") is false as shipped, and a test locks the error in.
effort: S
kind: docs
area: workout-wellness, docs/wellness.md, src/fitdocs/skills/fitdocs-workouts/SKILL.md
created: 2026-10-18
surfaced_by: /kiro-validate-impl workout-wellness (judgment reviewer, confirmed by the controller)
pinned_at: a0e4b92
resume_command: "do: drop 'other wellness signals' from the Morning Of sentence in docs/wellness.md and its pinned literal in tests/morning/test_docs_morning.py; reword the SKILL.md 'not refreshed' guidance so the unexpected-error line is not called no-action [queue: .kiro/queue/2026-10-18-morning-docs-claim-other-signals.md]"
context:
  - docs/wellness.md
  - tests/morning/test_docs_morning.py
  - src/fitdocs/skills/fitdocs-workouts/SKILL.md
  - .kiro/specs/workout-wellness/requirements.md
blocked_by: []
---

## What

`docs/wellness.md:324-325`: "The `Morning Of` block before Training Load shows
resting heart rate, HRV, **other wellness signals** and sleep". That contradicts
three things:
- Req 5.3: "The block shall show no wellness signal other than the baselined
  signals and the sleep signals".
- The spec's out-of-scope list: weight, SpO2, respiration, steps and stress
  stay on the recovery page.
- The code, which shows only resting HR, HRV (SDNN/rMSSD) and the sleep rows.

`tests/morning/test_docs_morning.py:29-30` pins the sentence word for word, so
correcting the doc turns that test red until its literal changes too.

There is also a smaller wording defect in the same documentation set.
`src/fitdocs/skills/fitdocs-workouts/SKILL.md:141-143` says neither "Morning
of: not refreshed" line needs athlete action. But the
`<ExceptionType>: <message>` variant makes the run exit 1 (Req 8.8,
`cli.py:776-779`), and if the cause persists it recurs on every run. "The next
run retries" understates it, which weakens Req 11.5 ("state which of them need
the athlete").

## Why it matters

The guide is where the athlete and the agent learn what the block shows. As
written, it promises signals that never appear, and it says the agent may
ignore a failure line that can stay red indefinitely.

## Evidence

- `docs/wellness.md:325`: `HRV, other wellness signals and sleep from the normalized wellness series.`
- `tests/morning/test_docs_morning.py:29-30` pins that exact string.
- Real-corpus scratch rebuild, 2026-10-18 at a0e4b92 (2,567 real pages): the
  only row labels in any block were Resting HR, HRV (SDNN), Sleep, Deep sleep,
  Light sleep, REM sleep and Awake in sleep.
- `SKILL.md:142-143`: "Neither `not refreshed` line needs athlete action; the
  next run retries."

## How to pick it up

1. Edit the sentence at `docs/wellness.md:324-325`, e.g. "shows resting heart
   rate, HRV and the previous night's sleep". Change the parametrized literal
   in `tests/morning/test_docs_morning.py` to match.
2. In `SKILL.md`, split the two lines:
   - series unreadable: no action, the next run retries;
   - unexpected error: report it to the user if it repeats.

   Update any SKILL literal pinned in `tests/morning/test_docs_morning.py` or
   `tests/test_agent_skill*.py`.
3. Done when `uv run pytest tests/morning tests/test_agent_skill*.py -q` is
   green and `grep -n "other wellness signals" docs/` finds nothing.
