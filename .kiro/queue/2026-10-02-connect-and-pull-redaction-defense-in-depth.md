---
id: 2026-10-02-connect-and-pull-redaction-defense-in-depth
title: Three secret-handling gaps in connect and pull -- report subjects and ledger ids are never redacted, a login's tokens are not registered with the redactor, and connect's no-data-root sentinel is a cwd-relative path
status: open
importance: low
importance_why: Each needs a misbehaving or unusual connector (a token in a remote id, a crash that echoes a token, a write during connect) to matter; no shipped connector triggers any, but intervals-connector will be the first network one.
effort: S
kind: gap
area: connectors, src/fitdocs/connectors/pull.py, src/fitdocs/connectors/connect.py, src/fitdocs/cli.py
created: 2026-10-02
surfaced_by: /kiro-impl connectors
pinned_at: ad985b3
resume_command: "/kiro-impl connectors [queue: .kiro/queue/2026-10-02-connect-and-pull-redaction-defense-in-depth.md] Redact PullNote subjects, register a login's tokens with the redactor before saving, and make connect's no-data-root sentinel unwritable"
context:
  - src/fitdocs/connectors/pull.py
  - src/fitdocs/connectors/connect.py
  - src/fitdocs/connectors/ledger.py
  - src/fitdocs/cli.py
  - .kiro/specs/connectors/design.md
  - .kiro/specs/connectors/tasks.md
blocked_by: []
---

## What
1. **Subjects are printed raw.** `PullNote` is `subject` + `detail`; design.md
   types only `detail` as redacted (`design.md:1236-1238`). `run_pull` builds
   notes with `subject=note.subject` (a connector's `ListingDeferral.subject`)
   and `subject=activity.remote_id` (`src/fitdocs/connectors/pull.py:454`,
   `:466`, `:474`, and every later failed/skipped site), and `_report_pull`
   prints `note.subject` unchanged (`src/fitdocs/cli.py:1247`). The same
   remote ids are written to the ledger raw
   (`src/fitdocs/connectors/ledger.py`, `LedgerEntry.remote_id`). Task 4.4
   says "Every reported string passes the run's redactor"
   (`.kiro/specs/connectors/tasks.md:491`).
2. **Login tokens are not registered.** `run_connect`'s LOGIN branch
   (`src/fitdocs/connectors/connect.py:186-201`) receives `tokens` from the
   connector and saves them without `redactor.add(...)`; the pull's renewal
   path does register them (`pull.py:412-414`). If `store.save` or anything
   after `login` raises with a token in its text, the CLI's catch-all
   (`cli.py:911-919`) redacts with a redactor that does not know the token.
3. **Relative sentinel.** `_NO_DATA_ROOT = Path("connect-has-no-data-root")`
   (`connect.py:60`, used `:160`) is relative, so a connector that wrongly
   writes under `session.data_root` during `connect` creates that directory
   in the current working directory -- which may be the data root, the case
   Req 5.9 ("connect writes nothing under the data root") forbids.

## Why it matters
A service whose activity ids embed a signed token, or a connector that puts a
URL in a deferral subject, would print and persist it. Each fix is a line or
two; together they make "no secret in any output" hold without relying on
connector good behaviour.

## Evidence
Lines above read at `ad985b3`. `grep -n "redactor.add" src/fitdocs/connectors/connect.py`
returns nothing. Items 1 and 3 were first reported by the task 4.4/4.5 and
feature-validation reviewer subagents, item 2 by the task 5.1 reviewer; the
code paths were re-read in this session, no leaking connector was run.

## How to pick it up
1. In `run_pull`, pass each subject through `redactor.redact` where a
   `PullNote` is built (or in one constructor helper), keeping the instance
   name and inbox-relative paths unchanged. Decide (open question) whether
   the ledger keeps raw ids -- it must, to recognise them next run -- and say
   so in design.md's PullNote/ledger text.
2. In `run_connect`'s LOGIN branch, `redactor.add` every token value before
   `store.save`, mirroring `pull.py:412-414`.
3. Make the sentinel absolute and non-existent (e.g. under the credentials
   directory's parent with a reserved name), or have `ConnectorSession`
   refuse `data_root` access during connect.
4. Pin each with a fixture that *would* leak: a remote id containing a
   registered secret, a store whose `save` raises with the token in its
   message, a connector that writes to `session.data_root` during login.

## Open questions
- Should a remote id that contains a registered secret be refused rather than
  redacted? Redacting it in the report while storing it raw in the ledger is
  defensible but should be a stated decision.
