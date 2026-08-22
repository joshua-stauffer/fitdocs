---
id: 2026-07-27-settings-offending-value-unasserted-at-cli
title: Req 5.3's "names the offending value" clause is never asserted through CLI output
status: open
importance: low
importance_why: The message body is what a user actually sees; only the file and key halves of the requirement are pinned at that surface.
effort: S
kind: gap
area: athlete-benchmarks, tests/test_cli.py, src/fitdocs/load/settings.py
created: 2026-07-27
surfaced_by: /kiro-impl athlete-benchmarks (task 5.3 review, round 3)
pinned_at: bb5ab9d
resume_command: "do: assert the offending value in the CLI configuration-error output, closing Req 5.3's third clause at the user-visible surface [queue: .kiro/queue/2026-07-27-settings-offending-value-unasserted-at-cli.md]"
context:
  - .kiro/specs/athlete-benchmarks/requirements.md
  - tests/test_cli.py
  - tests/load/test_settings.py
  - src/fitdocs/load/settings.py
blocked_by: []
---

## What

Requirement 5.3 says an invalid `[load]` value fails naming the file, the key
**and the offending value**. At the CLI surface only the first two are asserted:
`tests/test_cli.py:384-385` checks the settings file path and the
`benchmark_staleness_days` token. The offending value is asserted only in the
reader's own unit tests (`tests/load/test_settings.py`), never through
`result.output`.

## Why it matters

The unit tests pin the message the reader *constructs*; the CLI test pins what a
user *sees*. Those can diverge — a truncating formatter, a rewrapping renderer, or
a future handler that reformats the error would break the user-visible half while
every existing test stays green. The value is the part of the message that tells
the user what to edit.

## Scope note

Req 5.3 is **not** in task 5.3's `_Requirements:` list (that task lists 2.9 and
5.5), and the task's Observable asks only for the file and key. This is adjacent
work the task correctly did not do, not a defect in it.

## Evidence

- `tests/test_cli.py:384-385` — asserts `str(data_root / "fitdocs.toml")` and
  `"benchmark_staleness_days"` against the unwrapped output; no value assertion.
- `tests/load/test_settings.py:153, 163, 173, 184, 194` — each asserts the value
  in the message body at the reader level.
- Caution when writing the CLI assertion: `tests/test_cli.py` unwraps rich's line
  wrapping with `.replace("\n", "")` before matching, and the Implementation Notes
  in `.kiro/specs/athlete-benchmarks/tasks.md` warn against asserting a bare digit
  against a message embedding a `tmp_path` (a pytest tmp dir carries the session
  counter). Normalize the path out of the body first, and keep a separate
  un-normalized assertion that the path is named.

## How to pick it up

1. Read `tests/test_cli.py:339` (the staleness config-error test) and the
   path-normalization note in `tasks.md`'s Implementation Notes.
2. Add the value assertion against the normalized body.
3. Verify by deleting the value interpolation from the reader's message in
   `src/fitdocs/load/settings.py` — the new assertion must red. Restore from a
   scratch copy, never `git checkout`.
4. Done looks like: all three clauses of Req 5.3 red under a message mutation at
   the CLI surface.
