# Brief: plugin-api

## Problem

The product promise is "update the tool without overwriting your bespoke
logic" — user logic must live *outside* fitdocs, plugged into defined
extension points. The `LoadCalculator` Protocol seam exists and is clean
(`load/types.py`), but nothing can discover a third-party implementation:
the registry is a module-level dict populated by an import side-effect
(`load/__init__.py` registers the withdrawn calculator), there is no entry-point group in
`pyproject.toml`, and the CLI never imports user code. Today the only way
to add a calculator is to fork fitdocs — the exact failure mode the plugin
design exists to prevent.

## Current State

- `LoadCalculator` Protocol: `calculator_id`, `display_name`,
  `supported_modalities`, `required_athlete_fields()`, `compute()` →
  closed `LoadOutcome` union; calculators may decline a sport.
- Public `register()` exists but relies on being called at import time;
  discovery mechanism absent. Additive `athlete_field_hints` read via
  `getattr` is a soft convention.
- Packaging declares only the console script; no plugin entry-point group,
  no `py.typed` marker, no documented/versioned public API surface for
  plugin authors.

## Desired Outcome

- Third-party packages: `pip install fitdocs-mycalc` + an entry point in
  the `fitdocs.load_calculators` group → discovered automatically
  (`importlib.metadata.entry_points`), validated against the Protocol at
  registration, with per-plugin failure isolation (a broken plugin is
  reported by name, never crashes the run).
- Local unpackaged plugins: a config-referenced `.py` file (or plugins
  dir) under the user's vault config for bespoke logic that never becomes
  a package — datasette `--plugins-dir` / mkdocs `hooks:` pattern.
  Arbitrary-code-execution tradeoff documented; config is user-owned.
- `fitdocs plugins` lists discovered calculators: id, display name,
  version, origin (built-in / entry point / local file), load errors.
- A versioned, typed public API for plugin authors: `py.typed`, documented
  import surface (activity model, `LoadCalculator`, `LoadOutcome`,
  registration), and a stated compatibility policy tied to semver.

## Approach

Textbook Python plugin distribution (pytest/datasette/mkdocs lineage):
plain entry points + Protocol validation, no pluggy (overkill for a
one-object-per-plugin registry). Built-ins move onto the same discovery
path where practical so there is one registration story.

## Scope

- **In**: entry-point discovery; local plugin file/dir loading; validation
  + failure isolation; `fitdocs plugins` command; `py.typed` + public API
  docs + naming convention (`fitdocs-*`); plugin-author guide with a
  worked example.
- **Out**: pluggable renderers/templates/charts/frontmatter (future,
  gated on wiki-contract stabilizing); pluggy/hook lifecycles; a plugin
  marketplace; sandboxing of plugin code.

## Boundary Candidates

- Discovery/loading/validation (new module) vs. the existing registry and
  engine (consume it, unchanged semantics).
- Public API surface definition vs. internal modules (explicit split —
  what plugin authors may import).

## Out of Boundary

- Doc ownership/regions (wiki-contract); ingestion (inbox); release
  mechanics (distribution).
- Which methodologies ship built-in (the third party's licensing is an
  external gate, out of scope here).

## Upstream / Downstream

- **Upstream**: training-load (Protocol, registry, engine, profile
  store), fit-ingest model (the types plugins consume).
- **Downstream**: distribution (documents/ships the plugin story);
  community calculators; the pkm wiki invoking `fitdocs load`.

## Existing Spec Touchpoints

- **Extends**: training-load (registration/discovery layer over its
  interface; engine behavior unchanged).
- **Adjacent**: workout-docs load region rendering (unchanged; outcomes
  flow through the same `LoadOutcome` union).

## Constraints

- Protocol/`LoadOutcome` changes must be additive; existing withdrawn-
  calculator behavior and golden files unchanged.
- A missing/broken plugin must never alter exit-code semantics for
  otherwise-successful runs beyond the established failure channels.
- Keep dependency footprint zero-added (stdlib `importlib.metadata`).
