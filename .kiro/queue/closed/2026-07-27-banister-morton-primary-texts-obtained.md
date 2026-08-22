---
id: 2026-07-27-banister-morton-primary-texts-obtained
title: Banister (1991) and Morton (1990) primary texts have been obtained — BANISTER_TRIMP can clear BLOCKED_CITATIONS
status: done
importance: high
importance_why: The only blocking condition on two separate specs' named, accepted schedule risk has just been removed. Both fit-ingest Req 15.4 and load-channels' BLOCKED_CITATIONS exception exist solely because these texts were unobtainable; they no longer are, and the exception mechanism is only honest while the search genuinely fails.
effort: M
kind: gap
area: load-channels, fit-ingest, src/fitdocs/load/channels/sources.py
created: 2026-07-27
surfaced_by: /kiro-queue close 2026-07-26-citation-vocabulary-diverges-across-layers (untracked primary texts found in the working tree)
pinned_at: 4a5c838
resume_command: "do: re-source BANISTER_TRIMP from SECONDARY_ATTESTATION to PRIMARY_TEXT against the extraction in docs/reference/banister-trimp-primary-sources.md, remove it from BLOCKED_CITATIONS (leaving the frozenset empty rather than deleting the mechanism), and reconcile every prose claim in load-channels, fit-ingest and roadmap.md that names these two texts as an unobtainable, accepted risk [queue: .kiro/queue/2026-07-27-banister-morton-primary-texts-obtained.md]"
context:
  - docs/reference/banister-trimp-primary-sources.md
  - src/fitdocs/load/channels/sources.py
  - tests/load/channels/test_sources.py
  - .kiro/specs/load-channels/requirements.md
  - .kiro/specs/fit-ingest/requirements.md
  - .kiro/specs/fit-ingest/spec.json
blocked_by: []
---

> **Amended 2026-07-27 by session `banister-primary-text`, after this item was
> written.** Both texts have now been **read in full** and extracted to
> `docs/reference/banister-trimp-primary-sources.md`. That retires steps 1–2
> below and changes the answer to steps 3–4. Specifically:
>
> - **Step 1 is done, by the other route this item allows.** Both sources are
>   now gitignored at the repo root alongside the source workbooks rather than
>   relocated, matching the established precedent for unredistributable source
>   material. Verified by probe build: the sdist excludes both, while an
>   unignored control file in the same position is included — so the ignore
>   rules, not luck, are what keep them out of a published artifact.
> - **The exponent checks out; the coefficient does not, cleanly — but it is now
>   ruled on.** Banister 1991 p. 408 states `y = 0.64·e^(1.92x)` (male) /
>   `0.86·e^(1.67x)` (female). Morton 1990 Eq. 2 p. 1172 states `Y = e^(bx)`,
>   b = 1.92 / 1.67 — **with no multiplicative coefficient at all**. That
>   triggered step 4's "does not check out" branch, and the maintainer ruled
>   2026-07-27 to **keep `0.64`**, which is what `stress.py` already ships. So
>   step 4 does *not* apply after all: **no constant changes and no migration is
>   owed.** Closed as `.kiro/queue/closed/2026-07-27-trimp-coefficient-b91-vs-m90.md`,
>   whose Resolution hands this item two obligations: the citation note must
>   name **both** forms and say which fitdocs ships, and `VerificationStatus`
>   has no term for "primary text, but a companion primary text disagrees" —
>   decide here whether `PRIMARY_TEXT` plus a note suffices.
> - **The shipped values are the sex-specific male pair, applied sex-neutrally.**
>   Both texts define b per sex; fitdocs applies 1.92 to everyone. Now confirmed
>   as a real deviation from both primary texts, not a sourcing artifact.
> - **`roadmap.md`'s refutation has been withdrawn** (done 2026-07-27, not
>   pending). It listed the web-quoted `0.64·e^(1.92·%HRR)` men / `1.67` women
>   string under "Also rejected (refuted 0-3)"; Banister p. 408 states exactly
>   that pair. The "refuted 0-3" framing in this item's own *Why it matters*
>   section should be read in that light. The Phase 4 fit-ingest roadmap entry
>   now records the ruling and no longer warns that document access is needed.
> - **Do not use the primary text's worked examples as test vectors.** All
>   three of Banister's printed examples contradict his own equation; see
>   `2026-07-27-banister-figure-captions-unusable-as-vectors`.
> - **The bibliographic frame is complete.** Cover, title page and copyright page
>   were added 2026-07-27: editors **MacDougall, Wenger & Green**, **second
>   edition**, **Human Kinetics Books, Champaign, Illinois**, published for the
>   Canadian Association of Sport Sciences, ISBN **0-87322-300-4**. The
>   **year, 1991, comes from the library catalogue record** (Internet Archive /
>   **OCLC 1150972541**) — the book's copyright page was captured in full and
>   carries no copyright notice at all, its verso having been reset for a later
>   printing. No further page will produce it.
>   - **This needs a vocabulary decision from this item.** The chapter's
>     *content* is primary-text attested; its *publication year* rests on a
>     cataloguing authority, which is neither the work's own text nor a
>     "secondary summary" in the sense `SECONDARY_ATTESTATION` was coined for —
>     and is in fact the standard, stronger source for that particular datum.
>     Decide whether `PRIMARY_TEXT` plus a note covers it, or whether a citation
>     may hold different verification levels for content and frame. This is the
>     **second** vocabulary gap this work has surfaced; the other is the
>     conflict-between-primary-sources case from the closed coefficient item.
>   - **Grep for the 1982 title while you are here.** The catalogue record shows
>     the 1991 edition is a revision of *Physiological Testing of the Elite
>     Athlete* (1982). This repo's history records `BANISTER_TRIMP.work` once
>     citing "Physiological Testing of Elite Athletes" — that was the **first
>     edition**, a different book that does not contain this chapter. Any
>     surviving copy of that string points at the wrong volume.

## What

Two specs carry the same named, accepted risk: the TRIMP weighting coefficient
`0.64` and exponent `1.92` could not be verified against a primary text, because
Banister (1991), *Physiological Testing of the High-Performance Athlete*, 2nd
ed. (Human Kinetics) is held by the Internet Archive under controlled digital
lending, and Morton, Fitz-Clarke & Banister (1990), *J Appl Physiol*
69(3):1171-1177, is paywalled with no free mirror found.

**Both texts are now present in the working tree** (untracked, as of
2026-07-27 22:42-22:50):

- `Morton20et20al20Modeling20human20performance20in20running.pdf` (2.0 MB)
- `bannister_physiological_testing_of_the_high_performance_athlete/` — 13
  page screenshots, ~44 MB

That removes the sole justification for every downstream accommodation built
around their unavailability.

## Why it matters

The whole point of `BLOCKED_CITATIONS` and of fit-ingest Req 15.9's
record-what-you-searched rule is that a tracked exception must not become a
cheaper answer than obtaining a text that is in fact reachable. The text is
now reachable. Leaving `BANISTER_TRIMP` at `SECONDARY_ATTESTATION` from here
is the exact failure mode the mechanism was designed to prevent, and the
recorded search prose becomes false the moment it is read next to these files.

There is also a live correctness question waiting on the same reading. The
coefficient string `0.64`/`1.92` was **refuted 0-3 in adversarial verification**
when it was cited only to `docs/reference/fitdocs-ai-reference.md`
(`sources.py` module docstring). Nobody has yet checked the values against the
defining work. Two consequences:

- `load-channels` research found HRSS's ratio form cancels the multiplicative
  `0.64` exactly, so only the `1.92` exponent survives into a computed result —
  the blast radius of a wrong coefficient is narrower than it looks, but a
  wrong **exponent** changes reported numbers.
- fit-ingest Amendment 1's own rationale says the sex-neutral collapse "is a
  different reported number for some athletes". The primary texts are what
  settle whether the shipped constants are the sex-specific or collapsed form.

Unblocking this also retires a schedule risk fit-ingest Amendment 1 names
explicitly, and `.kiro/steering/roadmap.md`'s Phase 4 entry records that both
texts "were searched for and NOT obtained" — that line becomes false too.

## Evidence

Verified on `main` at `4a5c838`:

- `src/fitdocs/load/channels/sources.py:174` —
  `BLOCKED_CITATIONS = frozenset({"banister_trimp"})`.
- `src/fitdocs/load/channels/sources.py:193` — `BANISTER_TRIMP` is the sole
  remaining `VerificationStatus.SECONDARY_ATTESTATION` citation.
- `src/fitdocs/load/channels/sources.py:218` — its note says the definition
  "is out of this feature's scope (see BLOCKED_CITATIONS)".
- `.kiro/specs/load-channels/requirements.md:270-271` — criteria 8.9/8.10,
  the named-exception variant and its record-your-search obligation.
- `.kiro/specs/fit-ingest/spec.json` `amendments[0].design` — "Banister (1991)
  and Morton (1990) remain the named, accepted schedule risk."
- `git status --porcelain` at `4a5c838` — both source files present and
  untracked in the repo root.

## How to pick it up

1. **Move the source files out of the repo before anything else.** They are
   third-party copyrighted texts sitting in the working root of an
   open-source repo; `CLAUDE.md`'s hard rule keeps non-code artifacts out of
   the tree, and neither is gitignored today. Relocate them outside the repo
   (or add an ignore rule) and cite them by title/edition/page in the record,
   never by committing the file.
2. Read the TRIMP weighting definition in both texts. Establish, digit for
   digit: the coefficient, the exponent, and whether the shipped values are
   the sex-specific or sex-collapsed form. Record page and figure/equation
   numbers — `MINETTI_2002`'s "Fig. 1 caption" precedent is the standard here.
3. If the values check out: flip `BANISTER_TRIMP` to `PRIMARY_TEXT` with the
   located citation, and remove `"banister_trimp"` from `BLOCKED_CITATIONS`.
   Leave the frozenset in place and empty — the guard
   `test_no_new_secondary_attestation_citations_exist` and
   `test_blocked_citation_notes_name_both_attempted_sources` are the mechanism
   that keeps a future downgrade from landing silently; deleting them is a
   regression, not a cleanup. Check both tests still discriminate with an
   empty set.
4. If they do **not** check out, that is a shipped-value defect, not a
   citation edit: stop and queue it separately before changing any constant.
   Note `src/fitdocs/load/channels/` currently holds only `sources.py` and
   `__init__.py` — no heart-rate channel consumes these yet, so a correction
   is cheapest now.
5. Reconcile every prose claim that asserts unavailability. Known copies:
   `sources.py`'s module docstring and `BANISTER_TRIMP.note`;
   `load-channels/requirements.md` 8.9/8.10 and its research/design records;
   `fit-ingest/spec.json` `amendments[0]` and `requirements.md` Req 15.4's
   named risk; `.kiro/steering/roadmap.md`'s Phase 4 entry. Grep for
   `banister`, `morton`, `BLOCKED_CITATIONS` and `controlled digital lending`
   — the walking-form claim in the sibling item needed six passes to find all
   its copies.
6. This is a `src/`+`tests/` change: full validation gate per
   `change-protocol.md` (`uv run pytest && uv run ruff check . && uv run ruff
   format --check . && uv run mypy`), on a worktree branch.

## Open questions

- Does fit-ingest's own Amendment 1 sourcing task want to do this reading
  once, in the layer that owns the constants, rather than `load-channels`
  doing it and fit-ingest repeating it? fit-ingest is upstream and its design
  already claims ownership of the citation vocabulary
  (`src/fitdocs/citation.py`); a single reading recorded there and re-exported
  is likely cheaper than two. Decide before starting the write-up.

## Resolution

Closed 2026-07-29, merged to `main` as `6a8ebf6` (branch
`chore/banister-resource-and-note-backstops`, 7 commits, `--ff-only`,
validated after rebase: 2121 passed, all gates clean). Three adversarial
review rounds.

`BANISTER_TRIMP` is now `VerificationStatus.PRIMARY_TEXT` with a real
`locator` (B91 p. 408, corroborated by Morton Eq. 2 p. 1172).
`BLOCKED_CITATIONS` is an **empty `frozenset()` with the mechanism retained**,
as this item required — a reviewer injected a real untracked
`SECONDARY_ATTESTATION` citation and confirmed the guard still reds, so the
empty set has not made it toothless.

**The item understated the problem.** By the time it was picked up, the note
on `main` read *"Re-searched 2026-07-27 and still not obtained"* — a false
factual claim in shipped source, since the texts had been obtained and
extracted to `docs/reference/banister-trimp-primary-sources.md` days earlier.
This was not pending work; it was a live falsehood.

**`PRIMARY_TEXT` was judged the honest status**, independently of the note:
the status asserts only that the value was read from *the cited work's* own
text, the cited work is B91, and Morton's disagreement is a corroboration
failure rather than a defect in the B91 reading. The maintainer's 0.64 ruling
was verified against `roadmap.md:558-564` and commit `ec44cb6`, not taken
from the note.

**Prose reconciled**: `load-channels` requirements 8.9/8.10, design, tasks,
`spec.json`, and `research.md` including its References section.
`.kiro/specs/fit-ingest/requirements.md` was corrected in a deliberately
isolated commit; `fit-ingest/spec.json` was **left untouched** and routed to
the peer session that owns that spec — it still calls the two texts a "named,
accepted schedule risk".

**The lesson, logged for peers**: a whole-value backstop pins *text*, not
*truth*. One sentence took three rounds — round 1 generalized a Banister-only
finding to both texts, round 2 corrected the scope but exonerated Morton
outright (contradicting the extraction doc's own D1a heading), round 3 stated
what D1a says. Each round the machinery got stronger and the prose was wrong
somewhere new.

**Left open deliberately**: the two `VerificationStatus` vocabulary questions
this item said must be answered "here" were answered by shipping rather than
recorded — now tracked as
`.kiro/queue/2026-07-29-verificationstatus-lacks-two-needed-terms.md`.
