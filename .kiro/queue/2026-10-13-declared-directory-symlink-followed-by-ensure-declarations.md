---
id: 2026-10-13-declared-directory-symlink-followed-by-ensure-declarations
title: ensure_declarations follows a symlinked declared directory and writes AGENTS.md into the link target, while the dashboard pass refuses the same link as location_foreign
status: open
importance: medium
importance_why: A fitdocs write lands outside the data root through a link the user made, for every directory in DECLARED_DIRS, and the two writers disagree about whether the link is acceptable (dashboards Req 16.2).
effort: S
kind: bug
area: wiki-contract, src/fitdocs/declaration.py, src/fitdocs/layout.py
created: 2026-10-13
surfaced_by: /kiro-validate-impl dashboards (coverage dimension; classified UPSTREAM)
pinned_at: 0a98d5c
resume_command: "/kiro-spec-requirements wiki-contract [queue: .kiro/queue/2026-10-13-declared-directory-symlink-followed-by-ensure-declarations.md] make ensure_declarations refuse to write through a symlinked declared directory and report it"
context:
  - src/fitdocs/declaration.py
  - src/fitdocs/layout.py
  - tests/test_declaration.py
  - tests/test_declaration_refresh.py
  - .kiro/specs/wiki-contract/requirements.md
  - .kiro/specs/dashboards/requirements.md
blocked_by: []
---

## What
`ensure_declarations` (`src/fitdocs/declaration.py:597`) reads the declaration
with `_read_existing(path)` and, when it finds nothing, does
`path.parent.mkdir(parents=True, exist_ok=True)` and `path.write_text(...)`
(lines 626-629). If the declared directory itself (`workouts/`, `history/`,
`blocks/`, `fit-archive/` and, on the dashboards branch, `dashboards/`) is a
symlink, `path.parent` resolves through it and the file is written into the
link's target. The docstring and requirement 3.6 treat a symlinked
*declaration file* as foreign; a symlinked *directory* is not considered.

The dashboards pass, which has its own rule (Req 16.2: never follow a symbolic
`dashboards/`), reports `location_foreign` for the same layout, so one run can
write a file through a link and report that the link is unusable.

## Why it matters
`ensure_declarations` runs on `sync`, `regen`, `history`, `plan` and others.
A user who symlinks `fit-archive/` or `dashboards/` to another volume gets
`AGENTS.md` created at the target, outside the data root and, if the target is
outside the test sandbox, outside the confinement guard's view. It is a small write, but
it is the project's own rule (never follow a link to write) broken by the
project's own code.

## Evidence
Run at 0a98d5c (`PYTHONPATH=src`, script `symlink_decl.py` in the session
scratchpad, wiped on reboot):

```
root/dashboards -> elsewhere/        (symlink, directory)
ensure_declarations(root)            -> [('dashboards/', 'WRITTEN')]
elsewhere/ now holds                 -> ['AGENTS.md']
has_dashboards(root) (after elsewhere/p.md exists) -> True
plan_run(...).location_problems      -> [('location_foreign', 'The dashboards location cannot be used: dashboards/ is a symbolic link.')]
```

The same code path serves every `DECLARED_DIRS` entry (`src/fitdocs/layout.py`,
`DECLARED_DIRS`), so the four directories on `main` have the same behaviour;
only the dashboards one was probed because that is where the disagreement
surfaced. Dashboards Req 16.2: ".../ `dashboards/` ... is a symbolic link ...
fitdocs shall not follow, overwrite or delete it and shall report it".

## How to pick it up
1. Read `ensure_declarations` and `_read_existing` (`declaration.py`), and how `inspect_declarations` classifies the same case.
2. Decide the state for a symlinked or non-directory declared directory: a new `DeclarationState` (for example `FOREIGN`, reusing the existing meaning "left untouched, reported") is the least invasive, since callers already render `FOREIGN`.
3. Check `os.path.islink(data_root / dir)` and `not is_dir()` before the `mkdir`/`write_text`, return `FOREIGN`, and add a test per directory kind plus a case for a link in the middle of the path. Done means no write lands through a link and the report names the directory.

## Open questions
Scope of the check: the data root itself reached through a link (a normal wiki setup) should keep working, so the refusal should cover only the declared directory and its declaration file, not their ancestors.
