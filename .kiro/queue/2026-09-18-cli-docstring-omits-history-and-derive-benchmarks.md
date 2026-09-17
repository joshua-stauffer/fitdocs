---
id: 2026-09-18-cli-docstring-omits-history-and-derive-benchmarks
title: cli.py module docstring documents five tree-processing commands; `history` and `derive-benchmarks` are registered but named nowhere in it
status: open
importance: low
importance_why: Documentation only; the 1.2 lead-in was reworded to stop claiming exhaustiveness, so nothing is false, just incomplete.
effort: S
kind: docs
area: src/fitdocs/cli.py
created: 2026-09-18
surfaced_by: /kiro-impl build-training-block (reviewers, the recorded exercise, /kiro-validate-impl)
pinned_at: e45f114
resume_command: "do: add one-line bullets for `fitdocs history` and `fitdocs derive-benchmarks` to the tree-processing list in src/fitdocs/cli.py's module docstring and keep tests/test_cli_skill.py's docstring pins green"
context:
  - src/fitdocs/cli.py
  - tests/test_cli_skill.py
blocked_by: []
---

## What
`src/fitdocs/cli.py:5-7` now reads "Nine commands are registered ... The
tree-processing commands documented here are:" followed by five bullets
(sync, regen, load, check, plan) and a paragraph naming `plugins` and
`skill`. `history` and `derive-benchmarks` (load-history, performance-benchmarks)
are in neither.

## Evidence
`typer.main.get_command(app).commands` has nine keys; `sed -n 9,32p
src/fitdocs/cli.py` lists five. `tests/test_cli_skill.py` pins the count
against the live registry, so a tenth command updates the sentence anyway.

## How to pick it up
Add the two bullets in the existing shape; run `uv run pytest
tests/test_cli_skill.py tests/test_cli.py -q`.
