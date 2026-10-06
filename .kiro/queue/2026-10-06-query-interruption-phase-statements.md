---
id: 2026-10-06-query-interruption-phase-statements
title: Qualify query design statements about execution and fetch interruption phases
status: open
importance: low
importance_why: The planned timer ordering is correct, but the design overstates where DuckDB interruptions surface.
effort: S
kind: inconsistency
area: analytics-query, .kiro/specs/analytics-query/design.md
created: 2026-10-06
surfaced_by: /kiro-impl analytics-index task 8.4 floor diagnostic
pinned_at: 3cf3c2e
resume_command: "do: qualify analytics-query design U2 statements so errors and interruptions may surface during execute or fetch; preserve timer coverage of both phases [queue: .kiro/queue/2026-10-06-query-interruption-phase-statements.md]"
context:
  - .kiro/specs/analytics-query/design.md
  - .kiro/specs/analytics-query/tasks.md
  - src/fitdocs/index/store.py
  - tests/index/test_store.py
  - .kiro/specs/analytics-index/tasks.md
blocked_by: []
---

## What

The query design's U2 descriptions say execution streams/lazy evaluation
means errors and interruptions surface at fetch. The observed interruption
phase differs between supported DuckDB versions for the same aggregate.
State that both execute and fetch can surface the facade exceptions.

## Why it matters

The statements could lead a later test or implementation to arm cancellation
after execute returns. The planned `execute_statement` ordering already starts
the timer before execute and fetch; preserve that correct ordering.

## Evidence

- `.kiro/specs/analytics-query/design.md:197` says execution streams and
  interruptions surface at fetch; `:576` makes the same lazy-execution claim.
  `:773–776` correctly arms the timer before both operations.
- Authorized synthetic probes through the store facade observed
  `IndexInterrupted` during execute on DuckDB 1.2.0 and during fetch on 1.5.6,
  with the original `InterruptException` and matching nonempty messages.
  The controller inspected both raw phase outputs:
  `/private/tmp/analytics-index-evidence/8.4/remediation-interruption/phase-floor.txt`
  and `phase-current.txt`.
- The original fixture timed out because it started the timer after execute.
  The repaired test starts it first; independent review passed the same 62
  floor cases, preserving the original case and 60-second bound. See
  `/private/tmp/analytics-index-evidence/8.4/diagnostic-authorized/REPORT.md`
  and `/private/tmp/analytics-index-evidence/8.4/review-interruption/VERDICT.md`.
- These observations do not prove that every query executes eagerly in 1.2.0
  or lazily in 1.5.6. This is a design wording correction, not evidence of a
  defect in query's planned timer ordering.

## How to pick it up

1. Read the two U2 descriptions and the `execute_statement` timer contract.
2. Qualify both phase claims without changing the facade contract or floor.
3. Ensure planned tests cover errors/interruption at execute and fetch, and
   cancellation is armed before either can do expensive work. The existing
   store test supplies the real cross-version regression evidence.
