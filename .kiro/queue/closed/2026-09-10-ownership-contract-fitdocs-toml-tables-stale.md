---
id: 2026-09-10-ownership-contract-fitdocs-toml-tables-stale
title: docs/ownership-contract.md still describes fitdocs.toml as "[tiles] today"
status: done
importance: low
importance_why: The user-facing ownership document understates the settings surface by every table shipped since route-maps; wrong for a first-time reader, cheap to fix.
effort: S
kind: docs
area: docs/ownership-contract.md
created: 2026-09-10
surfaced_by: /kiro-spec-batch (effort-tags design, wave 1)
pinned_at: 1251a98
resume_command: "do: nothing -- absorbed by training-blocks task 1.3 (see Resolution)"
context:
  - docs/ownership-contract.md
  - .kiro/specs/effort-tags/tasks.md
blocked_by: []
---

## What
The `fitdocs.toml` bullet in `docs/ownership-contract.md` says the file
holds "`[tiles]` today; more tables as more features land". Several more
tables have landed since and the sentence was never updated.

## Why it matters
This is the document that tells an athlete which files are theirs and which
are fitdocs'. A stale table list makes the settings surface look smaller
than it is, and a reader who greps the doc for a table name will not find it.

## Evidence
- `docs/ownership-contract.md:173-176` — the bullet quoted above.
- Tables actually read from `fitdocs.toml` today (grep at 1251a98):
  - `src/fitdocs/plugins.py:64:PLUGINS_TABLE: Final[str] = "plugins"`
  - `src/fitdocs/tiles.py:61:TILES_TABLE: Final[str] = "tiles"`
  - `src/fitdocs/inbox.py:154:INBOX_TABLE: Final[str] = "inbox"`
  - `src/fitdocs/load/settings.py:69:LOAD_TABLE = "load"`

## How to pick it up
1. Re-run the grep above against current `main` to get the live table list.
2. Rewrite the bullet to enumerate the tables and keep the "read-only to
   fitdocs" statement unchanged.
3. If effort-tags task 4.2 is in flight, hand it the edit rather than racing
   it on the same file.

## Resolution
Absorbed by training-blocks task 1.3 (main 68fe42e, 2026-09-16): the
`fitdocs.toml` bullet in `docs/ownership-contract.md` now names `[tiles]`,
`[inbox]`, `[plugins]`, `[load]`, `[history]` and `[plans]` and keeps the
read-only statement. The 1.3 reviewer verified the list against every
`*_TABLE` constant under `src/fitdocs/` (`LOAD_TABLE` has no `Final`
annotation, which is why a `_TABLE: Final` grep misses it). Closed by the
training-blocks session.
