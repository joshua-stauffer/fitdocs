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
