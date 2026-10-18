---
id: 2026-10-18-morning-recovery-presentation-rules-duplicated
title: The morning block and the recovery page each keep a private copy of the contributing-origin rule and the value formatter, and print normal ranges differently
status: open
importance: low
importance_why: Figures agree today, as verified on 2,567 real pages. But Req 2.3 and 2.5 agreement rests on two copies that no test compares.
effort: S
kind: inconsistency
area: workout-wellness, recovery, src/fitdocs/morning/block.py, src/fitdocs/recovery/view.py, src/fitdocs/recovery/page.py
created: 2026-10-18
surfaced_by: /kiro-validate-impl workout-wellness (judgment reviewer, controller-verified)
pinned_at: a0e4b92
resume_command: "do: lift the contributing-origin day set and the metric value formatter into one recovery-owned helper used by both morning/block.py and recovery/view.py+page.py, align the normal-range form, and add one test rendering the recovery page and a block for the same day [queue: .kiro/queue/2026-10-18-morning-recovery-presentation-rules-duplicated.md]"
context:
  - src/fitdocs/morning/block.py
  - src/fitdocs/recovery/view.py
  - src/fitdocs/recovery/page.py
  - .kiro/specs/workout-wellness/requirements.md
  - .kiro/specs/recovery/design.md
blocked_by: []
---

## What

Two presentation rules exist twice:

- **Contributing-origin days.** These are the day value, the 7-day window if a
  rolling mean exists, and the 60-day window if a baseline mean exists.
  - Morning: `src/fitdocs/morning/block.py:257-283` (`_row_source`).
  - Recovery: `src/fitdocs/recovery/view.py:288-299` (`collect`).
- **Value formatting.**
  - Morning: `block.py:290-298` (`_fmt`).
  - Recovery: `recovery/page.py:63-74` (`_value`).
  - Both call the shared `format_value` with the metric unit, so unit and
    precision agree.

The two surfaces also print a normal range differently:
- block: `52 to 66 ms`;
- recovery page: `Normal range: 58 ms to 86 ms` (`page.py:96`).

Req 2.5 asks for "the unit symbol and precision the recovery page uses", which
both satisfy. The form differs, though, and nothing pins whether it should.

## Why it matters

The figures come from one `Baselines` computation, so they cannot diverge.
Attribution and formatting can. A change to either copy would silently break
"the block and the recovery page show the same numbers" (Req 2.3) in its
presentation. No test renders both for the same day.

## Evidence

- The code locations above.
- A real-corpus check in a scratch copy at a0e4b92 found agreement today. An
  independent oracle, recomputing from `wellness/*.csv` without importing
  fitdocs, matched every figure of 2,465 non-empty blocks. It also matched the
  recovery page's 2026-10-17 HRV, resting HR and sleep figures.

## How to pick it up

1. Read the recovery design's public interface section. Decide whether
   `fitdocs.recovery` should export the origin-day set (e.g.
   `BaselineDay.contributing_days()`) and a `format_metric_value`.
2. Make both callers use them. Keep the morning boundary's allowed imports;
   check `tests/morning/test_boundary.py`.
3. Add one test: build a synthetic series, render the recovery page and a
   workout page for its last day, and assert equal printed figures and origins.
