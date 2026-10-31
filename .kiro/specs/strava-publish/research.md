# Research & Design Decisions

## Summary
- **Feature**: `strava-publish`
- **Discovery Scope**: Complex Integration. A new external integration
  (Strava's OAuth, activities, uploads, webhooks and rate limits) on the
  relay, plus extensions of the connector framework, the CLI, the relay's
  storage, routes and deploy contract, and the activity-identity match
  rule. The full discovery process ran.
- **Downgrade**: research ran in-context. No subagent dispatch is available
  to batch writers, so the codebase analysis and the external research the
  design skill would delegate were done in this writer's own context.
  Public Strava developer pages were read for verification; no API call was
  made.
- **Key Findings**:
  - `resolve_credentials` receives an instance name and a connector, never
    the instance's settings (`connectors/credentials.py:391-397`), and
    publish-core's `prepare_target` resolves credentials through it. A
    Strava instance that borrowed its bound relay instance's token would
    need a new signature at every call site. Issuing the Strava instance
    its own relay token when its connection completes (a connection token)
    keeps every existing resolution path unchanged: the browser-consent
    style then resolves exactly as the relay-token style does.
  - `activity-identity`'s `pair_evidence` is not standard-library-only:
    `identity/matching.py:20-21` imports `fitdocs.identity.kinds` and
    `fitdocs.model`. Its strict tier, however, needs neither: it compares
    sport strings, aware datetimes and floats. Extracting that tier into a
    standard-library-only module, which `pair_evidence` then calls, lets
    the relay carry a byte-identical copy through relay-server's pinned-copy
    mechanism with no restatement.
  - The relay's envelope caps every request body at 64 KiB
    (relay-server design, `MAX_REQUEST_BYTES`), and an activity file is
    usually hundreds of kilobytes. Sending the file only on a second,
    upload request, made only when the first found no activity and uploads
    are enabled, keeps the athlete's track off the relay in the common case
    and confines the larger body limit to one route.
  - Strava's webhook events are not signed (developers.strava.com/docs/
    webhooks: the verify token is used only at subscription validation).
    A secret path segment is the only authenticator available; the relay
    uses the same secret as the verify token.

## Research Log

### The connector framework seams this spec extends
- **Context**: R5 gives strava-publish the driving of `OAUTH_BROWSER`, and
  relay-server's `run_disconnect` refuses it until then.
- **Sources Consulted**: `src/fitdocs/connectors/protocol.py` (`AuthStyle`
  146-155, `SUPPORTED_AUTH_STYLES` 157-159, `ConnectorSession` 277-301);
  `credentials.py` (`resolve_credentials` 391-485, the unsupported-style
  raise 482-485, `env_var_name` 131-133); `settings.py`
  (`load_connectors_settings` 242-317, the cross-instance pass
  `_check_credential_collisions` 225-240); `registry.py`
  (`validate_connector` 112-228, the OAUTH_BROWSER note 130-131);
  `connect.py` (`_env_override` 115-132); `cli.py` (the reserved-style
  refusal 1360-1364); `pull.py` (credential resolution 674, the instance
  error for a non-pulling instance 705-710). relay-server design.md
  ("DisconnectEngine", "RelayConnector and RelayClient", "CliRelay").
- **Findings**:
  - Every dispatch on `OAUTH_BROWSER` today is a refusal. The tests that pin
    the refusal are `tests/connectors/test_protocol.py:224-236` (the style
    set and the reserved set), `test_registry.py:579-585` (a reserved style
    needs no operation), `test_credentials.py:631-640` (resolution raises
    `NotConnectedError`), `test_cli_connectors.py:96-104, 350-362, 435-450`
    (the CLI exit-2 refusal), and `test_connect.py:128-147, 607` (`run_connect`
    refuses it). The last stays true: browser consent gets its own engine,
    and `run_connect` keeps handling only the personal-key and login styles.
  - The settings loader already runs one cross-instance pass after the
    per-instance checks (`_check_credential_collisions`). A second pass that
    checks and binds a Strava instance's `relay` key to a configured relay
    instance follows the same pattern, so every command that loads
    `[connectors]` refuses a dangling binding before any request.
  - `ConnectorSession.settings` is the instance's parsed settings
    (`protocol.py:286`). Binding the relay instance's `RelaySettings` into
    the Strava instance's settings at load time is what lets the publish
    operation, which receives only a session, know the relay URL.
- **Implications**: browser consent is a fifth driven style whose credential
  is a relay token the relay issued for this instance; the binding pass and
  the consent engine are new; publish-core's `prepare_target` and
  `list_targets` need no change.

### Transport, single attempt and the relay client
- **Context**: R4 and R9: strava-publish's fitdocs-to-relay publish request
  is single-attempt, through publish-core's mode; relay-server's
  `RelayClient` has no attempt flag and relies on `CallMode.AUTH`.
- **Sources Consulted**: `connectors/http.py` (`send` 278-283: AUTH sends
  once; `_send_data` 297-317: DATA retries 429, 5xx and transport failures
  up to three attempts; `post` 337-354); publish-core design.md
  ("ConnectorChanges": `HttpRequest.single_attempt`, `HttpClient.post(...,
  single_attempt=False)`; "Targets": `prepare_target` builds a
  `CallMode.DATA` client).
- **Findings**:
  - The publish operation runs on the session publish-core builds, whose
    client is in DATA mode. A publish or upload request sent through it
    unmarked would be retried up to three times.
  - `HttpClient.get` takes no attempt flag in publish-core's design, but
    `HttpClient.send` takes any `HttpRequest`, including one with
    `single_attempt=True`.
- **Implications**: `RelayClient` marks every request it builds
  `single_attempt=True` (POST through `HttpClient.post(...,
  single_attempt=True)`, GET through `send`). Every relay call is then one
  transport call whatever client its caller built, which is also what
  relay-server's Req 15.2 states. No second mechanism is added.

### The match rule and its shareability
- **Context**: R10 asks whether `pair_evidence` can be reused in the relay
  through a pinned copy, and notes it is not standard-library-only.
- **Sources Consulted**: `src/fitdocs/identity/matching.py` (imports 13-21;
  constants 39-46; `_within` 124-128; `pair_evidence` 139-187);
  `tests/identity/test_boundary.py:99-108` (the module list);
  `tests/test_public_api.py:1393-1410` (the identity seam pin and the
  submodule list); `src/fitdocs/compose/alignment.py:18`,
  `identity/planning.py:18`, `identity/pages.py:27`, `sync.py:230` (the
  importers of `matching`).
- **Findings**:
  - The strict tier is: same sport, both starts present, starts within
    `START_TOLERANCE_S` (1 s); then, with both distances present, distances
    within `max(DISTANCE_TOLERANCE_M, DISTANCE_TOLERANCE_FRACTION x longer)`;
    otherwise, with a distance missing and both elapsed times present,
    elapsed within `ELAPSED_TOLERANCE_S` (10 s). Comparisons are inclusive
    through `_within`.
  - The device tier needs a device digest, and the shifted tier needs a
    source kind; Strava's listing has neither, so only the strict tier
    applies remotely.
  - The early `return None` when either elapsed time is missing (line 168)
    also guards the shifted tier, which needs both elapsed times. Moving the
    strict tests into a function and keeping that return after it leaves
    every result unchanged.
- **Implications**: a new `fitdocs.identity.strict` holds the four strict
  constants, `within` and `strict_match`; `matching` imports and re-exports
  the constants (its `__all__` and `_IDENTITY_SURFACE` stay true) and calls
  `strict_match`. The relay's copy is byte-identical. This is an
  activity-identity amendment whose proof is the existing identity suite
  passing unchanged.

### Strava's OAuth, scopes and revocation
- **Context**: the connect flow, scope checking and disconnect.
- **Sources Consulted**: developers.strava.com/docs/authentication
  (checked 2026-10-31); the brief.
- **Findings**:
  - Scopes include `activity:read_all` and `activity:write`; the callback
    carries `code`, `scope` (possibly narrower than requested) and `state`,
    or `error=access_denied`. `approval_prompt` is `auto` (default) or
    `force`.
  - The token exchange answers `access_token`, `refresh_token`,
    `expires_at` (epoch seconds) and an `athlete` summary.
  - "Once a new refresh token is returned, the older refresh token is
    invalidated immediately."
  - `POST /oauth/revoke` takes `token` (access or refresh) and client
    credentials in HTTP Basic; revoking one revokes the other; it answers
    200 even for an unknown token. `/oauth/deauthorize` still exists, and
    the page says revoke will be the only supported endpoint from
    2027-06-01.
  - Access tokens travel in `Authorization: Bearer`.
- **Implications**: request exactly `activity:read_all,activity:write`;
  require both in the callback's `scope`; serialize refreshes per
  connection; revoke with the refresh token on disconnect; keep only a
  keyed hash of the athlete id.

### Strava's activities, uploads and limits
- **Sources Consulted**: developers.strava.com/docs/uploads,
  developers.strava.com/docs/rate-limits, the brief (API reference
  findings for `GET /athlete/activities` and `PUT /activities/{id}`).
- **Findings**:
  - Uploads answer `id`, `external_id`, `error`, `status` and
    `activity_id`; poll no more than once a second; mean processing under
    2 s; a duplicate is reported in `error` as English text naming the
    other activity. The page states no maximum file size.
  - Limits: overall 200 per 15 minutes and 2,000 per day; non-upload 100
    and 1,000; windows reset at :00, :15, :30, :45 and at midnight UTC;
    `X-RateLimit-Usage` and `X-ReadRateLimit-Usage` report usage as
    "15-minute,daily"; over-limit answers are 429, and a request refused by
    the short-term limit still counts toward the daily one.
  - Webhooks: one subscription per application; validation GET with
    `hub.mode`, `hub.challenge`, `hub.verify_token`, answered with
    `{"hub.challenge": ...}`; events must get 200 within two seconds;
    deauthorization carries `updates: {"authorized": "false"}` and
    `owner_id`; the subscription is created, viewed and deleted with client
    credentials (the view and delete calls carry the client secret in the
    query string).
- **Implications**: the upload is classified by structure (`activity_id`
  set, `error` set, neither), never by text; a duplicate is resolved by
  re-listing; the budget windows align with epoch-aligned fixed windows of
  900 and 86,400 seconds, which is exactly relay-server's window rule; the
  subscription commands mark their address secret.

### Strava's brand guidelines
- **Sources Consulted**: developers.strava.com/guidelines (checked
  2026-10-31).
- **Findings**: "Connect with Strava" must link to Strava's
  `/oauth/authorize`; the button is 48 px tall at 1x; button assets are
  offered for download but the page does not state they are required; an
  activity link reads "View on Strava" and must be identifiable as a link;
  interoperability is "Powered by Strava" or "Compatible with Strava"; the
  Strava name may not appear in the application's name or be more
  prominent than it.
- **Implications**: the control is a link straight to the authorization
  address, rendered as fitdocs-written text at the guideline height; the
  relay ships no Strava artwork (structure.md's rule against redistributing
  a third party's restricted material); docs say "Compatible with Strava".

### Relay seams consumed
- **Sources Consulted**: relay-server design.md ("StorageInterface" and its
  extension rule, "AnswersGlue, CoreRoutes, AppFactory", "DeployContract and
  ConfigLoader", "SharedEnvelopeCodec", "SharedCopySync", "IdentityService",
  "RateLimiter", "Data Contracts — Envelope v1"); relay-server tasks.md 4.1
  and 4.3; publish-core design.md ("Outcomes", "RequestTypes", "Targets").
- **Findings**:
  - `RecordStore` gives namespaced, expiring records with an atomic
    `take_record`; extension namespaces match `^[a-z][a-z0-9-]{0,31}$`, so a
    core namespace containing a dot cannot collide with one.
  - `count_request` uses a fixed window starting at `now - now % window_s`,
    but checks one key at a time and always increments; a Strava call draws
    on several limits at once and must not count where it is refused.
  - `OFFERED_TARGETS` is a static tuple and capabilities list it whole;
    Req 5.5 says no target is listed while none has been added.
  - `decode_answer` checks the `outcome` key's shape only; membership is
    the consuming target's.
  - `relay_envelope.py` imports only `.relay_codes` relatively, so a module
    in `src/fitdocs/connectors/` can share the relay's copy directory only
    by importing siblings that are also copies there. `outcomes.py` lives in
    `src/fitdocs/publish/`, so no shared connectors module can import it.
- **Implications**: connect sessions reuse `RecordStore`; the budget is a
  new all-or-nothing operation; capabilities list a target only when it is
  configured; the Strava wire module carries the per-route outcome sets as
  literal strings, and tests on each side hold them inside the vocabulary.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A. Strava instance borrows its relay instance's token | Credentials resolve through the bound relay instance | One token per principal | Needs a settings-aware `resolve_credentials` at every caller, including publish-core's | Rejected |
| B. Strava instance copies the relay token at connect | The relay token is written into the Strava instance's file | No relay change | Copies a secret the user may hold only in the environment; goes stale when the relay token is revoked | Rejected |
| C. Relay issues a connection token at grant | The poll that sees the grant returns a new relay token for the same principal | Self-contained instance; offline ready state; publish-core unchanged; disconnect revokes it | One more token per principal; a lost poll answer orphans a token until the next connect replaces it | Selected |
| D. The relay connector itself becomes the Strava target | A relay instance gains a target setting | No new connector | Capabilities are per connector, so every relay instance would become a publish target; leaves `OAUTH_BROWSER` undriven | Rejected |

## Design Decisions

### Decision: A Strava connector bound to a relay instance, with its own connection token
- **Context**: Req 1, 2, 11; R5; brief "connect once, to the relay token's
  principal".
- **Alternatives Considered**: options A, B and D above.
- **Selected Approach**: a built-in `strava` connector (browser-consent
  style, three publish capabilities). Its required `relay` key names a relay
  instance; the settings loader binds that instance's `RelaySettings` into
  the Strava settings. `fitdocs connect` starts a connect session with the
  relay instance's token; the relay binds the session to that token's
  principal and, at grant, issues a connection token for that principal,
  which becomes the Strava instance's own credential.
- **Rationale**: every existing credential path (`resolve_credentials`,
  `list_targets`, `prepare_target`, `run_disconnect`'s absent-file row)
  works unchanged; the ready state is offline and meaningful.
- **Trade-offs**: a lost granted answer leaves a valid token nobody holds
  until the next successful connect revokes it; the relay instance must be
  connected first.
- **Follow-up**: relay-intervals binds an intervals instance to a relay
  the same way.

### Decision: The strict rule extracted and pinned, not restated
- **Context**: Req 6.3, 15.2; R10.
- **Alternatives Considered**: 1. a relay-side restatement with a
  behavioural cross-check test; 2. extracting a standard-library-only core.
- **Selected Approach**: option 2 (`fitdocs.identity.strict`).
- **Rationale**: byte equality is a stronger guarantee than a table of
  cases, and it uses the mechanism that already exists.
- **Trade-offs**: a refactor of a carefully tuned module; mitigated by
  keeping every existing identity test unchanged and green.

### Decision: Two requests, file only when needed
- **Context**: Req 5.1, 5.4, 12.3; the 64 KiB envelope cap.
- **Selected Approach**: a publish request without the file; an upload
  request, with the file base64-encoded in the envelope, only after a
  not-found outcome on an upload-enabled instance. The relay re-resolves on
  the upload request before uploading.
- **Rationale**: data minimization, a single large-body route, and the
  common case (an already-synced activity) costs one request.
- **Trade-offs**: an upload costs two relay requests and two listings.

### Decision: No Strava cache at all
- **Context**: POL §6.2 allows a cache of at most 7 days; Req 10.5, 12.3.
- **Selected Approach**: the relay keeps no cached activity id; `/go/`
  resolves on every click.
- **Rationale**: retention is then satisfied trivially, and no sweep job is
  needed for Strava Data.
- **Trade-offs**: each click costs one listing, bounded by the redirect
  headroom and the client limit.

### Decision: A storage-level refresh lease with generation compare-and-swap
- **Context**: Req 4.3-4.5, 14.2; rotation invalidates the old refresh
  token at once.
- **Selected Approach**: `claim_refresh` takes a lease (id, expiry) only
  when the connection's generation matches and no live lease exists;
  `swap_tokens` writes new ciphertexts and increments the generation only
  when the generation and lease match; definitive refusals delete with the
  expected generation.
- **Rationale**: correct across threads and processes on both backends,
  testable in the conformance suite.
- **Trade-offs**: a refresh whose answer is lost after Strava rotated
  leaves a dead connection (the athlete reconnects). Documented.

### Decision: The budget as one all-or-nothing storage operation
- **Context**: Req 9.
- **Selected Approach**: `spend_budget(charges, now)` increments every
  charged window only when every one stays within its ceiling. Each Strava
  call charges the application's overall windows (and the non-upload
  windows unless it is the upload itself), and the principal's own share of
  each. A link resolution uses a lower ceiling on the non-upload windows, both the
  application's and the principal's own (Step 3.5 review finding 3), and the
  relay serves a `robots.txt` that disallows `/go/`.
- **Rationale**: no refused call is counted, concurrent requests cannot
  overshoot, and fairness and headroom are ceilings, not separate
  mechanisms.

### Decision: The privacy policy and consent text live in the relay package
- **Context**: Req 16; R10 (no website edit; operator-configurable).
- **Selected Approach**: fixed fitdocs text in `fitdocs_relay.strava.
  policy`, rendered at `/privacy` and on the connect page with the
  operator's name and support contact from the environment; an operator may
  point the pages at their own policy address instead. `docs/relay.md`
  states the Strava application field value and summarizes the policy; a
  test binds its section list to the policy's sections.
- **Rationale**: a self-hoster runs their own Strava application and needs
  their own policy page; the text is versioned with the code that it
  describes.

### Decision: Controller ruling R11 applied
- **Context**: the intervals-publish Step 3.5 review produced three wave-2
  rulings.
- **Selected Approach**:
  - `connectors.strava` names `PublishCode` and `TARGET_CODES` through
    `fitdocs.connectors.protocol`'s re-export and imports nothing from
    `fitdocs.publish`; the relay keeps its pinned copy of the vocabulary.
  - `local_record_unreadable` is not used: neither fitdocs nor the relay
    keeps a local record of fetched Strava activities.
  - An upload never runs on unreadable identity state: the relay reaches
    the upload call only after a fully parsed, not-full listing, decrypted
    tokens and error-free storage reads, and fitdocs sends an upload request
    only after a definite `not_found` (requirement 7.8).
- **Note**: intervals-publish compares sport by passing the page's sport
  on both keys (accepted by R11). This spec compares Strava's sport type
  through the sport-family table, because Strava states one; a family gap
  fails safe (no match).

### Decision: Step 3.5 repairs and controller ruling R12
- The keyring precedes the configuration (crypto before config), since the
  configuration parses the encryption keys.
- `EnvVar` gains `required_with`, the deploy contract's way to say
  "required when the Strava client id is set"; the contract version stays 1.
- On the upload route, `unavailable` and `storage-unreachable` map to
  `unconfirmed`, because a non-envelope 5xx after the file was sent leaves
  the result unknown; the relay answers `unconfirmed` for any failure after
  its upload call.
- The fitdocs-sports literal lives in the shared wire module, pinned
  against `fitdocs.model.Sport` on the fitdocs side.
- R12: the live check is a maintainer procedure plus a record template; no
  session carries out a step that reaches the real Strava API.

## Synthesis Outcomes
- **Generalization**: the connect machinery (sessions, pages, callback,
  custody, revocation) is keyed by target id, and the storage operations
  take a target, so relay-intervals adds a provider rather than a second
  machinery. The browser-consent style is defined as "consent at the bound
  relay", which fits both targets. Only Strava is built.
- **Build vs. adopt**:
  - authenticated encryption is adopted (`cryptography`'s AES-GCM, the
    brief's choice) rather than built;
  - the OAuth device-authorization pattern (RFC 8628's user code, poll and
    expiry) is adopted for the CLI side, reusing relay-server's started and
    issued answer shapes;
  - the Strava HTTP client is built on the standard library's `urllib`,
    like fitdocs's own transport, rather than adding an HTTP library;
  - no OAuth library: the flow is three form posts.
- **Simplification**: no cache, no background sweep (nothing expires that
  is not already invisible), no per-athlete capacity enforcement (Strava
  enforces it at authorization), no retry of any write except one repeat of
  the idempotent update, no new publish outcome code.

## Risks & Mitigations
- **A sync service that shifts a start by more than one second** gives
  `not_found` (or, with uploads on, an upload Strava refuses as a duplicate,
  then `rejected`). Never a wrong match. Mitigation: documented; the strict
  rule's tolerance is activity-identity's measured one.
- **Session phishing**: an attacker can send a victim a connect page for
  the attacker's own session. Mitigation: the page shows the user code and
  says to continue only when one's own terminal shows it (relay-server's
  registration defence), and a session serves one browser only.
- **Lost refresh answer after rotation** breaks a connection. Mitigation:
  lease longer than the call timeout; definitive refusal answers
  `auth_rejected`, whose next step is to connect again.
- **Budget starvation** by one athlete. Mitigation: per-principal share.
- **Rotating the token-hashing secret** breaks the deauthorization match
  (account keys are keyed by it). Mitigation: documented as part of the
  existing statement that rotating the secret invalidates every relay
  token; the operator deletes principals or asks athletes to reconnect.
- **Terms risk** (POL §5.16 and the brief's other broad clauses) was
  accepted by the maintainer at discovery; the design limits the relay to
  fitdocs's own requests, one application and per-athlete tokens.

## References
- [Strava authentication](https://developers.strava.com/docs/authentication/) — scopes, callback, token rotation, revoke.
- [Strava uploads](https://developers.strava.com/docs/uploads/) — upload fields, status polling.
- [Strava rate limits](https://developers.strava.com/docs/rate-limits/) — limits, windows, headers.
- [Strava webhooks](https://developers.strava.com/docs/webhooks/) — validation, events, subscription calls.
- [Strava brand guidelines](https://developers.strava.com/guidelines/) — button, link and interoperability wording.
- [RFC 8628](https://www.rfc-editor.org/rfc/rfc8628) — the device authorization pattern the CLI side follows.
- `.kiro/specs/strava-publish/brief.md` — the API Agreement and API Policy findings with sources.
