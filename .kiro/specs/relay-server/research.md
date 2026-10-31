# Research & Design Decisions

## Summary
- **Feature**: `relay-server`
- **Discovery Scope**: New Feature (the relay package) plus Extension (the
  connector framework, the CLI, the release gate, CI, steering and docs).
  The full discovery process ran.
- **Downgrade**: research ran in-context. No subagent dispatch is available
  to batch writers, so the codebase analysis and the external research the
  design skill would delegate were done in this writer's own context.
- **Key Findings**:
  - Configuring any non-pulling connector instance today makes a bare
    `fitdocs pull` fail: `_pull_one` reports "does not pull activities or
    wellness" as the instance's own error (`connectors/pull.py:705-710`),
    and `PullReport.failed` turns that into exit 1. A relay instance is the
    first non-pulling connector kind, so this spec must change the bare-pull
    selection, or the packaged skill's routine (`fitdocs pull --sync
    --no-prompt`) breaks for every athlete who configures a relay.
  - The connector registry rejects an empty capability set
    (`connectors/registry.py:164-165`; connectors Req 2.3). None of the nine
    capabilities describes a token holder, and declaring the publish
    capabilities would couple this spec to publish-core's driving of them
    (R5). The relay style is therefore the one style that may declare no
    capability.
  - `CallMode.AUTH` already makes exactly one attempt whatever the answer
    (`connectors/http.py:281-282`). Every relay-server client call (token
    check, capabilities read, registration start and poll, revocation) is an
    authentication-class call, so this spec uses AUTH mode, adds no
    transport mode, and does not need publish-core's single-attempt write
    mode. Publish requests that later specs send go through `RelayClient`
    with whatever `HttpClient` the caller builds, so they can consume
    publish-core's mode unchanged.

## Research Log

### The connector framework seams this spec extends
- **Context**: R5 gives relay-server the relay auth style. The style touches
  every place that dispatches on `AuthStyle`.
- **Sources Consulted**: `src/fitdocs/connectors/protocol.py` (`AuthStyle`
  146-159, `SUPPORTED_AUTH_STYLES` 157-159, `KeyVerifier`/`TokenIssuer`
  326-341); `credentials.py` (`resolve_credentials` 391-485, `env_var_name`
  131-133); `connect.py` (`run_connect` 135-227, `_env_override` 115-132);
  `registry.py` (`validate_connector` 112-228); `cli.py` (`connect_command`
  1275-1440, the reserved-style refusal 1360-1364, `pull_command`
  1483-1640); `pull.py` (`_runnable` 421-430, the instance error 705-710).
  Verified by `grep -rn AuthStyle src/fitdocs`.
- **Findings**:
  - The dispatch sites are `connect.py:125,169,186`, `credentials.py:411,
    414,456`, `registry.py:102,180,186`, `cli.py:1351,1360,1373,1586` and
    `pull.py:679`. `folder.py:68` and `intervals.py:170` only declare a
    style.
  - `run_connect` builds its session with `settings=None` (`connect.py:155-
    164`). A relay connector needs its instance URL at connect time, so the
    relay flows get their own engine that passes the instance settings.
  - `ConnectFailed.message` quotes the service's message (`connect.py:203`;
    connectors Req 5.6). A relay must never have its text printed, so the
    relay engine returns a code and fitdocs-written text instead.
  - `fitdocs pull` without names pulls every configured instance
    (`cli.py:1572-1584`) and, with an empty selection, prints "No connectors
    are configured; nothing to pull." (`cli.py:1621-1627`).
- **Implications**: a new `AuthStyle.RELAY_TOKEN`, resolved like a personal
  key (environment override included); a `RelayTokenClient` operation
  protocol required by the registry for that style; a separate
  `connectors/relay_connect.py` engine; the bare-pull selection filter with
  its own empty-selection line.

### Guards and pins the fitdocs-side change must keep green
- **Sources Consulted**: `tests/connectors/test_boundary.py` (module list
  91-107, per-module import equality pins 276-380, the tree-wide network
  allow-list 519-631, the clock scan); `tests/connectors/test_surface.py`
  (`EXPECTED_ALL`); `tests/connectors/test_docs.py`
  (`NEUTRAL_SCAN_EXEMPTIONS` 661-671); `tests/connectors/
  test_network_statements.py` (the tech.md pins 630-700);
  `tests/test_release_artifacts.py` (forbidden-pattern controls 180-245);
  `tests/test_agent_skill.py` (the never-connect pins 967-1017);
  `tests/test_version_identity.py` (the released-version scan of `src/`,
  `tests/`, `docs/`).
- **Findings**:
  - The network scan forbids any import of `http` (with submodules), so the
    shared code module may not use `http.HTTPStatus`; statuses are plain
    integers.
  - Every new connectors module needs a `CONNECTORS_MODULE_NAMES` entry and
    an exact import set; the scan resolves relative imports to the real
    module.
  - `api.fitdocs.ai` is not a prefix of any `[project.urls]` value
    (`https://fitdocs.ai`), so the relay connector's module, tests and doc
    section need their own neutral-scan exemption entry, as intervals did.
  - `tech.md`'s Architecture sentence "No server, no background jobs. One
    database: ..." is pinned verbatim (`test_network_statements.py:640-
    647`). The steering amendment rewrites it, so the same task updates
    that pin as a literal.
  - `docs/*.md` must not carry the fitdocs release version literal.
- **Implications**: the File Structure Plan lists each of these test edits
  with the amendment that causes it.

### Release gate and packaging
- **Sources Consulted**: `pyproject.toml` (`[tool.hatch.build.targets.
  wheel] packages = ["src/fitdocs"]`, sdist `only-include`);
  `release/artifact-policy.toml`; `scripts/check_artifacts.py`.
- **Findings**: neither artifact can include `relay/` today, by
  construction. Nothing would catch a later manifest edit that let it in.
  The checker's `FORBIDDEN_MEMBER` check over fnmatch patterns is the
  natural gate. `fnmatch` lets `*` cross `/`, so `relay/*` covers every
  depth. A wheel would carry the package as `fitdocs_relay/...`.
- **Implications**: the distribution amendment adds `relay/*` and
  `fitdocs_relay/*` to `[forbidden].members`, with a positive control each
  and a negative control proving `src/fitdocs/connectors/relay.py` (which
  does ship) is not matched.

### CI shape
- **Sources Consulted**: `.github/workflows/ci.yml`;
  `tests/test_ci_workflow.py` (it pins exactly two jobs, `gates` and
  `supported-pythons`, at line 198); `tests/test_docs_workflow.py`.
- **Findings**: a third job in `ci.yml` would break an existing pin and mix
  the relay's dependencies into the fitdocs job. A separate workflow file
  is pinned by nothing today.
- **Implications**: `.github/workflows/relay.yml` with one `relay` job and
  its own pin module `tests/test_relay_workflow.py`. The root `gates` job
  already runs the pinned-copy cross-check, because it lives in root
  `tests/`.

### External libraries (checked 2026-10-31)
- **Sources Consulted**: PyPI JSON for `starlette`, `uvicorn`, `psycopg`,
  `psycopg-pool`; Starlette's release notes on GitHub; uvicorn's release
  notes on GitHub.
- **Findings**:
  - Starlette 1.x is current (1.0.0 on 2026-03-22, 1.10.0 on 2026-10-24),
    requires Python 3.11 or later, and is BSD-3. 1.0 removed `on_startup`/
    `on_shutdown` and the route decorators: use `lifespan=` and pass routes
    and middleware to the constructor.
  - uvicorn 0.54.0, BSD-3, Python 3.10 or later. `--timeout-graceful-
    shutdown` has existed since 0.22.0. 0.29.0 added "cooperative signal
    handling": after a graceful shutdown uvicorn restores the earlier
    handlers and re-raises the captured signal. Under the default SIGTERM
    disposition the process would then end by signal, not with status 0.
  - psycopg 3.3.6 and psycopg-pool 3.3.3: both LGPL-3.0-only, Python 3.10
    or later. The `binary` and `pool` extras exist.
- **Implications**: floors `starlette>=1.0,<2` and `uvicorn>=0.30,<1`, plus
  `psycopg[binary,pool]>=3.2,<4` in the `postgres` extra. The lockfile pins
  exact versions at implementation time, choosing releases at least two
  weeks old. `fitdocs-relay serve` installs its own SIGTERM/SIGINT handlers
  before handing control to uvicorn, so the re-raised signal lands on them
  and the command exits 0. A subprocess test pins this against the locked
  uvicorn.

### Device-style registration (RFC 8628 as the pattern)
- **Sources Consulted**: RFC 8628 §3.2 (device authorization response),
  §3.4-3.5 (polling, `authorization_pending`, `slow_down`, `access_denied`,
  `expired_token`) and §6.1 (user-code entropy).
- **Findings**:
  - The default poll interval is 5 s, and `slow_down` adds 5 s.
  - §6.1 recommends an 8-character base-20 code from
    `BCDFGHJKLMNPQRSTVWXZ`, which gives about 34.5 bits.
  - The device code (our poll secret) is private to the client.
  - The verification URI is not needed here: the relay emails a link, and
    the CLI prints no relay-supplied URL.
- **Implications**: user code format `^[BCDFGHJKLMNPQRSTVWXZ]{4}-
  [BCDFGHJKLMNPQRSTVWXZ]{4}$`, a 5 s slow-down step, interval bounds 1-60 s,
  expiry bounds 60-3600 s. The codes are `registration-pending`,
  `-slow-down`, `-issued`, `-refused` and `-expired`, with no OAuth error
  strings.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Ports and adapters (selected) | Domain services (identity, rate limits, seam) over one storage protocol, with two backend adapters and HTTP handlers on Starlette | Backends swap by URL; conformance suite targets the port; SQL confined to two modules | More types than a single-module app | Matches the brief's "domain-level interface, not SQL/ORM" |
| Generic SQL layer (SQLAlchemy Core or an ORM) | One query builder for both engines | Less per-backend code | Hides `BEGIN IMMEDIATE` and row locks, which the brief rejects; large dependency | Rejected by the maintainer (brief, Approach) |
| FastAPI | Validation and docs generation | Familiar | Its default validation answers with free-text `detail`; bigger dependency surface; envelope validation is hand-written either way | Starlette suffices |

## Design Decisions

### Decision: the relay auth style is a new `AuthStyle.RELAY_TOKEN`
- **Context**: R5; brief "That needs an auth-style decision".
- **Alternatives Considered**:
  1. Reuse `API_KEY` and bolt registration onto connect as an optional
     protocol.
  2. A new style `RELAY_TOKEN = "relay-token"`.
- **Selected Approach**: option 2. The token resolves exactly like a
  personal key (stored value, or the `FITDOCS_CONNECTOR_<INSTANCE>_TOKEN`
  override). The registry requires the five `RelayTokenClient` operations
  for this style and lets it declare no capability.
- **Rationale**: the style decides how `connect` and `disconnect` behave.
  Encoding the difference in the style keeps the CLI dispatch honest and
  leaves `API_KEY` untouched.
- **Trade-offs**: every style dispatch site gains a branch, and an older
  fitdocs refuses a credentials file whose `auth_style` is `relay-token`
  (it has no relay connector anyway).

### Decision: shared modules are a byte-identical pinned copy (R2)
- **Selected Approach**: `src/fitdocs/connectors/relay_codes.py` (the R3
  vocabulary) and `src/fitdocs/connectors/relay_envelope.py` (the wire
  codec and the format validators) are standard-library-only. The second
  imports the first relatively (`from .relay_codes import ...`), so the
  same bytes import correctly in both packages. The copies live in
  `relay/src/fitdocs_relay/shared/`. `scripts/sync_relay_shared.py`
  (`SHARED_MODULES`, the table later specs append to) writes them, and
  `tests/test_relay_shared_copies.py` fails on any drift or any orphan
  file in `shared/`.
- **Rationale**: one codec on both sides means a field validator cannot
  differ between client and server.
- **Follow-up**: strava-publish appends `src/fitdocs/publish/outcomes.py`
  to `SHARED_MODULES` when it first sends an outcome over the wire.
  relay-server sends none, so it copies none.

### Decision: migrations are one numbered SQL set per backend, applied by a hand-rolled runner
- **Alternatives Considered**: Alembic (needs SQLAlchemy, an SQL toolkit
  the brief rejects); yoyo-migrations (an extra dependency for about 100
  lines of logic); one dialect-portable set (forces a lowest-common-
  denominator DDL and hides type differences).
- **Selected Approach**: `storage/migrations/{sqlite,postgres}/NNNN_<slug>.
  sql`, plus a `relay_schema` version table. Each backend applies a change
  and its version row in one transaction, after taking its own writer lock
  (`BEGIN IMMEDIATE`, or `pg_advisory_xact_lock`) and re-reading the
  current version. A parity test requires identical file names in both
  directories, and the conformance suite checks behaviour.

### Decision: the wrapper seam owns routes, one registration provider, token issuance and namespaced records
- **Context**: the brief's "app factory that accepts extra routes plus the
  token-issuing operation", plus "the database is the whole state".
- **Selected Approach**:
  - `RelayExtension.build(ExtensionContext) -> ExtensionParts`. Routes go
    under `/x/<extension name>/`.
  - The registration wire format is the relay's own, so the CLI client and
    every wrapper agree by construction. The provider supplies only the
    semantics.
  - `ExtensionRecords` is a small expiring key-value store kept in the
    relay's database, so a wrapper's pending sign-ups stay inside the one
    database without their own schema or migrations.
  - Extensions load by configuration (`FITDOCS_RELAY_EXTENSIONS`) or
    programmatically (`create_app(extensions=...)`).
- **Rationale**: the relay side of registration stays out of scope (no
  verification, delivery or pages here). Without records, a wrapper would
  need its own migrations and a second migrate step, which is the
  "patching" the brief rules out.
- **Trade-offs**: the record store is one more pair of backend operations
  under conformance. The seam is a breaking-change surface, so it is
  versioned (`SEAM_VERSION = 1`) and its signatures are pinned.

### Decision: this repository builds the image in CI and publishes none
- **Alternatives Considered**: publishing a versioned image from CI.
- **Selected Approach**: deployments build from a pinned commit (context
  `relay/`). CI builds the image and smoke-runs it on both backends, and
  pushes nothing.
- **Rationale**: there are no registry credentials, no `id-token`, and no
  image-redistribution obligation in CI (consistent with `ci.yml`'s
  "Publishes nothing"). The distribution amendment reduces to the release
  exclusion.

### Decision: `fitdocs disconnect` is general, and relay instances revoke remotely
- **Selected Approach**:
  - A relay instance revokes its stored token with one call, then removes
    the file.
  - Personal-key and login instances remove the file only.
  - `NONE` has nothing to disconnect.
  - The reserved browser style is refused until strava-publish drives it.
- **Rationale**: the brief asks for token revocation from the CLI.
  strava-publish and relay-intervals both plan a "CLI disconnect". One
  command with per-style behaviour is the seam they extend.

### Decision: a bare `fitdocs pull` selects only pulling instances
- **Selected Approach**: without names, the CLI selects instances whose
  connector declares `PULL_ACTIVITIES` or `PULL_WELLNESS`. Named instances
  keep today's behaviour. An empty selection with configured instances
  prints "No configured connector instance pulls activities or wellness;
  nothing to pull." `run_pull` is unchanged, so its pinned instance-error
  test stays green.

### Generalization, build-vs-adopt, simplification
- **Generalization**:
  - One envelope codec serves every route and every later target.
  - `RelayClient` is mode-agnostic: the caller supplies the `HttpClient`.
  - The storage protocol is a union of per-area protocols, so a later spec
    adds an area and both backends implement it.
- **Adopt**: Starlette and uvicorn (ASGI), psycopg 3 with psycopg-pool, the
  standard library's `sqlite3`, `hmac` and `secrets`, and RFC 8628 as the
  registration pattern.
- **Build**: the migration runner, the envelope codec and the JSON log
  formatter (each small; adopting would add dependencies).
- **Simplified away**:
  - no in-repo "feature plugin" registry: later specs add their routes to
    `routes.py` and their target ids to `OFFERED_TARGETS`;
  - no extension migrations;
  - no pepper rotation (documented as invalidating every token);
  - no token `last_used_at`;
  - no `--yes` on operator deletes.

### Decision: relay-server takes the contract version for `fitdocs disconnect` (R13.1)
- **Context**: `docs/ownership-contract.md:895-906` says of the credentials
  store that "fitdocs never deletes it or anything in it", and that
  `connect` and a credential-renewing `pull` are its only writers.
  `fitdocs disconnect` removes a credentials file, so the stated guarantee
  changes.
  - Precedent: connectors raised the version from 5 to 6 when connect and
    pull changed what fitdocs writes (`src/fitdocs/contract.py:387-398`).
- **Selected Approach**:
  - Rewrite the bullet, and add a `disconnect` overwrite entry.
  - Take `CONTRACT_VERSION` main + 1 at landing, with an appended literal
    history. This overrides R6 for this spec, by controller ruling.
  - Regenerate the declaration goldens, and carry a wiki-contract
    amendment.
  - The wording holds in either landing order with publish-core, which
    also takes main + 1.
  - strava-publish's `OAUTH_BROWSER` disconnect is covered by the same
    statement, so it adds no bump.

### Decision: canonical envelope key order (R13.4)
- **Selected Approach**:
  - An answer's keys are `envelope`, `code`, `data`, then `outcome` when
    present, in that order. `encode_answer` writes them so, with compact
    separators.
  - Decoders accept any order.
  - The design states the order once, under SharedEnvelopeCodec, and
    relay-intervals' Data Contracts cite it.

## Risks & Mitigations
- uvicorn's cooperative signal re-raise changes the exit status. Mitigation:
  own handlers in `serve`, plus a subprocess shutdown test against the
  locked version.
- SQLite file locking on network filesystems is unreliable. Mitigation: the
  serving claim uses a sidecar `flock`, and the documentation says a shared
  network filesystem is unsupported and undetectable.
- The PostgreSQL conformance run is silently skipped. Mitigation:
  `FITDOCS_RELAY_REQUIRE_POSTGRES=1` in CI turns an absent or unreachable
  URL into a failure, and `tests/test_relay_workflow.py` pins the variable.
- Shared-copy drift. Mitigation: the byte-equality test in the root suite,
  plus an orphan check on `shared/`.
- Wrapper misuse of the registration format. Mitigation: the core validates
  every provider answer before encoding it, and answers `relay-failure`
  otherwise.

## References
- [RFC 8628: OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628), the polling and user-code pattern
- [Starlette release notes](https://github.com/encode/starlette/blob/main/docs/release-notes.md), the 1.0 removals and lifespan
- [uvicorn release notes](https://github.com/encode/uvicorn/blob/master/docs/release-notes.md), graceful shutdown and signal handling
- [psycopg on PyPI](https://pypi.org/project/psycopg/) and [psycopg-pool on PyPI](https://pypi.org/project/psycopg-pool/), versions and licence
