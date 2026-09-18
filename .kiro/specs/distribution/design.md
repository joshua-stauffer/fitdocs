# Technical Design: distribution

## Overview

**Purpose**: distribution turns a working local tool into a released product. It adds no product behavior: it adds the package metadata that makes `fitdocs` installable from the public index, one place the released version is declared and consistently reported, a written compatibility policy over the three contracts the Phase 3 siblings just published, a changelog, a gated release procedure that is code rather than memory, user documentation covering install/upgrade/uninstall for standalone and wiki-hosted data roots, and an agent skill that gives an LLM-managed wiki a turnkey inbox workflow.

**Users**: anyone who wants to run fitdocs without cloning it; existing users deciding whether an upgrade is safe; plugin authors who need a version range to depend on; LLM wiki maintainers adopting fitdocs as an input path; and the maintainer, who needs a release procedure whose gates cannot be skipped by inattention.

**Impact**: `pyproject.toml` gains complete metadata and, for the first time, explicit artifact-content control. Three unguarded `importlib.metadata.version("fitdocs")` call sites converge on one leaf that degrades to *unknown* instead of raising. Two project scripts — a build driver and an artifact-conformance checker — become the executable form of the release gates, invoked identically by a maintainer and by the tag-triggered workflow; the checker's encumbered-content gate reuses the purge's two guard cores rather than carrying a marker list of its own, and fails closed when its match data is absent. *(Amendment 2, 2026-09-18: the sentence that stood here — "the built-in calculator registration becomes tolerant of a package built without a bundled methodology" — is retired. The encumbered methodology was withdrawn on 2026-07-25 and purged, with every identifying token, on 2026-08-23; the built-in is the unencumbered `threshold` engine and every release bundles it. Requirement 6 is now the encumbered-content release gate: one artifact set, out-of-repository match data, fail-closed, no symbolic-link members. Every block below that changed says so.)* Nothing in `sync`, `regen`, `load`, `check`, or `plugins` changes behavior, and generated documents are byte-identical.

### Goals

- One command installs a working `fitdocs` from the public index, with artifacts whose contents are declared rather than inherited from build-backend defaults.
- One version declaration, reported identically by the CLI, the tile user-agent, and the built-in calculator listing, and provably equal to the changelog entry and the release tag.
- A compatibility policy that names the three public contracts as the thing version numbers govern, and a changelog that reports against it.
- A release procedure whose every gate is executable, testable, and identical by hand and in automation — including an encumbered-content gate that inspects built artifacts and refuses to publish the removed third-party material, by any path it might return.
- Documentation that carries a reader from install to a generated document, states exactly what upgrade and uninstall touch, and packages the wiki-integration path as an agent skill locked to the release.

### Non-Goals

- Defining what the removed third-party material *is*. `encumbered-content-purge` owns that definition — the out-of-repository match data its token guard reads and the digest set its value oracle carries — and this design consumes both guard cores unchanged. *(Amendment 2: formerly "resolving the methodology's licensing question, negotiating permission, or replacing the methodology"; the replacement happened.)*
- Changing the content or semantics of the three public contracts, or of any command the siblings define.
- Plugin-marketplace packaging of the agent skill for a specific agent client — the standard defines no install location and the plugin-root-to-skills mapping could not be verified; distribution is by documented copy from a path the tool prints.
- Any self-update or auto-update mechanism; a hosted service; an MCP server; an editor plugin; a documentation site generator.
- Publishing third-party calculator distributions, or hosting an index of them.
- Multi-Python-version or multi-platform test matrices beyond the single supported floor the project already declares.

## Boundary Commitments

### This Spec Owns

- **Package identity and artifact contents**: all `[project]` metadata, the license file, the build targets, the sdist allowlist and the wheel contents, and the declared required/forbidden member sets that make "what is in the artifact" a reviewable decision rather than a build-backend default.
- **Version identity**: the single version declaration, the one leaf that resolves it at runtime, its *unknown* degradation, and the equality of the reported version with the changelog entry and the release tag.
- **The compatibility policy**: which contracts version numbering governs, what breaking / additive / internal mean for each, the pre-1.0 and post-1.0 rules, the deprecation window, and the statement that everything undocumented is internal.
- **The changelog**: its format, its obligations, and the release-time gate that its newest entry matches the version being released.
- **The release procedure**: its ordered steps, its quality gates, its artifact verification in a clean environment, its tagging, its rehearsal target, its credential posture, its post-publication check, and the project automation that runs the same gates.
- **The encumbered-content release gate**: the artifact-side inspection that refuses to publish the removed material, its fail-closed posture when the match data is absent, the rule that no artifact carries a symbolic-link member, and the binding of that inspection to both the manual procedure and the tag-triggered workflow. *(Amendment 2: formerly "the recorded permission state, … the unencumbered build profile, and the tolerance of a package with no bundled methodology".)*
- **User-facing documentation structure**: the entry point, install, configuration, inbox, upgrade, uninstall, wiki-integration, compatibility, releasing, and contribution documents, plus the README rewrite — including preserving every behavior statement the project and its siblings publish at the time of the rewrite. The rewrite **relocates or keeps** the sections wiki-contract, inbox, and plugin-api publish in the README; it never drops them (10.7).
- **The project-wide statements that need one home**: what is public versus internal (by reference to plugin-api's enumeration, which is the authority), the governance of the user-facing settings schema including `[tiles]`, and the rule deciding which commands require a resolved data root. All three live in `docs/compatibility.md` (3.8, 3.9, 3.10).
- **The agent skill**: its packaged location, its frontmatter contract, its body's scope, its version locking, the read-only command that reports its installed path, and the conformance test binding it to the CLI's real command surface.

### Out of Boundary

- The **document/ownership contract**, the emitted in-tree declaration, the document-format version and its migration-by-regeneration story, and the `check` command — wiki-contract owns them. This design cites them and changes none.
- The **inbox interface**: the `[inbox]` settings table, the drain, the stability and quarantine safeguards, the disposition policy — inbox owns them. This design documents them (relocating inbox's README section into `docs/inbox.md`, wording intact) and drives the agent skill from them.
- The **settings file's plumbing**: the settings-file constant, the data-root-relative path resolver, the shared parse-once loader, and its single file-level error — the pre-wave settings foundation owns them, and each `[table]` reader stays with its owning feature. This design governs the resulting *schema* in the compatibility policy (3.8) and classifies the loader and the layout module as internal (3.9); it changes neither.
- **Plugin discovery mechanics**: the entry-point group, the local-plugin channel, the `[plugins]` table, the `plugins` command, the `py.typed` marker, the documented public import surface, and the plugin-author guide — plugin-api owns them. This design verifies the marker reaches the artifact and carries plugin-api's compatibility statement into one project-wide policy; it does not restate the authoring instructions.
- The **calculator-authoring guide** (`docs/contributing-calculators.md`) — training-load owns it.
- The **two guard cores** the gate reuses — `tests/_forbidden_strings.py` (token match data from outside the repository, Req 11.7–11.10 of the purge) and `tests/_content_oracle.py` with `tests/_content_fingerprints.py` (digest-keyed value scan) — and the definition of the removed material they encode. `encumbered-content-purge` owns them; this design imports them and changes neither. *(Amendment 2: formerly "the methodology itself … this design may prune it from a build".)*
- The **built-in calculator** (`threshold`) and the load package's public names: plugin-api's enumerated surface is the authority and is unconditional. This design registers, guards, or conditionally exports nothing in `fitdocs.load`. *(Amendment 2.)*
- Any **new product capability**: no new pipeline stage, renderer, metric, or engine behavior. The one command this design adds prints a path and writes nothing.
- The **route-maps tile behavior** and its network carve-out — documented, not changed.

### Allowed Dependencies

- `version.py` is a pure leaf: `importlib.metadata` and typing only. It imports nothing from `fitdocs`.
- `agentskill.py` depends on `importlib.resources` only.
- `cli → {version, agentskill}` plus its existing dependencies; `tiles → version`; `plugins → version`. Nothing imports `cli`.
- The release scripts live outside the package and import nothing from `fitdocs`. They use the standard library (`zipfile`, `tarfile`, `tomllib`, `subprocess`, `shutil`, `pathlib`, `email`) plus exactly two repository-local imports — the purge's guard cores `tests._forbidden_strings` (its pure `load`/`matches`/`ForbiddenStringsSourceError`; the module also imports `pytest` for its skip helper, which the dev environment always provides) and `tests._content_oracle` / `tests._content_fingerprints` — so the gate has one matcher, not two. They are invoked as modules from the repository root (`python -m scripts.check_artifacts`), never imported by the package, and never ship. *(Amendment 2: the "use only the standard library" clause is relaxed by exactly those two imports, which is what Requirement 6.3 demands; the guarded-import rule for `load/__init__.py` is retired with the package it guarded.)*
- The workflows depend on `uv`, the project's own scripts, and the standard publishing action. No project code runs at build time beyond the build backend.
- Direction, violations are errors: `{version, agentskill} → {cli, tiles, plugins}`; `scripts → artifacts` and `scripts → tests.{_forbidden_strings, _content_oracle, _content_fingerprints}` (never `scripts → src`); `workflows → scripts`.
- **No new runtime dependency at any layer** (10.1). No new development dependency beyond what `uv` and the build backend already provide.

### Revalidation Triggers

- Changing the artifact required/forbidden sets, the sdist allowlist, or the wheel contents → the conformance checker, its policy file, and the packaging tests all change together; plugin authors relying on shipped type information must be re-checked.
- Changing the version declaration's location or the runtime resolution rule → the CLI, the tile user-agent, and the plugin listing's built-in version all change; the equality tests must be re-derived.
- Changing the compatibility policy's contract list, its breaking-change definition, or its deprecation window → the changelog's obligations, the contribution documentation, and plugin-api's published plugin-surface statement must be reconciled.
- Changing either guard core's public functions, the match-data file format, or the environment variable that names the match data (all `encumbered-content-purge`'s) → the checker's encumbered-content check and its fixture tests must be re-derived; a change that makes the token core's `load` return `None` in any new circumstance turns a fail-closed gate into a silent one and must be caught by the `GATE_NOT_RUN` test. *(Amendment 2.)*
- Removing the built-in calculator from a release, or adding a second one → a public-contract change the changelog records (6.6); the artifact policy's required members are re-checked. *(Amendment 2.)*
- Changing the CLI's registered command surface (any sibling adding or removing a command), or the drain report's channel set (any sibling adding, renaming, or removing a reported channel) → the agent skill's body and its conformance test must be re-checked.
- Adding a settings table, or a key to one → the compatibility policy's settings-schema section and the documentation that publishes the key must be updated in the same change (3.8).
- Changing plugin-api's enumerated public import surface → the compatibility policy's public-versus-internal statement points at it and must be re-read; `tests/test_public_api.py` stays plugin-api's to change.
- Changing the release workflow's trigger, environments, or publishing action → the credential posture and the rehearsal path must be re-validated against the index's current requirements.

## Architecture

### Existing Architecture Analysis

- **`pyproject.toml` is minimal but sound**: hatchling, src-layout, `version = "0.1.0"` static, five runtime dependencies, one console script, `packages = ["src/fitdocs"]`. It declares no `authors`, `keywords`, `classifiers`, `[project.urls]`, `license-files`, or sdist target — so the sdist today would inherit hatchling's defaults and carry `tests/`, `.kiro/`, `uv.lock`, and `docs/reference/`.
- **Version reporting already half-exists.** `cli.py` registers an eager `--version` callback on `@app.callback()`; `importlib.metadata.version("fitdocs")` is called at `cli.py:57,94` and at `tiles.py:54,242` for the tile user-agent. None of the three call sites guards `PackageNotFoundError`, so `--version` raises from an uninstalled source tree. plugin-api adds a fourth consumer (the built-in calculator's reported version).
- **Packaging tests already exist and are the right shape.** `tests/test_packaging.py` performs an offline `uv tool install` into a temporary `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`, runs the installed console script, and compares `--version` against the `pyproject.toml` value. `tests/load/test_packaging.py` builds a wheel and an sdist and scans every regular member of each with the purge's two guard cores — the digest-keyed value oracle and the out-of-repository token matcher — asserting the removed material is absent and that the fresh-interpreter registry holds exactly the `threshold` built-in. This design extends that established pattern rather than inventing one. *(Amendment 2: rewritten — at the original base this bullet described a wheel guard asserting two methodology CSVs were present.)*
- **The encumbered material is gone, and the guards that keep it gone already scan artifacts — but only when someone runs them.** *(Amendment 2: this bullet formerly read "The encumbered material is committed and packaged by design", describing the 2026-07-21 tree. Since 2026-08-23 no tracked file, path, or commit carries an identifying token; the guards read their match data from outside the repository and skip, distinguishably, when it is absent.)* There is no continuous integration and no `[tool.hatch.build.targets.sdist]` section at all, so hatchling's default sdist ships `.kiro/`, `tests/`, and the root `agent-log` symlink — a dangling link to the shared agent log, which is untracked, un-ignored, invisible to the content scan by construction (`member.isfile()` is false for a link), and whose target carries exactly the identity the purge erases. `uv build && uv publish` on any checkout would ship all of that with no mechanism objecting.
- **The CLI is a thin typer shell** with three commands today and two more arriving from siblings (`check`, `plugins`), a fixed 0/1/2 exit-code contract, and an established `_config_error` path for anything the user can fix. A read-only command that prints a path fits that shell without disturbing it.
- **`src/fitdocs/__init__.py`** re-exports 19 names lazily under PEP 562 and is guarded by `tests/test_public_api.py`; `tests/test_determinism.py` already asserts no writes and no network with patched `open`/`socket`. Both are the natural homes for this feature's preserved-guarantee assertions.
- **Nothing exists for release**: no `.github/`, no `LICENSE` file despite the declared MIT terms, no `CHANGELOG.md`, no `CONTRIBUTING.md`, no git tags, no CI.

### Architecture Pattern & Boundary Map

Selected pattern: **declared artifact, executable gates**. Package contents are declared (an allowlist in the manifest plus a policy file the checker reads) instead of inherited; every release gate is a script the test suite exercises, so the maintainer path and the automation path run the same code. The package itself gains only two pure leaves and one read-only command.

```mermaid
graph TB
    subgraph Automation
        CiWorkflow[CiWorkflow ci yml]
        ReleaseWorkflow[ReleaseWorkflow release yml]
    end
    subgraph ReleaseTooling
        ReleaseBuilder[ReleaseBuilder build_release py]
        ArtifactChecker[ArtifactChecker check_artifacts py]
    end
    subgraph PolicyData
        ArtifactPolicy[ArtifactPolicy artifact-policy toml]
        MatchData[MatchData out of repository]
        GuardCores[GuardCores tests forbidden strings and content oracle]
        Changelog[Changelog CHANGELOG md]
        PackageManifest[PackageManifest pyproject toml]
    end
    subgraph Package
        VersionSource[VersionSource version py]
        AgentSkillLocator[AgentSkillLocator agentskill py]
        AgentSkillPackage[AgentSkillPackage SKILL md]
        CliApp[CliApp cli py]
        TileStore[TileStore tiles py]
        PluginDiscovery[PluginDiscovery plugins py]
    end
    subgraph Documentation
        DocsEntry[DocsEntry index md]
        CompatibilityPolicy[CompatibilityPolicy compatibility md]
        InstallDocs[InstallDocs install upgrading configuration]
        WikiIntegrationDocs[WikiIntegrationDocs wiki-integration md]
        ReleaseProcedure[ReleaseProcedure releasing md]
        ContributionDocs[ContributionDocs CONTRIBUTING md]
    end

    CiWorkflow --> ArtifactChecker
    ReleaseWorkflow --> ReleaseBuilder
    ReleaseWorkflow --> ArtifactChecker
    ReleaseBuilder --> PackageManifest
    ArtifactChecker --> ArtifactPolicy
    ArtifactChecker --> GuardCores
    GuardCores --> MatchData
    ArtifactChecker --> Changelog
    ArtifactChecker --> PackageManifest
    CliApp --> VersionSource
    CliApp --> AgentSkillLocator
    TileStore --> VersionSource
    PluginDiscovery --> VersionSource
    AgentSkillLocator --> AgentSkillPackage
    DocsEntry --> CompatibilityPolicy
    DocsEntry --> InstallDocs
    DocsEntry --> WikiIntegrationDocs
    DocsEntry --> ReleaseProcedure
    DocsEntry --> ContributionDocs
    ReleaseProcedure --> ReleaseBuilder
    ReleaseProcedure --> ArtifactChecker
```

**Architecture Integration**:

- **Domain boundaries**: policy is *data* (`artifact-policy.toml`, the manifest, the changelog, and — for the removed material — the match data outside the repository and the digest set the purge owns); enforcement is *scripts* that read that data and inspect artifacts; the package gains only version resolution, skill location, and a print-a-path command. No component co-owns a decision: the checker never defines what the removed material is, it asks the purge's guard cores; the builder never decides what is forbidden, it builds the working tree and the checker judges the result. *(Amendment 2: `licensing.toml` and the prune list are gone with the permission question.)*
- **Existing patterns preserved**: absent data is `None` and never fabricated (an unresolvable version is *unknown*); frozen dataclasses with tuple fields; loud configuration failure before any effect; read-only diagnostic commands that write nothing; the offline-by-default posture with the tile carve-out untouched; the `uv tool install` into an isolated tool directory that `tests/test_packaging.py` already established.
- **New components rationale**: `version.py` exists because four modules need one answer and the current three copies each raise on an uninstalled tree. `agentskill.py` exists so the packaged skill has one resolution path shared by the command and its tests. The two scripts exist because the encumbered-content gate must reason over *built artifacts*, which neither a manifest nor a workflow step can do in a testable way — and because the two guards that already scan a built wheel and sdist (`tests/load/test_packaging.py`) are pytest tests that nothing forces onto the publish path: a checker the workflow *must* run, that cannot skip, is the difference between a guard and a test.
- **Steering compliance**: no new runtime dependency; `mypy --strict` over the two new package modules; nothing written outside the data root by any new code path (the skill command prints, it does not install); personal data cannot reach an artifact because the sdist is an allowlist and the checker fails on any undeclared member.

### Technology Stack

| Layer | Choice / Version | Role in Feature | Notes |
|-------|------------------|-----------------|-------|
| Build backend | `hatchling` (existing) | Builds wheel and sdist from declared targets | Explicit sdist allowlist replaces default inclusion; no build hooks, no code generation |
| Packaging front end | `uv` (existing dev tool) | `uv build`, `uv tool install` for clean-environment verification | Already the project's tool and already used by the packaging tests |
| Version resolution | stdlib `importlib.metadata` | Runtime version of the installed distribution | Guarded for `PackageNotFoundError`; called lazily, never at import time |
| Skill location | stdlib `importlib.resources` | Resolves the packaged skill directory in an installed tool | Package-data resource resolution *(Amendment 2: "the mechanism the methodology tables already use" — those tables are gone)* |
| Release scripts | stdlib `zipfile`, `tarfile`, `tomllib`, `email`, `subprocess`, `shutil` + the purge's two guard cores under `tests/` | Deterministic build; artifact member, link, content and metadata inspection | No new dependency; scripts import nothing from `fitdocs`; invoked as `python -m scripts.<name>` from the repository root *(Amendment 2)* |
| Automation | GitHub Actions | CI on push/PR; tag-triggered release | Publish job inline (Trusted Publishing is unavailable from reusable workflows) |
| Publication | `pypa/gh-action-pypi-publish` (pinned tag) | Uploads to TestPyPI then PyPI via OIDC | `permissions: id-token: write` scoped to the publish job; PEP 740 attestations are default-on since v1.11.0; no API token anywhere |
| Skill format | Agent Skills open standard | `SKILL.md` frontmatter + body | `name` must equal the directory name; `description` 1–1024 chars; version carried under `metadata` (the standard has no top-level `version` field) |
| Changelog format | Keep a Changelog 1.1.2 | Human-written release history | Six canonical sections; `## [X.Y.Z] - YYYY-MM-DD`; standing `## [Unreleased]` |

## File Structure Plan

### New Files

```
LICENSE                            # MIT text matching the declared metadata (1.8)
CHANGELOG.md                       # Keep a Changelog 1.1.2; Unreleased + releases (4.1-4.6)
CONTRIBUTING.md                    # Contributor path, changelog duty, public/internal,
                                   #   calculator-publisher guidance, encumbered-material rule (9.1-9.5)

release/
└── artifact-policy.toml           # Required members per artifact kind, forbidden member
                                   #   patterns, required metadata fields — the checker's
                                   #   declarative input (1.5, 1.6, 5.4). Amendment 2: no
                                   #   licensing.toml, no marker list, no when-bundled split

scripts/
├── __init__.py                    # Makes `python -m scripts.<name>` resolvable from the
│                                  #   repository root; never ships (Amendment 2)
├── build_release.py               # Builds wheel + sdist from the working tree into a
│                                  #   cleared directory; deterministic timestamps
│                                  #   (1.4, 6.10, 10.2, 10.5). Amendment 2: no profiles
└── check_artifacts.py             # Artifact conformance + encumbered-content gate (via the
                                   #   purge's guard cores; fails closed) + link-member rule +
                                   #   version/changelog consistency; exit 0 clean / 1
                                   #   violations (1.3, 1.5-1.8, 1.10, 2.6, 4.7, 5.4, 6.1,
                                   #   6.2, 6.3, 6.7, 6.9, 10.3)

.github/workflows/
├── ci.yml                         # Push/PR: tests, lint, strict types, artifact build +
│                                  #   conformance check (5.2)
└── release.yml                    # Tag-triggered: gates, build, check, clean-environment
                                   #   install, TestPyPI rehearsal, approval-gated PyPI
                                   #   publish, post-publish verification (5.5-5.10)

src/fitdocs/
├── version.py                     # Pure leaf: tool_version() -> str | None,
│                                  #   version_display() -> str, DIST_NAME (2.1-2.4)
├── agentskill.py                  # PACKAGED_SKILLS registry, skill_root(name),
│                                  #   skill_file(name), skill_files(name) (8.1, 8.6, 8.9)
│                                  #   -- landed by build-training-block (Amendment 1)
└── skills/
    └── fitdocs-workouts/
        └── SKILL.md               # The published agent skill: inbox workflow, outcome
                                   #   interpretation, ownership boundary (8.1-8.5, 8.8)

docs/
├── index.md                       # The single documentation entry point (7.9)
├── install.md                     # Install, data root, first run, standalone vs wiki (7.1, 7.2)
├── configuration.md               # Settings file, data-root contract, offline/network
│                                  #   behavior, tile opt-out, attribution (7.7, 7.8, 10.6)
├── inbox.md                       # The inbox interface as a user-facing document:
│                                  #   relocated from inbox's README section — keys and
│                                  #   defaults, drain semantics, safeguards, the
│                                  #   never-delete guarantee, and the no-watching /
│                                  #   no-scheduling statement (7.9, 10.6, 10.7)
├── upgrading.md                   # Upgrade and uninstall commands, what is untouched,
│                                  #   the regeneration step, what persists (7.3-7.6)
├── wiki-integration.md            # Agent-skill install/verify/update + the end-to-end
│                                  #   adoption recipe for an agent-managed wiki (8.6, 8.7)
├── compatibility.md               # The compatibility policy over the governed contracts,
│                                  #   the settings schema including [tiles], the one
│                                  #   public-versus-internal statement, and the data-root
│                                  #   posture rule (3.1-3.10)
└── releasing.md                   # The ordered release procedure and its gates (5.1, 5.3, 5.6, 5.9, 6.9)

tests/
├── test_version_identity.py       # One declaration; unknown fallback; equality across
│                                  #   manifest, changelog, tag, installed tool (2.1-2.6)
├── test_release_artifacts.py      # The one artifact set built and checked; required and
│                                  #   forbidden members; a planted link member is a
│                                  #   violation; a planted synthetic token (test-supplied
│                                  #   match file) and a planted fingerprinted value are
│                                  #   each caught; unset match data is GATE_NOT_RUN, never
│                                  #   a pass; metadata completeness; reproducibility
│                                  #   (1.3-1.6, 1.10, 5.4, 6.1, 6.2, 6.3, 6.7, 6.9, 6.10,
│                                  #   10.3, 10.5). Amendment 2: test_unencumbered_install.py
│                                  #   is not created -- there is no such profile
├── test_agent_skill.py            # Frontmatter conformance; name equals directory;
│                                  #   version matches release; every named command and
│                                  #   option exists in the CLI surface (8.1, 8.5, 8.8)
└── test_docs_guarantees.py        # New, or extended if inbox already created it.
                                   #   Entry point links resolve (install, configuration,
                                   #   inbox, upgrading, wiki integration, ownership
                                   #   contract, plugin platform, compatibility,
                                   #   releasing, contributing); preserved behavior
                                   #   statements still published, including the sibling
                                   #   features' (7.9, 10.6, 10.7)
```

**Amendment 1 (2026-09-16, landed by build-training-block)**: `skills/`
gains a sibling directory, `build-training-block/`, holding that spec's own
`SKILL.md` and `example-block.toml`; `tests/test_agent_skill.py` above is not
a new file for that spec — it exists, generalized over `PACKAGED_SKILLS`,
and that spec's task 4.2 extends its per-skill map.

### Modified Files

- `pyproject.toml` — complete `[project]` metadata (`authors`, `keywords`, `classifiers`, `license-files`, `[project.urls]` for source, documentation, changelog, issues); explicit `[tool.hatch.build.targets.sdist]` allowlist *(Amendment 2: there is no sdist section at all today — the purge deleted the exclude-only one — so the default ships `.kiro/`, `tests/`, `scripts/` and the root `agent-log` symlink; the allowlist excludes all four by construction, and 1.10 asserts the link stays out)*; wheel target unchanged in intent but stated explicitly. Version stays static and stays the single declaration. `[project.urls]` must additionally resolve every documentation page a *shipped or emitted* artifact points at — the ownership contract, the plugin platform, the inbox, and the configuration document — because the sdist excludes `docs/` and wiki-contract's emitted `AGENTS.md` lands in a tree that has no repository (1.9).
- `src/fitdocs/cli.py` — `--version` and any other version output read `version.version_display()`; the read-only `skill [NAME]` command (landed by build-training-block, Amendment 1); docstring amended. *(Amendment 2: the "`--calculator` help example replaced with a methodology-neutral one" clause is retired — the help text is already neutral, "Use only the calculator with this id.")*
- `src/fitdocs/tiles.py` — the tile user-agent composes from `version.version_display()` instead of calling `importlib.metadata` directly, so an uninstalled tree still produces a valid identification string.
- `src/fitdocs/plugins.py` — the built-in calculator's reported version comes from `version.tool_version()`; an unknown version stays `None` rather than becoming a fabricated string (plugin-api Req 4.3 already forbids fabrication).
- ~~`src/fitdocs/load/__init__.py`~~ — **not modified** *(Amendment 2: the guarded import and conditional export of 6.8 are withdrawn; the package registers the unencumbered `threshold` built-in unconditionally and this design does not touch it)*.
- `README.md` — rewritten: what fitdocs is, install, a minimal first run, and links into `docs/index.md`. The rewrite is a **reorganization, not a replacement** (10.7): the route-maps privacy, opt-out, and attribution statements move to `docs/configuration.md` intact; wiki-contract's ownership section, inbox's inbox section, and plugin-api's plugins section are each either kept in place or relocated verbatim into `docs/ownership-contract.md`, `docs/inbox.md`, and `docs/plugins.md` with the README linking to them. Dropping any of those statements is a defect the preserved-guarantee test catches (10.6).
- `tests/test_packaging.py` — extended with the metadata completeness assertions and the no-side-effect assertion (installing creates no data root).
- `tests/test_cli.py` — the `skill` command's output and exit code; `--version` reporting *unknown* rather than raising when the distribution is not installed.
- `tests/test_determinism.py` — the existing offline guard extended to assert this feature introduced no new runtime network access (10.4).
- `tests/test_public_api.py` — **not** extended with new names. plugin-api's enumeration is the authoritative public surface; this feature only asserts that its new package module (`version.py`) is absent from the documented surface (it is internal by the policy's own rule). *(Amendment 2: the unencumbered-install assertions of 6.8 are withdrawn with the criterion.)*
- `docs/plugins.md` — plugin-api writes this page and owns its content; this feature replaces its
  self-contained version-policy paragraph with a pointer to `docs/compatibility.md`, so the project
  has exactly one compatibility statement rather than two that can drift (3.7). No other content changes.
- `.gitignore` — ignore `dist/` build output (already covered) and the release scripts' temporary build trees.

## System Flows

### Release pipeline

```mermaid
flowchart TB
    Tag[Release tag pushed] --> Gates[Run tests lint and strict type check]
    Gates -->|fail| Stop[Stop nothing published]
    Gates --> Version[Compare tag manifest and changelog versions]
    Version -->|mismatch| Stop
    Version --> Build[Build wheel and sdist from the working tree]
    Build --> Check[Run artifact conformance and encumbered content gate]
    Check -->|match data absent| Stop
    Check -->|violations| Stop
    Check --> Clean[Install artifact into a clean environment and run it]
    Clean -->|fail| Stop
    Clean --> Rehearse[Publish to the rehearsal index]
    Rehearse -->|fail| Stop
    Rehearse --> Approve[Await manual approval on the publish environment]
    Approve --> Publish[Publish to the public index with short lived credentials]
    Publish --> Verify[Install from the public index and confirm the version]
```

Flow decisions worth stating: (a) every gate that can fail runs **before** the rehearsal publish, so a failure never spends a version number (5.8); (b) the version equality check happens before the build, because a mismatched tag is the cheapest failure to detect (2.6, 4.7); (c) the clean-environment install exercises the *artifact*, never the working tree, so a file missing from the wheel fails here rather than for the first user (5.3); (d) the public publish is guarded by an environment approval, which is also what makes a hand-run publish cross a recorded gate (5.7); (e) the post-publication install is the only step that runs after the version is spent, and its failure is a defect report, not a rollback — a released version is never altered (2.5).

### Encumbered-content gate decision *(Amendment 2: formerly "Licensing gate decision")*

```mermaid
flowchart TD
    Start[Artifacts built] --> Load[Load the token match data from outside the repository]
    Load -- unset --> NotRun[GATE_NOT_RUN violation stop the release]
    Load -- set but unusable --> Error[Hard error stop the release]
    Load -- loaded --> Scan[Enumerate every member and read the distribution metadata]
    Scan --> Link{Any member is a symbolic link}
    Link -- yes --> Fail[Report each offending member and stop the release]
    Link -- no --> Tokens{Token match in any text member or the metadata}
    Tokens -- yes --> Fail
    Tokens -- no --> Values{Fingerprinted value in any text member}
    Values -- yes --> Fail
    Values -- no --> Clean[Gate passes for the encumbered content concern]
```

The gate is deliberately artifact-side (6.7): material reaches a distribution by two different mechanisms — package data inside the wheel and the build backend's inclusion rules for the sdist — and only the built archive shows what actually happened. The check covers archive members *and* the distribution metadata, because the long description is the README rendered into `METADATA` and would otherwise carry a token past a member-name-only scan. There is no permission branch: the material was withdrawn and purged, so any match is a violation (6.1, 6.2). The gate's definition of the material is not its own — the token match data lives outside the repository and is read through the purge's `tests/_forbidden_strings.py` core, and the value scan uses the purge's digest set through `tests/_content_oracle.py` (6.3) — so the repository retains no forbidden term in any readable form and the release gate and the repository guard cannot disagree. An unset match-data source is a `GATE_NOT_RUN` violation, not a skip and not a pass (6.9): the purge's guards may skip in an ordinary developer run, but a release step that did not scan has not gated anything. A symbolic-link member is a violation in its own right (1.10), because a link's bytes are its target path, not its target's content, and every content scan is blind to it by construction.

### Version resolution

```mermaid
stateDiagram-v2
    [*] --> Lookup
    Lookup --> Resolved: distribution metadata found
    Lookup --> Unknown: distribution not installed
    Resolved --> [*]: report the installed version
    Unknown --> [*]: report unknown and continue
```

The lookup is performed lazily at the point of use, never at import time, because reading distribution metadata is measurably slow for a CLI's startup. *Unknown* is a first-class outcome, not an error: a developer running from a source checkout gets a working tool that declines to invent a version (2.4).

## Requirements Traceability

| Requirement | Summary | Components | Interfaces | Flows |
|-------------|---------|------------|------------|-------|
| 1.1 | Published under a stable name, standard installers | PackageManifest, ReleaseWorkflow | `[project] name`, publish job | Release pipeline |
| 1.2 | Console entry point; documented commands run | PackageManifest, InstalledToolVerification | `[project.scripts]`, clean-environment install | Release pipeline |
| 1.3 | Complete declared metadata | PackageManifest, ArtifactChecker | `[project]`, `required_metadata` | — |
| 1.4 | Both sdist and wheel each release | ReleaseBuilder | `build()` | Release pipeline |
| 1.5 | Artifacts contain every runtime file (packaged skills, `py.typed`) | ArtifactPolicy, ArtifactChecker | `required_members` | Encumbered-content gate |
| 1.6 | Artifacts contain no development-only material | PackageManifest, ArtifactPolicy, ArtifactChecker | sdist allowlist, `forbidden_members` | Encumbered-content gate |
| 1.7 | Install creates nothing on the user's machine | InstalledToolVerification | packaging test assertion | — |
| 1.8 | License file matches declared license | LicenseFile, PackageManifest, ArtifactChecker | `license-files`, `required_members` | — |
| 1.9 | Shipped and emitted doc references use project URLs | PackageManifest, DocsGuaranteeTest | `[project.urls]`, URL-form assertion | — |
| 2.1 | One version declaration | PackageManifest, VersionSource | `[project] version`, `DIST_NAME` | Version resolution |
| 2.2 | Installed tool reports the installed version | VersionSource, CliApp | `tool_version`, `--version` | Version resolution |
| 2.3 | Same version everywhere it appears | VersionSource, CliApp, TileStore, PluginDiscovery | `version_display`, `tool_version` | Version resolution |
| 2.4 | Unknown rather than fabricated; keeps working | VersionSource | `tool_version` returns `None` | Version resolution |
| 2.5 | Publish a version exactly once | ReleaseProcedure, ReleaseWorkflow | no skip-existing on the public index | Release pipeline |
| 2.6 | Version matches changelog and tag | ArtifactChecker, ReleaseWorkflow | `check_version_consistency` | Release pipeline |
| 3.1 | Policy names the three public contracts | CompatibilityPolicy | `docs/compatibility.md` | — |
| 3.2 | Breaking / additive / internal per contract | CompatibilityPolicy | `docs/compatibility.md` | — |
| 3.3 | Pre-1.0 and post-1.0 numbering rules | CompatibilityPolicy | `docs/compatibility.md` | — |
| 3.4 | Format, contract, and settings versions map to releases | CompatibilityPolicy | `docs/compatibility.md` | — |
| 3.5 | Compatible upgrade needs no user edit | CompatibilityPolicy, UpgradeDocs | `docs/compatibility.md`, `docs/upgrading.md` | — |
| 3.6 | Deprecation announcement and notice window | CompatibilityPolicy | `docs/compatibility.md` | — |
| 3.7 | One policy, referenced from readme and elsewhere | CompatibilityPolicy, DocsEntry, ContributionDocs | link structure | — |
| 3.8 | Settings schema, including `[tiles]`, is governed | CompatibilityPolicy | `docs/compatibility.md` | — |
| 3.9 | One public-versus-internal statement | CompatibilityPolicy, ContributionDocs | `docs/compatibility.md` | — |
| 3.10 | Data-root posture rule stated once | CompatibilityPolicy, CliApp | `docs/compatibility.md`, `cli.py` docstring | — |
| 4.1 | Every release recorded with date, newest first | Changelog | `CHANGELOG.md` | — |
| 4.2 | Grouped by change kind | Changelog | Keep a Changelog sections | — |
| 4.3 | Contract changes named with required action | Changelog, CompatibilityPolicy | `CHANGELOG.md` | — |
| 4.4 | Standing unreleased section | Changelog, ContributionDocs | `## [Unreleased]` | — |
| 4.5 | Written for users, not commit-derived | Changelog, ContributionDocs | `CONTRIBUTING.md` | — |
| 4.6 | Shipped or reachable from the artifact | PackageManifest, ArtifactPolicy | `[project.urls]`, `required_members` | — |
| 4.7 | Missing or stale entry blocks the release | ArtifactChecker | `check_version_consistency` | Release pipeline |
| 5.1 | Documented end-to-end procedure | ReleaseProcedure | `docs/releasing.md` | Release pipeline |
| 5.2 | Tests, lint, strict types before publication | CiWorkflow, ReleaseWorkflow | gate jobs | Release pipeline |
| 5.3 | Verify by installing the artifact in a clean environment | ReleaseWorkflow, InstalledToolVerification | install-and-run job | Release pipeline |
| 5.4 | Artifacts contain exactly what is required | ArtifactChecker, ArtifactPolicy | `check()` | Encumbered-content gate |
| 5.5 | Version tag records the released revision | ReleaseWorkflow, ReleaseProcedure | tag trigger | Release pipeline |
| 5.6 | Rehearsal path not touching the public index | ReleaseWorkflow | rehearsal publish job | Release pipeline |
| 5.7 | Short-lived per-release credentials | ReleaseWorkflow | OIDC publish, `id-token: write` | Release pipeline |
| 5.8 | Any gate failure stops before publication | ReleaseWorkflow | job dependency chain | Release pipeline |
| 5.9 | Post-publication install and version check | ReleaseWorkflow, ReleaseProcedure | verification job | Release pipeline |
| 5.10 | Automation runs the same gates as a maintainer | ReleaseWorkflow, ReleaseBuilder, ArtifactChecker | shared scripts | Release pipeline |
| 1.10 | No symbolic-link member; a link is a violation, never skipped | PackageManifest, ArtifactChecker | sdist allowlist, `LINK_MEMBER` | Encumbered-content gate |
| 6.1 | No artifact carries the removed material | ArtifactChecker, GuardCores | token + value scan | Encumbered-content gate |
| 6.2 | Gate inspects artifacts and stops the release | ArtifactChecker, ReleaseWorkflow | `check()` exit status | Encumbered-content gate |
| 6.3 | Match data from the purge guard's single out-of-repository source | ArtifactChecker, GuardCores, MatchData | `tests._forbidden_strings.load` | Encumbered-content gate |
| 6.4 | *withdrawn (Amendment 2)* | — | — | — |
| 6.5 | *withdrawn (Amendment 2)* | — | — | — |
| 6.6 | Built-in calculator change is a contract change in the changelog | Changelog, CompatibilityPolicy | `CHANGELOG.md` | — |
| 6.7 | Gate reads artifacts, not the source tree | ArtifactChecker | archive member and metadata scan | Encumbered-content gate |
| 6.8 | *withdrawn (Amendment 2)* | — | — | — |
| 6.9 | Absent match data stops the release as "gate did not run" | ArtifactChecker, ReleaseWorkflow, ReleaseProcedure | `GATE_NOT_RUN` | Encumbered-content gate |
| 6.10 | One artifact set per release, no profiles | ReleaseBuilder | `build()` | Release pipeline |
| 7.1 | First-run path from install to a document | InstallDocs | `docs/install.md` | — |
| 7.2 | Standalone and wiki-hosted data roots | InstallDocs | `docs/install.md` | — |
| 7.3 | Exact upgrade and uninstall commands | UpgradeDocs | `docs/upgrading.md` | — |
| 7.4 | What an upgrade does not touch | UpgradeDocs | `docs/upgrading.md` | — |
| 7.5 | The one command that brings documents current | UpgradeDocs | `docs/upgrading.md` | — |
| 7.6 | What persists after uninstall | UpgradeDocs | `docs/upgrading.md` | — |
| 7.7 | Data-root contract kept prominent | ConfigurationDocs, DocsGuaranteeTest | `docs/configuration.md` | — |
| 7.8 | Offline behavior and network switch-off | ConfigurationDocs, DocsGuaranteeTest | `docs/configuration.md` | — |
| 7.9 | One documentation entry point, inbox included | DocsEntry, InboxDocs, DocsGuaranteeTest | `docs/index.md`, `docs/inbox.md` | — |
| 8.1 | Published agent skill for the inbox workflow | AgentSkillPackage | `SKILL.md` | — |
| 8.2 | When it applies, commands, every channel, exceptions | AgentSkillPackage | `SKILL.md` body | — |
| 8.3 | Ownership boundary pointing at the declaration | AgentSkillPackage | `SKILL.md` body | — |
| 8.4 | Refers rather than restates | AgentSkillPackage | `SKILL.md` body | — |
| 8.5 | Usable as plain markdown | AgentSkillPackage, AgentSkillTest | frontmatter + body | — |
| 8.6 | Where to install, verify, and update the skill | WikiIntegrationDocs, AgentSkillLocator, CliApp | `skill` command | — |
| 8.7 | End-to-end wiki adoption recipe | WikiIntegrationDocs | `docs/wiki-integration.md` | — |
| 8.8 | Released with the tool; named commands and channels exist | AgentSkillPackage, AgentSkillTest | `metadata.version`, CLI surface check, channel-name check | — |
| 9.1 | Contributor path and quality gates | ContributionDocs | `CONTRIBUTING.md` | — |
| 9.2 | Changelog duty and policy application | ContributionDocs | `CONTRIBUTING.md` | — |
| 9.3 | Public versus internal, by reference | ContributionDocs, CompatibilityPolicy | `CONTRIBUTING.md` | — |
| 9.4 | Guidance for calculator publishers | ContributionDocs | `CONTRIBUTING.md` | — |
| 9.5 | Encumbered material must not be added | ContributionDocs, GuardCores | `CONTRIBUTING.md` | — |
| 10.1 | No new runtime dependency | Technology Stack, PackageManifest | dependency list unchanged | — |
| 10.2 | Artifact behaves as the tested revision | ReleaseBuilder | no build hooks, no codegen | Release pipeline |
| 10.3 | No personal data in any artifact | ArtifactPolicy, ArtifactChecker | sdist allowlist, undeclared-member rule | Encumbered-content gate |
| 10.4 | No new runtime network access | DeterminismGuard | existing offline test extended | — |
| 10.5 | Same revision builds to identical contents | ReleaseBuilder, ReleaseArtifactTest | deterministic timestamps | Release pipeline |
| 10.6 | Documentation reorganization loses nothing, siblings included | DocsGuaranteeTest, ConfigurationDocs, InboxDocs | statement assertions | — |
| 10.7 | README rewrite preserves sibling-published sections | DocsGuaranteeTest, InboxDocs | relocation + link assertions | — |

## Components and Interfaces

| Component | Domain/Layer | Intent | Req Coverage | Key Dependencies (P0/P1) | Contracts |
|-----------|--------------|--------|--------------|--------------------------|-----------|
| PackageManifest | packaging | Declare identity, dependencies, and artifact contents | 1.1–1.4, 1.6, 1.8, 1.9, 2.1, 4.6, 10.1 | hatchling (P0) | State |
| VersionSource | package (leaf) | One resolved version, or *unknown* | 2.1–2.4 | `importlib.metadata` (P0) | Service |
| AgentSkillLocator | package (leaf) | Resolve the packaged skill directory | 8.1, 8.6 | `importlib.resources` (P0) | Service |
| AgentSkillPackage | package data | The published agent skill | 8.1–8.5, 8.8 | AgentSkillLocator (P1) | State |
| CliApp additions | cli | Version display and the read-only `skill` command | 2.2, 2.3, 8.6 | VersionSource (P0), AgentSkillLocator (P0) | Service |
| GuardCores | purge-owned test helpers | The one definition of the removed material: token matcher over out-of-repository data, digest-keyed value oracle | 6.1, 6.3 | MatchData (P0) | Service (consumed, not owned) |
| ArtifactPolicy | policy data | Required members per artifact kind, forbidden patterns, required metadata fields | 1.5, 1.6, 5.4, 10.3 | — | State |
| ReleaseBuilder | release tooling | One deterministic build of the working tree | 1.4, 6.10, 10.2, 10.5 | hatchling (P0) | Batch |
| ArtifactChecker | release tooling | Conformance, link-member, encumbered-content (fail-closed), and version consistency gates | 1.3, 1.5–1.8, 1.10, 2.6, 4.7, 5.4, 6.1, 6.2, 6.3, 6.7, 6.9, 10.3 | ArtifactPolicy (P0), GuardCores (P0), Changelog (P0) | Batch |
| CiWorkflow | automation | Quality gates on every change | 5.2 | ReleaseBuilder (P1), ArtifactChecker (P1) | Batch |
| ReleaseWorkflow | automation | Tag-triggered gated publication | 2.5, 5.2, 5.3, 5.5–5.10 | ReleaseBuilder (P0), ArtifactChecker (P0), publishing action (P0) | Batch |
| Changelog | documentation | Per-release account against the policy | 4.1–4.6, 6.6 | CompatibilityPolicy (P1) | State |
| CompatibilityPolicy | documentation | What version numbering promises; what is public; who needs a data root | 3.1–3.10, 6.6 | — | — |
| InstallDocs / ConfigurationDocs / UpgradeDocs | documentation | Install, configure, upgrade, uninstall | 7.1–7.8, 10.6 | — | — |
| InboxDocs | documentation | The inbox interface as a linked, user-facing document | 7.9, 10.6, 10.7 | inbox spec's published section (P1) | — |
| WikiIntegrationDocs | documentation | Skill installation and the adoption recipe | 8.6, 8.7 | AgentSkillPackage (P1) | — |
| ReleaseProcedure | documentation | The ordered, gated procedure | 5.1, 5.3, 5.5, 5.6, 5.9, 5.10, 6.9 | ReleaseBuilder (P0), ArtifactChecker (P0) | — |
| ContributionDocs | documentation | Contributor and calculator-publisher expectations | 9.1–9.5 | CompatibilityPolicy (P1) | — |
| DocsEntry | documentation | The single entry point | 7.9, 3.7 | — | — |

### Package (leaves)

#### VersionSource (`src/fitdocs/version.py`)

| Field | Detail |
|-------|--------|
| Intent | The one place the running tool learns which release it is |
| Requirements | 2.1, 2.2, 2.3, 2.4 |

**Responsibilities & Constraints**

- Resolves the installed distribution's version through the standard metadata mechanism and returns it, or `None` when the distribution is not installed. It never raises and never fabricates (2.4), matching the project's absent-data rule.
- Provides one display form for surfaces that must render *something* — the version, or a fixed `unknown` token. The token is a constant, so it cannot vary between runs.
- Performs the lookup lazily at the point of use. The module holds no import-time work and no cached module-level state beyond the distribution name, because metadata reads are slow enough to matter for CLI startup.
- Imports nothing from `fitdocs`. It is the leaf every version consumer depends on, so it may not acquire a package dependency without inverting the direction.

**Dependencies**

- Inbound: CliApp, TileStore, PluginDiscovery (P0).
- External: `importlib.metadata` (P0).

**Contracts**: Service [x]

##### Service Interface

```python
DIST_NAME: Final[str] = "fitdocs"
UNKNOWN_VERSION: Final[str] = "unknown"

def tool_version() -> str | None:
    """The installed distribution's version, or None when not installed."""

def version_display() -> str:
    """tool_version(), or UNKNOWN_VERSION — never raises, never empty."""
```

- Preconditions: none.
- Postconditions: `tool_version` returns a non-empty string or `None`; `version_display` returns a non-empty string; neither writes, prompts, or performs network access.
- Invariants: for one installed distribution both functions agree; `version_display()` equals `tool_version()` whenever the latter is not `None`.

**Implementation Notes**

- Integration: `cli.py`'s eager `--version` callback, `tiles.py`'s user-agent composition, and `plugins.py`'s built-in origin version all read from here. `plugins.py` uses `tool_version()` directly so an unknown version stays `None` in the listing rather than becoming a fabricated string, which plugin-api Req 4.3 forbids.
- Validation: unit tests for the resolved and unresolved paths with the metadata lookup patched; an installed-tool test asserting the reported version equals the manifest's; a source-tree test asserting `--version` prints the unknown token and exits 0 instead of raising.
- Risks: a second version declaration creeping in (a `__version__` attribute, a hardcoded string in a docstring) — mitigated by a repository scan that fails on any occurrence of the released version literal outside the manifest and the two places checked against it for equality: the changelog's newest released entry and the agent skill's recorded version.

**Amendment 1 (2026-09-16, landed by build-training-block)**: the permitted
copies of the released version are one `metadata.version` per
`PACKAGED_SKILLS` entry, not one fixed "the agent skill's recorded version" —
two packaged skills mean two recorded versions, and the repository scan
above allows exactly those alongside the changelog's newest entry.

#### AgentSkillLocator (`src/fitdocs/agentskill.py`)

| Field | Detail |
|-------|--------|
| Intent | Give the packaged skill one resolution path shared by the command and its tests |
| Requirements | 8.1, 8.6 |

**Responsibilities & Constraints**

- Resolves a packaged skill directory inside an installed distribution through package-data resource resolution, so it works from a wheel install, a source checkout, and a `uv tool` environment alike.
- Returns `None` when the skill data is absent rather than raising, so a packaging defect surfaces as an instructive command message instead of a traceback.
- Holds every packaged skill's canonical name in the `PACKAGED_SKILLS` registry, because the Agent Skills standard requires the directory name and the frontmatter `name` to be equal — the registry entry is what the conformance test asserts both against *(Amendment 2: "the constant" → the registry, per Amendment 1)*.
- Reads nothing else and writes nothing.

**Dependencies**

- Inbound: CliApp (P0), AgentSkillTest (P1).
- External: `importlib.resources` (P0).

**Contracts**: Service [x]

```python
INBOX_SKILL_NAME: Final[str] = "fitdocs-workouts"        # appended by task 4.2
PACKAGED_SKILLS: Final[tuple[str, ...]] = ("build-training-block", INBOX_SKILL_NAME)

def skill_root(name: str) -> Path | None:
    """The packaged skill directory for a registered name, or None when absent."""

def skill_file(name: str) -> Path | None:
    """The packaged SKILL.md for a registered name, or None when absent."""

def skill_files(name: str) -> tuple[Path, ...]:
    """Every regular file under a packaged skill's directory."""
```

- Postconditions: any returned path exists and is readable; nothing is created.
- Invariants: `skill_root(name)`'s final path component equals `name`, and `name` is a `PACKAGED_SKILLS` entry. *(Amendment 2: the block above formerly showed the single-name `SKILL_NAME` shape Amendment 1 retired; it now shows the shape as landed.)*

**Amendment 1 (2026-09-16, landed by build-training-block)**: `SKILL_NAME` is
retired in favour of a registry `PACKAGED_SKILLS: tuple[str, ...]` holding
this skill's name — renamed `INBOX_SKILL_NAME` (value `"fitdocs-workouts"`)
and appended by task 4.2 — alongside `build-training-block`'s own; the two
no-argument resolvers become
`skill_root(name)` and `skill_file(name)`, and a third resolver,
`skill_files(name)`, lists every regular file under a packaged skill's
directory. Resolution is otherwise unchanged: absent-by-default, nothing at
import time, nothing from `fitdocs` imported, nothing written.

#### AgentSkillPackage (`src/fitdocs/skills/fitdocs-workouts/SKILL.md`)

| Field | Detail |
|-------|--------|
| Intent | The turnkey inbox workflow an LLM wiki maintainer installs |
| Requirements | 8.1, 8.2, 8.3, 8.4, 8.5, 8.8 |

**Responsibilities & Constraints**

- Frontmatter conforms to the open standard's field contract: `name` equal to the directory name and to its `PACKAGED_SKILLS` entry (`INBOX_SKILL_NAME`); a `description` within the published length limit that states both what the skill does and when to use it; `license`; a `compatibility` note naming the requirement that the `fitdocs` command be installed and on the agent's path; and the release version carried under `metadata`, because the standard defines no top-level version field (8.8).
- The body covers, in order: when this applies (new `.fit` files have arrived, or the wiki's workouts look stale); the commands to run and in what order; how to read **every** reported channel — written, skipped, failed, deferred, quarantined, moved, **move failures**, and warnings; what to do about each exceptional channel, including that a deferred file needs no action, a quarantined file needs the user rather than the agent, and a move failure means the file was processed successfully and will be retried on the next drain, so it is not a reason to reprocess anything; and the ownership boundary (8.2). The channel list is the drain report's own set — inbox reports `move_failures` as a row of its own, and an enumeration that omits it teaches an agent to misread a clean run as a partial one.
- The ownership section states the boundary and then **defers**: it names the in-tree ownership declaration as the authority and the published contract as the detail, and does not enumerate owned paths, region ids, or managed frontmatter keys (8.3, 8.4). This is what keeps the skill from drifting when wiki-contract's enumerations change.
- The body is ordinary markdown with no client-specific syntax, so a human or a non-supporting agent environment can follow it directly (8.5). No `allowed-tools` field, which the standard still flags experimental and which would not port.
- Body length stays inside the standard's recommended budget; anything longer belongs in the documentation the skill links to.

**Contracts**: State [x]

- State: a static file shipped as package data; it carries no runtime state and is never written by the tool.
- Invariants: every `fitdocs` command and option named in the body exists in the release's registered command surface, and every reported channel the body names is one the drain report actually carries (8.8); the `metadata` version equals the released version; the frontmatter parses as a mapping with the two required keys present and within their length limits.

**Implementation Notes**

- Integration: shipping the skill *inside the package* is what locks it to the release and makes it reachable from an index-only install; the `skill` command prints where it landed, and the documentation gives the copy and symlink recipes for the common agent clients.
- Validation: `tests/test_agent_skill.py` parses the frontmatter against the field constraints, asserts `name` equals both the directory name and its `PACKAGED_SKILLS` entry, asserts the recorded version matches the manifest, and extracts every `fitdocs <command>` and `--option` occurrence from the body, asserting each exists in the typer application's registered surface. A second binding covers the **channels**: the set of channel names the body documents is compared against the drain report's own field set, so a channel added, renamed, or dropped by inbox fails this test rather than silently leaving the skill incomplete. Command binding alone would not catch it (8.8).
- Risks: the standard is versionless and evolving, so a future field could become required — mitigated by keeping the frontmatter to the documented required-plus-stable set and by the conformance test failing loudly rather than silently accepting an unknown shape.

**Amendment 1 (2026-09-16, landed by build-training-block)**: a second
packaged skill, `build-training-block`, ships alongside this one under the
same `skills/` location. The conformance test is `tests/test_agent_skill.py`,
generalized over `PACKAGED_SKILLS` with a per-skill map (heading tuple,
channel binding) rather than a single fixed body; task 4.2 adds this skill's
entry to that map when it lands — the frame is not re-written.

### CLI

#### CliApp additions (`src/fitdocs/cli.py`)

| Field | Detail |
|-------|--------|
| Intent | Report one version everywhere and tell the user where the skill is |
| Requirements | 2.2, 2.3, 8.6 |

**Responsibilities & Constraints**

- The existing eager `--version` callback prints `version_display()` and exits 0. From an uninstalled source tree it prints the unknown token rather than raising (2.4) — today it raises.
- A new `skill` command prints the packaged skill directory's absolute path plus a one-line recipe for copying it into an agent's skills directory, and exits 0. It resolves no data root, loads no profile, constructs no tile store, runs no engine, and **writes nothing** — the tool never installs into a location it does not own.
- If the skill data is absent from the installed package, the command reports that through the existing configuration-error path (an instructive message, exit 2), because it means the install is incomplete rather than that the user did something wrong.
- The module docstring's command list and exit-code contract are amended for the new command; the 0/1/2 contract itself is unchanged. The docstring also records the project-wide data-root posture rule in code — *commands that describe the installed tool need no data root; commands that describe or change a tree require one* (3.10) — with `skill` as an instance of the first half: it resolves nothing, so it cannot fail for want of a data root, which is exactly the posture `plugins` takes and the opposite of `check`'s.

**Contracts**: Service [x]

**Implementation Notes**

- Validation: CLI tests for `skill` printing an existing path and exiting 0, for the absent-skill path exiting 2 with an instructive message, and for `--version` on an uninstalled tree.
- Risks: command-surface churn across three concurrent Phase 3 specs — mitigated by the skill conformance test, which fails the moment the skill names a command that no longer exists.

**Amendment 1 (2026-09-16, landed by build-training-block)**: `skill` gains
one optional positional argument, `NAME`. No argument lists every registered
name and its directory (or absence); a registered name prints its directory
and a copy recipe; an unregistered name is the configuration-error path
(exit 2) listing the packaged names. The no-argument and absent-skill forms
above are the `NAME`-omitted case of this widened command, not a second one.

### Load

#### BuiltInRegistration — retired *(Amendment 2, 2026-09-18)*

This block designed a guarded import of the bundled methodology package and a conditionally-assembled `__all__` for `src/fitdocs/load/__init__.py` (former 6.4, 6.8). Both criteria are withdrawn: the methodology was withdrawn on 2026-07-25 and purged on 2026-08-23, and the package now registers the unencumbered `threshold` built-in unconditionally — `available()` returns exactly that one calculator in a fresh interpreter, which `tests/load/test_packaging.py` already pins. This design does not modify `fitdocs.load`. The tool's behaviour when a *configured* calculator is absent belongs to plugin-api and threshold-load, not to a build configuration this spec produces.

### Policy Data

#### ArtifactPolicy (`release/artifact-policy.toml`) *(Amendment 2: formerly "LicensingRecord and ArtifactPolicy")*

| Field | Detail |
|-------|--------|
| Intent | Make the release's one remaining judgement call — what an artifact must and must not contain — reviewable data rather than script internals |
| Requirements | 1.5, 1.6, 5.4, 10.3 |

**Responsibilities & Constraints**

- `artifact-policy.toml` declares what an artifact must contain, what it must never contain, and the metadata fields a release must declare. Required members are matched per artifact kind, because a wheel and an sdist legitimately differ.
- It carries **no content marker list** (6.3). What the removed material *is* lives in the purge's match data outside the repository and in its digest set; a marker list inside the repository could only ever name the redaction placeholder (queue item `2026-08-04-distribution-forbidden-markers-scan-for-the-placeholder`), and the purge forbids retaining any forbidden term in the tree in any readable form.
- It carries **no permission state and no prune list** (6.10). `release/licensing.toml` is not created. *(Amendment 2: that file recorded a permission decision for a methodology that no longer exists.)*
- The symbolic-link rule (1.10) is **not** policy data: the checker applies it unconditionally, so no policy edit can declare a link acceptable.
- Pure data: no expressions, no code, no environment lookups. A gate decision must be readable by a person who does not read Python. Not shipped in any artifact.

**Contracts**: State [x]

##### Data Shape

```toml
# release/artifact-policy.toml
[wheel]
required = ["fitdocs/__init__.py", "fitdocs/py.typed",
            "fitdocs/skills/build-training-block/SKILL.md",
            "fitdocs/skills/build-training-block/example-block.toml",
            "fitdocs/skills/fitdocs-workouts/SKILL.md"]       # last entry arrives with task 4.2

[sdist]
required = ["pyproject.toml", "README.md", "LICENSE", "CHANGELOG.md",
            "src/fitdocs/__init__.py"]

[forbidden]
members = ["tests/*", ".kiro/*", "scripts/*", "release/*", "docs/*", "*.xlsx", "*.fit",
           "*.gpx", "uv.lock", "data/*", "*/.fitdocs/*", "agent-log"]

[metadata]
required_fields = ["Name", "Version", "Summary", "License-Expression",
                   "Requires-Python", "Project-URL"]
```

- Invariants: the shape above is the **end state**; each required member is declared by whichever task creates the file it names, so the inbox skill's entry arrives with the skill and not before. `agent-log` appears in `forbidden.members` as belt-and-braces beside the sdist allowlist and the unconditional link rule — three independent reasons the symlink cannot ship. *(Amendment 2: `required_when_bundled` and `[forbidden].markers` are gone with the profile split and the in-repository marker list.)*

### Release Tooling

#### ReleaseBuilder (`scripts/build_release.py`)

| Field | Detail |
|-------|--------|
| Intent | Produce the release's one artifact set, deterministically, from the working tree |
| Requirements | 1.4, 6.10, 10.2, 10.5 |

**Responsibilities & Constraints**

- Builds from the working tree, always. There is no profile, no prune list, and no per-release selection between variants (6.10). *(Amendment 2: the bundled/unencumbered profile selection this block used to own is retired with the permission question.)*
- Produces both a wheel and a source distribution in one invocation (1.4), through the project's existing build front end with no build hooks and no code generation, so the installed artifact is the tested revision (10.2).
- Sets a deterministic timestamp source for the build so that two builds of the same revision produce archives with identical member sets and identical member contents (10.5).
- Writes only into the output directory. It performs no network access and never publishes.

**Dependencies**

- Inbound: ReleaseWorkflow (P0), ReleaseProcedure (P0), ReleaseArtifactTest (P1).
- External: the build front end and backend (P0); stdlib `subprocess`, `shutil`, `pathlib` (P0).

**Contracts**: Batch [x]

##### Batch / Job Contract

```python
def build(*, out_dir: Path, source_date_epoch: int | None) -> tuple[Path, ...]: ...
def main(argv: Sequence[str]) -> int: ...   # 0 built, 1 build failed
```

- Trigger: a maintainer running the documented step, or the release workflow's build job.
- Output: exactly one wheel and one sdist in the output directory.
- Idempotency & recovery: the output directory is cleared before building, so a re-run replaces rather than accumulates; a failed build leaves no partial artifact behind.

**Implementation Notes**

- Validation: a reproducibility test builds twice and compares member names and content digests; the artifact test asserts exactly one wheel and one sdist result.
- Risks: none specific to the builder — every judgement about the artifact's *contents* is the checker's, which is the point of the split.

#### ArtifactChecker (`scripts/check_artifacts.py`)

| Field | Detail |
|-------|--------|
| Intent | Decide, from the artifacts alone, whether this release may be published |
| Requirements | 1.3, 1.5, 1.6, 1.7, 1.8, 1.10, 2.6, 4.7, 5.4, 6.1, 6.2, 6.3, 6.7, 6.9, 10.3 |

**Responsibilities & Constraints**

- Opens each artifact in the output directory, enumerates its members, and reads its distribution metadata. Everything the gate decides is decided from that evidence; the source tree is never consulted for content (6.7).
- Applies five independent checks and reports **all** violations rather than stopping at the first, so one run fixes the whole release: required members present per artifact kind; no forbidden member present; **no member is a symbolic link** (1.10); no removed material in any text-like member's content or in the distribution metadata (6.1); every required metadata field declared and non-empty.
- The encumbered-content check has **no matcher of its own** (6.3). It calls the purge's token core — `tests._forbidden_strings.load(repo_root)` for the match data and `matches(text, forbidden_strings)` per member — and the purge's value core — `tests._content_oracle.scan(text, FINGERPRINTS, WINDOW_LENGTHS, SALT)` with the constants from `tests._content_fingerprints`. Both are exactly what `tests/load/test_packaging.py` already runs over a built artifact; the checker adds the binding to the release path, not a second definition.
- **Fails closed** (6.9): `load` returning `None` — the token source unset — is a `GATE_NOT_RUN` violation naming the environment variable to set, never a skip and never a pass; `ForbiddenStringsSourceError` (set but missing, unreadable, empty, or inside the working tree) is a hard error. In an ordinary developer run the purge's guards skip distinguishably; a *release* step that did not scan has gated nothing, and the checker is only ever run as a release step or in CI.
- Runs one consistency check that needs no artifact opened: the manifest version, the changelog's newest released entry, and — when supplied — the release tag must all agree (2.6, 4.7).
- The metadata scan matters because the long description is the readme rendered into the distribution metadata; a member-name-only scan would let a token in prose past the gate.
- Text scanning is confined to text-like members (source, markdown, data, metadata); binary members are matched by name only. A link member is never opened — its bytes are its target path — which is why it is a violation of its own kind rather than a scanned member.
- Reports each violation with the subject it concerns, what was observed, and the action that resolves it — the same finding shape the project's other read-only inspection uses. Exit 0 when clean, 1 when any violation was found. It never modifies, deletes, or publishes anything.
- **Report vocabulary (project-wide convention for Phase 3 report types)**: fields are named `(subject, detail[, remedy])` — `subject` is what the finding is about (here, the artifact filename), `detail` is what was observed, `remedy` is the action that resolves it. Classification enums are `StrEnum`, so a finding renders without a conversion step and sorts by its member value. `Violation`'s leading field is `subject`, not `artifact`, so the shape reads the same as the siblings' report types.

**Dependencies**

- Inbound: ReleaseWorkflow (P0), CiWorkflow (P0), ReleaseProcedure (P0), ReleaseArtifactTest (P1).
- Outbound: ArtifactPolicy (P0), GuardCores — `tests._forbidden_strings`, `tests._content_oracle`, `tests._content_fingerprints` (P0), Changelog (P0), PackageManifest (P0).
- External: stdlib `zipfile`, `tarfile`, `tomllib`, `email` (P0). Invoked as `python -m scripts.check_artifacts` from the repository root so the `tests` package resolves; `scripts/__init__.py` exists for that reason and nothing else.

**Contracts**: Batch [x]

##### Batch / Job Contract

```python
class ViolationKind(StrEnum):
    MISSING_REQUIRED     # a required member is absent from the artifact
    FORBIDDEN_MEMBER     # a member matches a forbidden pattern
    LINK_MEMBER          # a member is a symbolic link, whatever its target (1.10)
    ENCUMBERED_CONTENT   # the removed material matched in a member or the metadata (6.1)
    GATE_NOT_RUN         # the token match data is unset; the content gate did not run (6.9)
    METADATA_INCOMPLETE  # a required metadata field is missing or empty
    VERSION_MISMATCH     # manifest, changelog, and tag do not agree

@dataclass(frozen=True)
class Violation:
    subject: str    # the artifact filename, or "" for the version consistency check and GATE_NOT_RUN
    kind: ViolationKind
    detail: str     # what was observed, naming the member where applicable
    remedy: str     # the action that resolves it

def check_artifacts(dist_dir: Path, *, policy: ArtifactPolicy,
                    repo_root: Path) -> tuple[Violation, ...]: ...
def check_version_consistency(manifest: Path, changelog: Path,
                              tag: str | None) -> tuple[Violation, ...]: ...
def main(argv: Sequence[str]) -> int: ...   # 0 clean, 1 violations found
```

- Trigger: the documented manual step, the release workflow's gate job, and the CI workflow on every change.
- Input / validation: an output directory containing exactly one wheel and one sdist; a missing or malformed policy file is a hard error, never a silently-skipped check; `repo_root` is passed to the token core's `load`, which refuses match data that resolves inside it.
- Output: a violation listing on standard error and a process exit status. Nothing is written.
- Idempotency & recovery: read-only and repeatable; running it twice on the same artifacts yields the same violations in the same order (sorted by subject, then kind, then detail).

**Implementation Notes**

- Integration: CI runs the builder and the checker on every change, so a manifest edit that would break a release fails on the pull request rather than at release time. CI and the release workflow supply the token match data as a repository secret written to a runner-local file outside the checkout; a workflow that cannot supply it fails on `GATE_NOT_RUN`, which is the intended outcome.
- Validation: fixture-driven tests construct artifacts that trip each violation kind exactly once, plus a clean artifact that trips none. The `ENCUMBERED_CONTENT` fixtures plant a **synthetic** needle supplied through a test-written match file (the same technique `tests/test_forbidden_strings.py` already uses — never a real token) and a **fingerprinted control value** (the same technique `tests/load/test_packaging.py`'s positive control uses); the `GATE_NOT_RUN` fixture unsets the variable and asserts a violation, not a skip; the `LINK_MEMBER` fixture plants a symlink member and asserts it is reported even when its target text is clean.
- Risks: a false positive blocking a legitimate release (a match in unrelated prose) — accepted deliberately: the gate fails closed, and the remedy is to reword rather than to weaken the match data. The residual risk is the one 6.9 exists for: a runner without the secret would otherwise pass an unscanned artifact.

### Automation

#### CiWorkflow and ReleaseWorkflow (`.github/workflows/`)

| Field | Detail |
|-------|--------|
| Intent | Run the same gates a maintainer runs, and make publication the last thing that happens |
| Requirements | 2.5, 5.2, 5.3, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10 |

**Responsibilities & Constraints**

- **CI** runs on push and pull request: the full test suite, the linter, and the strict type check on the project's supported Python floor, followed by a build and an artifact conformance check. It publishes nothing (5.2).
- **Release** is triggered by a version tag (5.5) and is a chain of dependent jobs in the order the release-pipeline flow shows. Each job's failure prevents every later job, so publication is unreachable unless every gate passed (5.8).
- The clean-environment verification job installs the *built artifact* into an isolated tool environment and runs the installed console script — never the working tree (5.3).
- The rehearsal job publishes to the rehearsal index before the public one (5.6). The public publish job targets an environment that requires manual approval, which is what makes even a deliberate hand-triggered release cross a recorded gate.
- Both publish jobs authenticate by short-lived, per-release OIDC credentials with the identity-token permission scoped to that job alone; no long-lived secret exists in or alongside the project (5.7). Signed attestations accompany the upload by default with the current publishing action.
- The public publish job does not tolerate an already-present version: a re-run of a spent version fails rather than silently skipping, which is how "publish exactly once" is enforced mechanically (2.5).
- A final job installs the published version from the public index in a fresh environment and asserts the reported version matches the tag (5.9).
- Every gate is the project's own script or the project's own test command, so the maintainer path in `docs/releasing.md` and the automation path execute identical logic (5.10).
- The publish job is inline rather than factored into a reusable workflow, because trusted publishing does not work from one.

**Contracts**: Batch [x]

**Implementation Notes**

- Validation: workflow correctness is verified by a rehearsal release to the rehearsal index; the gates themselves are covered by the test suite, so the workflow contributes ordering and credentials, not logic.
- Risks: an index-side policy change silently altering publication requirements — noted as a revalidation trigger, with the rehearsal path as the standing early warning.

### Documentation

#### CompatibilityPolicy (`docs/compatibility.md`)

| Field | Detail |
|-------|--------|
| Intent | State what the version number promises, contract by contract — and carry the three project-wide statements that need exactly one home |
| Requirements | 3.1–3.10, 6.6 |

**Responsibilities & Constraints**

- Names the three governed contracts explicitly — the generated-document and ownership contract, the inbox interface, and the load-calculator plugin API and its documented import surface — and states the Datasette-style rule that documented means public and everything else, including anything undocumented or underscore-prefixed, is internal and may change in any release (3.1).
- Defines, per contract, what breaking / additive / internal mean (3.2): for the document contract, a change to the frontmatter's managed keys, the region ownership policy, or the document-format version; for the inbox interface, a change to the settings schema's meaning, the disposition guarantees, or the reported channels; for the plugin API, a change to the calculator contract's required members, the entry-point group, or a documented public name.
- States the numbering rules before and after the first stable release (3.3), following the widespread pre-1.0 convention that the minor position carries breaking changes while major zero holds, and full semantic versioning from the first stable release.
- Maps the three internal version identifiers onto releases and user action (3.4): a document-format version bump is a compatible change requiring one regeneration command; an ownership-contract version bump is a compatible change requiring nothing; a settings-schema change that invalidates an existing configuration is breaking.
- States the deprecation model (3.6): announced in the changelog and in the tool's output where it can be, kept for at least two minor releases before removal, and never removed in a patch release.
- Guarantees that a compatible upgrade requires no edit to the settings file, the athlete profile, or a local plugin (3.5), and is the single statement the readme, the plugin documentation, and the contribution documentation all point at (3.7).
- **Governs the user-facing settings schema as a named contract (3.8).** `<data-root>/fitdocs.toml` is one schema with three tables today — `[tiles]`, `[inbox]`, `[plugins]` — each read by its owning feature but all of them user-written and all documented. `[tiles]` is governed like the others rather than left ungoverned: breaking is removing a key, narrowing an accepted value, or changing a default in a way that changes behavior for an unchanged file; additive is a new optional key with a behavior-preserving default; internal is anything about how the file is parsed, including the shared loader and its error type.
- **Carries the project's single public-versus-internal statement (3.9).** The authority for the public *import* surface is plugin-api's enumeration (`fitdocs` and `fitdocs.load`, name by name); this document points at it rather than restating it, and states plainly that everything else is internal — naming `fitdocs.contract`, `fitdocs.inbox`, `fitdocs.plugins`, `fitdocs.version`, `fitdocs.agentskill`, `fitdocs.layout`, and `fitdocs.settings` as internal modules that a release may change freely, and that the bundled calculator class is not public either. Three specs edit `tests/test_public_api.py`; this statement is what they are all consistent with, and the contribution documentation refers to it instead of forming its own notion of "public" (9.3).
- **States the data-root posture rule once (3.10).** A command that describes the *installed tool* needs no data root; a command that describes or changes a *tree* requires one. That is why `skill` resolves no data root at all and exits 0 (it describes the installed tool), why `plugins` degrades and exits 0 without one (it describes the installed tool), and why `check` exits 2 without one (it describes a tree). `cli.py`'s module docstring carries the same rule in code so a new command's author meets it where the command is written.

#### Changelog (`CHANGELOG.md`)

- Keep a Changelog 1.1.2: a standing `## [Unreleased]` section, releases newest first as `## [X.Y.Z] - YYYY-MM-DD`, and the six canonical sections (4.1, 4.2, 4.4).
- A release entry that touches a governed contract names the contract and the user's required action inline in the entry, not in a footnote (4.3) — including removing the built-in calculator from a release or adding one (6.6).
- Entries describe user-observable behavior; the contribution documentation states that commit subjects are not changelog entries (4.5).
- The changelog ships inside the source distribution and is linked from the package metadata, so it is reachable from the artifact either way (4.6).
- The newest released entry's version is a release gate, checked by the artifact checker (4.7).

#### InstallDocs, ConfigurationDocs, InboxDocs, UpgradeDocs, WikiIntegrationDocs, ReleaseProcedure, ContributionDocs, DocsEntry — summary-only

- `docs/index.md` is the single entry point (7.9): install, configuration, **the inbox interface**, upgrading, wiki integration, the ownership contract (wiki-contract's document), the plugin platform (plugin-api's document), compatibility, releasing, and contributing. The readme links here rather than growing. The inbox was the one contract missing from an earlier draft of this list; since the agent skill's whole job is draining the inbox, an entry point that does not reach it is a hole rather than an omission.
- `docs/inbox.md` receives inbox's published interface material — the default location and how it resolves, every `[inbox]` key with its default and meaning, drain semantics, the safeguards, the disposition policy with its **never-delete guarantee**, and the plain statement that **fitdocs performs no watching and no scheduling** (10.6). The content is inbox's, moved verbatim, not restated: this feature owns *where it lives and that it stays reachable*, not what it says. A clearly named inbox section inside `docs/configuration.md` would satisfy 7.9 only if `docs/index.md` links that section separately; a dedicated document is preferred because the agent skill and the wiki-integration recipe both point at it.
- `docs/install.md` carries the first-run path — install command, choosing a data root and pointing at it, getting `.fit` files where fitdocs will find them, the first run, and the resulting document (7.1) — with a standalone section and a wiki-hosted section stating exactly what differs (7.2).
- `docs/configuration.md` receives the data-root contract with its resolution order and loud failure (7.7) and the offline/network material currently in the readme — what leaves the machine and when, the persistent opt-out, provider choice, attribution, and the cache (7.8, 10.6).
- `docs/upgrading.md` gives the upgrade and uninstall commands for both supported installers (7.3), states what an upgrade does not touch — user-owned regions, the settings file, the athlete profile, local plugin files, the archive (7.4) — names the single regeneration command when the document format moved and states that nothing else is required (7.5), and states what remains on disk after uninstalling and why (7.6).
- `docs/wiki-integration.md` covers the skill: where it lands, how to copy or symlink it into an agent's skills directory, how to confirm it is active, and that upgrading fitdocs means re-copying it (8.6); then the adoption recipe end to end — install, point the data root at the wiki, configure the inbox, run the first drain, confirm the documents and the emitted ownership declaration (8.7).
- `docs/releasing.md` is the ordered procedure with the command for each step (5.1) and the same gates the workflow runs (5.10), including the clean-environment verification (5.3), the rehearsal (5.6), and the post-publication check (5.9).
- `CONTRIBUTING.md` covers the development environment and the three quality gates (9.1), the changelog duty and the obligation to apply the compatibility policy to the version number (9.2), the public/internal boundary **by reference to `docs/compatibility.md`'s single statement**, which in turn defers to plugin-api's enumeration — the contribution guide forms no notion of "public" of its own (9.3, 3.9), guidance for someone publishing their own calculator distribution — the fitdocs version range to declare, verifying against a released version, and what the policy guarantees them, deferring authoring detail to the plugin documentation (9.4) — and the rule that third-party encumbered material must never be added to the repository or an artifact without recorded permission (9.5).

## Data Models

### Release policy data

One TOML document, human-edited and read by the checker, shown under Policy Data above. It is not shipped. Its shape is fixed by the checker's schema validation: an unknown key is tolerated, a missing required key or a wrongly-typed value is a hard error. *(Amendment 2: the second document, `licensing.toml`, and its granted-without-evidence rule are retired.)* The definition of the removed material is not repository data at all: the token match data lives outside the repository and the value digests are the purge's `tests/_content_fingerprints.py`.

### Artifact contents

| Artifact | Contains | Never contains |
|----------|----------|----------------|
| Wheel | the package tree, the type-information marker, every packaged skill's files, and the distribution metadata | tests, specifications, steering documents, reference material, lockfiles, spreadsheets, any `.fit`/`.gpx` file, any data-root content, any symbolic link |
| Source distribution | the manifest, the readme, the license, the changelog, and the package tree | everything in the wheel's *never* column, plus documentation (linked from metadata instead), the release scripts and policy, and the root `agent-log` link |

The sdist is an explicit allowlist rather than an exclusion list, so a file added later is absent by default. That is what makes 10.3 a structural property rather than a vigilance exercise.

**Doc references leave the repository, so they must not be repo-relative (1.9).** Because `docs/` ships in neither artifact, and because wiki-contract emits `AGENTS.md` into a user's tree that has no repository at all, a path like `docs/ownership-contract.md` resolves to nothing for the reader who most needs it. The rule: **anything shipped inside a distribution artifact — the README rendered into the distribution metadata, the changelog, the packaged `SKILL.md` — or emitted into a user's tree must reference documentation by its published project URL.** Repo-relative links stay legal only in files that never leave the repository (`.kiro/`, `CONTRIBUTING.md`'s internal pointers, `docs/` cross-links among themselves). `[project.urls]` therefore declares a documentation base URL plus the specific pages those artifacts point at — the ownership contract, the plugin platform, the inbox, and configuration — so every such reference has a URL to use. `tests/test_docs_guarantees.py` asserts the URL form for the shipped and emitted surfaces it can read.

### Version identity

One declaration in the manifest. Four derived appearances, all equal: the distribution metadata's version, the CLI's version output, the tile user-agent's version component, and the built-in calculator's reported version. Three further appearances are checked for equality without deriving from it — the changelog's newest released entry, the release tag, and the agent skill's recorded version — because their independence is exactly what makes the check meaningful. No other literal copy of the released version may exist anywhere in the repository.

**Amendment 1 (2026-09-16, landed by build-training-block)**: "the agent
skill's recorded version" above is, from this amendment forward, one
`metadata.version` per `PACKAGED_SKILLS` entry — a second packaged skill is
a second permitted, independently-checked copy, not a second literal copy
that violates "no other literal copy".

### Skill frontmatter

| Field | Presence | Constraint |
|-------|----------|-----------|
| `name` | required | equals the containing directory and its `PACKAGED_SKILLS` entry; lowercase alphanumeric and hyphens |
| `description` | required | non-empty, within the standard's length limit, states both what and when |
| `license` | present | the project's license identifier |
| `compatibility` | present | states that the `fitdocs` command must be installed and reachable. That is the contract for every packaged skill; a skill may add clauses of its own (`build-training-block` adds "a fitdocs data root already configured"), and the inbox skill does **not** carry that clause — configuring the data root is part of the workflow its body teaches (8.7), not a precondition of reading it *(decided by Amendment 2, closing the open question in queue item `2026-09-18-distribution-design-leftovers-after-amendment-1`)* |
| `metadata.version` | present | equals the released version (8.8) |

## Error Handling

### Error Strategy

Two postures, matching the codebase. **Release-time failures are loud and total**: any gate violation stops the procedure before publication, reports every violation it found, and leaves the index untouched. **Runtime degradations are quiet and honest**: an unresolvable version reports *unknown*. That is not an error and does not change an exit code. *(Amendment 2: the "package built without a methodology" degradation is retired with 6.4.)*

### Error Categories and Responses

| Condition | Classification | Response |
|-----------|----------------|----------|
| Tag, manifest, and changelog versions disagree (2.6, 4.7) | release gate | Report all three values, stop before the build |
| Required member missing from an artifact (1.5) | release gate | Name the artifact and the member, stop before publication |
| Forbidden member present in an artifact (1.6, 10.3) | release gate | Name the artifact and the member, stop before publication |
| Removed material matched in a member or the metadata (6.1, 6.2) | release gate | Name every offending member, stop before publication |
| Token match data unset when the checker runs (6.9) | release gate | `GATE_NOT_RUN`: name the variable to set, stop before publication; never a skip |
| Token match data set but unusable (6.9) | hard error | Stop before publication with the source error's own message |
| A member is a symbolic link (1.10) | release gate | Name the artifact and the member, stop before publication, whatever the link's target |
| Required metadata field missing (1.3) | release gate | Name the field, stop before publication |
| Clean-environment install or smoke run fails (5.3) | release gate | Stop before publication; the artifact, not the tree, is at fault |
| Rehearsal publication fails (5.6) | release gate | Stop before the public publish |
| Public publication rejected because the version exists (2.5) | release gate | Fail; never skip, never overwrite |
| Post-publication verification fails (5.9) | defect report | The version is spent; fix forward in the next release, never re-publish |
| Distribution not installed, version unresolvable (2.4) | runtime degradation | Report *unknown*, continue normally, exit code unchanged |
| Packaged skill absent from the installed distribution | configuration error | Instructive message naming the incomplete install, exit 2 |

### Monitoring

No telemetry and no logging framework, consistent with the project. Observability is the checker's violation listing, the workflow's job status, and the post-publication verification job.

## Testing Strategy

### Unit Tests

- **Version resolution**: resolved and unresolved lookups; `version_display()` returning the token rather than raising; both functions agreeing for an installed distribution; a repository scan asserting the released version literal appears only in the manifest and in the two equality-checked places — the changelog's newest released entry and the agent skill's recorded version (2.1–2.4).
  - **Amendment 1 (2026-09-16, landed by build-training-block)**: the scan's
    permitted set is the manifest, the changelog's newest entry, and every
    `PACKAGED_SKILLS` entry's recorded version — one `SKILL.md` per entry —
    and nowhere else.
- **Skill location**: the resolved directory's final component equals the canonical name; an absent skill resolves to `None` rather than raising (8.1, 8.6).
- **Policy reader**: each required key missing raises; a wrongly-typed value raises; an unknown key is tolerated (5.4).
- **Artifact checker rules**: fixture archives trip `MISSING_REQUIRED`, `FORBIDDEN_MEMBER`, `LINK_MEMBER`, `ENCUMBERED_CONTENT`, `GATE_NOT_RUN`, and `METADATA_INCOMPLETE` exactly once each; a clean archive trips none; violations sort deterministically; a synthetic token present only in the distribution metadata is caught; a link member whose target text is clean is still a violation; with the match variable unset the result is a `GATE_NOT_RUN` violation and not a skip (1.3, 1.5, 1.6, 1.10, 5.4, 6.1, 6.3, 6.7, 6.9).
- **Version consistency**: agreement passes; each of the three pairwise disagreements produces one violation naming both values (2.6, 4.7).
- **Skill frontmatter**: required fields present, within length limits, `name` equal to the directory and its `PACKAGED_SKILLS` entry, recorded version equal to the manifest's (8.5, 8.8).

### Integration Tests

- **The one build**: exactly one wheel and one sdist result; the sdist's member set is the allowlist and nothing else — no `tests/`, `.kiro/`, `scripts/`, `release/`, `docs/`, and no `agent-log` (1.4, 1.6, 1.10, 6.10).
- **Artifact conformance end to end**: build, then check, then assert zero violations — the exact sequence the release workflow runs — with the token match data supplied through the same mechanism the purge's guards use (`tests._forbidden_strings.require`, so the test skips distinguishably in an environment without it, while the checker it exercises would have failed closed) (5.4, 5.10, 6.2, 6.3).
- **Reproducibility**: the same revision built twice yields archives with identical member names and identical member digests (10.5).
- **Skill/CLI conformance**: every `fitdocs` command and option named in the skill body exists in the registered command surface, and every reported channel the body names — including move failures — matches the drain report's own field set; removing a command from the application, or renaming a channel, makes the test fail (8.8).
- **Documentation guarantees**: the entry point's links all resolve to existing files and cover install, configuration, **the inbox**, upgrading, wiki integration, the ownership contract, the plugin platform, compatibility, releasing, and contributing (7.9); the preserved statements are still published somewhere in the documentation set — data-root resolution order, the persistent tile opt-out, provider attribution, **the inbox never-delete guarantee**, **the "no watching and no scheduling" statement**, and **a pointer to the published ownership contract** (10.6); and the README still reaches every section its siblings publish, whether in place or by link (10.7). Shipped and emitted documentation references use the project-URL form rather than a repo-relative path (1.9).

### E2E Tests

- **Installed tool from the built artifact** (extends the existing packaging test): install into an isolated tool directory, assert the console script exists, `--version` matches the manifest, `--help` lists every released command, and **no data root, configuration file, or profile was created anywhere** during install (1.2, 1.7, 2.2).
- **Source-tree version**: running the CLI from an uninstalled checkout prints the unknown token and exits 0 (2.4).
- **Skill command**: the installed tool prints an existing skill path; copying that directory into a skills location yields a valid skill directory whose name matches its frontmatter (8.6).

### Regression / Preserved-Guarantee Tests

- The dependency list is unchanged from the pre-feature revision (10.1).
- The existing determinism and offline guards still pass, extended to assert that no new runtime network access was introduced (10.4).
- Golden documents remain byte-identical: nothing in this feature touches rendering (10.2).
- The public import surface test still passes unchanged, and the two new package modules are not added to it — they are internal (10.1, and the policy's documented-is-public rule).

## Security Considerations

- **No long-lived publishing credential exists.** Publication authenticates by short-lived OIDC exchange scoped to a single job; there is no API token in the repository, in a secret store, or on a maintainer's machine to leak (5.7). The public publish environment additionally requires manual approval.
- **The gate fails closed.** Every unknown is a violation: an undeclared metadata field, a member matching no allowlist, a link member, and — above all — match data that is not there (`GATE_NOT_RUN`). The match data cannot be weakened by a diff to this repository at all, because it does not live here (6.3, 6.9).
- **Third-party licensed material is treated as a security-grade boundary**, not a documentation footnote: it is enforced against the artifact, and the contribution documentation states the rule for future contributors (6.1, 9.5).
- **No new execution surface.** The release scripts run only in a maintainer's or the automation's context, import nothing from the package, and execute no artifact content. The package gains one command that prints a path and one function that reads metadata.
- **Personal data cannot reach an artifact structurally**, because the source distribution is an allowlist and the checker rejects any member matching the forbidden patterns — including `.fit`, `.gpx`, and data-root paths (10.3).
- **The skill instructs an agent but grants it nothing.** It declares no pre-approved tools, so an agent environment applies its own permission model unchanged.

## Migration Strategy

There is no user-facing data migration: no released version exists, so no installed base can be broken. The migration that matters is the project's own, and it is ordered so that each stage is independently verifiable.

```mermaid
flowchart LR
    S1[Stage 1 version leaf and manifest metadata] --> S2[Stage 2 artifact policy and checker]
    S2 --> S3[Stage 3 encumbered content gate bound to the release path]
    S3 --> S4[Stage 4 changelog compatibility policy and documentation]
    S4 --> S5[Stage 5 agent skill and its conformance]
    S5 --> S6[Stage 6 automation and a rehearsal release]
```

- **Rollback trigger**: any stage that changes generated-document bytes is a defect, not expected churn — this feature must not alter rendering at any point.
- **Validation checkpoint**: stage 3 — task 2.3 builds the gate, task 3.2 is the checkpoint that proves it against the real artifacts — is the gate that matters. Before it, the project can build artifacts it must not publish; after it, an unpublishable artifact is a failing check rather than a judgement call — including an artifact that was never scanned. No publication of any kind may be attempted before stage 3 passes.
- **First release**: the first published version is produced by a full rehearsal on the rehearsal index followed by the real procedure, from the working tree, with the `threshold` built-in bundled. *(Amendment 2: there is no profile to select and no permission state to consult.)*
