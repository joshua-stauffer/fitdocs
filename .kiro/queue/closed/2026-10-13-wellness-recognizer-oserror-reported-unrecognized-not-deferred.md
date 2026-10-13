---
id: 2026-10-13-wellness-recognizer-oserror-reported-unrecognized-not-deferred
title: "wellness-store design: an OSError raised inside a recognizer is swallowed as 'no claim', so an unreadable candidate is reported unrecognized instead of deferred, contradicting its own probe section and Req 1.2"
status: done
importance: high
importance_why: The maintainer's data root and inbox sit on iCloud Drive, where a file can be evicted or only partly present and a read fails with OSError; the design as written gives such a file a false 'no supported wellness format reads this file' verdict. The file is not lost (it stays in place and is probed again), but the contradiction is cheap to fix now and expensive once tasks 1.2, 1.3 and 3.3 have encoded both halves in tests.
effort: S
kind: inconsistency
area: wellness-store, src/fitdocs/wellness/registry.py, src/fitdocs/wellness/probe.py, src/fitdocs/wellness/intake.py
created: 2026-10-13
surfaced_by: /kiro-spec-batch phase 12 (wellness-store spec, controller queue triage)
pinned_at: 86cdf14
resume_command: "do: amend wellness-store design § Registry (design.md:544) and § Probe (design.md:650) so an OSError raised from a probe read, including one inside a recognizer, defers the candidate instead of counting as no claim, and amend tasks 1.2, 1.3 and 3.3 (and the 3.1 matrix) in .kiro/specs/wellness-store/tasks.md before running /kiro-impl wellness-store 1.2 [queue: .kiro/queue/2026-10-13-wellness-recognizer-oserror-reported-unrecognized-not-deferred.md]"
context:
  - .kiro/specs/wellness-store/design.md
  - .kiro/specs/wellness-store/requirements.md
  - .kiro/specs/wellness-store/tasks.md
  - .kiro/specs/inbox/design.md
  - .kiro/queue/2026-08-23-data-root-readers-have-no-cloud-placeholder-category.md
blocked_by: []
---

## What

wellness-store's design says two incompatible things about a read error during
recognition.

- § Registry: "`recognize(probe)` ... A recognizer that raises counts as no
  claim." A recognizer reads through the lazy probe methods `probe.json()` (the
  whole file when it is at most 64 MiB) and `probe.zip_members()` (the zip
  central directory, which sits at the end of the file).
- § Probe: "Every read error propagates as `OSError` (the intake maps it to
  deferral)", and § Intake: `identify` maps an `OSError` to `Deferred`.

The two meet in `recognize`. An `OSError` raised by `probe.json()` or
`probe.zip_members()` inside a recognizer is caught by the "raises" rule, so it
never reaches `identify`. If no other format claims the file, the candidate
is reported `Unrecognized` ("no supported wellness format reads this file")
and left in place, where the correct outcome is `Deferred` ("could not be
read ...; retried on a later drain"). Requirement 1.2 asks for
exactly that deferral: an "unreadable wellness candidate" is deferred "exactly
as it defers a `.fit` file".

## Why it matters

A candidate that is evicted, partly downloaded or on a flaky volume gets a
wrong, alarming verdict about its content instead of a retry note. For a
multi-gigabyte `export.zip`, the one read that decides recognition is at the
tail of the file, far from the 64 KiB head that `CandidateProbe.open` reads
first. The FIT path does not have this problem: its content hash read doubles
as the readability probe and a failed read is a deferral (inbox design).
In the wellness path `identify` runs `recognize` before `hash_file`, so
recognition's lazy reads are the first deep reads.

The file is not lost: unrecognized files stay in place and are probed on every
later drain (see `.kiro/queue/2026-10-13-unrecognized-wellness-files-reported-on-every-drain.md`),
so the harm is a misleading report. It is rated high because the fix is a
one-sentence design change today and a coordinated test change after tasks 1.2,
1.3 and 3.3 pin the current behaviour.

## Evidence

Read at `86cdf14` (design text only; the package is not implemented yet).

- `.kiro/specs/wellness-store/design.md:542-544` -- `recognize`: "A recognizer
  that raises counts as no claim."
- `.kiro/specs/wellness-store/design.md:621-651` -- § Probe: `json()` and
  `zip_members()` are lazy methods (`:630-634`); `:650-651` "Every read error
  propagates as `OSError` (the intake maps it to deferral)."
- `.kiro/specs/wellness-store/design.md:1012-1014` -- § Intake: `identify` is
  `CandidateProbe.open` -> `recognize` -> `hash_file`; `OSError` -> `Deferred`.
  There is no `OSError` branch inside `recognize`.
- `.kiro/specs/wellness-store/requirements.md:123` -- Req 1.2 (defer an
  unreadable wellness candidate exactly as a `.fit` file).
- `.kiro/specs/wellness-store/tasks.md:282-284` -- task 1.3's tests require "a
  raising recognizer counted as no claim"; `:700-707` -- task 3.3 tests an
  `OSError` "in the probe and in hashing" -> deferred, with the mutation "map a
  probe `OSError` to unrecognized", but no case puts the `OSError` inside a
  recognizer's lazy read. Task 1.2 (`:217-253`) tests `json()` and
  `zip_members()` on decoys but never on a failing read.
- The deferral precedent: `.kiro/specs/inbox/design.md:259` ("A read that
  fails is treated as a deferral with its reason ... a timing problem") and
  `tests/test_drain.py:311`.
- Storage exposure: `.kiro/steering/roadmap.md:2108` ("The real data root is
  in iCloud Drive"); the sibling data-root item
  `.kiro/queue/2026-08-23-data-root-readers-have-no-cloud-placeholder-category.md`
  records the dataless-file behaviour this inherits.
- Unverified: whether macOS fails the head read in `CandidateProbe.open` first
  for an evicted file, which would defer it before any recognizer runs. A
  partly materialized file, or an I/O error after the head, still takes the
  path above.

## How to pick it up

1. Amend the design before task 1.2 starts. Choose one rule and state it in
   both sections: `recognize` re-raises `OSError` (only non-`OSError`
   exceptions count as no claim) and `identify` already maps it to
   `Deferred`; or `recognize` returns a third variant carrying the error.
   The first is the smaller change.
2. Amend the tests the same way: task 1.3's raising-recognizer case becomes
   two (a `ValueError` is no claim, an `OSError` propagates); task 1.2 adds a
   failing-read case for `json()` and `zip_members()`; task 3.3 adds the
   recognizer-internal `OSError` case with a mutation that restores the
   swallow; task 3.1's matrix gets one unreadable-candidate row.
3. Done when no sentence in the design says a recognizer's read error means
   "unrecognized" and a mutation that catches `OSError` in `recognize` reds a
   named test.

## Open questions

- Should a recognizer be allowed to raise any exception at all, or should the
  registry require recognizers to return `False` and let only the probe raise?
  The design's current wording (§ Seams, "returns `False` rather than raising
  for a file it does not want", `design.md:1513-1514`) already points that
  way.

## Resolution
Done 2026-10-13 at 0e2cd09 (before any wellness-store task started): took the
smaller rule. `recognize` re-raises `OSError` at once (without asking the
remaining formats) and `identify` maps it to `Deferred`; any other
recognizer exception still counts as no claim, as a defensive backstop to the
§ Seams rule that recognizers return `False` rather than raise (open question
answered: keep the backstop, do not widen it to `OSError`). `json()` /
`zip_members()` still return `None` for a decode error or a non-zip, which
are not read errors. Tasks: 1.2 adds a failing-read opener mode plus
`json()`/`zip_members()` cases on files larger than `HEAD_BYTES` (the size
matters: a file inside the head never reads past it); 1.3 splits the
raising-recognizer case into `ValueError` (no claim) and `OSError`
(propagates), with a mutation that catches `OSError` in `recognize`; 3.1
gains one unreadable matrix row; 3.3 a recognizer-read `OSError` → deferred
case with the swallow mutation. Unverified item left as is: whether macOS
fails the head read first for an evicted file is irrelevant now, since both
paths defer.
