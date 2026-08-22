# Research & Design Decisions — load-channels

## Summary

- **Feature**: `load-channels`
- **Discovery Scope**: New Feature (a new pure-computation layer) built as an
  Extension of the shipped `fitdocs.metrics` primitives and the
  `athlete-benchmarks` store.
- **Key Findings**:
  1. **The disputed Banister coefficient largely cancels.** HRSS is defined as
     `TRIMP_activity / TRIMP_one_hour_at_LTHR × 100`. Both terms carry the same
     multiplicative coefficient, so it divides out exactly; only the *exponent*
     survives into the result. The refuted-0-3 constant therefore has a much
     smaller blast radius on this feature than on the shipped `trimp` metric,
     and that invariance is directly testable.
  2. **intervals.icu publishes a pace-load formula; TrainingPeaks does not.**
     A developer post gives `intensity = mps / threshold_pace_mps`,
     `load = moving_time × mps × intensity × 100 / (threshold_pace × 3600)`,
     which reduces to `hours × intensity² × 100`. TrainingPeaks describes rTSS
     and NGP only in prose. The interop constraint therefore resolves to
     intervals.icu's form, which also happens to be the one with a published
     equation.
  3. **A coverage gate has a citable precedent.** TrainingPeaks documents an
     **80% power-data coverage** requirement before it will compute power-based
     TSS, and marks manually-entered TSS with an asterisk rather than computing
     silently. That is the source for this feature's default, so the number is
     not invented.
  4. **Neither the Banister nor the Minetti coefficients could be verified
     against primary text** in this pass (paywalls / print-only book chapter).
     Both are consistently attested by independent secondary sources. This is
     recorded as a *verification status* on each citation rather than papered
     over. _(Superseded 2026-07-27/2026-07-29, queue
     2026-07-27-banister-morton-primary-texts-obtained: both texts have since
     been obtained and read in full. `MINETTI_2002` was re-sourced to
     `PRIMARY_TEXT` 2026-07-27 (queue
     2026-07-26-citation-vocabulary-diverges-across-layers) and
     `BANISTER_TRIMP` to `PRIMARY_TEXT` 2026-07-29; see
     `docs/reference/banister-trimp-primary-sources.md`. Neither citation is
     secondary-attested any longer.)_

## Research Log

### Banister TRIMP coefficients and their provenance

- **Context**: The roadmap refutes the web-quoted string `0.64·e^(1.92·%HRR)`
  (men) / `1.67` (women) 0-3 and requires primary-literature sourcing.
- **Sources consulted**: Morton, Fitz-Clarke & Banister (1990), *J Appl Physiol*
  69(3):1171-1177 (abstract only; full text 403); Banister (1991), "Modeling
  elite athletic performance", in MacDougall/Wenger/Green (eds.),
  *Physiological Testing of the High-Performance Athlete*, 2nd ed., Human
  Kinetics, pp. 403-424 (print only, no accessible full text); Banister,
  Calvert, Savage & Bach (1975), *Aust J Sports Med* 7:57-61 (origin of the
  TRIMP *concept*, not of the exponential weighting); fellrnr.com/wiki/TRIMP;
  forum.intervals.icu threads "Bannister's TRIMP" and "HRSS (normalized TRIMP)
  training load". _(Superseded 2026-07-27 for Morton, 2026-07-29 for Banister,
  queue 2026-07-27-banister-morton-primary-texts-obtained: both works' full
  texts were subsequently obtained and read in full -- Morton et al. (1990) as
  the publisher PDF, Banister (1991) as page scans of the complete chapter
  9 (pp. 403-424) -- and extracted to
  `docs/reference/banister-trimp-primary-sources.md`. Neither remains
  "abstract only" or "print only, no accessible full text".)_
- **Findings**:
  - The exponential HR-*reserve* weighting is uniformly attributed to
    Banister (1991) and described as fitted to a blood-lactate-versus-%HRR
    regression. No reachable source quotes the book chapter's page text.
    _(Superseded 2026-07-29, queue
    2026-07-27-banister-morton-primary-texts-obtained: the book chapter's own
    p. 408 was subsequently read directly and now is quoted --
    `docs/reference/banister-trimp-primary-sources.md` §1.)_
  - The better-attested sex-specific form changes **both** terms —
    `0.64·e^(1.92·HRr)` for men, `0.86·e^(1.67·HRr)` for women. A minority of
    derivative sources mis-state this as `0.64·e^(1.67·HRr)` for women,
    conflating the female exponent with the female coefficient. _(Confirmed,
    not merely "better-attested", 2026-07-29: Banister (1991) p. 408 states
    exactly this pair in its own text. Morton, Fitz-Clarke & Banister (1990)
    Eq. 2, p. 1172, agrees on both exponents (1.92 men, 1.67 women) but
    prints no multiplicative coefficient at all -- see
    `docs/reference/banister-trimp-primary-sources.md` §1, §2, §5 D1.)_
  - `HRr` is a **fraction in [0, 1]**, not a percentage, in every source that
    specifies units.
  - fellrnr is the most likely proximate origin of the modern web string, and
    it attributes to 1975 rather than 1991 — an internal inconsistency in the
    secondary record.
  - intervals.icu implements exactly this TRIMP and normalizes it as
    `TRIMP_activity / TRIMP_one_hour_at_LTHR × 100`, crediting the HRSS
    convention to the Elevate Strava extension. It requires **resting HR,
    maximum HR and a threshold HR** for HRSS to work.
- **Implications**: This feature must **not** restate the coefficients. It
  consumes the shipped `metrics.stress.trimp` for both the activity value and
  the one-hour reference, so the two can never be weighted differently and a
  later fit-ingest re-sourcing moves both together. The remaining exposure —
  the exponent, and a possible future sex-specific split — is recorded as a
  cross-spec risk below.

### Coggan NP / IF / TSS and its worked examples

- **Sources consulted**: TrainingPeaks help centre articles on Normalized
  Power, Intensity Factor and "Training Stress Scores (TSS) Explained"
  (restating Allen & Coggan, *Training and Racing with a Power Meter*); several
  cross-consistent cycling-power references.
- **Findings**:
  - `IF = NP / FTP`; `TSS = IF² × hours × 100`, equivalently
    `TSS = duration_s × NP × IF / (FTP × 3600) × 100` — algebraically identical
    to the formula already shipped in `metrics/stress.py:power_tss`.
  - Worked examples obtained: **NP 210 W ÷ FTP 280 W → IF 0.75**;
    **7080 s, NP 183 W, FTP 215 W → IF 0.851, TSS ≈ 142**;
    **5400 s, NP 220 W, FTP 250 W → IF 0.88, TSS ≈ 116**. One hour at FTP is
    100 by definition.
- **Implications**: The power channel is a thin, verifiable composition over
  shipped primitives. The worked examples become the channel's verification
  cases (Req 4.8, 8.4).

### Minetti energy cost of running on a gradient

- **Sources consulted**: Minetti, Moia, Roi, Susta & Ferretti (2002), "Energy
  cost of walking and running at extreme uphill and downhill slopes", *J Appl
  Physiol* 93:1039-1046 (PubMed 12183501; publisher full text 403); a
  reverse-engineering writeup that transcribes the equation directly from the
  paper; independent search-index corroboration of the same coefficients.
- **Findings**:
  - Running cost, gradient `i` as a decimal fraction, in J·kg⁻¹·m⁻¹:
    `Cr(i) = 155.4·i⁵ − 30.4·i⁴ − 43.3·i³ + 46.3·i² + 19.5·i + 3.6`.
  - Validated gradient range **−0.45 ≤ i ≤ +0.45** (the treadmill grades the
    study covered). Level cost `Cr(0) = 3.6`.
  - One widely-mirrored transcription (a garbled OCR) renders the linear term
    as `−165·i`; two independent sources agree on `+19.5·i`, and only `+19.5`
    is physically coherent (uphill must cost more). The corrupted variant is
    explicitly rejected.
  - The **walking** polynomial could not be obtained at all — only the paper's
    reported empirical minima. It is therefore not implemented. _(Superseded
    2026-07-27, queue 2026-07-26-citation-vocabulary-diverges-across-layers:
    re-sourcing `MINETTI_2002` to `PRIMARY_TEXT` located and read Fig. 1's
    caption in full, which gives both the running and the walking
    polynomials together, so the walking form was in fact read alongside the
    running form. It remains unimplemented, but by scope choice, not for
    lack of a source — see Req 7.9, amended to match.)_
  - No platform documents a grade-smoothing window. Strava's post-2017 GAP is
    proprietary and no longer Minetti-based; intervals.icu says only that it
    uses "the same model Strava uses"; Runalyze cites Minetti by name.
- **Implications**: Minetti's running polynomial is the citable model, applied
  as the ratio `Cr(i)/Cr(0)`, clamped to ±0.45 rather than extrapolated
  (Req 7.4). Smoothing has no external convention to match, so the design
  reuses fitdocs' own shipped convention instead (below). Walk/Hike get no pace
  channel (Req 6.7, 7.9), which is consistent with the roadmap already routing
  those modalities to the HR channel.

### Pace-anchored load: which formulation to match

- **Sources consulted**: forum.intervals.icu "Running load vs TrainingPeaks
  rTSS"; TrainingPeaks articles on rTSS and Normalized Graded Pace.
- **Findings**:
  - intervals.icu (published): `intensity = mps / threshold_pace`,
    `load = round(moving_time × mps × intensity × 100 / (threshold_pace × 3600))`
    where `mps` is the mean speed of the GAP (or raw) trace. This reduces
    exactly to `hours × intensity² × 100`, and one hour at threshold pace gives
    100 by substitution.
  - intervals.icu counts **moving time only**, excluding stopped time.
  - TrainingPeaks' NGP additionally *normalizes* graded pace the way NP
    normalizes power (variability-weighted), but publishes neither the equation
    nor a worked example.
- **Implications**: The interop constraint selects intervals.icu's form. The
  deliberate consequence — the pace channel is variability-blind where the
  power channel is not — is recorded as a stated decision rather than an
  oversight.

### Data-sufficiency precedent

- **Findings**: TrainingPeaks documents that power-based TSS requires **power
  data for at least 80% of total workout time**, with a documented fallback and
  an explicit asterisk marker when a load is not automatically computable.
  GoldenCheetah, Runalyze and intervals.icu publish no numeric coverage gate.
- **Implications**: 0.80 is adopted as the documented default minimum stream
  coverage with TrainingPeaks cited as its source (Req 3.10). The rest of the
  gate — per-channel overrides, the minimum-duration floor — is fitdocs' own
  and is declared as such.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Pure function leaf per channel over resolved inputs | Each channel is `f(activity, metrics, benchmark, settings) -> outcome` | No I/O, trivially testable against worked examples, no policy leakage | Caller must resolve benchmarks first | **Selected.** Matches the brief's `(Samples, benchmark, config)` shape |
| Channels take a `ProfileView` and resolve their own benchmarks | Channels call `profile.benchmark(kind, discipline=..., on=...)` | Fewer arguments at the call site | Forces the modality→discipline mapping into this spec, which the roadmap assigns to `threshold-load`; makes channels impure in spirit | Rejected |
| A `Channel` class hierarchy with a shared abstract base | Polymorphic `compute` over a common ABC | Uniform dispatch for the caller | Signatures genuinely differ (one benchmark vs three); an ABC would force a bag-of-benchmarks parameter and erase the type safety | Rejected; a shared *result* vocabulary gives the uniformity without the false abstraction |
| Fold the channels into the `threshold` calculator | One module computes and selects | Fewer files | Produces the ~22-task spec the roadmap's boundary strategy explicitly rejects; mixes verifiable math with policy | Rejected by roadmap |

## Design Decisions

### Decision: Channels consume already-resolved benchmarks

- **Context**: A channel needs a threshold value. Reaching it requires a
  discipline, which requires a modality→discipline mapping that
  `athlete-benchmarks` explicitly disclaims and the roadmap assigns to
  `threshold-load`.
- **Alternatives considered**: (1) pass a `ProfileView` plus the activity;
  (2) pass the resolved `Benchmark` objects.
- **Selected approach**: channels take `Benchmark | None` arguments.
- **Rationale**: keeps the mapping out of this spec entirely (Req 9.5), keeps
  channels I/O-free and clock-free, and lets the result carry the anchor's
  `measured_on` and `note` so a downstream consumer can report what the number
  was anchored to.
- **Trade-offs**: `threshold-load` carries more wiring. Accepted: that wiring
  *is* its job.
- **Follow-up**: the channel must reject a benchmark of the wrong `kind` as a
  programming error (Req 1.9), because the type system alone cannot.

### Decision: Coverage is time-weighted over the sampled span

- **Context**: "60% HR coverage" must be defined precisely enough to gate on.
- **Alternatives considered**: (1) sample-count coverage — present samples ÷
  total samples, which is what the shipped document renderer displays;
  (2) time-weighted coverage — the summed inter-sample intervals whose earlier
  sample carries a value, divided by the total sampled span.
- **Selected approach**: time-weighted.
- **Rationale**: it is exactly the accumulation domain of the load itself.
  `metrics.stress.trimp` sums `dt` over pairs whose *earlier* sample has a
  heart rate; measuring coverage the same way makes the gate report the true
  fraction of the activity the number describes. Under uniform sampling — the
  normal case — the two definitions coincide; they diverge precisely in the
  smart-recording and dropout cases the gate exists for.
- **Trade-offs**: the figure can differ from the "Channel coverage" table the
  workout document already renders (sample-count). Recorded as a cross-spec
  consistency note rather than changing shipped render output, which is out of
  boundary (Req 9.8).
- **Follow-up**: a device *pause* produces one long interval whose earlier
  sample does carry a value, so a pause counts as covered and does not penalize
  the gate. That mirrors shipped `trimp` behavior, which also credits the whole
  gap; correcting that is a fit-ingest question, not this feature's.

### Decision: the one-hour-at-LTHR reference is computed by the shipped TRIMP itself

- **Context**: Req 5.4 and 5.5 forbid two training-impulse computations, and
  Req 5.6 forbids restating the coefficients.
- **Alternatives considered**: (1) expose the per-sample weighting from
  `metrics/stress.py` as a public helper and multiply by 60; (2) call the
  shipped `trimp` on a synthetic one-hour, constant-heart-rate sample series.
- **Selected approach**: (2).
- **Rationale**: it requires **no change at all** to the fit-ingest-owned
  module (Req 9.8), and it makes the identity structural: the reference is
  literally "what this tool would score for one hour at LTHR". Any future
  change to the shipped implementation — coefficients, clamping, gap handling —
  moves the numerator and the denominator together by construction.
- **Trade-offs**: constructing a two-sample synthetic `Samples` is mildly
  unusual. Documented at the call site.
- **Follow-up**: HRSS is then provably invariant to the multiplicative
  coefficient; that property is pinned by a test (Req 5.10).

### Decision: the heart-rate weighting seam is a Protocol with exactly one implementation

- **Context**: Roadmap decision 7 — the build-time regression is deferred
  *entirely, not stubbed*, yet the weighting must be substitutable.
- **Selected approach**: a `HeartRateIntensityModel` Protocol used as the
  channel's parameter type, with one shipped implementation bound as the
  default argument. No second implementation, no registry, no configuration key.
- **Rationale**: a Protocol used as a parameter type is a live type seam, not
  dead code; the regression later ships as a second implementer without
  touching the channel.
- **Trade-offs**: a reviewer may read a one-implementer Protocol as speculative
  abstraction. The roadmap decision is the justification and is cited in the
  module docstring.

### Decision: match intervals.icu's pace-load formulation, not TrainingPeaks' NGP

- **Context**: interop constraint; TrainingPeaks publishes no equation.
- **Selected approach**: mean grade-adjusted speed over moving time, then
  `hours × intensity² × 100`.
- **Rationale**: it is the only published, reproducible formulation; it matches
  the platform the roadmap names for interop; and it is fully determined by
  values fitdocs already computes.
- **Trade-offs**: the pace channel does not weight variability, so an interval
  session and a steady run at the same average grade-adjusted pace score the
  same. Recorded as a stated, intentional divergence from TrainingPeaks rTSS.

### Decision: grade smoothing reuses fitdocs' own shipped convention

- **Context**: no external smoothing convention exists to match.
- **Selected approach**: a trailing, `None`-skipping boxcar of width 10 over
  the altitude channel — the same width and alignment the shipped elevation
  metrics already pin — but emitted **index-aligned** with the sample arrays,
  because the shipped helper compacts its output and is private.
- **Rationale**: the terrain the document reports as climb and the terrain the
  load adjusts for are then the same terrain (Req 7.3), with no change to the
  shipped metric.
- **Trade-offs**: a small, deliberate duplication of a 10-line helper across an
  ownership boundary, justified by the differing output shape and recorded in
  the module docstring.

### Decision: sufficiency configuration lives in a `[load.sufficiency]` sub-table

- **Context**: the `[load]` table is co-owned by `athlete-benchmarks`
  (`benchmark_staleness_days`), the `training-load` update (`default_calculator`)
  and this feature; `training-load` states that unknown **sub-tables** are
  ignored precisely so downstream specs can add their own.
- **Selected approach**: extend the single existing `LoadSettings` dataclass
  with a `sufficiency` member projected from a `[load.sufficiency]` sub-table;
  no second reader (Req 3.7).
- **Rationale**: namespacing prevents key collisions between three siblings and
  matches the additivity contract both upstream specs declare.
- **Trade-offs**: one extra level of nesting in the settings file.
- **Follow-up**: the pure `SufficiencySettings` value type lives with the
  channel types, and `load/settings.py` imports it — never the reverse — so the
  channels stay free of any configuration-module dependency.

## Risks & Mitigations

- **The fit-ingest re-sourcing may introduce sex-specific coefficients.** The
  multiplicative term cancels in HRSS but the exponent does not, and a
  sex-dependent exponent would require an athlete-sex input this feature does
  not have. *Mitigation*: the weighting seam takes the whole model, so a
  sex-aware model is a different implementer rather than a signature change;
  flagged to the fit-ingest update as a consequence to weigh.
- **Two in-flight specs each introduce a `[load]` reader.**
  `athlete-benchmarks` creates `load/settings.py` with `LoadSettings`;
  `training-load` task 3.1 also adds "the load configuration table reader".
  *Mitigation*: this feature extends whichever lands first and adds no reader
  of its own; the collision is reported to both owners.
- **Minetti and Banister coefficients are secondary-attested only.**
  *Mitigation*: each carries an explicit verification status in code, and a
  test pins that no constant lacks one; upgrading a status later is a one-line
  change with no arithmetic impact. _(Superseded 2026-07-27/2026-07-29:
  materialized as predicted, then resolved -- both were upgraded to
  `PRIMARY_TEXT` -- `MINETTI_2002` 2026-07-27, `BANISTER_TRIMP` 2026-07-29,
  queue 2026-07-27-banister-morton-primary-texts-obtained -- with no
  arithmetic impact, exactly as this mitigation anticipated.)_
- **The coverage figure this feature gates on differs from the one the shipped
  document displays** under non-uniform sampling. *Mitigation*: reported as a
  cross-spec note; `activity-qa-flags` is the natural place to surface the
  gate's own figure if the divergence ever confuses a reader.
- **A pause credited as covered time also inflates the shipped TRIMP.**
  Pre-existing shipped behavior; out of boundary here, recorded for the
  fit-ingest owner.

## References

- Allen H. & Coggan A., *Training and Racing with a Power Meter* — NP / IF / TSS
  definitions, as restated by the TrainingPeaks help centre (worked examples:
  IF 210/280 = 0.75; 7080 s, NP 183 W, FTP 215 W → TSS ≈ 142).
- TrainingPeaks help centre — the 80% power-coverage requirement for power-based
  TSS and the explicit not-computed marker.
- Banister E.W. (1991), "Modeling elite athletic performance", in MacDougall,
  Wenger & Green (eds.), *Physiological Testing of the High-Performance
  Athlete*, 2nd ed., Human Kinetics, 403-424 — TRIMP exponential HR-reserve
  weighting. *Not verified against primary text.* _(Superseded 2026-07-29,
  queue 2026-07-27-banister-morton-primary-texts-obtained: the book chapter's
  own page scans were obtained and read in full this session — see
  `BANISTER_TRIMP` in `sources.py`, re-sourced to `PRIMARY_TEXT` — so this
  marker no longer applies; it is left standing above only as a record of
  this research phase's original, now-resolved finding.)_
- Morton R.H., Fitz-Clarke J.R. & Banister E.W. (1990), "Modeling human
  performance in running", *J Appl Physiol* 69(3):1171-1177 — abstract confirms
  the duration × HR-reserve × lactate-derived weighting structure. _(Superseded
  2026-07-29, queue 2026-07-27-banister-morton-primary-texts-obtained: the
  full publisher PDF was obtained and read in this session, not merely its
  abstract — see `BANISTER_TRIMP.note` in `sources.py`, which cites this
  paper's own Eq. 2, p. 1172, directly; "abstract confirms" is left standing
  above only as a record of this research phase's original, now-superseded
  finding.)_
- Minetti A.E., Moia C., Roi G.S., Susta D. & Ferretti G. (2002), "Energy cost
  of walking and running at extreme uphill and downhill slopes", *J Appl
  Physiol* 93:1039-1046 — running cost polynomial and its ±45% validated range.
  *Coefficients not verified against primary text.* _(Superseded 2026-07-27,
  queue 2026-07-26-citation-vocabulary-diverges-across-layers: the paper's
  own text was located and read this session — see `MINETTI_2002` in
  `sources.py`, re-sourced to `PRIMARY_TEXT` — so this marker no longer
  applies to Minetti; it is left standing above only as a record of this
  research phase's original, now-resolved finding.)_
- forum.intervals.icu — the published pace-load formula, the HRSS normalization
  and its required inputs, and the HR-from-power regression feature that this
  feature's weighting seam is shaped to accommodate later.
- fellrnr.com/wiki/TRIMP — worked TRIMP example (male, HRmax 200, HRrest 40,
  30 min at 130 bpm → ≈ 31.5), used as a verification case for the shipped
  training-impulse computation this feature consumes.
