---
id: 2026-10-17-cli-help-prints-internal-spec-references
title: Several `fitdocs <command> --help` screens print developer docstrings with spec requirement and design references
status: open
importance: low
importance_why: User-facing help shows internal traceability ("Req 3.9", "design.md", "task 1.4") and run-on implementation detail; nothing breaks.
effort: M
kind: docs
area: src/fitdocs/cli.py, connectors, wellness-pull, plan-resolution, build-training-block
created: 2026-10-17
surfaced_by: maintainer-requested Phase 12 re-validation (reading `fitdocs pull --help` while preparing the live pull)
pinned_at: 160b007
resume_command: "do: split each Typer command's docstring into a short user-facing help paragraph and a developer comment (Typer uses the docstring; move Req/design/task references out of it), then check every `fitdocs <cmd> --help` [queue: .kiro/queue/2026-10-17-cli-help-prints-internal-spec-references.md]"
context:
  - src/fitdocs/cli.py
  - docs/reference
blocked_by: []
---

## What
Typer renders a command function's whole docstring as its `--help` text.
Several commands carry developer docstrings, so users read lines such as
"(connectors design: CliCommands "``fitdocs pull``"; Req 3.9, 4.2, 6.1-6.3,
...)" and "after the pull report, ``--sync`` chains
:func:`_run_drain_passes` (task 1.4)".

## Why it matters
The help screen is the first documentation a user meets. Spec traceability
belongs in comments, and the RST markup (`:func:`, double backticks) renders
literally.

## Evidence
At 160b007, the number of help-screen lines matching
`Req [0-9]|design\.md|requirements\.md|task [0-9]` per command: pull 14,
connect 13, skill 6, plan 5, history 3, plugins 3, check 2, sync 1, regen 1;
index, load, recovery, derive-benchmarks, query and dashboard 0. The
related but distinct item `2026-09-12-cli-help-swallows-bracketed-table-names`
covers Rich eating `[table]` names.

## How to pick it up
1. For each affected command in `src/fitdocs/cli.py`, keep one or two
   user-facing paragraphs as the docstring and move the traceability into a
   `#` comment block above the function. Typer also accepts `help=` on the
   command decorator.
2. Check any tests that pin help text (`grep -rn "\-\-help" tests/`).
3. Re-run the count above; expect 0 everywhere.
