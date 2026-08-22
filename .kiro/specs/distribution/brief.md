# Brief: distribution

## Problem

fitdocs should be installable as a plugin for LLM-powered markdown wikis —
and updatable in place without touching user content or user logic. Today
the README says "no installable package yet": version 0.1.0, no release
process, no changelog/semver policy, no upgrade story, and no packaging of
the wiki-integration surface (how an agent-managed wiki like
joshua-stauffer/pkm adopts fitdocs as a first-class input path).

## Current State

- `pyproject.toml` is sound (hatchling, src-layout, MIT, console script);
  installable locally via `uv tool install .` but never published.
- Wiki-contract, inbox, and plugin-api specs (siblings) define the
  interfaces this spec packages and documents.
- The pkm repo integrates tools as skills + scripts over a shared
  data-root contract; fitdocs already mirrors that contract. Agent Skills
  (SKILL.md) is the current portable packaging for agent-workflow plugins.
- The withdrawn methodology's tables/name require the third party's
  sign-off before public redistribution (see the reference writeup,
  recorded in the purge's provenance record).

## Desired Outcome

- Published package (PyPI) with semver, changelog, and a stated
  compatibility policy covering: the doc/ownership contract, the inbox
  interface, and the plugin API. `uv tool install fitdocs` / `pipx` just
  work; upgrades never rewrite user-owned zones or require re-doing user
  config.
- Wiki-integration packaging: install/upgrade docs for standalone and
  pkm-style wikis; a SKILL.md so agent-managed wikis get a turnkey
  "process the fitdocs inbox" workflow; the emitted ownership declaration
  (from wiki-contract) referenced as the adoption contract.
- Release checklist/automation: build, test, tag, changelog, publish.

## Approach

Ship the three interface specs as one coherent, versioned product. Treat
the contracts (doc ownership, inbox, plugin API) as the public API that
semver governs — code churn behind them stays invisible to users.

## Scope

- **In**: PyPI packaging + release process; versioning/changelog policy;
  install/upgrade/uninstall docs (standalone + pkm-style wiki); SKILL.md
  packaging; compatibility statement; contribution docs for community
  calculators.
- **Out**: resolving the third party's licensing (external gate: sign-off or
  replacement happens outside this spec — but release is blocked until
  one of them lands); MCP server; Obsidian-specific plugin; marketing
  site; auto-update mechanisms.

## Boundary Candidates

- Package/release mechanics vs. integration documentation vs. SKILL.md
  authoring — separable workstreams within the spec.

## Out of Boundary

- The content of the contracts themselves (owned by wiki-contract, inbox,
  plugin-api).
- New product features.

## Upstream / Downstream

- **Upstream**: wiki-contract, inbox, plugin-api (must be approved/stable
  first); all Phase 1–2 specs.
- **Downstream**: end users, the pkm wiki, community calculator authors.

## Existing Spec Touchpoints

- **Extends**: none directly; packages the outputs of the Phase 3
  siblings.
- **Adjacent**: workout-docs (README/docs it wrote get reorganized into
  user-facing install docs).

## Constraints

- **Release gate**: no public artifact containing the withdrawn
  methodology's tables/name without sign-off, or with the calculator
  replaced. The plugin-api local escape hatch makes shipping without a
  bundled methodology viable.
- Personal data never in the repo or package; docs must keep the
  data-root loud-failure contract front and center.
- Keep the dependency footprint minimal — an installable tool for
  non-developers.
