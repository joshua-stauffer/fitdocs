# Implementation handoff — 2026-10-06

## Validation Report

- DECISION: NO-GO
- Branch: `impl/analytics-index`, parked without merging.
- Completed: 29 of 31 executable tasks, through 8.3, including the approved
  2.5 `document_load_basis` reader. All implementers used Luna.
- Integration: all 14 requirement sections and 94 criteria mapped to source
  and tests; this is not complete verification.
- Resolved: interruption fixture (`ce3e53e`) and annotation-only handoff import
  (`3cf3c2e`), both independently reviewed and pushed.
- Current blocker: two UTC runs failed the unchanged docs-site post-deletion
  preview assertion at `test_preview.py:1179`, HTTP 404 != 200.
- Ownership: UPSTREAM, docs-site preview synchronization. Task 8.4 exhausted
  its two debug cycles and remains blocked; no third cycle was run.
- Task 8.5 real-data measurements remain maintainer-only and pending.
- CI mode, static checks after failed UTC pytest, and final build/artifact
  smoke were not run. No feature-level GO is claimed.

## Resolved findings

The authorized DuckDB 1.2.0 diagnostic proved that the original test remained
inside execute before it could start its timer. Pre-arming cancellation
interrupted execute at about 0.53 seconds, preserving cause/message and closing
cleanly. Synthetic HOME stayed empty. The repaired fixture retains the query,
60-second bound and all selected cases. Its observed interruption phase is
execute on 1.2.0 and fetch on 1.5.6. Independent review passed 62 floor cases,
91 store tests, and three claimed plus two reviewer mutation controls. No floor
or runtime policy changed. The original 61-pass/one-timeout run remains failed.

The handoff import is now under TYPE_CHECKING, with behavior AST unchanged.
Exact owner annotations remain independently checked using explicit localns.
Its bounded clean-process guard failed against the original runtime import.
Independent review passed four claimed and two reviewer controls, 80 scoped
and 9,386 regression tests, with two expected skips.

## Task 8.4 results

Final fetch/rebase onto origin/main f36bf46 required no change. The local
mypy diff appends all 27 new Python test files; no entries were removed.
It remains **uncommitted and unreviewed**, since final validation failed.
Its exact text is preserved in `pending-mypy-registration.patch` beside this
report; the original local pyproject diff also remains available.

| Check | Result |
|---|---|
| Fresh DuckDB 1.2.0 floor selection | 62 passed; existing synthetic HOME empty |
| Registered canonical mypy | 340 files passed |
| Plain full suite | 9,386 passed, two expected skips; exit 0 |
| Plain Ruff / format / mypy | All exit 0 |
| First UTC full suite | 9,385 passed, one failure, two skips; exit 1; 379.31s |
| Unchanged UTC retry after debug2 | Same 9,385 / one failure / two skips; exit 1; 269.65s |
| CI mode | Unrun after repeated UTC failure |
| Versions | Contract 9 = current main 8 + 1; schema 1 |

The repeated failure is the known deletion/break readiness branch, distinct
from prior initial-edit/added-page deadlines. Preview code, tests and dependency
bytes match the causal baseline; the current assertion-time timeline was not
captured. Both failed runs remain failed evidence. The owning repair is tracked
in `.kiro/queue/2026-10-06-preview-delete-readiness-race.md`.

## Resume

1. Repair synchronization through the owning docs-site work and queued evidence.
   Preserve HTTP, content, error-report and source-preservation assertions.
   Do not add a workaround to analytics-index.
2. Reclaim analytics-index; inspect the preserved registration diff or patch
   against the current added-module inventory. Rebase onto current main.
   Resume independently reviewed registration/floor/plain/UTC/CI/static gates.
3. Use Python 3.11.15, the warmed uv cache, `uv run --group docs pytest`, and
   the established forbidden-strings gate, without printing its data. Floor
   tests use the separate 1.2.0 venv and an existing empty synthetic HOME.
   Build release artifacts and smoke the installed artifact for final validation.
4. Only the maintainer runs 8.5: rebuild wall time/file size, no-change sync
   index-pass time, and five-file sync index-pass time. Record numbers only in
   research/Implementation Notes and assess the required performance target.
5. Rerun feature integration validation. Merge and tick the analytics-index
   roadmap entry only after all required gates pass.

Raw evidence under `/private/tmp/analytics-index-evidence/`:
`8.4/diagnostic-authorized/`, `8.4/review-interruption/`,
`final/handoff-review/`, `8.4/final-plain/`, `8.4/final-utc/`,
`8.4/debug2-preview/`, `8.4/final-utc-debug2-retry/`, and
`final/VALIDATION_REPORT.md`.

Adjacent queue work: interpreter-fixture path, mypy perimeter coverage, preview
readiness, and query design interruption-phase wording. Query's planned timer
already covers execute and fetch; the last item corrects wording only.
