---
id: 2026-07-26-tests-not-type-checked
title: The suite's protocol-conformance guards are never type-checked, so the comments claiming they fail mypy are false
status: done
importance: medium
importance_why: The load contract's structural conformance is asserted only by annotations no command checks, so a calculator signature change can land green while every stub silently stops conforming — exactly the drift training-load task 3.3 had to fix by hand.
effort: M
kind: gap
area: tooling, tests/, pyproject.toml
created: 2026-07-26
surfaced_by: /kiro-impl training-load (task 3.2 adversarial review)
pinned_at: c8034d5
resume_command: "do: decide whether mypy's scope extends to tests/ or whether the suite's 'fails mypy --strict' conformance comments are dropped, then apply that decision across tests/load/conftest.py, tests/load/test_arbitrate.py and every sibling carrying the same claim"
context:
  - pyproject.toml
  - .kiro/steering/change-protocol.md
  - .kiro/steering/tech.md
  - tests/load/conftest.py
  - tests/load/test_arbitrate.py
  - src/fitdocs/load/types.py
blocked_by: []
---

## What

Several test modules annotate a stub calculator with the `LoadCalculator`
protocol type and label it a static conformance guard — for example
`tests/load/test_arbitrate.py:165`:

```python
# Static structural-conformance checks -- a shape mismatch fails mypy --strict.
_STUB_CALC: LoadCalculator = _StubCalculator("stub-x", Modality.RUN)
_HIKE_ONLY_CALC: LoadCalculator = _HikeOnlyCalculator()
```

**No command in the Definition of Done type-checks `tests/`**, so that comment
describes a guard that never runs. The annotations are inert: a stub whose
`compute` signature stopped matching the protocol would be caught by nothing.

The convention is copied verbatim from `tests/load/conftest.py`, so the same
false claim sits on the four shared stub calculators the whole load suite is
built on — the highest-value conformance assertions in the repo.

## Why it matters

`medium`, not `low`, because of what these particular guards are for. The load
calculator contract is a **structural** `Protocol` with no explicit subclassing
— that is deliberate, so a plugin author needs no import from fitdocs. The only
way to detect that a stub has drifted from the contract is to type-check it.

training-load task 3.3 changed `compute` from four parameters to five. Every
stub had to be moved by hand, and the suite would have stayed green if one had
been missed, because the stubs are invoked through the registry with no static
check anywhere. The next signature change — `threshold-load` and
`load-channels` both extend this surface — has the same exposure.

This is **pre-existing and was not introduced by task 3.2**; that task simply
copied the established convention. Filed against the tooling, not the task.

## Evidence

Verified in this run at `c8034d5` (branch `impl/training-load`):

- `pyproject.toml:41-44` — `[tool.mypy]` sets `python_version = "3.11"`,
  `strict = true`, **`files = ["src"]`**. `tests/` is outside the configured
  scope, so a bare `uv run mypy` never sees it.
- `.kiro/steering/change-protocol.md:92` — the Definition of Done for a
  `src/`, `tests/`, `pyproject.toml` change is
  `uv run pytest && uv run ruff check . && uv run mypy src/`. The mypy
  invocation is explicitly scoped to `src/`, so even overriding the config
  default would not reach the suite.
- There is no `Makefile`, no `justfile`, and no `.github/workflows/` in the
  repo — checked — so no CI job supplies a wider invocation either.
- `tests/load/test_arbitrate.py:163-166` and `tests/load/conftest.py` carry the
  "fails mypy --strict" comment on annotations nothing checks.

## How to pick it up

This is a **decision first, edit second** — do not just widen the scope and
watch it redden.

1. Run `uv run mypy tests/` once to size the problem before choosing. That
   number is the whole input to the decision; it was deliberately not run when
   this item was filed, to avoid presenting a stale count as fact.
2. Choose one:
   - **Extend the scope** — `files = ["src", "tests"]`, and update
     `change-protocol.md:92` to match so the DoD and the config agree. Honest
     and makes the comments true. Cost is whatever step 1 reports, and test
     code legitimately does things strict mode dislikes (deliberate bad types
     passed to error paths), so expect targeted `# type: ignore` with reasons.
   - **Narrow the claim** — keep mypy on `src/` and delete the "fails mypy
     --strict" sentence wherever it appears, leaving the annotations as
     documentation. Cheap and honest, but leaves the contract-drift exposure
     open, so pair it with a runtime conformance assertion
     (`isinstance(stub, LoadCalculator)` against a `@runtime_checkable`
     protocol, or an explicit signature check) if the guard is wanted at all.
   - A **third option worth pricing**: scope mypy to `src/` plus only the
     conformance-bearing test modules, which buys the guard without the
     suite-wide cost.
3. Apply the decision **everywhere the claim appears**, not just where it was
   found: `grep -rn "mypy --strict" tests/` and treat each hit.
4. Done looks like: no comment in `tests/` claims a check that its command set
   does not run; `pyproject.toml` and `.kiro/steering/change-protocol.md:92`
   agree on mypy's scope; and the full DoD command is green.

Not blocked by anything and touches no spec's boundary, but it edits shared
tooling config — check the shared agent log
(`$(git rev-parse --git-common-dir)/agent-log`) for an in-flight session before
starting, since `pyproject.toml` affects every worktree's validation at once.

## Resolution

**Done 2026-07-26** (queue sweep, merged to `main` at `e806c57`).

`c99d3ff`. Scoped option taken: `[tool.mypy] files` is `src` + the 5 modules carrying the claim, DoD now runs bare `uv run mypy`. Deliberately partial — sizing it found 5 of 10 stub-bearing modules still unguarded, with 6 live conformance failures already present, tracked at `2026-07-26-loadcalculator-stubs-outside-mypy-scope-have-drifted`.
