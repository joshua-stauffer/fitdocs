---
id: 2026-07-26-cli-reader-spy-two-surface-stale
title: tests/test_cli.py's reader spy patches two hand-picked surfaces and claims it covers all
status: done
importance: medium
importance_why: Its docstring asserts a coverage property that is false, and a future session may delete the package-wide sweep as redundant.
effort: S
kind: docs
area: training-load, plugin-api, tests/test_cli.py
created: 2026-07-26
surfaced_by: /kiro-validate-impl training-load
pinned_at: 3121bb6
resume_command: "do: Correct tests/test_cli.py:1234-1240's docstring claim that it spies "both binding surfaces a Python import can produce", and note that the package-wide sweep in tests/load/test_settings.py is not redundant with it"
context:
  - tests/test_cli.py
  - tests/load/test_settings.py
  - .kiro/specs/training-load/tasks.md
blocked_by: []
---

## What
`tests/test_cli.py::test_load_command_calls_load_load_settings_exactly_once` patches exactly two binding surfaces by hand (`tests/test_cli.py:1255-1256`) and its docstring claims it spies "both binding surfaces a Python import can produce". There is one binding surface per importing module, not two.

## Why it matters
The false claim is load-bearing in the wrong direction: a future session reading it may conclude the package-wide sweep added by task 6.4 is redundant and delete it. That sweep is the only guard covering Req 14.1's "anywhere in the tool".

## Evidence
Measured by the task 6.4 round-4 reviewer: a module-level `from fitdocs.load.settings import load_load_settings as _r2` in `src/fitdocs/load/arbitrate.py` plus a call in `validate_configured` -- a real second read on the `fitdocs load` path -- left `uv run pytest -q tests/test_cli.py` at 36 passed, whole module green, while the package-wide sweep correctly reddened.

## How to pick it up
Open `tests/test_cli.py:1225-1261`. Narrow the docstring to what the test does: it closes every spelling that routes through the two modules it patches, for `fitdocs load` only. Add one sentence pointing at `tests/load/test_settings.py`'s sweep as the package-wide guard. This file is task 4.2's boundary, not 6.4's -- that is why it was not fixed in place. Done when no docstring in either file claims a perimeter its test lacks.


## Resolution

**Done 2026-07-26** — `ae96ff9`, branch `chore/queue-top-ten`.

The measurement was re-run here rather than taken on the item's word: a
module-level `from fitdocs.load.settings import load_load_settings as _r2` in
`src/fitdocs/load/arbitrate.py` plus a call in `validate_configured` leaves
`tests/test_cli.py` at 36 passed, whole module green, while the package-wide
sweep reddens two tests.

The docstring now states the real perimeter -- every spelling routed through
those two modules, for `fitdocs load` only -- and names
`tests/load/test_settings.py`'s sweep as the package-wide guard with an explicit
do-not-delete.
