# Banister TRIMP — extracted from the primary texts

Everything fitdocs needs from the two works that define the training impulse and
the fitness–fatigue model, read from the primary texts on 2026-07-27:

- **[B91]** Banister, E.W. "Modeling Elite Athletic Performance", chapter 9,
  pp. 403–424, in MacDougall, J.D., Wenger, H.A. & Green, H.J. (eds.),
  *Physiological Testing of the High-Performance Athlete*, **second edition**,
  **1991**, published for the Canadian Association of Sport Sciences. Human
  Kinetics Books, Champaign, Illinois. ISBN 0-87322-300-4; OCLC 1150972541.
  x, 432 pp. A revised edition of *Physiological Testing of the Elite Athlete*
  (1982). Cover, title page and copyright page read 2026-07-27; the copy scanned
  is a later printing (printing line "10 9 8 7 6 5"). **The year comes from the
  library catalogue record, not from the book's own pages** — see
  [§8](#8-what-the-scans-do-and-do-not-attest).
- **[M90]** Morton, R.H., Fitz-Clarke, J.R. & Banister, E.W. "Modeling human
  performance in running". *Journal of Applied Physiology* 69(3): 1171–1177,
  1990. Received 17 Feb 1989; accepted in final form 30 Apr 1990. School of
  Kinesiology, Simon Fraser University, Burnaby BC.

Both were previously recorded as unobtainable — B91 behind Internet Archive
controlled digital lending, M90 behind the APS paywall — which is why
`BANISTER_TRIMP` in `src/fitdocs/load/channels/sources.py` ships as
`SECONDARY_ATTESTATION` and is named in `BLOCKED_CITATIONS`. The maintainer
supplied both on 2026-07-27. **That blocking premise is now false**; see
[§7](#7-what-this-changes-for-fitdocs) for what it unblocks.

> **Licensing.** Neither source text is redistributable, and neither lives in
> this repo. B91 was read from page scans and M90 from a publisher PDF, both
> gitignored at the repo root alongside the source workbooks (see `.gitignore`).
> This document records **formulas, constants and measured values** — facts, not
> expression — with quotation held to the short attributed phrases needed to
> prove the sourcing. That distinction matters because `docs/reference/` is
> shipped verbatim in the sdist (queue
> `2026-07-27-sdist-redistributes-withdrawn-methodology-tables`), so anything
> written here is published if an sdist is.

## 1. The training impulse, as B91 states it

B91's TRIMP is developed in "The Unit of Quantitation: The Training Impulse"
(p. 406) and completed on pp. 407–408.

**Scope.** The training impulse is specified from training time and HR data
"during activities when HR reaches steady state" (p. 406). A session whose HR
varies substantially is split into subperiods, each scored separately, and the
subperiod scores summed to a session total (pp. 406, 409). Duration is in
**minutes**; the result is in **arbitrary units** (p. 407).

**Unweighted form** (p. 407):

```
delta HR exercise ratio  =  ΔHR_ex / span HR
span HR                  =  HR_max − HR_rest
ΔHR_ex                   =  HR_ex − HR_rest

training impulse         =  T (min) × ΔHR ratio          [dimensionless ratio]
```

**Weighted form** (p. 408). The ratio is weighted by a multiplying factor `y`
"based on the classically described increase in blood lactate in trained male
and female subjects", so that long low-HR work is not scored disproportionately
against short intense work:

```
y = 0.64 · e^(1.92x)     (male)
y = 0.86 · e^(1.67x)     (female)

w(t) = training impulse = T × ΔHR ratio × y
```

where `x` is the delta HR ratio during exercise. Figure 9.4 plots both curves
over a fraction-elevation axis of 0 → 1.0 with `y` reaching ~6.0; the female
curve lies above the male curve across that range.

B91 defines `e` as "the Napierian logarithm having a value of **2.712**"
(p. 408) — a misstatement of 2.71828…; see [D3](#d3-b91-misstates-e).

**Operational notes.** HR_max and HR_rest, once measured, "remain relatively
constant and need be reassessed only every month" (p. 408). Figure 9.7's sample
athlete log records HR_max 192 and HR_rest 55 as the per-subject constants
carried alongside daily duration and average HR.

## 2. The training impulse, as M90 states it

M90 gives the same construction in explicit equation form (p. 1172), as a
pseudointegral summed over segments of relatively constant HR:

```
w(t) = (duration of exercise) · (HR_ex − HR_rest)/(HR_max − HR_rest)

  (1)  w(t) = D · (ΔHR ratio)
  (2)  Y    = e^(bx)                      x = ΔHR ratio
  (3)  w(t) = D · (ΔHR ratio) · Y
```

with **b = 1.92 for men and 1.67 for women** — and **no multiplicative
coefficient** on `Y`. See [D1](#d1-the-multiplicative-coefficient).

M90 supplies three things B91 does not:

- **Provenance of b.** The values were "chosen to match the shape of the
  increment curve in blood lactate concentration (in mM) with increasing work
  rate and heart rate in men and women" as reported by Green, Hughson, Orr &
  Ranney, "Anaerobic threshold, blood lactate and muscle metabolites in
  progressive exercise", *J Appl Physiol* 54: 1032–1038, 1983 (M90 ref. 6).
  The chain of custody for 1.92/1.67 therefore terminates in Green et al. 1983,
  not in either Banister text.
- **Expected range of x.** The ΔHR ratio ranges "~0.2–1.0" for a low or a high
  raw heart rate respectively (p. 1172).
- **Sampling.** HR was recorded every **15 s** from a chest transmitter (Polar
  Electro) to a wrist unit (p. 1176) — i.e. the segment decomposition is applied
  to a real 15-second sampled series, not to hand-timed intervals.

M90 names the unit "trimp" and states that "a precise evaluation of whole
session can be obtained from sum of separate segments" (Fig. 2 caption).

## 3. The fitness–fatigue model

Training contributes to two factors whose difference is performance
(B91 p. 413; M90 Fig. 1).

**B91 (p. 413–414):** a fitness impulse `p(t) = k₁w(t)` and a fatigue impulse
`f(t) = k₂w(t)`, "initially K₁ = 1 for fitness and K₂ = 2 for fatigue", decaying
between sessions with time constants τ₁ and τ₂ — "on average" **45 d for fitness
and 15 d for fatigue**. B91 defines the time constant as the time for a decaying
variable to fall to **37%** of its level, and observes fatigue therefore decays
~3× faster than fitness, which is what makes a taper reveal accumulated fitness.

**M90 (p. 1173), the defining mathematical statement:**

```
  (4)  g(t) = g(t−i)·e^(−i/τ₁) + w(t)          fitness
  (5)  h(t) = h(t−i)·e^(−i/τ₂) + w(t)          fatigue
  (8)  p(t) = k₁·g(t) − k₂·h(t)                performance
```

where `i` is the interval since the previous training. `k₁` and `k₂` are applied
**once**, at the combination step; `g` and `h` accumulate `w(t)` unweighted.
See [D2](#d2-b91-states-the-recursion-inconsistently).

M90 also derives, for the constant case `w(t) = T`, `i = 1`:

```
  (6)  g(t) = T·(1 − e^(−t/τ₁))/(1 − e^(−1/τ₁))       (7) likewise for h, τ₂
  (9)  p(t) = k₁T·[…] − k₂T·[…]
 (10)  t_n  = (τ₁τ₂/(τ₁−τ₂))·ln[ (τ₁k₂(1−e^(−1/τ₁))) / (τ₂k₁(1−e^(−1/τ₂))) ]
 (11)  p(∞) = k₁T/(1 − e^(−1/τ₁)) − k₂T/(1 − e^(−1/τ₂))
 (12)  p(t) = k₁g(t_s)·e^(−t/τ₁) − k₂h(t_s)·e^(−t/τ₂)   after training ceases
```

`t_n` is the time of the performance minimum — performance first *declines* from
the onset of training, then recovers and rises.

**Illustrative behaviour** (M90 Fig. 3–4), for w = T = 100 trimps/day, i = 1,
τ₁ = 45, τ₂ = 15, k₁ = 1, k₂ = 2: fitness 3,351 and fatigue 3,044 arbitrary
units at day 60 (difference ~307); performance minimum at t_n = 16 d, back to
baseline by day 47; continuous-training asymptote 1,449 units; ceasing training
at day 60 peaks at 1,353 units on day 83.

**Fitted, per-subject values** (M90 Table 2) — these are the empirical result,
and they are *not* 45/15:

| Subject | τ₁ | τ₂ | k₁ | k₂ | r² | F | df | P | SE |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| EWB (M, 57 y, VO₂max 48.8) | 50 | 11 | 1 | 1.8 | 0.71 | 59 | 4,21 | ≤0.001 | +13 |
| RHM (M, 42 y, VO₂max 51.3) | 40 | 11 | 1 | 2.0 | 0.96 | 252 | 4,18 | ≤0.0001 | ±7 |

B91 adds that a fitted constant set holds for **60–90 d** before re-fitting is
needed (p. 415), and that the optimal taper in the athlete shown ran to **7 d**
(p. 410).

## 4. Criterion performance (M90 §Quantifying actual performance)

Performance times are converted to a points score on a nonlinear scale, because
equal time improvements are worth more near the elite asymptote:

```
 (13)  R(t) = 3.1 + 1.065·e^(−0.01t)     1500 m world record, min; t = years from 1896
 (14)  Cp   = 294.7 · ln[ 11.9 / (y − 3.1) ]     y = recorded 1500 m time, decimal min
```

anchored so a 3.5-min world best scores 1,000 points and 15 min scores 0, with
L = 3.1 min the assumed ultimate limit. fitdocs has no use for this today; it is
recorded because it is the scale every "criterion points" figure in both texts
is plotted against.

## 5. Discrepancies between the sources

### D1 The multiplicative coefficient

> **Resolved 2026-07-27 (maintainer ruling): fitdocs uses B91's coefficient.**
> The conflict below is recorded because the citation must carry it, not
> because it is still open. See [§7](#7-what-this-changes-for-fitdocs).

B91 carries `0.64` (male) / `0.86` (female); M90 Eq. 2 has no leading
coefficient at all. Both agree exactly on the exponents 1.92 / 1.67.

| x = ΔHR ratio | B91 male | B91 female | M90 men | M90 women |
|---:|---:|---:|---:|---:|
| 0.0 | 0.640 | 0.860 | 1.000 | 1.000 |
| 1.0 | 4.365 | 4.568 | 6.821 | 5.312 |

Consequences: M90's form yields a raw TRIMP exactly **1/0.64 = 1.5625×** B91's
for men, and B91's weighting is *below unity* at low intensity (it attenuates)
where M90's is neutral at x = 0 by construction.

A plausible reconciliation, offered as **inference, not text**: M90 says b was
chosen to match the *shape* of Green et al.'s blood-lactate curve. A lactate
curve of the form `0.64·e^(1.92x)` has a resting intercept of 0.64 mM, which is
physiologically ordinary. B91 appears to retain the fitted lactate curve
including its intercept; M90 appears to retain only its shape, normalising
Y(0) = 1. Neither text says this.

### D1a M90's own worked example contradicts M90 Eq. 2

M90 p. 1172 illustrates the scale: subject RHM "could generate ~125 training
impulses by running 14 km in 1 h at a heart rate of 150 beats/min". RHM is male,
age 42 (Table 1). Solving back for the ΔHR ratio that produces 125 units in 60
min gives:

| Weighting used | implied x | implied HR_max at HR_rest = 50 |
|---|---:|---:|
| M90 Eq. 2, `Y = e^(1.92x)` | 0.626 | **210** |
| B91, `y = 0.64·e^(1.92x)` | 0.759 | **182** |

An HR_max of 182 is the ordinary expectation for a 42-year-old; 210 is not.
**M90's numerical illustration is consistent with the coefficient its own
equation omits.** This is the strongest available evidence that `0.64` belongs
in the formula and that M90 Eq. 2 is an incomplete transcription rather than a
deliberate alternative — but it is an inference from one example with unstated
HR_max/HR_rest, not a statement in either text.

### D2 B91 states the recursion inconsistently

B91 defines `p(t) = k₁w(t)` and `f(t) = k₂w(t)` on p. 413, then on p. 414 gives
both

```
a(t) = k₁·w(t)·e^(−t/τ₁) − k₂·w(t)·e^(−t/τ₂)        (p. 414 body)
a(t) = k₁·p(t) − k₂·f(t)                            (Fig. 9.10 annotation)
```

The second applies k₁/k₂ **twice** (since p and f already carry them). The first
applies them once but describes the decay of a *single* impulse — it has no
cross-session accumulation term, so it cannot produce the multi-session curves
B91's own Figures 9.10–9.12 show. **M90 Eqs. 4/5/8 are the correct and complete
statement**; B91's rendering is schematic. Use M90 for any implementation.

### D3 B91 misstates e

"the Napierian logarithm having a value of 2.712" (p. 408). Evaluating
`0.64·2.712^(1.92x)` instead of `0.64·e^(1.92x)` understates y by 0.22% at
x = 0.5 and 0.44% at x = 1.0. Use `math.e`; the misstatement is a typo in the
source, not an alternative base.

### D4 None of B91's worked examples satisfy B91's own equation

| Figure | T (min) | HR | x | B91's stated y | B91's stated TRIMP | y from B91 male eq. | TRIMP from B91 male eq. |
|---|---:|---:|---:|---:|---:|---:|---:|
| 9.5 | 10 | 150 | 0.667 | 2.5 | ~16.6 | 2.302 | 15.35 |
| 9.6 | 60 | 140 | 0.600 | 1.8 | 64.8 | 2.025 | 72.91 |
| 9.6 | 18 | 80 | 0.200 | 0.2 | 0.9 | 0.940 | 3.38 |

(All three assume HR_max = 200, HR_rest = 50, as the captions state.)

Rows 1 and 2 are internally consistent — `T × x × y` reproduces the stated TRIMP
from the stated `y` — but the stated `y` matches neither published curve. Row 3
is not even internally consistent: `18 × 0.2 × 0.2 = 0.72`, while the caption
says 0.9 (which would need y = 0.25). Under M90's unweighted-coefficient form
the mismatch is larger still (Fig. 9.5 → 23.98 units).

**Consequence: B91's figure captions cannot serve as pinned test vectors.** Any
worked example fitdocs ships must be computed from the formula and labelled as
such, never quoted from these captions. This matters directly to load-channels
`design.md`'s worked-example requirement for the heart-rate channel.

### D5 45 d / 15 d are illustrative, not fitted

B91 presents τ₁ = 45 d and τ₂ = 15 d as average starting values, and M90 uses
the same pair only to draw Figs. 3–4. The least-squares fits in M90 Table 2 are
τ₁ = 50/40 and **τ₂ = 11 for both subjects**. Any fitdocs default of 45/15 is a
seed value, not an empirical finding, and must be described that way.

### D6 Model fidelity is imperfect even in the source

M90 p. 1177 reports t_m (time to peak after taper) modelled at 11 d against
15–19 d observed for RHM, and 16 d against 25–26 d for EWB — the latter
described as agreeing "less well with reality". Worth carrying into any
user-facing claim about predicted peaking.

## 6. Deviations of fitdocs' shipped implementation from the sources

`src/fitdocs/metrics/stress.py` accumulates, per consecutive sample pair with
`dt > 0` and the earlier sample's HR present:

```
HRr    = clamp((hr − rest)/(max − rest), 0, 1)
trimp += (dt/60) · HRr · 0.64 · exp(1.92 · HRr)
```

Against the primary texts that is:

1. **B91's coefficient, not M90's.** Attested by B91 and by [D1a](#d1a-m90s-own-worked-example-contradicts-m90-eq-2); contradicted by M90 Eq. 2 as printed. **Ruled 2026-07-27: this is the intended form and stays.**
2. **Sex-neutral use of the male exponent.** Both sources define b per sex
   (1.92 / 1.67). fitdocs applies 1.92 to every athlete. This is now confirmed
   as a genuine deviation from both primary texts, not an artifact of secondary
   sourcing.
3. **Per-sample integration, not per-steady-state-segment.** Both sources sum
   over segments of relatively constant HR using each segment's *average* HR.
   fitdocs integrates every sample pair. This is the continuous limit of the
   same construction, but it is **not numerically equal**: `f(x) = x·e^(1.92x)`
   is convex on [0, 1], so by Jensen's inequality the per-sample sum is
   **systematically ≥** the segment-mean form whenever HR varies within a
   segment. Equal only for constant HR.
4. **Clamping to [0, 1].** Neither source specifies clamping. M90 states the
   expected range of x as ~0.2–1.0 without bounding it; B91 is silent. The
   clamp is a fitdocs robustness choice for HR below rest or above max.
5. **`None` for an absent HR channel.** A fitdocs invariant; neither source
   addresses missing data.
6. **Minutes, arbitrary units.** Matches both sources exactly.

## 7. What this changes for fitdocs

Recorded here as findings; no code was changed by the session that wrote this
document. Two queue items carry the remaining work:
`2026-07-27-banister-morton-primary-texts-obtained` (re-source the citation and
sweep the stale prose) and
`2026-07-27-banister-figure-captions-unusable-as-vectors` (the D4 trap). The D1
decision is closed — see below.

- **`BANISTER_TRIMP` is no longer blocked.** Its note, its membership in
  `BLOCKED_CITATIONS`, and the design/queue prose asserting the texts could not
  be obtained are all stale as of 2026-07-27. Both texts are read; the citation
  is eligible for `PRIMARY_TEXT`, and M90 is citable to page and equation number.
- **`roadmap.md`'s refutation is withdrawn** (2026-07-27). It listed the
  web-quoted string `0.64·e^(1.92·%HRR)` men / `1.67` women under "Also rejected
  (refuted 0-3)". B91 p. 408 states exactly that pair. The web sources were
  right; the entry was withdrawn rather than re-marked, since leaving it told
  every later session to reject a confirmed string.
- **The citation's `work` string is confirmed**, and its bibliographic frame is
  now complete: chapter title (p. 403) and running heads (pp. 407–423) match, the
  cover/title page give the editors, edition, publisher and ISBN, and the
  catalogue record supplies the year
  ([§8](#8-what-the-scans-do-and-do-not-attest)).
- **An old citation defect is explained.** This repo's history records
  `BANISTER_TRIMP.work` once citing *"Physiological Testing of Elite Athletes"* —
  a title that never quite matched. The catalogue record resolves it: the 1991
  second edition is a **revised edition of *Physiological Testing of the Elite
  Athlete* (1982)**, so the wrong title was the *first edition* of the same
  book, not a fabrication. Anything still carrying the 1982 title is pointing at
  a different book that does not contain this chapter — worth a grep when the
  citation is re-sourced.
- **D1 is decided: fitdocs keeps B91's `0.64`** (maintainer ruling, 2026-07-27).
  It is what B91 states and what M90's own worked example implies, so it is both
  the better-attested option and the one already shipped. Consequences:
  - **No value moves.** `metrics/stress.py` already ships 0.64, so no rendered
    `DerivedMetrics.trimp` changes and **no migration-by-regen is owed** — the
    1.5625× exposure existed only on the road not taken.
  - **The citation note must still name both forms.** Recording B91 alone would
    hide that a companion primary text prints the weighting without the
    coefficient. A note that flattens that is the failure the citation-vocabulary
    work exists to prevent.
  - **A vocabulary gap is now live**, not hypothetical: `VerificationStatus` has
    no term for "primary text, but a companion primary text disagrees". Carried
    on `2026-07-27-banister-morton-primary-texts-obtained`.
  - The heart-rate *channel* was never exposed either way: HRSS's ratio form
    cancels the coefficient exactly, leaving only the 1.92 exponent — on which
    both texts agree.

## 8. What the scans do and do not attest

The B91 scans cover pp. 403–424 continuously — the full chapter, opening page
through the last figure — plus the cover, title page and copyright page, added
2026-07-27.

**Now attested from the book itself:**

- Book title, **second edition**, and "Published for the Canadian Association of
  Sport Sciences" (cover and title page).
- Editors: **J. Duncan MacDougall** (McMaster), **Howard A. Wenger**
  (Victoria), **Howard J. Green** (Waterloo).
- Publisher: **Human Kinetics Books, Champaign, Illinois**.
- ISBN **0-87322-300-4** — hand-written on the title page by a cataloguer
  rather than printed, so it is a library annotation rather than a statement of
  the book; it agrees with the catalogue record below.
- Chapter authorship, title and page range (p. 403 opener; running heads
  pp. 407–423).

**Attested by the library catalogue record, not by the book:**

- The **publication year, 1991**, together with the publisher string
  "Champaign, Ill. : Human Kinetics Books", the collation `x, 432 p. : 24 cm`,
  the note that this edition is a revision of *Physiological Testing of the
  Elite Athlete* (1982), and the editors as associated names. Source: the
  Internet Archive record for this book (**OCLC 1150972541**), confirmed by the
  maintainer 2026-07-27.
- **Why it is not in the book.** The copyright page was captured in full — it
  carries the printing line "10 9 8 7 6 5", Human Kinetics' office addresses, a
  humankinetics.com URL and a University of Greenwich library stamp of 16 Apr
  1998, and **no copyright notice or year at all**. The scanned copy is a later
  printing whose verso was reset for reprint, and the year did not survive that
  reset. No further page will produce it; this is the ceiling of what the
  physical book attests.
- **How to classify it.** A library catalogue record is not the work's own text,
  so under this repo's vocabulary the year is not `PRIMARY_TEXT`-attested — but
  it is also not a "secondary summary" in the sense
  `SECONDARY_ATTESTATION` was coined for. A cataloguing authority is the
  *standard* source for publication metadata, and is stronger for that datum
  than the book would be. The split to record: **the chapter's content is
  primary-text attested; its publication year rests on a bibliographic
  authority.** Flagged on
  `2026-07-27-banister-morton-primary-texts-obtained`, which owns the
  `VerificationStatus` question.
- The collation `x, 432 p.` independently corroborates the chapter's extent —
  ch. 9 ending at p. 424 sits correctly inside a 432-page body.

**Still not attested:**

- The chapter carries **no reference list** in the scanned range, so B91's own
  sourcing for the lactate curve cannot be followed from the chapter itself.
  M90 ref. 6 (Green et al. 1983) is the usable pointer — and note that its first
  author, **Howard J. Green of the University of Waterloo, is an editor of this
  very book**. The provenance chain for the 1.92/1.67 exponents runs through the
  volume's own editor.

M90, by contrast, is a complete journal PDF: the citation, DOI-era page range,
receipt dates, funding note (NSERC) and full 12-item reference list are all
present and verifiable.
