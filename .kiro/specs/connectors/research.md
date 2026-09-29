# Research & Design Decisions: connectors

## Summary
- **Feature**: `connectors`
- **Discovery Scope**: Complex Integration — a new package with the project's
  first credential handling, its second network user, and its first writer
  into the inbox, wired beside (never into) the existing drain, and landing
  edits to three governed contracts (inbox wording, settings schema, ownership
  contract) plus the packaged skill.
- **Research mode**: every investigation below was done in-context by the spec
  writer (no research subagents were available in this run). The only
  "external" facts relied on are stdlib and packaging behavior, each checked
  against the interpreter in the worktree (`uv run python`, Python 3.11.15,
  typer 0.27.0) rather than from memory. No network request was made and no
  service was contacted.
- **Key Findings**:
  - **The inbox is ready to receive deliveries without change.**
    `inbox.select_candidates` (`src/fitdocs/inbox.py:563-597`) already skips
    any path with a dot-prefixed component (`:590`) and requires a `.fit`
    suffix (`:587`), so a delivery written as `.<name>.tmp` and renamed is
    invisible until it is whole. The drain (`sync.drain`, `sync.py:616`)
    hashes each stable candidate once and dedupes against
    `fit-archive/<sha>.fit` (`layout.archive_path`, `layout.py:297`), so a
    delivered file is an ordinary candidate.
  - **Under LEAVE a delivered file is re-read and re-hashed on every drain,
    forever** (queue `2026-09-17-inbox-drain-leaves-source-fit-in-inbox`,
    confirmed at `sync.py:750-765`: `candidate.path.read_bytes()` at
    `:752` then `hashlib.sha256` at `:765` for every stable candidate, with
    no skip before the read). A folder connector pointed at a 2,478-file export folder would
    triple the bytes on disk (source, inbox copy, archive) and re-hash 2,478
    files per drain. The never-delete guarantee is pinned in four places
    (inbox Req 6.6; `docs/inbox.md` "No configuration ever deletes an inbox
    file"; `tests/test_install_docs.py:331-344`;
    `tests/test_docs_guarantees.py:175-197`) and in the compatibility policy
    (`docs/compatibility.md:17-18`).
  - **The only network code is `tiles.py`, and nothing guards that.**
    `tiles.py:50` is the only `import urllib.request` in `src/`. The roadmap
    names `tests/test_contract.py:1345`, `tests/performance/test_purity.py:525`
    and `tests/test_determinism.py:124, 226` as "the guards" of the "only
    network module" statements; measured, none of them asserts that: the
    first bans `urllib` from `contract.py` only, the second bans network
    modules from the pure performance modules only, and the third blocks
    sockets during parse/compute and plugin discovery only. The statements
    at `cli.py:98-102`, `sync.py:41-52`, `tiles.py:7, 246, 407`,
    `docs/configuration.md:74, 93` and `README.md:66` are unguarded prose.
  - **The load-calculator registry is the shape the plugin kind will
    parameterize.** `plugins.py` drives `registry.register`,
    `registry.unregister`, `registry.available` and
    `registry.validate_calculator` (`load/registry.py`), catches
    `DuplicateCalculatorIdError(calculator_id=...)`, and attributes local
    files by diffing `available()` ids before and after executing the file
    (`plugins.py:604` records the ids before a local file runs;
    `_attribute_local_ids`/`_registered_ids` at `:648-658` diff them after). A connector registry with the same five
    operations and the same three error types is enough for the plugin-api
    update to add a kind without redesign.
  - **`tests/test_confinement.py`'s `EntryPoint` field is `non_vacuous`,
    not `wrote`** (`:792-812`); the relayed peer note paraphrased it. It is
    `Callable[[Sequence[str]], bool]` with `_wrote_a_workout_document` as
    the default.

## Research Log

### Live-tree verification of every seam the brief and roadmap cite
- **Context**: specs are instructions to later agents; every file:line must be
  true when written. Measured at `a5792f2` (this branch's base).
- **Findings** (drift from the brief/roadmap in parentheses):
  - `[inbox]` reader `inbox.py:228-277` ✓; `select_candidates` `:563-597` ✓;
    `settle` `:667-721`; `DEFAULT_IGNORE_PATTERNS` `:532-537`;
    `DEFAULT_INBOX_SETTINGS` `:198-204`; `validate_inbox_paths` `:417-463`;
    `create_inbox_paths` `:466-484`; `move_processed` `:762-814`.
  - Stability/read-defer in the drain: `sync.py:742-764` (settle at
    `:742-745`, the read-or-defer at `:751-764`; the brief said `750-763`;
    cosmetic).
  - `tiles._user_agent` `tiles.py:252-271` ✓; `TileSource` `:279-297`;
    `_default_fetch` `:404-418`; the fetch timeout constant `:275`.
  - Network statements: `cli.py:98-102` ✓, `sync.py:41-52` ✓, `tiles.py:7`
    ✓ plus two more the brief omits — `tiles.py:246` ("The only
    network-touching code in the package") and `tiles.py:407` ("The
    package's only network call") — and `README.md:66` ("the only time
    fitdocs touches the network"); `docs/configuration.md:74, 93` ✓.
  - `_config_error` `cli.py:1000-1010` ✓; `WRITING_ENTRY_POINTS`
    `tests/test_confinement.py:815` ✓; `SETTINGS_LOCATION_KEYS` `:110-113`.
  - `plugins.py:207` `ENTRY_POINT_GROUP` ✓.
  - Frozen dependencies: `tests/test_determinism.py:672-712` ✓ and
    `tests/test_packaging.py:503-519` ✓.
  - Skill pins: `tests/test_agent_skill.py:614` (every named command/option
    exists) ✓ and `:681` (`test_inbox_skill_routine_fence_is_exactly_sync_and_check`)
    ✓; the channel binding is `:94-106` (literal of eight) and `:454-491`.
  - Command count: `cli.py:5` says "Nine commands"; `tests/test_cli_skill.py:266`
    pins `len(commands) == 9` and `"Nine" in doc[:400]`. Adding two commands
    makes eleven (the training-blocks WARN on stale counts applies).
  - Settings-table counts: "six tables" at `docs/configuration.md:51`,
    `docs/compatibility.md:24` and `:64`;
    `tests/test_compatibility_policy.py:137-144` (`SETTINGS_TABLE_LITERALS`)
    and `:270` (`test_settings_schema_subsection_names_all_six_tables`);
    the ownership contract's `fitdocs.toml` bullet lists the tables at
    `docs/ownership-contract.md:439-441`.
  - `CONTRACT_VERSION` is `"4"` at `contract.py:275`; the ownership contract
    states it at `docs/ownership-contract.md:3`; the declaration goldens
    (`tests/declaration_golden/*.AGENTS.md`) restate it.
  - `docs/index.md` rows: ten pages; `tests/test_docs_guarantees.py:1110-1121`
    lists the required links.
  - `[project.urls]`: `pyproject.toml:33-44`; every docs URL a shipped
    artifact (including `SKILL.md`) references must be a declared URL
    (`tests/test_packaging.py:263-293`).
  - mypy perimeter: `pyproject.toml:81-164` (`files`), "Every module holding
    a LoadCalculator- or TileSource-shaped stub is in scope".

### Standard-library and packaging behavior relied on
- **Sources Consulted**: the interpreter in the worktree; CPython source via
  `inspect.getsource`; typer's `Typer.__init__` signature.
- **Findings**:
  - `urllib.request.HTTPRedirectHandler.redirect_request` copies only
    `req.headers` to the redirected request; headers added with
    `Request.add_unredirected_header` are not copied. A credential header
    added that way is therefore never sent to the redirect target, while the
    User-Agent (an ordinary header) is.
  - `urllib` raises `HTTPError` for every 4xx/5xx; the error object carries
    `code`, `headers` and a readable body, so a transport can turn it into
    an ordinary status-bearing response. `urllib` does not decode
    `Content-Encoding`; a gzip body arrives compressed (the intervals.icu
    viability finding agrees).
  - `tempfile.mkstemp` creates its file with mode `0o600` (measured), so the
    temp-then-`os.replace` idiom already used by `quarantine.py` and
    `tiles.py` yields owner-only files.
  - typer 0.27.0 defaults `pretty_exceptions_show_locals` to `False`, but
    `pyproject.toml` admits `typer>=0.12`; setting it explicitly on the app
    removes any dependence on the resolved version for a crash's local
    variables (Req 10.6).
  - A FIT file header is 12 or 14 bytes: byte 0 is the header size, bytes
    8-11 are the ASCII signature `.FIT`. The synthesized fixtures
    (`tests/fixtures/builder.py:1041-1147`) include valid, non-FIT and
    truncated shapes.
  - The XDG Base Directory convention: `XDG_CONFIG_HOME` is honored only when
    set to an absolute path; otherwise `~/.config` is the default. CI runs
    Ubuntu only (`.github/workflows/ci.yml:41`), so POSIX file modes are the
    tested platform.

### Sibling specs and their briefs
- **Context**: five Phase 8 specs are written in parallel; this one is
  upstream of `intervals-connector` and adjacent to `activity-identity`.
- **Findings**:
  - `activity-identity`'s brief derives source kind "from the file itself
    (`file_id` manufacturer/product, writer markers …), never from which
    connector delivered it". Delivery therefore needs to carry no
    classification; it must only never alter the bytes.
  - `intervals-connector`'s brief needs: a personal key over HTTP Basic, a
    listing by date window, skipping Strava stubs, a source filter, a gzip
    original checked for a FIT header, an explicit User-Agent, 401/403
    reported by name, and 429 backoff "within the bounds `connectors` sets".
    Every one maps onto this design's protocol, transport and ledger (see
    design.md "Cross-spec seams").
  - Amendment 4 of `wiki-contract` is landed by three specs; each lander
    advances the contract version by one from `main`'s value and the second
    re-pins (cross-spec ruling 2026-09-29, superseding this spec's earlier
    once-per-release sharing rule; design.md "Contract version").

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Inbox producer (selected) | Connectors deliver into the inbox; the existing drain ingests | One ingestion path; hand drops, exports and pulls identical; no page knowledge in connectors | Delivered copies accumulate under LEAVE unless removed | The roadmap's decision; this design adds removal of archived deliveries |
| Direct archive write | The pull writes `fit-archive/<sha>.fit` itself | No inbox copy | Archive presence is the "processed" marker (`sync.py` module docstring); writing it before a page exists marks unprocessed work done | Rejected |
| Second ingestion path | The pull calls the per-file pipeline itself | No inbox copy | Rejected at discovery ("connector-aware direct attach") | Rejected |
| Drain consults the ledger | The drain skips candidates a ledger says are archived | No deletion | Couples `inbox`/`sync` to `connectors`; copies still accumulate on disk | Rejected |

## Design Decisions

### Decision: What LEAVE means for pulled files
- **Context**: Req 8; queue `2026-09-17-inbox-drain-leaves-source-fit-in-inbox`;
  the brief asks the design to pick a pull-set disposition or the ledger.
- **Alternatives Considered**:
  1. Leave deliveries forever — violates "pulled files do not accumulate".
  2. The drain skips ledger-known files — couples the drain to connectors and
     still triples storage.
  3. The pull renames archived deliveries to hidden names — no re-hash, but
     storage still accumulates and the inbox fills with hidden debris.
  4. The pull removes its own archived deliveries (selected).
- **Selected Approach**: each delivery is recorded in the ledger as pending
  with its content hash and inbox-relative location. At the start of every
  non-dry-run pull, the instance's pending deliveries are swept: one whose
  hash is present in `fit-archive/` and whose file still hashes the same is
  removed; one whose file differs is released (no longer tracked, never
  touched); one whose file vanished before archiving is forgotten so it is
  fetched again; anything else stays.
- **Rationale**: a delivery is never the only copy — the source holds the
  original and the archive holds identical, hash-verified bytes before
  removal — so removing it loses nothing, which is exactly the property the
  never-delete guarantee protects for the athlete's own files. The drain is
  untouched and still never deletes.
- **Trade-offs**: a governed contract's wording is refined (inbox docs and
  compatibility policy gain an explicit carve-out; every pinned never-delete
  sentence stays true because it speaks of configurations and dispositions,
  which the drain alone applies). A run's deliveries are removed by the
  *next* pull, not the same one, so at most one pull's deliveries are
  re-hashed by intervening drains. The inbox spec gains an amendment record,
  which the roadmap's Phase 8 Existing Spec Updates list did not name.
- **Follow-up**: the controller should add an `inbox` line to the roadmap's
  Phase 8 Existing Spec Updates (task 9.1 records it on the inbox spec; the roadmap line was added at the Phase 8 spec batch, 2026-09-29).

### Decision: Named instances, not one table per connector id
- **Context**: Req 3. An athlete may point two folder connectors at two
  export folders.
- **Selected Approach**: `[connectors.<name>]` sub-tables; the `connector`
  key names the implementation and defaults to the name. Ledger, credentials
  file, delivery subdirectory and environment variables are all keyed by the
  instance name.
- **Trade-offs**: renaming an instance orphans its ledger; the next pull
  re-fetches and records each file as already held (hash dedupe), which is
  slow but lossless. Documented.

### Decision: Authentication styles
- **Selected Approach**: `none`, `api-key`, `login` implemented; `oauth-browser`
  reserved. `login` covers a user-installed connector for a service with a
  password-for-token exchange (the password is used once and never stored);
  it has no shipped user in this spec and is exercised by a synthetic
  connector in tests.
- **Rationale**: the brief requires the MFA/lockout/429 reporting and
  "a service with a refresh flow never has its password persisted"; those
  only exist with a login flow. Building it now keeps the credential store
  from needing a rebuild when the first such connector (a plugin) arrives.
- **Trade-offs**: environment overrides apply to static personal keys only;
  a rotating refresh token cannot be written back to the environment, so a
  login-style connector's tokens live only in the store. Documented.

### Decision: Watermark plus look-back, ledger decides
- **Context**: Req 6.4, 7.2, 7.7. A windowed service lists by start time, and
  activities can reach it days after they happened.
- **Selected Approach**: listing starts at `watermark − lookback_days`
  (default 30), or unbounded when there is no watermark; `--since` overrides.
  The ledger, never the window, decides what is new. The watermark only
  advances over a contiguous prefix of final outcomes.
- **Trade-offs**: an activity uploaded to a service more than 30 days after
  the watermark passed it is missed until `--since` or a larger look-back is
  used. Documented.

### Decision: One User-Agent definition
- **Selected Approach**: `fitdocs.version.user_agent()` composes
  `fitdocs/<version_display()> (+https://github.com/joshua-stauffer/fitdocs)`;
  `tiles._user_agent()` delegates to it; the connector transport uses it.
  `tests/test_tiles.py:536-602` patch `fitdocs.version.version`, so they stay
  green unchanged.

### Decision: The framework checks the FIT header
- **Selected Approach**: before delivery, bytes whose byte 0 is not 12 or 14
  or whose bytes 8-11 are not `.FIT` are recorded skipped ("not a FIT
  file"); a connector may decline earlier with a more specific reason
  (`intervals-connector`: "original is GPX").
- **Rationale**: a non-FIT payload delivered as `.fit` would be quarantined
  by the drain and sit in the inbox forever; one check in the framework
  protects every connector.

### Decision: A positive network allow-list guard
- **Selected Approach**: a new AST guard walks every module under
  `src/fitdocs/` and fails when any module other than `fitdocs/tiles.py` and
  `fitdocs/connectors/http.py` imports `socket`, `ssl`, `http` (any
  submodule), `urllib.request`, `urllib.error`, `ftplib`, `smtplib` or
  `xmlrpc`. The existing purity guards stay as they are; they are not the
  statements' guards (see Research Log) and remain true.

### Decision: Registry mirrors the load registry; plugins.py untouched
- **Selected Approach**: `fitdocs.connectors.registry` exports `register`,
  `unregister`, `get`, `available`, `validate_connector` and the three error
  types, with `DuplicateConnectorIdError.connector_id`. The plugin-api update
  parameterizes `plugins.py` over (entry-point group, validate, register,
  unregister, available, info builder); nothing here pre-empts it.
- **Rationale**: the plugin platform's machinery is proven against exactly
  this shape; a different shape would force the "copy, not parameterize"
  outcome the roadmap forbids.

### Decision: Package-private atomic writer
- **Selected Approach**: one `connectors/_atomic.py` helper (temp file in the
  target directory with a dot prefix, fsync, `os.replace`, cleanup) used by
  the ledger, the credentials store and delivery. This is one more private
  copy of the idiom queue item `2026-09-15-atomic-write-helper-copied-per-engine`
  tracks (activity-identity's `identity/holds.py` is another); consolidating
  it is that item's work, not this spec's. Task 1.2 appends the
  `connectors/_atomic.py` site to that item, noting that its resume command
  puts the shared helper in `fitdocs.docio`, which this package's boundary
  guard forbids, so the consolidation must widen that guard to admit the
  helper's module.

## Risks & Mitigations
- Real use before `activity-identity` duplicates pages — documented caution in
  `docs/connectors.md` (replaced by the regenerate-before-first-pull
  statement when identity is on `main` first); no connector is pointed at a
  real data root before identity lands (roadmap constraint, operator rule).
- Two overlapping pulls (cron overlap) — last ledger write wins; lost entries
  cause a re-fetch that records "already held" (hash dedupe). No lock is
  introduced (no other fitdocs command locks). Documented.
- A delivery's name raced by another writer between the existence check and
  the rename — single-writer assumption; the collision check plus hash
  verification before any removal bound the damage to a re-fetch.
- A service echoing a key in an error body — every reported string passes the
  run's redactor, which knows every credential value and signed location
  the run handled, raw and percent-encoded.
- Platforms without POSIX modes — the permission check and modes are
  enforced on POSIX; CI is Linux; documented.

## References
- `.kiro/steering/roadmap.md` Phase 8 (lines 1417-1797).
- `.kiro/specs/connectors/brief.md`, `.kiro/specs/intervals-connector/brief.md`,
  `.kiro/specs/activity-identity/brief.md`.
- `.kiro/specs/inbox/requirements.md` Requirement 6.
- XDG Base Directory Specification — `XDG_CONFIG_HOME` semantics (relied on
  from the standard, not fetched).
- Python 3.11 `urllib.request` (`HTTPRedirectHandler.redirect_request`,
  `Request.add_unredirected_header`), `tempfile.mkstemp`.
