---
id: 2026-07-26-docedit-zone-label-docstring-vestige
title: docedit's YAML-scalar docstring still uses the withdrawn methodology's zone label as its worked example
status: done
importance: low
importance_why: Prose only, no code path; but it teaches vocabulary for a concept task 2.1 deleted.
effort: S
kind: docs
area: training-load, src/fitdocs/load/docedit.py
created: 2026-07-26
surfaced_by: /kiro-validate-impl training-load
pinned_at: 3121bb6
resume_command: "do: Replace the 'Zone 6 (Aerobic Threshold)' example in src/fitdocs/load/docedit.py:386-387 with a value the current LoadResult can actually produce"
context:
  - src/fitdocs/load/docedit.py
  - .kiro/specs/training-load/design.md
blocked_by: []
---

## What
`_yaml_scalar`'s docstring offers "zone labels like ``Zone 6 (Aerobic Threshold)``" as its worked example of a safe plain scalar. Zones were removed from `LoadResult` by task 2.1, and no shipped code can produce such a value now.

## Why it matters
Harmless at runtime -- no code path, no behaviour. It is a vestige of a withdrawn concept in shipped source, which makes the withdrawal look incomplete to a reader and models vocabulary that no longer exists for anyone extending the module.

## Evidence
`sed -n '386,388p' src/fitdocs/load/docedit.py` at 3121bb6 shows the example verbatim. A case-insensitive search of `src/` for the third party's name and the methodology's trademarked abbreviation returns zero hits, so this is the last conceptual trace, though it names no withdrawn symbol.

## How to pick it up
One-line docstring edit. Pick an example a current `LoadResult` can produce -- a `calculator_id` like `mycalc` or a basis string. Done when the example is a value the shipped types can hold.

## Resolution

Done 2026-08-05 (`encumbered-content-purge` task 3.12). The redaction is
task 3.5's. It is committed on branch `impl/encumbered-content-purge`, not
yet merged to `main`. `_yaml_scalar`'s docstring in
`src/fitdocs/load/docedit.py` no longer offers a zone label as its worked
example. It now offers `stub-computing` as its example of a safe plain
scalar. `stub-computing` is a `calculator_id` value shipped types already
hold elsewhere in the test suite (`tests/load/conftest.py`).
