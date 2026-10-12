---
id: 2026-10-13-recovery-page-hr-benchmarks-and-source-display-names
title: "The recovery page shows no resting or maximum heart-rate benchmark and names sources by id, because the wellness facade does not export display names"
status: open
importance: low
importance_why: Both omissions are deliberate first-pass scope cuts that make the page less readable rather than wrong; nothing breaks, and the page is new.
effort: S
kind: gap
area: recovery, wellness-store, hr-derivation, src/fitdocs/benchmarks.py
created: 2026-10-13
surfaced_by: /kiro-spec-batch phase 12 (recovery spec, controller queue triage)
pinned_at: 86cdf14
resume_command: "do: after recovery and hr-derivation have landed, (a) add the resting and maximum heart-rate benchmark in force on the page's last day to the recovery page via BenchmarkSet.applicable, and (b) export SourceSpec display names through the wellness facade and show them beside the source id [queue: .kiro/queue/2026-10-13-recovery-page-hr-benchmarks-and-source-display-names.md]"
context:
  - .kiro/specs/recovery/design.md
  - .kiro/specs/recovery/requirements.md
  - .kiro/specs/wellness-store/design.md
  - .kiro/specs/hr-derivation/requirements.md
  - src/fitdocs/benchmarks.py
blocked_by: [recovery, hr-derivation]
---

## What

Two small additions the recovery spec left out on purpose, recorded together
because both change the same page section and both wait on specs that have not
landed.

1. **No resting or maximum heart-rate benchmark on the page.** Recovery
   plots the daily resting heart rate from the wellness series and its
   baseline, but the athlete's dated resting and maximum heart-rate benchmarks
   (the entries that drive heart-rate load) are not shown. Once hr-derivation
   lands those entries exist without the athlete typing them, and the page
   could show the one in force on its last day through
   `BenchmarkSet.applicable(kind, discipline=None, on=day)`.
2. **Sources appear as ids, not names.** The page names each shown source by
   its identifier and origins. The wellness facade exports neither
   `SourceSpec` nor `source_named`, so `SourceSpec.display_name` is
   unreachable from `fitdocs.recovery`, and the page prints, for example, the
   raw source id.

## Why it matters

(1) Without it, two numbers that describe the same athlete (a wellness
baseline and a load-pass benchmark) live on different pages and a difference
between them looks like a bug. hr-derivation's own requirements name recovery
as a downstream that "may plot the values". (2) A source id reads as an
implementation detail to a reader who never saw the registry.

## Evidence

Read at `86cdf14`.

- `.kiro/specs/recovery/design.md:41` -- Non-Goals: "Deriving or showing
  resting/max-HR benchmarks (`hr-derivation`)"; `:42-43` -- "source display
  names beyond the source id"; `:1406` -- "Sources named by id and origin; no
  display-name amendment".
- `.kiro/specs/recovery/requirements.md:142` -- the page names each shown
  source by "the source's identifier and the origins its values record".
- `.kiro/specs/wellness-store/design.md:564-567` -- `SourceSpec` carries
  `display_name`; `:1162-1169` -- the facade re-exports an exact list that
  includes neither `SourceSpec` nor `source_named`.
- `src/fitdocs/benchmarks.py:189-243` -- `BenchmarkSet.applicable(kind, *,
  discipline, on)`; `:49-50` the `MAX_HR_BPM` and `RESTING_HR_BPM` kinds;
  `:69-71` they are athlete-scoped, so `discipline` is `None`.
- `.kiro/specs/hr-derivation/requirements.md:36-39` -- recovery "may plot the
  values".

## How to pick it up

1. Land recovery and hr-derivation first. Read `recovery/design.md` § View
   (`:632`) and § Page (`:812`), the sections that assemble source rows, and
   `src/fitdocs/benchmarks.py:158-243`.
2. For (2), add the source-name export to wellness-store's facade as an
   amendment (`SourceSpec` or a small `source_display_name(source_id)`), then
   print the display name beside the id. Keep the id: it is what a
   `[wellness]` precedence setting uses.
3. For (1), decide the page text for "no entry in force" (absent, never a
   default), read the profile once in `engine`, and pass the two values into
   the pure `view`.

## Open questions

- Should (1) show only the entry in force on the last day, or the benchmark
  history as a step line? The first needs no new chart kind.
