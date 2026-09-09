# Brief: performance-benchmarks

## Problem

Every load fitdocs computes is anchored on a dated benchmark — FTP, lactate
threshold heart rate, threshold pace — and the archive has none for the past.
A benchmark answered at the prompt is dated today, the store never applies a
future-dated benchmark to a past activity, and so an athlete with nine years
of `.fit` files runs `fitdocs load` and gets *not computed* on every page
(queue item `2026-08-27-prompt-date-strands-historical-documents`, critical).
Wave 0 of Phase 6 fixes the prompt's dating. But even a correctly dated
prompt answer is one number for one date; it cannot describe what the athlete's
threshold was in 2019, 2021 and 2024.

The races can. A race is a dated maximal performance with a certified distance
and an official time, and the literature has been converting such results into
threshold estimates for forty years. The athlete asked for exactly this: use
races and hard workouts to calculate historical fitness. This spec turns tagged
efforts into dated benchmarks, so the existing calculator scores the whole
archive against the threshold that was true at the time.

## Current State

- `src/fitdocs/benchmarks.py`: `Benchmark(kind, discipline, value,
  measured_on, note)`; kinds `ftp_watts`, `lthr_bpm`,
  `threshold_pace_s_per_km`, `max_hr_bpm`, `resting_hr_bpm`; `applicable()`
  returns the latest entry dated on or before the activity, never a later one.
  **Nothing records how a benchmark was obtained** — `note` is the only free
  slot and the prompt path never fills it.
- The write path exists: `AthleteProfile.with_benchmark(...)` +
  `save_profile(...)` (`src/fitdocs/load/profile.py`). The merge is keyed
  `(scope, kind, measured_on)` and **explicitly preserves unrecognised entry
  keys, naming "a `source` a future feature wrote" as the case it protects**
  (`profile.py:535-540`). The parser ignores unknown keys; the serializer
  emits only `value`, `measured_on`, `note`.
- The load pass already resolves each page's archived `.fit` from the
  fit-archive and re-parses it (`src/fitdocs/load/engine.py`), so re-reading a
  tagged activity's streams is an established pattern, not a new capability.
- Boundaries that say no today, and why this spec is allowed to say yes:
  `athlete-benchmarks` lists "auto-FTP / eFTP estimation of any kind" out of
  scope, and `threshold-load` Req 11.6 forbids the *calculator* from estimating
  a threshold from activity data. Both are about keeping estimation out of the
  store's and the calculator's own code. This spec is a separate pass with its
  own module that hands the store ordinary dated entries; the calculator still
  reads only what it is handed. `athlete-benchmarks`' boundary line is
  amended to point here; Req 11.6 stands untouched.
- `effort-tags` supplies the input: which pages are races, tests or hard
  efforts, with an optional official distance and time.
- Data reality on the athlete's archive (2026-07-15 check of HealthFit
  exports): running files carry power at ~99% coverage and HR that can gap to
  62–72%; the cycling sample carried **no power**. So on this archive the
  running derivations will fire and the FTP derivation may derive nothing —
  which must be reported, never papered over.

## Desired Outcome

- A `fitdocs benchmarks derive` command (name to be settled) that reads every
  tagged page, re-parses its archived source, and derives, per effort:
  - **Threshold pace** (running, from a race): the pace the athlete could hold
    for one hour, solved from the race's distance and time through a cited
    race-equivalence model. Official distance and chip time when the tag
    carries them; recorded distance and moving time otherwise, with the
    fallback named in provenance.
  - **LTHR** (running or cycling, from a race, test or hard effort with an HR
    stream): the average heart rate of a sustained maximal effort of the
    duration the literature validates, with the HR stream's coverage gated.
  - **FTP** (cycling, from a test or race with a power stream): from a
    20-minute test by the published factor, or from a 50–70-minute time
    trial's average power by the definition itself.
- Each derived benchmark is written to `athlete.toml` **dated at the effort's
  local calendar date**, with a provenance record naming the method, the
  source page, the inputs used and the citation key. User-typed and
  prompt-answered entries are never overwritten or shadowed on the same date.
  Re-running is idempotent; the pass reconciles derived entries to the current
  tag set.
- A report per run: what was derived, what was declined and why — no HR
  stream, no power, effort outside the model's validity window, sport not
  covered — in the same vocabulary the load pass reports in.
- Every constant and formula carries a `CitedConstant`; every heuristic step
  the literature does not state is recorded as a fitdocs choice with its
  justification.

## Approach

A pure derivation leaf (`fitdocs/benchmarks/` grows a `derive` module, or a
sibling `fitdocs/performance/` package — design decides against the dependency
direction `cli -> engine/prompts -> profile -> benchmarks -> model`) that takes
an `Activity`, its `EffortTag` and the sufficiency verdicts and returns derived
benchmark candidates with provenance. A CLI pass composes the shipped document
readers, the load engine's archive resolution, and the profile write path. The
store gains a `source` field per entry — the seam its own merge already
reserved — under `athlete-benchmarks`' schema-version discipline.

The science, as settled by the discovery viability check (2026-09-09):

- **Race-equivalence model: Riegel's power law**, `t = a·d^b`, from Riegel
  (1981) *American Scientist* 69(3):285–290, valid for efforts of 3.5–230
  minutes; the running exponent 1.06 was printed in Riegel's *Runner's World*
  article (1977) and is attested in peer-reviewed literature (Drake, Finke &
  Ferguson 2024, *Eur J Appl Physiol* 124:507–526). The 1981 text is
  JSTOR-only and has not been read by this project — until it is, the model
  cites as secondary attestation, not primary text. Solving for the 60-minute
  distance is fitdocs' own step, inside the validity window, and is recorded
  as such. Rejected: Daniels' VDOT equations (the coefficients are not printed
  in *Oxygen Power* or *Daniels' Running Formula*, so they cannot cite to a
  page — the tables can, the formulae cannot); critical speed (needs two or
  more races at different distances and is not a one-hour pace: Hill 1993
  puts exhaustion at CP at 30–60 min, Jones et al. 2019 at 20–30 min). Both
  are candidates for a later amendment once two-race archives are common.
- **LTHR from a sustained effort**: McGehee, Tanner & Houmard (2005) *J
  Strength Cond Res* 19(3):553–558 — 30-minute time-trial average HR not
  different from HR at the 4 mmol/L lactate threshold, 27 runners and
  triathletes; Dumke et al. (2006) *J Strength Cond Res* 20(3):601–607 —
  60-minute time-trial HR matched HR at the lactate threshold in cyclists.
  Both use the **whole-effort average**. The coaching-book protocol ("final 20
  minutes of a 30-minute test", Friel) is secondary only and its 10-minute
  discard is unsourced — the spec uses the whole-effort average and a duration
  window informed by the two papers, recorded as a fitdocs choice.
- **FTP**: the definition (highest power sustainable for roughly one hour;
  average power of a ~40 km / 50–70-minute time trial) is stated in Coggan
  (2003) "Training and racing using a power meter: an introduction", the USA
  Cycling coaching-manual chapter, which is in hand. The 0.95 × 20-minute
  rule originates in Allen & Coggan, *Training and Racing with a Power Meter*
  (VeloPress; 2nd ed. 2010, chapter 3 by reviewer account — **page not yet
  verified**), and is attested and measured in Borszcz et al. (2018) *Int J
  Sports Med* 39(10):737–742, whose limits of agreement (about ±40 W) belong
  in the provenance note of every FTP this pass writes.

## Scope

- **In**: the derivation leaf and its three derivations; the `source`
  provenance field on a benchmark entry (an `athlete-benchmarks` amendment);
  the pass and its command; the reconciliation and never-overwrite rules; the
  run report; the citation records; the amendment to `athlete-benchmarks`'
  boundary line.
- **Out**: deriving maximum or resting heart rate (a race maximum is only a
  lower bound and wrist-optical spikes are common — listed as a candidate,
  not a deliverable); any change to channel arithmetic, selection or the
  calculator (`threshold-load` Req 11 stands); auto-detection of efforts;
  prompting; aggregation over time (`load-history`); fitting
  (`performance-model-fit`); sports other than running and cycling — the pass
  declines them by name.

## Boundary Candidates

- **Derivation leaf** (pure): `(Activity, EffortTag, sufficiency) ->
  derived candidates`, one function per benchmark kind, each with its citation
  and validity gate.
- **Provenance in the store**: the `source` field's shape, parsing,
  serialization, and the never-overwrite rule (`athlete-benchmarks`
  amendment).
- **The pass**: document discovery, archive resolution, reconciliation,
  report, command, confinement registration.

## Out of Boundary

- What the calculator does with a derived benchmark — nothing changes there;
  a derived entry is an ordinary dated entry to it.
- Whether a benchmark is stale (`activity-qa-flags` / `athlete-benchmarks`).
- The tag vocabulary (`effort-tags`).

## Upstream / Downstream

- **Upstream**: `effort-tags` (the reader); `athlete-benchmarks` (the store,
  amended for provenance); `training-load` (profile write path; the wave-0
  prompt-date fix is complementary, not a dependency — derived entries carry
  their own dates); `fit-ingest` (streams, `parse_fit`); `load-channels`
  sufficiency rules, reused or mirrored by design decision (their purity guard
  forbids the channels importing anything back).
- **Downstream**: the load pass scores the archive against the derived
  entries with no code change; `performance-model-fit` reuses the
  race-equivalence model for its criterion scale.

## Existing Spec Touchpoints

- **Extends**: `athlete-benchmarks` — `source` on an entry, serializer and
  parser, the boundary line that excluded estimation; `training-load` —
  `with_benchmark` gains the provenance argument.
- **Adjacent**: `threshold-load` (its boundary test pins the calculator's
  allowed imports; this pass must not be reachable from it); `distribution`
  (a new command is a README line); `tests/test_confinement.py` (a new writing
  entry point).

## Constraints

- **Citation discipline is the gate on every number.** Riegel's model,
  exponent and validity window, the two LTHR papers' durations, Coggan's FTP
  definition and the 0.95 factor each land as a `CitedConstant` in a layer
  `sources.py`, with the verification status the evidence supports today —
  secondary attestation for Riegel until the 1981 text is read, and for the
  book page until someone with the book confirms it. No bare numeric literal;
  the existing literal-guard pattern applies to the new module.
- **Derived is not measured.** Provenance is mandatory on every derived entry;
  a user-typed entry always wins; the pass never edits an entry it did not
  write. `athlete.toml` stays plain, readable and editable without fitdocs.
- **Official beats recorded.** A certified distance and chip time from the tag
  take precedence over GPS distance and elapsed time; the fallback is named in
  provenance so a later reader knows which one anchored the number.
- **Validity windows are refusals, not clamps.** A race outside Riegel's
  3.5–230-minute window, an effort shorter than the LTHR window, a power
  stream below coverage — each is declined with its reason. Absent data is
  `None`, never a fabricated value.
- **Determinism and offline**: the same tags, archive and configuration
  produce the same `athlete.toml` bytes; no network, no clock beyond the
  pass's `today`.
- **Data-root contract**: writes only `athlete.toml`, already a permitted
  shared file; the new command registers with the confinement guard.
- No personal data in the repository: fixtures are synthetic activities and
  pages.
