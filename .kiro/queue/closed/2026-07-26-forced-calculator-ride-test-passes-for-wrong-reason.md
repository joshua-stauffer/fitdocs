---
id: 2026-07-26-forced-calculator-ride-test-passes-for-wrong-reason
title: The forced-calculator ride test registers one calculator, so it cannot observe that --calculator was honored
status: done
importance: medium
importance_why: It is the test named for Requirement 8.4 at the CLI boundary, and it passes identically whether the flag is threaded or ignored — so the requirement it advertises is covered by its docstring, not its assertions.
effort: S
kind: gap
area: training-load, tests/load/test_cli_load.py
created: 2026-07-26
surfaced_by: /kiro-impl training-load (task 4.2, requirement sweep)
pinned_at: 12caa6e
resume_command: "do: register a second, differently-identified calculator in tests/load/test_cli_load.py::test_load_calculator_stub_yields_unsupported_on_ride so that dropping --calculator threading in cli.py changes the outcome, and assert the forced calculator is the one that ran"
context:
  - tests/load/test_cli_load.py
  - src/fitdocs/cli.py
  - .kiro/specs/training-load/requirements.md
  - tests/load/conftest.py
blocked_by: []
---

## What

`tests/load/test_cli_load.py:352`
`test_load_calculator_stub_yields_unsupported_on_ride` documents itself as
covering Requirement 8.4:

> "A forced ``--calculator`` uses only that calculator; a ride it cannot score
> becomes the honest unsupported state (Req 8.4, 1.3)."

It registers **one** calculator (`computing_calculator`, via `isolated_registry`).
With a single calculator in the registry, arbitration selects that same
calculator whether `--calculator` was supplied, ignored, or never parsed — and
the ride is unsupported either way. The assertions therefore hold identically
under a broken flag.

Mutation: hardcoding `calculator_id=None` at `src/fitdocs/cli.py:579` leaves this
test **green**.

The 1.3 half (a ride the calculator cannot score reaches the honest unsupported
state) *is* genuinely covered. It is the 8.4 half — "uses **only** that
calculator" — that the fixture cannot observe.

## Why it matters

`medium`. Requirement 8.4's CLI-level threading is not left entirely
unprotected — task 4.2 added
`tests/test_cli.py::test_calculator_flag_overrides_configured_default`, and
`tests/load/test_cli_load.py::test_load_unknown_calculator_exits_two` also
reddens under the same mutation. So the flag is pinned *somewhere*.

The problem is this test's **name and docstring advertise a guarantee its body
does not make**, which is worse than an absent test: a later reviewer sweeping
Requirement 8.4 finds it, reads the docstring, and marks the requirement covered
without running a mutation. That is precisely the failure mode this spec has
lost five review rounds to, recorded in `tasks.md` `## Implementation Notes`
under "From task 4.1".

## Evidence

Verified in this run at `12caa6e` (branch `impl/training-load`):

- `tests/load/test_cli_load.py:352-358` — the test signature takes
  `isolated_registry` and `computing_calculator` only; **one** calculator is
  registered.
- Mutation `calculator_id=None` at `src/fitdocs/cli.py:579` → this test stays
  green (reported by the task-4.2 reviewer's sweep, which ran it as part of
  classifying Req 8.4).
- The requirement's CLI-level threading is separately pinned by
  `tests/test_cli.py::test_calculator_flag_overrides_configured_default` (added
  by task 4.2) and `tests/load/test_cli_load.py::test_load_unknown_calculator_exits_two`,
  which is why this is `medium` and not `high`.

## How to pick it up

1. Open `tests/load/conftest.py` and pick a second stub with a **different**
   `calculator_id` — the load suite already ships four. The second one must be a
   calculator arbitration would otherwise select, so that ignoring `--calculator`
   produces a visibly different outcome.
2. Register both in `test_load_calculator_stub_yields_unsupported_on_ride`, force
   the first with `--calculator`, and assert the outcome identifies **which**
   calculator ran — the summary line carries the `[<calculator-id>]` detail for
   computed documents, which is the cheapest observable.
3. Beware the shadowing trap recorded in `tasks.md` `## Implementation Notes`:
   most conftest stubs self-guard their modality inside `compute`, so a stub's
   own defence-in-depth can mask the engine's behaviour. Check which branch
   actually executes before claiming the test covers it.
4. Verify by mutation: `calculator_id=None` at `src/fitdocs/cli.py:579` must now
   redden this test. Restore byte-identically and confirm green.
5. Done looks like: the test's docstring claim about Req 8.4 is true of its
   assertions, and the mutation reddens it.

Fold into task 6.3, which already proves the command surface with an empty
registry and is the natural home for multi-calculator CLI cases.


## Resolution

**Done 2026-07-26** — `17ff697`, branch `chore/queue-top-ten`.

Renamed to `test_load_calculator_forces_that_calculator_and_rides_stay_unsupported`
and given a second RUN calculator, `_FieldFreeCalculator`, which requires no
athlete input -- necessary because every `tests.load.conftest` stub declares a
required field, so forcing one under `CliRunner`'s non-interactive session lands
in `MissingInputs` and prints no `[<calculator-id>]` detail at all.

It raises rather than self-guarding on a non-RUN activity, so it cannot shadow
the engine's own prefilter (the trap in `tasks.md` Implementation Notes).

With two supporters and no configured default the run is an unresolved ambiguity
(Req 10.2), so `[stub-field-free]` appears iff the flag reached arbitration.
Under `calculator_id=None` at `cli.py:577` the output becomes "more than one
calculator supports this activity (stub-computing, stub-field-free)" and the
identity assertion dies -- verified.

Not sole failure: the three sibling tests the item already named redden under
the same mutation. The point was that this test now discriminates rather than
advertising.
