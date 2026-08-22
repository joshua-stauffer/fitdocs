---
id: 2026-07-27-np-rolling-window-starts-at-zero
title: Normalized power's rolling average starts at t=0 with partial windows, not at 30 s as its now-cited primary source specifies
status: done
importance: high
importance_why: This is shipped code producing a wrong number in rendered documents, not a latent risk. Measured -6.7% on NP and about -13% on TSS for a 2-minute effort from a standing start. The divergence is recorded nowhere, and the citation newly added to the repo now documents an algorithm the code does not implement.
effort: M
kind: bug
area: fit-ingest, src/fitdocs/metrics/power.py, src/fitdocs/metrics/stress.py
created: 2026-07-27
surfaced_by: adversarial review of chore/citation-vocabulary-unify (queue sweep 2026-07-27)
pinned_at: 189ea70
resume_command: "do: decide whether _trailing_rolling_mean's partial-window start is a deliberate divergence from Coggan 2003 step 1 ('starting at 30 s, calculate a 30 second rolling average') or a defect — if deliberate it needs a DIVERGENCES record and a note on the citation; if a defect, NP must not be reported for streams shorter than the window, which is the same refuse-to-report shape fit-ingest already uses elsewhere [queue: .kiro/queue/2026-07-27-np-rolling-window-starts-at-zero.md]"
context:
  - src/fitdocs/metrics/power.py
  - src/fitdocs/metrics/stress.py
  - src/fitdocs/load/channels/sources.py
  - .kiro/specs/fit-ingest/requirements.md
blocked_by: []
---

## What

`src/fitdocs/metrics/power.py:87-101` (`_trailing_rolling_mean`) computes the
30-second rolling average with **partial (shorter) windows from i=0**, which its
docstring states explicitly: "a partial (shorter) window at the very start
rather than dropping those seconds".

Andrew Coggan's 2003 manuscript — now cited in-repo as `COGGAN_TSS`'s
`PRIMARY_TEXT`, and verified verbatim during the 2026-07-27 review — specifies
in step 1: "**starting at 30 s**, calculate a 30 second rolling average".

So the first 29 samples are averaged over progressively shorter windows instead
of being excluded. Because the fourth-power step weights the smallest values
least, a low-power standing start pulls normalized power down rather than being
dropped.

## Why it matters

This is shipped code writing a wrong number into rendered documents today, and
it is the class the project ranks above everything else.

Measured during the review:

- 2-minute effort from a standing start: fitdocs NP **402.1 W**, Coggan step 1
  **430.9 W** — **-6.7%**. TSS scales with NP squared, so roughly **-13%** on the
  reported score.
- 1-hour ride: **-0.16%** — negligible.

The error is therefore worst exactly where short, hard efforts are recorded, and
invisible on long rides, which is how it has survived.

Compounding it: the repo now carries a `PRIMARY_TEXT` citation whose own quoted
text describes an algorithm the code does not implement, and no
`DIVERGENCES` entry records the gap. That is worse than the unverified citation
it replaced, because it reads as confirmation.

## Evidence

Gathered by the adversarial reviewer of `chore/citation-vocabulary-unify`
(2026-07-27), which fetched and read the primary source:

- Source: `https://www.ipmultisport.com/ref_lib/Coggan_Power_Meter.pdf`, HTTP 200,
  22 pages. PDF metadata authenticates it — `Author: Andrew Coggan`,
  `Title: Chapter for USAC coach's manual`, `Subject: IF/TSS`,
  `CreationDate: 2003-06-06`. Step 1 is on printed page 10.
- Code: `src/fitdocs/metrics/power.py:87-101`.
- Every other Coggan constant was checked and MATCHES: TSS scale 100
  (`_TSS_SCALE`), window 30 s (`_NP_ROLLING_WINDOW_S`), 4th power / 4th root,
  IF as NP over threshold power, and the full TSS expression. This one quantity
  is the sole mismatch.

## How to pick it up

1. Read `src/fitdocs/metrics/power.py:87-101` and its docstring — the partial
   window is deliberate and documented, so the first question is whether it was
   a considered divergence or an unexamined convenience. Check git history for
   the reasoning.
2. Reproduce the measurement before changing anything: a synthetic 2-minute
   power stream from a standing start, computed both ways.
3. If it is a defect, the fix is not simply to drop the first 29 samples —
   decide what NP means for a stream shorter than the window. fit-ingest already
   has a refuse-to-report shape for exactly this (the minimum power-stream span
   below which normalized power is not reported, one of Req 15.6's enumerated
   constants); reuse it rather than inventing a second rule.
4. If it is deliberate, it needs a `DIVERGENCES` record in
   `src/fitdocs/load/channels/sources.py` and a note on `COGGAN_TSS` saying the
   implementation departs from step 1, so the citation stops implying agreement.

Either way this changes already-rendered documents, so it carries
migration-by-regen cost that grows with every document written in the meantime.

Related: `.kiro/queue/2026-07-27-coggan-2003-sources-three-amendment-1-constants.md`
records that the same newly-located manuscript is primary text for three of the
constants fit-ingest Amendment 1 must classify.

## Resolution

**Status: done. Closed 2026-07-30** by the maintainer, on evidence gathered in
this session and verified against `main` at `5a92bd5`.

Resolved as a **defect**, not a deliberate divergence — the second of the two
paths this item's `resume_command` laid out. `_trailing_rolling_mean` now emits
only complete windows and refuses to report below one full window, which is the
"refuse-to-report" shape the item itself proposed.

### What landed

- `142da42` — *feat(fit-ingest): emit only complete rolling windows in
  normalized power (task 13.1)*
- `31576b0` — *fix(fit-ingest): correct the NP minimum-span rationale that task
  13.1 falsified*
- `68be52c` — Amendment 1 complete (47/47 tasks), merged to `main`

### Verification

Code, at `src/fitdocs/metrics/power.py:153-172` (the item pinned the defect at
`:87-101`, before the rewrite):

```python
if len(values) < window:
    return []
running = sum(values[:window])
result: list[float] = [running / window]
```

Behaviour, run against `main`:

```
$ uv run python -c "... power._trailing_rolling_mean(...) ..."
len(out) = 6            # 35 samples, window 30 -- partial windows would give 35
first value = 14.5      # mean of samples 0..29, i.e. the first COMPLETE window
short input (29 pts) -> []
NP_ROLLING_WINDOW_S = 30
```

Six values rather than thirty-five, the first being the mean of samples 0–29,
and an input shorter than one window returning `[]`. The partial-window start
the item reported is gone.

### Corroboration

The reading was reached independently three times before this close: by the
`/kiro-queue` ranking pass, by the implementer on
`spec/fit-ingest-np-window-criterion`, and by that branch's reviewer, which
derived the movement condition from `power.py` and validated it with a
randomized differential check over 4000 series (`iff violations: 0`,
`direction violations: 0`).

The change was value-moving and received the full migration: `DOC_VERSION`
advanced 3 → 4, every committed golden regenerated, and a real-data pass over
77 `.fit` files (54 yielding an NP) measured a median move of +0.48 W (+0.17%),
max +1.01 W (+0.42%), with 53 rising and 1 falling.

### What this close does NOT cover

The item's own worry — that the behaviour was held in place by prose rather
than by a criterion — was real and outlived the fix. Tracked separately, and
resolved on `spec/fit-ingest-np-window-criterion` (unmerged at the time of
writing):

- `.kiro/queue/closed/2026-07-28-np-window-start-has-no-criterion.md` —
  criterion 8.9 now requires the complete-window start condition, so a revert
  to the partial-window form fails a requirement rather than only a test.
- `.kiro/queue/closed/2026-07-30-np-direction-claim-is-conditional.md` — the
  single falling file above disproves the unconditional "raises NP" claim that
  had propagated into five separate documents.
