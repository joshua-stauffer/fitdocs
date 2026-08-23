---
id: 2026-08-23-channel-test-modules-are-outside-the-mypy-perimeter
title: The channels' test modules sit outside the mypy perimeter the Definition of Done runs
status: open
importance: low
importance_why: A type-ignore comment now sits on the exact expression a delegation test asserts, and no command in the Definition of Done would catch it being wrong.
effort: S
kind: gap
area: repo test perimeter, pyproject.toml, tests/load/channels/
created: 2026-08-23
surfaced_by: /kiro-impl load-channels task 3.1 adversarial review
pinned_at: 4aba266
resume_command: "do: decide whether tests/load/channels/ belongs in [tool.mypy] files, and if so add it and fix what surfaces"
context:
  - pyproject.toml
  - tests/load/channels/test_power.py
blocked_by: []
---

## What

`pyproject.toml`'s `[tool.mypy] files` list carries 21 entries, none under
`tests/load/channels/`. The Definition of Done's type gate is `uv run mypy
src/`, so none of this spec's test modules is ever type-checked by the command
the protocol runs.

This surfaced because task 3.1's delegation test now carries a
`# type: ignore[attr-defined]` on `power.power_tss` — the exact expression the
test asserts identity against. The ignore is **correct**: removing it produces
a real `no_implicit_reexport` error, and strict's `warn_unused_ignores` does not
flag it as dead. But nothing in the Definition of Done checks that.

## Why it matters

An ignore comment on an assertion's own subject is the place where a silent
mistake costs most: if the attribute stopped existing, a wrongly-scoped ignore
could hide the static half while the runtime half still fails — or, in the
other direction, a future ignore could mask a genuine error nobody re-runs.

The task's reviewer verified this specific one by hand (`uv run mypy
tests/load/channels/test_power.py` is clean, and the attribute exists at
runtime). That verification is not repeatable by any standing command.

## Evidence

At `4aba266`:

- `pyproject.toml` `[tool.mypy] files` contains no entry under
  `tests/load/channels/`
- `uv run mypy src/` reports 66 source files and does not include the test
- `uv run mypy tests/load/channels/test_power.py` run explicitly is clean
- removing the ignore yields: `error: Module
  "fitdocs.load.channels.power" does not explicitly export attribute
  "power_tss" [attr-defined]`

## How to pick it up

1. Read `[tool.mypy]` in `pyproject.toml` and note why the 21 entries were
   chosen — the perimeter looks deliberate, so this may be a considered
   exclusion rather than an oversight.
2. Run `uv run mypy tests/load/` and see how much surfaces.
3. If the volume is manageable, add the directory and fix what appears. If not,
   record why the perimeter stops where it does, so the next session does not
   re-litigate it.

Done looks like: either the test tree is inside the perimeter, or the exclusion
is documented with its reason.

## Open questions

- Was the 21-entry perimeter chosen deliberately, or has it simply never been
  revisited since the purge reduced it from 115 to 83 and onward?
