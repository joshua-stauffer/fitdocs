# Brief: analytics-derived

## Problem

`analytics-index` gives agents the raw facts as SQL tables: activities,
laps, sets, per-second records and zone times. Four kinds of question are
still expensive or wrong to answer from those tables alone:

- **Best efforts.** "Best 20-minute power this year" over the records table
  means a rolling window over about 9 million rows, and the window has to
  handle pauses correctly. An agent writing that SQL by hand will get pauses
  wrong.
- **Fitness, fatigue and form.** Load-history's series is exponentially
  weighted (`history/model.py`). Plain SQL can't express that cleanly, and a
  hand-rolled recursive query would be a second implementation that
  disagrees with the history page.
- **Thresholds in force on a date.** FTP, LTHR, threshold pace and max or
  resting HR live in `athlete.toml` with `measured_on` and `applies_from`
  dates. The index doesn't hold them, so nothing joins a workout to the
  thresholds it was done at.
- **Plan compliance.** Training blocks, their mesocycles and planned
  workouts, and their reconciliation against logged workouts, exist only as
  rendered `blocks/` pages.

## Current State

- **Mean-max:** no code exists. The only rolling primitive is NP's
  `_trailing_rolling_mean` (`src/fitdocs/metrics/power.py:187`).
  `performance/models.py` has `time_weighted_mean`.
- **Daily load:** `history/series.py` builds `DayLoad` (:356),
  `DailySeries` (:383) and `WeekRow` (:513), with the Banister model in
  `history/model.py`. Everything is recomputed from frontmatter on every
  `fitdocs history` run, and the methodology comes from
  `[history].methodology` or `[load].default_calculator`.
- **Benchmarks:** `benchmarks.py:125` defines the benchmark kinds, each with
  `measured_on`, `applies_from` and `source`. They're stored in
  `athlete.toml` (`load/profile.py:448`, `:469`), and derived values come
  from `performance/derive.py`.
- **Plans:** `plans/model.py` has `Block` (:346), `Mesocycle` (:98) and
  `PlannedWorkout` (:53). Resolution is in `plans/resolution.py:41`, and
  `LoggedWorkout` in `plans/corpus.py:98`. Plan sources are athlete-owned,
  under the data root's `plans/` (read-only, `layout.py:389`).
- `analytics-index` (upstream) defines the store, the schema version and the
  producer seam this spec registers through.

## Desired Outcome

Four producers registered through `analytics-index`'s producer seam. Each
fills its own tables, which are updated by the same reconciling pass and
rebuilt by the same `fitdocs index --rebuild`:

1. **Mean-max curves (per page).** For each workout page, the best average
   power, speed and heart rate over a stated set of durations, computed from
   the composed activity (base plus donated channels). The duration set,
   the pause and gap rule, and whether a window may span a pause are
   decided, stated and tested once. A channel the activity lacks yields no
   rows, never zeros.
2. **Daily load series (corpus level).** For each day and methodology:
   load, fitness, fatigue and form, plus the weekly rows. These are
   produced by the same code `fitdocs history` uses, so a value in the index
   always equals the one on the history page for the same inputs.
3. **Benchmark timeline (corpus level).** Every benchmark in `athlete.toml`
   with its kind, value, unit, `measured_on`, `applies_from` and source. It
   lets a query join a workout to the thresholds in force on its date.
4. **Training blocks (corpus level).** Blocks, mesocycles and planned
   workouts, with each planned workout's resolution against logged pages, as
   `plan-resolution` decides it today.

Each table carries its units and meaning in schema comments, so
`analytics-query`'s introspection explains it without a separate doc.

## Approach

**One computation, two projections.** Every corpus-level producer calls the
owning engine's existing computation: history's series builder, the profile
reader, plan resolution. It never re-derives. The index is one more place
the same numbers land. Mean-max is the one new computation, and it lives in
`fitdocs.metrics` as a pure function over `Samples` so a future document
section can reuse it.

Corpus-level producers fingerprint their inputs. For example: every page's
load keys plus the history settings, `athlete.toml`'s benchmark tables, or
the plan sources plus the logged-workout projection. Each recomputes only
when its fingerprint moves. Recomputing a corpus table replaces it whole.

## Scope

- **In**:
  - the four producers and their tables;
  - the mean-max function in `fitdocs.metrics`, with its duration set and
    pause rule;
  - input fingerprints for each corpus-level producer;
  - schema comments for every new table and column;
  - the schema-version advance these tables need;
  - test fixtures that pin each table against the owning engine's own
    output.
- **Out**:
  - the store, the location, the reconciling pass and the producer seam
    itself (`analytics-index`);
  - the query command, the sandbox and the agent skill (`analytics-query`);
  - a mean-max section in the workout documents (a follow-on);
  - new load or fitness methodologies;
  - forecasting form from a plan (still deferred, `product.md`).

## Boundary Candidates

- Mean-max as a pure metric function in `fitdocs.metrics`, separate from its
  producer.
- Corpus-level producers as thin adapters over history, profile and plan
  code.
- Input fingerprinting for corpus-level tables.

## Out of Boundary

- Changing what history, derive-benchmarks or plan compute. If a producer
  needs an engine function exposed, it's exposed without changing behavior.
- Reading the index from any existing pass. The documents stay the truth
  (discovery decision, 2026-10-04).

## Upstream / Downstream

- **Upstream**:
  - `analytics-index`: the store, the schema version and the producer seam;
  - `load-history` (series builder), `performance-benchmarks` and
    `athlete-benchmarks` (profile and benchmark model), `training-blocks`
    and `plan-resolution` (block model and resolution);
  - `channel-merge` (composed activity for mean-max).
- **Downstream**:
  - `analytics-query`'s agent skill, which names these tables in its worked
    examples once both have landed;
  - a possible mean-max document section.

## Existing Spec Touchpoints

- **Extends**: none. Engine functions it needs are exposed without changing
  behavior. If one can't be, that becomes an amendment to its owning spec,
  recorded in the roadmap.
- **Adjacent**: `load-history`, `plan-resolution`, `performance-benchmarks`
  (must not duplicate their computations); `analytics-index` (must not
  reshape the core tables).

## Constraints

- Absent data is NULL, never 0. A curve point the activity can't support,
  such as a 2-hour window in a 40-minute ride, is absent.
- A table must match the owning engine exactly: the history page, the
  benchmark store and the block page. Tests pin the index against the
  engine's own output for the same fixture, not against the index itself.
- Deterministic row content for the same inputs.
- The schema version advances by one per lander. If `analytics-query` lands
  between this spec and `analytics-index`, it doesn't change the schema.
