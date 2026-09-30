---
id: 2026-09-30-running-dynamics-fixture-realism
title: Stryd and native-dynamics fixtures carry internal inconsistencies that show on their golden pages
status: open
importance: low
importance_why: Goldens show a lap total that disagrees with moving time and an average pace faster than the best pace, which readers and later reviewers will mistake for defects.
effort: S
kind: chore
area: running-dynamics fixtures, tests/fixtures/builder.py, tests/render/golden_docs
created: 2026-09-30
surfaced_by: /kiro-impl running-dynamics
pinned_at: 8b07b9f
resume_command: "do: make the running-dynamics fixtures internally consistent (lap elapsed, starting distance, distinct timer vs elapsed) and regenerate their two goldens"
context:
  - tests/fixtures/builder.py
  - tests/fixtures/test_builder.py
  - tests/render/golden_docs/stryd_run.md
  - tests/render/golden_docs/run_native_dynamics.md
  - .kiro/specs/running-dynamics/design.md
blocked_by: []
---

## What
Three fixture artefacts, all from tests/fixtures/builder.py, the running-dynamics builders:
- **Stryd laps.** Each lap records `total_elapsed_time` = end - start + 1 (11 s) against a 10 s timestamp span (`_stryd_laps`; the same convention appears in the older run fixture at ~245-246). The stryd_run page's Device laps Total therefore reads 0:44 beside a 0:43 session.
- **native-dynamics distance.** The distance starts at 3.1 m at record 0, so the run_native_dynamics page shows average pace 4:55 /km faster than best pace 4:59 /km.
- **Stryd timer and elapsed.** Both totals are 43 s, so no page-level test can tell moving time from elapsed time.

## Why it matters
Both goldens look wrong to a reader, and every later reviewer re-investigates them. The equal timer/elapsed totals leave the page-level swap pinned only by older unit tests.

## Evidence
- `grep -n "Total\|Moving time" tests/render/golden_docs/stryd_run.md` shows `**Total** | – | 0:44` against Moving time 0:43.
- The native golden's pace line reads `4:55 /km (best 4:59 /km)`.
- The 4.1 and 4.2 reviewer subagents traced the causes to the builder lines named above; the traces were not re-run here.
- design.md § Supporting References says only that the session totals are "recorded", so matching timer and elapsed is not a spec violation.

## How to pick it up
1. In builder.py, make each Stryd lap's elapsed equal its span, start the native-dynamics distance at 0, and give the Stryd session a timer total below elapsed (the three-record pause is the natural gap).
2. Keep every fixture self-test in tests/fixtures/test_builder.py true. Some pin these exact values; update them deliberately.
3. Regenerate only the stryd_run and run_native_dynamics goldens with `uv run python -m tests.render.test_golden_docs`, and check no other golden moved.
4. Consider tightening tests/test_running_dynamics_e2e.py's 6.3 test to separate moving from elapsed once the totals differ.
