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
  - `CONTRACT_VERSION` takes main + 1 at landing, in task 8.8 (R13.1,
    overriding R6): 18 if this lands before publish-core, else 19. Its
    history entry is appended with the landed literals ("Raised from ``N``
    to ``N+1`` by relay-server"). `DOC_VERSION` is unchanged.
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

- [x] 1. Foundation: shared modules, the relay package skeleton, the cross-check and CI

- [x] 1.1 Add the closed relay code vocabulary to the fitdocs source
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

- [x] 1.2 Add the envelope v1 codec beside the vocabulary
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

- [x] 1.3 Scaffold the relay package with its own manifest, lock and boundary guard
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

- [x] 1.4 Pin the shared modules into the relay and add the cross-check
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

- [x] 1.5 Add the relay CI workflow and its pins
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

- [x] 2. Relay storage: configuration, the interface, and each storage area on both backends

- [x] 2.1 Read configuration only from the environment against the contract table
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

- [x] 2.2 Define the storage interface and the conformance harness
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

- [x] 2.3 Apply schema changes in order on both backends
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

- [x] 2.4 Store principals and tokens on both backends
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

- [x] 2.5 Count rate limits, keep wrapper records and claim the serving instance on both backends
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

- [x] 2.6 Prove both backends equal under concurrency, complete the coverage rule and select the backend by URL
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

- [x] 3. Relay domain services

- [x] 3.1 (P) Mint, verify and revoke relay tokens
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

- [x] 3.2 (P) Limit requests per token and per client
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

- [x] 3.3 (P) Write secret-free structured logs to standard output
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

- [x] 4. Relay HTTP: the envelope server, probes, core routes and the seam

- [x] 4.1 Serve envelope answers through the request pipeline
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

- [x] 4.2 Answer liveness and readiness, and gate the API on readiness
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

- [x] 4.3 Serve the capabilities, token-check and token-revocation routes
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

- [x] 4.4 Expose the versioned wrapper seam
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

- [x] 4.5 Serve the registration routes through an installed provider
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

- [x] 4.6 Record the envelope exchanges and replay them against the relay
  - The recorded exchanges file covers at least one exchange per route and
    one per relay-origin code, with visibly fake tokens (all `a`).
  - The relay suite seeds state (a known pepper and token, and a test
    provider), replays each request, and asserts each answer's status and
    bytes.
  - Done when the replay passes, and editing one recorded answer byte reds
    it.
  - _Requirements: 4.1, 4.3, 4.5_

- [x] 5. Relay process, operator commands and the image

- [x] 5.1 Run one serving instance with graceful shutdown
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

- [x] 5.2 Provide the operator commands
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

- [x] 5.3 Define the image and smoke-run it in CI
  - A two-stage image definition:
    - the build stage uses uv pinned by digest, with a locked, non-dev
      install including the `postgres` extra into the documented
      environment path, plus the licence collection script;
    - the runtime stage uses the slim Python base pinned by digest, with
      the environment at the same path and its `bin` first on `PATH`, a
      numeric non-root user, an empty owned data directory, the listen
      address set for containers, the documented port, the entrypoint
      `fitdocs-relay` with `serve` as the default command, no secret
      variable, no volume and no database file.
  - An ignore file.
  - A static image test that pins each rule, with mutations proving that a
    tag-only base, a root user and an environment path other than the
    contract's each red it.
  - A minimal installable wrapper package under `relay/tests/
    smoke_extension` with one route under `/x/smoke/`.
  - The smoke script, run for SQLite and for PostgreSQL. Each run migrates,
    serves detached, probes both endpoints, stops with SIGTERM (asserting
    exit 0), and scans the logs for planted secrets. A third run,
    `derived`, builds a derived image by the documented steps with that
    package, serves it on SQLite with `FITDOCS_RELAY_EXTENSIONS` naming it,
    and checks that its route answers.
  - Add the build and smoke steps to the relay workflow, without push or
    login, and extend its pin test.
  - Done when:
    - the image builds locally;
    - the three smoke runs pass;
    - the licence directory lists the installed distributions;
    - the workflow pin test requires the build step and forbids push.
  - _Requirements: 9.1, 9.11_

- [x] 5.4 Pin the deploy contract and tie its version to the relay changelog
  - A contract pin test fixes, as literals: the contract version, the full
    environment table, the probe paths, the image user, port, entrypoint
    and environment path, and the command list.
  - The relay changelog's newest section names deploy contract 1,
    envelope 1 and seam 1, and a test reds when any constant differs from
    the section.
  - Done when:
    - the pins pass;
    - adding an environment row without updating the pin reds;
    - bumping a version constant without a changelog line reds.
  - _Requirements: 9.10, 9.12_

- [ ] 6. fitdocs client: the relay connector, connect, register and disconnect

- [x] 6.1 (P) Admit the relay authentication style into the connector framework
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
    - the published surface and its `EXPECTED_ALL` pin, plus the literal
      surface count pins at `tests/connectors/test_surface.py:127`
      (`len(EXPECTED_ALL)` and its set) and `:158` (`len(__all__)`). Raise
      them by this spec's five names to main + 5 at landing (55 if this
      lands first), written as literals;
    - the boundary import set for `protocol`.
  - Done when the protocol, registry, credentials, surface and boundary
    tests pass. They show:
    - a relay connector lacking one operation is rejected, naming it;
    - a non-relay connector with no capability is still rejected;
    - the override variable satisfies a relay token with nothing stored.
  - _Requirements: 11.3, 11.4, 14.7_
  - _Boundary: ProtocolAmendment, RegistryAmendment, CredentialsAmendment_
  - _Depends: 1.2_

- [x] 6.2 Provide the relay connector and the envelope client
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

- [x] 6.3 Connect with a pasted relay token
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

- [x] 6.4 Register against a relay that advertises registration
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

- [x] 6.5 Disconnect per authentication style
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

- [x] 6.6 Wire relay connecting into `fitdocs connect`
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

- [x] 6.7 Add `fitdocs disconnect`, keep relay instances out of a bare pull, and raise the command-count pins
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

- [x] 7.1 Prove the fitdocs side stays offline and confined with a relay configured
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

- [x] 8.1 (P) Exclude the relay from the release by gate
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

- [x] 8.2 Amend the technology and structure steering
  - Technology steering:
    - Architecture: "No server, no background jobs." becomes "The `fitdocs`
      CLI runs no server and no background jobs.", followed by the relay
      paragraph from design.md.
    - Network and Credentials: names the relay calls of `fitdocs connect`
      and `fitdocs disconnect`, and that relay tokens use the credential
      store.
  - Structure steering:
    - a relay server directory entry;
    - the connectors sentence (`structure.md:71-75`) gains `disconnect` and
      the standard-library-only shared modules, appended after whatever
      clauses are present at landing.
  - Rewrite the network-statements test's Architecture pin to the new
    literal sentence.
  - Done when the network-statements tests pass against the new literal,
    and restoring the old sentence reds them.
  - _Requirements: 16.1, 16.2_

- [x] 8.3 Document the relay for operators in one page, with the self-hosting guide
  - The relay page holds:
    - a self-hosting guide: a local SQLite run, building the image from a
      pinned commit, migrate then serve, minting a token, connecting
      fitdocs, switching to PostgreSQL;
    - the deploy contract v1 with the environment table and the image's
      environment path;
    - the derived-image steps for installing a wrapper;
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
    - add the connectors-page statement to the rewritten places only if it
      is absent at landing (intervals-publish may add it first);
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
  - wiki-contract: the next free Requirement 2 criterion, stating that
    `fitdocs disconnect` removes the named instance's own credentials file
    and nothing else, plus the contract version advance (R13.1).
  - docs-site: no amendment, since the website is not edited (R9).
  - Done when the connectors, wiki-contract and distribution requirements
    documents each carry their dated amendment naming relay-server and the
    pin that enforces it.
  - _Requirements: 1.4, 11.3, 11.4, 11.5, 14.1, 15.1_

- [ ] 8.8 Advance the ownership contract for `fitdocs disconnect`
  - In the published ownership contract:
    - rewrite the credentials-store bullet (`docs/ownership-contract.md:
      895-906`). `fitdocs disconnect` removes the named instance's own
      credentials file and nothing else, which replaces "fitdocs never
      deletes it or anything in it". `connect`, a credential-renewing
      `pull` and `disconnect` are the only operations that write to or
      remove from the store, one instance's file at a time, never under the
      data root;
    - add a `disconnect` entry to "Overwrite Semantics of Every Writing
      Operation" beside `connect` (around `:1176-1180`);
    - update the version head and the "what changed" paragraph.
  - Raise `CONTRACT_VERSION` to one more than its value at landing, and
    append its history paragraph with the landed literals. The paragraph
    must read true in either landing order with publish-core.
  - Regenerate the declaration goldens, and move every literal
    current-version pin with its paragraph: the asset-write, retimed-rename,
    index contract-docs and derived-preserved tests, plus publish-core's
    pins if publish-core landed first.
  - Add (heading, phrase) pins in `tests/test_ownership_contract.py` for
    the rewritten bullet and the `disconnect` entry.
  - Append the changelog line naming the contract version change with its
    action (run `fitdocs sync` or `fitdocs regen` once to refresh the
    in-tree ownership declarations).
  - Done when the contract docs tests, declaration goldens and every
    version pin pass at the new value. Named mutations:
    - restoring "never deletes it or anything in it" reds the bullet pin;
    - deleting the `disconnect` entry reds its pin.
  - _Requirements: 14.8, 14.9, 16.7_
  - _Depends: 6.7_

- [ ] 8.9 Run the full validation sweep
  - Run both suites and both sets of gates, the release build and artifact
    check, the site build and checks, the pinned-copy check, and the relay
    workflow locally where possible.
  - Done when every gate is green and the sync script's check mode reports
    no drift.
  - _Requirements: 16.8_

## Implementation Notes
- 1.1: vocabulary-wide rules (status iff relay origin, explanation completeness) must iterate the whole registry, not the pinned 22-prefix, or a later spec's appended code escapes them; only the order/name/value pins are prefix-sliced. Explanations are pinned verbatim as literals in the test. (Round 3 was a controller-applied one-line fix verified by the reviewer's own mutation, in place of a third review round.)
- 1.2: a too-deep fixture must stay under the size limit or the size rule refuses it before the parse path (assert len < limit as the precondition). Fixed-text error rules are tested on every decoder/parser, asserting membership in copied literals, not just canary-absence. relay_envelope also exports is_target_id and the frozen Answer/CapabilitiesData/StartedData; oversize is refused by the codec with one fixed message, the relay's request-too-large comes from the pipeline's body-limit stage. (Round 3 docstring fix controller-applied, verified by reading, in place of a third review round.)
- 1.3 (controller ruling, departs from design File Structure Plan "[tool.ruff] extends ../pyproject.toml"): relay/pyproject.toml does NOT extend the root ruff config -- with extend, the root's `./relay` exclude is inherited and `--force-exclude` from relay/ finds no files. It copies target-version + select instead. Root excludes only the top-level dir via `extend-exclude = ["./relay"]` (a bare "relay" matched any nested relay/ dir). relay/.python-version pins 3.11. The relay boundary guard pins `scanned == 0` for shared/: task 1.4 MUST change it to the literal count of shared files.
- 1.4: the sync command is `SYNC_COMMAND` in scripts/sync_relay_shared.py (`uv run python -B -m scripts.sync_relay_shared [--check]`); docs must reuse that spelling. Controller ruling: the script's extra `--root PATH` option (not in design) is kept as test plumbing for the subprocess tests. Appending a shared pair (strava-publish: outcomes.py) means: append to SHARED_MODULES, run the sync, and raise relay/tests/test_boundary.py's literal shared/ count (now 3) and name list in the same commit. Only shared/__init__.py itself is exempt from the orphan rule.
- 1.5: tests/test_relay_workflow.py pins relay.yml by allow-lists at every level (top, top env, job, service, every step ⊆ {name,uses,run,env} -- no `with`, test step exact). 5.3 MUST extend these sets for its image steps rather than loosen them; the publish/login/push/upload check is a word match on run bodies, the raw-text scan is `id-token` only. postgres:17 digest from `docker buildx imagetools inspect postgres:17` (2026-11-01). (Round 4 one-token fix controller-applied, verified by the reviewer's two mutations.)
- 2.1 rulings: FITDOCS_RELAY_TEST_POSTGRES_URL / FITDOCS_RELAY_REQUIRE_POSTGRES are NOT contract variables (load_config refuses unknown FITDOCS_RELAY_*); relay tests/conftest.py (2.2) captures them once then autouse-delenvs every FITDOCS_RELAY_* name, and subprocess serve/CLI tests build env without them. load_config(environ=None) defaults to os.environ (design shows no default). FORWARDED_ALLOW_IPS refuses `*` (design: "proxy addresses"; queued for Josh). SQLite in-memory refusal is judged on the normalised Path and every component (Path() normalisation bypassed raw-string checks). (Round 3 test-only lines + dead-clause removal controller-applied, verified by the reviewer's O4/O11 mutations.)
- 2.2: relay/tests/conftest.py owns env isolation (captures the two test knobs, autouse-delenv FITDOCS_RELAY_*), the `database_target` fixture (SQLite temp path / PostgreSQL fresh schema via search_path, dropped on teardown) and the `covers("<DeclaringProtocol>.<member>")` marker; 2.3 must add a backend fixture on top of database_target, typed by area protocol, closing on teardown. Conformance tests live under relay/tests/conformance/ (coverage check: conformance/test_coverage.py). interface.py is pinned whole by an AST literal (tests/storage/test_interface.py DESIGNED) equal to design.md's block -- changing the interface means changing that literal. Backend classes are SqliteBackend/PostgresBackend (controller ruling; design's file tree says *Storage). Rejection species: pinning a projection of a design block (names/fields) lets signature/decorator/default drift survive -- pin the rendered block.
- 2.3: backends are SqliteBackend(SqliteTarget)/PostgresBackend(PostgresTarget); conftest `schema_store`/`open_schema_store` fixtures (typed SchemaStore) close via StorageBase.close before the schema drop. SQLite opens per operation with `file:<abs>?mode=rw` (a deleted file is unreachable, never recreated), splits change SQL with sqlite3.complete_statement (executescript would commit). PostgreSQL: after the xact advisory lock, re-read via pg_catalog.pg_tables, NOT to_regclass (stale catalog). is_connection_failure (controller ruling, per design) = sqlstate-less, class 08, 57P01-03, 53300, class 28 -> unreachable; everything else StorageError. The data model is pinned on both backends incl. defaults, uniqueness, FK actions, CHECK/COLLATE absence, PostgreSQL persistence and collation -- any later schema change (0002+) must extend those literals. PostgreSQL text sorts use the DB default collation; storage queries ordering by text ids must be made backend-equal (COLLATE "C"). (Round 3 verified by the controller re-running mutation N4.)
- 2.4: PostgreSQL text ordering uses COLLATE "C" (byte order = SQLite BINARY); ordering conformance tests take the `ids_sort_by_locale_here` fixture, which FAILS on a C-collation test DB (the check would be vacuous there) -- run PostgreSQL conformance on a non-C database (CI postgres:17 is en_US.utf8). conftest gains AccountStore/open_account_store/account_store, TIED_IDS/BYTE_ORDER. mint_token raises ValueError unless exactly one of principal_id/new_principal. (Round 2 test-only precondition verified by the controller on a C-locale DB.)
- 2.5: record expiry is exclusive (visible while now < expires_at; put purges expires_at <= now), matching the window rule (window_end <= now ends it); delete_record has no now and returns True for any physical row; close() never releases a serving claim (caller releases, per Serve lifecycle). SQLite claim = fcntl.flock on `<db>.serve-lock` (per open-file-description, so a second storage object in-process is refused); PostgreSQL claim = session advisory lock hashtext('fitdocs-relay:' || current_schema()) on a dedicated connection. Tests that inspect pg_locks must filter by database and key (server-wide reads flake under concurrent runs); purge rules must be tested with mixed window lengths; hash-keyed locks need a deterministic negative-key case. (Round 3 verified by the controller re-running mutation N2.)
- 2.6 (controller ruling): the count's atomicity is the single upsert statement (design Invariants), not the transaction lock; the Done-when lock-removal mutation is replaced by: splitting the upsert into an unlocked read-modify-write reds the 20-thread test on each backend, and the same split under the lock stays green. open_storage(target) -> Storage is the only factory (lazy PostgreSQL import; MissingPostgresSupport names the postgres extra); conftest `open_full_storage` gives a full Storage. Coverage completeness check skips under -k/-m or partial collection; CI's pinned bare `pytest` step keeps it live.
- 3.2: RateLimiter(storage, *, pepper, clock, token_limit, client_limit) — keys `t:<token_id>` and `c:<hex(HMAC-SHA256(pepper, b"client\0"+address))[:32]>`, absent address `c:unknown`; WINDOW_S=60 constant; limits come from config token_limit_per_minute/client_limit_per_minute (defaults 60/20). Client addresses are not normalised (follow-up queued).
- 3.1: TokenService (identity.py) — verifier hex(HMAC-SHA256(pepper, b"fitdocs-relay-token-v1\0"+id+b"\0"+secret)); authenticate compares (hmac.compare_digest) BEFORE the revoked check (controller ruling: a revoked token with a wrong secret answers token-unknown, so non-holders cannot learn revocation); unknown id computes one dummy verifier + one compare; mint/create_principal retry once on DuplicateIdentifier; MintedToken hides the token from repr/str. mint(principal_id=existing, principal_label=x) ignores the label (5.2's CLI should refuse --principal-label with --principal; follow-up queued). Store-only-verifier tests pin the stored record by equality over every mint shape (absence checks alone let partial/transformed secrets survive).
- 3.3: logs.py API — configure_logging(*, pepper, password, level=INFO, stream=None) installs one root handler (JSON lines on stdout, ASCII-only), clears uvicorn/uvicorn.error handlers so they propagate, and SILENCES uvicorn.access (propagate=False + NullHandler; controller ruling per design 'access log is off'); log_event(logger, event, *, level, **fields). Failure fields are named `error_type` (str) and `frames` (list of exactly {file: str, line: int, function: str}) — 4.x must use these names; caller-supplied ones are validated and redacted, otherwise dropped. Redaction applies TOKEN_RE before the registered secrets. 5.1 must: call configure_logging before opening storage/claiming; register the DB password from both the password variable and a URL-embedded password (decoded + percent-encoded).
- 4.1: pipeline = RelayApp.__call__ (Starlette subclass, outermost): body limit (declared Content-Length, leading zeros stripped, then streamed) → version prefix `/vN/` (canonical decimal; unserved → envelope-unsupported with served versions) → routing (unmatched/405 → not-offered, no redirect_slashes) → handlers (StorageUnreachable → unavailable; other → relay-failure logged with error_type/frames, exception swallowed so uvicorn doesn't log it). One log record per request: uuid4-hex request id, route TEMPLATE (null when unmatched), method (7 standard, else OTHER), code, status, duration_ms, token_id. answers.answer() refuses retry_after_s inside data (keyword only, sets Retry-After). Routes set the token id via answers.note_token_id(request, id) after auth; storage-touching handlers are sync def. Extra seams: build_app(services, routes), compute_ready(storage). create_app still lacks design's `extensions` param and RelayServices.registration — 4.4/4.5 MUST add them and pin the blocks whole. Route tests from 4.3 on must go through create_app.
- 4.2: /livez never touches storage; /readyz → ok (with {schema:{current,expected}}), storage-unreachable ({}), schema-behind, schema-ahead (all non-ok 503) and refreshes services.ready; any other storage error → relay-failure with ready=False. Readiness gate (controller ruling: design order Match → gate) runs after route matching via RelayApp._match (FULL match only; sets scope["route"] for the log), so unmatched/405 while not ready still answer not-offered. A later versioned Mount would need _match revisited (Mount.matches is FULL on prefix). (Round 3 one-assertion fix controller-applied, verified by mutation N6.)
- 4.3 rulings: Auth → Rate (design pipeline): a failed authentication counts against the client first, then answers the token code (or rate-limited); a valid token counts only per token; capabilities always counts per client, ignoring any presented token. token_revoke is `async def` (read_request is async) with storage work via run_in_threadpool, authenticating BEFORE reading the body (a bad body from a valid token costs a token count, revokes nothing, answers request-malformed; empty body is request-malformed). RevokeResult UNKNOWN (concurrent principal deletion) → token-unknown; ALREADY_REVOKED (concurrent revoke) → ok. Bearer: case-insensitive scheme, then 1*SP (spaces only; tabs refused); spaces-only value → token-missing. Token-check ok and revoke ok answer data {}. Capabilities read routes.OFFERED_TARGETS at call time; registration False until 4.5. 4.6's replay rows must match these.
- 4.4: seam.py (SEAM_VERSION=1, design surface pinned whole as DESIGNED_SEAM) imports answers — controller ruling, design.md dependency order amended (answers → seam). create_app(config, *, extensions=(), storage=None, clock=None) and RelayServices(registration before ready) pinned whole as DESIGNED_APP. Seam implementations (_TokenIssuance, _ExtensionRecords, _install_extensions) live in app.py. Refusal messages `extension '<name>': <reason>` (label `<TypeName>` for non-text names); version checked before name; a store create_app opened is closed on any build exception. Records: key ≤128 chars, value ≤4096 bytes, ttl 1..2592000 s (ValueError), per-extension namespace, expiry clock()+ttl exclusive. /x/<name>/ routes: body limit, one log record (route template only), unhandled exception → envelope relay-failure, no readiness gate. capabilities still reports registration false until 4.5 reads services.registration. load_extensions(config.extensions) is wired by 5.1's serve. (Round 2 verified by the controller re-running O7 and O15.)
- 4.5: POST /v1/registrations ({email}) and POST /v1/registrations/poll ({poll_secret}); without a provider both answer not-offered UNCOUNTED; with one, the request is counted per client BEFORE the body is read (malformed costs a count), then read strictly, then the provider runs. Provider answers validated via the shared codec (parse_started, parse_retry_after) and services.tokens.authenticate; controller ruling: an issued token must authenticate to its stated token_id AND principal_id (stricter than design). Every invalid answer kind raises ProviderAnswerError (no message; logged by type only) → relay-failure; provider exceptions → relay-failure logged by type. capabilities registration = services.registration is not None. Test pattern: keep one started TestClient per address for a whole test (ExitStack) — a TestClient's lifespan end closes the store, so a second `with client:` answers unavailable. 4.6 replay needs this. (Round 2 verified by the controller re-running O3.)
- 4.6: relay/contract/envelope-v1.json — 29 exchanges (every route, every relay-origin code at its design status), all-`a` fake token; each has request {method,path,headers,body} and answer {status, exact lowercase headers incl. content-length/content-type/cache-control/retry-after, body}; `state.profile` / `state.provider` are relay-test setup keys 6.8 may ignore; one request body (too-large) uses {prefix, fill, count, suffix} — answer bodies are always plain text. Coverage is derived from RELAY_CODES and create_app().routes (appending a code/route reds until recorded). readyz rows record schema 1-of-1 — a 0002 migration must regenerate them.
- 5.1: serve.run_server(config, extensions=None) -> int: configure_logging FIRST (one redactor over pepper + DB password as variable, URL userinfo and URL ?password= query, each raw/decoded/encoded via logs.configure_logging(extra_secrets=...)); load_extensions(config.extensions) unless given; open storage; claim (held → serve-refused, 1; StorageError at open/claim → serve-failed type+frames, 1); install _StopRequest SIGTERM/SIGINT handlers that record the signal and set server.should_exit (a startup signal ends cleanly with 0, never swallowed); uvicorn.Server with proxy_headers=True, forwarded_allow_ips=list (never None), access_log=False, lifespan on, timeout_graceful_shutdown=grace; finally release claim, close storage, restore handlers. SeamError propagates (5.2 → exit 2); uvicorn startup failure raises SystemExit(3) (5.2 must map it — collides with 'migrations pending'). Subprocess tests run `python -B -s -E tests/serve_child/entry.py` with FITDOCS_RELAY_*/PYTHON*/FORWARDED_* scrubbed.
- 5.2: relay CLI (argparse) — outputs pinned in relay/tests/test_cli.py: migrate `schema <found> -> <left>`; --check `schema <current> -> <expected>` (+ 'migrations are pending' on stderr, exit 3); principal list / token list tab-separated, ISO-8601 UTC (`...Z`), created_at then id; mint token alone on stdout, `token_id=`/`principal_id=` on stderr; errors via fixed MSG_* constants (unexpected failures print only the type name). Rulings: serve not schema-gated (design amended); --principal-label with --principal → exit 2; missing postgres extra, usage and label errors → 2; uvicorn SystemExit(3) → 1; SeamError → 2. All output (incl. argparse usage errors, via an environment-built redactor) passes through one SecretRedactor (pepper, DB password var + URL forms, token format); labels in listings are redacted too. 8.3's docs must reuse these literals. (Round 3 one-assertion fix controller-applied, verified by mutation G2.)
- 5.3: relay/Dockerfile — build stage FROM the digest-pinned python:3.12-slim-bookworm with uv COPY'd from ghcr.io/astral-sh/uv:0.11.24@sha256 (controller ruling: the design's 'build stage uses uv pinned by digest' is met by copying uv by digest; the uv image has no shell); runtime stage same pinned base, env at /opt/fitdocs-relay, uid 10001, /data owned 0700, HOST 0.0.0.0, port 8080, ENTRYPOINT fitdocs-relay CMD serve. relay/LICENSE is a byte copy of the root LICENSE (MIT, pinned). relay/scripts/image_smoke.sh {sqlite|postgres|derived} is pinned WHOLE from `set -euo pipefail` on (tests/test_image.py _SMOKE_CODE) — any edit to the script must update that literal in the same commit. relay.yml: timeout-minutes 30; gates → docker build → smoke sqlite → postgres → derived; no push/login. The static checker derives secret variable names from contract.ENVIRONMENT.
- 5.4: relay/tests/test_contract.py pins the deploy contract as literals copied from design.md (version 1 with a type pin, the 11-row env table whole and ordered, probes, image user/port/entrypoint/default command/env path, COMMANDS). relay/CHANGELOG.md's newest `## ` section must carry exactly `- Deploy contract version: N`, `- Envelope version: N`, `- Seam version: N` (8.4 keeps this format when finalizing prose); any section whose deploy-contract or seam version differs from the next-older section must contain `**Breaking for deployments:**`. A contract change edits the literals; a version bump also adds a new newest changelog section. The env table is also pinned in test_config.py (follow-up: dedupe at 8.3). (Round 2 verified by the controller re-running O12.)
- Group 6 (client stream impl/rs-client, merged e6d8f984) notes:
  - 6.1: AuthStyle.RELAY_TOKEN + RelayRefused/RelayCapabilities/RegistrationStarted/RegistrationPolled/RelayTokenClient pinned whole by AST literals equal to design.md's ProtocolAmendment block (test_protocol.py _RELAY_DESIGN_RENDERINGS); registry._RELAY_OPERATIONS tied to RelayTokenClient's method order; CredentialStore.remove(name) -> bool touches only <name>.toml (never the directory). Surface pins are literal 55 -- the second lander of relay-server/publish-core re-counts. run_connect has NO relay branch yet: 6.3 must add relay dispatch and test it through run_connect/the CLI.
  - 6.2: relay.RelayClient/RelayConnector/RelayReply/RelaySettings; the client requires `{}` data on token-check ok, revoke ok, registration-pending and -slow-down (relay side 4.x and envelope-v1 recorded exchanges must send {} there). Controller ruling: client never fabricates a relay-origin code; an unencodable request raises EnvelopeError (caller defect), nothing sent. Retry-After header honoured only on a non-envelope 429. Tests build loopback URLs as "http://" + host because the neutral scan admits localhost but not 127.0.0.1/::1 (follow-up queued; 8.4's docs must avoid loopback literals or extend the scan).
  - 6.3 (controller ruling, supersedes the 6.1 note): relay connects do NOT go through run_connect — design routes them through the separate `run_relay_connect` (CliRelay calls it); run_connect keeps its AssertionError for RELAY_TOKEN; 6.6's CLI must dispatch RELAY_TOKEN instances to run_relay_connect / registration. relay_connect.py: run_relay_connect, relay_next_step (total over RelayCode; texts pinned as literals — 6.4/6.5 that need different next steps, e.g. disconnect's "retry, or --local-only", must extend it deliberately and update the pins), RelayConnected/RelayConnectFailed/RelayTokenFormatError. Registration codes on the token route surface as answer-malformed.
  - For 6.6 (CLI): RelayTokenFormatError's message is fixed text that never contains the value, but run_relay_connect registers the refused value for redaction BEFORE the format check, so `redactor.redact(str(exc))` (the CLI's usual pattern, cli.py ~1408/1644) mangles it when a short paste was entered ("Th<redacted>t is not <redacted> rel<redacted>y token…"). Print RelayTokenFormatError's message without passing it through redaction (pin it with a short paste like "a").
  - For 6.5: relay_next_step(code, *, name, retry_after_s) has no route context; Req 14.2 needs disconnect's next step "retry, or --local-only" — compose in disconnect.py (preferred, no design-signature change) or amend design deliberately.
  - 6.4 (controller ruling): RegistrationEmailError + EMAIL_FORMAT_MESSAGE ("That is not a plausible email address.") are a recorded departure from design — the engine (run_relay_registration) is the single email validator; 6.6's CLI must catch RegistrationEmailError → exit 2 and NOT add a second is_email check/message. Deadline inclusive (now >= expires_at → registration-expired). Loop: sleep → deadline check → poll.
  - For 6.8: the recorded exchanges file is relay/contract/envelope-v1.json (on impl/relay-server; merge it into the client stream first). Ignore state.profile/state.provider; answer bodies are plain text (assert it); only the too-large REQUEST body uses {prefix, fill, count, suffix}. Decode every recorded answer through RelayClient with a fake transport.
  - For 6.6 (from 6.5 review): disconnect_command must catch CredentialStoreError from run_disconnect (corrupt/wrong-mode file on the revoke path, tokenless file) → configuration-error exit, pointing at `fitdocs disconnect NAME --local-only` (which never reads the file); and must print NothingToDisconnect.env_override as Req 14.4's statement (the variable is not revoked and remains set). Catch UnsupportedDisconnect → exit 2; print LOCAL_ONLY_NOTE / SERVICE_NOTE from disconnect.py.
  - 6.6: cli.connect relay path = _connect_relay (paste via getpass "Relay token: "; --register with --email or "Email address: " prompt); misuse checks (--register/--email on non-relay; --email without --register) run right after the instance lookup, before NONE/reserved branches (exit 2, zero requests); (KeyboardInterrupt, typer.Abort) → 130; started lines "Registering <email>." / "Your code: <CODE>" / confirm-only-if-same / "This registration expires in N minute(s)." (floor; "less than a minute"); format/email errors printed unredacted.
- 6.7: `fitdocs disconnect NAME [--local-only]` lines: success `NAME: disconnected.` / `Credentials removed: <path>` / `Relay code: <code>` / `Note: <note>.`; nothing-to-disconnect + `Environment variable X is not revoked and remains set.` (plural form); failure `NAME: <code>: <explanation>` + next step, exit 1; unsupported → 2; CredentialStoreError → 2 on stderr with one --local-only hint. Bare pull selects by PULL_ACTIVITIES/PULL_WELLNESS capability; empty selection prints `No configured connector instance pulls activities or wellness; nothing to pull.` exit 0. CLI command count is 16 ("Sixteen") — publish-core landing second takes 17.
- 8.2: steering now says the `fitdocs` CLI runs no server; the relay paragraph (tech.md) and `### Relay server` entry (structure.md) are pinned by tests/connectors/test_network_statements.py::test_steering_publishes_the_relay_server_and_its_network_calls; the shared-module set is worded openly via SHARED_MODULES (strava-publish's outcomes.py append needs no steering rewrite); versions are a pointer to relay/CHANGELOG.md, never literals; network statements are scoped to the `fitdocs` package.
- 7.1: tests/connectors network guard (conftest `_forbid_network_sockets` + the in-test recorders) now refuses socket.socket, socket.getaddrinfo AND socket.create_connection — relay.example.com has no DNS record, so a guard on socket.socket alone never sees a urllib request to it (getaddrinfo raises first and the code swallows it as a TransportError). Pinned by test_isolation. Controller downgrade: the round-2 pin (test_isolation getaddrinfo/create_connection), conftest docstring and 0o750 mode fix were applied by the controller, verified by mutations MC (guard back to socket only → only that test reds) and G8 (save always chmods 0o700 → registration confinement reds).
- 8.3: docs/relay.md is bound by relay/tests/test_docs_relay.py (versions, image constants, env table, probe paths, command names, derived-image steps, statement pins for Req 2.8/9.6/not-governed) and tests/connectors/test_relay_docs.py (code table); relay/tests/test_config.py now takes the env table from tests.test_contract.PINNED_ENVIRONMENT (one pin, 5.4 dedupe done). The page documents current limits honestly: wrapper HTTPException → not-offered, restart the relay after restarting its PostgreSQL.
