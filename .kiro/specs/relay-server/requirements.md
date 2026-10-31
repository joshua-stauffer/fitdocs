# Requirements Document

## Project Description (Input)
**Who has the problem.** An athlete who wants fitdocs to publish to a
platform whose API needs a registered application. Strava is the case in
point: an application registration needs a paid Strava subscription since
2026-06-01, and its client secret cannot ship in an open-source CLI. A relay
can hold that application and make the platform's calls on the athlete's
behalf. Two kinds of athlete need one they can reach: one who uses the relay
the maintainer runs at `https://api.fitdocs.ai`, and one who runs their own
relay with their own application.

**Current situation.** fitdocs has no server, and no way to authenticate to
one. The technology steering says "No server, no background jobs." The
connector framework stores per-instance credentials outside the data root and
knows four authentication styles (none, personal key, login, and the
reserved browser consent), none of which is a relay token. Only the map tiles
and the connector transport may reach the network.

**What should change.** This repository gains a small, self-hostable relay
server as its own package, never part of the `fitdocs` release. It has no
accounts and sends no email: its operator mints, lists and revokes relay
tokens with server commands, and each token belongs to a principal that owns
its target connections. A deployment that wraps the server can add its own
token issuance (email sign-up on a hosted relay, for example) through a
documented in-process seam, without patching the server. The server runs
locally on a SQLite file with nothing else installed, runs identically on
PostgreSQL when given a PostgreSQL database URL, keeps all of its state in
that database, and ships a deploy contract any deployment can wrap. On the
fitdocs side, a relay connector instance points at a relay URL (by default
`https://api.fitdocs.ai`); `fitdocs connect` stores a relay token that was
either pasted or obtained through a device-style registration against a relay
that advertises registration; and the token can be revoked from the CLI. This
spec ships no publish target: `strava-publish` and `relay-intervals` add them.

Source: `.kiro/specs/relay-server/brief.md`; Phase 14 of
`.kiro/steering/roadmap.md`. Dependencies: none (wave 1, parallel with
`publish-core`). Extends `connectors`, `distribution`, `docs-site` and the
steering.

## Introduction

Some publish targets cannot be reached from an open-source CLI alone,
because their API needs an application whose secret must stay private. A
**relay** holds that application. This feature builds the relay's foundation
and fitdocs's way of authenticating to it. It builds no target: the first
target arrives with `strava-publish`.

Terms used below:
- The **relay** is the server this feature adds. Its **operator** is whoever
  runs an instance of it. A **deployment** is one running instance with its
  configuration and database.
- A **principal** is the relay's notion of "whoever holds a valid relay
  token". It owns its target connections; it is not an account and carries no
  email address, name or password.
- A **relay token** is the credential a principal's holder presents on every
  relay request. It is minted by the operator or by a wrapper and revoked by
  the operator, a wrapper, or its holder.
- The **envelope** is the relay's versioned HTTP request and response format.
  Every envelope answer carries one **relay code** from a closed vocabulary.
- A **wrapper** is code that a deployment runs in the same process as the
  relay to add routes and token issuance through the documented **seam**.
- **Registration** is a device-style flow a relay may offer: fitdocs sends an
  email address, shows the short **user code** the relay returns, and polls
  with a private **poll secret** until the relay issues a token, refuses, or
  the registration expires. Its relay side is a wrapper's.
- The **deploy contract** is what any deployment relies on: the image, the
  environment configuration, the probes, the commands and the state rule.
- A **backend** is one database engine the relay stores its state in: SQLite
  (the default) or PostgreSQL. The **conformance suite** is one set of tests
  every storage operation must pass on both backends.

## Boundary Context

- **In scope**: the relay package under its own directory, with its own
  manifest, tests and CI job, excluded from the `fitdocs` wheel and sdist by
  the release gate; principals and relay tokens; the operator commands; the
  storage interface with its two backends, schema migrations and the
  conformance suite; the relay's own rate limiting; the versioned envelope,
  the closed relay code vocabulary (with its byte-identical pinned copy and
  cross-check test), token authentication and the capabilities endpoint; the
  wire contract of registration and the provider interface a wrapper
  implements; the wrapper seam; the deploy contract, the container image
  definition, the local SQLite run and the self-hosting guide (including the
  switch to PostgreSQL); on the fitdocs side, the relay connector kind and its
  instance URL, the relay authentication style, `fitdocs connect` with a
  pasted token or the registration client, `fitdocs disconnect`, and the
  `fitdocs pull` instance selection that keeps relay instances out of a bare
  pull; the steering, connectors, distribution and docs-site amendments.
- **Out of scope**: accounts, sign-up, email, verification pages and every
  other relay-side behaviour of registration (a wrapper's); any publish target
  and any third-party OAuth (`strava-publish`, `relay-intervals`); composing
  posts, the publish ledger, `fitdocs publish` and the outcome vocabulary
  (`publish-core`); hosting or operating any relay instance, TLS termination,
  backups and infrastructure; publishing a container image or a relay
  distribution; running several relay replicas against one database; paid
  plans, billing and social features.
- **Adjacent expectations**: `publish-core` owns the closed outcome
  vocabulary (`fitdocs.publish.outcomes`) and its single-attempt write mode in
  the connector transport; the envelope carries a publish result as one of
  publish-core's outcome codes and never redefines them, and this feature
  sends no publish request. `strava-publish` and `relay-intervals` add target
  routes, capability entries, storage operations (token custody, including an
  atomic refresh-token rotation) and deploy-contract variables, each passing
  the conformance suite on both backends, and add the shared modules they
  need to the pinned-copy cross-check; `strava-publish` drives the reserved
  browser-consent authentication style. A wrapper consumes the seam and the
  deploy contract. The connector framework (`connectors`) keeps owning the
  credential store, the transport and the registry this feature extends.

## Requirements

### Requirement 1: A Separate, Self-Hostable Relay Package
**Objective:** As an operator who wants my own relay, I want the relay to be a small package in this repository that installs and runs on its own, so that I can run it without installing fitdocs and without anything but the package and a database file.

#### Acceptance Criteria
1. The relay server shall live in this repository as its own package, with its own manifest, its own lockfile, its own tests and its own CI job, and shall install and run without the `fitdocs` distribution or any of its runtime dependencies.
2. The relay server shall run locally against a SQLite database file with nothing installed beyond the relay package itself: no database server, no database driver and no container runtime.
3. Where the PostgreSQL support is installed as the relay package's optional extra and the configured database URL names a PostgreSQL database, the relay server shall store its state in that PostgreSQL database instead, with no other configuration change.
4. The `fitdocs` wheel and sdist shall contain no file of the relay package, and the release gate shall fail a release whose wheel or sdist contains one.
5. The relay package's own quality checks (tests, lint, format and strict type checks) shall run in this repository's CI on every push and pull request.
6. The relay package shall never import the `fitdocs` package; every vocabulary it shares with fitdocs shall reach it as a pinned copy (Requirement 4).

### Requirement 2: Principals and Relay Tokens
**Objective:** As an operator, I want each relay token to belong to a principal that owns its target connections, with no accounts, no email and no stored secret, so that a leaked database never yields a usable token and deleting a principal removes everything it owned.

#### Acceptance Criteria
1. The relay server shall represent each token holder as a principal with an opaque identifier, a creation time and an optional operator-supplied label, and shall store no email address, name or password for it.
2. When a relay token is minted, the relay server shall generate it from at least 256 bits of cryptographic randomness in a documented, recognizable format, return its full value exactly once, and store only a keyed hash of its secret part, keyed by a secret taken from the deploy environment.
3. When a request presents a relay token, the relay server shall accept it only if its stored keyed hash matches, comparing in constant time, and the token has not been revoked and its principal still exists.
4. When a relay token is revoked, the relay server shall refuse every later request presenting it, and shall answer such a request with the revoked-token code rather than the unknown-token code.
5. When a principal is deleted, the relay server shall delete its tokens and every record the principal owns in the same transaction, so that no later request authenticates as it and nothing it owned remains.
6. The relay server shall never store, log or return a relay token's full value after minting, and shall never return a token's keyed hash.
7. If the token-hashing secret is absent or shorter than the documented minimum, the relay server and every operator command shall refuse to start, naming the variable but never its value.
8. The relay documentation shall state that changing the token-hashing secret invalidates every existing relay token.

### Requirement 3: Operator Commands
**Objective:** As an operator, I want server commands to create, list and delete principals and to mint, list and revoke relay tokens, so that I can issue access to my relay without any sign-up flow.

#### Acceptance Criteria
1. The relay package shall provide one operator command with subcommands to create, list and delete principals and to mint, list and revoke relay tokens, configured from the same environment as the server.
2. When the operator mints a token, the operator command shall mint it for a named existing principal or for a new principal created in the same transaction, print the token's full value alone on standard output, and print its identifier and principal on standard error.
3. When the operator lists principals or tokens, the operator command shall print each one's identifier, principal, label, creation time and revocation state in a stable order, and shall never print a token's value or keyed hash.
4. If an operator command names a principal or token that does not exist, the operator command shall change nothing, name the identifier, and exit with a non-zero code.
5. The operator commands shall work while the relay server is serving against the same database, and their changes shall take effect for the next request the server handles.
6. If the database is unreachable, not yet migrated, or migrated by a newer relay version, every operator command other than the migration command shall change nothing and exit with a non-zero code naming the condition.
7. The operator commands shall never print a database password, the token-hashing secret, or any other secret from the environment.

### Requirement 4: The Versioned Envelope and the Relay Code Vocabulary
**Objective:** As a fitdocs user and as a later spec adding a target, I want every exchange with a relay to use one versioned format whose answers are codes from a closed vocabulary that both sides share exactly, so that no text from the relay or from a platform behind it ever reaches my terminal and the two sides can never drift apart.

#### Acceptance Criteria
1. The relay server shall serve its fitdocs-facing API under a versioned envelope, and every envelope answer shall carry the envelope version and exactly one relay code.
2. The relay code vocabulary shall be closed and append-only: each code has a stable string value, a fixed explanation written by fitdocs and a fixed HTTP status, and an automated test shall pin the vocabulary's members in order as a prefix, so that a later spec may only append.
3. The relay code vocabulary shall cover at least: success; a missing, unknown or revoked token; an unsupported envelope version; a malformed or oversized request; a capability, route or flow this relay does not offer; the relay's own rate limit with its retry wait; the relay being unavailable; an unexpected relay failure; the readiness conditions (database unreachable, schema older or newer than the build); the registration answers (started, pending, slow down, issued, refused, expired); and the client-observed conditions of an unreachable relay and an answer that is not a valid envelope.
4. Where an envelope answer reports a publish result, the envelope shall carry it as one code of publish-core's outcome vocabulary in its own field, and the relay code vocabulary shall define no publish outcome of its own.
5. The envelope shall carry no human-readable message, explanation or service text in either direction: every field of every request and answer shall be one the envelope's documented schema defines, and an answer with any other top-level field shall be treated as malformed.
6. If a request names an envelope version the relay does not serve, the relay server shall answer with the unsupported-envelope code and the versions it serves.
7. If a request is not a valid envelope request for its route, or exceeds the route's documented size limit, the relay server shall answer with the malformed-request or oversized-request code and change nothing.
8. If a request reaches a route, capability or flow the relay does not offer, the relay server shall answer with the not-offered code.
9. The relay package shall receive every vocabulary and codec it shares with fitdocs as a byte-identical copy of a dependency-free module in the `fitdocs` source, never edited by hand and refreshed by one documented command, and an automated test run in this repository's CI shall fail when any copy differs from its source.
10. The relay server shall emit only codes the vocabulary marks as sent by the relay, and never a client-observed code.
11. Where a wrapper or a later spec adds a browser-facing page, the relay server shall serve it outside the envelope, and the fitdocs CLI shall never request it.

### Requirement 5: Token Authentication and the Capabilities Endpoint
**Objective:** As a fitdocs user, I want every protected relay request authenticated by my relay token and one public endpoint that says what this relay offers, so that fitdocs can tell before asking whether a relay supports registration or a given target.

#### Acceptance Criteria
1. The relay server shall require a relay token on every envelope route except the capabilities endpoint, the registration routes and the probes, and shall answer a protected request without one with the missing-token code.
2. The relay server shall serve a token-check route that answers success for a valid token and the unknown-token or revoked-token code otherwise, and that changes nothing.
3. The relay server shall serve a token-revocation route that revokes the token presenting it and answers success.
4. The relay server shall serve an unauthenticated capabilities endpoint that lists the envelope versions it serves, the targets it offers, and whether it offers registration, with no free text.
5. While no target has been added by a later spec or a wrapper, the capabilities endpoint shall list no target.
6. The capabilities endpoint shall advertise registration exactly when a wrapper has installed a registration provider through the seam.

### Requirement 6: The Relay's Own Rate Limits
**Objective:** As an operator, I want the relay to limit how often each token and each unauthenticated client may call it, counted in the database, so that one client cannot exhaust the relay and a restart forgets nothing.

#### Acceptance Criteria
1. The relay server shall limit authenticated requests per relay token and unauthenticated requests (including failed authentications and registration requests) per client, each to a configurable count per window with documented defaults.
2. When a request exceeds its limit, the relay server shall answer with the rate-limited code and the whole seconds to wait, in the envelope and as a standard retry header, and shall not run the request.
3. The relay server shall keep its rate-limit counts in the configured database and nowhere else, so that a restart neither resets nor loses them, and shall store a client's network address only as a keyed hash.
4. The relay server shall discard expired rate-limit counts, so that their number stays bounded by the clients active within one window.

### Requirement 7: Storage — One Interface, Two Backends, One Conformance Suite
**Objective:** As the maintainer and as a later spec that adds token custody, I want all relay state behind one domain-level storage interface with SQLite and PostgreSQL backends that behave identically, proven by one conformance suite, so that an operator can choose either database and nothing behaves differently.

#### Acceptance Criteria
1. The relay server shall reach its state only through one storage interface of domain operations (create, look up, list and delete a principal; mint, look up, list and revoke a token; count a request against a rate limit; the wrapper's namespaced records; schema and readiness state; the single-serving-instance claim), and no relay code outside the two backends shall issue a database query.
2. The relay server shall select the backend from the configured database URL alone: a SQLite URL selects SQLite and a PostgreSQL URL selects PostgreSQL; any other URL shall be a configuration error naming the variable but not its value.
3. If a PostgreSQL URL is configured and the PostgreSQL support is not installed, the relay server shall refuse to start and name the optional extra that provides it.
4. Each storage operation shall be atomic on both backends: concurrent operations shall never lose an update, never mint two tokens with one identifier, never let a revoked token authenticate after its revocation returns, and never count one request twice or not at all.
5. One conformance suite shall exercise every storage interface operation, including its concurrent and failure cases, against both backends, and an automated check shall fail when any operation of the interface is not covered by the suite.
6. This repository's CI shall run the conformance suite against both backends on every push and pull request, with PostgreSQL provided by the CI job itself, and shall fail rather than skip when the PostgreSQL backend cannot be reached there.
7. When a later spec adds a storage operation, that operation shall join the same interface and the same conformance suite, and shall pass on both backends before it lands; behaviour only one backend can give shall be a defect, not a documented difference.
8. The relay server shall keep all of its state in the configured database, so that a backup of that database is a complete backup of the relay and its container or process can be discarded at any time.

### Requirement 8: Schema Migrations
**Objective:** As an operator, I want a separate migration command that brings the database to the schema the relay needs and is safe to re-run, so that a deploy can migrate before the server starts and a mistaken second run changes nothing.

#### Acceptance Criteria
1. The relay package shall provide a migration command that applies every schema change the installed relay needs, in order, and reports the schema version it found and the version it left.
2. When the migration command runs against a database already at the installed relay's schema, it shall change nothing and exit with the success code.
3. If the database records a schema newer than the installed relay knows, the migration command shall change nothing and exit with a non-zero code naming both versions.
4. If two migration commands run at once against one database, the relay shall apply each schema change exactly once.
5. If one schema change fails, the migration command shall leave the database at the last fully applied version and exit with a non-zero code.
6. The migration command shall offer a check mode that changes nothing and exits with a distinct non-zero code when schema changes are pending.
7. Both backends shall reach the same schema version through the same numbered sequence of changes, and an automated test shall fail when the two sequences differ in number or naming.

### Requirement 9: The Deploy Contract
**Objective:** As anyone deploying a relay, I want one documented, versioned contract — the image, environment-only configuration, probes, commands and state rule — that the relay keeps until it deliberately changes it, so that a deployment that wraps it keeps working across relay updates.

#### Acceptance Criteria
1. The relay package shall define a container image that runs as a non-root user, starts from a base image pinned by digest, contains no secret and no database, and carries the licence texts of the third-party software it contains.
2. The relay server and its commands shall take configuration only from environment variables listed in one documented table that names each variable, whether it is required, its default and whether it is secret, and an automated test shall bind that table to the variables the relay reads.
3. If an environment variable carrying the relay's reserved prefix is not in that table, the relay server and its commands shall refuse to start, naming the variable.
4. If a required variable is absent or a variable's value is invalid, the relay server and its commands shall refuse to start with a configuration error naming the variable, never printing a secret variable's value.
5. The relay server shall serve a liveness probe that answers success while the process is serving, and a readiness probe that answers success only while the database is reachable and at the installed relay's schema version, answering otherwise with the readiness code naming which condition fails.
6. The relay server shall run as one serving instance per database; if another serving instance already holds the database, a starting instance shall refuse to start, and the relay documentation shall state where a backend cannot tell (a database file on a shared network filesystem).
7. When the relay server receives a termination signal, it shall stop accepting new connections, finish in-flight requests within a configurable grace period, release the database and exit with the success code.
8. The relay server shall write its logs to standard output as one structured record per line, and no log record shall contain a relay token, a poll secret, an email address, a request or response body, a request header value, a query string, a client network address, the database password or the token-hashing secret.
9. If an unexpected failure occurs while handling a request, the relay server shall answer with the unexpected-failure code and log the failure's type and location only, never its message or the values of local variables.
10. The deploy contract shall carry its own version number, documented with the image, the variable table, the probes, the commands, the one-replica rule and the state rule, and an automated test shall pin each of them.
11. This repository's CI shall build the image and run it against both backends (migrate, serve, probe, terminate) on every push and pull request, and shall publish no image; deployments build the image from a pinned commit.
12. When the deploy contract or the seam changes incompatibly, its version shall advance and the relay changelog shall call the change out as breaking for every deployment.

### Requirement 10: The Wrapper Seam
**Objective:** As someone running a hosted relay, I want to add my own token issuance and routes in the same process through one documented, versioned seam, so that I can offer sign-up without patching the relay and without leaving the relay's database.

#### Acceptance Criteria
1. The relay package shall offer a documented in-process seam through which a wrapper adds routes, installs at most one registration provider, and issues relay tokens, revokes them and deletes principals through the same operations the operator commands use.
2. The relay package shall let a deployment install a wrapper by configuration alone, with no change to the relay's own code, and the same seam shall be usable programmatically from the relay's application factory.
3. The seam shall give each wrapper a namespaced store of small records with an expiry, kept in the configured database through the storage interface, so that a wrapper's own state needs no schema or migration of its own and the database stays the deployment's only state.
4. Where a registration provider is installed, the relay server shall serve the registration routes with the wire format this feature defines, validate each answer the provider returns against that format, apply its own rate limits, and answer with the registration codes.
5. If a registration provider returns an answer outside the wire format (a malformed user code, an out-of-range interval or expiry, or a token not issued through the seam), the relay server shall answer with the unexpected-failure code and log the failure's type only.
6. While no registration provider is installed, the relay server shall answer the registration routes with the not-offered code.
7. If a wrapper declares a seam version other than the one the relay implements, adds a route that collides with a relay route, or is the second wrapper to install a registration provider, the relay server shall refuse to start, naming the wrapper and the reason.
8. The seam shall carry its own version number, and an automated test shall pin its version and the names and signatures of its surface, so that a change to it is always deliberate.
9. The relay package shall implement no registration provider, send no email, and serve no verification page.

### Requirement 11: Relay Instances in fitdocs
**Objective:** As a fitdocs user, I want to configure a relay as a connector instance that points at a relay URL, defaulting to the maintainer's relay, so that fitdocs knows where my relay is and which token belongs to it.

#### Acceptance Criteria
1. The fitdocs CLI shall provide a built-in relay connector whose instance takes an optional relay URL, defaulting to `https://api.fitdocs.ai`.
2. If a relay instance's URL is neither an absolute `https` URL nor an `http` URL to the local machine's loopback address, or carries a query, fragment or user information, the fitdocs CLI shall stop with a configuration error naming the settings file, the instance and the key, before any network request.
3. The connector framework shall add a relay authentication style whose single secret credential field is the relay token, stored in the existing per-user credential store and overridable from the instance's `FITDOCS_CONNECTOR_*` environment variable exactly as a personal key is.
4. The connector framework shall accept a relay connector that declares no capability, and shall reject a connector declaring the relay authentication style that lacks any of the relay operations (token check, registration start, registration poll, revocation, capabilities read).
5. When `fitdocs pull` runs without instance names, the fitdocs CLI shall pull only from configured instances whose connector pulls activities or wellness, so that a configured relay instance never makes a bare pull fail; when a relay instance is named explicitly, the fitdocs CLI shall report that it pulls nothing, as for any non-pulling instance.
6. The fitdocs CLI shall make no relay request during `fitdocs pull`, whether or not relay instances are configured.

### Requirement 12: Connecting with a Pasted Token
**Objective:** As a fitdocs user whose relay operator gave me a token, I want `fitdocs connect` to check it once and store it, so that later commands can use it without my typing it again.

#### Acceptance Criteria
1. When `fitdocs connect NAME` runs for a relay instance without the registration option, the fitdocs CLI shall prompt for the relay token without echoing it.
2. If the answer does not have the documented relay-token format, the fitdocs CLI shall exit with the configuration-error code before any request and store nothing.
3. When the token has the documented format, the fitdocs CLI shall make exactly one token-check request to the relay; when the relay answers success, it shall store the token, report the instance, the credentials file's location and any environment variable that will override it, and exit with the success code.
4. If the relay answers any other code, or cannot be reached, or answers with something that is not a valid envelope, the fitdocs CLI shall print the instance, the relay code and its fitdocs-written explanation and next step, store nothing, and exit with the failure code.
5. If standard input is not an interactive terminal, the fitdocs CLI shall prompt for nothing, exit with the configuration-error code, and name the environment variable an unattended command can use instead.
6. When `fitdocs connect` succeeds for a relay instance that already has a stored token, the fitdocs CLI shall replace it atomically and shall not revoke the replaced token.

### Requirement 13: The Registration Client
**Objective:** As a fitdocs user of a relay that offers registration, I want `fitdocs connect` to register my email address and wait for the relay to issue my token, showing me a code to match against the confirmation page, so that I can get a token without asking an operator and someone else cannot register my address.

#### Acceptance Criteria
1. When `fitdocs connect NAME --register` runs for a relay instance, the fitdocs CLI shall first read the relay's capabilities; if the relay does not advertise registration, it shall print the not-offered code with its explanation and the next step (ask the relay's operator for a token), store nothing, and exit with the failure code.
2. The fitdocs CLI shall take the email address from an `--email` option or, when standard input is an interactive terminal, from a prompt; if neither is available, it shall exit with the configuration-error code before any request; if the address is not a syntactically plausible email address, it shall exit with the configuration-error code before any request.
3. When the relay answers the registration start with the started code, the fitdocs CLI shall print the email address the user gave, the user code, and an instruction to confirm only if the relay's confirmation page shows the same code, and shall print the time remaining before the registration expires.
4. The fitdocs CLI shall print the user code only after it matches the documented user-code format, and shall print no other value the relay returned; if a started answer's user code, poll secret, poll interval or expiry is outside the documented format or range, it shall treat the answer as malformed.
5. While a registration is pending, the fitdocs CLI shall poll the relay with the poll secret at the interval the relay stated, one request per poll, never repeating a poll request automatically, and shall lengthen the interval by a fixed documented step each time the relay answers slow down.
6. When the relay answers issued with a token in the documented relay-token format, the fitdocs CLI shall store it exactly as a pasted token is stored, report the instance and the credentials file's location, and exit with the success code.
7. If the relay answers refused, expired, rate-limited, or any code other than pending, slow down and issued, or a poll cannot reach the relay or returns something that is not a valid envelope, the fitdocs CLI shall stop polling, print the relay code with its fitdocs-written explanation and next step, store nothing, and exit with the failure code.
8. If the registration's stated expiry passes without an issued answer, the fitdocs CLI shall stop polling, report the expired code, store nothing, and exit with the failure code.
9. If the user interrupts the registration, the fitdocs CLI shall stop polling, store nothing, and exit with the interrupt code.
10. The fitdocs CLI shall never print, store or write the poll secret, and shall never store the email address.
11. If `--register` or `--email` is given for an instance that is not a relay instance, the fitdocs CLI shall exit with the configuration-error code before any request.

### Requirement 14: Disconnecting and Revoking from the CLI
**Objective:** As a fitdocs user, I want one command that revokes my relay token at the relay and forgets it locally, so that a token I no longer use stops working everywhere.

#### Acceptance Criteria
1. When `fitdocs disconnect NAME` runs for a relay instance with a stored token, the fitdocs CLI shall make exactly one revocation request with that token; when the relay answers success, or answers that the token is already unknown or revoked, it shall remove the instance's credentials file, report the relay code, and exit with the success code.
2. If the revocation request cannot reach the relay, or the relay answers any other code, the fitdocs CLI shall keep the credentials file, print the relay code with its fitdocs-written explanation and the next step (retry, or `--local-only`), and exit with the failure code.
3. Where `--local-only` is given, the fitdocs CLI shall make no request, remove the instance's credentials file, and state that the token stays valid at the relay until its operator revokes it.
4. While the instance has no stored token, the fitdocs CLI shall report that there is nothing to disconnect, make no request, and exit with the success code; where the instance's environment override is set, it shall state that the variable is not revoked and remains set.
5. Where the instance's connector uses the personal-key or login style, the fitdocs CLI shall remove the instance's credentials file without any request and state that the credential remains valid at the service; where it requires no authentication, the fitdocs CLI shall report that there is nothing to disconnect; where its style is reserved, it shall exit with the configuration-error code naming the style as unsupported by this version.
6. If NAME is not a configured instance, the fitdocs CLI shall exit with the configuration-error code naming every configured instance.
7. The fitdocs CLI shall write nothing under the data root during `fitdocs disconnect`, and shall remove nothing but the named instance's credentials file.

### Requirement 15: Network, Secrets and No Relay Text on the fitdocs Side
**Objective:** As a privacy-conscious fitdocs user, I want the relay reached only by the commands that need it, through the existing transport, with nothing the relay says printed back to me, so that I know exactly when fitdocs talks to a relay and what I see is fitdocs's own words.

#### Acceptance Criteria
1. The fitdocs CLI shall make relay requests only during `fitdocs connect` and `fitdocs disconnect` for a relay instance (and, once a later spec adds it, `fitdocs publish --yes`), and every other command shall make none, whether or not relay instances are configured.
2. Every relay request fitdocs makes shall go through the connector transport, send the composed fitdocs User-Agent, carry the relay token only as a credential header, and be attempted exactly once, never repeated automatically whatever the answer.
3. The fitdocs CLI shall print, log and write only relay codes, fitdocs-written explanations and next steps, values the user supplied, and the registration user code once validated; it shall never print, log or write any other text, identifier or value a relay returned.
4. The fitdocs CLI shall register every relay token and poll secret with the run's redaction before its first use, so that no output, report or error ever shows one.
5. The connector framework shall add no runtime dependency for the relay connector, and the relay connector's modules shall read no clock of their own.
6. The fitdocs source's network allow-list shall be unchanged: the shared vocabulary and codec modules shall import no network-capable module, and the relay connector shall reach the network only through the connector transport.

### Requirement 16: Steering, Documentation and Changelog
**Objective:** As a maintainer, operator or fitdocs user relying on what the repository says, I want every statement about servers, the network, credentials and the release to stay true, and the relay documented for both operators and users, so that nothing published contradicts what the code does.

#### Acceptance Criteria
1. The technology steering shall state that the `fitdocs` CLI runs no server and no background jobs and that the repository also holds a separately deployed relay server that is never part of the `fitdocs` release, and its network and credentials section shall name the relay commands among the connector requests.
2. The structure steering shall describe the relay package's directory, its independence from the `fitdocs` package, the pinned-copy rule and the dependency direction of the shared modules.
3. The connectors documentation shall describe the relay connector, its URL setting and default, the relay token and its environment override, `fitdocs connect` with a pasted token and with `--register`, `fitdocs disconnect`, what leaves the machine for each, and the bare-pull selection rule.
4. The repository shall document the relay for operators in one page: the deploy contract (image, variable table, probes, commands, one-replica and state rules) with its version, the envelope and its version, the relay code vocabulary, the operator commands and the seam with its version; automated tests shall bind the page's variable table, code table and version numbers to the code.
5. The website shall gain a guide to connecting fitdocs to a relay and a self-hosting guide covering a local SQLite run, building and running the image, minting a token, connecting fitdocs to it, and switching to PostgreSQL; the website's CLI reference shall document `fitdocs connect --register` and `fitdocs disconnect`, and its privacy-and-network guide shall name what a relay instance sends and when; each page shall pass the website's content contract.
6. The packaged `fitdocs-workouts` skill shall tell the agent never to run `fitdocs disconnect` itself, beside its existing `fitdocs connect` rule, and an automated test shall pin both.
7. The `fitdocs` changelog's unreleased section shall record the relay connector, the relay authentication style, `fitdocs connect --register`, `fitdocs disconnect` and the bare-pull selection change, each with the action a user must take; the relay package shall keep its own changelog recording the deploy contract, envelope and seam versions.
8. Every new or changed document shall pass every existing documentation and network-statement guard, and no new document shall mention a hosting provider, an email provider or a deployment's infrastructure.
