# Implementation Plan

Two streams meet in the integration group:
- **relay**: tasks 2.x to 5.x, the relay package, in order;
- **fitdocs**: tasks 6.x, the client side, in order.

The foundation group (1.x) lands first, in order. After it:
- group 6 depends only on group 1, and may run alongside groups 2 to 5 in
  its own worktree;
- 6.8 also waits on 4.6;
- 8.1 may run any time after 1.3.

Group 7 integrates and validates. Group 8 carries the documentation, gates,
steering and amendments.

Rules for every task:
- **Both suites stay green.** Each task leaves both suites green on its own:
  - the root gates: `uv run pytest`, `uv run ruff check .`,
    `uv run ruff format --check .` and `uv run mypy`;
  - from 1.3 on, the relay's own gates: `uv run --directory relay pytest`,
    ruff and mypy.
- **Every new assertion names the mutation it dies on** (tech.md, Testing).
  Run that mutation before reporting the task done.
- **Version pins are literals.** `ENVELOPE_VERSION = 1`, `SEAM_VERSION = 1`
  and `DEPLOY_CONTRACT_VERSION = 1` are pinned as literals, never derived
  from the live constant.
  - A later bump appends a new literal pin, and the old pins stay.
  - This spec changes neither `CONTRACT_VERSION` nor `DOC_VERSION`.
- **PostgreSQL is exercised, never skipped.** Every storage task and every
  later relay task that touches storage runs the relay suite twice:
  - without the test URL (PostgreSQL cases skip);
  - with the URL and `FITDOCS_RELAY_REQUIRE_POSTGRES=1` (PostgreSQL cases
    run, and an unreachable server fails).

  The task's branch CI run (`relay.yml`) must also be green. Local recipe,
  either one:
  - Docker, matching CI: `docker run --rm -d --name relay-pg -p 55432:5432
    -e POSTGRES_PASSWORD=relay-test postgres:17`, then
    `FITDOCS_RELAY_TEST_POSTGRES_URL=postgresql://postgres:relay-test@127.0.0.1:55432/postgres`;
  - Homebrew `postgresql@16`: `brew services start postgresql@16` and
    `createdb fitdocs_relay_test`, then
    `FITDOCS_RELAY_TEST_POSTGRES_URL=postgresql:///fitdocs_relay_test`.

  CI pins PostgreSQL 17. The Homebrew 16 run is a convenience, not the
  reference.
- **The website is not edited** (controller ruling R9). Site copy is the
  follow-up item `.kiro/queue/2026-10-31-relay-server-site-copy-at-next-release.md`.
- **Amendments** to other specs take the next free amendment number at
  landing.
- **Documentation constraints**: no new document names a hosting provider,
  an email provider or a deployment's infrastructure. Nothing under `docs/`
  carries the fitdocs release version literal.

- [ ] 1. Foundation: shared modules, the relay package skeleton, the cross-check and CI

- [ ] 1.1 Add the closed relay code vocabulary to the fitdocs source
  - The 22 codes from design.md, in their order, each with:
    - a fitdocs-written explanation;
    - a fixed HTTP status (none for the two client-observed codes);
    - its origin.

    The module imports only the standard library: no `http`, and nothing
    from `fitdocs`.
  - Register the module in the connectors boundary guard, with an empty
    import set.
  - Done when the vocabulary test passes. It pins the 22 values in order as
    a literal prefix, and checks that every code has an explanation and
    that a status is present exactly when the origin is the relay. Its
    named mutations:
    - swapping two codes reds the prefix pin;
    - giving a client-origin code a status reds the status rule;
    - deleting one explanation reds the completeness check.
  - _Requirements: 4.2, 4.3, 4.10, 15.6_

- [ ] 1.2 Add the envelope v1 codec beside the vocabulary
  - Define the envelope version, the served versions, the route paths, and
    the field formats and bounds from design.md:
    - token, user code, poll secret, target id and email;
    - the interval and expiry bounds, the slow-down step, and the size
      limits.
  - Encode and decode answers and requests strictly. Refuse duplicate keys,
    `NaN`, unknown top-level keys, a boolean envelope, a client-origin code
    and an oversize body.
  - `outcome` is the one optional top-level key: absent, or a non-empty
    string.
    - This spec validates only its shape.
    - Membership in publish-core's vocabulary is checked by whichever spec
      pins `outcomes.py` into the relay (strava-publish).
  - Parse the capabilities, started, issued, retry-after and envelopes data
    sets exactly.
  - The module imports the vocabulary only through a relative import.
    Register it in the boundary guard with that one import.
  - Done when the codec test passes for every rule, including:
    - an answer carrying `outcome` decodes with it preserved;
    - an empty-string `outcome` is malformed.

    Named mutations that must each red a test:
    - removing the unknown-key rule;
    - rejecting `outcome` as an unknown key;
    - accepting `True` as envelope 1;
    - accepting an interval of 61 seconds;
    - accepting a user code with a vowel.
  - _Requirements: 4.1, 4.4, 4.5, 4.6, 4.7, 15.6_

- [ ] 1.3 Scaffold the relay package with its own manifest, lock and boundary guard
  - Create the relay package in the relay directory:
    - distribution `fitdocs-relay` 0.1.0, import name `fitdocs_relay`,
      Python 3.11 or later;
    - runtime dependencies Starlette and uvicorn, at the design's floors;
    - the `postgres` extra (psycopg with binary and pool);
    - a dev group (pytest, httpx, ruff, mypy);
    - the `fitdocs-relay` console script entry (a stub printing usage until
      5.2);
    - its own ruff, strict mypy and pytest configuration;
    - its own lockfile, a short README pointing at the docs page to come,
      and a changelog skeleton;
    - an ignore file under the relay directory for local `*.db`,
      `*.db-wal`, `*.db-shm` and `*.serve-lock` files.
  - Add the relay boundary guard:
    - no module imports `fitdocs`;
    - SQL drivers only in their backend modules;
    - Starlette and uvicorn only in their allowed modules;
    - shared copies import only the standard library and relative siblings.

    Positive controls on synthetic sources prove each rule can fail.
  - Done when:
    - `uv sync --directory relay --locked --extra postgres` installs;
    - the relay suite (boundary guard only) passes;
    - the root suite, ruff, format and mypy are unchanged and green;
    - the root `uv.lock` is untouched.
  - _Requirements: 1.1, 1.6_

- [ ] 1.4 Pin the shared modules into the relay and add the cross-check
  - Add the sync script, with its table of (source, copy) pairs listing
    exactly the two shared modules. strava-publish appends the
    `outcomes.py` pair (R9). It writes byte-identical copies into the relay's
    `shared` package, and its check mode exits 1 listing drift.
  - The `shared` package marker states that the copies are never edited by
    hand.
  - Add the root cross-check test. It asserts:
    - byte equality for every pair;
    - no orphan module in `shared`;
    - standard-library-only sources;
    - relay-server's two pairs present, by literal.

    Its failure message names the sync command. Add it to the root mypy
    file list.
  - Done when:
    - the relay can import both copies;
    - the cross-check passes;
    - appending one byte to a copy reds it;
    - adding a hand-written module to `shared` reds the orphan check;
    - deleting a pair from the table reds the literal check.
  - _Requirements: 4.9, 1.6_

- [ ] 1.5 Add the relay CI workflow and its pins
  - A separate workflow on every push and pull request, with
    `contents: read`. It runs one relay job:
    - a PostgreSQL 17 service container pinned by digest, with a
      `pg_isready` health check;
    - pinned checkout and setup-uv actions, and the Python floor;
    - a locked sync with the `postgres` extra;
    - the relay tests with the test PostgreSQL URL and the
      require-PostgreSQL flag set;
    - ruff, format and mypy in the relay.
  - The image steps arrive in 5.3.
  - Add the root workflow pin test, and add it to the root mypy file list.
    It pins:
    - triggers and permissions;
    - no publish, registry login, push or `id-token` anywhere;
    - every action pinned to a version or SHA;
    - the service image pinned by digest, with its health check;
    - the require flag on the test step.
  - Done when:
    - the pin test passes;
    - removing the require flag from the YAML text in memory reds it;
    - changing the service image to an unpinned tag reds it.
  - _Requirements: 1.5, 7.6_

- [ ] 2. Relay storage: configuration, the interface, and each storage area on both backends

- [ ] 2.1 Read configuration only from the environment against the contract table
  - Define the deploy contract's environment table: each variable's name,
    whether it is required, its default, whether it is secret, and its
    meaning, exactly as in design.md. Also define the contract version
    constant and the image constants.
  - Build the one configuration reader:
    - database URL parsing (relative or absolute SQLite paths;
      `postgresql://` and `postgres://`; in-memory SQLite refused);
    - the separate password variable's rules;
    - a pepper of at least 43 characters;
    - port, limit and grace ranges;
    - log levels and extension references;
    - refusal of any unknown variable with the relay prefix.
  - Every error names the variable and never prints a secret value.
  - Done when the config tests pass. Each rule is exercised, including an
    unknown prefixed variable refused and a planted secret value absent from
    every error message. Named mutations:
    - lowering the pepper minimum to 42;
    - dropping the unknown-variable check.
  - _Requirements: 2.7, 7.2, 9.2, 9.3, 9.4_

- [ ] 2.2 Define the storage interface and the conformance harness
  - The value types, errors and per-area protocols from design.md, composed
    into one storage protocol. Storage takes `now` as an argument and never
    reads a clock.
  - The protocols:
    - `StorageBase` (`backend`, `ping`, `close`) as the base of every area
      protocol;
    - the empty SQLite and PostgreSQL backend classes.
  - The typing rule: until 2.6, each fixture and test types a backend by
    the area protocol it exercises, and `migrate` and `pending` take the
    narrow `SchemaStore`, which carries `backend` through `StorageBase`.
    Only 2.6, which completes every area, assigns a backend to the full
    storage protocol. A backend never satisfies a protocol with methods
    that raise `NotImplementedError`.
  - The conformance harness:
    - a backend fixture that yields SQLite on a temporary file, and
      PostgreSQL on a fresh schema per test from the test URL;
    - a skip with a stated reason when the URL is unset;
    - a failure instead of a skip when the require flag is set.
  - The coverage marker, and a check that every marker names a real
    storage protocol member. The completeness half lands in 2.6, so the
    suite stays green in between.
  - Done when:
    - the marker check passes, and a marker naming a non-member reds it;
    - with the require flag set and no URL, a PostgreSQL-parametrized
      sentinel test fails, and unsetting the flag skips it;
    - with the URL and the flag set against a local PostgreSQL, the
      sentinel passes;
    - the branch CI run is green.
  - _Requirements: 7.1, 7.5, 7.6_

- [ ] 2.3 Apply schema changes in order on both backends
  - The numbered schema-change discovery: contiguous from 1, one directory
    per backend.
  - Schema change `0001` for SQLite and for PostgreSQL, with identical file
    names: the version table, principals, tokens with a cascading foreign
    key, rate counts and records, as in the data model.
  - A parity test that reds when the two directories' names differ.
  - Both backends' `StorageBase` members (`backend`, `ping`, `close`),
    with coverage markers. Fixture teardown closes through them from here
    on.
  - Both backends' schema-state and apply-change operations. Each change
    and its version row commit together, after the backend's writer lock is
    taken (`BEGIN IMMEDIATE`, or a transaction-scoped advisory lock) and the
    current version is re-read.
  - SQLite opening: WAL, foreign keys, the busy timeout, a SQLite version
    check (at least 3.35), and a new file at mode 0600.
  - PostgreSQL opening: a capped pool, with the password passed separately.
    Connection errors become the unreachable error and other driver errors
    the storage error, never carrying the driver's message.
  - The migrate and pending functions, typed against `SchemaStore`, and
    the migration report. A database newer than the build raises the
    schema-ahead error.
  - Conformance tests on both backends, marked with the operations they
    cover:
    - a fresh migrate reaches the expected version;
    - a second run changes nothing;
    - a newer database is refused unchanged;
    - a failing change leaves the last applied version;
    - two concurrent migrations apply each change once;
    - `ping` succeeds while the store is open and raises the unreachable
      error once it is closed.
  - Done when:
    - these tests pass without the URL (SQLite only), and with the URL and
      the require flag set (both backends);
    - adding a stray file to one migrations directory reds the parity test;
    - the branch CI run is green.
  - _Requirements: 1.2, 1.3, 8.1, 8.2, 8.3, 8.4, 8.5, 8.7, 9.5_

- [ ] 2.4 Store principals and tokens on both backends
  - Principals: create; get; list (by creation time, then id); delete,
    which cascades the principal's tokens in one transaction.
  - Minting: for an existing principal, or for a new principal in the same
    transaction. An unknown principal and a duplicate identifier are typed
    errors.
  - Tokens: find; list (without verifiers); revoke, reporting revoked,
    already revoked or unknown, and never undone.
  - PostgreSQL uses `FOR UPDATE` wherever a read precedes a write.
  - Done when the principal and token conformance tests pass on both
    backends with the URL and the require flag set, are marked covered, and
    the branch CI run is green. The tests include:
    - cascade on delete;
    - a mint with a new principal rolled back when the token insert fails;
    - revocation idempotent and reported.
  - _Requirements: 2.5, 7.4_

- [ ] 2.5 Count rate limits, keep wrapper records and claim the serving instance on both backends
  - Fixed-window request counting returns the count, plus the seconds to
    the window's end once the limit is exceeded. It deletes ended windows.
    PostgreSQL counts with insert-on-conflict and returning.
  - Namespaced records with an expiry: put, get, take (atomic
    read-and-delete; PostgreSQL uses delete-with-returning) and delete.
    Expired records are invisible, and put purges them.
  - The serving claim:
    - SQLite: an exclusive non-blocking lock on a sidecar lock file;
    - PostgreSQL: a session advisory lock keyed by the current schema, on a
      dedicated connection.

    A second claim while one is held answers `None`, and release frees it.
  - Done when those conformance tests pass on both backends with the URL
    and the require flag set, are marked covered, and the branch CI run is
    green. The tests include: expired windows and records removed; a second
    claim from a separate storage object refused; release, then reclaim,
    succeeds.
  - _Requirements: 6.3, 6.4, 7.8, 9.6, 10.3_

- [ ] 2.6 Prove both backends equal under concurrency, complete the coverage rule and select the backend by URL
  - Concurrency conformance on both backends:
    - 20 threads counting one key total exactly 20;
    - exactly one thread wins a take;
    - a revocation racing a token lookup never yields an active token after
      the revocation returns;
    - concurrent mints with one id yield exactly one duplicate error.
  - The coverage check's completeness half: every storage protocol member
    is named by at least one coverage marker.
  - Both backend classes are now typed as the full storage protocol.
  - The factory opens the configured storage:
    - a SQLite target opens SQLite;
    - a PostgreSQL target imports its backend lazily;
    - missing PostgreSQL support raises an error naming the `postgres`
      extra.
  - Done when, with the URL and the require flag set, every conformance
    test passes on both backends, and the branch CI run is green. Also:
    - deleting one operation's only marker reds the completeness check;
    - removing the transaction lock from either backend's count operation
      reds the 20-thread test;
    - the missing-extra case, simulated by blocking the driver import,
      names the extra.
  - _Requirements: 1.2, 1.3, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 9.6_

- [ ] 3. Relay domain services

- [ ] 3.1 (P) Mint, verify and revoke relay tokens
  - Token format `fdr1_<id>_<secret>` with base32 parts drawn from
    `secrets`. Principal ids carry their prefix.
  - The keyed verifier over the id and secret, compared in constant time.
    An unknown id still computes one dummy verifier.
  - Authentication answers:
    - missing gives `token-missing`;
    - malformed, unknown or mismatched gives `token-unknown`;
    - revoked gives `token-revoked`;
    - a deleted principal's former token gives `token-unknown`.
  - Mint retries generation once on a duplicate identifier. The minted
    value is returned once and is hidden from `repr`.
  - Done when the identity tests pass. They show the stored record holds
    only the verifier, and that a database copy plus a wrong pepper
    authenticates nothing. Named mutations:
    - replacing the constant-time compare with `==` reds a test that spies
      on the compare function;
    - dropping the revoked check reds the revoked-token test.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6_
  - _Boundary: IdentityService_
  - _Depends: 2.6_

- [ ] 3.2 (P) Limit requests per token and per client
  - Token keys from the token id. Client keys are a keyed hash of the
    address, and an absent address shares one key.
  - Limits come from configuration, in one-minute windows.
  - Done when the rate-limiter tests pass on SQLite. They show:
    - the 61st request in a window is refused with the seconds to wait;
    - the stored key never contains the raw address;
    - a new window allows again.
  - _Requirements: 6.1, 6.3_
  - _Boundary: RateLimiter_
  - _Depends: 2.6_

- [ ] 3.3 (P) Write secret-free structured logs to standard output
  - A JSON-lines formatter with the design's fields.
  - A redacting filter for anything matching the token format, the pepper,
    or the database password.
  - Unexpected failures are logged as their type and frame list only.
  - uvicorn's loggers are routed through the formatter.
  - Done when the log tests pass. They show:
    - a record built from a message containing a planted token, pepper and
      password prints none of them;
    - a failure record carries no exception message.

    Named mutation: removing the filter reds the planted-token test.
  - _Requirements: 9.8, 9.9_
  - _Boundary: RelayLogs_

- [ ] 4. Relay HTTP: the envelope server, probes, core routes and the seam

- [ ] 4.1 Serve envelope answers through the request pipeline
  - The answer helper:
    - the status from the vocabulary;
    - `Cache-Control: no-store`;
    - a retry header on rate-limited answers;
    - refusal to emit a client-origin code.
  - Bearer-token and client-address helpers, and a strict request reader.
  - The app factory skeleton with the lifespan and the middleware:
    - the body limit;
    - the version-prefix check (an unserved version answers
      `envelope-unsupported` with the served versions);
    - an unmatched path answers `not-offered`;
    - an unexpected exception answers `relay-failure`, and an unreachable
      store answers `unavailable`;
    - one request log record per request, with a server-generated request
      id.
  - Done when route tests through the test client show each pipeline answer
    and its status, and the log record per request carries the route
    template and code but no path or query.
  - _Requirements: 4.1, 4.5, 4.6, 4.7, 4.8, 4.10, 9.9_
  - _Depends: 3.1, 3.2, 3.3_

- [ ] 4.2 Answer liveness and readiness, and gate the API on readiness
  - Liveness answers `ok` with no database access.
  - Readiness pings, reads the schema state, and answers `ok`,
    `storage-unreachable`, `schema-behind` or `schema-ahead`, with the
    schema numbers. It refreshes the readiness flag.
  - While not ready, every versioned route answers `unavailable`.
  - Done when tests show four things:
    - an unmigrated database gives readiness `schema-behind` and
      `unavailable` on the API;
    - migrating then probing readiness restores service;
    - a newer schema gives `schema-ahead`;
    - a closed store gives `storage-unreachable` while liveness stays `ok`.
  - _Requirements: 9.5_

- [ ] 4.3 Serve the capabilities, token-check and token-revocation routes
  - Capabilities (unauthenticated, limited per client):
    - the served envelopes;
    - whether registration is offered;
    - the offered target ids (an empty tuple that later specs append to).
  - The token check answers `ok` or the token code, and changes nothing.
  - Revocation revokes the presenting token.
  - Authenticated requests are limited per token. Failed authentications
    count per client before answering.
  - Done when route tests show:
    - capabilities with no target and registration false;
    - a revoked token answering `token-revoked` on the next request;
    - a missing token answering `token-missing`;
    - the 61st request answering `rate-limited` with its header and data.
  - _Requirements: 2.3, 2.4, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2_

- [ ] 4.4 Expose the versioned wrapper seam
  - The seam surface from design.md:
    - the seam version;
    - extension, context and parts;
    - token issuance through the same token service the operator uses;
    - namespaced records with key, value and expiry limits;
    - the registration provider and its answer types;
    - the envelope response helper;
    - extension loading from the configured references.
  - The app factory refuses, naming the extension and the reason:
    - a mismatched seam version;
    - a duplicate or invalid name;
    - a route outside `/x/<name>/`;
    - a second registration provider.
  - Browser-facing extension routes are served outside the envelope.
  - A surface pin test fixes the seam version as a literal and the names
    and signatures of the surface.
  - Done when seam tests show each refusal, a test extension's routes
    served under its prefix, records isolated per extension name, and
    issued tokens authenticating. Named mutation: changing one seam
    signature reds the surface pin.
  - _Requirements: 4.11, 10.1, 10.2, 10.3, 10.7, 10.8_

- [ ] 4.5 Serve the registration routes through an installed provider
  - Start reads exactly an email. Poll reads exactly a poll secret.
  - Provider answers are validated before encoding:
    - user code, poll secret, interval and expiry bounds;
    - an issued token must authenticate to its stated id.

    An invalid answer gives `relay-failure`, logged by type only.
  - Capabilities advertise registration exactly when a provider is
    installed. Without one, both routes answer `not-offered`.
  - Registration requests are limited per client.
  - Done when tests with a scripted test provider show:
    - each answer code and its data;
    - a provider returning a vowel user code or a foreign token answers
      `relay-failure`;
    - no email or poll secret appears in captured logs.
  - _Requirements: 5.6, 6.1, 10.4, 10.5, 10.6, 10.9_

- [ ] 4.6 Record the envelope exchanges and replay them against the relay
  - The recorded exchanges file covers at least one exchange per route and
    one per relay-origin code, with visibly fake tokens (all `a`).
  - The relay suite seeds state (a known pepper and token, and a test
    provider), replays each request, and asserts each answer's status and
    bytes.
  - Done when the replay passes, and editing one recorded answer byte reds
    it.
  - _Requirements: 4.1, 4.3, 4.5_

- [ ] 5. Relay process, operator commands and the image

- [ ] 5.1 Run one serving instance with graceful shutdown
  - The server runner, in order:
    - opens storage and claims serving, returning 1 when the claim is held;
    - installs its own termination and interrupt handlers;
    - runs uvicorn with the configured host, port, proxy-header trust,
      lifespan on, its access log off, and the shutdown grace;
    - releases the claim and closes storage.
  - Done when subprocess tests show two things:
    - a termination signal during a slow in-flight request (served by a
      test extension) completes that request and exits 0;
    - a second serve against the same SQLite file exits 1 while the first
      runs.
  - _Requirements: 1.2, 9.6, 9.7_

- [ ] 5.2 Provide the operator commands
  - The commands are serve, migrate (with check mode), principal create,
    list and delete, token mint, list and revoke, and new-pepper. The design
    fixes their outputs, ordering and exit codes (0, 1, 2, 3).
  - Mint prints the token alone on standard output, and the ids on
    standard error. Listings never show a token value or verifier.
  - Every command except migrate and new-pepper first requires the current
    schema. No command prints a secret.
  - Done when CLI tests show:
    - each command's output and exit code;
    - check mode exiting 3 before migration and 0 after;
    - an unknown id exiting 1 with nothing changed;
    - a planted password and pepper absent from all output.
  - _Requirements: 2.2, 3.1, 3.2, 3.3, 3.4, 3.6, 3.7, 8.1, 8.6_

- [ ] 5.3 Define the image and smoke-run it in CI
  - A two-stage image definition:
    - the build stage uses uv pinned by digest, with a locked, non-dev
      install including the `postgres` extra, plus the licence collection
      script;
    - the runtime stage uses the slim Python base pinned by digest, with a
      numeric non-root user, an empty owned data directory, the listen
      address set for containers, the documented port, the entrypoint
      `fitdocs-relay` with `serve` as the default command, no secret
      variable, no volume and no database file.
  - An ignore file.
  - A static image test that pins each rule, with mutations proving that a
    tag-only base and a root user each red it.
  - The smoke script, run for SQLite and for PostgreSQL. Each run migrates,
    serves detached, probes both endpoints, stops with SIGTERM (asserting
    exit 0), and scans the logs for planted secrets.
  - Add the build and smoke steps to the relay workflow, without push or
    login, and extend its pin test.
  - Done when:
    - the image builds locally;
    - both smoke runs pass;
    - the licence directory lists the installed distributions;
    - the workflow pin test requires the build step and forbids push.
  - _Requirements: 9.1, 9.11_

- [ ] 5.4 Pin the deploy contract and tie its version to the relay changelog
  - A contract pin test fixes, as literals: the contract version, the full
    environment table, the probe paths, the image user, port and
    entrypoint, and the command list.
  - The relay changelog's newest section names deploy contract 1,
    envelope 1 and seam 1, and a test reds when any constant differs from
    the section.
  - Done when:
    - the pins pass;
    - adding an environment row without updating the pin reds;
    - bumping a version constant without a changelog line reds.
  - _Requirements: 9.10, 9.12_

- [ ] 6. fitdocs client: the relay connector, connect, register and disconnect

- [ ] 6.1 (P) Admit the relay authentication style into the connector framework
  - Append the relay-token style, mark it supported, and add the relay value
    types and the relay operation protocol from design.md.
  - Registry:
    - an empty capability set is allowed only for the relay style;
    - the five relay operations are required for it.
  - Credentials: the relay style resolves exactly like a personal key,
    including the environment override.
  - The store gains a remove operation that touches only the named file.
    The connect engine's override report covers the relay style.
  - Update the pins this changes:
    - in `tests/connectors/test_protocol.py:220-236`, the `AuthStyle` value
      set (adding `relay-token`), its length from 4 to 5, and
      `SUPPORTED_AUTH_STYLES`;
    - the published surface and its `EXPECTED_ALL` pin;
    - the boundary import set for `protocol`.
  - Done when the protocol, registry, credentials, surface and boundary
    tests pass. They show:
    - a relay connector lacking one operation is rejected, naming it;
    - a non-relay connector with no capability is still rejected;
    - the override variable satisfies a relay token with nothing stored.
  - _Requirements: 11.3, 11.4, 14.7_
  - _Boundary: ProtocolAmendment, RegistryAmendment, CredentialsAmendment_
  - _Depends: 1.2_

- [ ] 6.2 Provide the relay connector and the envelope client
  - The `relay` connector:
    - optional `url` defaulting to `https://api.fitdocs.ai`;
    - URL rules: `https`, or `http` to loopback only; absolute; no query,
      fragment or userinfo; trailing slash stripped;
    - one secret token field;
    - no capability;
    - the five relay operations, each one client call through the session's
      transport.
  - The envelope client:
    - sends the token only as an unredirected credential header;
    - never raises for an answer;
    - maps transport failure to `relay-unreachable`;
    - maps a non-envelope body to `rate-limited` (429), `unavailable`
      (5xx) or `answer-malformed`;
    - exposes data only for parsing.
  - Its `post(route, fields)` carries no per-request attempt flag.
    strava-publish extends it for the publish call (R9).
  - Register the connector at package import. Add the module's
    boundary-table row (`relay`: errors, http, protocol, secrets,
    relay_codes, relay_envelope) and its `CONNECTORS_MODULE_NAMES` entry,
    which `tests/connectors/test_boundary.py:128` enforces.
  - Add the neutral-scan exemption entry for its address, in the intervals
    entry's form, listing the connector module and its test modules. An
    entry is exercised when at least one listed path names the host
    (`_unexercised_exemptions`). The documentation section's key joins the
    entry in 8.4.
  - Done when the connector tests with the fake transport show:
    - each URL rule and each fallback mapping;
    - the token absent from any URL and present only in the credential
      header;
    - the registration answers parsed into the protocol types.
  - _Requirements: 11.1, 11.2, 15.2, 15.3, 15.5_

- [ ] 6.3 Connect with a pasted relay token
  - Refuse a value outside the token format before any request.
  - Make exactly one token check in authentication mode. On `ok`, store the
    token atomically, replacing without revoking.
  - On any other answer, return the code, its fitdocs explanation and a
    next step per code, storing nothing.
  - The token is registered for redaction before use.
  - Add the module's boundary-table row (`relay_connect`: credentials,
    http, protocol, secrets, settings, relay_codes, relay_envelope) and its
    module-list entry.
  - Done when engine tests show:
    - a scripted 503 and a scripted 429 each produce exactly one transport
      call (named mutation: building the client in `CallMode.DATA` reds
      both);
    - nothing is stored after each failure code and after an unreachable
      relay;
    - a replaced token is never revoked;
    - the explanation and next step come only from fitdocs text, even when
      the scripted relay body carries extra strings.
  - _Requirements: 12.2, 12.3, 12.4, 12.6, 15.2, 15.4_

- [ ] 6.4 Register against a relay that advertises registration
  - Read capabilities first. Without registration, return `not-offered`
    with the ask-the-operator next step.
  - Start with the email. Validate the started answer, report it through
    the callback, and compute the local deadline from the injected clock.
  - Poll once per interval:
    - slow-down adds the fixed step, capped at the maximum;
    - issued stores the token as a paste would;
    - every other code, an unreachable relay or a malformed answer stops
      with its code;
    - passing the deadline gives `registration-expired`;
    - an interrupt from sleep propagates with nothing stored.
  - The poll secret is registered for redaction and never stored. The
    email is never stored.
  - Done when engine tests with a scripted transport and a fake clock and
    sleep show:
    - each path, the slow-down step and the deadline;
    - the credentials file absent after every non-issued ending;
    - the capabilities read, the start and a poll, each scripted to a 503
      and to a 429, each make exactly one transport call (named mutation:
      `CallMode.DATA`);
    - dropping the deadline check makes the expiry test loop until the fake
      clock's guard fails it.
  - _Requirements: 13.1, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9, 13.10, 15.2, 15.4_

- [ ] 6.5 Disconnect per authentication style
  - Relay instance with a stored token: one revocation with the stored
    token.
    - `ok`, `token-unknown` or `token-revoked` removes the file;
    - anything else keeps it and returns the code with its next step.
  - Local-only: no request, the file is removed, and a note says the token
    stays valid.
  - Personal-key and login instances: the file is removed with no request,
    and a note says the credential stays valid at the service.
  - No stored file: nothing to disconnect, listing any override variable
    still set. No-auth instances: nothing to disconnect. The reserved style
    is refused as unsupported.
  - Add the module's boundary-table row (`disconnect`: credentials, http,
    protocol, secrets, settings, relay_codes) and its module-list entry.
  - Done when engine tests show:
    - each row of the design table;
    - a failed revocation leaving the file byte-identical, with no other
      file in the credentials directory changed;
    - a revocation scripted to a 503 and to a 429 each making exactly one
      transport call (named mutation: `CallMode.DATA`).
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.7, 15.2_

- [ ] 6.6 Wire relay connecting into `fitdocs connect`
  - For relay instances:
    - the no-echo token prompt;
    - `--register` with `--email`, or an interactive email prompt;
    - the email check before any request;
    - the started lines printing the typed email, the user code and the
      confirm-only-if-same instruction, with the minutes remaining;
    - success and failure lines;
    - exit codes 0, 1, 2 and 130.
  - Each of these exits 2 before any request:
    - non-interactive input without an email (naming the override
      variable);
    - `--register` or `--email` on a non-relay instance;
    - `--email` without `--register` on a relay instance.
  - Other instances behave exactly as before.
  - Done when CLI tests show each path and exit code, and the existing
    connect tests pass unchanged.
  - _Requirements: 12.1, 12.5, 13.2, 13.11, 15.1_

- [ ] 6.7 Add `fitdocs disconnect`, keep relay instances out of a bare pull, and raise the command-count pins
  - The disconnect command takes the shared preflight. An unknown name
    exits 2, naming the configured instances. It prints each result and its
    exit code.
  - A bare pull selects only instances whose connector pulls activities or
    wellness. When that selection is empty while instances exist, it prints
    the distinct nothing-to-pull line. Named pulls and `run_pull` are
    unchanged.
  - Raise the registered-command count pins to main + 1 at landing, as
    literals (R9). publish-core also adds a command, so the value is 16
    with "Sixteen" if this lands first, and 17 with "Seventeen" otherwise.
    The pins are:
    - `tests/test_cli_skill.py:266-268`;
    - `tests/index/test_cli_index.py:609`;
    - `tests/query/test_cli_query.py:811-812`;
    - the count word in the cli.py module docstring.
  - Done when CLI tests show:
    - a bare pull with a relay and a folder instance pulls the folder and
      exits 0, without contacting the relay;
    - a bare pull with only a relay instance prints the distinct line and
      exits 0;
    - a named relay instance with no stored token reports not connected,
      and with a stored token reports that it pulls nothing, neither making
      a request;
    - every existing pull test passes unchanged;
    - the three count pins pass at the new literal.
  - _Requirements: 11.5, 11.6, 14.6, 15.1_

- [ ] 6.8 Decode the recorded exchanges through the fitdocs client
  - Feed every recorded answer from 4.6 through the envelope client with a
    fake transport. Assert the decoded code and the parsed data for each
    route.
  - Done when the decode test passes, and editing one recorded field so it
    falls outside its format reds it.
  - _Requirements: 4.4, 15.3_
  - _Depends: 4.6_

- [ ] 7. Integration and validation

- [ ] 7.1 Prove the fitdocs side stays offline and confined with a relay configured
  - Add a configured relay instance to the wired root of the socket-guarded
    offline-commands test. Every listed command still makes no request.
  - Add confinement cases: registration and disconnect write nothing under
    the data root, and touch only the instance's credentials file.
  - A bare pull with only a relay instance, run under the socket guard:
    assert exit 0 and the distinct nothing-to-pull line.
  - Done when those tests pass. Named mutation: removing the bare-pull
    filter makes the relay-only case exit 1, with the instance error and
    without the distinct line. The socket guard alone cannot catch it,
    because that path makes no request either way.
  - _Requirements: 11.6, 14.7, 15.1_
  - _Depends: 6.7_

- [ ] 7.2 Exercise the relay end to end with planted secrets
  - Run one full exercise against an app that serves while operator
    commands run against the same SQLite file:
    - mint by operator command, check, revoke by command, then the next
      request answers `token-revoked`;
    - registration through a test provider;
    - rate limiting;
    - a failure path.
  - Scan every captured log line for the planted token, pepper, email,
    poll secret and database password.
  - Done when the exercise passes on both backends in CI, and none of the
    planted values appears in any log line.
  - _Requirements: 3.5, 9.8_
  - _Depends: 5.2_

- [ ] 8. Documentation, gates, steering and amendments

- [ ] 8.1 (P) Exclude the relay from the release by gate
  - Add `relay/*` and `fitdocs_relay/*` to the release policy's forbidden
    members.
  - Add positive controls (`relay/pyproject.toml`,
    `fitdocs_relay/__init__.py`) and a negative control
    (`src/fitdocs/connectors/relay.py`). Also check that `relay` is absent
    from the sdist allow-list.
  - Done when:
    - the artifact checker reports a forbidden member for a synthetic sdist
      carrying `relay/pyproject.toml`;
    - a real build passes the check;
    - deleting either pattern reds its positive control.
  - _Requirements: 1.4_
  - _Boundary: ReleaseExclusion_

- [ ] 8.2 Amend the technology and structure steering
  - Technology steering:
    - Architecture: "No server, no background jobs." becomes "The `fitdocs`
      CLI runs no server and no background jobs.", followed by the relay
      paragraph from design.md.
    - Network and Credentials: names the relay calls of `fitdocs connect`
      and `fitdocs disconnect`, and that relay tokens use the credential
      store.
  - Structure steering:
    - a relay server directory entry;
    - the connectors bullet adds `disconnect` and the standard-library-only
      shared modules.
  - Rewrite the network-statements test's Architecture pin to the new
    literal sentence.
  - Done when the network-statements tests pass against the new literal,
    and restoring the old sentence reds them.
  - _Requirements: 16.1, 16.2_

- [ ] 8.3 Document the relay for operators in one page, with the self-hosting guide
  - The relay page holds:
    - a self-hosting guide: a local SQLite run, building the image from a
      pinned commit, migrate then serve, minting a token, connecting
      fitdocs, switching to PostgreSQL;
    - the deploy contract v1 with the environment table;
    - the database URLs;
    - the probes and the commands;
    - stop-then-start and the one-replica rule, including the
      shared-network-filesystem limit;
    - the state rule, shutdown, logs, and TLS terminated in front;
    - the operator commands;
    - envelope v1 (routes, answer shape, code table, registration format);
    - seam v1;
    - the pepper-rotation statement;
    - that it is not governed by fitdocs's compatibility policy.
  - Add its row to the documentation index.
  - Bind the page to the code:
    - the relay suite binds its environment table and versions;
    - the root suite binds its code table to the vocabulary.
  - Done when both binding tests pass, deleting one table row reds the
    binding, and the page names no hosting or email provider.
  - _Requirements: 2.8, 9.6, 9.10, 16.4, 16.5_

- [ ] 8.4 Document the relay connector and record the changelogs
  - Rewrite the page preamble (`docs/connectors.md:12-16`).
    - It names the three built-in connectors (`folder`, `intervals`,
      `relay`).
    - It treats the relay section exactly like the intervals section: the
      framework sections outside those two describe no online service.
    - Add a pin that binds the preamble's connector list to the registry's
      built-in connector ids. Named mutation: deleting `relay` from the
      preamble reds it.
  - Add a connectors documentation section:
    - the relay connector, its URL and default;
    - the token and its override;
    - connect by paste and with `--register`;
    - disconnect;
    - what leaves the machine for each;
    - the bare-pull rule.

    Append its headings to `_EXPECTED_HEADINGS` in
    `tests/connectors/test_docs.py`; the table is append-only (R9). Add the
    section's key to the relay's neutral-scan exemption entry.
  - Append the root changelog's Unreleased entries:
    - Added: the connector, register and disconnect;
    - Changed: the bare pull, and the credentials style value.

    Each names the action. Pin them through the changelog view anchored to
    0.2.0.
  - Finalize the relay changelog entry.
  - Done when the docs, headings, preamble, neutral-scan and changelog
    tests pass with the new entries.
  - _Requirements: 16.3, 16.7_

- [ ] 8.5 Rewrite every network statement to name the relay commands
  - Each statement that lists the network-touching commands names
    `fitdocs disconnect` and the registration of `fitdocs connect` beside
    `fitdocs connect` and `fitdocs pull`:
    - `README.md` "Route maps";
    - `docs/configuration.md`, the tiles-section opener and the warm-cache
      paragraph;
    - the `cli.py` module docstring;
    - `sync.py`;
    - `tiles.py`, in three places;
    - `docs/connectors.md` "What leaves your machine", including its "No
      other fitdocs command ever makes a connector request" sentence.
  - Extend `tests/connectors/test_network_statements.py`:
    - add the connectors-page statement to the rewritten places;
    - move anchors with the new text;
    - add a predicate that requires `fitdocs disconnect` in every window,
      with one named mutation per place (dropping `fitdocs disconnect`
      there reds the pin).
  - Do not edit `website/content/` (R9). The follow-up queue item covers
    `guides/privacy-and-network.md:50-52`.
  - Done when the network-statement tests pass, and each place's mutation
    reds its pin.
  - _Requirements: 15.1, 16.8, 16.9_

- [ ] 8.6 Tell the packaged skill never to run `fitdocs disconnect`
  - Add the sentence beside the existing connect rule, and pin it next to
    the never-connect pins.
  - Done when the skill tests pass, and deleting the sentence reds the new
    pin.
  - _Requirements: 16.6_

- [ ] 8.7 Record the amendments in the affected specifications
  - Each takes the next free number at landing, worded like the earlier
    landed amendments.
  - connectors:
    - the auth styles (1.7);
    - the empty capabilities and relay operations (2.3);
    - the surface (2.7);
    - the override (4.5);
    - relay connect and the message rule (5.6, 5.7);
    - the bare pull (6.1);
    - the authentication requests (9.4);
    - the network commands (14.1, 14.4);
    - the disconnect command.
  - distribution: the release exclusion, the skill line, and no image
    published.
  - docs-site: no amendment, since the website is not edited (R9).
  - Done when the connectors and distribution requirements documents each
    carry their dated amendment naming relay-server and the pin that
    enforces it.
  - _Requirements: 1.4, 11.3, 11.4, 11.5, 14.1, 15.1_

- [ ] 8.8 Run the full validation sweep
  - Run both suites and both sets of gates, the release build and artifact
    check, the site build and checks, the pinned-copy check, and the relay
    workflow locally where possible.
  - Done when every gate is green and the sync script's check mode reports
    no drift.
  - _Requirements: 16.8_
