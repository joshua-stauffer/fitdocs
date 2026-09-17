# Requirements Document

## Project Description (Input)

fitdocs works, but nobody can install it. The README still says "no installable
package yet": the version is a static `0.1.0` that only an installed
distribution can report, there is no release process, no changelog, no stated
compatibility policy, no upgrade or uninstall story, and no packaging of the
wiki-integration surface — the recipe by which an LLM-managed markdown wiki
adopts fitdocs as a first-class input path.

Meanwhile the three Phase 3 sibling specs have just defined the interfaces that
make fitdocs installable as a *plugin* rather than a personal script: the
document/ownership contract (wiki-contract), the configured inbox interface
(inbox), and the load-calculator plugin API (plugin-api). Those three contracts
are the public API. This feature ships them as one coherent, versioned product:
a package published to PyPI that `uv tool install fitdocs` or `pipx install
fitdocs` just works with; a version the tool reports about itself consistently;
a changelog and a written compatibility policy that says what version numbering
governs and what is internal churn; install, upgrade, and uninstall
documentation for both standalone use and pkm-style wikis; an agent skill so an
LLM-managed wiki gets a turnkey "process the fitdocs inbox" workflow; and
contribution documentation for community calculator authors. A repeatable,
gated release process — test, build, verify, tag, changelog, publish — replaces
the current absence of one.

One hard external gate: no public artifact may contain the withdrawn
methodology's lookup tables or name without the third party's sign-off, or
with the calculator replaced by an unencumbered one (see the reference
writeup, recorded in the purge's provenance record). Resolving that licensing question
is out of scope here. This feature treats it purely as a release gate that must be
mechanically satisfied before anything is published, and makes shipping without
a bundled methodology a supported configuration by leaning on plugin-api's
local-plugin escape hatch.

In scope: package metadata and build; the PyPI release process and its
automation; version single-sourcing and self-reporting; version-numbering,
changelog, and the published compatibility policy over the three contracts;
install/upgrade/uninstall documentation for standalone and pkm-style wikis;
agent-skill (SKILL.md) packaging; contribution documentation; the release
checklist that enforces the licensing gate.

Out of scope: resolving the third party's licensing question itself; the content of the
three contracts (owned by wiki-contract, inbox, and plugin-api); new product
features; an MCP server; an Obsidian-specific plugin; a marketing site; any
auto-update mechanism.

Full discovery context: `brief.md` in this directory.

## Introduction

distribution turns a working local tool into a released product. Nothing about
what fitdocs *does* changes; what changes is that a stranger can install it, an
existing user can upgrade it without fear, a plugin author can depend on it, and
an agent-managed wiki can adopt it from a documented recipe instead of by
reading the source.

The organizing idea is that fitdocs' public API is not its Python modules but
its three contracts: the generated-document and ownership contract, the inbox
interface, and the load-calculator plugin API. Those are what version numbering
governs and what the changelog reports on; everything behind them is internal
churn that a release may change freely. This spec publishes that policy, builds
and ships the artifact that carries it, and documents the install, upgrade, and
uninstall paths — including the wiki-integration path, where the deliverable is
an agent skill that teaches an LLM wiki maintainer to drain the inbox and to
respect the ownership boundary fitdocs declares in the tree.

Publication is gated. Beyond the ordinary quality gates, one gate is
non-negotiable and external to this spec: the bundled training-load methodology
is encumbered, and no artifact carrying its tables or its name may be published
until redistribution permission is recorded or the methodology is replaced.
Because the plugin API already supports supplying a calculator from outside the
package, "released with no bundled methodology" is a first-class supported
configuration rather than a degraded one, and this spec requires it to work and
to be documented.

## Boundary Context

- **In scope**: the published package and its metadata; what the built
  artifacts must and must not contain; version single-sourcing and consistent
  self-reporting; the written compatibility policy over the three public
  contracts and the version-numbering rules that back it; the changelog and its
  obligations; the end-to-end release procedure, its quality gates, its
  artifact verification, its tagging, its rehearsal path, its credential
  posture, and its post-publication check; the licensing release gate and the
  supported no-bundled-methodology configuration; install, upgrade, and
  uninstall documentation for standalone and wiki-hosted data roots; the agent
  skill that packages the inbox workflow for an LLM-managed wiki and the
  integration recipe that accompanies it; contribution documentation for the
  project and for authors publishing their own calculator distributions.
- **Out of scope**: the content and semantics of the three public contracts —
  the document/ownership contract and its inspection command (wiki-contract),
  the inbox interface, its settings, and its quarantine behavior (inbox), and
  plugin discovery, the typed public import surface, and the plugin-author
  guide (plugin-api); the training-load calculator-authoring guide
  (training-load); resolving the methodology's licensing question or
  negotiating permission; replacing or reimplementing the methodology; new
  product features or CLI commands beyond what the released surface already
  provides; an MCP server, an editor-specific plugin, a hosted service, or a
  marketing site; any self-update or auto-update mechanism; publishing
  third-party calculator distributions on their authors' behalf.
- **Adjacent expectations**: wiki-contract supplies the document-format version,
  the ownership-contract version, the emitted in-tree ownership declaration,
  and the read-only inspection command — this feature cites them in the
  compatibility policy, the upgrade documentation, and the agent skill, and
  changes none of them. inbox supplies the configured inbox, the no-argument
  drain, and the never-delete disposition policy — this feature documents them
  as the integrator's interface and drives the agent skill from them. plugin-api
  supplies the entry-point group, the local-plugin escape hatch, the shipped
  type information, and the wording of the plugin-surface compatibility
  statement — this feature carries that statement into one project-wide policy
  and makes the release process enforce it. A pre-wave
  settings foundation supplies the settings-file location constant, its
  data-root-relative path resolver, and the shared loader that parses
  `<data-root>/fitdocs.toml` once and raises a single settings error for
  file-level problems; each per-table reader (`[tiles]`, `[inbox]`,
  `[plugins]`) stays with its owning feature. This feature documents that
  file as one user-facing schema and treats the loader and the layout module
  as internal. workout-docs and route-maps own the
  behavior statements currently living in the README (data-root precedence,
  tile opt-out, attribution), and wiki-contract, inbox, and plugin-api each
  publish their own README section (ownership, inbox, plugins);
  reorganizing that material into user-facing documentation must preserve
  every one of those statements. Apart from documentation,
  packaging metadata, and version reporting, installed behavior for unchanged
  inputs is unchanged.

## Requirements

### Requirement 1: Installable, Publishable Package
**Objective:** As someone who wants to use fitdocs, I want to install it with
one standard command, so that I can run it without cloning a repository or
knowing anything about its build.

#### Acceptance Criteria
1. The fitdocs project shall publish a distribution to the public Python package index under a stable distribution name, installable with the standard isolated-application installers.
2. When a user installs the published distribution, the fitdocs command shall be available as a single console entry point and every documented command shall run without further setup.
3. The published distribution shall declare its supported Python versions, its runtime dependencies, its license, its summary and long description, and links to its source and its documentation.
4. The fitdocs project shall publish, for every release, both a source distribution and a built distribution.
5. The published distribution shall contain every file the installed tool reads at runtime, including bundled calculator lookup data and the type-information marker that the plugin API requires.
6. The published distribution shall contain no development-only material: no tests, no specification or steering documents, no dependency lockfile, no methodology source spreadsheets, and no personal fitness data.
7. Installing or upgrading the published distribution shall create no directory, configuration file, profile, or data root anywhere on the user's machine.
8. The published distribution shall carry a license file whose terms match the license the package metadata declares.
9. Any documentation reference carried inside a published artifact, or emitted by the tool into a user's tree, shall address the documentation by its published project URL rather than by a repository-relative path, and the package metadata shall declare the project URLs those references depend on.

### Requirement 2: Version Identity and Self-Reporting
**Objective:** As a user or plugin author diagnosing behavior, I want the
installed tool to tell me exactly which release I am running, so that a bug
report, a compatibility claim, or a changelog lookup is unambiguous.

#### Acceptance Criteria
1. The fitdocs project shall declare the released version in exactly one place, and every surface that reports a version shall derive it from that declaration.
2. When a user asks the installed tool for its version, the fitdocs CLI shall report the version of the installed distribution.
3. The fitdocs CLI shall report the same version wherever a version appears: in its version output, in how it identifies itself to any external service it contacts, and as the reported version of its built-in calculators.
4. If the version cannot be determined because the tool is running from an uninstalled source tree, the fitdocs CLI shall report that the version is unknown rather than a fabricated one, and shall continue to operate normally.
5. The fitdocs project shall publish each version number exactly once and shall never alter or republish an already-released version.
6. The version reported by the installed tool shall match the version recorded in the changelog entry and in the release tag for that release.

### Requirement 3: Compatibility Policy over the Published Contracts
**Objective:** As a user upgrading fitdocs, or an author whose calculator
depends on it, I want a written statement of what the version number promises,
so that I can upgrade — or declare a supported range — without reading the
source.

#### Acceptance Criteria
1. The fitdocs documentation shall publish a compatibility policy naming the public contracts that version numbering governs — the generated-document and ownership contract, the inbox interface, and the load-calculator plugin API — and shall state that everything outside them is internal and may change in any release.
2. The compatibility policy shall define, for each named contract, what constitutes a breaking change, what constitutes an additive change, and what constitutes internal change.
3. The compatibility policy shall state the version-numbering rules that apply before the first stable release and the rules that apply from the first stable release onward.
4. The compatibility policy shall state how a change to the generated-document format version, to the ownership-contract version, or to the user-owned settings schema is reflected in the released version number, and what action, if any, the user must take.
5. While a user's settings file, athlete profile, and local plugins are unchanged, upgrading within the range the policy calls compatible shall require no edit to any of them.
6. The compatibility policy shall state how a deprecation is announced and the minimum notice a deprecated part of a public contract receives before removal.
7. The compatibility policy shall be reachable from the project's readme and shall be the single statement that the plugin-author documentation and the contribution documentation both refer to.
8. The compatibility policy shall govern the user-facing settings schema as a named public contract, covering every settings table the tool reads — the tile table alongside the inbox and plugin tables — and shall define what a breaking, an additive, and an internal change to that schema is.
9. The compatibility policy shall carry the project's single statement of what is public and what is internal, naming the plugin API's enumerated import surface as the authority for the public names and stating that every other module — including the document-contract, inbox, plugin-discovery, and version-resolution modules — is internal regardless of where it is imported from.
10. The compatibility policy shall state the project-wide rule that decides whether a command requires a resolved data root: a command that describes the installed tool requires none, while a command that describes or changes a tree requires one.

### Requirement 4: Changelog
**Objective:** As a user deciding whether to upgrade, I want a per-release
account of what changed and what it costs me, so that I never have to diff
releases to find out.

#### Acceptance Criteria
1. The fitdocs project shall maintain a changelog that records every released version with its version number and release date, newest first.
2. Each release entry shall group its changes by kind, distinguishing at minimum added, changed, deprecated, removed, and fixed behavior.
3. When a release changes any contract named in the compatibility policy, its changelog entry shall say so explicitly, name the contract, and state the action a user or plugin author must take.
4. The changelog shall carry an unreleased section that accumulates entries as changes are made, so that a release entry is assembled rather than reconstructed at release time.
5. The changelog shall describe changes in terms of user-observable behavior rather than reproducing commit messages.
6. The changelog shall be included in the published distribution or reachable from a link the published distribution carries.
7. If the changelog has no entry for the version being released, or its newest released entry does not match that version, the release shall not proceed.

### Requirement 5: Repeatable, Gated Release Process
**Objective:** As the maintainer, I want a release procedure with gates I cannot
skip by accident, so that every published version is tested, verified, and
traceable, and a failed step never reaches the public index.

#### Acceptance Criteria
1. The fitdocs project shall document a release procedure that one maintainer can follow end to end, listing every step in order with the command for each.
2. Before any artifact is published, the release procedure shall require the full test suite, the linter, and the strict type check to pass on the exact revision being released.
3. The release procedure shall verify the built artifacts by installing them into a clean, isolated environment and exercising the installed console command there, rather than by exercising the working tree.
4. The release procedure shall verify that the built artifacts contain exactly the files Requirement 1 requires them to contain and none of the files it forbids.
5. The release procedure shall record the released revision with a version tag that matches the released version number.
6. The release procedure shall provide a rehearsal path that exercises building and publishing without affecting the public index.
7. Publication shall authenticate with short-lived, per-release credentials rather than a long-lived secret stored in or alongside the project.
8. If any gate fails, the release procedure shall stop before publication and leave the public index unchanged.
9. After publication, the release procedure shall confirm that the published version installs from the public index and reports the expected version.
10. The release procedure shall be runnable as project automation triggered by the release tag, and its gates shall be the same gates a maintainer running it by hand would apply.

### Requirement 6: Methodology Licensing Release Gate
**Objective:** As the maintainer, I want publication mechanically blocked while
the bundled methodology's redistribution permission is unresolved, so that a
licensing question can never be lost to a moment of inattention.

#### Acceptance Criteria
1. The fitdocs project shall publish no artifact containing the encumbered training-load methodology's lookup tables, its name, or its trademarked terms unless permission covering redistribution has been recorded as granted, or the methodology has been replaced with an unencumbered one.
2. The release procedure shall inspect the built artifacts for that encumbered material and shall stop the release before publication when the material is present and permission is not recorded as granted.
3. The fitdocs project shall record the state of that permission in a single place that the release gate reads, so that the gate's decision is explicit rather than remembered.
4. Where no training-load methodology is bundled, the fitdocs tool shall remain fully functional for every capability except load computation, shall state in its output that no calculator is available rather than failing, and shall keep its exit-code contract unchanged.
5. The fitdocs documentation shall explain how a user obtains and installs a training-load methodology when the release bundles none.
6. Removing a bundled methodology from a release, or restoring one, shall be treated as a change to a public contract and recorded in the changelog with the action the user must take.
7. The release gate shall inspect the artifacts themselves rather than the source tree, so that material reaching a distribution by an unexpected path is still caught.
8. Where no training-load methodology is bundled, the load package shall not export the bundled calculator's name and shall omit it from its declared public names, while every other documented public name of that package remains importable — including by wildcard import.

### Requirement 7: Install, Upgrade, and Uninstall Documentation
**Objective:** As a new or existing user, I want documentation that takes me
from nothing to a generated workout document and tells me exactly what an
upgrade or an uninstall will do, so that adopting fitdocs into a wiki I care
about is not an act of faith.

#### Acceptance Criteria
1. The fitdocs documentation shall provide a first-run path from installation to a generated workout document, covering installing the tool, choosing and pointing at a data root, getting source files where fitdocs will find them, and running the tool.
2. The documentation shall cover both a standalone data root and a data root inside an existing markdown wiki, and shall state what differs between the two.
3. The documentation shall state the exact commands to upgrade the installed tool and to uninstall it.
4. The documentation shall state what an upgrade does not touch: user-owned document regions, the user-owned settings file, the athlete profile, local plugin files, and the archived source files.
5. When an upgrade changes the generated-document format, the documentation shall name the single command that brings existing documents current, and shall state that no other user action is required.
6. The documentation shall state what remains on disk after uninstalling, and that generated documents, archived sources, settings, and profile are unaffected by uninstalling.
7. The documentation shall keep the data-root contract prominent, including its resolution order, its loud failure when unresolved, and the guarantee that fitdocs never writes into a code repository by default.
8. The documentation shall state what the tool does offline, what network access it can make, and how to switch that access off — preserving every such statement the project already publishes.
9. The documentation shall be organized so that a reader can find installation, configuration, the inbox interface, the ownership contract, the plugin platform, and the compatibility policy from a single entry point.

### Requirement 8: Wiki Integration Packaging
**Objective:** As someone running an LLM-managed markdown wiki, I want fitdocs
to arrive with a ready-made agent workflow, so that my wiki's agent can process
new workouts and respect the ownership boundary without me writing the
instructions myself.

#### Acceptance Criteria
1. The fitdocs project shall publish an agent skill that gives an LLM-managed markdown wiki a turnkey workflow for processing the fitdocs inbox.
2. The agent skill shall state when it applies, the commands to run, how to interpret every reported outcome channel — written, skipped, failed, deferred, quarantined, moved, files whose move failed, and warnings — and what to do about files the tool deferred, quarantined, failed on, or could not move.
3. The agent skill shall state the ownership boundary — that the fitdocs-owned tree is tool-owned, which document regions the wiki's author owns, and that generated content is never hand-edited — and shall point at the ownership declaration fitdocs emits inside the owned tree as the authority for it.
4. The agent skill shall not restate the ownership contract's enumerated content; where detail is needed it shall refer to the emitted declaration and the published contract.
5. The agent skill shall be readable and usable as plain markdown instructions by a human, and by an agent environment that does not support the packaged skill format.
6. The fitdocs documentation shall state where to install the agent skill, how to verify it is active, and how to update it when fitdocs is upgraded.
7. The fitdocs documentation shall provide an integration recipe for adopting fitdocs into an existing agent-managed wiki, covering installation, pointing the data root at the wiki, configuring the inbox, running the first drain, and confirming the result.
8. The agent skill shall be released together with the tool and carry the released version, and every command, option, and reported outcome channel it names shall exist in that release's command surface and in that release's reported outcomes.
9. *(added by Amendment 1)* The distribution shall package more than one agent skill under one skills location, shall list the packaged skills on request, shall report one skill's location by name, and criterion 8.6's install/verify/update documentation obligation shall apply to every packaged skill.

### Requirement 9: Contribution Documentation
**Objective:** As someone who wants to contribute to fitdocs or to publish my
own calculator, I want the project's expectations written down, so that I can
make a change that is accepted and a package that keeps working.

#### Acceptance Criteria
1. The fitdocs documentation shall describe the contributor path: setting up the development environment, running the test suite, the linter, and the strict type check, and what must pass before a change is accepted.
2. The contribution documentation shall state that a user-visible change requires a changelog entry, and that a change touching any contract named in the compatibility policy requires that policy to be applied to the version number.
3. The contribution documentation shall state which parts of the project are public and which are internal, consistent with and referring to the compatibility policy rather than restating it.
4. The contribution documentation shall guide an author publishing their own calculator distribution on declaring the range of fitdocs versions they support, verifying against a released version, and what the compatibility policy guarantees them — without duplicating the plugin-authoring instructions the plugin documentation already owns.
5. The contribution documentation shall state that material encumbered by a third party's license or trademark must not be added to the repository or to any published artifact without recorded permission.

### Requirement 10: Preserved Guarantees
**Objective:** As an existing user, I want packaging and release to cost nothing
in behavior, so that becoming installable does not make fitdocs heavier, less
private, or less predictable.

#### Acceptance Criteria
1. The fitdocs tool shall add no new runtime dependency in order to become publishable, installable, or self-reporting.
2. The installed tool shall behave identically to the revision that passed the release gates; no build step shall alter behavior between the tested revision and the published artifact.
3. No published artifact shall contain personal fitness data, generated workout documents, or the contents of any data root.
4. Running the installed tool shall require no network access beyond the map-tile requests the project already documents, and the release process shall not introduce any new runtime network access.
5. Building the same tagged revision twice shall produce artifacts with identical contents.
6. Reorganizing the project's documentation shall preserve every behavior statement the project publishes at the time of the reorganization — its own and its sibling features' — including data-root resolution order, the persistent tile opt-out, tile-provider attribution, the inbox never-delete guarantee, the statement that fitdocs performs no watching and no scheduling, and a pointer to the published ownership contract.
7. Rewriting the readme shall preserve rather than replace the sections other features publish there — the ownership section, the inbox section, and the plugins section — either keeping each in place or relocating each into the documentation set with the readme linking to it.

## Amendment 1 (2026-09-16): a second packaged skill, located by name, landed by build-training-block

`build-training-block` lands, at implementation time, the by-name skill
locator, the `skill` command and the generalized conformance test this
spec's major 4 had not yet shipped (distribution was `tasks-generated` with
0 of 33 tasks done at that base) — so that its own skill consumes them
instead of re-adding a single-skill version. That spec owns its skill's
content, its example plan source, and the frame of the generalized
conformance test; this spec owns only the by-name locator (published in
code as the registry `PACKAGED_SKILLS`, with `skill_root(name)`,
`skill_file(name)` and `skill_files(name)`), the `skill` command, the
artifact policy's required-member set and the version-identity guarantee it
extends — the registry replacing the single-name constant, the `skill
[NAME]` command's listing and by-name forms, the artifact policy's
required-member set gaining `build-training-block`'s two files
(`fitdocs/skills/build-training-block/SKILL.md` and
`fitdocs/skills/build-training-block/example-block.toml`) now and this
spec's own inbox skill's `SKILL.md` when task 4.2 lands it, and the
statement that one `metadata.version` per registered skill is a permitted
copy of the released version, not a second declaration — recorded here as
Requirement 8 criterion 8.9. No criterion is renumbered. This is the
roadmap's Phase 7
Existing Spec Update for this spec.
