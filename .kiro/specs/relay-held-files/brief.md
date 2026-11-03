# Brief: relay-held-files

## Problem

Push-only sources deliver when the athlete is offline, but fitdocs pulls
only when the athlete runs it. Nothing in between can hold the data:
- **The database is the relay's only state, by contract** (relay-server
  Req 7.8 and Req 10.3; the "State" rule, `docs/relay.md:322-330`).
- **The wire is JSON** with 64 KiB answers (`relay_envelope.py:44-45`), and
  has no binary path.
- **The relay does no background work.** Everything happens inside a
  request (`app.py:393-399`, `serve.py:97-168`).
- **`fitdocs pull` may not contact a relay** (relay-server Req 11.6,
  `requirements.md:258`; pinned by `tests/connectors/test_cli_relay_pull.py:71`).
- **Pull lists and fetches, but cannot acknowledge.** `ActivityPuller` is
  `protocol.py:416-425`, and `PULL_ACTIVITIES` is declared non-mutating
  (`protocol.py:129-135`).

Some push sources also send a notice instead of the data. The notice
carries a short-lived, single-use download link, and the receiver must
answer within seconds before fetching. Fetching at pull time would lose
files.

## Current State

- **Storage:**
  - `Storage` combines the area protocols (`storage/interface.py:385-397`);
  - SQLite and PostgreSQL backends are chosen by URL
    (`storage/__init__.py:18-36`);
  - migrations live at `migrations/<backend>/NNNN_slug.sql`
    (0001 initial, 0002 target custody);
  - conformance is in `relay/tests/conformance/`, with every `Storage`
    member covered (`test_coverage.py:16`) on both backends, PostgreSQL
    required in CI (`.github/workflows/relay.yml:36-65`).
- **Encryption:** AES-256-GCM through `cryptography`
  (`relay/src/fitdocs_relay/crypto.py`). Sealed values look like
  `v1.<keyid>.<b64>` and are bound to a context string.
- **Size caps:** outbound provider responses are capped at 8 MiB
  (`outbound.py:23`). The fitdocs transport caps a response at 64 MiB
  (`connectors/http.py:89`), and `MAX_FIT_BYTES` is 16 MiB
  (`relay_targets.py`).
- **Pull on the fitdocs side:**
  - `run_pull` and `_pull_one` (`connectors/pull.py:623,1049`) list, fetch,
    check `is_fit`, dedup by sha, deliver into `<inbox>/<instance>/`
    (`delivery.py:131-190`), and save the ledger in a `finally`.
  - Bare pull skips non-pulling relay instances (Req 11.5).
- **Connector instances:** `OAUTH_BROWSER` instances bind to a
  `RELAY_TOKEN` instance (`connectors/settings.py:259-304`). Nothing
  forbids `OAUTH_BROWSER` together with `PULL_ACTIVITIES`.

## Desired Outcome

**Relay.**
- **Held-item store:**
  - Metadata lives in the database: principal, provider, the provider's
    item id, kind (activity or wellness), supersede key, sha256, size,
    received time and state.
  - Bytes live in an object store behind a port with two backends: a local
    directory (the default) and S3-compatible storage through an `[s3]`
    extra, selected by URL.
- **Encryption.** Every object is encrypted with the relay key ring before
  it leaves the process, bound to principal, provider and item.
  `reencrypt` covers held items.
- **Deposit API for providers:**
  - idempotent by the provider's item id;
  - a supersede key keeps only the latest item (a day's summary re-sent as
    the day fills in).
- **A durable fetch queue for notice-style sources:**
  1. record the notice;
  2. answer;
  3. fetch once, with the user's token, through the provider, to its
     allow-listed hosts;
  4. resume after a restart.

  A fetch that cannot finish in time becomes a code reported at the next
  list.
- **Retrieval routes** are served to the principal's own connection token
  only: list held items, download one, and acknowledge one or many.
  Acknowledging evicts.
- **A hold limit,** off by default. When on, items older than N days are
  evicted and reported as expired at the next list. Turning it on is one
  setting.
- **Deletion cascades** remove held items and tokens at once on:
  - disconnect;
  - a provider's deregistration event;
  - a permission withdrawal, per kind;
  - principal deletion;
  - operator revocation.
- **The deploy contract:**
  - state is the database plus the object store;
  - new environment rows;
  - readiness covers the object store;
  - `DEPLOY_CONTRACT_VERSION` advances, and the changelog marks the change
    as breaking;
  - backup and consistency semantics: the database references objects, and
    orphaned objects are swept.
- **Conformance** runs on SQLite and PostgreSQL × the local and S3 backends
  (an S3 emulator in CI).
- **The policy** gains a held-data section through relay-legal-pages,
  covering:
  - encryption;
  - eviction on retrieval;
  - "may be deleted after 30 days";
  - the deletion triggers.

**fitdocs.**
- **A relay-source connector:**
  - It is `OAUTH_BROWSER`, bound to a relay instance by the existing bind
    pass.
  - It pulls activities and wellness through the relay.
  - It names its provider from the relay's capabilities, with no
    provider-specific code.
- **Pull:**
  1. list held items;
  2. download each;
  3. deliver it into the inbox (sha dedup as today);
  4. save the ledger;
  5. acknowledge.
- **A new acknowledge operation in the connectors protocol.** It changes
  remote state, and runs only after a durable delivery.
- **The pull report** shows expired and failed fetches as codes.
- **`fitdocs disconnect`** removes the provider connection, and with it the
  held items.
- **Statements.** relay-server Req 11.5 and 11.6 are amended for
  relay-source instances. Every network statement is rewritten (R9).

## Approach

- **A domain-level `HeldItemStore` area on `Storage`,** with the next free
  migration number on both backends (relay-intervals adds no schema). Plus
  an `ObjectStore` port, not a SQL layer. The S3 adapter's client is the
  design's choice, informed by the viability check (below).
- **Background work runs in-process, for one replica.** The design picks
  between Starlette background tasks after the response and a
  lifespan-started worker draining a database-backed queue. It defines
  graceful shutdown either way.
- **Downloads use a binary route,** outcome in headers, or a stated
  envelope exception. The answer shapes go in a shared standard-library
  wire module, which joins `SHARED_MODULES` as a pinned copy.
- **The fitdocs connector reuses the pull engine,** with the acknowledge
  step after `deliver` and the ledger save.

## Scope

- **In**: every item under Desired Outcome. Docs: `docs/relay.md` (storage,
  the contract, backup) and `docs/connectors.md` (relay-source instances).
- **Out**:
  - any real provider;
  - parsing held items on the relay;
  - publishing held items;
  - a general file API;
  - per-user encryption;
  - enforcing the hold by default;
  - several replicas;
  - the hosted bucket.

## Boundary Candidates

- The `HeldItemStore` area and its migration.
- The `ObjectStore` port with its two backends, and the encryption wrapper.
- The deposit API and supersession.
- The fetch queue and the background runner.
- The retrieval wire and its routes.
- The hold limit and the cascades.
- The deploy-contract change.
- The fitdocs connector and the acknowledge operation.
- Network statements and docs.

## Out of Boundary

- Provider registration, consent and webhooks (relay-providers).
- The wellness format (wellness-interchange). Held wellness items are
  interchange files.
- Policy composition (relay-legal-pages). This spec contributes one
  section.

## Upstream / Downstream

- **Upstream**:
  - relay-providers: the provider seam, allow-lists and budgets;
  - wellness-interchange: the wellness item format;
  - relay-server: storage, conformance and the contract;
  - connectors: the pull engine, delivery and the ledger.
- **Downstream**: the hosted Garmin provider; other push sources later.

## Existing Spec Touchpoints

- **Extends**:
  - relay-server: Req 7.8, 10.3, 11.5, 11.6 and 4.5; the conformance
    discipline; `DEPLOY_CONTRACT_VERSION`;
  - connectors: the acknowledge operation, relay-bound pulling instances,
    and the network statements;
  - steering: `tech.md`'s relay paragraph and "Network and Credentials",
    plus `structure.md`. Each is appended after whatever clauses are present
    at landing.

  Amendment numbers are the next free ones at landing.
- **Adjacent**: relay-intervals, which keeps its own Req 1.10 (relay-routed
  intervals.icu instances never pull).

## Constraints

- **Eviction only after a durable delivery,** and acknowledging is
  idempotent. A crash between download and acknowledge re-delivers the item,
  and sha dedup absorbs it.
- **No silent loss.** Record a notice before answering. Fetch once. Resume
  after a restart. Report what expired or failed.
- **Opaque bytes.** The relay never parses, indexes or derives from a held
  item.
- **Every answer is a fitdocs code** (`relay_codes`, append-only). No
  platform text crosses the wire.
- **Size limits.** Raise outbound and download caps deliberately, for files
  up to the source's real ceiling.
- **The local relay stays serverless.** SQLite plus a local directory needs
  no database server, object server or Docker.
- **The public-text rule.** The fetch queue, notices and fixtures are
  described generically: no platform's payload shapes, and nothing from
  Garmin's developer documentation.
- **Pins.** Literal pins move at main + 1, and the CLI command count is
  unchanged unless a command is added.
