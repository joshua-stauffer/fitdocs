---
id: 2026-11-01-publish-midrun-ledger-save-traceback
title: "A mid-run ledger save failure surfaces as a traceback from fitdocs publish --yes"
status: open
importance: medium
importance_why: Breaks the documented 0/1/2/130 exit contract on a real failure (disk full, permissions); posting stays safe.
effort: S
kind: bug
area: publish-core, src/fitdocs/publish/engine.py, src/fitdocs/publish/ledger.py, src/fitdocs/cli.py
created: 2026-11-01
surfaced_by: "/kiro-validate-impl publish-core"
pinned_at: dd9fcaa1
resume_command: "do: catch PublishLedgerError around run_publish in cli.publish_command, print the fitdocs message naming the file, exit non-zero per a ruling on the code, and test it [queue: .kiro/queue/2026-11-01-publish-midrun-ledger-save-traceback.md]"
context:
  - src/fitdocs/publish/engine.py
  - src/fitdocs/publish/ledger.py
  - src/fitdocs/cli.py
  - .kiro/specs/publish-core/design.md
blocked_by: []
---

## What
`save_ledger` wraps `OSError` as `PublishLedgerError`
(`src/fitdocs/publish/ledger.py:281-282`). A mid-run save from `engine._save`
(`engine.py` ~381-383) is uncaught, so `fitdocs publish --yes` prints a
traceback; `cli.publish_command` catches only `KeyboardInterrupt`. The design's
error table (~1361) has no row for it.

## Why it matters
It breaks the 0/1/2/130 exit contract. Posting stays safe: the pre-request save
fails before anything is sent, and the id is reused next run.

## Evidence
The cited lines; reproduce by making the ledger path unwritable mid-run.

## How to pick it up
1. Catch `PublishLedgerError` around `run_publish` in `cli.publish_command`.
2. Print the message naming the file; choose the exit code (needs a ruling) and add the design table row.
3. Add a CLI test.

## Open questions
Which exit code (1 or 2) a ledger failure should return.
