# Research & Design Decisions: plugin-api

## Summary

- **Feature**: `plugin-api`
- **Discovery Scope**: Extension (light discovery — an existing, clean seam gains a
  discovery layer; no new architecture, no new dependency)
- **Key Findings**:
  - The `LoadCalculator` seam already carries everything a plugin needs
    (`calculator_id`, `display_name`, `supported_modalities`,
    `required_athlete_fields()`, `compute()` → closed `LoadOutcome`), and the
    engine reads the additive `athlete_field_hints` seam via `getattr`. No
    contract change is required for third-party calculators — only discovery.
  - `importlib.metadata.entry_points(group=...)` on the project's floor (3.11)
    returns an empty list for an unknown group and exposes `EntryPoint.dist`
    with `.name` / `.version` (verified in this checkout: 3.11.15). That covers
    the whole `fitdocs plugins` listing (id, display name, version, origin)
    with zero added dependencies.
  - Plugin failures can be isolated entirely inside the CLI: discovery returns a
    report the CLI prints through the same additive warning treatment
    route-maps established, so `sync.py` and `load/engine.py` need no change and
    exit-code semantics are untouched.

## Research Log

### Existing extension seam and registration path

- **Context**: Determine how much of the plugin story already exists and what
  must change.
- **Sources Consulted**: `src/fitdocs/load/types.py`,
  `src/fitdocs/load/registry.py`, `src/fitdocs/load/__init__.py`,
  `src/fitdocs/load/engine.py`, `docs/contributing-calculators.md`,
  `pyproject.toml`.
- **Findings**:
  - `registry._REGISTRY` is a module-level `dict[str, LoadCalculator]` whose
    insertion order *is* registration order; `register()` raises `ValueError` on
    a duplicate id and performs no other validation.
  - `fitdocs.load.__init__` registers `WithdrawnCalculator()` as an import side
    effect. Any code path that imports the load layer therefore has the built-in
    registered before anything else can register.
  - `engine.apply_load` validates a forced `--calculator` id with
    `registry.get()` (message lists registered ids) and otherwise selects
    `registry.for_modality(...)` in registration order, using the first
    calculator that does not decline.
  - `pyproject.toml` declares only `[project.scripts] fitdocs`; there is no
    entry-point group, no `py.typed`, and `[tool.hatch.build.targets.wheel]
    packages = ["src/fitdocs"]` (so a `py.typed` marker ships automatically once
    the file exists).
- **Implications**: The feature is purely additive: a new discovery module, a
  validation gate inside `register()`, one new CLI command, and CLI wiring.
  Registration order semantics give the ordering guarantee (1.3) for free as
  long as discovery runs after the built-ins and in a sorted order.

### `importlib.metadata` behavior on Python 3.11

- **Context**: Confirm the stdlib API supports keyless discovery, per-plugin
  isolation, and the metadata the listing command must print, without a
  compatibility shim.
- **Sources Consulted**: live check in this checkout
  (`uv run python -c "import importlib.metadata ..."`, Python 3.11.15); stdlib
  documentation for `importlib.metadata`.
- **Findings**:
  - `entry_points(group="fitdocs.load_calculators")` returns an empty
    `EntryPoints` when nothing advertises the group — no error, no cost.
  - Each `EntryPoint` exposes `.name`, `.value`, and `.dist`; `.dist.name` and
    `.dist.version` give the origin distribution and its version. `.dist` is
    typed optional, so the listing must tolerate `None` (report the version as
    unknown rather than fabricate one — Req 4.3, and the project's
    absent-data-is-`None` rule).
  - `EntryPoint.load()` imports the target module; only distributions that
    advertise the group are imported (Req 1.9).
  - Iteration order across distributions is not contractually stable, so an
    explicit sort is required for Req 1.3.
- **Implications**: Selected group name `fitdocs.load_calculators`; sort key
  `(entry_point.name, distribution name, entry_point.value)`; wrap each
  `.load()` in its own `try/except Exception`.

### Ecosystem precedent for local (unpackaged) plugins

- **Context**: The brief calls for a config-referenced local plugin file/dir; we
  need a precedent-backed shape and an honest statement of the trade-off.
- **Sources Consulted**: datasette `--plugins-dir`, mkdocs `hooks:`, pytest
  `conftest.py` (all cited in the Phase 3 discovery that produced the brief).
- **Findings**: The converged pattern is: a user-owned configuration value names
  a file or directory; the tool executes those modules as ordinary Python at
  startup; the tool documents that this is arbitrary code execution and applies
  no sandbox. datasette additionally puts the directory on `sys.path`; mkdocs
  does not.
- **Implications**: Adopt the config-referenced path (no implicit default
  location — Req 2.5), load top-level `*.py` in sorted order, skip
  `_`-prefixed files, and do **not** mutate `sys.path` (each local plugin file
  must be self-contained). Document the execution trade-off (Req 2.8).

### Where plugin failures surface

- **Context**: Requirement 3.5 forbids any exit-code change from a plugin load
  failure, and route-maps already added a warn-and-continue channel.
- **Sources Consulted**: `src/fitdocs/cli.py` (`_report`, `_finish`, exit-code
  docstring), `src/fitdocs/sync.py` (`SyncReport.warnings`),
  `src/fitdocs/load/engine.py` (`LoadReport`).
- **Findings**: `SyncReport.warnings` is per-document (map omissions) and
  `LoadReport` has no warning channel. Plugin load errors are per-run, not
  per-document, and are known before either engine is called.
- **Implications**: Do not extend `SyncReport`/`LoadReport`. The CLI holds the
  `PluginReport` returned by discovery and prints its errors at the end of the
  run, next to the existing summaries. `sync.py` and `load/engine.py` stay
  untouched — the smallest possible blast radius for a spec whose hard
  constraint is "existing behavior and golden files unchanged".

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Plain entry points + Protocol validation (**selected**) | stdlib `importlib.metadata` discovery of one calculator object per entry point, validated before registration | Zero added dependencies; textbook pytest/datasette lineage; one-object registry needs nothing more | Author must publish a distribution (mitigated by the local-file channel) | Matches the brief and the roadmap's rejection of pluggy |
| pluggy hook specs | Adopt pytest's hook framework | Multi-hook lifecycles, hook ordering, first-result semantics | A runtime dependency and a whole conceptual layer for a registry that holds one object per plugin | Rejected in discovery and re-rejected here |
| Config-declared import paths only (`calculators = ["pkg.mod:Cls"]`) | User lists dotted paths in config | Trivial to implement | Every plugin needs configuration; defeats "pip install and it works" (Req 1.1) | Rejected; the local-file channel already covers unpackaged logic |
| Namespace-package scanning (`fitdocs_plugins.*`) | Import everything under a namespace package | No metadata needed | Imports by guesswork, no distribution/version metadata, no way to advertise intent | Rejected |

## Design Decisions

### Decision: Entry points resolve to a calculator object, local files self-register

- **Context**: Two channels must produce registrations; one registration policy
  (validation + duplicate-id rejection) must govern both (Req 3.1, 3.3).
- **Alternatives Considered**:
  1. Both channels self-register by calling `fitdocs.load.register()`.
  2. Both channels expose a module attribute fitdocs reads.
  3. Entry point resolves to a calculator object; local files self-register.
- **Selected Approach**: (3). An entry point's value resolves to a class
  (instantiated with no arguments), a non-calculator callable (called with no
  arguments), or an instance (used directly); fitdocs then validates and
  registers it. A local plugin file is executed and calls the already-documented
  `fitdocs.load.register()` itself; fitdocs attributes the ids that appeared by
  diffing the registry around the import.
- **Rationale**: The entry-point channel gets the declarative, inspectable form
  (`mycalc = "fitdocs_mycalc:MyCalculator"`) that the listing command and the
  worked example need; the local channel keeps working exactly as
  `docs/contributing-calculators.md` already teaches. Validation is enforced in
  one place either way, because it moves *into* `registry.register()`.
- **Trade-offs**: Two shapes to document instead of one; in exchange neither
  channel is awkward and no existing documentation becomes wrong.
- **Follow-up**: The author guide must show both shapes side by side (Req 6.2).

### Decision: Validation lives in `registry.register()`

- **Context**: Req 3.1 requires rejection with a precise reason; the brief calls
  for "Protocol validation at registration".
- **Alternatives Considered**: validate in the discovery module only;
  `@runtime_checkable` + `isinstance`; a hand-written validator in the registry.
- **Selected Approach**: A hand-written `validate_calculator()` in
  `registry.py`, called by `register()`, raising `InvalidCalculatorError`
  (a `ValueError` subclass, so existing `ValueError` expectations still hold).
  The duplicate-id path raises `DuplicateCalculatorIdError`, also a `ValueError`
  subclass with the current message.
- **Rationale**: `@runtime_checkable` only checks member *presence*, never types,
  and cannot say "`supported_modalities` is a list of strings, not a frozenset of
  Modality" — the message quality Req 3.1 demands. Putting the gate in
  `register()` means self-registering local plugins are validated too, and the
  built-in registration is validated by the same code on every startup.
- **Trade-offs**: A malformed built-in would now fail loudly at import — which is
  the desired behavior and is covered by existing tests.
- **Follow-up**: Validation must not call `required_athlete_fields()` or
  `compute()` (no side effects at registration time).

### Decision: Discovery state and origin metadata live in `plugins.py`, not the registry

- **Context**: The listing command needs origin/version per calculator; the
  registry stores calculators only.
- **Selected Approach**: `plugins.py` owns a module-level origin map plus the
  cached `PluginReport`. It snapshots the ids present before loading anything
  (those are the built-ins) and attributes each subsequently-appearing id to the
  entry point or file that produced it.
- **Rationale**: Keeps the registry a pure id→calculator store (training-load's
  boundary) and keeps plugin concepts in the plugin module.
- **Trade-offs**: Discovery must run at most once per process; a `reset()`
  (backed by an additive `registry.unregister()`) supports the test suite.
- **Follow-up**: `reset()` must never unregister a built-in.

### Decision: `[plugins]` table in the existing user-owned `fitdocs.toml`

- **Context**: Req 1.8 (disable switch) and Req 2.1 (local plugin path) need
  user-owned configuration under the data root.
- **Selected Approach**: A `[plugins]` table in `<data-root>/fitdocs.toml`, read
  by a `load_plugin_settings()` that mirrors `load_tile_settings()` exactly:
  absent file/table → defaults, malformed value → a loud settings error the CLI
  maps to exit 2 before anything is written.
- **Rationale**: The file already exists, is documented as user-owned and
  read-only to fitdocs, and explicitly anticipates further tables. One
  configuration file, one failure treatment.
- **Trade-offs**: A second independent reader of the same file (a few hundred
  microseconds). The settings *filename* is centralized in `layout.py` so it has
  one definition; consolidating the two readers is deferred.

### Decision: Plugin errors are a CLI-level warning channel

- **Context**: Req 3.5/3.6 — reported by name, never exit-code-affecting.
- **Selected Approach**: The CLI prints a "Plugin load errors" block at the end
  of the run from the `PluginReport` it already holds; `_finish()` is unchanged.
- **Rationale**: Plugin failures are per-run and known before the engines run,
  so threading them through per-document reports would be an invented coupling.
- **Trade-offs**: Plugin errors are not part of `SyncReport`, so a future
  machine-readable run summary would need to merge two sources.

## Risks & Mitigations

- **A third-party plugin installed in a developer's environment perturbs the
  test suite** — discovery happens only inside CLI commands, tests run against
  temporary data roots, and `plugins.reset()` clears state between tests; the
  golden/determinism suites additionally assert output with no plugins present.
- **A plugin that shadows a built-in id silently changes results** — duplicate
  ids are rejected in favor of the incumbent and reported by name (Req 3.3), and
  `fitdocs plugins` shows the conflict.
- **Arbitrary code execution via the local plugin path** — the setting is
  opt-in with no implicit default, the path is user-owned configuration, and the
  documentation states plainly that fitdocs applies no sandboxing (Req 2.8).
- **Entry-point discovery slows startup** — only distributions advertising the
  group are imported (Req 1.9); with no plugins installed the cost is one
  metadata scan.
- **`EntryPoint.dist` is `None` in an exotic installation** — the listing reports
  the version as unknown instead of fabricating one.

## References

- Python stdlib `importlib.metadata` — entry-point discovery API used verbatim
  (`entry_points(group=...)`, `EntryPoint.load()`, `EntryPoint.dist`).
- PEP 561 — the `py.typed` marker that makes a package's inline annotations
  visible to a plugin author's type checker (Req 5.1).
- datasette `--plugins-dir`, mkdocs `hooks:`, pytest `conftest.py` — precedent
  for executing user-owned local plugin modules named by configuration.
- `docs/contributing-calculators.md` — the existing author guide this feature
  extends rather than replaces.
- `.kiro/specs/route-maps/design.md` — the warn-and-continue channel and the
  `fitdocs.toml` settings-reader pattern this design mirrors.
