---
id: 2026-07-27-load-string-overloaded-across-namespaces
title: The literal "load" names three unrelated things, so any literal-key guard on one guards all three
status: open
importance: medium
importance_why: A guard meant to catch a second reader of the `[load]` settings table already misattributes a read of the rendered `load` document region on `main` today. Four sibling specs will add code touching both namespaces, and a misattributed red costs review rounds before anyone questions the guard.
effort: M
kind: inconsistency
area: training-load, src/fitdocs/contract.py, src/fitdocs/cli.py, tests/load/test_settings.py
created: 2026-07-27
surfaced_by: adversarial review of impl/load-second-reader (queue sweep 2026-07-27)
pinned_at: 80cc5c5
resume_command: "do: decide whether the three `load` namespaces need distinguishable spellings — the `[load]` settings table (src/fitdocs/load/settings.py:57 LOAD_TABLE), the rendered document region (src/fitdocs/contract.py:284 LOAD_REGION) and the CLI command (src/fitdocs/cli.py:376) — or whether the literal-key guards in tests/load/test_settings.py must instead resolve which namespace a literal belongs to [queue: .kiro/queue/2026-07-27-load-string-overloaded-across-namespaces.md]"
context:
  - src/fitdocs/contract.py
  - src/fitdocs/cli.py
  - src/fitdocs/load/settings.py
  - src/fitdocs/load/docedit.py
  - tests/load/test_settings.py
blocked_by: []
---

## What

The string `"load"` names three unrelated things in this codebase:

- the settings table — `src/fitdocs/load/settings.py:57` `LOAD_TABLE`
- the rendered document region — `src/fitdocs/contract.py:284`
  `LOAD_REGION: Final[str] = "load"`
- the CLI command — `src/fitdocs/cli.py:376` `@app.command("load")`

`tests/load/test_settings.py`'s single-reader guards detect a second reader of
the *settings table* by looking for the literal `"load"` in a subscript or a
`.get`/`.pop` call. Structurally that is a guard on all three namespaces at
once. It cannot distinguish `document["load"]` (settings table — forbidden)
from `extract_regions(md)["load"]` (document region — entirely legitimate and
documented).

This is already live on `main`, not a hypothetical: `src/fitdocs/load/docedit.py:217`
documents the region contract as literally `extract_regions(md)["load"] == c`
and `:253` does `regions[LOAD_REGION]`.

## Why it matters

Four sibling specs (`load-channels`, `threshold-load`, `activity-qa-flags`,
`athlete-benchmarks`) will add code touching both the settings table and the
rendered region. Each time one spells the region constant out or compares a
region name, the guard fires with a message asserting a forbidden second reader
of the `[load]` settings table — a misattributed red the next session burns
review rounds on before anyone thinks to doubt the guard.

The failure is worse than noise: a guard that reds for the wrong reason trains
sessions to suppress it, which is how the real second-reader case eventually
walks through.

## Evidence

Measured by the adversarial reviewer of `impl/load-second-reader`
(2026-07-27), probing constructs in `src/fitdocs/audit.py`:

| Construct | branch | main |
|---|---|---|
| `extract_regions(md)["load"]` — read the load region | FLAGGED | **FLAGGED** |
| `regions.pop("load")` — remove the load region | FLAGGED | not flagged |
| `command_name == "load"` — CLI dispatch | FLAGGED | not flagged |
| `options.get("mode", "load")` — `"load"` is the default *value* | FLAGGED | not flagged |

Only the first row is pre-existing on `main`; the rest were introduced by that
branch's widening and are being addressed there. The pre-existing row is what
makes this its own item — narrowing the widened clauses does not fix it.

## How to pick it up

1. Read `src/fitdocs/load/docedit.py:217` and `:253` for how the region
   constant is actually used, and `tests/load/test_settings.py`'s
   `_reads_load_table_literally` for what the guard actually matches.
2. Reproduce the `main` row above — write `extract_regions(md)["load"]` into a
   module and confirm the guard fires on current `main`.
3. Decide between the two routes: give the namespaces distinguishable spellings
   (rename the region constant's value, which is a rendered-output change with
   migration-by-regen cost — check that first), or teach the guard to resolve
   which namespace a literal belongs to (no output change, more guard
   complexity).

Done looks like: a legitimate region read does not fire the settings-table
guard, proven by a negative control in the fixture.
