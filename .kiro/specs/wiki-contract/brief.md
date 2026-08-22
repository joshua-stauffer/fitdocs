# Brief: wiki-contract

## Problem

fitdocs is about to be installed into wikis it does not control and updated
independently of the user's content. Today the ownership contract is implicit
in code: the region-marker grammar lives in `docmerge.py`, the frontmatter
schema and `uuid`/`sources` identity are re-parsed in at least three places
(`sync.py`, `load/engine.py`, read paths), `doc_version` is a bare int with
no migration story, and nothing in the generated tree tells a human — or an
LLM agent maintaining the wiki — which files fitdocs owns and which zones
belong to the author. In an LLM-managed wiki that last gap is acute: agents
will happily "improve" generated docs unless the boundary is declared where
they read it.

## Current State

- Sole-writer mechanics largely exist: fitdocs writes only under
  `workouts/`, `workouts/assets/`, `fit-archive/`, `.cache/` (`layout.py`);
  regeneration merges via `<!-- fitdocs:begin:<id> -->` regions and raises
  `RegionError` rather than silently overwriting damaged markers; writes are
  atomic; the archive is the processed-state marker.
- User-owned zones exist: `notes` region on every doc, `workout` region on
  strength docs, `load` managed separately. Region ids and placeholders are
  hardcoded in `views.py`; `PRESERVED_REGIONS` in `docmerge.py`.
- No provenance header, no emitted ownership declaration (AGENTS.md/
  CLAUDE.md) in the owned tree, no `linguist-generated` guidance, no
  documented contract a wiki (or its agent) can rely on.
- User frontmatter keys outside managed lines survive merge by accident,
  not by contract.

## Desired Outcome

- One **document-contract module** is the single source of truth for
  frontmatter schema, doc identity (`uuid`/`sources`), and region policy;
  `sync`, `load`, and future consumers import it.
- A written, versioned **ownership contract**: which paths fitdocs owns,
  which regions are user-owned, what regeneration preserves, what
  `--force`/destructive regenerate does. Published in docs and emitted into
  the owned tree as an AGENTS.md-style declaration LLM agents will read.
- Generated docs carry provenance (generated-by line / frontmatter stamp);
  guidance for `.gitattributes` `linguist-generated` where the wiki is a
  git repo.
- `doc_version` has a defined migration path: docs are re-derivable from
  `fit-archive/`, so migration = regenerate; the contract states this and
  the tool detects/reports version drift.
- Explicit statement of what is guaranteed for user-added frontmatter keys.

## Approach

Formalize, don't re-architect: extract the duplicated schema/identity
parsing into one module, declare the existing region mechanism as the
public contract (obsidian-zotero-integration "persist" pattern, projen
"tool owns files, intent lives elsewhere" philosophy, inverted per-file),
and add the declaration surface (emitted AGENTS.md + provenance stamps)
that makes the boundary legible to humans and agents.

## Scope

- **In**: document-contract module + refactor of `sync.py`/`load/engine.py`
  to use it; ownership contract doc; emitted per-directory ownership
  declaration; provenance stamping; doc_version drift detection +
  regenerate-as-migration; contract for user frontmatter keys; labeled
  destructive-regenerate semantics.
- **Out**: user-configurable region sets or templates (policy stays fixed
  this pass; the mechanism already generalizes); MCP server surface;
  enforcement beyond declaration (no file permissions games); inbox and
  plugin discovery (sibling specs).

## Boundary Candidates

- Contract module (pure, no I/O) vs. its consumers (sync/load engines).
- Declaration artifacts (emitted files, docs) vs. merge mechanics
  (unchanged `docmerge.py`).

## Out of Boundary

- Which load calculators exist and how they register (plugin-api).
- How files arrive (inbox).
- Release packaging (distribution).

## Upstream / Downstream

- **Upstream**: workout-docs (doc structure, regions), fit-ingest
  (identity inputs), training-load (load region semantics).
- **Downstream**: distribution (publishes the contract), inbox and
  plugin-api (write within it), any future renderer customization.

## Existing Spec Touchpoints

- **Extends**: workout-docs Req 10 (user-content preservation) — elevates
  it from behavior to published contract.
- **Adjacent**: training-load (docedit/frontmatter load keys must move to
  the shared module without behavior change).

## Constraints

- No behavior change to merge semantics or existing docs' bytes on regen
  (byte-identical regen must keep holding for unchanged inputs).
- Output stays plain markdown; declarations must degrade gracefully in
  vanilla renderers.
- Data-root contract unchanged.
