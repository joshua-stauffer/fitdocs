---
id: 2026-10-02-sync-written-list-repeats-a-multi-file-page
title: fitdocs sync's Written report lists a page once per member file, so two pages made of four files read as Written 4 with each page listed twice
status: open
importance: low
importance_why: Cosmetic and pre-existing; the count and the list overstate how many pages were written, but no file is wrong.
effort: S
kind: bug
area: activity-identity, src/fitdocs/sync.py, src/fitdocs/cli.py
created: 2026-10-02
surfaced_by: /kiro-impl channel-merge
pinned_at: 5c41759
resume_command: "do: make sync's written list hold each page once (dedupe by document path in the run's outcome loop) and decide whether the Written count means pages or files; pin it with a two-pages-four-files case [queue: .kiro/queue/2026-10-02-sync-written-list-repeats-a-multi-file-page.md]"
context:
  - src/fitdocs/sync.py
  - src/fitdocs/cli.py
  - tests/fixtures/merge.py
  - tests/test_sync.py
  - .kiro/specs/activity-identity/design.md
blocked_by: []
---

## What
When several files of one workout are synced in one run, the page they form is
reported in `Written:` once per member file. Four files forming two pages print
`Written 4` and each page path twice.

## Why it matters
The summary is the athlete's only feedback from a run. "Written 4" for two pages
suggests four documents changed, and two identical lines look like a bug in the
tool.

## Evidence
Reproduced in this run, at 5c41759 and again with the source tree of 1e1fe8c
(origin/main at the start of this session; extracted with `git archive` into a
scratch directory, fed the same four files), so it predates channel-merge.
- Setup: a scratch data root holding `fitdocs.toml` with `[tiles]` and
  `enabled = false`; a source directory holding the four files from
  `tests/fixtures/merge.py` (`run_pair_fit_bytes()` and `ride_pair_fit_bytes()`,
  each written as two `.fit` files); `typer.testing.CliRunner().invoke(app,
  ["sync", <source>, "--out", <root>, "--no-prompt"])`.
- Output (identical on both trees), exit 0:

  ```
  Written  4
  Skipped  0
  Failed   0
  Warnings 2
  Written:
    workouts/2042-04-15-ride-0720.md
    workouts/2042-04-15-ride-0720.md
    workouts/2042-04-14-run-0720.md
    workouts/2042-04-14-run-0720.md
  ```

  and `workouts/` holds exactly two pages.
- Mechanism not traced. `src/fitdocs/sync.py:1478` appends `outcome.value`
  to `written` once per run item, and `:1306` appends once per file in the loop above it;
  `src/fitdocs/cli.py:1816-1829` prints `len(sync.written)` and each entry.
  The Warnings count, by contrast, is per page (2).

## How to pick it up
1. Run the recipe above; confirm `len(SyncReport.written)` is 4 with two
   distinct values.
2. Dedupe in the loop at `sync.py:1474-1480` (keep first-seen order) and decide
   whether `Written N` counts pages or files (the spec, `Req` text of
   activity-identity and workout-docs, is the place to look; this item did not
   check what it says).
3. Pin it with this fixture in `tests/test_sync.py` or the identity e2e suite,
   and check `regen`'s report (`cli.py:1754-1763`) for the same shape.
