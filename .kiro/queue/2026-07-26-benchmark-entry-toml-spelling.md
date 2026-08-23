---
id: 2026-07-26-benchmark-entry-toml-spelling
title: The store writes benchmark entries as inline-table arrays where the design documents the array-of-tables spelling
status: open
importance: low
importance_why: Both parse identically so no requirement is violated, but a long hand-edited history reads materially worse in the shipped spelling than in the documented one.
effort: S
kind: inconsistency
area: athlete-benchmarks, src/fitdocs/benchmarks.py, .kiro/specs/athlete-benchmarks/design.md
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 3.2, round-2 review)
pinned_at: c3d2201
resume_command: "/kiro-impl athlete-benchmarks [queue: .kiro/queue/2026-07-26-benchmark-entry-toml-spelling.md] Decide the on-disk benchmark entry spelling and align writer and design"
context:
  - .kiro/specs/athlete-benchmarks/design.md
  - .kiro/specs/athlete-benchmarks/requirements.md
  - src/fitdocs/benchmarks.py
blocked_by: []
---

## What
`benchmarks_to_document` emits each quantity's entries as an array of inline
tables:

    [benchmarks.run]
    lthr_bpm = [
        { value = 165, measured_on = 2025-01-01 },
    ]

`design.md`'s Physical Data Model (~line 1170) documents the array-of-tables
spelling instead:

    [[benchmarks.run.threshold_pace_s_per_km]]

Both are valid TOML, both decode to the same structure, and `parse_benchmarks`
accepts either.

## Why it matters
Req 9.3 requires the file stay "valid, human-readable plain text whose benchmark
entries are understandable without fitdocs installed", and both spellings
satisfy that — this is not a defect. But the file is explicitly hand-editable
and expected to accumulate history, and the two spellings diverge sharply in
readability as the history grows: an array of inline tables becomes one long
bracketed block, while the array-of-tables spelling gives each measurement its
own headed stanza. Since the writer normalises the whole region on every save,
whichever spelling it emits is the one users will actually live with, and a
hand-edited `[[...]]` stanza gets rewritten into the inline form on the next
prompt-driven save.

## Evidence
Writer output, at `84e5e56`: `benchmarks_to_document` in
`src/fitdocs/benchmarks.py` (~`:442-466`) builds a `list` of `dict`s per
quantity, which `tomli_w` renders as an inline-table array. Observed in the
files written by `tests/load/test_profile.py`'s round-trip tests.

Documented shape: `.kiro/specs/athlete-benchmarks/design.md`, Physical Data
Model section (~line 1170), which shows `[[benchmarks.run.threshold_pace_s_per_km]]`.

Reported by the round-2 reviewer subagent of task 3.2 and classified explicitly
as "not a defect — worth a decision".

## How to pick it up
Read the Physical Data Model section of `design.md` and
`benchmarks_to_document` in `src/fitdocs/benchmarks.py`. Write out a realistic
three-year history in both spellings and look at them — this is a judgment about
the artifact the user owns, so make it by looking rather than by reasoning.

Then either change the writer (`tomli_w` emits array-of-tables when the value is
a list of dicts under a nested key path; check what shape it needs) or change
the design's example to match what ships. Whichever way it goes, the round-trip
tests already prove the parser accepts both, so no parser change is needed.

Done when: writer and design agree, and a round-trip test asserts the emitted
**text** spelling rather than only the decoded structure — otherwise the
decision is unpinned and drifts back on the next serializer edit.
