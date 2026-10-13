---
id: 2026-10-13-snapshot-decode-skips-the-sql-digest-check
title: Snapshot decode does not check that sql_sha256 is the digest of the stored sql, so a hand-edited snapshot keeps a stale digest and raises no sql_changed
status: open
importance: low
importance_why: Snapshots are hand-editable files the user commits; the Req 10.6 notice depends on the stored digest alone, so an edit that desynchronises sql and digest hides or fakes the notice. Nothing wrong is drawn.
effort: S
kind: gap
area: dashboards, src/fitdocs/dashboards/snapshot.py, src/fitdocs/dashboards/engine.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 3.3 reviewer)
pinned_at: 0a98d5c
resume_command: "do: decide whether snapshot.decode should refuse a snapshot whose sql_sha256 differs from the digest of its stored sql (same rule as Directive.sql_sha256); if yes add the check as a SnapshotFormatError and a snapshot_unreadable test, if no record the decision in design.md Snapshot [queue: .kiro/queue/2026-10-13-snapshot-decode-skips-the-sql-digest-check.md]"
context:
  - src/fitdocs/dashboards/snapshot.py
  - src/fitdocs/dashboards/directive.py
  - src/fitdocs/dashboards/engine.py
  - .kiro/specs/dashboards/design.md
  - .kiro/specs/dashboards/requirements.md
blocked_by:
  - dashboards
---

## What
A snapshot file stores the chart's SQL text and a digest of it
(`sql_sha256`). `decode` reads both as plain strings
(`src/fitdocs/dashboards/snapshot.py:277` calls `_text(document, "sql_sha256")`)
and never recomputes the digest from the stored `sql`. The only comparison in
the engine is the stored digest against the digest of the directive's current
SQL (`src/fitdocs/dashboards/engine.py:1018`). The stored `sql` itself is never
consulted. The design does not require the cross-check, so this is a gap, not a
violation.

## Why it matters
Req 10.6 promises a `sql_changed` notice when the chart's SQL differs from the
SQL its snapshot was taken with. A user who edits a snapshot's `sql` (or its
digest) by hand, or merges two snapshots badly in git, can leave the two
fields disagreeing: the notice then reflects the digest, not the text the file
shows. The rows are still drawn correctly, so the harm is a misleading or
missing notice.

## Evidence
Run against 0a98d5c, duckdb 1.5.6:

```
snap = Snapshot(page="p", chart="c", generation=1, today=date(2026,10,13),
                sql="SELECT 'a' AS label, 1.0 AS value",
                sql_sha256=sha256(b"SELECT 2").hexdigest(), data=...)
back = decode(encode(snap))
-> decoded without error; sql_sha256 == sha256(sql): False
```

`encode` accepts the mismatched pair and `decode` returns it unchanged.
Reported by the 3.3 reviewer subagent; reproduced in this session.

## How to pick it up
1. Read `decode` in `src/fitdocs/dashboards/snapshot.py` (line 200 onward) and the `sql_sha256` property in `src/fitdocs/dashboards/directive.py` (line 63).
2. Note the digest rule: it hashes `sql.rstrip("\r\n")` (ruling R8 in `.kiro/specs/dashboards/tasks.md`; `design.md` line 725 still says `sha256 of sql.encode("utf-8")` until its validation amendment lands). Any check in `decode` must use the same rule, or it will reject every snapshot written from a `sql: |` block that ends the body.
3. Decide refuse versus accept. Done means the decision is in the design and a test pins it.

## Open questions
Whether a mismatch is a `snapshot_unreadable` problem (the file cannot be trusted) or only a notice. A refusal makes a frozen chart fail on a harmless whitespace edit of the stored `sql`; a notice keeps it drawing.
