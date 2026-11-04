# The relay: operator guide and contract

The relay is a small server you can host yourself. It holds a platform
application on a person's behalf, so the `fitdocs` command line never carries
it, and it gives each person a *relay token* that fitdocs presents instead.
The relay lives in the `relay/` directory of the fitdocs repository. It is a
separate package with its own manifest and lock, it is never part of the
`fitdocs` release, and it imports nothing from `fitdocs`. The `fitdocs`
command runs no server.

This page is for the person running a relay, and for anyone writing a wrapper
around one. It holds a self-hosting guide, then the contracts the relay keeps:
the deploy contract, the envelope that fitdocs and the relay speak, and the
seam a wrapper uses. To connect fitdocs to a relay as a user, see
[Connectors](connectors.md).

**This page is not governed by fitdocs's [compatibility policy](compatibility.md).**
The relay is versioned on its own. Each contract below carries its own version
number, and a change that breaks a deployment advances that number and is
called out as breaking in the relay's own changelog, `relay/CHANGELOG.md`.
Re-read that file, and re-check this page's versions, before you update a
deployment.

## Self-hosting guide

This guide takes you from a local run to a deployment on PostgreSQL. It names
no hosting provider because none is needed: the relay is one process and one
database.

### 1. Run it locally with SQLite

From a checkout of the fitdocs repository, with [uv](https://docs.astral.sh/uv/)
installed:

```bash
cd relay
uv sync --locked
export FITDOCS_RELAY_TOKEN_PEPPER="$(uv run fitdocs-relay new-pepper)"
export FITDOCS_RELAY_DATABASE_URL="sqlite:///relay.db"
uv run fitdocs-relay migrate
uv run fitdocs-relay serve
```

`migrate` prints `schema 0 -> 2` the first time. `serve` listens on
`127.0.0.1` port `8080` and logs JSON lines to standard output. In another
terminal:

```bash
curl http://localhost:8080/livez
```

The pepper is a secret that keys every token's stored hash. Keep it somewhere
you will not lose it: changing it invalidates every token (see
[Pepper rotation](#pepper-rotation)). `new-pepper` prints a fresh one and needs
no configuration.

### 2. Build the image from a pinned commit

The repository publishes no image. You build one from a commit you have read
and chosen:

```bash
git clone <the fitdocs repository> fitdocs
cd fitdocs
git checkout <the commit you pinned>
docker build -t fitdocs-relay relay
```

Record the commit hash in your deployment's own configuration, so a rebuild is
the same relay. The image contains no secret and no database.

### 3. Migrate, then serve

Generate the pepper once and keep it where the deployment's other secrets live:

```bash
docker run --rm fitdocs-relay new-pepper
```

Run the image with the database on a volume. The image's working directory is
`/data`, owned by the image's non-root user, so a relative SQLite path lands
there:

```bash
docker volume create fitdocs-relay-data
docker run --rm \
  -e FITDOCS_RELAY_TOKEN_PEPPER \
  -e FITDOCS_RELAY_DATABASE_URL=sqlite:///relay.db \
  -v fitdocs-relay-data:/data \
  fitdocs-relay migrate

docker run -d --name fitdocs-relay \
  -e FITDOCS_RELAY_TOKEN_PEPPER \
  -e FITDOCS_RELAY_DATABASE_URL=sqlite:///relay.db \
  -v fitdocs-relay-data:/data \
  -p 127.0.0.1:8080:8080 \
  fitdocs-relay
```

`-e NAME` with no value passes the variable from your shell, so the secret is
never on a command line. A bind mount instead of a named volume must be
writable by user id `10001`. The relay speaks plain HTTP: put a TLS-terminating
proxy in front of the published port before anything outside your machine
connects (see [TLS in front](#tls-terminated-in-front)).

### 4. Mint a token

The operator commands run against the same database, while the relay serves:

```bash
docker run --rm \
  -e FITDOCS_RELAY_TOKEN_PEPPER \
  -e FITDOCS_RELAY_DATABASE_URL=sqlite:///relay.db \
  -v fitdocs-relay-data:/data \
  fitdocs-relay token mint --new-principal --label "my laptop"
```

The token is printed alone on standard output, exactly once; its identifier
and its principal go to standard error. The relay stores only a keyed hash, so
a lost token cannot be recovered: revoke it and mint another. Take the token
to the person it is for through a channel you trust.

### 5. Connect fitdocs

In fitdocs's settings file (see [Configuration](configuration.md)), add an
instance of the `relay` connector:

```toml
[connectors.my-relay]
connector = "relay"
url = "https://relay.example.com"
```

The URL must be `https`, except for a relay on your own machine
(`http://localhost:8080`). Then paste the token when fitdocs asks:

```bash
fitdocs connect my-relay
```

fitdocs checks the token against the relay and stores it in its credential
file. The [Connectors](connectors.md) page documents what is stored where.

### 6. Switch to PostgreSQL

Create an empty database, then point the relay at it:

```bash
export FITDOCS_RELAY_DATABASE_URL="postgresql://relay@db.example.com:5432/relay"
export FITDOCS_RELAY_DATABASE_PASSWORD="<the database password>"
docker run --rm -e FITDOCS_RELAY_TOKEN_PEPPER -e FITDOCS_RELAY_DATABASE_URL \
  -e FITDOCS_RELAY_DATABASE_PASSWORD fitdocs-relay migrate
```

then run `serve` the same way, without the `/data` volume. From a checkout,
add the `postgres` extra: `uv sync --locked --extra postgres`; the image
already has it.

The relay has no command that copies one database into another. Switching
backends starts a new, empty database: principals and tokens minted on SQLite
are not carried over, so mint new tokens and give them out again. The pepper
does not depend on the backend, so you may keep it.

## Deploy contract

The deploy contract is everything a deployment may rely on: the image, the
environment, the probes, the commands, the one-replica rule and the state
rule. It is kept until it is deliberately changed, and a change that breaks a
deployment advances its version.

### Versions

- Deploy contract version: 1
- Envelope version: 1
- Seam version: 1

A test in the relay's suite binds these three numbers, the image constants,
the environment table, the probe paths, the command names and the
derived-image steps to the code; fitdocs's suite binds the code table.

### The image

- Image user id: `10001`
- Image port: `8080`
- Image entrypoint: `fitdocs-relay`
- Image default command: `serve`
- Image Python environment: `/opt/fitdocs-relay`

The image runs as that non-root user and starts from a Python base image
pinned by digest. The Python environment holding the relay and its
dependencies sits at the path above, and its `bin` directory is first on the
command search path. The image sets `FITDOCS_RELAY_HOST` to `0.0.0.0`, exposes
the port above, declares no volume, and contains no secret and no database.
The third-party licence texts of what it contains are under
`/usr/share/licenses/fitdocs-relay`. Because the entrypoint is `fitdocs-relay`,
`docker run <image> migrate` runs the `migrate` command.

### Environment

The relay and every command read their configuration only from these
variables. A variable that starts with `FITDOCS_RELAY_` and is not in the table
is refused, naming it. A missing required variable or an invalid value is a
configuration error naming the variable, and never printing a secret value:
the process exits with code 2.

| Variable | Required | Default | Secret | Meaning |
| --- | --- | --- | --- | --- |
| `FITDOCS_RELAY_DATABASE_URL` | yes | — | yes | `sqlite:///relative.db`, `sqlite:////absolute/path.db`, or `postgresql://` / `postgres://user@host:port/db[?params]`; anything else, including in-memory SQLite, is an error |
| `FITDOCS_RELAY_DATABASE_PASSWORD` | no | — | yes | PostgreSQL password. An error with a SQLite URL, or when the URL already carries a password |
| `FITDOCS_RELAY_TOKEN_PEPPER` | yes | — | yes | Token-hashing secret, at least 43 characters (`fitdocs-relay new-pepper` prints one) |
| `FITDOCS_RELAY_HOST` | no | `127.0.0.1` | no | Listen address (the image sets `0.0.0.0`) |
| `FITDOCS_RELAY_PORT` | no | `8080` | no | Listen port, 1-65535 |
| `FITDOCS_RELAY_FORWARDED_ALLOW_IPS` | no | empty | no | Comma-separated proxy addresses trusted for forwarded client addresses |
| `FITDOCS_RELAY_TOKEN_RATE_LIMIT_PER_MINUTE` | no | `60` | no | Requests per token per minute, 1-100000 |
| `FITDOCS_RELAY_CLIENT_RATE_LIMIT_PER_MINUTE` | no | `20` | no | Unauthenticated requests per client address per minute, 1-100000 |
| `FITDOCS_RELAY_SHUTDOWN_GRACE_SECONDS` | no | `20` | no | Graceful-shutdown wait, 0-600 |
| `FITDOCS_RELAY_LOG_LEVEL` | no | `info` | no | `debug`, `info`, `warning` or `error` |
| `FITDOCS_RELAY_EXTENSIONS` | no | empty | no | Comma-separated `module:attribute` references to `RelayExtension` objects |
| `FITDOCS_RELAY_PUBLIC_URL` | with `FITDOCS_RELAY_STRAVA_CLIENT_ID` | — | no | The relay's public base address (`https`, or `http` to loopback); builds the OAuth callback `<url>/strava/callback` and the webhook address `<url>/strava/webhook/<token>` |
| `FITDOCS_RELAY_ENCRYPTION_KEYS` | with `FITDOCS_RELAY_STRAVA_CLIENT_ID` | — | yes | Comma-separated `<id>:<key>` entries, 1-8; id `[a-z0-9]{1,16}` and distinct, key 32 bytes in unpadded base64url; the first encrypts (`fitdocs-relay new-encryption-key`) |
| `FITDOCS_RELAY_OPERATOR_NAME` | with `FITDOCS_RELAY_STRAVA_CLIENT_ID` | — | no | The relay's operator, as the pages name them; 1-100 printable characters |
| `FITDOCS_RELAY_SUPPORT_CONTACT` | with `FITDOCS_RELAY_STRAVA_CLIENT_ID` | — | no | An email address or `https` address where athletes reach the operator |
| `FITDOCS_RELAY_PRIVACY_POLICY_URL` | no | the relay's /privacy | no | An `https` address of the operator's own policy |
| `FITDOCS_RELAY_TERMS_URL` | no | — | no | An `https` address of the operator's terms of use; the pages link it |
| `FITDOCS_RELAY_STRAVA_CLIENT_ID` | no | — | no | The Strava application's client id (digits); setting it enables the Strava target |
| `FITDOCS_RELAY_STRAVA_CLIENT_SECRET` | with `FITDOCS_RELAY_STRAVA_CLIENT_ID` | — | yes | The application's client secret |
| `FITDOCS_RELAY_STRAVA_WEBHOOK_TOKEN` | with `FITDOCS_RELAY_STRAVA_CLIENT_ID` | — | yes | 32-128 characters of `[A-Za-z0-9_-]`; the webhook path secret and verify token |
| `FITDOCS_RELAY_STRAVA_API_URL` | no | `https://www.strava.com/api/v3` | no | Strava's API base |
| `FITDOCS_RELAY_STRAVA_OAUTH_URL` | no | `https://www.strava.com/oauth` | no | Strava's OAuth base (authorize, token, revoke) |
| `FITDOCS_RELAY_STRAVA_WEB_URL` | no | `https://www.strava.com` | no | Base of activity pages (`/activities/<id>`) |
| `FITDOCS_RELAY_STRAVA_RATE_LIMIT` | no | `200,2000` | no | Overall limit per 15 minutes and per day |
| `FITDOCS_RELAY_STRAVA_READ_RATE_LIMIT` | no | `100,1000` | no | Non-upload limit per 15 minutes and per day |

- A row marked "with" is required when the variable it names is set (when any
  of several is set). While `FITDOCS_RELAY_STRAVA_CLIENT_ID` is unset, none of
  the rows from `FITDOCS_RELAY_PUBLIC_URL` to `FITDOCS_RELAY_STRAVA_READ_RATE_LIMIT`
  may be set, and the relay refuses to start if one is.
- `FITDOCS_RELAY_STRAVA_RATE_LIMIT` and `FITDOCS_RELAY_STRAVA_READ_RATE_LIMIT`
  each take two comma-separated numbers, the limit per 15 minutes then the
  limit per day; the first may not exceed the second. The windows are aligned
  to Strava's: quarter hours, and days from midnight UTC.
- `FITDOCS_RELAY_FORWARDED_ALLOW_IPS` takes IP addresses or networks
  (`10.0.0.0/8`); `*` is refused. See [TLS in front](#tls-terminated-in-front).
- The two `_PER_MINUTE` limits (`FITDOCS_RELAY_TOKEN_RATE_LIMIT_PER_MINUTE`
  and `FITDOCS_RELAY_CLIENT_RATE_LIMIT_PER_MINUTE`) count in fixed windows of 60
  seconds.
- A `rate-limited` answer carries the wait in seconds, in its data and in a
  `Retry-After` header.

### Database URLs

| Form | Meaning |
| --- | --- |
| `sqlite:///relay.db` | A SQLite file at a path relative to the working directory (`/data` in the image). |
| `sqlite:////var/lib/relay/relay.db` | A SQLite file at an absolute path (four slashes). |
| `postgresql://user@host:5432/name` | PostgreSQL; `postgres://` is accepted too. Parameters after `?` are passed to the driver. |

In-memory SQLite and any other scheme are refused. Give a PostgreSQL password
in `FITDOCS_RELAY_DATABASE_PASSWORD`, or inside the URL, never both. The
password is never logged or printed. SQLite needs nothing installed beyond
Python; PostgreSQL needs the `postgres` extra, which the image includes.

### Probes

| Probe | Path | Answers |
| --- | --- | --- |
| Liveness | `/livez` | `ok` (200) while the process is serving. It never touches the database. |
| Readiness | `/readyz` | `ok` (200) only while the database is reachable and at the installed relay's schema version. Otherwise 503: `storage-unreachable`, `schema-behind` or `schema-ahead`. |

Both answer in the envelope. Readiness is worked out at start-up and again each
time `/readyz` is probed; until it is ready, every versioned route (`/v1/...`)
answers `unavailable` (503). Probe `/readyz` from your orchestrator.

### Commands

| Command | Behaviour |
| --- | --- |
| `serve` | Runs the server. The image's default command. |
| `migrate` | Brings the database to the installed schema. Safe to re-run. |
| `principal` | `create`, `list` and `delete` principals. |
| `token` | `mint`, `list` and `revoke` relay tokens. |
| `new-pepper` | Prints a fresh token-hashing secret. Needs no configuration. |
| `strava` | `webhook show`, `webhook create` and `webhook delete` manage the Strava webhook subscription. Needs the Strava target configured. |
| `reencrypt` | Re-encrypts the stored Strava tokens under the current encryption key. Needs the Strava target configured. |
| `new-encryption-key` | Prints a fresh `<id>:<key>` encryption key. Needs no configuration. |

The subcommands, their output and their exit codes are under
[Operator commands](#operator-commands).

### Migrate before serve

Run `migrate` before `serve` on a new deployment and on every update. Starting
`serve` does not migrate, and it does not refuse a database at the wrong
schema: it serves the probes, reports `schema-behind` or `schema-ahead` on
`/readyz`, and answers versioned routes with `unavailable` until the schema is
current and `/readyz` has been probed again. `migrate` applies each change
exactly once even if two run at once, and leaves the database at the last
change that fully applied if one fails.

### One replica, stop-then-start

Run exactly one serving instance per database. A starting instance takes a
claim on the database; if another instance already holds it, the starting one
logs `serve-refused` and exits with code 1.

- For SQLite the claim is a lock on a file beside the database
  (`<database>.serve-lock`). For PostgreSQL it is a session lock held on a
  dedicated connection.
- To update, stop the old instance, wait for it to exit, then start the new
  one (stop-then-start). Do not run a rolling update that starts the new
  instance first: it will be refused.
- **Shared network filesystems.** The SQLite claim relies on file locking, and
  a database file on a network filesystem shared between hosts (NFS, SMB or a
  shared volume) may not show one host's lock to another. There the relay
  cannot tell that a second instance is serving, and two instances writing one
  SQLite file can corrupt it. Keep a SQLite database on a local disk, or use
  PostgreSQL.
- A PostgreSQL claim lives as long as its dedicated connection. If that
  connection is dropped, for instance by a database restart, the relay does not
  notice; restart the relay after restarting its database.

### State

The configured database is the only state. The relay keeps nothing else: its
rate-limit counters, tokens, principals and a wrapper's records are all in it,
and a container's own filesystem can be thrown away. SQLite keeps its
`-wal` and `-shm` files and the `.serve-lock` file beside the database file;
they belong to it. Copy a SQLite database for backup only while the relay is
stopped, with those files together. Operator commands work against a database
that a relay is serving, and their changes apply to the next request.

### Shutdown

On `SIGTERM` or `SIGINT` the relay stops accepting new connections, finishes
requests in flight for up to `FITDOCS_RELAY_SHUTDOWN_GRACE_SECONDS`, releases
its claim and the database, and exits with code 0. Set your orchestrator's
stop timeout longer than the grace period: a container runtime's default
timeout is often shorter than the default 20 seconds.

### Logs

The relay writes one JSON record per line to standard output, with `ts`,
`level` and `event` first. A request record has the event `request` and the
fields `request_id`, `method`, `route` (the route template, not the path),
`status`, `code`, `duration_ms`, `token_id` (when the request
authenticated) and `outcome` (when the answer carried one: the Strava target's
`publish` and `upload` answers, whose publish outcome code is recorded here). A failure carries only
`error_type` and `frames` (file, line and function), never a message or a
value. `serve-refused` and `serve-failed` are the start-up refusals.

No record contains a relay token, a poll secret, an email address, a request
or response body, a header value, a query string, a client network address, the
database password or the pepper. The server's own access log is off. Set the
detail with `FITDOCS_RELAY_LOG_LEVEL`.

### TLS terminated in front

The relay serves plain HTTP and does no TLS. Put a reverse proxy or load
balancer in front that terminates TLS, and publish only the proxy. fitdocs
refuses a relay URL that is not `https`, except for a loopback address such as `localhost`.

While the Strava target is configured, the proxy must accept request bodies up
to 22 MiB (the upload bound) on `/v1/targets/strava/upload`. A request the proxy
refuses for size never reaches the relay, so the person gets the proxy's own
answer, not an envelope answer.

The relay rate-limits unauthenticated requests per client address. Behind a
proxy every request arrives from the proxy's address, so without help they all
share one limit. Set `FITDOCS_RELAY_FORWARDED_ALLOW_IPS` to the proxy's
address (or network): the relay then takes the client address from the
`X-Forwarded-For` header, but only from those peers. Leave it empty if the
relay is reached directly. The relay stores a client address only as a keyed
hash.

### Install a wrapper in a derived image

A wrapper is a Python package that adds routes and a registration flow through
the [seam](#seam-v1). A deployment installs it by building a derived image from
the relay image, in the wrapper's directory. These are the steps the
repository's own CI builds and serves:

```dockerfile
FROM <relay image>
USER root
COPY --from=<uv image> /uv /bin/uv
COPY . /tmp/wrapper
RUN uv pip install --python /opt/fitdocs-relay/bin/python /tmp/wrapper
USER 10001
```

`<relay image>` is the image you built from your pinned commit. `<uv image>` is
the uv image that `relay/Dockerfile` copies `uv` from, with its digest: use
the same reference. Leave the entrypoint and the command alone. At run time set
`FITDOCS_RELAY_EXTENSIONS` to the wrapper's `module:attribute`, and run it as
you would the relay image.

## Operator commands

`fitdocs-relay` is configured from the same environment as the server (both
`FITDOCS_RELAY_DATABASE_URL` and `FITDOCS_RELAY_TOKEN_PEPPER` are required).
Output goes to standard output unless noted. Times are ISO-8601 UTC, like
`2026-01-02T03:04:05Z`; listings are tab-separated and ordered by creation
time, then identifier. A command never prints a token's value after minting, a
token's hash, the pepper or the database password.

| Invocation | What it prints |
| --- | --- |
| `migrate` | `schema <found> -> <left>`, for example `schema 0 -> 2`. |
| `migrate --check` | `schema <current> -> <expected>`, changing nothing. When changes are pending it also prints `migrations are pending` on standard error and exits 3. |
| `principal create [--label L]` | The new principal's identifier. |
| `principal list` | One line per principal: identifier, label, created. |
| `principal delete ID` | `deleted ID`. Deleting a principal deletes its tokens and every record it owns. |
| `token mint (--principal ID \| --new-principal) [--label L] [--principal-label L]` | The token alone. On standard error: `token_id=<id>` then `principal_id=<id>`. |
| `token list [--principal ID]` | One line per token: identifier, principal, label, created, `active` or `revoked`, and the revocation time (empty when active). |
| `token revoke TOKEN_ID` | `revoked TOKEN_ID`, or `already revoked TOKEN_ID`. |
| `new-pepper` | A fresh pepper. |
| `strava webhook show` | `subscribed`, `subscribed elsewhere` (another callback) or `not subscribed`. |
| `strava webhook create` | `subscribed` or `already subscribed`. When another callback is subscribed it creates nothing and prints `subscribed elsewhere` on standard error, exiting 1. |
| `strava webhook delete` | `deleted` or `not subscribed`. |
| `reencrypt` | `re-encrypted <n>, unreadable <m>`; exits 1 when `m` is above zero. |
| `new-encryption-key` | A fresh `<id>:<key>`. |

Labels are 1 to 64 printable characters. `--principal-label` names a principal
the command creates, so it needs `--new-principal`; with `--principal` the
command prints `fitdocs-relay: --principal-label needs --new-principal` and
exits 2.

Exit codes: 0 success; 1 the operation failed; 2 a configuration or usage
error; 3 migrations are pending (`migrate --check` only).

| Failure (standard error) | Exit |
| --- | --- |
| `unknown principal: <id>` | 1 |
| `unknown token: <id>` | 1 |
| `the database is unreachable` | 1 |
| `the database could not be opened` | 1 |
| `the database schema is not current (found <n>, expected <m>); run 'fitdocs-relay migrate'` | 1 |
| `the database schema is newer than this build (found <n>, expected <m>)` | 1 |
| `the server could not start` | 1 |
| `strava failure: <class>` (`auth`, `forbidden`, `missing`, `limited`, `invalid`, `server`, `network` or `unreadable`) | 1 |
| `the Strava target is not configured` | 2 |
| `unexpected failure: <type>` | 1 |

Every command except `migrate`, `new-pepper`, `new-encryption-key`, `serve` and
`strava` first requires the schema to be current, and changes nothing otherwise
(`strava` never opens the database). `serve` exits 0 after a
clean stop, 1 when another instance holds the database or it cannot start, and
2 on a configuration or wrapper error.

## The Strava target

The relay can publish workouts to Strava on a person's behalf. The person
connects once, through a page the relay serves, and fitdocs then posts to the
relay with the relay token the connection issued; the relay holds the Strava
application, keeps the person's Strava tokens encrypted, and is the only
program that talks to Strava. This section is for the operator of a relay that
offers the target. To connect fitdocs to such a relay, see
[Connectors](connectors.md).

### Configuring Strava

The Strava target is offered exactly when `FITDOCS_RELAY_STRAVA_CLIENT_ID` is
set. Set it together with the other rows of the [environment
table](#environment) that name it in their "Required" column:
`FITDOCS_RELAY_STRAVA_CLIENT_SECRET`, `FITDOCS_RELAY_STRAVA_WEBHOOK_TOKEN`,
`FITDOCS_RELAY_PUBLIC_URL`, `FITDOCS_RELAY_ENCRYPTION_KEYS`,
`FITDOCS_RELAY_OPERATOR_NAME` and `FITDOCS_RELAY_SUPPORT_CONTACT`. A missing or
invalid one stops the relay and every command that reads the configuration,
naming the variable and never its value. Setting any of the shared rows (the public address, the encryption
keys, the operator name, the support contact or the policy address) without the
client id is refused too.

1. Create the Strava application (see [Running your own Strava
   application](#running-your-own-strava-application)). Copy its client id and
   client secret into `FITDOCS_RELAY_STRAVA_CLIENT_ID` and
   `FITDOCS_RELAY_STRAVA_CLIENT_SECRET`.
2. Set the application's authorization callback domain to the host of
   `FITDOCS_RELAY_PUBLIC_URL`. The relay sends athletes back to
   `<public address>/strava/callback`.
3. Generate an encryption key and set it (see [Encryption keys and
   rotation](#encryption-keys-and-rotation)).
4. Choose a webhook token of 32 to 128 characters from `A-Z`, `a-z`, `0-9`, `_`
   and `-`, and set it in `FITDOCS_RELAY_STRAVA_WEBHOOK_TOKEN`. Anything long and
   random will do; it is both the secret in the webhook's address and the
   verify token Strava presents when the subscription is created.
5. Set the operator name and the support contact. The privacy page names the
   operator, and every HTML page the relay serves for the target shows the
   support contact and a link to the privacy policy in its footer.
6. Run `migrate`, start the relay, then create the [webhook
   subscription](#the-webhook-subscription).

Value bounds the table cannot show: the client id is 1 to 20 digits; the client
secret is at most 256 printable ASCII characters without spaces; the two rate
limits take whole numbers from 1 to 1000000; the support contact is at most
254 characters; the public address, the policy address and the three Strava
addresses carry no user, query or fragment, and a trailing slash is dropped.
Only the three Strava addresses and the public address may be `http`, and then
only to a loopback host.

The three Strava address variables exist so the relay can move to a new address
Strava announces without a code change; leave them at their defaults otherwise.
Requests to Strava honour the standard `HTTPS_PROXY` and `NO_PROXY` variables,
and a redirect on a request that carries a body is never followed.

While the target is not configured, capabilities list no target and every
Strava route, page and webhook address answers `not-offered` like any unknown
path; the relay otherwise behaves as it does without this section.

### Encryption keys and rotation

The relay stores each connection's Strava access and refresh tokens only under
authenticated encryption, each ciphertext bound to its principal, target and
field. `FITDOCS_RELAY_ENCRYPTION_KEYS` holds one to eight `<id>:<key>` entries
with distinct ids; the first encrypts, and any of them decrypts.

- **Generate a key.** `fitdocs-relay new-encryption-key` prints a fresh
  `<id>:<key>` and needs no configuration (exit 0).
- **Rotate without downtime.** Put the new key first, keep the old keys after
  it, restart, run `fitdocs-relay reencrypt`, and, only when it reports no
  unreadable connection, remove the old key and restart. Connections stay
  readable throughout, because the old keys are still configured until the
  last step.
- **What `reencrypt` prints.** `re-encrypted <n>, unreadable <m>`. It exits 0
  when `m` is zero and 1 otherwise, and 2 when the Strava target is not
  configured. A connection held by a token refresh in flight is retried for up
  to a minute; one still busy after that is left as it is and counted in
  neither number, so run the command again to pick it up.
- **An unreadable connection.** A connection that no configured key opens is
  treated as not connected, and `reencrypt` leaves it unchanged. Restoring the
  key that sealed it makes it readable again.
- **The token-hashing secret.** The relay keeps no athlete identifier, only a
  keyed hash of it made with the token-hashing secret. Changing
  `FITDOCS_RELAY_TOKEN_PEPPER` also breaks the match between deauthorization
  events and stored connections, on top of invalidating every relay token (see
  [Pepper rotation](#pepper-rotation)).

### The webhook subscription

Strava tells an application that an athlete revoked its access through one
webhook subscription per application. Without the subscription the relay never
learns that an athlete revoked its access in their Strava settings, so the
relay keeps the connection until Strava refuses to renew its tokens, the
principal is deleted, the same Strava account is connected from another
principal or `fitdocs disconnect` runs. Create the subscription once the relay is running and reachable at its
public address, because Strava checks the address when the subscription is
created:

| Command | Prints |
| --- | --- |
| `fitdocs-relay strava webhook show` | `subscribed`, `subscribed elsewhere` or `not subscribed`. |
| `fitdocs-relay strava webhook create` | `subscribed` or `already subscribed`. |
| `fitdocs-relay strava webhook delete` | `deleted` or `not subscribed`. |

The subscription's callback is `<public address>/strava/webhook/<webhook
token>`. The commands never print it. When the application already has a
subscription with another callback, `create` creates nothing and prints
`subscribed elsewhere` on standard error, exiting 1: delete that subscription
first. The commands print nothing Strava answered; their failures and exit
codes are under [Operator commands](#operator-commands). Changing the webhook
token or the public address changes the callback, so delete the subscription and
create it again.

### Routes and pages

The routes are served only while the target is configured. `FITDOCS_RELAY_PUBLIC_URL`
must be the address fitdocs instances configure as their relay's `url`: the
connect page and its callback are served there, and the callback
address Strava is given is built from it.

| Path | Method | Answers |
| --- | --- | --- |
| `/v1/targets/strava/connect` | POST | Starts a connection (`connect-started`); bearer token. |
| `/v1/targets/strava/connect/poll` | POST | `connect-pending`, `connect-granted`, `connect-refused` or `connect-expired`; bearer token. |
| `/v1/targets/strava/publish` | POST | Finds the activity and sets its name and description; bearer token. |
| `/v1/targets/strava/upload` | POST | Finds the activity and updates it as `publish` does; uploads the workout's file only when none matches; bearer token. |
| `/v1/targets/strava/disconnect` | POST | Revokes at Strava when it can, then deletes the connection; bearer token. |
| `/connect/strava` | GET | The connect page, with the consent text and the "Connect with Strava" control. |
| `/strava/callback` | GET | Where Strava sends the athlete back to; a page telling them to return to the terminal. |
| `/privacy` | GET | The privacy policy page. |
| `/strava/webhook/<webhook token>` | GET, POST | Subscription validation and events. |

- **Envelope routes.** The five `/v1/targets/strava/` routes speak the
  [envelope](#envelope-v1), and capabilities list `strava` among their
  `targets`. Only while the Strava target is configured does the upload route
  accept a request of up to 22 MiB (a workout file of at most 16 MiB, in
  base64); every other route keeps the 64 KiB limit.
- **Pages.** The connect page, its callback and `/privacy` are served outside the
  envelope. Each HTML page carries the
  operator's support contact, a restrictive content security policy, no
  referrer and no caching. A page route answers `405` with `Allow: GET` to HEAD,
  so a link previewer can neither claim a connection nor run the callback. While
  the relay is not ready, or its database cannot be reached, a page answers a
  fitdocs-written "Not available" page.
- **The activity address.** Every posted or uploaded answer carries the
  activity's address, `<web URL>/activities/<id>`, and fitdocs writes it into the
  workout's page.
- **The webhook.** A request whose path secret is wrong answers `not-offered`.
  A validation request with the right verify token is answered with Strava's
  challenge as `{"hub.challenge": ...}`. An event is acknowledged with an empty
  `200` and acted on only when it is an athlete's deauthorization; any other
  body is ignored. A body over 64 KiB is refused with `request-too-large`
  (413) before the route sees it.
- **Rate limits.** Every Strava request the relay makes for an athlete is
  counted before it is made, against `FITDOCS_RELAY_STRAVA_RATE_LIMIT`,
  `FITDOCS_RELAY_STRAVA_READ_RATE_LIMIT` and the athlete's share of them. A
  request the counts do not allow is not made.

### What the relay keeps and when it deletes it

For each connection the relay keeps the athlete's Strava access and refresh
tokens, encrypted, with the time the access token expires; a keyed hash of the
Strava account (not the identifier itself); and the relay token issued for the connection,
only as its identifier and keyed hash. It keeps
no publication, no activity, no Strava activity or athlete identifier, no profile detail and no
copy of any Strava answer, and it writes no Strava token, authorization code or
response into its logs. A connect session lives for at most ten minutes. The call
counters hold counts only.

The relay deletes a connection at once, and
revokes the connection's relay token (it stays listed as revoked, and fitdocs
then gets `token-revoked`), when:

- `fitdocs disconnect` reaches the relay. The relay also asks Strava to revoke
  its access when its call budget allows, and deletes the connection whatever
  Strava answered.
- Strava reports a deauthorization through the webhook subscription (the
  athlete revoked the relay's access, or removed the application). This needs
  the [webhook subscription](#the-webhook-subscription).
- Strava refuses to renew a connection's tokens. A redirect, a server error or
  an unreachable Strava is transient: the stored tokens stay as they are.
- The principal is deleted (`principal delete`), which deletes its tokens
  outright as well.
- The same Strava account is connected again from another principal: the
  connection moves, and the earlier one is deleted.

### Privacy policy and consent

The relay serves its policy at `<public address>/privacy`. Give that address as
the privacy policy of the Strava application. To publish your own policy
instead, set `FITDOCS_RELAY_PRIVACY_POLICY_URL`; the relay's pages then link
that address and `/privacy` stays served. The text is fixed by fitdocs. The policy has these sections, in this order:

- **The relay's operator** names the operator and says the relay publishes workouts to Strava on the athlete's behalf.
- **What fitdocs sends** lists the workout facts, name and description, the publication identifier and, with uploads enabled, the file.
- **What the relay receives from Strava and keeps** lists the encrypted tokens and the keyed account hash, and says nothing else is kept.
- **What the relay sends to Strava** lists the code exchange, token renewal, the activity listing, the name and description update, uploads and revocation.
- **What the relay returns to fitdocs** says the relay returns the activity's address and nothing else that Strava supplied.
- **Deletion** lists four of the cases above: disconnecting, a deauthorization, a refused renewal and a deleted relay account. It does not list a connection moved to another principal.
- **Your choices** names `fitdocs disconnect` and revoking access in Strava's settings.
- **Security** says tokens are encrypted and not logged, and that a breach affecting an athlete's data is notified to Strava within 24 hours.
- **Contact** shows the operator's support contact.

The connect page shows the consent text, which says what the relay will do with
the athlete's Strava access, what it returns to fitdocs
and what it will never do, before the "Connect with Strava" control. The page
shows the user code and tells the athlete to continue only if their terminal
shows the same one.

To publish terms of use, set `FITDOCS_RELAY_TERMS_URL` to an `https` address:
every page's footer then links it after the privacy policy, and the connect page
says "By connecting, you accept the terms of use." directly before the control.
Unset, the pages are unchanged and the relay has no terms of its own.

### Operator obligations

Operating a relay that offers the Strava target carries these obligations:

- Keep the consent and privacy pages reachable at the addresses above.
- Keep a support contact in `FITDOCS_RELAY_SUPPORT_CONTACT` that athletes can
  reach.
- Notify Strava of a breach within 24 hours.
- Respect the application's athlete capacity: one athlete at first, up to ten
  on the owner's request, and more only after Strava's review.
- Never charge for the feature.
- Publish no announcement that references Strava. Describe the feature, where
  you must, as compatible with Strava ("Compatible with Strava"); the connect
  control reads "Connect with Strava" and the link reads "View on Strava".

### Running your own Strava application

A self-hosted relay needs its own Strava application, registered under your own
Strava subscription with your own callback domain, and its own webhook subscription.
Never use another operator's application credentials: an application's client
id and secret authorize requests in its owner's name. Give the application a
name that does not contain Strava's name.

## Envelope v1

fitdocs and the relay speak the *envelope*: JSON bodies over HTTPS with a
closed vocabulary of codes. Every envelope answer the relay sends is a JSON object with
exactly the keys `envelope` (the version, `1`), `code` (one code from the table
below) and `data` (an object whose fields depend on the route); an optional
`outcome` key is sent only by the Strava target's `publish` and `upload`
answers when they are `ok`. The envelope carries no free text.
Answers carry `Content-Type: application/json` and `Cache-Control: no-store`.
A request that names a token sends it as `Authorization: Bearer <token>` and
never in a URL. Requests with a body are JSON objects of at most 64 KiB (the Strava upload
route is the one exception, under [The Strava target](#routes-and-pages)), with
no duplicate keys and no extra fields.

A relay token looks like `fdr1_` followed by 16 and then 52 lowercase base32
characters, separated by an underscore.

### Routes

| Method | Path | Auth | Request fields | Answer codes (data) |
| --- | --- | --- | --- | --- |
| GET | `/livez` | none | none | `ok` (`{}`) |
| GET | `/readyz` | none | none | `ok`, `storage-unreachable`, `schema-behind`, `schema-ahead` (`{"schema": {"current": n, "expected": n}}`, empty for `storage-unreachable`) |
| GET | `/v1/capabilities` | none | none | `ok` (`envelopes`, `registration`, `targets`), `rate-limited` |
| GET | `/v1/token` | bearer | none | `ok` (`{}`), `token-missing`, `token-unknown`, `token-revoked`, `rate-limited` |
| POST | `/v1/token/revoke` | bearer | `{}` | `ok` (`{}`), the `token-*` codes, `rate-limited` |
| POST | `/v1/registrations` | none | `email` | `registration-started`, `registration-refused`, `rate-limited`, `not-offered` |
| POST | `/v1/registrations/poll` | none | `poll_secret` | `registration-pending`, `registration-slow-down`, `registration-issued` (`token`), `registration-refused`, `registration-expired`, `rate-limited`, `not-offered` |
| any | `/vN/...` where N is not served | none | none | `envelope-unsupported` (`envelopes`) |
| POST | the five `/v1/targets/strava/` routes, listed under [Routes and pages](#routes-and-pages) | bearer | see that section | served only while the Strava target is configured |
| any | anything else | none | none | `not-offered` |

Every route may also answer `request-malformed`, `request-too-large`,
`unavailable` or `relay-failure`. `rate-limited` carries
`{"retry_after_s": n}`. Capabilities lists the served envelope versions, whether
a registration provider is installed, and the target ids the relay offers.
`/x/<name>/...` routes belong to a wrapper and are served outside the envelope.
So are the Strava target's HTML pages and
the webhook's challenge echo and its empty `200`.

### Answer shape

```json
{"envelope":1,"code":"ok","data":{}}
```

The relay never sends a `Retry-After` header on anything but `rate-limited`.
`relay/contract/envelope-v1.json` records one exchange per route and per code,
with a visibly fake token (all `a`; the connection token the Strava connect
exchange issues is all `b`); both the relay's and fitdocs's test suites replay
it.

### Code table

Origin `relay` codes may appear on the wire; `client` codes are concluded by
fitdocs and never sent. The vocabulary is closed and append-only.

| Code | Status | Origin | Meaning |
| --- | --- | --- | --- |
| `ok` | 200 | relay | The relay accepted the request. |
| `token-missing` | 401 | relay | The request carried no relay token. |
| `token-unknown` | 401 | relay | The relay does not recognise this token. |
| `token-revoked` | 401 | relay | This relay token has been revoked. |
| `envelope-unsupported` | 400 | relay | The relay does not serve this envelope version. |
| `request-malformed` | 400 | relay | The relay could not read the request. |
| `request-too-large` | 413 | relay | The request is larger than the relay accepts. |
| `not-offered` | 404 | relay | This relay does not offer that. |
| `rate-limited` | 429 | relay | The relay is limiting requests; wait before trying again. |
| `unavailable` | 503 | relay | The relay is temporarily unavailable. |
| `relay-failure` | 500 | relay | The relay failed while handling the request. |
| `storage-unreachable` | 503 | relay | The relay cannot reach its database. |
| `schema-behind` | 503 | relay | The relay's database needs migrating. |
| `schema-ahead` | 503 | relay | The relay's database was migrated by a newer relay. |
| `registration-started` | 200 | relay | The relay started the registration. |
| `registration-pending` | 200 | relay | The registration is waiting for confirmation. |
| `registration-slow-down` | 200 | relay | The relay asked fitdocs to poll less often. |
| `registration-issued` | 200 | relay | The relay issued a relay token. |
| `registration-refused` | 403 | relay | The relay refused the registration. |
| `registration-expired` | 410 | relay | The registration expired before it was confirmed. |
| `relay-unreachable` | — | client | fitdocs could not reach the relay. |
| `answer-malformed` | — | client | The relay's answer was not a valid fitdocs relay answer. |
| `connect-started` | 200 | relay | The relay started connecting this target. |
| `connect-pending` | 200 | relay | The connection is waiting for the step in the browser. |
| `connect-granted` | 200 | relay | The connection is made, and the relay issued this instance's token. |
| `connect-refused` | 403 | relay | The connection was declined, or was not given every permission it needs. |
| `connect-expired` | 410 | relay | The connection attempt expired or is not known to the relay. |

### Registration format

Registration is offered only while a wrapper has installed a provider
(`registration` is `true` in capabilities); otherwise both routes answer
`not-offered`.

- `POST /v1/registrations` with `{"email": "<address>"}` (at most 254
  characters). `registration-started` carries `user_code`, `poll_secret`,
  `interval_s` and `expires_in_s`.
  - `user_code`: two groups of four consonants from `BCDFGHJKLMNPQRSTVWXZ`,
    joined by a hyphen, like `BCDF-GHJK`. fitdocs shows it; the wrapper's own
    page must show the same one.
  - `poll_secret`: 32 to 128 characters from `A-Z`, `a-z`, `0-9`, `_` and `-`.
  - `interval_s`: how often to poll, 1 to 60 seconds. Every poll counts
    against the relay's per-client rate limit (20 a minute by default) and
    fitdocs ends a registration on `rate-limited`, so a provider should
    answer 5 seconds or more unless the limit is raised.
  - `expires_in_s`: how long the registration lasts, 60 to 3600 seconds.
- `POST /v1/registrations/poll` with `{"poll_secret": "<secret>"}`.
  `registration-pending` and `registration-slow-down` carry `{}`; on
  `registration-slow-down` fitdocs adds 5 seconds to its polling interval, up
to 60 seconds.
  `registration-issued` carries `{"token": "<relay token>"}` once.
  `registration-refused` and `registration-expired` end the registration.

## Seam v1

The seam is the in-process surface a wrapper uses to add routes, install at most
one registration provider, and issue and revoke relay tokens through the same
operations the operator commands use. The relay implements no provider, sends no
email and serves no verification page.

A wrapper is an object with a `name` (`^[a-z][a-z0-9-]{0,31}$`), a
`seam_version` and a `build(context)` method returning its routes and, at most,
a provider. Install it by setting `FITDOCS_RELAY_EXTENSIONS` to
`module:attribute` references, comma-separated; the same objects can be passed
to the application factory `create_app(config, *, extensions=(), storage=None,
clock=None)`.

```python
SEAM_VERSION: Final = 1
EXTENSION_ROUTE_PREFIX: Final = "/x/"          # every extension route is under /x/<name>/
@dataclass(frozen=True)
class IssuedToken: token_id: str; principal_id: str; token: str = field(repr=False)
class TokenIssuance(Protocol):
    def issue(self, *, principal_id: str | None, label: str | None) -> IssuedToken: ...
    def revoke(self, token_id: str) -> bool: ...
    def delete_principal(self, principal_id: str) -> bool: ...
class ExtensionRecords(Protocol):     # namespace = extension name; key <=128 chars; value <=4096 bytes; ttl 1..2592000 s
    def put(self, key: str, value: bytes, *, ttl_s: int) -> None: ...
    def get(self, key: str) -> bytes | None: ...
    def take(self, key: str) -> bytes | None: ...
    def delete(self, key: str) -> bool: ...
@dataclass(frozen=True)
class StartAccepted: user_code: str; poll_secret: str; interval_s: int; expires_in_s: int
@dataclass(frozen=True)
class StartRefused: pass
@dataclass(frozen=True)
class RateLimitedAnswer: retry_after_s: int
@dataclass(frozen=True)
class PollPending: pass
@dataclass(frozen=True)
class PollSlowDown: pass
@dataclass(frozen=True)
class PollIssued: token: IssuedToken
@dataclass(frozen=True)
class PollRefused: pass
@dataclass(frozen=True)
class PollExpired: pass
StartAnswer = StartAccepted | StartRefused | RateLimitedAnswer
PollAnswer = PollPending | PollSlowDown | PollIssued | PollRefused | PollExpired | RateLimitedAnswer
class RegistrationProvider(Protocol):
    def start(self, email: str) -> StartAnswer: ...          # sync; run in a worker thread
    def poll(self, poll_secret: str) -> PollAnswer: ...
@dataclass(frozen=True)
class ExtensionContext:
    tokens: TokenIssuance; records: ExtensionRecords; clock: Callable[[], int]; logger: logging.Logger
@dataclass(frozen=True)
class ExtensionParts:
    routes: tuple[BaseRoute, ...] = (); registration: RegistrationProvider | None = None
class RelayExtension(Protocol):
    @property
    def name(self) -> str: ...            # ^[a-z][a-z0-9-]{0,31}$
    @property
    def seam_version(self) -> int: ...
    def build(self, context: ExtensionContext) -> ExtensionParts: ...
def envelope_response(code: RelayCode, data: Mapping[str, object] | None = None) -> Response: ...
class SeamError(Exception): ...           # names the extension and the reason; serve exits 2
def load_extensions(references: tuple[str, ...]) -> tuple[RelayExtension, ...]: ...
```

- **Refused at start-up** (the relay exits 2, naming the wrapper and the
  reason): a seam version other than the one above, an invalid or duplicate
  name, a route whose path does not start with `/x/<name>/`, and a second
  registration provider.
- **Routes live under a sub-path.** A Starlette `Mount("/x/<name>/")` is
  normalised to `/x/<name>` and refused; mount under a sub-path such as
  `/x/<name>/app`.
- **Browser-facing routes** under `/x/<name>/` are served outside the envelope
  and are not held back by readiness. An exception a route raises answers
  `relay-failure` in the envelope and is logged by type only. An
  `HTTPException` a route raises is answered as the envelope's `not-offered`;
  return a response instead to control a status.
- **Records.** Each wrapper has a namespace of small records with an expiry,
  kept in the relay's database, so a wrapper needs no schema or migration of
  its own. A record is visible until its expiry time.
- **Provider answers are validated.** The relay checks a `StartAccepted`
  against the registration format above, and requires a `PollIssued` token to
  authenticate as the token and principal it names (it does not check how the
  token was minted). An answer
  outside the format is a `relay-failure`, logged by type only. The relay
  applies its own rate limits before the provider runs.

## Pepper rotation

Changing `FITDOCS_RELAY_TOKEN_PEPPER` invalidates every existing relay token:
each stored hash was keyed with the old value, so every token answers
`token-unknown` afterwards. Version 1 has no rotation procedure. To change the
pepper, set the new value, restart, and mint new tokens for everyone. With the
Strava target configured the change also breaks the match between
deauthorization events and stored connections; see [Encryption keys and
rotation](#encryption-keys-and-rotation).
