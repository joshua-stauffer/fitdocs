---
id: 2026-09-18-config-error-output-surface-wrap-and-stderr
title: `_config_error` hard-wraps at 80 columns in non-tty output, and no test in tests/test_cli.py asserts its messages reach stderr
status: open
importance: low
importance_why: Cosmetic wrap plus a convention gap; tests/test_cli_skill.py already asserts stderr, so the gap is the older suite only.
effort: S
kind: chore
area: src/fitdocs/cli.py, tests/test_cli.py
created: 2026-09-18
surfaced_by: /kiro-impl build-training-block (reviewers, the recorded exercise, /kiro-validate-impl)
pinned_at: e45f114
resume_command: "do: give _config_error's Console.print soft_wrap=True like every path line in cli.py, and convert tests/test_cli.py's config-error `.output` assertions to `result.stderr` where the message is the pin"
context:
  - src/fitdocs/cli.py
  - tests/test_cli.py
  - tests/test_cli_skill.py
blocked_by: []
---

## What
`src/fitdocs/cli.py:1002` prints config errors with `markup=False,
highlight=False` but no `soft_wrap=True`, so under CliRunner (80 cols) a
message wraps mid-sentence (`... -- the \ninstallation is incomplete.`).
Separately, `grep -c result.stderr tests/test_cli.py` is 0: the older suite
reads the mixed `result.output`, which cannot see a stdout/stderr swap;
1.2's review proved that by routing a message to stdout unnoticed.

## Evidence
- `src/fitdocs/cli.py:1002`; observed wrap in the 1.2 round-2 review stream probe.
- `tests/test_cli_skill.py` asserts `result.stderr` (controller ruling, Implementation Notes 1.2).

## How to pick it up
Two one-line edits plus a sweep of `tests/test_cli.py` for `_config_error`
pins; run `uv run pytest tests/test_cli.py tests/test_cli_skill.py -q`.
