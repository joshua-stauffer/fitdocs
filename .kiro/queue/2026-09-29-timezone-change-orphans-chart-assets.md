---
id: 2026-09-29-timezone-change-orphans-chart-assets
title: A re-render under a different timezone keeps the page's filename but writes its charts under a new stem, leaving the old chart assets orphaned
status: open
importance: medium
importance_why: Every page whose local stem moves (a travel re-sync, or the DST fix the local-tz item asks for) leaves its old SVGs behind with nothing that ever removes them; activity-identity's cleanup runs only on a rename.
effort: S
kind: bug
area: activity-identity, workout-docs, src/fitdocs/sync.py, src/fitdocs/layout.py
created: 2026-09-29
surfaced_by: /kiro-spec-batch (Phase 8, activity-identity writer)
pinned_at: f500dc1
resume_command: "do: once activity-identity has landed, extend its rename-time asset cleanup to the keep-filename path in src/fitdocs/sync.py: when a re-render's computed stem differs from the stem of the chart assets the page's previous generated content linked, remove each previously linked assets/<name>.svg the new render does not write and no user-owned region links; test with one page synced under one tz and regenerated under another, asserting the old SVGs are gone and the page's links resolve"
context:
  - src/fitdocs/sync.py
  - src/fitdocs/layout.py
  - .kiro/specs/activity-identity/design.md
  - .kiro/specs/activity-identity/tasks.md
  - .kiro/queue/2026-09-12-local-tz-is-fixed-offset-of-run-time.md
blocked_by: [activity-identity]
---

## What
`sync.py` computes the stem from the activity's local start time in the
run's `tz` and then writes to the matched page's existing path, not to a path
built from that stem. The stem still names the chart assets
(`assets/<stem>-<chart>.svg`). So when `tz` differs from the run that last
wrote the page, the page keeps its filename, the regenerated charts land
under the new stem, the page's links move to them, and the previous SVGs
stay on disk with nothing linking them. Nothing in `sync.py` removes a file.
activity-identity (Req 6.4, task 4.2) adds removal of previously linked
assets only when a base change renames the page, and lists this case as a
non-goal ("today's behaviour, unchanged").

## Why it matters
Orphans accumulate silently in `workouts/assets/`, which the ownership
contract says fitdocs owns. The local-tz item's fix (a DST-aware zone) will
move the stem of every page recorded in the opposite DST half-year on its
first regen, so it would orphan one chart set per such page in one run
unless this lands first or with it.

## Evidence
- `src/fitdocs/sync.py:1269` `stem = doc_stem(activity, uid, tz, taken)`;
  `:1272` `target = match.path if match is not None else doc_path(data_root, stem)`;
  `:1298` `doc_stem=stem` into the render context.
- `src/fitdocs/layout.py:215-240` -- `doc_stem` formats the local date and
  `HHMM` in `tz`; `:252-261` -- `asset_rel_path` returns
  `assets/<stem>-<chart>.svg`.
- `grep -n "unlink\|rmtree" src/fitdocs/sync.py` -- no hits.
- `.kiro/specs/activity-identity/design.md:54-55` (non-goal);
  `tasks.md` task 4.2, "otherwise keep the filename (user renames and
  timezone changes as today)".

## How to pick it up
1. Read activity-identity's shipped cleanup (task 4.2: "remove every chart
   asset the previous generated content linked that the new render does not
   write and no preserved region links") and find how it learns the
   previously linked set.
2. Reproduce first: sync a synthesized run under one fixed-offset `tz`,
   regen under another, list `workouts/assets/` -- expect two chart sets.
3. Apply the same removal on the keep-filename path; done when the repro
   leaves one chart set and every link on the page resolves.

## Open questions
- Alternative the maintainer may prefer: keep the asset stem stable (derive
  it from the assets the page already links) instead of cleaning up after a
  stem change. That avoids churn but makes asset names diverge from the
  current local time; choose before implementing.
