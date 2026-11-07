---
id: 2026-11-07-index-refresh-with-open-reader-reports-needs-rebuild
title: "An index refresh with a read-only session open in the same process reports needs_rebuild"
status: open
importance: low
importance_why: A misleading message with no damage; no command does this today, and post-templates plans its order to avoid it.
effort: S
kind: bug
area: analytics-index, src/fitdocs/index/refresh.py
created: 2026-11-07
surfaced_by: "/kiro-discovery post-templates (viability probe)"
pinned_at: c310795a
resume_command: "do: make refresh_after_command report an open reader in the same process as itself, not as needs_rebuild [queue: .kiro/queue/2026-11-07-index-refresh-with-open-reader-reports-needs-rebuild.md]"
context:
  - src/fitdocs/index/refresh.py
  - src/fitdocs/query/command.py
  - .kiro/specs/post-templates/brief.md
blocked_by: []
---

## What
`refresh_after_command` called while a `QuerySession` is still open in the same
process returns `Outcome.NEEDS_REBUILD`, whose message is DuckDB's "Can't open a
connection to same database file with a different configuration". The index is
fine. The athlete would be told to rebuild an index that needs no rebuild.

## Why it matters
No command hits this today: `run_dashboards` closes its session in `finally`, and the
dashboard pass runs last. Any new pass that reads the index and then refreshes it can
hit it. `post-templates` plans to close the session first, so the fault only appears if
that order is broken, and it then sends the reader to a rebuild of several minutes.

## Evidence
- `src/fitdocs/index/refresh.py:117-119` maps every fault that isn't the lock or a missing
  file to `Outcome.NEEDS_REBUILD`.
- The post-templates viability probe (2026-11-07, DuckDB 1.5.6 and 1.2.0, synthetic data)
  observed the outcome and the message above. The probe lived in a session scratch directory
  and was not kept; to reproduce it, call `open_session` and then `refresh_after_command`
  without closing the session.

## How to pick it up
1. Reproduce it with a small in-process test on a tiny built index.
2. Read how the fault is classified before `refresh.py:117`, and decide whether this case
   should be its own `FaultKind`, reported as busy rather than as a rebuild.
3. Done when the outcome no longer tells the reader to rebuild, with a test that pins it.
