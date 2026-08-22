---
id: 2026-07-26-hrss-exact-interop-claim-unsupported
title: The "exact interop match" claim for HR load rests on a citation that publishes no formula
status: done
importance: medium
importance_why: Shipped source asserts numeric equivalence with another product twice, and a test pins the wording, but the sole supporting citation establishes only "same scale" — the interop strategy's central claim is stated more strongly than its evidence.
effort: S
kind: inconsistency
area: load-channels, src/fitdocs/load/channels/sources.py
created: 2026-07-26
surfaced_by: /kiro-queue sweep — citation-verification remediation (queue item 2026-07-26-channel-citations-unverified)
pinned_at: 17ff340
resume_command: "do: reconcile the 'exact interop match' claim in src/fitdocs/load/channels/sources.py (module docstring and the heart_rate_reported_intensity DIVERGENCES reason) with what INTERVALS_ICU_HRSS actually supports — either soften both to the scale claim the source establishes, or cite a source that publishes intervals.icu's HRSS formula [queue: .kiro/queue/2026-07-26-hrss-exact-interop-claim-unsupported.md]"
context:
  - src/fitdocs/load/channels/sources.py
  - tests/load/channels/test_sources.py
  - .kiro/specs/load-channels/design.md
  - .kiro/specs/load-channels/requirements.md
blocked_by: []
---

## What

`src/fitdocs/load/channels/sources.py` asserts, in two places, that fitdocs'
heart-rate load is an **exact interop match** with intervals.icu's HRSS:

- the module docstring: "The heart-rate *load* itself remains an exact interop
  match with intervals.icu; only the reported intensity differs."
- the `DIVERGENCES` entry `heart_rate_reported_intensity`, `reason` field:
  "The heart-rate load value itself remains an exact interop match with
  intervals.icu's HRSS; only the reported intensity differs."

Both rest entirely on the `INTERVALS_ICU_HRSS` citation. That citation was
re-verified on 2026-07-26 against its actual source — the founder's
announcement thread — and the corrected note now records what the text
supports: intervals.icu's HR load is HRSS (normalized TRIMP), scaled so 100
corresponds to one hour at max effort. **Neither post publishes a formula.**

"Same name, same scale" does not establish numeric equivalence. Two
implementations of "normalized TRIMP scaled to 100 = 1h max effort" can differ
in the TRIMP weighting, the smoothing window, the reserve basis, or the
rounding, and still both match that description.

## Why it matters

Interop with intervals.icu is not incidental — `.kiro/steering/roadmap.md`
Phase 4 states it as a constraint: "Where intervals.icu has an established
behavior, match it; every divergence needs a stated reason recorded in the
spec." The `DIVERGENCES` table is the artifact discharging that constraint. An
entry in that table which *overstates* agreement is the same defect class as
one that omits a divergence: it tells a reader the comparison was made to a
precision it was not.

The claim is also **pinned by a test** —
`test_divergences_include_the_three_known_cases` asserts `"exact"` and
`"match"` appear in the combined `fitdocs`/`reason` text — so the wording
cannot drift accidentally, which makes it read as deliberately verified.

Nothing computes from this today; no rendered document carries it. It is a
correctness-of-record issue in the layer whose entire job is provenance, which
is why it is `medium` and not higher.

## Evidence

Verified at `17ff340` in the sweep worktree:

- `INTERVALS_ICU_HRSS` is `VerificationStatus.PRIMARY_TEXT`, year 2020, sourced
  to `forum.intervals.icu/t/hrss-normalized-trimp-training-load/569`. Quote 1
  (post 1, david, 2020-03-21): "You can now choose to estimate training load
  for activities with heart rate data only (no power) using HRSS (normalized
  TRIMP) as used in Elevate". Quote 2 (post 4, david, 2020-03-26): "normalised
  in a similar way to TSS (100 = 1h max effort)."
- Neither quote contains a formula, a coefficient, or a worked example.
- The two "exact interop match" sites are in the module docstring and the
  `heart_rate_reported_intensity` `DIVERGENCES` entry.
- `tests/load/channels/test_sources.py::test_divergences_include_the_three_known_cases`
  asserts on the substrings `"exact"` and `"match"`.
- Contrast the standard the sibling citation already meets:
  `INTERVALS_ICU_PACE_LOAD`'s note is explicit that its source "does not itself
  use the name 'Pace Load' or state the … formulation … so it is recorded as
  secondary corroboration rather than primary confirmation of the full claim."
  The HRSS entry now carries the same caveat in its note while the docstring
  and divergence text above it do not.

## How to pick it up

1. Read `src/fitdocs/load/channels/sources.py` — the `INTERVALS_ICU_HRSS`
   note first (it already states the limit honestly), then the module
   docstring and the `DIVERGENCES` entry that contradict it.
2. Decide which direction to reconcile:
   - **Soften** both sites to what the source supports — that intervals.icu's
     HR load is HRSS on the same 100 = 1h-at-threshold scale, so the two are
     directly comparable, without asserting numeric identity. Cheapest, and
     consistent with the note.
   - **Substantiate** — find a source that publishes intervals.icu's HRSS
     formula (the Elevate project the announcement names is open source and is
     the more promising lead than the forum). If found, the exactness claim can
     stand with a real citation, which is strictly better.
3. Whichever direction: `test_divergences_include_the_three_known_cases`
   asserts on `"exact"`/`"match"` and will need its assertion moved with the
   wording. Do not weaken the test to a substring that no longer discriminates
   — assert the new claim, not fewer characters of the old one.
4. Done means: no statement in `sources.py` claims a precision its citation
   does not support, and the docstring, the divergence reason and the citation
   note all say the same thing.

## Open questions

- Does `load-channels` have a requirement asserting numeric equivalence with
  intervals.icu for the HR channel specifically? If so it needs the same
  treatment, and this becomes a requirements correction rather than a prose
  fix. Worth grepping `requirements.md` for "exact" before choosing.


## Resolution

**Done 2026-07-26** — `23c45a8`, branch `chore/queue-top-ten`.

Both sites softened to the claim `INTERVALS_ICU_HRSS` actually supports -- the
shared HRSS scale (normalized TRIMP, 100 = one hour at max effort), so the two
are directly comparable -- with the reason for the limit stated inline. The
citation note is updated too: it used to flag the contradiction as live, which
it no longer is. `load-channels/tasks.md` carried the same wording as an
instruction and now carries a do-not-restore note.

Per the item's instruction the pinning test was **moved to the new claim, not
weakened**: it pins the scale wording, the "comparable" wording and the explicit
disclaimer, plus a negative assertion that "exact interop match" is absent, so
the overclaim cannot return silently. All three directions verified by mutation,
each a sole failure.

Open question resolved: nothing in `load-channels/requirements.md` asserts
numeric equivalence with intervals.icu (grepped for "exact"), so this is a prose
correction rather than a requirements change.
