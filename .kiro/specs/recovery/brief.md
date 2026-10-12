# Brief: recovery

## Problem

The athlete can see training load: fitness, fatigue and form on the history
page. They cannot see whether the body is absorbing that load. The signals
that answer it live outside workouts: resting HR, HRV, sleep and, for some
platforms, stress or body battery. A raw daily value means little on its
own. An HRV of 45 ms is high for one person and low for another, and the
nightly noise is large. A useful view puts each signal against the
athlete's own baseline and normal range, beside the load that might explain
it.

## Current State

- **The history page** (`fitdocs history`, `history/engine.py:394`).
  - It builds a contiguous daily load series from workout-page frontmatter
    (`history/series.py:31-49`).
  - It computes fitness, fatigue and form with the Morton/Banister recursion
    (`history/model.py:1-34`).
  - It renders one page and one SVG in a fixed section order
    (`history/page.py:643-706`).
  - load-history pins that the series is built only from workout documents
    (Req 1.1, `requirements.md:102`).
  - It pins "no zones, no readiness verdict, no overload warning, and no
    recommendation" (Req 2.11, `:127`).
  - So wellness does not go onto the history page. A separate page leaves
    load-history untouched.
- **Wellness data.** There is none in fitdocs today. `wellness-store` (this
  phase) provides the normalized, source-attributed daily series.
- **Charts.**
  - `chart-kit` is on main (d03e85e).
  - `chart-catalog` is in implementation (2026-10-12). Its `band` (low/high
    with a centre line), `dual-axis` and `calendar-heatmap` kinds are the
    shapes a recovery view needs.
- **Owned locations.**
  - Today: `workouts/`, `history/`, `blocks/`, `fit-archive/`, `.cache/` and
    `.fitdocs/` (`layout.py:133-142`).
  - `dashboards/` arrives with Phase 11 (`CONTRACT_VERSION` "10").

## Desired Outcome

- A fitdocs-owned recovery page, regenerated from the wellness series and
  the workout load series. For each signal it shows:
  - the daily values;
  - the athlete's rolling baseline and normal range;
  - the days that fall outside the range, marked;
  - fitness, fatigue and form on the same time axis.
- Every method is cited on the page, as the history page cites its
  constants.
- The page states what it does not know: days without data, and a source
  change that restarts a baseline.
- The page is descriptive. It gives no advice and no composite readiness
  verdict (maintainer, 2026-10-12).

## Approach

**Descriptive baseline bands** (maintainer, 2026-10-12), over a readiness
verdict and over bare charts.

- **HRV.**
  - The 7-day rolling mean of ln(HRV) is compared with a 60-day normal range
    (the HRV4Training method; Plews et al. 2013, *Sports Med* 43:773, on
    ln-rMSSD rolling means and the smallest worthwhile change).
  - **One baseline per source and metric.** SDNN (Apple) and rMSSD (Garmin,
    Oura, WHOOP, Polar) are never spliced into one series. Even two rMSSD
    sources use different measurement windows (research 2026-10-12).
- **Resting HR**: the daily value against a rolling baseline and range, kept
  per source.
- **Sleep**: duration, and stages where the source carries them, against a
  rolling mean.
- **Other signals** (SpO2, respiration, stress, body battery, weight,
  subjective scores): included only as plain series where present. The
  design decides which earn a section.
- The design picks and cites the exact windows and range multipliers. The
  research flagged the commonly quoted ±0.75 SD and 0.5 × SD as unverified.

## Scope

- **In**:
  - the baseline computations (pure, per source and metric, with absent days
    left absent);
  - the recovery page:
    - its layout, sections and citations;
    - its chart assets, drawn with chart-kit and chart-catalog kinds;
  - the command or pass that writes it, and when it is refreshed after the
    drain and regen (the design decides; mirror history);
  - the new owned location and declared directory (a wiki-contract
    amendment), and the `CONTRACT_VERSION` bump (main + 1 at landing);
  - an index table of baselines, if the design finds agents need it. It must
    equal the page's computation (analytics-derived rules,
    `requirements.md:169-206`);
  - the no-network list, the writing-entry-point guard, docs and the
    packaged skill.
- **Out**:
  - a readiness score, status label, training recommendation or overload
    warning;
  - wellness on the history page (load-history Req 1.1 and 2.11 stand);
  - morning-of blocks on workout pages (`workout-wellness`);
  - derived benchmark values (`hr-derivation`), though the page may plot
    them;
  - writing into athlete-owned daily notes (`daily/` in the maintainer's
    PKM). fitdocs never edits an athlete-owned page outside its declared
    regions.

## Boundary Candidates

- Baselines: a pure library that `workout-wellness` consumes.
- The recovery page renderer and its assets.
- Owned-location and contract plumbing.

## Out of Boundary

- Parsing, merging or storing wellness (`wellness-store`).
- The load model. Recovery reuses history's series and model functions; it
  never recomputes them differently and never reads the history page.

## Upstream / Downstream

- **Upstream**:
  - `wellness-store` (the series);
  - `load-history` (series and model functions, consumed rather than
    re-implemented);
  - `chart-kit` and `chart-catalog` (kinds);
  - `wiki-contract` (owned locations).
- **Downstream**:
  - `workout-wellness` (consumes the baselines);
  - `dashboards` (charts of the index tables);
  - the packaged skill.

## Existing Spec Touchpoints

- **Extends**:
  - `wiki-contract`: an amendment adding the recovery location and page type
    and bumping `CONTRACT_VERSION`;
  - `connectors`: an amendment adding the command to the no-network list.
- **Adjacent**:
  - `load-history` (no change to its page);
  - `chart-catalog` (consume its kinds; append a shared-layer extension only
    if a kind proves the need);
  - `analytics-derived` (an optional baselines table).

## Constraints

- Absent data is `None`, never 0. A gap stays a gap in every chart and
  baseline.
- A source switch restarts that source's baseline. The page says so, rather
  than drawing one continuous line through it.
- Determinism:
  - same inputs, same bytes;
  - the run date never enters the page (Phase 11's rule against daily
    churn);
  - an "as of" date is the last day with data.
- Dark-mode-safe charts, through chart-kit's theme mechanism.
- No network, no new runtime dependency.
