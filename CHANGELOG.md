# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Convention:** an entry that touches a governed contract -- the generated
document and ownership contract, the inbox interface, the plugin API, or the
`fitdocs.toml` settings schema -- names the contract and the action a user or
plugin author must take, inline in the entry that changes it. Entries
describe user-observable behavior, not commit subjects; removing or adding
the built-in `threshold` calculator is itself a contract change and is
recorded as one.

## [Unreleased]

### Added

- Workout pages gain a `Morning Of` block with the day's wellness
  signals and sleep against the athlete's own per-source baselines.
  Every `fitdocs sync`, `fitdocs pull --sync` and `fitdocs regen`
  refreshes it from the wellness series; it states no readiness verdict.
- Apple Health import reads supported wellness types from `export.zip` or bare
  `export.xml`, archives a compact extract, and uses the latest export date to
  supersede earlier exports entirely. See the [Apple Health
  guide](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/wellness.md#apple-health).
- `fitdocs recovery` writes the recovery page and chart images from
  the normalized wellness series and workout documents. Run it after
  a drain that archived wellness or changed the series, or when you
  want the page; see
  [the recovery guide](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/recovery.md).
- The chart kit adds `reference-band` for points against a reference
  band. When a chart has genuine marks, `line`, `small-multiples`
  and `reference-band` preserve the extent of present x positions
  even where endpoint values are absent, without fabricating values
  or marks.

- `fitdocs derive-benchmarks` gains a heart-rate stage after tagged efforts:
  resting heart rate comes from per-source wellness baselines, and maximum
  heart rate from sustained workout peaks. Hand-recorded entries stay
  unchanged and win from their measurement date until later evidence passes
  the disagreement and confirmation rules; dated benchmark selection is
  unchanged. Run `fitdocs derive-benchmarks` to build the timeline; see
  [derived heart-rate benchmarks](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/configuration.md#derived-heart-rate-benchmarks).
- The athlete-benchmarks provenance contract gains the optional `series`
  key for a wellness-series reference. The load-channels contract adds
  `resting_hr_measured_on` and `max_hr_measured_on` to the heart-rate
  channel's `inputs_used`, identifying the dated resting and maximum
  entries used; existing documents need no migration. `fitdocs check` adds
  `hr_benchmark_takeover`, `hr_benchmark_inconsistent` and
  `athlete_profile_unreadable`: relay a takeover to the athlete to decide,
  correct the wrong recorded value for an inconsistency, or fix the profile
  before loading or deriving again.
- The intervals.icu wellness pull: `fitdocs pull` delivers wellness files
  into the inbox, with field attribution from intervals.icu's per-platform
  wellness import settings and a separate wellness report table.
  `fitdocs.toml` settings schema gains the optional `wellness` key
  (default `false`); enable it per connector instance.
- A local wellness store imports intervals.icu wellness JSON and four Garmin
  export JSON formats from the inbox. `wellness-archive/` keeps immutable
  source bytes; `wellness/` holds the rebuildable daily series and manifest.
  Drop supported exports into the inbox and run `fitdocs sync`; see
  [the wellness guide](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/wellness.md).
- `fitdocs.toml` settings schema (additive; no action needed): `[wellness]`
  configures general and per-metric source precedence; defaults apply when
  absent. `fitdocs check` adds `wellness_orphaned_entry`,
  `wellness_series_stale`, `wellness_series_occupied` and `wellness_conflict`,
  each with a remedy.
- The analytics index gains `wellness_daily`, including source, canonical
  selection and measurement origin. Index schema version advances from `2`
  to `3`: run `fitdocs index` once after upgrading to rebuild the disposable
  cache; existing documents need no migration.

- `fitdocs index [--rebuild]` builds the disposable analytics index once;
  writing commands refresh it after their document and load writes. The
  per-data-root index lives outside the data root, resolved by
  `FITDOCS_INDEX_DIR`, then `XDG_CACHE_HOME`, then the user's cache directory.
  Run `fitdocs index` once to build it. The ownership contract now describes
  this cache and the change requires no action for existing documents.
- The analytics index adds four derived projections: best efforts, daily and
  weekly load series, a benchmark timeline, and training blocks. Run
  `fitdocs index` once after upgrading: the index schema version changed, and
  writing commands report that the index needs a rebuild until it is rebuilt.
- `fitdocs query` accepts one SQL statement as a positional argument or on
  standard input (`-`), with `--file` for a file; its default is a table on a
  terminal and CSV when piped. The `--format` option explicitly selects
  table, CSV, or JSON, and it supports the sandboxed `--schema` view. The
  packaged `fitdocs-analytics` skill teaches safe SQL; see the
  [analytics guide](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/analytics.md).
- The runtime dependency `duckdb>=1.2,<2` (about 44 MB installed) powers the
  analytics index. Prebuilt wheels are not available for musl-based Linux or
  free-threaded Python builds.
- A run page gains a Running Dynamics section, with its own chart, when the
  activity records running-dynamics channels (native `.fit`
  running-dynamics fields, or record-level developer fields such as those a
  Stryd pod writes).
- The `fitdocs.toml` settings schema gains an `[identity]` table whose
  `precedence` key chooses which of a workout's files a page is rendered
  from; the default is a Garmin original, then the phone copy, then any
  other original, then unknown files, and applies when the table is
  absent; see [the configuration reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/configuration.md).
- `fitdocs check` reports three new findings: a held file that could not be
  placed on one page (`ambiguous_source`), an archived source that no page
  lists (`orphaned_source`), and one workout recorded on two or more pages
  (`duplicate_session`), each with the action that resolves it.
- Plugin API (additive; no action needed): `FileIdentity`, the record of what
  a file's own `file_id` message declares, is exported from the `fitdocs`
  package root; `Activity.file_identity` carries it, and
  `Provenance.undocumented_messages` counts the messages a file carries that
  the installed FIT profile does not define (`None` when not counted). See
  [the plugin guide](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/plugins.md).
- The package metadata gains a `Homepage` project URL, `https://fitdocs.ai`,
  listed first among the project URLs; the other project URLs are unchanged
  and no action is needed.
- `fitdocs connect` and `fitdocs pull`: configure a named connector instance
  in a new `[connectors]` table, authenticate it once with `connect` if it needs credentials, and
  fetch new activities with `pull`, delivered into the existing inbox where
  the existing drain picks them up. This release's first connector,
  `folder`, reads a local directory and needs no authentication.
  `fitdocs.toml` settings schema (additive; no action needed): gains the
  `[connectors]` table. See
  [the connectors reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/connectors.md).
- The `intervals` connector pulls the original `.fit` files of an
  intervals.icu account with a personal API key (pull only): configure it as
  `[connectors.intervals]`, or as any `[connectors.<name>]` table with
  `connector = "intervals"`, then run `fitdocs connect <name>` once. Its
  optional `sources` key chooses which recording sources a pull keeps; the
  default is `["GARMIN_CONNECT"]`. `fitdocs.toml` settings schema (additive;
  no action needed): `[connectors.<name>]` gains the `sources` key for this
  connector. See
  [the connectors reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/connectors.md).
- Chart kinds `calendar-heatmap`, `heatmap`, `dual-axis`, `band`, `box`,
  `mean-max`, `small-multiples` and `stacked-100` join the chart kit,
  ready for dashboard charts. On the grid kinds (`calendar-heatmap` and
  `heatmap`) a row with no value shows a cross, a zero an outlined square
  and a missing row nothing, and a negative value is refused.
- `fitdocs dashboard` keeps the charts on your dashboard pages (markdown files
  under `dashboards/`) current: `check`, `refresh` and `freeze` run each
  chart's SQL against the analytics index and draw the result, and `kinds`
  lists the chart kinds. `fitdocs sync` (with or without a source),
  `fitdocs pull --sync`, `fitdocs regen` and `fitdocs load` run the
  dashboard pass right after the index refresh. The packaged `fitdocs-dashboards` skill
  teaches the page format; see
  [the dashboards guide](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/dashboards.md).
  The ownership contract advances to version 10: it describes the
  `dashboards/` location, where only the chart regions and the chart images
  and snapshots under `dashboards/assets/` are fitdocs's. Action: run
  `fitdocs sync` or `fitdocs regen` once to place `dashboards/AGENTS.md`.
  `fitdocs.toml` settings schema: `[plans] path` is now refused when it is
  `dashboards` or inside it (exit status `2`). Action: if your plan sources
  live there, move them and set `[plans] path` to the new directory.

### Changed

- The generated document format advances (`doc_version` 9 to 10)
  to add the morning-of region. Run `fitdocs regen` once after
  upgrading to bring existing workout pages to the current format.
- The ownership contract (wiki-contract) advances from version `14`
  to `15`: fitdocs owns the refreshed morning-of region and its
  pass. Run `fitdocs regen` once to refresh existing pages and
  their ownership declarations.
- A change confined to the morning-of block is a document-only
  change in the analytics index: it updates the document without
  recomputing the page's computed values.
- Inbox interface: `.zip` and `.xml` files are wellness candidates. Unrelated ZIP or
  XML stays in place and is reported as unrecognized; add it to `[inbox] ignore` to
  silence it.
- The default wellness source order gains `apple-health` between `garmin-export` and
  `intervals-icu`. The first `fitdocs sync` or `fitdocs regen` after upgrading
  rebuilds the series once.
- The ownership contract (wiki-contract) advances from version `13`
  to `14`: `recovery/` holds the generated page `recovery/recovery.md`
  and its chart images under `recovery/assets/`. Run `fitdocs recovery`
  to create or refresh the page and place `recovery/AGENTS.md`; see
  [the ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md).

- The ownership contract (wiki-contract) advances from version `12` to
  `13`: `derive-benchmarks` reads composed workout archives and normalized
  wellness series and writes `athlete.toml` at most once per stage, without
  changing hand-recorded entries. Run `fitdocs sync` or `fitdocs regen` once
  to refresh the in-tree ownership declarations; see
  [the ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md).
- Derivation can narrow a hand-recorded entry's applies-from back-reach only
  where a derived entry is dated before the cover begins; deriving alone does
  not rescore existing load, and a rescore happens only after you explicitly
  run `fitdocs load --recompute`.
- Connector ledger format: a connector's ledger uses ledger format 2 when it
  holds wellness records. An older fitdocs refuses such a ledger. To enable
  wellness, set `wellness = true` on the instance and run `fitdocs pull --sync`.
  Activity-only ledgers keep format 1; existing documents need no migration.
- Ownership contract version advances from `11` to `12`: it now covers
  wellness deliveries into the instance's inbox, their removal once
  identical bytes are archived, and the pull never writing the wellness
  archive or series. Existing documents need no action; enable wellness
  with the setting and command above.
- Inbox interface: bare `fitdocs sync` now handles wellness before workouts,
  prints four additional report rows (Unrecognized, Wellness archived,
  Wellness skipped and Wellness failed), and reports changed-series results.
  Unrecognized files remain in place; recognized parse failures use the
  content-keyed quarantine. Wellness failures and failed series rebuilds
  make the command fail. No action is needed for existing workout inboxes;
  use `[inbox] ignore` to silence an unwanted wellness candidate.
- Workout intake skips FIT headers declaring a non-activity type, warns and
  leaves those files in place even with move disposition and a legacy
  archive copy. No action is needed: no new page is made; `fitdocs regen`
  still rebuilds pages that already list such files.
- Ownership contract version advances from `10` to `11`: `wellness-archive/`
  and `wellness/` are now owned locations. Run `fitdocs sync` or `fitdocs
  regen` once to place their ownership declarations. See
  [the contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md).
- Plugin API (additive; no action needed): `FileIdentity.file_type` is a
  defaulted final field carrying the declared FIT file type, or `None`.
  Existing constructors remain compatible.

- The ownership contract version advances from 8 to 9 to describe the
  analytics index's external location, disposable-cache behavior and refresh
  agreement. No action is needed for documents.
- The generated document format advances (`doc_version` 5 to 6): run pages
  gain the Running Dynamics section, a 0 bpm heart-rate sample is no longer
  recorded (where the session records no average or maximum heart rate, those
  are computed from the remaining samples),
  and a session developer field holding a sentinel or float32 value is
  decoded. Run `fitdocs regen` to bring existing documents current; `fitdocs
  check` reports them stale until then.
- Generated document contract: a workout's frontmatter carries four new
  managed keys (`source_kind`, `source_elapsed_s`, `source_distance_m`,
  `source_device`) that describe the file the page is rendered from — the
  last three appear only when that file records the value — and the document
  format advances again (`doc_version` 6 to 7). `sources` lists every
  archived file of the page in one canonical order, the base last. A page
  keeps a phone-side copy's session `uuid` when a file without one becomes
  its base, and a page may be renamed when its base changes (a file that
  outranks it arrives, or the precedence changes at `fitdocs regen`) and the
  new base gives a different filename, or when a page written under a
  collision-suffixed name `<name>-<8 characters>.md` finds `<name>.md` free
  (links to its previous filename are not updated). A file that cannot be
  placed on one page is archived and held, recorded in `.fitdocs/held.toml`,
  and never written as a second page. Action: run `fitdocs regen` after
  upgrading, and before syncing a file of a workout you already have from
  another source, so pages written before this release are recognized; see
  [the ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md).
- `fitdocs.toml` settings schema: the new `[identity]` table is additive and
  optional; an invalid `[identity]` exits with status `2`. Action:
  `fitdocs regen` applies a changed `precedence` to existing pages.
- Inbox interface: a file a connector pull delivered is fitdocs's own copy,
  and the next pull removes it once identical bytes are archived — no
  action; every other never-delete guarantee is unchanged.
- Ownership contract: states that credentials never live under the data
  root, that each connector's ledger is fitdocs-owned tool state in the
  tool-state directory `.fitdocs/`, what `fitdocs pull` writes and removes,
  and that `fitdocs connect` writes nothing under the data root — no
  action.
- Garmin devices are named by model in a workout's devices table, and a page
  rendered from a Garmin-recorded file carries the line `Data source: Garmin
  <model>` directly beneath its title, as intervals.icu's API terms and
  Garmin's API Brand Guidelines require. The generated document format
  advances, so a page written by an earlier release lacks the line and the
  model names until regenerated. Action: run `fitdocs regen` to bring existing
  documents current, and before the first `fitdocs pull` of an `intervals`
  instance; `fitdocs check` reports them stale until then. See
  [the connectors reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/connectors.md).
- Generated document contract: a page that lists several files of one
  workout takes the channels its base file lacks from the others (a channel
  the base records at all stays the base's) and, in a new Channel Sources
  section, names the file each channel came from; training load and derived
  benchmarks are computed from the same combined activity, and the ownership
  contract's version advances. The generated document format advances again
  (`doc_version` 8 to 9); `fitdocs check` reports older pages as out of date
  until they are regenerated. The Garmin data-source line beneath the title
  also counts the files that donate channels: a Garmin-recorded one is named,
  any other adds "other devices". Actions: run `fitdocs regen` to apply this
  to existing pages, and `fitdocs load --recompute` to rescore a page whose
  files changed after its load was computed (a computed load is otherwise
  kept); see
  [the ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md).
- Ownership contract: two files of the same sport whose starts are no more
  than 1 s apart, and whose distances are no more than 5 m or 20 % of the
  longer distance apart, whichever is larger, are now one workout, however
  far apart their elapsed times are. Elapsed time is compared only when a
  distance is missing. Before, a Stryd file and its HealthFit copy were often
  two pages, because HealthFit's session runs on until the workout is ended
  on the watch. The ownership contract's version advances. Actions: run
  `fitdocs check` to see pages that are now recognized as one workout
  (`duplicate_session`), and resolve each by deleting one of its pages (move
  anything worth keeping out of its notes first) and running `fitdocs regen`
  before adding more files of that workout, which
  would otherwise be held because they match both pages; see
  [the ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md#deciding-that-two-files-are-one-workout).
- Derived heart-rate benchmarks: maximum heart rate now comes only from run
  and ride sessions (other sessions are reported as `not_run_or_bike`, a new
  row in the derive-benchmarks table), is never dated after the newest such
  session, and never falls; record a lower maximum by hand. A hand-recorded
  entry is challenged only by evidence dated after it and formed from
  sessions or wellness days after it, so historic heart-rate load before a
  hand entry's date keeps the hand value wherever its applies-from date
  reaches. Run `fitdocs derive-benchmarks` once to
  replace earlier derived heart-rate entries; rescore history afterwards with
  `fitdocs load --recompute` if you want it. See
  [derived heart-rate benchmarks](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/configuration.md#derived-heart-rate-benchmarks).

### Fixed

- `athlete.toml` now refuses a non-finite number (`nan`, `inf`, `-inf`) in a
  threshold such as `ftp_watts`, in a zone divider, or in any profile value a
  calculator reads, as a configuration error naming the key, instead of letting
  it produce `nan` intensity and load values. `fitdocs.toml` likewise refuses
  one in the `[load.flags]` thresholds `cadence_lock_max_delta_bpm`,
  `divergence_max_intensity_delta` and `aerobic_drift_max_pct`, in
  `[inbox] settle_seconds`, and in `[connectors.<folder>] settle_seconds`.
  A load prompt that is answered with a non-finite value asks again, as it
  does for any other non-number.
- Recovery page: a change of shown source is now stated even when days with no
  value separate the two sources, the Sleep section now states its source
  changes and names its sources with their recorded origins (its table caption
  names the source and night shown), and the Other Signals section names each
  charted panel's source and origins. The page's `recovery_version` advances
  from 1 to 2. Action: run `fitdocs recovery` to rewrite the page; see
  [the recovery guide](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/recovery.md).
- Garmin weight now imports from a real export. Its `*_userBioMetrics.json`
  stamps `metaData.calendarDate` with a local time (for example
  `2024-05-01T06:30:15.1`), which the importer rejected, so the whole file was
  reported as failed and no weight reached the series. The importer takes the
  date part of that stamp, with no timezone conversion; run `fitdocs sync`
  to import a file that was left in the inbox or quarantined.
- A value outside its metric's accepted range in a `wellness/*.csv` series file,
  such as an HRV of 0 from a hand edit, is now reported as an unreadable series.
  `fitdocs recovery` used to stop with a `math domain error` traceback; it now
  exits 1 and names the file, day, metric and value, with the `fitdocs sync` or
  `fitdocs regen` remedy. `fitdocs derive-benchmarks` reports it as a
  resting-heart-rate read failure, and `fitdocs index` reports it as a
  `derived.wellness` refresh error instead of loading the value.
- `fitdocs pull` prints `1 day`, not `1 days`, for a one-day wellness
  delivery.
- A one-off read error while archiving an Apple Health `export.zip` (for
  example while an iCloud file is still materialising) now defers the file for
  the next drain. Before, it was quarantined as "not an Apple Health export".
- Apple Health import no longer slows down quadratically with the number of
  nights of history. Each overnight HRV, respiration and SpO2 reading is now
  matched to its night with one lookup instead of a scan of every night; the
  reduction time now grows in step with the readings, not with nights times
  readings. The archived extract and the series values are unchanged.
- An Apple Health `export.zip` whose compressed data is corrupt or cut short
  is now reported as an unreadable export and quarantined, like other bad zips.
  Before, the decompression error escaped as an unhandled failure.
- `fitdocs regen` and `fitdocs sync` no longer write a new page over an existing
  `workouts/` file they did not match. A page whose frontmatter is damaged
  matches nothing, and a new page for its activity could land on its path and
  replace your notes; the file is now reported as a failure and left unchanged.
  When the damaged page sits at the new page's usual name, the new page is still
  written beside it and the run warns, naming the damaged page.
- A load channel that declines an activity as too short because the stream has
  no measurable recorded span (fewer than two samples, or no time between
  them) now reports its observed duration as absent. Before, it reported
  `0`, a duration that was never measured. No stored page carries the old
  wording; the next `fitdocs load` reports the new one.
- A hand-edited page whose frontmatter is well-formed YAML but not a value
  PyYAML can build (an unquoted `date: 2026-02-30`, a UTC offset past 24 hours)
  no longer crashes `check`, `regen`, `load` or `sync` with a traceback. The
  page is treated as not a fitdocs document and the run continues instead of
  crashing. A dashboard directive body PyYAML cannot load (a `\U` escape past
  the Unicode range, absurd nesting) is likewise reported as a syntax problem.
- A device name, manufacturer or battery status recorded in a `.fit` file
  can no longer break the devices table or forge a region marker line on the
  page. Each is now shown on one line with any `|` escaped, and so is each
  decode error. Before, a newline or pipe in the recorded text was written
  into the page verbatim.

## [0.1.0] - 2026-09-19

### Added

- `fitdocs` is installable as a Python package with a single console
  command.
- `fitdocs sync` ingests `.fit` files from the configured inbox, archives
  each source, and writes one markdown document per workout under the data
  root's `workouts/` directory, with charts and computed training load;
  `fitdocs regen` rebuilds every workout document from the data root alone
  (the archive, the athlete profile, and settings) -- the original files
  and the inbox are not needed.
- The data root's owned paths, the overwrite rules, and the user-owned
  regions of every generated document are published as the ownership
  contract; the four owned directories a human or agent browses
  (`workouts/`, `fit-archive/`, `history/`, `blocks/`) each carry a generated
  `AGENTS.md` restating it, and every generated document carries a matching
  provenance banner.
- The inbox is configured through the `[inbox]` table in
  `<data-root>/fitdocs.toml`: a location fitdocs drains on `sync`, with a
  disposition policy that never deletes a source file.
- Training-load calculation is pluggable through the `LoadCalculator`
  interface: a calculator is discovered as an installed distribution
  advertising the `fitdocs.load_calculators` entry point, or as a local
  plugin file/directory named in `[plugins]`. fitdocs ships one built-in
  calculator, `threshold`.
- `fitdocs plugins` lists every registered calculator (built-in, packaged,
  and local) with its id, display name, version, origin, and supported
  modalities, and every plugin load error; it works with or without a
  configured data root.
- `fitdocs check` reports every place a data root diverges from the
  installed ownership contract.
- Every packaged agent skill ships inside the distribution and is
  discoverable through `fitdocs skill`, which prints a packaged skill's
  directory and a one-line copy recipe without resolving a data root or
  writing anything.
- `fitdocs --version` reports the installed package version.
