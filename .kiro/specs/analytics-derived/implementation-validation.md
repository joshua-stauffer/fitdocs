# Analytics-derived implementation validation

Validated 2026-10-07 at `3b11bc2`, after final rebase onto main `995db58`.
This report records validation readiness; merge-back and the pushed main SHA
are recorded separately in the shared append-only agent log after landing.

## Validation Report

- DECISION: GO
- MECHANICAL_RESULTS:
  - Tests: PASS — fresh complete-branch canonical full suite, 9,629 passed,
    2 expected actionlint skips, 325.02 seconds, actual exit 0.
  - TBD/TODO/FIXME/HACK/XXX scan: CLEAN in introduced production lines.
  - Secrets scan: CLEAN in introduced production lines.
  - Ruff check, Ruff format, mypy: PASS, all actual exit 0; 552 files already
    formatted and 367 source files type-checked.
  - Build/artifacts: PASS — one wheel and one source distribution built from
    the working candidate, artifact and forbidden-content gate exit 0.
  - Fail-closed gate: VERIFIED — unset match data yields expected exit 1 and
    `gate_not_run`, rather than a passing skipped gate.
  - Smoke boot: PASS — offline wheel install into isolated tool directories;
    absolute installed binary `--version`, `--help`, `plugins`, and `skill`
    all exit 0. Version output agrees with the manifest.
- INTEGRATION:
  - Cross-task contracts: aligned; public engine computations feed projections.
  - Shared state: core-first registry, four derived producers, eleven new tables,
    24 tables total; schema 2 is exactly landing-base schema 1 plus one.
  - Boundary audit: clean; owning refresh/store remain unchanged, goldens and
    document/ownership declarations preserved, no runtime dependency added.
- COVERAGE: all 10 sections / 64 acceptance criteria mapped; no local gap.
- DESIGN: all 13 components present; no architecture or dependency-direction
  drift; file layout and allowed seams agree with the design.
- OWNERSHIP: LOCAL
- UPSTREAM_SPEC: N/A — earlier upstream preview and core index fixture failures
  were repaired by their owners and the final gates include those landed fixes.
- BLOCKED_TASKS: none; 20/20 leaf tasks and 6/6 groups complete.
- REMEDIATION: none.

## Verification Result

- STATUS: VERIFIED
- CLAIM_TYPE: FEATURE_GO
- CLAIM: analytics-derived meets the approved feature plan and is ready to land.
- EVIDENCE: fresh complete-branch full suite and statics; independent 64-criterion,
  13-component coverage/integration review; built artifact startup; all tasks
  independently accepted; frozen input hashes checked after final validation.
- GAPS: none for the first-lander branch. Requirement 10.4's later publication
  remains explicitly owned by analytics-query task 7.3, as both approved plans
  require. Query is absent from the validated main base; the three bounded
  read-side files are untouched.

## Canonical gates and environment

All commands use the default warm uv cache (`UV_CACHE_DIR` unset) and the
external forbidden-string source via `FITDOCS_FORBIDDEN_STRINGS`. The docs
optional dependency group is installed. Python is the canonical pyenv 3.11.15.
No match-data contents are included in this report.

`uv run --group docs pytest`, `uv run ruff check .`,
`uv run ruff format --check .`, and `uv run mypy` all passed in each mode.

| Gate | Pytest passed / skipped | Pytest seconds | Exit | Ruff / format / mypy |
|---|---:|---:|---:|---|
| Task 6.3 plain, TZ and CI unset | 9,629 / 2 | 288.84 | 0 | all exit 0 |
| Task 6.3 TZ=UTC, CI unset | 9,629 / 2 | 290.92 | 0 | all exit 0 |
| Task 6.3 CI=true, TZ unset | 9,629 / 2 | 287.31 | 0 | all exit 0 |
| Independent task 6.3 plain | 9,629 / 2 | 296.33 | 0 | all exit 0 |
| Final complete-branch plain | 9,629 / 2 | 325.02 | 0 | all exit 0 |

Both skips are tests requiring unavailable actionlint. Initial task 6.3 plain
and UTC launches hit restricted default-cache access before collection (exit 2);
these are retained as environment failures. Authorized default-cache canonical
runs passed. Earlier rejected gates and remediation evidence remain historical;
none is silently substituted for the fresh passing results above.

The exact 108 existing mypy paths remain the ordered prefix, including main's
27 core index entries; all 19 feature test/fixture modules are appended. Runtime
dependencies remain the same six entries. DOC_VERSION and CONTRACT_VERSION
remain 9; MANAGED_KEYS and uv.lock are unchanged. All 618 frozen source/test/config
files match the independently reviewed, built and three-mode-tested candidate.
The candidate manifest SHA-256 is
`12cdd50eccf11a2617f9901082978a5bd98599c8ef3cca07451f3bdd1a80de07`.

## Task outcomes

Every implementer returned READY_FOR_REVIEW and received an independent
APPROVED task verdict. All implementers were Luna; the latest user instruction
restored standard harness reuse. Individual mutation logs and qualified RED
chronology are recorded in Implementation Notes and the local evidence archive.

| Task | Implementer status | Review verdict | Accepted code/record commit | Changed files |
|---|---|---|---|---|
| 1.1 | READY_FOR_REVIEW | APPROVED | `d546ab2` | `.kiro/queue/2026-10-06-preview-delete-readiness-race.md`, `.kiro/specs/analytics-derived/implementation-blocker.md`, `src/fitdocs/metrics/mean_max_sources.py`, `tests/metrics/test_mean_max_sources.py` |
| 1.2 | READY_FOR_REVIEW | APPROVED | `a7a7b5f` | `src/fitdocs/index/derived/__init__.py`, `tests/index/derived/__init__.py`, `tests/index/derived/conftest.py`, `tests/index/derived/test_fixtures.py` |
| 1.3 | READY_FOR_REVIEW | APPROVED | `f7a68f6` | `src/fitdocs/index/derived/inputs.py`, `tests/index/derived/test_inputs.py` |
| 2.1 | READY_FOR_REVIEW | APPROVED | `cef5f92` | `src/fitdocs/metrics/mean_max.py`, `tests/metrics/test_mean_max.py` |
| 2.2 | READY_FOR_REVIEW | APPROVED | `fe1ddab` | `src/fitdocs/history/__init__.py`, `src/fitdocs/history/engine.py`, `src/fitdocs/history/page.py`, `tests/history/test_compute_seam.py`, `tests/test_public_api.py` |
| 2.3 | READY_FOR_REVIEW | APPROVED | `04162f6` | `src/fitdocs/plans/__init__.py`, `src/fitdocs/plans/engine.py`, `src/fitdocs/plans/reconcile.py`, `tests/plans/test_resolve_seam.py`, `tests/test_public_api.py` |
| 3.1 | READY_FOR_REVIEW | APPROVED | `218fefe` | `src/fitdocs/index/derived/mean_max.py`, `tests/index/derived/test_mean_max_producer.py` |
| 3.2 | READY_FOR_REVIEW | APPROVED | `69bd13d` | `src/fitdocs/index/derived/load_series.py`, `tests/index/derived/test_load_series_producer.py` |
| 3.3 | READY_FOR_REVIEW | APPROVED | `776f560` | `src/fitdocs/index/derived/benchmarks.py`, `tests/index/derived/test_benchmark_producer.py` |
| 3.4 | READY_FOR_REVIEW | APPROVED | `f4ce7c7` | `src/fitdocs/index/derived/blocks.py`, `tests/index/derived/test_block_producer.py` |
| 4.1 | READY_FOR_REVIEW | APPROVED | `35ff0a5` | `src/fitdocs/index/registry.py`, `src/fitdocs/index/schema.py`, `tests/index/derived/test_registration.py`, `tests/index/test_schema.py`, `tests/index/test_schema_version.py` |
| 4.2 | READY_FOR_REVIEW | APPROVED | `aae9a97` | `tests/index/derived/test_boundary.py` |
| 5.1 | READY_FOR_REVIEW | APPROVED | `953ee7e` | `tests/index/derived/test_refresh.py` |
| 5.2 | READY_FOR_REVIEW | APPROVED | `10ff27a` | `tests/index/derived/test_determinism.py` |
| 5.3 | READY_FOR_REVIEW | APPROVED | `7555384` | `tests/index/derived/test_composed_and_upgrade.py` |
| 5.4 | READY_FOR_REVIEW | APPROVED | `f50b98f` | `tests/index/derived/test_preserved.py`, `tests/test_confinement.py` |
| 6.1 | READY_FOR_REVIEW | APPROVED | `b5bcf2a` | `.kiro/specs/fit-ingest/requirements.md`, `.kiro/specs/fit-ingest/spec.json`, `.kiro/steering/roadmap.md`, `.kiro/steering/structure.md`, `CHANGELOG.md`, `tests/index/derived/test_published.py` |
| 6.2 | READY_FOR_REVIEW | APPROVED | `bdad792` | Implementation Notes / conditional ownership decision |
| 6.3 | READY_FOR_REVIEW | APPROVED | `fed15d3` | `pyproject.toml` |
| 6.4 | READY_FOR_REVIEW | APPROVED | `7324cd9` | `.kiro/specs/analytics-derived/research.md` |

## Measurements and limits

The user authorized agent measurements and confirmed the shared HealthFit root
is equivalent to the actual installation. Measurements used a complete private
writer copy and leave both shared data and the measurement copy intact.
`research.md` records only aggregate measurements. All 11 measured runtime
source hashes match the final accepted runtime; no affected rerun is needed.

The 2,517 FIT files produced 2,502 composed pages and 30,802 mean-max rows.
Mean-max computation took 8.511576691875234 seconds, 2.977452460764906% of the
measured derived rebuild. Every measured channel/duration 5-to-10-second loss
rate is below the plan's 5% follow-up threshold. Single rebuild trials establish
no causal speedup. The ten other derived tables had empty outputs, with no
athlete profile or plan sources and no core loads; their measured times cannot
estimate populated-corpus performance. Synthetic integration fixtures separately
exercise all eleven non-empty tables. POSIX special-file controls test FIFO and
Unix-domain sockets, not every possible platform-specific special kind.

## Follow-ups and durable evidence

One separately verified low-importance infrastructure issue is queued:
`2026-10-07-confinement-snapshot-dangling-links` — the older shared confinement
snapshot follows dangling links. The derived-specific guard is covered; no
shared-policy repair was folded into this feature.

Canonical stdout, actual exits, mutation recipes, artifact hashes, frozen source
hashes, and superseded owned-context backups are retained locally under
`/private/tmp/analytics-derived-evidence/resume/`. The matrices below preserve
coverage and design evidence in the repository; task-specific summaries and
history are in `tasks.md`. The historical task 1.1 recovery patch must not be
applied over accepted files.

## Design components: 13-component source/test map

| Component | Actual implementation | Evidence tests / current integration state |
|---|---|---|
| `MeanMaxRule` | `src/fitdocs/metrics/mean_max.py` | `tests/metrics/test_mean_max.py; tests/index/derived/test_mean_max_producer.py` |
| `MeanMaxRecords` | `src/fitdocs/metrics/mean_max_sources.py` | `tests/metrics/test_mean_max_sources.py; tests/index/derived/test_boundary.py` |
| `HistorySeam` | `src/fitdocs/history/engine.py; src/fitdocs/history/page.py` | `tests/history/test_compute_seam.py; tests/history/test_engine.py` |
| `PlanSeam` | `src/fitdocs/plans/engine.py; src/fitdocs/plans/reconcile.py` | `tests/plans/test_resolve_seam.py; tests/plans/test_reconcile.py` |
| `DerivedInputs` | `src/fitdocs/index/derived/inputs.py` | `tests/index/derived/test_inputs.py; tests/index/derived/test_refresh.py; tests/index/derived/test_determinism.py` |
| `MeanMaxProducer` | `src/fitdocs/index/derived/mean_max.py` | `tests/index/derived/test_mean_max_producer.py; test_composed_and_upgrade.py` |
| `LoadSeriesProducer` | `src/fitdocs/index/derived/load_series.py` | `tests/index/derived/test_load_series_producer.py; tests/index/derived/test_refresh.py` |
| `BenchmarkProducer` | `src/fitdocs/index/derived/benchmarks.py` | `tests/index/derived/test_benchmark_producer.py; tests/test_benchmarks.py` |
| `BlockProducer` | `src/fitdocs/index/derived/blocks.py` | `tests/index/derived/test_block_producer.py; tests/plans/test_resolve_seam.py` |
| `Registration` | `src/fitdocs/index/registry.py; src/fitdocs/index/schema.py` | `tests/index/derived/test_registration.py; tests/index/test_schema.py; tests/index/test_schema_version.py` |
| `DerivedGuards` | `tests/index/derived/test_boundary.py; tests/test_confinement.py` | `AST/import/network/clock/write boundary tests; actual derived-index confinement plus root preservation accepted in 5.4.` |
| `DerivedRefreshTests` | `tests/index/derived/test_refresh.py; tests/index/derived/test_determinism.py; tests/index/derived/test_composed_and_upgrade.py` | `Failure retention/next-good repair accepted in 5.1; input fingerprints and deterministic/build equivalence covered in 5.2–5.3.` |
| `PublishedStatements` | `CHANGELOG.md; .kiro/steering/structure.md; .kiro/specs/fit-ingest/{requirements.md,spec.json}` | `tests/index/derived/test_published.py; tests/test_changelog.py. Tasks 6.1–6.3 accepted; 6.2 follows first-lander conditional ownership.` |

### Contract and integration observations

- **Composition and computed rows:** `MeanMaxProducer` consumes `PageComputed.activity.samples`; `tests/index/derived/test_composed_and_upgrade.py` checks donated heart rate against the independent metrics computation. The pure metric layer reads `MeanMaxRecords` and does not depend on the index.
- **Corpus snapshot and fingerprints:** `DerivedInputs` consumes `CorpusSnapshot` and separates workout/settings/profile/plan fingerprints; `tests/index/derived/test_inputs.py` checks held and left-out page inclusion and declared-input sensitivity. Load and block producer tests check engine parity and producer call boundaries.
- **History contract:** `read_history_inputs` and `compute_history` are exported from `fitdocs.history`; `day_rows` derives suppressed-day values. `tests/history/test_compute_seam.py` compares the seam with the writing command for both history choices and configuration/error cases. Load-series projection tests check per-methodology daily/weekly rows and model constants.
- **Plan contract:** `read_plan_sources` and `resolve_plans` are public plan APIs; `PlanResolution` carries the canonical plan output. `tests/plans/test_resolve_seam.py` compares source reading/resolution and writes on a copy; the block producer test checks the projected plan report and preserved inputs.
- **Registry/store boundary:** registry imports all four producers. Table contracts/descriptions are checked by derived registration and schema tests; refresh remains owned by analytics-index. `test_boundary.py` checks derived import, clock and write boundaries. The store-facade/non-vacuous actual CLI confinement leg is independently accepted in 5.4.
- **Public surfaces:** task code adds history and plan exports, with `tests/test_public_api.py` as surface pin. The producer modules import owning package APIs rather than private engine submodules, consistent with design dependency direction.
- **First-lander 6.2:** the current branch contains the first-lander decision and leaves exactly the three analytics-query-owned read-side files untouched. Analytics-query task 7.3 owns schema block generation, four SQL examples, and its `derived_inputs()` fixture extension when it lands second. The validated landing base still has query absent from main; task 6.2 is accepted on the first-lander branch, with query task 7.3 owning the later second-lander obligation.

## Acceptance-criteria matrix (64 criteria)

| Criterion | Design summary | Source / API | Test / integration evidence | Coverage status |
|---|---|---|---|---|
| 1.1 | One row per supported duration, three channels with starts | `src/fitdocs/metrics/mean_max.py; src/fitdocs/index/derived/mean_max.py` | `tests/metrics/test_mean_max.py; tests/index/derived/test_mean_max_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 1.2 | From the composed activity | `src/fitdocs/metrics/mean_max.py; src/fitdocs/index/derived/mean_max.py` | `tests/index/derived/test_composed_and_upgrade.py; tests/index/derived/test_mean_max_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 1.3 | Unsupported point is NULL | `src/fitdocs/metrics/mean_max.py; src/fitdocs/index/derived/mean_max.py` | `tests/metrics/test_mean_max.py; tests/index/derived/test_mean_max_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 1.4 | No row when no channel supports; none without computed values | `src/fitdocs/metrics/mean_max.py; src/fitdocs/index/derived/mean_max.py` | `tests/metrics/test_mean_max.py; tests/index/derived/test_mean_max_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 1.5 | Stale-document rule | `src/fitdocs/metrics/mean_max.py; src/fitdocs/index/derived/mean_max.py` | `tests/index/derived/test_refresh.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 1.6 | Hand-over equals re-derivation, incremental equals build | `src/fitdocs/metrics/mean_max.py; src/fitdocs/index/derived/mean_max.py` | `tests/index/derived/test_determinism.py; tests/index/derived/test_composed_and_upgrade.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 2.1 | Fixed set, 1 s to 6 h | `src/fitdocs/metrics/mean_max.py; src/fitdocs/metrics/mean_max_sources.py` | `tests/metrics/test_mean_max.py; tests/metrics/test_mean_max_sources.py; tests/index/derived/test_boundary.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 2.2 | Windows inside continuous recording; maximum step | `src/fitdocs/metrics/mean_max.py; src/fitdocs/metrics/mean_max_sources.py` | `tests/metrics/test_mean_max.py; tests/metrics/test_mean_max_sources.py; tests/index/derived/test_boundary.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 2.3 | Hold the latest recorded value; never from another stretch | `src/fitdocs/metrics/mean_max.py; src/fitdocs/metrics/mean_max_sources.py` | `tests/metrics/test_mean_max.py; tests/metrics/test_mean_max_sources.py; tests/index/derived/test_boundary.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 2.4 | Recorded zero is real; unrecorded never zero | `src/fitdocs/metrics/mean_max.py; src/fitdocs/metrics/mean_max_sources.py` | `tests/metrics/test_mean_max.py; tests/metrics/test_mean_max_sources.py; tests/index/derived/test_boundary.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 2.5 | Earliest on ties | `src/fitdocs/metrics/mean_max.py; src/fitdocs/metrics/mean_max_sources.py` | `tests/metrics/test_mean_max.py; tests/metrics/test_mean_max_sources.py; tests/index/derived/test_boundary.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 2.6 | Unrounded | `src/fitdocs/metrics/mean_max.py; src/fitdocs/metrics/mean_max_sources.py` | `tests/metrics/test_mean_max.py; tests/metrics/test_mean_max_sources.py; tests/index/derived/test_boundary.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 2.7 | Records with justification and search basis; guard | `src/fitdocs/metrics/mean_max.py; src/fitdocs/metrics/mean_max_sources.py` | `tests/index/derived/test_boundary.py; tests/metrics/test_mean_max_sources.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 2.8 | Independent of the index | `src/fitdocs/metrics/mean_max.py; src/fitdocs/metrics/mean_max_sources.py` | `tests/metrics/test_mean_max.py; tests/metrics/test_mean_max_sources.py; tests/index/derived/test_boundary.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 3.1 | Daily rows per methodology | `src/fitdocs/history/engine.py; src/fitdocs/history/page.py; src/fitdocs/index/derived/load_series.py` | `tests/history/test_compute_seam.py; tests/index/derived/test_load_series_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 3.2 | Equal to `history --methodology m` | `src/fitdocs/history/engine.py; src/fitdocs/history/page.py; src/fitdocs/index/derived/load_series.py` | `tests/history/test_compute_seam.py; tests/index/derived/test_load_series_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 3.3 | Suppressed days NULL and marked | `src/fitdocs/history/engine.py; src/fitdocs/history/page.py; src/fitdocs/index/derived/load_series.py` | `tests/history/test_compute_seam.py; tests/index/derived/test_load_series_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 3.4 | No rows after the last contributing day or with no loads | `src/fitdocs/history/engine.py; src/fitdocs/history/page.py; src/fitdocs/index/derived/load_series.py` | `tests/history/test_compute_seam.py; tests/index/derived/test_load_series_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 3.5 | The history default marked | `src/fitdocs/history/engine.py; src/fitdocs/history/page.py; src/fitdocs/index/derived/load_series.py` | `tests/history/test_compute_seam.py; tests/index/derived/test_load_series_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 4.1 | Weekly rows | `src/fitdocs/history/engine.py; src/fitdocs/index/derived/load_series.py` | `tests/history/test_compute_seam.py; tests/index/derived/test_load_series_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 4.2 | Suppressed week NULL | `src/fitdocs/history/engine.py; src/fitdocs/index/derived/load_series.py` | `tests/history/test_compute_seam.py; tests/index/derived/test_load_series_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 4.3 | Series terms | `src/fitdocs/history/engine.py; src/fitdocs/index/derived/load_series.py` | `tests/history/test_compute_seam.py; tests/index/derived/test_load_series_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 4.4 | Unrounded | `src/fitdocs/history/engine.py; src/fitdocs/index/derived/load_series.py` | `tests/history/test_compute_seam.py; tests/index/derived/test_load_series_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 5.1 | Benchmark rows | `src/fitdocs/benchmarks.py; src/fitdocs/index/derived/benchmarks.py` | `tests/test_benchmarks.py; tests/index/derived/test_benchmark_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 5.2 | In-force periods | `src/fitdocs/benchmarks.py; src/fitdocs/index/derived/benchmarks.py` | `tests/test_benchmarks.py; tests/index/derived/test_benchmark_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 5.3 | Equal to the profile's rule every date | `src/fitdocs/benchmarks.py; src/fitdocs/index/derived/benchmarks.py` | `tests/test_benchmarks.py; tests/index/derived/test_benchmark_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 5.4 | Unit of the kind, unconverted | `src/fitdocs/benchmarks.py; src/fitdocs/index/derived/benchmarks.py` | `tests/test_benchmarks.py; tests/index/derived/test_benchmark_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 5.5 | No cross-discipline borrowing | `src/fitdocs/benchmarks.py; src/fitdocs/index/derived/benchmarks.py` | `tests/test_benchmarks.py; tests/index/derived/test_benchmark_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 5.6 | Absent profile gives no rows | `src/fitdocs/benchmarks.py; src/fitdocs/index/derived/benchmarks.py` | `tests/test_benchmarks.py; tests/index/derived/test_benchmark_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 5.7 | No notes, inputs text or flat keys | `src/fitdocs/benchmarks.py; src/fitdocs/index/derived/benchmarks.py` | `tests/test_benchmarks.py; tests/index/derived/test_benchmark_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 6.1 | Block rows | `src/fitdocs/plans/engine.py; src/fitdocs/plans/reconcile.py; src/fitdocs/index/derived/blocks.py` | `tests/plans/test_resolve_seam.py; tests/index/derived/test_block_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 6.2 | Mesocycle rows with the actual-load picture | `src/fitdocs/plans/engine.py; src/fitdocs/plans/reconcile.py; src/fitdocs/index/derived/blocks.py` | `tests/plans/test_resolve_seam.py; tests/index/derived/test_block_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 6.3 | Planned-workout rows | `src/fitdocs/plans/engine.py; src/fitdocs/plans/reconcile.py; src/fitdocs/index/derived/blocks.py` | `tests/plans/test_resolve_seam.py; tests/index/derived/test_block_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 6.4 | Claimed pages, missing override stems | `src/fitdocs/plans/engine.py; src/fitdocs/plans/reconcile.py; src/fitdocs/index/derived/blocks.py` | `tests/plans/test_resolve_seam.py; tests/index/derived/test_block_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 6.5 | Unplanned pages | `src/fitdocs/plans/engine.py; src/fitdocs/plans/reconcile.py; src/fitdocs/index/derived/blocks.py` | `tests/plans/test_resolve_seam.py; tests/index/derived/test_block_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 6.6 | Equal to the plan pass | `src/fitdocs/plans/engine.py; src/fitdocs/plans/reconcile.py; src/fitdocs/index/derived/blocks.py` | `tests/plans/test_resolve_seam.py; tests/index/derived/test_block_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 6.7 | Not logged versus upcoming by the current date; recorded | `src/fitdocs/plans/engine.py; src/fitdocs/plans/reconcile.py; src/fitdocs/index/derived/blocks.py` | `tests/plans/test_resolve_seam.py; tests/index/derived/test_block_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 6.8 | Invalid source and no-source behaviour | `src/fitdocs/plans/engine.py; src/fitdocs/plans/reconcile.py; src/fitdocs/index/derived/blocks.py` | `tests/plans/test_resolve_seam.py; tests/index/derived/test_block_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 6.9 | No prescription, reason, trail or original rows | `src/fitdocs/plans/engine.py; src/fitdocs/plans/reconcile.py; src/fitdocs/index/derived/blocks.py` | `tests/plans/test_resolve_seam.py; tests/index/derived/test_block_producer.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 7.1 | Engines' page sets, left-out pages included | `src/fitdocs/index/derived/inputs.py; src/fitdocs/history/engine.py; src/fitdocs/plans/engine.py` | `tests/index/derived/test_inputs.py; tests/history/test_compute_seam.py; tests/plans/test_resolve_seam.py; tests/index/derived/test_preserved.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 7.2 | Data-root files byte-identical | `tests/test_confinement.py; tests/index/derived/test_preserved.py` | `tests/index/derived/test_preserved.py; independent 5.4 review verdict` | PINNED by accepted 5.4 complete-root snapshots across sync/regen/load with fresh and prebuilt external indexes. |
| 7.3 | Command output and exits unchanged | `src/fitdocs/index/derived/inputs.py; src/fitdocs/history/engine.py; src/fitdocs/plans/engine.py` | `tests/history/test_compute_seam.py; tests/plans/test_resolve_seam.py; existing command goldens` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 7.4 | Corpus tables as inputs stood at the last refresh | `src/fitdocs/index/derived/inputs.py; src/fitdocs/history/engine.py; src/fitdocs/plans/engine.py` | `tests/index/derived/test_inputs.py; tests/history/test_compute_seam.py; tests/plans/test_resolve_seam.py; tests/index/derived/test_preserved.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 7.5 | Tests against each owning computation, on discriminating fixtures | `src/fitdocs/index/derived/{mean_max,load_series,benchmarks,blocks}.py; src/fitdocs/metrics/mean_max.py; src/fitdocs/history/engine.py; src/fitdocs/benchmarks.py; src/fitdocs/plans/reconcile.py` | `tests/index/derived/test_mean_max_producer.py; tests/index/derived/test_load_series_producer.py; tests/index/derived/test_benchmark_producer.py; tests/index/derived/test_block_producer.py` | PINNED at the four producer comparison modules; preservation tests are not used as owner-computation oracles. |
| 8.1 | Load-series recompute inputs | `src/fitdocs/index/derived/{inputs,load_series,benchmarks,blocks}.py; src/fitdocs/index/refresh.py` | `tests/index/derived/test_inputs.py; tests/index/derived/test_refresh.py; tests/index/derived/test_determinism.py; tests/index/derived/test_composed_and_upgrade.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 8.2 | Benchmark recompute inputs | `src/fitdocs/index/derived/{inputs,load_series,benchmarks,blocks}.py; src/fitdocs/index/refresh.py` | `tests/index/derived/test_inputs.py; tests/index/derived/test_refresh.py; tests/index/derived/test_determinism.py; tests/index/derived/test_composed_and_upgrade.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 8.3 | Block recompute inputs, held pages, the date only with sources | `src/fitdocs/index/derived/{inputs,load_series,benchmarks,blocks}.py; src/fitdocs/index/refresh.py` | `tests/index/derived/test_inputs.py; tests/index/derived/test_refresh.py; tests/index/derived/test_determinism.py; tests/index/derived/test_composed_and_upgrade.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 8.4 | Whole-table replacement | `src/fitdocs/index/derived/{inputs,load_series,benchmarks,blocks}.py; src/fitdocs/index/refresh.py` | `src/fitdocs/index/refresh.py; tests/index/derived/test_refresh.py; tests/index/test_refresh.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 8.5 | Failure keeps previous rows, others refresh | `src/fitdocs/index/derived/{inputs,load_series,benchmarks,blocks}.py; src/fitdocs/index/refresh.py` | `tests/index/derived/test_refresh.py (accepted 5.1 evidence)` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 8.6 | No-op leaves the index byte-identical | `src/fitdocs/index/derived/{inputs,load_series,benchmarks,blocks}.py; src/fitdocs/index/refresh.py` | `src/fitdocs/index/derived/inputs.py; tests/index/derived/test_refresh.py (accepted 5.1 evidence)` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 8.7 | Same rows whatever the order or path | `src/fitdocs/index/derived/{inputs,load_series,benchmarks,blocks}.py; src/fitdocs/index/refresh.py` | `tests/index/derived/test_determinism.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 9.1 | NULL, except the engine's own zero | `src/fitdocs/index/schema.py; src/fitdocs/index/derived/*.py` | `tests/index/derived/test_registration.py; tests/index/test_schema.py; producer contract tests` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 9.2 | Unit suffixes and words | `src/fitdocs/index/schema.py; src/fitdocs/index/derived/*.py` | `tests/index/derived/test_registration.py; tests/index/test_schema.py; producer contract tests` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 9.3 | Descriptions; corpus agreement sentence | `src/fitdocs/index/schema.py; src/fitdocs/index/derived/*.py` | `tests/index/derived/test_registration.py; tests/index/test_schema.py; producer contract tests` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 9.4 | Dates as dates; starts in seconds | `src/fitdocs/index/schema.py; src/fitdocs/index/derived/{mean_max,load_series,benchmarks,blocks}.py` | `tests/index/test_schema.py exact physical schema manifest; tests/index/derived/test_registration.py ColumnType checks; producer tests for Python date values and elapsed-second starts` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 9.5 | Missing description fails tests | `src/fitdocs/index/schema.py; src/fitdocs/index/derived/*.py` | `tests/index/derived/test_registration.py; tests/index/test_schema.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 10.1 | Version +1; exact table/column/type/order digest | `src/fitdocs/index/schema.py; src/fitdocs/index/registry.py` | `tests/index/test_schema.py; tests/index/test_schema_version.py; tests/index/derived/test_registration.py; accepted 6.3 review` | PINNED: main schema 1 → feature schema 2; version-2 digest and 24-table manifest are checked. |
| 10.2 | Rebuild on the earlier version | `src/fitdocs/index/schema.py; src/fitdocs/index/registry.py; CHANGELOG.md; .kiro/steering/structure.md; .kiro/specs/fit-ingest/{requirements.md,spec.json}` | `tests/index/derived/test_composed_and_upgrade.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 10.3 | Release notes | `src/fitdocs/index/schema.py; src/fitdocs/index/registry.py; CHANGELOG.md; .kiro/steering/structure.md; .kiro/specs/fit-ingest/{requirements.md,spec.json}` | `CHANGELOG.md; tests/index/derived/test_published.py; tests/test_changelog.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 10.4 | Conditional publication when this feature/query land second | `CHANGELOG.md; .kiro/steering/structure.md; analytics-query task 7.3 owns the later read-side integration` | `Task 6.2 accepted first-lander decision; query and the three bounded read-side paths are absent from current main` | CONDITIONAL, satisfied for this first-lander branch; no local gap. Analytics-query task 7.3 owns the later second-lander requirement. |
| 10.5 | Steering dependency statement | `src/fitdocs/index/schema.py; src/fitdocs/index/registry.py; CHANGELOG.md; .kiro/steering/structure.md; .kiro/specs/fit-ingest/{requirements.md,spec.json}` | `.kiro/steering/structure.md; tests/index/derived/test_published.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 10.6 | fit-ingest amendment | `src/fitdocs/index/schema.py; src/fitdocs/index/registry.py; CHANGELOG.md; .kiro/steering/structure.md; .kiro/specs/fit-ingest/{requirements.md,spec.json}` | `.kiro/specs/fit-ingest/requirements.md; spec.json; tests/index/derived/test_published.py` | Mapped to completed leaf task(s) and named owner tests; task-level acceptance is recorded. Fresh final feature gate passed. |
| 10.7 | No write location/network/clock/dependency; versions unchanged | `tests/index/derived/test_boundary.py; tests/test_confinement.py; tests/index/derived/test_preserved.py; pyproject.toml; src/fitdocs/contract.py` | `tests/index/derived/test_boundary.py; accepted 5.4 confinement/preservation review; accepted 6.3 dependency and version-pin review` | PINNED across the accepted boundary, confinement/preservation, and final version/dependency gates. |
| 10.8 | Confinement with non-vacuity | `tests/test_confinement.py; src/fitdocs/index/store.py; src/fitdocs/index/location.py` | `tests/test_confinement.py actual index-derived dispatcher, 11 physical non-empty tables, and managed-workout negative control; accepted 5.4 review` | PINNED by the actual CLI path and strict external-cache boundary. |

