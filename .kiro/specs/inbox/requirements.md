# Requirements Document

## Project Description (Input)

The plugin story says "fitdocs defines an inbox where `.fit` files land to be processed" — a standing interface the user's export/sync tooling (HealthFit → iCloud, watch sync, manual drops) plugs into. Today ingestion is a CLI argument: `fitdocs sync SOURCE` walks whatever path it is handed. The demo wiki already uses an `inbox/` directory by convention, but the tool has no notion of it: no configured path, no drain semantics, and none of the safeguards watch-folder tools have converged on. Files mid-copy from cloud sync, `.syncthing.*`/`.DS_Store` droppings, and known-bad real-world files (16/22 real HealthFit files once crashed the parser) are all handled by luck or not at all.

This feature promotes ingestion from a CLI argument to a standing configured inbox interface: the settings file declares the inbox (data-root-relative by default, `inbox/`), bare `fitdocs sync` drains it one-shot (no daemons or filesystem watchers — inboxes often live on iCloud/Dropbox/Syncthing storage where filesystem event APIs are unreliable), and the drain carries the standard watch-folder safeguards: a stability check for partially-written files, default ignore patterns for hidden files and sync-tool droppings, a quarantine channel so known-bad files are reported without looping as failures on every scheduled run, and an explicit, documented disposition policy for processed files (leave-in-place by default; never delete). The explicit `SOURCE` argument keeps working unchanged. The inbox contract is documented as a public interface: "get files here, however you like; fitdocs does the rest."

Full discovery context: `brief.md` in this directory.

## Introduction

inbox layers a thin, configured interface over the existing sync engine's
read-only, idempotent, warn-and-continue contract. The inbox is where the
user's export tooling delivers `.fit` files; `fitdocs sync` invoked with no
source argument drains it in one shot, applying the safeguards watch-folder
tools have converged on: junk and hidden files are ignored, files still being
written are deferred to a later run, files fitdocs cannot process are
quarantined — visible on every run but never looping as fresh failures — and
processed files are left in place unless the user explicitly configures a
move-to-processed disposition. Files are never deleted. Explicit-source sync,
regen, and load behavior is unchanged; the feature is purely additive.

## Boundary Context

Sequencing: this feature lands **after** the pre-wave `settings-foundation`
item and **after** `wiki-contract`. settings-foundation supplies the shared
settings-file location (`layout.SETTINGS_FILE`, `layout.settings_path`) and a
single reader that parses `<data-root>/fitdocs.toml` once, raising one shared
settings error for file-level problems; wiki-contract supplies the published
ownership contract (owned paths, the ownership declaration, and the
document-format-version gate that skips a newer document without archiving
it).

- **In scope**: the typed `[inbox]` table reader over the already-parsed
  settings document, and the inbox/processed path resolution rules;
  no-argument `fitdocs sync` draining the resolved inbox; candidate selection
  (ignore patterns) and the stability check for the inbox drain; the
  quarantine record and its reporting/retry behavior; the disposition policy
  (leave-in-place default, opt-in move keyed on archive presence, never
  delete); extended drain reporting; refreshing the ownership declarations on
  the drain path; documentation of the inbox as a public interface.
- **Out of scope**: reading, locating, or parsing the settings file itself and
  the shared settings error for file-level problems (settings-foundation), and
  the `[tiles]`/`[plugins]` table readers (route-maps, plugin-api);
  filesystem watchers, daemons, or scheduling of any kind (the user's
  cron/agent invokes the CLI); automated `.fit` acquisition from devices or
  platforms; non-`.fit` formats; any change to the per-file processing
  pipeline (parse, render, merge, archive), to explicit-source sync
  semantics, to `regen`/`load`, or to the document/wiki ownership contract
  itself (wiki-contract owns its content, including the clause admitting
  user-configured locations); load calculators (plugin-api).
- **Adjacent expectations**: the existing sync engine supplies the per-file
  pipeline, content-hash dedupe against the archive, per-file failure
  isolation, the written/skipped/failures/warnings report channels, and exit
  codes 0/1/2 — this feature composes with those contracts and must not
  change their observable behavior for existing invocations. fit-ingest's
  decode errors supply the failure reasons the quarantine record stores.
  wiki-contract supplies the ownership-declaration refresh the drain must
  call and the skip-without-archive outcome the disposition must respect.
  distribution (downstream) documents and packages the interface, including
  a home in the shipped documentation set for the inbox guarantees.

## Requirements

### Requirement 1: Inbox Configuration and Resolution
**Objective:** As a PKM user whose export tooling drops `.fit` files into a folder, I want fitdocs to know a standing inbox location from configuration, so that ingestion is an interface the rest of my tooling can rely on rather than a path I type each run.

#### Acceptance Criteria
1. Where the data root's settings file (`fitdocs.toml`) contains an inbox section with a path value, the fitdocs CLI shall use that path as the inbox location, resolving a relative path against the data root and using an absolute path as given.
2. When the settings file or its inbox section is absent, the fitdocs CLI shall use the default inbox location `inbox/` under the data root, with every other inbox setting at its documented default.
3. Where individual inbox settings are present, the fitdocs CLI shall apply each present setting independently, keep documented defaults for absent settings, and ignore unknown keys.
4. If the inbox section exists but is invalid — a wrong-typed or empty value, an unknown disposition, a move disposition without a processed-files destination, or a processed-files destination equal to or nested inside the inbox — the fitdocs CLI shall report an instructive configuration error naming the offending key and exit with the configuration-error code, writing nothing.
5. When the resolved inbox location lies inside the data root and the directory does not exist at drain time, the fitdocs CLI shall create it and proceed with the drain.
6. If the resolved inbox location lies outside the data root and does not exist or is not a directory at drain time, the fitdocs CLI shall report a configuration error naming the path and exit with the configuration-error code (guarding against typos and unmounted cloud storage).
7. If the settings file itself cannot be read or is not valid TOML, the fitdocs CLI shall surface the shared settings error raised by the single settings reader — one message for the file, not one per table — and exit with the configuration-error code, writing nothing.

### Requirement 2: No-Argument Sync Drains the Inbox
**Objective:** As a user, I want bare `fitdocs sync` to drain the inbox, so that the standing interface is a single command my scheduler or wiki agent can invoke.

#### Acceptance Criteria
1. When `fitdocs sync` is invoked without a source argument, the fitdocs CLI shall drain the resolved inbox: select eligible `.fit` files, process each through the existing per-file pipeline, and then run the training-load pass exactly as an explicit-source sync does.
2. When `fitdocs sync SOURCE` is invoked with an explicit source directory, the fitdocs CLI shall process that source with today's behavior unchanged — recursive discovery, strictly read-only source, content dedupe, report, and exit codes — without applying inbox selection, stability, quarantine, or disposition policy.
3. When a drain runs, the fitdocs CLI shall name the inbox path being drained in its output alongside the existing run summary.
4. When the inbox contains no eligible files, the fitdocs CLI shall complete the drain successfully, reporting nothing written and exiting with the success code.
5. The fitdocs CLI shall honor the existing sync options (`--out`, `--force`, `--no-prompt`) identically for inbox drains.

### Requirement 3: Candidate Selection and Ignore Patterns
**Objective:** As a user whose inbox lives on cloud-synced storage, I want hidden files and sync-tool droppings excluded from the drain, so that junk never reaches the parser or the failure report.

#### Acceptance Criteria
1. While draining the inbox, the fitdocs CLI shall consider as candidates only regular files with the `.fit` extension (case-insensitive), discovered recursively in a deterministic order.
2. The fitdocs CLI shall ignore any candidate whose inbox-relative path contains a component beginning with a dot — covering hidden files such as AppleDouble `._*` companions and everything inside hidden directories such as sync-tool version stores.
3. The fitdocs CLI shall ignore candidates matching the default junk-name patterns `*.tmp`, `*.part`, `.syncthing.*`, and `.DS_Store`.
4. Where the inbox configuration provides additional ignore patterns, the fitdocs CLI shall ignore candidates matching any of them, in addition to the defaults.
5. The fitdocs CLI shall exclude ignored files from processing and from the run's written/skipped/failed classification, and shall not treat them as failures.

### Requirement 4: Stability Check for Partially-Written Files
**Objective:** As a user whose files arrive via cloud sync or manual copy, I want files still being written to be left for a later run, so that a partial file is never parsed, archived, or quarantined.

#### Acceptance Criteria
1. While draining the inbox, the fitdocs CLI shall process a candidate only after verifying it is stable: its size and modification time unchanged across two observations separated by a settle interval.
2. If a candidate changes or disappears between the two observations, the fitdocs CLI shall defer it: leave it untouched, exclude it from processing, and report it as deferred, naming the file.
3. When a previously deferred file is stable during a subsequent drain, the fitdocs CLI shall process it normally, with no deferral state carried between runs.
4. The fitdocs CLI shall use a settle interval of 2 seconds by default; where the inbox configuration provides a settle interval, the fitdocs CLI shall use the configured value, and a value of zero shall disable the stability wait.
5. The fitdocs CLI shall wait at most one settle interval per drain regardless of the number of candidates, observing all candidates as a batch.
6. Deferred files shall not cause the failure exit code; a drain whose only exceptional entries are deferrals shall exit with the success code.

### Requirement 5: Quarantine for Failing Files
**Objective:** As a user with a standing inbox drained on a schedule, I want files fitdocs cannot process to be surfaced once and then remembered, so that known-bad files neither loop as fresh failures on every run nor disappear silently.

#### Acceptance Criteria
1. When an inbox file fails processing during a drain because of a source-level fault — the `.fit` bytes themselves cannot be decoded or parsed — the fitdocs CLI shall report the failure with its reason and exit with the failure exit code, and shall record the file's content identity, name, and failure reason in a quarantine record kept under the data root.
2. While a file's content identity is present in the quarantine record, subsequent drains shall not re-process the file and shall report it in a distinct quarantined channel, naming the file and its recorded failure reason.
3. Files reported through the quarantined channel shall not by themselves cause the failure exit code — a drain whose only exceptional entries are known-quarantined files shall exit with the success code.
4. When a file's content differs from every quarantined content identity, the fitdocs CLI shall treat it as new even if its name matches a quarantined file — the quarantine record applies to content, not names.
5. When `fitdocs sync` is invoked with the retry-quarantined option, the fitdocs CLI shall re-attempt quarantined inbox files: a success removes the file's quarantine record entry, and a renewed failure updates the entry and is reported as a failure.
6. If the quarantine record exists but cannot be read or is not in its documented form, the fitdocs CLI shall report an instructive configuration error naming the record's location and exit with the configuration-error code rather than silently discarding or rebuilding it.
7. When an inbox file fails processing for a reason that is a property of the existing document rather than of the source bytes — a damaged preserved region being the representative case — the fitdocs CLI shall report the failure and exit with the failure exit code without recording a quarantine entry, so that repairing the document is enough to make the next drain succeed.

### Requirement 6: Disposition of Processed Files
**Objective:** As a user, I want an explicit, documented policy for what happens to inbox files after processing — leaving them in place unless I say otherwise — so that no tool ever surprises me by moving or deleting my exports.

#### Acceptance Criteria
1. The fitdocs CLI shall apply the leave-in-place disposition by default: inbox files are never written, moved, renamed, or deleted, and the archived copy plus content dedupe make subsequent drains skip already-processed files.
2. Where the inbox configuration explicitly selects the move disposition with a processed-files destination, the fitdocs CLI shall move an inbox file out of the inbox to that destination only when that file's content is present in the archive at the end of its processing — whether archived by this run or already archived before it — and never on the basis of a written-or-skipped label alone.
3. If moving a file would collide with an existing name at the destination, the fitdocs CLI shall preserve both files by storing the moved file under a distinct name, never overwriting.
4. The fitdocs CLI shall never move failed, deferred, or quarantined files, nor any file whose processing was skipped without leaving an archived copy — an existing document at a newer document-format version being the representative case — so that such a file stays in the inbox and is retried on the next drain.
5. If an individual move fails after successful processing, the fitdocs CLI shall report the failed move distinctly, shall leave the completed processing intact, and shall not emit the failure exit code for the move alone; a later drain shall retry the move when it encounters the file again.
6. The fitdocs CLI shall offer no disposition that deletes inbox files; deletion is never performed under any configuration.
7. Where the move disposition is active and the processed-files destination lies inside the data root, the fitdocs CLI shall create the destination directory on demand; if the destination lies outside the data root and does not exist at drain time, the fitdocs CLI shall report a configuration error and exit with the configuration-error code before processing anything.

### Requirement 7: Reporting, Exit Codes, and Idempotency Compatibility
**Objective:** As a user with automation built on the existing report and exit codes, I want the inbox feature to be purely additive, so that existing invocations and re-run guarantees are unaffected byte for byte.

#### Acceptance Criteria
1. When a drain completes, the fitdocs CLI shall present the existing written/skipped/failed/warnings summary extended with deferred, quarantined, moved, and failed-move counts — each reported as its own named row so that downstream documentation and agent skills can enumerate the channels — and shall list per-file detail, with reasons where recorded, for deferred entries, quarantined entries, and failed moves.
2. The fitdocs CLI shall keep the exit-code contract unchanged: success (including no-op drains and drains whose only exceptional entries are deferrals, known-quarantined files, or failed moves), the failure code when one or more new per-file or load failures occur, and the configuration-error code — writing nothing — for configuration errors.
3. While no inbox configuration is present and `fitdocs sync` is invoked with an explicit source, the fitdocs CLI shall leave explicit-source sync, regen, and load behavior, reports, outputs, and exit codes unchanged by this feature.
4. When a drain is re-run under the default leave-in-place disposition with the inbox and data root unchanged, the fitdocs CLI shall write nothing — documents, assets, archive, and quarantine record all untouched — and shall classify previously processed files as skipped.
5. When a drain is re-run under the move disposition after a fully successful drain, the fitdocs CLI shall find no candidates in the inbox and write nothing.
6. When a drain runs, the fitdocs CLI shall refresh the ownership declarations for the directories fitdocs owns exactly as an explicit-source sync does, so that the declaration stays current on what becomes the primary ingestion path.

### Requirement 8: The Inbox as a Documented Public Interface
**Objective:** As an integrator (export tooling author, wiki agent, or user with a sync pipeline), I want the inbox contract documented, so that any tool can deliver files — "get files here, however you like; fitdocs does the rest."

#### Acceptance Criteria
1. The shipped fitdocs user documentation shall describe the inbox contract: the default location, every inbox configuration key with its default, drain semantics, the safeguards (ignore patterns, stability check, quarantine), and the disposition policy including the never-delete guarantee.
2. The shipped fitdocs user documentation shall state that delivering files into the inbox is the integrator's concern and that fitdocs performs no watching or scheduling — a drain happens only when `fitdocs sync` is invoked.
3. The `fitdocs sync` command help text shall describe the no-argument drain behavior and how the inbox location is determined.
4. The never-delete guarantee (6.6) and the no-watching-or-scheduling guarantee (8.2) shall each be asserted by an automated preserved-guarantee test, so that a later documentation rewrite cannot drop them silently.
5. The locations this feature creates shall be reconciled with the published ownership contract: the inbox directory and its optional processed-files destination as user-configured locations fitdocs may create, and the tool-state directory holding the quarantine record as tool-owned state; nothing in this feature shall write outside the paths that contract names.
