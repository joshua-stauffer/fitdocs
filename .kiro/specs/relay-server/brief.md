# Brief: relay-server

## Problem

Some publish targets cannot be reached from an open-source CLI alone.

- A target whose API needs a registered application holds a client secret
  that cannot ship in public code. Strava is the case in point: an app
  registration needs a paid Strava subscription, since 2026-06-01.
- A relay holds that application and makes the target's API calls on the
  athlete's behalf.

Two kinds of athlete need a relay they can reach:

- one who uses the relay the maintainer runs at `https://api.fitdocs.ai`;
- one who runs their own relay, with their own application.

Today fitdocs has no server, and no way to authenticate to one.

## Current State

- **No server.** `tech.md` says "No server, no background jobs."
- **Credential store** (`connectors/credentials.py`):
  - one TOML file per connector instance, under
    `$FITDOCS_CREDENTIALS_DIR`, `$XDG_CONFIG_HOME/fitdocs/credentials` or
    `~/.config/fitdocs/credentials`;
  - files are 0600 and written atomically; the directory is 0700;
  - a store that resolves inside the data root is refused;
  - `CredentialAccess.replace` persists rotated tokens;
  - `FITDOCS_CONNECTOR_<INSTANCE>_<FIELD>` overrides apply to `API_KEY`
    connectors.
- **Auth styles** (`connectors/protocol.py:146-159`): `NONE`, `API_KEY` and
  `LOGIN`, plus the reserved `OAUTH_BROWSER`, which `fitdocs connect`
  refuses (`cli.py:1360-1364`). `TokenIssuer` has `login`/`refresh`
  (`protocol.py:334-341`).
- **The network allow-list** (`tests/connectors/test_boundary.py:519-631`)
  admits only `fitdocs/tiles.py` and `fitdocs/connectors/http.py` in
  `src/fitdocs/`. Any relay client in fitdocs goes through `http.py`.
- **The packaged skill** says never to run `fitdocs connect`, because it
  asks for secrets at a terminal (`skills/fitdocs-workouts/SKILL.md:36-38`).

## Desired Outcome

- **A small server.**
  - A self-hostable relay server lives in this repository as its own
    package, separate from the `fitdocs` wheel.
  - It runs locally with nothing to install beyond the package, on a
    SQLite file.
  - It ships a deploy contract that any deployment can wrap.
- **No accounts in it** (maintainer, 2026-10-31). It is single-operator:
  - the operator mints, lists and revokes relay tokens with a server
    command;
  - each token belongs to a principal, and a principal owns its target
    connections (its Strava connection, for example);
  - there is no self-service sign-up, no email and no verification pages.
- **Wrappable.** A deployment that wraps the server can add its own way of
  issuing tokens through a documented in-process seam, without patching the
  server. Email sign-up on a hosted relay is one example.
- **The fitdocs side.**
  - `fitdocs connect <relay instance>` stores a relay token in the
    credential store. The token is either:
    - pasted by the athlete, after the operator minted it; or
    - obtained by registration, when the relay advertises that it offers
      registration. The relay at fitdocs.ai does.
  - **The registration client** (device style; RFC 8628 is the pattern):
    1. the CLI sends the email address;
    2. it shows the short user code the relay returns;
    3. it polls with a private secret at the relay's interval until the
       relay issues a token, refuses, or the registration expires.

    The relay's side of registration (verification, delivery, pages) is
    not specified here.
  - Tokens can be revoked from the CLI.
- **The same behaviour on both backends.** The same server runs on
  PostgreSQL, selected by the database URL, and behaves identically. The
  conformance suite proves it.
- **The database is the whole state.** All relay state is in the
  configured database, so a backup of the database is a complete backup of
  the relay.

## Approach

**A Python ASGI app with storage behind one domain-level interface**
(maintainer, 2026-10-31).

- **Code.** It lives under `relay/` with its own `pyproject.toml`, tests and
  CI job. It is never included in the `fitdocs` wheel.
- **Scope.** The application and its deploy contract (maintainer, revised
  2026-10-31). Hosting is out of scope.
- **Why the application stays open:**
  - Strava allows each operator only their own application. A self-hosted
    relay is the only way to publish to Strava without fitdocs.ai.
  - The client and the relay share the outcome vocabulary and the HTTP
    contract, so one CI tests both sides.
  - Users hand the relay their Strava authorization, and open code lets
    them check what it does with it.
- **Identity.** A principal is whoever holds a valid relay token.
  - Tokens are high-entropy and opaque, stored only as hashes, compared in
    constant time, and revocable.
  - Operator commands mint and revoke them.
  - A wrapper mints them through the same in-process operation. The design
    decides its shape, for example an app factory that accepts extra routes
    plus the token-issuing operation.
- **Storage.** One interface, two backends, chosen by the database URL.
  - The interface speaks in domain operations: create and delete a
    principal; mint, look up and revoke a token; count against a rate
    limit. `strava-publish` adds its token-custody operations, including an
    atomic refresh-token rotation.
  - It is not a SQL or ORM layer. Each backend gives the same
    transactional guarantees in its own way: `BEGIN IMMEDIATE` and WAL
    mode in SQLite, row locks (`SELECT … FOR UPDATE`) in PostgreSQL. A
    generic SQL wrapper would hide exactly those differences.
  - **SQLite** (the standard library's `sqlite3`) is the default. A local
    relay needs no database server, no driver and no Docker.
  - **PostgreSQL** is an optional extra (`[postgres]`, psycopg 3), selected
    by passing a PostgreSQL database URL.
  - **One conformance suite** runs every interface operation against both
    backends in this repository's CI (SQLite in-process, PostgreSQL as a CI
    service container). This suite is what keeps the two consistent.
  - The design decides the migration approach: one dialect-portable set,
    or one set per backend with the conformance suite as the check.

## Scope

- **In**:
  - the relay package skeleton: the ASGI app, structured logs to stdout
    that never contain secrets, and graceful shutdown;
  - principals and relay tokens, plus the operator commands (mint, list,
    revoke, delete a principal);
  - the storage interface, with SQLite and PostgreSQL backends, their
    schema and migrations, and the conformance suite. The design chooses
    the migration tool;
  - the relay's versioned HTTP envelope:
    - token authentication on every request;
    - a capabilities endpoint saying which targets and token-issuing flows
      this relay offers (registration, for example);
    - every response carrying one code from a closed relay vocabulary. The
      design decides how it relates to publish-core's outcome vocabulary
      and how both packages share it without the relay importing the whole
      of `fitdocs`;
    - no free text crossing the wire;
  - the documented in-process seam a wrapper uses to add token issuance
    and routes;
  - **the deploy contract**, documented and pinned by tests:
    - a container image (non-root, pinned base) that holds no secret and no
      database;
    - configuration only from environment variables, with one documented
      list of names, required/optional and defaults;
    - the database URL that selects the backend (`sqlite:///…` or
      `postgresql://…`);
    - liveness and readiness endpoints, where readiness means the database
      is reachable and migrated;
    - a separate migration command, run before the app starts and safe to
      re-run;
    - the configured database as the only state;
    - one replica at a time;
    - the design decides whether this repository's CI publishes a
      versioned image, or deployments build from a pinned commit;
  - a local run on SQLite for development and self-hosting, documented in a
    self-hosting guide. That guide also covers switching to PostgreSQL;
  - the fitdocs client side:
    - a relay connector with an instance URL that defaults to
      `https://api.fitdocs.ai`;
    - `fitdocs connect` for it: a pasted token (an `API_KEY`-style field,
      with the `FITDOCS_CONNECTOR_*` override), or the registration client
      above when the relay advertises registration. That needs an
      auth-style decision (connectors amendment);
    - revoking a token from the CLI;
  - steering amendments:
    - `tech.md`: the CLI still has no server, and the repository also holds
      a separately deployed relay;
    - `structure.md`: the `relay/` directory;
  - a distribution amendment: the wheel and sdist exclude `relay/`, enforced
    by the release gate, plus the image publishing if the design puts it
    here.
- **Out**:
  - accounts, sign-up, email and verification pages in the server;
  - the relay side of registration;
  - hosting and operating any relay instance;
  - any publish target. `strava-publish` and `relay-intervals` add them;
  - paid plans, billing, social features;
  - running several relay replicas against one database.

## Boundary Candidates

- Identity (principals, tokens, operator commands) against storage (the
  interface, backends, migrations) against the HTTP envelope (auth,
  capabilities, codes) against the deploy contract (image, configuration,
  probes).
- The relay service against the fitdocs client (connect, the registration
  client, token storage).

## Out of Boundary

- Any third-party OAuth, and any publish endpoint.
- Composing posts, and publish-core's CLI and ledger.
- The relay side of any token-issuing flow other than operator commands.
- Hosting and operating relay instances.

## Upstream / Downstream

- **Upstream**: connectors (the credential store, `http.py`, auth styles)
  and publish-core's outcome vocabulary (a shared seam).
- **Downstream**:
  - `strava-publish` (Strava OAuth and publishing on the relay);
  - `relay-intervals`;
  - any wrapper, which consumes the in-process seam and the deploy
    contract.

## Existing Spec Touchpoints

- **Extends**:
  - `connectors`: the relay connector and its auth style;
  - `distribution`: the relay is excluded from the release, and any image
    publishing;
  - `docs-site`: a self-hosting guide, and a `fitdocs connect` page for the
    relay;
  - steering: `tech.md` and `structure.md`.
- **Adjacent**: `intervals-connector`, the precedent for connector instance
  settings.

## Constraints

- **Secrets come from the deploy environment only.** That covers the
  database URL and password, the token-hash pepper and (for
  `strava-publish`) the encryption key. None is ever in the repository, the
  image, under the data root, or in a log.
- **The configured database is the only state.** Rate limits and tokens
  included. The app container is disposable.
- **The backends never diverge.**
  - No relay code outside the storage backends touches SQL.
  - Every interface operation passes the conformance suite on both SQLite
    and PostgreSQL before it lands.
  - Behaviour that only one backend can give is a design defect, not a
    documented difference.
- **A SQLite relay runs as one process.** Several replicas sharing one
  SQLite file is unsupported, and the relay refuses it where it can tell.
- **The deploy contract and the wrapper seam change only deliberately.**
  Both are versioned and documented. A change to either is a breaking change
  for every deployment, and is called out in the changelog.
- **The fitdocs side stays offline outside its commands.** Only
  `fitdocs connect`, the token commands and `fitdocs publish --yes` talk to
  the relay, through `connectors/http.py` with the composed User-Agent.
- **Registration answers are codes too.** Pending, expired, refused,
  rate-limited and issued are relay codes. The CLI prints no relay-supplied
  text.
- **Licences.** These are all compatible with the repository's MIT licence:
  - Starlette BSD-3;
  - FastAPI MIT;
  - uvicorn BSD-3;
  - psycopg LGPL-3.0, only in the `[postgres]` extra and installed
    unmodified;
  - cryptography Apache-2.0/BSD.

  A published image ships their licence texts.
