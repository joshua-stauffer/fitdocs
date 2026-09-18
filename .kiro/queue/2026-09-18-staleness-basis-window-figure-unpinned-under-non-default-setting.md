---
id: 2026-09-18-staleness-basis-window-figure-unpinned-under-non-default-setting
title: The non-retroactive staleness basis quotes "configured window N days" with no test that N is read from the reading rather than hardcoded, and d26b682 claimed it was already pinned
status: open
importance: low
importance_why: The verdict is proven threaded and the production line is correct today; only the athlete-visible basis figure under a non-default benchmark_staleness_days is unpinned, but the closure claim in d26b682's commit message is false and tasks.md still says "queued" when nothing was.
effort: S
kind: gap
area: activity-qa-flags, src/fitdocs/load/qa/flags.py, tests/load/qa/test_flags.py, .kiro/specs/activity-qa-flags/tasks.md
created: 2026-09-18
surfaced_by: /kiro-validate-impl activity-qa-flags (post-merge pass, 2026-09-18; cross-task integration reviewer, mutation-confirmed by the controller)
pinned_at: e16acc3
resume_command: "do: in tests/load/qa/test_flags.py add one case (mirroring test_drift_detail_reference_pct_reflects_non_default_setting at :449) that calls evaluate_flags with a non-default staleness_window_days (not 90) on a CURRENT or STALE anchor and asserts 'configured window <that N> days' appears in the staleness flag's detail; then rewrite the '3.1 low-importance residual' Implementation Note in .kiro/specs/activity-qa-flags/tasks.md (:619-626) to say the drift half was closed by d26b682 and the staleness half by this item"
context:
  - src/fitdocs/load/qa/flags.py
  - tests/load/qa/test_flags.py
  - .kiro/specs/activity-qa-flags/tasks.md
  - .kiro/specs/activity-qa-flags/design.md
blocked_by: []
---

## What

`flags.py`'s `_staleness_detail` builds the non-retroactive basis as

```python
f"{reading.age.age_days} day(s) old (configured window "
f"{reading.age.window_days} days)."
```

(`src/fitdocs/load/qa/flags.py:199-204`). No test proves the second figure is
read from `reading.age.window_days` rather than being a literal. Every
assertion on that text in `tests/load/qa/test_flags.py` (:486, :525, :553,
:573) reads `configured window 90 days`, and `_default_kwargs` (:153) passes
`staleness_window_days=90` explicitly, so a hardcoded `90` satisfies them
all. The one test that varies the window
(`test_staleness_window_days_argument_is_threaded_through`, :736-750, windows
10 and 365) asserts the *verdict* only, never `.detail`.

The drift check had the identical gap; d26b682 closed that half with
`test_drift_detail_reference_pct_reflects_non_default_setting` (:449) and
its commit message states "the parallel staleness-window figure was already
pinned". It was not. tasks.md's "3.1 low-importance residual" note
(:619-626) still reads "(queued, not fixed here)" for both halves; neither
half was ever queued, and the drift half is now fixed.

## Why it matters

The basis is athlete-visible document text whose whole purpose (Req 1.4) is
to let a reader disagree with the threshold without re-running the tool. A
future edit that hardcodes the figure would ship a wrong window on every
athlete whose `[load] benchmark_staleness_days` is not 90 and nothing in the
suite would go red. Separately, a commit message asserting a pin that does
not exist is the "prose is not evidence" class `change-protocol.md` warns
about: the next editor will trust it.

## Evidence

- `src/fitdocs/load/qa/flags.py:199-204` — the format line.
- `grep -n "configured window" tests/load/qa/test_flags.py` → :484, :486,
  :525, :553, :573, all `90 days`; `_default_kwargs` default at :153 is 90.
- Mutation run by the validating controller at e16acc3 (file restored via
  `cp` afterwards, tree verified clean): replace the second f-string with the
  literal `f"90 days)."` →
  `uv run pytest tests/load/qa/test_flags.py tests/load/qa/test_feature_e2e.py tests/load/qa/test_staleness.py tests/load/threshold/test_calculator.py -q -p no:cacheprovider`
  → `96 passed`. Control: hardcode `5.0` for `{reading.reference_pct:.1f}`
  at `flags.py:170` → `1 failed` (`test_drift_detail_reference_pct_reflects_non_default_setting`), `28 passed` —
  the probe technique discriminates; the staleness figure is the one that
  is not pinned.
- `tests/load/qa/test_feature_e2e.py:230` compares `flag.detail` against the
  rendered document — both come from the same function, so it cannot catch a
  literal either.
- `git log -1 --format=%B d26b682` — "the parallel staleness-window figure
  was already pinned".
- `.kiro/specs/activity-qa-flags/tasks.md:619` — "(queued, not fixed
  here)"; `grep -ln "window_days\|configured window" .kiro/queue/*.md` before
  this item → no match.

## How to pick it up

1. Open `tests/load/qa/test_flags.py:449` and read the drift case; copy its
   shape for staleness using `_benchmark(ACTIVITY_DATE - timedelta(days=50))`
   and `staleness_window_days=365` (CURRENT) or `=10` (STALE).
2. Assert `"configured window 365 days"` (or 10) is in the staleness flag's
   `.detail`. Re-run the mutation above; the new test must be the sole
   failure.
3. Fix the tasks.md note so it no longer claims the residual is queued and
   unfixed. Done means: mutation reds, note accurate, suite green.
