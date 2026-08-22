---
id: 2026-07-26-load-command-no-prompt-forwarding-unpinned
title: The load command's --no-prompt forwarding is unpinned, unlike sync's, so dropping it stays green
status: done
importance: medium
importance_why: Breaking the flag would make `fitdocs load --no-prompt` silently prompt-free-by-accident or prompting-by-accident with the whole suite green; Req 3.5 is a user-facing interactivity guarantee and `sync` already has the spy that would catch it.
effort: S
kind: gap
area: training-load, tests/load/test_cli_load.py
created: 2026-07-26
surfaced_by: /kiro-impl training-load (task 4.2, confirmatory review regression spot-check)
pinned_at: 12caa6e
resume_command: "do: add a _build_session forwarding spy to tests/load/test_cli_load.py for the load command, mirroring tests/test_cli_sync_inbox.py:451's drain-path spy, so that mutating cli.py:399's no_prompt=no_prompt to a constant reddens"
context:
  - src/fitdocs/cli.py
  - tests/load/test_cli_load.py
  - tests/test_cli_sync_inbox.py
  - .kiro/specs/training-load/requirements.md
blocked_by: []
---

## What

`src/fitdocs/cli.py:399` forwards the CLI flag into the single interactivity
decision point:

```python
session = _build_session(no_prompt=no_prompt)
```

Mutating that to `no_prompt=True` (or `False`) leaves **all 1815 tests green**.
Requirement 3.5 — non-interactive means no prompt, nothing computed from
guesses, and a clean finish — is a user-facing guarantee, and the `load`
command's half of it is unpinned.

The delivered line is **correct**; this is purely missing coverage.

## Why it matters

`medium`, not `low`, for two reasons.

First, the failure is silent and user-facing in both directions. Pinned to
`True`, `fitdocs load` would stop prompting even on a TTY and quietly produce
uncomputed documents. Pinned to `False`, a `--no-prompt` run in a script or cron
job would block waiting on stdin.

Second, **`sync` already has exactly the test this needs** —
`tests/test_cli_sync_inbox.py:451`
`test_no_prompt_flag_is_forwarded_to_the_session_builder_on_the_drain_path`
installs a `_build_session` spy recording the `no_prompt` value. So this is an
asymmetry between two commands sharing one decision point, not a missing idea.

Root cause of why nothing else catches it: `CliRunner`'s stdin is never a TTY,
so the constructed session class is the same under the mutation and no
behavioural assertion can distinguish the two. Only a forwarding spy can.

## Evidence

Verified in this run at `12caa6e` (branch `impl/training-load`):

- `src/fitdocs/cli.py:399` — `session = _build_session(no_prompt=no_prompt)`;
  mutating the argument to a constant leaves `uv run pytest -q` at **1815
  passed**.
- `tests/test_cli_sync_inbox.py:451-466` — the existing spy for the sync drain
  path, recording `no_prompt` into a `calls` list. This is the pattern to copy.
- `tests/load/test_cli_load.py` references `_build_session` 12 times but never
  as a forwarding spy — the existing uses construct sessions, they do not
  observe what the command forwarded.

Surfaced by the task-4.2 confirmatory reviewer while spot-checking the
requirements the task **preserves** rather than implements. Task 4.2 never
touched this line, so it is pre-existing, not a regression.

## How to pick it up

1. Read `tests/test_cli_sync_inbox.py:451` end to end — it is the working
   reference, including how it monkeypatches the name on the *consuming* module
   rather than at the definition site.
2. Add the equivalent to `tests/load/test_cli_load.py` for `fitdocs load`:
   monkeypatch `_build_session` with a spy that records `no_prompt` and delegates
   to the original, invoke the command both with and without `--no-prompt`, and
   assert the forwarded values are `True` and `False` respectively. Asserting
   **both** directions is what makes it immune to a constant of either value.
3. Verify by mutation: set `cli.py:399` to `no_prompt=True`, confirm the new test
   reddens, restore byte-identically, confirm green. Then repeat with
   `no_prompt=False` — a test that only catches one constant is half a pin.
4. Done looks like: neither constant survives, and
   `uv run pytest && uv run ruff check . && uv run mypy src/` is green.

Cheap and self-contained. Worth folding into task 6.1, which already proves the
prompting boundaries end to end.

## Resolution

**Done 2026-07-26** (queue sweep, merged to `main` at `e806c57`).

`1e40817`. Forwarding spy mirroring the sync drain-path test. Both constants verified as sole failures — `no_prompt=True` and `no_prompt=False` each redden it, since a test catching only one is half a pin.
