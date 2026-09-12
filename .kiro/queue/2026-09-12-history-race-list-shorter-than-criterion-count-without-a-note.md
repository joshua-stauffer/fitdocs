---
id: 2026-09-12-history-race-list-shorter-than-criterion-count-without-a-note
title: The history page lists 12 race markers but reports 13 criterion points, with nothing on the page explaining the race that fell before series_start
status: open
importance: low
importance_why: Both numbers are correct by their own definitions (Req 1.8 confines markers to the drawable span; the criterion count reads every tagged page), but the page presents them side by side with no sentence bridging them, so the reader has to diff two lists to find the missing race.
effort: S
kind: gap
area: load-history, src/fitdocs/history/engine.py, src/fitdocs/history/page.py
created: 2026-09-12
surfaced_by: hand session tagging 13 historical races on the real data root, then running fitdocs history
pinned_at: e8416b5
resume_command: "do: when the marker set is a strict subset of the tagged race pages, have the history page state how many tagged races fall outside [series_start, series_end] and their dates, next to the Races list; pin it in tests/history"
context:
  - src/fitdocs/history/engine.py
  - src/fitdocs/history/page.py
  - .kiro/specs/load-history/requirements.md
blocked_by: []
---

## What

`src/fitdocs/history/engine.py` (the `markers = tuple(...)` comprehension and
the comment above it) drops a race page dated outside
`series.start..series.end` because the chart has no day index for it, per
Req 1.8. `criterion_points(scan.pages)` counts every tagged page. The
rendered page shows `Races:` 1–12 and, two sections later, `13 criterion
points … Earliest 2022-12-03`, and never says the two differ by design.

## Why it matters

The first real render (2026-09-12) hit this immediately: the maintainer's
earliest race (2022-12-03, a marathon) predates `series_start` 2022-12-29
because December 2022's files carry no distance stream and so no load. A
reader sees 12 vs 13 and suspects a lost tag.

## Evidence

- `history/training-load-history.md` on the real data root, 2026-09-12:
  frontmatter `series_start: "2022-12-29"`, `criterion_points: 13`; body
  `Races:` enumerates 12 entries starting `1. 2023-04-01 — Marathon`;
  "13 criterion points: 13 race, 0 test … Earliest 2022-12-03".
- `workouts/2022-12-03-run-1400.md` carries `effort: race`,
  `effort_distance_m: 42195`, `effort_time_s: 10619` and no `load_value`
  (its FIT has no distance stream; `fitdocs load` skipped it).

## How to pick it up

1. Read the marker comprehension and its comment in
   `src/fitdocs/history/engine.py`, and `page.py`'s Races rendering.
2. Add a one-line statement under the Races list when `len(markers) <`
   number of tagged race pages: how many, and which dates, lie outside the
   span. No fabricated result, no marker.
3. Done when the golden page for a fixture with one out-of-span race shows
   that line and the in-span-only fixture is byte-identical to today.
