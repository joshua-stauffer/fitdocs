---
id: 2026-07-27-coggan-2003-sources-three-amendment-1-constants
title: The located Coggan 2003 manuscript is primary text for three of Amendment 1's constants, and fit-ingest does not know it
status: open
importance: high
importance_why: fit-ingest Amendment 1 requires every metrics constant classified against a primary work, and three of the seven items were open for want of exactly this source. It has now been located, fetched and verified — leaving it recorded only in load-channels means fit-ingest re-does the search or ships the constants unclassified.
effort: S
kind: gap
area: fit-ingest, .kiro/specs/fit-ingest/requirements.md
created: 2026-07-27
surfaced_by: adversarial review of chore/citation-vocabulary-unify (queue sweep 2026-07-27)
pinned_at: 189ea70
resume_command: "do: classify the TSS scale (100), the normalized-power rolling-window width (30 s) and the normalized-power averaging exponent (4) against Coggan 2003 in fit-ingest's Amendment 1 record — the manuscript is at https://www.ipmultisport.com/ref_lib/Coggan_Power_Meter.pdf, section 3, printed pages 8-11, and its PDF metadata authenticates it (Author: Andrew Coggan, Subject: IF/TSS, CreationDate 2003-06-06); note the NP averaging exponent is still an inline literal at metrics/power.py:126-127 with no named constant [queue: .kiro/queue/2026-07-27-coggan-2003-sources-three-amendment-1-constants.md]"
context:
  - .kiro/specs/fit-ingest/requirements.md
  - .kiro/specs/fit-ingest/design.md
  - src/fitdocs/metrics/power.py
  - src/fitdocs/metrics/stress.py
  - src/fitdocs/load/channels/sources.py
blocked_by: []
---

## What

fit-ingest Amendment 1 requires each of criterion 15.6's enumerated constants
to be classified against the published work that defines it. Three of them are
defined by a source that was, until 2026-07-27, believed unobtained:

- the training-stress-score scale (`_TSS_SCALE = 100.0`)
- the normalized-power rolling-window width (`_NP_ROLLING_WINDOW_S = 30`)
- the normalized-power averaging exponent (the `**4` / `**0.25` pair)

That source has now been located, fetched and read end to end during the
`chore/citation-vocabulary-unify` review: Andrew Coggan's 2003 chapter-length
manuscript, which states the full NP → IF → TSS algorithm directly.

The finding currently lives only in `src/fitdocs/load/channels/sources.py`'s
`COGGAN_TSS` record. fit-ingest — the spec that actually owes the
classification — has no record of it.

## Why it matters

Amendment 1's whole purpose is that no metrics constant ships without a
recorded provenance verdict. These three were open for want of a primary text.
The text exists, is freely available, and has been verified against the code
constant by constant.

Left as is, the next session working Amendment 1 either repeats the search that
already succeeded, or classifies the three constants as unsourced and ships
them under a weaker status than the evidence supports — which is precisely the
"cheap escape hatch" the amendment's own design review warned about.

## Evidence

Gathered by the adversarial reviewer of `chore/citation-vocabulary-unify`
(2026-07-27), which fetched the source rather than trusting the citation:

- `https://www.ipmultisport.com/ref_lib/Coggan_Power_Meter.pdf` — HTTP 200,
  22 pages.
- PDF metadata authenticates authorship independently of the hosting site:
  `Author: Andrew Coggan`, `Title: Chapter for USAC coach's manual`,
  `Subject: IF/TSS`, `CreationDate: 2003-06-06`; body reads
  "Revised: 25 March 2003".
- Locator: section 3 "Analysis of power meter data" → "Intensity factor (IF)
  and training stress score (TSS)", printed pages 8-11. Steps 1-8 appear in
  full.
- Constant-by-constant agreement with the shipped code was verified: TSS scale
  100, window 30 s, 4th power and 4th root, IF as NP over threshold power, and
  the complete TSS expression all match.
- Its reference (4) is "Banister EW, Calvert TW, Savage MV, Bach TM… 1975",
  which confirms this manuscript is distinct from the still-blocked
  `BANISTER_TRIMP` 1991 chapter.

One caveat carried over: the same review found the code's rolling average
**starts at t=0 with partial windows** rather than at 30 s as step 1 specifies.
That is tracked separately in
`.kiro/queue/2026-07-27-np-rolling-window-starts-at-zero.md` and should be read
alongside this item — the window width is sourced, its start condition is not
implemented as sourced.

## How to pick it up

1. Read `.kiro/specs/fit-ingest/requirements.md` criterion 15.6 and the
   classification table in `design.md` to see how the other constants are
   recorded, then follow the same shape.
2. Fetch the PDF yourself and confirm the locator before writing the
   classification — this item is a pointer, not a substitute for reading it.
3. Note that the NP averaging exponent is still a bare inline literal at
   `src/fitdocs/metrics/power.py:126-127` (`sum(value**4 …)` and
   `fourth_power_mean**0.25`) with no named constant, unlike the other two.
   Decide whether classifying it also warrants naming it.
4. Check whether `src/fitdocs/metrics/stress.py:55-59`'s bare
   "(reference section 2)" justification for the TRIMP coefficients should be
   repointed at the same time — it currently cites nothing resolvable.

Done looks like: three fewer unclassified constants in Amendment 1's record,
each with the locator a reader can check.
