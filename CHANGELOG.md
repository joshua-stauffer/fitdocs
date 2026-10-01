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

### Changed

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
  archived file of the page in one canonical order, the base last. A page keeps a phone-side copy's session
  `uuid` when a file without one becomes its base, and a page may be renamed
  when its base changes (a file that outranks it arrives, or the precedence
  changes at `fitdocs regen`) and the new base gives a different filename, or
  when a page written under a collision-suffixed name
  `<name>-<8 characters>.md` finds `<name>.md` free (links to its previous
  filename are not updated). A file that cannot be placed on one page
  is archived and held, recorded in `.fitdocs/held.toml`, and never written as
  a second page. Action: run `fitdocs regen` after
  upgrading, and before syncing a file of a workout you already have from
  another source, so pages written before this release are recognized; see
  [the ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md).
- `fitdocs.toml` settings schema: the new `[identity]` table is additive and
  optional; an invalid `[identity]` exits with status `2`. Action:
  `fitdocs regen` applies a changed `precedence` to existing pages.

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
