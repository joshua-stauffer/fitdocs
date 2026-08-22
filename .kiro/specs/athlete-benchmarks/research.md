# Research & Design Decisions — athlete-benchmarks

## Summary

- **Feature**: `athlete-benchmarks`
- **Discovery Scope**: Extension (integration-focused discovery against a fully
  implemented `training-load` / `fit-ingest` tree)
- **Key Findings**:
  - The brief's mental model ("`athlete.py` is the read path, `load/profile.py`
    is the write path") does not match the implemented tree: **both modules
    read `<data_root>/athlete.toml` today**, and the type calculators actually
    see is `AthleteProfile` (`load/profile.py`), which structurally implements
    `ProfileView`. The reconciliation must therefore be *one file, one parser,
    one writer* — not a read/write split by module.
  - `tomllib` decodes a bare TOML date (`2026-03-14`) to a native
    `datetime.date`, and `tomli_w` — already used by `save_profile` — round-trips
    it. Nothing in `src/` currently validates a date-typed config value, so this
    feature establishes the first date validator. No third-party date library is
    needed.
  - There is a latent prompt-loop defect in any naive date-scoped design:
    `collect_missing_fields` skips a field when its value is *present*. If
    presence were evaluated date-scoped, every pre-benchmark historical activity
    would re-prompt and append a duplicate measurement. Presence (for prompting)
    and applicability (for scoring) must be two different questions.

## Research Log

### Implemented-code survey: who reads and writes `athlete.toml`

- **Context**: The roadmap seam says `athlete.toml` is "read-only by
  construction today while `load/profile.py` writes a separate prompt-driven
  store", and requires Phase 4 to reconcile the two rather than add a third.
  The reconciliation has to be designed against the real tree.
- **Sources Consulted**: `src/fitdocs/athlete.py`, `src/fitdocs/load/profile.py`,
  `src/fitdocs/load/engine.py`, `src/fitdocs/load/prompts.py`,
  `src/fitdocs/load/types.py`, `src/fitdocs/cli.py`, `src/fitdocs/settings.py`,
  `src/fitdocs/layout.py`, `src/fitdocs/metrics/types.py`,
  `tests/test_public_api.py`.
- **Findings**:
  - `athlete.ATHLETE_FILE == "athlete.toml"` and
    `profile.PROFILE_FILENAME == "athlete.toml"` — the *same file*. It is not
    a separate store; `profile.py`'s docstring already states this and commits
    to preserving keys it does not manage (Req 2.5).
  - `engine.apply_load` loads both up front (`athlete.py:210`, `profile.py:211`)
    and threads the `AthleteProfile` document-by-document, persisting each
    accepted answer through `save_profile` (`engine.py:381-386`).
  - `AthleteFileError` and `ProfileError` are both members of the engine's
    `_CONFIG_ERRORS` tuple and both are caught by the CLI's `_run_load_pass`
    → `_config_error` → exit code 2, always before anything is written.
  - `AthleteInputs` (`metrics/types.py`) is consumed by `compute_metrics`
    (intensity factor, time-in-zone, TRIMP, power TSS) and carried on
    `DocContext`. It is pinned by name in the strict root `__all__` check of
    `tests/test_public_api.py`; `fitdocs.load.__all__` is only *inclusion*
    checked, so adding names there is cheap while adding to the root is not.
  - Per-table settings readers all take the already-parsed document:
    `tile_settings_from_document(document, path)`,
    `load_plugin_settings(document, settings_file)`,
    `load_inbox_settings(document, *, data_root)`. `SettingsError` is the
    file-level base type that per-table error types subclass.
- **Implications**: the design's reconciliation is (a) one shared benchmark
  parser used by the one store type that exposes benchmarks, (b) a schema-version
  guard in the reader that runs on *every* sync, and (c) `ProfileError`
  subclassing `AthleteFileError` so one file has one catchable voice — the exact
  pattern settings-foundation established for `fitdocs.toml`.

### Date representation and comparability

- **Context**: Constraint from the brief — "Dates must be timezone-unambiguous
  and comparable to activity timestamps."
- **Sources Consulted**: `tomllib` (stdlib) TOML v1.0.0 date-time types,
  `src/fitdocs/layout.py:doc_stem`, `src/fitdocs/render/frontmatter.py:107-110`.
- **Findings**:
  - TOML distinguishes offset date-time, local date-time, local date and local
    time. A **local date** (`2026-03-14`) decodes to `datetime.date` — no time,
    no zone, no ambiguity.
  - fitdocs already treats an activity's *local calendar date* as its canonical
    date: `doc_stem` names documents `YYYY-MM-DD-...` from
    `start_time.astimezone(tz)`, and the renderer emits the same local date as
    the frontmatter `date` key (as a string, deliberately, so YAML never coerces
    it).
  - An activity's `start_time` is a timezone-aware UTC datetime and may be
    `None` (`layout.doc_stem` has an explicit undated branch).
- **Implications**: benchmark dates are `datetime.date`; the activity side of
  every comparison is the activity's **local calendar date in the same time zone
  fitdocs names documents from**. That makes "measured the morning of the ride"
  apply to that ride, and it makes the comparison total and deterministic. An
  activity with no start time has no calendar date, so it has no applicable
  benchmark (Req 3.7) — consistent with the shipped `undated-` naming branch,
  which already refuses to fabricate a date.

### The prompt-presence vs. applicability split

- **Context**: `collect_missing_fields` (`prompts.py:88-89`) skips a field when
  `profile.get_number(field.key) is not None`. Date-scoped benchmarks break that
  predicate.
- **Findings**: if presence were "is there a benchmark applicable to *this*
  activity", then a data root of 2023 activities with a single 2026-dated FTP
  would prompt on every document, and each accepted answer would append another
  measurement — an unbounded prompt loop that also pollutes the store.
- **Implications**: two distinct predicates, both required by requirements:
  `has_benchmark(kind, discipline)` — undated existence, drives prompting (Req
  8.2, 8.3); `benchmark(kind, discipline, on=date)` — date-scoped applicability,
  drives scoring (Req 3.1-3.4). The gap between them is a first-class reportable
  state (Req 3.5, 8.4), not an error and not a prompt.

### Staleness window default

- **Context**: The brief cites research suggesting an ~8–12 week window and
  requires the window to be configuration, not a constant.
- **Findings**: the range is a coaching heuristic, not a measured constant; the
  research pass also refuted (0-3) the claim that real-time FTP determination
  removes the need for the flag at all, so the flag stays and its window is a
  tuning surface.
- **Implications**: default **84 days (12 weeks)** — the outer end of the range,
  chosen so the default under-flags rather than over-flags; an athlete who tests
  every 8 weeks shortens it in `[load]`. The default is *policy*, not athlete
  data, so it does not violate the "absent data is `None`" rule; a missing
  benchmark still yields nothing, and only the comparison window has a default.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Verdict |
|--------|-------------|-----------|---------------------|---------|
| Current-value-plus-date | One value per discipline/quantity with a sibling `*_measured_on` key | Smallest schema; trivial reader | Cannot express history, so a 2023 activity cannot be scored against a 2023 threshold — defeats the roadmap's date-scoping seam | Rejected |
| Array of dated measurements | `[[benchmarks.<discipline>.<kind>]]` entries, each `value` + `measured_on` + optional `note` | Native TOML array-of-tables; history is expressible; selection is a filter-and-max; hand-editable | Slightly more verbose; requires a duplicate-date rule | **Selected** |
| Separate benchmark file | New `benchmarks.toml` beside `athlete.toml` | Clean separation from legacy flat keys | Adds the third store the roadmap explicitly forbids | Rejected |
| Dotted string keys on the existing `get_number` | `"benchmarks.run.ftp_watts@2026-03-14"` | No contract change | Encodes structured data in strings — the brief forbids it by name | Rejected |

## Design Decisions

### Decision: `benchmarks.py` is a top-level leaf, not a `load/` module

- **Context**: `load/types.py` documents an invariant — it imports no other
  `fitdocs.load.*` module, so the calculator contract stays at the bottom of the
  load chain. The redefined `ProfileView` must name benchmark types.
- **Alternatives Considered**: (1) `src/fitdocs/load/benchmarks.py` — violates
  that invariant the moment `types.py` imports it; (2) define the types inside
  `load/types.py` — mixes a data vocabulary into the plugin contract and makes
  the store depend on the contract module; (3) top-level `src/fitdocs/benchmarks.py`.
- **Selected Approach**: (3). Benchmarks become a top-level fitdocs value
  vocabulary alongside `model.py` and `metrics/types.py`, which is exactly the
  category `load/types.py` already permits itself to import.
- **Trade-offs**: one more top-level module; in exchange the dependency
  direction (`cli → render → load → metrics/model` ) is preserved without
  exception, and `athlete.py` could consume the same vocabulary later without
  importing upward.

### Decision: the parser lives with the value types; callers own the error voice

- **Context**: Two modules read `athlete.toml`. Two parsers would eventually
  disagree about one file.
- **Selected Approach**: `benchmarks.py` exposes one pure parser over an
  already-decoded mapping and raises its own `BenchmarkError`. `AthleteProfile`
  re-raises it as `ProfileError` naming the file. This mirrors the shipped
  pattern in `athlete.py:135-140`, where `ZoneSpec`'s `ValueError` is re-raised
  as `AthleteFileError`.
- **Rationale**: one set of validation rules, one place to test them, and the
  file-level error message still names the file.
- **Follow-up**: `ProfileError` becomes a subclass of `AthleteFileError` so that
  "any `athlete.toml` problem" is one catchable type — the same consolidation
  settings-foundation made for `fitdocs.toml`. Existing `except (ProfileError,
  AthleteFileError, ...)` sites keep working unchanged.

### Decision: the store carries the configured staleness window

- **Context**: A calculator needs the window to judge staleness, but widening
  `LoadCalculator.compute()` is the `training-load` contract update's job, not
  this spec's.
- **Alternatives Considered**: (1) thread `LoadSettings` into `compute()` — owned
  by another spec, and would make this spec block on it; (2) let each calculator
  read `fitdocs.toml` itself — a calculator that reads files breaks the pure
  seam; (3) expose the window on the profile view the calculator already receives.
- **Selected Approach**: (3). `load_profile(data_root, *, staleness_window_days)`
  and a `staleness_window_days` attribute on the `ProfileView` protocol. The
  engine resolves it once from `[load]` and hands it to the store.
- **Trade-offs**: the profile store now carries one policy value alongside
  athlete data. In exchange, no cross-spec contract change is required, the
  `[load]` reader gains a real consumer in this spec (no orphan code), and the
  staleness function itself stays pure.

### Decision: legacy flat keys are frozen, not migrated

- **Context**: `ftp_watts`, `max_hr_bpm`, `resting_hr_bpm` already exist as flat
  keys feeding `AthleteInputs` (zone strip, IF, TRIMP, power TSS in already-
  rendered documents). The same quantities now also exist as dated benchmarks.
- **Alternatives Considered**: (1) derive `AthleteInputs` from benchmarks when
  the flat key is absent — changes shipped rendering behavior and needs an
  activity date the `AthleteInputs` contract does not have; (2) migrate flat keys
  into dated benchmarks on first write — fabricates a measurement date; (3)
  freeze the flat keys.
- **Selected Approach**: (3). Flat keys keep their exact shipped meaning and
  their exact consumer. The benchmark write path never creates or updates a flat
  key (Req 6.8), so the duplication cannot grow, and no rendered document
  changes as a result of this feature.
- **Trade-offs**: an athlete may hold both `ftp_watts = 250` and a dated cycling
  FTP; they serve different consumers and can legitimately differ (one is the
  renderer's zone anchor, the other the load anchor). Recorded as a cross-spec
  risk: a later spec may choose to unify them, and doing so is a document-output
  change that must ride migration-by-regen.

### Decision: duplicate measurement dates are rejected on read and upserted on write

- **Context**: Selection picks the latest `measured_on` on or before the activity
  date. Two entries with the same date make that non-deterministic.
- **Selected Approach**: `(discipline, kind, measured_on)` is the entry key.
  Reading two entries with the same key is a loud configuration error (Req 2.7);
  writing an answer for an existing key replaces that entry (Req 6.3).
- **Rationale**: the read rule makes ambiguity impossible; the write rule keeps
  the read rule reachable — without the upsert, answering twice on one day would
  itself create the malformed file the reader then rejects.

### Decision: reserved `athlete` scope for whole-athlete quantities

- **Context**: FTP, LTHR and threshold pace are per-discipline; maximum and
  resting heart rate are properties of the athlete.
- **Selected Approach**: discipline table names are the lowercase `Sport` values
  fitdocs already uses (`run`, `ride`, `walk`, `hike`, …) plus the reserved token
  `athlete` for whole-athlete quantities. No `Sport` value lowercases to
  `athlete`, so the vocabularies cannot collide. A quantity recorded in the wrong
  scope is a loud error (Req 2.6), and lookup never falls back across scopes.
- **Rationale**: reusing the shipped sport vocabulary avoids inventing a third
  naming system and keeps `[benchmarks.run]` aligned with `layout.sport_slug`.

## Risks & Mitigations

- **Downstream discipline mapping** — Walk and Hike are HR-channel modalities
  with no LTHR of their own unless the athlete records one under those
  disciplines. Mitigation: this spec neither maps nor falls back; the mapping
  from an activity's modality to a benchmark discipline is stated as
  `threshold-load`'s decision and flagged as a cross-spec agreement point.
- **Test churn on the profile store** — eager benchmark parsing in
  `AthleteProfile` and the new `ProfileView` members touch existing test fakes.
  Mitigation: the surface is pre-production and explicitly unpinned by the
  roadmap; tasks call out the fixture updates rather than leaving them implicit.
- **`[load]` table co-ownership** — three sibling specs will add keys to the same
  table. Mitigation: one reader with one error type is established here, and it
  **ignores unrecognized keys** so a sibling's key never trips this reader (Req
  5.4).
- **Clock in the write path** — stamping "today" inside the store would make the
  write path untestable and non-deterministic. Mitigation: the date is resolved
  once at the load-pass entry point and passed down explicitly.

## References

- `.kiro/specs/athlete-benchmarks/brief.md` — problem, scope, constraints.
- `.kiro/steering/roadmap.md` — Phase 4 scope, discovery decisions 5 and 7,
  boundary strategy and the two seams this spec closes.
- `.kiro/specs/training-load/requirements.md` — Req 2 (profile store), Req 3
  (prompt flow), Req 9 (missing-data honesty), Amendments 1 and 2.
- `.kiro/specs/fit-ingest/requirements.md` — Req 8.3, the read-only invariant
  this feature must preserve.
- TOML v1.0.0 local-date type, decoded by `tomllib` to `datetime.date`.
