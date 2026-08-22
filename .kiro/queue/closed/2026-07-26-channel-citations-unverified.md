---
id: 2026-07-26-channel-citations-unverified
title: Verify the channel-layer citations marked PRIMARY_TEXT against their actual sources
status: done
importance: high
importance_why: Four citations claim primary-text verification nobody performed; TRAININGPEAKS_COVERAGE_GATE's note already asserts the 0.80 figure Req 3.10's default coverage threshold rests on.
effort: S
kind: research
area: load-channels, src/fitdocs/load/channels/sources.py
created: 2026-07-26
surfaced_by: /kiro-impl load-channels (task 1.1 implementer CONCERN + reviewer FOLLOW_UPS)
pinned_at: 0dc3be2
resume_command: "do: open each source cited in src/fitdocs/load/channels/sources.py, confirm or correct its year and locator, and downgrade any that cannot be opened to VerificationStatus.SECONDARY_ATTESTATION with a note saying why [queue: .kiro/queue/2026-07-26-channel-citations-unverified.md]"
context:
  - src/fitdocs/load/channels/sources.py
  - tests/load/channels/test_sources.py
  - .kiro/specs/load-channels/requirements.md
  - .kiro/specs/load-channels/design.md
blocked_by: []
---

## What

Task 1.1 of `load-channels` landed the channel layer's provenance record. Four
of its six citations carry `VerificationStatus.PRIMARY_TEXT` — which the module
itself defines as "read from the source's own text" — but nobody read them. The
implementer stated plainly in its status report that the years and locators are
"best-effort real-world attributions rather than verified against the actual
source pages", and the reviewer confirmed this is not visible from the code:
the structure is correct, the works are real, and the status is simply asserted.

The four are `COGGAN_TSS` (2010, "Ch. 4-5"), `INTERVALS_ICU_PACE_LOAD` (2023,
"intervals.icu Help Center, 'Pace Load'"), `INTERVALS_ICU_HRSS` (2023, "Heart
Rate Load") and `TRAININGPEAKS_COVERAGE_GATE` (2022, "data-coverage
requirements for a valid TSS calculation").

`MINETTI_2002` and `BANISTER_TRIMP` are *not* affected — both are correctly
marked `SECONDARY_ATTESTATION` with notes explaining why the primary text was
not obtained. That is the honest pattern the four above should match if they
cannot be verified.

## Why it matters

Requirement 8.2 forbids presenting a secondary attestation as a primary one.
This does not violate 8.1 as literally written — author, year, work and a
status are all present — but `PRIMARY_TEXT` is a factual claim about how the
citation was obtained, and right now it is false for four of six entries.

The concrete risk is deferred, not absent. Task 1.1 introduces no numeric
constant, so nothing computes from these keys yet. Tasks 2.2 (grade
adjustment), 3.1 (power channel) and 3.3 (pace channel) each pin coefficients
that cite these keys, and requirement 8.3 makes "no constant without a
citation" a structural, test-enforced rule. At that point an unverified locator
stops being a documentation defect and becomes an unaudited provenance chain
under a test suite that asserts provenance is sound.

`TRAININGPEAKS_COVERAGE_GATE` is the urgent one: its note already asserts 0.80
as a sourced figure, and requirement 3.10's default coverage threshold — used
by the sufficiency gate in task 1.3 — is justified by exactly that citation. A
wrong or unfindable source there means the shipped default has no published
basis, which is the specific failure `.kiro/steering/` prohibits.

## Evidence

- `src/fitdocs/load/channels/sources.py` — the six citations and their
  `verification` values, landed in `0dc3be2`.
- Task 1.1 implementer status report, `CONCERNS` field: "Citation
  `locator`/`year` values (e.g. TrainingPeaks 2022, intervals.icu 2023) are my
  best-effort real-world attributions rather than verified against the actual
  source pages."
- Task 1.1 round-1 reviewer `FOLLOW_UPS`: "`PRIMARY_TEXT` means 'read from the
  cited work's own text,' and no one read them for this task... the risk
  becomes real in tasks 2.2, 3.1 and 3.3 when constants start pointing at these
  keys."
- Round-2 reviewer confirmed the content is intact and load-bearing (24
  mutants, all caught) — so the *values* are pinned by tests; only their
  real-world accuracy is unverified.
- `uv run pytest -q` at `0dc3be2` → 1765 passed. Nothing here is failing; this
  is a correctness-of-record issue that no test can detect.

## How to pick it up

1. Read `src/fitdocs/load/channels/sources.py` — the whole file is ~218 lines
   and the citation block is self-describing. Note which entries carry
   `PRIMARY_TEXT`.
2. Start with `TRAININGPEAKS_COVERAGE_GATE`, since requirement 3.10's default
   turns on it. Find TrainingPeaks' published statement of the data-coverage
   requirement for a valid TSS calculation and confirm the 0.80 figure and the
   year. If it cannot be found, that is itself the finding — the default needs
   either a different citation or a `FITDOCS_MEASURED` status plus a recorded
   measurement, which is exactly what that third `VerificationStatus` member
   exists for.
3. Repeat for the two intervals.icu entries and `COGGAN_TSS`, correcting year
   and locator in place.
4. Anything that cannot be opened gets downgraded to `SECONDARY_ATTESTATION`
   with a note saying why, matching the pattern `MINETTI_2002` and
   `BANISTER_TRIMP` already set.
5. Done looks like: every `PRIMARY_TEXT` entry has actually been read, or has
   been downgraded. `tests/load/channels/test_sources.py` should stay green
   throughout — it asserts structure, not accuracy. If a downgrade happens,
   check whether the test asserting "exactly two secondary-attested citations"
   needs its count updated.

## Open questions

- If `TRAININGPEAKS_COVERAGE_GATE` proves unfindable, does the 0.80 default
  stay (restated as a fitdocs-measured choice under the third verification
  status, per requirement 8.2) or change? That is a product decision about the
  sufficiency gate's default, not a documentation fix, and it touches
  `load-channels` task 1.2's stated coverage default.

## Resolution

**Done 2026-07-26** (queue sweep, merged to `main` at `e806c57`).

`3f0e45b`. `PRIMARY_TEXT` went 4 -> 2, each survivor carrying a quote from a source actually opened. Corrections found: `COGGAN_TSS` locator Ch. 4-5 -> Ch. 7; `INTERVALS_ICU_PACE_LOAD` cited a "Help Center" that does not exist (year 2023 -> 2021); `INTERVALS_ICU_HRSS` year 2023 -> 2020. `TRAININGPEAKS_COVERAGE_GATE` is `PRIMARY_TEXT` after all — the Wayback snapshot is reachable and states the 80% figure verbatim (year 2022 -> 2016). Two new guards pin the exact `PRIMARY_TEXT` key set and require every `SECONDARY_ATTESTATION` to carry a note. Open questions spun out: the 0.80 gate is confirmed bike-power-only while Req 3.10 applies it cross-channel (product decision), and `2026-07-26-hrss-exact-interop-claim-unsupported`.
