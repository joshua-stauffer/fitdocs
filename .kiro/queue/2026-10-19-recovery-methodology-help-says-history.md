---
id: 2026-10-19-recovery-methodology-help-says-history
title: "`fitdocs recovery --help` describes --methodology as summing the history page's curve"
status: open
importance: low
importance_why: User-facing help text is wrong for one option of one command; behavior is unaffected.
effort: S
kind: bug
area: recovery, src/fitdocs/cli.py
created: 2026-10-19
surfaced_by: 0.2 site-copy update (capturing every command's --help for the site's CLI reference)
pinned_at: 90cd00b
resume_command: "do: give `fitdocs recovery` its own --methodology typer.Option in src/fitdocs/cli.py (help: the load methodology the recovery page's Fitness, Fatigue and Form section uses), keep history's text for history, and pin both help strings in the CLI tests"
context:
  - src/fitdocs/cli.py
  - docs/recovery.md
blocked_by: []
---

## What
`history` and `recovery` share one option object, `_METHODOLOGY_OPTION`,
whose help text is written for `history`. So `fitdocs recovery --help` says
`--methodology` will "Sum the history page's curve under only this
methodology id", although recovery uses it for the load section of the
recovery page.

## Why it matters
A user or agent reading `fitdocs recovery --help` is told the option affects
the history page. It does not: `fitdocs recovery` never writes the history
page (`docs/recovery.md:134-135`).

## Evidence
- `src/fitdocs/cli.py:463-467` defines `_METHODOLOGY_OPTION` with
  `help="Sum the history page's curve under only this methodology id."`.
- `src/fitdocs/cli.py:1204` uses it for recovery
  (`methodology: str | None = _METHODOLOGY_OPTION,`), and line 1211 passes it
  to `run_recovery`.
- `NO_COLOR=1 COLUMNS=200 uv run fitdocs recovery --help` at 90cd00b prints
  `--methodology <str> Sum the history page's curve under only this methodology id.`
- `docs/recovery.md:12-14` describes the option as selecting "a root and load
  methodology".

## How to pick it up
1. Read `src/fitdocs/cli.py` around lines 463 and 1200-1215.
2. Add a recovery-specific option with accurate help text. Leave history's
   option unchanged.
3. Pin both strings in the CLI help tests.
4. Done when `fitdocs recovery --help` names the recovery page's Fitness,
   Fatigue and Form section.
