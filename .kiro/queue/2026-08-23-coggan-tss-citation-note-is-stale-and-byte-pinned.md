---
id: 2026-08-23-coggan-tss-citation-note-is-stale-and-byte-pinned
title: COGGAN_TSS's citation note describes a channels package that no longer exists
status: open
importance: medium
importance_why: The note is byte-pinned by task 1.1's test, so it cannot be corrected without editing another task's owned test module — and it will go on aging as tasks 3.2 and 3.3 land.
effort: S
kind: docs
area: load-channels, src/fitdocs/load/channels/sources.py, tests/load/channels/test_sources.py
created: 2026-08-23
surfaced_by: /kiro-impl load-channels task 3.1
pinned_at: 4aba266
resume_command: "do: correct COGGAN_TSS's note in src/fitdocs/load/channels/sources.py and transcribe the new fingerprint into BACKSTOP_COGGAN_TSS_NOTE in tests/load/channels/test_sources.py"
context:
  - src/fitdocs/load/channels/sources.py
  - tests/load/channels/test_sources.py
  - .kiro/specs/load-channels/tasks.md
blocked_by: []
---

## What

`COGGAN_TSS`'s citation note in `src/fitdocs/load/channels/sources.py:153`
still reads that `fitdocs/load/channels/` "holds sources.py, sufficiency.py and
types.py only, and the channel is load-channels task 3.1, not yet written".

Both halves are now false. The directory holds `__init__.py`, `grade.py`,
`power.py`, `sources.py`, `sufficiency.py`, `types.py` and `weighting.py`; the
power channel landed at `4aba266`. The note was already stale for `grade.py`
and `weighting.py` before task 3.1.

The identical text is byte-pinned as `BACKSTOP_COGGAN_TSS_NOTE` in
`tests/load/channels/test_sources.py:77`, which **task 1.1 owns**. Correcting
the note therefore requires editing another task's owned test module, which the
plan's Test File Ownership contract forbids a task from doing on its own.

## Why it matters

The note is a citation record — the artifact this spec built specifically so
provenance claims are checkable rather than aspirational. A citation whose note
misdescribes the code it cites is the same defect species the encumbered-content
purge spent three review rounds on: a pointer that does not resolve.

It will keep aging. Tasks 3.2 and 3.3 add `heart_rate.py` and `pace.py`, making
the file list wronger with each one.

## Evidence

At `4aba266`:

- `src/fitdocs/load/channels/sources.py:153` carries the quoted text
- `ls src/fitdocs/load/channels/` returns seven modules, not three
- `tests/load/channels/test_sources.py:77` pins the string byte-for-byte as
  `BACKSTOP_COGGAN_TSS_NOTE`
- task 3.1's implementer flagged it and declined to edit `sources.py` as out of
  its `PowerChannel` boundary; the reviewer independently confirmed declining
  was correct

## How to pick it up

1. Read `COGGAN_TSS` in `sources.py` and `BACKSTOP_COGGAN_TSS_NOTE` in
   `test_sources.py`.
2. Rewrite the note so it does not enumerate the package's contents at all —
   a list of sibling modules is not what a citation note is for, and it is what
   makes this go stale. State what the citation establishes and where the
   formula is consumed, without a file inventory.
3. Transcribe the new fingerprint into the backstop. The pre-flight branch's
   own guidance applies: adding a field to `Citation` reds all six backstops by
   design — transcribe, do not weaken the helper.

Done looks like: the note carries no claim that a later task can falsify, and
the backstop matches.

## Open questions

- Should citation notes be forbidden from naming sibling modules at all? This
  is the second time a note has gone stale by enumerating its surroundings.

## Additional evidence (2026-09-12, performance-benchmarks 1.2 review)

`COGGAN_TSS.locator` in `src/fitdocs/load/channels/sources.py:127-129` says
"pp. 8-11" for IF/TSS; in the manuscript fetched during that review
(`pdftotext` of the URL the record names) §3 "Analysis of power meter data"
begins on printed p. 7 and the TSS steps run to about p. 9 — re-check the
page range when this item is taken.

(1.2 reviewer, pinned_at d4fbc6f)
