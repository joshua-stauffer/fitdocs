---
id: 2026-10-18-morning-docs-claim-other-signals
title: The workouts skill says neither Morning-of "not refreshed" line needs athlete action, though the unexpected-error one exits 1 and recurs (docs "other wellness signals" half fixed)
status: open
importance: low
importance_why: The packaged skill understates one failure line (Req 11.5). The medium-importance half, a false claim in the wellness guide, is fixed.
effort: S
kind: docs
area: workout-wellness, src/fitdocs/skills/fitdocs-workouts/SKILL.md
created: 2026-10-18
surfaced_by: /kiro-validate-impl workout-wellness (judgment reviewer, confirmed by the controller)
pinned_at: 0f6b965
resume_command: "do: reword the fitdocs-workouts SKILL.md 'not refreshed' guidance so the unexpected-error line (exits 1, recurs while its cause persists) is not called no-action, and update any pinned literal [queue: .kiro/queue/2026-10-18-morning-docs-claim-other-signals.md]"
context:
  - src/fitdocs/skills/fitdocs-workouts/SKILL.md
  - src/fitdocs/cli.py
  - tests/morning/test_docs_morning.py
  - .kiro/specs/workout-wellness/requirements.md
blocked_by: []
---

## What

`src/fitdocs/skills/fitdocs-workouts/SKILL.md:141-143` says neither "Morning
of: not refreshed" line needs athlete action. But the
`<ExceptionType>: <message>` variant makes the run exit 1 (Req 8.8): the
handler at `cli.py:774-778` returns `True`, which the command folds into its
exit code. If the cause persists, it recurs on every run. "The next run
retries" understates it, which weakens Req 11.5 ("state which of them need
the athlete").

### Resolved half

This item first also covered `docs/wellness.md:324-325`, which said the block
shows "resting heart rate, HRV, **other wellness signals** and sleep",
contradicting Req 5.3 ("no wellness signal other than the baselined signals
and the sleep signals"). That sentence now reads "shows resting heart rate,
HRV and sleep from the normalized wellness series, and no other wellness
signal", and the literal in `tests/morning/test_docs_morning.py` moved with it
(branch `chore/q-morning-docs`, 2026-10-18). Only the SKILL wording remains.

## Why it matters

The skill is where the agent learns which report lines to raise with the
athlete. As written, it says the agent may ignore a failure line that can stay
red indefinitely.

## Evidence

- `SKILL.md:142-143`: "Neither `not refreshed` line needs athlete action; the
  next run retries."
- `cli.py:774-778`: the unexpected-error handler prints the line and returns
  `True` (failed).

## How to pick it up

1. In `SKILL.md`, split the two lines:
   - series unreadable: no action, the next run retries;
   - unexpected error: report it to the user if it repeats.
2. Update any SKILL literal pinned in `tests/morning/test_docs_morning.py` or
   `tests/test_agent_skill*.py`.
3. Done when `uv run pytest tests/morning tests/test_agent_skill*.py -q` is
   green.
