---
id: 2026-07-27-cli-config-error-byte-identity-vacuous
title: The older CLI config-error tests assert byte-identity in fixtures that write nothing either way
status: open
importance: medium
importance_why: Each of these tests presents "nothing was written" as proven while its fixture makes that outcome unconditional, so the abort-before-write ordering they appear to guard is unguarded.
effort: S
kind: gap
area: tests/test_cli.py, training-load
created: 2026-07-27
surfaced_by: /kiro-impl athlete-benchmarks (task 5.3 review, rounds 1 and 2)
pinned_at: bb5ab9d
resume_command: "do: give tests/test_cli.py:324's config-error test the registered-stub fixture so its byte-identity assertion can fail, or state plainly that the clause is unpinned there [queue: .kiro/queue/2026-07-27-cli-config-error-byte-identity-vacuous.md]"
context:
  - tests/test_cli.py
  - src/fitdocs/load/engine.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

`tests/test_cli.py::test_malformed_load_table_exits_two_and_writes_nothing`
(around `:324`, landed by `training-load` task 4.2) asserts that a configuration
error leaves the workout document byte-identical. In its fixture no calculator is
registered, so the load pass writes nothing **whether it aborts up front or runs
to completion** — the assertion cannot fail under any implementation.

`athlete-benchmarks` task 5.3 shipped a clone of this test and was rejected twice
for the same defect before the fixture was strengthened. The original remains as
written.

## Why it matters

This is the **indistinguishable outcome** anti-pattern named at
`.kiro/steering/change-protocol.md:172`. The test reads as proof that a
configuration error aborts before any write; it proves only that the command
exits 2. A future change that deferred the `[load]` validation until after the
document loop would keep this test green while silently writing documents during
a failing run.

## Evidence

- Probe on the equivalent fixture: with a *valid* `[load]` table the same data
  root runs to completion at `Computed 0 / Restored 0 / Unsupported 0 /
  Skipped 0 / Failed 0`, `doc_changed=False`. The data root is unchanged either
  way.
- Deferring the `[load]` projection at `src/fitdocs/load/engine.py:269` until
  after the document loop left the un-strengthened test **passing**.
- The working fix, measured twice during task 5.3: register the stub calculators
  (`_register_stub_calculators()`, `tests/test_cli.py:1035`) and set
  `default_calculator = "cli-stub-a"` in the same `[load]` table. The fixture then
  reports `Computed 1` and genuinely rewrites the document, so the abort becomes
  the only reason it stays byte-identical — and the deferral mutation reds it as a
  sole failure.
- The already-correct pattern to copy lives at `tests/test_cli.py:397` and, after
  task 5.3, at `tests/test_cli.py:339` and `:395`.

## How to pick it up

1. Read `tests/test_cli.py:339` (the strengthened staleness test) as the template.
2. Apply the same `try/finally` stub registration and `default_calculator` line to
   the test at `:324`, plus the computable-and-uncomputed precondition assertions.
3. Verify by deferring the `[load]` projection at `engine.py:269` past the
   document loop — the test must now red. Revert via a scratch copy, never
   `git checkout`.
4. Done looks like: every CLI config-error test asserting byte-identity reds under
   an ordering mutation, or says in its docstring that it does not.
