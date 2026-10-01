---
id: 2026-10-01-chart-assets-named-by-computed-stem-collide-across-pages
title: A page whose filename the user changed still names its chart assets by the computed stem, so another activity with that stem overwrites them, and a rename cleanup can delete them
status: open
importance: medium
importance_why: One page silently shows another activity's charts, and the activity-identity rename cleanup (Req 6.4) adds a deletion path to a collision that already existed.
effort: M
kind: bug
area: activity-identity, workout-docs, src/fitdocs/sync.py, src/fitdocs/layout.py
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "/kiro-impl activity-identity [queue: .kiro/queue/2026-10-01-chart-assets-named-by-computed-stem-collide-across-pages.md] Name a page's chart assets so two pages can never share an asset path, then cover the rename cleanup"
context:
  - src/fitdocs/sync.py
  - src/fitdocs/layout.py
  - .kiro/specs/activity-identity/design.md
  - .kiro/specs/activity-identity/requirements.md
  - .kiro/queue/2026-09-29-timezone-change-orphans-chart-assets.md
blocked_by: []
---

## What
A page's chart assets are written as `assets/<stem>-<chart>.svg`, where `<stem>`
is the stem *computed* for the activity (`doc_stem`), not the page's own
filename. The collision rule only protects the page filename: `doc_stem` appends
a suffix when `workouts/<stem>.md` exists. If the user renames a page, its
computed stem is no longer occupied, so a different activity with the same
local date, sport and minute gets the plain stem and writes the same asset
filenames. Req 6.4's rename cleanup deletes "every chart asset the page's
previous generated content linked that the new render does not write", and
`_stale_assets` protects only links inside the renaming page's own user regions,
so it can delete an asset another page also links. Both defects share a root
cause with the sibling item on timezone changes: asset names are tied to the
computed stem, not to the page.

## Why it matters
The first effect is silent wrong output: page A (renamed by the user) now
displays activity B's hero chart. It needs a user rename plus a second activity of
the same sport starting in the same local minute (also the case that makes the
page-filename collision suffix apply at all). That is rare, but nothing reports
it when it happens.

## Evidence
Collision reproduced at `fc5c06d`; the deletion half is by reading only.
- `src/fitdocs/layout.py:252-261` `asset_rel_path` returns
  `assets/<stem>-<chart>.svg`; `src/fitdocs/sync.py:1941-1944` the stem is
  computed with `doc_stem(..., taken)` and `taken` tests only
  `workouts/<candidate>.md` (`:1933-1939`).
- Repro: two builder-style Garmin runs with the same start and different
  elapsed times (3000 s and 3400 s, so two sessions), via
  `tests.fixtures.identity.session_fit_bytes`. `fitdocs sync` the first; the page
  is `2043-11-14-run-0013.md` with `assets/2043-11-14-run-0013-hero.svg` (sha1
  `5b6fe191...`). `mv` the page to `my-renamed-run.md` (it still links
  `assets/2043-11-14-run-0013-hero.svg`, line 42). `fitdocs sync` the second:
  it writes a new page at the now-free `2043-11-14-run-0013.md` and the same
  asset path now has sha1 `d6483204...`. Page A's link resolves to B's chart.
- Deletion half (reported by reviewer subagent, not reproduced here):
  `src/fitdocs/sync.py:1755-1766` `_stale_assets` subtracts only the renaming
  page's own `inside` links, and `:2257` `_remove_stale_assets` unlinks the
  result.

## How to pick it up
1. Reproduce with the recipe above and write the e2e test first (two pages, one
   renamed, same computed stem; neither page's charts may change the other's).
2. Choose the naming rule (Open questions), then make `taken`-style protection
   cover assets as well: an asset name already linked by another page must not
   be written or removed by this page.
3. Read `2026-09-29-timezone-change-orphans-chart-assets` first and fix both
   with one rule if you can; that item's open question already proposes deriving
   the asset stem from the page.

## Open questions
- Derive the asset stem from the page's own filename (stable under timezone
  change and collisions, but asset names stop matching the activity's local
  time, and a user rename would then move every asset), or from the assets the
  page already links, or add a collision check for asset paths only? Decide
  together with the timezone item.
