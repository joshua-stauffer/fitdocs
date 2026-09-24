# Brief: channel-merge

## Problem

`activity-identity` gives each session one page, with one base file and
possibly some extras. The athlete's reason for bringing in the extras is the
channels they carry and the base lacks:
- **Runs.** A HealthFit copy (the base: session UUID, full summaries, HR
  laps) plus the Stryd file (form power, air power, leg spring stiffness,
  impact, stance-time balance, the balance channels).
- **Rides.** A Garmin original (the base: power, pedal dynamics, altitude,
  temperature, GPS) plus a HealthFit copy that holds the watch's HR on a
  ride recorded without a chest strap.

Until the page is composed from both files, those channels are archived and
unused.

## Current State

- After `activity-identity`, a page records its base and extras, and renders
  from the base only.
- The model is one `Activity` per file. `Samples` (`src/fitdocs/model.py:97`)
  is index-aligned arrays per channel, widened by `running-dynamics`.
- Nothing composes two decoded activities. The only tolerance logic in the
  codebase is plan matching (`plans/matching.py`), which is unrelated.

Measured alignment (viability check 2026-09-24; three Stryd↔HealthFit pairs
of the same runs):
- All timestamps are whole seconds. Every Stryd timestamp exists in the
  HealthFit copy (5401/5401, 3744/3744, 2373/2373); HealthFit has 2–7 extra
  trailing samples.
- The content is shifted by a lag that changes between pauses. HealthFit's
  Stryd-derived channels (power, vertical oscillation, stance time, speed,
  distance) match Stryd exactly at a lag of +1 s in some stretches and 0 s
  in others (one file: +1, +1, 0, +1, 0). A plain timestamp join puts
  the extras 1 s early for 52–100% of samples.
- HR sits at a different lag again, −1 or 0 s, so it is not an alignment
  key.
- Shared channels differ slightly: step length about 0.8% higher in Stryd,
  cadence ±1.
- Garmin↔HealthFit ride pairs: start identical to the second, distance
  within 5 m. HealthFit's power coverage is about 99% against 100%.

## Desired Outcome

- **One composed activity per page.** It is built from the base plus its
  extras, and is a pure function of the file set: order-independent and
  deterministic.
- **Donation, never override.** An extra contributes a channel only when the
  base lacks it (absent, or entirely `None`). The base wins every channel
  both carry. A stated per-channel rule decides partial coverage (e.g. the
  base has HR for 51% of the ride): leave the base alone, or fill only its
  gaps. The design picks one, states it, and tests it.
- **Correct alignment.**
  - Split each file at pauses (gaps over 1 s).
  - Within each stretch, choose the lag at which a shared, exactly
    reproduced channel (distance or power) matches, and shift the donated
    channels by that lag.
  - When no shared channel establishes a lag, fall back to exact
    timestamps and state the fallback on the page.
  - Samples the base does not have are not invented. Donated values land
    only on the base's timeline.
- **Visible provenance.** The page states which file each shown channel came
  from, in the coverage table or a sources section.
- **Summaries follow the channels.** A summary that a donated channel feeds
  is computed from the composed samples; for example, average form power,
  or average HR on a ride whose base lacked it. Session-level values the
  base carries are not replaced.
- **Laps stay the base's.** Laps come from the base file. An extra's laps
  are ignored, and the design says so.
- **Regen reproduces it.** Rebuilding from the archive yields the same
  composed page.

## Approach

A pure composition module takes the decoded base and extras with their
roles and returns one activity plus a channel-provenance map. The stretch
segmentation, lag estimation and donation are separate, individually
mutation-tested functions. `_process_file` calls it when the page has
extras, reading each extra from the archive. Rendering takes the provenance
map for the coverage section.

## Scope

- **In**:
  - composition;
  - segmentation and lag estimation;
  - the donation rules, including partial coverage;
  - the provenance map and its rendering;
  - summary recomputation for donated channels;
  - the engine and regen wiring;
  - the doc-version bump, and any managed key for provenance (wiki-contract
    Amendment 4);
  - goldens.
- **Out**:
  - deciding which files form a set, or which is base
    (`activity-identity`);
  - new channels (`running-dynamics`);
  - averaging or blending two values of one channel;
  - composing files from different sessions;
  - lap merging.

## Boundary Candidates

- Segmentation and lag estimation (pure).
- Donation rules (pure, per channel).
- Provenance and summaries.
- Engine and render wiring.

## Out of Boundary

- The match rule and roles (`activity-identity`).
- Channel definitions and decoding (`running-dynamics`, `fit-ingest`).
- Load: the load pass reads the composed page as it reads any page. A
  donated power channel on a base without power is a real change to what
  load can score, and the design must say so.

## Upstream / Downstream

- **Upstream**: `activity-identity` (roles, archive refs); `running-dynamics`
  (the channel set, the developer-field reader); `fit-ingest`;
  `workout-docs`.
- **Downstream**: the load pass, `activity-qa-flags` and `load-history` read
  composed pages; a future push connector posts text drawn from composed
  pages.

## Existing Spec Touchpoints

- **Extends**:
  - `workout-docs`: provenance on the page;
  - `wiki-contract`: a provenance key, if one is chosen, and the version;
  - `training-load` and `threshold-load`: no code change, but a donated
    power or HR channel changes which channels a page can be scored on, so
    the load-channel sufficiency rules must be checked against composed
    pages.
- **Adjacent**: `activity-qa-flags` (flags evaluated on the composed
  channels); `route-maps` (position comes from the base; a base without GPS
  can take an extra's position only if the design allows position as a
  donated channel, and says so).

## Constraints

- **Order independence and determinism.** The same files give the same page
  bytes.
- **Absent is `None`.** A donated channel's gaps stay gaps. A lag that
  cannot be established is stated, never guessed silently.
- **Fixtures are synthesized pairs** reproducing the measured lags (per
  stretch +1/0), the HR offset, the trailing extra samples and the
  step-length bias. No personal files.
- **Named mutations**: a single global lag instead of per-stretch, donating
  a channel the base has, aligning on HR, or letting an extra's laps through
  must each turn a test red.
- **No new runtime dependencies.**
