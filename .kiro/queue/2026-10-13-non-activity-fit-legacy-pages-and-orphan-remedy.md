---
id: 2026-10-13-non-activity-fit-legacy-pages-and-orphan-remedy
title: "Workout pages already rendered from non-activity FIT files outlive wellness-store's guard, check cannot see them, and its orphaned_source remedy points their archived sources at a regen that will skip them"
status: open
importance: low
importance_why: Only an athlete who dropped a Garmin monitoring or sleep file into the inbox before the guard landed is affected; the junk page is harmless but permanent, and the remedy wording is a dead end rather than a hazard.
effort: S
kind: gap
area: wellness-store, audit, src/fitdocs/audit.py, docs/upgrading.md
created: 2026-10-13
surfaced_by: /kiro-spec-batch phase 12 (wellness-store spec, controller queue triage)
pinned_at: 86cdf14
resume_command: "do: after wellness-store task 4.1 lands, decide how an athlete finds and clears the workouts/undated-* pages and archived sources that non-activity FIT files left behind, and reword _REMEDY_RENDER_ORPHAN in src/fitdocs/audit.py (plus tests/test_audit.py:765-767 and docs/upgrading.md:118-124) so it no longer tells the athlete to regen an archived file the guard will skip [queue: .kiro/queue/2026-10-13-non-activity-fit-legacy-pages-and-orphan-remedy.md]"
context:
  - .kiro/specs/wellness-store/design.md
  - .kiro/specs/wellness-store/requirements.md
  - .kiro/specs/wellness-store/tasks.md
  - src/fitdocs/audit.py
  - tests/test_audit.py
  - docs/upgrading.md
blocked_by: [wellness-store]
---

## What

wellness-store adds a guard that keeps `.fit` files whose own header declares a
non-activity type (Garmin monitoring, sleep) off workout pages. It is not
retroactive, by design: Req 4.5 keeps every existing page and lets `regen`
keep rebuilding it. Two facts follow, and they are one problem because they
meet at the same athlete.

1. **A legacy page is invisible to `check`.** A monitoring or sleep file
   dropped before the guard became `workouts/undated-workout-<uid12>.md` plus
   an archived source. After the guard, `fitdocs check` has no way to flag
   such a page: the audit never opens a `.fit` file, so it cannot learn the
   file's declared type. The page stays until the athlete notices it.
2. **The `orphaned_source` remedy is misleading for the same files.** If the
   athlete deletes that junk page, its archived source becomes an
   `orphaned_source` finding whose remedy reads "run `fitdocs regen` to render
   it, or delete it if its page was removed on purpose". Once the guard is in,
   `regen`'s second part (archived files no page lists) parses the file,
   fails `is_activity_file`, skips it with a warning and writes no page. The
   finding then never clears by following the first half of the advice.

## Why it matters

The athlete is told to run a command that cannot fix the finding, and the
finding recurs on every `check`. The remedy's second half ("delete it") is the
right one for exactly this case but is framed as the exception. Separately, a
bounded number of meaningless `undated-` pages stay in the wiki with no
tool surfacing them.

## Evidence

Read at `86cdf14`.

- `src/fitdocs/audit.py:19-21` -- the module docstring: the audit "never opens
  a `.fit` source". `_orphan_findings` (`:492-522`) only globs
  `fit-archive/*.fit` by name (`:503`; "listed, never opened", `:495-496`).
- `src/fitdocs/audit.py:231-233` -- `_REMEDY_RENDER_ORPHAN` ("run `fitdocs
  regen` to render it, or delete it if its page was removed on purpose"),
  used at `:517`; pinned by `tests/test_audit.py:765-767`; repeated for users
  in `docs/upgrading.md:118-124`.
- `.kiro/specs/wellness-store/design.md:1267-1294` -- the guard sits in
  `_run_planned` right after `parse_fit(data)` (`src/fitdocs/sync.py:1446`) and
  covers a new file, "an archived file no page lists (`regen`'s second part)"
  and a `--force` re-process; `regen`'s page part never reaches it, so
  existing pages are untouched (Req 4.5, `requirements.md:170`).
- `.kiro/specs/wellness-store/research.md:29-30` and `:121-126` -- a scratch
  probe confirmed a `monitoring_b` file becomes an `undated-workout-<uid12>.md`
  page plus an archived source, "not covered by any test".
- `.kiro/specs/wellness-store/design.md:139-140` -- the spec itself records that
  `check` "never opens a source".
- `grep -rli "undated\|non-activity\|orphaned_source" .kiro/queue/*.md` finds
  no item on this subject.

## How to pick it up

1. Wait for wellness-store task 4.1 (`tasks.md:735`) to land, then confirm
   the claim: stage a monitoring file as a page and an archive entry (task
   4.1's own staging recipe works), delete the page, run `fitdocs check`, then
   `fitdocs regen`, then `check` again. The finding should survive the regen.
2. Reword `_REMEDY_RENDER_ORPHAN`, its pin in `tests/test_audit.py`, and the
   `docs/upgrading.md` paragraph so the delete option is not framed as only
   for a page "removed on purpose", and `regen`'s warning is mentioned as the
   sign the file is not an activity.
3. Decide, or ask the maintainer, about detection (see below). Done when an
   athlete following only `check`'s text reaches a clean tree.

## Open questions

- Is documentation enough for the legacy pages, or should something list them?
  Opening FIT headers in `check` would break the audit's read-only, no-`.fit`
  contract (`audit.py:19-21`, `:495-496`); a `regen` warning for
  a page whose every listed source is non-activity would stay inside the
  existing guard but changes Req 4.5's "keep rebuilding" behaviour.
