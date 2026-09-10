---
id: 2026-09-10-load-channels-renders-a-retroactive-anchor-date-unexplained
title: The power and heart-rate channels render the anchor's measured_on into the document, so a retroactive anchor now shows a measurement date after the activity with nothing explaining it, while pace renders no anchor date at all
status: open
importance: medium
importance_why: A 2019 run scored against a prompt answer given in 2026 prints "ftp_measured_on: 2026-09-10" in its inputs table with no applies_from beside it; the athlete cannot tell a bug from their own declaration, and the prompt they answered said the activity would be marked as measured later — which the pace channel, running's default, does not do.
effort: S
kind: gap
area: load-channels, threshold-load, src/fitdocs/load/channels/power.py, src/fitdocs/load/channels/heart_rate.py, src/fitdocs/load/channels/pace.py, src/fitdocs/load/threshold/calculator.py
created: 2026-09-10
surfaced_by: /kiro-validate-impl training-load (Amendment 4, design + boundary dimension)
pinned_at: 52c473e
resume_command: "/kiro-spec-design threshold-load [queue: .kiro/queue/2026-09-10-load-channels-renders-a-retroactive-anchor-date-unexplained.md] Surface applies_from beside measured_on wherever an anchor date is rendered, for every channel"
context:
  - src/fitdocs/load/channels/power.py
  - src/fitdocs/load/channels/heart_rate.py
  - src/fitdocs/load/channels/pace.py
  - src/fitdocs/load/threshold/calculator.py
  - .kiro/specs/athlete-benchmarks/design.md
  - .kiro/queue/2026-08-27-anchor-provenance-missing-for-pace-and-hr.md
blocked_by: []
---

## What

athlete-benchmarks' design carries a revalidation trigger: any change to the
`[benchmarks]` shape → `load-channels` and `threshold-load` re-check their
benchmark reads. Amendment 1 added `Benchmark.applies_from`; threshold-load
was re-checked (Amendment 2: no code change needed for *resolution*), but
load-channels' **rendering** read was not. `power.py` and `heart_rate.py`
put the anchoring benchmark's `measured_on` into `inputs_used`
(`ftp_measured_on`, `lthr_measured_on`); `pace.py` emits no anchor date.
None of them knows `applies_from` exists.

## Why it matters

The whole point of Amendment 4 is that a historical activity now scores
against a benchmark measured later, by the athlete's declaration. The
document then says the anchor was measured after the activity and offers no
reason. For running — whose default channel is pace — it says nothing about
the anchor date at all, so the prompt's promise that in-between activities
are "marked as measured later" was true for no running document; that
clause was removed from the prompt on 2026-09-10 rather than left as an
unbacked claim.

## Evidence

- `src/fitdocs/load/channels/power.py` and `heart_rate.py`: `grep -n
  measured_on` shows the `inputs_used` entries (reviewer-reported lines 158
  and 281 at 52c473e); `src/fitdocs/load/channels/pace.py` has no
  `measured_on` in its `inputs_used`.
- `.kiro/specs/athlete-benchmarks/design.md` § Revalidation Triggers (the
  TOML-shape trigger, amended 2026-09-10 to name this item).
- Related open item: `2026-08-27-anchor-provenance-missing-for-pace-and-hr`
  (the anchor triple is missing for pace and heart rate); this item is the
  `applies_from` half of the same rendering question.

## How to pick it up

1. Read `build_result` in `src/fitdocs/load/threshold/calculator.py` and the
   three channels' `inputs_used` construction; read the anchor-provenance
   queue item, which will be fixed in the same place.
2. Decide the rendering: beside every anchor date, when the anchor carries
   `applies_from`, add "applied from <date> by the athlete's declaration";
   for pace, first give it an anchor date at all.
3. Done: the 7.4 end-to-end module's yes-scenario document shows the
   applies-from provenance for its selected channel, and threshold-load's
   Req 3.7/8.6 provenance triple is complete for all three channels.
