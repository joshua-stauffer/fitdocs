---
id: 2026-07-26-citation-vocabulary-diverges-across-layers
title: fit-ingest Amendment 1 forbids the secondary-attestation fallback that load-channels' citation record is built on
status: done
importance: medium
importance_why: Two layers will hold contradictory rules for the same vocabulary — load-channels' BANISTER_TRIMP note explicitly defers re-sourcing to fit-ingest, and fit-ingest has now accepted it under a stricter bar that load-channels itself does not meet.
effort: S
kind: spec
area: fit-ingest, load-channels, src/fitdocs/load/channels/sources.py
created: 2026-07-26
surfaced_by: /kiro-spec-requirements fit-ingest (Amendment 1, primary sourcing for the metrics layer's constants)
pinned_at: spec/fit-ingest-primary-sourcing
resume_command: "do: reconcile the citation vocabulary across fit-ingest and load-channels — decide whether VerificationStatus.SECONDARY_ATTESTATION remains acceptable in load-channels now that fit-ingest Req 15.4 forbids it for the layer beneath, and update src/fitdocs/load/channels/sources.py's BANISTER_TRIMP note, which currently says re-sourcing is out of scope [queue: .kiro/queue/2026-07-26-citation-vocabulary-diverges-across-layers.md]"
context:
  - src/fitdocs/load/channels/sources.py
  - .kiro/specs/fit-ingest/requirements.md
  - .kiro/specs/load-channels/requirements.md
  - .kiro/queue/2026-07-26-channel-citations-unverified.md
blocked_by: []
---

## What

fit-ingest Amendment 1 (2026-07-26) adds Requirement 15.4, which forbids
recording a secondary attestation in place of a primary-text verification: a
constant whose primary text cannot be obtained blocks the feature rather than
shipping under a weaker status. That is deliberately stricter than the pattern
`load-channels` established one layer up, where `MINETTI_2002` and
`BANISTER_TRIMP` both ship as `SECONDARY_ATTESTATION` with a note explaining
why the primary text was not obtained — and where that honest downgrade is the
*recommended* remedy, per step 4 of
`.kiro/queue/2026-07-26-channel-citations-unverified.md`.

Two concrete inconsistencies follow once fit-ingest Amendment 1 is implemented:

1. `src/fitdocs/load/channels/sources.py:112-118` — `BANISTER_TRIMP`'s note
   says "fitdocs consumes these coefficients unchanged from the shipped
   `metrics.stress.trimp` definition; re-sourcing them is out of this feature's
   scope." fit-ingest has now taken that scope. The note becomes stale the
   moment Amendment 1 lands, and it is the only record telling a reader why
   that citation is secondary.
2. The same coefficients will carry two different verification statuses in one
   codebase — `SECONDARY_ATTESTATION` in `load-channels`, primary-text-verified
   in fit-ingest — with no statement of which is authoritative.

## Why it matters

Not a correctness bug: no number changes and no test fails. It is a
provenance-record contradiction, which is exactly the class of defect the
citation vocabulary exists to prevent. `load-channels` Requirement 8.2 forbids
presenting a secondary attestation as a primary one; nothing yet forbids two
layers disagreeing about which one a value is. A reader auditing where `0.64`
and `1.92` came from will find two answers.

The decision is genuinely open, and it is a product decision rather than a
cleanup: either `load-channels` adopts fit-ingest's stricter bar (and its four
unverified `PRIMARY_TEXT` entries plus two `SECONDARY_ATTESTATION` ones all
come due), or the two layers keep different bars and that difference is stated
explicitly in both. Do not pick one silently.

## Evidence

- `.kiro/specs/fit-ingest/requirements.md` Req 15.4 (added by Amendment 1):
  "an attestation from secondary sources shall not be recorded in place of a
  primary-text verification".
- `src/fitdocs/load/channels/sources.py:104-119` — `BANISTER_TRIMP`,
  `SECONDARY_ATTESTATION`, with the "out of this feature's scope" note.
- `src/fitdocs/load/channels/sources.py:121-134` — `MINETTI_2002`, the same
  pattern, unaffected by fit-ingest's scope but subject to the same question.
- `.kiro/queue/2026-07-26-channel-citations-unverified.md` step 4 recommends
  precisely the downgrade fit-ingest Req 15.4 now forbids one layer down.

## Update (2026-07-26): narrowed, not closed

fit-ingest's Amendment 1 was revised at its design gate (`2e13925`) to add a
**fitdocs-chosen** category — criteria 15.8, 15.9 and 16.7 — because three of
the seven items Req 15.6 names (which together enumerate eight constants, per
`.kiro/queue/2026-07-26-amendment-1-constant-count-ambiguous.md`, reopened,
proposed resolution) are
defined by no published work at all (the moving-time threshold, the
normalized-power minimum span, the altitude-smoothing window), and without a
category for them Req 15.4 blocked the feature permanently rather than
pending research.

This narrows the divergence rather than resolving it. The new category is
deliberately `VerificationStatus.FITDOCS_MEASURED`'s existing semantics
(`sources.py:60`) rather than a fourth vocabulary, so the two layers now agree
on the *shape* of the record and differ on exactly one point: whether
`SECONDARY_ATTESTATION` is permitted. Req 15.4 still forbids it for fit-ingest;
`MINETTI_2002` and `BANISTER_TRIMP` still ship under it in `load-channels`.

Both open questions below stand unchanged.

## Open questions

- Does `load-channels` adopt Req 15.4's bar, or do the layers keep different
  bars with the difference stated? If the former, the existing
  `channel-citations-unverified` item's remedy changes and its four
  `PRIMARY_TEXT` entries can no longer be resolved by downgrading.
- Which spec owns the vocabulary once fit-ingest also needs it? fit-ingest is
  *upstream* of `load-channels`, so it cannot import
  `fitdocs.load.channels.sources`. That is a fit-ingest design-phase question
  (Req 16.1), but the answer determines whether one vocabulary or two exist.

## Resolution (proposed, 2026-07-27) — NOT verified done, reopened

This section was previously written as a closing `## Resolution` and the item
moved to `.kiro/queue/closed/` with `status: done` by the implementing
session. That close was premature by this skill's own gate
(`.claude/skills/kiro-queue/SKILL.md:141`, "verify it is actually done...
do not close on assertion") for two concrete reasons, found on remediation of
a rejected review:

1. **Not yet merged.** The work sits on `chore/citation-vocabulary-unify`
   (worktree `../fitdocs-citations`), which this same Resolution's first
   paragraph already said out loud — "not yet merged to `main`". Work that is
   not on `main` is not done; it is a proposal awaiting review and merge.
2. **The second open question was declared answered when it was not.** The
   "Vocabulary ownership... is unaffected" bullet below treats "no cross-layer
   import change happened yet" as though it resolves *which spec owns the
   vocabulary once fit-ingest also needs it* — it doesn't. fit-ingest's
   `citation.py`/`sources.py` module is still design-only; the ownership
   question is deferred, not answered, and remains genuinely open until
   fit-ingest's own implementation lands and actually re-exports (or
   duplicates) this vocabulary.

Reopening with `status: open`, restoring the file to `.kiro/queue/`. The
`## Resolution` below is left as the implementer's PROPOSAL, not a closing
record — a human should review the branch before this item is closed for
real.

Maintainer decision: `load-channels` adopts fit-ingest Req 15.4's bar rather
than keeping the weaker one. Implemented on `chore/citation-vocabulary-unify`
(worktree `../fitdocs-citations`, not yet merged to `main` — left for the
dispatching session per its instructions).

- `load-channels/requirements.md` gained criteria 8.9 (a new
  `SECONDARY_ATTESTATION` is forbidden where a defining published work
  exists) and 8.10 (an exception under 8.9 must record its search), mirroring
  fit-ingest Req 15.4 without adopting fit-ingest's separate 15.8/15.9
  fitdocs-chosen category — that category answers a different question (no
  published work defines the value at all) that does not apply to any of
  this layer's citations.
- Three of the four `SECONDARY_ATTESTATION` citations were re-sourced to
  `PRIMARY_TEXT` after locating and reading their actual primary texts this
  session: `COGGAN_TSS` (retargeted from the unread 2010 book to Coggan's own
  2003 chapter-length manuscript, found at
  `ipmultisport.com/ref_lib/Coggan_Power_Meter.pdf`, which states the
  NP/IF/TSS algorithm directly), `MINETTI_2002` (the paper's own Fig. 1
  caption, via an open PDF mirror, gives both 5th-order polynomial
  regressions verbatim), and `INTERVALS_ICU_PACE_LOAD` (the forum text was
  already read in the prior session but held at `SECONDARY_ATTESTATION`
  regardless; narrowed to what it actually supports and upgraded, matching
  `TRAININGPEAKS_COVERAGE_GATE`'s existing honest-scope-gap pattern).
- `BANISTER_TRIMP` remains `SECONDARY_ATTESTATION` and could not be
  re-sourced: Banister (1991) is a book chapter held by the Internet Archive
  under controlled digital lending (a borrow queue, not open access) and
  Morton, Fitz-Clarke & Banister (1990, *J Appl Physiol* 69(3):1171-1177) is
  a paywalled journal article with no free mirror found (ResearchGate
  returned HTTP 403). This is the same accepted risk fit-ingest's own
  Amendment 1 named for the identical two sources. It is now recorded as a
  named, tracked exception via a new `BLOCKED_CITATIONS: Final[frozenset[str]]`
  in `sources.py`, guarded by
  `test_no_new_secondary_attestation_citations_exist` — not silently
  accepted, and not fabricated into `PRIMARY_TEXT` or `FITDOCS_MEASURED`
  (a defining work exists, so it is not eligible for the latter).
- Vocabulary ownership (the second open question): fit-ingest's own
  `citation.py` module is still design-only, not implemented, so this session
  made no cross-layer import change and `VerificationStatus` stays defined
  locally in `load.channels.sources` with its three members unchanged.
  **Correction (remediation, below): this is a deferral, not an answer.**
  Calling the question "unaffected" was itself premature — which spec owns
  the vocabulary once fit-ingest also needs it is still genuinely open and
  remains so until fit-ingest's own implementation lands and either
  re-exports or duplicates this vocabulary.
- Follow-up: obtaining Banister (1991) or Morton et al. (1990) — e.g. via
  interlibrary loan or an Internet Archive borrow — would let
  `BANISTER_TRIMP` clear `BLOCKED_CITATIONS` too. Not queued separately since
  it is the same named, accepted risk fit-ingest's own Amendment 1 already
  carries for the identical sources; re-attempt whenever that risk is next
  revisited.

### Remediation (2026-07-27, second implementer, on the same branch)

A review of the branch found all four citations themselves real, primary,
accurately quoted and numerically exact, but six defects in the surrounding
provenance record. All six were fixed on this same branch (commits after the
two above; see the branch's own log for exact SHAs):

1. `BANISTER_TRIMP.note` falsely claimed "no computed value depends on
   resolving this citation." fit-ingest's own Amendment 1 rationale says the
   sex-neutral collapse "is a different reported number for some athletes,"
   and this package's heart-rate channel consumes that exact coefficient
   pair (Req 8.6) — a real dependency. Corrected.
2. The guard's prose claimed a completeness property (`CITATIONS` cannot
   silently omit a citation) that the code did not actually enforce — a
   `SNEAKY_NEW` citation defined but never appended to `CITATIONS` left the
   suite green. Added an AST-based registry-completeness test
   (`test_every_module_level_citation_is_registered_in_citations`) that
   walks the module's own source rather than trusting the hand-maintained
   tuple; verified it fails on that exact mutation.
3. `requirements.md` Req 7.9 said the Minetti walking form "was not
   obtained," which the re-sourcing to `PRIMARY_TEXT` falsified — both
   polynomials are in the same read Fig. 1 caption. Amended 7.9 to state
   the true reason (a scope choice, not unavailability) rather than leave
   design.md's already-corrected traceability row standing against a
   contradicted, unamended criterion.
4. `BANISTER_TRIMP.note` also read "x" green under a mutation (non-empty,
   but recording no search at all). Added
   `test_blocked_citation_notes_name_both_attempted_sources`, which pins
   that a `BLOCKED_CITATIONS` note must name both candidate primary texts
   and why each attempt failed; verified it fails on that exact mutation.
5. **Open question for the maintainer, stated rather than decided here:**
   load-channels' Req 8.9/8.10 is a *named-exception variant* of fit-ingest
   Req 15.4, not the identical bar — 15.4 blocks fit-ingest's completion
   outright for an unobtainable primary text, with no exception set; 8.10
   instead lets `BANISTER_TRIMP` ship as a tracked exception in
   `BLOCKED_CITATIONS`. Softened `sources.py`'s and `design.md`'s "holds
   itself to the same bar" language to say so explicitly. **Is that variant
   a faithful implementation of "load-channels adopts fit-ingest's bar," or
   is it a weakening the maintainer did not intend?** If the latter, 8.10's
   exception mechanism should be removed and `BANISTER_TRIMP` should block
   this feature's completion the same way an unobtainable primary text
   blocks fit-ingest's.
6. `BANISTER_TRIMP.work` cited "Physiological Testing of Elite Athletes"
   (the 1982 first edition's title) under `year=1991`; the citation's own
   note, correctly, names the 1991 second edition ("Physiological Testing
   of the High-Performance Athlete," Human Kinetics) held by archive.org.
   Corrected the `work` field to match.

`uv run pytest && uv run ruff check . && uv run mypy` all green after the
above (1873 passed at the time this section was written; the count has
since moved with rebases onto `main` — see the round-2 remediation below for
the current figure). Still not merged to `main`.

### Remediation round 2 (2026-07-27, third session, on the same branch)

A second review rejected round 1 on five defects plus two nits, after
confirming Fix 1 (dependency claim), Fix 4 (the `note="x"` mutation redding)
and Fix 6 (the 1991 edition title) as correctly fixed and the reopening
above as correct. All five must-fixes and both nits were addressed on this
same branch:

1. **The round-1 registry guard (item 2 above) saw exactly one spelling of
   "define a Citation"; four evasions shipped green.** `Citation(...)` with
   no annotation, `Final[Citation] = _make(...)` through an aliased factory,
   definitions nested inside `if True:`/`if TYPE_CHECKING:`, and
   `_C = Citation` followed by `_C(...)` all left the AST-based
   `test_every_module_level_citation_is_registered_in_citations` green while
   shipping an unregistered `SECONDARY_ATTESTATION` citation. Replaced the
   AST walk with a runtime check —
   `{v for v in vars(sources).values() if isinstance(v, Citation)} -
   set(CITATIONS)` — which closes all four in one line, needs no source
   parsing, and does not care how a `Citation` was spelled. Verified: all
   four evasions above, plus the original mutation (a `Citation` never
   appended to `CITATIONS` at all), red this test; citations registered via
   `+`-concatenation, an `*_EXTRA`-suffixed name, or a non-literal
   `CITATIONS` right-hand side are unaffected by the change (still correctly
   caught by the other vocabulary tests when they carry an unblocked
   `SECONDARY_ATTESTATION`, not by this registry-completeness test, which is
   the correct division of labor).
2. **Req 7.9's own pinning test still asserted the falsified claim and could
   not discriminate.** `test_minetti_note_records_walking_form_not_implemented`'s
   docstring still read "the Minetti citation records that the walking form
   was not obtained" — the exact claim item 3 above corrected in
   `requirements.md`. The test itself only grepped for `"walking"` and
   `"not implemented"`, both of which a falsified note (walking form claimed
   "NOT OBTAINED") also satisfies. Corrected the docstring and added a
   positive check for `"read alongside"` plus a negative check ruling out
   `"not obtained"`; verified the exact falsification mutation now reds.
3. **A dangling cross-reference.** `BLOCKED_CITATIONS.__doc__` pointed at
   "the module docstring's 'One bar across both layers' section" — a
   section round 1 itself had renamed to "A named-exception variant of
   fit-ingest's bar". Repointed.
4. **The normative text was the one place not softened to match the
   mechanism.** `requirements.md` criterion 8.9 still said the layer "shall
   hold itself to the same bar" as fit-ingest Req 15.4, with no exception
   mentioned, while criterion 8.10 grants the tracked exception 15.4
   forbids — a self-contradiction. **Maintainer ruling (received
   2026-07-27): the tracked-exception variant is acceptable** —
   `BANISTER_TRIMP` may ship under `SECONDARY_ATTESTATION` while named in
   `BLOCKED_CITATIONS`. This closes item 5's open question above. Amended
   8.9 to describe the named-exception variant honestly and to record the
   ruling, matching the wording already used in `sources.py`'s module
   docstring and design.md's ProvenanceRecord bullet; amended design.md's
   traceability row to match.
5. **Three unreconciled copies of the walking-form claim in `research.md`,
   only one of which round 1 had mentioned.** `:107-108`'s "the walking
   polynomial could not be obtained at all" and `:317`'s "Coefficients not
   verified against primary text" (on the Minetti reference; the identical
   marker on Banister at `:310` is still correct and was left alone) both
   read as live findings, since `research.md` carries no per-finding date
   stamps. Appended the same dated "Superseded 2026-07-27" amendment
   parenthetical already used in `requirements.md` and `tasks.md` to both.

Nits also addressed:

- `BANISTER_TRIMP.note` was present-tense about a heart-rate channel that
  does not exist yet (`src/fitdocs/load/channels/` holds only `sources.py`
  and `__init__.py`); corrected to say so and to note the dependency is
  narrower than the raw coefficient pair suggests — this feature's own
  research (research.md, "The disputed Banister coefficient largely
  cancels") found that HRSS's ratio form cancels the 0.64 multiplicative
  coefficient exactly, so only the 1.92 exponent survives into the result.
- `test_blocked_citation_notes_name_both_attempted_sources`'s docstring
  claimed the test "requires the note to actually name the search"; it
  actually enforces a length floor plus four substring checks, not a
  semantic read. Docstring corrected to say so.
- This section's own "1873 passed" claim above was stale post-rebase, and so
  would any single fixed count be the moment `main` next moves; see the
  final validation line below for the count as of the commit that closes
  this remediation, not as a number expected to still match by the time
  this item is read.

A sixth, out-of-boundary copy of the stale claim was found and is recorded
here rather than fixed on this branch, since it sits in a different spec:
`.kiro/specs/threshold-load/research.md:108` still reads "Minetti's walking
polynomial was not obtained" in a bullet about anchoring Walk/Hike. Left
unedited — outside this branch's `load-channels` boundary — but flagged for
whoever next touches `threshold-load/research.md`.

`uv run pytest && uv run ruff check . && uv run mypy` all green after the
above and after a further rebase onto local `main` (which had itself moved
during this remediation): 1889 passed. Still not merged to `main`.

## Closed (2026-07-27, maintainer confirmed, verified on `main`)

Both reasons the previous close was reversed are now discharged, and the
maintainer confirmed the close.

**1. Merged.** `chore/citation-vocabulary-unify` landed on `main` `--ff-only`
(agent-log `2026-07-27T07:54:07Z`), worktree and branch removed, validated on
`main`. Re-verified against `main` at `4a5c838` rather than trusting that log
line:

- `sources.py:174` — `BLOCKED_CITATIONS: Final[frozenset[str]] =
  frozenset({"banister_trimp"})` is present, with the runtime registry guard
  and the note requirements described above.
- `sources.py` — `COGGAN_TSS`, `MINETTI_2002` and `INTERVALS_ICU_PACE_LOAD`
  all carry `VerificationStatus.PRIMARY_TEXT`; `BANISTER_TRIMP` (`:193`) is
  the sole remaining `SECONDARY_ATTESTATION`, and it is the sole member of
  `BLOCKED_CITATIONS`.
- `load-channels/requirements.md:270-271` — criteria 8.9 and 8.10 exist, 8.9
  in its corrected named-exception-variant wording carrying the maintainer's
  2026-07-27 ruling, 8.10 requiring the exception to record its search.
- `load-channels/requirements.md:252` — Req 7.9 amended to the true reason
  the Minetti walking form is unimplemented (a scope choice, not a sourcing
  gap).

The first open question is therefore answered and implemented: `load-channels`
adopts fit-ingest Req 15.4's bar as a named-exception variant, ratified.

**2. The vocabulary-ownership question is answered, and tracked where it
belongs.** The remediation was right that "no cross-layer import change
happened yet" is a deferral rather than an answer — but fit-ingest's design
phase, which this item explicitly handed the question to, has since answered
it on the record: `fit-ingest/spec.json` `amendments[0].design` decision (1)
states that `VerificationStatus`/`Citation` move to a dependency-free
`src/fitdocs/citation.py` which `load.channels.sources` re-exports, so exactly
one vocabulary exists, and that the edit is import-only with
`tests/load/channels/test_sources.py` passing unmodified as its evidence.
`fit-ingest/design.md` carries the same. That is spec-owned work under
fit-ingest Amendment 1 (roadmap Phase 4), so it is exempt from the queue per
`.kiro/queue/README.md` — it is not dropped by closing this item.

**Two follow-ups this close does not carry, queued separately** so they do not
travel into `closed/` with this file:

- `.kiro/queue/2026-07-27-banister-morton-primary-texts-obtained.md` — both
  blocked primary texts have since been obtained locally, which is exactly the
  condition the "Follow-up" bullet above said would let `BANISTER_TRIMP` clear
  `BLOCKED_CITATIONS`.
- `.kiro/queue/2026-07-27-threshold-load-research-walking-form-stale.md` —
  the sixth, out-of-boundary copy of the falsified walking-form claim at
  `.kiro/specs/threshold-load/research.md:108`, recorded above but never
  queued in its own right.
