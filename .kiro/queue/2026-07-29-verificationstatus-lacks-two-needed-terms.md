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
pinned_at: c3d2201
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

## Triage note (2026-08-23, `b4ccfa4`) — RAISED IN PRIORITY, blocked on a maintainer ruling

Reviewed during the post-purge queue triage as a load-channels pre-flight
candidate. It is the right thing to do before load-channels adds a citation
record per channel — but it is the one pre-flight item a session must not
decide alone, so it was deliberately left rather than forgotten.

**Why it needs a ruling, not an implementation.** The item's own preferred
answer renames `FITDOCS_MEASURED` to something like `FITDOCS_CHOSEN`. That is
not an internal tidy:

- `FitdocsChoice.verification` is type-pinned as
  `Literal[VerificationStatus.FITDOCS_MEASURED]`, so the rename changes a
  public type, not just a name.
- `VerificationStatus` is exported from `fitdocs.load`, so it is part of the
  plugin surface `plugin-api` publishes and `docs/plugins.md` documents.
- It changes what four already-shipped records *assert*, which is a provenance
  claim about published work — the one class of change this repo's citation
  machinery exists to make deliberate.

**Why it is cheaper before load-channels than after.** load-channels adds
citation records for three channels. Every record written under the current
vocabulary is a record to migrate if the vocabulary changes, and the item
already notes the pressure is increasing rather than static — task 12.2 added a
fourth `FitdocsChoice` since it was filed.

**The three decisions needed**, all answerable in one sitting:

1. Rename `FITDOCS_MEASURED` -> `FITDOCS_CHOSEN`, reserving `FITDOCS_MEASURED`
   for records that actually populate `measurement`? Or keep the name and
   document the divergence?
2. Add a term for "read from the cited work's primary text, but a companion
   primary work disagrees" (the B91 / M90 case), or keep answering it in `note`
   prose?
3. Add a term for "content primary-attested, a bibliographic field
   catalogue-sourced" (the 1991 / OCLC case), or the same?

Partial progress that reduces the cost either way: as of `b4ccfa4`,
`verification` is pinned by `_ATTRIBUTION_BACKSTOPS` in
`tests/load/channels/test_sources.py` (queue
`2026-07-30-citation-authors-year-work-unpinned`), so any change to a record's
status now reds and cannot happen silently. Whatever is decided, the migration
is visible.
