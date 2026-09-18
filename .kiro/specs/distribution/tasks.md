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
> kind may be attempted before task 3.2 passes.** Until the encumbered-content
> gate can refuse an artifact — and refuse to *pass* one it never scanned —
> the project can build things it must not publish. Nothing in this plan may
> change a generated document's bytes; a golden diff at any point is a defect,
> not expected churn.
>
> **Amendment 2 (2026-09-18)**: Requirement 6 was re-based on the
> post-withdrawal, post-purge tree — the encumbered methodology is gone, the
> built-in is the unencumbered `threshold` engine, and the gate is a standing
> property over one artifact set with its match data outside the repository.
> Tasks 1.4, 2.1, 2.2, 2.3 and 3.2 are rewritten in place; 3.1 is withdrawn
> (struck, number kept); major 3 is retitled; 1.2, 5.1, 5.2, 5.6, 6.2, 6.3,
> 7.2 and 7.3 lose their profile / licensing-record / no-methodology clauses.
> Nothing is renumbered.
>
> Deliberate deviation from the usual code-only task rule: Requirements 3, 4, 5,
> 7, 8, and 9 are themselves documentation and release-process deliverables —
> the compatibility policy, the changelog, the release procedure, the user
> documentation, the agent skill, and the contribution guide are the feature.
> They appear as tasks, each paired with the conformance test or gate that keeps
> it honest, following the precedent set by the published ownership contract.
>
> **Sequencing note (Amendment 1, 2026-09-16)**: `build-training-block` landed
> the by-name skill locator and the `skill [NAME]` command before this plan's
> major 4 started — task 4.1 below is ticked "landed by build-training-block"
> rather than executed fresh. Task 4.2 stays open: it still authors this
> spec's own inbox skill and now also carries 4.1's one residual (appending
> the inbox name to the registry and creating its directory in the same
> change). The alternative — major 4 shipping first, then `build-training-block`
> widening a single-skill locator in place — did not occur at this base; that
> path is recorded in `build-training-block`'s own design.md, § DistributionSpecUpdate,
> "If distribution major 4 shipped first" bullet, not in this spec's design.md
> (which has no such section).

- [ ] 1. Foundation: version identity, package manifest, and policy data
- [x] 1.1 Consolidate version resolution behind one leaf
  - A pure module holding the distribution name, a resolver returning the installed version or an absent value, and a display form that falls back to a fixed unknown token; the lookup happens at the point of use, never at import time, because reading distribution metadata is measurably slow for a command-line start-up
  - The three existing unguarded call sites converge on it: the version flag, the tile user-agent, and the plugin listing's built-in version. The listing keeps an absent version absent rather than substituting the token, because the plugin surface forbids fabricating one
  - The module imports nothing from the package and is not added to the documented public import surface — it is internal
  - Observable: unit tests cover the resolved and unresolved paths with the metadata lookup patched, running the command from an uninstalled checkout prints the unknown token and exits successfully instead of raising, and a repository scan finds the released version literal only in the manifest, the changelog's newest entry, and every packaged skill's recorded version (one `SKILL.md` per `PACKAGED_SKILLS` entry) -- and nowhere else *(amended by Amendment 1, 2026-09-16, landed by build-training-block: the "two places" singular count is replaced by the registry-sized set)*
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - _Boundary: VersionSource, CliApp, TileStore, PluginDiscovery_

- [x] 1.2 Complete the package manifest and add the license file
  - Full package metadata: authors, keywords, classifiers, the license file declaration, and project links for source, documentation, changelog, and issues; the version stays static and stays the single declaration
  - The project links must additionally resolve every documentation page that a **shipped or emitted** artifact points at — the ownership contract, the plugin platform, the inbox, and configuration — because no artifact ships `docs/` and the ownership declaration is emitted into a user's tree that has no repository; the rule those references follow is project-URL form, never a repository-relative path
  - An explicit source-distribution allowlist replacing the build backend's default inclusion, so the archive carries the manifest, the readme, the license, the changelog, and the package tree and nothing else — in particular not `tests/`, `.kiro/`, `scripts/`, `release/`, `docs/`, and not the root `agent-log` symbolic link, which today ships as a dangling link member because there is no sdist section at all *(Amendment 2)*; the wheel target's contents stated explicitly rather than implied
  - A license file whose terms match the declared license
  - The runtime dependency list is unchanged — becoming publishable must cost no new dependency
  - Observable: a build produces one wheel and one source distribution; the source distribution contains no tests, specifications, steering documents, reference material, lockfile, spreadsheet, activity file, or symbolic-link member — asserted against a build of a temporary copy of the tree into which the test has itself planted a root `agent-log` symbolic link (invoking `uv build` as `tests/load/test_packaging.py` does, but over a temporary copy of the tree — that file builds the working tree itself and has no copy step to borrow), because the link exists only in the primary checkout, never in a worktree or a CI checkout, and an assertion that depends on the developer's checkout state is vacuous; the declared dependency list is byte-identical to the previous revision's; every documentation page a shipped or emitted artifact references has a declared project URL
  - _Requirements: 1.1, 1.3, 1.4, 1.6, 1.8, 1.9, 1.10, 10.1_
  - _Boundary: PackageManifest_

- [x] 1.3 (P) Establish the changelog
  - A changelog in the established human-written format: a standing unreleased section, releases newest first with version and date, and the six canonical change categories
  - An initial unreleased entry describing the work this phase delivers, written in terms of user-observable behavior rather than commit subjects
  - The convention recorded in the file itself that an entry touching a governed contract names the contract and the action the user or plugin author must take
  - Observable: the file parses under the format's heading conventions, carries an unreleased section, and its category names match the format exactly
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
  - _Boundary: Changelog_

- [x] 1.4 Declare the release policy data *(rewritten by Amendment 2)*
  - One artifact policy declaring, per artifact kind, the members a release must contain, the member patterns it must never contain (tests, specifications, release scripts and policy, documentation, reference material, lockfiles, spreadsheets, activity files, data-root paths, and the root `agent-log` link by name), and the metadata fields a release must declare; the source-distribution member set must mirror the allowlist declared in task 1.2, and the license and changelog files it names are created by tasks 1.2 and 1.3
  - `build-training-block`'s two skill files (`fitdocs/skills/build-training-block/SKILL.md`, `fitdocs/skills/build-training-block/example-block.toml`) are required wheel members *(Amendment 1)*. The packaged `fitdocs-workouts` skill is deliberately **not** listed here — it does not exist yet, and task 4.2 adds its entry when it lands
  - **No licensing record, no permission state, no prune list, no when-bundled member split, and no content-marker list** — the removed material's definition lives outside the repository (task 2.3 reads it through the purge's guard cores), and there is one artifact set per release
  - Pure data with no expressions or environment lookups; not shipped in any artifact
  - Observable: reader unit tests show a missing required key and a wrongly-typed value each raise and an unknown key is tolerated; a scan of the policy file finds no key named for permission, profile, prune, marker, or bundling
  - _Requirements: 1.5, 1.6, 5.4, 10.3_
  - _Boundary: ArtifactPolicy_
  - _Depends: 1.2, 1.3_

- [ ] 2. Release tooling
- [x] 2.1 (P) Build the release artifact builder *(rewritten by Amendment 2: no profiles)*
  - One invocation builds the working tree — always the working tree, never a copy, never a variant — into both a wheel and a source distribution in a cleared output directory, through the existing build front end with no build hooks and no code generation, so the artifact is the tested revision
  - A deterministic timestamp source so the same revision builds to identical archive contents
  - The scripts live under a `scripts/` package (with an `__init__.py`) invoked as `python -m scripts.<name>` from the repository root, so task 2.3 can import the `tests` package; `scripts/` ships in no artifact
  - Observable: the build succeeds and yields exactly one wheel and one sdist; building twice yields archives with identical member names and identical member digests; the builder's command surface offers no profile, variant, or prune option
  - _Requirements: 1.4, 6.10, 10.2, 10.5_
  - _Boundary: ReleaseBuilder_
  - _Depends: 1.4_

- [x] 2.2 Build the artifact conformance checker *(rewritten by Amendment 2: link-member rule added; not parallel with 2.1 — both write into the new `scripts/` package and both add to `tests/test_release_artifacts.py`)*
  - A read-only pass that opens each built artifact, enumerates its members, and reads its distribution metadata, then applies four checks and reports every violation rather than stopping at the first: required members present per artifact kind, no forbidden member present, **no member is a symbolic link** — reported as its own violation kind regardless of the link's target, because a link's bytes are its target path and every content scan is blind to it by construction — and every required metadata field declared and non-empty
  - Each violation names the subject it concerns, what was observed, and the action that resolves it; violations sort deterministically; the pass writes nothing and exits successfully only when clean
  - The finding type follows the project-wide report vocabulary for Phase 3: fields named `(subject, detail[, remedy])` — the artifact filename is the `subject`, not a field called `artifact` — and the classification enum is a `StrEnum`
  - A missing or malformed policy file is a hard error, never a silently skipped check
  - Observable: fixture archives trip each of the four violation kinds exactly once — the link fixture plants a symlink member whose target text is clean and asserts it is still reported — and a clean archive trips none; running the pass twice over the same artifacts produces the same violations in the same order
  - _Requirements: 1.3, 1.5, 1.6, 1.10, 5.4, 10.3_
  - _Boundary: ArtifactChecker_
  - _Depends: 1.4, 2.1_

- [x] 2.3 Add the encumbered-content gate to the checker *(rewritten by Amendment 2: reuses the purge's guard cores, fails closed)*
  - A scan over every text-like member and over the distribution metadata — the metadata matters because the long description is the readme rendered into it, and a member-name-only scan would let a token in prose through — for the removed third-party material as the purge already defines it: the token matcher whose match data is read from the single out-of-repository source (`tests/_forbidden_strings.py`'s `load` and `matches`) and the digest-keyed value oracle (`tests/_content_oracle.py` with the constants in `tests/_content_fingerprints.py`). **No matcher and no marker list of the checker's own**; the two imports are the only non-standard-library imports the scripts make, and neither imports `fitdocs`
  - Any match is a violation — there is no permission branch to consult; binary members are matched by name only so the scan stays fast and cannot produce spurious matches
  - **Fails closed**: the token source being unset is a violation of its own kind that names the variable to set, never a skip and never a pass; a source that is set but unusable (the core's own error) is a hard error. The purge's guards may skip in an ordinary developer run — a release step that did not scan has gated nothing
  - The gate reads the artifacts alone and never consults the source tree, because material reaches a distribution by two different mechanisms and only the archive shows what actually happened
  - This is the gate the migration strategy's stage 3 binds; task 3.2 is the checkpoint that proves it against the real artifacts. After 3.2, an unpublishable artifact — including one that was never scanned — is a failing check rather than a judgement call
  - Observable: with a test-written match file holding a **synthetic** needle (the technique `tests/test_forbidden_strings.py` already uses; never a real token), a fixture artifact carrying the needle in a member fails, one carrying it only in the distribution metadata fails with its artifact and remedy named, and a clean one passes; a fixture carrying a fingerprinted control value fails — the control builds a throwaway digest set from the planted value (the technique `tests/load/test_packaging.py`'s positive control uses) and monkeypatches the checker module's bound fingerprint constants for that test alone, since `check_artifacts` binds them internally by design; with the variable unset the result is the gate-not-run violation and the test asserts a violation, not a skip; with the variable naming a path inside the working tree the checker exits non-zero with the core's error
  - _Requirements: 6.1, 6.2, 6.3, 6.7, 6.9_
  - _Boundary: ArtifactChecker_
  - _Depends: 2.2_

- [x] 2.4 Add the version-consistency gate
  - A check needing no artifact opened: the manifest version, the changelog's newest released entry, and the release tag when one is supplied must all agree
  - Each pairwise disagreement produces one violation naming both values; a changelog with no entry for the version being released is a violation in its own right
  - Observable: agreement passes cleanly, and each of the three possible disagreements produces exactly one violation naming both conflicting values
  - _Requirements: 2.6, 4.7_
  - _Depends: 1.3, 2.2_

- [ ] 3. The release-path checkpoint *(retitled by Amendment 2; formerly "Shipping without a bundled methodology")*
- [x] ~~3.1 Make the bundled methodology optional at the package level~~ — **withdrawn by Amendment 2 (2026-09-18)**; ticked so it is not counted as remaining work
  - This task built a guarded import and a conditionally-assembled `__all__` in `src/fitdocs/load/__init__.py` for former criteria 6.4 and 6.8, and neutralized a branded `--calculator` help example. The methodology package it guarded was deleted on 2026-07-25 and purged on 2026-08-23; the package registers the unencumbered `threshold` built-in unconditionally, its public names are plugin-api's enumerated surface, and the help text is already neutral. Nothing in `fitdocs.load` is modified by this plan. Number kept so that design and review references resolve
  - _Requirements: none (6.4 and 6.8 withdrawn)_

- [x] 3.2 Validate the one artifact set end to end *(rewritten by Amendment 2; formerly "Validate the unencumbered release end to end")*
  - Build the artifact set, run the conformance and encumbered-content gates over it with the match data supplied through the same mechanism the purge's guards use (so this test skips distinguishably in an environment without it, while the checker it exercises would have failed closed), then install the resulting wheel into a clean isolated environment and run a full ingestion over a fixture source
  - Assert the installed tool writes documents with the `threshold` built-in computing load, and exits successfully; assert the source distribution's member set equals the task 1.2 allowlist and nothing else, with no link member — for the real build; the planted-link non-vacuity proof is task 1.2's, and 3.2 does not repeat it
  - Assert the gate's fail-closed posture against the *real* built artifacts, not a fixture: the checker run with the token source unset reports the gate-not-run violation and exits non-zero
  - This is the checkpoint the plan header names: no publication of any kind may be attempted before it passes
  - Observable: the real artifact set passes every gate with the match data supplied; the same artifacts fail on gate-not-run with it unset; the installed wheel completes a sync with load computed by the built-in; the sdist member listing is exactly the allowlist
  - _Requirements: 1.10, 6.2, 6.3, 6.9, 6.10_
  - _Boundary: ReleaseArtifactTest_
  - _Depends: 1.2, 2.1, 2.3_

- [ ] 4. Agent skill packaging
- [x] 4.1 Add the skill locator and the read-only skill command — **landed by build-training-block** *(Amendment 1, 2026-09-16)*
  - A leaf holding the skill's canonical name and resolving the packaged skill directory through package-data resource resolution, so it works from a wheel install, a source checkout, and an isolated tool environment alike; an absent skill resolves to an absent value rather than raising
  - A command that prints the packaged skill directory's absolute path plus a one-line copy recipe and exits successfully; it resolves no data root, loads no profile, builds no tile store, runs no engine, and writes nothing — the tool never installs into a location it does not own
  - An absent skill in an installed distribution is reported through the existing configuration-error path, because it means the install is incomplete rather than that the user erred
  - The command list and exit-code contract in the module docstring are amended; the exit-code contract itself is unchanged. The docstring also records the project-wide data-root posture rule in code — commands that describe the installed tool need no data root, commands that describe or change a tree require one — and this command is an instance of the first half, consistent with the plugin listing and deliberately unlike the contract check
  - Observable: with the skill directory scaffolded (its content is task 4.2's), the command prints an existing directory whose final path component equals the canonical skill name and exits successfully; with the directory absent, it exits with the configuration-error status and an instructive message
  - *(Amendment 1, 2026-09-16)* `build-training-block` landed this task's locator (as `agentskill.PACKAGED_SKILLS`, `skill_root(name)`, `skill_file(name)`, `skill_files(name)`) and command (`fitdocs skill [NAME]`) by name rather than by the single-skill shape above; its one residual for this spec — appending `INBOX_SKILL_NAME` (`"fitdocs-workouts"`) to `PACKAGED_SKILLS` — is folded into task 4.2, which creates the directory in the same change
  - _Requirements: 8.1, 8.6_
  - _Boundary: AgentSkillLocator, CliApp_

- [x] 4.2 Author the agent skill and its conformance test
  - Frontmatter conforming to the open standard's field contract: a name equal to the containing directory and to the locator's constant, a description within the published length limit stating both what the skill does and when to use it, the licence identifier, a compatibility note requiring the command to be installed and reachable, and the released version carried under the metadata map because the standard defines no top-level version field
  - A body covering, in order: when the skill applies, the commands to run and in what order, how to read **every** reported channel — written, skipped, failed, deferred, quarantined, moved, **move failures**, and warnings — and what to do about each: a deferred file needs no action, a quarantined file needs the user rather than the agent, and a move failure means the file was processed successfully and will be retried on the next drain, so it is never a reason to reprocess anything. The channel list is the drain report's own set; the move-failure row is a channel in its own right and an enumeration that omits it teaches an agent to misread a clean run
  - Any documentation the skill points at is referenced by its published project URL, never by a repository-relative path — the skill ships inside the wheel and is copied into an agent's tree, where no repository exists
  - An ownership section that states the boundary and then defers: it names the in-tree ownership declaration as the authority and the published contract as the detail, and enumerates no owned paths, region identifiers, or managed frontmatter keys, so the skill cannot drift when those enumerations change
  - Plain markdown with no client-specific syntax and no pre-approved-tools declaration, so a human or a non-supporting agent environment can follow it directly and an agent environment applies its own permission model unchanged
  - *(Amendment 1, 2026-09-16)* This task also appends `INBOX_SKILL_NAME` (`"fitdocs-workouts"`) to `PACKAGED_SKILLS` and creates its directory in the same change (folded in from task 4.1's residual): the both-ways pin (`skills/` subdirectories equal the registered names) and the registry-parametrized conformance test red on a name registered without its directory and on a directory without its name, so the two cannot be separate tasks in either order
  - Packaging lands with the content: the skill directory is confirmed to ship as package data in the wheel, and its file is added to the artifact policy's unconditionally-required member set — until both hold, the skill never reaches an installed tool *(Amendment 1: this bullet becomes adding the inbox skill's file to the policy's required set; the wheel-member test already covers a registered skill via build-training-block's own)*
  - Observable: a conformance test extends `tests/test_agent_skill.py`'s per-skill map with this skill's heading tuple and its eight-channel binding — the frame is not re-written — asserting the name matches both the directory and `INBOX_SKILL_NAME` and the recorded version matches the manifest, extracting every command and option the body names and asserting each exists in the registered command surface, and comparing the set of reported channel names the body documents against the union of the drain report's own channel fields and the nested sync report's channel fields (eight in total — the drain report carries the deferred, quarantined, moved, and move-failure channels, while written, skipped, failures, and warnings live on the nested sync report) — removing a command from the application, or adding, renaming, or dropping a channel, makes the test fail, which binding commands alone would not catch
  - _Requirements: 1.9, 8.1, 8.2, 8.3, 8.4, 8.5, 8.8, 8.9_

- [ ] 5. Policy and user documentation
- [x] 5.1 (P) Publish the compatibility policy
  - The three governed contracts named explicitly — the generated-document and ownership contract, the inbox interface, and the plugin API with its documented import surface — together with the rule that documented means public and everything else, including anything undocumented, is internal and may change in any release
  - Per contract, what breaking, additive, and internal mean; the numbering rules that hold before and after the first stable release; how a document-format, ownership-contract, or settings-schema version change maps onto a released version number and what action it costs the user; the deprecation model with its announcement channel and its minimum notice before removal; and the guarantee that a compatible upgrade requires no edit to the settings file, the athlete profile, or a local plugin
  - The statement that removing the built-in calculator from a release, or adding one, is a contract change by definition *(Amendment 2: subject re-scoped from "whether a methodology is bundled")*
  - The user-facing settings schema governed as a named contract alongside the three: one file with the tile, inbox, and plugin tables, all user-written and all documented, with breaking / additive / internal defined for it — the tile table is governed, not left as an ungoverned user-facing schema, and how the file is parsed (the shared loader and its single error) is internal
  - The project's one public-versus-internal statement, naming the plugin API's enumerated import surface as the authority for the public names rather than restating it, and stating that everything else is internal — the document-contract, inbox, plugin-discovery, version-resolution, skill-locator, layout, and settings modules by name, and the bundled calculator class. Three specs edit the public-surface test; this is the statement they are all consistent with
  - The project-wide data-root posture rule stated once: a command that describes the installed tool needs no data root, a command that describes or changes a tree requires one — with the read-only skill command, the plugin listing, and the contract check named as the three current instances, and a note that the CLI module docstring carries the same rule in code
  - Observable: the policy names all three contracts plus the settings schema, gives a breaking/additive/internal definition for each, states both numbering regimes and the deprecation window, carries the public-versus-internal statement and the data-root posture rule, and is the single document the readme, the plugin-platform page, and the contribution documentation all
    link to — the plugin page's own version-policy paragraph is replaced by that pointer, so no second
    compatibility statement survives
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 6.6_
  - _Boundary: CompatibilityPolicy_

- [x] 5.2 (P) Write the install and configuration documentation and rewrite the readme
  - A first-run path from installation to a generated document: the install command, choosing a data root and pointing at it, getting source files where the tool will find them, the first run, and the resulting document — with a standalone section and a wiki-hosted section stating exactly what differs between them
  - A configuration document receiving the data-root contract with its resolution order and its loud failure when unresolved, the guarantee that the tool never writes into a code repository by default, and the offline and network material currently in the readme: what leaves the machine and when, the persistent opt-out, provider choice, attribution, and the cache
  - An inbox document receiving the inbox interface material the inbox feature publishes in the readme — the default location and how it resolves, every key with its default and meaning, drain semantics, the safeguards, the disposition policy with its never-delete guarantee, and the plain statement that fitdocs performs no watching and no scheduling. The content moves verbatim; this task owns where it lives and that it stays reachable, not what it says. Keeping it as a clearly named section of the configuration document is acceptable only if task 5.7's entry point links that section separately
  - The readme rewritten to what the tool is, how to install it, a minimal first run, and links onward — the stale "no installable package yet" status removed. The onward link targets the documentation entry point, which task 5.7 creates; task 5.7's link test is what proves the reference resolves
  - The rewrite **preserves rather than replaces** the sections the sibling features publish in the readme: the ownership section, the inbox section, and the plugins section are each kept in place or relocated intact into the documentation set with the readme linking to them. A wholesale rewrite that drops one of them is the failure mode this bullet exists to prevent
  - Every documentation reference the readme carries is in project-URL form where the readme is shipped — it is rendered into the distribution metadata, where a repository-relative path resolves to nothing
  - Observable: every behavior statement the readme publishes at the time of the rewrite — this project's and its siblings' — is still published somewhere in the documentation set, the readme still reaches every sibling-published section, and the readme no longer claims the project is unreleasable
  - _Requirements: 1.9, 7.1, 7.2, 7.7, 7.8, 10.6, 10.7_
  - _Boundary: InstallDocs, ConfigurationDocs, InboxDocs_

- [x] 5.3 (P) Write the upgrade and uninstall documentation
  - The exact upgrade and uninstall commands for both supported isolated-application installers, and what each leaves behind
  - What an upgrade does not touch: user-owned document regions, the user-owned settings file, the athlete profile, local plugin files, and the archived sources — and the corresponding guarantee that a compatible upgrade needs no edit to any of them
  - The single command that brings existing documents current when a release moves the document format, with the explicit statement that nothing else is required
  - What remains on disk after uninstalling, stated as a property of where the tool writes rather than as a claim about the installers' behavior
  - Observable: a reader can upgrade and uninstall from the document alone, and every category of user-owned state is individually named as untouched
  - _Requirements: 3.5, 7.3, 7.4, 7.5, 7.6_
  - _Boundary: UpgradeDocs_

- [x] 5.4 (P) Write the wiki integration documentation
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
  - The ordered procedure a single maintainer can follow end to end, with the command for every step: quality gates, version consistency, build, artifact conformance and encumbered-content gates — including how the maintainer supplies the out-of-repository match data, and that a gate-not-run result is a failed gate, never a step to skip — clean-environment verification of the built artifact, tagging, rehearsal publication, public publication, and post-publication verification *(Amendment 2)*
  - Each step names the project script or test command that performs it, so the manual path and the automated path execute identical logic
  - Observable: every gate the release automation runs appears in the document as a runnable command, and following the document by hand reaches the same decision points in the same order
  - _Requirements: 5.1, 5.3, 5.6, 5.9, 5.10, 6.9_
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
  - A repository secret, `FITDOCS_FORBIDDEN_STRINGS_CONTENT`, holding the contents of the out-of-repository match-data file — the workflows in 6.2 and 6.3 write it to a runner-local file outside the checkout and point the guard's environment variable at that file; the secret's name carries no identifying token, per the purge's rule for configuration keys *(Amendment 2)*
  - Observable (secret): the secret exists under that name in the repository settings, and a workflow step that writes it to a file and runs the purge's own guard tests reports them as run, not skipped
  - Observable: both indexes show the claimed name with a pending publisher entry for this repository, and both environments exist with the public one gated on approval
  - _Requirements: 1.1, 5.7, 6.9_

- [ ] 6.2 Add the continuous integration workflow
  - Runs on every push and pull request against the project's supported version floor: the full test suite, the linter, and the strict type check, followed by a build and an artifact conformance check so a manifest edit that would break a release fails on the change rather than at release time
  - Publishes nothing and requires no publishing credential; the token match data is supplied from the `FITDOCS_FORBIDDEN_STRINGS_CONTENT` secret task 6.1 creates, written to a runner-local file outside the checkout, so the encumbered-content gate runs rather than reporting gate-not-run *(Amendment 2)*
  - Observable: a pull request that breaks the artifact policy fails the workflow with the checker's violation listing in its output; a workflow run with the secret deliberately absent fails on the gate-not-run violation rather than passing
  - _Requirements: 5.2, 6.9_
  - _Depends: 2.1, 2.2, 2.3, 6.1_

- [ ] 6.3 Add the tag-triggered gate and verification chain
  - Triggered by a version tag: quality gates, version consistency against the tag, build, artifact conformance and encumbered-content gates with the match data supplied as in task 6.2, then clean-environment installation and a smoke run of the **built artifact** rather than the working tree *(Amendment 2)*
  - Each job's failure prevents every later job, and every gate invokes the project's own script or test command, so the automated path and the documented manual path execute identical logic
  - This chain publishes nothing and requires no credential, so it is independently runnable and independently verifiable
  - Observable: a tag whose version disagrees with the changelog fails before anything is built, and a tag whose artifact would violate the encumbered-content gate — or whose runner cannot supply the match data — fails before any publication job is reachable
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
  - Reproducibility re-asserted at the feature level: the same revision built twice yields archives with identical member names and digests
  - The documented public import surface is unchanged and the two new package modules are absent from it — they are internal by the policy's own rule
  - Observable: the full test suite, the linter, and the strict type check pass clean with all new coverage, the golden diff is empty, and the whole run stays offline
  - _Requirements: 10.1, 10.2, 10.4, 10.5_
  - _Depends: 3.2, 4.2, 6.2_

- [ ] 7.3 Rehearse a full release
  - Follow the release procedure end to end against the rehearsal index: gates, version consistency, build, conformance and encumbered-content checks with the match data supplied, clean-environment verification, rehearsal publication, and installation of the rehearsal artifact from that index into a fresh environment
  - Deliberately trip one gate — a stale changelog entry — and confirm the run stops before any publication and leaves both indexes untouched
  - Observable: the rehearsal artifact installs from the rehearsal index and reports the expected version, and the deliberately failed run publishes nothing
  - _Requirements: 5.1, 5.3, 5.6, 5.8, 5.9, 5.10, 6.2_
  - _Depends: 5.6, 6.1, 6.4, 7.1, 7.2_

## Implementation Notes
- 1.1: the released-version scan (`tests/test_version_identity.py`) walks `git ls-files -co --exclude-standard` and keeps a count-exact allowlist of two pre-existing non-declaration lines (`docs/plugins.md` example snippet, `tests/load/test_packaging.py` comment). Any task that edits either line, or adds a `CHANGELOG.md` newest entry / a `SKILL.md` `metadata.version`, must keep that test green in the same change — a second whole-token copy of the literal anywhere else is a failure.
- 1.2: hatchling ALWAYS adds `.gitignore` and `PKG-INFO` to the sdist regardless of `only-include`, and auto-ships README/LICENSE -- task 1.4's `[sdist].required` and 3.2's "member set equals the allowlist" must account for both extras. Mutating `pyproject.toml` under `uv run` silently re-resolves `uv.lock`; restore it with `git show HEAD:uv.lock > uv.lock` after any manifest mutation. A dangling symlink named in `only-include` is not shipped; only the default (no sdist table) build ships it -- the whole-table removal is the only meaningful mutation.
- 1.3 (5 review rounds, zero production defects after round 1): for any guard/walker test, state the discrimination sweep criterion UP FRONT -- for every token of every rule, one case per relaxation class {absent, wrong text, case, whitespace, partial match, type (numeric vs string), scope/off-by-one} -- and report it as a table. Enumerating tokens without classes cost rounds 3 and 4 (patch-only ordering, separator, string-vs-int compare each surfaced one round at a time). Also: hand-authored prose bullets must be read against the CODE (regen re-decodes archived .fit bytes; only DECLARED_DIRS get AGENTS.md) -- two false bullets shipped from reading docs alone.
- 1.4: the landed `release/artifact-policy.toml` deviates from the design Data Shape and the policy header records why: `[sdist].required` +`PKG-INFO`; `[forbidden].members` +`.fitdocs/*` (fnmatch `*/.fitdocs/*` cannot match a top-level dir); `[metadata].required_fields` +`Author-email`, and NO `Description` (hatchling writes the long description as the METADATA body unconditionally, never as a header). Consequences for 2.2: check `Requires-Dist` presence and a non-empty body separately from the header loop; use `fnmatchcase` (fnmatch lowercases on Windows only); `scripts/` is importable only from the repo root. Reader: `scripts.artifact_policy.load_policy(path) -> ArtifactPolicy`, `PolicyError`, `DEFAULT_POLICY_PATH`.
- 2.1: `scripts.build_release.build(out_dir=, source_date_epoch=)` -- default epoch 315532800; builds are byte-identical across same-epoch runs and path copies (hatchling normalizes uid/gid/mode/mtime). `uv build` writes a one-byte `.gitignore` into the out dir beside the two artifacts -- 2.2 must not treat it as an artifact. Relative `--out-dir` resolves against the process cwd; invoke from the repo root. Fakes of `subprocess.run` must honor `check` faithfully (raise only when nonzero) or they pin `check=False` as a literal. Nothing in the suite pins "no build hooks" (queued).
- 2.2: `scripts.check_artifacts` -- `ViolationKind` has all seven design members; only MISSING_REQUIRED/FORBIDDEN_MEMBER/LINK_MEMBER/METADATA_INCOMPLETE are wired; `repo_root` is accepted and unused (the 2.3 seam); exit 0 clean / 1 violations / 2 hard error (bad policy, wrong artifact count). Metadata check also requires `Requires-Dist` and a non-empty body. Synthetic fixtures must use a fictitious version (`9.9.9`) or the version-literal scan reds. Every "exactly once" fixture needs a sdist-side twin AND a multi-violation-per-check fixture, or the sdist wiring / `break` mutations survive. hatchling never writes a link entry into a wheel (WheelArchive.add_file stats and reads the target); a zip entry with `external_attr == 0` is indistinguishable from a regular file -- 2.3's content scan is the defence.
- 2.3: the checker now imports `tests._forbidden_strings` (which imports pytest) -- the CI/release workflows (6.2/6.3) must install the dev group before the gate step. `tests/test_release_artifacts.py` has an autouse fixture pointing `FITDOCS_FORBIDDEN_STRINGS` at a synthetic match file; tests that need the unset case `delenv` it. Text-like member set is by exact-case suffix (queued: `.svg/.html/.xml/.tsv`, `.MD`). Every content fixture needs a wheel AND sdist twin (fingerprint, token, binary-name, metadata body) -- the sdist-side call survived until each twin existed.
- 2.4: version check is PAIRWISE (M/C, M/T, C/T each one violation when they disagree; no dedupe; no-entry is additive). `main` modes: default (both gates), `--no-artifacts` (version gate only, before the build), `--no-version-check` (artifact gates only -- what CI must run, because the real CHANGELOG has no released entry until the first release); the two flags together are an argparse error. `--tag ""` == no tag; leading lowercase `v` stripped; `V`/`refs/tags/` are mismatches. Not yet in design.md (queued). Two tests pin the real no-entry state and must change when the first `## [0.1.0]` entry is written.
- 3.2: CHECKPOINT PASSED -- publication is no longer forbidden by the plan header. The gate-pass test reads the SHELL's `FITDOCS_FORBIDDEN_STRINGS` (captured at import, restored per-test over the module autouse fixture) and skips via the core's `require` when unset. `tests/fixtures/builder` fixtures are 10 records -- below `DEFAULT_MIN_DURATION_S = 60`, so the threshold calculator does not compute over them; the E2E builds 90-record fixtures locally. hatchling ships untracked-not-ignored files under `src/` (and symlinks, as link members), so the sdist expectation derives from `git ls-files -co --exclude-standard`. `[tiles] enabled = false` prevents every fetch. `--no-prompt` is needed for a non-interactive `sync`.
- 4.2: `tests/test_docs_guarantees.py:~1040` carries a corpus-wide negative pin `"fitdocs-workouts" not in corpus` whose docstring says 4.2 removes it -- it is WikiIntegrationDocs' boundary, so task 5.4 must delete that clause when README names the inbox skill. `tests/test_agent_skill.py` frame: eight former "shared" tests were really build-training-block content and are now narrowed to `(BLOCK_SKILL_NAME,)`; `_SkillProfile.channels` binds the inbox skill to `fields(DrainReport) | fields(SyncReport)` minus `{inbox, sync}`. Skill prose lessons: warnings are additive (not a partition); moved/move_failures are post-hoc for written/skipped files; `regen` must never share a fence with the routine drain commands; `fitdocs check` prints the regen remedy (`audit.py:165`).
- 5.1: `fitdocs.toml` has SIX user-written tables today (`[tiles] [inbox] [plugins] [load]+sub-tables [plans] [history]`, per `docs/ownership-contract.md:439-441` and the `*_TABLE` constants) -- the design's "three tables today" and this plan's 3.8 wording are stale; 5.2's configuration doc must document all six. Only `doc_version` gates `regen`; `history_version`/`block_version`/`planned_version` are written, never read. Prose-guard tests: an assertion on a word that appears under both polarities ("patch", "settings") pins nothing -- assert the polarity-bearing phrase and scope to the list item/subsection.
- 5.2 (4 rounds): `tests/fixtures/readme_pre_5_2.md` is the pre-rewrite README snapshot the preservation test reads -- a `git show HEAD:` control is self-referential the moment the task commits. `tests/test_docs_guarantees.py`'s corpus-wide never-delete guard is satisfied by a meta-mention in `docs/reference/history-rewrites.md` (queued; 5.7's preserved-guarantee test must scope the corpus to README + docs/ minus reference/). Docs facts: fitdocs never creates the data root (`mkdir -p` first); the pointer file lives in the WORKING tree, not `<data-root>/.fitdocs/`; all four `AGENTS.md` are written on every sync/regen; `[load.priority]` rejects unknown keys (exit 2) while `[load]`/`[load.sufficiency]`/`[load.flags]` ignore them; equal neighbouring defaults defeat any proximity heuristic -- read the value structurally from the key's own row/parenthetical. README Agent-skills paragraph still names one skill; 5.4 adds `fitdocs-workouts` and removes the negative pin.
- 5.3: fitdocs WRITES only the data root's owned paths, the athlete profile, and whatever write location settings configure (inbox `path`/`processed_dir`, possibly outside the data root); it only READS `fitdocs.toml` and the pointer file -- never state "nowhere else, ever". Installer claims: `uv tool dir` prints the PARENT tools directory; `uv tool uninstall fitdocs` removes `<uv tool dir>/fitdocs` + the shim, and uv keeps its own cache; pipx is not installed here -- hedge. A link-anchor test must match the HREF (`](file#slug)`), not the label; a list-of-categories test needs per-item distinctness (exactly one category token per item), not count + presence.
- 5.4 (3 rounds): a test that executes page-parsed shell must resolve the binary from `Path(sys.executable).parent`, not `shutil.which` (which found the GLOBAL `~/.local/bin/fitdocs` shim under `.venv/bin/pytest`), run with `bash -e -c`, `HOME=<tmp>`, dead proxies, and reject `~`/`$HOME` in any block; scope the executor to the recipe section only. Doc fact: `cp -R src dst` over an EXISTING dst copies INTO it -- an update recipe must `rm -rf` the old copy first (the reviewer executed the bare form and found the nested copy). The README Agent-skills paragraph now names both skills; the `"fitdocs-workouts" not in corpus` negative pin is gone.
