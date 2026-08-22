---
id: 2026-07-28-load-channel-citation-notes-unpinned
title: The load layer's six citation notes are asserted only non-empty, so any claim in them can be falsified with the suite green
status: done
importance: medium
importance_why: These notes carry the same kind of content fit-ingest task 9.1 spent four review rounds hardening — quoted formulas, page attributions, statements about what a primary text does and does not contain — and they are guarded by `assert note is not None` and `note.strip() != ""`. Every factual claim in all six is freely invertible with the suite green. The defect class is confirmed, not hypothetical: an independent reviewer found 21 such falsifications in fit-ingest's three notes before the whole-note backstop closed them.
effort: M
kind: gap
area: load-channels, src/fitdocs/load/channels/sources.py, tests/load/channels/test_sources.py
created: 2026-07-28
surfaced_by: /kiro-impl fit-ingest (task 9.1 review round 4 — reviewer FOLLOW_UPS, while auditing the sibling layer)
pinned_at: 8e72bfc
resume_command: "/kiro-impl load-channels [queue: .kiro/queue/2026-07-28-load-channel-citation-notes-unpinned.md] Add whole-note equality backstops to the six load-layer citation records"
context:
  - src/fitdocs/load/channels/sources.py
  - tests/load/channels/test_sources.py
  - tests/metrics/test_sources.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

`fitdocs.load.channels.sources` holds six `Citation` records whose `note=` fields
carry substantive provenance claims — including `BANISTER_TRIMP`'s statement
that its coefficient string "was refuted 0-3 in adversarial verification", and
`COGGAN_TSS`'s multi-sentence account of which manuscript was obtained, where,
and what it states about the NP algorithm.

`tests/load/channels/test_sources.py` asserts of those notes only that they are
not `None` and not empty after stripping (around lines 97-98 and 160-161).
Nothing checks what any of them says. Every claim in all six can be inverted,
falsified, or replaced with the whole suite green.

## Why it matters

This is the same defect class fit-ingest task 9.1 was rejected for four times,
now confirmed one layer down.

The cost is specific to provenance records: a citation note is read as fact by
anyone deciding whether a constant is trustworthy, and it describes texts that
are paywalled, out of print, or otherwise expensive to re-check. A false claim
in one is not caught by a reader — that is precisely why it needs a mechanical
guard. `COGGAN_TSS`'s note is *load-bearing across specs*: fit-ingest's own
`COGGAN_2003` record reuses its identification rather than re-deriving it, so a
falsification here propagates upward silently.

Note the fix is cheap relative to the risk, and the pattern is already written:
`tests/metrics/test_sources.py` on `impl/fit-ingest` now carries whole-note
equality backstops for exactly this reason.

## Evidence

At `8e72bfc`:

- `tests/load/channels/test_sources.py:97-98` — `assert BANISTER_TRIMP.note is not None` and `assert BANISTER_TRIMP.note.strip() != ""`
- `tests/load/channels/test_sources.py:160-161` — the same pair in the loop over
  every record carrying a note
- `grep -c` over that file for any assertion on note *content*: none

The confirmed severity comes from the sibling layer. In fit-ingest's three
notes, an independent reviewer designed 56 mutations and found **21
falsifications shipping green** even after an exhaustive per-clause inventory
had pinned 29 claims — including quoted formulas altered, page attributions
moved, and an `OMITS`/`AGREES` corroboration classification swapped. Two
sub-species are worth carrying over:

1. **Substring assertions on numbers are blind upward.** `assert "multiply by
   100" in note` **passes** when the note reads "multiply by 1000", because the
   true token is a prefix of the false one. `100 → 95` reds, so the assertion
   looks discriminating while missing an order-of-magnitude error.
2. **Per-clause inventories do not terminate.** A clause-granular sweep found 29
   claims; independent enumeration of the same text found 43. The falsifiable
   surface is every quoted substring, which is a finer grain than any clause
   list.

## How to pick it up

1. Read `tests/metrics/test_sources.py` on `impl/fit-ingest` (or `main` once
   merged) for the established pattern: one whole-note equality assertion per
   record, with targeted per-claim assertions kept underneath as diagnostics so
   a failure says *which* claim moved.
2. Add one such backstop per record in `tests/load/channels/test_sources.py`.
   Prefer literal equality over a digest: when a hash reds, the natural response
   is to regenerate it; when an equality reds, the text diff is visible in the
   failure output and in the next code review, which is the whole point.
3. Do **not** attempt to pin the notes clause by clause. That strategy is known
   not to terminate on this content — see the evidence above.
4. Done looks like: altering any single character of any of the six notes reds a
   named assertion. Verify by mutation per `.kiro/steering/change-protocol.md`
   — pick three notes, falsify one claim in each (invert a relation, move a page
   number, change a quoted formula), and confirm each reds.
5. While there, check whether `BANISTER_TRIMP`'s note is still accurate at all.
   It states the primary text was unobtainable, and that is no longer true —
   both texts were obtained 2026-07-27 and read in full. That is tracked
   separately at `2026-07-27-banister-morton-primary-texts-obtained.md`, but a
   backstop pinned to a stale note would freeze the staleness in place, so
   sequence the two.

## Open questions

Whether the backstop belongs in `load-channels`' own test module or in a shared
helper both layers use — fit-ingest and load-channels now hold structurally
identical citation records, and a single parametrized "every `Citation` in the
tree has a whole-note pin" guard would cover future records automatically
instead of relying on each author remembering. That is the more durable shape
but it crosses a spec boundary, so it wants a maintainer call.

## Resolution

Closed 2026-07-29, merged to `main` as `6a8ebf6` (branch
`chore/banister-resource-and-note-backstops`, `--ff-only`, validated after
rebase: 2121 passed, all gates clean). Done together with
`.kiro/queue/closed/2026-07-27-banister-morton-primary-texts-obtained.md`,
whose false shipped note was a live instance of exactly this gap.

All six citation notes now carry whole-value equality backstops against
literal `BACKSTOP_*` constants — literals, never derived from the module at
import time, or the pin would be self-satisfying. The suite grew from 2097 to
2121.

**Verified as genuine equality, not a substring or length check.** The
reviewer inverted a factual claim with *no change in length and no digits
touched* (`agree`↔`disagree` in "the two texts agree exactly on both
exponents and disagree on whether a leading coefficient exists") and got sole
failure. Further length-preserving inversions on the final text — `"does not
satisfy"`→`"does yet satisfy"`, `"not a test vector"`→`"and a test vector"`,
`"are unstated"`→`"are stated"` (whitespace-padded to identical length) —
each red with sole failure.

**A second defect was found and fixed**: the test written to prove the
`BLOCKED_CITATIONS` mechanism still worked was itself vacuous — it copied the
guard's filter rather than invoking it, so neutering the real guard left the
suite green. It now monkeypatches `CITATIONS` and calls the guard inside
`pytest.raises`; both named neuterings (dropping the `in BLOCKED_CITATIONS`
check, short-circuiting the loop) were run by the reviewer and both red.

**Known residual, now tracked**: the `Citation.locator` fields beside these
notes carry the same class of evidence claim and are guarded only by `is not
None`. Only `BANISTER_TRIMP`'s is pinned. MINETTI's `Fig. 1 caption (p. 1041)`
and COGGAN's `2003 edition` were both falsified with 2098 passing — see
`.kiro/queue/2026-07-29-citation-locators-unpinned-and-undeclared.md` (high).
