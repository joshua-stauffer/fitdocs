---
id: 2026-09-12-cli-help-swallows-bracketed-table-names
title: Typer/Rich help rendering swallows bracketed TOML table names in command docstrings
status: open
importance: low
importance_why: fitdocs derive-benchmarks --help and fitdocs plugins --help both print a malformed "table" line where the TOML table name should appear, degrading CLI help output.
effort: S
kind: bug
area: src/fitdocs/cli.py
created: 2026-09-12
surfaced_by: /kiro-impl performance-benchmarks (adversarial reviews, 2026-09-11/12)
pinned_at: d4fbc6f
resume_command: "do: fix Typer/Rich markup swallowing [load]/[plugins] in cli.py command docstrings via rich_markup_mode or escaping/rewording"
context:
  - src/fitdocs/cli.py
blocked_by: []
---

## What

Typer/Rich markup interprets bracketed TOML table names in command
docstrings as markup and eats them: `fitdocs derive-benchmarks --help`
prints "a malformed ```` table" and `fitdocs plugins --help` prints "a
malformed  table" (pre-existing at `cli.py:452`).

## Why it matters

The rendered help text for both commands is visibly broken where a
concrete table name (`[load]`, `[plugins]`) should appear.

## Evidence

- (4.4 reviewer) "Typer/Rich help rendering swallows bracketed TOML table
  names in command docstrings: `fitdocs derive-benchmarks --help` prints 'a
  malformed ```` table' and `fitdocs plugins --help` (pre-existing,
  cli.py:452) 'a malformed  table'. Fix: rich_markup_mode/escaping or
  rewording. cli, S."

## How to pick it up

1. Reproduce with `fitdocs derive-benchmarks --help` and `fitdocs plugins
   --help` and confirm the malformed output.
2. Read the affected docstrings in `src/fitdocs/cli.py` (including the
   pre-existing case at line 452).
3. Fix via `rich_markup_mode` configuration, escaping the brackets, or
   rewording to avoid bracketed table names in help text.
</content>
