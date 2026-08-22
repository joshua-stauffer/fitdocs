# Implementation Plan

> Sequencing precondition: this plan is Wave 2 of Phase 3 and builds on the
> implemented wiki-contract, inbox, and plugin-api specs. The emitted in-tree
> ownership declaration, the published ownership contract, the `check` command,
> the configured inbox and its no-argument drain, the plugin entry-point group,
> the `plugins` command, the documented public import surface, and the
> `py.typed` marker must all be in place before these tasks start — the artifact
> policy, the compatibility policy, and the agent skill all reference them. The
> pre-wave settings foundation (the settings-file constant, its data-root-relative
> path resolver, and the shared parse-once loader with its single file-level
> error) is likewise already in place; this plan governs the resulting settings
> *schema* in the compatibility policy and treats the loader and the layout
> module as internal, changing neither.
>
> Ordering rule from the design's Migration Strategy: **no publication of any
> kind may be attempted before task 3.2 passes.** Until the licensing gate can
> refuse an artifact, the project can build things it must not publish. Nothing
> in this plan may change a generated document's bytes; a golden diff at any
> point is a defect, not expected churn.
>
> Deliberate deviation from the usual code-only task rule: Requirements 3, 4, 5,
> 7, 8, and 9 are themselves documentation and release-process deliverables —
> the compatibility policy, the changelog, the release procedure, the user
> documentation, the agent skill, and the contribution guide are the feature.
> They appear as tasks, each paired with the conformance test or gate that keeps
> it honest, following the precedent set by the published ownership contract.

- [ ] 1. Foundation: version identity, package manifest, and policy data
- [ ] 1.1 Consolidate version resolution behind one leaf
  - A pure module holding the distribution name, a resolver returning the installed version or an absent value, and a display form that falls back to a fixed unknown token; the lookup happens at the point of use, never at import time, because reading distribution metadata is measurably slow for a command-line start-up
  - The three existing unguarded call sites converge on it: the version flag, the tile user-agent, and the plugin listing's built-in version. The listing keeps an absent version absent rather than substituting the token, because the plugin surface forbids fabricating one
  - The module imports nothing from the package and is not added to the documented public import surface — it is internal
  - Observable: unit tests cover the resolved and unresolved paths with the metadata lookup patched, running the command from an uninstalled checkout prints the unknown token and exits successfully instead of raising, and a repository scan finds the released version literal only in the manifest and in the two places that are checked against it for equality — the changelog's newest entry and the agent skill's recorded version — and nowhere else
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - _Boundary: VersionSource, CliApp, TileStore, PluginDiscovery_

- [ ] 1.2 Complete the package manifest and add the license file
  - Full package metadata: authors, keywords, classifiers, the license file declaration, and project links for source, documentation, changelog, and issues; the version stays static and stays the single declaration
  - The project links must additionally resolve every documentation page that a **shipped or emitted** artifact points at — the ownership contract, the plugin platform, the inbox, and configuration — because no artifact ships `docs/` and the ownership declaration is emitted into a user's tree that has no repository; the rule those references follow is project-URL form, never a repository-relative path
  - An explicit source-distribution allowlist replacing the build backend's default inclusion, so the archive carries the manifest, the readme, the license, the changelog, and the package tree and nothing else; the wheel target's contents stated explicitly rather than implied
  - A license file whose terms match the declared license
  - The runtime dependency list is unchanged — becoming publishable must cost no new dependency
  - Observable: a build produces one wheel and one source distribution; the source distribution contains no tests, specifications, steering documents, reference material, lockfile, spreadsheet, or activity file; the declared dependency list is byte-identical to the previous revision's; every documentation page a shipped or emitted artifact references has a declared project URL
  - _Requirements: 1.1, 1.3, 1.4, 1.6, 1.8, 1.9, 10.1_
  - _Boundary: PackageManifest_

- [ ] 1.3 (P) Establish the changelog
  - A changelog in the established human-written format: a standing unreleased section, releases newest first with version and date, and the six canonical change categories
  - An initial unreleased entry describing the work this phase delivers, written in terms of user-observable behavior rather than commit subjects
  - The convention recorded in the file itself that an entry touching a governed contract names the contract and the action the user or plugin author must take
  - Observable: the file parses under the format's heading conventions, carries an unreleased section, and its category names match the format exactly
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
  - _Boundary: Changelog_

- [ ] 1.4 Declare the release policy data
  - A licensing record naming the bundled methodology, its branded name, the recorded permission state, the evidence reference, and the paths an unencumbered build prunes — the single place the release gate reads its licensing decision from
  - An artifact policy declaring, per artifact kind, the members a release must contain, the member patterns it must never contain (tests, specifications, reference material, lockfiles, spreadsheets, activity files, data-root paths), the content markers that indicate encumbered material, and the metadata fields a release must declare
  - Required members are split into those every profile must carry and those required **only when a methodology is bundled**, so an unencumbered artifact is legal rather than a missing-member violation; the source-distribution member set must mirror the allowlist declared in task 1.2, and the license and changelog files it names are created by tasks 1.2 and 1.3
  - The packaged agent skill is deliberately **not** listed as a required member here — it does not exist yet, and task 4.2 adds its entry when it lands
  - Both files are pure data with no expressions or environment lookups, and neither ships in any artifact; the marker list carries branded terms only and never the bare calculator id, which is not a trademark and must stay usable
  - Observable: reader unit tests show a missing required key and a wrongly-typed value each raise, an unknown key is tolerated, and a permission recorded as granted with empty evidence is itself treated as a violation
  - _Requirements: 1.5, 1.6, 5.4, 6.3, 10.3_
  - _Boundary: LicensingRecord, ArtifactPolicy_
  - _Depends: 1.2, 1.3_

- [ ] 2. Release tooling
- [ ] 2.1 (P) Build the release artifact builder with its two profiles
  - Profile selection from the licensing record: the bundled profile builds from the working tree, the unencumbered profile builds from a temporary copy with the recorded prune paths removed, so the working tree is never modified
  - One invocation produces both a wheel and a source distribution into a cleared output directory, through the existing build front end with no build hooks and no code generation, so the artifact is the tested revision
  - A deterministic timestamp source so the same revision under the same profile builds to identical archive contents
  - A licensing record claiming permission without evidence is a hard error before any build begins
  - Observable: both profiles build successfully; the unencumbered wheel's member set differs from the bundled one by exactly the pruned paths; building the same profile twice yields archives with identical member names and identical member digests
  - _Requirements: 1.4, 10.2, 10.5_
  - _Boundary: ReleaseBuilder_
  - _Depends: 1.4_

- [ ] 2.2 (P) Build the artifact conformance checker
  - A read-only pass that opens each built artifact, enumerates its members, and reads its distribution metadata, then applies three checks and reports every violation rather than stopping at the first: required members present per artifact kind, no forbidden member present, and every required metadata field declared and non-empty
  - Each violation names the subject it concerns, what was observed, and the action that resolves it; violations sort deterministically; the pass writes nothing and exits successfully only when clean
  - The finding type follows the project-wide report vocabulary for Phase 3: fields named `(subject, detail[, remedy])` — the artifact filename is the `subject`, not a field called `artifact` — and classification enums are `StrEnum`, which both `ViolationKind` and the builder's `Profile` already are
  - A missing or malformed policy or licensing file is a hard error, never a silently skipped check
  - Observable: fixture archives trip each violation kind exactly once and a clean archive trips none; running the pass twice over the same artifacts produces the same violations in the same order
  - _Requirements: 1.3, 1.5, 1.6, 5.4, 10.3_
  - _Boundary: ArtifactChecker_
  - _Depends: 1.4_

- [ ] 2.3 Add the encumbered-content gate to the checker
  - A marker scan over every text-like member and over the distribution metadata — the metadata matters because the long description is the readme rendered into it, and a member-name-only scan would let branded prose through
  - A marker match is a violation unless the licensing record states permission was granted; binary members are matched by name only so the scan stays fast and cannot produce spurious matches
  - The gate reads the artifacts alone and never consults the source tree, because the encumbered material reaches a distribution by two different mechanisms and only the archive shows what actually happened
  - Observable: a bundled-profile artifact fails the gate while permission is recorded as not granted, an unencumbered-profile artifact passes it, and a marker present only in the distribution metadata is caught with its artifact and remedy named
  - _Requirements: 6.1, 6.2, 6.7_
  - _Depends: 2.2_

- [ ] 2.4 Add the version-consistency gate
  - A check needing no artifact opened: the manifest version, the changelog's newest released entry, and the release tag when one is supplied must all agree
  - Each pairwise disagreement produces one violation naming both values; a changelog with no entry for the version being released is a violation in its own right
  - Observable: agreement passes cleanly, and each of the three possible disagreements produces exactly one violation naming both conflicting values
  - _Requirements: 2.6, 4.7_
  - _Depends: 1.3, 2.2_

- [ ] 3. Shipping without a bundled methodology
- [ ] 3.1 Make the bundled methodology optional at the package level
  - The built-in registration becomes a guarded import: when the methodology package is absent from the installed distribution the registry starts empty, the import succeeds, and the absence is never reported as a failure; no other module may import the methodology package directly, so the guard is the single point of tolerance
  - The remaining consequences are already handled by the existing design — calculator selection finds no candidate, the load region carries the established not-computed placeholder, and the exit-code contract is unchanged
  - The bundled calculator's **name is conditionally exported**: today the package imports it, lists it in `__all__`, and registers it at import time, so an unencumbered wheel would break `from fitdocs.load import *` and every documented import through the package. Under the guard the name is bound only when the import succeeded, and `__all__` is assembled so the name is present exactly when the object is — absent from `__all__` in an unencumbered build, unchanged in a bundled one. The bundled calculator is not part of the public surface (the plugin API's enumeration excludes it), so its conditional absence is not itself a contract change; whether a methodology is bundled at all is, and the changelog records that
  - The branded example in the calculator-selection help text is replaced with a methodology-neutral one, and any remaining branded prose outside the methodology package is neutralized, so an unencumbered artifact carries no protected term
  - When the methodology is present, registration order, selection, computed results, and the exported name set are unchanged
  - Observable: the existing load suite passes unchanged with the methodology present, and with the methodology package removed the load package imports successfully, yields an empty registry, `from fitdocs.load import *` succeeds, every enumerated public name of the package still imports, and the calculator's name is absent from `__all__` rather than present and unresolvable
  - _Requirements: 6.1, 6.4, 6.8_
  - _Boundary: BuiltInRegistration, CliApp_

- [ ] 3.2 Validate the unencumbered release end to end
  - Build the unencumbered profile, run the conformance and licensing gates over it, then install the resulting wheel into a clean isolated environment and run a full ingestion over a fixture source
  - Assert the installed tool writes documents, states in its output that no calculator is available, leaves the load region carrying the not-computed placeholder, and exits successfully
  - In that same installed environment assert the public surface holds: a star-import of the load package succeeds and every name the plugin API enumerates as public for that package is importable — the profile in which a broken export list would otherwise ship unnoticed
  - This is the checkpoint the migration strategy names: after it, an unpublishable artifact is a failing check rather than a judgement call, and no publication of any kind may be attempted before it passes
  - Observable: the unencumbered artifact passes every gate with permission recorded as not granted, the installed unencumbered tool completes a sync successfully with no calculator registered, and a star-import plus every documented public name of the load package resolve in that install
  - _Requirements: 6.2, 6.4, 6.8_
  - _Depends: 2.1, 2.3, 3.1_

- [ ] 4. Agent skill packaging
- [ ] 4.1 Add the skill locator and the read-only skill command
  - A leaf holding the skill's canonical name and resolving the packaged skill directory through the same resource mechanism the bundled tables already use, so it works from a wheel install, a source checkout, and an isolated tool environment alike; an absent skill resolves to an absent value rather than raising
  - A command that prints the packaged skill directory's absolute path plus a one-line copy recipe and exits successfully; it resolves no data root, loads no profile, builds no tile store, runs no engine, and writes nothing — the tool never installs into a location it does not own
  - An absent skill in an installed distribution is reported through the existing configuration-error path, because it means the install is incomplete rather than that the user erred
  - The command list and exit-code contract in the module docstring are amended; the exit-code contract itself is unchanged. The docstring also records the project-wide data-root posture rule in code — commands that describe the installed tool need no data root, commands that describe or change a tree require one — and this command is an instance of the first half, consistent with the plugin listing and deliberately unlike the contract check
  - Observable: with the skill directory scaffolded (its content is task 4.2's), the command prints an existing directory whose final path component equals the canonical skill name and exits successfully; with the directory absent, it exits with the configuration-error status and an instructive message
  - _Requirements: 8.1, 8.6_
  - _Boundary: AgentSkillLocator, CliApp_

- [ ] 4.2 Author the agent skill and its conformance test
  - Frontmatter conforming to the open standard's field contract: a name equal to the containing directory and to the locator's constant, a description within the published length limit stating both what the skill does and when to use it, the licence identifier, a compatibility note requiring the command to be installed and reachable, and the released version carried under the metadata map because the standard defines no top-level version field
  - A body covering, in order: when the skill applies, the commands to run and in what order, how to read **every** reported channel — written, skipped, failed, deferred, quarantined, moved, **move failures**, and warnings — and what to do about each: a deferred file needs no action, a quarantined file needs the user rather than the agent, and a move failure means the file was processed successfully and will be retried on the next drain, so it is never a reason to reprocess anything. The channel list is the drain report's own set; the move-failure row is a channel in its own right and an enumeration that omits it teaches an agent to misread a clean run
  - Any documentation the skill points at is referenced by its published project URL, never by a repository-relative path — the skill ships inside the wheel and is copied into an agent's tree, where no repository exists
  - An ownership section that states the boundary and then defers: it names the in-tree ownership declaration as the authority and the published contract as the detail, and enumerates no owned paths, region identifiers, or managed frontmatter keys, so the skill cannot drift when those enumerations change
  - Plain markdown with no client-specific syntax and no pre-approved-tools declaration, so a human or a non-supporting agent environment can follow it directly and an agent environment applies its own permission model unchanged
  - Packaging lands with the content: the skill directory is confirmed to ship as package data in the wheel, and its file is added to the artifact policy's unconditionally-required member set — until both hold, the skill never reaches an installed tool
  - Observable: a conformance test parses the frontmatter against the field constraints, asserts the name matches both the directory and the constant and the recorded version matches the manifest, extracts every command and option the body names and asserts each exists in the registered command surface, and compares the set of reported channel names the body documents against the union of the drain report's own channel fields and the nested sync report's channel fields (eight in total — the drain report carries the deferred, quarantined, moved, and move-failure channels, while written, skipped, failures, and warnings live on the nested sync report) — removing a command from the application, or adding, renaming, or dropping a channel, makes the test fail, which binding commands alone would not catch
  - _Requirements: 1.9, 8.1, 8.2, 8.3, 8.4, 8.5, 8.8_
  - _Depends: 4.1_

- [ ] 5. Policy and user documentation
- [ ] 5.1 (P) Publish the compatibility policy
  - The three governed contracts named explicitly — the generated-document and ownership contract, the inbox interface, and the plugin API with its documented import surface — together with the rule that documented means public and everything else, including anything undocumented, is internal and may change in any release
  - Per contract, what breaking, additive, and internal mean; the numbering rules that hold before and after the first stable release; how a document-format, ownership-contract, or settings-schema version change maps onto a released version number and what action it costs the user; the deprecation model with its announcement channel and its minimum notice before removal; and the guarantee that a compatible upgrade requires no edit to the settings file, the athlete profile, or a local plugin
  - The statement that changing whether a methodology is bundled is a contract change by definition
  - The user-facing settings schema governed as a named contract alongside the three: one file with the tile, inbox, and plugin tables, all user-written and all documented, with breaking / additive / internal defined for it — the tile table is governed, not left as an ungoverned user-facing schema, and how the file is parsed (the shared loader and its single error) is internal
  - The project's one public-versus-internal statement, naming the plugin API's enumerated import surface as the authority for the public names rather than restating it, and stating that everything else is internal — the document-contract, inbox, plugin-discovery, version-resolution, skill-locator, layout, and settings modules by name, and the bundled calculator class. Three specs edit the public-surface test; this is the statement they are all consistent with
  - The project-wide data-root posture rule stated once: a command that describes the installed tool needs no data root, a command that describes or changes a tree requires one — with the read-only skill command, the plugin listing, and the contract check named as the three current instances, and a note that the CLI module docstring carries the same rule in code
  - Observable: the policy names all three contracts plus the settings schema, gives a breaking/additive/internal definition for each, states both numbering regimes and the deprecation window, carries the public-versus-internal statement and the data-root posture rule, and is the single document the readme, the plugin-platform page, and the contribution documentation all
    link to — the plugin page's own version-policy paragraph is replaced by that pointer, so no second
    compatibility statement survives
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 6.6_
  - _Boundary: CompatibilityPolicy_

- [ ] 5.2 (P) Write the install and configuration documentation and rewrite the readme
  - A first-run path from installation to a generated document: the install command, choosing a data root and pointing at it, getting source files where the tool will find them, the first run, and the resulting document — with a standalone section and a wiki-hosted section stating exactly what differs between them
  - A configuration document receiving the data-root contract with its resolution order and its loud failure when unresolved, the guarantee that the tool never writes into a code repository by default, and the offline and network material currently in the readme: what leaves the machine and when, the persistent opt-out, provider choice, attribution, and the cache
  - An inbox document receiving the inbox interface material the inbox feature publishes in the readme — the default location and how it resolves, every key with its default and meaning, drain semantics, the safeguards, the disposition policy with its never-delete guarantee, and the plain statement that fitdocs performs no watching and no scheduling. The content moves verbatim; this task owns where it lives and that it stays reachable, not what it says. Keeping it as a clearly named section of the configuration document is acceptable only if task 5.7's entry point links that section separately
  - The route to obtaining a training-load methodology when a release bundles none
  - The readme rewritten to what the tool is, how to install it, a minimal first run, and links onward — the stale "no installable package yet" status removed. The onward link targets the documentation entry point, which task 5.7 creates; task 5.7's link test is what proves the reference resolves
  - The rewrite **preserves rather than replaces** the sections the sibling features publish in the readme: the ownership section, the inbox section, and the plugins section are each kept in place or relocated intact into the documentation set with the readme linking to them. A wholesale rewrite that drops one of them is the failure mode this bullet exists to prevent
  - Every documentation reference the readme carries is in project-URL form where the readme is shipped — it is rendered into the distribution metadata, where a repository-relative path resolves to nothing
  - Observable: every behavior statement the readme publishes at the time of the rewrite — this project's and its siblings' — is still published somewhere in the documentation set, the readme still reaches every sibling-published section, and the readme no longer claims the project is unreleasable
  - _Requirements: 1.9, 6.5, 7.1, 7.2, 7.7, 7.8, 10.6, 10.7_
  - _Boundary: InstallDocs, ConfigurationDocs, InboxDocs_

- [ ] 5.3 (P) Write the upgrade and uninstall documentation
  - The exact upgrade and uninstall commands for both supported isolated-application installers, and what each leaves behind
  - What an upgrade does not touch: user-owned document regions, the user-owned settings file, the athlete profile, local plugin files, and the archived sources — and the corresponding guarantee that a compatible upgrade needs no edit to any of them
  - The single command that brings existing documents current when a release moves the document format, with the explicit statement that nothing else is required
  - What remains on disk after uninstalling, stated as a property of where the tool writes rather than as a claim about the installers' behavior
  - Observable: a reader can upgrade and uninstall from the document alone, and every category of user-owned state is individually named as untouched
  - _Requirements: 3.5, 7.3, 7.4, 7.5, 7.6_
  - _Boundary: UpgradeDocs_

- [ ] 5.4 (P) Write the wiki integration documentation
  - Where the packaged skill lands, how to copy or symlink it into an agent's skills directory, how to confirm it is active, and the statement that upgrading the tool means refreshing the copy
  - An end-to-end adoption recipe for an existing agent-managed wiki: install, point the data root at the wiki, configure the inbox, run the first drain, and confirm both the generated documents and the emitted ownership declaration
  - Observable: the recipe runs start to finish against a scratch wiki directory and ends with generated documents and an ownership declaration present
  - _Requirements: 8.6, 8.7_
  - _Boundary: WikiIntegrationDocs_
  - _Depends: 4.2_

- [ ] 5.5 Write the contribution documentation
  - The development environment and the three quality gates that must pass before a change is accepted; the duty to add a changelog entry for any user-visible change and to apply the compatibility policy to the version number when a governed contract moves
  - The public-versus-internal boundary stated by reference to the compatibility policy's single statement — which itself defers to the plugin API's enumerated import surface — rather than restated or re-derived; guidance for an author publishing their own calculator distribution covering the version range to declare, verifying against a released version, and what the policy guarantees them — deferring the authoring mechanics to the documentation that already owns them
  - The rule that material encumbered by a third party's licence or trademark must never be added to the repository or to any published artifact without recorded permission
  - Observable: the document states all three quality gates, the changelog duty, and the encumbered-material rule, and links to rather than duplicates the compatibility policy and the plugin-authoring guide
  - _Requirements: 4.5, 9.1, 9.2, 9.3, 9.4, 9.5_
  - _Boundary: ContributionDocs_
  - _Depends: 5.1_

- [ ] 5.6 Write the release procedure document
  - The ordered procedure a single maintainer can follow end to end, with the command for every step: quality gates, version consistency, profile selection and build, artifact conformance and licensing gates, clean-environment verification of the built artifact, tagging, rehearsal publication, public publication, and post-publication verification
  - Each step names the project script or test command that performs it, so the manual path and the automated path execute identical logic
  - Observable: every gate the release automation runs appears in the document as a runnable command, and following the document by hand reaches the same decision points in the same order
  - _Requirements: 5.1, 5.3, 5.6, 5.9, 5.10_
  - _Depends: 2.3, 2.4_

- [ ] 5.7 Add the documentation entry point and the preserved-guarantee test
  - A single entry point linking install, configuration, **the inbox interface**, upgrading, wiki integration, the ownership contract, the plugin platform, the compatibility policy, the release procedure, and the contribution guide. The inbox is a governed contract and the subject of the agent skill's entire workflow; an entry point that does not reach it is a hole
  - A test asserting every link from the entry point resolves to an existing file (or, where the inbox lives as a section, to that section), and that every preserved statement is still published somewhere in the documentation set: the data-root resolution order, the persistent tile opt-out, the provider attribution, **the inbox never-delete guarantee**, **the statement that fitdocs performs no watching and no scheduling**, and **a pointer to the published ownership contract**. Pinning only this feature's own three statements would let a sibling's guarantee regress at this wave with nothing failing
  - The same test asserts the readme still reaches each sibling-published section, and that documentation references carried by shipped or emitted artifacts use the project-URL form rather than a repository-relative path
  - Observable: the test fails if a documentation file is renamed or removed, if any of the named behavior statements disappears from the documentation set, or if a sibling-published readme section is dropped rather than relocated
  - _Requirements: 1.9, 3.7, 7.9, 10.6, 10.7_
  - _Depends: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [ ] 6. Release automation
- [ ] 6.1 Establish the publication prerequisites
  - Confirm the distribution name is available on both the public index and the rehearsal index, and reserve it on each **by registering a pending publisher only** — no placeholder upload, because a released version number can never be spent twice and nothing may be published before task 3.2 passes
  - The pending publisher on each index names this repository, the release workflow's filename, and its environment; the workflow file itself arrives in task 6.3, and naming it ahead of time is exactly how a pending publisher works
  - Create the two deployment environments the release workflow targets: a rehearsal environment with no approval, and a public-publication environment that requires manual approval
  - This is external configuration, not code, and it must exist before the release workflow can run even once — task 7.3 cannot rehearse without it
  - Observable: both indexes show the claimed name with a pending publisher entry for this repository, and both environments exist with the public one gated on approval
  - _Requirements: 1.1, 5.7_

- [ ] 6.2 Add the continuous integration workflow
  - Runs on every push and pull request against the project's supported version floor: the full test suite, the linter, and the strict type check, followed by a build and an artifact conformance check so a manifest edit that would break a release fails on the change rather than at release time
  - Publishes nothing and requires no credential
  - Observable: a pull request that breaks the artifact policy fails the workflow with the checker's violation listing in its output
  - _Requirements: 5.2_
  - _Depends: 2.1, 2.2, 2.3_

- [ ] 6.3 Add the tag-triggered gate and verification chain
  - Triggered by a version tag: quality gates, version consistency against the tag, profile selection and build, artifact conformance and licensing gates, then clean-environment installation and a smoke run of the **built artifact** rather than the working tree
  - Each job's failure prevents every later job, and every gate invokes the project's own script or test command, so the automated path and the documented manual path execute identical logic
  - This chain publishes nothing and requires no credential, so it is independently runnable and independently verifiable
  - Observable: a tag whose version disagrees with the changelog fails before anything is built, and a tag whose artifact would violate the licensing gate fails before any publication job is reachable
  - _Requirements: 5.2, 5.3, 5.5, 5.8, 5.10_
  - _Depends: 2.1, 2.3, 2.4, 5.6_

- [ ] 6.4 Add the publication and post-publication chain
  - Rehearsal publication to the rehearsal index, then public publication behind the approval-gated environment, then a final job installing the published version from the public index in a fresh environment and asserting the reported version matches the tag
  - Both publish jobs authenticate by short-lived per-release identity-token exchange with that permission scoped to the publishing job alone; no long-lived secret exists in or alongside the project, and the publish jobs stay inline rather than factored out, because the credential exchange does not work from a reusable workflow
  - The public publish job does not tolerate an already-present version — a re-run of a spent version fails rather than silently skipping
  - Every job in this chain depends on the whole gate chain, so publication is unreachable unless every earlier gate passed
  - Observable: a run whose gate chain failed exposes no publication job at all, and a successful run ends with the published version installed from the public index reporting the expected number
  - _Requirements: 2.5, 5.6, 5.7, 5.9_
  - _Depends: 6.1, 6.3_

- [ ] 7. Feature validation
- [ ] 7.1 Validate installed-tool behavior and version identity end to end
  - Extend the existing installed-tool coverage: install the built artifact into an isolated tool directory, assert the console script exists, the reported version equals the manifest's, the help output lists every released command, and the declared metadata fields are all present and non-empty
  - Assert that installing creates no data root, configuration file, or profile anywhere on the machine, and that running the tool from an uninstalled checkout reports the unknown version and exits successfully
  - Observable: the installed console script runs every released command's help successfully, its reported version matches the manifest, and a before-and-after filesystem comparison shows the install created no user-facing state
  - _Requirements: 1.2, 1.7, 2.2, 2.4_
  - _Depends: 1.1, 1.2, 4.1_

- [ ] 7.2 Validate the preserved guarantees
  - The runtime dependency list is unchanged from the pre-feature revision; the golden documents are byte-identical, since nothing in this feature touches rendering; the existing determinism and offline guards still pass, extended to assert no new runtime network access was introduced
  - Reproducibility re-asserted at the feature level: the same revision built twice under the same profile yields archives with identical member names and digests
  - The documented public import surface is unchanged and the two new package modules are absent from it — they are internal by the policy's own rule
  - Observable: the full test suite, the linter, and the strict type check pass clean with all new coverage, the golden diff is empty, and the whole run stays offline
  - _Requirements: 10.1, 10.2, 10.4, 10.5_
  - _Depends: 3.2, 4.2, 6.2_

- [ ] 7.3 Rehearse a full release
  - Follow the release procedure end to end against the rehearsal index using the profile the recorded permission state selects: gates, version consistency, build, conformance and licensing checks, clean-environment verification, rehearsal publication, and installation of the rehearsal artifact from that index into a fresh environment
  - Deliberately trip one gate — a stale changelog entry — and confirm the run stops before any publication and leaves both indexes untouched
  - Observable: the rehearsal artifact installs from the rehearsal index and reports the expected version, and the deliberately failed run publishes nothing
  - _Requirements: 5.1, 5.3, 5.6, 5.8, 5.9, 5.10, 6.2_
  - _Depends: 5.6, 6.1, 6.4, 7.1, 7.2_
