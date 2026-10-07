# Task 1.3: upstream preview propagation blocks acceptance

Task 1.3 remains unchecked. Its synthetic fixture and bounded importer guard
passed scoped verification (138 tests) and independent discrimination review
(64 claims, four new reviewer mutations; only the explicitly permitted
module-date pin remains UNPINNED). Review round 3 rejected an incorrect
statement creating-task annotation and the mandatory canonical regression
gate: 9,474 passed, two failed, two optional actionlint skips in 325.13 s.
The first live-preview test timed out on the initial edit at
`tests/sitebuild/test_preview.py:1143`; the second timed out waiting for a
deleted-route 404 at `:1165`. These are distinct stages. Candidate sources
were restored and hash-identical, and no external probes ran during the gate.

Fresh independent debugging returned `NEXT_ACTION: BLOCK_TASK`. A focused
diagnostic reproduced an initial-edit timeout after validation and sync had
completed: the generator process remained alive while generated HTML and HTTP
responses stayed stale. The native mechanism remains unknown. The diagnostic
second case passed deletion, then stalled on a later fix; it does not explain
the retained canonical deletion failure. No native repair, timeout weakening
or unchanged full-suite retry is justified by these observations.

Route the generator propagation investigation to the owning docs-site
boundary through `.kiro/queue/2026-10-06-preview-delete-readiness-race.md`.
After an independently verified causal owner repair, verify both exact
preview tests, sitebuild checks, the corrected task scope, and one serialized
canonical suite. Independent query tasks may proceed; tasks depending on
1.3 wait. Personal HealthFit data remains ready outside Git for both peers;
query timings still require the completed query command.

Private evidence: `/private/tmp/analytics-query-review-round3/verdict.md`,
`full-suite.txt`, `independent-exhaustive-sweep.json`, and
`/private/tmp/analytics-query-debug1-3/REPORT.md`, `events.jsonl`,
`stage-summary.json`, `source-integrity.json`. The original failed canonical
and failed diagnostic (two failures in 65.81 s) remain failed evidence.

## Historical task 1.1 interruption phase contract: correction approved

The Luna implementer made no edits and returned BLOCKED. Independent
`kiro-debug` returned SPEC_CONFLICT / STOP_FOR_HUMAN. At that initial block,
no implementation task was complete. Task 1.1 has since been accepted after
the approved correction below; feature-level validation has not run.

## Evidence

Task 1.1 requires the aggregate's interruption assertion to fail when
`IndexResult.fetchmany` rethrows the raw backend exception. Task 8.2 reruns
this test on DuckDB 1.2.0. Fresh independent read-only probes showed:

| DuckDB | Interruption phase | Raw-fetchmany mutation on real aggregate |
| --- | --- | --- |
| 1.2.0 | execute | passes: mutation survives |
| 1.5.6 | fetchmany | fails |

The independent debugger also observed a deterministic synthetic fetch
interruption assertion fail under that mutation on 1.2.0. After restoring
source, conversion pins, the real interruption regression, and the synthetic
fetch interruption pin passed: four tests on each version. Subprocesses were
bounded to 15 seconds; HOME directories stayed empty. These diagnostics
confirm the existing facade contract; they do not complete the query task.

## Correction approved on 2026-10-07

1. In task 1.1, start the 0.5-second interrupt timer before execute. Run the
   specified aggregate and `fetchmany(1)` inside one exception boundary;
   require chained `IndexInterrupted` from either operation within the
   existing 60-second subprocess bound. Record the observed phase.
2. Add a separate deterministic fetch interruption test using a
   non-forwarding synthetic backend relation that raises its
   `InterruptException` during `fetchmany`. Require `IndexInterrupted`,
   original cause identity, and matching message. Assign the raw-fetchmany
   mutation's interruption assertion to this test; retain the conversion
   error mutations and the real aggregate cancellation regression.
3. Qualify the U2 phase claims in design.md under Upstream Prerequisites and
   StoreFacadeAddition: exceptions may surface during execute or fetch.
   Preserve the dependency floor, facade contract, and timer coverage of
   both phases.

The maintainer explicitly approved this correction on 2026-10-07. The parent
applied the bounded task/design wording correction; a Luna implementer resumes
1.1 with fresh tests on both releases and independent review. Do not alter
production code to force the aggregate to interrupt in a particular phase.

The existing queue item
`.kiro/queue/closed/2026-10-06-query-interruption-phase-statements.md` tracks this
issue. The approved plan now incorporates only the bounded correction above; the
blocker annotation has been removed. Task 1.1 implementation and independent review are complete: round 3 APPROVED,
canonical 9,397 passed with two optional skips, and fresh parent query 10 passed.
The queue item moved to `closed/` with status done. Later feature tasks and
feature-level validation remain pending.


## Independent debugger transcript excerpts

The fresh diagnostics below were reported by the independent debugger.
Raw logs were printed in its tool transcript and were not saved separately;
temporary probe directories were removed automatically. Historical raw phase
outputs also remain under
`/private/tmp/analytics-index-evidence/8.4/remediation-interruption/phase-floor.txt`
and `phase-current.txt`.

```text
current exit=0 version=1.5.6 phase=fetchmany error=IndexInterrupted cause=InterruptException message=INTERRUPT Error: Interrupted!
floor exit=0 version=1.2.0 phase=execute error=IndexInterrupted cause=InterruptException message=INTERRUPT Error: Interrupted!

current-real-mutation exit=1
FAILED tests/index/test_store.py::test_interrupt_during_execute_or_fetch_is_wrapped_in_bounded_subprocess
1 failed in 1.96s

floor-real-mutation exit=0
1 passed in 0.75s

floor-synthetic-mutation exit=1
FAILED tests/index/test_store.py::test_facade_wraps_original_backend_errors_for_every_operation[fetchmany-True]
1 failed in 0.09s

source restored
current baseline exit=0: 4 passed in 0.81s
floor baseline exit=0: 4 passed in 0.75s
git diff --exit-code and git status --short: no output, exit=0
```
