# Brief: connectors

## Problem

The athlete moves `.fit` files into the inbox by hand. HealthFit exports
land in an iCloud folder and are copied over. Garmin rides are exported from
Connect one at a time. Anything the phone-side store never received (a ride
after HealthFit stopped getting Garmin data, a run only on Stryd) is missed
unless the athlete notices.

The athlete wants a configured tool that fetches every file they do not yet
have. The same tool should later push to platforms: posts to Strava;
activities, descriptions and planned workouts to intervals.icu. It should
also pull thresholds and plans back. None of that later work is this spec,
but this spec's protocol, state and credential store must not need
rebuilding to admit it.

## Current State

- **The inbox is the ingestion interface.**
  - Configuration: `[inbox]` (`src/fitdocs/inbox.py:228-277`), with keys
    `path`, `settle_seconds`, `ignore`, `disposition` and `processed_dir`.
  - Candidates are selected recursively for `.fit`, skipping any
    dot-prefixed path component (`select_candidates`, 563-597).
  - A stability check stats every file twice, and an unreadable file is
    deferred, not failed (`sync.py:750-763`).
  - Disposition is LEAVE (the default) or MOVE, gated on the archive copy
    existing.
  - Under LEAVE, every drain re-reads and re-hashes every file ever dropped
    (queue `2026-09-17-inbox-drain-leaves-source-fit-in-inbox`).
- **The only network code is `tiles.py`.** It uses stdlib `urllib` with an
  explicit User-Agent (`_user_agent`, 252-271), a 10 s timeout, one attempt
  and a cache-first design. Its engine sees only a Protocol with an
  injectable `fetch` (279-344). Tests stub the network three ways
  (`tests/test_tiles.py:490, 557`, `tests/test_route_maps_e2e.py:345`), and
  a socket guard blocks the rest (`tests/test_determinism.py:124, 226`).
  "Only network module" is stated at `cli.py:98-102`, `sync.py:41-52` and
  `tiles.py:7`, and import-purity guards ban `urllib` elsewhere
  (`tests/test_contract.py:1345`, `tests/performance/test_purity.py:525`).
  The user docs make the same claim: "every other operation runs fully
  offline" (`docs/configuration.md:74, 93`).
- **No secret handling exists.** There is no keyring, dotenv, getpass or
  token store. `os.environ` is read only for `FITDOCS_DATA`.
- **Tool state lives in `.fitdocs/`**, which is owned and has no
  `AGENTS.md`. `quarantine.py` is the pattern for a state file: versioned
  TOML, sorted, atomic write-if-different, keyed by sha.
- **The data root may be a git repository** (`docs/ownership-contract.md:671-693`).
  `fitdocs.toml` is read, never written, by fitdocs.
- **CLI.** `pull`, `fetch`, `connect`, `login` and `auth` are free. `sync`
  is the drain. `sources` would collide with the managed key. Config errors
  go through `_config_error` (`cli.py:1000-1010`, exit 2). Every writing
  command is registered in `WRITING_ENTRY_POINTS`
  (`tests/test_confinement.py:815`).
- **Plugins** are one kind only today (`plugins.py:207`,
  `fitdocs.load_calculators`). A connector plugin kind is the plugin-api
  update that follows this spec.
- **Dependencies are frozen by tests** (`tests/test_determinism.py:672-712`,
  `tests/test_packaging.py:503-519`), and tech.md asks for a small
  footprint.
- **The packaged `fitdocs-workouts` skill** documents the routine `fitdocs
  sync --no-prompt` then `fitdocs check`. Its fence is pinned to exactly
  those two (`tests/test_agent_skill.py:681`), and every command a skill
  names must exist (`:614`).

## Desired Outcome

- **A published connector protocol.**
  - A connector declares an id, a display name, the auth style it needs, and
    its capabilities.
  - This phase implements one capability: **pull activities**. It is a
    listing of remote activities (a stable remote id, start time, sport and
    duration where known, and whether an original file is available)
    followed by fetching bytes for chosen ids.
  - The capability vocabulary names the follow-ons' kinds now: push
    activity, annotate remote activity, resolve remote activity, push
    planned workout, pull planned workouts, pull plans, pull thresholds,
    pull wellness. Each is marked reversible or irreversible, so a later
    push command can require dry-run or confirmation for irreversible ones.
  - Connectors never import render, load or metrics.
- **A ledger per connector** under `.fitdocs/`. It records each remote id
  fetched, with its archive sha and outcome, plus a watermark for
  incremental listing. It is keyed so a later push connector can map a page
  to a remote id. Versioned, atomic and sorted, like the quarantine file.
- **Credentials and tokens outside the data root.**
  - They live in a per-user config location (resolution order documented;
    an environment override for unattended runs), as 0600 files written
    atomically.
  - Rotating refresh tokens are saved before use of the new access token
    completes.
  - A service with a refresh flow never has its password persisted.
  - Secrets and signed URLs never appear in output, logs, reports or
    exceptions.
- **A connect command.** It authenticates one connector interactively
  (prompting without echo) and stores only what the connector needs to
  continue, recording the granted scopes. It reports a 429, MFA challenge or
  lockout verbatim, never retries, and names the next step.
- **A pull command.** It pulls from all configured connectors, or the named
  ones, with `--since` and `--dry-run`.
  - Each new file is delivered atomically into the inbox under a
    dot-prefixed temporary name, then renamed.
  - It optionally chains the drain, so one command fetches and ingests,
    which is the unattended cron/launchd path.
  - Failures are isolated per connector, and the report states per
    connector what was listed, fetched, skipped as already held, and
    failed. Exit codes follow the CLI's 0/1/2.
- **The folder connector.** A local directory (e.g. HealthFit's iCloud
  export folder) as a source. New files are copied into the inbox and
  tracked in the ledger. An unreadable or unmaterialized cloud file is
  deferred to the next run, never failed. A listing that undercounts (lazy
  cloud materialization) is caught by later runs because the ledger, not a
  watermark, decides. It needs no network, which makes it the framework's
  end-to-end test bed.
- **Pulled files do not accumulate.** Pulled files are not re-hashed forever
  under LEAVE: by a disposition the pull sets for its own deliveries, or by
  the ledger, which the design picks and states.
- **Honest steering.** The network statements and purity guards name the
  connector package. tech.md gains the network and credentials rules. The
  packaged skill's routine learns the pull, with its pins moved.

## Approach

A `fitdocs.connectors` package holds:
- the protocol and capability vocabulary;
- a small built-in registry, which the plugin-api update will extend with an
  entry-point group and the local-file fallback;
- the credential store;
- the ledger;
- an HTTP seam modeled on `TileSource`: stdlib `urllib`, an explicit
  User-Agent, timeouts, bounded backoff for data calls, and no retry for
  auth;
- delivery;
- the folder connector.

The CLI gains the connect and pull commands. Connector-specific specs
(`intervals-connector`, and user-installed plugins) implement the protocol.

## Scope

- **In**:
  - the protocol, the capability vocabulary (implemented: pull activities;
    named and reserved: the rest), auth-style declarations;
  - the ledger;
  - the credential and token store;
  - the HTTP seam;
  - delivery;
  - the connect and pull commands, and chaining;
  - the folder connector;
  - a `fitdocs.toml` connector table and its reader;
  - the revised network statements and guards;
  - tech.md;
  - the ownership-contract lines (credentials outside the root, ledger owned);
  - confinement registration;
  - the packaged skill routine;
  - `docs/` for configuring connectors.
- **Out**:
  - any specific online service (`intervals-connector`, plugins);
  - the plugin kind (a plugin-api update, after this spec);
  - identity and merge (`activity-identity`, `channel-merge`);
  - push, planned workouts, thresholds and plans (reserved names only);
  - a daemon, file watcher or scheduler;
  - OAuth browser-consent flows (reserved as an auth style, built with the
    first connector that needs them);
  - Stryd, Garmin-direct or Strava connectors.

## Boundary Candidates

- The protocol and capability vocabulary (the published surface).
- State: the ledger and the credential/token store.
- Transport: the HTTP seam, with its UA, timeouts, backoff and no-auth-retry.
- Orchestration: the connect and pull commands, delivery, chaining,
  reporting.
- The folder connector.

## Out of Boundary

- What a delivered file means for the corpus (the drain and
  `activity-identity`).
- Service-specific endpoints, auth details and quirks.

## Upstream / Downstream

- **Upstream**: `inbox` (delivery target, selection, disposition); `sync`
  (the drain chained after pull); `settings-foundation` (the per-table
  reader pattern); `wiki-contract` (owned `.fitdocs/`, confinement).
- **Downstream**:
  - `intervals-connector`;
  - the plugin-api connector kind;
  - user-installed connectors;
  - the follow-on push connectors (Strava, intervals.icu), which use the
    reserved capabilities, the ledger's page↔remote mapping, and the OAuth
    auth style.

## Existing Spec Touchpoints

- **Extends**:
  - `wiki-contract`: ownership-contract prose on credentials and the ledger;
  - `distribution`: the packaged skill routine and its pins;
  - `inbox`: only if the design adds a disposition for connector-delivered
    files; otherwise producer guidance only.
- **Adjacent**:
  - `plugin-api` (the kind comes next; this spec publishes what it
    validates);
  - `route-maps` (the other network user; the HTTP seam may share its UA
    helper but not its cache).

## Constraints

- **Stdlib only.** No new runtime dependency, so the frozen-dependency tests
  stay green.
- **Every request sends an explicit User-Agent.** intervals.icu's Cloudflare
  front returns 403 "error code: 1010" to `Python-urllib/3.x`.
- **The network is used only by the connect and pull commands.** Tests run
  against the injected seam with the socket guard active.
- **Authentication is never retried automatically.**
- **Secrets never live under the data root, never in `fitdocs.toml`, and
  never in output.**
- **No service is shipped whose terms forbid the access.** fitdocs is
  public. The protocol and docs are service-neutral, and no spec, doc or
  test here names an endpoint of a service that has not approved it.
- **Real use waits for identity.** Until `activity-identity` merges, a pull
  against a corpus holding phone-side copies duplicates pages. The docs say
  so while that is true.
- **Every writing command is registered with the confinement guard**, with
  a non-vacuous test.
