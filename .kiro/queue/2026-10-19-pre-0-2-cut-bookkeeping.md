---
id: 2026-10-19-pre-0-2-cut-bookkeeping
title: Before the 0.2 cut, tick the landed Phase 12 roadmap lines and plugin-api parent tasks, and close the queue items already resolved on main
status: open
importance: low
importance_why: Pure bookkeeping -- no user-visible effect -- but every stale box and resolved-but-open item is re-triaged by each release-readiness pass, as it was on 2026-10-19.
effort: S
kind: chore
area: .kiro/steering/roadmap.md, .kiro/specs/plugin-api/tasks.md, .kiro/queue
created: 2026-10-19
surfaced_by: 0.2 release-readiness triage (/kiro-queue over all 477 open items)
pinned_at: 4f1c1f4
resume_command: "do: with the maintainer's OK, tick roadmap.md Phase 12's wiki-contract and analytics-derived/analytics-index lines and plugin-api tasks.md parents 1-4, then /kiro-queue close each item listed under 'Likely resolved' after re-verifying it"
context:
  - .kiro/steering/roadmap.md
  - .kiro/specs/plugin-api/tasks.md
  - .kiro/specs/plugin-api/spec.json
  - .kiro/queue/README.md
blocked_by: []
---

## What

Three kinds of stale state that each release-readiness pass has to re-derive:

1. **Roadmap Phase 12 lines still `- [ ]` though every part has landed.**
   `.kiro/steering/roadmap.md` § Phase 12 Existing Spec Updates: the
   `wiki-contract` line (owned locations, five landers) and the
   `analytics-derived / analytics-index` line. The last outstanding part of
   each was workout-wellness's, and both are on `main`.
2. **plugin-api parent tasks unticked.** `.kiro/specs/plugin-api/tasks.md`
   parents `1.`, `2.`, `3.`, `4.` are `- [ ]` while every numbered subtask
   (1.2, 1.3, 2.1-2.4, 3.1, 3.2, 4.1, 4.2) is `- [x]`; `spec.json` `phase` is
   still `tasks-generated`.
3. **Open queue items that look resolved on `main`** (list below).

## Why it matters

The 2026-10-19 pass spent reviewer time on each of these. Left as is, the next
pass (0.3) repeats it, and "spec has open tasks" reads as unfinished work in
`/kiro-spec-status`.

## Evidence

Roadmap (verified at `4f1c1f4`):
- workout-wellness's contract half: `b042e10 feat(workout-wellness): publish
  refreshed-region ownership contract`; `docs/ownership-contract.md:382`
  "The `morning` region is refreshed rather than preserved".
- workout-wellness's index half: `src/fitdocs/index/fingerprint.py:46` skips
  `contract.PRESERVED_REGIONS + contract.REFRESHED_REGIONS`.
- The other four wiki-contract landers are already marked complete/implemented
  inside the same roadmap line.

plugin-api: `grep -nE '^\s*- \[[ x]\]\*? [0-9]+\.[0-9]+' .kiro/specs/plugin-api/tasks.md`
lists ten subtasks, all `[x]`; `grep -nE '^- \[ \]'` lists only the four parents.

Likely resolved -- **verified in this run**:
- `2026-07-30-package-description-undersells-the-tool`: `pyproject.toml:4`
  now reads "Turn .fit files into rich per-workout markdown documents, with
  pluggable training-load calculation."
- `2026-07-27-cli-test-doc-pick-unordered-glob`: the only remaining
  `glob("*.md"))` in `tests/test_cli.py` is the hazard docstring; tests use
  `_only_doc` (`tests/test_cli.py:116`).
- `2026-07-26-spec-status-arguments-path-interpolation`:
  `.claude/skills/kiro-spec-status/SKILL.md:19-27` takes the first token only
  and ignores `[queue: ...]`. (Sibling `2026-07-27-spec-status-empty-arguments-unrouted` stays open.)

Likely resolved -- **reported by reviewer subagents, not re-verified here**:
- `2026-07-29-task-13-1-undercounts-np-migration-sites` (task 13.1 ticked, note names both NP tests).
- `2026-07-30-fourth-choice-search-basis-not-web-remediated` (item self-describes as moot; constant gone).
- `2026-09-12-derived-entry-change-detection-includes-applies-from`
  (`src/fitdocs/performance/engine.py:450-465` second comparison, from `2a512ea`; code-read only, no test pins it).
- `2026-10-18-inbox-move-disposition-and-connector-deliveries`
  (`connectors/delivery.py:307-308` settles archived-but-absent; remaining gap is a test and a docs sentence).

Partly resolved -- narrow, do not close:
- `2026-08-22-readme-ownership-section-test-inspects-the-wrong-heading`: one
  `## Ownership` heading now (`README.md:207`); a per-link pin is still open.
- `2026-09-18-config-error-output-surface-wrap-and-stderr`: wrap half fixed
  (`soft_wrap=True`, `src/fitdocs/cli.py:551,581`); the stderr test half is open.
- `2026-10-02-connectors-page-delivery-and-lookback-inaccuracies`: point 1
  fixed (`docs/connectors.md:33`); points 2-3 open.
- `2026-10-17-site-copy-lags-main`: fixed on `origin/chore/site-copy-0-2`
  (PR #1, draft), which itself moves the item to `closed/`; resolves when that
  PR merges after 0.2.0 is on PyPI. No action here.

## How to pick it up

1. Ask the maintainer before touching `roadmap.md` -- ticking roadmap lines is
   their call, and `/kiro-queue` must not edit it.
2. Tick plugin-api's four parents; consider `phase: implementation-complete`
   in `spec.json` (check what `/kiro-spec-status` expects first).
3. For each "Likely resolved" item, re-run its own check, then
   `/kiro-queue close <id>` (the skill moves it to `closed/` with a
   `## Resolution`). For each "Partly resolved" item, narrow its `What` to the
   open half instead of closing.

Done when the roadmap and plugin-api boxes match what is on `main` and every
item above is either closed or narrowed.
