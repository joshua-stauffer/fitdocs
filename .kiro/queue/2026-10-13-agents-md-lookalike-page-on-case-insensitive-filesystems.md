---
id: 2026-10-13-agents-md-lookalike-page-on-case-insensitive-filesystems
title: On a case-insensitive filesystem a user file named agents.md in dashboards/ is listed as a dashboard page while sharing its path with the generated AGENTS.md declaration
status: open
importance: low
importance_why: The collision needs a user file whose name differs from AGENTS.md only in case, on macOS or Windows; the declaration is left alone (foreign), but the same file is then also a page fitdocs may edit.
effort: S
kind: bug
area: dashboards, src/fitdocs/dashboards/storage.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 4.2 reviewer)
pinned_at: 0a98d5c
resume_command: "do: make storage.list_markdown (and read_page) exclude a name that equals AGENTS.md ignoring case, or detect the shared path by file identity; add a test that skips where the filesystem is case-sensitive [queue: .kiro/queue/2026-10-13-agents-md-lookalike-page-on-case-insensitive-filesystems.md]"
context:
  - src/fitdocs/dashboards/storage.py
  - src/fitdocs/declaration.py
  - tests/dashboards/test_storage.py
blocked_by:
  - dashboards
---

## What
`list_markdown` skips the generated declaration by exact name:
`and entry != _DECLARATION_FILE` (`src/fitdocs/dashboards/storage.py:208`, with
`_DECLARATION_FILE = "AGENTS.md"` at line 32). On a case-insensitive filesystem
a user file `dashboards/agents.md` is the same path as `dashboards/AGENTS.md`,
yet its name is not equal, so it is listed as a page called `agents`.

## Why it matters
The one file is then two things at once. `ensure_declarations` treats it as the
declaration location: unstamped, so it reports `FOREIGN` and leaves it alone.
The dashboard pass treats it as a page and may insert or rewrite chart regions
in it if it holds a directive. The declaration can never be placed for that
user, and a chart-region write lands in a file the ownership contract calls the
declaration.

## Evidence
Run on macOS APFS (case-insensitive by default) at 0a98d5c:

```
dashboards/ holds only: agents.md   ("# my notes about agents")
list_markdown(root)           -> ('agents',)
ensure_declarations(root)     -> [('dashboards/', 'FOREIGN')]
os.listdir(dashboards)        -> ['agents.md']
(dashboards / 'AGENTS.md').exists() -> True
```

Reported by the 4.2 reviewer subagent; reproduced in this session. On a
case-sensitive filesystem the two names are distinct files and nothing
collides.

## How to pick it up
1. Read `list_markdown` and `read_page` in `src/fitdocs/dashboards/storage.py` (lines 190-235).
2. Compare case-insensitively against the declaration name in `list_markdown`, and refuse the same name in `read_page` and `plan_run`'s page-name handling. Alternatively compare `os.path.samefile` against the declaration path when it exists.
3. Add a test that creates `agents.md`, asserts `list_markdown` omits it, and skips when `Path('X').exists()` shows a case-sensitive volume. Done means the file is neither a page nor a declaration collision.

## Open questions
Whether the user file should instead be reported (a `page_name`-style notice) so the user learns why the declaration is missing.
