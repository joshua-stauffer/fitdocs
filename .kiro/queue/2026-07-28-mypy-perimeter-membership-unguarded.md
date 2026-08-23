---
id: 2026-07-28-mypy-perimeter-membership-unguarded
title: Nothing guards `[tool.mypy].files` membership, so deleting a test module's line silently degrades the type-check perimeter
status: open
importance: medium
importance_why: The perimeter is opt-in per test module and every command stays green when an entry is removed, so a type-level observable reverts to vacuous with no signal at all. Now confirmed TWICE IN ONE DAY by independent reviewers. (1) fit-ingest task 8.1's Req 16.4 negative is enforced ONLY by `tests/test_citation.py` being inside the perimeter; deleting that one line takes mypy 71 -> 70 files, leaves the widening mutation completely undetected, and leaves `uv run pytest` at 2108 passed. (2) task 8.2's explicit `as` re-export in `load/channels/sources.py` is load-bearing under `no_implicit_reexport`, yet collapsing it leaves pytest, ruff, ruff format AND mypy all green because `tests/load/channels/` is not in the list. The second is an ordinary refactor, not a type-level observable someone opted into — which is what makes this a general hazard rather than an 8.1 quirk.
effort: S
kind: gap
area: pyproject.toml, tests/test_docs_guarantees.py, fit-ingest
created: 2026-07-28
surfaced_by: /kiro-impl fit-ingest (task 8.1 review, round 1 FOLLOW_UPS; re-confirmed by paired probe in round 4)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-28-mypy-perimeter-membership-unguarded.md] Guard that every test module carrying a type-level observable stays inside the mypy perimeter"
context:
  - pyproject.toml
  - tests/test_docs_guarantees.py
  - tests/test_citation.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

`pyproject.toml`'s `[tool.mypy].files` enumerates checked test modules one by
one, and the long comment above the list explains why the perimeter is
deliberately explicit. Nothing asserts that the list still contains the modules
whose coverage depends on being in it. Removing an entry is a one-line,
green-on-every-command regression.

This is the mirror of a problem the repo already solved in the other direction:
`docs/plugins.md`'s public-surface list and plugin-api's `design.md` enumeration
have each gone stale repeatedly, and the fix each time was a mechanical guard.
The mypy perimeter has the same shape — a hand-maintained list that silently
stops covering what it claims to cover — and no guard.

## Why it matters

A test module inside the perimeter can pin a claim that is *only* checkable
statically. fit-ingest task 8.1 uses exactly this: `FitdocsChoice.verification`
is `Literal[VerificationStatus.FITDOCS_MEASURED]`, so annotating a
fitdocs-chosen value with `PRIMARY_TEXT` fails `mypy --strict` rather than
constructing — which is how Requirement 16.4 ("never conflate a chosen value
with a sourced one") is enforced by the type system instead of by review. The
negative is pinned by a `# type: ignore[...]` that mypy reports as
`unused-ignore` if the error ever stops occurring.

Delete `"tests/test_citation.py"` from the list and that entire mechanism goes
quiet. Both `uv run pytest` and `uv run mypy` still pass. The task's own
observable — "demonstrated from a module the checker actually reads" — becomes
vacuous, which is the precise failure mode the task bullet was written to
prevent.

More generally: every future task that pins a `mypy`-only claim inherits this
hole, and the failure is invisible rather than noisy.

## Evidence

At `8e3cb05`, in a worktree on `impl/fit-ingest`, the round-4 reviewer ran a
paired probe:

- With `"tests/test_citation.py"` present in `[tool.mypy].files`, widening
  `FitdocsChoice.verification` from `Literal[VerificationStatus.FITDOCS_MEASURED]`
  to plain `VerificationStatus` →
  `tests/test_citation.py:308: error: Unused "type: ignore" comment [unused-ignore]`,
  exit 1. Caught.
- With that one line removed and the *same* widening applied →
  `uv run mypy` reports `Success: no issues found in 70 source files`, exit 0.
  Completely undetected. `uv run pytest` → 2108 passed.

The round-1 reviewer independently found the same thing before the widening
mutation existed: removing the line alone gives `Success ... 70 source files`
with the suite green.

**Second, independent instance — found the same day in task 8.2 (`067a30e`).**
`src/fitdocs/load/channels/sources.py` re-exports the shared vocabulary with
explicit aliasing:

```python
from fitdocs.citation import Citation as Citation
from fitdocs.citation import VerificationStatus as VerificationStatus
```

The `as` form is load-bearing, because `no_implicit_reexport` means a plain
`from fitdocs.citation import Citation` does not re-export. Proven by an
out-of-band probe module importing both names *from* `sources.py`:
`uv run mypy --strict --no-incremental` passes with the aliases and fails
without them (`Module "fitdocs.load.channels.sources" does not explicitly
export attribute "Citation"`, 2 errors).

**But the whole validation set is blind to it.** With the aliases collapsed to
the plain form: `uv run pytest` → 2112 passed, `uv run ruff check .` clean,
`uv run ruff format --check .` clean, `uv run mypy` → "Success: no issues found
in 71 source files". All green, static re-export silently broken. The cause is
the same hole — `tests/load/channels/` is absent from `[tool.mypy].files`, and
that is the only place importing those names from `sources.py`.

This second instance matters because it is not a type-level *observable* a task
chose to write; it is an ordinary refactor whose correctness has a static half
that no command in the Definition of Done can see. The generalization worth
recording: **absence of a type error is not evidence of type safety for any
module you have not confirmed is inside the perimeter.**

**Third instance — a whole test module never entered the perimeter at all
(2026-07-29, `4449d3e`).** Task 10.1 added 157 lines to
`tests/metrics/test_aggregates.py`, and that module is absent from
`[tool.mypy].files` entirely — so `uv run mypy` reports
`Success: no issues found in 73 source files` with and without the diff, and
the implementer's "mypy clean" claim was true but vacuous for the test half of
its own change. This is the same hole from the other direction: the earlier
instances were a line *removed* from the list, this one is a line never
*added*. `grep -n 'test_aggregates\|test_power' pyproject.toml` returns
nothing, while `tests/metrics/test_sources.py` is listed. Whatever guard closes
this should therefore assert membership for the test modules the spec relies
on, not merely detect deletions from the existing list.

## How to pick it up

1. Read the comment above `files = [...]` in `pyproject.toml` — it states the
   perimeter's rationale and warns that adding a module and fixing its errors
   must happen in the same change. Any guard must not contradict it.
2. Read `tests/test_docs_guarantees.py` for the established mechanical-guard
   idiom in this repo (it already guards `docs/plugins.md` bidirectionally
   against the package root's public surface). The natural home for this guard
   is either that module or a sibling.
3. Decide what the guard asserts. The weak form — "the list parses and every
   named path exists" — catches a typo but not a deletion, which is the actual
   failure. Stronger options, in rough order of cost: (a) every test module
   containing a `# type: ignore[` that is load-bearing must be listed;
   (b) a declared inventory in the test itself, so removing a `pyproject.toml`
   entry reds; (c) every `tests/**/*.py` importing from a module in `src/` and
   asserting a type-level claim. Pick the one that fails on deletion.
4. Done looks like: deleting any single entry from `[tool.mypy].files` reds a
   named assertion, and adding a new checked test module requires exactly one
   obvious edit. Per `.kiro/steering/change-protocol.md` § Fixture
   Discrimination, prove it by running that deletion as the mutation — a guard
   never shown to fail is not a guard.

## Open questions

Whether the guard should enumerate the perimeter's expected contents (simple,
but a second list to keep in sync — the very defect being fixed) or derive the
requirement from the test tree (no second list, but needs a rule for which
modules qualify). The derived form is better if a clean rule exists; the
enumerated form is acceptable only if removing an entry from `pyproject.toml`
without updating the guard reds.
