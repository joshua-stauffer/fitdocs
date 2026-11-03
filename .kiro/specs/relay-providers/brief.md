# Brief: relay-providers

## Problem

The relay's consent machinery is built for Strava alone. A second provider
cannot reuse it, and a deployment cannot register a provider of its own.
- **relay-intervals designed the lift** into `fitdocs_relay/targets/`, but
  its spec is gated on intervals.icu approving an OAuth app, so the lift
  waits on someone else's review.
- **The hosted Garmin provider (private) needs it now.** It also needs two
  things the design lacks:
  - **PKCE.** relay-intervals chose none, because the relay is a
    confidential client (`.kiro/specs/relay-intervals/research.md:343-344`).
    Garmin's OAuth 2.0 uses PKCE (S256) alongside a client secret
    (Garmin's public OAuth2 PKCE document,
    <https://developerportal.garmin.com/sites/default/files/OAuth2PKCE_1.pdf>).
  - **A way for an extension to register a provider** with its own webhook
    routes, environment rows and call budget.

## Current State

- **Strava-specific code:**
  - `ConnectFlow` names `STRAVA`, and `CALLBACK_PATH` is `/strava/callback`
    (`relay/src/fitdocs_relay/strava/connect.py:44,204,335`);
  - `Custody` (`strava/custody.py`) and the budget (`strava/budget.py:22-153`);
  - the webhook (`strava/webhook.py:20-64`, matched by a path secret,
    `strava/routes.py:302-326`);
  - the pages (`strava/pages.py`) and the policy;
  - `OFFERED_TARGETS=(STRAVA,)` (`routes.py:72`);
  - `StravaServices` (`app.py:99-110`) and per-route limits (`app.py:412`);
  - `target_secrets` (`serve.py:83-94`);
  - `reencrypt`, which lists only `STRAVA` (`custody.py:272-306`).
- **Already target-neutral:**
  - every storage area (each table has a `target` column; `TargetConnectionStore`,
    `storage/interface.py:216-306`);
  - `Keyring`, `account_key` and `context` (`crypto.py`, `strava/custody.py:54-62`);
  - `RecordStore` and `TargetsConfig`;
  - `target_route`, `connect_page_path` and the five connect codes;
  - on the fitdocs side, the bind pass (`connectors/settings.py:259-304`)
    and the `BrowserConsentClient` protocol.
- **relay-intervals' lift plan** (`design.md:405-470,1063-1170`):
  - `targets/config.py`;
  - `targets/connect.py`: a `ConsentProvider` with `target`,
    `service_name`, `connect_label`, `consent_text`, `policy_sections`,
    `authorize_url`, `complete` and `withdraw`, plus a multi-provider
    `ConnectFlow`;
  - `targets/vault.py` (`TokenVault`);
  - `targets/pages.py`, `targets/policy.py`, `targets/routes.py` and
    `targets/cli.py`;
  - on the fitdocs side, `connectors/relay_route.py` lifted out of
    `strava.py`, and `service_name` on `BrowserConsentClient`.
- **The extension seam** (`FITDOCS_RELAY_EXTENSIONS`, `RelayExtension`) adds
  token issuance only.
- **The environment contract** refuses any unknown `FITDOCS_RELAY_*` name
  (`contract.py`). `_WITH_ANY_TARGET` lists the client ids that enable the
  target-neutral rows ("a later target appends its client id",
  `contract.py:73-78`).

## Desired Outcome

- **The lift.** `fitdocs_relay/targets/` exists as relay-intervals designed
  it, and Strava runs as a built-in provider on it with no change in
  behavior.
- **Optional PKCE.** `ConsentProvider` supports S256 PKCE. The verifier is
  held in the connect session record, and the client secret is kept as
  well.
- **Extension-registered providers.** A `RelayExtension` can register a
  provider that declares:
  - consent text. Policy text is not a provider declaration: relay-legal-pages
    was shelved on 2026-11-03. A built-in provider's policy lives in the
    relay's built-in policy (Strava's today); a deployment's provider's
    policy lives with that deployment (the hosted static pages);
  - webhook routes under a secret path, each with its own body limit (at
    least 10 MB where a source needs it);
  - token custody through `TokenVault`, with the existing refresh lease;
  - an allow-list of the hosts its outbound calls and fetches may reach;
  - a call budget, on `BudgetStore`;
  - its own environment rows, which the contract accepts and documents
    instead of refusing.
- **The wire.** The relay's capabilities endpoint lists every offered
  provider. A provider's connect, poll and disconnect use the same wire
  routes as Strava's.
- **Key rotation.** `reencrypt` covers every provider's custody.
- **A test kit.** A fake provider and a provider test kit (pytest fixtures
  plus conformance checks for the seam) ship with the relay. Its own tests
  and the hosted provider both use them.
- **The fitdocs side:**
  - `connectors/relay_route.py` is lifted out of the Strava connector;
  - `BrowserConsentClient` gains `service_name`;
  - the CLI names a relay-offered provider without provider-specific code.

## Approach

- **Implement relay-intervals' lift** as designed, then extend it:
  - PKCE in `ConsentProvider`;
  - a `ProviderRegistration` that an extension returns: the provider, its
    routes, environment rows, host allow-list and budget;
  - a webhook route helper generalized from Strava's path-secret route.
- **Re-express Strava** through the same registration, as a built-in.
- **Keep the wire stable.** The design decides whether a provider that
  sends data in is still a "target" on the wire (`/v1/targets/<id>/...`),
  which needs no envelope change, or gets a new prefix.
- **Body limits** (viability, 2026-11-03):
  - `ROUTE_BODY_LIMITS` is honoured only when Strava is configured
    (`app.py:412`), so a relay without Strava would cap every webhook at
    64 KiB. Decouple per-route limits from Strava, and let a provider's
    registration add its webhook paths.
  - Read webhook bodies as raw bytes; Starlette's `form()` caps parts at
    1 MiB.
  - Bound concurrency on the large-body routes. `_admit` buffers whole
    bodies, and uvicorn has no body-read timeout.

## Scope

- **In**:
  - the `targets/` lift, PKCE, and extension-registered providers;
  - extension environment rows;
  - the webhook helper, host allow-lists and per-provider budgets;
  - Strava as a built-in provider;
  - `reencrypt` across providers;
  - the fake provider and the test kit;
  - the fitdocs-side `relay_route` lift;
  - docs in `docs/relay.md` for extension authors: the seam contract, not a
    recipe for any platform.
- **Out**:
  - held items, deposits and the fetch queue (relay-held-files);
  - any real provider beyond Strava;
  - Garmin;
  - intervals.icu's provider (relay-intervals);
  - storage schema changes. None is expected, because `target_connections`
    is already keyed by target; if one turns out to be needed, it takes the
    next free migration number.

## Boundary Candidates

- The `ConsentProvider` protocol, PKCE and the multi-provider `ConnectFlow`.
- `TokenVault` and the custody lease.
- Provider registration through the extension seam: routes, environment
  rows, allow-list and budget.
- The webhook route helper.
- The fake provider and the test kit.
- The fitdocs-side route lift.

## Out of Boundary

- What a provider does with a webhook beyond verifying and routing it. A
  deposit is relay-held-files'; Strava's deauthorization stays Strava's.
- Policy pages. relay-legal-pages was shelved on 2026-11-03; the relay's
  built-in Strava policy stays as it is, and the hosted deployment serves
  static pages.

## Upstream / Downstream

- **Upstream**:
  - relay-server: the seam, storage, the envelope and the contract;
  - strava-publish: the machinery being lifted.
- **Downstream**:
  - relay-held-files: providers deposit through it;
  - relay-intervals: it consumes the lift;
  - the hosted Garmin provider.

## Existing Spec Touchpoints

- **Extends**:
  - strava-publish: machinery lifted, with no change in behavior;
  - relay-server: the wrapper-seam version and environment-contract rows;
  - relay-intervals: its lift is delivered here, so its tasks shrink at the
    spec batch's cross-spec review;
  - connectors: the `BrowserConsentClient.service_name` and
    `relay_route` lift.
- **Adjacent**:
  - relay-held-files, which lands next and shares the route table and the
    contract.

## Constraints

- **Strava behavior is unchanged.** strava-publish's tests stay green, with
  only their imports moved.
- **Secrets.** Secrets and tokens are never logged. Outbound calls go only to
  a provider's declared hosts, through `outbound.py`, which the boundary
  guard keeps as the only network module.
- **Versions.** The wrapper seam is a versioned, breaking surface for the
  hosted wrapper: advance its version at main + 1, with a literal history.
  `relay_codes` stays append-only.
- **One serving instance.** The conformance suite runs on SQLite and
  PostgreSQL.
- **The public-text rule:** the docs, the fake provider and the tests name
  no real platform beyond Strava and intervals.icu, and carry nothing from
  Garmin's developer documentation.
