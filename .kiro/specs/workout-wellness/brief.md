# Brief: workout-wellness

## Problem

When the athlete reads a workout, the questions after "how did it go?" are:
- "what state was I in?" — slept five hours, resting HR up 6 bpm, HRV below
  the normal range;
- "was it the legs or the day?"

Today the workout page knows nothing about the day around the workout. The
answer sits in another app.

## Current State

- Workout pages are rendered by the drain, `sync` and `regen` from archived
  `.fit` files.
  - `DOC_VERSION` is 9 (`contract.py:183`). `CONTRACT_VERSION` is "9"
    (`:328`), moving to "10" with Phase 11 `dashboards`.
  - Regions such as notes and the load payload `fitdocs-load:v2`
    (`load/render.py:1-16`) are carried across re-renders.
- A page is re-rendered when its sources change, and always on `regen`.
  Nothing re-renders a page because data about its *day* arrived later.
  - Wellness for the morning of a workout often lands after the workout's
    file. HealthFit syncs the previous day's HRV "every morning after 9 AM"
    (research 2026-10-12).
  - An intervals.icu pull can bring weeks of backfill at once.
- `wellness-store` (this phase) provides the series. `recovery` (this phase)
  provides the per-source baselines and normal ranges.

## Desired Outcome

- Each workout page carries a small, fitdocs-owned morning-of block for the
  workout's local date:
  - that morning's resting HR and HRV, each against the athlete's baseline
    and normal range for that source;
  - the previous night's sleep (duration, and stages where present);
  - any other signal the design chooses.
- With no wellness for the date, the block is omitted or states that
  plainly. It never shows a 0.
- The page updates when the wellness for its date arrives or changes,
  without a full `regen`.

## Approach

- **The block is rendered from the series and the baselines at page-render
  time.** It reads neither the analytics index nor the recovery page.
- **Re-render on wellness change.** Each page carries the fingerprint of the
  wellness inputs it used: the day's merged values and the baseline state for
  that day. The wellness ingest pass, or a pass chained after it, re-renders
  exactly the pages whose fingerprint moved.
  - The design must bound the cost. One backfill import can touch every
    page from 2018 on: about 2,500 pages for the maintainer.
  - The design must make that one pass, not one pass per day.
- **A `DOC_VERSION` bump** (main + 1 at landing). The block changes every
  page's bytes once.

## Scope

- **In**:
  - the block's content, placement in the section order, wording and
    frontmatter keys (if any);
  - the wellness fingerprint on a page;
  - the targeted re-render pass;
  - a workout-docs amendment (section and frontmatter);
  - a wiki-contract amendment if a frontmatter key or region is added;
  - the `DOC_VERSION` bump;
  - docs and goldens.
- **Out**:
  - computing baselines, which is consumed from `recovery`;
  - the series and merge (`wellness-store`);
  - any verdict or advice ("you should rest"). The block is descriptive,
    like the recovery page;
  - wellness in the index's activities table. An agent joins
    `wellness_daily` (`wellness-store`) by date instead.

## Boundary Candidates

- Block rendering: a pure function of the date, the series and the baselines.
- The wellness fingerprint and the targeted re-render pass.
- Contract and `DOC_VERSION` plumbing.

## Out of Boundary

- The recovery page and baseline methods (`recovery`).
- Any change to load, zones or benchmarks.

## Upstream / Downstream

- **Upstream**:
  - `wellness-store`;
  - `recovery` (the baselines library);
  - `workout-docs` (page structure);
  - `wiki-contract`;
  - `activity-identity` (the page's local date).
- **Downstream**: the analytics index re-fingerprints re-rendered pages
  through its existing post-pass.

## Existing Spec Touchpoints

- **Extends**:
  - `workout-docs`: an amendment for the morning-of section;
  - `wiki-contract`: an amendment if a key or region is added.
- **Adjacent**:
  - `recovery`;
  - `analytics-index` (the post-pass picks up re-rendered pages as it does
    today).

## Constraints

- **"Morning of" needs a day-boundary rule.** It is the workout's local date,
  but sleep spans midnight and sources assign nights differently: Garmin
  `calendarDate` against sleep start, and Apple's overlapping stage segments.
  The rule is set once, in `wellness-store`'s model, and consumed here.
- Determinism: same inputs, same bytes, and no clock reads.
- **Re-render churn** lands in the athlete's git and iCloud wiki. The block
  changes a page only when its own day's inputs change.
- No network, no new runtime dependency.
