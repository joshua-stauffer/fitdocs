# Implementation Plan

> Sequencing precondition: this plan builds on the implemented training-load and
> workout-docs specs — the `LoadCalculator` contract, the id-addressable
> registry with its import-time built-in registration, the load engine and its
> per-document failure isolation, the data-root contract, the user-owned
> settings file under the data root, and the CLI shell with its three-tier exit
> codes must be in place before these tasks start. It also builds on the
> pre-wave **settings-foundation** item, which supplies `layout.SETTINGS_FILE`,
> `layout.settings_path(data_root)`, and the shared one-time read/parse of
> `<data-root>/fitdocs.toml` raising a single `SettingsError` for file-level
> problems, with the `[tiles]` reader already redirected onto it. No task in
> this plan edits `layout.py`, `settings.py`, or `tiles.py`; no task in this
> plan may change the calculator contract, the engine, the sync pipeline, or
> any generated document content.

- [ ] 1. Foundation: registration gate, shipped typing

  _Task 1.1 was withdrawn: it gave the settings file one definition in the
  data-root layout and redirected the tile reader onto it. That work moved to
  the pre-wave **settings-foundation** item, which lands before this plan.
  Later numbers are left unchanged so existing `_Depends:_` references stay
  valid._

- [x] 1.2 (P) Add the contract-validation gate to calculator registration
  - A pure validator that accepts any object and returns either "valid" or a
    human-readable reason naming the first violated member: a non-empty string
    id, a non-empty string display name, a non-empty collection of real modality
    members, and callable field-declaration and compute members; it never calls
    the declared methods, so registration stays side-effect free
  - Registration runs the validator first and raises a typed invalid-calculator
    error; the duplicate-id path raises a typed duplicate-id error naming the id
    and keeps the incumbent registration untouched. Both error types subclass
    the error the current registration already raises, so existing callers and
    tests keep working
  - An unregister operation that removes an id when present and is a no-op
    otherwise, for discovery-state teardown
  - Both new error types join the load layer's re-exported names and its declared
    public list, because the design's public-surface definition includes them for
    plugin authors
  - Observable: unit tests reject each malformed-calculator shape with a reason
    that names the offending member, accept the shipped calculator unchanged,
    confirm a duplicate registration leaves the original object in place, and
    confirm both error types import from the load layer's public surface
  - _Requirements: 3.1, 3.3, 5.6_
  - _Boundary: RegistryValidation, PublicApi_
- [x] 1.3 (P) Ship type information to plugin authors
  - The package carries an inline-typing marker so a third-party plugin's strict
    type checker resolves fitdocs types without stubs or suppressions; the
    existing wheel target already includes package files, so no packaging
    configuration changes
  - The existing install smoke suite is the single owner of this assertion: it
    checks the marker is present in a real installed package, not only in the
    source tree
  - Observable: the install smoke suite fails if the marker is ever dropped from
    the built and installed package
  - _Requirements: 5.1_
  - _Boundary: Packaging_

- [ ] 2. Plugin configuration and discovery
- [x] 2.1 Implement the plugin settings reader
  - A typed *per-table* reader over the mapping settings-foundation's shared
    reader has already parsed — this task performs no file read and no TOML
    parse of its own, and never composes the settings path from a bare
    filename constant. File-level problems (unreadable file, invalid TOML) are
    already reported once by the shared reader's single error; this reader
    speaks only for the plugins table
  - An absent file or table yields the documented defaults (discovery enabled,
    no local plugin path), each key defaults independently, and unknown keys
    and other tables are ignored because the file is shared
  - Loud validation: the enable flag must be a real boolean (an integer is
    rejected) and the local path must be a non-empty string; violations raise a
    typed settings error naming the file and the offending key. Path *existence*
    is deliberately not checked here — a missing path is a plugin load error,
    not a configuration error
  - A relative local path resolves against the data root so a vault stays
    portable; an absolute path is used as given
  - Observable: unit tests cover absent file, absent table, partial table, both
    validation failures, unknown-key tolerance, and relative-versus-absolute
    path resolution
  - _Requirements: 1.8, 2.1, 2.4, 2.5, 2.7_
  - _Boundary: PluginSettings_
- [x] 2.2 Implement entry-point discovery with provenance and per-plugin isolation
  - The discovery module and its value objects: the extension-group name, the
    origin union (built-in, an advertising distribution with its entry-point
    name, a local file), the per-calculator info record (id, display name,
    version, origin, sorted modalities), the load-error record (subject and
    detail, per the Phase 3 report-type vocabulary), and the report that
    carries both tuples
  - Built-ins are snapshotted as origin "built-in" before anything third-party
    loads, so they always occupy the first registration slots; entry points are
    then processed in an order derived only from the advertised names, making
    automatic calculator selection reproducible across machines
  - An entry-point value resolves to a calculator: a class is instantiated with
    no arguments, a non-calculator callable is called with no arguments, an
    instance is used as-is, and a module value is rejected with a reason naming
    the expected shapes. The resolved object goes through the registration gate
    from 1.2
  - Every per-plugin step runs inside its own failure boundary: an import error,
    a bad shape, a contract violation, or a duplicate id becomes one named load
    error and discovery continues with the remaining plugins; only distributions
    advertising the group are ever imported; the disable flag short-circuits the
    whole channel
  - This task owns populating every info record: the origin, and the version —
    the advertising distribution's version, the installed fitdocs version for a
    built-in, and an explicit absent value for a local file, never a fabricated
    one. The listing command later only formats what this task produced
  - The entry-point source is an injected parameter defaulting to the standard
    library lookup, so ordering, coercion, and isolation are testable without
    installing anything
  - Discovery-state teardown lands with the state it tears down: a reset
    operation that clears the module's cached report and origin map and
    unregisters exactly the ids attributed to plugins, never a built-in, plus an
    automatic test fixture that calls it, so the process-global registry cannot
    leak between this task's tests or any later ones
  - Observable: with an injected source of deliberately unordered entries — one
    that raises on import, one resolving to a non-calculator, one duplicating the
    shipped calculator id — the healthy plugins register after the built-ins in
    the sorted order with their distribution name and version recorded, three
    errors are reported by name, the shipped calculator still resolves to its
    original instance, discovery returns normally, and a reset leaves the
    registry holding only the built-ins
  - _Requirements: 1.1, 1.3, 1.7, 1.8, 1.9, 3.2, 3.4, 4.2, 4.3, 7.1, 7.5_
  - _Boundary: PluginDiscovery_
  - _Depends: 1.2, 2.1_
- [x] 2.3 Implement local plugin file and directory loading
  - When the settings name a local path, a single file is loaded as itself and a
    directory contributes its top-level Python files in alphabetical order,
    skipping underscore-prefixed names and never descending into subdirectories;
    modules execute under a reserved private module namespace and the import
    path is never mutated, so each local plugin file must be self-contained
  - A local module registers its own calculators through the public registration
    function it is already documented to call; discovery attributes the ids that
    appear across each file's execution to that file's path
  - A configured path that does not exist or cannot be read is one named load
    error and the run continues; a file that raises part-way keeps whatever it
    registered before the raise and reports the error against its path
  - Observable: against a temporary data root whose plugin directory holds two
    healthy files, an underscore-prefixed helper, and a failing file, the two
    healthy calculators register in filename order, the helper is skipped, and
    exactly one error names the failing file
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6_
  - _Boundary: PluginDiscovery_
- [x] 2.4 Make discovery once-per-invocation and correct under repeated calls
  - The first discovery caches its report against the data root and settings it
    ran for; a later call with the same pair returns that same report without
    re-registering anything, so discovery is exactly once per invocation no
    matter how many callers ask
  - A call with a *different* data root or settings is a new invocation: the
    previous plugin registrations are dropped through the reset from 2.2 and
    discovery runs again. This is what keeps the existing in-process command
    tests honest, where one process invokes commands against several temporary
    data roots in turn
  - Observable: two identical discovery calls in one process return an equal
    report with each plugin id registered exactly once, and a second call naming
    a different data root loads that root's local plugins instead of silently
    reusing the first root's result
  - _Requirements: 1.2_
  - _Boundary: PluginDiscovery_

- [ ] 3. CLI integration
- [x] 3.1 Run discovery in the existing commands and report failures harmlessly
  - The ingest, regenerate, and standalone-load commands load the plugin
    settings and run discovery once, after the data root is resolved and before
    any engine call, so a plugin-provided calculator can be selected by id and an
    unknown id's error lists plugin ids alongside built-in ones
  - A malformed plugins table is treated exactly like the other settings
    failures: an instructive message and the configuration exit code, before
    anything is written
  - Plugin load errors are printed after the existing end-of-run summaries, each
    naming its subject and detail; the exit-code decision is untouched, and the
    command docstring states plainly that plugin load errors are warnings, never
    failures
  - Observable: a run whose only anomaly is a failed plugin prints the failure
    and exits successfully, a run with a genuine per-file failure still exits
    with the failure code, and a document whose modality only a plugin supports
    is computed by that plugin
  - _Requirements: 1.2, 1.4, 1.5, 1.6, 2.7, 3.5, 3.6_
  - _Boundary: CliPluginWiring_
  - _Depends: 2.3, 2.4_
- [x] 3.2 Implement the plugins listing command
  - A command that prints one row per registered calculator — id, display name,
    version, origin, and supported modalities — rendering the records discovery
    already populated in 2.2; this task owns presentation only, including
    printing an explicit "unknown" wherever the recorded version is absent
    rather than inventing one
  - A second block lists every load error with its subject and detail, and an
    explicit line states when there were none
  - The command exits successfully whenever it produced a listing, including
    with load errors present; when the data root cannot be resolved it still
    lists built-ins and distribution-provided calculators, states that no local
    plugin configuration was consulted, and exits successfully — a deliberate,
    documented departure from the configuration-error treatment, because the
    command must work outside a configured vault
  - The command performs no network access and writes nothing to the data root
  - Observable: the command lists only built-ins on a clean install, lists an
    injected plugin with its distribution name and version, still exits zero
    with load errors present, and produces a listing plus the not-consulted note
    when no data root resolves
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_
  - _Boundary: PluginsCommand_

- [ ] 4. Validation and plugin-author documentation
- [x] 4.1 (P) Verify discovery against a really installed plugin distribution
  - A minimal fixture distribution under the test fixtures that advertises a
    trivial running calculator in the extension group, kept license-clean and
    dependency-free
  - A slow end-to-end test mirroring the existing install smoke: install fitdocs
    from this checkout together with the fixture distribution into an isolated
    tool location, run the installed binary's listing command, then uninstall.
    The shipped-typing assertion is not repeated here — 1.3 owns it
  - Observable: the installed listing names the fixture calculator with the
    fixture distribution's name and version, confirming keyless discovery works
    from a real install and not only from an injected source
  - _Requirements: 1.1, 4.1, 4.2, 4.3, 6.1_
  - _Boundary: PluginInstallE2E_
  - _Depends: 3.2_
- [x] 4.2 (P) Guard the preserved guarantees and the public surface
  - Regression coverage that with nothing installed and nothing configured the
    document goldens and the repeat-render determinism suite are byte-identical
    and the shipped calculator's registration, selection, and results are
    unchanged
  - The offline guard extends over discovery (loading plugins performs no
    network access) and the dependency footprint is asserted unchanged
  - A public-surface test asserting every plugin-facing name imports and is the
    same object its defining module exposes, so a compatible upgrade cannot
    silently drop one. The authoritative list is the design's public-surface
    enumeration, not the prose written in 4.3 — both tasks read the same source,
    so neither waits on the other
  - A test that a registered plugin whose computation raises is reported through
    the existing per-document failure channel — that document fails, every other
    document is processed
  - Observable: the full suite passes with the new coverage, and deleting any
    documented public name or making discovery touch the network fails a test
  - _Requirements: 1.7, 3.7, 4.8, 5.2, 5.5, 7.1, 7.2, 7.3, 7.4_
  - _Boundary: RegressionSuite, PublicApi_
  - _Depends: 3.1_
- [x] 4.3 (P) Document the plugin platform for authors and users
  - A plugin guide covering the end-to-end packaged example (source layout, the
    extension-group declaration, install, verification with the listing
    command), the local plugin file alternative and when to choose each, the
    published-distribution naming convention and the id-uniqueness rule, and a
    diagnosis section showing the output for each rejection reason
  - The guide states the public import surface available to plugin authors —
    transcribed from the design's public-surface enumeration, the same source
    4.2's guard test reads — states that everything else is internal and may
    change without notice, and states the compatibility policy in terms of
    released version numbers
  - The guide states plainly that local plugin files are executed as ordinary
    code with the user's own privileges and that fitdocs applies no sandboxing;
    the project README gains a short plugins section pointing at the guide, and
    the existing calculator-authoring page cross-links to it
  - Observable: a reader can follow the guide from an empty directory to a
    calculator the listing command reports, and every import name the guide
    documents appears in the design's public-surface enumeration
  - _Requirements: 2.8, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 6.4_
  - _Boundary: UserDocs_
  - _Depends: 3.2_
- [x] 4.4 Reconcile the design's public-surface enumeration against the shipped
      `training-load` contract
  - `design.md`'s Packaging + PublicApi section (~line 806) still lists the
    pre-`training-load` surface: `NotConfirmed` instead of `NotComputed`, and
    it is missing `LoadContext`, `LoadSettings`, `LoadSettingsError`,
    `DEFAULT_LOAD_SETTINGS`, `NonSelectedValue`, `QualityFlag`, and
    `supports_activity` — all real `fitdocs.load.__all__` exports today. Bring
    the enumeration into agreement with the live export list, deciding
    deliberately (and recording the reasoning inline) whether `registry`, a
    re-exported submodule rather than a contract symbol, belongs in a
    depend-on list of names
  - Resolve the design's own **RECORDED FOLLOW-UP (2026-07-25, cross-spec
    review)** note at ~lines 815-837 as part of this task, rather than leaving
    it standing alongside a corrected list: its three numbered items
    (`NotConfirmed` → `NotComputed`, the compatibility-statement rewrite, and
    the `LoadContext`/`supports`/`ProfileView` contract changes) are exactly
    what this task closes out
  - **Item 3's `supports` half is superseded, not literal.** It reads "the
    Protocol gains `supports(activity)`" — that has since been withdrawn:
    commit `3121bb6` ("remove the Protocol supports declaration the drift
    closure missed") deleted that member, and `LoadCalculator`
    (`src/fitdocs/load/types.py:325-375`) declares no `supports` member today,
    by design. `supports` is an optional, off-Protocol capability a calculator
    may define; the engine discovers it only through the module-level
    `supports_activity(calculator, activity)`
    (`src/fitdocs/load/types.py:378`), never as a Protocol requirement.
    Transcribing item 3 at face value would re-land exactly the drift
    `3121bb6` removed — resolve it as "the Protocol gains `supports_activity`
    as a module-level function; `LoadCalculator` itself gains no `supports`
    member," not as a literal Protocol addition. See
    `.kiro/queue/2026-07-26-phase4-specs-pin-withdrawn-supports-member.md` for
    the wider spread this same drift left across other specs
  - This task is this spec's vehicle to correct its own design copy — no other
    task or spec may edit `plugin-api/design.md` without one; per the design's
    own note, this is not a re-spec, so requirements, other tasks, and prior
    approvals are unchanged
  - Observable: `design.md`'s surface enumeration matches
    `fitdocs.load.__all__` (modulo the recorded `registry` decision), and the
    RECORDED FOLLOW-UP note is either resolved-and-removed or updated to state
    plainly that all three of its items are closed
  - _Requirements: 5.2, 5.3_
  - _Boundary: PublicApi_
  - _Depends: 4.3_

## Implementation Notes

- Test command in this environment must be `COLUMNS=200 TERM=dumb uv run pytest -q`.
  Without it, 5 tests in `tests/test_cli.py`, `tests/load/test_cli_load.py`, and
  `tests/load/test_prompts.py` fail on `rich` terminal-width wrapping and ANSI
  colorization — an environment artifact, never a regression.
- 1.2: `validate_calculator` is total over malformed *shapes* but not over hostile
  descriptors — an object whose `calculator_id` is a raising property, or whose
  `supported_modalities` raises while being iterated, propagates that exception out
  of the validator, and `register()`'s message interpolates `{calculator!r}` so a
  raising `__repr__` does the same. Task 2.2's per-plugin failure boundary must
  therefore be `except Exception`, never narrowed to `except ValueError`.
- 1.3: `[tool.hatch.build.targets.wheel] packages = ["src/fitdocs"]` ships non-Python
  package files as-is — `py.typed` needed no `pyproject.toml` change (confirmed by
  `uv build --wheel` + `unzip -l`). `tests/test_packaging.py`'s module docstring is
  now stale (still says "install the console script and run it", "two-or-fewer
  `uv tool install` invocations"); task 4.1 mirrors that file and should refresh it.
- 2.1: Two sanctioned deviations from the design's pre-settings-foundation code
  sketch, both applied: `PluginSettingsError` subclasses `fitdocs.settings.SettingsError`
  (so the CLI `except SettingsError` boundary catches it, matching
  `tiles.TileSettingsError`), and `load_plugin_settings`'s `document` param is typed
  `Mapping[str, object]` (what `load_settings_document` returns), not `Mapping[str, Any]`.
  `plugins.py` currently holds ONLY the settings half; task 2.2 adds discovery to the
  same module.
- 2.2: `discover()` runs the entry-point channel + built-in snapshot only; it does
  NOT load local files (2.3) and does NOT cache (2.4). The 2.3 local-channel seam is
  a plain descriptive comment after the entry-point loop, not a stub. Per-plugin
  isolation uses `except Exception` (three steps: load, coerce, register) — never
  narrowed to `except ValueError`, per the 1.2 finding. `reset()` unregisters only
  ids in the module `_plugin_origins` map, never a built-in; an autouse
  `plugins.reset()` fixture in `tests/conftest.py` prevents registry leakage across
  the whole suite. Sort key `(entry_point.name, dist_name, entry_point.value)` uses
  advertised data only. `plugins.py` + `test_plugins.py` now hold both the settings
  half (2.1) and the discovery half (2.2); tasks 2.3 and 2.4 extend the same files.
- 2.3: Local channel runs after the entry-point loop inside `discover()`, gated on
  `settings.enabled` and a non-`None` `data_root` (the degraded listing path skips
  it). `_load_local_file` execs each file under `fitdocs_local_plugins.<stem>` via
  `spec_from_file_location`/`exec_module` with a `before`/`after` id-diff for
  attribution in a `finally`, wrapped in `except Exception` so a mid-import raise
  keeps whatever registered first. Req 2.6's "cannot be read" covers BOTH a missing
  path AND an existing-but-unlistable directory: `_load_local_channel` wraps the
  `_local_files()` enumeration in `except OSError` so an unreadable directory's
  `iterdir()` `PermissionError` becomes one named load error instead of propagating
  out of `discover()` — the single-file unreadable case is already covered by
  `_load_local_file`'s boundary. The unreadable-directory test `chmod 000`s the dir
  and self-skips if still listable (root).
- 2.4: Discovery is now cached on module-level `_cached_key: tuple[Path | None,
  PluginSettings] | None` + `_cached_report`. `discover()` computes `key =
  (data_root, settings)` FIRST: a same-key hit returns the cached report before any
  registration work (nothing re-registers, no duplicate-id error); a different-key
  hit calls `reset()` to drop the prior root's plugins, then re-runs both channels
  and re-caches. `entry_points_fn` is deliberately NOT part of the key (design keys
  on `(data_root, settings)` only). `reset()` now clears the cache (key + report) in
  ADDITION to unregistering plugin ids — so the autouse `plugins.reset()` fixture in
  `tests/conftest.py` (unchanged) prevents cache leakage across tests just as it
  already prevented registry leakage.
- 3.1: `_plugin_report(data_root)` mirrors `_tile_store`: `load_settings_document`
  + `load_plugin_settings(document, settings_path(data_root))` inside ONE
  `except SettingsError` (a table-level `PluginSettingsError` is a `SettingsError`
  subclass, so the same clause routes both to `_config_error` → exit 2 before any
  write), then `discover(data_root, settings)`. All three commands call it after
  `_resolved_data_root` and before any engine call (in `load`, before
  `_run_load_pass`, so a plugin `--calculator` id resolves and unknown ids list
  plugin ids). `_report_plugin_errors(report)` prints subject/detail AFTER the
  summaries and is a no-op when clean (the standing "no errors" line is 3.2's, not
  here); the `failed=...` passed to `_finish` is byte-identical to pre-3.1, so plugin
  errors never move the exit code. Test files: `tests/test_cli.py`,
  `tests/load/test_cli_load.py`. NOTE for 4.2: Req 1.4 (auto-select a plugin for a
  modality no built-in supports) has no dedicated CLI test — design traceability maps
  1.4 to the Registry, and 3.1 proxies it via the forced `--calculator` path; 4.2's
  regression suite is the place to add auto-selection coverage if wanted.
- 3.2: `plugins_command` (`@app.command("plugins")`) is presentation-only and reuses
  `_plugin_report(data_root)` on the resolvable path (a malformed `[plugins]` table
  still exits 2). On `DataRootError` it sets `data_root=None`, calls
  `discover(None, DEFAULT_PLUGIN_SETTINGS)` (2.3's gating skips the local channel for
  a `None` data_root), prints a "no local plugin configuration consulted" note, and
  exits 0 — the documented 4.7 departure, reserved ONLY for an unresolvable root, not
  a broken table. `_report_plugins`/`_origin_text` render a rich table (origin:
  `built-in` / `<dist> <entry point>` / `local: <path>`; `version is None` → literal
  `unknown`) plus a load-error block that prints "No plugin load errors." when clean.
  The command NEVER calls `_finish()`, so a produced listing always exits 0 even with
  load errors. Injected-`PluginReport` tests cover distribution-origin + `None`-version
  rendering (a clean install can't produce those); clean-install / malformed-table /
  unresolvable-root tests exercise real control flow. Pre-existing (NOT 3.2) mypy
  errors remain in `tests/test_cli.py`: garmin_fit_sdk untyped ×2 and a
  `_DummyTiles`/`TileSource.resolve` signature mismatch — verified on `main` via git
  stash; `mypy src/fitdocs/cli.py` itself is clean.
- 4.1: `tests/test_plugins_install.py` mirrors `tests/test_packaging.py`'s isolated
  offline `uv tool install`, adding `--with <tests/fixtures/plugin_pkg>` to co-install
  the fixture distribution on EVERY install path (offline, cache-warm, retried
  offline). Fixture `fitdocs-fixture-calc==9.9.9` advertises
  `[project.entry-points."fitdocs.load_calculators"] fixture =
  "fitdocs_fixture_calc:FixtureCalculator"`; the distinctive `9.9.9` (fitdocs itself
  is `0.1.0`) makes the version assertion a real provenance proof, not a self-version
  echo. The listing is exercised via the DEGRADED path: scrub `FITDOCS_DATA` (correct
  env var per `config.py`, NOT `FITDOCS_DATA_ROOT`) + empty cwd → `DataRootError` →
  `discover(None, ...)` runs the entry-point channel only. GOTCHA: rich's
  `Console.size` forces a fixed 80×25 when `TERM=dumb` REGARDLESS of `COLUMNS`, which
  wraps wide-table cells apart — the listing subprocess therefore sets
  `TERM=xterm-256color`, `COLUMNS=400` so assertions on id/dist-name/version don't
  split. Does NOT repeat the `py.typed` assertion (1.3/`test_packaging.py` owns it).
- 4.2: Four test-only guards (no `src/**`). Public-surface guard in
  `tests/test_public_api.py` is an `_LOAD_EXPECTED` INCLUSION check (hasattr + `is`
  identity) over exactly the 17 authoritative `fitdocs.load` names — NOT an
  `__all__`-equality pin, so `WithdrawnCalculator`/`registry` (in `__all__` but declared
  non-public) never fail it. Offline + dep-footprint guards in `tests/test_determinism.py`
  (section 7): `discover()` runs inside the existing `_no_socket` guard (7.1), and
  `_BASELINE_RUNTIME_DEPENDENCIES` pins `[project].dependencies` verbatim
  (garmin-fit-sdk, typer, rich, pyyaml, tomli-w) + asserts no runtime
  optional-deps (7.2). New `tests/test_plugin_regression.py` holds the no-plugin
  regression (no-op `discover()` leaves `after[0] is before[0]`; byte-identical
  apply_load across discovery-preceded vs not) and the Req 3.7 per-document isolation
  test (`_RaisingRideCalculator` on `Modality.BIKE` fails only the ride doc via
  apply_load's existing per-doc `except Exception`; the run doc still processes).
  Pre-existing mypy noise remains on UNTOUCHED lines of `test_determinism.py`
  (121/407/540/550) and `tests/fixtures/builder.py` (garmin_fit_sdk) — not 4.2's.
- 4.3: `docs/plugins.md` (new) + a README "Plugins" section + a
  `docs/contributing-calculators.md` cross-link. Docs-only. The guide's diagnosis
  examples were corrected (review round 1) to show the tool's ACTUAL output —
  every plugin-error `detail` is a bare `str(exc)`, so NO exception-class prefix
  (`ModuleNotFoundError:`/`ValueError:`), no invented `; got '' (str)` suffix, and
  the contract-violation detail is the real `calculator <repr> does not satisfy the
  contract: <reason>` wrapper. The closing cross-reference points at
  `README.md#choosing-a-provider` (the malformed-`[tiles]` exit-2 section), not a
  non-existent README plugins-failure section.
- 3.3 gap CLOSED (found during 4.3 review; reopened tasks 1.2/2.2/4.3 with user
  sign-off): the duplicate-id load error now names the contested id AND both
  origins. `registry.py`'s `DuplicateCalculatorIdError` gained an additive
  `calculator_id` attribute (message byte-unchanged, so existing `str(exc)` asserts
  hold); `register()` sets it. `plugins.py` added `_incumbent_origin_text(id)`
  (reads only `_plugin_origins` + the validated id string — never the newcomer's
  `__repr__`) and both channels catch `DuplicateCalculatorIdError` BEFORE the broad
  `except Exception` (isolation intact: every non-duplicate failure still hits the
  broad catch, per the 1.2 hostile-descriptor note), building
  `detail=f"{exc}; kept the {_incumbent_origin_text(...)}"`. Newcomer origin stays
  the error `subject`. Incumbent renders as `built-in registration` /
  `registration from <dist>: <entry point>` / `registration from local file <path>`.
  The local channel relies on `exc.calculator_id` (the id is not otherwise in hand
  mid-`exec_module`). `docs/plugins.md` restored to describe both origins; 3 new
  duplicate-id tests in `test_plugins.py` (built-in, distribution, local incumbents).
