---
id: 2026-10-02-pull-report-title-wraps-and-folder-missing-source-next-step
title: Two small pull-output defects -- the per-instance table title wraps long instance names mid-name at any width, and the folder connector's missing-source error omits its designed next step
status: open
importance: low
importance_why: Cosmetic and wording only; the report's counts and the error's cause are correct, but a split instance name is hard to read and the error leaves the user without the remedy the design promises.
effort: S
kind: bug
area: connectors, src/fitdocs/cli.py, src/fitdocs/connectors/folder.py
created: 2026-10-02
surfaced_by: /kiro-impl connectors
pinned_at: ad985b3
resume_command: "/kiro-impl connectors [queue: .kiro/queue/2026-10-02-pull-report-title-wraps-and-folder-missing-source-next-step.md] Print each pull table's heading as its own soft-wrapped line and add 'check the path or mount' to the folder connector's missing-source error"
context:
  - src/fitdocs/cli.py
  - src/fitdocs/connectors/folder.py
  - tests/connectors/test_cli_connectors.py
  - tests/connectors/test_folder.py
  - .kiro/specs/connectors/design.md
blocked_by: []
---

## What
1. **Table title wrap.** `_report_pull` builds
   `Table(title=f"fitdocs pull: {instance.name} ({instance.connector_id})")`
   (`src/fitdocs/cli.py:1210`). Rich wraps a table title to the table's own
   width (two narrow columns, about 24 characters), so a long instance name
   is split mid-name regardless of terminal width.
2. **Folder next step.** The folder connector raises
   `ConnectorError(f"{source}: folder connector source is missing or not a directory")`
   (`src/fitdocs/connectors/folder.py:157-159`). design.md's Error Categories
   table gives this case the next step "check the path or mount"
   (`.kiro/specs/connectors/design.md:1881`); the message carries no next
   step.

## Why it matters
The instance name is the user's handle for the table; splitting it mid-word
makes the report look broken. A missing folder is most often an unmounted
drive or synced folder, and the next step is what tells the user so.

## Evidence
Run at `ad985b3`, `COLUMNS=200`, calling `cli._report_pull` with one instance
named `my-long-garmin-export-folder-instance`:

```
Inbox: /x
     fitdocs pull:
my-long-garmin-export-fo
 lder-instance (folder)
┏━━━━━━━━━━━━━━┳━━━━━━━┓
```

Item 1 first reported by the feature-validation integration reviewer (F2),
item 2 by the task 4.4 reviewer; both re-checked here.

## How to pick it up
1. In `_report_pull`, print `fitdocs pull: <name> (<connector_id>)` with
   `console.print(..., markup=False, highlight=False, soft_wrap=True)` before
   the table and drop the `title=` (or keep a short fixed title). Check
   `tests/connectors/test_cli_connectors.py` and `tests/test_agent_skill.py`
   for assertions on the title text first.
2. Append "; check the path or mount" (wording per design.md:1881) to the
   folder error and pin it in `tests/connectors/test_folder.py`.
3. Done when the probe above prints the name on one line, and the folder
   error test asserts the next step.
