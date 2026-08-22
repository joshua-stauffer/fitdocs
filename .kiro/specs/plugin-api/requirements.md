# Requirements Document

## Project Description (Input)

The product promise is "update the tool without overwriting your bespoke logic":
user logic must live *outside* fitdocs and plug into defined extension points.
The `LoadCalculator` seam delivered by training-load is clean — a calculator
declares its id, display name, supported modalities, and required athlete
inputs, and returns a closed set of typed outcomes — but nothing can *discover*
a third-party implementation. Calculators are registered only by an import
side-effect inside fitdocs itself, the package advertises no extension group,
and the CLI never loads user code. Today the only way to add a methodology is
to fork fitdocs — the exact failure mode the pluggable seam exists to prevent.

This feature makes the seam reachable from outside. A third-party package that
advertises a calculator in fitdocs' extension group is discovered on install,
with no configuration. A user with bespoke logic that will never become a
package can point their user-owned configuration at a local plugin file or
directory. Every discovered calculator is validated against the contract before
it is registered, and any plugin that fails to import, fails validation, or
claims an already-taken id is reported by name and skipped — never crashing the
run and never changing the exit code of an otherwise-successful run. A
`fitdocs plugins` command lists what was discovered (id, display name, version,
origin, supported modalities) together with every load error. Plugin authors get
a typed, documented, versioned public import surface and a worked example.

In scope: entry-point discovery of load calculators; local plugin file/directory
loading from user-owned configuration; contract validation and per-plugin
failure isolation; the `fitdocs plugins` listing command; shipped type
information plus a documented public API surface, compatibility policy, and
distribution naming convention; a plugin-author guide with a worked example.
Out of scope: pluggable renderers, templates, charts, or frontmatter; hook
lifecycles beyond one-object-per-plugin registration; a plugin marketplace or
index; sandboxing of plugin code; release mechanics.

Full discovery context: `brief.md` in this directory.

## Introduction

plugin-api extends training-load with the discovery layer its pluggable
calculator seam has always assumed. Two discovery channels feed one registry:
installed distributions that advertise a calculator in fitdocs' extension group
(no configuration required), and a local plugin file or directory named by the
user's own configuration under the data root (for bespoke logic that never
becomes a package). Everything discovered is validated against the calculator
contract before registration, and every plugin failure is isolated: named,
reported, and skipped, with built-ins and healthy plugins unaffected. A new
`fitdocs plugins` command makes the whole picture inspectable, and a typed,
documented, versioned public import surface lets authors write calculators
against a stable contract and type-check them like any other code. The
calculator contract itself, the load engine, and the athlete profile are
unchanged: this feature adds *who can register*, not *what a calculator is*.

## Sequencing Precondition

This spec depends on **settings-foundation**, a pre-wave direct-implementation
item that lands before it. settings-foundation provides `layout.SETTINGS_FILE`,
`layout.settings_path(data_root)`, and a `settings.py` that reads and parses
`<data-root>/fitdocs.toml` exactly once per invocation, raising a single
`SettingsError` for file-level problems (unreadable file, invalid TOML), with
the existing `[tiles]` reader already redirected onto it. plugin-api therefore
owns only a typed **per-table** reader for `[plugins]` over the already-parsed
mapping; it adds nothing to `layout.py` and touches no other spec's reader.

## Boundary Context

- **In scope**: discovery of third-party load calculators from installed
  distributions advertising fitdocs' calculator extension group; loading local
  plugin modules from a user-configured file or directory; contract validation,
  duplicate-id rejection, and per-plugin failure isolation with named reporting;
  a configuration switch that disables third-party discovery; the
  `fitdocs plugins` listing command; shipping type information for the package;
  a documented, versioned public import surface with a compatibility policy and
  a distribution naming convention; plugin-author documentation with a worked
  packaged example and the local-plugin arbitrary-code-execution disclosure.
- **Out of scope**: any change to the calculator contract's semantics or the set
  of outcome variants (changes must be additive only); pluggable renderers,
  document templates, charts, or frontmatter (deferred until the document
  contract stabilizes); hook or lifecycle mechanisms beyond one calculator
  object per plugin; a plugin index, marketplace, or discovery service;
  sandboxing, permission prompts, or any other containment of plugin code;
  the settings-file location helper, the shared one-time read/parse of
  `<data-root>/fitdocs.toml`, and its file-level error voice (settings-
  foundation); publishing/release mechanics and version-number policy
  enforcement (distribution); the ownership/frontmatter contract
  (wiki-contract); ingestion and inbox configuration (inbox); which
  methodologies ship built-in (the third party's licensing is an external gate).
- **Adjacent expectations**: training-load owns the calculator contract, the
  registry's addressing/selection rules, the load engine, and the athlete
  profile store — plugin-api adds registrants and changes none of those
  behaviors; a plugin calculator is treated exactly like a built-in once
  registered, including its outcome handling and the engine's existing
  per-document failure isolation. The user-owned settings file under the data
  root gains a `[plugins]` table; settings-foundation owns locating, reading,
  and parsing that file once per invocation and the single file-level error
  voice, while this spec owns only the typed `[plugins]` reader over the parsed
  result. fitdocs only ever reads the file. workout-docs owns document
  rendering and the sync/regen reporting
  channels — plugin load errors reuse the established warning channel rather
  than introducing a new failure class. The project-wide data-root posture rule
  applies: commands that *describe the installed tool* need no data root, while
  commands that *describe a tree* require one — the plugins command describes
  the installed tool plus optional local configuration, so requirement 4.7's
  degraded listing is that rule, not an exception to it. distribution documents
  and ships the plugin story publicly (including the project-wide compatibility
  statement and any build-profile pruning of bundled methodologies); this
  feature defines and documents the plugin surface in-repo.

## Requirements

### Requirement 1: Discovery of Installed Third-Party Calculators
**Objective:** As an athlete who wants a methodology fitdocs does not ship, I want to install a calculator package and have fitdocs find it, so that I never have to fork the tool to score my training my way.

#### Acceptance Criteria
1. When a fitdocs command that uses training-load calculators runs, the fitdocs CLI shall discover every calculator advertised by an installed distribution in fitdocs' load-calculator extension group and register it alongside the built-in calculators, with no user configuration required beyond installing the distribution.
2. The fitdocs CLI shall perform discovery exactly once per invocation, before any workout document is processed.
3. The fitdocs CLI shall register built-in calculators first, in their existing order, followed by discovered third-party calculators in an order that depends only on the advertised entry-point names, so that automatic calculator selection is reproducible across machines and installation orders.
4. When a document's modality is supported by a registered plugin calculator and no earlier-ordered calculator supports it, the fitdocs CLI shall use that plugin calculator to compute load, applying the same outcome handling it applies to built-in calculators.
5. When the user names a registered plugin calculator's id with the calculator-selection option, the fitdocs CLI shall use only that calculator.
6. If the user names an unregistered calculator id, the fitdocs CLI shall fail with the existing configuration-error behavior and list every registered id, including plugin-provided ids.
7. While no third-party calculators are installed and no local plugins are configured, the fitdocs CLI shall behave exactly as it did before this feature, including identical generated document content.
8. Where third-party discovery is disabled in the user-owned configuration, the fitdocs CLI shall register only built-in calculators and shall load no third-party code from either discovery channel.
9. The fitdocs CLI shall import only those installed distributions that advertise a calculator in fitdocs' extension group, and shall not import unrelated installed distributions in order to discover calculators.

### Requirement 2: Local Plugin Files for Bespoke Logic
**Objective:** As a user with one-off calculation logic that will never be a published package, I want to keep it as a plain Python file next to my vault configuration, so that my bespoke logic survives every fitdocs upgrade without being packaged or forked.

#### Acceptance Criteria
1. Where the user-owned configuration under the data root names a local plugin path, the fitdocs CLI shall load Python module(s) from that path at discovery time and register the calculators they register.
2. When the configured local plugin path is a directory, the fitdocs CLI shall load its top-level Python files in a deterministic alphabetical order and shall not descend into subdirectories.
3. When the configured local plugin path is a single Python file, the fitdocs CLI shall load exactly that file.
4. When the configured local plugin path is relative, the fitdocs CLI shall resolve it against the data root, so that a vault remains portable between machines.
5. While no local plugin path is configured, the fitdocs CLI shall load no local plugin code and shall scan no implicit default location.
6. If the configured local plugin path does not exist or cannot be read, the fitdocs CLI shall record a plugin load error naming the configured path, continue the run with the remaining calculators, and leave the exit code unchanged.
7. If the `[plugins]` table itself is malformed (a value of the wrong type), the fitdocs CLI shall fail with the existing configuration-error behavior, naming the settings file and the offending key, before anything is written. File-level problems with the settings file (unreadable, invalid TOML) are reported once by the shared settings reader owned by settings-foundation, not by a second voice in this feature.
8. The fitdocs user documentation shall disclose that local plugin files are executed as ordinary code with the user's own privileges, that fitdocs applies no sandboxing, and that the user is responsible for what they point the setting at.

### Requirement 3: Validation and Per-Plugin Failure Isolation
**Objective:** As a user running fitdocs on a schedule, I want a broken plugin to be reported and skipped rather than to take the run down, so that a third party's mistake never costs me my workout documents.

#### Acceptance Criteria
1. When a discovered plugin offers an object that does not satisfy the calculator contract (a missing or wrongly-typed identity attribute, or a missing required method), the fitdocs CLI shall reject it, record a plugin load error naming the plugin and what the object is missing, and leave it unregistered.
2. If loading a plugin raises an error (import failure, syntax error, or an error raised during its registration), the fitdocs CLI shall record a plugin load error naming the plugin and the error, and shall continue discovering, validating, and registering all remaining plugins.
3. If a plugin claims a calculator id that is already registered, the fitdocs CLI shall keep the existing registration, reject the new one, and record a plugin load error naming the contested id and both origins.
4. The fitdocs CLI shall register every built-in calculator regardless of how many plugins fail to load.
5. The fitdocs CLI shall never abort a run and never change the exit code of an otherwise-successful run because a plugin failed to load; plugin load errors are reported through the established warning channel, not as failures.
6. When a run finishes and any plugin failed to load, the fitdocs CLI shall report each failed plugin by name with its reason in the run's output.
7. If a registered plugin calculator raises an error while computing load for a document, the fitdocs CLI shall handle it through the existing per-document failure channel: that document is reported as failed with the reason, and every other document is processed normally.

### Requirement 4: Inspecting Discovered Plugins
**Objective:** As a user who just installed or wrote a calculator, I want one command that tells me what fitdocs sees, so that I can confirm my plugin is live or find out exactly why it is not.

#### Acceptance Criteria
1. When the user runs the plugins command, the fitdocs CLI shall list every registered calculator with its id, display name, version, origin, and supported modalities.
2. The fitdocs CLI shall report each calculator's origin as one of: built-in, an installed distribution (named), or a local plugin file (named by path).
3. The fitdocs CLI shall report the version of a distribution-provided calculator as that distribution's version, the version of a built-in as the fitdocs version, and shall report a local plugin file's version as unknown rather than fabricating one.
4. When any plugin failed to load, the plugins command shall list each failure with the plugin's name or source and the reason it was rejected.
5. When no third-party plugins are installed or configured, the plugins command shall list the built-in calculators and report that no plugin load errors occurred.
6. The plugins command shall exit successfully whenever it produced a listing, including when plugin load errors are present, so that it remains usable as a diagnostic.
7. If the data root cannot be resolved, the plugins command shall still list built-in and distribution-provided calculators, state that no local plugin configuration was consulted, and exit successfully.
8. The plugins command shall perform no network access and shall write nothing to the data root.

### Requirement 5: Typed, Versioned Public API for Plugin Authors
**Objective:** As a plugin author, I want a documented, type-checked contract to build against, so that my calculator keeps working across fitdocs upgrades and my editor and type checker understand fitdocs types.

#### Acceptance Criteria
1. The distributed fitdocs package shall ship its type information so that a third-party plugin importing fitdocs types type-checks under a strict type checker without suppressions or stub packages.
2. The fitdocs documentation shall define the public import surface available to plugin authors, covering at minimum the activity model and derived-metric types, the calculator contract, the athlete-input declaration type, the interaction primitives, the complete outcome set, and registration.
3. The fitdocs documentation shall state that anything outside the documented public surface is internal and may change without notice, explicitly including the bundled calculator implementation, which is not part of the plugin-author surface and may be absent from a given distribution.
4. The fitdocs documentation shall state the compatibility policy for the public plugin surface in terms of the package's released version numbering, including what an author may rely on within a compatible range and what constitutes a breaking change.
5. While a plugin imports only documented public names, upgrading fitdocs within the stated compatible range shall not require changes to that plugin.
6. The fitdocs CLI shall keep every existing documented public name importable and shall introduce contract changes only additively, so that existing calculators — including the shipped one — continue to satisfy the contract unchanged.

### Requirement 6: Plugin Authoring Guidance
**Objective:** As a developer who wants to contribute a methodology, I want a worked example that takes me from empty directory to a calculator fitdocs discovers, so that I can ship one without reverse-engineering the codebase.

#### Acceptance Criteria
1. The fitdocs documentation shall provide an end-to-end worked example of a packaged third-party calculator, covering the package layout, how the calculator is advertised for discovery, installation, and verification with the plugins command.
2. The fitdocs documentation shall document the local plugin file path alternative alongside the packaged route, including when to choose each.
3. The fitdocs documentation shall state the recommended naming convention for published calculator distributions and the requirement that a calculator id be short, stable, and unique across everything the user has installed.
4. The fitdocs documentation shall describe what a user sees when a plugin fails to load and how to diagnose it with the plugins command.

### Requirement 7: Preserved Guarantees
**Objective:** As an existing user, I want the plugin layer to cost me nothing, so that adding an extension point does not compromise the tool's offline, deterministic, dependency-light behavior.

#### Acceptance Criteria
1. The fitdocs CLI shall discover and load plugins without any network access.
2. The fitdocs tool shall add no new third-party runtime dependency in order to support plugin discovery.
3. While no third-party calculators are installed and no local plugins are configured, repeated runs over the same inputs shall produce byte-identical documents and assets, unchanged from the behavior before this feature.
4. The fitdocs CLI shall keep the shipped withdrawn calculator's registration, selection, and computed results unchanged.
5. The fitdocs CLI shall confine plugin discovery to load calculators; no other part of the pipeline shall become extensible as a side effect of this feature.
