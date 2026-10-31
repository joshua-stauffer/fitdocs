# Brief: relay-accounts

## Problem

Some publish targets cannot be reached from an open-source CLI alone.

- A target whose API needs a registered application holds a client secret
  that cannot ship in public code. Strava is the case in point: an app
  registration needs a paid Strava subscription, since 2026-06-01.
- Every athlete registering their own application is a barrier most will
  not cross.

A relay that holds one application for many athletes needs a way to know
who is calling. fitdocs today has no server and no account of any kind.

## Current State

- **No server.** `tech.md` says "No server, no background jobs."
  fitdocs.ai is a static GitHub Pages site (`docs/website.md`). Its DNS is
  on Cloudflare, Free plan, with DNS-only records.
- **Credential store** (`connectors/credentials.py`):
  - one TOML file per connector instance, under
    `$FITDOCS_CREDENTIALS_DIR`, `$XDG_CONFIG_HOME/fitdocs/credentials` or
    `~/.config/fitdocs/credentials`;
  - files are 0600 and written atomically; the directory is 0700;
  - a store that resolves inside the data root is refused;
  - `CredentialAccess.replace` persists rotated tokens.
- **Auth styles** (`connectors/protocol.py:146-159`): `NONE`, `API_KEY` and
  `LOGIN`, plus the reserved `OAUTH_BROWSER`, which `fitdocs connect`
  refuses (`cli.py:1360-1364`). `TokenIssuer` has `login`/`refresh`
  (`protocol.py:334-341`).
- **The network allow-list** (`tests/connectors/test_boundary.py:519-631`)
  admits only `fitdocs/tiles.py` and `fitdocs/connectors/http.py` in
  `src/fitdocs/`. Any relay client in fitdocs goes through `http.py`.
- **The packaged skill** says never to run `fitdocs connect`, because it
  asks for secrets at a terminal (`skills/fitdocs-workouts/SKILL.md:36-38`).
- **Measured facts** (viability, 2026-10-31):
  - DigitalOcean blocks outbound SMTP (ports 25, 465 and 587) on droplets by
    default (<https://docs.digitalocean.com/support/why-is-smtp-blocked/>).
  - DigitalOcean volumes are replicated within one datacenter and "are not
    included in Droplet backups"
    (<https://docs.digitalocean.com/products/volumes/details/limits/>).
  - Docker's published ports bypass `ufw`
    (<https://docs.docker.com/engine/network/packet-filtering-firewalls/>).
  - WAL-G v3.0.9 (2026-08-20) is the first release that fixes remote base
    backups against PostgreSQL 15+ (wal-g PR #2262).
  - Resend's free tier is 3,000 emails/month (100/day). Its keys can be
    limited to sending, and to one domain
    (<https://resend.com/docs/api-reference/api-keys/create-api-key>).
  - Gmail and Yahoo require SPF or DKIM, TLS and valid DNS for all senders.
    DMARC and one-click unsubscribe are bulk-only
    (<https://support.google.com/a/answer/81126>).

## Desired Outcome

- **A deployable relay.** A self-hostable relay service lives in this
  repository as its own deployable package, separate from the `fitdocs`
  wheel. The maintainer runs it at `api.fitdocs.ai`; anyone can run their
  own.
- **Registration.**
  - `fitdocs connect <relay instance>` asks for an email address, sends a
    registration to the relay, and shows a short code.
  - The relay emails a verification link. The page it opens shows the same
    code and has a Confirm button.
  - Once confirmed, the waiting CLI receives a relay token and stores it in
    the credential store.
- **Revocable.** The token can be revoked, and the account deleted, from
  the CLI.
- **Local mode.** A local relay runs without email: it prints the
  confirmation link to its console. It refuses to start that way unless it
  is bound to loopback.
- **Durable.** A lost droplet loses no account: the database is restored
  from the backup in Spaces.

## Approach

**A Python ASGI app with PostgreSQL, deployed as a Compose stack on a
DigitalOcean droplet** (maintainer, 2026-10-31).

- **Code.** It lives under `relay/` with its own `pyproject.toml`, tests and
  CI job. It is never included in the `fitdocs` wheel.
- **Storage.**
  - PostgreSQL runs in a container whose data directory is on a
    DigitalOcean block-storage volume.
  - WAL-G (≥ 3.0.9) archives continuously to a Spaces bucket in a different
    region.
  - The restore is documented and rehearsed.
- **Email.** It is sent through a provider's HTTPS API, not SMTP
  (maintainer, 2026-10-31). The API avoids DigitalOcean's SMTP block. Its
  keys can be limited to sending and to one domain, and HTTPS cannot be
  downgraded the way STARTTLS can.
  - A small sender interface has one provider adapter, Resend by default,
    and a console sender for local mode.
  - Other adapters are follow-ons.
- **Registration flow** (device style; RFC 8628 is the pattern):
  1. The CLI posts the email. The relay returns a registration id, a short
     user code, a polling interval and an expiry, and the CLI keeps a
     private polling secret that never appears in the email.
  2. The email link opens a GET page showing the user code. Only a POST
     from its Confirm button verifies, so link scanners cannot.
  3. The CLI polls with its secret and receives the relay token once the
     registration is confirmed.

## Scope

- **In**:
  - the relay package skeleton: the ASGI app, configuration from the
    environment only, structured logs that never contain secrets or email
    bodies, and health checks;
  - the PostgreSQL schema and migrations for accounts, registrations and
    tokens. The design chooses the migration tool;
  - registration and verification as above:
    - single-use, high-entropy, short-lived verification tokens, stored only
      as hashes and compared in constant time;
    - the same answer whether or not an email is known;
    - email built from fixed content, with no caller-supplied text in it;
    - the address validated, and headers built safely;
  - rate limits per IP and per address on registration and email sends,
    with cooldowns;
  - issuing, listing and revoking relay tokens (stored hashed), and deleting
    an account;
  - the relay's versioned HTTP envelope.
    - Every response carries one code from a closed relay vocabulary. The
      design decides how it relates to publish-core's outcome vocabulary and
      how both packages share it without the relay importing the whole of
      `fitdocs`.
    - No free text crosses the wire.
  - the email sender interface, the Resend adapter, and the console sender
    for local mode, which refuses to bind to anything but loopback;
  - the fitdocs client side:
    - a relay connector with an instance URL that defaults to
      `https://api.fitdocs.ai`;
    - the `fitdocs connect` registration flow, which needs an auth-style
      decision: a new style, or `LOGIN` with a stepwise issuer (connectors
      amendment);
    - token storage, revocation and account deletion commands;
  - deployment:
    - the Dockerfile, and a Compose file for the relay plus `postgres` built
      `FROM postgres:N` with WAL-G;
    - a DNS-only `api` A record and TLS on the droplet (Let's Encrypt; the
      design picks the reverse proxy);
    - a DigitalOcean Cloud Firewall that never exposes 5432;
    - the backup and restore runbook, and a restore drill;
    - the SPF/DKIM/DMARC records for the sending domain;
  - the operator's obligations as a service that holds email addresses: a
    privacy policy and a support contact, published on the fitdocs.ai site
    (docs-site amendment), plus account deletion on request;
  - steering amendments:
    - `tech.md`: the CLI still has no server, and the repository also holds
      a separately deployed relay;
    - `structure.md`: the `relay/` directory;
  - a distribution amendment: the wheel and sdist exclude `relay/`, enforced
    by the release gate.
- **Out**:
  - any publish target. `strava-publish` and `relay-intervals` add them to
    this relay;
  - paid plans, billing, social features;
  - a web dashboard beyond the verification pages;
  - more email adapters, and SMTP (follow-ons);
  - running several relay instances against one database.

## Boundary Candidates

- The account core (registration, verification, tokens) against delivery
  (the email sender) against storage (schema, migrations, backups).
- The relay service against the fitdocs client (the connect flow and token
  storage).

## Out of Boundary

- Any third-party OAuth, and any publish endpoint.
- Composing posts, and publish-core's CLI and ledger.

## Upstream / Downstream

- **Upstream**: connectors (the credential store, `http.py`, auth styles)
  and publish-core's outcome vocabulary (a shared seam).
- **Downstream**:
  - `strava-publish` (Strava OAuth and publishing on the relay);
  - `relay-intervals`;
  - any future hosted feature that needs an account.

## Existing Spec Touchpoints

- **Extends**:
  - `connectors`: the relay connector and its auth style;
  - `distribution`: the relay is excluded from the release;
  - `docs-site`: the privacy policy, a self-hosting guide, and a
    `fitdocs connect` page for the relay;
  - steering: `tech.md` and `structure.md`.
- **Adjacent**: `intervals-connector`, the precedent for connector instance
  settings.

## Constraints

- **Secrets come from the deploy environment only.** That covers the email
  provider key, the database password, the token-hash pepper and (for
  `strava-publish`) the encryption key. None is ever in the repository,
  under the data root, or in a log.
- **Durability.**
  - The data directory is on a volume.
  - WAL archives go continuously to Spaces in another region.
  - Restore is rehearsed before the relay holds a real account.
  - One relay instance at a time.
- **The firewall.** Only 80/443 (and SSH, restricted) are open. The
  database port is never published, because Docker bypasses `ufw`.
- **Local mode cannot reach the public.** The console sender runs only when
  the relay is bound to loopback, so a public deploy cannot skip email.
- **The fitdocs side stays offline outside its commands.** Only
  `fitdocs connect`, the token commands and `fitdocs publish --yes` talk to
  the relay, through `connectors/http.py` with the composed User-Agent.
- **Licences.** Starlette BSD-3, FastAPI MIT, uvicorn BSD-3,
  psycopg LGPL-3.0 (installed unmodified), cryptography Apache-2.0/BSD and
  WAL-G Apache-2.0 are all compatible with the repository's MIT licence. A
  published image ships their licence texts.
