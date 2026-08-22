---
id: 2026-07-29-verificationstatus-lacks-two-needed-terms
title: VerificationStatus has no term for a disputed primary text, a catalogue-sourced year, or a choice that measured nothing — all three were answered by shipping
status: open
importance: medium
importance_why: BANISTER_TRIMP now ships as PRIMARY_TEXT while a companion primary work disagrees with it, and its year rests on a catalogue record rather than the book. Both judgments were defensible and both were recorded only as prose inside the note, so the next citation facing either case has no vocabulary and no precedent to find.
effort: M
kind: gap
area: load-channels, fit-ingest, src/fitdocs/citation.py, src/fitdocs/load/channels/sources.py, src/fitdocs/metrics/sources.py
created: 2026-07-29
surfaced_by: adversarial review of chore/banister-resource-and-note-backstops (queue-top7 batch)
pinned_at: 421c075
resume_command: "do: decide whether VerificationStatus needs terms for (a) primary text read but a companion primary work disagrees, and (b) content primary-attested while a bibliographic field rests on a catalogue record — then either add them or record the ruling that PRIMARY_TEXT plus a disclosing note is the answer [queue: .kiro/queue/2026-07-29-verificationstatus-lacks-two-needed-terms.md]"
context:
  - src/fitdocs/load/channels/sources.py
  - docs/reference/banister-trimp-primary-sources.md
  - .kiro/queue/closed/2026-07-27-banister-morton-primary-texts-obtained.md
  - .kiro/specs/fit-ingest/design.md
blocked_by: []
---

## What

`VerificationStatus` offers `PRIMARY_TEXT` ("the value was read from the cited
work's own text"), `SECONDARY_ATTESTATION`, and `FITDOCS_MEASURED`. The
Banister re-sourcing hit two cases none of them names:

1. **A companion primary work disagrees.** Banister (1991) p. 408 prints
   `y = 0.64e^1.92x`; Morton et al. (1990) Eq. 2 prints `Y = e^bx` with no
   multiplicative coefficient at all. Both are primary texts. The value was
   genuinely read from B91, but a reader who then opens M90 finds something
   different, and a maintainer ruling was required to keep `0.64`.
2. **Content is primary-attested, a bibliographic field is not.** The
   coefficients were read from the book; the **year 1991** rests on the
   Internet Archive / OCLC 1150972541 catalogue record, because the copyright
   page carries no year at all.

Both were resolved by shipping `PRIMARY_TEXT` and disclosing the caveat in the
`note` prose.

3. **`FITDOCS_MEASURED` names a measurement that no record has to have.**
   Added 2026-07-30 from the `fit-ingest` task 12.2 review. This is a third
   instance of the same vocabulary gap, in the enum's remaining member rather
   than in `PRIMARY_TEXT`. `FitdocsChoice.verification` is *type-pinned* to
   `FITDOCS_MEASURED` — `Literal[VerificationStatus.FITDOCS_MEASURED]`, so no
   other value is expressible — while `measurement: str | None = None` is
   optional and is `None` on every record that exists. The status therefore
   asserts a measurement in its name while the type guarantees nothing of the
   kind, and the load layer's own docstring states the real meaning outright:
   *"that status is for a value **no** published work defines"*
   (`src/fitdocs/load/channels/sources.py:58`) — which is a statement about
   provenance, not about measuring anything. `src/fitdocs/metrics/sources.py`
   says the quiet part directly in its module docstring: *"None of the three
   rests on a measurement fitdocs itself took."*

   The pressure is now increasing rather than static: task 12.2 added a
   fourth `FitdocsChoice` (`POWER_ABSENT_SAMPLE_CHOICE`, for the absent-power
   fill), so four records now carry a status named for a measurement none of
   them took. The honest name for what the member actually means is something
   like `FITDOCS_CHOSEN`, with `FITDOCS_MEASURED` reserved for the case where
   `measurement` is populated — but that is exactly the ruling this item
   exists to make, and it should be made once across all three cases rather
   than piecemeal.

## Why it matters

The reviewer judged the shipped answer **correct**: `PRIMARY_TEXT`'s docstring
asserts only that the value was read from *the cited work's* own text, the
cited `work` is B91, and M90's disagreement is a corroboration failure rather
than a defect in the B91 reading. So this is not a mis-statused citation.

The gap is that the *reasoning* lives only in one citation's prose. The
closed item `2026-07-27-banister-morton-primary-texts-obtained` named both
questions as needing a ruling "here", and they were answered by construction
instead of recorded. The next citation that hits either case — and
`fit-ingest`'s Amendment 1 work is actively creating cited constants — has to
re-derive the judgment from scratch, or worse, reach a different one, leaving
two citations with the same status meaning different things.

The whole point of a sealed status union is that a reader can tell what a
status asserts without reading every note.

## Evidence

- `src/fitdocs/load/channels/sources.py` — `VerificationStatus` members and
  their docstrings; `BANISTER_TRIMP` now `PRIMARY_TEXT` with both caveats in
  its `note`.
- `docs/reference/banister-trimp-primary-sources.md` §5 D1 (the disagreement
  and the maintainer ruling), §8 (the catalogue-sourced year), §7 — the
  extraction document flags both as owned by the queue item for a ruling.
- `.kiro/queue/closed/2026-07-27-banister-morton-primary-texts-obtained.md` —
  the item that named them; closed without recording either answer.
- Reviewer verdict: the status choice is honest and the ruling is real
  (`roadmap.md:558-564`, commit `ec44cb6`); only the record is missing.

## How to pick it up

1. Read `VerificationStatus` and the three docstrings, then §5 D1 and §8 of the
   extraction document.
2. Decide, for each case, between: a new enum member; a separate orthogonal
   field (e.g. a `corroboration` or `disputed_by` slot); or a ruling that
   `PRIMARY_TEXT` plus a disclosing note is deliberately the answer.
3. Note fit-ingest already built adjacent vocabulary for the first case —
   `Corroboration`, `Agreement` and `CitedConstant.corroborators`
   (`.kiro/specs/fit-ingest/design.md:103-106`, traceability row `:464`).
   Check whether that mechanism, which `load-channels` inherits without
   currently using, already covers case 1 before adding anything new.
4. Whatever is decided, record it where a future session finds it without
   reading `BANISTER_TRIMP`'s note.

## Open questions

Whether the year problem generalises — if a bibliographic field can be
catalogue-sourced while content is primary-read, the same split could apply to
edition, publisher or page numbering, which argues for a field rather than an
enum member.
