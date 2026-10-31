# Implementation Plan

Prerequisites, all on `main` before any task starts:
- **The implementation gate** (design.md "Implementation Gate", Req 16.1):
  this spec's `research.md` "Implementation gate" record shows either that
  intervals.icu approved the maintainer's OAuth application or the
  maintainer's written decision to implement before approval. Task 1.1
  checks it; when it shows neither, 1.1 stops the whole run for a human
  (kiro-impl's `STOP_FOR_HUMAN`, never a skippable task block). No task is
  dispatched while 1.1 is unchecked, and the first task of every later
  group declares `_Depends: 1.1_`.
- `publish-core`, `relay-server`, `intervals-publish` and `strava-publish`
  have landed, including the controller's R11 folds (`PublishCode` and
  `TARGET_CODES` re-exported through `fitdocs.connectors.protocol`;
  `local_record_unreadable` after `ready`). This spec consumes their names as
  their design.md files state them, and moves some of their code (the
  amendments in design.md "Amendments Carried").

Three streams meet in the integration group:
- **shared**: group 1, in order, first;
- **relay**: groups 2 to 4, in order;
- **fitdocs**: group 5, in order. It depends only on group 1 and may run
  alongside groups 2 to 4 in its own worktree; 5.6 also waits on 4.3.
- 6.3 runs both suites over one case file and waits on both streams (3.8
  and 5.4).

Group 6 integrates and validates. Group 7 carries the documentation, gates,
steering and amendment records. Group 8 writes the maintainer's live-check
documents; carrying out the live check is the maintainer's.

Rules for every task:
- **Both suites stay green.** Each task leaves the root gates (`uv run
  pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run
  mypy`) and the relay's gates (`uv run --directory relay pytest`, ruff,
  mypy) green on its own.
- **Every new assertion names the mutation it dies on** (tech.md, Testing).
  Run that mutation before reporting the task done.
- **No request to intervals.icu, ever, in any test or session.**
  intervals.icu is scripted at the relay's outbound seam; the relay is
  scripted at fitdocs's transport. No implementation, review or validation
  session carries out a step of the live check or any step that reaches
  intervals.icu through a real application.
- **PostgreSQL is exercised, never skipped.** Every relay task that touches
  storage runs the relay suite with and without
  `FITDOCS_RELAY_TEST_POSTGRES_URL` (the second run with
  `FITDOCS_RELAY_REQUIRE_POSTGRES=1`), using relay-server's local recipe;
  the branch's relay CI run must be green.
- **Moved code keeps its results** (Req 14.2). Where a task moves
  strava-publish's or intervals-publish's code, their tests keep every
  expected value they assert. A moved test may change only its imports, its
  setup and the construction of the objects it tests, the target argument a
  shared operation now takes, the four target-neutral rows' `required_with`
  tuples gaining the intervals.icu client id in the contract pin,
  the place of moved documentation headings, and (for the privacy page) the
  grouping of the Strava sections.
- **The relay boundary test moves with each module.** A task that creates
  or moves a relay module updates `relay/tests/test_boundary.py` for it in
  the same task, so the relay suite is never red between tasks; a task that
  creates a fitdocs connectors module updates
  `tests/connectors/test_boundary.py` likewise.
- **No version constant moves.** `CONTRACT_VERSION`, `DOC_VERSION`,
  `ENVELOPE_VERSION`, `SEAM_VERSION` and `DEPLOY_CONTRACT_VERSION` stay; no
  command is added, so the CLI command-count pins do not move. No schema
  change is added (strava-publish's `NNNN_target_custody` already stores an
  absent expiry, R13.6), so no schema-count or readiness literal moves. The
  connectors surface count moves with the new names, as a literal written at
  landing, never derived from a live constant.
- **The website is not edited** (R9). Its copy is the queue item
  `.kiro/queue/2026-10-31-relay-intervals-site-copy.md`, written with this
  spec.
- **Amendments** to other specs take the next free amendment number at
  landing.
- **Wording**: no document names a hosting or email provider or a
  deployment's infrastructure; no text says who runs a command; nothing in
  the relay-routed connector or the relay-route module names an
  intervals.icu address; the only Strava brand phrases stay "Connect with
  Strava", "View on Strava" and "Compatible with Strava".
- **R11**: the relay-routed connector names publish codes and request
  types only through `fitdocs.connectors.protocol`; the shared rules module
  holds code values as strings and imports nothing.

- [ ] 1. Foundation: the gate and the shared intervals.icu rules

- [ ] 1.1 Check the implementation gate
  - Read the "Implementation gate" record in this spec's research.md.
  - If it shows neither an approval by intervals.icu nor the maintainer's
    written decision to implement before approval, change nothing and stop
    the whole feature run for a human: this task's stop means
    `STOP_FOR_HUMAN`, never a block that lets the run skip to 1.2.
  - Done when the record's dated line is quoted in this task's
    Implementation Notes and no file outside the spec directory changed.
  - _Requirements: 16.1_

- [ ] 1.2 Move the answer table and the request shapes into the shared rules module
  - Create the standard-library-only shared rules module with the request
    kinds, the answer classes, the success statuses per kind, the answer
    table (holding publish-code values), the status classification, the
    remote identifier rule, the update body, the deterministic one-part
    multipart body, the upload answer reading, the relative request paths,
    and the self-athlete and Strava-source constants, exactly as
    intervals-publish's design states them.
  - The direct connector imports them from there, wraps table values as
    publish codes, and keeps every request it sends byte-identical; its own
    copies are removed, so one definition remains.
  - Add the module to the connectors boundary test's module list and
    allowed-import table, and widen the direct connector's entry, in this
    task (exact equality over the files on disk).
  - Done when every intervals-publish test passes with only its imports
    changed, an AST test shows the module imports only the standard library
    and nothing relatively, a test shows every table value is a target code
    and neither posted nor uploaded, and swapping the creation column's 5xx
    cell to unavailable reds both the module's and the direct route's tests.
  - _Requirements: 8.1, 8.4, 8.5, 9.1, 9.2, 9.3, 9.5_
  - _Depends: 1.1_

- [ ] 1.3 Move the listing window, parsing and match into the shared rules module
  - Move the listing window, its fields, the entry parsing and the
    one-to-one match, with the strict predicate and the start tolerance
    passed in by the caller; the match returns a matched identifier, a
    refusal (ambiguous, not updatable) or nothing.
  - The direct route builds its predicate from activity-identity's
    standard-library strict rule with the page's sport on both sides, in
    place of the match rule's strict tier; its boundary entry admits the
    strict module in place of the match rule.
  - Make the direct route's link builder, link reader, pull-record lookup
    and base-file reader public under the design's names, for the
    relay-routed connector.
  - Rewrite the connectors package docstring's allowed-import sentence and
    the intervals module docstring's import sentence, which intervals-publish
    wrote with the match rule, to name the strict module.
  - Create the shared case file `relay/contract/intervals-cases.json` with
    its `match` cases (external id before strict, two strict matches
    ambiguous, a different sport still matching, a Strava import by instant
    and by local start, an absent id excluded), with visibly fake values; the
    fitdocs suite reads the file, as it reads the recorded envelope
    exchanges, and the relay suite reads the same file in 1.4.
  - Done when every intervals-publish finding test passes with only its
    imports changed, the file's match cases pass, importing the connectors package
    in a fresh interpreter still loads no identity module (the strict rule is
    imported inside the match helper),
    and building the predicate with the entry's sport reds the
    different-sport case.
  - _Requirements: 2.4, 6.10, 7.3, 7.5, 7.6, 9.2, 9.5_

- [ ] 1.4 Pin the shared rules module into the relay
  - Append the rules module to the sync script's pairs, write the copy, and
    extend the cross-check test to assert the new pair by literal.
  - Relay tests show every table value and every match refusal is a member
    of the pinned publish vocabulary, and run the shared case file's `match`
    cases (read from `relay/contract/intervals-cases.json`, never imported
    from `tests/`) against the copy with the predicate built from the
    relay's pinned strict rule.
  - Done when the cross-check passes, the sync check mode reports no drift,
    editing one byte of the copy reds the cross-check, and both suites pass
    the same match cases.
  - _Requirements: 7.4, 9.2, 9.3_

- [ ] 1.5 Append the intervals.icu names to the shared relay wire module
  - The intervals.icu target id, the known-activities field (zero to two
    distinct usable identifiers) with its known-only flag (true only with at
    least one identifier), the activity-identifier answer field, the
    publish and upload field sets, the two outcome sets of design.md, and
    their codec, refusing a malformed known-activities list or flag with
    fixed text.
  - The wire module imports the shared rules module relatively (its relay
    copy finds the rules copy 1.4 wrote); widen its connectors boundary
    entry in this task.
  - A fitdocs test pins both outcome sets as literals and as subsets of the
    target codes; run the sync command so the relay's copy of the wire
    module matches.
  - Done when the codec tests pass for zero, one and two known activities,
    a repeat, a malformed identifier, three, and the known-only flag with
    none are refused, the pinned-copy cross-check passes, and adding
    `not_found` to the upload set, accepting three known activities or
    accepting the flag with none reds a test.
  - _Requirements: 6.5, 6.9, 7.10, 12.1_

- [ ] 2. Relay foundation: one copy of the target machinery, configuration and storage

- [ ] 2.1 Lift the target configuration and the token vault out of the Strava package
  - Move the target-neutral configuration (public address, encryption keys,
    operator name, support contact, policy address, loaded when any target
    is configured) and the sealing, account-key and re-encryption code to
    the targets package; Strava's custody keeps its refresh lease,
    withdrawal and account forgetting over the vault.
  - Re-encryption covers every target's connections and keeps its two
    counts; the re-encryption and key-generation commands move with it,
    with their exit codes, built whenever the target configuration exists.
  - "Any target configured" still means Strava's client id until 2.5
    adds the second one.
  - Move the matching Strava tests, every expected value kept (Strava's
    custody is now built over the vault); update the relay boundary test for
    the new targets modules.
  - Done when the whole relay suite passes on both backends, a
    re-encryption over a Strava row and a second-target row re-seals both,
    the moved command tests pass, and an AST test shows the Strava package
    defines no sealing or account-key code.
  - _Requirements: 5.1, 5.7, 14.1, 14.2, 14.4_
  - _Depends: 1.1_

- [ ] 2.2 Lift the connect flow over a consent-provider protocol
  - Move the connect sessions, the page claim, the callback checks, the
    poll and the connection-token issuance to the targets package, generic
    over a provider that supplies the authorization address, completes a
    callback and withdraws a connection; the session's target is checked on
    the page, the callback and the poll.
  - Strava's provider keeps its callback logic (its scope check before one
    budget spend and one exchange, then its custody's grant).
  - Move the Strava connect tests, every expected value kept, adding the
    target argument and the providers mapping; update the relay boundary
    test for the moved module.
  - Done when every moved Strava connect test passes, a Strava user code
    opening another target's page is refused as unknown, and dropping the
    session-target check reds that test.
  - _Requirements: 4.1, 4.4, 4.7, 14.2, 14.4_

- [ ] 2.3 Lift the pages and compose the privacy policy per target
  - Move every page to the targets package, taking the control label, the
    consent text and the service name as arguments; with Strava's arguments
    every page keeps its text.
  - The privacy page is the common opening sections, then one group per
    configured target headed by its service name, then the common closing
    sections.
  - Move strava-publish's standard-library pins on its pages and policy
    modules in the relay boundary test to the targets modules in this task.
  - Done when the moved page tests pass with Strava's arguments, every
    interpolated value is escaped, each page carries the support contact,
    and a privacy page with two providers shows both groups in target order.
  - _Requirements: 12.4, 14.1, 14.2, 14.4_

- [ ] 2.4 Lift the target-neutral routes and the target services
  - Serve connect, poll and disconnect, the connect page, the callback and
    the privacy page from the targets package, mounted only for configured
    targets, with the privacy page served while any target is configured;
    Strava's routes keep publish, upload, the link redirect, the robots file
    and the webhook.
  - The services gain the target core (configuration, keyring, vault,
    connect flow, providers), and Strava's services keep only what is
    Strava's.
  - The relay boundary test admits the web framework in the targets routes
    module in this task.
  - Done when the whole relay suite passes on both backends, the disconnect
    route calls the target's provider and answers success with no
    connection, and a relay configured for no target answers not found on
    the privacy page.
  - _Requirements: 4.1, 11.3, 12.5, 14.1, 14.2_

- [ ] 2.5 Configure the intervals.icu target from the environment
  - Append `FITDOCS_RELAY_INTERVALS_CLIENT_ID` to the four target-neutral
    rows' conditional-requirement tuple, which strava-publish ships as the
    Strava client id alone (R13.6), so they render as "with A or B";
    Strava's own rows are unchanged.
  - Append the seven intervals.icu variables with their required flag or
    condition, default, secret flag and meaning, to the contract table, its
    literal pin and the relay docs variable table in the same task.
  - "Any target configured" now means either client id: an
    intervals.icu-only environment requires the four target-neutral
    variables.
  - Load the intervals.icu configuration: the client id enables the target,
    the secret is then required; a variable without the client id, a
    missing secret, a non-https address (loopback http aside), a limit that
    is not a positive integer, or a fifteen-minute figure above the daily
    one is a configuration error naming the variable and never its value.
  - Done when configuration tests cover each refusal with a planted secret
    absent from every message, an intervals.icu-only environment missing a
    target-neutral variable refuses to load naming it, unconfigured and
    Strava-only environments load exactly as before, and dropping a row from
    the docs table reds its binding test.
  - _Requirements: 10.1, 13.1, 13.2, 13.3, 13.6_

- [ ] 3. Relay intervals.icu services

- [ ] 3.1 Speak intervals.icu's OAuth endpoints
  - The authorization address with exactly the activity-write scope and the
    state; one code exchange with the client credentials in the form body;
    the revocation call with the token in the authorization header; the
    answer classification of each.
  - A scripted outbound fake for the intervals.icu tests, which records
    requests and serves canned answers, so no test can reach intervals.icu.
  - The relay boundary test keeps the new API module off `urllib` in this
    task.
  - Done when tests pin each call's method, address, query, headers and
    body, an exchange answer without an athlete gives a grant without one,
    one without a token is unreadable, and a sentinel in a scripted body
    appears in no returned value.
  - _Requirements: 4.3, 4.5, 4.6, 5.4, 12.2_
  - _Depends: 1.1_

- [ ] 3.2 Speak intervals.icu's activity endpoints
  - The listing over the shared window with the shared fields and parser,
    the update with the shared body and path, and the upload with the
    shared multipart body and the publication id as external identifier;
    every non-success answer as its answer class; the token only in an
    unredirected header.
  - Done when scripted tests show each call's method, path, decoded query
    and body, a listing entry missing its id read as not in documented form,
    an update's answer body never read, and putting the token in the query
    reds the header-only test.
  - _Requirements: 5.4, 8.1, 8.4, 8.5, 8.9, 9.1, 12.2_

- [ ] 3.3 (P) Count the intervals.icu call budget
  - The application's day, the application's fixed fifteen-minute window at
    half the configured rolling figure, and the principal's day, charged
    together before each call; the upload reserved with its confirming
    update; a rate-limit answer marking nothing.
  - Done when tests show a call refused at one principal's ceiling while
    another's is allowed, the reservation all-or-nothing, counts surviving a
    new budget over the same storage, and a fifteen-minute ceiling equal to
    the rolling figure reds the straddle test.
  - _Requirements: 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_
  - _Boundary: IntervalsBudget_

- [ ] 3.4 Keep custody of a principal's intervals.icu token
  - Store a grant through the vault with no refresh token and no expiry
    (`None` in strava-publish's nullable expiry column);
    give a usable token or not connected; delete the connection on a refused
    token only when its generation is unchanged; withdraw with one
    revocation when the budget allows, then delete whatever happened.
  - Done when tests over both backends show an absent expiry read back as
    absent (never zero), an undecryptable token reading as not connected, a stale deletion leaving a newer connection, a second
    principal's grant of the same account displacing the first and revoking
    its connection token, a deleted principal taking its connection with
    it, and a withdrawal with the budget spent still deleting.
  - _Requirements: 4.8, 5.2, 5.3, 5.5, 5.6, 9.4, 11.3, 11.4, 11.5_

- [ ] 3.5 (P) Write the intervals.icu consent text and policy sections
  - The consent text and the policy group of design.md, as fixed fitdocs
    text, with no artwork and no brand phrase; the relay boundary test keeps
    the module to the standard library in this task.
  - Done when a test of the policy composition over a stub provider carrying
    these sections shows them grouped under intervals.icu, a test pins the
    group's section headings as literals (removing one reds it), and the
    texts contain no Strava brand phrase. The served page with intervals.icu
    configured is checked in 4.2.
  - _Requirements: 4.2, 12.4, 14.1_
  - _Boundary: IntervalsPolicy_

- [ ] 3.6 Connect intervals.icu through the provider
  - The intervals.icu provider: its target, service name, control label,
    consent text and policy sections; completing a callback by one budget
    spend and one exchange, storing a grant that holds activity write and
    names the athlete, and otherwise revoking the token once when the
    budget allows and refusing; withdrawing through its custody.
  - Done when tests show a narrowed scope refused with the token revoked
    once and nothing stored, a missing athlete refused likewise, an exchange
    failure storing nothing, the code exchanged exactly once, and the
    exchange charged to the principal's budget.
  - _Requirements: 4.2, 4.3, 4.5, 4.6, 4.8, 10.6_

- [ ] 3.7 Publish a post on intervals.icu through the relay
  - The publish flow of design.md: the known activities updated in order
    with an absent one excluded; with the known-only flag, not found when
    every known activity is absent, with no facts check and no listing; the
    facts check, the listing and the shared match through the pinned strict
    rule, the update, the named single repeat of a listing or update on a
    server or network failure within budget and deadline (never after a
    429), a refused token deleting the connection, and the publish deadline.
  - Nothing is written to storage by a publish.
  - Done when scripted tests cover every branch and every table cell the
    flow reaches, a known-only request makes no listing call, a 429 is never
    repeated, a second repeat never happens, a fake monotonic clock drives
    the deadline, and a publish leaves every table unchanged; listing
    anyway on a known-only request reds a test.
  - _Requirements: 5.3, 7.1, 7.2, 7.3, 7.5, 7.6, 7.7, 7.8, 7.9, 7.11, 8.1, 8.2, 8.9, 9.1, 9.4_

- [ ] 3.8 Upload a post on intervals.icu when no activity exists
  - The upload flow of design.md: listing and matching again, the
    reservation, one upload never repeated, the confirming update, the
    created and already-held answers, the unconfirmed cases, the upload
    deadline, and the upload guard.
  - After the upload call, any later failure in the request answers
    unconfirmed, logged by type only.
  - Done when scripted tests cover every upload branch and table cell, the
    scripted upload endpoint is hit exactly once even when it answers a
    server error and never when the guard or the reservation ends the
    request, and a fake monotonic clock drives the deadline to unavailable
    before and unconfirmed after the file was sent.
  - _Requirements: 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 10.4, 10.5_

- [ ] 4. Relay HTTP surface

- [ ] 4.1 Offer the intervals.icu target in the relay pipeline
  - The services gain the intervals.icu services when configured; the
    offered targets gain `intervals`; the capabilities endpoint lists it
    only while configured; the reserved prefixes gain its callback path; its
    upload route gets the larger body limit; the log filter redacts its
    client secret and its call events carry only the call kind and the
    answer class.
  - Done when tests show capabilities with no target, Strava only,
    intervals.icu only and both, partial configuration refusing to start,
    and a planted client secret absent from captured logs.
  - _Requirements: 12.2, 13.2, 13.4, 13.5_
  - _Depends: 1.1_

- [ ] 4.2 Serve the intervals.icu routes and pages
  - Publish and upload envelope routes through the relay's authentication,
    per-token limit and strict reader, each answer's outcome checked against
    its route's set and the activity identifier given beside a landed
    outcome only; and the target-neutral connect, poll, disconnect, page and
    callback routes mounted for intervals.icu. The relay boundary test admits
    the web framework in the intervals.icu routes module in this task.
  - Done when test-client tests with scripted intervals.icu show each
    route's answers, an unconfigured target answering not-offered on its
    envelope routes and not found on its pages, a malformed known-activities
    list answered request-malformed with no intervals.icu call, a disconnect
    answering success with no connection, and the served privacy page
    carrying the intervals.icu group while intervals.icu is configured.
  - _Requirements: 4.1, 4.2, 4.4, 4.7, 6.9, 7.10, 11.3, 12.1, 12.5, 13.4_

- [ ] 4.3 Record the intervals.icu exchanges and replay them against the relay
  - One recorded exchange per intervals.icu envelope route answer kind, with
    visibly fake values, replayed by the relay suite byte for byte.
  - Done when the replay passes and editing one recorded byte reds it.
  - _Requirements: 12.1_

- [ ] 5. fitdocs client: the relay-routed intervals.icu connector

- [ ] 5.1 Keep a target's publish record across a route switch
  - Add the shared-ledger protocol and its registry rule (a connector id
    other than its own, on a publish target); publish-core's target module
    gains the ledger identity, and the publish command loads ledgers under
    it.
  - Append the new name to the connectors surface and its count literal at
    landing.
  - Done when tests show the registry rejecting a self-naming or
    non-target declaration, an instance switched between the two
    intervals.icu connectors reading its existing ledger and deciding
    unchanged for a landed page, the reverse switch, a ledger written for
    another connector refused with exit 2 and nothing written, and the
    identity returning the plain connector id reds the switch test.
  - _Requirements: 2.1, 2.2_
  - _Depends: 1.1_

- [ ] 5.2 Lift the relay-target client code out of the Strava connector
  - Move the consent operations (with the target as a parameter) and the two
    relay-answer mapping tables to the relay-route module; the Strava
    connector calls them.
  - Browser-consent connectors declare a service name, required and checked
    by the registry; the connect engine stores the instance's own connector
    id; the disconnect notes name the service, and the CLI's started line
    stays strava-publish's neutral line, naming no service (R13.5).
  - Add the module to the connectors boundary test in this task; move the
    Strava mapping tests with their assertions kept.
  - Done when every Strava connect, disconnect, mapping and CLI test passes
    with every printed Strava line unchanged, and storing the Strava id
    literally reds a test that connects a second browser-consent connector
    registered by the test.
  - _Requirements: 3.3, 6.8, 6.9, 11.1, 11.2, 14.3, 14.4_

- [ ] 5.3 Add the relay-routed connector's settings and consent operations
  - The settings (`relay` required, `publish_upload` optional boolean,
    every other key ignored), the bind that accepts only relay settings, and
    the three consent operations through the relay-route module with the
    intervals.icu target, every secret registered with the redactor.
  - Add the module to the connectors boundary test in this task.
  - Done when settings tests show each refusal naming the file, instance and
    key before any request, `wellness = true` refused, an unknown or
    non-relay `relay` refused by the binding pass, each consent answer
    parsed over a scripted transport, and the module naming no intervals.icu
    address.
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 1.7, 3.1, 3.2_

- [ ] 5.4 Publish through the relay and register the connector
  - The publish operation of design.md: the known activities from the
    recorded link and the instance's own pull record (an ambiguous pull
    record with a recorded link sends the link alone with the known-only
    flag, and the relay's not found then gives ambiguous), the local refusals,
    one publish request, the upload request only after a definite
    `not_found` with uploads on, a readable or absent pull record and an
    intact file, sending the upload through the relay client's
    `max_request_bytes` keyword (strava-publish's, R13.3), the mapping through
    the relay-route module, and the direct
    link built by the direct route's own builder.
  - Register the connector after the direct one with its label, service
    name and ledger identity; name it in the connectors page's built-in list
    in the same task, since that pin reads the registry; the module names
    publish codes only through the protocol's re-export, which a boundary
    assertion pins.
  - Done when tests over a scripted transport cover every step and code,
    an unreadable pull record still posts through the link and answers local
    record unreadable on `not_found` with uploads on and off, an ambiguous
    pull record with a recorded link sends a known-only request and answers
    ambiguous on not found, a landed answer without an identifier maps as
    malformed, the link equals the direct route's for the same identifier,
    a data-mode client scripted with 503 sees one transport call for the
    publish request and one for the upload request, and dropping the
    unreadable-record branch, answering ambiguous before the request when a
    link is known, or sending the upload after a malformed answer reds a
    test.
  - _Requirements: 1.1, 1.2, 1.8, 1.9, 2.3, 2.4, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11_

- [ ] 5.5 Present the relay-routed connect and disconnect in the CLI
  - `fitdocs connect NAME [--no-browser]` and `fitdocs disconnect NAME
    [--local-only]` for a relay-routed instance through the shared
    browser-consent and disconnect paths: the neutral started line (no
    "connect <service>"), and disconnect notes naming intervals.icu.
  - Done when CLI tests pin the printed lines, including the neutral started
    line, show no browser call with
    `--no-browser`, exit 2 for `--register` and `--email` before any
    request, the credentials file written owner-only with the relay-routed
    connector's id, and the local-only note naming intervals.icu's settings.
  - _Requirements: 3.1, 3.2, 3.3, 11.1, 11.2, 14.3_

- [ ] 5.6 Decode the recorded intervals.icu exchanges through the client
  - The fitdocs suite decodes every recorded intervals.icu answer through
    the relay client and the relay-routed connector with a fake transport
    and asserts the code, the link and the parsed data.
  - Done when the decoding test passes and editing one recorded code reds
    it.
  - _Requirements: 6.9, 12.1_
  - _Depends: 4.3_

- [ ] 6. Integration and validation

- [ ] 6.1 Hold the fitdocs-side guarantees with a relay-routed instance configured
  - The socket-guarded offline-commands test gains a relay-routed instance
    in its wired root; a bare and a named `fitdocs pull` make no request for
    it and leave its pull record byte-identical; `fitdocs publish --targets`
    shows it ready and not connected; the confinement test shows its connect
    writing nothing under the data root.
  - An end-to-end route switch: a root published through the direct route
    and switched to the relay route reports not connected until connected,
    then decides unchanged for a landed page and sends its recorded
    identifier as a known activity for a changed one.
  - Sentinel strings in every scripted relay answer appear in no output,
    ledger or page.
  - Done when these tests pass and a scripted relay request during `fitdocs
    pull` fails the socket guard.
  - _Requirements: 1.6, 1.8, 1.10, 2.1, 2.3, 6.11_
  - _Depends: 1.1_

- [ ] 6.2 Prove nothing from intervals.icu escapes the relay but the identifier
  - A scripted intervals.icu that plants one sentinel in every field and
    header, driven through connect, publish, upload, disconnect and a
    refused token on both backends.
  - Done when the sentinel appears in no envelope answer, page, log record
    or database column outside the sealed token, no table holds an activity
    or athlete identifier, and an identifier other than the scripted one
    never crosses.
  - _Requirements: 7.9, 12.1, 12.2, 12.3, 12.5_

- [ ] 6.3 Pin resolution parity across both routes
  - Append the `resolution` cases to the shared case file: each gives a
    resolution state (recorded link, pull record tiers or unreadable, facts,
    upload setting, file state, intervals.icu's answer per call), the
    expected code, the publish request the relay-routed connector sends and
    the relay's answer to it, and, when the case sends one, the upload
    request and the relay's answer to that.
  - Scripting rule: every scripted intervals.icu answer is fixed per call
    kind and activity and returned on every attempt; answer sequences that
    change between attempts stay in each route's own repeat tests (3.7 and
    the direct route's transport tests), and the absent-yet-listed state is
    left out, as design.md's ParityCases states. Cover at least: link confirmed; link absent then pull record;
    a recorded link with an ambiguous pull record (link confirmed, and link
    absent); an ambiguous pull record without a link; an unreadable pull
    record with uploads on and off; facts missing with and without a link;
    a listing match; a Strava import; uploads on and nothing found.
  - The fitdocs suite runs every case through the direct connector over a
    scripted intervals.icu transport and through the relay-routed connector
    over a scripted relay; the relay suite runs every case's request through
    the publisher over its scripted outbound and checks the case's relay
    answer for each request.
  - Done when both suites pass every case, and making the relay-routed
    connector answer ambiguous before any request when a link is known reds
    the fitdocs suite on the link-confirmed case.
  - _Requirements: 9.7_
  - _Depends: 3.8, 5.4_

- [ ] 7. Documentation, gates, steering and amendments

- [ ] 7.1 Document the relay route in the connectors page
  - The relay-route subsection of design.md inside the intervals.icu
    section, after its publishing subsection, with no URL; heading rows
    added in page order to the connectors and intervals docs pins.
  - It states that the direct route's transport makes up to three attempts
    and waits and repeats after a 429, while the relay repeats a listing or
    an update once after a server or network failure and never after a 429,
    with the same code for the final answer.
  - Done when the connectors docs tests and the neutral scan pass, the
    stated direct attempt count, the direct route's repeat after a 429 and
    the post and file limits equal the code's constants (binding tests over
    the transport's attempt count and repeated statuses and the wire
    bounds), and deleting the route-switch paragraph reds a test.
  - _Requirements: 9.6, 15.1, 15.7_
  - _Depends: 1.1_

- [ ] 7.2 Document the intervals.icu target and the shared target sections for operators
  - The relay page's target-neutral section (variables with "with either
    target", encryption keys and rotation moved there, connect pages,
    privacy policy and consent) and its intervals.icu section of design.md,
    including the self-hosting note; the policy summary bound to the policy
    composition for both targets.
  - Its routes subsection states the relay's single repeat of a listing or
    an update, which the relay docs test binds to the publisher's named
    repeat constant.
  - Done when the relay docs tests pass, removing an intervals.icu policy
    section from the summary reds its binding test, changing the stated
    repeat count reds its binding, and the page names no hosting or email
    provider.
  - _Requirements: 9.6, 13.7, 15.2, 15.7_

- [ ] 7.3 Make every network statement name `fitdocs publish --yes` and the relay route
  - Written to hold in any landing order with the other Phase 14 targets:
    every statement that lists the network-touching commands names `fitdocs
    publish --yes` (add it where absent, keep it where another target added
    it), and "What leaves your machine" gains the relay-routed line (its
    bound relay's URL, never intervals.icu).
  - Pins require both, one named mutation per place.
  - Done when the network-statement tests pass and removing the command or
    the relay-routed line from any place reds its pin.
  - _Requirements: 15.3_

- [ ] 7.4 Add the steering sentences
  - `tech.md` "Network and Credentials" gains the relay-routed sentence of
    design.md; `structure.md` gains the shared-rules sentence; each is
    line-disjoint from other specs' edits.
  - Rewrite the two `structure.md` clauses intervals-publish added that name
    the match rule (in the connectors sentence and in the identity
    sentence's importers) to name `identity.strict`, matching the import
    task 1.3 switched.
  - Done when the steering pins still pass, the new sentences read as in
    design.md, and no steering sentence still says the intervals connector
    imports `identity.matching`.
  - Not parallel with 7.3, which may touch the same `tech.md` section.
  - _Requirements: 15.4_

- [ ] 7.5 (P) Record the changelog entries
  - Root Unreleased (pinned through `unreleased_since(text, V0_2_0)`): the
    relay route to intervals.icu, its settings and browser connect, and the
    service-named browser-consent lines. The relay changelog: a new section
    for the intervals.icu target, its variables, routes and pages, the
    widened condition on the target-neutral variables and the internal
    targets package, restating deploy contract 1, envelope 1 and seam 1.
  - Done when both changelog pins pass and moving the root entry into the
    0.2.0 section reds its pin.
  - _Requirements: 15.5_
  - _Boundary: Changelogs_

- [ ] 7.6 Record the amendments in the affected specifications
  - strava-publish, intervals-publish, publish-core, relay-server,
    connectors and intervals-connector, each with the items of design.md's
    Amendments Carried, worded like the earlier landed amendments and naming
    the pin that enforces each. publish-core pre-words its Req 11.6 as "the
    target's ledger identity (its connector id)"; its amendment here changes
    only that definition, to the ledger identity of design.md. Confirm the
    site-copy queue item still names true lines.
  - Done when each requirements document carries its dated amendment naming
    relay-intervals and the packaged agent skill is unchanged.
  - _Requirements: 14.2, 15.6, 15.8_

- [ ] 7.7 Run the full validation sweep
  - Both suites and gates, the release build and artifact check, the site
    build and checks, the sync check mode, the relay workflow and image
    smoke on both backends, and a scan that the packaged skill names no
    target.
  - Done when every gate is green and the sync check reports no drift.
  - _Requirements: 15.7, 15.8_

- [ ] 8. The maintainer's live check

- [ ] 8.1 Write the maintainer's live-check procedure and its record template
  - This task writes documents only. No implementation, review or
    validation session carries out any step that reaches intervals.icu
    through a real application.
  - The procedure, for the maintainer to carry out against the maintainer's
    own approved intervals.icu application and account: connect, publish an
    update to one activity, follow its direct link, disconnect; it states
    first that it writes to that real account, and lists what to observe for
    TBC-R1 to TBC-R9.
  - The record template: one row per step for the fitdocs code and the
    shapes observed, never an identifier, name, date, token or secret.
  - Never run by the test suite or CI.
  - Done when both files exist, the procedure's first section states the
    real-account write, and the template has a row for each of the four
    steps and each TBC-R item.
  - _Requirements: 16.2, 16.3_
  - _Depends: 1.1_

- [ ]* 8.2 Record the maintainer's live-check findings (maintainer-gated)
  - Only after the maintainer reports the live check, carried out by the
    maintainer on the maintainer's real intervals.icu account with the
    maintainer's explicit go; no session carries out a step.
  - Fill the record template and research.md's findings with the fitdocs
    codes and shapes the maintainer reports; a contradicted TBC-R item
    amends design.md and every affected task. No other task waits for this.
  - Done when every TBC-R item reads confirmed or contradicted and any
    contradiction's repair is merged.
  - _Requirements: 16.3, 16.4_
