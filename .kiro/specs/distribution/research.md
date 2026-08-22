# Research & Design Decisions: distribution

## Summary

- **Feature**: `distribution`
- **Discovery Scope**: Complex Integration — no new product behavior, but a new
  operational layer (build, release, policy, documentation, agent packaging)
  laid over a codebase whose three public contracts were just defined by the
  Phase 3 siblings.
- **Key Findings**:
  1. Far less is missing than the README implies. `fitdocs --version` already
     exists and already reads `importlib.metadata.version("fitdocs")`;
     `tests/test_packaging.py` already installs the project with
     `uv tool install` into an isolated `UV_TOOL_DIR` and asserts the console
     script works; `tests/load/test_packaging.py` already asserts the bundled
     calculator tables survive a `uv build` wheel. The gap is *policy,
     metadata, release mechanics, and documentation*, not plumbing.
  2. The encumbered material is already committed and already packaged. The two
     withdrawn-methodology CSVs live at `src/fitdocs/load/withdrawn/data/` and ship inside the wheel
     via `packages = ["src/fitdocs"]`; the extracted methodology *and* a second
     copy of both tables also live at `docs/reference/`, which today would ride
     into an sdist. The licensing gate therefore has to inspect **built
     artifacts**, and the sdist needs an explicit allowlist.
  3. Nothing exists for release: no `.github/`, no `LICENSE` file (despite
     `license = { text = "MIT" }`), no `CHANGELOG.md`, no `CONTRIBUTING.md`, no
     classifiers, no `[project.urls]`, no git tags, no `py.typed`
     (plugin-api adds that one).
  4. Agent Skills is a genuinely open, versionless standard with a strict
     `name`-must-equal-directory rule — which decides where the skill file
     lives and how it is validated.

## Research Log

### Existing packaging surface (codebase inventory)

- **Context**: Establish what the spec builds on versus creates.
- **Sources Consulted**: `pyproject.toml`, `README.md`, `.gitignore`,
  `src/fitdocs/cli.py`, `src/fitdocs/tiles.py`, `src/fitdocs/__init__.py`,
  `tests/test_packaging.py`, `tests/load/test_packaging.py`,
  `tests/load/test_install_smoke.py`, `docs/`.
- **Findings**:
  - `pyproject.toml`: hatchling, src-layout, `version = "0.1.0"` static,
    `license = { text = "MIT" }`, five runtime dependencies, one console
    script. No `authors`, `keywords`, `classifiers`, `[project.urls]`,
    `license-files`, sdist target config, or entry-point groups.
  - `cli.py` registers exactly three commands (`sync`, `regen`, `load`) plus an
    eager `--version` callback on `@app.callback()`; `importlib.metadata.version`
    is called at `cli.py:57,94` and `tiles.py:54,242` (tile user-agent) with **no
    `PackageNotFoundError` guard** — three call sites, no shared helper.
  - `src/fitdocs/__init__.py` exports 19 names lazily (PEP 562). No `py.typed`.
  - `tests/test_packaging.py` already performs an offline `uv tool install`
    into a temp `UV_TOOL_DIR` and compares `--version` output with the
    `pyproject.toml` value; `tests/load/test_packaging.py` already asserts the
    wheel carries both withdrawn-methodology CSVs with their licensing header.
  - `.gitignore` carries a deliberate re-include block for
    `src/fitdocs/load/withdrawn/data/*.csv` so the encumbered tables are committed
    and packaged, and gitignores the two source `.xlsx` workbooks.
  - `README.md` (133 lines) is stale: `## Status` reads "Early discovery / spec
    phase. No installable package yet."; there is no install, quickstart, or
    data-root section, but there *are* three route-maps behavior statements
    (what leaves the machine, the persistent tile opt-out, provider
    attribution) that any reorganization must preserve.
  - `docs/` holds `contributing-calculators.md` (training-load owns it),
    `reference/fitdocs-ai-reference.md`, the reference writeup, and
    the extracted tables (a second copy of the encumbered tables).
- **Implications**: version work is a *consolidation plus fallback*, not a
  rebuild; artifact-content control is the real packaging work; the licensing
  gate must cover `docs/reference/` as well as the package data.

### PyPI publication mechanics

- **Context**: Requirement 5 demands short-lived credentials, a rehearsal path,
  and tag-triggered automation.
- **Sources Consulted**:
  packaging.python.org "Publishing package distribution releases using GitHub
  Actions"; `pypa/gh-action-pypi-publish` README and v1.11.0 release notes;
  blog.pypi.org 2025 year in review; docs.pypi.org attestations security model.
- **Findings**:
  - Trusted Publishing (OIDC) remains the recommended path; API tokens are the
    fallback, not the default. `pypa/gh-action-pypi-publish` is still the
    blessed action; latest confirmed release v1.14.1 (2026-07-19). Pin to a tag
    or SHA rather than a branch.
  - The publishing job needs `permissions: id-token: write` scoped to that job
    only. PyPA recommends a GitHub `pypi` environment with manual approval and a
    separate `testpypi` environment without.
  - PEP 740 attestations are **on by default since action v1.11.0** for Trusted
    Publishing; nothing to configure. No source confirms PyPI *requires* them.
  - TestPyPI is a separate registry with its own account and its own pending
    publisher; it is the standard rehearsal target.
  - Known limitation: Trusted Publishing does not work from a GitHub *reusable*
    workflow. Keep the publish job inline.
- **Implications**: two workflows (CI on push/PR, release on tag), a TestPyPI
  job that always runs before the PyPI job, an approval-gated `pypi`
  environment, no secrets in the repository.

### Version single-sourcing

- **Context**: Requirement 2 wants one declaration and consistent reporting.
- **Sources Consulted**: packaging.python.org "Single-sourcing the version";
  hatch dynamic-metadata docs; `ofek/hatch-vcs`;
  `maresb/hatch-vcs-footgun-example`; `importlib.metadata` docs.
- **Findings**:
  - Three sanctioned strategies (VCS-derived, static in `pyproject.toml`,
    static in source read by the backend). PyPA blesses none; it does recommend
    a test asserting the runtime-reported version equals the distribution
    metadata version.
  - `importlib.metadata.version()` raises `PackageNotFoundError` from an
    uninstalled source tree, and its metadata read is slow enough that it should
    stay out of import time.
  - `hatch-vcs` freezes the version at install time under editable installs — a
    documented footgun with a whole repository devoted to working around it.
- **Implications**: keep the static `pyproject.toml` version; add one leaf
  helper with a `PackageNotFoundError` fallback; route all three existing call
  sites through it; assert equality across pyproject, changelog, tag, and the
  installed tool.

### Compatibility policy precedent

- **Context**: Requirement 3 needs a policy that is specific, not boilerplate.
- **Sources Consulted**: semver.org; pytest backwards-compatibility and
  deprecation pages; Datasette plugin-hook and internals docs; the MkDocs 2.0
  public-API discussion.
- **Findings**:
  - SemVer clause 1 requires a declared public API, which "could be declared in
    the code itself or exist strictly in documentation" — exactly the
    three-contracts framing this spec needs. Clause 4 makes 0.y.z explicitly
    unstable; the widespread convention is to treat `0.MINOR` as the
    breaking axis.
  - pytest is the strongest model: changes classified trivial / transitional /
    true breakage, removals only in major releases, and deprecated behavior kept
    for at least two minor releases, signalled by a named warning class.
  - Datasette carries no global policy but establishes the useful rule
    *documented means public, undocumented means internal*.
  - MkDocs is the cautionary case: with no declared boundary, every symbol
    became de-facto plugin surface.
- **Implications**: state the boundary as "the three contracts plus the
  documented import surface"; adopt pytest's two-minor-release deprecation
  window; adopt Datasette's documented-is-public rule verbatim in spirit.

### Changelog conventions

- **Context**: Requirement 4.
- **Sources Consulted**: keepachangelog.com (current spec 1.1.2, 2024-09-27);
  scriv and towncrier documentation; commentary on generated changelogs.
- **Findings**: six canonical sections (Added, Changed, Deprecated, Removed,
  Fixed, Security), `## [X.Y.Z] - YYYY-MM-DD`, newest first, standing
  `## [Unreleased]`. Fragment tools (towncrier, scriv) exist to avoid merge
  conflicts on a shared file, and pay off only with several concurrent
  contributors. Hand-written Keep a Changelog is what small tools converge on;
  commit-derived changelogs are widely judged low-value for users.
- **Implications**: hand-written `CHANGELOG.md` in Keep a Changelog 1.1.2
  format, no fragment tooling, machine-checked only for the release-version
  match.

### Agent Skills packaging

- **Context**: Requirement 8 — what "publish an agent skill" concretely means.
- **Sources Consulted**: agentskills.io specification and site;
  platform.claude.com Agent Skills overview; code.claude.com skills and
  plugin-marketplaces docs; github.com/anthropics/skills.
- **Findings**:
  - A skill is a directory containing `SKILL.md` with YAML frontmatter.
    Spec-required fields: `name` (1–64 chars, lowercase alphanumeric and
    hyphens, **must equal the parent directory name**) and `description`
    (1–1024 chars, must say both what it does and when to use it). Optional:
    `license`, `compatibility` (≤500 chars), `metadata` (string→string map —
    where a version belongs, since there is no top-level `version` field), and
    the still-experimental `allowed-tools`.
  - Conventional layout is `SKILL.md` plus optional `scripts/`, `references/`,
    `assets/`, with progressive disclosure: frontmatter always loaded, body on
    trigger, bundled files only when read. Recommended body under ~500 lines.
  - Install locations are client concerns: `~/.claude/skills/<name>/`,
    `.claude/skills/<name>/`, plugin marketplaces, zip upload, or an API
    endpoint. **The published spec defines no install directory at all.**
    Claude Code follows symlinks.
  - The standard is open (agentskills.io, separate repo, CC-BY/Apache), adopted
    by many non-Anthropic clients, and **versionless** — no tagged releases.
  - No official convention exists for shipping a skill on PyPI, and the
    spec documents no relationship to `AGENTS.md`.
- **Implications**: the skill is an ordinary directory of package data with a
  strictly validated frontmatter contract; distribution is by documented copy
  from a path the tool can print; plugin-marketplace packaging is deliberately
  deferred because the plugin-root-to-skills mapping could not be verified.

### Install / upgrade / uninstall behavior

- **Context**: Requirement 7.
- **Sources Consulted**: docs.astral.sh uv tools guide, tools concepts, storage
  reference; pipx documentation and manpages.
- **Findings**: `uv tool install|upgrade|uninstall fitdocs`, `uvx fitdocs` for
  an ephemeral run; tool environments under `~/.local/share/uv/tools` with
  binaries in `~/.local/bin`, overridable via `UV_TOOL_DIR` / `UV_TOOL_BIN_DIR`.
  `pipx install|upgrade|reinstall|uninstall`, `PIPX_HOME` default
  `~/.local/share/pipx`. Both remove only the managed environment and its
  shims; neither touches anything the tool wrote elsewhere. uv's docs do not
  state this explicitly — it is inferred from the same venv-deletion model.
- **Implications**: the uninstall section can promise that the data root
  survives, and should state it as a property of *where fitdocs writes* rather
  than as a claim about the installers' behavior.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Verdict |
|--------|-------------|-----------|---------------------|---------|
| Declarative-only packaging | Put everything in `pyproject.toml` and a workflow; no project-owned scripts | Least code; nothing to maintain | Cannot express the licensing gate, which must reason over built artifacts; makes the gate unreviewable and untestable | Rejected |
| Gate as a workflow step | Inline shell in the release workflow | No new files | Untestable locally, invisible to the test suite, easy to bypass by hand-publishing | Rejected |
| **Artifact-conformance checker + build driver as project scripts, called by both the workflow and the test suite** | Two small stdlib scripts plus one recorded permission file | The gate is code, therefore testable, reviewable, and identical by hand and in CI (5.10) | Two more files to maintain | **Selected** |
| Separate `fitdocs-withdrawn` distribution | Move the methodology to its own package | Cleanly unencumbers the main package | Relocates rather than resolves the licensing question, and plugin-api Req 7.4 fixes the built-in registration for now | Rejected for this spec; noted as the natural follow-up if permission is refused |
| `hatch-vcs` tag-derived version | Git tag is the version | No manual bump | Editable-install staleness footgun; the release already tags deliberately | Rejected |
| towncrier / scriv changelog fragments | One file per change | No merge conflicts | Tooling and a new dev dependency for a single-maintainer project | Rejected |

## Design Decisions

### Decision: the licensing gate reads built artifacts, not the source tree

- **Context**: Requirement 6. The encumbered material exists in two places
  (`src/fitdocs/load/withdrawn/data/`, `docs/reference/`) and reaches artifacts by
  two different mechanisms (wheel package data, sdist default inclusion).
- **Alternatives Considered**: (1) grep the source tree before building;
  (2) rely on `.gitignore` and reviewer discipline; (3) inspect the built
  archives.
- **Selected Approach**: a conformance checker that opens `dist/*.whl` and
  `dist/*.tar.gz`, enumerates their members, and evaluates them against a
  required-set, a forbidden-set, and a forbidden-content marker list, cross-
  referenced with the recorded permission state.
- **Rationale**: only the artifact is published, so only the artifact is
  evidence. A source-tree check cannot see what hatchling's defaults added.
- **Trade-offs**: the check runs after a build rather than before, so a failing
  release wastes a build; that cost is trivial next to the risk it removes.
- **Follow-up**: the marker list must include the markers, redacted here
  ("the withdrawn methodology", "the third party's Performance Level", "HPL")
  and the two CSV filenames. The `--calculator` help text no longer carries a
  methodology example at all, so that half of this follow-up is discharged by
  removal rather than by substitution.

### Decision: an unencumbered build is a supported, tested profile

- **Context**: Requirement 6.4 and the brief's observation that the plugin API
  makes shipping without a bundled methodology viable.
- **Alternatives Considered**: (1) never build without the methodology and
  simply block release; (2) conditional hatchling excludes; (3) build from a
  pruned copy of the tree.
- **Selected Approach**: the build driver selects a profile from the recorded
  permission state. The unencumbered profile builds from a temporary pruned
  copy of the tree with the methodology package and the encumbered reference
  material removed; the built-in registration is guarded so the absence is
  tolerated rather than fatal.
- **Rationale**: hatchling has no first-class conditional-exclude mechanism, and
  a build hook would be more machinery than a twenty-line prune. Pruning a copy
  keeps the working tree untouched and makes the profile trivially testable.
- **Trade-offs**: the pruned build is not byte-identical to a normal build by
  construction — that is the point, and each profile is independently
  reproducible.
- **Follow-up**: an end-to-end test must install the unencumbered wheel and
  assert the tool runs, reports no available calculator, and keeps its exit-code
  contract.

### Decision: one version helper, three existing call sites converge on it

- **Context**: Requirements 2.1–2.4. Three modules call
  `importlib.metadata.version("fitdocs")` today, none guarded.
- **Selected Approach**: a pure leaf exposing the resolved version or `None`,
  plus a display form. The CLI, the tile user-agent, and the plugin listing's
  built-in version all read it.
- **Rationale**: matches the project's existing "absent data is `None`, never a
  fabricated value" rule and the wiki-contract precedent of collapsing
  duplicated readers into one leaf.
- **Trade-offs**: the tile user-agent must tolerate an unknown version; it
  degrades to a stable placeholder rather than omitting identification.
- **Follow-up**: keep the lookup out of import time — it is measurably slow.

### Decision: the agent skill is package data, distributed by documented copy

- **Context**: Requirement 8, against a standard that defines no install
  location and a client landscape with several.
- **Alternatives Considered**: (1) repo-only skill; (2) plugin-marketplace
  packaging; (3) package data plus a path-printing command.
- **Selected Approach**: canonical skill directory inside the package so it
  ships with every install and is version-locked to the release; one read-only
  command prints its installed location; the documentation gives the copy and
  symlink recipes for the common clients.
- **Rationale**: a repo-only skill is unreachable for a user who installed from
  the index; marketplace packaging could not be verified from the sources and
  would bind the spec to one client.
- **Trade-offs**: users copy rather than subscribe, so a skill refresh is a
  documented upgrade step rather than automatic.
- **Follow-up**: a test must parse the frontmatter against the published field
  constraints and assert every `fitdocs` command and option the body names
  exists in the CLI's registered surface.

### Decision: explicit sdist allowlist rather than exclusion patterns

- **Context**: Requirements 1.6 and 5.4. Hatchling's sdist default would ship
  `docs/reference/`, `tests/`, `.kiro/`, and `uv.lock`.
- **Selected Approach**: declare exactly what the sdist contains.
- **Rationale**: an allowlist fails closed. A new encumbered or private file
  added later is excluded by default instead of silently shipped.
- **Trade-offs**: the sdist cannot rebuild the test suite; that is acceptable
  for an application distribution and is stated in the contribution
  documentation.

## Risks & Mitigations

- **The gate is bypassed by publishing from a laptop** — the same checker runs
  in the test suite and is the documented manual step, and the PyPI environment
  requires manual approval, so a hand-publish still crosses a recorded gate.
- **Marker list drifts from reality** (a new encumbered file is added under a
  name the checker does not know) — the required/forbidden sets are an
  allowlist over artifact members, so an unexpected member fails the check
  regardless of its name.
- **Documentation reorganization silently drops a published guarantee** — a
  test asserts the specific route-maps and data-root statements survive.
- **The skill's commands drift from the CLI** as siblings add `check`,
  `plugins`, and the no-argument drain — the skill/CLI conformance test fails
  the moment a named command disappears.
- **A published version number cannot be corrected** — the release procedure
  makes tagging the last step before publication and the post-publication check
  the last step overall, and the changelog match is a gate, so the number is
  verified three times before it is spent.

## References

- [Publishing package distribution releases using GitHub Actions](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/) — the Trusted Publishing workflow this design follows.
- [pypa/gh-action-pypi-publish](https://github.com/pypa/gh-action-pypi-publish) — publishing action; attestations default-on since v1.11.0.
- [PyPI attestations security model](https://docs.pypi.org/attestations/security-model/) — PEP 740 behavior.
- [Single-sourcing the package version](https://packaging.python.org/en/latest/discussions/single-source-version/) — version strategies and the equality-test recommendation.
- [hatch-vcs footgun example](https://github.com/maresb/hatch-vcs-footgun-example) — why the version stays static.
- [Semantic Versioning 2.0.0](https://semver.org/) — declared-public-API requirement and 0.y.z semantics.
- [pytest backwards compatibility policy](https://docs.pytest.org/en/stable/backwards-compatibility.html) — the deprecation-window model adopted here.
- [Datasette plugin hooks](https://docs.datasette.io/en/stable/plugin_hooks.html) — documented-is-public convention.
- [Keep a Changelog 1.1.2](https://keepachangelog.com/en/1.1.0/) — changelog format and sections.
- [Agent Skills specification](https://agentskills.io/specification) — frontmatter fields and constraints.
- [Claude Code skills documentation](https://code.claude.com/docs/en/skills) — install locations and symlink behavior.
- [uv tools guide](https://docs.astral.sh/uv/guides/tools/) and [pipx](https://pipx.pypa.io/stable/) — install, upgrade, uninstall commands and storage locations.
