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
- **No version constant moves.** `CONTRACT_VERSION`, `DOC_VERSION`,
  `ENVELOPE_VERSION`, `SEAM_VERSION` and `DEPLOY_CONTRACT_VERSION` stay as
  they are; no command is added, so the CLI command-count pins do not move.
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

- [ ] 1. Foundation: the shared modules and their pinned copies

- [ ] 1.1 Extract the strict tier of the match rule into a standard-library-only module
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

- [ ] 1.2 Add the shared Strava wire module
  - The target route builder, the connect-page and link paths, the
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

- [ ] 1.3 Append the connect answers to the relay code vocabulary
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

- [ ] 1.4 Pin the three new shared modules into the relay
  - Append the outcome vocabulary, the Strava wire module and the strict
    module to the sync script's pairs, write the copies with the sync
    command, and extend the cross-check test to assert the three new pairs
    by literal beside relay-server's two.
  - The relay's boundary test keeps the shared copies to the standard
    library and relative siblings.
  - Done when the cross-check passes, the sync check mode reports no drift,
    and editing one byte of any new copy reds the cross-check.
  - _Requirements: 6.3, 15.1_

- [ ] 2. Relay foundation: configuration, encryption, the outbound client and storage

- [ ] 2.1 Seal tokens with rotating keys
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

- [ ] 2.2 Configure the Strava target from the environment
  - Give relay-server's environment-variable record a `required_with` field
    (the variable whose presence makes this one required), rendered in
    `docs/relay.md`'s Required column as "with `<variable>`".
  - Append the thirteen variables to the deploy contract's table with their
    required flag or `required_with`, default, secret flag and meaning, and
    append them to relay-server's literal full-table pin.
  - Load the targets configuration (with the keys parsed by the keyring's
    parser) and the Strava configuration: the client id enables the target;
    the "with Strava" variables are then required; any Strava variable
    without the client id, a missing required one, an invalid value
    (including an invalid encryption key list), or a fifteen-minute limit
    above the daily one is a configuration error naming the variable and
    never its value.
  - Add the rows to `docs/relay.md`'s variable table in the same task, since
    its binding test reads the contract.
  - Done when configuration tests cover each refusal with a planted secret
    absent from every message, an unconfigured environment loads exactly
    as before, the contract pins pass, and dropping a row from the docs
    table reds the binding test.
  - _Requirements: 9.1, 13.1, 13.2, 13.5_

- [ ] 2.3 Add the relay's outbound client for provider calls
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

- [ ] 2.4 Store target connections on both backends
  - Add the schema change pair (the three tables of design.md's physical
    model, identically named for both backends) and the connection area's
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
  - Done when the conformance suite passes on both backends, the migration
    parity test and the readiness replay pass, deleting a principal removes
    its connection, and the coverage check fails if one member's marker is
    removed.
  - _Requirements: 3.10, 11.5, 11.6, 11.8, 12.3, 14.1, 14.2, 14.3, 14.4_

- [ ] 2.5 Issue connection tokens atomically
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

- [ ] 2.6 Rotate tokens atomically through a refresh lease
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

- [ ] 2.7 Store link records on both backends
  - Add the publication area: put only for the owning principal, get by
    target and publication id; it joins the combined protocol.
  - Done when conformance tests on both backends show another principal's
    put refused, the owner's update kept, and records removed with their
    principal, with their connection, when another principal's put of the
    same account displaces the connection, and when the same principal's
    put changes the account.
  - _Requirements: 3.10, 3.11, 10.1, 10.6, 14.1, 14.4_

- [ ] 2.8 Count the call budget on both backends
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

- [ ] 3. Relay Strava services

- [ ] 3.1 Speak Strava's OAuth endpoints and classify every answer
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

- [ ] 3.2 Speak Strava's activity, upload and subscription endpoints
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

- [ ] 3.3 (P) Spend the call budget before every Strava call
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

- [ ] 3.4 Pick one activity by the strict rule
  - The sport-family table, every family value pinned within the shared
    fitdocs-sports literal's pinned copy; the listing window; the pick through the pinned strict match, where a full
    listing, two matches and an unknown sport type never yield a pick and
    order never decides.
  - Done when tests cover none, one, two, a full listing and an unknown
    sport type; named mutation: returning the first of two matches reds the
    ambiguity test.
  - _Requirements: 6.1, 6.2, 6.4, 6.5_

- [ ] 3.5 Keep custody of a principal's Strava tokens
  - Store a grant sealed under the connection's context with the keyed
    account hash; return a usable access token, refreshing through the
    lease near expiry, waiting on another holder, deleting on a definitive
    refusal, keeping the tokens on a transient one; withdraw (one revoke
    when the budget allows, then delete whatever happened); forget an
    account; re-encrypt every connection under the current key.
  - Done when tests over both backends show concurrent requests on an
    expiring token causing exactly one refresh call, a refused refresh
    deleting the connection and revoking its token, an undecryptable
    connection reading as not connected, and re-encryption counting an
    unreadable row and leaving it unchanged.
  - _Requirements: 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.7, 4.8, 11.5, 11.10_

- [ ] 3.6 Publish a post on Strava
  - The common checks (both facts absent, a publication id owned by another
    principal, a usable token), then the publish flow of design.md: one
    listing, the pick, one update with at most one repeat of the identical
    update on a server or network failure, and the publication record on a
    landed outcome; the publish deadline; the step-outcome table's list,
    update and refresh columns.
  - Done when scripted tests cover every publish branch and every row of
    those columns, a fake monotonic clock drives the deadline, a second
    repeat never happens, and a publication id owned by another principal
    answers `rejected` with no Strava call.
  - _Requirements: 5.6, 6.4, 7.1, 7.2, 7.6, 7.7, 8.1, 8.2, 10.1, 10.6_

- [ ] 3.7 Upload a post on Strava when no activity exists
  - The upload flow of design.md: listing and pick again, the upload
    reservation, one upload never repeated, bounded status polling,
    re-resolution after a failed upload, the upload deadline, and the
    step-outcome table's upload and status columns.
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

- [ ] 3.8 Resolve a link at click time
  - Look up the publication, its connection and a usable token, spend the
    budget for a link, list and pick, and return the activity page address
    or a refusal, storing nothing about the result.
  - Done when tests show one match giving the address, none or several or
    no connection giving not found, the headroom giving try later, and no
    storage write during a resolution.
  - _Requirements: 10.2, 10.3, 10.4, 10.5_

- [ ] 3.9 Run connect sessions, the page claim, the callback and the poll
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

- [ ] 3.10 Act on Strava's webhook
  - Validation answered only for the configured verify token; a
    deauthorization event forgetting its account; every other event
    acknowledged and ignored.
  - Done when tests show a deauthorization deleting the connection, its
    link records and its connection token, and an activity event leaving
    every table unchanged.
  - _Requirements: 11.6, 11.7, 11.10_

- [ ] 3.11 (P) Write the pages, the consent text and the privacy policy
  - Every page of design.md, in fitdocs's words, with the support contact
    and policy link on each, the connect page in the stated order, and the
    "Connect with Strava" control as a link to the authorization address at
    the guideline height, with no Strava artwork; the page headers; the
    policy sections and the consent text.
  - Done when tests show every interpolated value escaped, each page
    carrying the support contact, the connect page's order, the operator's
    own policy address replacing the built-in one, and the only brand
    phrases being the allowed ones.
  - _Requirements: 3.2, 3.5, 10.3, 10.4, 12.4, 16.1, 16.2, 16.3, 16.4_
  - _Boundary: Pages, Policy_

- [ ] 4. Relay HTTP surface and operator commands

- [ ] 4.1 Extend the relay pipeline for targets
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

- [ ] 4.2 Serve the Strava envelope routes
  - Connect, poll, publish, upload and disconnect, through the relay's
    authentication, per-token limit and strict request reader, each answer
    checked against its route's outcome set.
  - Done when test-client tests with scripted Strava show each route's
    answers, an unconfigured relay answering `not-offered` on each, a
    disconnect answering `ok` when the principal held no connection, and a
    70 KiB body refused on the publish route but accepted on the upload
    route.
  - _Requirements: 3.1, 3.8, 3.9, 5.1, 8.2, 11.5, 12.1, 12.5, 13.3_

- [ ] 4.3 Serve the browser pages, the link and the webhook
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

- [ ] 4.4 Record the Strava exchanges and replay them against the relay
  - One recorded exchange per Strava envelope route and per new relay code,
    with visibly fake values, replayed by the relay suite byte for byte.
  - Done when the replay passes and editing one recorded byte reds it.
  - _Requirements: 12.1, 15.4_

- [ ] 4.5 Provide the Strava operator commands
  - The webhook show, create and delete commands, re-encryption, and key
    generation, printing only fitdocs-written states, with the exit codes
    of design.md; append `strava`, `reencrypt` and `new-encryption-key` to
    the deploy contract's command list and its pin.
  - Done when command tests with scripted Strava show each state and exit
    code, the subscription addresses never printed, and re-encryption
    exiting 1 when a row is unreadable.
  - _Requirements: 4.2, 11.9_

- [ ] 5. fitdocs client: the Strava connector, connect and disconnect

- [ ] 5.1 Drive the browser-consent authentication style
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

- [ ] 5.2 Bind each browser-consent instance to its relay instance
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

- [ ] 5.3 Attempt every relay request exactly once
  - The relay client marks every request it builds single-attempt; where
    it bounds an outgoing body, `post` takes the bound as a keyword
    defaulting to relay-server's. Its imports, and its boundary row, do not
    change.
  - Done when a scripted 503 over a data-mode client sees one transport call
    for a GET and for a POST; named mutation: dropping the mark from POST
    sees three calls.
  - _Requirements: 5.5_

- [ ] 5.4 Add the Strava connector's settings and consent operations
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

- [ ] 5.5 Publish to Strava and register the connector
  - The publish operation: facts and bounds checks before any request, the
    publish request, the upload request only after `not_found` with
    uploads enabled, the file checks, both mapping tables, and the link
    only with a landed code.
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
    oversize file, and the boundary, surface and preamble pins pass; named
    mutation: importing `PublishCode` from `fitdocs.publish.outcomes` reds
    the boundary assertion.
  - _Requirements: 1.1, 1.7, 5.1, 5.2, 5.3, 5.4, 5.6, 5.7, 5.8, 5.9, 7.8, 8.4_

- [ ] 5.6 Run the browser-consent connect loop
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

- [ ] 5.7 Disconnect a Strava instance
  - The disconnect rows for the style: one withdraw request with the stored
    token, the local-only removal with its note, and nothing to disconnect
    without a stored token.
  - Done when tests cover each row, an unknown-token answer removing the
    file with its note, any other answer keeping it, and the override never
    sent.
  - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [ ] 5.8 Present Strava connect and disconnect in the CLI
  - The browser-consent branch of `fitdocs connect` with `--no-browser`,
    its refusals of `--register` and `--email`, `--no-browser` refused on
    other styles, the printed lines, the browser opener and its failure
    line, and the exit codes; disconnect results printed as for relay
    instances.
  - Done when CLI tests pin the printed lines, show no browser call with
    `--no-browser`, exit 2 for each refused flag before any request, exit 1
    when the relay instance has no token, and exit 130 on interrupt.
  - _Requirements: 2.3, 2.8, 2.9, 2.10, 11.1, 11.3_

- [ ] 5.9 Decode the recorded Strava exchanges through the client
  - The fitdocs suite decodes every recorded Strava answer through the
    relay client and the Strava connector with a fake transport and asserts
    the code and the parsed data.
  - Done when the decoding test passes and editing one recorded code reds
    it.
  - _Requirements: 5.6, 8.4_
  - _Depends: 4.4_

- [ ] 6. Integration and validation

- [ ] 6.1 Hold the fitdocs-side guarantees with a Strava instance configured
  - The socket-guarded offline-commands test gains a Strava instance in its
    wired root; a bare and a named `fitdocs pull` make no request for it;
    `fitdocs publish --targets` shows it ready and not connected; the
    confinement test shows a Strava connect writing nothing under the data
    root.
  - Done when these tests pass, and a scripted relay request during
    `fitdocs pull` fails the socket guard.
  - _Requirements: 1.6, 1.8, 2.9_

- [ ] 6.2 Prove nothing from Strava escapes the relay
  - A scripted Strava that plants one sentinel in every field and header,
    driven through connect, publish, upload, a link, a disconnect and a
    deauthorization on both backends.
  - Done when the sentinel appears in no envelope answer, page, log record
    or database column outside the sealed tokens, and no table holds an
    activity id or athlete id.
  - _Requirements: 12.1, 12.2, 12.3, 12.5_

- [ ] 7. Documentation, gates, steering and amendments

- [ ] 7.1 Document the Strava connector
  - The Strava section of the connectors page with the four subsections of
    design.md, "Compatible with Strava", the settings table, the relay
    instance and public-address prerequisites, both mapping tables, what
    leaves the machine, and the default relay's policy address; heading
    rows added in page order; the neutral-scan entry gains the section.
  - Done when the connectors docs tests pass, the section names no Strava
    host, and deleting a mapping row from the page reds a binding test
    against the mapping tables.
  - _Requirements: 16.4, 16.5, 17.1, 17.7_

- [ ] 7.2 Document the Strava target for operators
  - The relay page's Strava sections of design.md, including the
    `required_with` rendering and the relay instance URL matching the
    public address, and the policy summary bound to the policy sections by
    a test.
  - Done when the relay docs tests pass, removing a policy section from the
    summary reds its binding test, and the page names no hosting or email
    provider.
  - _Requirements: 4.9, 13.6, 16.1, 16.5, 16.6, 17.2, 17.7_

- [ ] 7.3 Make every network statement name `fitdocs publish --yes` and the Strava host
  - Written to hold in either landing order with `intervals-publish`:
    every statement that lists the network-touching commands names
    `fitdocs publish --yes` (add it where absent, keep it where the other
    target already added it), and the connectors page's "What leaves your
    machine" gains the Strava line (its bound relay's URL, never Strava).
  - Pins require both in every place, with one named mutation per place.
  - Done when the network-statement tests pass, and removing the command or
    the Strava line from any place reds its pin.
  - _Requirements: 17.3_

- [ ] 7.4 Add the steering sentences
  - `tech.md` "Network and Credentials" gains the Strava sentence of
    design.md; `structure.md` gains the strict-module sentence; each is
    line-disjoint from other specs' edits.
  - Done when the steering pins still pass and the new sentences read as in
    design.md.
  - _Requirements: 17.4_

- [ ] 7.5 Record the changelog entries
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

- [ ] 7.6 Record the amendments in the affected specifications
  - connectors, relay-server and activity-identity, each with the items of
    design.md's Amendments Carried, worded like the earlier landed
    amendments and naming the pin that enforces each; confirm the site-copy
    queue item still names true lines.
  - Done when each requirements document carries its dated amendment
    naming strava-publish.
  - _Requirements: 15.2, 17.6, 17.8_

- [ ] 7.7 Run the full validation sweep
  - Both suites and gates, the release build and artifact check, the site
    build and checks, the sync check mode, the relay workflow and image
    smoke on both backends, and a scan that the packaged skill names no
    target.
  - Done when every gate is green and the sync check reports no drift.
  - _Requirements: 17.7, 17.8_

- [ ] 8. Write the maintainer's live-check procedure and its record template
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
