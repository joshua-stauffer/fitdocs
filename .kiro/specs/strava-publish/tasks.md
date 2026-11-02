# Implementation Plan

Prerequisites: `publish-core` and `relay-server` have landed on `main`
(this spec consumes `PostPublisher`, `PublishRequest`, `TARGET_CODES`,
`HttpRequest.single_attempt`, the relay package, its storage interface,
`RelayClient`, `run_disconnect` and the pinned-copy mechanism). It also
consumes the R11 re-export of `PublishCode` and `TARGET_CODES` through
`fitdocs.connectors.protocol`, which the controller folded into
publish-core.

Three streams meet in the integration group:
- **shared**: group 1, in order, first;
- **relay**: groups 2 to 4, in order;
- **fitdocs**: group 5, in order. It depends only on group 1 and may run
  alongside groups 2 to 4 in its own worktree. 5.9 also waits on 4.4.

Group 6 integrates and validates. Group 7 carries the documentation, gates,
steering and amendments. Task 8 writes the maintainer's live-check
documents only (R12); carrying out the live check is the maintainer's.

Rules for every task:
- **Both suites stay green.** Each task leaves the root gates (`uv run
  pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run
  mypy`) and the relay's gates (`uv run --directory relay pytest`, ruff,
  mypy) green on its own.
- **Every new assertion names the mutation it dies on** (tech.md, Testing).
  Run that mutation before reporting the task done.
- **No request to Strava, ever, in any test or session.** Strava is
  scripted at the relay's outbound seam; fitdocs is scripted at its
  transport. No implementation, review or validation session carries out a
  step that reaches the real Strava API or a relay connected to it (R12).
- **PostgreSQL is exercised, never skipped.** Every storage task, and every
  later relay task that touches storage, runs the relay suite with and
  without `FITDOCS_RELAY_TEST_POSTGRES_URL` (the second run with
  `FITDOCS_RELAY_REQUIRE_POSTGRES=1`), using relay-server's local recipe;
  the branch's relay CI run must be green.
- **No version constant moves in this spec.** It changes none of
  `CONTRACT_VERSION`, `DOC_VERSION`, `ENVELOPE_VERSION`, `SEAM_VERSION` and
  `DEPLOY_CONTRACT_VERSION` (relay-server's own `CONTRACT_VERSION` bump for
  `fitdocs disconnect`, R13.1, is relay-server's and already covers this
  spec's disconnect rows); no command is added, so the CLI command-count
  pins do not move.
  Any pin this spec adds is a literal, never derived from a live constant.
- **The website is not edited** (R9). Its copy is the queue item
  `.kiro/queue/2026-10-31-strava-publish-site-copy.md`, written with this
  spec.
- **Amendments** to other specs take the next free amendment number at
  landing. The schema change pair takes the next free `NNNN` (0002 if it
  lands first after relay-server).
- **Wording**: the only brand phrases are "Connect with Strava", "View on
  Strava" and "Compatible with Strava"; no document names a hosting or email
  provider or a deployment's infrastructure; nothing under `src/fitdocs/`
  or in the Strava section of `docs/connectors.md` names a Strava host; no
  text says who runs a command.

- [x] 1. Foundation: the shared modules and their pinned copies

- [x] 1.1 Extract the strict tier of the match rule into a standard-library-only module
  - Move the four strict tolerances and the inclusive comparison into the
    new strict-rule module, with the strict facts value and the strict
    match function exactly as design.md states them.
  - The match rule imports them from there, keeps every name in its public
    list and tolerance sources, and calls the strict match for its strict
    tier, after the device tier and before the existing early return when
    an elapsed time is missing.
  - Add the module to the identity package's module list
    (`tests/identity/test_boundary.py`) and to the public-API submodule list
    (`tests/test_public_api.py`).
  - New table tests for the strict match: start at exactly one second and
    just over it; distances at the five-metre floor and at twenty percent;
    a missing distance with elapsed at ten seconds and just over; both
    distances present but far apart with equal elapsed times (no match).
    Named mutations: `<` for `<=` in the comparison; comparing elapsed
    times when both distances exist.
  - Done when every existing identity, compose and fixture-merge test
    passes unchanged, the new table passes, an AST test shows the module
    imports only the standard library, and both named mutations red it.
  - _Requirements: 6.3, 15.2_

- [x] 1.2 Add the shared Strava wire module
  - The target route builder, the connect-page and link paths, the link
    field, the
    publication-id and sport formats, the title, description, file and
    upload-body bounds, the publish and upload field sets, the publish facts
    codec, and the two per-route outcome sets, as design.md states them.
  - Strict parsing: a naive start, a boolean or negative or non-finite
    number, an over-long title, a title with a control character, a
    description with a control character other than newline and tab, a
    file that does not decode, exceeds the bound or lacks the FIT marker,
    and any extra or missing field are each refused with fixed text.
  - A fitdocs test asserts both outcome sets are subsets of publish-core's
    target codes and pins them as literals, and pins the fitdocs-sports
    literal equal to the values of `fitdocs.model.Sport`.
  - Add the module to the connectors boundary test's module list and
    allowed-import table in this task (that test is exact equality over the
    files on disk).
  - Done when the codec tests and the connectors boundary test pass, an AST
    test shows only standard-library and relative sibling imports, and
    dropping the naive-start check, adding `not_found` to the upload set,
    or removing a sport from the literal reds a test.
  - _Requirements: 5.1, 5.3, 5.4, 5.6, 6.2, 15.3_

- [x] 1.3 Append the connect answers to the relay code vocabulary
  - Five codes after `answer-malformed`, all sent by the relay, with the
    statuses and explanations in design.md.
  - Keep relay-server's 22-value prefix pin; add a literal pin of all 27
    values in order. Add the five rows to `docs/relay.md`'s code table in
    the same task, since its binding test reads the vocabulary.
  - The vocabulary already has a pinned copy in the relay: run the sync
    command in this task so the copy matches.
  - Done when the vocabulary tests, the relay docs binding and the
    pinned-copy cross-check pass, and reordering two appended codes reds
    the new pin.
  - _Requirements: 15.4_

- [x] 1.4 Pin the three new shared modules into the relay
  - Append the outcome vocabulary, the Strava wire module and the strict
    module to the sync script's pairs, write the copies with the sync
    command, and extend the cross-check test to assert the three new pairs
    by literal beside relay-server's two.
  - The relay's boundary test keeps the shared copies to the standard
    library and relative siblings.
  - Done when the cross-check passes, the sync check mode reports no drift,
    and editing one byte of any new copy reds the cross-check.
  - _Requirements: 6.3, 15.1_

- [x] 2. Relay foundation: configuration, encryption, the outbound client and storage

- [x] 2.1 Seal tokens with rotating keys
  - Add the relay's encryption dependency to its manifest and lock, and the
    keyring: parse the configured keys, seal with the first key under the
    associated-data context, open with any configured key, and report a
    ciphertext's key id; generate a new key.
  - The boundary test allows the encryption library only in the keyring
    module.
  - Done when tests show a round trip, two seals of one value differing,
    and `None` for a wrong context, a tampered tag, an unknown key and a
    malformed value, and the relay image still builds and passes its smoke
    run on both backends in the branch's CI; named mutation: ignoring the
    context reds the wrong-context test.
  - _Requirements: 4.1, 4.2, 4.7_

- [x] 2.2 Configure the Strava target from the environment
  - Give relay-server's environment-variable record a `required_with:
    tuple[str, ...] = ()` field (required when any named variable is set),
    rendered in `docs/relay.md`'s Required column as "with `<variable>`",
    several names joined by " or "; the generic rows carry
    `("FITDOCS_RELAY_STRAVA_CLIENT_ID",)`, so a later target only appends
    its own client id.
  - Append the fourteen variables to the deploy contract's table with their
    required flag or `required_with`, default, secret flag and meaning, and
    append them to relay-server's literal full-table pin.
  - Load the targets configuration (with the keys parsed by the keyring's
    parser) and the Strava configuration: the client id enables the target;
    the "with Strava" variables are then required; any Strava variable
    without the client id, a missing required one, an invalid value
    (including an invalid encryption key list, or a link setting other than
    `activity` or `relay`), or a fifteen-minute limit
    above the daily one is a configuration error naming the variable and
    never its value.
  - Add the rows to `docs/relay.md`'s variable table in the same task, since
    its binding test reads the contract.
  - Done when configuration tests cover each refusal with a planted secret
    absent from every message, an unconfigured environment loads exactly
    as before, the contract pins (the full table with the tuples) pass, a
    two-name tuple renders with " or ", and dropping a row from the docs
    table reds the binding test.
  - _Requirements: 9.1, 10.7, 13.1, 13.2, 13.5_

- [x] 2.3 Add the relay's outbound client for provider calls
  - Requests with GET, POST, PUT and DELETE; secret headers added
    unredirected; a per-call timeout; a response cap; the relay's own
    User-Agent; failures raised with a fixed kind and never a URL, header
    or body; secret addresses never named.
  - The boundary test allows `urllib.request` and `http.client` only in
    this module.
  - Done when tests with a patched opener show the secret header absent on
    a redirect target, an oversize body refused, and an error message free
    of a planted secret query value.
  - _Requirements: 4.6, 12.2_

- [x] 2.4 Store target connections on both backends
  - Add the schema change pair (the three tables of design.md's physical
    model, identically named for both backends, with a nullable
    `access_expires_at`) and the connection area's
    put (with displacement of another principal's connection to the same
    account, and removal of the principal's link records when its account
    changes), get, list, delete with an optional expected generation, and
    delete by account. The area joins the combined storage protocol.
  - Conformance tests carry the coverage marker for every member,
    including concurrent puts of one account by two principals (one
    connection remains). The link-record effects of a put are asserted in
    2.7, once link records can be written.
  - The new schema change moves the schema counts: update relay-server's
    recorded `/readyz` exchange and every schema-count literal, by
    appended literals.
  - Done when the conformance suite passes on both backends (including a
    connection stored and read back with no access expiry), the migration
    parity test and the readiness replay pass, deleting a principal removes
    its connection, and the coverage check fails if one member's marker is
    removed.
  - _Requirements: 3.10, 11.5, 11.6, 11.8, 12.3, 14.1, 14.2, 14.3, 14.4_

- [x] 2.5 Issue connection tokens atomically
  - Add the connection-token issuance to the connection area: insert the
    new relay token for the principal, revoke the connection's previous
    token and record the new one, in one transaction; `None` without a
    connection. A same-principal put keeps the recorded token, so the next
    issuance revokes it. Deleting a connection revokes its token.
  - Tests build the new token records directly (the token service's
    prepare step arrives in 3.9) and observe revocation through the token
    store's lookup.
  - Done when conformance tests on both backends show concurrent issuance
    leaving exactly one unrevoked connection token, the earlier token's
    record carrying a revocation time after a second issuance (also after a
    same-principal re-put), and a delete revoking the current one.
  - _Requirements: 3.8, 11.5, 14.2_

- [x] 2.6 Rotate tokens atomically through a refresh lease
  - Add claim, swap and release to the connection area with the generation
    and lease rules of design.md; a swap without a lease succeeds only when
    no lease is live.
  - Conformance and concurrency tests: twenty threads claiming one
    generation leave one holder; a stale swap is refused and leaves the
    tokens unchanged; an expired lease can be claimed again; a delete with
    a stale generation changes nothing.
  - Done when these pass on both backends; named mutation: dropping the
    generation condition from the swap reds the stale-swap test.
  - _Requirements: 4.3, 4.4, 4.5, 14.2_

- [x] 2.7 Store link records on both backends
  - Add the publication area: put only for the owning principal, get by
    target and publication id; it joins the combined protocol.
  - Done when conformance tests on both backends show another principal's
    put refused, the owner's update kept, and records removed with their
    principal, with their connection, when another principal's put of the
    same account displaces the connection, and when the same principal's
    put changes the account.
  - _Requirements: 3.10, 3.11, 10.1, 10.6, 14.1, 14.4_

- [x] 2.8 Count the call budget on both backends
  - Add the budget area: an all-or-nothing spend over several windows with
    ceilings, the longest wait reported on refusal, ended windows deleted,
    and an exhaust that raises a window's count; it joins the combined
    protocol.
  - Concurrency tests: twenty one-unit spends against a ceiling of ten allow
    exactly ten; a two-charge spend whose second window is full leaves the
    first unchanged; principal-tagged rows go with their principal.
  - Done when these pass on both backends; named mutation: incrementing
    before checking every charge reds the all-or-nothing test.
  - _Requirements: 9.2, 9.6, 14.1, 14.2, 14.4_

- [x] 3. Relay Strava services

- [x] 3.1 Speak Strava's OAuth endpoints and classify every answer
  - The authorization address with exactly the two requested scopes, the
    state and `approval_prompt=auto`; the code exchange, the refresh and
    the revoke calls, with client credentials as Strava documents and
    access tokens only in the authorization header.
  - The classification of an answer into the failure classes, with the
    daily-spent flag read from the usage headers and discarded.
  - A scripted outbound fake for the whole relay suite, which records
    requests and serves canned answers, so no test can reach Strava.
  - Done when the classification table is pinned row by row, the exchange
    returns the athlete id only inside its value, and a sentinel in a
    scripted error body appears in no returned value.
  - _Requirements: 3.3, 3.6, 4.6, 8.1, 8.3_

- [x] 3.2 Speak Strava's activity, upload and subscription endpoints
  - The activity listing with its window, page size and full-page flag; the
    update of name and description only; the multipart upload with the
    publication id as external identifier; the upload state from its
    structure, never its text; the subscription view, create and delete,
    with their addresses marked secret.
  - Done when scripted tests show each call's method, path and fields, a
    listing entry missing a needed field giving `unreadable`, an upload
    with a non-null error reading as failed whatever its text, and the
    update request carrying no field but the two.
  - _Requirements: 6.1, 7.1, 7.3, 7.4, 7.5, 7.6, 11.9_

- [x] 3.3 (P) Spend the call budget before every Strava call
  - The application-wide and per-principal windows per call kind, the link
    headroom, the upload reservation, and marking windows spent after a
    rate-limit answer, as design.md states them.
  - Done when tests show a read refused at the principal's share while
    another principal is still allowed, a link refused at the application
    headroom while a publish is allowed, a principal's link refused at its
    own headroom while its publish is allowed, an upload reservation
    all-or-nothing, and a spent mark blocking the rest of its window.
  - _Requirements: 9.2, 9.3, 9.4, 9.5, 9.7_
  - _Boundary: StravaBudget_

- [x] 3.4 Pick one activity by the strict rule
  - The sport-family table, every family value pinned within the shared
    fitdocs-sports literal's pinned copy; the listing window; the pick through the pinned strict match, where a full
    listing, two matches and an unknown sport type never yield a pick and
    order never decides.
  - Done when tests cover none, one, two, a full listing and an unknown
    sport type; named mutation: returning the first of two matches reds the
    ambiguity test.
  - _Requirements: 6.1, 6.2, 6.4, 6.5_

- [x] 3.5 Keep custody of a principal's Strava tokens
  - Store a grant sealed under the connection's context with the keyed
    account hash; return a usable access token, refreshing through the
    lease near expiry, waiting on another holder, deleting on a definitive
    refusal, keeping the tokens on a transient one; withdraw (one revoke
    when the budget allows, then delete whatever happened); forget an
    account; re-encrypt every connection under the current key.
  - Done when tests over both backends show concurrent requests on an
    expiring token causing exactly one refresh call, a refused refresh
    deleting the connection and revoking its token, an undecryptable
    connection reading as not connected, a connection with no access
    expiry used without any refresh call, and re-encryption counting an
    unreadable row and leaving it unchanged.
  - _Requirements: 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.7, 4.8, 11.5, 11.10_

- [x] 3.6 Publish a post on Strava
  - The common checks (both facts absent, a publication id owned by another
    principal, a usable token), then the publish flow of design.md: one
    listing, the pick, one update with at most one repeat of the identical
    update on a server or network failure, and the publication record on a
    landed outcome; the publish deadline; the step-outcome table's list,
    update and refresh columns. A landed outcome is a `Landed` carrying the
    updated activity's page address, built by the same function the link
    resolution uses.
  - Done when scripted tests cover every publish branch and every row of
    those columns, a fake monotonic clock drives the deadline, a second
    repeat never happens, a publication id owned by another principal
    answers `rejected` with no Strava call, and a posted result carries the
    scripted activity's page address.
  - _Requirements: 5.6, 6.4, 7.1, 7.2, 7.6, 7.7, 8.1, 8.2, 10.1, 10.6_

- [x] 3.7 Upload a post on Strava when no activity exists
  - The upload flow of design.md: listing and pick again, the upload
    reservation, one upload never repeated, bounded status polling,
    re-resolution after a failed upload, the upload deadline, and the
    step-outcome table's upload and status columns. An uploaded or posted
    outcome is a `Landed` carrying the activity's page address.
  - The upload guard: an unparseable listing entry, an undecryptable token
    or a storage failure ends the request before any upload.
  - After the upload call, any later failure in the request (a storage
    error writing the link record, an unexpected exception) answers
    `unconfirmed`, logged by type only.
  - Done when scripted tests cover every upload branch and table row, the
    scripted upload endpoint is hit exactly once even when it answers a
    server error and never when the guard or the reservation ends the
    request, a storage failure after the upload answers `unconfirmed`, and
    a fake monotonic clock drives the deadline to `unconfirmed`.
  - _Requirements: 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 8.1, 9.3, 10.1_

- [x] 3.8 Resolve a link at click time
  - Look up the publication, its connection and a usable token, spend the
    budget for a link, list and pick, and return the activity page address
    or a refusal, storing nothing about the result.
  - Done when tests show one match giving the address, none or several or
    no connection giving not found, the headroom giving try later, and no
    storage write during a resolution.
  - _Requirements: 10.2, 10.3, 10.4, 10.5_

- [x] 3.9 Run connect sessions, the page claim, the callback and the poll
  - Add the token service's prepare step (a token generated but not
    stored), which minting also uses; the connection token carries the
    label `connection:strava`, so the operator's token listing shows what
    it is.
  - The connect flow over namespaced expiring records: start, the page
    claim by one browser, the callback checked before its state is taken,
    the scope check, the single exchange, the stored grant, and the poll
    that issues the connection token once and revokes the earlier one.
  - Done when tests show a second browser refused, a narrowed scope
    refused with no token stored, a callback from another browser leaving
    the state usable, a poll from another principal answering expired, and
    the granted answer issued exactly once.
  - _Requirements: 3.1, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11_

- [x] 3.10 Act on Strava's webhook
  - Validation answered only for the configured verify token; a
    deauthorization event forgetting its account; every other event
    acknowledged and ignored.
  - Done when tests show a deauthorization deleting the connection, its
    link records and its connection token, and an activity event leaving
    every table unchanged.
  - _Requirements: 11.6, 11.7, 11.10_

- [x] 3.11 (P) Write the pages, the consent text and the privacy policy
  - Every page of design.md, in fitdocs's words, with the support contact
    and policy link on each, the connect page in the stated order, and the
    "Connect with Strava" control as a link to the authorization address at
    the guideline height, with no Strava artwork; the page headers; the
    policy sections and the consent text.
  - Done when tests show every interpolated value escaped, each page
    carrying the support contact, the connect page's order, the operator's
    own policy address replacing the built-in one, and the only brand
    phrases being the allowed ones.
  - The consent text and the policy section "What the relay returns to
    fitdocs" follow the link setting, one fixed text for each.
  - _Requirements: 3.2, 3.5, 10.3, 10.4, 10.7, 12.4, 16.1, 16.2, 16.3, 16.4_
  - _Boundary: Pages, Policy_

- [x] 4. Relay HTTP surface and operator commands

- [x] 4.1 Extend the relay pipeline for targets
  - The services gain the configured targets and the Strava services, built
    when the target is configured; the capabilities endpoint lists only
    configured targets; the reserved prefixes gain the Strava paths; the
    body limit is per route; an answer's outcome must be a member of the
    pinned vocabulary; the log filter redacts the new secrets and request
    records carry the outcome.
  - The boundary test allows the web framework in the Strava routes module
    and keeps the pages and policy modules to the standard library.
  - Done when tests show capabilities without and with the Strava
    configuration, a non-member outcome answering `relay-failure`, the
    per-route limit lookup giving the upload route its larger bound and
    every other route the default, and a planted client secret absent from
    captured logs.
  - _Requirements: 12.1, 12.2, 13.3, 13.4, 15.3_

- [x] 4.2 Serve the Strava envelope routes
  - Connect, poll, publish, upload and disconnect, through the relay's
    authentication, per-token limit and strict request reader, each answer
    checked against its route's outcome set. Under the `activity` link
    setting a landed answer's data carries the activity's page address as
    `link`; under `relay` no answer carries it.
  - Done when test-client tests with scripted Strava show each route's
    answers, an unconfigured relay answering `not-offered` on each, a
    disconnect answering `ok` when the principal held no connection, a
    70 KiB body refused on the publish route but accepted on the upload
    route, a posted and an uploaded answer carrying `link` under `activity`
    and none under `relay`, and `/go/` redirecting under both settings.
  - _Requirements: 3.1, 3.8, 3.9, 5.1, 8.2, 10.7, 11.5, 12.1, 12.5, 13.3_

- [x] 4.3 Serve the browser pages, the link and the webhook
  - The connect page, the callback, `/go/`, `/privacy`, a `robots.txt`
    that disallows `/go/`, and the webhook address, rate-limited per client
    except a webhook request with the right secret, and the unavailable page
    while the relay is not ready.
  - Done when tests show the claim cookie's attributes, a 302 carrying only
    `Location` and the page headers, `/robots.txt` answering `User-agent: *`
    and `Disallow: /go/` only while Strava is configured, a wrong webhook secret answering not
    found and counting against the client, and every page free of a
    sentinel the scripted Strava returned.
  - _Requirements: 3.2, 3.4, 3.5, 3.6, 3.7, 10.2, 10.3, 10.4, 10.5, 11.6, 11.7, 12.4, 16.1, 16.3_

- [x] 4.4 Record the Strava exchanges and replay them against the relay
  - One recorded exchange per Strava envelope route and per new relay code,
    with visibly fake values, replayed by the relay suite byte for byte.
  - Done when the replay passes and editing one recorded byte reds it.
  - _Requirements: 12.1, 15.4_

- [x] 4.5 Provide the Strava operator commands
  - The webhook show, create and delete commands, re-encryption, and key
    generation, printing only fitdocs-written states, with the exit codes
    of design.md; append `strava`, `reencrypt` and `new-encryption-key` to
    the deploy contract's command list and its pin.
  - Done when command tests with scripted Strava show each state and exit
    code, the subscription addresses never printed, and re-encryption
    exiting 1 when a row is unreadable.
  - _Requirements: 4.2, 11.9_

- [x] 5. fitdocs client: the Strava connector, connect and disconnect

- [x] 5.1 Drive the browser-consent authentication style
  - Every style becomes supported; add the consent value types, the
    relay-bound settings protocol and the browser-consent operation
    protocol; the registry requires the three consent operations for the
    style; credentials resolve for it as for a relay token; the environment
    override covers it; the published surface appends the four names.
  - Move the pins listed in design.md: the supported-style set, the
    registry's reserved-style test (now a rejection without the
    operations), the credentials test (now a resolution), and retire the
    CLI's three reserved-style tests, keeping the refusal branch for any
    future reserved style.
  - Done when the connectors suite passes, the registry rejects a
    browser-consent connector missing each operation in turn, and dropping
    the style from credential resolution reds the new test.
  - _Requirements: 1.5, 1.6, 2.6_

- [x] 5.2 Bind each browser-consent instance to its relay instance
  - The cross-instance pass after the credential-collision check: the
    named relay instance must exist and use the relay-token style, and the
    instance's settings are bound to the relay instance's settings. Only
    browser-consent instances take part, so the existing settings pins stay
    green.
  - Update the settings module's docstring, which says one more pass runs
    across instances.
  - Done when settings tests show an unknown name and a non-relay instance
    each refused with the file, instance and key named and the configured
    relay instances listed, a successful bind carrying the relay URL, and
    no file read or written.
  - _Requirements: 1.3_

- [x] 5.3 Attempt every relay request exactly once
  - The relay client marks every request it builds single-attempt, and
    `post(route, fields, *, max_request_bytes: int | None = None)` refuses
    an encoded body over the bound before any request (`None` keeps
    relay-server's bound). These are relay-server amendments carried here
    (R13.3). Its imports, and its boundary row, do not change.
  - Done when a scripted 503 over a data-mode client sees one transport call
    for a GET and for a POST, and an over-bound body makes no transport
    call; named mutation (relay-server's, restated): dropping
    `single_attempt=True` from `post` sees three calls.
  - _Requirements: 5.5_

- [x] 5.4 Add the Strava connector's settings and consent operations
  - The settings (`relay` required, `upload` optional boolean, other keys
    ignored), the bind that accepts only relay settings, and the three
    consent operations over the relay client, with the page address
    composed by fitdocs and every secret registered with the redactor.
  - Add the module to the connectors boundary test's module list and
    allowed-import table in this task.
  - Done when tests over a scripted transport show each consent answer
    parsed, a started answer with a vowel user code treated as malformed,
    the boundary test passing, and the module's source naming no Strava
    host.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.4_

- [x] 5.5 Publish to Strava and register the connector
  - The publish operation: facts and bounds checks before any request, the
    publish request, the upload request only after `not_found` with
    uploads enabled, the file checks, both mapping tables, and the link
    only with a landed code: the answer's `link` when its data carries one
    (none when that value is not a string), otherwise the relay's `/go/`
    address.
  - The upload request is sent only after a definite `not_found` outcome,
    never after a malformed, failed or missing answer.
  - Register the connector in the package with its label "View on
    Strava"; append the package's boundary entry and the surface names (the
    connector names publish codes only through the protocol module's
    re-export and imports nothing from `fitdocs.publish`, which a boundary
    assertion pins); name
    `strava` in the connectors page's built-in list in the same task, since
    its pin reads the registry.
  - Done when both mapping tables are pinned row by row, a scripted
    non-envelope 502 on the upload route gives `unconfirmed`, an
    upload-route outcome on the publish route maps to `unavailable` with no
    upload request, no request is made for missing facts, an absent file or an
    oversize file, the upload request passes `MAX_UPLOAD_REQUEST_BYTES` as
    its bound, a landed answer with a string `link` gives that link, one
    without gives the `/go/` link, one with a non-string `link` gives none,
    without a `link` a loopback `http` relay URL gives a landed code whose
    link publish-core refuses (`link_refused`, no "View on Strava" link on
    the page), and the boundary, surface and preamble pins pass; named
    mutation: importing `PublishCode` from `fitdocs.publish.outcomes` reds
    the boundary assertion.
  - _Requirements: 1.1, 1.7, 5.1, 5.2, 5.3, 5.4, 5.6, 5.7, 5.8, 5.9, 5.10, 7.8, 8.4_

- [x] 5.6 Run the browser-consent connect loop
  - The engine of design.md: the relay instance's token first, one start,
    the started callback, polls at the stated interval, the local deadline,
    the store on grant, and the fixed next steps.
  - Add the module to the connectors boundary test's module list and
    allowed-import table in this task.
  - Done when tests with a scripted transport and fake clock show grant
    (file written, owner-only), refused, expired by the local deadline, a
    relay instance with no token (no request), and an interrupt (nothing
    stored).
  - _Requirements: 2.1, 2.2, 2.5, 2.6, 2.7, 2.8, 2.9_

- [x] 5.7 Disconnect a Strava instance
  - The disconnect rows for the style: one withdraw request with the stored
    token, the local-only removal with its note, and nothing to disconnect
    without a stored token.
  - Done when tests cover each row, an unknown-token answer removing the
    file with its note, any other answer keeping it, and the override never
    sent.
  - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [x] 5.8 Present Strava connect and disconnect in the CLI
  - The browser-consent branch of `fitdocs connect` with `--no-browser`,
    its refusals of `--register` and `--email`, `--no-browser` refused on
    other styles, the printed lines, the browser opener and its failure
    line, and the exit codes; disconnect results printed as for relay
    instances.
  - The started line is neutral: "NAME: open this address in a browser to
    connect this instance:" (R13.5); only the relay page says "Connect with
    Strava".
  - Done when CLI tests pin the printed lines, show no browser call with
    `--no-browser`, exit 2 for each refused flag before any request, exit 1
    when the relay instance has no token, and exit 130 on interrupt.
  - _Requirements: 2.3, 2.8, 2.9, 2.10, 11.1, 11.3_

- [x] 5.9 Decode the recorded Strava exchanges through the client
  - The fitdocs suite decodes every recorded Strava answer through the
    relay client and the Strava connector with a fake transport and asserts
    the code and the parsed data.
  - Done when the decoding test passes and editing one recorded code reds
    it.
  - _Requirements: 5.6, 8.4_
  - _Depends: 4.4_

- [x] 6. Integration and validation

- [x] 6.1 Hold the fitdocs-side guarantees with a Strava instance configured
  - The socket-guarded offline-commands test gains a Strava instance in its
    wired root; a bare and a named `fitdocs pull` make no request for it;
    `fitdocs publish --targets` shows it ready and not connected; the
    confinement test shows a Strava connect writing nothing under the data
    root.
  - Done when these tests pass, and a scripted relay request during
    `fitdocs pull` fails the socket guard.
  - _Requirements: 1.6, 1.8, 2.9_

- [x] 6.2 Prove nothing from Strava escapes the relay except the landed activity's link
  - A scripted Strava that plants one sentinel in every field and header,
    driven through connect, publish, upload, a link, a disconnect and a
    deauthorization on both backends.
  - Done when, under both link settings, the sentinel appears in no
    envelope answer, page, log record or database column outside the sealed
    tokens, no table holds an activity id or athlete id, and the scripted
    activity id reaches fitdocs only inside a posted or uploaded answer's
    `link` under the `activity` setting.
  - _Requirements: 12.1, 12.2, 12.3, 12.5_

- [ ] 7. Documentation, gates, steering and amendments

- [x] 7.1 Document the Strava connector
  - The Strava section of the connectors page with the four subsections of
    design.md, "Compatible with Strava", the settings table, the relay
    instance and public-address prerequisites, both mapping tables, what
    leaves the machine, the default relay's policy address, the link under
    each link setting, and that a loopback `http` relay set to `relay`
    gives no "View on Strava" link; heading rows added
    in page order; the neutral-scan entry gains the section.
  - Done when the connectors docs tests pass, the section names no Strava
    host, and deleting a mapping row from the page reds a binding test
    against the mapping tables.
  - _Requirements: 5.10, 16.4, 16.5, 17.1, 17.7_

- [x] 7.2 Document the Strava target for operators
  - The relay page's Strava sections of design.md, including the
    `required_with` rendering, the link setting and the relay instance URL
    matching the public address, and the policy summary bound to the policy sections by
    a test.
  - Done when the relay docs tests pass, removing a policy section from the
    summary reds its binding test, and the page names no hosting or email
    provider.
  - _Requirements: 4.9, 13.6, 16.1, 16.5, 16.6, 17.2, 17.7_

- [x] 7.3 Make every network statement name `fitdocs publish --yes` and the Strava host
  - Written to hold in either landing order with `intervals-publish`; each
    step is skipped where an earlier target already made it:
    - every statement that lists the network-touching commands names
      `fitdocs publish --yes`;
    - where a statement lists the commands making none (in `tech.md`, in
      its own sentence after the pinned no-request list, which stays
      unedited), it states that `fitdocs publish` without `--yes` and
      `fitdocs publish --targets` make none;
    - the connectors page's "What leaves your machine" gains the Strava line
      (its bound relay's URL, never Strava); this line is this spec's own.
  - Pins in `tests/connectors/test_network_statements.py` use the shared
    predicate `_names_publish_command(window)`, added only if absent, to
    require `fitdocs publish --yes` in every place, with one named mutation
    per place, plus a pin for the Strava line.
  - Done when the network-statement tests and the three existing `tech.md`
    list pins pass, and removing the command or the Strava line from any
    place reds its pin.
  - _Requirements: 17.3_

- [x] 7.4 Add the steering sentences
  - `tech.md` "Network and Credentials" gains the Strava sentence of
    design.md; `structure.md` gains the strict-module sentence; each is
    line-disjoint from other specs' edits.
  - Done when the steering pins still pass and the new sentences read as in
    design.md.
  - _Requirements: 17.4_

- [x] 7.5 Record the changelog entries
  - Root Unreleased (pinned through `unreleased_since(text, V0_2_0)`): the
    Strava connector described as compatible with Strava, `fitdocs connect
    --no-browser`, Strava disconnect, and browser consent supported. The
    relay changelog: a new section recording the Strava target, variables,
    routes, commands and schema change, marked additive, which restates
    deploy contract 1, envelope 1 and seam 1 so the newest-section pin stays
    green.
  - Done when the changelog pins pass and neither entry uses a brand phrase
    other than "Compatible with Strava".
  - _Requirements: 16.5, 17.5_

- [x] 7.6 Record the amendments in the affected specifications
  - connectors, relay-server and activity-identity, each with the items of
    design.md's Amendments Carried, worded like the earlier landed
    amendments and naming the pin that enforces each; distribution's Req
    10.4 amendment naming `fitdocs publish --yes`, skipped when an earlier
    target recorded it; confirm the site-copy queue item still names true
    lines.
  - Check that the browser-consent disconnect rows agree with relay-server's
    ownership-contract statement for `fitdocs disconnect` (R13.1); add no
    version bump.
  - Done when each requirements document carries its dated amendment
    naming strava-publish (distribution's only if no earlier target
    recorded it).
  - _Requirements: 15.2, 17.3, 17.6, 17.8_

- [ ] 7.7 Run the full validation sweep
  - Both suites and gates, the release build and artifact check, the site
    build and checks, the sync check mode, the relay workflow and image
    smoke on both backends, and a scan that the packaged skill names no
    target.
  - Done when every gate is green and the sync check reports no drift.
  - _Requirements: 17.7, 17.8_

- [x] 8. Write the maintainer's live-check procedure and its record template
  - Controller ruling R12: no implementation, review or validation session
    carries out any step that reaches the real Strava API or a relay
    connected to it (no Strava connect against a live relay, no publish to
    Strava, no authorization grant). This task writes documents only.
  - The procedure, for the maintainer to carry out against the maintainer's
    own Strava application and account: connect, publish an update to one
    activity, follow its link, disconnect. It states first that it writes to
    that real account, and lists what to observe at each step.
  - The record template: one row per step for the fitdocs code observed and
    a fitdocs-written note. A session fills it only with the codes the
    maintainer reports, never with Strava Data.
  - Never run by the test suite or CI.
  - Done when both files exist, the procedure's first section states the
    real-account write, and the template has a row for each of the four
    steps.
  - _Requirements: 18.1, 18.2_

## Implementation Notes

- 1.1: the strict tier keeps main's 1e-9 relative slack in `within`, so exact-tolerance table rows cannot see a `<`-for-`<=` flip; inclusivity is pinned only by `test_within_is_inclusive`. Controller downgrade: the round-1 rejection was one false docstring sentence in `tests/identity/test_strict.py`; the controller deleted it and re-ran the file instead of a second review round.
- 1.3: controller rulings. (a) `relay_connect._NEXT_STEPS` covers the whole vocabulary, a file design.md's file list omits: the five connect codes take the `REGISTRATION_*` text ("Run {connect} again; if this repeats, tell the relay's operator."), because to the relay connector they are another route's answers. (b) `RelayClient`'s token operations keep refusing all five connect codes (`_SUCCESS_SHAPED` unchanged; refusal literal 19). **Task 4.4 must delete both `_CONNECT_CODES_RECORDED_BY_4_4` exemption sets** (tests/connectors/test_relay_wire_examples.py, relay/tests/test_envelope_replay.py) when it records the connect exchanges. Controller downgrade: round 2's only finding was one false comment sentence in tests/connectors/test_relay.py; the controller rewrote it and re-ran the file.
- Local relay runs need `uv sync --directory relay --extra postgres` (without it, relay mypy shows 26 psycopg errors and the PostgreSQL cases cannot import).
- 1.2: `relay_targets` imports only `relay_envelope` (design.md's allowed-dependency line also names `relay_codes`; the exact-equality boundary table pins `{relay_envelope}`). `target_route`, `connect_page_path` and `link_path` refuse malformed parts with `EnvelopeError` (design is silent; every design-described caller passes valid parts). Control characters are Unicode category Cc only (Cf such as ZWJ in emoji, and U+2028, are accepted). Numbers parse to float; a too-large int is refused, not an OverflowError. No test yet shows the largest valid upload body fits `MAX_UPLOAD_REQUEST_BYTES` (literal pin only): the consumer of that bound (4.1 route limits / 5.5 client bound) should pin it. Controller downgrade: round 3 (test-only, from the round-2 reviewer's exhaustive 55-mutation list) was verified by the controller re-running that harness: every non-equivalent mutation reds; survivors R, AR, BF are equivalent.
- Mutation harness trap: a copied tree's `.venv` editable install still imports the ORIGINAL tree's `src`; force `PYTHONPATH=<copy>/src` or every mutation reads green.
- 1.4: `SHARED_MODULES` has five pairs (relay_codes, relay_envelope, publish/outcomes, relay_targets, identity/strict). **7.4 must also reword** the steering phrases "today `relay_codes` and `relay_envelope`" (tech.md ~35, structure.md ~93-96, incl. what each shared module may import) and move their literal pins in tests/connectors/test_network_statements.py (~914, ~962).
- 2.1: `cryptography>=44,<51` (lock 50.0.2, +cffi, pycparser). `parse_keys` also refuses duplicate key ids and non-canonical base64url (design silent; docs row for FITDOCS_RELAY_ENCRYPTION_KEYS must say ids are distinct); `Keyring(())` raises. Controller downgrade: round 1's two test-only findings (extra-segment value, non-UTF-8 plaintext) were added by the controller and verified by the reviewer's mutations M8/M19 (each reds its test alone). Branch CI must show the relay image smoke on both backends green.
- 5.1: connectors `__all__` 67. OAUTH_BROWSER now passes the CLI style check; until 5.8 a browser-consent instance would fall into the generic prompt path (unreachable: no such connector registered before 5.5) — **5.8 must add the branch before group 5 merges**. 5.7/5.8: sweep leftover "reserved" wording (cli.py ~1494, ~1708 docstrings; tests/connectors/test_cli_relay_connect.py:352; `_ReservedConnector` name). The order "style refusal before the credentials-directory check" is no longer pinned (one CLI reserved-style test deleted, the other rewritten to monkeypatch SUPPORTED_AUTH_STYLES).
- 5.2: browser-consent instance naming another browser instance is refused with the same 'relay:' message (only RELAY_TOKEN instances count). The shared _ReservedConnector test fixture now carries bindable settings + RESERVED_RELAY_TABLE. Controller downgrade: round 2 (test-only) verified by the controller re-running reviewer mutations R1/R5/R8 in a scratch copy, each red.
- 5.3 ruling: shared relay_envelope encode_request/decode_request gain keyword-only max_bytes (default MAX_REQUEST_BYTES); RelayClient.post passes its bound through; relay copy re-synced. Relay-server amendment item for 7.6. **4.1 needs this: merge impl/sp-client (or integration) into impl/sp-relay before 4.1** so ROUTE_BODY_LIMITS can call decode_request(max_bytes=...).
- 2.2: new relay package relay/src/fitdocs_relay/strava/ (config.py: load_targets_config, load_strava_config, TargetsConfig, StravaConfig, Limits, LinkSetting). Any target variable (PUBLIC_URL, ENCRYPTION_KEYS, OPERATOR_NAME, SUPPORT_CONTACT, PRIVACY_POLICY_URL) without a client id is refused. required_with: _WITH_ANY_TARGET (generic rows; a later target appends its client id) vs _WITH_STRAVA (CLIENT_SECRET, WEBHOOK_TOKEN). Value bounds the design left open (client id 1-20 ASCII digits, secret <=256 printable ASCII no spaces, limits 1..1e6, contact <=254) are the implementer's. docs/relay.md states the Strava windows are quarter hours and days from midnight UTC — **3.3 must implement exactly that**. Controller downgrade: round 3 (exhaustive 155-mutation sweep, test/prose only) verified by the controller: full relay suite green, 6 sweep survivors all equivalent (empty values refused earlier by load_config; host None; leading-slash strip).
- 5.3: controller downgrade: round-2 review's three test/comment findings (bound 0, decode smaller bound, _DESIGN_SIGNATURES comment) applied by the controller and verified by the reviewer's mutations M4b/M10 (each reds its new test alone). **4.1: relay answers.py:119 and app.py:237-249 enforce MAX_REQUEST_BYTES on their own — raise both for the upload route, not only decode_request(max_bytes=...).**
- 5.4: controller ruling: a success code from another route (ok, registration-*, connect-* not the operation's own) and `ok` with data read as `RelayRefused(ANSWER_MALFORMED)` (mirrors relay.py `_refused`/`_empty_ok`), where design.md:936-944 literally says "anything else is RelayRefused(code)" / "ok gives None" — design text to be amended in 7.6. Tests for settings/consent live in tests/connectors/test_strava_consent.py (design's file plan names test_strava.py). Controller downgrade: round-1 test/docstring findings (capabilities literal, credential label, every success code, one docstring sentence) applied by the controller and verified by the reviewer's mutations (each reds).
- 2.3: relay/src/fitdocs_relay/outbound.py. Non-2xx comes back as an OutboundResponse (capped, 8 MiB); a request WITH A BODY never follows a redirect — its 3xx is returned as a response; GET/DELETE follow https-only redirects (secret headers unredirected); urllib's own loop/limit/file:// redirect refusals also surface as a 3xx response. **3.1/3.2 classify MUST treat any 3xx as a non-success (design ~1252 classify has no 3xx row; revoke/update/create_subscription would otherwise report success on a 302).** Errors are raised outside any except block (no __context__). The outbound `timeout > 0` guard admits inf (OverflowError escapes) — unreachable per design (min(CALL_TIMEOUT_S, left)).
- 2.3 controller downgrade: round 3 (test/prose only) verified by the controller re-running V1 and P2 in a scratch copy (each reds its new test alone); round-2 reviewer's mutations V2/P1/R3 reported red by the implementer.
- 5.5 review FUs for later tasks: (5.7) `fitdocs disconnect strava` exits 2 "oauth-browser not supported" until 5.7; (5.8) `fitdocs connect strava` falls into generic prompt path until 5.8; (6.1) pin named `fitdocs pull strava` makes no request with AND without a token (without one it reports NotConnectedError — same as relay instances, predates this spec), bare pull skips strava, `publish --targets` not_connected/ready, all under the socket guard; (7.1) rewrite docs/connectors.md preamble "Outside those ... sections" sentence to cover `## Strava`, keep the "`...`. Outside" adjacency test_docs.py:688 matches.
- 5.5: StravaConnector registered (registry order folder, intervals, relay, strava); surface stays 67 (connector not exported). publish_fields EnvelopeError -> rejected unsent; unreadable/non-regular base file -> activity_file_missing. Controller downgrade: round 2 (tests + prose) verified by the controller re-running reviewer mutations R1/R2/R15/R19 (each reds). R7 (drop st_size pre-read guard) is equivalent (the codec refuses oversize anyway; only memory differs).
- 2.4: schema pair 0002_target_custody (target_connections, target_publications, budget_counts); TargetConnectionStore in Storage. The recorded /readyz exchange bodies moved to schema 2 in place (a replayed recording cannot keep a stale twin). PostgreSQL put takes a per-target advisory lock (not schema-scoped; FYI). Controller downgrade: round-1 finding (rival lookup must be target-scoped) fixed by the controller with test_a_rival_is_sought_on_the_puts_target_only, verified by the reviewer's R1s/R1p (each reds only its own backend).
- 5.6: controller ruling: connectors/browser_connect.py imports `fitdocs.connectors.errors` (NotConnectedError, which design's own behaviour text needs) and `fitdocs.connectors.relay` (RelaySettings guard + url) beyond design.md:122/:518's allowed list; the boundary table pins both. `_env_override` is a private copy of relay_connect's (design asks for no shared helper). The engine sleeps the full stated interval even past the deadline, so the CLI "expires in" line and the exit can differ by up to one interval (low).
- 5.6 controller downgrade: round 2 (tests + docstring) verified by the controller re-running the reviewer's harness for R5/R14/R15/R16/R18 (each reds its own case).
- 5.7: browser-consent disconnect: ok/token-unknown/token-revoked remove the file (the latter two with CONSENT_UNKNOWN_NOTE); local-only note CONSENT_LOCAL_ONLY_NOTE (implementer-written from design rows). UnsupportedDisconnect kept for a future reserved style; the CLI branch is now unreachable and untested (low). Controller downgrade: round-1 finding (Strava no-token error said 'relay token') fixed by the controller: wording by style + exact-message pin, verified by the reverting mutation (reds that test alone).
- 2.5: issue_connection_token raises DuplicateIdentifier on an existing token id and rolls back everything (like mint_token); updated_at unchanged on issuance — design silent on both; **3.9 decides what DuplicateIdentifier means to the poll caller**.
- 5.8: fitdocs connect browser-consent branch + --no-browser (no new command; no count pin moved). --register/--email on Strava reuse the relay-only refusal line. Controller downgrade: round 2 (tests only) verified by the controller re-running M8 (unredacted exception line) and M12 (narrowed opener catch), each reds its new test alone.
- 2.6: a swap by the holder after its lease expired still lands (literal design rule; safe: any claim replaces lease_id, a landed swap advances generation). **3.5 custody: keep a refresh shorter than LEASE_S (60 s) and decide what reencrypt_all does when its no-lease swap is refused** (a no-lease swap may land between an expired holder's Strava refresh and its own swap, losing Strava's new tokens). Lease races live in tests/conformance/test_concurrency.py (design names test_concurrency_custody.py).
- 3.11 rulings: Operator dataclass lives in pages.py (pages may not import config at run time); page statuses implementer-chosen (only unavailable=503 is in design); the breach-notice sentence (Req 16.6) stays in the policy; policy/consent describe what fitdocs disconnect does, never who runs it. The pages/policy stdlib-only boundary rule (task 4.1's bullet) is pre-landed in 3.11.
- 2.7: PublicationStore.put_publication returns False for another principal's id, raises UnknownPrincipal for a missing principal, and does NOT require a live connection (design ~1663). **3.6/3.7 must not leave a link record after a disconnect/account change**: a publish finishing after a disconnect would put a record that outlives its connection (queued FU). Controller downgrade: round-1's only finding (one false docstring sentence + a suggestion) fixed by the controller; interface/publication tests re-run green.
- 3.11 controller downgrade: round 3 (prose + literal pins, exhaustive) accepted on the implementer's mutation table (R1-R25, N1-N7 red; N5 equivalent) plus a controller read of every final policy/consent sentence against design; no fresh reviewer round. Merge impl/sp-pages into impl/sp-relay after 2.8.
- 3.1 rulings: any 3xx/1xx/out-of-range status classifies INVALID (so update/upload map to rejected per STEP_OUTCOMES; a redirect is never success); daily_spent compares x-ratelimit-usage / x-readratelimit-usage to the configured Limits (overall_day, read_day), not Strava's own -limit headers. Scripted Strava fake: relay/tests/strava/scripted_strava.py (ScriptedOutbound/UnscriptedCall), fixture scripted_outbound in relay/tests/conftest.py (lazy import — tests/storage/test_harness.py copies that conftest alone). 3.2 must extend list/upload/upload-status body readers and their pinned rows.
- 2.8 FUs for 3.3: StravaBudget must omit zero-amount charges (amount<1 is ValueError); exhaust_budget takes no principal_id, so mark_spent stays on application windows only; a refusal with amount > ceiling on an empty window reports a misleading wait — 3.3 should refuse such charges before calling storage (e.g. reserve_upload reads above the per-principal ceiling).
- **4.1 must add an autouse network guard to the relay suite** (no autouse guard refuses real HTTPS in relay/tests; once urllib_outbound is the app's default outbound, one route test that forgets scripted_outbound would call the configured Strava base). Patch socket.create_connection + getaddrinfo (relay-server lesson: socket-only guards are blind to example.com hosts).
- 2.8: PostgreSQL spend cleanup deletes ended windows with FOR UPDATE SKIP LOCKED (never waits; a held ended row is left for a later spend) — fixes a window-boundary deadlock the round-1 reviewer reproduced. exhaust_budget refuses a negative count. Controller downgrade: round 2 verified by the controller re-running the restore-blocking-DELETE / drop-SKIP-LOCKED mutation on PostgreSQL (both new PG tests red); other round-2 mutations per implementer.
- 3.2: listing reads sport from sport_type and start from start_date (UTC instant, never start_date_local); any malformed entry makes the WHOLE listing unreadable (never drop an entry: a dropped entry could make an ambiguous listing look unique). Subscription view/delete carry client credentials in the query with url_is_secret=True (Strava's documented shape); requests whose path carries a Strava id are url_is_secret (Req 12.2).
- 3.2 controller downgrade: round 2 (tests + docstring + url_is_secret on id-bearing paths) verified by the controller re-running M16 and M27 (red); the rest per the implementer's table.
- 3.3: StravaBudget keys strava:all|read:<w> and strava:p:<pid>:all|read:<w>; for_link lowers only the read windows; a charge larger than its ceiling is refused before storage as BudgetDecision(False, None) — **callers (3.5-3.8) must accept retry_after_s None on a refusal**. Only READ and UPLOAD call kinds exist; OAuth/subscription callers charge READ (pin per caller task). Controller downgrade: round-1's only finding (odd-limit row for the principal link ceiling) added by the controller and verified by the reviewer's nested-floor mutation (reds the odd rows on both backends).
- 3.4: resolve.py skips a candidate whose sport type is unknown/missing (design built one with sport ""; same result for every envelope-valid page). SPORT_FAMILIES' 50 Strava types written from memory (queued: source + live-check). Controller downgrade: round-1's only finding (unknown/missing type vs a Workout page) fixed by the controller by checking every FITDOCS_SPORTS page; verified by the reviewer's R1 (.get default Workout) and R2 (or "Workout") — both red.
- 8: relay/LIVE_CHECK_STRAVA.md + _RECORD.md; observations verified against the fitdocs CLI as built, but the webhook commands (4.5), the link setting and /go/ behaviour (4.2/4.3) are described per design — **re-check the procedure against the built relay at validate-impl**. Controller downgrade: round 2 (documents; implementer reported STATUS: DONE instead of the template token) accepted on the round-1 reviewer's itemised remediation without a second review round.
- 3.5 CONTROLLER RULINGS (tell Josh): (B) a 1xx/3xx/out-of-range Strava answer classifies SERVER (transient), not INVALID — revises the 3.1 ruling, because INVALID on the refresh step deletes the connection (Req 4.5 deletes only on a refusal; a moved token endpoint would have deleted every connection). (A) TargetConnectionStore.delete_connection gains keyword `lease_id`; custody's refused-refresh delete requires the holder's generation AND lease_id, so a reconnect during a refresh (put resets generation to 1 and clears the lease) is never deleted (reviewer reproduced the ABA deletion on both backends). Design amendments for 7.6: classify table rows; delete_connection signature.
- 3.5 controller downgrade: round 3 (two tests + docstrings, no behaviour change) verified by the controller re-running O6 on PostgreSQL (reds the lease test alone); O5/O12 per implementer.
- 3.6 rulings: the link record is written only if the connection still exists just before put_publication (narrows the orphan race; storage-level fix queued); an update that landed while the connection vanished still answers Landed(POSTED, page) with no record; put_publication False after landing is ignored. strava/publish.py holds StravaPublisher, STEP_OUTCOMES, Landed and activity_page(web_url, id) — **3.7/3.8 extend this class and reuse activity_page**.
- 3.9 rulings: a 429 on the connect code exchange calls budget.mark_spent (Req 9.4; design's ConnectFlow is silent); a store_grant/result-write failure after the state was taken marks the session refused (Req 3.7) instead of leaving it pending to expiry. **4.3 routes: read the `fitdocs_connect` cookie from the Cookie header, pass the raw value to page() and callback(), send ShowConsent.set_cookie back verbatim as one Set-Cookie header, and turn an exception escaping callback() into a fitdocs-written page.** TokenService.prepare(*, label) added (IdentityAmendment); mint uses it.
- 3.6 controller downgrade: round 2 (tests + docstrings + deadline-before-spend reorder) verified by the controller re-running O9 (reds its test); others per implementer. Deadline check now precedes the budget spend in _find/_update.
- 3.9 controller downgrade: round 2 verified by the controller re-running N2 and R10 (each reds its test).
- 3.7 ruling: after a failed upload the re-resolution update is made once with no repeat, to stay within the upload reservation (UPLOAD_FOLLOW_UPS = 2); a server failure there answers via the update column. StravaPublisher gained sleep=; publish() routes through _post; _find/_update take charge=/repeat=.
- **4.3 webhook route: cap the body read at MAX_EVENT_BYTES+1 before calling Webhook.event (it checks len only after the body is in memory); oversized → 200-ignore per design "Always 200"; bound the hub.challenge query value.** Deauth keying verified end to end (exchange str(int) == webhook str(owner_id)).
- intervals-publish MERGED to main at 978c74fa: it took amendments connectors 8, intervals-connector 2, distribution 8, wellness-pull 1 (**7.6: strava-publish takes connectors 9, distribution 9, next relay-server/activity-identity numbers on main**); tests/connectors/test_network_statements.py already has _names_publish_command + position pins (**7.3: skip steps intervals already made**); HttpClient.put exists. strava lands second: merge main into the spec branch before 7.x.
- 3.10 controller downgrade: round 2 (test-only) verified by the controller re-running M20 (reds the exact-delta deauth test).
- 3.7 controller downgrade: round 2 verified by the controller re-running O3b (reds the new upload twin test alone).
- 4.5 rulings: `strava webhook create` over another application's callback creates nothing, prints `subscribed elsewhere` on stderr, exit 1; a Strava failure prints `strava failure: <Failure value>` on stderr, exit 1; `reencrypt` refuses (exit 2) when the Strava target is unconfigured (no keys load). **4.3: the webhook route must share WEBHOOK_PATH (now in strava/cli.py) — move it to strava/webhook.py and import it in both, with a test tying route and callback.** Optional: an exception-path test that no unexpected outbound exception text reaches stderr.
- 3.8 ruling: resolve_link answers TRY_LATER only for a refresh or link spend the budget refuses, or Strava's 429 on the refresh/listing; a Strava-refused refresh, custody unavailable (refresh 5xx/network, lease wait timeout), a passed deadline, unknown id, no connection, no single match and any other listing failure → NOT_FOUND (design resolve_link bullet + Req 10.4). Link deadline reuses PUBLISH_DEADLINE_S (design names none; a click can wait lease 5 s + refresh + 8 s listing — low FU).
- 3.8 controller downgrade: round 2 (tests + prose) verified by the controller re-running M11 (reds the new 503/network tests).
- 4.1 ruling: the larger upload body bound applies only when the Strava target is configured (per_route_limits = services.strava is not None) — an unconfigured relay stays byte-for-byte relay-server (Req 13.3); design RoutesAmendment/AppAmendment to say so (7.6). read_request takes its bound from the scope key the admission stage sets. make_services(config, store, *, clock, outbound, monotonic, sleep) builds RelayServices. **4.2/4.3: core_routes must append strava_routes(services); add Strava call-event fields step and failure to logs REQUEST_FIELDS/_STRING_FIELDS when an emitter is added.** Relay tests have an autouse network guard (conftest).
- 4.1 controller downgrade: round 2 verified by the controller re-running R13 (keyring) and C2 (CLI redactor), each reds its test alone. One unreproduced SQLite flake of test_the_built_connect_page_names_the_configured_public_address during a mutation run — watch CI.
- 4.2: /go/ is served in minimal form (ready → per-client limit → id format → resolve_link → 302 Location + PAGE_HEADERS, else try-later/not-found pages); **4.3 must: put Referrer-Policy/CSP on every /go/ answer incl. storage failures (a StorageUnreachable from resolve_link currently gives a JSON envelope), pin PAGE_HEADERS on /go/ refusal pages, decide HEAD /go/ (Starlette adds HEAD — runs a full resolve).** Disconnect revokes only the connection's own token (pinned). Controller downgrade: round-1 findings (connection-token-only revocation unpinned; a misnamed storage-error test) fixed by the controller and verified by the reviewer's O7 (reds the strengthened test).
- 4.3 ruling: a webhook body over 64 KiB is refused by the pipeline's admission bound (request-too-large 413) before the route, not the design's 'Always 200' (Strava events are tiny); HEAD on every page route answers 405 Allow: GET with page headers (a link previewer can't claim a session or run the callback).
- 4.3 controller downgrade: round-1 findings (ready-before-limit unpinned; false docstring) fixed by the controller; verified by the reviewer's M1 guard swap (reds the new test on all page routes).
- **5.9: the recorded strava-publish-facts-missing request can't be reached through StravaConnector.publish (the connector answers ACTIVITY_FACTS_MISSING locally, never sends it) — decode that answer through the relay client directly, or exempt it with a reason.** **7.2: docs/relay.md ~487-489 says the recording uses only the all-a token; it now also carries the all-b connection token.**
- 4.4: a second visibly fake token (all-b) is the recorded connection token. Controller downgrade: round 2 verified by the controller re-running the extra-route mutation (reds the derived route-coverage test).
- 5.9 controller downgrade: test-only task accepted on the implementer's 9-mutation table plus a controller re-run (poll-granted token mutation reds its case), without an independent review round. Mapping rows other than NOT_OFFERED stay pinned only by test_strava_publish.py (recordings are all ok answers).
- 6.2 controller downgrade: test-only task accepted on the implementer's 11-mutation table plus a controller re-run (plaintext athlete-id account key reds both link settings), without an independent review round. Logs are checked via caplog (before the redacting filter) — stricter than production.
- 6.1 controller downgrade: round-1 finding (three now-false docstrings in test_e2e.py) fixed by the controller. **Merge hazard: main's intervals-publish rewrote the same publish block in tests/connectors/test_e2e.py — reconcile to an exact two-row --targets literal (strava-src then wellness-src) and recompute the dry-run literal; don't adopt main's startswith.**
- 7.1 controller downgrade: round-1 findings (two false sentences: relay-token override at connect, 'the answer carries a link' under relay; one who-runs phrase; weak 'connected.' pin; loopback sentence grammar) fixed by the controller; pins re-run (connected-line and loopback mutations red).
- 7.3: every publish --yes step was already landed by intervals-publish (pins in test_network_statements.py); this spec adds only the Strava line + its pin. Controller downgrade: accepted on the implementer's two red mutations plus a controller read of the sentence, without an independent review round.
- 7.2: two review rounds (round 1: eight false sentences — operator name only on the privacy page, token revoked not deleted, connection ends only on a refused renewal, upload updates a match first, Envelope v1 outcome/routes/'every answer'); round 2 APPROVED.
- 7.5: relay changelog section headed `## Unreleased` (controller ruling: relay/pyproject.toml is 0.1.0; no version invented — whether Strava ships in relay 0.1.0 is a release-cut call). Round-1 findings (Strava --local-only consequence omitted 'or access is revoked in Strava's settings' and the token-unknown/revoked removal rows; 'an unconfigured relay is unchanged' ignored that every relay must apply migration 0002) fixed by the controller; new 'revoked' pin reds alone when the clause is dropped.
- 7.6: connectors Amendment 9, relay-server Amendment 1, activity-identity Amendment 3; distribution skipped (Amendment 8 by intervals-publish already records Req 10.4); design.md gains an Amendment note (2026-11-02) carrying the 5.4, 3.5 and 4.1 rulings. Also fixed (17.3): tech.md and the cli.py module docstring now name the Strava connect/disconnect requests. Three review rounds; the round-3 one-line finding (5.4 parenthetical overclaimed the malformed set) fixed by the controller.
