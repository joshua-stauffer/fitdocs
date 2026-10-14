# wellness-store implementation validation

Validated 2026-10-14 at implementation head `b15dc2981fc8eb40c0919e5c7f35bb5c667834fc`,
after fetch/rebase onto main `2d1251479c956aa8b4d2f528c530afeed007e0f1`.
The completion metadata/report commit changes no packaged inputs or executable tests.

## Validation Report

- DECISION: GO
- MECHANICAL_RESULTS:
  - Tests: PASS; canonical `uv run pytest`, exit 0, **14,733 passed, 44 skipped**.
  - Lint/format/types: PASS; `uv run ruff check .`, `uv run ruff format --check .`
    (735 files), configured `uv run mypy` (550 files), and `git diff --check`, all exit 0.
  - Introduced source TBD/TODO/FIXME/HACK/XXX scan: CLEAN.
  - Introduced source hardcoded password/api_key/secret/token assignment scan: CLEAN.
  - Build: PASS; canonical `uv run python -m scripts.build_release --out-dir <scratch>/dist`,
    exit 0; wheel and sdist produced.
  - Smoke boot: PASS; actual wheel installed offline into a separate fresh environment,
    imported outside the checkout, and exercised through its installed CLI.
- INTEGRATION:
  - Cross-task contracts: PASS; recognition → intake → archive → merge → series → reader
    → index/report/check contracts align.
  - Shared state consistency: PASS; SHA quarantine, single settle, MOVE eligibility,
    precedence, manifest-last publication, and stale-series recovery agree.
  - Boundary audit: PASS; all 15 ranked wellness modules traversed, zero violations;
    facade has the exact 16 names. Existing four index→dashboard passes remain intact.
- COVERAGE: **20/20 sections, 125/125 numbered criteria assessed**; no concrete uncovered
  behavior under the approved capped-JSON interpretation described below.
- DESIGN: component/file plan matches; no unapproved architecture drift, dependency
  inversion, extra network owner, downstream implementation or hidden writer found.
- OWNERSHIP: LOCAL validated feature; no failure requiring ownership routing.
- UPSTREAM_SPEC: N/A.
- BLOCKED_TASKS: none. All **27 mandatory leaf tasks** independently accepted; optional
  maintainer-only task **6.3 remains unchecked and was not run**.
- REMEDIATION: none required for GO.

## Requirements coverage

Two independent read-only audits mapped every numbered criterion to actual source and
verification evidence; a third audited the complete architecture/integration graph.
The table summarizes those criterion-level mappings. Paths are relative to the repository.
Semantic coverage does not assert that every explanatory sentence has a mutation guard.

| Requirement | Criteria | Completed tasks | Implementation and verification seams |
|---|---:|---|---|
| 1. Recognizing inbox files | 9 | 1.2–1.4, 2.7, 3.1, 3.3, 4.2 | `inbox`, `probe`, `registry`, `intake`, shared drain settle; inbox/folder, registered-format, intake and drain tests |
| 2. Archiving a file | 10 | 1.5, 2.6, 3.3, 4.2 | streamed/hash-checked atomic original/extract commits; archive, quarantine, stability and MOVE tests |
| 3. Large-file reads | 4 | 1.2, 2.6, 4.2, 4.5 | bounded probe/hash/copy, capped JSON, streamed extract/progress; probe/archive/TTY progress tests; limits below |
| 4. Non-activity FIT guard | 6 | 1.6, 4.1, 6.1 | canonical identity, cached-drain classification and MOVE veto, preserved page regen; ingest/sync/drain/e2e tests |
| 5. Metrics | 6 | 1.1, 2.1, 2.2, 5.1 | `Metric`, `METRICS`, units, source maps and guide; model/parser/docs tests |
| 6. Absence | 5 | 1.1, 2.1–2.4 | `accept_value`, parser coverage, absent lookup returns None; model/parser/merge/series tests |
| 7. Wellness day | 6 | 1.1, 2.1, 2.2, 5.1, 6.1 | source dates and recorded-offset sleep-end rule; boundary/model/parser and independent-TZ determinism tests |
| 8. Attribution | 4 | 2.1–2.4, 5.1 | delivery origins, Garmin attribution, source preservation; parser/merge/codec and mixed-drain assertions |
| 9. Overlaps | 5 | 2.3, 2.6, 3.2, 3.4, 4.3 | revision-before-value, covered absence, header-first latest-entry selection, conflicts; merge/engine/inspect/audit tests |
| 10. Precedence | 6 | 1.3, 2.3, 2.5, 3.2, 4.2, 4.5 | dynamic defaults, metric overrides, pre-write validation, input digest; settings/merge/drain/CLI tests |
| 11. Series files | 8 | 1.5, 2.4, 3.2, 3.4, 4.4, 6.1 | exact CSV/manifest codecs, owned paths, reader and atomic publication; goldens/engine/reader/declaration/determinism tests |
| 12. Rebuild | 8 | 2.4, 3.2, 4.2, 4.5, 6.1 | digest, force=False drain/force=True regen, failure preservation, supersession; engine/drain/CLI/e2e tests |
| 13. Reporting | 6 | 3.2, 4.2, 4.5, 6.1 | twelve rows, four detailed wellness channels, change counts/status/exit gates; CLI/drain/e2e and wheel smoke |
| 14. Check findings | 6 | 1.5, 3.4, 4.3, 6.1 | metadata-only inspect, orphan/stale/conflict/occupied remedies and declarations; inspect/audit/check/read-only tests |
| 15. intervals.icu | 7 | 2.1, 2.6, 3.1, 3.3, 5.1 | API list/delivery envelope, 17 field mappings, original bytes and version handling; parser/registered/intake/archive/docs tests |
| 16. Garmin | 8 | 1.1, 1.3, 2.2, 2.3, 2.6, 3.1, 3.3, 4.1 | four content signatures, calendarDate, revisions, strict weights, original bytes; parser/merge/registered/drain/e2e and wheel tests |
| 17. Later formats | 5 | 1.2–1.4, 2.4, 2.6, 3.1–3.4, 4.4 | dynamic declarations, extract seam, header-only winner selection, rules digest and generic row shape; synthetic original/extract/latest-entry/future-metric tests |
| 18. Analytics index | 5 | 1.4, 4.4, 5.2, 6.1, 6.2 | reader-only seven-column `wellness_daily`, fingerprint/retained rows, schema 3; producer/schema/CLI/index boundary/e2e tests |
| 19. Contract/docs | 6 | 1.5, 4.2, 5.1, 5.2, 6.2 | contract 11, guide, configuration/inbox/plugin/ownership docs, skill and changelog; conformance/docs/skill/key guards plus prose review |
| 20. Offline/deterministic | 5 | 1.4, 2.4, 2.6, 3.2, 4.2, 5.3, 6.1 | boundary/network guards, no dependency changes, synthetic provenance and confined writes; socket-blocked lifecycle, independent TZ/hashseed and confinement tests |

## Fresh execution evidence

The full post-rebase suite ran with the existing warm UV cache and Unix-socket permissions:
`UV_CACHE_DIR=/Users/josh/.cache/uv uv --cache-dir /private/tmp/fitdocs-recovery-uv-cache run --offline pytest`.
Raw output records 14,733 passed, 44 skipped in 374.95 seconds, exit 0. Skips cover optional
site tooling, unavailable actionlint, and six local forbidden-string checks whose protected
match data is unset. These local skips are not represented as a completed protected scan.

Source-head [CI run 38534697552](https://github.com/joshua-stauffer/fitdocs/actions/runs/38534697552)
passed, including the protected artifact check and fail-closed gate. Final landing also
requires successful CI on the completion commit.

Build and smoke evidence uses the actual release artifacts:

- Wheel SHA256: `e0bd1e8444287d703088e7399203b63d8e86ed4a8b68d1f58af9617c3542a291`.
- Sdist SHA256: `7ee3c46e1150959482c22c9e3564f21a73fe44c674c88c7129a5c6f52fb8492b`.
- All 249 captured source hashes and artifact hashes independently match current bytes.
  Packaged inputs are unchanged since the build at `f2c2531`.
- Fourteen installed-wheel steps had their expected actual exits: create/install environment,
  verify installed import path and versions, `--help`, sync, index, check, regen, query,
  invalid-weight rejection, quiet same-SHA quarantine, missing/null omission, query and check.
- Real `wellness_daily` query returned the expected two synthetic rows for 2032-07-09:
  resting HR 53 bpm and steps 8123 from intervals.icu. Quiet regen preserved bytes and mtimes.
  Present nonnumeric Garmin weight failed; missing/null weights produced no values and the
  query remained unchanged. Dates are validated even when weight is absent.

Raw evidence retained on the originating machine: `/private/tmp/landing6-2-reviewer-full.{txt,json}`,
`/private/tmp/landing6-2-reviewer-static.json`, `/private/tmp/wellness6-2-build-result.json`,
`/private/tmp/wellness6-2-wheel-smoke-result.json`, and the independent
`/private/tmp/wellness-final-{coverage-a,coverage-b,architecture}.md` audits.

## Explicit scope and evidence limits

- Requirement 3.1 is read with 3.2 and the approved Probe/Seams design: large framework
  reads/copies/extracts stream in bounded chunks, while shipped JSON recognition permits
  whole parsed JSON up to 64 MiB. Shipped JSON parsers materialize supported inputs;
  this is not streaming JSON parsing, arbitrary-size JSON import, or a parser cap against
  hostile manual replacement of archive entries. Oversized shipped inbox JSON is unrecognized.
- Atomic publication means individual replacements, staged bytes and manifest-last recovery;
  it does not promise a filesystem-wide transaction. The next run detects partial publication.
- The approved cached non-activity identity probe/MOVE veto and wellness-only nonfatal
  explicit-index producer-error rule are recorded design/task clarifications. Other CLI
  failure gates and dashboard sequencing remain intact.
- New fixture provenance was inspected as synthetic; this is not universal runtime proof of
  the absence of personal data. Protected CI supplies the separate artifact gate. Optional
  maintainer personal-export task 6.3 was not run and no personal export was opened.
- Narrative documentation was reviewed directly; structural tests do not discriminate every
  explanatory sentence. Current bounded copy and inbox case normalization are correct, with
  two explicitly tracked regression-sensitivity limits below.

## Verification Result

- STATUS: VERIFIED
- CLAIM_TYPE: FEATURE_GO
- CLAIM: All mandatory wellness-store implementation work is ready to land with contract 11
  and schema 3, each one greater than current main, subject to final completion-commit CI.
- EVIDENCE: current-source integrity; independently accepted mandatory tasks; exhaustive
  requirements coverage; architecture/integration/boundary audits; post-rebase full suite and
  statics; canonical release build and actual installed-wheel runtime smoke.
- GAPS: no mandatory behavior or verification gap. Optional 6.3 and regression limits are
  explicitly excluded from broader completion claims.

## Queued follow-ups

No new feature-validation remediation was surfaced. Preserve the two existing low-priority
test-guard items, both describing correct current production code:

- [2026-10-14-wellness-archive-retained-memory-guard](../../queue/2026-10-14-wellness-archive-retained-memory-guard.md): measure retained-memory regression sensitivity of wellness archive copying.
- [2026-10-14-inbox-nested-basename-case-guard](../../queue/2026-10-14-inbox-nested-basename-case-guard.md): pin case normalization for nested basename-only inbox ignores.
