# Research & Design Decisions

## Summary
- **Feature**: `relay-intervals`
- **Discovery Scope**: Extension (a second relay target on strava-publish's
  machinery, and a second route for intervals-publish's target), with one
  external integration (intervals.icu OAuth and three activity endpoints).
- **Process note (downgrade)**: research ran in-context. A batch writer
  cannot dispatch subagents, so the codebase analysis and the public-docs
  reading that `kiro-spec-design` would delegate were done in this session.
  No API call was made.
- **Key Findings**:
  - An auth style is a property of a connector, not of an instance
    (`ConnectorInstance.connector`, `settings.py:82-90`; `resolve_credentials`
    switches on `connector.auth_style`, `credentials.py:391-409`). A relay
    route therefore wants its own connector kind; per-instance auth styles
    would reach every credential, registry, connect, disconnect and pull
    site.
  - publish-core's ledger loader refuses a target's ledger whose `connector`
    differs from the configured connector (publish-core design
    "PublishLedger"), so switching an instance between two connector kinds
    would stop `fitdocs publish` for every target with exit 2. A small
    publish-core amendment (a shared ledger identity) is needed for the
    route setting to be usable.
  - intervals-publish keeps its answer table, identifier rule, listing
    window, match and upload parsing as private helpers of `intervals.py`,
    which imports half the connectors package. The relay can run them only
    if they move into a standard-library-only leaf it can pin.

## Research Log

### The code the feature builds on (verified at e39c24e3, which is main ef14cd9c plus the four upstream specs)
- `src/fitdocs/connectors/settings.py:82-90`: `ConnectorInstance(name,
  connector, lookback_days, settings, wellness)`. The connector key resolves
  to one registered connector, or the instance's own name when absent
  (`:113-132`). One cross-instance pass runs after the per-instance checks
  (`:225-240`, called at `:316`); strava-publish adds `_bind_relay_instances`
  after it.
- `src/fitdocs/connectors/credentials.py:391-485`: `resolve_credentials`
  switches on `connector.auth_style`; the stored file's `connector_id` must
  equal the connector's (`:416-420`, `:463-467`). `env_var_name` is
  `FITDOCS_CONNECTOR_<INSTANCE>_<FIELD>` (`:131-133`), so a relay-routed
  instance named `intervals` reads `..._INTERVALS_TOKEN` while the direct
  one reads `..._INTERVALS_API_KEY`: no collision on a route switch.
- `src/fitdocs/connectors/registry.py:54`: connector ids match
  `^[a-z0-9][a-z0-9-]{0,63}$`; `intervals-relay` is valid.
- `src/fitdocs/connectors/ledger.py:467-508`: `load_ledger(data_root,
  instance, *, connector_id)`; an absent file is an empty ledger; a file
  naming another connector raises `LedgerError` (`:506`). A relay-routed
  instance that reuses a direct instance's name finds that instance's pull
  ledger (connector `intervals`).
- `src/fitdocs/connectors/http.py:82-87, 297-317`: the DATA mode retries
  429 and 5xx and transport failures up to three attempts; the default
  timeout is 30 s. strava-publish marks every relay request
  `single_attempt=True` (its RelayClientAmendment), so no relay request from
  fitdocs is repeated.
- `src/fitdocs/connectors/intervals.py:62-66`: `API_BASE`, `SELF_ATHLETE`,
  `STRAVA_SOURCE`; `:557-566` `_auth_headers` (the Basic credential, direct
  route only).
- `src/fitdocs/identity/__init__.py` imports nothing, so importing
  `fitdocs.identity.strict` (strava-publish) loads only the standard library.
- `tests/connectors/test_docs.py:661-670`: the neutral scan finds URL hosts
  only (`_URL_PATTERN`); a module that names intervals.icu in prose without a
  URL needs no exemption. The direct link base stays in `intervals.py`, so
  the new shared leaf names no URL.
- `tests/connectors/test_docs.py:102-122`: `_EXPECTED_HEADINGS`, which
  intervals-publish extends with `### Publishing` inside `## intervals.icu`.

### Upstream designs consumed (authoritative: the four design.md files)
- **strava-publish**: `ConnectFlow` (`strava/connect.py`), `Custody`
  (`strava/custody.py`), `Keyring` (`crypto.py`), `Outbound`
  (`outbound.py`), the three storage areas and `NNNN_target_custody`,
  `TargetsConfig` with `load_targets_config(environ, *, any_target)`,
  `EnvVar.required_with: str | None`, `relay_targets.py` (route builder,
  `PublishFacts` codec, field and outcome sets), `BrowserConsentClient`,
  `RelayBound`, `_bind_relay_instances`, `run_browser_connect`,
  `PUBLISH_MAPPING`/`UPLOAD_MAPPING`, `identity.strict`. The connect
  session, claim, state and poll mechanics are target-neutral but live under
  `strava/`, and `browser_connect` stores `connector_id="strava"`
  literally; the CLI and disconnect lines name Strava.
- **intervals-publish**: the resolution order (recorded link, pull record,
  facts check, listing match by external id then strict rule without sport,
  Strava-import rule), `ANSWER_CODES` by `CallKind` and `AnswerClass`, the
  update (`PUT /activity/{id}`, retried), the upload (`POST
  /athlete/0/activities?external_id=`, single attempt) confirmed by an
  update, `local_record_unreadable` when the pull record cannot be read.
- **relay-server**: the envelope and codes, `OFFERED_TARGETS`,
  `RESERVED_PREFIXES`, `ROUTE_BODY_LIMITS` (strava), the storage extension
  rule (area protocol, both backends, next `NNNN` pair, conformance with
  the coverage marker), `TokenService`, `RelayClient`.
- **publish-core**: `PostPublisher`, `PublishRequest(publication_id, post,
  subject, recorded_link)`, `PublishResult`, `TARGET_CODES`, the ledger
  (`connector` must match), the link rule (`valid_link`, kept only beside a
  landed code), the re-export of `PublishCode`/`TARGET_CODES` through
  `connectors.protocol` (R11).

### intervals.icu OAuth (public sources, read 2026-10-31)
- **Sources**: forum topic "Intervals.icu OAuth support" (t/2759) and the
  forum topic "API access to Intervals.icu" (t/609), as relayed by the brief
  and re-read for this design; no request was made to any API.
- **Findings** (paraphrased):
  - Authorization at `https://intervals.icu/oauth/authorize` with
    `client_id`, `redirect_uri`, `scope` and an optional `state`; PKCE (S256)
    optional. A refusal returns `error=access_denied`.
  - Token exchange: a form POST to `https://intervals.icu/api/oauth/token`
    with `client_id`, `client_secret` and `code`, within two minutes of the
    redirect. The answer carries `token_type`, `access_token`, `scope` (the
    granted scopes) and `athlete` with `id` and `name`.
  - Scopes are `<AREA>:READ` or `<AREA>:WRITE` for ACTIVITY, WELLNESS,
    CALENDAR, CHATS, LIBRARY and SETTINGS; WRITE implies READ; several are
    comma-separated.
  - Access tokens only, no refresh token, no stated expiry. One forum report
    of a 403 after a few hours is unresolved in the thread. A new
    authorization issues a new token that replaces the previous one.
  - API calls send `Authorization: Bearer <token>`; athlete `0` is the
    token's athlete.
  - Revocation: `DELETE https://intervals.icu/api/v1/disconnect-app` with
    the token.
  - Redirect URIs must be registered on the application's management page.
  - An application shows "Pending" until intervals.icu approves it, and
    OAuth does not work before then; no approval criteria are published.
  - Limits (forum, draft wording): a daily limit of 100 calls per user, up to
    500 users, with a floor of 5,000 and a cap of 50,000 for the
    application, resetting at midnight UTC; a rolling fifteen-minute limit of
    one eighth of the daily, floor 2,500; 10 calls per second per IP address.
    Current figures show on the application's management page.
  - Terms (effective 2025-10-23): any lawful purpose, commercial included;
    no relay or AI clause; Garmin attribution where Garmin-sourced data is
    shown (the relay shows none).
- **Implications**: no refresh machinery; deletion on refusal instead of on
  a refresh failure; the scope check happens after the exchange (the
  callback carries no scope); the account key comes from the exchange's
  `athlete.id`; a budget with per-athlete and application windows; the
  fifteen-minute window is rolling, so fixed windows count at half of it.

### Assumptions to be confirmed (TBC-R*, the maintainer's live check)
Each is behind one function and its tests.
- **TBC-R1**: the scope string `ACTIVITY:WRITE` permits listing, updating
  and uploading the athlete's activities, and the exchange's `scope` field
  lists the granted scopes comma-separated with that spelling.
- **TBC-R2**: `client_id`, `redirect_uri`, `scope` and `state` are the only
  authorization parameters needed (no `response_type`); the callback
  carries `code` and `state`, or `error`.
- **TBC-R3**: the exchange accepts the form `client_id`, `client_secret`,
  `code` (whether `grant_type=authorization_code` and `redirect_uri` are also
  required), and answers JSON with `access_token`, `token_type` `Bearer`,
  `scope` and `athlete.id` (a string or an integer).
- **TBC-R4**: a token has no expiry and stays usable until it is revoked or
  replaced by a newer authorization of the same application; a dead token
  answers 401. If it answers 403, the custody's deletion rule is amended.
- **TBC-R5**: `DELETE <api>/disconnect-app` with the token answers 2xx, and
  the token answers 401 afterwards.
- **TBC-R6**: the activity endpoints behave for a Bearer token exactly as
  for the personal key (intervals-publish TBC-P1 to TBC-P5 carry over).
- **TBC-R7**: the limit figures above; whether the OAuth endpoints count;
  whether the per-athlete figure binds per athlete; what a 429 carries.
- **TBC-R8**: the redirect URI must equal a registered one exactly.
- **TBC-R9**: the client id is 1-128 characters of `[A-Za-z0-9._-]`.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A. Separate connector kind | `intervals-relay`, `OAUTH_BROWSER`, publish only; the route is the instance's `connector` key | Every framework site keeps "one connector, one style"; no pull capability to mask; credential fields differ naturally; strava-publish's engine, binding and disconnect rows apply as they are | Switching routes changes the connector id, which the publish ledger checks | Selected, with the shared ledger identity |
| B. Per-instance auth style | The intervals connector declares both styles; `route = "relay"` picks one | One connector id; the ledger check holds as is | `ConnectorInstance` gains a style; credentials, registry (both operation sets), connect and disconnect dispatch, `list_targets`, the binding pass, `_check_no_credential_keys`, the collision check and the bare-pull selection (a relay-routed instance must not pull) all change; connectors Req 1.7's one-style rule breaks | Rejected |
| C. `route` key resolved by the settings loader to a second connector | A hidden alias in `_resolve_connector` | Reads nicely | A special case in a generic loader; still two connector ids, so the ledger issue remains | Rejected |

| Option | Sharing the intervals.icu rules with the relay | Notes |
|--------|------------------------------------------------|-------|
| 1. Shared stdlib leaf, pinned | Move the table, id rule, window, parsing, match core, upload answer and request shapes from `intervals.py` into `connectors/intervals_rules.py`; the relay runs its byte-identical copy | Selected: one definition, the existing cross-check enforces it |
| 2. Relay restatement plus cross-check test | The relay writes its own table; a test compares | The fitdocs suite cannot import relay code without the relay's dependencies; a comparison test checks only what it compares |
| 3. Pinned copy of `intervals.py` | — | Impossible: it imports `errors`, `http`, `protocol`, `ledger` |

## Design Decisions

### Decision: a separate connector kind, chosen by the instance's `connector` key
- **Context**: the route is per instance and direct is the default.
- **Selected Approach**: option A. `[connectors.intervals]` with no
  `connector` key is the direct connector (the settings loader resolves the
  instance's own name); `connector = "intervals-relay"` with `relay =
  "<relay instance>"` is the relay route.
- **Rationale**: the framework's existing per-instance selector is the
  `connector` key; every downstream site keys on the connector.
- **Trade-offs**: the switch changes the connector id, which publish-core's
  ledger check would refuse (next decision); a stray `relay` key on a
  direct instance is ignored (intervals-connector Req 2.4), which the docs
  call out, because refusing it would change the direct route.

### Decision: a shared publish-ledger identity (publish-core amendment)
- **Context**: publish-core refuses a ledger whose `connector` differs from
  the configured connector, which would make a route switch exit 2 for every
  target.
- **Alternatives Considered**: tell athletes to edit or delete the ledger
  (loses the digests and links, so every page posts again); per-instance
  auth styles (rejected above).
- **Selected Approach**: an optional connector protocol,
  `PublishLedgerShared.publish_ledger_connector`, naming the connector whose
  ledger identity the connector's instances use. `IntervalsRelayConnector`
  declares `"intervals"`. publish-core's `fitdocs.publish.targets` maps each
  configured target to `ledger_connector(instance)` before loading ledgers,
  so both routes read and write `connector = "intervals"`.
- **Rationale**: the records are valid on either route: the same service,
  the same activity identifiers, the same link and label, the publication id
  that both routes use as the external identifier.
- **Trade-offs**: one protocol and one function in publish-core; the
  mismatch check still refuses every other pairing.

### Decision: fitdocs does the local steps; the relay does the remote steps
- **Context**: the relay cannot read the pull ledger; the direct route's
  order is link, pull record, facts check, listing.
- **Selected Approach**: fitdocs gathers the known activities (the
  recorded link's id, then the pull record's id), answers `ambiguous` from
  an ambiguous pull record and `activity_facts_missing` when nothing is
  known and the facts are absent, and sends the known activities in order.
  The relay updates them in order, then checks the facts, lists and
  matches. fitdocs alone decides whether an upload request is sent (uploads
  on, pull record readable or absent, base file intact).
- **Rationale**: the same order and the same codes as the direct route;
  an unreadable pull record still bars the upload (R11) because fitdocs
  never sends the upload request then.
- **Parity repair (Step 3.5 review, controller ruling)**: the direct route
  updates the recorded link's activity before it reads the pull record, so
  a page with a recorded link and an ambiguous pull record is `posted` when
  the link's activity takes the update. The first draft answered
  `ambiguous` locally before any request. Now fitdocs sends the link alone
  with `known_only: true`; the relay updates only the known activities and
  answers `not_found` without a facts check or a listing when none takes
  it; fitdocs maps that `not_found` to `ambiguous`. A shared case file
  (`relay/contract/intervals-cases.json`) that both suites run pins equal
  codes on both routes for every resolution state.
- **Trade-offs**: at most two identifiers in a request; the relay keeps no
  record of them.

### Decision: two routes, the upload route lists again
- **Selected Approach**: `publish` (no file) and `upload` (the file),
  as Strava's target does; the upload route lists and matches again before
  uploading, because seconds pass between the two requests.
- **Trade-offs**: one more listing call on the upload path (four calls in
  all for a first-time upload).

### Decision: the relay returns the activity identifier, fitdocs builds the link
- **Context**: publish-core lets intervals.icu's direct link reach the page;
  R4 allows it across the relay boundary for intervals.icu only.
- **Selected Approach**: a landed answer carries `data.activity_id`,
  validated against the shared identifier rule on both sides; fitdocs builds
  the link with the direct route's own `activity_link`. The relay never
  sends a URL.
- **Rationale**: the same link as the direct route, built by the same
  function, from an identifier that cannot carry text; the ledger then
  records it, so the next publish sends it back as a known activity.

### Decision: the intervals.icu rules in one standard-library leaf
- **Selected Approach**: option 1. `src/fitdocs/connectors/intervals_rules.py`
  holds `CallKind`, `AnswerClass`, `SUCCESS_STATUSES`, `ANSWER_CODES` (code
  values as strings, since the leaf cannot import `fitdocs.publish`),
  `answer_class`, `answer_code`, the identifier rule, the listing window,
  path, fields and parser, `match_listing` (taking the strict predicate),
  the upload answer parser, the multipart and update bodies and the request
  paths. `intervals.py` imports it; the relay pins it.
- **Why the strict predicate is injected**: the leaf lives in `connectors/`
  and `identity.strict` in `identity/`; a relative import works in only one
  of the two layouts. Each side builds the predicate from its own
  `strict_match` (fitdocs's module or its pinned copy) in a few lines, and
  each side's tests run the same case table.
- **The direct route switches to `strict_match`**: with `device=None`,
  `kind=None` and the page sport on both keys, `pair_evidence(...) is
  Evidence.STRICT` holds exactly when `strict_match` holds (strava-publish's
  MatchingAmendment calls `strict_match` for the strict tier, and the device
  and shifted tiers cannot fire). Both routes then call the same function.

### Decision: lift the target-neutral relay machinery (strava-publish amendment)
- **Selected Approach**: a new relay package `fitdocs_relay/targets/` gets
  `config.py` (`TargetsConfig`), `connect.py` (`ConnectFlow` over a
  `ConsentProvider` protocol), `vault.py` (sealing, account keys,
  re-encryption across targets), `pages.py`, `policy.py` (common sections
  plus per-target groups), `routes.py` (connect, poll, disconnect, the
  connect page, the callback, `/privacy`) and `cli.py` (`reencrypt`,
  `new-encryption-key`). Strava keeps its provider, refresh lease, budget,
  resolver, publisher, webhook, `/go/` and their routes. On the fitdocs side
  `connectors/relay_route.py` takes the consent operations and the two
  relay-answer mapping tables from `strava.py`.
- **Rationale**: a relay configured for intervals.icu alone must serve the
  connect pages, `/privacy` and `reencrypt` without Strava's services; an
  intervals module importing from `strava/` would make one target depend
  on another.
- **Trade-offs**: a refactor of landed Strava code inside this spec; every
  Strava test keeps every expected value, and may change only its imports,
  its setup and object construction, the target argument the shared
  operations now take, the `required_with` shape, the place of moved doc
  headings, and the privacy page's grouping (Req 14.2, widened after the
  Step 3.5 review).

### Decision: `required_with` becomes a tuple
- **Selected Approach**: `EnvVar.required_with: tuple[str, ...] = ()`,
  meaning "required when any of these is set"; the generic rows name both
  client ids; the docs render "with `A` or `B`".
- **Rationale**: one mechanism that a third target extends by appending a
  name; `DEPLOY_CONTRACT_VERSION` stays 1 because a Strava-only deployment
  behaves the same.

### Decision: no recorded expiry for intervals.icu tokens
- **Context**: strava-publish's `SealedTokens.access_expires_at` is an
  `int` and the column is NOT NULL; intervals.icu states no expiry.
- **Selected Approach**: make it `int | None` and the column nullable, in
  this spec's schema change pair `NNNN_target_expiry_optional` (PostgreSQL
  `ALTER COLUMN ... DROP NOT NULL`; SQLite table rebuild, which is safe
  because no table references `target_connections`).
- **Rationale**: absent data is `None`, never a fabricated value.
- **Follow-up**: if the controller folds the nullability into
  strava-publish's own pair before it is implemented, this pair is dropped.

### Decision: no refresh; a refused token deletes the connection
- **Selected Approach**: a 401 on any call made with the token deletes the
  connection (generation-checked) and revokes its connection token.
- **Rationale**: intervals.icu has no refresh token; a 401 means the athlete
  revoked access or a newer authorization replaced the token. Keeping a dead
  token helps no one.

### Decision: the budget
- **Selected Approach**: before each call, one all-or-nothing charge
  against the application's day (UTC), the application's fixed
  fifteen-minute window at half the configured rolling limit, and the
  principal's day; the upload and its confirming update reserved together.
  A 429 answers `rate_limited` and marks nothing, because intervals.icu's
  429 does not say which limit it hit (TBC-R7).
- **Rationale**: two fixed windows at half the rolling limit can never sum
  past it in any fifteen-minute span.
- **Rejected**: per-second pacing for the per-IP limit. One run sends pages
  one at a time, and a 429 from it costs only a `rate_limited` for that run.

### Decision: one repeat of a listing or an update
- **Selected Approach**: the relay repeats a listing or an update once on a
  5xx or a network failure, never after a 429, never an upload; fitdocs's
  direct transport makes up to three attempts. The code the final answer
  gives is the same on both routes; the docs state the attempt counts.
- **Rationale**: a 100-call daily budget per athlete.

### Decision: no PKCE, no webhook, no publication records
- **PKCE**: the relay is a confidential client (the code is useless without
  the client secret), and the claim cookie plus single-use state already
  bind the callback to one browser.
- **Webhook**: intervals.icu documents none for a revocation; the relay
  learns of it at the next 401.
- **Publication records**: the link is direct, so the relay has nothing to
  redirect and keeps no page-to-activity map.

### Decision: the approval gate
- **Selected Approach**: requirements 16.1, a design section, the
  "Implementation gate" record below, and the first task, which checks that
  record and, when it shows neither an approval nor a written decision to
  proceed, stops the whole run for a human (`STOP_FOR_HUMAN` in kiro-impl's
  terms, not a skippable BLOCKED); the first task of every later group
  depends on it, and no task is dispatched while it is unchecked.

## Synthesis
- **Generalization**: the relay's connect machinery becomes a
  target-neutral core with one provider per target; the fitdocs relay-answer
  mapping becomes one table for every relay target; the intervals.icu rules
  become one definition for two routes.
- **Build vs. adopt**: adopted unchanged: the envelope, relay tokens, the
  storage areas, the keyring, the outbound client, the budget store, the
  browser-consent engine, the binding pass, the disconnect rows, the strict
  rule, publish-core's ledger and link rule. Built: the intervals.icu
  provider, its API client, its publisher, its budget policy, its pages'
  words and policy sections, the fitdocs relay-routed connector.
- **Simplification**: no refresh lease, no webhook, no `/go/`, no
  publication records, no per-second pacing, no PKCE, no new storage area,
  no new relay code, no new publish code.

## Risks & Mitigations
- intervals.icu does not approve the application, or approves it late:
  the gate keeps implementation from starting; a self-hoster with their own
  approved application can still use the code.
- A live answer differs from the description (TBC-R1 to TBC-R9): each is
  behind one function; the maintainer's live check confirms them.
- Tokens turn out to expire after hours (the unresolved forum report): the
  athlete sees `auth_rejected` and connects again; the design is amended to
  say so (TBC-R4).
- The lift breaks a Strava behaviour: every Strava test keeps its
  assertions (imports and target arguments aside), as the lift task's
  done-criterion.

## Implementation gate
Status: **pending**. intervals.icu has not yet approved the maintainer's
OAuth application (applying is a maintainer action). The maintainer records
here, as a dated line, either "approved" or "decision: implement before
approval". Nothing else goes here: no client id, no secret.

## Live-check findings
None yet. The maintainer's procedure (`relay/LIVE_CHECK_INTERVALS.md`)
records into `relay/LIVE_CHECK_INTERVALS_RECORD.md`; confirmed or
contradicted TBC-R items are summarised here as shapes and codes only.

## References
- intervals.icu forum, "Intervals.icu OAuth support", topic 2759 (read
  2026-10-31).
- intervals.icu forum, "API access to Intervals.icu", topic 609 (rate-limit
  posts, read 2026-10-31).
- intervals.icu API Terms and Conditions, forum topic 114087 (effective
  2025-10-23), as relayed by the brief.
- `.kiro/specs/strava-publish/design.md`, `.kiro/specs/intervals-publish/design.md`,
  `.kiro/specs/relay-server/design.md`, `.kiro/specs/publish-core/design.md`.
