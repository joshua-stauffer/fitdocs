---
id: 2026-10-13-query-indexed-root-fixture-teardown-and-dead-xdg
title: The tests/query indexed_root fixture asserts the whole fixture HOME is empty at teardown and carries a dead XDG_CACHE_HOME setenv/delenv
status: open
importance: low
importance_why: Test hygiene only; the teardown can fail for a reason unrelated to the index (anything else writing under HOME), and the dead lines suggest an isolation step that does not exist.
effort: S
kind: chore
area: analytics-query, tests/query/conftest.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 1.1 reviewer)
pinned_at: 0a98d5c
resume_command: "do: in tests/query/conftest.py `indexed_root`, drop the dead XDG_CACHE_HOME setenv (keep the delenv and its assert) and narrow the final `home.iterdir() == ()` assertion to the paths the index and CLI could have written [queue: .kiro/queue/2026-10-13-query-indexed-root-fixture-teardown-and-dead-xdg.md]"
context:
  - tests/query/conftest.py
  - tests/query/test_crash_vectors.py
  - tests/dashboards/conftest.py
blocked_by: []
---

## What
`indexed_root` is a module-scoped fixture that builds a real index for the
analytics-query tests. Two lines in it do nothing useful. It sets
`XDG_CACHE_HOME` and deletes it on the next line, so the set has no effect and
the following assert only proves the variable is absent. And its teardown
asserts that the whole fixture `HOME` directory is empty, which is stricter
than "the index did not write under HOME": any other process that writes under
`$HOME` fails an unrelated module teardown.

## Why it matters
A teardown that fails for a reason other than the behaviour under test reads as
an index-isolation regression and costs a debugging session. The dead
setenv/delenv pair also invites a reader to think `XDG_CACHE_HOME` is being
pointed somewhere on purpose.

## Evidence
- `tests/query/conftest.py:134-136` at 0a98d5c: `isolated.setenv("XDG_CACHE_HOME", str(base / "user-xdg"))`, then `isolated.delenv("XDG_CACHE_HOME", raising=False)`, then `assert "XDG_CACHE_HOME" not in os.environ`.
- `tests/query/conftest.py:198`: `assert tuple(home.iterdir()) == ()` after the `yield`.
- The Rosetta part is reported, not re-run here: running x86-64 containers on the Mac under Rosetta writes `$HOME/.cache/rosetta`, which broke HOME-purity assertions of this kind during the 2026-10-08 CI work on analytics-query. Reported by the 1.1 reviewer subagent of the dashboards run as "whole-HOME emptiness teardown (Rosetta trap)".

## How to pick it up
1. Open `tests/query/conftest.py` around `indexed_root` (line 92) and delete the `setenv("XDG_CACHE_HOME", ...)` line.
2. Decide what the teardown should prove. The useful claim is that the index lands under `FITDOCS_INDEX_DIR`, not under HOME. Assert that with a path-specific check (for example that `home` holds no `.cache/fitdocs`), or keep the empty check but exclude `.cache/rosetta`.
3. Run `uv run pytest tests/query -q`. Done means the fixture still fails if the index is written under HOME (mutate `resolve_index_location` to ignore `FITDOCS_INDEX_DIR` and watch it red).
