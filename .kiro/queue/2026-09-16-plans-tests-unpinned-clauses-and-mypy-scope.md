---
id: 2026-09-16-plans-tests-unpinned-clauses-and-mypy-scope
title: Five test-side leftovers in the training-blocks suites (ever-present token, an unpinned "writes nothing", a count assertion, mypy scope)
status: open
importance: low
importance_why: Each is a sentence the suite claims but cannot fail on, or a typed module mypy does not see; none changes behaviour, all are cheap and rot silently.
effort: S
kind: gap
area: training-blocks, tests/test_cli_plan.py, tests/plans/test_engine.py, tests/plans/test_settings.py, tests/test_declaration_refresh.py, pyproject.toml
created: 2026-09-16
surfaced_by: /kiro-impl training-blocks (reviewers of 1.2, 4.3, 4.6)
pinned_at: 68fe42e
resume_command: "do: (1) tests/test_cli_plan.py:229,240 replace `\"path\" in result.output` with the configured directory name and check tests/plans/test_settings.py for the same token on the owned-path/not-a-directory errors; (2) tests/plans/test_engine.py ~:100 pin \"writes nothing\" with a counting stub around _atomic_write as tests/test_plan_e2e.py does; (3) tests/test_declaration_refresh.py test_refresh_declarations_appends_a_warning_per_foreign_directory add `assert len(warnings) == len(DECLARED_DIRS)`; (4) add tests/test_cli_plan.py, tests/test_plan_e2e.py and a typed tests/test_history_e2e.py to [tool.mypy].files"
context:
  - tests/test_cli_plan.py
  - tests/plans/test_engine.py
  - tests/plans/test_settings.py
  - tests/test_declaration_refresh.py
  - tests/test_history_e2e.py
  - pyproject.toml
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What
1. `tests/test_cli_plan.py:229` and `:240` assert `"path" in result.output`
   for the two configuration-error exits. The word matches the `[plans] path`
   key literal that every such message carries, so dropping the resolved
   directory from the message leaves the suite green (Req 1.10 "naming the
   path"). `tests/test_plan_e2e.py` pins its own copy with the directory
   name; `tests/plans/test_settings.py` may carry the same token on the
   owned-path / not-a-directory errors (Req 1.9) -- check.
2. `tests/plans/test_engine.py:100` says a second unmodified run "writes
   nothing"; rewriting every planned page with identical bytes while still
   reporting `unchanged` left that module green. `tests/test_plan_e2e.py`
   now pins it with an `_atomic_write` call count; the engine test should
   too (design.md "Performance" prescribes the counting-stub idiom).
3. `tests/test_declaration_refresh.py::test_refresh_declarations_appends_a_warning_per_foreign_directory`
   asserts a set equality over `w.doc`, so a double-append per foreign
   directory is caught only by the sync/regen parametrisations elsewhere in
   the module; `assert len(warnings) == len(DECLARED_DIRS)` makes the test
   carry its own "one warning per directory" sentence.
4. `tests/test_cli_plan.py` and `tests/test_plan_e2e.py` type-check clean
   standalone but are not in `[tool.mypy].files` (`tests/test_cli.py` and
   `tests/test_cli_derive.py` are). `tests/test_history_e2e.py`, which the
   e2e module now imports `_fake_system_date` from, shows 18 strict errors
   standalone.

## Why it matters
change-protocol.md § Fixture Discrimination: an assertion that cannot fail
tells every later session the behaviour is pinned while pinning nothing.

## Evidence
- `grep -n '"path" in result.output' tests/test_cli_plan.py` -> 229, 240.
- `tests/plans/test_engine.py:100` (the "writes nothing" sentence);
  4.6 reviewer mutation o15 (unconditional `_atomic_write`, `written.append`
  gated on the byte comparison) -> whole suite green before 4.6's pin.
- `grep -n "test_cli_plan\|test_plan_e2e\|test_history_e2e" pyproject.toml`
  -> no hits.
- Items 1-3 reported by reviewer subagents with mutation counts; item 4
  verified by the grep above.

## How to pick it up
1. Run the named mutation for each of 1-3 first (it must stay green before
   your change, red after) -- the mutation is the evidence, per steering.
2. For 4, add the three modules, run `uv run mypy`, fix the history e2e
   module's typing.
3. Done when `uv run pytest -q`, `uv run mypy` are green and each of the four
   named mutations reds.
