---
id: 2026-10-02-sync-drain-path-exit-order-and-plugin-placement-unpinned
title: Three behaviours of `fitdocs sync`'s no-source drain are unpinned on the sync side -- exit 1 on a load-pass failure, [plugins] errors winning over inbox-preflight errors, and plugin load errors printing after the drain summary
status: open
importance: medium
importance_why: The drain body is now a helper shared by `sync` and `pull --sync`; a change made for one caller can silently alter `sync`'s exit code or error order, and those are what scripts and the packaged skill depend on.
effort: S
kind: gap
area: inbox, connectors, src/fitdocs/cli.py, tests/test_cli_sync_inbox.py
created: 2026-10-02
surfaced_by: /kiro-impl connectors
pinned_at: ad985b3
resume_command: "do: add three sync-side tests to tests/test_cli_sync_inbox.py -- no-source drain exits 1 when only the load pass fails, a malformed [plugins] plus malformed [inbox] reports the [plugins] error, and the plugin-load-error block is asserted to start after the drain table -- each proven by the mutation named in .kiro/queue/2026-10-02-sync-drain-path-exit-order-and-plugin-placement-unpinned.md"
context:
  - src/fitdocs/cli.py
  - tests/test_cli_sync_inbox.py
  - tests/connectors/test_cli_connectors.py
  - .kiro/specs/inbox/design.md
  - .kiro/specs/connectors/design.md
blocked_by: []
---

## What
Connectors task 1.4 moved `sync_command`'s no-source branch verbatim into
`_run_drain_passes` (`src/fitdocs/cli.py:482-546`) so `pull --sync` can chain
the identical drain; `sync_command` now calls it with `command="sync"`
(`:470-479`). Three properties of that path have no test from the `sync` side:

1. **Exit 1 on a load-pass failure.** The helper returns
   `drain failures or bool(load_report.failures) or plan_report.failed`
   (`:541-545`). Only `pull --sync` pins the load term
   (`tests/connectors/test_cli_connectors.py:2515`
   `test_pull_sync_chained_load_failure_exits_1`). No test in
   `tests/test_cli_sync_inbox.py` makes the load pass fail on a no-source
   `sync` (grep for `apply_load`/`_run_load_pass` there: none).
2. **[plugins] before the inbox preflight.** `_plugin_report` (`:505`) runs
   before `_inbox_preflight` (`:514`), so a malformed `[plugins]` table is
   the reported configuration error when both tables are malformed. No
   two-violation fixture pins which wins.
3. **Plugin errors after the drain summary.**
   `test_drain_reports_plugin_load_errors_after_the_drain_summary`
   (`tests/test_cli_sync_inbox.py:810-833`) asserts only that the plugin
   file name and message appear in the output and exit is 0; it never
   compares positions, though its name and the `sync` docstring
   (`cli.py:408-410`, "printed after the summaries") promise "after".

## Why it matters
`fitdocs sync` is the routine command and the packaged skill's fallback
(`pull --sync` with no connectors "is exactly `fitdocs sync --no-prompt`").
With the body shared, the `sync` side is protected only by tests written for
`pull`; a future edit to `sync_command` (e.g. ignoring the helper's return
value for one path) or a reorder inside the helper passes the suite.

## Evidence
- Code positions as cited above, read at `ad985b3`.
- Mutations reported by the task 1.4 and 5.3 reviewer subagents (not re-run in
  this session): dropping `or bool(load_report.failures)` from the helper was
  green on the sync suite at base `e8839a8` and on the branch (it is now
  caught only by the pull-side test above); swapping the `_plugin_report` and
  `_inbox_preflight` calls was green on base and branch; moving
  `_report_plugin_errors` before `_report_drain` was green.

## How to pick it up
1. Read `cli.py:378-546` and the canned-`DrainReport` helpers at the top of
   `tests/test_cli_sync_inbox.py` (`:90-115`).
2. Add: (a) a no-source `sync` whose drain succeeds and whose load pass is
   patched to report one failure -- assert exit 1; (b) a `fitdocs.toml` with
   both a malformed `[plugins]` and a malformed `[inbox]` -- assert exit 2 and
   that the message names `[plugins]` and not `[inbox]`; (c) in the existing
   plugin-error test, assert the index of the plugin file name is greater
   than the index of the drain table's title.
3. Run each named mutation above and confirm each new test goes red.
