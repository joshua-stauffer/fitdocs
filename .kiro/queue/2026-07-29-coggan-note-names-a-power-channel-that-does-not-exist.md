---
id: 2026-07-29-coggan-note-names-a-power-channel-that-does-not-exist
title: COGGAN_TSS's note credits a load-channels power channel that does not exist
status: open
importance: medium
importance_why: A citation note tells a reader where the cited formula is implemented. This one names a module that has never existed, so anyone verifying the citation looks in the wrong package. It is now frozen under a whole-note backstop, so the wrong pointer is pinned rather than merely present.
effort: S
kind: inconsistency
area: load-channels, src/fitdocs/load/channels/sources.py, tests/load/channels/test_sources.py
created: 2026-07-29
surfaced_by: adversarial review of chore/banister-resource-and-note-backstops (queue-top7 batch)
pinned_at: c3d2201
resume_command: "do: correct COGGAN_TSS.note's claim that the TSS formula is what 'this package's power channel already implements' — there is no power channel; it ships in src/fitdocs/metrics/stress.py:119 power_tss — and move BACKSTOP_COGGAN_TSS_NOTE in the same commit [queue: .kiro/queue/2026-07-29-coggan-note-names-a-power-channel-that-does-not-exist.md]"
context:
  - src/fitdocs/load/channels/sources.py
  - tests/load/channels/test_sources.py
  - src/fitdocs/metrics/stress.py
  - .kiro/specs/load-channels/research.md
blocked_by: []
---

## What

`COGGAN_TSS.note` in `src/fitdocs/load/channels/sources.py` states that the
training-stress formula it cites is what *"this package's power channel
already implements"*.

There is no power channel. `src/fitdocs/load/channels/` contains exactly
`__init__.py` and `sources.py` — the `BANISTER_TRIMP` note in the same module
says so itself, describing the heart-rate channel as "not yet implemented as
of this writing". The formula actually ships in
`src/fitdocs/metrics/stress.py:119` as `power_tss`, which is what
`.kiro/specs/load-channels/research.md:104` correctly records.

## Why it matters

The purpose of a citation note in this repo is to let a reader verify the
claim without re-doing the search — that is why the notes carry page numbers,
quoted equations, and statements about what each text does and does not
contain. A note that misdirects a reader to a non-existent module fails at
exactly that job, and does so with the authority of a record that has been
through review.

The defect is **pre-existing**, not introduced by the 2026-07-29 re-sourcing
change. But that change added a whole-note equality backstop over this note,
so the wrong pointer is now pinned: any future correction must move
`BACKSTOP_COGGAN_TSS_NOTE` in the same commit, and the pin will keep the
error stable in the meantime. This is a concrete instance of the peer
session's standing warning that **a whole-value backstop pins text, not
truth** — the machinery is working exactly as designed and preserving a
falsehood.

## Evidence

```
$ ls src/fitdocs/load/channels/
__init__.py  sources.py

$ grep -n "power_tss" src/fitdocs/metrics/stress.py
119:def power_tss(...)
```

`.kiro/specs/load-channels/research.md:104` records the formula's home
correctly. The note's own sibling in the same module (`BANISTER_TRIMP`)
independently confirms no channel is implemented yet.

Found during the round-2 adversarial review of
`chore/banister-resource-and-note-backstops`, while sweeping the five notes
the round-1 truth-check had not covered in depth.

## How to pick it up

1. Read `COGGAN_TSS` in `src/fitdocs/load/channels/sources.py` and locate the
   "power channel" phrase.
2. Check the rest of that note while you are there — the round-2 review
   verified its NP algorithm and `TSS = duration_s * NP * IF / (FTP * 3600) *
   100` against `research.md:103-105`, and its Banister-1975 attribution
   against `research.md:53`, all correct. Only the implementation pointer is
   wrong.
3. Repoint it at `src/fitdocs/metrics/stress.py`'s `power_tss`, or state
   plainly that no load-channel consumes it yet.
4. **Update `BACKSTOP_COGGAN_TSS_NOTE` in the same commit** or the suite will
   red — and verify the backstop still discriminates afterwards with a
   single-clause mutation.
5. Sweep the other four notes for the same species of claim (a pointer to
   where something is implemented) while you are in the file.
