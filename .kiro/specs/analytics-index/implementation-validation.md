# Implementation handoff — 2026-10-06

## Interruption update

The maintainer authorized the bounded diagnostic. It confirmed that the test
started its timer after a potentially expensive execute call. A reviewed
test-only repair now arms the timer first and preserves interruption mapping,
cause/message and the original 60-second deadline. Fresh floor: 62/62 passed,
existing synthetic HOME empty; current store: 91/91; full regression: 9,385
passed, two expected skips. No dependency or runtime policy changed. The floor
stop is resolved; the historical failed run below remains failed evidence.
Handoff import repair and the remaining task 8.4/8.5 checks are still pending.


## Validation Report

- DECISION: NO-GO
- Branch: `impl/analytics-index`, parked without merging.
- Completed: 29 of 31 executable tasks, through 8.3, including the approved
  2.5 `document_load_basis` reader prerequisite. All implementers used Luna.
- Latest approved full regression: 9,385 passed, two expected actionlint
  skips; mypy, Ruff, format, help and diff checks passed for task 8.3.
  This does not satisfy the remaining three-mode validation in 8.4.
- Final fetch/rebase: `origin/main` was `f36bf46`; no rebase change required.
- Integration: all 14 requirement sections and 94 criteria mapped to source
  and tests in a read-only assessment. Mapping is not complete verification.
- LOCAL blocker: `src/fitdocs/index/handoff.py:9` imports `sync.RenderedPage`
  at runtime, contrary to the design's `TYPE_CHECKING`-only allowance.
- Resolved floor blocker: the selected DuckDB 1.2.0 suite now passes after
  the reviewed timer-order repair. The earlier failure is retained below.
- Manual work: task 8.5's real-data performance measurements remain pending.
- Final build and built-artifact smoke: unrun after the floor stop.

## Floor evidence

Python 3.11.15, DuckDB 1.2.0, separate scratch venv. The 35 selected
pre-DDL policy, facade and classification functions expanded to 62 cases:
**61 passed, one failed**, exit 1, 61.64 seconds. The failure was
`tests/index/test_store.py::test_interrupt_at_fetch_is_wrapped_in_bounded_subprocess`:
its child exceeded the existing 60-second bound without stdout/stderr phase
output. The existing run-level synthetic HOME remained empty.

The child executes a huge aggregate before starting its interruption timer.
Execution before timer creation is a plausible explanation, but the observed
timeout does not locate the stall. Mandatory settings and classification cases
passed; this is not evidence of a safety-settings failure or proof that the
declared floor is unusable. The selected failing case must not be silently
excluded. No floor, test, runtime or mypy-registration change was made in 8.4.

Raw evidence on the implementation machine:

- `/private/tmp/analytics-index-evidence/8.4/floor/floor-test-output.txt`
- `/private/tmp/analytics-index-evidence/8.4/floor/selectors.txt`
- `/private/tmp/analytics-index-evidence/8.4/floor/floor-summary.txt`
- `/private/tmp/analytics-index-evidence/8.4/debug1/REPORT.md`
- `/private/tmp/analytics-index-evidence/final/integration.md`

## Resume

1. The authorized floor diagnostic and test repair are complete. Preserve
   their evidence in `diagnostic-authorized` and `review-interruption` under
   the scratch evidence directory. Any future dependency-floor change still
   requires the roadmap decision specified in task 8.4.
2. Repair the handoff import through a Luna implementer. Guard `RenderedPage`
   with `TYPE_CHECKING`, retaining its exact annotations and behavior. Give
   annotation introspection tests explicit `localns` containing the owner's
   `RenderedPage`. Add a clean-process import-isolation pin, prove original
   source RED and repair GREEN, and discriminate a reintroduced runtime import.
   Obtain independent review before committing the repair.
3. Resume 8.4: register every added Python test module in the curated mypy list;
   pass the agreed floor selection with existing empty synthetic HOME; perform
   the final rebase and full validation in plain, `TZ=UTC`, and `CI=true` modes.
   Use the warmed uv cache, Python 3.11.15, `uv run --group docs pytest`, the
   existing forbidden-string gate, Ruff, format and mypy. Recheck contract
   version as main plus one and schema version 1. Build release artifacts and
   smoke the installed artifact for feature validation.
4. The maintainer alone runs 8.5: rebuild wall time/file size, no-change sync
   index-pass time, and five-file sync index-pass time. Record only numbers in
   research/Implementation Notes. Assess the required no-op performance target.
5. Rerun feature integration validation. Merge and tick the analytics-index
   roadmap entry only after all required gates pass.

Existing adjacent follow-ups remain in the queue: the interpreter-fixture path,
mypy perimeter coverage, and preview deletion readiness. Distinct initial-edit
and added-page preview timeouts remain unresolved observations in the latter;
they are not explained by the known deletion race. Current acceptance blockers
are tracked in task 8.4 and this report, rather than deferred to that queue.
