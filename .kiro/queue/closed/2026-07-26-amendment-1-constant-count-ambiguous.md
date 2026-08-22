---
id: 2026-07-26-amendment-1-constant-count-ambiguous
title: Amendment 1's "seven constants" count does not match criterion 15.6's enumeration
status: done
importance: low
importance_why: The enumeration governs and the design classifies all of it, so nothing ships wrong — but the narrative count is the number a reader checks completeness against, and it is off by one against the criterion it summarizes.
effort: S
kind: inconsistency
area: fit-ingest, .kiro/specs/fit-ingest/requirements.md
created: 2026-07-26
surfaced_by: /kiro-spec-design fit-ingest -y (Amendment 1 design regeneration)
pinned_at: c7eaa2e
resume_command: "do: reconcile Amendment 1's 'seven constants' narrative count with criterion 15.6's enumeration in .kiro/specs/fit-ingest/requirements.md — either state that the training-impulse coefficient and exponent count as one item, or correct the count to eight; whichever, make the revision table at requirements.md:97-101 and the spec.json amendment record agree with it [queue: .kiro/queue/2026-07-26-amendment-1-constant-count-ambiguous.md]"
context:
  - .kiro/specs/fit-ingest/requirements.md
  - .kiro/specs/fit-ingest/spec.json
  - .kiro/specs/fit-ingest/design.md
blocked_by: []
---

## What

Amendment 1's narrative says Requirement 15.6 "named seven constants" and that
"three of the seven are defined by no published work at all". Criterion 15.6
itself enumerates eight named values:

1. the training-impulse weighting coefficient
2. the training-impulse weighting exponent
3. the training-stress-score scale
4. the normalized-power rolling-window width
5. the normalized-power averaging exponent
6. the minimum power-stream span below which normalized power is not reported
7. the moving-time movement threshold
8. the altitude-smoothing window width

The count reconciles to seven only under one reading — that items 1 and 2 count
as a single item, "the weighting". That reading is never stated. A second,
incompatible route to seven also exists: the amendment's own **Measured
surface** list (`spec.json` `amendments[0].requirement`... `also`) counts the
coefficient and exponent separately but omits the averaging exponent entirely,
which criterion 15.6 includes.

So two different countings each produce "seven", and they disagree about which
value is the odd one out.

## Why it matters

Nothing computes from the count and no shipped behavior depends on it: the
criterion's enumeration is the requirement and the design classifies all eight
named values, so the amendment is satisfiable either way. The cost is to
completeness checking. A reviewer asked "is every constant classified?" counts
the records against the number in the prose; a mismatch either raises a false
alarm or, worse, conceals a genuinely missing record because the reviewer
stopped at seven.

The averaging exponent is the value most exposed. It is the only one of the
eight that is not a named constant today (`metrics/power.py` computes
`value**4` and `**0.25` inline) *and* the only one absent from the amendment's
measured-surface list, so it is the one a count-based check would drop.

## Evidence

Verified at `c7eaa2e`:

- `.kiro/specs/fit-ingest/requirements.md:372` — criterion 15.6, eight named
  values in one sentence.
- `.kiro/specs/fit-ingest/requirements.md:95` — "three of the seven are
  defined by no published work at all".
- `.kiro/specs/fit-ingest/requirements.md:97-101` — the revision table, three
  rows: moving-time threshold, minimum power-stream span, altitude-smoothing
  window.
- `.kiro/specs/fit-ingest/spec.json` `amendments[0].requirement` — the measured
  surface: `_TRIMP_COEFFICIENT`, `_TRIMP_EXPONENT`, `_TSS_SCALE`,
  `_NP_MIN_SPAN_S`, `_NP_ROLLING_WINDOW_S`, `_ALTITUDE_SMOOTHING_WINDOW`, and
  the moving-time threshold = seven, with no averaging exponent.
- `src/fitdocs/metrics/power.py:126-127` — the averaging exponent as inline
  literals, confirming it is not among the named constants the measured-surface
  list enumerated.
- `.kiro/specs/fit-ingest/design.md` (MetricsSources component) — the design
  classifies all eight and records this discrepancy rather than resolving it.

## How to pick it up

1. Read criterion 15.6 in `requirements.md` and the Revision section above it
   (lines 90-123). Decide which reading is intended: the weighting is one item
   (count stays seven), or it is two (count becomes eight).
2. Whichever is chosen, make three places agree: the narrative count in the
   Amendment 1 and Revision sections, the revision table's framing of "three of
   the N", and `spec.json`'s `amendments[0]` prose. Criterion 15.6's
   enumeration itself is correct and must not change — the design and the
   guard tests are written against it.
3. Do **not** renumber or withdraw any criterion; Amendment 1 states, and
   `spec.json` records, that nothing is renumbered.
4. Done means: a reader counting records against the prose gets the same
   number, and the averaging exponent is unambiguously inside the covered set
   under whichever counting is chosen.

## Open questions

- Is the averaging exponent's absence from the measured-surface list an
  oversight, or was it added to 15.6 deliberately during requirements drafting
  after the surface was measured? The answer decides whether `spec.json`'s
  measured-surface prose is corrected or simply annotated as pre-dating the
  criterion.

## Resolution (2026-07-27) -- PROPOSED, awaiting maintainer confirmation

This session's close was reversed: per `.claude/skills/kiro-queue/SKILL.md:157`,
"Never auto-close. Closing is the human's call; this skill proposes." What
follows is the session's finding, proposed as done -- not a ratified close.
A later reviewer independently re-derived the count and confirmed "7
items / 8 constants" as correct, corroborated by criterion 15.2's own "a term
of Banister's training-impulse weighting" (plural terms, one weighting). The
open maintainer question below is separate from, and not resolved by, that
confirmation.

**Reading chosen: option one.** Criterion 15.6's enumeration is unchanged and
reads, comma-delimited, as seven list items — the first item, "the
training-impulse weighting coefficient and exponent", names two constants
under a single item. Seven items, eight named constants. This is also what
`design.md`'s own MetricsSources note had already concluded ("reconciles only
if the weighting coefficient and exponent count as one item") without stating
it as settled.

All three places now read seven items / eight constants explicitly:

- `requirements.md:92-97` (the Revision narrative, immediately above the
  revision table at 99-103): now reads "Requirement 15.6 enumerates seven
  items — the training-impulse weighting counts as one item though it names
  two constants, the coefficient and the exponent, so the enumeration covers
  eight named constants in all" and "three of the seven **items** are defined
  by no published work at all" (was "three of the seven").
- `spec.json` `amendments[0].revision`: the identical clarification applied to
  the matching sentence ("Req 15.6 enumerates seven items ... so the
  enumeration covers eight named constants in all ... three of the seven
  items are defined by no published work at all").
- `spec.json` `amendments[0].design`: the note that used to say "criterion
  15.6 enumerates EIGHT values while the amendment narrative calls them seven"
  now states the same seven-items/eight-constants reading and points at this
  closed item instead of the open one.

The second, incompatible route to seven (this item's Evidence, `spec.json`
`amendments[0].reason`'s measured-surface list) is also fixed: the NP
averaging exponent — the constant most exposed, per Why it matters above — is
now named in that list (it is still an inline literal in `power.py`, not a
named constant), so the list no longer silently omits one of the eight and no
longer produces a seven-by-omission that disagrees with the seven-by-item-
grouping reading used everywhere else.

That fix was made by editing `amendments[0].reason`'s text in place, which is
itself a departure from how this record otherwise treats `amendments[*]`
entries — as dated records of what was measured or ruled at the time, left
verbatim, with later corrections appended as new notes rather than rewritten
into the original. See "For the maintainer" below: this in-place edit is the
one open question this resolution does not get to answer on its own.

`design.md`'s MetricsSources note (`Responsibilities & Constraints`, near the
eight-row classification table) is updated to state the reconciliation and
point at this file, noting the resolution is proposed and awaiting the
maintainer's confirmation — it is documentation of the same fact, not one of
the three places the queue item required to agree.

Criterion 15.6's enumeration itself was not touched, per the item's own
instruction (`How to pick it up` step 2) — no criterion is renumbered or
withdrawn, matching what Amendment 1 and `spec.json` already state.

## Closed (2026-07-27, maintainer confirmed)

The maintainer confirmed the proposed resolution and the one open question
below, closing this item. Reading (B) — that "seven" meant seven *measured*
constants — **is** foreclosed correctly: the averaging exponent's absence from
`amendments[0].reason`'s measured-surface list was an oversight, and editing
the list in place to add it is the right correction.

Re-verified on `main` at `4a5c838` before closing, rather than trusting the
proposal text:

- `requirements.md:92-97` — the Revision narrative reads "Requirement 15.6
  enumerates seven items — the training-impulse weighting counts as one item
  though it names two constants … so the enumeration covers eight named
  constants in all", and `:97` reads "three of the seven **items**".
- `spec.json` `amendments[0].revision` — the identical clarification present.
- `spec.json` `amendments[0].reason` — the measured-surface list now names
  "the NP averaging exponent (power.py, inline \*\*4 / \*\*0.25, not a named
  constant)", so it enumerates all eight and no longer yields a
  seven-by-omission that disagrees with the seven-by-item-grouping reading.
- `spec.json:22` `phase_note` and `design.md:960` — both state the same
  seven-items / eight-constants reading.
- Criterion 15.6's own enumeration is untouched; nothing renumbered or
  withdrawn.

All three places a reader would count against now agree, and the averaging
exponent is unambiguously inside the covered set. The in-place edit to
`amendments[0].reason` stands as the documented exception to the
"amendments\[\*\] entries are left verbatim" convention, which `spec.json:22`
already records as such.

## For the maintainer (RESOLVED — see "Closed" above)

The original "Open questions" entry above asked whether the averaging
exponent's absence from `amendments[0].reason`'s measured-surface list was an
oversight, or deliberate. This session's fix answered that by editing the
list in place to add the exponent — which forecloses, rather than decides,
a second reading raised in this item's Evidence: that "seven" in Amendment
1's narrative meant seven **measured** constants, counted independently of
criterion 15.6's item-grouping. Under that reading, the pre-edit list (which
already counted the TRIMP coefficient and exponent as two separate entries)
omitting the averaging exponent would not be an omission at all — it would
be the second, internally consistent seven.

The question for the maintainer: is that second reading (B) foreclosed
correctly? The edit already made assumes the exponent's absence was an
oversight and corrects it as one; nothing in the amendment record states 15.6
was drafted to deliberately exclude a value the measurement pass had already
decided to scope out. If the maintainer confirms the same conclusion, this
item can be re-closed as done. If not, `amendments[0].reason`'s edit needs to
be reconsidered — a decision this session does not have standing to make on
its own, per `.kiro/queue/README.md:61-62`.
