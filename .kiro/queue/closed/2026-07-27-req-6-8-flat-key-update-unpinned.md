---
id: 2026-07-27-req-6-8-flat-key-update-unpinned
title: Req 6.8's "never updated" clause is unpinned — the benchmark write path could overwrite a hand-written flat threshold key with the suite green
status: done
importance: high
importance_why: A user's hand-written flat max_hr_bpm/ftp_watts could be silently rewritten on every benchmark answer, and no test would notice; it is the write-path twin of the queued Req 1.11 read-path gap.
effort: S
kind: gap
area: athlete-benchmarks, src/fitdocs/load/profile.py, tests/load/test_profile.py
created: 2026-07-27
surfaced_by: /kiro-validate-impl athlete-benchmarks (requirements-coverage dimension)
pinned_at: 32441af
resume_command: "do: add the fixture that reds when with_benchmark updates an existing flat threshold key of the same quantity [queue: .kiro/queue/2026-07-27-req-6-8-flat-key-update-unpinned.md]"
context:
  - .kiro/specs/athlete-benchmarks/requirements.md
  - src/fitdocs/load/profile.py
  - tests/load/test_profile.py
  - .kiro/queue/2026-07-27-req-1-11-prohibition-unpinned.md
blocked_by: []
---

## What

Requirement 6.8 has two clauses: the benchmark write path shall never **create**
a flat threshold key, and flat keys already present are preserved but never
**updated** by that path. The creation half is covered. The update half is
pinned by nothing.

`AthleteProfile.with_benchmark` is correct today — it touches only
`document["benchmarks"]`. But a change that also wrote the flat key would ship
green.

## Why it matters

The flat athlete-input keys are what the user hand-wrote. Silently rewriting one
every time a benchmark of that quantity is persisted would change rendered
output for every subsequent document, and the user would see a threshold they
never entered. This is the same class of harm as the queued Req 1.11 gap, and
together the two leave *both* directions of the flat-key/benchmark boundary
unenforced: 1.11 is the read path deriving a flat key **from** benchmarks
(`src/fitdocs/athlete.py`), this is the write path overwriting a flat key
**with** a benchmark answer (`src/fitdocs/load/profile.py`). Different modules,
different call paths — the 1.11 item's evidence and pick-up steps do not reach
this one.

## Evidence

Probe inserted in `AthleteProfile.with_benchmark` (`src/fitdocs/load/profile.py`)
immediately after the merge:

```python
if kind.value in document:  # PROBE: update an existing flat key
    document[kind.value] = stored_value
```

`PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider` (with
`__pycache__` cleared first) → **2064 passed**. Reverted from a scratch copy;
`shasum` matched and `git status` was clean afterwards.

Why existing coverage misses it: the sole 6.8 assertion is
`assert "ftp_watts" not in raw` in
`tests/load/test_profile.py::test_with_benchmark_round_trip_upserts_sorts_and_preserves`.
That fixture seeds flat `max_hr_bpm = 190` but only ever writes a **RUN
`ftp_watts`** benchmark — the flat key and the persisted quantity never
coincide, so only the *creation* half can redden. No fixture anywhere pairs a
flat threshold key with a benchmark write of that same quantity.

## How to pick it up

1. Read `tests/load/test_profile.py::test_with_benchmark_round_trip_upserts_sorts_and_preserves`
   to see why its fixture cannot cover this.
2. Add a test seeding flat `max_hr_bpm = 188`, persisting an athlete-scoped
   `MAX_HR_BPM` benchmark of `200`, and asserting `raw["max_hr_bpm"] == 188`.
   **Pairwise-distinct values are essential** — equal values make the mutation
   invisible (confounded fixture, `change-protocol.md`).
3. Verify with the probe above: the new test must red, ideally as a sole
   failure. Restore from a scratch copy, never `git checkout`.
4. Consider doing this together with
   `2026-07-27-req-1-11-prohibition-unpinned` — same boundary, opposite
   direction, and one session holding both in mind will get the fixture shapes
   right faster.

## Resolution

Closed 2026-07-29, merged to `main` as `421c075` (branch
`chore/flat-key-prohibition-guards`, `--ff-only`, validated after rebase:
2112 passed, all gates clean). **Test-only.** See the sibling item
`.kiro/queue/closed/2026-07-27-req-1-11-prohibition-unpinned.md` — they were
done together as the read-path and write-path halves of one guarantee.

`test_with_benchmark_never_updates_an_existing_flat_threshold_key` is now
parametrized over all five `BenchmarkKind` values, so the name is literally
true; it previously pinned `max_hr_bpm` alone while claiming all of them. The
assertion reads the file after `save_profile`, so it spans **both** entry
points of the write path — a reviewer mutation confirmed `save_profile`
coverage is real and not incidental.

**A second clause was found unpinned during review and also closed**: Req
6.8's *creation* clause ("shall not write any new flat threshold key") was
independently guarded only for `ftp_watts`, by a pre-existing round-trip
assertion. The argument that the other four kinds "share the same code path
so are very likely equally sound" was falsified by mutation — creating a flat
key for every kind *except* `ftp_watts` left all 2103 tests green, which is
exactly a kind-discriminating bug on that shared path. Now covered by
`test_with_benchmark_never_creates_a_flat_threshold_key`, parametrized over
all five kinds.

**Self-maintaining**: `test_flat_quantity_attrs_cover_every_benchmark_kind_with_a_flat_counterpart`
reds if a future `BenchmarkKind` with a flat counterpart is added without
extending the cases. Verified in both directions — a new kind *with* a flat
counterpart reds it; one *without* leaves it green.
