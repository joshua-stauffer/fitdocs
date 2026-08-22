---
id: 2026-07-26-withdrawal-guards-evadable-by-rename
title: The withdrawal guards are keyed to names and to .csv, so a rename ships undetected
status: open
importance: low
importance_why: Nothing is trying to reintroduce the methodology today; this is defence-in-depth on a settled withdrawal.
effort: S
kind: gap
area: training-load, tests/load/test_packaging.py
created: 2026-07-26
surfaced_by: /kiro-validate-impl training-load
pinned_at: 3121bb6
resume_command: "do: Widen the withdrawal guards in tests/load/test_packaging.py -- check for any non-.py data file under src/fitdocs/load/, and consider a directory-level allowlist instead of the name-keyed _WITHDRAWN_SYMBOLS list"
context:
  - tests/load/test_packaging.py
  - .kiro/specs/training-load/requirements.md
blocked_by: []
---

## What
Two narrow spots in the Requirement 13.1/13.3 withdrawal guards. The bundled-table check looks only for `.csv` under `fitdocs/load/`, so a table shipped as `.json`, `.toml` or `.parquet` passes. `_WITHDRAWN_SYMBOLS` is name-keyed. A reintroduction under any other spelling clears both the symbol guard and the withdrawn-methodology-constant guard. Such a spelling would be a module and class built from the methodology's trademarked abbreviation, not the names the guard holds (`WithdrawnCalculator` / `fitdocs.load.withdrawn`).

## Why it matters
The methodology is withdrawn and nobody is re-adding it, so this is low. It matters only as defence-in-depth: the guards exist precisely because the withdrawal must not silently reverse, and a guard that a rename defeats provides less assurance than its docstring implies.

## Evidence
Reported by the task 6.4 round-1 reviewer from reading the guard bodies at `tests/load/test_packaging.py:35` and `:174-179`; the `.csv`-only glob and the literal symbol list are verified present at 3121bb6. The evasions were not individually executed.

## How to pick it up
Open `tests/load/test_packaging.py`. Replace the `.csv` glob with a check for any non-`.py` file under `src/fitdocs/load/` (allowlisting `__init__.py`-adjacent legitimate assets if any appear). For the symbol list, consider asserting the set of modules under `src/fitdocs/load/` against an explicit allowlist, so a new methodology module is caught whatever it is called. Done when a `.json` table and a renamed calculator module each redden a test.
