# Requirements Document

## Project Description (Input)

Every threshold-anchored load number is only as good as the threshold behind
it. The "1 hour at threshold = 100" scale that makes load comparable across
disciplines requires a *per-discipline*, *current* benchmark: a running FTP, a
cycling FTP, an LTHR, a threshold pace. fitdocs has nowhere to put them.

Two stores exist today and neither can hold this. `athlete.toml` is read
optionally into the fit-ingest athlete-inputs contract — flat, read-only by
construction (fit-ingest Req 8.3: never creates the file, never prompts, writes
nothing on any path), with no discipline scoping and no dates. A second,
writable store driven by declared athlete fields and the prompt flow persists
what prompting collects, under methodology-scoped keys. So one path is
read-only and undated, the other is writable and methodology-scoped, and
neither knows what discipline a threshold belongs to or when it was measured.

This feature delivers a single reconciled benchmark store: per-discipline
thresholds, each with the date it was measured, readable without fitdocs
installed and writable through the existing prompt flow; date-aware selection
so scoring a 2023 activity picks the benchmark that was current in 2023;
staleness computed against the activity's own date rather than today's; and an
explicit schema version so later shape changes are migrations rather than
silent misreads. Absent means absent — a missing benchmark yields nothing and
the dependent channel reports insufficiency; it never falls back to a default
FTP.

Source: `.kiro/specs/athlete-benchmarks/brief.md`; Phase 4 scope, discovery
decisions and boundary strategy in `.kiro/steering/roadmap.md`.

## Introduction

athlete-benchmarks is the first spec of the Phase 4 threshold load engine. It
owns the **benchmark store**: what a benchmark is, where it lives, how it is
validated, which one applies to a given activity, and how old it was when that
activity happened. Everything downstream — the per-channel load math, the
`threshold` calculator's selection policy, the QA flag layer — anchors on the
values this store hands out, so the store must be exact about three things the
current profile cannot express at all: **discipline**, **measurement date**,
and **absence**.

Discipline matters because a running FTP and a cycling FTP are different
numbers for the same athlete. Measurement date matters because the athlete's
runs cross a measurement-system boundary (Apple Watch native running power
through 2024, Stryd from 2026): a running FTP measured on Stryd applied
retroactively to Apple Watch runs mis-scales years of history. Absence matters
because a fabricated default FTP produces a confident, wrong number that looks
exactly like a right one.

Three principles govern every requirement below. A benchmark that is not on
file yields nothing — never a default, never a substituted value from another
discipline. A benchmark that exists but was measured after the activity is not
applicable to it — unless the athlete has declared, on that entry, that it
stands in for earlier activities (Amendment 1). And a file that exists but is
malformed fails loudly and names the offending entry, because silently
dropping a threshold would change computed load invisibly.

## Boundary Context

- **In scope**: the versioned per-discipline benchmark schema carried in the
  data root's `athlete.toml`; validation and loud failure on malformed input;
  the measurement date on every benchmark; date-aware selection of the
  benchmark applicable to a given activity; staleness computation against a
  configured window; the staleness window as one user-configurable **key**
  (`benchmark_staleness_days`) contributed to the settings file's `[load]`
  table; the reconciliation of today's read-only reader and the writable
  prompt-driven store onto that one file, including the persistence of prompted
  benchmark answers; and the benchmark queries added to the access contract
  through which a calculator reaches a benchmark by discipline and date.
- **Out of scope**: rendering the staleness flag or any benchmark into a
  document (activity-qa-flags owns surfacing); auto-FTP / eFTP estimation of
  any kind — `performance-benchmarks` performs that estimation and hands
  this store ordinary dated entries (Amendment 2); this store performs no
  estimation or inference of its own; any load math whatsoever — no TSS, no
  HRSS, no channel logic, no channel selection; zone-definition changes (the
  shipped zone-divider contract is unchanged); changes to the questions the
  prompt flow asks or how it asks them; what a stale benchmark *means* for a
  rendered document or a load value — this feature reports the fact and
  does not decide the consequence; interpreting or aggregating benchmarks
  over time (trend analysis, CTL/ATL).
- **Not owned by this spec** (stated plainly so the boundary does not drift):
  - The `[load]` settings **reader module** (`src/fitdocs/load/settings.py`) —
    `training-load` owns it, including the `LoadSettings` dataclass, the reader
    function name and the error type. This feature adds one field and one key
    to it and never creates a second reader.
  - The `LoadCalculator.compute` signature and the per-pass calculator context
    that carries the activity date and the resolved settings — `training-load`
    owns both. This feature supplies the values that context carries; it does
    not define the type.
  - The document-contract module (`src/fitdocs/contract.py`) and its test
    module — `wiki-contract` owns the frontmatter key set and its pure-reader
    set, and `training-load` task 4.1 lands the one reader this feature needs
    (`document_date`). This feature specifies and consumes that reader; it adds
    it only as the documented fallback, if task 4.1 has not landed first.
  - The profile store's non-benchmark lifecycle, the registry, arbitration,
    document surgery and the load report vocabulary — `training-load`.
- **Adjacent expectations**: fit-ingest supplies the athlete-inputs contract
  read from `athlete.toml` today, and its read-only invariant (never creates,
  never prompts, writes nothing) must survive this feature intact — the write
  path stays in the load layer. The shipped settings file is read once per
  invocation and an absent settings file yields no configuration rather than an
  error; this feature's `[load]` key inherits that behavior. training-load owns
  the profile store, the declared-field prompt flow, the `[load]` reader and the
  calculator access contract that this feature extends; load-channels,
  threshold-load and activity-qa-flags consume this store and are not specified
  here. wiki-contract owns the document-contract module this feature adds a date
  reader to. The ownership contract already treats `athlete.toml` as user-owned
  rather than tool-owned, and this feature does not change that.

## Amendment 1 (2026-09-10): retroactive application of a prompt-answered benchmark

Queue item `2026-08-27-prompt-date-strands-historical-documents`, ruled by the
maintainer on 2026-08-29 (*extend the design to handle past dates*) and taken
up as roadmap Phase 6 wave 0 under `training-load` Amendment 4, which records
the decision and its rejected alternatives in full. Only what this spec owns
is restated here.

A prompt answer is recorded as measured on the day it is given (6.2,
unchanged). The load pass may hand this store, alongside that answer, the
athlete's declaration that it also stands in for earlier activities back to a
given date. That declaration is a new optional entry field, **`applies_from`**
— a bare calendar date no later than the entry's `measured_on` — and it
changes three things this store does: what a valid entry is (1.12, 2.11), which
entry applies to an activity that no earlier measurement covers (3.3 revised,
3.10, 3.11), and what staleness reports for an entry measured after the
activity (4.6 revised). The write path carries the field like the note (6.10),
and the question itself stays `training-load`'s (8.8).

The principle "a benchmark measured after the activity is not applicable to
it" is narrowed, not dropped: the *tool* still never applies a later
measurement on its own. Only the athlete's explicit, per-entry declaration
does, and every hand-edited history keeps its meaning — an entry without
`applies_from` behaves exactly as before. The measurement-system case in the
Introduction (a Stryd FTP must not rescale Apple Watch runs) is preserved
because an entry measured on or before the activity always wins over a
retroactive one, whatever their values.

The schema version does not change. A fitdocs older than this amendment
ignores the key (1.10) and merely declines to score activities before the
measurement — a degradation the athlete can see, never a misread number. The
other direction is also deliberate: a file that already carried an
`applies_from` key while it was unrecognized is now validated by 2.11, so an
entry whose stray value falls after its `measured_on` becomes a loud
configuration error rather than being silently preserved.
Nothing is renumbered; the design components named in `training-load`'s
amendment record are amended in place, and the implementing tasks are
`training-load` 7.1 (this leaf module) and 7.2 (the profile store).

## Amendment 2 (2026-09-11): benchmark provenance for a derivation pass

Roadmap Phase 6 Existing Spec Update, taken up by `performance-benchmarks`
task 5.3 (that spec's design § `BenchmarkProvenance` and § Cross-spec
obligations → *performance-benchmarks ↔ athlete-benchmarks (the Existing Spec
Update)*). `performance-benchmarks` turns an athlete's tagged races, tests and
hard efforts into dated benchmark entries and needs a way to record where an
entry came from and, when it was derived, how — a fact this store must
validate, store and hand back, without itself estimating, inferring or
choosing a value.

A benchmark entry gains a new optional field, **`source`** — a provenance
record naming the entry's origin and, for a derived origin, the derivation
detail. `source` is the *fifth* recognized entry field, appended after
Amendment 1's `applies_from`; it neither displaces `applies_from` nor
interacts with it — a derived entry carries no `applies_from` (the deriver
never writes one), so it is tier-1 only in Amendment 1's two-tier
resolution — and it changes nothing about which entry
`BenchmarkSet.applicable` selects or how staleness is computed — those
remain governed by `measured_on` and `applies_from` alone. The origin
vocabulary is closed to exactly two values: `derived`, written only by a
derivation pass, and `measured`, written only by the athlete by hand to
state that a number came from a lab or field test rather than merely being
typed; this store never writes `measured` itself and reads it only as "not
derived." A derived origin additionally requires a non-empty method,
document, inputs and citation; a measured origin requires none of them. Any
other key inside the `source` table is ignored on read, for the same
forward-compatibility reason the store already ignores unrecognized keys
elsewhere (1.10), and is carried through unchanged when the store rewrites
the file. When an automated derivation pass writes to the store, it neither
modifies nor deletes an entry whose `source` is absent or whose origin is
not `derived`, and it does not write a derived entry at a discipline,
quantity and measurement date such an entry already occupies — an automated
write path touches only the entries it itself derived, never a
hand-recorded or measured one; the prompt-driven write path (6.1–6.3, 6.10)
is unchanged by this rule.

The schema version does not change; an older reader ignores the key (1.10)
and simply cannot distinguish a derived entry from a hand-recorded one, a
degradation the athlete can see, never a misread number. The `source` field
is validated by the store but is not part of the entry's natural key
`(discipline, kind, measured_on)`, so it never affects duplicate detection.
Nothing is renumbered. This spec's design is amended only at its Non-Goals
line; the field's component-level design (parser, serializer, merge overlay
and the derived write path) lives in `performance-benchmarks` design §
`BenchmarkProvenance` and § `ProfileDerivedWrite`, and the implementing
tasks are that spec's 2.1–2.3.

## Requirements

### Requirement 1: Versioned Per-Discipline Benchmark Schema

**Objective:** As an athlete, I want my thresholds recorded per discipline with
the date each was measured, in one plain-text file I can read and edit without
fitdocs installed, so that every load number is anchored to a benchmark that
actually belongs to that sport and that point in time.

#### Acceptance Criteria

1. The fitdocs athlete store shall record benchmarks in the data root's `athlete.toml` file, and shall not introduce a second or additional benchmark file.
2. The fitdocs athlete store shall support a benchmark for each of the following quantities: functional threshold power in watts, lactate threshold heart rate in beats per minute, threshold pace in seconds per kilometre, maximum heart rate in beats per minute, and resting heart rate in beats per minute.
3. The fitdocs athlete store shall scope threshold power, threshold heart rate and threshold pace benchmarks to a named discipline drawn from the sport vocabulary fitdocs already uses, and shall scope maximum and resting heart rate to the athlete as a whole rather than to a discipline.
4. The fitdocs athlete store shall record, for every benchmark, a measurement date expressed as a calendar date with no time and no time zone, and shall accept an optional free-text note alongside it.
5. The fitdocs athlete store shall accept more than one dated measurement for the same discipline and quantity, so that a benchmark history is expressible rather than only a current value.
6. The `athlete.toml` file shall carry an explicit schema version identifier so that later shape changes are detectable.
7. If `athlete.toml` declares a schema version the installed fitdocs does not recognize, the fitdocs CLI shall fail with an instructive configuration error naming the file and the declared version, and shall not read any part of the file's contents as benchmarks.
8. If `athlete.toml` carries no schema version identifier, the fitdocs athlete store shall treat the file as the earliest schema version and shall read any benchmarks present in it normally.
9. If `athlete.toml` does not exist, the fitdocs athlete store shall report no benchmarks and shall not treat this as an error.
10. The fitdocs athlete store shall ignore keys and tables in `athlete.toml` that it does not recognize, so that files written by a later fitdocs version within the same schema version remain readable.
11. The fitdocs athlete store shall leave the existing flat athlete-input keys — the ones the document renderer consumes for zones and threshold-dependent metrics — readable with unchanged meaning, and shall not derive, override or reinterpret them from benchmarks.
12. _(added by Amendment 1)_ The fitdocs athlete store shall accept, on any benchmark entry, an optional applies-from calendar date no later than the entry's measurement date, expressing the athlete's declaration that the measurement also stands in for activities dated on or after that date which no earlier-measured entry covers; an entry without one applies from its measurement date only, exactly as before.
13. _(added by Amendment 2)_ The fitdocs athlete store shall accept, on any benchmark entry, an optional source provenance record naming the entry's origin as either "derived" or "measured" and, when the origin is "derived", the derivation method, the document it was derived from, the inputs it used, and a citation key; this is the fifth recognized entry field, appended after applies-from, and it neither displaces applies-from nor changes which entry is selected or how staleness is computed.

### Requirement 2: Loud Validation of Benchmark Data

**Objective:** As an athlete who hand-edits the profile file, I want a
malformed benchmark to stop the run with a message naming exactly what is
wrong, so that a typo never silently changes a computed load or vanishes from
the file.

#### Acceptance Criteria

1. If a benchmark entry's value is missing, is not a number, or is a boolean, the fitdocs CLI shall fail with a configuration error naming the file, the discipline, the quantity and the offending value.
2. If a benchmark entry's value is zero, negative, or not a finite number, the fitdocs CLI shall fail with a configuration error naming the file and the offending entry.
3. If a benchmark quantity that is recorded in whole beats per minute is given a fractional value, the fitdocs CLI shall fail with a configuration error rather than rounding or truncating it.
4. If a benchmark entry's measurement date is missing, is not a calendar date, or carries a time or time-zone component, the fitdocs CLI shall fail with a configuration error naming the file and the offending entry.
5. If a benchmark is recorded under a discipline name that is not a recognized sport, the fitdocs CLI shall fail with a configuration error naming the offending name and listing the recognized ones.
6. If a discipline-scoped quantity is recorded in the athlete-wide scope, or an athlete-wide quantity is recorded under a discipline, the fitdocs CLI shall fail with a configuration error naming the quantity and the scope it belongs in.
7. If two benchmark entries share the same discipline, quantity and measurement date, the fitdocs CLI shall fail with a configuration error naming the duplicated date, and shall not choose one of them.
8. If the benchmark section of `athlete.toml` is structurally wrong — a scalar where a table or a list of entries belongs — the fitdocs CLI shall fail with a configuration error naming the offending path.
9. When a benchmark validation failure occurs, the fitdocs CLI shall report it as a configuration error and terminate before writing, modifying, or deleting any file.
10. The fitdocs athlete store shall never silently drop, coerce, or substitute a benchmark entry it cannot validate.
11. _(added by Amendment 1)_ If a benchmark entry's applies-from date is not a bare calendar date, carries a time or time-zone component, or falls after the entry's measurement date, the fitdocs CLI shall fail with a configuration error naming the file and the offending entry.
12. _(added by Amendment 2)_ If a benchmark entry's source record declares an origin that is missing, is not a string, or is outside the closed vocabulary "derived" and "measured", the fitdocs CLI shall fail with a configuration error naming the file and the offending entry.
13. _(added by Amendment 2)_ If a benchmark entry's source record declares a "derived" origin without a non-empty method, document, inputs, and citation each, the fitdocs CLI shall fail with a configuration error naming the file, the offending entry, and the missing field; a "measured" origin shall require none of these four.
14. _(added by Amendment 2)_ The fitdocs athlete store shall ignore any key inside a benchmark entry's source record that it does not recognize, so that a source detail a later fitdocs version adds remains readable within the same schema version.

### Requirement 3: Date-Aware Benchmark Selection

**Objective:** As an athlete regenerating years of history, I want each activity
scored against the benchmark that was current when that activity happened, so
that a threshold measured on new hardware in 2026 does not retroactively
rescale my 2023 training.

#### Acceptance Criteria

1. When asked for the benchmark applicable to an activity, the fitdocs athlete store shall consider only entries for the requested quantity and scope whose measurement date is on or before the activity's own calendar date.
2. When more than one entry qualifies, the fitdocs athlete store shall return the one with the latest measurement date.
3. _(revised by Amendment 1)_ When no entry qualifies because every recorded measurement date falls after the activity's date, the fitdocs athlete store shall report no applicable benchmark and shall not return a later-measured one — unless the athlete has declared an entry to apply from a date on or before the activity's, in which case 3.10 governs.
4. When no entry exists at all for the requested quantity and scope, the fitdocs athlete store shall report no applicable benchmark and shall not substitute a value from another discipline, from the athlete-wide scope, or from any default.
5. The fitdocs athlete store shall distinguish "no benchmark of this kind is on file at all" from "benchmarks exist but none applies on that date", so that callers can report the two situations differently.
6. When an activity's calendar date is determined, the fitdocs athlete store shall use the activity's local calendar date — the same date the document is named from — so that a benchmark measured on the day of an activity applies to it regardless of the recording time zone.
7. If an activity has no recorded start time, the fitdocs athlete store shall report no applicable benchmark rather than assuming today's date or any other date.
8. When the same request is repeated with the same file contents and the same activity date, the fitdocs athlete store shall return the same benchmark, so that repeated runs are deterministic.
9. When a benchmark is returned, the fitdocs athlete store shall return its measurement date and note alongside its value, so that a caller can report what the number was anchored to.
10. _(added by Amendment 1)_ When no entry for the requested quantity and scope is measured on or before the activity's date but one or more such entries carry an applies-from date on or before it, the fitdocs athlete store shall return, among those, the entry measured soonest after the activity; it shall never return an entry that carries neither a measurement date on or before the activity nor such an applies-from date, and an entry measured on or before the activity shall always take precedence over a retroactively applied one.
11. _(added by Amendment 1)_ When a benchmark is returned, the fitdocs athlete store shall return its applies-from date, when it has one, alongside its measurement date and note, so that a caller can report that the anchor was measured after the activity and applied by the athlete's declaration.

### Requirement 4: Staleness Computation

**Objective:** As an athlete, I want to know when the benchmark behind a load
number was already old at the time of that activity, so that a confident-looking
number carries the fact that its threshold may no longer have been valid.

#### Acceptance Criteria

1. The fitdocs athlete store shall compute a benchmark's age as the number of days between its measurement date and the date of the activity being scored.
2. The fitdocs athlete store shall report a benchmark as stale when its age at the time of that activity exceeds the configured staleness window, and as current otherwise.
3. While regenerating a document for a past activity, the fitdocs athlete store shall evaluate staleness against that activity's date and not against the current calendar date, so that regenerating an old document does not flag it differently than the original run did.
4. When reporting staleness, the fitdocs athlete store shall report the benchmark's age in days and the window it was compared against, not only a yes/no verdict.
5. The staleness computation shall depend only on the activity date, the measurement date and the configured window, and shall read no files and consult no clock.
6. _(revised by Amendment 1)_ If staleness is requested for a benchmark whose measurement date falls after the activity date, the fitdocs athlete store shall report a negative age in days and a current verdict rather than failing, because an entry the athlete declared to apply retroactively legitimately reaches this computation; the sign of the age is what tells a caller the benchmark was measured after the activity. A staleness window below one day remains a loud failure.
7. The fitdocs athlete store shall report staleness as a fact about the benchmark and shall not alter, suppress, or adjust any benchmark value in response to it.

### Requirement 5: Staleness Window Configuration

**Objective:** As an athlete, I want the window after which a threshold counts
as stale to be a setting rather than a constant baked into the tool, so that I
can match it to how often I actually test.

> **Ownership note.** "The fitdocs settings reader" below means the single
> `[load]` table reader owned by `training-load`. This feature contributes the
> `benchmark_staleness_days` key and the field that holds it; it never creates a
> second reader for that table.

#### Acceptance Criteria

1. The fitdocs settings reader shall read the staleness window from the `[load]` table of the data root's settings file.
2. If the settings file, the `[load]` table, or the staleness-window key is absent, the fitdocs settings reader shall use a documented default window and shall not treat the absence as an error.
3. If the staleness-window value is not a whole number of days, is a boolean, or is zero or negative, the fitdocs CLI shall fail with a configuration error naming the file, the key and the offending value.
4. The fitdocs settings reader shall ignore keys in the `[load]` table it does not recognize, so that sibling features can add their own `[load]` settings without this reader rejecting them.
5. When a load pass begins, the fitdocs CLI shall validate the `[load]` table and, on a configuration error, terminate before any document is written or modified.
6. The fitdocs settings reader shall consume the already-parsed settings document handed to it and shall not open, locate, or re-read the settings file itself.

### Requirement 6: Reconciled Single Store with a Prompt-Driven Write Path

**Objective:** As an athlete, I want the answers I give at the prompt to land in
the same file I hand-edit, with everything else in that file left alone, so
that there is exactly one place my thresholds live.

#### Acceptance Criteria

1. The fitdocs athlete store shall write prompted benchmark answers into the same `athlete.toml` the reader consumes, and shall not create a separate profile file.
2. When a benchmark answer is persisted, the fitdocs athlete store shall record it as a dated measurement whose measurement date is the date the answer was provided.
3. When a benchmark answer is persisted for a discipline and quantity that already has a measurement on that same date, the fitdocs athlete store shall replace that entry rather than adding a second entry with the same date.
4. When the store is written, the fitdocs athlete store shall preserve every key, table and value it does not manage — including the flat athlete-input keys the document renderer consumes and any benchmark history already on file — so that no user- or feature-owned data is lost on rewrite; hand-written comments are not preserved, which is the store's existing documented trade-off.
5. When the store is written, the fitdocs athlete store shall stamp the current schema version into the file.
6. When the store is written, the fitdocs athlete store shall emit benchmark entries for a given discipline and quantity in ascending measurement-date order, so that identical inputs produce an identical file.
7. When the store is written, the fitdocs athlete store shall write the file atomically, leaving no partial or temporary file behind on failure.
8. The fitdocs athlete store shall not write any new flat threshold key when persisting a benchmark; flat keys already present are preserved but never created or updated by this path.
9. If a value fails validation, the fitdocs athlete store shall reject it and persist nothing, leaving the file exactly as it was.
10. _(added by Amendment 1)_ When a benchmark answer is persisted together with an applies-from date, the fitdocs athlete store shall record that date on the same entry, shall refuse one later than the entry's measurement date exactly as it refuses an invalid value (6.9), and on rewrite shall preserve and overlay it exactly as it does the note.
11. _(added by Amendment 2)_ When the store rewrites `athlete.toml`, it shall preserve, on an existing entry's source record, any key it does not recognize, and shall overlay only the recognized source keys onto that record; when a freshly written entry carries no source record at all, the store shall remove any source record already on file for that entry rather than inheriting it — a rule distinct from, and not extended to, note or applies-from.
12. _(added by Amendment 2)_ When an automated derivation pass writes to the store, the fitdocs athlete store shall neither modify nor delete a benchmark entry whose `source` is absent or whose origin is not "derived", and shall not write a derived entry at the discipline, quantity and measurement date such an entry already occupies; the prompt-driven write path (6.1–6.3, 6.10) is unchanged by this rule.

### Requirement 7: Benchmark Access for Load Calculators

**Objective:** As a load-calculator author, I want to ask for a benchmark by
discipline, quantity and activity date directly, so that I never have to encode
structured data in a key string or guess which threshold applies.

#### Acceptance Criteria

1. The fitdocs load-calculator contract shall let a calculator request a benchmark by quantity, scope and activity date, and shall return the applicable benchmark with its value, measurement date and note, or nothing when none applies.
2. The fitdocs load-calculator contract shall let a calculator ask whether any benchmark of a given quantity and scope is on file, independently of whether one applies to a given date.
3. The fitdocs load-calculator contract shall expose the configured staleness window to calculators through the per-pass calculator context's resolved settings rather than through the profile view, so that a calculator can evaluate staleness without reading configuration itself.
4. The fitdocs load-calculator contract shall continue to provide access to non-benchmark numeric profile values addressed by key, so that methodology-scoped fields remain supported.
5. The fitdocs load-calculator contract shall express discipline and date as explicit arguments and shall not encode them inside profile key strings.
6. The published fitdocs plugin surface shall include the benchmark types a calculator needs to consume this contract, and the test that pins that surface shall be updated to the new shape.
7. When a calculator requests a benchmark that is absent, the fitdocs load-calculator contract shall return nothing rather than raising, so that absence is an ordinary outcome a calculator handles by declining to compute.

### Requirement 8: Prompting for Missing Benchmarks

**Objective:** As an athlete running a sync, I want fitdocs to ask once for a
threshold it needs and never nag me again, so that filling in a benchmark is a
single answer rather than a question repeated for every historical activity.

#### Acceptance Criteria

1. The fitdocs prompt flow shall accept benchmark quantities as declarable athlete inputs, using the same declaration-driven mechanism as non-benchmark fields.
2. When a calculator declares a required benchmark and no benchmark of that quantity and scope is on file, the fitdocs CLI shall prompt for it during an interactive load pass.
3. When a benchmark of the declared quantity and scope is already on file, the fitdocs CLI shall not prompt for it again, even when no entry applies to the activity being processed.
4. If no benchmark applies to the activity being processed but one exists on file, the fitdocs CLI shall report that activity as not computed with a reason distinguishing it from a benchmark that was never provided, and shall not prompt.
5. If the user declines to provide a prompted benchmark, the fitdocs CLI shall persist nothing, report the reason, and shall not substitute any value.
6. While running non-interactively, the fitdocs CLI shall not prompt for a benchmark, shall leave affected documents uncomputed with the reason reported, and shall complete the pass cleanly.
7. When a prompted benchmark answer is accepted, the fitdocs CLI shall persist it immediately, so that a later failure in the same run does not lose the answer.
8. _(added by Amendment 1)_ The question by which the fitdocs CLI establishes whether a prompted answer also applies to earlier activities is `training-load`'s (its criteria 3.7–3.9); this store persists whatever applies-from date that flow hands it and asks nothing itself.

### Requirement 9: Store Invariants and Data-Root Contract

**Objective:** As a fitdocs user whose profile file is mine to own, I want the
tool's read path to stay strictly read-only and the file to stay plain, local
and hand-editable, so that fitdocs never surprises me by creating or rewriting
data I did not ask it to touch.

#### Acceptance Criteria

1. The fitdocs athlete-inputs read path shall remain read-only by construction: it shall never create `athlete.toml`, never prompt, and write nothing on any path.
2. The fitdocs athlete store shall create or modify `athlete.toml` only as the result of an answer the user provided.
3. The `athlete.toml` file shall remain valid, human-readable plain text whose benchmark entries are understandable without fitdocs installed.
4. The fitdocs athlete store shall keep `athlete.toml` in the user's configured data root and shall never read or write a benchmark file inside a code repository.
5. When benchmark data is absent, the fitdocs athlete store shall yield nothing rather than a zero, a default, or a placeholder value, at every point where a benchmark is read.
