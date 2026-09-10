---
id: 2026-09-10-benchmark-gained-a-published-field-without-plugin-api-coordination
title: The published Benchmark dataclass gained applies_from with no plugin-api coordination row, and the public-surface test pins identity only, so a field added to an exported type is invisible to every gate
status: open
importance: medium
importance_why: fitdocs.load re-exports Benchmark on the plugin surface; a plugin author reading docs/plugins.md or the published surface list learns nothing about applies_from or a negative BenchmarkAge, and the pin that exists cannot detect the change — the same species Amendment 3 recorded for NotConfirmed.
effort: S
kind: inconsistency
area: plugin-api, docs/plugins.md, src/fitdocs/load/__init__.py, tests/test_public_api.py
created: 2026-09-10
surfaced_by: /kiro-validate-impl training-load (Amendment 4, design + boundary dimension)
pinned_at: 52c473e
resume_command: "/kiro-spec-design plugin-api [queue: .kiro/queue/2026-09-10-benchmark-gained-a-published-field-without-plugin-api-coordination.md] Record Benchmark.applies_from and the negative BenchmarkAge on the published surface and decide whether the surface pin should cover exported dataclass fields"
context:
  - docs/plugins.md
  - src/fitdocs/load/__init__.py
  - src/fitdocs/benchmarks.py
  - tests/test_public_api.py
  - .kiro/specs/plugin-api/design.md
blocked_by: []
---

## What

`src/fitdocs/load/__init__.py` re-exports `Benchmark`, `BenchmarkAge` and
`benchmark_age`; `tests/test_public_api.py` pins them by identity
(`"Benchmark": fitdocs.benchmarks.Benchmark`). Amendment 4 / athlete-benchmarks
Amendment 1 added a public field (`Benchmark.applies_from`) and changed
`benchmark_age`'s contract (a negative age instead of a raise). The identity
pin cannot see either; `docs/plugins.md`'s benchmark paragraph was corrected
on 2026-09-10 for the resolution rule and the negative age (one sentence
each), but plugin-api's own published-surface record and coordination table
know nothing of the change.

## Why it matters

The pre-1.0 surface is declared unstable, so the change is legitimate; what
is missing is the record. A plugin author who constructs `Benchmark` directly
or calls `benchmark_age` on an anchor gets a field and a sign they were never
told about. The identity-only pin is the structural cause: it will miss the
next field too (Phase 6's `source` is already specified).

## Evidence

- `grep -n Benchmark src/fitdocs/load/__init__.py` — the re-exports.
- `tests/test_public_api.py` — `"Benchmark": fitdocs.benchmarks.Benchmark`
  (identity pin; reviewer-reported line 198 at 52c473e).
- `docs/plugins.md` benchmark paragraph (~L270-280) — corrected wording as of
  this branch; no mention in plugin-api's own files.
- `.kiro/specs/training-load/design.md` Cross-Spec table lists
  `docs/plugins.md` as plugin-api-coordinated.

## How to pick it up

1. Read plugin-api's published-surface list in its design.md and the
   Amendment 1/3 history of surface repins in training-load's spec.json.
2. Record `applies_from` and the negative-age contract; decide whether the
   surface pin should enumerate exported dataclass fields (a
   `dataclasses.fields()` snapshot per exported type) so the next addition
   (`source`) is a deliberate repin.
3. Done: plugin-api's surface record names the field; the pin reds when a
   field is added to an exported dataclass without a repin.
