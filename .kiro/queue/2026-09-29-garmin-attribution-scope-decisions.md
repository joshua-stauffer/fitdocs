---
id: 2026-09-29-garmin-attribution-scope-decisions
title: Three Garmin-attribution scope decisions intervals-connector left to the maintainer -- chart images, aggregate pages, model display names
status: open
importance: medium
importance_why: The attribution exists to meet intervals.icu's API terms and Garmin's API Brand Guidelines; two of the three gaps are places the guidelines' own wording reaches that the shipped design will not.
effort: S
kind: spec-work
area: intervals-connector, src/fitdocs/render/, src/fitdocs/history/, src/fitdocs/plans/
created: 2026-09-29
surfaced_by: /kiro-spec-batch (Phase 8, intervals-connector writer)
pinned_at: f500dc1
resume_command: "/kiro-spec-requirements intervals-connector [queue: .kiro/queue/2026-09-29-garmin-attribution-scope-decisions.md] Decide chart-image stamping, aggregate-page attribution and model display names for the Garmin attribution"
context:
  - .kiro/specs/intervals-connector/design.md
  - .kiro/specs/intervals-connector/research.md
  - .kiro/specs/intervals-connector/requirements.md
blocked_by: []
---

## What
intervals-connector's design records three questions it did not decide:
(a) **chart images** -- Garmin's guidelines ("Visual and social media") ask
for the attribution "in every image" of exported visual assets; the design
treats the page as the data view (the line sits under the title, above every
chart) and does not stamp the SVGs; (b) **aggregate pages** -- the
training-history page and block pages derive from many workouts, some
Garmin-recorded, and the guidelines' "Combined or derived data" section would
ask for a contributing-source line there; the spec covers workout pages only;
(c) **model display names** -- the page shows the SDK's product identifier
(e.g. `edge_1040`) verbatim; a display-name table would read better and is
not in the SDK. Task 2.1 also makes the same SDK identifiers the device names
in the devices table.

## Why it matters
(a) and (b) are decisions about compliance scope, not polish: if the
maintainer reads the guidelines as binding on charts or aggregates, the
shipped attribution is incomplete, and stamping SVGs touches every chart
renderer and golden, which is cheaper to decide before implementation.

## Evidence
- `.kiro/specs/intervals-connector/design.md` § "Open Questions / Risks"
  (~:1129-1141 at this pin; the file was being edited concurrently).
- `.kiro/specs/intervals-connector/research.md:126` -- "in every image".
- `.kiro/specs/intervals-connector/tasks.md` 2.1 (~:128-150) -- SDK-resolved
  names `edge_1040`, `hrm_pro`.

## How to pick it up
1. Read the design's Open Questions and research.md's guideline notes
   (~:101-130).
2. Put (a), (b), (c) to the maintainer as three yes/no decisions.
3. Record each answer in intervals-connector's requirements (amendment if
   the spec has been implemented); a "no" closes that part with its reason.

## Open questions
- All three are maintainer decisions; no picking-up session can make them.
