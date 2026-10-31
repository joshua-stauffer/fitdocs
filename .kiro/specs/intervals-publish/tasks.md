# Implementation Plan

Prerequisite: publish-core is on `main`, including the controller's R11
folds (the connector protocol re-exports `PublishCode` and `TARGET_CODES`,
and the vocabulary carries `local_record_unreadable` after `ready`): its
vocabulary, request values, single-attempt mode, publish operation protocol
and registration rules for groups 2 and 3, and its engine, ledger,
`published` region and `fitdocs publish` command for tasks 3.3 and 5.1.
Implementation does not start before then. relay-server is expected to land
first too (its network-statement places and `fitdocs disconnect` predicate),
but every task here holds in either order: 4.2 adds what is missing and 4.3
appends after whatever clauses are present.

Streams: the transport and the settings key (1.x) are independent; the
connector helpers (2.x) all live in the intervals module and its new test
module, so they run in order; the publish operation (3.1) wires them and
declares the target; the privacy guards (3.2), the end-to-end tests (3.3),
the documentation and the network statements (4.x) and the validation group
(5.x) follow.

Every task leaves the full suite, ruff, ruff format and mypy green on its
own. Every new assertion names the production mutation it dies on
(`tech.md`, Testing; `change-protocol.md` § Fixture Discrimination); run the
named mutations before reporting a task done.

Shared, append-only touches (rebase-safe against `strava-publish` and
`relay-server`): the intervals entry of the connectors boundary pin (each
task that adds an import updates only that entry); the `intervals.icu`
neutral-scan exemption entry; `_EXPECTED_HEADINGS`; `CHANGELOG.md`
Unreleased; the amendment blocks. The network-statement task (4.2) is
idempotent: whichever publish target lands first adds `fitdocs publish
--yes` and its predicate, and the second adds only its own host line.

This spec changes neither `CONTRACT_VERSION` nor `DOC_VERSION`, adds no
command and no runtime dependency, so no version or command-count pin
moves. Nothing under `website/content/` is edited (R9); the site copy is
`.kiro/queue/2026-10-31-intervals-publish-site-copy.md`.

- [ ] 1. Foundation: the update method and the upload switch

- [ ] 1.1 (P) Add the update method to the connector transport
  - Admit the update method in the request value and add the client's update
    helper beside the existing post helper, taking a body, plain and secret
    headers, and publish-core's single-attempt marker.
  - An unmarked update in data mode is retried exactly like any data
    request; a marked one is sent once; the standard-library transport sends
    the method it is given.
  - Add a sentence to the transport module's docstring naming the three
    request methods (today only the request value's type names them).
  - Done when transport-seam tests with a scripted transport show the update
    reaching it with its method, body and secret headers; three calls for an
    unmarked data-mode update answered 503, 503, 200; one call when marked;
    and, through the standard-library transport with a patched opener, a
    request whose method is the update method. The method test dies on the
    helper sending a post; the retry test dies on marking the helper's
    requests single-attempt by default.
  - _Requirements: 5.5_
  - _Boundary: TransportPut_

- [ ] 1.2 (P) Read the per-instance upload switch
  - The intervals.icu settings gain an upload switch, off when the key is
    absent; a boolean sets it; any other value is a settings error naming the
    key and the offending value, which the framework reports naming the
    settings file and the instance before any request or write.
  - The source filter and the rule that every other key is ignored are
    unchanged; no pull request changes.
  - Done when settings tests cover the key absent, true, false, a string, an
    integer one and a list, each refusal's message naming the key, through
    both the connector's parser and the connectors settings loader; they die
    on accepting a truthy non-boolean; the existing pull and wellness tests
    pass unchanged.
  - _Requirements: 1.5, 2.1, 2.3_
  - _Boundary: IntervalsDeclaration_

- [ ] 2. Core: finding the activity and writing to it

- [ ] 2.1 Map intervals.icu's answers into publish codes
  - Add the three request kinds (a read, a write safe to repeat, a write that
    creates), the answer classes, the success statuses per kind, and the one
    answer table of the design, with every cell a code a publish target may
    return or the flow's own handling.
  - Add the remote identifier rule (letters and digits, 1 to 64) and the
    direct link built from a usable identifier, with its inverse that reads
    an identifier back out of a recorded link of exactly that form.
  - Name the publish codes through the connector protocol's re-export only;
    the intervals module imports nothing from the publish package, so its
    entry in the connectors boundary pin is unchanged by this task.
  - Create the publish test module and add it to the `intervals.icu`
    neutral-scan exemption entry, since it spells the link base.
  - Done when tests pin the table as a literal, show every cell's code is in
    the target codes and none is posted or uploaded, classify each status of
    the design's list per kind, and accept `i9000001` while refusing `i9/1`,
    `i 1`, a 65-character id, a non-https link and a link with a query; they
    die on swapping the creation column's 5xx cell to unavailable, on
    classifying 201 as an update's success, and on admitting `/` in an id.
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 8.2, 8.3_
  - _Boundary: AnswerMapping_

- [ ] 2.2 Find the activity through the recorded link and the pull record
  - Read the instance's own pull record read-only through the connectors
    ledger reader; an absent record names no activity; an unreadable one is
    reported to the caller as the local-record-unreadable code (which the
    operation in 3.1 notes, keeping its read-only steps and barring only the
    upload); the record is never written.
  - Take the base file's digest first and the page's other digests only when
    the base names no activity; one identifier in a tier is the answer, more
    than one is the ambiguous code; identifiers that are not usable name
    nothing; an entry's outcome does not matter.
  - Import the ledger reader and admit it in the intervals entry of the
    boundary pin; rewrite the intervals module docstring's import sentence
    (`intervals.py:6-9`) to name it.
  - Done when tests over ledgers written with the connectors ledger writer
    cover: the base digest mapped; only an extra mapped; base and extra
    mapped to different activities (the base wins); two activities for the
    base (ambiguous); two for the extras with none for the base (ambiguous);
    a file of invalid TOML (the local-record-unreadable answer, file bytes
    unchanged); a malformed identifier; and no source digests. They die on
    reading the second tier when the first has an answer, on returning the
    first of two, and on reading an unreadable record as an empty one.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 8.3_
  - _Boundary: ActivityFinding_

- [ ] 2.3 List the activities around the page's start
  - Compute the local-date window from the page's UTC start date, one day
    before through two days after, as date-time bounds; request the listing
    for the key's own athlete with exactly the design's fields, through the
    data-mode client with the credential as secret headers.
  - Map a transport failure or a non-success answer through the table's
    read column; a body that is not a JSON array of objects each with a
    usable identifier is the unavailable code; parse each entry's fields as
    the design states, absent or malformed values as absent and never zero;
    keep a repeated identifier once.
  - Done when tests assert the request's address, query and header names; for
    starts at 00:30 and 23:30 UTC the window holds the local wall-clock start
    at every whole-hour offset from -12:00 to +14:00; each field's present,
    absent and malformed forms; and each failure's code. They die on a window
    starting on the UTC date itself, on a window ending one day after it, and
    on reading a start without an offset as UTC.
  - _Requirements: 3.5, 7.4, 9.3, 9.5_
  - _Boundary: ActivityFinding_

- [ ] 2.4 Match the listing one-to-one
  - Over entries not already answered absent: the one non-Strava entry
    carrying the publication id as its external identifier; otherwise the one
    non-Strava entry for which activity-identity's rule gives the strict
    tier, with the page's sport on both keys and no device or kind, so that
    sport is not compared and no other tier can hold; several at either step
    is the ambiguous code.
  - With no match, a Strava entry starting within the rule's start tolerance
    of the page, by its instant start or, without one, by its local
    wall-clock start against the page's recorded wall clock, is the
    not-updatable code; otherwise no activity.
  - Import the match rule inside the matching helper only and admit it in the
    intervals entry of the boundary pin; extend the intervals module
    docstring's import sentence and the connectors package docstring's
    allowed-import sentence (`connectors/__init__.py:13-16`) with it;
    importing the connectors package in a fresh interpreter loads no identity
    module.
  - Done when tests cover: an external-id match beating a strict match; a
    strict match by distance; by elapsed time with one distance missing; no
    match with both missing; a different sport still matching; two strict
    matches ambiguous; an absent identifier excluded; a Strava entry never
    matched and reported by instant start and by local start. They die on
    accepting the shifted tier, on testing the evidence for not-none instead of
    strict, on picking the first of two matches, and on matching a Strava
    entry.
  - _Requirements: 3.6, 3.7, 3.8, 4.1, 4.2_
  - _Boundary: ActivityFinding_

- [ ] 2.5 Update an activity's name and description
  - Send one update to the activity's address with a JSON body holding
    exactly the post's title as the name and its description, an empty
    description sent empty, through the unmarked data-mode client with the
    credential as secret headers.
  - Success is confirmed; the not-found answer is absent; every other answer
    and a transport failure map through the table's update column. The answer
    body is never read.
  - Done when tests assert the method, address, parsed body (exactly two keys),
    content type, that the title and description are in no address and the
    key only in the secret headers, a 503-503-200 sequence confirmed after
    retries, and each answer's result. They die on adding a third field to the
    body and on mapping the not-found answer to rejected.
  - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6, 9.2, 9.5_
  - _Boundary: ActivityWrites_
  - _Depends: 1.1_

- [ ] 2.6 Upload the base file once
  - Read the page's base file from the archive only when it is present,
    readable and hashes to the base digest; otherwise no file.
  - Build the one-part multipart body (field, file name, content type and the
    file's bytes unmodified) with the design's deterministic boundary rule.
  - Send the upload to the key's own athlete with the publication id as the
    only query value, marked single-attempt; a transport failure is
    unconfirmed; a 200 or 201 yields whether it created and the one usable
    identifier its answer names, or none; every other answer maps through
    the table's creation column.
  - Done when tests assert the address and decoded query, that the multipart
    part's bytes equal the archived file, the boundary rule over a file that
    contains the first boundary's delimiter, one transport call for 503, 429
    and a transport failure, and the answer parser over one id, none, two
    distinct ids, a malformed id and a non-object body. They die on dropping
    the single-attempt marker, on putting the title in the query, and on
    skipping the digest check (a tampered archive file is uploaded).
  - _Requirements: 6.2, 6.3, 6.4, 6.7, 9.5_
  - _Boundary: ActivityWrites_

- [ ] 3. Integration: the publish operation and the target

- [ ] 3.1 Answer publish requests and declare the publish target
  - Implement the publish operation in the design's order: the recorded
    link, the pull record, the facts check, the listing match, then the
    absent branch (local record unreadable when the pull record could not be
    read, whatever the upload setting; not found with uploads off; missing
    file; the upload and its confirming update), each activity updated at most once and one answered
    absent excluded for the rest of the request; after a creation, any answer
    to the confirming update but success is unconfirmed.
  - Rewrite the intervals module docstring's opening ("Lists, filters and
    fetches") to say it also publishes posts.
  - Declare the three publish capabilities beside the two pull capabilities
    and the fixed link label, in the same change, so that registration's
    publish rules accept the connector; move the two capability pins
    (`tests/connectors/test_intervals.py:118-120`,
    `tests/connectors/test_intervals_wellness.py:822-825`) to the five-member
    literal.
  - Done when operation tests cover every branch of the design's flow with
    its code and link, count at most one listing, one upload and one update
    per identifier, show the connector passes registration and appears in the
    target listing with its three publish capabilities in vocabulary order;
    an unreadable pull record with nothing else resolving answers local
    record unreadable with uploads on (no file read, no upload) and with
    uploads off alike, and still posts through a recorded link or a listing
    match; every non-landed result carries no link;
    they die on dropping the absent set (a stale identifier is updated
    twice), on answering uploaded after an unconfirmed creation, on checking
    the facts before the pull record (a page without distance or elapsed time
    and with a pull record then gets activity facts missing), on uploading
    when the pull record was unreadable, on answering not found with uploads
    off when the pull record was unreadable, on returning the link with a
    non-landed code, and on dropping push from the capabilities.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.2, 3.4, 3.9, 3.10, 4.2, 5.3, 6.1, 6.5, 6.6, 6.7, 6.8, 7.1, 7.8, 9.4_
  - _Depends: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [ ] 3.2 Guard the publish path against service text
  - Add the call-graph test: parse the intervals module, follow every
    module-level function a call reachable from the publish operation names,
    and assert that the two service-message helpers, the generic failure
    mapper and both pull status mappers are unreachable while the update,
    listing, upload and credential helpers are reachable (the positive
    control).
  - Add the sentinel test: every answer class at every step of the flow,
    with response bodies and headers carrying a sentinel string; the
    sentinel is in no field of any result and no call raises.
  - Done when both tests pass and die on adding a service-message call in
    the update helper and on raising an error that quotes the response body
    from the listing helper.
  - _Requirements: 8.1_

- [ ] 3.3 Publish through the CLI end to end
  - Over a synced temporary data root with an intervals instance, its key in
    the override variable and the CLI's connector transport patched to a
    scripted transport, run `fitdocs publish --yes` for a page that opts in.
  - Add the CLI test module to the `intervals.icu` neutral-scan exemption
    entry.
  - Done when tests show: a listing then an update, the publish ledger
    recording posted with the direct link, the page's published region
    reading the link with the `intervals.icu` label, and the JSON report's
    `link_refused` false; a second run sending nothing (an empty script); a
    pull record written by the test leading to an update with no listing;
    uploads on and nothing listed leading to one upload, one update and
    uploaded, with the upload's external identifier equal to the publication
    id the publish ledger recorded (the CLI mints it at random, so the test
    reads it back and never fixes it); and `publish_upload = "yes"` making
    `fitdocs publish --yes` exit 2, naming the settings file, the instance,
    the key and the value, with an empty script and the page and ledgers
    byte-identical. They die on dropping the confirming update after an
    upload (the page then carries no link) and on building the link from a
    different base.
  - _Requirements: 1.3, 2.3, 5.3, 6.5, 9.1, 9.6_
  - _Depends: 3.1_

- [ ] 4. Documentation, network statements and records

- [ ] 4.1 Document publishing in the intervals.icu section
  - Rewrite the section's opening (pulls and publishes; writes only an
    activity's name and description, and the base file while uploads are
    on), remove "It never writes to the account.", add the switch to
    "Configuring" and its "no other key" sentence, and add a "Publishing"
    subsection after "Wellness" with the design's content and the answer
    table; add one sentence to "The ledger" that publishing reads it and never
    writes it; state that a malformed `publish_upload` is a configuration
    error for `fitdocs pull` too, since it goes through the same settings
    loader; document the local-record-unreadable answer (an unreadable
    instance ledger never stops an update through the link or the listing;
    when neither finds the activity the answer is local record unreadable
    whether or not uploads are on, never not found and never an upload);
    update the
    README's Connectors paragraph to say the intervals connector also
    publishes posts.
  - Append the new heading to `_EXPECTED_HEADINGS` and to the intervals
    docs test's subsection list; bind the page's answer table to the code's
    table; pin that the retired sentence is gone and the switch's documented
    default equals the settings default.
  - Done when the docs tests pass and die on changing one table cell, on
    restoring the retired sentence, and on dropping the new heading.
  - _Requirements: 11.1, 11.2, 11.3_
  - _Depends: 3.1_

- [ ] 4.2 Name `fitdocs publish --yes` in every network statement
  - In every statement that lists the commands making network requests
    (README "Route maps", `docs/configuration.md` twice, the CLI module
    docstring, the sync engine's docstring, the tiles module three times,
    `docs/connectors.md` "What leaves your machine", and `tech.md` "Network
    and Credentials"), name `fitdocs publish --yes`, and where a statement
    lists the commands making none, name `fitdocs publish` without `--yes`
    and `fitdocs publish --targets`. In `tech.md`, add them in their own
    sentences ("`fitdocs publish` without `--yes` and `fitdocs publish
    --targets` make none", skipped when an earlier target recorded it) and
    leave the pinned no-request list sentence unchanged.
  - In "What leaves your machine", say that an intervals.icu instance's
    publish requests go to intervals.icu, by name and section link, with no
    URL.
  - Idempotent: a statement that already names the command (another publish
    target landed first) is left as it is, and the predicate below is added
    only if absent; this task then adds only the intervals.icu host line.
  - Extend `tests/connectors/test_network_statements.py` with the predicate
    `_names_publish_command` (the name shared with strava-publish; skipped
    when an earlier target added it) requiring `fitdocs publish --yes` in
    every rewritten place's window,
    moving anchors with the text; add the connectors page's "What leaves your
    machine" statement to the rewritten places if relay-server has not
    already added it.
  - Done when the network-statement tests, the three existing `tech.md`
    list pins and the neutral scan pass, and dropping `fitdocs publish --yes`
    from any one place reds that place's case.
  - _Requirements: 10.1, 10.2, 10.3, 10.4_
  - _Depends: 4.1_

- [ ] 4.3 (P) Record the changelog, the amendments and the steering
  - Append the Unreleased entries (Added: publishing to intervals.icu, the
    switch, the direct link; Changed: the connector writes to the account for
    pages that opt in, and, unless an earlier publish target's entry already
    says so, the network statements name the publish command; no contract
    change, no action), pinned through the changelog view anchored to 0.2.0
    (`V0_2_0`).
  - Take the next free amendment number at landing in `connectors`,
    `intervals-connector` and, unless an earlier publish target already
    recorded it, `distribution`, recording the design's amendment texts and
    preserving every existing criterion and approval.
  - In the structure steering, append to the connectors sentence, after
    whatever clauses are present at landing, that the intervals connector
    imports activity-identity's match rule on its publish path and names
    publish codes through the connector protocol; and add the intervals
    connector's publish path to the identity sentence's importer list
    (`structure.md:68-71`, "`render`, `sync`, `audit` and `cli` import it").
  - Refresh the evidence line numbers in the site-copy queue item to the
    tree at landing.
  - The connectors amendment records that a connector target names publish
    codes only through the protocol's re-export (R11), and admits the pull
    ledger reader and the match rule in the intervals module.
  - Done when the changelog pin passes and dies on moving the entry into the
    0.2.0 section, the two steering sentences name the new edges, and each
    amended spec carries a dated amendment naming this spec with its status
    check clean.
  - _Requirements: 11.4, 11.5, 11.6, 11.7_
  - _Boundary: Records_
  - _Depends: 3.1_

- [ ] 5. Validation

- [ ] 5.1 Prove the privacy and offline guarantees
  - Through the CLI with an intervals instance configured: `fitdocs publish`
    without `--yes` and `fitdocs publish --targets` against an empty script
    (any request fails the test); a posting run whose every scripted body and
    header carries a sentinel string, with the sentinel absent from stdout,
    stderr, the publish ledger, the pull ledger and the page; the key and the
    title in no request address.
  - Run the whole suite, ruff, ruff format and mypy.
  - Done when these tests pass in the full suite on macOS and on CI; the
    sentinel case dies on building the direct link from a listing identifier
    without the identifier rule (a listing identifier carrying a sentinel and
    a hyphen then reaches the page), and the empty-script case dies on the
    engine treating a dry run as posting (a scratch-copy mutation of
    publish-core's posting flag, reverted after).
  - _Requirements: 8.1, 9.1, 9.2, 9.6_
  - _Depends: 3.3_

- [ ]* 5.2 Run the live check on the maintainer's account (maintainer-gated)
  - Runs only on the maintainer's explicit go at implementation time, with the
    maintainer's own key, after stating that it writes to the maintainer's
    real intervals.icu account; no automated agent runs it otherwise, and no
    other task waits for it.
  - Confirms TBC-P1 to TBC-P5: one update of an activity the maintainer
    names, and the answer for an activity id of another athlete (expected
    403, mapped to permission denied, which stops the target), the listing
    fields, an upload's answers for a new file and a
    duplicate (the maintainer deletes the test activity by hand), the
    external identifier's round trip, and the direct link's form.
  - Records findings in this spec's `research.md` as shapes, statuses and
    vocabulary only; a contradiction amends the design and the affected
    tasks.
  - Done when the findings section exists with every TBC-P item confirmed or
    contradicted, and any contradiction's repair is merged.
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_
