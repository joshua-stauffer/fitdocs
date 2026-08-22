---
id: 2026-07-26-ruff-format-not-gated
title: Decide whether `ruff format` joins the validation gate — ~40 files are non-conformant
status: done
importance: low
importance_why: Not currently gated, so nothing is broken; but files drift in and out of format-clean per session with no rule, and each session must re-derive that `ruff format` is not the standard.
effort: S
kind: chore
area: tooling, pyproject.toml, .kiro/steering/change-protocol.md
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 1.3 final reviewer FOLLOW_UPS)
pinned_at: 03e0f38
resume_command: "do: decide whether `uv run ruff format --check .` joins the src/tests validation gate in change-protocol.md, and if so reformat the ~40 non-conformant files in one mechanical commit [queue: .kiro/queue/2026-07-26-ruff-format-not-gated.md]"
context:
  - .kiro/steering/change-protocol.md
  - pyproject.toml
blocked_by: []
---

## What

`.kiro/steering/change-protocol.md` defines the gate for `src/`, `tests/` and
`pyproject.toml` changes as `uv run pytest && uv run ruff check . && uv run
mypy src/`. `ruff format` is deliberately absent, so formatting is unenforced.

As a result files drift: `tests/test_benchmarks.py` was `ruff format`-clean at
task 1.2 and is not clean after task 1.3, and roughly 33 files repo-wide are
already non-conformant. Nothing fails, because nothing checks.

## Why it matters

This is not a correctness issue and should not be treated as urgent. It is a
recurring small tax: every session that runs `ruff format` incidentally — or
notices a diff is noisier than its change — has to re-derive that formatting is
not part of the standard, and decide ad hoc whether to reformat. Task 1.3's
reviewer spent effort establishing this was not a rejection ground.

Two coherent end states, either of which is better than the present drift:
add `ruff format --check .` to the gate and reformat once, or state explicitly
in `change-protocol.md` that formatting is intentionally unenforced so future
sessions stop re-litigating it.

The cost of deciding is small and it removes a recurring judgment call. The
cost of adopting it is one mechanical commit touching ~33 files, which is
cheapest done in isolation rather than tangled into a feature diff — and which
argues for doing it between specs rather than mid-spec.

## Evidence

- `.kiro/steering/change-protocol.md` — the validation-by-class table lists
  `uv run pytest && uv run ruff check . && uv run mypy src/` for
  `src/`, `tests/`, `pyproject.toml`.
- Task 1.3 final reviewer, FOLLOW_UPS 3: "`tests/test_benchmarks.py` was
  `ruff format`-clean at base and is not clean in the working tree. Not gated
  (the project runs `ruff check`, not `ruff format`), and 33 files repo-wide
  are already non-conformant."
- `uv run ruff check .` and `uv run mypy --strict src/` are clean at
  `03e0f38`; only formatting differs.

## How to pick it up

1. Run `uv run ruff format --check .` to get the current non-conformant list
   and confirm the count.
2. Decide with the repo owner: gate it, or document it as intentionally
   ungated. There is no third state worth keeping.
3. If gating: reformat in one commit that touches nothing else, add
   `uv run ruff format --check .` to the `src/`/`tests/` row of
   `change-protocol.md`'s validation table, and do it while no spec is
   mid-flight — a 33-file reformat colliding with an in-flight branch is a
   guaranteed rebase conflict. Two specs are active as of this writing.
4. If not gating: add one line to `change-protocol.md` saying so, so the
   question stops recurring.
5. Done looks like: a session can answer "is `ruff format` part of green?" from
   `change-protocol.md` alone, without running anything.

## Open questions

- Is the omission deliberate (a considered choice to keep the gate fast and
  avoid churn) or incidental? That determines which end state is correct, and
  it is the repo owner's call, not a session's.

## Resolution

Closed 2026-07-29. Both halves the item asked for have landed. The decision
went in favour of gating: `.kiro/steering/change-protocol.md`'s Validation By
Class table now names `uv run ruff format --check .` in the
`src/`, `tests/`, `pyproject.toml` row alongside pytest, ruff check and mypy.
The ~40 non-conformant files were reformatted — `uv run ruff format --check .`
on `main` at `84008a6` reports "174 files already formatted", so the gate is
green rather than merely declared.
